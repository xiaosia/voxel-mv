#!/usr/bin/env python3
"""体素关（voxel-mv 稳妥模式的一道关）。只量这种画风专有、脚本量得准的东西，不看构图和创意。
用法（在项目根目录）：python tools/voxel_check.py [out/mv.mp4] [--json]
                     python tools/voxel_check.py --shot S03 --data out/voxel_shot.json   （单镜头复查，run.py check --shot S03 的内部步骤）
读：out/voxel.json（tools/voxel_dump.mjs 逐帧读 window.voxelProbe）、plan.json、data/audio.timeline.json；给了成片还量画面。
写：out/voxel_check.md、out/voxel_check.json（给 tools/report.py 汇总）。
退出码只看必过档（V0、V4、碰撞 STUCK）；自动修/警告档只报告，见 checks_common.py。

  V0 不是占位场景      window.PLACEHOLDER 为假                                  【必过】
  V1 等高              同一帧里的角色「眼睛到脚底」世界高度差 ≤ 3%（故意放大缩小的写进 plan.json 的 sizes）【自动修：引擎按 mv_scale 校正】
  V2 贴地              贴地角色脚底离地面 ≤ 身高 2%；没有登记地面的不算贴地      【自动修：最大的平面 Group 自动 addGround】
  V2被挡               鞋底被前景方块挡住不超过 6 帧（碰撞推开后的贴着不算）     【警告】
  V3 不打滑            侧面走一拍前进 0.4 身高、跑一拍 1.6 身高（±40%），方向和朝向一致（原地踏步的写进 treadmill）【警告】
  V4 不发糊            角色在画面里的像素高 ≤ 素材站立像素高 × 1.5（连续超过 6 帧才算；1.2–1.5 倍只提示；交接窗口不算）【必过】
  V5 不用坏帧          frames.json 的 bad 里列的帧一次都不出现                   【自动修：引擎换最近的好帧】
  V6 微缩质感          非特写帧里 ≥ 70% 开着移轴（band ≤ 0.35）；成片里近黑像素（亮度 < 8）> 1% 的帧只能出现在登记过的转场、交接和片头片尾 1.5 秒里
                       （plan.json 的 grade 里标了 dark: true 的段落放宽到 8%）  【警告】
  V7 表情卡拍          plan.json 的每个表情符号弹出帧离最近的拍点 ≤ 1 帧         【自动修：吸附到 ±3 帧内最近拍点】
  STUCK 碰撞           推不开的（头顶太低、推开太远、卡死角）一次都不许有（plan.json 的 allow 里按时间段登记过的豁免不拦）【必过】
另外报告（不拦）：每个镜头的可见方块数（场景细节）、角色景别分布。"""
import json, os, subprocess, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checks_common as CC
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('video', nargs='?', help='成片或检查小样.mp4（不给就只查探针层）')
    ap.add_argument('--shot', help='只查一个镜头（plan.json scenes 的 id），配合 --data 用单镜头 dump')
    ap.add_argument('--data', default='out/voxel.json', help='探针数据文件（默认 out/voxel.json；--shot 时是 voxel_dump.mjs --out 出的单镜头文件）')
    ap.add_argument('--json', action='store_true', help='只把结果写进 out/voxel_check.json（markdown 报告照写）')
    A = ap.parse_args()
    VID, SHOT, DATA = A.video, A.shot, A.data
else:
    VID, SHOT, DATA = None, None, 'out/voxel.json'

P = os.getcwd()
V = json.load(open(DATA if os.path.isabs(DATA) else os.path.join(P, DATA), encoding='utf-8'))
plan = json.load(open(os.path.join(P, 'plan.json'), encoding='utf-8'))
TL = json.load(open(os.path.join(P, 'data/audio.timeline.json'), encoding='utf-8'))
MODE = open(os.path.join(P, 'MODE'), encoding='utf-8').read().strip() if os.path.exists(os.path.join(P, 'MODE')) else 'safe'
START, FPS, STEP = plan['start'], V['fps'], V.get('step', 1)
F = V['frames']
if SHOT:
    F = [fr for fr in F if fr['shot'] == SHOT]
    if not F: sys.exit(f'--shot {SHOT}：dump 里没有这个镜头的帧（{DATA} 覆盖的是 {"单镜头" if "shot" in DATA else "全片"}）')
rows, notes, RULES = [], [], []

def res(name, ok, detail):
    """name 以规则 id 开头（'V4 不发糊'）；V2被挡 这种连写 id 的按整段当 id"""
    rid = name.split(' ', 1)[0]
    rows.append(f'| {name} | {"PASS" if ok else ("**FAIL·" + CC.CN[CC.tier(rid)] + "**") if CC.tier(rid) != "warn" else "警告"} | {detail} |')
    RULES.append({'rule': rid, 'name': name.split(' ', 1)[1] if ' ' in name else rid, 'ok': ok, 'detail': detail})

def spans(fs, gap=1):
    """帧号列表 → [(f0, f1)] 连续段"""
    out = []
    for f in sorted(fs):
        if out and f - out[-1][1] <= gap * STEP: out[-1][1] = f
        else: out.append([f, f])
    return out
def fmt(sp, n=6): return '、'.join(f'{a}–{b}' if a != b else f'{a}' for a, b in sp[:n]) + ('…' if len(sp) > n else '')
def declared(key, who, f):
    return any(d.get('who') in (who, None, '*') and d['f0'] <= f <= d['f1'] for d in plan.get(key, []))

# ---------- V0 ----------
res('V0 不是占位场景', not V.get('PLACEHOLDER'), '已换成自己的场景' if not V.get('PLACEHOLDER') else 'shots.js 里 R.run(...) 还带着 placeholder: true')

# ---------- V1 等高 ----------
sizes = plan.get('sizes', {})
bad1 = []
for fr in F:
    cs = [c for c in fr['chars'] if not fr['cut']]
    if len(cs) < 2: continue
    e = [c['eyeW'] / (sizes.get(c['id'], {}).get('scale', 1)) for c in cs]
    if max(e) / min(e) - 1 > 0.03: bad1.append(fr['f'])
undecl = sorted({c['id'] for fr in F for c in fr['chars'] if abs(c['scale'] - sizes.get(c['id'], {}).get('scale', 1)) > 0.01})
res('V1 等高', not bad1, (f'有 {len(bad1)} 帧两人眼睛到脚底差 > 3%：{fmt(spans(bad1))}' if bad1 else '同框角色眼睛到脚底一致')
    + (f'；{"、".join(undecl)} 用了没登记的 scale（写进 plan.json 的 sizes：{{"名字": {{"scale": 1.2, "why": "…"}}}}）' if undecl else ''))

# ---------- V2 贴地（悬空=自动修）+ V2被挡（警告；occlude 旧写法和 plan.allow 都认） ----------
float_, noground, blocked = {}, {}, {}
alsB = CC.allow_map(plan, 'collide')
for fr in F:
    if fr['cut']: continue
    for c in fr['chars']:
        if not c['snap'] or c['onTop']: continue
        if c['noGround']: noground.setdefault(c['id'], []).append(fr['f']); continue
        if c['gap'] is not None and c['gap'] > 0.02 * c['H']: float_.setdefault(c['id'], []).append(fr['f'])
        if c.get('blocked') and not c.get('legit') and not declared('occlude', c['id'], fr['f']) and not CC.allowed(alsB, c['id'], fr['f']):
            blocked.setdefault(c['id'], []).append(fr['f'])
msg, ok2 = [], True
for who, fs in noground.items(): ok2 = False; msg.append(f'{who} 脚下没有登记的地面（R.addGround）{fmt(spans(fs))}')
for who, fs in float_.items(): ok2 = False; msg.append(f'{who} 脚底离地 > 2% 身高 {fmt(spans(fs))}')
res('V2 贴地', ok2, '；'.join(msg) or '脚都踩在地面上')
msg, okb = [], True
for who, fs in blocked.items():
    long = [s for s in spans(fs) if (s[1] - s[0]) / STEP + 1 > 6]
    if long: okb = False; msg.append(f'{who} 鞋底被前面的方块挡住 {fmt(long)}（立牌离挡的东西远一点，或写进 occlude）')
res('V2被挡 鞋底', okb, '；'.join(msg) or '鞋底没有被挡（推开后贴着家具的不算）')

# ---------- V3 不打滑 ----------
EXP = {'walk_side': 0.4, 'run_side': 1.6}
beats = [round(b * FPS) + START for b in TL['beat_times']]
cutf = {fr['f'] for fr in F if fr['cut']}
byf = {fr['f']: fr for fr in F}
def at(f, who):
    fr = byf.get(f); return next((c for c in fr['chars'] if c['id'] == who), None) if fr else None
bad3 = []
for b0, b1 in zip(beats, beats[1:]):
    if any(f in cutf for f in range(b0, b1 + 1)): continue
    fr0, fr1 = byf.get(b0 - b0 % STEP), byf.get(b1 - b1 % STEP)
    if not fr0 or not fr1 or fr0['shot'] != fr1['shot']: continue
    for c0 in fr0['chars']:
        c1 = at(fr1['f'], c0['id'])
        if not c1 or c0['act'] not in EXP or c1['act'] != c0['act'] or declared('treadmill', c0['id'], b0): continue
        d = np.subtract(c1['pos'], c0['pos']); step = float(np.hypot(d[0], d[2])) / c0['H']
        exp = EXP[c0['act']]; dirok = (c1['right'] - c0['right']) * (-1 if c0['flip'] else 1) > 0
        if not (0.6 * exp <= step <= 1.4 * exp) or not dirok:
            bad3.append((b0, c0['id'], c0['act'], step, dirok))
if bad3:
    det = '；'.join(f'{w} {a} @{b}：一拍前进 {s:.2f} 身高（要 {EXP[a]}）' + ('' if ok else '，方向和朝向相反') for b, w, a, s, ok in bad3[:6])
    res('V3 不打滑', False, f'{len(bad3)} 拍脚下打滑：{det}' + ('…' if len(bad3) > 6 else '') + '（原地踏步、镜头跟拍不算：世界坐标里要真的往前走；确实原地的写进 treadmill）')
else: res('V3 不打滑', True, '走一拍一步、跑一拍两步，步幅和位移对得上')

# ---------- V4 不发糊 ----------
hand = set()
for h in plan.get('handoffs', []): hand |= set(range(h['f0'] - 72, h['f1'] + 73))   # 交接窗口（含前后 3 秒的推拉）由交接卡定大小，不算
bad4, soft4 = {}, {}
for fr in F:
    if fr['f'] in hand: continue
    for c in fr['chars']:
        k = c['hpx'] / c['srcpx']
        if k > 1.5: bad4.setdefault(c['id'], []).append(fr['f'])
        elif k > 1.2: soft4.setdefault(c['id'], []).append(fr['f'])
long4 = {w: [s for s in spans(fs) if (s[1] - s[0]) / STEP + 1 > 6] for w, fs in bad4.items()}
long4 = {w: s for w, s in long4.items() if s}
res('V4 不发糊', not long4, '；'.join(f'{w} 放大到素材的 1.5 倍以上 {fmt(s)}（换远一点的景别，或者换高分辨率素材：把 4 倍原图放进 assets/<角色>/）' for w, s in long4.items()) or '角色都没被放大到发糊')
for w, fs in soft4.items(): notes.append(f'{w} 有 {len(fs)} 帧放大到素材的 1.2–1.5 倍（{fmt(spans(fs), 4)}），截图看看边缘软不软')

# ---------- V5 坏帧 ----------
bad5 = sorted({(c['id'], c['act'], c['i'] + 1) for fr in F for c in fr['chars'] if c['bad']})
res('V5 不用坏帧', not bad5, '、'.join(f'{w} {a} 第 {i} 帧' for w, a, i in bad5) or '没用到坏帧')

# ---------- V6 微缩质感 ----------
nonclose = [fr for fr in F if not fr['cut'] and not any(c['h'] > 0.6 for c in fr['chars'])]
tilt = [fr for fr in nonclose if fr['post']['band'] <= 0.35 and fr['post']['hblur'] < 0.5]
share = len(tilt) / max(1, len(nonclose))
ok6, msg6 = share >= 0.7, [f'非特写帧开移轴 {share:.0%}（要 ≥ 70%）']
if VID and not SHOT:
    N = plan['end'] - START
    allowed = set(range(0, 36)) | set(range(N - 36, N))
    for k in V.get('TRANSITIONS', []):
        if k.get('kind') in ('flash', 'iris', 'cut', 'dissolve', 'other') or str(k.get('to', '')).startswith('T') or str(k.get('from', '')).startswith('T'):
            allowed |= set(range(int(k['t0'] * FPS) - 2, int(k['t1'] * FPS) + 3))
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', VID, '-vf', 'select=not(mod(n\\,6)),scale=480:270', '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                         capture_output=True, check=True).stdout
    g = np.frombuffer(raw, np.uint8).reshape(-1, 270, 480)
    # 调色关键帧写了 dark: true 的段落（夜景、桥段压暗）近黑像素放宽到 8%：暗是故意的，但不能大片死黑
    gk = sorted(plan.get('grade') or [], key=lambda k: k['f']); darkf = set()
    for k, nx in zip(gk, gk[1:] + [{'f': plan['end']}]):
        if k.get('dark'): darkf |= set(range(k['f'] - START, nx['f'] - START))
    dark = [i * 6 for i in range(len(g)) if (g[i] < 8).mean() > (0.08 if i * 6 in darkf else 0.01) and i * 6 not in allowed]
    if dark: ok6 = False; msg6.append(f'有 {len(dark)} 个取样帧近黑像素 > 1%（本段帧号 {fmt(spans(dark, 6))}）：阴影太黑、天空太暗或者场景有洞，补环境光；故意压暗的段落在 grade 关键帧上标 dark: true')
    else: msg6.append('没有死黑')
elif SHOT: msg6.append('（--shot 单镜头不量近黑，全片 check 再看）')
else: msg6.append('（没给成片，近黑像素没量）')
res('V6 微缩质感', ok6, '；'.join(msg6))

# ---------- V7 表情卡拍 ----------
bad7 = []
for e in plan.get('emotes', []):
    d = min(abs(e['f0'] - b) for b in beats)
    if d > 1: bad7.append(f"{e['who']} {e['g']}@{e['f0']}（离拍 {d} 帧）")
res('V7 表情卡拍', not bad7, '、'.join(bad7[:8]) or f"{len(plan.get('emotes', []))} 个表情符号都在拍上弹出")

# ---------- STUCK 碰撞推不开（必过；plan.allow 登记过且时间盖得住的豁免） ----------
stuck = {(s['who'], s['by'], s['reason'], s['hint'], fr['f']) for fr in F for s in fr.get('stuck', [])}
als = CC.allow_map(plan, 'collide')
bys, exc = {}, {}
for who, by, reason, hint, f in stuck:
    if CC.allowed(als, who, f): exc.setdefault((who, by, reason), (hint, []))[1].append(f); continue
    bys.setdefault((who, by, reason), (hint, []))[1].append(f)
for (w, b, reason), (hint, fs) in bys.items():   # allow 写了但时间段没盖住：提示哪条没生效
    miss = [a for a in als if a[0] == w and not CC.covered([a], w, min(fs), max(fs))]
    if miss: bys[(w, b, reason)] = (hint + f'；allow 里 {w} {miss[0][1]}–{miss[0][2]} 没盖住实际冲突（时间写错了？）', fs)
res('STUCK 碰撞推不开', not bys, '；'.join(f'{w} 和 {b}：{reason}（{fmt(spans(fs), 3)}）——{hint}' for (w, b, reason), (hint, fs) in bys.items()) or '没有推不开的碰撞')
for (w, b, reason), (hint, fs) in exc.items():
    notes.append(f'{w} 和 {b}：{reason}（{fmt(spans(fs), 3)}）在 allow 豁免里（{hint}），不拦——确认 why 写的是真的再交付')

# ---------- 报告（不拦）----------
shots = {}
for fr in F:
    if fr['cut']: continue
    s = shots.setdefault(fr['shot'], {'m': [], 'h': []}); s['m'].append(fr['meshes']); s['h'] += [c['h'] for c in fr['chars']]
size = lambda h: '大远景' if h < .15 else '全景' if h < .35 else '中景' if h < .6 else '近景/特写'
srows = [f"| {k} | {int(np.median(v['m']))} | {size(max(v['h'])) if v['h'] else '无角色'} |" for k, v in shots.items()]
thin = [k for k, v in shots.items() if np.median(v['m']) < 40]
if thin: notes.append(f'可见方块少于 40 的镜头：{"、".join(thin)}。场景细节是风格样张关最容易丢分的一项，看看能不能加小物件。')

for r in RULES: r.setdefault('tier', CC.tier(r['rule']))
nfail = sum(1 for r in RULES if not r['ok'])
tiers = {}
for r in RULES:
    if not r['ok']: tiers[r['tier']] = tiers.get(r['tier'], 0) + 1
head = '；'.join(f'{CC.CN[t]} {n}' for t, n in tiers.items()) or '全部 PASS'
title = f'体素关 · {SHOT}（单镜头复查）' if SHOT else '体素关（voxel check）'
md = [f'# {title}', '', f'mode: **{MODE}**；没过：{head}', '',
      '| 关 | 结果 | 说明 |', '|---|---|---|', *rows, '', '## 每个镜头（参考，不拦）', '', '| 镜头 | 可见方块数（中位） | 最大角色景别 |', '|---|---|---|', *srows, '']
md += [f'- {n}' for n in notes]
os.makedirs(os.path.join(P, 'out'), exist_ok=True)
suffix = f'_{SHOT}' if SHOT else ''
open(os.path.join(P, f'out/voxel_check{suffix}.md'), 'w', encoding='utf-8').write('\n'.join(md) + '\n')
p = CC.dump_json('voxel_check', RULES, os.path.join(P, 'out')) if not SHOT else f'out/voxel_check{suffix}.md（单镜头不写 json，不进 report）'
if __name__ == '__main__' and not A.json:
    print('\n'.join(rows)); print(f'-> out/voxel_check{suffix}.md  {nfail} 项没过（必过 {sum(1 for r in RULES if not r["ok"] and r["tier"] == "must")}）  {p}')
sys.exit(CC.exit_code(RULES))

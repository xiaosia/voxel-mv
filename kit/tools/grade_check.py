#!/usr/bin/env python3
"""调色关：全片的色调跟着段落走（前奏、主歌收着，副歌放开，桥段有反差），暗的段落也看得清。
只量段落之间的相对关系和底线，不规定用什么颜色、多亮多暗：基调、配色由你按歌和画风定。

用法（在项目根目录）：python tools/grade_check.py [成片或检查小样.mp4]
读：data/lines.json 的 parts（段落表，song_structure.py 产出）、plan.json（voxel-mv：start、grade、grade_why、cuts、incamera、handoffs）、
    out/page_meta.json 的 TRANSITIONS 和 ACTIONS.json 的 grade_why（song-mv）。
写：out/grade_check.md。稳妥模式有 FAIL 退出码 1；MODE 是 free 时只报告，退出码 0。

不量画面就能查的（plan.json 里有 grade 才查，voxel-mv）：
  L1 段落有调色关键帧   第二段起每个段落开头 ±1 拍内有一个 grade 关键帧（或者落在某个关键帧的过渡里）；第一段开头前后 1 拍内也要有一个
  L2 参数在范围内       exp 0.35–1.8、con 0.6–1.6、sat 0–2、temp/tint 绝对值 ≤ 2、shadowAmt/hiAmt 0–0.6、vig 0–0.7
量成片的（每秒取 4 帧，去掉底部 20% 字幕区和登记过的转场，按段落取中位数）：
  L3 有起伏             3 个段落以上时，最亮和最暗的段落平均亮度差 ≥ 0.12（0–1）
  L4 副歌放开           每个副歌 / 炸点比它前面最近的非副歌段落亮 ≥ 0.04，或者饱和度高 ≥ 0.03
  L5 桥段有反差         桥段和它前面那一段比：亮度差 ≥ 0.08、冷暖差 ≥ 0.05、饱和度差 ≥ 0.04，至少占一样
  L6 暗也看得清         每个段落：平均亮度 ≥ 0.10，最亮的 5% 像素亮度 ≥ 0.45（角色和主体还看得出来），过曝（亮度 > 0.98）的像素 ≤ 15%
故意不这么做（比如悲伤的歌最后一遍副歌反而暗下去），在 plan.json（voxel-mv）或 ACTIONS.json（song-mv）写 "grade_why": {"L4 P06": "原因"}（规则名 + 段落 id），
这一条就不拦，原因写进报告。歌没有段落表（data/lines.json 没 parts）时只查 L2。"""
import json, os, subprocess, sys
import numpy as np
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')

FPS, STEP = 24, 6
Y_RANGE, CH_Y, CH_C, BR_Y, BR_W, BR_C = 0.12, 0.04, 0.03, 0.08, 0.05, 0.04
DARK_Y, DARK_P95, CLIP = 0.10, 0.45, 0.15
RANGES = {'exp': (0.35, 1.8), 'con': (0.6, 1.6), 'sat': (0, 2), 'temp': (-2, 2), 'tint': (-2, 2), 'shadowAmt': (0, 0.6), 'hiAmt': (0, 0.6), 'vig': (0, 0.7), 'ease': (0, 10 ** 6)}
CN = {'intro': '前奏', 'verse': '主歌', 'pre-chorus': '导歌', 'chorus': '副歌', 'interlude': '间奏', 'bridge': '桥段', 'outro': '尾奏', 'build': '蓄力', 'drop': '炸点'}

ROOT = os.getcwd()
VID = sys.argv[1] if len(sys.argv) > 1 else None
load = lambda p, d=None: json.load(open(os.path.join(ROOT, p), encoding='utf-8')) if os.path.exists(os.path.join(ROOT, p)) else d
plan = load('plan.json', {}) or {}
lines = load('data/lines.json', {}) or {}
parts = [p for p in lines.get('parts') or [] if p['t1'] - p['t0'] >= 1.0]
tl = load('data/audio.timeline.json', {}) or {}
spb = (plan.get('tempo') or {}).get('spb') or tl.get('seconds_per_beat') or (60.0 / tl['bpm'] if tl.get('bpm') else 0.5)
BEAT = max(1, round(spb * FPS))
S0 = plan.get('start', 0)
mf = os.path.join(ROOT, 'MODE'); MODE = (open(mf, encoding='utf-8').read().split() or ['safe'])[0] if os.path.exists(mf) else 'safe'
WHY = {**((load('ACTIONS.json', {}) or {}).get('grade_why') or {}), **(plan.get('grade_why') or {})}
fails, rep = [], []
name = lambda p: p.get('name') or CN.get(p.get('label'), p.get('label'))
def fail(rule, pid, msg):
    k = f'{rule} {pid}' if pid else rule
    if k in WHY: rep.append(f'- {k} 不拦（grade_why：{WHY[k]}）：{msg}')
    else: fails.append(f'{rule} {msg}')

# ---------- L1 / L2：plan.json 的 grade ----------
G = sorted(plan.get('grade') or [], key=lambda g: g['f']) if 'grade' in plan or plan.get('grade') else None
if G is not None:
    if not G and parts: fail('L1', None, 'plan.json 的 grade 是空的：按段落表给每段定一个色调（见 references/plan-format.md「grade」）')
    for p in parts:
        f = S0 + round(p['t0'] * FPS)
        hit = any(abs(g['f'] - f) <= BEAT or (g['f'] <= f <= g['f'] + g.get('ease', 0) + BEAT) for g in G)
        if p is parts[0]: hit = hit or any(g['f'] <= f + BEAT for g in G)
        rep.append(f"- L1 {p['id']} {name(p)}（第 {f} 帧）：{'有' if hit else '没有'}调色关键帧")
        if G and not hit: fail('L1', p['id'], f"{p['id']} {name(p)}（第 {f} 帧）开头 ±1 拍（{BEAT} 帧）内没有 grade 关键帧：这一段的色调要和上一段分开定（想保持不变，就把上一段的值抄一遍，再在 why 里写为什么）")
    for g in G:
        for k, (lo, hi) in RANGES.items():
            if k in g and not (lo <= g[k] <= hi): fail('L2', None, f"第 {g['f']} 帧的 grade {k}={g[k]} 超出 {lo}–{hi}：再大就是坏图（死黑、过曝、颜色断层）")
elif plan:
    rep.append('- plan.json 里没有 grade：L1 不查（voxel-mv 的项目应该写；song-mv 不用）')

# ---------- 量成片 ----------
rows, M = [], {}
if VID and parts:
    W, H = 480, 270
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', VID, '-vf', f'fps={FPS // STEP},scale={W}:{H}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                         capture_output=True, check=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3)[:, :int(H * 0.8)].astype(np.float32) / 255
    skip = set()
    for c in plan.get('cuts', []): skip |= set(range(c['c'] - c.get('len', 12) // 2 - 2 - S0, c['c'] + c.get('len', 12) // 2 + 3 - S0))
    for c in plan.get('incamera', []) + plan.get('handoffs', []):
        if 'f0' in c and 'f1' in c: skip |= set(range(c['f0'] - 2 - S0, c['f1'] + 3 - S0))
    for k in (load('out/page_meta.json', {}) or {}).get('TRANSITIONS') or []:   # song-mv 页面登记的转场（秒，本片时间）
        if 't0' in k and 't1' in k: skip |= set(range(int(k['t0'] * FPS) - 2, int(k['t1'] * FPS) + 3))
    stats = []
    for i, a in enumerate(fr):
        lf = i * STEP
        if lf in skip: stats.append(None); continue
        Y = a @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        stats.append((Y.mean(), np.percentile(Y, 95), (Y > 0.98).mean(), (a.max(2) - a.min(2)).mean(), (a[..., 0] - a[..., 2]).mean()))
    for p in parts:
        sel = [s for i, s in enumerate(stats) if s and p['t0'] * FPS <= i * STEP < p['t1'] * FPS]
        if len(sel) < 3: rep.append(f"- {p['id']} {name(p)} 取样不到 3 帧，不量"); continue
        m = dict(zip(('Y', 'P95', 'CLIP', 'C', 'W'), np.median(np.array(sel), 0).tolist())); M[p['id']] = m
        rows.append(f"| {p['id']} | {name(p)} | {p['t0']:.1f}–{p['t1']:.1f} | {m['Y']:.2f} | {m['P95']:.2f} | {m['C']:.3f} | {m['W']:+.3f} |")
    mp = [p for p in parts if p['id'] in M]
    # L3
    if len(mp) >= 3:
        ys = [M[p['id']]['Y'] for p in mp]; lo, hi = mp[int(np.argmin(ys))], mp[int(np.argmax(ys))]
        rep.append(f"- L3 最暗 {name(lo)} {min(ys):.2f}、最亮 {name(hi)} {max(ys):.2f}，差 {max(ys) - min(ys):.2f}（要 ≥ {Y_RANGE}）")
        if max(ys) - min(ys) < Y_RANGE: fail('L3', None, f"全片段落亮度只差 {max(ys) - min(ys):.2f}（最暗 {name(lo)}、最亮 {name(hi)}），要 ≥ {Y_RANGE}：整片一个调子。收着的段落压暗、压饱和，副歌提亮，桥段换色温")
    # L4
    for i, p in enumerate(mp):
        if p['label'] not in ('chorus', 'drop'): continue
        prev = next((q for q in reversed(mp[:i]) if q['label'] not in ('chorus', 'drop')), None)
        if not prev: continue
        dy, dc = M[p['id']]['Y'] - M[prev['id']]['Y'], M[p['id']]['C'] - M[prev['id']]['C']
        ok = dy >= CH_Y or dc >= CH_C
        rep.append(f"- L4 {name(p)} 比 {name(prev)}：亮度 {dy:+.2f}、饱和 {dc:+.3f} → {'放开了' if ok else '没放开'}")
        if not ok: fail('L4', p['id'], f"{name(p)} 比前面的 {name(prev)} 亮度只高 {dy:+.2f}（要 ≥ {CH_Y}）、饱和只高 {dc:+.3f}（要 ≥ {CH_C}）：副歌要放开——提曝光、提饱和，或者把前一段压下去")
    # L5
    for i, p in enumerate(mp):
        if p['label'] != 'bridge' or i == 0: continue
        q = mp[i - 1]; a, b = M[p['id']], M[q['id']]
        dy, dw, dc = abs(a['Y'] - b['Y']), abs(a['W'] - b['W']), abs(a['C'] - b['C'])
        ok = dy >= BR_Y or dw >= BR_W or dc >= BR_C
        rep.append(f"- L5 {name(p)} 对 {name(q)}：亮度差 {dy:.2f}、冷暖差 {dw:.3f}、饱和差 {dc:.3f} → {'有反差' if ok else '没反差'}")
        if not ok: fail('L5', p['id'], f"{name(p)} 和前面的 {name(q)} 色调几乎一样（亮度差 {dy:.2f} / 冷暖差 {dw:.3f} / 饱和差 {dc:.3f}，要有一项 ≥ {BR_Y} / {BR_W} / {BR_C}）：桥段换个色调——冷下来、暗下来、去饱和或者换成另一种颜色")
    # L6
    for p in mp:
        m = M[p['id']]; bad = []
        if m['Y'] < DARK_Y: bad.append(f"平均亮度 {m['Y']:.2f} < {DARK_Y}")
        if m['P95'] < DARK_P95: bad.append(f"最亮 5% 的像素只有 {m['P95']:.2f} < {DARK_P95}（主体发闷，暗场景也要给角色留一道亮：轮廓光、灯、窗）")
        if m['CLIP'] > CLIP: bad.append(f"过曝像素 {m['CLIP']:.0%} > {CLIP:.0%}")
        if bad: fail('L6', p['id'], f"{p['id']} {name(p)}：" + '；'.join(bad))
elif not VID: rep.append('- 没给成片：L3–L6 不量')

ok = not fails
out = [f"# 调色关（grade check）\n\nmode: **{'safe（有 FAIL 就拦）' if MODE != 'free' else 'free（只报告）'}**\n"]
if rows: out += ['## 每段的色调（中位数；亮度 0–1、饱和 = 每像素 max−min、冷暖 = R−B，正数偏暖）', '', '| 段 | 段落 | 时间 | 亮度 | 最亮5% | 饱和 | 冷暖 |', '|---|---|---|---|---|---|---|'] + rows + ['']
out += ['## 明细', ''] + rep + ['', '## 关', ''] + ([f'- {f}' for f in fails] or ['- L1–L6 全部通过']) + ['', f"**{'PASS' if ok else 'FAIL'}**"]
os.makedirs(os.path.join(ROOT, 'out'), exist_ok=True)
open(os.path.join(ROOT, 'out/grade_check.md'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
print('\n'.join(out[-(len(fails) + 3):])); print('-> out/grade_check.md')
sys.exit(1 if fails and MODE != 'free' else 0)

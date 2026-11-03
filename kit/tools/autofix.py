#!/usr/bin/env python3
"""计划层自动修（三档制「自动修」档的 --fix 实现）。在项目根目录运行：python tools/autofix.py [--json]
只改数值不改剧本：不加动作、不换转场种类、不增删场景。人工改过的不覆盖（条目带 "_auto" 的才是机器改的，重复跑不重复修）。
改之前 plan.json 整份备份成 plan.bak.json；每条修改写进 out/fixes.json（report.py 汇总进报告）。

  V7 表情卡拍    emotes f0 吸附到 ±3 帧内最近拍点
  D1 舞句在拍上  tracks 里 dance 条目起点吸附到 ±1 帧内拍点
  T3 转场在拍上  cuts c 吸附到 ±2 帧内拍点/小节线/重音
  T4 转场长度    cuts len 夹到 [2 帧, 1 小节]（kind cut 允许 0）
  C1 场景表完整  首场景对齐 start、末场景对齐 end、相邻重叠/留空并拢、零长场景删掉
  C4 边界有转场  场景边界吸附到 ±6 帧内最近的转场/交接关键帧（前一个场景的 f1 跟着动）
  occlude→allow  旧 occlude 条目迁移：out/voxel.json 里这段时间没有 STUCK 的直接删（引擎自动合法），其余转成 plan.allow
  G4 计划动作    跑 tools/make_actions.py 按 tracks 重新生成 ACTIONS.json
V1/V2/V3/V5 的自动修在引擎里（relay.js 渲染时校正、换好帧），不在计划层。"""
import json, os, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')

JSON_ONLY = '--json' in sys.argv
FPS = 24
plan = json.load(open('plan.json', encoding='utf-8'))
START = plan['start']
TL = json.load(open('data/audio.timeline.json', encoding='utf-8'))
spb = (plan.get('tempo') or {}).get('spb') or TL.get('seconds_per_beat') or 0.5
bt = lambda t: round(t * FPS) + START
beats = [bt(t) for t in TL.get('beat_times', [])]
grid = sorted({*beats, *[bt(t) for t in TL.get('bar_times', [])], *[bt(h['time']) for h in TL.get('hits', [])]})
BAR = max(2, round(spb * 4 * FPS))
fixes = []

def nearest(f, pool, tol):
    g = min(pool, key=lambda x: abs(x - f)) if pool else None
    return g if g is not None and abs(g - f) <= tol else None

def fix(rule, where, detail):
    fixes.append({'rule': rule, 'where': where, 'detail': detail})

# ---------- V7 表情卡拍 ----------
for e in plan.get('emotes') or []:
    if e.get('_auto'): continue
    g = nearest(e['f0'], beats, 3)
    if g is not None and g != e['f0']:
        fix('V7', f"{e.get('who')} {e.get('g')}", f"f0 {e['f0']} → {g}（吸附到拍点）"); e['f0'] = g; e['_auto'] = True

# ---------- D1 舞句在拍上 ----------
for who, tr in (plan.get('tracks') or {}).items():
    for e in tr:
        if e[0] != 'dance' or not beats: continue
        g = min(beats, key=lambda x: abs(x - e[2]))
        if abs(g - e[2]) >= 2:
            fix('D1', f'{who} {e[1]}', f'起点 {e[2]} → {g}（吸附到拍点）'); e[2] = g

# ---------- T3 / T4 转场 ----------
# 正好落在场景边界上的转场不吸拍：转场 shader 两面按 c−1 / c 取景，挪离边界两面就成同一个场景（camplan 起草的都在边界上）。
# 要对拍就挪场景表的边界，T3 只警告
SCENE_EDGES = {s['f0'] for s in (plan.get('scenes') or [])} - {START}
for c in plan.get('cuts') or []:
    if not c.get('_auto') and c['c'] not in SCENE_EDGES:
        g = nearest(c['c'], grid, 2)
        if g is not None and g != c['c']:
            fix('T3', f"c{c['c']} {c.get('mode', '')}", f"关键帧 {c['c']} → {g}（吸附到拍/小节/重音）"); c['c'] = g; c['_auto'] = True
    lo = 0 if c.get('kind') == 'cut' else 2
    if c.get('len') is not None and not (lo <= c['len'] <= BAR):
        nl = min(max(c['len'], lo), BAR)
        fix('T4', f"c{c['c']}", f"len {c['len']} → {nl}（夹回 [{lo}, {BAR}]）"); c['len'] = nl; c['_auto'] = True

# ---------- C1 场景表完整 ----------
sc = sorted(plan.get('scenes') or [], key=lambda s: s['f0'])
if sc:
    if sc[0]['f0'] != START:
        fix('C1', sc[0]['id'], f"f0 {sc[0]['f0']} → {START}（对齐 start）"); sc[0]['f0'] = START; sc[0]['_auto'] = True
    if sc[-1]['f1'] != plan['end']:
        fix('C1', sc[-1]['id'], f"f1 {sc[-1]['f1']} → {plan['end']}（对齐 end）"); sc[-1]['f1'] = plan['end']; sc[-1]['_auto'] = True
    for a, b in zip(sc, sc[1:]):
        if b['f0'] != a['f1']:
            act = '重叠' if b['f0'] < a['f1'] else '留空'
            fix('C1', b['id'], f"f0 {b['f0']} → {a['f1']}（和 {a['id']} 之间{act}，并拢）"); b['f0'] = a['f1']; b['_auto'] = True
    plan['scenes'] = [s for s in sc if s['f1'] > s['f0']]     # 并拢后零长的场景删掉

# ---------- C4 边界有转场 ----------
keys = [c['c'] for c in plan.get('cuts') or []] + [c['key'] for c in plan.get('incamera') or []]
keys += [h[k] for h in plan.get('handoffs') or [] for k in ('f0', 'f1', 'key') if k in h]
sc = plan.get('scenes') or []
for a, b in zip(sc, sc[1:]):
    if b.get('_auto_c4'): continue
    g = nearest(b['f0'], keys, 6)
    if g is not None and g != b['f0']:
        fix('C4', f"{a['id']}→{b['id']}", f"边界 {b['f0']} → {g}（吸附到最近转场/交接关键帧）")
        a['f1'] = g; b['f0'] = g; b['_auto_c4'] = True
plan['scenes'] = [s for s in sc if s['f1'] > s['f0']]

# ---------- occlude → allow ----------
old = plan.get('occlude')
if old:
    stuck_w = set()
    vp = 'out/voxel.json'
    if os.path.exists(vp):
        try:
            for fr in json.load(open(vp, encoding='utf-8')).get('frames', []):
                for s in fr.get('stuck', []): stuck_w.add((s.get('who'), fr['f']))
        except Exception: pass
    allow = plan.setdefault('allow', [])
    probed = os.path.exists(vp)
    if not probed: fix('allow', 'occlude', '没有 out/voxel.json（没跑过探针），保守转成 allow，人工确认')
    for o in old:
        who, f0, f1 = o.get('who'), o.get('f0'), o.get('f1')
        hit = (not probed) or any(w == who and f0 <= f <= f1 for w, f in stuck_w)
        if hit:
            allow.append({'rule': 'collide', 'who': who, 'f0': f0, 'f1': f1, 'by': o.get('by') or '?',
                          'why': o.get('why') or ('（从 occlude 迁移；没有探针数据，人工确认）' if not probed else '（从 occlude 迁移；引擎判不了，人工确认）'), '_auto': True})
            fix('allow', str(who), f'occlude {f0}–{f1}' + ('没有探针数据' if not probed else '有对应 STUCK') + '，转成 allow（人工确认 why）')
        else:
            fix('allow', str(who), f'occlude {f0}–{f1} 没有对应 STUCK（碰撞没冲突），删掉')
    plan.pop('occlude')

# ---------- 写回 ----------
if fixes:
    shutil.copy('plan.json', 'plan.bak.json')
    json.dump(plan, open('plan.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
if plan.get('tracks') is not None and os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'make_actions.py')):
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'make_actions.py')],
                       cwd=os.getcwd(), capture_output=True, text=True)
    if r.returncode == 0: fixes.append({'rule': 'G4', 'where': 'ACTIONS.json', 'detail': '按 tracks 重新生成（make_actions）'})
os.makedirs('out', exist_ok=True)
json.dump({'n': len(fixes), 'fixes': fixes}, open('out/fixes.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
if not JSON_ONLY:
    for f in fixes: print(f"[{f['rule']}] {f['where']}：{f['detail']}")
    print(f'{len(fixes)} 处自动修' + ('（plan.json 已改，旧的在 plan.bak.json）' if fixes else '（没什么可修的）') + ' -> out/fixes.json')

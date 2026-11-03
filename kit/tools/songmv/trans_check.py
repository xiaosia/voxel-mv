#!/usr/bin/env python3
"""Transitions: the page declares them (window.TRANSITIONS), this script checks the table and verifies it against the film.
Usage: python3 trans_check.py <project_dir> [video=out/mv.mp4] [--mode safe|free] [--json]
Reads out/page_meta.json (render.sh writes it), data/lines.json, data/audio.timeline.json, and the video if it exists
(without a video only the table checks run: T2-T5; T1 waits for render.sh video). Writes out/trans_check.md + out/trans_check.json.
Mode: --mode, else the first word of <project>/MODE. Only affects wording now: 必过 gates block in both modes.

window.TRANSITIONS = [{ from: 'S03', to: 'S04', t0: 6.69, t1: 7.29, key: 7.036, kind: 'iris', note: '...' }, ...]
  key  = the moment the picture changes (the frame the eye reads as "new scene"); t0..t1 = the whole transition.
  kind = how it moves, one of KINDS below (any art style can draw any of them). A big change inside one shot
         (a drop that turns night into day, a one-take that travels to a new place) is an entry with kind 'incamera'.
Gates:
  T1  every entry visibly changes the picture at its key; no undeclared scene change anywhere else (a one-frame jump
      after which >= 40 % of the picture stays different: a cut, a new panel taking half the page, the whole sky
      swapping colour. Flashes that fade back, blinks, sparks and small pop-ins do not count) 【必过，成片再判】
  T2  >= 4 kinds; no kind > 40 %; never the same kind 3 times in a row; 'cut' <= 30 %   ('incamera' not counted) 【警告】
  T3  >= 80 % of keys within 1 frame of a beat, a bar line or a hit 【自动修：吸附到最近拍点】
  T4  2 frames <= t1 - t0 <= 1 bar ('cut' and 'incamera' may be 0); a transition spans at most one lyric-line start 【自动修：长度夹回范围】
  T5  every drop has an entry whose key is within 1 frame of it and it is a heavy kind (light = dissolve/dip/
      leak/iris/slide: a 溶解 on the drop gets smeared away, a flash or a cut reads) 【必过】
  T6  no heavy kind twice in a row (two adjacent entries, same kind, both heavy = monotonous) 【警告】
  T7  dip (落黑/落白) only in the intro / bridge / outro; a dip in the middle of the vocals warns 【警告】
  T8  directional sweeps (whip / split / occlude / leak) hand the eye to the next shot: the following shot's
      camera shouldn't pan against the sweep (needs out/voxel.json, skipped without it) 【警告】"""
import json, os, subprocess, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import checks_common as CC
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')

KINDS = {'cut': '硬切', 'flash': '闪白/闪黑', 'dissolve': '溶解', 'wipe': '擦除', 'iris': '圈入圈出', 'slide': '推拉滑入',
         'whip': '甩镜', 'through': '穿过物体推进', 'match': '形状匹配', 'page': '翻页', 'rotate': '旋转',
         'dip': '落色（落黑/落白）', 'leak': '光晕扫过', 'voxel': '体素化（光爆）', 'glitch': '故障',
         'incamera': '镜头内换景/一镜到底', 'other': '其他（note 里写清楚）'}
# 轻重：炸点上只有轻转场会被音乐的能量抹掉。新引擎的登记带 mv（引擎模式名），老登记只有 kind，两套都认
LIGHT_MV = {'dip', 'iris', 'leak', 'rows', 'split'}
LIGHT_KIND = {'dissolve', 'dip', 'leak', 'iris', 'slide'}   # slide 近似盖住 rows/split；拿不准的一律算重（不冤枉炸点）
FPS, TOL = 24, 1 / 24 + .01
args = sys.argv[1:]; mode = None
if '--mode' in args: i = args.index('--mode'); mode = args[i + 1]; del args[i:i + 2]
JSON_ONLY = '--json' in args
P = args[0] if args else '.'; V = args[1] if len(args) > 1 else os.path.join(P, 'out/mv.mp4')
if not mode:
    mf = os.path.join(P, 'MODE'); mode = (open(mf, encoding='utf-8').read().split() or ['safe'])[0] if os.path.exists(mf) else 'safe'
L = json.load(open(os.path.join(P, 'data/lines.json'), encoding='utf-8'))['lines']
TL = json.load(open(os.path.join(P, 'data/audio.timeline.json'), encoding='utf-8'))
beats, bars = np.array(TL['beat_times']), np.array(TL['bar_times'])
spb, bar = float(np.median(np.diff(beats))), float(np.median(np.diff(bars)))
grid = np.sort(np.concatenate([beats, bars, [h['time'] for h in TL.get('hits', [])]]))
drops = [d['time'] for d in TL.get('drops', [])]
meta_p = os.path.join(P, 'out/page_meta.json')
meta = json.load(open(meta_p, encoding='utf-8')) if os.path.exists(meta_p) else {}
TR = meta.get('TRANSITIONS')
out, RULES = ['# transition check\n', f'mode: **{mode}**（只影响措辞）\n'], []
if not TR:
    RULES.append({'rule': 'T1', 'name': '看得见、没有漏登记', 'ok': False, 'detail': '页面没有登记 window.TRANSITIONS（见 SKILL.md 页面契约）；一镜到底也要把换景登记成 kind "incamera"'})
    for r in RULES: r.setdefault('tier', CC.tier(r['rule']))
    out.append('**FAIL: the page declares no window.TRANSITIONS** (see SKILL.md 页面契约). A one-take film still declares '
               'its scene changes as kind "incamera".')
    p = CC.dump_json('trans_check', RULES, os.path.join(P, 'out'))
    open(os.path.join(P, 'out/trans_check.md'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    if not JSON_ONLY: print(out[-1], f'-> out/trans_check.md, {p}')
    sys.exit(CC.exit_code(RULES))
TR = sorted(TR, key=lambda r: r['key'])
# 老项目登记没有 mv 字段：从 plan.json 的 cuts 把模式名找回来（voxel 光爆在旧版登记成 kind "dissolve"，不算轻转场）
try:
    with open(os.path.join(P, 'plan.json'), encoding='utf-8') as fh: PLANJ = json.load(fh)
except FileNotFoundError: PLANJ = {}
_mv_at = {round((k['c'] - PLANJ.get('start', 0)) / FPS, 3): k['mode'] for k in PLANJ.get('cuts', []) if k.get('mode')}
def weight(r):
    mv = r.get('mv') or _mv_at.get(round(float(r['key']), 3))
    if mv: return 'light' if mv in LIGHT_MV else 'heavy'
    return 'light' if r.get('kind') in LIGHT_KIND else 'heavy'

# ---------- video ----------
fr = None
if os.path.exists(V):
    raw = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', V, '-vf', f'fps={FPS},scale=160:90,format=gray', '-f', 'rawvideo', '-'],
                         capture_output=True, check=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 90, 160).astype(np.float32)
    N = len(fr); d = np.concatenate([[0], np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))])
    fi = lambda t: int(np.clip(round(t * FPS), 0, N - 1))
    diff = lambda a, b: float(np.abs(fr[fi(a)] - fr[fi(b)]).mean())
    win = [(r['t0'] - 2 / FPS, r['t1'] + 2 / FPS) for r in TR]
    def calm_med(t):   # typical change per frame around t, outside every transition
        ii = [i for i in range(fi(t - 1.5), fi(t + 1.5)) if not any(a <= i / FPS <= b for a, b in win)]
        return float(np.median(d[ii])) if ii else float(np.median(d))

# ---------- per entry ----------
rows, bad = [], {k: [] for k in ('T1', 'T3', 'T4')}
for r in TR:
    kind, key, t0, t1 = r.get('kind', '?'), float(r['key']), float(r['t0']), float(r['t1'])
    on = float(np.abs(grid - key).min()) <= TOL
    if not on: bad['T3'].append(r)
    dur = t1 - t0; lines_in = [l for l in L[1:] if t0 + spb / 2 < l['t'] < t1 - spb / 2]
    t4 = (dur <= bar + 1e-6) and (kind in ('cut', 'incamera') or dur >= 2 / FPS - 1e-6) and len(lines_in) <= 1 and t0 <= key <= t1
    if not t4: bad['T4'].append(r)
    vis = '–'
    if fr is not None:
        pk = float(d[fi(key - 2 / FPS):fi(key + 2 / FPS) + 1].max()); ratio = pk / max(calm_med(key), .5)
        span = max(t1 - t0, 2 / FPS) + 4 / FPS; change = diff(t0 - 2 / FPS, t1 + 2 / FPS)
        # the same before/after difference measured over equally long stretches nearby, outside every transition
        ref = [diff(x, x + span) for x in np.arange(key - 2.5, key + 2.5, 1 / FPS)
               if 0 <= x and x + span < N / FPS and not any(a < x + span and x < b for a, b in win)]
        cr = change / max(np.median(ref), 3) if ref else 9
        ok = ratio >= 2.5 or cr >= 1.8
        vis = f'{"ok" if ok else "NOT SEEN"} (peak ×{ratio:.1f}, before/after ×{cr:.1f})'
        if not ok: bad['T1'].append(r)
    rows.append(f"| {r.get('from', '')}→{r.get('to', '')} | {key:.3f} | {kind} | {dur:.2f}s | {'yes' if on else 'NO'} | "
                f"{'ok' if t4 else 'NO'} | {vis} | {str(r.get('note', ''))[:30]} |")

# undeclared scene changes: a one-frame jump after which a large part of the picture stays changed
undeclared = []
if fr is not None:
    for i in range(2, N - 8):
        if d[i] < 22 or any(a <= i / FPS <= b for a, b in win): continue
        loc = np.median(d[max(0, i - 12):i + 12])
        if d[i] < 3 * max(loc, 1): continue
        stay = float((np.abs(fr[i + 6] - fr[i - 1]) > 25).mean())   # share of the picture still different 6 frames later
        if stay >= .4 and (not undeclared or i / FPS - undeclared[-1] > .5): undeclared.append(i / FPS)
    if undeclared: bad['T1'].append('undeclared')

# ---------- film-level ----------
kinds = [r.get('kind', '?') for r in TR if r.get('kind') != 'incamera']
unknown = sorted({r.get('kind') for r in TR} - set(KINDS))
cnt = {k: kinds.count(k) for k in set(kinds)}; n = len(kinds)
run = max((len(list(g)) for _, g in __import__('itertools').groupby(kinds)), default=0)
need = min(4, n)
t2 = n == 0 or (len(cnt) >= need and max(cnt.values()) <= max(.4 * n, 1) and run < 3 and cnt.get('cut', 0) <= .3 * n and not unknown)
t5_bad = []
for x in drops:
    cov = [r for r in TR if abs(float(r['key']) - x) <= TOL]
    if not cov: t5_bad.append((x, '没登记'))
    elif all(weight(r) == 'light' for r in cov):
        t5_bad.append((x, '只有轻转场(' + '/'.join(sorted({r.get('kind', '?') for r in cov})) + ')'))
hv = [r for r in TR if weight(r) == 'heavy']
t6_runs = []
for k, g in __import__('itertools').groupby(r.get('kind', '?') for r in hv):
    n2 = len(list(g))
    if n2 >= 2: t6_runs.append((k, n2))
# 落色只许在前奏/桥段/尾奏（含间奏）：有段落表时按段落判，落在这几种段落里的不算曲中；没有段落表退回「第二句词到最后一句词之间」
_st_p = os.path.join(P, 'data/structure.json')
PARTS = []
if os.path.exists(_st_p):
    with open(_st_p, encoding='utf-8') as fh: PARTS = json.load(fh).get('parts', [])
CALM = {'intro', 'bridge', 'outro', 'interlude'}
def in_calm(t):
    return any(p2.get('label') in CALM and float(p2['t0']) <= t < float(p2['t1']) for p2 in PARTS)
t7_bad = [r for r in TR if r.get('kind') == 'dip' and len(L) > 1 and float(L[1]['t']) <= float(r['key']) <= float(L[-1]['t'])
          and not in_calm(float(r['key']))]
vox_p = os.path.join(P, 'out', 'voxel.json')
vox = None
if os.path.exists(vox_p):
    with open(vox_p, encoding='utf-8') as fh: vox = json.load(fh)
t8_bad, t8_note = [], ''
if vox is None:
    t8_note = '（没有 out/voxel.json 运镜档，跳过）'
else:
    FR = [f2 for f2 in vox.get('frames', []) if f2.get('cam')]
    # 探针帧号是绝对帧，转场 key 是从本段 start 起的秒数（接力第 2 段起 start ≠ 0）：统一换成段内秒数再比
    START8 = (vox.get('PLAN') or PLANJ).get('start', 0)
    FR_T = [((f2['f'] - START8) / FPS, f2['cam']['target'][0]) for f2 in FR]
    eye = lambda mv, r: 1 if mv == 'whip' else (1 if (r.get('dir') or 1) >= 0 else -1)
    for r in TR:
        mv = r.get('mv') or _mv_at.get(round(float(r['key']), 3))
        if mv not in ('whip', 'split', 'occlude', 'leak') or not FR: continue
        key = float(r['key'])
        cx = lambda t: min(FR_T, key=lambda q: abs(q[0] - t))[1]
        x0, x1 = cx(key + 2 / FPS), cx(key + 0.5)
        if abs(x1 - x0) < 0.05: continue            # 下一镜头基本没横移，不判
        if (x1 - x0) * eye(mv, r) < 0: t8_bad.append(r)  # 扫向把眼睛带往一边，下一镜头却往反位移
gate = {
    'T1': (fr is None) or not bad['T1'],
    'T2': t2,
    'T3': len(bad['T3']) <= .2 * len(TR),
    'T4': not bad['T4'],
    'T5': not t5_bad,
    'T6': not t6_runs,
    'T7': not t7_bad,
    'T8': vox is None or not t8_bad,   # 没有运镜档就跳过（不判 FAIL）
}
out.append(f'{len(TR)} entries: ' + ', '.join(f'{k}×{v}' for k, v in sorted(cnt.items(), key=lambda x: -x[1])) +
           (f', incamera×{len(TR) - n}' if len(TR) > n else '') + '\n')
out.append('| from→to | key | kind | length | on beat/bar/hit | length ok | seen in the film | note |\n|---|---|---|---|---|---|---|---|')
out += rows
out.append('\n## gates\n')
out.append(f"- T1 visible & complete: " + ('waiting for out/mv.mp4 (render.sh video)' if fr is None else
           ('PASS' if gate['T1'] else 'FAIL') + (f" — not seen at: {', '.join(str(r['key']) for r in bad['T1'] if r != 'undeclared')}" if any(r != 'undeclared' for r in bad['T1']) else '') +
           (f" — undeclared scene change at: {', '.join(f'{x:.2f}s' for x in undeclared)}" if undeclared else '')))
out.append(f"- T2 variety: {'PASS' if gate['T2'] else 'FAIL'} ({len(cnt)} kinds, largest {max(cnt.values()) if cnt else 0}/{n}, longest run {run}, cut {cnt.get('cut', 0)}/{n}" +
           (f", unknown kinds: {unknown}" if unknown else '') + ')')
out.append(f"- T3 on the beat: {'PASS' if gate['T3'] else 'FAIL'} ({len(TR) - len(bad['T3'])}/{len(TR)})" +
           (f" — off: {', '.join(str(r['key']) for r in bad['T3'])}" if bad['T3'] else ''))
out.append(f"- T4 length: {'PASS' if gate['T4'] else 'FAIL'}" + (f" — {', '.join(str(r['key']) for r in bad['T4'])}" if bad['T4'] else ''))
out.append(f"- T5 drops (heavy): {'PASS' if gate['T5'] else 'FAIL'}" +
           (f" — {'; '.join(f'{x:.3f} {w}' for x, w in t5_bad)}" if t5_bad else ''))
out.append(f"- T6 heavy run: {'PASS' if gate['T6'] else 'FAIL'}" +
           (f" — same heavy kind twice in a row: {', '.join(f'{k}×{n2}' for k, n2 in t6_runs)}" if t6_runs else ''))
out.append(f"- T7 dip placement: {'PASS' if gate['T7'] else 'FAIL'}" +
           (f" — dip in the middle of the vocals at {', '.join(str(r['key']) for r in t7_bad)}" if t7_bad else ''))
out.append(f"- T8 sweep direction: {'PASS' if gate['T8'] else 'FAIL'}{t8_note}" +
           (f" — next shot pans against the sweep at {', '.join(str(r['key']) for r in t8_bad)}" if t8_bad else ''))
RULES = [
    {'rule': 'T1', 'name': '看得见、没有漏登记', 'ok': gate['T1'],
     'detail': '没给成片，等出片后再判（不拦）' if fr is None else
               (('；'.join([f"关键帧上看不到变化：{', '.join(str(r['key']) for r in bad['T1'] if r != 'undeclared')}" if any(r != 'undeclared' for r in bad['T1']) else '',
                           f"漏登记的换景 @{', '.join(f'{x:.2f}s' for x in undeclared)}" if undeclared else '']) or '每条都看得见，没有漏登记'))},
    {'rule': 'T2', 'name': '种类够多', 'ok': gate['T2'],
     'detail': f'{len(cnt)} 种（要 ≥ {need}），最大占比 {max(cnt.values()) if cnt else 0}/{n}（≤ 40%），最长连用 {run}（< 3），cut {cnt.get("cut", 0)}/{n}（≤ 30%）' + (f'；未知 kind：{unknown}' if unknown else '')},
    {'rule': 'T3', 'name': '关键帧在拍上', 'ok': gate['T3'], 'detail': f'{len(TR) - len(bad["T3"])}/{len(TR)} 在拍/小节/重音 ±1 帧内（要 ≥ 80%）' + (f'；不在：{", ".join(str(r["key"]) for r in bad["T3"][:8])}' if bad['T3'] else '')},
    {'rule': 'T4', 'name': '长度合理', 'ok': gate['T4'], 'detail': '长度都在 2 帧–1 小节（cut/incamera 可为 0），至多跨一句词的起点' + (f'；不对：{", ".join(str(r["key"]) for r in bad["T4"][:8])}' if bad['T4'] else '')},
    {'rule': 'T5', 'name': '炸点有重转场', 'ok': gate['T5'],
     'detail': '每个炸点 key ±1 帧内有登记，且是重转场（轻=溶解/落色/光晕/圈入/滑条，炸点上会被音乐能量抹掉；闪白、硬切都算重）' +
               (f'；不对：{"; ".join(f"{x:.3f} {w}" for x, w in t5_bad[:6])}' if t5_bad else '')},
    {'rule': 'T6', 'name': '重的别连用', 'ok': gate['T6'],
     'detail': '相邻两条重转场不同 kind（同一种重转场连用两次就单调）' + (f'；连用：{", ".join(f"{k}×{n2}" for k, n2 in t6_runs[:6])}' if t6_runs else '')},
    {'rule': 'T7', 'name': '落色只在头尾', 'ok': gate['T7'],
     'detail': 'dip（落黑/落白）放前奏/尾奏/桥段；人声中间的落色压不住场面，改重转场或挪位置' +
               (f'；曲中 dip @{", ".join(str(r["key"]) for r in t7_bad[:6])}' if t7_bad else '')},
    {'rule': 'T8', 'name': '方向接得上', 'ok': gate['T8'],
     'detail': '方向性转场（甩镜/分屏/遮挡/光晕）的扫向和下一镜头的横移要同向' + t8_note +
               (f'；逆着扫向：{", ".join(str(r["key"]) for r in t8_bad[:6])}' if t8_bad else '')},
]
for r in RULES: r.setdefault('tier', CC.tier(r['rule']))
tiers = {'must': 0, 'auto': 0, 'warn': 0}
for r in RULES:
    if not r['ok']: tiers[r['tier']] += 1
out += ['', '## rule table', '', '| rule | 档 | 结果 | 说明 |', '|---|---|---|---|']
out += ['| %s %s | %s | %s | %s |' % (r['rule'], r['name'], CC.CN[r['tier']], 'PASS' if r['ok'] else '**FAIL**', r['detail'][:150]) for r in RULES]
out.append('\nKinds: ' + ', '.join(f'{k} = {v}' for k, v in KINDS.items()))
out.append(f'\n**{"PASS" if tiers["must"] == 0 else "FAIL"}**（没过：必过 {tiers["must"]}，自动修 {tiers["auto"]}，警告 {tiers["warn"]}）' +
           ('（T1 还没判：没给成片）' if fr is None else ''))
p = CC.dump_json('trans_check', RULES, os.path.join(P, 'out'))
open(os.path.join(P, 'out/trans_check.md'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
if not JSON_ONLY: print(out[-1], f'-> out/trans_check.md, {p}')
sys.exit(CC.exit_code(RULES))

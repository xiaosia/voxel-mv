#!/usr/bin/env python3
"""Do the characters actually move, and with the music? Reads out/probe.json (from render.sh act), data/lines.json,
data/audio.timeline.json and, if present, ACTIONS.json. Writes out/act_check.md, out/act_check.json and out/act_check.png.
Usage: python3 act_check.py <project_dir> [--mode safe|free] [--json]
Mode: --mode, else the first word of <project>/MODE. Only affects wording now: 必过 gates block in both modes.

Only body motion counts: every key point (head, hands, feet) is taken relative to the character's own root and divided
by its height h, so camera moves, zooms and whole-body slides do not count. Art style plays no part.
A character counts as on screen when its root is inside the frame and h >= 12 % of the frame height
(smaller figures are background and are listed but not gated).

  still beat     a beat in which no key point moves more than 4 % of h
  clear action   a key point moves >= 15 % of h within 1 s (counted again only after the previous one)
  sync           how much the body's speed locks to the beat grid: 0 = unrelated, 1 = every movement at the same
                 beat phase. Per key point |sum v*exp(2*pi*i*beatpos/period)| / sum v, period 1 or 2 beats (the
                 better one), per line, averaged over the lines by time on screen. Hitting on beats and landing on
                 beats both count. Rough values: pop on the beat 0.8, eased move beat to beat 0.6, eased move every
                 2 beats 0.6, smooth walk with steps on the beats 0.33, idle sway / free sine motion under 0.15.
Gates, for each character while on screen:
  G1  at least 1 clear action in every 2-bar window it is on screen for >= half of 【必过】
  G2  no more than 4 still beats in a row 【必过】
  G3  sync >= 0.25 over the film (and, advisory, per line) 【警告】
  G4  ACTIONS.json exists, and each planned action shows a clear action of that character within 1 beat of its time
      【自动修：重跑 make_actions / 改 tracks 后复判】
ACTIONS.json: {"actions": [{"line": "L03", "who": "me", "beat": 27, "act": "挥手"}, ...],
               "holds":   [{"who": "you", "from": 50.4, "to": 53.5, "why": "最后一个画面停住看烟花"}]}
  "beat" = index into beat_times (or "t" in seconds); "who" = the id the page gives to mark().
  A hold is a stillness you chose: it excuses G1/G2 inside it. Each hold is cut to 8 beats, and holds may cover at
  most 15 % of a character's time on screen (the rest of the hold still counts)."""
import json, os, sys, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import checks_common as CC
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')

args = sys.argv[1:]; mode = None
if '--mode' in args: i = args.index('--mode'); mode = args[i + 1]; del args[i:i + 2]
JSON_ONLY = '--json' in args
P = args[0] if args else '.'
if not mode:
    mf = os.path.join(P, 'MODE'); mode = (open(mf, encoding='utf-8').read().split() or ['safe'])[0] if os.path.exists(mf) else 'safe'
MIN_H, STILL, ACT, ACT_WIN, MAX_STILL, SYNC_MIN = .12, .04, .15, 1.0, 4, .15
KEYS = ['head', 'handL', 'handR', 'footL', 'footR']

pr = json.load(open(os.path.join(P, 'out/probe.json'), encoding='utf-8')); FPS = pr['fps']; F = pr['frames']; N = len(F)
L = json.load(open(os.path.join(P, 'data/lines.json'), encoding='utf-8'))['lines']
TL = json.load(open(os.path.join(P, 'data/audio.timeline.json'), encoding='utf-8'))
beats, bars = np.array(TL['beat_times']), np.array(TL['bar_times'])
T = np.arange(N) / FPS

ids = sorted({c['id'] for f in F for c in f})
spb = float(np.median(np.diff(beats)))
plan, holds, plan_note = [], [], ''
ap = os.path.join(P, 'ACTIONS.json')
if os.path.exists(ap):
    try:
        j = json.load(open(ap, encoding='utf-8'))
        plan, holds = (j, []) if isinstance(j, list) else (j.get('actions', []), j.get('holds', []))
    except Exception as e: plan_note = f'ACTIONS.json could not be read: {e}'
else: plan_note = 'no ACTIONS.json'
def hold_mask(cid, vis):
    m, budget = np.zeros(N, bool), .15 * vis.sum()
    for h in holds:
        if h.get('who') not in (cid, '*', None): continue
        a = int(h['from'] * FPS); b = min(int(min(h['to'], h['from'] + 8 * spb) * FPS), N)
        for i in range(max(a, 0), b):
            if m.sum() >= budget: break
            m[i] = True
    return m
def track(cid):
    """per frame: pose (K,2) relative to root / h, visible flag, h"""
    pose = np.full((N, len(KEYS), 2), np.nan); vis = np.zeros(N, bool); hh = np.zeros(N); root = np.full((N, 2), np.nan)
    for i, f in enumerate(F):
        cs = [c for c in f if c['id'] == cid and c.get('root')]
        if not cs: continue
        c = max(cs, key=lambda c: c['h']); r = np.array(c['root']); h = c['h']
        hh[i] = h; root[i] = r
        vis[i] = -0.02 <= r[0] <= 1.02 and -0.02 <= r[1] <= 1.1 and h >= MIN_H
        for k, key in enumerate(KEYS):
            if c.get(key): pose[i, k] = (np.array(c[key]) - r) * [16 / 9, 1] / h   # x was in widths: make it square
    # a jump in size or place between two frames = a cut or a flip: break continuity there
    brk = np.zeros(N, bool)
    for i in range(1, N):
        if hh[i] and hh[i - 1]:
            if abs(hh[i] / hh[i - 1] - 1) > .25 or np.hypot(*(root[i] - root[i - 1])) > .15 or np.nanmax(np.abs(pose[i] - pose[i - 1]), initial=0) > .6: brk[i] = True
        else: brk[i] = True
    return pose, vis, hh, brk

def disp(a, b): return float(np.nanmax(np.hypot(*(a - b).T), initial=0))

BP = np.interp(T, beats, np.arange(len(beats)), left=np.nan, right=np.nan)
CTL = [(T - beats[0]) / (spb * f) for f in (.73, .87, 1.17, 1.37)]
R = {}
for cid in ids:
    pose, vis, hh, brk = track(cid); hm = hold_mask(cid, vis)
    sp = np.zeros(N); sk = np.zeros((N, len(KEYS)))           # speed in h per second: fastest key point / each key point
    for i in range(1, N):
        if vis[i] and vis[i - 1] and not brk[i]:
            sk[i] = np.nan_to_num(np.hypot(*(pose[i] - pose[i - 1]).T)) * FPS; sp[i] = sk[i].max()
    # clear actions
    ev, last, w = [], 0, int(ACT_WIN * FPS)
    for i in range(N):
        if not vis[i] or brk[i]: last = max(last, i); continue
        lo = max(last, i - w)
        for j in range(lo, i):
            if vis[j] and disp(pose[i], pose[j]) >= ACT: ev.append(T[i]); last = i; break
    ev = np.array(ev)
    # still beats (only beats fully on screen and unbroken)
    sb = []
    for k in range(len(beats) - 1):
        a, b = int(round(beats[k] * FPS)), int(round(beats[k + 1] * FPS))
        if b > N or a >= b: sb.append(None); continue
        if not vis[a:b].all() or brk[a + 1:b].any(): sb.append(None); continue
        sb.append(None if hm[a:b].mean() > .5 else max(disp(pose[i], pose[a]) for i in range(a, b)) < STILL)
    runs, cur, worst = [], 0, (0, 0)
    for k, s in enumerate(sb):
        if s: cur += 1; worst = max(worst, (cur, k - cur + 1))
        else: cur = 0
    # sync
    def sync1(m, bp, sk=sk):
        # per key point (so a walk, where one foot is always moving, still shows each foot's beat), at the beat
        # period and at the 2-beat period (a move every 2 beats peaks between its two landings); the better of the two
        m = m & ~np.isnan(bp); v = sk[m]
        if v.sum() < 1e-6 or m.sum() < 4 * FPS * .44: return None
        return max(float(np.abs((v * np.exp(2j * math.pi * bp[m] / per)[:, None]).sum(0)).sum() / v.sum()) for per in (1, 2))
    def sync(m, sync1=sync1):
        # line by line (different shots may lock to different beat phases), averaged by time on screen, minus the same
        # number measured against wrong beat grids (tempo x0.73 .. x1.37): what is left is locking to THIS song's beat
        vals = []
        for l in L:
            ml = m & (T >= l['t']) & (T < l['end'])
            r = sync1(ml, BP)
            if r is None: continue
            ctl = [sync1(ml, g) for g in CTL]; vals.append((r - float(np.median([c for c in ctl if c is not None] or [0])), ml.sum()))
        return sum(s * w for s, w in vals) / sum(w for s, w in vals) if vals else None
    # 2-bar windows
    wins = []
    for k in range(0, len(bars) - 2, 2):
        a, b = bars[k], bars[k + 2]; m = (T >= a) & (T < b)
        if vis[m].mean() >= .5 and hm[m].mean() < .5: wins.append((a, b, int(((ev >= a) & (ev < b)).sum())))
    R[cid] = dict(vis=vis, sp=sp, ev=ev, sb=sb, worst=worst, sync=sync, wins=wins, hh=hh, onscreen=float(vis.sum() / FPS))

# ---------- planned actions ----------
plan_rows, plan_fail = [], []
for a in plan:
    t = a['t'] if 't' in a else (beats[int(a['beat'])] if 'beat' in a and 0 <= int(a['beat']) < len(beats) else None)
    who = a.get('who'); ok = False; why = 'MISSING (no clear move of this character within a beat of it)'
    if t is None: why = 'MISSING (bad beat / t)'
    elif who not in R: why = f'MISSING (no character "{who}" was marked)'
    else:
        e = R[who]['ev']; ok = bool(((e >= t - spb) & (e <= t + spb * 1.5)).any())
        i = min(int(t * FPS), N - 1)
        if not ok and not R[who]['vis'][max(0, i - int(spb * FPS)):i + int(spb * FPS) + 1].any(): why = 'MISSING (not on screen then, or smaller than 12 % of the frame height)'
    row = (a.get('line', ''), who, a.get('beat', ''), f'{t:.2f}' if t is not None else '?', a.get('act', ''), 'ok' if ok else why)
    plan_rows.append(row)
    if not ok: plan_fail.append(row)

# ---------- report ----------
out, RULES = ['# act check\n', f'mode: **{mode}**（只影响措辞）  ·  characters: {", ".join(ids) or "none"}\n'], []
if not ids: out.append('No character was marked in any frame. If the film has characters, call mark() where they are drawn (SKILL.md).\n')
out.append('## per line\n\n| line | text | ' + ' | '.join(f'{c}: on / actions / longest still / sync' for c in ids) + ' |\n|---|---|' + '---|' * len(ids))
for l in L:
    cells = []
    for c in ids:
        r = R[c]; m = (T >= l['t']) & (T < l['end']); on = r['vis'][m].mean() if m.any() else 0
        if on < .05: cells.append('–'); continue
        na = int(((r['ev'] >= l['t']) & (r['ev'] < l['end'])).sum())
        ks = [k for k in range(len(r['sb'])) if l['t'] <= beats[k] < l['end']]
        run = cur = 0
        for k in ks:
            cur = cur + 1 if r['sb'][k] else 0; run = max(run, cur)
        s = r['sync'](m & r['vis'])
        cells.append(f'{on:.0%} / {na} / {run} / ' + ('–' if s is None else f'{s:.2f}' + ('' if s >= SYNC_MIN else ' ⚠')))
    out.append(f"| {l['id']} | {l['text'][:14]} | " + ' | '.join(cells) + ' |')
out.append('\n## gates\n')
for c in ids:
    r = R[c]
    if r['onscreen'] < 1: out.append(f'- {c}: on screen {r["onscreen"]:.1f} s (big enough to judge), not gated'); continue
    empty = [(a, b) for a, b, n in r['wins'] if n == 0]
    g1 = not empty
    out.append(f'- **{c}** on screen {r["onscreen"]:.1f} s, {len(r["ev"])} clear actions')
    out.append(f'  - G1 action every 2 bars: {"PASS" if g1 else "FAIL"} ({len(r["wins"]) - len(empty)}/{len(r["wins"])} windows)' +
               ('' if g1 else ' — no action in ' + ', '.join(f'{a:.1f}–{b:.1f}s' for a, b in empty)))
    n, k0 = r['worst']; g2 = n <= MAX_STILL
    out.append(f'  - G2 longest still: {n} beats' + (f' (from {beats[k0]:.1f}s)' if n else '') + f' {"PASS" if g2 else "FAIL"}')
    s = r['sync'](r['vis']); g3 = bool(s is None or s >= SYNC_MIN)
    out.append(f'  - G3 sync: {"–" if s is None else f"{s:.2f}"} {"PASS" if g3 else "FAIL"}')
    RULES.append({'rule': 'G1', 'name': f'{c} 每两小节有动作', 'ok': g1,
                  'detail': (f'{len(r["wins"]) - len(empty)}/{len(r["wins"])} 个两小节窗口有动作' + ('；空窗 ' + ', '.join(f'{a:.1f}–{b:.1f}s' for a, b in empty[:4]) if empty else '')) if r['wins'] else '没有在屏 ≥ 半程的两小节窗口'})
    RULES.append({'rule': 'G2', 'name': f'{c} 不长静止', 'ok': g2, 'detail': f'最长静止 {n} 拍（上限 {MAX_STILL}）' + (f'，从 {beats[k0]:.1f}s 起' if n else '')})
    RULES.append({'rule': 'G3', 'name': f'{c} 卡拍', 'ok': g3, 'detail': '量不出（动作太少）' if s is None else f'sync {s:.2f}（下限 {SYNC_MIN}）'})
if ids:
    if plan_note:
        out.append(f'- G4 action plan: FAIL ({plan_note})')
        RULES.append({'rule': 'G4', 'name': '计划动作兑现', 'ok': False, 'detail': plan_note})
    else:
        ok4 = not plan_fail
        out.append(f'- G4 action plan: {"PASS" if ok4 else "FAIL"} ({len(plan_rows) - len(plan_fail)}/{len(plan_rows)} planned actions seen)')
        RULES.append({'rule': 'G4', 'name': '计划动作兑现', 'ok': ok4, 'detail': f'{len(plan_rows) - len(plan_fail)}/{len(plan_rows)} 个计划动作在 ±1 拍内看到' + ('；缺的见下表' if plan_fail else '')})
    if plan_rows:
        out.append('\n| line | who | beat | t | action | seen |\n|---|---|---|---|---|---|')
        out += ['| ' + ' | '.join(map(str, r)) + ' |' for r in plan_rows]
out.append('\nRead with out/act_check.png: each character\'s body speed, beats as ticks, clear actions as dots, '
           'still beats in grey, 2-bar windows with no action in red.')
for r in RULES: r.setdefault('tier', CC.tier(r['rule']))
tiers = {'must': 0, 'auto': 0, 'warn': 0}
for r in RULES:
    if not r['ok']: tiers[r['tier']] += 1
out += ['', '## rule table', '', '| rule | 档 | 结果 | 说明 |', '|---|---|---|---|']
out += ['| %s %s | %s | %s | %s |' % (r['rule'], r['name'], CC.CN[r['tier']], 'PASS' if r['ok'] else '**FAIL**', r['detail'][:150]) for r in RULES]
out.append(f'\n**{"PASS" if tiers["must"] == 0 else "FAIL"}**（没过：必过 {tiers["must"]}，自动修 {tiers["auto"]}，警告 {tiers["warn"]}）')
open(os.path.join(P, 'out/act_check.md'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
pj = CC.dump_json('act_check', RULES, os.path.join(P, 'out'))

# ---------- plot ----------
ROW, PXS, LH = 15.0, 110, 90
rows = math.ceil(T[-1] / ROW) if N else 1
Wd, Hd = int(ROW * PXS) + 80, rows * (len(ids) * LH + 40) + 20
im = Image.new('RGB', (Wd, Hd), 'white'); d = ImageDraw.Draw(im)
try: fnt = ImageFont.truetype('DejaVuSans.ttf', 13)
except Exception: fnt = ImageFont.load_default()
cols = [(220, 40, 60), (40, 90, 220), (20, 150, 80), (200, 120, 0), (130, 50, 180)]
for rw in range(rows):
    t0 = rw * ROW; y0 = 20 + rw * (len(ids) * LH + 40); x = lambda t: 70 + (t - t0) * PXS
    for l in L:
        if t0 <= l['t'] < t0 + ROW: d.line([(x(l['t']), y0 - 14), (x(l['t']), y0 + len(ids) * LH)], fill=(150, 150, 150)); d.text((x(l['t']) + 3, y0 - 16), l['id'], fill=(80, 80, 80), font=fnt)
    for ci, c in enumerate(ids):
        r = R[c]; yb = y0 + (ci + 1) * LH - 8; col = cols[ci % len(cols)]
        d.text((4, yb - LH // 2), c, fill=col, font=fnt)
        for a, b, n in r['wins']:
            if n == 0 and b > t0 and a < t0 + ROW: d.rectangle([x(max(a, t0)), yb - LH + 14, x(min(b, t0 + ROW)), yb], fill=(255, 215, 215))
        for k, s in enumerate(r['sb']):
            if s and t0 <= beats[k] < t0 + ROW: d.rectangle([x(beats[k]), yb - LH + 14, x(beats[k + 1]), yb], fill=(225, 225, 225))
        for b in beats:
            if t0 <= b < t0 + ROW: d.line([(x(b), yb), (x(b), yb + 5)], fill=(0, 0, 0))
        pts = [(x(T[i]), yb - min(r['sp'][i], 3) / 3 * (LH - 16)) for i in range(N) if t0 <= T[i] < t0 + ROW]
        vis = [r['vis'][i] for i in range(N) if t0 <= T[i] < t0 + ROW]
        for (p, q), v in zip(zip(pts, pts[1:]), vis[1:]):
            if v: d.line([p, q], fill=col, width=2)
        for e in r['ev']:
            if t0 <= e < t0 + ROW: d.ellipse([x(e) - 4, yb - LH + 10, x(e) + 4, yb - LH + 18], fill=col)
        d.line([(70, yb), (Wd - 10, yb)], fill=(0, 0, 0))
im.save(os.path.join(P, 'out/act_check.png'))
if not JSON_ONLY:
    print('\n'.join(out[-2:]), f'-> out/act_check.md, {pj}, out/act_check.png')
sys.exit(CC.exit_code(RULES))

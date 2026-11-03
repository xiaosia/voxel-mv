#!/usr/bin/env python3
"""改了 plan.json 的 tracks 之后，重新生成 ACTIONS.json（动作关 G4 对照用）。在开工包根目录运行：python tools/make_actions.py
动作关用角色的关键点（头、双手、双脚）量动作。帧图里关键点几乎不动的动作（例如有的角色「仰望」只是抬一下头），
量不出来，就放进 subtle 列表，不算进 G4；这些动作要靠镜头（推近）、表情符号、特效让人看出来。
顺手给每个角色量碰撞半径，写进 assets/<角色>/frames.json：foot_r（脚部包围盒半宽）、body_r（画面下 60% 包围盒半宽，
算上裙摆头发），单位是引擎米；没有数据时引擎按 0.3 / 0.45 算。"""
import json, os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dance import load_moves, expand, entry_end
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')
CLEAR = 0.17          # 关键点位移 ≥ 身高的 17% 才算看得出来（动作关的门槛是 15%，留一点余量）
LOOPS = ('walk_side', 'run_side', 'walk_front', 'walk_back', 'laugh', 'cry', 'wave_bye', 'pick_up')
plan = json.load(open('plan.json', encoding='utf-8'))
TL = json.load(open('data/audio.timeline.json', encoding='utf-8'))
lines = json.load(open('data/lines.json', encoding='utf-8'))['lines']
beats = [round(t * 24) + plan['start'] for t in TL['beat_times']]
cuts = [k['c'] for k in plan['cuts']]
beat_of = lambda f: min(range(len(beats)), key=lambda i: abs(beats[i] - f))

def line_of(f):
    t = (f - plan['start']) / 24; cur = lines[0]['id']
    for L in lines:
        if L['t'] <= t + 1e-6: cur = L['id']
    return cur

KP, META = {}, {}
def load(who):
    if who not in KP:
        KP[who] = json.load(open(os.path.join('assets', who, 'kp.json'), encoding='utf-8'))
        META[who] = json.load(open(os.path.join('assets', who, 'frames.json'), encoding='utf-8'))
def kp(who, act, i):
    load(who); q = KP[who][act][i]; return [(q[j], q[j + 1]) for j in range(0, 10, 2)]
def disp(a, b, who):
    return max(((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5 for (x1, y1), (x2, y2) in zip(a, b)) / META[who]['stand_h']
def label(who, act):
    load(who); return META[who]['actions'][act]['label']

def shown(who, e):
    """这一条动作轨显示的帧（从 0 数），按出现顺序"""
    load(who); m, act = e[0], e[1]; n = len(KP[who][act]); o = e[4] if len(e) > 4 and isinstance(e[4], dict) else {}
    if m == 'once':
        r = list(range(o.get('from', 0), o.get('to', n - 1) + 1)); return r[::-1] if o.get('rev') else r
    if m == 'loop': return list(range(o.get('from', 0), o.get('to', n - 1) + 1))
    if m == 'ping': return [e[4], e[5]]
    if m == 'hold': return [e[4]]
    return []

acts, subtle = [], []
MV = load_moves('.', plan); SPB, B0 = plan['tempo']['spb'], plan['tempo']['beat0']
def kpm(who, act, i, mir):
    q = kp(who, act, i)
    if not mir: return q
    cx = META[who]['center_x']; return [(2 * cx - x, y) for x, y in q]
for who, tr in plan['tracks'].items():
    for k, e in enumerate(tr):
        if e[0] == 'dance':        # 舞句：一拍一步，换姿势（或翻面）够大的那几拍进动作关，同一条里至少隔 2 拍
            load(who); o = e[4] if len(e) > 4 and isinstance(e[4], dict) else {}
            steps = expand(MV, META[who], e, entry_end(tr, k, plan['end']), B0, SPB)
            mir, prev, last = bool(o.get('mirror')), None, -10 ** 9
            lab = MV['phrases'][e[1]].get('label', e[1])
            for f, a, i, si, turn in steps:
                if turn: mir = not mir
                cur = kpm(who, a, i, mir)
                if prev is not None and plan['start'] <= f < plan['end']:
                    d = disp(cur, prev, who)
                    if d >= CLEAR and f - last >= 2 * SPB * 24 - 1:
                        acts.append({'line': line_of(f), 'who': who, 'beat': beat_of(f), 'act': f'{lab}·第{si + 1}步', 'frame': f}); last = f
                prev = cur
            continue
        if e[0] == 'once':
            rev = len(e) > 4 and isinstance(e[4], dict) and e[4].get('rev')
            f, txt = e[3], label(who, e[1]) + ('（倒放）' if rev and '倒放' not in label(who, e[1]) else '') + '到位'
        elif e[0] == 'loop' and e[1] in LOOPS: f, txt = e[2], label(who, e[1])
        else: continue
        if not (plan['start'] <= f < plan['end']): continue
        if len(e) > 4 and isinstance(e[4], dict) and e[4].get('gate') is False: continue     # 交接出画这类不进动作关
        fr = shown(who, e)
        own = max(disp(kp(who, e[1], i), kp(who, e[1], fr[0]), who) for i in fr)     # 动作自己的幅度
        prev = tr[k - 1] if k and tr[k - 1][0] not in ('off', 'dance') else None
        sw = 0.0                                                                         # 从上一个动作换过来那一下
        if prev and not any(abs(e[2] - c) <= 1 for c in cuts) and (e[0] != 'once' or e[3] - e[2] <= 18):
            pf = shown(who, prev); pf = pf[-2:] if prev[0] == 'once' else pf
            sw = min(disp(kp(who, prev[1], i), kp(who, e[1], fr[0]), who) for i in pf)
        row = {'line': line_of(f), 'who': who, 'beat': beat_of(f), 'act': txt, 'frame': f}
        if max(own, sw) >= CLEAR: acts.append(row)
        else:
            row['why'] = '帧图里关键点只动了身高的 %.0f%%，动作关量不出来：用推近、表情符号或特效强调' % (100 * max(own, sw))
            subtle.append(row)
key = lambda a: (a['frame'], a['who'])
json.dump({'note': '由 plan.json 的动作轨生成（python tools/make_actions.py）。subtle 里的动作不算进动作关 G4，但分镜里照样要做',
           'actions': sorted(acts, key=key), 'subtle': sorted(subtle, key=key)},
          open('ACTIONS.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f'{len(acts)} 个动作进动作关，{len(subtle)} 个幅度太小（subtle）-> ACTIONS.json')

# ---------- 碰撞半径：站立帧里量，写进 frames.json（collide.js 读，缺省 0.3 / 0.45） ----------
# 这批 Q 版素材头发裙摆很宽，包围盒会虚大（量出来 0.85m）：所以从立牌中线向外数「连续不透明像素」的
# 中位半宽当身宽（脱开的发丝不算），脚用 kp.json 脚点间距 × 1.35（脚点在脚心，包上鞋边）。
def sprite_radii(who):
    import numpy as np
    from PIL import Image
    load(who)
    m = META[who]; base, sh, cx = m['baseline_y'], m['stand_h'], m['center_x']
    k = 2.0 * m.get('mv_scale', 1.0) / sh                       # 素材像素 → 引擎米（立牌统一身高 2.0）
    act = m.get('stand_act') or ('idle' if 'idle' in m['actions'] else sorted(m['actions'])[0])
    fr = m['actions'][act]['frames'][0]['file']
    al = np.asarray(Image.open(os.path.join('assets', who, fr)).convert('RGBA'))[..., 3] > 40
    kp = KP.get(who) or json.load(open(os.path.join('assets', who, 'kp.json'), encoding='utf-8'))
    q = kp[act][0]
    stance = abs(q[8] - q[6]) / 2 * k                            # 两脚脚心间距的一半
    rows = []
    for yy in range(max(0, int(base - .60 * sh)), min(al.shape[0], int(base)), 4):   # 下 60%，每 4 行采一次
        row = al[yy]
        if not row[int(cx)]: continue
        w = 0
        while w < 600 and row[int(cx) - w - 1:int(cx) - w + 7].any(): w += 8     # 中线向左数连续不透明（8px 一档）
        w2 = 0
        while w2 < 600 and row[int(cx) + w2:int(cx) + w2 + 8].any(): w2 += 8     # 向右
        rows.append(max(w, w2))
    body = float(np.median(rows)) * k if rows else stance + 0.15
    return round(min(.45, max(.2, stance * 1.35)), 2), round(min(.45, max(.35, body * 1.1)), 2)   # body 上限 0.45：和「并排间距 ≥1.0」（0.45×2+gap0.1）自洽

for who in plan.get('cast', []):
    try:
        fr, br = sprite_radii(who)
    except Exception as ex:
        print(f'{who}: 量碰撞半径失败（{ex}），用默认 0.3 / 0.45'); continue
    mp = os.path.join('assets', who, 'frames.json')
    m = json.load(open(mp, encoding='utf-8'))
    m['foot_r'], m['body_r'] = fr, br
    json.dump(m, open(mp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{who}: foot_r={fr} body_r={br}（站立帧量得）-> assets/{who}/frames.json')

#!/usr/bin/env python3
"""编舞层的 Python 端：读舞句库（engine/moves.json + plan.json 的 moves/slots），把 dance 动作轨条目按拍展开。
和 engine/relay.js 的 danceAt 同一套规则（一步 = 一拍，speed 改步长，canon 晚几拍开始，槽位取角色有的第一个动作）。
make_actions.py、choreo.py 用它；自己一般不用直接跑。"""
import json, math, os

def load_moves(root, plan):
    mv = {'slots': {}, 'phrases': {}}
    p = os.path.join(root, 'engine', 'moves.json')
    if os.path.exists(p): mv = json.load(open(p, encoding='utf-8'))
    mv.setdefault('slots', {}).update(plan.get('slots') or {})
    mv.setdefault('phrases', {}).update(plan.get('moves') or {})
    return mv

def resolve(mv, meta, a):
    if not a.startswith('@'): return a if a in meta['actions'] else None
    return next((x for x in mv['slots'].get(a, []) if x in meta['actions']), None)

def phrase_acts(mv, meta, pid):
    """舞句用到的动作（按这个角色解析好槽位）；有解析不了的返回 (动作表, 缺的列表)"""
    ph = mv['phrases'].get(pid)
    if not ph: return [], [f'舞句 {pid} 不存在']
    acts, miss = [], []
    for s in ph['steps']:
        r = resolve(mv, meta, s['a'])
        if r is None: miss.append(s['a'])
        elif r not in acts: acts.append(r)
    return acts, miss

def expand(mv, meta, e, f_end, beat0, spb, fps=24):
    """dance 条目 e 从 e[2] 播到 f_end（下一条的 f0），返回每一步 [(帧号, 动作, 帧序, 步序号, 这一步翻面没有)]"""
    ph = mv['phrases'][e[1]]; o = e[4] if len(e) > 4 and isinstance(e[4], dict) else {}
    S = ph['steps']; n = len(S); speed = o.get('speed', 1) or 1; canon = o.get('canon', 0) or 0
    B0 = round((e[2] / fps - beat0) / spb)
    out, kk = [], 0
    while True:
        b = B0 + canon + kk / speed                       # 第 kk 步开始的拍位
        f = round((beat0 + b * spb) * fps)
        if f >= f_end: break
        if f >= e[2]:
            st = S[kk % n]; a = resolve(mv, meta, st['a']); nf = len(meta['actions'][a]['frames'])
            i = st.get('i', 0); i = i + nf if i < 0 else i
            out.append((f, a, max(0, min(nf - 1, i)), kk % n, bool(st.get('turn'))))
            if st.get('i2') is not None:
                j = st['i2']; j = j + nf if j < 0 else j
                out.append((round((beat0 + (b + 0.5 / speed) * spb) * fps), a, max(0, min(nf - 1, j)), kk % n, False))
        kk += 1
        if kk > 10000: break
    return out

def entry_end(tr, k, plan_end):
    for x in tr[k + 1:]:
        return x[1] if x[0] == 'off' else x[2]
    return plan_end

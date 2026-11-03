#!/usr/bin/env python3
"""编舞：按段落表给角色排舞句（dance 动作轨），或者检查已经排好的舞句。在项目根目录运行。
  python tools/run.py choreo                       只出草稿 out/choreo.md（每段每个角色排什么舞句、什么队形），不改 plan.json
  python tools/run.py choreo --apply               把草稿写进 plan.json 的 tracks（只替换这些段落时间里的条目；之前的 plan.json 备份成 plan.before_choreo.json）
  python tools/run.py choreo --parts chorus,drop   只排这几种段落（默认 pre-chorus,chorus,drop,interlude,outro；主歌、桥段一般演剧情）
  python tools/run.py choreo --who claude,deepseek 只给这几个人排（默认 plan.json 的 cast）
  python tools/run.py choreo --check               舞步关 → out/choreo_check.md（预检和 video 也会跑）
草稿只是起点：舞句、队形、哪几拍转身都可以改，也可以在 plan.json 的 moves 里写自己的舞句（格式见 engine/moves.json）。
舞步关（python tools/run.py choreo --check → out/choreo_check.md + out/choreo_check.json；预检和 video 也会跑）：
  D0 每遍副歌 / 炸点里，出场的角色至少跳一句舞（dance 条目）【必过】
  D1 舞句和槽位对这个角色都能解析（帧图里有这些动作），条目开始在拍上（±1 帧）【自动修：吸附到 ±1 帧内最近拍点】
  D2 同一个角色不连续用同一个舞句超过 2 条 【警告】
  D3 副歌的平均舞句能量 ≥ 主歌 / 导歌；最后一遍副歌的能量不低于前面的副歌 【警告】
  D4 每遍副歌的舞句组合不完全一样 【警告】
  D5 新舞步预算：用到的新动作（dance_ 开头）不超过 plan.json 的 choreo.new_moves 个 【警告】
退出码只看必过档（D0）；plan.json 的 choreo.why 写 {"D0 副歌2": "原因"} 可以豁免某一条。"""
import json, os, sys, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checks_common as CC
from dance import load_moves, phrase_acts, entry_end
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')

args = sys.argv[1:]
def opt(name, default=None):
    if name in args: i = args.index(name); return args[i + 1] if i + 1 < len(args) else default
    return default
plan = json.load(open('plan.json', encoding='utf-8'))
FPS, START, END = 24, plan['start'], plan['end']
B0, SPB = plan['tempo']['beat0'], plan['tempo']['spb']
MV = load_moves('.', plan)
META = {c: json.load(open(os.path.join('assets', c, 'frames.json'), encoding='utf-8')) for c in plan['cast']}
CH = plan.get('choreo') or {}
ST = json.load(open('data/structure.json', encoding='utf-8')) if os.path.exists('data/structure.json') else {'parts': []}
PARTS = [dict(p, f0=START + round(p['t0'] * FPS), f1=START + round(p['t1'] * FPS)) for p in ST.get('parts', [])]
LEVEL = {'intro': 1, 'verse': 1, 'pre-chorus': 2, 'chorus': 3, 'interlude': 2, 'bridge': 1, 'outro': 1, 'build': 2, 'drop': 3}
beat_f = lambda b: round((B0 + b * SPB) * FPS)
beat_at = lambda f: (f / FPS - B0) / SPB
os.makedirs('out', exist_ok=True)

def is_new(a): return a.startswith('dance_')
def usable(c, pid):
    acts, miss = phrase_acts(MV, META[c], pid); return not miss

# ---------------------------------------------------------------- 草稿
def draft(parts_f, who):
    rows, tracks_add = [], {c: [] for c in who}
    chorus_n = sum(1 for p in PARTS if p['label'] == 'chorus')
    ci, used_prev = 0, {c: [] for c in who}
    for pi, p in enumerate(PARTS):
        if p['label'] not in parts_f: continue
        lvl = LEVEL.get(p['label'], 1)
        last_chorus = p['label'] == 'chorus' and ci == chorus_n - 1
        if p['label'] == 'chorus': ci += 1
        b0 = int(-(-beat_at(p['f0']) // 1)); b1 = int(beat_at(p['f1']) // 1)
        if b1 - b0 < 4: continue
        n = len(who)
        form = 'unison' if n == 1 else ['mirror', 'canon', 'wave', 'unison'][(pi + ci) % 4] if not last_chorus else 'unison'
        if p['label'] == 'outro': form = 'unison'
        blocks = list(range(b0, b1 - 3, 8))
        for bi, bb in enumerate(blocks):
            seg_end = min(bb + 8, b1)
            lead_pick = None
            for k, c in enumerate(who):
                pool = [pid for pid, ph in MV['phrases'].items() if usable(c, pid)]
                if p['label'] == 'outro' and bi == len(blocks) - 1: want = ['bow_finish'] if 'bow_finish' in pool else pool
                else:
                    lo = max(1, lvl - (1 if bi == 0 and lvl > 1 and not last_chorus else 0))
                    want = [pid for pid in pool if MV['phrases'][pid]['energy'] == lo] or [pid for pid in pool if MV['phrases'][pid]['energy'] <= lvl] or pool
                    if n > 1: want = [pid for pid in want if MV['phrases'][pid].get('people') == 'group'] or want
                # 先用新舞步（有的话），再避开刚用过的；每遍副歌错开起点
                score = lambda pid: (any(is_new(a) for a in phrase_acts(MV, META[c], pid)[0]), -used_prev[c][-2:].count(pid), -used_prev[c].count(pid))
                want = sorted(want, key=score, reverse=True)
                top = [x for x in want if score(x) == score(want[0])]
                pick = top[(bi + ci) % len(top)]
                if k and lead_pick in pool and (n == 1 or MV['phrases'][lead_pick].get('people') == 'group'): pick = lead_pick   # 多人跟领舞跳同一句，靠队形（镜像、错拍）做变化
                if k == 0: lead_pick = pick
                used_prev[c].append(pick)
                o = {}
                if form == 'mirror' and k % 2: o['mirror'] = True
                if form == 'canon': o['canon'] = k
                if form == 'wave': o['canon'] = round(0.5 * k, 2)
                if last_chorus: o['size'] = 1.2
                tracks_add[c].append((beat_f(bb), beat_f(seg_end), ['dance', pick, beat_f(bb), None] + ([o] if o else [])))
                rows.append((p['name'], f'{bb}–{seg_end}', c, pick, MV['phrases'][pick].get('label', pick), form, o))
    return rows, tracks_add

def apply(tracks_add):
    shutil.copy('plan.json', 'plan.before_choreo.json')
    for c, adds in tracks_add.items():
        if not adds: continue
        tr = plan['tracks'].setdefault(c, [])
        f0e = lambda x: x[1] if x[0] == 'off' else x[2]
        # 按段落合并成连续窗口，窗口里原来的条目删掉，窗口结束处接回原来那一刻在播的条目（拿不准的接 idle 循环）
        wins = []
        for a, b, e in adds:
            if wins and wins[-1][1] >= a: wins[-1][1] = max(wins[-1][1], b)
            else: wins.append([a, b])
        new = list(tr)
        for a, b in wins:
            active_b = None
            for x in sorted(new, key=f0e):
                if f0e(x) <= b: active_b = x
            if active_b is not None and active_b[0] == 'off' and f0e(active_b) <= a: continue   # 那时她本来不出场：不加
            new = [x for x in new if not (a <= f0e(x) < b)]
            if active_b is None or active_b[0] in ('once', 'dance'): tail = ['loop', 'idle', b, None]
            elif active_b[0] == 'off': tail = ['off', b, None]
            else: tail = list(active_b); tail[2] = b
            if not any(f0e(x) == b for x in new): new.append(tail)
        for a, b, e in adds:
            if any(a <= f0e(x) < b and x[0] == 'off' for x in tr): continue
            if any(w[0] <= a < w[1] for w in wins): new.append(e)
        new.sort(key=lambda x: (f0e(x), x[0] != 'dance'))
        plan['tracks'][c] = new
        acts = set(plan.get('extra_actions', {}).get(c, []))
        plan.setdefault('extra_actions', {})[c] = sorted(acts | {'idle'})
    json.dump(plan, open('plan.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# ---------------------------------------------------------------- 舞步关
def part_of(f):
    return next((p for p in PARTS if p['f0'] <= f < p['f1']), None)
def check():
    res, why, RULES = [], CH.get('why') or {}, []
    def gate(rid, name, ok, msg, key=None):
        w = why.get(key or f'{rid} {name}')
        if not ok and w:
            RULES.append({'rule': rid, 'name': name, 'ok': True, 'detail': f'豁免（{w}）— {msg}'})
            res.append(f'- {name}：豁免（{w}）— {msg}'); return
        RULES.append({'rule': rid, 'name': name, 'ok': bool(ok), 'detail': msg})
        res.append(f'- {name}：{"PASS" if ok else "FAIL"} — {msg}')
    dances = {c: [(k, e) for k, e in enumerate(tr) if e[0] == 'dance'] for c, tr in plan['tracks'].items()}
    on = lambda c, f: (lambda tr: (lambda x: x is not None and x[0] != 'off')(next((x for x in reversed(tr) if (x[1] if x[0] == 'off' else x[2]) <= f), None)))(plan['tracks'].get(c, []))
    # D0
    bad0 = []
    for p in PARTS:
        if p['label'] not in ('chorus', 'drop'): continue
        for c in plan['cast']:
            if not any(on(c, f) for f in range(p['f0'], p['f1'], 12)): continue
            if not any(p['f0'] - 12 <= e[2] < p['f1'] for _, e in dances.get(c, [])) and not why.get(f'D0 {p["name"]}'):
                bad0.append(f'{p["name"]} {c}')
    gate('D0', '副歌有舞', not bad0, '、'.join(bad0) + ' 没有 dance 条目（跑 python tools/run.py choreo 出草稿；故意不跳写进 choreo.why，键 "D0 副歌2"）' if bad0 else '每遍副歌 / 炸点出场的角色都跳了')
    # D1
    bad1 = []
    for c, ds in dances.items():
        for k, e in ds:
            if c not in META: bad1.append(f'{c} 不在 cast 里'); continue
            acts, miss = phrase_acts(MV, META[c], e[1])
            if miss: bad1.append(f'{c} @{e[2]} {e[1]} 缺 {"/".join(miss)}')
            b = beat_at(e[2]); off = abs(b - round(b)) * SPB * FPS
            if off > 1.01: bad1.append(f'{c} @{e[2]} {e[1]} 没在拍上（差 {off:.0f} 帧，用 beatFrame(n)）')
    gate('D1', '能解析、在拍上', not bad1, '；'.join(bad1[:8]) or '舞句、槽位都对得上帧图，条目都在拍上')
    # D2
    bad2 = []
    for c, ds in dances.items():
        run, prev = 0, None
        for k, e in ds:
            run = run + 1 if e[1] == prev else 1; prev = e[1]
            if run == 3: bad2.append(f'{c} {e[1]} @{e[2]}')
    gate('D2', '不连续重复', not bad2, '连续 3 条同一个舞句：' + '、'.join(bad2[:6]) if bad2 else '同一个人没有连着 3 条用同一句')
    # D3 D4
    def energy(c, p):
        es = [MV['phrases'][e[1]]['energy'] for _, e in dances.get(c, []) if p['f0'] - 12 <= e[2] < p['f1'] and e[1] in MV['phrases']]
        return sum(es) / len(es) if es else None
    msg3, ok3, msg4, ok4 = [], True, [], True
    for c in plan['cast']:
        ch = [(p, energy(c, p)) for p in PARTS if p['label'] == 'chorus']
        ch = [(p, x) for p, x in ch if x is not None]
        vs = [x for p in PARTS if p['label'] in ('verse', 'pre-chorus') for x in [energy(c, p)] if x is not None]
        if ch and vs and sum(x for _, x in ch) / len(ch) < max(vs): ok3 = False; msg3.append(f'{c} 副歌平均能量 {sum(x for _, x in ch) / len(ch):.1f} 低于主歌/导歌 {max(vs):.1f}')
        if len(ch) >= 2 and ch[-1][1] < max(x for _, x in ch[:-1]): ok3 = False; msg3.append(f'{c} 最后一遍副歌 {ch[-1][1]:.1f} 比前面的副歌小')
        seqs = [tuple(e[1] for _, e in dances.get(c, []) if p['f0'] - 12 <= e[2] < p['f1']) for p in PARTS if p['label'] == 'chorus']
        seqs = [s for s in seqs if s]
        if len(seqs) >= 2 and len(set(seqs)) < len(seqs): ok4 = False; msg4.append(f'{c} 有两遍副歌舞句一模一样：{" ".join(seqs[0])}')
    gate('D3', '能量跟段落走', ok3, '；'.join(msg3) or '副歌 ≥ 主歌/导歌，最后一遍副歌最大（或者只有一种段落有舞）')
    gate('D4', '每遍副歌不一样', ok4, '；'.join(msg4) or '每遍副歌的舞句组合都不同（或者只跳了一遍）')
    # D5
    budget = int(CH.get('new_moves', 0) or 0)
    used = sorted({a for c, ds in dances.items() if c in META for _, e in ds for a in phrase_acts(MV, META[c], e[1])[0] if is_new(a)})
    used += sorted({a for c, tr in plan['tracks'].items() for e in tr if e[0] in ('loop', 'once', 'ping', 'hold') and is_new(e[1])} - set(used))
    gate('D5', '新舞步预算', len(used) <= budget, f'用到新动作 {len(used)} 个（{"、".join(used) or "无"}），预算 choreo.new_moves = {budget}')
    n_d = sum(len(v) for v in dances.values())
    for r in RULES: r.setdefault('tier', CC.tier(r['rule']))
    tiers = {'must': 0, 'auto': 0, 'warn': 0}
    for r in RULES:
        if not r['ok']: tiers[r['tier']] += 1
    out = ['# 舞步关\n', f'dance 条目 {n_d} 条；没过：必过 {tiers["must"]}，自动修 {tiers["auto"]}，警告 {tiers["warn"]}\n'] + res
    out += ['', '| 关 | 结果 | 说明 |', '|---|---|---|']
    out += ['| %s %s | %s | %s |' % (r['rule'], r['name'], ('豁免' if r['detail'].startswith('豁免') else ('**FAIL·%s**' % CC.CN[r['tier']]) if not r['ok'] else 'PASS'), r['detail'][:200]) for r in RULES]
    out.append('\n**%s**' % ('PASS' if tiers['must'] == 0 else 'FAIL（必过档）') + ('' if tiers['must'] else '（自动修档跑 python tools/run.py check --fix）'))
    open('out/choreo_check.md', 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    p = CC.dump_json('choreo_check', RULES)
    if '--json' not in args:
        print('\n'.join(res)); print(out[-1].strip(), f'-> out/choreo_check.md, {p}')
    return CC.exit_code(RULES)

if __name__ == '__main__':
    if '--check' in args: sys.exit(check())
    if not PARTS: sys.exit('没有段落表 data/structure.json：先按 SKILL.md「歌曲由什么组成」生成，再排舞')
    parts_f = (opt('--parts') or 'pre-chorus,chorus,drop,interlude,outro').split(',')
    who = (opt('--who') or ','.join(plan['cast'])).split(',')
    rows, adds = draft(parts_f, who)
    md = ['# 编舞草稿\n', '每 8 拍（2 小节）一条 dance。队形：unison 齐跳、mirror 隔一个人镜像、canon 一人晚一拍（轮唱）、wave 一人晚半拍（波浪）。',
          '站位（谁站哪、间隔多大）在 shots.js 里给：舞句的位移是在你给的站位上叠加的，两人之间至少留 1 个身高。\n',
          '| 段落 | 拍 | 角色 | 舞句 | 中文 | 队形 | 选项 |', '|---|---|---|---|---|---|---|']
    md += [f'| {a} | {b} | {c} | {d} | {e} | {f} | {json.dumps(g, ensure_ascii=False) if g else ""} |' for a, b, c, d, e, f, g in rows]
    open('out/choreo.md', 'w', encoding='utf-8').write('\n'.join(md) + '\n')
    print(f'{len(rows)} 条舞句 -> out/choreo.md')
    if '--apply' in args:
        apply(adds); print('已写进 plan.json 的 tracks（旧的在 plan.before_choreo.json）。接着跑 python tools/run.py actions')
    else: print('满意就加 --apply 写进 plan.json')

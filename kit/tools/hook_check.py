#!/usr/bin/env python3
"""钩子关（稳妥模式拦渲染，自由模式只出报告）：没词的地方不能变成空景，开场要抓人，人声进来那一拍要兑现，
副歌进来要炸、间奏桥段进来要换。
只看「什么时候发生了一件事」，不看画法。

「事件」= 登记过的、看得出的一件事，任何一种都算：
  - 角色动作：ACTIONS.json 的 actions（{t} 秒 或 {beat} 拍号；voxel-mv 由 plan.json 的 tracks 生成）
  - 转场 / 镜头内大变化：voxel-mv 是 plan.json 的 cuts[].c、incamera[].key、handoffs；song-mv 是页面的 window.TRANSITIONS[].key
  - 表情符号：voxel-mv 的 plan.json emotes[].f0
  - 其他画面事件（镜头揭示、片名出现、道具亮起、灯亮、新东西入画…）：
      voxel-mv 写 plan.json 的 events: [{"f": 帧号(全曲), "what": "拉开露出整条街"}]
      song-mv  写 ACTIONS.json 的 events: [{"t": 秒, "what": "片名浮出"}]
    登记了就要真的做出来，并且看得出来。

  H1 开场钩子：全片从歌的第 0 秒开始时，前 5 秒里至少 1 个事件（第一眼就要有东西可看，不要空镜慢慢淡入）【必过】
  H2 没词长段不空：连续的 ♪ 行（前奏、间奏、尾奏，data/lines.json）加起来 ≥ 16 秒时，里面每 4 小节至少 1 个事件 【警告】
  H3 人声进来要兑现：≥ 8 秒的 ♪ 段之后第一句歌词的句首 ±1 拍内至少 1 个事件（揭开钩子、或一次转场推进正片）【警告】
  有段落表（data/structure.json → data/lines.json 的 parts，song_structure.py 产出）时再查：
  H4 副歌、炸点进来要炸：每一遍副歌 / 炸点的开头 ±1 拍内至少 1 个事件（一般是一次大转场或全片最大的动作）【必过】
  H5 换段要换：每个间奏、桥段的开头 ±1 拍内至少 1 个事件（换景、换光色、换视角的那一下）【警告】
报告 → out/hook_check.md，结构化结果 → out/hook_check.json（report.py 汇总）。
用法：python hook_check.py [项目目录] [--mode safe|free] [--json]；voxel-mv 的场景关也会调用它。"""
import json, os, sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')

OPEN_S, LONG_S, BARS, VOX_S = 5.0, 16.0, 4, 8.0
FPS = 24


def _load(p, default=None):
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else default


def check(P='.'):
    """返回 (fails, report_lines)。时间一律用本项目本地秒（data/ 里的时间轴）。"""
    TL = _load(os.path.join(P, 'data/audio.timeline.json'))
    L = (_load(os.path.join(P, 'data/lines.json')) or {}).get('lines', [])
    if not TL or not L: return [], ['- 没有 data/lines.json 或时间轴，跳过前奏钩子关']
    beats, bars = TL.get('beat_times', []), TL.get('bar_times', [])
    spb = TL.get('seconds_per_beat') or (60 / TL['tempo_bpm'] if TL.get('tempo_bpm') else 0.5)
    plan = _load(os.path.join(P, 'plan.json'))
    acts = _load(os.path.join(P, 'ACTIONS.json'), {}) or {}
    ev = []      # (秒, 来源)
    for a in acts.get('actions', []):
        t = a.get('t')
        if t is None and 'beat' in a and 0 <= int(a['beat']) < len(beats): t = beats[int(a['beat'])]
        if t is not None: ev.append((float(t), f"动作 {a.get('who', '')} {a.get('act', '')}".strip()))
    for e in acts.get('events', []):
        if 't' in e: ev.append((float(e['t']), '事件 ' + e.get('what', '')))
    if plan:     # voxel-mv
        S0 = plan.get('start', 0); sec = lambda f: (f - S0) / FPS
        ev += [(sec(c['c']), '转场 ' + c.get('kind', c.get('type', ''))) for c in plan.get('cuts', []) if 'c' in c]
        ev += [(sec(c['key']), '镜头内变化 ' + c.get('note', '')) for c in plan.get('incamera', []) if 'key' in c]
        ev += [(sec(e['f0']), '表情 ' + str(e.get('g', ''))) for e in plan.get('emotes', []) if 'f0' in e]
        ev += [(sec(h[k]), '交接') for h in plan.get('handoffs', []) for k in ('key',) if k in h]
        ev += [(sec(e['f']), '事件 ' + e.get('what', '')) for e in plan.get('events', []) if 'f' in e]
        film_start = S0 == 0
    else:        # song-mv
        meta = _load(os.path.join(P, 'out/page_meta.json'), {}) or {}
        ev += [(float(t['key']), '转场 ' + t.get('kind', '')) for t in (meta.get('TRANSITIONS') or []) if 'key' in t]
        film_start = True
    ev.sort()
    def n_in(a, b): return [e for e in ev if a - 1e-6 <= e[0] < b + 1e-6]

    fails, rep = [], []
    # H1
    if film_start:
        got = n_in(0, OPEN_S)
        rep.append(f"- H1 开场 0–{OPEN_S:g} 秒：{len(got)} 个事件" + (f"（第一个在 {got[0][0]:.1f} 秒：{got[0][1]}）" if got else ''))
        if not got: fails.append(f'H1 开场前 {OPEN_S:g} 秒没有任何事件：第一眼要有东西可看——第一个动作 / 镜头变化 / 揭示放在前奏的第一个重拍上（登记进 events）')
    else:
        rep.append('- H1 开场：本段不是从歌的开头开始，不查')
    # 连续的 ♪ 段
    runs, cur = [], None
    for l in L:
        if l['text'].startswith('♪'):
            if cur and abs(cur[1] - l['t']) < 1e-3: cur[1] = l['end']
            else: cur = [l['t'], l['end'], (lambda w: w[1] if len(w) > 1 and '/' not in w[1] else '没词段')(l['text'].split())]; runs.append(cur)
        else: cur = None
    for t0, t1, name in runs:
        span = t1 - t0
        if span < LONG_S: continue
        bar = 4 * spb                     # 窗口切在小节线上，每 4 小节一个；头尾不满 2 小节的零头并进相邻窗口
        bi = [b for b in bars if t0 - 1e-6 <= b < t1][::BARS]
        edges = [t0] + [b for b in bi if b - t0 > 2 * bar - 1e-6 and t1 - b > 2 * bar - 1e-6] + [t1]
        empty = []
        for a, b in zip(edges, edges[1:]):
            if not n_in(a, b): empty.append((a, b))
        rep.append(f"- H2 {name} {t0:.1f}–{t1:.1f} 秒（{span:.1f} 秒）：{len(edges) - 1 - len(empty)}/{len(edges) - 1} 个 {BARS} 小节窗口有事件")
        if empty: fails.append(f"H2 {name} 里 " + '、'.join(f'{a:.1f}–{b:.1f}' for a, b in empty) +
                               f" 秒没有任何事件：没词的长段每 {BARS} 小节要揭开一点、加一点（角色动作、转场、镜头揭示、新东西入画，登记进 events）")
    # H3
    for t0, t1, name in runs:
        if t1 - t0 < VOX_S: continue
        nxt = [l for l in L if abs(l['t'] - t1) < 1e-3 and not l['text'].startswith('♪')]
        if not nxt: continue
        got = n_in(t1 - spb, t1 + spb)
        rep.append(f"- H3 {name}之后 {t1:.1f} 秒人声进来：±1 拍内 {len(got)} 个事件" + (f"（{got[0][1]}）" if got else ''))
        if not got: fails.append(f"H3 {t1:.1f} 秒人声进来（{name}结束）±1 拍内没有事件：这一拍兑现钩子——角色亮相、道具揭开或一次转场")
    if not runs: rep.append('- 没有 ♪ 段，H2/H3 不查')
    # H4 / H5：按段落表
    parts = (_load(os.path.join(P, 'data/lines.json')) or {}).get('parts') or []
    dur = TL.get('duration', L[-1]['end'])
    if not parts: rep.append('- 没有段落表（data/structure.json），H4/H5 不查')
    for pt in parts:
        lab = pt.get('label')
        if lab not in ('chorus', 'drop', 'interlude', 'bridge') or pt['t0'] < 0.5 or pt['t0'] > dur - 1: continue
        keys = [pt['t0']] + ([pt['vocal_t0']] if pt.get('vocal_t0') is not None and abs(pt['vocal_t0'] - pt['t0']) > spb else [])
        got = [e for k in keys for e in n_in(k - spb, k + spb)]
        tag = 'H4' if lab in ('chorus', 'drop') else 'H5'
        rep.append(f"- {tag} {pt.get('name', lab)} {pt['t0']:.1f} 秒进来：±1 拍内 {len(got)} 个事件" + (f"（{got[0][1]}）" if got else ''))
        if not got:
            fails.append(f"{tag} {pt.get('name', lab)} {pt['t0']:.1f} 秒进来 ±1 拍内没有事件：" +
                         ('副歌 / 炸点要炸开——这一拍放一次大转场、大动作或最强的画面变化' if tag == 'H4' else
                          '间奏 / 桥段要换口气——这一拍换景、换光色或换视角（登记成转场或 events）'))
    return fails, rep


if __name__ == '__main__':
    import argparse
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import checks_common as CC
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('project', nargs='?', default='.', help='项目目录（默认当前目录）')
    ap.add_argument('--mode', choices=('safe', 'free'), help='默认读项目里 MODE 文件（现在只影响报告措辞，必过档两种模式都拦）')
    ap.add_argument('--json', action='store_true', help='只把结构化结果写进 out/hook_check.json（markdown 报告照写）')
    a = ap.parse_args()
    P, mode = a.project, a.mode
    if not mode:
        mf = os.path.join(P, 'MODE'); mode = (open(mf, encoding='utf-8').read().split() or ['safe'])[0] if os.path.exists(mf) else 'safe'
    fails, rep = check(P)
    by = {}
    for f in fails:
        rid, rest = f.split()[0], f.split(None, 1)[1] if len(f.split()) > 1 else ''
        by.setdefault(rid, []).append(rest)
    NAMES = {'H1': '开场钩子', 'H2': '没词长段不空', 'H3': '人声进来要兑现', 'H4': '副歌/炸点要炸', 'H5': '换段要换'}
    RULES = []
    for rid in ('H1', 'H2', 'H3', 'H4', 'H5'):
        ok = not by.get(rid)
        lines = [x[2:].strip() for x in rep if x.startswith('- ' + rid)]
        RULES.append({'rule': rid, 'name': NAMES[rid], 'ok': ok, 'detail': '；'.join(by.get(rid, [])) or ('；'.join(lines) or '通过')})
    for r in RULES: r.setdefault('tier', CC.tier(r['rule']))
    tiers = {'must': 0, 'auto': 0, 'warn': 0}
    for r in RULES:
        if not r['ok']: tiers[r['tier']] += 1
    out = [f"# hook check（钩子关）\n\nmode: **{'safe' if mode != 'free' else 'free'}**；没过：必过 {tiers['must']}，警告 {tiers['warn']}\n"] + rep
    out += ['', '## gates', '', '| 关 | 结果 | 说明 |', '|---|---|---|']
    out += ['| %s %s | %s | %s |' % (r['rule'], r['name'], ('**FAIL·%s**' % CC.CN[r['tier']]) if not r['ok'] else 'PASS', r['detail'][:200]) for r in RULES]
    out += ['', f"**{'PASS' if tiers['must'] == 0 else 'FAIL'}**（必过档全过即 PASS，两种模式都拦）"]
    os.makedirs(os.path.join(P, 'out'), exist_ok=True)
    open(os.path.join(P, 'out/hook_check.md'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    p = CC.dump_json('hook_check', RULES, os.path.join(P, 'out'))
    if not a.json:
        print('\n'.join(f"| {r['rule']} | {'PASS' if r['ok'] else 'FAIL·' + CC.CN[r['tier']]} | {r['detail'][:120]} |" for r in RULES))
        print(f"-> out/hook_check.md, {p}  {'PASS' if tiers['must'] == 0 else f'必过 {tiers['must']} 项 FAIL'}")
    sys.exit(CC.exit_code(RULES))

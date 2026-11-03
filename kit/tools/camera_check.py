#!/usr/bin/env python3
"""运镜关（数据来自探针 out/voxel.json 的 cam 字段，voxel_dump.mjs 导出时带出）：
  K1 运镜不单一【必过，K1+K3 的种类部分合并】：全片运镜种类 ≥3，且单一种类不占 motion 镜头的一半以上；
     副歌的运动量（速度中位数）要大于主歌。手写机位（没写 camera 轨）的镜头按实际运动推种类：
     拉近=dolly、变焦=zoom、横向看=pan、升降=crane，不冤枉全部算一种。
  K2 相邻镜头换运镜【警告】：挨着的两个镜头别用同一种运镜。
  K3 段落呼吸【警告】：桥段换一种运镜、最后一遍副歌运动量最大、尾奏慢下来但别定死。
  K4 炸点有冲击【警告】：drop 段里要有 punch（打在重拍上的 fov 冲击）。
  K5 定机位要有理由【警告】：连续 2 小节以上不动镜头要有 camera_why 豁免说明。
  K6 安全线已自动修【自动修】：orbit/fov/手持幅度这些超线的地方引擎运行时已经夹好（entry.fixed 有记录），
     这里列出来算「已自动修」，不拦。
plan.json 的 camera_why: [{"f0":..,"f1":..,"why":".."}] 给 K5 豁免；allow 里 rule:"camera" 也算。
报告 → out/camera_check.md，结构化结果 → out/camera_check.json（report.py 汇总）。
用法：python camera_check.py [项目目录] [--mode safe|free] [--json]
先跑过探针（python tools/run.py check 会自动跑）：探针里没有 cam 字段 = 引擎太旧，upgrade-engine。"""
import json, os, sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')

FPS = 24
LAYERS = {'handheld', 'punch', 'bob'}          # 叠加层不算运镜种类（K1 数的是 dolly/zoom/orbit…）
STILL_SPEED = 0.05                            # 低于这个速度算定机位（K5）


def _load(p, default=None):
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else default


def median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else None


def kind_of_shot(cams):
    """一个镜头的运镜种类：写了 moves 的直接用（去掉叠加层）；全手动（moves 空）从首尾实际运动推。"""
    kinds = set()
    for c in cams:
        kinds |= {m for m in (c.get('moves') or []) if m not in LAYERS}
    if kinds:
        return kinds
    a, b = cams[0], cams[-1]
    if not a.get('pos') or not b.get('pos') or not a.get('target'):
        return set()
    def dist(c):
        return sum((c['pos'][i] - c['target'][i]) ** 2 for i in range(3)) ** .5
    d0, d1 = dist(a), dist(b)
    if abs(d1 - d0) / max(d0, 1e-6) > 0.06: kinds.add('dolly')
    if abs((b.get('fov') or 28) - (a.get('fov') or 28)) > 0.8: kinds.add('zoom')
    dvo = sum((b['target'][i] - a['target'][i]) ** 2 for i in range(3)) ** .5
    if dvo / max(d0, 1e-6) > 0.06: kinds.add('pan')
    if abs(b['pos'][1] - a['pos'][1]) > 0.3: kinds.add('crane')
    return kinds


def check(P='.'):
    vp = os.path.join(P, 'out', 'voxel.json')
    if not os.path.exists(vp): return [], ['- 没有探针数据 out/voxel.json（先跑 python tools/run.py check 或 voxel），运镜关跳过']
    data = _load(vp) or {}
    STEP = max(1, data.get('step') or 1)
    frames = [fr for fr in data.get('frames', []) if fr.get('cam')]
    if not frames:
        return [], ['- 探针里没有 cam 字段：引擎是旧版，项目里跑 python tools/run.py upgrade-engine 后重新 check，运镜关跳过']
    plan = _load(os.path.join(P, 'plan.json')) or {}
    ST = _load(os.path.join(P, 'data/structure.json')) or {}
    TL = _load(os.path.join(P, 'data/audio.timeline.json')) or {}
    START = (data.get('PLAN') or plan).get('start', 0)
    parts = [dict(p, f0=START + round(p['t0'] * FPS), f1=START + round(p['t1'] * FPS)) for p in ST.get('parts', [])]
    spb = ((plan.get('tempo') or {}).get('spb')) or TL.get('seconds_per_beat') or 0.5
    why = [(w.get('f0'), w.get('f1'), w.get('why') or '') for w in plan.get('camera_why', [])]
    why += [(a.get('f0'), a.get('f1'), a.get('why') or '') for a in plan.get('allow', []) if a.get('rule') == 'camera']

    # 按镜头聚合 CAMLOG（探针 step>1 时按帧号排）
    shots, order = {}, []
    for fr in frames:
        sid = fr['cam'].get('shot') or fr.get('shot') or '?'
        if sid not in shots: shots[sid] = []; order.append(sid)
        shots[sid].append(fr['cam'])
    kinds = {sid: kind_of_shot(cs) for sid, cs in shots.items()}
    sec_of = lambda f: (f - START) / FPS
    frames_in = lambda f0, f1: [fr['cam'] for fr in frames if f0 <= fr['f'] <= f1 and fr['cam'].get('speed') is not None]
    speeds = lambda f0, f1: [c['speed'] for c in frames_in(f0, f1)]

    fails, rep = [], []

    # ---------- K1（必过）：种类 ≥3、单一种类 ≤50%、副歌 > 主歌 ----------
    motion_shots = [sid for sid in order if kinds[sid]]
    all_kinds = sorted({k for sid in motion_shots for k in kinds[sid]})
    if len(order) < 3 or not motion_shots:
        rep.append(f'- K1 {len(order)} 个镜头、{len(motion_shots)} 个有运镜')
        if not motion_shots: fails.append('K1 全片没有一个镜头在动：至少要有推、拉、环绕、变焦里的一种（写 camera 轨，或 camplan 起草）')
    else:
        rep.append(f'- K1 运镜种类 {len(all_kinds)} 种（{"、".join(all_kinds)}），{len(motion_shots)}/{len(order)} 个镜头在动')
        if len(all_kinds) < 3:
            fails.append(f'K1 全片只有 {len(all_kinds)} 种运镜（{"、".join(all_kinds)}）：至少 3 种——推/拉、环绕、变焦、跟、摇里挑着用，别一条 lerp 拉全片')
        dom = max(all_kinds, key=lambda k: sum(1 for sid in motion_shots if k in kinds[sid]))
        dn = sum(1 for sid in motion_shots if dom in kinds[sid])
        rep.append(f'- K1 用得最多的是 {dom}（{dn}/{len(motion_shots)} 个镜头）')
        if dn * 2 > len(motion_shots):
            fails.append(f'K1 {dom} 占了 {dn}/{len(motion_shots)} 个镜头：单一种类别超过一半，换几段改成环绕 / 变焦 / 跟')
    ch = [p for p in parts if p['label'] in ('chorus', 'drop')]
    vs = [p for p in parts if p['label'] in ('verse', 'intro')]
    if ch and vs:
        cs, vsn = median(speeds(ch[0]['f0'], ch[-1]['f1'])), median(speeds(vs[0]['f0'], vs[-1]['f1']))
        if cs is not None and vsn is not None:
            rep.append(f'- K1 副歌速度中位数 {cs:.2f} / 主歌 {vsn:.2f}（单位/秒）')
            if cs <= vsn:
                fails.append(f'K1 副歌的运镜速度（中位数 {cs:.2f}）没有快过主歌（{vsn:.2f}）：副歌放开——环绕、快速推近、punch 都行，主歌收着走')
        else:
            rep.append('- K1 副歌/主歌段落里没有速度数据，运动量对比跳过')

    # ---------- K2（警告）：相邻镜头不同 ----------
    adj_same = [(a, b) for a, b in zip(order, order[1:]) if kinds[a] and kinds[b] and kinds[a] == kinds[b]]
    if adj_same:
        for a, b in adj_same[:6]:
            fails.append(f'K2 镜头 {a} → {b} 用了同样的运镜（{"、".join(sorted(kinds[a]))}）：挨着的镜头换一种，剪出来才有节奏')
    rep.append(f'- K2 相邻镜头同运镜 {len(adj_same)} 处')

    # ---------- K3（警告）：桥段换种、最后一遍副歌最大、尾奏慢但不定 ----------
    br = [p for p in parts if p['label'] == 'bridge']
    if br and motion_shots:
        b_shots = [sid for sid in order if any(shots[sid][0]['f'] <= p['f1'] and shots[sid][-1]['f'] >= p['f0'] for p in br)]
        b_kinds = set().union(*[kinds[sid] for sid in b_shots if kinds[sid]]) if b_shots else set()
        o_kinds = set().union(*[kinds[sid] for sid in motion_shots if sid not in b_shots]) if len(motion_shots) > len(b_shots) else set()
        if b_kinds and o_kinds and not (b_kinds - o_kinds):
            fails.append(f'K3 桥段（{"、".join(p.get("name", "bridge") for p in br)}）用的运镜（{"、".join(sorted(b_kinds))}）和前面一样：桥段要换口气，换一种运镜（拉远、升起、慢环绕都行）')
        rep.append(f'- K3 桥段运镜 {sorted(b_kinds) if b_kinds else "（无）"}' + ('（和别段重复）' if b_kinds and o_kinds and not (b_kinds - o_kinds) else ''))
    las = [p for p in parts if p['label'] in ('chorus', 'drop')]
    if len(las) >= 2:
        meds = [median(speeds(p['f0'], p['f1'])) for p in las]
        if all(m is not None for m in meds) and meds[-1] < max(meds):
            fails.append(f'K3 最后一遍副歌的运镜速度（{meds[-1]:.2f}）不是最强的一遍（最强 {max(meds):.2f}）：收尾的副歌推到最满——幅度、速度或 punch 加大')
        rep.append(f'- K3 各遍副歌速度中位数 {" / ".join(f"{m:.2f}" for m in meds)}')
    ou = [p for p in parts if p['label'] == 'outro']
    if ou and motion_shots:
        om, vm = median(speeds(ou[0]['f0'], ou[-1]['f1'])), median(speeds(vs[0]['f0'], vs[-1]['f1'])) if vs else None
        o_shots = [sid for sid in order if shots[sid][0]['f'] <= ou[0]['f1'] and shots[sid][-1]['f'] >= ou[0]['f0']]
        o_kinds = set().union(*[kinds[sid] for sid in o_shots if kinds[sid]]) if o_shots else set()
        if not o_kinds:
            fails.append('K3 尾奏完全定机位：慢下来可以，但别停死——慢推、慢拉或轻微 handheld 收住')
        elif vm is not None and om is not None and om > vm:
            fails.append(f'K3 尾奏速度（{om:.2f}）比主歌（{vm:.2f}）还快：收尾要收，速度降下来')
        else:
            rep.append(f'- K3 尾奏 {sorted(o_kinds)}、速度中位数 {om:.2f}' + (f'（主歌 {vm:.2f}）' if vm is not None else ''))

    # ---------- K4（警告）：drop 里有 punch ----------
    dr = [p for p in parts if p['label'] == 'drop']
    for p in dr:
        hit = [c for c in frames_in(p['f0'], p['f1']) if 'punch' in (c.get('moves') or [])]
        rep.append(f'- K4 {p.get("name", "drop")} {sec_of(p["f0"]):.1f} 秒起：punch {len(hit)} 帧')
        if not hit:
            fails.append(f'K4 {p.get("name", "drop")}（{sec_of(p["f0"]):.1f} 秒起）没有 punch：炸点那一下给 fov 冲击（camera 轨加 punch，on: hit）')

    # ---------- K5（警告）：定机位 ≤2 小节，有 camera_why 豁免 ----------
    still_f = []                                  # [(f0, f1)] 连续静止的帧段
    run0 = None
    prev = None
    for fr in frames:
        c = fr['cam']
        still = not (c.get('moves') or []) and (c.get('speed') or 0) < STILL_SPEED
        if still and run0 is not None and prev is not None and fr['f'] - prev <= STEP + 1: still_f[-1] = (run0, fr['f'])
        elif still: run0 = fr['f']; still_f.append((run0, fr['f']))
        else: run0 = None
        prev = fr['f']
    two_bars = 8 * spb * FPS
    n_k5 = 0
    for f0, f1 in [r for r in still_f if r[1] - r[0] >= two_bars]:
        n_k5 += 1
        cov = [w for w in why if w[0] is not None and w[0] <= f0 and f1 <= (w[1] or f1)]
        if cov:
            rep.append(f'- K5 {sec_of(f0):.1f}–{sec_of(f1):.1f} 秒定机位（有理由：{cov[0][2]}）')
        else:
            fails.append(f'K5 {sec_of(f0):.1f}–{sec_of(f1):.1f} 秒（{f1 - f0} 帧）定机位：超过 2 小节的静止镜头要有理由——写在 plan.json 的 camera_why 里（f0/f1/why），或者给点微动（呼吸、手持 0.02）')
    rep.append(f'- K5 超 2 小节的定机位 {n_k5} 处' + ('（没豁免的见 FAIL 行）' if any(f.startswith('K5') for f in fails) else '') if n_k5 else '- K5 没有超 2 小节的定机位')

    # ---------- K6（自动修）：引擎运行时已夹 ----------
    notes = {}
    for fr in frames:
        for x in fr['cam'].get('fixed') or []: notes[x] = notes.get(x, 0) + 1
    if notes:
        rep.append('- K6 已自动修（引擎运行时夹好，不用改 plan）：' + '；'.join(f'{k}（{v} 帧）' for k, v in notes.items()))
    else:
        rep.append('- K6 没有触发安全线')
    return fails, rep


if __name__ == '__main__':
    import argparse
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import checks_common as CC
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('project', nargs='?', default='.', help='项目目录（默认当前目录）')
    ap.add_argument('--mode', choices=('safe', 'free'), help='默认读项目里 MODE 文件（现在只影响报告措辞，必过档两种模式都拦）')
    ap.add_argument('--json', action='store_true', help='只把结构化结果写进 out/camera_check.json（markdown 报告照写）')
    a = ap.parse_args()
    P, mode = a.project, a.mode
    if not mode:
        mf = os.path.join(P, 'MODE'); mode = (open(mf, encoding='utf-8').read().split() or ['safe'])[0] if os.path.exists(mf) else 'safe'
    fails, rep = check(P)
    by = {}
    for f in fails:
        rid, rest = f.split()[0], f.split(None, 1)[1] if len(f.split()) > 1 else ''
        by.setdefault(rid, []).append(rest)
    NAMES = {'K1': '运镜不单一', 'K2': '相邻镜头换运镜', 'K3': '段落呼吸', 'K4': '炸点有冲击', 'K5': '定机位要有理由', 'K6': '安全线已自动修'}
    RULES = []
    for rid in ('K1', 'K2', 'K3', 'K4', 'K5', 'K6'):
        lines = [x[2:].strip() for x in rep if x.startswith('- ' + rid)]
        ok = not by.get(rid)
        RULES.append({'rule': rid, 'name': NAMES[rid], 'ok': ok, 'detail': '；'.join(by.get(rid, [])) or ('；'.join(lines[-2:]) or '通过')})
    for r in RULES: r.setdefault('tier', CC.tier(r['rule']))
    tiers = {'must': 0, 'auto': 0, 'warn': 0}
    for r in RULES:
        if not r['ok']: tiers[r['tier']] += 1
    out = [f"# camera check（运镜关）\n\nmode: **{'safe' if mode != 'free' else 'free'}**；没过：必过 {tiers['must']}，警告 {tiers['warn']}\n"] + rep
    out += ['', '## gates', '', '| 关 | 结果 | 说明 |', '|---|---|---|']
    out += ['| %s %s | %s | %s |' % (r['rule'], r['name'], ('**FAIL·%s**' % CC.CN[r['tier']]) if not r['ok'] else 'PASS', r['detail'][:200]) for r in RULES]
    out += ['', f"**{'PASS' if tiers['must'] == 0 else 'FAIL'}**（必过档全过即 PASS，两种模式都拦）"]
    os.makedirs(os.path.join(P, 'out'), exist_ok=True)
    open(os.path.join(P, 'out/camera_check.md'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    p = CC.dump_json('camera_check', RULES, os.path.join(P, 'out'))
    if not a.json:
        print('\n'.join(f"| {r['rule']} | {'PASS' if r['ok'] else 'FAIL·' + CC.CN[r['tier']]} | {r['detail'][:120]} |" for r in RULES))
        print(f"-> out/camera_check.md, {p}  {'PASS' if tiers['must'] == 0 else f'必过 {tiers['must']} 项 FAIL'}")
    sys.exit(CC.exit_code(RULES))

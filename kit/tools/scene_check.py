#!/usr/bin/env python3
"""场景关：全片按「场景」切开，每个场景 10–20 秒左右，相邻场景看得出换了。由 python tools/run.py scenes / video 调用。

场景 = 一套布景：一个地点 + 一种光色（同一条街的白天和夜里算两个场景）。场景表写在 plan.json 的 scenes 里：
  {"id": "A", "f0": 0, "f1": 312, "world": "雨天方块小镇", "look": "灰蓝阴天"}      帧号是全曲帧号，含头不含尾
可选：  "why": "..."        这个场景故意短于 8 秒（快剪蒙太奇、片头字卡），写原因
        "same_as": "A"      故意回到前面某个场景（首尾呼应），C3 不拿它和 A 比画面，但它和前后相邻的场景照样要不一样

  C1 场景表完整        scenes 从 start 连到 end，不重叠、不留空                【自动修：补空、并对齐 start/end】
  C2 长度              每个场景 8–24 秒（目标 10–20 秒）；全片第一个和最后一个场景可以短到 4 秒；
                       写了 why 的可以短于 8 秒；任何场景都不能超过 24 秒            【警告】
  C3 看得出换了        相邻两个场景的 world 或 look 至少有一个不同；有成片时再量画面，
                       相邻场景的颜色分布不能几乎一样                            【警告】
  C4 换场景有转场      每条场景边界 ±2 帧内有一个登记过的转场（cuts 的 c、incamera 的 key）或交接
                       【自动修：吸附到 ±2 帧内最近的转场关键帧】
报告 → out/scene_check.md，结构化结果 → out/scene_check.json（report.py 汇总）。
用法：python tools/scene_check.py [成片.mp4] [--json]"""
import json, os, subprocess, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checks_common as CC
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('video', nargs='?', help='成片或检查小样.mp4（不给就只查文字层）')
    ap.add_argument('--json', action='store_true', help='只把结构化结果写进 out/scene_check.json（markdown 报告照写）')
    a = ap.parse_args()

    FPS = 24
    MIN_S, MAX_S, EDGE_MIN_S = 8.0, 24.0, 4.0
    SIM_MAX = 0.65          # 相邻场景颜色分布的相似度（直方图交集，0–1）超过它就算「几乎一样」。
                            # 实测（接力 S1）：同一场景换机位 0.74–0.87，真换了场景 0.29–0.46
    P = json.load(open('plan.json', encoding='utf-8'))
    S0, S1 = P['start'], P['end']
    scenes = sorted(P.get('scenes') or [], key=lambda s: s['f0'])
    video = a.video
    f1, f2, f3, f4 = [], [], [], []      # 各规则的 FAIL 明细
    notes, rows = [], []
    sec = lambda f: f / FPS

    # ---------- C1 ----------
    if not scenes:
        f1.append('plan.json 里没有 scenes：先在 TREATMENT 里把全片分成场景，再写进 scenes')
    else:
        if scenes[0]['f0'] != S0: f1.append(f"第一个场景 {scenes[0]['id']} 应该从第 {S0} 帧开始（现在是 {scenes[0]['f0']}）")
        if scenes[-1]['f1'] != S1: f1.append(f"最后一个场景 {scenes[-1]['id']} 应该到第 {S1} 帧结束（现在是 {scenes[-1]['f1']}）")
        for a_, b_ in zip(scenes, scenes[1:]):
            if a_['f1'] != b_['f0']: f1.append(f"{a_['id']}（到 {a_['f1']}）和 {b_['id']}（从 {b_['f0']}）之间{'重叠' if a_['f1'] > b_['f0'] else '留了空'}")

    # ---------- C2 ----------
    for i, s in enumerate(scenes):
        L = sec(s['f1'] - s['f0']); edge = i in (0, len(scenes) - 1)
        lo = EDGE_MIN_S if edge else (0.0 if s.get('why') else MIN_S)
        ok = lo <= L <= MAX_S
        if not ok: f2.append(f"场景 {s['id']} 长 {L:.1f} 秒，要在 {lo:g}–{MAX_S:g} 秒之间" + ('（太长：拆成两个场景，换地点或换光色）' if L > MAX_S else '（太短：并进相邻场景，或者在 why 里写清楚为什么要这么短）'))
        rows.append([s['id'], f"{sec(s['f0'] - S0):.1f}–{sec(s['f1'] - S0):.1f}", f'{L:.1f}', s.get('world', ''), s.get('look', ''), 'ok' if ok else 'FAIL'])

    # ---------- C3（文字） ----------
    for a_, b_ in zip(scenes, scenes[1:]):
        if a_.get('world', '').strip() == b_.get('world', '').strip() and a_.get('look', '').strip() == b_.get('look', '').strip():
            f3.append(f"{a_['id']} 和 {b_['id']} 的 world、look 写得一样：相邻场景要换地点或换光色")

    # ---------- C4 ----------
    keys = [c['c'] for c in P.get('cuts', [])] + [c['key'] for c in P.get('incamera', [])]
    keys += [h[k] for h in P.get('handoffs', []) for k in ('f0', 'f1', 'key') if k in h]
    for a_, b_ in zip(scenes, scenes[1:]):
        if not any(abs(k - b_['f0']) <= 2 for k in keys):
            f4.append(f"{a_['id']}→{b_['id']}（第 {b_['f0']} 帧）附近没有登记的转场：把场景边界放在一个 cuts / incamera 的关键帧上")

    # ---------- C3（画面） ----------
    sims = []
    if video and len(scenes) > 1 and os.path.exists(video):
        W, H = 96, 54
        raw = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', video, '-vf', f'fps=4,scale={W}:{H}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                             capture_output=True, check=True).stdout
        fr = np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3)
        def sig(s):      # 场景中段（去掉头尾各 0.75 秒的转场）的颜色分布：RGB 各 6 档的 3D 直方图
            t0, t1 = sec(s['f0'] - S0) + 0.75, sec(s['f1'] - S0) - 0.75
            idx = [i for i in range(len(fr)) if t0 <= i / 4 < t1] or [min(len(fr) - 1, int((sec(s['f0'] + s['f1']) / 2 - sec(S0)) * 4))]
            q = (fr[idx].reshape(-1, 3) // 43).astype(int)
            h = np.bincount(q[:, 0] * 36 + q[:, 1] * 6 + q[:, 2], minlength=216).astype(float)
            return h / h.sum()
        sg = {s['id']: sig(s) for s in scenes}
        for a_, b_ in zip(scenes, scenes[1:]):
            sim = float(np.minimum(sg[a_['id']], sg[b_['id']]).sum()); sims.append((a_['id'], b_['id'], sim))
            if sim > SIM_MAX: f3.append(f"{a_['id']}→{b_['id']} 画面颜色分布 {sim:.2f} 相似（上限 {SIM_MAX}）：看起来还是同一个场景，换光色、换地点或换主色")
        for s in scenes:
            if s.get('same_as') in sg: notes.append(f"{s['id']} 回到 {s['same_as']}：相似度 {float(np.minimum(sg[s['id']], sg[s['same_as']]).sum()):.2f}（只记录，不拦）")
    elif not video:
        notes.append('没有成片，C3 只查了文字；跑 python tools/run.py video 时会量画面')

    # ---------- 结构化结果 + 报告 ----------
    RULES = [
        {'rule': 'C1', 'name': '场景表完整', 'ok': not f1, 'detail': '；'.join(f1) or 'scenes 从 start 连到 end，不重叠不留空'},
        {'rule': 'C2', 'name': '场景长度', 'ok': not f2, 'detail': '；'.join(f2) or '都在 8–24 秒（首尾可短到 4 秒）'},
        {'rule': 'C3', 'name': '看得出换了', 'ok': not f3, 'detail': '；'.join(f3) or ('相邻场景 world/look、画面分布都不一样' if sims else '相邻场景 world/look 不一样' + ('；' + notes[0] if not video and notes else ''))},
        {'rule': 'C4', 'name': '换场景有转场', 'ok': not f4, 'detail': '；'.join(f4) or f'{len(scenes) - 1} 条边界 ±2 帧内都有登记的转场/交接'},
    ]
    for r in RULES: r.setdefault('tier', CC.tier(r['rule']))
    tiers = {'must': 0, 'auto': 0, 'warn': 0}
    for r in RULES:
        if not r['ok']: tiers[r['tier']] += 1
    L = [f"# scene check（场景关）\n\n{len(scenes)} 个场景，全片 {sec(S1 - S0):.1f} 秒；没过：必过 {tiers['must']}，自动修 {tiers['auto']}，警告 {tiers['warn']}\n",
         '| 场景 | 秒（本片） | 长度 | world | look | 长度 ok |', '|---|---|---|---|---|---|']
    L += ['| ' + ' | '.join(r) + ' |' for r in rows]
    if sims: L += ['', '相邻场景画面相似度（越低越不一样，上限 %.2f）：' % SIM_MAX] + [f'- {a_}→{b_}: {s:.2f}' for a_, b_, s in sims]
    if notes: L += [''] + [f'- {n}' for n in notes]
    L += ['', '## gates', '', '| 关 | 结果 | 说明 |', '|---|---|---|']
    L += ['| %s %s | %s | %s |' % (r['rule'], r['name'], ('**FAIL·%s**' % CC.CN[r['tier']]) if not r['ok'] else 'PASS', r['detail']) for r in RULES]
    L += ['', f"**{'PASS' if tiers['must'] == 0 else 'FAIL'}**（必过档全过即 PASS；自动修档跑 python tools/run.py check --fix）"]
    os.makedirs('out', exist_ok=True)
    open('out/scene_check.md', 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    p = CC.dump_json('scene_check', RULES)
    if not a.json:
        print('\n'.join(f"| {r['rule']} | {'PASS' if r['ok'] else 'FAIL·' + CC.CN[r['tier']]} | {r['detail']} |" for r in RULES))
        print(f'-> out/scene_check.md, {p}  {"PASS" if tiers["must"] == 0 else f"必过 {tiers['must']} 项 FAIL"}')
    sys.exit(CC.exit_code(RULES))

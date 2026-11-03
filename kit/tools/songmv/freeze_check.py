#!/usr/bin/env python3
"""Find frozen stretches: compares frames 1/4 s apart; any stretch of >= 1 s where the picture barely changes is reported.
Usage: python3 tools/freeze_check.py out/video.mp4 [threshold=1.2] [--json]
Threshold is mean absolute pixel difference (0-255) on a 160x90 grey copy. Grain alone gives ~0.5-1; real motion is 2+.
FREEZE 是必过关：有 ≥ 1 秒的冻结就退出码 3。报告 → out/freeze_check.md + out/freeze_check.json（report.py 汇总）。"""
import os, sys, subprocess
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import checks_common as CC
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')

args = [a for a in sys.argv[1:] if a != '--json']
JSON_ONLY = '--json' in sys.argv
src = args[0]; th = float(args[1]) if len(args) > 1 else 1.2
raw = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', src, '-vf', 'fps=4,scale=160:90,format=gray', '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
fr = np.frombuffer(raw, np.uint8).reshape(-1, 90, 160).astype(np.float32)
d = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))
bad, start = [], None
for i, v in enumerate(list(d) + [99]):
    if v < th and start is None: start = i
    if v >= th and start is not None:
        if i - start >= 4: bad.append((start / 4, i / 4, float(d[start:i].mean())))
        start = None
det = '、'.join(f'{a:.2f}–{b:.2f}s（mean diff {m:.2f}）' for a, b, m in bad[:8]) + ('…' if len(bad) > 8 else '')
RULES = [{'rule': 'FREEZE', 'name': '画面不冻结', 'ok': not bad,
          'detail': f'{len(bad)} 段 ≥ 1 秒几乎不动：{det}（让画面里有东西一直动：粒子、光点、呼吸下蹲、镜头慢推）' if bad
          else f'没有 ≥ 1 秒的冻结（帧差中位 {np.median(d):.2f}）'}]
for r in RULES: r.setdefault('tier', CC.tier(r['rule']))
outd = os.path.dirname(os.path.abspath(src)) or '.'
lines = [f'# freeze check\n', f'frames {len(fr)}  median diff {np.median(d):.2f}  min {d.min():.2f}',
         '', '| 关 | 结果 | 说明 |', '|---|---|---|',
         f"| FREEZE | {'PASS' if not bad else '**FAIL·必过**'} | {RULES[0]['detail']} |", '']
os.makedirs(outd, exist_ok=True)
open(os.path.join(outd, 'freeze_check.md'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
p = CC.dump_json('freeze_check', RULES, outd)
if not JSON_ONLY:
    print(lines[1])
    print('FROZEN stretches:' if bad else 'no frozen stretch >= 1 s')
    for a, b, m in bad: print(f'  {a:6.2f}s - {b:6.2f}s  mean diff {m:.2f}')
    print(f"-> {os.path.join(outd, 'freeze_check.md')}, {p}  {'PASS' if not bad else 'FREEZE FAIL'}")
sys.exit(CC.exit_code(RULES))

#!/usr/bin/env python3
"""把新生成的舞步（或别的新动作）帧并进已有角色：按角色原来的画布、脚底基线、中线、站立身高缩放对齐，
写进 characters/<名字>/frames/<动作>/NN.png，并把这些动作合并进角色的 frames.json。
用法：python scripts/add_moves.py <新帧目录（frames.json + frames/）> characters/<名字> [--acts dance_arms,dance_clap]
  默认并入新项目里所有 dance_ 开头的动作；已有同名动作会被覆盖（先备份成 frames.json.bak）。
  新帧的站立身高按新帧 frames.json 的 stand_h 对齐到角色的 stand_h，所以两边都要是「全身、同一个人」。"""
import argparse, json, os, shutil, sys
from PIL import Image
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ap = argparse.ArgumentParser(); ap.add_argument('src'); ap.add_argument('char'); ap.add_argument('--acts')
A = ap.parse_args()
sm = json.load(open(os.path.join(A.src, 'frames.json'), encoding='utf-8'))
cp = os.path.join(A.char, 'frames.json'); cm = json.load(open(cp, encoding='utf-8'))
acts = A.acts.split(',') if A.acts else [a for a in sm['actions'] if a.startswith('dance_')]
if not acts: sys.exit(f'{A.src}/frames.json 里没有 dance_ 开头的动作（用 --acts 指定）')
k = cm['stand_h'] / sm['stand_h']; S = int(cm['canvas'])
shutil.copy(cp, cp + '.bak')
for a in acts:
    if a not in sm['actions']: sys.exit(f'新项目里没有动作 {a}')
    src = sm['actions'][a]; frames = src['frames'] if isinstance(src, dict) else src
    od = os.path.join(A.char, 'frames', a); os.makedirs(od, exist_ok=True)
    out = []
    for n, fr in enumerate(frames, 1):
        im = Image.open(os.path.join(A.src, fr['file'])).convert('RGBA')
        im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
        cv = Image.new('RGBA', (S, S), (0, 0, 0, 0))
        cv.alpha_composite(im, (round(cm['center_x'] - sm['center_x'] * k), round(cm['baseline_y'] - sm['baseline_y'] * k)))   # 中线、脚底基线对齐
        name = f'{n:02d}.png'; cv.save(os.path.join(od, name))
        out.append({**{x: y for x, y in fr.items() if x != 'file'}, 'file': f'frames/{a}/{name}', 'merged_from': os.path.abspath(A.src)})
    cm['actions'][a] = {**({x: y for x, y in src.items() if x != 'frames'} if isinstance(src, dict) else {}), 'frames': out}
    print(f'{a}: {len(out)} 帧 -> {od}（缩放 {k:.3f}）')
json.dump(cm, open(cp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f'已合并进 {cp}（旧的在 frames.json.bak）。建项目时 keypoints.py 会给新动作算关键点；舞句库的槽位会先用它们。')

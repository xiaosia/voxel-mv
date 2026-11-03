#!/usr/bin/env python3
"""俯视布局图：check --layout 的产物。每个镜头一张 out/layout/<镜头 id>.png：
碰撞体灰色（cyl 画圆）、角色彩色圆点+名字、被推开的画绿箭头（from→to）、STUCK 红圈+原因。
输入 out/voxel.json（要带 colliders：voxel_dump.mjs --layout 才会导）。纯画图，不判关。
usage: python layout_map.py [out/voxel.json] [--out-dir out/layout]"""
import json, os, sys
from PIL import Image, ImageDraw
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace')

vox = json.load(open(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else 'out/voxel.json', encoding='utf-8'))
outdir = 'out/layout'
if '--out-dir' in sys.argv: outdir = sys.argv[sys.argv.index('--out-dir') + 1]
os.makedirs(outdir, exist_ok=True)

shots = {}
for fr in vox.get('frames', []):
    shots.setdefault(fr.get('shot') or 'S00', []).append(fr)

PALETTE = ['#E4572E', '#2E86AB', '#7CB518', '#B5179E', '#F4A259', '#5BC0BE', '#9B5DE5', '#F15BB5']
SCALE = 90   # 每米多少像素

def draw(shot, sid):
    mid = shot[len(shot) // 2]
    cols = mid.get('colliders') or []
    chars = mid.get('chars') or []
    xs, zs = [], []
    for c in cols:
        b = c['box']; xs += [b['x0'], b['x1']]; zs += [b['z0'], b['z1']]
    for ch in chars:
        x, y, z = ch['pos']; xs.append(x); zs.append(z)
    if not xs: return None
    pad = 1.5
    x0, x1, z0, z1 = min(xs) - pad, max(xs) + pad, min(zs) - pad, max(zs) + pad
    W, H = int((x1 - x0) * SCALE), int((z1 - z0) * SCALE)
    W, H = max(W, 320), max(H, 240)
    k = min(W / (x1 - x0), H / (z1 - z0))
    px = lambda x: (x - x0) * k + (W - (x1 - x0) * k) / 2
    pz = lambda z: (z - z0) * k + (H - (z1 - z0) * k) / 2
    img = Image.new('RGB', (W, H), '#141414')
    d = ImageDraw.Draw(img)
    for c in cols:
        b = c['box']
        if c.get('cyl'):
            cx, cz, cr = c['cyl']['cx'], c['cyl']['cz'], c['cyl']['cr']
            d.ellipse([px(cx - cr), pz(cz - cr), px(cx + cr), pz(cz + cr)], outline='#8a8a8a', width=2)
        else:
            d.rectangle([px(b['x0']), pz(b['z0']), px(b['x1']), pz(b['z1'])], outline='#8a8a8a', width=2)
        d.text((px(c['box']['x0']) + 3, pz(c['box']['z0']) + 2), c['id'], fill='#8a8a8a')
    stuck = {}
    for fr in shot:
        for s in fr.get('stuck') or []: stuck.setdefault(s['who'], s)
    colors = {ch['id']: PALETTE[i % len(PALETTE)] for i, ch in enumerate(chars)}
    for fr in shot:   # nudge 箭头（取中间帧那次的）
        if fr is not mid: continue
        for n in fr.get('nudges') or []:
            f, t = n.get('from'), n.get('to')
            if not t: continue
            a = f or t
            d.line([px(a[0]), pz(a[1]), px(t[0]), pz(t[1])], fill='#3ddc84', width=2)
            if f: d.ellipse([px(f[0]) - 3, pz(f[1]) - 3, px(f[0]) + 3, pz(f[1]) + 3], outline='#3ddc84', width=2)
    for ch in chars:
        x, y, z = ch['pos']; col = colors.get(ch['id'], '#fff')
        d.ellipse([px(x - 0.3), pz(z - 0.3), px(x + 0.3), pz(z + 0.3)], fill=col)
        d.text((px(x) + 6, pz(z) - 6), ch['id'], fill=col)
        if ch['id'] in stuck:
            s = stuck[ch['id']]
            d.ellipse([px(x - 0.5), pz(z - 0.5), px(x + 0.5), pz(z + 0.5)], outline='#ff2d2d', width=3)
            d.text((px(x) + 6, pz(z) + 8), f"STUCK: {s.get('reason', '')}", fill='#ff2d2d')
    d.text((8, 8), f'{sid}  第 {mid.get("f")} 帧  灰=碰撞体 绿=被推 红=STUCK', fill='#cccccc')
    p = os.path.join(outdir, f'{sid}.png')
    img.save(p)
    return p, len(cols), len(chars), sum(1 for _ in stuck)

made = []
for sid, frs in sorted(shots.items()):
    r = draw(frs, sid)
    if r: made.append((sid, *r))
    print(f'{sid}: 碰撞体 {r[1]}、角色 {r[2]}、STUCK {r[3]} → {r[0]}' if r else f'{sid}: 没有可画的帧')
print(f'\n{len(made)} 张俯视图 → {outdir}' + ('' if not any(m[4] for m in made) else '（红圈的镜头去把站位或碰撞配置改掉）'))

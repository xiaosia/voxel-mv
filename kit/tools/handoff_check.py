#!/usr/bin/env python3
"""交接自查（交接卡 T1–T6 + 片头片尾 + 成片规格）。
用法：python tools/handoff_check.py --segment S3 --video out/S3_Gemini.mp4 [--project .]
读：plan.json（段起止帧、交接）、out/probe.json（tools/run.py 的动作关会生成；T3、T4 要用）、shots.js（是否还是占位场景）。
写：out/checks/handoff_check.md、out/handoff.json（切点前后各 6 帧的 probe 记录和测量值）、out/first3/、out/last3/。
全部 PASS 退出码 0，有 FAIL 退出码 1。"""
import argparse, json, os, subprocess, sys
import numpy as np
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ap = argparse.ArgumentParser()
ap.add_argument('--segment', required=True); ap.add_argument('--video', required=True); ap.add_argument('--project', default='.')
A = ap.parse_args()
P = os.path.abspath(A.project)
plan = json.load(open(os.path.join(P, 'plan.json'), encoding='utf-8'))
START, END = plan['start'], plan['end']
N = END - START
rows, data, fails = [], {'segment': A.segment, 'start': START, 'end': END, 'checks': {}}, 0

def res(name, ok, detail):
    global fails
    rows.append(f'| {name} | {"PASS" if ok else "**FAIL**"} | {detail} |')
    data['checks'][name] = {'pass': bool(ok), 'detail': detail}
    if not ok: fails += 1

# ---------- 规格 ----------
pr = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames', '-show_entries',
                                'stream=codec_name,width,height,pix_fmt,r_frame_rate,nb_read_frames,color_space,color_range', '-of', 'json', A.video],
                               capture_output=True, text=True, check=True).stdout)['streams'][0]
nf = int(pr.get('nb_read_frames', 0))
res('帧数', nf == N, f'{nf}（要求 {N}）')
res('尺寸', (pr['width'], pr['height']) == (1920, 1080), f"{pr['width']}×{pr['height']}")
res('帧率', pr['r_frame_rate'] in ('24/1', '24'), pr['r_frame_rate'])
res('编码', pr['codec_name'] == 'h264' and pr['pix_fmt'] == 'yuv420p', f"{pr['codec_name']} {pr['pix_fmt']}")
src = open(os.path.join(P, 'shots.js'), encoding='utf-8').read()
res('不是占位场景', 'placeholder: true' not in src, '已换成自己的场景' if 'placeholder: true' not in src else 'shots.js 还是占位场景（R.run 里有 placeholder: true）')

# ---------- 取帧 ----------
_cache = {}
def frame(k):
    """本段第 k 帧（从 0 数，负数从末尾数）→ RGB uint8 1920×1080×3"""
    k = k % N
    if k not in _cache:
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', A.video, '-vf', f'select=eq(n\\,{k})', '-fps_mode', 'passthrough', '-frames:v', '1',
                              '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True).stdout
        _cache[k] = np.frombuffer(raw, np.uint8).reshape(1080, 1920, 3)
    return _cache[k]
def lab(rgb):
    c = rgb.astype(np.float64) / 255
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)
def solid_share(img, hexcol):
    target = lab(np.array([[[int(hexcol[i:i + 2], 16) for i in (1, 3, 5)]]], np.uint8))[0, 0]
    d = np.linalg.norm(lab(img[::4, ::4]) - target, axis=-1)
    return float((d <= 10).mean())
def luma(img): return img[..., 0] * 0.299 + img[..., 1] * 0.587 + img[..., 2] * 0.114
def bright_centroid(img):
    """圆窗的圆心：最宽那一行的高度、左右边的中点（只看上面 75%，避开字幕）"""
    y = luma(img[::4, ::4]); m = y > 24; m[int(m.shape[0] * 0.75):] = False
    if m.sum() < 50: return None
    rows = [(i, np.nonzero(r)[0]) for i, r in enumerate(m) if r.any()]
    span = np.array([x.max() - x.min() for _, x in rows]); best = [rows[j] for j in np.nonzero(span >= span.max() * 0.99)[0]]
    cy = np.mean([i for i, _ in best]); cx = np.mean([(x.min() + x.max()) / 2 for _, x in best])
    return float(cx * 4 / 1920), float(cy * 4 / 1080)
def shift_x(a, b):
    """b 相对 a 的横向位移（像素，负数 = 内容往左走）：上面 75% 画面（避开字幕）按列求平均亮度，再互相关"""
    h = int(a.shape[0] * 0.75)
    pa, pb = luma(a[:h]).mean(0), luma(b[:h]).mean(0)
    pa, pb = pa - pa.mean(), pb - pb.mean()
    best, bd = -1e18, 0
    for d in range(-640, 641, 2):
        x, y = (pa[:len(pa) - d], pb[d:]) if d >= 0 else (pa[-d:], pb[:len(pb) + d])
        c = float((x * y).mean())
        if c > best: best, bd = c, d
    return bd
def hblur_ratio(img):
    g = luma(img[:int(img.shape[0] * 0.75):2, ::2]).astype(np.float64)    # 不看下面 25%（字幕不模糊）
    gx = np.percentile(np.abs(np.diff(g, axis=1)), 99.9); gy = np.percentile(np.abs(np.diff(g, axis=0)), 99.9)   # 最强的边：横向模糊后竖边被抹平
    return float(gx / max(gy, 1e-6))

# ---------- probe（角色在屏幕上的位置）----------
probe = None
pp = os.path.join(P, 'out/probe.json')
if os.path.exists(pp): probe = json.load(open(pp, encoding='utf-8'))['frames']
def who(k, name):
    if probe is None: return None
    k = k % N
    for c in probe[k]:
        if c['id'] == name: return c
    return None
def rec(k0, k1, name):
    return [{'frame': START + (k % N), 'who': who(k, name)} for k in range(k0, k1)]

# ---------- 交接 ----------
os.makedirs(os.path.join(P, 'out/checks'), exist_ok=True)
for h in plan['handoffs']:
    side, card = h['side'], h['card']
    tag = f'{card} {"入场" if side == "in" else "出场"}'
    if card == 'T1':
        ks = [0, 1] if side == 'in' else [-2, -1]
        sh = [solid_share(frame(k), '#FFF4E0') for k in ks]
        res(tag, min(sh) >= 0.95, '纯色 #FFF4E0 占比 ' + '、'.join(f'{s:.1%}' for s in sh) + '（要求 ≥ 95%）')
    elif card == 'T2':
        ks = [0, 1, 2] if side == 'in' else [-3, -2, -1]
        mx = [float(np.percentile(luma(frame(k)), 99.5)) for k in ks]
        res(tag + ' 全黑', max(mx) <= 16, '亮度（99.5% 分位）' + '、'.join(f'{m:.0f}' for m in mx) + '（要求 ≤ 16）')
        kc = 6 if side == 'in' else -7
        c = bright_centroid(frame(kc))
        ok = c is not None and abs(c[0] - 0.5) <= 0.05 and abs(c[1] - 0.4) <= 0.06
        res(tag + ' 圆心', ok, f'第 {START + kc % N} 帧亮区中心 ' + (f'({c[0]:.1%}, {c[1]:.1%})' if c else '无') + '（要求 (50%, 40%) 附近）')
    elif card == 'T3':
        if probe is None: res(tag, False, '没有 out/probe.json：先跑 python tools/run.py act'); continue
        if side == 'out':
            z = who(-1, 'zai'); ok = z is None or z['xmin'] > 1.0
            res(tag + ' 最后一帧出画', ok, '最后一帧 ZAI ' + ('不在画面里' if z is None else f"最左点 x={z['xmin']:.1%}（要求 > 100%）"))
            k = -8
        else:
            z = who(0, 'zai'); ok = z is not None and z['xmin'] < 0 and 0 < z['xmax'] < 0.12
            res(tag + ' 第一帧刚入画', ok, '第一帧 ZAI ' + ('不在画面里' if z is None else f"最左 {z['xmin']:.1%}、最右 {z['xmax']:.1%}（要求最左 < 0、最右 0–12%）"))
            k = 8
        z = who(k, 'zai')
        ok = z is not None and abs(z['h'] - 0.40) <= 0.04 and abs(z['base'][1] - 0.85) <= 0.02 and z['act'] == 'walk_side'
        res(tag + ' 大小和脚底', ok, '第 %d 帧 ' % (START + k % N) + ('ZAI 不在画面里' if z is None else f"身高 {z['h']:.1%}（40%±4%）脚底 {z['base'][1]:.1%}（85%±2%）动作 {z['act']}"))
        data[card] = rec(-6, 0, 'zai') if side == 'out' else rec(0, 6, 'zai')
    elif card == 'T4':
        if probe is None: res(tag, False, '没有 out/probe.json：先跑 python tools/run.py act'); continue
        name = 'zai' if side == 'out' else 'qwen'
        ks = range(-10, 0) if side == 'out' else range(0, 10)
        bad = []
        for k in ks:
            c = who(k, name)
            if c is None or c['act'] != 'look_up' or c['i'] != 3 or abs(c['base'][0] - 0.5) > 0.03 or abs(c['base'][1] - 0.85) > 0.02 or abs(c['h'] - 0.45) > 0.045:
                bad.append(START + k % N)
        c = who(-1 if side == 'out' else 0, name)
        res(tag, not bad, ('全部对上' if not bad else f'对不上的帧：{bad}') + (f"；切点帧 中线 {c['base'][0]:.1%} 脚底 {c['base'][1]:.1%} 身高 {c['h']:.1%} 动作 {c['act']} 第 {c['i'] + 1} 帧" if c else ''))
        data[card] = [{'frame': START + k % N, 'who': who(k, name)} for k in ks]
    elif card == 'T5':
        ks = [0, 1] if side == 'in' else [-2, -1]
        sh = [solid_share(frame(k), '#1F3B66') for k in ks]
        res(tag + ' 鲸身满屏', min(sh) >= 0.95, '鲸身色 #1F3B66 占比 ' + '、'.join(f'{s:.1%}' for s in sh) + '（要求 ≥ 95%）')
        k = 10 if side == 'in' else -12
        img = frame(k); t = lab(np.array([[[0x1F, 0x3B, 0x66]]], np.uint8))[0, 0]
        m = np.linalg.norm(lab(img[::8, ::8]) - t, axis=-1) <= 12
        L, R = m[:, :m.shape[1] // 2].mean(), m[:, m.shape[1] // 2:].mean()
        ok = (R > L) if side == 'in' else (L > R)
        res(tag + ' 向右游', ok, f'第 {START + k % N} 帧鲸身在左半 {L:.0%}、右半 {R:.0%}（{"入场：鲸往右游走，右边多" if side == "in" else "出场：鲸从左边游进来，左边多"}）')
    elif card == 'T6':
        ks = [0, 1, 2] if side == 'in' else [-3, -2, -1]
        rr = [hblur_ratio(frame(k)) for k in ks]
        res(tag + ' 横向强模糊', max(rr) <= 0.35, '横向/纵向梯度比 ' + '、'.join(f'{r:.2f}' for r in rr) + '（最强横向边 / 最强纵向边，≤ 0.35 = 竖边被横向抹开了）')
        k0, k1 = (0, 3) if side == 'in' else (-10, -7)          # 出场：甩镜刚开始、画面还有细节的那几帧
        moved = []                                                # 先看角色（probe）：画面里的角色往哪边走
        if probe is not None:
            for c in (probe[k0 % N] if k0 % N < len(probe) else []):
                d = who(k1, c['id'])
                if d is not None and 0 <= c['base'][0] <= 1: moved.append((d['base'][0] - c['base'][0]) * 1920)
        if moved: dx, how = int(round(float(np.median(moved)))), '角色'
        else: dx, how = shift_x(frame(k0), frame(k1)), '画面'
        res(tag + ' 内容往左', dx < 0, f'第 {START + k0 % N}→{START + k1 % N} 帧{how}位移 {dx:+d} 像素（负数 = 往左）')
        data[card] = {'mean_luma': [float(luma(frame(k)).mean()) for k in ks]}
        rows.append(f'| {tag} 平均亮度 | 记录 | ' + '、'.join(f'{x:.0f}' for x in data[card]['mean_luma']) + '（拼接时和另一边比，差 ≤ 15%）|')
    elif card == 'END':
        mx = float(np.percentile(luma(frame(-1)), 99.5))
        res('片尾淡出到黑', mx <= 16, f'最后一帧亮度 {mx:.0f}（要求 ≤ 16）')

# ---------- 头尾 3 帧 ----------
from PIL import Image
for d, ks in (('first3', [0, 1, 2]), ('last3', [-3, -2, -1])):
    os.makedirs(os.path.join(P, 'out', d), exist_ok=True)
    for k in ks: Image.fromarray(frame(k)).save(os.path.join(P, 'out', d, f'{START + k % N:04d}.png'))

json.dump(data, open(os.path.join(P, 'out/handoff.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
md = [f'# 交接自查 {A.segment}（{os.path.basename(A.video)}）', '', '| 项 | 结果 | 详情 |', '|---|---|---|'] + rows
md += ['', '**全部 PASS**' if not fails else f'**{fails} 项 FAIL**：按详情改到 PASS 再交付。']
open(os.path.join(P, 'out/checks/handoff_check.md'), 'w', encoding='utf-8').write('\n'.join(md) + '\n')
print('\n'.join(md))
sys.exit(1 if fails else 0)

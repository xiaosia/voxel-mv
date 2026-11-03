#!/usr/bin/env python3
"""歌曲结构识别：把一首歌切成「前奏 / 主歌 / 导歌 / 副歌 / 间奏 / 桥段 / 尾奏」（电音还有「蓄力 / 炸点」），
每段给起止时间、小节、能量、第几遍、可信度和判断依据 → structure.json + structure.md。

看四样东西：
  1. 歌词重复：同样的几句连着出现两遍以上 = 副歌或导歌（重复且能量最高的那组是副歌，紧挨在副歌前面的另一组是导歌）
  2. 人声有无：没人唱的地方是前奏、间奏、尾奏（按歌词时间或 vocal_pieces 算；两样都没有时只能按位置和能量猜）
  3. 能量：每小节响度（audio.timeline.json 的 energy_per_bar）
  4. 旋律 / 和声相似度（给了 --audio 才算）：没歌词时靠它找重复段；有歌词时用来分辨「主歌 2」和「桥段」
只要 Python 3 + numpy（给 --audio 时还要 ffmpeg）。

用法：
  python song_structure.py --timeline audio.timeline.json [--lyrics lyrics.lrc|lines.json] [--audio song.mp3] [--vocal lyrics_align.json] --out 目录 [--force]
  --vocal  有人声的片段（align_lyrics.py 产出的 lyrics_align.json 里的 vocal_pieces）；不给时自动找歌词同目录的 lyrics_align.json
歌词支持：普通 LRC、逐字 LRC（句尾取最后一个字的时间）、JSON（列表或 {"lines": [...]}，每项 {t0|start|t, t1|end, text}）。

人工校对：打开 structure.json 改 parts 里的 label（intro verse pre-chorus chorus interlude bridge outro build drop）
或 t0 / t1，把 "checked" 改成 true。之后再跑本脚本不会覆盖它（新结果写到 structure.auto.json，可以对照），
用 --force 才覆盖。也可以 python song_structure.py --validate structure.json 只检查改过的文件（首尾相接、标签合法）。
结果是自动估的：副歌、前奏、间奏、尾奏一般准；主歌 / 导歌 / 桥段的分界最容易错，写 TREATMENT 前对着歌听一遍。"""
import argparse, difflib, json, os, re, subprocess, sys
import numpy as np
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')

LABELS = {'intro': '前奏', 'verse': '主歌', 'pre-chorus': '导歌', 'chorus': '副歌', 'interlude': '间奏', 'bridge': '桥段',
          'outro': '尾奏', 'build': '蓄力', 'drop': '炸点'}
HOWTO = {   # structure.md 里每种段落的一句拍法提示（详细的在 SKILL.md「歌曲由什么组成」）
    'intro': '钩子：第一眼抓人，悬念吊到人声进来那一拍兑现',
    'verse': '收着：讲故事、交代人物和世界，景别偏中近，动作小而准',
    'pre-chorus': '往上推：节奏加快、镜头推近或加速，最后一拍憋住给副歌',
    'chorus': '放开：全片最满最亮，大动作、大景别变化、最强转场；每遍副歌要有变化，最后一遍最大',
    'interlude': '换口气：换景、换时间或换视角，器乐重音配画面事件',
    'bridge': '反差：换世界 / 换色调 / 换视角，情绪转折，给最后一遍副歌蓄力',
    'outro': '收：动作和镜头慢下来，回收前面的道具或画面，首尾呼应，最后一拍落定',
    'build': '蓄力：越来越密越来越紧，镜头推进、闪烁加速，最后一拍留空',
    'drop': '炸开：全片最强的画面变化落在第一拍',
}


def mmss(t): return f'{int(t // 60):02d}:{t % 60:05.2f}'


# ---------------------------------------------------------------- 歌词
TS = re.compile(r'[\[<](\d+):(\d+(?:\.\d+)?)[\]>]')


def read_text(p):
    raw = open(p, 'rb').read()
    for enc in ('utf-8-sig', 'gb18030', 'big5'):
        try: return raw.decode(enc)
        except UnicodeDecodeError: pass
    return raw.decode('utf-8', 'replace')


def load_vocal_pieces(p):
    """lyrics_align.json（align_lyrics.py 的产出）里的 vocal_pieces：[[起, 止], …] 有人声的片段。"""
    try:
        d = json.load(open(p, encoding='utf-8'))
        return [[float(a), float(b)] for a, b in d.get('vocal_pieces', [])] if isinstance(d, dict) else []
    except Exception: return []


def load_lyrics(p):
    """→ [{t0, t1, text}]，按时间排好，去掉 ♪ 行。t1 没有时为 None（后面用下一句句首补）。"""
    if not p or not os.path.exists(p): return []
    txt = read_text(p)
    rows = []
    if p.lower().endswith('.json') or re.match(r'\s*(\{|\[\s*\{)', txt):
        d = json.loads(txt)
        items = d.get('lines', d.get('lyrics', [])) if isinstance(d, dict) else d
        for it in items:
            t0 = next((it[k] for k in ('t0', 'start', 't') if k in it), None)
            t1 = next((it[k] for k in ('t1', 'end') if k in it), None)
            text = str(it.get('text', '')).strip()
            if t0 is None or not text: continue
            rows.append({'t0': float(t0), 't1': float(t1) if t1 is not None else None, 'text': text})
    else:
        off = re.search(r'\[offset:(-?\d+)\]', txt); off = int(off.group(1)) / 1000 if off else 0
        for ln in txt.splitlines():
            ts = TS.findall(ln)
            if not ts or re.match(r'\[[a-z]+:', ln): continue
            text = TS.sub('', ln).strip()
            times = [int(m) * 60 + float(s) + off for m, s in ts]
            if not text:                      # 只有时间没有字的行 = 上一句的句尾（align_lyrics.py 的写法）
                if rows and times[0] > rows[-1]['t0']: rows[-1]['t1'] = times[0]
                continue
            rows.append({'t0': times[0], 't1': max(times) if len(times) > 2 else None, 'text': text})
    rows = sorted([r for r in rows if not r['text'].startswith('♪')], key=lambda r: r['t0'])
    for i, r in enumerate(rows):
        nxt = rows[i + 1]['t0'] if i + 1 < len(rows) else r['t0'] + 6
        if r['t1'] is None or r['t1'] <= r['t0']: r['t1'] = min(nxt, r['t0'] + 6)
        r['t1'] = min(r['t1'], nxt if nxt > r['t0'] else r['t1'])
    return rows


def norm(s):
    return re.sub(r'[\s\W_]+', '', s.lower())


# ---------------------------------------------------------------- 音频特征（可选）
def bar_features(audio, bars, dur):
    """每小节一个特征：12 维音级（和声 / 旋律）+ 12 维对数频带（音色），各自归一化。失败返回 None。"""
    SR, NFFT, HOP = 22050, 4096, 2048
    try:
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', audio, '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'],
                             capture_output=True, check=True).stdout
    except Exception as e:
        print('（读不了音频，不算旋律相似度：%s）' % e); return None
    y = np.frombuffer(raw, np.float32).astype(np.float64)
    if len(y) < NFFT * 4: return None
    win = np.hanning(NFFT); nfr = 1 + (len(y) - NFFT) // HOP
    fr = np.lib.stride_tricks.sliding_window_view(y, NFFT)[::HOP][:nfr] * win
    S = np.abs(np.fft.rfft(fr, axis=1)).astype(np.float32)          # (帧, 频率)
    f = np.fft.rfftfreq(NFFT, 1 / SR)
    ok = (f > 65) & (f < 4200)
    pc = (np.round(12 * np.log2(f[ok] / 440.0)) % 12).astype(int)
    C = np.zeros((S.shape[0], 12), np.float32)
    for k in range(12): C[:, k] = S[:, ok][:, pc == k].sum(1)
    C = np.log1p(C * 5)
    edges = np.geomspace(40, 10000, 13)
    T = np.log1p(np.stack([S[:, (f >= a) & (f < b)].sum(1) for a, b in zip(edges, edges[1:])], 1) * 10)
    tf = (np.arange(S.shape[0]) * HOP + NFFT / 2) / SR
    out = []
    for a, b in zip(bars, list(bars[1:]) + [dur]):
        m = (tf >= a) & (tf < b)
        if not m.any(): m = np.abs(tf - a) == np.abs(tf - a).min()
        c = C[m].mean(0); c = c - c.mean(); c /= np.linalg.norm(c) + 1e-9
        out.append((c, T[m].mean(0)))
    Tm = np.array([t for _, t in out]); Tm = (Tm - Tm.mean(0)) / (Tm.std(0) + 1e-9)
    F = np.array([np.concatenate([c, t / np.sqrt(12)]) for (c, _), t in zip(out, Tm)])
    F /= np.linalg.norm(F, axis=1, keepdims=True) + 1e-9
    return F


def seg_sim(F, a0, a1, b0, b1):
    """两段（小节下标区间）的相似度：从段首对齐，允许错开 ±1 小节，取对角线平均余弦。"""
    if F is None: return None
    best = -1
    for sh in (-1, 0, 1):
        n = min(a1 - a0, b1 - b0 - sh) if sh >= 0 else min(a1 - a0 + sh, b1 - b0)
        if n < 2: continue
        A = F[a0 + max(0, -sh): a0 + max(0, -sh) + n]; B = F[b0 + max(0, sh): b0 + max(0, sh) + n]
        best = max(best, float((A * B).sum(1).mean()))
    return best if best > -1 else None


def novelty_cuts(F, bars, t0, t1, min_bars=4, max_n=None):
    """在 [t0, t1] 里按小节特征的「新颖度」找换段点（棋盘核），两个点至少隔 min_bars 小节。"""
    if F is None or len(F) < 2 * min_bars + 2: return []
    K = 4; n = len(F); sim = F @ F.T
    ker = np.kron(np.array([[1, -1], [-1, 1]]), np.ones((K, K)))
    nov = np.zeros(n)
    for i in range(K, n - K): nov[i] = (sim[i - K:i + K, i - K:i + K] * ker).sum()
    idx = [i for i in range(n) if t0 + min_bars * 0.9 * (bars[1] - bars[0]) < bars[i] < t1 - min_bars * 0.9 * (bars[1] - bars[0])]
    if not idx: return []
    thr = np.percentile(nov[K:n - K], 70) if n > 2 * K else 0
    got = []
    for i in sorted(idx, key=lambda i: -nov[i]):
        if nov[i] <= thr or (max_n and len(got) >= max_n): break
        if all(abs(i - j) >= min_bars for j in got): got.append(i)
    return sorted(float(bars[i]) for i in got)


# ---------------------------------------------------------------- 主流程
def analyze(TL, lines, F, vp=None):
    dur = float(TL['duration']); bars = list(TL.get('bar_times') or [])
    spb = TL.get('seconds_per_beat') or 60 / TL.get('tempo_bpm', 120)
    if not bars: bars = list(np.arange(0, dur, 4 * spb))
    if bars[0] > 0.5: bars = [0.0] + bars                         # 第一小节之前的零头算一小节
    barlen = float(np.median(np.diff(bars))) if len(bars) > 1 else 4 * spb
    nb = len(bars); bend = bars[1:] + [dur]
    E = np.array(TL.get('energy_per_bar') or [], float)
    if len(E) < nb: E = np.concatenate([np.full(nb - len(E), E[0] if len(E) else .5), E]) if len(E) else np.full(nb, .5)
    E = E[-nb:] if len(E) > nb else E
    lo_, hi_ = np.percentile(E, 5), np.percentile(E, 98)       # 母带压得很平的歌也拉开差别：按全曲 5%–98% 分位拉到 0..1
    E = np.clip((E - lo_) / (hi_ - lo_ + 1e-9), 0, 1) * 0.9 + 0.1
    bi_of = lambda t: int(np.clip(np.searchsorted(bars, t + 1e-6) - 1, 0, nb - 1))
    beats = list(TL.get('beat_times') or [])
    def snap(t):
        # 段首对齐：句首前 1 拍 / 后半拍以内有小节线就对到小节线（弱起的字常常比强拍早一点），否则对到最近的拍
        b = min(bars + [dur], key=lambda x: abs(x - t))
        if -0.5 * spb <= b - t <= 1.05 * spb or abs(b - t) < 0.15: return b
        if beats:
            bb = min(beats, key=lambda x: abs(x - t))
            if abs(bb - t) < 0.5 * spb: return bb
        return t
    drops = [d['time'] if isinstance(d, dict) else d for d in TL.get('drops', [])]
    secs = [s if isinstance(s, (int, float)) else s.get('time', 0) for s in TL.get('sections', [])]

    # ---- 人声区间
    vocal_unknown = False
    if lines:
        method = 'lyrics'
        voc_spans = [[l['t0'], l['t1']] for l in lines]
    elif vp:
        method = 'vocal-pieces'
        voc_spans = [list(x) for x in vp]
    else:
        method = 'audio'
        va = np.array(TL.get('vocal_activity_per_beat') or [], float); bts = TL.get('beat_times') or []
        voc_spans = []
        if len(va) < 8 or np.percentile(va, 90) - np.percentile(va, 10) < 0.3:
            # 人声频段估计分不出唱和不唱（大多数混音都这样）：整首当成「不知道哪里在唱」，前奏尾奏只按能量猜
            vocal_unknown = True
            loud = [bars[i] for i in range(nb) if E[i] > 0.2]
            voc_spans = [[loud[0] if loud else 0.0, (bend[bars.index(loud[-1])] if loud else dur)]]
        elif len(va) and len(bts):
            thr = max(0.35, float(np.percentile(va, 40)))
            on = [(bts[i], va[i] > thr and (E[bi_of(bts[i])] > 0.25)) for i in range(min(len(va), len(bts)))]
            cur = None
            for t, v in on:
                if v and cur is None: cur = [t, t + spb]
                elif v: cur[1] = t + spb
                elif cur is not None:
                    voc_spans.append(cur); cur = None
            if cur: voc_spans.append(cur)
            voc_spans = [s for s in voc_spans if s[1] - s[0] >= 2 * barlen]     # 太碎的不算
    # 合并成「唱的块」：空档 < 1.5 小节（且 < 4 秒）算同一块
    GAP = min(1.5 * barlen, 4.0)
    sung = []
    for s in voc_spans:
        if sung and s[0] - sung[-1][1] < GAP: sung[-1][1] = max(sung[-1][1], s[1])
        else: sung.append(list(s))

    pieces = []   # {t0, t1, kind: sung|inst, lines: [idx]}
    if lines:
        # ---- 歌词重复：每句一个类号，再找「连续 ≥2 句都相同」的重复片段
        N = len(lines); keys = [norm(l['text']) for l in lines]
        cid = list(range(N))
        for i in range(N):
            for j in range(i):
                if cid[j] == j and keys[i] and keys[j] and difflib.SequenceMatcher(None, keys[i], keys[j]).ratio() >= 0.7:
                    cid[i] = j; break
        cnt = {c: cid.count(c) for c in set(cid)}
        R = np.zeros((N + 1, N + 1), int)
        for i in range(N - 1, -1, -1):
            for j in range(N - 1, i, -1):
                if cid[i] == cid[j]: R[i, j] = R[i + 1, j + 1] + 1
        runs = []   # (i, j, L) 最长的、不能再往前延伸的重复片段
        for i in range(N):
            for j in range(i + 1, N):
                L = int(R[i, j])
                if L >= 2 and (i == 0 or cid[i - 1] != cid[j - 1] or R[i - 1, j - 1] == 0):
                    L = min(L, j - i)                                       # 两段不能重叠
                    if L >= 2: runs.append((i, j, L))
        # 切点：每个重复片段的首尾 + 歌词里的长空档 + 时间轴段落分界（只在句间）；切点沿重复片段互相投影直到稳定
        cuts = {0, N}
        for i, j, L in runs: cuts |= {i, i + L, j, j + L}
        for k in range(1, N):
            if lines[k]['t0'] - lines[k - 1]['t1'] >= GAP: cuts.add(k)
        for _ in range(10):
            new = set(cuts)
            for i, j, L in runs:
                for c in list(cuts):
                    if i < c < i + L: new.add(j + c - i)
                    if j < c < j + L: new.add(i + c - j)
            if new == cuts: break
            cuts = new
        cuts = sorted(cuts)
        blocks = [list(range(a, b)) for a, b in zip(cuts, cuts[1:]) if b > a]
        # 相邻的「都不重复」的块合并（同一段主歌被长空档切开的除外：空档 ≥ 2 小节才保留切口）
        def rep(b): return sum(cnt[cid[k]] > 1 for k in b) / len(b)
        merged = []
        for b in blocks:
            if merged and rep(b) < .5 and rep(merged[-1]) < .5 and lines[b[0]]['t0'] - lines[merged[-1][-1]]['t1'] < 2 * barlen:
                merged[-1] += b
            else: merged.append(b)
        blocks = merged
        # 很长的不重复块（> 16 小节）再切一刀：切在最长的句间空档（≥ 1.2 秒）或旋律换段点最近的句首
        out = []
        for b in blocks:
            span = lines[b[-1]]['t1'] - lines[b[0]]['t0']
            if rep(b) < .5 and span > 16 * barlen and len(b) >= 4:
                gaps = [(lines[k]['t0'] - lines[k - 1]['t1'], k) for k in b[2:-1]]
                g_, k_ = max(gaps) if gaps else (0, None)
                if g_ < 1.2:
                    nc = novelty_cuts(F, bars, lines[b[0]]['t0'], lines[b[-1]]['t1'], max_n=1)
                    k_ = min(b[2:-1], key=lambda k: abs(lines[k]['t0'] - nc[0])) if nc and len(b) > 3 else None
                if k_ is not None:
                    i_ = b.index(k_); out += [b[:i_], b[i_:]]; continue
            out.append(b)
        blocks = out
        # 块分组：内容相同（逐句类号序列相似）的块同组
        sig = [[cid[k] for k in b] for b in blocks]
        grp = [-1] * len(blocks); g = 0
        for a in range(len(blocks)):
            if grp[a] >= 0: continue
            grp[a] = g
            for b in range(a + 1, len(blocks)):
                if grp[b] < 0 and min(len(sig[a]), len(sig[b])) >= 2 and rep(blocks[a]) >= .5 and \
                        difflib.SequenceMatcher(None, sig[a], sig[b]).ratio() >= 0.6:
                    grp[b] = g
            g += 1
        for k, b in enumerate(blocks):
            pieces.append({'t0': lines[b[0]]['t0'], 't1': lines[b[-1]]['t1'], 'kind': 'sung', 'lines': b, 'grp': grp[k]})
    else:
        # ---- 没歌词：唱的块按时间轴段落分界再切，切出来的块按旋律相似度分组
        for s0, s1 in sung:
            inner = novelty_cuts(F, bars, s0, s1, max_n=int((s1 - s0) / (6 * barlen)) + 1) if F is not None else \
                [c for c in secs if s0 + 4 * barlen <= c <= s1 - 4 * barlen]
            cs = [s0] + inner + [s1]
            for a, b in zip(cs, cs[1:]): pieces.append({'t0': a, 't1': b, 'kind': 'sung', 'lines': [], 'grp': None})
        g = 0
        for a in range(len(pieces)):
            if pieces[a]['grp'] is not None: continue
            pieces[a]['grp'] = g
            for b in range(a + 1, len(pieces)):
                if pieces[b]['grp'] is None:
                    s = seg_sim(F, bi_of(pieces[a]['t0']), bi_of(pieces[a]['t1'] - .01) + 1, bi_of(pieces[b]['t0']), bi_of(pieces[b]['t1'] - .01) + 1)
                    if s is not None and s >= 0.55: pieces[b]['grp'] = g
            g += 1

    # ---- 边界对齐到小节线，补上没人声的段
    for p in pieces: p['s0'] = snap(p['t0'])
    for k, p in enumerate(pieces): p['s1'] = pieces[k + 1]['s0'] if k + 1 < len(pieces) else snap(p['t1'])
    full = []; t = 0.0
    for p in pieces:
        if p['s0'] - t >= 2 * barlen - 1e-6 or (not full and p['s0'] - t >= 2.0):
            full.append({'s0': t, 's1': p['s0'], 'kind': 'inst', 'lines': [], 'grp': None})
        elif full: full[-1]['s1'] = p['s0']                        # 很短的空档并进前一段
        else: p['s0'] = 0.0                                         # 歌一开头就唱
        full.append(p); t = p['s1']
    if dur - t >= 2.0 or not full: full.append({'s0': t, 's1': dur, 'kind': 'inst', 'lines': [], 'grp': None})
    elif full: full[-1]['s1'] = dur
    # 唱的块里如果有长于 2 小节的无人声尾巴（副歌唱完后的器乐），切出来
    out = []
    for p in full:
        if p['kind'] == 'sung' and p['lines']:
            last = lines[p['lines'][-1]]['t1']; cut = snap(last + .3)
            if p['s1'] - cut >= 4 * barlen - 1e-6 and cut > p['s0']:
                out.append(dict(p, s1=cut)); out.append({'s0': cut, 's1': p['s1'], 'kind': 'inst', 'lines': [], 'grp': None}); continue
        out.append(p)
    full = [p for p in out if p['s1'] - p['s0'] > 0.05]
    for p in full:
        b0, b1 = bi_of(p['s0']), max(bi_of(p['s0']) + 1, bi_of(p['s1'] - 0.01) + 1)
        p['b0'], p['b1'] = b0, b1; p['E'] = float(E[b0:b1].mean())

    # ---- 贴标签
    sungp = [p for p in full if p['kind'] == 'sung']
    groups = {}
    for p in sungp: groups.setdefault(p['grp'], []).append(p)
    reps = {g: ps for g, ps in groups.items() if len(ps) >= 2}
    meanE = np.mean([p['E'] for p in sungp]) if sungp else 0.5
    chorus_g = None
    if reps:
        chorus_g = max(reps, key=lambda g: np.mean([p['E'] for p in reps[g]]) + 0.04 * len(reps[g]) +
                       0.02 * np.mean([len(p['lines']) for p in reps[g]] or [0]))
    for p in sungp:
        p['why'] = []
        if p['grp'] == chorus_g:
            p['label'] = 'chorus'; p['why'].append('歌词重复 %d 遍、能量在重复段里最高' % len(reps[chorus_g]) if lines else '旋律重复 %d 遍、能量最高' % len(reps[chorus_g]))
    # 导歌：另一组重复段，每次都紧挨在副歌前面，能量比副歌低
    for g, ps in reps.items():
        if g == chorus_g: continue
        before = 0
        for p in ps:
            k = full.index(p)
            if k + 1 < len(full) and full[k + 1].get('grp') == chorus_g: before += 1
        cE = np.mean([p['E'] for p in reps[chorus_g]]) if chorus_g is not None else 1
        for p in ps:
            if before >= max(1, len(ps) - 1) and np.mean([q['E'] for q in ps]) <= cE + 0.02:
                p['label'] = 'pre-chorus'; p['why'].append('重复 %d 遍、每次都接副歌、能量比副歌低' % len(ps))
            elif np.mean([q['E'] for q in ps]) >= cE - 0.03 and any(full.index(q) > 0 and full[full.index(q) - 1].get('grp') == chorus_g for q in ps):
                p['label'] = 'chorus'; p['why'].append('紧跟副歌的重复段、能量和副歌一样高（副歌后半）')
            else:
                p['label'] = 'verse'; p['why'].append('重复 %d 遍但不接副歌、能量不高' % len(ps))
    # 没有可重复的副歌：能量最高的唱段当副歌（可信度低）
    if chorus_g is None and sungp:
        top = sorted(sungp, key=lambda p: -p['E'])[:max(1, len(sungp) // 3)]
        for p in top:
            if p['E'] > meanE: p['label'] = 'chorus'; p['why'] = ['没找到重复段，按能量最高估的']
    # 其余唱的段：主歌 / 桥段 / 导歌 / 尾奏
    ch_idx = [k for k, p in enumerate(full) if p.get('label') == 'chorus']
    first_verse = None
    for k, p in enumerate(full):
        if p['kind'] != 'sung' or p.get('label'): continue
        n_before = len({full[c].get('grp') for c in ch_idx if c < k} and [c for c in ch_idx if c < k and (c == 0 or full[c - 1].get('label') != 'chorus')])
        after = [c for c in ch_idx if c > k]
        nxt_ch = k + 1 < len(full) and full[k + 1].get('label') == 'chorus'
        if n_before == 0 or first_verse is None and not after:
            p['label'] = 'verse'; p['why'].append('歌词不重复、在第一遍副歌之前' if n_before == 0 else '歌词不重复')
        elif not after:
            p['label'] = 'outro' if p['E'] < meanE and k >= len(full) - 2 else 'verse'
            p['why'].append('最后一遍副歌之后、能量回落' if p['label'] == 'outro' else '歌词不重复')
        else:
            sim = None
            if first_verse is not None:
                sim = seg_sim(F, p['b0'], p['b1'], first_verse['b0'], first_verse['b1'])
            nxt_pre = k + 1 < len(full) and full[k + 1].get('label') == 'pre-chorus'
            if not nxt_pre and (n_before >= 2 or (sim is not None and sim < 0.45)):
                p['label'] = 'bridge'; p['why'].append('歌词只出现一次、在第 %d 遍副歌之后' % n_before + (f'、旋律和主歌 1 相似度 {sim:.2f}' if sim is not None else ''))
            else:
                p['label'] = 'verse'; p['why'].append('歌词不重复、在两遍副歌之间' + ('、后面接导歌' if nxt_pre else '') + (f'、旋律和主歌 1 相似度 {sim:.2f}' if sim is not None else ''))
        if p['label'] == 'verse' and first_verse is None: first_verse = p
    # 主歌最后几小节能量明显上扬、又没有导歌时，切出导歌（≥ 4 小节，≤ 8 小节）
    out = []
    for k, p in enumerate(full):
        if p.get('label') == 'verse' and k + 1 < len(full) and full[k + 1].get('label') == 'chorus' and p['b1'] - p['b0'] >= 12:
            tail = E[p['b1'] - 4:p['b1']].mean(); head = E[p['b0']:p['b1'] - 4].mean()
            if tail - head > 0.12 and lines:
                cut_b = p['b1'] - 4; cut = bars[cut_b]
                # 切在句首上：取最接近的句首
                ls = [lines[i]['t0'] for i in p['lines'] if p['s0'] + 2 * barlen < lines[i]['t0'] < p['s1'] - 2 * barlen]
                if ls:
                    cut = snap(min(ls, key=lambda x: abs(x - cut)))
                    a = dict(p, s1=cut, lines=[i for i in p['lines'] if lines[i]['t0'] < cut - .3])
                    b = dict(p, s0=cut, lines=[i for i in p['lines'] if lines[i]['t0'] >= cut - .3], label='pre-chorus',
                             why=['主歌最后几小节能量上扬（+%.2f）、接副歌' % (tail - head)])
                    out += [a, b]; continue
        out.append(p)
    full = out
    # 没人声的段
    first_s = next((k for k, p in enumerate(full) if p['kind'] == 'sung'), None)
    last_s = max((k for k, p in enumerate(full) if p['kind'] == 'sung'), default=None)
    for k, p in enumerate(full):
        if p['kind'] != 'inst': continue
        if first_s is None: p['label'] = 'intro' if k == 0 else 'interlude'; p['why'] = ['全段没有人声']
        elif k < first_s: p['label'] = 'intro'; p['why'] = ['第一句歌词之前，没人声']
        elif k > last_s: p['label'] = 'outro'; p['why'] = ['最后一句歌词之后，没人声']
        else: p['label'] = 'interlude'; p['why'] = ['两段歌词之间没人声 %.1f 秒' % (p['s1'] - p['s0'])]
    # 电音：没人声的段里有 drop → 蓄力 + 炸点
    out = []
    for p in full:
        dd = [d for d in drops if p['s0'] + 2 * barlen <= d < p['s1'] - 2 * barlen] if p['kind'] == 'inst' else []
        if dd and p['label'] in ('interlude', 'intro', 'outro'):
            d = snap(dd[0]); bstart = max(p['s0'], d - 8 * barlen)
            if E[bi_of(d):bi_of(min(p['s1'], d + 4 * barlen))].mean() > meanE:
                pre = dict(p, s1=bstart) if bstart - p['s0'] >= 2 * barlen else None
                if pre: out.append(pre)
                out.append(dict(p, s0=bstart if pre else p['s0'], s1=d, label='build', why=['drop 前的器乐段']))
                out.append(dict(p, s0=d, label='drop', why=['时间轴标了 drop、之后能量高、没人声']))
                continue
        out.append(p)
    full = out
    for p in full:
        b0, b1 = bi_of(p['s0']), max(bi_of(p['s0']) + 1, bi_of(p['s1'] - 0.01) + 1)
        p['b0'], p['b1'] = b0, b1; p['E'] = float(E[b0:b1].mean())
        if p['kind'] == 'sung' and any(abs(d - p['s0']) < 1.5 * barlen for d in drops): p['why'].append('段首有 drop')

    # ---- 合并相邻同标签、同组的段（例如被长空档切开的同一段主歌）
    merged = []
    for p in full:
        q = merged[-1] if merged else None
        if q and q['label'] == p['label'] and q['kind'] == p['kind'] and q.get('grp') == p.get('grp') and p['label'] in ('verse', 'intro', 'outro', 'interlude'):
            q['s1'] = p['s1']; q['lines'] = q['lines'] + p['lines']; q['b1'] = p['b1']; q['E'] = float(E[q['b0']:q['b1']].mean())
        else: merged.append(p)
    full = merged

    # ---- 不知道哪里在唱时：头尾能量偏低、又不是重复段的，当前奏 / 尾奏（猜的）
    if vocal_unknown and len(full) >= 3:
        med = float(np.median([p['E'] for p in full]))
        for k in (0, len(full) - 1):
            p = full[k]
            if p.get('label') != 'chorus' and p['E'] < med and (p['s1'] - p['s0']) < 0.25 * dur:
                p['label'] = 'intro' if k == 0 else 'outro'; p['kind'] = 'inst'
                p['why'] = ['分不出人声，按位置和能量猜的（开头 / 结尾、能量偏低）']
    # ---- 编号、第几遍、可信度
    nth = {}; parts = []
    allE = np.array([p['E'] for p in full]); rankE = {id(p): int((allE > p['E'] + 1e-9).sum()) + 1 for p in full}
    for k, p in enumerate(full):
        lab = p['label']; nth[lab] = nth.get(lab, 0) + 1
        conf = 0.85 if lab in ('intro', 'outro', 'interlude') and lines else 0.8 if lab == 'chorus' and chorus_g is not None else 0.6
        if not lines: conf -= 0.2
        if lab == 'bridge' or (lab == 'pre-chorus' and 'repeat' not in ''.join(p['why'])): conf = min(conf, 0.6)
        if lab == 'chorus' and p['E'] < meanE - 0.05: conf -= 0.15; p['why'].append('提醒：这一遍能量不高，听一下是不是收着唱的副歌')
        sub = [round(s, 3) for s in secs if p['s0'] + 2 < s < p['s1'] - 2] if lab in ('intro', 'interlude', 'outro', 'bridge') else []
        parts.append({
            'id': 'P%02d' % (k + 1), 'label': lab, 'name': LABELS[lab] + (str(nth[lab]) if lab in ('verse', 'pre-chorus', 'chorus', 'interlude', 'bridge') else ''),
            'nth': nth[lab], 't0': round(p['s0'], 3), 't1': round(p['s1'], 3),
            'bar0': int(p['b0']), 'bars': int(p['b1'] - p['b0']), 'energy': round(p['E'], 3), 'energy_rank': rankE[id(p)],
            'vocal': p['kind'] == 'sung', 'first_line': (lines[p['lines'][0]]['text'] if p['lines'] else ''),
            'vocal_t0': round(lines[p['lines'][0]]['t0'], 3) if p['lines'] else None,
            'n_lines': len(p['lines']), 'group': (chr(65 + p['grp']) if isinstance(p.get('grp'), int) and p['grp'] < 26 else None),
            'sub': sub, 'conf': round(max(0.2, conf), 2), 'why': '；'.join(p['why'])})
    # 每种段落出现的总遍数，写进 name（只出现一次的不加数字）
    tot = {}
    for q in parts: tot[q['label']] = tot.get(q['label'], 0) + 1
    for q in parts:
        if tot[q['label']] == 1: q['name'] = LABELS[q['label']]
    return {'version': 1, 'checked': False, 'method': method + ('+melody' if F is not None else '') + '+energy',
            'duration': round(dur, 3), 'bar_seconds': round(barlen, 3),
            'labels': LABELS, 'parts': parts,
            'summary': ' → '.join(q['name'] for q in parts)}


def renumber(S):
    """按 label 重新起名（副歌1、副歌2…；只出现一次的不带数字）、重算第几遍和 summary。人工改了 label 之后用。"""
    P = S.get('parts', []); tot, nth = {}, {}
    for p in P: tot[p['label']] = tot.get(p['label'], 0) + 1
    for k, p in enumerate(P):
        nth[p['label']] = nth.get(p['label'], 0) + 1
        p['id'] = 'P%02d' % (k + 1); p['nth'] = nth[p['label']]
        p['name'] = LABELS.get(p['label'], p['label']) + (str(nth[p['label']]) if tot[p['label']] > 1 else '')
    S['summary'] = ' → '.join(p['name'] for p in P)
    return S


def validate(S):
    errs = []
    P = S.get('parts', [])
    if not P: return ['parts 是空的']
    if abs(P[0]['t0']) > 0.05: errs.append(f"第一段应从 0 开始，现在是 {P[0]['t0']}")
    for a, b in zip(P, P[1:]):
        if abs(a['t1'] - b['t0']) > 0.05: errs.append(f"{a['id']} 结束 {a['t1']} 和 {b['id']} 开始 {b['t0']} 没接上")
    if abs(P[-1]['t1'] - S.get('duration', P[-1]['t1'])) > 0.5: errs.append(f"最后一段应到歌尾 {S.get('duration')}")
    for p in P:
        if p.get('label') not in LABELS: errs.append(f"{p.get('id')} 的 label「{p.get('label')}」不认识，只能用：{' '.join(LABELS)}")
        if p['t1'] <= p['t0']: errs.append(f"{p.get('id')} 起止时间反了")
    return errs


def report(S, path):
    bar = lambda e: '█' * int(round(e * 12)) + '·' * (12 - int(round(e * 12)))
    R = ['# 歌曲结构（%s）' % ('已人工校对' if S.get('checked') else '自动估计，请核对'), '',
         '**' + S['summary'] + '**', '',
         '| 段 | 段落 | 时间 | 小节 | 能量 | 第一句 | 可信度 | 判断依据 |', '|---|---|---|---|---|---|---|---|']
    for p in S['parts']:
        R.append(f"| {p['id']} | **{p['name']}** `{p['label']}` | {mmss(p['t0'])}–{mmss(p['t1'])}（{p['t1'] - p['t0']:.1f}s） | {p['bars']} | "
                 f"`{bar(p['energy'])}` {p['energy']:.2f} | {p['first_line'][:14]} | {p['conf']:.2f} | {p['why']} |")
    R += ['', '## 每种段落怎么拍（提示）', '']
    for lab in dict.fromkeys(p['label'] for p in S['parts']): R.append(f"- **{LABELS[lab]}**：{HOWTO[lab]}")
    ch = [p for p in S['parts'] if p['label'] in ('chorus', 'drop')]
    if ch:
        top = max(ch, key=lambda p: (p['energy'], p['t0']))
        R += ['', f"全片最大的时刻候选：{top['name']}（{mmss(top['t0'])} 起，能量 {top['energy']:.2f}）。最后一遍副歌通常要做成最大，即使能量差不多。"]
    R += ['', '## 怎么改', '',
          '标签不对就改 `structure.json` 里 parts 的 `label`（' + ' / '.join(f'{k}={v}' for k, v in LABELS.items()) + '）或 `t0` / `t1`，',
          '把 `"checked": false` 改成 `true`，再重建项目（或在项目里跑 make_data）。改过的文件不会被自动分析覆盖。',
          '最容易错的是主歌 / 导歌 / 桥段的分界：对着歌听这几处的开头。']
    open(path, 'w', encoding='utf-8').write('\n'.join(R) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--timeline'); ap.add_argument('--lyrics'); ap.add_argument('--audio'); ap.add_argument('--vocal'); ap.add_argument('--out', default='.')
    ap.add_argument('--force', action='store_true'); ap.add_argument('--validate')
    A = ap.parse_args()
    if A.validate:
        S = json.load(open(A.validate, encoding='utf-8')); e = validate(S)
        if not e: renumber(S); json.dump(S, open(A.validate, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('\n'.join(e) if e else 'OK：' + S.get('summary', '')); sys.exit(1 if e else 0)
    if not A.timeline: sys.exit('要给 --timeline audio.timeline.json')
    TL = json.load(open(A.timeline, encoding='utf-8'))
    lines = load_lyrics(A.lyrics)
    vpf = A.vocal or (os.path.join(os.path.dirname(os.path.abspath(A.lyrics)), 'lyrics_align.json') if A.lyrics else None)
    vp = load_vocal_pieces(vpf) if vpf and os.path.exists(vpf) else []
    bars = list(TL.get('bar_times') or [])
    if bars and bars[0] > 0.5: bars = [0.0] + bars
    F = bar_features(A.audio, bars, TL['duration']) if A.audio and bars else None
    S = analyze(TL, lines, F, vp)
    os.makedirs(A.out, exist_ok=True)
    js, md = os.path.join(A.out, 'structure.json'), os.path.join(A.out, 'structure.md')
    if os.path.exists(js) and not A.force:
        try: old = json.load(open(js, encoding='utf-8'))
        except Exception: old = {}
        if old.get('checked'):
            e = validate(old)
            if e: print('structure.json（人工校对版）有问题：\n  ' + '\n  '.join(e))
            else: renumber(old); json.dump(old, open(js, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            json.dump(S, open(os.path.join(A.out, 'structure.auto.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            print('structure.json 已人工校对，不覆盖；这次自动结果写在 structure.auto.json：' + S['summary'])
            report(old, md); return
    json.dump(S, open(js, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    report(S, md)
    print(f"歌曲结构（{'按歌词重复' if lines else '没歌词，按旋律和能量估'}）：{S['summary']} → {js}、structure.md")
    low = [p for p in S['parts'] if p['conf'] < 0.6]
    if low: print('  拿不准的段：' + '、'.join(f"{p['name']} {mmss(p['t0'])}" for p in low) + '，写 TREATMENT 前听一下')


if __name__ == '__main__':
    main()

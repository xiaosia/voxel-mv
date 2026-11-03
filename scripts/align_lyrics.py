#!/usr/bin/env python3
"""歌词对时间：把「字是对的」歌词对到这首歌（这个版本）的音频上，每句拿到准确的开始和结束时间。
没有歌词文字时，也能只靠听歌识别出带时间的歌词（错字会多，要人核对）。

做法（字和时间分开拿）：
  1. 分离人声（装了 demucs 或 audio-separator 才做；没装就用原曲）
  2. 按人声切片：人声停 ≥1 秒的地方下刀，一片 10–30 秒；没有人声的片（前奏、间奏、DJ 纯音乐段）不送去识别，
     这样就不会凭空编出「Don't don't don't」这类句子
  3. faster-whisper 逐片识别，拿到每个字的时间（有显卡默认 large-v3，没有默认 medium）
  4. 有歌词文字时：按拼音把歌词一个字一个字对到识别结果上（同音错字也能对上），每句取第一个/最后一个对上的字的时间；
     分离后和原曲各识别一遍，每句用对得更好的那一版（分离效果差的歌会自动退回原曲）
  5. 输出 LRC（句尾写一个空时间行当结束时间）+ lyrics_align.json（每句的开始、结束、置信度、听到的字）+ lyrics_check.md

用法：
  python $SKILL/scripts/align_lyrics.py song.mp3 --text 歌词.txt [--out lyrics.lrc]
  python $SKILL/scripts/align_lyrics.py song.mp3                 # 没有歌词文字：只靠识别
  --text     歌词文字：纯文本（一行一句）或 LRC（时间会被当成参考，主要用字）。网易云 / QQ 音乐复制下来的就行
  --sep      auto（默认：BS-RoFormer（audio-separator）→ demucs → 不分离）| demucs | roformer | none
  --model    auto（默认）| small | medium | large-v3 …  faster-whisper 模型
  --device   auto（默认）| cuda | cpu
  --lang     zh（默认）
  --work     中间文件目录（默认：输出文件旁边的 _lyrics_work/），识别结果会缓存在这里，换参数重跑很快
  --preview  另外出一个带字幕的试听视频 lyrics_preview.mp4（听一遍就知道准不准）
  --compare  实测用：分离和不分离各出一份完整结果对比（报告里列每句两种做法的置信度）
依赖：ffmpeg、numpy；识别要 pip install faster-whisper（模型下不动：python scripts/fetch_ct2_model.py large-v3，或 VOXEL_ASR_MODEL=模型目录）；对齐要 pip install pypinyin；
      分离人声 pip install demucs（或 pip install "audio-separator[gpu]"）；繁转简 pip install opencc-python-reimplemented（可选）
退出码：0 成功；1 没拿到歌词（没装识别、也没给能用的歌词）；2 参数或文件错误

输出的时间轴文件格式（别的脚本读这个）见 references/lyrics-format.md。"""
import argparse, json, os, re, subprocess, sys, shutil, hashlib
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import numpy as np

SR = 16000
mmss = lambda t: f'{int(max(0, t) // 60):02d}:{max(0, t) % 60:05.2f}'

# ======================================================================================
# 文字处理
# ======================================================================================
CJK = re.compile(r'[㐀-鿿豈-﫿]')
UNIT = re.compile(r"[㐀-鿿豈-﫿]|[A-Za-z0-9]+(?:'[A-Za-z]+)?")

def units(text):
    """拆成对齐单位：汉字一个字一个，英文/数字一个词一个；标点、空格不算。"""
    return UNIT.findall(text)

try:
    from pypinyin import lazy_pinyin, Style
    def _py(u): return lazy_pinyin(u, style=Style.NORMAL, errors='ignore')[0] if CJK.match(u) else u.lower()
    HAVE_PINYIN = True
except ImportError:
    def _py(u): return u.lower()
    HAVE_PINYIN = False

_pyc = {}
def py(u):
    if u not in _pyc: _pyc[u] = _py(u) or u
    return _pyc[u]

try:
    import opencc
    _cc = opencc.OpenCC('t2s')
    to_simp = _cc.convert
except Exception:
    to_simp = lambda s: s

INITS = ('zh', 'ch', 'sh', 'b', 'p', 'm', 'f', 'd', 't', 'n', 'l', 'g', 'k', 'h', 'j', 'q', 'x', 'r', 'z', 'c', 's', 'y', 'w')
def split_py(p):
    for i in INITS:
        if p.startswith(i): return i, p[len(i):]
    return '', p
CLOSE = [{'z', 'zh'}, {'c', 'ch'}, {'s', 'sh'}, {'n', 'l'}, {'f', 'h'}, {'', 'y'}, {'', 'w'}]
_simc = {}
def sim(a, b):
    """两个单位有多像：同字 1，同音 0.85，近音（平翘舌、前后鼻音、n/l）0.7，同韵 0.35，否则扣分。"""
    if a == b: return 1.0
    k = (a, b)
    if k in _simc: return _simc[k]
    pa, pb = py(a), py(b)
    if pa == pb: s = 0.85
    elif not (CJK.match(a) and CJK.match(b)):
        s = 0.6 if pa[:3] == pb[:3] and len(pa) > 2 else -0.6   # 英文：前缀一样算半对（love / lov）
    else:
        ia, fa = split_py(pa); ib, fb = split_py(pb)
        nz = lambda f: f.replace('ng', 'n')
        if nz(fa) == nz(fb): s = 0.7 if (ia == ib or {ia, ib} in CLOSE) else 0.35
        elif ia == ib and ia: s = 0.12
        else: s = -0.6
    _simc[k] = s
    return s

def read_text(path):
    """读歌词文字：LRC 或纯文本。返回 [(参考时间或 None, 一句)]，去掉 [ti:] 之类的标签和 作词/作曲 行。"""
    raw = open(path, 'rb').read()
    for enc in ('utf-8-sig', 'gb18030', 'big5'):
        try: txt = raw.decode(enc); break
        except UnicodeDecodeError: pass
    else: txt = raw.decode('utf-8', 'replace')
    TS = re.compile(r'[\[<](\d+):(\d+(?:\.\d+)?)[\]>]')
    out = []
    for ln in txt.splitlines():
        if re.match(r'\s*\[[a-zA-Z]+:', ln): continue
        ts = TS.findall(ln)
        s = TS.sub('', ln).strip()
        if not s or not units(s): continue
        if re.match(r'^(作词|作曲|编曲|词|曲|演唱|歌手|制作|混音|和声|监制|录音|出品|吉他|贝斯|鼓|弦乐|母带|op|sp|lyrics|composer)\s*[:：]', s, re.I): continue
        t = int(ts[0][0]) * 60 + float(ts[0][1]) if ts else None
        s = to_simp(s)   # 网上的歌词常是繁体：字幕用简体（装了 opencc 才转）
        for part in [p for p in re.split(r'\s{2,}|\t', s) if units(p)] if not ts else [s]:
            out.append((t, part))
    return out

# ======================================================================================
# 音频：读取、分离、切片
# ======================================================================================
def load(path):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()

def has_cuda():
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception: return False

def separate(audio, work, how, device):
    """分离人声，返回 (vocals.wav 路径, 用的什么) 或 (None, 原因)。结果缓存在 work/。"""
    out = os.path.join(work, f'vocals_{how}.wav')
    if os.path.exists(out): return out, how + '（缓存）'
    if how == 'demucs':
        try: import demucs  # noqa: F401
        except ImportError: return None, '没装 demucs'
        tmp = os.path.join(work, '_demucs')
        dev = 'cuda' if device != 'cpu' and _torch_cuda() else 'cpu'
        print(f'分离人声：demucs htdemucs（{dev}；显卡上一首歌十几秒，CPU 上几分钟）…', flush=True)
        r = subprocess.run([sys.executable, '-m', 'demucs', '--two-stems=vocals', '-n', 'htdemucs', '-d', dev, '-o', tmp, audio])
        v = [os.path.join(d, f) for d, _, fs in os.walk(tmp) for f in fs if f == 'vocals.wav']
        if r.returncode != 0 or not v: return None, 'demucs 运行失败'
        shutil.move(v[0], out); shutil.rmtree(tmp, ignore_errors=True)
        return out, 'demucs htdemucs'
    if how == 'roformer':
        try: from audio_separator.separator import Separator
        except ImportError: return None, '没装 audio-separator'
        print('分离人声：audio-separator BS-RoFormer …', flush=True)
        tmp = os.path.join(work, '_roformer'); os.makedirs(tmp, exist_ok=True)
        try:
            sp = Separator(output_dir=tmp, output_single_stem='Vocals')
            sp.load_model(model_filename=os.environ.get('LYRICS_ROFORMER', 'model_bs_roformer_ep_317_sdr_12.9755.ckpt'))
            files = sp.separate(audio)
        except Exception as e: return None, f'audio-separator 失败：{type(e).__name__}: {e}'
        v = [os.path.join(tmp, os.path.basename(f)) for f in files]
        v = [f for f in v if os.path.exists(f)] or [os.path.join(d, f) for d, _, fs in os.walk(tmp) for f in fs if 'ocal' in f]
        if not v: return None, 'audio-separator 没产出人声文件'
        shutil.move(v[0], out); shutil.rmtree(tmp, ignore_errors=True)
        return out, 'BS-RoFormer'
    return None, '不分离'

def _torch_cuda():
    try:
        import torch
        return torch.cuda.is_available()
    except Exception: return False

def rms_db(y, hop=0.05):
    h = int(SR * hop); n = len(y) // h
    if n == 0: return np.zeros(0)
    r = np.sqrt(np.mean(y[:n * h].reshape(n, h) ** 2, axis=1) + 1e-12)
    return 20 * np.log10(r)

def vocal_activity(v, hop=0.05):
    """人声轨上哪些 50 ms 有人声。阈值在「最安静的 10%」和「最响的 5%」之间：
    动态大的歌 = 比最响低 30 dB 以内且高于底噪 12 dB；压得很响、人声从头唱到尾的歌（DJ 版）两头只差十来 dB，
    这时阈值取两头之间靠下 35% 的位置，不会高过最响的部分（不然一帧都判不成人声）。"""
    db = rms_db(v, hop)
    if len(db) == 0: return db.astype(bool)
    top = np.percentile(db, 95); floor = np.percentile(db, 10)
    thr = max(top - 30, floor + 12)
    if thr > top - 8: thr = floor + (top - floor) * 0.35
    act = db > thr
    # 平滑：0.3 秒以内的空洞补上，0.15 秒以内的毛刺去掉
    k = int(0.3 / hop)
    idx = np.where(act)[0]
    for a, b in zip(idx, idx[1:]):
        if 1 < b - a <= k: act[a:b] = True
    out = act.copy(); i = 0
    while i < len(act):
        if act[i]:
            j = i
            while j < len(act) and act[j]: j += 1
            if (j - i) * hop < 0.15: out[i:j] = False
            i = j
        else: i += 1
    return out

def slices(act, dur, hop=0.05, min_gap=1.0, max_len=30.0, pad=0.5, quiet=None):
    """按人声切片：人声停 ≥ min_gap 秒处下刀；太长的片在中间最安静的地方再切；前后各留 pad 秒。"""
    regs = []; i = 0
    while i < len(act):
        if act[i]:
            j = i
            while j < len(act) and act[j]: j += 1
            regs.append([i * hop, j * hop]); i = j
        else: i += 1
    merged = []
    for a, b in regs:
        if merged and a - merged[-1][1] < min_gap: merged[-1][1] = b
        else: merged.append([a, b])
    out = []
    for a, b in merged:
        while b - a > max_len:   # 太长：在 15–30 秒之间找人声最少的那 0.3 秒切开
            lo, hi = int((a + 15) / hop), int((a + max_len) / hop)
            seg = (quiet if quiet is not None else act)[lo:hi].astype(float)
            w = max(1, int(0.3 / hop))
            cut = lo + int(np.argmin(np.convolve(seg, np.ones(w), 'same'))) if len(seg) > w else hi
            out.append([a, cut * hop]); a = cut * hop
        out.append([a, b])
    return [(max(0.0, a - pad), min(dur, b + pad)) for a, b in out if b - a >= 0.3]

# ======================================================================================
# 识别
# ======================================================================================
_model = {}
def get_model(name, device):
    from faster_whisper import WhisperModel
    if (name, device) in _model: return _model[(name, device)]
    # 模型：环境变量 VOXEL_ASR_MODEL > 技能目录 models/faster-whisper-<名字>（scripts/fetch_ct2_model.py 下的）> 交给 faster-whisper 自己下
    ref = os.environ.get('VOXEL_ASR_MODEL')
    if not ref:
        local = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'models', f'faster-whisper-{name}')
        ref = local if os.path.isdir(local) else name
    device = os.environ.get('VOXEL_ASR_DEVICE', device)
    tries = [('cuda', 'float16'), ('cpu', 'int8')] if device in ('auto', 'cuda') else [('cpu', 'int8')]
    err = None
    for dev, ct in tries:
        try:
            print(f'加载 faster-whisper {ref}（{dev}；第一次会下载模型，下不动就用 scripts/fetch_ct2_model.py {name}）…', flush=True)
            m = WhisperModel(ref, device=dev, compute_type=ct)
            _model[(name, device)] = (m, dev); return m, dev
        except Exception as e:
            err = e; print(f'  {dev} 不行：{type(e).__name__}: {str(e)[:160]}')
    raise err

REPEAT = re.compile(r'(.{1,6}?)\1{3,}')
# whisper 在音乐上常编出来的句子（训练数据里的字幕署名、片尾）。实测《雨爱》DJ 版：
# 「简体中文歌词」「作词曲来自网易飓风计划」「字幕志愿者杨茜茜」
JUNK = re.compile(r'字幕|志愿者|简体中文|中文歌词|作词|作曲|词曲|编曲|网易|飓风计划|云音乐|QQ音乐|酷狗|订阅|点赞|转发|打赏|关注|感谢观看|谢谢观看|明镜|栏目|本期|下期|未经授权|版权所有')
def drop_junk(ws):
    """去掉识别结果里的「字幕署名」类幻觉：把这一段的字连起来找 JUNK，命中的字去掉（字幕/志愿者 后面紧跟的 3 个字是人名，一起去掉）。"""
    if not ws: return ws
    txt = ''.join(w['u'] for w in ws)
    starts, acc = [], 0
    for w in ws: starts.append(acc); acc += len(w['u'])
    bad = set()
    for mt in JUNK.finditer(txt):
        a, b = mt.start(), mt.end() + (3 if mt.group() in ('字幕', '志愿者') else 0)
        bad |= {i for i, s0 in enumerate(starts) if s0 < b and s0 + len(ws[i]['u']) > a}
    return [w for i, w in enumerate(ws) if i not in bad]
def transcribe(y, pieces, model_name, device, lang, prompts=None):
    """逐片识别，返回 [{'u': 单位, 't0', 't1', 'p': 概率, 'piece': 片号}]。"""
    m, dev = get_model(model_name, device)
    words = []
    for k, (a, b) in enumerate(pieces):
        seg = y[int(a * SR):int(b * SR)]
        if len(seg) < SR * 0.3: continue
        pr = (prompts or {}).get(k)
        segs, _ = m.transcribe(seg, language=lang, word_timestamps=True, vad_filter=False, beam_size=5,
                               condition_on_previous_text=False, no_speech_threshold=0.6,
                               initial_prompt=pr or None)   # 不给默认提示：实测 large-v3 会把「以下是简体中文歌词」原样当歌词吐出来
        for sg in segs:
            if sg.no_speech_prob > 0.7 and sg.avg_logprob < -0.8: continue   # 很可能是没人唱的地方编出来的
            if sg.compression_ratio > 2.6: continue                           # 一直重复同一个词
            if REPEAT.search(sg.text.replace(' ', '')): continue
            seg_w = []
            for w in (sg.words or []):
                us = units(to_simp(w.word))
                if not us: continue
                if w.end - w.start > 4 and w.probability < 0.6: continue   # 一个字拖了 4 秒以上又没把握：多半是没人声处编的
                for q, u in enumerate(us):   # 一个词里有几个字：时间平分
                    t0 = w.start + (w.end - w.start) * q / len(us); t1 = w.start + (w.end - w.start) * (q + 1) / len(us)
                    seg_w.append({'u': u, 't0': round(a + t0, 3), 't1': round(a + t1, 3), 'p': round(w.probability, 3), 'piece': k})
            words += drop_junk(seg_w)
        print(f'  片 {k + 1}/{len(pieces)}  {mmss(a)}–{mmss(b)}  累计 {len(words)} 字', flush=True)
    return words

# ======================================================================================
# 对齐
# ======================================================================================
def align(ref, asr, ref_open=-0.7, ref_ext=-0.12, skip_open=-0.5, skip_ext=-0.03):
    """全局对齐（三状态仿射）：ref 是歌词单位，asr 是识别单位。
    M = 这个字对上了；X = 跳过识别出来的一串（幻觉、和声、口水词），整串只扣 0.5 + 每个 0.03；
    Y = 跳过歌词里的一串（这段没唱的句子、没听出来的字），整串扣 0.7 + 每个 0.12。
    音频开始前、结束后的歌词和识别内容都免费跳过（剪辑片段、前奏里的幻觉）。返回每个歌词单位对上的识别下标（或 None）和相似度。"""
    n, m = len(ref), len(asr)
    au = [w['u'] for w in asr]
    NEG = np.float32(-1e9)
    M = np.full((n + 1, m + 1), NEG, np.float32); X = M.copy(); Y = M.copy()
    BM = np.zeros((n + 1, m + 1), np.int8); BX = BM.copy(); BY = BM.copy()   # 记从哪个状态来：0 M 1 X 2 Y
    M[0, 0] = 0; X[0, 1:] = 0; BX[0, 1:] = 1; Y[1:, 0] = 0; BY[1:, 0] = 2; BY[1, 0] = 0
    for i in range(1, n + 1):
        ri = ref[i - 1]
        sv = np.array([sim(ri, a) for a in au], np.float32)
        P = np.stack([M[i - 1], X[i - 1], Y[i - 1]])               # 上一行三种状态
        # M：对角来
        arg = P[:, :-1].argmax(0); M[i, 1:] = P[:, :-1].max(0) + sv; BM[i, 1:] = arg
        # Y：上面来（跳过歌词这个字）；最后一列（音频结束后）免费
        ro = np.full(m, ref_open, np.float32); re_ = np.full(m, ref_ext, np.float32); ro[-1] = 0; re_[-1] = 0
        cy = np.stack([P[0, 1:] + ro, P[1, 1:] + ro, P[2, 1:] + re_])
        Y[i, 1:] = cy.max(0); BY[i, 1:] = cy.argmax(0)
        # X：左边来（跳过识别单位），沿 j 顺序算；最后一行免费
        ao, ae = (0.0, 0.0) if i == n else (skip_open, skip_ext)
        Mi, Yi, Xi, bx = M[i], Y[i], X[i], BX[i]
        for j in range(1, m + 1):
            c0 = Mi[j - 1] + ao; c1 = Xi[j - 1] + ae; c2 = Yi[j - 1] + ao
            if c0 >= c1 and c0 >= c2: Xi[j] = c0; bx[j] = 0
            elif c1 >= c2: Xi[j] = c1; bx[j] = 1
            else: Xi[j] = c2; bx[j] = 2
    i, j = n, m
    st = int(np.argmax([M[n, m], X[n, m], Y[n, m]]))
    mp = [None] * n; sc = [0.0] * n
    while i > 0 or j > 0:
        if st == 0:
            if i == 0 or j == 0: st = 1 if i == 0 else 2; continue
            s_ = sim(ref[i - 1], au[j - 1])
            if s_ > 0: mp[i - 1] = j - 1; sc[i - 1] = s_
            st = BM[i, j]; i -= 1; j -= 1
        elif st == 1:
            if j == 0: st = 2; continue
            st = BX[i, j]; j -= 1
        else:
            if i == 0: st = 1; continue
            st = BY[i, j]; i -= 1
    return mp, sc

def place_lines(lines, asr, act, dur, hop=0.05):
    """lines: [(参考时间, 文字)]。返回每句 {t, end, conf, heard, matched}。"""
    ref, owner = [], []
    for li, (_, s) in enumerate(lines):
        for u in units(s): ref.append(u); owner.append(li)
    mp, sc = align(ref, asr) if asr else ([None] * len(ref), [0.0] * len(ref))
    res = []
    for li, (rt, s) in enumerate(lines):
        idx = [k for k in range(len(ref)) if owner[k] == li]
        hit = [(k, mp[k]) for k in idx if mp[k] is not None]
        if len(hit) > 1:   # 一句里对上的字要挨着：中间断开 > 2.5 秒的，只留得分最高的那一团（零星对到远处的字不算）
            groups, g = [], [hit[0]]
            for h in hit[1:]:
                if asr[h[1]]['t0'] - asr[g[-1][1]]['t1'] > 2.5: groups.append(g); g = [h]
                else: g.append(h)
            groups.append(g)
            hit = max(groups, key=lambda g: sum(sc[k] for k, _ in g))
        keep = {k for k, _ in hit}
        conf = sum(sc[k] for k in idx if k in keep) / max(1, len(idx))
        strong = sum(1 for k, _ in hit if sc[k] >= 0.85)   # 同字或同音
        r = {'text': s, 'ref_t': rt, 'conf': round(conf, 3), 'n': len(idx), 'matched': len(hit), 'strong': strong}
        if hit:
            k0, j0 = hit[0]; k1, j1 = hit[-1]
            span = asr[j1]['t1'] - asr[j0]['t0']
            cps = span / max(1, k1 - k0 + 1) if k1 > k0 else 0.3          # 每个字大概多久
            cps = min(max(cps, 0.12), 0.8)
            r['t'] = asr[j0]['t0'] - (k0 - idx[0]) * cps                   # 句首几个字没对上：往前推
            r['end'] = asr[j1]['t1'] + (idx[-1] - k1) * cps
            r['heard'] = ''.join(w['u'] for w in asr[j0:j1 + 1])
        res.append(r)
    # 站得住的句子：对上的字够多（置信度 ≥ 0.25，或有 2 个以上同字/同音挨着）
    ok = lambda r: 't' in r and (r['conf'] >= 0.25 or r['strong'] >= 2)
    # 这段音频没唱的句子（歌词是整首、音频只是一段）：在第一句、最后一句「扎实对上」的句子之外，又没站住的，标 drop。
    # 扎实 = ≥3 个同字/同音，或 2 个且置信度 ≥ 0.45
    solid = [i for i, r in enumerate(res) if 't' in r and (r['strong'] >= 3 or (r['strong'] >= 2 and r['conf'] >= 0.45))]
    for i, r in enumerate(res):
        if solid and (i < solid[0] or i > solid[-1]) and not ok(r): r['drop'] = True
    # 对不上的句子：参考时间（线性映射到这个版本）或者夹在前后两句之间
    fit = _fit_ref_times([r for r in res if not r.get('drop')])
    for i, r in enumerate(res):
        if r.get('drop') or ok(r): continue
        prev = next((res[k]['end'] for k in range(i - 1, -1, -1) if not res[k].get('drop') and ok(res[k])), 0.0)
        nxt = next((res[k]['t'] for k in range(i + 1, len(res)) if not res[k].get('drop') and ok(res[k])), dur)
        if fit and r['ref_t'] is not None:
            t = fit[0] * r['ref_t'] + fit[1]
            if prev - 0.5 <= t <= nxt: r['t'] = max(prev, t); r['end'] = min(nxt, r['t'] + 0.3 * max(4, r['n'])); r['how'] = '参考时间'; continue
        # 前后之间平分（同一个空档里连着几句没对上时，按字数分）
        run = [k for k in range(i, len(res)) if not ok(res[k]) and not res[k].get('drop') or k == i]
        run = [k for k in run if k == i or (k - 1 in run)]
        tot = sum(res[k]['n'] for k in run) or 1
        acc = sum(res[k]['n'] for k in run if k < i)
        r['t'] = prev + (nxt - prev) * acc / tot; r['end'] = prev + (nxt - prev) * (acc + r['n']) / tot; r['how'] = '估计'
    # 用人声轨收紧：句首落在没人声的地方就往后挪到人声开始（最多 1 秒），句尾挪到人声结束 + 0.15 秒
    for i, r in enumerate(res):
        if r.get('drop'): continue
        if act is not None and len(act):
            a = int(r['t'] / hop)
            if 0 <= a < len(act) and not act[a]:
                k = a
                while k < len(act) and not act[k] and (k - a) * hop < 1.0: k += 1
                if k < len(act) and act[k]: r['t'] = k * hop
            b = int(r['end'] / hop)
            if 0 < b < len(act) and not act[min(b, len(act) - 1)]:
                k = b
                while k > a and not act[k - 1] and (b - k) * hop < 1.5: k -= 1
                if k > a: r['end'] = k * hop + 0.15
        r['t'] = round(max(0.0, r['t']), 2); r['end'] = round(min(dur, max(r['end'], r['t'] + 0.4)), 2)
    kept = [r for r in res if not r.get('drop')]
    for a_, b_ in zip(kept, kept[1:]):   # 不能重叠、不能倒序
        if b_['t'] < a_['t'] + 0.2: b_['t'] = round(a_['t'] + 0.2, 2)
        if a_['end'] > b_['t'] - 0.05: a_['end'] = round(max(a_['t'] + 0.2, b_['t'] - 0.05), 2)
    for r in kept: r['end'] = round(max(r['end'], r['t'] + 0.2), 2)
    return res

def _fit_ref_times(res):
    """参考歌词带时间（别的版本的 LRC）时，用对得好的句子拟合 新时间 = a × 参考时间 + b（DJ 加速版 a≠1）。"""
    pts = [(r['ref_t'], r['t']) for r in res if r.get('ref_t') is not None and 't' in r and r['conf'] >= 0.6]
    if len(pts) < 3: return None
    x, y = np.array(pts).T
    best = None
    for _ in range(3):   # 去掉偏差大的点再拟合
        a, b = np.polyfit(x, y, 1)
        err = np.abs(a * x + b - y)
        best = (a, b)
        keep = err < max(1.0, np.median(err) * 3)
        if keep.all() or keep.sum() < 3: break
        x, y = x[keep], y[keep]
    return best if 0.6 < best[0] < 1.6 else None

def lines_from_asr(asr, act, hop=0.05):
    """没有歌词文字：按人声停顿断句（停 ≥0.45 秒且已有 4 个字，或停 ≥0.9 秒，或 14 个字了）。"""
    out, cur = [], []
    for w in asr:
        if cur:
            gap = w['t0'] - cur[-1]['t1']
            if (gap >= 0.45 and len(cur) >= 4) or gap >= 0.9 or len(cur) >= 14 or w['piece'] != cur[-1]['piece']:
                out.append(cur); cur = []
        cur.append(w)
    if cur: out.append(cur)
    res = []
    for c in out:
        txt = ''.join(w['u'] if CJK.match(w['u']) else ' ' + w['u'] + ' ' for w in c)
        txt = re.sub(r'\s+', ' ', txt).strip()
        p = sum(w['p'] for w in c) / len(c)
        res.append({'text': txt, 't': round(c[0]['t0'], 2), 'end': round(c[-1]['t1'] + 0.1, 2), 'conf': round(p, 3),
                    'n': len(c), 'matched': len(c), 'heard': txt, 'how': '识别'})
    for i in range(len(res) - 1):
        if res[i]['end'] > res[i + 1]['t'] - 0.05: res[i]['end'] = round(res[i + 1]['t'] - 0.05, 2)
    return res

# ======================================================================================
# 输出
# ======================================================================================
def write_lrc(path, res, head):
    L = list(head)
    for i, r in enumerate(res):
        L.append(f"[{mmss(r['t'])}]{r['text']}")
        nxt = res[i + 1]['t'] if i + 1 < len(res) else None
        if nxt is None or nxt - r['end'] > 0.3: L.append(f"[{mmss(r['end'])}]")   # 空时间行 = 上一句结束
    open(path, 'w', encoding='utf-8').write('\n'.join(L) + '\n')

def write_srt(path, res):
    f = lambda t: '%02d:%02d:%02d,%03d' % (t // 3600, t % 3600 // 60, t % 60, round(t % 1 * 1000) % 1000)
    open(path, 'w', encoding='utf-8').write(''.join(f"{i + 1}\n{f(r['t'])} --> {f(r['end'])}\n{r['text']}\n\n" for i, r in enumerate(res)))

def flag(r):
    if r.get('how') == '识别': return '?' if r['conf'] < 0.6 else ''
    if r['conf'] < 0.45 or r.get('how') == '估计': return '✗'
    if r['conf'] < 0.7 or r.get('how') == '参考时间': return '?'
    return ''

def leak_ratio(v, mix, res, dur):
    """分离质量：没人唱的地方人声轨还有多少能量（相对唱的地方）。越低越好；> -12 dB 说明伴奏漏进人声轨了。"""
    if v is None or not res: return None
    sung = np.zeros(int(dur / 0.05) + 1, bool)
    for r in res: sung[int(r['t'] / 0.05):int(r['end'] / 0.05) + 1] = True
    db = rms_db(v); n = min(len(db), len(sung)); db, sung = db[:n], sung[:n]
    mdb = rms_db(mix)[:n]; loud = mdb > np.percentile(mdb, 30)   # 只看有音乐的地方
    if sung.sum() < 20 or (~sung & loud).sum() < 20: return None
    p = lambda m: 10 * np.log10(np.mean(10 ** (db[m] / 10)) + 1e-12)
    return round(p(~sung & loud) - p(sung), 1)

def combine(placed):
    """几种识别来源（人声 / 原曲 / 带提示）各对齐一遍后合成一份：整体对得最好的那一版当底，
    某句在别的版本里置信度高 0.2 以上、时间又在前后两句之间，才换成那一版。返回 (句子, 去掉的没唱句子)。"""
    score = lambda k: sum(r['conf'] * r['n'] for r in placed[k] if not r.get('drop'))
    base = max(placed, key=lambda k: (score(k), k.endswith('提示')))
    B = placed[base]; res = []
    for i, r0 in enumerate(B):
        r = dict(r0); r['src'] = base; r['alt'] = {k: placed[k][i]['conf'] for k in placed}
        if not r.get('drop'):
            prev_end = next((B[j]['end'] for j in range(i - 1, -1, -1) if not B[j].get('drop')), 0.0)
            nxt_t = next((B[j]['t'] for j in range(i + 1, len(B)) if not B[j].get('drop')), 1e9)
            for k, P in placed.items():
                o = P[i]
                if k != base and not o.get('drop') and o.get('how', '对齐') == '对齐' and o['conf'] >= r['conf'] + 0.2 \
                        and prev_end - 0.5 <= o['t'] and o['end'] <= nxt_t + 0.5:
                    alt = r['alt']; r = dict(o); r['src'] = k; r['alt'] = alt
        res.append(r)
    dropped = [r for r in res if r.get('drop')]
    res = [r for r in res if not r.get('drop')]
    for r in [r for r in res if r.get('how') == '估计' and (r['end'] - r['t']) < 0.15 * max(1, r['n'])]:   # 挤在很窄的空档里：多半没唱
        dropped.append(r); res.remove(r)
    for a_, b_ in zip(res, res[1:]):   # 保证顺序、不重叠、结束不早于开始
        if b_['t'] < a_['t'] + 0.2: b_['t'] = round(a_['t'] + 0.2, 2)
        if a_['end'] > b_['t'] - 0.05: a_['end'] = round(b_['t'] - 0.05, 2)
    for r in res: r['end'] = round(max(r['end'], r['t'] + 0.2), 2)
    return res, dropped

def main():
    ap = argparse.ArgumentParser(description='歌词对时间')
    ap.add_argument('audio'); ap.add_argument('--text'); ap.add_argument('--out'); ap.add_argument('--work')
    ap.add_argument('--sep', default='auto', choices=['auto', 'demucs', 'roformer', 'none'])
    ap.add_argument('--model', default='auto'); ap.add_argument('--device', default='auto', choices=['auto', 'cuda', 'cpu'])
    ap.add_argument('--lang', default='zh'); ap.add_argument('--preview', action='store_true'); ap.add_argument('--compare', action='store_true')
    ap.add_argument('--no-prompt', action='store_true', help='第二遍识别不用歌词当提示')
    A = ap.parse_args()
    if not os.path.exists(A.audio): print(f'找不到音频：{A.audio}'); sys.exit(2)
    if shutil.which('ffmpeg') is None: print('没找到 ffmpeg'); sys.exit(2)
    OUT = os.path.abspath(A.out or os.path.splitext(A.audio)[0] + '.lrc')
    WORK = os.path.abspath(A.work or os.path.join(os.path.dirname(OUT), '_lyrics_work')); os.makedirs(WORK, exist_ok=True)
    lines = read_text(A.text) if A.text else None
    if A.text and not lines: print(f'{A.text} 里没读到歌词'); sys.exit(2)
    if lines and not HAVE_PINYIN:
        print('提醒：没装 pypinyin，只能按「同一个字」对齐，同音错字对不上。装上更准：pip install pypinyin')
    try: import faster_whisper  # noqa: F401
    except ImportError:
        print('没装 faster-whisper，没法听歌对时间：pip install faster-whisper（有歌词文字也需要它来定时间）'); sys.exit(1)

    mix = load(A.audio); dur = len(mix) / SR
    cuda = has_cuda() if A.device != 'cpu' else False
    model = A.model if A.model != 'auto' else ('large-v3' if cuda else 'medium')
    if A.device == 'auto': A.device = 'cuda' if cuda else 'cpu'
    print(f'音频 {dur:.1f} 秒；识别模型 {model}（{"显卡" if cuda else "CPU"}）；歌词文字 {len(lines) if lines else 0} 句', flush=True)

    # 1. 分离人声
    # 实测《雨爱》DJ 版：RoFormer 分得干净（8 句全对上），demucs 漏伴奏严重，所以 RoFormer 优先
    order = {'auto': ['roformer', 'demucs'], 'demucs': ['demucs'], 'roformer': ['roformer'], 'none': []}[A.sep]
    vpath, sep_note = None, '不分离（--sep none）' if A.sep == 'none' else ''
    notes = []
    for how in order:
        vpath, why = separate(A.audio, WORK, how, A.device)
        if vpath: sep_note = why; break
        notes.append(why)
    if not vpath and A.sep != 'none': sep_note = '没分离（' + '；'.join(notes) + '）：直接用原曲识别。装 demucs 会准很多：pip install demucs'
    voc = load(vpath) if vpath else None
    print('人声：' + sep_note, flush=True)

    # 2. 切片：有人声轨用人声轨，没有就用原曲（原曲上的人声判断不准，片会多一些）
    act = vocal_activity(voc if voc is not None else mix)
    if voc is not None:
        pieces = slices(act, dur)
        if sum(b - a for a, b in pieces) < 0.15 * dur:   # 判出来的人声太少：多半是阈值不合这首歌，退回整首送
            print('人声片太少（不到全曲 15%），改成整首切块送去识别', flush=True)
            pieces = slices(np.ones_like(act), dur, quiet=rms_db(voc if voc is not None else mix))
    else:   # 没分离：原曲上判断人声不靠谱，整首切块送去识别（靠识别自己的 no_speech 过滤）
        pieces = slices(np.ones_like(act), dur, quiet=rms_db(voc if voc is not None else mix))
        act = None
    sung = sum(b - a for a, b in pieces) - sum(max(0, pieces[i][1] - pieces[i + 1][0]) for i in range(len(pieces) - 1))   # 片之间留的重叠不重复算
    print(f'切成 {len(pieces)} 片，共 {sung:.0f} 秒送去识别（跳过 {dur - sung:.0f} 秒没人声的部分）', flush=True)

    # 3. 识别（缓存：同一音频 + 模型 + 来源 + 切片 只识别一次）
    key = hashlib.md5(open(A.audio, 'rb').read(1 << 20) + json.dumps([model, A.lang, pieces]).encode()).hexdigest()[:10]
    def asr_of(src_name, y, prompts=None):
        ph = ('_p' + hashlib.md5(json.dumps(prompts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:6]) if prompts else ''
        tag = f"asr_{src_name}_{model.replace('/', '_')}_{key}{ph}.json"
        p = os.path.join(WORK, tag)
        if os.path.exists(p): return json.load(open(p, encoding='utf-8'))
        print(f'识别（{src_name}{"，用歌词做提示" if prompts else ""}）…', flush=True)
        w = transcribe(y, pieces, model, A.device, A.lang, prompts)
        json.dump(w, open(p, 'w', encoding='utf-8'), ensure_ascii=False); return w

    cands = {}
    if voc is not None: cands['人声'] = asr_of('vocals', voc)
    if voc is None or lines or A.compare: cands['原曲'] = asr_of('mix', mix)   # 有歌词时两版都识别，每句挑对得好的

    if lines:
        placed = {k: place_lines(lines, w, act, dur) for k, w in cands.items()}
        # 第二遍：每片用对到这片里的歌词做提示，再识别一遍（实测错字少很多）。人声、原曲都做
        if not A.no_prompt:
            best_src = max(placed, key=lambda k: sum(r['conf'] * r['n'] for r in placed[k] if not r.get('drop')))
            prompts = {}
            for k, (a, b) in enumerate(pieces):
                inside = [r['text'] for r in placed[best_src] if not r.get('drop') and r['end'] > a and r['t'] < b]
                if inside: prompts[k] = '，'.join(inside)[:200]
            if prompts:
                for name, y, tag in (('人声', voc, 'vocals'), ('原曲', mix, 'mix')):
                    if name in cands:
                        cands[name + '+提示'] = asr_of(tag, y, prompts)
                        placed[name + '+提示'] = place_lines(lines, cands[name + '+提示'], act, dur)
        res, dropped = combine(placed)
        if dropped: print(f'歌词文字里有 {len(dropped)} 句在这段音频里没唱（多半是剪辑片段），已去掉：' + '；'.join(r['text'] for r in dropped[:8]) + ('…' if len(dropped) > 8 else ''))
        mode = '歌词文字 + 对时间'
    else:
        src = '人声' if '人声' in cands else '原曲'
        res = lines_from_asr(cands[src], act)
        for r in res: r['src'] = src
        mode = '只靠识别（会有错字，要人核对）'
        if len(res) < 3:
            print(f'只识别出 {len(res)} 句，太少（可能是纯音乐或人声太小），不生成歌词'); sys.exit(1)

    # 4. 输出
    head = [f'[re:align_lyrics {mode}；人声 {sep_note.split("：")[0]}；模型 {model}]']
    write_lrc(OUT, res, head)
    base = os.path.splitext(OUT)[0]
    js = {'version': 1, 'audio': os.path.basename(A.audio), 'duration': round(dur, 3), 'mode': 'text' if lines else 'asr',
          'separation': sep_note, 'model': model,
          'lines': [{'t': r['t'], 'end': r['end'], 'text': r['text'], 'conf': r['conf'], 'flag': flag(r) or 'ok',
                     'heard': r.get('heard', ''), 'how': r.get('how', '对齐'), 'src': r.get('src', '')} for r in res],
          'vocal_pieces': [[round(a, 2), round(b, 2)] for a, b in pieces]}
    jpath = os.path.join(os.path.dirname(OUT), 'lyrics_align.json')
    json.dump(js, open(jpath, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    srt = base + '.srt'; write_srt(srt, res)
    leak = leak_ratio(voc, mix, res, dur)

    bad = [r for r in res if flag(r) == '✗']; mid = [r for r in res if flag(r) == '?']
    R = ['# 歌词对时间检查', '',
         f'- 做法：{mode}', f'- 人声：{sep_note}', f'- 识别模型：{model}（{"显卡" if cuda else "CPU"}）',
         f'- 送去识别的人声片：{len(pieces)} 片，{sung:.0f} / {dur:.0f} 秒']
    if leak is not None:
        R.append(f'- 分离质量：没唱的地方人声轨能量 {leak} dB（相对唱的地方）' + ('　⚠ 伴奏漏进人声轨比较多，识别可能把乐器声听成字' if leak > -12 else '　正常'))
    R += [f'- 结果：{len(res)} 句，✗ 需要核对 {len(bad)} 句，? 建议听一下 {len(mid)} 句', '',
          '✗ = 和听到的对不上、时间是估的；? = 部分对上。置信度：1 = 每个字都听到了，0.85 = 同音字，< 0.45 = 基本没对上。',
          '核对方法：打开 ' + os.path.basename(srt) + '（和音频同名放一起用播放器播），或者加 --preview 出带字幕的视频。', '',
          '| # | 开始 | 结束 | 歌词 | 听到的 | 置信度 | 来源 | |', '|---|---|---|---|---|---|---|---|']
    for i, r in enumerate(res):
        alt = ' / '.join(f'{k} {v:.2f}' for k, v in r.get('alt', {}).items()) if args_compare(A) else r.get('src', '')
        R.append(f"| {i + 1} | {mmss(r['t'])} | {mmss(r['end'])} | {r['text']} | {r.get('heard', '')} | {r['conf']:.2f} | {alt} | {flag(r)} |")
    if lines:
        covered = np.zeros(int(dur / 0.05) + 1, bool)
        for r in res: covered[int(r['t'] / 0.05):int(r['end'] / 0.05) + 1] = True
        extra = [(a, b) for a, b in pieces if not covered[int((a + 0.5) / 0.05):int((b - 0.5) / 0.05) + 1].any() and b - a > 2.5]
        if extra:
            R += ['', '## 有人声但歌词里没有的段', '', '可能是歌词文字少了几句（重复的副歌、念白、和声），也可能是乐器被当成人声。听一下，确实在唱就把词补进歌词文字再跑一次。', '']
            src = cands.get('人声') or cands.get('原曲') or []
            for a, b in extra:
                h = ''.join(w['u'] for w in src if a <= w['t0'] < b)
                R.append(f'- {mmss(a)}–{mmss(b)}：听到「{h[:40]}」')
    open(os.path.join(os.path.dirname(OUT), 'lyrics_check.md'), 'w', encoding='utf-8').write('\n'.join(R) + '\n')

    if A.preview:
        pv = os.path.join(os.path.dirname(OUT), 'lyrics_preview.mp4')
        sub = os.path.basename(srt).replace("'", r"\'")   # 在 srt 所在目录里跑 ffmpeg，免得 Windows 盘符的冒号要转义
        cmd = ['ffmpeg', '-y', '-v', 'error', '-i', os.path.abspath(A.audio), '-filter_complex',
               f"[0:a]showwaves=s=1280x720:mode=cline:colors=0x6b5bd6,format=yuv420p,subtitles='{sub}':force_style='FontSize=28,Alignment=2,MarginV=60'[v]",
               '-map', '[v]', '-map', '0:a', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '28', '-c:a', 'aac', '-shortest', pv]
        r = subprocess.run(cmd, capture_output=True, cwd=os.path.dirname(srt))
        print('试听视频：' + pv if r.returncode == 0 else '试听视频没做成（ffmpeg 可能没带字幕滤镜）：' + r.stderr.decode('utf-8', 'replace')[-200:])

    print(f'\n歌词：{len(res)} 句 → {OUT}\n时间轴：{jpath}\n检查：{os.path.join(os.path.dirname(OUT), "lyrics_check.md")}（✗ {len(bad)} 句，? {len(mid)} 句）')
    if bad: print('有 ✗ 的句子：时间是估的，一定要听一遍：' + '；'.join(f"{mmss(r['t'])} {r['text']}" for r in bad[:6]))
    sys.exit(0)

def args_compare(A): return A.compare

if __name__ == '__main__':
    main()

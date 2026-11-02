#!/usr/bin/env python3
"""没有 .lrc 时自动找带时间的歌词 → lyrics.lrc。new_project.py 没给 --lrc 时会自动调用它。
按顺序试，哪一步拿到就停：
  1. 联网查 lrclib.net（免费的同步歌词库）：按歌名、歌手、时长找最接近的一版
  2. 本地语音识别：装了 faster-whisper 才会用（pip install faster-whisper），按逐词时间断句；
     再装了 demucs（pip install demucs）会先分离人声再识别，准很多。歌声识别总会有些错字
  3. 都不行：不生成，告诉你原因；MV 照样能做，只是没有字幕
用法：python $SKILL/scripts/fetch_lyrics.py song.mp3 [--out lyrics.lrc] [--title 歌名] [--artist 歌手] [--no-online] [--no-asr] [--model small|medium] [--lang zh] [--no-separate]
  --model  faster-whisper 模型：small 快，medium 准（中文推荐 medium，有显卡时更快）
  歌名、歌手不给时，先读音频文件里的标签，再看文件名（「歌手 - 歌名.mp3」或「歌名.mp3」）
退出码：0 找到了；1 没找到（不算出错，跳过字幕就行）
自动拿到的歌词一定要人听一遍核对：版本不对（现场版、伴奏版）或者识别错字都会让字幕对不上。"""
import argparse, json, os, re, subprocess, sys, urllib.parse, urllib.request
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ap = argparse.ArgumentParser(); ap.add_argument('audio'); ap.add_argument('--out'); ap.add_argument('--title'); ap.add_argument('--artist')
ap.add_argument('--no-online', action='store_true'); ap.add_argument('--no-asr', action='store_true'); ap.add_argument('--model', default='small'); ap.add_argument('--lang', default='zh'); ap.add_argument('--no-separate', action='store_true')
A = ap.parse_args()
OUT = A.out or os.path.splitext(A.audio)[0] + '.lrc'
API = os.environ.get('LRCLIB_URL', 'https://lrclib.net/api')

def probe():
    try: d = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:format_tags', '-of', 'json', A.audio],
                                       capture_output=True, check=True).stdout.decode('utf-8', 'replace'))['format']
    except Exception: return None, {}
    return float(d.get('duration') or 0) or None, {k.lower(): v for k, v in (d.get('tags') or {}).items()}

dur, tags = probe()
stem = re.sub(r'[\(（\[【].*?[\)）\]】]', '', os.path.splitext(os.path.basename(A.audio))[0]).strip()   # 去掉 (Live) 【伴奏】 之类
f_artist, f_title = (s.strip() for s in stem.split(' - ', 1)) if ' - ' in stem else ('', stem)
title = A.title or tags.get('title') or f_title
artist = A.artist or tags.get('artist') or f_artist
mmss = lambda t: f'{int(t // 60):02d}:{t % 60:05.2f}'
log = []

def save(text, how):
    open(OUT, 'w', encoding='utf-8').write(text.strip() + '\n')
    n = sum(1 for l in text.splitlines() if re.match(r'\[\d+:\d+', l) and l.split(']')[-1].strip())
    print(f'拿到歌词（{how}）：{n} 句 → {OUT}\n请听一遍核对：开头几句的时间对不对、字有没有错。')
    sys.exit(0)

# ---------- 1. lrclib ----------
def get(path, **q):
    url = f'{API}/{path}?' + urllib.parse.urlencode({k: v for k, v in q.items() if v})
    req = urllib.request.Request(url, headers={'User-Agent': 'voxel-mv-skill (https://github.com/lemomo-ai/lemo-opuscar)'})
    with urllib.request.urlopen(req, timeout=15) as r: return json.loads(r.read().decode('utf-8'))

if not A.no_online and title:
    try:
        found = []
        try:
            one = get('get', track_name=title, artist_name=artist, duration=round(dur) if dur else None)
            if one: found.append(one)
        except Exception: pass   # get 要精确匹配，查不到时 404，接着用 search
        for q in ({'track_name': title, 'artist_name': artist}, {'q': f'{title} {artist}'.strip()}, {'q': title}):
            if found and any(f.get('syncedLyrics') for f in found): break
            try: found += get('search', **q) or []
            except Exception as e:
                if not found: raise
        synced = [f for f in found if f.get('syncedLyrics') and not f.get('instrumental')]
        # 时长差 5 秒以内的才算同一个版本；同等条件下歌手一致的优先
        ok = [f for f in synced if not dur or abs((f.get('duration') or 0) - dur) <= 5]
        ok.sort(key=lambda f: (abs((f.get('duration') or 0) - (dur or 0)), artist.lower() not in (f.get('artistName') or '').lower()))
        if ok:
            f = ok[0]
            save(f"[ti:{f.get('trackName', title)}]\n[ar:{f.get('artistName', artist)}]\n" + f['syncedLyrics'],
                 f"lrclib：{f.get('artistName')} -《{f.get('trackName')}》，时长 {f.get('duration')} 秒，本歌 {dur and round(dur)} 秒")
        if synced: log.append(f'lrclib 有 {len(synced)} 版带时间的歌词，但时长都和这首差 5 秒以上（可能是别的版本），没用')
        elif found:
            plain = next((f['plainLyrics'] for f in found if f.get('plainLyrics')), None)
            if plain:
                p = os.path.splitext(OUT)[0] + '_无时间.txt'; open(p, 'w', encoding='utf-8').write(plain)
                log.append(f'lrclib 只有不带时间的歌词，存成了 {p}（可以给 AI 当参考，但做不了字幕）')
            else: log.append('lrclib 找到了这首歌，但没有歌词（可能是纯音乐）')
        else: log.append(f'lrclib 上没找到《{title}》{artist and " - " + artist}')
    except Exception as e:
        log.append(f'连不上 lrclib.net（{type(e).__name__}）：可能没联网或被墙')
elif not title: log.append('不知道歌名：用 --title 告诉它')

# ---------- 2. 本地语音识别（faster-whisper，逐词时间）----------
def separate_vocals():
    """装了 demucs 就先把人声分出来再识别（伴奏少了，错字少很多）；没装就直接用原曲。"""
    if A.no_separate: return A.audio
    try: import demucs  # noqa: F401
    except ImportError: return A.audio
    tmp = os.path.join(os.path.dirname(os.path.abspath(OUT)), '_demucs')
    print('先用 demucs 分离人声（CPU 上一首歌要几分钟）…')
    r = subprocess.run([sys.executable, '-m', 'demucs', '--two-stems=vocals', '-o', tmp, A.audio])
    v = [os.path.join(d, f) for d, _, fs in os.walk(tmp) for f in fs if f == 'vocals.wav']
    return v[0] if r.returncode == 0 and v else A.audio

def lines_from_words(words, gap=0.6, maxlen=16):
    """按停顿断句：两个词之间停顿超过 gap 秒、或者一句超过 maxlen 个字就换行。"""
    out, cur = [], []
    for w in words:
        if cur and (w.start - cur[-1].end > gap or sum(len(x.word.strip()) for x in cur) >= maxlen):
            out.append(cur); cur = []
        cur.append(w)
    if cur: out.append(cur)
    return [(c[0].start, ''.join(x.word for x in c).strip()) for c in out]

def asr():
    try: from faster_whisper import WhisperModel
    except ImportError: return None
    src = separate_vocals()
    # 模型：环境变量 > 本地 models/faster-whisper-<name> > 交给 faster-whisper 自己下
    ref = os.environ.get('VOXEL_ASR_MODEL')
    if not ref:
        local = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'models', f'faster-whisper-{A.model}')
        ref = local if os.path.isdir(local) else A.model
    device = os.environ.get('VOXEL_ASR_DEVICE', 'cpu')
    print(f'用 faster-whisper 识别歌词（模型 {ref}；CPU 上整首歌几分钟）…')
    model = WhisperModel(ref, device=device, compute_type='float16' if device == 'cuda' else 'int8')
    try: import onnxruntime  # noqa: F401
    except ImportError: vad = False          # 没装 onnxruntime 就关掉 VAD，少一层依赖冲突
    else: vad = True
    # 不用 PyAV 解码：新版 PyAV 去掉了 metadata_errors，faster-whisper 会直接 TypeError
    import tempfile, wave
    import numpy as np
    wav = os.path.join(tempfile.gettempdir(), 'voxel_asr_in.wav')
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', src, '-ac', '1', '-ar', '16000', '-f', 'wav', wav], check=True)
    with wave.open(wav, 'rb') as w:
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    segs, _ = model.transcribe(samples, language=A.lang, vad_filter=vad, word_timestamps=True,
                               condition_on_previous_text=False,   # 不然间奏里容易一直重复上一句
                               initial_prompt='以下是简体中文歌词。' if A.lang == 'zh' else None)
    rows = []
    for sg in segs:
        rows += lines_from_words(sg.words) if sg.words else [(sg.start, sg.text.strip())]
    return rows

if not A.no_asr:
    try:
        rows = asr()
        if rows is None: log.append('没装 faster-whisper（想在查不到时自动识别：pip install faster-whisper；再装 demucs 能先分离人声，更准）')
        else:
            lines, last = [], None
            for t, s in rows:
                if not s or s == last: continue   # 间奏里的重复句去掉
                lines.append(f'[{mmss(t)}]{s}'); last = s
            if len(lines) >= 3: save('[re:faster-whisper 自动识别，需要人工核对]\n' + '\n'.join(lines), 'faster-whisper 语音识别，会有错字和断句不准')
            log.append(f'faster-whisper 只识别出 {len(lines)} 句，太少了（可能是纯音乐或人声太小），没用')
    except Exception as e: log.append(f'语音识别出错：{type(e).__name__}: {e}')

print('没拿到带时间的歌词，这首歌先不做字幕：\n' + '\n'.join('  - ' + l for l in log) +
      '\n想要字幕：从网易云 / QQ 音乐下载 .lrc（或者自己写），再用 --lrc 建项目。')
sys.exit(1)

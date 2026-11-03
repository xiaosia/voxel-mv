#!/usr/bin/env python3
"""给一首歌拿到「字对、时间也对」的歌词 → lyrics.lrc（+ lyrics_align.json、lyrics_check.md）。new_project.py 没给 --lrc 时会自动调用它。
思路：字和时间分开拿。字从最可靠的地方拿，时间用 align_lyrics.py 对到这首歌（这个版本）的音频上。
  字的来源（按顺序，拿到就停）：
    1. 用户给的歌词文字 --text（纯文本一行一句，或者别处下载的 LRC；网易云 / QQ 音乐复制下来的就行）——最准
    2. 联网查 lrclib.net：带时间的、不带时间的都要，时长对不上（DJ 版、加速版、剪辑版）也照样拿字来用
    3. 都没有：只靠听歌识别（会有错字，要人核对）
  时间：装了 faster-whisper 就用 align_lyrics.py 对齐（再装 demucs 先分离人声，准很多）；
        没装的话，只有 lrclib 上时长相差 5 秒以内的同步歌词能直接用，别的情况就做不了字幕。
用法：python $SKILL/scripts/fetch_lyrics.py song.mp3 [--out lyrics.lrc] [--text 歌词.txt] [--title 歌名] [--artist 歌手]
      [--no-online] [--no-align] [--model auto|medium|large-v3] [--sep auto|demucs|roformer|none] [--preview]
  歌名、歌手不给时，先读音频文件里的标签，再看文件名（「歌手 - 歌名.mp3」「歌名.mp3」；抖音那种「一句歌词#歌名 #歌名dj」会拆开试）
退出码：0 拿到了；1 没拿到（不算出错，跳过字幕就行）
拿到后看 lyrics_check.md：✗ 的句子一定要听一遍。"""
import argparse, json, os, re, subprocess, sys, urllib.parse, urllib.request
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))

ap = argparse.ArgumentParser(); ap.add_argument('audio'); ap.add_argument('--out'); ap.add_argument('--text')
ap.add_argument('--title'); ap.add_argument('--artist')
ap.add_argument('--no-online', action='store_true'); ap.add_argument('--no-align', action='store_true')
ap.add_argument('--no-asr', action='store_true', help='同 --no-align（旧参数）')
ap.add_argument('--model', default='auto'); ap.add_argument('--sep', default='auto'); ap.add_argument('--lang', default='zh')
ap.add_argument('--preview', action='store_true'); ap.add_argument('--no-separate', action='store_true', help='同 --sep none（旧参数）')
A = ap.parse_args()
if A.no_asr: A.no_align = True
if A.no_separate: A.sep = 'none'
OUT = os.path.abspath(A.out or os.path.splitext(A.audio)[0] + '.lrc')
os.makedirs(os.path.dirname(OUT), exist_ok=True)
API = os.environ.get('LRCLIB_URL', 'https://lrclib.net/api')
mmss = lambda t: f'{int(t // 60):02d}:{t % 60:05.2f}'
log = []

def probe():
    try: d = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:format_tags', '-of', 'json', A.audio],
                                       capture_output=True, check=True).stdout.decode('utf-8', 'replace'))['format']
    except Exception: return None, {}
    return float(d.get('duration') or 0) or None, {k.lower(): v for k, v in (d.get('tags') or {}).items()}

dur, tags = probe()

# ---------- 歌名候选 ----------
GENERIC = re.compile(r'^(音乐分享|音乐|分享|热门|热歌|推荐|抖音|dj|dj版|伤感|情歌|经典|老歌|怀旧|翻唱|好歌|歌曲|治愈|emo|bgm|循环|单曲循环|live|现场)$', re.I)
def title_candidates():
    stem = os.path.splitext(os.path.basename(A.audio))[0]
    tags_ = [t.strip() for t in re.findall(r'#([^#\s]+)', stem)]
    base = re.sub(r'#[^#\s]+', '', stem)
    base = re.sub(r'[\(（\[【].*?[\)）\]】]', '', base).strip(' -_')   # 去掉 (Live) 【伴奏】 之类
    f_artist, f_title = (s.strip() for s in base.split(' - ', 1)) if ' - ' in base else ('', base)
    cands = []
    def add(t, a=''):
        t = (t or '').strip()
        if t and not GENERIC.match(t) and (t, a) not in cands: cands.append((t, a))
    add(A.title, A.artist or '')
    add(tags.get('title'), tags.get('artist', ''))
    for t in tags_:   # 「#雨爱 #雨爱dj」：话题词本身、去掉 dj/版 后缀的
        add(re.sub(r'(dj|DJ|版|女声|男声|完整版|抖音版|加速版|慢速版)+$', '', t), A.artist or '')
    add(f_title, f_artist or A.artist or '')
    return cands

def get(path, **q):
    url = f'{API}/{path}?' + urllib.parse.urlencode({k: v for k, v in q.items() if v})
    req = urllib.request.Request(url, headers={'User-Agent': 'song-mv-skill (lyrics lookup)'})
    with urllib.request.urlopen(req, timeout=15) as r: return json.loads(r.read().decode('utf-8'))

def lrclib():
    """返回 (最合适的一条, 时长是否对得上)；没有返回 (None, False)。"""
    found = []
    for title, artist in title_candidates()[:5]:
        try:
            try:
                one = get('get', track_name=title, artist_name=artist, duration=round(dur) if dur else None)
                if one: found.append(one)
            except Exception: pass   # get 要精确匹配，查不到时 404
            for q in ({'track_name': title, 'artist_name': artist}, {'q': f'{title} {artist}'.strip()}):
                try: found += get('search', **q) or []
                except Exception:
                    if not found: raise
            if any(f.get('syncedLyrics') or f.get('plainLyrics') for f in found): break
        except Exception as e:
            log.append(f'连不上 lrclib.net（{type(e).__name__}）：可能没联网或被墙'); return None, False
    good = [f for f in found if not f.get('instrumental') and (f.get('syncedLyrics') or f.get('plainLyrics'))]
    if not good:
        log.append('lrclib 上没找到这首歌的歌词' if not found else 'lrclib 找到了这首歌，但没有歌词（可能是纯音乐）'); return None, False
    art = (A.artist or tags.get('artist') or '').lower()
    def key(f):
        dd = abs((f.get('duration') or 0) - (dur or 0))
        return (dd > 5, not f.get('syncedLyrics'), art not in (f.get('artistName') or '').lower(), dd)
    good.sort(key=key)
    f = good[0]
    return f, bool(dur) and abs((f.get('duration') or 0) - dur) <= 5 and bool(f.get('syncedLyrics'))

def have_asr():
    try: import faster_whisper  # noqa: F401
    except ImportError: return False
    return True

def run_align(text_path):
    cmd = [sys.executable, os.path.join(HERE, 'align_lyrics.py'), A.audio, '--out', OUT, '--model', A.model, '--sep', A.sep, '--lang', A.lang]
    if text_path: cmd += ['--text', text_path]
    if A.preview: cmd += ['--preview']
    return subprocess.run(cmd).returncode == 0

def done(how):
    n = sum(1 for l in open(OUT, encoding='utf-8') if re.match(r'\[\d+:\d+', l) and l.split(']')[-1].strip())
    print(f'拿到歌词（{how}）：{n} 句 → {OUT}')
    chk = os.path.join(os.path.dirname(OUT), 'lyrics_check.md')
    print(f'核对：看 {chk}，✗ 的句子要听一遍' if os.path.exists(chk) else '请听一遍核对：开头几句的时间对不对、字有没有错。')
    sys.exit(0)

# ---------- 1. 字从哪来 ----------
text_path, src, entry, same_ver = None, '', None, False
if A.text:
    if not os.path.exists(A.text): sys.exit(f'找不到歌词文字：{A.text}')
    text_path, src = A.text, '你给的歌词文字'
elif not A.no_online:
    entry, same_ver = lrclib()
    if entry:
        text_path = os.path.splitext(OUT)[0] + '_lrclib.lrc'
        body = entry.get('syncedLyrics') or entry.get('plainLyrics')
        open(text_path, 'w', encoding='utf-8').write(f"[ti:{entry.get('trackName', '')}]\n[ar:{entry.get('artistName', '')}]\n" + body.strip() + '\n')
        src = (f"lrclib：{entry.get('artistName')} -《{entry.get('trackName')}》，{'带时间' if entry.get('syncedLyrics') else '不带时间'}，"
               f"时长 {entry.get('duration')} 秒（这首 {dur and round(dur)} 秒{'，版本一致' if same_ver else '，可能是别的版本'}）")
        print('歌词文字来自 ' + src)

# ---------- 2. 对时间 ----------
if not A.no_align and have_asr():
    if run_align(text_path): done((src + ' + ' if src else '只靠听歌识别，') + '对齐到这首歌的音频')
    log.append('align_lyrics.py 没成功（看上面的输出）')
elif not A.no_align:
    log.append('没装 faster-whisper，没法把歌词对到这首歌上：pip install faster-whisper pypinyin（再装 demucs 先分离人声更准）')

# 没法对齐时的退路：版本一致的 lrclib 同步歌词直接用；用户给的 LRC 原样用
if entry and same_ver:
    open(OUT, 'w', encoding='utf-8').write(open(text_path, encoding='utf-8').read()); done(src + '，没对齐，直接用')
if A.text and re.search(r'\[\d+:\d+', open(A.text, 'rb').read().decode('utf-8', 'ignore')):
    open(OUT, 'w', encoding='utf-8').write(open(A.text, 'rb').read().decode('utf-8', 'ignore')); done('你给的 LRC，没对齐，直接用')
if text_path:
    log.append(f'有歌词文字（{src}），但没有时间、也没法对齐，存在 {text_path}（可以给 AI 当参考，做不了字幕）')

print('没拿到带时间的歌词，这首歌先不做字幕：\n' + '\n'.join('  - ' + l for l in log) +
      '\n想要字幕：pip install faster-whisper pypinyin demucs 后重跑；或者从网易云 / QQ 音乐复制歌词存成 txt，用 --text 给它。')
sys.exit(1)

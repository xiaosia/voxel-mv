#!/usr/bin/env python3
"""建一个 voxel-mv 项目：拷引擎和工具、转音频、生成节拍和歌词数据、接入角色、写空白 plan.json 和占位 shots.js。
用法：
  python $SKILL/scripts/new_project.py <项目目录> --audio song.mp3 [--lrc lyrics.lrc] [--timeline audio.timeline.json] [--report audio.report.md]
         --cast claude,deepseek [--lead claude] [--name 我的MV] [--chars <角色目录>] [--seconds 30]
  --lrc      歌词（时间已经和这个音频对好的 LRC，原样用）。
  --lyrics   只有歌词文字（纯文本，或别的版本的 LRC）：用 scripts/fetch_lyrics.py → align_lyrics.py 把每句对到这首歌上。
             两个都不给：自动找（lrclib 拿字 → 听歌对时间；都没有就只靠识别，再不行就不做字幕）。
             --title / --artist 帮它找对歌；--no-lyrics 不找、不要字幕。结果和检查表在 data/analysis/（lyrics_check.md）
  --timeline 节奏分析结果；不给就自动用 scripts/analyze_audio.py 分析音频（只要 numpy 和 ffmpeg）
  --structure 人工校对过的段落表（structure.json，全曲时间）；不给就用 scripts/song_structure.py 按歌词重复、能量、旋律自动识别
  --cast     用哪些角色，名字是角色目录下的文件夹名（默认在 $SKILL/characters/ 里找）
  --lead     主角（默认 cast 的第一个）
  --seconds  只做多少秒（试做、测试用；默认到歌尾）
  --new-moves N   新舞步预算：最多给角色新出几个舞步动作（默认 0 = 只用现有帧编舞，不出新图；最多 4 = 每人 1 张图）。
                  > 0 时会打印预计出图张数，先告诉用户、等用户同意再出（见 SKILL.md「编舞」）
  --new-moves-cast 只给这几个角色出新舞步（默认主角）
  --from     从第几秒开始（多段接力时做其中一段，见 references/relay.md；页面里仍然用全曲时间）
角色目录的格式见 $SKILL/characters/README.md（参考精灵图生成的帧动画：frames.json + frames/<动作>/NN.png）。
做完后：cd <项目目录>，python tools/run.py doctor，然后 python tools/run.py still 1 5 看占位画面。"""
import argparse, json, os, shutil, subprocess, sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')
os.environ['PYTHONUTF8'] = '1'; os.environ['PYTHONIOENCODING'] = 'utf-8'   # 子脚本读写文件、打印中文都用 UTF-8（中文 Windows 默认是 GBK）
HERE = os.path.dirname(os.path.abspath(__file__)); SKILL = os.path.dirname(HERE); KIT = os.path.join(SKILL, 'kit')
sys.path.insert(0, os.path.join(KIT, 'tools'))
import engine_dist
ap = argparse.ArgumentParser(); ap.add_argument('project')
ap.add_argument('--audio', required=True); ap.add_argument('--timeline')
ap.add_argument('--lrc'); ap.add_argument('--report'); ap.add_argument('--no-lyrics', action='store_true')
ap.add_argument('--title'); ap.add_argument('--artist')
ap.add_argument('--lyrics', help='歌词文字（纯文本一行一句，或别的版本的 LRC）：字用它的，时间对齐到这首歌'); ap.add_argument('--structure')
ap.add_argument('--cast', required=True); ap.add_argument('--lead'); ap.add_argument('--name', default='MV')
ap.add_argument('--chars', default=os.path.join(SKILL, 'characters')); ap.add_argument('--seconds', type=float)
ap.add_argument('--from', dest='frm', type=float, default=0.0)
ap.add_argument('--new-moves', type=int, default=0); ap.add_argument('--new-moves-cast')
A = ap.parse_args()
P = os.path.abspath(A.project); os.makedirs(P, exist_ok=True)
if not os.path.exists(A.audio): sys.exit(f'找不到音频文件：{A.audio}')
if shutil.which('ffmpeg') is None: sys.exit('没找到 ffmpeg：先装 ffmpeg（Windows：winget install Gyan.FFmpeg；macOS：brew install ffmpeg），装完重开终端')
cast = [c.strip() for c in A.cast.split(',') if c.strip()]
for c in cast:
    if not os.path.exists(os.path.join(A.chars, c, 'frames.json')):
        have = sorted(d for d in os.listdir(A.chars) if os.path.exists(os.path.join(A.chars, d, 'frames.json'))) if os.path.isdir(A.chars) else []
        sys.exit(f'找不到角色 {c}：{os.path.join(A.chars, c, "frames.json")} 不存在。' + (f'现在能用的角色：{", ".join(have)}。' if have else '') + f'角色放法见 {os.path.join(SKILL, "characters/README.md")}')

# ---------- 引擎、工具、页面 ----------
for notice in ('LICENSE', 'LICENSE.zh-CN.md', 'THIRD_PARTY_NOTICES.md'):
    shutil.copy2(os.path.join(SKILL, notice), os.path.join(P, notice))
shutil.copytree(os.path.join(SKILL, 'LICENSES'), os.path.join(P, 'LICENSES'), dirs_exist_ok=True)
for d in ('engine', 'vendor', 'tools'):
    shutil.copytree(os.path.join(KIT, d), os.path.join(P, d), dirs_exist_ok=True, ignore=shutil.ignore_patterns('node_modules', '__pycache__'))
engine_dist.write_version(os.path.join(P, 'engine'), SKILL)   # 引擎版本 + 每个文件的 sha256，run.py 校验/升级用
for f, dst in (('index.html', 'index.html'), ('shots_placeholder.js', 'shots.js')):
    if not os.path.exists(os.path.join(P, dst)): shutil.copy(os.path.join(KIT, f), os.path.join(P, dst))
shutil.copytree(os.path.join(SKILL, 'references/style'), os.path.join(P, 'ref/style'), dirs_exist_ok=True)
open(os.path.join(P, 'MODE'), 'w', encoding='utf-8').write('safe\n') if not os.path.exists(os.path.join(P, 'MODE')) else None

# ---------- 数据 ----------
D = os.path.join(P, 'data'); os.makedirs(D, exist_ok=True); os.makedirs(os.path.join(P, 'src'), exist_ok=True)
if not A.timeline:   # 没给节奏分析：自动分析
    an = os.path.join(D, 'analysis'); os.makedirs(an, exist_ok=True)
    subprocess.run([sys.executable, os.path.join(HERE, 'analyze_audio.py'), A.audio, '--out', an], check=True)
    A.timeline = os.path.join(an, 'audio.timeline.json'); A.report = A.report or os.path.join(an, 'audio.report.md')
TL = json.load(open(A.timeline, encoding='utf-8'))
OFF = round(A.frm * 24) / 24                                    # 段起点对齐到整帧
dur = (TL['duration'] - OFF) if not A.seconds else min(TL['duration'] - OFF, A.seconds)
dur = round(dur * 24) / 24
B = TL['beat_times']; n = len(B)                                 # 节拍网格按全曲拟合（引擎用全曲时间）
mx, my = (n - 1) / 2, sum(B) / n
spb = sum((i - mx) * (b - my) for i, b in enumerate(B)) / sum((i - mx) ** 2 for i in range(n)); beat0 = my - spb * mx
err = max(abs(beat0 + i * spb - b) for i, b in enumerate(B))
if err > 1.5 / 24: print(f'提醒：这首歌节拍不太匀（固定网格最大偏差 {err * 1000:.0f} ms）。引擎的踩拍按固定网格走，关键动作建议直接用 TL.beat_times 的时间。')
cut = ['-ss', f'{OFF:.4f}', '-t', f'{dur:.4f}'] if (A.seconds or OFF) else []
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', A.audio, *cut, '-ar', '44100', '-ac', '2', os.path.join(D, 'song.wav')], check=True)
if A.seconds or OFF:   # 截一段：时间轴换成本段本地时间（检查脚本用本地时间，页面用全曲时间 = 本地 + 段起点）
    def sh_(x):
        if isinstance(x, (int, float)): return round(x - OFF, 4)
        if isinstance(x, dict): return {k: (round(v - OFF, 4) if k in ('time', 'start', 'end', 't') and isinstance(v, (int, float)) else v) for k, v in x.items()}
        return x
    def tt(x): return x if isinstance(x, (int, float)) else x.get('time', x.get('start', x.get('t', 0)))
    keepb = [i for i, b in enumerate(TL['beat_times']) if OFF - 1e-6 <= b < OFF + dur]
    for k in ('energy_per_beat', 'vocal_activity_per_beat'):
        if k in TL: TL[k] = [TL[k][i] for i in keepb if i < len(TL[k])]
    keepbar = [i for i, b in enumerate(TL.get('bar_times', [])) if OFF - 1e-6 <= b < OFF + dur]
    if 'energy_per_bar' in TL: TL['energy_per_bar'] = [TL['energy_per_bar'][i] for i in keepbar if i < len(TL['energy_per_bar'])]
    for k in ('beat_times', 'bar_times', 'hits', 'drops', 'sections'):
        if k in TL: TL[k] = [sh_(x) for x in TL[k] if OFF - 1e-6 <= tt(x) < OFF + dur]
    TL['duration'] = dur
json.dump(TL, open(os.path.join(D, 'audio.timeline.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
if not A.lrc and not A.no_lyrics:   # 没给歌词：自动找（找不到不算错，只是没有字幕）
    an = os.path.join(D, 'analysis'); os.makedirs(an, exist_ok=True)
    got = os.path.join(an, 'lyrics.lrc')
    r = subprocess.run([sys.executable, os.path.join(HERE, 'fetch_lyrics.py'), A.audio, '--out', got]
                       + (['--title', A.title] if A.title else []) + (['--artist', A.artist] if A.artist else [])
                       + (['--text', A.lyrics] if A.lyrics else []) + ['--preview'])
    if r.returncode == 0 and os.path.exists(got): A.lrc = got; print('（歌词是自动对齐的：写 TREATMENT 前先看 data/analysis/lyrics_check.md，✗ 的句子听一遍；字不对就用 --lyrics 歌词.txt 重建，别只改字不改时间）')
if A.lrc:
    import re
    raw = open(A.lrc, 'rb').read()
    for enc in ('utf-8-sig', 'gb18030', 'big5'):   # 网上下载的 lrc 有不少是 GBK
        try: lrc_text = raw.decode(enc); break
        except UnicodeDecodeError: pass
    else: lrc_text = raw.decode('utf-8', 'replace')
    keep = []
    for ln in lrc_text.splitlines():   # 截短时去掉 dur 之后开始的句子
        m = re.match(r'\[(\d+):(\d+(?:\.\d+)?)\]', ln)
        if m:
            t0 = int(m.group(1)) * 60 + float(m.group(2))
            if t0 >= OFF + dur or t0 < OFF - 0.5: continue
            if OFF:   # 换成本段本地时间
                ln = re.sub(r'([\[<])(\d+):(\d+(?:\.\d+)?)([\]>])', lambda q: '%s%02d:%05.2f%s' % (q.group(1), *divmod(max(0.0, int(q.group(2)) * 60 + float(q.group(3)) - OFF), 60), q.group(4)), ln)
        keep.append(ln)
    open(os.path.join(D, 'lyrics.lrc'), 'w', encoding='utf-8').write('\n'.join(keep) + '\n')
elif not os.path.exists(os.path.join(D, 'lyrics.lrc')): open(os.path.join(D, 'lyrics.lrc'), 'w', encoding='utf-8').write('[00:00.00]♪\n')
if A.report and os.path.abspath(A.report) != os.path.abspath(os.path.join(D, 'audio.report.md')): shutil.copy(A.report, os.path.join(D, 'audio.report.md'))
# ---------- 段落表（前奏 / 主歌 / 导歌 / 副歌 / 间奏 / 桥段 / 尾奏）：按全曲识别，再换成本段本地时间 ----------
an = os.path.join(D, 'analysis'); os.makedirs(an, exist_ok=True)
if not A.structure:
    subprocess.run([sys.executable, os.path.join(HERE, 'song_structure.py'), '--timeline', A.timeline, '--audio', A.audio, '--out', an]
                   + (['--lyrics', A.lrc] if A.lrc else []), check=False)
    A.structure = os.path.join(an, 'structure.json')
elif os.path.abspath(A.structure) != os.path.abspath(os.path.join(an, 'structure.json')): shutil.copy(A.structure, os.path.join(an, 'structure.json'))
if os.path.exists(A.structure):
    ST = json.load(open(A.structure, encoding='utf-8'))
    parts = []
    for p in ST.get('parts', []):
        a, b = max(p['t0'], OFF), min(p['t1'], OFF + dur)
        if b - a < 0.05: continue
        q = dict(p, t0=round(a - OFF, 3), t1=round(b - OFF, 3))
        if q.get('vocal_t0') is not None: q['vocal_t0'] = round(q['vocal_t0'] - OFF, 3)
        q['cut'] = p['t0'] < OFF - 0.05 or p['t1'] > OFF + dur + 0.05      # 只截到这一段的一部分
        parts.append(q)
    ST['parts'] = parts; ST['duration'] = dur; ST['offset'] = OFF
    json.dump(ST, open(os.path.join(D, 'structure.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    if os.path.exists(os.path.join(an, 'structure.md')): shutil.copy(os.path.join(an, 'structure.md'), os.path.join(D, 'structure.md'))
subprocess.run([sys.executable, os.path.join(P, 'tools/songmv/make_data.py'), P], check=True)
lines = json.load(open(os.path.join(D, 'lines.json'), encoding='utf-8'))['lines']
lyr = [{'t0': round(l['t'] + OFF, 3), 't1': round(min(l['end'], l.get('sung_end', l['end']) + 0.3, l['t'] + 6.5) + OFF, 3), 'text': l['text']} for l in lines if not l['text'].startswith('♪') and l['t'] < dur]   # 字幕用全曲时间
os.makedirs(os.path.join(P, 'assets'), exist_ok=True)
json.dump(lyr, open(os.path.join(P, 'assets/lyrics.json'), 'w', encoding='utf-8'), ensure_ascii=False)

# ---------- 角色 ----------
H = {}; hp = os.path.join(A.chars, '身高校正.json')
if os.path.exists(hp): H = json.load(open(hp, encoding='utf-8')).get('mv_scale', {})
BAD = json.load(open(os.path.join(SKILL, 'characters/bad_frames.json'), encoding='utf-8'))
for c in cast:
    src, dst = os.path.join(A.chars, c), os.path.join(P, 'assets', c)
    os.makedirs(dst, exist_ok=True)
    if os.path.isdir(os.path.join(src, 'frames')): shutil.copytree(os.path.join(src, 'frames'), os.path.join(dst, 'frames'), dirs_exist_ok=True)
    m = json.load(open(os.path.join(src, 'frames.json'), encoding='utf-8'))
    m['mv_scale'] = m.get('mv_scale', H.get(c, 1.0))
    if c in BAD: m['bad'] = {a: [i - 1 for i in v] for a, v in BAD[c].items()}
    m.setdefault('eye_sole', round(0.61 * m['stand_h'] / m['mv_scale'], 1))   # 眼睛到脚底（素材像素）；有实测值就写进角色目录的 frames.json
    json.dump(m, open(os.path.join(dst, 'frames.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for extra in ('character.md', 'ref.png', 'ref.jpg'):
        if os.path.exists(os.path.join(src, extra)): shutil.copy(os.path.join(src, extra), dst)
subprocess.run([sys.executable, os.path.join(P, 'tools/keypoints.py')] + [os.path.join(P, 'assets', c) for c in cast], check=True)

# ---------- plan.json ----------
pp = os.path.join(P, 'plan.json')
if not os.path.exists(pp):
    plan = {'segment': 'MV', 'maker': A.name, 'lead': A.lead or cast[0], 'start': round(OFF * 24), 'end': round(OFF * 24) + round(dur * 24),
            'tempo': {'beat0': round(beat0, 4), 'spb': round(spb, 4)}, 'cast': cast,
            'scenes': [], 'shots': [], 'cuts': [], 'incamera': [], 'handoffs': [], 'emotes': [], 'events': [],
            'tracks': {c: [] for c in cast}, 'extra_actions': {c: ['idle'] for c in cast},
            'sizes': {}, 'occlude': [], 'treadmill': [],
            'choreo': {'new_moves': max(0, min(4, A.new_moves)), 'new_moves_cast': [c.strip() for c in (A.new_moves_cast or A.lead or cast[0]).split(',') if c.strip()] if A.new_moves > 0 else [], 'why': {}}}
    json.dump(plan, open(pp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
json.dump({'note': '由 plan.json 的动作轨生成（python tools/run.py actions）', 'actions': [], 'subtle': []},
          open(os.path.join(P, 'ACTIONS.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1) if not os.path.exists(os.path.join(P, 'ACTIONS.json')) else None
print(f'项目建好了：{P}\n  {dur:.1f} 秒，{round(dur * 24)} 帧（全曲第 {round(OFF * 24)}–{round(OFF * 24) + round(dur * 24) - 1} 帧），全曲 {n} 拍（{60 / spb:.1f} BPM），{len(lyr)} 句歌词，角色 {", ".join(cast)}')
if not A.seconds and not OFF:
    full = TL['duration']; secs = TL.get('sections', [])
    print(f'这首歌 {full / 60:.0f} 分 {full % 60:02.0f} 秒，{len(secs) + 1} 个段落（分界在 ' + '、'.join(f'{s if isinstance(s, (int, float)) else s.get("time", 0):.1f}' for s in secs) + ' 秒）。'
          '整首做成一个项目还是拆成几段，由你判断，见 SKILL.md「先决定：一个项目还是分段」。')
sung = [l for l in lines if not l['text'].startswith('♪')]
intro = sung[0]['t'] if sung else dur
if intro > 8:
    inner = [s if isinstance(s, (int, float)) else s.get('time', 0) for s in TL.get('sections', [])]
    inner = [s for s in inner if 2 < s < intro - 2]          # TL 这时已经是本段本地时间
    print(f'注意：{"本段" if OFF or A.seconds else "这首歌"}' + (f'前奏 {intro:.1f} 秒（占 {intro / dur:.0%}）' if sung else '没有歌词，全段都是器乐') +
          ('，里面的分界在 ' + '、'.join(f'{s:.1f}' for s in inner) + ' 秒' if inner else '') +
          '。前奏是钩子不是空白：按 SKILL.md「前奏是钩子」规划，♪ 行和歌词行一样排动作，写完跑 python tools/run.py hook。')
if os.path.exists(os.path.join(D, 'structure.json')):
    ST = json.load(open(os.path.join(D, 'structure.json'), encoding='utf-8'))
    print(('本段' if OFF or A.seconds else '这首歌') + '的段落：' + ' → '.join(p['name'] for p in ST['parts']) +
          ('（已人工校对）' if ST.get('checked') else '（自动识别，看 data/structure.md 核对；改 data/analysis/structure.json 后标 checked、用 --structure 重建）'))
NM = max(0, min(4, A.new_moves))
if A.new_moves > 4: print('注意：--new-moves 最多 4（每人 1 张图），已按 4 算')
if NM:
    nmc = [c.strip() for c in (A.new_moves_cast or A.lead or cast[0]).split(',') if c.strip()]
    have = {c: [a for a in json.load(open(os.path.join(P, 'assets', c, 'frames.json'), encoding='utf-8'))['actions'] if a.startswith('dance_')] for c in nmc if os.path.exists(os.path.join(P, 'assets', c, 'frames.json'))}
    need = [c for c in nmc if len(have.get(c, [])) < NM]
    print(f'新舞步预算：{NM} 个动作 × {len(nmc)} 人（{", ".join(nmc)}）。' + (f'已经有了的：{", ".join(f"{c} {len(v)} 个" for c, v in have.items() if v)}。' if any(have.values()) else '') +
          (f'要出图的 {len(need)} 人：每人 1 张 4×4 精灵图（参考角色精灵图生成 {NM} 个舞步的帧动画），预计 {len(need)} 张，'
           f'按平均重出 1 次算约 {2 * len(need)} 张，最多 {4 * len(need)} 张（每张最多重出 3 次）。先把这个数告诉用户，同意了再出；出不来就用现有帧的舞句，不卡住。' if need else '都已经有了，不用出图。'))
print('下一步：cd 进项目，python tools/run.py doctor，再 python tools/run.py still 1 5 看占位画面能不能出图。')

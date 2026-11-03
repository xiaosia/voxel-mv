#!/usr/bin/env python3
"""Turn data/audio.timeline.json + data/lyrics.lrc into src/data.js (TL + LYR) and data/lines.json (for the check scripts).
Usage: python3 tools/make_data.py <project_dir>
Time before the first line (> 4 s) gets a '♪ 前奏' line, gaps longer than 4 s between lines a '♪ 间奏' line, the end a '♪ 尾奏'
line, so every second of the song belongs to a line. An LRC line with a time but no text marks the end of the
line before it (align_lyrics.py writes these); such lines get 'sung_end' and their end_guess uses it. '♪' stretches longer than 12 s are split at section boundaries / bar lines
(about 10 s each, '♪ 前奏 1/3' …). A segment without any lyric gets one '♪' line."""
import json, re, sys, os
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')
root = sys.argv[1] if len(sys.argv) > 1 else '.'
tl = json.load(open(os.path.join(root, 'data/audio.timeline.json'), encoding='utf-8'))
keep = ['duration', 'tempo_bpm', 'seconds_per_beat', 'beat_times', 'bar_times', 'hits', 'sections', 'drops',
        'energy_per_beat', 'energy_per_bar', 'vocal_activity_per_beat']
TL = {k: tl[k] for k in keep if k in tl}
# 段落表（song_structure.py 产出的 data/structure.json，可人工校对）：每行歌词标上所属段落，♪ 长段也在段落分界处切开
_sp = os.path.join(root, 'data/structure.json')
STRUCT = json.load(open(_sp, encoding='utf-8')).get('parts', []) if os.path.exists(_sp) else []
_ZH = {'intro': '前奏', 'verse': '主歌', 'pre-chorus': '导歌', 'chorus': '副歌', 'interlude': '间奏', 'bridge': '桥段', 'outro': '尾奏', 'build': '蓄力', 'drop': '炸点'}
_tot, _n = {}, {}
for p in STRUCT: _tot[p['label']] = _tot.get(p['label'], 0) + 1
for p in STRUCT:   # 人工改了 label 也能对上名字：副歌1、副歌2…（只出现一次的不带数字）
    _n[p['label']] = _n.get(p['label'], 0) + 1
    p['name'] = _ZH.get(p['label'], p['label']) + (str(_n[p['label']]) if _tot[p['label']] > 1 else '')
lrc = open(os.path.join(root, 'data/lyrics.lrc'), encoding='utf-8-sig').read()
off = re.search(r'\[offset:(-?\d+)\]', lrc); off = int(off.group(1)) / 1000 if off else 0
rows = []
ENDS = {}   # 句首 → 句尾（LRC 里写了结束时间的句子）
# 一行一句：普通 LRC「[00:01.99]歌词」和逐字 LRC「[00:01.99]我[00:01.99]们…」都按一行算一句，句首取第一个时间
TS = re.compile(r'[\[<](\d+):(\d+(?:\.\d+)?)[\]>]')
for ln in lrc.splitlines():
    ts = TS.findall(ln)
    if not ts or re.match(r'\[[a-z]+:', ln): continue
    text = TS.sub('', ln).strip()
    if text: rows.append([round(int(ts[0][0]) * 60 + float(ts[0][1]) + off, 3), text])
    elif rows: ENDS[rows[-1][0]] = round(int(ts[0][0]) * 60 + float(ts[0][1]) + off, 3)   # 空时间行 = 上一句结束
rows.sort()
DUR = TL['duration']
out = []
if not rows:      # 本段一句歌词都没有（纯前奏 / 纯间奏的分段，或者整首不做字幕）
    out.append({'t': 0.0, 'text': '♪', 'end_guess': DUR})
elif rows[0][0] > 4:
    out.append({'t': 0.0, 'text': '♪ 前奏', 'end_guess': rows[0][0]})
for i, (t, text) in enumerate(rows):
    if out and t - out[-1]['end_guess'] > 4 and not out[-1]['text'].startswith('♪'):
        out.append({'t': round(out[-1]['end_guess'], 3), 'text': '♪ 间奏', 'end_guess': t})
    nxt = rows[i + 1][0] if i + 1 < len(rows) else DUR
    # a sung line rarely lasts more than ~6 s; the rest of a long gap is an interlude
    out.append({'t': t, 'text': text, 'end_guess': min(nxt, ENDS.get(t, t + 6)) if not text.startswith('♪') else nxt})
    if t in ENDS: out[-1]['sung_end'] = min(nxt, ENDS[t])
if rows and DUR - out[-1]['end_guess'] > 3:
    out.append({'t': round(out[-1]['end_guess'], 3), 'text': '♪ 尾奏', 'end_guess': DUR})
for i, r in enumerate(out): r['end'] = out[i + 1]['t'] if i + 1 < len(out) else DUR

# 没词的长段（前奏、间奏、尾奏）超过 12 秒就切成几行：先切在分析出的段落分界上，还长就每隔约 10 秒切在小节线上。
# 这样排动作、合拍度、逐句检查、逐句帧条都会一小段一小段地覆盖到它，不会整段当成空白。
SPLIT, PIECE = 12.0, 10.0
secs = [s if isinstance(s, (int, float)) else s.get('time', 0) for s in TL.get('sections', [])]
secs = sorted(set(secs + [p['t0'] for p in STRUCT if p['t0'] > 0]))
bars = TL.get('bar_times', [])
def cuts_in(t0, t1):
    cs = [t0] + [c for c in secs if t0 + 4 < c < t1 - 4] + [t1]
    res = [cs[0]]
    for a, b in zip(cs, cs[1:]):
        if b - a > SPLIT:
            n = max(2, round((b - a) / PIECE)); step = (b - a) / n
            for k in range(1, n):
                want = a + k * step
                near = min(bars, key=lambda x: abs(x - want)) if bars else want
                res.append(near if a + 4 < near < b - 4 else want)
        res.append(b)
    return sorted(set(round(x, 3) for x in res))
rows2 = []
for r in out:
    if r['text'].startswith('♪') and r['end'] - r['t'] > SPLIT:
        cs = cuts_in(r['t'], r['end']); n = len(cs) - 1
        for k in range(n): rows2.append({'t': cs[k], 'end': cs[k + 1], 'text': f"{r['text']} {k + 1}/{n}"})
    else: rows2.append(r)
LYR = []
for i, r in enumerate(rows2):
    LYR.append({'t': round(r['t'], 3), 'text': r['text'], 'end': round(r['end'], 3), 'id': 'L%02d' % (i + 1)})
for l in LYR:      # 按句子的中点归到段落
    mid = (l['t'] + l['end']) / 2
    pt = next((p for p in STRUCT if p['t0'] - 1e-6 <= mid < p['t1']), STRUCT[-1] if STRUCT and mid >= STRUCT[-1]['t0'] else None)
    if pt: l['part'], l['part_name'], l['part_id'] = pt['label'], pt['name'], pt['id']
# ♪ 行按段落改名：连着的同一段 ♪ 行叫「♪ 间奏2 1/2」「♪ 炸点」「♪ 副歌1」（分段时截到的上一段尾巴）…
if STRUCT:
    i = 0
    while i < len(LYR):
        if not LYR[i]['text'].startswith('♪') or 'part_id' not in LYR[i]: i += 1; continue
        j = i
        while j + 1 < len(LYR) and LYR[j + 1]['text'].startswith('♪') and LYR[j + 1].get('part_id') == LYR[i]['part_id']: j += 1
        for k in range(i, j + 1): LYR[k]['text'] = '♪ ' + LYR[i]['part_name'] + (f' {k - i + 1}/{j - i + 1}' if j > i else '')
        i = j + 1
SUNG = {r['t']: r['sung_end'] for r in out if 'sung_end' in r}   # 唱完的时间（有就给字幕用，没唱的尾巴不挂字幕）
for l in LYR:
    if l['t'] in SUNG: l['sung_end'] = round(SUNG[l['t']], 3)
with open(os.path.join(root, 'src/data.js'), 'w', encoding='utf-8') as f:
    f.write('// generated from data/audio.timeline.json + data/lyrics.lrc\n')
    f.write('export const TL = ' + json.dumps(TL, ensure_ascii=False) + ';\n')
    f.write('export const LYR = ' + json.dumps(LYR, ensure_ascii=False, indent=0) + ';\n')
with open(os.path.join(root, 'src/data.js'), 'a', encoding='utf-8') as f:   # 没有段落表时是空数组，页面照样可以 import
    f.write('// 段落表：data/structure.json（label: intro verse pre-chorus chorus interlude bridge outro build drop）\n')
    f.write('export const STRUCT = ' + json.dumps(STRUCT, ensure_ascii=False, indent=0) + ';\n')
json.dump({'lines': LYR, 'duration': TL['duration'], 'parts': STRUCT}, open(os.path.join(root, 'data/lines.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
for l in LYR: print(l['id'], l['t'], l['end'], ('[%s] ' % l['part_name']) if l.get('part_name') else '', l['text'], sep=' ')

# 歌词时间轴文件格式

`scripts/fetch_lyrics.py` / `scripts/align_lyrics.py` 的产出。`new_project.py` 自动找歌词时它们在 `data/analysis/`，时间都是**全曲时间**（分段做时 `data/lyrics.lrc` 已换成本段时间，`lyrics_align.json` 没换，要自己减 `--from`）。

## lyrics.lrc

```
[re:align_lyrics 歌词文字 + 对时间；人声 demucs htdemucs；模型 large-v3]
[00:10.96]我爱上给我勇气的 Rainie Love
[00:15.91]
[00:17.36]窗外的雨滴
```

- 一行一句，行首时间 = 句首。
- **只有时间、没有文字的行 = 上一句结束**（和下一句隔开 0.3 秒以上才写）。读的时候把它当上一句的 `end`；没有就用下一句的开始当结束。
- `make_data.py` 按这个规则读：有结束行就用它当句尾，没有才用「下一句开始，最多 6 秒」估。

## lyrics_align.json

```json
{
 "version": 1,
 "audio": "song.wav",
 "duration": 44.4,
 "mode": "text",
 "separation": "demucs htdemucs",
 "model": "large-v3",
 "lines": [
  {"t": 10.96, "end": 15.91, "text": "我爱上给我勇气的 Rainie Love", "conf": 0.61, "flag": "?",
   "heard": "我爱上你我勇气地", "how": "对齐", "src": "人声+提示"}
 ],
 "vocal_pieces": [[0.0, 30.45], [35.8, 37.15]]
}
```

| 字段 | 意思 |
|---|---|
| `mode` | `text`：字来自歌词文字（用户给的或 lrclib），时间对齐到音频；`asr`：没有歌词文字，字和时间都来自识别（错字多） |
| `lines[].t` / `end` | 句首、句尾（秒，全曲时间） |
| `lines[].conf` | 0–1。1 = 每个字都听到了，0.85 = 同音字，< 0.45 = 基本没对上 |
| `lines[].flag` | `ok`；`?` 部分对上，建议听；`✗` 没对上、时间是估的，必须听 |
| `lines[].heard` | 识别听到的字（对照用） |
| `lines[].how` | `对齐`（听到了）；`参考时间`（没听清，用别的版本 LRC 的时间按比例换算）；`估计`（夹在前后两句之间按字数分）；`识别`（mode=asr） |
| `vocal_pieces` | 人声轨上有人唱的片段 `[起, 止]`，前奏、间奏、DJ 纯音乐段不在里面。判断段落时可以用 |

## lyrics_check.md

给人看的检查表：每句的时间、歌词、听到的字、置信度、✗/?；分离质量（没唱的地方人声轨还剩多少能量）；「有人声但歌词里没有的段」（歌词文字可能漏了句子）。另有同名 `.srt` 字幕，`--preview` 时还有 `lyrics_preview.mp4`（波形 + 字幕 + 原声），听一遍就知道准不准。

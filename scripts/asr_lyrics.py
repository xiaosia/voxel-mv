"""把一首歌识别成带时间的 LRC（faster-whisper，离线可用）。

和 fetch_lyrics.py 里的 ASR 区别：
  - 不经过 PyAV 解码（新版 PyAV 去掉了 metadata_errors 参数，faster-whisper 1.2 会直接 TypeError），
    改用 ffmpeg 解成 16k 单声道 wav 再喂 numpy 数组给 transcribe()。
  - 不要求 onnxruntime（vad_filter 关掉），少一层依赖冲突。
  - 模型可以从本地目录读（VOXEL_ASR_MODEL 或 models/faster-whisper-<name>），不联网也能跑。

用法：
  python asr_lyrics.py song.mp3 out.lrc [model] [lang]
    model 可以是模型名（small/medium）或本地目录；不带就用环境变量 VOXEL_ASR_MODEL，
    再没有就用 small（会去下模型，见 fetch_ct2_model.py）。
"""
import os
import re
import subprocess
import sys
import tempfile
import wave

import numpy as np

audio = sys.argv[1]
out = sys.argv[2]
model_ref = sys.argv[3] if len(sys.argv) > 3 else os.environ.get('VOXEL_ASR_MODEL') or 'small'
lang = sys.argv[4] if len(sys.argv) > 4 else 'zh'

from faster_whisper import WhisperModel  # noqa: E402

wav = os.path.join(tempfile.gettempdir(), 'voxel_asr_in.wav')
subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', audio,
                '-ac', '1', '-ar', '16000', '-f', 'wav', wav], check=True)
with wave.open(wav, 'rb') as w:
    pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
samples = pcm.astype(np.float32) / 32768.0
print(f'解码 {len(samples) / 16000:.1f}s', flush=True)

device = os.environ.get('VOXEL_ASR_DEVICE', 'cpu')
compute = 'float16' if device == 'cuda' else 'int8'
print(f'加载模型 {model_ref}（{device}/{compute}）', flush=True)
model = WhisperModel(model_ref, device=device, compute_type=compute)

segs, info = model.transcribe(
    samples,
    language=lang,
    vad_filter=False,
    beam_size=5,
    condition_on_previous_text=False,
    initial_prompt='以下是普通话歌曲的歌词。' if lang == 'zh' else None,
)
print(f'语言={info.language} 时长={info.duration:.1f}s', flush=True)


def ts(t):
    m, s = divmod(max(0.0, t), 60)
    return f'{int(m):02d}:{s:05.2f}'


rows = []
for seg in segs:
    text = (seg.text or '').strip()
    if not text:
        continue
    parts = [p for p in re.split(r'(?<=[，。！？、,.!?])', text) if p.strip()]
    if len(parts) <= 1:
        rows.append((seg.start, text))
        continue
    total = sum(len(p) for p in parts)
    acc = 0
    for p in parts:
        rows.append((seg.start + (seg.end - seg.start) * (acc / total), p.strip()))
        acc += len(p)

with open(out, 'w', encoding='utf-8') as f:
    for t0, text in rows:
        f.write(f'[{ts(t0)}]{text}\n')

print(f'{len(rows)} 句 -> {out}')
print('识别出来的句子一定有错字（歌唱 + 伴奏），拿其中一两句去搜歌名，再用真歌词换掉文字、保留时间轴。')
for t0, text in rows:
    print(f'  [{ts(t0)}] {text}')

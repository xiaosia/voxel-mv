"""下 CTranslate2 版的 faster-whisper 模型（不经过 huggingface_hub）。

为什么单独写一个：huggingface_hub 2.x 在部分网络下拉一半会断、还多两个依赖（httpx2 / hf-xet），
而 faster-whisper 只要能传一个本地目录给 WhisperModel 就够。这里直接下 5 个文件，
用 curl 续传（没有 curl 就退回 urllib），镜像 hf-mirror.com 优先。

用法：
  python fetch_ct2_model.py small                 -> models/faster-whisper-small
  python fetch_ct2_model.py medium D:\\models\\fw-medium
可用的名字：tiny / base / small / medium / large-v3
"""
import os
import shutil
import subprocess
import sys
import urllib.request

FILES = ['config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt', 'preprocessor_config.json']
HOSTS = ['https://hf-mirror.com', 'https://huggingface.co']
OPTIONAL = {'preprocessor_config.json'}


def have_curl():
    return shutil.which('curl') is not None


def curl_get(url, dest):
    part = dest + '.part'
    cmd = ['curl', '-L', '--fail', '--retry', '8', '--retry-delay', '3', '--retry-all-errors',
           '-C', '-', '--max-time', '1800', '-o', part, url]
    print('GET(curl)', url, flush=True)
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise RuntimeError(f'curl exit {r.returncode}')
    os.replace(part, dest)


def urllib_get(url, dest):
    part = dest + '.part'
    start = os.path.getsize(part) if os.path.exists(part) else 0
    headers = {'User-Agent': 'curl/8'}
    if start:
        headers['Range'] = f'bytes={start}-'
    print(f'GET(urllib) {url} from {start // 1024} KB', flush=True)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=300) as r, open(part, 'ab') as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    os.replace(part, dest)


def download(repo, out):
    os.makedirs(out, exist_ok=True)
    for fn in FILES:
        dest = os.path.join(out, fn)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print(f'skip {fn} ({os.path.getsize(dest) // 1024} KB)')
            continue
        ok = False
        for host in HOSTS:
            url = f'{host}/{repo}/resolve/main/{fn}'
            try:
                (curl_get if have_curl() else urllib_get)(url, dest)
                print(f'  done {fn} {os.path.getsize(dest) // 1024} KB')
                ok = True
                break
            except Exception as e:
                print(f'  fail {host}: {e}')
        if not ok:
            if fn in OPTIONAL:
                print(f'  {fn} 拿不到（可选，跳过）')
                continue
            sys.exit(f'拿不到 {fn}；换个网络或手动下载 {repo} 的这几个文件到 {out}')


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else 'small'
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join('models', f'faster-whisper-{name}')
    download(f'Systran/faster-whisper-{name}', out)
    print('模型就绪：' + os.path.abspath(out))
    print('用法：VOXEL_ASR_MODEL=' + os.path.abspath(out) + '  python fetch_lyrics.py song.mp3')


if __name__ == '__main__':
    main()

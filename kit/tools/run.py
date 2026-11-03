#!/usr/bin/env python3
"""voxel-mv 一条命令跑完：自动修（--fix）→ 预检（舞步关、动作关、转场登记、体素关、运镜关、场景关、钩子关，不出图）→ 按场景分块渲染 → 不定格 → 各关量成片 →（分段时）交接检查 → 打包交付。
Windows、macOS、Linux 都一样用。
在项目根目录（有 index.html 和 plan.json 的那层）运行：
  python tools/run.py doctor             检查环境（node、ffmpeg、Chrome、Python 包、浏览器有没有用上显卡），第一次会自动装渲染用的 node 依赖
  python tools/run.py upgrade-engine     把 skill 的 kit/engine/ 升级到项目 engine/（旧的整份备份到 engine_bak/；--skill 指 skill 目录，默认用 ENGINE_VERSION 里记的）
  python tools/run.py preview            边做边看：浏览器里带音乐实时播放当前项目（不渲染不导出），改了 plan.json / shots.js 自动刷新，写镜头时一直开着
  python tools/run.py still 0 3.5 10     截图（项目本地秒数）→ out/chk/t_<秒>.jpg，写镜头时随时看
  python tools/run.py frame 740 903      截图（全曲帧号）→ out/chk/f_<帧>.jpg
  python tools/run.py style 3.2 11 20    风格对照：体素参考图在上，这几秒的画面在下 → out/style_compare.jpg
  python tools/run.py actions            按 plan.json 的动作轨重新生成 ACTIONS.json（动作关 G4 对照用）
  python tools/run.py choreo             编舞草稿（按段落表排舞句 → out/choreo.md；加 --apply 写进 plan.json，--check 舞步关）
  python tools/run.py camplan            运镜草稿（按段落能量配运镜 → out/camplan.md；加 --apply 写进 plan.json 的 camera，--force 覆盖已有的）
  python tools/run.py camera             运镜关（读探针 cam 档：运镜不单一、段落呼吸、炸点冲击、定机位）→ out/camera_check.md
  python tools/run.py act                动作关（约 1 分钟）→ out/act_check.md、out/act_check.png
  python tools/run.py check              一条命令看能不能过：预检各关 → out/report.md 汇总（必过拦、自动修修不好拦、警告只报告）
  python tools/run.py check --fix        先自动修（plan.json 的数值改到能过，旧版备份 plan.bak.json）再查
  python tools/run.py check --shot S03   只复查一个镜头（逐帧重 dump 这个镜头，要先跑过一次全片 check）
  python tools/run.py check --layout     探针带上碰撞体，出每个镜头的俯视布局图 out/layout/<镜头 id>.png（灰=碰撞体、绿=被推开、红=STUCK）
  python tools/run.py selftest           自检：在 kit/tests/bad_scene（故意做错的测试项目）上把自动修、必过拦、警告不拦整个验一遍
  python tools/run.py trans              转场表检查 → out/trans_check.md
  python tools/run.py voxel              体素关（等高、贴地、不打滑、不发糊、坏帧、移轴、表情卡拍）→ out/voxel_check.md
  python tools/run.py scenes             场景关（场景表完整、每个场景 10–20 秒左右、相邻场景看得出换了、换场景有转场）→ out/scene_check.md
  python tools/run.py hook               钩子关（开场 5 秒、没词长段每 4 小节、人声进来那一拍、副歌 / 间奏 / 桥段开头都有事件）→ out/hook_check.md
  python tools/run.py grade              调色关（每段有调色关键帧；量成片：段落之间有明暗起伏、副歌放开、桥段有反差、暗段也看得清）→ out/grade_check.md
  python tools/run.py video              全流程：自动修 → 预检 → 渲染 → 全部检查 + 接触表、逐句帧条 → 打包到 out/交付/（必过或自动修没修好会停下并说明原因）
  python tools/run.py video --redo C,D   只重渲这几个场景（plan.json scenes 的 id，或者秒数范围 12-30），其余场景用上次渲好的，再跑全部检查
  python tools/run.py draft              草稿：每秒 12 帧、不跑检查，快速出 out/draft.mp4 看整体节奏（交付必须用 video）
并行数默认按 CPU 核数定（2–6 个浏览器），环境变量 VOXEL_WORKERS=4 可以改。每次 video / draft 跑完写 out/timing.md（每一步花了多久）。
"""
import glob, json, os, platform, shutil, subprocess, sys, time, zipfile
os.environ.setdefault('PYTHONUTF8', '1'); os.environ.setdefault('PYTHONIOENCODING', 'utf-8')   # 子进程（各个检查脚本）在中文 Windows 上也按 UTF-8 读写
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROOT = os.path.abspath(os.getcwd())
if not os.path.exists(os.path.join(ROOT, 'index.html')) or not os.path.exists(os.path.join(ROOT, 'plan.json')):
    sys.exit('请在开工包根目录（有 index.html 和 plan.json 的那层）运行：python tools/run.py ...')
import engine_dist                          # 引擎分发（和 new_project.py 共用；engine/ 版本、哈希、备份、升级）
TOOLS = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(TOOLS, 'render')          # 渲染器（lemo-opuscar 的 core/render）
SM = os.path.join(TOOLS, 'songmv')            # song-mv 的检查脚本
PY = sys.executable
PLAN = json.load(open(os.path.join(ROOT, 'plan.json'), encoding='utf-8'))
SEG, MAKER = PLAN['segment'], PLAN['maker']
N = PLAN['end'] - PLAN['start']
RELAY = bool(PLAN.get('handoffs'))              # 多段接力：有交接卡才跑 handoff_check
SAFE = not (os.path.exists(os.path.join(ROOT, 'MODE')) and open(os.path.join(ROOT, 'MODE'), encoding='utf-8').read().strip() == 'free')
SKILL = os.path.dirname(os.path.dirname(TOOLS)) if os.path.basename(os.path.dirname(TOOLS)) == 'kit' else None
NAME = f'{SEG}_{MAKER}'
OUT = os.path.join(ROOT, 'out')
ENGINE = os.path.join(ROOT, 'engine')
WIN = platform.system() == 'Windows'
WORKERS = int(os.environ.get('VOXEL_WORKERS') or max(2, min(6, (os.cpu_count() or 4) // 2)))
CHUNKS = os.path.join(OUT, 'chunks')          # 按场景分块的成片，video --redo 只重渲其中几块
TIMES = []                                    # (步骤, 秒) → out/timing.md

def timed(name, fn, *a, **k):
    t = time.time(); r = fn(*a, **k); TIMES.append((name, time.time() - t)); return r

def write_timing(title):
    tot = sum(s for _, s in TIMES)
    L = [f'# {title} 耗时', '', f'{N / 24:.1f} 秒的片子，{N} 帧，{WORKERS} 个浏览器并行，总共 {tot / 60:.1f} 分钟', '', '| 步骤 | 秒 | 占比 |', '|---|---|---|']
    L += [f'| {n} | {s:.0f} | {s / max(tot, 1e-9):.0%} |' for n, s in TIMES]
    os.makedirs(OUT, exist_ok=True); open(os.path.join(OUT, 'timing.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('\n'.join(L[2:3]) + ' → out/timing.md')

def sh(cmd, cwd=None, check=True, env=None, capture=False):
    print('»', ' '.join(str(c) for c in cmd), flush=True)
    r = subprocess.run(cmd, cwd=cwd, env=env, shell=False, capture_output=capture, text=capture, encoding='utf-8' if capture else None, errors='replace' if capture else None)
    if check and r.returncode != 0: sys.exit(f'命令失败（退出码 {r.returncode}）：{cmd[0]}')
    return r

def which(x):
    p = shutil.which(x)
    if not p and WIN: p = shutil.which(x + '.exe') or shutil.which(x + '.cmd')
    return p

def find_chrome():
    if os.environ.get('PLAYWRIGHT_CHROME') and os.path.exists(os.environ['PLAYWRIGHT_CHROME']): return os.environ['PLAYWRIGHT_CHROME']
    c = []
    if WIN:
        for base in (os.environ.get('PROGRAMFILES', r'C:\Program Files'), os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)'), os.environ.get('LOCALAPPDATA', '')):
            c += [os.path.join(base, r'Google\Chrome\Application\chrome.exe'), os.path.join(base, r'Microsoft\Edge\Application\msedge.exe')]
        c += glob.glob(os.path.join(os.environ.get('LOCALAPPDATA', ''), r'ms-playwright\chromium_headless_shell-*\chrome-*\chrome-headless-shell.exe'))
    elif platform.system() == 'Darwin':
        c += ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge']
        c += glob.glob(os.path.expanduser('~/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-*/chrome-headless-shell'))
    else:
        c += glob.glob('/opt/pw-browsers/chromium_headless_shell-*/chrome-*/chrome-headless-shell')
        c += glob.glob(os.path.expanduser('~/.cache/ms-playwright/chromium_headless_shell-*/chrome-*/chrome-headless-shell'))
        c += glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome') + [which('google-chrome') or '', which('chromium') or '']
    for p in c:
        if p and os.path.exists(p): return p
    return None

def env():
    e = dict(os.environ)
    import importlib.util as _iu   # 歌词对齐（scripts/align_lyrics.py）要用的可选库
    _have = {m: _iu.find_spec(m) is not None for m in ('faster_whisper', 'pypinyin', 'demucs', 'audio_separator')}
    if _have['faster_whisper'] and _have['pypinyin']:
        sep = 'demucs' if _have['demucs'] else ('audio-separator' if _have['audio_separator'] else '')
        print('  [OK]  （可选）歌词对齐：faster-whisper + pypinyin' + (f' + {sep} 分离人声' if sep else f'；没装分离人声，会准一些：{PY} -m pip install demucs'))
    else:
        miss = ' '.join(n for n, m in (('faster-whisper', 'faster_whisper'), ('pypinyin', 'pypinyin'), ('demucs', 'demucs')) if not _have[m])
        print(f'  [--]  （可选）歌词对齐没装全：没有对好时间的 LRC 时，字幕时间会不准或者没字幕。想要：{PY} -m pip install {miss}')
    ch = find_chrome()
    if ch: e['PLAYWRIGHT_CHROME'] = ch
    return e

def ensure_render():
    if not os.path.isdir(os.path.join(LIB, 'node_modules', 'playwright-core')):
        npm = which('npm') or sys.exit('没找到 npm：先装 Node.js 20 以上（https://nodejs.org）')
        sh([npm, 'install', '--no-audit', '--no-fund'], cwd=LIB)

def doctor():
    ok = True
    def line(name, good, msg):
        nonlocal ok; ok &= bool(good); print(('  [OK]  ' if good else '  [缺]  ') + name + '：' + msg)
    nd = which('node'); v = subprocess.run([nd, '-v'], capture_output=True, text=True).stdout.strip() if nd else ''
    line('Node.js ≥ 20', nd and int(v.lstrip('v').split('.')[0]) >= 20, v or '没装，去 https://nodejs.org 装 LTS 版')
    line('ffmpeg / ffprobe', which('ffmpeg') and which('ffprobe'), '在 PATH 里' if which('ffmpeg') else '没装：Windows 用 winget install Gyan.FFmpeg，macOS 用 brew install ffmpeg')
    try:
        import numpy, PIL; line('Python 包 numpy、pillow', True, f'numpy {numpy.__version__}，pillow {PIL.__version__}')
    except ImportError:
        line('Python 包 numpy、pillow', False, f'运行：{PY} -m pip install numpy pillow')
    ch = find_chrome()
    line('Chrome / Edge', ch, ch or '没找到：装 Chrome，或者设置环境变量 PLAYWRIGHT_CHROME 指向浏览器程序')
    if nd and ok:
        ensure_render(); line('渲染器依赖', os.path.isdir(os.path.join(LIB, 'node_modules', 'playwright-core')), 'tools/render/node_modules')
        r = subprocess.run([nd, os.path.join(TOOLS, 'gpu_check.mjs'), LIB], env=env(), capture_output=True, text=True)
        gpu = (r.stdout.strip().splitlines() or ['?'])[-1]
        soft = r.returncode != 0 or any(k in gpu.lower() for k in ('swiftshader', 'llvmpipe', 'software', 'basic render'))
        print(('  [OK]  ' if not soft else '  [慢]  ') + '显卡渲染：' + gpu)
        if soft:
            print('        浏览器在用软件渲染（CPU 画 3D），渲染会慢 3–6 倍。可以试：更新显卡驱动；Windows 上设环境变量 LEMO_ANGLE=d3d11'
                  '（PowerShell：$env:LEMO_ANGLE="d3d11"）再跑一次 doctor；笔记本把 Chrome 设成用独立显卡；macOS 默认已经用 Metal。')
    print('\n环境齐了，可以开工。' if ok else '\n先把上面标「缺」的装好，再运行一次 doctor。')
    return ok

def node(script, *args):
    ensure_render()
    return sh([which('node'), script, *args], env=env(), check=False)

def still(times, prefix='t_'):
    r = node(os.path.join(LIB, 'core/render/still.mjs'), ROOT, *times, '--q', 'export=1', '--prefix', prefix, '--out', os.path.join(OUT, 'chk'))
    if r.returncode: sys.exit('截图失败：看上面的报错（页面里的 JS 错误也会显示在这里）')

PROBE_KEY = os.path.join(OUT, 'probe_key.json')   # 探针缓存：页面用到的文件都没变就不重跑

def probe_inputs():
    """探针结果只由这些文件决定：plan、镜头代码、页面、引擎、素材的 json、节奏数据。图片帧换了 frames.json 也会变。"""
    fs = ['plan.json', 'shots.js', 'index.html', 'assets/lyrics.json']
    for d in ('src', 'engine'):
        for base, _, files in os.walk(os.path.join(ROOT, d)):
            fs += [os.path.relpath(os.path.join(base, f), ROOT) for f in files if f.endswith(('.js', '.mjs', '.json'))]
    fs += [os.path.relpath(f, ROOT) for f in glob.glob(os.path.join(ROOT, 'assets', '*', '*.json')) + glob.glob(os.path.join(ROOT, 'data', '*.json'))]
    return sorted(set(f.replace(os.sep, '/') for f in fs if os.path.isfile(os.path.join(ROOT, f))))

def probe_key(layout):
    import hashlib
    h = hashlib.sha256(b'probe_all v1' + (b' layout' if layout else b''))
    for f in probe_inputs():
        h.update(f.encode('utf-8') + b'\0'); h.update(open(os.path.join(ROOT, f), 'rb').read()); h.update(b'\0')
    return h.hexdigest()

def probe_fresh(layout=False):
    """缓存还能用：key 对得上、三个输出都在。--layout 跑出来的数据是超集，不带 layout 的也能用。"""
    try: k = json.load(open(PROBE_KEY, encoding='utf-8'))
    except Exception: return False
    outs = all(os.path.exists(os.path.join(OUT, f)) for f in ('probe.json', 'voxel.json', 'page_meta.json'))
    return outs and (k.get('key') == probe_key(layout) or (not layout and k.get('layout') and k.get('key') == probe_key(True)))

def probe(layout=False):
    """预检探针：一遍、多个浏览器并行，同时写 out/probe.json、voxel.json、page_meta.json。
    页面用到的文件（plan.json、shots.js、src/、engine/、素材 json）都没变就直接用上次的（VOXEL_NOCACHE=1 强制重跑）。返回 0 = 有数据。"""
    if not os.environ.get('VOXEL_NOCACHE') and probe_fresh(layout):
        print('探针：页面用到的文件都没变，用上次的结果（out/probe.json、voxel.json）'); return 0
    try: os.remove(PROBE_KEY)
    except OSError: pass
    r = node(os.path.join(TOOLS, 'probe_all.mjs'), LIB, ROOT, '--workers', str(WORKERS), *(['--layout'] if layout else []))
    if r.returncode: return r.returncode
    json.dump({'key': probe_key(layout), 'layout': layout, 'time': time.strftime('%Y-%m-%d %H:%M:%S')}, open(PROBE_KEY, 'w', encoding='utf-8'))
    return 0

def act(dump=True):
    """动作关。返回退出码：0 = 必过档干净；3 = 必过没过；1 = 探针就没采到（查不了，也拦）。"""
    if dump and probe(): return 1
    return sh([PY, os.path.join(SM, 'act_check.py'), '.', '--mode', 'safe' if SAFE else 'free'], cwd=ROOT, check=False).returncode

def choreo(*a):
    return sh([PY, os.path.join(TOOLS, 'choreo.py'), *a], cwd=ROOT, check=False).returncode

def trans(video=None, dump=True):
    if dump and not probe_fresh(): node(os.path.join(SM, 'probe_dump.mjs'), LIB, ROOT, '24', '--meta-only')   # 探针缓存是新的就不用再开浏览器
    cmd = [PY, os.path.join(SM, 'trans_check.py'), '.'] + ([video] if video else []) + ['--mode', 'safe' if SAFE else 'free']
    return sh(cmd, cwd=ROOT, check=False).returncode

def latest_video():   # 检查用的成片：优先用 480×270 的小样（解码快），没有就用 mv.mp4
    for f in ('proxy.mp4', 'mv.mp4'):
        if os.path.exists(os.path.join(OUT, f)): return os.path.join(OUT, f)
    return None

def voxel(video='latest', dump=True, layout=False):
    """体素关。dump 失败返回 1（查不了也拦）；其余透传 voxel_check.py 的退出码。"""
    if dump and probe(layout): return 1
    if video == 'latest': video = latest_video()
    return sh([PY, os.path.join(TOOLS, 'voxel_check.py')] + ([video] if video else []), cwd=ROOT, check=False).returncode

def scenes(video='latest'):
    if video == 'latest': video = latest_video()
    return sh([PY, os.path.join(TOOLS, 'scene_check.py')] + ([video] if video else []), cwd=ROOT, check=False).returncode

def hook():
    return sh([PY, os.path.join(TOOLS, 'hook_check.py'), ROOT], cwd=ROOT, check=False).returncode

def camera():
    """运镜关：读 out/voxel.json 探针里的 cam 档（voxel 关先跑才有数据）。"""
    return sh([PY, os.path.join(TOOLS, 'camera_check.py'), ROOT], cwd=ROOT, check=False).returncode

def camplan(*a):
    return sh([PY, os.path.join(TOOLS, 'camplan.py'), *a], cwd=ROOT, check=False).returncode

def grade(video='latest'):
    if video == 'latest': video = latest_video()
    return sh([PY, os.path.join(TOOLS, 'grade_check.py')] + ([video] if video else []), cwd=ROOT, check=False).returncode

def style(times):
    still(times, prefix='s_')
    # still.mjs 按传进去的字符串原样命名（传 2 出 s_2.jpg、传 3.5 出 s_3.5.jpg）：先认原字符串，再认 :g / 4 位小数的老写法。
    # 不用前缀通配——s_2*.jpg 会把 s_2.5.jpg、s_20.jpg 也匹配进来。找不到就跳过并说明
    paths = []
    for t in times:
        cands = [os.path.join(OUT, 'chk', f's_{n}.jpg') for n in (t, f'{float(t):g}', f'{float(t):.4f}')]
        hit = next((p for p in cands if os.path.exists(p)), None)
        if not hit:
            print(f'[style] 缺少 s_{t}.jpg，跳过'); continue
        paths.append(hit)
    if paths:
        sh([PY, os.path.join(TOOLS, 'style_compare.py')] + paths, cwd=ROOT, check=False)

def chunk_list():
    """渲染分块：有完整的场景表就一个场景一块，否则每 10 秒一块。返回 [(名字, 本片起帧, 本片止帧)]。"""
    S, sc = PLAN['start'], sorted(PLAN.get('scenes') or [], key=lambda s: s['f0'])
    if sc and sc[0]['f0'] == S and sc[-1]['f1'] == PLAN['end'] and all(a['f1'] == b['f0'] for a, b in zip(sc, sc[1:])):
        return [(s['id'], s['f0'] - S, s['f1'] - S) for s in sc]
    return [(f'{a // 24}s', a, min(N, a + 240)) for a in range(0, N, 240)]

def pick(chunks, redo):
    """--redo 的写法：场景 id（逗号分开）或秒数范围 12-30（本片时间）。"""
    hit = set()
    for tok in [x.strip() for x in redo.split(',') if x.strip()]:
        ids = [c for c in chunks if c[0] == tok]
        if ids: hit.update(ids); continue
        try: a, b = (float(v) * 24 for v in tok.split('-'))
        except ValueError: sys.exit(f'--redo 里的 "{tok}" 既不是场景 id（{", ".join(c[0] for c in chunks)}），也不是秒数范围（例如 12-30）')
        hit.update(c for c in chunks if c[1] < b and c[2] > a)
    return hit

def render_chunks(chunks, todo, fps, cdir):
    """渲 todo 里的块到 cdir/<起>_<止>.mp4（按 fps 换算的帧号），再无损拼成一个文件返回。"""
    os.makedirs(cdir, exist_ok=True)
    k = fps / 24; span = lambda c: (round(c[1] * k), round(c[2] * k))
    if todo:
        r = node(os.path.join(LIB, 'core/render/video.mjs'), ROOT, '--fps', str(fps), '--workers', str(WORKERS), '--q', 'export=1',
                 '--out', os.path.join(cdir, 'render.mp4'), '--chunks', ','.join('%d:%d' % span(c) for c in todo), '--chunk-dir', cdir)
        if r.returncode: sys.exit('渲染失败：看上面的报错')
    files = [os.path.join(cdir, '%d_%d.mp4' % span(c)) for c in chunks]
    lst = os.path.join(cdir, 'list.txt')
    open(lst, 'w', encoding='utf-8').write(''.join("file '%s'\n" % os.path.basename(f) for f in files))
    joined = os.path.join(cdir, 'joined.mp4')
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', 'list.txt', '-c', 'copy', 'joined.mp4'], cwd=cdir)
    return joined

def precheck(layout=False):
    """不出图就能查的关先查：引擎校验、舞步关、动作关、转场登记、体素关（不量画面的部分）、运镜关、场景关（不量画面的部分）、钩子关。
    返回 [(名字, 退出码)]：0 = 这关必过档干净；3 = 必过没过；其他 = 脚本本身出错了（也拦，查不了不能渲）。"""
    engine_verify()
    pr = timed('预检 · 探针（并行，没改就用缓存）', probe, layout)   # 动作关、体素关、运镜关、转场关共用这一份
    if pr: print('探针没跑成（看上面的报错）：动作关、体素关、运镜关查不了，按没过算')
    res = [('舞步关', timed('预检 · 舞步关', choreo, '--check')), ('动作关', 1 if pr else timed('预检 · 动作关', act, False)), ('转场关', timed('预检 · 转场登记', trans, None, bool(pr))),
           ('体素关', 1 if pr else timed('预检 · 体素关', voxel, None, False)), ('运镜关', timed('预检 · 运镜关', camera)), ('场景关', timed('预检 · 场景关', scenes, None)),
           ('钩子关', timed('预检 · 钩子关', hook)), ('调色关', timed('预检 · 调色关', grade, None))]
    print('\n预检：' + '  '.join(f'{"PASS" if rc == 0 else ("FAIL" if rc == 3 else "错误")} {n}' for n, rc in res))
    return res

def engine_verify():
    """项目 engine/ 和 ENGINE_VERSION 记录的哈希对一遍：被手改、缺文件就警告（不拦）。返回警告数。"""
    meta = engine_dist.read_version(ENGINE)
    if not meta:
        print('  [警]  engine/ 没有 ENGINE_VERSION（老项目）：跑 python tools/run.py upgrade-engine 接入版本管理，以后升级引擎先备份再覆盖')
        return 1
    d = engine_dist.diff(ENGINE, meta)
    for f in d['modified']: print(f'  [警]  引擎被改过：engine/{f}（和 ENGINE_VERSION 记录的不一致）')
    for f in d['missing']: print(f'  [警]  引擎缺文件：engine/{f}')
    if d['modified'] or d['missing']:
        print('        engine/ 在项目里不要手改：要改引擎就改 skill 的 kit/engine/，再到项目里跑 python tools/run.py upgrade-engine（会先把现在的引擎备份到 engine_bak/）')
    return len(d['modified']) + len(d['missing'])

def upgrade_engine(args):
    skill = args[args.index('--skill') + 1] if '--skill' in args and args.index('--skill') + 1 < len(args) else None
    meta = engine_dist.read_version(ENGINE)
    skill = skill or (meta or {}).get('skill') or os.environ.get('VOXEL_MV_SKILL')
    if not skill or not os.path.isdir(os.path.join(skill, 'kit', 'engine')):
        sys.exit('找不到 skill 的 kit/engine：python tools/run.py upgrade-engine --skill <skill 目录>（建过项目的机器上 ENGINE_VERSION 里记了路径，不用给）')
    r = engine_dist.upgrade(ENGINE, skill, ROOT)
    if r['local']:
        for f in r['local']['modified']: print('升级会覆盖你改过的 engine/' + f + '（旧版在 engine_bak/）')
        for f in r['local']['extra']: print('engine/' + f + ' 上次没登记（新加的或旧清单没记）：skill 里有同名就覆盖，没有就保留')
    if r['backup']: print('旧引擎整份备份到 ' + os.path.relpath(r['backup'], ROOT))
    print('引擎现在是 ' + r['meta']['version'] + ('，没有变化' if not r['changed'] else '，换掉了：' + '、'.join(r['changed'])))

def report():
    """汇总 out/*_check.json → out/report.md。退出码：0 干净 / 3 必过没过 / 4 自动修没修好。"""
    return sh([PY, os.path.join(TOOLS, 'report.py')], cwd=ROOT, check=False).returncode

def selftest():
    """在 kit/tests/bad_scene（故意做错的测试项目）上把检查链验一遍：自动修、必过拦、警告不拦、
    错误的 allow 照样 FAIL、修完在拍上、plan.bak.json 在、幂等。工作副本放在 <项目>/out/selftest/。"""
    meta = engine_dist.read_version(ENGINE)
    cands = [os.path.join(os.path.dirname(TOOLS), 'tests', 'bad_scene')]
    if SKILL: cands.append(os.path.join(SKILL, 'kit', 'tests', 'bad_scene'))
    if meta and meta.get('skill'): cands.append(os.path.join(meta['skill'], 'kit', 'tests', 'bad_scene'))
    src = next((c for c in cands if os.path.isdir(c)), None)
    if not src: sys.exit('找不到 kit/tests/bad_scene（自检项目）：在 skill 检出目录里跑，或确认 ENGINE_VERSION 记的 skill 路径还在')
    work = os.path.join(OUT, 'selftest', 'bad_scene')
    shutil.rmtree(work, ignore_errors=True); os.makedirs(work)
    shutil.copytree(src, work, dirs_exist_ok=True)
    out_ = lambda *p: os.path.join(work, *p)
    print(f'自检项目：{src}\n工作副本：{work}\n')
    def py(script, *a):
        r = sh([PY, os.path.join(TOOLS, script), *a], cwd=work, check=False, capture=True)
        return r.returncode, r.stdout
    R = []
    def ok(name, cond, why=''):
        R.append(bool(cond)); print(f'  {"PASS" if cond else "FAIL"}  {name}' + ('' if cond else f'——{why}'))

    rc1, _ = py('autofix.py')
    fx = json.load(open(out_('out', 'fixes.json'), encoding='utf-8'))['fixes']
    rules = {f['rule'] for f in fx}
    ok('自动修把数值类的错都修了（V7/D1/T3/T4/C1/C4/allow）', rc1 == 0 and {'V7', 'D1', 'T3', 'T4', 'C1', 'C4', 'allow'} <= rules, f'退出码 {rc1}，修到 {sorted(rules)}')
    ok('plan.bak.json 备份在', os.path.exists(out_('plan.bak.json')))

    rcv, _ = py('voxel_check.py', '--data', 'out/voxel.json')
    vj = json.load(open(out_('out', 'voxel_check.json'), encoding='utf-8'))['rules']
    st = next((r for r in vj if r['rule'] == 'STUCK'), {})
    vmd = open(out_('out', 'voxel_check.md'), encoding='utf-8').read()
    ok('必过档 FAIL 拦（退出码 3）', rcv == 3, f'退出码 {rcv}')
    ok('STUCK 在 FAIL 里', st.get('ok') is False, str(st.get('detail', ''))[:120])
    ok('写错时间的 allow 照样 FAIL（提示没盖住）', '没盖住' in str(st.get('detail', '')), str(st.get('detail', ''))[:160])
    ok('occlude 迁成 allow 的那条豁免生效（不拦）', '在 allow 豁免里' in vmd)

    rcs, _ = py('scene_check.py')
    sj = json.load(open(out_('out', 'scene_check.json'), encoding='utf-8'))['rules']
    c2 = next((r for r in sj if r['rule'] == 'C2'), {})
    ok('警告档不拦（场景太长只报，退出码 0）', rcs == 0 and c2.get('ok') is False, f'退出码 {rcs}，C2={c2.get("ok")}')

    plan2 = json.load(open(out_('plan.json'), encoding='utf-8'))
    beats = {round(t * 24) for t in json.load(open(out_('data', 'audio.timeline.json'), encoding='utf-8'))['beat_times']}
    e = (plan2.get('emotes') or [{}])[0]
    d = ((plan2.get('tracks') or {}).get('a') or [[None] * 4])[0]
    ok('表情修到拍上', e.get('f0') in beats, f'emote f0={e.get("f0")}')
    ok('舞句修到拍上', d[2] in beats, f'dance 起点={d[2]}')
    rc2 = py('autofix.py')[0]
    n2 = json.load(open(out_('out', 'fixes.json'), encoding='utf-8'))['n']
    ok('再跑一遍没有新修（幂等）', rc2 == 0 and n2 == 0, f'退出码 {rc2}，{n2} 处')

    rcr, rout = py('report.py')
    ok('report 汇总拦（退出码 3）', rcr == 3, f'退出码 {rcr}；{rout.strip()[-160:]}')

    bad = sum(1 for g in R if not g)
    print('\n' + (f'selftest 全过（{len(R)} 项）。工作副本留着：{work}' if not bad else f'selftest {bad}/{len(R)} 项没过：工作副本 {work}'))
    sys.exit(1 if bad else 0)

def autofix():
    """自动修：只改 plan.json 的数值（旧版备份 plan.bak.json），改了什么看 out/fixes.json。"""
    return sh([PY, os.path.join(TOOLS, 'autofix.py')], cwd=ROOT, check=False).returncode

def shot_check(shot):
    """单镜头复查：从上次全片探针找这个镜头的帧范围，逐帧重新 dump，只查它。"""
    vp = os.path.join(OUT, 'voxel.json')
    if not os.path.exists(vp): sys.exit('--shot 要先有全片探针：先跑一次 python tools/run.py check')
    frs = [fr['f'] for fr in json.load(open(vp, encoding='utf-8')).get('frames', []) if fr.get('shot') == shot]
    if not frs:
        have = sorted({fr.get('shot') for fr in json.load(open(vp, encoding='utf-8')).get('frames', [])})
        sys.exit(f'--shot {shot}：探针里没有这个镜头。可用的镜头 id：{"、".join(map(str, have))}（镜头在 plan.json 的 shots 里，一个场景可能拆成几个镜头）')
    node(os.path.join(TOOLS, 'voxel_dump.mjs'), LIB, ROOT, '1', f'{min(frs)}:{max(frs) + 1}', '--out=voxel_shot.json')
    return sh([PY, os.path.join(TOOLS, 'voxel_check.py'), '--shot', shot, '--data', 'out/voxel_shot.json'], cwd=ROOT, check=False).returncode

def check(args):
    """计划层一条命令：--fix 先自动修 → 预检各关 → report.py 汇总。退出码 0/3/4（警告不拦）。
    只带 --shot 时是快捷路径：只逐帧重查这个镜头的体素关（几秒），别的关不动。"""
    if '--shot' in args and args.index('--shot') + 1 < len(args) and '--fix' not in args and '--layout' not in args:
        rc = shot_check(args[args.index('--shot') + 1])
        print(f'\n镜头 {args[args.index("--shot") + 1]} 复查{"没过（必过档）" if rc == 3 else "过了（警告不算）" if rc == 0 else "没跑成，按没过算"}：{os.path.join(OUT, "voxel_check_" + args[args.index("--shot") + 1] + ".md")}')
        return rc if rc in (0, 3) else 3
    if '--fix' in args: autofix()
    pre = precheck(layout='--layout' in args)
    if '--layout' in args: sh([PY, os.path.join(TOOLS, 'layout_map.py')], cwd=ROOT, check=False)
    if '--shot' in args and args.index('--shot') + 1 < len(args): shot_check(args[args.index('--shot') + 1])
    rc = timed('汇总报告', report)
    bad = [n for n, c in pre if c not in (0, 3)]            # 脚本本身出错 = 查不了，比必过还严重
    if bad: print(f'\n这几关没跑成（脚本出错）：{"、".join(bad)}——看上面的报错')
    if rc == 3 or bad: code = 3
    elif rc == 4: code = 4
    else: code = 0
    print('\n' + ('预检全过（警告不计）：可以渲染，看 out/report.md' if code == 0 else
                  '有必过没过：修好再渲，清单在 out/report.md' if code == 3 else
                  '自动修修不好（没跑过 --fix 就先 python tools/run.py check --fix）：这几条机器改不了，人工改完再跑（out/report.md）'))
    return code

def video(redo=None):
    os.makedirs(OUT, exist_ok=True); t0 = time.time()
    autofix()                                               # 先把数值类的错修掉（改了什么看 out/fixes.json）
    pre = precheck()
    rc = timed('汇总报告', report)
    if rc in (3, 4) or any(c not in (0, 3) for _, c in pre):
        why = '必过档没过' if rc == 3 else ('自动修修不好（要人工改）' if rc == 4 else '有检查脚本没跑成')
        write_timing('video（预检没过，没有渲染）')
        sys.exit(f'\n预检没过（{why}），还没开始渲染（省下整片渲染的时间）：按 out/report.md 改完再运行 python tools/run.py video')
    chunks = chunk_list(); span = lambda c: '%d_%d.mp4' % (c[1], c[2])
    todo = chunks if not redo else [c for c in chunks if c in pick(chunks, redo) or not os.path.exists(os.path.join(CHUNKS, span(c)))]
    if redo: print(f'重渲 {len(todo)}/{len(chunks)} 块：' + '、'.join(c[0] for c in todo) + '；其余用上次渲好的')
    for f in glob.glob(os.path.join(CHUNKS, '*.mp4')):   # 场景表改过以后旧边界的块用不上了
        if os.path.basename(f) not in {span(c) for c in chunks} | {'joined.mp4'}: os.remove(f)
    joined = timed(f'渲染（{sum(c[2] - c[1] for c in todo)} 帧）', render_chunks, chunks, todo, 24, CHUNKS)
    film = os.path.join(OUT, NAME + '.mp4'); shutil.copy(joined, film)   # 渲染时已经按交付规格编码（H.264、yuv420p、bt709、CRF 16），不再重编码
    mv, proxy = os.path.join(OUT, 'mv.mp4'), os.path.join(OUT, 'proxy.mp4')
    def finish():
        sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', film, '-i', os.path.join(ROOT, 'data/song.wav'), '-c:v', 'copy', '-c:a', 'aac', '-b:a', '256k', '-shortest', mv])
        # 检查用的小样：480×270、每 12 帧一个关键帧。各项检查都从它读，成片只解码这一次
        sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', film, '-an', '-vf', 'scale=480:270', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '12', '-g', '12', '-pix_fmt', 'yuv420p', proxy])
    timed('配音轨、做检查小样', finish)
    timed('接触表', sh, [PY, os.path.join(SM, 'sheet.py'), proxy, os.path.join(OUT, 'sheet.jpg'), '1.5'], check=False)
    fz = timed('不定格', sh, [PY, os.path.join(SM, 'freeze_check.py'), proxy], capture=True, check=False).stdout
    print(fz)
    os.makedirs(os.path.join(OUT, 'checks'), exist_ok=True)
    open(os.path.join(OUT, 'checks/freeze_check.txt'), 'w', encoding='utf-8').write(fz)
    timed('节拍报告', sh, [PY, os.path.join(SM, 'check.py'), '.', proxy], cwd=ROOT, check=False)       # 提示性的，不拦
    timed('逐句帧条', sh, [PY, os.path.join(TOOLS, 'strips.py'), proxy], cwd=ROOT, check=False)
    ok_act = dict(pre)['动作关'] == 0                                  # 动作关只看探针，预检的结果就是最终结果
    ok_trn = timed('转场关（量成片）', trans, proxy, False) == 0
    ok_vox = timed('体素关（量成片）', voxel, proxy, False) == 0
    ok_scn = timed('场景关（量成片）', scenes, proxy) == 0
    ok_grd = timed('调色关（量成片）', grade, proxy) == 0
    gates = [('不定格', 'FROZEN' not in fz), ('舞步关', dict(pre)['舞步关'] == 0), ('动作关', ok_act), ('转场关', ok_trn), ('体素关', ok_vox), ('运镜关', dict(pre)['运镜关'] == 0), ('场景关', ok_scn), ('钩子关', dict(pre)['钩子关'] == 0), ('调色关', ok_grd)]
    if RELAY:
        gates.append(('交接检查', timed('交接检查', sh, [PY, os.path.join(TOOLS, 'handoff_check.py'), '--segment', SEG, '--video', film, '--project', ROOT], check=False).returncode == 0))
    for f in ('act_check.md', 'act_check.png', 'trans_check.md', 'check.md', 'voxel_check.md', 'camera_check.md', 'scene_check.md', 'hook_check.md', 'grade_check.md', 'choreo_check.md', 'choreo.md', 'camplan.md', 'report.md', 'report.html', 'fixes.json'):
        if os.path.exists(os.path.join(OUT, f)): shutil.copy(os.path.join(OUT, f), os.path.join(OUT, 'checks', f))
    rc = timed('汇总报告（量成片后）', report)
    print('\n' + '\n'.join(f'  {"PASS" if g else "FAIL"}  {n}' for n, g in gates))
    crashed = any(c not in (0, 3) for _, c in pre)
    ok = all(g for _, g in gates) and crashed is False and rc not in (3, 4)
    if ok: timed('打包交付', package, film)
    write_timing('video' + (f' --redo {redo}' if redo else ''))
    if not ok:
        sys.exit('\n还不能交付：清单在 out/report.md（必过 = 要修；自动修没修好 = 要人工；警告不用管）。只改了某几个场景的话，用 python tools/run.py video --redo <场景 id> 只重渲那几块')

def preview(args):
    """边做边看：本地起一个网页服务，浏览器里带音乐实时播放当前项目（不渲染、不导出）。
    plan.json、shots.js、src/、engine/、素材 json 一改就自动刷新，停在原来的时间点；out/*_check.json 的没过项列在右边，点帧号就跳过去。"""
    import http.server, socketserver, threading, webbrowser, urllib.parse, mimetypes
    port = int(args[args.index('--port') + 1]) if '--port' in args and args.index('--port') + 1 < len(args) else 8765
    page_dir = os.path.join(TOOLS, 'preview')
    INJECT = (b'<script>(function(){var s=function(m){try{parent.postMessage({voxelPreviewError:String(m).slice(0,600)},"*")}catch(e){}};'
              b'addEventListener("error",function(e){s((e.message||"load error")+(e.filename?" @ "+e.filename.split("/").pop()+":"+e.lineno:""))},true);'
              b'addEventListener("unhandledrejection",function(e){s(e.reason&&e.reason.stack||e.reason)});'
              b'var ce=console.error;console.error=function(){s([].slice.call(arguments).join(" "));ce.apply(console,arguments)}})();</script>')
    def stamp(paths):
        m = 0.0
        for f in paths:
            try: m = max(m, os.path.getmtime(os.path.join(ROOT, f)))
            except OSError: pass
        return m
    def checks():
        out = {}
        for f in sorted(glob.glob(os.path.join(OUT, '*_check.json'))):
            try: out[os.path.basename(f)[:-11]] = {'mtime': os.path.getmtime(f), 'data': json.load(open(f, encoding='utf-8'))}
            except Exception: pass
        return out

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k): super().__init__(*a, directory=ROOT, **k)
        def log_message(self, *a): pass
        def end_headers(self):
            self.send_header('Cache-Control', 'no-store'); super().end_headers()
        def send_bytes(self, body, ctype, code=200):
            self.send_response(code); self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(body))); self.end_headers()
            if self.command != 'HEAD': self.wfile.write(body)
        def do_GET(self):
            u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query); path = urllib.parse.unquote(u.path)
            if path in ('/', '/__preview', '/__preview/'): self.send_response(302); self.send_header('Location', '/__preview/index.html'); self.end_headers(); return
            if path == '/__preview/stamp':
                body = json.dumps({'page': stamp(probe_inputs()), 'checks': max([c['mtime'] for c in checks().values()] or [0])}).encode()
                return self.send_bytes(body, 'application/json')
            if path == '/__preview/checks': return self.send_bytes(json.dumps(checks(), ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')
            if path.startswith('/__preview/'):
                f = os.path.normpath(os.path.join(page_dir, path[len('/__preview/'):]))
                if not f.startswith(page_dir) or not os.path.isfile(f): return self.send_error(404)
                return self.send_bytes(open(f, 'rb').read(), (mimetypes.guess_type(f)[0] or 'application/octet-stream') + ('; charset=utf-8' if f.endswith(('.html', '.js', '.css')) else ''))
            if path == '/index.html' and 'preview' in q:   # 页面里的报错转给预览页显示
                html = open(os.path.join(ROOT, 'index.html'), 'rb').read()
                i = html.find(b'<head>'); html = html[:i + 6] + INJECT + html[i + 6:] if i >= 0 else INJECT + html
                return self.send_bytes(html, 'text/html; charset=utf-8')
            rng = self.headers.get('Range')
            f = self.translate_path(self.path)
            if rng and os.path.isfile(f):   # 音频拖进度要 Range（http.server 自己不支持）
                size = os.path.getsize(f)
                try:
                    a, b = rng.replace('bytes=', '').split(',')[0].split('-')
                    a, b = (int(a), int(b) if b else size - 1) if a else (size - int(b), size - 1)
                except ValueError: return self.send_error(416)
                a, b = max(0, a), min(size - 1, b)
                if a > b: return self.send_error(416)
                self.send_response(206); self.send_header('Content-Type', self.guess_type(f)); self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Content-Range', f'bytes {a}-{b}/{size}'); self.send_header('Content-Length', str(b - a + 1)); self.end_headers()
                with open(f, 'rb') as fh:
                    fh.seek(a); left = b - a + 1
                    while left > 0:
                        chunk = fh.read(min(1 << 20, left))
                        if not chunk: break
                        try: self.wfile.write(chunk)
                        except (BrokenPipeError, ConnectionResetError): return
                        left -= len(chunk)
                return
            return super().do_GET()

    mimetypes.add_type('text/javascript', '.js'); mimetypes.add_type('text/javascript', '.mjs'); mimetypes.add_type('application/json', '.json')
    H.extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, '.js': 'text/javascript', '.mjs': 'text/javascript', '.wasm': 'application/wasm'}
    class S(socketserver.ThreadingMixIn, http.server.HTTPServer): daemon_threads = True; allow_reuse_address = True
    for p_ in range(port, port + 20):
        try: srv = S(('127.0.0.1', p_), H); break
        except OSError: continue
    else: sys.exit(f'端口 {port}–{port + 19} 都被占了：python tools/run.py preview --port 9000')
    url = f'http://127.0.0.1:{srv.server_address[1]}/__preview/index.html'
    print(f'预览：{url}\n  浏览器里带音乐实时播放（空格 播放/暂停，← → 一帧，Shift+← → 一拍，[ ] 设循环起止，L 开关循环）。\n'
          f'  改了 plan.json / shots.js / src/ 会自动刷新，停在原来的时间点。按 Ctrl+C 停止。')
    if '--no-open' not in args: threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: print('\n预览已停止')

def draft():
    """草稿：每秒 12 帧、不跑检查，看整体节奏用。"""
    os.makedirs(OUT, exist_ok=True)
    chunks = chunk_list()
    joined = timed('渲染草稿（每秒 12 帧）', render_chunks, chunks, chunks, 12, os.path.join(OUT, 'chunks_draft'))
    d = os.path.join(OUT, 'draft.mp4')
    timed('配音轨', sh, ['ffmpeg', '-y', '-loglevel', 'error', '-i', joined, '-i', os.path.join(ROOT, 'data/song.wav'), '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', d])
    timed('接触表', sh, [PY, os.path.join(SM, 'sheet.py'), d, os.path.join(OUT, 'sheet_draft.jpg'), '1.5'], check=False)
    write_timing('draft')
    print(f'草稿：{d}（每秒 12 帧，动作看起来会顿一点，正式片是 24 帧）；接触表 out/sheet_draft.jpg')

def package(film):
    D = os.path.join(OUT, '交付', NAME)
    shutil.rmtree(D, ignore_errors=True); os.makedirs(D)
    shutil.copy(film, D)
    for d in (('first3', 'last3', 'checks') if RELAY else ('checks',)): shutil.copytree(os.path.join(OUT, d), os.path.join(D, d))
    if RELAY: shutil.copy(os.path.join(OUT, 'handoff.json'), D)
    for f in ('sheet.jpg', 'strips.jpg', 'mv.mp4'):
        if os.path.exists(os.path.join(OUT, f)): shutil.copy(os.path.join(OUT, f), D)
    for f in ('TREATMENT.md', 'STYLE_FRAMES.md', 'CHARACTERS.md', 'CHANGES.md', 'ACTIONS.json'):
        if os.path.exists(os.path.join(ROOT, f)): shutil.copy(os.path.join(ROOT, f), D)
    if os.path.exists(os.path.join(OUT, 'style_compare.jpg')): shutil.copy(os.path.join(OUT, 'style_compare.jpg'), D)
    with zipfile.ZipFile(os.path.join(D, f'{NAME}_源码.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
        for base, dirs, files in os.walk(ROOT):
            rel = os.path.relpath(base, ROOT)
            if rel.split(os.sep)[0] in ('out', 'node_modules') or 'node_modules' in rel.split(os.sep) or rel.startswith(os.path.join('assets')) and 'frames' in rel: continue
            for f in files:
                if f == 'song.wav': continue
                z.write(os.path.join(base, f), os.path.join(rel, f))
    note = os.path.join(ROOT, '说明.md')
    if os.path.exists(note): shutil.copy(note, D)
    txt = open(note, encoding='utf-8').read() if os.path.exists(note) else ''
    print(f'\n交付文件已经打包到 {D}')
    if RELAY and ('（这里写' in txt or not txt.strip()): print('提醒：说明.md 还没写完（三五句：构思、用了哪些动作、有没有没解决的问题）。写完再运行一次 python tools/run.py video，或者直接把 说明.md 复制进交付文件夹。')

if __name__ == '__main__':
    if len(sys.argv) < 2: sys.exit(__doc__)
    m, rest = sys.argv[1], sys.argv[2:]
    if m == 'doctor': sys.exit(0 if doctor() else 1)
    elif m == 'check': sys.exit(check(rest))
    elif m == 'upgrade-engine': upgrade_engine(rest); sys.exit(0)
    elif m == 'still': still(rest or ['0'])
    elif m == 'frame':
        ts = [f'{(int(x) - PLAN["start"]) / 24:.4f}' for x in rest]
        still(ts, prefix='f_')
        for x, t in zip(rest, ts):          # 文件名换成全曲帧号：f_<帧>.jpg
            a, b = os.path.join(OUT, 'chk', f'f_{t}.jpg'), os.path.join(OUT, 'chk', f'f_{int(x)}.jpg')
            if os.path.exists(a): os.replace(a, b); print(b)
    elif m == 'act': sys.exit(act())
    elif m == 'choreo': sys.exit(choreo(*rest))
    elif m == 'camplan': sys.exit(camplan(*rest))
    elif m == 'voxel': sys.exit(voxel())
    elif m == 'scenes': sys.exit(scenes())
    elif m == 'hook': sys.exit(hook())
    elif m == 'grade': sys.exit(grade())
    elif m == 'style': style(rest or ['2', '10', '20'])
    elif m == 'actions': sh([PY, os.path.join(TOOLS, 'make_actions.py')], cwd=ROOT)
    elif m == 'trans': sys.exit(trans())
    elif m == 'video': video(rest[rest.index('--redo') + 1] if '--redo' in rest and rest.index('--redo') + 1 < len(rest) else None)
    elif m == 'selftest': selftest()
    elif m == 'draft': draft()
    elif m == 'preview': preview(rest)
    else: sys.exit(__doc__)

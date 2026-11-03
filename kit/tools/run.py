#!/usr/bin/env python3
"""voxel-mv 一条命令跑完：预检（动作关、转场登记、体素关、场景关、钩子关，不出图）→ 按场景分块渲染 → 不定格 → 各关量成片 →（分段时）交接检查 → 打包交付。
Windows、macOS、Linux 都一样用。
在项目根目录（有 index.html 和 plan.json 的那层）运行：
  python tools/run.py doctor             检查环境（node、ffmpeg、Chrome、Python 包、浏览器有没有用上显卡），第一次会自动装渲染用的 node 依赖
  python tools/run.py still 0 3.5 10     截图（项目本地秒数）→ out/chk/t_<秒>.jpg，写镜头时随时看
  python tools/run.py frame 740 903      截图（全曲帧号）→ out/chk/f_<帧>.jpg
  python tools/run.py style 3.2 11 20    风格对照：体素参考图在上，这几秒的画面在下 → out/style_compare.jpg
  python tools/run.py actions            按 plan.json 的动作轨重新生成 ACTIONS.json（动作关 G4 对照用）
  python tools/run.py act                动作关（约 1 分钟）→ out/act_check.md、out/act_check.png
  python tools/run.py trans              转场表检查 → out/trans_check.md
  python tools/run.py voxel              体素关（等高、贴地、不打滑、不发糊、坏帧、移轴、表情卡拍）→ out/voxel_check.md
  python tools/run.py scenes             场景关（场景表完整、每个场景 10–20 秒左右、相邻场景看得出换了、换场景有转场）→ out/scene_check.md
  python tools/run.py hook               钩子关（开场 5 秒、没词长段每 4 小节、人声进来那一拍、副歌 / 间奏 / 桥段开头都有事件）→ out/hook_check.md
  python tools/run.py grade              调色关（每段有调色关键帧；量成片：段落之间有明暗起伏、副歌放开、桥段有反差、暗段也看得清）→ out/grade_check.md
  python tools/run.py video              全流程：预检 → 渲染 → 全部检查 + 接触表、逐句帧条 → 打包到 out/交付/（不过关会停下并说明原因）
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

def act():
    r = node(os.path.join(SM, 'probe_dump.mjs'), LIB, ROOT, '24')
    if r.returncode: return False
    return sh([PY, os.path.join(SM, 'act_check.py'), '.', '--mode', 'safe' if SAFE else 'free'], cwd=ROOT, check=False).returncode == 0

def trans(video=None, dump=True):
    if dump: node(os.path.join(SM, 'probe_dump.mjs'), LIB, ROOT, '24', '--meta-only')
    cmd = [PY, os.path.join(SM, 'trans_check.py'), '.'] + ([video] if video else []) + ['--mode', 'safe' if SAFE else 'free']
    return sh(cmd, cwd=ROOT, check=False).returncode == 0

def latest_video():   # 检查用的成片：优先用 480×270 的小样（解码快），没有就用 mv.mp4
    for f in ('proxy.mp4', 'mv.mp4'):
        if os.path.exists(os.path.join(OUT, f)): return os.path.join(OUT, f)
    return None

def voxel(video='latest', dump=True):
    if dump and node(os.path.join(TOOLS, 'voxel_dump.mjs'), LIB, ROOT, '1').returncode: return False
    if video == 'latest': video = latest_video()
    return sh([PY, os.path.join(TOOLS, 'voxel_check.py')] + ([video] if video else []), cwd=ROOT, check=False).returncode == 0

def scenes(video='latest'):
    if video == 'latest': video = latest_video()
    return sh([PY, os.path.join(TOOLS, 'scene_check.py')] + ([video] if video else []), cwd=ROOT, check=False).returncode == 0

def hook():
    return sh([PY, os.path.join(TOOLS, 'hook_check.py'), ROOT], cwd=ROOT, check=False).returncode == 0

def grade(video='latest'):
    if video == 'latest': video = latest_video()
    return sh([PY, os.path.join(TOOLS, 'grade_check.py')] + ([video] if video else []), cwd=ROOT, check=False).returncode == 0

def style(times):
    still(times, prefix='s_')
    sh([PY, os.path.join(TOOLS, 'style_compare.py')] + [os.path.join(OUT, 'chk', f's_{float(t):.4f}.jpg') for t in times], cwd=ROOT, check=False)

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

def precheck():
    """不出图就能查的关先查：动作关、转场登记、体素关（不量画面的部分）、场景关（不量画面的部分）、钩子关。"""
    res = [('动作关', timed('预检 · 动作关', act)), ('转场关', timed('预检 · 转场登记', trans, None)),
           ('体素关', timed('预检 · 体素关', voxel, None)), ('场景关', timed('预检 · 场景关', scenes, None)),
           ('钩子关', timed('预检 · 钩子关', hook)), ('调色关', timed('预检 · 调色关', grade, None))]
    print('\n预检：' + '  '.join(f'{"PASS" if g else "FAIL"} {n}' for n, g in res))
    return res

def video(redo=None):
    os.makedirs(OUT, exist_ok=True); t0 = time.time()
    pre = precheck()
    if SAFE and not all(g for _, g in pre):
        write_timing('video（预检没过，没有渲染）')
        sys.exit('\n预检没过，还没开始渲染（省下整片渲染的时间）：按 out/ 里对应的报告改完再运行 python tools/run.py video')
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
    ok_act = dict(pre)['动作关']                                       # 动作关只看探针，预检的结果就是最终结果
    ok_trn = timed('转场关（量成片）', trans, proxy, False)
    ok_vox = timed('体素关（量成片）', voxel, proxy, False)
    ok_scn = timed('场景关（量成片）', scenes, proxy)
    ok_grd = timed('调色关（量成片）', grade, proxy)
    gates = [('不定格', 'FROZEN' not in fz), ('动作关', ok_act), ('转场关', ok_trn), ('体素关', ok_vox), ('场景关', ok_scn), ('钩子关', dict(pre)['钩子关']), ('调色关', ok_grd)]
    if RELAY:
        gates.append(('交接检查', timed('交接检查', sh, [PY, os.path.join(TOOLS, 'handoff_check.py'), '--segment', SEG, '--video', film, '--project', ROOT], check=False).returncode == 0))
    for f in ('act_check.md', 'act_check.png', 'trans_check.md', 'check.md', 'voxel_check.md', 'scene_check.md', 'hook_check.md', 'grade_check.md'):
        if os.path.exists(os.path.join(OUT, f)): shutil.copy(os.path.join(OUT, f), os.path.join(OUT, 'checks', f))
    if SAFE is False: gates = [(n, g or n != '不定格') for n, g in gates]   # 自由模式：只有不定格拦
    print('\n' + '\n'.join(f'  {"PASS" if g else "FAIL"}  {n}' for n, g in gates))
    ok = all(g for _, g in gates)
    if ok: timed('打包交付', package, film)
    write_timing('video' + (f' --redo {redo}' if redo else ''))
    if not ok:
        sys.exit('\n还不能交付：按 out/checks/ 里对应的报告改。只改了某几个场景的话，用 python tools/run.py video --redo <场景 id> 只重渲那几块')

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
    elif m == 'still': still(rest or ['0'])
    elif m == 'frame':
        ts = [f'{(int(x) - PLAN["start"]) / 24:.4f}' for x in rest]
        still(ts, prefix='f_')
        for x, t in zip(rest, ts):          # 文件名换成全曲帧号：f_<帧>.jpg
            a, b = os.path.join(OUT, 'chk', f'f_{t}.jpg'), os.path.join(OUT, 'chk', f'f_{int(x)}.jpg')
            if os.path.exists(a): os.replace(a, b); print(b)
    elif m == 'act': sys.exit(0 if act() else 1)
    elif m == 'voxel': sys.exit(0 if voxel() else 1)
    elif m == 'scenes': sys.exit(0 if scenes() else 1)
    elif m == 'hook': sys.exit(0 if hook() else 1)
    elif m == 'grade': sys.exit(0 if grade() else 1)
    elif m == 'style': style(rest or ['2', '10', '20'])
    elif m == 'actions': sh([PY, os.path.join(TOOLS, 'make_actions.py')], cwd=ROOT)
    elif m == 'trans': sys.exit(0 if trans() else 1)
    elif m == 'video': video(rest[rest.index('--redo') + 1] if '--redo' in rest and rest.index('--redo') + 1 < len(rest) else None)
    elif m == 'draft': draft()
    else: sys.exit(__doc__)

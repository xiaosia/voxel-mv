#!/usr/bin/env python3
"""引擎分发：给项目的 engine/ 记版本和每个文件的 sha256，校验有没有被手改，升级时整份备份再覆盖。
new_project.py 建项目时写、run.py 的 upgrade-engine / check 用。项目里的 engine/ 不要手改：
要改引擎就改 skill 的 kit/engine/，再在项目里跑 python tools/run.py upgrade-engine。"""
import hashlib, json, os, shutil, subprocess, time

META = 'ENGINE_VERSION'
IGNORE_FILES = {'.DS_Store'}
SKIP_DIRS = {'__pycache__', 'node_modules'}


def file_hashes(engine_dir):
    """{相对路径: sha256}；ENGINE_VERSION 自己不算在内。"""
    out = {}
    if not os.path.isdir(engine_dir): return out
    for base, dirs, files in os.walk(engine_dir):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for f in sorted(files):
            if f == META or f in IGNORE_FILES or f.endswith('.pyc'): continue
            p = os.path.join(base, f)
            rel = os.path.relpath(p, engine_dir).replace(os.sep, '/')
            out[rel] = hashlib.sha256(open(p, 'rb').read()).hexdigest()
    return out


def skill_version(skill):
    """skill 的版本号：优先 VERSION 文件，其次 git 短哈希（从 zip 解压时没有 .git）。"""
    vf = os.path.join(skill, 'VERSION')
    if os.path.exists(vf):
        v = open(vf, encoding='utf-8').read().strip()
        if v: return v
    try:
        r = subprocess.run(['git', '-C', skill, 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip(): return r.stdout.strip()
    except OSError:
        pass
    return 'unversioned'


def write_version(engine_dir, skill):
    meta = {'format': 1, 'version': skill_version(skill), 'skill': os.path.abspath(skill), 'files': file_hashes(engine_dir)}
    os.makedirs(engine_dir, exist_ok=True)
    json.dump(meta, open(os.path.join(engine_dir, META), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return meta


def read_version(engine_dir):
    p = os.path.join(engine_dir, META)
    if not os.path.exists(p): return None
    try: return json.load(open(p, encoding='utf-8'))
    except (ValueError, OSError): return None


def diff(engine_dir, meta):
    """登记过的哈希 vs 现在磁盘上的文件：{modified, missing, extra}。"""
    want = (meta or {}).get('files') or {}
    now = file_hashes(engine_dir)
    return {
        'modified': sorted(f for f in want if f in now and now[f] != want[f]),
        'missing': sorted(f for f in want if f not in now),
        'extra': sorted(f for f in now if f not in want),
    }


def _copy(src, dst):
    copied = []
    for base, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel = os.path.relpath(base, src)
        target = dst if rel == '.' else os.path.join(dst, rel)
        os.makedirs(target, exist_ok=True)
        for f in files:
            if f == META or f in IGNORE_FILES or f.endswith('.pyc'): continue
            shutil.copy2(os.path.join(base, f), os.path.join(target, f))
            copied.append(os.path.relpath(os.path.join(base, f), src).replace(os.sep, '/'))
    return copied


def backup(engine_dir, root):
    """整份拷到 <项目>/engine_bak/<时间>/，同一秒重名时加序号。"""
    if not os.path.isdir(engine_dir): return None
    base = os.path.join(root, 'engine_bak', time.strftime('%Y%m%d-%H%M%S'))
    bdir, n = base, 1
    while os.path.exists(bdir):
        bdir = f'{base}-{n}'; n += 1
    shutil.copytree(engine_dir, bdir, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    return bdir


def upgrade(engine_dir, skill, root):
    """备份项目引擎 → 用 skill 的 kit/engine 覆盖 → 重写 ENGINE_VERSION。
    返回 {backup, meta, local, changed}：local 是升级前项目里被手改/多出的文件，changed 是这次升级实际换掉的文件。"""
    src = os.path.join(skill, 'kit', 'engine')
    if not os.path.isdir(src): raise RuntimeError(f'找不到 skill 的引擎：{src}')
    old = read_version(engine_dir)
    local = diff(engine_dir, old) if old else None
    bak = backup(engine_dir, root)
    _copy(src, engine_dir)
    meta = write_version(engine_dir, skill)
    of, nf = (old or {}).get('files') or {}, meta['files']
    changed = sorted(set(f for f in nf if of.get(f) != nf[f]) | set(f for f in of if f not in nf))
    return {'backup': bak, 'meta': meta, 'local': local, 'changed': changed}

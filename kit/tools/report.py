#!/usr/bin/env python3
"""汇总各关的 out/<tool>.json 成一份报告：out/report.md + out/report.html。
各关原来的详细表格拷到 out/checks/ 当附录，报告里只留分档结论和链接。
结构（交接文档 3.6）：必过（拦渲染）/ 已自动修（plan.json 已改，备份 plan.bak.json）/ 警告。
用法：python tools/report.py（在项目根目录；run.py check / video 最后一步会调）。"""
import glob, json, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checks_common as CC
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')

OUT = 'out'
CN_NAME = {'voxel_check': '体素关', 'scene_check': '场景关', 'hook_check': '钩子关', 'grade_check': '调色关',
           'choreo_check': '舞步关', 'act_check': '动作关', 'trans_check': '转场关', 'freeze_check': '不定格关',
           'camera_check': '运镜关', 'handoff_check': '交接关'}
ORDER = ['voxel_check', 'camera_check', 'scene_check', 'choreo_check', 'act_check', 'trans_check', 'hook_check', 'grade_check', 'freeze_check', 'handoff_check']

os.makedirs(os.path.join(OUT, 'checks'), exist_ok=True)
tools, rules, fixes = [], [], []
for p in sorted(glob.glob(os.path.join(OUT, '*_check.json'))):
    tool = os.path.basename(p)[:-5]
    try: d = json.load(open(p, encoding='utf-8'))
    except Exception: continue
    for r in d.get('rules') or []: r.setdefault('tool', tool); r.setdefault('tier', CC.tier(r['rule']))
    rules += d.get('rules') or []
    if tool not in tools: tools.append(tool)
    src = os.path.join(OUT, tool + '.md')
    if os.path.exists(src): shutil.copy(src, os.path.join(OUT, 'checks', tool + '.md'))
fx = os.path.join(OUT, 'fixes.json')
if os.path.exists(fx):
    try: fixes = json.load(open(fx, encoding='utf-8')).get('fixes') or []
    except Exception: fixes = []

must = [r for r in rules if r['tier'] == 'must' and not r['ok']]
warn = [r for r in rules if r['tier'] == 'warn' and not r['ok']]
auto_bad = [r for r in rules if r['tier'] == 'auto' and not r['ok']]
head = '✅ 可以渲染' if not must else f'❌ 有 {len(must)} 条必过没过'

def rows(rs):
    body = [f"| {CN_NAME.get(r['tool'], r['tool'])} | {r['rule']} {r.get('name', '')} | {str(r.get('detail', ''))[:200]} |" for r in rs]
    return ['| 关 | 规则 | 说明 |', '|---|---|---|'] + (body or ['| — | 无 | |'])

md = [f'# 检查报告  {head}', '']
if not rules and not fixes: md += ['（还没有检查结果：先跑 python tools/run.py check）', '']
if must: md += [f'## 必过（{len(must)}）——修好之前不渲染', ''] + rows(must) + ['']
if auto_bad: md += [f'## 自动修没修好（{len(auto_bad)}）——机器修不了，要人工改', ''] + rows(auto_bad) + ['']
md += [f'## 已自动修（{len(fixes)}）', '', 'plan.json 已改（旧版在 plan.bak.json）；修过的条目带 "_auto": true。', '',
      '| 关 | 位置 | 改了什么 |', '|---|---|---|',
      *( [f"| {f['rule']} | {f.get('where', '')} | {f.get('detail', '')} |" for f in fixes] or ['| — | 无 | |'])]
md += ['', f'## 警告（{len(warn)}）——只报告，不拦', ''] + rows(warn) + ['']
md += ['## 附录（各关详细表格）', ''] + [f'- [{CN_NAME.get(t, t)}](checks/{t}.md)' for t in ORDER if t in tools] + ['']
open(os.path.join(OUT, 'report.md'), 'w', encoding='utf-8').write('\n'.join(md) + '\n')

esc = lambda s: str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
def tbl(title, rs, note=''):
    h = f'<h2>{esc(title)}</h2>' + (f'<p>{esc(note)}</p>' if note else '')
    if not rs: return h + '<p>无</p>'
    h += '<table><tr><th>关</th><th>规则</th><th>说明</th></tr>'
    h += ''.join(f"<tr><td>{esc(CN_NAME.get(r['tool'], r['tool']))}</td><td><b>{esc(r['rule'])}</b> {esc(r.get('name', ''))}</td><td>{esc(str(r.get('detail', ''))[:300])}</td></tr>" for r in rs)
    return h + '</table>'
html = ['<!doctype html><meta charset="utf-8"><title>检查报告</title>',
        '<style>body{font-family:system-ui,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#222}',
        'h1{font-size:22px} h2{font-size:17px;margin-top:28px;border-bottom:1px solid #ddd;padding-bottom:4px}',
        'table{border-collapse:collapse;width:100%;font-size:13px} td,th{border:1px solid #ddd;padding:4px 8px;text-align:left;vertical-align:top} th{background:#f5f5f5}',
        '.bad{color:#c22;font-weight:600} .ok{color:#181}</style>',
        f'<h1>检查报告 <span class="{"ok" if not must else "bad"}">{esc(head)}</span></h1>']
if must: html.append(tbl(f'必过（{len(must)}）——修好之前不渲染', must))
if auto_bad: html.append(tbl(f'自动修没修好（{len(auto_bad)}）——要人工改', auto_bad))
html.append(tbl(f'已自动修（{len(fixes)}）', [{'tool': f['rule'], 'rule': f.get('where', ''), 'name': '', 'detail': f.get('detail', '')} for f in fixes],
                'plan.json 已改（旧版在 plan.bak.json）；修过的条目带 "_auto": true。'))
html.append(tbl(f'警告（{len(warn)}）——只报告，不拦', warn))
html.append('<h2>附录</h2><ul>' + ''.join(f'<li><a href="checks/{esc(t)}.md">{esc(CN_NAME.get(t, t))}</a></li>' for t in ORDER if t in tools) + '</ul>')
open(os.path.join(OUT, 'report.html'), 'w', encoding='utf-8').write('\n'.join(html) + '\n')

print(f'-> out/report.md, out/report.html  {head}；自动修没修好 {len(auto_bad)}，自动修 {len(fixes)}，警告 {len(warn)}')
sys.exit(3 if must else (4 if auto_bad else 0))   # 3 = 必过没过（拦），4 = 自动修修不好（要人工，也拦），0 = 干净（警告不拦）

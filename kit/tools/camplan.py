#!/usr/bin/env python3
"""运镜起草：按段落表给每个场景出一份 camera 轨草稿和段落边界的转场草稿（out/camplan.md 人类可读，--apply 写进 plan.json）。
只是起草不是规定：写出来的都是起点数值，人工改过再 check；不跑这个工具、plan 里不写 camera/cuts，画面和以前一样。
和编舞联动：舞句里有翻面步的，起手那拍建议一记快速变焦；canon（轮唱式错拍起跳）的，建议跟镜头。
转场跟着能量走：能量升上去的边界（进副歌、进 drop）放重转场（方块雨、甩镜、光爆、闪白…轮着来，T6 不许同种连用），
能量持平或落下来的边界（主歌内部、进尾奏）放轻的（横条、圈入、光晕、落色——落色只往头尾放）。

  python tools/camplan.py            草稿 → out/camplan.md（每段建议什么运镜、每条边界放什么转场、为什么）
  python tools/camplan.py --apply    把草稿写进 plan.json 的 camera 和 cuts（cuts 只在原来为空时写，要覆盖加 --force；
                                     旧的整份备份成 plan.before_camplan.json）
草稿按段落能量配运镜：intro 慢推、verse 慢移、pre-chorus/build 变焦蓄力、chorus 环绕+打点、
drop 冲击、interlude 升降、bridge 拉远+降（换口气）、outro 慢拉收尾；
起草自带底线：全片 ≥3 种运镜、单一种类不占一半、副歌比主歌动得多（camera_check.py 的 K1 会复核）。
"""
import json, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8', errors='replace'); sys.stderr.reconfigure(encoding='utf-8', errors='replace')

FPS = 24
LEVEL = {'intro': 1, 'verse': 1, 'pre-chorus': 2, 'chorus': 3, 'interlude': 2, 'bridge': 1, 'outro': 1, 'build': 2, 'drop': 3}
JSON_OUT = '--json' in sys.argv


def opt(args, name, default=None):
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default


def phrase_has_turn(mv, pid):
    return any(s.get('turn') for s in (mv.get('phrases', {}).get(pid) or {}).get('steps', []))


def draft(P='.'):
    plan = json.load(open(os.path.join(P, 'plan.json'), encoding='utf-8'))
    START, END = plan['start'], plan['end']
    B0, SPB = (plan.get('tempo') or {}).get('beat0', 0), (plan.get('tempo') or {}).get('spb', 0.5)
    from dance import load_moves
    MV = load_moves(P, plan)
    ST = json.load(open(os.path.join(P, 'data/structure.json'), encoding='utf-8')) if os.path.exists(os.path.join(P, 'data/structure.json')) else {'parts': []}
    parts = [dict(p, f0=START + round(p['t0'] * FPS), f1=START + round(p['t1'] * FPS)) for p in ST.get('parts', [])]

    # 分段：有场景表按场景，没有就按段落，再没有 10 秒一段
    if plan.get('scenes'):
        segs = [(s['id'], s['f0'], s['f1']) for s in sorted(plan['scenes'], key=lambda x: x['f0'])]
    elif parts:
        segs = [(p.get('name', p['label']), p['f0'], p['f1']) for p in parts]
    else:
        segs = [(f'{a / FPS:.0f}s', a, min(END, a + 240)) for a in range(START, END, 240)]

    def label_at(f):
        lab = [p for p in parts if p['f0'] <= f < p['f1']]
        return lab[0]['label'] if lab else 'verse'

    tracks = plan.get('tracks') or {}
    cam, notes, vi = [], [], 0                       # vi = chorus 序号（每遍副歌环绕方向/幅度递进）
    for name, f0, f1 in segs:
        if f1 - f0 < 8: continue
        lab = label_at((f0 + f1) // 2)
        base = {'f0': f0, 'f1': f1}
        got = []
        if lab == 'intro':
            got = [dict(base, move='dolly', amt=0.8, ease='easeIO'), dict(base, move='handheld', amt=0.03)]
        elif lab == 'verse':
            m = ['truck', 'pan', 'dolly'][vi % 3]
            got = [dict(base, move=m, **({'deg': 12} if m == 'pan' else {'amt': 0.6})), dict(base, move='bob', amt=0.02)]
        elif lab in ('pre-chorus', 'build'):
            got = [dict(base, move='zoom', amt=-6, ease='easeIO'), dict(base, move='dolly', amt=0.6)]
        elif lab == 'chorus':
            vi += 1
            a = 30 + vi * 10
            got = [dict(base, move='orbit', **({'from': 0, 'to': a} if vi % 2 else {'from': -a, 'to': 0}), ease='easeIO'),
                   dict(base, move='punch', amt=0.15, on='hit')]
        elif lab == 'drop':
            got = [dict(base, move='punch', amt=0.2, on='hit'), dict(base, move='handheld', amt=0.05)]
        elif lab == 'interlude':
            got = [dict(base, move='crane', amt=1.2, ease='easeIO')]
        elif lab == 'bridge':
            got = [dict(base, move='dolly', amt=-1.0, ease='easeIO'), dict(base, move='crane', amt=-0.8, ease='easeIO')]
        else:   # outro / 没认出来的
            got = [dict(base, move='dolly', amt=-1.2, ease='easeOut'), dict(base, move='handheld', amt=0.02)]
        # 编舞联动：翻面起手 → 快速变焦一记；canon → 跟镜头
        for who, tr in tracks.items():
            for k, e in enumerate(tr):
                if e[0] != 'dance' or not (f0 <= e[2] < f1): continue
                o = e[4] if len(e) > 4 and isinstance(e[4], dict) else {}
                if phrase_has_turn(MV, e[1]):
                    got.append({'f0': e[2], 'f1': min(e[2] + 6, f1), 'move': 'zoom', 'amt': -4, 'ease': 'expo',
                                'why': f'{who} 翻面起手（{e[1]}）打一记'})
                if o.get('canon'):
                    end = None
                    for x in tr[k + 1:]: end = x[1] if x[0] == 'off' else x[2]; break
                    got.append({'f0': e[2], 'f1': min(end or f1, f1), 'move': 'follow', 'who': who,
                                'why': f'{who} canon 错拍起跳，跟住'})
        cam += got
        hum = '、'.join(f"{g['move']}" + (f" {g['from']}→{g['to']}" if g['move'] == 'orbit' else '') for g in got)
        notes.append((name, lab, f0, f1, hum))

    # 底线：≥3 种；不够就把最长的 verse 换成 orbit
    kinds = {g['move'] for g in cam}
    if len(kinds) < 3:
        vs = [g for g in cam if g['move'] in ('truck', 'pan', 'dolly') and (label_at(g['f0']) == 'verse')]
        if vs:
            g = max(vs, key=lambda x: x['f1'] - x['f0'])
            g.pop('amt', None); g.pop('deg', None)
            g.update(move='orbit'); g['from'] = 0; g['to'] = 40
            kinds = {g2['move'] for g2 in cam}
            notes.append(('底线', '-', 0, 0, f'种类不够 3，把最长的一段 verse 换成 orbit（现在 {"、".join(sorted(kinds))}）'))

    # 转场草稿：段落边界一条，能量升上去放重的，持平或落下放轻的；key 就用场景边界帧（不吸拍——
    # 转场 shader 的 A/B 两面按 c−1/c 取景，挪离边界两边就成同一个场景了），在不在拍上写进草稿让人工看
    TL = {}
    tlp = os.path.join(P, 'data/audio.timeline.json')
    if os.path.exists(tlp):
        TL = json.load(open(tlp, encoding='utf-8'))
    grid = sorted([*(TL.get('beat_times') or []), *(TL.get('bar_times') or []), *(h['time'] for h in TL.get('hits') or [])])
    LYR = json.load(open(os.path.join(P, 'data/lines.json'), encoding='utf-8')).get('lines', []) if os.path.exists(os.path.join(P, 'data/lines.json')) else []
    heavy_cycle = ['rain', 'whip', 'voxel', 'through', 'crumble', 'flash']
    light_cycle = ['rows', 'iris', 'leak', 'split', 'dip']
    cuts, cut_rows, hi, li = [], [], 0, 0
    for (na, fa, fb), (nb, fb2, fc) in zip(segs, segs[1:]):
        la, lb = label_at((fa + fb) // 2), label_at((fb2 + fc) // 2)
        if fc - fb2 < 8: continue
        heavy = LEVEL.get(lb, 1) > LEVEL.get(la, 1) or lb == 'drop'   # 进 drop 一定是重的（T5 要炸点上有重转场）
        if heavy:
            mode = heavy_cycle[hi % len(heavy_cycle)]; hi += 1
            why = f'{la}→{lb} 能量升上去，用重的 {mode}'
        else:
            mode = 'dip' if lb == 'outro' else light_cycle[li % len(light_cycle)]; li += 1
            why = f'{la}→{lb} 能量持平或落下，用轻的 {mode}' + ('（落色放尾奏）' if mode == 'dip' else '')
        c = {'c': fb2, 'len': 16 if mode == 'dip' else 12, 'mode': mode, 'from': na, 'to': nb, 'note': why}
        cuts.append(c)
        voc = [l['t'] for l in LYR[1:] if fb2 / FPS <= l['t'] < fb2 / FPS + 2 * (TL.get('seconds_per_beat') or SPB) * 2]
        if voc: c['note'] += f'；人声第一拍在 {voc[0]:.2f}s（和边界差 {round(voc[0] * FPS - fb2)} 帧，要跟人声就一起挪场景表）'
        if not grid: ongrid = '（没有拍表，看不出）'
        else:
            ongrid = '在拍上' if min(abs(g - fb2 / FPS) for g in grid) <= 1 / FPS + 1e-3 else '不在拍上（T3 会想吸附：先挪场景边界，别让它挪转场）'
        cut_rows.append((f'{na}→{nb}', f'{la}→{lb}', '重' if heavy else '轻', mode, f"{fb2} ({fb2 / FPS:.2f}s)", ongrid, c['note']))
    return plan, cam, notes, kinds, cuts, cut_rows


def main():
    P = '.'
    args = sys.argv[1:]
    plan, cam, notes, kinds, cuts, cut_rows = draft(P)
    lines = ['# 运镜草稿（camplan）', '', f"段落能量配的运镜，{len(notes)} 段、{len(cam)} 条、种类 {'、'.join(sorted(kinds))}。数值是起点，写完跑 python tools/run.py check 让运镜关复核。", '',
             '| 段 | 段落 | 帧 | 建议 |', '|---|---|---|---|']
    lines += ['| %s | %s | %d–%d | %s |' % n for n in notes]
    lines += ['', '## 转场草稿（cuts）', '', '段落边界一条：能量升上去用重的（轮着换，别同种连用），持平或落下用轻的，落色只往尾奏放。key 就放在场景边界帧上——转场两边按 c−1/c 取景，挪离边界两面就成同一个场景了；要跟人声第一拍就一起挪场景表。', '',
              '| 边界 | 段落 | 轻/重 | mode | key | 在拍? | 说明 |', '|---|---|---|---|---|---|---|']
    lines += ['| %s | %s | %s | %s | %s | %s | %s |' % r for r in cut_rows]
    lines += ['', '## camera 轨 JSON', '', '```json', json.dumps(cam, ensure_ascii=False, indent=1), '```',
              '', '## cuts JSON', '', '```json', json.dumps(cuts, ensure_ascii=False, indent=1), '```',
              '', '--apply 写进 plan.json 的 camera 和 cuts（cuts 只在原来为空时写，要覆盖加 --force；旧 plan 备份成 plan.before_camplan.json）。']
    os.makedirs(os.path.join(P, 'out'), exist_ok=True)
    open(os.path.join(P, 'out/camplan.md'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    if JSON_OUT: print(json.dumps({'camera': cam, 'cuts': cuts}, ensure_ascii=False))
    else: print(f'运镜草稿：{len(notes)} 段 {len(cam)} 条、{"、".join(sorted(kinds))}；转场草稿：{len(cuts)} 条边界 -> out/camplan.md')
    if '--apply' in args:
        if plan.get('camera') and '--force' not in args:
            sys.exit('plan.json 已经有 camera 轨了：要覆盖加 --force（会先备份）。')
        keep_cuts = bool(plan.get('cuts')) and '--force' not in args   # 已有 cuts 只写 camera，cuts 不动（覆盖加 --force）
        bk = os.path.join(P, 'plan.before_camplan.json')
        i = 1
        while os.path.exists(bk): bk = os.path.join(P, f'plan.before_camplan{i}.json'); i += 1
        shutil.copy(os.path.join(P, 'plan.json'), bk)
        plan['camera'] = cam
        if not keep_cuts: plan['cuts'] = cuts
        with open(os.path.join(P, 'plan.json'), 'w', encoding='utf-8') as fh: json.dump(plan, fh, ensure_ascii=False, indent=1)
        print(f"camera 轨（{len(cam)} 条）已写入 plan.json" +
              (f"；原来已有 cuts（{len(plan['cuts'])} 条），没动——要换成草稿加 --force" if keep_cuts else f"，cuts（{len(cuts)} 条）也写进去了") +
              f"，旧版在 {os.path.basename(bk)}")


if __name__ == '__main__':
    main()

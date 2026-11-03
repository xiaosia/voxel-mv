"""检查分档共用：必过（拦）/ 自动修（--fix 修完重判，修不好才拦）/ 警告（只报告）。
各检查脚本把结果凑成 rules 列表，dump_json() 写 out/<tool>.json 给 tools/report.py 汇总；
exit_code() 只按必过档给退出码——稳妥和自由模式都一样拦必过（三档定义，MODE 只影响报告措辞）。
必过现在 11 条 + 交接关（接力才有）+ 冻结关：V0 V4 STUCK G1 G2 D0 H1 H4 T5 K1，成片再判 T1、FREEZE；
交接卡全部项聚合成一条 HANDOFF（必过）。
第 4 批接运镜关：K1+K3 合并成 K1 进必过（不写 camera 轨的老项目从 CAMLOG 实际运动推种类，不冤枉），
K6 引擎运行时夹好了、这里按「已自动修」判，其余 K 警告。第 5 批转场 T6–T8 也是警告：重转场别连用、落色只在头尾、方向接得上。"""
import json, os, sys

MUST = {'V0', 'V4', 'STUCK', 'G1', 'G2', 'D0', 'H1', 'H4', 'T5', 'T1', 'FREEZE', 'HANDOFF', 'K1'}
AUTO = {'V1', 'V2', 'V3', 'V5', 'V7', 'G4', 'D1', 'T3', 'T4', 'C1', 'C4', 'K6'}
CN = {'must': '必过', 'auto': '自动修', 'warn': '警告'}

def tier(rule):
    """规则 id → 档位。STUCK-xxx 这种带后缀的按前缀算。"""
    r = rule.split('-')[0].split('+')[0].strip()
    return 'must' if r in MUST else ('auto' if r in AUTO else 'warn')

def rules_of(fails):
    """fails: [(rule, msg)] → 结构化 rules 列表（给 dump_json）"""
    return [{'rule': r, 'tier': tier(r), 'ok': False, 'detail': m} for r, m in fails]

def dump_json(tool, rules, out_dir='out'):
    """rules: [{'rule','name','ok','detail'}]（缺 tier 字段就按规则 id 补）。写 out/<tool>.json 返回路径。"""
    for r in rules: r.setdefault('tier', tier(r['rule']))
    ok = not any(not r['ok'] and r['tier'] == 'must' for r in rules)
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, f'{tool}.json')
    json.dump({'tool': tool, 'ok': ok, 'rules': rules}, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1,
              default=lambda o: o.item() if hasattr(o, 'item') else str(o))   # numpy 标量（sync、中位数）兜底
    return p

def exit_code(rules):
    """退出码：有必过 FAIL → 3（各检查脚本原来的非零码），否则 0。"""
    return 3 if any(not r['ok'] and tier(r['rule']) == 'must' for r in rules) else 0

def allow_map(plan, rule):
    """plan.json 的 allow 豁免（autofix 迁移 occlude 也写这里）→ [(who, f0, f1, why)]，rule 对得上的才返回。"""
    return [(a.get('who'), a.get('f0'), a.get('f1'), a.get('why') or '')
            for a in plan.get('allow') or [] if a.get('rule') == rule]

def allowed(als, who, f):
    """这一帧这条豁免盖不盖得住：who 对得上（或 * / 空 = 全部）且 f 在 [f0, f1] 里。写错时间的豁免盖不住 = 照样 FAIL。"""
    return any(w in (who, None, '*') and f0 is not None and f0 <= f <= f1 for w, f0, f1, _ in als)

def covered(als, who, f0, f1):
    """[f0, f1] 整段被豁免盖住才免；只盖一半 = 没盖住。返回盖住的比例（1 = 全盖）。"""
    if not als: return 0.0
    n = d = 0
    for f in range(f0, f1 + 1):
        n += 1; d += 1 if allowed(als, who, f) else 0
    return d / max(n, 1)

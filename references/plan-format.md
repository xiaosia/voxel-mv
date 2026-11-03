# plan.json 字段

`new_project.py` 会写一份空白的。引擎（`R.run`）、检查脚本都读它。帧号一律是**全曲帧号**（第 n 帧 = 第 n/24 秒）。

| 字段 | 谁用 | 说明 |
|---|---|---|
| `segment`、`maker` | run.py | 交付文件名 `<segment>_<maker>`。单曲 MV 用 `MV` 和片名 |
| `lead` | 你 | 主角 |
| `start`、`end` | 引擎、全部检查 | 本片的帧范围（含头不含尾）。单曲 MV 是 0 和全曲帧数；接力分段是本段的切点 |
| `tempo` | 引擎 | `{beat0, spb}` 固定节拍网格（第 0 拍的秒数、每拍秒数），`beatOf`、踩拍、`beatFrame` 都按它 |
| `cast` | 引擎 | 出场角色（`assets/` 下的文件夹名），只加载这些 |
| `scenes` | 场景关 | `[{id, f0, f1, world, look, why?, same_as?}]`：全片的场景表，从 `start` 连到 `end`。一个场景 = 一套布景（地点 + 光色），10–20 秒左右；`why` 写故意短于 8 秒的原因，`same_as` 标故意回到的前一个场景 |
| `shots` | 引擎、你 | `[{id, f0, f1, lyric?, camera?, need?, …}]`，`R.shotOf(sf)` 按帧找镜头；除 id/f0/f1 外的字段随你写（分镜笔记） |
| `cuts` | 引擎、转场关 | 镜头之间的转场，见 engine.md |
| `incamera` | 转场关 | 镜头内的大变化 `{shot, f0, f1, key, note}` |
| `emotes` | 引擎、体素关 V7 | 表情符号 `{who, g, f0, f1, dx}` |
| `events` | 钩子关 | `[{f, what}]`：动作轨、转场、表情以外的画面事件（镜头揭示、片名出现、道具亮起、新东西入画），开场 5 秒、没词的长段、人声进来那一拍靠它们和动作、转场一起过钩子关。登记了就要真的做出来 |
| `tracks` | 引擎、动作关 | 动作轨，见 engine.md |
| `extra_actions` | 引擎 | `{名字: [动作…]}`：轨里没有、但要手动 `pose` 的动作 |
| `sizes` | 体素关 V1 | `{名字: {scale, why}}`：故意放大缩小的角色（巨人、远处的倒影） |
| `occlude` | 体素关 V2 | `[{who, f0, f1, why}]`：故意让脚被挡住（站在草丛里、躲在墙后） |
| `treadmill` | 体素关 V3 | `[{who, f0, f1, why}]`：故意原地走（跑步机、梦里走不动） |
| `handoffs`、`handoff_cards` | 接力 | 见 relay.md；单曲 MV 留空 |

`ACTIONS.json` 由 `python tools/run.py actions` 从 `tracks` 生成；想要静止的地方在里面加 `holds: [{who, from, to, why}]`（秒，项目本地时间）。

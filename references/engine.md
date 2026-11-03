# 引擎速查（engine/relay.js）

`shots.js` 开头 `import * as R from './engine/relay.js'`，最后 `R.run({ build, setupShot, overlay })`。

- `build()`：开场跑一次，搭场景（可以是很多组，不同镜头显示不同的组）。
- `setupShot(f, sf)`：每帧跑。`f` 是这一帧的全曲帧号；`sf` 是镜头帧（转场时引擎用旧镜头、新镜头各渲一次，`R.shotOf(sf)` 告诉你是哪个镜头）。在这里摆机位、灯、角色、特效。返回值可选：`{ focus, band, hblur, veilColor, veilOp, hideCaption, grade }`（移轴清晰带高度 0 底~1 顶、带宽、横向动态模糊像素、整屏蒙色和不透明度、这帧不出字幕、叠加在段落色调上的镜头内调色，字段同 plan-format.md「grade」）。
- `overlay(f)`：在最上层 2D 画布 `R.fxc` 上画东西（闪光、遮罩、自定义转场）。
- 确定性：同一个 `f` 永远画同一帧。不用 `Math.random()`、`Date.now()`、跨帧累积的状态；随机用 `R.hash(n)`。

## 写一个镜头

```js
function setupShot(f, sf) {
  const t = f / FPS, shot = R.shotOf(sf);
  hideAllGroups();
  switch (shot.id) {
    case 'S03': {
      town.visible = true;
      R.setSky(0x2a3566, 20, 90);                 // 天空颜色、雾近、雾远
      R.keyAt(0, 0, 0, 0xffe2c0, 2.0);            // 主光对准哪里、颜色、亮度
      R.hemi.intensity = 0.9;                     // 环境光
      const k = (f - shot.f0) / (shot.f1 - shot.f0);
      R.look(lerp(-1, 1, k), 1.6, 9, 0, 1.1, 0);  // 机位 (x,y,z) 看向 (x,y,z)；镜头最好一直在动
      R.play('claude', f, -0.8, 0, 0);            // 按动作轨摆角色，你只给脚底位置
      R.play('deepseek', f, 0.8, 0, 0, { flip: true });
      return { focus: 0.55 };
    }
  }
}
```

角色选项（`play` 和 `pose` 一样）：`flip` 朝左、`lean` 倾斜（弧度）、`hop` 跳起高度、`tint` 调色 `[r,g,b]`、`scale` 缩放（要登记进 `plan.json` 的 `sizes`）、`bob` 每拍下蹲摆动的强度（默认 1）、`shadow` 影子、`snap` 贴地（默认开；飞在空中、坐在会动的东西上时关掉）、`opacity`、`onTop` 画在最前面。

## 函数表

| 名字 | 用途 |
|---|---|
| `R.look(px,py,pz, tx,ty,tz)`、`R.camera` | 摆机位；`R.camera.fov` 改焦距 |
| `R.setSky(颜色, 雾近, 雾远, 顶色?, 顶色比例?)`、`R.keyAt(x,y,z, 颜色, 亮度)`、`R.hemi`、`R.key` | 天空、主光、环境光 |
| `plan.json` 的 `grade`、`R.gradeAt(f)`、`R.GRADE0` | 后期调色：段落色调关键帧（见 plan-format.md「grade」）、某一帧算出来的调色参数、中性值 |
| `R.box(父, 宽,高,深, 颜色, x,y,z, {emissive, ei, opacity, cast})` | 一个方块，(x,y,z) 是底面中心 |
| `R.rbox(…同上, {r})` | 圆角方块（近处大件用） |
| `R.instanced(父, 数量, 颜色, {emissive, opacity})` + `R.setInst(im, i, x,y,z, sx,sy,sz, rx,ry,rz)` | 大量方块（地砖、草、雨、粒子），改完 `im.instanceMatrix.needsUpdate = true`。**没用到的槽位要藏掉**（`setInst` 到 y=-80、缩放 0），它们默认停在原点；用过 `setColorAt` 的 InstancedMesh，没设色的槽位是黑的，会渲染成黑方块（V6 死黑） |
| `R.addGround(组)` | 登记会站人的地面（贴地、防穿模、体素关 V2 都靠它） |
| `R.groundAt(x, y, z)` | 查这里的地面高度 |
| `R.play(名字, f, x,y,z, 选项)` | 按动作轨摆角色；这一帧轨里没她就隐藏，返回 false |
| `R.actAt(名字, f)` | 查这一帧的动作和帧序 `{act, idx, mode}` |
| `R.pose(R.chars.名字, 动作, 帧序, x,y,z, 选项)` | 不按动作轨，手动摆（帧序从 0 数） |
| `R.loopIdx(角色, 动作, t)`、`R.onceIdx(角色, 动作, f, f0, f1)`、`R.ping(t, a, b)` | 踩拍取帧：循环一拍一姿势、一次性动作最后一帧落在 f1、两帧每拍来回 |
| `R.placeOnScreen(角色, 动作, 帧序, 中线x像素, 脚底y像素, 身高占比)`、`R.placeHead(…)` | 按屏幕位置摆角色 |
| `R.chars`、`R.H`、`R.plan()`、`R.shotOf(sf)` | 角色表、标准身高（2）、plan.json、当前镜头 |
| `R.makeRain(数量, 颜色)` → `.at(t, cx, cz, 雨量0~1)` | 方块雨 |
| `R.makeBurst(数量, 发光色)` → `.at(f, 爆开帧, x,y,z, 散开, 向上速度, i => 颜色)` | 爆开的方块粒子（1.6 秒） |
| `R.fxc`、`R.drawGlyph(符号, x, y, 格子大小, 透明度, t)` | 最上层 2D 画布、手动画表情符号 |
| `clamp lerp smooth easeIO easeOut hash pulse beatOf beatFrame` | 小工具；`beatOf(t)` 小数拍位，`beatFrame(n)` 第 n 拍的帧号 |
| `props.js`：`makePuzzle()`、`makeFireworks(槽数)` | 发光拼图、方块烟花（接力 MV 的共用道具） |

## 动作轨（plan.json 的 tracks）

每个角色一串，按时间排：

```
["loop", 动作, f0, null, {from, to}?]   循环，一拍一姿势（走一拍一步、跑一拍两步）
["once", 动作, f0, f1, {rev, from, to}?] 一次性：前半段停在第一帧蓄力，后半段快速做完，最后一帧落在 f1（放在拍上）；之后自动在最后两帧每拍来回
["ping", 动作, f0, null, a, b]           停住，a/b 两帧每拍来回（从 0 数）
["hold", 动作, f0, null, i]              定在第 i 帧（配合每拍下蹲摆动，不会定格）
["off", f0]                              不出场
["dance", 舞句, f0, null, {mirror, canon, speed, size}?]   跳一句舞（编舞层），从 f0 那一拍起一拍一步、循环到下一条
```

**dance（编舞层）**：舞句在 `engine/moves.json`（和 `plan.json` 的 `moves`，同名覆盖）。每句是一串步，一步一拍，字段：`a` 动作（`@clap` 这种是槽位，按 `slots` 的顺序取角色有的第一个动作）、`i` 帧序（负数从末尾数）、`i2` 后半拍换成这一帧、`dx`/`dz` 相对站位的偏移（身高的倍数，这一拍前 40% 滑过去）、`hop` 跳起高度（身高的倍数，拍上起跳、下一拍落地）、`lean` 倾斜（弧度）、`turn` 立牌翻面转身（之后一直朝反方向，直到下一个 turn）、`spin` 原地转一圈、`sq` 重拍下蹲。条目选项：`mirror` 镜像（朝向、左右位移、倾斜反过来，多人对称）、`canon` 晚几拍开始（小数也行，0.5 = 晚半拍，波浪）、`speed` 0.5 半速 / 2 倍速、`size` 位移、跳、倾斜的幅度倍数（最后一遍副歌 1.2）。`R.play` 照常调，位移、跳、倾斜、翻面叠加在你给的站位和选项上；`R.actAt` 返回的 `fx` 里有这一帧的偏移，镜头想跟着舞走可以读它。舞句里用 `walk_side` 走路的步（横移滑步）每拍走 0.4 身高，体素关 V3 照样量。`python tools/run.py choreo` 按段落表出草稿，见 SKILL.md「编舞」。

f1 用 `beatFrame(n)` 算。改了 tracks 跑 `python tools/run.py actions`。轨里没出现、但镜头里要用的动作写进 `extra_actions`（只加载用得到的动作，七个人同框时显存才够）。

新舞步（可选，参考精灵图另外生成的帧动画）：`dance_arms dance_clap dance_pose dance_hip`（4 帧），有了槽位会优先用。deepseek 自带直播用的 `stream_clap stream_dance_hands stream_dance_step stream_bounce`，槽位也会用上。

角色动作（标准 18 个）：`walk_side run_side`（8 帧）、`walk_front walk_back turn_back pick_up sit_idle hug_knees look_up reach_out cry pray hold_look bow idle wave_bye laugh sleep`（4 帧）。侧面动作素材朝右，朝左用 `flip`。库里没有的双人动作（摸头、递东西、牵手）用两人的单人帧拼：一人 `reach_out` + 另一人 `idle`，加位移、倾斜、道具移动。

## 碰撞（默认开，不用写任何代码）

角色是一根竖直圆柱（半径：各角色 frames.json 的 `foot_r` 碰家具 / `body_r` 碰角色，`python tools/run.py actions` 会从站立帧量好写进去，量不出按 0.3 / 0.45）。建完场景，`scene` 根下每个直接子 Group 自动是一件家具的碰撞体（单边 > 6 的大件——房子、整个场景容器——下钻成一件件家具；手工 `R.collider` 登记的按整件算、不下钻）；实例化、透明、关深度测试的网格不算实体（和体素关的判定一致）。**地面不是障碍**：真实项目习惯把整个场景容器 `addGround`，所以地面也参与收集，但归类成 `low`（顶面 ≤ 脚底 + 25% 身高）的碰撞体只给贴地用、从不推人；真不想让某件家具参与，用 `R.noBlock` 或 `R.collider(obj, { kind: 'ground' })`。镜头摆好后统一解算：站进家具会被推开，推完重新贴地。

**自动分类**（相对角色脚底 y0、身高 2.0）：顶面 ≤ 0.5 不推（矮凳、台阶，可以踩）；底面 ≥ 2.3 忽略；底面在 1.4–2.3 推开并记「头顶太低」；其余推开。布景照 STYLE.md 的比例表定高度就都不会触发。

**手工 API（全部可选）**：

```js
R.collider(obj, { kind: 'seat', shape: 'cyl', pad: 0.1 })   // 手动覆盖一件家具的形状 / 类别 / 外扩
R.noBlock(obj)                    // 整棵子树不参与碰撞（巨手要盖住角色、剧情要穿过）
R.mark('S02/石桌.北凳', x, z, { face: 0, sit: 0.44 })       // 站位/座位锚点；带 sit 会自动预留位置
R.spot('S02/石桌.北凳')           // → {x, z, face, sit}
R.reserve(x, z, r)                // 预留区域（撒东西、站位都避开）
R.scatter(n, (i, x, z) => {...}, { area: [x0, z0, x1, z1] })  // 随机撒树石，避开预留区和碰撞体（地面这类 low 能踩，不算障碍），逐帧一致
R.collideCollect()                // 镜头中途加了大件家具后手动重收一遍（换镜头会自动收）
```

登记时机不用管：`shots.js` 在模块顶层就把场景搭完的项目，`R.collider` / `R.noBlock` 会比 `collide.init` 先跑——那时还没有 scene，登记照做、收碰撞体留到 init 和换镜头时补，不会炸。

**单帧选项**（写在这帧的 `R.play(..., o)` 里）：`touch: 'S05/书案'` 靠扶趴桌（只推到贴边）、`touchIgnore: ['id']` 忽略某件、`collide: false` 故意穿过（幽灵、穿墙特效；引擎不再推它，也不会因此报 STUCK）。拥抱、牵手这两个人不互推：`plan.json` 的 `"touch": [{"a": "甲", "b": "乙", "f0": 帧号, "f1": 帧号}]`。

**坐着**：用 `sit_*` 动作且离座位中心 ≤ 0.3 时不被推（座位用 `kind: 'seat'` 登记或 `R.mark` 带 `sit`）；`onTop`（交接定位、站上桌面）不参与碰撞。船、移动平台：平台 `addGround`（还是贴地用的地面），篷和桅杆照常是碰撞体。

**配置**（plan.json，不写就全按默认）：`"collide": {"pad": 0.05, "prefer": "short", "charGap": 0.1, "off": ["S01"]}`——`prefer` 推开方向优先级（`short` 最短路径 / `away` 远离镜头），`off` 列出关掉碰撞的镜头 id。

**结果去哪看**：每帧 `window.NUDGES`（谁被谁推了多少，带 `f` / `from` / `to` / `by` / `dist`）和 `window.STUCK`（推不开的：`reason` 头顶太低 / 推开太远 / 推不开，`hint` 是改法建议），`window.voxelProbe(t)` 的返回里也带这两个数组（还有 `colliders`：当帧碰撞体的 id / kind / 形状 / AABB，`check --layout` 的俯视布局图——灰块碰撞体、彩点角色、绿箭头推挤、红圈推不开——读的就是它们）；推开后贴着家具 0.3 以内的遮挡算 `legit`，体素关不算它穿模。结果只由当帧位置决定：单独渲一帧和分块并行渲，位置一致。推不开要不要豁免见 `references/plan-format.md` 的 `allow`。

## 转场（plan.json 的 cuts、incamera）

`cuts` 每条 `{c, len, mode, from, to, note, glowAmt?, center?, grid?, color?, dir?, match?}`：`c` 是关键帧（新镜头第一帧，放在拍上，也必须正好是场景边界——转场两边按 c−1/c 取景，挪离边界两面就成同一个场景了），`len` 总帧数（前后各一半）。`center` 圆心/透视中心（默认画面中央，iris 可以对准角色的屏幕位置）、`grid` 方块密度、`color` 转场色、`dir` 方向 ±1、`match: {a:[u,v], b:[u,v]}` 形状匹配的两个屏幕位置（0~1，原点左下：a 是形状在旧画面的位置、b 是它在新画面的位置）。`mode` 19 种，按轻重分两档——炸点/drop 上必须用重的，轻的会被音乐能量抹掉（转场关 T5 必过）：

| mode | 画面 | 轻/重 |
|---|---|---|
| `rain` | 方块雨落进新画面 | 重 |
| `crumble` | 旧画面碎成方块崩塌 | 重 |
| `voxel` | 体素化光爆（`glowAmt` 加光） | 重 |
| `through` | 穿梭推进（径向模糊冲进新画面） | 重 |
| `pullback` | 拉远揭出新画面 | 重 |
| `whip` / `whip_up` | 甩镜横移 / 甩镜上摇 | 重 |
| `zoom_out` | 拉穿：冲进 `center` 一个黑点，再从里面拉出新画面（比 through 更重） | 重 |
| `flash` | 闪白/闪黑（`color`，默认白） | 重 |
| `occlude` | 一块色板从 `dir` 侧扫过换画面（`color`，默认深板） | 重 |
| `glitch` | 故障：RGB 分离 + 行块错位里换画面 | 重 |
| `spin` | 旧画面转着放大出画、新的转着缩小进画（`dir` 转向、`center` 旋转中心） | 重 |
| `match` | 形状匹配：画面按 `match` 从 a 滑到 b 交叉溶解，匹配的形状在屏上不动 | 重 |
| `rows` | 横条滑移 | 轻 |
| `split` | 旧画面左右两半往 `dir` 两边滑开，露出新画面 | 轻 |
| `iris` | 圈入圈出（`dir`=+1 新画面从 `center` 长出来 / −1 旧画面收进圆里） | 轻 |
| `leak` | 光晕从 `dir` 角漫进来换画面（`color`，默认暖黄） | 轻 |
| `dip` | 落色再起：落进 `color`（默认黑）停一拍再浮出新画面——只放前奏/尾奏/桥段（T7） | 轻 |

引擎把前后两个镜头各渲一张再用着色器混合，并自动登记到 `window.TRANSITIONS`（每条带 `kind`、引擎模式名 `mv`、方向 `dir`，转场关的轻重和方向检查读它们）。全片同一种重的别连用（T6 警告）；方向性转场（甩镜/分屏/遮挡/光晕）的扫向要和下一镜头的横移同向（T8 警告）。

自己画的转场（在 `overlay` 里画遮罩、闪光、形状匹配……）：`mode` 写 `0`、`kind` 按运动方式写（`flash dip leak voxel glitch wipe iris slide whip through match dissolve rotate other`），引擎只登记不混合，画面由你画；`kind` 也要按上表认轻重——手画的溶解登记成 `dissolve` 就是轻的，放在炸点上 T5 会拦。镜头里的大变化（整片天换色、灯全亮）写进 `incamera`：`{shot, f0, f1, key, note}`。

## 运镜（plan.json 的 camera 轨、setupShot 里的 R.cam.*）

两种写法，可以混用，都叠在 setupShot 用 `R.look` 摆好的基础机位上：

- **声明式**：`plan.json` 的 `camera: [{f0, f1, move, …}]`。`move`：`dolly`（推拉，`amt` 世界单位）、`truck`（横移）、`crane`（升降）、`pan`（摇，`deg`）、`tilt`（俯仰，`deg`）、`orbit`（环绕，`from`/`to` 度数，绕看向点转）、`zoom`（变焦，`to` 目标 fov 或 `amt` 变化量）、`dollyzoom`（推近同时变焦）、`roll`（滚转，`deg`）、`follow`（跟角色：`who`、`offset` 默认 [0,1.2,3.5]、`look` 默认 [0,1.3,0]）、`punch`（打点冲击：fov 短促缩一下再弹回，默认 `on: "hit"` 锁到重击点，`amt`、`shake`）、`handheld`（手持感，`amt`）、`bob`（呼吸起伏，`amt`）。可选 `ease: linear/easeIO/easeIn/easeOut/back/expo`、`on: beat/bar/hit`（把进度锁到节拍网格，一格一格走）、`shot`（只对某个镜头生效）、`why`（给自己看）。
- **命令式**：setupShot 里 `R.cam.dolly({amt: 0.5})` 这类，只对这一帧生效（要连续就在自己的代码里逐帧给参数）。

什么都不写（没有 camera 轨、也不调 R.cam）：相机一个字段都不动，画面和没有运镜库时逐帧一致。运镜是工具不是默认值。

每帧的机位、看向点、fov、用到的运镜种类、实际运动速度记进 `window.CAMLOG`（`window.voxelProbe(t)` 的返回带 `cam` 字段，探针导出到 `out/voxel.json`，运镜关 K1–K6 读它）。安全线在引擎运行时夹（K6，夹了什么记在 `fixed` 里、报告列成「已自动修」）：环绕 ±50°（过半圈立牌会穿帮）、最终俯仰 ±50°、tilt ±35°、fov [16,50]、推近不超过基础距离的一半、手持 ≤0.06、punch ≤0.3、呼吸 ≤0.04、滚转 ±8°。起草用 `python tools/run.py camplan`（见 STYLE「运镜跟着段落走」）。

## 表情符号（plan.json 的 emotes）

`{who, g, f0, f1, dx}`：f0 弹出（放在拍上，V7）、f1 消失，`dx` 左右偏移（身高的倍数）。可用：heart 爱心、heartbreak 心碎、star 星星、sparkle 闪光、exclaim 感叹号、question 问号、note 音符、cloud 乌云、sweat 汗滴、tear 泪滴、dots 省略号、zzz、idea 灯泡、anger 怒、dizzy 晕、flower 小花。新符号按 `GLYPH` 里的格子写法加。

## 页面契约（引擎已经实现，改引擎时保留）

`window.DUR`、`window.render(t)`、`window.READY`、`window.probe(t)`（动作关用的关键点）、`window.TRANSITIONS`（转场表）、`window.voxelProbe(t)`（体素关用：世界身高、贴地、鞋底遮挡、像素高、坏帧、后期参数、可见方块数、碰撞体 / 推挤 / 推不开，外加运镜档 `cam`；置 `window.LAYOUT = 1` 再导出会带 `colliders` 布局图数据）、`window.probeAll(t)`（一次摆场景同时给 probe 和 voxelProbe 的结果，`tools/probe_all.mjs` 并行探针用；老引擎没有它就分别调）、`window.PLACEHOLDER`。边做边看用 `python tools/run.py preview`（带进度条、逐帧、循环、自动刷新、检查结果跳转）；直接打开 `index.html` 也是带音乐的简易预览，`?f=帧号` 停在某一帧。每帧结果只由帧号决定（运镜速度要上一帧，分段时先空跑前两帧），所以渲染和探针都能分段并行。

## 引擎分发（项目里的 engine/ 不准改）

引擎的源头是 skill 的 `kit/engine/`；建项目时整份拷到 `<项目>/engine/`，并写 `engine/ENGINE_VERSION`（skill 版本号 + 每个文件的 sha256 + skill 路径）。规则：

- 项目里发现画面不对，**不要改 `engine/`**：先跑 `python tools/run.py check`，它会对比哈希、警告被改过的文件；确认是引擎的问题就改 skill 的 `kit/engine/`，再回项目跑 `python tools/run.py upgrade-engine`。
- `upgrade-engine` 会先把现在的引擎整份备份到 `engine_bak/<时间>/`，再覆盖、重写 `ENGINE_VERSION`，并打印这次换掉了哪些文件；`--skill` 可以指定 skill 目录（默认用 ENGINE_VERSION 里记的路径）。
- 老项目（没有 ENGINE_VERSION）第一次跑 `upgrade-engine` 就接入这套管理，之后 `check` / `video` 的预检都会自动核对哈希（只警告，不拦渲染）。

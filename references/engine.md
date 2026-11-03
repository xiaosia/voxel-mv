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
```

f1 用 `beatFrame(n)` 算。改了 tracks 跑 `python tools/run.py actions`。轨里没出现、但镜头里要用的动作写进 `extra_actions`（只加载用得到的动作，七个人同框时显存才够）。

角色动作（sprite-frames 的 18 个）：`walk_side run_side`（8 帧）、`walk_front walk_back turn_back pick_up sit_idle hug_knees look_up reach_out cry pray hold_look bow idle wave_bye laugh sleep`（4 帧）。侧面动作素材朝右，朝左用 `flip`。库里没有的双人动作（摸头、递东西、牵手）用两人的单人帧拼：一人 `reach_out` + 另一人 `idle`，加位移、倾斜、道具移动。

## 转场（plan.json 的 cuts、incamera）

`cuts` 每条 `{c, len, mode, from, to, note, glowAmt?, center?, grid?}`：`c` 是关键帧（新镜头第一帧，放在拍上），`len` 总帧数（前后各一半）。`mode`：`rain` 方块雨落、`crumble` 碎裂崩塌、`voxel` 体素化（`glowAmt` 加光）、`rows` 横条滑移、`through` 穿梭推进、`pullback` 拉远、`whip` 甩镜横移、`whip_up` 甩镜上摇。引擎把前后两个镜头各渲一张再用着色器混合，并自动登记到 `window.TRANSITIONS`。

自己画的转场（在 `overlay` 里画遮罩、闪光、形状匹配……）：`mode` 写 `0`、`kind` 按运动方式写（`flash wipe iris slide whip through match dissolve rotate other`），引擎只登记不混合，画面由你画。镜头里的大变化（整片天换色、灯全亮）写进 `incamera`：`{shot, f0, f1, key, note}`。

## 表情符号（plan.json 的 emotes）

`{who, g, f0, f1, dx}`：f0 弹出（放在拍上，V7）、f1 消失，`dx` 左右偏移（身高的倍数）。可用：heart 爱心、heartbreak 心碎、star 星星、sparkle 闪光、exclaim 感叹号、question 问号、note 音符、cloud 乌云、sweat 汗滴、tear 泪滴、dots 省略号、zzz、idea 灯泡、anger 怒、dizzy 晕、flower 小花。新符号按 `GLYPH` 里的格子写法加。

## 页面契约（引擎已经实现，改引擎时保留）

`window.DUR`、`window.render(t)`、`window.READY`、`window.probe(t)`（动作关用的关键点）、`window.TRANSITIONS`（转场表）、`window.voxelProbe(t)`（体素关用：世界身高、贴地、鞋底遮挡、像素高、坏帧、后期参数、可见方块数）、`window.PLACEHOLDER`。浏览器里直接打开 `index.html`（`python -m http.server`）是带音乐的实时预览，`?f=帧号` 停在某一帧。

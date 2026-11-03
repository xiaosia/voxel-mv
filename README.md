# voxel-mv：一首歌 → 方块体素 3D 动画 MV

**源码公开 · 非商业使用。** 自有代码采用 PolyForm Noncommercial 1.0.0，自有技能文档采用 CC BY-NC-SA 4.0。商业接单、广告、带货和以商业收益为目的的视频制作不在一般非商业授权范围内；标准许可中的明确允许用途仍然有效。第三方组件保留原许可，权属未核实的角色、图片和歌词不因放入仓库而获得新授权。详见 [中文许可说明](LICENSE.zh-CN.md)、[许可范围](LICENSE) 和 [第三方与素材清单](THIRD_PARTY_NOTICES.md)。

把一首歌交给 AI，做成一支「摆在桌上的体素微缩世界」MV：three.js 实时渲染的方块小镇、房间、海底或一张唱片，精灵图帧动画角色做成立牌站在里面，跟着拍子走、跳、做表情。画面是哑光圆角方块、柔和棚拍光、浅景深和移轴，像手办模型拍的小电影。

![《雨爱》成片接触表](examples/yuai/preview/sheet.jpg)

## 做出来是什么样

- **世界**：体素微缩场景，10–20 秒换一个（同一地点的白天和夜里算两个场景）。前奏和主歌收着，副歌放开，桥段换世界或换视角，drop 是全片最大的场面，结尾收回来。
- **角色**：内置 7 个帧动画角色（claude、deepseek、gemini、gpt、kimi、qwen、zai），全片统一身高、脚底贴地、朝向镜头；走路按拍位移，表情用方块符号拼出来，都踩在拍上。
- **声音和字幕**：成片带原曲；歌词字幕自动出，普通 LRC 和逐字 LRC 都支持；转场、表情和特效落在拍点、小节线或 hit 上。
- **交付**：1920×1080 / 24 fps 的 `mv.mp4`，外加接触表、逐句帧条、检查报告和源码包。

## 小白怎么用

1. **把整个 `voxel-mv` 文件夹给 AI**（Claude Code、Codex 这类能在你电脑上跑命令的 AI），`characters/` 里的帧图也要在。
2. **准备歌**：一个音频文件（mp3 / wav 都行），文件名最好是「歌手 - 歌名.mp3」。节拍和歌词都不用自己做：节拍会自动分析，歌词会先上网查字，再听歌把每句对到这首歌上。手上有歌词文字（网易云 / QQ 音乐复制的纯文本就行）就一起给，最准。
3. **对 AI 说一句话**，比如：

> 读 `voxel-mv/SKILL.md`，按里面的流程把 `D:\歌\寂寞烟火.mp3`（歌词 `D:\歌\寂寞烟火.lrc`）做成 MV，角色用 claude 和 deepseek。

角色可以不指定，AI 会按歌挑。AI 写完构思（TREATMENT）会停下来给你看一次；不想看就加一句「中间不用问我，直接做完」。只想先试试，就说「先做前 30 秒」。

几个常用说法：

- 「整首放在同一个世界里」——不换地点，靠时间、光色和镜头内的变化推进（场景表照样按 10–20 秒切）。
- 「按照这首歌的感觉自由发挥」——打开自由模式。所有检查照跑、照出报告；必过清单（11 条）两种模式都拦，`MODE` 只影响报告措辞。
- 「这首太长了，拆成两段做」——AI 会按段落切开、分别渲染，最后拼回整首。

画面上的小改动也可以直接说，比如「字幕换成米黄色、再靠下一点」「副歌主色换成青色」「转场别用甩镜」「最后一个镜头多停两拍」。AI 会去改对应的 `plan.json`、`shots.js` 或 `index.html`，再只重渲受影响的场景。

## 电脑上要装的

Windows、macOS、Linux 都能跑。需要 Node.js 20 以上、ffmpeg、Python 3（再 `pip install numpy pillow`）、Chrome 或 Edge。可选：`pip install faster-whisper pypinyin "audio-separator[gpu]"`（把歌词对到这首歌上；audio-separator 先分离人声，准很多，装不上就装 demucs）。不用自己检查：AI 第一步会跑 `python tools/run.py doctor`，缺什么它会列出来，并给出安装命令。

doctor 最后一行「显卡渲染」如果是 `[慢]`（SwiftShader 之类），说明浏览器没用上显卡，出片会慢好几倍，照它下面的提示改。

## AI 会替你做完这些

1. **建项目**：分析音频，拿到拍点、小节线、hits、drops 和段落；找歌词；把引擎、检查工具和角色拷进项目。
2. **写构思**：想几个差别很大的故事和世界，选最贴歌的一个，写 `TREATMENT.md`：世界、角色、情绪曲线、场景表、关键音乐时刻，以及整首做成一个项目还是拆段。
3. **做风格样张**：先出 2–3 张成片级画面，和 `references/style/` 的参考图并排打分，不过关就改。这几张之后是全片的标准。
4. **排动作、写全片**：按歌词逐句排动作轨，再一个场景一个镜头地写，边写边截图；每加一个转场、每写完一个场景都会跑对应检查。
5. **检查出片**：预检通过后按场景分块渲染，配原曲、生成接触表和逐句帧条，全部检查通过后打包到 `out/交付/`。

## 会检查什么

写镜头时 AI 会随时跑检查，`video` 出片前也会先预检，不过就不渲染。六道关：

- **风格样张**：写全片前先做 2–3 张成片级画面，和 `references/style/` 的参考图并排打分。
- **不定格**：全片不许出现定格（安静段也要有镜头、环境或呼吸在动）。
- **动作**：出镜角色每 2 小节至少一个明显动作，连续静止不超过 4 拍，动作落在拍上。
- **转场**：每次换场都登记、看得出；至少 4 种，关键帧落在拍点或小节线上。
- **体素**：角色等高、贴地、走路不打滑、特写不发糊、不用坏帧；非特写开着移轴，画面里没有大片死黑；表情符号卡在拍上。
- **场景**：10–20 秒一个场景，相邻场景至少换地点或换光色，全片有起承转合。

报告在 `out/` 里，出片时汇总到 `out/交付/<名字>/checks/`。哪关不过，就按报告里的秒数截那一帧去看，别只看分数。常见问题和修法收在 [references/common-problems.md](references/common-problems.md)。

## 它是怎么工作的

- 每个镜头都是 `render(t)` 的确定性函数：同样的秒数永远渲染出同一帧，所以能逐帧截图、能只重渲某一段。
- `plan.json` 管结构：场景、镜头、动作轨、转场、表情；`shots.js` 搭布景、摆角色、给机位。也可以全写在 `shots.js` 里。
- `run.py` 用浏览器逐帧渲染，再交给 ffmpeg 编码；渲染按场景分块存在 `out/chunks/`，改一个场景只重渲那一块。

## 自己动手跑

以下命令都在项目根目录（有 `index.html` 和 `plan.json` 的那层）执行：

```bash
python tools/run.py doctor                 # 检查环境，第一次会装渲染依赖
python tools/run.py preview                # 边做边看：浏览器里带音乐实时播放，改了文件自动刷新（不导出）
python tools/run.py still 0.5 3.2 7.06     # 截图 → out/chk/t_<秒>.jpg
python tools/run.py frame 120 340          # 按帧号截图
python tools/run.py style 3.2 11 20        # 和参考图并排 → out/style_compare.jpg
python tools/run.py actions                # 按 plan.json 生成 ACTIONS.json
python tools/run.py act                    # 动作关 + 接触图
python tools/run.py trans                  # 转场关
python tools/run.py voxel                  # 体素关
python tools/run.py scenes                 # 场景关
python tools/run.py grade                  # 调色关（色调跟着段落起伏）
python tools/run.py draft                  # 每秒 12 帧的草稿，看整体节奏
python tools/run.py video                  # 预检 → 分块渲染 → 检查 → 打包
python tools/run.py video --redo C,D       # 只重渲 C、D 两个场景（也可以写 12-30）
```

想在浏览器里边听边看：在项目根目录跑 `python -m http.server 8000`，打开 `http://localhost:8000/`。不带 `?export=1` 时是带音乐的预览循环，适合快速看节奏。

建项目在技能根目录执行：

```bash
python scripts/new_project.py my_mv --audio song.mp3 --lrc lyrics.lrc --cast claude,deepseek
```

常用参数：`--title` / `--artist` 指定歌名歌手，`--seconds 30` 只做前 30 秒试手，`--from 90 --seconds 60` 只做中间某一段，`--timeline` / `--report` 用现成的节拍数据和结构说明跳过自动分析。

分段做的几个项目，最后在技能根目录拼成整首：

```bash
python scripts/join_segments.py 成片.mp4 --audio 原曲.mp3 段1 段2 段3
```

## 定制清单：想改什么，改哪里

画风是定死的（见 [STYLE.md](STYLE.md)），画风以外基本都能改。大部分定制只动 `plan.json` 和 `shots.js`，不用改引擎：

| 想改 | 改哪里 | 说明 |
|---|---|---|
| 故事、世界、分镜 | `TREATMENT.md` + `shots.js` | 先定场景表和情绪曲线，再写镜头。世界可以是一张唱片、一间教室、海底或太空。 |
| 角色阵容 | 建项目时 `--cast`；之后 `plan.json` 的 `cast` | 只加载出场角色，人越多越慢。内置 7 个；加新角色见 [characters/README.md](characters/README.md)。 |
| 故意不等高（巨人、倒影） | `plan.json` 的 `sizes` | 写 `{名字: {scale, why}}`，体素关 V1 就不按 3% 卡。 |
| 动作和走位 | `plan.json` 的 `tracks` → `run.py actions` | 动作轨按拍排；真的静止写进 `ACTIONS.json` 的 `holds`；原地踏步、故意藏脚写进 `plan.json` 的 `treadmill` / `occlude`。 |
| 表情符号 | `plan.json` 的 `emotes` | 16 种方块符号（爱心、星星、问号、音符、乌云、汗滴……），`f0` 必须卡拍（V7）；新符号在引擎的 `GLYPH` 里加。 |
| 场景划分 | `plan.json` 的 `scenes` | 10–20 秒一个；快剪蒙太奇写 `why`，首尾呼应写 `same_as`。 |
| 转场 | `plan.json` 的 `cuts` / `incamera` | 8 种引擎转场（方块雨、碎裂、体素化、横条、穿梭、拉远、两种甩镜）；`mode: 0` 可以自己画，或做拍点硬切；镜头内的大变化（天亮、全城亮灯）写 `incamera`。 |
| 光色、天空、雾 | `shots.js` 里的 `R.setSky`、灯光和材质 | 每个场景一套光色，相邻场景至少换地点或换光色。 |
| 每段的色调（明暗、冷暖、浓淡） | `plan.json` 的 `grade` | 引擎后期对整帧调色，角色和场景一起变，字幕不受影响；按段落写关键帧，见 [references/plan-format.md](references/plan-format.md)「grade」。 |
| 移轴、景深、泛光、暗角 | `setupShot` 返回的 `focus`、`band`、`hblur` | `focus` 是清晰带中心的高度（0 底、1 顶），`band` 是清晰带半宽，越小景深越浅；后期参数在引擎里。 |
| 字幕 | 项目 `index.html` 的 `#cap` | 字体、字号、颜色、描边、位置都能改；字高要 ≥ 画面高 4.5%（≥49px），任何背景上都看得清。 |
| 歌词 | `data/lyrics.lrc`（自动找的原始文件在 `data/analysis/lyrics.lrc`） | 改完用 `new_project.py --lrc` 重新生成字幕；直接改 `assets/lyrics.json` 会在重建时被覆盖。 |
| 片名和署名 | `shots.js` 的 `overlay` | 只在片头片尾出现；不要用文字解释剧情。 |
| 道具 | `engine/props.js` 或自己用 `R.box` / `R.rbox` 搭 | 现成有发光拼图和方块烟花；一件反复出现的道具比逐句插图更有记忆点。 |
| 歌、拍点、段落 | `data/analysis/` + `scripts/analyze_audio.py` | 换歌基本等于重做；BPM 差一倍用 `--bpm` 重分析；长歌用 `--from` / `--seconds` 切段。 |
| 渲染速度 | `VOXEL_WORKERS`、`draft`、`video --redo` | 并行浏览器 2–6 个；草稿 12fps 看节奏；改一个场景只重渲那一块。 |
| 检查严格度 | 项目根的 `MODE` 写 `free` | 两种模式拦法一样：必过 11 条都拦，`MODE` 只影响报告措辞；其余分「自动修」和「警告」，见 `out/report.md`。 |

### 三个常见定制

- **换一个世界**：在 `build()` 里新建一套布景函数，给场景配一套新光色，`plan.json` 的 `scenes` 换 `world` / `look` 和帧范围；角色、动作轨、检查都不用动。
- **加一个角色**：按 [characters/README.md](characters/README.md) 准备帧图、跑身高校正、登记坏帧，再把名字加进 `--cast` 和 `plan.json` 的 `cast`。
- **自己画转场**：`plan.json` 里写 `{"mode": 0, "kind": "wipe", ...}`，在 `shots.js` 的 `overlay(f)` 里按进度画遮罩或形状匹配；引擎只负责登记，不混合画面。

### 不建议动的

- **输出规格**：1920×1080 / 24 fps 写死在渲染器、着色器和检查里，改分辨率或帧率要同时改引擎和检查脚本，牵一发动全身。
- **画风**：哑光圆角方块、棚拍光、浅景深和移轴是这支 MV 的识别度。可以换世界、换配色，不要换成别的渲染风格。
- **页面契约**：改引擎时保留 `DUR / render / probe / TRANSITIONS / voxelProbe`，截图、导出和检查都靠它们。

接口细节见 [references/engine.md](references/engine.md)（函数表和写法）、[references/plan-format.md](references/plan-format.md)（`plan.json` 每个字段）、[references/relay.md](references/relay.md)（分段和交接）。

## 目录结构

```text
voxel-mv/
  SKILL.md / STYLE.md        流程与检查 / 画风标准
  scripts/                   建项目、分析音频、找歌词、拼接分段
  kit/engine/                引擎：渲染、角色、贴地、踩拍、转场、后期
  kit/tools/                 run.py 和各项检查
  characters/                7 个角色帧动画、身高校正、坏帧表
  references/                引擎速查、plan 格式、分段交接、常见问题、风格参考图
  examples/yuai/             《雨爱》完整源码、预览和检查报告
```

一个建好的项目长这样：

```text
my_mv/
  index.html / shots.js / plan.json / MODE
  engine/ tools/ vendor/     从 kit 拷来的引擎和工具
  data/song.wav              成片音轨
  data/analysis/             拍点、段落、歌词、分析报告
  assets/                    项目用到的角色帧图
  out/                       截图、草稿、分块渲染、检查报告、交付包
```

## 常见问题

- **出片慢**：先看 `out/timing.md`。`run.py doctor` 里「显卡渲染」是 `[慢]`（SwiftShader 之类）就照提示开显卡；检查没过时用 `video --redo <场景>`；只想调节奏用 `draft`。
- **歌词不对**：自动找的歌词可能是别的版本，改 `data/lyrics.lrc`（自动找的原始文件在 `data/analysis/lyrics.lrc`），再用 `new_project.py --lrc` 重建项目。
- **BPM 明显不对**（速度差一倍）：用 `scripts/analyze_audio.py song.mp3 --bpm 大概的值 --out 项目/data/analysis` 重分析，再用 `--timeline` 重建。
- **长歌**：3 分钟以上、段落多时通常拆成 30–60 秒一段分别做，每段照样 10–20 秒一个场景，最后 `join_segments.py` 拼接。
- **检查不过**：报告会写清是哪一关、哪一帧；按秒数截图看，再去 [common-problems.md](references/common-problems.md) 找对应修法。

## 完整示例

[《雨爱》44 秒 MV](examples/yuai/README.md)：4 个场景、8 个镜头，Claude 和 DeepSeek 在一张会下雨的黑胶唱片上走完「等—遇见—一起跳—黎明」。目录里有成片接触表、逐句帧条、原始提示词、源码、检查报告和风格迭代记录；`prepare.py` 会用内置角色和你的音频把整片重新渲染出来。

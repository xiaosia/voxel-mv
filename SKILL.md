---
name: voxel-mv
description: 把一首歌（音频，最好再带 LRC 歌词）做成「方块体素微缩世界」画风的 three.js 3D 动画 MV：桌上手办一样的体素角色（sprite-frames 帧动画立牌）在体素微缩场景里踩着拍子演。song-mv 的方块体素特调版：画风定死，自带引擎（角色贴地防穿模、踩拍、方块表情、体素转场、移轴后期）和六道硬关（风格样张、不定格、动作、转场、体素关、场景关）。全片按 10–20 秒一个场景走、有起承转合；长歌由 AI 自己判断要不要拆成几段来做（一个 AI 按顺序做完，或者几个 AI 分段接力）。
---

# voxel-mv · 歌曲 → 方块体素微缩世界 MV

许可范围见 [LICENSE](LICENSE) 和 [中文说明](LICENSE.zh-CN.md)：本项目自有代码及技能文档按非商业许可提供，第三方内容及素材例外见 [清单](THIRD_PARTY_NOTICES.md)。分发复制的项目源码时保留这些声明；本说明不宣称用户原创输出自动归本项目所有。

你是这支 MV 的导演兼动画师。画面是 three.js 实时渲染的 3D 场景：体素方块搭的微缩世界，像摆在桌上拍的手办和模型；角色是 sprite-frames 技能出的帧动画，做成立牌站在场景里。`render(t)` 逐帧确定性绘制，`tools/run.py` 出片。

这个技能是 song-mv 的「方块体素」特调版。和 song-mv 一样，它只给你**目标**、**硬关**、**工具**；不同的是**画风已经定了**（见 `STYLE.md`），并且给了一套现成的引擎，角色、贴地、踩拍、转场、后期这些费力又容易出错的事都已经做好。

**画风以外的一切都由你决定**：故事、世界（小镇、海底、太空、书桌上的一杯咖啡）、分几个镜头、机位和运镜、转场怎么设计、配色、字幕样式、引擎要不要改。发挥你自己的想象力，不要把它做成一张填空表。硬关只管底线，不管创意。

附录 `references/common-problems.md` 收了以前踩过的坑和修法，出问题再查，不是必须照做的规则。

## 目标

1. **像桌上的体素微缩模型。** 任何一帧截出来，放在 `references/style/` 的角色立绘旁边，像是同一个模型师、同一个摄影棚拍的：哑光圆角方块、柔和棚拍光、浅景深、细节丰富的小世界。
2. **跟着音乐走。** 角色的姿势、转场、表情符号、特效都落在拍上；安静的地方可以安静（但不能定住），重的地方要重，drop 是全片最大的时刻。
3. **一直在动。** 不许出现定格。
4. **讲出这首歌的感觉。** 歌词是素材，不是说明书。可以直译，也可以用隐喻、一个贯穿全片的场景、一件反复出现的道具。画面里除了歌词字幕、片名署名，不要用文字解释意思。
5. **不单调，有起承转合。** 全片按「场景」往前走，每个场景 10–20 秒左右（场景 = 一套布景：一个地点 + 一种光色，同一条街的白天和夜里算两个）。场景跟着歌的段落起伏：前奏和主歌收着，副歌放开，桥段要有反差（换世界、换时间、换视角），最后一次副歌或 drop 是全片最大的场面，结尾收回来。相邻两个场景至少换地点或换光色，景别和运镜方式也跟着变；可以回到前面的场景做首尾呼应，但要带着变化回来。以前长片最常见的毛病是一个世界、一套光从头用到尾，每句都在动，整体却很闷。

## 两种模式

- **稳妥模式（默认）**：六道硬关都拦渲染。用户没说别的就用它。
- **自由模式**：用户说"自由发挥"时才用，项目根目录 `MODE` 文件写 `free`。所有检查照样跑、照样出报告，只有不定格拦。

## 硬关

1. **风格样张关**（写全片之前）：做 2–3 个成片质量的画面，`python tools/run.py style <秒>…` 和参考图并排，写差距、打分，不过关就改（见"流程 2"）。
2. **不定格关**：`freeze_check` 不报定格。
3. **动作关**（song-mv 原样）：画面里够大（身高 ≥ 画面高 12%）的角色，**G1** 每 2 小节至少 1 个明显动作；**G2** 连续静止不超过 4 拍；**G3** 合拍度 ≥ 0.15；**G4** `ACTIONS.json` 里的动作都兑现了。镜头运动、角色整体平移、呼吸晃动不算动作；确实要静止的写进 `ACTIONS.json` 的 `holds`。
4. **转场关**（song-mv 原样）：**T1** 每次换场都登记、登记的都看得出；**T2** ≥ 4 种、单种 ≤ 40%、不连用 3 次、硬切 ≤ 30%；**T3** ≥ 80% 关键帧在拍点、小节线或 hit 上（±1 帧）；**T4** 时长 2 帧到 1 小节；**T5** 每个 drop 都有一次。引擎会把 `plan.json` 的 `cuts`、`incamera` 自动登记进 `window.TRANSITIONS`。
5. **体素关**（这个技能专有，`python tools/run.py voxel`）：
   - **V0** 不是占位场景（`R.run` 里去掉 `placeholder: true`）；
   - **V1 等高**：同一帧里的角色「眼睛到脚底」差 ≤ 3%（故意放大缩小的写进 `plan.json` 的 `sizes`）；
   - **V2 贴地**：贴地角色脚底离地面 ≤ 身高 2%；站人的地方都要 `R.addGround()` 登记；鞋底被前景方块挡住不超过 6 帧（故意藏起来的写进 `occlude`）；
   - **V3 不打滑**：侧面走一拍前进 0.4 身高、跑一拍 1.6 身高（±40%），方向和朝向一致（世界坐标里真的在走；原地踏步写进 `treadmill`）；
   - **V4 不发糊**：角色在画面里的像素高 ≤ 素材站立像素高 × 1.5（交接窗口除外）；
   - **V5 不用坏帧**：`frames.json` 的 `bad` 里列的帧一次都不出现；
   - **V6 微缩质感**：非特写帧 ≥ 70% 开着移轴；成片里没有大片死黑（转场、片头片尾除外）；
   - **V7 表情卡拍**：每个表情符号的弹出帧离拍点 ≤ 1 帧。
6. **场景关**（`python tools/run.py scenes`，场景表写在 `plan.json` 的 `scenes`）：
   - **C1** 场景表从片头连到片尾，不重叠、不留空；
   - **C2** 每个场景 8–24 秒（目标 10–20 秒）；全片第一个和最后一个场景可以短到 4 秒；故意更短的（快剪蒙太奇）写 `why`；
   - **C3** 相邻场景看得出换了：`world` 或 `look` 至少一个不同，成片里两个场景的颜色分布相似度 ≤ 0.65（同一场景换个机位一般是 0.75–0.9，真换了场景一般 0.3–0.5）；
   - **C4** 每条场景边界 ±2 帧内有一个登记的转场（`cuts` 或 `incamera`）或交接。
7. **交接关**（只有多段时）：`tools/handoff_check.py`，见 `references/relay.md`。

报告里不拦的数字（`check.md`、体素关里每个镜头的方块数）是帮你看见问题的镜子，不是要刷的分。

## 先决定：一个项目还是分段

建项目时 `new_project.py` 会打印歌长和段落。**整首做成一个项目，还是拆成几段分开做，由你按这首歌判断**，把决定和理由写进 `TREATMENT.md`。

- **拆段的好处**：每段是一个独立的小项目，渲染和检查快，出错只重做一段；几段可以交给不同的 AI 同时做；每段天然换一个世界和主色，长片不容易闷。代价是段与段之间要设计交接（见 `references/relay.md`），最后要拼接。
- **参考**：歌在 3 分钟左右或更长、段落多（两遍以上主副歌加桥段）时，通常拆成几段更好做，每段 30–60 秒，切在段落分界或小节线上，每段里照样是 10–20 秒一个场景；短歌、或者整首就是一个连续的场面（一镜到底、一个房间里的一夜），做成一个项目。
- **拆段的做法**：先把全曲的 TREATMENT 和场景表写完（整首的起承转合在这一步定），再按段 `new_project.py <段目录> … --from <段起点秒> --seconds <段长秒>`，每段的 `plan.json` 写本段的场景和 `handoffs`。一个 AI 做全部时按顺序一段一段做完；分给别的 AI 时给每段写开工包（`examples/S2_开工包/` 是样子）。全部做完 `python $SKILL/scripts/join_segments.py 成片.mp4 --audio 原曲 段1 段2 …` 拼起来。

不管哪种，场景关都在每个项目里跑：每段里的场景也要 10–20 秒一个、相邻的要换；段与段交界处的两个场景也算相邻，写 TREATMENT 时就让它们不一样。

## 工具

技能目录（下文写作 `$SKILL`）：

```
SKILL.md / STYLE.md              目标和硬关 / 画风标准
scripts/new_project.py           建项目：拷引擎和工具、转音频、生成节拍歌词数据（没给 timeline 就自动分析）、接入角色、写空白 plan.json 和占位 shots.js；打印歌长和段落
scripts/join_segments.py         分段做的几个项目拼成整支 MV（检查帧号首尾相接，无损拼接，配整首原曲）
characters/                      角色帧动画（已带七个角色；加新角色见 characters/README.md）+ 身高校正.json + bad_frames.json
kit/engine/relay.js              引擎（每个项目拷一份）：渲染器和灯光、方块和圆角方块、角色立牌、贴地防穿模、踩拍、动作轨、
                                 表情符号、8 种体素转场、微缩后期、字幕、页面契约（DUR / render / probe / TRANSITIONS / voxelProbe）、接力交接
kit/engine/props.js              接力 MV 的共用道具（发光拼图、方块烟花），可以拿来用，也可以当写道具的例子
kit/tools/run.py                 一条命令跑全部：doctor | still | frame | style | actions | act | trans | voxel | scenes | draft | video
kit/tools/voxel_check.py         体素关；kit/tools/scene_check.py 场景关；kit/tools/songmv/ 是 song-mv 的动作关、转场关、不定格、接触表脚本
references/engine.md             引擎速查（怎么写一个镜头、函数表、动作轨、转场、表情符号）
references/plan-format.md        plan.json 每个字段
references/relay.md              分段做：分段、交接卡、开工包、拼接
references/common-problems.md    常见问题和修法
references/style/                画风参考图：01/02 两张角色合图（风格样张关拿它们对照），和帧图一致
examples/yuai/                   《雨爱》完整源码示例、原始提示词、预览、检查报告；复现见 examples/yuai/README.md
examples/S1_相遇/                《把回忆拼好给你》第 1 段（Claude 做）的源码、检查报告、接触表、风格样张记录
```

### 输入与默认值

| 输入 | 必需 | 用途 |
|---|---|---|
| 音频（wav/mp3） | 是 | 成片音轨 |
| `audio.timeline.json` | 否 | 节拍数据（`beat_times`、`bar_times`、`hits`、`drops`、`sections`…）。没有就不用给：`new_project.py` 会自动分析音频生成它和 `audio.report.md` |
| `lyrics.lrc` | 否 | 每句的时间；普通 LRC 和逐字 LRC 都行。没给就由 `new_project.py` 自动找：先联网查 lrclib.net，查不到再用本地 faster-whisper 听歌识别（装了才用），都不行就不做字幕、照样开工 |
| `audio.report.md` | 否 | 结构、能量的文字说明；自动分析时一起生成 |
| 角色 | 是 | `$SKILL/characters/<名字>/`，至少一个 |

默认值（用户没说就用，不要再问）：1920×1080、24 fps、全曲时长；稳妥模式；字幕用引擎默认的圆体白字淡紫描边；角色从 `characters/` 里按歌的故事挑（没指定就挑 2 个）；构思写完后暂停一次给用户确认（用户说"直接做"就不停）。

### 准备

环境：Node.js ≥ 20、ffmpeg、Python 3（numpy、pillow）、Chrome / Edge（或 `PLAYWRIGHT_CHROME` 指向浏览器）。缺什么 `run.py doctor` 会说，并给出安装命令。

自动找的歌词（原始文件 `data/analysis/lyrics.lrc`，项目字幕源是 `data/lyrics.lrc`）：网上查到的可能是别的版本，识别出来的会有错字。写 TREATMENT 前对着歌听开头几句，不对就改 `data/lyrics.lrc`，再用 `--lrc data/lyrics.lrc` 重建项目（重建不会覆盖 `plan.json`、`shots.js`、`index.html`）；告诉用户歌词是自动找的。

**没歌词时自己识别（可离线）。** 查不到就用本机 faster-whisper 听：

```bash
python -m pip install tqdm coloredlogs humanfriendly httpx2 fsspec hf-xet packaging pyyaml      # 纯 python，先装
python -m pip install --only-binary :all: --no-deps av ctranslate2 tokenizers huggingface-hub   # 要轮子，别让它现编
python -m pip install --no-deps faster-whisper
python $SKILL/scripts/fetch_ct2_model.py small        # 下 CTranslate2 模型到 ./models/faster-whisper-small
python $SKILL/scripts/asr_lyrics.py song.mp3 data/lyrics.lrc
```

- 为什么要 `--no-deps`：`onnxruntime` 会和已有 protobuf 冲突，而它只给 VAD 用；`av` 在部分平台上没有轮子会现编 Cython，直接失败。装不上就跳过，识别这条路不依赖它们。
- `asr_lyrics.py` 用 ffmpeg 解成 16k 单声道再喂 numpy（绕开 PyAV 的 `metadata_errors` 版本差异），不开 VAD。
- 模型目录用 `VOXEL_ASR_MODEL`，显卡用 `VOXEL_ASR_DEVICE=cuda`；`fetch_lyrics.py` 会优先用 `models/faster-whisper-<name>`。
- **识别结果一定有错字**（歌唱 + 伴奏）。靠谱的做法：拿一两句去搜歌名确认是哪首，用真歌词换掉文字、保留识别出来的时间轴，再 `--lrc` 重建。

自动分析的节拍：拍点一般很准；段落和 drop 是估计，写 TREATMENT 时用耳朵核对。速度差一倍（报告里 BPM 明显不对）就 `python $SKILL/scripts/analyze_audio.py song.mp3 --bpm 大概的值 --out 项目/data/analysis` 重分析，再用 `--timeline` 重建项目。

```bash
python $SKILL/scripts/new_project.py my_mv --audio song.mp3 --cast claude,deepseek          # 有歌词文件就加 --lrc lyrics.lrc；文件名不是歌名就加 --title 歌名 --artist 歌手
# 已经有 audio.timeline.json / audio.report.md 的话加 --timeline audio.timeline.json --report audio.report.md，就不再自动分析
cd my_mv
python tools/run.py doctor          # 第一次会装渲染用的 node 依赖；也会告诉你浏览器有没有用上显卡（用的是软件渲染会慢好几倍）
python tools/run.py still 1 5       # 占位画面能出图，流程就通了
```

`--seconds 30` 只做前 30 秒（试做用）。项目里你主要写 `shots.js`（场景、镜头、角色位置）和 `plan.json`（镜头划分、动作轨、转场、表情），也可以全写在 `shots.js` 里。`engine/` 可以改，改的时候保留页面契约。

### 命令（在项目根目录）

```bash
python tools/run.py still 0.5 3.2 7.06   # → out/chk/t_<秒>.jpg，写镜头时随时看（用 Read 打开）
python tools/run.py frame 120 340        # 按帧号截图 → out/chk/f_<帧>.jpg
python tools/run.py style 3.2 11 20      # 风格对照 → out/style_compare.jpg
python tools/run.py actions              # 按 plan.json 的动作轨生成 ACTIONS.json
python tools/run.py act                  # 动作关 → out/act_check.md + act_check.png（约 1 分钟）
python tools/run.py trans                # 转场表 → out/trans_check.md
python tools/run.py voxel                # 体素关 → out/voxel_check.md（有 out/mv.mp4 时也量画面）
python tools/run.py scenes               # 场景关 → out/scene_check.md（有 out/mv.mp4 时也量画面）
python tools/run.py draft                # 草稿：每秒 12 帧、不跑检查，快速出 out/draft.mp4 看整体节奏
python tools/run.py video                # 预检 → 按场景分块渲染 → 配原曲 + 接触表 + 逐句帧条 + 全部检查 → 打包到 out/交付/
python tools/run.py video --redo C,D     # 只重渲场景 C、D（或者秒数范围 12-30），其余用上次渲好的块，再跑全部检查
```

渲染是最花时间的一步（显卡渲染时 1 秒成片要几秒，软件渲染要十几秒）。省时间的顺序：
- 写镜头时用 `still`（一次多给几个时间点，只开一次浏览器）、`act`、`voxel`、`scenes`，这些不出整片；
- `video` 会先做**预检**（动作关、转场登记、体素关、场景关里不需要画面的部分），稳妥模式下预检不过就不渲染，按报告改完再跑；
- 成片按场景分块存在 `out/chunks/`。检查报出问题、只改了某几个场景时，用 `video --redo <场景 id>` 只重渲那几块；改了引擎、共用的场景代码或者全片的东西（字幕、后期）就整片重跑 `video`；
- 想先看整体节奏就跑 `draft`（每秒 12 帧，时间减半，不能交付）；
- 每次跑完看 `out/timing.md`，知道时间花在哪一步。

## 流程

顺序是建议，可以来回走。

1. **听歌，写 `TREATMENT.md`。** 读 `audio.report.md` 和 `data/audio.timeline.json`。先想几个差别很大的构思（不同的微缩世界、叙事、镜头语言），选最贴这首歌、也最有想象力的一个。写清楚：世界是什么、角色是谁（从 `characters/` 里挑，读各自的 `character.md`）、情绪从哪到哪、哪几个音乐时刻要最强的画面（`drops`、最重的 `hits`）。分镜粒度自己定。
   - **场景表**：按歌的段落把全片切成 10–20 秒一个的场景，每个写清地点（`world`）、光色（`look`）、对应哪段歌、这一段的情绪和能量（收 / 放 / 反差 / 最高潮）、主要景别和运镜。先看整张表的起伏：能量曲线要有高有低，副歌比主歌大，桥段换个样子，高潮只有一个最大。写进 `plan.json` 的 `scenes`，场景边界放在转场的关键帧上。
   - **一个项目还是分段**：见上面「先决定：一个项目还是分段」，决定和理由写在这里。
2. **风格样张（硬关）。** 挑 2–3 个最难、最能代表全片的画面（通常一个大场面、一个有角色的中近景、高潮），直接写成影片里的镜头，`python tools/run.py style <秒>…` 和参考图并排。写进 `STYLE_FRAMES.md`：
   - 先写"比参考差在哪"，至少 3 条具体差距。
   - 再按"放在参考图旁边，像不像同一个模型师在同一个棚里拍的"逐项打 1–5 分：**构图**、**方块和边缘**（哑光、圆角、不是平面大块）、**光影和景深**、**配色**、**角色和场景的融合**（落地、影子、比例）、**场景细节**、**字幕**。低于 4 分就改，改完重新出图重新评。**场景细节**是以前最常丢分的一项（接力 MV 第 1 段只拿到 3 分），不要给自己放水。
   - 过关的样张留在片子里，是后面所有镜头的标准。
3. **排动作（稳妥模式）。** 在写镜头之前，给每句歌词里出镜的角色排动作：这句做什么、落在哪一拍。写进 `plan.json` 的 `tracks`（动作轨，写法见 `references/engine.md`），`python tools/run.py actions` 生成 `ACTIONS.json`。帧图里幅度太小、动作关量不出来的动作会进 `subtle`，照样要演，用推近、表情符号、特效让人看出来。
4. **写全片。** 一次写一个场景、一个镜头，写完马上 `still` 截图看，质量向样张看齐。每写完一个有角色的镜头跑 `act` 和 `voxel`，每加一个转场跑 `trans`，每写完一个场景跑 `scenes`。新场景不要只把旧场景换个颜色：地点、主要物件、镜头语言都要换。
5. **看。** 跑 `video`，看 `out/sheet.jpg`（接触表）和 `out/strips.jpg`（每句一行）：角色有没有在演、画面是不是在动、接触表从头扫到尾有没有起伏（是不是一大片同一个颜色、同一个景别）、哪一帧放在参考图旁边会掉价。
6. **实现不顺就改剧本。** 某个画面改两轮还是难看，或者成本远超它的价值，就换一种表达，保住这句歌的意思和情绪，运动量不能变少。改动记在 `CHANGES.md`。

## 实现上的几个提示

- **角色**：`R.play(名字, f, x, y, z)` 按动作轨摆，你只给脚底的世界坐标；身高统一是 `R.H` = 2 个世界单位，不要单独缩放主角。站的地方用 `R.addGround()` 登记，给个大概的 y，引擎会贴到真实表面。立牌朝向镜头、前移防遮挡都是引擎在镜头摆好之后自动做的。
- **走路**：动作轨里的走路一拍一步，你的代码要让角色在世界里每拍前进 0.4 身高（0.8 单位），跑步 1.6 身高（3.2 单位），脚才不打滑（V3）。镜头跟拍时也要真的移动角色，再让镜头跟上。
- **转场**：先在 TREATMENT 里给每次换场定种类和落点（哪一拍、哪条小节线、哪个 hit）。引擎的 8 种体素转场（`rain` 方块雨落、`crumble` 碎裂崩塌、`voxel` 体素化、`rows` 横条滑移、`through` 穿梭推进、`pullback` 拉远、`whip` / `whip_up` 甩镜）是现成可用的，不是白名单：自己写新的也行，在 `overlay` 里画、或者改着色器，只要登记。拍点上的硬切也是合法的一手（`mode: 0` + `kind: "cut"`、2 帧，T2 给硬切留了 ≤30% 的额度），前提是前后两个镜头有明显区别；普通淡入淡出不要用，硬切也不要连着用。
- **表情**：不出表情图，用代码拼的方块符号（16 种，`plan.json` 的 `emotes`），在拍上弹出。
- **字幕**：引擎在句首自动出字幕，样式在 `index.html` 的 `#cap` 里改；字高 ≥ 画面高 4.5%，任何背景上都看得清。
- **关键时刻取 `TL` 里的时间**（`beat_times`、`bar_times`、`hits`），帧号用 `R.beatFrame(n)`，不要手写秒数。
- 交付前去掉调试框、帧号、占位文字。

## 交付

前提：风格样张和成片复评都过关，`python tools/run.py video` 全部 PASS（自由模式只要求不定格）。

`out/交付/<名字>/` 里会自动收齐：成片、带音乐的 `mv.mp4`、接触表、逐句帧条、`checks/`（不定格、动作关、转场关、体素关、场景关报告）、`ACTIONS.json`、`TREATMENT.md`、`STYLE_FRAMES.md`、`style_compare.jpg`、`CHARACTERS.md` 和 `CHANGES.md`（如果有）、源码 zip。告诉用户：时长、构思和结构、主要卡点、检查报告提示了什么以及你怎么处理的、有没有没解决的问题。

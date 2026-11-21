# README 演示图是怎么做出来的

写 README、重拍截图、补新图时看这份。内容来自 2026-10-07 至 10-09 做宣传片和 README 素材的全过程记录：原图怎么出、在工具里怎么处理、截图怎么拍、怎么合成成 `docs/images/` 里的文件，以及工具改版后哪些图该重拍。

当前功能、界面名称和快捷键以 [中文 README](../../README.md) 和 [英文 README](../../README.en.md) 为准，[features.md](features.md) 是宣传片时期的快照。生成 `docs/images/` 的脚本是 [make_readme_images.py](make_readme_images.py)，开头动画是 [make_hook.py](make_hook.py)。

## 1. 一句话流程

原图（Anima 或 GPT Image 出的光滑丝袜，白底）→ 在工具里选部位、画走向线 → 导出成品图 + 用无头 Edge 拍界面截图 → 放进素材库 `readme\` → `make_readme_images.py` 裁切、拼接，写到 `docs/images/`。

两个原则贯穿始终：

- **纹理永远不重采样。** 凡是展示纹理的裁图，都按素材自己的像素裁，拼图不超过 GitHub 的 README 栏宽（约 830 px，所以拼图最宽 820）。浏览器一缩放，横纹就会混叠成摩尔纹，图就废了。界面截图（只有文字和叠加层，没有纹理）可以正常缩放。
- **每张图都能用工具重做。** 原图、走向线配方、截图步骤都有脚本，不靠手点。

## 2. 素材放在哪

全部在 `D:\Video\assets\stocking-promo\`：

| 目录 | 内容 |
| --- | --- |
| `raw\anima\`、`raw\anima2\` | Anima 出的候选图（第 1 轮、第 2 轮），带 `-sheet.jpg` 总览 |
| `raw\gpt\` | GPT Image 的候选图和日志（`b1`、`b2`、`b5`、`b5r2`、`b1-white`） |
| `work\b1-black\` 等 | 每个姿势在工具里处理的工作副本：原图、`-丝袜引导.psd`、`-丝袜成品.png`。`work\b2-black\user-draw\` 是用户亲手画的弯折腿（见 5.2） |
| `readme\` | **README 用的全部原始素材**（原图、成品、引导 psd、截图），`readme\README.md` 是文件清单 |
| `prompts\` | 出图脚本、提示词、截图配方（`*.json`）、`stk.py`（工具 HTTP 客户端）、`shot.mjs`（截图驱动） |
| `hook\final\` | 开头动画用的原图和成品（用户自己出的图） |
| `shots\` | 截图的中间产物 |
| `film\` | 宣传片素材（工具数据、界面截图、安装录屏等），README 不直接用 |

`readme\` 里的文件名规则：`<姿势>-<黑白>-<序号>-<内容>.png`，英文界面加 `-en`。

## 3. README 里每张图的来源

`docs/images/` 的文件 ← `readme\` 里的素材 ← 怎么拍的。尺寸是现在 `docs/images/` 里的实际像素。

| README 图 | 尺寸 | 素材 | 内容和做法 |
| --- | --- | --- | --- |
| `hook.png` | 820×1000 动图 | `.scratch\release\hook\original.png`、`finished.png` | 同一张图处理前后，分界线来回滑动。`make_hook.py`：裁 (196,100,1336,1490)，一次 Lanczos 缩到 820 宽，20 fps，第一帧是左右各半，不播动画的看图器也能看到对比 |
| `hero.png` | 820×610 | `b1-{black,white}-{original,finished}.png` | 左膝盖，上黑丝下白丝，左原图右成品，裁 (285,300,690,600)，按像素裁不缩放 |
| `regions-page.jpg`、`-en` | 1600×1000 | `b1-black-00-regions(-en).png` | 引导页，两条腿各涂成一个部位。只显示部位：关掉走向线、横纹、纵纹、隔开线（「显示」那组里只留「部位」） |
| `torso-regions.jpg` | 820×741 | `b5-black-00-regions.png` | 上衣三个部位：领子、左胸、右胸。只裁画布，裁 (902,94,1905,1000) 再缩到 820 |
| `courses-knee-ankle.jpg` | 1696×600 | `b1-black-02-knee-courses.png`、`-03-ankle-courses.png` | 膝盖（凸起：上 ∩ 下 ∪）和脚踝正面（凹处：上 ∪ 下 ∩）的横纹走向。引导页里滚轮放大后截一块 560×400，两张并排，间隔 16 |
| `guides-page.jpg`、`-en` | 1600×1000 | `b1-black-01-guides.png` | 引导页，两条腿各 6 条走向线，白色细线是算出来的横纹 |
| `torso-courses.jpg` | 820×741 | `b5-black-01-guides.png` | 三个部位各自的走向线，横纹顺着胸部弯，领子画成一圈圈 |
| `fold-step1/2/3.jpg` | 820×464 | `b2-black-fold-step1-no-divider / step2-divider / step3-knee-arc.png` | 弯折的腿三步：只画大腿和小腿各一条线（横纹串过折痕）→ 加隔开线 → 膝盖加弧线。引导页放大到折痕，裁画布 (420,300,2400,1420) 缩到 820×464 |
| `fold-finished.png` | 820×550 | `b2-black-fold-finished.png` | 三步做完后的成品，裁 (40,560,860,1110)，原像素 |
| `fold-knee.png`、`fold-junction.png` | 820×400 | `b2-black-fold-crop100-knee / junction.png` | 膝盖、大腿小腿交界处，左原图右成品，100% 原像素，每半边 400 宽，间隔 20 |
| `texture-page.jpg`、`-en` | 1600×1000 | `b1-black-04-texture-page(-en).png` | 纹理页：整体图拖分界线对比原图，细节框在大腿上。2026-10-09 重拍过：面板最上面是「预设」行，里面先在界面里存了一个和当前设置相同的预设（中文「黑丝·细线」，英文 Black · Fine lines），所以设置不变，只多出预设行里的名字；样式里多了「线圈」；「亮点」下面多了「摩尔纹效果（试验）」一行，右边是滑动开关，关着、滑杆收起（摩尔纹那一行是同日晚些时候再拍时加上的） |
| `styles.png` | 820×728 | `b1-{black,white}-style-N-*.png` | 样式对比：上黑丝六种，下白丝五种（油光是给深色丝袜用的，白丝没放），顺序和面板一致。每格是纹理页「细节」200% 的截图，裁 (433,260,563,620)，不缩放：每格 130 宽，六格加间隔正好 820。线圈格的素材是 `*-style-6-coil.png`（后补的，所以编号在最后） |
| `particle-page.jpg`、`-en` | 1600×1000 | `b1-black-10-particle-page(-en).png` | 纹理页，高光粒子的开关打开：下面露出「亮度」滑杆（100%，2026-11-19 之前叫「强度」），细节 100% 框在站姿腿的左大腿上（`fitclick` 0.327, 0.099），看得到顺着双腿受光处走的高光粒子带。预设行里先存了一个和当前设置相同的预设（中文「黑丝·高光粒子」，英文 Black · Particles）。和其他页面截图一样缩放（`shot(…, 1600)`）。2026-10-14 拍 |
| `particle-strength.png` | 818×400 | `b1-black-particle-000/035/070/100.png` | 高光粒子的强度 0 / 35 / 70 / 100% 下 B1 黑丝站姿的同一条左大腿到膝盖，从左到右，每张整图裁 (350,300,550,700)，即 200×400，四格间隔 6，按像素裁不缩放。四张整图用 `readme-recipes\b1_particle_export.py` 导出（B1 先用 `b1_setup.py` 重建，细线、密度 100、亮点关）；0% 是开关关着（逐像素等于 `b1-black-layers-000.png`），35 / 70 / 100% 是开关打开后各档强度。2026-10-14 |
| `moire-page.jpg`、`-en` | 1600×1000 | `b1-black-06-moire-page(-en).png` | 纹理页，摩尔纹效果的开关打开：下面露出「明暗」、「面积」两个滑杆（都是 100%；「明暗」在 2026-11-19 之前叫「强度」），细节 100% 框在站姿腿的左大腿上（`fitclick` 0.327, 0.099），看得到大腿和膝盖上一圈圈条纹。预设行里先存了一个和当前设置相同的预设（中文「黑丝·摩尔纹」，英文 Black · Moiré）。和其他页面截图一样缩放（`shot(…, 1600)`）。2026-10-09 拍，同日改用 B1 重拍（原先是 B2 弯折腿的膝盖，旧图备份在 `readme\old-moire-b2\`）；2026-10-14 摩尔纹改为从每个鼓起顶点由内向外扩展后重拍（旧图备份在 `readme\old-moire-v1\`） |
| `moire-area.png` | 820×820 | `b1-black-moire-area-035/050/070/100.png` | 面积 35 / 50 / 70 / 100%（强度 100%）下 B1 黑丝站姿的同一块左大腿，2×2（左上 35、右上 50、左下 70、右下 100），每张整图裁 (238,1,643,406)，每格 405 宽，间隔 10，按像素裁不缩放。四张整图用 `readme-recipes\b1_moire_export.py` 导出（B1 先用 `b1_setup.py` 重建，细线、密度 100、亮点关）。35% 是大腿顶上中心的一小圈 V，50% 在外侧再添一圈 V，70% 三圈，100% 扩满整个鼓起一圈套一圈（内圈始终不动，随面积增大不断往外增加）。选左大腿的理由：这一块条纹成 V 形一圈套一圈；膝盖上的条纹是不闭合的弧，面积低时也淡，右小腿更弱，脚踝没有。在这几块的窗口里量「效果开 − 关」的明暗差（平滑后）：左大腿 25% 起就有约 6 级灰度，左膝盖 25 / 35 / 50 / 70 / 100% 是 1.5 / 3.4 / 5.7 / 5.5 / 5.4，右小腿是 1.8 / 3.6 / 3.6 / 4.2 / 4.2。面积取 35 / 50 / 70 / 100：20% 在这块大腿上只有最顶上一丁点，35% 起最里圈 V 已完整清楚，后面三格把「一圈、两圈、三圈、一圈套一圈」拉开。先前用 B2 弯折腿的膝盖做过（面积 25 / 45 / 70 / 100，裁 (108,678,513,1083)），用户要求改用 B1 站姿图，旧图备份在 `readme\old-moire-b2\`；2026-10-14 改算法后重导，旧图备份在 `readme\old-moire-v1\`；更早试过 B5 躯干，黑色上衣上条纹的对比太低，看不清 |
| `layers-page.jpg`、`-en` | 1600×1000 | `b1-black-07-layers-page(-en).png` | 纹理页，加了第二层纹理：顶栏只有「引导、纹理」两个页签，左面板的「纹理层」列表两行（纹理 1 30%、纹理 2 70%，每行一根融合滑杆和「×」），标题右边是「+」，列表下面「自动 100%」按下，再往下的框第一行是「正在调：纹理 2」，框里加濑风选中；细节 100% 框在站姿腿的左大腿上（`fitclick` 0.327, 0.099）。预设行里先存了一个和当前设置相同的预设（中文「黑丝·细线+加濑风」，英文 Black · Layers，英文名要短，长了会在下拉里被截成省略号）。和其他页面截图一样缩放（`shot(…, 1600)`）。2026-10-12 拍 |
| `layers-mix.png` | 818×400 | `b1-black-layers-000/030/070/100.png` | 加濑风的占比 0 / 30 / 70 / 100%（其余是细线，自动 100% 开着）下 B1 黑丝站姿的同一条左大腿到膝盖，从左到右，每张整图裁 (350,300,550,700)，即 200×400，四格间隔 6，按像素裁不缩放。四张整图用 `readme-recipes\b1_layers_export.py` 导出（B1 先用 `b1_setup.py` 重建，细线、密度 100、亮点关）。0 和 100% 时只画一层，所以是细线、加濑风本身；30 / 70% 逐像素等于 `look.blend_layers` 算出来的加权平均（脚本之外用 `look.blend_layers([细线, 加濑风], [0.7, 0.3])` 核对过）。选这一条的理由：大腿的暗处、膝盖的高光和肤色透出的红都在里面，三种地方的纹理混合都看得清。试过的另一块（大腿上段 (330,120,530,520)）全是暗处，差别小。2026-10-12 |
| `presets-share.png`、`-en` | 820×132（中文）、820×341（英文） | `b1-black-08-presets-export(-en).png`、`b1-black-09-presets-import(-en).png` | 预设的导出和导入。每张素材是整页 DPR 2（3200×2000），只留两块：预设区块（`预设` 标题行带「导入…」「导出…」，下面是列表和保存、删除）和状态栏里的提示。导出那张是选中预设后点「导出…」，提示写着存到了哪个文件（`D:\预设\黑丝·细线.json`，英文 `D:\presets\Black · Fine lines.json`）；导入那张是点「导入…」选同一个文件，库里已有同名，提示是「已导入预设“黑丝·细线 (2)”（已有同名预设，没有覆盖）」。裁法：预设区块 (0,100,540,252)，提示 (0,1944,w,2000)，w 是提示的宽加 48（中文 640，英文约 1030）。中文左右并排（导出左、导入右）；英文提示长，并排会缩到 0.4，所以上下叠。缩到 820 宽，按界面截图缩放。2026-10-12 拍。系统的文件对话框拍不了，所以拍的时候用 `readme-recipes\preset_files_shot.py` 起服务器，把「导出」「导入」两个对话框换成固定文件夹（`D:\预设`、`D:\presets`，路径里不带用户名） |
| `slider-density/strength/tilt/sparkles.png` | 818×200 | `b1-black-density-070/100/130` 等 | 每个滑杆三档，同一位置并排。裁 (367,300,633,500) |
| `show-problems.png` | 820×405 | `b2-black-04-problems-density-140.png`、`-05-...-085.png` | 「标出问题」：密度 140% 时膝窝一大块红色，85% 基本消失。两张素材各裁 (1798,290,2203,695)，只取细节画布，不带面板、标题或勾选框 |

`readme\` 里还有一些做了但没进 README 的图（B5 的细节 100% / 200%、强度对比、白丝引导页、`b2-black-fold-texture-page-*` 等），要补图时可以直接用。

## 4. 原图怎么来的

### 4.1 统一要求

- **安全：** 全年龄。平视或俯视，不从低处往上拍；鞋一直穿着，不拍脚底；平底鞋（乐福鞋、玛丽珍鞋），不要高跟鞋；不用特定角色。
- **取景：** 只拍丝袜，膝盖略上方到脚。B2 放宽到大腿中段，裙摆盖住大腿上半。
- **画风：** 最基本的画风，白底，简单柔和上色。躯干要像一张绘画练习。
- **丝袜要画成光滑无纹的：** 不要网袜、罗纹、花纹袜，否则工具加的纹理会和原画打架。
- **尺寸：** 至少 1280×1856。832×1216 落在密度下限附近，滑杆拖不上去。
- **四角没有签名或文字。**
- 每个姿势出 4～8 个候选，选定前都要在工具里真的跑一遍：B2 的大腿要清楚地压在小腿上（交界处才有得画隔开线），白丝效果要过关，油光样式在黑丝上要稳。

### 4.2 Anima 出图（B1 站姿、B2 跪坐）

用 TagSystem 的 `bf16` 预设（`Evolved 2.9B 2.3`），高清修复开、修脸关，最前面加用户常用的 2 号画师串：

```
[(@jima:0.8), (@kedama milk:0.9), :@omone hokoma agm, (@rhasta:0.5), :12][:(@aki99:0.4), :8]
```

脚本 `prompts\anima_run2.py`。第 1 轮（`raw\anima\`，不带画师串）画风不对，弃用；第 2 轮（`raw\anima2\`，带画师串）选中：

| 姿势 | 选中的 | 尺寸 | 提示词要点 |
| --- | --- | --- | --- |
| B1 站姿正面 | seed 20261012 | 1344×2048（出图 896×1344 + 高清修复） | `masterpiece, best quality, safe, 1girl, solo, close-up, from front, standing, head out of frame, legs, knees, feet, black pantyhose, loafers, black footwear, ankle ribbon, red ribbon, white background, simple background, shadow.` + 一段英文描述：膝盖略上方到脚、不露裙子、两腿对称、光滑黑丝、小腿有柔和高光、脚踝骨清楚、平底黑乐福鞋 |
| B2 跪坐侧面 | seed 20261012 | 2048×1344（出图 1344×896） | `…seiza, sitting, kneeling, from side, head out of frame, legs, knees, black pantyhose, loafers, black footwear, pleated skirt, blue skirt, white background…` + 描述：侧面、大腿中段到脚、坐在脚跟上、**大腿压在小腿上并挡住一部分**、裙子盖住大腿上半 |

`readme\b1-black-original.png`、`b2-black-original.png` 和这两个 seed 的 raw 文件逐字节相同，没有后期修改。

### 4.3 GPT Image 出图（B5 躯干、B1 白丝）

用 GPT Image（Azure gpt-image-2.5，经 TagSystem 调用）。

**B5 躯干习作：** `prompts\gpt-b5-r2.txt`，从第 2 轮 3 个候选里选了第 1 个（`raw\gpt\b5r2\124532-GPTGen-b3decac7_00001_.png`，1536×2048）：

> Simple 2D anime-style figure-drawing practice illustration of a woman's torso only, like an art student's clothed torso study on a plain pure-white background: clean black line art, flat anime cel shading with one soft shadow tone and one soft highlight, minimalist, not photorealistic, not 3D. The frame shows only the torso from the base of the neck down to just below the waist; no head, no face; the arms are cut off just below the shoulders like a mannequin study. Front view, turned very slightly to one side. She wears a plain, smooth, opaque black long-sleeved turtleneck top made of thin stocking fabric that fits closely; it is neatly tucked into a high-waisted plain grey skirt whose waistband is visible at the bottom edge. Average, slim, modest proportions; the chest is small-to-average and fully covered, shown simply as two gentle rounded forms with a soft shaded fold line between them; nothing is emphasised. The fabric is plain: no pattern, no texture lines, no seams, no lace, no see-through areas. No text, no signature, no watermark. Modest, safe-for-all-ages art study.

Anima 画的 B5（`raw\anima2\b5__*`）胸部过于突出，没用。

**B1 白丝：** 用 GPT Image 的**编辑**功能从黑丝原图改，只改丝袜，两版构图完全一致（`prompts\gpt-b1-white.txt`）：

> Change only the stockings: make the black pantyhose plain white pantyhose. Everything else stays exactly as it is: the same pose, leg outlines, line art, black loafers, red ankle ribbon, white background and floor shadow, and the same simple anime illustration style. The white pantyhose are plain and smooth (no pattern, no texture lines, no seams), slightly sheer: soft light grey shading along the sides of the legs, a faint warm skin tint on the knees, and soft highlights on the shins, keeping the same light direction and shading shapes as the original.

编辑后做了**颜色校正**（对照黑丝原图，把没改的区域的色偏拉回来），文件名带 `-color`：选中 `raw\gpt\b1-white\130347-GPTEdit-24d96f04_00001_-color.png`。腿以外的像素和黑丝原图平均只差 1/255。

GPT 候选里 B1、B2 的构图稿（`raw\gpt\b1`、`b2`）最后都没用，B1、B2 用的是 Anima 的图。

### 4.4 开头动画的图

用户自己出的一组对比图：黑丝、红底高跟鞋的腿部特写，1536×1536，Forge seed 2058236258，2 号画师串。成品是用户在工具里处理的。这张是高跟鞋，只用在开头动画，不受上面「平底鞋」的规则约束。

> 曾尝试过「找 danbooru 上裤袜占比高的 rating:g 图，用 ControlNet（深度模式，强度 0.7，作用步数 0–0.43）复刻构图」做人气角色引子（`prompts\hook_render.py`），出了 7 个角色，用户看过后整轮弃用。

## 5. 在工具里怎么处理

### 5.1 环境

- 只用**独立实例**，不碰用户自己的实例（端口 8765）和 `%LOCALAPPDATA%\StockingTexture`：

  ```
  cd D:\Stocking
  .venv\Scripts\python.exe -m stocking --isolated --port 8790 --no-window --stay
  ```

  起来后 `POST /api/lang {"lang":"zh"}` 切中文。
- `prompts\stk.py` 是薄薄一层 HTTP 客户端：`open_path`、`wait_ready`、`segment`（点选）、`stroke`（走向线）、`divider`、`mirror`、`rename`、`split`、`look_put`、`export`、`wait_solved`……要 `requests`、`numpy`、`Pillow`（TagSystem 的 Python 里有）。
- 画布坐标都是**原图像素**。

### 5.2 各姿势的处理

**B1 站姿（黑丝、白丝，`prompts\b1_setup.py`）**

1. 打开原图，等 SAM 和深度模型就绪。
2. 点选：左腿点 (470,1000)，右腿点 (860,1000)。左腿用小档点选会连带右大腿一块，点了右腿才抢回来；右脚丝带下面漏了一条丝袜，用小档在 (906,1530) 补点一下。
3. 每条腿 6 条走向线，用 `stk.arc` 画弧。弧度 `sag` 是占腿宽的比例，正数向下弯（U），负数向上拱（∩）；`inset` 是两端离腿边的比例：

   | y | sag | inset | 位置 |
   | --- | --- | --- | --- |
   | 260 | +0.10 | 0.10 | 大腿 |
   | 445 | −0.22 | 0.06 | 膝盖凸起，上方 ∩ |
   | 600 | +0.24 | 0.06 | 膝盖凸起，下方 ∪ |
   | 1000 | +0.14 | 0.10 | 小腿中段 |
   | 1505 | +0.20 | 0.06 | 脚踝正面凹处，上方 ∪ |
   | 1625 | −0.22 | 0.08 | 脚踝正面凹处，下方 ∩ |

   凸起处（膝盖）上方 ∩、下方 ∪ 把凸起包住；凹处（脚踝正面）反过来。
4. 导出：`style=knit`（界面上叫「细线」，见第 8 节第 1 条）、密度 100、斜度 32、强度自动、亮点全 0。

**B2 弯折的腿（`prompts\b2_strokes.py` 是旧配方，现在的见下）**

大腿压在小腿上是两块丝袜贴在一起，深度上没有台阶，自动隔开线找不到，所以要手画隔开线（D）。README 现在用的是**用户亲手画的线**（`work\b2-black\user-draw\`）：

- 用户在 PSD 里画了线（`user-drawn-v2-丝袜引导.psd`），`smooth.py` 做平滑（高斯，每条偏离原手绘 ≤ 4 px，远侧腿膝盖那条 8.7 px），存成 `smoothed.json`。
- `build_step.py <0..4>` 用 API 重放：两个部位「近侧腿」「远侧腿」；远侧腿始终 2 条线；近侧腿 `1` = 大腿一条 + 小腿一条，`2` = 再加隔开线，`3` = 再加膝盖弧线（在膝盖中间，弧度和膝盖弯折一样）。
- 成品图用 `export_result.py <步骤>` 导出：细线、密度 100、强度自动、亮点关；「标出问题」减弱面积 0.06%。
- 截图：引导页放大到折痕（窗口 1600×1000，DPR 2.4，滚轮 −450 于画布 (600,650)），拍 `step1/2/3-zoom.png`，就是 README 里 `b2-black-fold-step*.png`。
- **这张蹲姿的走向线是不完美的**（用户 2026-10-10 说明）：在这张图上看到的不对劲，不少来自走向线本身，不要拿它当油光的基准，也不要为它再往油光里加专门的补丁。具体表现：V 在膝盖最大，往髋和往脚都变小，所以每个 V 行同时切到大腿和小腿；走向场只在膝盖一头连通（去掉膝盖端，大腿和小腿是互不相连的两块，各约 23 万像素）。油光里隔开线没到头时的处理（两侧各算一块、延长线处没有硬边）是通用机制，只在隔开线没碰到轮廓时触发，其他图不变；两侧的光在膝盖处连不连成一条，这张图不保证，也不画东西去连（做过一条手工的弧，已去掉，见 `.scratch\oily-glint-centre\research.md`）。

**B5 躯干（`prompts\b5_strokes.py`）**

1. 点选中档选整件上衣，右键点选减掉两只袖子。
2. 先把领子切出来；剩下的身体点「自动分割」，沿镜像对称轴竖着切成左右两块（4c74de1 起的行为）。之前的旧版本会把宽躯干横着切，所以 B5 的老截图是手切的，两者基本重合。
3. 三个部位：领子、左胸（`身体-左` 改名）、右胸（`身体-右` 改名）。
4. 走向线：左右胸各 4 条，y = 470（sag −0.12）、690（−0.16）、930（+0.16）、1180（+0.10），inset 0.10 / 0.08 / 0.08 / 0.10；领子 2 圈，y = 150、240，sag +0.12，inset 0.10。
5. 深色上衣在默认强度下横纹太淡：**强度手动 170%**（成品图和截图都是），不要「自动」。

### 5.3 设置清单

| 项 | 取值 | 说明 |
| --- | --- | --- |
| 密度 | B1、B5 用 100%（横纹间距 4.87 px）；B2 用 85% | 按「标出问题」调：主要区域不能有大块红色。B2 的膝窝 100% 就有 0.5%，所以成品用 85% |
| 强度 | 黑丝自动（100%）；白丝自动（40%）；B5 手动 170% | |
| 亮点 | 细线、针织、线圈、油光：按深度、按画面亮部都设 0；斜单线、加濑风：默认（100，关联） | 线圈是画画时的底纹，不加亮点。亮点对比图在黑丝上做，用「均匀分布」0 / 100 / 300%（「按深度」「按画面亮部」只落在凸起和高光处，细节框里不一定有）。白丝的整页截图和成品开着均匀分布 300%，说明里不提 |
| 细节放大 | 200%，细节框放在**平坦的大腿**上（`fitclick` 0.342, 0.085） | 小腿和膝盖都不好看；膝盖留给展示横纹走向。B5 用 100%（0.49, 0.33）看完整横纹随胸部形状弯，再用两张 200% 看上方（0.605, 0.264）和下方（0.605, 0.425） |
| 样式顺序 | 细线、针织、线圈、斜单线、加濑风、油光（试验） | 就是面板里的顺序；`styles.png` 也按这个顺序 |
| 摩尔纹效果 | 默认关。摩尔纹那两张图里：开关打开，强度 100%、面积 100%（对比图用 35 / 50 / 70 / 100） | 面板里滑动开关（`#moire-on`）打开后才出现强度（`#moire`）和面积（`#moire-area`）。条纹要等深度模型算完才有：开了开关后要等 3.5 秒以上再拍。亮点关着，不影响条纹 |

「标出问题」的减弱面积（图例里的百分数）：B1 黑丝 0.08%，B5 0.03%；B2 按密度看，85% 不到 0.1%、100% 0.5%、130% 2.5%、140% 3.5%、160% 6.7%。膝窝那里走向线呈扇形收拢，横纹挤得最密，红色最先在那里出现。

## 6. 截图怎么拍

驱动脚本 `prompts\shot.mjs`：Playwright 驱动无头 Edge（`playwright-core`，用的是 `D:\Video\promo\node_modules`），跑一个 JSON 配方：

```
node shot.mjs <配方>.json
```

- 窗口 1600×1000，中文界面；README 的界面截图用 **DPR 1.5**（得到 2400×1500，合成时缩到 1600 宽）；放大折痕的 B2 三步图用 **DPR 2.4**（3840×2400）。
- 配方里的步骤：`click`（CSS 选择器）、`range`（设滑杆值）、`fitclick`（按「整体」图的比例点一下，用来定细节框位置）、`wheel`（滚轮缩放）、`key`、`mouse`、`eval`（读界面上的值，用来核对）、`shot`（可带 `clip` 或 `selector`；细节用 `.detail-pane`）。
- 用到的界面元素：`#tab-edit` / `#tab-look`（引导 / 纹理）、`[data-style=…]`（样式）、`#density`、`#strength`、`#tilt`、`#sparkle-depth` / `#sparkle-bright` / `#sparkle-even`、`[data-zoom='1'|'2']`（细节 100% / 200%）、`#show-problems`（预览区里的「标出问题」勾选框，配方可用 `{"check":["#show-problems",true]}` 打开）、`#strength-auto`（强度自动）。
- 配方文件：

  | 文件 | 拍什么 |
  | --- | --- |
  | `b1_zh_guides.json`、`b1_en.json` | 引导页（中、英），英文还拍纹理页 |
  | `.scratch\release\readme-recipes\b1_guides_zh.json`、`b1_guides_en.json` | README 的引导页和部位页（中、英），一个配方拍两张：先拍引导页（`01-guides(-en).png`，默认的「点选」工具，「显示」各项保持默认：部位、走向线、横纹、隔开线勾着，覆盖范围和纵纹不勾），再把「走向线」「横纹」「隔开线」三个显示勾掉拍部位页（`00-regions(-en).png`）。每张拍之前把指针移到状态栏。英文先把部位改名成 Left leg / Right leg。2026-11-20 起用这两份，取代素材库里的 `b1_zh_guides.json` 和 `b1_en.json` 的引导页那一步 |
  | `.scratch\release\readme-recipes\models_shot.py` | 在没有 `models\` 的工作树里起独立实例，从工作树根目录运行：`.venv` 的 `python .scratch\release\readme-recipes\models_shot.py D:\Stocking\models 8790`。从给定文件夹取 SAM 权重和深度模型（缺哪个文件就报哪个，不会退到联网下载），不改工具自己的代码；运行时的日志和实例登记写到本次运行的临时文件夹，不碰用户的 |
  | `b1_black_shots.json` | 引导页、膝盖和脚踝放大、纹理页、五种样式的细节、「标出问题」 |
  | `b1_flat.json` | 五种样式和密度、强度、斜度三档 |
  | `b1_black_sparkles.json` | 亮点「均匀分布」0 / 100 / 300 |
  | `b1_white.json`、`b1_white_look.json` | 白丝的引导页和纹理页 |
  | `.scratch\release\readme-recipes\b1_black.json` | 黑丝的纹理页、六种样式（含线圈）和密度、强度、斜度各档，一个配方拍完（取代 `b1_flat.json`） |
  | `.scratch\release\readme-recipes\b1_white.json` | 白丝的纹理页和六种样式的细节 |
  | `.scratch\release\readme-recipes\b1_texture_zh.json`、`b1_texture_en.json` | README 的纹理页截图（中、英）：在界面里存一个和当前设置相同的预设，等 5.5 秒让「已保存预设」提示消失，再点细节框的位置拍。拍之前先把服务器语言切到对应的 zh / en |
  | `b2a.json`、`b2b.json`、`b2c.json`、`b2_red.json` | B2 的折痕放大和「标出问题」140% / 85% |
  | `.scratch\release\readme-recipes\b1_particle_zh.json`、`b1_particle_en.json` | 高光粒子打开的纹理页（中、英），拍在 B1 黑丝站姿上：细线、亮点关、细节 100%，打开开关（`#particle-on`），强度 100%，在界面里存一个预设（中文「黑丝·高光粒子」，英文 Black · Particles），等 5.5 秒让提示消失，再点左大腿（`fitclick` 0.327, 0.099）。拍之前把服务器语言切到对应的 zh / en，英文先把部位改名成 Left leg / Right leg；文档要先用 `prompts\b1_setup.py` 重建。存成 `shots\b1-black\10-particle-page(-en).png` |
  | `.scratch\release\readme-recipes\b1_particle_export.py` | 把重建好的 B1 按高光粒子强度 0 / 35 / 70 / 100% 导出四张整图，写到素材库 `readme\b1-black-particle-NNN.png`。要用有 `requests` 的 Python |
  | `.scratch\release\readme-recipes\b1_moire_zh.json`、`b1_moire_en.json` | 摩尔纹效果打开的纹理页（中、英），拍在 B1 黑丝站姿上：细节 100%，打开开关（`#moire-on`），强度、面积 100%，在界面里存一个预设，等 5.5 秒让提示消失，再点左大腿（`fitclick` 0.327, 0.099）。拍之前把服务器语言切到对应的 zh / en；文档要先用 `prompts\b1_setup.py` 重建（见 5.2）。存成 `shots\b1-black\06-moire-page(-en).png` |
  | `.scratch\release\readme-recipes\b1_moire_export.py` | 把重建好的 B1 按面积 35 / 50 / 70 / 100% 导出四张整图，写到素材库 `readme\b1-black-moire-area-NNN.png`。要用有 `requests` 的 Python（3.12 的有，项目的 `.venv` 没有） |
  | `.scratch\release\readme-recipes\b1_layers_zh.json`、`b1_layers_en.json` | 加了第二层纹理的纹理页（中、英），拍在 B1 黑丝站姿上：细线、亮点关、细节 100%，点「+」加一层（新层默认就是加濑风，选中），把「融合」区第二根滑杆（`#blend-rows .blend-row:nth-child(2) input`）拉到 70，在界面里存一个预设，等 5.5 秒让提示消失，再点左大腿（`fitclick` 0.327, 0.099）。拍之前把服务器语言切到对应的 zh / en，英文要先把部位改名成 Left leg / Right leg，拍完改回；每次拍之前用 `prompts\b1_setup.py` 重建文档（导出会把当时的设置存进文档，不重建的话打开纹理页就带着上次的几层）。存成 `shots\b1-black\07-layers-page(-en).png` |
  | `.scratch\release\readme-recipes\b1_layers_export.py` | 把重建好的 B1 按加濑风的占比 0 / 30 / 70 / 100% 导出四张整图（细线加加濑风，自动 100% 开着），写到素材库 `readme\b1-black-layers-NNN.png`。要用有 `requests` 的 Python |
  | `.scratch\release\readme-recipes\b1_presets_zh.json`、`b1_presets_en.json` | 预设的导出和导入（中、英），DPR 2、整页：纹理页，细线、亮点关、细节 100%，在界面里存一个预设（中文「黑丝·细线」，英文 Black · Fine lines），等 5.5 秒让提示消失，点「导出…」等 2.5 秒拍 `08-presets-export(-en).png`；再点「导入…」等 2.5 秒拍 `09-presets-import(-en).png`。两次的提示都在状态栏，5 秒后就消失，所以点完要马上拍。**不能直接用 `python -m stocking` 起服务器**：「导出…」「导入…」会弹系统的文件对话框，无头 Edge 点不了。用 `readme-recipes\preset_files_shot.py <文件夹> <原图> 8790` 起（它把两个对话框换成固定文件夹：导出写 `<文件夹>\<建议的文件名>`，导入读文件夹里第一个 `.json`），中文用 `D:\预设`，英文用 `D:\presets`。2026-11-20 起可以再带两个参数 `<模型文件夹> <显示用的文件夹>`：文件实际写进 `<文件夹>`（放在被忽略的 `out\` 下），状态栏里显示成 `D:\预设\…`、`D:\presets\…`，不用在 D 盘根目录建文件夹，图里的路径只是展示用的。点完「导出…」「导入…」配方会把指针移到状态栏，免得按钮的悬停提示入镜。起之前文件夹和预设库都要是空的，否则导入的名字会是 (3)。英文要先切 zh、用 `b1_setup.py` 重建文档（它用中文部位名），再切 en 拍 |
  | `b5.json`、`b5_200.json`、`b5_200u.json`、`b5_strength.json` | B5 的纹理页、200% 细节、强度对比 |
  | `…\user-draw\tools\` | B2 三步里带「走向 / 隔开」按钮选中状态的截图（宣传片用，README 没用） |

- 英文界面：`POST /api/lang {"lang":"en"}`，并把部位**临时改名**成 `Left leg` / `Right leg` 再拍，拍完改回，不要动用户的文件。

拍每张图之前确认：服务器没有求解中、页面没有请求在途、状态栏里没有残留的「已更新，用时 x 秒」之类的临时提示（它的秒数会变，对比时会显示出差异）、指针移到一边、没有悬停提示。

## 7. 合成

`make_readme_images.py`（在 `.scratch\release\`，输出到 `docs/images/`）：

- `load()` 读素材库里的图，`row()` / `col()` 拼接，`save()` 写出：JPG 用 q88、progressive；PNG 用 optimize。
- 纹理裁图按素材像素裁，不缩放；界面截图用 `shot(name, width)` 缩放（Lanczos）。
- 英文版的图如果素材库里没有，脚本只打印一句「missing」，不会报错。
- 在工作树重拍时，按第 9 节的只读覆盖流程同时设置 `README_IMAGES_SRC` 和 `README_IMAGES_OUT`，先在 `out/` 中合成并和现行 `docs/images/` 逐张比较，再换图。脚本会打印每张的尺寸和大小；别让它按默认路径写到主检出。

## 8. 容易踩的坑

1. **样式的内部 id 和界面名字不一样**，配方和导出参数里写的是内部 id：

   | 界面名 | id |
   | --- | --- |
   | 细线 | `knit` |
   | 针织 | `loops` |
   | 线圈 | `coil` |
   | 斜单线 | `lines` |
   | 加濑风 | `grain` |
   | 油光 | `oily` |

2. **`fitclick` 的坐标是比例**（相对「整体」图），换一张图要重找位置。
3. **等求解和渲染：** 画完线要 `wait_solved()`；换样式、拖滑杆后细节要等 3 秒，油光要等 6 秒。
4. **导出接口变了：** 现在 `POST /api/doc/{id}/export` 必须带 `path`（导出先弹「另存为」，API 没有窗口，直接传路径）。旧脚本 `export_png.py` 是按「写到原图旁边」写的，要补 `path`。
5. **点选的顺序：** 左腿小档点选会连带右大腿一块，必须点了右腿才抢回来；漏了的地方用小档补点。
6. **镜像出来的右腿和直接画出来的右腿位置差几个像素**（轮廓拟合），对比时别拿两种混着用。
7. **切开工具开着时，工具会把「不是正在切的部位」压暗**（透明度约 0.12），拍 B5 的部位图时先按 Esc 回到画线工具，否则领子看起来像消失了。
8. 不要碰用户的实例和 `%LOCALAPPDATA%\StockingTexture`；按 PID 停自己起的进程。

## 9. 工具改版后，哪些图要重拍（2026-10-09 核对到 be7d4bc）

| 图 | 状态 | 原因 |
| --- | --- | --- |
| `regions-page(-en)`、`guides-page(-en)` | 已更新（9b8f37a） | 引导页第 2 步改成一行「走向 P｜隔开 W｜镜像」，删了常驻说明 |
| `texture-page.jpg`、`-en` | **已重拍（2026-10-09）** | 纹理面板最上面多了「预设」行（aa4cd80、79d2ef5），样式里多了「线圈」（88a3898），右上角语言开关现在高亮当前语言。除了这三处，整页和原图逐像素相同（舞台部分只有语言开关那 45×34 px 不同） |
| `texture-page.jpg`、`-en` 再拍一次 | **已重拍（2026-10-09，be7d4bc 之后）** | 纹理面板在「亮点」下面又多了一行「摩尔纹效果（试验）」，右边是个滑动开关，默认关、滑杆收起。照下面「重拍的做法」重建文档，用 `b1_texture_zh.json`、`b1_texture_en.json` 拍，开关留在默认关。和旧图逐像素比：舞台（整体、细节、分界线）0 个像素不同，只有左栏从这一行往下不同（中文版 y ≥ 702，英文版 y ≥ 716，DPR 1 的坐标），上面的预设、样式、密度、强度、亮点完全一样。重拍前的旧图备份在 `readme\old-ui-v2\`。`make_readme_images.py` 重新合成的 22 张图里，20 张和 `docs/images` 里的逐字节相同，变的只有这两张 |
| 摩尔纹效果的演示图 | **已做（2026-10-09），同日改用 B1 重做** | README 的摩尔纹效果那一段后面多了两张图：`moire-page.jpg`（`-en`）纹理页开关打开的样子，`moire-area.png` 面积 35 / 50 / 70 / 100% 的 2×2 对比（做法见第 3 节）。素材是 `readme\b1-black-06-moire-page(-en).png` 和 `readme\b1-black-moire-area-NNN.png`。最初用 B2 弯折腿的膝盖做，后来用户要求改用 B1 站姿图，那一套 B2 素材备份在 `readme\old-moire-b2\`。重新合成后原来的 22 张图都和 `docs/images` 里的逐字节相同，变的只有这三张。以后摩尔纹的画法（`look.py` 的 `MOIRE_*`）一改，这几张就得重拍 |
| 纹理层的演示图 | **已做（2026-10-12）** | README 的「纹理层」那一段多了两张图：`layers-page.jpg`（`-en`）纹理页加了第二层的样子（融合区两根滑杆、自动 100%、纹理 2 标签），`layers-mix.png` 加濑风占比 0 / 30 / 70 / 100% 的一排对比（做法见第 3 节）。素材是 `readme\b1-black-07-layers-page(-en).png` 和 `readme\b1-black-layers-NNN.png`。重新合成后原来的 25 张图都和 `docs/images` 里的逐字节相同，变的只有这三张。核对过：功能之前的代码（e72a262）和加了纹理层之后的渲染单层完全一样；一层的导出等于 `layers-000`；30 / 70% 的两张等于 `look.blend_layers` 的加权平均。**注意：** 素材库里旧的 `b1-black-finished.png` 等是 e72a262（细线、针织、线圈的间隙明暗改成按部位取一次）之前的渲染，和现在的细线有细微差别（用 `b1_setup.py` 重建后导出，约 12.8 万像素不同，差的平均 2.5 级、最大 35，各处都有）；`layers-000` 是现在的渲染，所以和 `hero.png` 等旧图里的细线会有这点差别，不影响观感，哪天重拍旧图时一并换掉 |
| `styles.png` | **已重拍（2026-10-09）** | 加了线圈一列：黑丝六种、白丝五种，每格裁窄到 130 px，六格正好 820 px |
| `styles.png` 白丝那一行 | **已重拍确认（2026-10-09）** | def4c1d 让强度不再缩放亮点。白丝自动强度是 40%，斜单线和加濑风开着亮点，亮点变亮了：只有亮点像素变，各约 1800 个，全部变亮、没有一个变暗；细线、针织、油光逐像素不变 |
| `styles.png` 黑丝那一行的油光格 | **已重拍（2026-10-09，8ba539a 之后）** | 油光改版了（`oily.py`）：反光从一条细线变成「细而亮的芯 + 宽而柔的光」，形状照真实油光黑丝的商品图量出来；深色丝袜的边缘变黑、中间透一点暖色；没画高光的部位补一条淡淡的中线。所以这一格从一道细斜线变成一片柔和的光泽过渡（最亮的光落在格子上沿）。**只有这一格变**：黑丝那一行重拍的 14 张细节图（五种其它样式、密度、强度、斜度各档）和素材库逐像素相同，只有 `15-style-glossy.png` 不同；用 `make_readme_images.py` 重新合成的 25 张图里 24 张和 `docs/images` 逐字节相同，不同的只有 `styles.png`，而且新旧 `styles.png` 只有油光格那 130×360 个像素不同。白丝那一行没有油光，不受影响，没有重拍。素材 `readme\b1-black-style-5-glossy.png`，重拍前的在 `readme\old-oily-v6\`。截图等 6 秒和等 20 秒逐像素相同（渲染已经完成）。`b1-black-glossy-page.png`（油光的整页截图）没进 README，没有更新，左栏里还是旧版的说明文字 |
| `styles.png` 黑丝那一行的油光格 再拍一次 | **已重拍（2026-10-10，底线光之后）** | 油光的反光现在沿整条腿一直延续（`oily.py` 的底线光，见 [features.md](features.md) 里的「底线光」）：画里高光变暗的地方补一道淡一些的光线接上，不再断。所以这一格从「光在格子上沿最亮、往下散掉」变成「一道贯穿整格的光，往下变淡但不断」。**只有这一格变**：用 `make_readme_images.py` 合成的 25 张图里 24 张和 `docs/images` 逐字节相同，不同的只有 `styles.png`，新旧 `styles.png` 只有油光格 130×360 里的 44451 个像素不同（最大差 44 级），其余五种样式和白丝那一行不变。拍法同上一行：`b1_setup.py` 重建 B1 黑丝（「标出问题」减弱面积 .0008），只点油光（先点细线，`fitclick` 0.342, 0.085 落到左大腿，再点油光，两个亮点滑杆设 0，等 6 秒，截 `.detail-pane`）。**改了 `oily.py` 要重启独立实例**才会加载新代码，不重启拍出来还是旧的。后面几轮对被丝带切开的右腿的改动（被切开的几段按一条肢体对齐、切口不当轮廓）没动这一格：用最终代码再拍一次，和这张逐像素相同（左大腿没被切开）。素材 `readme\b1-black-style-5-glossy.png`，重拍前的在 `readme\old-oily-v7\`。 |
| 其他 | 不受影响 | 黑丝的细节裁图（五种样式、密度、强度、斜度各档共 14 张）用现在的工具重拍，和素材库原图逐像素相同；`make_readme_images.py` 重新合成的 22 张图里，19 张和 `docs/images` 里的逐字节相同，变的只有上面三张 |

`readme\` 里的这些图带着旧版引导页的左栏：`b2-black-01-guides-divider.png`、`b1-white-01-guides.png`、`b1-white-04-texture-page.png`、`b5-black-01-guides.png`、`b5-black-00-regions*.png`、`b2-black-fold-step*.png`。其中 `torso-*` 和 `fold-step*` 在 README 里只用了画布部分的裁图，不受影响；其余几张没进 README，要用的话先重拍。

### 重拍的做法，和怎么核对（2026-10-09 照这个做过一遍）

1. 起独立实例（第 5.1 节），语言先切 zh。
2. **重建文档，不要打开导出的 `丝袜引导.psd`：** 用 `python prompts\b1_setup.py <readme\b1-black-original.png>`（白丝用 `b1-white-original.png`）重新点选、画线。PSD 里的走向线是栅格，求解出来的横纹和 API 画的浮点折线差约 0.1 px，纹理会有 1–3 级的噪点差异，和素材库里的原图对不上；按原配方重建，细节图就和原图逐像素相同。重建后「标出问题」的减弱面积应是黑丝 0.08%、白丝 0.06%。
3. 拍：`node prompts\shot.mjs .scratch\release\readme-recipes\<配方>.json`（配方见第 6 节）。
4. 核对：`python .scratch\release\compare_shots.py black <shots\b1-black>`、`… white <shots\b1-white>`。黑丝的细节图应全部 `identical`；白丝只有斜单线和加濑风不同，而且全是变亮的像素。页面整图（`04-look`）只有界面不同。纹理页整图的配方（`b1_texture_zh/en.json`）存的文件名是 `04-look-presets(-en).png`，不在 `compare_shots.py` 的对照表里：自己用像素对比和 `readme\` 里现有的 `b1-black-04-texture-page(-en).png` 比，左栏（272 px，截图 1.5 倍，即 x < 408）以右的舞台应该 0 个像素不同，不同的只该是左栏里这次改版动过的那几行。
5. 把要换的图放进 `readme\`（先备份旧的，文件名不变），`README_IMAGES_OUT=<临时文件夹>` 先试跑 `make_readme_images.py`，逐张对比后，只把变了的复制进 `docs/images\`。

核对时会出现假差异的几件事：

- 用新旧两个提交各拍一遍（旧的是 83c694c，当时拍原图的版本），细节图逐像素相同：线圈和针织的改动没有动任何已有样式的渲染，对不上就是文档重建得不对（第 2 步），不是工具变了。
- 状态栏的「已保存预设」「已载入预设」提示 5 秒后才消失，拍之前要等。
- 开着的预设下拉（原生控件）在无头 Edge 里拍不出来，所以截图里只有选中的名字。把 `select.size` 改大想让它展开成列表也不行：下拉有固定高度，只露出一行半。所以导入那张图只拍状态栏里的提示，不拍列表。
- `make_readme_images.py` 要用 Pillow 12.x 的 Python 跑（项目 `.venv` 的 Python 3.12 是 12.3.0，系统的 Python 3.12 是 12.2.0）。默认的 `python` 若是 3.10（Pillow 11.3.0，有 `requests` 所以拍图脚本用它），合成出来的 `fold-knee.png` 和 `docs/images` 里的字节不同（像素完全一样，是 PNG 编码器版本不同），别当成图变了；换 Pillow 12.x 再合成，就只剩真正变了的图。别忘了设 `README_IMAGES_OUT`，不设的话默认写到 `D:\Stocking\docs\images`（主工作区）。

### 2026-11-20 重拍记录（核对到 2fef199）

界面改版（ee4bfca 纹理层移进左面板、b94c603 高光粒子「强度」改叫「亮度」、摩尔纹效果「强度」改叫「明暗」、点选换成 W、隔开换成 D，dfc1f52、2fef199 两页的提示和按钮状态）之后，带界面的 14 张图全部重拍：`regions-page`、`guides-page`、`texture-page`、`particle-page`、`moire-page`、`layers-page` 的中英 12 张 JPG，和 `presets-share.png`、`presets-share-en.png`（预设区块里「删除」变成红色，整块下移了几个像素；状态栏的文案没变）。其余 20 张（纹理裁图、画布裁图、`hook.png`）没有动，重新合成后和 `docs/images` 逐字节相同。

- **做法：** 在工作树里做，素材库只读。用 `models_shot.py` 起独立实例（预设两张用 `preset_files_shot.py` 带后两个参数），`b1_setup.py` 重建文档，每组配方之前重建一次；配方里写到素材库 `shots\` 的路径在拍之前改道到工作树被忽略的 `out\readme-shots\shots\`。新截图按素材库的文件名放进 `out\readme-shots\override\`，`README_IMAGES_SRC=<那个文件夹>`、`README_IMAGES_OUT=<临时文件夹>` 跑 `make_readme_images.py`（先在覆盖文件夹里找，没有的才读素材库），只把变了的 14 张复制进 `docs/images`。配方里的 `shot` 默认仍指向素材库的 `shots\`（维护者自己重拍时的输出位置），不能写素材库时必须先改道再拍；运行素材库里的 Python 脚本（`b1_setup.py`，它会导入 `stk.py`）要加 `-B` 并设 `PYTHONDONTWRITEBYTECODE=1`，否则会在素材库里生成字节码缓存。
- **素材库 `readme\` 里这 16 张原始截图还是旧版的**（`b1-black-00-regions`、`-01-guides`、`-04-texture-page`、`-06-moire-page`、`-07-layers-page`、`-10-particle-page`、`-08-presets-export`、`-09-presets-import`，各有 `-en`）。不带 `README_IMAGES_SRC` 重跑合成会把旧界面写回去：要么先照上面重拍，要么把新截图放进素材库（先备份旧的）。
- **和旧截图逐像素比**（2400×1500，左栏 x < 408、顶栏 y < 66、状态栏 y ≥ 1458 之外算舞台）：部位页中英舞台 0 个像素不同；纹理、高光粒子、摩尔纹、纹理层页中英舞台只有 155–181 个像素不同，都在细节标题行「回到最密处」那个按钮上（文字变亮），整体图、细节图、分界线逐像素相同；引导页中英舞台各 158705 个像素不同，都在画布上，是横纹和走向线叠加层的画法变了，线的位置和形状没变。重建后「标出问题」的减弱面积是 0.08%。
- **配方的改动：** `#btn-layer-add` 改成面板里的 `#layer-add`，`b1_black.json` 里的 `#btn-strength-auto` 改成 `#strength-auto`；纹理类 8 个配方点完细节位置后先把指针移到状态栏再拍（现在指针停在整体图上会一直显示「点一下，把细节挪到这里」）；`tests\test_readme_recipes.py` 核对配方里写的每个 `#id` 和样式都还在页面里。
- 第 3 节和上面表里说的高光粒子、摩尔纹效果的「强度」，在界面上现在是「亮度」和「明暗」；接口参数名没变。

### 2026-11-20 再次重拍（核对到 51be2fc）

这次的整页图补上顶栏 `?` 快捷键速查表入口，并展示移到预览区的「标出问题」组：行首是短竖色条，纹理减弱和颜色排除的开关各贴着自己的名称和 `?`。引导页仍用点选工具的默认画面；工具选项改存本机用户设置，没有改变这个取景。预设保存时的新说明在弹窗和悬停提示里，不是分享图要拍的内容。

- **重拍方式：** 沿用上面的只读覆盖流程。从工作树用 `models_shot.py` 起独立实例，预设导出、导入用 `preset_files_shot.py` 单独起中、英两个实例，实际导出写入 `out\readme-shots\`，图里仍显示演示用的路径。每个语言、配方都先用 `b1_setup.py` 重建 B1（加 `-B`、设 `PYTHONDONTWRITEBYTECODE=1`）；英文拍摄前将部位改为 Left leg / Right leg。视口 1600×1000：整页原片 DPR 1.5（2400×1500），分享原片 DPR 2（3200×2000）。指针停到状态栏的空白处；除刻意展示导入、导出提示的照片外，拍摄时状态栏没有临时信息。
- **替换的整页图：** `regions-page`、`guides-page`、`texture-page`、`particle-page`、`moire-page`、`layers-page` 各中、英一张。以 `1d5d584` 入库图为基线，按解码后任一 RGB 通道有差异计数：部位、引导页每张不同 13,868–15,361 像素，只在顶栏和左栏（包括部位行本来就显示的求解用时），画布逐像素相同；纹理类每张不同 655,744–732,766 像素，差异主要在预览区（新检查组和整体、细节画布的重新排布），也有顶栏和左栏变化。状态栏右侧的常驻说明片区（成图 x ≥ 1000、y ≥ 972）里，只有中文 `layers-page.jpg` 有差异，10,413 像素：那里是同一句常驻说明、同一位置，只是这一次截图的笔画栅格化略重，不是残留的临时提示；其余 7 张纹理类成图在这一片区是 0。B1 默认密度下的减弱面积仍是 0.08%。
- **预设分享图：** 中、英都重拍了原片，两版成图都保留入库的原图，没有替换。裁出预设区块和状态栏后，中文成图和入库图逐字节相同。英文第一次重拍合成的成图和入库图差 22,335 像素，集中在文字边缘，布局和导入、导出提示不变；之后用 `51be2fc` 再独立重拍一次，以及用 `1d5d584` 的程序在同一环境重拍，各自用同一脚本合成，都和入库图逐字节相同。第一次的差异没有重现，成因没有查明，不当作界面变化。
- **不重拍的局部图：** `show-problems.png` 只从 B2 裁两块细节画布，不带标出问题控件；与其他画布裁图、成品和纹理对比图一起用原素材重合成，逐字节相同。`hook.png` 由另一个脚本生成，不受影响。
- **配方：** 仓库内的配方已无旧 `#btn-check`，不用改；素材库还有旧配方，保持只读。以后若需运行它们，先复制到 `out/`，把打开和关闭标记的步骤换为 `#show-problems` 的勾选和取消勾选，检查其他旧选择器（如 `#check-faded`），并改道输出，不在素材库里改。素材库原始截图仍是旧界面，重合成时须继续使用覆盖目录，不能只设输出路径。

### 移除颜色排除常驻说明后（848c9ab）

沿用上面的只读覆盖流程，在 `out/readme-shots/` 重拍、合成纹理、高光粒子、摩尔纹效果、纹理层的中英整页图，同步移除「颜色排除」下方的常驻小字（运行素材库 Python 脚本仍须加 `-B` 并设 `PYTHONDONTWRITEBYTECODE=1`）。只替换这 8 张 JPG，其余 26 张入库图逐字节不变；素材库原片仍是旧界面，重合成时继续传入覆盖目录。

## 10. 许可和来源（README 或发布说明里可能用到）

- B1、B2 原图由用户的 Anima 模型（SilvermoonMix-Anima-Evolved v2.3，BF16）生成，B5 和 B1 白丝由 GPT Image 生成；都没有特定角色。
- 用户发来的三张示例图（脚踝、折叠腿、躯干）和一张同人参考图（Mika，画师 ttt）只作参考，不进 README，也不进片子。
- 宣传封面里的白丝图是第三方同人图，不是这套素材，来源写在封面的说明里。

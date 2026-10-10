# Stocking texture tool (丝袜纹理工具)

Status: ready-for-agent

A local desktop tool that adds a realistic, moiré-free stocking texture to an illustration, with no agent in the loop. The user paints rough **regions** and a few **guide strokes** in the tool's UI; the tool computes how the **courses** wrap the body, renders the texture in the chosen **style** and **density**, and exports a PSD layer group the user drops into their Photoshop document.

Everything numeric below was measured on the fixtures, now `tests/data/sample-guides.psd` and `tests/data/sample.png` (the Ganyu picture, not distributed). [reference/](reference/) holds working code for every hard part; [reference/verify.py](reference/verify.py) reproduces the numbers. Build the tool from that code, and keep `verify.py` passing as you go.

## Terms

- **art**: the user's painting. From a PNG, or a PSD's composite with the guide group and every layer whose name contains `丝袜纹理` left out.
- **region** (部位): a rough mask for one body part. Every crease gets a region on each side: left thigh, right thigh, crotch, left breast, right breast. One region spanning a crease makes the courses on both sides fold into each other (seen on the fixture before the chest was split).
- **pair**: two regions that mirror each other, named `左…` / `右…`.
- **guide stroke** (走向线): a freehand line along which one course should run. Each connected stroke is one course; 3–5 per region, each spanning about 80% of the region's width.
- **course** (横纹): one row of the knit, an iso-line of `V`. **wale**: the faint perpendicular structure, from `A`.
- **coverage**: where texture may show: regions, minus colours far from the stocking's (gold trim, gloves, hair, skin). The user refines its edge in Photoshop.
- **period**: course spacing in screen px where the guide strokes sit at their median spacing. Strokes that crowd together (a surface receding) carry that perspective into `V`, so the period shrinks there by itself.
- **density** (密度): 100% = 普通 at this resolution (see Density).
- **style**: 细线 (fine threads with skin showing between courses), 针织 (V-shaped stitch loops), 斜单线 (one tilted line family; the reference's 单线亮点), 加濑风 (fine grain + faint knit), 油光 (glossy, experimental). Every style can add sparkles.
- **sparkle map**: where the fabric is stretched (dome tops, the front of each thigh), so sparkles go there.
- **moiré**: courses denser than about 0.33 cycles/px beating against the pixel grid; shows as rings even at 200%.

## User workflow

1. Launch from a desktop shortcut; the UI opens as an Edge app window (`msedge --app=http://127.0.0.1:<port>`).
2. Open a PNG or PSD (drag-drop or dialog). A PSD holding a `丝袜引导` group loads its guides too (`tests/data/sample-guides.psd` is the format).
3. **Regions**: list on the left (add, rename, delete; default five names as above). Tools: SAM click on the current region (left click adds, right click subtracts), brush, eraser. Regions show as colour overlays at about 45%.
4. **Guide strokes**: a 走向 pen. After each stroke the course overlay for that region updates (only the changed region re-solves, about 1 s). A 镜像 button per pair copies one side's strokes onto the other (see Symmetry).
5. **Look**: style, density slider, tilt angle (斜单线 only), strength. Two previews update live: a 100% crop placed where the courses are densest (moiré shows there first), and the whole image fitted to the screen. The UI flags areas where density has pushed courses into the anti-moiré fade.
6. **Sparkles** (every style): from the depth model by default, or from a painted 亮点 layer when present.
7. **Export**, next to the source file, one file per export from a split button (导出 ▾; 成品图 by default):
   - 成品图, `<name>-丝袜成品.png`: the baked result.
   - 仅丝袜, `<name>-仅丝袜.png`: the stockings alone, everything else transparent; laid over the art it gives the baked result.
   - 丝袜引导.psd, `<name>-丝袜引导.psd`: the guides in the fixture's format, so they reopen in the tool or Photoshop.

   The interface is Chinese or English (the Windows display language, or the 中 / EN switch, remembered). File names, the guides PSD's group and layer names and new regions' names follow it; files are read in either language.

   The user's own PSD stays read-only: it holds smart objects and generative-fill layers, and rewriting such a file from Python risks corrupting it.

## Architecture

- **Backend**: Python, FastAPI + uvicorn, one process, state per open document in memory: art, region bitmaps, strokes, solved fields per region, SAM embedding, depth map. Python does all image work so previews and exports come from the same code.
- **Frontend**: plain HTML/JS/canvas, no bundler. Stacked canvases (art, region overlays, strokes, preview), zoom and pan, pointer events. Strokes live as vector polylines (undo, delete one stroke, mirror) and are rasterised 5 px wide for the solver.
- **Project layout**: `D:\Stocking` is the project root (not yet a git repo; `git init` first). Keep the reference modules as the tool's own code (`knit.py` is a snapshot of the `add-stocking-texture` skill's renderer; the tool owns its copy from here on).
- **Install**: `install.bat` creates a venv in the project, installs pinned dependencies, downloads models, places the desktop shortcut. `start.bat` starts the server and opens the app window. Both are English, for the GitHub release.

## Pipeline (reference code)

| step | code | verified on the fixture |
| --- | --- | --- |
| read guides from PSD | `psd_io.read_guides` | art identical to `sample.png`; five regions + strokes read |
| regions + strokes → `V`, normal, `A` | `guide_fields.solve_guides` | 4.4 s for five regions (each solved in its own bounding box); arc length `dA/ds` p10–p90 0.95–1.05 on thighs and breasts; course direction vs a hand-fitted reference: median 2.5° (left thigh), 3.4° (right thigh), 3.6–4.3° (breasts) |
| coverage | in `verify.py` | Lab chroma robust z-score < 6 inside the regions; drops gold trim and gloves |
| render | `knit.render`, `knit.render_lines`, `knit.render_grain`, `knit.add_sparkles` | full image 0.56 s; 512×512 crop 60 ms |
| course phase | `phi = V/period + 0.37*region`, wales `u = A/(period*1.25)` | |
| tilted single lines | `cos θ·V/period + sin(±θ)·A/period`, θ = 32°, + for 左, − for 右 | chevron symmetric by construction |
| mirror strokes | `symmetry.mirror_strokes` | see Symmetry |
| export PSD | `psd_io.write_texture_psd` | re-composite vs baked result: max error 1 level |

Sparkle map from depth (verified visually: bright on dome tops and thigh fronts, dark on the printed bands): Depth Anything V2 (`depth-anything/Depth-Anything-V2-Small-hf`; the tool first used Large, which finds the same walls and nearly the same sparkles but is 13× the download and CC BY-NC) at 1036 px on the short side; per region `smoothstep(p40, p99)` of disparity, times `0.35 + 0.65·smoothstep(0.30, 0.62, value blurred σ6)`, times coverage. Sparkle calls per style are in the `add-stocking-texture` skill's `references/ganyu-example.py`.

SAM: `segment_anything` with `sam_vit_b_01ec64.pth`. Model load 0.6 s, image encode 0.32 s, 28 ms per click on the RTX 4090. With five clicks per region SAM matched the colour-based mask at IoU 0.87; its errors (grabbing gold trim and collarbone skin, missing the crotch) are the ones the coverage step removes.

## Density

`period_px = 4.6 / (density/100) × sqrt(W·H / (1280·1920))`, so the texture looks the same at the same on-screen size. Below 3.2 px, clamp, say so in the UI, and suggest upscaling the image first (common 832×1216 renders land at about 2.9 px). Interpolate the fade band from the period: 4.6 px → `f_lo, f_hi = 0.27, 0.34`; 3.7 px → 0.29, 0.35; 3.4 px → 0.30, 0.36. Slider ticks for the earlier deliveries: 普通 100%, 密 124%, 初版密度 128%, 更密 135%.

## Symmetry

Courses follow whatever the user draws, so lopsided strokes give lopsided texture. Three mechanisms keep a pair matched:

- **Mirror**: draw one side, press 镜像. `mirror_strokes` fits a mirrored similarity transform between the two outlines and maps the strokes across. Thighs: mirrored strokes gave courses within 2.3° (median) of hand-drawn ones; breasts 11°, where both sets look plausible. Mirrored strokes stay editable: real poses are often asymmetric, so mirroring is a starting point, never a constraint.
- **Both sides in view**: the course overlay draws every region at once, so a mismatch is visible as soon as it happens.
- **Tilt as a number**: for 斜单线 the user draws plain courses and the tilt is applied as ±θ per side, so the chevron is symmetric by construction.

## Environment and gotchas

- GPU: `cuda:0` is the RTX 4090 (sm_89), `cuda:1` the RTX 5060 Ti (sm_120). torch 2.11.0+cu128 runs on both (the 4090 through its sm_86 kernels); `sam.pick_device` takes the supported card with the most memory, the 4090. Machines without an NVIDIA card (or with one older than Turing, or a driver before 570) get the CPU build from `install.bat`.
- The global Python 3.10 has a broken TensorFlow, and `transformers` imports it unless `USE_TF=0`. The tool's own venv sidesteps this; leave the global environment alone.
- Non-ASCII paths: `cv2.imread` fails on them; use `knit.load` / `knit.write`.
- psd-tools ≥ 1.24:
  - Set names through the `name` setter: constructor names fail to save non-Latin text.
  - `topil()` ignores layer masks, and psd-tools stores transparency as a mask, so read alpha with `composite(force=True)`.
  - A mask on a group writes a corrupt file. Mask each layer instead.
  - Build layers from RGB images: RGBA layers already carry a mask, and `create_mask` then refuses.
  - `Group.new` defaults to Normal, which isolates blend modes. Set `PASS_THROUGH`.
- Texture as layers: `out = art × f` per channel splits into a Multiply layer (`f ≤ 1`) and a Color Dodge layer (`f ≥ 1`). The group depends only on the ratio, so it survives later edits to the art beneath it.
- Photoshop 2021, 2024 and 2026 are installed. No exported PSD has been opened in real Photoshop yet; ask the user to check the first one.
- The integrated browser tools can drive the UI for testing.

## Build order

Each milestone ends with the user able to try it.

1. **Skeleton.** Launcher, open PNG/PSD, zoom/pan, region brush and eraser, 走向 pen, course overlay. Done when loading `tests/data/sample-guides.psd` in the UI shows courses matching `verify.py`'s solve, and a stroke edit re-solves only its region.
2. **SAM regions.** Click-to-segment per region, coverage overlay. Done when the five fixture regions can be rebuilt with clicks plus touch-ups.
3. **Look.** Styles, density slider with ticks and the 3.2 px floor, tilt, strength, both previews, sparkle map (depth or painted). Done when the slider updates the crop preview without visible lag and the three styles match `verify.py`'s renders.
4. **Export.** 成品图, 仅丝袜 and 丝袜引导.psd. Done when the user lays the 仅丝袜 PNG over their document in Photoshop and sees the same result as the 成品图.
5. **Symmetry and install.** Mirror per pair, `install.bat`, `start.bat`, desktop shortcut. Done when a fresh install on this machine runs end to end from the shortcut.

## Later

- A Photoshop menu entry that runs the tool and places the result in the open document.
- Larger SAM weights (ViT-H, about 2.4 GB) for tighter region edges.

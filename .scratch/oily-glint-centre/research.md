# Does the oily-stocking highlight sit at the visual centre of the leg? (research note)

Prepared 2026-10-09 for the 油光 style, by a research agent working only from pages and PDFs it opened. The maintainer's
question: in real photographs of oily (马油) stockings, is the highlight mostly in the middle of the leg as displayed, are
the edges darker, is there a physical reason, and when does it fail? (Private development note; `.scratch/` is not
published.) The sin(φ/2) rule below was also re-checked independently by the session that saved this note: a 20001-sample
Blinn–Phong (exponent 128) cylinder gives peaks at 0.000, 0.174, 0.342, 0.500, 0.707, 0.866 for φ = 0, 20, 40, 60, 90, 120°.

Tags:
- **[primary]**: a paper, book, standard or manufacturer document I opened and read.
- **[secondary]**: a blog, web guide or encyclopaedia.
- **[inferred]**: my own derivation, checked by the ray-cast numbers under "Formulae".

S-numbers refer to "Sources". No photographs were viewed or downloaded.

## 中文摘要
1. 观察①（高光多在腿的视觉中线）：物理上成立，但"90%+"没有任何来源量化。
2. 原理：高光在法线=光/视半角向量处；圆柱腿上偏离中线=sin(φ/2)×半宽（φ=光与相机绕腿轴夹角）。
3. φ=0/20/40/60/90/120° → 0/0.17/0.34/0.50/0.71/0.87；正面光、环形灯、45°主光(φ≤45°)偏离≤0.38，大柔光箱再把线变宽带，故显得居中。
4. 观察②（边缘更暗）：正面光+暗背景成立：余弦衰减（已证实）+薄织物视线更长（比尔–朗伯，推断，仅最外约13%半宽）；菲涅耳使边缘反射升高，亮暗取决于环境。
5. 暗边不决定高光位置，二者同源；细长主因是圆柱沿轴对称，纱线绕腿时 Kajiya–Kay 锥形高光再加强（针织无测量，推断）。
6. 失效：侧光/条形灯(0.71)、逆光(≥0.92)、窗光、腿朝向镜头(偏到0.59)、椭圆小腿/胫骨嵴随旋转偏0.13–0.26、膝/交叉腿/遮挡使可见中线≠真中线。
7. 建议默认位置0，容差±0.35(最宽±0.5)；有漫反射峰位置u_d时取sin(½·asin u_d)；宽度≈(Δφ/2)·cos(φ/2)。
8. 注意：没有找到统计高光位置的研究，"居中"比例只是物理预期；很多摄影/厂商资料打不开，见 Not verified。
9. 之后又在真实油光黑丝商品图上量过（只有一张图的四段，样本很小）：高光是从大腿到脚踝连续的宽而柔的光带，离腿中线的偏移在大腿上中位数 0.23–0.40 个半宽、一条小腿 0.08，"多半居中"大致成立但不是正中。横截面和对我们渲染的改动见文末最后一节。

## Findings

Definitions used throughout:
- φ is the angle, around the leg axis, between the directions from the leg to the light and to the camera.
- u is the lateral position across the visible width, −1 to +1, measured from the midpoint of the two silhouette edges. This is the maintainer's "visual centre".
- u = ±1 is a silhouette edge.

### Q1. Where the highlight falls on a leg-like body

**F1 [primary] The highlight lies where the surface normal equals the half vector.**
- Blinn 1977, p.192 (S1): "If the surface was a perfect mirror light would only reach the eye if the surface normal, N, pointed halfway between the source direction, L, and the eye direction, E. We will name this direction of maximum hilights H". Page 193 gives the specular term (N·H)^c.
- Blinn's own retrospective (S2) credits Torrance–Sparrow. When N is aligned with H, "the light and eye were in the right position for perfect mirror reflection".
- pbr-book §8.4.4 and Fig. 8.19 (S5): only microfacets "with a normal equal to the half-angle vector" (the normalised ω_i + ω_o) reflect ω_i into ω_o. Rough surfaces give a lobe around that normal.
- Phong 1975, pp.314–315 (S3), uses a different rule that it admits is empirical. It peaks where "s", the angle between the reflected light and the line of sight, is 0, and "no physical justifications are made" for its constants. For light and camera in the plane perpendicular to the axis, both rules peak at the same normal (Table A).

**F2 [inferred, derived from F1, ray-cast verified] On a cylinder with the axis perpendicular to the view, offset = R·sin(φ/2) toward the light.**
- Set up the axis along z, the camera along +x and the screen-horizontal along y.
- The normal at azimuth θ is n = (cosθ, sinθ, 0). That surface point projects to y = R·sinθ, and the silhouettes are at θ = ±90°, so the half-width is R.
- For a light in the plane at angle φ from the view, l + v = 2cos(φ/2)·(cos(φ/2), sin(φ/2), 0), so h points at azimuth φ/2.
- Setting n = h gives θ = φ/2, hence y = R·sin(φ/2). The sign is toward the light's side.
- The Lambert maximum (n = l) sits at θ = φ, i.e. u_d = sin φ. The highlight sits at half that normal angle.
- Orthographic projection of a circular section is symmetric, so the silhouette midpoint is the projected axis and "visual centre" equals the axis.
- Every 10° of change in φ moves the highlight by only 0.06–0.09 half-widths, so the position is robust to the light angle.
- Variants, all checked numerically (Table B):
  - A light elevated by e above the section plane: tanθ = cos e·sinφ/(1 + cos e·cosφ), which pulls the highlight inward.
  - An axis tilted by τ toward the camera: tanθ = tan(φ/2)/cosτ, which pushes it outward.
  - A perspective camera at 20 radii or more shifts it by 0.01 or less.

**F3 [secondary + inferred] Typical φ for common set-ups.**

| Set-up | φ | sin(φ/2) | Basis |
|---|---|---|---|
| On-camera flash, ring light, light on the lens axis | ≈0–5° | 0–0.04 | ring flash "closely and evenly surrounding the optical axis" (S23, secondary); on-camera flash is inferred |
| Large softbox or umbrella beside the camera | 0–25° | 0–0.22, plus band | inferred |
| "45°" key light (softbox, beauty dish) | ≈45° | 0.38 | "main (key) light at 45 degrees in front" (S21, secondary) |
| Window: facing it, or turned 45° to it | ≈0° / 45° | 0 / 0.38 | S22 (secondary): the facing-the-window set-up is called flat and frontal; the "45 Degrees to the Window" set-up is called "Classic Portrait Light" |
| Strip or side light, window perpendicular | ≈90° | 0.71 | inferred |
| Rim or edge light behind the subject | ≈135° | 0.92 | S21: lights "at 45 degrees behind the subject" |
| Backlight (sun or lamp behind) | 135–180° | 0.92–1.0 | S21: "roughly 135-180 degrees from the camera" |

**F4 [inferred; S19, S20 secondary] A large source widens the line into a band.**
- Normals turn at half the rate of the light, so the full width at half maximum (FWHM) is about (Δφ/2, in radians) × cos(φ/2), in half-widths. Lobe roughness adds roughly in quadrature (Table D). Δφ is the source's angular width around the leg axis.
- A 120 cm softbox at 1.5 m has Δφ ≈ 44°, giving about 0.38 half-widths, or ~19% of the visible leg width.
- A vertical 30 cm strip at 1 m has Δφ ≈ 17°, giving about 0.15, or ~7%.
- The same strip lying horizontal gives about 0.5.
- S19: "A larger light source generally produces a larger reflection across a curved surface", and rotating a rectangular softbox from vertical to horizontal made the highlight "wider and less intense" on cylinders.

**F5 [inferred; S13 primary anatomy] Non-circular sections.**
- Anatomy (S13): the tibia's "anterior crest or border, the most prominent of the three… is sinuous and prominent in the upper two-thirds of its extent, but smooth and rounded below". The medial surface "in the rest of its extent… is subcutaneous". The shin therefore has a real ridge covered only by skin.
- Ellipse, depth a over width b, no rotation (Table C): a/b = 1.3 pulls the highlight toward the centre (0.27 at φ=40°, against 0.34 for a circle). a/b = 0.7 pushes it outward (0.46).
- A rotated elliptical calf (a/b = 1.3) at φ=0 sits 0.13 (15°), 0.22 (30°), 0.26 (45°) and 0.22 (60°) off the silhouette midpoint. A circular section never moves.
- Ridge toy model, rounded triangle with crest toward the camera. Illustrative geometry only: it is a pure toy with c = 0.7, ρ = 0.3, not a body model.
  - φ=0–120° gives 0–0.29, and the circle gives 0–0.87.
  - Rotated 20°, it gives 0.41–0.71.
  - So on a ridged limb the highlight follows the crest, not the visual midpoint.

### Q2. Fibre and yarn highlights

**F6 [primary] A cylindrical fibre reflects into a cone, and the image highlight runs perpendicular to the fibre.**
- Kajiya & Kay 1989, "Lighting model for hair", pp.275–276, Figs. 6–8, Eqs. 15–16 (S9): "Any light striking the hair is specularly reflected at a mirror angle along the tangent. Since the normals on the cylinders point in all directions perpendicular to the tangent, the reflected light should be independent of the azimuthal component of the eye vector. Thus the reflected light forms the cone whose angle at the apex is equal to the angle of incidence". They call their specular term "ad hoc".
- Marschner et al. 2003, p.1 (S10): Kajiya–Kay's model "was designed to capture the most obvious feature of scattering from a fiber—namely the appearance of a linear highlight in the image running perpendicular to the fiber directions".
- Marschner et al. 2003, p.2: reflection from a cylinder is "all directed into a cone of outgoing directions", and the surface reflection (R) is "spread fairly uniformly around the cone".
- Irawan & Marschner 2012 (S11): only the abstract was readable. It says the woven-cloth model rests on "an analysis of specular reflection from the fibers" and covers filament and staple yarns. I make no claim about highlight shape from it.

**F7 [inferred] What this means for a stocking.**
- Main reason, with no fibre needed: a leg is nearly a cylinder, so all normals are perpendicular to the axis and the highlight is a line along the axis. Its width is set by source size and roughness (F4).
- Second reason: Kaldor et al. (S12) define the course as "the direction of a single row of loops" (around the leg) and the wale as "the stack of loops" (along the leg).
  - If the yarn tangent is perpendicular to the axis (courses), the cone puts the highlight along the axis. It is present for any light and camera elevation. In my test, with light elevation 30° and camera 0°, the Kajiya–Kay peak stays at 1.000 (position u = 0.317). An isotropic Blinn–Phong lobe with exponent 128 collapses to 0.007, and to 0.000 when both are 30° up.
  - If the tangent is along the axis (wale-direction loop legs), the same physics gives a band across the leg.
  - A plain-knit face has both, so the net anisotropy is unknown, and I found no hosiery measurement.
- Verdict: it is a separate but secondary reason that can reinforce or compete with the macro streak.
- An isotropic smooth lobe keeps half its peak only while the half-vector's elevation stays within acos(0.5^(1/s)). That is 11.9° for exponent 32, 5.9° for 128 and 3.0° for 512. The half-vector elevation is about half of (light elevation + camera elevation).

### Q3. Edge darkening for sheer, glossy stockings

**F8 (a) Lambert cosine fall-off — law [primary], magnitude [inferred].**
- Lambert's law (S7): the energy arriving is proportional to the cosine of the angle between the light direction and the normal.
- For light on the camera axis, diffuse radiance is cosθ = √(1−u²): 0.87 at u=0.5, 0.60 at 0.8, 0.44 at 0.9, 0.31 at 0.95. That is a smooth dome and symmetric.
- For side light the dome peaks at u_d = sin φ, so only the far edge is dark.

**F9 (b) Fresnel [primary equations; table computed] — environment-dependent, not a systematic darkening.**
- S6 (§8.2.1, FrDielectric) gives dielectric reflectance rising toward grazing.
- Rims therefore reflect more of the surroundings, so dark studio gives dark edges and a bright backdrop or window gives a bright rim line. This follows from S6 [inferred].
- Values are in Table E. At n = 1.53 reflectance goes from 4.4% at 0° to 9.4% at 60° and 39% at 80°.

**F10 (c)/(d) Path length and projected fibre density — law [primary], application [inferred].**
- Beer's law (S8, Eqs. 11.1 and 11.3): T = e^(−σ_t·d). A thin layer seen at angle θ has d = t/cosθ.
- For a sparse knit I assume this gives 1/cosθ. A continuous refracting film would cap it near 1.3–1.56. The cap is 1.56 = 1/√(1−1/n²) for n = 1.53, which is an assumed index.
- At the very rim the path through a shell is √(2Rt). For R = 40 mm and t = 0.15 mm (assumed) that is 3.5 mm, about 23 times the thickness.
- Opacity A = 1−(1−A0)^(1/cosθ) (Table F). The effect is confined to the outer ≈13% of the half-width, since 1/cosθ = 2 at u = 0.866.
- (d) "projected fibre density" is the same mechanism counted differently. For an infinitely thin screen the open fraction per projected area stays constant, so the angular effect comes from yarn thickness.
- Measured analogue (S16, p.9): for a woven shade-screen the unscattered transmitted part is "expected to start at the openness and the decrease with increasing angle of incidence". That is a shade screen, not hosiery, and the statement is about model output.
- Luster: S17 (PA6 chip maker) gives "Bright (BR), luminous translucency, TiO2: 0%; Semi-dull (SD), milk white, TiO2: 0.3%; Full-dull (FD), beige white, TiO2: 1.6% (±0.03)". S18 lists nylon 20D/6F–25D/12F yarns in BR/SD/FD. Bright filaments give clean glints, and delustred ones scatter. No source ties luster to angular opacity.

**F11 [inferred] Which mechanism dominates.**
- For frontal-lit sheer stockings:
  - u < 0.7: (a) alone.
  - 0.7–0.9: (a) plus (c)/(d).
  - Above 0.9: (c)/(d) grows to 2.3× or more, and (b) rises above 12% but depends on the environment.
- No hosiery study quantifies this.
- Community stocking shaders use the same idea (S26, secondary): the Fresnel "rims" make the stocking "more like opaque" and the centre transparent.
- Black stockings have little diffuse light, so their edges are dark mostly because little is reflected except at grazing angles.

### Q4. Photography practice

**F12 [primary, not read] Hunter, Biver & Fuqua, *Light: Science & Magic*.**
- Chapter 4 of the 5th edition is "The Management of Reflection and the Family of Angles" (S25, 22 pp.).
- I could not read it. The Taylor & Francis abstract only says the previous chapter covered brightness, color and contrast, and that a subject can "transmit, absorb, or reflect" light.
- I therefore attribute no specific claim to the book. My recollection of "family of angles" as the range of light positions whose mirror reflection reaches the camera is unverified.

**F13 [secondary] Practice statements, all consistent with the F2–F4 geometry but giving no leg or hosiery numbers.**
- S19: source size and orientation control reflection width on cylinders.
- S20: a strip box "doesn't produce a thin strip of light", and used vertically it works "as an edge light".
- S21: rim lights behind the subject, with a dark background showing the rim best.
- S22 and S23: window and ring-flash geometry (F3).
- I found no good hosiery or legwear lighting guide; only retail denier guides turned up.

### Q5. Counter-cases and how often

**F14 [none] No source quantifies how often highlights sit near the centre of glossy legs or cylinders in photographs.**
- I found no published position statistics. My search surfaced only highlight-detection datasets, which I did not open. A search tool's summary claimed they carry no position statistics; that is unverified.
- "Most are central" is therefore a physical expectation, not a measurement.
- Related perceptual evidence:
  - Kim, Marlow & Anderson 2011 (S14): "perceived gloss diminished as the position of highlights became incompatible with the surface's global diffuse shading maxima". Displacing highlights from natural locations reduces gloss.
  - Mamassian & Goutcher 2001 (S15): the assumed light position is above-left, with a leftward bias up to 26°. That is a perceptual prior, not photo statistics.
- Selection-bias warning [inferred]: photos with a prominent oily streak are exactly the frontal-ish set-ups that produce one.

## Formulae and the offset table

Method: orthographic ray-cast of an infinite cylinder, distant light and camera, using `D:\Stocking\.venv\Scripts\python.exe` (Python 3.12.10, numpy 2.5.3). The peak is the argmax over visible columns. The position is (y_peak − y_mid)/half-width, with y_mid and half-width taken from the silhouette edges. Scripts were piped via stdin and no files were written.

**Table 1. Offset versus φ** (n = 1.53 for Fresnel):

| φ | offset sin(φ/2) | F at the highlight | Lambert peak u_d |
|---|---|---|---|
| 0° | 0.000 | 0.044 | 0 |
| 20° | 0.174 | 0.044 | 0.342 |
| 40° | 0.342 | 0.044 | 0.643 |
| 60° | 0.500 | 0.045 | 0.866 |
| 90° | 0.707 | 0.054 | 1.0 |
| 120° | 0.866 | 0.094 | rim (light behind the limb edge) |

Inverse table: offset ≤ 0.25, 0.33, 0.5, 0.71 corresponds to φ ≤ 29°, 38.5°, 60°, 90°.

**Table A. Ray-cast peak versus prediction:**

| φ | 0 | 20 | 40 | 60 | 90 | 120 | 150 |
|---|---|---|---|---|---|---|---|
| sin(φ/2) | 0.000 | 0.174 | 0.342 | 0.500 | 0.707 | 0.866 | 0.966 |
| Blinn–Phong s=32, 128, 512 | identical to prediction to 3 decimals | | | | | | |
| Phong R·V, s=128 | identical | | | | | | |
| Blinn–Phong × N·L, s=128 | 0.000 | 0.175 | 0.345 | 0.504 | 0.713 | 0.873 | 0.973 |
| GGX+Smith+Fresnel, α=0.10 | 0.000 | 0.174 | 0.343 | 0.501 | 0.709 | 0.868 | n/a |
| GGX+Smith+Fresnel, α=0.30 | 0.000 | 0.178 | 0.351 | 0.513 | 0.725 | 0.888 | n/a |

**Table B. Variants** (measured values agreed with the formulas to 0.001):

| Variant | φ=40° | φ=90° | φ=120° |
|---|---|---|---|
| Light elevated 30° | 0.317 | 0.655 | 0.798 |
| Axis tilted 30° toward camera | 0.388 | 0.756 | n/a |
| Axis tilted 60° toward camera | 0.589 | 0.895 | n/a |
| Perspective, 6 radii | 0.366 | 0.745 | n/a |
| Perspective, 20 radii | 0.350 | 0.719 | n/a |
| Perspective, 40 radii | 0.346 | 0.713 | n/a |

**Table C. Elliptical section, depth a over width b**, offsets at φ = 20°, 40°, 90°:
- a/b = 0.7: 0.244, 0.462, 0.820
- a/b = 1.0: 0.174, 0.342, 0.707
- a/b = 1.3: 0.134, 0.270, 0.610
- a/b = 1.6: 0.110, 0.222, 0.530

**Table D. Source width: FWHM in half-widths** (band centre = sin(φ0/2); for symmetric sources the argmax jitters by ±0.06 on a flat top, so use the band centre):

| Δφ | φ0=0° | φ0=45° | φ0=90° |
|---|---|---|---|
| 0°, s=128 | 0.207 | 0.191 | 0.147 |
| 15°, s=128 | 0.228 | 0.210 | 0.161 |
| 15°, mirror | 0.134 | 0.124 | 0.094 |
| 40°, s=128 | 0.365 | 0.337 | 0.258 |
| 40°, mirror | 0.355 | 0.329 | 0.251 |
| 70°, s=128 | 0.616 | 0.569 | 0.436 |
| 70°, mirror | 0.616 | 0.569 | 0.436 |

**Table E. Fresnel reflectance F(θ)**, with θ from the normal:

| n | 0° | 45° | 60° | 70° | 80° | 85° | 89° |
|---|---|---|---|---|---|---|---|
| 1.47 | 0.036 | 0.046 | 0.084 | 0.165 | 0.382 | 0.609 | 0.903 |
| 1.53 | 0.044 | 0.054 | 0.094 | 0.176 | 0.392 | 0.616 | 0.905 |
| 1.58 | 0.051 | 0.062 | 0.102 | 0.185 | 0.399 | 0.620 | 0.906 |

Position across the half-width, with u = sinθ:

| u | θ | cosθ | F (n=1.53) | 1/cosθ |
|---|---|---|---|---|
| 0.5 | 30° | 0.87 | 0.045 | 1.15 |
| 0.7 | 44° | 0.71 | 0.054 | 1.40 |
| 0.8 | 53° | 0.60 | 0.069 | 1.67 |
| 0.866 | 60° | 0.50 | 0.094 | 2.00 |
| 0.9 | 64° | 0.44 | 0.119 | 2.29 |
| 0.95 | 72° | 0.31 | 0.202 | 3.20 |
| 0.98 | 78.5° | 0.20 | 0.346 | 5.03 |
| 0.99 | 82° | 0.14 | 0.464 | 7.09 |

**Table F. Beer–Lambert opacity** A(u) = 1−(1−A0)^(1/cosθ):

| A0 | u=0 | 0.5 | 0.7 | 0.866 | 0.95 | 0.985 |
|---|---|---|---|---|---|---|
| 0.1 | 0.100 | 0.115 | 0.137 | 0.190 | 0.286 | 0.457 |
| 0.3 | 0.300 | 0.338 | 0.393 | 0.510 | 0.681 | 0.873 |
| 0.5 | 0.500 | 0.551 | 0.621 | 0.750 | 0.891 | 0.982 |

## When the observation fails

1. **Side, strip or window light:** φ = 90° gives 0.71 and φ = 120° gives 0.87. Backlight at 150° or more gives 0.97 or more, a rim line on or beyond the edge.
2. **A single hard light at 90°:** the highlight sits at 0.71, and the Lambert maximum is at the rim. The lit edge is the brightest and the far edge is dark, so "darker edges" fails on the lit side.
3. **Very large or close sources:** a Δφ of 70° gives a FWHM of 0.6 half-widths at φ0=0. That is a sheen over the central half, not a streak.
4. **Elevation mismatch:** for a smooth upright cylinder the highlight needs light elevation + camera elevation ≈ 0, within about 2·acos(0.5^(1/s)) (about 12° at s=128). A high light with a level camera shows none. Tall sources and circumferential yarn make it robust (F7).
5. **A leg pointing toward the camera** (axis tilted 30° or 60°): the offset is multiplied by about 1.1 or 1.7 at φ=40°.
6. **Non-circular or rotated sections:** a calf with depth/width 1.3 rotated 15–60° shifts the φ=0 highlight by 0.13–0.26. A ridged shin pins it to the crest.
7. **Knee and bends:** the axis direction changes, so the streak breaks and the centreline bends. The patella is a separate high-curvature blob. Not quantified.
8. **Crossed legs, clothing, hands:** an occluder cuts one silhouette edge, so the visible midpoint is not the true axis. With half the leg hidden the error is 0.5 of the true half-width [inferred].
9. **Bright surroundings:** rims brighten (Fresnel), so "edges darker" fails. A backlit nude leg can show a rim glow.
10. **Close camera:** at 6 radii or less the shift is up to 0.04 (F2).

## Implications for the renderer

All of these are [inferred] from the findings above unless a source is named. The repo already does much of this: `stocking/oily.py:3-4, 13-19, 80, 434, 671-674` builds facing = √(1−u²), reads the light across the limb, and applies `(1−facing)^1.5` darkening.

1. **Default position and window.**
   - Use u_h = 0 on the whole-limb centreline as the mode. Treat |u| ≤ 0.35 (φ ≤ 40°) as the expected window and ≤ 0.5 (φ ≤ 60°) as the tolerance.
   - Allow up to 0.7 when the painted brightness shows a side light. Allow 0.9 or more only with rim evidence.
   - Put the highlight on the side of the brightness maximum.
2. **Use the lighting estimate when the image gives one.**
   - If the diffuse peak is at u_d, set u_h = sin(½·asin u_d), which is about u_d/2. Examples: u_d = 0.5 gives 0.26, 0.7 gives 0.38, 0.9 gives 0.53, and 1 or more gives 0.71 or more.
   - Kim et al. (S14) support keeping the highlight inside the lit region.
3. **Width.**
   - FWHM (in half-widths) ≈ √(w_rough² + ((Δφ/2)·cos(φ/2))²), with w_rough ≈ 0.2 at s≈128 (0.10 at s=512, 0.41 at s=32).
   - A typical softbox gives 0.35–0.6, and a strip gives 0.13–0.23.
   - Scale the width with the local half-width h(V) so it tapers with the leg.
4. **Brightness toward the edge.**
   - Do not dim the glint toward the edge just because the leg is darker. The diffuse light falls but the specular does not: F is about 4.4–5.4% for |u_h| ≤ 0.7 and above 12% only for |u_h| > 0.9.
   - Base falloff is cosθ. Stocking density follows A = 1−(1−A0)^(1/cosθ) with 1/cosθ capped at about 6–10.
   - The current `(1−facing)^1.5` matches the normalised Beer–Lambert gain for A0 ≈ 0.3 within 0.07 across u = 0.3–0.985. It over-darkens very sheer stockings (A0 ≤ 0.1, where the gain reaches only 0.4 at the rim) and under-darkens dense ones (A0 = 0.5). Tie the exponent to measured stocking darkness or denier.
5. **Continuity.**
   - Draw the glint as one continuous ribbon along the limb, at a constant lateral offset u_h·h(V) from the centreline c(V).
   - Break it at the knee, ankle, hip or a hem. Allow fades but not random gaps.
   - A smooth isotropic lobe predicts gaps under elevation mismatch, but tall sources and circumferential yarn keep the streak long (F7).
6. **Non-circular or foreshortened limbs.**
   - Add a ±0.15–0.25 tolerance on u_h for a rotated calf or shin.
   - Allow the glint to snap to a detected ridge, such as the shin crest, when the painted brightness shows one.
   - For a limb pointing toward the camera, push u_h outward (about 1.1× at 30° tilt, 1.7× at 60° at φ=40°) and clamp at 1.
7. **Occlusion.** Take c(V) and h(V) from the whole-limb outline extended through occluders, not from the visible mask. The current frame code already measures a side from the other when an edge meets the frame or a wall (`stocking/oily.py:13-16`). Place the glint relative to the true axis and let the occluder cut it.
8. **Presets and validation.**
   - Offer presets: frontal soft at 0 with a wide band (0.4–0.6); 45° key at 0.35 with a medium band (0.3); side or strip at 0.7 with a narrow band (0.15–0.25); rim at 0.9–1.0 with a narrow band.
   - Check the "90%+" claim by measuring u_h = (x_h − c)/h on 50–100 photos. No published number exists.

## Sources

- **S1 [primary]** J. F. Blinn, "Models of Light Reflection for Computer Synthesized Pictures", SIGGRAPH '77 (Computer Graphics 11(2)), pp.192–198, 1977. https://www.microsoft.com/en-us/research/wp-content/uploads/1977/01/p192-blinn.pdf — p.192 (definition of H), p.193 (N·H power).
- **S2 [primary]** J. F. Blinn, author's note on the Microsoft Research publication page, same title. https://www.microsoft.com/en-us/research/publication/models-of-light-reflection-for-computer-synthesized-pictures/
- **S3 [primary]** B. T. Phong, "Illumination for Computer Generated Pictures", Communications of the ACM 18(6):311–317, 1975. https://users.cs.northwestern.edu/~ago820/cs395/Papers/Phong_1975.pdf — "Using a Physical Model / Specular Reflection", pp.314–315.
- **S4 [primary, not opened]** K. E. Torrance & E. M. Sparrow, JOSA 57(9):1105–1114, 1967. Cited only through S2 and S5.
- **S5 [primary]** Pharr, Jakob & Humphreys, *Physically Based Rendering*, 3rd ed., 2018, §8.4.4 "The Torrance–Sparrow Model", Fig. 8.19. https://pbr-book.org/3ed-2018/Reflection_Models/Microfacet_Models
- **S6 [primary]** Same book, §8.2.1 "Fresnel Reflectance" (FrDielectric). https://pbr-book.org/3ed-2018/Reflection_Models/Specular_Reflection_and_Transmission
- **S7 [primary]** Same book, Ch. 5 "Radiometry" (Lambert's law, Fig. 5.7) https://pbr-book.org/3ed-2018/Color_and_Radiometry/Radiometry, and §8.3 Lambertian reflection.
- **S8 [primary]** Same book, §11.1 (Eq. 11.1 transmittance, Eq. 11.3 Beer's law). https://pbr-book.org/3ed-2018/Volume_Scattering/Volume_Scattering_Processes
- **S9 [primary]** J. T. Kajiya & T. L. Kay, "Rendering Fur with Three Dimensional Textures", Computer Graphics 23(3), pp.271–280, 1989. https://www.cs.drexel.edu/~david/Classes/Papers/p271-kajiya.pdf — "Lighting model for hair", pp.275–276.
- **S10 [primary]** Marschner, Jensen, Cammarano, Worley & Hanrahan, "Light Scattering from Human Hair Fibers", ACM TOG 22(3) (SIGGRAPH 2003). https://www.cs.cornell.edu/~srm/publications/SG03-hair.pdf — §1 (p.1), p.2.
- **S11 [primary, abstract only]** Irawan & Marschner, "Specular Reflection from Woven Cloth", ACM TOG 31(1), 2012. https://www.cs.cornell.edu/~srm/publications/TOG12-cloth.html (DOI 10.1145/2077341.2077352; closed access).
- **S12 [primary]** Kaldor, James & Marschner, "Simulating Knitted Cloth at the Yarn Level", SIGGRAPH 2008. https://www.cs.cornell.edu/~srm/publications/SG08-knit.pdf — p.3 and Fig. 2.
- **S13 [primary]** H. Gray, *Anatomy of the Human Body*, 1918, "The Tibia", Bartleby edition. https://www.bartleby.com/107/61.html
- **S14 [primary]** Kim, Marlow & Anderson, "The perception of gloss depends on highlight congruence with surface shading", J. Vision 11(9):4, 2011. doi:10.1167/11.9.4 (PMID 21841140).
- **S15 [primary]** Mamassian & Goutcher, "Prior knowledge on the illumination position", Cognition 81(1):B1–B9, 2001 (PMID 11525484).
- **S16 [primary]** Jonsson, Lee & Rubin (LBNL), "Light-scattering properties of a woven shade-screen material used for daylighting and solar heat-gain control", venue and year not confirmed from the PDF (c. 2008). https://digital.library.unt.edu/ark:/67531/metadc902743/m2/1/high_res_d/936585.pdf — p.9.
- **S17 [primary, manufacturer]** Fortune Cat, PA6 nylon chip page (TiO2 0 / 0.3 / 1.6%). https://fortunecatfibers.com/products/engineering-plastic-grade-pa6-nylon-chip/
- **S18 [primary, manufacturer]** Kayavlon nylon FDY catalogue (BR/SD/FD). https://www.kayavlon.com/nfdy.htm
- **S19 [secondary]** Society of Photographers, "How to Light Glass Bottles". https://thesocieties.net/blog/2024/04/18/how-to-light-glass-bottles-photography-lighting-for-shiny-surfaces/
- **S20 [secondary]** ISO 1200 summary of Gavin Hoey's stripbox video. https://www.iso1200.com/2024/02/the-ultimate-stripbox-guide-by-gavin.html
- **S21 [secondary]** PhotoWorkout, "Rim Light Photography". https://www.photoworkout.com/rim-light-photography/
- **S22 [secondary]** DailyPhotoTips, "Window Light". https://dailyphototips.com/lighting/window-light/
- **S23 [secondary]** Wikipedia, "Ring flash". https://en.wikipedia.org/wiki/Ring_flash. A pointer only, as is "Specular highlight" https://en.wikipedia.org/wiki/Specular_highlight
- **S25 [primary, not read]** Hunter, Biver & Fuqua, *Light: Science & Magic*, 5th ed., Routledge/Focal Press, 2015, Ch. 4 (22 pp.). https://uat.taylorfrancis.com/chapters/mono/10.4324/978131586397-4/management-reflection-family-angles-fil-hunter-steven-biver-paul-fuqua (abstract page only).
- **S26 [secondary]** Blatke, "Silk Stocking Shader for ME", README. https://github.com/Blatke/Silk-Stocking-Shader-for-ME
- **S27 [primary, not opened]** IUPAC Gold Book, "Beer–Lambert law". https://goldbook.iupac.org/terms/view/B00626 (HTTP 403, Cloudflare challenge). The law is taken from S8 instead.
- **Repo context (read-only):** `stocking/oily.py:3-4, 13-47, 80, 434, 671-674`.

## Not verified

- Several pages could not be opened, and I did not work around any challenge: ACM DL, ScienceDirect, MDPI, escholarship, O'Reilly, Taylor & Francis (full text), IUPAC, B&H, Canon and ligum.umontreal.ca (an anti-bot challenge). One more could not be read in usable form: the Ward 1992 anisotropic-reflection paper (only page scans).

## The glint across a divider (the kneeling picture, `b2-black-fold`)

Report: on a kneeling picture the glint ran from the calf onto the thigh across the divider (隔开线). Reproduced offline from the user's own document (art, masks, strokes, divider, read through the GET endpoints of his instance and rebuilt in `Document`: `files\user_case.py`, 2048x1344, one region = thigh + calf, one wall of 13k px).

Cause (measured, not guessed). The wall does not reach the outline at its left end (the knee; the solver flows the courses round such an end on purpose) and eats the thigh's tip at the right, so the region is ONE connected piece for `oily_maps`. V and A are one coordinate system: thigh and calf are two strips side by side in A, so at one V the cross-section is thigh + wall + calf. `_frame`, `_lighting`, `_tracks` and `_floor_glint` read it as one limb: its middle (where the floor glint goes) is on the wall, the calf's own painted highlight is averaged with the thigh pixels of equal A, and `_curve` places a row's glint at the MEAN screen position of the pixels at the glint's A, which, where both strips have that A, lies between them, on the wall. The glint ran along the wall for about 150 px, up the thigh, and out to the shoe.

Fix, after one review (the first duck round was lost to a failed model connection; the second took the brief of the prototype and answered in half a minute). (1) `_closed_cut`: the free ends of each wall are carried on straight (direction: `walls._ends`, a PCA of the band's last stretch) to the outline of the region, to another wall or to an earlier line, within twice the greatest half-width; specks and short walls are left alone; a ray that finds nothing draws nothing. (2) `oily_maps` runs a region with a closure in two passes: 'look' with the walls as drawn (facing, zones, tone), 'glint' with the closed walls (core, band, tail, centre only). A first prototype used the closed walls for everything: the thigh's left half has region 2 above it and the wall below, both edges "hidden", so `_frame`'s trust flickered 0 / 0.5 band by band (vertical stripes and a slanted seam in the zone map) and `whole` was False, so no floor there. The duck's recommendation (a): keep the look from the unsplit frame, give the strands their own lighting, and read the floor's strength from the look's zone map (the mean over each band of the strand). Option (b) globally (the wall edge as a silhouette) it advised against: a divider says nothing about the limb's width. In the glint pass the wall is simply not "hidden" (nothing says the limb is wider behind it either), so a strand with a wall along its whole length (the calf) is still measured whole and gets a floor. (3) `_outside`: a glint's path is cut where it enters another piece of the region, so that nothing is drawn across a wall even where the closing did not part the two.

Result on the user's picture: nothing crosses the wall; the thigh's glint runs from the knee to the peak and down the thigh's right edge; the calf has its own glint (the artist's highlight plus the floor) down to the shoe; no stripes in the zones. On the 16 cached pictures `tone`, `facing` and `zone` are 0.000 different; the glints changed only on the three versions of this picture whose divider stops short (`9ae0628e`, `e45242d8`, `user_fold`).

Checks: the full suite (8 new tests: the closed walls, the look as drawn, a speck/blob/short wall left alone, a wall ending on another and on an earlier line, a path in another piece lighting nothing, `_outside`); 19 mutants of the new mechanisms (the ones that live: the wall-as-edge choice in the glint frame, the seam copy of the glint role, which no synthetic leg makes visible; on the real picture the first is worth about 1280 px of floor); 1500 random legs with random walls (long, slanted, across, T, specks, short) through `oily_maps`: finite, in range, drawn on painted pixels only, the look bit for bit as drawn, and, where the closing parts the leg, brightening one piece changes nothing of the glints on the others (the invariant that says light does not cross a wall).
Limits: the extension is a straight line along the last 20-30 px of the wall, so a wall whose end curves is closed a little off.

**The kneeling picture's course lines are not perfect (the maintainer, 2026-10-10).** Much of what looked wrong on it came from its course lines, not from the glint: the other pictures, with their own lines, are right. Do not use it as the benchmark of the oily glint, and do not add machinery for it alone (the bridge below was one, and was taken out). What this picture's field is: V is highest at the knee and falls toward the hip and the foot, so each V row cuts the thigh and the calf; the field is connected round the knee end only.

Second round (the same picture, the user's next screenshots): the light was cut along the closing line (a hard straight edge: the calf strand's lobes stop at the piece boundary, nothing on the thigh side). The closing is for the light's fit, not a wall: `_reach` lights the pixels of the other pieces near a closing line (`wall & ~cut`) with this strand's lobes (distance to its curve, the half-width where they lie as the strand's own pixels have it: with the median a 24% step showed up on the tail), times the visibility of the nearest curve point over the real wall band (`_shadow`: the wall blurred, sigma 8 px, times 10 and clipped: the duck's blocker was that the plain blur let 78% of the light through a wall one pixel thick; a first version tested sight binary and the shadow edge cast from the wall's tip showed as a thin diagonal needle). A cKDTree over a 0.25 px polyline is slow (every 4th sample: 1.9 s to 0.3 s). `oily_maps` on the 2048x1344 picture: 2.0 s, 2.7 s with the spill.
A bridge was built, reviewed and then taken out. The user had said the glint should not go round the knee because a line is drawn there, but because the courses do; a hand-made Bezier between the two glints' ends (`_joins_at_ends`, `_bridge_path`, with a strength run from one end's to the other's) is a patch for one kneeling pose whose course lines are not perfect (the user's words: many of the problems come from that pose's course lines; the other pictures are right). What stays: the real wall stops the light, the closing line does not, nothing is drawn to join the two sides.
What the experiments on the way showed, for a later proper redesign (the duck's recommendation was a graph of cross-section strands, a deep change of tracker, fit and draw, with a terminal-or-open policy for each wall end): on this picture V is not monotone along the folded leg (V is highest at the knee and falls toward the hip and the foot, so every V row cuts the thigh and the calf), the field is connected round the knee end only (with the knee end removed the thigh and the calf are two pieces of 23k px each), and the main glint's path in the unsplit region jumps from the thigh's tip to the calf's top edge across the wall's closed end, by interpolation between rows, not by the field.
Checks of the second round: 189 tests in `test_oily.py` after the bridge was taken out; mutants of the closing and the spill (only the wall-as-edge choice lives); 1500 random legs with random walls, with the metamorphic property taken with `LIGHT_ACROSS_LINE` off (the spill is exactly where the pieces meet); the 16 cached pictures: tone, facing and zone 0.000 different, glints changed only on the three versions of this picture.
The duck's review of the second round: the blurred wall density alone let 78% of the light through a wall one pixel thick (blur peak .05 at sigma 8, never the 2/3 that blocked): `_shadow` scales the blur by 10 before clipping, and the line of sight is sampled in 24 steps (a test with a one-pixel and a twelve-pixel wall, and one with a wall's end for the penumbra). The rest of its questions (spills overwritten by a later piece, the cell key with a width not divisible by four, short curves) it found sound.
- So I did not read *Light: Science & Magic* text, Irawan–Marschner 2012 beyond its abstract, Torrance–Sparrow 1967, or Poulin & Fournier 1990.
- Nylon's refractive index (about 1.52–1.58) is not confirmed from an opened table. The 1.47 value is an assumed mineral-oil figure. The Fresnel results are not very sensitive to it (F0 of 3.6–5.1%).
- I found no hosiery-specific study of opacity versus viewing angle or cover factor, no measurement of knit yarn direction or anisotropy, and no highlight-position statistics. The 90% figure is neither supported nor refuted.
- The ellipse ratios, the ridge geometry, the A0 values, the fabric thickness (0.15 mm) and the softbox sizes are illustrative assumptions.
- The search tool's AI summaries were never used as evidence. Two of them contradicted each other on whether Irawan–Marschner highlights run along or across the yarn. Every claim above comes from a page or PDF I opened.

## What this session did with it (oily.py, automatic centring)

- First tried as a slider (`centre`, 0–85%, a window of ±W half-widths that took glints outside it away). The maintainer rejected it: the highlight has to be automatic. It was removed; nothing of it remains in the settings, the UI or the presets.
- Now automatic and not hard-coded to the middle (`oily._centre`). The painted light across a leg is often a broad flat top with shallow bumps and ledges a few grey levels apart, so *which* bump is the highest (and so where the glint goes) is the brushwork's chance, and the glint wandered between them (the PSD that started this: a central ledge with a slightly higher bump off to the side). Of the places level with a glint's top (a local maximum of the light within `LEVEL` = 0.05 luminance of it, above or below, with no dip deeper than `RIDGE` = 0.025 between: one top, not two ridges; the dip limit is `PROM[0]`, the least a peak must stand out to be a glint at all, so a lower side that deep would be a light of its own) the glint now takes the most central one, along one continuous path no faster than a glint moves (a Viterbi pass per glint; cost = distance from the middle, with none inside `CENTRAL` = 0.35 half-widths). A top standing more than `LEVEL` above every such place, a glint already near the middle and a glint painted off to one side with nothing level beside it all stay where the light puts them, so a highlight the artist painted off-centre is followed as before. This is the note's "expected ≤ 0.35" window used as a preference among equal places rather than a wall, which is what the maintainer's suggestion 1 (limit to the middle first, with a contrast threshold so a strong off-centre highlight is not thrown away) comes to; taken literally (cut the range first, then find peaks) it fails on the PSD, where the central bump is only a ledge (prominence 0.001–0.008, under the 0.0125 a peak needs) and has no peak inside a restricted range.
- Suggestion 2, the wales: the middle is measured in the courses' own across coordinate A (which the wales follow), from the visible centre line c(V), so a bent leg's middle bends with it.
- A moved glint is the same glint: it keeps its strength, light and sureness (which of its rows its brightness is read from), so moving it neither brightens nor dims it (a first version took the new place's own light and could nearly extinguish a glint on an evenly lit leg; a second took its support and, where the new place was thinly supported, left the dim rows out as sources and came out at full strength there). Where putting the pieces of a glint on one line heals a cut that a hand-over could not bridge, it is one glint from then on: no fade at the old cut, one brightest point to measure against (the only per-row strength change on the real pictures: 12287231, at most 0.27 on one row).
- A glint that went on unseen anywhere (its place out of sight for some rows: trim, a hand, a dress) is not moved at all, and neither is one that shares a row with such a glint. Moving only the rows around such a gap bends the smoothed curve through it into rows in plain view where the light has no peak; the linker's 'out of sight' test (a window of the glint's uncertainty, ~half the lobe's width on a flat top) cannot vouch for a new place; and the curve is drawn through those rows wherever the smoothing puts it, so another glint centred nearby could land on top of it (a reservation of the interpolated path did not cover that). On the 17 pictures this costs one faint node in one piece.
- Where no cross-section of a piece is seen whole (e.g. a leg cut off by the image frame all down one side) the centre is only assumed, and nothing moves there.
- Result on the maintainer's PSD: the left calf's glint is one straight central line from knee to ankle (before: a stub at the side and a diagonal back to the middle). Across 33 pieces of 17 pictures 6 change, none gets a bigger row-to-row step (one loses a 15-cell zig-zag), total glint mass unchanged.
- Not done, deliberately: moving glints by the note's `u_h = sin(½·asin u_d)` (the painted highlight the model follows is already the artist's glint, not the diffuse peak), presets per light set-up, and taking the centre line through occluders (the maintainer asked for the *visual* centre as displayed; where a dress hides part of the limb the visible midpoint is biased by up to ~0.3 half-widths, which the preference tolerates).
- The note's continuity advice ("one continuous ribbon... break it at the knee") fits what the model does at a dim knee: the glint fades out and in along one line rather than jumping sideways.

## What this session did with it (oily.py, the gloss lobe after real photos)

The maintainer then showed Google image-search results for 油丝 黑丝 and 油丝 白丝 and asked what real glossy stockings look like, black ones above all (far more used). About ten product photos of black tights were saved and looked at; the numbers below come from one of them (two legs standing on a plain background: the thigh and the shin of each leg, four stretches of rows), the rest were compared by eye. It is a very small sample.

- **What they look like:** the highlight is a continuous broad soft band from thigh to ankle, not a line. Its contrast fades smoothly down the leg (about 100 grey levels at the thigh, 30–50 on the shin, about 10 at the ankle) rather than breaking. Its offset from the leg's visible centre is a median of 0.23–0.40 half-widths on the thigh and 0.08 on one shin: mostly central, not exactly (a first look at the "90%" question; one photo is no statistic).
- **Cross-section** (value of (v − base)/(peak − base), which is `bright / bright_max` because `out = 255 − (255 − base)(1 − bright)` is linear; against the distance from the peak in half-widths of the leg):

  | distance | 0 | 0.1 | 0.2 | 0.3 | 0.4 | 0.5 | 0.6 | 0.8 |
  |---|---|---|---|---|---|---|---|---|
  | real | 1.00 | 0.58 | 0.37 | 0.28 | 0.23 | 0.18 | 0.14 | 0.08 |
  | our lobes before | 1.00 | 0.25 | 0.12 | 0.08 | | 0.03 | | 0.01 |
  | our lobes now | 1.00 | 0.57 | 0.36 | 0.28 | 0.22 | 0.17 | 0.13 | 0.07 |

- **The fit:** core gaussian σ 0.064, band gaussian σ 0.54, exponential tail 0.20 (half-widths), weights 0.31 / 0.20 / 0.39 (sum 0.90, the peak brightness the old weights had, so full strength is as bright as before). `oily.py`: `CORE_REL, BAND_REL, TAIL_REL`, `W_CORE, W_BAND, W_TAIL`. The widths are a share of the limb's half-width where the glint is (`h[k]`, the A-units half-width, close to px for an upright leg), times 0.8–1.6 where the painted highlight is broad, never below 1.5 / 4 / 3 px (times the image's scale): a thigh gets a broad glint and an ankle a narrow one, as in the photos. (An earlier version kept a 14 px floor on the tail: it decided the tail in 11 of the 37 pieces of the 17 pictures, up to 3× the fitted length on narrow limbs, so it is now 3 px.)
- **Why the old line looked broken:** its core was σ ≈ 1.5 px, so nearly all of it counted as "flank", and the flank of a glint is where the courses' texture shows through (`1 − flank·0.55·(1 − tex)`): the line was cut into dashes. The texture's grip on the flanks is now 0.15 (core) and 0.25 (band). `SPEC_EXP` went from 6 to 3: a 6th power turns a ±10% wobble of the painted light into ±50% of the glint's strength. And the path may stray `TOL_REL` = 0.07 half-widths from the painted peaks (a painted highlight's wobble is no wobble of a real one).
- **Checks:** the PSD's left calf at strengths 35 / 60 / 100 / 150 (the old line is a faint, broken string at the low ones, the new band continuous at every one), five dark-stocking pictures and the PSD side by side with the old code, 1500 fuzzed fits through `_tracks` (SPEC_EXP the same in both versions: still no difference with `middle=None` and no invariant broken), and `tests/test_oily.py`: the cross-section on a 160 px and a 60 px leg to within 0.03 and the glow's breadth against the leg's. Both fail with the old thin-line lobes, and the 60 px one with the old 14 px tail floor.
- **Not done:** where the art has no highlight, the glint is absent (the PSD's knee, rows ~365–737, where the thigh and the calf are separate pieces too); in the photos the band runs on across the knee. The model follows the painted light and invents none, so carrying a glint across such a gap (fading through it) would be a new rule between pieces. Offered to the maintainer, not built.

## The maintainer's redesign idea: find the highlight line with the longitudinal flow lines, zone the leg with them

After the lobes the maintainer, looking at the photos, said the oily style should be rebuilt: on real ones there is a thin bright line at the centre facing the light, pale colour around it and black leg edges; and since this project is about flow lines, find that line from the longitudinal flow lines and the painted highlight (the flow line that overlaps the highlight most? several?), then use the longitudinal lines to zone the leg: where it is pale, where the edge is dark.

**The line, tried and not adopted.** The glint is already found in the wale coordinate: the light is fitted per row of V in cells of A and the peaks are found across A (`u = (A − c) / h` in half-widths of the limb); a glint is a track of those peaks. What was tried (a throwaway prototype in the session folder, not in the repo): take every peak of a piece, vote for the constant-u line (a gaussian histogram of the peaks' u, sigma 0.07), pick the most central of the lines within 80% of the best, optionally a second line, and run the glint along it for the piece's length, its strength per row the nearest painted peaks' strength interpolated across gaps. On the 38 real pieces (17 pictures) the chosen line covers the painted peaks within 0.15 half-widths with a median of 71% of their weight (20th percentile 32%); the main current track deviates from the best constant-u line by a median 0.22 half-widths (80th percentile 0.49), a quarter of the pieces having a painted highlight that itself wanders by sigma 0.2–0.3 (a calf with muscle bulges, a kneeling thigh); on the PSD the line is one band from thigh to ankle and the knee gap is gone; the row-to-row jog of the line's path (the frame's centre and half-width jump where a side is hidden) was 3.3 cells at worst, 2.0 after smoothing the path. The rubber-duck review found it unsound as a replacement, and the numbers agree:

- constant u should be a prior, not a constraint: a highlight that meanders beyond the vote's reach becomes two partial tracks (a synthetic one did), and noisy c(V) / h(V) where a side is hidden bends the line; it is also not an iso-A wale (`A(V) = c(V) + u·h(V)` follows the silhouette, which is the better optical model but not a fabric line);
- interpolating votes invents a glint across a visible unlit gap (strength 0 now, 0.30 in the prototype for a 16-row gap between two equal highlights), and its votes were the already processed tracks (padding, smoothing, carried rows), 16 zero-support rows among them, which it then marked as fully sure; a replacement would have to vote with the measured peaks and keep support, width and positional uncertainty;
- histogram mass favours long lights over short ones (a 60% second-line threshold and a 0.35 half-width exclusion erase a genuine shorter light or a close one), and a second mode is not a second lamp (one wandering highlight makes one);
- with the prototype installed 4 of 18 selected regression tests fail (hair-shadow strips, occlusion identity, short domed arcs, two lights).

So the tracker stays; what the idea got right, and the tracker lacked, is the zoning.

**The zones** (`oily.py`: `zone` map, `_frame`'s `trust`, `DARK`, `KAPPA`, `K_SEE`, `HALF_ZONE`). The photo (the same one, five stretches of two legs, the leg's brightness against the distance from its centre line, as a share of the middle's, far side): 1.0 up to 0.6 half-widths, 0.90 at 0.7, 0.76 at 0.8, 0.54 at 0.9 (stretches: .67–1.0, .33–.98, .16–.71); the side the highlight is on keeps its edge bright, 1.4–1.7× the middle's (the glint's halo), which the symmetric edge does not model. The fabric is 1 / facing as thick along the line of sight (`facing = sqrt(1 − u²)·cos(tilt)`), so a dark stocking's edges go as `exp(−KAPPA (1 / facing − 1))` with KAPPA = 0.35 and warm skin lifts the middle by `K_SEE` = 0.08 of the headroom; on flat dark art that renders .70–.75, .56–.62, .34–.38 at 0.7 / 0.8 / 0.9 (the middle is also lifted by the existing `see` term, which the photo's plateau includes), inside the photo's ranges; without it the edge was .74 / .81 / .91.

Where it is believed (the duck's points): per region (not per pixel: a white stocking's shadow would count as black) `dark = 1 − sstep(DARK, median luminance of the visible stocking)`, DARK = (0.30, 0.75) (the cached pictures: black .17–.42, grey .41–.52, white .67–.95, the PSD .67–.72); `trust` per band of V from `_frame` (1 where the cross-section is seen whole, 0.5 with one side out of sight, 0 with both or none seen whole anywhere; the first and last three bands take their interior neighbour's, because the cut across a piece's end hides a whole cross-section there, not the outline beside it, which without this dimmed the zones for ~50 px before every wall and frame end; smoothed along V by sigma = half the limb's width in bands); limbs under 4 px of half-width get none, 8 px or more all (`HALF_ZONE`). So the kneeling thigh whose outline is a skirt hem and the other leg gets half or none, a leg cut by the frame, a limb wider than the picture and a sliver get none, and a pale stocking is untouched (two white pictures 0.00 grey levels different, the PSD 0.36 on average, 6.7 at most).

Results on eight dark pictures: the far edge at 0.9 half-widths goes from .65–.78 to .45–.51 on thin legs (the photo's median .54); on art that already paints dark edges it compounds (12237543 .27 → .19). Not done: only the missing darkening (final edge = the darker of the art's own and the photo's target); an asymmetric edge (bright on the highlight's side).

**The faint default glint** (the duck's Q4, decided by the maintainer: yes). A dark stocking whose art paints no highlight on a stretch of limb is no less glossy for that, and the maintainer's read of real oily stockings is that most of the light is along the middle: so where the zones are believed (`believed` = darkness × `_frame`'s trust × limb width, the same per-band value as the zone map) and the piece is a limb, `_middle_glint` adds one synthetic track along the centre line c(V), `DEFAULT_GLINT` = 0.4 strong (a painted glint reaches 1; the lobes draw it like any other track) times `believed` at each row, held to the piece's ends (a wall and the frame are no end of a glint). Gates: `MIN_LENGTH` = 1.5 widths of actual ΔV (a foot, a dome); no painted track, or the strongest one's top under `FAINT` = 0.15, all of the default below half of FAINT and none of it from FAINT up (smoothstep: a painted highlight a hair stronger must not take the light away all at once). A piece with a painted glint is bit-identical to before. Strength 0.4 picked by eye against a real black thigh (real_vs_fallback.png: .35 / .5 / .7). On the 15 cached pictures it touches 4 pieces: the legs of 12347081, 12347558 and 12347586 (no peak at all) and one piece of 9ae0628e whose only painted track is 0.03 strong; the PSD and the pale pictures are untouched (0.00 grey levels).

The duck's review (read-only, 127 passed / 29 skipped, 13 old painted-highlight and occlusion scenarios re-run with it on): one blocking bug, fixed. On limbs 14–20 px wide the default glint vanished entirely (a 19 px limb was fine): `_curve` takes a row's glint from the pixels within `ab` = hmed / 20 of its A, which is under half a pixel on a thin limb, and the synthetic centre lies between pixels. It now looks at least `PIXEL` = 1 px around (test: widths 16–30, three sub-pixel phases; the zones fade the glint, as they should, below 8 px of half-width, so 14 px is weaker: tested). The same change moves nothing on the cached pictures but 833 pixels of one thin piece of 6b6a4476 (the lobe tightens a little). Non-blocking, taken: the FAINT cliff (a painted max of 0.149 added a 0.4 central track, 0.150 none) is now smooth; the length test uses the real ΔV rather than rows × row length. Non-blocking, not taken: at a wall between an off-centre painted thigh glint and a calf with none, the default glint starts on the calf's own centre line, 30–55 px from the thigh's glint (the wall band copies maps from the nearest body pixel, so the jump is inside the band); it is the same "each side of a wall on its own" as for two painted glints, none of the 15 real pictures has the combination, and a fade of the synthetic end would have to know the neighbouring piece's glint (a second pass). Also noted: at the maximum strength (250%) the faint glint reaches 0.90 of the 0.93 cap, as everything scales with strength; auto strength does not go there.

Checks: 13 new tests (18 cases), each failing when what it guards is broken (FAINT 0 / 99, MIN_LENGTH 0, the glint off the middle, `believed` = 1, the old cliff, the old reach, no length gate, every piece too short); the old test scenarios (print stripes, noise, near-black art, a flat leg, a hand in front, a wall, hair-shadow stripes) re-run with it on by hand: every map finite and in range, nothing added but one line along the middle, painted glints identical; 1000 random legs and 16 real pictures through the fuzz with every map's range checked; the full suite.

**The floor under the whole limb, and limbs in pieces** (the maintainer's black oily B1: the calves had no glint at all; then: "the foot and the leg are one selection with an occluder between, keep the line continuous"). Cause 1 (calf): the default glint gave way to any piece with a painted track, and the painted glint of the thigh (strength 1.0, dipping to 0.13 at mid-thigh, 0.77 at the knee, 0.05 at row 23 of 62) covered rows −1..23 only; the faint ridge in the art's calf (prominence .018–.035) has a lit share of .2–.4, under `LIT[0]` = .45, so the tracker dropped it. So `_middle_glint` became `_floor_glint`: one path along the whole piece, `FLOOR_GLINT` strong times `believed`, shared with the main painted glint (a painted glint stronger than the floor is returned bit-identical; below it the place goes over to the glint's held place, `FOLLOW` = (.25, 1) of the floor's strength; past its ends and across its gaps the place is held, from the rows at least half as strong as at its best, sure (`su >= SURE`), within `U_MAX` = 1.1 half-widths). The duck's round 5 found why a separate floor track is wrong: a glint that dims to 0.77 of its light and then slides 25 px stays a painted lobe at 0.45 while the floor holds the place it had where it was clear, 6–25 px away: two ridges (42 of 106 sampled rows; the new path 0); the regression tests use two such drifting glints and fail on the old design. Its other points taken: places past the outline (u = 4.4 on the foot of the B1 picture) and carried (unseen) rows are no anchors; the main glint is the one with the most sure light (`sum st·su`), not the first. Not taken: a policy for two lights of near-equal light (the floor follows whichever has a little more: the painted ones are as they were either way).
Cause 2 (foot): `Document.fields()` keeps V and A only on the painted pixels, so the foot beyond the ribbon was a piece of its own (too short for a limb) although the solver had one sheet over both (`fill_occlusions`). First attempt, dropped: give the solver's fill to `oily_maps` as pixels of the limb (V, A, a wider piece). It failed in three ways found by checking on the real pictures: the closing's virtual outline moved glints and facing (the duck: a 40-px notch moved the glint 11 px and raised the edge's facing from .475 to .841), two limbs of unequal width joined (150 + 20 + 70 px: the narrow one lost its glint), and, the worst, the user's white PSD (558cd91a) lost the calf glint of its second region: joined with the brighter foot beyond the shoe strap the piece's range of lighting (2 / 98 % of `absolute`, .51–.93 instead of about .5–.76) put the calf's peaks (.70) under `LIT[0]`; the lighting fit also ran wild (`_local_linear` extrapolates the slope in cells with no support, up to 1.8, beside a width jump). Kept (the first version; rounds 6 to 8 below): `filled_map` (`{region: connector mask}`, less the band along a wall) groups pieces (`_pieces`: stacked along the limb, both over `MIN_PIECE`) so that the limb's length is all of them and a piece with no glint of its own goes on with the glint of the others; each piece's lighting and glints are measured within the piece, as painted. Side by side (two limbs of one region, a strand of hair down a leg) is never grouped: nothing says them from each other.
Checks: 187 tests in `test_oily.py` and `test_look.py` (the new ones: the floor as one path, the drifting glints, invalid and unseen anchors, the pieces: ribbon, slanted band, side by side with an off-centre glint on the bigger piece, staggered, notch, pale limb, group length, nearer end both ways) and the real-Document ones in `test_document.py` (connector masks, a divider across the ribbon); about 35 mutants, every one failing a test (several only after adding the case that showed it was missed: the first side-by-side test had no glint on the bigger piece, so grouping them changed nothing visible). Fifteen cached pictures rendered against the committed version (`.scratch` scripts `effect_scan2.py`, `compare_crop.py`): the black ones gain a continuous line along every leg (12347558, 12299022, 12310121, 11762650, b1black; 6b6a4476's buttock a thin line under its hot spot).

**Rounds 6 to 8: the donors, the smoothing, and the cut's edge** (found by the duck, and by looking at the maintainer's picture at native zoom). Round 6: the first piece processed (the biggest) supplied the group's ends, so a blank big leg beside a painted small foot misaligned: `oily_maps` is two passes per region now (pass 1 measures every piece and `_ends` of the grouped ones, pass 2 the floors with `_nearest`); `_curve` re-smoothed strong painted glints (core off by up to .33): the floor's own rows are `free`, the painted rows are smoothed as they were and the floor's rows follow with the offset the smoothing made dying out over `FREE_TAU`; steep bands failed the V-overlap rule: `STACK` = (.75, .5). Round 7: a faint glint painted on a piece sent the floor toward 0 instead of toward the place the limb's other piece holds (`path` blends toward `held`); the confidence-shrunk u of a faint nearer donor displaced the clear one beyond it (`_ends` returns the unscaled places and `follow`; `_nearest` folds the donors of each side from the farthest, `u = follow * place + (1 - follow) * u`); a blank piece between two differently placed painted ones jumped at one seam (`held` is a pair, linear along the piece); a strip too short to see a cross-section whole once the cut is hidden lost the floor (it is measured as before). The cut's edge: at native zoom on the B1 ribbon the line crossed the ribbon but veered right above it and started at the left edge below it. The ribbon cuts the courses aslant, so near it each band of V is in sight only in part, and `_frame` took the middle of the part in sight for the limb's (synthetic legs cut at 20 to 45 degrees: the glint 36 to 75 px off the middle; the real-solver fixture: 35 px above, 20 below; the zones darkened the cut as an outline). The connector (`_joins`: the components of the fill that touch two pieces of one limb) is the limb running on behind it, like a wall: its 3x3-dilated pixels are `hidden` for `_frame`, so a cut band is measured from the outline on the other side and the limb's half-width from whole bands; the glint is then 1 to 3 px off the middle on both sides, a little weaker where the outline is not seen whole (`trust` .5: the floor is .24 to .31 instead of .4 next to an aslant cut). A notch the closing fills in (the duck: a bite 40 px deep next to a real ribbon moved the glint 11 px and the facing at its edge from .475 to .866 when every fill pixel counted) and side by side pieces are not connectors. The white PSD (558cd91a) is no longer pixel-identical: at its ankle straps and the lace trim the glint maps are smoother, one continuous line per leg (141k px of glint maps differ, tone not at all).
Round 8 (the duck again: one blocker, three smaller). Blocker: the connector-aware frame took the typical half-width from the cross-sections seen whole, and where those are few (the duck's strip beside a hair strand, whose only rows clear of the strand are a toe 8 px wide: 3.5 px for a limb 40 to a side) the lighting fit got cells 0.2 px wide, a 166 x 429 grid, and found no painted glint at all (core 1.0 to 0). A limb is no narrower than it is seen, so `_frame` has `hmed_min`, which `oily_maps` gives the plain frame's width; on the real pictures it never acts (the connector-aware width is 0.5% above the plain one on every piece of b1black and 558cd91a). Smaller: the held place of a piece between two painted ones ran over the fit's rows with the padding rows at its ends (the duck's 40 px piece started 3 px and ended 11 px from the places held at its ends): it runs along the piece's actual extent now, each row's place taken in the middle of the part of the row the piece covers, which is where `_curve` puts the row's glint (the mean of its pixels); a piece of one fit row (at most 24 px times scale tall) had its floor as a point, a blob in its middle (core .06 at its ends): its floor counts in thirds of its extent now (an eighth element in the track, `(offset, rows per row)`, which the draw reads), a line from the place at its top to the one at its bottom (14, 20, 40, 60 and 140 px tall: both ends within 2 px of the held places, 0.40 all along); donors equally near and equally big with glints at -0.3 and +0.3 gave -0.3 (the smaller signed place sorted last and had the last word): they are one donor at the mean of their places weighted by how clear each is. Also: the notch that touches the ribbon's fill is one component with it (the duck: a 40 px bite right above a ribbon, facing at its edge .109 to .864, the glint x=199 to 180, up to 92 px above the ribbon): not separable from hair the limb goes on behind, kept and written into the docstring and the feature note as a limit.
Checks of round 8: 253 tests in `test_oily`, `test_look`, `test_document`, 11 new (the toe, the one-row piece, the extent, the ties, the width floor in `_frame`, strips of 4 to 20 rows, blank pieces of 140, 40 and 14 px between differently placed glints, the notch limit); 50 mutants of all the new mechanisms and the ones before, none left; the 15 real pictures give the same numbers as before the round (the fixes do not touch them).
Round 9 (the duck's check of round 8: one blocker, three smaller). Blocker: the thirds were for a piece with no glint painted only; `_tracks` gives a track of one row however faint (0.0276 of the lighting's top was enough), and with it the piece's glint was a point again (core .061 at the first and last pixel row, .40 in the middle). `_floor_glint` has one evaluation grid now, the fit's rows or thirds of the extent, and the same blend of the painted glint and the floor on either (`tg`: where each row lies in fit rows; the arrays of the painted track are read there); with nrow >= 2 it is bit for bit what it was (8000 random cases against the saved source). Smaller: the thirds were put at their centres, and `_curve` takes the mean of the pixels it selects, which in a strip of 4 pixel rows is not there (x = 196 / 141 at the ends for hints 205 / 150): each third's place is at the mean of its pixels (`t` is the pixels' rows now, not an extent pair; 205 / 151); donors as near as each other were compared to the last digit (a shift of 1e-4 px in one's V edge flipped the glint from -0.3 to +0.3): the distance is by pixel (`round(gap / PIXEL)`), 2 px or more still decides; and the thirds changed pieces that are no slivers: one fit row also comes of a long piece of which only a small patch is in sight (the lighting is fitted to that), and thirds of its whole extent are much coarser than the one row there is a fit for: thirds only where the piece's pixels are within two rows of each other, else the rows of the fit as before. Found while testing the slivers: a strip of 5 or 6 px (three bands of V at the tests' scale) is whole in its middle band only; its trust, smoothed (sigma = half the limb's width in bands, mode 'nearest') over three bands, is 0.02, and 0.4 x 0.02 is under the floor's 0.05: no glint at all (the frame with the connectors out of sight had been taken for the one whole band, where the plain frame has trust 1). That frame is taken only where it believes the outline somewhere at least `CUT_TRUST` = 0.25 of what the plain frame does at best (no band whole is trust 0 everywhere, so that case is the same rule): strips of 3 to 20 px between two ribbons all have the line now.
Checks of round 9: 275 tests in `test_oily`, `test_look`, `test_document` (22 new); 54 mutants, none left; 1500 random limbs (bands, slanted bands, strands) with and without the fill; the 15 real pictures give the same numbers as before the round.
Round 10 (the duck's check of round 9: one blocker, one smaller; both its own fixes, applied as it put them, no further round). Blocker, my own doing: I had dropped `cut_frame[6] and` from the acceptance of the frame with the connectors out of sight as subsumed by the trust ratio, and it is not when the plain frame's trust is 0 as well (`0 >= 0.25 * 0`): a leg cut by the image's edge (no cross-section whole in either frame) with a ribbon across it took a frame with its connector edges out of sight, which made the right edge, a silhouette in sight, one out of sight beside the ribbon (facing .18 to 1.0, 63056 px, a pale cap). Both conditions again; a test of that leg (tone, facing and zone as without the fill). Smaller: the thirds' pixel means were taken with `floor((t - t_lo) * 3 / span)`, the draw bins with `(t - t_lo) * (3 / span) - 0.5` in [k - 0.5, k + 0.5): the last pixel of about one sliver in seven (30214 of 200000 random ones) is exactly at the edge of the last third and the two differ in the last digit (a strip of 5 px at a fit row of 20.853115214047392 px; 204 / 154 at the ends of a strip of 8 for 205 / 150). The means are taken over the pixels the draw puts in each third, by its own expression.
Checks of round 10: the full suite, 337 tests (two new: the cropped leg with a ribbon, the thirds' pixels); 56 mutants, none left; 4000 random `_floor_glint` cases with nrow >= 2 bit for bit as before the refactor; 1500 random limbs with and without the fill; the 15 real pictures give the same numbers as before the round.
Checks: tests 302 passed; 38 mutants of these mechanisms all failing a test (donor order, follow ignored, top-only held, the end toward the piece, tie by size, path toward 0, a notch as a connector, nothing a connector, the whole gap hiding, undilated, no fallback, ...); 1200 random limbs (bands, slanted bands, strands) through `oily_maps` with and without the fill: finite, in range, drawing on painted pixels only, tone unchanged by the connectors, facing and zones unchanged when the only gaps are strands. (The fuzz once showed identical calls of `oily_maps` differing by up to 1e-5 in a few hundred pixels of the lobe maps: traced to the output of `cv2.distanceTransform` for an identical canvas, not reproducible on that canvas in isolation, so no logic of the pieces; the tolerance of its determinism check is 1e-4.)

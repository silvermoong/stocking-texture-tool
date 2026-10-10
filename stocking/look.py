"""From solved courses to the finished texture: style, density, tilt, strength, sparkles, moire; renders and crops.

斜单线 (earlier called 单线亮点) and 加濑风 call the knit renderers exactly as the reference renders the presets were
tuned on did (tests/verify.py), with their seed and draw order, so default settings reproduce those renders. 细线,
针织 and 线圈 are the tool's own (knit.render_thread / render_loops / render_coil; 细线 replaced the reference's knit
after it was compared with a drawing of real knit stockings). The
random fields (sparkles, grain) are drawn once per image at full size, and every image-wide map a style needs is taken
from the whole image, so a crop is pixel-identical to the same area of the full render: the live 100% preview shows
exactly what the export will hold.

The 摩尔纹效果 is not a style but a layer over whatever style is chosen: bands of light and dark along the contours of
the depth model's bulge, one ring for every fixed step of height (moire_phase, moire_fringes), grown from the crown
outward by the 面积 slider. It is moire on purpose, as the user asks for it. The texture itself still never aliases
(the fade in every style), and the bands are far coarser than a pixel and fade out where they would not be, so they
cannot alias either.
"""
import re
import threading

import cv2
import numpy as np

from . import knit, oily
from .i18n import tr

SEED = 20261005
BASE_PERIOD = 4.6           # px per course at 100% density on a 1280x1920 image
MIN_PERIOD = 3.2            # below this most of a curved surface sits in the anti-moire fade
REF_AREA = 1280 * 1920
# Skin visibility (线圈): the Lab direction of skin (60 degrees from a* toward b*), the smoothing in px at REF_AREA, and
# the spread (5th to 95th percentile, in Lab units) over which a region's colour counts as showing skin at all.
SKIN_AXIS = (0.5, 0.866)
SEE_SIGMA = 10.0
SEE_SPAN = (4.0, 9.0)
# period -> fade band and wale ratio of the earlier deliveries (普通, 密, 更密); interpolated in between
BANDS = np.array([(3.4, 0.30, 0.36, 1.8), (3.7, 0.29, 0.35, 1.6), (4.6, 0.27, 0.34, 1.25)])
STYLES = ('knit', 'loops', 'coil', 'lines', 'grain', 'oily')    # 细线, 针织, 线圈, 斜单线, 加濑风, 油光
EXPERIMENTAL_STYLES = ('oily',)                     # shown as 试验 in the panel
SPARKLE_STYLES = STYLES                            # every style scatters sparkles (亮点), by the same settings
LEGACY_STYLES = {'p_oily': 'oily'}                  # saved by an early version
# where sparkles may go: bulges, painted highlights, a 亮点 layer, everywhere alike
SPARKLE_KINDS = ('depth', 'bright', 'painted', 'even')
DEFAULTS = {'style': 'knit', 'density': 100.0, 'tilt': 32.0, 'strength': 100.0,
            'strength_auto': True, 'sparkle_depth': 100.0, 'sparkle_bright': 100.0, 'sparkle_painted': 0.0,
            'sparkle_even': 0.0, 'sparkle_link': True, 'moire_on': False, 'moire': 100.0, 'moire_area': 100.0}
# Mean lightness step per unit of texture ratio (see suggested_strength) over the dark fixture's stockings, where the
# presets were tuned: 100% strength reads right at this value.
STRENGTH_REF = 33.2
# Sparkle weight of the 'even' source at 100%, per style: three times the mean weight the depth source gives over
# the dark fixture's stockings at 100% (matching it looked too sparse spread over everything; the user set the old
# 300% as the new 100%).
EVEN_SPARKLES = {'lines': 0.36, 'grain': 0.81, 'knit': 0.81, 'loops': 0.81, 'coil': 0.81, 'oily': 0.81}
# How each style scatters them: chance per pixel (times the weight), brightness range (strength leaves it alone:
# 强度 scales the texture only, the 亮点 sliders the sparkles), colour (B, G, R gain; None = neutral light) and the
# random draws used. 斜单线's warm single-pixel glints and 加濑风's white flecks are the reference renders'; the other
# styles take 加濑风's flecks.
SPARKLE_RECIPES = {
    'lines': dict(density=0.045, r_lo=0.18, r_hi=0.55, tint=(0.95, 1.0, 1.08), draws='lines'),
    'grain': dict(density=0.014, r_lo=0.12, r_hi=0.38, tint=None, draws='grain'),
    'knit': dict(density=0.014, r_lo=0.12, r_hi=0.38, tint=None, draws='grain'),
    'loops': dict(density=0.014, r_lo=0.12, r_hi=0.38, tint=None, draws='grain'),
    'coil': dict(density=0.014, r_lo=0.12, r_hi=0.38, tint=None, draws='grain'),
    'oily': dict(density=0.014, r_lo=0.12, r_hi=0.38, tint=None, draws='grain'),
}
# 摩尔纹效果 is off until its switch (moire_on) is turned on; then moire (强度) is how strongly the bands show and
# moire_area (面积) how much of each bulge carries them. The fringes of two fine layers over a stretched surface are
# contours of its height, so the bands run along the depth model's bulge (smoothed by MOIRE_BLUR px at REF_AREA
# first), one ring for every MOIRE_STEP of the depth the stockings span: a taller bulge holds more rings, a flat one
# none, whatever the size of its part. The 面积 slider grows the bulge from nothing to its full height, so the first
# ring is born as a small light disc on the crown, spreads outward and is joined by more rings. A band is a sine
# squared up by tanh (MOIRE_SHARP) into crisp edges; it shows only once the bulge has climbed MOIRE_FIRST of a step
# (a surface that has not yet risen half a step has no ring at all). Where the bulge changes so fast that the bands
# would run finer than MOIRE_FADE cycles/px they fade out, as the texture's own courses do. At strength 100% a band
# moves the stocking's lightness by MOIRE_LIGHT (at the strength a dark stocking gets, less on light ones, where the
# same ratio looks twice as strong) and the texture's own contrast by MOIRE_TEXTURE.
MOIRE_STEP = 0.045
MOIRE_FIRST = (0.3, 0.55)
MOIRE_BLUR = 8.0
MOIRE_FADE = (0.06, 0.14)
MOIRE_SHARP = 2.2
MOIRE_LIGHT = 0.13
MOIRE_TEXTURE = 0.9
RENDER_KEYS = ('style', 'density', 'tilt', 'strength', 'sparkle_depth', 'sparkle_bright',
               'sparkle_painted', 'sparkle_even', 'moire_on', 'moire', 'moire_area')
MARGIN = 8                  # px around a crop, so blurs and gradients at its edge see real neighbours


def _legacy_sparkles(p):
    """Settings saved before each sparkle source had its own amount: one source (or a depth/brightness mix) and
    one overall amount."""
    src = p.pop('sparkles')
    a = float(p.pop('sparkle_amount', 100.0))
    m = float(p.pop('sparkle_mix', 50.0)) / 100.0
    d, b, pt = {'depth': (a, 0, 0), 'bright': (0, a, 0), 'painted': (0, 0, a), 'off': (0, 0, 0),
                'auto': (a * min(1.0, 2 * (1 - m)), a * min(1.0, 2 * m), 0)}.get(src, (a, a, 0))
    p.setdefault('sparkle_depth', round(d))
    p.setdefault('sparkle_bright', round(b))
    p.setdefault('sparkle_painted', round(pt))
    p.setdefault('sparkle_link', p['sparkle_depth'] == p['sparkle_bright'])


def clean_params(p):
    """Defaults filled in and every value range-checked."""
    p = dict(p or {})
    if 'sparkles' in p:
        _legacy_sparkles(p)
    p.pop('sparkle_amount', None)
    p.pop('sparkle_mix', None)
    q = dict(DEFAULTS)
    q.update({k: v for k, v in p.items() if k in DEFAULTS and v is not None})
    q['style'] = LEGACY_STYLES.get(q['style'], q['style'])
    if q['style'] not in STYLES:
        raise ValueError(tr('未知样式：{style}', style=q['style']))
    q['density'] = float(np.clip(float(q['density']), 40, 200))
    q['tilt'] = float(np.clip(float(q['tilt']), 0, 75))
    q['strength'] = float(np.clip(float(q['strength']), 0, 250))
    q['moire'] = float(np.clip(float(q['moire']), 0, 100))
    q['moire_area'] = float(np.clip(float(q['moire_area']), 0, 100))
    for k in SPARKLE_KINDS:
        q[f'sparkle_{k}'] = float(np.clip(float(q[f'sparkle_{k}']), 0, 300))
    for k in ('sparkle_link', 'strength_auto', 'moire_on'):
        v = q[k]
        q[k] = v.strip().lower() in ('1', 'true', 'yes') if isinstance(v, str) else bool(v)
    if p.get('strength_auto') is None and 'strength' in p:
        q['strength_auto'] = q['strength'] == 100.0     # settings from before auto strength: a moved slider stays put
    if q['sparkle_link']:
        q['sparkle_bright'] = q['sparkle_depth']        # linked amounts are one value; depth's wins
    return q


def geometry(density, w, h):
    """Course period and fade band for a density (percent) on a w x h image."""
    raw = BASE_PERIOD / (density / 100.0) * np.sqrt(w * h / REF_AREA)
    period = max(raw, MIN_PERIOD)
    f_lo, f_hi, wale = (float(np.interp(period, BANDS[:, 0], BANDS[:, c])) for c in (1, 2, 3))
    return {'period': float(period), 'raw_period': float(raw), 'clamped': bool(raw < MIN_PERIOD),
            'f_lo': f_lo, 'f_hi': f_hi, 'wale_ratio': wale,
            'max_density': float(100.0 * BASE_PERIOD * np.sqrt(w * h / REF_AREA) / MIN_PERIOD)}


def _lstar(v):
    """CIELAB L* of an sRGB grey level v in 0..1."""
    y = np.where(v > 0.04045, ((v + 0.055) / 1.055) ** 2.4, v / 12.92)
    return np.where(y > 0.008856, 116 * np.cbrt(y) - 16, 903.3 * y)


def suggested_strength(src_bgr, R, alpha):
    """Strength (%) at which the texture reads as strong on these stockings as 100% does on the dark ones the presets
    were tuned on.

    The texture scales the art by a ratio, and the same ratio is a bigger step in lightness on a light colour: on
    white stockings about twice as big. Rounded to 5, between 30 and 100 (stockings as dark as the fixture or darker
    keep the tuned 100%).
    """
    m = (R > 0) & (alpha > 0.5)
    if not m.any():
        return 100.0
    v = (src_bgr[m].astype(np.float32) @ np.float32([0.114, 0.587, 0.299])) / 255
    step = (_lstar(np.minimum(v + 0.002, 1)) - _lstar(np.maximum(v - 0.002, 0))) / 0.004 * v
    val = cv2.GaussianBlur(src_bgr.max(axis=2).astype(np.float32) / 255, (0, 0), 1.5)[m]
    gate = knit.sstep(0.03, 0.30, val)          # the renderers fade the texture out in the darks
    s = float((step * gate).mean())
    if s <= 0:
        return 100.0
    return float(np.clip(5 * round(20 * STRENGTH_REF / s), 30, 100))


def side_of(name):
    """Tilt sign for a region by its name: +1 for 左 or the word left, -1 for 右 or right (whichever comes last in the
    name wins), else 0."""
    low = name.lower()
    left = max(low.rfind('左'), *(m.start() for m in re.finditer(r'\bleft\b', low)), -1)
    right = max(low.rfind('右'), *(m.start() for m in re.finditer(r'\bright\b', low)), -1)
    return 0.0 if left < 0 and right < 0 else (1.0 if left > right else -1.0)


def tilt_sides(R, names):
    """Tilt sign per pixel (斜单线 leans +θ or -θ, so the two sides of the body make a chevron). A region named
    左… or 右… takes its sign from the name; any other region from where it lies, each separate piece on its own:
    left of the middle of all the stockings +1 (as 左, the leg on the image's left), right of it -1, and 0 (no lean)
    for a piece in the middle with stockings on both sides of it, as a crotch between two legs. Without this a
    region named neither (腿, 部位 2) got 0, and its lines only spread apart as the tilt grew, never leaning."""
    side = np.zeros(R.shape, np.float64)
    inside = R > 0
    if not inside.any():
        return side
    xs_all = np.nonzero(inside)[1]
    mid, span = xs_all.mean(), max(float(np.ptp(xs_all)), 1.0)
    margin = 0.15 * span
    parts = {}                                              # region -> [(piece mask, centre x)]
    for i in range(1, len(names) + 1):
        n, lab = cv2.connectedComponents((R == i).astype(np.uint8), connectivity=8)
        parts[i] = [(p, np.nonzero(p)[1].mean()) for p in (lab == k for k in range(1, n))]

    def lean(cx, i):
        # in the middle with other stockings on both sides of it (a crotch between two legs): no lean
        others = [c for j, ps in parts.items() if j != i for p, c in ps if p.sum() >= 0.01 * len(xs_all)]
        if abs(cx - mid) < margin and any(c < cx - margin for c in others) and any(c > cx + margin for c in others):
            return 0.0
        return 1.0 if cx <= mid else -1.0

    for i, pieces in parts.items():
        if not pieces:
            continue
        m = R == i
        s = side_of(names[i - 1])
        if s:
            side[m] = s
            continue
        # one region painted over both legs: each leg on its own; otherwise the region as a whole
        big = [c for p, c in pieces if p.sum() >= 0.1 * m.sum()]
        if any(c < mid - margin for c in big) and any(c > mid + margin for c in big):
            for p, c in pieces:
                side[p] = 1.0 if c <= mid else -1.0
        else:
            side[m] = lean(np.nonzero(m)[1].mean(), i)
    return side


def _same_region(R):
    same = R > 0
    for sh in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        same &= np.roll(R, sh, axis=(0, 1)) == R
    return same


def bulge(disp, R, down=4):
    """How far each point bulges toward the viewer above the region's own surroundings, in the disparity's units (0
    outside the regions).

    Raw nearness would put everything on whatever end of a limb points at the camera (a crossed leg: the foot);
    the bulge relative to a neighbourhood about as wide as the region is the crown of a leg, the top of a knee or
    a breast, which is where the fabric is stretched. The surroundings are a masked blur at 1/down resolution.
    """
    h, w = R.shape
    out = np.zeros((h, w), np.float32)
    small = (max(w // down, 1), max(h // down, 1))
    for i in np.unique(R[R > 0]):
        m = R == i
        radius = float(cv2.distanceTransform(np.pad(m, 1).astype(np.uint8), cv2.DIST_L2, 5).max())
        sig = max(radius, 6.0) / down
        mf = m.astype(np.float32)
        num = cv2.GaussianBlur(cv2.resize(disp * mf, small, interpolation=cv2.INTER_AREA), (0, 0), sig)
        den = cv2.GaussianBlur(cv2.resize(mf, small, interpolation=cv2.INTER_AREA), (0, 0), sig)
        around = cv2.resize(num / np.maximum(den, 1e-6), (w, h), interpolation=cv2.INTER_LINEAR)
        out[m] = disp[m] - around[m]
    return out


def relief_of(rel, R):
    """0..1 per region: bulge stretched from the region's flat (its 40th percentile, 0) to its crown (99th, 1)."""
    out = np.zeros(R.shape, np.float32)
    for i in np.unique(R[R > 0]):
        m = R == i
        p40, p99 = np.percentile(rel[m], [40, 99])
        out[m] = knit.sstep(p40, max(p99, p40 + 1e-6), rel[m])
    return out


def relief(disp, R, down=4):
    """0..1 per region: how far each point bulges (see bulge) between its region's flat (0) and its crown (1)."""
    return relief_of(bulge(disp, R, down), R)


def skin_visibility(src_bgr, R, alpha, scale=1.0):
    """(see, trust), each 0..1 per pixel (0 outside the regions): how much skin shows through the stocking.

    The painting says it in colour: where the knit is open the skin's warm yellow-red comes through the black or
    white yarn. The measure is the Lab chroma along the skin's hue (a* and b*, mostly b*), smoothed over about 10 px
    (at 1280 x 1920) so the knit itself is not in it, then stretched between the region's own 5th and 95th
    percentile: the lightest stockings and the darkest sit at the same 0..1. trust says whether that stretch means
    anything: a region whose colour hardly varies (a flat swatch) has no skin to read, and 线圈 draws its flat
    texture there instead."""
    lab = cv2.cvtColor(src_bgr, cv2.COLOR_BGR2LAB).astype(np.float32) - 128
    skin = lab[..., 1] * SKIN_AXIS[0] + lab[..., 2] * SKIN_AXIS[1]
    see = np.zeros(R.shape, np.float32)
    trust = np.zeros(R.shape, np.float32)
    sigma = SEE_SIGMA * scale
    for i in np.unique(R[R > 0]):
        m = (R == i) & (alpha > 0.5)
        if m.sum() < 64:
            continue
        mf = m.astype(np.float32)
        sm = cv2.GaussianBlur(skin * mf, (0, 0), sigma) / np.maximum(cv2.GaussianBlur(mf, (0, 0), sigma), 1e-6)
        lo, hi = np.percentile(sm[m], [5, 95])
        see[m] = np.clip((sm[m] - lo) / max(hi - lo, 1e-6), 0, 1)
        trust[m] = knit.sstep(SEE_SPAN[0], SEE_SPAN[1], hi - lo)
    return see, trust


def highlight(src_bgr, R, down=4):
    """0..1 per region: how much brighter each point is painted than the region's own surroundings.

    The artist's highlights (a knee top, a shin's lit side), whatever the stocking's base colour. It cannot tell a
    highlight from a light print, so on printed stockings (beige bands) the depth source is the safer choice.
    """
    h, w = R.shape
    val = cv2.cvtColor(src_bgr, cv2.COLOR_BGR2HSV)[..., 2].astype(np.float32) / 255
    out = np.zeros((h, w), np.float32)
    small = (max(w // down, 1), max(h // down, 1))
    for i in np.unique(R[R > 0]):
        m = R == i
        mf = m.astype(np.float32)
        # brightness smoothed inside the region only, so the outline and the background do not bleed in
        vb = cv2.GaussianBlur(val * mf, (0, 0), 4) / np.maximum(cv2.GaussianBlur(mf, (0, 0), 4), 1e-6)
        radius = float(cv2.distanceTransform(np.pad(m, 1).astype(np.uint8), cv2.DIST_L2, 5).max())
        sig = max(radius, 6.0) / down
        num = cv2.GaussianBlur(cv2.resize(vb * mf, small, interpolation=cv2.INTER_AREA), (0, 0), sig)
        den = cv2.GaussianBlur(cv2.resize(mf, small, interpolation=cv2.INTER_AREA), (0, 0), sig)
        around = cv2.resize(num / np.maximum(den, 1e-6), (w, h), interpolation=cv2.INTER_LINEAR)
        rel = vb[m] - around[m]
        p50, p99 = np.percentile(rel, [50, 99.5])
        out[m] = knit.sstep(p50, max(p99, p50 + 1e-6), rel)
    return out


def _smooth_within_regions(f, R, sigma):
    """f blurred by sigma inside each region on its own (a masked blur), 0 outside them: a region's edge, a hole in it
    (a hand, trim) or the region beside it does not pull the values near it toward zero."""
    h, w = R.shape
    out = np.zeros((h, w), np.float32)
    pad = int(3 * sigma) + 1
    for i in np.unique(R[R > 0]):
        m = R == i
        rows, cols = np.flatnonzero(m.any(1)), np.flatnonzero(m.any(0))
        y0, y1 = max(rows[0] - pad, 0), min(rows[-1] + pad + 1, h)
        x0, x1 = max(cols[0] - pad, 0), min(cols[-1] + pad + 1, w)
        mf = m[y0:y1, x0:x1].astype(np.float32)
        smooth = cv2.GaussianBlur(f[y0:y1, x0:x1] * mf, (0, 0), sigma)
        smooth /= np.maximum(cv2.GaussianBlur(mf, (0, 0), sigma), 1e-6)
        out[y0:y1, x0:x1] = np.where(mf > 0, smooth, out[y0:y1, x0:x1])
    return out


def moire_phase(rel, disp, R, scale=1.0):
    """(phase, slope), float32 per pixel (0 outside the regions): how many ring steps the bulge rel (bulge()) stands
    above its region's flat (its 40th percentile, as in relief), and how fast that changes per px.

    A step is MOIRE_STEP of the depth the stockings span (disp's 2nd to 98th percentile over the regions), the same all
    over the picture: a taller bulge holds more rings and a shallow one few or none, while the size of the part only
    sets how big its rings are. scale: the image's size against REF_AREA's (sqrt of the area ratio), which the
    smoothing follows."""
    inside = R > 0
    zero = np.zeros(R.shape, np.float32)
    if not inside.any():
        return zero, zero
    lo, hi = np.percentile(disp[inside], [2, 98])
    up = np.zeros(R.shape, np.float32)
    for i in np.unique(R[inside]):
        m = R == i
        up[m] = np.maximum(rel[m] - np.percentile(rel[m], 40), 0)
    phase = _smooth_within_regions(up, R, MOIRE_BLUR * scale) / (MOIRE_STEP * max(float(hi - lo), 1e-6))
    gy, gx = np.gradient(phase)
    return phase, np.hypot(gx, gy).astype(np.float32)


def moire_fringes(phase, slope, area):
    """The moire bands, -1..1 per pixel, from moire_phase's maps with every bulge grown to area (0..1) of its height.

    Dark and light bands alternate with every half step the grown bulge stands above the flat, so one that has just
    climbed half a step shows as a small light disc on its crown; the disc spreads outward as area rises, and more
    rings join it. It is a sine, not a cosine: the flat carries no band, and the bands add next to no light on average.
    Where the bulge changes so fast that the bands would run finer than MOIRE_FADE cycles/px they fade out (so do the
    outermost pixels of a region, where the map ends), so nothing here can alias."""
    grown = area * phase
    bands = -np.tanh(MOIRE_SHARP * np.sin(2 * np.pi * grown)) / np.tanh(MOIRE_SHARP)
    fade = 1 - knit.sstep(MOIRE_FADE[0], MOIRE_FADE[1], area * slope)
    return (bands * fade * knit.sstep(MOIRE_FIRST[0], MOIRE_FIRST[1], grown)).astype(np.float32)


def moire_active(q):
    """Whether the (cleaned) settings q draw the 摩尔纹效果 at all: its switch is on and the 强度 slider is above 0."""
    return bool(q['moire_on']) and q['moire'] > 0


def apply_moire(out, src, fringes, amount, light):
    """The moire bands over a style's render. out: BGR uint8 render of src; fringes: Scene.moire_map (cropped like
    src); amount: the 强度 slider, 0..1; light: the strength a stocking this light gets, 0..1 (Scene.suggested_strength).
    In a bright band the stocking is lighter and its texture stronger, in a dark one the reverse."""
    b = (amount * fringes)[..., None]
    s = src.astype(np.float32)
    res = (s + (out.astype(np.float32) - s) * (1 + MOIRE_TEXTURE * b)) * (1 + MOIRE_LIGHT * light * b)
    return np.clip(np.round(res), 0, 255).astype(np.uint8)


class Scene:
    """Everything a render needs from one document state, prepared once.

    art_rgb: HxWx3. REG: region index per pixel (0 = untextured; already limited to solved regions). V, A: course and
    across coordinates. stock, alpha: coverage. names: region names by index - 1. sparkle: a painted 亮点 layer
    (HxW uint8) or None. disparity: a function returning the depth model's disparity, or None while it is not ready.
    cut: HxW bool, the bands along walls where V and A jump from one stretch of stocking to the one behind it
    (Document.cut_map), or None: no gradient there counts (densest point, fade check).
    fill: {region index: bool mask} of what the solver filled in beside each region (Document.filled_map), or None:
    the 油光's glints take pieces of a limb something the selection leaves out cuts across for one limb.
    """

    def __init__(self, art_rgb, REG, V, A, stock, alpha, names, sparkle=None, disparity=None, randoms=None,
                 cut=None, fill=None):
        self.h, self.w = REG.shape
        self.src = np.ascontiguousarray(art_rgb[..., ::-1])            # the renderers work in BGR
        self.REG = REG
        self.R = np.where(stock, REG, 0).astype(np.int8)
        self.V, self.A, self.alpha = V, A, alpha
        self.cut = cut if cut is not None and cut.any() else None
        self.fill = fill or None
        self.names = list(names)
        self.side = tilt_sides(self.R, self.names)
        self.sparkle = sparkle
        self._disparity = disparity
        self._randoms = randoms if randoms is not None else {}
        self._lock = threading.Lock()
        self._stretch = {}
        self._grads = None
        self._densest = None
        self._suggested = None
        self._full = (None, None)

    # ------------------------------------------------------------- shared fields

    def randoms(self, style):
        """The random fields a style draws, in the reference's order from a fresh generator seeded with SEED."""
        with self._lock:
            if style not in self._randoms:
                rng = np.random.default_rng(SEED)
                if style == 'grain':
                    g, gc = knit.grain_noise(rng, self.h, self.w)
                    self._randoms[style] = (g, gc, rng.random((self.h, self.w)), rng.random((self.h, self.w)))
                else:
                    self._randoms[style] = (rng.random((self.h, self.w)), rng.random((self.h, self.w)))
            return self._randoms[style]

    def suggested_strength(self):
        with self._lock:
            if self._suggested is None:
                self._suggested = suggested_strength(self.src, self.R, self.alpha)
            return self._suggested

    def resolve(self, q):
        """Clean params with an automatic strength filled in."""
        return dict(q, strength=self.suggested_strength()) if q['strength_auto'] else q

    def wide_luma(self):
        """knit.wide_luma of the whole image, cached: crops take theirs from it, so they match the whole render."""
        with self._lock:
            if 'wide' not in self._stretch:
                self._stretch['wide'] = knit.wide_luma(self.src)
            return self._stretch['wide']

    def see_map(self):
        """skin_visibility (see, trust) of the whole image, cached: crops slice it, so they match the whole render."""
        with self._lock:
            maps = self._stretch.get('see')
        if maps is None:
            maps = skin_visibility(self.src, self.R, self.alpha, float(np.sqrt(self.w * self.h / REF_AREA)))
            with self._lock:
                self._stretch['see'] = maps
        return maps

    def oily_maps(self):
        """oily.oily_maps of the whole image (油光's tone, glint and translucency maps), cached: crops slice it."""
        with self._lock:
            maps = self._stretch.get('oily')
        if maps is None:
            maps = oily.oily_maps(self.src, self.R, self.alpha, self.A, self.V,
                                  float(np.sqrt(self.w * self.h / REF_AREA)), cut=self.cut, REG=self.REG,
                                  fill=self.fill)
            with self._lock:
                self._stretch['oily'] = maps
        return maps

    def _depth(self):
        return self._disparity() if self._disparity else None

    def bulge_map(self):
        """bulge() of the depth model's disparity over the whole image, cached; None while the model is not ready."""
        with self._lock:
            if 'bulge' in self._stretch:
                return self._stretch['bulge']
        disp = self._depth()
        if disp is None:
            return None
        rel = bulge(disp, self.R)
        with self._lock:
            self._stretch['bulge'] = rel
        return rel

    def relief_map(self):
        """relief() of the depth model's disparity over the whole image, cached; None while the model is not ready."""
        with self._lock:
            if 'relief' in self._stretch:
                return self._stretch['relief']
        rel = self.bulge_map()
        if rel is None:
            return None
        rel = relief_of(rel, self.R)
        with self._lock:
            self._stretch['relief'] = rel
        return rel

    def moire_maps(self):
        """(phase, slope, gate) of the 摩尔纹效果 over the whole image, cached: moire_phase's two maps and the texture's
        own gate (nothing on dark or uncovered pixels). None while the depth model is not ready."""
        with self._lock:
            if 'moire' in self._stretch:
                return self._stretch['moire']
        rel, disp = self.bulge_map(), self._depth()
        if rel is None or disp is None:
            return None
        phase, slope = moire_phase(rel, disp, self.R, float(np.sqrt(self.w * self.h / REF_AREA)))
        gate = (knit.sstep(0.03, 0.30, knit._luma(self.src, 1.5)) * self.alpha).astype(np.float32)
        with self._lock:
            self._stretch['moire'] = (phase, slope, gate)
        return phase, slope, gate

    def moire_map(self, area):
        """The 摩尔纹效果's bands (moire_fringes) over the whole image at area (0..1), -1..1, gated like the texture:
        crops slice it. Kept for the area asked last. None while the depth model is not ready."""
        maps = self.moire_maps()
        if maps is None:
            return None
        with self._lock:
            kept = self._stretch.get('moire_bands')
        if kept is not None and kept[0] == area:
            return kept[1]
        phase, slope, gate = maps
        fringes = (moire_fringes(phase, slope, area) * gate).astype(np.float32)
        with self._lock:
            self._stretch['moire_bands'] = (area, fringes)
        return fringes

    def sparkle_map(self, kind):
        """One placed sparkle source, 0..1, cached: 'depth', 'bright' or 'painted'; None if not available (yet).
        ('even' needs no map: see sparkle_weight.)"""
        with self._lock:
            if kind in self._stretch:
                return self._stretch[kind]
        cover = self.alpha > 0.5
        if kind == 'painted':
            if self.sparkle is None:
                return None
            s = (self.sparkle.astype(np.float32) / 255) * cover
        elif kind == 'bright':
            s = highlight(self.src, self.R) * cover
        else:
            rel = self.relief_map()
            if rel is None:
                return None
            val = cv2.cvtColor(self.src, cv2.COLOR_BGR2HSV)[..., 2].astype(np.float32) / 255
            lit = knit.sstep(0.30, 0.62, cv2.GaussianBlur(val, (0, 0), 6))
            s = rel * (0.35 + 0.65 * lit) * cover
        with self._lock:
            self._stretch[kind] = s
        return s

    def sparkle_weight(self, q, style, sl=None):
        """Per-pixel sparkle weight for the style, combined over the sources with their amounts (q: clean params).

        Each source's map goes through the style's curve and is scaled by its amount; where sources overlap the
        higher one wins, so a spot both bulging and painted bright is not sparkled twice. Same random draws for
        every setting, so raising any amount only adds sparkles. Returns (weight or None, ready): ready is False
        while a source with a non-zero amount is still being computed (the depth model).
        """
        sl = sl if sl is not None else (slice(None), slice(None))
        cover = (self.alpha[sl] > 0.5)
        total, ready = None, True
        for kind in SPARKLE_KINDS:
            a = q[f'sparkle_{kind}'] / 100.0
            if a <= 0:
                continue
            if kind == 'even':
                w = a * EVEN_SPARKLES[style] * cover.astype(np.float32)
                total = w if total is None else np.maximum(total, w)
                continue
            m = self.sparkle_map(kind)
            if m is None:
                ready = ready and kind == 'painted'         # no 亮点 layer: nothing to wait for
                continue
            m = m[sl]
            w = m ** 1.2 if style == 'lines' else (0.15 + 0.85 * m) * cover
            w = a * w
            total = w if total is None else np.maximum(total, w)
        return total, ready

    def _gradients(self):
        """Course and across gradients of V, A inside the texture (vx, vy, ax, ay, same), cached."""
        with self._lock:
            if self._grads is not None:
                return self._grads
        same = _same_region(self.R)
        if self.cut is not None:
            same &= ~self.cut
        vy, vx = np.gradient(self.V)
        ay, ax = np.gradient(self.A)
        z = np.float32(0)
        grads = tuple(np.where(same, g, z).astype(np.float32) for g in (vx, vy, ax, ay)) + (same,)
        with self._lock:
            self._grads = grads
        return grads

    def densest(self, size=41):
        """(x, y) where the courses run densest inside the texture: moire shows there first."""
        with self._lock:
            if self._densest is not None:
                return self._densest
        vx, vy, _, _, same = self._gradients()
        if not same.any():
            return (self.w // 2, self.h // 2)
        f = np.hypot(vx, vy) * same
        cover = same.astype(np.float32)
        num = cv2.boxFilter(f, -1, (size, size), normalize=False)
        den = cv2.boxFilter(cover, -1, (size, size), normalize=False)
        score = np.where(den >= 0.6 * size * size, num / np.maximum(den, 1), 0)
        y, x = np.unravel_index(int(np.argmax(score)), score.shape)
        with self._lock:
            self._densest = (int(x), int(y))
        return self._densest

    def check(self, params):
        """Where the texture is missing or weak, for the diagnostic overlay: (faded, excluded) bool masks.
        faded: the courses are so dense that the anti-moire fade took more than half the texture away.
        excluded: inside a solved region, but coverage dropped the colour (gold trim, gloves, skin)."""
        _, fade = self.fade(params)
        return fade > 0.5, (self.REG > 0) & (self.R == 0)

    def fade(self, params):
        """(fraction of the texture faded by more than half, HxW float32 fade 0..1) for these settings."""
        q = clean_params(params)
        g = geometry(q['density'], self.w, self.h)
        vx, vy, ax, ay, same = self._gradients()
        p = g['period']
        if q['style'] == 'lines':
            th = np.deg2rad(q['tilt'])
            sn = np.sin(th * self.side).astype(np.float32)
            fx, fy = (np.cos(th) * vx + sn * ax) / p, (np.cos(th) * vy + sn * ay) / p
        else:
            fx, fy = vx / p, vy / p
        fade = knit.sstep(g['f_lo'], g['f_hi'], np.hypot(fx, fy)).astype(np.float32) * same
        n = int(same.sum())
        return (float((fade > 0.5).sum() / n) if n else 0.0), fade

    # ------------------------------------------------------------- rendering

    def render(self, params, rect=None):
        """BGR uint8 render of the whole image, or of rect = (x0, y0, x1, y1) (identical to that area of the whole).
        Returns (image, info); info says whether it is final: sparkles_ready and moire_ready are False while a
        sparkle source or the 摩尔纹效果 still waits for the depth model (what it needs is left out until then)."""
        q = self.resolve(clean_params(params))
        g = geometry(q['density'], self.w, self.h)
        if rect is None:
            key = tuple((k, q[k]) for k in RENDER_KEYS)
            with self._lock:
                if self._full[0] == key:
                    return self._full[1]
            x0, y0, x1, y1 = 0, 0, self.w, self.h
        else:
            x0, y0, x1, y1 = (int(v) for v in rect)
            x0, y0 = max(x0, 0), max(y0, 0)
            x1, y1 = min(x1, self.w), min(y1, self.h)
            if x1 <= x0 or y1 <= y0:
                raise ValueError(tr('预览区域在画面外'))
        X0, Y0 = max(x0 - MARGIN, 0), max(y0 - MARGIN, 0)
        X1, Y1 = min(x1 + MARGIN, self.w), min(y1 + MARGIN, self.h)
        sl = (slice(Y0, Y1), slice(X0, X1))
        src, R, V, A, alpha = self.src[sl], self.R[sl], self.V[sl], self.A[sl], self.alpha[sl]
        p, s = g['period'], q['strength'] / 100.0
        weight, ready = self.sparkle_weight(q, q['style'], sl)
        if q['style'] == 'coil':
            gn, gc = self.randoms('grain')[:2]
            see, trust = self.see_map()
            out, _ = knit.render_coil(src, R, V / p + 0.37 * R, A / (p * g['wale_ratio']), alpha, self.wide_luma()[sl],
                                      see[sl], trust[sl], (gn[sl], gc[sl]), amp=s, f_lo=g['f_lo'], f_hi=g['f_hi'])
        elif q['style'] in ('knit', 'loops'):
            draw = knit.render_thread if q['style'] == 'knit' else knit.render_loops
            out, _ = draw(src, R, V / p + 0.37 * R, A / (p * g['wale_ratio']), alpha, self.wide_luma()[sl],
                          amp=(0.10 if q['style'] == 'knit' else 0.12) * s, f_lo=g['f_lo'], f_hi=g['f_hi'])
        elif q['style'] == 'lines':
            th = np.deg2rad(q['tilt'])
            phase = np.cos(th) * V / p + np.sin(th * self.side[sl]) * A / p
            out, _ = knit.render_lines(src, R, phase, alpha, amp=0.115 * s, f_lo=g['f_lo'], f_hi=g['f_hi'])
        elif q['style'] == 'oily':
            maps = self.oily_maps()
            gn, gc = self.randoms('grain')[:2]
            out = oily.render_oily(src, R, V, A, alpha, g, s, *(m[sl] for m in maps), noise=(gn[sl], gc[sl]))
        else:
            gn, gc = self.randoms('grain')[:2]
            out, _ = knit.render_grain(src, R, V / p + 0.37 * R, A / (p * g['wale_ratio']), alpha, None,
                                       knit_amp=0.04 * s, grain=0.050 * s, grain_dark=0.020 * s,
                                       f_lo=g['f_lo'], f_hi=g['f_hi'], noise=(gn[sl], gc[sl]))
        moire_ready = True
        if moire_active(q):
            fringes = self.moire_map(q['moire_area'] / 100.0)
            if fringes is None:
                moire_ready = False                 # the depth model is not ready: the render is not final yet
            else:
                out = apply_moire(out, src, fringes[sl], q['moire'] / 100.0, self.suggested_strength() / 100.0)
        if weight is not None:
            r = SPARKLE_RECIPES[q['style']]
            u1, u2 = self.randoms('lines') if r['draws'] == 'lines' else self.randoms('grain')[2:]
            out = knit.add_sparkles(out, weight, None, density=r['density'], r_lo=r['r_lo'], r_hi=r['r_hi'],
                                    tint=r['tint'], draws=(u1[sl], u2[sl]))
        out = out[y0 - Y0:y1 - Y0, x0 - X0:x1 - X0]
        info = dict(g, style=q['style'], sparkles_ready=ready, moire_ready=moire_ready)
        if rect is None and ready and moire_ready:
            with self._lock:
                self._full = (key, (out, info))
        return out, info


def scene_from_doc(doc, disparity=None):
    """A Scene of the document's current solves and coverage."""
    REG, V, NX, NY, A = doc.fields()
    stock, alpha, _, _ = doc.coverage()
    names = [r.name for r in doc.regions]
    if not hasattr(doc, '_randoms'):
        doc._randoms = {}
    return Scene(doc.art, REG, V, A, stock, alpha, names, sparkle=doc.sparkle, disparity=disparity,
                 randoms=doc._randoms, cut=doc.cut_map(), fill=doc.filled_map())

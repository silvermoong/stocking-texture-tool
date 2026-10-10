"""Texture renderers for the stocking texture tool.

Started as a snapshot of an earlier standalone renderer; the tool owns this copy now.
Everything here is image-independent.
"""
import os

import cv2
import numpy as np
from PIL import Image

from . import tiles

SUFFIX = '丝袜纹理'


def load(path):
    """BGR uint8. cv2.imread silently fails on non-ASCII Windows paths; this does not."""
    img = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(path)
    return img


def write(path, img):
    ok, buf = cv2.imencode(os.path.splitext(path)[1], img)
    if not ok:
        raise IOError(path)
    buf.tofile(path)


def dil(mask, k):
    return cv2.dilate(mask.astype(np.uint8), np.ones((k, k), np.uint8)) > 0


def sstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def perspective_scale(v, gamma, v_ref, s_min=0.88, s_max=1.3):
    return np.clip(1 + gamma * (v - v_ref), s_min, s_max)


def perspective_phase(v, period, gamma, v_ref, s_min=0.88, s_max=1.3):
    """Course phase in cycles along surface coordinate v, period scaling as period*perspective_scale(v).

    Past the clamp the phase keeps advancing at the clamped period. Holding it constant there instead
    makes the courses vanish and leaves only wales (bare vertical stripes).
    """
    if gamma == 0:
        return v / period
    s = 1 + gamma * (v - v_ref)
    ph = np.log(np.clip(s, s_min, s_max)) / (gamma * period)
    for s_b, beyond in ((s_min, s < s_min), (s_max, s > s_max)):
        v_b = v_ref + (s_b - 1) / gamma
        ph = np.where(beyond, np.log(s_b) / (gamma * period) + (v - v_b) / (period * s_b), ph)
    return ph


# Contrast of the cos^1.3 thread profile the presets were tuned with, carried over to the sinusoid.
_t = np.linspace(0, 1, 4096, endpoint=False)
_d = ((1 + np.cos(2 * np.pi * _t)) / 2) ** 1.3
_GAIN = (_d.std() / (1 - _d.mean())) / np.sqrt(0.5)


def render(src, reg, phi, u, alpha, amp=0.16, zig=0.12, wale=0.10, f_lo=0.27, f_hi=0.34,
           tint=(0.90, 1.0, 1.10), dark=(0.03, 0.30)):
    """Multiply a knit pattern into src.

    reg: int region map, 0 = untouched; phase fields are never differentiated across a region border.
    phi: course phase in cycles. u: wale phase in cycles. alpha: 0..1 coverage.
    f_lo..f_hi: local frequency (cycles/px) over which each sinusoid fades out before it can alias.
    tint is B, G, R. Returns (out BGR uint8, gate) where gate is the per-pixel strength.
    """
    same = reg > 0
    for sh in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        same &= np.roll(reg, sh, axis=(0, 1)) == reg

    def grad(f):
        gy, gx = np.gradient(f)
        return np.where(same, gx, 0), np.where(same, gy, 0)

    def comp(phase, fx, fy):
        f = np.sqrt(fx * fx + fy * fy)
        return np.cos(2 * np.pi * phase) * (1 - sstep(f_lo, f_hi, f)) * np.sinc(fx) * np.sinc(fy)

    cx, cy = grad(phi)
    ux, uy = grad(u)
    zs = np.pi * zig
    keep_c = 1 - sstep(f_lo, f_hi, np.sqrt(cx * cx + cy * cy))
    m = comp(phi, cx, cy)
    # knit loops = first-order sidebands of a sideways wobble of each course; they live only where the courses do
    knit = zs * comp(phi + u, cx + ux, cy + uy) - zs * comp(phi - u, cx - ux, cy - uy) - 0.5 * wale * comp(u, ux, uy)
    m = np.where(same, m + knit * keep_c, 0) * _GAIN

    L = cv2.GaussianBlur(cv2.cvtColor(src, cv2.COLOR_BGR2HSV)[..., 2].astype(np.float32) / 255, (0, 0), 1.5)
    gate = sstep(dark[0], dark[1], L) * alpha
    res = src.astype(np.float64) * (1 - amp * (gate * m)[..., None] * np.asarray(tint)[None, None, :])
    return np.clip(np.round(res), 0, 255).astype(np.uint8), gate


def _same_region(reg):
    same = reg > 0
    for sh in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        same &= np.roll(reg, sh, axis=(0, 1)) == reg
    return same


def _luma(src, sigma):
    v = cv2.cvtColor(src, cv2.COLOR_BGR2HSV)[..., 2].astype(np.float32) / 255
    return cv2.GaussianBlur(v, (0, 0), sigma)


def render_lines(src, reg, phase, alpha, amp=0.115, f_lo=0.27, f_hi=0.34, tint=(0.92, 1.0, 1.08), dark=(0.03, 0.30)):
    """斜单线 style (the reference's 单线亮点), lines half: one band-limited line family along `phase` (cycles), no
    loops. Pair with add_sparkles."""
    same = _same_region(reg)
    gy, gx = np.gradient(phase)
    gx = np.where(same, gx, 0); gy = np.where(same, gy, 0)
    f = np.sqrt(gx * gx + gy * gy)
    m = np.where(same, np.cos(2 * np.pi * phase) * (1 - sstep(f_lo, f_hi, f)) * np.sinc(gx) * np.sinc(gy), 0)
    gate = sstep(dark[0], dark[1], _luma(src, 1.5)) * alpha
    res = src.astype(np.float64) * (1 - amp * (gate * m)[..., None] * np.asarray(tint)[None, None, :])
    return np.clip(np.round(res), 0, 255).astype(np.uint8), gate


_RIPS = {}
FLIP_SHARE = 0.25           # how much of a style's pol_band the gaps take to turn from lighter to darker than the stocking


def wide_luma(src):
    """Local lightness over ~25 px, 0..1: whether a stocking is light (gaps go darker) or dark (gaps go lighter)."""
    return cv2.GaussianBlur(_luma(src, 1.5), (0, 0), 8)


def _rip(name):
    if name not in _RIPS:
        make = {'thread': tiles.thread_gap_tile, 'loops': tiles.loops_gap_tile, 'coil': tiles.coil_gap_tile}[name]
        _RIPS[name] = tiles.ripmap(make())
    return _RIPS[name]


def gap_factor(src, reg, phi, u, alpha, wide, rip, amp, f_lo=0.27, f_hi=0.34, dark=(0.03, 0.30),
               pol_band=(0.40, 0.70)):
    """What render_gaps multiplies src by, as float32 HxWx3, and the gate. amp: a number, or an HxW array of
    amplitudes. pol_band: the local lightness (wide) between which the gaps turn from lighter to darker than the
    stocking; the turn itself takes only the middle FLIP_SHARE of it."""
    same = _same_region(reg)

    def footprint(f):
        gy, gx = np.gradient(f.astype(np.float32))
        return np.where(same, np.hypot(gx, gy), np.float32(0))

    fv = footprint(phi)
    keep = (1 - sstep(f_lo, f_hi, fv)) * same
    m = tiles.sample(rip, u, phi, footprint(u), fv) * keep
    gate = sstep(dark[0], dark[1], _luma(src, 1.5)) * alpha
    mid, half = sum(pol_band) / 2, (pol_band[1] - pol_band[0]) / 2 * FLIP_SHARE
    s = sstep(mid - half, mid + half, wide)[..., None].astype(np.float32)             # 0 on dark stockings, 1 on light
    to_dark = np.array([1.25, 1.1, 0.6], np.float32)                 # B, G, R: the gap as a pink line
    to_light = np.array([0.75, 0.95, 1.25], np.float32)              # the gap as a warm light line
    # Cross-fade the two drawings, and do it over a narrow band: they cancel where they meet, so a wide band left a
    # ring of plain fabric round a bright highlight, where the turn between them goes through the stocking's lightness.
    tint = (1 - s) * to_light - s * to_dark
    a = np.float32(amp) if np.ndim(amp) == 0 else np.asarray(amp, np.float32)[..., None]
    return 1 + a * (gate * m).astype(np.float32)[..., None] * tint, gate


def render_gaps(src, reg, phi, u, alpha, wide, rip, amp, f_lo=0.27, f_hi=0.34, dark=(0.03, 0.30)):
    """A knit drawn as the gaps between its yarn, where the skin shows through: rip is a ripmap of a tiles.*_gap_tile
    (one course by one wale, positive in the gaps).

    The gaps take the skin's colour: on light stockings they darken toward pink, on dark ones they lighten toward a
    warm tone. phi: course phase in cycles; u: wale phase in cycles; wide: wide_luma() of the whole image (cropped
    like src), so a crop renders exactly like the same area of the whole. Returns (out BGR uint8, gate).
    """
    f, gate = gap_factor(src, reg, phi, u, alpha, wide, rip, amp, f_lo, f_hi, dark)
    res = src.astype(np.float32) * f
    return np.clip(np.round(res), 0, 255).astype(np.uint8), gate


def render_thread(src, reg, phi, u, alpha, wide, amp=0.10, **kw):
    """细线: wide threads, a thin gap between courses (modelled on a drawing of white knit stockings: white
    threads, thin pink lines between them). See render_gaps."""
    return render_gaps(src, reg, phi, u, alpha, wide, _rip('thread'), amp, **kw)


def render_loops(src, reg, phi, u, alpha, wide, amp=0.12, **kw):
    """针织: columns of V-shaped stitch loops, as on a stocking's reinforced sole. See render_gaps."""
    return render_gaps(src, reg, phi, u, alpha, wide, _rip('loops'), amp, **kw)


# 线圈 varies with how much skin shows through the stocking (see, 0..1: look.skin_visibility). Two drawings of black
# stockings by the one artist were cut into windows and every window measured; against see the two agree to within
# 0.01 in each bin. (Predicting the same texture from the painting's brightness, from the depth or from the facing
# the guide lines give came out worse, and did not carry over from one drawing to the other.) Where no skin shows
# the texture is a rough grain at a relative contrast of 0.07; where it does, the lattice takes over and the contrast
# climbs to 0.19. SEE_LATTICE is the lattice's share of the texture: how regular it is (its autocorrelation at the
# cell spacing), rescaled to 0..1. The loops' height also changes along those legs, but with position and not with
# any of these, and the tool spaces its courses evenly by design, so that is not modelled.
SEE_AT = (0.0, 0.075, 0.225, 0.375, 0.525, 0.675, 0.825, 0.95, 1.0)
SEE_CONTRAST = (0.070, 0.070, 0.072, 0.092, 0.108, 0.131, 0.146, 0.178, 0.190)
SEE_LATTICE = (0.0, 0.0, 0.28, 0.56, 0.76, 0.85, 0.95, 1.0, 1.0)
# Relative contrast (the std of the high-passed lightness over its mean, measured as on the drawings) of the tile at
# amplitude 1 and of the grain at amplitude 1, rendered at the drawings' own cell size (3.7 x 5.9 px, density 124%).
LATTICE_UNIT = 0.424
GRAIN_UNIT = 0.97
COIL_FLAT = 0.12            # lattice amplitude where the colour says nothing about skin: what 线圈 drew before it varied
COIL_DARK = (0.02, 0.10)    # the texture is a ratio, so near-black needs little fading
COIL_POL = (0.55, 0.80)     # lightness where the windows stop being lighter than the stocking: the skin's own, higher


def coil_gains(see, trust):
    """Lattice and grain amplitudes (float32, per pixel) at 100% strength for a skin-visibility map and its trust."""
    c = np.interp(see, SEE_AT, SEE_CONTRAST)
    share = np.interp(see, SEE_AT, SEE_LATTICE)
    lat = np.sqrt(share) * c / LATTICE_UNIT
    grain = np.sqrt(1 - share) * c / GRAIN_UNIT
    return (trust * lat + (1 - trust) * COIL_FLAT).astype(np.float32), (trust * grain).astype(np.float32)


def render_coil(src, reg, phi, u, alpha, wide, see, trust, noise, amp=1.0, chroma=0.35, **kw):
    """线圈: plain knit drawn loop by loop from its yarn path, every loop the same so the rows and columns run
    straight (see tiles.coil_gap_tile), over a fine grain, in the proportions the skin showing through (see) sets:
    see 0..1 and trust 0..1 are look.skin_visibility's, noise is (g, gc) of grain_noise, amp the strength (1 = 100%).
    Returns (out BGR uint8, gate). Other arguments: see gap_factor."""
    lat, grain = coil_gains(see, trust)
    kw.setdefault('dark', COIL_DARK)
    f, gate = gap_factor(src, reg, phi, u, alpha, wide, _rip('coil'), amp * lat, pol_band=COIL_POL, **kw)
    g, gc = noise
    ggate = sstep(COIL_DARK[0], COIL_DARK[1], _luma(src, 1.5)) * alpha
    f = f + (amp * grain * ggate).astype(np.float32)[..., None] * (g[..., None] + chroma * gc)
    res = src.astype(np.float32) * f
    return np.clip(np.round(res), 0, 255).astype(np.uint8), np.maximum(gate, ggate)


def grain_noise(rng, h, w, sigma=0.6):
    """The grain field render_grain draws: (g HxW, gc HxWx3), each blurred and normalised to unit std."""
    g = cv2.GaussianBlur(rng.standard_normal((h, w)).astype(np.float32), (0, 0), sigma)
    g /= g.std()
    gc = cv2.GaussianBlur(rng.standard_normal((h, w, 3)).astype(np.float32), (0, 0), sigma)
    gc /= gc.std()
    return g, gc


def render_grain(src, reg, phi, u, alpha, rng, knit_amp=0.04, grain=0.050, grain_dark=0.020, chroma=0.35, sigma=0.6,
                 f_lo=0.29, f_hi=0.35, dark=(0.02, 0.16), noise=None):
    """加濑风 style, grain half: 1-2 px grain (heavier toward the darks, faintly chromatic) over a faint knit.

    Pair with add_sparkles(neutral). Returns (out, gate) with gate covering both layers. noise: a precomputed
    grain_noise() field (or a crop of one) instead of drawing from rng.
    """
    faint, gate_k = render(src, reg, phi, u, alpha, amp=knit_amp, f_lo=f_lo, f_hi=f_hi)
    h, w = src.shape[:2]
    g, gc = grain_noise(rng, h, w, sigma) if noise is None else noise
    L = _luma(src, 1.5)
    gate = sstep(dark[0], dark[1], L) * alpha
    rel = grain + grain_dark * (1 - sstep(0.25, 0.65, L))
    noise = g[..., None] + chroma * gc
    out = faint.astype(np.float64) * (1 + (rel * gate)[..., None] * noise)
    return np.clip(np.round(out), 0, 255).astype(np.uint8), np.maximum(gate, gate_k)


def add_sparkles(img, weight, rng, density, r_lo, r_hi, tint=None, draws=None):
    """Scatter single-pixel highlights with probability density*weight; random, so they never alias.

    Strength r in r_lo..r_hi, skewed toward r_lo. tint (B, G, R) brightens multiplicatively in that colour;
    tint=None adds neutral light (whitish flecks). draws: two precomputed uniform HxW fields (or crops of them),
    used instead of drawing from rng in the same order.
    """
    h, w = img.shape[:2]
    u_hit, u_r = (rng.random((h, w)), rng.random((h, w))) if draws is None else draws
    hit = u_hit < density * weight
    r = r_lo + (r_hi - r_lo) * u_r ** 2
    out = img.astype(np.float64)
    if tint is None:
        add = (r[..., None] * out.mean(axis=2, keepdims=True)) * np.ones(3)[None, None, :]
        out = np.where(hit[..., None], out + add, out)
    else:
        out = np.where(hit[..., None], out * (1 + r[..., None] * np.asarray(tint)[None, None, :]), out)
    return np.clip(np.round(out), 0, 255).astype(np.uint8)


def debug_isolines(src, reg, v, path, step=16.0):
    """Draw iso-lines of surface coordinate v every `step` px, one colour per region."""
    out = src.copy()
    palette = [(0, 255, 255), (255, 255, 0), (0, 255, 0), (255, 0, 255), (0, 128, 255), (255, 128, 0)]
    fr = (v / step) % 1.0
    line = (fr < 0.09) | (fr > 0.91)
    for i, r in enumerate(np.unique(reg[reg > 0])):
        out[(reg == r) & line] = palette[i % len(palette)]
    write(path, out)


def inspect(src, out, workdir, crops):
    """Write the inspection set; returns the paths to view.

    crops: {name: (x0, y0, x1, y1)}. Each crop is saved at 100% and 200% nearest-neighbour; the whole image at
    50% linear and 40% area (how viewers and Photoshop show it zoomed out), plus a diff overlay marking every
    changed pixel in green.
    """
    h, w = out.shape[:2]
    paths = {}
    p = os.path.join(workdir, 'whole_50_linear.png')
    write(p, cv2.resize(out, (w // 2, h // 2), interpolation=cv2.INTER_LINEAR)); paths['50%'] = p
    p = os.path.join(workdir, 'whole_40_area.png')
    write(p, cv2.resize(out, (w * 2 // 5, h * 2 // 5), interpolation=cv2.INTER_AREA)); paths['40%'] = p
    diff = np.abs(out.astype(np.int16) - src.astype(np.int16)).max(axis=2) > 0
    vis = src // 3
    vis[diff] = (0, 255, 0)
    p = os.path.join(workdir, 'diff.png')
    write(p, cv2.resize(vis, (w // 2, h // 2), interpolation=cv2.INTER_AREA)); paths['diff'] = p
    for name, (x0, y0, x1, y1) in crops.items():
        c = out[y0:y1, x0:x1]
        p = os.path.join(workdir, f'crop_{name}_100.png'); write(p, c); paths[f'{name} 100%'] = p
        p = os.path.join(workdir, f'crop_{name}_200.png')
        write(p, cv2.resize(c, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)); paths[f'{name} 200%'] = p
    return paths


def save_outputs(src_path, out, gate, tag=''):
    """Write <stem>-丝袜纹理[-tag].png and its Photoshop layer next to the source, and prove the layer is exact.

    The layer is RGBA: result pixels wherever the texture touched, transparent elsewhere. Placed on top of the
    original in Normal mode it reproduces the result exactly, so lowering its opacity is an exact strength dial.
    """
    stem = os.path.splitext(src_path)[0]
    name = f'{SUFFIX}-{tag}' if tag else SUFFIX
    p_full, p_layer = f'{stem}-{name}.png', f'{stem}-{name}-图层.png'
    orig = Image.open(src_path)
    kw = {'dpi': orig.info['dpi']} if 'dpi' in orig.info else {}
    s = np.asarray(orig.convert('RGB'))
    o = np.ascontiguousarray(out[..., ::-1])
    if o.shape != s.shape:
        raise ValueError(f'size mismatch {o.shape} vs {s.shape}')
    if 'A' in orig.getbands():
        full = Image.fromarray(np.dstack([o, np.asarray(orig.getchannel('A'))]))
    else:
        full = Image.fromarray(o)
    full.save(p_full, optimize=True, **kw)
    a = np.where(gate > 0.001, 255, 0).astype(np.uint8)
    Image.fromarray(np.dstack([o, a])).save(p_layer, optimize=True, **kw)
    L = np.asarray(Image.open(p_layer)).astype(np.float64)
    comp = s * (1 - L[..., 3:] / 255) + L[..., :3] * (L[..., 3:] / 255)
    err = np.abs(np.round(comp) - o).max()
    if err != 0:
        raise AssertionError(f'layer does not reproduce the result (max err {err})')
    return p_full, p_layer

import cv2
import numpy as np
import pytest

from stocking import coverage, knit, look, oily, tiles
from stocking import guide_fields as gf
from stocking import psd_io

from sample_data import PSD, require

OFF = {'sparkle_depth': 0, 'sparkle_bright': 0, 'sparkle_painted': 0, 'sparkle_link': False}
PAINTED = {'sparkle_depth': 0, 'sparkle_bright': 0, 'sparkle_painted': 100, 'sparkle_link': False}


@pytest.fixture(scope='module')
def fx():
    """The sample solved exactly as tests/verify.py solves it."""
    require()
    art, regions, strokes, _ = psd_io.read_guides(PSD)
    names, masks = list(regions), list(regions.values())
    REG, V, NX, NY, A = gf.solve_guides(masks, strokes)
    stock, alpha = coverage.stocking_coverage(coverage.lab_of(art), REG)
    return art, names, REG, V, A, stock, alpha


def scene(fx, **kw):
    art, names, REG, V, A, stock, alpha = fx
    return look.Scene(art, REG, V, A, stock, alpha, names, **kw)


def test_geometry():
    g = look.geometry(100, 1280, 1920)
    assert g['period'] == 4.6 and (g['f_lo'], g['f_hi'], g['wale_ratio']) == (0.27, 0.34, 1.25) and not g['clamped']
    assert abs(look.geometry(124, 1280, 1920)['period'] - 3.71) < 0.01
    assert abs(look.geometry(135, 1280, 1920)['period'] - 3.41) < 0.01
    small = look.geometry(100, 832, 1216)                        # common SD renders land below the floor
    assert small['clamped'] and small['period'] == 3.2 and abs(small['raw_period'] - 2.95) < 0.01
    assert (small['f_lo'], small['f_hi']) == (0.30, 0.36)
    assert abs(look.geometry(100, 1280, 1920)['max_density'] - 143.75) < 0.01


def test_side_of():
    assert [look.side_of(n) for n in ('左腿', '右胸', '胯部', '胸部-左', '中间-右', '左胸-右')] == [1, -1, 0, 1, -1, -1]


def test_defaults_reproduce_verify_renders(fx):
    """tests/verify.py's lines render, call for call; the reference's 针织 (knit) is the tool's 细线, called as below."""
    art, names, REG, V, A, stock, alpha = fx
    src = np.ascontiguousarray(art[..., ::-1])
    R = np.where(stock, REG, 0).astype(np.int8)
    period = 4.6
    ref_knit, _ = knit.render_thread(src, R, V / period + 0.37 * R, A / (period * 1.25), alpha, knit.wide_luma(src))
    theta = np.deg2rad(32)
    side = np.select([np.isin(R, [1, 4]), np.isin(R, [2, 5])], [1.0, -1.0], 0.0)
    ref_lines, _ = knit.render_lines(src, R, np.cos(theta) * V / period + np.sin(theta * side) * A / period, alpha)
    s = scene(fx)
    out, info = s.render(dict(OFF, style='knit'))
    assert np.array_equal(out, ref_knit) and info['period'] == 4.6
    out, _ = s.render(dict(OFF, style='lines'))
    assert np.array_equal(out, ref_lines)


def _flat(rgb, h=240, w=240, freq=1.0):
    """A flat swatch of one colour, courses running across (V = y * freq), one region."""
    art = np.empty((h, w, 3), np.uint8)
    art[...] = rgb
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    REG = np.ones((h, w), np.int8)
    return look.Scene(art, REG, yy * freq, xx, np.ones((h, w), bool), np.ones((h, w)), ['左腿'])


@pytest.mark.parametrize('style', ['knit', 'loops', 'coil'])
@pytest.mark.parametrize('rgb, darker', [((223, 216, 226), True), ((62, 50, 58), False)])
def test_thread_gaps_take_the_skin_colour(style, rgb, darker):
    """White stockings: thin pink lines between the threads; black ones: thin warm light lines."""
    s = _flat(rgb)
    out, info = s.render(dict(OFF, style=style, strength=100, strength_auto=False))
    d = out.astype(float)[20:-20, 20:-20] - s.src.astype(float)[20:-20, 20:-20]     # B, G, R
    lum = d @ [0.114, 0.587, 0.299]
    gap = lum < -3 if darker else lum > 3
    assert 0.05 < gap.mean() < 0.4                                     # thin lines, not half the area
    prof = lum.mean(1) - lum.mean()
    spec = np.abs(np.fft.rfft(prof * np.hanning(prof.size)))
    f = np.fft.rfftfreq(prof.size)[np.argmax(spec[1:]) + 1]
    assert abs(1 / f - info['period']) < 0.3                           # one gap per course
    b, g, r = d[gap].mean(0)
    assert (r > b) and (r > g)                                         # warmer than the stocking either way


@pytest.mark.parametrize('style', ['knit', 'loops', 'coil'])
def test_texture_does_not_vanish_between_dark_and_light(style):
    """The gaps turn from lighter to darker than the stocking as it goes from dark to light. The drawing fades from
    one to the other; it must not cancel half way (a plain ring round a bright highlight)."""
    ramp = np.linspace(0, 1, 240)[None, :, None]
    art = np.round((1 - ramp) * np.array([62, 50, 58]) + ramp * np.array([240, 232, 240]))
    s = _flat(np.broadcast_to(art, (240, 240, 3)))
    out, _ = s.render(dict(OFF, style=style, strength=100, strength_auto=False))
    rel = ((out.astype(float) - s.src.astype(float)) / np.maximum(s.src, 1))[20:-20, 20:-20]
    contrast = [np.sqrt((rel[:, c:c + 4] ** 2).mean()) for c in range(0, 200, 4)]      # dark to light, in 4-column steps
    assert min(contrast) > 0.15 * min(contrast[0], contrast[-1])


@pytest.mark.parametrize('style', ['loops', 'coil'])
def test_loops_stand_in_columns(style):
    """针织 and 线圈 repeat across the wales too (one column of loops per wale); 细线 barely does."""
    def peak_period(style):
        s = _flat((223, 216, 226))
        out, info = s.render(dict(OFF, style=style, strength=100, strength_auto=False))
        lum = (out.astype(float) - s.src.astype(float))[20:-20, 20:-20] @ [0.114, 0.587, 0.299]
        prof = lum.mean(0) - lum.mean()
        spec = np.abs(np.fft.rfft(prof * np.hanning(prof.size)))
        k = np.argmax(spec[1:]) + 1
        return 1 / np.fft.rfftfreq(prof.size)[k], spec[k] / prof.size, info
    period, amp, info = peak_period(style)
    assert abs(period - info['period'] * info['wale_ratio']) < 0.4
    assert amp > 3 * peak_period('knit')[1]


def test_coil_is_every_loop_the_same():
    """线圈 is for painting over: no loop wobbles, so the tile is one loop and mirror-symmetric about its wale."""
    t = tiles.coil_gap_tile()
    assert abs(t.mean()) < 1e-3 and abs(t.std() - 1) < 1e-3
    assert np.array_equal(t, t[:, ::-1])


def test_coil_shows_the_courses_as_seams_between_the_cells():
    """A loop is a closed ring, so the courses show as seams between the loops. 针织's V's run on down each wale as
    one stripe: 3% of its variance in the course lines, 81% in the wale lines. 线圈: 33% and 60%."""
    s = _flat((100, 88, 96))
    out, _ = s.render(dict(OFF, style='coil', strength=100, strength_auto=False))
    lum = ((out.astype(float) - s.src.astype(float)) @ [0.114, 0.587, 0.299])[30:-30, 30:-30]
    assert lum.mean(1).var() / lum.var() > 0.2
    assert lum.mean(0).var() / lum.var() < 0.7


def test_coil_loop_stays_inside_the_limits_of_a_real_plain_knit():
    length = tiles.loop_length()
    assert 5.0 <= length / tiles.COURSE <= 5.6                      # Munden: a relaxed loop holds 5.0-5.6 courses of yarn
    assert tiles.LOOP['width'] <= length / 16.66                    # Peirce: even jammed, a loop is 16.7 yarn widths
    assert 2 * tiles.LOOP['spread'] + tiles.LOOP['width'] <= 1.0    # neighbouring loops touch, they do not overlap


def _warm_ramp(h=240, w=300):
    """One stocking going from cool blue-grey on the left to warm brown-pink on the right: skin showing more and more."""
    x = np.linspace(0, 1, w)[None, :] * np.ones((h, 1))
    art = np.empty((h, w, 3), np.float32)
    art[..., 0], art[..., 1], art[..., 2] = 60 + 85 * x, 70 + 25 * x, 80 - 20 * x          # R, G, B
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    return look.Scene(art.astype(np.uint8), np.ones((h, w), np.int8), yy, xx, np.ones((h, w), bool),
                      np.ones((h, w)), ['左腿'])


def test_skin_visibility_reads_the_warmth_of_the_painting():
    see, trust = _warm_ramp().see_map()
    assert trust.min() == 1.0
    assert see[:, 10].max() < 0.1 and see[:, -10].min() > 0.85
    assert np.all(np.diff(see[120, 15:-15]) > -0.01)                # warmer to the right, never back
    # brightness alone is not skin: a flat swatch and a plain grey ramp have nothing to read
    grey = np.empty((240, 300, 3), np.uint8)
    grey[...] = (40 + 100 * np.linspace(0, 1, 300))[None, :, None].astype(np.uint8)
    yy, xx = np.mgrid[0:240, 0:300].astype(np.float64)
    ramp = look.Scene(grey, np.ones((240, 300), np.int8), yy, xx, np.ones((240, 300), bool), np.ones((240, 300)), ['左腿'])
    assert _flat((90, 80, 100)).see_map()[1].max() == 0 and ramp.see_map()[1].max() == 0


def test_coil_is_a_lattice_where_skin_shows_and_rough_grain_where_it_does_not():
    """The artist's stockings (two drawings, same numbers): no skin, a rough grain at 0.07 relative contrast; skin
    showing, the neat lattice at up to 0.19. On the ramp from cool to warm the courses are seams on the warm side only."""
    s = _warm_ramp()
    out, _ = s.render(dict(OFF, style='coil', strength=100, strength_auto=False))
    d = ((out.astype(float) - s.src.astype(float)) @ [0.114, 0.587, 0.299])[20:-20]
    base = (s.src.astype(float) @ [0.114, 0.587, 0.299])[20:-20]
    cool, warm = slice(20, 90), slice(210, 280)
    assert (d[:, warm] / base[:, warm]).std() > 1.5 * (d[:, cool] / base[:, cool]).std()
    lines = [d[:, sl].mean(1).var() / d[:, sl].var() for sl in (cool, warm)]
    assert lines[1] > 0.2 and lines[0] < 0.1


def test_coil_amplitudes_reproduce_the_artists_contrast():
    see = np.array(knit.SEE_AT, np.float32)
    lat, grain = knit.coil_gains(see, np.ones_like(see))
    assert np.allclose(np.hypot(lat * knit.LATTICE_UNIT, grain * knit.GRAIN_UNIT), knit.SEE_CONTRAST, rtol=0.01)
    assert lat[0] == 0 and grain[0] > 0 and grain[-1] == 0          # grain without skin, the lattice alone with it
    lat0, grain0 = knit.coil_gains(see, np.zeros_like(see))
    assert np.all(lat0 == knit.COIL_FLAT) and not grain0.any()      # nothing to read: the flat texture it drew before


def test_coil_crop_equals_the_same_area_of_the_whole():
    s = _warm_ramp()
    q = dict(OFF, style='coil', strength=100, strength_auto=False)
    whole, _ = s.render(q)
    crop, _ = s.render(q, rect=(37, 51, 151, 133))
    assert np.array_equal(whole[51:133, 37:151], crop)


def test_thread_fades_out_instead_of_aliasing():
    s = _flat((223, 216, 226), freq=1.6)                               # courses far too dense for the pixels
    out, _ = s.render(dict(OFF, style='knit', strength=100, strength_auto=False))
    assert np.abs(out.astype(int) - s.src.astype(int))[20:-20, 20:-20].max() <= 2


def test_tile_sampler():
    t = np.arange(16, dtype=np.float32).reshape(4, 4)
    rip = tiles.ripmap(t)
    v, u = np.mgrid[0:4, 0:4]
    exact = tiles.sample(rip, (u + 0.5) / 4, (v + 0.5) / 4 + 3, np.full(u.shape, 1e-3), np.full(u.shape, 1e-3))
    assert np.allclose(exact, t)                                       # texel centres, wrapped repeats
    blurred = tiles.sample(rip, (u + 0.5) / 4, (v + 0.5) / 4, np.full(u.shape, 2.0), np.full(u.shape, 1e-3))
    assert np.allclose(blurred, t.mean(1, keepdims=True).repeat(4, 1))  # only u averaged out


def test_grain_and_sparkles_reproduce_the_reference_renders(fx):
    """加濑风 and 斜单线 as the reference renders drew them: same calls, same seed, same draw order."""
    art, names, REG, V, A, stock, alpha = fx
    rng0 = np.random.default_rng(1)
    painted = (rng0.random(REG.shape) * 255).astype(np.uint8)
    s = scene(fx, sparkle=painted)
    stretch = (painted.astype(np.float32) / 255) * (alpha > 0.5)
    src = np.ascontiguousarray(art[..., ::-1])
    R = np.where(stock, REG, 0).astype(np.int8)
    g = look.geometry(124, 1280, 1920)
    p, wr = g['period'], g['wale_ratio']
    rng = np.random.default_rng(look.SEED)
    ref, _ = knit.render_grain(src, R, V / p + 0.37 * R, A / (p * wr), alpha, rng, f_lo=g['f_lo'], f_hi=g['f_hi'])
    ref = knit.add_sparkles(ref, (0.15 + 0.85 * stretch) * (alpha > 0.5), rng, density=0.014, r_lo=0.12, r_hi=0.38)
    out, _ = s.render(dict(PAINTED, style='grain', density=124))
    assert np.array_equal(out, ref)

    rng = np.random.default_rng(look.SEED)
    lines, _ = s.render(dict(OFF, style='lines'))
    ref = knit.add_sparkles(lines, stretch ** 1.2, rng, density=0.045, r_lo=0.18, r_hi=0.55, tint=(0.95, 1.0, 1.08))
    out, _ = s.render(dict(PAINTED, style='lines'))
    assert np.array_equal(out, ref)


@pytest.mark.parametrize('style', look.STYLES)
def test_crop_equals_full(fx, style):
    s = scene(fx, sparkle=np.full(fx[2].shape, 200, np.uint8))
    p = {'style': style, 'density': 128, 'tilt': 25, 'strength': 140, 'sparkle_depth': 0, 'sparkle_bright': 80,
         'sparkle_painted': 150, 'sparkle_even': 60, 'sparkle_link': False}
    full, _ = s.render(p)
    for rect in [(300, 320, 812, 832), (0, 0, 64, 64), (1100, 1800, 1280, 1920)]:
        crop, _ = s.render(p, rect)
        x0, y0, x1, y1 = rect
        assert np.array_equal(crop, full[y0:y1, x0:x1]), rect


def test_auto_strength_lowers_on_light_stockings(fx):
    """100% was tuned on dark stockings; on white the same ratio is about twice the lightness step, so auto halves it."""
    art, names, REG, V, A, stock, alpha = fx
    assert scene(fx).suggested_strength() == 100.0               # the tuning fixture keeps its tuned strength
    white = np.empty_like(art)
    white[...] = (223, 216, 226)                                  # RGB of the white stockings the user tested
    s = look.Scene(white, REG, V, A, np.ones_like(stock), np.ones_like(alpha), names)
    sug = s.suggested_strength()
    assert 40 <= sug <= 50 and sug % 5 == 0
    auto, _ = s.render(dict(OFF, style='knit'))
    manual, _ = s.render(dict(OFF, style='knit', strength=sug, strength_auto=False))
    assert np.array_equal(auto, manual)
    assert look.Scene(np.zeros_like(art), REG, V, A, stock, alpha, names).suggested_strength() == 100.0


def test_auto_strength_settings():
    assert look.clean_params({})['strength_auto'] is True
    assert look.clean_params({'strength': 140})['strength_auto'] is False        # saved before auto: slider was moved
    assert look.clean_params({'strength': 100})['strength_auto'] is True
    assert look.clean_params({'strength': 60, 'strength_auto': 'true'})['strength_auto'] is True
    assert look.clean_params({'strength_auto': 'false'})['strength_auto'] is False


@pytest.mark.parametrize('style', look.STYLES)
def test_even_sparkles_spread_everywhere(fx, style):
    """Every style scatters sparkles (亮点), by the same settings."""
    art, names, REG, V, A, stock, alpha = fx
    s = scene(fx)
    on = dict(OFF, style=style, sparkle_even=100)
    w, ready = s.sparkle_weight(look.clean_params(on), style)
    cover = alpha > 0.5
    assert ready and np.allclose(w[cover], look.EVEN_SPARKLES[style]) and (w[~cover] == 0).all()
    base, _ = s.render(dict(OFF, style=style))
    out, _ = s.render(on)
    hit = np.abs(out.astype(int) - base.astype(int)).max(axis=2) > 0
    rows = np.array_split(np.flatnonzero(cover.any(1)), 4)              # top to bottom, all get their share
    shares = [hit[r].sum() / max(cover[r].sum(), 1) for r in rows]
    assert min(shares) > 0.5 * max(shares)


@pytest.mark.parametrize('style', look.STYLES)
def test_strength_leaves_sparkles_alone(fx, style):
    """强度 scales the texture only: a sparkle lifts its pixel by the same ratio at any strength."""
    s = scene(fx)
    rect = (300, 320, 812, 832)

    def lift(strength):
        p = dict(OFF, style=style, strength=strength, strength_auto=False)
        base = s.render(p, rect)[0].astype(float).sum(axis=2)
        out = s.render(dict(p, sparkle_even=100), rect)[0].astype(float)
        hit = (out.sum(axis=2) != base) & (base > 90) & (out.max(axis=2) < 250)
        return hit, np.where(hit, out.sum(axis=2) / np.maximum(base, 1) - 1, 0)

    hit_lo, lo = lift(30)
    hit_hi, hi = lift(200)
    both = hit_lo & hit_hi
    assert both.sum() > 200
    assert abs(np.median(lo[both]) / np.median(hi[both]) - 1) < 0.1


def test_removed_bulge_setting_is_ignored_and_nothing_waits_for_depth(fx):
    """起伏松紧 is gone: an old saved 'bulge' is dropped, and while depth is still being estimated a style without
    depth sparkles renders final (nothing is waiting for it)."""
    assert 'bulge' not in look.clean_params({'bulge': 150})
    pending = scene(fx, disparity=lambda: None)
    out, info = pending.render(dict(OFF, style='knit', bulge=150))
    assert info['sparkles_ready'] and np.array_equal(out, scene(fx).render(dict(OFF, style='knit'))[0])


def test_removed_centre_slider_is_ignored():
    """居中 was a slider for a while and is automatic now: a setting or a preset saved with it reads without it."""
    assert 'centre' not in look.clean_params({'style': 'oily', 'centre': 60})


def test_densest_point_and_fade(fx):
    s = scene(fx)
    x, y = s.densest()
    assert s.R[y, x] > 0
    low, _ = s.fade({'density': 100})
    high, fade = s.fade({'density': 140})
    assert 0 <= low < high <= 1 and fade.shape == s.R.shape


def test_depth_stretch_is_per_region_and_lit(fx):
    art, names, REG, V, A, stock, alpha = fx
    disp = np.tile(np.linspace(0, 1, REG.shape[1], dtype=np.float32), (REG.shape[0], 1))
    s = scene(fx, disparity=lambda: disp)
    st = s.sparkle_map('depth')
    assert st.min() >= 0 and st.max() <= 1
    assert (st[alpha <= 0.5] == 0).all()
    for i in range(1, 6):                                      # every region reaches near 1 at its nearest part
        m = (s.R == i) & (alpha > 0.5)
        assert st[m].max() > 0.3
    assert scene(fx).sparkle_map('depth') is None                # no depth yet: no sparkles, no crash


def test_relief_favours_the_crown_over_the_nearest_end():
    """A leg pointing at the camera: disparity rises toward the foot and bulges across the leg's crown. Raw nearness
    put every sparkle on the foot; relief puts them along the crown, at every height."""
    h, w = 600, 200
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    R = ((np.abs(xx - 100) < 60) & (yy > 20) & (yy < 580)).astype(np.int8)
    across = np.clip(1 - ((xx - 100) / 60) ** 2, 0, 1)
    disp = yy / h * 3.0 + 1.0 * np.sqrt(across)
    s = look.relief(disp, R)
    crown, side = np.abs(xx - 100) < 12, (np.abs(xx - 100) > 40) & (np.abs(xx - 100) < 55)
    top, foot = (yy > 60) & (yy < 200), yy > 450
    m = R > 0
    assert s[m & crown & top].mean() > 3 * s[m & side & top].mean()
    assert s[m & crown & top].mean() > 0.5 * s[m & crown & foot].mean()


def test_sparkle_amounts_add_without_moving(fx):
    s = scene(fx, sparkle=np.full(fx[2].shape, 200, np.uint8))
    plain, _ = s.render(dict(OFF, style='lines'))
    hits = {}
    for amount in (0, 50, 100, 200):
        out, _ = s.render(dict(OFF, style='lines', sparkle_painted=amount))
        hits[amount] = np.abs(out.astype(int) - plain.astype(int)).max(2) > 0
    assert not hits[0].any()
    assert hits[50].sum() < hits[100].sum() < hits[200].sum()
    assert not (hits[50] & ~hits[100]).any() and not (hits[100] & ~hits[200]).any()


def test_check_maps(fx):
    s = scene(fx)
    faded, excluded = s.check({'density': 135})
    assert faded.shape == excluded.shape == s.R.shape
    assert not (faded & excluded).any()
    assert excluded.any() and (s.REG[excluded] > 0).all() and (s.R[excluded] == 0).all()
    assert faded.sum() > s.check({'density': 100})[0].sum()


def test_highlight_source_follows_painted_light(fx):
    """按画面亮部: sparkles follow where the art is painted brighter than its surroundings."""
    art, names, REG, V, A, stock, alpha = fx
    lit = art.copy()
    m = (REG == 4) & stock
    ys, xs = np.nonzero(m)
    cy, cx = int(ys.mean()), int(xs.mean())
    spot = np.zeros(REG.shape, np.uint8)
    cv2.circle(spot, (cx, cy), 40, 1, -1)
    lit[(spot > 0) & m] = np.clip(lit[(spot > 0) & m].astype(int) + 60, 0, 255).astype(np.uint8)
    s = look.Scene(lit, REG, V, A, stock, alpha, names)
    st = s.sparkle_map('bright')
    base = look.Scene(art, REG, V, A, stock, alpha, names).sparkle_map('bright')
    assert st.min() >= 0 and st.max() <= 1 and (st[alpha <= 0.5] == 0).all()
    inside = (spot > 0) & m & (alpha > 0.5)
    far = (REG != 4) & (alpha > 0.5)
    assert st[inside].mean() > 0.6 and st[inside].mean() - base[inside].mean() > 0.3
    assert np.abs(st[far] - base[far]).max() < 1e-6        # other regions are untouched
    for style in ('lines', 'grain'):
        p = {'style': style, 'sparkle_depth': 0, 'sparkle_bright': 100, 'sparkle_link': False, 'density': 120}
        full, info = s.render(p)
        assert info['sparkles_ready']
        crop, _ = s.render(p, (cx - 100, cy - 100, cx + 100, cy + 100))
        assert np.array_equal(crop, full[cy - 100:cy + 100, cx - 100:cx + 100])


def test_overlapping_sources_take_the_higher(fx):
    """Depth and brightness each have an amount; where both want sparkles the higher weight wins, not the sum."""
    art, names, REG, V, A, stock, alpha = fx
    disp = np.tile(np.linspace(0, 1, REG.shape[1], dtype=np.float32), (REG.shape[0], 1))
    s = scene(fx, disparity=lambda: disp)
    dep, bri = s.sparkle_map('depth'), s.sparkle_map('bright')
    for style, curve in (('lines', lambda m: m ** 1.2), ('grain', lambda m: (0.15 + 0.85 * m) * (alpha > 0.5))):
        q = look.clean_params({'sparkle_depth': 150, 'sparkle_bright': 60, 'sparkle_link': False})
        w, ready = s.sparkle_weight(q, style)
        assert ready and np.allclose(w, np.maximum(1.5 * curve(dep), 0.6 * curve(bri)), atol=1e-6)
    plain, _ = s.render(dict(OFF, style='lines'))

    def hit(**amounts):
        out, _ = s.render(dict(OFF, style='lines', **amounts))
        return np.abs(out.astype(int) - plain.astype(int)).max(2) > 0
    d, b, both = hit(sparkle_depth=100), hit(sparkle_bright=100), hit(sparkle_depth=100, sparkle_bright=100)
    assert np.array_equal(both, d | b)                       # same draws: the union, nothing doubled
    assert both.sum() < d.sum() + b.sum()
    # no depth yet: brightness still shows, and the render says it is waiting for depth
    nodepth = scene(fx)
    out, info = nodepth.render(dict(OFF, style='lines', sparkle_depth=100, sparkle_bright=100))
    assert not info['sparkles_ready']
    assert np.array_equal(out, nodepth.render(dict(OFF, style='lines', sparkle_bright=100))[0])


def test_legacy_sparkle_settings():
    c = look.clean_params

    def pick(q):
        return q['sparkle_depth'], q['sparkle_bright'], q['sparkle_painted']
    assert pick(c({'sparkles': 'depth'})) == (100, 0, 0)
    assert pick(c({'sparkles': 'bright', 'sparkle_amount': 60})) == (0, 60, 0)
    assert pick(c({'sparkles': 'painted'})) == (0, 0, 100)
    assert pick(c({'sparkles': 'off'})) == (0, 0, 0)
    assert pick(c({'sparkles': 'auto', 'sparkle_mix': 70})) == (60, 100, 0)
    assert c({'sparkles': 'auto', 'sparkle_mix': 70})['sparkle_link'] is False     # unequal: not linked
    assert c({'sparkles': 'depth'})['sparkle_link'] is False
    assert pick(c({})) == (100, 100, 0) and c({})['sparkle_link'] is True
    assert c({'sparkle_link': 'false'})['sparkle_link'] is False


def test_linked_amounts_are_one_value():
    c = look.clean_params
    q = c({'sparkle_link': True, 'sparkle_depth': 40, 'sparkle_bright': 180})
    assert (q['sparkle_depth'], q['sparkle_bright']) == (40, 40)
    q = c({'sparkle_link': 'false', 'sparkle_depth': 40, 'sparkle_bright': 180})
    assert (q['sparkle_depth'], q['sparkle_bright']) == (40, 180)


def _line_angle(diff):
    """Angle (degrees, image axes, y down) the stripes of a pattern run at, from the peak of its spectrum (exact
    even for stripes a few px apart, where finite-difference gradients skew the angle)."""
    h, w = diff.shape
    f = np.abs(np.fft.fftshift(np.fft.fft2((diff - diff.mean()) * np.outer(np.hanning(h), np.hanning(w)))))
    f[h // 2 - 2:h // 2 + 3, w // 2 - 2:w // 2 + 3] = 0
    ky, kx = np.unravel_index(f.argmax(), f.shape)
    normal = np.degrees(np.arctan2((ky - h // 2) / h, (kx - w // 2) / w))
    return (normal + 90 + 90) % 180 - 90


def test_tilt_leans_regions_named_neither_left_nor_right_by_where_they_are():
    """斜单线 at 32 deg: two legs named 腿 and 部位 2 lean opposite ways, mirrored (a chevron), the one on the image's
    left like 左腿 and the other like 右腿; a region named 左/右 keeps its name's side wherever it is. These used to get
    no lean at all (their lines only spread apart as the tilt grew)."""
    h, w = 240, 600
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    left, right = (xx >= 40) & (xx < 260), (xx >= 340) & (xx < 560)
    REG = np.where(left, 1, np.where(right, 2, 0)).astype(np.int8)
    cx = np.where(left, 150, 450)
    V, A = np.where(REG > 0, yy, 0), np.where(REG > 0, cx - xx, 0)      # as solved: V down the leg, A leftward
    art = np.full((h, w, 3), 120, np.uint8)
    q = dict(OFF, style='lines', tilt=32, sparkle_depth=0, sparkle_bright=0)
    angles = {}
    for names in (['腿', '部位 2'], ['左腿', '右腿'], ['右腿', '左腿']):
        s = look.Scene(art, REG, V, A, REG > 0, (REG > 0).astype(np.float32), names)
        out = s.render(q)[0].astype(np.float64).mean(2) - 120
        angles[names[0]] = [_line_angle(out[20:-20, 60:240]), _line_angle(out[20:-20, 360:540])]
    a, b = angles['腿']
    assert abs(abs(a) - 32) < 4 and abs(a + b) < 2, angles                 # leaning, mirrored
    assert np.allclose(angles['腿'], angles['左腿'], atol=1)                  # placed like their names would be
    assert np.allclose(angles['右腿'], [b, a], atol=1)                         # a name wins over the place
    R = np.zeros((10, 30), np.int8)
    R[:, 2:8] = 1
    R[:, 22:28] = 1                                                        # one region, two separate legs
    assert look.tilt_sides(R, ['腿'])[5, 5] == 1 and look.tilt_sides(R, ['腿'])[5, 25] == -1
    R[:, 13:17] = 2                                                        # a crotch between them: no lean
    side = look.tilt_sides(R, ['腿', '胯部'])
    assert side[5, 5] == 1 and side[5, 25] == -1 and side[5, 15] == 0
    assert look.tilt_sides(R[:, :12], ['腿'])[5, 5] == 1                   # a lone leg still leans


def test_oily_is_an_experimental_style_and_reads_old_settings():
    assert 'oily' in look.STYLES and look.EXPERIMENTAL_STYLES == ('oily',) and look.SPARKLE_STYLES == look.STYLES
    assert look.clean_params({'style': 'p_oily'})['style'] == 'oily'        # saved by an early version


def test_oily_glint_on_the_lit_side_and_texture_only_on_the_stockings(fx):
    """油光: nothing changes off the stockings; the painted highlight's crest gets the brightest lift and the shadow
    side sinks."""
    art, names, REG, V, A, stock, alpha = fx
    s = scene(fx)
    out, _ = s.render(dict(OFF, style='oily'))
    off = alpha == 0
    assert np.array_equal(out[off], s.src[off])
    tone, core, band, tail, facing, centre, zone = s.oily_maps()
    m = alpha > 0.5
    lift = out.astype(float).mean(2) - s.src.astype(float).mean(2)
    crest, shade = m & (core > 0.5), m & (tone < -0.6)
    assert crest.sum() > 200 and shade.sum() > 200
    assert np.median(lift[crest]) > 20 and np.median(lift[shade]) < 0


# ---------------------------------------------------------------- 摩尔纹效果

def _dome(h=600, w=400, rgb=(120, 100, 104), ready=True, heights=(1.0,)):
    """Bulging stockings on a plain picture: an elliptical region for each height, side by side, courses across them,
    and a dome of disparity over each that high (nearest in the middle), so the depth model's bulge has a known shape.
    Returns (scene, disparity, holder): the scene sees the disparity once holder['disp'] is set (at once, unless ready
    is False)."""
    n = len(heights)
    yy, xx = np.mgrid[0:h, 0:w * n].astype(np.float64)
    REG = np.zeros((h, w * n), np.int8)
    disp = np.zeros((h, w * n), np.float32)
    for k, top in enumerate(heights):
        u = ((xx - (k + 0.5) * w) / (0.42 * w)) ** 2 + ((yy - h / 2) / (0.42 * h)) ** 2
        REG[u < 1] = k + 1
        disp += (np.clip(1 - u, 0, None) * top).astype(np.float32)
    art = np.empty((h, w * n, 3), np.uint8)
    art[...] = rgb
    holder = {'disp': disp if ready else None}
    s = look.Scene(art, REG, yy, xx, REG > 0, (REG > 0).astype(np.float32), ['左腿', '右腿', '胯部'][:n],
                   disparity=lambda: holder['disp'])
    return s, disp, holder


def _rings(f, col):
    """How many times the bands change sign down one column: two for each ring."""
    c = f[:, col]
    return int((np.diff(np.sign(c[np.abs(c) > 0.5])) != 0).sum())


def test_moire_is_a_switch_that_is_off_by_default_over_two_sliders():
    assert look.DEFAULTS['moire_on'] is False and look.clean_params({})['moire_on'] is False
    assert [look.clean_params({'moire_on': v})['moire_on'] for v in (True, 'true', '1', False, 'false', '0')] == [
        True, True, True, False, False, False]                                    # from a query string, too
    assert look.DEFAULTS['moire'] == 100 and look.clean_params({})['moire'] == 100     # the strength it has once on
    assert look.clean_params({'moire': 140})['moire'] == 100 and look.clean_params({'moire': -5})['moire'] == 0
    assert look.clean_params({'moire': '35'})['moire'] == 35                      # from a query string
    assert look.DEFAULTS['moire_area'] == 100 and look.clean_params({})['moire_area'] == 100     # the whole bulge
    assert look.clean_params({'moire_area': 140})['moire_area'] == 100 and look.clean_params({'moire_area': -5})['moire_area'] == 0
    assert look.clean_params({'moire_area': '35'})['moire_area'] == 35
    assert all(k in look.RENDER_KEYS for k in ('moire_on', 'moire', 'moire_area'))


def test_the_moire_is_drawn_only_with_the_switch_on_and_the_sliders_keep_their_values():
    on = lambda **kw: look.moire_active(look.clean_params(dict({'moire_on': True}, **kw)))
    assert on() and on(moire=40) and not on(moire=0)                              # on, but no strength: nothing to draw
    assert not look.moire_active(look.clean_params({}))                           # the switch is off by default
    off = look.clean_params({'moire_on': False, 'moire': 35, 'moire_area': 20})
    assert not look.moire_active(off) and off['moire'] == 35 and off['moire_area'] == 20     # off keeps what was set
    s, disp, _ = _dome()
    p = dict(OFF, style='knit')
    plain, _ = s.render(p)
    assert np.array_equal(s.render(dict(p, moire_on=False, moire=100, moire_area=100))[0], plain)
    assert not np.array_equal(s.render(dict(p, moire_on=True, moire=100))[0], plain)
    assert np.array_equal(s.render(dict(p, moire_on=True, moire=0))[0], plain)


def test_moire_bands_follow_the_bulge_and_add_no_light():
    """Rings round the dome, none on the flat of the region or off it, and a sine so that light and dark bands cancel."""
    s, disp, _ = _dome()
    phase, slope, gate = s.moire_maps()
    f = look.moire_fringes(phase, slope, 1.0)
    inside = s.R > 0
    assert f.shape == s.R.shape and f.dtype == np.float32 and np.abs(f).max() <= 1
    assert f.min() < -0.95 and f.max() > 0.95
    assert (f[~inside] == 0).all()
    flat = inside & (phase < 0.3)
    assert flat.sum() > 40000 and (f[flat] == 0).all()                    # the lowest 40% of a region has no bulge
    assert abs(f[inside].mean()) < 0.05
    assert _rings(f, s.w // 2) >= 16                                      # a deep dome: many rings each side of the crown
    assert np.allclose(s.moire_map(1.0), f)                               # a light stocking: the texture's gate is open
    dark, _, _ = _dome(rgb=(6, 5, 5))
    assert np.abs(dark.moire_map(1.0)).max() < 0.01                       # a near-black one gets no bands, like no texture


def test_moire_grows_from_a_small_light_disc_on_the_crown():
    """面积: nothing at 0, then a small light disc on the crown that spreads outward, the first dark ring appearing
    round it and more rings after that."""
    s, _, _ = _dome(heights=(1.0, 4.0))                  # the first dome stands a quarter as high: a few rings, not a dozen
    phase, slope, _ = s.moire_maps()
    left = s.R == 1
    cx, cy = s.w // 4, s.h // 2
    assert not look.moire_fringes(phase, slope, 0.0).any()

    def reach(a):
        yy, xx = np.nonzero((np.abs(look.moire_fringes(phase, slope, a)) > 0.5) & left)
        return float(np.hypot(xx - cx, yy - cy).max()) if len(xx) else 0.0

    small = look.moire_fringes(phase, slope, 0.2)
    assert (small[left] > 0.5).any() and not (small[left] < -0.5).any()           # a light disc, no ring yet
    assert small[cy, cx] > 0.5                                                    # on the crown
    areas = [0.2, 0.3, 0.5, 0.8, 1.0]
    reaches = [reach(a) for a in areas]
    assert 0 < reaches[0] < 0.6 * reaches[-1] and reaches == sorted(reaches)      # it spreads, never shrinks
    counts = [_rings(look.moire_fringes(phase, slope, a), cx) for a in areas]
    assert counts == sorted(counts) and counts[0] == 0 and counts[-1] >= 8        # and rings join it


def test_a_taller_bulge_holds_more_rings_whatever_its_size():
    """The count follows the height: in one picture a dome four times as high gets about four times the rings, while a
    dome twice as wide and as long, as high as before, holds the same number: its rings are just bigger."""
    s, _, _ = _dome(heights=(1.0, 4.0))
    phase, slope, _ = s.moire_maps()
    top = lambda i: float(np.percentile(phase[s.R == i], 99))
    assert 3.5 < top(2) / top(1) < 4.5
    f = look.moire_fringes(phase, slope, 1.0)
    assert _rings(f, 3 * s.w // 4) > 2 * _rings(f, s.w // 4)
    small, big = _dome(), _dome(h=1200, w=800)
    assert abs(float(big[0].moire_maps()[0].max()) / float(small[0].moire_maps()[0].max()) - 1) < 0.05


def test_moire_bands_too_fine_for_the_pixels_fade_away():
    """5 bands over a ramp 20 px wide would be 0.25 cycles/px, as fine as the courses at their limit: they fade out
    (as does everything finer than look.MOIRE_FADE); over 200 px they are 0.025 cycles/px and stay at full strength."""
    xx = np.tile(np.arange(400, dtype=np.float32), (120, 1))

    def bands(width):
        phase = 5 * np.clip((xx - 100) / width, 0, 1)
        gy, gx = np.gradient(phase)
        return look.moire_fringes(phase, np.hypot(gx, gy).astype(np.float32), 1.0)

    steep, gentle = bands(20), bands(200)
    assert np.abs(steep[10:-10, 105:115]).max() < 0.02
    assert np.abs(gentle[10:-10, 100:300]).max() > 0.95


def test_moire_smoothing_stays_inside_each_region():
    R = np.zeros((40, 80), np.int8)
    R[:, :40], R[:, 40:] = 1, 2
    out = look._smooth_within_regions(np.where(R == 1, 1.0, 0.0).astype(np.float32), R, 3.0)
    assert np.allclose(out[:, :40], 1) and np.allclose(out[:, 40:], 0)       # nothing bleeds across the border
    R[10:20, 10:20] = 0                                                      # a hole (a hand): not counted either
    out = look._smooth_within_regions(np.where(R == 1, 1.0, 0.0).astype(np.float32), R, 3.0)
    assert np.allclose(out[R == 1], 1) and (out[R == 0] == 0).all()


def test_moire_lays_light_and_texture_contrast_over_the_render():
    src = np.full((4, 4, 3), 100, np.uint8)
    on, off = np.ones((4, 4), np.float32), -np.ones((4, 4), np.float32)

    def gives(out, want):                                                    # to the nearest level
        return np.abs(out.astype(float) - want).max() <= 0.5001

    assert gives(look.apply_moire(src, src, on, 1.0, 1.0), 100 * (1 + look.MOIRE_LIGHT))
    assert gives(look.apply_moire(src, src, off, 1.0, 1.0), 100 * (1 - look.MOIRE_LIGHT))
    assert gives(look.apply_moire(src, src, on, 1.0, 0.4), 100 * (1 + 0.4 * look.MOIRE_LIGHT))       # light stockings: less
    assert gives(look.apply_moire(src, src, on, 0.5, 1.0), 100 * (1 + 0.5 * look.MOIRE_LIGHT))       # half the slider
    dim = np.full((4, 4, 3), 90, np.uint8)                                   # a texture that dims the stocking by 10
    assert gives(look.apply_moire(dim, src, on, 1.0, 0.0), 100 - 10 * (1 + look.MOIRE_TEXTURE))
    assert gives(look.apply_moire(dim, src, off, 1.0, 0.0), 100 - 10 * (1 - look.MOIRE_TEXTURE))
    assert np.array_equal(look.apply_moire(dim, src, on, 0.0, 1.0), dim)     # amount 0: the render itself


@pytest.mark.parametrize('style', look.STYLES)
def test_moire_goes_over_every_style_on_the_stockings_only(style):
    """Any style: the stocking gets bands (no lighter on average), nothing off it changes, and a crop is the same
    area of the whole render, sparkles and all."""
    s, disp, _ = _dome()
    plain, _ = s.render(dict(OFF, style=style))
    out, info = s.render(dict(OFF, style=style, moire_on=True, moire=100))
    assert info['moire_ready']
    inside = s.R > 0
    assert np.array_equal(out[~inside], plain[~inside])
    assert np.array_equal(s.render(dict(OFF, style=style, moire_on=False, moire=100))[0], plain)       # the switch is off
    light = lambda im: cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(float)[inside].mean()
    assert abs(light(out) / light(plain) - 1) < 0.01
    assert np.abs(out.astype(int) - plain.astype(int)).max() > 10
    p = dict(OFF, style=style, moire_on=True, moire=70, moire_area=60, sparkle_even=60)
    whole, _ = s.render(p)
    for rect in [(100, 150, 300, 400), (0, 0, 64, 64), (330, 540, 400, 600)]:
        x0, y0, x1, y1 = rect
        assert np.array_equal(s.render(p, rect)[0], whole[y0:y1, x0:x1]), rect


def test_moire_area_sets_how_far_the_rings_reach_in_the_render():
    s, disp, _ = _dome(heights=(1.0, 4.0))
    p = dict(OFF, style='knit', moire_on=True, moire=100)
    plain, _ = s.render(dict(p, moire_on=False))
    assert np.array_equal(s.render(dict(p, moire_area=0))[0], plain)               # no area, no rings
    small, wide = s.render(dict(p, moire_area=25))[0], s.render(dict(p, moire_area=100))[0]
    changed = lambda im: (np.abs(im.astype(int) - plain.astype(int)).max(2) > 3) & (s.R == 1)    # the lower dome
    assert 0 < changed(small).sum() < changed(wide).sum()
    assert np.array_equal(s.render(dict(p, moire_area=25))[0], small)              # asking again after another area


def test_moire_waits_for_the_depth_model():
    """Without the bulge there are no bands: the render is the plain one and says it is not final, so it is not kept
    and the next one has them."""
    s, disp, holder = _dome(ready=False)
    p = dict(OFF, style='knit', moire_on=True, moire=100)
    plain, _ = s.render(dict(p, moire_on=False))
    out, info = s.render(p)
    assert not info['moire_ready'] and info['sparkles_ready'] and np.array_equal(out, plain)
    assert s.moire_maps() is None and s.moire_map(1.0) is None and s.sparkle_map('depth') is None
    holder['disp'] = disp
    out, info = s.render(p)
    assert info['moire_ready'] and (out != plain).any()
    assert s.render(dict(p, moire_on=False))[1]['moire_ready']                # nothing waits when the effect is off


def test_the_depth_model_is_started_for_the_moire(monkeypatch):
    import types
    from stocking import server
    started = []
    monkeypatch.setattr(server.depth.service, 'disparity_async', started.append)
    q = lambda **kw: look.clean_params(dict({'sparkle_depth': 0, 'sparkle_link': False}, **kw))
    d = types.SimpleNamespace()
    server._want_depth(d, q())
    server._want_depth(d, q(moire=40))                                       # the switch is off
    server._want_depth(d, q(moire_on=True, moire=0))                         # on, but nothing to draw
    assert started == [] and not getattr(d, '_depth_started', False)
    server._want_depth(d, q(moire_on=True, moire=40))
    assert started == [d] and d._depth_started
    server._want_depth(d, q(moire_on=True, moire=40))                        # once is enough
    assert started == [d]

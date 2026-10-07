"""油光's glints (oily.py v7) on synthetic limbs, one feature at a time: where the glint goes and where it must not."""
import cv2
import numpy as np

from stocking import oily

H, W = 600, 360
X0, X1, CX = 100, 260, 180            # the leg: x 100..260, its middle at x 180


def leg(shade, hole=None, top=0):
    """A straight leg down the image; shade(yy, xx) -> painted brightness 0..255 on it. hole: a bool mask of things
    in front of it (cut out of the visible stocking, kept in the painted region). top: rows above the leg."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    m = (xx >= X0) & (xx < X1) & (yy >= top)
    src = np.full((H, W, 3), 250, np.uint8)
    src[m] = np.clip(shade(yy, xx), 0, 255)[m][:, None].astype(np.uint8)
    R = m.astype(np.int8)
    REG = R.copy()
    if hole is not None:
        R[hole] = 0
    return src, R, (R > 0).astype(np.float32), np.where(m, CX - xx, 0.0), np.where(m, yy, 0.0), REG


def maps(src, R, alpha, A, V, REG, scale=0.64):
    return dict(zip(('tone', 'core', 'band', 'tail', 'facing', 'centre'),
                    oily.oily_maps(src, R, alpha, A, V, scale, REG=REG)))


def lit(yy, xx, at=205, width=32):
    """A broad soft highlight across the leg, centred at x = at."""
    return 70 + 70 * np.exp(-((xx - at) / width) ** 2)


def pieces(core, thr=0.3):
    n, _, stats, _ = cv2.connectedComponentsWithStats((core > thr).astype(np.uint8), connectivity=8)
    return [stats[i] for i in range(1, n) if stats[i][4] >= 6]


def test_glint_sits_on_the_painted_highlight_and_runs_the_leg():
    m = maps(*leg(lit))
    rows = m['core'][50:550]
    assert (rows.max(1) > 0.5).all()
    assert np.abs(rows.argmax(1) - 205).max() <= 2


def test_hair_shadows_make_no_glints_of_their_own():
    """Shadows of hair strands painted across the top of the leg, soft slanted stripes: still one streak down the
    whole leg (the bright strips between the shadows used to each make a short squiggle), fainter where the hair
    shades it, as painted."""
    def shade(yy, xx):
        stripes = 0.5 + 0.5 * np.cos(2 * np.pi * (xx + 0.35 * yy) / 26)
        return lit(yy, xx) * (1 - 0.3 * stripes * np.clip((180 - yy) / 120, 0, 1))
    core = maps(*leg(shade))['core']
    p = pieces(core, 0.08)
    assert len(p) == 1 and p[0][3] > 590, [tuple(q) for q in p]
    assert np.abs(core.argmax(1) - 205).max() <= 6


def test_hair_in_front_is_no_outline():
    """Strands hanging in front of the leg, one of them over its edge, painted over in the region: holes in the
    visible stocking only. The leg's facing beside them stays as it was (they are not its silhouette), and the glint
    carries on past them."""
    hole = np.zeros((H, W), bool)
    for x in (96, 130, 170, 225):
        hole[:160, x:x + 12] = True
    plain, holed = maps(*leg(lit)), maps(*leg(lit, hole=hole))
    near = np.zeros((H, W), bool)
    near[:160] = True
    near &= ~hole & (cv2.dilate(hole.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0)
    near[:, :X0 + 4] = near[:, X1 - 4:] = False
    assert np.abs(holed['facing'][near] - plain['facing'][near]).max() < 0.05
    assert (holed['core'][20:150, 200:212].max(1) > 0.4).all()


def test_strips_between_shadows_make_no_glints_of_their_own():
    """A hand's fingers shading a broadly lit leg, soft dark bands along it near the light's top: the lit strip
    between them stands out against the shadows only, not against the light around it, so the one glint stays the
    only one."""
    def shade(yy, xx):
        fingers = sum(np.exp(-((xx - x) / 5) ** 2) for x in (195, 225))
        return (70 + 70 * np.exp(-((xx - 175) / 60) ** 2)) * (1 - 0.45 * fingers * ((yy > 200) & (yy < 420)))
    core = maps(*leg(shade))['core']
    assert core[220:400, 203:218].max() < 0.1
    assert (core[60:540, 165:186].max(1) > 0.5).all()


def test_a_glint_goes_on_behind_trim_as_one():
    """Gold trim cut out of the leg beside its highlight, a wide diamond head over it: the glint carries on at full
    strength up to the trim and out the other side, not two pieces fading out toward it."""
    yy, xx = np.mgrid[0:H, 0:W]
    trim = (np.abs(xx - 195) + np.abs(yy - 260) * 0.5 < 34) | ((xx >= 190) & (xx < 200) & (yy > 260) & (yy < 380))
    core = maps(*leg(lit, hole=trim))['core']
    rows = [y for y in range(60, 540) if not trim[y, 205]]           # where the glint's own line is in sight
    assert core[rows, 203:208].max(1).min() > 0.7


def test_trim_over_a_broad_light_neither_moves_nor_dims_its_glint():
    """A broad flat-topped light with trim hiding the middle of it for a stretch: the bands there lose their
    brightest part, so their own medians would sink and the cells beside the trim stand out. The glint stays where
    and as bright as it is without the trim."""
    def broad(yy, xx):
        return 70 + 70 * np.exp(-((xx - 205) / 45) ** 4)
    yy, xx = np.mgrid[0:H, 0:W]
    trim = (np.abs(xx - 198) + np.abs(yy - 260) * 0.5 < 30) | ((xx >= 193) & (xx < 203) & (yy > 260) & (yy < 380))
    plain, core = maps(*leg(broad))['core'], maps(*leg(broad, hole=trim))['core']
    want = plain[60:540].max(1)
    gx = core.argmax(1)
    rows = [y for y in range(60, 540) if not trim[y, gx[y]]]
    assert np.abs(gx[60:540] - plain[60:540].argmax(1)).max() <= 4
    assert (core[rows, gx[rows]] > 0.8 * want[np.asarray(rows) - 60]).all()


def test_a_stem_lying_on_the_glint_leaves_its_glow_beside_it():
    """A narrow stem of trim right over the highlight, down a long stretch: the glint goes on under it, and the glow
    beside the stem stays as bright as without it (the fit is unsure of the light under the stem, so how bright the
    glint is there comes from where it is sure)."""
    yy, xx = np.mgrid[0:H, 0:W]
    stem = (np.abs(xx - 205) <= 5) & (yy > 150) & (yy < 450)
    plain, holed = maps(*leg(lit))['tail'], maps(*leg(lit, hole=stem))['tail']
    assert holed[160:440, 211].min() > 0.85 * plain[160:440, 211].min()


def test_a_glint_that_ends_in_plain_sight_is_not_joined_to_another():
    """A glint that stops where the stocking is in full view (the fit sure there is no peak), the limb's edge not far
    off, and another starting lower down elsewhere across it: two glints, not one carried through the gap (only out
    of sight does a glint go on)."""
    c = np.arange(60)
    fit = np.zeros((40, 60))
    fit[:15] = 0.15 * np.exp(-((c - 32) / 3.0) ** 2)
    fit[25:] = 0.15 * np.exp(-((c - 22) / 3.0) ** 2)
    den = np.where(c < 36, 1.0, np.where(c < 40, 0.2, 0.0)) * np.ones((40, 1))
    for rows, *_ in oily._tracks(fit, 0.3 + fit, den, 0.001, 12):
        assert not (rows[1] <= 14 and rows[-2] >= 25)


def test_unsure_rows_do_not_dim_the_sure_ones():
    """Rows where the fit only bridges a gap over the glint (support 0.2) and reads it dimmer: the rows either side,
    seen in full, keep the glint's full strength."""
    c = np.arange(60)
    fit = np.tile(0.15 * np.exp(-((c - 30) / 4.0) ** 2), (40, 1))
    absolute, den = 0.3 + fit, np.ones_like(fit)
    den[15:20, 26:35] = 0.2
    absolute[15:20, 26:35] -= 0.03
    rows, u, st, *_ = max(oily._tracks(fit, absolute, den, 0.001, 8), key=lambda t: len(t[0]))
    at = {int(r): s for r, s in zip(rows, st)}
    assert min(at[14], at[20]) > 0.95 * at[5]


def test_a_flat_top_is_known_only_to_within_its_width():
    """A light whose top is exactly flat for 21 cells, without noise: where its peak is stays uncertain by the flat's
    half-width, however clean the fit."""
    c = np.arange(80)
    prof = 0.2 - 0.01 * np.clip(np.abs(c - 40) - 10, 0, None) ** 1.5
    fit = np.tile(prof, (20, 1))
    *_, dl = max(oily._tracks(fit, 0.3 + fit, np.ones_like(fit), 0.0, 8), key=lambda t: len(t[0]))
    assert dl[1:-1].min() >= 9.5


def test_a_print_step_beside_trim_makes_no_glint():
    """A stocking top: dark above, light below, the step running with the courses, and a diamond of trim cut out of
    the leg across the step. Brightness that depends on the course alone is no light across the limb, however much
    of each band is hidden."""
    yy, xx = np.mgrid[0:H, 0:W]
    trim = np.abs(xx - 180) + np.abs(yy - 260) < 40
    assert maps(*leg(lambda yy, xx: np.where(yy < 260, 30.0, 230.0), hole=trim))['core'].max() < 0.05


def test_a_glint_near_the_edge_of_the_view_is_kept():
    """A narrow highlight 18 px inside the leg's outline, falling off to both sides in sight: a glint."""
    core = maps(*leg(lambda yy, xx: 60 + 80 * np.exp(-((xx - 118) / 6) ** 2)))['core']
    assert core[50:550, 114:123].max(1).min() > 0.5


def test_two_close_lights_of_one_height_keep_their_own_glints():
    """Two equal narrow lights 32 px apart: the dip between them is no shade to fill flat, so each keeps its glint
    where it is painted, and none sits in the dip."""
    def shade(yy, xx):
        return 60 + 80 * (np.exp(-((xx - 190) / 6) ** 2) + np.exp(-((xx - 222) / 6) ** 2))
    core = maps(*leg(shade))['core']
    assert core[300, 187:194].max() > 0.5 and core[300, 219:226].max() > 0.5 and core[300, 200:213].max() < 0.2


def test_a_glint_sits_only_where_the_light_is_measured_at_its_top():
    """Two lights of exactly one height, close enough that the envelope fills the dip between them up to their
    height (the dip itself lit, so no gate turns a glint there away): glints on the two tops, none in the dip."""
    c = np.arange(49)
    fit = np.tile(0.15 * (np.exp(-((c - 20) / 1.5) ** 2) + np.exp(-((c - 28) / 1.5) ** 2)), (20, 1))
    absolute = np.tile(0.3 + 0.3 * np.exp(-((c - 24) / 6.0) ** 2), (20, 1))
    tracks = oily._tracks(fit, absolute, np.ones_like(fit), 0.001, 8)
    at = sorted(round(float(u[len(u) // 2]), 1) for _, u, st, *_ in tracks if st.max() > 0.1)
    assert at == [20.5, 28.5], at


def test_another_region_in_front_is_no_outline():
    """The other leg crossing in front of this one (painted as its own region): this leg's edge against it is no
    silhouette, so its facing there stays as it was."""
    src, R, alpha, A, V, REG = leg(lit)
    plain = maps(src, R, alpha, A, V, REG)
    other = np.zeros((H, W), bool)
    other[250:350, 200:300] = True                          # in front, over the leg's right side
    R2, REG2 = R.copy(), REG.copy()
    R2[other], REG2[other] = 2, 2
    crossed = oily.oily_maps(src, R2, (R2 > 0).astype(np.float32), A, V, 0.64, REG=REG2)[4]
    beside = (REG2 == 1) & (cv2.dilate(other.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0)
    assert np.abs(crossed[beside] - plain['facing'][beside]).max() < 0.05


def test_print_running_with_the_courses_makes_no_glint():
    """Bright bands across the leg (a stocking top, printed stripes) on a leg lit evenly across: no glint."""
    def shade(yy, xx):
        return 70 + 90 * ((yy % 120) < 30)
    assert maps(*leg(shade))['core'].max() < 0.05


def test_brightness_along_curved_courses_makes_no_glint():
    """Courses curving round (an annulus, V the radius): brightness that depends only on V is no glint, however the
    courses bend (a curvature measured along a straight tangent took such a band for one)."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    r = np.hypot(xx - 30, yy - 300)
    th = np.arctan2(yy - 300, xx - 30)
    m = (r > 150) & (r < 310) & (np.abs(th) < 1.2)
    src = np.full((H, W, 3), 250, np.uint8)
    src[m] = (60 + 100 * np.exp(-((r - 230) / 20) ** 2))[m][:, None].astype(np.uint8)
    R = m.astype(np.int8)
    out = oily.oily_maps(src, R, R.astype(np.float32), np.where(m, th * 230, 0), np.where(m, r, 0), 0.64, REG=R)
    assert out[1].max() < 0.05


def test_dark_or_flat_art_gets_no_glint_and_a_flat_leg_no_sink():
    """A near-black leg with a faint bump (2..8 of 255) gets no glint; a leg of one flat grey is neither all sheen
    nor all shadow."""
    dark = maps(*leg(lambda yy, xx: 2 + 6 * np.exp(-((xx - 205) / 20) ** 2)))
    assert dark['core'].max() < 0.05
    flat = maps(*leg(lambda yy, xx: np.full_like(xx, 90)))
    assert flat['core'].max() < 0.05 and np.abs(flat['tone'][flat['facing'] > 0]).max() < 0.1


def test_two_lights_make_two_glints():
    def shade(yy, xx):
        return 60 + 70 * np.exp(-((xx - 140) / 14) ** 2) + 70 * np.exp(-((xx - 228) / 14) ** 2)
    row = maps(*leg(shade))['core'][300]
    assert row[136:145].max() > 0.5 and row[224:233].max() > 0.5 and row[175:195].max() < 0.2


def test_the_image_frame_is_no_outline():
    """A leg running off the top of the image keeps its glint up to the frame."""
    m = maps(*leg(lit))
    assert m['core'][0:8, 200:211].max() > 0.5


def test_a_wall_leaves_no_seam():
    """A wall across the leg (cut band where V and A jump): each side finds its own glint, and the band itself
    takes the maps from beside it, so nothing drops to zero along the wall."""
    src, R, alpha, A, V, REG = leg(lit)
    cut = np.zeros((H, W), bool)
    cut[296:304, X0:X1] = True
    core = oily.oily_maps(src, R, alpha, A, V, 0.64, cut=cut, REG=REG)[1]
    assert core[296:304, 200:211].max(1).min() > 0.5
    assert core[100, 200:211].max() > 0.5 and core[500, 200:211].max() > 0.5


def test_noise_is_no_light():
    """Painting that is only noise, with no light falling across the limb, gets no visible glint (a chance peak
    may leave a trace far below what shows: core 0.1 lifts a dark stocking by about 4 of 255)."""
    rng = np.random.default_rng(3)
    src, R, alpha, A, V, REG = leg(lambda yy, xx: 60 + 120 * rng.random(yy.shape))
    core = maps(src, R, alpha, A, V, REG)['core']
    assert core.max() < 0.1 and (core > 0.02).sum() < 50


def test_a_highlight_on_a_bending_limb_is_followed():
    """An S-bent leg with its highlight painted at the same place across it all the way down: the glint follows it
    (one cubic through the whole path missed it by up to 36 px)."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    cx = 180 + 60 * np.sin(2 * np.pi * yy / H)
    m = np.abs(xx - cx) < 70
    shade = 70 + 70 * np.exp(-((xx - cx - 25) / 10) ** 2)
    src = np.full((H, W, 3), 250, np.uint8)
    src[m] = shade[m][:, None].astype(np.uint8)
    R = m.astype(np.int8)
    core = oily.oily_maps(src, R, R.astype(np.float32), np.where(m, cx - xx, 0), np.where(m, yy, 0), 0.64, REG=R)[1]
    rows = np.arange(40, H - 40, 10)
    want = (cx[rows, 0] + 25).round()
    assert (core[rows].max(1) > 0.4).all()
    assert np.abs(core[rows].argmax(1) - want).max() <= 4              # a quarter of the highlight's 16 px width


def test_a_glint_seen_in_one_row_is_drawn():
    """A piece only one row of the lighting fit long still shows its glint."""
    src, R, alpha, A, V, REG = leg(lit, top=H - 12)
    assert maps(src, R, alpha, A, V, REG)['core'][H - 6, 200:211].max() > 0.4


def test_light_rising_into_an_edge_or_past_a_gap_is_no_glint():
    """Light rising steadily across the leg to its edge (a printed band seen at a slant, a light background bleeding
    in) shows no fall-off on the far side: no glint at the edge, and none beside a strip of gold trim cut out of the
    leg on the way (what is hidden there is unknown, not dark)."""
    src, R, alpha, A, V, REG = leg(lambda yy, xx: 60 + 0.8 * (xx - X0))
    assert maps(src, R, alpha, A, V, REG)['core'].max() < 0.05
    trim = np.zeros((H, W), bool)
    trim[:, 180:192] = True
    assert maps(*leg(lambda yy, xx: 60 + 0.8 * (xx - X0), hole=trim))['core'].max() < 0.05


def test_a_limb_wider_than_the_view_has_no_silhouette_at_the_frame():
    """Stocking filling the whole image across: the frame is no outline, so nothing there darkens as a silhouette."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    R = np.ones((H, W), np.int8)
    src = np.full((H, W, 3), 90, np.uint8)
    facing = oily.oily_maps(src, R, np.ones((H, W), np.float32), 180 - xx, yy, 0.64, REG=R)[4]
    assert facing[:, :3].min() > 0.9 and facing[:, -3:].min() > 0.9


def test_a_real_narrowing_is_kept():
    """A knee-like narrowing painted in the region (half-width 80 -> 45 -> 80, gently) is the leg's own shape, not
    something in front of it: near the outline at the narrowest point the surface turns away."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    half = 80 - 35 * np.exp(-((yy - 300) / 70) ** 2)
    m = np.abs(xx - 180) < half
    src = np.full((H, W, 3), 250, np.uint8)
    src[m] = 90
    R = m.astype(np.int8)
    facing = oily.oily_maps(src, R, R.astype(np.float32), np.where(m, 180 - xx, 0), np.where(m, yy, 0), 0.64, REG=R)[4]
    x_in = int(180 + half[300, 0] - 4)
    assert facing[300, x_in] < 0.55, facing[300, x_in]


def test_a_region_inside_a_wall_band_reads_nothing_from_elsewhere():
    """A region lying wholly in a wall's band has no stocking beside it to take its maps from: they must not come
    from some other region (an empty nearest-neighbour search pointed at the image's corner)."""
    R = np.zeros((H, W), np.int8)
    R[100:110, 100:200] = 1
    cut = np.zeros((H, W), bool)
    cut[95:115, 90:210] = True
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    src = np.full((H, W, 3), 90, np.uint8)
    args = dict(cut=cut)
    a = oily.oily_maps(src, R, (R > 0).astype(np.float32), 150 - xx, yy, 0.64, REG=R, **args)
    R2 = R.copy()
    R2[H - 1, 0] = 2
    b = oily.oily_maps(src, R2, (R2 > 0).astype(np.float32), 150 - xx, yy, 0.64, REG=R2, **args)
    inside = R == 1
    assert all(np.array_equal(x[inside], y[inside]) for x, y in zip(a, b))

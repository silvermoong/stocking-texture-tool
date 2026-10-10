"""油光's glints (oily.py v7) on synthetic limbs, one feature at a time: where the glint goes and where it must not."""
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from scipy.signal import find_peaks

from stocking import look, oily

H, W = 600, 360
X0, X1, CX = 100, 260, 180            # the leg: x 100..260, its middle at x 180


@pytest.fixture(autouse=True)
def no_floor_glint(monkeypatch):
    """These tests are about where painted glints are found, and are not: they run without the floor glint a dark limb
    has along its whole length (oily.FLOOR_GLINT), which the tests of that glint switch on."""
    monkeypatch.setattr(oily, 'FLOOR_GLINT', 0.0)


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


def maps(src, R, alpha, A, V, REG, scale=0.64, fill=None):
    return dict(zip(('tone', 'core', 'band', 'tail', 'facing', 'centre', 'zone'),
                    oily.oily_maps(src, R, alpha, A, V, scale, REG=REG, fill=fill)))


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


CELL = np.arange(80.0)


def flat_top(*bumps):
    """The light across the limb in one row of the lighting fit: a dome flat over cells 28..52 and falling off to both
    sides, with a bump (cell, height) on the flat for each. Bumps this shallow (the least a peak may stand out is
    oily.TIE) are no peaks of their own: they only decide where along the flat the highest point is."""
    dome = 0.2 - 0.0035 * np.clip(np.abs(CELL - 40) - 12, 0, None) ** 1.5
    return dome + sum(h * np.exp(-((CELL - c) / 3.0) ** 2) for c, h in bumps)


def left_higher():
    return flat_top((28, 0.006), (46, 0.002))


def right_higher():
    return flat_top((28, 0.002), (46, 0.006))


def follow(rows, den=None, noise=0.001, middle=None):
    """oily._tracks of a lighting fit made of these rows (the light across the limb in each), seen in full unless den
    (support per row and cell) says otherwise. middle: each cell's place across the limb (oily_maps' middle)."""
    fit = np.array(rows)
    fit = fit - fit.mean(1, keepdims=True)
    return oily._tracks(fit, 0.3 + fit, np.ones_like(fit) if den is None else den, noise, 8, middle)


def spans(tracks):
    """Each track's first and last row, sorted (the arrays are padded with a row past either end)."""
    return sorted((int(rows[1]), int(rows[-2])) for rows, *_ in tracks)


def test_a_glint_goes_with_the_highest_point_of_a_flat_top_from_one_bump_to_another():
    """The same flat-topped light all down the limb, but which of two shallow bumps on it is the higher changes from
    one row to the next: the glint moves over from one to the other, one track no faster than a glint moves (it used
    to end at one bump and begin again at the other, 18 cells away)."""
    tracks = follow([left_higher() if q < 19 else right_higher() for q in range(40)])
    assert spans(tracks) == [(0, 39)]
    u = tracks[0][1]
    assert u[1] < 30 and u[-2] > 45
    assert np.abs(np.diff(u[1:-1])).max() <= oily.LINK * oily.CELLS + 1e-9


def test_a_bump_that_is_the_higher_for_a_row_or_two_is_no_glint_of_its_own():
    """The other bump the higher for one row, or for two, of a glint on the first: the glint stays where it is, and
    those rows are not a glint beginning and ending again beside it."""
    for moved in ((10,), (10, 11)):
        tracks = follow([right_higher() if q in moved else left_higher() for q in range(30)])
        assert spans(tracks) == [(0, 29)] and np.ptp(tracks[0][1]) < 0.5


def test_two_bumps_exactly_level_are_two_glints_as_ever():
    """Both bumps exactly as high in one row, so both are peaks of it: there is no telling which glint goes over to
    which, and the glints are left as they were, one ending where the other begins."""
    rows = [left_higher() if q < 19 else right_higher() for q in range(40)]
    rows[19] = flat_top((28, 0.006), (46, 0.006))
    assert spans(follow(rows)) == [(0, 19), (19, 39)]


def test_a_glint_does_not_go_across_a_dark_flank_to_another_bump():
    """Broad light for two rows between a crisp light that ends and another 20 cells off that begins: the broad rows
    are level with each other's places, but a glint running between the two would cross the dark flank of the crisp
    ones, so there are two glints, each on its own light."""
    def crisp(c):
        return 0.15 * np.exp(-((CELL - c) / 2.0) ** 2)
    broad = 0.15 * np.clip(1 - np.clip(np.abs(CELL - 29) - 15, 0, None) / 10.0, 0, 1)
    rows = [crisp(20)] * 10 + [broad + 0.002 * np.exp(-((CELL - 20) / 3.0) ** 2),
                               broad + 0.002 * np.exp(-((CELL - 40) / 3.0) ** 2)] + [crisp(40)] * 18
    tracks = sorted(follow(rows), key=lambda t: t[1][1])
    assert spans(tracks) == [(0, 10), (11, 29)]
    assert [(float(np.ptp(u)), round(float(u[1]), 1)) for _, u, *_ in tracks] == [(0, 20.5), (0, 40.5)]


def test_a_glint_moves_over_in_sight_and_stays_where_it_was_out_of_sight():
    """A glint hidden for four rows (a hand across the top of the limb) and, once it is out, the higher bump passing
    to the other: the glint moves over in the rows in sight, and in the rows it was hidden it is where it was last
    seen, not drifting toward a place nothing there says it goes."""
    den = np.ones((30, 80))
    den[5:9, 15:65] = 0.0
    tracks = follow([left_higher() if q < 10 else right_higher() for q in range(30)], den)
    rows, u, *_ = tracks[0]
    assert spans(tracks) == [(0, 29)] and np.ptp(u[(rows >= 4) & (rows <= 9)]) < 0.5 and u[-2] > 45


def test_a_glint_that_may_go_on_unseen_does_not_hand_over():
    """Its place hidden in one row while the higher bump is the other there: the glint goes on unseen where it was and
    comes out as the same one; the other bump seen in that row is a glint of its own for that row, as it always was."""
    den = np.ones((30, 80))
    den[10, 18:38] = 0.2
    tracks = follow([right_higher() if q == 10 else left_higher() for q in range(30)], den)
    assert spans(tracks) == [(0, 29), (10, 10)]
    assert np.ptp(max(tracks, key=lambda t: len(t[0]))[1]) < 0.5


def test_equally_strong_glints_compete_in_the_same_order_whichever_was_hidden():
    """Two equally strong glints, the left one hidden for a row, then a single light between the two: the left glint
    goes on with it and the right one ends, as when neither is hidden (a glint that went on unseen was put behind the
    one in sight, and the two swapped who gets the peak)."""
    def lights(*cells):
        return sum(0.18 * np.exp(-((CELL - c) / 2.0) ** 2) for c in cells)
    den = np.ones((30, 80))
    den[10, 18:23] = 0.2
    tracks = follow([lights(20, 25)] * 10 + [lights(25)] + [lights(23)] * 19, den, noise=0.0001)
    ends = sorted((int(rows[-2]), round(float(u[1]), 1)) for rows, u, *_ in tracks)
    assert ends == [(10, 25.5), (29, 20.5)]


def test_a_later_hand_over_cannot_rewrite_a_piece_already_cut_off():
    """A small bump moving across a wide flat light: five cells a row, then an eight-cell jump the glint cannot make
    in a row, with no straight run across it that the bump's fast drift allows, so the glint is cut there. Later the
    bump comes back from one end of the flat to the other and stays (a hand-over with a run across it, over the flat,
    in the steady rows after). That run starts after the cut: the piece before the cut is exactly what it was before
    those rows were there (a run reaching back over the cut moved the piece's last row from 40.5 to 33.1)."""
    centres = np.array([20, 25, 30, 35, 40, 48, 53, 58, 63, 68, 73] + [2] * 20)
    fit = 0.14 * ((CELL >= 1) & (CELL <= 75)) + 0.006 * np.exp(-((CELL[None, :] - centres[:, None]) / 2.0) ** 2)
    before, after = follow(list(fit[:11]), noise=0.005), follow(list(fit), noise=0.005)
    assert spans(before) == [(0, 4), (5, 10)] and spans(after) == [(0, 4), (5, 30)]
    first, still_first = (min(tracks, key=lambda t: t[0][1]) for tracks in (before, after))
    np.testing.assert_allclose(first[1][1:-1], [20.5, 25.5, 30.5, 35.5, 40.5], atol=1e-6)
    for was, is_ in zip(first, still_first):
        np.testing.assert_allclose(is_, was, rtol=0, atol=1e-9)


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
    where it is painted, and none sits in the dip (the glints' soft edges overlap there, but the light dips: two peaks
    along the row, none between them)."""
    def shade(yy, xx):
        return 60 + 80 * (np.exp(-((xx - 190) / 6) ** 2) + np.exp(-((xx - 222) / 6) ** 2))
    core = maps(*leg(shade))['core']
    row = core[300, 110:250]
    peaks, _ = find_peaks(row, prominence=0.05)
    assert [round(p + 110, -1) for p in peaks] == [190, 220] and core[300, 187:194].max() > 0.5 and core[300, 219:226].max() > 0.5
    assert core[300, 200:213].max() < 0.5 * min(core[300, 187:194].max(), core[300, 219:226].max())


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


def test_a_flat_lit_leg_whose_highest_spot_moves_across_gets_one_unbroken_glint():
    """A leg lit flat across its middle (the artist's brushwork leaves only a faint bump or two on it) whose higher
    bump is the left one in the top half and the right one below: the highlight is painted as one streak that swings
    across, not as two that stop short of each other (the second used to begin 64 px to the side of where the first
    ended)."""
    def shade(yy, xx):
        plateau = np.clip(np.minimum((xx - 110) / 20, (250 - xx) / 20), 0, 1)
        over = 0.5 * (1 + np.tanh((yy - 300) / 30))
        return (70 + 70 * plateau + (2 - 1.5 * over) * np.exp(-((xx - 150) / 9) ** 2)
                + (0.5 + 1.5 * over) * np.exp(-((xx - 214) / 9) ** 2))
    core = maps(*leg(shade))['core']
    p = pieces(core, 0.3)
    ridge = core[60:540].argmax(1)
    assert len(p) == 1 and p[0][3] >= 590
    assert core[60:540].max(1).min() > 0.5
    assert abs(int(ridge[0]) - 150) <= 4 and abs(int(ridge[-1]) - 214) <= 4
    assert np.abs(np.diff(ridge)).max() <= 3                                # no jump: it moves over a stretch of leg


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


def limb(shade, left, right):
    """A leg down the image between x = left(yy) and right(yy), cut off by the image frame where either lies outside
    it; A across as in leg(). What maps() takes."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    m = (xx >= left(yy)) & (xx < right(yy))
    src = np.full((H, W, 3), 250, np.uint8)
    src[m] = np.clip(shade(yy, xx), 0, 255)[m][:, None].astype(np.uint8)
    R = m.astype(np.int8)
    return src, R, R.astype(np.float32), np.where(m, CX - xx, 0.0), np.where(m, yy, 0.0), R.copy()


def flat_lit(at=CX, bump=12.0, ledge=4.0, off=48.0):
    """The painted light of an evenly lit leg, as a function (yy, xx): a broad flat top, a faint ledge on the middle of the
    leg (x = at) and a bump on it, off to the side (x = at + off, 0.6 half-widths of a leg 160 px wide). With the
    defaults the bump stands 7 grey levels above the ledge: more than a peak must stand out to be a peak (oily.TIE),
    less than oily.LEVEL."""
    def shade(yy, xx):
        d = xx - at
        return 100 + 80 * np.exp(-(np.abs(d) / 100) ** 6) + ledge * np.exp(-(d / 7) ** 2) + bump * np.exp(-((d - off) / 7) ** 2)
    return shade


def glint_at(maps_, y0=60, y1=540):
    """The x of the glint's peak in each row of the core map and how bright it is there."""
    core = maps_['core'][y0:y1]
    return core.argmax(1), core.max(1)


def test_a_glint_on_an_evenly_lit_leg_goes_along_the_middle_not_to_a_bump_beside_it(monkeypatch):
    """The highest point of the light is a bump 48 px from the middle, higher than the faint ledge on the middle by a hair
    (7 grey levels): the brushwork's chance, so the glint goes along the middle (without centring it runs down the bump),
    as bright as it was."""
    args = leg(flat_lit())
    got = maps(*args)
    x, bright = glint_at(got)
    assert (bright > 0.5).all() and np.abs(x - CX).max() <= 3
    monkeypatch.setattr(oily, '_centre', lambda tracks, *a: tracks)
    free = maps(*args)
    assert np.abs(glint_at(free)[0] - (CX + 48)).max() <= 3
    assert np.allclose(got['band'][60:540].max(1), free['band'][60:540].max(1), atol=0.02)      # no brighter, no dimmer


def test_a_bump_standing_well_above_the_middle_keeps_its_glint():
    """The same, with the bump 24 grey levels above the ledge: that is a light of its own, the glint stays on it."""
    x, bright = glint_at(maps(*leg(flat_lit(bump=28.0))))
    assert (bright > 0.5).all() and np.abs(x - (CX + 48)).max() <= 3


def test_a_leg_with_no_cross_section_seen_whole_is_not_centred():
    """A leg cut off by the image frame all down one side: its middle is only taken to be the frame's edge (for facing),
    so there is no middle to centre on and the glint goes where the light does."""
    args = limb(flat_lit(), lambda yy: -50 + 0 * yy, lambda yy: 260 + 0 * yy)
    x, bright = glint_at(maps(*args))
    assert (bright > 0.5).all() and np.abs(x - (CX + 48)).max() <= 3


def test_a_side_out_of_sight_still_leaves_a_middle_to_centre_on():
    """A leg 200 px wide whose left side runs off the image from row 300 down: its middle there is measured from the side
    in sight with the width seen above, and the glint still goes along it."""
    left = lambda yy: np.where(yy < 300, 60, -40)
    x, bright = glint_at(maps(*limb(flat_lit(160), left, lambda yy: 260 + 0 * yy)))
    assert (bright > 0.5).all() and np.abs(x - 160).max() <= 3


def test_the_middle_runs_on_through_rows_where_both_sides_are_out_of_sight():
    """A limb wider than the image for a stretch of its length, whole above and below: through the stretch its middle runs
    on from either side, and the glint goes on along it."""
    left = lambda yy: np.where((yy >= 200) & (yy < 400), -60, 60)
    right = lambda yy: np.where((yy >= 200) & (yy < 400), 420, 260)
    x, bright = glint_at(maps(*limb(flat_lit(160), left, right)))
    assert (bright > 0.5).all() and np.abs(x - 160).max() <= 3


def test_the_middle_is_the_limbs_own_centre_line_where_it_bends():
    """An S-bent leg across courses that do not follow the bend (so the middle's place across, in A, moves down the
    leg), the ledge on its middle all the way down and the bump a fixed distance beside it: the glint follows the
    limb's own centre line."""
    cx = lambda yy: CX + 15 * np.sin(2 * np.pi * yy / H)
    bent = lambda yy, xx: flat_lit(0.0)(yy, xx - cx(yy))
    x, bright = glint_at(maps(*limb(bent, lambda yy: cx(yy) - 70, lambda yy: cx(yy) + 70)))
    assert (bright > 0.2).all() and np.abs(x - cx(np.arange(60, 540))).max() <= 5


REAL_SECTION = {0.1: 0.58, 0.2: 0.37, 0.3: 0.28, 0.4: 0.23, 0.5: 0.18, 0.6: 0.14, 0.8: 0.08}


def glow_row(maps_, y=300):
    """What a glint adds to the picture along a row (the three lobes with their weights, as render_oily sums them)."""
    return oily.W_CORE * maps_['core'][y] + oily.W_BAND * maps_['band'][y] + oily.W_TAIL * maps_['tail'][y]


@pytest.mark.parametrize('half', [80, 30])
def test_a_glints_cross_section_is_that_of_real_glossy_tights(half):
    """A glint in the middle of a leg is a bright narrow core on a broad soft glow, as the highlight is on product photos
    of glossy black tights (profile measured on them, in half-widths of the leg from the peak): .58 of the peak at 0.1,
    .37 at 0.2, .28 at 0.3, .18 at 0.5, .08 at 0.8. It was a line 2-3 px wide (.25, .12, .08, .03, .01), which the courses
    cut into dashes. On a leg 160 px wide and on one 60 px wide alike: no floor of some px holds a narrow leg's skirt
    wider than the real one's."""
    shade = lambda yy, xx: lit(yy, xx, at=CX)
    row = glow_row(maps(*limb(shade, lambda yy: CX - half + 0 * yy, lambda yy: CX + half + 0 * yy)))
    peak = row[CX - 1:CX + 2].max()
    for d, want in REAL_SECTION.items():
        got = 0.5 * (row[int(round(CX - d * half))] + row[int(round(CX + d * half))]) / peak
        assert abs(got - want) < 0.03, (half, d, round(float(got), 3), want)


def test_a_glint_is_as_broad_as_the_leg_it_is_on():
    """The same highlight on a leg of 100 px instead of 160: its glow is as broad in half-widths, so 5/8 as broad in px."""
    def width(left, right):
        row = glow_row(maps(*limb(lambda yy, xx: lit(yy, xx, at=CX), lambda yy: left + 0 * yy, lambda yy: right + 0 * yy)))
        return float((row > 0.5 * row.max()).sum())
    wide, narrow = width(X0, X1), width(CX - 50, CX + 50)
    assert 0.5 < narrow / wide < 0.75, (wide, narrow)


def flat(grey):
    return lambda yy, xx: np.full_like(xx, float(grey))


def render(src, R, alpha, A, V, REG, s=1.0, zone=True):
    """The picture render_oily makes of a leg (courses on, grain off) and its maps. zone=False: the zone map zeroed."""
    gn, gc = np.zeros((H, W), np.float32), np.zeros((H, W, 3), np.float32)
    maps_ = oily.oily_maps(src, R, alpha, A, V, 0.64, REG=REG)
    if not zone:
        maps_ = maps_[:-1] + (np.zeros_like(maps_[-1]),)
    return oily.render_oily(src, R, V, A, alpha, look.geometry(100.0, W, H), s, *maps_, noise=(gn, gc)), maps_


def edge_share(img, u, half=80, rows=slice(250, 350)):
    """How bright a leg's picture is u half-widths from its middle (the two sides averaged), as a share of its middle's
    (the median over |u| <= 0.5), averaged over rows."""
    col = img[rows].astype(np.float32).mean((0, 2))
    mid = np.median([col[int(round(CX + v * half))] for v in np.linspace(-0.5, 0.5, 21)])
    return 0.5 * (col[int(round(CX - u * half))] + col[int(round(CX + u * half))]) / mid


@pytest.mark.parametrize('grey', [20.0, 45.0])
def test_a_dark_stocking_goes_black_toward_its_edges_as_real_glossy_tights_do(grey):
    """Dark art on a leg seen whole: its brightness toward the edges falls as on product photos of glossy black tights
    (as a share of the middle's, far side, median over the thigh, shin and ankle of both legs: .9 at 0.7 half-widths from
    the middle, .76 at 0.8, .54 at 0.9; the stretches range .67-1.0, .33-.98, .16-.71). Without the zones it was .74,
    .81 and .91: edges as bright as the middle."""
    img, maps_ = render(*leg(flat(grey)))
    assert maps_[-1][300, CX] > 0.95
    for u, lo, hi in ((0.7, 0.67, 0.85), (0.8, 0.33, 0.72), (0.9, 0.16, 0.6)):
        assert lo <= edge_share(img, u) <= hi, (u, edge_share(img, u))
    plain, _ = render(*leg(flat(grey)), zone=False)
    assert edge_share(plain, 0.9) > 0.6


def test_a_pale_stocking_keeps_its_own_edges():
    """Pale art (a white stocking's) has its own edge shading painted in: the zones are not on it, and what the style
    made of it before is unchanged."""
    img, maps_ = render(*leg(flat(235)))
    assert maps_[-1].max() < 0.02
    off, _ = render(*leg(flat(235)), zone=False)
    assert np.abs(img.astype(int) - off).max() <= 1


def test_the_zones_are_not_believed_where_the_outline_is_out_of_sight():
    """A leg cut by the image frame all down one side, one wider than the picture, a sliver: no cross-section is seen
    whole, or the outline is a guess, so the black edges stay off."""
    for left, right in ((lambda yy: -50 + 0 * yy, lambda yy: 260 + 0 * yy),
                        (lambda yy: -50 + 0 * yy, lambda yy: 420 + 0 * yy),
                        (lambda yy: CX - 3 + 0 * yy, lambda yy: CX + 3 + 0 * yy)):
        assert maps(*limb(flat(45), left, right))['zone'].max() < 0.02


def test_a_stretch_with_one_side_out_of_sight_gets_half_the_zones():
    """The left side of a dark leg runs off the image from row 300 on: above that its outline is seen whole, below it
    the side in sight is measured against the width seen above, and the zones are half believed."""
    left = lambda yy: np.where(yy < 300, 60, -40)
    zone = maps(*limb(flat(45), left, lambda yy: 260 + 0 * yy))['zone']
    assert zone[60:200, 160].min() > 0.95 and 0.4 < zone[400:540, 160].mean() < 0.6


def test_a_wall_leaves_no_seam_in_the_zones_either():
    src, R, alpha, A, V, REG = leg(flat(45))
    cut = np.zeros((H, W), bool)
    cut[296:304, X0:X1] = True
    zone = oily.oily_maps(src, R, alpha, A, V, 0.64, cut=cut, REG=REG)[-1]
    assert zone[296:304, CX].min() > 0.9 and zone[100, CX] > 0.95 and zone[500, CX] > 0.95


def frame_trust(rows, hidden):
    """_frame's trust for a leg 160 px across and `rows` rows long (2 px to a band at this scale); hidden(yy, xx): the
    pixels whose outline is out of sight."""
    yy, xx = np.mgrid[0:rows, 0:160]
    return oily._frame(yy.ravel().astype(float), xx.ravel() - 80.0, hidden(yy, xx).ravel(), 0.64)[-1]


def test_a_cut_across_a_pieces_end_is_no_hidden_outline():
    """A wall or the frame across a piece's end hides a whole cross-section there, not the outline beside it: the end
    bands keep the trust of the bands inside, for short pieces (7 to 12 bands: one jumped from .61 to 1.0 between 8 and 9)
    and long ones alike."""
    for rows in range(14, 26):
        assert frame_trust(rows, lambda yy, xx, rows=rows: (yy < 2) | (yy >= rows - 2)).min() > 0.9, rows
    assert frame_trust(300, lambda yy, xx: (yy < 2) | (yy >= 298)).min() > 0.99


def test_a_side_out_of_sight_in_a_pieces_end_bands_is_still_a_hidden_outline():
    """One side hidden along the first bands only is a real occlusion, not a cut across the end: half believed there."""
    trust = frame_trust(300, lambda yy, xx: (xx < 6) & (yy < 6))
    assert trust[0] < 0.9 and trust[-1] > 0.99


def test_the_zones_follow_a_stockings_colour_not_its_shadows_or_highlights():
    """Pale art with a deep shadow down one side is still a pale stocking (the region's median decides), dark art with a
    bright highlight still a dark one."""
    assert maps(*leg(lambda yy, xx: np.where(xx < X0 + 50, 60.0, 225.0)))['zone'].max() < 0.1
    assert maps(*leg(lambda yy, xx: 40 + 150 * np.exp(-((xx - CX) / 14.0) ** 2)))['zone'][300, CX - 50] > 0.95


@pytest.mark.parametrize('floor', [0.0, 0.4])
def test_zone_and_facing_stay_in_range_on_odd_limbs(floor, monkeypatch):
    """Limbs of any width, pushed against or off the frame, bent, dark or pale, with a highlight painted down their upper
    half or none, with the floor glint on or off: every map finite, the glint maps, zone and facing in 0..1."""
    monkeypatch.setattr(oily, 'FLOOR_GLINT', floor)
    rng = np.random.default_rng(5)
    for _ in range(12):
        half, off, amp = rng.uniform(3, 140), rng.choice([0, -150, 150]), rng.uniform(0, 30)
        grey, glow = rng.choice([20, 60, 120, 230]), rng.choice([0.0, 70.0])
        cx = lambda yy, off=off, amp=amp: CX + off + amp * np.sin(yy / 70.0)

        def shade(yy, xx, cx=cx, half=half, grey=grey, glow=glow):
            return grey + glow * np.exp(-((xx - cx(yy) - 0.3 * half) / max(0.25 * half, 3.0)) ** 2) * (yy < 300)
        got = maps(*limb(shade, lambda yy: cx(yy) - half, lambda yy: cx(yy) + half))
        assert all(np.isfinite(v).all() for v in got.values())
        for key in ('core', 'band', 'tail', 'centre', 'zone', 'facing'):
            assert 0 <= got[key].min() and got[key].max() <= 1, key


@pytest.fixture
def floor_glint(monkeypatch):
    """The floor glint of a dark limb, switched on."""
    monkeypatch.setattr(oily, 'FLOOR_GLINT', 0.4)


def ramp(yy, top, bottom):
    """1 above row top, 0 below row bottom, smooth between."""
    x = np.clip((yy - top) / (bottom - top), 0, 1)
    return 1 - x * x * (3 - 2 * x)


def upper(*lights, grey=30.0):
    """Dark art with highlights painted down the upper half of the leg only, fading out between rows 260 and 330:
    (x, strength, width) of each; what a thigh with a calf under it looks like when the art paints the thigh's light."""
    return lambda yy, xx: grey + sum(a * np.exp(-((xx - x) / w) ** 2) for x, a, w in lights) * ramp(yy, 260, 330)


def test_a_dark_limb_with_no_painted_light_has_a_faint_glint_down_its_middle(floor_glint):
    """A flat dark leg, no highlight painted: one glint down its middle, a third to a half as strong as a painted
    one can be, and nothing elsewhere."""
    got = maps(*leg(flat(30)))
    x, bright = glint_at(got)
    assert (bright > 0.3).all() and (bright < 0.5).all() and np.abs(x - CX).max() <= 2
    assert got['core'][:, :CX - 30].max() < 0.05 and got['core'][:, CX + 30:].max() < 0.05


def test_the_floor_glint_shows_in_the_picture_and_only_faintly(floor_glint, monkeypatch):
    """On the render the middle of the leg is lifted over the part of the leg a little way from it, but by a good deal
    less than a painted highlight lifts it; with the floor off there is no line."""
    def lift(img):
        return float(img[250:350, CX - 1:CX + 2].mean() - img[250:350, CX - 30:CX - 27].mean())
    on = lift(render(*leg(flat(30)))[0])
    monkeypatch.setattr(oily, 'FLOOR_GLINT', 0.0)
    off = lift(render(*leg(flat(30)))[0])
    painted = lift(render(*leg(lambda yy, xx: 30 + 100 * np.exp(-((xx - CX) / 20.0) ** 2)))[0])
    assert 15 < on < 0.6 * painted and abs(off) < 6, (on, off, painted)


def test_a_glint_painted_the_whole_length_has_the_floor_out_of_sight_beneath_it(floor_glint, monkeypatch):
    """A highlight painted down the whole leg is stronger than the floor all the way and on the same line: every map is
    as it is without the floor, to a hundredth."""
    args = leg(lit)
    on = maps(*args)
    monkeypatch.setattr(oily, 'FLOOR_GLINT', 0.0)
    off = maps(*args)
    assert all(np.abs(on[key] - off[key]).max() < 0.01 for key in on)


def test_a_glint_painted_down_the_upper_half_goes_on_down_the_lower_at_its_place(floor_glint, monkeypatch):
    """A thigh's highlight at x = 205 (0.3 half-widths off the middle) fading out at row 300, a calf with none painted: the
    glint goes on down the calf along x = 205 at the floor's strength, where without the floor it was gone; the painted
    part is as painted, to a hundredth."""
    args = leg(upper((205, 100, 28.0)))
    on = maps(*args)
    monkeypatch.setattr(oily, 'FLOOR_GLINT', 0.0)
    off = maps(*args)
    x, bright = glint_at(on, 380, 540)
    assert (bright > 0.35).all() and np.abs(x - 205).max() <= 2 and off['core'][380:540].max() < 0.05
    assert np.abs(on['core'][:240] - off['core'][:240]).max() < 0.01


@pytest.mark.parametrize('depth', [0.8, 1.0])
def test_a_dim_stretch_or_a_gap_in_a_painted_glint_is_lifted_to_the_floor(floor_glint, monkeypatch, depth):
    """A highlight down a dark leg that is dimmed by 80 % (or gone) around row 300: the glint keeps at least the floor's
    strength all the way, at the same place, where without the floor it breaks."""
    def dip(yy, xx):
        return 30 + 100 * np.exp(-((xx - 205) / 28.0) ** 2) * (1 - depth * np.exp(-((yy - 300) / 30.0) ** 2))
    args = leg(dip)
    on = maps(*args)
    monkeypatch.setattr(oily, 'FLOOR_GLINT', 0.0)
    off = maps(*args)
    x, bright = glint_at(on)
    assert bright.min() > 0.35 and np.abs(x - 205).max() <= 2
    assert off['core'][290:310].max() < 0.2


def floor_of(rows, u, s, su=None, nrow=40, half=50.0, believed=1.0, held=0.0, **kw):
    """oily._floor_glint's answer for one painted glint given by its rows, place (u: half-widths from the middle) and
    strength s, on a limb 50 px to a side and 400 long whose middle slants (3 px a row), and any other tracks (kw: others):
    (the tracks it returns, the main one's rows, place and strength). held: where the limb's other pieces put the glint."""
    c = 3.0 * np.arange(nrow)
    kq = np.arange(nrow)
    rows, u, s = (np.asarray(x, np.float64) for x in (rows, u, s))
    ones = np.ones(len(rows))
    su = ones if su is None else np.asarray(su, np.float64)
    ext = np.concatenate([[0], kq, [nrow - 1]])
    painted = [(rows, c[np.clip(rows, 0, nrow - 1).astype(int)] + u * half, s, ones, su, ones)] + list(kw.get('others', []))
    out = oily._floor_glint(painted, nrow, 400.0, half, kq, c, np.full(nrow, half), 0.0, 1.0, np.full(nrow, believed), held)
    main = out[-1]
    return out, main[0], (main[1] - c[ext[np.clip(main[0] + 1, 0, nrow + 1).astype(int)]]) / half, main[2]


def test_the_floors_place_goes_over_to_the_glints_as_it_dims_and_holds_it_past_its_end(floor_glint):
    """A glint painted 0.3 half-widths off the middle, strong down to row 15 and fading out by row 20, wandering off its
    place from half strength down (where it is faint its place is a guess, by a third of a half-width on real pictures):
    where it is as strong as the floor it is as painted; as it dims below the floor its place gives way to the place it
    had where it was clear, held from the row it is gone; and never less than the floor's strength."""
    rows = np.arange(-1.0, 21.0)
    s = np.clip(1.0 - np.maximum(rows - 10, 0) / 10, 0.0, 1.0)
    u = np.where(s >= 0.5, 0.3, 0.3 - 0.5 * (1 - s))
    out, r, place, st = floor_of(rows, u, s)
    assert r[0] == -1 and r[-1] == 40 and (st >= 0.4 - 1e-9).all()
    assert np.abs(place[r <= 15] - 0.3).max() < 1e-9 and np.abs(place[r >= 19] - 0.3).max() < 1e-9
    assert place.min() > -0.11 and place.max() < 0.31


def test_the_floor_is_the_painted_glint_where_that_is_stronger_and_leaves_other_lights_alone(floor_glint):
    """Where the painted glint is stronger than the floor its rows are as painted, to the last digit; another painted
    glint (a second light) is not touched."""
    rows = np.arange(-1.0, 21.0)
    s = 0.5 + 0.5 * np.cos(rows / 4.0) ** 2
    u = 0.2 + 0.05 * np.sin(rows / 3.0)
    other = (np.arange(5.0, 15.0), np.full(10, 130.0), np.full(10, 0.7), np.ones(10), np.ones(10), np.ones(10))
    out, r, place, st = floor_of(rows, u, s, others=[other])
    assert out[0] is other
    inside = r <= 20
    np.testing.assert_array_equal(st[inside], s)
    assert np.abs(place[inside] - u).max() < 1e-9


def test_the_floor_weighs_a_painted_row_as_painted_in_the_smoothing_and_its_own_rows_are_free(floor_glint):
    """_curve weighs a row by (strength + 1e-3) x sureness: the rows the floor lifts keep the weight they had, so the painted
    glint's path is smoothed as it was without the floor; the glint's pad rows and the rows past them are the floor's own,
    free of that smoothing."""
    rows = np.arange(-1.0, 21.0)
    s = 0.1 + 0.9 * np.sin(rows / 4.0) ** 2                                       # dim rows (under the floor) and strong ones
    out, r, place, st = floor_of(rows, np.full(22, 0.2), s, su=np.full(22, 0.8))
    rows_f, tu, st_f, wd, su_f, dl, free = out[-1]
    inner = (rows_f > -1) & (rows_f < 20)
    assert (st_f[inner] > s[1:-1] + 1e-9).any()                                   # some rows are lifted
    np.testing.assert_allclose((st_f[inner] + 1e-3) * su_f[inner], (s[1:-1] + 1e-3) * 0.8)
    assert not free[inner].any() and free[rows_f <= -1].all() and free[rows_f >= 20].all()


def curve_x(kept_x, kept_w, free_x, free_w, floor_px):
    """oily._curve on a vertical strip of pixels (x from -80 to 80, 10 px to a row, A = x) for a track whose painted rows 0.. follow
    kept_x with the weights kept_w and whose own rows of the floor (free) go on from there along free_x with free_w: the x of
    the curve at each row."""
    n = len(kept_x) + len(free_x)
    xs, ys = (g.ravel().astype(float) for g in np.meshgrid(np.arange(-80, 81), np.arange(0, 10 * (n + 1))))
    rows = np.arange(-1, n + 1, dtype=float)
    ga, st, su, dl, free = (np.zeros(len(rows)) for _ in range(5))
    free = free.astype(bool)
    for q, (x, w) in enumerate(zip(list(kept_x) + list(free_x), list(kept_w) + list(free_w))):
        ga[q + 1], st[q + 1], su[q + 1], dl[q + 1], free[q + 1] = x, w, 1.0, 1.0, q >= len(kept_x)
    curve = oily._curve(rows, ga, st, dl, su, ys / 10.0 - 0.5, xs.copy(), xs, ys, 1.0, floor=floor_px, free=free)
    return np.interp(10.0 * np.arange(n) + 4.5, curve[:, 1], curve[:, 0])


def test_the_floors_own_rows_go_on_from_the_smoothed_end_of_a_painted_glint_without_a_jog():
    """The smoothing takes a corner off the painted path (a few px, up to a third of a half-width on real pictures), the floor's
    own rows follow the path as it is and the offset the smoothing made at the glint's last row dies out over a few rows: the
    path steps by its own slope (6 px a row) or less, where without it the floor started 11 px from where the glint ended."""
    kept = [0.0 if q <= 19 else 6.0 * (q - 19) for q in range(25)]
    x = curve_x(kept, [1.0] * 25, [30.0] * 15, [0.4] * 15, 12.0)
    assert np.abs(np.diff(x[18:33])).max() < 4, np.round(x[18:33], 1)


def test_a_weak_painted_path_is_followed_within_its_tolerance_whatever_the_floor_beside_it_weighs():
    """A painted path 0.05 strong that curves (12 px each way) with the floor beside it at 0.4: its rows are clear (they are
    measured against the painted rows' own best, not the floor's), so the smoothing keeps each within its tolerance (2 px)
    of where the peak is; the floor's weight must not take that away."""
    kept = [12.0 * np.sin(q / 3.0) for q in range(25)]
    x = curve_x(kept, [0.05] * 25, [0.0] * 15, [0.4] * 15, 2.0)
    assert np.abs(x[:25] - np.asarray(kept)).max() < 2.5


@pytest.mark.parametrize('sure', [1.0, 0.0])
def test_a_place_past_the_limb_or_not_seen_is_no_place_for_the_floor_to_hold(floor_glint, sure):
    """A painted glint strong down to row 15 whose place is 4.4 half-widths from the middle (the estimate of a frame that
    does not reach it), or whose rows were only carried over (sureness 0): as painted where it is, but the floor goes on
    past its end down the middle, not along that."""
    rows = np.arange(-1.0, 21.0)
    s = np.clip(1.0 - np.maximum(rows - 10, 0) / 10, 0.0, 1.0)
    out, r, place, st = floor_of(rows, np.full(22, 4.4 if sure else 0.3), s, su=np.full(22, sure))
    assert np.abs(place[r >= 20]).max() < 1e-9
    assert np.abs(place[r <= 15] - (4.4 if sure else 0.3)).max() < 1e-9


@pytest.mark.parametrize('top', [0.05, 0.0749, 0.0751, 0.1, 0.14, 0.4])
def test_a_faint_painted_glint_goes_on_at_the_held_place_not_down_the_middle(floor_glint, top):
    """A piece held at u = 0.3 (the other pieces of its limb have the glint there) with a glint of its own painted along the
    same place, as strong as top, from nothing to clear: the floor stays at 0.3 along the whole piece, whatever that is. It
    is the share a faint glint falls short of FAINT that goes to the held place, not to the middle (it went to 0 the
    moment the glint became clear enough to count)."""
    rows = np.arange(-1.0, 11.0)
    out, r, place, st = floor_of(rows, np.full(12, 0.3), np.full(12, top), held=0.3)
    assert np.abs(place - 0.3).max() < 0.02


def test_a_held_place_given_for_both_ends_of_a_piece_runs_from_the_one_to_the_other(floor_glint):
    """With no glint painted, the floor goes along the place held at the top of the piece, -0.4, to the one held at its
    bottom, 0.6, in a straight line along the piece's actual extent: the first row of its pixels (row -0.5, the top of the
    fit's first) to the last (row 38.8: the fit's 40th row is a short one, 0.8 of it covered, and the piece ends in it, not
    at the padding row past it), at each of them there. Each row's place is where its pixels are: the last row's is the
    middle of the 0.3 of it the piece covers."""
    nrow, half = 40, 50.0
    c = 3.0 * np.arange(nrow)
    t_lo, t_hi = -0.5, 38.8
    out = oily._floor_glint([], nrow, 400.0, half, np.arange(nrow), c, np.full(nrow, half), 0.0, 1.0, np.ones(nrow), (-0.4, 0.6),
                            np.linspace(t_lo, t_hi, 300))
    rows, tu = out[0][0], out[0][1]
    place = (tu - c[np.clip(rows, 0, nrow - 1).astype(int)]) / half
    expect = lambda t: -0.4 + (t - t_lo) / (t_hi - t_lo)                    # 0.6 - -0.4 = 1: straight along the extent
    assert abs(place[0] + 0.4) < 1e-9 and abs(place[-1] - 0.6) < 1e-9                   # the padding rows are the ends
    full = (rows >= 0) & (rows <= 38)
    np.testing.assert_allclose(place[full], expect(rows[full]), atol=1e-9)
    assert abs(place[rows == 39][0] - expect(0.5 * (38.5 + t_hi))) < 1e-9


def one_row(tu, st, rows=(-1.0, 0.0, 1.0)):
    """A painted glint of one row of the lighting fit: the track _tracks gives (the same value in its three rows: the padding
    rows are its own at both ends of a piece)."""
    rows = np.asarray(rows)
    return (rows, np.full(3, float(tu)), np.full(3, float(st)), np.ones(3), np.ones(3), np.ones(3))


SLIVER = dict(length=400.0, half=50.0, kq=np.zeros(1, int), c=np.array([30.0]), h=np.array([50.0]), believed=np.ones(1))


def sliver_floor(tracks, held, t):
    s = SLIVER
    return oily._floor_glint(tracks, 1, s['length'], s['half'], s['kq'], s['c'], s['h'], 0.0, 1.0, s['believed'], held, t)


def test_the_floor_of_a_piece_of_one_fit_row_runs_across_it_in_thirds_of_its_extent(floor_glint):
    """A piece of one row of the lighting fit (a sliver of a limb, 20 px or less) has one glint position to a row, and a
    glint of one row is a point: a blob in its middle. Its floor is counted in thirds of the piece's extent instead (an
    eighth element of the track: where its rows start and how many go to a row), from the place held at its top to the one at
    its bottom, each third's place where its pixels are (their mean: the draw puts the glint of a row there)."""
    t = np.concatenate([np.linspace(-0.5, 0.2, 8), [0.2]])                 # a few pixel rows, as a sliver has: 7 px tall
    out = sliver_floor([], (-0.4, 0.6), t)
    assert len(out) == 1 and len(out[0]) == 8
    rows, tu, st, wd, su, dl, free, (offset, per_row) = out[0]
    assert list(rows) == [-1, 0, 1, 2, 3] and offset == -0.5 and per_row == pytest.approx(3.0 / 0.7)
    tt = (t - offset) * per_row - 0.5                                              # the rows of the draw
    means = [t[(tt >= k - 0.5) & (tt < k + 0.5)].mean() for k in range(3)]
    place = (tu - 30.0) / 50.0
    np.testing.assert_allclose(place[1:4], [-0.4 + (m + 0.5) / 0.7 for m in means], atol=1e-9)
    assert place[0] == pytest.approx(-0.4) and place[4] == pytest.approx(0.6) and (st >= 0.4 - 1e-9).all() and free is None
    two = oily._floor_glint([], 2, 400.0, 50.0, np.zeros(2, int), np.array([30.0, 30.0]), np.full(2, 50.0), 0.0, 1.0, np.ones(2), (0.0, 0.0))
    assert len(two[0]) == 6                                                          # two rows are two points: as before


def test_the_thirds_of_a_sliver_take_the_pixels_the_draw_puts_in_them(floor_glint):
    """A sliver 5 px tall at a fit row of 20.853115214047392 px (about one sliver in seven is one where it matters): its last
    pixel is at the very edge of the last third, and `floor((t - t_lo) * 3 / span)` and the draw's `(t - t_lo) * (3 / span) -
    0.5` in [k - 0.5, k + 0.5) differ in the last digit and put it in the last third and in none. The places of the thirds are
    at the means of the pixels the draw takes, by its own expression: the line is where the draw's rows are (it ended 4 px off
    at a strip of 8)."""
    t = np.arange(5.0) / 20.853115214047392 - 0.5
    out = sliver_floor([], (-0.4, 0.6), t)
    rows, tu, st, wd, su, dl, free, (offset, per_row) = out[0]
    tt = (t - offset) * per_row - 0.5
    assert [int(((tt >= k - 0.5) & (tt < k + 0.5)).sum()) for k in range(3)] == [2, 1, 1]          # the last pixel is in no third
    means = [t[(tt >= k - 0.5) & (tt < k + 0.5)].mean() for k in range(3)]
    np.testing.assert_allclose((tu[1:4] - 30.0) / 50.0, [-0.4 + (m - t[0]) / (t[-1] - t[0]) for m in means], atol=1e-9)


@pytest.mark.parametrize('painted, strength, expect_place', [(0.3, 1.0, 0.3), (0.3, 0.02, None), (0.3, 0.07, None)])
def test_a_sliver_with_a_painted_glint_has_it_in_thirds_too_as_painted_or_as_faint_as_it_is(floor_glint, painted, strength, expect_place):
    """A painted glint of one fit row (it was the case that stayed a point: the thirds were for a glint with none painted
    only; a track of one row is a blob however faint, 0.0276 of the lighting's top was enough): the floor and the painted
    glint are one track in thirds of the extent. Strong (1.0), it is as painted: its place (0.3) and its strength all
    along. Faint (0.02, 0.07: under the floor's 0.4, and under half of FAINT, so with no place of its own to follow), it is
    lifted to the floor, and its place gives way to the place the piece's limb holds at its top (-0.4) and bottom (0.6), as
    the floor of a long piece does, not to the middle."""
    t = np.linspace(-0.5, 0.2, 30)
    out = sliver_floor([one_row(30.0 + painted * 50.0, strength)], (-0.4, 0.6), t)
    assert len(out) == 1 and len(out[0]) == 8
    rows, tu, st, wd, su, dl, free, remap = out[0]
    place = (tu - 30.0) / 50.0
    assert (st >= max(strength, 0.4) - 1e-9).all()
    if expect_place is not None:
        np.testing.assert_allclose(place, expect_place, atol=1e-9)
    else:
        assert place[0] == pytest.approx(-0.4) and place[-1] == pytest.approx(0.6) and (np.diff(place) > 0).all()


def test_a_long_piece_of_which_a_small_patch_is_in_sight_keeps_its_rows_of_the_fit(floor_glint):
    """A piece of one fit row because only a small patch of it is in sight (the lighting is fitted to that), whose pixels
    reach 30 rows from it: thirds of its extent would be much coarser than the one row there is a fit for. It has its floor
    as it had, in rows of the fit: three padded rows, no eighth element."""
    out = sliver_floor([], 0.0, np.linspace(-30.0, 40.0, 200))
    assert len(out) == 1 and len(out[0]) == 6 and list(out[0][0]) == [-1, 0, 1]
    out = sliver_floor([one_row(45.0, 1.0)], 0.0, np.linspace(-30.0, 40.0, 200))
    assert len(out[0]) == 7


def _limb_piece(j, v0, v1, size=1000):
    return SimpleNamespace(j=j, vmean=(v0 + v1) / 2.0, vlo=float(v0), vhi=float(v1), size=size)


def test_the_glints_of_the_other_pieces_of_a_limb_count_as_far_as_they_are_clear_nearest_first():
    """_nearest: where a piece with none of its own has its glint, given the others' glints at their ends toward it
    (u at the first clear row, u at the last, follow): a faint nearer glint (follow 0.03) hints at its place and the clear
    one beyond it has the rest; a clear nearer one is the place alone; and ties by distance go to the bigger piece."""
    job = _limb_piece(1, 400, 500)
    thigh, calf, other = _limb_piece(2, 0, 200), _limb_piece(3, 210, 390), _limb_piece(4, 210, 390, size=5000)
    ends = {2: (0.5, 0.5, 1.0), 3: (0.2, 0.2, 0.03), 4: (-0.3, -0.3, 1.0)}
    assert oily._nearest(job, [thigh, calf], ends) == pytest.approx((0.03 * 0.2 + 0.97 * 0.5,) * 2)
    assert oily._nearest(job, [thigh, calf, other], ends) == pytest.approx((-0.3, -0.3))
    assert oily._nearest(job, [calf, other], ends) == pytest.approx((-0.3, -0.3))
    assert oily._nearest(job, [calf], ends) == pytest.approx((0.006, 0.006))      # alone, it hints: toward the middle
    assert oily._nearest(job, [], ends) == (0.0, 0.0)


@pytest.mark.parametrize('sign', [1, -1])
def test_donors_as_near_and_as_big_as_each_other_have_no_side_preferred(sign):
    """Two pieces beside each other on the limb, equally near the piece with no glint and as big, with glints at -0.3 and
    +0.3 of the limb's half-width (and the other way round: sign): the glint goes where neither is, down the middle, and
    not along the one whose place happens to sort last; and one that is the clearer has more of a say in it."""
    job = _limb_piece(1, 400, 500)
    left, right = _limb_piece(2, 0, 390), _limb_piece(3, 0, 390)
    assert oily._nearest(job, [left, right], {2: (-0.3 * sign, -0.3 * sign, 1.0), 3: (0.3 * sign, 0.3 * sign, 1.0)}) == pytest.approx((0.0, 0.0))
    assert oily._nearest(job, [right, left], {2: (-0.3 * sign, -0.3 * sign, 0.5), 3: (0.3 * sign, 0.3 * sign, 0.5)}) == pytest.approx((0.0, 0.0))
    # the clearer glint (follow 1) at -0.3, the other (follow 0.5) at +0.3: (-0.3 + 0.5 * 0.3) / 1.5 = -0.1, taken whole
    mixed = oily._nearest(job, [left, right], {2: (-0.3 * sign, -0.3 * sign, 1.0), 3: (0.3 * sign, 0.3 * sign, 0.5)})
    assert mixed == pytest.approx((-0.1 * sign, -0.1 * sign))


@pytest.mark.parametrize('shift, nearer', [(0.0, None), (1e-4, None), (-1e-4, None), (0.4, None), (2.0, 'right'), (-2.0, 'left')])
def test_donors_as_near_as_each_other_to_a_pixel_are_as_near_whatever_the_solvers_last_digits(shift, nearer):
    """Two clear donors of one size at -0.3 and +0.3, one's stretch of V to the piece differing from the other's by shift px:
    within half a pixel (the solver's last digits, 1e-4, are no distance) they are as near as each other and the glint goes
    down the middle, as when they tie exactly (it was -0.3 or +0.3, by the sign of the digits); two pixels or more, the nearer
    has it."""
    job = _limb_piece(1, 400, 500)
    left, right = _limb_piece(2, 0, 390), _limb_piece(3, 0, 390 + shift)
    got = oily._nearest(job, [left, right], {2: (-0.3, -0.3, 1.0), 3: (0.3, 0.3, 1.0)})
    assert got == pytest.approx((0.0, 0.0) if nearer is None else ((0.3, 0.3) if nearer == 'right' else (-0.3, -0.3)))


def test_a_few_whole_cross_sections_do_not_make_the_limb_narrower_than_it_is_seen():
    """_frame's typical half-width is that of the cross-sections seen whole, and a limb is at least as wide as it is seen:
    hmed_min is the least it is taken to be. A leg 80 px to a side with an edge that runs on out of sight all down it but
    for a toe 7 px wide has 3 px for its typical half-width, from the toe alone; given the 40 px seen otherwise it is 40; and
    the same leg with nothing hidden is wider than that, whatever minimum is under it."""
    n = 200
    Vg, Ag = np.nonzero(np.ones((n, 160)))
    Vg, Ag = Vg.astype(np.float64), Ag.astype(np.float64) - 80
    keep = (Vg < 190) | ((Vg >= 190) & (np.abs(Ag) < 4))                                # a toe 8 px wide at the bottom
    Vg, Ag = Vg[keep], Ag[keep]
    hidden = (Vg < 190) & (Ag < -75)                                                       # an edge the limb goes on behind
    alone = oily._frame(Vg, Ag, hidden, 0.64)
    floored = oily._frame(Vg, Ag, hidden, 0.64, hmed_min=40.0)
    plain = oily._frame(Vg, Ag, np.zeros(len(Vg), bool), 0.64)
    assert alone[6] and alone[4] < 6 and floored[4] == 40.0 and floored[6]
    assert plain[4] > 40.0
    assert oily._frame(Vg, Ag, np.zeros(len(Vg), bool), 0.64, hmed_min=1.0)[4] == plain[4]       # a minimum under it changes nothing


def test_a_piece_between_two_painted_ones_takes_the_place_each_has_at_its_end():
    """A piece with a glint painted before it along the limb (u = 0.5 at its end) and one after it (u = -0.4 at its first
    clear row): (top, bottom) = (0.5, -0.4). Only one side has a glint: both ends alike. The ends toward the piece are the
    ones that count, not the far ends."""
    job = _limb_piece(1, 300, 400)
    above, below = _limb_piece(2, 0, 290), _limb_piece(3, 410, 700)
    ends = {2: (0.9, 0.5, 1.0), 3: (-0.4, -0.9, 1.0)}
    assert oily._nearest(job, [above, below], ends) == pytest.approx((0.5, -0.4))
    assert oily._nearest(job, [above], ends) == pytest.approx((0.5, 0.5))
    assert oily._nearest(job, [below], ends) == pytest.approx((-0.4, -0.4))


def test_nothing_is_added_without_a_floor_or_on_a_stretch_too_short(floor_glint, monkeypatch):
    c = 3.0 * np.arange(40)
    track = (np.arange(-1.0, 3.0), np.zeros(4), np.ones(4), np.ones(4), np.ones(4), np.ones(4))
    args = ([track], 40, 400.0, 50.0, np.arange(40), c, np.full(40, 50.0), 0.0, 1.0, np.ones(40))
    assert oily._floor_glint(*args)[0] is not track and len(oily._floor_glint(*args)) == 1
    assert oily._floor_glint(*args[:2], 30.0, *args[3:])[0] is track                   # 30 px: under 1.5 widths
    monkeypatch.setattr(oily, 'FLOOR_GLINT', 0.0)
    assert oily._floor_glint(*args)[0] is track
    assert oily._floor_glint([], 40, 400.0, 50.0, *args[4:]) == []


@pytest.mark.parametrize('end, dim, slide, shift', [(0.77, (250, 350), (380, 530), 25), (0.80, (250, 330), (350, 500), 20)])
def test_a_painted_glint_that_moves_as_it_dims_stays_one_line_with_the_floor(floor_glint, end, dim, slide, shift):
    """A highlight that dims to a share of its light (still above the floor in strength: 0.45 against 0.4) and then slides
    sideways down the leg (25 px of its 160): the floor under it goes over to its place, so every row has one line, not
    the painted glint and the floor's one beside it (as when the floor held the place the glint had where it was clear,
    and the two stood 6 to 25 px apart)."""
    def drifting(yy, xx):
        amp = 1 - (1 - end) * (1 - ramp(yy, *dim))
        at = 205 - shift * (1 - ramp(yy, *slide))
        return 30 + 100 * np.exp(-((xx - at) / 28.0) ** 2) * amp
    core = maps(*leg(drifting))['core']
    for y in range(60, 590, 5):
        peaks, _ = find_peaks(core[y], height=0.1, prominence=0.03)
        assert len(peaks) == 1, (y, peaks, core[y][peaks])


def test_the_floor_goes_on_along_the_stronger_of_two_painted_glints(floor_glint):
    """Two lights painted down the upper half of a dark leg, a strong one at x = 205 and a weaker at x = 130, none below:
    the floor carries on down the lower half along the stronger."""
    got = maps(*leg(upper((205, 100, 12.0), (130, 70, 12.0))))
    assert got['core'][60:240, 120:140].max() > 0.5                          # the weaker is a glint of its own
    x, bright = glint_at(got, 380, 540)
    assert (bright > 0.35).all() and np.abs(x - 205).max() <= 2


def test_the_floor_holds_its_place_across_a_bent_limb(floor_glint):
    """A glint painted 0.3 half-widths from the middle of a bent leg down its upper half, none below: the floor goes on at
    0.3 half-widths from the middle, which bends with the leg, as far as a glint's path is held to (oily.TOL_REL of the
    half-width, 5 px here)."""
    cx = lambda yy: CX + 15 * np.sin(2 * np.pi * yy / H)
    bent = lambda yy, xx: 30 + 100 * np.exp(-((xx - cx(yy) - 21) / 20.0) ** 2) * ramp(yy, 260, 330)
    x, bright = glint_at(maps(*limb(bent, lambda yy: cx(yy) - 70, lambda yy: cx(yy) + 70)), 380, 540)
    assert (bright > 0.35).all() and np.abs(x - (cx(np.arange(380, 540)) + 21)).max() <= oily.TOL_REL * 70 + 1.5


def test_a_painted_glint_too_faint_to_follow_leaves_the_floor_down_the_middle(floor_glint, monkeypatch):
    """The painted highlight at a twentieth of its strength is no glint to follow (below half of oily.FAINT): the floor
    goes down the middle; at a half it is a glint, and the floor goes along it, the middle having nothing."""
    real = oily._tracks

    def weaker(factor):
        return lambda *a, **k: [(r, u, s * factor, w, su, dl) for r, u, s, w, su, dl in real(*a, **k)]
    args = leg(lit)
    monkeypatch.setattr(oily, '_tracks', weaker(0.05))
    faint = maps(*args)['core']
    monkeypatch.setattr(oily, '_tracks', weaker(0.5))
    strong = maps(*args)['core']
    assert faint[300, CX] > 0.35 and strong[300, CX] < 0.05 and strong[300, 205] > 0.45


def test_the_floors_place_moves_smoothly_as_a_painted_glint_grows_clear(floor_glint, monkeypatch):
    """A painted highlight a hair stronger must not move the floor all at once: its place goes smoothly from the middle to
    the painted glint's as the painted one's top goes from half of oily.FAINT to FAINT, and stays there from FAINT up."""
    real = oily._tracks
    args = leg(lit)
    got = []
    tops = np.linspace(0.4 * oily.FAINT, 1.2 * oily.FAINT, 33)
    for top in tops:
        monkeypatch.setattr(oily, '_tracks', lambda *a, top=top, **k: [
            (r, u, s * top / max(float(np.max(s)), 1e-9), w, su, dl) for r, u, s, w, su, dl in real(*a, **k)])
        got.append(float(maps(*args)['core'][300].argmax()))
    got = np.array(got)
    assert abs(got[0] - CX) <= 2 and np.abs(got[tops >= oily.FAINT] - 205).max() <= 2
    assert np.diff(got).min() >= -1 and np.diff(got).max() <= 4, got


@pytest.mark.parametrize('width', [16, 18, 20, 22, 24, 30])
def test_the_floor_is_on_thin_limbs_at_any_subpixel_position(floor_glint, width):
    """A thin limb's cells are narrower than a pixel: its glint must still be found (it was lost on limbs 14-20 px wide)."""
    for phase in (0.0, 0.3, 0.6):
        got = maps(*limb(flat(30), lambda yy: CX - width / 2 + phase + 0 * yy, lambda yy: CX + width / 2 + phase + 0 * yy))
        assert got['core'][150:450].max(1).min() > 0.3, (width, phase)


def test_the_floor_is_weaker_on_a_limb_too_thin_to_trust_the_outline_of(floor_glint):
    """Half-widths under oily.HALF_ZONE[1] get the zones, and the glint, only in part: 14 px across (7 to a side) is
    there, but weaker than on a limb of 16."""
    def strength(width):
        return float(maps(*limb(flat(30), lambda yy: CX - width / 2 + 0 * yy, lambda yy: CX + width / 2 + 0 * yy))['core'][300].max())
    assert 0.1 < strength(14) < strength(16) - 0.05


def test_no_floor_on_a_pale_limb(floor_glint):
    assert maps(*leg(flat(235)))['core'].max() < 0.05
    assert maps(*leg(upper((205, 60, 28.0), grey=225.0)))['core'][380:540].max() < 0.05


def test_no_floor_where_the_outline_is_out_of_sight_or_the_piece_is_too_short(floor_glint):
    for args in (limb(flat(30), lambda yy: -50 + 0 * yy, lambda yy: 260 + 0 * yy),             # cut by the frame all down one side
                 limb(flat(30), lambda yy: -50 + 0 * yy, lambda yy: 420 + 0 * yy),             # wider than the picture
                 limb(flat(30), lambda yy: CX - 3 + 0 * yy, lambda yy: CX + 3 + 0 * yy),       # a sliver
                 leg(flat(30), top=520)):                                                      # 80 rows of a leg 160 across: a foot
        assert maps(*args)['core'].max() < 0.05


def test_a_stretch_is_a_limb_from_oily_MIN_LENGTH_widths_long(floor_glint):
    """A leg 160 px across: no floor on 1.4 widths of it (a dome, a foot), one on 1.6."""
    short, long_ = int(1.4 * (X1 - X0)), int(1.6 * (X1 - X0))
    assert maps(*leg(flat(30), top=H - short))['core'].max() < 0.05
    assert maps(*leg(flat(30), top=H - long_))['core'].max() > 0.3


def test_the_floor_follows_a_bent_limbs_own_middle(floor_glint):
    """As far as a glint's path is held to (oily.TOL_REL of the half-width, 5 px here)."""
    cx = lambda yy: CX + 15 * np.sin(2 * np.pi * yy / H)
    x, bright = glint_at(maps(*limb(flat(30), lambda yy: cx(yy) - 70, lambda yy: cx(yy) + 70)))
    assert (bright > 0.25).all() and np.abs(x - cx(np.arange(60, 540))).max() <= oily.TOL_REL * 70 + 1.5


def test_the_floor_is_as_strong_as_the_zones_are_believed(floor_glint):
    """Down a leg whose left side runs off the image from row 300 on the zones are half believed, and so is the floor."""
    left = lambda yy: np.where(yy < 300, 60, -40)
    x, bright = glint_at(maps(*limb(flat(30), left, lambda yy: 260 + 0 * yy)))
    assert bright[20:100].mean() > 0.35 and 0.15 < bright[340:480].mean() < 0.25


def test_a_wall_leaves_no_seam_in_the_floor(floor_glint):
    """A wall across a dark leg splits it into two pieces, each long enough for a floor of its own: the glint is as strong
    along the wall's own band, which takes its maps from the stocking beside it, as anywhere."""
    src, R, alpha, A, V, REG = leg(flat(30))
    cut = np.zeros((H, W), bool)
    cut[296:304, X0:X1] = True
    core = oily.oily_maps(src, R, alpha, A, V, 0.64, cut=cut, REG=REG)[1]
    assert core[:, CX].min() > 0.35


def cut_out(args, gap):
    """leg()'s arguments with `gap` (a bool mask) left out of the painted region too, as a selection leaves out a ribbon or
    strands of hair, and the connectors the solver fills the gap with, {1: the gap} (V and A as the scene has them: none
    there): (what maps() takes, fill)."""
    src, R, alpha, A, V, REG = args
    gap = gap & (REG > 0)
    return (src, np.where(gap, 0, R).astype(np.int8), np.where(gap, 0, alpha).astype(np.float32), np.where(gap, 0, A),
            np.where(gap, 0, V), np.where(gap, 0, REG).astype(np.int8)), {1: gap}


YY, XX = np.mgrid[0:H, 0:W]


def same(a, b):
    return all(np.array_equal(a[key], b[key]) for key in a)


def test_a_limb_a_ribbon_cuts_in_two_is_one_limb_and_its_glint_goes_on_across_it(floor_glint):
    """A ribbon across a leg that the selection leaves out (rows 420 to 440; below it 160 rows, a foot, too short to be a limb
    alone): with what the solver filled in the glint goes on down the foot along the leg's, at the floor's strength, and
    nothing is drawn on the ribbon; without it the foot has none."""
    args, fill = cut_out(leg(upper((205, 100, 28.0))), (YY >= 420) & (YY < 440))
    got, alone = maps(*args, fill=fill), maps(*args)
    above, below = glint_at(got, 340, 415), glint_at(got, 450, 590)
    assert (above[1] > 0.35).all() and (below[1] > 0.35).all() and np.abs(above[0] - 205).max() <= 2 and np.abs(below[0] - 205).max() <= 2
    assert alone['core'][450:590].max() < 0.05
    assert all(v[420:440].max() == 0 for v in got.values())


def test_a_ribbon_over_a_lit_leg_leaves_the_glints_as_painted(floor_glint):
    """A ribbon across a leg with a highlight painted down it (rows 420 to 440): the pieces are one limb for how far it
    runs and where the glint goes on, but the glints they show are their own, as painted: above the ribbon every map is as
    it is without the fill (a light fit and the range of a piece's lighting are the piece's: pieces joined into one
    lost the calf's glint of a real picture to the brighter foot beyond a strap)."""
    args, fill = cut_out(leg(lit), (YY >= 420) & (YY < 440))
    got, alone = maps(*args, fill=fill), maps(*args)
    assert all(np.array_equal(got[key][:420], alone[key][:420]) for key in got)
    above, below = glint_at(got, 60, 410), glint_at(got, 450, 590)
    assert (above[1] > 0.7).all() and (below[1] > 0.7).all() and np.abs(above[0] - 204).max() <= 2 and np.abs(below[0] - 204).max() <= 2


def test_pieces_of_a_pale_limb_are_as_painted_with_or_without_the_fill():
    """A pale leg with a brighter foot beyond a ribbon (no floor on a pale stocking): nothing changes at all."""
    args, fill = cut_out(leg(lambda yy, xx: 180 + 40 * np.exp(-((xx - 205) / 28.0) ** 2) + 30 * (yy > 440)), (YY >= 420) & (YY < 440))
    assert same(maps(*args), maps(*args, fill=fill))


def test_a_limb_in_pieces_runs_as_far_as_all_of_them(floor_glint):
    """A leg of 400 rows (2.5 widths) with a band of hair across it (rows 380 to 400): each piece alone, 180 and 200 rows,
    is too short to be a limb (a dome, a foot), the limb as a whole is not."""
    args, fill = cut_out(leg(flat(30), top=200), (YY >= 380) & (YY < 400))
    alone, joined = maps(*args), maps(*args, fill=fill)
    assert alone['core'].max() < 0.05
    assert (joined['core'][210:370, CX - 1:CX + 2].max(1) > 0.35).all() and (joined['core'][410:590, CX - 1:CX + 2].max(1) > 0.35).all()


def test_a_piece_with_no_glint_of_its_own_takes_the_place_from_the_nearer_end_of_the_limbs(floor_glint):
    """A band of hair across the top of a leg (rows 100 to 120) whose biggest piece, the one below, has a glint painted along
    x = 150: the small piece above, with none of its own, goes on with it, at the same place."""
    shade = lambda yy, xx: 30 + 100 * np.exp(-((xx - 150) / 28.0) ** 2) * (yy >= 120)
    args, fill = cut_out(leg(shade), (YY >= 100) & (YY < 120))
    above = glint_at(maps(*args, fill=fill), 10, 95)
    assert (above[1] > 0.35).all() and np.abs(above[0] - 150).max() <= 2
    assert maps(*args)['core'][10:95].max() < 0.05


def test_the_pieces_of_a_limb_beside_its_biggest_take_the_place_of_its_glint_at_their_own_end(floor_glint):
    """A glint painted down the middle piece of a leg (rows 120 to 440) that moves from x = 150 at its top to x = 210 at its
    bottom, bands of hair above and below it (rows 100-120, 440-460), small pieces of the leg beyond them with none of
    their own: the piece above goes on at the place the glint has at its top, the piece below at the place it has at its
    bottom."""
    def moving(yy, xx):
        return 30 + 100 * np.exp(-((xx - (150 + 60 * (yy - 120) / 320.0)) / 28.0) ** 2) * ((yy >= 120) & (yy < 440))
    args, fill = cut_out(leg(moving), ((YY >= 100) & (YY < 120)) | ((YY >= 440) & (YY < 460)))
    got = maps(*args, fill=fill)
    above, below = glint_at(got, 10, 95), glint_at(got, 470, 590)
    assert (above[1] > 0.35).all() and (below[1] > 0.35).all()
    assert np.abs(above[0] - 150).max() <= 6 and np.abs(below[0] - 210).max() <= 6, (above[0][[0, -1]], below[0][[0, -1]])


@pytest.mark.parametrize('slope, y0, rows', [(0.4375, 380, (490, 590)), (1.0, 330, (540, 590))])
def test_a_band_across_a_limb_at_a_slant_joins_it_too(floor_glint, slope, y0, rows):
    """A band of hair across the leg at a slant (rows 380 to 400 at its left, 450 to 470 at its right; or at 45 degrees, from
    330 to 490, where the pieces' V ranges overlap by 0.6 of the shorter's): the glint goes on down the foot along the leg's,
    even where only part of the foot's cross-section is in sight (its edge there is the band's, no outline), a little less
    strong where the outline is not seen whole."""
    args, fill = cut_out(leg(upper((205, 100, 28.0))), (YY >= y0 + (XX - X0) * slope) & (YY < y0 + 20 + (XX - X0) * slope))
    x, bright = glint_at(maps(*args, fill=fill), *rows)
    assert (bright[:40] > 0.25).all() and (bright[40:] > 0.35).all() and np.abs(x - 205).max() <= 2


@pytest.mark.parametrize('slope, y0', [(0.4375, 380), (-0.4375, 450), (1.0, 330)])
def test_a_cut_across_a_limb_at_a_slant_leaves_its_middle_where_it_is(floor_glint, slope, y0):
    """A band of hair across a blank dark leg at a slant (20 px thick, 24 degrees one way and the other, and 45): near the
    cut each course is only partly in sight, and the edge there is the band's, no outline of the limb, so the limb's middle
    is where it is. Down to the cut, on both sides, the glint is down the middle (it was dragged up to 70 px toward the side
    that is in sight), the leg is no darker toward the cut (the cut an outline darkened it), and the glint still shows."""
    cut = (YY >= y0 + (XX - X0) * slope) & (YY < y0 + 20 + (XX - X0) * slope)
    args, fill = cut_out(leg(flat(30)), cut)
    got = maps(*args, fill=fill)
    mid = int(y0 + (CX - X0) * slope + 10)
    for rows in ((60, mid - 14), (mid + 14, 590)):
        x, bright = glint_at(got, *rows)
        assert np.abs(x - CX).max() <= 3 and bright.min() > 0.15, rows
    side = slice(CX - 45, CX - 35)                                  # u = -0.5, where the leg is whole in sight
    seen = (args[1][:, side] > 0).all(1)
    facing = got['facing'][:, side].mean(1)[seen]
    assert facing.min() > 0.83 and facing.max() < 0.89, (facing.min(), facing.max())


def test_a_limb_whose_biggest_piece_has_no_glint_goes_on_with_the_painted_glint_of_a_smaller(floor_glint):
    """A band of hair across a blank leg (rows 400 to 420) with the only painted glint, along x = 205, on the small piece
    below it: the big piece above goes on with it, not down its own middle (x = 179: the two lines across the band would be
    misaligned, as when the biggest piece was the one every other took its place from)."""
    shade = lambda yy, xx: 30 + 100 * np.exp(-((xx - 205) / 28.0) ** 2) * (yy >= 420)
    args, fill = cut_out(leg(shade), (YY >= 400) & (YY < 420))
    x, bright = glint_at(maps(*args, fill=fill), 20, 380)
    assert (bright > 0.35).all() and np.abs(x - 205).max() <= 2


def test_a_piece_goes_on_with_the_nearest_painted_piece_of_its_limb_not_the_biggest(floor_glint):
    """A leg in three pieces (bands across it at rows 260-280 and 420-440): a thigh, the biggest, painted along x = 205, a calf
    painted along x = 150, and a foot with none: the foot goes on with the calf's, the piece beside it."""
    def chain(yy, xx):
        return (30 + 100 * np.exp(-((xx - 205) / 28.0) ** 2) * (yy < 260)
                + 100 * np.exp(-((xx - 150) / 28.0) ** 2) * ((yy >= 280) & (yy < 420)))
    args, fill = cut_out(leg(chain), ((YY >= 260) & (YY < 280)) | ((YY >= 420) & (YY < 440)))
    got = maps(*args, fill=fill)
    foot = glint_at(got, 450, 590)
    assert (glint_at(got, 290, 410)[1] > 0.9).all() and np.abs(glint_at(got, 290, 410)[0] - 150).max() <= 2
    assert (foot[1] > 0.35).all() and np.abs(foot[0] - 150).max() <= 2


def test_a_faint_glint_painted_on_a_piece_goes_on_where_the_limbs_other_piece_has_its_glint(floor_glint):
    """A band of hair across a leg (rows 400 to 420): a strong glint along x = 205 above it, and below it only a faint one
    along the same place (10 grey levels over the leg's 30): the foot's line is along x = 205 too, not down its own
    middle (x = 180: the faint glint's own place counted for the share of it that it is clear, and the rest went to the
    middle instead of to the place the other piece has)."""
    shade = lambda yy, xx: 30 + 100 * np.exp(-((xx - 205) / 28.0) ** 2) * (yy < 400) + 10 * np.exp(-((xx - 205) / 28.0) ** 2) * (yy >= 420)
    args, fill = cut_out(leg(shade), (YY >= 400) & (YY < 420))
    got = maps(*args, fill=fill)
    for rows in ((60, 395), (430, 590)):
        x, bright = glint_at(got, *rows)
        assert (bright > 0.35).all() and np.abs(x - 205).max() <= 2, rows


def test_a_faint_piece_between_a_strong_one_and_a_blank_one_does_not_take_the_blank_ones_place_away(floor_glint):
    """A leg in three pieces (bands at rows 260-280 and 420-440): a thigh painted strongly along x = 205, a calf with only a
    faint glint along the same place, a foot with none: the foot goes on at x = 205 (the calf's glint, barely there, only
    hints at the place, and was scaled toward the middle as if it were the whole of it, which the thigh's clear glint
    beyond it then had no say about)."""
    shade = lambda yy, xx: (30 + 100 * np.exp(-((xx - 205) / 28.0) ** 2) * (yy < 260)
                            + 10 * np.exp(-((xx - 205) / 28.0) ** 2) * ((yy >= 280) & (yy < 420)))
    args, fill = cut_out(leg(shade), ((YY >= 260) & (YY < 280)) | ((YY >= 420) & (YY < 440)))
    got = maps(*args, fill=fill)
    for rows in ((290, 410), (450, 590)):
        x, bright = glint_at(got, *rows)
        assert (bright > 0.35).all() and np.abs(x - 205).max() <= 2, rows


@pytest.mark.parametrize('height', [140, 40, 14, 6, 4])
def test_a_blank_piece_between_two_painted_ones_joins_the_glint_at_both_seams(floor_glint, height):
    """A leg in three pieces (bands of hair 20 px across, above and below the middle piece): a thigh painted along x = 205,
    a foot painted along x = 150 and a piece between them with none, 140, 40, 14, 6 or 4 px tall (the last three are one row
    of the lighting fit: slivers): its line runs from where the thigh's is at the first row of pixels of the piece to where
    the foot's is at its last, to within 2 px (the fit's last row is a short one, a sliver has one row, a strip of 4 rows
    holds a pixel row to a third: the places are by the piece's actual extent, each at the mean of the pixels its row of
    the line takes, and a sliver's line is a run across it, not a blob in its middle), at the floor's strength all along, so
    that there is no jump at either band (it held the one place all down it, 55 px off the other)."""
    y0, y1 = 300, 300 + height
    shade = lambda yy, xx: (30 + 100 * np.exp(-((xx - 205) / 28.0) ** 2) * (yy < y0 - 20)
                            + 100 * np.exp(-((xx - 150) / 28.0) ** 2) * (yy >= y1 + 20))
    args, fill = cut_out(leg(shade), ((YY >= y0 - 20) & (YY < y0)) | ((YY >= y1) & (YY < y1 + 20)))
    x, bright = glint_at(maps(*args, fill=fill), y0, y1)
    assert (bright > 0.35).all()
    assert abs(x[0] - 205) <= 2 and abs(x[-1] - 150) <= 2 and (np.diff(x) <= 1).all(), (x[0], x[-1])     # a run down, one way
    if height > 30:
        assert np.abs(x - np.linspace(205, 150, len(x))).max() <= 5                                       # straight


def test_a_leg_cut_by_the_image_edge_with_a_ribbon_across_it_is_measured_as_without_the_fill(floor_glint):
    """A leg whose left side is the image's edge (x 0 to 259: no cross-section is seen whole, in the plain frame or in the one
    with the ribbon's edges out of sight) with a ribbon across it: with the fill, the pieces are one limb for how far it runs
    and where its glint goes on, and the frame with the connectors' edges out of sight is not taken (it would turn the
    right edge, an outline in sight, into one out of sight beside the ribbon: facing there 0.18 to 1.0, a pale cap): tone,
    facing and zone are as without the fill, everywhere."""
    m = XX < 260
    src = np.full((H, W, 3), 250, np.uint8)
    src[m] = 60
    R = m.astype(np.int8)
    args, fill = cut_out((src, R, R.astype(np.float32), np.where(m, 180.0 - XX, 0.0), np.where(m, YY, 0.0).astype(np.float64), R.copy()),
                         (YY >= 300) & (YY < 320) & m)
    with_fill, without = maps(*args, fill=fill), maps(*args)
    for key in ('tone', 'facing', 'zone'):
        assert np.array_equal(with_fill[key], without[key]), key
    assert with_fill['facing'][298, 250] < 0.3


def test_a_notch_in_the_outline_beside_a_ribbon_is_still_no_hidden_edge(floor_glint):
    """A ribbon across a leg and, elsewhere, a bite out of its edge (40 px deep, 50 high) that the solver fills in as well:
    only what joins the two pieces is no outline. The notch's fill changes nothing, as without the ribbon: the facing and
    the zones beside the bite, and the glints, are as they are with the ribbon's fill alone."""
    shade = upper((205, 100, 28.0))
    notch = (XX < X0 + 40) & (YY >= 200) & (YY < 250)
    ribbon = (YY >= 420) & (YY < 440)
    args, both = cut_out(leg(shade), ribbon | notch | (XX < X0))
    with_notch = maps(*args, fill=both)
    ribbon_only = maps(*args, fill={1: both[1] & ribbon})
    assert same(with_notch, ribbon_only)
    assert with_notch['facing'][225, X0 + 41] < 0.6 and with_notch['zone'][225, X0 + 41] > 0.95           # an outline, in full


def test_a_notch_in_the_outline_that_touches_the_ribbons_fill_is_one_component_with_it_a_known_limit(floor_glint):
    """KNOWN LIMIT. A bite out of the edge (40 px deep) right above a ribbon, closed by the solver in one with the ribbon's
    fill (one connected component: nothing in the mask says the bite from a hair strand beside the ribbon, which the limb goes
    on behind): the bite's edge is taken for out of sight with the ribbon's, as all of the component is, and the glint and the
    facing near it are those of a limb whose edge is hidden there (as much as 20 px off, up to 90 px above the ribbon). Not
    promised, and not pinned here. What is: no crash, nothing out of range, nothing drawn off the painted pixels, and the piece
    on the other side of the ribbon, which the bite is not part of, is on the glint of the piece above."""
    shade = upper((205, 100, 28.0))
    notch = (XX < X0 + 40) & (YY >= 380) & (YY < 420)
    ribbon = (YY >= 420) & (YY < 440)
    args, fill = cut_out(leg(shade), ribbon | notch | (XX < X0))
    got = maps(*args, fill=fill)
    assert all(np.isfinite(v).all() and v.min() >= -1 and v.max() <= 1 for v in got.values())
    assert not any(got[k][args[1] == 0].any() for k in ('core', 'band', 'tail', 'centre'))
    x, bright = glint_at(got, 450, 590)
    assert np.abs(x - 205).max() <= 3 and bright.min() > 0.2


@pytest.mark.parametrize('tip', [4, 8])
def test_a_few_whole_narrow_rows_do_not_cost_a_piece_its_painted_glint(floor_glint, tip):
    """Below a ribbon, a leg cut along its left by a strand of hair (the fill carries the strand and the ribbon: the pieces'
    edges there run on out of sight), a strong highlight painted along x = 220 on the piece to its right, whose only rows
    that are not beside such an edge are a toe 8 px wide at its bottom (4 or 8 rows): the typical width of the piece is
    that of the strip beside the strand, 40 px to a side, not of the toe (3.5: the lighting then had cells 0.2 px wide and
    found no glint at all)."""
    shade = lambda yy, xx: 30 + 100 * np.exp(-((xx - 220) / 18.0) ** 2) * (yy >= 280)
    ribbon = (YY >= 260) & (YY < 280)
    strand = (XX >= 120) & (XX < 180) & (YY >= 280)
    outside = (YY >= 600 - tip) & ((XX < 228) | (XX >= 236))
    args, _ = cut_out(leg(shade), ribbon | strand | outside)
    core = maps(*args, fill={1: (ribbon | strand) & (args[5] == 0)})['core'][350:500, 180:260]
    assert core.max(1).min() > 0.8 and np.abs(core.argmax(1) + 180 - 220).max() <= 2


@pytest.mark.parametrize('rows', [3, 4, 5, 6, 7, 8, 9, 14, 20])
def test_a_strip_between_two_ribbons_has_its_glint_too(floor_glint, rows):
    """A blank dark leg with two ribbons across it, 3 to 20 rows apart: the strip of leg between them is too short for a
    cross-section to be seen whole once what the ribbons hide is taken out of sight (or, at 5 or 6 rows, three bands of V of
    which one is whole, whose trust is smoothed away to nothing, and no floor with it), and is measured as it was before
    that; it has the line along the middle like the pieces beside it, across the whole strip, from its first row of pixels to
    its last at the floor's strength (a strip of one row of the lighting fit had a blob in its middle, and none at its ends)."""
    args, fill = cut_out(leg(flat(30)), ((YY >= 420) & (YY < 440)) | ((YY >= 440 + rows) & (YY < 460 + rows)))
    core = maps(*args, fill=fill)['core']
    assert core[440:440 + rows, CX - 2:CX + 3].max(1).min() > 0.35 and core[300:415].max() > 0.35 and core[480 + rows:590].max() > 0.35


@pytest.mark.parametrize('amplitude', [0, 9, 10, 40, 100])
def test_a_sliver_between_two_ribbons_has_its_line_across_it_whatever_the_art_paints_in_it(floor_glint, amplitude):
    """A strip 20 px tall (one row of the lighting fit) between two ribbons, all glints along x = 205: with nothing painted in
    it, with a barely detectable glint (9 and 10 grey levels over the leg's 30: a track of one row, 0.03 to 0.08 of the
    lighting's top, which was enough to make a point of its line: core 0.06 at its first and last row, the floor's 0.4 only in
    the middle), and with a strong one: the line runs across the whole strip, from its first row of pixels to its last, at
    the floor's strength or the painted glint's."""
    shade = lambda yy, xx: (30 + 100 * np.exp(-((xx - 205) / 28.0) ** 2) * ((yy < 260) | (yy >= 320))
                            + amplitude * np.exp(-((xx - 205) / 28.0) ** 2) * ((yy >= 280) & (yy < 300)))
    args, fill = cut_out(leg(shade), ((YY >= 260) & (YY < 280)) | ((YY >= 300) & (YY < 320)))
    x, bright = glint_at(maps(*args, fill=fill), 280, 300)
    assert (bright >= (0.99 if amplitude >= 40 else 0.39)).all() and np.abs(x - 205).max() <= 1, (bright.min(), x)


def test_a_painted_glint_stronger_than_the_floor_stays_where_it_is_painted_with_the_floor_on(floor_glint, monkeypatch):
    """A curved highlight that fades out between rows 250 and 350 (x = 185 + 25 sin(y / 160)): where it is strong its core
    is as it is without the floor to within 0.05 (a ridge shift of a px at most: the path of a painted glint is smoothed
    as it was, the floor's rows past its end weigh next to nothing, and the rows it lifts keep the weight they had; its
    smoothing used to move the ridge by 2 px, the core by 0.12 and more on real pictures)."""
    def curved(yy, xx):
        return 30 + 100 * np.exp(-((xx - (185 + 25 * np.sin(yy / 160.0))) / 28.0) ** 2) * ramp(yy, 250, 350)
    args = leg(curved)
    on = maps(*args)
    monkeypatch.setattr(oily, 'FLOOR_GLINT', 0.0)
    off = maps(*args)
    strong = off['core'] >= 0.6
    assert strong.sum() > 1000 and np.abs(on['core'] - off['core'])[strong].max() < 0.08
    assert np.abs(on['core'].argmax(1)[:240] - off['core'].argmax(1)[:240]).max() <= 1


def test_pieces_side_by_side_stay_as_painted(floor_glint):
    """What nothing says from each other stays as it is without the fill: two limbs of one region (110 px across, 40 apart),
    two of unequal widths (150 and 70, 20 apart), two staggered along the limb (one above the other, but side by side
    across it), and a strand of hair down the whole of a leg. The bigger of two has a glint painted off its middle: the
    other's glint is down its own middle, not along that."""
    def two(x0, x1, x2, x3, glint, top=0, bottom=H):
        m = (((XX >= x0) & (XX < x1) & (YY < bottom)) | ((XX >= x2) & (XX < x3) & (YY >= top)))
        src = np.full((H, W, 3), 250, np.uint8)
        src[m] = np.clip(30 + 100 * np.exp(-((XX - glint) / 12.0) ** 2), 0, 255)[m][:, None]
        R = m.astype(np.int8)
        return (src, R, R.astype(np.float32), np.where(m, 170.0 - XX, 0.0), np.where(m, YY, 0.0).astype(np.float64), R.copy()), \
            {1: (XX >= x1) & (XX < x2) & (YY >= top - 40) & (YY < bottom + 40)}
    cases = [(two(40, 150, 190, 300, 70), ((40, 150, 70, 100, 500), (190, 300, 245, 100, 500))),
             (two(40, 190, 210, 280, 80), ((40, 190, 80, 100, 500), (210, 280, 245, 100, 500))),
             (two(40, 150, 190, 300, 70, top=320, bottom=300), ((40, 150, 70, 40, 260), (190, 300, 245, 360, 560)))]
    for (args, fill), glints in cases:
        got = maps(*args, fill=fill)
        assert same(got, maps(*args))
        for lo, hi, middle, y0, y1 in glints:
            x = got['core'][y0:y1, lo:hi].argmax(1) + lo
            assert np.abs(x - middle).max() <= 2 and got['core'][y0:y1, lo:hi].max(1).min() > 0.35, (lo, hi)
    args, fill = cut_out(leg(flat(30)), (XX >= 130) & (XX < 146))
    assert same(maps(*args, fill=fill), maps(*args))


def test_an_outline_notch_the_fill_closes_changes_nothing(floor_glint):
    """A bite out of the leg's edge (40 px deep, 50 high), which the solver's closing fills: the piece is one as it was, what
    is filled in is no outline and no stocking, so every map is as it is without the fill."""
    args, fill = cut_out(leg(upper((205, 100, 28.0))), (XX < X0 + 40) & (YY >= 250) & (YY < 300) | (XX < X0))
    assert same(maps(*args, fill=fill), maps(*args))


def test_the_filled_in_pixels_show_nothing_and_no_fill_changes_nothing(floor_glint):
    args, fill = cut_out(leg(upper((205, 100, 28.0))), (YY >= 420) & (YY < 440))
    got = maps(*args, fill=fill)
    assert all(v[fill[1]].max() == 0 for v in got.values())
    assert same(maps(*args), maps(*args, fill={})) and same(maps(*args), maps(*args, fill={1: np.zeros((H, W), bool)}))


def middle_at(nr, cell=40):
    """oily_maps' middle for a fit of nr rows and CELL's cells: a limb 20 cells to a side of its middle at this cell."""
    return np.tile((CELL - cell) / 20, (nr, 1))


def crisp(cell, height=0.15):
    return 0.02 + height * np.exp(-((CELL - cell) / 2.0) ** 2)


def places(tracks):
    """The place (cells) of each track's glint, left to right (a track that does not move: its first place)."""
    return [round(float(u[1]), 1) for _, u, *_ in sorted(tracks, key=lambda t: t[1][1])]


def test_a_glint_on_a_flat_top_goes_to_the_most_central_place_level_with_its_top():
    """The same flat-topped light all down the limb, a faint ledge in the middle (cell 40) and a bump 10 cells beside it
    that is higher by a hair (0.026, within oily.LEVEL): the light's highest point is the bump, and the glint ends up
    on the ledge, still one glint and as strong as it was."""
    rows = [flat_top((40, 0.004), (50, 0.030))] * 30
    free, kept = follow(rows), follow(rows, middle=middle_at(30))
    assert spans(free) == spans(kept) == [(0, 29)]
    assert np.allclose(free[0][1][1:-1], 50.5, atol=0.05) and np.allclose(kept[0][1][1:-1], 40.5, atol=0.05)
    np.testing.assert_allclose(kept[0][2], free[0][2])


def test_central_is_to_the_limbs_middle_not_to_the_cells():
    """The same light on limbs whose middle is in different places: the glint goes to whichever of the two bumps is nearer
    its middle, and stays on the one that is the middle."""
    rows = [flat_top((32, 0.004), (48, 0.030))] * 30
    assert places(follow(rows, middle=middle_at(30, 30))) == [32.5]
    assert places(follow(rows, middle=middle_at(30, 50))) == [48.5]


def test_a_top_standing_clear_of_the_middle_stays_where_the_light_puts_it():
    rows = [flat_top((40, 0.004), (50, 0.200))] * 30                        # the bump 0.196 above the ledge
    kept = follow(rows, middle=middle_at(30))
    assert spans(kept) == [(0, 29)] and np.allclose(kept[0][1][1:-1], 50.5)


def test_two_ridges_with_a_valley_between_are_not_one_top():
    """Two crisp lights, the one off the middle a little higher than the one in it but the light falling away far between
    them: two glints, each where its light is. A place level with a glint's top is one on the same top."""
    rows = [0.02 + 0.14 * np.exp(-((CELL - 40) / 2.0) ** 2) + 0.16 * np.exp(-((CELL - 56) / 2.0) ** 2)] * 30
    assert places(follow(rows, middle=middle_at(30))) == [40.5, 56.5]


def test_two_faint_lights_a_valley_apart_are_two_not_one_top():
    """A faint light in the middle (0.035, no glint of its own) and a stronger one off it (0.078), within oily.LEVEL of
    each other but each standing clear of the flat ground between them: that valley is deeper than oily.RIDGE, so the
    middle's light is no ledge on the other's top and the glint stays on the stronger one (on a leg of low contrast,
    where the whole light is a few grey levels, a dip allowed by its size alone let it be moved onto the faint one)."""
    bump = lambda cell, height: height * np.exp(-((CELL - cell) / 3.0) ** 2)
    rows = [bump(40, 0.035) + bump(58, 0.078)] * 30
    free, kept = follow(rows), follow(rows, middle=middle_at(30))
    assert len(free) == len(kept) == 1 and places(kept) == places(free)
    assert all(np.array_equal(a, b) for a, b in zip(free[0], kept[0]))


def test_two_faint_lights_a_valley_apart_keep_the_glint_on_the_stronger_through_the_whole_pipeline():
    """The same on a painted leg (grey 70, lights of 10 and 20 grey levels, 48 px apart), through oily_maps."""
    shade = lambda yy, xx: 70 + 10 * np.exp(-((xx - 180) / 10) ** 2) + 20 * np.exp(-((xx - 228) / 10) ** 2)
    x, bright = glint_at(maps(*leg(shade)))
    assert (bright > 0.5).all() and np.abs(x - 228).max() <= 3


def test_a_higher_place_is_not_level_with_the_top_either(monkeypatch):
    """A glint on a lobe of 0.30 and, nearer the middle, a shelf of 0.404 that makes no glint of its own (it hardly
    stands off the edge of the stretch) with a dip of 0.04 between: not a place for the glint. The dip alone rules it
    out; and, with the dip rule off, so does the shelf's height, 0.104 above the top (oily.LEVEL is a distance either
    way: it used to hold only for places below the top)."""
    rows = [np.interp(CELL, [0, 14, 18, 30, 34, 56, 79], [0.40, 0.404, 0.26, 0.26, 0.30, 0.0, -0.2])] * 30
    around = middle_at(30, 14)
    free = places(follow(rows))
    assert len(free) == 1 and abs(free[0] - 34.5) < 0.5
    assert places(follow(rows, middle=around)) == free
    monkeypatch.setattr(oily, 'RIDGE', 1.0)
    assert places(follow(rows, middle=around)) == free


def test_a_glint_never_moves_onto_another_glints_place():
    """Two glints, a bump each side of a faint ledge in the middle: the ledge is as good a place for either, and only
    one goes to it. The other stays on its bump: not one glint drawn twice."""
    rows = [flat_top((25, 0.050), (40, 0.004), (55, 0.050))] * 30
    free, kept = follow(rows), follow(rows, middle=middle_at(30))
    assert len(free) == len(kept) == 2
    moved, stayed = sorted(places(kept), key=lambda p: abs(p - 40.5))
    assert abs(moved - 40.5) < 0.3 and stayed in places(free)


def spike(cell, height):
    """One cell a little brighter than its neighbours: a place for a glint that the fit's smoothing would not merge into
    a bump beside it."""
    return height * (CELL == cell)


def test_a_glint_central_enough_is_not_chased_to_the_exact_middle():
    """A bump 0.3 half-widths from the middle, higher than a ledge on the middle by a hair: that is central enough, the
    glint stays on the bump."""
    rows = [flat_top() + spike(40, 0.004) + spike(46, 0.030)] * 30
    assert places(follow(rows, middle=middle_at(30))) == [46.5]


def test_a_place_hardly_nearer_the_middle_is_not_worth_moving_to():
    """The ledge is only 0.15 half-widths nearer the middle than the bump (it must be oily.NEARER, 0.2, to move for it):
    the glint stays on the bump."""
    rows = [flat_top() + spike(48, 0.004) + spike(51, 0.030)] * 30
    assert places(follow(rows, middle=middle_at(30))) == [51.5]


def test_a_glint_with_no_better_place_is_exactly_as_it_was():
    for cell in (46, 56):                                                   # near the middle, and far from it with no other place
        rows = [crisp(cell)] * 30
        free, kept = follow(rows), follow(rows, middle=middle_at(30))
        assert len(free) == len(kept) == 1 and all(np.array_equal(a, b) for a, b in zip(free[0], kept[0]))


def test_a_glint_moves_only_along_a_path_it_could_take():
    """The ledge is there for the first ten rows only. To be on it there and on the bump after, the glint would have to
    jump 10 cells in a row, which a glint cannot: it stays on the bump all the way, with no kink."""
    rows = [flat_top((40, 0.004), (50, 0.030))] * 10 + [flat_top((50, 0.030))] * 10
    kept = follow(rows, middle=middle_at(20))
    u = kept[0][1][1:-1]
    assert spans(kept) == [(0, 19)] and np.allclose(u, 50.5)
    assert np.abs(np.diff(u)).max() <= oily.LINK * oily.CELLS


def row_strengths(tracks, nr):
    """The strength of the glints in each row of the fit (the largest, where there are several)."""
    st = np.zeros(nr)
    for rows, _, s, *_ in tracks:
        r = rows[1:-1].astype(int)
        st[r] = np.maximum(st[r], s[1:-1])
    return st


def test_a_moved_glint_is_as_bright_as_it_was_whatever_the_support_of_its_new_place():
    """For ten rows the painted light is dimmer along the glint and the ledge it goes to is thinly supported by the fit
    (under oily.SURE, as the stocking is bridged there): the glint's brightness is still read from the rows it was read
    from, so its strength is exactly what it was, dimmer in those rows (a moved glint took its new place's support, left
    those rows out and came out at full strength there: 0.64 became 1.0)."""
    nr = 30
    fit = np.array([flat_top((40, 0.004), (50, 0.030))] * nr)
    fit = fit - fit.mean(1, keepdims=True)
    absolute = 0.3 + fit
    absolute[10:20] -= 0.04
    den = np.ones_like(fit)
    den[10:20, 36:45] = 0.2
    free = oily._tracks(fit, absolute, den, 0.001, 8)
    kept = oily._tracks(fit, absolute, den, 0.001, 8, middle_at(nr))
    assert np.allclose(free[0][1][1:-1], 50.5, atol=0.05) and np.allclose(kept[0][1][1:-1], 40.5, atol=0.05)
    np.testing.assert_allclose(row_strengths(kept, nr), row_strengths(free, nr), atol=1e-9)
    assert row_strengths(kept, nr)[15] < 0.9 * row_strengths(kept, nr)[3]


def test_a_glint_that_went_on_unseen_is_left_as_it_was():
    """Its place hidden for six rows (a hand across the bump) while the middle is in plain view there and the light flat:
    the glint went on unseen where it was. Moved onto the middle it would be drawn through six rows of plain view that
    have no peak in them, so it stays where it was, the whole track."""
    nr = 30
    rows = [flat_top((40, 0.004), (50, 0.030)) for _ in range(nr)]
    for q in range(10, 16):
        rows[q] = flat_top()
    fit = np.array(rows)
    fit = fit - fit.mean(1, keepdims=True)
    den = np.ones_like(fit)
    den[10:16, 45:57] = 0.0
    free = oily._tracks(fit, 0.3 + fit, den, 0.001, 8)
    kept = oily._tracks(fit, 0.3 + fit, den, 0.001, 8, middle_at(nr))
    assert spans(free) == spans(kept) == [(0, 29)] and np.allclose(free[0][1][1:-1], 50.5, atol=0.05)
    assert all(np.array_equal(a, b) for a, b in zip(free[0], kept[0]))


def test_a_glint_hidden_for_a_stretch_of_the_leg_is_drawn_as_it_was(monkeypatch):
    """A dress over the right side of the leg for 140 px, the glint's bump under it and the middle in plain view: the
    glint went on unseen there. Its curve is smoothed with the rows either side, so moving those rows' glint to the middle
    would bend it into view through the rows it was hidden in: it is left as the light puts it, and the maps (the drawn
    curve and all) are those without centring."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    args = leg(flat_lit(), hole=(yy >= 200) & (yy < 340) & (xx >= 196))
    centred = maps(*args)
    monkeypatch.setattr(oily, '_centre', lambda tracks, *a: tracks)
    free = maps(*args)
    assert np.abs(glint_at(free)[0] - (CX + 48)).max() <= 3 and glint_at(free)[1].min() > 0.5
    assert all(np.array_equal(centred[k], free[k]) for k in free)


def test_no_glint_moves_onto_the_curve_another_carries_across_rows_it_went_on_unseen():
    """A glint in the middle goes on unseen for six rows (the fit is thinly supported where it is); another, off to the
    side, is a glint of its own there, and the ledge in the middle is as good a place for it: it would be drawn on top of
    the first, two glints made one stronger streak. It stays where it was."""
    nr = 30
    rows = [crisp(40, 0.055) for _ in range(nr)]
    for q in range(10, 16):
        rows[q] = flat_top((40, 0.004), (55, 0.03))
    fit = np.array(rows)
    fit = fit - fit.mean(1, keepdims=True)
    den = np.ones_like(fit)
    den[10:16, 37:40], den[10:16, 40], den[10:16, 41] = 0.2, 0.5, 0.8
    free = oily._tracks(fit, 0.7 + fit, den, 0.0001, 8)
    kept = oily._tracks(fit, 0.7 + fit, den, 0.0001, 8, middle_at(nr))
    assert spans(free) == spans(kept) == [(0, 29), (10, 15)]
    assert all(np.array_equal(a, b) for f, k in zip(free, kept) for a, b in zip(f, k))


def test_a_glint_is_not_moved_near_where_the_curve_of_one_that_went_on_unseen_is_drawn():
    """The curve a glint is carried along across rows it went on unseen is smoothed with the rows either side and can be
    drawn far from where the track has it (here 54.3 in a row where the track has 45.5): another glint is not moved
    onto the middle, where it would be drawn on top of it (two glints in the picture, one after centring)."""
    c, q = np.arange(80.0), np.arange(60)
    gap = (q >= 30) & (q < 36)
    s = np.where(gap, 65, np.where(np.isin(q, [29, 36]), 45, 55))
    fit = ((0.5 - 0.007 * np.maximum(abs(c - 45) - 20, 0) ** 1.5)[None, :]
           + 0.003 * np.exp(-((c[None, :] - s[:, None]) / 3) ** 2) + 0.001 * gap[:, None] * (c == 54)[None, :])
    fit = fit - fit.mean(1, keepdims=True)
    den = np.full_like(fit, 0.6)
    den[gap] = 1
    den[30:36, 44:48] = 0.2
    around = np.tile((c - 50) / 20, (60, 1))
    free, kept = oily._tracks(fit, 0.8 + fit, den, 0.02, 8), oily._tracks(fit, 0.8 + fit, den, 0.02, 8, around)
    assert len(free) == len(kept) >= 2
    assert all(np.array_equal(a, b) for f, k in zip(free, kept) for a, b in zip(f, k))


def test_centring_heals_a_cut_a_hand_over_could_not_bridge():
    """The highest bump passes from 28 to 46 through two rows where neither stands much above the other (a hand-over
    with no run across it): the glint is cut in two, and fades out and in at the cut. Centring puts both pieces on the one
    line (46 is central enough), so it is one glint, without the fade at the old cut (its strength there is what the
    painted light gives) and as it was elsewhere."""
    nr = 30
    b28, b46 = np.full(nr, 0.002), np.full(nr, 0.002)
    b28[:9], b46[11:] = 0.040, 0.040
    b28[9], b46[9], b28[10], b46[10] = 0.006, 0.002, 0.002, 0.006
    rows = [flat_top((28, b28[q]), (46, b46[q]), (40, 0.004)) for q in range(nr)]
    fit = np.array(rows)
    fit = fit - fit.mean(1, keepdims=True)
    free = oily._tracks(fit, 0.3 + fit, np.ones_like(fit), 0.0001, 8)
    kept = oily._tracks(fit, 0.3 + fit, np.ones_like(fit), 0.0001, 8, middle_at(nr))
    assert spans(free) == [(0, 9), (10, 29)] and spans(kept) == [(0, 29)]
    assert np.ptp(kept[0][1][1:-1]) < 1.0
    sf, sk = row_strengths(free, nr), row_strengths(kept, nr)
    assert sk[9] > sf[9] + 0.1 and sk[10] > sf[10] + 0.1
    far = np.r_[0:6, 14:nr]
    np.testing.assert_allclose(sk[far], sf[far], atol=0.01)


def test_a_central_glint_goes_on_along_the_middle_across_a_stretch_of_flat_top():
    """A crisp light in the middle, then for ten rows only a flat top with a faint ledge on the middle and a higher bump
    beside it, then the crisp light again: the glint in the stretch was on the bump, ten cells off, between two on the
    middle. It is on the middle, in line with the others (and no stronger or weaker for it)."""
    rows = [crisp(40)] * 10 + [flat_top((40, 0.004), (50, 0.030))] * 10 + [crisp(40)] * 10
    free, kept = follow(rows), follow(rows, middle=middle_at(30))
    assert spans(free) == spans(kept) == [(0, 9), (10, 19), (20, 29)]
    assert places(free) == [40.5, 40.5, 50.5] and places(kept) == [40.5, 40.5, 40.5]
    for a, b in zip(sorted(free, key=lambda t: t[0][0]), sorted(kept, key=lambda t: t[0][0])):
        np.testing.assert_allclose(b[2], a[2])

import time

import cv2
import numpy as np
import pytest

from stocking import guide_fields as gf
from stocking import psd_io
from stocking.document import Document

from sample_data import PNG, PSD, needed, require

# a course across the left thigh, between two of the fixture's strokes
LEFT_THIGH_STROKE = [(300 + i * 12, 190 + i * 1.5) for i in range(26)]


@pytest.fixture(scope='module')
def reference():
    require()
    art, regions, strokes, _ = psd_io.read_guides(PSD)
    return list(regions), gf.solve_guides(list(regions.values()), strokes), list(regions.values())


@pytest.fixture
def doc():
    require()
    d = Document.open(PSD)
    assert d.wait_idle(60)
    yield d
    d.close()


def versions(d):
    return {r['name']: r['solve_v'] for r in d.state()['regions']}


def test_fixture_matches_reference_solve(doc, reference):
    names, (R0, V0, NX0, NY0, A0), masks = reference
    st = doc.state()
    assert [r['name'] for r in st['regions']] == names
    assert all(r['status'] == 'ok' for r in st['regions'])
    REG, V, NX, NY, A = doc.fields()
    # the reference drops islands under 2% of a region; the document keeps every piece (here the strip of 右腿
    # showing between the cloth and the cuff, and three specks of stray paint)
    assert (REG == gf.label_regions(masks, min_frac=0)).all()
    assert ((REG == R0) | (R0 == 0)).all()
    for i, name in enumerate(names, 1):
        sel = cv2.erode((R0 == i).astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool)
        ang = np.degrees(np.arccos(np.clip(np.abs(NX[sel] * NX0[sel] + NY[sel] * NY0[sel]), 0, 1)))
        # the document gives each stroke to one region; the reference's shared stroke layer lets the narrow 胯部 see
        # the bits of thigh strokes inside its filled-in outline, so it is held a little looser
        assert np.median(ang) < (2.0 if name == '胯部' else 1.5), name
    # the strokes only set the direction: the courses are evenly spaced, wherever the strokes crowd or spread
    sel = cv2.erode((REG > 0).astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool)
    g = np.hypot(*np.gradient(V)[::-1])[sel]
    p10, p50, p90 = np.percentile(g, [10, 50, 90])
    assert abs(p50 - 1) < 0.05 and p10 > 0.85 and p90 < 1.15


def test_stroke_edit_resolves_only_its_region(doc):
    before = versions(doc)
    sid = doc.add_stroke(LEFT_THIGH_STROKE)
    assert doc.wait_idle(60)
    after = versions(doc)
    assert [n for n in before if before[n] != after[n]] == ['左腿']
    st = doc.state()
    left = next(r for r in st['regions'] if r['name'] == '左腿')
    assert next(s for s in st['strokes'] if s['id'] == sid)['region'] == left['id']
    assert left['strokes'] == 6

    # undo returns to the cached solve: no re-solve, same version as at the start
    doc.undo()
    assert doc.wait_idle(5)
    assert versions(doc) == before


def test_region_edit_resolves_only_that_region(doc):
    before = versions(doc)
    crotch = next(r for r in doc.regions if r.name == '胯部')
    assert doc.paint(crotch.id, [(640, 860), (660, 870)], 6)
    assert doc.wait_idle(60)
    after = versions(doc)
    assert [n for n in before if before[n] != after[n]] == ['胯部']


def test_paint_erase_undo_redo(doc):
    r = doc.regions[2]
    m0 = r.mask.copy()
    assert doc.paint(r.id, [(100, 100), (140, 100)], 10)
    painted = r.mask.copy()
    assert painted.sum() > m0.sum()
    assert painted[100, 120] and painted[100, 100] and not painted[100, 160]
    assert doc.paint(r.id, [(120, 100)], 4, erase=True)
    assert not r.mask[100, 120]
    doc.undo()
    assert np.array_equal(r.mask, painted)
    doc.undo()
    assert np.array_equal(r.mask, m0)
    doc.redo()
    assert np.array_equal(r.mask, painted)


def test_delete_region_and_undo(doc):
    r = doc.regions[0]
    n = len(doc.regions)
    doc.delete_region(r.id)
    assert len(doc.regions) == n - 1
    # its strokes now belong to nobody (or a neighbour they overlap), never to a deleted region
    assert all(s['region'] != r.id for s in doc.state()['strokes'])
    doc.undo()
    assert doc.regions[0] is r
    assert doc.wait_idle(5)
    assert doc.state()['regions'][0]['status'] == 'ok'


def test_stroke_goes_to_majority_region_and_hint_breaks_ties():
    from stocking.document import Stroke
    d = Document(np.zeros((200, 200, 3), np.uint8), 'synthetic.png')
    try:
        a = np.zeros((200, 200), bool); a[:, :100] = True
        b = np.zeros((200, 200), bool); b[:, 100:] = True
        with d.lock:
            ra, rb = d._new_region('左', a), d._new_region('右', b)
            d._touch()

        def split(x0, x1):
            t = np.zeros((200, 200), np.uint8)
            Stroke(0, [(x0, 100), (x1, 100)]).raster(t, 0, 0)
            return (t[:, :100] > 0).sum(), (t[:, 100:] > 0).sum()

        tie = next(x for x in np.arange(55, 65, 0.25) if split(x, 199 - x)[0] == split(x, 199 - x)[1])
        s1 = d.add_stroke([(20, 50), (120, 50)])                        # mostly in A
        s2 = d.add_stroke([(tie, 100), (199 - tie, 100)], hint=rb.id)   # exact split: the hint decides
        s3 = d.add_stroke([(tie, 150), (199 - tie, 150)], hint=ra.id)
        s4 = d.add_stroke([(-50, -50), (-10, -10)])                     # outside the image: nobody's
        owner = {s['id']: s['region'] for s in d.state()['strokes']}
        assert owner[s1] == ra.id and owner[s2] == rb.id and owner[s3] == ra.id and owner[s4] is None
    finally:
        d.close()


def _leg_cut_in_two():
    """A straight leg 240 px wide with three strokes on its upper part, cut in two by something wider than it is
    (the other leg crossing in front): the lower piece has no stroke of its own. And the same leg uncut."""
    full = np.zeros((800, 400), bool)
    full[20:790, 60:300] = True
    region = full.copy()
    region[380:640] = False
    alpha = np.zeros((800, 400), np.uint8)
    for y in (80, 190, 300):
        cv2.line(alpha, (80, y), (280, y + 15), 255, 5)
    return full, region, alpha


def test_detached_piece_takes_the_courses_carried_on_behind():
    """A piece cut off by the other leg, with no stroke of its own, takes the courses of the rest carried on behind
    the crossing, as if the leg were whole. (Before that it was left untextured; before that the solver gave it a
    density of one course per pixel and took about a minute: stuck at 等待求解.)"""
    full, region, alpha = _leg_cut_in_two()
    t = time.perf_counter()
    V, NX, NY, A = gf.solve_region(region, alpha)
    assert time.perf_counter() - t < 5
    ref = gf.solve_region(full, alpha)
    low = cv2.erode((region & (np.arange(800)[:, None] > 600)).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    assert np.isfinite(V[region]).all() and np.isfinite(A[region]).all()
    assert np.percentile(np.abs(V - ref[0])[low], 99) < 3.0
    ang = np.degrees(np.arccos(np.clip(np.abs(NX * ref[1] + NY * ref[2])[low], 0, 1)))
    assert np.percentile(ang, 99) < 3.0


def test_document_textures_the_piece_beyond_the_crossing():
    full, region, alpha = _leg_cut_in_two()
    d = Document(np.zeros((800, 400, 3), np.uint8), 'synthetic.png')
    try:
        with d.lock:
            d._new_region('右腿', region)
            d._touch()
        for y in (80, 190, 300):
            d.add_stroke([(80, y), (280, y + 15)])
        assert d.wait_idle(30)
        st = d.state()['regions'][0]
        assert st['status'] == 'ok' and st['unguided'] == 0
        REG, V, NX, NY, A = d.fields()
        assert (REG[region] == 1).all() and np.isfinite(V).all()
        assert not d.unguided_map().any()
    finally:
        d.close()


def _occluded_leg():
    """A leg 280 px wide leaving the frame at the top, three slanted strokes; and the same leg with what might lie in
    front of it cut out of its mask: three strands of hair hanging over its top, a hand in the middle (the middle
    stroke runs under it) and a hand over its right edge."""
    h, w = 900, 400
    full = np.zeros((h, w), bool)
    full[:, 60:340] = True
    alpha = np.zeros((h, w), np.uint8)
    for y in (200, 450, 700):
        cv2.line(alpha, (80, y), (320, y + 25), 255, 5)
    occ = full.copy()
    for x0 in (110, 180, 250):
        occ[0:160, x0:x0 + 24] = False
    occ[400:510, 150:240] = False
    occ[600:680, 280:340] = False
    return full, occ, alpha


def test_courses_run_on_under_what_lies_in_front():
    """Hair, a hand: the courses must carry on underneath as if nothing were there, not bend around the hole the
    occluder leaves in the region's mask (and the stroke running under the hand must stay one course)."""
    full, occ, alpha = _occluded_leg()
    ref = gf.solve_region(full, alpha)
    got = gf.solve_region(occ, alpha)
    sel = cv2.erode(occ.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    assert np.isfinite(got[0][sel]).all()
    assert np.percentile(np.abs(got[0] - ref[0])[sel], 99) < 2.0            # V, px
    th = np.deg2rad(32)
    ang = [np.arctan2(*np.gradient(np.cos(th) * V + np.sin(th) * A)) for V, A in ((ref[0], ref[3]), (got[0], got[3]))]
    d = np.degrees(np.abs((ang[1] - ang[0] + np.pi) % (2 * np.pi) - np.pi))
    assert np.percentile(d[sel], 99) < 3.0                                    # tilted 斜单线 lines, degrees


def test_document_keeps_a_strip_showing_between_strands_of_hair():
    """Hair hangs over the top of a leg and a narrow strip of the leg shows between two strands, cut off from the
    rest by a strand across its foot: far under 2% of the region, which the region map used to drop as a stray speck
    (no texture there although the user selected it). It is the leg carried on under the hair, courses and all."""
    h, w = 800, 400
    full = np.zeros((h, w), bool)
    full[:790, 60:340] = True
    region = np.zeros((h, w), bool)
    region[200:790, 60:340] = True
    strip = np.zeros((h, w), bool)
    strip[40:185, 150:170] = True
    region |= strip
    assert strip.sum() < 0.02 * (region & ~strip).sum()
    alpha = np.zeros((h, w), np.uint8)
    for y in (300, 450, 600):
        cv2.line(alpha, (80, y), (320, y + 25), 255, 5)
    d = Document(np.zeros((h, w, 3), np.uint8), 'synthetic.png')
    try:
        with d.lock:
            d._new_region('右腿', region)
            d._touch()
        for y in (300, 450, 600):
            d.add_stroke([(80, y), (320, y + 25)])
        assert d.wait_idle(30)
        st = d.state()['regions'][0]
        assert st['status'] == 'ok' and st['unguided'] == 0
        REG, V, NX, NY, A = d.fields()
        assert (REG[strip] == 1).all()
        ref = gf.solve_region(full, alpha)[0]
        inner = cv2.erode(strip.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
        assert np.percentile(np.abs(V - ref)[inner], 99) < 3.0                # px: the leg's own courses, carried on
    finally:
        d.close()


@needed
def test_png_opens_with_default_regions():
    d = Document.open(PNG)
    try:
        st = d.state()
        assert [r['name'] for r in st['regions']] == ['左腿', '右腿']
        assert all(r['status'] == 'empty' for r in st['regions'])
        assert st['strokes'] == []
    finally:
        d.close()


def test_narrow_region_courses_run_one_way_to_the_edge():
    """A leg about 110 px across with a ragged outline: the edge pixels used to get bogus course values from the
    coarse solve grid, and on a region this narrow the iso-lines along that rim outgrew the real courses, so whole
    bands of courses had their across coordinate reversed (zigzags in 斜单线)."""
    h, w = 900, 300
    yy, xx = np.mgrid[0:h, 0:w]
    centre = 150 + 40 * np.sin(yy / 260.0)
    half = 55 + 6 * np.sin(yy / 7.0) + 4 * np.cos(xx / 5.0)
    region = (np.abs(xx - centre) < half) & (yy > 30) & (yy < 870)
    strokes = np.zeros((h, w), np.uint8)
    for y in (150, 330, 510, 690):
        c = int(150 + 40 * np.sin(y / 260.0))
        cv2.line(strokes, (c - 42, y), (c + 42, y + 6), 255, 5)
    REG, V, NX, NY, A = gf.solve_guides([region], strokes)
    sel = cv2.erode((REG == 1).astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    gy, gx = np.gradient(A)
    along = gx * (-NY) + gy * NX
    assert (along[sel] < 0).mean() < 0.01
    vy, vx = np.gradient(V)
    assert np.percentile(np.hypot(vx, vy)[sel], 99) < 1.5


@pytest.mark.parametrize('slope', [40, -40])
def test_wales_stay_straight_where_the_region_ends_across_the_courses(slope):
    """The courses run at a slant to the region's top and bottom edges (a leg leaving the frame): the courses there
    are cut short, and their arc-length midpoints used to slide sideways, bending the wales (and tilted 斜单线
    lines) in a band at each end. A stays a straight function of x on this rectangle."""
    h, w = 900, 500
    mc = np.zeros((h, w), bool)
    mc[:, 100:400] = True
    alpha = np.zeros((h, w), np.uint8)
    cv2.line(alpha, (120, 450), (380, 450 + slope), 255, 5)
    V, NX, NY, A = gf.solve_region(mc, alpha)
    zero = [100 + int(np.argmin(np.abs(A[y, 100:400]))) for y in range(10, h - 10, 5)]
    assert max(zero) - min(zero) <= 8, (min(zero), max(zero))       # it slid 63 px before


@pytest.mark.parametrize('bend', ['slant', 'arc'])
def test_no_seam_along_the_first_stroke(bend):
    """The phase used to be pinned to 0 on every coarse cell the first stroke touches. A slanted or curved stroke
    touches a staircase of cells either side of the line, so the field went flat across a band a cell wide and one
    course along that stroke came out about twice as wide: a seam along the drawn line, once per region."""
    mc = np.zeros((300, 200), bool)
    mc[10:290, 10:190] = True
    alpha = np.zeros((300, 200), np.uint8)
    xs = np.arange(20, 181)
    for y in (60, 150, 240):
        dy = np.tan(np.deg2rad(10)) * (xs - 100) if bend == 'slant' else 0.004 * (xs - 100) ** 2
        cv2.polylines(alpha, [np.stack([xs, y + dy], 1).astype(np.int32)], False, 255, 5)
    V, NX, NY, A = gf.solve_region(mc, alpha)
    gy, gx = np.gradient(V)
    g = np.hypot(gx, gy)
    for Q in gf.centre_lines(alpha, mc):
        xi, yi = np.round(Q[:, 0]).astype(int), np.round(Q[:, 1]).astype(int)
        n = np.stack([NX[yi, xi], NY[yi, xi]], 1)
        on = g[yi, xi]
        off = [g[np.round(P[:, 1]).astype(int), np.round(P[:, 0]).astype(int)] for P in (Q + 10 * n, Q - 10 * n)]
        ratio = on / np.mean(off, axis=0)
        assert np.percentile(ratio, 20) > 0.9, (Q.mean(0), np.percentile(ratio, 20))
    first = min(gf.centre_lines(alpha, mc), key=lambda Q: Q[:, 1].mean())
    assert abs(np.median(V[np.round(first[:, 1]).astype(int), np.round(first[:, 0]).astype(int)])) < 2


def test_strokes_set_the_direction_not_the_spacing():
    """Strokes 20 px apart at the top and 60 px apart below: the courses stay evenly spaced (the reference crowded
    them like the strokes, as perspective); more strokes only say more about which way they run."""
    mc = np.zeros((400, 240), bool)
    mc[10:390, 10:230] = True
    alpha = np.zeros((400, 240), np.uint8)
    for y in (40, 60, 80, 140, 200, 260, 320):
        cv2.line(alpha, (25, y), (215, y + 8), 255, 5)
    V, NX, NY, A = gf.solve_region(mc, alpha)
    g = np.hypot(*np.gradient(V)[::-1])
    top, low = (slice(45, 75), slice(40, 200)), (slice(160, 300), slice(40, 200))
    assert 0.9 < g[top].mean() / g[low].mean() < 1.1 and abs(np.median(g[20:380, 20:220]) - 1) < 0.03
    few = np.zeros_like(alpha)
    for y in (40, 320):
        cv2.line(few, (25, y), (215, y + 8), 255, 5)
    Vf = gf.solve_region(mc, few)[0]
    inner = (slice(20, 380), slice(20, 220))
    assert np.percentile(np.abs((V - Vf)[inner] - np.median((V - Vf)[inner])), 99) < 1.0

def test_courses_keep_one_way_round_a_bend():
    """A leg bending through 240 degrees (a band round a centre), strokes across it: the courses' normal must turn
    with the leg, so V climbs steadily along it. Oriented by one global sign, as before, the ends of the band
    disagreed with the middle and the courses folded."""
    h, w = 520, 520
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(xx - 260, yy - 260)
    th = np.degrees(np.arctan2(yy - 260, xx - 260))
    mc = (r > 100) & (r < 230) & (np.abs(th) < 120)
    alpha = np.zeros((h, w), np.uint8)
    for a in (-100, -50, 0, 50, 100):
        t = np.deg2rad(a)
        cv2.line(alpha, (int(260 + 110 * np.cos(t)), int(260 + 110 * np.sin(t))),
                 (int(260 + 220 * np.cos(t)), int(260 + 220 * np.sin(t))), 255, 5)
    V, NX, NY, A = gf.solve_region(mc, alpha)
    ang = np.deg2rad(np.arange(-112, 113, 4))
    v = V[np.round(260 + 165 * np.sin(ang)).astype(int), np.round(260 + 165 * np.cos(ang)).astype(int)]
    dv = np.diff(v) * np.sign(v[-1] - v[0])
    assert dv.min() > 0.5 * np.median(dv)                # monotonic all the way round, no fold


def _folded_leg():
    """A thigh (x 40..190) with its calf folded up behind it (x 190..340), touching along x = 190 above y = 300 and
    joined by the knee below; the thigh's stroke slants, the calf's is level. The wall: where they touch."""
    h, w = 420, 380
    mc = np.zeros((h, w), bool)
    mc[10:410, 40:340] = True
    alpha = np.zeros((h, w), np.uint8)
    cv2.line(alpha, (60, 120), (175, 180), 255, 5)
    cv2.line(alpha, (205, 150), (325, 150), 255, 5)
    W = np.zeros((h, w), bool)
    W[10:300, 189:192] = True
    return mc, alpha, W


def test_a_wall_keeps_folded_stretches_apart_and_the_knee_joins_them():
    mc, alpha, W = _folded_leg()
    info = {}
    V, NX, NY, A = gf.solve_region(mc, alpha, W, info)
    ang = lambda y, x: np.degrees(np.arctan2(NY[y, x], NX[y, x])) % 180
    thigh, calf = ang(150, 175), ang(150, 205)
    assert abs(thigh - (90 + np.degrees(np.arctan2(60, 115)))) < 6 and abs(calf - 90) < 6
    assert abs(ang(60, 183) - ang(60, 197)) > 0.8 * abs(thigh - calf)    # 7 px either side of the wall
    _, NX0, NY0, _ = gf.solve_region(mc, alpha)
    ang0 = lambda y, x: np.degrees(np.arctan2(NY0[y, x], NX0[y, x])) % 180
    assert abs(ang0(60, 183) - ang0(60, 197)) < 0.2 * abs(thigh - calf)   # without it they run into each other
    knee = cv2.erode(mc.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool)
    knee[:330] = False
    g = np.hypot(*np.gradient(V)[::-1])[knee]
    assert 0.6 < g.min() and g.max() < 1.4               # evenly spaced and seamless round the end of the wall
    cut = info['cut']
    assert cut[150, 190] and not cut[150, 170] and not cut[150, 210] and not cut[350].any()


def test_document_finds_walls_once_depth_arrives():
    """No depth, no walls: the region solves as before. When the depth model's disparity lands, the step where the
    calf lies behind the thigh becomes a wall and the region re-solves with it."""
    mc, alpha, _ = _folded_leg()
    h, w = mc.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    disp = 1.5 * np.sqrt(np.clip(1 - ((xx - 190) / 170) ** 2, 0, 1)) + 0.5 * (xx < 190) / (1 + np.exp((yy - 300) / 25))
    art = np.full((h, w, 3), 40, np.uint8)
    d = Document(art, 'synthetic.png')
    try:
        with d.lock:
            r = d._new_region('左腿', mc)
            d._touch()
        d.add_stroke([(60, 120), (175, 180)])
        d.add_stroke([(205, 150), (325, 150)])
        assert d.wait_idle(30)
        before = versions(d)['左腿']
        assert not d.cut_map().any() and d.courses(r.id)['walls'] == []
        d.disparity = disp.astype(np.float32)
        assert d.wait_idle(30) and versions(d)['左腿'] != before
        cut = d.cut_map()
        assert cut[150, 190] and not cut[380].any()
        walls = d.courses(r.id)['walls']
        assert len(walls) == 1 and abs(np.reshape(walls[0], (-1, 2))[:, 0] / 10 - 190).max() < 6
    finally:
        d.close()


def test_across_coordinate_runs_on_along_courses_split_by_a_wall():
    """A wall splits many courses in two (thigh side, calf side). Only the longest piece of each used to be traced,
    so the other side took its across coordinate A from courses beyond the wall: tilted 斜单线 lines and 针织
    columns came out in broken bands. Along every course, on both sides, A must run at one px per px."""
    mc, alpha, W = _folded_leg()
    info = {}
    V, NX, NY, A = gf.solve_region(mc, alpha, W, info)
    gy, gx = np.gradient(A)
    along = gx * -NY + gy * NX
    ok = cv2.erode((mc & ~info['cut']).astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
    assert np.percentile(np.abs(along[ok] - 1), 99) < 0.15
    across = np.abs(gx * NX + gy * NY)
    sides = ok.copy()
    sides[300:] = False                                  # round the knee the courses turn: A shears there anyway
    assert np.percentile(across[sides], 99) < 0.3


def _folded_doc(depth=True):
    mc, alpha, _ = _folded_leg()
    h, w = mc.shape
    d = Document(np.full((h, w, 3), 40, np.uint8), 'synthetic.png')
    with d.lock:
        r = d._new_region('左腿', mc)
        d._touch()
    d.add_stroke([(60, 120), (175, 180)])
    d.add_stroke([(205, 150), (325, 150)])
    if depth:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        d.disparity = (1.5 * np.sqrt(np.clip(1 - ((xx - 190) / 170) ** 2, 0, 1))
                       + 0.5 * (xx < 190) / (1 + np.exp((yy - 300) / 25))).astype(np.float32)
    assert d.wait_idle(30)
    return d, r


def test_drawn_divider_separates_without_depth_and_undoes():
    """No depth model: the user draws the 隔开 line themselves. It cuts like a found wall, and undo/redo take it
    away and back."""
    d, r = _folded_doc(depth=False)
    try:
        assert not d.cut_map().any()
        did = d.add_divider([(190, 12), (190, 298)])
        assert d.wait_idle(30)
        assert d.cut_map()[150, 190] and [x['id'] for x in d.state()['dividers']] == [did]
        assert d.courses(r.id)['walls'] == []            # the view draws the user's own lines from the state
        _, _, NX, NY, _ = d.fields()
        ang = lambda y, x: np.degrees(np.arctan2(NY[y, x], NX[y, x])) % 180
        assert abs(ang(60, 183) - ang(60, 197)) > 20
        d.undo()
        assert d.wait_idle(30) and not d.cut_map().any() and d.state()['dividers'] == []
        d.redo()
        assert d.wait_idle(30) and d.cut_map()[150, 190]
        assert d.remove_wall_at(192, 150, 6) == 'divider'
        assert d.wait_idle(30) and not d.cut_map().any()
        with pytest.raises(ValueError):
            d.remove_wall_at(100, 380, 6)                 # nothing there
    finally:
        d.close()


def test_deleting_a_found_wall_keeps_it_gone():
    d, r = _folded_doc()
    try:
        assert d.cut_map()[150, 190] and len(d.courses(r.id)['walls']) == 1
        assert d.remove_wall_at(191, 120, 6) == 'found'
        assert d.wait_idle(30)
        assert not d.cut_map().any() and d.courses(r.id)['walls'] == []
        d.undo()
        assert d.wait_idle(30) and d.cut_map()[150, 190]
    finally:
        d.close()


def test_color_exclusion_can_be_turned_off_and_undone():
    """A grey stocking with a warm patch (skin showing through at a knee): the colour test drops the patch. Turned
    off, every region pixel is textured; undo turns it back on. Each change gives a new coverage version, so the
    views and the look re-render."""
    art = np.full((200, 160, 3), 70, np.uint8)
    art[80:120, 60:100] = (150, 105, 95)
    m = np.zeros((200, 160), bool)
    m[10:190, 20:140] = True
    m[100, 140:150] = True                               # a 1 px sliver of the selection: kept when the test is off
    d = Document(art, 'synthetic.png')
    try:
        with d.lock:
            d._new_region('左腿', m)
            d._touch()
        stock, _, stats, v_on = d.coverage()
        assert not stock[100, 80] and stock[30, 30] and d.state()['color_exclude'] is True
        d.set_color_exclude(False)
        stock, _, stats, v_off = d.coverage()
        assert v_off != v_on and stock[100, 80] and np.array_equal(stock, m) and stats[0]['covered'] == stats[0]['pixels']
        assert d.state()['color_exclude'] is False and d.state()['coverage_v'] == v_off
        d.undo()
        assert d.coverage()[3] == v_on and not d.coverage()[0][100, 80]
    finally:
        d.close()


def test_wales_have_no_steps_where_courses_alternate_whole_and_cut_short():
    """A bend: the leg's lower edge runs at about 45 degrees to the courses, wobbling a little, so from one course
    to the next some cross the whole width and some are cut short by that edge. Each course's across coordinate A
    was pinned hard to a target, and the two kinds take their targets differently (the smoothed medial line, the
    medial line carried on straight), so A stepped wherever the kind changed: bands of jagged 斜单线 lines at 32
    degrees and broken 针织 columns on the user's bent leg. A must change smoothly from course to course."""
    h, w = 500, 600
    yy, xx = np.mgrid[0:h, 0:w]
    mc = (yy > 40) & (yy < 60 + (xx - 50) + 260 + 3 * np.sin(xx / 9.0)) & (xx > 50) & (xx < 560)
    alpha = np.zeros((h, w), np.uint8)
    for x in (150, 300, 450):
        cv2.line(alpha, (x, 60), (x + 10, 300), 255, 5)
    V, NX, NY, A = gf.solve_region(mc, alpha)
    gy, gx = np.gradient(A)
    dn = (gx * NX + gy * NY).astype(np.float32)
    mf = mc.astype(np.float32)
    blur = lambda f, s: cv2.GaussianBlur(f * mf, (0, 0), s) / np.maximum(cv2.GaussianBlur(mf, (0, 0), s), 1e-6)
    step = np.abs(blur(dn, 1.0) - blur(dn, 8.0))           # A's change across one course, less its smooth trend
    inner = cv2.erode(mc.astype(np.uint8), np.ones((31, 31), np.uint8)).astype(bool)
    assert np.percentile(step[inner], 99.5) < 0.6

import cv2
import numpy as np
import pytest

from stocking.document import Document, clean_segment


def make_doc(n=3, size=100):
    d = Document(np.full((size, size, 3), 128, np.uint8), 'synthetic.png')
    with d.lock:
        regs = [d._new_region(f'r{i}') for i in range(n)]
        d._touch()
    return d, regs


def rect(size, x0, y0, x1, y1):
    m = np.zeros((size, size), bool)
    m[y0:y1, x0:x1] = True
    return m


def test_paint_takes_pixels_from_other_regions_and_undo_restores_both():
    d, (a, b, _) = make_doc()
    try:
        d.paint(b.id, [(50, 50)], 10)
        assert b.mask[50, 50]
        d.paint(a.id, [(50, 50)], 4)
        assert a.mask[50, 50] and not b.mask[50, 50]
        assert b.mask[50, 58]                      # outside the smaller dab, b keeps its pixels
        d.undo()
        assert not a.mask[50, 50] and b.mask[50, 50]
        d.redo()
        assert a.mask[50, 50] and not b.mask[50, 50]
    finally:
        d.close()


def test_erase_touches_only_the_current_region():
    d, (a, b, _) = make_doc()
    try:
        d.paint(b.id, [(50, 50)], 10)
        d.paint(a.id, [(20, 20)], 5)
        d.paint(a.id, [(50, 50)], 10, erase=True)
        assert b.mask[50, 50]
    finally:
        d.close()


def test_segment_add_subtract_and_cycle():
    d, (a, b, _) = make_doc()
    try:
        small, mid, big = rect(100, 40, 40, 50, 50), rect(100, 30, 30, 60, 60), rect(100, 10, 10, 90, 90)
        d.paint(b.id, [(85, 85)], 3)
        b0 = b.mask.copy()
        d.segment_click(a.id, 45, 45, False, [small, mid, big], 1)
        assert np.array_equal(a.mask, mid)
        assert d.state()['segment_cycle'] == {'region': a.id, 'k': 1, 'n': 3, 'subtract': False, 'pt': (45.0, 45.0),
                                              'click': d._seg_last['click']}

        assert d.cycle_segment(1) == 2              # the biggest candidate takes b's pixels too
        assert np.array_equal(a.mask, big)
        assert not (b.mask & big).any()
        assert d.cycle_segment(1) == 0              # wraps round
        assert np.array_equal(a.mask, small) and np.array_equal(b.mask, b0)

        # one undo step per click, however many times it was cycled
        d.undo()
        assert not a.mask.any() and np.array_equal(b.mask, b0)
        d.redo()
        assert np.array_equal(a.mask, small)

        # subtracting removes from the current region only
        d.segment_click(b.id, 45, 45, True, [small, mid, big], 2)
        assert np.array_equal(b.mask, b0 & ~big)
    finally:
        d.close()


def test_cycle_only_straight_after_the_click():
    d, (a, b, _) = make_doc()
    try:
        m = [rect(100, 40, 40, 50, 50), rect(100, 30, 30, 60, 60), rect(100, 10, 10, 90, 90)]
        d.segment_click(a.id, 45, 45, False, m, 0)
        d.paint(b.id, [(5, 5)], 2)
        assert d.state()['segment_cycle'] is None
        with pytest.raises(ValueError):
            d.cycle_segment(1)
    finally:
        d.close()


def test_segment_that_changes_nothing_can_still_be_cycled():
    d, (a, _, _) = make_doc()
    try:
        m = [rect(100, 40, 40, 50, 50), rect(100, 30, 30, 60, 60), rect(100, 10, 10, 90, 90)]
        d.segment_click(a.id, 45, 45, True, m, 0)    # subtract from an empty region: no change, no undo step
        assert not d.state()['can_undo']
        assert d.cycle_segment(1) == 1
    finally:
        d.close()


def test_clean_segment_drops_specks_and_fills_pinholes():
    m = rect(200, 50, 50, 150, 150)
    m[100, 100] = False                             # pinhole
    m[5:7, 5:7] = True                              # speck
    box, crop = clean_segment(m)
    assert box == (50, 50, 150, 150)
    assert crop.all()
    assert clean_segment(np.zeros((50, 50), bool)) == (None, None)


def test_select_segment_by_tier_and_outlines():
    d, (a, _, _) = make_doc()
    try:
        m = [rect(100, 40, 40, 50, 50), rect(100, 30, 30, 60, 60), rect(100, 10, 10, 90, 90)]
        d.segment_click(a.id, 45, 45, False, m, 0)
        d.select_segment(2)
        assert np.array_equal(a.mask, m[2])
        d.select_segment(2)                         # same tier again: no change, still one undo step
        o = d.segment_outlines()
        assert o['click'] == d.state()['segment_cycle']['click'] and len(o['outlines']) == 3
        xs = np.array(o['outlines'][1][0][0::2]) / 10
        assert xs.min() == 30 and xs.max() == 59    # pixel-centre outline of the 30..59 square
        d.undo()
        assert not a.mask.any()
        with pytest.raises(ValueError):
            d.select_segment(1)
    finally:
        d.close()


def two_lobes(size=120):
    """Two touching discs with a dark crease drawn between them in the art."""
    m = np.zeros((size, size), np.uint8)
    cv2.circle(m, (38, 60), 30, 1, -1)
    cv2.circle(m, (82, 60), 30, 1, -1)
    art = np.full((size, size, 3), 150, np.uint8)
    cv2.line(art, (64, 0), (64, size), (20, 20, 20), 2)
    return m.astype(bool), art


def test_split_follows_the_crease_and_undo_restores():
    m, art = two_lobes()
    d = Document(art, 'synthetic.png')
    try:
        with d.lock:
            r = d._new_region('中间', m)
            other = d._new_region('右胸')
            d._touch()
        kept, new = d.split_region(r.id)
        names = [x.name for x in d.regions]
        assert names == ['中间-左', '中间-右', '右胸'] and kept == r.id
        left, right = d.region(kept).mask, d.region(new).mask
        assert not (left & right).any() and np.array_equal(left | right, m)
        cols = np.nonzero(left.any(0))[0]
        assert 62 <= cols.max() <= 66               # cut on the crease at x = 64, not at the 2-means centre
        d.undo()
        assert [x.name for x in d.regions] == ['中间', '右胸'] and np.array_equal(r.mask, m)
        d.redo()
        assert [x.name for x in d.regions] == ['中间-左', '中间-右', '右胸']
    finally:
        d.close()


def test_split_cuts_a_pair_down_its_mirror_axis_whatever_its_proportions():
    """自动分割 is for a left/right pair. Two standing legs make a tall region and a torso a nearly square one: the
    cut goes down the middle between the two halves, not across the region's longer side."""
    from stocking import split
    n = 200
    legs = np.zeros((n, n), np.uint8)
    cv2.fillConvexPoly(legs, np.array([[40, 5], [95, 5], [85, 195], [60, 195]]), 1)
    cv2.fillConvexPoly(legs, np.array([[105, 5], [160, 5], [140, 195], [115, 195]]), 1)
    a, b, axis = split.split_mask(legs.astype(bool), np.full((n, n, 3), 150, np.uint8))
    assert axis == 'x' and np.array_equal(a | b, legs.astype(bool))
    assert a[:, 100:].sum() == 0 and b[:, :100].sum() == 0

    torso = np.zeros((n, n), np.uint8)
    cv2.fillConvexPoly(torso, np.array([[10, 20], [190, 20], [160, 195], [40, 195]]), 1)   # shoulders wider than waist
    art = np.full((n, n, 3), 150, np.uint8)
    cv2.line(art, (100, 60), (100, 140), (20, 20, 20), 2)                               # the cleavage, drawn
    a, b, axis = split.split_mask(torso.astype(bool), art)
    assert axis == 'x'
    for y in (30, 100, 180):
        cols = np.flatnonzero(a[y])
        assert 95 <= cols.max() <= 105, (y, cols.max())


def test_split_separate_pieces_and_refuse_tiny():
    from stocking import split
    m = rect(100, 5, 40, 30, 60) | rect(100, 70, 10, 95, 30)
    a, b, axis = split.split_mask(m, np.zeros((100, 100, 3), np.uint8))
    assert axis == 'x' and np.array_equal(a, rect(100, 5, 40, 30, 60)) and np.array_equal(b, rect(100, 70, 10, 95, 30))
    assert split.split_mask(rect(100, 0, 0, 3, 3), np.zeros((100, 100, 3), np.uint8)) is None


def test_merge_region_and_neighbours():
    d, (a, b, c) = make_doc()
    try:
        d.paint(a.id, [(20, 50)], 10)
        d.paint(b.id, [(35, 50)], 6)               # touches a
        d.paint(c.id, [(85, 50)], 6)               # far away
        assert [n['id'] for n in d.neighbours(b.id)][0] == a.id
        assert next(n for n in d.neighbours(b.id) if n['id'] == c.id)['shared'] == 0
        sid = d.add_stroke([(28, 50), (42, 50)], hint=b.id)
        before = a.mask | b.mask
        d.merge_region(b.id, a.id)
        assert [r.id for r in d.regions] == [a.id, c.id]
        assert np.array_equal(a.mask, before)
        assert next(s for s in d.state()['strokes'] if s['id'] == sid)['region'] == a.id
        d.undo()
        assert [r.id for r in d.regions] == [a.id, b.id, c.id] and not (a.mask & b.mask).any()
        with pytest.raises(ValueError):
            d.merge_region(a.id, a.id)
    finally:
        d.close()


def test_split_cuts_a_chunk_attached_to_one_side_down_the_middle():
    """Two breasts clicked separately (they meet at a gap, the crease) plus the chunk above the cleavage, which is
    attached to the left one only. The cut follows the crease and carries straight on through the chunk."""
    from stocking import split
    n = 160
    art = np.full((n, n, 3), 150, np.uint8)
    left = np.zeros((n, n), np.uint8)
    right = np.zeros((n, n), np.uint8)
    cv2.circle(left, (45, 95), 38, 1, -1)
    cv2.circle(right, (115, 95), 38, 1, -1)
    m = (left | right).astype(bool)
    m[60:135, 79:81] = False                        # the crease: a gap between the two breasts
    cv2.line(art, (80, 60), (80, 135), (20, 20, 20), 2)
    chunk = np.zeros((n, n), bool)
    chunk[35:70, 60:100] = True
    outline = np.zeros((n, n), np.uint8)
    cv2.circle(outline, (115, 95), 39, 1, 2)        # the right breast's outline separates it from the chunk
    cv2.circle(art, (115, 95), 39, (20, 20, 20), 2)
    m |= chunk & (right == 0)
    m &= outline == 0
    a, b, axis = split.split_mask(m, art)
    assert axis == 'x' and np.array_equal(a | b, m) and not (a & b).any()
    for y in range(36, 55):                         # rows of the chunk above the breasts
        cols = np.flatnonzero(a[y, 60:100]) + 60
        assert 75 <= cols.max() <= 85, (y, cols.max())
    assert a[100, 40] and b[100, 120]


def test_cut_along_a_short_line_carried_on_past_its_ends():
    from stocking import split
    m = rect(100, 10, 10, 90, 90)
    a, b, axis = split.cut_mask(m, [(40, 45), (40, 55)])          # 10 px of line in the middle of an 80 px square
    assert axis == 'x' and np.array_equal(a | b, m) and not (a & b).any()
    cols_a = np.flatnonzero(a.any(0))
    assert 39 <= cols_a.max() <= 41 and a[12, 20] and b[88, 80]  # the whole height is cut, not just the 10 px
    a2, b2, axis2 = split.cut_mask(m, [(20, 30), (30, 40), (40, 50)])   # a diagonal: top-right vs bottom-left
    assert axis2 in ('x', 'y') and b2[80, 15] != b2[15, 80]
    assert split.cut_mask(m, [(95, 5), (99, 5)]) is None          # carried on, it still misses the region


def test_cut_line_splits_pieces_by_side():
    from stocking import split
    m = rect(120, 5, 40, 30, 60) | rect(120, 50, 40, 70, 60) | rect(120, 90, 40, 115, 60)
    a, b, _ = split.cut_mask(m, [(60, 45), (60, 55)])             # through the middle piece only
    assert a[50, 10] and a[50, 55] and b[50, 65] and b[50, 100]


def test_split_region_along_a_line_and_undo():
    d, (a, b, _) = make_doc()
    try:
        d.paint(a.id, [(20, 50), (80, 50)], 15)
        before = a.mask.copy()
        kept, new = d.split_region(a.id, [(50, 45), (50, 55)])
        assert [r.name for r in d.regions][:2] == ['r0-左', 'r0-右']
        assert np.array_equal(d.region(kept).mask | d.region(new).mask, before)
        assert d.region(kept).mask[50, 30] and d.region(new).mask[50, 70]
        d.undo()
        assert [r.name for r in d.regions] == ['r0', 'r1', 'r2'] and np.array_equal(a.mask, before)
        with pytest.raises(ValueError):
            d.split_region(a.id, [(98, 2), (99, 2)])
    finally:
        d.close()


def test_cut_snaps_a_shaky_line_onto_the_crease():
    """A jittery stroke drawn a few px beside a dark crease cuts along the crease when snapping is on."""
    from stocking import split
    n = 200
    art = np.full((n, n, 3), 150, np.uint8)
    cv2.line(art, (103, 0), (103, n), (25, 25, 25), 2)
    m = rect(n, 20, 20, 180, 180)
    rng = np.random.default_rng(0)
    ys = np.arange(60, 140, 2.0)
    pts = np.stack([96 + rng.normal(0, 2.5, len(ys)), ys], 1)       # 7 px left of the crease, shaky
    a0, b0, _ = split.cut_mask(m, pts)                               # as drawn
    a1, b1, _ = split.cut_mask(m, pts, art, 14)                      # snapped
    assert np.array_equal(a1 | b1, m) and not (a1 & b1).any()
    cols = [np.flatnonzero(a1[y])[-1] for y in range(30, 170, 10)]
    assert all(101 <= c <= 105 for c in cols), cols
    cols0 = [np.flatnonzero(a0[y])[-1] for y in range(60, 140, 10)]
    assert max(cols0) < 101                                          # unsnapped stays where it was drawn
    # with no line art nearby, snapping only smooths the stroke
    a2, _, _ = split.cut_mask(m, pts, np.full((n, n, 3), 150, np.uint8), 14)
    cols2 = [np.flatnonzero(a2[y])[-1] for y in range(60, 140, 10)]
    assert all(abs(c - 96) <= 4 for c in cols2), cols2

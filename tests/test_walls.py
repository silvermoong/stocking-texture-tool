import cv2
import numpy as np

from stocking import walls


def _scene(step=True, slope=False, stock_right=True, strip=False):
    """400 x 300 stockings, a gentle rounding in depth; the left half in front of the right along x = 150 for
    y < 250 (a calf folded behind its thigh), the step fading out smoothly below (they join at the knee)."""
    h, w = 400, 300
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = 1.5 * np.sqrt(np.clip(1 - ((xx - 150) / 170) ** 2, 0, 1))         # rounded about as much as a real leg
    if step:
        d += 0.5 * (xx < 150) / (1 + np.exp((yy - 250) / 30.0))
    if slope:
        d += 0.5 / (1 + np.exp(-(xx - 150) / 25.0))
    stock = np.ones((h, w), bool) if stock_right else xx < 150
    if strip:
        stock[:, 148:154] = False                        # a strand of hair lying across, nearer than the stocking
        d[:, 148:154] += 1.0
    return d, stock


def test_wall_where_one_stretch_lies_in_front_of_another():
    d, stock = _scene()
    W = walls.find_walls(walls.ridges(d), stock)
    ys, xs = np.nonzero(W)
    assert len(ys) and np.abs(xs - 150).max() <= 4
    assert ys.min() < 40 and 220 < ys.max() < 320                         # down the step, fading by the knee


def test_no_wall_on_a_slope_a_silhouette_or_an_occluder():
    """The side of a leg turning away is steep but not a step; the outline has background on its other side; a
    strand of hair across the stocking has itself on one side of each of its edges."""
    for kw in ({'step': False, 'slope': True}, {'stock_right': False}, {'step': False, 'strip': True}):
        d, stock = _scene(**kw)
        assert not walls.find_walls(walls.ridges(d), stock).any(), kw


def test_carry_through_crosses_only_the_filled_in_gap():
    """A wall ending at (or just short of) the visible outline where the filled-in area goes on continues through
    it to the end of the domain; one ending in visible stocking stops."""
    h, w = 300, 300
    visible = np.ones((h, w), bool)
    visible[:80, 140:160] = False                        # a gap between the tops of thigh and calf, filled in
    W = np.zeros((h, w), bool)
    W[92:200, 149:152] = True                            # stops 12 px short of it
    out = walls.carry_through(W, visible, np.ones((h, w), bool))
    assert out[:92, 145:156].any(axis=1).all()           # on up through the gap to the frame
    assert out[:80, 140:160].all()                        # the gap itself is left out of the solve
    assert not out[203:].any()                            # not on down into the knee

"""Renders and solves that went wrong on edge cases of numbers: a stale full render after changing only the first
layer's amount, a phase anchor on a stroke lying in a wall's slit, NaN settings, tilt sides holding a whole-image
mask per speck, region labels past 127, and the densest point landing on the background."""
import tracemalloc

import cv2
import numpy as np
import pytest

from stocking import guide_fields as gf, look, presets


def _flat_scene(h=120, w=160, REG=None, names=('左腿',)):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    art = np.full((h, w, 3), 120, np.uint8)
    REG = np.ones((h, w), np.int16) if REG is None else REG
    m = REG > 0
    return look.Scene(art, REG, np.where(m, yy, 0.0), np.where(m, xx, 0.0), m, m.astype(np.float32), list(names))


# ------------------------------------------------------------------ #2 the full render's cache key

def test_changing_only_the_first_layers_amount_renders_anew():
    base = dict(style='knit', strength=100, strength_auto=False, lock_total=False, amount=50,
                layers=[dict(style='lines', strength=100, strength_auto=False, amount=50)])
    s = _flat_scene()
    before, _ = s.render(base)
    after, _ = s.render(dict(base, amount=90))
    fresh, _ = _flat_scene().render(dict(base, amount=90))
    assert not np.array_equal(before, after)
    assert np.array_equal(after, fresh)
    assert 'amount' in look.RENDER_KEYS


def test_every_setting_that_changes_a_render_is_in_its_key():
    # strength_auto and sparkle_link are folded into strength and sparkle_bright before the key is taken
    assert set(look.DEFAULTS) - set(look.RENDER_KEYS) == {'strength_auto', 'sparkle_link'}


# ------------------------------------------------------------------ #8 phase anchor in a wall's slit

def _two_guides():
    m = np.zeros((100, 100), bool)
    m[10:90, 10:90] = True
    alpha = np.zeros((100, 100), np.uint8)
    alpha[19:22, 15:85] = 255
    alpha[59:62, 15:85] = 255
    return m, alpha


@pytest.mark.parametrize('rows', [(16, 25), (56, 65)])
def test_a_stroke_in_a_walls_slit_does_not_anchor_the_phase(rows):
    m, alpha = _two_guides()
    walls = np.zeros((100, 100), bool)
    walls[rows[0]:rows[1], :] = True
    res = gf.solve_v(m, alpha, walls)
    assert res is not None
    V = res[0]
    assert np.isfinite(V[m]).all()


def test_every_stroke_in_a_walls_slit_leaves_the_region_unsolved():
    m, alpha = _two_guides()
    alpha[59:62] = 0
    walls = np.zeros((100, 100), bool)
    walls[16:25, :] = True
    assert gf.solve_v(m, alpha, walls) is None


# ------------------------------------------------------------------ #10 NaN and infinity

NUMERIC = ('density', 'tilt', 'strength', 'weight', 'amount', 'particle', 'moire', 'moire_area',
           'sparkle_depth', 'sparkle_bright', 'sparkle_painted', 'sparkle_even')


@pytest.mark.parametrize('key', NUMERIC)
@pytest.mark.parametrize('bad', [float('nan'), 'nan', float('inf'), '-inf'])
def test_non_finite_settings_are_refused(key, bad):
    with pytest.raises(ValueError):
        look.clean_params({key: bad, 'sparkle_link': False})


@pytest.mark.parametrize('key', ('density', 'tilt', 'strength', 'weight', 'amount'))
def test_non_finite_layer_settings_are_refused(key):
    with pytest.raises(ValueError):
        look.clean_params({'layers': [{key: 'nan'}]})


def test_a_stored_preset_with_nan_is_unreadable_not_a_crash(monkeypatch):
    monkeypatch.setattr(presets, '_stored', lambda: {'坏': {'density': float('nan')}, '好': {'style': 'knit'}})
    bad, good = presets.listing()
    assert bad['params'] is None and good['params'] is not None


# ------------------------------------------------------------------ #13 tilt sides

def _old_tilt_sides(R, names):
    """look.tilt_sides as it was, one whole-image mask per piece."""
    side = np.zeros(R.shape, np.float64)
    inside = R > 0
    if not inside.any():
        return side
    xs_all = np.nonzero(inside)[1]
    mid, span = xs_all.mean(), max(float(np.ptp(xs_all)), 1.0)
    margin = 0.15 * span
    parts = {}
    for i in range(1, len(names) + 1):
        n, lab = cv2.connectedComponents((R == i).astype(np.uint8), connectivity=8)
        parts[i] = [(p, np.nonzero(p)[1].mean()) for p in (lab == k for k in range(1, n))]

    def lean(cx, i):
        others = [c for j, ps in parts.items() if j != i for p, c in ps if p.sum() >= 0.01 * len(xs_all)]
        if abs(cx - mid) < margin and any(c < cx - margin for c in others) and any(c > cx + margin for c in others):
            return 0.0
        return 1.0 if cx <= mid else -1.0

    for i, pieces in parts.items():
        if not pieces:
            continue
        m = R == i
        s = look.side_of(names[i - 1])
        if s:
            side[m] = s
            continue
        big = [c for p, c in pieces if p.sum() >= 0.1 * m.sum()]
        if any(c < mid - margin for c in big) and any(c > mid + margin for c in big):
            for p, c in pieces:
                side[p] = 1.0 if c <= mid else -1.0
        else:
            side[m] = lean(np.nonzero(m)[1].mean(), i)
    return side


def _tilt_cases():
    h, w = 120, 200
    two = np.zeros((h, w), np.int16)
    two[10:110, 20:70], two[10:110, 130:180] = 1, 2
    crotch = two.copy()
    crotch[10:40, 80:120] = 3
    both = np.zeros((h, w), np.int16)
    both[10:110, 20:70] = 1
    both[10:110, 130:180] = 1
    both[50:60, 95:100] = 2
    rng = np.random.default_rng(3)
    specks = np.where(rng.random((h, w)) < 0.05, rng.integers(1, 4, (h, w)), 0).astype(np.int16)
    return [(two, ['腿', '部位 2']), (two, ['左腿', '右腿']), (crotch, ['腿', '腿 2', '部位 3']),
            (crotch, ['左腿', '右腿', '胯部']), (both, ['腿', '部位 2']), (specks, ['a', 'b', 'c']),
            (specks, ['right', 'b', '左']), (np.zeros((h, w), np.int16), ['腿'])]


@pytest.mark.parametrize('case', range(len(_tilt_cases())))
def test_tilt_sides_are_unchanged(case):
    R, names = _tilt_cases()[case]
    assert np.array_equal(look.tilt_sides(R, names), _old_tilt_sides(R, names))


def test_tilt_sides_of_a_region_in_specks_stays_small():
    h, w = 1920, 1280
    R = np.zeros((h, w), np.int16)
    R[30:h - 30:96, 30:w - 30:64] = 1           # 400 single-pixel pieces of one region
    R[1880:1920, 1220:1280] = 2
    assert cv2.connectedComponents((R == 1).astype(np.uint8), connectivity=8)[0] - 1 == 400
    tracemalloc.start()
    try:
        side = look.tilt_sides(R, ['部位', '部位 2'])
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 64 * 2 ** 20, peak
    assert set(np.unique(side[R > 0])) <= {-1.0, 0.0, 1.0}


# ------------------------------------------------------------------ #17 region labels past 127

def test_region_labels_past_127_survive():
    regions = []
    for k in range(130):
        m = np.zeros((104, 80), bool)
        y, x = 8 * (k // 10), 8 * (k % 10)
        m[y:y + 8, x:x + 8] = True
        regions.append(m)
    REG = gf.label_regions(regions, min_frac=0)
    assert REG.max() == 130 and (REG > 0).all()
    assert all((REG[r] == k).all() for k, r in enumerate(regions, 1))
    s = _flat_scene(104, 80, REG, [f'部位 {k}' for k in range(1, 131)])
    assert s.R.max() == 130 and np.array_equal(s.R, REG)


# ------------------------------------------------------------------ #18 densest point

def test_densest_point_of_a_strip_narrower_than_the_window_is_on_the_strip():
    REG = np.zeros((100, 100), np.int16)
    REG[10:90, 47:53] = 1
    x, y = _flat_scene(100, 100, REG, ['腿']).densest()
    assert REG[y, x] == 1
    assert 48 <= x <= 51 and 20 <= y <= 80


def test_densest_point_is_textured_where_windows_qualify():
    REG = np.zeros((120, 160), np.int16)
    REG[10:110, 20:140] = 1
    s = _flat_scene(120, 160, REG, ['腿'])
    x, y = s.densest()
    assert REG[y, x] == 1

"""Synthetic fixed-sample position gates; no private images or reference paths."""
from dataclasses import replace

import numpy as np
import pytest

from stocking import _glint_position as position, oily


def lighting_grid(kind='single', rows=30):
    q = np.arange(rows, dtype=float)
    axis = np.arange(40) + .5
    if kind == 'single':
        u = np.clip(q / 29., 0, 1)
        centre = 14. + 12. * u * u
        fit = (.18 - .11 * u)[:, None] * np.exp(-.5 * ((axis[None, :] - centre[:, None]) / 3.) ** 2)
    else:
        centre = np.interp(q, [7, 11], [22., 19.])
        amplitude = np.where((q > 7) & (q < 11), .018, .15)
        fit = amplitude[:, None] * np.exp(-((axis[None, :] - centre[:, None]) / 5.) ** 4)
        if kind == 'blank':
            fit[(q > 7) & (q < 11)] = 0.
        if kind == 'double':
            fit = np.tile(.15 * np.exp(-((axis - 12.) / 3.) ** 2) +
                          .15 * np.exp(-((axis - 28.) / 3.) ** 2), (rows, 1))
    return fit, np.ones_like(fit)


def fixture(kind='single', height=600):
    yy, xx = np.mgrid[:height, :240]
    mask = (xx >= 40) & (xx < 200)
    ys, xs = np.nonzero(mask)
    t, across = ys / 20. - .5, 120. - xs
    fit, den = lighting_grid(kind)
    middle = np.tile((-80. + 4. * (np.arange(40) + .5)) / 80., (len(fit), 1))
    tracks = oily._tracks(fit, .3 + fit, den, .001, reach=8, middle=middle)
    kq = np.arange(len(fit))
    drawn = oily._floor_glint(tracks, len(fit), float(height), 80., kq,
                             np.zeros(len(fit)), np.full(len(fit), 80.), -80., 4.,
                             np.ones(len(fit)), t=t)
    coupled = [tr for tr in drawn if not any(tr is original for original in tracks)]
    assert len(coupled) == 1
    tr = coupled[0]
    rows, cells, strength, width, support, uncertainty = tr[:6]
    xy = oily._curve(rows, -80. + 4. * cells, strength, uncertainty, support,
                     t, across, xs, ys, 4., floor=oily.TOL_REL * 80., free=tr[6])
    context = position.PieceEvidence(tuple(tracks), fit, den, .001, middle, 80., 20.,
                                     -80., 4., t, across, xs, ys, mask.shape)
    return context, xy


def test_single_fading_curve_has_nonzero_fixed_id_improvement():
    context, xy = fixture()
    assert len(context.tracks) == 1
    copies = [array.copy() for array in context.tracks[0]]
    edit = position.refine_curve(context, xy)
    assert edit.reason == 'continuous_single_track_follow'
    assert edit.evidence_rows >= 4 and len(edit.sample_ids) > 0
    after = edit.apply(xy)
    assert after.shape == xy.shape and after.dtype == xy.dtype
    untouched = np.ones(len(xy), bool)
    untouched[edit.sample_ids] = False
    assert np.array_equal(after[untouched], xy[untouched])
    rows, cell, st, wd, su, dl = context.tracks[0]
    observed = oily._curve(rows, context.a0 + context.ab * cell, st, dl, su,
                          context.t, context.Ag, context.xs, context.ys, context.ab,
                          floor=oily.TOL_REL * context.hmed)
    y = np.arange(250., 550.)
    desired = np.interp(y, observed[:, 1], observed[:, 0])
    before_error = np.abs(np.interp(y, xy[:, 1], xy[:, 0]) - desired)
    after_error = np.abs(np.interp(y, after[:, 1], after[:, 0]) - desired)
    assert np.median(after_error) < np.median(before_error)
    assert all(np.array_equal(a, b) for a, b in zip(copies, context.tracks[0]))


@pytest.mark.parametrize('gate, reason', [
    ('missing', 'missing_or_competing_raw_peak'),
    ('long_tail', 'long_unobserved_tail'),
    ('cut', 'modified_path_crosses_cut'),
])
def test_single_safety_gates_after_real_position_evidence(gate, reason):
    context, xy = fixture()
    accepted = position.refine_curve(context, xy)
    assert len(context.tracks) == 1 and len(accepted.sample_ids) > 0
    if gate == 'missing':
        den = context.den.copy()
        den[-2] = 0.
        context = replace(context, den=den)
    elif gate == 'long_tail':
        # Leave the original identity and its evidence intact; expose more of the
        # same limb after its last nonpad row, past the fixed 2.5-row budget.
        context, xy = fixture(height=680)
    else:
        cut = np.zeros(context.shape, bool)
        point = accepted.xy[len(accepted.xy) // 2]
        x, y = np.round(point).astype(int)
        cut[y-1:y+2, x-1:x+2] = True
        context = replace(context, cut=cut)
    original = xy.copy()
    edit = position.refine_curve(context, xy)
    assert edit.reason == reason
    assert edit.evidence_rows >= 4
    assert len(edit.sample_ids) == 0
    assert np.array_equal(edit.apply(xy), original)
    assert np.array_equal(xy, original)


def test_two_track_weak_top_is_not_a_noop():
    context, xy = fixture('pair')
    assert len(context.tracks) == 2
    edit = position.refine_curve(context, xy)
    assert edit.reason == 'fixed_sample_supported_candidate'
    assert len(edit.sample_ids) and np.any(edit.apply(xy) != xy)


def borrowed_arrays(context, xy):
    arrays = [xy, context.fit, context.den, context.middle, context.t,
              context.Ag, context.xs, context.ys, context.cut]
    arrays.extend(a for track in context.tracks for a in track)
    return [a for a in arrays if a is not None]


def assert_rejected_unchanged(context, xy, reason):
    arrays = borrowed_arrays(context, xy)
    before = [a.copy() for a in arrays]
    edit = position.refine_curve(context, xy)
    assert edit.reason == reason
    assert len(edit.sample_ids) == 0
    assert edit.apply(xy) is xy
    assert all(np.array_equal(a, b) for a, b in zip(arrays, before))
    return edit


@pytest.mark.parametrize('kind, reason', [
    ('competing', 'competing_reachable_intervals'),
    ('deep_valley', 'interpolated_corridor_photometry'),
    ('blank', 'no_endpoint_connected_corridor'),
])
def test_gap_lighting_gates_preserve_complementary_identities(kind, reason):
    context, xy = fixture('pair')
    accepted = position.refine_curve(context, xy)
    assert accepted.reason == 'fixed_sample_supported_candidate'
    assert len(accepted.sample_ids) > 0
    first, second = sorted(context.tracks, key=lambda tr: tr[0][1])
    q0, q1 = int(first[0][-2]), int(second[0][1])
    assert (q0, q1) == (7, 11)
    assert first[0][-2] < second[0][1]
    fit = context.fit.copy()
    axis = np.arange(fit.shape[1]) + .5
    for q in range(q0 + 1, q1):
        if kind == 'competing':
            centre = np.interp(q, [q0, q1], [22., 19.])
            fit[q] = .018 * (np.exp(-((axis - centre - 2.) / .8) ** 2) +
                             np.exp(-((axis - centre + 2.) / .8) ** 2))
        elif kind == 'deep_valley':
            centre = np.interp(q, [q0, q1], [first[1][-2], second[1][1]])
            fit[q] = .05 * np.exp(-((axis - centre) / .8) ** 2)
        else:
            fit[q] = 0.
    assert np.array_equal(fit[:q0 + 1], context.fit[:q0 + 1])
    assert np.array_equal(fit[q1:], context.fit[q1:])
    changed = replace(context, fit=fit)
    assert changed.tracks is context.tracks and changed.den is context.den
    association = position.select_association(
        changed.tracks, fit, changed.den, changed.noise, changed.middle,
        changed.hmed, changed.wlen)
    assert association['reason'] == reason and not association['accepted']
    sections = [position.near_top_intervals(fit[q], changed.den[q], changed.noise)
                for q in range(q0, q1 + 1)]
    if kind == 'competing':
        assert len(association['endpoints']) == 2
        assert all(len(row) == 2 for row in sections[1:-1])
        # Each entire branch connects to both unchanged endpoint intervals.
        for branch in (0, 1):
            corridor = [sections[0][0], *(row[branch] for row in sections[1:-1]),
                        sections[-1][0]]
            assert all(max(a[0] - b[1], b[0] - a[1], 0.) <=
                       position.ASSOCIATION_POLICY.maximum_step_cells
                       for a, b in zip(corridor, corridor[1:]))
    elif kind == 'deep_valley':
        corridor = position.solve_corridor(
            sections, float(first[1][-2]), float(second[1][1]),
            float(first[1][-2] - first[1][-3]), float(second[1][2] - second[1][1]))
        assert corridor['accepted']
        photo = association['photometry']
        assert photo['reason'] == 'unsupported_or_deep_valley'
        assert photo['minimum_support'] == 1.
        assert photo['maximum_deficit_noise'] > position.ASSOCIATION_POLICY.maximum_deficit_noise
    else:
        assert len(association['endpoints']) == 2
        assert all(not row for row in sections[1:-1])
    assert_rejected_unchanged(changed, xy, reason)


def test_local_longitudinal_fold_reaches_screen_mapping_gate():
    context, xy = fixture()
    accepted = position.refine_curve(context, xy)
    assert accepted.reason == 'continuous_single_track_follow'
    assert len(accepted.sample_ids) > 0
    checks = position.evidence_for_track(
        context.tracks[0], context.fit, context.den, context.noise, {})
    assert len(checks) == accepted.evidence_rows >= 4
    t = context.t.copy()
    fold = context.ys == 400
    t[fold] -= .2
    assert np.array_equal(t[~fold], context.t[~fold])
    changed = replace(context, t=t)
    assert changed.tracks is context.tracks and changed.fit is context.fit
    mask, qmap, _ = position._fields(changed)
    support = position._sample_exact(mask, xy)
    q = position._sample_exact(qmap, xy) / np.maximum(support, 1e-8)
    ids = np.flatnonzero((support > position.FOLLOW_POLICY.mask_support) &
                         (q >= checks[0]['q']))
    assert len(ids) >= 3 and np.all(np.diff(ids) == 1)
    assert np.any(np.diff(q[ids]) < -position.FOLLOW_POLICY.monotonic_tolerance)
    with pytest.raises(position._PositionRejected, match='^nonmonotone_screen_mapping$'):
        position.mapped(xy, mask, qmap, checks[0]['q'])
    edit = assert_rejected_unchanged(changed, xy, 'nonmonotone_screen_mapping')
    assert edit.evidence_rows == len(checks)


@pytest.mark.parametrize('site', [
    'single_curve', 'pair_curve', 'single_sampler', 'single_linear_solve',
    'pair_spline', 'boundary_mapping',
])
@pytest.mark.parametrize('expected_rejection', [False, True])
def test_only_expected_position_rejections_are_caught(monkeypatch, site, expected_rejection):
    kind = 'single' if site.startswith('single') else 'pair'
    context, xy = fixture(kind)
    assert len(position.refine_curve(context, xy).sample_ids) > 0
    arrays = borrowed_arrays(context, xy)
    before = [a.copy() for a in arrays]
    error = (position._PositionRejected('injected_expected_rejection') if expected_rejection
             else ValueError('injected_internal_value_error'))
    calls = []
    original_parameter = position.parameter

    def fail(*args, **kwargs):
        calls.append(1)
        if site == 'boundary_mapping' and len(calls) < 3:
            return original_parameter(*args, **kwargs)
        raise error

    if site.endswith('_curve'):
        monkeypatch.setattr(oily, '_curve', fail)
    elif site == 'single_sampler':
        monkeypatch.setattr(position, 'map_coordinates', fail)
    elif site == 'single_linear_solve':
        monkeypatch.setattr(position.np.linalg, 'solve', fail)
    elif site == 'pair_spline':
        monkeypatch.setattr(position, 'CubicHermiteSpline', fail)
    else:
        monkeypatch.setattr(position, 'parameter', fail)
    if expected_rejection:
        reason = ('no_supported_transition_extent' if site == 'boundary_mapping'
                  else str(error))
        assert_rejected_unchanged(context, xy, reason)
    else:
        with pytest.raises(ValueError, match='^injected_internal_value_error$') as caught:
            position.refine_curve(context, xy)
        assert caught.value is error
    assert len(calls) == (3 if site == 'boundary_mapping' else 1)
    assert all(np.array_equal(a, b) for a, b in zip(arrays, before))


def test_linked_and_unseen_identities_remain_unchanged():
    context, xy = fixture()
    assert position.refine_curve(replace(context, linked=True), xy).reason == 'linked_piece_preserved'
    track = [a.copy() for a in context.tracks[0]]
    track[4][-3] = 0.
    edit = position.refine_curve(replace(context, tracks=(tuple(track),)), xy)
    assert edit.reason == 'original_identity_contains_unseen_rows'
    assert len(edit.sample_ids) == 0


def scene_fixture(monkeypatch, kind='single', height=600):
    from stocking import look
    yy, xx = np.mgrid[:height, :240]
    mask = (xx >= 40) & (xx < 200)
    region = mask.astype(np.int32)
    alpha = mask.astype(np.float32)
    across = np.where(mask, 120. - xx, 0.)
    along = np.where(mask, yy.astype(float), 0.)
    src = np.full((height, 240, 3), 80, np.uint8)
    fit, den = lighting_grid(kind)

    def lighting(*args):
        return fit.copy(), .3 + fit, den.copy(), 20., 0., -80., 4., .001

    monkeypatch.setattr(oily, '_lighting', lighting)
    params = look.clean_params(dict(look.DEFAULTS, style='oily', particle_on=True,
                                    strength_auto=False, strength=100.))
    return lambda: look.Scene(src, region, along, across, mask, alpha, ['synthetic']), params


@pytest.mark.parametrize('gate, reason', [
    ('missing', 'missing_or_competing_raw_peak'),
    ('long_tail', 'long_unobserved_tail'),
    ('cut', 'modified_path_crosses_cut'),
])
def test_rejected_single_edit_keeps_all_maps_and_full_renders(monkeypatch, gate, reason):
    factory, params = scene_fixture(monkeypatch, height=680 if gate == 'long_tail' else 600)
    refine = position.refine_curve
    calls = []

    def guarded(context, xy):
        assert len(context.tracks) == 1
        if gate != 'long_tail':
            positive = refine(context, xy)
            assert positive.evidence_rows >= 4 and len(positive.sample_ids)
        if gate == 'missing':
            den = context.den.copy()
            den[-2] = 0.
            context = replace(context, den=den)
        elif gate == 'cut':
            # Exercise the actual cut raster at the post-topology seam, rather
            # than letting topology split the identity before this gate runs.
            cut = np.zeros(context.shape, bool)
            x, y = np.round(positive.xy[len(positive.xy) // 2]).astype(int)
            cut[y-1:y+2, x-1:x+2] = True
            context = replace(context, cut=cut)
        answer = refine(context, xy)
        calls.append(answer)
        return answer

    monkeypatch.setattr(position, 'refine_curve', guarded)
    candidate = factory()
    maps = candidate.oily_maps()
    assert len(calls) == 1 and calls[0].reason == reason and calls[0].evidence_rows >= 4
    monkeypatch.setattr(position, 'refine_curve', lambda context, xy: position.unchanged(xy, 'baseline'))
    baseline = factory()
    original = baseline.oily_maps()
    assert len(maps) == 7
    for a, b in zip(maps, original):
        assert a.dtype == np.float32 and a.shape == candidate.R.shape and np.isfinite(a).all()
        assert np.array_equal(a, b)
    for particles in (False, True):
        settings = dict(params, particle_on=particles)
        actual, _ = candidate.render(settings)
        expected, _ = baseline.render(settings)
        assert np.array_equal(actual, expected)


@pytest.mark.parametrize('kind', ['single', 'pair'])
def test_positive_production_maps_cache_particles_and_crops(monkeypatch, kind):
    factory, params = scene_fixture(monkeypatch, kind)
    refine = position.refine_curve
    calls = []

    def capture(context, xy):
        before = [[a.copy() for a in track] for track in context.tracks]
        answer = refine(context, xy)
        assert all(np.array_equal(a, b) for tr, old in zip(context.tracks, before) for a, b in zip(tr, old))
        calls.append(answer)
        return answer

    monkeypatch.setattr(position, 'refine_curve', capture)
    scene = factory()
    maps = scene.oily_maps()
    assert len(calls) == 1 and len(calls[0].sample_ids) > 0
    assert scene.oily_maps() is maps
    scene.particle_maps()
    assert len(calls) == 1 and scene.oily_maps() is maps
    monkeypatch.setattr(position, 'refine_curve', lambda context, xy: position.unchanged(xy, 'baseline'))
    baseline = factory().oily_maps()
    assert any(np.any(a != b) for a, b in zip(maps, baseline))
    assert all(np.array_equal(maps[i], baseline[i]) for i in (0, 4, 6))
    for particles in (False, True):
        settings = dict(params, particle_on=particles)
        full, _ = scene.render(settings)
        crop, _ = scene.render(settings, (30, 50, 210, 550))
        assert np.array_equal(crop, full[50:550, 30:210])
    assert len(calls) == 1


def test_contexts_can_be_refined_concurrently_without_cross_talk():
    from concurrent.futures import ThreadPoolExecutor
    inputs = [fixture('single'), fixture('pair'), fixture('single', height=680)]
    expected = [position.refine_curve(context, xy) for context, xy in inputs]
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda item: position.refine_curve(*item), inputs * 2))
    for result, reference in zip(results, expected * 2):
        assert result.reason == reference.reason
        assert np.array_equal(result.sample_ids, reference.sample_ids)
        assert np.array_equal(result.xy, reference.xy)

"""Absorption-only correction: the shared normal and seven original maps stay intact."""
from concurrent.futures import ThreadPoolExecutor
import threading

import numpy as np
import pytest

from stocking import look, oily
from stocking._oily_absorption import absorption_facing


def test_supported_interior_repairs_only_the_absorption_context():
    yy, xx = np.mgrid[:600, :500].astype(float)
    half = 80 + 120 * np.exp(-((yy - 300) / 8) ** 2)
    region = np.abs(xx - 250) < half
    src = np.full((*region.shape, 3), 45, np.uint8)
    R = region.astype(np.int16)
    alpha = region.astype(np.float32)
    A, V = 250 - xx, yy
    original = oily.oily_maps(src, R, alpha, A, V, REG=R)
    context = oily.oily_maps(src, R, alpha, A, V, REG=R, with_absorption=True)
    assert len(context.maps) == 7
    for before, after in zip(original, context.maps):
        np.testing.assert_array_equal(before, after)
    assert original[6][300, 395] > .95
    assert original[4][300, 395] == 0
    assert context.absorption_facing[300, 395] > .45
    assert np.all(context.absorption_facing >= original[4])
    assert not context.absorption_facing.flags.writeable


def renderer_fixture():
    rng = np.random.default_rng(20261031)
    shape = (19, 23)
    R = np.ones(shape, np.int16)
    V, A = np.indices(shape, dtype=np.float32)
    src = rng.integers(10, 250, (*shape, 3), dtype=np.uint8)
    alpha = rng.random(shape, dtype=np.float32)
    maps = [rng.random(shape, dtype=np.float32) for _ in range(7)]
    maps[0] = maps[0] * 2 - 1
    noise = (rng.random(shape, dtype=np.float32), rng.random((*shape, 3), dtype=np.float32))
    return [src, R, V, A, alpha, look.geometry(100, shape[1], shape[0]), 1., *maps], noise


def test_renderer_accepts_an_absorption_field_without_replacing_facing():
    args, noise = renderer_fixture()
    original = oily.render_oily(*args, noise=noise)
    same, before = oily.render_oily(*args, noise=noise, absorption_facing=args[11], diagnostic=True)
    np.testing.assert_array_equal(original, same)
    corrected, after = oily.render_oily(*args, noise=noise,
        absorption_facing=np.maximum(args[11], .8), diagnostic=True)
    assert np.all(after['absorption_factor'] >= before['absorption_factor'])
    assert np.any(after['absorption_factor'] < 1)
    assert np.any(after['preclip_BGR'] > before['preclip_BGR'])
    assert np.any(corrected != original)


def scene_fixture(widen=True):
    yy, xx = np.mgrid[:600, :500].astype(float)
    half = 80 + (120 * np.exp(-((yy - 300) / 8) ** 2) if widen else 0)
    region = np.abs(xx - 250) < half
    src = np.full((*region.shape, 3), 45, np.uint8)
    return look.Scene(src, region.astype(np.int16), yy, 250 - xx,
                      region, region.astype(np.float32), ['stocking'])


def test_scene_uses_cached_full_context_for_margined_crops():
    scene = scene_fixture()
    context = scene.oily_context()
    assert scene.oily_context() is context
    assert scene.oily_maps() is context.maps
    q = dict(style='oily', strength=100, strength_auto=False)
    actual, _ = scene.render(q)
    noise = scene.randoms('grain')[:2]
    expected = oily.render_oily(scene.src, scene.R, scene.V, scene.A, scene.alpha,
        look.geometry(100, scene.w, scene.h), 1., *context.maps, noise=noise,
        absorption_facing=context.absorption_facing)
    np.testing.assert_array_equal(actual, expected)
    for rect in ((0, 0, 99, 115), (330, 270, 430, 340), (420, 520, 500, 600)):
        x0, y0, x1, y1 = rect
        crop, _ = scene.render(q, rect)
        np.testing.assert_array_equal(crop, actual[y0:y1, x0:x1])


def sections(kind='wide'):
    v, a = np.meshgrid(np.arange(300) * 2., np.linspace(-1, 1, 161), indexing='ij')
    half = 80 + 120 * np.exp(-((v - 300) / 8) ** 2)
    centre = np.zeros_like(v)
    if kind in ('straight', 'bent'):
        half[:] = 80
    if kind == 'bent':
        centre = 15 * np.sin(v / 90)
    if kind == 'knee':
        half = 80 - 35 * np.exp(-((v - 300) / 15) ** 2)
    return v.ravel(), (centre + a * half).ravel()


def section_result(v, a, hidden=None, scale=1.):
    hidden = np.zeros(len(v), bool) if hidden is None else hidden
    frame = oily._frame(v, a, hidden, scale)
    saved = [x.copy() if isinstance(x, np.ndarray) else x for x in frame]
    result = absorption_facing(v, a, hidden, scale, frame)
    for before, after in zip(saved, frame):
        np.testing.assert_array_equal(before, after)
    k, c, h, hf, hmed, tilt, whole, trust = frame
    u = np.clip((a - c[k]) / hf[k], -1, 1)
    original = np.sqrt(1 - u * u) * np.cos(tilt[k])
    assert np.isfinite(result).all()
    assert np.all(result >= original)
    assert np.all(result <= 1)
    return result, original


@pytest.mark.parametrize('kind', ['straight', 'bent'])
def test_normal_straight_and_bent_sections_are_exactly_unchanged(kind):
    corrected, original = section_result(*sections(kind))
    np.testing.assert_array_equal(corrected, original)


def test_true_narrowing_adds_no_absorption_and_preserves_existing_edge():
    v, a = sections('knee')
    corrected, original = section_result(v, a)
    edge = (v == 300) & (np.abs(a) > 40)
    assert edge.any()
    np.testing.assert_array_equal(corrected[edge], original[edge])
    # This relative contract does not repair or replace the old absolute < .55 gate.
    assert np.max(original[edge]) > .55


@pytest.mark.parametrize('sides', ['one', 'both'])
def test_hidden_section_edges_do_not_gain_corrections(sides):
    v, a = sections()
    half = 80 + 120 * np.exp(-((v - 300) / 8) ** 2)
    hidden = a < -.94 * half
    if sides == 'both':
        hidden |= a > .94 * half
    corrected, original = section_result(v, a, hidden)
    np.testing.assert_array_equal(corrected, original)


@pytest.mark.parametrize('kind', ['sparse', 'disconnected', 'isolated'])
def test_insufficient_section_evidence_keeps_original_absorption(kind):
    v, a = sections('straight' if kind == 'isolated' else 'wide')
    if kind == 'isolated':
        a[v == 300] *= 2.5
        target = v == 300
    else:
        keep = (np.arange(len(v)) % 161 < 8) if kind == 'sparse' else (
            np.abs(a) > .65 * (80 + 120 * np.exp(-((v - 300) / 8) ** 2)))
        v, a = v[keep], a[keep]
        target = np.ones(len(v), bool)
    corrected, original = section_result(v, a)
    np.testing.assert_array_equal(corrected[target], original[target])


@pytest.mark.parametrize('scale', [1., 2., 4.])
def test_absorption_is_translation_and_scale_consistent(scale):
    v, a = sections()
    expected, original = section_result(v, a)
    assert np.any(expected > original)
    actual, _ = section_result(v * scale + 117.25, a * scale - 212.5, scale=scale)
    np.testing.assert_allclose(actual ** 2, expected ** 2, atol=1e-12, rtol=0)


@pytest.mark.parametrize('dtype', [np.float32, np.float64])
@pytest.mark.parametrize('strength', [0., .5, 1., 1.5, 2.5])
@pytest.mark.parametrize('fade', [False, True])
def test_optional_or_identical_absorption_is_an_internal_and_pixel_noop(strength, fade, dtype):
    args, noise = renderer_fixture()
    args[6] = strength
    a, ad = oily.render_oily(*args, noise=noise, fade=fade, diagnostic=True)
    b, bd = oily.render_oily(*args, noise=noise, fade=fade, diagnostic=True,
                             absorption_facing=args[11].astype(dtype))
    np.testing.assert_array_equal(a, b)
    for key in ad:
        np.testing.assert_array_equal(ad[key], bd[key], err_msg=key)


@pytest.mark.parametrize('inactive', ['zone', 'strength', 'alpha'])
def test_inactive_absorption_does_not_change_factor_preclip_or_pixels(inactive):
    args, noise = renderer_fixture()
    if inactive == 'strength':
        args[6] = 0.
    else:
        args[13 if inactive == 'zone' else 4][:] = 0
    a, ad = oily.render_oily(*args, noise=noise, diagnostic=True)
    b, bd = oily.render_oily(*args, noise=noise, diagnostic=True, absorption_facing=np.ones_like(args[11]))
    np.testing.assert_array_equal(a, b)
    for key in ('absorption_factor', 'preclip_BGR', 'pre_absorption', 'see', 'bright', 'lift'):
        np.testing.assert_array_equal(ad[key], bd[key], err_msg=key)


@pytest.mark.parametrize('strength', [.5, 1., 1.5])
def test_low_nonzero_zone_retains_positive_absorption_at_each_strength(strength):
    args, noise = renderer_fixture()
    args[0][:] = 220
    args[4][:] = 1
    args[6] = strength
    args[11][:] = .4
    args[13][:] = .01
    _, before = oily.render_oily(*args, noise=noise, diagnostic=True)
    _, after = oily.render_oily(*args, noise=noise, diagnostic=True, absorption_facing=np.full_like(args[11], .7))
    assert np.all(after['absorption_factor'] < 1)
    assert np.all(after['absorption_factor'] > before['absorption_factor'])
    for key in ('pre_absorption', 'see', 'bright', 'lift'):
        np.testing.assert_array_equal(before[key], after[key], err_msg=key)


@pytest.mark.parametrize('dtype', [np.float32, np.float64])
@pytest.mark.parametrize('invalid', ['shape', 'nan', 'positive_inf', 'negative_inf'])
def test_absorption_field_rejects_invalid_crop_or_nonfinite_values(invalid, dtype):
    args, noise = renderer_fixture()
    field = args[11].astype(dtype)
    if invalid == 'shape':
        field = field[:-1]
    else:
        field[0, 0] = {'nan': np.nan, 'positive_inf': np.inf, 'negative_inf': -np.inf}[invalid]
    with pytest.raises(ValueError, match='absorption_facing'):
        oily.render_oily(*args, noise=noise, absorption_facing=field)


def test_finite_float64_field_is_not_overflowed_by_a_narrowing_conversion():
    args, noise = renderer_fixture()
    field = args[11].astype(np.float64)
    field[0, 0], field[0, 1] = np.finfo(np.float64).max, -np.finfo(np.float64).max
    with np.errstate(over='raise', invalid='raise'):
        image, values = oily.render_oily(*args, noise=noise, absorption_facing=field, diagnostic=True)
    assert np.isfinite(values['absorption_factor']).all()
    assert np.isfinite(values['preclip_BGR']).all()
    assert image.dtype == np.uint8


def test_scene_contexts_are_atomic_under_concurrent_first_use_and_instance_local():
    scenes = [scene_fixture(True), scene_fixture(False)]
    barrier = threading.Barrier(8)
    def get_context(index):
        barrier.wait(timeout=20)
        scene = scenes[index % 2]
        context = scene.oily_context()
        scene.particle_maps()
        image, _ = scene.render(dict(style='oily', strength=100, strength_auto=False))
        return index % 2, context, image
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(get_context, i) for i in range(8)]
        results = [future.result(timeout=60) for future in futures]
    for index, context, image in results:
        assert context is scenes[index].oily_context()
        expected, _ = scenes[index].render(dict(style='oily', strength=100, strength_auto=False))
        np.testing.assert_array_equal(image, expected)
    a, b = (scene.oily_context() for scene in scenes)
    assert a is not b
    assert not np.shares_memory(a.absorption_facing, b.absorption_facing)
    assert np.any(a.absorption_facing != b.absorption_facing)
    assert not a.absorption_facing.flags.writeable
    for scene in scenes:
        fresh = oily.oily_maps(scene.src, scene.R, scene.alpha, scene.A, scene.V,
            float(np.sqrt(scene.R.size / look.REF_AREA)), REG=scene.REG, with_absorption=True)
        np.testing.assert_array_equal(scene.oily_context().absorption_facing, fresh.absorption_facing)
        for cached, independent in zip(scene.oily_maps(), fresh.maps):
            np.testing.assert_array_equal(cached, independent)


def count_oily_work(monkeypatch):
    counts = dict(maps=0, frame=0, absorption=0, allocation=0)
    lock = threading.Lock()
    def watch(owner, name, key):
        original = getattr(owner, name)
        def wrapped(*args, **kwargs):
            with lock:
                counts[key] += 1
            return original(*args, **kwargs)
        monkeypatch.setattr(owner, name, wrapped)
    watch(oily, 'oily_maps', 'maps')
    watch(oily, '_frame', 'frame')
    watch(oily, '_absorption_facing', 'absorption')
    watch(oily._DeferredAbsorption, '__call__', 'allocation')
    return counts


@pytest.mark.parametrize('oil_first', [False, True])
def test_particles_and_oily_share_seven_maps_but_only_oily_allocates_absorption(monkeypatch, oil_first):
    scene = scene_fixture()
    counts = count_oily_work(monkeypatch)
    nonoil = dict(style='grain', strength=100, strength_auto=False, particle_on=True)
    oil = dict(nonoil, style='oily')
    first = oil if oil_first else nonoil
    first_image, _ = scene.render(first)
    context = scene.oily_context()
    maps = scene.oily_maps()
    frame_count = counts['frame']
    assert counts['maps'] == 1
    assert counts['allocation'] == int(oil_first)
    assert (context._absorption_facing is not None) == oil_first
    if not oil_first:
        assert counts['absorption'] == 0
        plan = context._absorption_factory
        assert 0 < plan.retained_nbytes < 4 * scene.R.size
        assert plan.A is scene.A and plan.V is scene.V
        for pieces in plan.frames.values():
            for _, packed, bands in pieces:
                assert not packed.flags.writeable
                assert all(not v.flags.writeable for v in bands if isinstance(v, np.ndarray))
    second_image, _ = scene.render(nonoil if oil_first else oil)
    assert counts['maps'] == 1 and counts['frame'] == frame_count
    assert counts['allocation'] == 1 and counts['absorption'] > 0
    assert context._absorption_factory is None
    assert scene.oily_maps() is maps
    assert all(not field.flags.writeable for field in (*maps, context.absorption_facing))
    repeated, _ = scene.render(first)
    np.testing.assert_array_equal(repeated, first_image)
    assert counts['allocation'] == 1
    reverse = scene_fixture()
    reverse_second, _ = reverse.render(nonoil if oil_first else oil)
    reverse_first, _ = reverse.render(first)
    np.testing.assert_array_equal(second_image, reverse_second)
    np.testing.assert_array_equal(first_image, reverse_first)


@pytest.mark.parametrize('active', [False, True])
@pytest.mark.parametrize('locked', [False, True])
def test_only_a_drawn_oily_layer_requests_absorption(monkeypatch, active, locked):
    scene = scene_fixture()
    counts = count_oily_work(monkeypatch)
    q = dict(style='grain', strength=100, strength_auto=False, particle_on=True,
             weight=60, amount=60, lock_total=locked,
             layers=[dict(style='oily', strength=100, strength_auto=False,
                          weight=40 if active else 0, amount=40 if active else 0)])
    full, _ = scene.render(q)
    assert counts['maps'] == 1
    assert counts['allocation'] == int(active)
    assert (counts['absorption'] > 0) == active
    rect = (330, 270, 430, 340)
    crop, _ = scene.render(q, rect)
    np.testing.assert_array_equal(crop, full[270:340, 330:430])
    assert counts['allocation'] == int(active)


def test_mixed_concurrent_cold_calls_compute_each_instance_once(monkeypatch):
    scenes = [scene_fixture(True), scene_fixture(False)]
    counts = count_oily_work(monkeypatch)
    barrier = threading.Barrier(8)
    def render(index):
        barrier.wait(timeout=20)
        scene = scenes[index % 2]
        q = dict(style='oily' if index % 4 < 2 else 'grain', strength=100,
                 strength_auto=False, particle_on=True)
        image, _ = scene.render(q)
        return index % 2, q, image
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(render, index) for index in range(8)]
        results = [future.result(timeout=60) for future in futures]
    assert counts['maps'] == 2 and counts['allocation'] == 2
    for index, q, image in results:
        expected, _ = scenes[index].render(q)
        np.testing.assert_array_equal(image, expected)
    a, b = [scene.oily_context() for scene in scenes]
    assert a is not b and a.maps is not b.maps
    assert not np.shares_memory(a.absorption_facing, b.absorption_facing)
    assert np.any(a.absorption_facing != b.absorption_facing)
    assert counts['maps'] == 2 and counts['allocation'] == 2


def test_failed_absorption_discards_partial_field_and_reuses_complete_maps(monkeypatch):
    source = scene_fixture()
    regions = source.REG.copy()
    regions[:, 250:] *= 2
    scene = look.Scene(source.src[..., ::-1], regions, source.V, source.A,
                       regions > 0, source.alpha, ['left', 'right'])
    counts = count_oily_work(monkeypatch)
    scene.render(dict(style='grain', strength_auto=False, particle_on=True))
    context = scene.oily_context()
    maps, plan = context.maps, context._absorption_factory
    frame_count = counts['frame']
    original = oily._absorption_facing
    calls = 0
    def fail_second_piece(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = original(*args, **kwargs)
        if calls == 2:
            raise RuntimeError('injected absorption failure')
        return result
    monkeypatch.setattr(oily, '_absorption_facing', fail_second_piece)
    q = dict(style='oily', strength=100, strength_auto=False, particle_on=True)
    with pytest.raises(RuntimeError, match='injected absorption failure'):
        scene.render(q)
    assert context._absorption_facing is None
    assert context._absorption_factory is plan
    assert scene.oily_maps() is maps
    image, _ = scene.render(q)
    assert counts['maps'] == 1 and counts['frame'] == frame_count
    assert counts['allocation'] == 2
    assert context._absorption_factory is None
    fresh = oily.oily_maps(scene.src, scene.R, scene.alpha, scene.A, scene.V,
        float(np.sqrt(scene.R.size / look.REF_AREA)), REG=scene.REG, with_absorption=True)
    np.testing.assert_array_equal(context.absorption_facing, fresh.absorption_facing)
    expected, _ = scene.render(q)
    np.testing.assert_array_equal(image, expected)


def test_failed_seven_maps_are_not_published_and_can_retry(monkeypatch):
    scene = scene_fixture()
    original = oily.oily_maps
    calls = 0
    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        context = original(*args, **kwargs)
        if calls == 1:
            raise RuntimeError('injected map failure')
        return context
    monkeypatch.setattr(oily, 'oily_maps', fail_once)
    with pytest.raises(RuntimeError, match='injected map failure'):
        scene.oily_maps()
    assert 'oily_context' not in scene._stretch
    maps = scene.oily_maps()
    assert calls == 2 and maps is scene.oily_context().maps
    assert scene.oily_context()._absorption_facing is None


def test_public_seven_map_path_does_not_allocate_or_retain_absorption(monkeypatch):
    scene = scene_fixture()
    counts = count_oily_work(monkeypatch)
    def unexpected(*args, **kwargs):
        pytest.fail('seven-map-only call must not retain deferred evidence')
    monkeypatch.setattr(oily._DeferredAbsorption, '__init__', unexpected)
    maps = oily.oily_maps(scene.src, scene.R, scene.alpha, scene.A, scene.V, REG=scene.REG)
    assert isinstance(maps, tuple) and len(maps) == 7
    assert counts['absorption'] == counts['allocation'] == 0

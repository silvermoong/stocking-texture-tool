"""Export: one file of the kind asked for. The finished picture is the render; the stockings-only PNG laid over the
art gives it back and holds nothing else; the guides PSD reopens as it was written; the user's own file is never
written."""
import hashlib
import os
import shutil

import cv2
import numpy as np
import pytest
from psd_tools import PSDImage

from stocking import export, look, trace
from stocking.document import Document

from sample_data import PNG, PSD, needed, require

# a 隔开 line that curves right round (past a half turn, so it doubles back), as one following an outline does
_t = np.linspace(-2.0, 2.0, 120)
ARC = np.stack([420 + 260 * np.sin(_t), 420 + 180 * np.cos(_t)], 1)


@pytest.fixture(scope='module')
def solved():
    require()
    d = Document.open(PSD)
    d.add_divider(ARC.ravel().tolist())
    d.sparkle = np.zeros((d.h, d.w), np.uint8)
    d.sparkle[300:340, 500:620] = 255
    assert d.wait_idle(120)
    yield d
    d.close()


def _read_png(p):
    return cv2.cvtColor(cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)


def _seg_dist(P, Q):
    """Largest distance from the points P to the polyline Q."""
    a, b = Q[:-1], Q[1:]
    ab = b - a
    t = np.clip(((P[:, None] - a[None]) * ab[None]).sum(-1) / np.maximum((ab ** 2).sum(-1), 1e-9)[None], 0, 1)
    return np.hypot(*(P[:, None] - (a[None] + t[..., None] * ab[None])).transpose(2, 0, 1)).min(1).max()


def test_base_names_and_the_source_is_never_a_target(tmp_path):
    assert export.base_name('sample.png') == 'sample'
    assert export.base_name('x-丝袜引导.psd') == 'x' and export.base_name('x-丝袜成品.png') == 'x'
    assert export.base_name('x-仅丝袜.png') == 'x' and export.base_name('x-丝袜纹理.png') == 'x'
    assert export.base_name('-丝袜引导.psd') == '-丝袜引导'
    src = str(tmp_path / 'x-丝袜引导.psd')
    assert [os.path.basename(export.target(str(tmp_path), 'x-丝袜引导.psd', k, source=src)) for k in export.KINDS] == \
        ['x-丝袜成品.png', 'x-仅丝袜.png', 'x-丝袜引导 (2).psd']


def _read_rgba(p):
    return cv2.cvtColor(cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_UNCHANGED), cv2.COLOR_BGRA2RGBA)


@pytest.mark.parametrize('style', ['knit', 'lines'])
def test_the_finished_picture_and_the_stockings_alone(solved, tmp_path, style):
    """Each export writes its one file. 仅丝袜 laid over the art gives the finished picture; it is opaque on the
    stockings, and transparent (and empty) wherever the picture is the art's own."""
    s = look.scene_from_doc(solved, disparity=lambda: None)
    q = look.clean_params({'style': style, 'sparkle_depth': 0, 'sparkle_bright': 100})
    png = _read_png(export.export(solved, s, q, str(tmp_path), 'png')['file'])
    assert sorted(os.listdir(tmp_path)) == ['sample-guides-丝袜成品.png']
    assert np.array_equal(png, cv2.cvtColor(s.render(q)[0], cv2.COLOR_BGR2RGB))
    assert (png != solved.art).any()
    cut = _read_rgba(export.export(solved, s, q, str(tmp_path), 'cutout')['file'])
    assert sorted(os.listdir(tmp_path)) == ['sample-guides-丝袜成品.png', 'sample-guides-仅丝袜.png']
    a = cut[..., 3:].astype(float) / 255
    over = cut[..., :3] * a + solved.art * (1 - a)
    assert np.abs(over - png).max() <= 1
    alpha = solved.coverage()[1]
    assert (cut[..., 3][alpha > 0.999] == 255).all()
    rest = (alpha == 0) & (png == solved.art).all(2)
    assert (cut[rest] == 0).all()


def test_guides_psd_reopens_as_written(solved, tmp_path):
    res = export.export(solved, None, None, str(tmp_path), 'guides')
    assert sorted(os.listdir(tmp_path)) == ['sample-guides-丝袜引导.psd']
    d2 = Document.open(res['file'])
    try:
        assert np.array_equal(d2.art, solved.art)
        assert [r.name for r in d2.regions] == [r.name for r in solved.regions]
        assert all(np.array_equal(a.mask, b.mask) for a, b in zip(solved.regions, d2.regions))
        assert len(d2.strokes) == len(solved.strokes)
        assert np.array_equal(d2.sparkle, solved.sparkle)
        assert len(d2.dividers) == 1
        Q = d2.dividers[0].pts
        assert _seg_dist(_dense(Q, trim=6), ARC) < 1.5           # follows the curve, nowhere folded across it
        assert _seg_dist(ARC[[0, -1]], Q) < 3                     # end to end
    finally:
        d2.close()


@needed
def test_export_never_writes_the_source(tmp_path):
    src = tmp_path / 'x-丝袜引导.psd'
    shutil.copy(PSD, src)
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    d = Document.open(str(src))
    try:
        res = export.export(d, None, None, str(tmp_path), 'guides')
        assert os.path.basename(res['file']) == 'x-丝袜引导 (2).psd'
        assert hashlib.sha256(src.read_bytes()).hexdigest() == before
    finally:
        d.close()


@needed
def test_a_file_in_use_is_reported_and_nothing_half_written(tmp_path):
    d = Document.open(PNG)
    try:
        s = look.scene_from_doc(d, disparity=lambda: None)
        res = export.export(d, s, look.clean_params({}), str(tmp_path))
        before = (tmp_path / 'sample-丝袜成品.png').read_bytes()
        with open(res['file'], 'rb'):                       # held open, as Photoshop or a viewer might
            with pytest.raises(ValueError, match='占用'):
                export.export(d, s, look.clean_params({}), str(tmp_path))
        assert (tmp_path / 'sample-丝袜成品.png').read_bytes() == before
        assert not [n for n in os.listdir(tmp_path) if '导出中' in n]
        with pytest.raises(ValueError, match='文件夹不存在'):
            export.export(d, s, look.clean_params({}), str(tmp_path / 'nope'))
    finally:
        d.close()


def _dense(Q, step=1.0, trim=0.0):
    """Points every `step` px along the polyline Q (a chord cutting across a curve shows up in them), leaving out
    `trim` px at each end."""
    out = [Q[0]]
    for a, b in zip(Q[:-1], Q[1:]):
        n = max(int(np.hypot(*(b - a)) / step), 1)
        out += [a + (b - a) * k / n for k in range(1, n + 1)]
    out = np.asarray(out)
    s = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(out, axis=0).T))])
    return out[(s >= trim) & (s <= s[-1] - trim)]


def test_trace_follows_curves_end_to_end():
    S = np.stack([60 + np.linspace(0, 300, 300), 200 + 50 * np.sin(np.linspace(0, 2 * np.pi, 300))], 1)
    lines = trace.trace_lines(trace.draw_lines([ARC, S], (700, 800), 3))
    assert len(lines) == 2
    for Q in lines:
        ref = ARC if _seg_dist(Q, ARC) < _seg_dist(Q, S) else S
        assert _seg_dist(_dense(Q, trim=6), ref) < 1.2              # walked in order: no chord across the curve
        assert _seg_dist(ref[[0, -1]], Q) < 3                       # from one end to the other

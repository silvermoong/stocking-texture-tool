import cv2
import numpy as np
import pytest

from stocking import coverage
from stocking import guide_fields as gf
from stocking import psd_io
from stocking.document import Document

from sample_data import PSD, needed, require


@pytest.fixture(scope='module')
def fixture():
    require()
    art, regions, strokes, _ = psd_io.read_guides(PSD)
    return art, list(regions.values())


def test_coverage_matches_reference_inline_code(fixture):
    art, masks = fixture
    REG = gf.label_regions(masks)
    stock, alpha = coverage.stocking_coverage(coverage.lab_of(art), REG)
    # the reference's code, as it was in verify.py
    src = cv2.cvtColor(art, cv2.COLOR_RGB2BGR)
    lab = cv2.cvtColor(src, cv2.COLOR_BGR2LAB).astype(np.float32)
    ab = lab[..., 1:][REG > 0]
    med = np.median(ab, 0)
    mad = np.median(np.abs(ab - med), 0) + 1.0
    z = np.sqrt((((lab[..., 1:] - med) / mad) ** 2).sum(-1))
    ref = (REG > 0) & (z < 6.0)
    ref = cv2.morphologyEx(ref.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
    assert np.array_equal(stock, ref)
    assert 0.80 < stock.sum() / (REG > 0).sum() < 0.99      # trims and gloves go, the stocking stays


@needed
def test_document_coverage_is_cached_until_a_mask_changes():
    d = Document.open(PSD)
    try:
        c1 = d.coverage()
        assert d.coverage() is c1
        d.add_stroke([(300, 200), (600, 220)])             # strokes do not change coverage
        assert d.coverage() is c1
        d.paint(d.regions[0].id, [(10, 10)], 4)
        c2 = d.coverage()
        assert c2 is not c1 and c2[3] != c1[3]
        assert c2[3] == d.state()['coverage_v']
    finally:
        d.close()


@needed
def test_sam_click_segments_a_thigh():
    from stocking import sam
    try:
        sam.service.wait_ready(120)
    except RuntimeError as e:
        pytest.skip(f'SAM unavailable: {e}')
    art, regions, _, _ = psd_io.read_guides(PSD)
    left = list(regions.values())[0]
    d = Document.open(PSD)
    try:
        r = d.regions[0]
        d.clear_region(r.id)
        masks, best, scores = sam.service.candidates(d, 500, 400)
        assert len(masks) == 3 and [m.sum() for m in masks] == sorted(m.sum() for m in masks)
        d.segment_click(r.id, 500, 400, False, masks, best)
        iou = (r.mask & left).sum() / (r.mask | left).sum()
        assert iou > 0.6, iou
    finally:
        d.close()


@needed
def test_guides_psd_round_trip(tmp_path):
    d = Document.open(PSD)
    try:
        assert d.wait_idle(60)
        p = str(tmp_path / 'x-丝袜引导.psd')
        psd_io.write_guides(p, d.art, {r.name: r.mask for r in d.regions}, d.stroke_alpha(),
                            {r.name: r.color for r in d.regions})
        d2 = Document.open(p)
        try:
            assert np.array_equal(d.art, d2.art)
            assert [r.name for r in d2.regions] == [r.name for r in d.regions]
            assert all(np.array_equal(a.mask, b.mask) for a, b in zip(d.regions, d2.regions))
            assert len(d2.strokes) == len(d.strokes)
            assert d2.wait_idle(60)
            R1, _, NX1, NY1, _ = d.fields()
            R2, _, NX2, NY2, _ = d2.fields()
            sel = (R1 > 0) & (R1 == R2)
            ang = np.degrees(np.arccos(np.clip(np.abs(NX1[sel] * NX2[sel] + NY1[sel] * NY2[sel]), 0, 1)))
            assert np.median(ang) < 1.0
        finally:
            d2.close()
    finally:
        d.close()

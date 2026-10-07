import cv2
import numpy as np
import pytest

from stocking.document import Document, _clip_polyline

from sample_data import PSD, needed


@pytest.fixture
def doc():
    d = Document.open(PSD)
    assert d.wait_idle(90)
    yield d
    d.close()


def ids(d):
    return {r.name: r.id for r in d.regions}


def course_angles(d, rid, NX0, NY0):
    REG, _, NX, NY, _ = d.fields()
    i = [r.id for r in d.regions].index(rid) + 1
    sel = cv2.erode((REG == i).astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool)
    return np.degrees(np.arccos(np.clip(np.abs(NX[sel] * NX0[sel] + NY[sel] * NY0[sel]), 0, 1)))


@needed
@pytest.mark.parametrize('a, b, limit', [('左腿', '右腿', 3.0), ('右腿', '左腿', 3.0), ('左胸', '右胸', 12.0)])
def test_mirrored_strokes_give_the_drawn_courses(doc, a, b, limit):
    # the spec's measure: thighs within 2.3° (median) of the hand-drawn courses, breasts 11°
    _, _, NX0, NY0, _ = doc.fields()
    made, replaced, fit = doc.mirror_strokes(ids(doc)[a], ids(doc)[b])
    assert made > 0 and replaced > 0 and fit < 20
    assert doc.wait_idle(90)
    assert np.median(course_angles(doc, ids(doc)[b], NX0, NY0)) < limit


@needed
def test_mirror_replaces_the_other_side_only_and_undoes_in_one_step(doc):
    before = {s.id: (s.region, s.pts.copy()) for s in doc.strokes}
    left, right = ids(doc)['左腿'], ids(doc)['右腿']
    made, replaced, _ = doc.mirror_strokes(left, right)
    assert doc.wait_idle(90)
    now = {s.id: s.region for s in doc.strokes}
    kept = {sid for sid, (rid, _) in before.items() if rid != right}
    assert kept <= set(now)                                          # every other region keeps its strokes
    assert not any(before[sid][0] == right for sid in now if sid in before)   # the old right-leg strokes are gone
    new = [s for s in doc.strokes if s.id not in before]
    assert len(new) == made and all(s.region == right for s in new)
    assert doc.undo()
    assert {s.id for s in doc.strokes} == set(before)
    assert all(np.array_equal(s.pts, before[s.id][1]) for s in doc.strokes)
    assert doc.redo() and len(doc.strokes) == len(before) - replaced + made


@needed
def test_mirror_refuses_what_it_cannot_do(doc):
    left = ids(doc)['左腿']
    with pytest.raises(ValueError):
        doc.mirror_strokes(left, left)
    empty = doc.add_region('空')
    with pytest.raises(ValueError):
        doc.mirror_strokes(empty, left)         # nothing painted, no strokes
    with pytest.raises(ValueError):
        doc.mirror_strokes(left, empty)         # nowhere to put them


def test_clip_polyline_keeps_the_runs_inside():
    m = np.zeros((50, 100), bool)
    m[:, 10:40] = True
    m[:, 60:90] = True
    runs = _clip_polyline(np.array([[0.0, 25], [99, 25]]), m)
    assert len(runs) == 2
    for run, (lo, hi) in zip(runs, ((10, 39), (60, 89))):
        assert abs(run[0, 0] - lo) < 1.6 and abs(run[-1, 0] - hi) < 1.6
    assert _clip_polyline(np.array([[12.0, 5], [15, 5]]), m) == []          # shorter than min_len
    assert _clip_polyline(np.array([[5.0, 5], [5, 5]]), m) == []            # a single point

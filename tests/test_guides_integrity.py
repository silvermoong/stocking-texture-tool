"""The guides survive what can go wrong around them: two regions of one name, edits made while a file is written,
a crash while the session is saved, a working file named like the source, layers reaching past the canvas, a long
history, and strokes that belong to no region."""
import hashlib
import json
import os

import numpy as np
import pytest
from PIL import Image
from psd_tools import PSDImage

from stocking import document, export, psd_io, session
from stocking.document import Document

H, W = 40, 60


def _art():
    return np.full((H, W, 3), 90, np.uint8)


def _rect(x0, y0, x1, y1):
    m = np.zeros((H, W), bool)
    m[y0:y1, x0:x1] = True
    return m


def _doc(*regions):
    """A document on plain art with the given (name, mask) regions, as if opened from a file that held them."""
    d = Document(_art(), 'a.png')
    with d.lock:
        for name, mask in regions:
            d._new_region(name, mask)
        d._touch()
    return d


# ---------------------------------------------------------------- #3 one name, one region

def test_region_names_stay_unique():
    d = _doc(('A', _rect(5, 5, 20, 20)), ('B', _rect(30, 5, 50, 20)))
    try:
        a, b = d.regions
        with pytest.raises(ValueError, match='已经有'):
            d.add_region('A')
        with pytest.raises(ValueError, match='已经有'):
            d.rename_region(b.id, 'A')
        d.rename_region(a.id, 'A')                          # its own name: nothing to do
        assert [r.name for r in d.regions] == ['A', 'B'] and not d._undo
    finally:
        d.close()


def test_duplicate_names_from_a_snapshot_or_a_psd_are_numbered_and_both_exported(tmp_path):
    m1, m2 = _rect(5, 5, 20, 20), _rect(30, 5, 50, 30)
    e = Document.from_snapshot(_art(), 'a.png', None, [('A', '#ff0000', m1), ('A', '#00ff00', m2)], [])
    try:
        assert [r.name for r in e.regions] == ['A', 'A 2']
        res = export.export(e, None, None, str(tmp_path / 'g.psd'), 'guides')
        g = psd_io.read_guide_layers(res['file'])
        assert list(g['regions']) == ['A', 'A 2']
        assert np.array_equal(g['regions']['A'], m1) and np.array_equal(g['regions']['A 2'], m2)
    finally:
        e.close()
    p = str(tmp_path / 'two.psd')
    psd_io.write_guides(p, _art(), {'A': m1, 'B': m2}, np.zeros((H, W), np.uint8))
    psd = PSDImage.open(p)
    group = next(L for L in psd if L.is_group())
    next(L for L in group if L.name == 'B').name = 'A'      # as a user might name two layers in Photoshop
    p2 = str(tmp_path / 'same.psd')
    psd.save(p2)
    d = Document.open(p2)
    try:
        assert [r.name for r in d.regions] == ['A', 'A 2']
        assert np.array_equal(d.regions[0].mask, m1) and np.array_equal(d.regions[1].mask, m2)
    finally:
        d.close()


# ---------------------------------------------------------------- #4 edits while the guides are written

def test_guides_export_marks_saved_only_the_state_it_wrote(monkeypatch, tmp_path):
    d = _doc(('A', _rect(5, 5, 50, 35)))
    real = psd_io.write_guides

    def slow(p, *a, **k):
        d.add_stroke([(10, 20), (45, 20)])                  # an edit made while the file is being written
        return real(p, *a, **k)
    monkeypatch.setattr(export.psd_io, 'write_guides', slow)
    try:
        d.paint(d.regions[0].id, [(30, 30)], 3)
        res = export.export(d, None, None, str(tmp_path / 'g.psd'), 'guides')
        d.mark_guides_saved(res['saved'])
        assert psd_io.read_guide_layers(res['file'])['strokes'].max() == 0
        assert d.unsaved_guides()                           # the stroke is in no file
        d.undo()
        assert not d.unsaved_guides()                       # back to what the file holds
    finally:
        d.close()


# ---------------------------------------------------------------- #5 a crash while the session is saved

def test_a_crash_while_saving_the_session_leaves_the_last_one_whole(monkeypatch, tmp_path):
    a = _doc(('A', _rect(5, 5, 20, 20)), ('B', _rect(30, 5, 50, 30)))
    b = _doc(('C', _rect(0, 0, 10, 10)))
    try:
        session.save(a, str(tmp_path))
        real = session._replace

        def crash(path, write):
            if os.path.basename(path) == 'meta.json':
                raise OSError('power cut')
            real(path, write)
        monkeypatch.setattr(session, '_replace', crash)
        with pytest.raises(OSError):
            session.save(b, str(tmp_path))
        monkeypatch.undo()
        e = session.load(str(tmp_path))
        assert e is not None
        try:
            assert [r.name for r in e.regions] == ['A', 'B']
            assert all(np.array_equal(x.mask, y.mask) for x, y in zip(a.regions, e.regions))
        finally:
            e.close()
        session.save(b, str(tmp_path))                      # the next save clears the earlier saves' files away
        assert len([n for n in os.listdir(tmp_path) if n.startswith('masks')]) == 1
        e = session.load(str(tmp_path))
        try:
            assert [r.name for r in e.regions] == ['C']
        finally:
            e.close()
    finally:
        a.close()
        b.close()


def test_a_session_of_the_old_layout_still_loads(tmp_path):
    a = _doc(('A', _rect(5, 5, 20, 20)))
    try:
        session.save(a, str(tmp_path))
        mp = tmp_path / 'meta.json'
        meta = json.loads(mp.read_text(encoding='utf-8'))
        os.replace(tmp_path / meta.pop('masks'), tmp_path / 'masks.npz')
        meta['format'] = 1
        mp.write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
        e = session.load(str(tmp_path))
        assert e is not None
        try:
            assert np.array_equal(e.regions[0].mask, a.regions[0].mask)
        finally:
            e.close()
    finally:
        a.close()


# ---------------------------------------------------------------- #6 the working file is never the source

def test_export_never_writes_a_source_named_like_its_working_file(tmp_path):
    src = tmp_path / 'x.导出中.psd'
    psd_io.write_guides(str(src), _art(), {'A': _rect(5, 5, 20, 20)}, np.zeros((H, W), np.uint8))
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    d = Document.open(str(src))
    try:
        export.export(d, None, None, str(tmp_path / 'x.psd'), 'guides')
        assert sorted(os.listdir(tmp_path)) == ['x.psd', 'x.导出中.psd']
        assert hashlib.sha256(src.read_bytes()).hexdigest() == before
    finally:
        d.close()


# ---------------------------------------------------------------- #7 layers reaching past the canvas

class _Layer:
    def __init__(self, x0, y0, alpha):
        self.bbox = (x0, y0, x0 + alpha.shape[1], y0 + alpha.shape[0])
        self._im = Image.fromarray(np.dstack([np.zeros(alpha.shape + (3,), np.uint8), alpha]), 'RGBA')

    def composite(self, force=False):
        return self._im


@pytest.mark.parametrize('x0, y0', [(-7, -3), (50, 30), (-5, 25), (40, -10), (-20, -20), (100, 100), (-100, 0)])
def test_layers_reaching_past_the_canvas_are_cropped_to_it(x0, y0):
    alpha = (np.arange(25 * 30).reshape(25, 30) % 251 + 1).astype(np.uint8)
    P = 200
    big = np.zeros((H + 2 * P, W + 2 * P), np.uint8)
    big[P + y0:P + y0 + 25, P + x0:P + x0 + 30] = alpha
    assert np.array_equal(psd_io._alpha(_Layer(x0, y0, alpha), (W, H)), big[P:P + H, P:P + W])


# ---------------------------------------------------------------- #14, #16 the history cap

def test_history_lets_go_of_regions_it_can_no_longer_bring_back(monkeypatch):
    monkeypatch.setattr(document, 'UNDO_LIMIT', 5)
    d = _doc(('A', _rect(5, 5, 20, 20)))
    try:
        a = d.regions[0]
        gone = d.add_region('x')
        d.delete_region(gone)
        with d.lock:
            d._solves[gone] = {'sig': None}
        assert gone in d._known
        for i in range(4):
            d.rename_region(a.id, f'n{i}')
        assert gone in d._known                             # undo can still bring it back
        d.rename_region(a.id, 'n5')
        assert gone not in d._known and gone not in d._solves   # region+ and region- both dropped
        nid = d.add_region('y')
        d.undo()
        assert nid in d._known                              # redo can bring it back
        d.rename_region(a.id, 'z')
        assert nid not in d._known
        assert all(r.id in d._known for r in d.regions)
        assert d.undo() and d.regions[0].name == 'n5'
    finally:
        d.close()


def test_a_saved_state_the_history_cap_dropped_is_not_saved_again():
    d = _doc(('A', _rect(5, 5, 20, 20)))
    try:
        a = d.regions[0]
        assert not d.unsaved_guides()
        for i in range(document.UNDO_LIMIT + 1):
            d.rename_region(a.id, f'n{i}')
        while d.undo():
            pass
        assert a.name == 'n0' and d.unsaved_guides()        # not the name the file had
        d.mark_guides_saved()
        assert not d.unsaved_guides()
    finally:
        d.close()


# ---------------------------------------------------------------- #15 strokes in no region

def test_guides_export_keeps_strokes_outside_every_region(tmp_path):
    d = _doc(('A', _rect(5, 5, 25, 20)))
    try:
        d.add_stroke([(35, 32), (55, 32)])
        res = export.export(d, None, None, str(tmp_path / 'g.psd'), 'guides')
        assert (psd_io.read_guide_layers(res['file'])['strokes'][32, 37:54] > 0).all()
        e = Document.open(res['file'])
        try:
            assert len(e.strokes) == 1
        finally:
            e.close()
    finally:
        d.close()

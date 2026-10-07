import numpy as np

from stocking import session
from stocking.document import Document

from sample_data import PSD, needed


@needed
def test_session_round_trip(tmp_path):
    d = Document.open(PSD)
    try:
        d.rename_region(d.regions[2].id, '裆部')
        sid = d.add_stroke([(300, 200), (600, 220)])
        d.paint(d.regions[0].id, [(20, 20)], 6)
        before = d.state()
        session.save(d, str(tmp_path))
        e = session.load(str(tmp_path))
        try:
            after = e.state()
            assert np.array_equal(e.art, d.art)
            assert e.name == d.name and e.path == d.path
            assert [(r['name'], r['color']) for r in after['regions']] == [(r['name'], r['color']) for r in before['regions']]
            assert all(np.array_equal(a.mask, b.mask) for a, b in zip(d.regions, e.regions))
            assert len(after['strokes']) == len(before['strokes'])
            owner = lambda st: [next(r['name'] for r in st['regions'] if r['id'] == s['region']) if s['region'] else None
                                for s in st['strokes']]
            assert owner(after) == owner(before)
            assert np.allclose(np.array(after['strokes'][-1]['pts']), np.array(before['strokes'][-1]['pts']), atol=0.06)
        finally:
            e.close()
        # a second document replaces the first one's art file
        d2 = Document(np.zeros((40, 30, 3), np.uint8), 'b.png')
        try:
            session.save(d2, str(tmp_path))
            assert sorted(p.name for p in tmp_path.glob('art-*.png')) == [f'art-{d2.id}.png']
            e2 = session.load(str(tmp_path))
            assert e2.w == 30 and e2.h == 40 and e2.regions == []
            e2.close()
        finally:
            d2.close()
    finally:
        d.close()


def test_load_without_session_is_none(tmp_path):
    assert session.load(str(tmp_path)) is None
    (tmp_path / 'meta.json').write_text('{broken', encoding='utf-8')
    assert session.load(str(tmp_path)) is None


def test_session_keeps_dividers_deleted_walls_and_colour_exclusion(tmp_path):
    d = Document(np.zeros((60, 80, 3), np.uint8), 'c.png')
    try:
        d.add_divider([(10, 10), (40, 50)])
        with d.lock:
            d.erased.append((30.0, 20.0))
        d.set_color_exclude(False)
        session.save(d, str(tmp_path))
        e = session.load(str(tmp_path))
        try:
            assert np.allclose(np.reshape(e.state()['dividers'][0]['pts'], (-1, 2)), [(10, 10), (40, 50)])
            assert e.erased == [(30.0, 20.0)] and e.color_exclude is False
        finally:
            e.close()
    finally:
        d.close()


@needed
def test_unsaved_guides_follow_the_last_file_that_held_them(tmp_path):
    """Opening another image would lose regions and 走向 lines only if they differ from the last file that held them:
    the file opened, or a 丝袜引导.psd exported since. Undoing back to that point is unchanged again, and the answer
    survives a restart."""
    d = Document.open(PSD)
    try:
        assert not d.unsaved_guides() and d.state()['unsaved_guides'] is False
        d.add_stroke([(300, 200), (600, 220)])
        assert d.unsaved_guides()
        d.undo()
        assert not d.unsaved_guides()
        d.redo()
        assert d.unsaved_guides()
        d.mark_guides_saved()
        assert not d.unsaved_guides()
        session.save(d, str(tmp_path))
        e = session.load(str(tmp_path))
        try:
            assert not e.unsaved_guides()
        finally:
            e.close()
        d.paint(d.regions[0].id, [(20, 20)], 6)
        session.save(d, str(tmp_path))
        e = session.load(str(tmp_path))
        try:
            assert e.unsaved_guides()
        finally:
            e.close()
    finally:
        d.close()
    blank = Document(np.zeros((40, 30, 3), np.uint8), 'b.png')
    try:
        blank.add_region('左腿')
        assert not blank.unsaved_guides()                  # nothing painted or drawn: nothing to lose
    finally:
        blank.close()

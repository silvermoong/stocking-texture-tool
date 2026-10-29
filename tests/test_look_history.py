import numpy as np
import pytest

from stocking import look, server, settings
from stocking.document import Document


@pytest.fixture
def d():
    doc = Document(np.full((40, 60, 3), 120, np.uint8), 'synthetic.png')
    yield doc
    doc.close()


def looks(**kw):
    return look.clean_params(kw)


def test_look_changes_are_steps_of_a_history_of_their_own(d):
    d.set_look(looks(density=110), before=looks())
    d.set_look(looks(density=120))
    d.set_look(looks(density=130))
    st = d.state()
    assert st['can_undo_look'] and not st['can_redo_look'] and not st['can_undo'] and st['look_rev'] == 0
    assert d.undo('look') and d.look == looks(density=120)
    assert d.undo('look') and d.look == looks(density=110)
    assert d.undo('look') and d.look == looks()
    assert not d.undo('look') and not d.state()['can_undo_look'] and d.state()['can_redo_look']
    assert d.state()['look_rev'] == 3
    assert d.redo('look') and d.look == looks(density=110)
    assert d.redo('look') and d.redo('look') and d.look == looks(density=130)
    assert not d.redo('look') and d.state()['look_rev'] == 6
    d.undo('look')
    d.set_look(looks(density=140))                               # a new change leaves nothing to redo
    assert not d.state()['can_redo_look'] and not d.redo('look')


def test_a_look_that_is_not_changed_makes_no_step(d):
    d.set_look(looks(density=110))                               # nothing to go back to: no look was saved yet
    assert not d.state()['can_undo_look']
    d.set_look(looks(density=110), before=looks())
    d.set_look(looks(density=110))
    assert not d.state()['can_undo_look']
    d.set_look(looks(density=120))
    assert d.undo('look') and d.look == looks(density=110)


def test_a_merged_change_goes_on_the_step_before_it(d):
    d.set_look(looks(density=110), before=looks())               # the start of a drag
    d.set_look(looks(density=115), merge=True)
    d.set_look(looks(density=120), merge=True)
    assert d.undo('look') and d.look == looks() and not d.state()['can_undo_look']
    assert d.redo('look') and d.look == looks(density=120)
    d.set_look(looks(density=130), merge=True)                   # after the undo and redo the step is on top again
    assert d.undo('look') and d.look == looks()
    d.redo('look')
    d.set_look(looks(density=140))
    d.set_look(looks(density=130), merge=True)                   # dragged back to where it began: no step at all
    assert d.look == looks(density=130) and d.state()['can_undo_look']
    assert d.undo('look') and d.look == looks() and not d.state()['can_undo_look']


def test_a_merge_never_lands_on_a_step_of_something_else(d):
    d.set_look(looks(density=110), before=looks())
    d.set_color_exclude(False)
    d.set_look(looks(density=120), merge=True)
    assert d.undo('look') and d.look == looks(density=110) and d.color_exclude is False
    assert d.undo('look') and d.color_exclude is True and d.look == looks(density=110)
    assert d.undo('look') and d.look == looks()


def test_color_exclusion_is_on_the_look_history_and_the_guides_are_apart(d):
    d.add_region('左腿')
    d.set_look(looks(density=110), before=looks())
    d.set_color_exclude(False)
    st = d.state()
    assert st['can_undo'] and st['can_undo_look']
    assert d.undo('look') and d.color_exclude is True and d.look == looks(density=110)
    assert d.state()['regions'] and d.undo() and not d.state()['regions']          # the guides' step is the region
    assert d.look == looks(density=110) and d.state()['can_undo_look'] and not d.state()['can_undo']
    assert d.redo() and d.state()['regions'] and d.state()['can_redo_look']


def test_there_are_two_histories_only(d):
    with pytest.raises(ValueError):
        d.undo('nope')


def test_the_server_undoes_the_page_asked_for(d, api, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, '_FILE', str(tmp_path / 'settings.json'))
    monkeypatch.setattr(server, '_doc', d)
    monkeypatch.setattr(server, 'look_info', lambda doc, q: {'params': q})
    monkeypatch.setattr(server, '_want_depth', lambda doc, q: None)
    c = api
    url = f'/api/doc/{d.id}'
    put = lambda density, merge: c.put(f'{url}/look?merge={merge}', json={'density': density}).raise_for_status()

    put(110, 0)                                                  # the first save goes back to a look's defaults
    put(120, 1)
    put(130, 0)
    assert d.look['density'] == 130
    st = c.post(f'{url}/undo?page=look').json()
    assert d.look['density'] == 120 and st['can_undo_look'] and st['can_redo_look'] and st['look_rev'] == 1
    assert c.post(f'{url}/undo').json()['can_undo_look']         # the guides are the default page: nothing to take back
    assert d.look['density'] == 120
    st = c.post(f'{url}/undo?page=look').json()
    assert d.look == looks() and not st['can_undo_look']
    st = c.post(f'{url}/redo?page=look').json()
    assert d.look['density'] == 120 and st['can_undo_look']
    assert c.post(f'{url}/undo?page=nope').status_code == 422
    assert c.post(f'{url}/redo?page=nope').status_code == 422

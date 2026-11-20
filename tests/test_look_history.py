import numpy as np
import pytest

from stocking import look, presets, server, settings
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


def test_the_preset_the_look_was_loaded_from_goes_back_and_forth_with_its_step(d):
    d.set_look(looks(density=110), before=looks())               # a tweak with no preset selected
    assert d.look_preset is None
    d.set_look(looks(style='grain'), preset='甲')                # 甲 is loaded
    d.set_look(looks(style='coil'), preset='乙')                 # 乙 over it
    d.set_look(looks(style='coil', density=90), preset='乙')     # a tweak: the page names the preset with every save
    assert d.look_preset == '乙'
    assert d.undo('look') and (d.look, d.look_preset) == (looks(style='coil'), '乙')
    assert d.undo('look') and (d.look, d.look_preset) == (looks(style='grain'), '甲')
    assert d.undo('look') and (d.look, d.look_preset) == (looks(density=110), None)
    assert d.undo('look') and (d.look, d.look_preset) == (looks(), None)
    assert d.redo('look') and d.redo('look') and (d.look, d.look_preset) == (looks(style='grain'), '甲')
    assert d.redo('look') and (d.look, d.look_preset) == (looks(style='coil'), '乙')
    assert d.redo('look') and (d.look, d.look_preset) == (looks(style='coil', density=90), '乙')
    d.set_look(looks(style='coil', density=95))                  # a save that names none (an export) keeps it
    assert d.look_preset == '乙'


def test_a_name_that_changes_while_the_settings_stay_is_no_step_and_the_steps_beside_it_take_it(d):
    d.set_look(looks(density=110), before=looks(), preset='甲')  # 甲 loaded with none selected
    d.set_look(looks(density=110), preset='乙')                  # the same settings saved as a new preset, 乙
    assert d.look_preset == '乙' and d.state()['look_rev'] == 0
    assert d.undo('look') and (d.look, d.look_preset) == (looks(), None) and not d.state()['can_undo_look']
    assert d.redo('look') and (d.look, d.look_preset) == (looks(density=110), '乙')      # not back to 甲
    d.undo('look')
    # named with a step still to put back; the page sends an automatic strength as this image resolves it: no change
    d.set_look(looks(strength=55, strength_auto=True), preset='丙')
    assert d.state()['can_redo_look'] and not d.state()['can_undo_look']
    assert d.redo('look') and d.look_preset == '乙'
    assert d.undo('look') and (d.look, d.look_preset) == (looks(), '丙')
    d.set_look(looks(), preset='丁')                             # a preset holding these very settings is picked:
    assert d.state()['can_redo_look'] and not d.state()['can_undo_look']       # the name alone, what is to redo stays
    assert d.redo('look') and d.look_preset == '乙'
    assert d.undo('look') and (d.look, d.look_preset) == (looks(), '丁')


def test_a_look_never_changed_takes_a_name_and_a_tweak_saved_as_a_preset_keeps_it_through_undo_and_redo(d):
    # saved as a preset before any setting was changed (the automatic strength as this image resolves it)
    d.set_look(looks(strength=55, strength_auto=True), before=looks(), preset='甲')
    assert d.look_preset == '甲' and not d.state()['can_undo_look']
    d.set_look(looks(density=110), preset='甲')                  # a tweak under 甲
    d.set_look(looks(density=110), preset='乙')                  # saved as a new preset, 乙
    assert d.undo('look') and d.look_preset == '甲'
    assert d.redo('look') and (d.look, d.look_preset) == (looks(density=110), '乙')      # the name is not lost
    d.set_look(looks(density=110), preset=None)                  # 乙 deleted: none, and still one step to take back
    assert d.undo('look') and d.look_preset == '甲' and not d.state()['can_undo_look']


def test_a_deleted_preset_is_not_selected_again_by_undo_or_redo(d):
    d.set_look(looks(style='grain'), before=looks(), preset='甲')            # 甲 loaded
    d.set_look(looks(style='grain', density=120), preset='甲')               # a tweak under it
    d.set_look(looks(style='coil'), preset='乙')                             # 乙 loaded over it
    d.undo('look')
    d.forget_look_preset('甲')                                               # 甲 is deleted
    assert (d.look, d.look_preset) == (looks(style='grain', density=120), None)
    assert d.undo('look') and (d.look, d.look_preset) == (looks(style='grain'), None)
    assert d.undo('look') and (d.look, d.look_preset) == (looks(), None)
    assert d.redo('look') and d.redo('look') and d.look_preset is None       # a preset made later under the name
    assert d.redo('look') and (d.look, d.look_preset) == (looks(style='coil'), '乙')     # is another one; 乙 is kept


def test_a_drag_under_a_preset_is_one_step_that_ends_with_its_name(d):
    d.set_look(looks(density=110), before=looks(), preset='甲')  # 甲 loaded, then its slider dragged
    d.set_look(looks(density=115), merge=True, preset='甲')
    d.set_look(looks(density=120), merge=True, preset='甲')
    assert d.undo('look') and (d.look, d.look_preset) == (looks(), None) and not d.state()['can_undo_look']
    assert d.redo('look') and (d.look, d.look_preset) == (looks(density=120), '甲')
    d.set_look(looks(), merge=True, preset='甲')                 # dragged back to the settings it began with: the
    assert d.state()['can_undo_look']                            # step stays, it is still what selected 甲
    assert d.undo('look') and (d.look, d.look_preset) == (looks(), None)


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


def test_deleting_a_preset_takes_its_name_out_of_the_history_of_the_open_image(d, api, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, '_FILE', str(tmp_path / 'settings.json'))
    monkeypatch.setattr(server, '_doc', d)
    monkeypatch.setattr(server, 'look_info', lambda doc, q: {'params': q})
    monkeypatch.setattr(server, '_want_depth', lambda doc, q: None)
    c = api
    url = f'/api/doc/{d.id}'
    presets.save('黑丝', {'density': 120})
    for density, query in ((110, {}), (120, {'preset': '黑丝'}), (130, {})):
        c.put(f'{url}/look', params=query, json={'density': density}).raise_for_status()

    def seen():
        got = c.get(f'{url}/look').json()
        return got['params']['density'], got['preset']

    assert seen() == (130, '黑丝')
    assert c.request('DELETE', '/api/look/presets', json={'name': '黑丝'}).json() == {'presets': []}
    assert seen() == (130, None)
    c.post(f'{url}/undo?page=look')
    assert seen() == (120, None)                                 # not the preset someone saves under the name later
    monkeypatch.setattr(server, '_doc', None)                    # and with no image open there is nothing to do
    presets.save('黑丝', {'density': 120})
    assert c.request('DELETE', '/api/look/presets', json={'name': '黑丝'}).json() == {'presets': []}


def test_the_server_keeps_the_preset_with_the_look_and_undo_brings_it_back(d, api, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, '_FILE', str(tmp_path / 'settings.json'))
    monkeypatch.setattr(server, '_doc', d)
    monkeypatch.setattr(server, 'look_info', lambda doc, q: {'params': q})
    monkeypatch.setattr(server, '_want_depth', lambda doc, q: None)
    c = api
    url = f'/api/doc/{d.id}'

    def put(density, **query):
        r = c.put(f'{url}/look', params=query, json={'density': density})
        r.raise_for_status()
        return r.json()

    def seen():
        got = c.get(f'{url}/look').json()
        return got['params']['density'], got['preset']

    assert seen() == (100, None)
    assert put(110)['preset'] is None                            # a tweak with none selected
    assert put(120, preset='黑丝')['preset'] == '黑丝'           # the preset is loaded
    assert put(130)['preset'] == '黑丝'                          # a save that does not say keeps it
    c.post(f'{url}/undo?page=look')
    assert seen() == (120, '黑丝')
    c.post(f'{url}/undo?page=look')
    assert seen() == (110, None)                                 # before the load: none selected
    st = c.post(f'{url}/redo?page=look').json()
    assert seen() == (120, '黑丝') and st['can_redo_look']
    assert put(120, preset='')['preset'] is None                 # the preset was deleted: none, and no step for it
    assert c.get('/api/doc').json()['can_redo_look'] and seen() == (120, None)
    assert put(120, preset='另存')['preset'] == '另存'           # saved as a new preset: the name alone again
    assert c.get('/api/doc').json()['can_redo_look']
    c.post(f'{url}/undo?page=look')
    assert seen() == (110, None)
    assert c.put(f'{url}/look/preset', json={'name': 'x'}).status_code in (404, 405)     # no way to name it apart

    def undone_meanwhile(doc, q):                                # an undo arrives while the answer is worked out
        doc.undo('look')
        return {'params': q}
    c.post(f'{url}/redo?page=look')
    rev = d.look_rev
    monkeypatch.setattr(server, 'look_info', undone_meanwhile)
    got = c.get(f'{url}/look').json()                            # the settings and their preset are read as one,
    assert (got['params']['density'], got['preset'], got['look_rev']) == (120, '另存', rev)     # and say of which step

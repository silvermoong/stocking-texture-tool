import json
import threading

import pytest
from fastapi.testclient import TestClient

from stocking import look, presets, server, settings


@pytest.fixture(autouse=True)
def own_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, '_FILE', str(tmp_path / 'settings.json'))


def names():
    return [p['name'] for p in presets.listing()]


def test_a_preset_is_the_cleaned_settings_and_keeps_an_automatic_strength_out():
    presets.save('黑丝', {'style': 'grain', 'density': 120, 'strength': 45, 'strength_auto': True, 'unknown_key': 1})
    (p,) = presets.listing()
    assert p['name'] == '黑丝'
    assert p['params'] == look.clean_params({'style': 'grain', 'density': 120, 'strength_auto': True})
    assert p['params']['strength'] == look.DEFAULTS['strength']
    presets.save('手调', {'strength': 45, 'strength_auto': False})
    assert presets.listing()[1]['params']['strength'] == 45


def test_a_preset_keeps_the_moire_settings_and_one_saved_before_them_reads_as_off():
    presets.save('水波', {'style': 'knit', 'moire_on': True, 'moire': 60, 'moire_area': 35})
    (p,) = presets.listing()
    assert (p['params']['moire_on'], p['params']['moire'], p['params']['moire_area']) == (True, 60, 35)
    settings.update(**{presets.KEY: {'旧': {k: v for k, v in look.DEFAULTS.items() if not k.startswith('moire')}}})
    old = presets.listing()[0]['params']
    assert (old['moire_on'], old['moire'], old['moire_area']) == (False, 100, 100)


def test_saving_over_a_name_replaces_it_in_place_and_delete_removes_it():
    presets.save('甲', {'style': 'knit'})
    presets.save('乙', {'style': 'loops'})
    res = presets.save('甲', {'style': 'oily'})
    assert [p['name'] for p in res] == ['甲', '乙'] and res[0]['params']['style'] == 'oily'
    assert names() == ['甲', '乙']
    assert [p['name'] for p in presets.delete('甲')] == ['乙']
    with pytest.raises(ValueError, match='甲'):
        presets.delete('甲')


def test_names_are_trimmed_and_checked_and_settings_are_validated_before_anything_is_stored():
    presets.save('  带空格  ', {})
    assert names() == ['带空格']
    presets.save('x' * presets.MAX_NAME, {})
    for bad in ('', '   ', 'x' * (presets.MAX_NAME + 1), 'a\nb', None):
        with pytest.raises(ValueError):
            presets.save(bad, {})
    for bad in ({'style': 'no-such-style'}, {'density': 'dense'}):
        with pytest.raises(ValueError):
            presets.save('坏', bad)
    assert names() == ['带空格', 'x' * presets.MAX_NAME]


def test_one_unreadable_entry_does_not_break_the_list_and_is_not_rewritten_on_read():
    good = look.clean_params({'style': 'coil'})
    future = dict(good, a_setting_from_a_newer_version=7)
    settings.update(**{presets.KEY: {'好': good, '新版': future, '坏样式': {'style': 'later-style'},
                                     '坏数': {'density': 'x'}, '不是字典': 3}})
    got = {p['name']: p['params'] for p in presets.listing()}
    assert got['好'] == good and got['新版'] == good
    assert got['坏样式'] is None and got['坏数'] is None and got['不是字典'] is None
    assert settings.get(presets.KEY)['新版'] == future                  # listing wrote nothing back
    presets.save('另存', {})
    assert settings.get(presets.KEY)['新版'] == future                  # and neither did a save of another name


def test_a_damaged_store_reads_as_empty():
    settings.update(**{presets.KEY: ['not', 'a', 'dict']})
    assert presets.listing() == []
    presets.save('新的', {})
    assert names() == ['新的']


def test_saves_from_several_threads_all_land_and_other_settings_survive():
    settings.update(lang='en', last_dir='C:/x')
    errors = []

    def work(i):
        try:
            presets.save(f'预设{i}', {'density': 60 + i})
            settings.update(export_dir=f'D:/{i}')
        except Exception as e:                 # pragma: no cover
            errors.append(e)
    threads = [threading.Thread(target=work, args=(i,)) for i in range(24)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert sorted(names()) == sorted(f'预设{i}' for i in range(24))
    assert settings.get('lang') == 'en' and settings.get('last_dir') == 'C:/x'


def test_the_api_lists_saves_overwrites_and_deletes():
    c = TestClient(server.app)
    assert c.get('/api/look/presets').json() == {'presets': []}
    body = {'name': '细腻', 'params': {'style': 'grain', 'density': 110}}
    r = c.put('/api/look/presets', json=body)
    assert r.status_code == 200 and [p['name'] for p in r.json()['presets']] == ['细腻']
    assert c.get('/api/look/presets').json()['presets'][0]['params']['density'] == 110
    body['params']['density'] = 90
    assert c.put('/api/look/presets', json=body).json()['presets'][0]['params']['density'] == 90
    r = c.request('DELETE', '/api/look/presets', json={'name': '细腻'})
    assert r.status_code == 200 and r.json() == {'presets': []}
    assert json.loads(open(settings._FILE, encoding='utf-8').read())[presets.KEY] == {}


def test_the_api_answers_a_bad_request_with_a_message():
    c = TestClient(server.app)
    r = c.put('/api/look/presets', json={'name': ' ', 'params': {}})
    assert r.status_code == 400 and '名字' in r.json()['detail']
    r = c.put('/api/look/presets', json={'name': '甲', 'params': {'style': 'nope'}})
    assert r.status_code == 400
    r = c.request('DELETE', '/api/look/presets', json={'name': '没有这个'})
    assert r.status_code == 400 and '没有这个' in r.json()['detail']
    assert c.get('/api/look/presets').json() == {'presets': []}

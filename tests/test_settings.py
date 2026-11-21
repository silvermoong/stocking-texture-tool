import json
import os
import re
import shutil

from stocking import settings


def test_isolated_settings_survive_their_temp_folder_being_cleaned(monkeypatch):
    # an --isolated server keeps its settings in a temp folder, which the system may delete while it runs
    monkeypatch.setattr(settings, '_FILE', settings._FILE)
    settings.isolate()
    folder = os.path.dirname(settings._FILE)
    try:
        settings.update(lang='en')
        shutil.rmtree(folder)
        settings.update(lang='zh')
        assert settings.get('lang') == 'zh'
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def test_interface_size_is_kept_and_served_on_the_page(api, monkeypatch):
    monkeypatch.setattr(settings, '_FILE', settings._FILE)
    settings.isolate()
    folder = os.path.dirname(settings._FILE)
    try:
        c = api
        assert c.get('/api/ui-scale').json()['scale'] == 100
        assert 'style="--k: 1"' in c.get('/').text
        assert c.post('/api/ui-scale', json={'scale': 125}).json()['scale'] == 125
        assert settings.get('ui_scale') == 125
        assert '<html style="--k: 1.25" lang=' in c.get('/').text
        assert c.post('/api/ui-scale', json={'scale': 90}).status_code == 400
        assert c.get('/api/ui-scale').json()['scale'] == 125
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def test_page_receives_each_saved_tool_preference_or_unset(api, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, '_FILE', str(tmp_path / 'settings.json'))

    def initial_preferences():
        page = api.get('/').text
        return json.loads(re.search(r"data-tool-prefs='([^']+)'", page)[1])

    assert initial_preferences() == {'cut_snap': None, 'wall_snap': None, 'fill_seams': None}
    for key, on in (('cut_snap', False), ('wall_snap', True)):
        response = api.put(f'/api/tool-preferences/{key}', json={'on': on})
        assert response.status_code == 200 and response.json() == {'on': on}
    assert initial_preferences() == {'cut_snap': False, 'wall_snap': True, 'fill_seams': None}
    assert api.put('/api/tool-preferences/lang', json={'on': False}).status_code == 422


def test_legacy_tool_preference_is_only_written_if_missing(api, monkeypatch, tmp_path):
    path = tmp_path / 'settings.json'
    monkeypatch.setattr(settings, '_FILE', str(path))
    settings.update(lang='en')
    cut = '/api/tool-preferences/cut_snap'
    wall = '/api/tool-preferences/wall_snap'

    def migrate(url, on):
        response = api.put(url, json={'on': on, 'only_if_unset': True})
        assert response.status_code == 200
        return response.json()['on']

    assert migrate(cut, False) is False             # the first old value is stored
    assert migrate(cut, True) is False              # another window cannot replace it
    assert api.put(cut, json={'on': True}).json() == {'on': True}
    assert migrate(cut, False) is True              # a late migration cannot overwrite a user's click
    assert migrate(wall, False) is False            # the condition is per key, not per file
    assert json.loads(path.read_text(encoding='utf-8')) == {'lang': 'en', 'cut_snap': True, 'wall_snap': False}


def test_legacy_tool_preference_is_not_written_over_settings_that_cannot_be_read(api, monkeypatch, tmp_path):
    # "Missing" must be known, not assumed: an unreadable file may hold this key and every other setting.
    path = tmp_path / 'settings.json'
    monkeypatch.setattr(settings, '_FILE', str(path))
    cut = '/api/tool-preferences/cut_snap'
    for damaged in (b'{"lang": "en", "cut_snap": tru', b'["not", "settings"]'):
        path.write_bytes(damaged)
        response = api.put(cut, json={'on': False, 'only_if_unset': True})
        assert response.status_code == 503, response.text  # the page keeps its old value and asks again next time
        assert path.read_bytes() == damaged
        assert not (tmp_path / 'settings.json.tmp').exists()

    path.unlink()                                   # no file at all is the one case that does mean "unset"
    response = api.put(cut, json={'on': False, 'only_if_unset': True})
    assert response.status_code == 200 and response.json() == {'on': False}
    assert json.loads(path.read_text(encoding='utf-8')) == {'cut_snap': False}

import os
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


def test_interface_size_is_kept_and_served_on_the_page(monkeypatch):
    from fastapi.testclient import TestClient

    from stocking import server
    monkeypatch.setattr(settings, '_FILE', settings._FILE)
    settings.isolate()
    folder = os.path.dirname(settings._FILE)
    try:
        c = TestClient(server.app)
        assert c.get('/api/ui-scale').json()['scale'] == 100
        assert 'style="--k: 1"' in c.get('/').text
        assert c.post('/api/ui-scale', json={'scale': 125}).json()['scale'] == 125
        assert settings.get('ui_scale') == 125
        assert '<html style="--k: 1.25" lang=' in c.get('/').text
        assert c.post('/api/ui-scale', json={'scale': 90}).status_code == 400
        assert c.get('/api/ui-scale').json()['scale'] == 125
    finally:
        shutil.rmtree(folder, ignore_errors=True)

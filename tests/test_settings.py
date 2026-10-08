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

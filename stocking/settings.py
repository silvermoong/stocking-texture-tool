"""Per-user settings and runtime files under %LOCALAPPDATA%\\StockingTexture."""
import json
import os
import tempfile
import threading

DIR = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'StockingTexture')
_FILE = os.path.join(DIR, 'settings.json')
_lock = threading.Lock()


def _read():
    try:
        with open(_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def isolate():
    """Keep this process's settings to itself, starting empty (an --isolated development or test server: its
    language switch and folders must not change the user's)."""
    global _FILE
    _FILE = os.path.join(tempfile.mkdtemp(prefix='stocking-settings-'), 'settings.json')


def get(key, default=None):
    with _lock:
        return _read().get(key, default)


def update(**kw):
    with _lock:
        s = _read()
        s.update(kw)
        os.makedirs(DIR, exist_ok=True)
        tmp = _FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(s, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _FILE)

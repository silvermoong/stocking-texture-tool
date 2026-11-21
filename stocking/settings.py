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


def _write(s):
    # the folder of this process's file (a temp folder for an --isolated server, which the system may clean)
    os.makedirs(os.path.dirname(_FILE), exist_ok=True)
    tmp = _FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _FILE)


def update(**kw):
    with _lock:
        s = _read()
        s.update(kw)
        _write(s)


class Unreadable(Exception):
    """The settings file is there but what it holds cannot be told."""


def set_if_unset(key, value):
    """Return the stored value, writing only if the key is absent. Share the lock with ordinary updates.

    Absent has to be known: only a file that does not exist counts as empty. Where get and update fall back to
    defaults for a file they cannot read, this raises Unreadable and writes nothing, since the caller discards its
    own copy of the value once it is told the value is stored."""
    with _lock:
        try:
            with open(_FILE, encoding='utf-8') as f:
                s = json.load(f)
        except FileNotFoundError:
            s = {}
        except (OSError, ValueError) as e:
            raise Unreadable(str(e)) from e
        if not isinstance(s, dict):
            raise Unreadable('settings.json does not hold settings')
        if key in s:
            return s[key]
        s[key] = value
        _write(s)
        return value

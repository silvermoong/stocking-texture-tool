"""Look presets: named snapshots of the 纹理 settings, kept per user in settings.json, not with an image.

A preset is look.clean_params of the settings it was saved from, so it holds whatever the panel holds (a later
version's new settings come along). An automatic strength is stored as the default: it is worked out per image.

Saving checks everything. Reading never fails on one bad entry (an unknown style, a value out of range, a key from a
newer version): that entry is listed as unreadable, and the file is not rewritten on read, so presets saved by a newer
version survive a pass through an older one.
"""
import threading

from . import look, settings
from .i18n import tr

KEY = 'look_presets'
MAX_NAME = 40
# A save or delete reads, changes and writes the whole set; settings.update only locks its own write.
_lock = threading.Lock()


def _stored():
    v = settings.get(KEY)
    return v if isinstance(v, dict) else {}


def clean_name(name):
    """The name trimmed; ValueError (with a message for the user) if it is empty, too long or has control characters."""
    name = name.strip() if isinstance(name, str) else ''
    if not name:
        raise ValueError(tr('预设要有一个名字'))
    if len(name) > MAX_NAME:
        raise ValueError(tr('预设的名字最多 {n} 个字', n=MAX_NAME))
    if not name.isprintable():
        raise ValueError(tr('预设的名字里不能有换行之类的控制字符'))
    return name


def snapshot(params):
    """The settings as a preset stores them (look.clean_params, ValueError if they are not valid)."""
    q = look.clean_params(params)
    if q['strength_auto']:
        q['strength'] = look.DEFAULTS['strength']
    return q


def listing():
    """[{'name', 'params'}] in the order saved; params is None for an entry that cannot be read."""
    out = []
    for name, raw in _stored().items():
        try:
            params = look.clean_params(raw)
        except (ValueError, TypeError):
            params = None
        out.append({'name': name, 'params': params})
    return out


def save(name, params):
    """Store the settings under name, replacing a preset of that name (it keeps its place). Returns the listing."""
    name = clean_name(name)
    snap = snapshot(params)
    with _lock:
        presets = dict(_stored())
        presets[name] = snap
        settings.update(**{KEY: presets})
    return listing()


def delete(name):
    """Remove the preset; ValueError if there is none of that name. Returns the listing."""
    with _lock:
        presets = dict(_stored())
        if name not in presets:
            raise ValueError(tr('没有叫“{name}”的预设', name=name))
        del presets[name]
        settings.update(**{KEY: presets})
    return listing()

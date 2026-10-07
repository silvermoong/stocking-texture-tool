"""Chinese and English. The Chinese text is the key, as in gettext: code passes the Chinese, with {name}-style
fields filled from keyword arguments, and static/i18n/en.json maps it to English. A text with no English stays Chinese. The page (static/i18n.js) reads the
same catalog, so the server's messages and the page's own text change together.

The language is the user's choice from the 中 / EN switch (settings 'lang'), else the Windows display language.
Names written into files (exports, the guides PSD's group and layers, new regions' names) follow it too; names
read back are recognised in either language (both()).
"""
import functools
import json
import locale
import os
import sys

from . import settings

LANGS = ('zh', 'en')
CATALOG = os.path.join(os.path.dirname(__file__), 'static', 'i18n', 'en.json')
with open(CATALOG, encoding='utf-8') as _f:
    EN = json.load(_f)
_forced = None                  # tests pin the language


@functools.lru_cache(maxsize=1)
def system_lang():
    """'zh' when Windows shows Chinese, else 'en'."""
    if sys.platform == 'win32':
        try:
            import ctypes
            return 'zh' if (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3ff) == 0x04 else 'en'
        except (OSError, AttributeError):
            pass
    loc = (locale.getlocale()[0] or '').lower()
    return 'zh' if loc.startswith(('zh', 'chinese')) else 'en'


def lang():
    if _forced:
        return _forced
    v = settings.get('lang')
    return v if v in LANGS else system_lang()


def chosen():
    """The language the user picked with the switch, or None (following Windows)."""
    v = settings.get('lang')
    return v if v in LANGS else None


def set_lang(code):
    """The 中 / EN switch: 'zh', 'en', or None to follow Windows again."""
    settings.update(lang=code if code in LANGS else None)


def use(code):
    """Pin the language (tests); None un-pins it."""
    global _forced
    _forced = code if code in LANGS else None


def tr(text, **params):
    s = EN.get(text, text) if lang() == 'en' else text
    return s.format(**params) if params else s


def both(text):
    """The text in either language: names read back from files may have been written in the other one."""
    return {text, EN.get(text, text)}

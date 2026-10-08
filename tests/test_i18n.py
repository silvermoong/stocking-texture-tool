"""Chinese and English: every text the user can see has an English entry in static/i18n/en.json (and the catalog
holds nothing else), and what is written into files follows the language while reading takes either."""
import json
import os
import re
from html.parser import HTMLParser

import numpy as np
import pytest

from stocking import document, export, i18n, look, psd_io

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, 'stocking')
STATIC = os.path.join(PKG, 'static')
CJK = re.compile(r'[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]')     # Chinese, and its punctuation
ATTRS = {'title', 'aria-label', 'data-tip', 'aria-description', 'aria-valuetext'}


def _unescape(s):
    return json.loads('"' + s.replace('"', '\\"') + '"') if '\\' in s else s


def _calls(path, fn):
    """First arguments of fn('…') / fn("…") in a source file."""
    src = open(path, encoding='utf-8').read()
    out = set()
    for q in ("'", '"'):
        out |= {_unescape(m) for m in re.findall(rf'\b{fn}\(\s*{q}((?:[^{q}\\]|\\.)*){q}', src)}
    return out


class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.keys, self.skip = set(), []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        no = a.get('translate') == 'no'
        if tag not in ('meta', 'link', 'input', 'br', 'img', 'hr'):
            self.stack.append(no)
        if not no and not any(self.stack[:-1]):
            self.keys |= {v.strip() for k, v in attrs if k in ATTRS and v and CJK.search(v)}

    def handle_endtag(self, tag):
        if self.stack and tag not in ('meta', 'link', 'input', 'br', 'img', 'hr'):
            self.stack.pop()

    def handle_data(self, data):
        if data.strip() and CJK.search(data) and not any(self.stack):
            self.keys.add(data.strip())


def keys():
    """Every Chinese text the program shows or writes, as looked up in the catalog."""
    k = set()
    for f in os.listdir(PKG):
        if f.endswith('.py'):
            k |= _calls(os.path.join(PKG, f), 'tr')
    for f in ('app.js', 'look.js'):
        k |= _calls(os.path.join(STATIC, f), 't')
    page = _Page()
    page.feed(open(os.path.join(STATIC, 'index.html'), encoding='utf-8').read())
    k |= page.keys
    # names written into files or looked up in either language through a constant
    k |= {psd_io.GUIDE_GROUP, psd_io.STROKE_LAYER, psd_io.SPARKLE_LAYER, psd_io.DIVIDER_LAYER, psd_io.TEXTURE_MARK,
          psd_io.ART_LAYER, *export.NAMES.values(), *document.DEFAULT_REGIONS, '丝袜纹理工具'}
    return {x for x in k if CJK.search(x)}


def test_every_text_has_english_and_the_catalog_nothing_else():
    k = keys()
    missing = sorted(k - set(i18n.EN))
    stale = sorted(set(i18n.EN) - k)
    assert not missing, f'{len(missing)} without English: {missing}'
    assert not stale, f'{len(stale)} in the catalog but used nowhere: {stale}'
    for zh, en in i18n.EN.items():
        assert en and not CJK.search(en), (zh, en)
        assert set(re.findall(r'\{(\w+)\}', zh)) == set(re.findall(r'\{(\w+)\}', en)), (zh, en)


@pytest.fixture
def english():
    i18n.use('en')
    yield
    i18n.use('zh')


def test_messages_follow_the_language(english):
    assert i18n.tr('打不开 {name}：{error}', name='a.png', error='x') == i18n.EN['打不开 {name}：{error}'].format(name='a.png', error='x')
    assert i18n.tr('没有这条翻译的文字') == '没有这条翻译的文字'
    i18n.use('zh')
    assert i18n.tr('打不开 {name}：{error}', name='a.png', error='x') == '打不开 a.png：x'


def test_files_are_named_in_the_language_and_read_in_either(tmp_path, english):
    t = {k: os.path.basename(export.suggest(str(tmp_path), 'x.png', k)) for k in export.KINDS}
    assert t == {k: f"x-{i18n.EN[export.NAMES[k]]}" for k in export.KINDS}
    for name in ('x-丝袜成品.png', f"x-{i18n.EN['丝袜成品.png']}", f"x-{i18n.EN['丝袜引导.psd']}", 'x-丝袜纹理.png'):
        assert export.base_name(name) == 'x', name
    # a guides PSD written in English opens with its regions, strokes, 亮点 and 隔开 layers, and so does a Chinese one
    art = np.full((40, 60, 3), 90, np.uint8)
    reg = np.zeros((40, 60), bool)
    reg[5:30, 10:40] = True
    strokes = np.zeros((40, 60), np.uint8)
    strokes[15, 12:38] = 255
    for lang in ('en', 'zh'):
        i18n.use(lang)
        p = str(tmp_path / f'{lang}.psd')
        psd_io.write_guides(p, art, {'Left leg': reg}, strokes, None, strokes, strokes)
        from psd_tools import PSDImage
        names = [L.name for L in PSDImage.open(p)]
        assert names[-1] == i18n.tr(psd_io.GUIDE_GROUP)
        g = psd_io.read_guide_layers(p)
        assert list(g['regions']) == ['Left leg'] and np.array_equal(g['regions']['Left leg'], reg)
        assert g['strokes'] is not None and g['sparkle'] is not None and g['dividers'] is not None


def test_new_images_and_splits_are_named_in_the_language(english):
    d = document.Document.open(data=_png(), filename='a.png')
    try:
        assert [r.name for r in d.regions] == [i18n.EN['左腿'], i18n.EN['右腿']]
        assert look.side_of(d.regions[0].name) == 1.0 and look.side_of(d.regions[1].name) == -1.0
    finally:
        d.close()


def _png():
    import cv2
    return cv2.imencode('.png', np.full((40, 60, 3), 120, np.uint8))[1].tobytes()

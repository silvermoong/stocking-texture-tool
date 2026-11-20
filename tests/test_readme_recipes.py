"""The README screenshot recipes (.scratch/release/readme-recipes/*.json) drive the real page by its selectors. A
control renamed or moved in the page leaves a recipe that fails only when somebody next retakes the pictures, so
every element a recipe names by id, and every style it picks, must be in the page as it is now.

GitHub's code ZIPs leave .scratch out (.gitattributes): without the recipes there is nothing to check."""
import glob
import json
import os
import re
from html.parser import HTMLParser

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(ROOT, '.scratch', 'release', 'readme-recipes')
RECIPES = sorted(glob.glob(os.path.join(FOLDER, '*.json')))
pytestmark = pytest.mark.skipif(not os.path.isdir(FOLDER), reason='the recipes are not in this copy (a code ZIP)')


class _Names(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.styles = set(), set()

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if value and key == 'id':
                self.ids.add(value)
            elif value and key == 'data-style':
                self.styles.add(value)


def page_names(html):
    """(ids, styles): the id and the data-style of every element of the page (what a comment holds is no element)."""
    p = _Names()
    p.feed(html)
    p.close()
    return p.ids, p.styles


def named(css):
    """(ids, styles) a selector, or a script holding selectors, names."""
    return (set(re.findall(r'#([A-Za-z][\w-]*)', css)),
            set(re.findall(r'data-style\s*=\s*[\'"]?([\w-]+)', css)))


def _selectors(step):
    """The CSS a step hands to the page: what it clicks, drags or shoots, and the script it evaluates."""
    out = []
    for key in ('click', 'selector', 'eval'):
        if isinstance(step.get(key), str):
            out.append(step[key])
    for key in ('range', 'check'):
        if step.get(key):
            out.append(step[key][0])
    return out


def _page():
    with open(os.path.join(ROOT, 'stocking', 'static', 'index.html'), encoding='utf-8') as f:
        return f.read()


def test_there_are_recipes():
    assert RECIPES


def test_only_real_elements_of_the_page_count():
    html = '<!-- <button id="gone" data-style="old"> --><p id=\'kept\' data-style=\'knit\'></p><b id="too"></b>'
    assert page_names(html) == ({'kept', 'too'}, {'knit'})


@pytest.mark.parametrize('css', ['[data-style=oily]', "[data-style='oily']", '[data-style = "oily"]'])
def test_a_style_is_read_from_a_selector_however_it_is_written(css):
    assert named(css + ' #a-b') == ({'a-b'}, {'oily'})


@pytest.mark.parametrize('path', RECIPES, ids=[os.path.basename(p) for p in RECIPES])
def test_recipe_names_only_elements_the_page_has(path):
    with open(path, encoding='utf-8') as f:
        spec = json.load(f)
    ids, styles = page_names(_page())
    missing = []
    for n, step in enumerate(spec['steps'], 1):
        for css in _selectors(step):
            want_ids, want_styles = named(css)
            missing += [f'step {n}: #{name}' for name in sorted(want_ids - ids)]
            missing += [f'step {n}: data-style={name}' for name in sorted(want_styles - styles)]
    assert not missing, f'{os.path.basename(path)} names what the page no longer has: {missing}'

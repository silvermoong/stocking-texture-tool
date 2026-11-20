"""What only shows when the page runs in a browser: the top bar at a large 界面大小 in a narrow window, and the
colours of a pressed toggle button under the pointer. Runs the real page in the system's Edge (see uibrowser.py);
skipped where there is no Edge. Every case leaves a full-size screenshot in out/ui-browser (ignored by git)."""
import pytest

import uibrowser

WINDOWS = ((1280, 720), (1024, 768))


@pytest.fixture(scope='module')
def ui(tmp_path_factory):
    """(server, page): an isolated server with the synthetic picture open and solved, and one browser tab."""
    uibrowser.require()
    folder = tmp_path_factory.mktemp('ui')
    server = uibrowser.Server(folder).start()
    browser = uibrowser.Browser(folder)
    page = None
    try:
        server.set_lang('zh')               # whatever Windows speaks: the picture's regions are named in Chinese
        uibrowser.synthetic_document(server)
        page = browser.start().page()
        yield server, page
    finally:
        if page is not None:
            page.close()
        browser.stop()
        server.stop()


def show(ui, lang, scale, size, look=False):
    """The page in this language, 界面大小 and window; on 纹理 with a second 纹理层 (the widest the bar gets) if asked."""
    server, page = ui
    server.set_lang(lang)
    server.set_scale(scale)
    page.resize(*size)
    page.goto(server.url + ('/?page=look' if look else '/'))
    page.wait_for('!document.body.classList.contains("no-doc")', what='the document to show')
    if look:
        page.wait_for('document.body.dataset.mode === "look" && !!document.querySelector("#strength-val").textContent',
                      what='the 纹理 page')
        if page.evaluate('document.querySelector("#blend-section").hidden'):
            page.evaluate('document.querySelector("#btn-layer-add").click()')
        page.wait_for('!document.querySelector("#blend-section").hidden', what='the second 纹理层')
    return page


@pytest.mark.parametrize('look', (False, True), ids=('guides', 'texture'))
@pytest.mark.parametrize('size', WINDOWS, ids=lambda s: f'{s[0]}x{s[1]}')
@pytest.mark.parametrize('scale', (150, 175))
@pytest.mark.parametrize('lang', ('zh', 'en'))
def test_every_control_of_the_bar_can_be_reached_at_a_large_interface_size(ui, lang, scale, size, look):
    # L-3 of docs/findings/ui-ux-audit-20261119.md: 界面大小 itself was pushed out of a narrow window, with no way back
    page = show(ui, lang, scale, size, look)
    page.screenshot(f'bar-{lang}-{scale}-{size[0]}x{size[1]}-{"texture" if look else "guides"}')
    assert uibrowser.out_of_reach(page, '.bar') == []
    # and the page did not grow sideways to make room: nothing to scroll, the panel and the stage stay in the window
    assert page.evaluate('[document.scrollingElement.scrollWidth, document.scrollingElement.scrollLeft, '
                         'Math.round(document.querySelector(".status").getBoundingClientRect().bottom)]') \
        == [size[0], 0, size[1]]


@pytest.mark.parametrize('look', (False, True), ids=('guides', 'texture'))
@pytest.mark.parametrize('lang', ('zh', 'en'))
def test_the_bar_is_one_row_at_the_default_interface_size(ui, lang, look):
    # the second row is for a window too narrow only: at 100% the bar is the 44px row it always was, zoom readout and all
    page = show(ui, lang, 100, (1440, 900), look)
    page.screenshot(f'bar-{lang}-100-1440x900-{"texture" if look else "guides"}')
    assert uibrowser.out_of_reach(page, '.bar') == []
    assert page.evaluate('document.querySelector(".bar").getBoundingClientRect().height') == 44
    tops = page.evaluate('[...document.querySelectorAll(".bar > *")].filter((e) => e.checkVisibility())'
                         '.map((e) => { const r = e.getBoundingClientRect(); return Math.round(r.top + r.height / 2); })')
    assert len(set(tops)) == 1, tops
    assert page.evaluate('document.querySelector("#zoom-pct").checkVisibility()') is not look


@pytest.mark.parametrize('lang', ('zh', 'en'))
def test_a_pressed_toggle_button_stays_readable_under_the_pointer(ui, lang):
    # L-4 of the same audit: the hover fill of every button replaced the pressed fill and left dark text on mid grey
    page = show(ui, lang, 100, (1280, 720), look=True)
    low = {}                                                # every button is measured and pictured before any fails
    for button in ('#blend-auto', '#strength-auto', '#btn-check'):
        if page.evaluate(f'document.querySelector("{button}").getAttribute("aria-pressed")') != 'true':
            page.click(button)
        page.wait_for(f'document.querySelector("{button}").getAttribute("aria-pressed") === "true"',
                      what=f'{button} to be pressed')
        page.hover('#status-msg')                           # away from it: as it rests
        rest = uibrowser.text_contrast(page, button)
        page.hover(button)
        assert page.evaluate(f'document.querySelector("{button}").matches(":hover")')
        hovered = uibrowser.text_contrast(page, button)
        page.screenshot(f'toggle-hover-{lang}-{button.lstrip("#")}')
        for state, seen in (('at rest', rest), ('under the pointer', hovered)):
            if seen['ratio'] < 4.5:
                low[f'{button} {state}'] = seen
    assert low == {}

"""What only shows when the page runs in a browser: the top bar at a large 界面大小 in a narrow window, and the
colours of a pressed toggle button under the pointer. Runs the real page in the system's Edge (see uibrowser.py);
skipped where there is no Edge. Every case leaves a full-size screenshot in out/ui-browser (ignored by git)."""
import contextlib

import pytest

import uibrowser

WINDOWS = ((1280, 720), (1024, 768))


@pytest.fixture(scope='module')
def ui(tmp_path_factory):
    """(server, page): an isolated server with the synthetic picture open and solved, and one browser tab."""
    uibrowser.require()
    with uibrowser.running(tmp_path_factory.mktemp('ui')) as (server, browser):
        server.set_lang('zh')               # whatever Windows speaks: the picture's regions are named in Chinese
        uibrowser.synthetic_document(server)
        with contextlib.closing(browser.page()) as page:
            yield server, page


# what the bar must always offer, 界面大小 first: a rule that hid one of them would leave nothing out of the window
BAR = ('#ui-scale', '.lang [data-lang="zh"]', '.lang [data-lang="en"]', '#btn-export', '#btn-export-more',
       '#btn-open', '#tab-edit', '#tab-look', '#btn-layer-add', '#btn-undo', '#btn-redo')


def bar_out_of_reach(page):
    return uibrowser.out_of_reach(page, '.bar', must=BAR)


def show(ui, lang, scale, size, look=False):
    """The page in this language, 界面大小 and window; on 纹理 with a second 纹理层 (the widest the bar gets) if asked."""
    server, page = ui
    server.set_lang(lang)
    server.set_scale(scale)
    page.resize(*size)
    page.goto(server.url + ('/?page=look' if look else '/'))
    page.wait_for('!document.body.classList.contains("no-doc")', what='the document to show')
    # the page shown is the one asked for, not one left from the case before
    shown = page.evaluate('[document.documentElement.lang.slice(0, 2), document.querySelector("#ui-scale").value, '
                          'getComputedStyle(document.documentElement).getPropertyValue("--k").trim()]')
    assert shown == [lang, str(scale), f'{scale / 100:g}'], shown
    if not look:
        assert page.evaluate('document.body.dataset.mode') == 'edit'
    if look:
        page.wait_for('document.body.dataset.mode === "look" && !!document.querySelector("#strength-val").textContent',
                      what='the 纹理 page')
        layers = 'document.querySelectorAll(".mode[data-mode=look]").length'
        for n in range(page.evaluate(layers) + 1, (look if look is not True else 2) + 1):
            page.evaluate('document.querySelector("#btn-layer-add").click()')
            page.wait_for(f'{layers} === {n}', what=f'纹理层 {n}')
        page.wait_for('!document.querySelector("#blend-section").hidden', what='the second 纹理层')
    return page


@pytest.mark.parametrize('size', WINDOWS, ids=lambda s: f'{s[0]}x{s[1]}')
@pytest.mark.parametrize('scale', (150, 175))
@pytest.mark.parametrize('lang', ('zh', 'en'))
def test_the_previews_stay_on_the_stage_under_a_bar_of_two_rows(ui, lang, scale, size):
    # four 纹理层 make the bar its widest, so two rows and the lowest stage: 整体 and 细节, with the line under 细节
    # (按住空格看原图, or the legend of 标出问题), must still end inside it
    page = show(ui, lang, scale, size, look=4)
    # the picture is of the previews as they end up: 细节 has its image (not only the stage's grey, #545454) and
    # 整体 is not being drawn again
    page.wait_for('''(() => {
        const c = document.querySelector('#crop');
        if (c.width < 2 || /更新中|Updating/.test(document.querySelector('#fit-status').textContent)) return false;
        const d = c.getContext('2d').getImageData(0, c.height >> 1, c.width, 1).data;
        for (let i = 0; i < d.length; i += 4) if (Math.abs(d[i] - 84) > 6) return true;
        return false;
    })()''', timeout=60, what='the previews to be drawn')
    page.screenshot(f'previews-{lang}-{scale}-{size[0]}x{size[1]}-texture-4-layers')
    assert bar_out_of_reach(page) == []
    # a row the tabs are too wide to share is still 打开's: on the left, where it always is
    assert page.evaluate('Math.round(document.querySelector("#btn-open").getBoundingClientRect().left)') \
        == round(12 * scale / 100)
    below = page.evaluate('''(() => {
        const stage = document.querySelector('#stage').getBoundingClientRect().bottom;
        return [...document.querySelectorAll('#look-stage .pane')].map((p) => {
            const last = p.lastElementChild.getBoundingClientRect();
            return Math.round(last.bottom - stage);
        });
    })()''')
    assert max(below) <= 0, f'the panes end {below} px below the stage'


@pytest.mark.parametrize('look', (False, True), ids=('guides', 'texture'))
@pytest.mark.parametrize('size', WINDOWS, ids=lambda s: f'{s[0]}x{s[1]}')
@pytest.mark.parametrize('scale', (150, 175))
@pytest.mark.parametrize('lang', ('zh', 'en'))
def test_every_control_of_the_bar_can_be_reached_at_a_large_interface_size(ui, lang, scale, size, look):
    # L-3 of docs/findings/ui-ux-audit-20261119.md: 界面大小 itself was pushed out of a narrow window, with no way back
    page = show(ui, lang, scale, size, look)
    page.screenshot(f'bar-{lang}-{scale}-{size[0]}x{size[1]}-{"texture" if look else "guides"}')
    assert bar_out_of_reach(page) == []
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
    assert bar_out_of_reach(page) == []
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
        # and it still shows that it is pressed: released under the same pointer, its fill is plainly another
        page.click(button)
        page.wait_for(f'document.querySelector("{button}").getAttribute("aria-pressed") === "false"',
                      what=f'{button} to be released')
        released = uibrowser.text_contrast(page, button)
        page.click(button)
        page.wait_for(f'document.querySelector("{button}").getAttribute("aria-pressed") === "true"',
                      what=f'{button} to be pressed again')
        if uibrowser.contrast(hovered['fill'], released['fill']) < 3:
            low[f'{button} pressed against released, both under the pointer'] = (hovered['fill'], released['fill'])
    assert low == {}

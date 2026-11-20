"""What only shows when the page runs in a browser: the top bar at a large 界面大小 in a narrow window, and the
colours of a pressed toggle button under the pointer. Runs the real page in the system's Edge (see uibrowser.py);
skipped where there is no Edge. Every case leaves a full-size screenshot in out/ui-browser (ignored by git)."""
import contextlib
import json

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
       '#btn-open', '#tab-edit', '#tab-look', '#btn-undo', '#btn-redo')

# the 纹理层 of the panel: a row for each when there are several, none for a lone layer
LAYER_ROWS = 'document.querySelectorAll("#blend-rows > *").length'


def bar_out_of_reach(page):
    return uibrowser.out_of_reach(page, '.bar', must=BAR)


def show(ui, lang, scale, size, look=False):
    """The page in this language, 界面大小 and window; on 纹理 if asked, with at least two 纹理层 (look=True) or at
    least as many as `look` says, added with the + of the panel."""
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
        want = 2 if look is True else look
        for n in range((page.evaluate(LAYER_ROWS) or 1) + 1, want + 1):
            page.evaluate('document.querySelector("#layer-add").click()')
            page.wait_for(f'{LAYER_ROWS} === {n}', what=f'纹理层 {n}')
        if want > 1:
            page.wait_for('document.querySelector("#blend-rows").checkVisibility()', what='the list of 纹理层')
    return page


@pytest.mark.parametrize('size', WINDOWS, ids=lambda s: f'{s[0]}x{s[1]}')
@pytest.mark.parametrize('scale', (150, 175))
@pytest.mark.parametrize('lang', ('zh', 'en'))
def test_the_previews_stay_on_the_stage_under_a_bar_of_two_rows(ui, lang, scale, size):
    # a bar of two rows leaves the lowest stage: 整体 and 细节, with the line under 细节 (按住空格看原图, or the legend
    # of 标出问题), must still end inside it. Four 纹理层, added in the panel, are the most there is to draw
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


@pytest.mark.parametrize('scale, size', ((100, (1440, 900)), (150, (1024, 768))), ids=('100-1440x900', '150-1024x768'))
@pytest.mark.parametrize('lang', ('zh', 'en'))
def test_texture_layers_live_in_the_panel_and_the_bar_only_switches_pages(ui, lang, scale, size):
    # O-2 and O-3 of the audit: the 纹理层 had tabs beside the two pages and were listed again in the panel, and
    # nothing showed which settings were one layer's and which the whole picture's
    page = show(ui, lang, scale, size, look=1)
    thrown = len(page.errors)                              # the page is shared: only what this case throws counts
    name = (lambda n: f'纹理 {n}') if lang == 'zh' else (lambda n: f'Texture {n}')
    while page.evaluate(LAYER_ROWS) > 1:                    # layers left by another case: back to a lone one
        n = page.evaluate(LAYER_ROWS)
        page.evaluate('document.querySelector("#blend-rows .layer-x").click()')
        page.wait_for(f'{LAYER_ROWS} < {n}', what='a 纹理层 to go')
    tag = f'layers-{lang}-{scale}-{size[0]}x{size[1]}'

    # the bar: the two pages and nothing of the layers
    assert page.evaluate('[...document.querySelectorAll(".bar [role=tab]")].map((e) => e.id)') == ['tab-edit', 'tab-look']
    assert page.evaluate('!document.querySelector("#btn-layer-add") && !document.querySelector("#layer-tabs")'
                         ' && !document.querySelector(".bar .tab-x")')

    # a lone layer: no list, no 自动 100%, only a light + on the row of the 样式 title, which costs the panel no height
    seen = '''(() => {
        const vis = (s) => { const e = document.querySelector(s); return !!e && e.checkVisibility({ visibilityProperty: true }); };
        const add = document.querySelector('#layer-add'), r = add.getBoundingClientRect();
        const head = document.querySelector('#layer-card h2').getBoundingClientRect();
        const mid = r.top + r.height / 2;
        return { rows: vis('#blend-rows'), auto: vis('#blend-auto'), add: vis('#layer-add'), text: add.textContent.trim(),
                 tag: add.tagName, off: add.getAttribute('aria-disabled'), sameRow: mid > head.top && mid < head.bottom,
                 global: vis('#global-note'), title: document.querySelector('#layer-card-title').textContent.trim() };
    })()'''
    page.screenshot(f'{tag}-1')
    one = page.evaluate(seen)
    assert (one['rows'], one['auto'], one['add'], one['tag'], one['off'], one['sameRow'], one['global']) \
        == (False, False, True, 'BUTTON', 'false', True, False), one
    assert ('添加纹理层' if lang == 'zh' else 'Add texture layer') in one['text'], one

    # two layers: the list, each row a name that shows the layer, its 融合 slider and a ×; the card says whose settings
    # it holds, and a line under it says the rest is shared by the layers and goes on the whole picture
    page.click('#layer-add')
    page.wait_for(f'{LAYER_ROWS} === 2', what='the second 纹理层')
    rows = '''(() => [...document.querySelectorAll('#blend-rows > *')].map((row) => {
        const n = row.querySelector('.blend-name'), s = row.querySelector('input[type=range]'), x = row.querySelector('.layer-x');
        return { name: n.textContent.trim(), tag: n.tagName, current: n.getAttribute('aria-current'),
                 slider: s.getAttribute('aria-label'), x: x.tagName + ':' + x.getAttribute('aria-label') };
    }))()'''
    two = page.evaluate(rows)
    assert [r['name'] for r in two] == [name(1), name(2)] and [r['current'] for r in two] == ['false', 'true'], two
    assert all(r['tag'] == 'BUTTON' and r['slider'] and r['x'].startswith('BUTTON:') and name(i + 1) in r['x']
               and name(i + 1) in r['slider'] for i, r in enumerate(two)), two
    many = page.evaluate(seen)
    assert (many['rows'], many['auto'], many['add'], many['global']) == (True, True, True, True), many
    assert name(2) in many['title'], many
    page.click('#blend-rows > :nth-child(1) .blend-name')
    page.wait_for('document.querySelector("#blend-rows .blend-name").getAttribute("aria-current") === "true"',
                  what='the first 纹理层 to be shown')
    assert name(1) in page.evaluate(seen)['title']
    page.screenshot(f'{tag}-2')

    # what is one layer's is in the card, what is the whole picture's is under the line, below it
    assert page.evaluate('''(() => {
        const card = document.querySelector('#layer-card'), note = document.querySelector('#global-note');
        const own = ['.styles', '#density', '#tilt', '#strength'].every((s) => card.contains(document.querySelector(s)));
        const whole = ['#sparkle-on', '#particle-on', '#moire-on', '#btn-check', '#fade', '#exclude']
            .every((s) => !card.contains(document.querySelector(s))
                && (note.compareDocumentPosition(document.querySelector(s)) & Node.DOCUMENT_POSITION_FOLLOWING));
        const edge = getComputedStyle(card), panel = getComputedStyle(document.querySelector('.side'));
        const framed = parseFloat(edge.borderTopWidth) > 0 || edge.backgroundColor !== 'rgba(0, 0, 0, 0)'
            && edge.backgroundColor !== panel.backgroundColor;
        return own && whole && framed && !!(card.compareDocumentPosition(note) & Node.DOCUMENT_POSITION_FOLLOWING);
    })()''')
    # the 融合 note names all three effects that go on after the blend (O-9)
    assert ('高光粒子' if lang == 'zh' else 'ighlight particles') in page.evaluate(
        'document.querySelector("#blend-info").textContent')
    # the words CONTEXT.md rules out for 纹理层 and 融合
    assert not page.evaluate('/图层|叠加层|不透明度|混合模式/.test(document.querySelector("#layers-section").innerHTML)')

    # four layers: + says why it adds no more, and adds none
    for n in (3, 4):
        page.click('#layer-add')
        page.wait_for(f'{LAYER_ROWS} === {n}', what=f'纹理层 {n}')
    full = page.evaluate('(() => { const a = document.querySelector("#layer-add"); a.click(); '
                         'return [a.getAttribute("aria-disabled"), a.dataset.tip, document.querySelector("#status-msg").textContent]; })()')
    assert full[0] == 'true' and '4' in (full[1] or '') and '4' in full[2], full
    assert page.evaluate(LAYER_ROWS) == 4
    page.hover('#status-msg')
    page.screenshot(f'{tag}-4')
    # nothing of the layers is cut off by the panel's edge or squeezed to nothing
    assert page.evaluate('''(() => {
        const side = document.querySelector('.side'), left = side.getBoundingClientRect().left;
        return [...document.querySelectorAll('#layers-section button, #layers-section input')]
            .filter((e) => e.checkVisibility({ visibilityProperty: true }))
            .filter((e) => { const r = e.getBoundingClientRect(); return r.width < 8 || r.left < left - 0.5 || r.right > left + side.clientWidth + 0.5; })
            .map((e) => e.id || e.getAttribute('aria-label') || e.textContent.trim());
    })()''') == []
    assert bar_out_of_reach(page) == []

    # × deletes its own layer; the others are numbered anew and + adds again
    page.click('#blend-rows > :nth-child(2) .layer-x')
    page.wait_for(f'{LAYER_ROWS} === 3', what='a 纹理层 to go')
    assert [r['name'] for r in page.evaluate(rows)] == [name(1), name(2), name(3)]
    assert page.evaluate('document.querySelector("#layer-add").getAttribute("aria-disabled")') == 'false'
    assert page.errors[thrown:] == []


def press(page, key, code, vk, ctrl=False):
    """A key pressed and released, as the keyboard sends it to whatever has the focus."""
    for kind in ('keyDown', 'keyUp'):
        text = {'Enter': '\r', ' ': ' '}.get(key, '') if kind == 'keyDown' and not ctrl else ''
        page.send('Input.dispatchKeyEvent', type=kind, key=key, code=code, windowsVirtualKeyCode=vk,
                  text=text, modifiers=2 if ctrl else 0)


def test_the_side_panel_cannot_be_used_until_an_image_opens(tmp_path):
    uibrowser.require()
    with uibrowser.running(tmp_path) as (server, browser), contextlib.closing(browser.page()) as page:
        page.goto(server.url + '/')
        page.evaluate('document.querySelector(".lang [aria-checked=true]").focus()')
        press(page, 'Tab', 'Tab', 9)
        assert page.evaluate('document.activeElement.id') == 'btn-open-2'

        tool = '[data-tool="brush"]'
        page.click(tool)
        assert page.evaluate(f"document.querySelector('{tool}').getAttribute('aria-checked')") == 'false'

        server.upload('synthetic.png', uibrowser.synthetic_png())
        page.wait_for('!document.querySelector("#empty").checkVisibility()', what='the opened image')
        page.evaluate('document.querySelector(".lang [aria-checked=true]").focus()')
        press(page, 'Tab', 'Tab', 9)
        assert page.evaluate('document.activeElement.id') == 'btn-add-region'
        page.click(tool)
        assert page.evaluate(f"document.querySelector('{tool}').getAttribute('aria-checked')") == 'true'


STATUS_MSG = 'document.querySelector("#status-msg").textContent'


def canvas_mark(page, button, dx=0):
    x, y = page.hover('#view')
    buttons = 1 if button == 'left' else 2
    page.send('Input.dispatchMouseEvent', type='mousePressed', x=x, y=y,
              button=button, buttons=buttons, clickCount=1)
    if dx:
        page.send('Input.dispatchMouseEvent', type='mouseMoved', x=x + dx, y=y, buttons=buttons)
    page.send('Input.dispatchMouseEvent', type='mouseReleased', x=x + dx, y=y, button=button, clickCount=1)


@pytest.mark.parametrize('tool', ('cut', 'pen', 'wall'))
@pytest.mark.parametrize('lang, message', (
    ('zh', '线太短，请拖出一段更长的线'), ('en', 'Line too short: drag out a longer line'),
))
def test_a_short_guides_line_explains_why_it_was_discarded(ui, lang, message, tool):
    page = show(ui, lang, 100, (1280, 720))
    page.click(f'[data-tool="{tool}"]')
    canvas_mark(page, 'left', dx=2)
    assert page.evaluate(STATUS_MSG) == message
    # the tool's own hint beside it is long (Split's in English most of all) and must be what gives way, not the message
    assert page.evaluate('''(() => {
        const el = document.querySelector('#status-msg');
        const text = document.createRange();
        text.selectNodeContents(el);
        return text.getBoundingClientRect().width <= el.getBoundingClientRect().width + 0.01;
    })()'''), 'the message is cut short'


@pytest.mark.parametrize('lang, message', (
    ('zh', '指针下没有走向线：把指针移到走向线上再右键'),
    ('en', 'No direction line under the pointer: move onto one, then right-click'),
))
def test_right_click_between_direction_lines_explains_how_to_delete_one(ui, lang, message):
    page = show(ui, lang, 100, (1280, 720))
    page.click('[data-tool="pen"]')
    canvas_mark(page, 'right')
    assert page.evaluate(STATUS_MSG) == message


@pytest.mark.parametrize('lang, message', (
    ('zh', '已自动配对：把“左腿”的走向线镜像到“右腿”，替换 3 条。Ctrl+Z 可以撤销'),
    ('en', 'Paired automatically: mirrored the direction lines of “Left leg” onto “Right leg”, replacing 3. Ctrl+Z undoes'),
))
def test_mirror_names_the_automatic_pair_and_what_changed(tmp_path, lang, message):
    uibrowser.require()
    with uibrowser.running(tmp_path) as (server, browser), contextlib.closing(browser.page()) as page:
        server.set_lang(lang)
        before = uibrowser.synthetic_document(server, w=320, h=480)
        page.goto(server.url + '/')
        page.wait_for('document.querySelector("#btn-mirror").getAttribute("aria-disabled") === "false"',
                      what='Mirror to be available')
        page.click('#btn-mirror')
        assert page.evaluate('document.querySelector("#mirror-menu").hidden')
        page.wait_for(f'{STATUS_MSG}.includes("Ctrl+Z")', what='mirror feedback')
        assert page.evaluate(STATUS_MSG) == message
        page.wait_for('!document.querySelector("#region-list .busy-dot")', what='the mirrored direction lines to solve')
        assert page.evaluate(STATUS_MSG) == message
        press(page, 'z', 'KeyZ', 90, ctrl=True)
        page.wait_for('!document.querySelector("#btn-redo").disabled', what='the mirror to be undone')
        # the receipt offered Ctrl+Z: once that is done it must not go on offering it
        assert page.evaluate(STATUS_MSG) != message
        assert server.api('/api/doc')['strokes'] == before['strokes']


RECEIPT = '已自动配对：把“左腿”的走向线镜像到“右腿”，替换 3 条。Ctrl+Z 可以撤销'

# window.__said keeps every text the status bar is given; a request whose address has `slow` in it is sent late, and
# window.__answered counts the answers to those with `count` in it
WATCH = '''((slow, count) => {
    window.__said = [];
    window.__answered = 0;
    new MutationObserver((records) => {
        for (const r of records) for (const n of r.addedNodes) if (n.textContent) window.__said.push(n.textContent);
    }).observe(document.querySelector('#status-msg'), { childList: true });
    const real = window.fetch;
    window.fetch = (url, opt) => {
        const late = slow && String(url).includes(slow) ? new Promise((go) => setTimeout(go, 700)) : Promise.resolve();
        return late.then(() => real(url, opt)).finally(() => { if (count && String(url).includes(count)) window.__answered++; });
    };
})'''


def test_undo_pressed_before_the_mirror_receipt_shows_takes_the_receipt_with_it(tmp_path):
    uibrowser.require()
    with uibrowser.running(tmp_path) as (server, browser), contextlib.closing(browser.page()) as page:
        server.set_lang('zh')
        before = uibrowser.synthetic_document(server, w=320, h=480)
        page.goto(server.url + '/')
        page.wait_for('document.querySelector("#btn-mirror").getAttribute("aria-disabled") === "false"',
                      what='Mirror to be available')
        page.evaluate(WATCH + '("/mirror", "")')
        page.click('#btn-mirror')
        press(page, 'z', 'KeyZ', 90, ctrl=True)
        # the case is Ctrl+Z first, the receipt after it
        assert RECEIPT not in page.evaluate('window.__said')
        page.wait_for('!document.querySelector("#btn-redo").disabled', what='the mirror to be undone')
        assert RECEIPT in page.evaluate('window.__said')
        assert server.api('/api/doc')['strokes'] == before['strokes']
        # the mirror it offers to undo is undone already: left there, the next Ctrl+Z would take back an older step
        assert 'Ctrl+Z' not in page.evaluate(STATUS_MSG)


def test_undo_on_a_texture_page_with_no_history_leaves_the_mirror_receipt(tmp_path):
    uibrowser.require()
    with uibrowser.running(tmp_path) as (server, browser), contextlib.closing(browser.page()) as page:
        server.set_lang('zh')
        uibrowser.synthetic_document(server, w=320, h=480)
        page.goto(server.url + '/')
        page.wait_for('document.querySelector("#btn-mirror").getAttribute("aria-disabled") === "false"',
                      what='Mirror to be available')
        page.evaluate(WATCH + '("", "/undo")')
        page.click('#btn-mirror')
        page.wait_for(f'{STATUS_MSG}.includes("Ctrl+Z")', what='mirror feedback')
        page.wait_for('document.querySelector("#tab-look").getAttribute("aria-disabled") === "false"',
                      what='the mirrored direction lines to solve')
        mirrored = server.api('/api/doc')['strokes']
        page.click('#tab-look')
        page.wait_for('document.body.dataset.mode === "look"', what='the 纹理 page')
        # the case: the receipt is still shown, and this page has nothing to undo
        assert page.evaluate(f'[{STATUS_MSG}, document.querySelector("#btn-undo").disabled]') == [RECEIPT, True]
        press(page, 'z', 'KeyZ', 90, ctrl=True)
        page.wait_for('window.__answered > 0', what='the answer to the undo')
        page.evaluate('new Promise(resolve => setTimeout(resolve, 100))')
        # nothing was undone, so what the receipt offers still holds
        assert server.api('/api/doc')['strokes'] == mirrored
        assert page.evaluate(STATUS_MSG) == RECEIPT


def test_undo_with_nothing_to_undo_leaves_what_the_bar_says(tmp_path):
    uibrowser.require()
    with uibrowser.running(tmp_path) as (server, browser), contextlib.closing(browser.page()) as page:
        server.set_lang('zh')
        server.upload('synthetic.png', uibrowser.synthetic_png(320, 480))
        page.goto(server.url + '/')
        page.wait_for('!document.body.classList.contains("no-doc")', what='the document to show')
        page.evaluate(WATCH + '("", "/undo")')
        page.click('[data-tool="pen"]')
        canvas_mark(page, 'left', dx=2)
        note = '线太短，请拖出一段更长的线'
        assert page.evaluate(f'[{STATUS_MSG}, document.querySelector("#btn-undo").disabled]') == [note, True]
        press(page, 'z', 'KeyZ', 90, ctrl=True)
        page.wait_for('window.__answered > 0', what='the answer to the undo')
        page.evaluate('new Promise(resolve => setTimeout(resolve, 100))')
        assert page.evaluate(STATUS_MSG) == note


def test_a_mirror_receipt_that_arrives_on_the_texture_page_is_still_the_guides_pages(tmp_path):
    uibrowser.require()
    with uibrowser.running(tmp_path) as (server, browser), contextlib.closing(browser.page()) as page:
        server.set_lang('zh')
        before = uibrowser.synthetic_document(server, w=320, h=480)
        page.goto(server.url + '/')
        page.wait_for('document.querySelector("#btn-mirror").getAttribute("aria-disabled") === "false"',
                      what='Mirror to be available')
        page.evaluate(WATCH + '("/mirror", "/undo")')
        page.click('#btn-mirror')
        page.click('#tab-look')
        assert page.evaluate('[document.body.dataset.mode, window.__said.length]') == ['look', 0]
        page.wait_for(f'{STATUS_MSG} === {RECEIPT!r}', what='mirror feedback')
        assert page.evaluate('[document.body.dataset.mode, document.querySelector("#btn-undo").disabled]') == ['look', True]
        # this page has nothing to undo: the receipt is about the other page's history, whichever page it showed on
        press(page, 'z', 'KeyZ', 90, ctrl=True)
        page.wait_for('window.__answered > 0', what='the answer to the undo')
        page.evaluate('new Promise(resolve => setTimeout(resolve, 100))')
        assert page.evaluate(STATUS_MSG) == RECEIPT
        page.click('#tab-edit')
        press(page, 'z', 'KeyZ', 90, ctrl=True)
        page.wait_for('!document.querySelector("#btn-redo").disabled', what='the mirror to be undone')
        assert server.api('/api/doc')['strokes'] == before['strokes']
        assert 'Ctrl+Z' not in page.evaluate(STATUS_MSG)


def test_a_texture_undo_answered_after_going_back_to_guides_leaves_the_mirror_receipt(tmp_path):
    uibrowser.require()
    with uibrowser.running(tmp_path) as (server, browser), contextlib.closing(browser.page()) as page:
        server.set_lang('zh')
        uibrowser.synthetic_document(server, w=320, h=480)
        page.goto(server.url + '/')
        page.wait_for('document.querySelector("#btn-mirror").getAttribute("aria-disabled") === "false"',
                      what='Mirror to be available')
        page.evaluate(WATCH + '("look?merge=", "/undo?page=look")')
        page.click('#btn-mirror')
        page.wait_for(f'{STATUS_MSG}.includes("Ctrl+Z")', what='mirror feedback')
        page.wait_for('document.querySelector("#tab-look").getAttribute("aria-disabled") === "false"',
                      what='the mirrored direction lines to solve')
        mirrored = server.api('/api/doc')['strokes']
        page.click('#tab-look')
        page.wait_for('document.body.dataset.mode === "look" && !!document.querySelector("#strength-val").textContent',
                      what='the 纹理 page')
        # a setting changed here is saved late: the undo waits for that save, and is asked for only after it
        page.evaluate('''[...document.querySelectorAll('[data-style]')]
            .find((b) => b.getAttribute('aria-checked') !== 'true' && b.getAttribute('aria-pressed') !== 'true').click()''')
        assert page.evaluate(STATUS_MSG) == RECEIPT
        press(page, 'z', 'KeyZ', 90, ctrl=True)
        page.click('#tab-edit')
        # the case: back on 引导 before the 纹理 page's undo is even sent
        assert page.evaluate('[document.body.dataset.mode, window.__answered]') == ['edit', 0]
        page.wait_for('window.__answered > 0', what='the answer to the undo')
        page.evaluate('new Promise(resolve => setTimeout(resolve, 100))')
        # it took back the setting, not the mirror: what the receipt offers still holds
        assert server.api('/api/doc')['strokes'] == mirrored
        assert page.evaluate(STATUS_MSG) == RECEIPT


def test_the_next_guides_edit_ends_the_mirror_receipt(tmp_path):
    uibrowser.require()
    with uibrowser.running(tmp_path) as (server, browser), contextlib.closing(browser.page()) as page:
        server.set_lang('zh')
        uibrowser.synthetic_document(server, w=320, h=480)
        page.goto(server.url + '/')
        page.wait_for('document.querySelector("#btn-mirror").getAttribute("aria-disabled") === "false"',
                      what='Mirror to be available')
        page.click('#btn-mirror')
        page.wait_for(f'{STATUS_MSG}.includes("Ctrl+Z")', what='mirror feedback')
        page.wait_for('!document.querySelector("#region-list .busy-dot")', what='the mirrored direction lines to solve')
        mirrored = len(server.api('/api/doc')['strokes'])
        assert page.evaluate(STATUS_MSG) == RECEIPT
        page.click('[data-tool="pen"]')
        canvas_mark(page, 'left', dx=80)
        # Ctrl+Z would now take back this line, not the mirror: the receipt is over, and the line's solve is the news
        page.wait_for(f'{STATUS_MSG}.includes("横纹已更新")', timeout=4, what='the news of the solve')
        assert len(server.api('/api/doc')['strokes']) == mirrored + 1


def test_a_solved_direction_line_replaces_the_note_about_the_short_one_before_it(tmp_path):
    uibrowser.require()
    with uibrowser.running(tmp_path) as (server, browser), contextlib.closing(browser.page()) as page:
        server.set_lang('zh')
        before = uibrowser.synthetic_document(server, w=320, h=480)
        page.goto(server.url + '/')
        page.wait_for('!document.body.classList.contains("no-doc")', what='the document to show')
        page.click('[data-tool="pen"]')
        canvas_mark(page, 'left', dx=2)
        assert page.evaluate(STATUS_MSG) == '线太短，请拖出一段更长的线'
        canvas_mark(page, 'left', dx=80)
        # the long line is drawn and solved while the note about the short one is still up: it is the old news now
        page.wait_for(f'{STATUS_MSG}.includes("横纹已更新")', timeout=4, what='the news of the solve')
        assert len(server.api('/api/doc')['strokes']) == len(before['strokes']) + 1


TIP = 'document.querySelector("#tooltip")'


def tip_text(page):
    return page.evaluate(f'{TIP}.hidden ? null : {TIP}.textContent')


@pytest.mark.parametrize('lang, starts', (
    ('zh', ('点选', '画笔', '橡皮', '切开', '走向', '隔开', '把')),
    ('en', ('Pick', 'Brush', 'Eraser', 'Split', 'Direction', 'Divider', 'Flips')),
))
def test_guides_tools_offer_the_same_description_to_pointer_and_keyboard(ui, lang, starts):
    page = show(ui, lang, 100, (1280, 720))
    tools = tuple(f'[data-tool="{tool}"]' for tool in ('segment', 'brush', 'erase', 'cut', 'pen', 'wall'))
    for tool, start in zip((*tools, '#btn-mirror'), starts):
        page.hover(tool)
        visible = tip_text(page)
        assert visible and visible.startswith(start), (tool, visible)
        assert page.evaluate(f'''(() => {{
            const el = document.querySelector('{tool}');
            return [el.getAttribute('aria-description'), el.hasAttribute('title')];
        }})()''') == [visible, False]
        if tool == tools[0]:
            pick_tip = visible
    page.hover('#view')
    page.evaluate('document.querySelector("#region-list .current .more").focus()')
    press(page, 'Tab', 'Tab', 9)
    assert page.evaluate('document.activeElement.dataset.tool') == 'segment'
    assert tip_text(page) == pick_tip
    press(page, 'Escape', 'Escape', 27)
    assert tip_text(page) is None


def test_a_long_tool_tip_fits_a_narrow_window(ui):
    page = show(ui, 'en', 125, (360, 840))
    # Scroll the control into view before moving the pointer, not in the same frame as the hover.
    page.evaluate('''new Promise(resolve => {
        document.querySelector('[data-tool="wall"]').scrollIntoView({block: 'center', inline: 'nearest'});
        requestAnimationFrame(resolve);
    })''')
    page.hover('[data-tool="wall"]')
    assert (tip_text(page) or '').startswith('Divider')
    assert page.evaluate(f'''(() => {{
        const r = {TIP}.getBoundingClientRect();
        return r.left >= 8 && r.right <= innerWidth - 8 && r.top >= 0 && r.bottom <= innerHeight;
    }})()''')


def test_a_tip_goes_when_its_control_is_hidden(ui):
    page = show(ui, 'zh', 100, (1280, 720))
    page.click('[data-tool="cut"]')
    page.wait_for('!document.querySelector("#cutbar").hidden', what='the Split bar')
    page.hover('#btn-auto-cut')
    assert (tip_text(page) or '').startswith('把左右一对')
    press(page, 'b', 'KeyB', 66)
    assert page.evaluate('document.querySelector("#cutbar").hidden')
    # long enough for the browser to tell the page that the pointer is over something else, if it is going to
    page.evaluate('new Promise(resolve => setTimeout(resolve, 400))')
    assert tip_text(page) is None


def test_a_tip_the_keyboard_brought_goes_when_its_control_is_hidden(ui):
    # the keyboard's way to the same end: the pointer is nowhere near, so only the lost focus can take the tip away
    page = show(ui, 'zh', 100, (1280, 720))
    page.click('[data-tool="cut"]')
    page.wait_for('!document.querySelector("#cutbar").hidden', what='the Split bar')
    page.hover('#status-msg')
    page.evaluate('document.querySelector("#cut-snap").focus()')
    press(page, 'Tab', 'Tab', 9)
    assert page.evaluate('document.activeElement.id') == 'btn-auto-cut'
    assert (tip_text(page) or '').startswith('把左右一对')
    press(page, 'b', 'KeyB', 66)
    assert page.evaluate('document.querySelector("#cutbar").hidden')
    page.evaluate('new Promise(resolve => setTimeout(resolve, 400))')
    assert tip_text(page) is None


def test_a_key_pressed_after_a_click_does_not_pin_the_tip_when_the_pointer_leaves(ui):
    # the focus is the click's, not the keyboard's, whatever was pressed since: the tip goes with the pointer
    page = show(ui, 'zh', 100, (1280, 720))
    page.click('[data-tool="brush"]')
    assert (tip_text(page) or '').startswith('画笔')
    press(page, ']', 'BracketRight', 221)
    assert page.evaluate('document.activeElement.dataset.tool') == 'brush'
    page.hover('#view')
    assert tip_text(page) is None


def test_a_key_pressed_after_a_click_does_not_pin_the_tip_through_a_scroll(ui):
    page = show(ui, 'en', 125, (360, 600))
    page.click('[data-tool="brush"]')
    assert (tip_text(page) or '').startswith('Brush')
    press(page, ']', 'BracketRight', 221)
    # a little: the tool stays in view, with the focus the click gave it
    scrolled, in_view, focused, hidden = page.evaluate(f'''(async () => {{
        const side = document.querySelector('.side'), was = side.scrollTop;
        side.scrollTop = was > 6 ? was - 6 : was + 6;
        for (let i = 0; i < 2; i++) await new Promise(requestAnimationFrame);
        const el = document.activeElement, r = el.getBoundingClientRect();
        const at = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        return [side.scrollTop !== was, !!at && el.contains(at), el.dataset.tool, {TIP}.hidden];
    }})()''')
    assert (scrolled, in_view, focused) == (True, True, 'brush'), 'the case needs the panel to scroll with the tool in view'
    assert hidden


def test_a_tool_that_tab_scrolls_into_view_keeps_its_tip(ui):
    page = show(ui, 'en', 125, (360, 600))
    page.evaluate('''(() => {
        document.querySelector('.side').scrollTop = 0;
        document.querySelector('#show-coverage').focus({ preventScroll: true });
        window.__scrolled = false;
        window.addEventListener('scroll', () => { window.__scrolled = true; }, true);
    })()''')
    press(page, 'Tab', 'Tab', 9)
    assert page.evaluate('document.activeElement.dataset.tool') == 'pen'
    page.evaluate('new Promise(resolve => setTimeout(resolve, 400))')
    assert page.evaluate('window.__scrolled'), 'the case needs the panel to scroll to the tool'
    assert (tip_text(page) or '').startswith('Direction')
    assert page.evaluate(f'''(() => {{
        const t = {TIP}.getBoundingClientRect();
        const a = document.activeElement.getBoundingClientRect();
        return t.left >= 0 && t.right <= innerWidth && t.top >= 0 && t.bottom <= innerHeight
            && a.top >= 0 && a.bottom <= innerHeight && (t.bottom <= a.top || t.top >= a.bottom);
    }})()''')


@pytest.mark.parametrize('lang, labels, guides, texture', (
    ('zh', ('撤销', '重做'), ('撤销引导页上一步 (Ctrl+Z)', '重做引导页上一步 (Ctrl+Shift+Z)'),
     ('撤销纹理页上一步 (Ctrl+Z)', '重做纹理页上一步 (Ctrl+Shift+Z)')),
    ('en', ('Undo', 'Redo'), ('Undo on the Guides page (Ctrl+Z)', 'Redo on the Guides page (Ctrl+Shift+Z)'),
     ('Undo on the Texture page (Ctrl+Z)', 'Redo on the Texture page (Ctrl+Shift+Z)')),
))
def test_history_tooltips_name_the_current_page_without_changing_the_button_labels(ui, lang, labels, guides, texture):
    page = show(ui, lang, 100, (1280, 720))
    page.evaluate('document.querySelector("#tab-edit").focus()')
    press(page, 'Tab', 'Tab', 9)
    assert page.evaluate('document.activeElement.id') == 'btn-undo'
    assert tip_text(page) == guides[0]

    for tab, expected in (('#tab-look', texture), ('#tab-edit', guides)):
        page.click(tab)
        for selector, label, description in zip(('#btn-undo', '#btn-redo'), labels, expected):
            page.hover(selector)
            assert tip_text(page) == description
            assert page.evaluate(f'''(() => {{
                const el = document.querySelector('{selector}');
                return [el.textContent, el.hasAttribute('title')];
            }})()''') == [label, False]


@pytest.mark.parametrize('lang, where, avoid, more', (
    ('zh', '选择导出位置和文件名', '保存', '选择导出什么'),
    ('en', 'choose where to export it and its name', 'save', 'Choose what to export'),
))
def test_the_export_buttons_describe_themselves_to_the_keyboard_like_the_rest_of_the_bar(ui, lang, where, avoid, more):
    page = show(ui, lang, 100, (1280, 720))
    page.evaluate('document.querySelector("#btn-100").focus()')
    press(page, 'Tab', 'Tab', 9)
    assert page.evaluate('document.activeElement.id') == 'btn-export'
    main = tip_text(page)
    assert main and '(Ctrl+E)' in main and where in main and avoid not in main.lower(), main
    press(page, 'Tab', 'Tab', 9)
    assert page.evaluate('document.activeElement.id') == 'btn-export-more'
    assert tip_text(page) == more
    assert page.evaluate('''['#btn-export', '#btn-export-more'].map((s) => {
        const el = document.querySelector(s);
        return [el.getAttribute('aria-description'), el.hasAttribute('title'), el.getAttribute('aria-label')];
    })''') == [[main, False, None], [more, False, more]]
    press(page, 'Escape', 'Escape', 27)


@pytest.mark.parametrize('lang, errors, normal', (
    ('zh', ('整体和细节预览失败', '整体预览失败'), '缩到窗口大小，看整体观感'),
    ('en', ('Whole and Detail previews failed', 'Whole preview failed'), 'Scaled to the window, for the overall look'),
))
def test_preview_failures_clear_independently_on_the_next_success(ui, lang, errors, normal):
    page = show(ui, lang, 100, (360, 840))
    page.evaluate('''window.__failFit = window.__failCrop = true;
        const real = window.fetch;
        window.fetch = (url, opt) => {
            if (window.__failFit && String(url).includes('/render/fit?'))
                return Promise.resolve(new Response('unavailable', {status: 503}));
            if (window.__failCrop && String(url).includes('/render/crop?'))
                return Promise.reject(new TypeError('network failed'));
            return real(url, opt);
        };''')
    page.click('#tab-look')
    error = 'document.querySelector("#preview-error")'
    message = f'{error}?.textContent'
    fit = 'document.querySelector("#fit-status").textContent'
    page.wait_for(f'{message} === {json.dumps(errors[0])}', timeout=5, what='both preview errors')
    assert page.evaluate(f'{fit} === {json.dumps(normal)}')
    assert page.evaluate(f'''(() => {{
        const text = document.createRange(); text.selectNodeContents({error});
        const r = text.getBoundingClientRect(), footer = {error}.parentElement.getBoundingClientRect();
        return r.left >= 0 && r.right <= innerWidth && r.top >= footer.top && r.bottom <= footer.bottom;
    }})()'''), 'all of the error should be visible even at 360 px'

    page.evaluate('window.__failCrop = false; document.querySelector("[data-zoom=\'1\']").click()')
    page.wait_for(f'{message} === {json.dumps(errors[1])}', timeout=5, what='only the failed Whole preview')
    page.evaluate('window.__failFit = false; document.querySelector("[data-style=\'knit\']").click()')
    page.wait_for(f'{message} === "" && {fit} === {json.dumps(normal)}', timeout=5,
                  what='both previews to recover')


@pytest.mark.parametrize('pane, next_control', (('fit', '[data-style=knit]'), ('crop', '[data-zoom="1"]')))
def test_a_superseded_preview_failure_is_not_shown(ui, pane, next_control):
    page = show(ui, 'en', 100, (1280, 900))
    page.evaluate('''window.__failFirst = null; window.__renders = 0;
        const real = window.fetch;
        window.fetch = (url, opt) => {
            if (!String(url).includes('/render/' + ''' + json.dumps(pane) + ''' + '?')) return real(url, opt);
            window.__renders++;
            if (window.__renders === 1) return new Promise((go, fail) => { window.__failFirst = fail; });
            return real(url, opt);
        };
        window.__previewMessages = [];
        new MutationObserver(records => {
            for (const r of records) for (const n of r.addedNodes) if (n.textContent)
                window.__previewMessages.push(n.textContent);
        }).observe(document.querySelector('.status'), {childList:true, subtree:true});''')
    page.click('#tab-look')
    page.wait_for('!!window.__failFirst', what='the first preview request')
    page.evaluate(f'document.querySelector({json.dumps(next_control)}).click(); '
                  'void window.__failFirst(new TypeError("network failed"))')
    page.wait_for('window.__renders >= 2', what='the newer preview request')
    assert not any('preview failed' in message for message in page.evaluate('window.__previewMessages'))


@pytest.mark.parametrize('pane, control, failed', (
    ('fit', '[data-style=knit]', 'Whole preview failed'), ('crop', '[data-zoom="1"]', 'Detail preview failed')))
def test_a_preview_asked_for_before_color_exclusion_changed_does_not_report_its_failure(tmp_path, pane, control, failed):
    # 颜色排除 changes what is textured: a preview still on its way shows the coverage before, so its failure is no
    # news of the picture now due, which is asked for once the settings have been read again
    uibrowser.require()
    with uibrowser.running(tmp_path) as (server, browser), contextlib.closing(browser.page()) as page:
        server.set_lang('en')
        uibrowser.synthetic_document(server, w=320, h=480)
        page.goto(server.url + '/')
        page.wait_for('!document.body.classList.contains("no-doc")', what='the document to show')
        # this pane's previews pass, wait to be failed by hand, or fail; the reading after a change can be made to wait
        page.evaluate('''window.__pane = ''' + json.dumps(pane) + ''';
            window.__previews = 'pass'; window.__held = []; window.__holdLook = false; window.__looks = [];
            window.__done = {fit: 0, crop: 0};
            const real = window.fetch;
            window.fetch = (url, opt) => {
                const to = String(url);
                if (window.__holdLook && (!opt?.method || opt.method === 'GET') && to.includes('/look?'))
                    return new Promise((go) => window.__looks.push(() => go(real(url, opt))));
                const of = to.includes('/render/fit?') ? 'fit' : to.includes('/render/crop?') ? 'crop' : null;
                if (!of) return real(url, opt);
                if (of !== window.__pane || window.__previews === 'pass')
                    return real(url, opt).then((r) => { window.__done[of]++; return r; });
                if (window.__previews === 'fail') return Promise.resolve(new Response('unavailable', {status: 503}));
                return new Promise((go, fail) => window.__held.push(() => fail(new TypeError('network failed'))));
            };
            window.__said = [];
            new MutationObserver(() => window.__said.push(document.querySelector('#preview-error').textContent))
                .observe(document.querySelector('#preview-error'), {childList: true, characterData: true, subtree: true});''')
        error = 'document.querySelector("#preview-error").textContent'
        exclude = 'document.querySelector("#exclude")'
        press = f'document.querySelector({json.dumps(control)}).click()'
        page.click('#tab-look')
        page.wait_for('window.__done.fit > 0 && window.__done.crop > 0', what='both previews of a good picture')
        assert page.evaluate(f'[{error}, {exclude}.checked]') == ['', True]

        # a preview is on its way when 颜色排除 is switched off; the server has it, and the reading it calls for is out
        page.evaluate(f'window.__previews = "hold"; {press}')
        page.wait_for('window.__held.length > 0', what='a preview to be on its way')
        page.evaluate(f'window.__holdLook = true; {exclude}.click()')
        page.wait_for(f'{exclude}.checked === false', what='颜色排除 to be off, as the server has it')
        page.wait_for('window.__looks.length > 0', what='the settings to be read again')
        page.evaluate('void window.__held.splice(0).forEach((fail) => fail())')
        page.evaluate('new Promise((resolve) => setTimeout(resolve, 200))')
        assert page.evaluate(f'[{error}, window.__said]') == ['', []]

        # the preview of the coverage now in force still says so when it fails, and the notice goes when it succeeds
        page.evaluate('window.__previews = "fail"; window.__holdLook = false; '
                      'void window.__looks.splice(0).forEach((go) => go())')
        page.wait_for(f'{error} === {failed!r}', timeout=10, what='the failure of the preview now due')
        page.evaluate(f'window.__previews = "pass"; {press}')
        page.wait_for(f'{error} === ""', timeout=10, what='the preview to recover')


def test_a_preview_failure_lasts_until_that_preview_succeeds_or_another_image_opens(tmp_path):
    uibrowser.require()
    with uibrowser.running(tmp_path) as (server, browser), contextlib.closing(browser.page()) as page:
        server.set_lang('en')
        uibrowser.synthetic_document(server, w=320, h=480)
        page.goto(server.url + '/')
        page.wait_for('!document.body.classList.contains("no-doc")', what='the document to show')
        # the previews fail, wait to be settled by hand, or pass; reading the settings can fail too
        page.evaluate('''window.__previews = 'fail'; window.__held = []; window.__failLook = false;
            const real = window.fetch;
            window.fetch = (url, opt) => {
                const to = String(url);
                if (window.__failLook && (!opt?.method || opt.method === 'GET') && /\\/look(\\?|$)/.test(to))
                    return Promise.resolve(new Response('unavailable', {status: 503}));
                if (!to.includes('/render/fit?') && !to.includes('/render/crop?')) return real(url, opt);
                if (window.__previews === 'fail') return Promise.resolve(new Response('unavailable', {status: 503}));
                if (window.__previews === 'hold') return new Promise((go, fail) => window.__held.push({
                    go: () => go(real(url, opt)), fail: () => fail(new TypeError('network failed'))}));
                return real(url, opt);
            };
            window.__said = [];
            new MutationObserver(() => window.__said.push(document.querySelector('#preview-error').textContent))
                .observe(document.querySelector('#preview-error'), {childList: true, characterData: true, subtree: true});''')
        error = 'document.querySelector("#preview-error")'
        both = 'Whole and Detail previews failed'
        shown = f'[{error}.textContent, {error}.checkVisibility()]'
        hint = 'document.querySelector("#status-hint")'
        page.click('#tab-look')
        page.wait_for(f'{error}.textContent === {both!r}', timeout=5, what='both preview errors')

        # on 引导 the notice is out of sight, and the bar there is as it always is
        page.click('#tab-edit')
        assert page.evaluate(f'[{error}.checkVisibility(), {hint}.checkVisibility(), !!{hint}.textContent]') \
            == [False, True, True]
        # back on the same image, the last pictures are still the ones that failed to update: so is the notice,
        # while the new previews are on their way
        page.evaluate('window.__previews = "hold"')
        page.click('#tab-look')
        page.wait_for('window.__held.length > 0', what='a preview to be asked for again')
        assert page.evaluate(shown) == [both, True]
        # those previews are answered only after the page was left and come back to: they are no news of this visit
        page.click('#tab-edit')
        page.click('#tab-look')
        page.evaluate('void window.__held.splice(0).forEach((h) => h.fail())')
        page.wait_for('window.__held.length > 0', what='the previews of this visit')
        assert page.evaluate(shown) == [both, True]
        page.evaluate('window.__previews = "pass"; void window.__held.splice(0).forEach((h) => h.go())')
        page.wait_for(f'{error}.textContent === ""', timeout=10, what='the previews to succeed')

        # a preview that fails after its page was left says nothing, then or on coming back
        page.evaluate('window.__said = []; window.__previews = "hold"; '
                      'document.querySelector("[data-zoom=\'1\']").click()')
        page.wait_for('window.__held.length > 0', what='a preview to be on its way')
        page.click('#tab-edit')
        page.evaluate('window.__previews = "pass"; void window.__held.splice(0).forEach((h) => h.fail())')
        page.click('#tab-look')
        page.wait_for('document.querySelector("#fit-status").textContent === "Scaled to the window, for the overall look"',
                      what='the previews to settle')
        page.evaluate('new Promise((resolve) => setTimeout(resolve, 300))')
        assert page.evaluate('window.__said') == []

        # nor does the notice go when the settings themselves cannot be read on coming back
        page.evaluate('window.__previews = "fail"; document.querySelector("[data-zoom=\'2\']").click()')
        page.wait_for(f'{error}.textContent === "Detail preview failed"', timeout=5, what='the Detail preview error')
        page.click('#tab-edit')
        page.evaluate('window.__failLook = true')
        page.click('#tab-look')
        page.wait_for('document.querySelector("#status-msg").matches(".error")', what='the settings to fail to load')
        assert page.evaluate(shown) == ['Detail preview failed', True]

        # another image has no failed preview
        page.evaluate('window.__failLook = false; window.__previews = "pass"')
        server.upload('other.png', uibrowser.synthetic_png(320, 480))
        page.wait_for(f'{error}.textContent === ""', timeout=10, what='the notice to go with the image')


def test_a_preview_failure_is_not_hidden_by_an_older_notice_in_a_narrow_window(ui):
    # a long notice that is no error is up when a preview fails: the failure is the newer news and may be mended
    # before the notice goes, so it is the notice that is cut short
    server, _ = ui
    name = 'A preset with quite a long name'
    server.api('/api/look/presets', 'PUT', {'name': name, 'params': {'density': 111, 'style': 'loops'}})
    page = show(ui, 'en', 100, (360, 840), look=1)
    preset = 'document.querySelector("#preset-select")'
    page.wait_for(f'[...{preset}.options].some(o => o.value === {json.dumps(name)})', what='the preset to be listed')
    page.evaluate('''window.__failCrop = false;
        const real = window.fetch;
        window.fetch = (url, opt) => {
            if (window.__failCrop && String(url).includes('/render/crop?'))
                return Promise.resolve(new Response('unavailable', {status: 503}));
            return real(url, opt);
        };''')
    page.evaluate(f'{preset}.value = {json.dumps(name)}; {preset}.dispatchEvent(new Event("change", {{bubbles:true}}))')
    assert name in page.evaluate(STATUS_MSG)
    page.evaluate('window.__failCrop = true; document.querySelector("[data-zoom=\'1\']").click()')
    error = 'document.querySelector("#preview-error")'
    page.wait_for(f'{error}.textContent === "Detail preview failed"', timeout=4, what='the Detail preview error')
    notice, is_error, whole, width = page.evaluate(f'''(() => {{
        const msg = document.querySelector('#status-msg'), e = {error};
        return [msg.textContent, msg.matches('.error'), e.scrollWidth <= e.clientWidth,
                e.getBoundingClientRect().width];
    }})()''')
    assert name in notice and not is_error, 'the case is a failure while the older notice is still up'
    assert whole and width > 1, f'the preview failure has {width} px under the older notice'
    page.screenshot('preview-failure-under-an-older-notice-en-360x840')
    page.evaluate('window.__failCrop = false; document.querySelector("[data-zoom=\'2\']").click()')
    page.wait_for(f'{error}.textContent === ""', timeout=5, what='the Detail preview to recover')


def test_a_preview_failure_gives_way_to_a_message_in_a_narrow_window(ui):
    # a server that stops answering fails the previews and the save together: the newer message must not be cut
    # short to keep the standing preview notice whole
    page = show(ui, 'en', 100, (360, 840))
    page.evaluate('''const real = window.fetch;
        window.fetch = (url, opt) => {
            const to = String(url);
            if (to.includes('/render/fit?') || to.includes('/render/crop?')
                || (opt?.method === 'PUT' && to.includes('/look?')))
                return Promise.resolve(new Response('unavailable', {status: 503}));
            return real(url, opt);
        };''')
    page.click('#tab-look')
    error = 'document.querySelector("#preview-error")'
    page.wait_for(f'{error}.textContent === "Whole and Detail previews failed"', timeout=5,
                  what='both preview errors')
    page.evaluate('document.querySelector("[data-style=\'loops\']").click()')
    page.wait_for('document.querySelector("#status-msg").matches(".error")', what='the save failure')
    whole, room = page.evaluate(f'''(() => {{
        const msg = document.querySelector('#status-msg');
        return [msg.scrollWidth <= msg.clientWidth, {error}.getBoundingClientRect().width];
    }})()''')
    assert whole or room < 1, f'the message is cut short while the preview notice keeps {room} px'


@pytest.mark.parametrize('lang, scope', (
    ('zh', '随当前图保存，不进入预设。'), ('en', 'Saved with this image, not in presets.'),
))
def test_color_exclusion_says_it_is_saved_with_the_image_not_presets(ui, lang, scope):
    page = show(ui, lang, 100, (360, 840), look=1)
    exclude = 'document.querySelector("#exclude")'
    assert page.evaluate(f'document.getElementById({exclude}.getAttribute("aria-describedby"))?.textContent') == scope
    assert page.evaluate('document.querySelector("#exclude-scope").innerText') == scope


@pytest.mark.parametrize('lang, reset', (
    ('zh', ('高光粒子', '纹理减弱', '颜色排除不变', 'Ctrl+Z')),
    ('en', ('highlight particles', 'moiré effect and texture fade', 'Color exclusion stays as is', 'Ctrl+Z')),
))
def test_reset_all_tooltip_says_what_changes_and_how_to_undo(ui, lang, reset):
    page = show(ui, lang, 100, (360, 840), look=1)
    page.evaluate('''new Promise(go => {
        document.querySelector('#btn-look-reset').scrollIntoView({block: 'center'});
        requestAnimationFrame(() => requestAnimationFrame(go));
    })''')
    page.hover('#btn-look-reset')
    got = tip_text(page)
    assert got and all(word in got for word in reset), got
    assert page.evaluate(f'''(() => {{
        const r = {TIP}.getBoundingClientRect();
        return r.left >= 8 && r.right <= innerWidth - 8 && r.top >= 0 && r.bottom <= innerHeight;
    }})()''')


def test_undo_never_goes_past_a_texture_change_that_could_not_be_saved(tmp_path):
    uibrowser.require()
    with uibrowser.running(tmp_path) as (server, browser), contextlib.closing(browser.page()) as page:
        server.set_lang('zh')
        doc = uibrowser.synthetic_document(server, w=320, h=480)['id']
        page.goto(server.url + '/?page=look')
        page.wait_for('document.body.dataset.mode === "look" && !!document.querySelector("#strength-val").textContent',
                      what='the 纹理 page')

        def look():
            got = server.api(f'/api/doc/{doc}/look')['params']
            return got['style'], got['fade']

        # an older step, saved
        page.evaluate('document.querySelector("[data-style=loops]").click()')
        uibrowser._wait('the style to be saved', lambda: look() == ('loops', True), 10)
        # saves of the settings wait to be answered by hand, fail, or pass; undos asked of the server are counted
        # and of the requests that reach the server, the order is kept
        page.evaluate('''window.__saves = 'hold'; window.__held = []; window.__undos = 0; window.__order = [];
            const real = window.fetch;
            window.fetch = (url, opt) => {
                const to = String(url);
                if (to.includes('/undo')) { window.__undos++; window.__order.push('undo'); }
                if (opt?.method !== 'PUT' || !to.includes('/look?')) return real(url, opt);
                if (window.__saves === 'pass') { window.__order.push('save'); return real(url, opt); }
                const down = () => new Response('unavailable', {status: 503});
                if (window.__saves === 'fail') return Promise.resolve(down());
                return new Promise((go) => window.__held.push(() => go(down())));
            };''')
        failed = 'document.querySelector("#status-msg").matches(".error")'
        pause = 'new Promise((resolve) => setTimeout(resolve, 300))'

        # the case: 撤销 is pressed with nothing left to send, while the save of the last change is on its way; then
        # that save fails
        page.evaluate('document.querySelector("#fade").click()')
        page.wait_for('window.__held.length === 1', what='the save of 纹理减弱 to be on its way')
        page.evaluate('window.__saves = "fail"')
        press(page, 'z', 'KeyZ', 90, ctrl=True)
        page.evaluate('void window.__held.splice(0).forEach((answer) => answer())')
        page.wait_for(failed, what='the save failure')
        page.evaluate(pause)
        # the older step is not taken back in its place, and the change stays on screen to send again
        assert page.evaluate('[window.__undos, document.querySelector("#fade").checked]') == [0, False]
        assert look() == ('loops', True)
        # once saves work, 撤销 sends it and takes that back
        page.evaluate('window.__saves = "pass"')
        press(page, 'z', 'KeyZ', 90, ctrl=True)
        page.wait_for('!document.querySelector("#btn-redo").disabled && document.querySelector("#fade").checked',
                      what='纹理减弱 to be undone')
        # it is that change the undo took back, after the save that was tried again: going past the failure would
        # have taken the style back instead, with no save before it
        assert look() == ('loops', True)
        assert page.evaluate('window.__order') == ['save', 'undo']
        assert page.evaluate('!document.querySelector("#btn-undo").disabled')

        # the same when 全部恢复默认 follows a change at once and the save of that change fails
        page.evaluate('''window.__saves = 'hold';
            document.querySelector('#fade').click();
            document.querySelector('#btn-look-reset').click();''')
        page.wait_for('window.__held.length === 1', what='the save of 纹理减弱 to be on its way')
        page.evaluate('window.__saves = "fail"')
        press(page, 'z', 'KeyZ', 90, ctrl=True)
        page.evaluate('void window.__held.splice(0).forEach((answer) => answer())')
        page.wait_for(failed, what='the save failure')
        page.evaluate(pause)
        assert page.evaluate('window.__order') == ['save', 'undo']
        assert look() == ('loops', True)
        assert page.evaluate('document.querySelector("[data-style=knit]").getAttribute("aria-checked")') == 'true'
        # what is on screen then goes as one step, and 撤销 takes back that and no more
        page.evaluate('window.__saves = "pass"')
        press(page, 'z', 'KeyZ', 90, ctrl=True)
        page.wait_for('window.__undos === 2', what='the undo to be asked for')
        page.wait_for('document.querySelector("[data-style=loops]").getAttribute("aria-checked") === "true"',
                      timeout=10, what='the reset to be undone')
        assert look() == ('loops', True)
        assert page.evaluate('window.__order') == ['save', 'undo', 'save', 'undo']


@pytest.mark.parametrize('lang, reason', (
    ('zh', '当前设置与所选预设一致，改动后再保存'), ('en', 'The settings match the selected preset. Change them before saving.'),
))
def test_an_unchanged_preset_explains_save_without_writing(ui, lang, reason):
    server, _ = ui
    server.api('/api/look/presets', 'PUT', {'name': 'Example', 'params': {'density': 125}})
    page = show(ui, lang, 100, (360, 840), look=1)
    preset = 'document.querySelector("#preset-select")'
    page.wait_for(f'[...{preset}.options].some(o => o.value === "Example")', what='the Example preset to be listed')
    page.evaluate(f'{preset}.value = "Example"; {preset}.dispatchEvent(new Event("change", {{bubbles:true}}))')
    page.evaluate('''window.__presetWrites = window.__saveClicks = 0;
        document.querySelector('#btn-preset-save').addEventListener('click', () => window.__saveClicks++);
        const real = window.fetch;
        window.fetch = (url, opt) => {
            if (url === '/api/look/presets' && opt?.method === 'PUT') window.__presetWrites++;
            return real(url, opt);
        };''')
    save = 'document.querySelector("#btn-preset-save")'
    assert page.evaluate(f'[{save}.disabled, {save}.getAttribute("aria-disabled")]') == [False, 'true']
    page.click('#btn-preset-save')
    assert tip_text(page) == reason
    assert page.evaluate(STATUS_MSG) == reason
    page.hover('#status-msg')
    page.evaluate(f'{preset}.focus()')
    press(page, 'Tab', 'Tab', 9)
    assert page.evaluate('document.activeElement.id') == 'btn-preset-save'
    assert tip_text(page) == reason
    press(page, 'Enter', 'Enter', 13)
    press(page, ' ', 'Space', 32)
    assert page.evaluate('[window.__saveClicks, window.__presetWrites]') == [3, 0]

    page.evaluate('''const el = document.querySelector('#density');
        el.value = 126; el.dispatchEvent(new Event('input', {bubbles:true}));''')
    assert page.evaluate(f'{save}.getAttribute("aria-disabled")') == 'false'
    assert tip_text(page) not in (None, reason)
    press(page, 'Enter', 'Enter', 13)
    page.wait_for(f'{save}.getAttribute("aria-disabled") === "true"', what='the edited settings to be saved')
    assert page.evaluate('window.__presetWrites') == 1
    assert tip_text(page) == reason


@pytest.mark.parametrize('lang, size, limited', (
    ('zh', (640, 840), '140%（实际 71%）'), ('en', (360, 840), '140% (71% effective)'),
))
def test_density_shows_the_effective_value_only_at_the_spacing_floor(ui, lang, size, limited):
    page = show(ui, lang, 100, size, look=1)  # 640×960 source; the last whole percent above the floor is 71%
    density = 'document.querySelector("#density")'
    readout = 'document.querySelector("#density-val")'
    for value, text in ((140, limited), (70, '70%')):
        page.evaluate(f'{density}.value = {value}; {density}.dispatchEvent(new Event("input", {{bubbles:true}}))')
        assert page.evaluate(f'[{density}.value, {readout}.textContent]') == [str(value), text]
        assert page.evaluate('document.querySelector("#density-note").matches(".warn")') == (value == 140)
    page.evaluate(f'{density}.value = 140; {density}.dispatchEvent(new Event("input", {{bubbles:true}}))')
    assert page.evaluate(f'{density}.getAttribute("aria-valuetext")') == limited
    assert page.evaluate(f'''(() => {{
        const el = {readout}, head = el.parentElement.getBoundingClientRect();
        const label = el.previousElementSibling.getBoundingClientRect();
        const text = document.createRange();
        text.selectNodeContents(el);
        const r = text.getBoundingClientRect();
        return r.left >= label.right && r.right <= head.right && r.height <= head.height;
    }})()'''), 'the selected and effective values must fit beside Density'


# the kinds the open 导出 menu marks as the one the main button exports: [by aria-checked, by a ✓ that shows]
EXPORT_MARKED = '''(() => {
    const items = [...document.querySelectorAll('#export-menu [role=menuitemradio]')];
    const name = (b) => b.querySelector('.what > span').textContent;
    const ticked = (b) => b.querySelector('.tick').checkVisibility() && b.querySelector('.tick').innerText.trim() === '✓';
    return [items.filter((b) => b.getAttribute('aria-checked') === 'true').map(name), items.filter(ticked).map(name)];
})()'''


@pytest.mark.parametrize('outcome', ('cancel', 'ask_error', 'write_error', 'written'))
def test_the_export_menu_only_remembers_a_format_after_the_file_is_written(ui, tmp_path, outcome):
    page = show(ui, 'en', 100, (1280, 720), look=1)
    target = tmp_path / 'stockings.png' if outcome != 'write_error' else tmp_path / 'missing' / 'stockings.png'
    answer = f'Response.json({json.dumps({"cancelled": True} if outcome == "cancel" else {"path": str(target)})})'
    if outcome == 'ask_error':          # the request for the dialog itself fails
        answer = 'new Response("unavailable", {status: 503})'
    # Only the native dialog is replaced; accepting it writes through the real isolated server.
    page.evaluate('''window.__answerExport = null; window.__startWrite = null;
        const real = window.fetch;
        window.fetch = (url, opt) => {
            if (String(url).endsWith('/export/ask')) return new Promise(go => { window.__answerExport = go; });
            if (String(url).endsWith('/export')) return new Promise(go => { window.__startWrite = go; })
                .then(() => real(url, opt));
            return real(url, opt);
        };''')
    select = '#export-menu [role=menuitemradio]'
    page.click('#btn-export-more')
    page.click(f'{select}:nth-child(2)')
    page.wait_for('!!window.__answerExport', what='the export dialog to be asked for')
    main = 'document.querySelector("#btn-export").textContent'
    assert page.evaluate(main) == 'Export image…'
    page.evaluate(f'void window.__answerExport({answer})')
    if outcome in ('write_error', 'written'):
        page.wait_for('!!window.__startWrite', what='the write to be requested')
        assert page.evaluate(main) == 'Export image…'
        assert not target.exists()
        page.click('#btn-export-more')  # the menu can be reopened while the write continues
        assert page.evaluate(EXPORT_MARKED) == [['Finished image']] * 2
        page.evaluate('void window.__startWrite()')
    if outcome == 'written':
        page.wait_for('!document.querySelector("#exported").hidden', what='the export receipt')
        assert target.is_file()
    elif outcome == 'write_error':
        page.wait_for('document.querySelector("#status-msg").matches(".error")', what='the write error')
    else:
        if outcome == 'ask_error':
            page.wait_for('document.querySelector("#status-msg").matches(".error")', what='the failure to ask')
        page.wait_for('document.querySelector("#busy").hidden', what='the export dialog to close')
        assert page.evaluate('window.__startWrite') is None
    assert page.evaluate(main) == ('Export stockings…' if outcome == 'written' else 'Export image…')
    if page.evaluate('document.querySelector("#export-menu").hidden'):
        page.click('#btn-export-more')
    assert page.evaluate(EXPORT_MARKED) == [['Stockings only' if outcome == 'written' else 'Finished image']] * 2
    page.screenshot(f'export-menu-after-{outcome}-en-1280x720')
    press(page, 'Escape', 'Escape', 27)


def test_exporting_the_guides_before_opening_another_image_leaves_the_remembered_format(tmp_path):
    uibrowser.require()
    with uibrowser.running(tmp_path) as (server, browser), contextlib.closing(browser.page()) as page:
        server.set_lang('en')
        uibrowser.synthetic_document(server, w=320, h=480)
        page.goto(server.url + '/?page=look')
        page.wait_for('document.body.dataset.mode === "look" && !!document.querySelector("#strength-val").textContent',
                      what='the 纹理 page')
        stockings, guides = tmp_path / 'chosen' / 'stockings.png', tmp_path / 'chosen' / 'guides.psd'
        stockings.parent.mkdir()
        # Only the system's dialogs are replaced: the save dialog names these paths, the open dialog is cancelled.
        # The files are written by the real isolated server.
        page.evaluate(f'''window.__paths = {json.dumps([str(stockings), str(guides)])}; window.__opens = 0;
            const real = window.fetch;
            window.fetch = (url, opt) => {{
                const to = String(url);
                if (to.endsWith('/export/ask')) return Promise.resolve(Response.json({{path: window.__paths.shift()}}));
                if (to.endsWith('/api/open/dialog')) {{
                    window.__opens++;
                    return Promise.resolve(Response.json({{cancelled: true}}));
                }}
                return real(url, opt);
            }};''')
        main = 'document.querySelector("#btn-export").textContent'
        page.click('#btn-export-more')
        page.click('#export-menu [role=menuitemradio]:nth-child(2)')
        page.wait_for('!document.querySelector("#exported").hidden', what='the export receipt')
        assert stockings.is_file() and page.evaluate(main) == 'Export stockings…'
        page.click('#btn-exported-close')

        # the case: another image is asked for, and the guides are exported first from the question that brings
        page.click('#btn-open')
        page.wait_for('document.querySelector("#confirm-open").open', what='the question before opening another image')
        page.click('#confirm-open button[value="export"]')
        page.wait_for('window.__opens === 1', what='the open dialog, after the guides are exported')
        assert guides.is_file()
        page.wait_for('document.querySelector("#busy").hidden', what='the open dialog to close')
        # the main button still exports what the user last chose there
        assert page.evaluate(main) == 'Export stockings…'
        page.click('#btn-exported-close')
        page.click('#btn-export-more')
        assert page.evaluate(EXPORT_MARKED) == [['Stockings only']] * 2
        page.screenshot('export-menu-after-guides-before-open-en-1280x720')


@pytest.mark.parametrize('lang, names', (('zh', ['点选', '隔开']), ('en', ['Pick', 'Divider'])))
def test_guides_tool_shortcuts_match_their_labels_and_s_is_unassigned(ui, lang, names):
    page = show(ui, lang, 100, (1280, 720))
    page.click('[data-tool="brush"]')
    page.evaluate('document.querySelector("#stage").focus()')
    active = 'document.querySelector(".tool[aria-checked=true]").dataset.tool'
    for key, tool in (('w', 'segment'), ('s', 'segment'), ('d', 'wall'), ('s', 'wall')):
        press(page, key, f'Key{key.upper()}', ord(key.upper()))
        assert page.evaluate(active) == tool, key
    assert page.evaluate('''['segment', 'wall'].map((tool) => {
        const b = document.querySelector(`[data-tool="${tool}"]`);
        return [b.firstChild.textContent.trim(), b.querySelector('kbd').textContent, b.getAttribute('aria-keyshortcuts')];
    })''') == [[names[0], 'W', 'W'], [names[1], 'D', 'D']]


@pytest.mark.parametrize('lang, strength, brightness, contrast', (
    ('zh', '强度', '亮度', '明暗'), ('en', 'Strength', 'Brightness', 'Contrast'),
))
def test_texture_strength_and_the_two_effects_have_distinct_slider_and_help_names(ui, lang, strength, brightness, contrast):
    page = show(ui, lang, 100, (1440, 900), look=1)
    assert page.evaluate('document.querySelector("#strength").labels[0].textContent') == strength
    for effect, name in (('particle', brightness), ('moire', contrast)):
        toggle = f'#{effect}-on'
        if not page.evaluate(f'document.querySelector("{toggle}").checked'):
            page.click(toggle)
        slider = f'document.querySelector("#{effect}")'
        assert page.evaluate(f'{slider}.checkVisibility()')
        page.click(f'[aria-controls="{effect}-info"]')
        note = f'document.querySelector("#{effect}-info")'
        assert page.evaluate(f'{note}.checkVisibility()')
        assert page.evaluate(f'[{slider}.labels[0].textContent, {note}.querySelector("b").textContent]') == [name, name]


@pytest.mark.parametrize('lang, compare, fill_gaps, avoid', (
    ('zh', '原图与效果对比拖杆', '补细缝', ('角度', '细线')),
    ('en', 'Compare original and result', 'Fill gaps', ('angle', 'fine lines')),
))
def test_compare_pick_and_tilt_use_distinct_ui_terms(ui, lang, compare, fill_gaps, avoid):
    page = show(ui, lang, 100, (1440, 900), look=1)
    assert page.evaluate('document.querySelector("#compare").getAttribute("aria-label")') == compare
    assert page.evaluate('document.querySelector("#fill-seams").labels[0].textContent.trim()') == fill_gaps
    page.click('[data-style="lines"]')
    page.click('[aria-controls="tilt-info"]')
    assert page.evaluate('document.querySelector("#tilt-info").checkVisibility()')
    tilt = page.evaluate('document.querySelector("#tilt-info p").textContent').lower()
    assert '0°' in tilt and not any(word in tilt for word in avoid), tilt


def test_the_focus_stays_with_the_layers_when_their_rows_are_made_anew(ui):
    # the rows are made anew when the number of 纹理层 changes: by Delete on a layer's name, and by 撤销 after it.
    # The keyboard must not be left on nothing (the page's body) either time
    page = show(ui, 'zh', 100, (1280, 720), look=3)
    thrown = len(page.errors)
    n = page.evaluate(LAYER_ROWS)
    # the layers show() added are saved a moment after they appear: 撤销 can only bring back a layer deleted from a
    # look the server already has (the first layer is the look's own keys, the others are its `layers`)
    server, _ = ui
    doc = server.api('/api/doc')['id']
    uibrowser._wait('the added 纹理层 to be saved',
                    lambda: 1 + len(server.api(f'/api/doc/{doc}/look')['params']['layers']) == n, 10)
    focus = 'document.activeElement.id || document.activeElement.className || document.activeElement.tagName'
    page.evaluate('document.querySelector("#blend-rows > :last-child .blend-name").focus()')
    press(page, 'Delete', 'Delete', 46)
    page.wait_for(f'{LAYER_ROWS} === {n - 1}', what='a 纹理层 to go')
    assert page.evaluate(focus) == 'blend-name'
    press(page, 'z', 'KeyZ', 90, ctrl=True)
    page.wait_for(f'{LAYER_ROWS} === {n}', what='the 纹理层 to come back')
    assert page.evaluate(focus) == 'blend-name'
    assert page.evaluate('document.activeElement.getAttribute("aria-current")') == 'true'
    assert page.errors[thrown:] == []

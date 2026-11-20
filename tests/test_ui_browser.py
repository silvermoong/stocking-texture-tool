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
                         'return [a.getAttribute("aria-disabled"), a.title, document.querySelector("#status-msg").textContent]; })()')
    assert full[0] == 'true' and '4' in full[1] and '4' in full[2], full
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
        page.send('Input.dispatchKeyEvent', type=kind, key=key, code=code, windowsVirtualKeyCode=vk,
                  modifiers=2 if ctrl else 0)


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

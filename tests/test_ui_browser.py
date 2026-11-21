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
       '#btn-open', '#tab-edit', '#tab-look', '#btn-undo', '#btn-redo', '#btn-shortcuts')

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
    # 界面大小 itself was once pushed out of a narrow window, with no way back
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


@pytest.mark.parametrize('look', (False, 1), ids=('guides', 'texture'))
@pytest.mark.parametrize('scale', (100, 150, 175))
@pytest.mark.parametrize('lang', ('zh', 'en'))
def test_the_shortcut_entry_shares_the_bar_in_a_360px_window(ui, lang, scale, look):
    page = show(ui, lang, scale, (360, 840), look)
    assert bar_out_of_reach(page) == []
    assert page.evaluate('document.querySelector(".bar").scrollWidth <= innerWidth')
    page.check_errors()


@pytest.mark.parametrize('scale', (100, 150, 175))
@pytest.mark.parametrize('lang', ('zh', 'en'))
def test_tab_into_the_guides_panel_keeps_the_bar_in_a_360px_window(ui, lang, scale):
    # the panel of 引导 is as wide as the window at a large 界面大小: the focus going into it with Tab must not scroll the
    # page sideways and carry the bar, 界面大小 and the shortcut entry with it, out of the window
    page = show(ui, lang, scale, (360, 840))
    page.evaluate('document.querySelector(".lang [aria-checked=\\"true\\"], .lang .seg-btn").focus()')
    assert page.evaluate('!!document.activeElement.closest(".lang")')
    for _ in range(12):
        press(page, 'Tab', 'Tab', 9)
        if page.evaluate('document.activeElement.id') == 'btn-add-region':
            break
    assert page.evaluate('document.activeElement.id') == 'btn-add-region'
    assert page.evaluate('[document.documentElement.scrollLeft, document.body.scrollLeft, '
                         'Math.round(document.querySelector(".bar").getBoundingClientRect().left)]') == [0, 0, 0]
    assert bar_out_of_reach(page) == []
    # and the control the focus went to is itself in the window, not cut by its right edge
    assert page.evaluate('''(() => {
        const r = document.querySelector('#btn-add-region').getBoundingClientRect();
        return r.width > 0 && r.left >= 0 && r.right <= innerWidth;
    })()''')
    page.check_errors()


@pytest.mark.parametrize('scale, size, look', ((100, (1440, 900), False), (175, (360, 840), 1)),
                         ids=('guides-1440x900-100', 'texture-360x840-175'))
@pytest.mark.parametrize('lang, title, uses', (
    ('zh', '快捷键与手势', ('按住空格拖动画面', '按住空格查看细节原图', '键盘聚焦的控件自己用空格', '可用「跳到画面」',
                        '悬停高亮该范围的轮廓，单击直接选这一档')),
    ('en', 'Shortcuts and gestures', ('Hold Space and drag', 'Hold Space to see the original in Detail',
                                      'Space stays with keyboard-focused controls', '(Skip to the picture)',
                                      'hover to highlight that range\'s outline; click to choose it')),
))
def test_the_shortcut_sheet_explains_both_space_gestures_and_fits(ui, lang, title, uses, scale, size, look):
    page = show(ui, lang, scale, size, look)
    canvas = '#fit' if look else '#view'
    page.wait_for(f'''(() => {{
        const c = document.querySelector('{canvas}');
        const pixel = c.getContext('2d').getImageData(c.width >> 1, c.height >> 1, 1, 1).data;
        return pixel[3] && pixel[0] !== 84;
    }})()''', what='the synthetic artwork to be drawn')
    tag = f'shortcuts-{lang}-{scale}-{size[0]}x{size[1]}'
    page.screenshot(f'{tag}-bar')

    page.click('#btn-shortcuts')
    assert page.evaluate('''(() => {
        const d = document.querySelector('#shortcut-help:modal');
        return d && document.getElementById(d.getAttribute('aria-labelledby')).textContent;
    })()''') == title
    contents = page.evaluate('document.querySelector("#shortcut-help").innerText')
    assert all(use in contents for use in uses), contents
    assert uibrowser.out_of_reach(page, '#shortcut-help', must=('#btn-shortcuts-close',)) == []
    assert page.evaluate('''(() => {
        const d = document.querySelector('#shortcut-help'), r = d.getBoundingClientRect();
        return r.left > 0 && r.right < innerWidth && r.top > 0 && r.bottom < innerHeight
            && d.scrollWidth === d.clientWidth;
    })()''')
    # the title stays beside Close in at most two lines, so the reference keeps most of a small window
    assert page.evaluate('''(() => {
        const h = document.querySelector('#shortcut-help-title');
        return Math.round(h.getBoundingClientRect().height / parseFloat(getComputedStyle(h).lineHeight));
    })()''') <= 2
    page.screenshot(f'{tag}-open')

    page.click('#btn-shortcuts-close')
    assert page.evaluate('!document.querySelector("#shortcut-help").open && document.activeElement.id === "btn-shortcuts"')
    page.check_errors()


@pytest.mark.parametrize('lang', ('zh', 'en'))
def test_a_pressed_toggle_button_stays_readable_under_the_pointer(ui, lang):
    # L-4 of the same audit: the hover fill of every button replaced the pressed fill and left dark text on mid grey
    page = show(ui, lang, 100, (1280, 720), look=True)
    low = {}                                                # every button is measured and pictured before any fails
    for button in ('#blend-auto', '#strength-auto'):
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


@pytest.mark.parametrize('lang', ('zh', 'en'))
def test_the_check_group_reads_clearly_with_marks_off_and_on(ui, lang):
    # Show problems was a pressed button whose text had to stay readable; it is a checkbox over rows of names and
    # notes now, on the stage: every one of them must read as well as the panel's, ticked or not
    page = show(ui, lang, 100, (1280, 720), look=1)
    page.wait_for('!!document.querySelector("#fade-note").textContent', what='the rows to say what they do now')
    low = {}
    for ticked in (False, True):
        if page.evaluate('document.querySelector("#show-problems").checked') != ticked:
            page.click('#show-problems')
        page.hover('#status-msg')
        for text in ('#show-problems-name', 'label[for="fade"]', 'label[for="exclude"]', '.check-name',
                     '#fade-note', '#exclude-note', '#check-nostroke'):
            seen = uibrowser.text_contrast(page, text)
            if seen['ratio'] < 4.5:
                low[f'{text}, ticked: {ticked}'] = seen
    page.click('#show-problems')
    assert low == {}
    page.check_errors()


CHECK_WINDOWS = ((100, (1440, 900)), (100, (1024, 768)), (125, (1024, 768)), (100, (360, 840)))
CHECK_WINDOW_IDS = tuple(f'{k}-{s[0]}x{s[1]}' for k, s in CHECK_WINDOWS)
CHECK_CONTROLS = ('#show-problems', '#fade', '#exclude')


@pytest.mark.parametrize('scale, size', CHECK_WINDOWS, ids=CHECK_WINDOW_IDS)
@pytest.mark.parametrize('lang', ('zh', 'en'))
def test_the_check_group_stays_available_with_or_without_marks(ui, lang, scale, size):
    page = show(ui, lang, scale, size, look=1)
    assert page.evaluate('!!document.querySelector("#check-group #show-problems[type=checkbox]")'), \
        'Show problems leads the same group as the two switches'
    assert page.evaluate('''(() => {
        const group = document.querySelector('#check-group');
        const reset = document.querySelector('#btn-look-reset');
        return [...group.querySelectorAll('input')].map(e => e.id).join() === 'show-problems,fade,exclude'
            && !document.querySelector('.pane-head #show-problems, #btn-check')
            && !document.querySelector('.side :is(#fade, #exclude, #show-problems)')
            && reset.closest('section') === reset.closest('.side-pane').lastElementChild
            && reset.closest('section').querySelectorAll('button, input').length === 1
            && !document.querySelector('#check-faded, #check-excluded');
    })()''')
    seen = '''(() => {
        const keys = [...document.querySelectorAll('#check-group .key')].map(e => [e, getComputedStyle(e)]);
        const visible = (s) => document.querySelector(s).checkVisibility({visibilityProperty: true});
        return [document.querySelector('#show-problems').checked,
            keys.map(([e, cs]) => cs.backgroundColor),
            // dim is still plain to see: a bar faded away altogether would leave the rows with no colour again
            keys.map(([e, cs]) => +cs.opacity >= 1 ? 'full' : +cs.opacity >= 0.35 ? 'dim' : 'gone'),
            // a bar of the legend, never a box to tick: no outline, and clearly taller than it is wide
            keys.every(([e, cs]) => cs.borderTopStyle === 'none' && e.offsetWidth >= 3
                && e.offsetHeight >= 2 * e.offsetWidth
                && e.checkVisibility({visibilityProperty: true, opacityProperty: true})),
            ['#fade', '#exclude', '#peek-hint'].every(visible)];
    })()'''
    hues = ['rgb(255, 50, 60)', 'rgb(70, 160, 255)', 'rgb(255, 190, 40)']
    # not ticked: every row still shows its own colour, dimmed, so the three never read as empty boxes to tick
    assert page.evaluate(seen) == [False, hues, ['dim'] * 3, True, True]
    page.click('#show-problems')
    assert page.evaluate(seen) == [True, hues, ['full'] * 3, True, True]
    page.click('#show-problems')
    assert page.evaluate(seen) == [False, hues, ['dim'] * 3, True, True]
    page.check_errors()


# How the rows of the check group lie (how many on each line) and where each switch is: how far right of its own ?
# (`own`) and, with another row to its right on the same line, how far left of that row (`next`), both in ems of the
# group's text.
SWITCH_PLACES = '''(() => {
    const r = (e) => e.getBoundingClientRect();
    const rows = [...document.querySelectorAll('#check-group .check-row')];
    const em = parseFloat(getComputedStyle(document.querySelector('#check-group')).fontSize);
    const top = (row) => Math.round(r(row).top);
    const tops = [...new Set(rows.map(top))];
    return { perLine: tops.map((t) => rows.filter((row) => top(row) === t).length),
        switches: rows.filter((row) => row.querySelector('.switch')).map((row) => {
            const sw = r(row.querySelector('.switch')), info = r(row.querySelector('.info-btn'));
            const next = rows[rows.indexOf(row) + 1];
            const beside = next && top(next) === top(row) ? r(next) : null;
            return { left: Math.round(sw.left), own: (sw.left - info.right) / em,
                     next: beside ? (beside.left - sw.right) / em : null, inRow: sw.right <= r(row).right + 1 };
        }) };
})()'''


@pytest.mark.parametrize('lang, scale, size, lines', (
    ('zh', 100, (1100, 520), [3]), ('zh', 100, (1440, 900), [2, 1]), ('en', 100, (1024, 768), [2, 1]),
    ('zh', 125, (1024, 768), [1, 1, 1]), ('en', 125, (360, 840), [1, 1, 1]),
), ids=('zh-100-1100x520-three-abreast', 'zh-100-1440x900-two-and-one', 'en-100-1024x768-two-and-one',
        'zh-125-1024x768-stacked', 'en-125-360x840-stacked'))
def test_each_switch_stays_with_its_own_name_however_the_rows_lie(check_ui, lang, scale, size, lines):
    # a wide group once pushed each switch to the far end of its column, 20 px from the next row's name and five
    # times as far from its own: it read as the next row's switch
    server, page = check_page(check_ui, lang, scale, size)
    page.hover('.status')
    resting_places(page)
    seen = page.evaluate(SWITCH_PLACES)
    assert seen['perLine'] == lines, seen           # the window really lays the rows out this way
    assert len(seen['switches']) == 2, seen
    for sw in seen['switches']:
        assert 0 < sw['own'] <= 3 and sw['inRow'], seen                 # right after its own name and ?
        assert sw['next'] is None or sw['next'] >= 3 and sw['next'] > sw['own'], seen     # and well clear of the next row
    if lines == [1, 1, 1]:
        # one under another, the two switches line up whatever the lengths of the two names
        assert len({sw['left'] for sw in seen['switches']}) == 1, seen
    page.check_errors()


@pytest.mark.parametrize('size', ((360, 840), (320, 840)), ids=lambda s: f'{s[0]}x{s[1]}')
def test_a_question_mark_keeps_its_shape_and_stays_clear_of_its_switch_in_a_narrow_column(ui, size):
    # where a name has to wrap, the room is taken from the name: the ? stays round, and the switch never lies on it
    # (the switch's input is unseen and on top: a ? under it would turn the switch instead of opening its note)
    page = show(ui, 'en', 175, size, look=1)
    page.wait_for('!!document.querySelector("#fade-note").textContent', what='the rows to say what they do now')
    seen = page.evaluate('''(() => {
        const k = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--k'));
        const stage = document.querySelector('#stage');
        const rows = [...document.querySelectorAll('#check-group .check-row')].filter((row) => row.querySelector('.switch'));
        return { sideways: stage.scrollWidth - stage.clientWidth, rows: rows.map((row) => {
            const info = row.querySelector('.info-btn');
            info.scrollIntoView({ block: 'center' });
            const i = info.getBoundingClientRect(), sw = row.querySelector('.switch').getBoundingClientRect();
            return { size: [i.width / k, i.height / k], gap: sw.left - i.right,
                     reached: document.elementFromPoint(i.right - 2, i.top + i.height / 2) === info,
                     inRow: sw.right <= row.getBoundingClientRect().right + 1 };
        }) };
    })()''')
    assert seen['sideways'] == 0 and len(seen['rows']) == 2, seen
    for row in seen['rows']:
        assert all(abs(side - 16) <= 0.5 for side in row['size']), seen     # 16 px at 100%, as every ? of the page
        assert row['gap'] >= 2 and row['reached'] and row['inRow'], seen
    page.check_errors()


@pytest.mark.parametrize('tiny, fade, exclude', (
    (True, '现在减弱了纹理的不到 0.1%。', '现在排除了已涂部位的不到 0.1%。'),
    (False, '现在减弱了纹理的 14%。', '现在排除了已涂部位的 3.6%。'),
), ids=('under-a-tenth-of-a-percent', 'a-plain-number'))
def test_a_share_has_a_space_before_a_number_and_none_before_a_word_in_chinese(check_ui, tiny, fade, exclude):
    # "…的 14%。" takes the space Chinese sets before a number; "…的 不到 0.1%。" had it before a word, on both rows.
    # For the tiny shares only the two numbers of the public /look answer are changed; the rows say them themselves.
    server, page = check_ui
    script = page.send('Page.addScriptToEvaluateOnNewDocument', source='''(() => {
        const real = window.fetch;
        window.fetch = async (url, opt) => {
            const res = await real(url, opt);
            if (!/\\/api\\/doc\\/[^/]+\\/look(\\?|$)/.test(String(url)) || !res.ok) return res;
            const info = await res.json();
            if (info && info.check) Object.assign(info.check, {faded: 0.0005, excluded: 0.0005});
            return Response.json(info, {status: res.status});
        };
    })()''')['identifier'] if tiny else None
    try:
        check_page(check_ui, 'zh', 100, (1280, 720))
        seen = page.evaluate('''Object.fromEntries(['fade', 'exclude'].map((row) => {
            const note = document.querySelector(`#${row}-note`);
            return [row, { said: note.textContent, reserved: [...note.closest('.check-notes')
                .querySelectorAll('.measure .note')].map((e) => e.textContent) }];
        }))''')
        assert (seen['fade']['said'], seen['exclude']['said']) == (fade, exclude), seen
        # the readings laid out unseen, which keep each row as tall as its longest, say the tiny share the same way
        assert '现在减弱了纹理的不到 0.1%。' in seen['fade']['reserved'], seen
        assert '现在排除了已涂部位的不到 0.1%。' in seen['exclude']['reserved'], seen
        assert not any('的 不到' in text for row in seen.values() for text in row['reserved']), seen
    finally:
        if script:
            page.send('Page.removeScriptToEvaluateOnNewDocument', identifier=script)


def check_document(server, portrait=False, *, image_size=None):
    """A synthetic region with closely curved courses and a different-colored patch, plus a region with no line.

    Other aspect ratios keep the same objects: fit them inside the picture, with neutral pixels around them.
    """
    import cv2
    import numpy as np

    art = np.full((352, 448, 3), 157, np.uint8)
    cv2.line(art, (282, 85), (282, 248), (38, 38, 38), 116)
    cv2.ellipse(art, (255, 165), (25, 53), 7, 0, 360, (50, 50, 50), -1)
    cv2.circle(art, (307, 158), 19, (78, 162, 225), -1)
    cv2.circle(art, (390, 185), 24, (67, 67, 67), -1)
    w, h = image_size or ((448, 600) if portrait else (448, 352))
    k = min(1, w / 448, h / 352)
    aw, ah = round(448 * k), round(352 * k)
    left, top = (w - aw) // 2, (h - ah) // 2
    if k < 1:
        art = cv2.resize(art, (aw, ah), interpolation=cv2.INTER_AREA)
    if (w, h) != (aw, ah):
        art = cv2.copyMakeBorder(art, top, h - ah - top, left, w - aw - left,
                                 cv2.BORDER_CONSTANT, value=(157, 157, 157))

    def pts(*xy):
        return [v for x, y in xy for v in (x * k + left, y * k + top)]

    st = server.upload('check-sample.png', cv2.imencode('.png', art)[1].tobytes())
    doc = f'/api/doc/{st["id"]}'
    guided, missing = (r['id'] for r in st['regions'])
    server.api(f'{doc}/regions/{guided}/paint', 'POST',
               {'pts': pts((282, 85), (282, 248)), 'radius': 58 * k, 'erase': False})
    server.api(f'{doc}/regions/{missing}/paint', 'POST',
               {'pts': pts((390, 185)), 'radius': 24 * k, 'erase': False})
    for line in (((237, 96), (258, 105), (282, 109), (304, 102), (326, 90)),
                 ((237, 171), (259, 185), (282, 183), (304, 167), (326, 145)),
                 ((237, 224), (259, 218), (282, 216), (304, 222), (326, 229))):
        server.api(f'{doc}/strokes', 'POST', {'pts': pts(*line), 'hint': guided})
    uibrowser._wait('the guided region to solve',
                    lambda: server.api('/api/doc')['regions'][0]['status'] == 'ok', 30)
    return server.api('/api/doc')


@pytest.fixture(scope='module')
def check_ui_session(tmp_path_factory):
    uibrowser.require()
    with uibrowser.running(tmp_path_factory.mktemp('check-ui')) as (server, browser):
        with contextlib.closing(browser.page()) as page:
            yield server, page


@pytest.fixture
def check_ui(check_ui_session):
    """A separate page and server for tests that replace the picture or modify the check settings.

    The tab is left on an empty page between cases: an open tool page keeps sending events, and while other cases
    run nobody reads them, until the connection gives up."""
    server, page = check_ui_session
    yield server, page
    page.check_errors()
    page.send('Page.navigate', url='about:blank')


CHECK_LAYOUT_RECTS = '''(() => {
    const stage = document.querySelector('#stage'), s = stage.getBoundingClientRect();
    const rects = Object.fromEntries(['#fit', '#crop', '#peek-hint', '#check-group'].map(name => {
        const r = document.querySelector(name)?.getBoundingClientRect();
        return [name, r ? [r.left - s.left, r.top - s.top + stage.scrollTop, r.width, r.height] : null];
    }));
    const blocks = ['.whole-pane', '.detail-pane', '#check-group'].map(n => [n, document.querySelector(n).getBoundingClientRect()]);
    const on = [];
    for (let i = 0; i < 3; i++) for (let j = i + 1; j < 3; j++) {
        const [a, p] = blocks[i], [b, q] = blocks[j];
        if (Math.min(p.right, q.right) - Math.max(p.left, q.left) > 1
            && Math.min(p.bottom, q.bottom) - Math.max(p.top, q.top) > 1) on.push(a + ' on ' + b);
    }
    return {rects, on, width: stage.clientWidth, height: stage.scrollHeight,
        sideways: [stage.scrollWidth - stage.clientWidth, document.scrollingElement.scrollWidth - innerWidth]};
})()'''


def assert_check_layout(page, image_size):
    """Check geometry against the stage rather than requiring a particular dock or preview arrangement."""
    page.wait_for('!!document.querySelector("#strength-val").textContent', what='the Texture page')
    assert page.evaluate('!!document.querySelector("#check-group")'), 'the previews share a stage with the check group'
    page.evaluate('new Promise(go => requestAnimationFrame(() => requestAnimationFrame(go)))')
    view = page.evaluate(CHECK_LAYOUT_RECTS)
    rects = view['rects']
    assert max(view['sideways']) <= 1, view
    assert view['on'] == [], view            # the two panes, rows of controls and all, and the group: none on another
    for name, (x, y, w, h) in rects.items():
        assert min(w, h) > 0 and x >= -1 and x + w <= view['width'] + 1, (name, view)
        assert y >= -1 and y + h <= view['height'] + 1, (name, view)
    for i, (name, (x, y, w, h)) in enumerate(rects.items()):
        for other, (ox, oy, ow, oh) in list(rects.items())[i + 1:]:
            assert min(x + w, ox + ow) - max(x, ox) <= 1 or min(y + h, oy + oh) - max(y, oy) <= 1, (name, other, view)
    _, _, fw, fh = rects['#fit']
    _, cy, cw, ch = rects['#crop']
    iw, ih = image_size
    assert max(fw, fh) >= 48 and abs(fw * ih - fh * iw) <= max(iw, ih) + 1, (image_size, view)
    assert cw >= 48 and abs(cw - ch) <= 1, view
    assert rects['#peek-hint'][1] >= cy + ch - 1, view
    return view


@pytest.mark.parametrize('image_size, size, scale', (
    ((1792, 352), (1600, 800), 100), ((448, 1792), (820, 1200), 125), ((448, 448), (1024, 768), 125),
    ((96, 80), (360, 840), 100),
), ids=('wide-on-wide', 'tall-on-portrait', 'square-at-125', 'small-on-narrow'))
def test_preview_and_check_group_layout_across_image_shapes(check_ui, image_size, size, scale):
    server, page = check_ui
    server.set_lang('en')
    check_document(server, image_size=image_size)
    show(check_ui, 'en', scale, size, look=1)
    initial = assert_check_layout(page, image_size)
    page.resize(1024, 560)
    assert_check_layout(page, image_size)
    page.resize(*size)
    # The best dock may legitimately be the same after a round trip, or an adjacent one within a hysteresis band.
    # At a settled size, the measurements must stay steady and neither scroll nor overlap.
    settled = assert_check_layout(page, image_size)
    assert settled == assert_check_layout(page, image_size)
    if size != (1024, 560):
        assert initial['width'] == settled['width']
    page.check_errors()


SHOW_PROBLEMS_WINDOWS = ((100, (1280, 720)), (150, (1024, 768)), (175, (1024, 768)), (100, (360, 840)),
                         (175, (360, 840)), (175, (360, 1240)))
SHOW_PROBLEMS_IDS = tuple(f'{k}-{s[0]}x{s[1]}' for k, s in SHOW_PROBLEMS_WINDOWS)


def resting_places(page, timeout=60):
    """Where the controls and pictures of the previews are, measured from the stage's own corner (so scrolling the
    stage does not count), once both previews are drawn and two looks a moment apart agree."""
    look = '''(() => {
        const c = document.querySelector('#crop');
        if (c.width < 2 || !/^(缩到窗口|Scaled)/.test(document.querySelector('#fit-status').textContent)) return null;
        const o = document.querySelector('#look-stage').getBoundingClientRect();
        return Object.fromEntries(['#show-problems', '#fade', '#exclude', '#check-group', '#peek-hint',
                '[data-zoom="1"]', '#btn-densest', '#fit', '#crop'].map((s) => {
            const r = document.querySelector(s).getBoundingClientRect();
            return [s, [r.left - o.left, r.top - o.top, r.width, r.height].map(Math.round)];
        }));
    })()'''
    last = [None]

    def steady():
        now = page.evaluate(look)
        same, last[0] = now is not None and now == last[0], now
        return now if same else None
    return uibrowser._wait('the previews to come to rest', steady, timeout, every=0.3)


def press_show_problems(page, pressed):
    page.click('#show-problems')
    page.wait_for(f'document.querySelector("#show-problems").checked === {str(pressed).lower()}',
                  what=f'Show problems to be {"ticked" if pressed else "cleared"}')
    page.hover('.status')


@pytest.mark.parametrize('scale, size', SHOW_PROBLEMS_WINDOWS, ids=SHOW_PROBLEMS_IDS)
@pytest.mark.parametrize('lang', ('zh', 'en'))
def test_show_problems_leaves_the_previews_where_they_were(ui, lang, scale, size):
    # the button now sits in the row above the picture it marks: pressing it must not move or resize that picture,
    # the button itself or the controls beside it, whether the legend takes one line or three
    page = show(ui, lang, scale, size, look=1)
    before = resting_places(page)
    press_show_problems(page, True)
    marked = resting_places(page)
    press_show_problems(page, False)
    after = resting_places(page)
    assert (marked, after) == (before, before)
    page.check_errors()


def test_show_problems_layout_stays_put_when_detail_moves_to_a_new_position(ui):
    page = show(ui, 'en', 175, (360, 1240), look=1)
    before = resting_places(page)
    page.evaluate('document.querySelector("#crop").focus()')
    press(page, 'ArrowRight', 'ArrowRight', 39)
    page.wait_for('!document.querySelector("#btn-densest").disabled', what='Detail to move away from the densest spot')
    assert resting_places(page) == before
    page.click('#btn-densest')
    page.wait_for('document.querySelector("#btn-densest").disabled', what='Detail to return to the densest spot')
    assert resting_places(page) == before
    page.check_errors()


def test_show_problems_layout_stays_put_when_a_switch_changes_what_its_row_says(ui):
    # the share is said once, on the row of its switch: from a share to "Off: …" and back, a shorter and a longer
    # reading, neither the row nor anything else of the previews may move
    page = show(ui, 'en', 175, (910, 768), look=1)
    said = 'document.querySelector("#fade-note").textContent'
    page.wait_for(f'{said} === "under 0.1% of the texture is faded now."', what='the initial faded share')
    before = resting_places(page)
    page.click('#fade')
    page.wait_for(f'{said}.startsWith("Off:")', what='the row to say the switch is off')
    page.hover('.status')
    after = resting_places(page)
    page.click('#fade')
    page.wait_for(f'{said} === "under 0.1% of the texture is faded now."', what='the original share to return')
    page.hover('.status')
    assert (after, resting_places(page)) == (before, before)
    page.check_errors()


@pytest.mark.parametrize('scale, size', SHOW_PROBLEMS_WINDOWS, ids=SHOW_PROBLEMS_IDS)
@pytest.mark.parametrize('lang', ('zh', 'en'))
def test_show_problems_layout_keeps_the_compare_labels_on_the_whole_preview(ui, lang, scale, size):
    # with the settings below the stage a narrow window has a small 整体: its two labels must not hang out of the
    # picture or lie on each other
    page = show(ui, lang, scale, size, look=1)
    resting_places(page)
    seen = page.evaluate('''(() => {
        const fit = document.querySelector('#fit').getBoundingClientRect();
        const tags = ['#compare-before', '#compare-after'].map((s) => document.querySelector(s))
            .filter((el) => el.checkVisibility({ visibilityProperty: true })).map((el) => el.getBoundingClientRect());
        return {
            fit: [Math.round(fit.left), Math.round(fit.right)],
            outside: tags.filter((r) => r.left < fit.left - 1 || r.right > fit.right + 1)
                .map((r) => [Math.round(r.left), Math.round(r.right)]),
            overlapping: tags.length === 2 && tags[0].right > tags[1].left,
            onSlider: (() => {
                const c = document.querySelector('#compare').getBoundingClientRect(), x = c.left + c.width / 2;
                return tags.some((r) => r.left < x + 1 && r.right > x - 1);
            })(),
            shown: tags.length,
        };
    })()''')
    # neither hangs out of the picture, lies on the other, or lies on the slider's line where it rests
    assert (seen['outside'], seen['overlapping'], seen['onSlider']) == ([], False, False), seen
    # they are left out only where the picture is too small for them: a wide window still names both sides
    if size[0] >= 1024:
        assert seen['shown'] == 2, seen


@pytest.mark.parametrize('lang, size, layers', (
    ('zh', (360, 840), 1), ('en', (360, 840), 1), ('en', (720, 480), 4), ('en', (800, 600), 1), ('en', (1024, 480), 1),
), ids=('zh-360x840', 'en-360x840', 'en-720x480-four-layers', 'en-800x600', 'en-1024x480'))
def test_show_problems_controls_can_be_scrolled_to_in_a_short_window(ui, lang, size, layers):
    # At 175% a short stage can run out of height even in a window wider than a phone. Keep room for the pictures
    # and reach every control by scrolling the stage alone, even with a long list of settings below it.
    page = show(ui, lang, 175, size, look=layers)
    pix = page.evaluate('''['#fit', '#crop'].map(s => {
        const r = document.querySelector(s).getBoundingClientRect(); return [r.width, r.height];
    })''')
    assert min(min(p) for p in pix) >= 32, pix
    resting_places(page)
    press_show_problems(page, True)
    resting_places(page)
    seen = page.evaluate('''(() => {
        const stage = document.querySelector('#stage'), out = [];
        for (const el of document.querySelectorAll('#look-stage button, #look-stage input, #look-stage canvas, #compare')) {
            if (!el.checkVisibility({ visibilityProperty: true })) continue;
            el.scrollIntoView({ block: 'center', inline: 'nearest' });
            const s = stage.getBoundingClientRect(), r = el.getBoundingClientRect();
            const name = el.id ? '#' + el.id : el.textContent.trim();
            const x = r.left + r.width / 2, y = r.top + r.height / 2;
            const top = document.elementFromPoint(x, y);
            const at = `${Math.round(r.left)}..${Math.round(r.right)} x ${Math.round(r.top)}..${Math.round(r.bottom)}`;
            if (r.left < s.left - 1 || r.right > s.right + 1) out.push(`${name} is cut off sideways (${at})`);
            else if (y < s.top || y > s.bottom) out.push(`${name} cannot be scrolled onto the stage (${at})`);
            // the compare slider starts on the middle of 整体, as it always has: that is not something in the way
            else if (!top || !(el === top || el.contains(top) || el.id === 'fit' && top.closest('#compare')))
                out.push(`${name} is covered (${at})`);
        }
        const page = document.scrollingElement;
        return { out, sideways: stage.scrollWidth - stage.clientWidth, page: [page.scrollWidth, page.scrollLeft, page.scrollTop],
                 canScroll: stage.scrollHeight <= stage.clientHeight || ['auto', 'scroll'].includes(getComputedStyle(stage).overflowY),
                 status: Math.round(document.querySelector('.status').getBoundingClientRect().bottom) };
    })()''')
    page.screenshot(f'show-problems-short-{lang}-175-{size[0]}x{size[1]}')
    assert seen == {'out': [], 'sideways': 0, 'page': [size[0], 0, 0], 'canScroll': True, 'status': size[1]}, seen
    page.check_errors()


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
        const settings = document.querySelector('#pane-look');
        const whole = ['#sparkle-on', '#particle-on', '#moire-on'].every((s) => {
            const el = document.querySelector(s);
            return settings.contains(el) && !card.contains(el) && (note.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING);
        }) && ['#fade', '#exclude'].every((s) => {      // the whole picture's too, with the marks they cause
            const el = document.querySelector(s);
            return !card.contains(el) && !!el.closest('#look-stage #check-group');
        });
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


def press(page, key, code, vk, ctrl=False, shift=False):
    """A key pressed and released, as the keyboard sends it to whatever has the focus."""
    for kind in ('keyDown', 'keyUp'):
        text = (key if len(key) == 1 else {'Enter': '\r'}.get(key, '')) if kind == 'keyDown' and not ctrl else ''
        page.send('Input.dispatchKeyEvent', type=kind, key=key, code=code, windowsVirtualKeyCode=vk,
                  text=text, modifiers=(2 if ctrl else 0) | (8 if shift else 0))


def test_the_shortcut_sheet_opens_before_a_picture_and_closes_without_click_through(tmp_path):
    uibrowser.require()
    with uibrowser.running(tmp_path) as (server, browser), contextlib.closing(browser.page()) as page:
        page.goto(server.url + '/')
        page.evaluate('document.querySelector("#stage").focus()')
        is_open = 'document.querySelector("#shortcut-help").open'
        press(page, '?', 'Slash', 191, ctrl=True, shift=True)
        assert not page.evaluate(is_open)
        press(page, '?', 'Slash', 191, shift=True)
        assert page.evaluate(is_open)
        assert page.evaluate('document.activeElement.id') == 'btn-shortcuts-close'
        press(page, '?', 'Slash', 191, shift=True)
        assert not page.evaluate(is_open)
        assert page.evaluate('document.activeElement.id') == 'stage'

        press(page, '?', 'Slash', 191, shift=True)
        press(page, 'Escape', 'Escape', 27)
        assert not page.evaluate(is_open)
        assert page.evaluate('document.activeElement.id') == 'stage'

        page.click('#btn-shortcuts')
        page.click('#shortcut-help-title')
        assert page.evaluate(is_open)
        # The click only closes this sheet; it must not activate anything under the backdrop.
        page.evaluate('''window.__backdropClicks = 0;
            document.querySelector('#btn-open').addEventListener('click', (e) => {
                window.__backdropClicks++;
                e.stopImmediatePropagation();
            }, true);''')
        page.click('#btn-open')
        assert not page.evaluate(is_open)
        assert page.evaluate('window.__backdropClicks') == 0
        assert page.evaluate('document.activeElement.id') == 'btn-shortcuts'


def test_question_mark_does_not_interrupt_an_input_a_menu_or_existing_help(ui):
    page = show(ui, 'en', 100, (1280, 900))
    is_open = 'document.querySelector("#shortcut-help").open'
    page.evaluate('document.querySelector("#region-list .current .pick").focus()')
    press(page, 'F2', 'F2', 113)
    press(page, '?', 'Slash', 191, shift=True)
    assert page.evaluate('document.activeElement.value') == '?'
    assert not page.evaluate(is_open)
    press(page, 'Escape', 'Escape', 27)

    page.click('#btn-export-more')
    press(page, '?', 'Slash', 191, shift=True)
    assert page.evaluate('!document.querySelector("#export-menu").hidden')
    assert not page.evaluate(is_open)
    press(page, 'Escape', 'Escape', 27)
    assert page.evaluate('document.querySelector("#export-menu").hidden')

    page.evaluate('document.querySelector("#ui-scale").focus()')
    press(page, '?', 'Slash', 191, shift=True)
    assert not page.evaluate(is_open)

    page = show(ui, 'en', 100, (1280, 900), look=1)
    page.click('[aria-controls="sparkle-info"]')
    press(page, '?', 'Slash', 191, shift=True)
    assert page.evaluate('document.querySelector("#sparkle-info").checkVisibility()')
    assert not page.evaluate(is_open)
    page.click('#btn-preset-save')
    assert page.evaluate('document.querySelector("#preset-dialog").open')
    press(page, '?', 'Slash', 191, shift=True)
    assert page.evaluate('document.activeElement.value') == '?'
    assert not page.evaluate(is_open)
    press(page, 'Escape', 'Escape', 27)
    assert not page.evaluate('document.querySelector("#preset-dialog").open')
    page.check_errors()


def test_space_still_pans_guides_and_peeks_in_texture_after_closing_the_sheet(ui):
    page = show(ui, 'en', 100, (1280, 900))
    page.evaluate('document.querySelector("#stage").focus()')
    press(page, '?', 'Slash', 191, shift=True)
    press(page, 'Escape', 'Escape', 27)
    page.hover('#view')
    position = 'document.querySelector("#status-pos").textContent'
    before = page.evaluate(position)
    assert before
    page.send('Input.dispatchKeyEvent', type='keyDown', key=' ', code='Space', windowsVirtualKeyCode=32, text=' ')
    canvas_mark(page, 'left', dx=60)
    page.send('Input.dispatchKeyEvent', type='keyUp', key=' ', code='Space', windowsVirtualKeyCode=32)
    page.hover('#view')
    assert page.evaluate(position) and page.evaluate(position) != before

    page = show(ui, 'en', 100, (1280, 900), look=1)
    page.evaluate('document.querySelector("#crop").focus()')
    press(page, '?', 'Slash', 191, shift=True)
    press(page, 'Escape', 'Escape', 27)
    assert page.evaluate('document.activeElement.id') == 'crop'
    peek = 'document.querySelector("#peek-hint").classList.contains("on")'
    page.send('Input.dispatchKeyEvent', type='keyDown', key=' ', code='Space', windowsVirtualKeyCode=32, text=' ')
    assert page.evaluate(peek)
    page.send('Input.dispatchKeyEvent', type='keyUp', key=' ', code='Space', windowsVirtualKeyCode=32)
    assert not page.evaluate(peek)
    page.check_errors()


def test_the_sheet_returns_the_focus_without_changing_what_space_does_on_that_control(ui):
    # A control the mouse clicked keeps the focus and Space still pans or peeks; a control the keyboard reached keeps
    # Space for itself. The sheet hands the focus back when it closes, and must hand it back as it found it.
    is_open = 'document.querySelector("#shortcut-help").open'
    focused = 'document.activeElement.id || document.activeElement.dataset.zoom'

    def through_the_sheet(page, close):
        if close is None:
            return
        press(page, '?', 'Slash', 191, shift=True)
        assert page.evaluate(is_open)
        if close == 'outside':
            page.click('#btn-open')
        elif close == '?':
            press(page, '?', 'Slash', 191, shift=True)
        else:
            press(page, 'Escape', 'Escape', 27)
        assert not page.evaluate(is_open)

    def space(page, kind):
        page.send('Input.dispatchKeyEvent', type=kind, key=' ', code='Space', windowsVirtualKeyCode=32,
                  **({'text': ' '} if kind == 'keyDown' else {}))

    page = show(ui, 'en', 100, (1280, 900))
    position = 'document.querySelector("#status-pos").textContent'
    for close in (None, 'Escape', '?'):
        page.click('#btn-fit')
        through_the_sheet(page, close)
        assert page.evaluate(focused) == 'btn-fit'
        page.hover('#view')
        before = page.evaluate(position)
        assert before
        space(page, 'keyDown')
        canvas_mark(page, 'left', dx=60)
        space(page, 'keyUp')
        page.hover('#view')
        assert page.evaluate(position) != before, f'Space did not pan after a clicked control (sheet closed by {close})'

    page = show(ui, 'en', 100, (1280, 900), look=1)
    zoom = '.seg-btn[data-zoom][aria-checked="true"]'
    peek = 'document.querySelector("#peek-hint").classList.contains("on")'
    for close in (None, 'Escape', '?'):
        page.click(zoom)
        through_the_sheet(page, close)
        assert page.evaluate(focused) == page.evaluate(f"document.querySelector('{zoom}').dataset.zoom")
        space(page, 'keyDown')
        assert page.evaluate(peek), f'Space did not peek after a clicked control (sheet closed by {close})'
        space(page, 'keyUp')
        assert not page.evaluate(peek)

    # the same control, reached with the keyboard this time: Space presses it, whichever way the sheet closed
    for close in (None, 'Escape', '?', 'outside'):
        press(page, 'Shift', 'ShiftLeft', 16)
        page.evaluate(f"(() => {{ const b = document.querySelector('{zoom}'); b.blur(); b.focus(); }})()")
        through_the_sheet(page, close)
        assert page.evaluate(focused) == page.evaluate(f"document.querySelector('{zoom}').dataset.zoom")
        space(page, 'keyDown')
        assert not page.evaluate(peek), f'Space peeked on a control the keyboard reached (sheet closed by {close})'
        space(page, 'keyUp')
    page.check_errors()


def test_a_question_over_the_sheet_does_not_lose_how_the_control_got_the_focus(tmp_path):
    # A file handed over from outside asks its question on top of the open sheet. The sheet stays open under it, `?`
    # is the question's, and the clicked control still gets the focus back as a clicked one: Space pans after it.
    uibrowser.require()
    with uibrowser.running(tmp_path) as (server, browser), contextlib.closing(browser.page(1280, 900)) as page:
        server.set_lang('en')
        uibrowser.synthetic_document(server, w=320, h=480)
        second = tmp_path / 'second.png'
        second.write_bytes(uibrowser.synthetic_png(320, 480))
        page.goto(server.url + '/')
        page.wait_for('!document.body.classList.contains("no-doc")', what='the document to show')
        help_open = 'document.querySelector("#shortcut-help").open'
        asking = 'document.querySelector("#confirm-open").open'
        position = 'document.querySelector("#status-pos").textContent'

        page.click('#btn-fit')
        press(page, '?', 'Slash', 191, shift=True)
        assert page.evaluate(help_open)
        assert server.api('/api/open/path', 'POST', {'path': str(second), 'ask': True})['pending'] is True
        page.wait_for(asking, what='the question about the guides not exported')
        press(page, '?', 'Slash', 191, shift=True)
        assert page.evaluate(asking) and page.evaluate(help_open)
        press(page, 'Escape', 'Escape', 27)
        page.wait_for(f'!{asking}', what='the question to close')
        assert page.evaluate(help_open)
        press(page, 'Escape', 'Escape', 27)
        assert not page.evaluate(help_open)
        assert page.evaluate('document.activeElement.id') == 'btn-fit'

        page.hover('#view')
        before = page.evaluate(position)
        assert before
        page.send('Input.dispatchKeyEvent', type='keyDown', key=' ', code='Space', windowsVirtualKeyCode=32, text=' ')
        canvas_mark(page, 'left', dx=60)
        page.send('Input.dispatchKeyEvent', type='keyUp', key=' ', code='Space', windowsVirtualKeyCode=32)
        page.hover('#view')
        assert page.evaluate(position) != before, 'Space did not pan after the clicked control got the focus back'
        page.check_errors()


def test_keys_do_not_reach_the_page_behind_the_open_sheet_wherever_it_was_clicked(ui):
    # a click on the sheet's title, the empty part of its head or its text leaves the focus in the sheet: the tool keys
    # and Space stay with it and do nothing to the page behind
    is_open = 'document.querySelector("#shortcut-help").open'
    in_sheet = '!!document.activeElement.closest("#shortcut-help")'
    segment = 'document.querySelector("#stage").classList.contains("tool-segment")'
    page = show(ui, 'en', 100, (1280, 900))
    assert page.evaluate(segment)
    press(page, '?', 'Slash', 191, shift=True)
    for spot in ('#shortcut-help-title', '.shortcuts-head', '.shortcuts-space dd', '.shortcut-rows dd'):
        page.click(spot)
        assert page.evaluate(is_open) and page.evaluate(in_sheet), spot
        press(page, 'b', 'KeyB', 66)
        assert page.evaluate(segment), f'B changed the tool behind the sheet after a click on {spot}'
    page.click('#shortcut-help-title')
    where = '[document.hasFocus(), document.activeElement.id || document.activeElement.tagName]'
    for n in range(8):                      # Tab goes round the sheet and past its end, where nothing of the page is
        press(page, 'Tab', 'Tab', 9)
        at = page.evaluate(where)
        press(page, 'b', 'KeyB', 66)
        assert page.evaluate(segment), f'B changed the tool behind the sheet after Tab {n + 1}, focus at {at}'
        assert page.evaluate(is_open)
    press(page, 'Escape', 'Escape', 27)

    page = show(ui, 'en', 100, (1280, 900), look=1)
    peek = 'document.querySelector("#peek-hint").classList.contains("on")'
    press(page, '?', 'Slash', 191, shift=True)
    for spot in ('#shortcut-help-title', '.shortcuts-head', '.shortcuts-space dd'):
        page.click(spot)
        assert page.evaluate(is_open) and page.evaluate(in_sheet), spot
        page.send('Input.dispatchKeyEvent', type='keyDown', key=' ', code='Space', windowsVirtualKeyCode=32, text=' ')
        peeked = page.evaluate(peek)
        page.send('Input.dispatchKeyEvent', type='keyUp', key=' ', code='Space', windowsVirtualKeyCode=32)
        assert not peeked, f'Space showed the original behind the sheet after a click on {spot}'
        assert page.evaluate(is_open), f'Space closed the sheet after a click on {spot}'
    page.click('#shortcut-help-title')
    for n in range(8):
        press(page, 'Tab', 'Tab', 9)
        at = page.evaluate(where)
        if at[1] == 'btn-shortcuts-close':  # Space is that button's: it closes the sheet, as it says
            continue
        page.send('Input.dispatchKeyEvent', type='keyDown', key=' ', code='Space', windowsVirtualKeyCode=32, text=' ')
        peeked = page.evaluate(peek)
        page.send('Input.dispatchKeyEvent', type='keyUp', key=' ', code='Space', windowsVirtualKeyCode=32)
        assert not peeked, f'Space showed the original behind the sheet after Tab {n + 1}, focus at {at}'
        assert page.evaluate(is_open)
    press(page, 'Escape', 'Escape', 27)
    page.check_errors()


def test_the_sheet_returns_the_focus_to_a_region_whose_row_was_made_anew_under_it(tmp_path):
    # The region rows are made anew on every state change, a solve that ends while the sheet is open among them. The
    # button that had the focus is gone by then: the focus goes back to the same button of the same region's new row.
    uibrowser.require()
    with uibrowser.running(tmp_path) as (server, browser), contextlib.closing(browser.page(1280, 900)) as page:
        server.set_lang('zh')
        before = uibrowser.synthetic_document(server)
        doc, left = before['id'], before['regions'][0]['id']
        page.goto(server.url + '/')
        page.wait_for('!!document.querySelector("#region-list .current .pick")', what='the region list')
        help_open = 'document.querySelector("#shortcut-help").open'
        page.evaluate('document.querySelector("#region-list .current .pick").focus()')
        assert page.evaluate('document.activeElement.closest(".region").dataset.id') == str(left)
        press(page, '?', 'Slash', 191, shift=True)
        assert page.evaluate(help_open)

        server.api(f'/api/doc/{doc}/strokes', 'POST',
                   {'pts': [190, 445, 220, 450, 250, 452, 285, 449, 300, 444], 'hint': left})
        page.wait_for('/^4 条走向线，求解/.test(document.querySelector("#region-list .current .meta").textContent)',
                      timeout=60, what='the fourth direction line to be solved and shown')
        assert page.evaluate(help_open)

        press(page, 'Escape', 'Escape', 27)
        assert not page.evaluate(help_open)
        press(page, 'F2', 'F2', 113)
        assert page.evaluate('[document.activeElement.name, document.activeElement.closest(".region")?.dataset.id]') \
            == ['region-name', str(left)], 'F2 did not rename the region that had the focus before the sheet'
        press(page, 'Escape', 'Escape', 27)
        page.check_errors()


def test_a_refresh_from_the_server_keeps_how_a_region_button_got_the_focus(tmp_path):
    # The region rows are made anew when a solve ends, and the focus is put back on the same button of the new row.
    # That is not the user moving the focus: a button the mouse clicked is still a clicked one, and Space still pans,
    # whatever key was pressed last (the ones that opened and closed the sheet, here).
    uibrowser.require()
    with uibrowser.running(tmp_path) as (server, browser), contextlib.closing(browser.page(1280, 900)) as page:
        server.set_lang('zh')
        before = uibrowser.synthetic_document(server)
        doc, left = before['id'], before['regions'][0]['id']
        page.goto(server.url + '/')
        page.wait_for('!!document.querySelector("#region-list .current .pick")', what='the region list')
        position = 'document.querySelector("#status-pos").textContent'
        on_pick = ('document.activeElement.matches("#region-list .current .pick") && '
                   f'document.activeElement.closest(".region").dataset.id === "{left}"')

        def space_pans():
            page.hover('#view')
            was = page.evaluate(position)
            assert was
            page.send('Input.dispatchKeyEvent', type='keyDown', key=' ', code='Space', windowsVirtualKeyCode=32, text=' ')
            canvas_mark(page, 'left', dx=60)
            page.send('Input.dispatchKeyEvent', type='keyUp', key=' ', code='Space', windowsVirtualKeyCode=32)
            page.hover('#view')
            return page.evaluate(position) != was

        page.click('#region-list .current .pick')
        assert page.evaluate(on_pick)
        press(page, '?', 'Slash', 191, shift=True)
        assert page.evaluate('document.querySelector("#shortcut-help").open')
        press(page, 'Escape', 'Escape', 27)
        assert not page.evaluate('document.querySelector("#shortcut-help").open')
        assert page.evaluate(on_pick)
        # Space is the picture's after the sheet closed (no pointer press here: one would itself say "clicked" again)
        page.send('Input.dispatchKeyEvent', type='keyDown', key=' ', code='Space', windowsVirtualKeyCode=32, text=' ')
        panning = page.evaluate('document.querySelector("#stage").classList.contains("panning")')
        page.send('Input.dispatchKeyEvent', type='keyUp', key=' ', code='Space', windowsVirtualKeyCode=32)
        assert panning, 'Space did not start panning after the sheet closed'
        assert page.evaluate(on_pick)

        server.api(f'/api/doc/{doc}/strokes', 'POST',
                   {'pts': [190, 445, 220, 450, 250, 452, 285, 449, 300, 444], 'hint': left})
        page.wait_for('/^4 条走向线，求解/.test(document.querySelector("#region-list .current .meta").textContent)',
                      timeout=60, what='the fourth direction line to be solved and shown')
        assert page.evaluate(on_pick)
        assert space_pans(), 'Space did not pan after the rows were made anew under a clicked button'

        # the other way round: the same button reached with the keyboard, the sheet closed with the mouse. Space is
        # still the button's after the next news from the server
        press(page, 'ArrowDown', 'ArrowDown', 40)
        press(page, 'ArrowUp', 'ArrowUp', 38)
        assert page.evaluate(on_pick)
        press(page, '?', 'Slash', 191, shift=True)
        assert page.evaluate('document.querySelector("#shortcut-help").open')
        page.click('#btn-open')                     # outside the sheet: closes it, and nothing else
        assert not page.evaluate('document.querySelector("#shortcut-help").open')
        assert page.evaluate(on_pick)
        server.api(f'/api/doc/{doc}/strokes', 'POST',
                   {'pts': [190, 600, 220, 605, 250, 607, 285, 604, 300, 599], 'hint': left})
        page.wait_for('/^5 条走向线，求解/.test(document.querySelector("#region-list .current .meta").textContent)',
                      timeout=60, what='the fifth direction line to be solved and shown')
        assert page.evaluate(on_pick)
        page.send('Input.dispatchKeyEvent', type='keyDown', key=' ', code='Space', windowsVirtualKeyCode=32, text=' ')
        panning = page.evaluate('document.querySelector("#stage").classList.contains("panning")')
        page.send('Input.dispatchKeyEvent', type='keyUp', key=' ', code='Space', windowsVirtualKeyCode=32)
        assert not panning, 'Space panned on a button the keyboard reached, after the rows were made anew'

        # and a click is still a click: the same button, focused with the keyboard, then clicked by the user. The row
        # is made anew because of that click, and is judged by it
        assert page.evaluate(on_pick)
        page.click('#region-list .current .pick')
        assert page.evaluate(on_pick)
        assert space_pans(), 'Space did not pan after the user clicked the button the keyboard had focused'
        page.check_errors()


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


@pytest.mark.parametrize('lang', ('zh', 'en'))
def test_color_exclusion_has_no_permanent_scope_note(ui, lang):
    page = show(ui, lang, 100, (360, 840), look=1)
    assert page.evaluate('document.querySelector("#exclude-scope") === null')
    assert page.evaluate('document.querySelector("#exclude").getAttribute("aria-describedby")') is None


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


@pytest.mark.parametrize('lang, scope', (
    ('zh', '保存纹理设置。不含颜色排除、部位和走向线。'),
    ('en', 'Saves texture settings, not color exclusion, regions or direction lines.'),
), ids=('zh', 'en'))
def test_the_save_preset_tooltip_explains_what_an_overwrite_keeps(ui, lang, scope):
    server, _ = ui
    name = 'Sample weave'
    server.api('/api/look/presets', 'PUT', {'name': name, 'params': {'density': 125}})
    page = show(ui, lang, 100, (1280, 720), look=1)
    preset = 'document.querySelector("#preset-select")'
    save = 'document.querySelector("#btn-preset-save")'
    page.wait_for(f'[...{preset}.options].some(o => o.value === {json.dumps(name)})', what='the saved name to be available')
    pick_preset(page, name)
    assert page.evaluate(f'{save}.getAttribute("aria-disabled")') == 'true'
    page.click('[data-style=loops]')
    assert page.evaluate(f'{save}.getAttribute("aria-disabled")') == 'false'
    page.wait_for('/^(缩到窗口|Scaled)/.test(document.querySelector("#fit-status").textContent)',
                  what='Whole to be drawn')

    page.hover('#btn-preset-save')
    mouse_tip = tip_text(page)
    page.screenshot(f'preset-save-{lang}-1280x720-tooltip')
    assert mouse_tip and scope in mouse_tip and name in mouse_tip, mouse_tip
    # what is saved and what the button does now are two sentences, each on its own line of the tip
    lines = mouse_tip.split('\n')
    assert len(lines) == 2 and lines[0] == scope and name in lines[1], mouse_tip
    assert page.evaluate(f'getComputedStyle({TIP}).whiteSpace') in ('pre-line', 'pre-wrap')
    page.hover('.status')
    page.evaluate(f'{preset}.focus()')
    press(page, 'Tab', 'Tab', 9)
    assert page.evaluate('document.activeElement.id') == 'btn-preset-save'
    assert tip_text(page) == mouse_tip
    assert page.evaluate(f'{save}.getAttribute("aria-description")') == mouse_tip
    page.check_errors()


@pytest.mark.parametrize('lang, reason, scope', (
    ('zh', '当前设置与所选预设一致，改动后再保存', '保存纹理设置。不含颜色排除、部位和走向线。'),
    ('en', 'The settings match the selected preset. Change them before saving.',
     'Saves texture settings, not color exclusion, regions or direction lines.'),
), ids=('zh', 'en'))
def test_an_unchanged_preset_explains_save_without_writing(ui, lang, reason, scope):
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
    unchanged_tip = tip_text(page)
    assert unchanged_tip == f'{scope}\n{reason}', unchanged_tip
    assert page.evaluate(STATUS_MSG) == reason
    page.hover('#status-msg')
    page.evaluate(f'{preset}.focus()')
    press(page, 'Tab', 'Tab', 9)
    assert page.evaluate('document.activeElement.id') == 'btn-preset-save'
    assert tip_text(page) == unchanged_tip
    press(page, 'Enter', 'Enter', 13)
    press(page, ' ', 'Space', 32)
    assert page.evaluate('[window.__saveClicks, window.__presetWrites]') == [3, 0]
    assert page.evaluate(STATUS_MSG) == reason

    page.evaluate('''const el = document.querySelector('#density');
        el.value = 126; el.dispatchEvent(new Event('input', {bubbles:true}));''')
    assert page.evaluate(f'{save}.getAttribute("aria-disabled")') == 'false'
    assert scope in (tip_text(page) or '') and reason not in tip_text(page)
    press(page, 'Enter', 'Enter', 13)
    page.wait_for(f'{save}.getAttribute("aria-disabled") === "true"', what='the edited settings to be saved')
    assert page.evaluate('window.__presetWrites') == 1
    assert tip_text(page) == unchanged_tip


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


# ------------------------------------------------------------------ the check group: marks, switches, keys

# How many pixels of each mark a preview holds. On 整体 the marks lie nearly opaque over the picture, right of the
# compare slider (`original` counts any left of it): measured there, red is about (224, 48, 64), blue (96, 160, 224)
# and yellow (224, 176, 48), and the picture's own orange patch (225, 162, 78) is none of them. On 细节 they are 60%
# over the picture: red on the dark stocking is about (150, 48, 48), blue on the orange patch a grey teal
# (144, 160, 160), where the picture itself has only greys with equal channels, dark texture and the orange.
CHECK_MARKS = '''(() => {
    const near = (d, i, c) => Math.abs(d[i] - c[0]) < 30 && Math.abs(d[i + 1] - c[1]) < 30 && Math.abs(d[i + 2] - c[2]) < 30;
    const fit = document.querySelector('#fit'), crop = document.querySelector('#crop');
    const split = Math.round(fit.width * +document.querySelector('#compare').getAttribute('aria-valuenow') / 100);
    const out = {red: 0, blue: 0, yellow: 0, original: 0, detailRed: 0, detailBlue: 0};
    const f = fit.getContext('2d').getImageData(0, 0, fit.width, fit.height).data;
    for (let y = 0; y < fit.height; y++) for (let x = 0; x < fit.width; x++) {
        const i = 4 * (y * fit.width + x);
        const mark = near(f, i, [224, 48, 64]) ? 'red' : near(f, i, [96, 160, 224]) ? 'blue'
            : near(f, i, [224, 176, 48]) && f[i + 2] < 64 ? 'yellow' : null;
        if (mark && x < split - 2) out.original++; else if (mark && x > split + 2) out[mark]++;
    }
    const c = crop.getContext('2d').getImageData(0, 0, crop.width, crop.height).data;
    for (let i = 0; i < c.length; i += 4) {
        if (c[i] > 120 && c[i + 1] < 80 && c[i + 2] < 80) out.detailRed++;
        if (c[i] > 110 && c[i + 1] - c[i] > 8 && c[i + 2] - c[i] > 8) out.detailBlue++;
    }
    return out;
})()'''
ALL_MARKS = 'm.red > 50 && m.blue > 20 && m.yellow > 20 && m.detailRed > 50 && m.detailBlue > 20'
CHECK_KEYS = '[...document.querySelectorAll("#check-group .key")].map(e => e.classList.contains("on"))'


def marks(page, want, timeout=60):
    """The mark counts once they are as `want` says (JavaScript over the counts `m`): the previews are drawn again a
    moment after a change, and the picture before it must not pass for the one after."""
    page.wait_for(f'(() => {{ const m = {CHECK_MARKS}; return {want}; }})()', timeout=timeout,
                  what=f'the previews to show {want}')
    return page.evaluate(CHECK_MARKS)


def check_page(check_ui, lang='en', scale=100, size=(1440, 900), **document):
    """The Texture page of a fresh synthetic picture with red, blue and yellow marks to show, both previews drawn."""
    server, page = check_ui
    server.set_lang(lang)
    check_document(server, **document)
    show(check_ui, lang, scale, size, look=1)
    page.wait_for('''document.querySelector('#fade-note').textContent && document.querySelector('#crop').width > 2
        && /^(缩到窗口|Scaled)/.test(document.querySelector('#fit-status').textContent)''', timeout=60,
                  what='the previews and the rows')
    return server, page


def hold_space(page, down):
    page.send('Input.dispatchKeyEvent', type='keyDown' if down else 'keyUp', key=' ', code='Space',
              windowsVirtualKeyCode=32, **({'text': ' '} if down else {}))


def test_marks_follow_the_box_and_each_switch_on_the_real_previews(check_ui):
    server, page = check_page(check_ui)
    said = lambda row: page.evaluate(f'document.querySelector("#{row}-note").textContent')    # noqa: E731
    assert page.evaluate(CHECK_KEYS) == [False] * 3
    assert set(marks(page, 'true').values()) == {0}, 'nothing is marked until the box is ticked'

    page.click('#show-problems')
    assert marks(page, ALL_MARKS)['original'] == 0, 'the original, left of the compare slider, is never marked'
    assert page.evaluate(CHECK_KEYS) == [True] * 3
    # the box was clicked, so Space is still the hold that shows the original in Detail: no marks on it, the box stays
    hold_space(page, True)
    held = marks(page, 'm.detailRed === 0 && m.detailBlue === 0')
    assert held['red'] > 50 and held['blue'] > 20, held
    hold_space(page, False)
    assert page.evaluate('document.querySelector("#show-problems").checked')
    marks(page, ALL_MARKS)

    # each switch takes its own colour off the pictures, not only off its row, and leaves the other two
    page.click('#fade')
    seen = marks(page, 'm.red === 0 && m.detailRed === 0')
    assert min(seen['blue'], seen['yellow'], seen['detailBlue']) > 20, seen
    assert page.evaluate(CHECK_KEYS) == [False, True, True]
    assert said('fade') == 'Off: texture is not faded where courses crowd.'
    page.click('#fade')
    marks(page, ALL_MARKS)
    page.click('#exclude')
    seen = marks(page, 'm.blue === 0 && m.detailBlue === 0')
    assert min(seen['red'], seen['detailRed']) > 50 and seen['yellow'] > 20, seen
    assert page.evaluate(CHECK_KEYS) == [True, False, True]
    assert said('exclude') == 'Off: nothing is excluded by color.'
    page.click('#exclude')
    marks(page, ALL_MARKS)

    page.click('#show-problems')
    assert set(marks(page, 'm.red + m.blue + m.yellow + m.detailRed + m.detailBlue === 0').values()) == {0}
    assert page.evaluate(CHECK_KEYS) == [False] * 3


def test_an_export_made_with_the_marks_showing_holds_none_of_them(check_ui, tmp_path):
    import cv2
    import numpy as np

    server, page = check_page(check_ui)
    page.click('#show-problems')
    marks(page, ALL_MARKS)
    target = tmp_path / 'marked.png'
    # Only the system's save dialog is answered here; the file is written by the real server.
    page.evaluate(f'''(() => {{
        const real = window.fetch;
        window.fetch = (url, opt) => String(url).endsWith('/export/ask')
            ? Promise.resolve(Response.json({json.dumps({'path': str(target)})})) : real(url, opt);
    }})()''')
    page.click('#btn-export')
    page.wait_for('!document.querySelector("#exported").hidden', timeout=60, what='the export receipt')
    out = cv2.imdecode(np.fromfile(str(target), np.uint8), cv2.IMREAD_COLOR).astype(int)
    assert out.shape[:2] == (352, 448)
    for name, bgr in (('red', (60, 50, 255)), ('blue', (255, 160, 70)), ('yellow', (40, 190, 255))):
        assert not (np.abs(out - bgr).max(axis=2) < 25).any(), f'the exported image holds {name} marks'
    assert (out != 157).any(axis=2).sum() > 5000, 'the export is the picture, not a blank'
    # and it was made while the previews showed them
    assert page.evaluate('document.querySelector("#show-problems").checked')
    assert marks(page, ALL_MARKS)['original'] == 0
    page.click('#btn-exported-close')


def test_tab_reaches_the_group_in_order_and_space_goes_by_how_the_focus_came(check_ui):
    server, page = check_page(check_ui)
    focus = 'document.activeElement.id || document.activeElement.getAttribute("aria-controls")'
    ticked = 'document.querySelector("#show-problems").checked'
    fading = 'document.querySelector("#fade").checked'
    peek = 'document.querySelector("#peek-hint").classList.contains("on")'

    # real Tab presses from Detail: the box, then each row's ? and switch, in the order they read
    page.click('#crop')
    assert page.evaluate(focus) == 'crop'
    order = []
    for _ in range(6):
        press(page, 'Tab', 'Tab', 9)
        order.append(page.evaluate(focus))
    assert order == ['show-problems', 'fade-info', 'fade', 'exclude-info', 'exclude', 'nostroke-info']

    # reached with the keyboard, the box keeps Space for itself (and Enter does nothing, as on any checkbox)
    for _ in range(5):
        press(page, 'Tab', 'Tab', 9, shift=True)
    assert page.evaluate(focus) == 'show-problems' and not page.evaluate(ticked)
    hold_space(page, True)
    assert not page.evaluate(peek), 'Space on a box the keyboard reached must not show the original'
    hold_space(page, False)
    assert page.evaluate(ticked)
    press(page, 'Enter', 'Enter', 13)
    assert page.evaluate(ticked)
    press(page, ' ', 'Space', 32)
    assert not page.evaluate(ticked)
    # and so does a switch
    press(page, 'Tab', 'Tab', 9)
    press(page, 'Tab', 'Tab', 9)
    assert page.evaluate(focus) == 'fade' and page.evaluate(fading)
    hold_space(page, True)
    assert not page.evaluate(peek)
    hold_space(page, False)
    page.wait_for(f'!{fading}', what='Space to turn the switch off')
    press(page, ' ', 'Space', 32)
    page.wait_for(fading, what='Space to turn the switch back on')

    # clicked with the mouse, either keeps the focus and Space is the hold that shows the original: nothing toggles
    for control, state in (('#show-problems', ticked), ('#fade', fading)):
        page.click(control)
        after_click = page.evaluate(state)
        assert page.evaluate(focus) == control.lstrip('#')
        hold_space(page, True)
        assert page.evaluate(peek), f'Space after clicking {control} did not show the original'
        hold_space(page, False)
        assert not page.evaluate(peek) and page.evaluate(state) == after_click, control
        page.click(control)
    # with the focus on Detail itself, however it came
    page.click('#crop')
    hold_space(page, True)
    assert page.evaluate(peek)
    hold_space(page, False)
    assert not page.evaluate(peek)


@pytest.mark.parametrize('lang, scale, size', (('zh', 100, (1440, 900)), ('en', 125, (1024, 768)), ('en', 125, (360, 840))),
                         ids=('zh-100-1440x900', 'en-125-1024x768', 'en-125-360x840'))
def test_a_question_mark_in_the_group_opens_beside_itself_and_closes_four_ways(check_ui, lang, scale, size):
    server, page = check_page(check_ui, lang, scale, size)
    scrolls = page.evaluate('(() => { const s = document.querySelector("#stage"); return s.scrollHeight > s.clientHeight + 20; })()')
    if size[0] == 360:
        assert scrolls, 'the narrow case is the one that proves a scroll of the previews closes the note'
    for name in ('fade', 'exclude', 'nostroke'):
        button = f'#check-group [aria-controls="{name}-info"]'
        seen = f'''(() => {{
            const p = document.querySelector('#{name}-info'), b = document.querySelector('{button}');
            if (p.hidden) return null;
            const r = p.getBoundingClientRect(), q = b.getBoundingClientRect();
            return {{
                inside: r.left >= 0 && r.top >= 0 && r.right <= innerWidth && r.bottom <= innerHeight,
                apart: Math.max(r.left - q.right, q.left - r.right, r.top - q.bottom, q.top - r.bottom),
                expanded: b.getAttribute('aria-expanded'), text: p.innerText,
                chinese: /[\u4e00-\u9fff]/.test(p.innerText),
            }};
        }})()'''
        shut = f'document.querySelector("#{name}-info").hidden && document.querySelector(\'{button}\').getAttribute("aria-expanded") === "false"'
        page.click(button)
        note = page.evaluate(seen)
        # beside its own button (not at the panel's edge), clear of the button, and whole inside the window
        assert note and note['inside'] and 0 <= note['apart'] <= 9 and note['expanded'] == 'true', note
        assert len(note['text']) > 20 and note['chinese'] == (lang == 'zh'), note
        assert '标题旁' not in note['text'] and 'beside the Detail' not in note['text'], note
        press(page, 'Escape', 'Escape', 27)
        assert page.evaluate(shut), f'Esc left the {name} note open'
        page.click(button)
        assert page.evaluate(seen)
        page.click(button)
        assert page.evaluate(shut), f'a second click left the {name} note open'
        page.click(button)
        page.click('#tab-look')            # elsewhere: the page's own tab, at the top, which no note reaches
        assert page.evaluate(shut), f'a click elsewhere left the {name} note open'
        if scrolls:
            page.click(button)
            assert page.evaluate(seen)
            page.evaluate('''new Promise(go => {
                const s = document.querySelector('#stage');
                s.scrollTop += s.scrollTop + 12 < s.scrollHeight - s.clientHeight ? 12 : -12;
                requestAnimationFrame(() => requestAnimationFrame(go));
            })''')
            assert page.evaluate(shut), f'scrolling the previews left the {name} note where it was'


@pytest.mark.parametrize('name, lands', (('fade', 'fade'), ('exclude', 'exclude')))
def test_esc_closes_a_note_of_the_group_after_tab_has_moved_on(check_ui, name, lands):
    # the note is opened with its ?, and Tab then goes on to the switch beside it: Esc still closes the note
    server, page = check_page(check_ui)
    button = f'#check-group [aria-controls="{name}-info"]'
    shut = f'document.querySelector("#{name}-info").hidden && document.querySelector(\'{button}\').getAttribute("aria-expanded") === "false"'
    page.click(button)
    assert not page.evaluate(shut)
    press(page, 'Tab', 'Tab', 9)
    assert page.evaluate('document.activeElement.id') == lands
    assert not page.evaluate(shut), 'the note went before Esc was pressed'
    state = page.evaluate(f'document.querySelector("#{lands}").checked')
    press(page, 'Escape', 'Escape', 27)
    assert page.evaluate(shut), f'Esc left the {name} note open with the focus on the switch'
    assert page.evaluate(f'document.querySelector("#{lands}").checked') == state


def test_a_note_taller_than_the_room_beside_its_question_mark_leaves_the_button_free(check_ui):
    # A short, narrow window at a large interface size, and a yellow row with many long names: the note has no room
    # left or right of its ?, and is taller than the room under or over it. It must still not lie on the ? itself:
    # a second click on the button is one of the ways to close it. Only the list of the public /look answer is set.
    server, page = check_ui
    names = [f'Region with a rather long name {i}' for i in range(1, 9)]
    script = page.send('Page.addScriptToEvaluateOnNewDocument', source=f'''(() => {{
        const real = window.fetch;
        window.fetch = async (url, opt) => {{
            const res = await real(url, opt);
            if (!/\\/api\\/doc\\/[^/]+\\/look(\\?|$)/.test(String(url)) || !res.ok) return res;
            const info = await res.json();
            if (info && 'untextured' in info) Object.assign(info, {json.dumps({'untextured': names})});
            return Response.json(info, {{status: res.status}});
        }};
    }})()''')['identifier']
    try:
        check_page(check_ui, 'en', 175, (360, 480))
        button = '#check-group [aria-controls="nostroke-info"]'
        page.evaluate(f'''new Promise(go => {{
            document.querySelector('{button}').scrollIntoView({{block: 'center'}});
            requestAnimationFrame(() => requestAnimationFrame(go));
        }})''')
        page.click(button)
        seen = page.evaluate(f'''(() => {{
            const p = document.querySelector('#nostroke-info'), b = document.querySelector('{button}');
            const r = p.getBoundingClientRect(), q = b.getBoundingClientRect();
            const top = document.elementFromPoint(q.left + q.width / 2, q.top + q.height / 2);
            return {{
                open: !p.hidden, free: top === b, names: p.innerText.includes('rather long name 8'),
                inside: r.left >= 0 && r.top >= 0 && r.right <= innerWidth && r.bottom <= innerHeight,
                note: [r.left, r.top, r.width, r.height].map(Math.round),
                button: [q.left, q.top, q.width, q.height].map(Math.round), window: [innerWidth, innerHeight],
            }};
        }})()''')
        assert seen['open'] and seen['names'] and seen['inside'], seen
        assert seen['free'], f'the note lies on its own ? button: {seen}'
        page.click(button)
        assert page.evaluate('document.querySelector("#nostroke-info").hidden'), 'a second click left the note open'
    finally:
        page.send('Page.removeScriptToEvaluateOnNewDocument', identifier=script)


ARRANGE_GROUP = '{ min: 220, max: 760, height: (w) => (w >= 700 ? 105 : w >= 440 ? 172 : 240) }'
ARRANGE_ROWS = '{ wholeHead: 34, detailHead: 34, detailFoot: 30, minWhole: 84, minDetail: 156 }'


def test_arrange_gives_a_long_banner_and_a_dense_screen_the_room_there_is(ui):
    page = show(ui, 'en', 100, (1280, 720), look=1)
    seen = page.evaluate(f'''(async () => {{
        const {{ arrange }} = await import('/static/look.js');
        const rest = {{ ...{ARRANGE_ROWS}, group: {ARRANGE_GROUP}, prev: null }};
        return {{
            // a 10:1 strip in the stage of a 360 px window: its short side cannot be 40 px there, its long side can be the width
            banner: arrange(328, 435, 3000, 300, 1, rest),
            // and the same turned upright, in a wide and low stage
            pole: arrange(1136, 300, 300, 3000, 1, rest),
            // four device pixels to one: Detail's budget (250 px) is under the usual least side, and is then the side
            dense: arrange(1200, 900, 448, 352, 4, rest),
        }};
    }})()''')
    banner, pole, dense = seen['banner'], seen['pole'], seen['dense']
    assert banner['ww'] >= 300 and banner['d'] >= 120 and banner['gw'] >= 220, seen
    assert pole['wh'] >= 150 and pole['d'] >= 120, seen
    assert 200 <= dense['d'] <= 250 and dense['ww'] >= 400, seen
    page.check_errors()


def test_arrange_never_gives_a_picture_no_size_however_long_it_is(ui):
    # A picture hundreds of times as long as it is wide leaves Whole's short side under one px at any width a
    # window has. What arrange() answers is still a size to draw at: every side at least 1, in narrow stages and
    # usual ones, for both ways the picture can be long.
    page = show(ui, 'en', 100, (1280, 720), look=1)
    seen = page.evaluate(f'''(async () => {{
        const {{ arrange }} = await import('/static/look.js');
        const rest = {{ ...{ARRANGE_ROWS}, group: {ARRANGE_GROUP}, prev: null }};
        const out = [];
        for (const [iw, ih] of [[4000, 10], [10, 5000], [3000, 4], [4, 3000]])
            for (const [W, H] of [[328, 435], [328, 796], [720, 664], [1136, 664], [1568, 796]])
                for (const dpr of [1, 2]) {{
                    const a = arrange(W, H, iw, ih, dpr, rest);
                    out.push({{ iw, ih, W, H, dpr, ww: a.ww, wh: a.wh, d: a.d, gw: a.gw, gh: a.gh }});
                }}
        return out;
    }})()''', timeout=120)
    assert len(seen) == 40
    none = [a for a in seen if not (a['ww'] >= 1 and a['wh'] >= 1 and a['d'] >= 1 and a['gw'] >= 1 and a['gh'] >= 1)]
    assert not none, none[:6]
    page.check_errors()


def test_arrange_does_not_pass_over_a_taller_plan_that_scores_more(ui):
    # Each case has a plan found by an exhaustive search (every dock, side of Detail and stage height, none skipped),
    # with the score that search gave it: arrange() may find another, but none that scores less.
    page = show(ui, 'en', 100, (1280, 720), look=1)
    seen = page.evaluate(f'''(async () => {{
        const {{ arrange }} = await import('/static/look.js');
        const rows = {ARRANGE_ROWS};
        const tall = {{ min: 250, max: 900, height: (w) => (w >= 800 ? 203 : w >= 500 ? 221 : 259) }};
        const of = (W, H, iw, ih, group) => {{
            const a = arrange(W, H, iw, ih, 1, {{ ...rows, group, prev: null }});
            return [a.score, a.ww, a.d];
        }};
        return [of(313, 796, 448, 600, {ARRANGE_GROUP}), of(345, 796, 448, 600, tall), of(345, 435, 1792, 352, tall),
            of(448, 198, 448, 600, {ARRANGE_GROUP})];
    }})()''')
    known = (10.5211, 10.4575, 8.5067, 6.9091)      # whole 280 with detail 245; 272 with 237; 344 with 235; 209 with 73
    short = [(got, score) for got, score in zip(seen, known) if got[0] < score - 0.005]
    assert not short, short
    page.check_errors()


def test_a_long_banner_gets_the_width_of_a_narrow_window(check_ui):
    server, page = check_ui
    server.set_lang('en')
    check_document(server, image_size=(3000, 300))
    show(check_ui, 'en', 100, (360, 840), look=1)
    view = assert_check_layout(page, (3000, 300))
    rects, width = view['rects'], view['width']
    assert rects['#fit'][2] >= 0.8 * width and rects['#crop'][2] >= 100, view
    assert rects['#check-group'][2] >= 0.75 * width, view


def test_arrange_keeps_its_promises_over_many_stages_and_picture_shapes(ui):
    # look.js's arrange() and place(), called as the page calls them, with a stand-in for the group's measured height
    # (three steps, as a real group has when its rows go from side by side to one under another). No dock is asked
    # for: only what must hold wherever the group goes.
    page = show(ui, 'en', 100, (1280, 720), look=1)
    seen = page.evaluate('''(async () => {
        const { arrange, place } = await import('/static/look.js');
        const group = { min: 220, max: 760, height: (w) => (w >= 700 ? 105 : w >= 440 ? 172 : 240) };
        const rows = { wholeHead: 34, detailHead: 34, detailFoot: 30, minWhole: 84, minDetail: 156 };
        const bad = [], docks = new Set();
        let n = 0, slowest = 0;
        for (const W of [200, 328, 500, 720, 1136, 1568, 2400]) for (const H of [180, 300, 435, 664, 796, 1300])
            for (const [iw, ih] of [[448, 352], [448, 600], [1792, 352], [448, 1792], [96, 80], [1000, 1000]])
                for (const dpr of [1, 2]) {
                    n++;
                    const t0 = performance.now();
                    arrange(W, H, iw, ih, dpr, { ...rows, group, prev: null });
                    slowest = Math.max(slowest, performance.now() - t0);
                    const a = arrange(W, H, iw, ih, dpr, { ...rows, group, prev: null });
                    const p = place(a.dock, { ...rows, ww: a.ww, wh: a.wh, d: a.d, gw: a.gw, gh: a.gh });
                    const why = [];
                    const lo = Math.min(group.min, W), hi = Math.max(lo, Math.min(group.max, W));
                    if (!(a.ww >= 1 && a.wh >= 1 && a.d >= 1)) why.push('a picture has no size');
                    if (Math.abs(a.ww * ih - a.wh * iw) > iw + ih) why.push('the whole picture lost its shape');
                    if (a.d > Math.max(1000 / dpr, 60) + 1e-6) why.push('Detail is over its render budget');
                    if (a.gw < lo || a.gw > hi || a.gh !== group.height(a.gw)) why.push('the group is not at a width it was measured at');
                    if (a.mode !== a.dock.split('/')[0]) why.push('mode and dock disagree');
                    // inside the width there is; no two of the three on each other (the canvases, not the stretched panes)
                    const box = { W: [p.at.W.x, p.at.W.y, a.ww, rows.wholeHead + a.wh],
                        D: [p.at.D.x, p.at.D.y, a.d, rows.detailHead + a.d + rows.detailFoot],
                        G: [p.at.G.x, p.at.G.y, a.gw, a.gh] };
                    if (W >= 328 && p.w > W + 1e-6) why.push(`it is ${p.w} wide in ${W}`);
                    for (const [i, j] of [['W', 'D'], ['W', 'G'], ['D', 'G']]) {
                        const [x, y, w, h] = box[i], [u, v, s, t] = box[j];
                        if (Math.min(x + w, u + s) - Math.max(x, u) > 1e-6 && Math.min(y + h, v + t) - Math.max(y, v) > 1e-6) why.push(`${i} is on ${j}`);
                    }
                    // a stage with room for all of it does not scroll
                    if (W >= 720 && H >= 664 && p.h > H + 1e-6) why.push(`it is ${p.h} tall in a roomy ${H}`);
                    // and where a plan does scroll though a smaller one would fit, it is the group that goes below
                    // what shows, never a picture: H 435 and up fits something at every width tried here
                    const low = Math.max(box.W[1] + box.W[3], box.D[1] + box.D[3]);
                    if (W >= 328 && H >= 435 && p.h > H + 1e-6 && low > H + 1e-6) why.push(`a picture ends at ${low} of ${H}`);
                    // the dock in use is kept, and against another dock the answer is one of the two, never a third
                    if (arrange(W, H, iw, ih, dpr, { ...rows, group, prev: a.dock }).dock !== a.dock) why.push('the dock in use was not kept');
                    for (const other of ['side/under', 'side/below', 'stack/right']) {
                        const b = arrange(W, H, iw, ih, dpr, { ...rows, group, prev: other }).dock;
                        if (b !== a.dock && b !== other) why.push(`from ${other} it went to ${b}, not ${a.dock}`);
                    }
                    docks.add(a.dock);
                    if (why.length) bad.push({ W, H, iw, ih, dpr, a, why });
                }
        return { n, bad: bad.slice(0, 5), failed: bad.length, docks: [...docks].sort(), slowest };
    })()''', timeout=240)
    assert seen['failed'] == 0, seen
    assert seen['n'] == 504 and len(seen['docks']) >= 4, seen       # the shapes really lead to different docks
    # a guard against a search that goes back to trying every size (seconds for one answer), not a promise of speed
    assert seen['slowest'] < 150, seen
    page.check_errors()


SWITCHES = '[document.querySelector("#fade").checked, document.querySelector("#exclude").checked]'


def set_switches(page, fade, exclude):
    """Click the two switches to these positions; each is there once the page shows it (颜色排除 waits for the server)."""
    for name, on, at in (('fade', fade, 0), ('exclude', exclude, 1)):
        if page.evaluate(SWITCHES)[at] != on:
            page.click(f'#{name}')
            page.wait_for(f'{SWITCHES}[{at}] === {str(on).lower()}', what=f'{name} to be {"on" if on else "off"}')


def pick_preset(page, name):
    """Choose an entry of the presets list, as picking it does (None: its last entry, 保存为新预设…)."""
    page.evaluate(f'''(() => {{
        const s = document.querySelector('#preset-select'), name = {json.dumps(name)};
        if (name === null) s.selectedIndex = s.options.length - 1; else s.value = name;
        s.dispatchEvent(new Event('change', {{bubbles: true}}));
    }})()''')


def save_new_preset(page, name):
    pick_preset(page, None)
    page.wait_for('document.querySelector("#preset-dialog").open && document.activeElement.id === "preset-name"',
                  what='the dialog that asks for a preset name')
    page.send('Input.insertText', text=name)
    page.click('#btn-preset-ok')
    page.wait_for(f'document.querySelector("#preset-select").value === {json.dumps(name)}'
                  ' && !document.querySelector("#preset-dialog").open', what=f'the preset {name} to be saved')


@pytest.mark.parametrize('size', ((1280, 720), (360, 840)), ids=('desktop', 'narrow'))
@pytest.mark.parametrize('lang, name, scope, collision', (
    ('zh', '示例纹理', '预设带上：纹理层、样式和滑杆、亮点、高光粒子、摩尔纹效果、纹理减弱。不带：颜色排除、部位和走向线。',
     '已有同名预设，保存会覆盖它。'),
    ('en', 'Sample weave', 'A preset keeps: texture layers, style and sliders, sparkles, highlight particles, '
     'moiré effect, texture fade. It leaves out: color exclusion, regions and direction lines.',
     'A preset with this name exists; saving replaces it.'),
), ids=('zh', 'en'))
def test_the_new_preset_dialog_keeps_its_scope_visible_with_a_duplicate_name(ui, size, lang, name, scope, collision):
    server, _ = ui
    server.api('/api/look/presets', 'PUT', {'name': name, 'params': {'density': 125}})
    page = show(ui, lang, 100, size, look=1)
    page.wait_for(f'[...document.querySelector("#preset-select").options].some(o => o.value === {json.dumps(name)})',
                  what='the saved name to be available')
    page.wait_for('/^(缩到窗口|Scaled)/.test(document.querySelector("#fit-status").textContent)',
                  what='Whole to be drawn')
    pick_preset(page, None)
    page.wait_for('document.querySelector("#preset-dialog").matches(":modal") && document.activeElement.id === "preset-name"',
                  what='the new preset dialog to ask for a name')
    visible_scope = '''(() => {
        const d = document.querySelector('#preset-dialog');
        const p = document.getElementById(d.getAttribute('aria-describedby'));
        return p && p.checkVisibility() ? p.textContent.trim() : null;
    })()'''
    before_name = page.evaluate(visible_scope)
    page.send('Input.insertText', text=name)
    page.screenshot(f'preset-dialog-{lang}-{size[0]}x{size[1]}-duplicate')
    assert before_name == scope
    assert page.evaluate(visible_scope) == scope
    assert page.evaluate('''(() => {
        const p = document.querySelector('#preset-dialog-note');
        return p.checkVisibility() ? p.textContent : null;
    })()''') == collision
    assert page.evaluate('''(() => {
        const d = document.querySelector('#preset-dialog'), r = d.getBoundingClientRect();
        const scope = document.getElementById(d.getAttribute('aria-describedby')).getBoundingClientRect();
        const name = d.querySelector('#preset-name').getBoundingClientRect();
        const warning = d.querySelector('#preset-dialog-note').getBoundingClientRect();
        return r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight
            && d.scrollWidth === d.clientWidth && d.scrollHeight === d.clientHeight
            && name.bottom <= scope.top && scope.bottom <= warning.top;
    })()''')
    assert uibrowser.out_of_reach(page, '#preset-dialog', must=('#btn-preset-ok', '#btn-preset-cancel')) == []
    page.click('#btn-preset-cancel')
    assert not page.evaluate('document.querySelector("#preset-dialog").open')
    page.check_errors()


def saved_preset(server, name):
    """What the server keeps for a preset: it must hold 纹理减弱 and nothing of 颜色排除."""
    params = next(p['params'] for p in server.api('/api/look/presets')['presets'] if p['name'] == name)
    assert not [key for key in params if 'exclu' in key.lower()], params
    return params


def test_presets_carry_texture_fade_and_leave_color_exclusion_both_ways(check_ui):
    server, page = check_page(check_ui)
    said = 'document.querySelector("#fade-note").textContent'
    stamp = uibrowser.uuid.uuid4().hex[:6]             # the presets outlive the picture on this server
    off, on = f'both off {stamp}', f'both on {stamp}'

    # saved as a new preset with both switches off, loaded with both on: the same load turns Texture fade off (so
    # the load did happen) and leaves Color exclusion on
    set_switches(page, False, False)
    save_new_preset(page, off)
    assert saved_preset(server, off)['fade'] is False
    set_switches(page, True, True)
    pick_preset(page, off)
    page.wait_for(f'{SWITCHES}[0] === false', what='the preset to turn Texture fade off')
    assert page.evaluate(SWITCHES) == [False, True]
    assert page.evaluate(said) == 'Off: texture is not faded where courses crowd.'

    # the other way round: saved with both on, loaded with both off
    set_switches(page, True, True)
    save_new_preset(page, on)
    assert saved_preset(server, on)['fade'] is True
    set_switches(page, False, False)
    pick_preset(page, on)
    page.wait_for(f'{SWITCHES}[0] === true', what='the preset to turn Texture fade on')
    assert page.evaluate(SWITCHES) == [True, False]
    assert page.evaluate(said) != 'Off: texture is not faded where courses crowd.'

    # Save with a preset selected writes over it without the dialog: the same holds on that path
    set_switches(page, False, False)
    page.wait_for('document.querySelector("#btn-preset-save").getAttribute("aria-disabled") === "false"',
                  what='Save to offer writing the changed settings')
    page.click('#btn-preset-save')
    assert not page.evaluate('document.querySelector("#preset-dialog").open')
    uibrowser._wait('the preset to be written over', lambda: saved_preset(server, on)['fade'] is False, 10)
    set_switches(page, True, True)
    pick_preset(page, on)
    page.wait_for(f'{SWITCHES}[0] === false', what='the overwritten preset to turn Texture fade off')
    assert page.evaluate(SWITCHES) == [False, True]
    set_switches(page, True, False)
    pick_preset(page, off)
    page.wait_for(f'{SWITCHES}[0] === false', what='the first preset to turn Texture fade off again')
    assert page.evaluate(SWITCHES) == [False, False]


def test_the_two_switches_work_unticked_each_a_step_and_reset_all_takes_only_texture_fade(check_ui):
    server, page = check_page(check_ui)
    doc = server.api('/api/doc')['id']
    note = lambda row: page.evaluate(f'document.querySelector("#{row}-note").textContent')    # noqa: E731
    assert not page.evaluate('document.querySelector("#show-problems").checked')
    assert (note('fade'), note('exclude')) == ('14% of the texture is faded now.',
                                               '3.6% of the painted regions is excluded now.')

    page.click('#fade')
    page.wait_for(f'{SWITCHES}[0] === false', what='Texture fade to turn off')
    assert note('fade') == 'Off: texture is not faded where courses crowd.'
    uibrowser._wait('the look without fade to be saved',
                    lambda: server.api(f'/api/doc/{doc}/look')['params']['fade'] is False, 10)

    # Color exclusion stays as it was until the server has answered, then changes
    page.evaluate('''(() => {
        const real = window.fetch;
        window.__letExclude = null;
        window.fetch = (url, opt) => String(url).endsWith('/coverage/exclude')
            ? new Promise(go => { window.__letExclude = go; }).then(() => real(url, opt)) : real(url, opt);
    })()''')
    page.click('#exclude')
    page.wait_for('!!window.__letExclude', what='the change of Color exclusion to be sent')
    assert page.evaluate(SWITCHES) == [False, True], 'the switch moved before the server answered'
    page.evaluate('void window.__letExclude()')
    page.wait_for(f'{SWITCHES}[1] === false', what='Color exclusion to turn off')
    assert note('exclude') == 'Off: nothing is excluded by color.'
    assert server.api('/api/doc')['color_exclude'] is False

    page.click('#btn-look-reset')
    page.wait_for(f'{SWITCHES}[0] === true', what='Reset all to turn Texture fade back on')
    assert page.evaluate(SWITCHES) == [True, False], 'Reset all must leave Color exclusion as it is'
    # and back, a step at a time: the reset, Color exclusion, Texture fade
    for expected in ('[false,false]', '[false,true]', '[true,true]'):
        page.click('#btn-undo')
        page.wait_for(f'JSON.stringify({SWITCHES}) === "{expected}"', timeout=10,
                      what=f'Undo to bring the switches to {expected}')
    assert page.evaluate('document.querySelector("#btn-undo").disabled'), 'three changes were three steps, no more'


def test_the_yellow_row_names_what_gets_no_texture_and_a_finished_solve_moves_nothing(check_ui):
    server, page = check_page(check_ui, size=(1024, 768))
    row = 'document.querySelector("#check-nostroke")'
    assert page.evaluate(f'{row}.textContent') == '5.9%: Right leg. Check their direction lines in Guides.'
    # one line, cut short where the group is narrow; the whole of it is in the row's tip and behind its ?
    assert page.evaluate(f'''(() => {{
        const p = {row}, line = parseFloat(getComputedStyle(p).lineHeight);
        return p.getBoundingClientRect().height < 1.6 * line && p.dataset.tip.includes('Right leg')
            && document.querySelector('#nostroke-names').textContent.includes('Right leg')
            && document.querySelector('#nostroke-solving').hidden;
    }})()''')
    page.click('#show-problems')
    marks(page, ALL_MARKS)
    page.hover('.status')
    before = resting_places(page)

    # the missing region gets its line: while it solves it is no longer listed as missing, and once it has, the row
    # says so, the shares are other numbers and the yellow is gone. Nothing of the previews or the group has moved
    state = server.api('/api/doc')
    missing = state['regions'][1]['id']
    server.api(f'/api/doc/{state["id"]}/strokes', 'POST',
               {'pts': [368, 185, 380, 189, 390, 190, 400, 189, 412, 185], 'hint': missing})
    uibrowser._wait('the second region to solve',
                    lambda: [r['status'] for r in server.api('/api/doc')['regions']] == ['ok', 'ok'], 30)
    page.wait_for(f'{row}.textContent === "None."', timeout=30, what='the yellow row to say nothing is missing')
    assert marks(page, 'm.yellow === 0')['red'] > 50
    assert page.evaluate(f'!{row}.dataset.tip && document.querySelector("#nostroke-names").hidden')
    assert resting_places(page) == before


def test_reloading_clears_the_box_and_another_picture_keeps_it(check_ui):
    server, page = check_page(check_ui)
    ticked = 'document.querySelector("#show-problems").checked'
    page.click('#show-problems')
    marks(page, ALL_MARKS)
    page.goto(server.url + '/?page=look')
    page.wait_for('document.body.dataset.mode === "look" && !!document.querySelector("#fade-note").textContent',
                  what='the Texture page after a reload')
    assert not page.evaluate(ticked) and page.evaluate(CHECK_KEYS) == [False] * 3

    page.click('#show-problems')
    marks(page, ALL_MARKS)
    check_document(server, portrait=True)                   # another picture: the page goes back to Guides for it
    page.wait_for('document.body.dataset.mode === "edit"', what='the new picture to open on Guides')
    page.click('#tab-look')
    page.wait_for('document.body.dataset.mode === "look" && !!document.querySelector("#fade-note").textContent',
                  what='the Texture page of the new picture')
    assert page.evaluate(ticked) and page.evaluate(CHECK_KEYS) == [True] * 3, 'the blocks blinked while the settings loaded'
    # the marks counted next are the new, upright picture's: not those the last one left on the canvases
    page.wait_for('''(() => { const f = document.querySelector('#fit'); return f.height > f.width
        && /^(缩到窗口|Scaled)/.test(document.querySelector('#fit-status').textContent); })()''', timeout=60,
                  what='the new picture to be drawn')
    assert marks(page, ALL_MARKS)['original'] == 0
    assert page.evaluate(CHECK_KEYS) == [True] * 3, page.evaluate(
        f'[{SWITCHES}, document.querySelector("#fade-note").textContent, document.querySelector("#exclude-note").textContent]')


def test_a_click_on_whole_of_a_very_upright_picture_shows_that_place_in_detail(check_ui):
    # A 1:10 picture can keep its ratio after Whole rounds both sides in this window. Use a slightly different
    # ratio to exercise the two different scales: a click near the lower end must still bring that place into
    # Detail, and the frame on Whole must lie where Detail's picture is.
    server, page = check_ui
    server.set_lang('en')
    iw, ih = 511, 5000
    check_document(server, image_size=(iw, ih))
    show(check_ui, 'en', 100, (360, 850), look=1)
    page.wait_for('''document.querySelector('#fade-note').textContent && document.querySelector('#crop').width > 2
        && /^(缩到窗口|Scaled)/.test(document.querySelector('#fit-status').textContent)''', timeout=60,
                  what='the previews and the rows')
    spot = page.evaluate('''(async () => {
        const real = window.fetch;
        window.__crops = [];
        window.fetch = (url, opt) => {
            const to = String(url);
            if (to.includes('/render/crop?')) {
                const q = new URL(to, location.href).searchParams;
                window.__crops.push(['x0', 'y0', 'w', 'h'].map((k) => +q.get(k)));
            }
            return real(url, opt);
        };
        const f = document.querySelector('#fit');
        f.scrollIntoView({block: 'center'});
        await new Promise((go) => requestAnimationFrame(() => requestAnimationFrame(go)));
        // beside the compare slider, whose handle is wider than its line: a place where the canvas itself is on top
        const r = f.getBoundingClientRect(), y = r.top + 0.94 * r.height;
        const over = (share) => document.elementFromPoint(r.left + share * r.width, y);
        const share = [0.2, 0.1, 0.8, 0.9, 0.05, 0.95].find((s) => over(s) === f);
        const x = r.left + (share ?? 0.2) * r.width, top = over(share ?? 0.2);
        return {x, y, on: top === f, over: top && `${top.tagName}#${top.id}.${top.className}`, size: [r.width, r.height],
            at: [(x - r.left) / r.width, (y - r.top) / r.height], canvas: [f.width, f.height],
            side: document.querySelector('#crop').width / 2};       // of what Detail shows at 200%, in picture px
    })()''')
    assert spot['on'], spot
    w, h = spot['size']
    # the case: in this window one ratio for both sides is off by more than half of what Detail shows
    assert abs(iw / w - ih / h) * spot['at'][1] * h > spot['side'] / 2, spot
    px, py = spot['at'][0] * iw, spot['at'][1] * ih
    for kind in ('mousePressed', 'mouseReleased'):
        page.send('Input.dispatchMouseEvent', type=kind, x=spot['x'], y=spot['y'], button='left', clickCount=1)
    page.wait_for('window.__crops.length > 0', timeout=20, what='Detail to be asked for at the place clicked')
    page.evaluate('new Promise((resolve) => setTimeout(resolve, 600))')
    x0, y0, cw, ch = page.evaluate('window.__crops.at(-1)')
    assert x0 <= px <= x0 + cw and y0 <= py <= y0 + ch, f'clicked ({px:.0f}, {py:.0f}), Detail shows {(x0, y0, cw, ch)}'
    # the frame on Whole: the rows of its canvas that hold the frame's white line
    top, bottom = page.evaluate('''(() => {
        const f = document.querySelector('#fit'), d = f.getContext('2d').getImageData(0, 0, f.width, f.height).data;
        const rows = [];
        for (let y = 0; y < f.height; y++) for (let x = 0; x < f.width; x++) {
            const i = 4 * (y * f.width + x);
            if (Math.min(d[i], d[i + 1], d[i + 2]) >= 236) { rows.push(y); break; }
        }
        return [rows[0], rows.at(-1)];
    })()''')
    k = spot['canvas'][1] / ih
    assert abs(top - y0 * k) <= 2 and abs(bottom - (y0 + ch) * k) <= 2, \
        f'the frame is on rows {top}..{bottom}, Detail shows rows {y0 * k:.1f}..{(y0 + ch) * k:.1f}'


def test_a_whole_narrower_than_the_compare_slider_can_still_be_clicked_and_the_slider_dragged(check_ui):
    # At a large interface size, Whole of a picture ten times as high as it is wide is narrower than the strip the
    # compare slider is grabbed by. A click on Whole must still reach the picture (it moves Detail there), anywhere
    # but on the slider's round grip; and the grip must still drag the slider.
    server, page = check_ui
    server.set_lang('en')
    iw, ih = 300, 3000
    check_document(server, image_size=(iw, ih))
    show(check_ui, 'en', 175, (500, 1150), look=1)
    page.wait_for('''document.querySelector('#fade-note').textContent && document.querySelector('#crop').width > 2
        && /^(缩到窗口|Scaled)/.test(document.querySelector('#fit-status').textContent)''', timeout=60,
                  what='the previews and the rows')
    spot = page.evaluate('''(async () => {
        const real = window.fetch;
        window.__crops = [];
        window.fetch = (url, opt) => {
            const to = String(url);
            if (to.includes('/render/crop?')) {
                const q = new URL(to, location.href).searchParams;
                window.__crops.push(['x0', 'y0', 'w', 'h'].map((k) => +q.get(k)));
            }
            return real(url, opt);
        };
        const f = document.querySelector('#fit');
        f.scrollIntoView({block: 'center'});
        await new Promise((go) => requestAnimationFrame(() => requestAnimationFrame(go)));
        const r = f.getBoundingClientRect(), g = document.querySelector('.compare-grip').getBoundingClientRect();
        // on the slider's own line, a fifth of the way down: well clear of the grip, which is at mid-height
        const x = r.left + r.width / 2, y = r.top + 0.2 * r.height, top = document.elementFromPoint(x, y);
        return {x, y, on: top === f, over: top && `${top.tagName}#${top.id}.${top.className}`,
            size: [r.width, r.height], strip: document.querySelector('#compare').getBoundingClientRect().width,
            grip: [g.left + g.width / 2, g.top + g.height / 2], left: r.left, width: r.width};
    })()''')
    assert spot['size'][0] < spot['strip'], f'not the case: Whole is wider than the strip of the slider: {spot}'
    assert spot['on'], f'a click on Whole lands on the compare slider: {spot}'
    for kind in ('mousePressed', 'mouseReleased'):
        page.send('Input.dispatchMouseEvent', type=kind, x=spot['x'], y=spot['y'], button='left', clickCount=1)
    page.wait_for('window.__crops.length > 0', timeout=20, what='Detail to be asked for at the place clicked')
    page.evaluate('new Promise((resolve) => setTimeout(resolve, 600))')
    x0, y0, cw, ch = page.evaluate('window.__crops.at(-1)')
    assert y0 <= 0.2 * ih <= y0 + ch, f'clicked a fifth of the way down ({0.2 * ih:.0f}), Detail shows {(x0, y0, cw, ch)}'
    # the grip is still the slider's: dragged to the right edge of Whole, most of it shows the original
    at = '+document.querySelector("#compare").getAttribute("aria-valuenow")'
    assert page.evaluate(at) == 50
    gx, gy = spot['grip']
    page.send('Input.dispatchMouseEvent', type='mousePressed', x=gx, y=gy, button='left', clickCount=1)
    page.send('Input.dispatchMouseEvent', type='mouseMoved', x=spot['left'] + spot['width'] - 1, y=gy, button='left',
              buttons=1)
    page.send('Input.dispatchMouseEvent', type='mouseReleased', x=spot['left'] + spot['width'] - 1, y=gy, button='left',
              clickCount=1)
    page.wait_for(f'{at} >= 90', timeout=10, what='the grip to drag the slider to the right')


def test_whole_shows_the_original_and_the_yellow_marks_when_nothing_gets_texture(check_ui):
    # The only painted region can have direction lines and still fail to solve: the Texture page opens, nothing is
    # textured, and the yellow row names the region. Whole must then show the picture, with the yellow on it when
    # the box is ticked, not an empty grey effect side. Only the public /look answer is changed here (it says nothing
    # is textured); the marks are the real server's, for the region of the picture that has no line.
    server, page = check_ui
    script = page.send('Page.addScriptToEvaluateOnNewDocument', source='''(() => {
        const real = window.fetch;
        window.fetch = async (url, opt) => {
            const res = await real(url, opt);
            if (!/\\/api\\/doc\\/[^/]+\\/look(\\?|$)/.test(String(url)) || !res.ok) return res;
            const info = await res.json();
            if (info && 'textured' in info) info.textured = 0;
            return Response.json(info, {status: res.status});
        };
    })()''')['identifier']
    try:
        check_page(check_ui)
        corner = '''(() => {
            const f = document.querySelector('#fit');
            return [...f.getContext('2d').getImageData(f.width - 4, 4, 1, 1).data].slice(0, 3);
        })()'''
        # the effect side, right of the compare slider, is the picture's own grey (157), not the stage's (84)
        page.wait_for(f'{corner}.every(v => Math.abs(v - 157) < 8)', timeout=20, what='Whole to show the picture')
        page.click('#show-problems')
        seen = marks(page, 'm.yellow > 20', timeout=20)
        assert seen['original'] == 0, seen
        page.click('#show-problems')
        marks(page, 'm.yellow === 0', timeout=20)
        assert page.evaluate(f'{corner}.every(v => Math.abs(v - 157) < 8)')
    finally:
        page.send('Page.removeScriptToEvaluateOnNewDocument', identifier=script)


# Detail's side, the width the previews have and whether they scroll, on each of 24 frames in a row.
LAYOUT_FRAMES = '''new Promise(go => {
    const seen = [], stage = document.querySelector('#stage'), crop = document.querySelector('#crop');
    const tick = () => {
        seen.push([crop.getBoundingClientRect().width, stage.clientWidth, stage.scrollHeight - stage.clientHeight > 1].join('/'));
        if (seen.length < 24) requestAnimationFrame(tick); else go(seen);
    };
    requestAnimationFrame(tick);
})'''


@pytest.mark.parametrize('size', ((352, 840), (700, 780), (696, 780)), ids=lambda s: f'{s[0]}x{s[1]}')
def test_the_layout_comes_to_rest_where_a_scroll_bar_changes_the_room(check_ui, size):
    # At these sizes the plan for the full width scrolls, and the plan for the width a scroll bar leaves does not:
    # the bar must not come and go with the plan, frame after frame.
    server, page = check_page(check_ui)
    page.resize(*size)
    uibrowser.time.sleep(0.6)
    seen = page.evaluate(LAYOUT_FRAMES)
    assert len(set(seen[4:])) == 1, sorted(set(seen))
    assert_check_layout(page, (448, 352))


# ------------------------------------------------------------------ the check group: what the first cases let through

def test_the_original_side_has_no_marks_wherever_the_compare_slider_is(check_ui):
    # where the slider rests by default nothing of the picture's marks lies left of it, so that position proves
    # nothing: the slider is moved with its own keys to where marks would lie on the original side if they were drawn
    server, page = check_page(check_ui)
    at = '+document.querySelector("#compare").getAttribute("aria-valuenow")'
    page.click('#show-problems')
    marks(page, ALL_MARKS)
    page.evaluate('document.querySelector("#compare").focus()')
    press(page, 'End', 'End', 35)                   # all original
    page.wait_for(f'{at} >= 99', what='the slider at the end')
    seen = marks(page, 'm.red + m.blue + m.yellow === 0')
    assert seen['original'] == 0, seen
    press(page, 'Home', 'Home', 36)                 # all effect
    page.wait_for(f'{at} <= 1', what='the slider at the start')
    whole = marks(page, 'm.red > 50 && m.blue > 20 && m.yellow > 20')
    assert whole['original'] == 0, whole
    for _ in range(40):                             # and across the red marks, part of them on each side
        if page.evaluate(at) >= 62:
            break
        press(page, 'ArrowRight', 'ArrowRight', 39, shift=True)
    assert 62 <= page.evaluate(at) <= 85, page.evaluate(at)
    part = marks(page, f'm.red < {whole["red"]} && m.original === 0')
    assert part['yellow'] > 20, part


def test_exports_made_with_and_without_the_marks_showing_are_the_same_pixels(check_ui, tmp_path):
    import cv2
    import numpy as np

    server, page = check_page(check_ui)
    # Only the system's save dialog is answered here; both files are written by the real server.
    page.evaluate('''(() => {
        const real = window.fetch;
        window.fetch = (url, opt) => String(url).endsWith('/export/ask')
            ? Promise.resolve(Response.json({path: window.__exportTo})) : real(url, opt);
    })()''')
    written = []
    for ticked in (True, False):
        if page.evaluate('document.querySelector("#show-problems").checked') != ticked:
            page.click('#show-problems')
        marks(page, ALL_MARKS if ticked else 'm.red + m.blue + m.yellow + m.detailRed + m.detailBlue === 0')
        target = tmp_path / f'marks-{"on" if ticked else "off"}.png'
        page.evaluate(f'window.__exportTo = {json.dumps(str(target))}')
        page.click('#btn-export')
        uibrowser._wait(f'{target.name} to be written', target.is_file, 60)
        page.wait_for('!document.querySelector("#exported").hidden', timeout=60, what='the export receipt')
        page.click('#btn-exported-close')
        written.append(cv2.imdecode(np.fromfile(str(target), np.uint8), cv2.IMREAD_UNCHANGED))
    assert written[0].shape == written[1].shape and written[0].shape[:2] == (352, 448)
    assert np.array_equal(written[0], written[1]), 'showing the marks changed what was exported'
    assert (written[0][..., :3] != 157).any(axis=2).sum() > 5000, 'the export is the picture, not a blank'


CANVAS_HASH = '''['#fit', '#crop'].map((s) => {
    const c = document.querySelector(s), d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    let h = 0;
    for (let i = 0; i < d.length; i += 4) h = (h * 31 + d[i] + 3 * d[i + 1] + 7 * d[i + 2]) | 0;
    return h;
})'''


def test_the_group_is_reached_and_really_works_in_a_short_window(check_ui):
    server, page = check_page(check_ui, 'en', 175, (720, 480))
    assert page.evaluate('(() => { const s = document.querySelector("#stage"); return s.scrollHeight > s.clientHeight + 20; })()')

    def reach(control):
        """Scroll the previews to the control; it must then be in what shows, with nothing over it."""
        page.evaluate(f'''new Promise(go => {{
            document.querySelector('{control}').scrollIntoView({{block: 'center'}});
            requestAnimationFrame(() => requestAnimationFrame(go));
        }})''')
        assert page.evaluate(f'''(() => {{
            const e = document.querySelector('{control}'), r = e.getBoundingClientRect();
            const s = document.querySelector('#stage').getBoundingClientRect();
            const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
            const own = top && (top === e || (top.closest('.switch, label') || top).contains(e));
            return r.top >= s.top && r.bottom <= s.bottom && !!own;
        }})()'''), f'{control} cannot be scrolled into view and clicked'

    def redrawn(drawn):
        page.wait_for(f'(() => {{ const h = {CANVAS_HASH}; return h[0] !== {drawn[0]} && h[1] !== {drawn[1]}; }})()',
                      timeout=60, what='both previews to be drawn again')
        return page.evaluate(CANVAS_HASH)

    page.hover('.status')
    before = resting_places(page)
    drawn = page.evaluate(CANVAS_HASH)
    # not ticked: each switch still changes both pictures, and the row's new words move nothing
    reach('#exclude')
    page.click('#exclude')
    page.wait_for(f'{SWITCHES}[1] === false', what='Color exclusion to turn off')
    drawn = redrawn(drawn)
    page.hover('.status')
    assert resting_places(page) == before
    reach('#fade')
    page.click('#fade')
    page.wait_for(f'{SWITCHES}[0] === false', what='Texture fade to turn off')
    redrawn(drawn)
    reach('#show-problems')
    page.click('#show-problems')
    assert page.evaluate('document.querySelector("#show-problems").checked')
    assert page.evaluate(CHECK_KEYS) == [False, False, True]
    marks(page, 'm.yellow > 0 && m.red === 0 && m.blue === 0')
    page.hover('.status')
    assert resting_places(page) == before


@pytest.mark.parametrize('lang, untextured, solving, none, suffix', (
    ('zh', ['测试部位', '左腿分开的一块'], ['右腿'], '没有。', '（求解中…）'),
    ('en', ['Test region', 'Separate piece of Left leg'], ['Right leg'], 'None.', '(solving…)'),
    ('en', [], ['Right leg'], 'None.', '(solving…)'),
    ('zh', ['测试部位'], [], '没有。', '（求解中…）'),
), ids=('zh-failed-detached-solving', 'en-failed-detached-solving', 'en-only-solving', 'zh-failed-alone'))
def test_the_yellow_row_reads_the_lists_the_server_gives(check_ui, lang, untextured, solving, none, suffix):
    # The server names what gets no texture (a region with no line or a failed solve by its name, a detached piece in
    # its own words) and, apart from them, what is still solving: the backend's tests prove where the lists come from.
    # Here only those two lists of the public /look answer are set, and the row must say them as they are.
    server, page = check_ui
    script = page.send('Page.addScriptToEvaluateOnNewDocument', source=f'''(() => {{
        const real = window.fetch;
        window.fetch = async (url, opt) => {{
            const res = await real(url, opt);
            if (!/\\/api\\/doc\\/[^/]+\\/look(\\?|$)/.test(String(url)) || !res.ok) return res;
            const info = await res.json();
            if (info && 'untextured' in info) Object.assign(info, {json.dumps({'untextured': untextured, 'solving': solving})});
            return Response.json(info, {{status: res.status}});
        }};
    }})()''')['identifier']
    try:
        check_page(check_ui, lang, 100, (1024, 768))
        seen = page.evaluate('''(() => {
            const row = document.querySelector('#check-nostroke'), text = (s) => document.querySelector(s);
            return { row: row.textContent, tip: row.dataset.tip || '',
                oneLine: row.getBoundingClientRect().height < 1.6 * parseFloat(getComputedStyle(row).lineHeight),
                names: text('#nostroke-names').hidden ? null : text('#nostroke-names').textContent,
                solving: text('#nostroke-solving').hidden ? null : text('#nostroke-solving').textContent,
                fade: text('#fade-note').textContent, exclude: text('#exclude-note').textContent };
        })()''')
        assert seen['oneLine'], seen
        if untextured:
            assert all(name in seen['row'] and name in seen['names'] and name in seen['tip'] for name in untextured), seen
            assert not seen['row'].startswith(none), seen
        else:
            assert seen['row'].startswith(none) and seen['names'] is None, seen
        if solving:
            # still solving: said after the list, never in it; named in the full note and the tip; no share shown yet
            assert seen['row'].rstrip().endswith(suffix), seen
            assert all(name not in seen['row'] and name not in (seen['names'] or '') for name in solving), seen
            assert all(name in seen['solving'] and name in seen['tip'] for name in solving), seen
            assert '%' not in seen['fade'] and '%' not in seen['exclude'], seen
        else:
            assert suffix not in seen['row'] and seen['solving'] is None, seen
        if lang == 'en':
            assert not page.evaluate('/[\\u4e00-\\u9fff]/.test(document.querySelector("#check-group").innerText)')
        assert_check_layout(page, (448, 352))
    finally:
        page.send('Page.removeScriptToEvaluateOnNewDocument', identifier=script)


def test_one_page_through_windows_that_dock_the_group_differently(check_ui):
    # no reload between them: the same page is given one real window after another, and the group goes under Detail,
    # under both previews or beside them as each window has room for; whichever it is, nothing overflows or overlaps
    server, page = check_page(check_ui)
    where = []
    for size in ((1440, 900), (1024, 768), (1600, 600), (360, 840), (700, 1100), (1440, 900)):
        page.resize(*size)
        uibrowser.time.sleep(0.5)
        page.hover('.status')
        resting_places(page)
        view = assert_check_layout(page, (448, 352))
        (cx, cy, cw, ch), (gx, gy, gw, gh) = view['rects']['#crop'], view['rects']['#check-group']
        where.append('beside' if gx >= cx + cw - 1 else 'under Detail' if abs(gx - cx) <= 2 and gy > cy + ch
                     else 'below' if gy > cy + ch else 'elsewhere')
    assert len(set(where)) >= 3 and 'elsewhere' not in where, where
    # Back in the first window the page may keep the dock it came with, where two docks are about as good (it holds
    # on to the one in use so that a window being dragged does not flip between them). That is the only memory there
    # is: the same window opened afresh is arranged as it first was.
    page.goto(server.url + '/?page=look')
    page.wait_for('document.body.dataset.mode === "look" && !!document.querySelector("#fade-note").textContent',
                  what='the Texture page after a reload')
    page.hover('.status')
    resting_places(page)
    view = assert_check_layout(page, (448, 352))
    (cx, cy, cw, ch), (gx, gy, gw, gh) = view['rects']['#crop'], view['rects']['#check-group']
    assert abs(gx - cx) <= 2 and gy > cy + ch, (where, view)
    page.check_errors()


def test_the_interface_size_control_lays_the_page_out_anew(check_ui):
    # the control itself (it reloads the page, as it always has), not the server's setting from outside
    server, page = check_page(check_ui, 'en', 100, (1024, 768))
    before = assert_check_layout(page, (448, 352))
    try:
        page.evaluate('''(() => {
            const s = document.querySelector('#ui-scale');
            s.value = '150';
            s.dispatchEvent(new Event('change', {bubbles: true}));
        })()''')
        page.wait_for('''getComputedStyle(document.documentElement).getPropertyValue('--k').trim() === '1.5'
            && document.body.dataset.mode === 'look' && !!document.querySelector('#fade-note').textContent
            && /^(缩到窗口|Scaled)/.test(document.querySelector('#fit-status').textContent)''', timeout=60,
                      what='the page at 150%')
        after = assert_check_layout(page, (448, 352))
        assert after['rects']['#check-group'][3] > before['rects']['#check-group'][3], (before, after)
        for control in CHECK_CONTROLS:
            assert page.evaluate(f'document.querySelector("{control}").checkVisibility({{visibilityProperty: true}})')
    finally:
        server.set_scale(100)

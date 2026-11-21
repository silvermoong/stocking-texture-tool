"""Guide tool habits in the real page, with test-owned settings and a fresh browser profile."""
import contextlib
import json
import time
from pathlib import Path

import pytest

import uibrowser


PREFS = ('cut_snap', 'wall_snap', 'fill_seams')
CHECKED = ('["#cut-snap", "#wall-snap", "#fill-seams"]'
           '.map(id => document.querySelector(id).checked)')


@pytest.fixture
def tools_ui(tmp_path):
    uibrowser.require()
    with uibrowser.running(tmp_path, keep_settings=True) as (server, browser):
        uibrowser.synthetic_document(server)
        with contextlib.closing(browser.page()) as page:
            yield server, page


def settings_on_disk(server):
    path = Path(server.settings_path)
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}


def open_guides(server, page):
    page.goto(server.url + '/')
    page.wait_for('!document.body.classList.contains("no-doc")', what='the document to show')


def wait_for_saved_preference(page, key, on):
    # Wait through the page's public boot response before opening the file: on Windows a concurrent reader
    # of the JSON file could itself get in the way of the server's atomic replace.
    page.wait_for(f'''(async () => {{
        const html = await (await fetch('/')).text();
        const root = new DOMParser().parseFromString(html, 'text/html').documentElement;
        return JSON.parse(root.dataset.toolPrefs)[{json.dumps(key)}] === {json.dumps(on)};
    }})()''', timeout=10, what=f'{key} to be stored as {on}')


def test_a_saved_tool_preference_survives_reload_and_new_port(tools_ui):
    server, page = tools_ui
    open_guides(server, page)
    assert not (settings_on_disk(server).keys() & set(PREFS))
    assert page.evaluate(CHECKED) == [True, True, True]

    page.click('[data-tool="cut"]')
    page.wait_for('!document.querySelector("#cutbar").hidden')
    page.click('#cut-snap')
    assert page.evaluate(CHECKED) == [False, True, True]
    assert page.evaluate('localStorage.getItem("cut_snap")') is None  # ordinary toggles no longer write here
    wait_for_saved_preference(page, 'cut_snap', False)
    assert settings_on_disk(server)['cut_snap'] is False
    open_guides(server, page)
    assert page.evaluate(CHECKED) == [False, True, True]

    page.evaluate('localStorage.setItem("origin-marker", "old")')
    page.check_errors()
    page.send('Page.navigate', url='about:blank')       # close the old event stream before stopping its server
    page.wait_for('location.href === "about:blank"')
    port, path = server.port, server.settings_path
    server.stop()
    server.start()
    assert server.port != port and server.settings_path == path
    uibrowser.synthetic_document(server)
    open_guides(server, page)
    assert page.evaluate('localStorage.getItem("origin-marker")') is None
    assert page.evaluate(CHECKED) == [False, True, True]


def seed_legacy_values(server, page, **values):
    open_guides(server, page)
    page.evaluate(f'Object.entries({json.dumps(values)}).forEach(([key, value]) => localStorage.setItem(key, value))')


def test_legacy_tool_values_migrate_and_server_wins_both_conflicts(tools_ui):
    server, page = tools_ui
    server.api('/api/tool-preferences/wall_snap', 'PUT', {'on': True})
    server.api('/api/tool-preferences/fill_seams', 'PUT', {'on': False})
    seed_legacy_values(server, page, cut_snap='0', wall_snap='0', fill_seams='1', unrelated='keep')
    open_guides(server, page)

    page.wait_for(f'{json.dumps(PREFS)}.every(key => localStorage.getItem(key) === null)',
                  timeout=10, what='the acknowledged and superseded keys to be removed')
    assert page.evaluate(CHECKED) == [False, True, False]
    assert page.evaluate('localStorage.getItem("unrelated")') == 'keep'
    assert {key: settings_on_disk(server)[key] for key in PREFS} == {
        'cut_snap': False, 'wall_snap': True, 'fill_seams': False,
    }


def test_a_failed_legacy_write_retries_on_next_start(tools_ui):
    server, page = tools_ui
    seed_legacy_values(server, page, cut_snap='0')
    script = page.send('Page.addScriptToEvaluateOnNewDocument', source='''(() => {
        const real = window.fetch;
        window.fetch = async (url, opt) => {
            if (url !== '/api/tool-preferences/cut_snap' || opt?.method !== 'PUT') return real(url, opt);
            window.failedMigration = JSON.parse(opt.body);
            return Response.json({ detail: 'test write failure' }, { status: 503 });
        };
    })()''')['identifier']
    open_guides(server, page)
    assert page.evaluate('window.failedMigration') == {'on': False, 'only_if_unset': True}
    assert page.evaluate(CHECKED) == [False, True, True]
    assert page.evaluate('localStorage.getItem("cut_snap")') == '0'
    assert not page.evaluate('document.querySelector("#status-msg").matches(".error")')
    assert 'cut_snap' not in settings_on_disk(server)

    page.send('Page.removeScriptToEvaluateOnNewDocument', identifier=script)
    open_guides(server, page)
    page.wait_for('localStorage.getItem("cut_snap") === null', timeout=10, what='the successful retry')
    assert page.evaluate(CHECKED) == [False, True, True]
    assert settings_on_disk(server)['cut_snap'] is False


def test_a_failed_daily_write_reports_the_error_but_leaves_the_choice(tools_ui):
    server, page = tools_ui
    server.api('/api/tool-preferences/wall_snap', 'PUT', {'on': True})
    open_guides(server, page)
    page.evaluate('''(() => {
        const real = window.fetch;
        window.fetch = (url, opt) => url === '/api/tool-preferences/wall_snap' && opt?.method === 'PUT'
            ? Promise.resolve(Response.json({ detail: 'test write failure' }, { status: 503 })) : real(url, opt);
    })()''')
    page.click('[data-tool="wall"]')
    page.wait_for('!document.querySelector("#wallbar").hidden')
    page.click('#wall-snap')
    page.wait_for('document.querySelector("#status-msg.error")?.textContent === "test write failure"')
    assert page.evaluate(CHECKED) == [True, False, True]
    assert settings_on_disk(server)['wall_snap'] is True
    open_guides(server, page)
    assert page.evaluate(CHECKED) == [True, True, True]


def test_a_real_reload_shows_the_stored_value_not_the_form_state_the_browser_kept(tools_ui):
    # Switching language or interface size reloads the page in place, and a browser may restore form controls then.
    server, page = tools_ui
    server.api('/api/tool-preferences/fill_seams', 'PUT', {'on': False})
    open_guides(server, page)
    assert page.evaluate(CHECKED) == [True, True, False]
    page.evaluate('''(() => {
        const real = window.fetch;
        window.fetch = (url, opt) => url === '/api/tool-preferences/cut_snap' && opt?.method === 'PUT'
            ? Promise.resolve(Response.json({ detail: 'test write failure' }, { status: 503 })) : real(url, opt);
    })()''')
    page.click('[data-tool="cut"]')
    page.wait_for('!document.querySelector("#cutbar").hidden')
    page.click('#cut-snap')
    page.wait_for('document.querySelector("#status-msg.error")?.textContent === "test write failure"')
    assert page.evaluate(CHECKED) == [False, True, False]
    server.api('/api/tool-preferences/wall_snap', 'PUT', {'on': False})  # saved elsewhere while this page was open

    page.evaluate('window.__leaving = true')
    page.evaluate('location.reload()')
    page.wait_for('!window.__leaving && document.readyState === "complete"'
                  ' && document.documentElement.classList.contains("i18n-done")'
                  ' && !document.body.classList.contains("no-doc")', timeout=30, what='the reloaded page')
    assert page.evaluate(CHECKED) == [True, False, False]
    assert 'cut_snap' not in settings_on_disk(server)


# The moment the old page starts waiting before it reloads itself, and the limit of that wait, without spending it:
# once the answer to the language POST has been handed to the page, the long timer it starts is recorded and kept
# for the test to end (window.endReloadWait) instead of running. Short timers and everything before then are real.
RELOAD_WAIT = '''(() => {
    const fetchNow = window.fetch, later = window.setTimeout;
    window.reloadWaits = [];
    window.fetch = async (url, opt) => {
        const answer = await fetchNow.call(window, url, opt);
        if (url === '/api/lang' && opt?.method === 'POST') window.languageStored = true;
        return answer;
    };
    window.setTimeout = (fn, ms, ...rest) => {
        if (!window.languageStored || !(ms >= 1000)) return later.call(window, fn, ms, ...rest);
        window.reloadWaits.push(ms);
        window.endReloadWait = fn;
        return 0;
    };
})()'''
WAITING_ON_THE_OLD_PAGE = 'window.__leaving === true && window.reloadWaits.length === 1'


def test_switching_language_does_not_drop_a_choice_still_waiting_to_be_saved(tools_ui):
    server, page = tools_ui
    page.send('Page.addScriptToEvaluateOnNewDocument', source=RELOAD_WAIT)
    page.send('Page.addScriptToEvaluateOnNewDocument', source='''(() => {
        const real = window.fetch;
        let held = false;
        window.fetch = (url, opt) => {
            if (held || url !== '/api/tool-preferences/cut_snap' || opt?.method !== 'PUT') return real(url, opt);
            held = true;                               // the request goes out now; only its answer is slow
            const sent = real(url, opt);
            return new Promise(resolve => { window.answerFirstSave = () => resolve(sent); });
        };
    })()''')
    open_guides(server, page)
    lang = page.evaluate('document.documentElement.lang')
    page.click('[data-tool="cut"]')
    page.wait_for('!document.querySelector("#cutbar").hidden')
    page.click('#cut-snap')
    wait_for_saved_preference(page, 'cut_snap', False)
    page.click('#cut-snap')                            # back on: this save waits behind the first one's answer
    assert page.evaluate(CHECKED) == [True, True, True]

    page.evaluate('window.__leaving = true')
    page.click('.lang .seg-btn[aria-checked="false"]')  # the page reloads itself in the other language
    # The language is stored and its answer handled, and the page is still the old one, waiting for the saves:
    # only now is the first save answered. With the limit's timer kept, nothing else can end the wait.
    page.wait_for(WAITING_ON_THE_OLD_PAGE, timeout=10, what='the old page to wait for its saves before reloading')
    assert page.evaluate(CHECKED) == [True, True, True]
    assert settings_on_disk(server)['cut_snap'] is False   # the second save has not gone out yet
    page.evaluate('window.answerFirstSave()')
    page.wait_for(f'!window.__leaving && document.documentElement.lang !== {json.dumps(lang)}'
                  ' && document.readyState === "complete"'
                  ' && document.documentElement.classList.contains("i18n-done")'
                  ' && !document.body.classList.contains("no-doc")', timeout=30, what='the page in the other language')
    assert page.evaluate(CHECKED) == [True, True, True]
    assert settings_on_disk(server)['cut_snap'] is True


def test_a_save_that_is_never_answered_holds_up_the_language_switch_for_three_seconds_at_most(tools_ui):
    server, page = tools_ui
    page.send('Page.addScriptToEvaluateOnNewDocument', source=RELOAD_WAIT)
    page.send('Page.addScriptToEvaluateOnNewDocument', source='''(() => {
        const real = window.fetch;
        window.fetch = (url, opt) => url === '/api/tool-preferences/cut_snap' && opt?.method === 'PUT'
            ? new Promise(() => {}) : real(url, opt);
    })()''')
    open_guides(server, page)
    lang = page.evaluate('document.documentElement.lang')
    page.click('[data-tool="cut"]')
    page.wait_for('!document.querySelector("#cutbar").hidden')
    page.click('#cut-snap')
    assert page.evaluate(CHECKED) == [False, True, True]

    page.evaluate('window.__leaving = true')
    page.click('.lang .seg-btn[aria-checked="false"]')
    page.wait_for(WAITING_ON_THE_OLD_PAGE, timeout=10, what='the old page to wait for its save before reloading')
    assert page.evaluate('window.reloadWaits') == [3000]   # the limit itself; its timer is the test's to end
    time.sleep(0.5)                                        # with the save unanswered and the limit not yet reached,
    assert page.evaluate(WAITING_ON_THE_OLD_PAGE)          # the page stays; without a limit it would stay for good
    assert page.evaluate(CHECKED) == [False, True, True]
    page.evaluate('window.endReloadWait()')                # three seconds are up
    page.wait_for(f'!window.__leaving && document.documentElement.lang !== {json.dumps(lang)}'
                  ' && document.readyState === "complete"'
                  ' && document.documentElement.classList.contains("i18n-done")'
                  ' && !document.body.classList.contains("no-doc")', timeout=30, what='the page in the other language')
    assert page.evaluate(CHECKED) == [True, True, True]   # what is stored: that choice never reached the server
    assert 'cut_snap' not in settings_on_disk(server)


def test_a_migration_that_started_on_a_stale_page_cannot_replace_a_new_save(tools_ui):
    server, page = tools_ui
    seed_legacy_values(server, page, cut_snap='0')
    page.send('Page.addScriptToEvaluateOnNewDocument', source='''(() => {
        const real = window.fetch;
        window.fetch = (url, opt) => {
            if (url !== '/api/tool-preferences/cut_snap' || opt?.method !== 'PUT') return real(url, opt);
            return new Promise(resolve => { window.sendMigration = () => resolve(real(url, opt)); });
        };
    })()''')
    open_guides(server, page)
    page.wait_for('!!window.sendMigration', timeout=10, what='the initial migration to wait at the network')
    assert page.evaluate(CHECKED) == [False, True, True]  # the old value is already usable, before fetch completes
    assert page.evaluate('localStorage.getItem("cut_snap")') == '0'
    server.api('/api/tool-preferences/cut_snap', 'PUT', {'on': True})  # a normal save from another page got there first
    page.evaluate('window.sendMigration()')
    page.wait_for('localStorage.getItem("cut_snap") === null', timeout=10)
    assert page.evaluate(CHECKED) == [True, True, True]
    assert settings_on_disk(server)['cut_snap'] is True


# Replace only the model's candidates in the isolated process. Picks, mask edits, history, and HTTP are real.
SYNTHETIC_PICK_MODEL = '''
import numpy as np
from stocking import sam

def candidates(doc, x, y):
    mask = np.zeros((doc.h, doc.w), dtype=bool)
    if x < 35:
        mask[20:80, 10:40] = True
    else:
        mask[20:80, 43:80] = True
    return [mask] * 3, 0, [1.0] * 3

sam.service.candidates = candidates
'''


def test_fill_gaps_is_ready_for_the_first_pick_and_redoes_only_on_change(tmp_path, monkeypatch):
    uibrowser.require()
    monkeypatch.setattr(uibrowser, '_CHILD', SYNTHETIC_PICK_MODEL + uibrowser._CHILD)
    with uibrowser.running(tmp_path, keep_settings=True) as (server, browser), contextlib.closing(browser.page()) as page:
        st = server.upload('thin-gap.png', uibrowser.synthetic_png(w=100, h=100))
        doc, rid = f'/api/doc/{st["id"]}', st['regions'][0]['id']
        server.api(f'{doc}/regions/{rid}/segment', 'POST', {'x': 20, 'y': 50, 'seams': True})
        page.send('Page.addScriptToEvaluateOnNewDocument', source='''(() => {
            window.picks = [];
            const real = window.fetch;
            window.fetch = (url, opt) => {
                if (opt?.method === 'POST' && /\\/segment(\\/select)?$/.test(url)) {
                    window.picks.push({ select: url.endsWith('/select'), ...JSON.parse(opt.body) });
                }
                return real(url, opt);
            };
        })()''')
        visible = 'document.querySelector("#fill-seams").checkVisibility()'
        open_guides(server, page)
        page.wait_for(visible)
        page.click('#fill-seams')
        wait_for_saved_preference(page, 'fill_seams', False)
        open_guides(server, page)
        page.wait_for(visible)
        assert page.evaluate(CHECKED) == [True, True, False]
        assert page.evaluate('window.picks') == []  # restoring the checkbox did not redo the visible pick

        open_pieces = 60 * (30 + 37)

        def pixels():
            return server.api(f'{doc}/coverage/stats')['regions'][0]['pixels']

        page.click('#view')
        page.wait_for('window.picks.length === 1', what='the first pick after reloading')
        first = page.evaluate('window.picks[0]')
        assert first['select'] is False and first['seams'] is False, first
        uibrowser._wait('the two pieces without their seam', lambda: pixels() == open_pieces, 10)

        page.wait_for(visible)
        page.click('#fill-seams')
        page.wait_for('window.picks.length === 2', what='redo of the visible pick')
        assert page.evaluate('window.picks[1]') == {'select': True, 'k': 0, 'seams': True}
        uibrowser._wait('the seam to fill', lambda: pixels() > open_pieces, 10)
        page.click('#btn-undo')
        uibrowser._wait('a single undo to take back the second pick and its seam', lambda: pixels() == 60 * 30, 10)
        assert page.evaluate(CHECKED) == [True, True, True]  # the tool preference isn't part of that edit


def test_a_failed_fill_gaps_save_is_not_replaced_by_the_news_of_the_pick_it_redid(tmp_path, monkeypatch):
    uibrowser.require()
    monkeypatch.setattr(uibrowser, '_CHILD', SYNTHETIC_PICK_MODEL + uibrowser._CHILD)
    with uibrowser.running(tmp_path, keep_settings=True) as (server, browser), contextlib.closing(browser.page()) as page:
        st = server.upload('thin-gap.png', uibrowser.synthetic_png(w=100, h=100))
        doc, rid = f'/api/doc/{st["id"]}', st['regions'][0]['id']
        server.api(f'{doc}/regions/{rid}/segment', 'POST', {'x': 20, 'y': 50, 'seams': True})
        page.send('Page.addScriptToEvaluateOnNewDocument', source='''(() => {
            window.redone = 0;
            const real = window.fetch;
            window.fetch = async (url, opt) => {
                if (url === '/api/tool-preferences/fill_seams' && opt?.method === 'PUT') {
                    return Response.json({ detail: 'test write failure' }, { status: 503 });
                }
                const answer = await real(url, opt);
                if (opt?.method === 'POST' && url.endsWith('/segment/select')) window.redone++;
                return answer;
            };
            const Real = window.EventSource;       // the page's own stream, to hand it an event at a chosen moment
            window.EventSource = class extends Real { constructor(...a) { super(...a); window.events = this; } };
        })()''')
        open_guides(server, page)
        page.wait_for('document.querySelector("#fill-seams").checkVisibility()')
        page.click('#fill-seams')
        failed = 'document.querySelector("#status-msg.error")?.textContent === "test write failure"'
        page.wait_for(failed, what='the failed save to be reported')
        page.wait_for('window.redone === 1', what='the redo of the visible pick')
        assert page.evaluate(CHECKED) == [True, True, False]

        # the redone pick changed the region, so its courses are solved again: that success arrives moments later
        solved = json.dumps(json.dumps({'type': 'solved', 'doc': st['id'], 'region': rid, 'seconds': 0.1}))
        page.evaluate(f'window.events.onmessage({{ data: {solved} }})')
        assert page.evaluate(failed), page.evaluate('document.querySelector("#status-msg").textContent')

        page.wait_for('document.querySelector("#status-msg").textContent === ""', timeout=15, what='the error to time out')
        page.evaluate(f'window.events.onmessage({{ data: {solved} }})')
        assert page.evaluate('(() => { const el = document.querySelector("#status-msg");'
                             ' return !!el.textContent && !el.matches(".error"); })()')  # ordinary news goes on

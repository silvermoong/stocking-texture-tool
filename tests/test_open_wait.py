"""The page's side of asking before an image is replaced (static/openwait.js), run under node with stand-ins for the
dialog and the server: one question at a time, and a file that waits (handed to the running tool from outside) is
asked about in every window while only its own dialog is closed when another window answers."""
import json
import os
import pathlib
import shutil
import subprocess

import pytest

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'stocking', 'static')

HARNESS = r"""
import assert from 'node:assert/strict';
const { createReplaceGuard } = await import(MODULE);
const ticks = async (n = 8) => { for (let i = 0; i < n; i++) await new Promise((r) => setTimeout(r, 0)); };
const file = (id, name = 'b.png') => ({ id, path: 'C:/x/' + name, name });

function setup({ unsaved = true } = {}) {
  const log = [];
  let up = null;                        // resolves the dialog that is up
  const h = {
    log, doc: { id: 'A', name: 'a.png', unsaved_guides: unsaved }, pending: null, taken: null, gate: null, exported: true,
    rev: 0, snapshot: null, shown: null, docFails: false, cancelFails: false, timers: [],
    get dialogUp() { return up !== null; },
    answer(choice) { assert.ok(up, 'no dialog is up'); const r = up; up = null; r(choice); },
  };
  h.guard = createReplaceGuard({
    latestDoc: async () => { if (h.docFails) throw new Error('no answer'); return h.doc; },
    shownDoc: () => h.shown,
    ask: () => { assert.equal(up, null, 'a second dialog over the first'); log.push('ask'); return new Promise((r) => { up = r; }); },
    dismiss: () => { if (up) { log.push('dismiss'); h.answer('cancel'); } },
    exportGuides: async () => { log.push('export'); return h.exported; },
    pending: async () => (h.snapshot ? h.snapshot() : { rev: h.rev, file: h.pending }),
    take: async (id) => {
      log.push('take ' + id);
      if (h.takeFails) { await new Promise((r) => setTimeout(r, 0)); throw new Error('lost'); }
      return h.taken ?? { id: 'B', name: 'b.png' };
    },
    cancel: async (id) => {
      log.push('cancel ' + id);
      if (h.gate) await h.gate;
      if (h.cancelFails) { h.cancelFails = false; throw new Error('lost'); }
    },
    opening: (name) => log.push('opening ' + name),
    opened: (st) => log.push('opened ' + st.name),
    failed: (e) => log.push('failed ' + e.message),
    done: () => log.push('done'),
    later: (fn) => { h.timers.push(fn); },
  });
  return h;
}

const cases = {
  async agreeing_opens_the_waiting_file() {
    const h = setup();
    h.guard.request(file('1'));
    await ticks();
    assert.ok(h.dialogUp);
    h.answer('discard');
    await ticks();
    assert.deepEqual(h.log, ['ask', 'opening b.png', 'take 1', 'opened b.png', 'done']);
  },
  async cancelling_tells_the_server_to_forget_it() {
    const h = setup();
    h.guard.request(file('1'));
    await ticks();
    h.answer('cancel');
    await ticks();
    assert.deepEqual(h.log, ['ask', 'cancel 1', 'done']);
  },
  async exporting_first_then_opens() {
    const h = setup();
    h.guard.request(file('1'));
    await ticks();
    h.answer('export');
    await ticks();
    assert.deepEqual(h.log, ['ask', 'export', 'opening b.png', 'take 1', 'opened b.png', 'done']);
    const k = setup();
    k.exported = false;                 // the save dialog was cancelled: the image stays, the file is forgotten
    k.guard.request(file('1'));
    await ticks();
    k.answer('export');
    await ticks();
    assert.deepEqual(k.log, ['ask', 'export', 'cancel 1', 'done']);
  },
  async with_nothing_to_lose_it_opens_without_asking() {
    const h = setup({ unsaved: false });
    h.guard.request(file('1'));
    await ticks();
    assert.deepEqual(h.log, ['opening b.png', 'take 1', 'opened b.png', 'done']);
  },
  async an_answer_the_server_no_longer_takes_changes_nothing_here() {
    const h = setup();
    h.taken = { settled: true };
    h.guard.request(file('1'));
    await ticks();
    h.answer('discard');
    await ticks();
    assert.deepEqual(h.log, ['ask', 'opening b.png', 'take 1', 'done']);
  },
  async the_same_file_seen_twice_is_asked_about_once() {
    const h = setup();
    h.pending = file('1');
    h.guard.request(file('1'));         // the event
    await h.guard.sync();               // and the stream connecting
    await ticks();
    h.answer('discard');
    await ticks();
    h.guard.request(file('1'));         // the event again, late
    await ticks();
    assert.deepEqual(h.log, ['ask', 'opening b.png', 'take 1', 'opened b.png', 'done']);
  },
  async questions_come_one_at_a_time() {
    const h = setup();
    const a = h.guard.ready(), b = h.guard.ready();
    await ticks();
    assert.deepEqual(h.log, ['ask']);
    h.answer('cancel');
    assert.equal(await a, false);
    await ticks();
    assert.deepEqual(h.log, ['ask', 'ask']);
    h.answer('discard');
    assert.equal(await b, true);
  },
  async settling_elsewhere_closes_the_waiting_files_dialog_and_sends_nothing() {
    const h = setup();
    h.guard.request(file('1'));
    await ticks();
    h.guard.settle();                   // answered in another window, or another image was opened
    await ticks();
    assert.deepEqual(h.log, ['ask', 'dismiss']);
    assert.equal(h.dialogUp, false);
  },
  async settling_elsewhere_leaves_the_users_own_open_dialog_alone() {
    const h = setup();
    const own = h.guard.ready();        // the user pressed 打开… here
    await ticks();
    h.guard.request(file('1'));         // a file arrives from outside and queues behind it
    await ticks();
    h.guard.settle();                   // another window cancelled that file
    await ticks();
    assert.ok(h.dialogUp, 'the dialog for 打开… was closed');
    h.answer('cancel');
    assert.equal(await own, false);
    await ticks();
    assert.deepEqual(h.log, ['ask']);   // and no stale question about the settled file
  },
  async a_file_that_arrives_while_the_answer_is_on_its_way_is_asked_about() {
    const h = setup();
    let release;
    h.gate = new Promise((r) => { release = r; });
    h.guard.request(file('1'));
    await ticks();
    h.answer('cancel');
    await ticks();
    h.pending = file('2', 'c.png');
    h.guard.request(file('2', 'c.png')); // before the cancel request has come back
    await ticks();
    release();
    await ticks();
    assert.deepEqual(h.log, ['ask', 'cancel 1', 'done', 'ask']);
    h.answer('discard');
    await ticks();
    assert.deepEqual(h.log.slice(4), ['opening c.png', 'take 2', 'opened b.png', 'done']);
  },
  async a_newer_file_takes_the_place_of_the_one_being_asked_about() {
    const h = setup();
    h.guard.request(file('1'));
    await ticks();
    h.guard.request(file('2', 'c.png'));
    await ticks();
    assert.ok(h.dialogUp);
    h.answer('discard');
    await ticks();
    assert.ok(h.log.includes('take 2') && !h.log.includes('take 1') && !h.log.includes('cancel 1'), h.log.join());
  },
  async a_failed_read_of_the_document_never_counts_as_agreeing() {
    const h = setup();
    h.docFails = true;                  // a window that has just opened and cannot reach the server
    h.pending = file('1');
    h.guard.request(file('1'));
    await ticks();
    assert.deepEqual(h.log, ['failed no answer']);
    h.docFails = false;
    await h.guard.sync();               // the stream reconnects: the file still waits, and is asked about
    await ticks();
    assert.deepEqual(h.log, ['failed no answer', 'ask']);
  },
  async the_users_own_open_goes_by_the_image_shown_when_the_server_does_not_answer() {
    const h = setup();
    h.docFails = true;
    h.shown = h.doc;
    const r = h.guard.ready();
    await ticks();
    assert.deepEqual(h.log, ['ask']);
    h.answer('discard');
    assert.equal(await r, true);
    const k = setup();
    k.docFails = true;                  // no image shown: nothing to lose
    assert.equal(await k.guard.ready(), true);
  },
  async the_settlement_of_an_older_file_leaves_the_newer_one() {
    const h = setup();
    h.guard.request(file('2', 'c.png'), 3);
    await ticks();
    h.guard.settle('1', 2);             // the older file's cancellation, arriving late
    h.guard.settle('1');                // even without a revision it names another file
    await ticks();
    assert.ok(h.dialogUp);
    assert.deepEqual(h.log, ['ask']);
  },
  async a_late_snapshot_does_not_replace_a_newer_file() {
    const h = setup();
    let deliver;
    h.snapshot = () => new Promise((r) => { deliver = () => r({ rev: 1, file: file('1') }); });
    const s = h.guard.sync();           // the stream connects; the answer is slow
    await ticks();
    h.snapshot = null;
    h.rev = 2;
    h.pending = file('2', 'c.png');
    h.guard.request(file('2', 'c.png'), 2);
    await ticks();
    deliver();
    await s;
    await ticks();
    h.answer('discard');
    await ticks();
    assert.ok(h.log.includes('take 2') && !h.log.includes('take 1'), h.log.join());
    assert.equal(h.log.filter((x) => x === 'ask').length, 1);
  },
  async an_answer_that_did_not_reach_the_server_is_asked_again() {
    const h = setup();
    h.pending = file('1');              // the server still holds it
    h.cancelFails = true;
    h.guard.request(file('1'));
    await ticks();
    h.answer('cancel');
    await ticks();
    assert.deepEqual(h.log, ['ask', 'cancel 1', 'failed lost', 'done']);
    await h.timers.shift()();           // looked at again in a while, not at once
    await ticks();
    assert.deepEqual(h.log, ['ask', 'cancel 1', 'failed lost', 'done', 'ask']);
  },
  async an_open_that_keeps_failing_with_nothing_to_lose_does_not_spin() {
    const h = setup({ unsaved: false }); // no dialog: nothing but the failing request stands between two tries
    h.pending = file('1');
    h.takeFails = true;
    h.guard.request(file('1'));
    await ticks(40);
    assert.equal(h.log.filter((x) => x === 'take 1').length, 1);
    assert.equal(h.timers.length, 1);
  },
  async the_same_file_seen_again_while_its_answer_is_on_its_way_is_not_asked_twice() {
    const h = setup();
    let release;
    h.gate = new Promise((r) => { release = r; });
    h.guard.request(file('1'));
    await ticks();
    h.answer('cancel');
    await ticks();
    h.guard.request(file('1'));
    release();
    await ticks();
    assert.deepEqual(h.log, ['ask', 'cancel 1', 'done']);
  },
  async a_file_that_could_not_be_asked_about_is_tried_again_without_a_reconnect() {
    const h = setup();
    h.docFails = true;                  // one request fails; the event stream stays up, so nothing reconnects
    h.pending = file('1');
    h.guard.request(file('1'));
    await ticks();
    assert.deepEqual(h.log, ['failed no answer']);
    assert.equal(h.timers.length, 1);
    await h.timers.shift()();           // still failing: tried again later, and said only once
    await ticks();
    assert.deepEqual(h.log, ['failed no answer']);
    assert.equal(h.timers.length, 1);
    h.docFails = false;
    await h.timers.shift()();
    await ticks();
    assert.deepEqual(h.log, ['failed no answer', 'ask']);
    assert.equal(h.timers.length, 0);
  },
  async a_failed_look_at_what_waits_is_tried_again() {
    const h = setup();
    h.pending = file('1');
    h.snapshot = () => Promise.reject(new Error('down'));
    await h.guard.sync();
    await h.guard.sync();               // a second failure meanwhile does not start a second round of tries
    assert.equal(h.timers.length, 1);
    h.snapshot = null;
    await h.timers.shift()();
    await ticks();
    assert.deepEqual(h.log, ['ask']);
  },
  async reconnecting_to_nothing_waiting_closes_a_stale_question() {
    const h = setup();
    h.guard.request(file('1'));
    await ticks();
    h.pending = null;
    await h.guard.sync();
    await ticks();
    assert.deepEqual(h.log, ['ask', 'dismiss']);
  },
};

await cases[CASE]();
"""

CASES = [
    'agreeing_opens_the_waiting_file',
    'cancelling_tells_the_server_to_forget_it',
    'exporting_first_then_opens',
    'with_nothing_to_lose_it_opens_without_asking',
    'an_answer_the_server_no_longer_takes_changes_nothing_here',
    'the_same_file_seen_twice_is_asked_about_once',
    'questions_come_one_at_a_time',
    'settling_elsewhere_closes_the_waiting_files_dialog_and_sends_nothing',
    'settling_elsewhere_leaves_the_users_own_open_dialog_alone',
    'a_file_that_arrives_while_the_answer_is_on_its_way_is_asked_about',
    'a_newer_file_takes_the_place_of_the_one_being_asked_about',
    'reconnecting_to_nothing_waiting_closes_a_stale_question',
    'a_failed_read_of_the_document_never_counts_as_agreeing',
    'the_users_own_open_goes_by_the_image_shown_when_the_server_does_not_answer',
    'the_settlement_of_an_older_file_leaves_the_newer_one',
    'a_late_snapshot_does_not_replace_a_newer_file',
    'an_answer_that_did_not_reach_the_server_is_asked_again',
    'the_same_file_seen_again_while_its_answer_is_on_its_way_is_not_asked_twice',
    'a_file_that_could_not_be_asked_about_is_tried_again_without_a_reconnect',
    'a_failed_look_at_what_waits_is_tried_again',
    'an_open_that_keeps_failing_with_nothing_to_lose_does_not_spin',
]


@pytest.mark.skipif(shutil.which('node') is None, reason='needs node')
@pytest.mark.parametrize('case', CASES)
def test_replace_guard(case):
    url = pathlib.Path(STATIC, 'openwait.js').as_uri()
    script = HARNESS.replace('MODULE', json.dumps(url)).replace('CASE', json.dumps(case))
    res = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True, encoding='utf-8',
                         timeout=60)
    assert res.returncode == 0, res.stderr[-2000:]

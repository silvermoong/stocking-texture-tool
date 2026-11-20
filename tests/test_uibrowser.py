"""The browser helper without a browser: isolation, bounded screenshots, and reports for a failing page."""
import base64
from concurrent.futures import ThreadPoolExecutor
import contextlib
import http.server
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import warnings

from PIL import Image
import pytest

import uibrowser


@pytest.fixture
def other_tool():
    """Something answering like the tool on a port of its own: (port, the POSTs it received)."""
    posts = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def _answer(self, body):
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._answer({'app': 'stocking-texture', 'pid': 34, 'version': 'x', 'lang': 'zh'})

        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length') or 0))
            posts.append(self.path)
            self._answer({'ok': True})

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield srv.server_address[1], posts
    finally:
        srv.shutdown()
        srv.server_close()


class Gone:
    """A process that has already ended (nothing here may be asked to end a process that is not the test's)."""
    pid = None

    def __init__(self, code):
        self.returncode = code

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode


def test_a_tool_that_is_not_ours_is_neither_taken_for_ours_nor_told_to_stop(other_tool, tmp_path):
    port, posts = other_tool
    server = uibrowser.Server(tmp_path)
    server.port = port
    open(server.log, 'w').close()           # ours never said it was up: another program got the port first
    server.proc = Gone(None)
    assert not server._up()
    server.proc = Gone(1)                   # and ours has ended
    with pytest.raises(RuntimeError):
        server._up()
    server.stop()
    assert posts == []


class Wire:
    """Scripted DevTools connection, with optional noise before answers and queued events just after an answer."""

    def __init__(self, answers):
        self.answers = answers
        self.noise, self.every = 0, 0.0
        self.queue, self.after_reply = [], []
        self.closed = False

    def send(self, text):
        msg = json.loads(text)
        self.queue += [{'method': 'Page.frameNavigated', 'params': {}}] * self.noise
        self.queue.append({'id': msg['id'], 'result': self.answers(msg['method'], msg['params'])})
        self.queue.extend(self.after_reply)
        self.after_reply.clear()

    def recv(self, timeout=None):
        if not self.queue:
            raise TimeoutError
        if self.every:
            time.sleep(self.every)
        return json.dumps(self.queue.pop(0))


@pytest.fixture
def page_on(monkeypatch):
    def make(wire):
        @contextlib.contextmanager
        def connect(url, **options):
            try:
                yield wire
            finally:
                wire.closed = True

        monkeypatch.setitem(sys.modules, 'websockets.sync.client', SimpleNamespace(connect=connect))
        return uibrowser.Page('ws://127.0.0.1/devtools/page/fake', 1280, 720)
    return make


def test_a_command_is_given_up_at_its_deadline_however_many_events_arrive(page_on):
    wire = Wire(lambda method, params: {})
    page = page_on(wire)
    wire.noise, wire.every = 40, 0.01
    t = time.monotonic()
    with pytest.raises(TimeoutError):
        page.send('Page.enable', timeout=0.05)
    assert time.monotonic() - t < 0.3


def test_a_page_that_did_not_load_is_not_taken_for_one_that_did(page_on):
    def answers(method, params):
        if method == 'Page.navigate':
            return {'frameId': 'f', 'errorText': 'net::ERR_ABORTED'}
        return {'result': {'value': True}}  # the document still showing is ready, translated and from this address
    with pytest.raises(RuntimeError, match='ERR_ABORTED'):
        page_on(Wire(answers)).goto('http://127.0.0.1:1/', timeout=1)


def test_nothing_is_sent_once_our_server_has_ended(other_tool, tmp_path):
    # it was up, then crashed, and another tool has its port now: that one must not get our settings
    port, posts = other_tool
    server = uibrowser.Server(tmp_path)
    server.port = port
    for proc in (Gone(1), None):
        server.proc = proc
        with pytest.raises(RuntimeError):
            server.set_lang('en')
        with pytest.raises(RuntimeError):
            server.upload('a.png', b'x')
    assert posts == []


def capture_png(width, height):
    with io.BytesIO() as data:
        Image.new('RGB', (width, height)).save(data, format='PNG')
        return {'data': base64.b64encode(data.getvalue()).decode()}


@pytest.fixture
def shots(monkeypatch, tmp_path):
    monkeypatch.setattr(uibrowser, 'SHOTS', str(tmp_path))
    monkeypatch.setattr(uibrowser, '_shots_used', 0)
    monkeypatch.setattr(uibrowser, '_shot_limit_warned', False)
    return tmp_path


@pytest.mark.parametrize('size', ((1601, 200), (200, 1601)))
def test_a_screenshot_larger_than_1600_pixels_on_either_edge_is_not_written(page_on, shots, size):
    page = page_on(Wire(lambda method, params: capture_png(*size)))
    with pytest.raises(ValueError, match=r'screenshot.*1600'):
        page.screenshot('too-large')
    assert list(shots.iterdir()) == []


def test_the_eight_screenshot_budget_is_shared_across_tabs(page_on, shots):
    requests = []
    png = capture_png(1600, 900)

    def answers(method, params):
        if method == 'Page.captureScreenshot':
            requests.append(method)
            return png
        return {}

    pages = [page_on(Wire(answers)) for _ in range(2)]
    for i, page in enumerate(pages * 4):
        assert Path(page.screenshot(f'shot-{i}')) == shots / f'shot-{i}.png'
    with pytest.warns(RuntimeWarning, match='8 PNGs.*skipped'):
        warnings.simplefilter('error', RuntimeWarning)  # pytest -W error must not skip the test's real assertions
        assert pages[1].screenshot('one-too-many') is None
    assert pages[0].screenshot('another') is None
    assert len(requests) == len(list(shots.glob('*.png'))) == 8
    with Image.open(shots / 'shot-0.png') as image:
        assert image.size == (1600, 900)  # the helper saves the PNG at its actual size


def test_parallel_tabs_cannot_both_claim_the_last_screenshot_slot(page_on, shots):
    entered, finish = threading.Event(), threading.Event()
    png = capture_png(640, 480)

    def answers(method, params):
        if method == 'Page.captureScreenshot':
            entered.set()
            assert finish.wait(3), 'the second tab never completed its attempt'
            return png
        return {}

    fast = page_on(Wire(lambda method, params: png if method == 'Page.captureScreenshot' else {}))
    slow = page_on(Wire(answers))
    for i in range(7):
        fast.screenshot(f'shot-{i}')
    with ThreadPoolExecutor(max_workers=1) as pool:
        last = pool.submit(slow.screenshot, 'last')
        try:
            assert entered.wait(3), 'the first tab never requested the screenshot'
            with pytest.warns(RuntimeWarning, match='8 PNGs.*skipped'):
                assert fast.screenshot('one-too-many') is None
        finally:
            finish.set()
        assert Path(last.result(timeout=3)) == shots / 'last.png'
    assert len(list(shots.glob('*.png'))) == 8


def event(method, **params):
    return {'method': method, 'params': params}


def test_a_checkpoint_reports_all_browser_errors_even_after_the_last_reply(page_on):
    commands = []
    wire = Wire(lambda method, params: commands.append(method) or {})
    page = page_on(wire)
    unreachable = 'http://127.0.0.1:1234/unreachable'
    unavailable = 'http://127.0.0.1:1234/unavailable'
    wire.after_reply += [
        event('Runtime.consoleAPICalled', type='error', args=[{'value': 'bad state'}, {'value': 42}]),
        event('Runtime.consoleAPICalled', type='warning', args=[{'value': 'not an error'}]),
        event('Runtime.exceptionThrown', exceptionDetails={'exception': {'description': 'ReferenceError: missing'}}),
        event('Network.responseReceived', response={'status': 503, 'url': unavailable}),
        event('Network.responseReceived', response={'status': 404, 'url': 'http://127.0.0.1:1234/not-found'}),
        event('Network.requestWillBeSent', requestId='x', request={'url': unreachable}),
        event('Network.loadingFailed', requestId='x', errorText='net::ERR_CONNECTION_REFUSED'),
        event('Network.loadingFailed', requestId='y', canceled=True, errorText='net::ERR_ABORTED'),
    ]
    with pytest.raises(AssertionError) as report:
        page.check_errors()
    text = str(report.value)
    assert 'Network.enable' in commands
    assert 'console.error: bad state 42' in text
    assert 'pageerror: ReferenceError: missing' in text
    assert f'HTTP 503: {unavailable}' in text
    assert f'requestfailed: {unreachable} -> net::ERR_CONNECTION_REFUSED' in text
    assert all(ignored not in text for ignored in ('not an error', '404', 'ERR_ABORTED'))
    assert page.errors == ['ReferenceError: missing']  # existing callers still see the list of JS exceptions
    page.check_errors()  # the previous step's errors were consumed, not reported twice


def test_an_exact_allowance_applies_only_to_the_step_being_checked(page_on):
    wire = Wire(lambda method, params: {})
    page = page_on(wire)
    intentional = event('Runtime.consoleAPICalled', type='error', args=[{'value': 'intentional'}])
    wire.after_reply.append(intentional)
    page.check_errors(allow={'console.error: intentional'})
    page.check_errors()
    wire.after_reply.append(intentional)
    with pytest.raises(AssertionError, match='console.error: intentional'):
        page.check_errors()  # another step must explicitly allow the error again


@pytest.mark.parametrize('body_fails', (False, True))
def test_closing_reports_unchecked_errors_without_hiding_the_test_failure(page_on, body_fails):
    commands = []
    wire = Wire(lambda method, params: commands.append(method) or {})
    page = page_on(wire)
    wire.after_reply.append(event('Runtime.consoleAPICalled', type='error', args=[{'value': 'late error'}]))
    if body_fails:
        with pytest.raises(ValueError, match='test failure') as primary:
            with contextlib.closing(page):
                raise ValueError('test failure')
        assert any('console.error: late error' in note for note in getattr(primary.value, '__notes__', ()))
    else:
        with pytest.raises(AssertionError, match='console.error: late error'):
            page.close()
    assert wire.closed and 'Page.close' in commands
    page.close()  # safe even after a cleanup assertion


def test_closing_reports_events_on_both_sides_of_the_close_reply(page_on):
    def answers(method, params):
        if method == 'Page.close':
            wire.queue.append(event('Runtime.consoleAPICalled', type='error', args=[{'value': 'before close reply'}]))
            wire.after_reply.append(event('Runtime.consoleAPICalled', type='error', args=[{'value': 'after close reply'}]))
        return {}

    wire = Wire(answers)
    page = page_on(wire)
    with pytest.raises(AssertionError) as report:
        page.close()
    assert 'console.error: before close reply' in str(report.value)
    assert 'console.error: after close reply' in str(report.value)
    assert wire.closed


def test_a_missing_browser_is_a_skip_with_a_reason(monkeypatch, tmp_path):
    monkeypatch.setenv('STOCKING_EDGE', str(tmp_path / 'not-installed.exe'))
    with pytest.raises(pytest.skip.Exception, match='needs Microsoft Edge.*STOCKING_EDGE'):
        uibrowser.require()


class Running:
    """A process that ends when killed (or, with dies=False, not even then)."""
    pid = 1
    returncode = None

    def __init__(self, dies=True):
        self.dies = dies

    def poll(self):
        return self.returncode

    def kill(self):
        if self.dies:
            self.returncode = -9

    def wait(self, timeout=None):
        if self.returncode is None:
            raise subprocess.TimeoutExpired('process', timeout)
        return self.returncode


@pytest.mark.parametrize('kind', (uibrowser.Server, uibrowser.Browser))
def test_a_process_is_ended_even_when_taskkill_cannot_run_and_kept_when_it_will_not_go(kind, monkeypatch, tmp_path):
    def no_taskkill(*args, **kw):
        raise OSError('taskkill is not there')
    monkeypatch.setattr(uibrowser.subprocess, 'run', no_taskkill)
    ours = kind(tmp_path)
    ours.proc = proc = Running()
    ours.stop()
    assert proc.returncode is not None and ours.proc is None
    ours.proc = proc = Running(dies=False)
    with pytest.raises(subprocess.TimeoutExpired):
        ours.stop()
    assert ours.proc is proc                # still ours to end: a later stop() tries again

"""The browser test helper itself (uibrowser.py), without a browser: what it must never do to a tool that is not its
own, and that a silent or failing page is reported instead of waited on or taken for a loaded one."""
import http.server
import json
import threading
import time

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
    """A DevTools connection played from a script: answers(method, params) gives each command's result, and `noise`
    events come in before every answer."""

    def __init__(self, answers, noise=0, every=0.0):
        self.answers, self.noise, self.every = answers, noise, every
        self.queue = []

    def send(self, text):
        msg = json.loads(text)
        self.queue += [{'method': 'Page.frameNavigated', 'params': {}}] * self.noise
        self.queue.append({'id': msg['id'], 'result': self.answers(msg['method'], msg['params'])})

    def recv(self, timeout=None):
        time.sleep(self.every)
        return json.dumps(self.queue.pop(0))


def page_on(wire):
    page = object.__new__(uibrowser.Page)
    page.ws, page.errors, page._id = wire, [], 0
    return page


def test_a_command_is_given_up_at_its_deadline_however_many_events_arrive():
    page = page_on(Wire(lambda method, params: {}, noise=40, every=0.01))
    t = time.monotonic()
    with pytest.raises(TimeoutError):
        page.send('Page.enable', timeout=0.05)
    assert time.monotonic() - t < 0.3


def test_a_page_that_did_not_load_is_not_taken_for_one_that_did():
    def answers(method, params):
        if method == 'Page.navigate':
            return {'frameId': 'f', 'errorText': 'net::ERR_ABORTED'}
        return {'result': {'value': True}}  # the document still showing is ready, translated and from this address
    with pytest.raises(RuntimeError, match='ERR_ABORTED'):
        page_on(Wire(answers)).goto('http://127.0.0.1:1/', timeout=1)

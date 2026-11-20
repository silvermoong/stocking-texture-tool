"""The real page in a real browser, for tests of what only shows when it runs (layout, hover colours).

Three parts, each usable on its own:

  Server    the tool started as its own process with --isolated (settings of its own, no session, never the shared
            server), on a free port that is not the tool's, with no models and no network
  synthetic_document()   a picture drawn by this program (two dark bars on grey), opened, painted and given 走向 lines
            through the API, so the 纹理 page can be entered
  Browser / Page   the system's Edge, headless, with a profile of its own, driven over the DevTools protocol

Nothing is installed for this: Edge comes with Windows and the websockets package with uvicorn[standard]. Where
either is missing the tests using require() are skipped. Screenshots go to out/ (ignored by git), or to the folder
STOCKING_UI_SHOTS names; they are never written into a tracked path.
"""
import base64
import contextlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.environ.get('STOCKING_UI_SHOTS') or os.path.join(ROOT, 'out', 'ui-browser')
TOOL_PORT = 8765            # the tool's own port: never used here
_open = urllib.request.build_opener(urllib.request.ProxyHandler({})).open       # this computer only: no proxy


def find_edge():
    p = os.environ.get('STOCKING_EDGE')
    if p:
        return p if os.path.isfile(p) else None
    from stocking.__main__ import find_edge as tool_edge
    return tool_edge()


def require():
    """In a fixture: skip the tests using it where there is no Edge or no websockets package."""
    if find_edge() is None:
        pytest.skip('needs Microsoft Edge (or STOCKING_EDGE pointing at a Chromium-based browser)')
    try:
        import websockets.sync.client  # noqa: F401
    except ImportError:
        pytest.skip('needs the websockets package (installed with uvicorn[standard])')


def _free_port():
    while True:
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        if port != TOOL_PORT:
            return port


def _wait(what, test, timeout, every=0.1):
    end = time.monotonic() + timeout
    while True:
        v = test()
        if v:
            return v
        if time.monotonic() > end:
            raise TimeoutError(f'timed out after {timeout} s waiting for {what}')
        time.sleep(every)


# ------------------------------------------------------------------ the tool, as its own process

class Server:
    """An --isolated server in a folder of its own. Its settings (language, 界面大小) start empty and are thrown away
    with it; the user's are never read or written. No model is found (the home folder is an empty one) and none is
    downloaded, so 点选 and the depth model report themselves unavailable, as on a computer without them."""

    def __init__(self, folder):
        self.folder = str(folder)
        self.port = None
        self.proc = None
        self.log = os.path.join(self.folder, 'server.log')

    @property
    def url(self):
        return f'http://127.0.0.1:{self.port}'

    def start(self, timeout=90):
        self.port = _free_port()
        home = os.path.join(self.folder, 'home')
        os.makedirs(home, exist_ok=True)
        env = dict(os.environ, LOCALAPPDATA=os.path.join(self.folder, 'localappdata'), USERPROFILE=home,
                   HF_HOME=os.path.join(home, 'hf'), HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                   CUDA_VISIBLE_DEVICES='-1', PYTHONUTF8='1', PYTHONPATH=ROOT)
        with open(self.log, 'w', encoding='utf-8') as log:
            self.proc = subprocess.Popen(
                [sys.executable, '-m', 'stocking', '--isolated', '--no-window', '--stay', '--port', str(self.port)],
                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            _wait('the server', self._up, timeout)
        except Exception:
            self.stop()
            raise
        return self

    def _up(self):
        if self.proc.poll() is not None:
            raise RuntimeError(f'the server exited with {self.proc.returncode}:\n{self._log_tail()}')
        try:
            return self.api('/api/ping', timeout=1).get('app') == 'stocking-texture'
        except (OSError, ValueError):
            return False

    def _log_tail(self):
        try:
            with open(self.log, encoding='utf-8', errors='replace') as f:
                return f.read()[-2000:]
        except OSError:
            return ''

    def stop(self):
        if self.proc is None:
            return
        try:
            self.api('/api/shutdown', 'POST', {}, timeout=5)      # the launcher's own way out: its child goes with it
            self.proc.wait(10)
        except Exception:
            pass
        if self.proc.poll() is None:
            if os.name == 'nt':     # a venv's python.exe starts the real one as a child: end the whole tree
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.proc.pid)], capture_output=True)
            else:
                self.proc.kill()
            self.proc.wait(10)
        self.proc = None

    def api(self, path, method='GET', body=None, timeout=30, headers=None, data=None):
        """A request to this server, as the launcher sends them (no Origin); the answer's JSON."""
        h = dict(headers or {})
        if body is not None:
            data = json.dumps(body).encode()
            h['Content-Type'] = 'application/json'
        req = urllib.request.Request(self.url + path, data=data, headers=h, method=method)
        try:
            with _open(req, timeout=timeout) as r:
                text = r.read().decode()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f'{method} {path} -> {e.code} {e.read().decode(errors="replace")[:300]}') from e
        return json.loads(text) if text else None

    def upload(self, name, data):
        """Open a picture from its bytes, as dropping it on the window does."""
        mark = uuid.uuid4().hex
        body = (f'--{mark}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
                f'Content-Type: application/octet-stream\r\n\r\n').encode() + data + f'\r\n--{mark}--\r\n'.encode()
        return self.api('/api/open/upload', 'POST', data=body,
                        headers={'Content-Type': f'multipart/form-data; boundary={mark}'})

    def set_lang(self, lang):
        return self.api('/api/lang', 'POST', {'lang': lang})

    def set_scale(self, percent):
        return self.api('/api/ui-scale', 'POST', {'scale': percent})


# ------------------------------------------------------------------ a picture of our own

def synthetic_png(w=640, h=960):
    """Two dark upright bars on grey, drawn here: no artwork is read. PNG bytes."""
    import cv2
    import numpy as np
    img = np.full((h, w, 3), 160, np.uint8)
    s = w / 1280
    for x0, x1 in ((380, 600), (680, 900)):
        cv2.rectangle(img, (int(x0 * s), int(200 * s)), (int(x1 * s), int(1750 * s)), (34, 30, 30), -1)
    return cv2.imencode('.png', img)[1].tobytes()


def synthetic_document(server, w=640, h=960, timeout=120):
    """Open the synthetic picture, paint its two bars as the two default regions and give each three 走向 lines; wait
    until they are solved. Returns the document's state."""
    st = server.upload('synthetic.png', synthetic_png(w, h))
    doc, s = st['id'], w / 1280

    def pts(*xy):
        return [round(v * s, 1) for p in xy for v in p]

    for cx, region in zip((490, 790), st['regions']):
        rid = region['id']
        server.api(f'/api/doc/{doc}/regions/{rid}/paint', 'POST',
                   {'pts': pts((cx, 240), (cx, 700), (cx, 1200), (cx, 1710)), 'radius': 114 * s, 'erase': False})
        for y in (520, 900, 1280):
            server.api(f'/api/doc/{doc}/strokes', 'POST',
                       {'pts': pts((cx - 100, y), (cx - 50, y + 14), (cx, y + 20), (cx + 50, y + 14), (cx + 100, y)),
                        'hint': rid})

    def solved():
        d = server.api('/api/doc')
        return d if all(r['status'] == 'ok' for r in d['regions']) else None
    return _wait('the regions to be solved', solved, timeout, every=0.3)


# ------------------------------------------------------------------ the browser

class Browser:
    """Edge, headless, with an empty profile of its own under `folder`; the user's Edge and its profile are not
    touched. One device pixel for each CSS pixel, so a screenshot is the size of the window asked for."""

    def __init__(self, folder):
        self.folder = str(folder)
        self.port = None
        self.proc = None

    def start(self, timeout=30):
        profile = os.path.join(self.folder, 'edge-profile')
        os.makedirs(profile, exist_ok=True)
        self.proc = subprocess.Popen(
            [find_edge(), '--headless=new', '--remote-debugging-port=0', f'--user-data-dir={profile}',
             '--no-first-run', '--no-default-browser-check', '--disable-extensions', '--disable-gpu',
             '--force-device-scale-factor=1',
             # a page left by navigating must go at once: kept for the back button, it keeps its event stream open,
             # and the sixth load waits for ever for one of the six connections a browser allows to one address
             '--disable-features=BackForwardCache', 'about:blank'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port_file = os.path.join(profile, 'DevToolsActivePort')     # the browser writes the port it chose here

        def port():
            if self.proc.poll() is not None:
                raise RuntimeError(f'the browser exited with {self.proc.returncode}')
            try:
                with open(port_file, encoding='utf-8') as f:
                    return int(f.readline())
            except (OSError, ValueError):
                return None
        try:
            self.port = _wait('the browser', port, timeout)
            _wait('the browser to answer', lambda: self._ask('/json/version', quiet=True), timeout)
        except Exception:
            self.stop()
            raise
        return self

    def _ask(self, path, method='GET', quiet=False):
        req = urllib.request.Request(f'http://127.0.0.1:{self.port}{path}', method=method)
        try:
            with _open(req, timeout=10) as r:
                return json.loads(r.read().decode())
        except OSError:
            if quiet:
                return None
            raise

    def page(self, width=1280, height=720):
        """A new tab with a window of this size."""
        return Page(self._ask('/json/new?about:blank', 'PUT')['webSocketDebuggerUrl'], width, height)

    def stop(self):
        if self.proc is None:
            return
        if self.proc.poll() is None:
            if os.name == 'nt':     # Edge is a tree of processes
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.proc.pid)], capture_output=True)
            else:
                self.proc.kill()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                pass
        self.proc = None


class Page:
    """One tab, over the DevTools protocol. `errors` collects the exceptions the page's scripts threw."""

    def __init__(self, ws_url, width, height):
        from websockets.sync.client import connect
        self._closing = contextlib.ExitStack()
        self.ws = self._closing.enter_context(connect(ws_url, max_size=None, open_timeout=20, proxy=None))
        self.errors = []
        self._id = 0
        self.send('Page.enable')
        self.send('Runtime.enable')
        self.resize(width, height)

    def send(self, method, timeout=30, **params):
        self._id += 1
        self.ws.send(json.dumps({'id': self._id, 'method': method, 'params': params}))
        end = time.monotonic() + timeout
        while True:
            msg = json.loads(self.ws.recv(timeout=max(0.1, end - time.monotonic())))
            if msg.get('id') == self._id:
                if 'error' in msg:
                    raise RuntimeError(f'{method}: {msg["error"]}')
                return msg.get('result', {})
            if msg.get('method') == 'Runtime.exceptionThrown':
                d = msg['params']['exceptionDetails']
                self.errors.append(d.get('exception', {}).get('description') or d.get('text'))

    def evaluate(self, js):
        """The value of a JavaScript expression in the page (a promise is awaited); it must be JSON."""
        r = self.send('Runtime.evaluate', expression=js, awaitPromise=True, returnByValue=True)
        if 'exceptionDetails' in r:
            d = r['exceptionDetails']
            raise RuntimeError(d.get('exception', {}).get('description') or d.get('text'))
        return r['result'].get('value')

    def wait_for(self, js, timeout=30, what=None):
        return _wait(what or js, lambda: self.evaluate(js), timeout)

    def resize(self, width, height):
        self.send('Emulation.setDeviceMetricsOverride', width=width, height=height, deviceScaleFactor=1, mobile=False)

    def goto(self, url, timeout=30):
        """Load the tool's page and wait until it is translated and its scripts have started."""
        self.send('Page.navigate', url=url)          # answered once the new document has taken the old one's place
        self.wait_for(f'{json.dumps(url)}.startsWith(location.origin) && document.readyState === "complete"'
                      ' && document.documentElement.classList.contains("i18n-done")', timeout, f'{url} to load')

    def _centre(self, selector):
        p = self.evaluate(f'''(() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return null;
            el.scrollIntoView({{ block: 'center', inline: 'nearest' }});
            const r = el.getBoundingClientRect();
            return [r.left + r.width / 2, r.top + r.height / 2];
        }})()''')
        if p is None:
            raise LookupError(f'no element matches {selector}')
        return p

    def hover(self, selector):
        """Put the pointer on the middle of an element, as a mouse would."""
        x, y = self._centre(selector)
        self.send('Input.dispatchMouseEvent', type='mouseMoved', x=x, y=y)
        return x, y

    def click(self, selector):
        x, y = self.hover(selector)
        for kind in ('mousePressed', 'mouseReleased'):
            self.send('Input.dispatchMouseEvent', type=kind, x=x, y=y, button='left', clickCount=1)

    def screenshot(self, name):
        """The window as a PNG in SHOTS (ignored by git), full size. Returns its path."""
        os.makedirs(SHOTS, exist_ok=True)
        path = os.path.join(SHOTS, name if name.endswith('.png') else name + '.png')
        with open(path, 'wb') as f:
            f.write(base64.b64decode(self.send('Page.captureScreenshot', format='png')['data']))
        return path

    def close(self):
        try:
            self.send('Page.close', timeout=5)
        except Exception:
            pass
        self._closing.close()


# ------------------------------------------------------------------ what a test asks of the page

def out_of_reach(page, scope):
    """The controls inside `scope` (a selector) that are shown but that the pointer cannot get to: partly or wholly
    outside the window, or with something else on top of their middle. A list of descriptions, empty when all can
    be reached."""
    return page.evaluate(f'''(() => {{
        const vw = innerWidth, vh = innerHeight, out = [];
        const scope = document.querySelector({json.dumps(scope)});
        for (const el of scope.querySelectorAll('button, select, input, a[href]')) {{
            if (!el.checkVisibility({{ visibilityProperty: true }})) continue;
            const r = el.getBoundingClientRect();
            if (!r.width || !r.height) continue;
            const name = el.id ? '#' + el.id : (el.getAttribute('aria-label') || el.textContent.trim());
            const at = `${{Math.round(r.left)}}..${{Math.round(r.right)}} x ${{Math.round(r.top)}}..${{Math.round(r.bottom)}}`;
            if (r.left < -0.5 || r.top < -0.5 || r.right > vw + 0.5 || r.bottom > vh + 0.5) {{
                out.push(`${{name}} is outside the ${{vw}}x${{vh}} window (${{at}})`);
                continue;
            }}
            const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
            if (!top || !(el === top || el.contains(top))) out.push(`${{name}} is covered (${{at}})`);
        }}
        return out;
    }})()''')


def text_contrast(page, selector):
    """The WCAG 2 contrast ratio of an element's text against the fill behind it, as the element is drawn now (so
    under the pointer after Page.hover). Returns {'ratio', 'text', 'fill'}."""
    return page.evaluate(f'''(() => {{
        const rgba = (s) => {{
            const m = s.match(/^rgba?\\(\\s*([\\d.]+)[,\\s]+([\\d.]+)[,\\s]+([\\d.]+)(?:\\s*[,\\/]\\s*([\\d.]+))?\\s*\\)$/);
            if (!m) throw new Error('cannot read the colour ' + s);
            return [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]];
        }};
        const over = (f, b) => [0, 1, 2].map((i) => f[i] * f[3] + b[i] * (1 - f[3])).concat(1);
        const el = document.querySelector({json.dumps(selector)});
        const fills = [];
        for (let e = el; e; e = e.parentElement) fills.push(rgba(getComputedStyle(e).backgroundColor));
        let fill = [255, 255, 255, 1];                      // the browser's own white, under everything
        for (const f of fills.reverse()) fill = over(f, fill);
        const text = over(rgba(getComputedStyle(el).color), fill);
        const lum = (c) => {{
            const f = (v) => {{ v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }};
            return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
        }};
        const a = lum(text), b = lum(fill);
        const hex = (c) => '#' + c.slice(0, 3).map((v) => Math.round(v).toString(16).padStart(2, '0')).join('');
        return {{ ratio: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05), text: hex(text), fill: hex(fill) }};
    }})()''')

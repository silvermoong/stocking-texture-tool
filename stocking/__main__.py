"""Start the tool: reuse a running server or start one, then open the UI as an Edge app window.

    pythonw -m stocking [file] [--port N] [--no-window] [--stay] [--isolated]

A running server is reused only if it runs the same code; an older one is asked to save its session and stop (or,
if it predates sessions, has its document pulled out over HTTP and is terminated), and the new server takes over
its port, so open windows reconnect and reload. The new server restores the last session unless a file is given.
Without --stay the server exits about 20 s after the last window closes; the session is saved as edits happen.
--isolated runs a separate server that neither reuses nor registers as the shared one, and has no session and
settings of its own (development and tests).
"""
import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

from . import settings
from .i18n import tr
from .version import code_version

DEFAULT_PORT = 8765
RUNFILE = os.path.join(settings.DIR, 'server.json')
TITLE = '丝袜纹理工具'
KEEP = 20                   # s without a window before exiting


def _log_to_file():
    """pythonw has no console; send stdout/stderr to a log so uvicorn and tracebacks have somewhere to go."""
    if sys.stdout is None or sys.stderr is None:
        os.makedirs(settings.DIR, exist_ok=True)
        f = open(os.path.join(settings.DIR, 'server.log'), 'a', encoding='utf-8', buffering=1)
        sys.stdout = sys.stderr = f


def _alert(msg):
    print(msg, file=sys.stderr)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, tr(TITLE), 0x10)
    except Exception:
        pass


def _request(port, path, body=None, timeout=1.0):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', data=data,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _ping(port):
    try:
        info = _request(port, '/api/ping')
        return info if info.get('app') == 'stocking-texture' else None
    except Exception:
        return None


def _alive(port):
    return _ping(port) is not None


def _retire(port, info, wait=15):
    """Stop a server that runs older code without losing its document."""
    try:
        _request(port, '/api/shutdown', {}, timeout=10)
        graceful = True
    except urllib.error.HTTPError:
        graceful = False            # predates sessions: no /api/shutdown
    except Exception:
        graceful = False
    if not graceful:
        from . import session
        try:
            session.rescue(port)
        except Exception as e:
            print(f'could not rescue the document from the old server: {e}', file=sys.stderr)
    end = time.monotonic() + wait
    while time.monotonic() < end:
        if not _alive(port) and _port_free(port):
            return True
        if not graceful or time.monotonic() > end - wait / 2:
            try:
                os.kill(int(info['pid']), signal.SIGTERM)
            except (OSError, KeyError, ValueError):
                pass
        time.sleep(0.25)
    return _port_free(port)


def _port_free(port):
    with socket.socket() as s:
        try:
            s.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def _any_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def find_edge():
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                p = winreg.QueryValue(hive, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe')
                if p and os.path.isfile(p.strip('"')):
                    return p.strip('"')
            except OSError:
                pass
    except ImportError:
        pass
    for base in (os.environ.get('ProgramFiles(x86)'), os.environ.get('ProgramFiles'), os.environ.get('LOCALAPPDATA')):
        if base:
            p = os.path.join(base, 'Microsoft', 'Edge', 'Application', 'msedge.exe')
            if os.path.isfile(p):
                return p
    return None


def open_window(url):
    edge = find_edge()
    if edge:
        subprocess.Popen([edge, f'--app={url}', '--window-size=1680,1050'])
    else:
        webbrowser.open(url)


def _read_runfile():
    try:
        with open(RUNFILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def main():
    ap = argparse.ArgumentParser(prog='stocking')
    ap.add_argument('file', nargs='?')
    ap.add_argument('--port', type=int)
    ap.add_argument('--no-window', action='store_true')
    ap.add_argument('--stay', action='store_true', help='keep running after the window closes')
    ap.add_argument('--isolated', action='store_true', help='separate server: no reuse, no runfile, no session')
    args = ap.parse_args()
    _log_to_file()
    if args.isolated:
        settings.isolate()
    path = os.path.abspath(args.file) if args.file else None

    taken_over = None
    if not args.isolated:
        port = _read_runfile().get('port')
        info = _ping(port) if port else None
        if info and info.get('version') == code_version():
            if path:
                try:
                    _request(port, '/api/open/path', {'path': path}, timeout=60)
                except Exception as e:
                    _alert(tr('打不开 {name}：{error}', name=path, error=e))
            if not args.no_window:
                open_window(f'http://127.0.0.1:{port}/')
            return
        if info:
            print(f'server on port {port} runs older code; replacing it', flush=True)
            if _retire(port, info):
                taken_over = port
            else:
                _alert(tr('旧版的工具没有退出，请在任务管理器里结束 pythonw.exe 后再试'))
                return

    import uvicorn
    from . import server, session

    port = args.port or taken_over or (DEFAULT_PORT if _port_free(DEFAULT_PORT) else _any_port())
    url = f'http://127.0.0.1:{port}/'
    srv = uvicorn.Server(uvicorn.Config(server.app, host='127.0.0.1', port=port, log_level='warning',
                                        timeout_graceful_shutdown=2))
    server.request_exit = lambda: setattr(srv, 'should_exit', True)
    if not args.isolated:
        server.sessions.enable(session.DIR)

    def after_start():
        while not srv.started:
            if srv.should_exit:
                return
            time.sleep(0.05)
        if not args.isolated:
            os.makedirs(settings.DIR, exist_ok=True)
            with open(RUNFILE, 'w', encoding='utf-8') as f:
                json.dump({'port': port, 'pid': os.getpid()}, f)
        print(f'{TITLE}: {url}', flush=True)
        if path:
            if not args.no_window:
                open_window(url)
            try:
                server.open_path(path)
            except Exception as e:
                _alert(tr('打不开 {name}：{error}', name=path, error=e))
        else:
            try:
                doc = server.sessions.restore()
                if doc is not None:
                    print(f'restored session: {doc.name}', flush=True)
            except Exception as e:
                print(f'could not restore the session: {e}', flush=True)
            if not args.no_window:
                open_window(url)
        started = time.monotonic()
        while not args.stay:
            time.sleep(2)
            bus = server.bus
            idle = not bus.queues and time.monotonic() - bus.last_seen > KEEP
            never = not bus.ever_connected and time.monotonic() - started > 180
            if (bus.ever_connected and idle) or never:
                srv.should_exit = True
                return

    threading.Thread(target=after_start, daemon=True).start()
    try:
        srv.run()
    finally:
        server.sessions.save_now()
        if _read_runfile().get('pid') == os.getpid():
            try:
                os.remove(RUNFILE)
            except OSError:
                pass


if __name__ == '__main__':
    main()
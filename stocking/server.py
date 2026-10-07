"""HTTP API and static UI for the stocking texture tool. One process, one open document at a time."""
import asyncio
import contextlib
import json
import os
import subprocess
import threading
import time

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import depth, export, i18n, look, sam, session, settings
from .i18n import tr
from .document import IMAGE_EXTS, PSD_EXTS, Document
from .version import code_version

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
NO_STORE = {'Cache-Control': 'no-store'}
VERSION = code_version()


class Bus:
    """Fan-out of server events to every connected UI (server-sent events)."""

    def __init__(self):
        self.queues = set()
        self.loop = None
        self.last_seen = time.monotonic()
        self.ever_connected = False

    def publish(self, ev):
        loop = self.loop
        if loop is None:
            return
        for q in list(self.queues):
            loop.call_soon_threadsafe(q.put_nowait, ev)

    def close_streams(self):
        """End every open event stream (the browsers reconnect on their own), so the server can stop at once."""
        self.publish(None)


@contextlib.asynccontextmanager
async def _lifespan(app):
    bus.loop = asyncio.get_running_loop()
    sam.service.on_change = lambda: bus.publish({'type': 'sam'})
    depth.service.on_change = lambda: bus.publish({'type': 'depth'})
    sam.service.start()
    yield


bus = Bus()
app = FastAPI(title='丝袜纹理工具', lifespan=_lifespan)
app.mount('/static', StaticFiles(directory=STATIC), name='static')

_doc = None
_doc_lock = threading.Lock()
_dialog_lock = threading.Lock()
request_exit = None             # set by the launcher: stops the server


# ------------------------------------------------------------------ session (autosave and restore)

class _Session:
    def __init__(self):
        self.dir = None
        self.saved = None           # (doc id, edits) last written
        self.lock = threading.Lock()

    def enable(self, d):
        self.dir = d
        threading.Thread(target=self._loop, name='autosave', daemon=True).start()

    def save_now(self):
        d = _doc
        if self.dir is None or d is None:
            return
        with self.lock:
            key = (d.id, d.edits)
            if key == self.saved:
                return
            try:
                edits = session.save(d, self.dir)
                self.saved = (d.id, edits)
            except Exception as e:
                print(f'autosave failed: {e}', flush=True)

    def _loop(self):
        while True:
            time.sleep(1.0)
            self.save_now()

    def restore(self):
        if self.dir is None:
            return None
        doc = session.load(self.dir)
        if doc is not None:
            set_document(doc)
            self.saved = (doc.id, doc.edits)
        return doc


sessions = _Session()


@app.middleware('http')
async def _no_cache_ui(request: Request, call_next):
    resp = await call_next(request)
    if request.url.path == '/' or request.url.path.startswith('/static/'):
        resp.headers['Cache-Control'] = 'no-cache'
    return resp


@app.exception_handler(KeyError)
async def _not_found(request, exc):
    return JSONResponse({'detail': tr('找不到这个对象，可能已被删除；按 F5 刷新一下再试')}, status_code=404)


@app.exception_handler(ValueError)
async def _bad_value(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=400)


def set_document(doc):
    global _doc
    with _doc_lock:
        old, _doc = _doc, doc
    if old is not None:
        old.close()
        if sam.service.status == 'ready':
            sam.service.forget(old)
    doc.on_event = bus.publish
    if doc.path:
        settings.update(last_dir=os.path.dirname(doc.path))
    sam.service.embed_async(doc)
    # the depth model finds the walls (one stretch of stocking in front of another) the courses must not cross
    doc._depth_started = True
    depth.service.disparity_async(doc)
    bus.publish({'type': 'opened', 'doc': doc.id})
    return doc


def state_of(doc):
    st = doc.state()
    st['export_folder'] = export_folder(doc)
    svc = sam.service
    if svc.status == 'unavailable':
        st['sam'] = {'state': 'error', 'error': svc.error}
    elif svc.status in ('idle', 'loading'):
        st['sam'] = {'state': 'loading', 'error': None}
    st['sam']['device'] = svc.device_name
    return st


def open_path(path):
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise ValueError(tr('文件不存在：{path}', path=path))
    bus.publish({'type': 'opening', 'name': os.path.basename(path)})
    try:
        return set_document(Document.open(path))
    except Exception as e:
        bus.publish({'type': 'open-failed', 'name': os.path.basename(path), 'error': str(e)})
        if isinstance(e, ValueError):
            raise
        raise ValueError(tr('打不开 {name}：{error}', name=os.path.basename(path), error=e)) from e


def doc_for(doc_id):
    d = _doc
    if d is None or d.id != doc_id:
        raise HTTPException(409, tr('这个文件已经关闭，请重新打开'))
    return d


@app.get('/')
def index():
    """The page, in the user's language: static/i18n.js translates it from the lang attribute."""
    with open(os.path.join(STATIC, 'index.html'), encoding='utf-8') as f:
        html = f.read()
    if i18n.lang() == 'en':
        html = html.replace('<html lang="zh-CN">', '<html lang="en">', 1)
    return Response(html, media_type='text/html; charset=utf-8')


class LangIn(BaseModel):
    lang: str | None = None             # 'zh', 'en', or None to follow Windows


@app.get('/api/lang')
def get_lang():
    return {'lang': i18n.lang(), 'chosen': i18n.chosen(), 'system': i18n.system_lang()}


@app.post('/api/lang')
def set_lang(body: LangIn):
    """The 中 / EN switch; the page reloads to show it."""
    i18n.set_lang(body.lang)
    return get_lang()


@app.get('/api/ping')
def ping():
    return {'app': 'stocking-texture', 'pid': os.getpid(), 'version': VERSION, 'lang': i18n.lang()}


@app.post('/api/shutdown')
def shutdown():
    """Save the session and stop; a launcher with newer code calls this before starting its own server."""
    sessions.save_now()
    bus.close_streams()
    if request_exit is not None:
        threading.Timer(0.3, request_exit).start()
    return {'ok': True}


@app.get('/api/doc')
def current():
    d = _doc
    return state_of(d) if d is not None else None


# ------------------------------------------------------------------ opening files

def _ask_open_path():
    import tkinter as tk
    from tkinter import filedialog
    exts = ' '.join(f'*{e}' for e in PSD_EXTS + IMAGE_EXTS)
    with _dialog_lock:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        try:
            p = filedialog.askopenfilename(parent=root, title=tr('打开图片或 PSD'), initialdir=settings.get('last_dir'),
                                           filetypes=[(tr('图片或 PSD'), exts), (tr('所有文件'), '*.*')])
        finally:
            root.destroy()
    return p or None


@app.post('/api/open/dialog')
def open_dialog():
    p = _ask_open_path()
    if not p:
        return {'cancelled': True}
    return state_of(open_path(p))


class PathIn(BaseModel):
    path: str


@app.post('/api/open/path')
def open_by_path(body: PathIn):
    return state_of(open_path(body.path))


@app.post('/api/open/upload')
def open_upload(file: UploadFile = File(...)):
    data = file.file.read()
    try:
        doc = Document.open(data=data, filename=file.filename)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(tr('打不开 {name}：{error}', name=file.filename, error=e)) from e
    return state_of(set_document(doc))


# ------------------------------------------------------------------ document data

@app.get('/api/doc/{doc_id}/art')
def art(doc_id: str):
    return Response(doc_for(doc_id).art_png(), media_type='image/png', headers=NO_STORE)


@app.get('/api/doc/{doc_id}/regions/{rid}/mask')
def mask(doc_id: str, rid: int):
    return Response(doc_for(doc_id).mask_png(rid), media_type='image/png', headers=NO_STORE)


@app.get('/api/doc/{doc_id}/regions/{rid}/courses')
def courses(doc_id: str, rid: int):
    return Response(json.dumps(doc_for(doc_id).courses(rid), separators=(',', ':')),
                    media_type='application/json', headers=NO_STORE)


# ------------------------------------------------------------------ edits

class NameIn(BaseModel):
    name: str


class PaintIn(BaseModel):
    pts: list[float]
    radius: float
    erase: bool = False


class StrokeIn(BaseModel):
    pts: list[float]
    hint: int | None = None


def _clean_name(name):
    name = name.strip()
    if not name:
        raise ValueError(tr('部位名不能为空'))
    return name[:40]


@app.post('/api/doc/{doc_id}/regions')
def add_region(doc_id: str, body: NameIn):
    d = doc_for(doc_id)
    rid = d.add_region(_clean_name(body.name))
    return dict(state_of(d), created=rid)


@app.patch('/api/doc/{doc_id}/regions/{rid}')
def rename_region(doc_id: str, rid: int, body: NameIn):
    d = doc_for(doc_id)
    d.rename_region(rid, _clean_name(body.name))
    return state_of(d)


@app.delete('/api/doc/{doc_id}/regions/{rid}')
def delete_region(doc_id: str, rid: int):
    d = doc_for(doc_id)
    d.delete_region(rid)
    return state_of(d)


@app.post('/api/doc/{doc_id}/regions/{rid}/paint')
def paint(doc_id: str, rid: int, body: PaintIn):
    d = doc_for(doc_id)
    d.paint(rid, body.pts, body.radius, body.erase)
    return state_of(d)


@app.post('/api/doc/{doc_id}/regions/{rid}/clear')
def clear(doc_id: str, rid: int):
    d = doc_for(doc_id)
    d.clear_region(rid)
    return state_of(d)


@app.post('/api/doc/{doc_id}/strokes')
def add_stroke(doc_id: str, body: StrokeIn):
    d = doc_for(doc_id)
    sid = d.add_stroke(body.pts, body.hint)
    return dict(state_of(d), created=sid)


@app.delete('/api/doc/{doc_id}/strokes/{sid}')
def delete_stroke(doc_id: str, sid: int):
    d = doc_for(doc_id)
    d.delete_stroke(sid)
    return state_of(d)


class DividerIn(BaseModel):
    pts: list[float]


class PointIn(BaseModel):
    x: float
    y: float
    tol: float = 8.0


@app.post('/api/doc/{doc_id}/dividers')
def add_divider(doc_id: str, body: DividerIn):
    d = doc_for(doc_id)
    did = d.add_divider(body.pts)
    return dict(state_of(d), created=did)


@app.post('/api/doc/{doc_id}/walls/remove')
def remove_wall(doc_id: str, body: PointIn):
    d = doc_for(doc_id)
    kind = d.remove_wall_at(body.x, body.y, max(1.0, min(body.tol, 60.0)))
    return dict(state_of(d), removed=kind)


@app.post('/api/doc/{doc_id}/undo')
def undo(doc_id: str):
    d = doc_for(doc_id)
    d.undo()
    return state_of(d)


@app.post('/api/doc/{doc_id}/redo')
def redo(doc_id: str):
    d = doc_for(doc_id)
    d.redo()
    return state_of(d)


# ------------------------------------------------------------------ click to segment, coverage

class ClickIn(BaseModel):
    x: float
    y: float
    subtract: bool = False


class CycleIn(BaseModel):
    step: int = 1


@app.post('/api/doc/{doc_id}/regions/{rid}/segment')
def segment(doc_id: str, rid: int, body: ClickIn):
    d = doc_for(doc_id)
    d.region(rid)
    if not (0 <= body.x < d.w and 0 <= body.y < d.h):
        raise ValueError(tr('点在画面外面了'))
    try:
        masks, _, _ = sam.service.candidates(d, body.x, body.y)
    except RuntimeError as e:
        raise ValueError(str(e)) from e
    # the smallest of SAM's three sizes by default: the larger ones tend to take in hair, the other leg or a shoe
    # lying against the part; the user steps up with the 小/中/大 chooser or Tab
    d.segment_click(rid, body.x, body.y, body.subtract, masks, 0)
    return state_of(d)


@app.post('/api/doc/{doc_id}/segment/cycle')
def segment_cycle(doc_id: str, body: CycleIn):
    d = doc_for(doc_id)
    d.cycle_segment(body.step)
    return state_of(d)


class SelectIn(BaseModel):
    k: int


@app.post('/api/doc/{doc_id}/segment/select')
def segment_select(doc_id: str, body: SelectIn):
    d = doc_for(doc_id)
    d.select_segment(body.k)
    return state_of(d)


@app.get('/api/doc/{doc_id}/segment/outlines')
def segment_outlines(doc_id: str):
    return Response(json.dumps(doc_for(doc_id).segment_outlines(), separators=(',', ':')),
                    media_type='application/json', headers=NO_STORE)


class MergeIn(BaseModel):
    into: int


class SplitIn(BaseModel):
    pts: list[float] | None = None      # the cut line, flat x, y in image px; none = split automatically
    snap: float = 0                     # snap the line onto the line art within this many image px; 0 = as drawn


@app.post('/api/doc/{doc_id}/regions/{rid}/split')
def split_region(doc_id: str, rid: int, body: SplitIn | None = None):
    d = doc_for(doc_id)
    line = None
    if body is not None and body.pts:
        if len(body.pts) < 4 or len(body.pts) % 2:
            raise ValueError(tr('切线至少要两个点'))
        line = [body.pts[i:i + 2] for i in range(0, len(body.pts), 2)]
    a, b = d.split_region(rid, line, body.snap if body is not None else 0)
    return dict(state_of(d), split=[a, b])


@app.post('/api/doc/{doc_id}/regions/{rid}/merge')
def merge_region(doc_id: str, rid: int, body: MergeIn):
    d = doc_for(doc_id)
    d.merge_region(rid, body.into)
    return state_of(d)


@app.get('/api/doc/{doc_id}/regions/{rid}/neighbours')
def neighbours(doc_id: str, rid: int):
    return doc_for(doc_id).neighbours(rid)


@app.post('/api/doc/{doc_id}/regions/{rid}/mirror')
def mirror_region(doc_id: str, rid: int, body: MergeIn):
    d = doc_for(doc_id)
    made, replaced, rms = d.mirror_strokes(rid, body.into)
    return dict(state_of(d), mirrored={'made': made, 'replaced': replaced, 'fit': round(rms, 1)})


# ------------------------------------------------------------------ look and previews

_scene = (None, None)               # (render key, Scene) of the open document's current state
_scene_lock = threading.Lock()
CROP_MAX = 1024                     # px per side of a live 100% crop; bigger panes would lag behind the sliders


def scene_for(d):
    global _scene
    key = d.render_key()
    with _scene_lock:
        if _scene[0] != key:
            _scene = (key, look.scene_from_doc(d, disparity=lambda: getattr(d, 'disparity', None)))
        return _scene[1]


def _base_look(d):
    """The document's saved look; before any is saved, a PSD with a painted 亮点 layer places sparkles by it."""
    if d.look is not None:
        return dict(d.look)
    if d.sparkle is not None:
        return {'sparkle_depth': 0.0, 'sparkle_bright': 0.0, 'sparkle_painted': 100.0}
    return {}


def _params(request: Request, d):
    """Look settings from the query string, falling back to the document's saved ones."""
    base = _base_look(d)
    for k in look.DEFAULTS:
        v = request.query_params.get(k)
        if v is not None:
            base[k] = v
    return look.clean_params(base)


def _png(img, extra=None):
    ok, buf = cv2.imencode('.png', img, [cv2.IMWRITE_PNG_COMPRESSION, 1])
    headers = dict(NO_STORE)
    if extra is not None:
        headers['X-Look'] = json.dumps(extra)           # ascii-escaped, safe in a header
    return Response(buf.tobytes(), media_type='image/png', headers=headers)


def _want_depth(d, q):
    """Start estimating depth once a setting needs it (按深度 sparkles), if opening the image has not already."""
    needs = q['style'] in look.SPARKLE_STYLES and q['sparkle_depth'] > 0
    if needs and getattr(d, 'disparity', None) is None and not getattr(d, '_depth_started', False):
        d._depth_started = True
        depth.service.disparity_async(d)


def check_maps(d, s, q):
    """The three kinds of missing texture (see Scene.check), plus the painted area they are measured against.
    nostroke: painted, but the region has no 走向线 (or its solve failed), or a detached piece of it has none;
    regions still being solved do not count, they are on their way."""
    faded, excluded = s.check(q)
    rmap = d.region_map()
    painted = rmap > 0
    missing = [i for i, r in enumerate(d.state()['regions'], 1) if r['status'] in ('nostroke', 'error')]
    nostroke = np.isin(rmap, missing) if missing else np.zeros_like(painted)
    nostroke |= d.unguided_map()
    return faded, excluded, nostroke, painted


def look_info(d, q):
    s = scene_for(d)
    q = s.resolve(q)
    g = look.geometry(q['density'], d.w, d.h)
    faded, excluded, nostroke, painted = check_maps(d, s, q)
    n = max(int(painted.sum()), 1)
    st = d.state()
    untextured = [r['name'] for r in st['regions'] if r['status'] in ('nostroke', 'error')]
    untextured += [tr('{name}分开的一块', name=r['name']) for r in st['regions'] if r['status'] == 'ok' and r['unguided']]
    solving = [r['name'] for r in st['regions'] if r['status'] in ('pending', 'solving')]
    dstate = ('ready' if getattr(d, 'disparity', None) is not None else
              'error' if depth.service.status == 'unavailable' or getattr(d, 'depth_error', None) else
              'working' if getattr(d, '_depth_started', False) else 'idle')
    return dict(g, params=q, strength_suggested=s.suggested_strength(), densest=s.densest(),
                untextured=untextured, solving=solving,
                check={'faded': faded.sum() / n, 'excluded': excluded.sum() / n, 'nostroke': nostroke.sum() / n},
                textured=int((s.R > 0).sum()), has_sparkle_layer=d.sparkle is not None, depth=dstate,
                depth_error=depth.service.error or getattr(d, 'depth_error', None))


@app.get('/api/doc/{doc_id}/look')
def get_look(doc_id: str, request: Request):
    d = doc_for(doc_id)
    q = _params(request, d)
    _want_depth(d, q)
    return look_info(d, q)


@app.put('/api/doc/{doc_id}/look')
def put_look(doc_id: str, body: dict):
    d = doc_for(doc_id)
    q = look.clean_params(body)
    d.set_look(q)
    _want_depth(d, q)
    return look_info(d, q)


@app.get('/api/doc/{doc_id}/render/crop')
def render_crop(doc_id: str, request: Request, x0: int, y0: int, w: int, h: int):
    d = doc_for(doc_id)
    q = _params(request, d)
    _want_depth(d, q)
    w, h = min(max(w, 1), CROP_MAX), min(max(h, 1), CROP_MAX)
    x0 = int(np.clip(x0, 0, max(d.w - w, 0)))
    y0 = int(np.clip(y0, 0, max(d.h - h, 0)))
    t = time.perf_counter()
    out, info = scene_for(d).render(q, (x0, y0, x0 + w, y0 + h))
    return _png(out, dict(x0=x0, y0=y0, w=out.shape[1], h=out.shape[0], ms=round(1000 * (time.perf_counter() - t)),
                          sparkles_ready=info['sparkles_ready']))


@app.get('/api/doc/{doc_id}/render/fit')
def render_fit(doc_id: str, request: Request, w: int, h: int):
    """The whole image, rendered at full size and area-averaged down to w x h (how a viewer shows it zoomed out)."""
    d = doc_for(doc_id)
    q = _params(request, d)
    _want_depth(d, q)
    t = time.perf_counter()
    out, info = scene_for(d).render(q)
    w, h = int(np.clip(w, 16, d.w)), int(np.clip(h, 16, d.h))
    small = cv2.resize(out, (w, h), interpolation=cv2.INTER_AREA)
    return _png(small, dict(ms=round(1000 * (time.perf_counter() - t)), sparkles_ready=info['sparkles_ready']))


CHECK_COLOURS = (                       # BGR, drawn in this order (later wins where they meet)
    (2, (40, 190, 255)),                # nostroke: amber
    (1, (255, 150, 70)),                # excluded: blue
    (0, (60, 50, 255)),                 # faded: red
)


@app.get('/api/doc/{doc_id}/render/check')
def render_check(doc_id: str, request: Request, w: int, h: int, x0: int | None = None, y0: int | None = None):
    """Where texture is missing or weak (red: faded, blue: excluded by colour, amber: no 走向线), as an overlay:
    the whole image area-averaged to w x h, or with x0, y0 the w x h crop at full resolution (the zoomed preview)."""
    d = doc_for(doc_id)
    q = _params(request, d)
    maps = [m.astype(np.float32) for m in check_maps(d, scene_for(d), q)[:3]]
    if x0 is not None and y0 is not None:
        w, h = min(max(w, 1), CROP_MAX), min(max(h, 1), CROP_MAX)
        x0 = int(np.clip(x0, 0, max(d.w - w, 0)))
        y0 = int(np.clip(y0, 0, max(d.h - h, 0)))
        maps = [m[y0:y0 + h, x0:x0 + w] for m in maps]
        h, w = maps[0].shape
    else:
        w, h = int(np.clip(w, 16, d.w)), int(np.clip(h, 16, d.h))
        maps = [cv2.resize(m, (w, h), interpolation=cv2.INTER_AREA) for m in maps]
    rgba = np.zeros((h, w, 4), np.float32)
    for k, colour in CHECK_COLOURS:
        a = np.clip(maps[k] * 1.3, 0, 1) * 0.85
        rgba[..., :3] = rgba[..., :3] * (1 - a[..., None]) + np.array(colour, np.float32) * a[..., None]
        rgba[..., 3] = rgba[..., 3] * (1 - a) + a
    rgb = rgba[..., :3] / np.maximum(rgba[..., 3:], 1e-6)
    return _png(np.dstack([rgb, rgba[..., 3:] * 255]).clip(0, 255).astype(np.uint8))


@app.get('/api/doc/{doc_id}/coverage')
def coverage_png(doc_id: str):
    return Response(doc_for(doc_id).coverage_png(), media_type='image/png', headers=NO_STORE)


@app.get('/api/doc/{doc_id}/coverage/stats')
def coverage_stats(doc_id: str):
    _, _, stats, v = doc_for(doc_id).coverage()
    return {'coverage_v': v, 'regions': stats}


class OnIn(BaseModel):
    on: bool


@app.put('/api/doc/{doc_id}/coverage/exclude')
def set_color_exclude(doc_id: str, body: OnIn):
    d = doc_for(doc_id)
    d.set_color_exclude(body.on)
    return state_of(d)


# ------------------------------------------------------------------ export

_export_lock = threading.Lock()
EXPORT_WAIT = 180                   # s: longest an export waits for solves and the depth model


def _ask_folder(initial):
    import tkinter as tk
    from tkinter import filedialog
    with _dialog_lock:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        try:
            p = filedialog.askdirectory(parent=root, title=tr('选择导出到哪个文件夹'), initialdir=initial, mustexist=True)
        finally:
            root.destroy()
    return os.path.normpath(p) if p else None


def export_folder(d):
    """Where the files go: next to the source; for a file dragged in (no known location), the folder chosen for it."""
    return os.path.dirname(d.path) if d.path else getattr(d, 'export_dir', None)


@app.post('/api/doc/{doc_id}/export/folder')
def choose_export_folder(doc_id: str):
    """Ask where a dragged-in file's exports go; remembered for this document."""
    d = doc_for(doc_id)
    p = _ask_folder(export_folder(d) or settings.get('export_dir') or settings.get('last_dir'))
    if not p:
        return {'cancelled': True}
    d.export_dir = p
    settings.update(export_dir=p)
    return state_of(d)


class ExportIn(BaseModel):
    kind: str = 'png'                   # export.KINDS: 成品图, 仅丝袜, 丝袜引导.psd
    params: dict | None = None          # the look being shown; None = the document's saved look


@app.post('/api/doc/{doc_id}/export')
def export_doc(doc_id: str, body: ExportIn):
    """Write the one file asked for. The pictures wait until every region is solved (and the depth model is done,
    if the look needs it); the guides PSD holds only what the user drew, so it goes at once."""
    d = doc_for(doc_id)
    if body.kind not in export.KINDS:
        raise ValueError(tr('不认识的导出内容'))
    folder = export_folder(d)
    if not folder:
        raise ValueError(tr('先选择导出到哪个文件夹'))
    notes = []
    with _export_lock:
        if body.kind == 'guides':
            res = export.export(d, None, None, folder, 'guides')
            d.mark_guides_saved()
        else:
            if not any(r['strokes'] > 0 and r['status'] != 'empty' for r in d.state()['regions']):
                raise ValueError(tr('还没有能出纹理的部位：先给部位画走向线'))
            q = look.clean_params(body.params if body.params is not None else _base_look(d))
            if body.params is not None:
                d.set_look(q)
            if not d.wait_idle(EXPORT_WAIT):
                raise ValueError(tr('部位还在求解，稍等一下再导出'))
            _want_depth(d, q)
            if q['style'] in look.SPARKLE_STYLES and q['sparkle_depth'] > 0:
                end = time.monotonic() + EXPORT_WAIT
                while getattr(d, 'disparity', None) is None and time.monotonic() < end:
                    if depth.service.status == 'unavailable' or getattr(d, 'depth_error', None):
                        break
                    time.sleep(0.2)
                if getattr(d, 'disparity', None) is None:
                    notes.append(tr('深度模型不可用，“按深度”的亮点没有导出'))
            res = export.export(d, scene_for(d), q, folder, body.kind)
            missing = [r['name'] for r in d.state()['regions'] if r['status'] in ('nostroke', 'error')]
            if missing:
                notes.append(tr('{names}没有走向线，没有纹理', names=tr('、').join(missing)))
        d.last_export = res['file']
        return {'kind': body.kind, 'file': res['file'], 'folder': folder, 'seconds': res['seconds'], 'notes': notes}


@app.post('/api/doc/{doc_id}/export/reveal')
def reveal_export(doc_id: str):
    """Open the export folder in Explorer with the file just exported selected."""
    d = doc_for(doc_id)
    f = getattr(d, 'last_export', None)
    if not f or not os.path.exists(f):
        raise ValueError(tr('找不到刚导出的文件，可能已被移走或删除；再导出一次'))
    subprocess.Popen(['explorer', '/select,', os.path.normpath(f)])
    return {'ok': True}


# ------------------------------------------------------------------ events

@app.get('/api/events')
async def events(request: Request):
    q = asyncio.Queue()
    bus.queues.add(q)
    bus.ever_connected = True

    async def stream():
        try:
            yield 'retry: 1000\n\n'
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    if ev is None:
                        break
                    yield f'data: {json.dumps(ev, ensure_ascii=False)}\n\n'
                except asyncio.TimeoutError:
                    yield ': keepalive\n\n'
                if await request.is_disconnected():
                    break
        finally:
            bus.queues.discard(q)
            bus.last_seen = time.monotonic()

    return StreamingResponse(stream(), media_type='text/event-stream', headers=NO_STORE)

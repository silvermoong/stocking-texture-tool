"""The open document saved to disk as it is edited, so a restart (or a crash) picks up where the user left off.

Layout of the session folder: meta.json (names, colours, strokes, file name and path), masks.npz (one packed bit
mask per region) and art-<doc id>.png (the art, written once per document). Undo history is not kept.
"""
import glob
import json
import os
import time
import urllib.request

import cv2
import numpy as np

from . import settings

DIR = os.path.join(settings.DIR, 'session')
FORMAT = 1


def _replace(path, write):
    tmp = path + '.tmp'
    write(tmp)
    os.replace(tmp, path)


def write(d, doc_id, art_png, name, path, regions, strokes, sparkle=None, look=None, dividers=(), erased=(),
          color_exclude=True, guides_saved=False):
    """regions: [(name, colour, HxW bool)]; strokes: [(N x 2 points in px, index of the owning region or None)];
    sparkle: a painted 亮点 layer (HxW uint8) or None; look: the look settings or None; dividers: [N x 2 points]
    (隔开 lines); erased: [(x, y)] (deleted found walls); color_exclude: 颜色排除 on; guides_saved: the guides as
    they are are in a file (opened from one, or exported as 丝袜引导.psd)."""
    os.makedirs(d, exist_ok=True)
    art_file = f'art-{doc_id}.png'
    ap = os.path.join(d, art_file)
    if not os.path.exists(ap):
        _replace(ap, lambda p: open(p, 'wb').write(art_png))
    shape = regions[0][2].shape if regions else (0, 0)
    arrays = {f'm{i}': np.packbits(m) for i, (_, _, m) in enumerate(regions)}
    if sparkle is not None:
        arrays['sparkle'] = np.asarray(sparkle, np.uint8)

    def save_npz(p):
        with open(p, 'wb') as f:
            np.savez_compressed(f, shape=np.array(shape), **arrays)
    _replace(os.path.join(d, 'masks.npz'), save_npz)
    meta = {'format': FORMAT, 'saved': time.strftime('%Y-%m-%d %H:%M:%S'), 'name': name, 'path': path,
            'art': art_file, 'regions': [{'name': n, 'color': c} for n, c, _ in regions],
            'strokes': [{'pts': np.round(np.asarray(p, float), 2).ravel().tolist(), 'region': k} for p, k in strokes],
            'dividers': [np.round(np.asarray(p, float), 2).ravel().tolist() for p in dividers],
            'erased': [[round(float(x), 1), round(float(y), 1)] for x, y in erased],
            'color_exclude': bool(color_exclude),
            'guides_saved': bool(guides_saved),
            'look': look}
    _replace(os.path.join(d, 'meta.json'),
             lambda p: open(p, 'w', encoding='utf-8').write(json.dumps(meta, ensure_ascii=False)))
    for old in glob.glob(os.path.join(d, 'art-*.png')):
        if os.path.basename(old) != art_file:
            try:
                os.remove(old)
            except OSError:
                pass


def save(doc, d=DIR):
    snap = doc.snapshot()
    write(d, doc.id, snap['art_png'], snap['name'], snap['path'], snap['regions'], snap['strokes'],
          snap['sparkle'], snap['look'], snap['dividers'], snap['erased'], snap['color_exclude'],
          snap['guides_saved'])
    return snap['edits']


def load(d=DIR):
    """The saved document, or None if there is none (or it is unreadable)."""
    from .document import Document
    try:
        with open(os.path.join(d, 'meta.json'), encoding='utf-8') as f:
            meta = json.load(f)
        if meta.get('format') != FORMAT:
            return None
        bgr = cv2.imdecode(np.fromfile(os.path.join(d, meta['art']), np.uint8), cv2.IMREAD_COLOR)
        with np.load(os.path.join(d, 'masks.npz')) as z:
            shape = tuple(int(v) for v in z['shape'])
            masks = [np.unpackbits(z[f'm{i}'], count=shape[0] * shape[1]).reshape(shape).astype(bool)
                     for i in range(len(meta['regions']))]
            sparkle = z['sparkle'] if 'sparkle' in z.files else None
    except (OSError, ValueError, KeyError):
        return None
    if bgr is None or (masks and masks[0].shape != bgr.shape[:2]):
        return None
    if sparkle is not None and sparkle.shape != bgr.shape[:2]:
        sparkle = None
    regions = [(r['name'], r['color'], m) for r, m in zip(meta['regions'], masks)]
    strokes = [(np.asarray(s['pts'], float).reshape(-1, 2), s['region']) for s in meta['strokes']]
    dividers = [np.asarray(p, float).reshape(-1, 2) for p in meta.get('dividers', [])]
    return Document.from_snapshot(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), meta['name'], meta.get('path'),
                                  regions, strokes, sparkle, meta.get('look'), dividers, meta.get('erased', []),
                                  meta.get('color_exclude', True), meta.get('guides_saved', False))


def rescue(port, d=DIR, timeout=30):
    """Pull the open document out of a running server through its HTTP API and save it as the session.

    For servers from before sessions existed, which can only be stopped by killing them. Returns True if a
    document was saved."""
    base = f'http://127.0.0.1:{port}'

    def get(path):
        with urllib.request.urlopen(base + path, timeout=timeout) as r:
            return r.read()
    st = json.loads(get('/api/doc'))
    if not st:
        return False
    art_png = get(f"/api/doc/{st['id']}/art")
    regions, index = [], {}
    for i, r in enumerate(st['regions']):
        png = cv2.imdecode(np.frombuffer(get(f"/api/doc/{st['id']}/regions/{r['id']}/mask"), np.uint8),
                           cv2.IMREAD_UNCHANGED)
        regions.append((r['name'], r['color'], png[..., 3] > 0))
        index[r['id']] = i
    strokes = [(np.asarray(s['pts'], float).reshape(-1, 2), index.get(s['region'])) for s in st['strokes']]
    dividers = [np.asarray(dv['pts'], float).reshape(-1, 2) for dv in st.get('dividers', [])]
    write(d, st['id'], art_png, st['name'], st.get('path'), regions, strokes, dividers=dividers,
          color_exclude=st.get('color_exclude', True))
    return True

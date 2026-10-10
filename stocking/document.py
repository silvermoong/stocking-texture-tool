"""One open document: the art, rough regions, vector guide strokes, and the per-region course solve.

Strokes are polylines in image px. Each belongs to the region it overlaps most (ties go to the region that was
selected when it was drawn) and is rasterised STROKE_WIDTH px wide, clipped to that region, for the solver. Every
region carries a signature of its own solver inputs (its mask once overlaps are resolved, plus the strokes it owns);
the background worker re-solves exactly the regions whose signature changed, most recently changed first.
"""
import contextlib
import hashlib
import io
import itertools
import os
import threading
import time

import contourpy
import cv2
import numpy as np

from . import coverage, split
from . import guide_fields as gf
from . import psd_io, symmetry, trace
from . import walls as walls_mod
from .i18n import tr

NEVER_SAVED = object()          # Document._saved_at: the guides were never in a file
DEFAULT_REGIONS = ('左腿', '右腿')          # a pair to start with (named in the page's language); + adds more
PALETTE = ('#65a7fa', '#f2823b', '#b77ff2', '#47c496', '#f3c443',
           '#f075aa', '#54c9e3', '#97ca5d', '#ec5b57', '#c19d74')
STROKE_WIDTH = 5
ERASE_TOL = 12.0            # px (at 1280x1920): a deleted found wall is any found wall passing this near the spot
MARGIN = 8
REF_AREA = 1280 * 1920
UNDO_LIMIT = 200
SOLVE_CACHE = 3         # solves kept per region, so undo/redo of recent edits needs no re-solve
IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff')
PSD_EXTS = ('.psd', '.psb')


class Region:
    def __init__(self, rid, name, mask, color):
        self.id, self.name, self.mask, self.color = rid, name, mask, color
        self.mask_v = 0


class Stroke:
    def __init__(self, sid, pts, hint=None):
        self.id = sid
        self.pts = np.asarray(pts, np.float64).reshape(-1, 2)
        self.hint = hint        # region selected when it was drawn; breaks overlap ties
        self.region = None      # region it belongs to now (recomputed whenever regions or strokes change)
        lo = np.floor(self.pts.min(0)).astype(int) - STROKE_WIDTH
        hi = np.ceil(self.pts.max(0)).astype(int) + STROKE_WIDTH + 1
        self.box = (lo[0], lo[1], hi[0], hi[1])

    def raster(self, out, x0, y0):
        """Draw into uint8 `out` whose top-left pixel is image (x0, y0)."""
        p = np.round((self.pts - [x0, y0]) * 16).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(out, [p], False, 255, STROKE_WIDTH, cv2.LINE_8, 4)


class Divider:
    """A 隔开 line the user drew: a wall (see walls.py) in every region it crosses, depth or no depth."""
    WIDTH = 3

    def __init__(self, did, pts):
        self.id = did
        self.pts = np.asarray(pts, np.float64).reshape(-1, 2)

    def raster(self, out, x0, y0):
        p = np.round((self.pts - [x0, y0]) * 16).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(out, [p], False, 1, self.WIDTH, cv2.LINE_8, 4)


class Inputs:
    """Solver inputs for one region at the current edit state. walls: bool crop, the found walls left after the
    user's deletions plus the user's own 隔开 lines, or None; auto: the found ones alone (drawn dashed)."""

    def __init__(self, index, box, mc, alpha, nstrokes, walls=None, auto=None):
        self.index, self.box, self.mc, self.alpha, self.nstrokes = index, box, mc, alpha, nstrokes
        self.walls, self.auto = walls, auto
        h = hashlib.blake2b(digest_size=16)
        h.update(np.asarray(box, np.int64).tobytes())
        h.update(np.packbits(mc).tobytes())
        h.update(alpha.tobytes())
        if walls is not None:
            h.update(b'walls')
            h.update(np.packbits(walls).tobytes())
        self.sig = h.hexdigest()


class Solved:
    def __init__(self, sig, inp, fields, error, seconds, courses, wales, version, unguided=None, cut=None,
                 walls=None):
        self.sig, self.box, self.mc = sig, inp.box, inp.mc
        self.fields = fields            # (V, NX, NY, A) float32 on the box crop, or None
        self.error, self.seconds = error, seconds
        self.courses, self.wales = courses, wales
        self.version = version
        self.unguided = unguided        # crop bool: detached pieces with no stroke (no texture there), or None
        self.cut = cut                  # crop bool: the band along the walls where the fields jump, or None
        self.walls = walls              # the found walls as [x0, y0, x1, y1, ...] lines in tenths of image px


def iso_lines(field, mask, step, x0, y0):
    """Iso-lines of `field` inside `mask` every `step`, as flat [x0, y0, x1, y1, ...] lists in tenths of image px.

    Pieces shorter than 1.5 steps are dropped: they are the field rolling off along the ragged region edge (the
    solve runs on a 1/4 grid), not courses.
    """
    if not mask.any():
        return []
    vals = field[mask]
    lo, hi = float(vals.min()), float(vals.max())
    if not np.isfinite([lo, hi]).all() or hi - lo < step:
        return []
    gen = contourpy.contour_generator(z=np.ma.array(np.where(mask, field, 0.0), mask=~mask))
    out = []
    for lv in np.arange(np.ceil(lo / step) * step, hi, step):
        for seg in gen.lines(lv):
            if len(seg) < 4 or np.hypot(*np.diff(seg, axis=0).T).sum() < 1.5 * step:
                continue
            seg = cv2.approxPolyDP(seg.astype(np.float32).reshape(-1, 1, 2), 0.35, False).reshape(-1, 2)
            out.append(np.round((seg + [x0, y0]) * 10).astype(int).ravel().tolist())
    return out


def _dist_to_polyline(p, P):
    """Distance from point p to polyline P (N, 2)."""
    a, b = P[:-1], P[1:]
    d = b - a
    l2 = np.maximum((d * d).sum(1), 1e-12)
    t = np.clip(((p - a) * d).sum(1) / l2, 0, 1)
    return float(np.hypot(*(a + t[:, None] * d - p).T).min())


def wall_polylines(walls, x0, y0):
    """Walls (bool crop) as centre polylines, flat [x0, y0, x1, y1, ...] in tenths of image px, for the 走向 view."""
    out = []
    n, lab = cv2.connectedComponents(walls.astype(np.uint8), connectivity=8)
    for k in range(1, n):
        m = lab == k
        ends = walls_mod._ends(m)
        if len(ends) < 2:
            continue
        # a wall is a thin curve: order its pixels along it from one end
        ys, xs = np.nonzero(m)
        P = np.stack([xs, ys], 1).astype(np.float64)
        e = ends[0][0]
        d = np.hypot(*(P - e).T)
        order = np.argsort(d)
        Q = P[order]
        bins = np.round(d[order] / 3.0).astype(int)
        _, first = np.unique(bins, return_index=True)
        pts = np.stack([np.add.reduceat(Q[:, 0], first) / np.diff(np.r_[first, len(Q)]),
                        np.add.reduceat(Q[:, 1], first) / np.diff(np.r_[first, len(Q)])], 1)
        out.append(np.round((pts + [x0, y0]) * 10).astype(int).ravel().tolist())
    return out


def _clip_polyline(P, mask, step=1.5, min_len=8.0):
    """The runs of polyline P (N x 2 image px) that lie inside bool `mask`, each at least min_len px long."""
    seg = np.diff(P, axis=0)
    d = np.r_[0, np.cumsum(np.hypot(*seg.T))]
    if d[-1] <= 0:
        return []
    t = np.linspace(0, d[-1], max(int(np.ceil(d[-1] / step)) + 1, 2))
    Q = np.c_[np.interp(t, d, P[:, 0]), np.interp(t, d, P[:, 1])]
    h, w = mask.shape
    ix, iy = np.round(Q[:, 0]).astype(int), np.round(Q[:, 1]).astype(int)
    inside = (ix >= 0) & (ix < w) & (iy >= 0) & (iy < h)
    inside[inside] = mask[iy[inside], ix[inside]]
    runs, start = [], None
    for i, ok in enumerate(np.r_[inside, False]):
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            if t[i - 1] - t[start] >= min_len:
                runs.append(Q[start:i])
            start = None
    return runs


def _pack(a):
    return a.shape, np.packbits(a)


def _unpack(p):
    shape, bits = p
    return np.unpackbits(bits, count=int(np.prod(shape))).reshape(shape).astype(bool)


def clean_segment(m, min_frac=2e-4):
    """A SAM mask as (box (x0, y0, x1, y1), crop), with specks and pinholes smaller than min_frac of the image
    removed; (None, None) if nothing is left."""
    m = np.asarray(m, bool)
    small = max(int(min_frac * m.size), 16)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
    if n > 1:
        m = np.isin(lab, 1 + np.flatnonzero(st[1:, 4] >= small))
    n, lab, st, _ = cv2.connectedComponentsWithStats((~m).astype(np.uint8), connectivity=4)
    h, w = m.shape
    for i in range(1, n):
        x, y, bw, bh, area = st[i]
        if area < small and x > 0 and y > 0 and x + bw < w and y + bh < h:
            m[lab == i] = True
    box = gf.region_box(m, margin=0)
    if box is None:
        return None, None
    y0, y1, x0, x1 = box
    return (x0, y0, x1, y1), m[y0:y1, x0:x1].copy()


class Document:
    def __init__(self, art_rgb, name, path=None):
        self.art = np.ascontiguousarray(art_rgb)
        self.h, self.w = self.art.shape[:2]
        self.name, self.path = name, path
        self.id = hashlib.blake2b(f'{name}{time.time()}'.encode(), digest_size=6).hexdigest()
        self.scale = float(np.sqrt(self.w * self.h / REF_AREA))
        self.course_step = 16.0 * self.scale
        self.sparkle = None
        self.look = None                # the user's look settings (look.clean_params), None = defaults
        self.regions, self.strokes = [], []
        self.dividers = []              # the user's 隔开 lines (Divider)
        self.erased = []                # (x, y) where the user deleted a found wall: walls there are dropped
        self.color_exclude = True       # 颜色排除: drop region pixels whose colour is far from the stocking's
        self._known = {}                # every region ever created, by id (undo can bring deleted ones back)
        self.dirty = False              # edited since opening
        self._saved_at = None           # the edit on top of the undo stack when the guides last matched a file
                                        # (opened, or exported as 丝袜引导.psd); NEVER_SAVED: no file has them
        self.edits = 0                  # bumped by every edit, undo and redo (the autosave watches it)
        self._seg_last = None           # last click-to-segment, for cycling through SAM's candidates
        self._lab, self._cov_key, self._cov = None, None, None
        self._disparity, self._ridges, self._walls = None, None, {}
        self.sam_state, self.sam_error, self.sam_embedding = 'waiting', None, None
        self._ids = itertools.count(1)
        self._versions = itertools.count(1)
        self._undo, self._redo = [], []
        self._epoch, self._prep_epoch, self._prep = 0, -1, None
        self._changed_at = {}           # region id -> time its solver inputs last changed
        self._last_sig = {}
        self._solves = {}               # region id -> {sig: Solved}, newest last; kept after deletion for undo
        self._solving = None            # (region id, sig) being solved right now
        self.lock = threading.RLock()
        self._cv = threading.Condition(self.lock)
        self._closed = False
        self.on_event = None
        self._art_png = None
        self._worker = threading.Thread(target=self._work, name=f'solve-{self.id}', daemon=True)
        self._worker.start()

    # ---------------------------------------------------------------- loading

    @classmethod
    def open(cls, path=None, data=None, filename=None):
        name = filename or os.path.basename(path)
        ext = os.path.splitext(name)[1].lower()
        dividers = None
        if ext in PSD_EXTS:
            g = psd_io.read_guide_layers(path if data is None else io.BytesIO(data))
            art, regions, strokes, sparkle, dividers = g['art'], g['regions'], g['strokes'], g['sparkle'], g['dividers']
        elif ext in IMAGE_EXTS:
            buf = np.fromfile(path, np.uint8) if data is None else np.frombuffer(data, np.uint8)
            bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if bgr is None:
                raise ValueError(tr('读不了这个文件：{name}', name=name))
            art, regions, strokes, sparkle = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), {}, None, None
        else:
            raise ValueError(tr('只支持 PNG、JPG 或 PSD：{name}', name=name))
        doc = cls(art, name, path)
        doc.sparkle = sparkle
        with doc.lock:
            for nm in (list(regions) or [tr(n) for n in DEFAULT_REGIONS]):
                doc._new_region(nm, regions.get(nm))
            if strokes is not None:
                doc._import_strokes(strokes)
            if dividers is not None:
                doc.dividers = [Divider(next(doc._ids), Q) for Q in trace.trace_lines(dividers)]
            doc._touch()
            doc.dirty = False
        return doc

    def _import_strokes(self, stroke_alpha):
        """A raster stroke layer as vector strokes: the centre line of each stroke inside each region, i.e. exactly
        the polylines the solver itself extracts from that layer. Pieces outside every region are kept too."""
        REG = (gf.label_regions([r.mask for r in self.regions], min_frac=0) if self.regions
               else np.zeros((self.h, self.w), np.int8))
        for i in range(len(self.regions) + 1):
            hint = self.regions[i - 1].id if i else None
            for Q in gf.centre_lines(stroke_alpha, REG == i):
                if len(Q) >= 2:
                    self.strokes.append(Stroke(next(self._ids), Q, hint))

    @classmethod
    def from_snapshot(cls, art_rgb, name, path, regions, strokes, sparkle=None, look=None, dividers=(), erased=(),
                      color_exclude=True, guides_saved=False):
        """regions: [(name, colour, mask)]; strokes: [(points, index of the owning region or None)];
        dividers: [points] (隔开 lines); erased: [(x, y)] (deleted found walls); color_exclude: 颜色排除 on;
        guides_saved: the guides were in a file when the snapshot was taken."""
        doc = cls(art_rgb, name, path)
        doc.sparkle, doc.look = sparkle, look
        doc.color_exclude = bool(color_exclude)
        with doc.lock:
            made = []
            for nm, color, mask in regions:
                r = doc._new_region(nm, mask)
                r.color = color
                made.append(r)
            for pts, k in strokes:
                if len(pts) >= 2:
                    hint = made[k].id if k is not None and 0 <= k < len(made) else None
                    doc.strokes.append(Stroke(next(doc._ids), pts, hint))
            for pts in dividers:
                if len(pts) >= 2:
                    doc.dividers.append(Divider(next(doc._ids), pts))
            doc.erased = [(float(x), float(y)) for x, y in erased]
            doc._touch()
            doc.dirty = True
            doc._saved_at = None if guides_saved else NEVER_SAVED
        return doc

    def _top(self):
        return self._undo[-1] if self._undo else None

    def mark_guides_saved(self):
        """The guides as they are now were written to a file (丝袜引导.psd)."""
        with self.lock:
            self._saved_at = self._top()

    def unsaved_guides(self):
        """Regions or 走向 lines the user would lose by opening another image: they differ from the last file that
        held them (undoing back to that point counts as unchanged), and there is something in them."""
        with self.lock:
            if self._saved_at is not NEVER_SAVED and self._top() is self._saved_at:
                return False
            return bool(self.strokes or self.dividers or any(r.mask.any() for r in self.regions))

    def snapshot(self):
        """Everything from_snapshot needs, copied under the lock (the session saver writes it out unlocked)."""
        with self.lock:
            self._prepare()
            index = {r.id: i for i, r in enumerate(self.regions)}
            return {'name': self.name, 'path': self.path, 'art_png': self.art_png(), 'edits': self.edits,
                    'regions': [(r.name, r.color, r.mask.copy()) for r in self.regions],
                    'strokes': [(s.pts.copy(), index.get(s.region, index.get(s.hint))) for s in self.strokes],
                    'dividers': [d.pts.copy() for d in self.dividers], 'erased': list(self.erased),
                    'color_exclude': self.color_exclude,
                    'sparkle': self.sparkle, 'look': self.look, 'guides_saved': not self.unsaved_guides()}

    def set_look(self, params):
        with self.lock:
            if params != self.look:
                self.look = params
                self.edits += 1

    def set_color_exclude(self, on):
        """颜色排除 on or off (undoable): off textures every pixel of every region, whatever its colour."""
        with self.lock:
            on = bool(on)
            if on == self.color_exclude:
                return
            self._push(('exclude', self.color_exclude, on))
            self.color_exclude = on
            self._touch()

    def render_key(self):
        """Changes whenever what a render would show changes: solves, region names (tilt sides), coverage."""
        with self.lock:
            _, prep = self._prepare()
            parts = []
            for r in self.regions:
                s = self._solve_for(r.id, prep.get(r.id))
                parts.append((r.id, r.name, s.version if s is not None and s.fields is not None else None))
            return (self.id, tuple(parts), self._coverage_key()[1])

    def close(self):
        with self._cv:
            self._closed = True
            self._cv.notify_all()

    # ---------------------------------------------------------------- edits (all hold self.lock)

    def _new_region(self, name, mask=None, index=None):
        used = {r.color for r in self.regions}
        color = next((c for c in PALETTE if c not in used), PALETTE[len(self.regions) % len(PALETTE)])
        m = np.zeros((self.h, self.w), bool) if mask is None else np.asarray(mask, bool).copy()
        r = Region(next(self._ids), name, m, color)
        self.regions.insert(len(self.regions) if index is None else index, r)
        self._known[r.id] = r
        return r

    def _unique_name(self, name):
        used = {r.name for r in self.regions}
        if name not in used:
            return name
        k = 2
        while f'{name} {k}' in used:
            k += 1
        return f'{name} {k}'

    @contextlib.contextmanager
    def _batch(self):
        """Edits inside become one undo step."""
        outer, self._undo = self._undo, []
        try:
            yield
        finally:
            ops, self._undo = self._undo, outer
            if ops:
                self._push(ops[0] if len(ops) == 1 else ('group', ops))

    def region(self, rid):
        for r in self.regions:
            if r.id == rid:
                return r
        raise KeyError(rid)

    def _touch(self):
        self._epoch += 1
        self._cv.notify_all()

    @property
    def disparity(self):
        """The depth model's disparity (depth.DepthService sets it), or None until it is ready."""
        return self._disparity

    @disparity.setter
    def disparity(self, d):
        with self._cv:
            self._disparity, self._ridges, self._walls = d, None, {}
            self._touch()                   # walls come with it: regions with one re-solve

    def _walls_for(self, rid, key, box, mc, stock):
        """Walls inside one region's box crop (walls.find_walls), cached on the masks; None without depth."""
        if self._disparity is None:
            return None
        hit = self._walls.get(rid)
        if hit is not None and hit[0] == key:
            return hit[1]
        if self._ridges is None:
            self._ridges = walls_mod.ridges(self._disparity, self.scale)
        y0, y1, x0, x1 = box
        sl = (slice(y0, y1), slice(x0, x1))
        W = walls_mod.find_walls(walls_mod.crop(self._ridges, sl), stock[sl] & mc, self.scale)
        W = W if W.any() else None
        self._walls[rid] = (key, W)
        return W

    def _drop_erased(self, W, x0, y0):
        """Found walls (crop at image (x0, y0)) less the pieces the user deleted: those passing near an erased spot."""
        if W is None or not self.erased:
            return W
        n, lab = cv2.connectedComponents(W.astype(np.uint8), connectivity=8)
        ys, xs = np.nonzero(lab)
        tol = ERASE_TOL * self.scale
        gone = set()
        for x, y in self.erased:
            near = np.hypot(xs + x0 - x, ys + y0 - y) <= tol
            gone.update(np.unique(lab[ys[near], xs[near]]).tolist())
        if not gone:
            return W
        W = W & ~np.isin(lab, list(gone))
        return W if W.any() else None

    def _push(self, op):
        self._undo.append(op)
        del self._undo[:-UNDO_LIMIT]
        self._redo.clear()
        self.dirty = True
        self.edits += 1

    def add_region(self, name):
        with self.lock:
            r = self._new_region(name)
            self._push(('region+', r, len(self.regions) - 1))
            self._touch()
            return r.id

    def delete_region(self, rid):
        with self.lock:
            r = self.region(rid)
            i = self.regions.index(r)
            self.regions.pop(i)
            self._push(('region-', r, i))
            self._touch()

    def rename_region(self, rid, name):
        with self.lock:
            r = self.region(rid)
            if name != r.name:
                self._push(('rename', rid, r.name, name))
                r.name = name

    def split_region(self, rid, line=None, snap_radius=0):
        """Cut a region in two, along `line` (N x 2 px, carried on past its ends) if given, else automatically
        (see split.py): it keeps the left/top part and is renamed <name>-左/-上; a new region <name>-右/-下 right
        after it gets the rest. snap_radius > 0 first moves the line onto the line art within that many px.
        Returns (kept id, new id); one undo step."""
        with self.lock:
            r = self.region(rid)
            if line is not None:
                res = split.cut_mask(r.mask, line, self.art, snap_radius)
                if res is None:
                    raise ValueError(tr('这条线没有把“{name}”分成两半。线要横穿过它；要切别的部位，先在左边选中那个部位',
                                        name=r.name))
            else:
                res = split.split_mask(r.mask, self.art)
                if res is None:
                    raise ValueError(tr('“{name}”太小了，分不成两块', name=r.name))
            a, b, axis = res
            first, second = (tr('左'), tr('右')) if axis == 'x' else (tr('上'), tr('下'))
            box = gf.region_box(r.mask, margin=0)
            y0, y1, x0, x1 = box
            with self._batch():
                self._set_masks([(r, (x0, y0, x1, y1), a[y0:y1, x0:x1])])
                base = r.name
                nb = self._new_region(self._unique_name(f'{base}-{second}'), b, index=self.regions.index(r) + 1)
                self._push(('region+', nb, self.regions.index(nb)))
                new_name = self._unique_name(f'{base}-{first}')
                self._push(('rename', r.id, base, new_name))
                r.name = new_name
                self._touch()
            return r.id, nb.id

    def merge_region(self, rid, into):
        """Fold region rid into region `into` (which keeps its name and colour); one undo step. Strokes follow
        the pixels they lie on."""
        with self.lock:
            src, dst = self.region(rid), self.region(into)
            if src is dst:
                raise ValueError(tr('不能合并到自己'))
            box = gf.region_box(src.mask, margin=0)
            with self._batch():
                if box is not None:
                    y0, y1, x0, x1 = box
                    self._set_masks([(dst, (x0, y0, x1, y1), dst.mask[y0:y1, x0:x1] | src.mask[y0:y1, x0:x1])])
                i = self.regions.index(src)
                self.regions.pop(i)
                self._push(('region-', src, i))
                self._touch()

    def neighbours(self, rid):
        """Other regions by how much border they share with rid (pixels within 3 px), most first."""
        with self.lock:
            r = self.region(rid)
            box = gf.region_box(r.mask, margin=4)
            out = []
            for o in self.regions:
                if o is r:
                    continue
                shared = 0
                if box is not None:
                    y0, y1, x0, x1 = box
                    ring = cv2.dilate(r.mask[y0:y1, x0:x1].astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
                    shared = int((ring & o.mask[y0:y1, x0:x1]).sum())
                out.append({'id': o.id, 'name': o.name, 'color': o.color, 'shared': shared})
            out.sort(key=lambda d: -d['shared'])
            return out

    def _set_masks(self, changes):
        """Apply [(region, (x0, y0, x1, y1), new crop), ...] as one undo step. Returns the op, or None if nothing
        changed."""
        rec = []
        for r, box, new in changes:
            x0, y0, x1, y1 = box
            old = r.mask[y0:y1, x0:x1]
            if np.array_equal(old, new):
                continue
            rec.append((r.id, box, _pack(old.copy()), _pack(new)))
            r.mask[y0:y1, x0:x1] = new
            r.mask_v += 1
        if not rec:
            return None
        op = ('masks', rec)
        self._push(op)
        self._touch()
        return op

    def _claim(self, r, box, seg):
        """Changes that add `seg` (a crop at `box`) to region r and take it away from every other region:
        each pixel belongs to one region, so what the overlay shows is what the solver gets."""
        x0, y0, x1, y1 = box
        changes = [(r, box, r.mask[y0:y1, x0:x1] | seg)]
        for o in self.regions:
            if o is not r:
                oc = o.mask[y0:y1, x0:x1]
                if (oc & seg).any():
                    changes.append((o, box, oc & ~seg))
        return changes

    def paint(self, rid, pts, radius, erase=False):
        """Brush (or erase) along a polyline of image-px points with the given radius. Painting takes the pixels
        from every other region; erasing touches only this one. Returns True if anything changed."""
        with self.lock:
            r = self.region(rid)
            P = np.asarray(pts, np.float64).reshape(-1, 2)
            if not len(P):
                return False
            radius = max(float(radius), 0.5)
            pad = int(np.ceil(radius)) + 2
            x0, y0 = np.maximum(np.floor(P.min(0)).astype(int) - pad, 0)
            x1, y1 = np.minimum(np.ceil(P.max(0)).astype(int) + pad + 1, [self.w, self.h])
            if x1 <= x0 or y1 <= y0:
                return False
            stamp = np.zeros((y1 - y0, x1 - x0), np.uint8)
            q = np.round((P - [x0, y0]) * 16).astype(np.int32)
            rq = int(round(radius * 16))
            for x, y in q:
                cv2.circle(stamp, (int(x), int(y)), rq, 255, -1, cv2.LINE_8, 4)
            if len(q) > 1:
                cv2.polylines(stamp, [q.reshape(-1, 1, 2)], False, 255, max(int(round(2 * radius)), 1), cv2.LINE_8, 4)
            box = (x0, y0, x1, y1)
            seg = stamp > 0
            if erase:
                changes = [(r, box, r.mask[y0:y1, x0:x1] & ~seg)]
            else:
                changes = self._claim(r, box, seg)
            return self._set_masks(changes) is not None

    def clear_region(self, rid):
        with self.lock:
            r = self.region(rid)
            return self._set_masks([(r, (0, 0, self.w, self.h), np.zeros((self.h, self.w), bool))]) is not None

    # ---------------------------------------------------------------- click to segment

    def _segment_op(self, r, cand, subtract):
        box, seg = cand
        if box is None:
            return None
        x0, y0, x1, y1 = box
        if subtract:
            return self._set_masks([(r, box, r.mask[y0:y1, x0:x1] & ~seg)])
        return self._set_masks(self._claim(r, box, seg))

    def segment_click(self, rid, x, y, subtract, masks, best):
        """Add (or subtract) the segment SAM proposes at (x, y) to region rid. `masks` are SAM's candidates for the
        click, smallest first; `best` is the one applied. cycle_segment() swaps in another candidate afterwards."""
        with self.lock:
            r = self.region(rid)
            cands = [clean_segment(m) for m in masks]
            op = self._segment_op(r, cands[best], subtract)
            self._seg_last = {'rid': rid, 'subtract': subtract, 'cands': cands, 'k': best, 'op': op,
                              'epoch': self._epoch, 'pt': (float(x), float(y)), 'click': next(self._ids),
                              'outlines': None}
            return op is not None

    def cycle_segment(self, step=1):
        """Replace the last click's segment with the next of SAM's candidates. Only straight after the click."""
        with self.lock:
            L = self._seg_last
            if not L or L['epoch'] != self._epoch:
                raise ValueError(tr('只能在点选之后马上切换范围'))
            return self.select_segment((L['k'] + step) % len(L['cands']))

    def select_segment(self, k):
        """Replace the last click's segment with SAM's candidate k (0 = smallest). Only straight after the click."""
        with self.lock:
            L = self._seg_last
            if not L or L['epoch'] != self._epoch or not 0 <= k < len(L['cands']):
                raise ValueError(tr('只能在点选之后马上切换范围'))
            if k == L['k']:
                return k
            if L['op'] is not None:
                if not self._undo or self._undo[-1] is not L['op']:
                    raise ValueError(tr('只能在点选之后马上切换范围'))
                self._undo.pop()
                self._apply(L['op'], False)
            op = self._segment_op(self.region(L['rid']), L['cands'][k], L['subtract'])
            L.update(k=k, op=op, epoch=self._epoch)
            return k

    def segment_outlines(self):
        """Outlines of the last click's candidates, smallest first: {click, outlines: [[flat xy in tenths], ...]}."""
        with self.lock:
            L = self._seg_last
            if not L:
                return {'click': None, 'outlines': []}
            if L['outlines'] is None:
                out = []
                for box, seg in L['cands']:
                    lines = []
                    if box is not None:
                        cs, _ = cv2.findContours(seg.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                        for c in cs:
                            if len(c) < 3:
                                continue
                            c = cv2.approxPolyDP(c, 0.8, True).reshape(-1, 2).astype(np.float64)
                            c = np.vstack([c, c[:1]]) + [box[0], box[1]]
                            lines.append(np.round(c * 10).astype(int).ravel().tolist())
                    out.append(lines)
                L['outlines'] = out
            return {'click': L['click'], 'outlines': L['outlines']}

    def add_stroke(self, pts, hint=None):
        with self.lock:
            s = Stroke(next(self._ids), pts, hint)
            if len(s.pts) < 2:
                raise ValueError(tr('走向线至少要两个点'))
            self.strokes.append(s)
            self._push(('stroke+', s, len(self.strokes) - 1))
            self._touch()
            return s.id

    def delete_stroke(self, sid):
        with self.lock:
            s = next((s for s in self.strokes if s.id == sid), None)
            if s is None:
                raise KeyError(sid)
            i = self.strokes.index(s)
            self.strokes.pop(i)
            self._push(('stroke-', s, i))
            self._touch()

    def mirror_strokes(self, rid, into):
        """Replace region `into`'s strokes with rid's, mirrored across by the flip-rotate-scale that best lays rid's
        outline onto into's (symmetry.fit_mirror), each clipped to `into`. The results are ordinary strokes, free to
        edit. One undo step. Returns (strokes made, strokes replaced, outline fit error in px)."""
        with self.lock:
            src, dst = self.region(rid), self.region(into)
            if src is dst:
                raise ValueError(tr('不能镜像到自己'))
            REG, _ = self._prepare()
            A, B = REG == self.regions.index(src) + 1, REG == self.regions.index(dst) + 1
            for r, m in ((src, A), (dst, B)):
                if not m.any():
                    raise ValueError(tr('“{name}”还没有涂', name=r.name))
            own = [s for s in self.strokes if s.region == src.id]
            if not own:
                raise ValueError(tr('“{name}”还没有走向线，先在它上面画几条', name=src.name))
            M, rms = symmetry.fit_mirror(A, B)
            runs = []
            for s in own:
                runs += _clip_polyline(s.pts @ M[:2, :2].T + M[:2, 2], B)
            if not runs:
                raise ValueError(tr('镜像过去的走向线都落在“{name}”外面', name=dst.name))
            old = [s for s in self.strokes if s.region == dst.id]
            with self._batch():
                for s in old:
                    i = self.strokes.index(s)
                    self.strokes.pop(i)
                    self._push(('stroke-', s, i))
                for pts in runs:
                    s = Stroke(next(self._ids), pts, dst.id)
                    self.strokes.append(s)
                    self._push(('stroke+', s, len(self.strokes) - 1))
                self._touch()
            return len(runs), len(old), rms

    # ---------------------------------------------------------------- walls (隔开)

    def add_divider(self, pts):
        """A 隔开 line: the courses do not continue across it, in whatever region it crosses."""
        with self.lock:
            d = Divider(next(self._ids), pts)
            if len(d.pts) < 2:
                raise ValueError(tr('隔开线至少要两个点'))
            self.dividers.append(d)
            self._push(('divider+', d, len(self.dividers) - 1))
            self._touch()
            return d.id

    def remove_wall_at(self, x, y, tol):
        """Delete the wall nearest (x, y) within tol px: one of the user's 隔开 lines, or a found one (remembered as
        a deleted spot, so it stays gone). Returns 'divider' or 'found'."""
        with self.lock:
            p = np.array([x, y], np.float64)
            best, bd = None, tol
            for d in self.dividers:
                dd = _dist_to_polyline(p, d.pts)
                if dd <= bd:
                    best, bd = d, dd
            if best is not None:
                i = self.dividers.index(best)
                self.dividers.pop(i)
                self._push(('divider-', best, i))
                self._touch()
                return 'divider'
            _, prep = self._prepare()
            for r in self.regions:
                inp = prep.get(r.id)
                if inp is None or inp.auto is None:
                    continue
                y0, y1, x0, x1 = inp.box
                ys, xs = np.nonzero(inp.auto)
                if len(ys) and np.hypot(xs + x0 - x, ys + y0 - y).min() <= tol:
                    self.erased.append((float(x), float(y)))
                    self._push(('erase+', (float(x), float(y)), len(self.erased) - 1))
                    self._touch()
                    return 'found'
            raise ValueError(tr('这里没有隔开线'))

    def _apply(self, op, forward):
        kind = op[0]
        if kind == 'group':
            for sub in (op[1] if forward else reversed(op[1])):
                self._apply(sub, forward)
        elif kind == 'masks':
            for rid, (x0, y0, x1, y1), before, after in op[1]:
                r = self._known[rid]
                r.mask[y0:y1, x0:x1] = _unpack(after if forward else before)
                r.mask_v += 1
        elif kind in ('region+', 'region-'):
            _, r, i = op
            if (kind == 'region+') == forward:
                self.regions.insert(i, r)
                r.mask_v += 1
            else:
                self.regions.remove(r)
        elif kind in ('stroke+', 'stroke-'):
            _, s, i = op
            if (kind == 'stroke+') == forward:
                self.strokes.insert(i, s)
            else:
                self.strokes.remove(s)
        elif kind in ('divider+', 'divider-'):
            _, d, i = op
            if (kind == 'divider+') == forward:
                self.dividers.insert(i, d)
            else:
                self.dividers.remove(d)
        elif kind == 'erase+':
            _, pt, i = op
            if forward:
                self.erased.insert(i, pt)
            else:
                self.erased.pop(i)
        elif kind == 'exclude':
            self.color_exclude = op[2] if forward else op[1]
        elif kind == 'rename':
            _, rid, old, new = op
            self._known[rid].name = new if forward else old
        self._touch()

    def undo(self):
        with self.lock:
            if not self._undo:
                return False
            op = self._undo.pop()
            self._apply(op, False)
            self._redo.append(op)
            self.dirty = True
            self.edits += 1
            return True

    def redo(self):
        with self.lock:
            if not self._redo:
                return False
            op = self._redo.pop()
            self._apply(op, True)
            self._undo.append(op)
            self.dirty = True
            self.edits += 1
            return True

    # ---------------------------------------------------------------- solver inputs

    def _prepare(self):
        """Resolve overlaps, assign strokes to regions, and build each region's solver inputs (cached per edit)."""
        if self._prep_epoch == self._epoch:
            return self._prep
        n = len(self.regions)
        # every piece the user selected counts, however small: a strip of leg showing between strands of hair is
        # cut off from the rest, and the solver carries the courses on into it (guide_fields.solve_region)
        REG = gf.label_regions([r.mask for r in self.regions], min_frac=0) if n else np.zeros((self.h, self.w), np.int8)
        index = {r.id: i for i, r in enumerate(self.regions, 1)}
        for s in self.strokes:
            x0, y0, x1, y1 = s.box
            x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, self.w), min(y1, self.h)
            s.region = None
            if x1 <= x0 or y1 <= y0:
                continue
            tmp = np.zeros((y1 - y0, x1 - x0), np.uint8)
            s.raster(tmp, x0, y0)
            c = np.bincount(REG[y0:y1, x0:x1][tmp > 0].astype(np.int64), minlength=n + 1)
            c[0] = 0
            if c.max() < gf.MIN_STROKE_PX:
                continue
            best = np.flatnonzero(c == c.max())
            k = index.get(s.hint) if index.get(s.hint) in best else best[0]
            s.region = self.regions[k - 1].id
        prep = {}
        now = time.monotonic()
        stock = self._stock(REG)[0] if self._disparity is not None and n else None
        mkey = self._coverage_key()[1]
        for i, r in enumerate(self.regions, 1):
            m = REG == i
            box = gf.region_box(m, MARGIN)
            if box is None:
                prep[r.id] = None
                continue
            y0, y1, x0, x1 = box
            mc = m[y0:y1, x0:x1]
            alpha = np.zeros(mc.shape, np.uint8)
            own = [s for s in self.strokes if s.region == r.id]
            for s in own:
                s.raster(alpha, x0, y0)
            W = self._walls_for(r.id, (mkey, box), box, mc, stock) if stock is not None and own else None
            W = self._drop_erased(W, x0, y0)
            mine = np.zeros(mc.shape, np.uint8)
            for d in self.dividers:
                d.raster(mine, x0, y0)
            mine = mine > 0
            walls = W if not mine.any() else (mine if W is None else W | mine)
            inp = Inputs(i, (y0, y1, x0, x1), mc, alpha, len(own), walls, W)
            if self._last_sig.get(r.id) != inp.sig:
                self._last_sig[r.id] = inp.sig
                self._changed_at[r.id] = now
            prep[r.id] = inp
        self._prep, self._prep_epoch = (REG, prep), self._epoch
        return self._prep

    def _solve_for(self, rid, inp):
        """The solve matching the region's current inputs, if there is one."""
        c = self._solves.get(rid)
        return c.get(inp.sig) if c and inp is not None else None

    def _shown(self, rid, inp):
        """The solve to draw: the current one, else the newest (stale, shown faded until the new one lands)."""
        s = self._solve_for(rid, inp)
        if s is None and self._solves.get(rid):
            s = next(reversed(self._solves[rid].values()))
        return s

    def _status(self, rid, inp):
        if inp is None:
            return 'empty'
        if inp.nstrokes == 0:
            return 'nostroke'
        s = self._solve_for(rid, inp)
        if s is not None:
            return 'error' if s.error else 'ok'
        if self._solving == (rid, inp.sig):
            return 'solving'
        return 'pending'

    def _next_job(self):
        _, prep = self._prepare()
        todo = [(self._changed_at.get(rid, 0), rid) for rid, inp in prep.items()
                if self._status(rid, inp) == 'pending']
        if not todo:
            return None
        rid = max(todo)[1]
        return rid, prep[rid]

    # ---------------------------------------------------------------- solver worker

    def _emit(self, **ev):
        cb = self.on_event
        if cb is not None:
            cb(dict(ev, doc=self.id))

    def _work(self):
        while True:
            with self._cv:
                job = None
                while not self._closed and (job := self._next_job()) is None:
                    self._cv.wait()
                if self._closed:
                    return
                rid, inp = job
                self._solving = (rid, inp.sig)
            self._emit(type='solving', region=rid)
            t = time.perf_counter()
            fields, error, courses, wales, unguided, cut, wall_lines = None, None, [], [], None, None, []
            try:
                info = {}
                res = gf.solve_region(inp.mc, inp.alpha, inp.walls, info)
                if res is not None:
                    fields = tuple(f.astype(np.float32) for f in res)
                    bare = inp.mc & np.isnan(fields[0])     # a piece with no stroke, even after filling occlusions
                    solved = inp.mc & ~bare
                    if not solved.any() or not np.isfinite(fields[0][solved]).all():
                        fields, error = None, tr('求解失败（数值发散），试着调整走向线')
                    else:
                        fields = tuple(np.where(bare, np.float32(0), f) for f in fields)
                        unguided = bare if bare.any() else None
                        y0, _, x0, _ = inp.box
                        cut = info.get('cut')
                        lines_in = solved if cut is None else solved & ~cut     # no lines along the jump
                        courses = iso_lines(fields[0], lines_in, self.course_step, x0, y0)
                        wales = iso_lines(fields[3], lines_in, self.course_step, x0, y0)
                        if inp.auto is not None:
                            wall_lines = wall_polylines(inp.auto, x0, y0)
            except Exception as e:      # a bad stroke set must not kill the worker
                error = tr('求解出错：{error}', error=e)
            dt = time.perf_counter() - t
            with self._cv:
                cache = self._solves.setdefault(rid, {})
                cache.pop(inp.sig, None)
                cache[inp.sig] = Solved(inp.sig, inp, fields, error, dt, courses, wales, next(self._versions),
                                        unguided, cut, wall_lines)
                while len(cache) > SOLVE_CACHE:
                    del cache[next(iter(cache))]
                self._solving = None
            self._emit(type='solved', region=rid, seconds=round(dt, 2), error=error)

    def wait_idle(self, timeout=60):
        """Block until every region is solved for the current edit state (tests and scripts)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.lock:
                _, prep = self._prepare()
                if all(self._status(rid, inp) not in ('pending', 'solving') for rid, inp in prep.items()):
                    return True
            time.sleep(0.05)
        return False

    # ---------------------------------------------------------------- views

    def state(self):
        with self.lock:
            _, prep = self._prepare()
            regions = []
            for r in self.regions:
                inp = prep.get(r.id)
                s = self._shown(r.id, inp)
                regions.append({
                    'id': r.id, 'name': r.name, 'color': r.color, 'mask_v': r.mask_v,
                    'status': self._status(r.id, inp),
                    'strokes': 0 if inp is None else inp.nstrokes,
                    'solve_v': s.version if s else 0,
                    'seconds': round(s.seconds, 2) if s else None,
                    'error': s.error if s else None,
                    'unguided': int(s.unguided.sum()) if s is not None and s.unguided is not None else 0,
                })
            strokes = [{'id': s.id, 'region': s.region,
                        'pts': np.round(s.pts, 1).ravel().tolist()} for s in self.strokes]
            dividers = [{'id': d.id, 'pts': np.round(d.pts, 1).ravel().tolist()} for d in self.dividers]
            L = self._seg_last
            cycle = None
            if L and L['epoch'] == self._epoch:
                cycle = {'region': L['rid'], 'k': L['k'], 'n': len(L['cands']), 'subtract': L['subtract'],
                         'pt': L['pt'], 'click': L['click']}
            return {'id': self.id, 'name': self.name, 'path': self.path, 'width': self.w, 'height': self.h,
                    'course_step': self.course_step, 'regions': regions, 'strokes': strokes, 'dividers': dividers,
                    'has_depth': self._disparity is not None, 'color_exclude': self.color_exclude,
                    'can_undo': bool(self._undo), 'can_redo': bool(self._redo), 'dirty': self.dirty,
                    'unsaved_guides': self.unsaved_guides(),
                    'coverage_v': self._coverage_key()[1], 'segment_cycle': cycle,
                    'has_sparkle_layer': self.sparkle is not None,
                    'sam': {'state': self.sam_state, 'error': self.sam_error}}

    # ---------------------------------------------------------------- coverage

    def _coverage_key(self):
        key = tuple((r.id, r.mask_v) for r in self.regions) + (('exclude', self.color_exclude),)
        return key, hashlib.blake2b(repr(key).encode(), digest_size=6).hexdigest()

    def _stock(self, REG):
        """(stock, alpha) of coverage.stocking_coverage for the region map REG of the current masks, cached."""
        key, v = self._coverage_key()
        if self._cov_key != key:
            if self._lab is None:
                self._lab = coverage.lab_of(self.art)
            stock, alpha = coverage.stocking_coverage(self._lab, REG, exclude=self.color_exclude)
            stats = []
            for i, r in enumerate(self.regions, 1):
                n = int((REG == i).sum())
                k = int(((REG == i) & stock).sum())
                stats.append({'id': r.id, 'pixels': n, 'covered': k})
            self._cov, self._cov_key = (stock, alpha, stats, v), key
        return self._cov

    def coverage(self):
        """(stock bool mask, alpha float32, per-region stats, version) for the current regions, cached until a
        mask changes."""
        with self.lock:
            REG, _ = self._prepare()
            return self._stock(REG)

    def coverage_png(self):
        stock = self.coverage()[0]
        a = np.where(stock, 255, 0).astype(np.uint8)
        ok, buf = cv2.imencode('.png', np.dstack([a, a, a, a]), [cv2.IMWRITE_PNG_COMPRESSION, 1])
        return buf.tobytes()

    def courses(self, rid):
        with self.lock:
            _, prep = self._prepare()
            s = self._shown(rid, prep.get(rid))
            if s is None:
                return {'version': 0, 'courses': [], 'wales': [], 'walls': []}
            return {'version': s.version, 'courses': s.courses, 'wales': s.wales, 'walls': s.walls}

    def art_png(self):
        with self.lock:
            if self._art_png is None:
                ok, buf = cv2.imencode('.png', cv2.cvtColor(self.art, cv2.COLOR_RGB2BGR),
                                       [cv2.IMWRITE_PNG_COMPRESSION, 1])
                self._art_png = buf.tobytes()
            return self._art_png

    def mask_png(self, rid):
        """White where the region is painted, transparent elsewhere; the UI tints it."""
        with self.lock:
            m = self.region(rid).mask
            a = np.where(m, 255, 0).astype(np.uint8)
        ok, buf = cv2.imencode('.png', np.dstack([a, a, a, a]), [cv2.IMWRITE_PNG_COMPRESSION, 1])
        return buf.tobytes()

    def stroke_alpha(self):
        """All strokes rasterised as the solver sees them: each clipped to the region it belongs to."""
        with self.lock:
            REG, prep = self._prepare()
            out = np.zeros((self.h, self.w), np.uint8)
            for r in self.regions:
                inp = prep.get(r.id)
                if inp is None:
                    continue
                y0, y1, x0, x1 = inp.box
                out[y0:y1, x0:x1][inp.mc] = np.maximum(out[y0:y1, x0:x1][inp.mc], inp.alpha[inp.mc])
            return out

    def divider_alpha(self):
        """The user's 隔开 lines drawn 3 px wide (255), for the guides PSD; None when there are none."""
        with self.lock:
            if not self.dividers:
                return None
            return trace.draw_lines([d.pts for d in self.dividers], (self.h, self.w), Divider.WIDTH)

    def region_map(self):
        """Region index per pixel (1..n by list position, 0 = none) for every painted region, solved or not."""
        with self.lock:
            return self._prepare()[0].copy()

    def cut_map(self):
        """Full-image bool: the bands along walls where the current solves' fields jump (see gf.wall_cut)."""
        with self.lock:
            _, prep = self._prepare()
            out = np.zeros((self.h, self.w), bool)
            for r in self.regions:
                inp = prep.get(r.id)
                s = self._solve_for(r.id, inp) if inp is not None else None
                if s is not None and s.cut is not None:
                    y0, y1, x0, x1 = inp.box
                    out[y0:y1, x0:x1] |= s.cut & inp.mc
            return out

    def filled_map(self):
        """{region index (1..n by list position): bool mask} of what the solver filled in beside each region with a
        current solve (guide_fields.fill_occlusions: a ribbon, a hand, a band of hair across a limb, which the courses
        run on under), where no painted region is, less the bands along its walls. It says which pieces of a region
        the stockings run on between (Scene: the 油光's glints are one across it); it is no stocking itself."""
        with self.lock:
            REG, prep = self._prepare()
            out = {}
            for i, r in enumerate(self.regions, 1):
                inp = prep.get(r.id)
                s = self._solve_for(r.id, inp) if inp is not None else None
                if s is None or s.fields is None:
                    continue
                y0, y1, x0, x1 = inp.box
                gap = gf.fill_occlusions(inp.mc) & ~inp.mc & (REG[y0:y1, x0:x1] == 0)
                if s.cut is not None:
                    gap &= ~s.cut
                if gap.any():
                    out[i] = np.zeros((self.h, self.w), bool)
                    out[i][y0:y1, x0:x1] = gap
            return out

    def fields(self):
        """Full-image (REG, V, NX, NY, A) from the current solves, with solve_guides' conventions:
        REG = 1..n by list position, 0 where a region has no up-to-date solve."""
        with self.lock:
            REG, prep = self._prepare()
            REG = REG.copy()
            V, NX, NY, A = (np.zeros((self.h, self.w)) for _ in range(4))
            for r in self.regions:
                inp = prep.get(r.id)
                if inp is None:
                    continue
                s = self._solve_for(r.id, inp)
                y0, y1, x0, x1 = inp.box
                if s is None or s.fields is None:
                    REG[y0:y1, x0:x1][inp.mc] = 0
                    continue
                if s.unguided is not None:
                    REG[y0:y1, x0:x1][s.unguided] = 0
                for dst, src_ in zip((V, NX, NY, A), s.fields):
                    dst[y0:y1, x0:x1][inp.mc] = src_[inp.mc]
            return REG, V, NX, NY, A

    def unguided_map(self):
        """Full-image bool: pixels of current solves left untextured because their piece of the region has no
        stroke (see guide_fields.unguided_pieces)."""
        with self.lock:
            _, prep = self._prepare()
            out = np.zeros((self.h, self.w), bool)
            for r in self.regions:
                inp = prep.get(r.id)
                s = self._solve_for(r.id, inp) if inp is not None else None
                if s is not None and s.unguided is not None:
                    y0, y1, x0, x1 = inp.box
                    out[y0:y1, x0:x1] |= s.unguided
            return out

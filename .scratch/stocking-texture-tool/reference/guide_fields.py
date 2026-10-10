"""Rough regions + guide strokes -> course coordinates. Reference implementation for the stocking texture tool.

Verified on the Ganyu example guide PSD (see ../spec.md, "Verified numbers"). Pure numpy/scipy/OpenCV/contourpy.

    REG, V, NX, NY, A = solve_guides(regions, stroke_alpha)

regions: list of HxW bool masks, one per body part (left thigh, right thigh, ...). Overlaps go to the later mask.
stroke_alpha: HxW uint8, the guide-stroke layer's alpha (any colour). Each connected stroke is one course.
REG: int8 region index 1..n (0 = none). V: px along the surface, constant along a course, calibrated so that
|grad V| = 1 where the strokes are at their median spacing (strokes crowding together = perspective, carried into V).
NX, NY: unit course normal (direction of increasing V). A: px of arc length along each course, 0 on the region's
medial line, increasing along the tangent (-NY, NX).

Courses for a renderer: phi = V / period. Wales: u = A / (period * wale_ratio). Tilted single-line family with a
mirrored angle for a left/right pair: cos(theta) * V / period + sin(+-theta) * A / period.
"""
import contourpy
import cv2
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

SC = 4             # solve on a 1/SC grid; fields are smooth, full-res solves are 16x the work for nothing
MIN_STROKE_PX = 30


def keep_major_parts(mask, min_frac=0.02, connectivity=8):
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity)
    if n <= 1:
        return mask.astype(bool)
    big = st[1:, 4].max()
    return np.isin(lab, [i for i in range(1, n) if st[i, 4] >= min_frac * big])


def centre_lines(stroke_alpha, region):
    """Each stroke inside `region` as a smoothed centre-line polyline (N, 2) in xy.

    A stroke is several px thick; pinning that whole band would pin a range of values and bend the field around it.
    """
    m = (stroke_alpha > 64) & region
    n, lab = cv2.connectedComponents(m.astype(np.uint8), connectivity=8)
    out = []
    for i in range(1, n):
        ys, xs = np.nonzero(lab == i)
        if len(xs) < MIN_STROKE_PX:
            continue
        P = np.stack([xs, ys], 1).astype(float)
        c = P.mean(0)
        e = np.linalg.eigh((P - c).T @ (P - c))[1][:, -1]
        e = e if e[0] >= 0 else -e
        bins = np.round((P - c) @ e).astype(int)
        u = np.unique(bins)
        Q = np.stack([[P[bins == b, 0].mean() for b in u], [P[bins == b, 1].mean() for b in u]], 1)
        Q = np.stack([ndi.gaussian_filter1d(Q[:, 0], 3, mode='nearest'),
                      ndi.gaussian_filter1d(Q[:, 1], 3, mode='nearest')], 1)
        out.append(Q)
    return out


class Grid:
    """A region on the 1/SC grid with forward-difference operators and natural (free) boundaries."""

    def __init__(self, region, h, w):
        self.h, self.w = h, w
        self.hs, self.ws = h // SC, w // SC
        reg = cv2.resize(region.astype(np.uint8), (self.ws, self.hs), interpolation=cv2.INTER_NEAREST) > 0
        # 4-connected pieces only: a piece linked by a diagonal alone gets no difference equation to the rest,
        # its values float freely and the solve goes singular (NaN everywhere)
        self.reg = keep_major_parts(reg, connectivity=4)
        self.idx = -np.ones((self.hs, self.ws), np.int64)
        self.n = int(self.reg.sum())
        self.idx[self.reg] = np.arange(self.n)
        self.Dx, self.ax = self._diff(0, 1)
        self.Dy, self.ay = self._diff(1, 0)
        self.L = (self.Dx.T @ self.Dx + self.Dy.T @ self.Dy).tocsr()

    def _diff(self, dy, dx):
        r = self.reg
        a = r[:self.hs - dy, :self.ws - dx] & r[dy:, dx:]
        i = self.idx[:self.hs - dy, :self.ws - dx][a]
        j = self.idx[dy:, dx:][a]
        k = len(i)
        R = np.arange(k)
        return sp.csr_matrix((np.r_[-np.ones(k), np.ones(k)], (np.r_[R, R], np.r_[i, j])), shape=(k, self.n)), a

    def edge(self, f, dy, dx):
        a = self.ax if (dy, dx) == (0, 1) else self.ay
        return 0.5 * (f[:self.hs - dy, :self.ws - dx] + f[dy:, dx:])[a]

    def rows(self, pts):
        xi = np.clip((pts[:, 0] / SC).astype(int), 0, self.ws - 1)
        yi = np.clip((pts[:, 1] / SC).astype(int), 0, self.hs - 1)
        k = self.idx[yi, xi]
        return k[k >= 0], k >= 0

    def interp(self, pts, vals, w_fix=10.0):
        """Laplace-smooth field through scattered samples (one column per channel)."""
        k, ok = self.rows(pts)
        F = sp.csr_matrix((np.ones(len(k)), (np.arange(len(k)), k)), shape=(len(k), self.n))
        solve = spla.factorized((self.L + w_fix * F.T @ F + 1e-6 * sp.eye(self.n)).tocsc())
        V = np.atleast_2d(np.asarray(vals).T).T[ok]
        out = []
        for c in range(V.shape[1]):
            f = np.zeros((self.hs, self.ws))
            f[self.reg] = solve(w_fix * (F.T @ V[:, c]))
            out.append(f)
        return np.stack(out, -1)

    def up(self, f):
        return cv2.resize(f, (self.w, self.h), interpolation=cv2.INTER_LINEAR)


def solve_v(region, stroke_alpha):
    """Course coordinate V for one region. Returns (V, NX, NY) at full resolution, or None without strokes."""
    h, w = region.shape
    G = Grid(region, h, w)
    lines = centre_lines(stroke_alpha, region)
    if not lines:
        return None
    # 1. course direction: doubled-angle tangents interpolated smoothly (stroke direction sign is meaningless)
    pts = np.concatenate(lines)
    tans = []
    for Q in lines:
        T = np.gradient(Q, axis=0)
        tans.append(T / (np.linalg.norm(T, axis=1, keepdims=True) + 1e-9))
    T = np.concatenate(tans)
    ang = np.arctan2(T[:, 1], T[:, 0])
    dd = G.interp(pts, np.stack([np.cos(2 * ang), np.sin(2 * ang)], 1))
    a = 0.5 * np.arctan2(dd[..., 1], dd[..., 0])
    nx, ny = -np.sin(a), np.cos(a)
    # orient the normal the way the strokes are stacked (first -> last), or downward for a single stroke
    cen = np.array([Q.mean(0) for Q in lines])
    if len(lines) > 1:
        mn = np.array([nx[G.reg].mean(), ny[G.reg].mean()])
        order = np.argsort(cen @ mn)
        lines, cen = [lines[i] for i in order], cen[order]
        ref = cen[-1] - cen[0]
    else:
        ref = np.array([0.0, 1.0])
    flip = (nx * ref[0] + ny * ref[1]) < 0
    nx, ny = np.where(flip, -nx, nx), np.where(flip, -ny, ny)
    # 2. course density rho (strokes per px) from each pair of neighbouring strokes, interpolated in log space
    rp, rv = [], []
    for A_, B_ in zip(lines[:-1], lines[1:]):
        for S, T_ in ((A_, B_), (B_, A_)):
            target = np.ones((h, w), bool)
            ti = np.clip(np.round(T_).astype(int), 0, [w - 1, h - 1])
            target[ti[:, 1], ti[:, 0]] = False
            dt = ndi.distance_transform_edt(target)
            si = np.clip(np.round(S).astype(int), 0, [w - 1, h - 1])
            rp.append(S)
            rv.append(1.0 / np.maximum(dt[si[:, 1], si[:, 0]], 1.0))
    if rp:
        rho = np.exp(G.interp(np.concatenate(rp), np.log(np.concatenate(rv))[:, None])[..., 0])
        gap = float(np.median(1.0 / np.concatenate(rv)))
    else:
        rho, gap = np.full((G.hs, G.ws), 1.0 / 60), 60.0
    # 3. phase: least squares grad(phi) = rho * n, pinned on the first stroke. Its gradient is held to a sane size
    # everywhere, so it cannot fold or go flat the way interpolating V values directly does.
    nxs = cv2.resize(nx, (G.ws, G.hs), interpolation=cv2.INTER_AREA)
    nys = cv2.resize(ny, (G.ws, G.hs), interpolation=cv2.INTER_AREA)
    gx = G.edge(rho * nxs, 0, 1) * SC
    gy = G.edge(rho * nys, 1, 0) * SC
    k, _ = G.rows(lines[0])
    F = sp.csr_matrix((np.ones(len(k)), (np.arange(len(k)), k)), shape=(len(k), G.n))
    A = (G.L + 10.0 * F.T @ F + 1e-6 * sp.eye(G.n)).tocsc()
    phi = np.zeros((G.hs, G.ws))
    phi[G.reg] = spla.spsolve(A, G.Dx.T @ gx + G.Dy.T @ gy)
    nx_f, ny_f = G.up(nx), G.up(ny)
    nn = np.hypot(nx_f, ny_f) + 1e-9
    return G.up(phi) * gap, nx_f / nn, ny_f / nn


def solve_across(region, V, NX, NY, step=2.0, medial_sigma=12, post_sigma=2.0):
    """Arc length along the courses, 0 on a smooth medial line.

    Sample V's iso-lines every `step` px, measure arc length along each from its medial point, then fill pixels from
    the nearest sample plus a first-order step along the tangent, and smooth lightly inside the region. The medial
    point is each course's arc-length midpoint, smoothed across courses: the distance-transform maximum jumps between
    ridges from one course to the next, and every jump shows as a band of crowded wales. Integrating the tangent
    field by least squares instead is inexact (the field is not a gradient) and shows as wavy wales.
    """
    h, w = region.shape
    inner = region & np.isfinite(V)
    vin = V[inner]
    levels = np.arange(np.percentile(vin, 0.5), np.percentile(vin, 99.5), step)
    gen = contourpy.contour_generator(z=np.ma.array(np.where(inner, V, 0.0), mask=~inner))
    courses, medial = [], []
    for lv in levels:
        segs = [s for s in gen.lines(lv) if len(s) >= 5]
        if not segs:
            continue
        P = max(segs, key=len)
        mid = P[len(P) // 2]
        my, mx = min(int(mid[1]), h - 1), min(int(mid[0]), w - 1)
        t = np.array([-NY[my, mx], NX[my, mx]])
        if (P[-1] - P[0]) @ t < 0:
            P = P[::-1]
        seg = np.diff(P, axis=0)
        s = np.r_[0, np.cumsum(np.hypot(seg[:, 0], seg[:, 1]))]
        k = int(np.searchsorted(s, s[-1] / 2))
        courses.append((P, s))
        medial.append(P[min(k, len(P) - 1)])
    if not courses:
        return np.zeros((h, w))
    medial = np.array(medial)
    medial = np.stack([ndi.gaussian_filter1d(medial[:, 0], medial_sigma, mode='nearest'),
                       ndi.gaussian_filter1d(medial[:, 1], medial_sigma, mode='nearest')], 1)
    sx, sy, sa, stx, sty = [], [], [], [], []
    for (P, s), m0 in zip(courses, medial):
        s0 = s[int(np.argmin(np.hypot(*(P - m0).T)))]
        T = np.gradient(P, axis=0)
        T /= np.linalg.norm(T, axis=1, keepdims=True) + 1e-9
        sx.append(P[:, 0]); sy.append(P[:, 1]); sa.append(s - s0); stx.append(T[:, 0]); sty.append(T[:, 1])
    sx, sy, sa, stx, sty = map(np.concatenate, (sx, sy, sa, stx, sty))
    tree = cKDTree(np.stack([sx, sy], 1))
    ys, xs = np.nonzero(region)
    _, q = tree.query(np.stack([xs, ys], 1).astype(float), workers=-1)
    A = np.zeros((h, w))
    A[ys, xs] = sa[q] + (xs - sx[q]) * stx[q] + (ys - sy[q]) * sty[q]
    if post_sigma:
        m = region.astype(np.float64)
        A = cv2.GaussianBlur(A * m, (0, 0), post_sigma) / np.maximum(cv2.GaussianBlur(m, (0, 0), post_sigma), 1e-6)
        A[~region] = 0
    return A


def solve_guides(regions, stroke_alpha, margin=8):
    """Solve every region inside its own bounding box; full-image solves spend most of their time on empty pixels."""
    h, w = stroke_alpha.shape
    REG = np.zeros((h, w), np.int8)
    for i, m in enumerate(regions, 1):
        REG[keep_major_parts(m)] = i
    V = np.zeros((h, w)); NX = np.zeros((h, w)); NY = np.zeros((h, w)); A = np.zeros((h, w))
    for i in range(1, len(regions) + 1):
        m = REG == i
        if not m.any():
            continue
        ys, xs = np.nonzero(m)
        y0, y1 = max(ys.min() - margin, 0), min(ys.max() + margin + 1, h)
        x0, x1 = max(xs.min() - margin, 0), min(xs.max() + margin + 1, w)
        mc = m[y0:y1, x0:x1]
        res = solve_v(mc, stroke_alpha[y0:y1, x0:x1])
        if res is None:
            REG[m] = 0          # no stroke in this region: leave it untextured, and let the UI say so
            continue
        v, nx, ny = res
        a = solve_across(mc, np.where(mc, v, np.nan), nx, ny)
        crop = (slice(y0, y1), slice(x0, x1))
        for dst, src_ in ((V, v), (NX, nx), (NY, ny), (A, a)):
            dst[crop][mc] = src_[mc]
    return REG, V, NX, NY, A

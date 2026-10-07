"""Rough regions + guide strokes -> course coordinates. Reference implementation for the stocking texture tool.

Verified on the sample guides PSD (tests/verify.py, tests/test_document.py). Pure numpy/scipy/OpenCV/contourpy.

    REG, V, NX, NY, A = solve_guides(regions, stroke_alpha)

regions: list of HxW bool masks, one per body part (left thigh, right thigh, ...). Overlaps go to the later mask.
stroke_alpha: HxW uint8, the guide-stroke layer's alpha (any colour). Each connected stroke is one course.
REG: int8 region index 1..n (0 = none). V: px along the surface normal to the courses, |grad V| = 1 everywhere: the
strokes only set which way the courses run, never how dense they are (unlike the reference, where strokes crowding
together meant perspective and was carried into V).
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
    """A region on the 1/SC grid with forward-difference operators and natural (free) boundaries.

    cut: walls (see walls.find_walls), full resolution: the cells they touch are left out, a slit nothing is
    smoothed across, so the fields flow round its ends instead (a calf folded behind its thigh)."""

    def __init__(self, region, h, w, cut=None):
        self.h, self.w = h, w
        self.hs, self.ws = h // SC, w // SC
        reg = cv2.resize(region.astype(np.uint8), (self.ws, self.hs), interpolation=cv2.INTER_NEAREST) > 0
        if cut is not None and cut.any():
            reg &= ~(cv2.resize(cut.astype(np.float32), (self.ws, self.hs), interpolation=cv2.INTER_AREA) > 0)
        # 4-connected pieces only: a piece linked by a diagonal alone gets no difference equation to the rest,
        # its values float freely and the solve goes singular (NaN everywhere)
        self._build(keep_major_parts(reg, connectivity=4))

    def _build(self, reg):
        self.reg = reg
        self.idx = -np.ones((self.hs, self.ws), np.int64)
        self.n = int(self.reg.sum())
        self.idx[self.reg] = np.arange(self.n)
        self.Dx, self.ax, px = self._diff(0, 1)
        self.Dy, self.ay, py = self._diff(1, 0)
        self.pairs = tuple(np.r_[a, b] for a, b in zip(px, py))
        self.L = (self.Dx.T @ self.Dx + self.Dy.T @ self.Dy).tocsr()
        self.__dict__.pop('_near', None)

    def keep_pieces_with(self, pts):
        """Drop the 4-connected pieces of the grid that none of pts (xy, image px) falls in."""
        n, lab = cv2.connectedComponents(self.reg.astype(np.uint8), connectivity=4)
        if n <= 2:
            return
        xi = np.clip((pts[:, 0] / SC).astype(int), 0, self.ws - 1)
        yi = np.clip((pts[:, 1] / SC).astype(int), 0, self.hs - 1)
        hit = np.unique(lab[yi, xi])
        keep = np.isin(lab, hit[hit > 0])
        if (keep != self.reg).any():
            self._build(keep)

    def _diff(self, dy, dx):
        r = self.reg
        a = r[:self.hs - dy, :self.ws - dx] & r[dy:, dx:]
        i = self.idx[:self.hs - dy, :self.ws - dx][a]
        j = self.idx[dy:, dx:][a]
        k = len(i)
        R = np.arange(k)
        M = sp.csr_matrix((np.r_[-np.ones(k), np.ones(k)], (np.r_[R, R], np.r_[i, j])), shape=(k, self.n))
        return M, a, (i, j)

    def orient(self, nx, ny, seeds):
        """Signs (+1/-1 per cell, on the 1/SC grid) that make an unoriented normal field (nx, ny: hs x ws, sign
        meaningless) agree between neighbouring cells. Propagated breadth-first from each seed (cell, (dx, dy)) in
        turn, the seed's normal turned toward its (dx, dy); each piece of the grid takes its first seed. One sign
        for the whole field (the old way) cannot follow a leg bent double: along the thigh the courses' normal
        points to the knee, along the calf away from it."""
        from scipy.sparse.csgraph import breadth_first_order
        i, j = self.pairs
        adj = sp.csr_matrix((np.ones(len(i)), (i, j)), shape=(self.n, self.n))
        adj = (adj + adj.T).tocsr()
        vx, vy = nx[self.reg].tolist(), ny[self.reg].tolist()
        sign = [0] * self.n
        for s, (dx, dy) in seeds:
            if s < 0 or sign[s]:
                continue
            order, pred = breadth_first_order(adj, s, directed=False, return_predecessors=True)
            sign[s] = 1 if vx[s] * dx + vy[s] * dy >= 0 else -1
            pred = pred.tolist()
            for c in order[1:].tolist():
                p = pred[c]
                sign[c] = sign[p] if vx[c] * vx[p] + vy[c] * vy[p] >= 0 else -sign[p]
        out = np.ones((self.hs, self.ws))
        out[self.reg] = [v or 1 for v in sign]
        return out

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
        """Full-resolution field, with the cells outside the region first filled from their nearest inside cell:
        left at zero they would blend into the region's edge pixels and give them bogus values (on a region a
        hundred px across, the iso-lines running along that rim outgrow the real courses)."""
        if not hasattr(self, '_near'):
            self._near = ndi.distance_transform_edt(~self.reg, return_distances=False, return_indices=True)
        f = f[tuple(self._near)]
        return cv2.resize(f, (self.w, self.h), interpolation=cv2.INTER_LINEAR)


def unguided_pieces(region, lines):
    """The pieces of `region` (8-connected) that no stroke runs through: nothing says which way their courses run or
    how dense they are, so they get no texture (a leg cut in two by the other leg in front needs a stroke on each
    piece). lines: centre_lines() of the region."""
    n, lab = cv2.connectedComponents(region.astype(np.uint8), connectivity=8)
    if n <= 2 or not lines:
        return np.zeros(region.shape, bool) if lines else region.copy()
    h, w = region.shape
    P = np.round(np.concatenate(lines)).astype(int)
    hit = np.unique(lab[np.clip(P[:, 1], 0, h - 1), np.clip(P[:, 0], 0, w - 1)])
    return region & ~np.isin(lab, hit[hit > 0])


def solve_v(region, stroke_alpha, walls=None):
    """Course coordinate V for one region. Returns (V, NX, NY) at full resolution, or None without strokes.
    V is NaN on unguided_pieces().

    The strokes only say which way the courses run; however many there are and however they crowd, the courses are
    spaced evenly: V is px along the surface normal to them, |grad V| ~ 1 everywhere. walls: see Grid.
    """
    h, w = region.shape
    G = Grid(region, h, w, cut=walls)
    lines = centre_lines(stroke_alpha, region)
    if not lines:
        return None
    # a piece of the grid with no stroke would interpolate direction from nothing, and solve_across would trace
    # every course of the wild V that comes out there
    G.keep_pieces_with(np.concatenate(lines))
    unguided = unguided_pieces(region, lines)
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
    # orient the normal the way the strokes are stacked (first -> last), or downward for a single stroke, carried
    # along the region from the first stroke so it stays one way round a bend
    cen = np.array([Q.mean(0) for Q in lines])
    if len(lines) > 1:
        mn = np.array([nx[G.reg].mean(), ny[G.reg].mean()])
        order = np.argsort(cen @ mn)
        lines, cen = [lines[i] for i in order], cen[order]
        ref = cen[-1] - cen[0]
    else:
        ref = np.array([0.0, 1.0])
    seeds = []
    for Q in lines:
        # the stroke's point nearest its middle that lies on the grid (not in a wall's slit)
        k, ok = G.rows(Q[np.argsort(np.abs(np.arange(len(Q)) - len(Q) // 2))])
        if len(k):
            seeds.append((int(k[0]), ref))
    sign = G.orient(nx, ny, seeds)
    nx, ny = nx * sign, ny * sign
    # 2. phase: least squares grad(V) = n, its free constant fixed by holding the first stroke's mean at 0.
    # Its gradient is held to a sane size everywhere, so it cannot fold or go flat the way interpolating V values
    # directly does. Pinning every cell the stroke touches instead flattens V across the staircase of cells a
    # slanted or curved stroke covers, and one course along that stroke comes out about twice as wide (a seam).
    nxs = cv2.resize(nx, (G.ws, G.hs), interpolation=cv2.INTER_AREA)
    nys = cv2.resize(ny, (G.ws, G.hs), interpolation=cv2.INTER_AREA)
    k, _ = G.rows(lines[0])
    k = np.unique(k)
    F = sp.csr_matrix((np.full(len(k), 1.0 / len(k)), (np.zeros(len(k), int), k)), shape=(1, G.n))
    gx = G.edge(nxs, 0, 1) * SC
    gy = G.edge(nys, 1, 0) * SC
    phi = np.zeros((G.hs, G.ws))
    phi[G.reg] = spla.spsolve((G.L + 10.0 * F.T @ F + 1e-6 * sp.eye(G.n)).tocsc(), G.Dx.T @ gx + G.Dy.T @ gy)
    V = G.up(phi)
    V[unguided] = np.nan
    nx_f, ny_f = G.up(nx), G.up(ny)
    nn = np.hypot(nx_f, ny_f) + 1e-9
    return V, nx_f / nn, ny_f / nn


def solve_across(region, V, NX, NY, step=2.0, medial_sigma=12, post_sigma=2.0, cut=None):
    """Arc length along the courses, 0 on a smooth medial line.

    Sample V's iso-lines every `step` px, measure arc length along each (every piece of each: a wall or a notch may
    split a level into several courses), and choose each course's offset so that neighbouring courses agree, with a
    weak pull toward each whole course's midpoint (see below); then fill pixels from the nearest sample plus a
    first-order step along the tangent, and smooth lightly inside the region. Midpoints, not the distance-transform
    maximum: that jumps between ridges from one course to the next, and every jump shows as a band of crowded
    wales. Integrating the tangent field by least squares instead is inexact (the field is not a gradient) and shows
    as wavy wales.

    Courses cut short by an end of the region (its outline there runs along the courses: a leg leaving the frame at
    a slant), or by a wall, do not cross the whole width, so their midpoints slide sideways and bent the wales in a
    band at that end. They pull toward no midpoint and take their offsets from their neighbours.

    cut: wall_cut() of the region's walls, where V jumps from one side to the other: no course is traced along it.
    """
    h, w = region.shape
    inner = region & np.isfinite(V)
    if cut is not None:
        inner &= ~cut
    vin = V[inner]
    levels = np.arange(np.percentile(vin, 0.5), np.percentile(vin, 99.5), step)
    gen = contourpy.contour_generator(z=np.ma.array(np.where(inner, V, 0.0), mask=~inner))
    # outline normals, with the array's own edges counting as outline (a region cut by the image frame)
    pad = 8
    soft = cv2.GaussianBlur(np.pad(region, pad).astype(np.float32), (0, 0), 3)
    by, bx = (g[pad:-pad, pad:-pad] for g in np.gradient(soft))

    def cut_short(p, t):
        """The course ends at p where the outline faces along the course's normal, not along the course."""
        x, y = int(np.clip(round(p[0]), 0, w - 1)), int(np.clip(round(p[1]), 0, h - 1))
        g = np.array([bx[y, x], by[y, x]])
        n = np.hypot(*g)
        if n < 1e-6:
            return False
        g /= n
        return abs(g @ t) < abs(g[0] * -t[1] + g[1] * t[0])

    near_cut = None if cut is None else cv2.dilate(cut.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    # every piece of every course: where a wall (or a notch in the outline) splits a level, each piece is a course
    # of its own. Keeping only the longest left the rest to borrow arc lengths from courses beyond the wall.
    courses, lev, whole, mid, walled = [], [], [], [], []
    for li, lv in enumerate(levels):
        for P in gen.lines(lv):
            if len(P) < 5:
                continue
            # run each course the way the tangent field points, judged along its whole length: its two ends alone
            # (or the tangent at one point) say little about a course that bends
            xi = np.clip(P[:, 0].astype(int), 0, w - 1)
            yi = np.clip(P[:, 1].astype(int), 0, h - 1)
            if (np.diff(P, axis=0) * np.stack([-NY[yi, xi], NX[yi, xi]], 1)[:-1]).sum() < 0:
                P = P[::-1]
            seg = np.diff(P, axis=0)
            s = np.r_[0, np.cumsum(np.hypot(seg[:, 0], seg[:, 1]))]
            if s[-1] < 1.5 * step:
                continue
            courses.append((P, s))
            lev.append(li)
            mid.append(s[-1] / 2)
            # the course's direction from the solved field: the contour itself hooks in the last px before the
            # outline. A course ending at a wall is cut short too: the stretch behind carries on out of sight.
            ok, at_wall = True, False
            for q in (P[0], P[-1]):
                x, y = int(np.clip(round(q[0]), 0, w - 1)), int(np.clip(round(q[1]), 0, h - 1))
                if near_cut is not None and near_cut[y, x]:
                    ok, at_wall = False, True
                elif cut_short(q, np.array([-NY[y, x], NX[y, x]])):
                    ok = False
            whole.append(ok)
            walled.append(at_wall)
    if not courses:
        return np.zeros((h, w))
    n = len(courses)
    lev, whole, mid, walled = np.array(lev), np.array(whole), np.array(mid), np.array(walled)
    # each course's A is its arc length less an offset c, from one least-squares solve. Neighbouring courses (one
    # level and about `step` px apart) must agree where they pass each other: that keeps A smooth from course to
    # course. Each course also leans weakly toward a medial target: whole courses toward their midpoints smoothed
    # over about medial_sigma neighbouring courses; courses cut short by the outline (a leg leaving the frame at a
    # slant) toward that line carried straight on past the last whole courses; courses cut short by a wall toward
    # nothing (their neighbours give them their offsets, so their A runs on past their end). A family of courses
    # with no whole one at all leans on its own midpoints. The lean must stay weak: pinned hard, A stepped from
    # one course to the next wherever two neighbours' targets disagreed (where courses alternate whole and cut
    # short across a bent leg), and the 斜单线 lines and 针织 columns came out jagged in bands.
    lean = 2.0 / medial_sigma ** 2
    pts, sid, sarc, tan = [], [], [], []
    for j, (P, s) in enumerate(courses):
        T = np.gradient(P, axis=0)
        T /= np.linalg.norm(T, axis=1, keepdims=True) + 1e-9
        pts.append(P); sid.append(np.full(len(P), j)); sarc.append(s); tan.append(T)
    pts, sid, sarc, tan = map(np.concatenate, (pts, sid, sarc, tan))
    start = np.r_[0, np.cumsum([len(P) for P, _ in courses])]
    tree = cKDTree(pts)
    every = np.arange(0, len(pts), 3)
    dist, nb = tree.query(pts[every], k=12, distance_upper_bound=1.5 * step + 1.0, workers=-1)
    found = np.isfinite(dist)
    nb = np.where(found, nb, 0)
    nxt = found & (lev[sid[nb]] == lev[sid[every]][:, None] + 1)
    first = np.argmax(nxt, axis=1)
    has = nxt[np.arange(len(every)), first]
    p_i = every[has]
    q_i = nb[has, first[has]]
    a, b = sid[p_i], sid[q_i]
    rows = np.arange(len(p_i))
    # (s_a(p) - c_a) - (s_b(q) - c_b) = (p - q) . t
    rhs = np.einsum('ij,ij->i', pts[p_i] - pts[q_i], tan[p_i]) - sarc[p_i] + sarc[q_i]
    M = sp.csr_matrix((np.r_[-np.ones(len(rows)), np.ones(len(rows))], (np.r_[rows, rows], np.r_[a, b])),
                      shape=(len(rows), n))
    from scipy.sparse.csgraph import connected_components
    _, comp = connected_components(M.T @ M, directed=False)
    has_whole = np.zeros(comp.max() + 1, bool)
    has_whole[comp[whole]] = True
    npts = np.bincount(sid, minlength=n).astype(np.float64)
    target = mid.copy()
    wgt = np.where(has_whole[comp], 0.0, lean * npts / 3.0)
    wi = np.flatnonzero(whole)
    if len(wi):
        # midpoints of the whole courses, smoothed along their chain (graph Laplacian, std ~ medial_sigma courses)
        pos = np.full(n, -1)
        pos[wi] = np.arange(len(wi))
        e = (pos[a] >= 0) & (pos[b] >= 0)
        adj = sp.csr_matrix((np.ones(int(e.sum())), (pos[a[e]], pos[b[e]])), shape=(len(wi), len(wi)))
        adj = ((adj + adj.T) > 0).astype(np.float64)
        Lw = sp.diags(np.asarray(adj.sum(1)).ravel()) - adj
        mp = np.array([pts[start[j] + min(int(np.searchsorted(sarc[start[j]:start[j + 1]], mid[j])),
                                          start[j + 1] - start[j] - 1)] for j in wi])
        X = spla.spsolve((sp.eye(len(wi)) + 0.5 * medial_sigma ** 2 * Lw).tocsc(), mp)
        X = X.reshape(len(wi), 2)
        for k, j in enumerate(wi):
            P = pts[start[j]:start[j + 1]]
            i = int(np.argmin(np.hypot(*(P - X[k]).T)))
            target[j] = sarc[start[j] + i] + (X[k] - P[i]) @ tan[start[j] + i]
        wgt[wi] = lean * npts[wi] / 3.0
        # outline-cut courses: where the medial line, fitted over the nearest whole courses of the family and carried
        # straight on, crosses them
        for j in np.flatnonzero(~whole & ~walled & has_whole[comp]):
            cand = wi[comp[wi] == comp[j]]
            near = cand[np.argsort(np.abs(lev[cand] - lev[j]), kind='stable')[:medial_sigma]]
            Xn = X[pos[near]]
            if len(Xn) < 2:
                continue
            c0 = Xn.mean(0)
            dvec = np.linalg.eigh(np.cov((Xn - c0).T))[1][:, -1]
            P = pts[start[j]:start[j + 1]]
            dd = (P[:, 0] - c0[0]) * dvec[1] - (P[:, 1] - c0[1]) * dvec[0]
            sgn = np.flatnonzero(np.sign(dd[:-1]) != np.sign(dd[1:]))
            if not len(sgn):
                continue
            i = sgn[0]
            f = dd[i] / (dd[i] - dd[i + 1])
            target[j] = sarc[start[j] + i] + f * (sarc[start[j] + i + 1] - sarc[start[j] + i])
            wgt[j] = lean * npts[j] / 3.0
    lhs = (M.T @ M + sp.diags(wgt) + 1e-9 * sp.eye(n)).tocsc()
    c = spla.spsolve(lhs, M.T @ rhs + wgt * target)
    sa = sarc - c[sid]
    ys, xs = np.nonzero(region)
    _, q = tree.query(np.stack([xs, ys], 1).astype(float), workers=-1)
    A = np.zeros((h, w))
    A[ys, xs] = sa[q] + (xs - pts[q, 0]) * tan[q, 0] + (ys - pts[q, 1]) * tan[q, 1]
    if post_sigma:
        # smoothed on each side of a wall separately: A jumps across it
        keep = region if cut is None else region & ~cut
        m = keep.astype(np.float64)
        B = cv2.GaussianBlur(A * m, (0, 0), post_sigma) / np.maximum(cv2.GaussianBlur(m, (0, 0), post_sigma), 1e-6)
        A = np.where(keep, B, A)
        A[~region] = 0
    return A


def label_regions(regions, min_frac=0.02):
    """int8 region map 1..n from bool masks; overlaps go to the later mask, detached islands smaller than min_frac
    of the mask's largest piece are dropped (stray paint in a hand-painted mask; 0 keeps every piece)."""
    REG = np.zeros(regions[0].shape, np.int8)
    for i, m in enumerate(regions, 1):
        REG[keep_major_parts(m, min_frac) if min_frac > 0 else m.astype(bool)] = i
    return REG


def region_box(m, margin=8):
    """(y0, y1, x0, x1) bounding box of mask m plus margin, clipped to the image; None for an empty mask."""
    h, w = m.shape
    rows, cols = np.flatnonzero(m.any(1)), np.flatnonzero(m.any(0))
    if not len(rows):
        return None
    return (max(rows[0] - margin, 0), min(rows[-1] + margin + 1, h),
            max(cols[0] - margin, 0), min(cols[-1] + margin + 1, w))


def fill_occlusions(region, frac=0.5):
    """The region with what lies in front of it filled in: holes inside it (a hand on a thigh) and notches cut into
    its outline narrower than about frac x its width (strands of hair hanging over a leg, a hand over its edge).
    Where the region meets the array's edge (the image frame) it is taken to carry on outward, so notches open to
    the frame fill too. A morphological closing by a disk of radius frac x the region's half-width, done exactly
    with two distance transforms, then a hole fill. The stockings run on underneath an occluder, so the courses are
    solved on this and only used where the region shows."""
    m = region.astype(bool)
    if not m.any():
        return m
    half = float(cv2.distanceTransform(np.pad(m, 1).astype(np.uint8), cv2.DIST_L2, 5).max())
    r = frac * half
    if r < 2:
        return m
    pad = int(np.ceil(r)) + 2
    mp = np.pad(m, pad, mode='edge')
    grown = cv2.distanceTransform((~mp).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE) <= r
    closed = cv2.distanceTransform(np.pad(grown, 1, mode='edge').astype(np.uint8), cv2.DIST_L2,
                                   cv2.DIST_MASK_PRECISE)[1:-1, 1:-1] > r
    closed = ndi.binary_fill_holes(closed | mp)[pad:-pad, pad:-pad]
    return closed | m


def bridge_pieces(filled, guided):
    """filled plus a bridge to each piece of it that is not guided (no stroke runs through it): the piece and the
    stretch of guided area nearest it, as far again as the gap plus the piece's own thickness, wrapped in their
    convex hull. A leg the other leg crosses in front of carries on behind it this way, so its courses reach the
    piece beyond the crossing. A piece already guided, or a filled area with nothing guided, is left as it is."""
    out = filled.copy()
    if not guided.any():
        return out
    n, lab = cv2.connectedComponents((filled & ~guided).astype(np.uint8), connectivity=8)
    g = guided.astype(np.uint8)
    for k in range(1, n):
        piece = lab == k
        if (cv2.dilate(piece.astype(np.uint8), np.ones((3, 3), np.uint8)) & g).any():
            continue                                    # touches a guided part: same piece, not detached
        dist = cv2.distanceTransform((~piece).astype(np.uint8), cv2.DIST_L2, 5)
        gap = float(dist[guided].min())
        thick = 2 * float(cv2.distanceTransform(np.pad(piece, 1).astype(np.uint8), cv2.DIST_L2, 5).max())
        near = guided & (dist <= gap + max(thick, 8))
        ys, xs = np.nonzero(piece | near)
        hull = cv2.convexHull(np.stack([xs, ys], 1).astype(np.int32))
        mask = np.zeros(filled.shape, np.uint8)
        cv2.fillConvexPoly(mask, hull, 1)
        out |= mask.astype(bool)
    return out


def wall_cut(walls):
    """Full-resolution band of the grid cells walls take out of a solve (see Grid): where the fields jump from one
    side of the wall to the other. Nothing traces courses or draws iso-lines inside it."""
    h, w = walls.shape
    cells = cv2.resize(walls.astype(np.float32), (w // SC, h // SC), interpolation=cv2.INTER_AREA) > 0
    full = cv2.resize(cells.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)
    return cv2.dilate(full, np.ones((SC + 1, SC + 1), np.uint8)) > 0


def solve_region(mc, stroke_alpha_crop, walls=None, info=None):
    """One region inside its bounding-box crop: (V, NX, NY, A) on the crop, or None without strokes.

    Solved on fill_occlusions(mc), so courses (and a stroke drawn across a hand) run on under what lies in front of
    the stockings instead of bending around it, and with bridge_pieces, so a piece cut off by something wider (the
    other leg) and carrying no stroke of its own takes the courses of the rest carried on behind it. The fields
    cover that whole area; NaN only where nothing could be reached (see unguided_pieces).

    walls: bool crop (walls.find_walls), where one stretch of the region lies in front of another: the courses do
    not continue across them, and flow round their ends (a leg bent double is one region, seamless at the knee).
    info: a dict that, given, receives 'walls' (as carried through the filled-in area) and 'cut' (wall_cut)."""
    filled = fill_occlusions(mc)
    # strokes count only inside the filled area, and there only as the continuation of one that shows: a stroke
    # lying wholly in the filled-in part, or out in a bridge, belongs to whatever region is really there (the guide
    # layer is shared)
    on = (stroke_alpha_crop > 64) & filled
    n, lab = cv2.connectedComponents(on.astype(np.uint8), connectivity=8)
    seen = np.unique(lab[on & mc])
    keep = np.isin(lab, seen[seen > 0]) & on
    stroke_alpha_crop = np.where(keep, stroke_alpha_crop, 0).astype(stroke_alpha_crop.dtype)
    lines = centre_lines(stroke_alpha_crop, filled)
    if not lines:
        return None
    domain = bridge_pieces(filled, filled & ~unguided_pieces(filled, lines))
    shown, left_out = None, None
    if walls is not None and walls.any():
        from .walls import carry_through
        shown, left_out = walls, carry_through(walls, mc, domain)
    res = solve_v(domain, stroke_alpha_crop, left_out)
    if res is None:
        return None
    v, nx, ny = res
    cut = None if left_out is None else wall_cut(left_out)
    if info is not None:
        info.update(walls=shown, cut=cut)
    a = solve_across(domain, v, nx, ny, cut=cut)
    return v, nx, ny, a


def solve_guides(regions, stroke_alpha, margin=8):
    """Solve every region inside its own bounding box; full-image solves spend most of their time on empty pixels."""
    h, w = stroke_alpha.shape
    REG = label_regions(regions)
    V = np.zeros((h, w)); NX = np.zeros((h, w)); NY = np.zeros((h, w)); A = np.zeros((h, w))
    for i in range(1, len(regions) + 1):
        m = REG == i
        box = region_box(m, margin)
        if box is None:
            continue
        y0, y1, x0, x1 = box
        mc = m[y0:y1, x0:x1]
        res = solve_region(mc, stroke_alpha[y0:y1, x0:x1])
        if res is None:
            REG[m] = 0          # no stroke in this region: leave it untextured, and let the UI say so
            continue
        crop = (slice(y0, y1), slice(x0, x1))
        bare = np.isnan(res[0])
        REG[crop][mc & bare] = 0            # a detached piece with no stroke of its own
        for dst, src_ in zip((V, NX, NY, A), res):
            dst[crop][mc] = np.where(bare, 0, src_)[mc]
    return REG, V, NX, NY, A

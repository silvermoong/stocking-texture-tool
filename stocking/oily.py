"""油光 (oily), experimental: sheer glossy nylon, after photos of oily black stockings the user picked.

A faint grain and knit as the fabric; translucency (warm skin showing through where the surface faces the viewer,
denser and darker fabric toward the silhouette); a broad smooth sheen on the lit side and a darker shadow side; and
gloss lobes: a clean bright centre, the courses and grain showing through on their flanks, a long soft fall-off,
wider where the leg is thick or its lighting flat.

v7 finds the glints from a model of the limb and its lighting, never from local brightness ridges (v6 took the crest
of the painted brightness at a fixed small scale, so the strips of leg between the shadows hair casts, or a band's
lit edge, each made a glint of their own). Per region, split where a wall cuts it (each piece is one stretch of
stocking):

  frame    the limb's extent across (A) per narrow band along it (V), from the painted region (REG: hair the user
           painted over is part of the limb, though the colour test leaves it untextured); where the region's edge
           meets the image frame, another region or a wall the limb goes on out of sight, and that side is measured
           from the other -> centre c(V), half-width h(V), position across u = (A - c) / h in -1..1.
  facing   how squarely the surface faces the viewer, the piece taken as a surface of revolution about its length:
           sqrt(1 - u^2) across, times cos(tilt) along, where tan(tilt) = dh/dV, how fast the cross-section grows or
           shrinks (a leg barely tapers, tilt ~ 0; a breast closes toward both ends).
  lighting the light across the limb, read from how the visible stocking's brightness steps from cell to cell
           (A) within each narrow band of the courses (V): print running with the courses, stocking tops and light
           falling off along the limb are one level along a band and cancel exactly, however much of it trim or a
           hand hides. Medians per cell and band, so grain and marks drop out; the steps are smoothed at a fraction
           of the limb's width with a local plane (beside a gap the slope is not taken from one side only) and
           summed across. Light is read only from pixels wholly of stocking: the ring at the edge of what is visible
           (the outline, gold trim, hair) blends in whatever lies beyond it, often far brighter, and runs along the
           limb like a glint would.
  glints   every clear peak across the limb in that light (any number: a key and a rim light, or none on a flat or
           dark leg), linked along the limb into tracks. Shade only darkens, so peaks are those of the light's upper
           envelope at half the limb's half-width (a strip of light between two shadows, of hair, fingers, a hand,
           is no peak of the light falling on the limb), and a glint sits only where the painted light reaches that
           top, never in a dip the envelope filled. A peak counts by absolute, visible contrast (its prominence in
           luminance) and by sitting on the lit side of its region, so near-black or flat art gets none. A peak's
           position is known to within what the light's curvature allows against the fit's noise (a flat top: only
           to within its width), and tracks link and smooth their paths within that. A glint whose peak is missing
           where it would be out of sight (behind trim, a hand) goes on unseen and comes out as the same glint; one
           whose peak is missing in plain view has ended. How bright it is comes only from rows where the fit is
           sure of it. Along a track the strength follows the painted light against the track's brightest point, to
           the power SPEC_EXP (gloss falls off far faster than the diffuse light it sits on), so a glint runs as far
           as the artist's highlight does: on and on down an evenly lit leg, a short arc on a dome lit in one place.
           Its path is a smooth curve on screen through the rows' peaks.

tone (lit-side sheen, shadow-side sink) is the region's own range of smoothed brightness with a floor, so a flat
region is neutral rather than all shadow. Every map is whole-image and crops slice them (Scene.oily_maps), so a crop
renders exactly like the whole. v6 was accepted as 试验 (saved then as style 'p_oily'); v7 keeps its look and replaces how the glints are found.

    maps = oily_maps(src, R, alpha, A, V, scale, cut=cut, REG=REG)       # once per image, the whole image
    out = render_oily(src, R, V, A, alpha, g, s, *(m[sl] for m in maps), noise=(gn[sl], gc[sl]))
"""
import cv2
import numpy as np
from scipy import ndimage as ndi
from scipy.signal import find_peaks, peak_widths
from scipy.spatial import cKDTree

from . import knit

TONE_FLOOR = 0.06           # luminance: a region lit less unevenly than this is not stretched to full sheen and sink
PROM = (0.025, 0.08)        # luminance: a glint fades in as its lighting peak stands out across the limb by this much
LIT = (0.45, 0.85)          # where in the region's range of lighting a peak must sit: its lit side
CELLS = 20                  # cells across a typical half-width of the limb
LINK = 0.12                 # x the half-width: how far a peak may move from one row to the next and stay one glint
SHADE = 0.5                 # x the half-width: dips in the light across the limb narrower than this are shade
SURE = 0.3                  # support below which the fit only bridges a gap: a peak there is unsure of its light,
                            # and a peak missing there is no sign that the glint has ended
CLEAR = (8.0, 16.0)         # x the fit's noise: a peak must stand this clear of it (noise alone reaches ~10)
SPEC_EXP = 6                # gloss against diffuse: (light / light at the glint's brightest point) ^ SPEC_EXP
MIN_PIECE = 64              # px: smaller pieces get facing only


def luminance(src_bgr):
    """Rec. 709 luma of the painting, 0..1, per pixel (no blur, so nothing outside the stocking leaks in)."""
    b, g, r = (src_bgr[..., k].astype(np.float32) / 255 for k in range(3))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _masked_blur(f, m, sigma):
    mf = m.astype(np.float32)
    return cv2.GaussianBlur(f * mf, (0, 0), sigma) / np.maximum(cv2.GaussianBlur(mf, (0, 0), sigma), 1e-6)


def _footprint(f, same):
    gy, gx = np.gradient(f)
    return np.where(same, np.hypot(gx, gy), 0)


def _groups(key, val, n):
    """val sorted within each key 0..n-1: (sorted values, starts, ends)."""
    order = np.lexsort((val, key))
    ks = key[order]
    return val[order], np.searchsorted(ks, np.arange(n)), np.searchsorted(ks, np.arange(n), side='right')


def _quantile(vs, starts, ends, q, min_n=1):
    cnt = ends - starts
    out = np.full(len(starts), np.nan)
    ok = cnt >= min_n
    out[ok] = vs[starts[ok] + np.floor(q * (cnt[ok] - 1) + 0.5).astype(np.int64)]
    return out


def _fill(x, fallback=0.0):
    """NaNs filled by linear interpolation along the array (ends held)."""
    ok = np.isfinite(x)
    if not ok.any():
        return np.full(len(x), fallback, np.float64)
    i = np.arange(len(x))
    return np.interp(i, i[ok], x[ok])


def _frame(Vg, Ag, hidden, scale):
    """The limb's cross-section per band of V. Vg, Ag: the piece's painted pixels; hidden: those on an edge where
    the limb runs on out of sight (the image frame, another painted region in front of or beside it, a wall), so
    its extent there is unknown, not an outline.

    The painted region is the limb's shape: its outline is the silhouette (hair painted over is part of the limb;
    hair painted round is outline the user drew), so a knee or a waist keeps its narrowing. A side out of sight is
    measured from the other side, with the limb's width from complete cross-sections; with none anywhere, the edge
    is taken as the limb's middle (one side hidden) or no silhouette is seen at all (both sides hidden).
    Returns (band of each pixel, c, h, hf, typical half-width, tilt), per band: centre, half-width (the limb's size),
    half-width for facing (inf: no silhouette seen), and the surface's tilt along the limb."""
    bv = max(2.0, 2.0 * scale)
    k = np.floor((Vg - Vg.min()) / bv).astype(np.int64)
    n = int(k.max()) + 1
    vs, s, e = _groups(k, Ag, n)
    lo, hi = _fill(_quantile(vs, s, e, 0.02)), _fill(_quantile(vs, s, e, 0.98))
    lo_cut, hi_cut = np.zeros(n, bool), np.zeros(n, bool)
    if hidden.any():
        bmin, bmax = np.full(n, np.inf), np.full(n, -np.inf)
        np.minimum.at(bmin, k[hidden], Ag[hidden])
        np.maximum.at(bmax, k[hidden], Ag[hidden])
        lo_cut, hi_cut = bmin <= lo + 2 * bv, bmax >= hi - 2 * bv
    good = ~lo_cut & ~hi_cut
    half = (hi - lo) / 2
    hmed = max(float(np.median(half[good] if good.any() else half)), 2.0)
    one = lo_cut ^ hi_cut
    both = lo_cut & hi_cut
    if good.any():
        hmed = max(float(np.median(half[good])), 2.0)
        h = np.where(good, half, np.maximum(_fill(np.where(good, half, np.nan)), half))
        c = np.where(good, (hi + lo) / 2, np.where(lo_cut & ~hi_cut, hi - h, lo + h))
        c = np.where(both, _fill(np.where(both, np.nan, c)), c)
        hf = h.copy()
    else:
        h = half
        c = np.where(one, np.where(lo_cut, lo, hi), (hi + lo) / 2)
        hf = np.where(one, 2 * half, np.where(both, np.inf, half))
    win = max(3, int(round(hmed / bv)))
    c = ndi.gaussian_filter1d(c, win / 4, mode='nearest')
    h = np.maximum(ndi.gaussian_filter1d(h, win / 4, mode='nearest'), 1.0)
    seen_hf = np.isfinite(hf)
    hf = np.where(seen_hf, np.maximum(ndi.gaussian_filter1d(np.where(seen_hf, hf, h), win / 4, mode='nearest'), 1.0),
                  np.inf)
    # the surface's tilt along the limb: how fast its cross-section grows or shrinks, over about a half-width
    hs = ndi.gaussian_filter1d(h, win / 2, mode='nearest')
    tilt = np.arctan(np.gradient(hs, bv)) if n > 1 else np.zeros(n)
    tilt = np.where(seen_hf, tilt, 0.0)
    return k, c, h, hf, hmed, tilt


def _lighting(Y, Vv, Av, kv, nband, hmed, scale):
    """Smooth fit of the visible stocking's light over rows along the limb x cells of A across it. Cells are fixed in
    A (the solver's arc length across the courses), not relative to the visible width, so something in front of part
    of the limb cannot drag a glint sideways.

    The light across is read from how the brightness steps from each cell to the next within one band of the courses
    (kv, a couple of px of V): print running with the courses, a stocking top and light falling off along the limb
    are one level along a band and cancel in its steps exactly, however much of the band is hidden. The steps (median
    over a row's bands) are smoothed at a fraction of the limb's width (_local_linear: beside trim the light's slope
    is not taken from one side only, which would move its top) and summed across: the light across, up to a level per
    row that no peak depends on.
    Returns (fit: that light, each row's mean 0; absolute: brightness; support; row length; V of row 0; A of cell 0;
    cell width; noise: the fit's own noise, from how far the cells scatter about it, over the number of cells each
    point of the fit averages)."""
    v0 = Vv.min()
    # rows a quarter of the limb's width long, but no longer than 24 px (times scale): a broad dome still resolves
    # where its painted highlight ends
    wlen = min(max(hmed / 4, 3.0 * scale), 24.0 * scale)
    rf = (Vv - v0) / wlen
    row = np.floor(rf).astype(np.int64)
    nrow = int(row.max()) + 1
    ab = hmed / CELLS
    a0 = Av.min()
    cf = (Av - a0) / ab
    col = np.floor(cf).astype(np.int64)
    ncol = int(col.max()) + 1
    key = row * ncol + col
    sig = (2.0, 1.2)                     # rows: half the limb's width along it; cells: 6% of its half-width across

    def smooth(c, w):
        """Normalised Gaussian smoothing of the cell values c, each weighted by w: (values, support)."""
        d = ndi.gaussian_filter(w, sig, mode='nearest')
        return ndi.gaussian_filter(np.nan_to_num(c) * w, sig, mode='nearest') / np.maximum(d, 1e-6), d

    def weight(c, n, least):
        """A cell counts by how many values its median comes from, against a typical full cell."""
        n = n.astype(np.float64)
        full = float(np.median(n[n >= least])) if (n >= least).any() else 1.0
        return np.where(np.isfinite(c), np.clip(n / full, 0, 1), 0.0)

    vs, s, e = _groups(key, Y, nrow * ncol)
    absolute_c = _quantile(vs, s, e, 0.5, min_n=2).reshape(nrow, ncol)
    absolute, den = smooth(absolute_c, weight(absolute_c, (e - s).reshape(nrow, ncol), 2))

    # each band's median brightness per cell, and its step to the next cell along the same band
    bkey = kv.astype(np.int64) * ncol + col
    order = np.lexsort((Y, bkey))
    uk, first, n = np.unique(bkey[order], return_index=True, return_counts=True)
    med = Y[order][first + n // 2]
    nx = np.minimum(np.searchsorted(uk, uk + 1), len(uk) - 1)
    pair = (uk[nx] == uk + 1) & (uk % ncol < ncol - 1)
    step = med[nx[pair]] - med[pair]
    # a band's row: where its stocking lies on average
    rb = np.bincount(kv, rf, minlength=nband) / np.maximum(np.bincount(kv, minlength=nband), 1)
    rb = np.clip(np.floor(rb), 0, nrow - 1).astype(np.int64)
    vs, s, e = _groups(rb[uk[pair] // ncol] * ncol + uk[pair] % ncol, step, nrow * ncol)
    steps = _quantile(vs, s, e, 0.5).reshape(nrow, ncol)
    slope = _local_linear(steps, weight(steps, (e - s).reshape(nrow, ncol), 1), sig)[0]
    fit = np.concatenate([np.zeros((nrow, 1)), np.cumsum(slope[:, :-1], axis=1)], axis=1)
    fit -= ((fit * den).sum(1) / np.maximum(den.sum(1), 1e-9))[:, None]

    # the fit's noise: the cells' scatter about it, once each band's level is taken out
    light = ndi.map_coordinates(fit, np.stack([rf - 0.5, cf - 0.5]), order=1, mode='nearest')
    vs, s, e = _groups(kv, Y - light, nband)
    vs, s, e = _groups(key, Y - _fill(_quantile(vs, s, e, 0.5))[kv], nrow * ncol)
    rel_c = _quantile(vs, s, e, 0.5, min_n=2).reshape(nrow, ncol)
    ok = np.isfinite(rel_c)
    resid = np.abs(rel_c[ok] - fit[ok])
    noise = 1.4826 * float(np.median(resid)) / np.sqrt(4 * np.pi * sig[0] * sig[1]) if ok.any() else 0.0
    return fit, absolute, den, wlen, v0, a0, ab, noise


def _local_linear(c, w, sig, ridge=0.1):
    """Normalised Gaussian smoothing of the cells c (weights w) that fits a plane under the window rather than a
    level: where what is seen lies to one side (beside a gap, at an edge), a sloping field keeps its own value instead
    of taking that of the side seen. A slope the support is too narrow to tell shrinks toward a level (ridge, x the
    support). Returns (values, support)."""
    nr, nc = c.shape
    y, x = (g / sg for g, sg in zip(np.mgrid[0:nr, 0:nc].astype(np.float64), sig))     # in units of the window

    def g(f):
        return ndi.gaussian_filter(f, sig, mode='constant')

    v = np.nan_to_num(c) * w
    s0, sx, sy, sxx, sxy, syy = (g(w * m) for m in (1.0, x, y, x * x, x * y, y * y))
    t0, tx, ty = (g(v * m) for m in (1.0, x, y))
    # moments about each cell itself
    cx, cy = sx - x * s0, sy - y * s0
    cxx, cyy = sxx - 2 * x * sx + x * x * s0, syy - 2 * y * sy + y * y * s0
    cxy = sxy - x * sy - y * sx + x * y * s0
    tx, ty = tx - x * t0, ty - y * t0
    m = np.stack([np.stack([s0, cx, cy], -1), np.stack([cx, cxx + ridge * s0, cxy], -1),
                  np.stack([cy, cxy, cyy + ridge * s0], -1)], -2)
    m += 1e-9 * np.eye(3)
    return np.linalg.solve(m, np.stack([t0, tx, ty], -1)[..., None])[..., 0, 0], s0


def _envelope(f, reach):
    """f with every dip filled that has higher light within reach cells on both sides, up to the lower of the two:
    the light with shade (which only darkens) taken off, wherever it is narrower than 2 * reach. Only within f:
    past its ends nothing is known, so a fall toward an end is no dip."""
    n = len(f)
    left, right = f.copy(), f.copy()
    for d in range(1, min(reach, n - 1) + 1):
        left[d:] = np.maximum(left[d:], f[:-d])
        right[:-d] = np.maximum(right[:-d], f[d:])
    return np.maximum(f, np.minimum(left, right))


def _tracks(fit, absolute, den, noise, reach):
    """The light's peaks across the limb, row by row, linked along it: [(rows, cell, strength, width in cells,
    sureness, position known to within, in cells)], each track padded with a row past either end so it fades in and
    out. Sureness is the fit's support at the peak, 0 in rows the glint went on unseen. reach: rows a glint may stay
    out of sight (behind trim, a hand) and still be the same glint where it comes out.

    Shade only darkens: a strip of light between two shadows (hair, fingers, a hand's shadow, a dark print) is no
    peak of the light falling on the limb. So peaks are those of each row's envelope (_envelope, dips up to SHADE of
    the half-width filled), and a glint sits only where the painted light itself reaches that envelope's top: a
    measured point, never one inferred in a filled dip (two close lights of one height keep a glint each). A peak
    counts by its prominence in the envelope (luminance), by standing clear of the fit's own noise, and by where it
    sits in the range of the region's brightness. Along a track the strength follows the painted light against the
    track's brightest point."""
    sup = den > SURE
    lo, hi = (float(np.percentile(absolute[sup], v)) for v in (2, 98)) if sup.any() else (0.0, 1.0)
    shade = max(1, int(round(SHADE * CELLS / 2)))
    peaks = []
    for q in range(fit.shape[0]):
        found = []
        # what lies past the stocking seen is unknown, not dark. Narrow gaps (trim or hair cut out of it) the fit
        # bridges, more uncertain where fewer cells support it (local noise below); where support ends (the limb's
        # edge) the row ends, so a peak needs light falling off on both sides of it, and a rise into the edge (a
        # band seen at a slant, light bleeding in) is none
        ok = den[q] > 0.05
        edges = np.flatnonzero(np.diff(np.concatenate([[0], ok.astype(np.int8), [0]])))
        for r0, r1 in zip(edges[::2], edges[1::2]):
            if r1 - r0 < 5:
                continue
            f = fit[q, r0:r1]
            env = _envelope(f, shade)
            ie, pe = find_peaks(env, prominence=0.5 * PROM[0], plateau_size=1)
            if not len(ie):
                continue
            width = peak_widths(env, ie, rel_height=0.5,
                                prominence_data=(pe['prominences'], pe['left_bases'], pe['right_bases']))[0]
            jf, pf = find_peaks(f, plateau_size=1)
            for i in range(len(ie)):
                on = (jf >= pe['left_edges'][i]) & (jf <= pe['right_edges'][i]) & (f[jf] >= env[jf] - 1e-12)
                for j, size in zip(jf[on], pf['plateau_sizes'][on]):
                    cell = r0 + j
                    # the top between cells: a parabola through it and its neighbours
                    off = 0.0
                    d2 = f[j - 1] - 2 * f[j] + f[j + 1]
                    if size == 1 and d2 < 0:
                        off = float(np.clip(0.5 * (f[j - 1] - f[j + 1]) / d2, -0.5, 0.5))
                    lit = (absolute[q, cell] - lo) / max(hi - lo, 1e-6)
                    # the fit is surer where more cells support it: its noise there, noise / sqrt(support)
                    sure = float(np.clip(den[q, cell], 0.05, 1.0))
                    local = noise / np.sqrt(sure)
                    prom = pe['prominences'][i]
                    st = (knit.sstep(PROM[0], PROM[1], prom) * knit.sstep(LIT[0], LIT[1], lit)
                          * knit.sstep(*CLEAR, prom / max(local, 1e-6)))
                    if st <= 0.02:
                        continue
                    # where the top is, to within (cells): a light curving down by k per cell^2 has its top moved by
                    # sqrt(2 noise / k) under the fit's noise, and no further than its own half-width; a flat top is
                    # anywhere along it. The light's curvature from the envelope (shade beside it is no curvature
                    # of the light), with the stencil cut short at the run's ends
                    jl, jr = max(j - 2, 0), min(j + 2, len(f) - 1)
                    a, b = j - jl, jr - j
                    bend = max(-2 * (b * env[jl] - (a + b) * env[j] + a * env[jr]) / (a * b * (a + b)), 1e-9)
                    where = max(min(np.sqrt(2 * local / bend), width[i] / 2), (size - 1) / 2)
                    found.append((cell + 0.5 + off, st, width[i], sure, where, lit))
        peaks.append(found)
    # linked row to row: the same glint if it moved no more than LINK of the half-width a row, give or take where
    # the two peaks are known to within. A glint with no peak where it could be goes on unseen, up to reach rows,
    # only while where it would be is out of sight (the fit unsure there); where the fit plainly sees no peak, the
    # glint has ended
    done, live = [], []
    for q, row in enumerate(peaks):
        taken, nxt = set(), []
        for t in sorted(live, key=lambda t: -t[2][-1]):              # the strongest glints claim their peaks first
            miss = q - t[0][-1] - 1
            u0, d0 = t[1][-1], t[5][-1]
            near = [(abs(pk[0] - u0), j) for j, pk in enumerate(row) if j not in taken
                    and abs(pk[0] - u0) <= LINK * CELLS * (1 + miss) + np.hypot(pk[4], d0)]
            best = min(near, default=None)
            if best is not None:
                taken.add(best[1])
                for lst, v in zip(t, (q,) + row[best[1]]):
                    lst.append(v)
                nxt.append(t)
                continue
            c0, c1 = (int(np.clip(np.floor(u0 + k * (d0 + 1)), 0, den.shape[1] - 1)) for k in (-1, 1))
            if miss < reach and (den[q, c0:c1 + 1] < SURE).any():
                nxt.append(t)                                         # out of sight here
            else:
                done.append(t)
        nxt += [([q], *([v] for v in pk)) for j, pk in enumerate(row) if j not in taken]
        live = nxt
    out = []
    last = fit.shape[0] - 1
    for rows, u, st, wd, su, dl, li in done + live:
        q = np.asarray(rows, np.int64)
        u, st, wd, su, dl, li = (np.asarray(x, np.float64) for x in (u, st, wd, su, dl, li))
        full = np.arange(q[0], q[-1] + 1)
        # how bright the glint is comes from the rows where the fit is sure of it: across a gap the fit bridges
        # (trim, a hand) and the rows the glint went on unseen it is carried over from either side, so it neither
        # fades nor flares beside what hides it, nor do those rows touch the rows that are sure
        sure = su >= SURE
        src = sure if sure.any() else np.ones(len(q), bool)
        st, li = (np.interp(full, q[src], x[src]) for x in (st, li))
        u, wd, dl, su = (np.interp(full, q, x) for x in (u, wd, dl, su))
        su[~np.isin(full, q)] = 0.0
        li = ndi.gaussian_filter1d(li, 1.0, mode='nearest') if len(li) > 2 else li
        top = int(np.argmax(li * st))
        st = st * np.clip(li / max(float(li[top]), 1e-6), 0, 1) ** SPEC_EXP
        # padded with a row past each end, then smoothed: where the glint ends inside the piece (its peak gone), a
        # zero row, so it fades out and a peak seen in one row only stays faint; where the piece itself ends (a
        # wall, the image frame), the glint goes on past it, so its own value
        rows = np.concatenate([[full[0] - 1], full, [full[-1] + 1]]).astype(np.float64)
        u, wd, su, dl = (np.concatenate([[a[0]], a, [a[-1]]]) for a in (u, wd, su, dl))
        ends = (st[0] if full[0] == 0 else 0.0, st[-1] if full[-1] == last else 0.0)
        st = ndi.gaussian_filter1d(np.concatenate([[ends[0]], st, [ends[1]]]), 1.0, mode='nearest')
        out.append((rows, u, st, wd, su, dl))
    return out


def _smooth_within(qs, pts, wts, tol, clear):
    """The smoothest path through the points (N, 2), sampled at qs, that keeps every clear one within its own
    tolerance (px): a local linear fit along the track (Gaussian window, weighted by strength), as wide as that
    allows. Local linear, not a plain average, so a straight or gently curving path keeps its ends where they are."""
    dq = qs[None, :] - qs[:, None]
    for sig in (8.0, 6.0, 4.0, 3.0, 2.0, 1.5, 1.0, 0.7):
        kern = np.exp(-0.5 * (dq / sig) ** 2) * wts[None, :]
        s0, s1, s2 = kern.sum(1), (kern * dq).sum(1), (kern * dq * dq).sum(1)
        t0, t1 = kern @ pts, (kern * dq) @ pts
        det = s0 * s2 - s1 * s1
        flat = det <= 1e-9 * np.maximum(s0 * s2, 1e-12)
        sm = np.where(flat[:, None], t0 / s0[:, None], (s2[:, None] * t0 - s1[:, None] * t1)
                      / np.where(flat, 1.0, det)[:, None])
        if (np.hypot(*(sm - pts).T)[clear] <= tol[clear]).all():
            return sm
    return pts


def _curve(rows, ga, st, dl, su, t, Ag, xs, ys, ab, step=0.25):
    """A glint track as a smooth curve on screen, densely sampled (N, 2) xy, or None. Each row's glint is where the
    stocking sits at the glint's A in that row. One light on a smooth body traces a smooth curve, so the path is
    smoothed as far as the painted highlight allows: every clear row stays within what its peak is known to within
    (dl, cells), never finer than the fit resolves. A broad soft highlight (whose flat top wanders) gets a smooth
    path; a crisp one is followed exactly. Rows where the glint went on unseen (sureness 0) are passed through, not
    aimed at, and rows less sure of it count for less."""
    pts, wts, tol, qs = [], [], [], []
    for q, a, w, d, u in zip(rows[1:-1], ga[1:-1], st[1:-1], dl[1:-1], su[1:-1]):
        sel = (t >= q - 0.5) & (t < q + 0.5) & (np.abs(Ag - a) < ab)
        if u > 0 and sel.sum() >= 2:
            pts.append((xs[sel].mean(), ys[sel].mean()))
            wts.append((w + 1e-3) * u)
            tol.append(max(d * ab, 0.25 * ab, 1.0))
            qs.append(q)
    if not pts:
        return None
    pts, wts, tol, qs = np.asarray(pts), np.asarray(wts), np.asarray(tol), np.asarray(qs, np.float64)
    if len(pts) == 1:
        return pts
    pts = _smooth_within(qs, pts, wts, tol, wts > 0.25 * wts.max())
    # carried on a row past each end along its own direction, as far as the track's rows reach
    pts = np.vstack([2 * pts[0] - pts[1], pts, 2 * pts[-1] - pts[-2]])
    qs = np.concatenate([[2 * qs[0] - qs[1]], qs, [2 * qs[-1] - qs[-2]]])
    qq = np.linspace(qs[0], qs[-1], max(4 * len(qs), 2))
    xy = np.stack([np.interp(qq, qs, pts[:, k]) for k in (0, 1)], 1)
    seg = np.hypot(*np.diff(xy, axis=0).T)
    sarc = np.concatenate([[0], np.cumsum(seg)])
    n = max(int(sarc[-1] / step), 2)
    return np.stack([np.interp(np.linspace(0, sarc[-1], n), sarc, xy[:, k]) for k in (0, 1)], 1)


def oily_maps(src, R, alpha, A, V, scale=1.0, cut=None, REG=None, core_half=1.5, band_half=4.0, tail_len=14.0):
    """Whole image: (tone, core, band, tail, facing, centre), each HxW float32, 0 outside the regions.

    src: BGR art. R: the visible stocking, region index per pixel. alpha: soft coverage (render_oily applies it).
    A, V: the courses' frame. cut: the bands along walls where V and A jump (Document.cut_map), or None. REG: the
    painted regions before the colour test (geometry), or None to use R.
    tone: -1..1, the region's smoothed brightness within its own range (with a floor). core, band, tail: each glint's
    gloss lobe, core_half / band_half px (times scale and widen) to each side and an exponential fall-off tail_len px
    long. facing: 0..1. centre: 1 at a glint's very centre, where its texture is washed out.
    """
    h_, w_ = R.shape
    Y = luminance(src)
    geo = REG if REG is not None else R
    tone, core, band, tail, centre, facing = (np.zeros((h_, w_), np.float32) for _ in range(6))
    on_frame = np.zeros((h_, w_), bool)
    on_frame[[0, -1], :] = on_frame[:, [0, -1]] = True
    ring = np.ones((3, 3), np.uint8)
    rim = max(2, int(round(2 * scale)))                   # px of mixed pixels at the edge of the visible stocking
    disc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * rim + 1, 2 * rim + 1))
    for i in np.unique(R[R > 0]):
        seen = R == i
        G = (geo == i) | seen
        # where this region's edge meets other stocking (another region, a wall): the limb goes on behind it
        beside = ((geo > 0) & (geo != i) & ~seen) if cut is None else (((geo > 0) & (geo != i) & ~seen) | cut)
        hidden = on_frame | (cv2.dilate(beside.astype(np.uint8), ring) > 0)
        Ls = _masked_blur(Y, seen, 3 * scale)
        lo, hi = (float(v) for v in np.percentile(Ls[seen], [3, 99]))
        tone[G] = np.clip((Ls[G] - (lo + hi) / 2) / max((hi - lo) / 2, TONE_FLOOR), -1, 1)
        body = G if cut is None else G & ~cut
        n, lab = cv2.connectedComponents(body.astype(np.uint8), connectivity=8)
        for j in range(1, n):
            m = lab == j
            Vg, Ag = V[m], A[m]
            k, c, h, hf, hmed, tilt = _frame(Vg, Ag, hidden[m], scale)
            hk = h[k]
            u = np.clip((Ag - c[k]) / hf[k], -1, 1)
            facing[m] = np.sqrt(1 - u * u) * np.cos(tilt[k])
            vis = seen[m]
            if vis.sum() < MIN_PIECE:
                continue
            pure = (cv2.erode(seen.astype(np.uint8), disc, borderType=cv2.BORDER_REPLICATE) > 0)[m]
            if pure.sum() >= MIN_PIECE:
                vis = pure
            fit, absolute, den, wlen, v0, a0, ab, noise = _lighting(Y[m][vis], Vg[vis], Ag[vis], k[vis],
                                                                    int(k.max()) + 1, hmed, scale)
            tracks = _tracks(fit, absolute, den, noise, reach=int(round(2 * hmed / wlen)))
            if not tracks:
                continue
            t = (Vg - v0) / wlen - 0.5                           # every pixel's position in rows
            ys, xs = np.nonzero(m)
            bx0, by0 = int(xs.min()), int(ys.min())
            box = (int(ys.max()) - by0 + 1, int(xs.max()) - bx0 + 1)
            exact = 3 * band_half * 2.0 * scale                 # px: within this, the lobe's shape needs exact distance
            wmed = float(np.median(np.concatenate([tr[3] for tr in tracks])))
            acc = [np.zeros(m.sum(), np.float32) for _ in range(4)]
            for rows, tu, st, wd, su, dl in tracks:
                at = (t >= rows[0]) & (t <= rows[-1])
                curve = _curve(rows, a0 + ab * tu, st, dl, su, t, Ag, xs, ys, ab)
                if curve is None or not at.any():
                    continue
                ti = t[at]
                g_s = np.interp(ti, rows, st)
                flat = np.clip(np.interp(ti, rows, wd) / max(wmed, 1e-6), 0.7, 2.5)
                widen = np.clip(0.6 * hk[at] / hmed + 0.4 * flat, 0.8, 2.0) * scale
                # px on screen to the glint's curve: a distance transform, exact (sub-pixel) close to the curve; a
                # glint seen in one row only is a point, measured to directly
                if len(curve) < 2:
                    d = np.hypot(xs[at] - curve[0, 0], ys[at] - curve[0, 1]).astype(np.float64)
                else:
                    canvas = np.full(box, 255, np.uint8)
                    cv2.polylines(canvas, [np.round((curve - [bx0, by0]) * 16).astype(np.int32).reshape(-1, 1, 2)],
                                  False, 0, 1, cv2.LINE_8, 4)
                    d = cv2.distanceTransform(canvas, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)[ys[at] - by0, xs[at] - bx0]
                    d = d.astype(np.float64)
                    near = d < exact
                    if near.any():
                        d[near] = cKDTree(curve).query(np.stack([xs[at][near], ys[at][near]], 1))[0]
                for a, val in zip(acc, (np.exp(-0.5 * (d / (core_half * widen)) ** 2) * g_s,
                                        np.exp(-0.5 * (d / (band_half * widen)) ** 2) * g_s,
                                        np.exp(-d / (tail_len * widen)) * g_s,
                                        np.exp(-0.5 * (d / (1.3 * core_half * widen)) ** 2) * (g_s > 0.05))):
                    a[at] = np.maximum(a[at], val)
            core[m], band[m], tail[m], centre[m] = acc
        if cut is not None and (G & cut).any() and body.any():
            # the wall's own band takes its maps from the nearest stocking beside it, so no seam opens along it
            gap = G & cut
            iy, ix = ndi.distance_transform_edt(~body, return_distances=False, return_indices=True)
            for mp in (core, band, tail, centre, facing):
                mp[gap] = mp[iy[gap], ix[gap]]
    return tone, core, band, tail, facing, centre


def render_oily(src, R, V, A, alpha, g, s, tone, core, band, tail, facing, centre, noise):
    """BGR uint8 of the (margined) crop. g: look.geometry; s: strength (1 = 100%); tone .. centre: oily_maps()
    cropped like src; noise: the scene's grain fields (knit.grain_noise), cropped like src."""
    p = g['period']
    gn, gc = noise
    phi = V / p + 0.37 * R
    base, _ = knit.render_grain(src, R, phi, A / (p * g['wale_ratio']), alpha, None, knit_amp=0.025 * s,
                                grain=0.010 * s, grain_dark=0.005 * s, chroma=0.15, f_lo=g['f_lo'], f_hi=g['f_hi'],
                                noise=(gn, gc))
    out = base.astype(np.float32)
    a3 = alpha[..., None]
    # translucency: skin through the middle, denser fabric at the silhouette
    see = (facing ** 2 * alpha)[..., None]
    out *= 1 + 0.35 * s * see * np.array([0.35, 0.65, 1.0], np.float32)      # B, G, R: warm
    out *= 1 - 0.30 * s * ((1 - facing) ** 1.5)[..., None] * a3
    sink = np.clip(-tone, 0, 1) ** 1.2
    out *= (1 - 0.30 * s * sink * alpha)[..., None]
    # what the glint reflects: the courses (faded where they would alias) and a little grain, 0..1
    same = knit._same_region(R)
    keep = (1 - knit.sstep(g['f_lo'], g['f_hi'], _footprint(V / p, same))) * same
    tex = 0.5 + 0.5 * np.clip(0.6 * np.cos(2 * np.pi * phi) * keep + 0.25 * gn, -1, 1)
    sheen = 0.20 * s * np.clip(tone, 0, 1) ** 1.6
    # texture shows on the flanks of the glint and fades out toward its centre, which stays clean
    flank = 1 - knit.sstep(0.25, 0.75, centre)
    t_core = 1 - flank * (0.55 - 0.55 * tex)
    glint = s * (0.42 * core * t_core + 0.18 * band * (1 - flank * (1 - tex))
                 + 0.30 * tail * (1 - flank * (0.15 - 0.15 * tex)))
    bright = np.clip((sheen + glint) * alpha, 0, 0.93)[..., None]        # soft coverage holds for every reflection
    out = 255 - (255 - out) * (1 - bright)
    return np.clip(np.round(out), 0, 255).astype(np.uint8)

"""Small repeating patterns drawn in surface coordinates without moire.

A tile covers one repeat: u (columns) along the course, v (rows) across it, both 0..1. Each pixel samples it at its
(u, v) from a ripmap: the tile pre-averaged over 2^i rows and 2^j columns, picked per axis by how many texels one
pixel spans along that axis and blended (trilinear per axis). Where the courses crowd, the pattern averages out to
its mean (0) instead of aliasing; where only the wales crowd, the courses stay sharp.
"""
import cv2
import numpy as np


def _halve(a, axis):
    h, w = a.shape
    if (h, w)[axis] <= 1:
        return None
    size = (w, h // 2) if axis == 0 else (w // 2, h)
    return cv2.resize(a, size, interpolation=cv2.INTER_AREA)


def ripmap(tile):
    """rip[i][j]: the tile (float32) averaged over 2^i rows and 2^j columns, down to one row / one column."""
    rows = [np.asarray(tile, np.float32)]
    while (r := _halve(rows[-1], 0)) is not None:
        rows.append(r)
    rip = []
    for r in rows:
        cols = [r]
        while (c := _halve(cols[-1], 1)) is not None:
            cols.append(c)
        rip.append(cols)
    return rip


def _remap(T, x, y, width=4096):
    """Bilinear lookup of T at flat texel coordinates x, y, wrapping around (cv2.remap caps maps at 32767 wide)."""
    n = x.size
    rows = -(-n // width)
    pad = rows * width - n
    mx = np.pad(x.astype(np.float32), (0, pad)).reshape(rows, width)
    my = np.pad(y.astype(np.float32), (0, pad)).reshape(rows, width)
    return cv2.remap(T, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP).ravel()[:n]


def sample(rip, u, v, fu, fv):
    """The tile at (u, v) in repeats, filtered for a pixel spanning fu repeats along u and fv along v.
    All arguments are arrays of one shape; returns float32 of that shape."""
    H0, W0 = rip[0][0].shape
    nv, nu = len(rip), len(rip[0])
    u, v, fu, fv = (np.asarray(a, np.float32) for a in (u, v, fu, fv))
    tiny = np.float32(1e-9)
    lv = np.clip(np.log2(np.maximum(fv * H0, tiny)), 0, nv - 1)
    lu = np.clip(np.log2(np.maximum(fu * W0, tiny)), 0, nu - 1)
    i0 = np.clip(np.floor(lv).astype(int), 0, max(nv - 2, 0))
    j0 = np.clip(np.floor(lu).astype(int), 0, max(nu - 2, 0))
    tv, tu = (np.clip(lv - i0, 0, 1)).ravel(), (np.clip(lu - j0, 0, 1)).ravel()
    uu, vv = np.mod(u, np.float32(1)).ravel(), np.mod(v, np.float32(1)).ravel()
    # pixels grouped by level pair, so each group is one contiguous slice instead of a mask over everything
    key = (i0 * nu + j0).ravel()
    order = np.argsort(key, kind='stable')
    ks = key[order]
    cuts = np.r_[0, np.flatnonzero(np.diff(ks)) + 1, ks.size]
    uu, vv, tv, tu = uu[order], vv[order], tv[order], tu[order]
    res = np.empty(ks.size, np.float32)
    for a, b in zip(cuts[:-1], cuts[1:]):
        i, j = divmod(int(ks[a]), nu)
        acc = np.zeros(b - a, np.float32)
        for di, wi in ((0, 1 - tv[a:b]), (1, tv[a:b])):
            for dj, wj in ((0, 1 - tu[a:b]), (1, tu[a:b])):
                T = rip[min(i + di, nv - 1)][min(j + dj, nu - 1)]
                h, w = T.shape
                acc += (wi * wj) * _remap(T, uu[a:b] * w - 0.5, vv[a:b] * h - 0.5)
        res[a:b] = acc
    out = np.empty(ks.size, np.float32)
    out[order] = res
    return out.reshape(np.shape(u))


def _unit(t):
    t = t - t.mean()
    return (t / (t.std() + 1e-9)).astype(np.float32)


def _segment_distance(x, y, x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    t = np.clip(((x - x0) * dx + (y - y0) * dy) / (dx * dx + dy * dy), 0, 1)
    return np.hypot(x - (x0 + t * dx), y - (y0 + t * dy))


def loops_gap_tile(n=64):
    """One course by one wale of plain knit seen from its face, positive in the gaps: a narrow V of two round yarn
    legs leaning toward each other, the V's stacked in columns with a gap between courses and between columns.
    Zero mean, unit standard deviation."""
    v, u = (np.mgrid[0:n, 0:n] + 0.5) / n
    yarn = np.zeros((n, n))
    r = 0.16
    for du in (-1, 0, 1):                       # legs of the neighbouring repeats reach into this one
        for dv in (-1, 0, 1):
            for u0, u1 in ((0.24, 0.46), (0.76, 0.54)):
                d = _segment_distance(u, v, du + u0, dv + 0.12, du + u1, dv + 0.88)
                yarn = np.maximum(yarn, np.sqrt(np.clip(1 - (d / r) ** 2, 0, 1)))
    return _unit(-yarn)


def thread_gap_tile(n=48):
    """One course by one wale of a fine knit, as the gap between the threads (positive where the skin shows): wide
    threads, a thin gap between courses that wobbles a little with each loop, a fainter gap between wales.
    Zero mean, unit standard deviation."""
    v, u = np.mgrid[0:n, 0:n] / n
    centre = 0.5 + 0.06 * np.sin(2 * np.pi * u)
    d = np.abs(v - centre)
    d = np.minimum(d, 1 - d)
    course_gap = np.exp(-0.5 * (d / 0.09) ** 2)
    wale_gap = 0.25 * np.exp(-0.5 * (np.minimum(u, 1 - u) / 0.06) ** 2)
    return _unit(np.maximum(course_gap, wale_gap))

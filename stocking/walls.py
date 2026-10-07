"""Walls: where one stretch of stocking lies in front of another (a calf folded behind its own thigh, one leg across
the other, the two breasts), found from the depth model. The courses are solved as one sheet everywhere else, so a
leg bent double needs no cutting and touching regions meet without a seam; across a wall they do not continue.

A wall is a sharp step in the depth (a ridge of its gradient, many times steeper than the stockings' own rounding)
with stocking on both sides of it. The silhouette is not one (the other side is background), nor is the edge of
a hand or hair lying on the stocking (the other side is the occluder), nor a line merely drawn on the stocking (a
lace pattern, a crease: no step in depth).

    R = ridges(disparity, scale)            # once per image
    walls = find_walls(R, stocking_mask)     # on any crop of both
"""
import cv2
import numpy as np

STEP_HI, STEP_LO = 5.0, 2.5     # depth gradient over the stockings' median gradient: a wall's core / its continuation
SHARP = 0.4                     # a step, not a slope: the gradient SIDE px either side is below this part of its peak
TALL = 0.3                      # and a step of some size: its height over (median gradient x the region's half-width),
                                # what the region's own rounding spans (a contour ~0.5-0.8, the crease of a knee less)
SIDE = 8.0                      # px (at 1280x1920) either side of a wall that must be stocking
MIN_LEN = 24.0                  # px (at 1280x1920): shorter ridges are noise


def ridges(disp, scale=1.0):
    """(g, nx, ny, peak, d) of the disparity: gradient magnitude, its unit direction, where g peaks across the step
    (non-maximum suppression), and the smoothed disparity itself, all HxW. scale: image size relative to 1280x1920
    (sqrt of the area ratio)."""
    d = cv2.GaussianBlur(disp.astype(np.float32), (0, 0), 1.5 * scale)
    gy, gx = np.gradient(d)
    g = np.hypot(gx, gy).astype(np.float32)
    nx, ny = (gx / (g + 1e-9)).astype(np.float32), (gy / (g + 1e-9)).astype(np.float32)
    h, w = g.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ahead = cv2.remap(g, xx + nx, yy + ny, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    behind = cv2.remap(g, xx - nx, yy - ny, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return g, nx, ny, (g >= ahead) & (g >= behind), d


def crop(R, sl):
    return tuple(a[sl] for a in R)


def find_walls(R, stock, scale=1.0):
    """bool mask of the walls inside `stock` (the stocking pixels, same shape as R's maps): thin lines, about 3 px.
    stock should be the stockings themselves (coverage), not a rough region: a region painted over the background
    would put stocking on both sides of the silhouette."""
    g, nx, ny, peak, dsm = R
    stock = stock.astype(bool)
    inner = cv2.erode(stock.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    if inner.sum() < 64:
        return np.zeros(stock.shape, bool)
    typical = max(float(np.median(g[inner])), 1e-9)
    en = g / typical
    h, w = stock.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    s8 = stock.astype(np.uint8)
    half = float(cv2.distanceTransform(np.pad(s8, 1), cv2.DIST_L2, 5).max())

    def across(f, r, interp):
        return [cv2.remap(f, xx + k * r * nx, yy + k * r * ny, interp, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
                for k in (1, -1)]

    r = SIDE * scale
    near = across(s8, r, cv2.INTER_NEAREST)
    hi, lo = across(dsm, r, cv2.INTER_LINEAR)
    tall = np.abs(hi - lo) >= TALL * typical * half
    cand = stock & peak & (near[0] > 0) & (near[1] > 0) & (en > STEP_LO) & tall
    if not cand.any():
        return np.zeros(stock.shape, bool)
    # judged line by line, not pixel by pixel: a few pixels of a slope can pass where the line as a whole does not.
    # NMS leaves 1 px lines that may touch only diagonally; join them before taking lines
    joined = cv2.dilate(cand.astype(np.uint8), np.ones((3, 3), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    far = across(s8, 2.5 * r, cv2.INTER_NEAREST)
    sharp = np.maximum(*across(g, r, cv2.INTER_LINEAR)) < SHARP * g
    L = lab[cand]
    count = np.maximum(np.bincount(L, minlength=n), 1)

    def share(f):
        return np.bincount(L, weights=f[cand].astype(np.float64), minlength=n) / count

    span = np.hypot(st[:, cv2.CC_STAT_WIDTH], st[:, cv2.CC_STAT_HEIGHT])
    # the edge of a finger or a strand of hair lying on the stocking is not between two stretches of stocking, even
    # where the occluder is thin enough for stocking to show again beyond it
    clear = cv2.distanceTransform(np.pad(s8, 1, mode='edge'), cv2.DIST_L2, 3)[1:-1, 1:-1] >= 4.0 * scale
    ok = ((share(en >= STEP_HI) >= 0.5) & (share(sharp) >= 0.5) & (share((far[0] > 0) & (far[1] > 0)) >= 0.7)
          & (share(clear) >= 0.7) & (span >= MIN_LEN * scale))
    ok[0] = False
    if not ok.any():
        return np.zeros(stock.shape, bool)
    walls = ok[lab] & (joined > 0)
    walls = cv2.morphologyEx(walls.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)) > 0
    return walls & stock


def _ends(piece):
    """The two ends of a thin curved line (bool mask) and the unit direction it leaves each by: [(xy, dir)]."""
    from scipy.sparse.csgraph import breadth_first_order
    ys, xs = np.nonzero(piece)
    n = len(ys)
    if n < 4:
        return []
    idx = -np.ones(piece.shape, np.int64)
    idx[ys, xs] = np.arange(n)
    h, w = piece.shape
    ii, jj = [], []
    for dy, dx in ((0, 1), (1, -1), (1, 0), (1, 1)):
        y2, x2 = ys + dy, xs + dx
        ok = (y2 >= 0) & (y2 < h) & (x2 >= 0) & (x2 < w)
        k = np.full(n, -1)
        k[ok] = idx[y2[ok], x2[ok]]
        ok = k >= 0
        ii.append(np.arange(n)[ok]); jj.append(k[ok])
    ii, jj = np.concatenate(ii), np.concatenate(jj)
    import scipy.sparse as sp
    adj = sp.csr_matrix((np.ones(len(ii)), (ii, jj)), shape=(n, n))
    adj = (adj + adj.T).tocsr()

    def far(s):
        order, pred = breadth_first_order(adj, s, directed=False, return_predecessors=True)
        return order[-1], pred

    a, _ = far(0)
    b, pred = far(a)
    path = [b]
    while pred[path[-1]] >= 0:
        path.append(pred[path[-1]])
    P = np.stack([xs[path], ys[path]], 1).astype(np.float64)       # from b to a
    pix = np.stack([xs, ys], 1).astype(np.float64)
    out = []
    for e0 in (P[0], P[-1]):
        # the direction from a straight fit to the line's last 20 px: a path through a 3 px band zigzags
        near = pix[np.hypot(*(pix - e0).T) <= 20.0]
        if len(near) < 3:
            continue
        c = near.mean(0)
        evals, evecs = np.linalg.eigh(np.cov((near - c).T))
        d = evecs[:, -1]
        if (e0 - c) @ d < 0:
            d = -d
        out.append((c + d * float(((near - c) @ d).max()), d))
    return out


def carry_through(walls, visible, domain, lead=0.15):
    """walls carried on through what is filled in: where a wall ends at (or near) a filled-in gap (fill_occlusions:
    the background between the tops of a thigh and the calf folded behind it, looking like a notch), that gap
    joins the wall, linked to its end, so the courses do not walk round the wall's end through it. The depth model
    blurs the last stretch before such a gap, so the wall may stop short of it: a gap within `lead` x the region's
    half-width of the wall's end counts. A wall ending in visible stocking (the fold of a knee) is left as it is.
    Returns the mask the solve leaves out (walls, gaps and links)."""
    if not walls.any():
        return walls
    h, w = walls.shape
    out = walls.copy()
    hidden = (domain & ~visible).astype(np.uint8)
    if not hidden.any():
        return out
    half = float(cv2.distanceTransform(np.pad(visible, 1).astype(np.uint8), cv2.DIST_L2, 5).max())
    reach = max(4.0, lead * half)
    ng, glab = cv2.connectedComponents(hidden, connectivity=8)
    n, lab = cv2.connectedComponents(walls.astype(np.uint8), connectivity=8)
    for k in range(1, n):
        for e, d in _ends(lab == k):
            x0, y0 = int(round(e[0])), int(round(e[1]))
            r = int(np.ceil(reach))
            ya, yb, xa, xb = max(y0 - r, 0), min(y0 + r + 1, h), max(x0 - r, 0), min(x0 + r + 1, w)
            win = glab[ya:yb, xa:xb]
            ys, xs = np.nonzero(win > 0)
            if not len(ys):
                continue
            dist = np.hypot(xs + xa - e[0], ys + ya - e[1])
            ahead = (xs + xa - e[0]) * d[0] + (ys + ya - e[1]) * d[1] > -2.0     # beyond the end, not beside it
            ok = (dist <= reach) & ahead
            if not ok.any():
                continue
            j = np.flatnonzero(ok)[np.argmin(dist[ok])]
            out |= glab == win[ys[j], xs[j]]
            link = np.zeros((h, w), np.uint8)
            cv2.line(link, (x0, y0), (int(xs[j] + xa), int(ys[j] + ya)), 1, 3)
            out |= (link > 0) & domain
    return out

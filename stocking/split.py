"""Split one region mask into two: along a line the user drew (cut_mask), or automatically (split_mask).

cut_mask carries the drawn line on straight past both ends and divides the region by which side of it each pixel
lies on, so a short line across the narrowest part is enough.

split_mask is for a left/right pair selected as one region (two breasts, two legs, a torso): it treats the region as
one shape however many pieces it is made of, and cuts it by one smooth line between the two halves. The line starts
on the shape's mirror axis (mirror_axis: the line it is most nearly symmetric about, whatever its proportions) and
bends to follow a crease where one runs nearby: a dark line in the art, or a gap between two pieces (SAM stops at
line art, so two breasts clicked separately meet at a gap). Lines that veer off (the outlines either side of the V
above a cleavage) are let go, so a chunk between two parts is cut down its middle. The line is the cheapest path
through the band either side of the axis (dynamic programming over rows of a frame rotated to the axis). A region
that is not such a pair (a near leg and the far one seen from the side) is cut along a line the user draws instead.
"""
import cv2
import numpy as np

BAND = 0.15         # the cut may move this fraction of the region's span across the axis either side of the axis
FIND = 0.3          # first pass, finding the crease: a weak pull toward the axis (fraction of the span at
                    # which being off costs as much as cutting through fabric)
HOLD = 0.08         # second pass: a strong pull toward the straight line fitted along that crease, so outlines that
                    # veer off it (either side of the V above a cleavage) are let go
LINE_COST = 0.3     # cost of cutting along a crease or a gap, relative to 1 for cutting through plain fabric
STEP_COST = 0.75    # extra cost per px the cut moves sideways per row

# snap_line (自动贴线, for the split line and the 隔开 line) pulls much harder than the automatic split does:
SNAP_LINE_COST = 0.1    # cost along a line or a gap: lines are close to free
SNAP_PULL = 0.3         # cost per row of lying at the edge of the search ribbon, the pull back to the drawn stroke;
                        # a line saves up to 0.9 a row, so a strong line reaches the whole ribbon, a faint one less far
SNAP_STEP = 0.15        # extra cost per px the snapped line moves sideways per row
SNAP_DARK = 0.05        # how much darker than both its sides a pixel is to count fully as a dark line (grey 0..1)
SNAP_SIDE = 3           # px either side of a pixel where a dark line's lighter surroundings are looked for
SNAP_EDGE = 0.05        # strength of a step between two tones (σ · gradient, a step of h gives 0.4 h) that counts well:
                        # a third of that counts for 0.4 of a line, three times that for 0.95
SNAP_EDGE_WEIGHT = 0.7  # a tone step pulls less than a dark line, so a line with an edge each side is followed along
                        # its middle
SNAP_RIDGE = 7          # px: only the crest of a tone step counts, the pixels beside it whose gradient is weaker than
                        # the strongest within this window count less, so the line lands on the step, not near it
SNAP_GAP = 15           # px: the gaps between the pieces of a region that snap_line takes for a line are at most this wide
SNAP_SMOOTH = 3.0       # px: how much the snapped line is smoothed at the end, so it does not follow the grain of the
                        # art's edge


def _seam(cost, centre, follow, step_cost=STEP_COST, gain=1 - LINE_COST):
    """Cheapest path down the rows of `cost` (one column per row, moving at most one column per row), paying
    step_cost per sideways move and gain / follow per column of distance from centre[row]."""
    ns, nt = cost.shape
    cols = np.arange(nt)
    total = cost + gain * np.abs(cols[None, :] - np.asarray(centre, float)[:, None]) / follow
    acc = total[0].copy()
    back = np.zeros((ns, nt), np.int8)
    for i in range(1, ns):
        left = np.r_[np.inf, acc[:-1]] + step_cost
        right = np.r_[acc[1:], np.inf] + step_cost
        stack = np.stack([left, acc, right])
        k = np.argmin(stack, 0)
        back[i] = k - 1
        acc = stack[k, cols] + total[i]
    path = np.zeros(ns, int)
    path[-1] = int(np.argmin(acc))
    for i in range(ns - 1, 0, -1):
        path[i - 1] = path[i] + back[i, path[i]]
    return path


def _line_cost(art_rgb):
    """Cost of cutting at each pixel: 1 on plain fabric, down to LINE_COST along the dark lines of the line art."""
    L = cv2.cvtColor(np.ascontiguousarray(art_rgb), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    line = np.clip((cv2.GaussianBlur(L, (0, 0), 5) - cv2.GaussianBlur(L, (0, 0), 1)) / 0.12, 0, 1)
    return 1 - (1 - LINE_COST) * line


def _snap_strength(art_rgb):
    """How much each pixel looks like something to snap a line to, 0 (plain fabric) to 1: a dark line (darker than
    both its sides, so one side of a tone step is not a line), or less so a step between two tones (the edge of a
    stocking lying over another, which has no outline of its own)."""
    L = cv2.cvtColor(np.ascontiguousarray(art_rgb), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    d = SNAP_SIDE
    B = cv2.copyMakeBorder(cv2.GaussianBlur(L, (0, 0), 1.0), d, d, d, d, cv2.BORDER_REPLICATE)
    h, w = L.shape
    c = B[d:d + h, d:d + w]
    line = np.zeros_like(L)
    for dy, dx in ((0, d), (d, 0), (d - 1, d - 1), (d - 1, 1 - d)):       # the four directions through a pixel
        both = np.minimum(B[d + dy:d + dy + h, d + dx:d + dx + w], B[d - dy:d - dy + h, d - dx:d - dx + w])
        line = np.maximum(line, both - c)
    dark = np.clip(line / SNAP_DARK, 0, 1)
    edge = np.zeros_like(L)
    for sigma in (1.5, 3.0):
        G = cv2.GaussianBlur(L, (0, 0), sigma)
        edge = np.maximum(edge, sigma * np.hypot(cv2.Sobel(G, cv2.CV_32F, 1, 0, ksize=3),
                                                 cv2.Sobel(G, cv2.CV_32F, 0, 1, ksize=3)) / 8)
    ridge = edge / (cv2.dilate(edge, np.ones((SNAP_RIDGE, SNAP_RIDGE), np.uint8)) + 1e-9)     # 1 on the crest only
    return np.maximum(dark, SNAP_EDGE_WEIGHT * (1 - np.exp(-edge / SNAP_EDGE)) * ridge ** 2)


def _resample(P, step=1.0):
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]
    if d[-1] < step:
        return P
    s = np.arange(0, d[-1] + 1e-9, step)
    return np.stack([np.interp(s, d, P[:, 0]), np.interp(s, d, P[:, 1])], 1)


def _smooth(P, sigma):
    from scipy.ndimage import gaussian_filter1d
    if len(P) < 3 or sigma <= 0:
        return P
    return np.stack([gaussian_filter1d(P[:, 0], sigma, mode='nearest'),
                     gaussian_filter1d(P[:, 1], sigma, mode='nearest')], 1)


def snap_line(P, art_rgb, mask, radius):
    """A hand-drawn line moved onto the line art it was drawn along.

    The stroke is resampled and smoothed (hand jitter goes), then the cut is the cheapest path through a ribbon
    `radius` px either side of it: nearly free along dark lines, tone edges and (with `mask`, the region being cut)
    the gaps between its pieces, a pull back to the stroke that a strong line outweighs from the far side of the
    ribbon, and a small cost for every sideways step, so where there is no line nearby it just follows the smoothed
    stroke. Returns the snapped polyline (N x 2) and the smoothed stroke (for the end directions).
    """
    H, W = art_rgb.shape[:2]
    radius = int(np.clip(round(radius), 2, 80))
    C = _smooth(_resample(np.asarray(P, np.float64)), float(np.clip(radius / 3.0, 3.0, 6.0)))
    if len(C) < 3:
        return C, C
    T = np.gradient(C, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True) + 1e-9
    N = np.stack([-T[:, 1], T[:, 0]], 1)
    offs = np.arange(-radius, radius + 1, dtype=np.float64)
    gx = C[:, 0, None] + offs[None, :] * N[:, 0, None]
    gy = C[:, 1, None] + offs[None, :] * N[:, 1, None]
    x0 = int(np.clip(np.floor(gx.min()) - 8, 0, W - 1)); x1 = int(np.clip(np.ceil(gx.max()) + 9, 1, W))
    y0 = int(np.clip(np.floor(gy.min()) - 8, 0, H - 1)); y1 = int(np.clip(np.ceil(gy.max()) + 9, 1, H))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return C, C
    strength = _snap_strength(art_rgb[y0:y1, x0:x1])
    if mask is not None:
        mc = np.ascontiguousarray(mask[y0:y1, x0:x1]).astype(np.uint8)
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (SNAP_GAP, SNAP_GAP))
        strength[(cv2.morphologyEx(mc, cv2.MORPH_CLOSE, k) > 0) & (mc == 0)] = 1      # gaps between the pieces
    cost = 1 - (1 - SNAP_LINE_COST) * strength
    mx, my = (gx - x0).astype(np.float32), (gy - y0).astype(np.float32)
    ribbon = cv2.remap(cost, mx, my, cv2.INTER_LINEAR, borderValue=1.0)
    gain = 1 - SNAP_LINE_COST
    path = _seam(ribbon, np.full(len(C), float(radius)), follow=gain * radius / SNAP_PULL, step_cost=SNAP_STEP,
                 gain=gain)
    S = C + (path - radius)[:, None] * N
    return _smooth(S, SNAP_SMOOTH), C


def snap_stroke(pts, art_rgb, radius):
    """A hand-drawn line (N x 2 px) moved onto the line art within `radius` px of it (a 隔开 line along the outline
    of one stocking over another); jitter is smoothed away and, unlike a cut, the ends are not carried on."""
    P = np.asarray(pts, np.float64).reshape(-1, 2)
    if len(P) < 2:
        return P
    return snap_line(P, art_rgb, None, radius)[0]


def _direction(Q, end_len=12.0):
    """Unit vector pointing out of the polyline at its first point, from its first end_len px; None if too short."""
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(Q, axis=0).T))]
    k = int(np.searchsorted(d, min(end_len, d[-1])))
    v = Q[0] - Q[max(k, 1)]
    n = np.hypot(*v)
    return v / n if n > 1e-6 else None


def _extend(P, end_len=12.0, reach=1e5, dirs=None):
    """The polyline with both ends carried on straight by `reach` px, in the direction of their last end_len px
    (or the given (start, end) directions)."""
    v0, v1 = dirs if dirs is not None else (_direction(P, end_len), _direction(P[::-1], end_len))
    out = [P]
    if v0 is not None:
        out.insert(0, (P[0] + v0 * reach)[None])
    if v1 is not None:
        out.append((P[-1] + v1 * reach)[None])
    return np.concatenate(out)


def cut_mask(mask, pts, art_rgb=None, snap_radius=0):
    """Split `mask` along a line the user drew: (part_a, part_b, axis) as split_mask, or None if the line, carried
    on straight past its ends, does not divide the mask. pts: N x 2 image px (pixel centres), any length.

    With art_rgb and snap_radius > 0 the line is first snapped onto the line art within snap_radius px
    (snap_line); it is carried on past its ends in the directions the user drew.
    """
    m = np.asarray(mask, bool)
    P = np.asarray(pts, np.float64).reshape(-1, 2)
    if len(P) >= 2:
        keep = np.r_[True, np.hypot(*np.diff(P, axis=0).T) > 1e-6]
        P = P[keep]
    if len(P) < 2 or not m.any():
        return None
    dirs = None
    if art_rgb is not None and snap_radius > 0:
        P, drawn = snap_line(P, art_rgb, m, snap_radius)
        # carried on in the direction the user drew, averaged over a long stretch so hand jitter does not tilt it
        span = max(24.0, 0.4 * float(np.hypot(*np.diff(drawn, axis=0).T).sum()))
        dirs = (_direction(drawn, span), _direction(drawn[::-1], span))
    ys, xs = np.nonzero(m)
    pad = 2
    y0, x0 = max(ys.min() - pad, 0), max(xs.min() - pad, 0)
    y1, x1 = min(ys.max() + 1 + pad, m.shape[0]), min(xs.max() + 1 + pad, m.shape[1])
    mc = m[y0:y1, x0:x1]
    h, w = mc.shape
    Q = _extend(P, reach=4.0 * (h + w), dirs=dirs) - [x0, y0]
    # the line (with sub-pixel precision) as a wall across the box; what is left falls apart into the two sides
    plane = np.ones((h, w), np.uint8)
    cv2.polylines(plane, [np.round(Q * 16).astype(np.int32).reshape(-1, 1, 2)], False, 0, 2, cv2.LINE_8, 4)
    n, lab = cv2.connectedComponents(plane, connectivity=4)
    counts = np.bincount(lab[mc], minlength=n)
    counts[0] = 0
    order = np.argsort(-counts)
    if n < 3 or counts[order[1]] == 0:
        return None
    a, b = _nearest_fill(mc, mc & (lab == order[0]), mc & (lab == order[1]))
    return _orient(m, a, b, y0, y1, x0, x1)


def _crease_line(path, on_line):
    """Straight line col = a + b * row fitted to the rows where the path runs along a crease, dropping rows that
    stray from the bulk of it (an outline it followed for a while); None if there is too little crease."""
    rows = np.flatnonzero(on_line)
    if len(rows) < max(10, 0.15 * len(path)):
        return None
    keep = rows
    for _ in range(3):
        b, a = np.polyfit(keep, path[keep], 1)
        res = np.abs(path[rows] - (a + b * rows))
        lim = max(3.0, 2.5 * np.median(res))
        keep = rows[res <= lim]
        if len(keep) < 10:
            return None
    b, a = np.polyfit(keep, path[keep], 1)
    return a + b * np.arange(len(path))


def _nearest_fill(mask, a, b):
    """Every pixel of `mask` in neither a nor b (the line itself, stray bits) goes to whichever is nearer."""
    rest = mask & ~a & ~b
    if not rest.any():
        return a, b
    da = cv2.distanceTransform((~a).astype(np.uint8), cv2.DIST_L2, 5)
    db = cv2.distanceTransform((~b).astype(np.uint8), cv2.DIST_L2, 5)
    to_a = rest & (da <= db)
    return a | to_a, b | (rest & ~to_a)


def _orient(m, a, b, y0, y1, x0, x1):
    """Full-size (a, b, axis) with a on the left (axis 'x') or on top (axis 'y'); None if a side is empty."""
    if not a.any() or not b.any():
        return None
    ya, xa = np.nonzero(a)
    yb, xb = np.nonzero(b)
    dx, dy = xb.mean() - xa.mean(), yb.mean() - ya.mean()
    axis = 'x' if abs(dx) >= abs(dy) else 'y'
    if (dx if axis == 'x' else dy) < 0:
        a, b = b, a
    out_a = np.zeros_like(m)
    out_b = np.zeros_like(m)
    out_a[y0:y1, x0:x1] = a
    out_b[y0:y1, x0:x1] = b
    return out_a, out_b, axis


def _reflect(m, n, d):
    """m (uint8) mirrored across the line {x : x·n = d} (n a unit normal, x in px)."""
    R = np.eye(2) - 2 * np.outer(n, n)
    M = np.c_[R, 2 * d * n].astype(np.float32)
    return cv2.warpAffine(m, M, (m.shape[1], m.shape[0]), flags=cv2.INTER_NEAREST, borderValue=0)


def _overlap(m, n, d):
    r = _reflect(m, n, d) > 0
    mb = m > 0
    return (mb & r).sum() / max((mb | r).sum(), 1)


def mirror_axis(mc):
    """The line the shape is most nearly mirror-symmetric about: (unit normal n, offset d) with the line
    {x : x·n = d}, x in px of mc. A left/right pair (two breasts, two legs, a torso) mirrors across the line
    between its two halves, whatever the shape's proportions. Searched on a small copy over every direction and
    offset (the line need not pass through the centre of mass: one leg may be drawn wider), then refined.

    Two different axes can be equally symmetric (two equal blocks mirror across the line between them and across
    the line through both): of the axes whose symmetry is within what half a pixel of boundary changes, the pair
    divides where the line crosses the least of the shape, i.e. between its parts rather than through them."""
    h, w = mc.shape
    k = min(1.0, 160.0 / max(h, w))
    small = cv2.resize(mc.astype(np.uint8), (max(int(round(w * k)), 1), max(int(round(h * k)), 1)),
                       interpolation=cv2.INTER_AREA)
    ys, xs = np.nonzero(small)
    c = np.array([xs.mean(), ys.mean()])
    angs = np.deg2rad(np.arange(0, 180, 3))
    K = int(np.ceil(0.25 * max(small.shape)))
    offs = np.arange(-K, K + 1, dtype=np.float64)       # symmetric, so the wrap from 177° to 0° (n -> -n) lines up
    S = np.array([[_overlap(small, np.array([np.cos(a), np.sin(a)]), c @ np.array([np.cos(a), np.sin(a)]) + o)
                   for o in offs] for a in angs])
    # local maxima over direction (wrapping round, the offset reversed) and offset: distinct axes
    ext = np.vstack([S[-1, ::-1], S, S[0, ::-1]])
    ext = np.pad(ext, ((0, 0), (1, 1)), constant_values=-1.0)
    peak = np.ones(S.shape, bool)
    for da in (-1, 0, 1):
        for do in (-1, 0, 1):
            if da or do:
                peak &= S >= ext[1 + da:1 + da + len(angs), 1 + do:1 + do + len(offs)]
    perim = sum(cv2.arcLength(q, True) for q in cv2.findContours(small, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0])
    tie = 0.5 * perim / max(len(xs), 1)                # IoU change from moving the boundary by half a pixel
    P = np.stack([xs, ys], 1).astype(np.float64)
    best = None
    for i, j in zip(*np.nonzero(peak & (S >= S.max() - tie))):
        n = np.array([np.cos(angs[i]), np.sin(angs[i])])
        d = c @ n + offs[j]
        crossed = int((np.abs(P @ n - d) <= 0.5).sum())
        if best is None or crossed < best[0] or (crossed == best[0] and S[i, j] > best[1]):
            best = (crossed, S[i, j], angs[i], d)
    _, _, ang, d = best
    full = mc.astype(np.uint8)
    k2 = min(1.0, 480.0 / max(h, w))
    med = cv2.resize(full, (max(int(round(w * k2)), 1), max(int(round(h * k2)), 1)), interpolation=cv2.INTER_AREA)
    d *= k2 / k
    best = (-1.0, ang, d)
    for a in ang + np.deg2rad(np.arange(-3, 3.01, 0.5)):
        n = np.array([np.cos(a), np.sin(a)])
        for dd in d + np.arange(-3.0 * k2 / k, 3.0 * k2 / k + 1e-9, 0.5):
            sc = _overlap(med, n, dd)
            if sc > best[0]:
                best = (sc, a, dd)
    _, a, d = best
    return np.array([np.cos(a), np.sin(a)]), d / k2


def split_mask(mask, art_rgb):
    """(part_a, part_b, axis) with a on the left (axis 'x') or the top (axis 'y'), or None if the mask is too small
    to split. Parts are full-size bool masks that together are exactly `mask`.

    Made for a left/right pair selected as one region: the cut starts on the pair's mirror axis (mirror_axis)."""
    m = np.asarray(mask, bool)
    if m.sum() < 64:
        return None
    ys, xs = np.nonzero(m)
    pad = 4
    y0, x0 = max(ys.min() - pad, 0), max(xs.min() - pad, 0)
    y1, x1 = min(ys.max() + 1 + pad, m.shape[0]), min(xs.max() + 1 + pad, m.shape[1])
    mc = m[y0:y1, x0:x1]
    P = np.stack([xs - x0, ys - y0], 1).astype(np.float64)
    c = P.mean(0)
    e, d = mirror_axis(mc)                                       # across the cut: the two halves lie along e
    f = np.array([-e[1], e[0]])                                  # along the cut
    t, s = (P - c) @ e, (P - c) @ f
    t0 = d - c @ e
    span = t.max() - t.min()
    w = max(BAND * span, 3.0)

    # cost of cutting at each pixel of the crop: cheap along dark lines and across gaps between pieces
    cost = _line_cost(art_rgb[y0:y1, x0:x1])

    # the frame of the cut: rows run across the axis (s), columns along it (t), one px apart
    S = np.arange(np.floor(s.min()) - 1, np.ceil(s.max()) + 2)
    Tfull = np.arange(np.floor(t.min()) - 1, np.ceil(t.max()) + 2)
    gx = c[0] + Tfull[None, :] * e[0] + S[:, None] * f[0]
    gy = c[1] + Tfull[None, :] * e[1] + S[:, None] * f[1]
    gx, gy = gx.astype(np.float32), gy.astype(np.float32)
    inside = cv2.remap(mc.astype(np.uint8), gx, gy, cv2.INTER_NEAREST, borderValue=0) > 0
    rot_cost = cv2.remap(cost, gx, gy, cv2.INTER_LINEAR, borderValue=1.0)
    # a gap is background with region on both sides of it in the same row
    gap = ~inside & np.maximum.accumulate(inside, 1) & np.maximum.accumulate(inside[:, ::-1], 1)[:, ::-1]
    rot_cost = np.where(gap, LINE_COST, rot_cost)
    lo = int(np.searchsorted(Tfull, t0 - w))
    hi = int(np.searchsorted(Tfull, t0 + w))
    if hi - lo < 3:
        return None
    band = rot_cost[:, lo:hi]
    straight = np.full(len(S), float(np.searchsorted(Tfull, t0) - lo))
    path = _seam(band, straight, max(FIND * span, 6.0))
    on_line = band[np.arange(len(S)), path] <= (1 + LINE_COST) / 2
    line = _crease_line(path, on_line)
    if line is not None:
        path = _seam(band, np.clip(line, 0, hi - lo - 1), max(HOLD * span, 6.0))
    cut_t = Tfull[lo + path]                                     # where the line crosses each row

    # each pixel goes to the side of the line it is on, measured in its own row
    row = np.clip(np.round(s - S[0]).astype(int), 0, len(S) - 1)
    left = t < cut_t[row]
    a = np.zeros_like(mc)
    b = np.zeros_like(mc)
    a[ys - y0, xs - x0] = left
    b[ys - y0, xs - x0] = ~left
    return _orient(m, a, b, y0, y1, x0, x1)

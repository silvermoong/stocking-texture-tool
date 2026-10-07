"""Lines drawn as pixels back into polylines: the 隔开 layer of a guides PSD becomes the user's 隔开 lines again.

Unlike guide_fields.centre_lines, which bins a stroke along its main axis (fine for the near-straight 走向 strokes), a
隔开 line follows an outline and may curve right round, so it is thinned to one pixel and walked end to end.
"""
import cv2
import numpy as np
from scipy import ndimage as ndi

MIN_LEN = 6            # px: shorter traces are specks, not lines

# 8 neighbours clockwise from north: (dy, dx)
_NB = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]


def _shifted(m):
    p = np.pad(m, 1)
    h, w = m.shape
    return [p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] for dy, dx in _NB]


def thin(mask):
    """Zhang-Suen thinning of a bool mask to one-pixel-wide lines."""
    m = mask.astype(bool).copy()
    while True:
        changed = False
        for step in (0, 1):
            P2, P3, P4, P5, P6, P7, P8, P9 = (s.astype(np.uint8) for s in _shifted(m))
            B = P2 + P3 + P4 + P5 + P6 + P7 + P8 + P9
            seq = [P2, P3, P4, P5, P6, P7, P8, P9, P2]
            A = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.uint8) for i in range(8))
            if step == 0:
                c = (P2 * P4 * P6 == 0) & (P4 * P6 * P8 == 0)
            else:
                c = (P2 * P4 * P8 == 0) & (P2 * P6 * P8 == 0)
            kill = m & (B >= 2) & (B <= 6) & (A == 1) & c
            if kill.any():
                m &= ~kill
                changed = True
        if not changed:
            return m


def trace_lines(alpha, threshold=64, smooth=1.5):
    """Polylines (N, 2) in xy, pixel centres, one per stroke of the layer `alpha` (uint8), in drawing order along
    each line. Branches become separate lines."""
    sk = thin(np.asarray(alpha) > threshold)
    nbrs = sum(s.astype(np.uint8) for s in _shifted(sk))
    left = sk.copy()
    out = []

    def walk(y, x):
        path = [(x, y)]
        left[y, x] = False
        while True:
            best = None
            for k, (dy, dx) in enumerate(_NB):          # straight neighbours before diagonal ones
                if k % 2:
                    continue
                yy, xx = y + dy, x + dx
                if 0 <= yy < left.shape[0] and 0 <= xx < left.shape[1] and left[yy, xx]:
                    best = (yy, xx)
                    break
            if best is None:
                for dy, dx in _NB[1::2]:
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < left.shape[0] and 0 <= xx < left.shape[1] and left[yy, xx]:
                        best = (yy, xx)
                        break
            if best is None:
                return path
            y, x = best
            left[y, x] = False
            path.append((x, y))

    # start at line ends first, so a line is walked from one end to the other; whatever is left is a loop
    for y, x in zip(*np.nonzero(sk & (nbrs == 1))):
        if left[y, x]:
            out.append(walk(y, x))
    while left.any():
        y, x = map(int, np.argwhere(left)[0])
        out.append(walk(y, x))
    lines = []
    for P in out:
        if len(P) < MIN_LEN:
            continue
        Q = np.asarray(P, np.float64)
        if smooth > 0:
            Q = np.stack([ndi.gaussian_filter1d(Q[:, 0], smooth, mode='nearest'),
                          ndi.gaussian_filter1d(Q[:, 1], smooth, mode='nearest')], 1)
        Q = _extend(Q)
        Q = cv2.approxPolyDP(Q.astype(np.float32).reshape(-1, 1, 2), 0.4, False).reshape(-1, 2).astype(np.float64)
        lines.append(Q)
    return lines


def _extend(Q, reach=4.0, look=6):
    """Thinning eats a few px off each end of a line; put them back along each end's own direction."""
    if len(Q) <= look:
        return Q
    ends = []
    for tip, inner in ((Q[0], Q[look]), (Q[-1], Q[-1 - look])):
        v = tip - inner
        n = np.hypot(*v)
        ends.append(tip + v / n * reach if n > 0 else tip)
    return np.vstack([ends[0], Q, ends[1]])


def draw_lines(lines, shape, width):
    """uint8 raster (255 on the lines) of polylines (N, 2) in xy pixel centres."""
    out = np.zeros(shape, np.uint8)
    for P in lines:
        p = np.round(np.asarray(P) * 16).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(out, [p], False, 255, width, cv2.LINE_8, 4)
    return out

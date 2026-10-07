"""Left/right symmetry for guide strokes: mirror a part's strokes onto its partner by matching outlines.

    strokes_for_b = mirror_strokes(region_a, region_b, stroke_alpha)

Maps region A onto region B with a mirrored similarity transform (flip, rotate, scale, translate) fitted to the two
outlines, then moves A's strokes through it, clipped to B. Good for a symmetric pair seen roughly face-on (two
thighs from above, two breasts). The fit is to silhouettes, so it inherits any asymmetry in how the pair is drawn,
which is usually what you want; where the pose itself is asymmetric, the user redraws instead.
"""
import cv2
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import cKDTree


def _outline(mask, n=400):
    cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    P = max(cs, key=len)[:, 0, :].astype(float)
    return P[np.linspace(0, len(P) - 1, n).astype(int)]


def fit_mirror(region_a, region_b):
    """3x3 matrix taking A's xy to B's xy: x' = s*R(t)*F*x + d, F = diag(-1, 1)."""
    pa, pb = _outline(region_a), _outline(region_b)
    ca, cb = pa.mean(0), pb.mean(0)
    ta = cKDTree(pa); tb = cKDTree(pb)
    s0 = np.sqrt(region_b.sum() / max(region_a.sum(), 1))

    def apply(p, x):
        t, s, dx, dy = p
        c, si = np.cos(t), np.sin(t)
        R = np.array([[c, -si], [si, c]]) @ np.diag([-1.0, 1.0])
        return s * (x - ca) @ R.T + cb + [dx, dy]

    def back(p, y):
        t, s, dx, dy = p
        c, si = np.cos(t), np.sin(t)
        R = np.array([[c, -si], [si, c]]) @ np.diag([-1.0, 1.0])
        return (y - cb - [dx, dy]) @ R / s + ca

    def resid(p):
        # symmetric chamfer: A's outline onto B, and B's outline back onto A
        return np.r_[tb.query(apply(p, pa))[0], ta.query(back(p, pb))[0] * p[1]]

    best = None
    for t0 in np.deg2rad([-20, -10, 0, 10, 20]):
        r = least_squares(resid, [t0, s0, 0.0, 0.0], loss='soft_l1', f_scale=5.0)
        if best is None or r.cost < best.cost:
            best = r
    t, s, dx, dy = best.x
    c, si = np.cos(t), np.sin(t)
    M2 = s * np.array([[c, -si], [si, c]]) @ np.diag([-1.0, 1.0])
    M = np.eye(3)
    M[:2, :2] = M2
    M[:2, 2] = cb + [dx, dy] - M2 @ ca
    return M, float(np.median(tb.query(apply(best.x, pa))[0]))


def mirror_strokes(region_a, region_b, stroke_alpha):
    """Strokes inside A, mirrored into B; returns (alpha for B, fit rms px)."""
    M, rms = fit_mirror(region_a, region_b)
    h, w = stroke_alpha.shape
    src = np.where(region_a, stroke_alpha, 0).astype(np.uint8)
    out = cv2.warpAffine(src, M[:2], (w, h), flags=cv2.INTER_LINEAR, borderValue=0)
    return np.where(region_b, out, 0).astype(np.uint8), rms

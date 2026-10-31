"""Frozen section evidence for reducing excess zone absorption, not normal recovery.

The 0.04 deadband and support rules preserve the accepted candidate. This field
must not replace the shared facing used by skin warmth, non-zone shading or glints.
"""
import threading

import numpy as np


class OilyContext:
    """Read-only maps with an instance-local, retryable absorption cache.

    The factory owns only deferred look evidence and references to scene inputs;
    it is released after a complete field has been successfully published.
    """
    def __init__(self, maps, absorption_facing=None, *, absorption_factory=None):
        self._maps = maps
        for field in maps:
            field.setflags(write=False)
        if absorption_facing is not None:
            absorption_facing.setflags(write=False)
        self._absorption_facing = absorption_facing
        self._absorption_factory = absorption_factory
        self._lock = threading.Lock()

    @property
    def maps(self):
        return self._maps

    @property
    def absorption_facing(self):
        with self._lock:
            if self._absorption_facing is None:
                field = self._absorption_factory()
                if field.shape != self.maps[4].shape or not np.isfinite(field).all():
                    raise ValueError('absorption_facing must be finite and shaped like facing')
                field.setflags(write=False)
                self._absorption_facing = field
                self._absorption_factory = None
            return self._absorption_facing


def _section_evidence(Vg, Ag, hidden, scale, frame):
    k, c, h, hf, hmed, tilt, whole, trust = frame
    n = len(c)
    old_u = np.clip((Ag - c[k]) / hf[k], -1, 1)
    before = np.sqrt(1 - old_u * old_u) * np.cos(tilt[k])
    order = np.lexsort((Ag, k))
    sorted_k, sorted_a = k[order], Ag[order]
    starts = np.searchsorted(sorted_k, np.arange(n))
    ends = np.searchsorted(sorted_k, np.arange(n), side='right')
    count = ends - starts
    present = count > 0
    lo, hi = np.zeros(n), np.zeros(n)
    for q, edge in ((0.02, lo), (0.98, hi)):
        ids = starts[present] + np.floor(q * (count[present] - 1) + 0.5).astype(int)
        edge[present] = sorted_a[ids]
    half = (hi - lo) / 2
    valid = present & (count >= 12) & (half > 0)
    bmin, bmax = np.full(n, np.inf), np.full(n, -np.inf)
    np.minimum.at(bmin, k[hidden], Ag[hidden])
    np.maximum.at(bmax, k[hidden], Ag[hidden])
    bv = max(2.0, 2.0 * scale)
    valid &= (bmin > lo + 2 * bv) & (bmax < hi - 2 * bv)
    cells = np.clip(np.floor(12 * (Ag - lo[k]) / np.maximum(hi[k] - lo[k], 1e-12)), 0, 11).astype(int)
    occupied = np.zeros((n, 12), bool)
    occupied[k, cells] = True
    valid &= occupied.sum(axis=1) >= 10
    local_lo, local_hi = lo.copy(), hi.copy()
    supported = np.zeros(n, bool)
    for b in np.flatnonzero(valid):
        js = np.arange(max(0, b - 2), min(n, b + 3))
        js = js[valid[js]]
        if len(js) < 3:
            continue
        med_lo, med_hi = np.median(lo[js]), np.median(hi[js])
        if max(abs(lo[b] - med_lo), abs(hi[b] - med_hi)) > 0.10 * half[b]:
            continue
        weights = np.exp(-0.5 * (js - b) ** 2)
        local_lo[b] = np.average(lo[js], weights=weights)
        local_hi[b] = np.average(hi[js], weights=weights)
        supported[b] = True
    slack = 0.04 * half
    left = np.clip(c - hf, local_lo - slack, local_lo + slack)
    right = np.clip(c + hf, local_hi - slack, local_hi + slack)
    supported &= np.isfinite(hf) & (right > left)
    return lo, hi, supported, before


def absorption_facing(Vg, Ag, hidden, scale, frame):
    """One-sided absorption correction using an existing look-pass frame, without mutation."""
    lo, hi, supported, before = _section_evidence(Vg, Ag, hidden, scale, frame)
    k, c, h, hf, hmed, tilt, whole, trust = frame
    half = (hi - lo) / 2
    raw_u = (Ag - (lo[k] + hi[k]) / 2) / np.maximum(half[k], 1e-12)
    old_u = (Ag - c[k]) / hf[k]
    margin = 0.04
    inside = np.clip((1 - np.abs(raw_u)) / margin, 0, 1)
    excess = np.abs(old_u) - np.abs(raw_u)
    activation = np.clip((excess - margin) / margin, 0, 1)
    activation = activation * activation * (3 - 2 * activation)
    gate = supported[k] * inside * activation
    reference_squared = (1 - np.clip(raw_u, -1, 1) ** 2) * np.cos(tilt[k]) ** 2
    original_squared = before ** 2
    gain = gate * np.maximum(reference_squared - original_squared, 0)
    result = before.copy()
    changed = gain > 0
    result[changed] = np.sqrt(original_squared[changed] + gain[changed])
    return result

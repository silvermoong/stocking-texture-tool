"""Position-only corrections to existing coupled main/floor curve samples.

A complementary pair may supply an evidence-supported connection; a single fading
identity may follow its measured near-top interval. Neither creates an observation,
merges identities, changes strengths/widths, or resamples the renderer's curve.
Unknown, ambiguous, linked, or unsafe paths keep the original geometry.

All context and scratch arrays are per call. Budgets are fixed experimental gates,
not calibrated probabilities. The short unobserved tail carries a supported offset;
only additional displacement is capped, and it remains artistic extrapolation.
"""
from dataclasses import dataclass

import cv2
import numpy as np
from scipy.interpolate import CubicHermiteSpline
from scipy.ndimage import map_coordinates
from scipy.optimize import Bounds, LinearConstraint, minimize
from scipy.signal import find_peaks


@dataclass(frozen=True)
class PieceEvidence:
    tracks: tuple
    fit: np.ndarray
    den: np.ndarray
    noise: float
    middle: np.ndarray | None
    hmed: float
    wlen: float
    a0: float
    ab: float
    t: np.ndarray
    Ag: np.ndarray
    xs: np.ndarray
    ys: np.ndarray
    shape: tuple
    cut: np.ndarray | None = None
    linked: bool = False


@dataclass(frozen=True)
class PositionEdit:
    sample_ids: np.ndarray
    xy: np.ndarray
    reason: str
    evidence_rows: int = 0
    source: str = 'unchanged'

    def apply(self, original):
        if not len(self.sample_ids):
            return original
        ids, xy = self.sample_ids, self.xy
        if (ids.ndim != 1 or ids.dtype.kind not in 'iu' or
                len(np.unique(ids)) != len(ids) or ids.min() < 0 or ids.max() >= len(original) or
                xy.shape != (len(ids), 2) or xy.dtype != original.dtype or not np.isfinite(xy).all()):
            raise ValueError('Invalid fixed-sample position edit')
        result = original.copy()
        result[ids] = xy
        return result


def unchanged(xy, reason, evidence_rows=0):
    return PositionEdit(np.empty(0, np.int64), np.empty((0, 2), xy.dtype), reason, evidence_rows)


def _fields(context):
    mask = np.zeros(context.shape, np.float32)
    mask[context.ys, context.xs] = 1.
    qmap = np.zeros_like(mask)
    qmap[context.ys, context.xs] = context.t
    amap = np.zeros_like(mask)
    amap[context.ys, context.xs] = context.Ag
    return mask, qmap, amap


def refine_curve(context, xy):
    """Return an atomic fixed-ID edit, or an explicit conservative rejection.

    Only call for the floor-coupled main track, after _curve and before _outside.
    Input arrays are borrowed read-only for this call; no state or files are retained.
    """
    if context.linked:
        return unchanged(xy, 'linked_piece_preserved')
    if len(context.tracks) == 1:
        return _follow_single(context, xy)
    if len(context.tracks) == 2:
        return _connect_pair(context, xy)
    return unchanged(xy, 'unsupported_identity_count')


@dataclass(frozen=True)
class AssociationPolicy:
    minimum_support: float = 0.3
    maximum_deficit_noise: float = 4.0
    maximum_gap_rows: int = 8
    maximum_gap_halfwidths: float = 1.5
    maximum_step_cells: float = 3.6
    maximum_turn_cells: float = 1.2
    maximum_endpoint_uncertainty_cells: float = 2.4
    maximum_abs_u: float = 1.1
    unsupported_extrapolation_u: float = 0.2
    dense_step_px: float = 0.25
    strong_threshold: float = 0.5
    endpoint_tangent_residual: float = 1e-07
    monotone_q_tolerance: float = 0.001
ASSOCIATION_POLICY = AssociationPolicy()

def near_top_intervals(profile, support, noise, policy=ASSOCIATION_POLICY):
    good = (support > policy.minimum_support) & np.isfinite(profile) & np.isfinite(support)
    edges = np.flatnonzero(np.diff(np.r_[False, good, False].astype(int)))
    intervals = []
    for a, b in zip(edges[::2], edges[1::2]):
        if b - a < 5:
            continue
        peaks, props = find_peaks(profile[a:b], prominence=0.0)
        runs = []
        for relative, prominence in zip(peaks, props['prominences']):
            j = int(a + relative)
            local = max(float(noise) / np.sqrt(support[j]), 1e-08)
            if prominence <= policy.maximum_deficit_noise * local:
                continue
            level = profile[j] - policy.maximum_deficit_noise * local
            left = right = j
            while left > a and profile[left - 1] >= level:
                left -= 1
            while right < b - 1 and profile[right + 1] >= level:
                right += 1
            if left == a or right == b - 1:
                continue
            runs.append([left + 0.5, right + 0.5])
        merged = []
        for left, right in sorted(runs):
            if merged and merged[-1][1] >= left:
                merged[-1][1] = max(merged[-1][1], right)
            else:
                merged.append([left, right])
        intervals.extend(merged)
    return intervals

def solve_corridor(sections, start, end, start_velocity, end_velocity, policy=ASSOCIATION_POLICY):
    sections = [[list(interval) for interval in row] for row in sections]
    if len(sections) < 3:
        return {'accepted': False, 'reason': 'insufficient_gap'}
    sections[0] = [p for p in sections[0] if p[0] <= start <= p[1]]
    sections[-1] = [p for p in sections[-1] if p[0] <= end <= p[1]]

    def reachable(a, b):
        return max(a[0] - b[1], b[0] - a[1], 0.0) <= policy.maximum_step_cells
    for _ in range(len(sections)):
        count = sum(map(len, sections))
        for q in range(1, len(sections)):
            sections[q] = [p for p in sections[q] if any((reachable(p, b) for b in sections[q - 1]))]
        for q in range(len(sections) - 2, -1, -1):
            sections[q] = [p for p in sections[q] if any((reachable(p, b) for b in sections[q + 1]))]
        if count == sum(map(len, sections)):
            break
    if any((not row for row in sections)):
        return {'accepted': False, 'reason': 'no_endpoint_connected_corridor'}
    if any((len(row) != 1 for row in sections)):
        return {'accepted': False, 'reason': 'competing_reachable_intervals'}
    lo = np.array([row[0][0] for row in sections])
    hi = np.array([row[0][1] for row in sections])
    lo[0] = hi[0] = start
    lo[-1] = hi[-1] = end
    n = len(lo)
    d1 = np.diff(np.eye(n), axis=0)
    d2 = np.diff(np.eye(n), n=2, axis=0)
    constraints = [LinearConstraint(d1, -policy.maximum_step_cells, policy.maximum_step_cells), LinearConstraint(d2, -policy.maximum_turn_cells, policy.maximum_turn_cells), LinearConstraint(d1[:1], start_velocity - policy.maximum_turn_cells, start_velocity + policy.maximum_turn_cells), LinearConstraint(d1[-1:], end_velocity - policy.maximum_turn_cells, end_velocity + policy.maximum_turn_cells)]

    def energy(z):
        return float(np.sum((d2 @ z) ** 2) + 0.01 * np.sum((d1 @ z) ** 2))
    result = minimize(energy, np.clip(np.linspace(start, end, n), lo, hi), method='SLSQP', bounds=Bounds(lo, hi), constraints=constraints, options={'maxiter': 200, 'ftol': 1e-10})
    z = result.x
    steps, turns = (d1 @ z, d2 @ z)
    residual = max(float(np.max(lo - z)), float(np.max(z - hi)), float(np.max(np.abs(steps))) - policy.maximum_step_cells, float(np.max(np.abs(turns))) - policy.maximum_turn_cells, abs(float(steps[0]) - start_velocity) - policy.maximum_turn_cells, abs(end_velocity - float(steps[-1])) - policy.maximum_turn_cells)
    accepted = bool(result.success and np.isfinite(z).all() and (residual <= 1e-07))
    return {'accepted': accepted, 'reason': 'position_corridor' if accepted else 'infeasible_corridor', 'solver_message': str(result.message), 'cells': z.tolist(), 'intervals': sections, 'maximum_step_cells': float(np.max(np.abs(steps))), 'maximum_turn_cells': float(np.max(np.abs(turns))), 'constraint_residual': float(residual)}

def photometry(fit, den, noise, qs, cells, policy=ASSOCIATION_POLICY):
    axis = np.arange(fit.shape[1]) + 0.5
    deficits, supports = ([], [])
    for q, cell in zip(qs, cells):
        if not np.isfinite(q + cell) or not 0 <= q <= len(fit) - 1 or (not axis[0] <= cell <= axis[-1]):
            return {'accepted': False, 'reason': 'outside_evidence_domain'}
        left = int(np.floor(q))
        right = min(left + 1, len(fit) - 1)
        values = []
        for row in (left, right):
            support = float(np.interp(cell, axis, den[row]))
            light = float(np.interp(cell, axis, fit[row]))
            window = (np.abs(axis - cell) <= 10.0) & (den[row] > policy.minimum_support)
            top = float(fit[row, window].max()) if window.any() else float('inf')
            local = max(float(noise) / np.sqrt(max(support, 0.05)), 1e-08)
            values.append(np.array([support, top - light, local]))
        fraction = q - left
        support, deficit, local = (1 - fraction) * values[0] + fraction * values[1]
        supports.append(float(support))
        deficits.append(float(deficit / local))
    accepted = bool(supports and min(supports) >= policy.minimum_support and (max(deficits) <= policy.maximum_deficit_noise + 1e-07))
    return {'accepted': accepted, 'reason': 'supported_near_top' if accepted else 'unsupported_or_deep_valley', 'minimum_support': min(supports) if supports else None, 'maximum_deficit_noise': max(deficits) if deficits else None}

def select_association(tracks, fit, den, noise, middle, hmed, row_length, linked=False, blocked_rows=(), policy=ASSOCIATION_POLICY):

    def reject(reason, **detail):
        return {'accepted': False, 'reason': reason, **detail}
    if linked:
        return reject('linked_piece_preserved')
    if middle is None:
        return reject('untrusted_geometry')
    if len(tracks) != 2:
        return reject('unsupported_identity_count', observed_tracks=len(tracks))
    if any((len(tr) != 6 or len(tr[0]) < 4 for tr in tracks)):
        return reject('unsupported_observation_layout')
    order = sorted(range(len(tracks)), key=lambda k: float(tracks[k][0][1]))
    first, second = (tracks[k] for k in order)
    if first[0][-2] >= second[0][1]:
        return reject('overlapping_observed_identities')
    q0, q1 = (float(first[0][-2]), float(second[0][1]))
    if not (q0.is_integer() and q1.is_integer()):
        return reject('noninteger_observation_rows')
    q0, q1 = (int(q0), int(q1))
    gap = q1 - q0
    if gap < 2:
        return reject('no_missing_observation_row')
    if gap > policy.maximum_gap_rows or gap * row_length > policy.maximum_gap_halfwidths * hmed:
        return reject('gap_too_long', gap_rows=gap)
    if any((q0 <= q <= q1 for q in blocked_rows)):
        return reject('divider')
    if q0 < 0 or q1 >= len(fit):
        return reject('outside_fit')
    axis = np.arange(fit.shape[1]) + 0.5
    endpoint_records = []
    for tr, index, neighbor in ((first, -2, -3), (second, 1, 2)):
        for k in (index, neighbor):
            q, cell = (float(tr[0][k]), float(tr[1][k]))
            if not q.is_integer() or not 0 <= q < len(fit) or (not axis[0] <= cell <= axis[-1]):
                return reject('endpoint_outside_fit')
            q = int(q)
            if tr[4][k] < policy.minimum_support or tr[5][k] > policy.maximum_endpoint_uncertainty_cells:
                return reject('endpoint_position_uncertain')
            if abs(float(np.interp(cell, axis, middle[q]))) > policy.maximum_abs_u:
                return reject('endpoint_outside_trusted_limb')
        if abs(float(tr[0][index] - tr[0][neighbor])) != 1.0:
            return reject('missing_endpoint_tangent_support')
        photo = photometry(fit, den, noise, [float(tr[0][index])], [float(tr[1][index])], policy)
        if not photo['accepted']:
            return reject('endpoint_not_near_top', photometry=photo)
        endpoint_records.append({'row': float(tr[0][index]), 'cell': float(tr[1][index]), 'support': float(tr[4][index]), 'uncertainty_cells': float(tr[5][index]), 'render_strength': float(tr[2][index])})
    sections = [near_top_intervals(fit[q], den[q], noise, policy) for q in range(q0, q1 + 1)]
    velocity0 = float(first[1][-2] - first[1][-3])
    velocity1 = float(second[1][2] - second[1][1])
    answer = solve_corridor(sections, float(first[1][-2]), float(second[1][1]), velocity0, velocity1, policy)
    if not answer['accepted']:
        return reject(answer['reason'], corridor=answer, endpoints=endpoint_records)
    qs = np.linspace(q0, q1, 1 + 100 * gap)
    cells = np.interp(qs, np.arange(q0, q1 + 1), answer['cells'])
    photo = photometry(fit, den, noise, qs, cells, policy)
    if not photo['accepted']:
        return reject('interpolated_corridor_photometry', photometry=photo)
    return {'accepted': True, 'reason': 'unique_complementary_position_evidence', 'track_indices': order, 'rows': list(range(q0, q1 + 1)), 'endpoints': endpoint_records, 'endpoint_velocities': [velocity0, velocity1], 'corridor': answer, 'photometry': photo, 'identity_claim': 'Two unchanged observations; artistic floor association only'}

@dataclass(frozen=True)
class Evidence:
    row: int
    cell: float
    radius: float
    weight: float
    prominence: float
    noise: float
    support: float
    valid: bool
    reason: str

def candidates(fit, den, noise):
    fit = np.asarray(fit, float)
    den = np.asarray(den, float)
    assert fit.shape == den.shape and fit.ndim == 2
    result = []
    for q, (profile, support) in enumerate(zip(fit, den)):
        available = np.isfinite(profile) & np.isfinite(support) & (support > 0.05)
        bounds = np.flatnonzero(np.diff(np.r_[False, available, False].astype(int)))
        found = []
        for lo, hi in zip(bounds[::2], bounds[1::2]):
            f = profile[lo:hi]
            if len(f) < 5:
                continue
            peaks, props = find_peaks(f, prominence=0, plateau_size=1)
            for i, j in enumerate(peaks):
                cell = int(lo + j)
                local = max(float(noise) / np.sqrt(max(float(support[cell]), 0.05)), 1e-08)
                off = 0.0
                bend = float(f[j - 1] - 2 * f[j] + f[j + 1])
                if props['plateau_sizes'][i] == 1 and bend < 0:
                    off = float(np.clip(0.5 * (f[j - 1] - f[j + 1]) / bend, -0.5, 0.5))
                x = cell + 0.5 + off
                left = right = int(j)
                level = float(f[j] - 4 * local)
                while left > 0 and f[left - 1] >= level:
                    left -= 1
                while right < len(f) - 1 and f[right + 1] >= level:
                    right += 1
                radius = 0.5 + max(abs(lo + left + 0.5 - x), abs(lo + right + 0.5 - x))
                prom = float(props['prominences'][i])
                other = any((left <= k <= right and k != j for k in peaks))
                reason = 'support_boundary' if left == 0 or right == len(f) - 1 else 'multiple_near_top_peaks' if other else 'insufficient_prominence' if prom <= 4 * local else 'ok'
                valid = reason == 'ok'
                weight = float(np.exp(-radius ** 2)) if valid else 0.0
                found.append(Evidence(q, x, float(radius), weight, prom, local, float(support[cell]), valid, reason))
        result.append(found)
    return result

@dataclass(frozen=True)
class FollowPolicy:
    strong: float = 0.5
    fully_follow_below: float = 0.25
    raw_support: float = 0.3
    max_uncertainty_cells: float = 2.0
    near_top_noise: float = 4.0
    max_near_top_radius_cells: float = 4.0
    minimum_observations: int = 4
    maximum_row_jump_cells: float = 3.6
    minimum_departure_px: float = 1.0
    max_unobserved_extension_rows: float = 2.5
    max_unobserved_extra_halfwidth: float = 0.2
    extension_decay_rows: float = 1.0
    segment_probe_px: float = 0.25
    monotonic_tolerance: float = 0.001
    mask_support: float = 0.999
    maximum_segment_stretch: float = 3.0
FOLLOW_POLICY = FollowPolicy()

class _PositionRejected(Exception):
    """Expected evidence or geometry rejection, not an internal computation error."""


def require(ok, reason):
    if not ok:
        raise _PositionRejected(reason)

def interpolate(q, run):
    return np.column_stack([np.interp(q, run[0], run[1][:, k]) for k in (0, 1)])

def _sample_exact(image, xy):
    # Zero-slack interval checks need exact bilinear interpolation, unlike remap's
    # 1/32-pixel table. The paired-track path retains its original grid sampler.
    return map_coordinates(np.asarray(image, float), np.asarray(xy).T[::-1], order=1, mode='constant', cval=0.0, prefilter=False)

def project_observed(target, q, q0, q1, eq, lows, highs, peaks, mask, qmap, amap, context):
    ids = np.flatnonzero((q >= q0) & (q <= q1))
    points = target[ids].copy()
    wanted_q = q[ids]
    support = _sample_exact(mask, points)
    require(np.all(support > FOLLOW_POLICY.mask_support), 'observed_projection_outside_piece')
    cell = (_sample_exact(amap, points) / support - context.a0) / context.ab
    peak = np.interp(wanted_q, eq, peaks)
    low = np.interp(wanted_q, eq, lows)
    high = np.interp(wanted_q, eq, highs)
    radius = np.where(cell < peak, peak - low, high - peak)
    require(np.all(radius > 0), 'zero_width_raw_interval')
    offset = (cell - peak) / radius
    # Smoothly project into the measured interval in the same (q, A) domain.
    desired = peak + radius * np.tanh(offset)
    wanted_a = context.a0 + context.ab * desired

    def coordinates(xy):
        s = _sample_exact(mask, xy)
        require(np.all(s > FOLLOW_POLICY.mask_support), 'projection_iteration_outside_piece')
        return np.column_stack([_sample_exact(qmap, xy) / s, _sample_exact(amap, xy) / s])
    for _ in range(8):
        current = coordinates(points)
        residual = np.column_stack([wanted_q, wanted_a]) - current
        jac = np.stack([(coordinates(points + [1.0, 0.0]) - coordinates(points - [1.0, 0.0])) / 2, (coordinates(points + [0.0, 1.0]) - coordinates(points - [0.0, 1.0])) / 2], axis=2)
        require(np.all(np.abs(np.linalg.det(jac)) > 1e-10), 'singular_local_q_a_mapping')
        step = np.linalg.solve(jac, residual[..., None])[..., 0]
        points += step
        if np.max(np.abs(step)) < 1e-07:
            break
    residual = coordinates(points) - np.column_stack([wanted_q, wanted_a])
    require(np.max(np.abs(residual)) < 1e-05, 'local_q_a_projection_did_not_converge')
    projected = target.copy()
    projected[ids] = points
    return (projected, float(np.linalg.norm(points - target[ids], axis=1).max(initial=0)))

def mapped(curve, mask, qmap, minimum_q):
    support = _sample_exact(mask, curve)
    q = _sample_exact(qmap, curve) / np.maximum(support, 1e-08)
    ids = np.flatnonzero(support > FOLLOW_POLICY.mask_support)
    eligible = np.flatnonzero(q[ids] >= minimum_q)
    require(len(eligible) > 0, 'no_mapping_at_suffix_start')
    ids = ids[max(0, int(eligible[0]) - 1):]
    require(len(ids) >= 3, 'insufficient_screen_mapping')
    require(np.all(np.diff(ids) == 1), 'disconnected_screen_mapping')
    require(np.all(np.diff(q[ids]) >= -FOLLOW_POLICY.monotonic_tolerance), 'nonmonotone_screen_mapping')
    result = np.interp(np.arange(len(curve)), ids, q[ids])
    for end, other, subset in [(ids[0], ids[min(16, len(ids) - 1)], np.arange(ids[0])), (ids[-1], ids[max(0, len(ids) - 17)], np.arange(ids[-1] + 1, len(curve)))]:
        slope = (q[end] - q[other]) / (end - other)
        result[subset] = q[end] + (subset - end) * slope
    return (result, ids, support)

def evidence_for_track(track, fit, den, noise, record):
    from . import oily
    rows, tu, st, wd, su, dl = track
    require(len(rows) >= FOLLOW_POLICY.minimum_observations + 2, 'short_original_identity')
    require(np.all(np.diff(rows) == 1), 'nonconsecutive_original_identity')
    require(np.all(su[1:-1] > 0), 'original_identity_contains_unseen_rows')
    strong = np.flatnonzero(st[1:-1] >= FOLLOW_POLICY.strong) + 1
    require(len(strong) > 0, 'no_strong_identity_anchor')
    start = int(strong[-1])
    require(len(rows) - 1 - start >= FOLLOW_POLICY.minimum_observations, 'no_long_fading_suffix')
    ev = candidates(fit, den, noise)
    checks = []
    record['evidence'] = checks
    for k in range(start, len(rows) - 1):
        q = int(rows[k])
        require(0 <= q < len(fit), 'nonpad_row_outside_fit')
        valid = [p for p in ev[q] if p.valid]
        require(len(valid) == 1, 'missing_or_competing_raw_peak')
        peak = valid[0]
        require(peak.radius <= FOLLOW_POLICY.max_near_top_radius_cells, 'raw_top_too_broad')
        require(su[k] >= FOLLOW_POLICY.raw_support and dl[k] <= FOLLOW_POLICY.max_uncertainty_cells, 'uncertain_original_position')
        cell = int(np.clip(np.floor(peak.cell), 0, fit.shape[1] - 1))
        available = den[q] > 0.05
        lo = hi = cell
        while lo > 0 and available[lo - 1]:
            lo -= 1
        while hi + 1 < len(available) and available[hi + 1]:
            hi += 1
        env = oily._envelope(fit[q, lo:hi + 1], max(1, int(round(oily.SHADE * oily.CELLS / 2))))
        require(float(env[cell - lo] - fit[q, cell]) <= 1e-12, 'shadow_strip_not_envelope_peak')
        local = max(float(noise) / np.sqrt(max(float(den[q, cell]), 0.05)), 1e-08)
        level = float(fit[q, cell] - FOLLOW_POLICY.near_top_noise * local)
        l = r = cell
        while l > lo and fit[q, l - 1] >= level:
            l -= 1
        while r < hi and fit[q, r + 1] >= level:
            r += 1
        require(l > lo and r < hi, 'near_top_reaches_support_boundary')
        # Subcell crossings of the measured level, not rounded cell centres.
        low = l + 0.5 - (fit[q, l] - level) / (fit[q, l] - fit[q, l - 1])
        high = r + 0.5 + (fit[q, r] - level) / (fit[q, r] - fit[q, r + 1])
        require(low <= tu[k] <= high, 'original_identity_not_on_raw_top')
        checks.append(dict(q=q, cell=float(tu[k]), low=low, high=high))
    require(np.max(np.abs(np.diff([p['cell'] for p in checks]))) <= FOLLOW_POLICY.maximum_row_jump_cells, 'discontinuous_raw_peak_motion')
    return checks

def _follow_single(context, xy):
    from . import oily
    rec = {}
    try:
        fit, den, noise = (context.fit, context.den, context.noise)
        track = context.tracks[0]
        checks = evidence_for_track(track, fit, den, noise, rec)
        rows, tu, st, wd, su, dl = track
        t, Ag, xs, ys = (context.t, context.Ag, context.xs, context.ys)
        mask, qmap, amap = _fields(context)
        original = oily._curve(rows, context.a0 + context.ab * tu, st, dl, su, t, Ag, xs, ys, context.ab, floor=oily.TOL_REL * context.hmed)
        require(original is not None, 'missing_original_screen_curve')
        q0, q1 = (float(checks[0]['q']), float(checks[-1]['q']))
        q, valid, support = mapped(xy, mask, qmap, q0)
        oq, oi, _ = mapped(original, mask, qmap, q0)
        require(oq[oi[0]] <= q0 and oq[oi[-1]] >= q1, 'observed_screen_curve_does_not_cover_evidence')
        require(q[valid[0]] <= q0 and q[valid[-1]] >= q1, 'drawn_curve_does_not_cover_evidence')
        require(float(t.max()) - q1 <= FOLLOW_POLICY.max_unobserved_extension_rows, 'long_unobserved_tail')
        obsrun = (oq[oi], original[oi])
        target = interpolate(q, obsrun)
        eq = np.array([v['q'] for v in checks], float)
        lows = np.array([v['low'] for v in checks])
        highs = np.array([v['high'] for v in checks])
        peaks = np.array([v['cell'] for v in checks])
        target, _ = project_observed(target, q, q0, q1, eq, lows, highs, peaks, mask, qmap, amap, context)
        weight = np.clip((FOLLOW_POLICY.strong - np.interp(q, rows, st)) / (FOLLOW_POLICY.strong - FOLLOW_POLICY.fully_follow_below), 0.0, 1.0)
        weight = weight * weight * (3 - 2 * weight)
        weight[q < q0] = 0.0
        bc = (_sample_exact(amap, xy) / np.maximum(support, 1e-08) - context.a0) / context.ab
        peak = np.interp(q, eq, peaks)
        radius = np.where(bc < peak, peak - np.interp(q, eq, lows), np.interp(q, eq, highs) - peak)
        uncertainty = np.interp(q, rows, dl)
        margin = radius - uncertainty
        active = np.clip((np.abs(bc - peak) - uncertainty) / np.maximum(margin, 1e-12), 0.0, 1.0)
        active = active * active * (3 - 2 * active)
        weight *= active
        corrected = xy + weight[:, None] * (target - xy)
        evidence = (q >= q0) & (q <= q1) & (support > FOLLOW_POLICY.mask_support)
        departure = np.maximum(np.interp(q, eq, lows) - bc, bc - np.interp(q, eq, highs)) * context.ab
        rec['baseline_departure_px'] = float(np.max(departure[evidence], initial=0))
        require(rec['baseline_departure_px'] > FOLLOW_POLICY.minimum_departure_px, 'baseline_already_within_position_interval')
        # Carry the evidence-supported offset; cap only the subsequent motion.
        # Returning to the old floor here would undo the accepted fading suffix.
        endpoint_q = np.array([q1 - 0.25, q1])
        endpoints, _ = project_observed(interpolate(endpoint_q, obsrun), endpoint_q, q0, q1, eq, lows, highs, peaks, mask, qmap, amap, context)
        bases = interpolate(endpoint_q, (q[valid], xy[valid]))
        ew = np.clip((FOLLOW_POLICY.strong - np.interp(endpoint_q, rows, st)) / (FOLLOW_POLICY.strong - FOLLOW_POLICY.fully_follow_below), 0.0, 1.0)
        ew = ew * ew * (3 - 2 * ew)
        ebs = _sample_exact(mask, bases)
        ebc = (_sample_exact(amap, bases) / ebs - context.a0) / context.ab
        ep = np.interp(endpoint_q, eq, peaks)
        er = np.where(ebc < ep, ep - np.interp(endpoint_q, eq, lows), np.interp(endpoint_q, eq, highs) - ep)
        eu = np.interp(endpoint_q, rows, dl)
        ea = np.clip((np.abs(ebc - ep) - eu) / np.maximum(er - eu, 1e-12), 0.0, 1.0)
        ew *= ea * ea * (3 - 2 * ea)
        offsets = ew[:, None] * (endpoints - bases)
        delta = offsets[-1]
        slope = (offsets[-1] - offsets[0]) / 0.25
        cap = FOLLOW_POLICY.max_unobserved_extra_halfwidth * context.hmed
        speed = float(np.linalg.norm(slope))
        tau = min(FOLLOW_POLICY.extension_decay_rows, cap / max(speed, 1e-12))
        tail = q > q1
        extra = tau * (1 - np.exp(-np.maximum(q[tail] - q1, 0) / tau))[:, None] * slope
        corrected[tail] = xy[tail] + delta + extra
        ids = np.flatnonzero(np.any(corrected != xy, axis=1))
        require(len(ids) > 0, 'zero_edit')
        length = np.linalg.norm(np.diff(corrected, axis=0), axis=1)
        oldlength = np.linalg.norm(np.diff(xy, axis=0), axis=1)
        stretch = length / np.maximum(oldlength, 1e-08)
        require(float(stretch.max()) <= FOLLOW_POLICY.maximum_segment_stretch, 'segment_stretch_limit')
        begin = max(0, int(ids[0]) - 1)
        end = min(len(xy), int(ids[-1]) + 2)
        require(np.array_equal(corrected[:begin], xy[:begin]) and np.array_equal(corrected[end:], xy[end:]), 'unmodified_prefix_or_suffix_changed')
        dense = np.concatenate([a + np.linspace(0, 1, max(2, int(np.ceil(d / FOLLOW_POLICY.segment_probe_px)) + 1))[:, None] * (b - a) for a, b, d in zip(corrected[begin:end - 1], corrected[begin + 1:end], length[begin:end - 1])])
        h, w = mask.shape
        inside = (dense[:, 0] >= 0) & (dense[:, 0] <= w - 1) & (dense[:, 1] >= 0) & (dense[:, 1] <= h - 1)
        visible = dense[inside]
        ds = _sample_exact(mask, visible)
        require(np.all(ds > FOLLOW_POLICY.mask_support), 'modified_path_leaves_piece_inside_frame')
        require(context.cut is None or not np.any(_sample_exact(context.cut, visible) > 0), 'modified_path_crosses_cut')
        dq = _sample_exact(qmap, visible) / ds
        require(np.all(np.diff(dq) >= -FOLLOW_POLICY.monotonic_tolerance), 'modified_path_nonmonotone')
        ac = (_sample_exact(amap, visible) / ds - context.a0) / context.ab
        tested = (dq >= q0) & (dq <= q1)
        violation = np.maximum(np.interp(dq, eq, lows) - ac, ac - np.interp(dq, eq, highs))
        rec['candidate_interval_violation_cells'] = float(np.max(violation[tested], initial=0))
        require(rec['candidate_interval_violation_cells'] <= 0, 'candidate_outside_raw_near_top_interval')
        return PositionEdit(ids, corrected[ids].astype(xy.dtype), 'continuous_single_track_follow', len(checks), 'observed_position_with_bounded_artistic_tail')
    except _PositionRejected as error:
        return unchanged(xy, str(error), len(rec.get('evidence', ())))

def _sample_grid(image, xy):
    return cv2.remap(np.asarray(image, np.float32), xy[:, 0].astype(np.float32)[None, :], xy[:, 1].astype(np.float32)[None, :], cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0).ravel()

def parameter(curve, mask, qmap, target):
    support = _sample_grid(mask, curve)
    q = _sample_grid(qmap, curve) / np.maximum(support, 1e-08)
    valid = (support > 0.999) & np.isfinite(q)
    edges = np.flatnonzero(np.diff(np.r_[False, valid, False].astype(int)))
    choices = []
    for a, b in zip(edges[::2], edges[1::2]):
        if b - a < 3:
            continue
        qq = q[a:b]
        if np.any(np.diff(qq) < -0.001):
            continue
        keep = np.r_[True, np.diff(qq) > 1e-06]
        qq = qq[keep]
        xy = curve[a:b][keep]
        if len(qq) >= 3 and qq[0] <= target <= qq[-1]:
            choices.append((qq, xy))
    if len(choices) != 1:
        raise _PositionRejected('missing_or_ambiguous_contiguous_mapping')
    return choices[0]

def at(q, run):
    return np.array([np.interp(q, run[0], run[1][:, k]) for k in (0, 1)])

def tangent(q, run):
    eps = 0.05
    if q - eps < run[0][0] or q + eps > run[0][-1]:
        raise _PositionRejected('endpoint_tangent_outside_observation')
    return (at(q + eps, run) - at(q - eps, run)) / (2 * eps)

def _connect_pair(context, xy):
    from . import oily
    rec = {}
    try:
        fit, den, noise, middle = (context.fit, context.den, context.noise, context.middle)
        tracks = context.tracks
        assoc = select_association(tracks, fit, den, noise, middle, context.hmed, context.wlen, linked=context.linked)
        if not assoc['accepted']:
            raise _PositionRejected(assoc['reason'])
        q0, q1 = (assoc['rows'][0], assoc['rows'][-1])
        t, Ag, xs, ys = (context.t, context.Ag, context.xs, context.ys)
        mask, qmap, amap = _fields(context)
        obs = []
        for index, target in zip(assoc['track_indices'], (q0, q1)):
            r, tu, st, wd, su, dl = tracks[index]
            curve = oily._curve(r, context.a0 + context.ab * tu, st, dl, su, t, Ag, xs, ys, context.ab, floor=oily.TOL_REL * context.hmed)
            if curve is None:
                raise _PositionRejected('missing_observed_curve')
            obs.append(parameter(curve, mask, qmap, target))
        first, second = obs
        p0, p1 = (at(q0, first), at(q1, second))
        bridge = CubicHermiteSpline([q0, q1], [p0, p1], [tangent(q0, first), tangent(q1, second)])
        lower = max(float(tracks[assoc['track_indices'][0]][0][1]), float(first[0][0]) + 0.05)
        end = min(q1 + 2.0, float(second[0][-1]) - 0.05)
        lower_track = tracks[assoc['track_indices'][1]]
        strong_rows = lower_track[0][(lower_track[2] >= 0.5) & (lower_track[0] > q1)]
        if len(strong_rows):
            end = min(end, float(strong_rows[0]) - 1.0)
        bs = _sample_grid(mask, xy)
        bq = _sample_grid(qmap, xy) / np.maximum(bs, 1e-08)
        bc = (_sample_grid(amap, xy) / np.maximum(bs, 1e-08) - context.a0) / context.ab
        choices = np.flatnonzero((bs > 0.999) & (bq >= lower) & (bq < q0))
        begin = None
        for k in choices:
            if k < 1 or bs[k - 1] <= 0.999:
                continue
            check = photometry(fit, den, noise, bq[k - 1:k + 1], bc[k - 1:k + 1])
            if check['accepted']:
                begin = float(bq[k])
                break
        valid_ids = np.flatnonzero(bs > 0.999)
        rec['boundary_diagnostic'] = {}
        try:
            baseline_run = parameter(xy, mask, qmap, q1)
            position_error = float(np.linalg.norm(at(q1, baseline_run) - p1))
            bv = tangent(q1, baseline_run)
            ov = tangent(q1, second)
            norms = float(np.linalg.norm(bv) * np.linalg.norm(ov))
            angle = float(np.degrees(np.arccos(np.clip(np.dot(bv, ov) / norms, -1.0, 1.0)))) if norms > 1e-12 else np.inf
            local_rows = np.linspace(q1 - 0.1, q1 + 0.1, 9)
            local_errors = [float(np.linalg.norm(at(v, baseline_run) - at(v, second))) for v in local_rows if baseline_run[0][0] <= v <= baseline_run[0][-1] and second[0][0] <= v <= second[0][-1]]
            rec['boundary_diagnostic'].update(
                exit_position_error_px=position_error, exit_tangent_angle_deg=angle,
                exit_neighborhood_max_error_px=max(local_errors, default=np.inf))
        except _PositionRejected as error:
            rec['boundary_diagnostic']['exit_mapping_error'] = str(error)
        boundary_start = False
        zero_exit = False
        bd = rec['boundary_diagnostic']
        if end <= q1:
            zero_exit = bd.get('exit_position_error_px', np.inf) <= 0.01 and bd.get('exit_neighborhood_max_error_px', np.inf) <= 0.01 and (bd.get('exit_tangent_angle_deg', np.inf) <= 0.1)
            if zero_exit:
                end = float(q1)
        if begin is None and len(valid_ids):
            start_idx = int(valid_ids[0])
            p = xy[start_idx]
            o = at(float(first[0][0]), first)
            height, width = mask.shape

            def frame_sides(point):
                x, y = point
                return {side for side, d in enumerate((x, y, width - 1 - x, height - 1 - y)) if -0.001 <= d <= 0.25}
            prefix_outside = bool(np.all((xy[:start_idx, 0] < 0) | (xy[:start_idx, 0] > width - 1) | (xy[:start_idx, 1] < 0) | (xy[:start_idx, 1] > height - 1)))
            if frame_sides(p) & frame_sides(o) and prefix_outside and (abs(float(bq[start_idx]) - float(first[0][0])) <= 0.01) and (float(tracks[assoc['track_indices'][0]][0][1]) == 0.0):
                boundary_start = True
                begin = float(bq[start_idx])
        if begin is None or end < q1 or (end == q1 and (not zero_exit)):
            raise _PositionRejected('no_supported_transition_extent')
        entry_end = begin if boundary_start else min(begin + 1.0, float(q0))
        if not boundary_start and entry_end <= begin:
            raise _PositionRejected('no_entry_blend_extent')
        ids = np.flatnonzero((bs > 0.999) & (bq >= begin) & (bq <= end))
        if boundary_start and len(ids):
            ids = np.arange(0, ids[-1] + 1)
        if len(ids) < 3 or np.any(np.diff(ids) != 1):
            raise _PositionRejected('noncontiguous_baseline_span')
        q = bq[ids].copy()
        if boundary_start:
            q[ids <= start_idx] = max(begin, float(first[0][0]))
        if np.any(np.diff(q) < -0.001):
            raise _PositionRejected('nonmonotone_baseline_span')
        target = xy[ids].copy()
        for i, v in enumerate(q):
            if v < q0:
                f = 1.0 if boundary_start else np.clip((v - begin) / (entry_end - begin), 0.0, 1.0)
                w = f * f * (3 - 2 * f)
                target[i] = xy[ids[i]] + w * (at(v, first) - xy[ids[i]])
            elif v <= q1:
                target[i] = bridge(v)
            else:
                f = np.clip((v - q1) / (end - q1), 0.0, 1.0)
                w = f * f * (3 - 2 * f)
                target[i] = (1 - w) * at(v, second) + w * xy[ids[i]]
        context_ids = np.arange(max(0, ids[0] - 1), min(len(xy), ids[-1] + 2))
        segment = xy[context_ids].copy()
        segment[ids - context_ids[0]] = target
        lengths = np.linalg.norm(np.diff(segment, axis=0), axis=1)
        dense = []
        for a, b, d in zip(segment[:-1], segment[1:], lengths):
            dense.extend(a + np.linspace(0, 1, max(2, int(np.ceil(d / 0.25)) + 1))[:, None] * (b - a))
        dense = np.asarray(dense)
        support = _sample_grid(mask, dense)
        hits = 0 if context.cut is None else int(np.count_nonzero(_sample_grid(context.cut, dense) > 0))
        if np.any(support <= 0.999) or hits:
            raise _PositionRejected('modified_path_outside_piece_or_cut')
        aq = _sample_grid(qmap, dense) / support
        ac = (_sample_grid(amap, dense) / support - context.a0) / context.ab
        if np.any(np.diff(aq) < -0.001):
            raise _PositionRejected('modified_path_nonmonotone')
        evidence_q = aq.copy()
        edge_samples = aq < 0
        if edge_samples.any():
            if not boundary_start or np.any(aq[edge_samples] < -0.5 - 1e-06):
                raise _PositionRejected('outside_first_cell_support')
            if np.any(aq[edge_samples] < float(t.min()) - 0.001):
                raise _PositionRejected('outside_piece_longitudinal_support')
            evidence_q[edge_samples] = 0.0
        photo = photometry(fit, den, noise, evidence_q, ac)
        if not photo['accepted']:
            raise _PositionRejected('full_modified_path_photometry_failed')
        return PositionEdit(ids, target.astype(xy.dtype), 'fixed_sample_supported_candidate', len(assoc['rows']), 'complementary_observations_artistic_connection')
    except _PositionRejected as e:
        return unchanged(xy, str(e))

"""油光 (oily), experimental: sheer glossy nylon, after photos of oily black stockings the user picked.

A faint grain and knit as the fabric; translucency (warm skin showing through where the surface faces the viewer,
denser and darker fabric toward the silhouette, going black on a dark stocking); a broad smooth sheen on the lit side
and a darker shadow side; and
gloss lobes shaped after real glossy tights (the cross-section of the highlight on product photos of black ones, fitted
in half-widths of the limb): a narrow bright core, a short skirt and a broad soft glow across the leg, so a glint is a
smooth band, not a thin line, and the courses and grain show through only a little on its flanks.

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
  zones    on a dark stocking (the region's median luminance below DARK) the facing is what real glossy black tights
           show: the edges go black and skin shows through the middle. The fabric is 1 / facing as thick along the line
           of sight, so what it lets through falls as exp(-KAPPA (1 / facing - 1)) (as a share of the middle's: .76 at
           0.8 half-widths from the centre line on product photos, .54 at 0.9), and warm skin lifts the middle (K_SEE).
           Believed only where the outline is seen (zone = the region's darkness x _frame's trust: 1 where the
           cross-section is seen whole, a half with one side out of sight, 0 with both or none seen whole) and on
           limbs wide enough for an outline to mean something. A pale stocking's art has its own edge shading, and it
           keeps the mild darkening it had.
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
           luminance) and by sitting on the lit side of its region, so near-black or flat art has no peak (see
           default, below). A peak's
           position is known to within what the light's curvature allows against the fit's noise (a flat top: only
           to within its width), and tracks link and smooth their paths within that. A glint whose peak is missing
           where it would be out of sight (behind trim, a hand) goes on unseen and comes out as the same glint; one
           whose peak is missing in plain view has ended. How bright it is comes only from rows where the fit is
           sure of it. Along a track the strength follows the painted light against the track's brightest point, to
           the power SPEC_EXP (gloss falls off faster than the diffuse light it sits on, but a real highlight fades
           smoothly along the leg, not in dashes where the painted light wavers), so a glint runs as far
           as the artist's highlight does: on and on down an evenly lit leg, a short arc on a dome lit in one place.
           Its path is a smooth curve on screen through the rows' peaks. Where the light across is a broad flat top
           with a shallow bump either side of it, the higher bump changes from one row to the next with nothing
           else moving: that is no new glint but the same one moving over (a hand-over, _hand_overs), and it goes
           across between the two along a straight run no faster than a glint moves (_bridge), or, where the light
           along that run is not near the top, is cut in two as before.
  centre   where across the limb a glint goes, where the light leaves it open. A highlight lies where the surface
           normal is halfway between the directions to the light and to the camera: lit from the front or front-quarter
           (the usual set-up for photographing glossy stockings) it runs along the middle of the leg as it is seen, at
           sin(phi / 2) half-widths from the centre line for a light phi from the camera (0.5 at 60 degrees, 0.71 at
           90), the edges dark; side or back light, a turned or oddly shaped leg put it nearer an edge. The painted
           light says where the glint is only to within its own flatness: on a broad top with shallow bumps and ledges
           the highest of them is the brushwork's chance (a hair of luminance), and a glint that follows it wanders
           from one to another. So of the places level with a glint's top (a local maximum of the light within LEVEL of
           it, above or below, with no dip deeper than RIDGE between: one top, not two ridges, so a light that would
           be a glint of its own is no place for this one) it goes to the most central (_centre), along one continuous
           path no faster than a glint moves. A top that stands more than LEVEL above
           every such place stays where the light puts it, and so does anything already near the middle: a highlight
           painted off to one side is followed as ever, nothing is dropped, nothing made up. A glint that moves is the
           same glint, as strong and as bright as it was; one that went on unseen anywhere (out of sight behind trim, a
           hand), or shares a row with one that did, is left as the light puts it. The middle
           is the centre
           line c(V) of what is seen (not a 3D axis) in half-widths, u = (A - c) / h, in the courses' own across
           coordinate A (what the wales follow), so a bent leg's middle bends with it. Where no cross-section of a
           piece is seen whole its middle is only assumed (a hidden side's edge, for facing) and nothing moves.
  floor    a dark stocking is no less glossy where its art paints no highlight, and the glint of a real oily stocking runs the
           whole length of the leg, fading but never gone: where the zones are believed (the region dark, the outline
           seen, the limb wide) and the piece is a limb (MIN_LENGTH widths long) a glint FLOOR_GLINT strong runs its whole
           length, as strong as the zones are believed at each row (_floor_glint). It is one path with the main painted
           glint, not a line beside it: where the art paints that stronger than the floor it is as painted; as it dims
           its place gives way to the place it had where it was clear (the rows the art is sure of, within the limb, at
           least half as strong as at its best), held past its ends and across its gaps (a light that stays put lights a
           straight limb along one u); with no glint painted, down the middle. A limb that something the selection leaves
           out (a ribbon, a hand, a band of hair) cuts across is in pieces, and stays so: each piece's glints are measured
           in the piece (the light a piece is lit by, and the range of its lighting, are its own: joined into one, the
           brighter foot beyond a strap made the calf's glint too dim to count). What the solver filled in across the
           gap (Document.filled_map) only says which pieces are one limb (_pieces: one beyond the other along it, not side
           by side): the limb runs as far as all of them, and a piece with no glint of its own goes on with that of the
           nearest of the others that have one, at its end toward the piece (_nearest; every piece is measured before
           any goes on, so a piece with nothing painted is no donor and no blocker).

tone (lit-side sheen, shadow-side sink) is the region's own range of smoothed brightness with a floor, so a flat
region is neutral rather than all shadow. Every map is whole-image and crops slice them (Scene.oily_maps), so a crop
renders exactly like the whole. v6 was accepted as 试验 (saved then as style 'p_oily'); v7 keeps its look and replaces how the glints are found.

    maps = oily_maps(src, R, alpha, A, V, scale, cut=cut, REG=REG)       # once per image, the whole image
    out = render_oily(src, R, V, A, alpha, g, s, *(m[sl] for m in maps), noise=(gn[sl], gc[sl]))
"""
import cv2
import numpy as np
from itertools import groupby
from types import SimpleNamespace
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
TIE = 0.5 * PROM[0]         # luminance: light this close to a peak's top is level with it (the least a peak stands out)
LEVEL = 0.05                # luminance: a place whose light is this close to a glint's top (above or below) is as good a place
RIDGE = PROM[0]             # luminance: a dip this deep between two places makes them two ridges (the lower would be a
                            # glint of its own), not one top; shallower, the lower is only a ledge on the other's top
CENTRAL = 0.35              # x the half-width: a glint this near the limb's middle is central enough, and stays
NEARER = 0.2                # x the half-width: the least a glint moves toward the middle for the move to be worth it
EPS = 1e-3                  # a glint stays where its light puts it unless another place is better by more than this
STRAIGHT = 0.002            # per cell of sideways step from row to row: of equally central paths, the straighter
APART = 3.0                 # cells: glints this close in a row are one glint (none moves onto another's place)
SPEC_EXP = 3                # gloss against diffuse: (light / light at the glint's brightest point) ^ SPEC_EXP
# The gloss lobe of a glint, after the cross-section of the highlight on a product photo of glossy black tights (median over
# the thigh and the shin of both legs, against the distance from the peak in half-widths of the leg: 1.00 at the peak, .58 at
# 0.1, .37 at 0.2, .28 at 0.3, .18 at 0.5, .08 at 0.8): a narrow bright core, a short skirt and a broad soft glow. Core and
# band are gaussians, the tail an exponential, and the widths (REL, x the limb's half-width, widened where the painted
# highlight is broad) reproduce those values to within 0.02; the weights are what each adds at the peak (sum 0.90 at full
# strength).
CORE_REL, BAND_REL, TAIL_REL = 0.064, 0.54, 0.20
W_CORE, W_BAND, W_TAIL = 0.31, 0.20, 0.39
TEX_CORE, TEX_BAND = 0.15, 0.25      # how much the courses modulate the flanks of the core and of the band (1: fully)
TOL_REL = 0.07              # x the limb's half-width: a glint's path need not follow its painted peaks closer than this
# The zones of a dark stocking, after the same photos (median over the thigh, the shin and the ankle of both legs; the
# leg's brightness against the distance from its centre line in half-widths, as a share of the middle's, on the side
# away from the highlight: 1.0 up to 0.6, .9 at 0.7, .76 at 0.8, .54 at 0.9): a flat middle and edges that go black. (The
# side the highlight is on keeps its edge bright there, which this symmetric model does not follow.) The
# fabric is 1 / facing as thick along the line of sight (facing = sqrt(1 - u^2) across), so what it lets through falls as
# exp(-KAPPA * (1 / facing - 1)); skin shows through the middle, warm, a share K_SEE of the headroom the art leaves. Only
# where the art is dark (a pale stocking's art has its own edge shading), where the outline is seen (the band's trust) and
# on limbs wide enough for the outline to mean anything.
DARK = (0.30, 0.75)         # luminance of a region's stocking (median): at the first the zones are in full, at the second gone
KAPPA = 0.35
K_SEE = 0.08
HALF_ZONE = (4.0, 8.0)      # px: the zones fade in on limbs from this half-width (a sliver's outline is a guess) to this
# A dark stocking is no less glossy where its art paints no highlight, and the glint of a real oily stocking runs the whole
# length of the leg, fading but never gone (on a product photo of black tights about 100 grey levels at the thigh, 30-50 on
# the shin, 10 at the ankle): where the zones are believed a glint of this strength runs the whole length of a limb,
# under whatever the art paints (_floor_glint).
FLOOR_GLINT = 0.4           # its strength (a painted glint reaches up to 1), times how far the zones are believed there
FAINT = 0.15                # a painted glint fainter than this is no glint to follow (the floor goes down the middle)
MIN_LENGTH = 1.5            # x the limb's width: a piece shorter than this (a foot, a dome) is no limb to run a glint down
PIXEL = 1.0                 # px: the least reach _curve takes a row's glint from (a thin limb's cells are narrower than that)
MIN_PIECE = 64              # px: smaller pieces get facing only
# The glint a dark limb never goes without (see _floor_glint): its place across the limb comes from where the painted glint
# was clear, within the limb (U_MAX half-widths from the centre line, a little past the outline for an estimate that is
# not exact) and not a guess; as the painted glint dims below the floor (FOLLOW: the shares of the floor's strength where its
# place counts for nothing, and for all) the floor goes over to that place
U_MAX = 1.1
FOLLOW = (0.25, 1.0)
FREE_TAU = 3.0              # rows: what the smoothing moved a painted glint's end by dies out over this on the floor's rows past it
# A limb something the selection leaves out cuts across (a ribbon, a band of hair) is one limb (_pieces): the pieces that
# the solver's filling-in joins are one when one is beyond the other along the limb (their V ranges overlap by less than
# STACK[0], their A ranges by at least STACK[1], as shares of the shorter: a band across the limb at up to about 50 degrees),
# side by side (two limbs of a region) they are not
STACK = (0.75, 0.5)
# What the ribbon or hair across a limb hides is no outline (_frame with the connectors out of sight); that frame is taken when
# some cross-section is whole in it (without one, no outline is believed anywhere, in the plain frame as well: a leg cut by the
# image's edge, and the connector's edges would only turn what is seen of its silhouette into an unseen one) and it believes the
# outline, anywhere, at least this share of what the plain frame does at best: a sliver of three bands of V of which only the
# middle one is whole has its trust smoothed away to nothing (and no floor: nothing believes its zones): measured as before
CUT_TRUST = 0.25


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


def _band(scale):
    """px of V in each band of the limb's frame (_frame)."""
    return max(2.0, 2.0 * scale)


def _frame(Vg, Ag, hidden, scale, hmed_min=0.0):
    """The limb's cross-section per band of V. Vg, Ag: the piece's painted pixels; hidden: those on an edge where
    the limb runs on out of sight (the image frame, another painted region in front of or beside it, a wall, the ribbon or
    hair across a limb in pieces), so its extent there is unknown, not an outline.

    The painted region is the limb's shape: its outline is the silhouette (hair painted over is part of the limb;
    hair painted round is outline the user drew), so a knee or a waist keeps its narrowing. A side out of sight is
    measured from the other side, with the limb's width from complete cross-sections; with none anywhere, the edge
    is taken as the limb's middle (one side hidden) or no silhouette is seen at all (both sides hidden). hmed_min: the
    least the typical half-width is taken to be: the limb is at least as wide as it is seen, so where the complete
    cross-sections are few (a toe, the one stretch the connectors leave alone) they must not make it narrower than the
    caller has it seen otherwise.
    Returns (band of each pixel, c, h, hf, typical half-width, tilt, whole, trust), per band: centre, half-width (the
    limb's size), half-width for facing (inf: no silhouette seen), and the surface's tilt along the limb; whether any
    cross-section was seen whole (if none was, the centre is only assumed: a hidden side's edge, taken as the middle);
    and per band how far its outline can be trusted, 0..1: 1 where the cross-section is seen whole, a half where one side
    is out of sight and measured from the other, 0 where both are (or none was seen whole anywhere)."""
    bv = _band(scale)
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
    hmed = max(float(np.median(half[good] if good.any() else half)), 2.0, hmed_min)
    one = lo_cut ^ hi_cut
    both = lo_cut & hi_cut
    if good.any():
        hmed = max(float(np.median(half[good])), 2.0, hmed_min)
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
    trust = np.where(good, 1.0, np.where(one, 0.5, 0.0)) if good.any() else np.zeros(n)
    # a cut across a piece's end (a wall, the frame) hides a whole cross-section there, not the outline beside it: the
    # end bands with both sides hidden take their interior neighbour's trust (a side hidden alone is a real occlusion)
    e = min(3, n // 4)
    if e:
        for ends, nb in ((slice(0, e), e), (slice(n - e, n), n - e - 1)):
            trust[ends] = np.where(both[ends], trust[nb], trust[ends])
    trust = ndi.gaussian_filter1d(trust, win / 2, mode='nearest')
    return k, c, h, hf, hmed, tilt, bool(good.any()), trust


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


def _tracks(fit, absolute, den, noise, reach, middle=None):
    """The light's peaks across the limb, row by row, linked along it: [(rows, cell, strength, width in cells,
    sureness, position known to within, in cells)], each track padded with a row past either end so it fades in and
    out. Sureness is the fit's support at the peak, 0 in rows the glint went on unseen. reach: rows a glint may stay
    out of sight (behind trim, a hand) and still be the same glint where it comes out. middle: None, or each cell's
    place across the limb in half-widths from its centre line; where the painted light leaves a glint's place open
    it goes to the most central of the places it could as well be (_centre), after the tracks are made as without it.

    Shade only darkens: a strip of light between two shadows (hair, fingers, a hand's shadow, a dark print) is no
    peak of the light falling on the limb. So peaks are those of each row's envelope (_envelope, dips up to SHADE of
    the half-width filled), and a glint sits only where the painted light itself reaches that envelope's top: a
    measured point, never one inferred in a filled dip (two close lights of one height keep a glint each). A peak
    counts by its prominence in the envelope (luminance), by standing clear of the fit's own noise, and by where it
    sits in the range of the region's brightness. Along a track the strength follows the painted light against the
    track's brightest point. A glint whose top moves from one bump of a flat-topped light to another goes with it
    (_hand_overs, _bridge), a path that is no faster than a glint moves, not an end here and a beginning there."""
    sup = den > SURE
    lo, hi = (float(np.percentile(absolute[sup], v)) for v in (2, 98)) if sup.any() else (0.0, 1.0)
    shade = max(1, int(round(SHADE * CELLS / 2)))

    def peak(q, r0, f, env, j, size, prom, width, like=None):
        """The glint a local maximum j of the light f (the stretch of row q in sight that starts at cell r0, env its
        envelope) makes, given the prominence and width of the envelope's peak it belongs to, or None where it is too
        faint. like: a glint this place is as good as (_centre): the same glint, so it keeps that one's strength,
        light and sureness (which of its rows its brightness is read from does not move with it), and is none where
        the region's light puts the place on its dark side. Where the top is, and to within what, is the place's own."""
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
        if like is None:
            st = (knit.sstep(PROM[0], PROM[1], prom) * knit.sstep(LIT[0], LIT[1], lit)
                  * knit.sstep(*CLEAR, prom / max(local, 1e-6)))
            if st <= 0.02:
                return None
            kept = sure
        elif lit <= LIT[0]:
            return None
        else:
            st, lit, kept = like[1], like[5], like[3]
        # where the top is, to within (cells): a light curving down by k per cell^2 has its top moved by
        # sqrt(2 noise / k) under the fit's noise, and no further than its own half-width; a flat top is
        # anywhere along it. The light's curvature from the envelope (shade beside it is no curvature
        # of the light), with the stencil cut short at the run's ends
        jl, jr = max(j - 2, 0), min(j + 2, len(f) - 1)
        a, b = j - jl, jr - j
        bend = max(-2 * (b * env[jl] - (a + b) * env[j] + a * env[jr]) / (a * b * (a + b)), 1e-9)
        where = max(min(np.sqrt(2 * local / bend), width / 2), (size - 1) / 2)
        # the cells round the top whose light is within TIE of it: where it could as well be
        t0 = t1 = j
        while t0 > 0 and f[t0 - 1] >= f[j] - TIE:
            t0 -= 1
        while t1 < len(f) - 1 and f[t1 + 1] >= f[j] - TIE:
            t1 += 1
        return (cell + 0.5 + off, st, width, kept, where, lit, r0 + t0, r0 + t1 + 1, float(f[j]), prom, cell)

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
                    pk = peak(q, r0, f, env, int(j), int(size), float(pe['prominences'][i]), float(width[i]))
                    if pk is not None:
                        found.append(pk)
        peaks.append(found)
    # linked row to row: the same glint if it moved no more than LINK of the half-width a row, give or take where
    # the two peaks are known to within. A glint with no peak where it could be goes on unseen, up to reach rows,
    # only while where it would be is out of sight (the fit unsure there); where the fit plainly sees no peak, the
    # glint has ended. Before that, a hand-over (_hand_overs) may take it to a peak nobody else has. The glints that
    # go on keep the order of the row before (strongest first), whichever way each one goes on: equally strong
    # glints compete for a peak in that order
    done, live = [], []
    for q, row in enumerate(peaks):
        order = sorted(live, key=lambda t: -t[2][-1])                # the strongest glints claim their peaks first
        taken, lost, on = set(), [], [False] * len(order)
        for n, t in enumerate(order):
            miss = q - t[0][-1] - 1
            u0, d0 = t[1][-1], t[5][-1]
            near = [(abs(pk[0] - u0), j) for j, pk in enumerate(row) if j not in taken
                    and abs(pk[0] - u0) <= LINK * CELLS * (1 + miss) + np.hypot(pk[4], d0)]
            best = min(near, default=None)
            if best is None:
                lost.append(n)
                continue
            taken.add(best[1])
            for lst, v in zip(t, (q,) + row[best[1]] + (False,)):
                lst.append(v)
            on[n] = True
        stay = []
        for n in lost:
            t = order[n]
            miss = q - t[0][-1] - 1
            u0, d0 = t[1][-1], t[5][-1]
            c0, c1 = (int(np.clip(np.floor(u0 + k * (d0 + 1)), 0, den.shape[1] - 1)) for k in (-1, 1))
            stay.append(miss < reach and bool((den[q, c0:c1 + 1] < SURE).any()))      # out of sight here
        over = _hand_overs([order[n] for n in lost], stay, row, taken, peaks[q - 1] if q else [], q)
        for i, n in enumerate(lost):
            t = order[n]
            if i in over:
                taken.add(over[i])
                for lst, v in zip(t, (q,) + row[over[i]] + (True,)):
                    lst.append(v)
                on[n] = True
            elif stay[i]:
                on[n] = True                                          # out of sight here
            else:
                done.append(t)
        live = [t for t, go in zip(order, on) if go]
        live += [([q], *([v] for v in pk), [False]) for j, pk in enumerate(row) if j not in taken]
    out = []
    last = fit.shape[0] - 1
    tracks = done + live
    if middle is not None:
        tracks = _centre(tracks, fit, den, middle, peak, shade)
    for rows, u, st, wd, su, dl, li in (p for t in tracks for p in _bridge(t, fit, den)):
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


def _centre(tracks, fit, den, middle, peak, shade):
    """The tracks with each glint at the most central place its light allows. Real glints run mostly along the middle of
    the leg as it is seen; the painted light says where within a flat top, a shoulder or a shallow bump the glint goes
    only to within LEVEL. So of the places level with a peak's top (a local maximum of the light within LEVEL of it,
    above or below, and no dip deeper than RIDGE between: one top, not two ridges, so a light that would stand as a
    glint of its own is no place for this one) the most central one is as good a place as any, and a top more than
    LEVEL above any such place stays where the light puts it.

    Each glint is moved as a whole, along one continuous path: no faster than a glint moves (as when linking), so a
    place level with the top for a row or two makes no glint of its own. A glint that went on unseen anywhere (out of
    sight behind trim, a hand) is not moved at all, and neither is one that shares a row with such a glint: the rows
    it was out of sight in are not known to be out of sight at a new place (a glint drawn through plain view where the
    light has no peak would be none), its curve through them is smoothed with the rows either side (so moving those
    would bend it into view), and where that curve is drawn in them is not known well enough to move another glint
    near it. Places are costed by how far from the middle they lie (none for what lies
    within CENTRAL of it); a glint stays put where nothing is better (EPS), the straighter path wins of equals
    (STRAIGHT), and no glint moves onto another's place (APART). Off the middle a place is a candidate only if it is
    NEARER it by more than NEARER half-widths; a glint central enough all along is left alone, and where one is only
    in some rows, the others can use any other place in the middle as well (the middle seen wobbles as a hand or a
    dress hides now one side of the limb, now the other, and a path must stay open through those rows).

    A glint that moves is the same glint: it keeps its strength, light and sureness, so moving it neither brightens
    nor dims it. Where putting the pieces of a glint on one line heals a cut that a hand-over could not bridge (_bridge)
    it is one glint from then on, with no fade at the old cut and one brightest point to measure against, as any glint
    that was never cut. Strongest glints first, so they claim their places before the weaker ones."""
    cells = np.arange(fit.shape[1])
    runs = {}

    def across(q, x):
        return abs(float(np.interp(x - 0.5, cells, middle[q])))

    def stretch(q, cell):
        """(start, end) of the stretch of row q in sight that holds cell, or None."""
        if q not in runs:
            ok = den[q] > 0.05
            edges = np.flatnonzero(np.diff(np.concatenate([[0], ok.astype(np.int8), [0]])))
            runs[q] = [(a, b) for a, b in zip(edges[::2], edges[1::2]) if b - a >= 5]
        return next((r for r in runs[q] if r[0] <= cell < r[1]), None)

    occupied = {}
    carried = set()                                         # rows in which some glint went on unseen
    for t in tracks:
        for q, x in zip(t[0], t[1]):
            occupied.setdefault(q, []).append(x)
        for k in range(1, len(t[0])):
            carried.update(range(t[0][k - 1] + 1, t[0][k]))
    out = list(tracks)
    for ti in sorted(range(len(tracks)), key=lambda i: -float(np.sum(tracks[i][2]))):
        t = tracks[ti]
        rows, handed, n = t[0], t[12], len(t[0])
        if any(rows[k] - rows[k - 1] > 1 for k in range(1, n)) or any(q in carried for q in rows):
            continue                                        # left as the light puts it (see above)
        stays = [tuple(t[i][k] for i in range(1, 12)) for k in range(n)]
        away = [across(q, stay[0]) for q, stay in zip(rows, stays)]
        if max(away) <= CENTRAL:
            continue                                        # central all along: nothing to move
        opts = []
        for k in range(n):
            q, stay = rows[k], stays[k]
            options = [(stay, True)]
            run = stretch(q, stay[10])
            if run is not None:
                r0, r1 = run
                f = fit[q, r0:r1]
                env = _envelope(f, shade)
                jf, pf = find_peaks(f, plateau_size=1)
                j0 = stay[10] - r0
                others = [x for x in occupied[q] if x != stay[0]]
                # off the middle, a place must be NEARER it; in the middle already, any other place in it will do, so a
                # path stays open across the rows where the glint is central enough (a middle that wobbles by a few
                # tenths of a half-width) to the rows where it moves
                limit = away[k] - NEARER if away[k] > CENTRAL else CENTRAL
                for jc, size in zip(jf, pf['plateau_sizes']):
                    jc = int(jc)
                    if jc == j0 or abs(float(middle[q, r0 + jc])) > limit or abs(stay[8] - f[jc]) > LEVEL:
                        continue
                    a, b = min(jc, j0), max(jc, j0)
                    if min(f[j0], f[jc]) - f[a:b + 1].min() > RIDGE:
                        continue
                    cand = peak(q, r0, f, env, jc, int(size), stay[9], stay[2], like=stay)
                    if cand is not None and all(abs(cand[0] - x) > APART for x in others):
                        options.append((cand, False))
            opts.append(options)
        if all(len(o) == 1 for o in opts):
            continue
        best = []
        for k in range(n):
            cur = []
            for o, is_stay in opts[k]:
                own = max(across(rows[k], o[0]), CENTRAL) + (0.0 if is_stay else EPS)
                if k == 0:
                    cur.append((own, -1))
                    continue
                prev = (np.inf, -1)
                for pi, (p, p_stay) in enumerate(opts[k - 1]):
                    # a path a glint could take: no faster than it moves, whatever the places are known to within
                    # (the stays are the track's own steps, linking had that slack for them)
                    if (is_stay and p_stay) or abs(o[0] - p[0]) <= LINK * CELLS:
                        prev = min(prev, (best[k - 1][pi][0] + STRAIGHT * abs(o[0] - p[0]), pi))
                cur.append((own + prev[0], prev[1]))
            best.append(cur)
        pick = [min(range(len(best[-1])), key=lambda i: best[-1][i][0])]
        for k in range(n - 1, 0, -1):
            pick.append(best[k][pick[-1]][1])
        pick.reverse()
        if all(opts[k][pick[k]][1] for k in range(n)):
            continue
        for k in range(n):
            old, new = opts[k][0][0][0], opts[k][pick[k]][0][0]
            occupied[rows[k]].remove(old)
            occupied[rows[k]].append(new)
        out[ti] = (list(rows),) + tuple([opts[k][pick[k]][0][i] for k in range(n)] for i in range(11)) + (list(handed),)
    return out


def _hand_overs(lost, stay, row, taken, before, q):
    """{index in lost: index in row}: the glints left without a peak in row q that go on with a peak nobody has,
    because the light's top has passed from one bump of a flat top to another. Such a glint is in plain sight (one
    that may go on unseen, stay, does), had its last peak in the row before (before: that row's peaks), and each
    peak's place is within TIE of the other's top: the light at either is level with the other, so which of the two
    bumps is the higher is nothing a glint depends on. No other peak lies in either stretch of level light (one top,
    one glint), and where a glint could go to more than one peak, or a peak be taken by more than one glint, none
    does."""
    pairs = []
    for i, t in enumerate(lost):
        if stay[i] or t[0][-1] != q - 1 or t[4][-1] < SURE:
            continue
        u0, lo0, hi0 = t[1][-1], t[7][-1], t[8][-1]
        if sum(lo0 <= o[0] <= hi0 for o in before) != 1:
            continue
        pairs += [(i, j) for j, pk in enumerate(row)
                  if j not in taken and pk[3] >= SURE and pk[6] <= u0 <= pk[7] and lo0 <= pk[0] <= hi0
                  and sum(pk[6] <= o[0] <= pk[7] for o in row) == 1]
    return {i: j for i, j in pairs if sum(a == i for a, _ in pairs) == 1 and sum(b == j for _, b in pairs) == 1}


def _bridge(t, fit, den):
    """A glint's track as pieces (rows, cell, strength, width, sureness, position known to within, light): one, unless
    a hand-over in it (_hand_overs) has no way across. Across a hand-over the glint's path is a straight run from a
    peak before it to one after, in place of the peaks between (the run that moves them least, shortest first).
    The run goes no faster than a glint moves (LINK of the half-width a row) over rows that are all peaks (none a row
    the glint went on unseen) and, in each, in sight and over light within TIE of that row's own top: the measured
    light, so the glint never crosses a dark flank between two crisp lights. Only runs reaching about as many rows
    either side of the hand-over as the jump takes at that pace are tried. Where there is no such run the track is
    cut at the hand-over: two glints, as before."""
    rows, u, st, wd, su, dl, li, _, _, top, _, _, handed = t
    q, u, top = np.asarray(rows, np.int64), np.array(u, np.float64), np.asarray(top, np.float64)
    pace, cells = LINK * CELLS, np.arange(fit.shape[1])
    cuts, end = [], 0                                       # end: the peak up to which the path is settled
    for k in np.flatnonzero(handed):
        if k <= end:
            continue
        room = int(np.ceil(abs(u[k] - u[k - 1]) / pace)) + 1
        best = None
        for a in range(max(end, k - 1 - room), k):
            for b in range(k, min(len(q), k + room + 1)):
                span = q[b] - q[a]
                if span != b - a or abs(u[b] - u[a]) > pace * span:
                    continue
                run = u[a] + (u[b] - u[a]) * (q[a + 1:b] - q[a]) / span
                if all(np.interp(x - 0.5, cells, den[r]) >= SURE and p - np.interp(x - 0.5, cells, fit[r]) <= TIE
                       for r, x, p in zip(q[a + 1:b], run, top[a + 1:b])):
                    cost = (float(np.abs(run - u[a + 1:b]).sum()), b - a)
                    if best is None or cost < best[0]:
                        best = (cost, a, b, run)
        if best is None:
            cuts.append(k)
            end = k
        else:
            u[best[1] + 1:best[2]] = best[3]
            end = best[2]
    edges = [0] + cuts + [len(q)]
    return [tuple(np.asarray(x)[s:e] for x in (rows, u, st, wd, su, dl, li)) for s, e in zip(edges[:-1], edges[1:])]


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


def _curve(rows, ga, st, dl, su, t, Ag, xs, ys, ab, step=0.25, floor=0.0, free=None):
    """A glint track as a smooth curve on screen, densely sampled (N, 2) xy, or None. Each row's glint is where the
    stocking sits at the glint's A in that row. One light on a smooth body traces a smooth curve, so the path is
    smoothed as far as the painted highlight allows: every clear row stays within what its peak is known to within
    (dl, cells), never finer than the fit resolves, and never tighter than floor (px: the wobble of a painted
    highlight is no wobble of a real one). A broad soft highlight (whose flat top wanders) gets a smooth
    path; a crisp one is followed exactly. Rows where the glint went on unseen (sureness 0) are passed through, not
    aimed at, and rows less sure of it count for less. free: which of the rows are the floor's own, past the ends of a
    painted glint (_floor_glint), or None: they are no part of the smoothing, which is of the painted rows alone as it
    would be without them; they follow the path as it is (the limb's centre line and its width, smooth already), with
    what the smoothing moved the nearest painted row by dying out over FREE_TAU rows, so that the line has no jog."""
    pts, wts, tol, qs, fr = [], [], [], [], []
    # the cells are narrower than a pixel on a thin limb, so a row's pixels at the glint's A (and a path to take the
    # mean of) are those within a pixel's reach at least
    reach = max(ab, PIXEL)
    own = np.zeros(len(rows), bool) if free is None else free
    for q, a, w, d, u, f in zip(rows[1:-1], ga[1:-1], st[1:-1], dl[1:-1], su[1:-1], own[1:-1]):
        sel = (t >= q - 0.5) & (t < q + 0.5) & (np.abs(Ag - a) < reach)
        if u > 0 and sel.sum() >= 2:
            pts.append((xs[sel].mean(), ys[sel].mean()))
            wts.append((w + 1e-3) * u)
            tol.append(max(d * ab, 0.25 * ab, 1.0, floor))
            qs.append(q)
            fr.append(f)
    if not pts:
        return None
    pts, wts, tol, qs, fr = np.asarray(pts), np.asarray(wts), np.asarray(tol), np.asarray(qs, np.float64), np.asarray(fr)
    if len(pts) == 1:
        return pts
    if fr.any() and not fr.all():
        kept = ~fr
        sm = pts.copy()
        sm[kept] = _smooth_within(qs[kept], pts[kept], wts[kept], tol[kept], wts[kept] > 0.25 * wts[kept].max())
        near = np.abs(qs[:, None] - qs[kept][None, :]).argmin(1)
        moved = (sm[kept] - pts[kept])[near]
        gone = np.abs(qs - qs[kept][near])
        sm[fr] = pts[fr] + moved[fr] * np.exp(-0.5 * (gone[fr] / FREE_TAU) ** 2)[:, None]
        pts = sm
    else:
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


def _anchors(tracks, ext, c, h, a0, ab):
    """The main painted glint (the one with the most light that is sure) and where it can be held: (main, place, clear,
    top), main None where nothing is painted. place: u of each of its rows, in half-widths from the limb's centre line c(V);
    clear: the rows to take a place from, the ones the art is sure of (a carried row is only interpolated), at least half
    as strong as at its best (a fading tail wanders, by a third of a half-width on real pictures), within the limb (U_MAX:
    a place past the outline is a bad estimate), and no pad row; top: its strongest row."""
    main = max(tracks, key=lambda tr: float(np.sum(tr[2] * tr[4])), default=None)
    if main is None:
        return None, None, None, 0.0
    rows, tu, st, wd, su, dl = main
    band = ext[np.clip(np.round(rows).astype(np.int64) + 1, 0, len(ext) - 1)]
    place = (a0 + ab * tu - c[band]) / h[band]
    top = float(np.max(st))
    clear = (st >= max(0.5 * FAINT, 0.5 * top)) & (su >= SURE) & (np.abs(place) <= U_MAX)
    clear[[0, -1]] = False
    return main, place, clear, top


def _ends(tracks, kq, c, h, a0, ab):
    """Where a limb's main glint is at its two ends, for the pieces of the limb that have none (_floor_glint's held):
    (u at its first clear row, u at its last, follow), or None. follow: how far the glint is to be gone by, 0..1 (by how
    clear it is: FAINT, smoothly, as there)."""
    ext = np.concatenate([[kq[0]], kq, [kq[-1]]])
    main, place, clear, top = _anchors(tracks, ext, c, h, a0, ab)
    if main is None or not clear.any():
        return None
    return float(place[clear][0]), float(place[clear][-1]), float(knit.sstep(0.5 * FAINT, FAINT, top))


def _floor_glint(tracks, nrow, length, hmed, kq, c, h, a0, ab, believed, held=0.0, t=None):
    """tracks with the glint a dark limb never goes without put in: a list of tracks like _tracks', the painted ones but
    for the main glint, which is carried on the whole length of the piece (a row past each end, as the others have: a
    wall or the frame is no end of a glint) and lifted to FLOOR_GLINT strong times how far the zones are believed at each
    row (believed: per band of V) wherever the art paints it dimmer, or none: down a calf under a thigh's highlight,
    through the dim stretch of a thigh, across a gap at the knee. With no glint painted, one down the limb at the place
    held (the middle of the limb as seen unless the limb's other pieces say otherwise: _nearest; u at the top of the piece
    and at its bottom, or one u for both, run from the one to the other along the piece's extent: the rows t of its pixels,
    first to last, or the fit's rows whole when None). It is one path, not a painted glint and another beside it: a painted
    highlight stronger than the floor is just as painted (its place, its strength); as it dims below the floor it goes over
    to the glint's place where it was clear, and past its ends and across its gaps it holds that place (u, in half-widths
    from the centre line c(V): one light lights a straight limb along one u; _anchors says which rows it is taken from). The
    glint is by how clear it is (FAINT, smoothly: a highlight painted a hair stronger does not move the line all at once) the
    main one's place or the held one. tracks: the painted glints; length: px of the limb along its course (a piece with the
    pieces of its limb across a ribbon or a hand: _pieces). A stretch at least MIN_LENGTH widths long takes it: no foot,
    no dome. A piece of one fit row whose pixels are within two rows of each other (a sliver) has its glint, painted or
    not, in thirds of its extent (the track an eighth element, (where its rows start, how many go to a row), for the draw):
    one position to a row would make a point of it, a blob in its middle and none at its ends."""
    if FLOOR_GLINT <= 0 or length < MIN_LENGTH * 2 * hmed:
        return tracks
    ext = np.concatenate([[kq[0]], kq, [kq[-1]]])
    floor = FLOOR_GLINT * believed[ext]
    if floor.max() < 0.05:
        return tracks
    held_top, held_bottom = np.broadcast_to(np.asarray(held, np.float64), (2,))
    # the held place runs from the one at the piece's top to the one at its bottom along its actual extent, so that the
    # line is at each of them at the very first and last pixel; a row's place is taken where its pixels are (the middle of
    # the part of the row the piece covers: the fit's last row is often a short one, and a row's glint is placed at the
    # mean of its pixels)
    t_lo, t_hi = (-0.5, nrow - 0.5) if t is None else (float(np.min(t)), float(np.max(t)))
    span = max(t_hi - t_lo, 1e-3)
    main, place, clear, top = _anchors(tracks, ext, c, h, a0, ab)
    remap = None
    if nrow < 2 and span <= 2.0:
        # thirds of the extent for rows, each at the mean of its pixels, where _curve places its glint: the pixels in each third
        # are those the draw puts in it, by the very expression it maps rows with and its half-open rows (a pixel at the edge
        # of a third falls on the one side in both: about one sliver in seven has its last pixel at such an edge, where
        # another way of writing the mapping disagrees in the last digit)
        remap = (t_lo, 3.0 / span)
        grid = np.arange(-1, 4, dtype=np.float64)
        mid = np.concatenate([[t_lo], t_lo + (np.arange(3) + 0.5) * span / 3.0, [t_hi]])
        if t is not None:
            pix = np.asarray(t, np.float64)
            tt = (pix - remap[0]) * remap[1] - 0.5
            for k in range(3):
                in_third = (tt >= k - 0.5) & (tt < k + 0.5)
                if in_third.any():
                    mid[1 + k] = float(pix[in_third].mean())
        tg = mid
        cg, hg, floor = (np.full(len(grid), a[1]) for a in (c[ext], h[ext], floor))
    else:
        grid = np.arange(-1, nrow + 1, dtype=np.float64)
        cover_lo, cover_hi = np.maximum(grid - 0.5, t_lo), np.minimum(grid + 0.5, t_hi)
        mid = np.where(cover_hi > cover_lo, 0.5 * (cover_lo + cover_hi), np.clip(grid, t_lo, t_hi))
        tg, cg, hg = grid, c[ext], h[ext]
    n = len(grid)
    keep = held_top + (held_bottom - held_top) * np.clip((mid - t_lo) / span, 0.0, 1.0)
    if main is None:
        return [(grid, (cg + keep * hg - a0) / ab, floor, np.ones(n), np.ones(n), np.ones(n))
                + ((None, remap) if remap else ())]
    rows, tu, st, wd, su, dl = main
    path = keep
    if clear.any():
        follow = float(knit.sstep(0.5 * FAINT, FAINT, top))
        path = follow * np.interp(tg, rows[clear], place[clear]) + (1 - follow) * keep
    inside = (tg >= rows[0]) & (tg <= rows[-1])
    painted = np.where(inside, np.interp(tg, rows, st), 0.0)
    # where the art paints the glint stronger than the floor it is as painted; as it dims, its place gives way to the
    # held one (it is no longer the glint the floor can hide under), and outside the glint's rows there is only that
    near = np.where(inside, np.where(floor > 1e-9, knit.sstep(FOLLOW[0], FOLLOW[1], painted / np.maximum(floor, 1e-9)),
                                     1.0), 0.0)
    u = near * np.interp(tg, rows, place) + (1 - near) * path
    tu_new = (cg + u * hg - a0) / ab
    tu_new = np.where(inside & (near >= 1.0), np.interp(tg, rows, tu), tu_new)
    # _curve weighs a row by (strength + 1e-3) * sureness: the rows the floor lifts (the art paints them dimmer) keep the weight
    # they had, and the rows past the glint's ends (and its pad rows) are the floor's own, free of the smoothing, so that
    # the painted glint's path is smoothed as it was without the floor and the floor follows it
    lifted = np.maximum(painted, floor)
    free = ~((tg > rows[0]) & (tg < rows[-1]))
    carried = [np.where(free, 1.0, np.interp(tg, rows, su) * (painted + 1e-3) / (lifted + 1e-3)),
               np.interp(tg, rows, dl, left=1.0, right=1.0)]
    return [tr for tr in tracks if tr is not main] + [
        (grid, tu_new, lifted, np.interp(tg, rows, wd), carried[0], carried[1], free) + ((remap,) if remap else ())]


def _nearest(job, donors, ends):
    """Where the painted glints of the other pieces of job's limb that have one (donors; ends: _ends of each, by label) put
    the glint of a piece of it with none of its own: (u at its top, u at its bottom), the places of the glints before it
    along the limb and after it, each at its end toward the piece, so that the line is continuous at both seams. Of the
    glints on one side the nearest by the stretch of V between (a piece beyond one that is blank is no worse for it), then
    the bigger, counts as far as it is clear (follow); what it is not goes to the next, and what none of them is to the
    middle (0), as for a piece's own faint glint: a glint that barely shows only hints at the place, and a hair's
    difference in its strength does not move the line all at once. Donors as near (to a pixel: PIXEL, not to the solver's
    last digits) and as big as each other are one donor at the mean of their places (by how clear each is): no side is
    preferred. Both ends alike where only one side has a glint."""
    before, after = [], []
    for d in donors:
        u0, u1, follow = ends[d.j]
        if follow > 0:
            lies_before = d.vmean < job.vmean
            gap = max((job.vlo - d.vhi) if lies_before else (d.vlo - job.vhi), 0.0)
            (before if lies_before else after).append((round(gap / PIXEL), -d.size, u1 if lies_before else u0, follow))

    def held(ds):
        u = None
        for _, tied in groupby(sorted(ds, key=lambda d: d[:2], reverse=True), key=lambda d: d[:2]):   # the farthest first
            tied = list(tied)
            follow = max(d[3] for d in tied)
            place = sum(d[3] * d[2] for d in tied) / sum(d[3] for d in tied)
            u = follow * place + (1 - follow) * (0.0 if u is None else u)                      # the nearest has the last word
        return u
    top, bottom = held(before), held(after)
    top, bottom = (bottom if top is None else top), (top if bottom is None else bottom)
    return (0.0, 0.0) if top is None else (top, bottom)


def _pieces(body, link, V, A):
    """(label image of the pieces of limb, 0 elsewhere: the connected pieces of body, a region's painted stocking less
    walls; group: per label, the number of the limb its piece is one of with others, or 0; span: per limb, the (lowest,
    highest) V of its pieces). A limb that something the selection leaves out cuts across (a ribbon, a hand, a band of
    hair: the stocking runs on underneath) is in pieces as painted, each its own: the glints they show are theirs (the
    light each is lit by is measured within the piece, and the foot beyond a ribbon is lit otherwise than the calf), but
    they are one limb for how far it runs, and for where its glint goes on. link: the pixels the solver filled in beside
    the region (Document.filled_map), or None. Pieces it joins are of one limb when one lies beyond the other along the
    limb (their V ranges overlap by less than STACK[0], their A ranges by at least STACK[1], as shares of the shorter) and
    both are more than a speck (MIN_PIECE); side by side, two limbs of one region or strands of hair down a limb, nothing
    says them from each other, and they are not."""
    n, lab = cv2.connectedComponents(body.astype(np.uint8), connectivity=8)
    group, span = np.zeros(n, np.int64), [None]
    if link is None or n < 3:
        return lab, group, span
    _, joined = cv2.connectedComponents((body | link).astype(np.uint8), connectivity=8)
    idx = np.arange(1, n)
    comp = np.asarray(ndi.maximum(joined, lab, idx), np.int64)
    area = np.bincount(lab.ravel(), minlength=n)[1:]
    lo_v, hi_v = (np.asarray(f(V, lab, idx), np.float64) for f in (ndi.minimum, ndi.maximum))
    lo_a, hi_a = (np.asarray(f(A, lab, idx), np.float64) for f in (ndi.minimum, ndi.maximum))

    def overlap(p, q, lo, hi):
        return max(0.0, min(hi[p], hi[q]) - max(lo[p], lo[q])) / max(min(hi[p] - lo[p], hi[q] - lo[q]), 1.0)
    for g in np.unique(comp):
        members = np.flatnonzero(comp == g)
        big = members[np.argmax(area[members])]
        of = [big] + [q for q in members if q != big and area[q] >= MIN_PIECE and area[big] >= MIN_PIECE
                      and overlap(q, big, lo_v, hi_v) < STACK[0] and overlap(q, big, lo_a, hi_a) >= STACK[1]]
        if len(of) > 1:
            group[np.add(of, 1)] = len(span)
            span.append((float(lo_v[of].min()), float(hi_v[of].max())))
    return lab, group, span


def _joins(lab, group, gap):
    """The part of gap, what the solver filled in beside a region, that lies between the pieces of one limb (group and lab:
    _pieces): what cuts the limb across, a ribbon, a hand, a band of hair, as a mask. A notch in the outline of one piece,
    which the solver fills in as well, joins nothing and is no part of it: the outline beside it is the limb's. Limit: the
    unit is a connected component of the fill, so a notch that the closing has joined to a ribbon's fill is one with it, and
    is taken for out of sight like the rest of it: nothing in the mask says it from hair that the limb goes on behind."""
    n, comp = cv2.connectedComponents(gap.astype(np.uint8), connectivity=8)
    touched = {}                                       # (limb, connector) -> the pieces of the limb that it touches
    for q in np.flatnonzero(group):
        for cn in np.unique(comp[(cv2.dilate((lab == q).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) & gap]):
            touched.setdefault((int(group[q]), int(cn)), set()).add(int(q))
    joins = np.zeros(gap.shape, bool)
    for (_, cn), pieces in touched.items():
        if len(pieces) > 1:
            joins |= comp == cn
    return joins


def oily_maps(src, R, alpha, A, V, scale=1.0, cut=None, REG=None, core_half=1.5, band_half=4.0, tail_len=3.0,
              fill=None):
    """Whole image: (tone, core, band, tail, facing, centre, zone), each HxW float32, 0 outside the regions.

    src: BGR art. R: the visible stocking, region index per pixel. alpha: soft coverage (render_oily applies it).
    A, V: the courses' frame. cut: the bands along walls where V and A jump (Document.cut_map), or None. REG: the
    painted regions before the colour test (geometry), or None to use R. fill: {region index: bool mask} of what the
    solver filled in beside each region (Document.filled_map), or None: the pieces of a limb that something the
    selection leaves out cuts across (a ribbon, a hand, a band of hair) are one limb for how far it runs and where its
    glint goes on (_pieces); the glints they show are their own, and the maps are on the painted pixels only. The edge the
    pieces of such a limb have at the ribbon is no outline either: the limb goes on behind it (_frame), so a cut across
    the limb aslant does not skew its middle, and the glint at the cut lines up with the one beyond it.
    tone: -1..1, the region's smoothed brightness within its own range (with a floor). core, band, tail: each glint's
    gloss lobe: gaussians of sigma CORE_REL and BAND_REL, and an exponential fall-off TAIL_REL long, all in half-widths
    of the limb where the glint is (so a thin leg has a narrow glint and a thigh a broad one), widened where the painted
    highlight is broad, and never narrower than core_half / band_half / tail_len px (times scale), the least a pixel
    grid draws. facing: 0..1. centre: 1 at a glint's very centre, where its texture is washed out. zone: 0..1, how far
    the zones (black edges, pale middle) are to be believed: 1 on a dark stocking where the outline is seen, 0 on a pale
    one, where it is out of sight, and on slivers.
    """
    h_, w_ = R.shape
    Y = luminance(src)
    geo = REG if REG is not None else R
    tone, core, band, tail, centre, facing, zone = (np.zeros((h_, w_), np.float32) for _ in range(7))
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
        dark = float(1 - knit.sstep(DARK[0], DARK[1], float(np.median(Y[seen]))))
        body = G if cut is None else G & ~cut
        gap = None if fill is None else fill.get(int(i))
        lab, group, span = _pieces(body, gap, V, A)
        # the pieces of a limb something cuts across (a ribbon, a hand, hair) have the edge they have there for no outline:
        # the limb goes on behind it. Not a notch in the outline the solver fills in on its own, which joins nothing, nor, side
        # by side, what is between two pieces: as far as can be told it is outside
        behind = cv2.dilate(_joins(lab, group, gap).astype(np.uint8), ring) > 0 if group.any() else None
        jobs = []
        for j in (int(x) for x in np.unique(lab[lab > 0])):
            m = lab == j
            Vg, Ag = V[m], A[m]
            frame = _frame(Vg, Ag, hidden[m], scale)
            if group[j] and behind[m].any():
                # with the limb's edge at the connector out of sight; the limb is no narrower than it was seen without it, so
                # a few whole cross-sections (a toe) do not make it narrow, and where none is whole, or it believes the outline
                # hardly anywhere (a sliver: CUT_TRUST), the piece is measured as before
                cut_frame = _frame(Vg, Ag, hidden[m] | behind[m], scale, hmed_min=frame[4])
                if cut_frame[6] and cut_frame[7].max() >= CUT_TRUST * frame[7].max():
                    frame = cut_frame
            k, c, h, hf, hmed, tilt, whole, trust = frame
            hk = h[k]
            u = np.clip((Ag - c[k]) / hf[k], -1, 1)
            facing[m] = np.sqrt(1 - u * u) * np.cos(tilt[k])
            vis = seen[m]
            if vis.sum() < MIN_PIECE:
                continue
            believed = dark * trust * knit.sstep(HALF_ZONE[0], HALF_ZONE[1], hmed)       # per band of V
            zone[m] = believed[k]
            pure = (cv2.erode(seen.astype(np.uint8), disc, borderType=cv2.BORDER_REPLICATE) > 0)[m]
            if pure.sum() >= MIN_PIECE:
                vis = pure
            fit, absolute, den, wlen, v0, a0, ab, noise = _lighting(Y[m][vis], Vg[vis], Ag[vis], k[vis],
                                                                    int(k.max()) + 1, hmed, scale)
            middle, kq = None, None
            if whole:
                # where each cell lies across the limb, in half-widths from its centre line (of the limb's size, as
                # seen, not the silhouette's: a side out of sight is no edge). Where no cross-section was seen whole
                # the middle is only assumed (a hidden side's edge, for facing), and where no silhouette is seen at
                # all there is none to speak of: the glints go where their light does
                kq = np.clip(np.floor((v0 + wlen * (np.arange(fit.shape[0]) + 0.5) - Vg.min()) / _band(scale)),
                             0, len(c) - 1).astype(np.int64)
                middle = (a0 + ab * (np.arange(fit.shape[1]) + 0.5)[None, :] - c[kq][:, None]) / h[kq][:, None]
            tracks = _tracks(fit, absolute, den, noise, reach=int(round(2 * hmed / wlen)), middle=middle)
            jobs.append(SimpleNamespace(j=j, Vg=Vg, Ag=Ag, k=k, c=c, h=h, hk=hk, hmed=hmed, believed=believed,
                                        fit=fit, v0=v0, wlen=wlen, a0=a0, ab=ab, middle=middle, kq=kq, tracks=tracks,
                                        vlo=float(Vg.min()), vhi=float(Vg.max()), vmean=float(Vg.mean()), size=int(m.sum())))
        # every piece measured: where each limb's pieces have a painted glint at their ends, for the ones that have none
        ends = {jb.j: _ends(jb.tracks, jb.kq, jb.c, jb.h, jb.a0, jb.ab) for jb in jobs if group[jb.j] and jb.middle is not None}
        for jb in jobs:
            m = lab == jb.j
            Vg, Ag, k, c, h, hk, hmed, believed = jb.Vg, jb.Ag, jb.k, jb.c, jb.h, jb.hk, jb.hmed, jb.believed
            fit, v0, wlen, a0, ab, middle, kq, tracks = jb.fit, jb.v0, jb.wlen, jb.a0, jb.ab, jb.middle, jb.kq, jb.tracks
            drawn = tracks
            t = (Vg - v0) / wlen - 0.5                           # every pixel's position in rows
            if middle is not None:
                length, held, g = float(np.ptp(Vg)) + 1.0, 0.0, group[jb.j]
                if g:
                    # one limb in pieces: it runs as far as all of them, and a piece with no glint of its own goes on
                    # with the glint of the nearest piece that has one, from its end toward this one
                    length = max(length, span[g][1] - span[g][0] + 1.0)
                    held = _nearest(jb, [o for o in jobs if o is not jb and group[o.j] == g and ends.get(o.j)], ends)
                drawn = _floor_glint(tracks, fit.shape[0], length, hmed, kq, c, h, a0, ab, believed, held, t)
            if not drawn:
                continue
            ys, xs = np.nonzero(m)
            bx0, by0 = int(xs.min()), int(ys.min())
            box = (int(ys.max()) - by0 + 1, int(xs.max()) - bx0 + 1)
            exact = 3 * band_half * 2.0 * scale                 # px: within this, the lobe's shape needs exact distance
            wmed = float(np.median(np.concatenate([tr[3] for tr in tracks]))) if tracks else 1.0
            acc = [np.zeros(m.sum(), np.float32) for _ in range(4)]
            for tr in drawn:
                rows, tu, st, wd, su, dl = tr[:6]
                # a track may count its rows in other steps than the fit's (the floor of a piece of one row: _floor_glint)
                tt = t if len(tr) < 8 else (t - tr[7][0]) * tr[7][1] - 0.5
                at = (tt >= rows[0]) & (tt <= rows[-1])
                curve = _curve(rows, a0 + ab * tu, st, dl, su, tt, Ag, xs, ys, ab, floor=TOL_REL * hmed,
                               free=tr[6] if len(tr) > 6 else None)
                if curve is None or not at.any():
                    continue
                ti = tt[at]
                g_s = np.interp(ti, rows, st)
                flat = np.clip(np.interp(ti, rows, wd) / max(wmed, 1e-6), 0.7, 2.5)
                # the lobe's widths on screen (px): a share of the limb's half-width where the glint is (CORE_REL ..),
                # more where the painted highlight is broad, never less than the least a pixel grid can draw
                rel = np.clip(0.5 + 0.5 * flat, 0.8, 1.6)
                cw = np.maximum(CORE_REL * hk[at] * rel, core_half * scale)
                bw = np.maximum(BAND_REL * hk[at] * rel, band_half * scale)
                tw = np.maximum(TAIL_REL * hk[at] * rel, tail_len * scale)
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
                for a, val in zip(acc, (np.exp(-0.5 * (d / cw) ** 2) * g_s,
                                        np.exp(-0.5 * (d / bw) ** 2) * g_s,
                                        np.exp(-d / tw) * g_s,
                                        np.exp(-0.5 * (d / (1.3 * cw)) ** 2) * (g_s > 0.05))):
                    a[at] = np.maximum(a[at], val)
            core[m], band[m], tail[m], centre[m] = acc
        if cut is not None and (G & cut).any() and body.any():
            # the wall's own band takes its maps from the nearest stocking beside it, so no seam opens along it
            gap = G & cut
            iy, ix = ndi.distance_transform_edt(~body, return_distances=False, return_indices=True)
            for mp in (core, band, tail, centre, facing, zone):
                mp[gap] = mp[iy[gap], ix[gap]]
    return tone, core, band, tail, facing, centre, zone


def render_oily(src, R, V, A, alpha, g, s, tone, core, band, tail, facing, centre, zone, noise):
    """BGR uint8 of the (margined) crop. g: look.geometry; s: strength (1 = 100%); tone .. zone: oily_maps()
    cropped like src; noise: the scene's grain fields (knit.grain_noise), cropped like src."""
    p = g['period']
    gn, gc = noise
    phi = V / p + 0.37 * R
    base, _ = knit.render_grain(src, R, phi, A / (p * g['wale_ratio']), alpha, None, knit_amp=0.025 * s,
                                grain=0.010 * s, grain_dark=0.005 * s, chroma=0.15, f_lo=g['f_lo'], f_hi=g['f_hi'],
                                noise=(gn, gc))
    out = base.astype(np.float32)
    a3 = alpha[..., None]
    z3 = zone[..., None]
    warm = np.array([0.35, 0.65, 1.0], np.float32)                           # B, G, R
    # translucency: skin through the middle, denser fabric at the silhouette
    see = (facing ** 2 * alpha)[..., None]
    out *= 1 + 0.35 * s * see * warm
    out *= 1 - 0.30 * s * ((1 - facing) ** 1.5)[..., None] * a3 * (1 - z3)
    # the zones of a dark stocking: the fabric's thickness along the line of sight is 1 / facing, so the edges go black
    out *= 1 - z3 * (1 - np.exp(-KAPPA * s * (1 / np.clip(facing, 0.15, 1.0) - 1))[..., None]) * a3
    sink = np.clip(-tone, 0, 1) ** 1.2
    out *= (1 - 0.30 * s * sink * alpha)[..., None]
    # what the glint reflects: the courses (faded where they would alias) and a little grain, 0..1
    same = knit._same_region(R)
    keep = (1 - knit.sstep(g['f_lo'], g['f_hi'], _footprint(V / p, same))) * same
    tex = 0.5 + 0.5 * np.clip(0.6 * np.cos(2 * np.pi * phi) * keep + 0.25 * gn, -1, 1)
    sheen = 0.20 * s * np.clip(tone, 0, 1) ** 1.6
    # texture shows on the flanks of the glint and fades out toward its centre, which stays clean
    flank = 1 - knit.sstep(0.25, 0.75, centre)
    t_core = 1 - flank * TEX_CORE * (1 - tex)
    glint = s * (W_CORE * core * t_core + W_BAND * band * (1 - flank * TEX_BAND * (1 - tex))
                 + W_TAIL * tail * (1 - flank * (0.15 - 0.15 * tex)))
    bright = np.clip((sheen + glint) * alpha, 0, 0.93)[..., None]        # soft coverage holds for every reflection
    lift = K_SEE * s * see * z3 * warm                                   # the skin through a dark stocking's middle
    out = 255 - (255 - out) * (1 - bright) * (1 - lift)
    return np.clip(np.round(out), 0, 255).astype(np.uint8)

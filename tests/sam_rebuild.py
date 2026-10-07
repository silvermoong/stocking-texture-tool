"""Rebuild the sample's five regions with SAM clicks, the way a user would, and compare with the hand-made ones.

    python tests/sam_rebuild.py <out_dir> [max_clicks]

Each region starts empty. A simulated user clicks the deepest point of the largest remaining error: left click
where the region is missing, right click where it spills over, at most max_clicks (default 5) per region, and
picks whichever of SAM's three candidates (Tab) looks best. Reports per-region IoU before and after the coverage
step, and how far the courses solved on the rebuilt regions (with the fixture's own strokes) are from the reference.
"""
import os
import sys
import time

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stocking import coverage, sam  # noqa: E402
from stocking import guide_fields as gf  # noqa: E402
from stocking import psd_io  # noqa: E402
from stocking.document import Document, clean_segment  # noqa: E402
from sample_data import PSD  # noqa: E402

OUT = sys.argv[1]
MAX_CLICKS = int(sys.argv[2]) if len(sys.argv) > 2 else 5
os.makedirs(OUT, exist_ok=True)

art, regions, strokes, _ = psd_io.read_guides(PSD)
names, targets = list(regions), [gf.keep_major_parts(m) for m in regions.values()]
H, W = strokes.shape


def iou(a, b):
    return (a & b).sum() / max((a | b).sum(), 1)


def deepest(mask):
    d = cv2.distanceTransform(np.pad(mask, 1).astype(np.uint8), cv2.DIST_L2, 5)[1:-1, 1:-1]
    y, x = np.unravel_index(np.argmax(d), d.shape)
    return float(x), float(y), float(d[y, x])


def largest_blob(mask):
    m = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if n <= 1:
        return None, 0
    i = 1 + int(np.argmax(st[1:, 4]))
    return lab == i, int(st[i, 4])


sam.service.wait_ready()
doc = Document(art, 'rebuild')
with doc.lock:
    for n in names:
        doc._new_region(n)
    doc._touch()
t = time.time()
sam.service.ensure_embedded(doc)
print(f'SAM on {sam.service.device_name}; embedding {time.time() - t:.2f}s')

log = []
REF = gf.label_regions(targets)
for i, (r, target, name) in enumerate(zip(doc.regions, targets, names), 1):
    clicks = []
    for _ in range(MAX_CLICKS):
        L = gf.label_regions([q.mask for q in doc.regions])
        missing, n_miss = largest_blob(target & (L != i))
        extra, n_extra = largest_blob((L == i) & ~target)
        if max(n_miss, n_extra) < 0.01 * target.sum():
            break
        subtract = n_extra > n_miss
        x, y, _ = deepest(extra if subtract else missing)
        t = time.time()
        masks, best, _ = sam.service.candidates(doc, x, y)
        dt = time.time() - t
        # the user cycles with Tab and keeps the candidate whose colours on screen look most right
        scores = []
        for m in masks:
            box, seg = clean_segment(m)
            trial = L.copy()
            if box is not None:
                x0, y0, x1, y1 = box
                sub = trial[y0:y1, x0:x1]
                if subtract:
                    sub[seg & (sub == i)] = 0
                else:
                    sub[seg] = i
            scores.append(int((trial == REF).sum()))
        k = int(np.argmax(scores))
        if scores[k] <= int((L == REF).sum()):
            clicks.append(('x', int(x), int(y), 0, round(dt * 1000)))     # no candidate helps: undo, move on
            break
        doc.segment_click(r.id, x, y, subtract, masks, best)
        while doc._seg_last['k'] != k:
            doc.cycle_segment(1)
        clicks.append(('-' if subtract else '+', int(x), int(y), k - best, round(dt * 1000)))
        if os.environ.get('REBUILD_TRACE'):
            print(f'  {name} {clicks[-1][:3]} cand {k} -> sizes', [int(q.mask.sum()) for q in doc.regions])
    log.append((name, clicks))

REG_ref = REF
REG = gf.label_regions([r.mask for r in doc.regions])
lab = coverage.lab_of(art)
stock_ref, _ = coverage.stocking_coverage(lab, REG_ref)
stock, _ = coverage.stocking_coverage(lab, REG)

ref_fields = gf.solve_guides(targets, strokes)
new_fields = gf.solve_guides([r.mask for r in doc.regions], strokes)

print(f'{"region":6} clicks  IoU  IoU(after coverage)  courses vs reference (median/p90 deg, where both exist)')
for i, (name, clicks) in enumerate(log, 1):
    a, b = REG == i, REG_ref == i
    ac, bc = a & stock, b & stock_ref
    _, _, NX0, NY0, _ = ref_fields
    R1, _, NX1, NY1, _ = new_fields
    sel = cv2.erode(((ref_fields[0] == i) & (R1 == i)).astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool)
    ang = np.degrees(np.arccos(np.clip(np.abs(NX0[sel] * NX1[sel] + NY0[sel] * NY1[sel]), 0, 1)))
    seq = ' '.join(f'{c[0]}{"" if c[3] == 0 else f"(Tab{c[3]:+d})"}' for c in clicks)
    crs = f'{np.median(ang):.1f} / {np.percentile(ang, 90):.1f}' if sel.any() else 'n/a (no common solved area)'
    print(f'{name:6} {len(clicks)}  {iou(a, b):.3f}  {iou(ac, bc):.3f}   {crs}'
          f'   [{seq}]  {[c[4] for c in clicks]} ms  px {a.sum()} vs {b.sum()}')

missing = (REG_ref > 0) & stock_ref & ~((REG > 0) & stock)
extra = (REG > 0) & stock & ~((REG_ref > 0) & stock_ref)
print(f'after coverage, vs the fixture: {missing.sum()} px missing, {extra.sum()} px extra '
      f'({100 * missing.sum() / stock_ref.sum():.1f}% / {100 * extra.sum() / stock_ref.sum():.1f}% of the stocking)')
dist = cv2.distanceTransform((REG == 0).astype(np.uint8), cv2.DIST_L2, 5)
core = missing & (dist > 6)
print(f'  of the missing, {100 * (1 - core.sum() / max(missing.sum(), 1)):.0f}% is a rim within 6 px of the '
      f'rebuilt outline; {core.sum()} px ({100 * core.sum() / stock_ref.sum():.1f}%) is farther in (touch-up work)')
n, lab, st, _ = cv2.connectedComponentsWithStats(core.astype(np.uint8), connectivity=8)
big = sorted(((int(s[4]), int(s[0] + s[2] / 2), int(s[1] + s[3] / 2)) for s in st[1:]), reverse=True)[:5]
print('  largest touch-up spots (px, centre x, y):', big)

vis = (art * 0.45).astype(np.uint8)
vis[(REG > 0) & (REG_ref > 0)] = (art[(REG > 0) & (REG_ref > 0)] * 0.5 + np.array([60, 60, 60])).astype(np.uint8)
vis[missing] = (255, 60, 60)
vis[extra] = (60, 200, 255)
cv2.imencode('.png', cv2.cvtColor(cv2.resize(vis, (W // 2, H // 2), interpolation=cv2.INTER_AREA),
                                  cv2.COLOR_RGB2BGR))[1].tofile(os.path.join(OUT, 'rebuild_diff.png'))
palette = np.array([[0, 0, 0], [61, 139, 255], [255, 122, 61], [176, 92, 255], [31, 201, 154], [255, 197, 61]])
over = (art * 0.55 + palette[REG] * 0.45).astype(np.uint8)
over[REG == 0] = art[REG == 0]
cv2.imencode('.png', cv2.cvtColor(cv2.resize(over, (W // 2, H // 2), interpolation=cv2.INTER_AREA),
                                  cv2.COLOR_RGB2BGR))[1].tofile(os.path.join(OUT, 'rebuild_regions.png'))
doc.close()

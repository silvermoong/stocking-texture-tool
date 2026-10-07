"""Reproduce the measured numbers end to end on the sample picture (see sample_data.py).

    python tests/verify.py <out_dir>

Needs numpy, scipy, opencv, contourpy, pillow, psd-tools >= 1.24. Writes previews and a texture PSD to out_dir.
"""
import os
import sys
import time

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stocking import coverage  # noqa: E402
from stocking import guide_fields as gf  # noqa: E402
from stocking import knit  # noqa: E402
from stocking import psd_io  # noqa: E402
from stocking import symmetry  # noqa: E402
from sample_data import PNG, PSD  # noqa: E402

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)

art, regions, strokes, _ = psd_io.read_guides(PSD)
src_png = knit.load(PNG)
src = cv2.cvtColor(art, cv2.COLOR_RGB2BGR)
print(f'guides: {list(regions)}; art vs sample.png max diff {int(np.abs(src.astype(int) - src_png.astype(int)).max())}')
names = list(regions)
masks = [regions[n] for n in names]

t = time.time()
REG, V, NX, NY, A = gf.solve_guides(masks, strokes)
print(f'solve_guides (5 regions, 1280x1920): {time.time() - t:.1f}s')
agy, agx = np.gradient(A)
along = agx * (-NY) + agy * NX
for i, n in enumerate(names, 1):
    sel = cv2.erode((REG == i).astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool)
    print(f'  {n}: dA/ds p10/50/90 {np.percentile(along[sel], 10):.2f} {np.median(along[sel]):.2f} {np.percentile(along[sel], 90):.2f}')

# stocking coverage: rough regions minus colours far from their dominant chroma (gold trim, gloves, hair, skin)
stock, alpha = coverage.stocking_coverage(coverage.lab_of(art), REG)
R = np.where(stock, REG, 0).astype(np.int8)

period = 4.6
t = time.time()
out, _ = knit.render(src, R, V / period + 0.37 * R, A / (period * 1.25), alpha)
print(f'knit render: {time.time() - t:.2f}s')
theta = np.deg2rad(32)
side = np.select([np.isin(R, [1, 4]), np.isin(R, [2, 5])], [1.0, -1.0], 0.0)    # pairs: left +theta, right -theta
lines, _ = knit.render_lines(src, R, np.cos(theta) * V / period + np.sin(theta * side) * A / period, alpha)
for tag, img in (('knit', out), ('lines', lines)):
    knit.write(os.path.join(OUT, f'{tag}_50.png'), cv2.resize(img, (640, 960), interpolation=cv2.INTER_LINEAR))
    for nm, (x0, y0, x1, y1) in {'thigh': (280, 320, 760, 720), 'cleavage': (440, 1200, 840, 1600),
                                 'far': (700, 0, 1100, 240)}.items():
        knit.write(os.path.join(OUT, f'{tag}_{nm}_200.png'),
                   cv2.resize(img[y0:y1, x0:x1], None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST))

for a, b, nm in [(0, 1, 'thighs'), (3, 4, 'breasts')]:
    mirrored, rms = symmetry.mirror_strokes(masks[a], masks[b], strokes)
    mixed = strokes.copy()
    mixed[masks[b]] = mirrored[masks[b]]
    R2, V2, *_ = gf.solve_guides(masks, mixed)
    g1 = np.gradient(cv2.GaussianBlur(V, (0, 0), 2)); g2 = np.gradient(cv2.GaussianBlur(V2, (0, 0), 2))
    ang = np.degrees(np.arccos(np.clip(np.abs(g1[0] * g2[0] + g1[1] * g2[1]) / (np.hypot(*g1) * np.hypot(*g2) + 1e-12), 0, 1)))
    sel = cv2.erode(((REG == b + 1) & (R2 == b + 1)).astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool)
    print(f'mirror {nm}: outline fit {rms:.1f}px; mirrored vs drawn courses median {np.median(ang[sel]):.1f} p90 {np.percentile(ang[sel], 90):.1f} deg')

cov = np.where(stock, 255, 0).astype(np.uint8)
p = psd_io.write_texture_psd(os.path.join(OUT, 'texture.psd'), art, cv2.cvtColor(out, cv2.COLOR_BGR2RGB), cov)
from psd_tools import PSDImage  # noqa: E402
doc = PSDImage.open(p)
for L in doc:
    if not L.is_group():
        L.visible = True
comp = np.asarray(doc.composite(force=True).convert('RGB')).astype(int)
err = np.abs(comp - cv2.cvtColor(out, cv2.COLOR_BGR2RGB).astype(int)).max(2)
print(f'texture PSD re-composite vs baked: max err {err.max()} (psd-tools compositor; Photoshop itself not yet checked)')

"""Compares fresh screenshots with the asset library's originals, pixel by pixel (see demo-images.md, section 9).

    python compare_shots.py black D:\\Video\\assets\\stocking-promo\\shots\\b1-black
    python compare_shots.py white D:\\Video\\assets\\stocking-promo\\shots\\b1-white

For each shot: "identical", or how many pixels differ and where. A document rebuilt as the original was (b1_setup.py:
SAM picks and the strokes through the API) reproduces every texture crop below exactly; the page shots differ by the
panel and the language switch, which are UI.
"""
import os
import sys

import numpy as np
from PIL import Image

LIB = r'D:\Video\assets\stocking-promo\readme'
MAPS = {
    'black': {
        '04-look.png': 'b1-black-04-texture-page.png',
        '11-style-fine-lines.png': 'b1-black-style-1-fine-lines.png',
        '12-style-knit.png': 'b1-black-style-2-knit.png',
        '13-style-slanted-lines.png': 'b1-black-style-3-slanted-lines.png',
        '14-style-kase.png': 'b1-black-style-4-kase.png',
        '15-style-glossy.png': 'b1-black-style-5-glossy.png',
        '16-style-coil.png': 'b1-black-style-6-coil.png',
        '20-density-70.png': 'b1-black-density-070.png',
        '21-density-100.png': 'b1-black-density-100.png',
        '22-density-130.png': 'b1-black-density-130.png',
        '23-strength-50.png': 'b1-black-strength-050.png',
        '24-strength-100.png': 'b1-black-strength-100.png',
        '25-strength-160.png': 'b1-black-strength-160.png',
        '26-tilt-10.png': 'b1-black-tilt-10.png',
        '27-tilt-32.png': 'b1-black-tilt-32.png',
        '28-tilt-55.png': 'b1-black-tilt-55.png',
        '07b-look-slanted-lines.png': 'b1-black-slanted-lines-page.png',
        '09b-look-glossy.png': 'b1-black-glossy-page.png',
    },
    'white': {
        '04-look.png': 'b1-white-04-texture-page.png',
        '11-style-fine-lines.png': 'b1-white-style-1-fine-lines.png',
        '12-style-knit.png': 'b1-white-style-2-knit.png',
        '13-style-slanted-lines.png': 'b1-white-style-3-slanted-lines.png',
        '14-style-kase.png': 'b1-white-style-4-kase.png',
        '15-style-glossy.png': 'b1-white-style-5-glossy.png',
        '16-style-coil.png': 'b1-white-style-6-coil.png',
    },
}


def load(path):
    return np.asarray(Image.open(path).convert('RGB')).astype(np.int16)


def main(which, folder):
    for new, old in MAPS[which].items():
        if not os.path.exists(os.path.join(folder, new)) or not os.path.exists(os.path.join(LIB, old)):
            print(f'{new:28s} not there ({old})')
            continue
        a, b = load(os.path.join(folder, new)), load(os.path.join(LIB, old))
        if a.shape != b.shape:
            print(f'{new:28s} SIZE {a.shape[:2]} vs {b.shape[:2]}  ({old})')
            continue
        d = np.abs(a - b).max(axis=2)
        n = int((d > 0).sum())
        if not n:
            print(f'{new:28s} identical  ({old})')
            continue
        ys, xs = np.nonzero(d)
        brighter = int((a - b).sum(axis=2)[d > 0].clip(0, 1).sum())
        print(f'{new:28s} {n} px differ ({100 * n / d.size:.3f}%, {brighter} of them brighter)  max {int(d.max())}  '
              f'bbox x {xs.min()}..{xs.max()} y {ys.min()}..{ys.max()}  ({old})')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])

"""Builds the app icon from a square picture, written as stocking/static/icon.ico (16-256 px: the desktop shortcut,
Windows and the page's favicon, which the Edge app window shows in the taskbar) and icon-256.png (the favicon for
browsers that prefer a PNG, and the README).

    python tools/make_icon.py <picture>            the picture is put on a tile with rounded corners
    python tools/make_icon.py --tiled <picture>    the picture already is a tile on a light background: the tile is
                                                   cut out and the background made transparent

Each size is scaled from the picture on its own (not from a larger icon), and edges are drawn or cut at full size
before scaling down, so the small sizes stay as sharp as they can.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'stocking', 'static')
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
PNG_SIZES = (256,)
PAD = 8 / 256           # margin around the tile, as a part of the icon's side
RADIUS = 52 / 256       # corner radius, as a part of the icon's side
BG_LIGHT = 200          # --tiled: background is lighter than this (0-255) in every channel


def shrink(im, size):
    """Scale down in halving steps, then to the exact size, all with Lanczos."""
    while im.width >= 2 * size:
        im = im.reduce(2)
    return im.resize((size, size), Image.LANCZOS)


def tile(picture, size):
    pad = round(size * PAD)
    inner = size - 2 * pad
    out = Image.new('RGB', (size, size), (255, 255, 255))
    out.paste(shrink(picture, inner), (pad, pad))
    s = 4
    mask = Image.new('L', (size * s, size * s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((pad * s, pad * s, (pad + inner) * s - 1, (pad + inner) * s - 1),
                                           round(size * RADIUS * s), fill=255)
    out.putalpha(mask.resize((size, size), Image.LANCZOS))
    return out


def cut_tile(picture):
    """A picture drawn as a tile on a light background: the square around the tile (a little margin kept, as PAD
    keeps for a made tile), with the background made transparent.

    The tile is the dark shape with everything inside it (binary_fill_holes): opaque. A pixel on its rim is a blend
    of the tile's edge colour and the background, so its alpha is how far it sits from the background toward the
    tile's edge colour (read just inside the rim), and its colour is that edge colour: no light fringe on a dark
    taskbar. The background's level is read from the picture's corners (an off-white is common)."""
    a = np.asarray(picture.convert('RGB')).astype(np.float32)
    dark = a.max(axis=2) < BG_LIGHT
    ys, xs = np.nonzero(dark)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    side = max(x1 - x0, y1 - y0)
    margin = round(side * PAD / (1 - 2 * PAD))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    half = side / 2 + margin
    box = (round(cx - half), round(cy - half), round(cx + half), round(cy + half))
    k = max(4, round(0.02 * min(a.shape[:2])))
    bg = np.median(np.concatenate([a[:k, :k], a[:k, -k:], a[-k:, :k], a[-k:, -k:]]).reshape(-1, 3), axis=0)
    rgb = np.asarray(Image.fromarray(a.astype(np.uint8)).crop(box)).astype(np.float32)
    outside = (np.arange(box[0], box[2])[None, :] < 0) | (np.arange(box[0], box[2])[None, :] >= a.shape[1]) | \
              (np.arange(box[1], box[3])[:, None] < 0) | (np.arange(box[1], box[3])[:, None] >= a.shape[0])
    rgb[outside] = bg                                           # past the picture's edge: background, not black
    solid = ndimage.binary_fill_holes(rgb.max(axis=2) < BG_LIGHT)
    inner = ndimage.binary_erosion(solid, iterations=3)
    rim = ndimage.binary_dilation(solid, iterations=2) & ~inner
    # the tile's edge colour near each rim pixel: the median of the solid pixels just inside
    edge = np.median(rgb[ndimage.binary_dilation(rim, iterations=2) & inner], axis=0)
    span = np.maximum(np.abs(bg - edge).max(), 1.0)
    t = np.clip(np.abs(bg[None, None] - rgb).max(axis=2) / span, 0, 1)    # 0 = background, 1 = tile edge colour
    alpha = np.where(inner, 1.0, np.where(rim, t, 0.0))
    col = np.where(rim[..., None] & ~inner[..., None], edge[None, None], rgb)
    out = np.dstack([np.clip(col, 0, 255), alpha * 255]).round().astype(np.uint8)
    return Image.fromarray(out, 'RGBA')


def shrink_rgba(im, size):
    """shrink() for a picture with transparency: colours averaged by alpha, so transparent pixels add no fringe."""
    return shrink(im.convert('RGBa'), size).convert('RGBA')


def main(path, tiled=False):
    pic = Image.open(path)
    if tiled:
        big = cut_tile(pic)
        make = lambda n: shrink_rgba(big, n)
    else:
        pic = pic.convert('RGB')
        side = min(pic.size)
        left, top = (pic.width - side) // 2, pic.height - side     # a tall picture keeps its bottom (the feet)
        pic = pic.crop((left, top, left + side, top + side))
        make = lambda n: tile(pic, n)
    icons = [make(n) for n in ICO_SIZES]
    icons[-1].save(os.path.join(STATIC, 'icon.ico'), sizes=[(n, n) for n in ICO_SIZES], append_images=icons[:-1])
    for n in PNG_SIZES:
        make(n).save(os.path.join(STATIC, f'icon-{n}.png'), optimize=True)
    print('wrote', ', '.join(['icon.ico'] + [f'icon-{n}.png' for n in PNG_SIZES]), 'in', STATIC)


if __name__ == '__main__':
    args = sys.argv[1:]
    tiled = '--tiled' in args
    args = [a for a in args if a != '--tiled']
    if len(args) != 1:
        sys.exit(__doc__)
    main(args[0], tiled)

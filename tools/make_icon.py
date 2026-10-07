"""Builds the app icon from a square picture: the picture on a tile with rounded corners, written as
stocking/static/icon.ico (16-256 px: the desktop shortcut, Windows and the page's favicon, which the Edge app window
shows in the taskbar) and icon-256.png (the favicon for browsers that prefer a PNG, and the README).

    python tools/make_icon.py <picture>

Each size is scaled from the picture on its own (not from a larger icon), and the corners are drawn at 4x and
scaled down, so the small sizes stay as sharp as they can.
"""
import os
import sys

from PIL import Image, ImageDraw

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'stocking', 'static')
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
PNG_SIZES = (256,)
PAD = 8 / 256           # margin around the tile, as a part of the icon's side
RADIUS = 52 / 256       # corner radius, as a part of the icon's side


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


def main(path):
    pic = Image.open(path).convert('RGB')
    side = min(pic.size)
    left, top = (pic.width - side) // 2, pic.height - side         # a tall picture keeps its bottom (the feet)
    pic = pic.crop((left, top, left + side, top + side))
    icons = [tile(pic, n) for n in ICO_SIZES]
    icons[-1].save(os.path.join(STATIC, 'icon.ico'), sizes=[(n, n) for n in ICO_SIZES], append_images=icons[:-1])
    for n in PNG_SIZES:
        tile(pic, n).save(os.path.join(STATIC, f'icon-{n}.png'), optimize=True)
    print('wrote', ', '.join(['icon.ico'] + [f'icon-{n}.png' for n in PNG_SIZES]), 'in', STATIC)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])

"""The README's opening image: one picture, original and finished, with a divider sweeping across.

    python .scratch/release/make_hook.py

Reads hook/original.png and hook/finished.png (the same 1536 x 1536 picture before and after the tool) and writes
docs/images/hook.png (an animated PNG; GitHub plays it). The crop holds the whole of both legs and the shoes, and is
scaled once (Lanczos) to WIDTH, which GitHub shows unscaled, so the only resampling is this one, checked by eye for
moire. The first frame is a half-and-half split, so a viewer that does not animate still shows the comparison.
Original left of the divider, finished right of it, as in the tool's own Whole preview.
"""
import os

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, 'docs', 'images')
BOX = (196, 100, 1336, 1490)        # x0, y0, x1, y1 in the source: both legs, thighs to heels, and the shadow
WIDTH = 820                         # GitHub's README column: wider images get scaled by the browser
FPS = 20
SS = 4                              # supersampling for the divider and its grip


def ease(t):
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def timeline(w):
    """(divider x, frame ms) per frame: split, sweep to all-finished, hold, sweep to all-original, hold, back."""
    keys = [(0.5, 1000), (0.0, 1300), (1.0, 900), (0.5, 0)]        # (position, hold after arriving there)
    moves = [0.7, 1.3, 0.7]                                          # seconds per sweep
    frames = [(keys[0][0], keys[0][1])]
    for (a, _), (b, hold), sec in zip(keys, keys[1:], moves):
        n = max(int(round(sec * FPS)), 2)
        for k in range(1, n + 1):
            frames.append((a + (b - a) * ease(k / n), 1000 // FPS))
        frames[-1] = (b, 1000 // FPS + hold)
    frames.pop()                                                     # the last frame equals the first
    return [(int(round(p * w)), ms) for p, ms in frames]


def grip(w, h):
    """The divider at x = 0 of a (2 * r + 1)-wide strip: RGBA, drawn at SS x and scaled down."""
    r = 17
    W, H = (2 * r + 2) * SS, h * SS
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = W // 2
    d.rectangle((cx - 2 * SS, 0, cx + 2 * SS, H), fill=(0, 0, 0, 60))                # soft edge either side
    d.rectangle((cx - SS, 0, cx + SS, H), fill=(255, 255, 255, 255))                  # the 2 px line
    cy = H // 2
    d.ellipse((cx - r * SS - SS, cy - r * SS - SS, cx + r * SS + SS, cy + r * SS + SS), fill=(0, 0, 0, 70))
    d.ellipse((cx - r * SS, cy - r * SS, cx + r * SS, cy + r * SS), fill=(255, 255, 255, 255))
    a, b, t = 5 * SS, 11 * SS, 5 * SS                                                # two arrow heads
    d.polygon([(cx - b, cy), (cx - a, cy - t), (cx - a, cy + t)], fill=(40, 40, 40, 255))
    d.polygon([(cx + b, cy), (cx + a, cy - t), (cx + a, cy + t)], fill=(40, 40, 40, 255))
    return im.resize((W // SS, H // SS), Image.LANCZOS), r + 1


def main():
    size = (WIDTH, round((BOX[3] - BOX[1]) * WIDTH / (BOX[2] - BOX[0])))

    def load(name):
        im = Image.open(os.path.join(HERE, 'hook', name)).convert('RGB').crop(BOX)
        return im.resize(size, Image.LANCZOS)

    before, after = load('original.png'), load('finished.png')
    w, h = before.size
    g, half = grip(w, h)
    frames, durations = [], []
    for x, ms in timeline(w):
        f = after.copy()
        if x > 0:
            f.paste(before.crop((0, 0, x, h)), (0, 0))
        f.paste(g, (x - half, 0), g)                # Image.paste clips a grip running off either edge
        frames.append(f)
        durations.append(ms)
    os.makedirs(OUT, exist_ok=True)
    frames[0].save(os.path.join(OUT, 'hook.png'), save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, optimize=True)
    print(f'hook.png: {w}x{h}, {os.path.getsize(os.path.join(OUT, "hook.png")) // 1024} KB')
    print(f'{len(frames)} frames, {sum(durations) / 1000:.1f} s per loop')


if __name__ == '__main__':
    main()

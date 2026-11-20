"""Builds the README images from the promo assets. Texture is never resampled: every crop that shows texture is
taken at the asset's own pixel size, and composites stay within GitHub's ~880 px column, so no browser scaling
aliases the courses into moiré: GitHub shows a README about 830 px wide, so composites are at most 820. UI screenshots are scaled normally."""
import os
from PIL import Image

A = r'D:\Video\assets\stocking-promo\readme'
# README_IMAGES_SRC names a folder that is looked in first, file by file: retaken shots under the library's file names
# that are not in the library (yet). What is not there comes from the library, which is only ever read.
SRC = os.environ.get('README_IMAGES_SRC')
OUT = os.environ.get('README_IMAGES_OUT', r'D:\Stocking\docs\images')     # a trial run can write elsewhere
BG = (255, 255, 255)
GAP = 10


def find(name):
    mine = os.path.join(SRC, name) if SRC else None
    return mine if mine and os.path.isfile(mine) else os.path.join(A, name)


def load(name):
    return Image.open(find(name)).convert('RGB')


def row(tiles, gap=GAP, bg=BG):
    w = sum(t.width for t in tiles) + gap * (len(tiles) - 1)
    h = max(t.height for t in tiles)
    out = Image.new('RGB', (w, h), bg)
    x = 0
    for t in tiles:
        out.paste(t, (x, 0)); x += t.width + gap
    return out


def col(tiles, gap=GAP, bg=BG):
    w = max(t.width for t in tiles)
    h = sum(t.height for t in tiles) + gap * (len(tiles) - 1)
    out = Image.new('RGB', (w, h), bg)
    y = 0
    for t in tiles:
        out.paste(t, (0, y)); y += t.height + gap
    return out


def save(im, name, **kw):
    p = os.path.join(OUT, name)
    if name.endswith('.jpg'):
        im.save(p, quality=88, optimize=True, progressive=True)
    else:
        im.save(p, optimize=True)
    print(f'{name:28s} {im.size[0]}x{im.size[1]}  {os.path.getsize(p) // 1024} KB')


def shot(name, w):
    im = load(name)
    return im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)


# hero: the left knee, original and finished, black and white, at the picture's own pixels
knee = (285, 300, 690, 600)
save(col([row([load('b1-black-original.png').crop(knee), load('b1-black-finished.png').crop(knee)]),
          row([load('b1-white-original.png').crop(knee), load('b1-white-finished.png').crop(knee)])]), 'hero.png')

# the six styles on the thigh, black then white (Detail at 200%: chrome cut off, no scaling). The order is the panel's;
# 6-coil was shot after the other five (2026-10-09), hence its number
STY = ['1-fine-lines', '2-knit', '6-coil', '3-slanted-lines', '4-kase', '5-glossy']
# 130 px wide: six cells and their gaps fill the 820 px column unscaled (the cells were 157 wide when there were five)
cut = (433, 260, 563, 620)
# 油光 is for dark stockings: on white it is next to blank, so the white row leaves it out (it is the last style)
save(col([row([load(f'b1-black-style-{s}.png').crop(cut) for s in STY], gap=8),
          row([load(f'b1-white-style-{s}.png').crop(cut) for s in STY[:-1]], gap=8)], gap=8), 'styles.png')

# sliders: three settings each, same spot
sl = (367, 300, 633, 500)
for name, files in (('slider-density.png', ['b1-black-density-070', 'b1-black-density-100', 'b1-black-density-130']),
                    ('slider-strength.png', ['b1-black-strength-050', 'b1-black-strength-100', 'b1-black-strength-160']),
                    ('slider-tilt.png', ['b1-black-tilt-10', 'b1-black-tilt-32', 'b1-black-tilt-55']),
                    ('slider-sparkles.png', ['b1-black-sparkles-000', 'b1-black-sparkles-100', 'b1-black-sparkles-300'])):
    save(row([load(f + '.png').crop(sl) for f in files]), name)

# 高光粒子 (试验), on B1's left leg. The Texture page with its switch on at 亮度 100% (Detail at 100%; scaled like the
# other pages), and one strip of the left thigh down to the knee at 亮度 0 / 35 / 70 / 100% at the pictures' own pixels:
# four 200 px tiles 6 px apart, so 818 px wide
for src, dst in (('b1-black-10-particle-page.png', 'particle-page.jpg'),
                 ('b1-black-10-particle-page-en.png', 'particle-page-en.jpg')):
    save(shot(src, 1600), dst)
p_strip = (350, 300, 550, 700)
save(row([load(f'b1-black-particle-{s}.png').crop(p_strip) for s in ('000', '035', '070', '100')], gap=6),
     'particle-strength.png')

# 摩尔纹效果 (试验), on B1's left thigh. The Texture page with its switch on (Detail at 100%; scaled like the other
# pages), and 面积 35 / 50 / 70 / 100% at the pictures' own pixels: four 405 px tiles 10 px apart, so 820 px wide
for src, dst in (('b1-black-06-moire-page.png', 'moire-page.jpg'), ('b1-black-06-moire-page-en.png', 'moire-page-en.jpg')):
    save(shot(src, 1600), dst)
mk = (238, 1, 643, 406)
save(col([row([load(f'b1-black-moire-area-{a}.png').crop(mk) for a in ('035', '050')]),
          row([load(f'b1-black-moire-area-{a}.png').crop(mk) for a in ('070', '100')])]), 'moire-area.png')

# 纹理层 (试验), on B1's left leg. The Texture page with two layers laid 30 / 70 (Detail at 100%; scaled like the other
# pages), and one strip of the left thigh down to the knee with 加濑风's share at 0 / 30 / 70 / 100% (细线 for the rest) at
# the pictures' own pixels: four 200 px tiles 6 px apart, so 818 px wide
for src, dst in (('b1-black-07-layers-page.png', 'layers-page.jpg'), ('b1-black-07-layers-page-en.png', 'layers-page-en.jpg')):
    save(shot(src, 1600), dst)
strip = (350, 300, 550, 700)
save(row([load(f'b1-black-layers-{s}.png').crop(strip) for s in ('000', '030', '070', '100')], gap=6), 'layers-mix.png')

# 预设文件的导出和导入, on the Texture page. Each raw shot is the whole page at DPR 2 (3200x2000); two crops of it are kept:
# the Presets block (heading row with 导入… and 导出…, the list) and the status bar's note, which has the file's path (导出)
# or says the name was taken (导入). The tool's own dialogs are not in the pictures: the shots were taken with the file
# dialogs answered from a folder (D:\预设, D:\presets). Export left, import right when that leaves the UI at about
# its size, else one above the other; scaled like the other pages (UI only, no texture to alias)
PANEL_BG = (44, 44, 44)                 # the left panel and the status bar are the same grey
TEXT_PX = {'': 295, '-en': 490}         # width of the longer note in CSS px (Range.getBoundingClientRect, DPR 2 doubles it)


def preset_tile(name, text_css):
    im = load(name)
    w = max(540, round(text_css * 2) + 48)
    tile = Image.new('RGB', (w, 152 + 56), PANEL_BG)
    tile.paste(im.crop((0, 100, 540, 252)), (0, 0))
    tile.paste(im.crop((0, 1944, w, 2000)), (0, 152))
    return tile


for sfx in ('', '-en'):
    tiles = [preset_tile(f'b1-black-{n}{sfx}.png', TEXT_PX[sfx]) for n in ('08-presets-export', '09-presets-import')]
    side = 820 / (sum(t.width for t in tiles) + 12) >= 0.5
    both = row(tiles, gap=12) if side else col(tiles, gap=12)
    if both.width > 820:
        both = both.resize((820, round(both.height * 820 / both.width)), Image.LANCZOS)
    save(both, f'presets-share{sfx}.png')

# UI pages (scaled: overlays and text, no texture to alias)
save(shot('b1-black-01-guides.png', 1600), 'guides-page.jpg')
save(shot('b1-black-04-texture-page.png', 1600), 'texture-page.jpg')
for src, dst in (('b1-black-01-guides-en.png', 'guides-page-en.jpg'), ('b1-black-04-texture-page-en.png', 'texture-page-en.jpg')):
    if os.path.exists(find(src)):
        save(shot(src, 1600), dst)
    else:
        print(f'{dst:28s} missing: {src} not in the assets yet')
save(row([load('b1-black-02-knee-courses.png'), load('b1-black-03-ankle-courses.png')], gap=16), 'courses-knee-ankle.jpg')
# the folded leg in three steps, drawn by the user: one line each on thigh and calf, then the divider, then the knee
# arc (the Guides page zoomed on the fold; the canvas only, no panel or status line)
for k, src in enumerate(('b2-black-fold-step1-no-divider.png', 'b2-black-fold-step2-divider.png',
                         'b2-black-fold-step3-knee-arc.png'), 1):
    save(load(src).crop((420, 300, 2400, 1420)).resize((820, 464), Image.LANCZOS), f'fold-step{k}.jpg')

# the folded leg as drawn in the three steps, finished, at its own pixels (the knee and the join)
save(load('b2-black-fold-finished.png').crop((40, 560, 860, 1110)), 'fold-finished.png')
# original | finished at the picture's own pixels, at the knee and at the join (the user's 520 px halves, 30 px apart,
# each cut to 400 so the pair fits the 820 px column unscaled)
for part in ('knee', 'junction'):
    im = load(f'b2-black-fold-crop100-{part}.png')
    save(row([im.crop((60, 0, 460, 400)), im.crop((592, 0, 992, 400))], gap=20), f'fold-{part}.png')

# step 2, regions alone (no direction lines, no courses): the Guides page, and a torso's three regions (picture only)
for src, dst in (('b1-black-00-regions.png', 'regions-page.jpg'), ('b1-black-00-regions-en.png', 'regions-page-en.jpg')):
    save(shot(src, 1600), dst)
save(load('b5-black-00-regions.png').crop((902, 94, 1905, 1000)).resize((820, 741), Image.LANCZOS), 'torso-regions.jpg')

# a torso in three regions, with its direction lines and the solved courses (the Guides page, the picture only)
save(load('b5-black-01-guides.png').crop((902, 94, 1905, 1000)).resize((820, 741), Image.LANCZOS),
     'torso-courses.jpg')


# Show problems: the Detail pane at density 140% and 85%, same spot, no scaling
pc = (1798, 290, 2203, 695)
save(row([load('b2-black-04-problems-density-140.png').crop(pc), load('b2-black-05-problems-density-085.png').crop(pc)]),
     'show-problems.png')




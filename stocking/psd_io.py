"""PSD in and out for the stocking texture tool (psd-tools >= 1.24).

Round trips are checked in tests/test_export.py and tests/test_coverage_sam.py.

read_guide_layers(path) -> {art, regions, strokes, sparkle, dividers}: everything a guides PSD holds
read_guides(path)        -> art (HxWx3 RGB uint8), regions {name: bool mask}, strokes (HxW uint8 alpha) or None,
                            sparkle (HxW uint8 alpha) or None
write_guides(...)        -> the guides in the same format, so they reopen in the tool or Photoshop
write_texture_psd(...)   -> a separate PSD holding the texture as a group the user drags into their document
"""
import numpy as np
from PIL import Image
from psd_tools import PSDImage
from psd_tools.api.layers import Group, PixelLayer
from psd_tools.constants import BlendMode

from .i18n import both, tr

# Names of the guides group and its layers, in Chinese (the fixture format). Written in the language of the page
# (i18n.tr), recognised in either when read.
GUIDE_GROUP = '丝袜引导'
STROKE_LAYER = '走向'
SPARKLE_LAYER = '亮点'
DIVIDER_LAYER = '隔开'      # the user's 隔开 lines (not in the original fixture format; read back by trace.py)
TEXTURE_MARK = '丝袜纹理'   # any layer whose name contains this is a previous result; leave it out of the art
ART_LAYER = '原图'


def _alpha(layer, size):
    """Full-canvas alpha of a layer as Photoshop shows it: pixel alpha x layer mask x opacity.

    psd-tools writes a layer's transparency as a layer mask, and topil() ignores masks, so a layer written by
    psd-tools reads back as fully opaque through topil(). composite(force=True) applies everything.
    """
    W, H = size
    out = np.zeros((H, W), np.uint8)
    c = layer.composite(force=True)
    if c is None:
        return out
    x0, y0 = layer.bbox[0], layer.bbox[1]
    a = np.asarray(c.getchannel('A')) if 'A' in c.getbands() else np.full((c.height, c.width), 255, np.uint8)
    out[y0:y0 + a.shape[0], x0:x0 + a.shape[1]] = a
    return out


def read_guide_layers(path):
    """Everything a guides PSD holds: {'art', 'regions', 'strokes', 'sparkle', 'dividers'} (alphas or None)."""
    psd = PSDImage.open(path)
    size = psd.size
    groups, strokes_n, sparkle_n, divider_n = both(GUIDE_GROUP), both(STROKE_LAYER), both(SPARKLE_LAYER), both(DIVIDER_LAYER)
    marks = both(TEXTURE_MARK)
    guide = next((L for L in psd if L.is_group() and L.name in groups), None)
    art = psd.composite(force=True, layer_filter=lambda L: L.is_visible() and L is not guide
                        and not any(m in L.name for m in marks))
    regions, strokes, sparkle, dividers = {}, None, None, None
    if guide is not None:
        for L in guide:
            a = _alpha(L, size)
            if L.name in strokes_n:
                strokes = a
            elif L.name in sparkle_n:
                sparkle = a
            elif L.name in divider_n:
                dividers = a
            elif L.name.startswith(tuple(strokes_n)):
                continue                                  # alternative stroke layers, e.g. a hidden example variant
            else:
                regions[L.name] = a > 0                   # coverage: the layer's display opacity is irrelevant
    return {'art': np.asarray(art.convert('RGB')), 'regions': regions, 'strokes': strokes, 'sparkle': sparkle,
            'dividers': dividers}


def read_guides(path):
    g = read_guide_layers(path)
    return g['art'], g['regions'], g['strokes'], g['sparkle']


def _named(layer, name):
    layer.name = name   # the setter stores the Unicode name; constructors' name= fails on non-Latin text when saving
    return layer


def split_factor(src_rgb, out_rgb, eps=1.0):
    """out = src * f per channel, as a Multiply layer (f <= 1) and a Color Dodge layer (f >= 1).

    Multiply: base * m / 255. Color Dodge: base / (1 - d / 255). Together they reproduce out within +-1 level.
    Pixels with src == 0 cannot be scaled; they get f = 1.
    """
    s = src_rgb.astype(np.float64)
    f = np.where(s >= eps, out_rgb.astype(np.float64) / np.maximum(s, eps), 1.0)
    mul = np.round(np.clip(np.minimum(f, 1.0), 0, 1) * 255).astype(np.uint8)
    dodge = np.round(np.clip(1 - 1 / np.maximum(f, 1.0), 0, 1) * 255).astype(np.uint8)
    return mul, dodge


def write_guides(path, art_rgb, regions, stroke_alpha, colors=None, sparkle_alpha=None, divider_alpha=None):
    """The guides in the fixture's format, so they reopen in the tool (read_guide_layers) or Photoshop.

    Layout: the art as a plain layer, then a group 丝袜引导 holding one layer per region (its colour at opacity 115,
    masked by the region), a 走向 layer (red, masked by the stroke alpha), and when given a 亮点 layer (white,
    masked by the painted sparkle alpha) and a 隔开 layer (cyan, masked by the 隔开 lines). regions:
    {name: HxW bool}; colors: {name: '#rrggbb'}.
    """
    H, W = art_rgb.shape[:2]
    doc = PSDImage.new('RGB', (W, H))
    _named(PixelLayer.frompil(Image.fromarray(art_rgb), doc, 'art'), tr(ART_LAYER))
    g = _named(Group.new(doc, name='g'), tr(GUIDE_GROUP))
    g.blend_mode = BlendMode.PASS_THROUGH
    for name, mask in regions.items():
        hexc = (colors or {}).get(name, '#ffc400').lstrip('#')
        rgb = tuple(int(hexc[i:i + 2], 16) for i in (0, 2, 4))
        L = _named(PixelLayer.frompil(Image.new('RGB', (W, H), rgb), g, 'r'), name)
        L.opacity = 115
        L.create_mask(Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), 'L'))
    S = _named(PixelLayer.frompil(Image.new('RGB', (W, H), (255, 0, 0)), g, 's'), tr(STROKE_LAYER))
    S.create_mask(Image.fromarray(np.asarray(stroke_alpha, np.uint8), 'L'))
    for name, alpha, rgb in ((SPARKLE_LAYER, sparkle_alpha, (255, 255, 255)), (DIVIDER_LAYER, divider_alpha, (0, 229, 255))):
        if alpha is not None:
            L = _named(PixelLayer.frompil(Image.new('RGB', (W, H), rgb), g, 'x'), tr(name))
            L.create_mask(Image.fromarray(np.asarray(alpha, np.uint8), 'L'))
    doc.save(path)
    return path


def write_texture_psd(path, art_rgb, out_rgb, coverage, name=TEXTURE_MARK):
    """A PSD with the art (for reference, hidden) and a group [Multiply, Color Dodge], each layer masked by `coverage`.

    The group depends only on the ratio out/src, so it stays valid when the user later edits the art beneath it.
    coverage: HxW uint8 0..255, where the texture may show; the user refines it in Photoshop.
    psd-tools 1.24 writes a corrupt file for a mask on a group, so each layer carries its own copy. Layers are built
    from RGB (not RGBA): psd-tools stores RGBA transparency as a layer mask, which blocks create_mask.
    """
    H, W = art_rgb.shape[:2]
    mul, dodge = split_factor(art_rgb, out_rgb)
    cov = Image.fromarray(coverage, 'L')
    doc = PSDImage.new('RGB', (W, H))
    ref = _named(PixelLayer.frompil(Image.fromarray(art_rgb), doc, 'art'), '原图（参考）')
    ref.visible = False
    g = _named(Group.new(doc, name='g'), name)
    g.blend_mode = BlendMode.PASS_THROUGH   # Group.new defaults to Normal, which isolates the blends from the art
    lm = _named(PixelLayer.frompil(Image.fromarray(mul), g, 'm'), '暗部 正片叠底')
    lm.blend_mode = BlendMode.MULTIPLY
    lm.create_mask(cov)
    ld = _named(PixelLayer.frompil(Image.fromarray(dodge), g, 'd'), '亮部 颜色减淡')
    ld.blend_mode = BlendMode.COLOR_DODGE
    ld.create_mask(cov)
    doc.save(path)
    return path

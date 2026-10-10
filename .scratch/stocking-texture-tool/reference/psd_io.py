"""PSD in and out for the stocking texture tool (psd-tools >= 1.24). Verified behaviour is in ../spec.md.

read_guides(path)        -> art (HxWx3 RGB uint8), regions {name: bool mask}, strokes (HxW uint8 alpha) or None
write_texture_psd(...)   -> a separate PSD holding the texture as a group the user drags into their document
"""
import numpy as np
from PIL import Image
from psd_tools import PSDImage
from psd_tools.api.layers import Group, PixelLayer
from psd_tools.constants import BlendMode

GUIDE_GROUP = '丝袜引导'
STROKE_LAYER = '走向'
SPARKLE_LAYER = '亮点'
TEXTURE_MARK = '丝袜纹理'   # any layer whose name contains this is a previous result; leave it out of the art


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


def read_guides(path):
    psd = PSDImage.open(path)
    size = psd.size
    guide = next((L for L in psd if L.is_group() and L.name == GUIDE_GROUP), None)
    art = psd.composite(force=True, layer_filter=lambda L: L.is_visible() and L is not guide and TEXTURE_MARK not in L.name)
    regions, strokes, sparkle = {}, None, None
    if guide is not None:
        for L in guide:
            a = _alpha(L, size)
            if L.name == STROKE_LAYER:
                strokes = a
            elif L.name == SPARKLE_LAYER:
                sparkle = a
            elif L.name.startswith(STROKE_LAYER):
                continue                                  # alternative stroke layers, e.g. a hidden example variant
            else:
                regions[L.name] = a > 0                   # coverage: the layer's display opacity is irrelevant
    return np.asarray(art.convert('RGB')), regions, strokes, sparkle


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

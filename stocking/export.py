"""Export: one file per export, of the kind the user picks, to the file the user names in a save dialog. The
user's own file is never written.

  png     <name>-丝袜成品.png   the finished picture (成品图)
  cutout  <name>-仅丝袜.png     the stockings alone, everything else transparent: laid over the art it gives the
                               finished picture
  guides  <name>-丝袜引导.psd   the guides (regions, 走向, 亮点, 隔开), which reopen in the tool or Photoshop

Those are the names the dialog suggests, numbered ' (2)', ' (3)' … past any file already there, so exporting a
second variant never takes the first one's place unless the user picks that file. The names follow the page's
language (English: -finished.png, -stockings-only.png, -stocking-guides.psd); either language's suffix is stripped
from a source that is one of our exports.

Each file is written beside its final name and then moved over it, so a failure (a file open in another program,
a full disk) never leaves a half-written file behind, and an earlier export stays intact.
"""
import os
import time

import cv2
import numpy as np

from . import knit, psd_io
from .i18n import both, tr

KINDS = ('png', 'cutout', 'guides')
NAMES = {'png': '丝袜成品.png', 'cutout': '仅丝袜.png', 'guides': '丝袜引导.psd'}   # in Chinese; written via tr()
EXTS = {k: os.path.splitext(n)[1] for k, n in NAMES.items()}
EARLIER = (psd_io.TEXTURE_MARK,)                                    # 丝袜纹理: what earlier exports were named


def base_name(filename):
    """The source's name without extension, and without our own suffix when the source is one of our exports, so
    re-exporting from x-丝袜引导.psd gives x-丝袜成品.png rather than x-丝袜引导-丝袜成品.png."""
    stem = os.path.splitext(os.path.basename(filename))[0]
    for suffix in [os.path.splitext(n)[0] for k in NAMES.values() for n in both(k)] + list(EARLIER):
        if stem.endswith(f'-{suffix}') and len(stem) > len(suffix) + 1:
            return stem[:-len(suffix) - 1]
    return stem


def _same(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def suggest(folder, filename, kind, source=None):
    """The file the save dialog offers for an export of `kind` in `folder`: <name>-<kind's name>, numbered ' (2)',
    ' (3)' … past any file already there (an earlier export) and past the source."""
    p = os.path.join(folder, f'{base_name(filename)}-{tr(NAMES[kind])}')
    stem, ext = os.path.splitext(p)
    i = 2
    while os.path.exists(p) or (source and _same(p, source)):
        p = f'{stem} ({i}){ext}'
        i += 1
    return p


def destination(path, kind, source=None):
    """The file an export of `kind` the user named `path` is written to: `path`, with the kind's extension added
    when it has another. Raises ValueError with a message for the user when its folder is missing or it is the
    source."""
    if kind not in KINDS:
        raise ValueError(tr('不认识的导出内容：{kind}', kind=kind))
    p = os.path.abspath(path)
    if os.path.splitext(p)[1].lower() != EXTS[kind]:
        p += EXTS[kind]
    folder = os.path.dirname(p)
    if not os.path.isdir(folder):
        raise ValueError(tr('文件夹不存在：{folder}', folder=folder))
    if source and _same(p, source):
        raise ValueError(tr('“{file}”是正在编辑的原文件，不能覆盖它；换一个文件名', file=os.path.basename(p)))
    return p


def _drop(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _replace(final, write):
    stem, ext = os.path.splitext(final)
    tmp = f'{stem}.导出中{ext}'
    try:
        write(tmp)
    except PermissionError as e:
        _drop(tmp)
        raise ValueError(tr('不能在这个文件夹里写文件：{folder}（{why}）', folder=os.path.dirname(final), why=e.strerror)) from e
    except BaseException:
        _drop(tmp)
        raise
    try:
        os.replace(tmp, final)
    except PermissionError as e:
        _drop(tmp)
        raise ValueError(tr('“{file}”正被别的程序占用（比如在 Photoshop 里开着），关掉它再导出',
                            file=os.path.basename(final))) from e


def stocking_layer(art_rgb, out_rgb, alpha):
    """RGBA uint8 of the stockings alone. Opacity is their soft coverage, raised wherever the render changed a pixel
    beyond it (a sparkle's glow) just as far as the change needs, and the colour is what, at that opacity over the
    art, gives the finished picture; so the layer laid over the art composites to it (to rounding), and everything
    else is transparent (and black: nothing of the rest of the picture is kept)."""
    art, out = art_rgb.astype(np.float64), out_rgb.astype(np.float64)
    d = out - art
    # the least opacity that explains the change with a colour in 0..255
    need = np.where(d > 0, d / np.maximum(255 - art, 1e-9), np.where(d < 0, -d / np.maximum(art, 1e-9), 0)).max(2)
    a8 = np.ceil(np.clip(np.maximum(np.clip(alpha, 0, 1), need), 0, 1) * 255 - 1e-6)
    a = a8 / 255
    rgb = np.where(a[..., None] > 0, art + d / np.maximum(a, 1e-9)[..., None], 0)
    return np.dstack([np.clip(np.round(rgb), 0, 255), a8]).astype(np.uint8)


def export(doc, scene, params, path, kind='png'):
    """Write one file of `kind` (KINDS) to `path` (see destination), replacing any file there. png and cutout render
    with `params` (look.clean_params) on `scene`; guides need neither. Returns {'file', 'seconds', 'sparkles_ready'}.
    Raises ValueError with a message for the user."""
    t0 = time.perf_counter()
    path = destination(path, kind, source=doc.path)
    ready = True
    if kind == 'guides':
        with doc.lock:
            regions = {r.name: r.mask.copy() for r in doc.regions}
            colors = {r.name: r.color for r in doc.regions}
            sparkle = doc.sparkle
        strokes, dividers = doc.stroke_alpha(), doc.divider_alpha()
        _replace(path, lambda p: psd_io.write_guides(p, doc.art, regions, strokes, colors, sparkle, dividers))
    else:
        out_bgr, info = scene.render(params)
        ready = info['sparkles_ready']
        if kind == 'png':
            _replace(path, lambda p: knit.write(p, out_bgr))
        else:
            layer = stocking_layer(doc.art, cv2.cvtColor(out_bgr, cv2.COLOR_BGR2RGB), doc.coverage()[1])
            _replace(path, lambda p: knit.write(p, cv2.cvtColor(layer, cv2.COLOR_RGBA2BGRA)))
    return {'file': path, 'seconds': round(time.perf_counter() - t0, 2), 'sparkles_ready': ready}

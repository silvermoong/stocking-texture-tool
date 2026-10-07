"""Click-to-segment with Segment Anything (ViT-B). One model per process, one image embedding per document.

The model loads in a background thread at startup (importing torch alone takes seconds); documents are embedded
in the background as soon as they open, so the first click is fast.
"""
import os
import threading
import time

import numpy as np

from .i18n import tr

CHECKPOINT = 'sam_vit_b_01ec64.pth'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def checkpoint_path():
    from . import settings
    for p in (settings.get('sam_checkpoint'), os.path.join(ROOT, 'models', CHECKPOINT),
              os.path.join(os.path.expanduser('~'), 'Downloads', CHECKPOINT)):
        if p and os.path.isfile(p):
            return p
    return None


def _runs_on(arches, major, minor):
    """Whether a torch build with kernels for `arches` (['sm_86', 'sm_120', ...]) runs on a device of this compute
    capability: a kernel built for sm_XY runs on any device of the same X with a minor version of Y or more (the
    RTX 4090, sm_89, runs the sm_86 kernels)."""
    for a in arches:
        if a.startswith('sm_') and a[3:].isdigit():
            n = int(a[3:])
            if n // 10 == major and n % 10 <= minor:
                return True
    return False


def pick_device(torch):
    """The CUDA device with the most memory among those this torch build has kernels for; else the CPU."""
    if not torch.cuda.is_available():
        return 'cpu', 'CPU'
    arches = torch.cuda.get_arch_list()
    best = None
    for i in range(torch.cuda.device_count()):
        if not _runs_on(arches, *torch.cuda.get_device_capability(i)):
            continue
        mem = torch.cuda.get_device_properties(i).total_memory
        if best is None or mem > best[0]:
            best = (mem, i)
    if best is None:
        return 'cpu', 'CPU'
    return f'cuda:{best[1]}', torch.cuda.get_device_name(best[1])


class SamService:
    def __init__(self):
        self.status = 'idle'        # idle, loading, ready, unavailable
        self.error = None
        self.device_name = None
        self.on_change = None
        self._predictor = None
        self._torch = None
        self._current = None        # document whose embedding is loaded in the predictor
        self._lock = threading.Lock()
        self._ready = threading.Event()

    def _changed(self):
        cb = self.on_change
        if cb is not None:
            cb()

    def start(self):
        if self.status != 'idle':
            return
        self.status = 'loading'
        threading.Thread(target=self._load, name='sam-load', daemon=True).start()

    def _load(self):
        try:
            ck = checkpoint_path()
            if ck is None:
                raise RuntimeError(tr('找不到 SAM 模型文件 {path}，请重新运行 install.bat', path=CHECKPOINT))
            import torch
            from segment_anything import SamPredictor, sam_model_registry
            dev, name = pick_device(torch)
            t = time.perf_counter()
            sam = sam_model_registry['vit_b'](checkpoint=ck).to(dev).eval()
            self._torch, self._predictor, self.device_name = torch, SamPredictor(sam), name
            self.status = 'ready'
            print(f'SAM ViT-B on {name} ({dev}), loaded in {time.perf_counter() - t:.1f}s', flush=True)
        except Exception as e:
            self.status, self.error = 'unavailable', str(e)
            print(f'SAM unavailable: {e}', flush=True)
        finally:
            self._ready.set()
            self._changed()

    def wait_ready(self, timeout=120):
        self.start()
        self._ready.wait(timeout)
        if self.status != 'ready':
            raise RuntimeError(self.error or tr('点选模型还没加载好'))

    # ------------------------------------------------------------- embeddings

    def embed_async(self, doc):
        """Embed a freshly opened document in the background."""
        def run():
            try:
                self.ensure_embedded(doc)
            except Exception as e:
                doc.sam_state, doc.sam_error = 'error', str(e)
            self._changed()
        threading.Thread(target=run, name=f'sam-embed-{doc.id}', daemon=True).start()

    def ensure_embedded(self, doc):
        self.wait_ready()
        with self._lock:
            self._activate(doc)

    def _activate(self, doc):
        p = self._predictor
        if self._current is doc and p.is_image_set:
            return
        emb = getattr(doc, 'sam_embedding', None)
        if emb is None:
            doc.sam_state = 'embedding'
            self._changed()
            t = time.perf_counter()
            with self._torch.inference_mode():
                p.set_image(doc.art)        # RGB uint8 HxWx3
            emb = (p.features, p.original_size, p.input_size)
            doc.sam_embedding = emb
            # the first prediction after loading pays a one-off ~0.5 s warm-up; pay it here, not on a click
            p.predict(point_coords=np.array([[doc.w / 2, doc.h / 2]], np.float32), point_labels=np.array([1]))
            doc.sam_state = 'ready'
            print(f'SAM embedding {doc.w}x{doc.h}: {time.perf_counter() - t:.2f}s', flush=True)
        else:
            p.features, p.original_size, p.input_size = emb
            p.is_image_set = True
        self._current = doc

    def forget(self, doc):
        with self._lock:
            if self._current is doc:
                self._predictor.reset_image()
                self._current = None
            doc.sam_embedding = None

    # ------------------------------------------------------------- clicks

    def candidates(self, doc, x, y):
        """The three nested segments SAM proposes for a click at image px (x, y), smallest first, with the index
        of the one SAM rates best. Masks are full-size bool arrays."""
        self.wait_ready()
        with self._lock:
            self._activate(doc)
            with self._torch.inference_mode():
                masks, scores, _ = self._predictor.predict(point_coords=np.array([[x, y]], np.float32),
                                                           point_labels=np.array([1]), multimask_output=True)
        order = np.argsort([m.sum() for m in masks], kind='stable')
        masks, scores = [masks[i] for i in order], [float(scores[i]) for i in order]
        return masks, int(np.argmax(scores)), scores


service = SamService()

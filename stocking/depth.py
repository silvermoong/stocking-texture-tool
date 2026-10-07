"""Monocular depth (Depth Anything V2 Small) for the walls and the sparkle map: where one stretch of stocking lies in
front of another, and where the fabric bulges toward the viewer.

Small, not Large: on the fixtures and the user's pictures both find the same walls and give sparkle weights that
correlate 0.97-0.99, while Small is a 99 MB download instead of 1.3 GB, runs in 2 s on a CPU instead of 12 s, and is
Apache-2.0 (Base and Large are CC BY-NC 4.0, non-commercial).

One model per process, loaded in the background on first use; each document's disparity is computed once and kept.
"""
import os
import threading
import time

import cv2
import numpy as np

from .i18n import tr

MODEL = 'depth-anything/Depth-Anything-V2-Small-hf'
# install.bat puts the model here; without it the Hugging Face cache is used (and filled from the internet if need be)
LOCAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'models', MODEL.split('/')[-1])
SHORT_SIDE = 1036           # input size on the short side (a multiple of 14, as the model wants)

os.environ.setdefault('USE_TF', '0')        # a broken TensorFlow elsewhere must not be imported by transformers


class DepthService:
    def __init__(self):
        self.status = 'idle'        # idle, loading, ready, unavailable
        self.error = None
        self.on_change = None
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._torch = self._model = self._proc = self._dev = None

    def _changed(self):
        cb = self.on_change
        if cb is not None:
            cb()

    def start(self):
        if self.status != 'idle':
            return
        self.status = 'loading'
        self._changed()
        threading.Thread(target=self._load, name='depth-load', daemon=True).start()

    def _load(self):
        try:
            import torch
            from transformers import AutoImageProcessor, AutoModelForDepthEstimation
            from .sam import pick_device
            dev, name = pick_device(torch)
            dtype = torch.float16 if dev.startswith('cuda') else torch.float32
            t = time.perf_counter()
            src = LOCAL if os.path.isfile(os.path.join(LOCAL, 'config.json')) else MODEL
            try:
                proc = AutoImageProcessor.from_pretrained(src, local_files_only=True)
                model = AutoModelForDepthEstimation.from_pretrained(src, dtype=dtype, local_files_only=True)
            except OSError:
                proc = AutoImageProcessor.from_pretrained(MODEL)
                model = AutoModelForDepthEstimation.from_pretrained(MODEL, dtype=dtype)
            self._model = model.to(dev).eval()
            self._torch, self._proc, self._dev, self._dtype = torch, proc, dev, dtype
            self.status = 'ready'
            print(f'depth model on {name}, loaded in {time.perf_counter() - t:.1f}s', flush=True)
        except Exception as e:
            self.status, self.error = 'unavailable', str(e)
            print(f'depth model unavailable: {e}', flush=True)
        finally:
            self._ready.set()
            self._changed()

    def disparity(self, doc, timeout=180):
        """Relative inverse depth at full resolution (float32, larger = nearer), computed once per document."""
        d = getattr(doc, 'disparity', None)
        if d is not None:
            return d
        self.start()
        self._ready.wait(timeout)
        if self.status != 'ready':
            raise RuntimeError(self.error or tr('深度模型还没加载好'))
        with self._lock:
            d = getattr(doc, 'disparity', None)
            if d is not None:
                return d
            torch = self._torch
            t = time.perf_counter()
            inp = self._proc(images=np.array(doc.art), return_tensors='pt',
                             size={'height': SHORT_SIDE, 'width': SHORT_SIDE}, keep_aspect_ratio=True,
                             ensure_multiple_of=14)
            with torch.inference_mode():
                pred = self._model(pixel_values=inp['pixel_values'].to(self._dev, self._dtype)).predicted_depth
            pred = pred[0].float().cpu().numpy()
            d = cv2.resize(pred, (doc.w, doc.h), interpolation=cv2.INTER_CUBIC).astype(np.float32)
            doc.disparity = d
            print(f'depth {doc.w}x{doc.h} via {pred.shape[1]}x{pred.shape[0]}: {time.perf_counter() - t:.2f}s',
                  flush=True)
            return d

    def disparity_async(self, doc):
        def run():
            try:
                self.disparity(doc)
            except Exception as e:
                doc.depth_error = str(e)
            self._changed()
        threading.Thread(target=run, name='depth-run', daemon=True).start()


service = DepthService()

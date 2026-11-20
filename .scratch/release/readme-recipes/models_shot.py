"""Development only: the tool as an --isolated server that takes its models from a folder named here, for retaking the
README pictures in a worktree, which has no models/ of its own (install.bat puts them in the main checkout).

    python .scratch\\release\\readme-recipes\\models_shot.py <models folder> <port>

Run it from the root of the checkout whose code is to be shown. <models folder> holds sam_vit_b_01ec64.pth and
Depth-Anything-V2-Small-hf, as D:\\Stocking\\models does. Nothing of the tool's own code is changed: 点选's
checkpoint is the sam_checkpoint setting, written into the isolated server's own empty settings, and the depth model's
folder is the one depth.py looks in first. The files the tool keeps while it runs (its log, the note of which server
is the shared one) go to a temporary folder of this run, never to the user's.
"""
import os
import sys
import tempfile

models, port = os.path.abspath(sys.argv[1]), sys.argv[2]
sys.path.insert(0, os.getcwd())
import stocking.__main__ as launcher  # noqa: E402
from stocking import depth, sam, settings  # noqa: E402

checkpoint = os.path.join(models, sam.CHECKPOINT)
depth_folder = os.path.join(models, os.path.basename(depth.LOCAL))
# every file of the depth model: with one missing, depth.py would go on to the Hugging Face cache or the internet
for need in [checkpoint] + [os.path.join(depth_folder, f)
                            for f in ('config.json', 'preprocessor_config.json', 'model.safetensors')]:
    if not os.path.isfile(need):
        sys.exit(f'not there: {need}')
depth.LOCAL = depth_folder

settings.DIR = tempfile.mkdtemp(prefix='stocking-shot-')
launcher.RUNFILE = os.path.join(settings.DIR, 'server.json')
_isolate = settings.isolate


def isolate():
    """--isolated starts from empty settings of its own: the checkpoint goes into those, not into the user's."""
    _isolate()
    settings.update(sam_checkpoint=checkpoint)


settings.isolate = isolate
sys.argv = ['stocking', '--port', port, '--no-window', '--stay', '--isolated']
launcher.main()

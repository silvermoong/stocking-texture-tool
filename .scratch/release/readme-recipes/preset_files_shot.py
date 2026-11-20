"""Development only: the tool with the preset file dialogs answered from a folder, for the README pictures. 导出… writes
<folder>\\<suggested name>; 导入… reads the first .json in <folder>.

    python .scratch\\release\\readme-recipes\\preset_files_shot.py <folder> <file to open> <port> [<models folder> [<folder shown>]]

Run it from the root of the checkout whose code is to be shown. <models folder> holds sam_vit_b_01ec64.pth and
Depth-Anything-V2-Small-hf, for a worktree that has no models/ of its own (see models_shot.py). With <folder shown>
(D:\\预设, D:\\presets) the status line names the exported preset file in that folder, as the README's pictures and
captions do, while the file itself is written into <folder>: nothing is made outside it, and <folder shown> need not
exist. The path in such a picture is for show only. Only a preset's export is answered so; an image or a PSD exported
from this server goes where it is told. The files the tool keeps while it runs go to a temporary folder of this run,
never to the user's.
"""
import glob
import os
import sys
import tempfile

args = sys.argv[1:]
root, first, port = args[0], args[1], args[2]
models = os.path.abspath(args[3]) if len(args) > 3 else None
shown = os.path.normpath(args[4]) if len(args) > 4 else None
sys.path.insert(0, os.getcwd())
import stocking.__main__ as launcher  # noqa: E402
from stocking import depth, sam, server, settings  # noqa: E402

if models:
    checkpoint = os.path.join(models, sam.CHECKPOINT)
    depth_folder = os.path.join(models, os.path.basename(depth.LOCAL))
    # every file of the depth model: with one missing, depth.py would go on to the Hugging Face cache or the internet
    for need in [checkpoint] + [os.path.join(depth_folder, f)
                                for f in ('config.json', 'preprocessor_config.json', 'model.safetensors')]:
        if not os.path.isfile(need):
            sys.exit(f'not there: {need}')
    depth.LOCAL = depth_folder
    _isolate = settings.isolate

    def isolate():
        """--isolated starts from empty settings of its own: the checkpoint goes into those, not into the user's."""
        _isolate()
        settings.update(sam_checkpoint=checkpoint)

    settings.isolate = isolate

os.makedirs(root, exist_ok=True)
settings.DIR = tempfile.mkdtemp(prefix='stocking-shot-')
launcher.RUNFILE = os.path.join(settings.DIR, 'server.json')

if shown:
    # The server checks that the folder of the file it was named is there, then writes the file (export_preset). From
    # the moment 导出… names a preset file in the folder shown until that file is written, the folder counts as there
    # and the file goes into <folder>; at any other time, and for any other file, nothing is answered differently.
    _isdir, _replace = os.path.isdir, server.export._replace
    pending = []

    def ask_save(suggested):
        pending[:] = [os.path.join(shown, os.path.basename(suggested))]
        return pending[0]

    def isdir(p):
        return bool(pending) and isinstance(p, str) and os.path.normpath(p) == shown or _isdir(p)

    def replace(final, write):
        if pending and final == pending[0]:
            del pending[:]
            final = os.path.join(root, os.path.basename(final))
        return _replace(final, write)

    os.path.isdir = isdir
    server.export._replace = replace
    server._ask_preset_save = ask_save
else:
    server._ask_preset_save = lambda suggested: os.path.join(root, os.path.basename(suggested))
server._ask_preset_open = lambda: next(iter(sorted(glob.glob(os.path.join(root, '*.json')))), None)
sys.argv = ['stocking', first, '--port', port, '--no-window', '--stay', '--isolated']
launcher.main()

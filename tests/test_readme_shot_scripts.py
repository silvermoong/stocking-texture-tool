"""The two launchers used to retake the README pictures (.scratch/release/readme-recipes/models_shot.py and
preset_files_shot.py) start the tool with a few of its parts answered from folders. Each is run here in a process of
its own with the tool's main() replaced by nothing, and what it left set up is looked at: nothing of the user's is
pointed at, and only the preset files are answered from the folder.

GitHub's code ZIPs leave .scratch out (.gitattributes): without the launchers there is nothing to check."""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDER = os.path.join(ROOT, '.scratch', 'release', 'readme-recipes')
MODELS_SHOT = os.path.join(FOLDER, 'models_shot.py')
PRESET_SHOT = os.path.join(FOLDER, 'preset_files_shot.py')
pytestmark = pytest.mark.skipif(not os.path.isfile(MODELS_SHOT), reason='the launchers are not in this copy (a code ZIP)')

_CHILD = '''
import json, os, runpy, sys
import stocking.__main__ as launcher
from stocking import depth, export, server, settings
launcher.main = lambda: None
script, argv, probe = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3]
sys.argv = [script] + argv
runpy.run_path(script, run_name='__main__')
out = {}
exec(probe)
print('PROBE' + json.dumps(out))
'''


def run(tmp_path, script, argv, probe='pass'):
    """Run a launcher with these arguments, then `probe` (Python that fills `out`). Returns (exit code, out, text)."""
    user = tmp_path / 'user'
    temp = tmp_path / 'temp'
    for d in (user, temp):
        d.mkdir(exist_ok=True)
    env = dict(os.environ, LOCALAPPDATA=str(user), TEMP=str(temp), TMP=str(temp), PYTHONUTF8='1',
               PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=ROOT)
    r = subprocess.run([sys.executable, '-c', _CHILD, script, json.dumps(argv), probe], cwd=ROOT, env=env,
                       capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
    text = r.stdout + r.stderr
    line = next((x for x in r.stdout.splitlines() if x.startswith('PROBE')), None)
    return r.returncode, json.loads(line[5:]) if line else None, text


def models(tmp_path, leave_out=()):
    """A folder laid out as the tool's models/ is, with empty files."""
    folder = tmp_path / 'models'
    (folder / 'Depth-Anything-V2-Small-hf').mkdir(parents=True)
    for name in ('sam_vit_b_01ec64.pth', 'Depth-Anything-V2-Small-hf/config.json',
                 'Depth-Anything-V2-Small-hf/preprocessor_config.json', 'Depth-Anything-V2-Small-hf/model.safetensors'):
        if name not in leave_out:
            (folder / name).write_bytes(b'')
    return str(folder)


_WHERE = "out.update(dir=settings.DIR, runfile=launcher.RUNFILE, depth=depth.LOCAL)"


def test_models_launcher_points_at_nothing_of_the_users(tmp_path):
    code, out, text = run(tmp_path, MODELS_SHOT, [models(tmp_path), '8790'], _WHERE)
    assert code == 0, text
    user = str(tmp_path / 'user')
    assert not out['dir'].startswith(user) and not out['runfile'].startswith(user), out
    assert out['depth'] == os.path.join(str(tmp_path / 'models'), 'Depth-Anything-V2-Small-hf')


def test_preset_launcher_points_at_nothing_of_the_users(tmp_path):
    code, out, text = run(tmp_path, PRESET_SHOT, [str(tmp_path / 'files'), 'x.png', '8790'], _WHERE)
    assert code == 0, text
    user = str(tmp_path / 'user')
    assert not out['dir'].startswith(user) and not out['runfile'].startswith(user), out


@pytest.mark.parametrize('gone', ['Depth-Anything-V2-Small-hf/preprocessor_config.json',
                                  'Depth-Anything-V2-Small-hf/model.safetensors', 'sam_vit_b_01ec64.pth'])
@pytest.mark.parametrize('script', [MODELS_SHOT, PRESET_SHOT], ids=['models', 'presets'])
def test_a_model_file_that_is_not_there_stops_the_launcher(tmp_path, script, gone):
    folder = models(tmp_path, leave_out=(gone,))
    argv = [folder, '8790'] if script == MODELS_SHOT else [str(tmp_path / 'files'), 'x.png', '8790', folder]
    code, out, text = run(tmp_path, script, argv)
    assert code != 0 and out is None, text
    assert os.path.basename(gone) in text


def test_three_arguments_name_the_file_as_the_folder_was_given(tmp_path):
    probe = "out.update(save=server._ask_preset_save(os.path.join('elsewhere', 'a.json')))"
    code, out, text = run(tmp_path, PRESET_SHOT, [os.path.join('out', 'never-made-by-tests', 'presets'), 'x.png', '8790'],
                          probe)
    try:
        assert code == 0, text
        assert out['save'] == os.path.join('out', 'never-made-by-tests', 'presets', 'a.json')
    finally:        # the launcher makes its folder: out/ is ignored by git, and this one is taken away again
        made = os.path.join(ROOT, 'out', 'never-made-by-tests')
        if os.path.isdir(os.path.join(made, 'presets')):
            os.rmdir(os.path.join(made, 'presets'))
            os.rmdir(made)


_SHOWN = '''
def write(tmp):
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('{}')

root, shown = argv[0], argv[4]             # as they were given: the launcher has put the tool's own arguments in sys.argv
out['before'] = os.path.isdir(shown)
try:                                        # an image exported to the folder shown: not a preset, not answered
    export._replace(os.path.join(shown, 'picture.png'), write)
except OSError:
    pass
out['picture'] = os.path.isfile(os.path.join(root, 'picture.png'))
p = server._ask_preset_save(os.path.join('elsewhere', 'a.json'))
out['save'] = p
out['during'] = os.path.isdir(os.path.dirname(p))
export._replace(p, write)
out['preset'] = os.path.isfile(os.path.join(root, 'a.json'))
out['after'] = os.path.isdir(shown)
out['open'] = server._ask_preset_open()
'''


def test_the_folder_shown_answers_preset_files_only(tmp_path):
    root, shown = str(tmp_path / 'files'), str(tmp_path / 'shown-and-not-there')
    code, out, text = run(tmp_path, PRESET_SHOT, [root, 'x.png', '8790', models(tmp_path), shown], _SHOWN)
    assert code == 0, text
    assert out['save'] == os.path.join(shown, 'a.json')             # what the status line shows
    assert out['during'] and out['preset']                          # the preset went into the folder
    assert out['open'] == os.path.join(root, 'a.json')
    assert not out['before'] and not out['after']                   # the folder shown is not there, and is not said to be
    assert not out['picture']                                       # and nothing else is written for it
    assert not os.path.exists(shown)

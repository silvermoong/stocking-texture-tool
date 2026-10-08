"""Builds the install files package (the "deps" release): everything install.bat needs besides the code. install.bat
downloads the package from this project's GitHub release, or with -Source official (and for whatever GitHub fails to
deliver) each file from where it is published (PyPI, PyTorch, Python's builds, Meta, Hugging Face); with the package
in a folder next to it, it installs with no network at all.

    .venv\\Scripts\\python tools/make_deps.py deps-2 [--out out\\deps]

Run it from an installed checkout (install.bat done: it uses .tools\\uv.exe and the venv's Python to resolve the
wheels). It writes, in --out\\<name>:

  stt-<name>-base.zip            uv, Python, every package but PyTorch, both models
  stt-<name>-torch-cpu.zip       PyTorch for any machine
  stt-<name>-torch-cuda.zip.00N  PyTorch for NVIDIA cards, in parts under GitHub's 2 GiB limit per file

and rewrites tools/deps.json, which install.ps1 reads: every file with its size, SHA-256 and original URL, and every
release asset with its own size and SHA-256. Upload the assets to a GitHub release named <name>
(gh release create <name> out\\deps\\<name>\\*), then commit tools/deps.json.

Files are pinned: the wheels are what requirements*.txt resolve to for Windows x64 and Python 3.12 today, Python is
the build the pinned uv installs, the models are the revisions below. A wheel that PyPI serves with a different
SHA-256 than the one resolved stops the build.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = 'silvermoong/stocking-texture-tool'
UV_VERSION = '0.12.23'
PART = 1_900 * 1024 * 1024          # bytes per release asset, under GitHub's 2 GiB limit
VARIANTS = ('cpu', 'cuda')
TORCH_INDEX = {'cpu': 'cpu', 'cuda': 'cu128'}
PYPI = 'https://files.pythonhosted.org/'
PYTORCH = 'https://download.pytorch.org/whl/'
MODELS = [                           # path in the package, original URL
    ('models/sam_vit_b_01ec64.pth', 'https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth'),
] + [
    (f'models/Depth-Anything-V2-Small-hf/{f}',
     f'https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf/resolve/5426e4f0f36572d16453bbda7a8389317b1bef99/{f}')
    for f in ('config.json', 'preprocessor_config.json', 'model.safetensors')
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def fetch(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print(f'  {os.path.basename(dest)}', flush=True)
    req = urllib.request.Request(url, headers={'User-Agent': 'stocking-texture-tool make_deps'})   # some hosts
    with urllib.request.urlopen(req, timeout=120) as r, open(dest + '.part', 'wb') as f:          # refuse urllib's
        shutil.copyfileobj(r, f, 1 << 20)
    os.replace(dest + '.part', dest)


def pypi_path(filename):
    """The packages/... path PyPI serves a wheel at, and its SHA-256."""
    name, version = filename.split('-')[:2]
    with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json', timeout=60) as r:
        info = json.load(r)
    for u in info['urls']:
        if u['filename'] == filename:
            return urllib.parse.urlparse(u['url']).path.lstrip('/'), u['digests']['sha256']
    raise SystemExit(f'{filename} is not on PyPI')


def wheels(py, variant, dest):
    reqs = ['-r', os.path.join(ROOT, 'requirements.txt'), '-r', os.path.join(ROOT, f'requirements-torch-{variant}.txt')]
    subprocess.run([py, '-m', 'pip', 'download', '-q', '--only-binary=:all:', '--platform', 'win_amd64',
                    '--python-version', '3.12', '--implementation', 'cp', '--dest', dest] + reqs, check=True)
    return sorted(f for f in os.listdir(dest) if f.endswith('.whl'))


def python_build(uv):
    env = dict(os.environ, UV_PYTHON_INSTALL_DIR=tempfile.mkdtemp())
    out = subprocess.run([uv, 'python', 'list', '3.12', '--only-downloads', '--output-format', 'json'],
                         check=True, capture_output=True, text=True, env=env).stdout
    for d in json.loads(out):
        if d['os'] == 'windows' and d['arch'] == 'x86_64' and d['implementation'] == 'cpython' \
                and d['variant'] == 'default':
            return d['version'], d['url']           # newest first
    raise SystemExit('uv lists no Python 3.12 for Windows x64')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('name', help='release name, e.g. deps-2')
    ap.add_argument('--out', default=os.path.join(ROOT, 'out', 'deps'))
    a = ap.parse_args()
    py = os.path.join(ROOT, '.venv', 'Scripts', 'python.exe')
    uv = os.path.join(ROOT, '.tools', 'uv.exe')
    out = os.path.join(a.out, a.name)
    stage = os.path.join(out, 'files')
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(stage)
    if subprocess.run([py, '-m', 'pip', '--version'], capture_output=True).returncode:
        subprocess.run([uv, 'pip', 'install', '--python', py, 'pip'], check=True)

    files = []                                   # (path in package, group, original URL)
    print('uv', flush=True)
    uv_whl = f'uv-{UV_VERSION}-py3-none-win_amd64.whl'
    src, digest = pypi_path(uv_whl)
    fetch(PYPI + src, os.path.join(stage, 'uv', uv_whl))
    if sha256(os.path.join(stage, 'uv', uv_whl)) != digest:
        raise SystemExit(f'{uv_whl}: SHA-256 differs from PyPI')
    files.append((f'uv/{uv_whl}', 'base', PYPI + src))

    print('Python', flush=True)
    version, url = python_build(uv)
    m = re.search(r'/download/([^/]+)/([^/]+)$', url)     # laid out as uv's download mirror: <release>/<file>
    tag, name = m.group(1), urllib.parse.unquote(m.group(2))
    fetch(url, os.path.join(stage, 'python', tag, name))
    files.append((f'python/{tag}/{name}', 'base', url))

    print('wheels', flush=True)
    sets = {}
    with tempfile.TemporaryDirectory() as tmp:
        for v in VARIANTS:
            d = os.path.join(tmp, v)
            sets[v] = wheels(py, v, d)
        common = set(sets['cpu']) & set(sets['cuda'])
        os.makedirs(os.path.join(stage, 'wheels'), exist_ok=True)
        for v in VARIANTS:
            for f in sets[v]:
                if f in common and v == 'cuda':
                    continue
                group = 'base' if f in common else v
                shutil.copy2(os.path.join(tmp, v, f), os.path.join(stage, 'wheels', f))
                if '+' in f.split('-')[1]:              # a PyTorch build: +cpu, +cu128
                    files.append((f'wheels/{f}', group, f'{PYTORCH}{TORCH_INDEX[v]}/{urllib.parse.quote(f)}'))
                else:
                    src, digest = pypi_path(f)
                    if sha256(os.path.join(stage, 'wheels', f)) != digest:
                        raise SystemExit(f'{f}: SHA-256 differs from PyPI')
                    files.append((f'wheels/{f}', group, PYPI + src))

    print('models', flush=True)
    for path, url in MODELS:
        local = os.path.join(ROOT, *path.split('/'))
        dest = os.path.join(stage, *path.split('/'))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.isfile(local):
            shutil.copy2(local, dest)
        else:
            fetch(url, dest)
        files.append((path, 'base', url))
    sam = os.path.join(stage, 'models', 'sam_vit_b_01ec64.pth')
    if sha256(sam) != 'ec2df62732614e57411cdcf32a23ffdf28910380d03139ee0f4fcbe91eb8c912':
        raise SystemExit('the SAM checkpoint is not the published one')

    manifest = {'name': a.name, 'release': f'https://github.com/{REPO}/releases/download/{a.name}/',
                'python': version, 'uv': UV_VERSION, 'groups': {}, 'files': []}
    for path, group, url in files:
        p = os.path.join(stage, *path.split('/'))
        manifest['files'].append({'path': path, 'group': group, 'size': os.path.getsize(p), 'sha256': sha256(p),
                                  'url': url})

    print('packages', flush=True)
    for group, label in (('base', 'base'), ('cpu', 'torch-cpu'), ('cuda', 'torch-cuda')):
        name = f'stt-{a.name}-{label}.zip'
        zpath = os.path.join(out, name)
        with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_STORED, allowZip64=True) as z:
            for f in manifest['files']:
                if f['group'] == group:
                    z.write(os.path.join(stage, *f['path'].split('/')), f['path'])
        whole = {'name': name, 'size': os.path.getsize(zpath), 'sha256': sha256(zpath)}
        assets = [whole]
        if whole['size'] > PART:
            assets = []
            with open(zpath, 'rb') as src_f:
                k = 1
                while True:
                    block = src_f.read(PART)
                    if not block:
                        break
                    part = f'{name}.{k:03d}'
                    with open(os.path.join(out, part), 'wb') as dst:
                        dst.write(block)
                    assets.append({'name': part, 'size': len(block), 'sha256': hashlib.sha256(block).hexdigest()})
                    k += 1
            os.remove(zpath)
        manifest['groups'][group] = {'zip': whole, 'assets': assets}
        print(f'  {group}: {", ".join(x["name"] for x in assets)} ({whole["size"] / 2**20:,.0f} MB)', flush=True)
    shutil.rmtree(stage)
    with open(os.path.join(ROOT, 'tools', 'deps.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(manifest, f, indent=1)
        f.write('\n')
    print(f'wrote tools/deps.json and {len(os.listdir(out))} release files in {out}')


if __name__ == '__main__':
    main()

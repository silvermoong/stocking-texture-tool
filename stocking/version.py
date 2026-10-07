"""A fingerprint of the tool's code, so a launcher can tell a server running older code from a current one."""
import hashlib
import os

PKG = os.path.dirname(os.path.abspath(__file__))
EXTS = ('.py', '.js', '.html', '.css')


def code_version():
    h = hashlib.blake2b(digest_size=8)
    for root, dirs, files in os.walk(PKG):
        dirs[:] = sorted(d for d in dirs if d != '__pycache__')
        for f in sorted(files):
            if f.endswith(EXTS):
                p = os.path.join(root, f)
                h.update(os.path.relpath(p, PKG).replace(os.sep, '/').encode())
                with open(p, 'rb') as fh:
                    h.update(fh.read())
    return h.hexdigest()

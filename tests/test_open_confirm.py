"""A file handed to a tool that is already running (dragged onto the desktop shortcut or start.bat, or given on the
command line) must not replace an image whose regions and 走向 lines are not exported yet: it waits until the page has
asked, as it does for 打开… and a file dropped on the window."""
import os
import shutil
import sys

import cv2
import numpy as np
import pytest

from stocking import depth, sam, server, session, settings
from stocking.document import Document


def painted(name='first.png'):
    """A synthetic image with a painted region that no file holds."""
    d = Document(np.full((40, 60, 3), 120, np.uint8), name)
    d.paint(d.add_region('左腿'), [(20, 20)], 6)
    assert d.unsaved_guides()
    return d


@pytest.fixture
def quiet(monkeypatch, tmp_path):
    """The server with settings of its own, no models, no image and no file waiting."""
    monkeypatch.setattr(settings, '_FILE', str(tmp_path / 'settings.json'))
    monkeypatch.setattr(sam.service, 'embed_async', lambda doc: None)
    monkeypatch.setattr(depth.service, 'disparity_async', lambda doc: None)
    monkeypatch.setattr(server, '_doc', None)
    monkeypatch.setattr(server, '_pending_open', None, raising=False)
    yield
    if server._doc is not None:
        server._doc.close()


@pytest.fixture
def opened(quiet, monkeypatch):
    d = painted()
    monkeypatch.setattr(server, '_doc', d)
    yield d
    if server._doc is not d:
        d.close()


@pytest.fixture
def second(tmp_path):
    """Another synthetic image on disk, as the launcher would name it."""
    p = tmp_path / 'second.png'
    p.write_bytes(cv2.imencode('.png', np.full((30, 50, 3), 60, np.uint8))[1].tobytes())
    return str(p)


def waiting(api):
    """The file that waits, as a window reads it when it connects; None when none does."""
    r = api.get('/api/open/pending')
    assert r.status_code == 200
    return r.json()['file']


def hand_over(api, path):
    """What the launcher sends; returns the waiting file as a window reads it."""
    assert api.post('/api/open/path', json={'path': path, 'ask': True}).json()['pending'] is True
    return waiting(api)


def test_a_file_from_the_launcher_waits_while_the_guides_are_not_exported(opened, second, api):
    r = api.post('/api/open/path', json={'path': second, 'ask': True})
    assert r.status_code == 200 and r.json() == {'pending': True, 'name': 'second.png'}
    st = api.get('/api/doc').json()
    assert st['id'] == opened.id and st['name'] == 'first.png' and st['unsaved_guides'] is True


def test_a_window_that_connects_later_finds_the_waiting_file(opened, second, api):
    """The launcher opens a window after handing the file over, and no window may have been open before."""
    assert waiting(api) is None
    p = hand_over(api, second)
    assert p['path'] == os.path.abspath(second) and p['name'] == 'second.png' and p['id']


def test_cancelling_keeps_the_image_and_forgets_the_file(opened, second, api):
    p = hand_over(api, second)
    assert api.post('/api/open/pending/cancel', json={'id': p['id']}).status_code == 200
    assert waiting(api) is None
    assert api.get('/api/doc').json()['id'] == opened.id


def test_cancelling_an_older_file_leaves_the_newer_one_waiting(opened, second, api, tmp_path):
    third = str(tmp_path / 'third.png')
    shutil.copyfile(second, third)
    old = hand_over(api, second)
    new = hand_over(api, third)
    assert new['id'] != old['id']
    api.post('/api/open/pending/cancel', json={'id': old['id']})
    assert waiting(api)['name'] == 'third.png'


def test_agreeing_opens_the_file_and_nothing_waits(opened, second, api):
    p = hand_over(api, second)
    st = api.post('/api/open/pending/open', json={'id': p['id']}).json()     # what the page sends once the user agrees
    assert st['name'] == 'second.png' and st['id'] != opened.id
    assert waiting(api) is None


def test_only_the_first_answer_to_a_waiting_file_counts(opened, second, api):
    """Every window asks. A second 直接打开 must not open the file again over what was done since, and one that comes
    after 取消 in another window must not open it at all."""
    p = hand_over(api, second)
    st = api.post('/api/open/pending/open', json={'id': p['id']}).json()
    again = api.post('/api/open/pending/open', json={'id': p['id']})
    assert again.status_code == 200 and again.json() == {'settled': True}
    assert api.get('/api/doc').json()['id'] == st['id']
    server._doc.paint(server._doc.regions[0].id, [(10, 10)], 4)           # the new image has guides of its own now
    q = hand_over(api, second)
    api.post('/api/open/pending/cancel', json={'id': q['id']})
    assert api.post('/api/open/pending/open', json={'id': q['id']}).json() == {'settled': True}
    assert api.get('/api/doc').json()['id'] == st['id']


def test_opening_any_other_image_settles_the_waiting_file(opened, second, api):
    """A file dropped on the window meanwhile: the page asked for that one, the launcher's must not come up again."""
    p = hand_over(api, second)
    with open(second, 'rb') as f:
        r = api.post('/api/open/upload', files={'file': ('dropped.png', f, 'image/png')})
    assert r.json()['name'] == 'dropped.png'
    assert waiting(api) is None
    assert api.post('/api/open/pending/open', json={'id': p['id']}).json() == {'settled': True}


def test_with_nothing_to_lose_the_launchers_file_opens_at_once(opened, second, api):
    opened.mark_guides_saved()
    st = api.post('/api/open/path', json={'path': second, 'ask': True}).json()
    assert st['name'] == 'second.png' and 'pending' not in st
    assert waiting(api) is None


def test_a_missing_file_is_refused_and_does_not_wait(opened, api, tmp_path):
    r = api.post('/api/open/path', json={'path': str(tmp_path / 'gone.png'), 'ask': True})
    assert r.status_code == 400 and '文件不存在' in r.json()['detail']
    assert waiting(api) is None


def test_the_launcher_asks_when_it_hands_a_file_to_a_running_tool(monkeypatch, second):
    from stocking import __main__ as launcher
    sent = []
    monkeypatch.setattr(sys, 'argv', ['stocking', second, '--no-window'])
    monkeypatch.setattr(launcher, '_log_to_file', lambda: None)
    monkeypatch.setattr(launcher, '_read_runfile', lambda: {'port': 8765})
    monkeypatch.setattr(launcher, '_ping', lambda port: {'app': 'stocking-texture', 'version': launcher.code_version()})
    monkeypatch.setattr(launcher, '_request', lambda port, path, body=None, timeout=1.0: sent.append((port, path, body)))
    launcher.main()
    assert sent == [(8765, '/api/open/path', {'path': os.path.abspath(second), 'ask': True})]


def test_an_answer_given_for_an_image_that_is_no_longer_open_opens_nothing(opened, second, api, monkeypatch):
    """Another window opens an image of its own. From the moment that one is in place, an 直接打开 given for the old
    image must not put the waiting file over it, also before the server has forgotten the file."""
    p = hand_over(api, second)
    other = painted('other.png')
    monkeypatch.setattr(server, '_doc', other)          # the new image is in place, the waiting file not yet forgotten
    assert api.post('/api/open/pending/open', json={'id': p['id']}).json() == {'settled': True}
    assert api.get('/api/doc').json()['id'] == other.id


def test_the_other_windows_are_told_which_file_was_settled(opened, second, api, monkeypatch):
    """Events and what a window reads carry a revision, so an older one cannot hide a newer file that waits."""
    seen = []
    monkeypatch.setattr(server.bus, 'publish', seen.append)
    p = hand_over(api, second)
    api.post('/api/open/pending/cancel', json={'id': p['id']})
    asked = next(e for e in seen if e['type'] == 'open-request')
    settled = next(e for e in seen if e['type'] == 'open-settled')
    assert asked['id'] == p['id'] and asked['name'] == 'second.png'
    assert settled['id'] == p['id'] and settled['rev'] > asked['rev']
    assert api.get('/api/open/pending').json() == {'rev': settled['rev'], 'file': None}


def test_a_waiting_file_that_cannot_be_opened_is_settled_for_every_window(opened, second, api, monkeypatch):
    seen = []
    monkeypatch.setattr(server.bus, 'publish', seen.append)
    p = hand_over(api, second)
    os.remove(second)
    assert api.post('/api/open/pending/open', json={'id': p['id']}).status_code == 400
    assert any(e['type'] == 'open-settled' and e['id'] == p['id'] for e in seen)
    assert waiting(api) is None and api.get('/api/doc').json()['id'] == opened.id


@pytest.fixture
def old_session(quiet, monkeypatch, tmp_path):
    """The session a tool running older code saved as it stopped: first.png with a painted region."""
    d = painted()
    try:
        session.save(d, str(tmp_path / 'session'))
    finally:
        d.close()
    monkeypatch.setattr(server.sessions, 'dir', str(tmp_path / 'session'))
    monkeypatch.setattr(server.sessions, 'saved', None)


def test_a_file_given_while_taking_over_from_older_code_waits_for_the_image_that_was_open(old_session, second, api):
    """After an update the launcher stops the running tool (which saves its session) and starts its own server: the
    image that was open comes back first, and the file waits for the page to ask."""
    from stocking import __main__ as launcher
    launcher.open_given(second, taken_over=True)
    st = api.get('/api/doc').json()
    assert st['name'] == 'first.png' and st['unsaved_guides'] is True
    assert waiting(api)['name'] == 'second.png'


def test_after_a_takeover_other_launchers_find_the_server_only_once_the_old_image_is_back(old_session, second, api):
    """A second launcher that found the server earlier could open its file into the still empty server, and autosave
    would write that over the old session before it is read."""
    from stocking import __main__ as launcher
    at = []
    launcher.open_given(second, taken_over=True,
                        register=lambda: at.append((api.get('/api/doc').json()['name'], waiting(api)['name'])))
    assert at == [('first.png', 'second.png')]


def test_a_session_that_cannot_be_read_after_a_takeover_is_not_written_over(quiet, monkeypatch, second, api):
    from stocking import __main__ as launcher

    def locked():
        raise OSError('locked')
    monkeypatch.setattr(server.sessions, 'restore', locked)
    registered = []
    with pytest.raises(OSError):
        launcher.open_given(second, taken_over=True, register=lambda: registered.append(True))
    assert api.get('/api/doc').json() is None and waiting(api) is None      # the file was not opened
    assert registered == [True]

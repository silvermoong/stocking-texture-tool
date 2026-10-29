"""The local API answers only requests addressed to this computer by name (DNS rebinding), and takes changes only from
the tool's own page or from no page at all (the launcher): other web pages the user visits can reach 127.0.0.1 too."""
import pytest
from fastapi.testclient import TestClient

from stocking import server


@pytest.mark.parametrize('base', ['http://evil.example:8765', 'http://192.168.1.5:8765', 'http://testserver'])
def test_a_request_not_addressed_to_this_computer_by_name_is_refused(base):
    c = TestClient(server.app, base_url=base)
    assert c.get('/').status_code == 400
    r = c.get('/api/doc')
    assert r.status_code == 400 and '本机' in r.json()['detail']
    assert c.get('/api/ping').status_code == 400


@pytest.mark.parametrize('origin', ['http://evil.example', 'http://127.0.0.1:9999', 'https://127.0.0.1:8765', 'null'])
def test_a_change_sent_by_another_site_is_refused(api, origin):
    r = api.post('/api/lang', json={'lang': None}, headers={'Origin': origin})
    assert r.status_code == 403


@pytest.mark.parametrize('origin', ['http://127.0.0.1:8765', 'http://localhost:8765'])
def test_a_change_from_the_tools_own_page_goes_through(api, origin):
    # 90 is not a 界面大小: reaching the endpoint's own check (400) shows the guard let it through
    assert api.post('/api/ui-scale', json={'scale': 90}, headers={'Origin': origin}).status_code == 400


def test_a_change_without_an_origin_goes_through(api):
    assert api.post('/api/ui-scale', json={'scale': 90}).status_code == 400


@pytest.mark.parametrize('base', ['http://127.0.0.1:8765', 'http://localhost:8765'])
def test_reading_needs_no_cookie_or_header(base):
    c = TestClient(server.app, base_url=base)
    for path in ('/', '/static/app.js', '/api/doc'):
        assert c.get(path).status_code == 200, path
    assert not c.cookies


def test_the_version_ping_is_open(api):
    r = api.get('/api/ping')
    assert r.status_code == 200 and r.json()['app'] == 'stocking-texture'

"""The tests match the Chinese texts: pin the language, whatever Windows or the user's 中 / EN switch says."""
import pytest

from stocking import i18n

i18n.use('zh')


@pytest.fixture
def api():
    """A client of the server's API at the tool's own address (the server refuses 'testserver')."""
    from fastapi.testclient import TestClient

    from stocking import server
    return TestClient(server.app, base_url='http://127.0.0.1:8765')

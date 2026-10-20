"""The project picker rescans: a repo cloned after the server started shows up on reload."""

import pytest
from fastapi.testclient import TestClient

from voice_mode_proxy import server
from voice_mode_proxy.config import settings
from voice_mode_proxy.pairing import PairingStore


@pytest.fixture
def ws(tmp_path, monkeypatch):
    store = PairingStore(tmp_path / "pairing.json", tmp_path / "devices.json")
    monkeypatch.setattr(server, "auth", store)
    client = TestClient(server.app)
    token = client.post("/pair", json={"code": store.new_code(), "name": "test"}).json()["token"]
    # settings is frozen, so poke the field store directly; monkeypatch puts it back
    monkeypatch.setitem(settings.__dict__, "projects", (f"{tmp_path / 'repos'}/*",))
    (tmp_path / "repos").mkdir()
    with TestClient(server.app).websocket_connect("/ws", headers={"Authorization": f"Bearer {token}"}) as sock:
        yield sock, tmp_path / "repos"


def test_reload_picks_up_a_new_repo(ws):
    sock, repos = ws
    assert sock.receive_json()["projects"] == []  # hello, before the clone

    (repos / "docs-mcp-server" / ".git").mkdir(parents=True)
    sock.send_json({"type": "projects_reload"})
    while (ev := sock.receive_json())["type"] != "projects":
        pass
    assert [p["name"] for p in ev["projects"]] == ["docs-mcp-server"]

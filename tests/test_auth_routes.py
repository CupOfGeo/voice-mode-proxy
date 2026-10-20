"""The routes with and without a paired device. conftest.py points VMP_CONFIG at a temp file
first, so importing the server is cheap; TestClient without `with` skips the lifespan."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from voice_mode_proxy import server
from voice_mode_proxy.pairing import PairingStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = PairingStore(tmp_path / "pairing.json", tmp_path / "devices.json")
    monkeypatch.setattr(server, "auth", s)
    return s


@pytest.fixture
def client(store):
    return TestClient(server.app)


def pair(client, store, name="test"):
    r = client.post("/pair", json={"code": store.new_code(), "name": name})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_open_routes(client):
    assert client.get("/").status_code == 200
    h = client.get("/health").json()
    assert h["ok"] is True and h["protocol"] == server.PROTOCOL
    assert "session" not in h


def test_sessions_needs_a_device(client):
    r = client.get("/sessions")
    assert r.status_code == 401
    assert "not paired" in r.json()["error"]


def test_pair_wrong_code(client, store):
    store.new_code()
    r = client.post("/pair", json={"code": "000000", "name": "x"})
    assert r.status_code == 401
    assert r.json()["error"].startswith("Wrong code")
    assert store.devices() == []


def test_pair_right_code_sets_cookie_and_token(client, store):
    code = store.new_code()
    r = client.post("/pair", json={"code": code, "name": "iPhone"})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "iPhone" and len(body["token"]) >= 40
    cookie = r.headers["set-cookie"]
    assert "vmp_token=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert "Secure" not in cookie  # plain http
    assert [d.name for d in store.devices()] == ["iPhone"]
    # the client keeps the cookie jar, so the page's next requests are authenticated
    assert client.get("/sessions").status_code == 200
    assert "session" in client.get("/health").json()


def test_cookie_is_secure_over_https(store):
    https = TestClient(server.app, base_url="https://testserver")
    r = https.post("/pair", json={"code": store.new_code(), "name": "a"})
    assert "Secure" in r.headers["set-cookie"]
    forwarded = TestClient(server.app)
    r = forwarded.post("/pair", json={"code": store.new_code(), "name": "b"}, headers={"x-forwarded-proto": "https"})
    assert "Secure" in r.headers["set-cookie"]


def test_bearer_header(client, store):
    token = pair(client, store)
    fresh = TestClient(server.app)  # no cookie jar
    assert fresh.get("/sessions").status_code == 401
    r = fresh.get("/sessions", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json() == []
    assert fresh.get("/health", headers={"Authorization": f"Bearer {token}"}).json()["session"] is None


def test_websocket_unpaired_is_told_then_closed(client):
    with client.websocket_connect("/ws") as ws:
        first = ws.receive_json()
        assert first["type"] == "error" and "not paired" in first["message"]
        with pytest.raises(WebSocketDisconnect) as info:
            ws.receive_json()
    assert info.value.code == 4401


def test_websocket_paired_gets_hello(client, store):
    token = pair(client, store, "phone")
    fresh = TestClient(server.app)
    with fresh.websocket_connect("/ws", headers={"Authorization": f"Bearer {token}"}) as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["protocol"] == server.PROTOCOL
    assert store.devices()[0].last_seen is not None


def test_revoke_without_restart(client, store):
    token = pair(client, store, "phone")
    fresh = TestClient(server.app)
    headers = {"Authorization": f"Bearer {token}"}
    assert fresh.get("/sessions", headers=headers).status_code == 200
    assert store.revoke("phone")
    assert fresh.get("/sessions", headers=headers).status_code == 401

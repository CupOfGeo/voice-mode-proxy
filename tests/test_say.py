"""`cmd | vmp say`: Claude pipes text to the server, which speaks it without the text
ever passing through Claude's output."""

import asyncio

from fastapi.testclient import TestClient

from voice_mode_proxy import server
from voice_mode_proxy.agent import AgentSession, spoken_tool


class FakeSession:
    def __init__(self):
        self.said: list[str] = []

    async def say_aloud(self, text: str) -> int:
        self.said.append(text)
        return len(text.split())


def test_say_needs_the_token(monkeypatch):
    monkeypatch.setattr(server.hub, "session", FakeSession())
    client = TestClient(server.app)
    assert client.post("/say", content="hi").status_code == 401
    assert client.post("/say", content="hi", headers={"X-VMP-Say-Token": "wrong"}).status_code == 401


def test_say_speaks_into_the_session(monkeypatch):
    session = FakeSession()
    monkeypatch.setattr(server.hub, "session", session)
    r = TestClient(server.app).post(
        "/say", content="# Backlog\n\n- one thing", headers={"X-VMP-Say-Token": server.hub.say_token}
    )
    assert r.status_code == 200 and r.json() == {"words": 5}
    assert session.said == ["# Backlog\n\n- one thing"]


def test_say_without_a_session(monkeypatch):
    monkeypatch.setattr(server.hub, "session", None)
    r = TestClient(server.app).post("/say", content="hi", headers={"X-VMP-Say-Token": server.hub.say_token})
    assert r.status_code == 409


def test_piping_to_say_is_announced_as_reading():
    assert spoken_tool("Bash", {"command": "head -n 5 BACKLOG.md | vmp say", "description": "x"}) == "Reading it out."


def test_say_aloud_cleans_markdown_and_counts_as_spoken(tmp_path):
    events = []

    async def emit(e):
        events.append(e)

    session = AgentSession(tmp_path, emit, tmp_path, max_spoken_chars=10)
    words = asyncio.run(session.say_aloud("# Backlog\n\n- first item that is long\n- second"))
    session.log.close()
    assert events == [{"type": "speak", "kind": "reply", "text": "Backlog first item that is long second"}]
    assert words == 7 and session._spoken_this_turn == 1  # not clipped to max_spoken_chars

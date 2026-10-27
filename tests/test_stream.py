"""A turn Claude starts itself (a background task reporting back) is read and spoken when it
arrives, so the next user message gets its own reply, not the stale one (2026-10-24)."""

import asyncio
from typing import cast

from claude_agent_sdk import AssistantMessage, ClaudeSDKClient, ResultMessage, SystemMessage, TextBlock

from voice_mode_proxy.agent import AgentSession


def turn(text: str) -> list:
    return [
        SystemMessage("init", {"model": "m"}),
        AssistantMessage([TextBlock(text)], "m"),
        ResultMessage("success", 1, 1, False, 1, "s"),
    ]


class FakeClient:
    """The SDK stream as a queue: query() enqueues the reply turn."""

    def __init__(self, replies: dict[str, str]):
        self.replies = replies
        self.stream: asyncio.Queue = asyncio.Queue()

    async def query(self, text: str) -> None:
        for m in turn(self.replies[text]):
            self.stream.put_nowait(m)

    async def receive_messages(self):
        while True:
            yield await self.stream.get()


def test_self_started_turn_does_not_shift_replies(tmp_path):
    spoken: list[str] = []

    async def emit(e):
        if e["type"] == "speak":
            spoken.append(e["text"])

    async def main():
        session = AgentSession(tmp_path, emit, tmp_path)
        session.title = "named"  # skip the real Haiku call that names a session
        client = FakeClient({"how did it go?": "Twenty of twenty.", "thanks": "You're welcome."})
        session._client = cast(ClaudeSDKClient, client)
        session._reader = asyncio.create_task(session._read())
        for m in turn("The background run finished."):  # nobody asked; Claude reports in
            client.stream.put_nowait(m)
        await asyncio.sleep(0.01)
        assert spoken == ["The background run finished."] and not session.busy
        await session.run_turn("how did it go?")
        assert spoken[-1] == "Twenty of twenty."
        await session.run_turn("thanks")
        assert spoken[-1] == "You're welcome."
        session._reader.cancel()
        session.log.close()

    asyncio.run(main())

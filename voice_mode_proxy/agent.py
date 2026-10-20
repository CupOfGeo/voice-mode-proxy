"""One Claude Code session, driven through the Agent SDK.

Responsibilities:
  * start a new or resumed session in a working directory
  * run one turn at a time: send text, stream SDK messages, log them
  * route permission requests out as events and wait for the answer
  * at the end of a turn, produce what should be spoken
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, cast, get_args

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    PermissionMode,
    PermissionResultDeny,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolPermissionContext,
    ToolUseBlock,
    query,
)

from .records import to_record
from .session_log import SessionLog, read_title
from .text import sentences, speakable

Emit = Callable[[dict], Awaitable[None]]

TITLE_MODEL = "claude-haiku-4-5-20251001"
TITLE_MAX_CHARS = 60
TITLE_PROMPT = """\
Write a title for a coding session that opened with the exchange below. \
Reply with the title only: three to seven words, plain English, no quotes, no trailing period.

User: {prompt}

Assistant: {reply}
"""

# Appended to Claude Code's own system prompt: Claude writes its final reply to be read aloud.
VOICE_PROMPT = """\
You are being used through a voice interface. The user is speaking to you from a phone, \
often while walking, and cannot see a screen. Your final reply of each turn is read aloud \
by text-to-speech, so write it to be spoken:
- Two or three short sentences in plain conversational English. Four at most.
- No markdown, headings, bullet lists, tables or code blocks. No file paths or line numbers; \
say file names as plain words, like "the models file".
- Lead with what you did or found. Then say clearly if anything failed, was skipped, or needs \
the user's decision, and what you need from them.
- Do not narrate intermediate steps. A few words before a tool call is fine.
- If the full answer is genuinely long, give the short spoken version and say the details are \
in the session transcript.
- To read a file or command output aloud, pipe exactly the part the user asked for into \
`vmp say` (for example `head -n 20 notes.md | vmp say`, or `jq -r` for plain JSON values). \
It is spoken for you; do not repeat it, just say a few words at most afterwards.
"""


def as_permission_mode(mode: str) -> PermissionMode:
    """Check a mode string from config or the client against the SDK's allowed values."""
    allowed = get_args(PermissionMode)
    if mode not in allowed:
        raise ValueError(f"unknown permission mode {mode!r}; expected one of {', '.join(allowed)}")
    return cast(PermissionMode, mode)


def strip_credentials() -> list[str]:
    """Drop API-key auth so the Claude Code subprocess uses the claude.ai login."""
    removed = []
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        if os.environ.pop(var, None) is not None:
            removed.append(var)
    return removed


def clip_spoken(text: str, max_chars: int) -> str:
    """Keep whole sentences up to about max_chars; say the rest is in the transcript."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    kept: list[str] = []
    for s in sentences(text):
        if kept and len(" ".join(kept)) + len(s) > max_chars:
            break
        kept.append(s)
    return " ".join(kept).strip() + " There's more in the transcript."


def spoken_permission(tool: str, inp: dict) -> str:
    """What to say out loud when Claude asks for permission."""
    name = Path(inp.get("file_path") or inp.get("notebook_path") or "").name
    if tool == "Write":
        return f"It wants to write {name}."
    if tool in {"Edit", "MultiEdit", "NotebookEdit"}:
        return f"It wants to edit {name}."
    if tool == "Read":
        return f"It wants to read {name}." if name else "It wants to read a file."
    if tool in {"Glob", "Grep"}:
        return "It wants to search the files."
    if tool == "LSP":
        return "It wants to look up code with the language server."
    if tool in {"WebFetch", "WebSearch"}:
        return "It wants to use the web."
    if tool == "Bash":
        desc = inp.get("description")
        return f"It wants to run a command: {desc}." if desc else "It wants to run a shell command."
    if tool.startswith("mcp__"):
        parts = tool.split("__")
        server = parts[1].replace("_", " ") if len(parts) > 1 else tool
        return f"It wants to use the {server} tool."
    return f"It wants to use {tool}."


def spoken_tool(tool: str, inp: dict) -> str:
    """What to say out loud as Claude starts a tool. Short: it lands between its own words.

    ponytail: in the default permission mode an edit is narrated here and then again by
    spoken_permission; live with the echo or gate it on the mode if it grates.
    """
    name = Path(inp.get("file_path") or inp.get("notebook_path") or "").name
    if tool == "Bash":
        if "vmp say" in inp.get("command", ""):
            return "Reading it out."
        desc = inp.get("description")
        return f"Running a command: {desc}." if desc else "Running a shell command."
    if tool == "Write":
        return f"Writing {name}." if name else "Writing a file."
    if tool in {"Edit", "MultiEdit", "NotebookEdit"}:
        return f"Editing {name}." if name else "Editing a file."
    if tool == "Read":
        return f"Reading {name}." if name else "Reading a file."
    if tool in {"Glob", "Grep"}:
        return "Searching the files."
    if tool == "LSP":
        return "Looking up code."
    if tool in {"WebFetch", "WebSearch"}:
        return "Checking the web."
    if tool in {"Task", "Agent"}:
        return "Starting a subagent."
    if tool.startswith("mcp__"):
        parts = tool.split("__")
        return f"Using the {parts[1].replace('_', ' ')} tool." if len(parts) > 1 else f"Using {tool}."
    return f"Using {tool}."


def tool_target(tool: str, inp: dict) -> str:
    """The one line the transcript shows beside the tool name. First field that says something."""
    for key in ("description", "file_path", "notebook_path", "command", "pattern", "query", "url", "prompt"):
        value = inp.get(key)
        if value:
            return " ".join(str(value).split())[:120]
    return ""


def permission_detail(tool: str, inp: dict) -> dict:
    """What the phone card shows. Full input goes to the log, not the wire."""
    if tool == "Write":
        return {"file": inp.get("file_path"), "bytes": len(inp.get("content", ""))}
    if tool in {"Edit", "MultiEdit"}:
        edits = inp.get("edits") or [inp]
        return {
            "file": inp.get("file_path"),
            "edits": [{"old": e.get("old_string", "")[:400], "new": e.get("new_string", "")[:400]} for e in edits[:5]],
        }
    if tool == "Bash":
        return {"command": inp.get("command", "")[:600], "description": inp.get("description")}
    return {k: (v if len(str(v)) <= 300 else str(v)[:300] + "…") for k, v in inp.items()}


@dataclass
class PermissionRequest:
    id: str
    tool: str
    input: dict
    spoken: str
    detail: dict
    future: asyncio.Future = field(repr=False)

    def as_event(self) -> dict:
        return {
            "type": "permission_request",
            "request_id": self.id,
            "tool": self.tool,
            "spoken": self.spoken,
            "detail": self.detail,
        }


class AgentSession:
    def __init__(
        self,
        cwd: Path,
        emit: Emit,
        logs_dir: Path,
        resume: str | None = None,
        claude_model: str | None = None,
        permission_mode: str = "auto",
        max_spoken_chars: int = 600,
        voice_prompt: str = VOICE_PROMPT,
    ):
        self.max_spoken_chars = max_spoken_chars
        self.voice_prompt = voice_prompt
        self._spoken_this_turn = 0
        self.cwd = cwd
        self.emit = emit
        self.resume = resume
        self.session_id = resume or str(uuid.uuid4())
        self.claude_model = claude_model
        self.logs_dir = logs_dir
        self.log = SessionLog(logs_dir / f"{self.session_id}.jsonl")
        self.title: str | None = read_title(self.log.path) if resume else None
        self._title_task: asyncio.Task | None = None
        self.pending: dict[str, PermissionRequest] = {}
        self.busy = False
        self.model: str | None = None
        self.permission_mode = permission_mode
        self._client: ClaudeSDKClient | None = None

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        options = ClaudeAgentOptions(
            cwd=self.cwd,
            # Claude Code's own prompt (needed for CLAUDE.md) plus the voice instructions. The SDK
            # sets this once per connect, so a changed prompt needs a session restart (resume).
            system_prompt={"type": "preset", "preset": "claude_code", "append": self.voice_prompt},
            setting_sources=None,  # user + project + local, same as the CLI
            permission_mode=as_permission_mode(self.permission_mode),
            can_use_tool=self._can_use_tool,
            model=self.claude_model,
            resume=self.resume,
            session_id=None if self.resume else self.session_id,
        )
        self._client = ClaudeSDKClient(options=options)
        await self._client.connect()
        self.log.write("session_started", session_id=self.session_id, cwd=str(self.cwd), resumed_from=self.resume)

    async def close(self) -> None:
        for req in list(self.pending.values()):
            if not req.future.done():
                req.future.set_result(False)
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:  # noqa: BLE001 - best effort on shutdown
                pass
        self.log.write("session_closed")
        self.log.close()

    async def interrupt(self) -> None:
        if self._client and self.busy:
            await self._client.interrupt()
            self.log.write("interrupt")

    async def set_permission_mode(self, mode: str) -> None:
        """'default' asks for everything; 'acceptEdits' stops asking for file edits."""
        assert self._client, "call start() first"
        await self._client.set_permission_mode(as_permission_mode(mode))
        self.permission_mode = mode
        self.log.write("permission_mode", mode=mode)
        await self.emit(self.info())

    def info(self) -> dict:
        return {
            "type": "session",
            "session_id": self.session_id,
            "cwd": str(self.cwd),
            "project": self.cwd.name,
            "title": self.title,
            "resumed_from": self.resume,
            "model": self.model,
            "busy": self.busy,
            "permission_mode": self.permission_mode,
        }

    # ------------------------------------------------------------------ turns

    async def run_turn(self, text: str) -> None:
        assert self._client, "call start() first"
        self.busy = True
        self.log.write("user_text", text=text)
        await self.emit({"type": "transcript", "role": "user", "text": text})
        await self.emit({"type": "status", "state": "working"})

        records: list[dict] = [{"type": "prompt", "cwd": str(self.cwd), "prompt": text}]
        error: str | None = None
        self._spoken_this_turn = 0
        try:
            await self._client.query(text)
            async for msg in self._client.receive_response():
                rec = to_record(msg)
                records.append(rec)
                self.log.write("sdk", message=rec)
                await self._relay(msg)
        except Exception as e:  # noqa: BLE001 - surface anything to the user, keep the server alive
            error = f"{type(e).__name__}: {e}"
            self.log.write("error", message=error)
        finally:
            self.busy = False

        await self._speak_outcome(records, error)
        await self.emit({"type": "status", "state": "idle"})
        await self.emit({"type": "turn_done"})

        if self.title is None and error is None and self._title_task is None:
            reply = " ".join(
                b["text"]
                for r in records
                if r.get("type") == "AssistantMessage"
                for b in r.get("content", [])
                if b.get("block") == "TextBlock"
            )
            self._title_task = asyncio.create_task(self._make_title(text, reply))

    async def _make_title(self, prompt: str, reply: str) -> None:
        """One cheap Haiku call after the first turn names the session. Falls back to the prompt's opening words."""
        title = ""
        try:
            options = ClaudeAgentOptions(
                model=TITLE_MODEL,
                max_turns=1,
                tools=[],
                system_prompt="You name coding sessions. Output only the title.",
                setting_sources=[],
                cwd=self.logs_dir,  # keep the throwaway transcript out of the user's project
            )
            text = TITLE_PROMPT.format(prompt=prompt[:1500], reply=reply[:1500])
            async for msg in query(prompt=text, options=options):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            title += block.text
        except Exception as e:  # noqa: BLE001 - a title is never worth failing the session
            self.log.write("error", message=f"title: {type(e).__name__}: {e}")
        title = " ".join(title.split()).strip(" \"'.")
        if not title:
            title = " ".join(prompt.split()[:7])
        self.title = title[:TITLE_MAX_CHARS]
        self.log.write("session_title", title=self.title)
        await self.emit(self.info())

    async def _relay(self, msg: object) -> None:
        """Forward the SDK stream to the UI. Claude's text blocks are spoken as they arrive,
        including the few words it says before a tool call; tool calls are screen-only."""
        if isinstance(msg, SystemMessage) and msg.subtype == "init":
            self.model = msg.data.get("model")
            await self.emit(self.info())
        elif isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock) and block.text.strip():
                    spoken = clip_spoken(speakable(block.text), self.max_spoken_chars)
                    if spoken:
                        self._spoken_this_turn += 1
                        await self._say("reply", spoken)
                elif isinstance(block, ToolUseBlock):
                    await self.emit(
                        {
                            "type": "tool",
                            "name": block.name,
                            "target": tool_target(block.name, block.input),
                            "spoken": spoken_tool(block.name, block.input),
                            "detail": permission_detail(block.name, block.input),
                        }
                    )
        elif isinstance(msg, ResultMessage):
            await self.emit(
                {
                    "type": "result",
                    "subtype": msg.subtype,
                    "is_error": msg.is_error,
                    "num_turns": msg.num_turns,
                    "duration_ms": msg.duration_ms,
                }
            )

    async def _speak_outcome(self, records: list[dict], error: str | None) -> None:
        if error:
            await self._say("error", f"Claude Code hit an error. {speakable(error)[:300]}")
            return
        result = next((r for r in records if r.get("type") == "ResultMessage"), None)
        if result and result.get("is_error"):
            await self._say(
                "error", "Claude Code stopped with an error. " + speakable(str(result.get("result") or ""))[:300]
            )
            return

        # Claude's final reply was already spoken by _relay as its last text block (it writes
        # for speech per VOICE_PROMPT).
        if not self._spoken_this_turn:
            await self._say("reply", "Done, but Claude Code did not say anything.")

    async def say_aloud(self, text: str) -> int:
        """Speak text piped in through `vmp say`, unclipped. Returns the words spoken."""
        spoken = speakable(text)
        if spoken:
            self._spoken_this_turn += 1
            await self._say("reply", spoken)
        return len(spoken.split())

    async def _say(self, kind: str, text: str) -> None:
        self.log.write("spoken", kind=kind, text=text)
        await self.emit({"type": "speak", "kind": kind, "text": text})

    # ------------------------------------------------------------------ permissions

    async def _can_use_tool(
        self, tool_name: str, tool_input: dict[str, Any], context: ToolPermissionContext
    ) -> PermissionResultAllow | PermissionResultDeny:
        req = PermissionRequest(
            id=context.tool_use_id or str(uuid.uuid4()),
            tool=tool_name,
            input=tool_input,
            spoken=spoken_permission(tool_name, tool_input),
            detail=permission_detail(tool_name, tool_input),
            future=asyncio.get_running_loop().create_future(),
        )
        self.pending[req.id] = req
        self.log.write("permission_request", request_id=req.id, tool=tool_name, input=tool_input, spoken=req.spoken)
        await self.emit(req.as_event())
        try:
            allow = await req.future
        finally:
            self.pending.pop(req.id, None)
        self.log.write("permission_response", request_id=req.id, allow=allow)
        await self.emit({"type": "permission_resolved", "request_id": req.id, "allow": allow})
        if allow:
            return PermissionResultAllow()
        return PermissionResultDeny(message="Denied by the user from the voice proxy")

    def answer_permission(self, request_id: str, allow: bool) -> bool:
        req = self.pending.get(request_id)
        if not req or req.future.done():
            return False
        req.future.set_result(allow)
        return True

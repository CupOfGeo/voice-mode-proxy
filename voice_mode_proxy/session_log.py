"""One JSON Lines file per session. No database.

Each line is one event with a timestamp. Enough to reconstruct both the real
conversation and the spoken one:
  user_text, sdk (raw SDK message), spoken, permission_request,
  permission_response, client_connected, client_disconnected, error.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class SessionLog:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh: TextIO = path.open("a", encoding="utf-8")

    def write(self, event: str, **data: Any) -> None:
        line = {"ts": _now(), "event": event, **data}
        self._fh.write(json.dumps(line, default=str) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


def list_sessions(logs_dir: Path, limit: int = 20) -> list[dict]:
    """Summaries of past sessions, newest first, from the first lines of each log."""
    out: list[dict] = []
    if not logs_dir.exists():
        return out
    files = sorted(logs_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files[:limit]:
        info: dict = {"session_id": path.stem, "updated": datetime.fromtimestamp(path.stat().st_mtime).isoformat()}
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("event") == "session_started":
                    info["cwd"] = ev.get("cwd")
                    info["started"] = ev.get("ts")
                    info["resumed_from"] = ev.get("resumed_from")
                elif ev.get("event") == "user_text" and "first_prompt" not in info:
                    info["first_prompt"] = ev.get("text", "")[:120]
                elif ev.get("event") == "session_title":
                    info["title"] = ev.get("title")
                    break  # the title is written after the first turn, so nothing else is needed
        out.append(info)
    return out


def read_title(path: Path) -> str | None:
    """Last `session_title` written to a log, or None. Used when resuming a session."""
    if not path.exists():
        return None
    title = None
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if '"session_title"' not in line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("event") == "session_title":
                title = ev.get("title")
    return title


def read_history(path: Path, limit: int = 300) -> list[dict]:
    """The conversation so far as client events (transcript / speak), oldest first, for redrawing the page."""
    if not path.exists():
        return []
    items: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if '"user_text"' not in line and '"spoken"' not in line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("event") == "user_text":
                items.append({"type": "transcript", "role": "user", "text": ev.get("text", "")})
            elif ev.get("event") == "spoken":
                items.append({"type": "speak", "kind": ev.get("kind", "reply"), "text": ev.get("text", "")})
    return items[-limit:]

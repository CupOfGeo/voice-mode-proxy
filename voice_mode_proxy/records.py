"""Turn SDK message dataclasses into plain dicts for the session log."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass


def to_record(msg: object) -> dict:
    """``type`` is the message class name; content blocks carry a ``block`` key."""
    if not (is_dataclass(msg) and not isinstance(msg, type)):
        return {"type": type(msg).__name__, "repr": repr(msg)}
    body = asdict(msg)  # type: ignore[arg-type]
    content = getattr(msg, "content", None)
    if isinstance(content, list):
        body["content"] = [
            {"block": type(b).__name__, **asdict(b)} if is_dataclass(b) else b  # type: ignore[arg-type]
            for b in content
        ]
    return {"type": type(msg).__name__, **body}

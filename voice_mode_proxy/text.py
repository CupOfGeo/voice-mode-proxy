"""Small text helpers shared across the speech path."""

from __future__ import annotations

import re

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def sentences(text: str) -> list[str]:
    """Split on sentence-ending punctuation; stripped, no empty pieces.

    Used by the echo guard, the spoken-reply clipper and the TTS streamer, so a
    tweak here (abbreviations, ellipses) lands everywhere.
    """
    return [s.strip() for s in _SENTENCE_END.split(text.strip()) if s.strip()]


def speakable(text: str) -> str:
    """Make markdown safe to read aloud without changing what it says."""
    text = re.sub(r"```.*?```", " Code omitted. ", text, flags=re.S)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)  # headings
    text = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", text, flags=re.M)  # bullets
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # links
    text = re.sub(r"[`*~>|]+", "", text)
    text = re.sub(r"(?<=\w)_(?=\w)", " ", text)  # snake_case -> separate words
    text = re.sub(r"(?<![\w.])_+|_+(?![\w.])", "", text)  # stray/dunder underscores
    text = re.sub(r"\n{2,}", " ", text)
    text = re.sub(r"\n", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

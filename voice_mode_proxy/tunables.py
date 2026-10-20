"""Settings the phone may change while the server runs.

config.toml and the VMP_ environment give the defaults. Whatever the phone last set is kept
in overrides.json next to config.toml and wins until it is set back to the default. The
server sends a ``settings`` event with both the current values and the defaults after every
hello and after every change, so the app shows both and never keeps its own copy.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .agent import VOICE_PROMPT
from .config import CONFIG_FILE, settings

log = logging.getLogger("vmp")

OVERRIDES_FILE = CONFIG_FILE.with_name("overrides.json")


class Tunables(BaseModel):
    """The values, with the ranges the sliders use. ``extra="forbid"`` rejects unknown keys."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    speech_rate: float = Field(ge=0.5, le=2.0)
    kokoro_voice: str = Field(min_length=1)
    vad_silence_ms: int = Field(ge=300, le=10_000)
    vad_min_speech_ms: int = Field(ge=0, le=5_000)
    vad_barge_in_ms: int = Field(ge=0, le=10_000)
    voice_prompt: str = Field(min_length=1, max_length=8_000)


def _defaults() -> Tunables:
    return Tunables(
        speech_rate=settings.speech_rate,
        kokoro_voice=settings.kokoro_voice,
        vad_silence_ms=settings.vad_silence_ms,
        vad_min_speech_ms=settings.vad_min_speech_ms,
        vad_barge_in_ms=settings.vad_barge_in_ms,
        voice_prompt=VOICE_PROMPT,
    )


class TunableStore:
    def __init__(self, path: Path = OVERRIDES_FILE):
        self.path = path
        self.defaults = _defaults()
        self.current = self.defaults
        overrides = self._read()
        if overrides:
            try:
                self.current = self.validate(overrides)
                log.info("overrides from %s: %s", path, ", ".join(sorted(overrides)))
            except ValidationError as e:
                log.warning("ignoring %s: %s", path, e)

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            log.warning("ignoring %s: %s", self.path, e)
            return {}
        return data if isinstance(data, dict) else {}

    def validate(self, values: dict) -> Tunables:
        """The current values with ``values`` on top, checked; raises ValidationError."""
        return Tunables.model_validate({**self.current.model_dump(), **values})

    def commit(self, new: Tunables) -> dict:
        """Make ``new`` current and persist the keys that differ from the defaults.

        Returns what changed against the previous values, for the log."""
        changed = {k: v for k, v in new.model_dump().items() if v != getattr(self.current, k)}
        self.current = new
        overrides = {k: v for k, v in new.model_dump().items() if v != getattr(self.defaults, k)}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if overrides:
                self.path.write_text(json.dumps(overrides, indent=2) + "\n")
            else:
                self.path.unlink(missing_ok=True)
        except OSError as e:
            log.warning("could not save %s: %s", self.path, e)
        return changed

    def event(self, voices: list[str]) -> dict:
        return {
            "type": "settings",
            "values": self.current.model_dump(),
            "defaults": self.defaults.model_dump(),
            "voices": voices,
        }

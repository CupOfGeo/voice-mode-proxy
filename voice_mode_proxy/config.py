"""Settings: config.toml first, environment variables (VMP_ prefix) on top, then defaults.

The file lives at ~/.config/voice-mode-proxy/config.toml unless VMP_CONFIG points elsewhere;
config.example.toml in the repo lists every key. Env vars use the key name upper-cased with
the prefix, e.g. ``vad_silence_ms`` is ``VMP_VAD_SILENCE_MS``.
"""

from __future__ import annotations

import os
from pathlib import Path
from collections.abc import Iterable
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import (
    BaseSettings,
    NoDecode,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = Path(os.environ.get("VMP_CONFIG", "~/.config/voice-mode-proxy/config.toml")).expanduser()


def _expand_project(entry: str) -> list[Path]:
    """One projects entry to concrete folders; "dir/*" lists the git repos directly inside dir."""
    entry = entry.strip()
    if entry.endswith("/*"):
        parent = Path(entry[:-2]).expanduser().resolve()
        return sorted(d for d in parent.iterdir() if d.is_dir() and (d / ".git").exists()) if parent.is_dir() else []
    return [Path(entry).expanduser().resolve()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VMP_", toml_file=CONFIG_FILE, frozen=True, extra="forbid")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, TomlConfigSettingsSource(settings_cls))

    # Loopback only, by default: the phone comes in through Tailscale Serve, which forwards
    # to this port. Set host to the Tailscale IP to skip Serve, or "0.0.0.0" to expose the
    # proxy on every network the Mac is on, in plain HTTP. Only paired devices can use the
    # proxy (see pairing.py); Tailscale keeps it off the open internet.
    host: str = "127.0.0.1"
    port: int = 8791

    # Working directory Claude Code sessions run in, unless the client names one.
    project_dir: Path = ROOT

    # Folders the phone may start sessions in; the picker shows these. Each entry may use "~",
    # and a trailing "/*" means every git repo directly under that folder. As an env var it is
    # colon-separated.
    projects: Annotated[tuple[str, ...], NoDecode] = (str(ROOT),)

    # One JSON Lines file per session lives here.
    logs_dir: Path = ROOT / "logs"

    # Speech in. stt_enabled = false skips loading Whisper (text box only).
    whisper_model: str = "mlx-community/whisper-large-v3-turbo"
    stt_enabled: bool = True
    # How long you must stay quiet before what you said is sent to Claude. Raise it if
    # it keeps cutting you off mid-thought; lower it for snappier turns.
    vad_silence_ms: int = 2000
    # Shorter bursts than this never reach Whisper at all (breaths, clicks, a cough).
    vad_min_speech_ms: int = 500
    # While the page is playing our reply, the mic must hear this much sustained speech
    # before it counts as a barge-in. Raise it if the phone speaker keeps interrupting
    # the reply (leaked audio); lower it for faster interrupts with earbuds.
    vad_barge_in_ms: int = 1500
    # Whisper confidence gate: transcripts with a mean token log-probability below this,
    # or a no-speech probability above this, are dropped. It invents phrases on noise.
    stt_min_logprob: float = -0.8
    stt_max_no_speech: float = 0.5
    # "rejected" keeps the clips the gate dropped as WAVs ("all" keeps every utterance)
    # under logs/audio with an index.jsonl of scores, for tuning.
    save_audio: Literal["", "rejected", "all"] = ""

    # Speech out. tts_enabled = false skips Kokoro; the page then falls back to the browser's voices.
    tts_enabled: bool = True
    # Backstop when Claude ignores the voice prompt's length rule: longer replies are cut at a
    # sentence boundary near this many characters, with a pointer to the transcript. 0 disables.
    max_spoken_chars: int = 0
    # 1.0 is the voice's natural pace; 1.2 is noticeably brisker without sounding rushed.
    speech_rate: float = 1.15
    # Kokoro needs kokoro-v1.0.onnx and voices-v1.0.bin in this directory.
    kokoro_dir: Path = ROOT / "voices/kokoro"
    kokoro_voice: str = "af_heart"

    # Leave unset to use Claude Code's default model for the account.
    claude_model: str | None = None

    # Starting permission mode for new sessions:
    #   auto        classifier approves safe tool calls, prompts for the rest
    #   default     prompt for everything the CLI would prompt for
    #   acceptEdits file edits never prompt, commands still do
    permission_mode: Literal["auto", "default", "acceptEdits"] = "auto"

    @field_validator("projects", mode="before")
    @classmethod
    def _split_projects(cls, v: str | Iterable[object]) -> tuple[str, ...]:
        entries = v.split(":") if isinstance(v, str) else list(v)
        return tuple(str(e).strip() for e in entries if str(e).strip())

    @field_validator("project_dir", "logs_dir", "kokoro_dir", mode="after")
    @classmethod
    def _absolute(cls, v: Path) -> Path:
        return v.expanduser().resolve()


settings = Settings()


def project_paths() -> tuple[Path, ...]:
    """The configured folders, rescanned on every call so a repo added to a "dir/*" entry
    after startup shows up as soon as a client asks for the list again."""
    seen: dict[Path, None] = {}
    for entry in settings.projects:
        for p in _expand_project(entry):
            seen.setdefault(p, None)
    return tuple(seen)

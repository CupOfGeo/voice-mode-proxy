"""Speech out: one PCM16 chunk per sentence, from Kokoro.

The engine exposes two things: ``sample_rate`` and ``synthesize(text)`` yielding
mono PCM16 bytes sentence by sentence, so the first sentence can play while the
rest is still being made. ``TextToSpeech`` is the seam for swapping engines.

Offline check, writes a WAV you can play:
  uv run python -m voice_mode_proxy.tts "Hello there. How are you?" out.wav
"""

from __future__ import annotations

import sys
import time
import wave
from pathlib import Path
from typing import Iterator, Protocol

import numpy as np

from .text import sentences


class TextToSpeech(Protocol):
    name: str
    sample_rate: int
    load_seconds: float
    voice: str
    rate: float
    voices: list[str]

    def synthesize(self, text: str) -> Iterator[bytes]: ...

    def set_voice(self, voice: str) -> None:
        """Switch voices for the next sentence; raises ValueError for a name the engine lacks."""
        ...


def split_sentences(text: str, max_chars: int = 220) -> list[str]:
    """Sentences for streaming; long ones are split at commas so no chunk drags."""
    parts = sentences(text)
    out: list[str] = []
    for p in parts:
        while len(p) > max_chars:
            cut = p.rfind(",", 0, max_chars)
            if cut < 40:
                cut = p.rfind(" ", 0, max_chars)
            if cut < 40:
                cut = max_chars
            out.append(p[:cut].strip())
            p = p[cut:].lstrip(", ")
        if p:
            out.append(p)
    return out


def _pcm16(audio: np.ndarray) -> bytes:
    return (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()


class KokoroTTS:
    def __init__(self, model_dir: Path, voice: str = "af_heart", rate: float = 1.0):
        from kokoro_onnx import Kokoro  # lazy: onnxruntime + phonemizer

        model = model_dir / "kokoro-v1.0.onnx"
        voices = model_dir / "voices-v1.0.bin"
        if not model.exists() or not voices.exists():
            raise FileNotFoundError(f"Kokoro files missing in {model_dir}: need kokoro-v1.0.onnx and voices-v1.0.bin")
        t = time.time()
        self._k = Kokoro(str(model), str(voices))
        self.voices: list[str] = sorted(self._k.get_voices())
        self.voice = ""
        self.set_voice(voice)
        self.rate = rate  # read per sentence, so it can change between replies
        self.sample_rate = 24_000
        list(self.synthesize("Ready."))  # warm up
        self.load_seconds = time.time() - t

    def set_voice(self, voice: str) -> None:
        if voice not in self.voices:
            raise ValueError(f"unknown Kokoro voice {voice!r}; try one of {self.voices[:12]}")
        self.voice = voice
        self.name = f"kokoro/{voice}"

    def synthesize(self, text: str) -> Iterator[bytes]:
        for sentence in split_sentences(text):
            samples, sr = self._k.create(sentence, voice=self.voice, speed=self.rate, lang="en-us")
            self.sample_rate = int(sr)
            yield _pcm16(np.asarray(samples, dtype=np.float32))


def load_tts(model_dir: Path, voice: str, rate: float) -> TextToSpeech:
    """Build the Kokoro engine; raises FileNotFoundError if the model files are missing."""
    return KokoroTTS(model_dir, voice, rate)


def _main(text: str, out: str) -> None:
    from .config import settings

    tts = load_tts(settings.kokoro_dir, settings.kokoro_voice, settings.speech_rate)
    print(f"{tts.name} at {tts.sample_rate} Hz, rate {tts.rate}, loaded in {tts.load_seconds:.1f}s")
    t = time.time()
    chunks = list(tts.synthesize(text))
    total = sum(len(c) for c in chunks)
    print(f"{len(chunks)} chunk(s), {total / 2 / tts.sample_rate:.1f}s of audio in {time.time() - t:.2f}s")
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(tts.sample_rate)
        for c in chunks:
            w.writeframes(c)
    print(f"wrote {out}")


if __name__ == "__main__":
    _main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "tts_check.wav")

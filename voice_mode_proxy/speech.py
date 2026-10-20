"""Speech in: Silero VAD segments the mic stream, mlx-whisper transcribes each utterance.

The browser sends 16 kHz mono PCM16 frames over the WebSocket. ``VadSegmenter``
turns that stream into finished utterances; ``SpeechToText`` turns an utterance
into text. ``AudioPipeline`` glues the two together for one client.

Offline check, streaming a WAV through the same code path in 100 ms frames:
  uv run python -m voice_mode_proxy.speech some.wav [more.wav ...]
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
import wave
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable

import numpy as np

from .config import settings

log = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
CHUNK = 512  # samples per Silero window at 16 kHz (32 ms)

# Whisper likes to invent these on silence or breath noise.
HALLUCINATIONS = {"", "you", "thank you", "thanks for watching", "bye", "so", "um", "uh", "the"}


class SpeechToText:
    """Whisper with a confidence gate: short noise bursts that slip past the VAD make
    Whisper invent plausible phrases ("She lives."), so anything it is not sure about
    is dropped rather than sent to Claude. Rejections are logged with their scores so
    the thresholds can be tuned from real sessions."""

    def __init__(
        self,
        model: str,
        min_logprob: float,
        max_no_speech: float,
        language: str | None = "en",
        save_audio: str = "",
        save_dir: Path | None = None,
    ):
        import mlx_whisper  # lazy: heavy import

        self._mlx_whisper = mlx_whisper
        self.model = model
        self.language = language
        self.min_logprob = min_logprob  # duration-weighted mean token log-probability, closer to 0 is surer
        self.max_no_speech = max_no_speech  # Whisper's own "this is not speech" probability
        # Opt-in clip archive for tuning: "rejected" keeps what the gate dropped, "all" keeps
        # every utterance. WAVs plus an index.jsonl of scores land in save_dir.
        self.save_audio = save_audio if save_audio in {"rejected", "all"} else ""
        self.save_dir = save_dir
        self._ready = False
        t = time.time()
        self.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32))  # loads and warms the model
        self.load_seconds = time.time() - t
        self._ready = True

    def transcribe(self, audio: np.ndarray) -> str:
        """audio: float32 mono at 16 kHz in [-1, 1]. Returns '' for nothing worth sending on."""
        result = self._mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=self.model,
            language=self.language,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            temperature=0.0,
        )
        text = str(result.get("text", "")).strip()
        segments = [s for s in result.get("segments") or [] if s.get("end", 0) > s.get("start", 0)]
        total = sum(s["end"] - s["start"] for s in segments)
        logprob = sum(s.get("avg_logprob", 0.0) * (s["end"] - s["start"]) for s in segments) / total if total else 0.0
        no_speech = (
            sum(s.get("no_speech_prob", 0.0) * (s["end"] - s["start"]) for s in segments) / total if total else 1.0
        )
        repetitive = any(s.get("compression_ratio", 0.0) > 2.4 for s in segments)

        reason = ""
        if not text:
            reason = "empty"  # Whisper itself heard nothing
        elif text.strip(" .!?,").lower() in HALLUCINATIONS:
            reason = "hallucination"
        elif segments and (logprob < self.min_logprob or no_speech > self.max_no_speech or repetitive):
            reason = "low-confidence"
        if reason and text:
            log.info(
                "dropped %s transcript %r (logprob %.2f, no_speech %.2f, %.1fs)",
                reason,
                text,
                logprob,
                no_speech,
                len(audio) / SAMPLE_RATE,
            )
        elif text:
            log.debug("transcript %r (logprob %.2f, no_speech %.2f)", text, logprob, no_speech)
        if self.save_audio and self._ready and (reason or self.save_audio == "all"):
            self._save(audio, text, reason, logprob, no_speech)
        return "" if reason else text

    def _save(self, audio: np.ndarray, text: str, reason: str, logprob: float, no_speech: float) -> None:
        """One WAV per utterance plus a line in index.jsonl so clips can be replayed and scored later."""
        if self.save_dir is None:
            return
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
            name = f"{stamp}_{reason or 'kept'}.wav"
            with wave.open(str(self.save_dir / name), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SAMPLE_RATE)
                w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
            entry = {
                "file": name,
                "seconds": round(len(audio) / SAMPLE_RATE, 2),
                "text": text,
                "dropped": reason or None,
                "logprob": round(logprob, 3),
                "no_speech": round(no_speech, 3),
            }
            with (self.save_dir / "index.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:  # noqa: BLE001 - archiving must never break transcription
            log.warning("could not save clip: %s", e)


class VadSegmenter:
    """Feed PCM16 bytes, get back finished utterances as float32 arrays."""

    def __init__(
        self,
        min_silence_ms: int,
        min_speech_ms: int,
        pre_roll_ms: int = 320,
        max_utterance_s: float = 30.0,
        threshold: float = 0.5,
    ):
        import torch
        from silero_vad import VADIterator, load_silero_vad

        self._torch = torch
        self._iter = VADIterator(
            load_silero_vad(), threshold=threshold, sampling_rate=SAMPLE_RATE, min_silence_duration_ms=min_silence_ms
        )
        self.min_speech_samples = int(SAMPLE_RATE * min_speech_ms / 1000)
        self.max_samples = int(SAMPLE_RATE * max_utterance_s)
        self._pre: deque[np.ndarray] = deque(maxlen=max(1, pre_roll_ms // 32))
        self._pending = np.zeros(0, dtype=np.float32)
        self._utterance: list[np.ndarray] = []
        self._utterance_len = 0
        self.speaking = False

    def feed(self, pcm16: bytes) -> list[np.ndarray]:
        samples = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        self._pending = np.concatenate([self._pending, samples])
        done: list[np.ndarray] = []
        while len(self._pending) >= CHUNK:
            chunk, self._pending = self._pending[:CHUNK], self._pending[CHUNK:]
            utt = self._process(chunk)
            if utt is not None:
                done.append(utt)
        return done

    def _process(self, chunk: np.ndarray) -> np.ndarray | None:
        event = self._iter(self._torch.from_numpy(chunk))
        if event and "start" in event and not self.speaking:
            self.speaking = True
            self._utterance = list(self._pre)
            self._utterance_len = sum(len(c) for c in self._utterance)
        if self.speaking:
            self._utterance.append(chunk)
            self._utterance_len += len(chunk)
        else:
            self._pre.append(chunk)

        ended = bool(event and "end" in event)
        too_long = self.speaking and self._utterance_len >= self.max_samples
        if self.speaking and (ended or too_long):
            audio = np.concatenate(self._utterance)
            self.speaking = False
            self._utterance, self._utterance_len = [], 0
            if too_long:
                self._iter.reset_states()
            return audio if len(audio) >= self.min_speech_samples else None
        return None

    @property
    def speaking_ms(self) -> int:
        """How long the current utterance has run, pre-roll excluded."""
        if not self.speaking:
            return 0
        pre_roll = (self._pre.maxlen or 0) * CHUNK
        return int(max(0, self._utterance_len - pre_roll) * 1000 / SAMPLE_RATE)

    def reset(self) -> None:
        self._iter.reset_states()
        self._pending = np.zeros(0, dtype=np.float32)
        self._utterance, self._utterance_len = [], 0
        self._pre.clear()
        self.speaking = False


class AudioPipeline:
    """Per-client: bytes in, transcribed text out. VAD runs inline, Whisper in a thread.

    ``on_speaking(True)`` is the barge-in signal. While the client reports that it is
    playing our audio, it only fires after ``barge_in_ms`` of sustained speech, so a
    syllable of speaker bleed doesn't silence the reply.
    """

    def __init__(
        self,
        stt: SpeechToText,
        on_text: Callable[[str, float], Awaitable[None]],
        on_speaking: Callable[[bool], Awaitable[None]],
        barge_in_ms: int,
        silence_ms: int,
        min_speech_ms: int,
    ):
        self.stt = stt
        self.on_text = on_text
        self.on_speaking = on_speaking
        self.barge_in_ms = barge_in_ms
        self.playing = False  # set from the client's {"type": "playing"} messages
        self.segmenter = VadSegmenter(min_silence_ms=silence_ms, min_speech_ms=min_speech_ms)
        self._announced = False

    def reconfigure(self, barge_in_ms: int, silence_ms: int, min_speech_ms: int) -> None:
        """Apply new timings from the phone. Silero fixes its silence window at construction,
        so the segmenter is rebuilt; anything being said at that moment is dropped."""
        self.barge_in_ms = barge_in_ms
        self.segmenter = VadSegmenter(min_silence_ms=silence_ms, min_speech_ms=min_speech_ms)
        self._announced = False

    async def feed(self, data: bytes) -> None:
        utterances = self.segmenter.feed(data)
        seg = self.segmenter
        if seg.speaking and not self._announced:
            if not self.playing or seg.speaking_ms >= self.barge_in_ms:
                self._announced = True
                await self.on_speaking(True)
        elif not seg.speaking and self._announced:
            self._announced = False
            await self.on_speaking(False)
        for audio in utterances:
            seconds = len(audio) / SAMPLE_RATE
            text = await asyncio.to_thread(self.stt.transcribe, audio)
            if text:
                await self.on_text(text, seconds)

    def reset(self) -> None:
        self.segmenter.reset()
        self._announced = False


# --------------------------------------------------------------------------- offline check


def read_wav_pcm16(path: Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == SAMPLE_RATE and w.getnchannels() == 1 and w.getsampwidth() == 2, (
            f"{path}: need 16 kHz mono 16-bit, got {w.getframerate()} Hz {w.getnchannels()} ch {w.getsampwidth() * 8}-bit"
        )
        return w.readframes(w.getnframes())


def _main(paths: list[str]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    t = time.time()
    stt = SpeechToText(settings.whisper_model, settings.stt_min_logprob, settings.stt_max_no_speech)
    print(f"whisper {stt.model} ready in {stt.load_seconds:.1f}s")
    seg = VadSegmenter(min_silence_ms=settings.vad_silence_ms, min_speech_ms=settings.vad_min_speech_ms)
    print(f"vad ready ({time.time() - t:.1f}s total)\n")

    frame = SAMPLE_RATE // 10 * 2  # 100 ms of PCM16 bytes
    for p in paths:
        pcm = read_wav_pcm16(Path(p)) + bytes(SAMPLE_RATE * 2 * 2)  # + 2 s silence to close the utterance
        print(f"== {Path(p).name}: {len(pcm) / 2 / SAMPLE_RATE:.1f}s incl. trailing silence")
        t0 = time.time()
        for i in range(0, len(pcm), frame):
            for utt in seg.feed(pcm[i : i + frame]):
                t1 = time.time()
                text = stt.transcribe(utt)
                print(f"  utterance {len(utt) / SAMPLE_RATE:.2f}s -> {time.time() - t1:.2f}s whisper -> {text!r}")
        print(f"  streamed in {time.time() - t0:.2f}s\n")


if __name__ == "__main__":
    _main(sys.argv[1:])

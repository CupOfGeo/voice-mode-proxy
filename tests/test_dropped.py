"""A garbled utterance reaches the phone as "dropped" (it plays a cue); Whisper junk stays silent."""

import asyncio
from typing import cast

import numpy as np

from voice_mode_proxy.speech import AudioPipeline, SpeechToText


class FakeStt:
    def __init__(self, result):
        self.result = result

    def transcribe(self, audio):
        return self.result


def run(result):
    got = []

    async def on_text(text, seconds):
        got.append(("text", text))

    async def on_dropped(text, seconds):
        got.append(("dropped", text))

    async def on_speaking(speech):
        pass

    pipe = AudioPipeline(
        cast(SpeechToText, FakeStt(result)),
        on_text,
        on_speaking,
        on_dropped,
        barge_in_ms=300,
        silence_ms=500,
        min_speech_ms=250,
    )
    setattr(pipe.segmenter, "feed", lambda data: [np.zeros(16000, dtype=np.float32)])  # one utterance, no VAD
    asyncio.run(pipe.feed(b""))
    return got


def test_low_confidence_is_reported_as_dropped():
    assert run(("the act and the table", "low-confidence")) == [("dropped", "the act and the table")]


def test_hallucination_and_kept_text():
    assert run(("Thank you.", "hallucination")) == []
    assert run(("hello there", "")) == [("text", "hello there")]

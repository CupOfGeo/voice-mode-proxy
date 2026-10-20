# Voice Mode Proxy — Build Order

Each step should be independently testable. Don't move on until the current
step works on its own.

## 1. SDK spike — text only
*Done; `spike_sdk.py` was removed 2026-09-16 once the server covered it.*

No audio at all. A Python script that starts a Claude Code session via the
Agent SDK, sends a typed prompt, and prints the structured messages.
Goal: confirm CLAUDE.md, settings and MCP servers are picked up from the
working directory, and see exactly what permission requests look like on the wire.

## 2. Summariser
*Superseded 2026-09-16: Claude Code is asked to write its final reply for speech
(VOICE_PROMPT in agent.py), so the local Qwen summariser was removed.*

Feed real SDK output from step 1 into local Qwen. Tune the prompt until diffs
and tool output reliably come back as one or two plain spoken sentences.
Test against the ugliest output you can find — a big multi-file edit.

## 3. Server skeleton
FastAPI plus a WebSocket endpoint. Text in, text out, no audio.
Wire up session create / resume, and the JSON Lines logger.
At this point it is a working typed remote control for Claude Code.

## 4. Web client
Minimal page served over Tailscale. Text box, transcript view, and the
permission card with Allow / Deny. Prove the round trip from the phone.

## 5. Speech in
Whisper on the server, Silero VAD in front of it. Browser streams mic audio
over the existing WebSocket. Replace the text box with real speech.

## 6. Speech out
Piper, or reuse the Fallout voice cloning work. Speak the summaries.
Add barge-in: new speech detected stops playback immediately.

## 7. Trail test
Walk the actual trail. Find out what breaks. Expect problems with buffering
on reconnect and with background noise.

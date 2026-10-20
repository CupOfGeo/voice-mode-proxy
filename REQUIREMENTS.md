# Voice Mode Proxy — Requirements

## Concept
A local voice layer sitting in front of Claude Code. Speak instructions from a phone,
hear back short spoken summaries instead of raw terminal output. A local LLM acts as
the proxy between the user and Claude Code.

## Core goals
- Talk to Claude Code hands-free, e.g. while on a walk.
- Dial in from a phone; the server runs at home.
- Never read raw diffs or full tool output aloud — summarise.
- Stay quiet by default; speak only when there is a decision or a result.

## Architecture (first pass)
- Client: small web app in the phone browser. Mic capture and audio playback only.
- Transport: WebSocket to the home server.
- Network: reachable over Tailscale. No public exposure, no separate auth layer.
- STT: Whisper (not yet installed).
- Proxy brain: local Qwen 3, ~30B. Classifies speech as instruction vs question,
  turns Claude Code output into short spoken updates.
- Agent: Claude Code via the Agent SDK, not the CLI.
- TTS: Piper, or reuse work from the existing Fallout voice cloning project.

## Why the SDK over the CLI
- Structured messages instead of scraped terminal text.
- Clear signals for: tool call started, permission requested, turn complete.
- Enables spoken permission prompts, e.g. "it wants to edit three files, shall I allow it?"
- Built-in session handling; resuming is a single parameter.

## Interaction design
- Silence while Claude Code works. No progress narration.
- Speak up for: permission requests, completed work, errors, questions.
- Barge-in: user can interrupt playback and issue a new instruction.

## Open questions
- How much conversation history does Qwen need to summarise well?
- Handling long-running tasks when the phone screen locks or the connection drops.
- Whether permission decisions are safe by voice, or need a tap in the web UI.
- Wake word, push-to-talk, or open mic?
- Should the proxy run more than one Claude Code session at once?
- Logging and transcript storage.

## Decisions

### Mic behaviour — DECIDED
Open mic, always listening. No wake word, no push-to-talk. Should feel like a
normal conversation, matching the existing Claude voice mode experience.
- In scope: voice activity detection (Silero VAD or similar) to segment speech.
- Out of scope for v1: detecting whether an utterance was actually addressed to
  the assistant. Known limitation — saying "good morning" to someone on the trail
  will get a reply. Current voice mode has the same flaw. Revisit later; Qwen
  could classify addressee if it becomes annoying.

### Permissions — DECIDED
Permission requests are approved by tapping in the web UI, never by voice.
Rationale: a mis-transcribed "yeah" or "no" is the one failure mode that
directly costs you files. Voice is too lossy for a destructive confirmation.
- Voice announces the request out loud, e.g. "it wants to edit three files."
- The web app shows a card with the details and Allow / Deny buttons.
- Phone is already in hand, so the friction is minimal.

### Disconnects — DECIDED
All state lives on the server, so losing the phone connection only loses the
speaker, not the session.
- Claude Code continues working through a disconnect.
- Server buffers anything the proxy would have spoken.
- On reconnect, the user gets a short catch-up: "while you were gone, here's
  what happened."
- Pending permission requests simply wait until the user is back.

## MVP scope — DECIDED

The bar for v1: it has to work while walking the trail. Nothing more.

### In scope
- One Claude Code session at a time.
- Sessions are resumable — pick an earlier session back up and continue it.
- User speech passes through to Claude Code essentially raw. No summarising the
  user; plain speech is already a fine prompt.
- Qwen has exactly one job: compress Claude Code's output into one or two
  spoken sentences. Diffs, file dumps and tool output never get read aloud.

### Out of scope for v1
- Multiple concurrent sessions.
- Addressee detection (see mic behaviour above).
- Voice-based permission approval.

### Logging — DECIDED
One JSON Lines file per session. No database.
Each line records one event, enough to reconstruct both the real conversation
and the spoken one:
- transcribed user speech
- raw messages from the Claude Code SDK
- the summarised text that was actually spoken aloud
- permission requests and how they were answered
Purpose: read back at a desk later and see what was actually agreed to.

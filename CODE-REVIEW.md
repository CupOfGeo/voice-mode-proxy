# Code smell review — 2026-09-16

Scope: `voice_mode_proxy/*.py`, `web/index.html`. Ordered by how much each one matters.

## 1. Client reconnect can stack WebSockets (root cause of today's "doubles")

`web/index.html:392-403`. Two paths open a socket and neither checks for one already in flight:

- `ws.onclose` schedules `connect()` with `setTimeout` and never keeps the timer handle.
- `visibilitychange` calls `connect()` whenever `ws.readyState !== OPEN`, which includes `CONNECTING`.

Each `connect()` overwrites the `ws` variable but the previous socket stays alive with its handlers attached, so every message is handled once per socket: two `tts` requests, two audio streams, two transcript bubbles. `ws.onerror = () => ws.close()` closes whichever socket is *current*, not the one that errored. The server log has 22 `connection open` lines and 0 `connection closed` since the last restart.

Fix: one `connect()` that returns early if a socket is `CONNECTING` or `OPEN`, stores the reconnect timer and clears it, and closes the old socket explicitly before opening a new one. Handlers should capture their own socket (`const sock = new WebSocket(...)`) rather than reading the shared `ws`.

## 2. TTS is driven by the client, so N clients = N syntheses

Resolved 2026-09-16: `Hub.emit` assigns a `tts` id to each speak/permission event, synthesises once, and broadcasts the frames. The client-side `tts` request is gone.

`server.py:372-379` + `index.html:263-273`. Every connected page asks the server to synthesise every `speak` event by id, and the server runs them serially under `_tts_lock`. With two pages open the same sentence is synthesised twice. The server already knows what it wants spoken; synthesise once per `speak` event and broadcast the frames to all clients. This also removes `_tts_cancelled` keyed on `id(ws)` (see 3).

## 3. Fire-and-forget task and a leaky cancel set

Resolved 2026-09-16: tasks are held in `_tts_tasks`; cancel/active sets are keyed on the server-wide tts id and cleared in the job's `finally`.

`server.py:376`: `asyncio.create_task(self._tts_job(...))` keeps no reference. Python's docs warn such tasks can be garbage-collected mid-run, and any exception is silently dropped. Keep them in a set and discard on done.

`server.py:378`: `_tts_cancelled` is keyed on `(id(ws), tts_id)`. A `tts_cancel` for a job that already finished leaves its key in the set forever. `id()` values are reused after the socket is freed, so a later socket with the same id and tts counter starts already cancelled. Keying on a per-connection counter (or per-connection state object) fixes both the leak and the collision.

## 4. Same sentence-split regex in four places

Resolved 2026-09-16: `text.sentences()` is the one splitter; all four call sites use it.

`r"(?<=[.!?])\s+"` appears in `server.is_echo`, `agent.clip_spoken`, `tts.split_sentences`, and `summarizer.describe_edits`. One `sentences(text)` helper in a small `text.py`, and any future tweak (abbreviations, ellipses) lands everywhere at once.

## 5. Defaults for the same knob disagree across layers

Resolved 2026-09-16: `VadSegmenter`, `AudioPipeline` and `SpeechToText` take their tuned values with no defaults, the offline `speech.py` CLI reads `settings`, and the model env var is `VMP_SUMMARIZER_MODEL`.

| knob | `config.py` | `AudioPipeline` | `VadSegmenter` |
|---|---|---|---|
| silence ms | 2000 | 700 | 700 |
| min speech ms | 500 | 500 | 300 |
| barge-in ms | 1500 | 1500 | n/a |

Only the config value is ever used at runtime, so the inner defaults are misleading. Make the inner parameters required (no default) or make the offline `speech.py` CLI read from `settings` too. Same pattern: `summarizer.DEFAULT_MODEL` duplicates `settings.summarizer_model`, and that one reads `SUMMARIZER_MODEL` without the `VMP_` prefix the config docstring promises.

## 6. `Hub._dispatch` is a 55-line if/elif ladder

`server.py:331-392`. Fifteen branches on `msg["type"]`. A handler table (`{"ping": self._on_ping, ...}`) makes each handler independently readable and testable, and the "unknown type" case falls out of a dict lookup. The two identical "speech recognition is disabled" replies (lines 323 and 367) would collapse into one.

## 7. Hub does too many jobs

`Hub` owns session lifecycle, the work queue, WebSocket framing, the STT pipeline registry, TTS streaming, the echo guard, and the offline backlog. The echo guard (`recent_spoken` + `is_echo`, and the side effect hidden inside `emit`) and TTS streaming are the two easiest to lift into their own classes. Not urgent, but it is where the next feature will make the file hard to follow.

## 8. Summariser module is mostly dormant

Resolved 2026-09-16: `summarizer.py`, the `VMP_SUMMARIZER*` settings and the `mlx-lm` dependency are gone. `speakable` moved to `text.py`; `final_reply` and `edit_facts` had no other callers.

`summarizer.py` (237 lines, Qwen dependency, its own CLI) is off by default and the docstring still describes it as "Step 2" with the spoken reply as part 2. `agent.py` imports only `speakable` and `final_reply` from it, and discards the reply half of `compose()`. Either move `speakable`/`final_reply` into a small text-cleaning module and keep the Qwen part clearly optional, or delete the Qwen part now that Claude writes for speech.

## 9. Smaller things

- `tts.py:76` `KokoroTTS.synthesize` mutates `self.sample_rate` on every sentence. Set it once at init; the server reads it for frame headers.
- `tts.py:108` `load_tts` prints to stderr; everything else uses `logging`.
- `index.html:245` `voice.playing` is set but not declared in the `voice` initialiser at line 243.
- `index.html:231` the `vad` handler reaches into `voice.source || voice.active.size`; wrap as `isSpeaking()`.
- `index.html:369,396` `audio_start` is sent from both `micOn` and `ws.onopen`; one path via `send()`, the other raw.
- `agent.py:273,277` and `permission_detail` use bare magic numbers (300, 400, 600). Name them.
- `speech.py:32` `""` in `HALLUCINATIONS` is unreachable; the `not text` branch runs first.
- `speech.py:74,82` `no_speech_threshold=0.6` and compression ratio `2.4` are hardcoded while the neighbouring gates are configurable.
- ~~`config.py:17` comment about Eric's Mac is a personal note in shared code.~~ Reworded 2026-09-16.
- `session_log.list_sessions` opens every log file on each call; the client calls it after every turn. Fine at dozens of sessions, not at thousands. (See 11 for the bigger issue.)
- `records.to_record` and `agent._speak_outcome` match on class-name strings (`"ResultMessage"`). Works, but nothing catches a typo.

## 10. Repo hygiene

- ~~No commits yet.~~ Baseline committed 2026-09-16.
- No tests. `split_sentences`, `speakable`, `clip_spoken`, `is_echo`, and `spoken_permission` are all pure functions and cheap to cover.
- ~~`ws_client.py` sits at the root.~~ Moved to `tools/ws_client.py` 2026-09-16; `spike_sdk.py`, `fixtures/` and the `sandbox/` throwaway project are gone.

## 11. The logs folder doubles as the session store

`session_log.list_sessions` builds the Sessions panel by globbing `logs/*.jsonl` and parsing the head of each file. The log is meant as an audit trail ("read back at a desk later", per REQUIREMENTS.md), but it is now load-bearing: delete or rotate a log and the session vanishes from the picker, even though Claude Code's own transcript for it still exists under `~/.claude/projects/`. The mtime of the log is also what orders the list, so any tooling that touches those files reorders the picker. Resume itself works only because the SDK resolves the id from its own storage; the proxy just remembers the id and the cwd.

Fix: keep a small session index that the proxy owns (a `sessions.json` or one line per session in an index file, written on `session_started` and on each turn with `updated`, `cwd`, `first_prompt`). `list_sessions` reads that file only. Logs go back to being logs, can rotate freely, and the picker stops paying for a scan on every turn. A later step could cross-check the index against `~/.claude/projects/<cwd-slug>/*.jsonl` so sessions started outside the proxy show up too.

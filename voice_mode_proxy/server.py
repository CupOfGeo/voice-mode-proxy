"""FastAPI server: one WebSocket, one Claude Code session at a time.

Run:  uv run python -m voice_mode_proxy.server

WebSocket protocol, JSON messages, at /ws

  client -> server
    {"type": "user_text", "text": "..."}                     send a prompt (starts a session if none)
    {"type": "session_new", "cwd": "/optional/path"}         start a fresh session
    {"type": "session_resume", "session_id": "...", "cwd": "/optional/path"}
    {"type": "permission_response", "request_id": "...", "allow": true, "mode": "acceptEdits"|null}
                                                             mode switches the session after answering
    {"type": "permission_mode", "mode": "auto"|"default"|"acceptEdits"}
    {"type": "settings", "values": {"speech_rate": 1.2, ...}}   change any of the tunables below
    {"type": "projects_reload"}                              rescan the project folders, answered
                                                             with a "projects" event (to this client)
    {"type": "session_restart"}                              resume the current session in place
                                                             (picks up a changed voice prompt)
    {"type": "interrupt"}                                    stop the current turn (barge-in)
    {"type": "audio_start", "sample_rate": 16000}            mic opened; binary frames follow
    <binary frame>                                           16 kHz mono PCM16 mic audio
    {"type": "audio_stop"}                                   mic closed
    {"type": "tts_cancel", "id": 7}                          stop synthesising tts id 7 (barge-in)
    {"type": "playing", "on": true|false}                    page is playing our audio; gates barge-in
    {"type": "client_log", "text"}                           playback diagnostics, written to the session log
    {"type": "ping"}

  server -> client
    {"type": "vad", "speech": true|false}                    the mic stream crossed into/out of speech
    {"type": "heard", "text": "...", "seconds": 2.3}         an utterance was transcribed and queued
    <binary frame>   4-byte big-endian header length, JSON header
                     {"id", "seq", "last", "sample_rate"}, then mono PCM16 for one sentence.
                     "id" matches the "tts" field of the speak/permission_request event it voices.
    {"type": "hello", "protocol": 3, "session": {...}|null, "projects": [{"name","path"}], "pending": [...]}
                     "protocol" is PROTOCOL below; bump it with any change to this contract.
                     The app refuses a server whose number is missing or ahead of its own.
    {"type": "projects", "projects": [{"name","path"}]}      a rescan, after projects_reload
    {"type": "settings", "values": {...}, "defaults": {...}, "voices": [...]}   after hello and on change;
                     keys: speech_rate, kokoro_voice, vad_silence_ms, vad_min_speech_ms,
                     vad_barge_in_ms, voice_prompt (see tunables.py for the ranges)
    {"type": "session", "session_id", "cwd", "project", "title", "resumed_from", "model", "busy", "permission_mode"}
    {"type": "history", "items": [transcript | speak events]}   the log so far; the page redraws from it
    {"type": "status", "state": "working"|"idle"}
    {"type": "transcript", "role": "user", "text"}                  for the screen, not spoken
    {"type": "tool", "name", "target", "spoken", "detail", "tts": 6}   activity, read aloud
    {"type": "speak", "kind": "edits"|"reply"|"error"|"system", "text", "tts": 7}   read this aloud
    {"type": "permission_request", "request_id", "tool", "spoken", "detail", "tts": 8}
    {"type": "permission_resolved", "request_id", "allow"}
    {"type": "result", ...}  {"type": "turn_done"}  {"type": "error", "message"}  {"type": "pong"}

Speech is synthesised once per spoken event, on the server, and the audio frames are
broadcast to every connected client; the "tts" id ties frames to their event. While no
client is connected, speak events are buffered and replayed after the next hello, behind
a "While you were away" note. Pending permission requests are re-sent in the hello.

Auth (pairing.py): /ws and GET /sessions need a paired device's token, as
"Authorization: Bearer <token>" (the app) or the vmp_token cookie (the web page).
POST /pair {"code": "483921", "name": "George's iPhone"} trades a code from `vmp pair`
for {"token", "name"} and sets the cookie. An unpaired socket gets one
{"type": "error", "message": ...} and is closed with code 4401; /sessions answers 401.
GET / , /s/<id>, /health and POST /pair are open; /health omits "session" when unpaired.
POST /say (plain-text body) speaks into the current session; it takes the per-run token in
the X-VMP-Say-Token header, which only Claude's own shell gets (see `vmp say` in cli.py).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import platform
import re
import secrets
import shutil
import sys
from collections import deque
from collections.abc import Iterator
from difflib import SequenceMatcher
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ValidationError
from starlette.requests import HTTPConnection

from .agent import AgentSession, strip_credentials
from .config import CONFIG_FILE, ROOT, project_paths, settings
from .pairing import COOKIE_NAME, UNPAIRED_MESSAGE, Device, PairingError, PairingStore, banner, token_from
from .session_log import list_sessions, read_history
from .speech import AudioPipeline, SpeechToText
from .text import sentences
from .tts import TextToSpeech, load_tts
from .tunables import TunableStore

log = logging.getLogger("vmp")

BUFFERED_TYPES = {"speak"}


def _spoken_text(event: dict) -> str:
    """The part of an outgoing event that gets read aloud, if any."""
    if event.get("type") == "speak":
        return str(event.get("text", ""))
    if event.get("type") in {"permission_request", "tool"}:
        return str(event.get("spoken", ""))
    return ""


MAX_BACKLOG = 50
# Bump with any change to the message contract in the docstring above. The app compares
# it against the version it speaks (mobile/src/protocol.ts) and says "server too old"
# rather than misbehave. Missing (a server older than 2026-09-22) reads as 0.
PROTOCOL = 3
PERMISSION_MODES = {"auto", "default", "acceptEdits"}
WEB_INDEX = ROOT / "web" / "index.html"


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", text.lower()).strip()


def project_list() -> list[dict]:
    return [{"name": p.name, "path": str(p)} for p in project_paths() if p.is_dir()]


def resolve_project(path: str | None) -> Path | None:
    """Only directories from the configured list may host a session."""
    if not path:
        return None
    wanted = Path(path).expanduser().resolve()
    if wanted in project_paths():
        return wanted
    raise ValueError(f"{wanted} is not in the configured project list")


def _next_chunk(it: Iterator[bytes]) -> bytes | None:
    """next(it, None) with a concrete signature, so it type-checks through asyncio.to_thread."""
    return next(it, None)


class Hub:
    def __init__(self) -> None:
        self.session: AgentSession | None = None
        self.clients: set[WebSocket] = set()
        self.backlog: list[dict] = []
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.stt: SpeechToText | None = None
        self.tts: TextToSpeech | None = None
        self.audio: dict[WebSocket, AudioPipeline] = {}
        self.tunables = TunableStore()
        self.recent_spoken: deque[str] = deque(maxlen=8)  # for the echo guard
        self._tts_lock = asyncio.Lock()
        self._tts_seq = 0
        self._tts_tasks: set[asyncio.Task] = set()  # asyncio keeps only weak refs to tasks
        self._tts_active: set[int] = set()
        self._tts_cancelled: set[int] = set()
        self._worker: asyncio.Task | None = None
        self._session_lock = asyncio.Lock()
        self.say_token = secrets.token_urlsafe(32)

    # ------------------------------------------------------------------ startup / shutdown

    async def startup(self) -> None:
        removed = strip_credentials()
        if removed:
            log.info("unset %s so Claude Code uses the subscription login", ", ".join(removed))
        # Claude Code inherits this environment, so its shell can run `... | vmp say`.
        os.environ["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{os.environ.get('PATH', '')}"
        os.environ["VMP_SAY_URL"] = f"http://127.0.0.1:{settings.port}/say"
        os.environ["VMP_SAY_TOKEN"] = self.say_token
        if settings.stt_enabled:
            log.info("loading whisper %s", settings.whisper_model)
            self.stt = await asyncio.to_thread(
                SpeechToText,
                settings.whisper_model,
                min_logprob=settings.stt_min_logprob,
                max_no_speech=settings.stt_max_no_speech,
                save_audio=settings.save_audio,
                save_dir=settings.logs_dir / "audio",
            )
            log.info("whisper ready in %.1fs", self.stt.load_seconds)
        if settings.tts_enabled:
            tune = self.tunables.current
            log.info("loading Kokoro voice %s", tune.kokoro_voice)
            try:
                self.tts = await asyncio.to_thread(load_tts, settings.kokoro_dir, tune.kokoro_voice, tune.speech_rate)
                log.info("%s ready in %.1fs at %d Hz", self.tts.name, self.tts.load_seconds, self.tts.sample_rate)
            except (FileNotFoundError, ValueError) as e:
                log.warning("%s; the page will use the browser's own voices", e)
        self._worker = asyncio.create_task(self._work())

    async def shutdown(self) -> None:
        if self._worker:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
        if self.session:
            await self.session.close()

    # ------------------------------------------------------------------ events out

    async def emit(self, event: dict) -> None:
        if event.get("type") == "speak":
            self.recent_spoken.append(event.get("text", ""))
        if self.clients:
            spoken = _spoken_text(event) if self.tts else ""
            if spoken:
                event["tts"] = self._next_tts_id()
            await self._broadcast(event)
            if spoken:
                self._start_tts(event["tts"], spoken)
        elif event.get("type") in BUFFERED_TYPES:
            self.backlog.append(event)
            del self.backlog[:-MAX_BACKLOG]

    async def _broadcast(self, event: dict) -> None:
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_json(event)
            except Exception:  # noqa: BLE001 - a dropped socket must not stop the others
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def _broadcast_bytes(self, data: bytes) -> None:
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_bytes(data)
            except Exception:  # noqa: BLE001 - a dropped socket must not stop the others
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    # ------------------------------------------------------------------ sessions

    async def start_session(self, cwd: Path | None = None, resume: str | None = None) -> AgentSession:
        async with self._session_lock:
            if self.session:
                if self.session.busy:
                    raise RuntimeError("Claude is still working; interrupt first or wait")
                await self.session.close()
                self.session = None
            session = AgentSession(
                cwd=(cwd or settings.project_dir).resolve(),
                emit=self.emit,
                logs_dir=settings.logs_dir,
                resume=resume,
                claude_model=settings.claude_model,
                permission_mode=settings.permission_mode,
                max_spoken_chars=settings.max_spoken_chars,
                voice_prompt=self.tunables.current.voice_prompt,
            )
            await session.start()
            self.session = session
            await self.emit(session.info())
            await self.emit(self._history())  # redraws every page: empty for new, the log so far when resuming
            return session

    def _history(self) -> dict:
        items = read_history(self.session.log.path) if self.session else []
        return {"type": "history", "items": items}

    async def _work(self) -> None:
        """Run queued user texts one at a time."""
        while True:
            text = await self.queue.get()
            try:
                if not self.session:
                    await self.start_session()
                assert self.session
                await self.session.run_turn(text)
            except Exception as e:  # noqa: BLE001 - keep the worker alive
                log.exception("turn failed")
                await self.emit({"type": "speak", "kind": "error", "text": f"The proxy hit an error. {e}"})
            finally:
                self.queue.task_done()

    # ------------------------------------------------------------------ clients

    async def handle(self, ws: WebSocket, device: str) -> None:
        """Serve one already-accepted, already-authenticated socket until it closes."""
        self.clients.add(ws)
        log.info("client connected: %s", device)
        if self.session:
            self.session.log.write("client_connected", device=device)
        pending = [r.as_event() for r in self.session.pending.values()] if self.session else []
        if pending and self.tts:  # the first open question is spoken again on reconnect
            pending[0]["tts"] = self._next_tts_id()
        await ws.send_json(
            {
                "type": "hello",
                "protocol": PROTOCOL,
                "session": self.session.info() if self.session else None,
                "projects": project_list(),
                "stt": self.stt is not None,
                "tts": self.tts is not None,
                "pending": pending,
            }
        )
        await ws.send_json(self._settings_event())
        if self.session:
            await ws.send_json(self._history())
        if self.backlog:  # already in the history above, so replay these for the ear only
            backlog, self.backlog = self.backlog, []
            await self.emit({"type": "speak", "kind": "system", "text": "While you were away."})
            for event in backlog:
                await self.emit({**event, "replay": True})
        if pending and "tts" in pending[0]:
            self._start_tts(pending[0]["tts"], pending[0]["spoken"])
        try:
            while True:
                frame = await ws.receive()
                if frame.get("type") == "websocket.disconnect":
                    break
                if frame.get("bytes"):
                    await self._audio(ws, frame["bytes"])
                elif frame.get("text"):
                    try:
                        msg = json.loads(frame["text"])
                    except json.JSONDecodeError:
                        await ws.send_json({"type": "error", "message": "not JSON"})
                        continue
                    await self._dispatch(ws, msg)
        except WebSocketDisconnect:
            pass
        finally:
            self.clients.discard(ws)
            self.audio.pop(ws, None)
            if self.session:
                self.session.log.write("client_disconnected")

    # ------------------------------------------------------------------ speech in

    def _pipeline(self, ws: WebSocket) -> AudioPipeline | None:
        if self.stt is None:
            return None
        pipe = self.audio.get(ws)
        if pipe is None:

            async def on_text(text: str, seconds: float) -> None:
                if self.is_echo(text):
                    if self.session:
                        self.session.log.write("echo_dropped", text=text)
                    log.info("dropped echo of our own speech: %r", text)
                    return
                if self.session:
                    self.session.log.write("stt", text=text, seconds=round(seconds, 2))
                await self.emit({"type": "heard", "text": text, "seconds": round(seconds, 2)})
                await self.queue.put(text)

            async def on_speaking(speech: bool) -> None:
                await self.emit({"type": "vad", "speech": speech})

            tune = self.tunables.current
            pipe = self.audio[ws] = AudioPipeline(
                self.stt,
                on_text,
                on_speaking,
                silence_ms=tune.vad_silence_ms,
                min_speech_ms=tune.vad_min_speech_ms,
                barge_in_ms=tune.vad_barge_in_ms,
            )
        return pipe

    # ------------------------------------------------------------------ settings from the phone

    def _settings_event(self) -> dict:
        return self.tunables.event(self.tts.voices if self.tts else [])

    async def _apply_settings(self, values: dict) -> None:
        """Validate, push into the live engines, persist, then tell every client."""
        try:
            new = self.tunables.validate(values)
        except ValidationError as e:  # one line per field, readable on the phone
            raise ValueError(
                "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
            ) from None
        if self.tts:
            if new.kokoro_voice != self.tts.voice:
                self.tts.set_voice(new.kokoro_voice)  # ValueError for a voice Kokoro lacks; nothing saved
            self.tts.rate = new.speech_rate
        old = self.tunables.current
        if (new.vad_silence_ms, new.vad_min_speech_ms, new.vad_barge_in_ms) != (
            old.vad_silence_ms,
            old.vad_min_speech_ms,
            old.vad_barge_in_ms,
        ):
            for pipe in self.audio.values():
                pipe.reconfigure(new.vad_barge_in_ms, new.vad_silence_ms, new.vad_min_speech_ms)
        changed = self.tunables.commit(new)
        if changed:
            log.info("settings changed: %s", ", ".join(sorted(changed)))
            if self.session:
                self.session.log.write("settings", **changed)
        await self._broadcast(self._settings_event())

    def is_echo(self, heard: str) -> bool:
        """True if the transcript looks like the phone's speaker leaking back into its mic."""
        h = _norm(heard)
        if len(h) < 8:
            return False
        for spoken in self.recent_spoken:
            s = _norm(spoken)
            if h in s:
                return True
            # A fragment of a sentence, cut off by the VAD or garbled at the edges ("work a
            # second time since this message" out of "the mic worked a second time since
            # this message arrived"): echo if most of what was heard is one run of the speech.
            m = SequenceMatcher(None, h, s, autojunk=False).find_longest_match(0, len(h), 0, len(s))
            if m.size >= 12 and m.size >= 0.7 * len(h):
                return True
            for sentence in sentences(spoken):
                if len(sentence) > 8 and SequenceMatcher(None, h, _norm(sentence)).ratio() > 0.8:
                    return True
        return False

    # ------------------------------------------------------------------ speech out

    def _next_tts_id(self) -> int:
        self._tts_seq += 1
        return self._tts_seq

    def _start_tts(self, tts_id: int, text: str) -> None:
        self._tts_active.add(tts_id)
        task = asyncio.create_task(self._tts_job(tts_id, text))
        self._tts_tasks.add(task)
        task.add_done_callback(self._tts_tasks.discard)

    async def _tts_job(self, tts_id: int, text: str) -> None:
        """Synthesise sentence by sentence; each sentence is broadcast as soon as it exists."""
        assert self.tts
        log.info("tts #%d: %d chars", tts_id, len(text))
        try:
            async with self._tts_lock:  # one synthesis at a time keeps sentence order and the CPU sane
                it = self.tts.synthesize(text)
                seq = 0
                pending = await asyncio.to_thread(_next_chunk, it)
                while pending is not None:
                    if tts_id in self._tts_cancelled or not self.clients:
                        log.info("tts #%d: stopped after %d sentence(s)", tts_id, seq)
                        break
                    nxt = await asyncio.to_thread(_next_chunk, it)
                    header = json.dumps(
                        {"id": tts_id, "seq": seq, "last": nxt is None, "sample_rate": self.tts.sample_rate}
                    ).encode()
                    await self._broadcast_bytes(len(header).to_bytes(4, "big") + header + pending)
                    seq += 1
                    pending = nxt
                else:
                    log.info("tts #%d: sent %d sentence(s)", tts_id, seq)
        except Exception:  # noqa: BLE001 - a bad sentence must not take the server down
            log.exception("tts #%d failed", tts_id)
        finally:
            self._tts_active.discard(tts_id)
            self._tts_cancelled.discard(tts_id)

    async def _audio(self, ws: WebSocket, data: bytes) -> None:
        pipe = self._pipeline(ws)
        if pipe is None:
            await ws.send_json({"type": "error", "message": "speech recognition is disabled on the server"})
            return
        try:
            await pipe.feed(data)
        except Exception as e:  # noqa: BLE001 - a bad frame must not kill the socket
            log.exception("audio frame failed")
            await ws.send_json({"type": "error", "message": f"audio: {type(e).__name__}: {e}"})

    async def _dispatch(self, ws: WebSocket, msg: dict) -> None:
        kind = msg.get("type")
        try:
            if kind == "ping":
                await ws.send_json({"type": "pong"})
            elif kind == "user_text":
                text = (msg.get("text") or "").strip()
                if text:
                    await self.queue.put(text)
            elif kind == "session_new":
                await self.start_session(cwd=resolve_project(msg.get("cwd")))
            elif kind == "session_resume":
                wanted = str(msg.get("session_id", ""))
                if self.session and self.session.session_id == wanted:
                    await ws.send_json(self.session.info())  # already there (a page refresh or a second device)
                    return
                known = next(
                    (s for s in list_sessions(settings.logs_dir, limit=500) if s["session_id"] == wanted), None
                )
                if known is None:
                    await ws.send_json({"type": "error", "message": f"no session {wanted[:8]} on this server"})
                    return
                cwd = resolve_project(msg.get("cwd")) or (Path(known["cwd"]) if known.get("cwd") else None)
                await self.start_session(cwd=cwd, resume=wanted)
            elif kind == "permission_response":
                ok = bool(self.session and self.session.answer_permission(msg["request_id"], bool(msg.get("allow"))))
                if not ok:
                    await ws.send_json({"type": "error", "message": "no such pending permission request"})
                elif msg.get("mode") in PERMISSION_MODES and self.session:
                    await self.session.set_permission_mode(msg["mode"])
            elif kind == "permission_mode":
                if msg.get("mode") not in PERMISSION_MODES:
                    raise ValueError(f"mode must be one of {sorted(PERMISSION_MODES)}")
                if self.session:
                    await self.session.set_permission_mode(msg["mode"])
            elif kind == "settings":
                values = msg.get("values")
                if not isinstance(values, dict):
                    raise ValueError("settings needs a values object")
                await self._apply_settings(values)
            elif kind == "session_restart":
                if self.session:
                    await self.start_session(cwd=self.session.cwd, resume=self.session.session_id)
                else:
                    await ws.send_json({"type": "error", "message": "no session to restart"})
            elif kind == "projects_reload":  # rescan the folders; a repo cloned since startup appears
                await ws.send_json({"type": "projects", "projects": project_list()})
            elif kind == "interrupt":
                if self.session:
                    await self.session.interrupt()
            elif kind == "audio_start":
                if msg.get("sample_rate", 16000) != 16000:
                    raise ValueError("audio must be 16 kHz mono PCM16")
                pipe = self._pipeline(ws)
                if pipe is None:
                    await ws.send_json({"type": "error", "message": "speech recognition is disabled on the server"})
                else:
                    pipe.reset()
            elif kind == "audio_stop":
                self.audio.pop(ws, None)
            elif kind == "tts_cancel":
                tts_id = int(msg["id"])
                if tts_id in self._tts_active:  # a stale cancel for a finished job is a no-op
                    self._tts_cancelled.add(tts_id)
                    log.info("tts #%d cancelled by client", tts_id)
            elif kind == "client_log":
                log.info("client: %s", msg.get("text", ""))
                if self.session:
                    self.session.log.write("client", text=str(msg.get("text", "")))
            elif kind == "playing":
                pipe = self.audio.get(ws)
                if pipe:
                    pipe.playing = bool(msg.get("on"))
            else:
                await ws.send_json({"type": "error", "message": f"unknown message type {kind!r}"})
        except Exception as e:  # noqa: BLE001 - report to the client, keep the socket open
            log.exception("dispatch failed")
            await ws.send_json({"type": "error", "message": f"{type(e).__name__}: {e}"})


hub = Hub()


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    await hub.startup()
    try:
        yield
    finally:
        await hub.shutdown()


app = FastAPI(title="Voice Mode Proxy", lifespan=lifespan)


@app.get("/")
@app.get("/s/{session_id}")
async def index(session_id: str | None = None) -> FileResponse:
    """The page; /s/<id> is the same page, which then rejoins that session (see the hello handler)."""
    return FileResponse(WEB_INDEX, headers={"Cache-Control": "no-store"})


auth = PairingStore()


def _device(conn: HTTPConnection) -> Device | None:
    """The paired device behind a request or socket, by bearer header or cookie."""
    return auth.device_for(token_from(conn.headers, conn.cookies))


def _is_https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https"


class PairRequest(BaseModel):
    code: str
    name: str = "Device"


@app.get("/health")
async def health(request: Request) -> dict:
    info = {
        "ok": True,
        "protocol": PROTOCOL,
        "clients": len(hub.clients),
        "whisper": hub.stt.model if hub.stt else None,
        "tts": hub.tts.name if hub.tts else None,
    }
    if _device(request) is not None:  # the session's project path is for paired devices only
        info["session"] = hub.session.info() if hub.session else None
    return info


@app.post("/pair")
async def pair(body: PairRequest, request: Request) -> JSONResponse:
    where = request.client.host if request.client else "?"
    try:
        token, device = auth.redeem(body.code, body.name)
    except PairingError as e:
        log.warning("pairing refused from %s: %s", where, e)
        return JSONResponse({"error": str(e)}, status_code=401)
    log.info("paired %r from %s", device.name, where)
    resp = JSONResponse({"token": token, "name": device.name})
    resp.set_cookie(
        COOKIE_NAME, token, httponly=True, samesite="lax", secure=_is_https(request), max_age=400 * 24 * 3600, path="/"
    )
    return resp


@app.get("/sessions", response_model=None)
async def sessions(request: Request) -> list[dict] | JSONResponse:
    if _device(request) is None:
        return JSONResponse({"error": UNPAIRED_MESSAGE}, status_code=401)
    return list_sessions(settings.logs_dir)


@app.post("/say")
async def say(request: Request) -> JSONResponse:
    if not secrets.compare_digest(request.headers.get("x-vmp-say-token", ""), hub.say_token):
        return JSONResponse({"error": "bad or missing say token"}, status_code=401)
    if hub.session is None:
        return JSONResponse({"error": "no voice session is running"}, status_code=409)
    # ponytail: no length cap; barge-in stops a long read, add a cap if `cat` of huge files bites
    words = await hub.session.say_aloud((await request.body()).decode(errors="replace"))
    return JSONResponse({"words": words})


@app.websocket("/ws")
async def websocket(ws: WebSocket) -> None:
    await ws.accept()
    device = _device(ws)
    if device is None:
        await ws.send_json({"type": "error", "message": UNPAIRED_MESSAGE})
        await ws.close(code=4401)
        return
    auth.touch(device)
    await hub.handle(ws, device.name)


def preflight() -> list[str]:
    """What would make startup fail or the first session fail, as plain sentences."""
    problems = []
    if shutil.which("claude") is None:
        problems.append(
            "Claude Code is not installed (no `claude` on PATH). The proxy drives it. Install with\n"
            "    curl -fsSL https://claude.ai/install.sh | bash\n"
            "then run `claude` once to log in."
        )
    if settings.stt_enabled and platform.machine() != "arm64":
        problems.append(
            "Speech recognition (mlx-whisper) needs Apple Silicon. Set stt_enabled = false in the config "
            "file to run with typed input only."
        )
    if settings.tts_enabled:
        missing = [f for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin") if not (settings.kokoro_dir / f).is_file()]
        if missing:
            problems.append(
                f"Kokoro voice files missing in {settings.kokoro_dir}: {', '.join(missing)}. Run ./install.sh, "
                "or download them from https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0 "
                "into that folder. Set tts_enabled = false in the config file to run without a server voice."
            )
    if settings.host not in ("127.0.0.1", "localhost", "::1"):
        log.warning(
            "host = %s: the proxy is on the network in plain HTTP. The pairing token, codes and your audio "
            "cross that network unencrypted, and anyone on it can try to pair. Only do this on a home network "
            "you trust. 127.0.0.1 behind Tailscale Serve is encrypted and reachable only from your own devices.",
            settings.host,
        )
    return problems


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if problems := preflight():
        print("Voice Mode Proxy cannot start:\n", file=sys.stderr)
        for p in problems:
            print(f"  * {p}\n", file=sys.stderr)
        sys.exit(1)
    log.info("config file %s%s", CONFIG_FILE, "" if CONFIG_FILE.is_file() else " (absent; using defaults)")
    if not auth.devices():  # first start: nothing can talk to us yet
        if sys.stderr.isatty():
            print(banner(auth.new_code()), file=sys.stderr)
        else:  # launchd: stderr is the log file, where a code would only get buried
            log.info("no devices paired yet; run `vmp pair` for a code")
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()

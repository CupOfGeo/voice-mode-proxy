"""Typed remote control for the server, for testing step 3 without a browser.

  uv run tools/ws_client.py -p "what is this project?"
  uv run tools/ws_client.py --resume <session_id> -p "and now?"
  uv run tools/ws_client.py --cwd /path/to/repo -p "..." --allow   # auto-allow permissions
  uv run tools/ws_client.py --listen                                # just watch events

The server only talks to paired devices: pass --token, or set VMP_TOKEN, with the token
from a POST /pair (see the "Pair your phone" section of the README).
Permission requests are answered from stdin unless --allow / --deny is given.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import websockets

try:  # trust the macOS keychain for wss:// through Tailscale Serve
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass


async def stream_wavs(ws, paths: list[Path]) -> None:
    """Send WAVs as the browser would: 100 ms PCM16 frames in real time, silence between."""
    import wave

    frame = 16_000 // 10 * 2
    await ws.send(json.dumps({"type": "audio_start", "sample_rate": 16_000}))
    for p in paths:
        with wave.open(str(p), "rb") as w:
            pcm = w.readframes(w.getnframes())
        pcm += bytes(16_000 * 2 * 2)  # 2 s of silence closes the utterance
        print(f"  🎤 streaming {p.name} ({len(pcm) / 2 / 16_000:.1f}s)")
        for i in range(0, len(pcm), frame):
            await ws.send(pcm[i : i + frame])
            await asyncio.sleep(0.1)
    await ws.send(json.dumps({"type": "audio_stop"}))


def show(ev: dict) -> None:
    t = ev.get("type")
    if t == "heard":
        print(f"\n🎤 heard ({ev.get('seconds', 0):.1f}s): {ev['text']}")
    elif t == "vad":
        print(f"  {'vad':>9}: {'speech' if ev['speech'] else 'silence'}")
    elif t == "speak":
        print(f"\n🔊 [{ev['kind']}] {ev['text']}\n")
    elif t == "transcript":
        print(f"  {ev['role']:>9}: {ev['text'][:200]}")
    elif t == "tool":
        print(f"  {'tool':>9}: {ev['name']} {ev['target']}")
        print(f"  {'':>9}  🔊 {ev.get('spoken')} [tts {ev.get('tts')}]  detail {json.dumps(ev.get('detail'))[:160]}")
    elif t == "permission_request":
        print(f"\n🛑 PERMISSION {ev['request_id']}: {ev['spoken']}\n   {json.dumps(ev['detail'])[:300]}")
    elif t == "hello":
        print(f"hello: protocol={ev.get('protocol')} session={ev.get('session')} pending={len(ev['pending'])}")
        for item in ev["pending"]:
            show(item)
    elif t in {"status", "turn_done", "pong", "permission_resolved", "result"}:
        print(f"  {t}: {json.dumps({k: v for k, v in ev.items() if k != 'type'})}")
    else:
        print(f"  {t}: {json.dumps(ev)[:300]}")


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--prompt")
    ap.add_argument("--url", default="ws://127.0.0.1:8791/ws")
    ap.add_argument("--token", default=os.environ.get("VMP_TOKEN"), help="pairing token (default: $VMP_TOKEN)")
    ap.add_argument("--cwd", type=Path, help="start a new session in this directory")
    ap.add_argument("--resume", help="resume this session id")
    ap.add_argument("--listen", action="store_true", help="stay connected and print events")
    ap.add_argument(
        "--leave-after", type=float, metavar="SECONDS", help="disconnect after this long (simulates the phone dropping)"
    )
    ap.add_argument(
        "--wav", type=Path, action="append", help="stream this 16 kHz mono PCM16 WAV as mic audio (repeatable)"
    )
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--allow", action="store_true")
    grp.add_argument("--deny", action="store_true")
    grp.add_argument(
        "--allow-edits", action="store_true", help="allow the first request and switch the session to acceptEdits"
    )
    args = ap.parse_args()

    headers = {"Authorization": f"Bearer {args.token}"} if args.token else None
    async with websockets.connect(args.url, max_size=None, additional_headers=headers) as ws:
        if args.resume:
            await ws.send(
                json.dumps(
                    {
                        "type": "session_resume",
                        "session_id": args.resume,
                        "cwd": str(args.cwd.resolve()) if args.cwd else None,
                    }
                )
            )
        elif args.cwd:
            await ws.send(json.dumps({"type": "session_new", "cwd": str(args.cwd.resolve())}))
        if args.prompt:
            await ws.send(json.dumps({"type": "user_text", "text": args.prompt}))

        streamer = asyncio.create_task(stream_wavs(ws, args.wav)) if args.wav else None
        expect_turns = len(args.wav or []) + (1 if args.prompt else 0)
        deadline = asyncio.get_running_loop().time() + args.leave_after if args.leave_after else None
        while True:
            try:
                remaining = None if deadline is None else max(0.0, deadline - asyncio.get_running_loop().time())
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                print(f"(leaving after {args.leave_after}s)")
                break
            except websockets.ConnectionClosed as e:
                code = e.rcvd.code if e.rcvd else None
                print(f"(connection closed, code {code})" + (": not paired; pass --token" if code == 4401 else ""))
                break
            if isinstance(raw, (bytes, bytearray)):
                hlen = int.from_bytes(raw[:4], "big")
                header = json.loads(raw[4 : 4 + hlen])
                pcm = bytes(raw[4 + hlen :])
                print(
                    f"  {'audio':>9}: id={header['id']} seq={header['seq']} {len(pcm) / 2 / header['sample_rate']:.2f}s last={header['last']}"
                )
                continue
            ev = json.loads(raw)
            show(ev)
            pending = (
                [ev]
                if ev.get("type") == "permission_request"
                else ev.get("pending", [])
                if ev.get("type") == "hello"
                else []
            )
            for req in pending:
                mode = None
                if args.allow or args.deny:
                    allow = args.allow
                    print(f"   -> {'allow' if allow else 'deny'} (flag)")
                elif args.allow_edits:
                    allow, mode = True, "acceptEdits"
                    print("   -> allow + acceptEdits for the session (flag)")
                else:
                    try:
                        answer = await asyncio.to_thread(input, "   allow? [y/N] ")
                    except EOFError:
                        answer = ""
                    allow = answer.strip().lower() in {"y", "yes"}
                await ws.send(
                    json.dumps(
                        {"type": "permission_response", "request_id": req["request_id"], "allow": allow, "mode": mode}
                    )
                )
            if ev.get("type") == "turn_done" and expect_turns and not args.listen:
                expect_turns -= 1
                if expect_turns == 0:
                    break
            if ev.get("type") == "error" and not args.listen:
                print("error from server:", ev.get("message"))
                if not args.prompt:
                    break
        if streamer and not streamer.done():
            streamer.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)

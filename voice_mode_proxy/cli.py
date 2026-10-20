"""The `vmp` command.

vmp               run the server in this terminal (python -m voice_mode_proxy.server does the same)
vmp start         run it under launchd instead: stays up across crashes and logins
vmp stop          stop the launchd job
vmp restart       stop and start (after a git pull, or a changed config or environment)
vmp status        is it up, and what /health says
vmp logs          follow logs/server.log
vmp pair          print a one-time pairing code for the app or the web page
vmp devices       list paired devices
vmp revoke NAME   forget a paired device; takes effect without a restart
cmd | vmp say     speak stdin to the phone; only works from Claude's shell inside a voice session
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="vmp", description="Voice Mode Proxy. With no subcommand, runs the server here.")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("start", help="run the server under launchd (installs the agent on first use)")
    sub.add_parser("stop", help="stop the launchd job")
    sub.add_parser("restart", help="stop and start; picks up code, config and environment changes")
    sub.add_parser("status", help="whether the server is up, and what /health says")
    sub.add_parser("logs", help="follow logs/server.log").add_argument(
        "-n", type=int, default=50, help="lines of history"
    )
    sub.add_parser("pair", help="print a one-time pairing code (valid 5 minutes, 5 tries)")
    sub.add_parser("devices", help="list paired devices")
    sub.add_parser("revoke", help="forget a paired device").add_argument("name")
    sub.add_parser("say", help="speak stdin in the current voice session (for Claude's shell)")
    args = ap.parse_args(argv)

    if args.cmd is None:
        from .server import main as serve  # lazy: the other subcommands must not load fastapi or the SDK

        serve()
        return

    if args.cmd in ("start", "stop", "restart", "status", "logs"):
        from . import service

        if args.cmd == "logs":
            sys.exit(service.logs(args.n))
        sys.exit(getattr(service, args.cmd)())

    if args.cmd == "say":
        sys.exit(say(sys.stdin.read()))

    from .pairing import PairingStore, banner

    store = PairingStore()
    if args.cmd == "pair":
        print(banner(store.new_code()))
    elif args.cmd == "devices":
        devices = store.devices()
        if not devices:
            print("No paired devices. Run `vmp pair` and enter the code in the app.")
            return
        width = max(len(d.name) for d in devices)
        print(f"{'name':<{width}}  {'paired':<25}  last seen")
        for d in devices:
            print(f"{d.name:<{width}}  {d.created:<25}  {d.last_seen or 'never'}")
    elif args.cmd == "revoke":
        if store.revoke(args.name):
            print(f"Revoked {args.name!r}. It can pair again with a new code.")
        else:
            print(f"No device named {args.name!r}; `vmp devices` lists them.", file=sys.stderr)
            sys.exit(1)


def say(text: str) -> int:
    """POST text to the server that started this shell's Claude; print only the word count,
    so the text never lands in Claude's context."""
    url, token = os.environ.get("VMP_SAY_URL"), os.environ.get("VMP_SAY_TOKEN")
    if not url or not token:
        print("vmp say only works from Claude's shell inside a voice session.", file=sys.stderr)
        return 1
    req = urllib.request.Request(
        url, data=text.encode(), headers={"X-VMP-Say-Token": token, "Content-Type": "text/plain"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"spoke {json.load(resp)['words']} words")
            return 0
    except urllib.error.HTTPError as e:
        print(f"vmp say failed: {json.load(e).get('error', e.reason)}", file=sys.stderr)
    except OSError as e:
        print(f"vmp say could not reach the server: {e}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    main()

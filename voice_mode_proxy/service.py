"""`vmp start|stop|restart|status|logs`: the server as a launchd user agent.

`vmp start` writes ~/Library/LaunchAgents/net.mainbranch.voice-mode-proxy.plist from the
current environment (this venv's Python, the config file, PATH so `claude` is found, any
VMP_* and ANTHROPIC_* variables except the API key) and hands it to launchd. launchd keeps
the proxy up across crashes and logins, and writes stdout and stderr to logs/server.log.
`restart` rewrites the plist too, so a changed environment or a `git pull` takes effect.
`stop` unloads it; it stays unloaded until the next `start`.

Nothing here imports server.py: these commands must stay light.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path

from .config import CONFIG_FILE, ROOT, settings

LABEL = "net.mainbranch.voice-mode-proxy"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG = settings.logs_dir / "server.log"

# Environment the server needs and launchd does not provide (its default PATH lacks
# ~/.local/bin and Homebrew, where `claude` and `uv` live). The API key is left out on
# purpose: it would override the Claude Code login (agent.py strips it too).
_KEEP_PREFIXES = ("VMP_", "ANTHROPIC_")
_KEEP_EXACT = ("PATH", "HOME", "USER", "LANG", "TMPDIR")
_DROP = {"ANTHROPIC_API_KEY", "VMP_SAY_URL", "VMP_SAY_TOKEN"}  # the say pair is per server run


def domain() -> str:
    return f"gui/{os.getuid()}"


def plist_dict(env: dict[str, str] | None = None) -> dict:
    """The launchd job: this venv's Python running the server module in the repo root."""
    src = os.environ if env is None else env
    keep = {k: v for k, v in src.items() if (k in _KEEP_EXACT or k.startswith(_KEEP_PREFIXES)) and k not in _DROP and v}
    keep.setdefault("VMP_CONFIG", str(CONFIG_FILE))
    return {
        "Label": LABEL,
        "ProgramArguments": [sys.executable, "-m", "voice_mode_proxy.server"],
        "WorkingDirectory": str(ROOT),
        "EnvironmentVariables": keep,
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,  # seconds between relaunches if it keeps dying
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
        "ProcessType": "Interactive",  # no App Nap throttling while the proxy is busy
    }


def write_plist(path: Path = PLIST, env: dict[str, str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        plistlib.dump(plist_dict(env), f)
    return path


def _launchctl(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, check=check)


def loaded() -> bool:
    return _launchctl("print", f"{domain()}/{LABEL}").returncode == 0


def _bootout() -> subprocess.CompletedProcess[str]:
    """bootout returns before launchd has torn the job down; bootstrapping the label again
    meanwhile fails with "5: Input/output error". Wait until it is gone (the server's own
    shutdown can take several seconds)."""
    r = _launchctl("bootout", f"{domain()}/{LABEL}")
    for _ in range(100):
        if not loaded():
            break
        time.sleep(0.2)
    return r


def job_pid() -> int | None:
    out = _launchctl("print", f"{domain()}/{LABEL}").stdout
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("pid = "):
            try:
                return int(line[6:])
            except ValueError:
                return None
    return None


def port_owner(port: int = settings.port) -> int | None:
    """PID listening on the port, whoever started it; None when free."""
    r = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"], capture_output=True, text=True)
    pids = [int(p) for p in r.stdout.split() if p.isdigit()]
    return pids[0] if pids else None


def start() -> int:
    """Install (or refresh) the agent and start it. Returns an exit code."""
    other = port_owner()
    if other is not None and other != job_pid():
        print(
            f"Port {settings.port} is already in use by pid {other}, which launchd did not start "
            f"(a `uv run vmp` from a terminal?). Stop it first:\n    kill {other}\nthen run `vmp start` again.",
            file=sys.stderr,
        )
        return 1
    from .server import preflight  # heavy import, only here: fail now with words, not in a launchd loop

    if problems := preflight():
        print("Voice Mode Proxy cannot start:\n", file=sys.stderr)
        for p in problems:
            print(f"  * {p}\n", file=sys.stderr)
        return 1
    if loaded():
        _bootout()
    write_plist()
    r = _launchctl("bootstrap", domain(), str(PLIST))
    if r.returncode != 0:
        print(f"launchctl bootstrap failed: {r.stderr.strip() or r.stdout.strip()}", file=sys.stderr)
        return 1
    print(f"Started. Logs: {LOG}\n`vmp status` shows whether it is up; `vmp logs` follows the log.")
    from .pairing import PairingStore, banner

    store = PairingStore()
    if not store.devices():
        print("\nNo phone is paired yet. Give the server a few seconds to load the voice, then enter this code:")
        print(banner(store.new_code()))
    return 0


def stop() -> int:
    if not loaded():
        print("Not running under launchd (nothing to stop).")
        return 0
    r = _bootout()
    if r.returncode != 0:
        print(f"launchctl bootout failed: {r.stderr.strip() or r.stdout.strip()}", file=sys.stderr)
        return 1
    print("Stopped. It stays stopped until `vmp start`.")
    return 0


def _inside_job() -> bool:
    """True when this process descends from the launchd job, e.g. a voice session's agent ran `vmp restart`.
    launchd sets XPC_SERVICE_NAME to the job's label and every child inherits it."""
    return os.environ.get("XPC_SERVICE_NAME") == LABEL


def restart() -> int:
    """Stop, rewrite the plist from the current environment, start. Sessions on the phone resume."""
    # bootout kills everything in the job, so a restart run from inside it would die before
    # start(). Rerun it in its own session (out of the job's process group) and return.
    if not os.environ.pop("_VMP_DETACHED", None) and _inside_job():
        with LOG.open("a") as log:
            subprocess.Popen(
                [sys.executable, "-m", "voice_mode_proxy.cli", "restart"],
                env={**os.environ, "_VMP_DETACHED": "1"},
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        print(f"Restarting in the background; the connection drops for a few seconds. Logs: {LOG}")
        return 0
    if loaded():
        _bootout()
    return start()


def status() -> int:
    pid = job_pid() if loaded() else None
    owner = port_owner()
    if pid:
        print(f"launchd: running, pid {pid}")
    elif PLIST.exists():
        print("launchd: installed but not running (`vmp start`)")
    else:
        print("launchd: not installed (`vmp start` installs it)")
    if owner and owner != pid:
        print(f"port {settings.port}: pid {owner} is listening, started outside launchd")
    elif owner:
        print(f"port {settings.port}: listening")
    else:
        print(f"port {settings.port}: nothing listening")
        return 1
    try:
        import json
        import urllib.request

        with urllib.request.urlopen(f"http://127.0.0.1:{settings.port}/health", timeout=3) as resp:
            h = json.load(resp)
        print(
            f"health: ok, protocol {h.get('protocol')}, {h.get('clients', 0)} client(s), "
            f"whisper {h.get('whisper') or 'off'}, voice {h.get('tts') or 'off'}"
        )
    except Exception as e:  # noqa: BLE001 - any failure here is "not healthy", said in one line
        print(f"health: no answer ({e})")
        return 1
    return 0


def logs(lines: int = 50) -> int:
    """Follow the log; exec so Ctrl-C ends cleanly. Only returns when there is no log."""
    if not LOG.exists():
        print(f"No log yet at {LOG}.")
        return 1
    os.execvp("tail", ["tail", "-n", str(lines), "-f", str(LOG)])

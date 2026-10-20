"""Device pairing: a short code from the Mac becomes a long token on the phone.

The code is the handshake, the token is the credential. `vmp pair` (or the server, on a
first start with nothing paired) writes a six-digit code to pairing.json next to
config.toml; it lasts five minutes and five wrong tries. POST /pair trades it for a
random token. Only the token's sha256 is kept, in devices.json with the device's name,
and every /ws and /sessions request must carry the token (Authorization: Bearer for the
app, the vmp_token cookie for the web page). devices.json is re-read on every check, so
`vmp revoke` takes effect without a restart.

This module imports only config.py: `vmp pair` must stay light, and the tests run it
without a server.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from .config import CONFIG_FILE

PAIRING_FILE = CONFIG_FILE.with_name("pairing.json")
DEVICES_FILE = CONFIG_FILE.with_name("devices.json")
CODE_TTL_SECONDS = 300
MAX_ATTEMPTS = 5
COOKIE_NAME = "vmp_token"
UNPAIRED_MESSAGE = "This device is not paired with the server. Run `vmp pair` on the Mac and enter the code."


class PairingError(Exception):
    """The message is plain English, safe to show the person typing the code."""


@dataclass(frozen=True)
class Device:
    name: str
    token_sha256: str
    created: str  # ISO 8601, UTC
    last_seen: str | None = None


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def write_private(path: Path, data: object) -> None:
    """Write JSON readable by this user only, atomically (temp file, then rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as f:
            os.fchmod(fd, 0o600)
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_json(path: Path) -> object | None:
    """The file's JSON, or None when it is missing or unreadable."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def token_from(headers: Mapping[str, str], cookies: Mapping[str, str]) -> str | None:
    """The bearer token from the Authorization header, else the cookie, else None."""
    auth = headers.get("authorization", "")
    scheme, _, value = auth.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return cookies.get(COOKIE_NAME) or None


def banner(code: str) -> str:
    return (
        f"\nPairing code:  {code[:3]} {code[3:]}\n\n"
        "Enter it in the app (Settings, or the Pair screen) within 5 minutes. The server must be\n"
        "running for the phone to pair. A newer code replaces this one.\n"
    )


class PairingStore:
    def __init__(self, pairing_file: Path = PAIRING_FILE, devices_file: Path = DEVICES_FILE) -> None:
        self.pairing_file = pairing_file
        self.devices_file = devices_file

    # ------------------------------------------------------------------ the code

    def new_code(self) -> str:
        code = f"{secrets.randbelow(10**6):06d}"
        write_private(
            self.pairing_file,
            {"code_sha256": sha256(code), "expires": time.time() + CODE_TTL_SECONDS, "attempts": 0},
        )
        return code

    def pending(self) -> dict | None:
        """The live code record, or None (and no file) when there is none or it has lapsed."""
        rec = read_json(self.pairing_file)
        if not isinstance(rec, dict) or not isinstance(rec.get("code_sha256"), str):
            self.pairing_file.unlink(missing_ok=True)
            return None
        if time.time() > float(rec.get("expires", 0)) or int(rec.get("attempts", 0)) >= MAX_ATTEMPTS:
            self.pairing_file.unlink(missing_ok=True)
            return None
        return rec

    def redeem(self, code: str, name: str) -> tuple[str, Device]:
        """Trade a correct code for a new token; raises PairingError otherwise."""
        rec = read_json(self.pairing_file)
        if not isinstance(rec, dict):
            raise PairingError("No pairing code is active. Run `vmp pair` on the Mac.")
        if time.time() > float(rec.get("expires", 0)):
            self.pairing_file.unlink(missing_ok=True)
            raise PairingError("The code has expired. Run `vmp pair` again.")
        digits = "".join(ch for ch in code if ch.isdigit())
        if not hmac.compare_digest(sha256(digits), str(rec.get("code_sha256", ""))):
            attempts = int(rec.get("attempts", 0)) + 1
            if attempts >= MAX_ATTEMPTS:
                self.pairing_file.unlink(missing_ok=True)
                raise PairingError("Too many wrong codes. Run `vmp pair` again for a fresh one.")
            write_private(self.pairing_file, {**rec, "attempts": attempts})
            left = MAX_ATTEMPTS - attempts
            raise PairingError(f"Wrong code. {left} {'try' if left == 1 else 'tries'} left.")
        self.pairing_file.unlink(missing_ok=True)
        token = secrets.token_urlsafe(32)
        device = Device(name=self._unique_name(name), token_sha256=sha256(token), created=_now())
        self._write_devices([*self.devices(), device])
        return token, device

    # ------------------------------------------------------------------ devices

    def devices(self) -> list[Device]:
        """Re-read every time: the file is tiny and `vmp revoke` edits it from another process."""
        data = read_json(self.devices_file)
        if not isinstance(data, list):
            return []
        out = []
        for item in data:
            if (
                isinstance(item, dict)
                and isinstance(item.get("name"), str)
                and isinstance(item.get("token_sha256"), str)
            ):
                out.append(
                    Device(
                        name=item["name"],
                        token_sha256=item["token_sha256"],
                        created=str(item.get("created", "")),
                        last_seen=item.get("last_seen"),
                    )
                )
        return out

    def device_for(self, token: str | None) -> Device | None:
        if not token:
            return None
        digest = sha256(token)
        found = None
        for d in self.devices():  # compare every entry so timing does not tell which one matched
            if hmac.compare_digest(digest, d.token_sha256):
                found = d
        return found

    def touch(self, device: Device) -> None:
        now = _now()
        self._write_devices(
            [replace(d, last_seen=now) if d.token_sha256 == device.token_sha256 else d for d in self.devices()]
        )

    def revoke(self, name: str) -> bool:
        before = self.devices()
        after = [d for d in before if d.name != name]
        if len(after) == len(before):
            return False
        self._write_devices(after)
        return True

    def _unique_name(self, name: str) -> str:
        base = " ".join(name.split())[:60] or "Device"
        taken = {d.name for d in self.devices()}
        candidate, n = base, 2
        while candidate in taken:
            candidate = f"{base} {n}"
            n += 1
        return candidate

    def _write_devices(self, devices: list[Device]) -> None:
        if devices:
            write_private(self.devices_file, [asdict(d) for d in devices])
        else:
            self.devices_file.unlink(missing_ok=True)

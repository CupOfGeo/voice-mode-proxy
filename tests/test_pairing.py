"""The pairing store on its own: codes, tokens, devices, files."""

import json
import re
import time

import pytest

from voice_mode_proxy import pairing
from voice_mode_proxy.pairing import MAX_ATTEMPTS, PairingError, PairingStore, sha256, token_from


@pytest.fixture
def store(tmp_path):
    return PairingStore(tmp_path / "pairing.json", tmp_path / "devices.json")


def test_new_code_is_six_digits_in_a_private_file(store):
    code = store.new_code()
    assert re.fullmatch(r"\d{6}", code)
    assert store.pairing_file.stat().st_mode & 0o777 == 0o600
    assert store.pending() is not None
    assert code not in store.pairing_file.read_text()  # only the hash is written


def test_redeem_right_code_pairs_a_device(store):
    code = store.new_code()
    token, device = store.redeem(code, "iPhone")
    assert len(token) >= 40
    assert device.name == "iPhone"
    assert not store.pairing_file.exists()
    assert store.devices_file.stat().st_mode & 0o777 == 0o600
    assert store.devices()[0].token_sha256 == sha256(token)
    assert token not in store.devices_file.read_text()
    assert store.device_for(token) == store.devices()[0]
    assert store.device_for("nope") is None
    assert store.device_for(None) is None
    assert store.device_for("") is None


def test_spaces_in_the_code_are_ignored(store):
    code = store.new_code()
    token, _ = store.redeem(f"{code[:3]} {code[3:]}", "Browser")
    assert store.device_for(token)


def test_no_code_active(store):
    with pytest.raises(PairingError, match="No pairing code"):
        store.redeem("123456", "x")


def test_five_wrong_tries_burn_the_code(store):
    code = store.new_code()
    wrong = f"{(int(code) + 1) % 10**6:06d}"
    for i in range(MAX_ATTEMPTS - 1):
        with pytest.raises(PairingError, match=rf"Wrong code\. {MAX_ATTEMPTS - 1 - i} tr"):
            store.redeem(wrong, "x")
    with pytest.raises(PairingError, match="Too many"):
        store.redeem(wrong, "x")
    assert not store.pairing_file.exists()
    with pytest.raises(PairingError, match="No pairing code"):
        store.redeem(code, "x")
    assert store.devices() == []


def test_expired_code(store, monkeypatch):
    code = store.new_code()
    later = time.time() + pairing.CODE_TTL_SECONDS + 1
    monkeypatch.setattr(pairing.time, "time", lambda: later)
    with pytest.raises(PairingError, match="expired"):
        store.redeem(code, "x")
    assert not store.pairing_file.exists()


def test_pending_drops_an_expired_code(store, monkeypatch):
    store.new_code()
    later = time.time() + pairing.CODE_TTL_SECONDS + 1
    monkeypatch.setattr(pairing.time, "time", lambda: later)
    assert store.pending() is None
    assert not store.pairing_file.exists()


def test_revoke_takes_effect_on_the_next_read(store):
    token, _ = store.redeem(store.new_code(), "iPhone")
    other = PairingStore(store.pairing_file, store.devices_file)  # a second process, like `vmp revoke`
    assert other.revoke("iPhone") is True
    assert other.revoke("iPhone") is False
    assert store.device_for(token) is None
    assert not store.devices_file.exists()


def test_touch_records_last_seen(store):
    token, device = store.redeem(store.new_code(), "iPhone")
    assert device.last_seen is None
    store.touch(device)
    seen = store.device_for(token)
    assert seen is not None and seen.last_seen and seen.last_seen.endswith("+00:00")


def test_duplicate_names_get_a_suffix(store):
    store.redeem(store.new_code(), "iPhone")
    _, second = store.redeem(store.new_code(), "  iPhone  ")
    _, third = store.redeem(store.new_code(), "")
    assert second.name == "iPhone 2"
    assert third.name == "Device"


def test_devices_survive_a_garbage_file(store):
    store.devices_file.write_text("not json")
    assert store.devices() == []
    store.devices_file.write_text(json.dumps([{"name": 1}, "x", {"name": "ok", "token_sha256": "h"}]))
    assert [d.name for d in store.devices()] == ["ok"]


def test_token_from_header_then_cookie():
    assert token_from({"authorization": "Bearer abc"}, {}) == "abc"
    assert token_from({"authorization": "bearer abc "}, {}) == "abc"
    assert token_from({}, {"vmp_token": "ck"}) == "ck"
    assert token_from({"authorization": "Bearer abc"}, {"vmp_token": "ck"}) == "abc"
    assert token_from({"authorization": "Basic abc"}, {}) is None
    assert token_from({"authorization": "Bearer "}, {}) is None
    assert token_from({}, {}) is None

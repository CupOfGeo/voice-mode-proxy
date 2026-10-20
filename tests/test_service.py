"""The launchd plist, without touching launchctl."""

import plistlib
import sys

from voice_mode_proxy import service


def test_plist_runs_this_venv_in_the_repo(tmp_path):
    env = {
        "PATH": "/opt/homebrew/bin:/usr/bin",
        "HOME": "/Users/x",
        "ANTHROPIC_API_KEY": "sk-secret",
        "ANTHROPIC_BASE_URL": "http://127.0.0.1:8787",
        "VMP_PORT": "8791",
        "SHELL": "/bin/zsh",
        "EMPTY": "",
    }
    path = service.write_plist(tmp_path / "agent.plist", env)
    with open(path, "rb") as f:
        d = plistlib.load(f)
    assert d["Label"] == service.LABEL
    assert d["ProgramArguments"] == [sys.executable, "-m", "voice_mode_proxy.server"]
    assert d["WorkingDirectory"] == str(service.ROOT)
    assert d["KeepAlive"] is True and d["RunAtLoad"] is True
    assert d["StandardOutPath"] == d["StandardErrorPath"] == str(service.LOG)
    ev = d["EnvironmentVariables"]
    assert ev["PATH"] == env["PATH"] and ev["HOME"] == env["HOME"]
    assert ev["ANTHROPIC_BASE_URL"] == env["ANTHROPIC_BASE_URL"]
    assert ev["VMP_PORT"] == "8791"
    assert "ANTHROPIC_API_KEY" not in ev  # it would override the Claude Code login
    assert "SHELL" not in ev and "EMPTY" not in ev
    assert ev["VMP_CONFIG"] == str(service.CONFIG_FILE)


def test_plist_keeps_an_explicit_config_path(tmp_path):
    d = service.plist_dict({"VMP_CONFIG": "/elsewhere/config.toml"})
    assert d["EnvironmentVariables"]["VMP_CONFIG"] == "/elsewhere/config.toml"


def test_restart_from_inside_the_job_detaches(monkeypatch, tmp_path):
    # bootout would kill this process mid-restart, so it must hand off to a new session instead.
    spawned = []
    monkeypatch.delenv("_VMP_DETACHED", raising=False)
    monkeypatch.setattr(service, "LOG", tmp_path / "server.log")
    monkeypatch.setattr(service, "_inside_job", lambda: True)
    monkeypatch.setattr(service.subprocess, "Popen", lambda *a, **kw: spawned.append(kw))
    monkeypatch.setattr(service, "_launchctl", lambda *a: (_ for _ in ()).throw(AssertionError("booted out in-job")))
    assert service.restart() == 0
    assert spawned[0]["start_new_session"] and spawned[0]["env"]["_VMP_DETACHED"] == "1"


def test_inside_job_follows_launchd_label(monkeypatch):
    monkeypatch.setenv("XPC_SERVICE_NAME", service.LABEL)
    assert service._inside_job()
    monkeypatch.setenv("XPC_SERVICE_NAME", "0")  # what Terminal sets
    assert not service._inside_job()


def test_plist_drops_the_per_run_say_token():
    env = service.plist_dict({"VMP_SAY_TOKEN": "t", "VMP_SAY_URL": "u", "VMP_PORT": "1"})["EnvironmentVariables"]
    assert "VMP_SAY_TOKEN" not in env and "VMP_SAY_URL" not in env and env["VMP_PORT"] == "1"


def test_bootout_waits_for_launchd_to_drop_the_job(monkeypatch):
    # bootstrap right after bootout fails with "5: Input/output error" while the job is still tearing down.
    checks = iter([True, True, False])
    monkeypatch.setattr(service, "_launchctl", lambda *a: service.subprocess.CompletedProcess(a, 0, "", ""))
    monkeypatch.setattr(service, "loaded", lambda: next(checks))
    monkeypatch.setattr(service.time, "sleep", lambda s: None)
    service._bootout()
    assert next(checks, "drained") == "drained"

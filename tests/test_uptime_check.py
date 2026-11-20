"""The outside uptime check (deploy/uptime_check.py): state machine and messages.

Run:  pytest tests/test_uptime_check.py
"""
import importlib.util
import json
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "uptime_check", os.path.join(_ROOT, "deploy", "uptime_check.py"))
u = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(u)


def test_one_failure_is_only_suspect_two_is_down():
    s, ev = u.step(None, False, 100)
    assert s == {"state": "suspect", "since": 100} and ev is None
    s, ev = u.step(s, False, 400)
    assert s == {"state": "down", "since": 100} and ev == "down"     # down since 1st fail
    s, ev = u.step(s, False, 700)
    assert s["state"] == "down" and ev is None                       # no repeat alerts
    s, ev = u.step(s, True, 1000)
    assert s["state"] == "up" and ev == "up" and s["was_down"] == 900


def test_a_blip_never_alerts():
    s, ev = u.step({"state": "up", "since": 0}, False, 100)
    assert ev is None
    s, ev = u.step(s, True, 400)
    assert s == {"state": "up", "since": 400} and ev is None


def test_messages():
    srv = {"id": "us", "name": "Official server (US Central)"}
    down = u.message(srv, "down", {"status page": "timeout", "game UDP": "no answer"},
                     {"state": "down", "since": 1000})
    assert "Official server (US Central)" in down and "timeout" in down and "<t:1000:t>" in down
    up = u.message(srv, "up", {}, {"state": "up", "since": 2000, "was_down": 1500})
    assert "25 min" in up


def test_main_writes_state_and_output(tmp_path, monkeypatch):
    servers = tmp_path / "servers.json"
    servers.write_text(json.dumps({"servers": [
        {"id": "a", "name": "A", "host": "192.0.2.1", "status_port": 8080},
        {"id": "nostatus", "host": "192.0.2.2", "status_port": 0}]}))
    monkeypatch.setattr(u, "check", lambda srv: (False, {"status page": "timeout"}))
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.delenv("DISCORD_WEBHOOK", raising=False)
    state = tmp_path / "state"
    u.main([str(servers), "--state", str(state)])
    assert json.loads(state.read_text())["a"]["state"] == "suspect"
    assert "nostatus" not in json.loads(state.read_text())          # no status page: skipped
    assert out.read_text().strip() == "changed=true"
    u.main([str(servers), "--state", str(state)])
    assert json.loads(state.read_text())["a"]["state"] == "down"
    out.write_text("")
    u.main([str(servers), "--state", str(state)])
    assert out.read_text().strip() == "changed=false"

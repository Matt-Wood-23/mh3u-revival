"""Tests for the Discord webhook status/alerts (discord_status.py), against a local
stand-in for Discord's webhook API.

Run:  python tests/test_discord_status.py     (or: pytest tests/test_discord_status.py)
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "..", "external", "NintendoClients"))
sys.path.insert(0, _ROOT)

import asyncio
import http.server
import json
import logging
import shutil
import tempfile
import threading
from pathlib import Path

import discord_status as ds
import matchmaking_handlers as mh
import status_http


class FakeDiscord(http.server.BaseHTTPRequestHandler):
    calls = []          # (method, path, payload)
    messages = {}       # id -> content
    next_id = [1000]

    def _handle(self):
        n = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(n) or b"null")
        self.calls.append((self.command, self.path, payload))
        path = self.path.split("?", 1)[0]
        if self.command == "POST" and path == "/api/webhooks/1/tok":
            mid = str(self.next_id[0])
            self.next_id[0] += 1
            self.messages[mid] = payload["content"]
            self._send(200, {"id": mid, "content": payload["content"]})
        elif self.command == "PATCH" and path.startswith("/api/webhooks/1/tok/messages/"):
            mid = path.rsplit("/", 1)[1]
            if mid not in self.messages:
                return self._send(404, {"message": "Unknown Message"})
            self.messages[mid] = payload["content"]
            self._send(200, {"id": mid})
        else:
            self._send(404, {"message": "Unknown Webhook"})

    do_POST = do_PATCH = _handle

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def _setup():
    FakeDiscord.calls.clear()
    FakeDiscord.messages.clear()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeDiscord)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    hook = f"http://127.0.0.1:{httpd.server_address[1]}/api/webhooks/1/tok"
    ds.STATUS_URL = ds.ALERT_URL = hook
    ds.STATE_DIR = Path(tempfile.mkdtemp(prefix="mh3u_discord_test_"))
    ds._state.clear()
    ds._failing.clear()
    return httpd


def _teardown(httpd):
    httpd.shutdown()
    shutil.rmtree(ds.STATE_DIR, ignore_errors=True)
    ds.STATUS_URL = ds.ALERT_URL = ""


def test_render():
    mh.CLIENTS.clear()
    mh.CLIENTS[0x45670001] = object()
    try:
        snap = status_http.snapshot()
    finally:
        mh.CLIENTS.clear()
    text = ds.render_status(snap, name="Test", now=1700000000)
    assert text.startswith("🟢 **Test** is online")
    assert "**1** hunter online · **0** rooms" in text
    assert "Gathering Hall 1: 0/" in text
    assert "<t:1700000000:R>" in text
    assert "45670001" not in text and str(0x45670001) not in text
    assert ds.render_offline(name="Test", now=5).startswith("🔴 **Test** is offline")
    assert ds._uptime(59) == "0m" and ds._uptime(3720) == "1h 02m"
    assert ds._uptime(90000) == "1d 1h"


def test_url_keeps_thread_query():
    u = ds._url("https://discord.com/api/webhooks/1/tok?thread_id=9", "/messages/5")
    assert u == "https://discord.com/api/webhooks/1/tok/messages/5?thread_id=9"
    u = ds._url("https://discord.com/api/webhooks/1/tok", wait="true")
    assert u == "https://discord.com/api/webhooks/1/tok?wait=true"


def test_status_message_post_then_edit():
    httpd = _setup()
    try:
        st = {}
        assert ds.set_status(st, "one")
        mid = st["status_message_id"]
        assert FakeDiscord.calls[-1][0] == "POST" and "wait=true" in FakeDiscord.calls[-1][1]
        assert FakeDiscord.calls[-1][2]["allowed_mentions"] == {"parse": []}
        assert ds.set_status(st, "two")
        assert FakeDiscord.calls[-1][0] == "PATCH" and FakeDiscord.messages[mid] == "two"
        assert ds.load_state()["status_message_id"] == mid      # saved for next start
        # someone deleted the message: a new one is posted
        del FakeDiscord.messages[mid]
        assert ds.set_status(st, "three")
        assert st["status_message_id"] != mid
        assert FakeDiscord.messages[st["status_message_id"]] == "three"
    finally:
        _teardown(httpd)


async def test_start_stop_and_crash_alerts():
    httpd = _setup()
    try:
        await ds.started()
        assert "started" in FakeDiscord.calls[-1][2]["content"]
        assert ds.load_state()["running"] is True
        ds.set_status(ds._state, "live")
        await ds.stopped()
        offline = FakeDiscord.messages[ds._state["status_message_id"]]
        assert offline.startswith("🔴")
        assert "stopped" in FakeDiscord.calls[-1][2]["content"]
        assert ds.load_state()["running"] is False
        # clean stop -> next start is a normal start
        await ds.started()
        assert "unexpected" not in FakeDiscord.calls[-1][2]["content"]
        # no stopped() this time (a crash): the next start says so
        ds._state.clear()
        await ds.started()
        assert "unexpected stop" in FakeDiscord.calls[-1][2]["content"]
        # the status message id survived the restarts, so it's edited, not reposted
        assert "status_message_id" in ds._state
    finally:
        _teardown(httpd)


def test_failures_log_once(caplog=None):
    ds.STATUS_URL = "http://127.0.0.1:9/api/webhooks/1/tok"     # nothing listens there
    ds.STATE_DIR = Path(tempfile.mkdtemp(prefix="mh3u_discord_test_"))
    ds._failing.clear()
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    ds.logger.addHandler(handler)
    try:
        assert not ds.set_status({}, "x")
        assert not ds.set_status({}, "x")
        assert len([r for r in records if r.levelno == logging.WARNING]) == 1
    finally:
        ds.logger.removeHandler(handler)
        shutil.rmtree(ds.STATE_DIR, ignore_errors=True)
        ds.STATUS_URL = ""


def main():
    test_render()
    test_url_keeps_thread_query()
    test_status_message_post_then_edit()
    asyncio.run(test_start_stop_and_crash_alerts())
    test_failures_log_once()
    print("discord_status: all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

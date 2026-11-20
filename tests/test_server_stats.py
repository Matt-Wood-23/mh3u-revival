"""Saved counters (server_stats.py): today's peak and the relay's traffic.

Run:  pytest tests/test_server_stats.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "..", "external", "NintendoClients"))
sys.path.insert(0, _ROOT)

import copy
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import config
import relay
import server_stats as st
import status_http


def _at(y, m, d, h=12):
    return datetime(y, m, d, h, tzinfo=timezone.utc)


def _fresh(monkeypatch):
    monkeypatch.setattr(st, "_state", copy.deepcopy(st._state))
    st._state["relay"].update(day="", day_in=0, day_out=0, month="", month_in=0, month_out=0)
    st._state["peak"] = {"date": "", "players": 0}
    st._state["egress_warned"] = ""
    st.RELAY.rx = st.RELAY.tx = 0


def test_relay_totals_roll_over_by_day_and_month(monkeypatch):
    _fresh(monkeypatch)
    st.RELAY.rx, st.RELAY.tx = 100, 300
    t = st.relay_totals(_at(2026, 11, 30))
    assert (t["bytes_in_today"], t["bytes_out_today"], t["bytes_out_month"]) == (100, 300, 300)
    st.RELAY.tx = 50
    t = st.relay_totals(_at(2026, 11, 30, 23))
    assert t["bytes_out_today"] == 350 and st.RELAY.tx == 0
    st.RELAY.tx = 10
    t = st.relay_totals(_at(2026, 12, 1))                     # new day AND new month
    assert (t["bytes_out_today"], t["bytes_out_month"], t["month"]) == (10, 10, "2026-12")


def test_peak_resets_each_day(monkeypatch):
    _fresh(monkeypatch)
    assert st.note_players(3, _at(2026, 11, 20))["players"] == 3
    assert st.note_players(1, _at(2026, 11, 20))["players"] == 3
    assert st.note_players(1, _at(2026, 11, 21)) == {"date": "2026-11-21", "players": 1}


def test_saved_and_loaded_across_a_restart(monkeypatch):
    _fresh(monkeypatch)
    d = Path(tempfile.mkdtemp(prefix="mh3u_stats_test_"))
    monkeypatch.setattr(st, "STATE_DIR", d)
    try:
        st.start(persist=True)
        st.note_players(7)
        st.RELAY.tx = 12345
        st.save()
        _fresh(monkeypatch)
        st.load()
        assert st._state["peak"]["players"] == 7
        assert st.relay_totals()["bytes_out_month"] == 12345
        (d / st.STATE_FILE).write_text("not json", encoding="utf-8")
        st.load()                                             # a bad file is ignored
    finally:
        st._persist = False
        shutil.rmtree(d, ignore_errors=True)


def test_no_state_file_unless_public(monkeypatch):
    _fresh(monkeypatch)
    d = Path(tempfile.mkdtemp(prefix="mh3u_stats_test_"))
    monkeypatch.setattr(st, "STATE_DIR", d / "state")
    try:
        st.start(persist=False)
        st.save()
        assert not (d / "state").exists()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_egress_warning_once_a_month(monkeypatch):
    _fresh(monkeypatch)
    monkeypatch.setattr(st, "EGRESS_WARN_GB", 1)
    st.RELAY.tx = 999_999_999
    assert st.egress_warning(_at(2026, 11, 5)) is None
    st.RELAY.tx = 1
    text = st.egress_warning(_at(2026, 11, 5))
    assert text and "1.0 GB" in text and "2026-11" in text
    st.RELAY.tx = 5_000_000_000
    assert st.egress_warning(_at(2026, 11, 6)) is None         # already warned this month
    st.RELAY.tx = 2_000_000_000
    assert st.egress_warning(_at(2026, 12, 1)) is not None      # next month, again
    monkeypatch.setattr(st, "EGRESS_WARN_GB", 0)
    st.RELAY.tx = 10 ** 12
    assert st.egress_warning(_at(2027, 1, 1)) is None           # 0 = off


def test_human_bytes():
    assert st.human_bytes(999) == "999 B"
    assert st.human_bytes(1_500_000) == "1.5 MB"
    assert st.human_bytes(2_340_000_000_000) == "2.34 TB"


def test_relay_counts_forwarded_bytes(monkeypatch):
    _fresh(monkeypatch)

    class _T:
        def __init__(self):
            self.sent = []

        def sendto(self, data, addr):
            self.sent.append((data, addr))
    p = relay.PairRelay(None, (1, 2, 3))
    p.transport = _T()
    a, b = ("1.1.1.1", 1000), ("2.2.2.2", 2000)
    p.datagram_received(b"x" * 10, a)          # buffered until the other end shows up
    p.datagram_received(b"y" * 20, b)          # flushes the 10, forwards the 20
    p.datagram_received(b"z" * 5, a)
    assert (st.RELAY.rx, st.RELAY.tx) == (35, 35)


def test_status_page_shows_relay_totals_only_with_relay_on(monkeypatch):
    _fresh(monkeypatch)
    monkeypatch.setattr(config, "RELAY_MODE", "off")
    assert "relay" not in status_http.snapshot()
    monkeypatch.setattr(config, "RELAY_MODE", "force")
    st.RELAY.tx = 4096
    r = status_http.snapshot()["relay"]
    assert r["mode"] == "force" and r["bytes_out_today"] == 4096 and "active_links" in r

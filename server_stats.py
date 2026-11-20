"""Counters that outlive a restart: today's player peak and the relay's traffic.

The relay is the server's one big bandwidth user (every relayed hunt flows through it),
and cloud hosts bill outbound traffic past a monthly allowance (Oracle: 10 TB). So the
relay's bytes are counted per day and per calendar month (UTC), shown on the status
page, and optionally announced once a month when they pass MH3U_EGRESS_WARN_GB.

Saved to <state dir>/stats.json every minute and at shutdown, but only on a server
that runs the status page or Discord (a public server). Elsewhere the counters live in
memory only, so a friend's server doesn't grow a state folder it never asked for.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import limits

logger = logging.getLogger("mh3u.stats")

STATE_DIR = Path(os.environ.get("MH3U_STATE_DIR") or os.environ.get("STATE_DIRECTORY")
                 or "state")
STATE_FILE = "stats.json"
SAVE_SECONDS = 60
EGRESS_WARN_GB = limits._int_env("MH3U_EGRESS_WARN_GB", 5000)   # 0 = never warn


class _Relay:
    """Hot-path counters, bumped for every relayed datagram. Plain attributes on
    purpose: a few integer adds per packet, folded into the dated totals later."""
    __slots__ = ("rx", "tx")

    def __init__(self):
        self.rx = 0
        self.tx = 0


RELAY = _Relay()
_persist = False
_state = {"peak": {"date": "", "players": 0},
          "relay": {"day": "", "day_in": 0, "day_out": 0,
                    "month": "", "month_in": 0, "month_out": 0},
          "egress_warned": ""}


def _now():
    return datetime.now(timezone.utc)


def _fold(now=None):
    """Move the hot counters into today's and this month's totals, starting fresh
    totals when the UTC day or month has changed."""
    now = now or _now()
    day, month = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")
    r = _state["relay"]
    if r["day"] != day:
        r["day"], r["day_in"], r["day_out"] = day, 0, 0
    if r["month"] != month:
        r["month"], r["month_in"], r["month_out"] = month, 0, 0
    rx, tx = RELAY.rx, RELAY.tx
    RELAY.rx = RELAY.tx = 0
    r["day_in"] += rx
    r["month_in"] += rx
    r["day_out"] += tx
    r["month_out"] += tx
    return r


def note_players(players, now=None):
    """Record the current player count; returns today's peak as a dict."""
    now = now or _now()
    today = now.strftime("%Y-%m-%d")
    peak = _state["peak"]
    if peak["date"] != today:
        peak["date"], peak["players"] = today, 0
    peak["players"] = max(peak["players"], players)
    return dict(peak)


def relay_totals(now=None):
    r = _fold(now)
    return {"bytes_out_today": r["day_out"], "bytes_in_today": r["day_in"],
            "bytes_out_month": r["month_out"], "bytes_in_month": r["month_in"],
            "month": r["month"]}


def human_bytes(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1000:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1000
    return f"{n:.2f} TB"


# --- persistence ------------------------------------------------------------

def load():
    """Read the saved counters (if any). Totals for a past day/month are kept as read
    and reset by the next fold, so a restart never double-counts or loses the month."""
    try:
        data = json.loads((STATE_DIR / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(data, dict):
        return
    peak, relay = data.get("peak"), data.get("relay")
    if isinstance(peak, dict) and isinstance(peak.get("players"), int):
        _state["peak"] = {"date": str(peak.get("date", "")), "players": peak["players"]}
    if isinstance(relay, dict):
        for k in _state["relay"]:
            v = relay.get(k)
            if isinstance(v, type(_state["relay"][k])):
                _state["relay"][k] = v
    if isinstance(data.get("egress_warned"), str):
        _state["egress_warned"] = data["egress_warned"]


def save():
    if not _persist:
        return
    _fold()
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STATE_DIR / (STATE_FILE + ".tmp")
        tmp.write_text(json.dumps(_state), encoding="utf-8")
        tmp.replace(STATE_DIR / STATE_FILE)
    except OSError as e:
        logger.warning("stats: can't save %s (%s)", STATE_DIR / STATE_FILE, e)


def start(persist):
    """Call once at startup. persist=True on a public server (status page or Discord)."""
    global _persist
    _persist = bool(persist)
    if _persist:
        load()
        logger.info("stats: saved to %s (relay out this month: %s)", STATE_DIR / STATE_FILE,
                    human_bytes(_state["relay"]["month_out"]))


def egress_warning(now=None):
    """The one-per-month warning text once relay output passes MH3U_EGRESS_WARN_GB,
    else None. Marks the month as warned."""
    if EGRESS_WARN_GB <= 0:
        return None
    r = _fold(now)
    if r["month_out"] < EGRESS_WARN_GB * 1_000_000_000 or _state["egress_warned"] == r["month"]:
        return None
    _state["egress_warned"] = r["month"]
    return (f"📈 The relay has sent **{human_bytes(r['month_out'])}** this month "
            f"({r['month']}, UTC), past the {EGRESS_WARN_GB} GB warning line. Check the "
            "host's free outbound allowance (Oracle: 10 TB a month).")


async def save_loop(alert=None):
    """Supervised background task: save every minute; post the egress warning through
    alert(text) (a blocking call, run in a thread) when it trips."""
    while True:
        await asyncio.sleep(SAVE_SECONDS)
        text = egress_warning()
        if text:
            logger.warning("stats: %s", text)
            if alert:
                await asyncio.to_thread(alert, text)
        save()

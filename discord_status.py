"""Discord webhooks: a live status message, plus start/stop alerts.

Both are off unless a webhook URL is set (Discord: channel settings > Integrations >
Webhooks > New Webhook > Copy Webhook URL):

    MH3U_DISCORD_STATUS_WEBHOOK  one message in that channel, edited in place with the
                                 player and room counts (counts only: no names or IPs)
    MH3U_DISCORD_ALERT_WEBHOOK   a new message when the server starts, stops, or comes
                                 back after an unexpected stop (crash, reboot, kill)

They can be the same URL, but the status message stays easiest to find in a channel of
its own. Optional: MH3U_SERVER_NAME (shown in the messages), MH3U_DISCORD_INTERVAL
(seconds between checks, default 60, minimum 30), MH3U_STATE_DIR (where the status
message id and the "running" flag are kept; under systemd, StateDirectory= sets it).

The process can't report its own crash, so an unexpected stop is noticed when the server
starts again: the "running" flag from the last run is still set.
"""
import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import limits
import status_http

logger = logging.getLogger("mh3u.discord")

STATUS_URL = os.environ.get("MH3U_DISCORD_STATUS_WEBHOOK", "").strip()
ALERT_URL = os.environ.get("MH3U_DISCORD_ALERT_WEBHOOK", "").strip()
NAME = os.environ.get("MH3U_SERVER_NAME", "").strip() or "MH3U Revival server"
INTERVAL = max(30, limits._int_env("MH3U_DISCORD_INTERVAL", 60))
REFRESH = 600          # edit at least this often, so a stale "Updated" time means trouble
STATE_DIR = Path(os.environ.get("MH3U_STATE_DIR") or os.environ.get("STATE_DIRECTORY")
                 or "state")
STATE_FILE = "discord.json"
USER_AGENT = "DiscordBot (https://github.com/Matt-Wood-23/mh3u-revival, 1)"
NO_PINGS = {"parse": []}

_failing = set()       # which calls are currently failing, so each failure logs once


def enabled():
    return bool(STATUS_URL or ALERT_URL)


# --- message text (pure) ----------------------------------------------------

def _plural(n, word):
    return f"**{n}** {word}" + ("" if n == 1 else "s")


def _uptime(secs):
    secs = int(secs)
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def status_key(snap):
    """What has to change for the status message to be edited."""
    return (snap["players"], snap["rooms"],
            tuple((h["name"], h["players"]) for h in snap["halls"]))


def render_status(snap, name=None, now=None):
    lines = [f"🟢 **{name or NAME}** is online",
             f"{_plural(snap['players'], 'hunter')} online · {_plural(snap['rooms'], 'room')}"]
    lines += [f"{h['name']}: {h['players']}/{h['max']}" for h in snap["halls"]]
    lines.append(f"Peak today: {snap['peak_today']['players']} · "
                 f"up {_uptime(snap['uptime_s'])}")
    lines.append(f"-# Updated <t:{int(now or time.time())}:R>")
    return "\n".join(lines)


def render_offline(name=None, now=None):
    return (f"🔴 **{name or NAME}** is offline (stopped)\n"
            f"-# Since <t:{int(now or time.time())}:f>")


# --- webhook calls (blocking; run them in a thread) -------------------------

def _url(webhook, path="", **query):
    """The webhook URL with a path suffix and extra query parameters, keeping any query
    it already has (e.g. ?thread_id= for a forum thread)."""
    parts = urllib.parse.urlsplit(webhook)
    q = urllib.parse.parse_qsl(parts.query) + list(query.items())
    return urllib.parse.urlunsplit(parts._replace(path=parts.path.rstrip("/") + path,
                                                  query=urllib.parse.urlencode(q)))


def _call(method, url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method=method,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as r:
        body = r.read()
    return json.loads(body) if body else None


def _logged(what, fn):
    """Run fn(); log the first failure of each kind and the recovery, not every retry."""
    try:
        result = fn()
    except Exception as e:
        if what not in _failing:
            _failing.add(what)
            logger.warning("discord: %s failed (%s); will keep trying quietly", what, e)
        return None
    if what in _failing:
        _failing.discard(what)
        logger.info("discord: %s works again", what)
    return result


def load_state():
    try:
        data = json.loads((STATE_DIR / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(state):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STATE_DIR / (STATE_FILE + ".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        tmp.replace(STATE_DIR / STATE_FILE)
    except OSError as e:
        logger.warning("discord: can't save %s (%s)", STATE_DIR / STATE_FILE, e)


def post_alert(text):
    if ALERT_URL:
        _logged("alert", lambda: _call("POST", _url(ALERT_URL, wait="true"),
                                       {"content": text, "allowed_mentions": NO_PINGS}))


def set_status(state, content):
    """Edit the status message, or post a new one if there is none yet or it was
    deleted. Returns True on success."""
    payload = {"content": content, "allowed_mentions": NO_PINGS}

    def edit_or_post():
        mid = state.get("status_message_id")
        if mid:
            try:
                _call("PATCH", _url(STATUS_URL, f"/messages/{mid}"), payload)
                return True
            except urllib.error.HTTPError as e:
                if e.code != 404:        # 404 = deleted, or a different webhook now
                    raise
        msg = _call("POST", _url(STATUS_URL, wait="true"), payload)
        state["status_message_id"] = str(msg["id"])
        save_state(state)
        return True

    return bool(_logged("status message", edit_or_post))


# --- server hooks -----------------------------------------------------------

_state = {}


async def started():
    """Call once at startup: alert, and note that we're running."""
    global _state
    if not enabled():
        return
    _state = load_state()
    unclean = bool(_state.get("running"))
    _state["running"] = True
    save_state(_state)
    logger.info("discord: status message %s, alerts %s",
                "on" if STATUS_URL else "off", "on" if ALERT_URL else "off")
    if unclean:
        text = (f"⚠️ **{NAME}** is back up after an unexpected stop "
                "(crash, reboot or kill). Anyone who was on will need to reconnect.")
    else:
        text = f"✅ **{NAME}** started."
    await asyncio.to_thread(post_alert, text)


async def status_loop():
    """Supervised background task: keep the status message current."""
    if not STATUS_URL:
        await asyncio.Event().wait()     # nothing to do; don't let the supervisor respawn us
    last_key, last_edit = None, -1e9
    while True:
        snap = status_http.snapshot()
        key = status_key(snap)
        if key != last_key or time.monotonic() - last_edit >= REFRESH:
            if await asyncio.to_thread(set_status, _state, render_status(snap)):
                last_key, last_edit = key, time.monotonic()
        await asyncio.sleep(INTERVAL)


async def stopped():
    """Call on a clean shutdown. Never raises and gives up after a few seconds, so it
    can't hold up a stop."""
    if not enabled():
        return
    _state["running"] = False
    save_state(_state)

    def work():
        if STATUS_URL and _state.get("status_message_id"):
            set_status(_state, render_offline())
        post_alert(f"🛑 **{NAME}** stopped.")
    try:
        await asyncio.wait_for(asyncio.to_thread(work), 8)
    except Exception:
        pass

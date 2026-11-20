"""Read-only HTTP status page: GET /status returns live player and room counts as JSON
(plus the relay's traffic totals when the relay is on).

Off unless MH3U_STATUS_PORT is set (a TCP port). Meant for a public server, so the
launcher and Discord can show "12 hunters online". It exposes counts only, never PIDs,
names or IP addresses.

    MH3U_STATUS_PORT=8080 python server.py
    curl http://<server>:8080/status

The handler is deliberately small and defensive, since anyone on the internet can reach
it: GET/HEAD only, a request head of at most 4 KiB read within 5 s, a cap on open
connections, and a snapshot cached for a couple of seconds so a flood of requests costs
almost nothing.
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone

import config
import limits
import matchmaking_handlers as mh
import relay
import server_stats

logger = logging.getLogger("mh3u.status")

PORT = limits._int_env("MH3U_STATUS_PORT", 0)
MAX_OPEN = limits._int_env("MH3U_STATUS_MAX_CONNECTIONS", 64)
READ_TIMEOUT = 5.0
HEAD_LIMIT = 4096
CACHE_SECONDS = 2.0

_START_WALL = datetime.now(timezone.utc)
_START_MONO = time.monotonic()
_cache = {"at": -1e9, "body": b""}
_open = 0
_server = None   # keep a reference to the listener for the life of the process


def _utc_now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _hall_name(pg):
    # Hall names are sent as repeated ':'-separated segments for the EU build's parser
    # (see CommunityRegistry); the first segment is the name players see.
    name = getattr(pg, "description", "") or ""
    return name.split(":", 1)[0]


def snapshot():
    """The status as a plain dict. Pure read of the live registries."""
    now = _utc_now()
    players = len(mh.CLIENTS)
    rooms = list(mh.REGISTRY.sessions.values())
    # A hall's Western and JP copies share a label and count as one hall.
    halls = {}
    for c in mh.COMMUNITY.communities.values():
        if c.official:
            name = getattr(c, "label", None) or _hall_name(c.pg)
            h = halls.setdefault(name, {"name": name, "players": 0, "max": mh.HALL_MAX})
            h["players"] += len(c.participants)
    halls = list(halls.values())
    snap = {
        "online": True,
        "players": players,
        "rooms": len(rooms),
        "players_in_rooms": sum(len(s.participants) for s in rooms),
        "halls": halls,
        "peak_today": server_stats.note_players(players, now),
        "started_at": _iso(_START_WALL),
        "uptime_s": int(time.monotonic() - _START_MONO),
        "updated_at": _iso(now),
    }
    if relay.enabled():
        # Traffic totals (UTC day / month) for the host's bandwidth bill. Counts only.
        snap["relay"] = {"mode": config.RELAY_MODE,
                         "active_links": len(relay.MANAGER._relays),
                         **server_stats.relay_totals(now)}
    return snap


def _status_body():
    t = time.monotonic()
    if t - _cache["at"] >= CACHE_SECONDS:
        _cache["body"] = json.dumps(snapshot(), separators=(",", ":")).encode()
        _cache["at"] = t
    return _cache["body"]


def _response(code, reason, body, ctype="application/json", head_only=False):
    head = (
        f"HTTP/1.1 {code} {reason}\r\n"
        f"Content-Type: {ctype}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Cache-Control: no-store\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "Connection: close\r\n\r\n"
    ).encode()
    return head if head_only else head + body


def handle_request(head):
    """Bytes of the request head -> bytes of the full response. Pure, so it's testable."""
    try:
        line = head.split(b"\r\n", 1)[0].decode("ascii")
        method, target, _version = line.split(" ", 2)
    except (UnicodeDecodeError, ValueError):
        return _response(400, "Bad Request", b'{"error":"bad request"}')
    if method not in ("GET", "HEAD"):
        return _response(405, "Method Not Allowed", b'{"error":"GET only"}')
    path = target.split("?", 1)[0]
    if path in ("/", "/status"):
        return _response(200, "OK", _status_body(), head_only=(method == "HEAD"))
    return _response(404, "Not Found", b'{"error":"not found"}', head_only=(method == "HEAD"))


async def _serve_one(reader, writer):
    global _open
    _open += 1
    try:
        if _open > MAX_OPEN:
            return
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), READ_TIMEOUT)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError,
                ConnectionError):
            return
        writer.write(handle_request(head))
        await asyncio.wait_for(writer.drain(), READ_TIMEOUT)
    except Exception:
        logger.debug("status: request failed", exc_info=True)
    finally:
        _open -= 1
        writer.close()


async def start(host, port=None):
    """Start the status listener if a port is configured. Returns the asyncio Server or
    None. A port that can't be bound only logs an error: the game server keeps running."""
    global _server
    port = PORT if port is None else port
    if not port:
        return None
    try:
        server = await asyncio.start_server(_serve_one, host, port, limit=HEAD_LIMIT)
    except OSError as e:
        logger.error("status page: could not listen on TCP %s:%d (%s); continuing without it",
                     host, port, e)
        return None
    _server = server
    logger.info("status page: http://%s:%d/status (counts only)", host, port)
    return server

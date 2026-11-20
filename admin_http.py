"""Admin port: announcements and planned restarts, for the host only.

Off unless MH3U_ADMIN_PORT is set. It always listens on 127.0.0.1 (never MH3U_BIND), so
it can only be reached from the server machine itself, e.g. over SSH:

    curl -s -X POST --data-binary "Event quest night at 8pm ET!" localhost:8081/announce
    curl -s -X POST "localhost:8081/restart?wait=idle&max_minutes=60"
    curl -s localhost:8081/restart                 # is a restart pending?
    curl -s -X POST localhost:8081/restart/cancel

/announce posts the request body as a chat message from "Server" to every player in a
hall or room (?scope=halls or ?scope=rooms to narrow it). Long text is split into a few
chat-sized messages. /restart: see maintenance.py.
"""
import asyncio
import json
import logging
import urllib.parse

import announce
import limits
import maintenance

logger = logging.getLogger("mh3u.admin")

PORT = limits._int_env("MH3U_ADMIN_PORT", 0)
HOST = "127.0.0.1"
READ_TIMEOUT = 5.0
HEAD_LIMIT = 4096
BODY_LIMIT = 2048
_server = None


def _json(code, obj):
    reason = {200: "OK", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed",
              413: "Payload Too Large"}.get(code, "OK")
    body = (json.dumps(obj) + "\n").encode()
    return (f"HTTP/1.1 {code} {reason}\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body


async def handle(method, target, body):
    """(method, target, body bytes) -> response bytes."""
    url = urllib.parse.urlsplit(target)
    q = dict(urllib.parse.parse_qsl(url.query))
    path = url.path.rstrip("/") or "/"
    if path == "/announce":
        if method != "POST":
            return _json(405, {"error": "POST the message text"})
        text = body.decode("utf-8", "replace").strip()
        scope = q.get("scope", "all")
        if not text or scope not in ("all", "halls", "rooms"):
            return _json(400, {"error": "empty text, or scope not all/halls/rooms"})
        reached, parts = await announce.send(text, scope)
        return _json(200, {"players": reached, "messages": parts,
                           "parts": announce.split(text)})
    if path == "/restart":
        if method == "GET":
            return _json(200, maintenance.status())
        if method != "POST":
            return _json(405, {"error": "GET or POST"})
        try:
            return _json(200, maintenance.schedule(q.get("wait", "idle"),
                                                   int(q.get("max_minutes", 60))))
        except ValueError as e:
            return _json(400, {"error": str(e)})
    if path == "/restart/cancel":
        if method != "POST":
            return _json(405, {"error": "POST"})
        return _json(200, {"cancelled": maintenance.cancel()})
    return _json(404, {"error": "not found"})


async def _serve_one(reader, writer):
    try:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), READ_TIMEOUT)
        lines = head.decode("latin-1").split("\r\n")
        method, target, _ = lines[0].split(" ", 2)
        length = 0
        for line in lines[1:]:
            k, _, v = line.partition(":")
            if k.strip().lower() == "content-length":
                length = int(v.strip() or 0)
        if length > BODY_LIMIT:
            writer.write(_json(413, {"error": f"at most {BODY_LIMIT} bytes"}))
        else:
            body = await asyncio.wait_for(reader.readexactly(length), READ_TIMEOUT) if length else b""
            writer.write(await handle(method, target, body))
        await asyncio.wait_for(writer.drain(), READ_TIMEOUT)
    except Exception:
        logger.debug("admin: request failed", exc_info=True)
    finally:
        writer.close()


async def start(port=None):
    """Start the admin listener if MH3U_ADMIN_PORT is set. Returns the server or None."""
    global _server
    port = PORT if port is None else port
    if not port:
        return None
    try:
        _server = await asyncio.start_server(_serve_one, HOST, port, limit=HEAD_LIMIT)
    except OSError as e:
        logger.error("admin port: could not listen on %s:%d (%s); continuing without it",
                     HOST, port, e)
        return None
    logger.info("admin port: http://%s:%d (announce, restart; this machine only)", HOST, port)
    return _server


def enabled():
    return bool(PORT)

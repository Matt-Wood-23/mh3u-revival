"""Tests for the read-only HTTP status page (status_http.py).

Run:  python tests/test_status_http.py     (or: pytest tests/test_status_http.py)
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "..", "external", "NintendoClients"))
sys.path.insert(0, _ROOT)

import asyncio
import json

import matchmaking_handlers as mh
import status_http


def _body(resp):
    head, _, body = resp.partition(b"\r\n\r\n")
    return head.decode(), body


def test_snapshot_counts_only():
    mh.CLIENTS.clear()
    mh.REGISTRY.sessions.clear()
    status_http._cache["at"] = -1e9
    mh.CLIENTS[0x40000001] = object()
    mh.CLIENTS[0x40000002] = object()
    hall = next(c for c in mh.COMMUNITY.communities.values() if c.official)
    hall.participants.update({0x40000001, 0x40000002})
    try:
        snap = status_http.snapshot()
        assert snap["online"] is True
        assert snap["players"] == 2
        assert snap["rooms"] == 0
        assert snap["halls"][0] == {"name": "Gathering Hall 1", "players": 2,
                                    "max": mh.HALL_MAX}
        assert snap["peak_today"]["players"] >= 2
        # nothing that identifies a player may leak
        text = json.dumps(snap)
        assert str(0x40000001) not in text and "40000001" not in text
    finally:
        mh.CLIENTS.clear()
        hall.participants.clear()


def test_routes():
    status_http._cache["at"] = -1e9
    head, body = _body(status_http.handle_request(b"GET /status HTTP/1.1\r\nHost: x\r\n\r\n"))
    assert head.startswith("HTTP/1.1 200")
    assert "application/json" in head and "Access-Control-Allow-Origin: *" in head
    assert json.loads(body)["online"] is True

    head, body = _body(status_http.handle_request(b"GET /?x=1 HTTP/1.1\r\n\r\n"))
    assert head.startswith("HTTP/1.1 200")

    head, body = _body(status_http.handle_request(b"HEAD /status HTTP/1.1\r\n\r\n"))
    assert head.startswith("HTTP/1.1 200") and body == b""

    head, _ = _body(status_http.handle_request(b"GET /admin HTTP/1.1\r\n\r\n"))
    assert head.startswith("HTTP/1.1 404")
    head, _ = _body(status_http.handle_request(b"POST /status HTTP/1.1\r\n\r\n"))
    assert head.startswith("HTTP/1.1 405")
    head, _ = _body(status_http.handle_request(b"\xff\xfe garbage\r\n\r\n"))
    assert head.startswith("HTTP/1.1 400")
    head, _ = _body(status_http.handle_request(b"nonsense\r\n\r\n"))
    assert head.startswith("HTTP/1.1 400")


async def _get(port, raw):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(raw)
    await writer.drain()
    data = await asyncio.wait_for(reader.read(), 5)
    writer.close()
    return data


async def test_over_tcp():
    server = await status_http.start("127.0.0.1", port=0) or None
    assert server is None          # port 0 = disabled
    server = await asyncio.start_server(status_http._serve_one, "127.0.0.1", 0,
                                        limit=status_http.HEAD_LIMIT)
    port = server.sockets[0].getsockname()[1]
    try:
        data = await _get(port, b"GET /status HTTP/1.1\r\nHost: x\r\n\r\n")
        head, body = _body(data)
        assert head.startswith("HTTP/1.1 200")
        assert json.loads(body)["online"] is True

        # an oversized request head is dropped without a response
        data = await _get(port, b"GET /status HTTP/1.1\r\nX: " + b"a" * 8000 + b"\r\n\r\n")
        assert data == b""

        # a client that connects and sends nothing is cut off, not held forever
        old = status_http.READ_TIMEOUT
        status_http.READ_TIMEOUT = 0.2
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            assert await asyncio.wait_for(reader.read(), 3) == b""
            writer.close()
        finally:
            status_http.READ_TIMEOUT = old
    finally:
        server.close()
        await server.wait_closed()


def main():
    test_snapshot_counts_only()
    test_routes()
    asyncio.run(test_over_tcp())
    print("status_http: all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())


def test_hall_names_setting():
    import matchmaking_handlers as mh
    f = mh._hall_names
    assert f(None, 1) == ["Gathering Hall 1"]
    assert f("", 3) == ["Gathering Hall 1", "Gathering Hall 2", "Gathering Hall 3"]
    assert f(" Americas , Europe,, Asia/Oceania ", 1) == ["Americas", "Europe", "Asia/Oceania"]
    assert f("EU: West", 1) == ["EU West"]                 # ':' is the EU language separator
    assert len(f("x" * 60, 1)[0]) == mh.HALL_NAME_MAX

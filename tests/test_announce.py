"""Server announcements (announce.py), planned restarts (maintenance.py) and the admin
port (admin_http.py).

Run:  pytest tests/test_announce.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "..", "external", "NintendoClients"))
sys.path.insert(0, _ROOT)

import asyncio
import json
import struct
import types

import admin_http
import announce
import maintenance
import matchmaking_handlers as mh


def _player_shout(gid, hall="Americas", room="", name="Hunter", lang="eng", text="Hello"):
    """A shout laid out the way the game writes one (see announce.py)."""
    pre = struct.pack("<III", 0, gid, 2) + bytes(20) + struct.pack("<I", 1)
    fields = [hall, "Lobby", room, "Acct01", name, lang, "", "", "M", text]
    return announce.build(pre, [f.encode() for f in fields], b"\x01\x00\x00")


def test_build_layout_and_round_trip():
    raw = _player_shout(0x201, text="Nice to meet you!")
    n = struct.unpack_from("<H", raw, 0)[0]
    assert raw[2:2 + n] == b"UserMessage\x00"
    outer, inner = struct.unpack_from("<II", raw, 2 + n)
    assert outer == inner + 4 and len(raw) == 2 + n + 8 + inner
    pre, fields, post = announce.parse(raw)
    assert announce.build(pre, fields, post) == raw
    assert announce.gid_of(raw) == 0x201
    assert fields[-1] == b"Nice to meet you!" and post == b"\x01\x00\x00"
    assert announce.parse(b"\x05\x00junk") is None
    assert announce.parse(raw[:-5]) is None


def test_message_from_scratch_matches_a_player_message():
    built = announce.message_for(0x202, "", "Restart soon")
    real = _player_shout(0x202, hall="", text="Restart soon")
    bp, rp = announce.parse(built), announce.parse(real)
    assert bp[0] == rp[0] and bp[2] == rp[2]                 # same header + trailer
    assert bp[1][3:6] == [b"Server", announce.SENDER.encode(), b"eng"]
    assert bp[1][:3] == rp[1][:3] and bp[1][6:] == rp[1][6:]


def test_hall_name_is_always_empty():
    # A game drops chat whose hall name isn't its own for that hall (language-dependent),
    # unless it's empty (tested in game on US and JP).
    assert announce.parse(announce.message_for(0x201, "", "Hi"))[1][0] == b""


def test_template_keeps_the_games_room_text_but_not_its_hall_name():
    announce._templates.clear()
    announce.remember(_player_shout(0x1001, hall="Américas", room="Hunt 80", lang="jpn"))
    fields = announce.parse(announce.message_for(0x1001, "", "Hi"))[1]
    assert fields[:3] == [b"", b"Lobby", b"Hunt 80"]
    assert fields[5] == b"eng" and fields[-1] == b"Hi"       # Western builds drop "jpn"
    announce._templates.clear()


def test_templates_are_bounded():
    announce._templates.clear()
    for gid in range(0x1000, 0x1000 + announce.TEMPLATES_MAX + 10):
        announce.remember(_player_shout(gid))
    assert len(announce._templates) == announce.TEMPLATES_MAX
    assert 0x1000 not in announce._templates
    announce._templates.clear()


def test_split():
    assert announce.split("a  b\tc\nd") == ["a b c d"]
    parts = announce.split("Server update tonight at 8pm ET, please finish hunts", 20)
    assert all(len(p) <= 20 for p in parts) and " ".join(parts).startswith("Server update")
    assert announce.split("x" * 45, 20) == ["x" * 20, "x" * 20, "x" * 5]
    assert len(announce.split("word " * 200, 10)) == announce.MAX_PARTS
    assert announce.split("   ") == []


class _Conn:
    def __init__(self):
        self.sent = []

    async def request(self, proto, method, body, noresponse=False):
        self.sent.append((proto, method, bytes(body), noresponse))


def _world(monkeypatch):
    monkeypatch.setattr(mh, "HALL_NAMES", ["Americas"])
    monkeypatch.setattr(mh, "HALL_NAMES_LANGS", [["Americas"] * mh.HALL_LANGS])
    monkeypatch.setattr(mh, "HALL_NAMES_JP", ["アメリカ"])
    monkeypatch.setattr(mh, "NUM_WORLDS", 1)
    r = mh.CommunityRegistry()
    monkeypatch.setattr(mh, "COMMUNITY", r)
    clients, reg = {}, mh.GatheringRegistry()
    monkeypatch.setattr(mh, "CLIENTS", clients)
    monkeypatch.setattr(mh, "REGISTRY", reg)
    return r, clients, reg


def test_each_player_gets_their_own_room_or_lobby(monkeypatch):
    r, clients, reg = _world(monkeypatch)
    west, jp, hunter = _Conn(), _Conn(), _Conn()
    clients.update({1: west, 2: jp, 3: hunter, 4: _Conn()})   # 4: online, in no gathering
    west._mh3u_world, jp._mh3u_world, hunter._mh3u_world = 0x101, 0x111, 0x101
    r.communities[0x201].participants.add(1)
    r.communities[0x211].participants.add(2)
    r.communities[0x201].participants.add(3)
    room = reg.create(types.SimpleNamespace(description="Hunt 80"), 3)
    dest = announce.destinations()
    assert dest == {1: (0x201, ""), 2: (0x211, ""), 3: (room.gid, "Hunt 80")}
    assert set(announce.destinations("halls")) == {1, 2}
    assert set(announce.destinations("rooms")) == {3}

    reached, parts = asyncio.run(announce.send("Restart soon"))
    assert (reached, parts) == (3, 1)
    for conn, gid in ((west, 0x201), (jp, 0x211), (hunter, room.gid)):
        (proto, method, body, noresp), = conn.sent
        assert (proto, method, noresp) == (0x1B, 1, True)
        assert announce.gid_of(body) == gid
        assert announce.parse(body)[1][-1] == b"Restart soon"
    assert clients[4].sent == []


def test_each_player_gets_the_notice_in_their_language(monkeypatch):
    r, clients, reg = _world(monkeypatch)
    us, es, jp, quiet = _Conn(), _Conn(), _Conn(), _Conn()
    clients.update({1: us, 2: es, 3: jp, 4: quiet})
    jp._mh3u_jp = True
    for pid in (1, 2, 4):
        r.communities[0x201].participants.add(pid)
    r.communities[0x211].participants.add(3)
    announce._langs.clear()
    announce.remember(_player_shout(0x201, lang="eng"), 1)
    announce.remember(_player_shout(0x201, lang="spa"), 2)
    announce.remember(_player_shout(0x211, lang="jpn"), 3)
    assert [announce.language_of(p) for p in (1, 2, 3, 4)] == ["eng", "spa", "jpn", "eng"]

    import maintenance
    asyncio.run(announce.send(maintenance.MSG_NOW))
    for pid, lang, tag in ((1, "eng", b"eng"), (2, "spa", b"eng"), (3, "jpn", b"jpn"),
                           (4, "eng", b"eng")):
        fields = [announce.parse(s[2])[1] for s in clients[pid].sent]
        assert b" ".join(f[-1] for f in fields) == maintenance.MSG_NOW[lang].encode()
        assert {f[5] for f in fields} == {tag}       # Western builds drop "jpn"
    asyncio.run(announce.send("Plain text"))         # the host's own: one text for all
    assert {announce.parse(c.sent[-1][2])[1][-1] for c in clients.values()} == {b"Plain text"}
    for msgs in (maintenance.MSG_PENDING, maintenance.MSG_NOW, maintenance.msg_soon(5)):
        assert set(msgs) == {"eng", "jpn", "fre", "ger", "ita", "spa"}
        for lang, text in msgs.items():              # each notice is one chat message
            assert announce.parts_in(msgs, lang)[1] == [text], (lang, text)
    announce._langs.clear()


def test_restart_waits_for_rooms_to_empty(monkeypatch):
    r, clients, reg = _world(monkeypatch)
    said, fired = [], []

    async def fake_send(text, scope="all"):
        said.append(text)
        return len(clients), 1
    monkeypatch.setattr(announce, "send", fake_send)
    monkeypatch.setattr(maintenance, "TICK", 0.01)
    monkeypatch.setattr(maintenance, "FINAL_PAUSE", 0.0)
    monkeypatch.setattr(maintenance, "on_restart", lambda: fired.append(True))
    clients.update({1: _Conn(), 2: _Conn()})
    room = reg.create(types.SimpleNamespace(), 1)
    room.participants.add(2)

    async def run():
        task = asyncio.create_task(maintenance.loop())
        maintenance.schedule("idle", 60)
        await asyncio.sleep(0.1)
        assert not fired and said == [maintenance.MSG_PENDING]      # one notice, then waits
        assert maintenance.status()["players_in_rooms"] == 2
        room.participants.clear()                                   # the hunt is over
        await asyncio.sleep(0.1)
        task.cancel()
    try:
        asyncio.run(run())
    finally:
        maintenance._plan = None
    assert fired == [True] and said[-1] == maintenance.MSG_NOW


def test_restart_deadline_warnings(monkeypatch):
    r, clients, reg = _world(monkeypatch)
    said = []

    async def fake_send(text, scope="all"):
        said.append(text)
        return 1, 1
    monkeypatch.setattr(announce, "send", fake_send)
    clients[1] = _Conn()
    reg.create(types.SimpleNamespace(), 1)
    plan = maintenance.schedule("idle", 3)
    assert plan["scheduled"] and plan["wait"] == "idle"
    monkeypatch.setattr(maintenance, "TICK", 0.0)

    async def one_tick():
        task = asyncio.create_task(maintenance.loop())
        await asyncio.sleep(0.05)
        task.cancel()
    try:
        asyncio.run(one_tick())
        assert said == [maintenance.msg_soon(3)]                     # not "5 minutes"
        maintenance._plan.deadline -= 150                            # ~30 s left
        asyncio.run(one_tick())
        assert said[-1] == maintenance.msg_soon(1)
        assert maintenance.cancel() is True and maintenance.status() == {"scheduled": False}
        assert maintenance.cancel() is False
    finally:
        maintenance._plan = None


def _admin(method, target, body=b""):
    resp = asyncio.run(admin_http.handle(method, target, body))
    head, _, payload = resp.partition(b"\r\n\r\n")
    return int(head.split()[1]), json.loads(payload)


def test_admin_routes(monkeypatch):
    sent = []

    async def fake_send(text, scope="all"):
        sent.append((text, scope))
        return 2, 1
    monkeypatch.setattr(announce, "send", fake_send)
    assert _admin("POST", "/announce", b"Hello hunters") == (
        200, {"players": 2, "messages": 1, "parts": ["Hello hunters"]})
    assert _admin("POST", "/announce?scope=halls", b"x")[0] == 200
    assert sent == [("Hello hunters", "all"), ("x", "halls")]
    assert _admin("POST", "/announce", b"  ")[0] == 400
    assert _admin("POST", "/announce?scope=everyone", b"x")[0] == 400
    assert _admin("GET", "/announce")[0] == 405
    try:
        code, st = _admin("POST", "/restart?wait=empty&max_minutes=5")
        assert code == 200 and st["wait"] == "empty" and st["deadline_in_s"] <= 300
        assert _admin("GET", "/restart")[1]["scheduled"] is True
        assert _admin("POST", "/restart?wait=later")[0] == 400
        assert _admin("POST", "/restart/cancel") == (200, {"cancelled": True})
    finally:
        maintenance._plan = None
    assert _admin("GET", "/nope")[0] == 404


def test_admin_listens_on_localhost_only():
    assert admin_http.HOST == "127.0.0.1"

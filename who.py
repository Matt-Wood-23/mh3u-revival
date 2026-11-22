"""Who's online, for the host: hunter names, where they are, what language they chat in.

Read through the admin port only (admin_http.py, 127.0.0.1); the public status page never
shows names. Everything here is kept on the connection objects, so it goes away with them.

The hunter name and HR come from the game's own presence string (update_notification_data
type 101), tab-separated:
    state | world gid | lobby gid | room gid | ? | room name | in room | room max |
    hunter name | HR | ...
The account (e.g. "CemuMH3U01", what the chat shows) is only known once the player chats.
"""
import logging
import time

import announce
import matchmaking_handlers as mh

logger = logging.getLogger("mh3u.admin")

def note_shout(client, raw):
    """A chat message: keep the sender's account name."""
    p = announce.parse(raw)
    if p and client is not None:
        client._mh3u_account = p[1][3].decode("utf-8", "replace")[:32]


def _status_fields(conn):
    return (getattr(conn, "_mh3u_status", "") or "").split("\t")


def _hunter(conn):
    f = _status_fields(conn)
    return f[8] if len(f) > 8 else ""


def find_player(player):
    """(pid, connection) of a player online now, by PID or hunter name (any case)."""
    live = mh.CLIENTS
    s = str(player).strip()
    if s.isdigit() and int(s) in live:
        return int(s), live[int(s)]
    hits = [(pid, c) for pid, c in list(live.items()) if s and _hunter(c).lower() == s.lower()]
    if len(hits) == 1:
        return hits[0]
    if hits:
        raise LookupError("%d players online are called %r; use the PID" % (len(hits), s))
    raise LookupError("nobody called %r is online" % s)


def set_master_key(player, on=True):
    pid, conn = find_player(player)
    conn._mh3u_master_key = bool(on)
    logger.warning("master key %s: pid=%s (%s)", "given" if on else "taken back", pid,
                   _hunter(conn) or "?")
    return {"pid": pid, "hunter": _hunter(conn), "master_key": bool(on)}


def _hall_label(world_gid):
    c = mh.COMMUNITY.communities.get(world_gid)
    return getattr(c, "label", "") or ""


def snapshot(now=None):
    """{"players": [...], "rooms": [...]} for the admin page."""
    now = time.time() if now is None else now
    live = mh.CLIENTS
    room_of, password_of, rooms = {}, {}, []
    for s in mh.REGISTRY.sessions.values():
        members = sorted(p for p in s.participants if p in live)
        name = ""
        for p in members:                          # the game's own name for the room
            f = _status_fields(live[p])
            if len(f) > 5 and f[0] == "3" and f[5]:
                name = f[5]
                break
        name = name or getattr(s.gathering, "description", "") or ""
        password = mh.room_password(s.gathering)
        rooms.append({"gid": "0x%x" % s.gid, "name": name, "players": len(members),
                      "password": password})
        for p in members:
            room_of[p] = name
            password_of[p] = password
    hall_of = {}
    for world_gid, lobby_gid in mh.COMMUNITY.lobbies.items():
        for p in getattr(mh.COMMUNITY.communities.get(lobby_gid), "participants", ()):
            hall_of[p] = _hall_label(world_gid)
    players = []
    for pid, conn in list(live.items()):
        f = _status_fields(conn)
        since = getattr(conn, "_mh3u_since", None)
        jp = getattr(conn, "_mh3u_jp", None)
        players.append({
            "pid": pid,
            "hunter": _hunter(conn),
            "hr": f[9] if len(f) > 9 else "",
            "account": getattr(conn, "_mh3u_account", ""),
            "game": "JP" if jp else ("US/EU" if jp is False else ""),
            "language": announce._langs.get(pid, ""),
            "hall": hall_of.get(pid) or _hall_label(getattr(conn, "_mh3u_world", None)),
            "room": room_of.get(pid, ""),
            "room_password": password_of.get(pid, ""),
            "master_key": bool(getattr(conn, "_mh3u_master_key", False)),
            "online_s": int(now - since) if since else None,
        })
    players.sort(key=lambda d: (d["hall"], d["room"], d["hunter"].lower()))
    rooms.sort(key=lambda r: r["name"].lower())
    return {"players": players, "rooms": rooms}

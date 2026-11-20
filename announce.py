"""Server announcements: a hall/room chat message from "Server", shown in every game.

MH3U's chat message ("shout") is a NEX UserMessage anydata whose body is (decoded from
captures on the official server, 2026-11-20, US/EU/JP builds):

    u32 0 | u32 gathering id | u32 2 | 20 zero bytes | u32 1      (36 bytes)
    string  hall \\t Lobby \\t room \\t account \\t hunter name \\t language \\t \\t \\t M \\t text
    01 00 00

The gathering id is the room's gid inside a room, or the hall's lobby gid (0x20N; the JP
copy 0x21N) in the hall. Western builds drop "jpn" messages, and "eng" shows in every
build. So an announcement is built per recipient: their room or lobby gid, tagged "eng",
with an EMPTY hall name (below). Where a player already chatted in that gathering, their
message is the template (it carries the exact room text the game wrote).

Tested in game (2026-11-20, US + JP Cemus on a local server):
  - the chat shows the ACCOUNT field as the sender ("Server:"), not the hunter name, and
    the game shows messages from an account that isn't in the hall;
  - the game drops a message whose hall name isn't its OWN name for that hall, unless
    the hall name is empty: "Gathering Hall 1" was dropped (that game had stored the
    name as ""), US "Asia/Oceania" vs JP "アジア・オセアニア" were dropped both ways,
    and "" showed on US and JP every time. An EU game's own name is in its language
    ("Amériques"), so an announcement can't know the right one: it always sends "";
  - text: up to ~80 characters show (the font shrinks past ~45); past that the rest is
    shown as "****". Hence 45 per message by default, 80 at most.

Languages: send() takes plain text (everyone gets it) or {language: text}. Each player
gets their own language when there's a version in it: JP-build players "jpn" (always
known), Western players the language tag of their own last chat message ("spa" and "deu"
seen in game, German and Spanish notices shown with their accents; French/Italian assumed
"fra"/"ita", "fre" also accepted), English otherwise. The automatic restart notices
(maintenance.py) come in all six; the host's own announcements are one text.
"""
import logging
import os
import re
import struct

from nintendo.nex import messaging

import limits
import matchmaking_handlers as mh

logger = logging.getLogger("mh3u.announce")

TYPE_NAME = b"UserMessage\x00"
SENDER = (os.environ.get("MH3U_ANNOUNCE_NAME", "").strip() or "Server")[:10]
ACCOUNT = "Server"
MAX_CHARS = min(80, max(10, limits._int_env("MH3U_ANNOUNCE_MAX_CHARS", 45)))  # per message
MAX_PARTS = 4                                                # messages per announcement

_templates = {}      # gid -> last real shout seen there (raw bytes), newest last
TEMPLATES_MAX = 256
_langs = {}          # pid -> language tag of the player's own chat, newest last
LANGS_MAX = 4096
WESTERN_LANGS = {"eng": "eng", "fre": "fre", "fra": "fre", "ger": "ger", "deu": "ger",
                 "ita": "ita", "spa": "spa"}
MAX_CHARS_JP = 20    # Japanese per message = one chat line in the JP game (tested)


def parse(raw):
    """raw shout -> (pre, fields, post), or None if it isn't the layout above."""
    try:
        raw = bytes(raw)
        n = struct.unpack_from("<H", raw, 0)[0]
        if raw[2:2 + n] != TYPE_NAME:
            return None
        o = 2 + n
        outer, inner = struct.unpack_from("<II", raw, o)
        body = raw[o + 8:o + 8 + inner]
        if outer != inner + 4 or len(body) != inner or inner < 38:
            return None
        pre = body[:36]
        length = struct.unpack_from("<H", body, 36)[0]
        text = body[38:38 + length]
        if len(text) != length or not text.endswith(b"\x00"):
            return None
        fields = text[:-1].split(b"\t")
        if len(fields) < 10:
            return None
        return pre, fields, body[38 + length:]
    except struct.error:
        return None


def build(pre, fields, post):
    text = b"\t".join(fields) + b"\x00"
    body = pre + struct.pack("<H", len(text)) + text + post
    return (struct.pack("<H", len(TYPE_NAME)) + TYPE_NAME
            + struct.pack("<II", len(body) + 4, len(body)) + body)


def gid_of(raw):
    p = parse(raw)
    return struct.unpack_from("<I", p[0], 4)[0] if p else None


def remember(raw, pid=None):
    """Keep a player's shout as the template for its gathering, and note the sender's
    language (called on every shout)."""
    p = parse(raw)
    if p is None:
        return
    gid = struct.unpack_from("<I", p[0], 4)[0]
    _templates.pop(gid, None)
    _templates[gid] = bytes(raw)
    while len(_templates) > TEMPLATES_MAX:          # rooms come and go; drop the oldest
        _templates.pop(next(iter(_templates)))
    if pid is not None:
        _langs.pop(pid, None)
        _langs[pid] = p[1][5].decode("ascii", "replace")
        while len(_langs) > LANGS_MAX:
            _langs.pop(next(iter(_langs)))


def language_of(pid):
    """The language to address a player in: "jpn" for the JP build, else the Western
    language they chat in, else "eng"."""
    if getattr(mh.CLIENTS.get(pid), "_mh3u_jp", None):
        return "jpn"
    return WESTERN_LANGS.get(_langs.get(pid), "eng")


def _clean(text):
    # One line of printable text: no tabs/newlines (they're the field separators).
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", text)).strip()


def split(text, limit=None):
    """Text -> chat-sized parts, split on spaces where possible."""
    limit = limit or MAX_CHARS
    words, parts, cur = _clean(text).split(" "), [], ""
    for w in words:
        while len(w) > limit:                       # a single over-long word
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(w[:limit])
            w = w[limit:]
        if not w:
            continue
        if cur and len(cur) + 1 + len(w) > limit:
            parts.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        parts.append(cur)
    return parts[:MAX_PARTS]


def message_for(gid, room, text, lang="eng"):
    """The announcement as a shout for gathering `gid` (`room`: the room's name, or "").
    `lang` is the tag: "eng" shows in every build, "jpn" only in the JP build."""
    p = parse(_templates[gid]) if gid in _templates else None
    if p:
        pre, fields, post = p
        fields = list(fields)
    else:
        pre = struct.pack("<III", 0, gid, 2) + bytes(20) + struct.pack("<I", 1)
        post = b"\x01\x00\x00"
        fields = [b"", b"Lobby", room.encode("utf-8"), b"", b"", b"", b"", b"", b"M", b""]
    fields[0] = b""                          # hall name: see the module docstring
    fields[3] = ACCOUNT.encode()
    fields[4] = SENDER.encode("utf-8")
    fields[5] = lang.encode("ascii")
    fields[-1] = text.encode("utf-8")
    return build(pre, fields, post)


def destinations(scope="all"):
    """pid -> (gid, room name or "") for every connected player in a room or hall.
    scope: "all", "halls" (players not in a room) or "rooms"."""
    out = {}
    live = set(mh.CLIENTS)
    in_room = set()
    for s in mh.REGISTRY.sessions.values():
        for pid in s.participants:
            in_room.add(pid)
            if pid in live and scope in ("all", "rooms"):
                out[pid] = (s.gid, getattr(s.gathering, "description", "") or "")
    if scope in ("all", "halls"):
        for world_gid, lobby_gid in mh.COMMUNITY.lobbies.items():
            lobby = mh.COMMUNITY.communities.get(lobby_gid)
            for pid in getattr(lobby, "participants", ()):
                if pid in live and pid not in in_room:
                    out[pid] = (lobby_gid, "")
    return out


def parts_in(texts, lang):
    """(tag, chat-sized parts) of the version of `texts` ({language: text}) for `lang`."""
    if lang in texts:
        return lang, split(texts[lang], MAX_CHARS_JP if lang == "jpn" else None)
    return "eng", split(texts["eng"])


async def send(text, scope="all"):
    """Announce `text` (a string, or {language: text} with an "eng" entry) to everyone
    (or one scope), each player in their own language where there's a version in it.
    Returns (players reached, parts of the English text)."""
    texts = text if isinstance(text, dict) else {"eng": text}
    english = split(texts["eng"])
    if not english:
        return 0, 0
    reached = 0
    for pid, (gid, room) in destinations(scope).items():
        conn = mh.CLIENTS.get(pid)
        if conn is None:
            continue
        tag, parts = parts_in(texts, language_of(pid))
        try:
            for part in parts:
                await conn.request(messaging.MessageDeliveryProtocol.PROTOCOL_ID,
                                   messaging.MessageDeliveryProtocol.METHOD_DELIVER_MESSAGE,
                                   message_for(gid, room, part, "jpn" if tag == "jpn" else "eng"),
                                   noresponse=True)
            reached += 1
        except Exception as e:
            logger.info("announce: to pid=%s failed: %s", pid, e)
    logger.info("ANNOUNCE (%s, %d part(s)) -> %d player(s): %r", scope, len(english), reached,
                texts["eng"])
    return reached, len(english)

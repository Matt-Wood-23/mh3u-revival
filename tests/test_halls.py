"""Gathering halls: a Western and a JP copy of each, one lobby per hall."""
import matchmaking_handlers as mh


def _registry(monkeypatch, names, jp=None):
    monkeypatch.setattr(mh, "HALL_NAMES", names)
    monkeypatch.setattr(mh, "HALL_NAMES_LANGS", [[n] * mh.HALL_LANGS for n in names])
    monkeypatch.setattr(mh, "HALL_NAMES_JP", jp or list(names))
    monkeypatch.setattr(mh, "NUM_WORLDS", len(names))
    return mh.CommunityRegistry()


def test_each_hall_has_a_western_and_a_jp_copy(monkeypatch):
    r = _registry(monkeypatch, ["Americas", "Europe"], ["アメリカ", "ヨーロッパ"])
    west, jp = r.communities[0x101].pg, r.communities[0x111].pg
    assert west.attribs[2] == mh.REGION_WEST and jp.attribs[2] == mh.REGION_JP
    assert west.description == ":".join(["Americas"] * 5)      # EU build: EN:FR:IT:DE:ES
    assert jp.description == "アメリカ"                         # JP build shows packed names empty
    assert r.communities[0x112].pg.description == "ヨーロッパ"
    assert {pg.id for pg in r.officials()} == {0x101, 0x102, 0x111, 0x112}
    # US/EU consoles widen their region mask to 6, a JP console keeps 1: each sees one copy.
    assert {pg.id for pg in r.officials() if pg.attribs[2] & 6} == {0x101, 0x102}
    assert {pg.id for pg in r.officials() if pg.attribs[2] & 1} == {0x111, 0x112}


def test_each_world_lists_only_its_own_lobby(monkeypatch):
    r = _registry(monkeypatch, ["Americas", "Europe"])
    assert r.lobbies == {0x101: 0x201, 0x102: 0x202, 0x111: 0x211, 0x112: 0x212}
    for world, lobby in r.lobbies.items():
        owner = r.communities[world].pg.attribs[1]
        assert [pg.id for pg in r.lobby_gatherings(owner)] == [lobby]
        assert r.communities[lobby].pg.owner == owner
        assert r.communities[lobby].pg.attribs[0] == lobby          # paired chat lobby
        assert [pg.id for pg in r.lobby_gatherings(0, world)] == [lobby]
    assert len(r.lobby_gatherings(0, None)) == 4                      # old behaviour


def test_status_counts_both_copies_as_one_hall(monkeypatch):
    import status_http
    r = _registry(monkeypatch, ["Americas", "Europe"], ["アメリカ", "ヨーロッパ"])
    r.join(0x101, 1001)
    r.join(0x111, 1002)
    r.join(0x102, 1003)
    monkeypatch.setattr(mh, "COMMUNITY", r)
    halls = status_http.snapshot()["halls"]
    assert [(h["name"], h["players"]) for h in halls] == [("Americas", 2), ("Europe", 1)]


def test_both_copies_share_population_and_type(monkeypatch):
    r = _registry(monkeypatch, ["Americas"])
    west, jp = r.communities[0x101], r.communities[0x111]
    assert west.twin is jp and jp.twin is west
    assert r.communities[0x201].twin is r.communities[0x211]
    r.join(0x101, 1001)                 # a US player
    r.join(0x111, 1002)                 # a JP player in the same hall
    # Both copies show 2 hunters (world list renders num - 2).
    assert west.pg.num_participants == jp.pg.num_participants == 2 + 2
    assert west.members() == jp.members() == {1001, 1002}
    r.leave(0x111, 1002)
    assert west.pg.num_participants == jp.pg.num_participants == 1 + 2
    # Worlds carry the hall type in attribs[0]; lobbies keep their own gid (chat lobby).
    assert west.pg.attribs[0] == jp.pg.attribs[0] == mh.HALL_TYPE == 1
    assert r.communities[0x201].pg.attribs[0] == 0x201


def test_hall_chat_reaches_the_other_build(monkeypatch):
    import protocols
    r = _registry(monkeypatch, ["Americas"])
    monkeypatch.setattr(mh, "COMMUNITY", r)
    monkeypatch.setattr(mh, "CLIENTS", {1001: object(), 1002: object(), 1003: object()})
    r.join(0x201, 1001)                 # US player in the Americas lobby
    r.join(0x211, 1002)                 # JP player in the Americas lobby (JP copy)
    assert protocols._shout_targets(1001) == {1001, 1002}


def test_rooms_point_at_the_viewers_own_lobby(monkeypatch):
    from types import SimpleNamespace
    from nintendo.nex import matchmaking
    r = _registry(monkeypatch, ["Americas", "Europe", "Asia/Oceania"])
    monkeypatch.setattr(mh, "COMMUNITY", r)
    room = matchmaking.MatchmakeSession()
    room.attribs = [1, 0x213, 1, 0, 0, 0, 0, 0, 0]       # made in the JP Asia/Oceania lobby
    room.application_data = bytes(0x134) + b""       # ...whose hall is 0x113
    us, jp, unknown = SimpleNamespace(), SimpleNamespace(), SimpleNamespace()
    us._mh3u_jp, jp._mh3u_jp = False, True                 # set by join_community
    seen = mh.room_view(us, room)
    assert seen is not room and seen.attribs[1] == 0x203   # the US build's Asia/Oceania lobby
    assert seen.attribs[2] == 2                            # and the Western region group
    assert seen.application_data[0x134] == 0x03            # and the Western hall 0x103
    assert room.application_data[0x134] == 0x13
    assert room.attribs[:3] == [1, 0x213, 1]               # the stored room is unchanged
    assert mh.room_view(jp, room) is room                  # same build: as is
    west_room = matchmaking.MatchmakeSession()
    west_room.attribs = [1, 0x201, 2, 0, 0, 0, 0, 0, 0]   # a US room in Americas
    assert mh.room_view(jp, west_room).attribs[:3] == [1, 0x211, 1]
    assert mh.room_view(us, west_room) is west_room
    assert mh.room_view(unknown, room) is room             # build not known yet: as is
    assert r.local_gid(0x203, True) == 0x213 and r.local_gid(0x1001, True) == 0x1001


def test_master_key_shows_locked_rooms_open(monkeypatch):
    from types import SimpleNamespace
    from nintendo.nex import matchmaking
    r = _registry(monkeypatch, ["Americas"])
    monkeypatch.setattr(mh, "COMMUNITY", r)
    data = bytearray(309)
    data[0] = 0x10
    data[0xC1:0xCB] = b"CemuMH3U01"
    data[0xF2:0xF6] = b"WXYZ"
    data[0x112:0x116] = b"matt"
    data[0x134] = 0x01
    room = matchmaking.MatchmakeSession()
    room.attribs = [1, 0x201, 2, 0, 0, 1, 0, 0, 0]
    room.application_data = bytes(data)
    assert mh.room_password(room) == "WXYZ"
    plain, keyed = SimpleNamespace(_mh3u_jp=False), SimpleNamespace(_mh3u_jp=False)
    keyed._mh3u_master_key = True
    assert mh.room_view(plain, room) is room
    seen = mh.room_view(keyed, room)
    assert seen.attribs[5] == 0 and mh.room_password(seen) == ""
    assert seen.application_data[0xF2:0xF6] == bytes(4)
    assert seen.application_data[:0xF2] == bytes(data[:0xF2])
    assert seen.application_data[0xF6:] == bytes(data[0xF6:])
    assert room.attribs[5] == 1 and mh.room_password(room) == "WXYZ"
    open_room = matchmaking.MatchmakeSession()
    open_room.attribs = [1, 0x201, 2, 0, 0, 0, 0, 0, 0]
    open_room.application_data = bytes(309)
    assert mh.room_view(keyed, open_room) is open_room
    jp_room = matchmaking.MatchmakeSession()
    jp_room.attribs = [1, 0x211, 1, 0, 0, 1, 0, 0, 0]
    jp_room.application_data = bytes(data[:0x134]) + b"\x11"
    seen = mh.room_view(keyed, jp_room)
    assert seen.attribs[:3] == [1, 0x201, 2] and seen.attribs[5] == 0
    assert seen.application_data[0x134] == 0x01 and mh.room_password(seen) == ""
    assert mh.room_password(SimpleNamespace(application_data=b"")) == ""


def test_rooms_are_listed_only_in_their_hall(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from nintendo.nex import matchmaking
    r = _registry(monkeypatch, ["Americas", "Europe"])
    monkeypatch.setattr(mh, "COMMUNITY", r)
    monkeypatch.setattr(mh, "REGISTRY", mh.GatheringRegistry())

    def room(host, attribs, hall_byte=None):
        g = matchmaking.MatchmakeSession()
        g.attribs = attribs
        g.application_data = bytes(309) if hall_byte is None else bytes(0x134) + bytes([hall_byte])
        return mh.REGISTRY.create(g, host).gid

    americas = room(1, [1, 0x201, 2, 0, 0, 0, 0, 0, 0], 0x01)        # US player, Americas
    europe = room(2, [1, 0x202, 2, 0, 0, 0, 0, 0, 0], 0x02)          # the room in the screenshot
    jp_americas = room(3, [1, 0x211, 1, 0, 0, 0, 0, 0, 0], 0x11)     # JP player, Americas
    by_byte = room(4, [1, 0, 2, 0, 0, 0, 0, 0, 0], 0x02)             # lobby unknown: hall byte
    nowhere = room(5, [], None)                                       # can't tell: every hall
    assert mh.room_hall(mh.REGISTRY.sessions[jp_americas].gathering) == 0x101
    assert mh.room_hall(mh.REGISTRY.sessions[by_byte].gathering) == 0x102
    assert mh.room_hall(mh.REGISTRY.sessions[nowhere].gathering) is None

    srv = mh.MatchmakeExtensionServer()
    everything = SimpleNamespace(offset=0, size=0)

    def listed(**client):
        rooms = asyncio.run(srv.browse_matchmake_session(
            SimpleNamespace(pid=9, **client), None, everything))
        return {g.id for g in rooms}

    assert listed(_mh3u_world=0x101, _mh3u_jp=False) == {americas, jp_americas, nowhere}
    assert listed(_mh3u_world=0x111, _mh3u_jp=True) == {americas, jp_americas, nowhere}
    assert listed(_mh3u_world=0x102, _mh3u_jp=False) == {europe, by_byte, nowhere}
    assert listed() == {americas, europe, jp_americas, by_byte, nowhere}   # hall not known yet


def test_hall_names_with_translations():
    langs = mh._hall_langs("Americas|Amériques|Americhe|Amerika|Américas, Europe|| Europa ,Asia", 1)
    assert langs[0] == ["Americas", "Amériques", "Americhe", "Amerika", "Américas"]
    assert langs[1] == ["Europe", "Europe", "Europa", "Europe", "Europe"]   # blanks -> English
    assert langs[2] == ["Asia"] * 5
    assert mh._hall_names("Americas|Amériques,Europe", 1) == ["Americas", "Europe"]
    assert mh._hall_langs(None, 2) == [["Gathering Hall 1"] * 5, ["Gathering Hall 2"] * 5]


def test_lobby_roster_lists_both_builds(monkeypatch):
    r = _registry(monkeypatch, ["Asia/Oceania"])
    monkeypatch.setattr(mh, "COMMUNITY", r)
    r.join(0x201, 1001)                 # US player in the Western lobby
    r.join(0x211, 1002)                 # JP room host in the JP copy of the lobby
    assert [d.pid for d in mh.participant_details(0x201)] == [1001, 1002]
    assert [d.pid for d in mh.participant_details(0x211)] == [1001, 1002]


def test_jp_shouts_reach_western_players_tagged_eng():
    import announce
    import protocols
    # A real JP room shout (captured 2026-11-20), the bytes up to and after the context string.
    jp = bytes.fromhex(
        "0c00557365724d657373616765009600000092000000000000000110000002000000000000000000"
        "0000000000000000000000000000010000006900") + (      # 36-byte header
        "Asia/Oceania\tLobby\t一狩りいこうぜ071\tCemuMH3U318b\tてst\tjpn\t\t\tM\t"
        "よろしくお願いします！").encode() + b"\x00\x01\x00\x00"
    orig = announce.parse(jp)[1]
    us_view = announce.parse(protocols._shout_for(jp, True, False))[1]
    assert us_view[5] == b"eng" and us_view[0] == b""               # tag + hall name
    assert us_view[1:5] == orig[1:5] and us_view[6:] == orig[6:]    # nothing else
    for s_jp, r_jp in ((True, True), (True, None), (False, False)):   # no "jpn" -> "eng"
        f = announce.parse(protocols._shout_for(jp, s_jp, r_jp))[1]
        assert f[5] == b"jpn" and f[0] == b"" and f[1:5] == orig[1:5]


def test_relayed_shout_keeps_an_empty_hall_name_and_unknown_layouts_as_is():
    import announce
    import protocols
    raw = announce.build(bytes(36), [b"", b"Lobby", b"", b"A", b"n", b"eng", b"", b"", b"M",
                                     b"x"], b"\x01\x00\x00")
    assert protocols._shout_for(raw, False, False) is raw
    assert protocols._shout_for(b"junk", True, False) == b"junk"


def test_hall_chat_between_builds_gets_the_recipients_lobby_gid(monkeypatch):
    # US <-> JP hall chat didn't show (2026-11-20): each build sits in its own copy of the
    # hall's lobby (0x20N / 0x21N) and drops chat carrying the other copy's gid.
    import announce
    import protocols
    r = _registry(monkeypatch, ["Americas", "Europe", "Asia/Oceania"])
    monkeypatch.setattr(mh, "COMMUNITY", r)

    def shout(gid, lang, hall=b"Asia/Oceania"):
        pre, fields, post = announce.parse(announce.message_for(gid, "", "Hi"))
        fields = list(fields)
        fields[0], fields[5] = hall, lang
        return announce.build(pre, fields, post)

    us = shout(0x203, b"eng")
    to_jp = protocols._shout_for(us, False, True)
    assert announce.gid_of(to_jp) == 0x213
    assert announce.parse(to_jp)[1][1:] == announce.parse(us)[1][1:]   # text untouched
    assert announce.parse(to_jp)[1][0] == b""                          # hall name blanked
    jp = shout(0x213, b"jpn", "アジア・オセアニア".encode())
    to_us = protocols._shout_for(jp, True, False)
    assert announce.gid_of(to_us) == 0x203 and announce.parse(to_us)[1][5] == b"eng"
    room = shout(0x1001, b"eng")                                    # rooms share one gid
    assert announce.gid_of(protocols._shout_for(room, False, True)) == 0x1001
    assert announce.gid_of(protocols._shout_for(us, False, False)) == 0x203  # same build

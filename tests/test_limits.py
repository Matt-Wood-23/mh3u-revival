"""Abuse / DoS guardrail tests (limits.py + the registry caps it drives).

Fast, deterministic, no network: exercises each hardening finding (F1-F6) directly against
the registry methods and the limits primitives, with the caps monkeypatched low so they bite
at small numbers. Asserts BOTH that a cap rejects abuse AND that normal use is untouched.

The happy-path end-to-end flow (create/browse/join, halls) is covered by test_matchmaking.py
and test_community.py — run those too; together they prove the guards are invisible to a
normal game while stopping the abuse cases below.

Run:  python tests/test_limits.py   (from the mh3u_server/ dir)
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # mh3u_server/
sys.path.insert(0, os.path.join(_ROOT, "..", "external", "NintendoClients"))
sys.path.insert(0, _ROOT)

os.environ.setdefault("MH3U_HOST_FREE", "0")   # no host Cemu in a unit test

import asyncio

from nintendo.nex import common, matchmaking

import limits
import matchmaking_handlers as mh
import protocols


def _session(max_participants=4):
    s = matchmaking.MatchmakeSession()
    s.game_mode = 1
    s.attribs = [0, 0, 0, 0, 0, 0]
    s.min_participants = 1
    s.max_participants = max_participants
    s.open_participation = True
    return s


def _persistent(owner=0):
    pg = matchmaking.PersistentGathering()
    pg.min_participants = 1
    pg.max_participants = 4
    pg.participation_policy = 1
    pg.flags = 512
    pg.description = "runtime hall"
    pg.type = 1
    pg.password = ""
    pg.attribs = [0, 0, 0xFFFFFFFF, 0, 0, 0]
    pg.application_buffer = b""
    pg.participation_start = common.DateTime.make(2013, 1, 1)
    pg.participation_end = common.DateTime.future()
    pg.matchmake_session_count = 0
    pg.num_participants = 0
    return pg


# --- F2: global room cap -------------------------------------------------------------
def test_room_cap():
    old = limits.MAX_ROOMS
    limits.MAX_ROOMS = 3
    try:
        reg = mh.GatheringRegistry()
        for i in range(3):
            reg.create(_session(), host_pid=1000 + i)     # 3 distinct-PID rooms OK
        assert len(reg.sessions) == 3
        try:
            reg.create(_session(), host_pid=2000)          # 4th must be rejected
            assert False, "room cap did not fire"
        except common.RMCError as e:
            assert "LimitExceeded" in str(e), str(e)
    finally:
        limits.MAX_ROOMS = old
    print("  F2 room cap: OK")


# --- F4: room fail-safe ceiling (NOT the game's 4-player max) -------------------------
def test_room_capacity_ceiling():
    # The cap is a pure anti-abuse ceiling, independent of the room's DECLARED max — a normal
    # 4-player room (declared max 4) must NOT be capped near 4 (that would bounce a legit
    # replacement joiner during the ghost window). Enforcement is only at MAX_ROOM_PARTICIPANTS.
    old = limits.MAX_ROOM_PARTICIPANTS
    limits.MAX_ROOM_PARTICIPANTS = 3
    try:
        reg = mh.GatheringRegistry()
        # declared max is small (4) but the ceiling (3) is what bites — proves we ignore declared max
        sess = reg.create(_session(max_participants=4), host_pid=1)   # host = participant #1
        reg.join(sess.gid, 2)                                         # #2
        reg.join(sess.gid, 3)                                         # #3 -> at ceiling
        try:
            reg.join(sess.gid, 4)                                     # #4 rejected by ceiling
            assert False, "room ceiling did not fire"
        except common.RMCError as e:
            assert "SessionFull" in str(e), str(e)
        reg.join(sess.gid, 2)                                         # re-join existing pid idempotent-OK
        assert reg.sessions[sess.gid].participants == {1, 2, 3}
    finally:
        limits.MAX_ROOM_PARTICIPANTS = old
    print("  F4 room ceiling (not declared max): OK")


# --- F3: destroy ownership -----------------------------------------------------------
def test_destroy_ownership():
    reg = mh.GatheringRegistry()
    sess = reg.create(_session(), host_pid=100)
    gid = sess.gid
    assert reg.destroy(gid, owner_pid=200) == "denied"     # a non-host cannot destroy
    assert gid in reg.sessions
    assert reg.destroy(gid, owner_pid=100) == "destroyed"  # the host can
    assert gid not in reg.sessions
    assert reg.destroy(gid, owner_pid=100) == "not_found"  # already gone
    print("  F3 destroy ownership: OK")


async def test_unregister_handler_ownership():
    # The MatchMaking.UnregisterGathering handler must deny a non-host but still ack True.
    class FakeClient:
        def __init__(self, pid):
            self._pid = pid
        def pid(self):
            return self._pid

    reg = mh.GatheringRegistry()
    saved = mh.REGISTRY
    mh.REGISTRY = reg                                       # point the handler at our fresh registry
    try:
        sess = reg.create(_session(), host_pid=100)
        srv = protocols.MatchMakingServer()
        acked = await srv.unregister_gathering(FakeClient(200), sess.gid)   # griefer
        assert acked is True and sess.gid in reg.sessions, "griefer destroyed a room they don't own"
        acked = await srv.unregister_gathering(FakeClient(100), sess.gid)   # real host
        assert acked is True and sess.gid not in reg.sessions
    finally:
        mh.REGISTRY = saved
    print("  F3 unregister handler ownership: OK")


# --- F1: community creation cap + cleanup --------------------------------------------
def test_community_cap_and_reap():
    old_g, old_o = limits.MAX_RUNTIME_COMMUNITIES, limits.MAX_COMMUNITIES_PER_OWNER
    limits.MAX_RUNTIME_COMMUNITIES = 4
    limits.MAX_COMMUNITIES_PER_OWNER = 2
    try:
        com = mh.CommunityRegistry()
        officials = len(com.officials())
        assert officials >= 1
        com.create(_persistent(), owner=100)
        com.create(_persistent(), owner=100)
        try:
            com.create(_persistent(), owner=100)           # 3rd for this owner -> per-owner cap
            assert False, "per-owner community cap did not fire"
        except common.RMCError as e:
            assert "CreationMax" in str(e), str(e)
        com.create(_persistent(), owner=200)
        com.create(_persistent(), owner=201)               # now 4 runtime -> global cap
        try:
            com.create(_persistent(), owner=202)
            assert False, "global community cap did not fire"
        except common.RMCError as e:
            assert "CreationMax" in str(e), str(e)
        # cleanup: reap_owner removes only that owner's runtime halls, never officials
        gone = com.reap_owner(100)
        assert len(gone) == 2
        assert len(com.officials()) == officials, "reap_owner destroyed an official hall!"
        assert len(com._runtime()) == 2                    # owners 200 + 201 remain
    finally:
        limits.MAX_RUNTIME_COMMUNITIES, limits.MAX_COMMUNITIES_PER_OWNER = old_g, old_o
    print("  F1 community cap + reap: OK")


# --- F5: shout rate limit + broadcast-fallback gate ----------------------------------
def test_shout_rate_limit():
    old_b, old_r = limits.SHOUT_BURST, limits.SHOUTS_PER_SEC
    limits.SHOUT_BURST = 2
    limits.SHOUTS_PER_SEC = 0.001                          # effectively no refill within the test
    limits._shout_buckets.clear()
    try:
        assert limits.shout_allowed(42) is True            # burst token 1
        assert limits.shout_allowed(42) is True            # burst token 2
        assert limits.shout_allowed(42) is False           # empty -> dropped
        assert limits.shout_allowed(99) is True            # a different sender has its own bucket
    finally:
        limits.SHOUT_BURST, limits.SHOUTS_PER_SEC = old_b, old_r
        limits._shout_buckets.clear()
    print("  F5 shout rate limit: OK")


def test_shout_broadcast_gate():
    # With the fallback OFF, an untracked sender's shout must NOT fan out to unrelated players.
    saved_clients = dict(mh.CLIENTS)
    saved_sessions = dict(mh.REGISTRY.sessions)
    old = limits.SHOUT_BROADCAST_FALLBACK
    try:
        mh.CLIENTS.clear()
        mh.CLIENTS.update({1: object(), 2: object(), 3: object()})
        mh.REGISTRY.sessions.clear()                       # sender 1 is in no tracked gathering
        limits.SHOUT_BROADCAST_FALLBACK = True
        assert protocols._shout_targets(1) == {1, 2, 3}    # beta: broadcast to all
        limits.SHOUT_BROADCAST_FALLBACK = False
        assert protocols._shout_targets(1) == {1}          # hardened: sender-only, no amplification
    finally:
        mh.CLIENTS.clear(); mh.CLIENTS.update(saved_clients)
        mh.REGISTRY.sessions.clear(); mh.REGISTRY.sessions.update(saved_sessions)
        limits.SHOUT_BROADCAST_FALLBACK = old
    print("  F5 broadcast-fallback gate: OK")


# --- F2/F7: connection accounting primitives -----------------------------------------
def test_connection_caps():
    old = limits.MAX_CONNECTIONS
    limits.MAX_CONNECTIONS = 2
    try:
        # reconnect (pid already present) never blocked
        assert limits.global_connection_ok(is_new_pid=False, current_count=99)[0] is True
        assert limits.global_connection_ok(is_new_pid=True, current_count=1)[0] is True
        assert limits.global_connection_ok(is_new_pid=True, current_count=2)[0] is False
    finally:
        limits.MAX_CONNECTIONS = old

    old_ip = limits.MAX_CONNECTIONS_PER_IP
    limits.MAX_CONNECTIONS_PER_IP = 2
    limits._ip_conns.clear()
    try:
        assert limits.is_loopback("127.0.0.1") and limits.ip_can_connect("127.0.0.1")[0] is True
        limits.ip_add("127.0.0.1"); limits.ip_add("127.0.0.1")   # loopback never tracked
        assert limits._ip_conns == {}
        ip = "26.1.2.3"
        assert limits.ip_can_connect(ip)[0] is True
        limits.ip_add(ip); limits.ip_add(ip)
        assert limits.ip_can_connect(ip)[0] is False            # per-IP cap reached
        limits.ip_remove(ip)
        assert limits.ip_can_connect(ip)[0] is True             # frees on disconnect
        limits.ip_remove(ip)
        assert ip not in limits._ip_conns
    finally:
        limits.MAX_CONNECTIONS_PER_IP = old_ip
        limits._ip_conns.clear()
    print("  F2/F7 connection caps: OK")


def test_bound_list():
    old = limits.MAX_GID_LIST
    limits.MAX_GID_LIST = 5
    try:
        assert limits.bound_list(range(100)) == [0, 1, 2, 3, 4]
        assert limits.bound_list([1, 2]) == [1, 2]
        assert limits.bound_list(None) == []                    # fail-open
    finally:
        limits.MAX_GID_LIST = old
    print("  F2 list bounding: OK")


def main():
    test_room_cap()
    test_room_capacity_ceiling()
    test_destroy_ownership()
    asyncio.run(test_unregister_handler_ownership())
    test_community_cap_and_reap()
    test_shout_rate_limit()
    test_shout_broadcast_gate()
    test_connection_caps()
    test_bound_list()
    print(">>> LIMITS OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

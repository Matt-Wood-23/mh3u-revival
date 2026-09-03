"""Focused tests for the optional UDP gameplay relay.

Run:  python tests/test_relay.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "..", "external", "NintendoClients"))
sys.path.insert(0, _ROOT)

import asyncio

from nintendo.nex import common

import config
import matchmaking_handlers as mh
import protocols
import relay
import relay_policy


class Client(asyncio.DatagramProtocol):
    def __init__(self):
        self.q = asyncio.Queue()
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self.q.put_nowait((data, addr))


async def _client():
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(
        Client, local_addr=("127.0.0.1", 0))
    return transport, protocol


async def test_pair_relay():
    old = (
        config.RELAY_MODE, config.HOST, config.RELAY_ADDRESS,
        config.RELAY_PORT_START, config.RELAY_PORT_END,
    )
    config.RELAY_MODE = "force"
    config.HOST = "127.0.0.1"
    config.RELAY_ADDRESS = "127.0.0.1"
    config.RELAY_PORT_START = 0
    config.RELAY_PORT_END = 0

    manager = relay.RelayManager()
    a_transport = b_transport = None
    try:
        station = common.StationURL(
            scheme="prudp", address="10.0.0.1", port=50000,
            PID=100, CID=0, RVCID=0x1234, type=3, sid=15, stream=10,
        )
        relayed = await manager.station_for(0x1001, 100, 200, station)
        assert relayed["address"] == "127.0.0.1"
        assert relayed["port"] != 50000
        assert relayed["PID"] == 100
        assert relayed["RVCID"] == 0x1234

        a_transport, a = await _client()
        b_transport, b = await _client()
        dst = ("127.0.0.1", relayed["port"])

        a_transport.sendto(b"first", dst)      # learns A; B unknown -> BUFFERED
        await asyncio.sleep(0.05)
        assert a.q.empty() and b.q.empty()

        b_transport.sendto(b"probe", dst)      # learns B; forwards to A
        data, _ = await asyncio.wait_for(a.q.get(), timeout=1)
        assert data == b"probe"

        # "first" used to be silently discarded here. That discard is what broke
        # guest<->guest links, whose establishing probe is exactly this packet, so it
        # must now be flushed to B once B is known.
        data, _ = await asyncio.wait_for(b.q.get(), timeout=1)
        assert data == b"first"

        a_transport.sendto(b"hunt", dst)
        data, _ = await asyncio.wait_for(b.q.get(), timeout=1)
        assert data == b"hunt"
    finally:
        if a_transport:
            a_transport.close()
        if b_transport:
            b_transport.close()
        manager.close_all()
        (
            config.RELAY_MODE, config.HOST, config.RELAY_ADDRESS,
            config.RELAY_PORT_START, config.RELAY_PORT_END,
        ) = old


async def test_matchmaking_station_substitution():
    class FakeClient:
        def __init__(self, pid):
            self._pid = pid

        def pid(self):
            return self._pid

    old_config = (
        config.RELAY_MODE, config.HOST, config.RELAY_ADDRESS,
        config.RELAY_PORT_START, config.RELAY_PORT_END,
    )
    old_manager = relay.MANAGER
    old_sessions = dict(mh.REGISTRY.sessions)
    old_stations = dict(mh.STATIONS)

    config.RELAY_MODE = "force"
    config.HOST = "127.0.0.1"
    config.RELAY_ADDRESS = "127.0.0.1"
    config.RELAY_PORT_START = 0
    config.RELAY_PORT_END = 0
    relay.MANAGER = relay.RelayManager()
    mh.REGISTRY.sessions.clear()
    mh.STATIONS.clear()

    try:
        sess = mh.REGISTRY.create(mh._placeholder_session(), host_pid=100)
        mh.REGISTRY.join(sess.gid, 200)
        mh.STATIONS[100] = common.StationURL(
            scheme="prudp", address="10.0.0.1", port=50000,
            PID=100, CID=0, RVCID=0x1234, type=3, sid=15, stream=10,
        )

        urls = await protocols.MatchMakingServer().get_session_urls(FakeClient(200), sess.gid)
        assert len(urls) == 1
        assert urls[0]["address"] == "127.0.0.1"
        assert urls[0]["port"] != 50000
        assert urls[0]["PID"] == 100
        assert urls[0]["RVCID"] == 0x1234
    finally:
        relay.MANAGER.close_all()
        relay.MANAGER = old_manager
        mh.REGISTRY.sessions.clear()
        mh.REGISTRY.sessions.update(old_sessions)
        mh.STATIONS.clear()
        mh.STATIONS.update(old_stations)
        (
            config.RELAY_MODE, config.HOST, config.RELAY_ADDRESS,
            config.RELAY_PORT_START, config.RELAY_PORT_END,
        ) = old_config


async def test_relay_port_released_on_guest_leave():
    old_config = (
        config.RELAY_MODE, config.HOST, config.RELAY_ADDRESS,
        config.RELAY_PORT_START, config.RELAY_PORT_END,
    )
    old_manager = relay.MANAGER
    old_sessions = dict(mh.REGISTRY.sessions)

    config.RELAY_MODE = "force"
    config.HOST = "127.0.0.1"
    config.RELAY_ADDRESS = "127.0.0.1"
    config.RELAY_PORT_START = 0
    config.RELAY_PORT_END = 0
    relay.MANAGER = relay.RelayManager()
    mh.REGISTRY.sessions.clear()

    rebound = None
    try:
        sess = mh.REGISTRY.create(mh._placeholder_session(), host_pid=100)
        mh.REGISTRY.join(sess.gid, 200)
        station = common.StationURL(
            scheme="prudp", address="10.0.0.1", port=50000,
            PID=100, CID=0, RVCID=0x1234, type=3, sid=15, stream=10,
        )
        relayed = await relay.MANAGER.station_for(sess.gid, 100, 200, station)
        port = relayed["port"]
        assert relay.MANAGER._relays

        assert mh.REGISTRY.leave_gathering(sess.gid, 200) == ("left", sess.gid, 1)
        assert relay.MANAGER._relays == {}

        await asyncio.sleep(0.05)
        loop = asyncio.get_running_loop()
        rebound, _ = await loop.create_datagram_endpoint(
            Client, local_addr=("127.0.0.1", port))
    finally:
        if rebound:
            rebound.close()
        relay.MANAGER.close_all()
        relay.MANAGER = old_manager
        mh.REGISTRY.sessions.clear()
        mh.REGISTRY.sessions.update(old_sessions)
        (
            config.RELAY_MODE, config.HOST, config.RELAY_ADDRESS,
            config.RELAY_PORT_START, config.RELAY_PORT_END,
        ) = old_config


async def test_relay_port_released_on_host_destroy():
    old_config = (
        config.RELAY_MODE, config.HOST, config.RELAY_ADDRESS,
        config.RELAY_PORT_START, config.RELAY_PORT_END,
    )
    old_manager = relay.MANAGER
    old_sessions = dict(mh.REGISTRY.sessions)

    config.RELAY_MODE = "force"
    config.HOST = "127.0.0.1"
    config.RELAY_ADDRESS = "127.0.0.1"
    config.RELAY_PORT_START = 0
    config.RELAY_PORT_END = 0
    relay.MANAGER = relay.RelayManager()
    mh.REGISTRY.sessions.clear()

    rebound = None
    try:
        sess = mh.REGISTRY.create(mh._placeholder_session(), host_pid=100)
        mh.REGISTRY.join(sess.gid, 200)
        station = common.StationURL(
            scheme="prudp", address="10.0.0.1", port=50000,
            PID=100, CID=0, RVCID=0x1234, type=3, sid=15, stream=10,
        )
        relayed = await relay.MANAGER.station_for(sess.gid, 100, 200, station)
        port = relayed["port"]
        assert relay.MANAGER._relays

        assert mh.REGISTRY.destroy(sess.gid, owner_pid=100) == "destroyed"
        assert relay.MANAGER._relays == {}

        await asyncio.sleep(0.05)
        loop = asyncio.get_running_loop()
        rebound, _ = await loop.create_datagram_endpoint(
            Client, local_addr=("127.0.0.1", port))
    finally:
        if rebound:
            rebound.close()
        relay.MANAGER.close_all()
        relay.MANAGER = old_manager
        mh.REGISTRY.sessions.clear()
        mh.REGISTRY.sessions.update(old_sessions)
        (
            config.RELAY_MODE, config.HOST, config.RELAY_ADDRESS,
            config.RELAY_PORT_START, config.RELAY_PORT_END,
        ) = old_config


async def test_relay_pair_key_is_directionless():
    old = (
        config.RELAY_MODE, config.HOST, config.RELAY_ADDRESS,
        config.RELAY_PORT_START, config.RELAY_PORT_END,
    )
    config.RELAY_MODE = "force"
    config.HOST = "127.0.0.1"
    config.RELAY_ADDRESS = "127.0.0.1"
    config.RELAY_PORT_START = 0
    config.RELAY_PORT_END = 0

    manager = relay.RelayManager()
    try:
        station = common.StationURL(
            scheme="prudp", address="10.0.0.1", port=50000,
            PID=200, CID=0, RVCID=0x1234, type=3, sid=15, stream=10,
        )
        first = await manager.station_for(0x1001, 300, 200, station)
        second = await manager.station_for(0x1001, 200, 300, station)
        assert first["port"] == second["port"]
        assert len(manager._relays) == 1
    finally:
        manager.close_all()
        (
            config.RELAY_MODE, config.HOST, config.RELAY_ADDRESS,
            config.RELAY_PORT_START, config.RELAY_PORT_END,
        ) = old


def test_nat_pair_resolution_is_directionless():
    old_sessions = dict(mh.REGISTRY.sessions)
    mh.REGISTRY.sessions.clear()
    try:
        sess = mh.REGISTRY.create(mh._placeholder_session(), host_pid=100)
        mh.REGISTRY.join(sess.gid, 200)
        mh.REGISTRY.join(sess.gid, 300)
        srv = protocols.NATTraversalServer()
        assert srv._room_pair(200, 100) == (sess.gid, 100, 200)
        assert srv._room_pair(100, 200) == (sess.gid, 100, 200)
        assert srv._room_pair(300, 200) == (sess.gid, 200, 300)
    finally:
        mh.REGISTRY.sessions.clear()
        mh.REGISTRY.sessions.update(old_sessions)


def test_relay_mode_policy_decisions():
    old = (
        config.RELAY_MODE,
        config.RELAY_AUTO_PAIR_TTL,
        config.RELAY_AUTO_CLIENT_TTL,
        config.RELAY_AUTO_BAD_NATM,
        config.RELAY_AUTO_BAD_NATF,
    )
    relay_policy.reset_for_tests()
    try:
        config.RELAY_MODE = "off"
        assert not relay.MANAGER.should_relay(100, 200)

        config.RELAY_MODE = "force"
        assert relay.MANAGER.should_relay(100, 200)

        config.RELAY_MODE = "auto"
        config.RELAY_AUTO_PAIR_TTL = 10.0
        config.RELAY_AUTO_CLIENT_TTL = 10.0
        config.RELAY_AUTO_BAD_NATM = ""
        config.RELAY_AUTO_BAD_NATF = ""
        assert not relay.MANAGER.should_relay(100, 200)

        relay_policy.record_pair_result(100, 200, success=False)
        assert relay.MANAGER.should_relay(100, 200)
        selected, reason = relay_policy.decide(
            100, 200, now=relay_policy.PAIRS[(100, 200)]["relay_until"] + 1.0)
        assert not selected
        assert reason == "no_risk_signal"

        config.RELAY_AUTO_BAD_NATM = "3"
        relay_policy.record_nat_properties(300, 3, 0, 25, now=2000.0)
        selected, reason = relay_policy.decide(300, 400, now=2001.0)
        assert selected
        assert reason == "client_nat_flags"
    finally:
        (
            config.RELAY_MODE,
            config.RELAY_AUTO_PAIR_TTL,
            config.RELAY_AUTO_CLIENT_TTL,
            config.RELAY_AUTO_BAD_NATM,
            config.RELAY_AUTO_BAD_NATF,
        ) = old
        relay_policy.reset_for_tests()


def test_auto_relay_learns_guest_to_guest_pair():
    old_sessions = dict(mh.REGISTRY.sessions)
    old_mode = config.RELAY_MODE
    old_ttl = config.RELAY_AUTO_PAIR_TTL
    mh.REGISTRY.sessions.clear()
    relay_policy.reset_for_tests()
    try:
        config.RELAY_MODE = "auto"
        config.RELAY_AUTO_PAIR_TTL = 100.0
        sess = mh.REGISTRY.create(mh._placeholder_session(), host_pid=100)
        mh.REGISTRY.join(sess.gid, 200)
        mh.REGISTRY.join(sess.gid, 300)
        relay_policy.record_pair_result(200, 300, success=False)

        relay_gid, peer_a, peer_b = protocols.NATTraversalServer()._room_pair(300, 200)
        assert relay_gid == sess.gid
        assert (peer_a, peer_b) == (200, 300)
        assert relay.MANAGER.should_relay(peer_a, peer_b)
    finally:
        config.RELAY_MODE = old_mode
        config.RELAY_AUTO_PAIR_TTL = old_ttl
        mh.REGISTRY.sessions.clear()
        mh.REGISTRY.sessions.update(old_sessions)
        relay_policy.reset_for_tests()


def test_nat_result_learning_dedupes_basic_and_detail_reports():
    old = config.RELAY_AUTO_PAIR_TTL
    relay_policy.reset_for_tests()
    try:
        config.RELAY_AUTO_PAIR_TTL = 100.0
        assert relay_policy.record_probe_result(100, 200, 0x1234, False, now=10.0)
        assert not relay_policy.record_probe_result(100, 200, 0x1234, False, now=11.0)
        assert relay_policy.PAIRS[(100, 200)]["failures"] == 1
        assert relay_policy.CLIENTS[100]["direct_failures"] == 1
        assert relay_policy.CLIENTS[200]["direct_failures"] == 1

        assert relay_policy.record_probe_result(100, 200, 0x1234, False, now=16.1)
        assert relay_policy.PAIRS[(100, 200)]["failures"] == 2
    finally:
        config.RELAY_AUTO_PAIR_TTL = old
        relay_policy.reset_for_tests()


def test_relay_policy_prunes_bounded_state():
    old = (
        config.RELAY_AUTO_MAX_CLIENTS,
        config.RELAY_AUTO_MAX_PAIRS,
        config.RELAY_AUTO_PAIR_TTL,
    )
    relay_policy.reset_for_tests()
    try:
        config.RELAY_AUTO_MAX_CLIENTS = 3
        config.RELAY_AUTO_MAX_PAIRS = 2
        config.RELAY_AUTO_PAIR_TTL = 100.0

        for i in range(5):
            relay_policy.record_seen(100 + i, now=float(i))
        assert len(relay_policy.CLIENTS) == 3
        assert 100 not in relay_policy.CLIENTS
        assert 101 not in relay_policy.CLIENTS

        relay_policy.record_pair_result(1, 2, success=False, now=1.0)
        relay_policy.record_pair_result(3, 4, success=False, now=2.0)
        relay_policy.record_pair_result(5, 6, success=False, now=3.0)
        assert len(relay_policy.PAIRS) == 2
        assert (1, 2) not in relay_policy.PAIRS
    finally:
        (
            config.RELAY_AUTO_MAX_CLIENTS,
            config.RELAY_AUTO_MAX_PAIRS,
            config.RELAY_AUTO_PAIR_TTL,
        ) = old
        relay_policy.reset_for_tests()


def test_relay_policy_zero_caps_disable_storage():
    old = (
        config.RELAY_AUTO_MAX_CLIENTS,
        config.RELAY_AUTO_MAX_PAIRS,
        config.RELAY_AUTO_PAIR_TTL,
    )
    relay_policy.reset_for_tests()
    try:
        config.RELAY_AUTO_MAX_CLIENTS = 0
        config.RELAY_AUTO_MAX_PAIRS = 0
        config.RELAY_AUTO_PAIR_TTL = 100.0
        relay_policy.record_seen(100)
        relay_policy.record_pair_result(100, 200, success=False)
        assert relay_policy.CLIENTS == {}
        assert relay_policy.PAIRS == {}
        assert not relay_policy.should_relay(100, 200)
    finally:
        (
            config.RELAY_AUTO_MAX_CLIENTS,
            config.RELAY_AUTO_MAX_PAIRS,
            config.RELAY_AUTO_PAIR_TTL,
        ) = old
        relay_policy.reset_for_tests()


def main():
    asyncio.run(test_pair_relay())
    asyncio.run(test_matchmaking_station_substitution())
    asyncio.run(test_relay_port_released_on_guest_leave())
    asyncio.run(test_relay_port_released_on_host_destroy())
    asyncio.run(test_relay_pair_key_is_directionless())
    test_nat_pair_resolution_is_directionless()
    test_relay_mode_policy_decisions()
    test_auto_relay_learns_guest_to_guest_pair()
    test_nat_result_learning_dedupes_basic_and_detail_reports()
    test_relay_policy_prunes_bounded_state()
    test_relay_policy_zero_caps_disable_storage()
    print(">>> RELAY OK")


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# Fail-closed on pool exhaustion (added 2026-09-03).
#
# A privacy feature that silently degrades to no privacy is worse than none, so
# `force` must NOT fall back to the host's real StationURL when it cannot get a
# relay port. `auto` is best-effort NAT rescue, so its fallback must be KEPT --
# these two tests pin both halves of that split.
# ---------------------------------------------------------------------------
class _FakeClient:
    def __init__(self, pid):
        self._pid = pid

    def pid(self):
        return self._pid


async def _urls_with_exhausted_pool(mode):
    old_config = (
        config.RELAY_MODE, config.HOST, config.RELAY_ADDRESS,
        config.RELAY_PORT_START, config.RELAY_PORT_END,
    )
    old_manager = relay.MANAGER
    old_sessions = dict(mh.REGISTRY.sessions)
    old_stations = dict(mh.STATIONS)

    config.RELAY_MODE = mode
    config.HOST = "127.0.0.1"
    config.RELAY_ADDRESS = "127.0.0.1"
    # An empty port window: start > end, so _bind() exhausts immediately.
    config.RELAY_PORT_START = 27100
    config.RELAY_PORT_END = 27099
    relay.MANAGER = relay.RelayManager()
    mh.REGISTRY.sessions.clear()
    mh.STATIONS.clear()
    try:
        sess = mh.REGISTRY.create(mh._placeholder_session(), host_pid=100)
        mh.REGISTRY.join(sess.gid, 200)
        mh.STATIONS[100] = common.StationURL(
            scheme="prudp", address="10.0.0.1", port=50000,
            PID=100, CID=0, RVCID=0x1234, type=3, sid=15, stream=10,
        )
        return await protocols.MatchMakingServer().get_session_urls(_FakeClient(200), sess.gid)
    finally:
        relay.MANAGER.close_all()
        relay.MANAGER = old_manager
        mh.REGISTRY.sessions.clear()
        mh.REGISTRY.sessions.update(old_sessions)
        mh.STATIONS.clear()
        mh.STATIONS.update(old_stations)
        (
            config.RELAY_MODE, config.HOST, config.RELAY_ADDRESS,
            config.RELAY_PORT_START, config.RELAY_PORT_END,
        ) = old_config


async def test_force_fails_closed_when_no_ports_left():
    urls = await _urls_with_exhausted_pool("force")
    # No URL at all. Crucially the host's real 10.0.0.1:50000 must NOT appear.
    assert urls == [], urls
    assert not any(u["address"] == "10.0.0.1" for u in urls)


async def test_auto_still_falls_back_to_direct():
    urls = await _urls_with_exhausted_pool("auto")
    # auto is NAT rescue, not privacy -- direct fallback is the correct outcome.
    assert len(urls) == 1
    assert urls[0]["address"] == "10.0.0.1"
    assert urls[0]["port"] == 50000


# ---------------------------------------------------------------------------
# Endpoint pinning. Off by default (a peer on an overlay network may legitimately
# send from a different IP than its NEX connection was observed on), enforced
# only under MH3U_RELAY_STRICT.
# ---------------------------------------------------------------------------
async def _relay_with_expected(strict, src_ip):
    old_strict = config.RELAY_STRICT
    config.RELAY_STRICT = strict
    try:
        pair = relay.PairRelay(None, ("k", 1, 2), expected_ips=["10.0.0.1", "10.0.0.2"])
        pair.transport = None
        pair.port = 27100
        pair.datagram_received(b"x", (src_ip, 40000))
        return list(pair.peers)
    finally:
        config.RELAY_STRICT = old_strict


async def test_strict_mode_drops_unexpected_source_ip():
    assert await _relay_with_expected(True, "203.0.113.9") == []


async def test_strict_mode_allows_expected_source_ip():
    assert await _relay_with_expected(True, "10.0.0.2") == [("10.0.0.2", 40000)]


async def test_non_strict_allows_unexpected_source_ip():
    # Default behaviour must be unchanged: learn it, just warn.
    assert await _relay_with_expected(False, "203.0.113.9") == [("203.0.113.9", 40000)]


# ---------------------------------------------------------------------------
# Per-recipient advertise address (added 2026-09-03).
#
# One global RELAY_ADDRESS cannot be right for a room that mixes LAN and internet
# players. These pin the ONE case that diverges and, more importantly, the cases
# that must not.
# ---------------------------------------------------------------------------
# NOTE: do not use 203.0.113.x / 192.0.2.x here. Those are TEST-NET documentation
# ranges and Python's ipaddress module reports them as *private*, which makes
# advertise_for() take its pure-LAN early return and quietly invalidates the test.
PUBLIC_IP = "93.184.216.34"


def _advertise(relay_addr, lan_addr, recipient):
    old = (config.RELAY_ADDRESS, config.RELAY_ADDRESS_LAN)
    config.RELAY_ADDRESS, config.RELAY_ADDRESS_LAN = relay_addr, lan_addr
    try:
        return relay.advertise_for(recipient)
    finally:
        config.RELAY_ADDRESS, config.RELAY_ADDRESS_LAN = old


async def test_advertise_lan_peer_gets_lan_address():
    # The whole point: public relay, player on the server's own LAN.
    assert _advertise(PUBLIC_IP, "192.168.1.50", "192.168.1.77") == "192.168.1.50"


async def test_advertise_remote_peer_gets_public_address():
    assert _advertise(PUBLIC_IP, "192.168.1.50", "8.8.4.4") == PUBLIC_IP


async def test_advertise_pure_lan_deployment_unchanged():
    # Every test so far has been this shape -- it must not start diverging.
    assert _advertise("10.9.9.1", "10.9.9.1", "10.9.9.2") == "10.9.9.1"


async def test_advertise_no_lan_known_is_unchanged():
    assert _advertise(PUBLIC_IP, "", "192.168.1.77") == PUBLIC_IP


async def test_advertise_overlay_peer_unchanged():
    # Radmin 26.x / Tailscale 100.x do not read as private, so an overlay deployment
    # keeps handing out the overlay address to everyone, exactly as before.
    assert _advertise("26.0.0.1", "192.168.1.50", "26.0.0.2") == "26.0.0.1"
    assert _advertise("100.64.0.1", "192.168.1.50", "100.64.0.9") == "100.64.0.1"


async def test_advertise_unknown_recipient_is_unchanged():
    assert _advertise(PUBLIC_IP, "192.168.1.50", None) == PUBLIC_IP


# ---------------------------------------------------------------------------
# Pre-pairing buffering (added 2026-09-03).
#
# The relay used to DISCARD any datagram that arrived before both endpoints were
# known. Fatal for guest<->guest, whose establishing probe IS that first packet:
# measured on a live 3-player room, the pair's NAT traversal never completed and
# the third player was ejected. Host<->guest hid the bug because the guest already
# has the relay address from get_session_urls and retries immediately.
# ---------------------------------------------------------------------------
class _CapturingTransport:
    def __init__(self):
        self.sent = []

    def sendto(self, data, addr):
        self.sent.append((data, addr))


async def test_first_packet_is_buffered_not_dropped():
    pair = relay.PairRelay(None, ("k", 1, 2))
    pair.transport = _CapturingTransport()
    pair.port = 27100

    A = ("10.0.0.1", 40000)
    B = ("10.0.0.2", 40001)

    # A probes before B has ever been seen. Nothing can be delivered yet...
    pair.datagram_received(b"probe-1", A)
    pair.datagram_received(b"probe-2", A)
    assert pair.transport.sent == [], "nothing should go out before the pair completes"

    # ...but the moment B appears, the buffered probes must reach it.
    pair.datagram_received(b"from-B", B)
    delivered = [d for d, addr in pair.transport.sent if addr == B]
    assert b"probe-1" in delivered, "first probe was dropped (the 3-player bug)"
    assert b"probe-2" in delivered
    # and B's own packet still goes to A
    assert (b"from-B", A) in pair.transport.sent


async def test_pending_buffer_is_bounded():
    pair = relay.PairRelay(None, ("k", 1, 2))
    pair.transport = _CapturingTransport()
    pair.port = 27100
    A = ("10.0.0.1", 40000)
    for i in range(relay.PENDING_MAX * 3):
        pair.datagram_received(b"x%d" % i, A)
    assert len(pair._pending) == relay.PENDING_MAX, "buffer must not grow unbounded"

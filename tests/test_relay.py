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

        a_transport.sendto(b"first", dst)      # learns A; no peer to forward to yet
        await asyncio.sleep(0.05)
        assert a.q.empty() and b.q.empty()

        b_transport.sendto(b"probe", dst)      # learns B; forwards to A
        data, _ = await asyncio.wait_for(a.q.get(), timeout=1)
        assert data == b"probe"

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

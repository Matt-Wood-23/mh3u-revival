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


def test_nat_pair_resolution_is_directionless():
    old_sessions = dict(mh.REGISTRY.sessions)
    mh.REGISTRY.sessions.clear()
    try:
        sess = mh.REGISTRY.create(mh._placeholder_session(), host_pid=100)
        mh.REGISTRY.join(sess.gid, 200)
        srv = protocols.NATTraversalServer()
        assert srv._room_pair(200, 100) == (sess.gid, 100, 200)
        assert srv._room_pair(100, 200) == (sess.gid, 100, 200)
    finally:
        mh.REGISTRY.sessions.clear()
        mh.REGISTRY.sessions.update(old_sessions)


def main():
    asyncio.run(test_pair_relay())
    asyncio.run(test_matchmaking_station_substitution())
    asyncio.run(test_relay_port_released_on_guest_leave())
    asyncio.run(test_relay_port_released_on_host_destroy())
    test_nat_pair_resolution_is_directionless()
    print(">>> RELAY OK")


if __name__ == "__main__":
    main()

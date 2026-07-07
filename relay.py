"""Optional UDP relay for MH3U gameplay P2P links.

The normal NEX path only brokers a direct UDP hole-punch. That cannot reliably cross
CGNAT/symmetric NAT pairs, so this module provides a small pair-scoped relay endpoint:
both Cemus send their encrypted gameplay UDP to one relay port, and the server forwards
datagrams to the other observed endpoint.
"""
import asyncio
import logging
import time

from nintendo.nex import common

import config
import relay_policy

logger = logging.getLogger("mh3u.relay")


def enabled():
    return config.RELAY_MODE in ("force", "auto")


def _pair_key(gid, a_pid, b_pid):
    if a_pid <= b_pid:
        return gid, a_pid, b_pid
    return gid, b_pid, a_pid


def _copy_station(url):
    return url.copy() if hasattr(url, "copy") else common.StationURL(url)


def relay_station(url, port):
    station = _copy_station(url)
    station["address"] = config.RELAY_ADDRESS
    station["port"] = port
    # Keep the peer's identity fields (PID/RVCID/CID/etc.). Only the UDP destination changes.
    return station


class PairRelay(asyncio.DatagramProtocol):
    def __init__(self, manager, key):
        self.manager = manager
        self.key = key
        self.transport = None
        self.port = None
        self.peers = []
        self.last_rx = time.monotonic()

    def connection_made(self, transport):
        self.transport = transport
        sock = transport.get_extra_info("socket")
        self.port = sock.getsockname()[1]

    def datagram_received(self, data, addr):
        self.last_rx = time.monotonic()
        if addr not in self.peers:
            if len(self.peers) >= 2:
                logger.warning("relay %s:%s dropping third endpoint %s", self.key, self.port, addr)
                return
            self.peers.append(addr)
            logger.info("relay %s:%s learned endpoint %d %s", self.key, self.port, len(self.peers), addr)
        if len(self.peers) < 2:
            return
        dst = self.peers[1] if addr == self.peers[0] else self.peers[0]
        self.transport.sendto(data, dst)

    def error_received(self, exc):
        logger.info("relay %s:%s UDP error: %s", self.key, self.port, exc)

    def close(self):
        if self.transport is not None:
            self.transport.close()
            self.transport = None


class RelayManager:
    def __init__(self):
        self._relays = {}          # (gid, host_pid, guest_pid) -> PairRelay
        self._lock = asyncio.Lock()
        self._janitor = None

    def should_relay(self, host_pid, guest_pid):
        if host_pid is None or guest_pid is None or host_pid == guest_pid:
            return False
        if config.RELAY_MODE == "force":
            return True
        if config.RELAY_MODE == "auto":
            selected, reason = relay_policy.decide(host_pid, guest_pid)
            if selected:
                logger.info("relay auto: host=%s guest=%s selected reason=%s",
                            host_pid, guest_pid, reason)
            return selected
        return False

    async def station_for(self, gid, host_pid, guest_pid, peer_station):
        pair = await self._get_or_create(gid, host_pid, guest_pid)
        return relay_station(peer_station, pair.port)

    async def _get_or_create(self, gid, host_pid, guest_pid):
        key = _pair_key(gid, host_pid, guest_pid)
        relay = self._relays.get(key)
        if relay is not None:
            return relay
        async with self._lock:
            relay = self._relays.get(key)
            if relay is not None:
                return relay
            relay = await self._bind(key)
            self._relays[key] = relay
            self._ensure_janitor()
            logger.info("relay allocated gid=0x%x host=%s guest=%s on %s:%d advertised as %s:%d",
                        gid, host_pid, guest_pid, config.HOST, relay.port,
                        config.RELAY_ADDRESS, relay.port)
            return relay

    async def _bind(self, key):
        loop = asyncio.get_running_loop()
        if config.RELAY_PORT_START == 0:
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: PairRelay(self, key), local_addr=(config.HOST, 0))
            return protocol
        for port in range(config.RELAY_PORT_START, config.RELAY_PORT_END + 1):
            used = any(r.port == port for r in self._relays.values())
            if used:
                continue
            try:
                transport, protocol = await loop.create_datagram_endpoint(
                    lambda: PairRelay(self, key), local_addr=(config.HOST, port))
                return protocol
            except OSError:
                continue
        raise RuntimeError("no UDP relay ports available in %d-%d" %
                           (config.RELAY_PORT_START, config.RELAY_PORT_END))

    def _ensure_janitor(self):
        if self._janitor is None or self._janitor.done():
            self._janitor = asyncio.create_task(self._janitor_task())

    async def _janitor_task(self):
        while self._relays:
            await asyncio.sleep(min(max(config.RELAY_IDLE_TIMEOUT / 2, 5.0), 60.0))
            now = time.monotonic()
            for key, relay in list(self._relays.items()):
                if now - relay.last_rx >= config.RELAY_IDLE_TIMEOUT:
                    logger.info("relay idle timeout closing %s:%s", key, relay.port)
                    self._close_key(key)

    def _close_key(self, key):
        relay = self._relays.pop(key, None)
        if relay is not None:
            logger.info("relay closing %s:%s", key, relay.port)
            relay.close()

    def close_gid(self, gid):
        for key in list(self._relays.keys()):
            if key[0] == gid:
                self._close_key(key)

    def close_for_pid(self, pid):
        for key in list(self._relays.keys()):
            if pid in key[1:]:
                self._close_key(key)

    def close_all(self):
        for key in list(self._relays.keys()):
            self._close_key(key)


MANAGER = RelayManager()

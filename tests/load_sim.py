#!/usr/bin/env python
"""Synthetic load / scale harness for the MH3U NEX server (no Cemu, no dump).

Spins up N headless NEX clients and drives each through the REAL MH3U lifecycle
(auth -> register -> join hall -> find_by_owner[lobbys] -> create/browse/join room
-> end_participation -> logout), well past the 4-player beta cap and across many
rooms. Purpose: de-risk the "larger lobbies / community hubs" roadmap item and
prove the multi-room churn + cleanup paths hold under load.

Two modes
---------
  --mode inproc    (default) start the servers in THIS process. Lets the harness
                   assert directly on the server's in-memory registries after
                   teardown -> "zero ghost leaks" is the hardening evidence.
  --mode external  drive a separately-running `python server.py` over real UDP
                   (measures the server process in isolation -> raw capacity).
                   Point --host/--auth-port at it; for a localhost server started
                   with no MH3U_ADVERTISE this is just 127.0.0.1:1223.

Scenarios (--scenario)
----------------------
  rooms    R rooms x P players (default)         -- multi-room at scale
  fill     ONE room, N joiners past MAX_PLAYERS  -- overflow behaviour
  churn    repeated leave/reconnect (+rounds)    -- leak / cleanup / PID-guard stress
  thunder  all N connect+login simultaneously    -- herd / auth throughput

Examples
--------
  python tests/load_sim.py --clients 64 --scenario rooms --players 4
  python tests/load_sim.py --scenario fill --clients 32
  python tests/load_sim.py --scenario churn --clients 24 --rounds 5
  python tests/load_sim.py --scenario thunder --clients 120
  python tests/load_sim.py --mode external --host 127.0.0.1 --clients 100
"""
import os
import sys

# MUST run before any import that pulls in host_roster_free (matchmaking_handlers /
# protocols capture MH3U_HOST_FREE at import time). No host Cemu exists in a load
# test, so disable the pymem roster-poke -> every join/leave stays pure in-memory.
os.environ.setdefault("MH3U_HOST_FREE", "0")
os.environ.setdefault("MH3U_BIND", "127.0.0.1")   # inproc server binds loopback
# The abuse/DoS guardrails (limits.py) ship with beta-safe caps; a stress run deliberately
# exceeds normal use, so raise them here (before limits.py is imported) so a legit thunder
# scenario isn't cap-limited. All clients come from loopback, which is per-IP-exempt anyway.
os.environ.setdefault("MH3U_MAX_CONNECTIONS", "100000")
os.environ.setdefault("MH3U_MAX_ROOMS", "100000")
os.environ.setdefault("MH3U_MAX_ROOM_PARTICIPANTS", "100000")
os.environ.setdefault("MH3U_MAX_RUNTIME_COMMUNITIES", "100000")
os.environ.setdefault("MH3U_MAX_COMMUNITIES_PER_OWNER", "100000")
os.environ.setdefault("MH3U_SHOUTS_PER_SEC", "100000")

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # mh3u_server/ (tests live one level down)
sys.path.insert(0, os.path.join(_ROOT, "..", "external", "NintendoClients"))
sys.path.insert(0, _ROOT)

import argparse
import asyncio
import contextlib
import logging
import math
import random
import time
from collections import defaultdict

from nintendo.nex import rmc, backend, matchmaking, common, secure

import config
import users
import protocols
import server


# NUM_WORLDS=1 -> a single seeded hall at gid 0x101 (see matchmaking_handlers).
HALL_GID = 0x101


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def _pct(xs, p):
    if not xs:
        return 0.0
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return xs[int(k)]
    return xs[f] * (c - k) + xs[c] * (k - f)


class Metrics:
    """Per-phase latency + error collector. Times in milliseconds."""

    def __init__(self):
        self.samples = defaultdict(list)
        self.errors = defaultdict(int)
        self.error_detail = defaultdict(list)

    async def timed(self, phase, awaitable):
        t = time.perf_counter()
        try:
            r = await awaitable
        except Exception as e:
            self.errors[phase] += 1
            if len(self.error_detail[phase]) < 3:
                self.error_detail[phase].append(repr(e))
            raise
        self.samples[phase].append((time.perf_counter() - t) * 1000.0)
        return r

    def report(self):
        order = ["connect", "login", "register", "join_hall", "find_lobbys",
                 "create_room", "browse", "join_room", "leave_room"]
        phases = [p for p in order if p in self.samples or p in self.errors]
        phases += [p for p in self.samples if p not in phases]
        phases += [p for p in self.errors if p not in phases]
        print("\n  phase                 calls    p50ms    p95ms    maxms    err")
        print("  " + "-" * 62)
        for p in phases:
            xs = self.samples.get(p, [])
            if xs:
                print("  %-18s %8d %8.1f %8.1f %8.1f %6d"
                      % (p, len(xs), _pct(xs, .5), _pct(xs, .95), max(xs), self.errors[p]))
            else:
                print("  %-18s %8d %8s %8s %8s %6d" % (p, 0, "-", "-", "-", self.errors[p]))
        for p, ds in self.error_detail.items():
            for d in ds:
                print("    ! %s: %s" % (p, d))

    @property
    def total_errors(self):
        return sum(self.errors.values())


# --------------------------------------------------------------------------- #
# wire helpers
# --------------------------------------------------------------------------- #
def make_session():
    s = matchmaking.MatchmakeSession()
    s.game_mode = 1
    s.attribs = [101, 0, 0, 0, 0, 0]
    s.min_participants = 1
    s.max_participants = 4
    s.open_participation = True
    return s


def make_criteria():
    # The server's browse ignores criteria (returns all live rooms); this just has to
    # encode. Wildcards + vacant_only=False so full rooms are returned too.
    c = matchmaking.MatchmakeSessionSearchCriteria()
    c.attribs = ["", "", "", "", "", ""]
    c.game_mode = ""
    c.min_participants = "0"
    c.max_participants = "0"
    c.matchmake_system = "0"
    c.vacant_only = False
    c.exclude_locked = False
    return c


def _station_for(pid):
    a, b, c = (pid >> 16) & 0xFF, (pid >> 8) & 0xFF, pid & 0xFF
    return common.StationURL(
        scheme="prudp", address="10.%d.%d.%d" % (a, b, c),
        port=1024 + (pid % 50000), PID=pid, CID=0, type=3, sid=15, stream=10,
    )


# --------------------------------------------------------------------------- #
# one fake hunter
# --------------------------------------------------------------------------- #
class Hunter:
    """One fake hunter. The NEX connection wraps an anyio task group whose cancel scope
    must be entered AND exited in the SAME task, so each hunter runs a single owner task
    (`_own`) that opens, holds, and closes its own connection. Scenario code calls the
    RMC action methods from other tasks — request/await is safe cross-task; only the
    connection's enter/exit must stay in-task."""

    def __init__(self, pid, settings, host, auth_port, metrics):
        self.pid = pid
        self.settings = settings
        self.host = host
        self.auth_port = auth_port
        self.m = metrics
        self.stack = None
        self.client = None
        self.room_gid = None      # set if hosting
        self.in_room_gid = None   # set if joined (host or guest)
        self._owner = None
        self._graceful = True
        self._setup_exc = None

    async def _own(self):
        """Owns the connection lifecycle in one task: connect -> login -> register, hold
        until signalled, then (graceful) disconnect + tear the stack down in this task.
        The _ready/_go_close/_closed events are created by open() before this task starts."""
        try:
            self.stack = contextlib.AsyncExitStack()
            be = await self.m.timed("connect", self.stack.enter_async_context(
                backend.connect(self.settings, self.host, self.auth_port)))
            self.client = await self.m.timed("login", self.stack.enter_async_context(
                be.login(str(self.pid), config.NEX_PASSWORD)))
            self.mm = matchmaking.MatchmakeExtensionClient(self.client)
            self.mmc = matchmaking.MatchMakingClient(self.client)
            self.mmx = matchmaking.MatchMakingClientExt(self.client)
            self.sec = secure.SecureConnectionClient(self.client)
            await self.m.timed("register", self.sec.register([_station_for(self.pid)]))
        except Exception as e:
            self._setup_exc = e
            self._ready.set()
            with contextlib.suppress(Exception):
                await self.stack.aclose()
            self._closed.set()
            return
        self._ready.set()
        await self._go_close.wait()
        # graceful=True -> send a PRUDP TYPE_DISCONNECT so the server runs logout() promptly
        # (clean exit-to-title). graceful=False -> drop with no disconnect packet (hard
        # Cemu-close; production reclaims via the reaper's idle-timeout, not logout).
        if self._graceful and self.client is not None:
            with contextlib.suppress(Exception):
                await self.client.disconnect()
        with contextlib.suppress(Exception):
            await self.stack.aclose()
        self.stack = None
        self.client = None
        self._closed.set()

    async def open(self):
        self._setup_exc = None
        self._ready = asyncio.Event()
        self._go_close = asyncio.Event()
        self._closed = asyncio.Event()
        self._owner = asyncio.create_task(self._own())
        await self._ready.wait()
        if self._setup_exc is not None:
            raise self._setup_exc

    async def close(self, graceful=True):
        self._graceful = graceful
        if self._owner is None:
            return
        self._go_close.set()
        await self._closed.wait()
        with contextlib.suppress(Exception):
            await self._owner
        self._owner = None

    async def enter_hall(self, hall=HALL_GID):
        await self.m.timed("join_hall", self.mm.join_community(hall, "", ""))
        # FindLobbys (method 22) — fatal if it returns [] for a real client.
        await self.m.timed("find_lobbys", self.mmc.find_by_owner(0, common.ResultRange(0, 10)))

    async def host_room(self):
        created = await self.m.timed(
            "create_room", self.mm.create_matchmake_session(make_session(), "load room", 1))
        self.room_gid = self.in_room_gid = created.gid
        return created.gid

    async def browse(self):
        return await self.m.timed(
            "browse", self.mm.browse_matchmake_session(make_criteria(), common.ResultRange(0, 64)))

    async def join_room(self, gid):
        await self.m.timed("join_room", self.mm.join_matchmake_session(gid, "hi"))
        self.in_room_gid = gid

    async def leave_room(self):
        if self.in_room_gid is not None:
            await self.m.timed("leave_room", self.mmx.end_participation(self.in_room_gid, "bye"))
            self.in_room_gid = None


# --------------------------------------------------------------------------- #
# scenarios
# --------------------------------------------------------------------------- #
def _gate(concurrency):
    sem = asyncio.Semaphore(concurrency)

    async def run(coro):
        async with sem:
            return await coro
    return run


async def _allow_fail(*aws):
    """A gather that records-but-tolerates per-client failures (metrics.timed already counted
    them) so a single timed-out hunter doesn't abort the whole load run — important when
    stressing the server hard enough that some clients legitimately time out."""
    return await asyncio.gather(*aws, return_exceptions=True)


async def _bring_online(hunters, gate):
    async def one(h):
        await gate(h.open())
        await gate(h.enter_hall())
    await _allow_fail(*(one(h) for h in hunters))


async def scenario_rooms(hunters, players, gate, hold):
    """R rooms of `players`. host[0] creates, guests browse + join."""
    await _bring_online(hunters, gate)
    rooms = [hunters[i:i + players] for i in range(0, len(hunters), players)]

    async def host(room):
        await gate(room[0].host_room())
    await _allow_fail(*(host(r) for r in rooms))

    async def join(room):
        gid = room[0].room_gid
        for h in room[1:]:
            await gate(h.browse())
            await gate(h.join_room(gid))
    await _allow_fail(*(join(r) for r in rooms))
    await asyncio.sleep(hold)
    return rooms


async def scenario_fill(hunters, gate, hold):
    """ONE room; everyone piles in past MAX_PLAYERS to see how overflow is handled."""
    await _bring_online(hunters, gate)
    gid = await hunters[0].host_room()

    async def join(h):
        await gate(h.browse())
        await gate(h.join_room(gid))
    await _allow_fail(*(join(h) for h in hunters[1:]))
    await asyncio.sleep(hold)

    # Population read works in BOTH modes via the browse result (gathering.num_participants).
    rooms = await hunters[0].browse()
    g = next((x for x in rooms if x.id == gid), None)
    pop = getattr(g, "num_participants", "?") if g else "?"
    import matchmaking_handlers as mh
    print("  fill: room 0x%x reports num_participants=%s  (server MAX_PLAYERS=%d, %d clients joined)"
          % (gid, pop, mh.MAX_PLAYERS, len(hunters)))
    return [hunters]


async def scenario_thunder(hunters, gate, hold):
    """All clients connect+login+register at once, then all enter the hall at once."""
    await _allow_fail(*(gate(h.open()) for h in hunters))
    await _allow_fail(*(gate(h.enter_hall()) for h in hunters))
    await asyncio.sleep(hold)
    return [hunters]


async def scenario_churn(hunters, players, gate, hold, rounds):
    """Steady-state rooms, then repeated leave -> reconnect -> rejoin cycles on half the
    guests each round. Stresses logout cleanup, the PID re-register guard, and rejoin."""
    rooms = await scenario_rooms(hunters, players, gate, hold)
    movers = [h for room in rooms for h in room[1:]][::2]
    print("  churn: %d room(s), cycling %d guest(s) for %d round(s)"
          % (len(rooms), len(movers), rounds))

    async def cycle(h):
        gid = h.in_room_gid
        await gate(h.leave_room())
        await gate(h.close())
        await gate(h.open())
        await gate(h.enter_hall())
        await gate(h.join_room(gid))

    for r in range(rounds):
        t = time.perf_counter()
        await _allow_fail(*(cycle(h) for h in movers))
        # consistency: every room's live participant count == its roster size
        import matchmaking_handlers as mh
        bad = []
        for room in rooms:
            gid = room[0].room_gid
            sess = mh.REGISTRY.sessions.get(gid)
            if sess and sess.gathering.num_participants != len(sess.participants):
                bad.append(hex(gid))
        print("    round %d: %.2fs  %s"
              % (r + 1, time.perf_counter() - t,
                 "OK" if not bad else "COUNT MISMATCH " + ",".join(bad)))
    return rooms


async def teardown(hunters, gate):
    async def one(h):
        with contextlib.suppress(Exception):
            await gate(h.leave_room())
        with contextlib.suppress(Exception):
            await gate(h.close())
    await _allow_fail(*(one(h) for h in hunters))


# --------------------------------------------------------------------------- #
# leak audit (inproc only — reads server globals directly)
# --------------------------------------------------------------------------- #
def audit_registries():
    import matchmaking_handlers as mh
    leaks = []
    if mh.REGISTRY.sessions:
        leaks.append("rooms still live: %s" % [hex(g) for g in mh.REGISTRY.sessions])
    for gid, c in mh.COMMUNITY.communities.items():
        if c.participants:
            leaks.append("hall/lobby 0x%x retains %d member(s)" % (gid, len(c.participants)))
    for nm, d in (("STATIONS", mh.STATIONS), ("CLIENTS", mh.CLIENTS), ("CID_TO_PID", mh.CID_TO_PID)):
        if d:
            leaks.append("%s leaked %d entry(ies)" % (nm, len(d)))
    return leaks


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
async def _body(args, hunters, metrics):
    gate = _gate(args.concurrency)
    t0 = time.perf_counter()
    if args.scenario == "rooms":
        await scenario_rooms(hunters, args.players, gate, args.hold)
    elif args.scenario == "fill":
        await scenario_fill(hunters, gate, args.hold)
    elif args.scenario == "thunder":
        await scenario_thunder(hunters, gate, args.hold)
    elif args.scenario == "churn":
        await scenario_churn(hunters, args.players, gate, args.hold, args.rounds)
    setup_wall = time.perf_counter() - t0

    await teardown(hunters, gate)
    metrics.report()
    print("\n  scenario=%s clients=%d concurrency=%d  setup+hold=%.2fs  errors=%d"
          % (args.scenario, args.clients, args.concurrency, setup_wall, metrics.total_errors))

    if args.mode == "inproc":
        # Graceful disconnect -> server-side logout cleanup is async and drains a little
        # after the client close returns. Poll until the registries are clean (or timeout)
        # and report how long the mass-disconnect took to reclaim — a real load metric.
        t = time.perf_counter()
        leaks = audit_registries()
        while leaks and time.perf_counter() - t < args.settle:
            await asyncio.sleep(0.1)
            leaks = audit_registries()
        drained = time.perf_counter() - t
        if leaks:
            print("  LEAK AUDIT: FAIL (after %.1fs)" % drained)
            for l in leaks:
                print("    - " + l)
        else:
            print("  LEAK AUDIT: clean - all state reclaimed in %.1fs "
                  "(no ghost rooms / hall members / stations / clients)" % drained)
        return 1 if (leaks or metrics.total_errors) else 0
    return 1 if metrics.total_errors else 0


async def run(args):
    s = server.build_settings()
    pids = random.sample(range(0x40000000, 0x70000000), args.clients)
    metrics = Metrics()
    hunters = [Hunter(pid, s, args.host, args.auth_port, metrics) for pid in pids]

    if args.mode == "inproc":
        auth = [server.AuthenticationServer(s)]
        secure_srv = protocols.secure_servers()
        server_key = users.derive_key(users.by_pid(config.SECURE_SERVER_PID))
        async with rmc.serve(s, auth, config.HOST, config.AUTH_PORT):
            async with rmc.serve(s, secure_srv, config.HOST, config.SECURE_PORT, key=server_key):
                return await _body(args, hunters, metrics)
    else:
        return await _body(args, hunters, metrics)


def main():
    ap = argparse.ArgumentParser(description="MH3U NEX server load / scale harness")
    ap.add_argument("--mode", choices=["inproc", "external"], default="inproc")
    ap.add_argument("--scenario", choices=["rooms", "fill", "churn", "thunder"], default="rooms")
    ap.add_argument("--clients", type=int, default=32, help="total fake hunters")
    ap.add_argument("--players", type=int, default=4, help="players per room (rooms/churn)")
    ap.add_argument("--rounds", type=int, default=3, help="churn cycles")
    ap.add_argument("--concurrency", type=int, default=0,
                    help="max concurrent client ops (0 = unlimited / = clients)")
    ap.add_argument("--hold", type=float, default=0.5, help="seconds to hold the steady state")
    ap.add_argument("--settle", type=float, default=10.0,
                    help="max seconds to wait for post-disconnect cleanup to drain (inproc)")
    ap.add_argument("--host", default="127.0.0.1", help="server host (external mode)")
    ap.add_argument("--auth-port", type=int, default=0,
                    help="auth port (0 = inproc:2223 / external:%d)" % config.AUTH_PORT)
    ap.add_argument("--secure-port", type=int, default=0,
                    help="secure port, inproc only (0 = 2224)")
    ap.add_argument("--verbose", action="store_true", help="keep server INFO logging")
    args = ap.parse_args()
    if args.concurrency <= 0:
        args.concurrency = max(1, args.clients)

    # Isolate the in-process server onto ALTERNATE ports by default so a load test can
    # never collide with — or inject fake hunters into — a live server already bound to
    # 1223/1224. The kerberos ticket bakes config.SECURE_PORT, so mutate the module
    # attrs before the servers are built and the bind/ticket/connect all agree.
    if args.mode == "inproc":
        config.AUTH_PORT = args.auth_port or 2223
        config.SECURE_PORT = args.secure_port or 2224
        args.auth_port = config.AUTH_PORT
    else:
        args.auth_port = args.auth_port or config.AUTH_PORT

    logging.getLogger().setLevel(logging.INFO if args.verbose else logging.WARNING)

    rc = asyncio.run(run(args))
    print("\n==> %s" % ("PASS" if rc == 0 else "FAIL (see above)"))
    sys.exit(rc)


if __name__ == "__main__":
    main()

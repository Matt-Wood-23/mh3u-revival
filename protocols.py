"""Secure-server protocol handlers for MH3U.

Strategy for v1: register the protocols MH3U uses and LOG every RMC method the
game calls (method_id + protocol). Unimplemented methods fall through to the
base class, which logs "Unknown method ...". So running this server against a
live Cemu produces an exact trace of the login -> lobby call sequence — which is
the to-do list for which handlers to implement next (Phase 2).
"""
import logging
import time

from nintendo.nex import secure, matchmaking, rmc, common, datastore, nattraversal, streams, notification

import asyncio

import config
import matchmaking_handlers
import host_roster_free

logger = logging.getLogger("mh3u.proto")


def _pid(client):
    p = getattr(client, "pid", None)
    return p() if callable(p) else p


def _conn_idle(rmc_client):
    """Seconds since this connection last received a PRUDP packet (reaper stamps
    _mh3u_last_rx on every inbound packet, pings included). None if unstamped/unknown.
    A small idle ~ a live peer; a large idle ~ a dead connection that just hasn't been
    cleaned up yet. Used to tell a same-PID reconnect from a true duplicate at register."""
    conn = getattr(rmc_client, "client", None)
    last = getattr(conn, "_mh3u_last_rx", None)
    if last is None:
        return None
    return time.monotonic() - last


import os

_RAW = os.environ.get("MH3U_RAW") == "1"   # dump raw RMC req/resp bytes when set


async def push_participation_left(gid, leaving_pid):
    """EXPERIMENT (2026-06-19): when a member leaves room `gid`, push a NEX NotificationEvent
    (protocol 0xE process_notification_event — server->client RMC, same mechanism as the
    working NATTraversal InitiateProbe forward) to each REMAINING member, so the host purges
    the leaver's nNetwork roster slot and a later REJOIN is clean (fixes the rejoin-after-leave
    stall seen 2026-06-19: initial join works, rejoin spins on 'retrieving room info').

    MH3U's handler (Ghidra FUN_02e4f8a4) switches on type/1000: MAJOR type 4 (4000-4999)
    latches event.param2 into the net mediator -> nNetwork roster manager. The exact minor type
    and what param2 must carry are NOT yet known, so this is OFF by default and opt-in:
      MH3U_NOTIFY_ON=1    enable the experiment (default OFF == proven 0a14ab9 behavior)
      MH3U_NOTIFY_TYPE    (int, default 4000)
      MH3U_NOTIFY_PARAM2  (leaver|gid, default leaver)

    STATUS 2026-06-19: push delivers to the host cleanly (no error) but with type=4000 /
    param2=leaver-pid it does NOT clear the rejoin-after-leave stall. Getting the right
    type+payload needs live Cemu debugging of the host (breakpoint FUN_02e4f8a4 +
    roster mgr FUN_02e71ee4, watch what a legit P2P leave writes). See
    handoffs/2026-06-19_notification_push_RE.md.
    """
    if os.environ.get("MH3U_NOTIFY_ON") != "1":
        return
    sess = matchmaking_handlers.REGISTRY.sessions.get(gid)
    if not sess:
        return
    ntype = int(os.environ.get("MH3U_NOTIFY_TYPE", "4000"))
    param2 = gid if os.environ.get("MH3U_NOTIFY_PARAM2") == "gid" else leaving_pid
    for pid in list(sess.participants):
        if pid == leaving_pid:
            continue
        conn = matchmaking_handlers.CLIENTS.get(pid)
        if conn is None:
            continue
        try:
            ev = notification.NotificationEvent()
            ev.pid = leaving_pid
            ev.type = ntype
            ev.param1 = gid
            ev.param2 = param2
            ev.text = ""
            out = streams.StreamOut(conn.settings)
            out.add(ev)
            await conn.request(
                notification.NotificationProtocol.PROTOCOL_ID,
                notification.NotificationProtocol.METHOD_PROCESS_NOTIFICATION_EVENT,
                out.get(), noresponse=True)
            logger.info("  -> NOTIFY-LEFT pushed (type=%d subj_pid=%d param2=%d gid=0x%x) to member pid=%s",
                        ntype, leaving_pid, param2, gid, pid)
        except Exception as e:
            logger.info("  -> NOTIFY-LEFT to pid=%s failed: %s", pid, e)


async def fire_notification(target_pid, subject_pid, ntype, param1, param2, text=""):
    """Push a single NEX NotificationEvent (proto 0xE m1, server->client RMC) to target_pid's
    live connection. Returns (ok, detail). Used by the on-demand trigger to hunt the exact
    participation-left type that makes a host purge a departed peer's roster/participant cache."""
    conn = matchmaking_handlers.CLIENTS.get(target_pid)
    if conn is None:
        return False, "no live connection for target pid"
    try:
        ev = notification.NotificationEvent()
        ev.pid = subject_pid
        ev.type = ntype
        ev.param1 = param1
        ev.param2 = param2
        ev.text = text or ""
        out = streams.StreamOut(conn.settings)
        out.add(ev)
        await conn.request(
            notification.NotificationProtocol.PROTOCOL_ID,
            notification.NotificationProtocol.METHOD_PROCESS_NOTIFICATION_EVENT,
            out.get(), noresponse=True)
        return True, "sent"
    except Exception as e:
        return False, repr(e)


async def notify_trigger_watcher(path=None, interval=0.4):
    """On-demand notification driver. Watches a JSON trigger file; when it appears, fires the
    described NotificationEvent(s) at a live host connection, logs the outcome, deletes the file.

    Trigger JSON (single push):
        {"pid": <target>, "subject_pid": <subj>, "type": <int>, "param1": <int>,
         "param2": <int>, "text": "<opt>"}
    or a batch: {"pushes": [ {..}, {..} ]}.
    Lets us live-hunt the participation-left type against the stuck host without a server restart
    per attempt. OFF unless MH3U_NOTIFY_TRIGGER=1.
    """
    import asyncio
    import json
    if os.environ.get("MH3U_NOTIFY_TRIGGER") != "1":
        return
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notify_trigger.json")
    logger.info("notify_trigger_watcher: watching %s", path)
    while True:
        try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    spec = json.load(f)
                try:
                    os.remove(path)
                except OSError:
                    pass
                pushes = spec.get("pushes") or [spec]
                for p in pushes:
                    tgt = int(p["pid"])
                    subj = int(p.get("subject_pid", p.get("param2", 0)))
                    ntype = int(p["type"])
                    param1 = int(p.get("param1", 0))
                    param2 = int(p.get("param2", 0))
                    text = p.get("text", "")
                    ok, detail = await fire_notification(tgt, subj, ntype, param1, param2, text)
                    logger.info("NOTIFY-TRIGGER -> target_pid=%s subj=%s type=%d p1=%d p2=%d text=%r : %s (%s)",
                                tgt, subj, ntype, param1, param2, text, "OK" if ok else "FAIL", detail)
        except Exception as e:
            logger.info("notify_trigger_watcher error: %s", e)
        await asyncio.sleep(interval)


class _Trace:
    """Mixin: log each incoming RMC method, then defer to the real handler.

    With MH3U_RAW=1, also dumps the raw request body + raw response bytes. Use this
    to decode MH3U's true request/response shapes when a handler's wire format is
    suspected wrong (e.g. findOfficialCommunity m21 — game disconnects regardless of
    content, so its response shape differs from NintendoClients' default)."""
    LABEL = "?"

    async def handle(self, client, method_id, input, output):
        logger.info("CALL  %-22s method_id=%s  (pid=%s)", self.LABEL, method_id, _pid(client))
        if _RAW:
            try:
                logger.info("RAW   %s m%s REQ=%s", self.LABEL, method_id, input.get().hex())
            except Exception as e:
                logger.info("RAW   %s m%s REQ unavailable (%s)", self.LABEL, method_id, e)
        await super().handle(client, method_id, input, output)
        if _RAW:
            try:
                logger.info("RAW   %s m%s RESP=%s", self.LABEL, method_id, output.get().hex())
            except Exception as e:
                logger.info("RAW   %s m%s RESP unavailable (%s)", self.LABEL, method_id, e)


class SecureConnectionServer(_Trace, secure.SecureConnectionServer):
    LABEL = "SecureConnection"

    def __init__(self):
        super().__init__()
        self._next_cid = 0x1000
        self.registry = {}          # pid -> {"cid": int, "urls": [StationURL]}

    def _build_public(self, client, urls, cid):
        """Echo back a station URL stamped with the address we observed + RVCID.

        Co-location override: when the host PLAYER shares a machine with the server it
        connects via loopback, so the observed address is 127.x — useless to a remote
        joiner. If config.ADVERTISE_ADDRESS (env MH3U_ADVERTISE) is set, substitute it for
        loopback-observed peers so the host advertises its real reachable IP. Genuinely
        remote peers keep their observed (NAT-external) address."""
        try:
            addr = client.remote_address()
        except Exception:
            addr = ("127.0.0.1", 0)
        host = addr[0]
        if config.ADVERTISE_ADDRESS and (host.startswith("127.") or host in ("::1", "localhost")):
            logger.info("_build_public: loopback peer %s -> advertising %s", host, config.ADVERTISE_ADDRESS)
            host = config.ADVERTISE_ADDRESS
        station = urls[0].copy() if urls else common.StationURL()
        station["address"] = host
        station["port"] = addr[1]
        station["RVCID"] = cid
        station["type"] = 3         # public | behind-nat (standard for registered peer)
        return station

    async def register(self, client, urls):
        # PID-uniqueness guard (the server is the authority on who owns a PID). If a
        # DIFFERENT connection already holds this PID, the newcomer is authoritative
        # (last-writer-wins) -- safe because the dominant real case is a RECONNECT (same
        # account returning after a drop; old connection is dead), which we must never
        # reject after all the rejoin work. With random per-account PIDs (make_account.py)
        # a true two-different-people collision is astronomically unlikely, but if one ever
        # happens it lands here too: we LOG it loudly (so the operator/player knows to
        # regenerate account.dat) and proactively retire the old connection's stale cid
        # mapping so the room roster can't hold two live sessions for one PID. The old
        # connection's own later logout takes the stale-path (CLIENTS.get(pid) is not it)
        # and won't clobber this live one.
        pid = _pid(client)
        prev = matchmaking_handlers.CLIENTS.get(pid)
        if prev is not None and prev is not client:
            idle = _conn_idle(prev)
            idle_s = ("%.0fs" % idle) if idle is not None else "unknown"
            logger.warning(
                "register: pid=%s already held by another connection (last-rx idle=%s) -> "
                "treating NEW connection as authoritative. Expected for a reconnect; if you "
                "see this for two DIFFERENT players at once, their PIDs COLLIDED -- have the "
                "newer player re-run make_account.py for a fresh PID.", pid, idle_s)
            prev_cid = getattr(prev, "_mh3u_cid", None)
            if prev_cid is not None and matchmaking_handlers.CID_TO_PID.get(prev_cid) == pid:
                matchmaking_handlers.CID_TO_PID.pop(prev_cid, None)
        self._next_cid += 1
        cid = self._next_cid
        # Stamp the cid on the connection so logout() can clean up exactly this
        # connection's entries (and tell itself apart from a newer reconnect).
        client._mh3u_cid = cid
        station = self._build_public(client, urls, cid)
        self.registry[_pid(client)] = {"cid": cid, "urls": urls}
        # publish the peer's P2P StationURL so the room's joiner can fetch it
        # (get_session_urls / get_participants_urls) to connect host<->guest.
        matchmaking_handlers.STATIONS[_pid(client)] = station
        # publish the live connection + RVCID->pid so NAT traversal can forward an
        # InitiateProbe to this peer (server->client RMC).
        matchmaking_handlers.CLIENTS[_pid(client)] = client
        matchmaking_handlers.CID_TO_PID[cid] = _pid(client)
        logger.info("REGISTER pid=%s cid=%s urls=%s -> public=%s",
                    _pid(client), cid, [str(u) for u in urls], station)
        resp = rmc.RMCResponse()
        resp.result = common.Result.success()
        resp.connection_id = cid
        resp.public_station = station
        return resp

    async def register_ex(self, client, urls, login_data=None):
        # Same as register; some titles add a login-data blob we don't need here.
        return await self.register(client, urls)

    async def logout(self, client):
        """Connection-close cleanup (rmc.cleanup() calls this on graceful logout AND
        on an ungraceful drop/timeout). Without it, a peer that disconnects leaks its
        room participation, station URL and connection entry forever — the "ghost
        participant" seen 2026-06-19 when a relay hiccup dropped the joiner mid-session.

        Reconnect-race safety: a stale OLD connection can close *after* the same player
        has already reconnected (same pid, new cid). Its late cleanup must not clobber
        the live new connection. So: always retire this connection's own cid, but only
        do the pid-keyed teardown (room leave, station, client handle) when THIS
        connection is still the registered one for that pid."""
        pid = _pid(client)
        cid = getattr(client, "_mh3u_cid", None)
        mh = matchmaking_handlers

        # Always drop this exact connection's cid->pid mapping (unique to it).
        if cid is not None and mh.CID_TO_PID.get(cid) == pid:
            mh.CID_TO_PID.pop(cid, None)

        if mh.CLIENTS.get(pid) is client:
            # This is still the current connection for pid -> full teardown.
            mh.CLIENTS.pop(pid, None)
            mh.STATIONS.pop(pid, None)
            self.registry.pop(pid, None)
            affected = mh.REGISTRY.leave(pid)
            pretty = [(a, hex(g), r) for (a, g, r) in affected]
            halls = mh.COMMUNITY.leave_all(pid)
            logger.info("LOGOUT pid=%s cid=%s -> cleaned up; rooms affected=%s; halls left=%s",
                        pid, cid, pretty, [hex(g) for g in halls])
        else:
            logger.info("LOGOUT pid=%s cid=%s -> stale connection (a newer one is active); "
                        "retired cid only, left live state intact", pid, cid)

        await super().logout(client)


class MatchMakingServer(_Trace, matchmaking.MatchMakingServer):
    LABEL = "MatchMaking"

    async def find_by_owner(self, client, owner, range):
        # method 22 = FindLobbys (CNEXLobby::PhaseFindLobbys, FUN_030d81f0). Called right
        # after JoinWorld to enumerate the *lobbys inside the joined world*. Returning []
        # is FATAL: the client raises 0x4a000205 "Failed to find lobby" -> "you have been
        # disconnected" (root-caused 2026-06-18, see CommunityRegistry docstring). So return
        # >=1 lobby gathering. owner is 0 here (no per-owner filter); the world context isn't
        # in this request, so we advertise the whole lobby set for now.
        import os
        if os.environ.get("MH3U_EMPTY_LOBBYS") == "1":
            logger.info("find_by_owner: owner=%s (pid=%s) -> [] (MH3U_EMPTY_LOBBYS=1)", owner, _pid(client))
            return []
        lobbys = matchmaking_handlers.COMMUNITY.lobby_gatherings()
        logger.info("find_by_owner(FindLobbys): owner=%s (pid=%s) -> %d lobby(s)",
                    owner, _pid(client), len(lobbys))
        return lobbys

    # proto-21 (MatchMaking) GetParticipants — the LOBBY enter calls these right after
    # the main+chat JoinCommunity (CNEXLobby PhaseGetParticipants). Returning Core::NotImplemented
    # aborts the lobby-load before GetRooms, so LoginLobbyEnd never sets its done flag (0x4000)
    # and the lobby session never finalizes -> "Create a Room" fails. Empty lists = clean success
    # ("0/0 connected players"). (NOTE: these are proto 21 (gid only); the proto-50 Ext versions
    # below take (gid, only_active) — different protocol, different signature.)
    async def get_participants(self, client, gid):
        logger.info("get_participants(MM21): gid=0x%x (pid=%s) -> []", gid, _pid(client))
        return []

    async def get_detailed_participants(self, client, gid):
        # The Lobby Menu polls this on the lobby gid (0x20N) to show 'Connected players X/99'.
        # Returning [] read as 0 even with players present; return the live roster so the count
        # is real. (Encoding round-trip-verified offline before enabling.)
        parts = matchmaking_handlers.participant_details(gid)
        logger.info("get_detailed_participants(MM21): gid=0x%x (pid=%s) -> %d participant(s)",
                    gid, _pid(client), len(parts))
        return parts

    async def unregister_gathering(self, client, gid):
        # The ROOM HOST's explicit teardown path: returning to the lobby, the host sends
        # UnregisterGathering(gid) to close its own room (the guest uses EndParticipation
        # instead). NintendoClients leaves this NotImplemented -> 0x80010002 -> the host
        # client treats it as fatal and shows "disconnecting" (seen 2026-06-19: host-leave
        # errored while guest-leave was clean). Destroy the room + ack True so the host
        # returns to the lobby cleanly and the room drops out of browse.
        existed = matchmaking_handlers.REGISTRY.destroy(gid)
        logger.info("unregister_gathering: gid=0x%x (pid=%s) -> %s",
                    gid, _pid(client), "destroyed" if existed else "not found")
        return True

    async def unregister_gatherings(self, client, gids):
        # Plural variant (same NotImplemented trap); destroy each + ack True.
        gone = [hex(g) for g in gids if matchmaking_handlers.REGISTRY.destroy(g)]
        logger.info("unregister_gatherings: gids=%s (pid=%s) -> destroyed %s",
                    [hex(g) for g in gids], _pid(client), gone)
        return True

    # --- room state + P2P address (the joiner's path) -----------------------
    def _host_station(self, gid):
        sess = matchmaking_handlers.REGISTRY.sessions.get(gid)
        host = sess.host_pid if sess else None
        url = matchmaking_handlers.STATIONS.get(host)
        return [url] if url is not None else []

    async def get_session_urls(self, client, gid):
        # The joiner asks for the room host's StationURL(s) to open the P2P link.
        urls = self._host_station(gid)
        logger.info("get_session_urls(MM21): gid=0x%x -> %s", gid, [str(u) for u in urls])
        return urls

    async def get_participants_urls(self, client, gid):
        urls = self._host_station(gid)
        logger.info("get_participants_urls(MM21): gid=0x%x -> %s", gid, [str(u) for u in urls])
        return urls

    async def find_by_single_id(self, client, gid):
        # Room/community self-poll. Now returns a fully-formed gathering so anydata encodes.
        resp = rmc.RMCResponse()
        sess = matchmaking_handlers.REGISTRY.sessions.get(gid)
        comm = matchmaking_handlers.COMMUNITY.communities.get(gid)
        if sess:
            resp.result, resp.gathering = True, sess.gathering
        elif comm:
            resp.result, resp.gathering = True, comm.pg
        else:
            resp.result, resp.gathering = False, matchmaking_handlers._placeholder_session()
        logger.info("find_by_single_id(MM21): gid=0x%x -> result=%s", gid, resp.result)
        return resp


class MatchMakingServerExt(_Trace, matchmaking.MatchMakingServerExt):
    # proto 0x32 — the gathering participation protocol. The game calls
    # EndParticipation (m1) to leave a hall it previewed; if that returns an error
    # the game treats it as a fatal disconnect ("you have been disconnected").
    LABEL = "MatchMakingExt"

    async def end_participation(self, client, gid, message):
        # EndParticipation is MH3U's explicit 'I'm backing out of this gathering' signal,
        # sent the instant a player exits a room (confirmed live: joiner exits room 0x1002
        # -> end_participation(0x1002)). It MUST drop the participant so browse/find report
        # the right count without waiting on a socket teardown; a HOST leaving destroys the
        # room. Hall (community) gids aren't tracked for occupancy -> leave_gathering returns
        # None for them and we just ack (the previous stub acked everything -> stuck counts).
        pid = _pid(client)
        affected = matchmaking_handlers.REGISTRY.leave_gathering(gid, pid)
        if affected:
            action, agid, remaining = affected
            logger.info("end_participation: ROOM gid=0x%x (pid=%s) -> %s (remaining=%d)",
                        agid, pid, action, remaining)
            if action == "left":
                # THE FIX (RE'd 2026-06-21): the host has no native room-leave path, so it keeps a
                # stale participant -> next rejoin drifts/stalls. Mirror the game's own remove
                # directly in the co-located host Cemu's memory (roster used-flag + station array +
                # dirty resync). Fail-safe + off-thread so it never blocks/breaks the server.
                # Live-proven across 3 clean leave/rejoin cycles. See host_roster_free.
                result = await asyncio.to_thread(host_roster_free.free_guest_slot, pid)
                logger.info("end_participation: host-free pid=%s -> %s", pid, result)
                # (legacy NEX-notification experiment retired; handler is inert, field_4 null)
        elif matchmaking_handlers.COMMUNITY.leave(gid, pid):
            # Backing out of a world/lobby (EndParticipation fires for the world gid 0x10N
            # and its lobby 0x20N) -> drop membership so the Population count on the World/
            # Lobby list reflects the real live occupancy for everyone else.
            pop = matchmaking_handlers.COMMUNITY.communities[gid].pg.num_participants
            logger.info("end_participation: HALL gid=0x%x (pid=%s) -> left (num_participants=%d)",
                        gid, pid, pop)
        else:
            logger.info("end_participation: gid=0x%x msg=%r (pid=%s) -> ack (not a tracked gathering)",
                        gid, message, pid)
        return True

    async def get_participants(self, client, gid, only_active):
        logger.info("get_participants: gid=0x%x only_active=%s (pid=%s) -> []",
                    gid, only_active, _pid(client))
        return []

    async def get_detailed_participants(self, client, gid, only_active):
        logger.info("get_detailed_participants: gid=0x%x (pid=%s) -> []", gid, _pid(client))
        return []

    async def get_participants_urls(self, client, gids):
        logger.info("get_participants_urls: gids=%s (pid=%s) -> []", gids, _pid(client))
        return []


class DataStoreServer(_Trace, datastore.DataStoreServer):
    # proto 0x73 — shared data store (player cards / hall content). The game does a
    # SearchObject (m12) on entering the hall; an *error* here (vs empty) may make it
    # treat the hall as broken. Return an empty result set.
    LABEL = "DataStore"

    async def search_object(self, client, param):
        res = datastore.DataStoreSearchResult()
        res.total_count = 0
        res.result = []
        res.total_count_type = 0
        logger.info("search_object (pid=%s) -> empty", _pid(client))
        return res


class NATTraversalServer(_Trace, nattraversal.NATTraversalServer):
    # proto 0x3 — P2P hole-punch coordination. After the joiner gets the host's StationURL
    # (get_session_urls), it reports its NAT properties (m5) and asks the server to coordinate
    # a probe to the host (m3 request_probe_initiation_ext), then reports the result (m4).
    # NintendoClients leaves all of these NotImplemented -> 0x80010002 -> the joiner can't
    # finish the P2P link and bounces. These methods carry no response payload (pure acks),
    # so returning None = clean RMC success. Both Cemu instances are on the same machine
    # (localhost/LAN, no NAT between them), so acking the coordination lets them connect
    # directly without real hole-punching. If a direct connect still fails, the next step is
    # to actually forward InitiateProbe to the host's connection.
    LABEL = "NATTraversal"

    async def report_nat_properties(self, client, natm, natf, rtt):
        logger.info("report_nat_properties: natm=%s natf=%s rtt=%s (pid=%s)", natm, natf, rtt, _pid(client))
        return None

    async def request_probe_initiation(self, client, target_urls):
        logger.info("request_probe_initiation: targets=%s (pid=%s)",
                    [str(u) for u in target_urls], _pid(client))
        return None

    async def initiate_probe(self, client, station_to_probe):
        logger.info("initiate_probe: station=%s (pid=%s)", station_to_probe, _pid(client))
        return None

    async def request_probe_initiation_ext(self, client, target_urls, station_to_probe):
        # The joiner (station_to_probe) wants to reach each target (the host). Forward an
        # InitiateProbe to every target's connection so the host fires a probe packet back at
        # the joiner -> completes the bidirectional path. Without this, only the joiner sends
        # and the host stays silent -> report_nat_traversal_result(False) (the gate we hit).
        logger.info("request_probe_initiation_ext: targets=%s probe=%s (pid=%s)",
                    [str(u) for u in target_urls], station_to_probe, _pid(client))
        for url in target_urls:
            rvcid = url["RVCID"]
            target_pid = matchmaking_handlers.CID_TO_PID.get(rvcid)
            target_client = matchmaking_handlers.CLIENTS.get(target_pid)
            if target_client is None:
                logger.info("  -> no live connection for RVCID=%s (pid=%s); cannot forward probe",
                            rvcid, target_pid)
                continue
            try:
                out = streams.StreamOut(target_client.settings)
                out.stationurl(station_to_probe)
                await target_client.request(
                    nattraversal.NATTraversalProtocol.PROTOCOL_ID,
                    nattraversal.NATTraversalProtocol.METHOD_INITIATE_PROBE,
                    out.get(), noresponse=True)
                logger.info("  -> forwarded InitiateProbe(joiner=%s) to host pid=%s RVCID=%s",
                            station_to_probe, target_pid, rvcid)
            except Exception as e:
                logger.info("  -> InitiateProbe forward to pid=%s failed: %s", target_pid, e)
        return None

    async def report_nat_traversal_result(self, client, cid, result):
        logger.info("report_nat_traversal_result: cid=%s result=%s (pid=%s)", cid, result, _pid(client))
        return None

    async def report_nat_traversal_result_detail(self, client, cid, result, detail, rtt):
        logger.info("report_nat_traversal_result_detail: cid=%s result=%s detail=%s rtt=%s (pid=%s)",
                    cid, result, detail, rtt, _pid(client))
        return None


class MatchmakeExtensionServer(_Trace, matchmaking_handlers.MatchmakeExtensionServer):
    # real create/browse/join logic from matchmaking_handlers + the call trace.
    LABEL = "MatchmakeExtension"


def secure_servers():
    """Protocol handlers hosted on the secure server. Add NAT/health/etc. as the
    live trace reveals MH3U needs them."""
    return [
        SecureConnectionServer(),
        MatchMakingServer(),
        MatchMakingServerExt(),
        NATTraversalServer(),
        DataStoreServer(),
        MatchmakeExtensionServer(),
    ]

"""Secure-server protocol handlers for MH3U.

Strategy for v1: register the protocols MH3U uses and LOG every RMC method the
game calls (method_id + protocol). Unimplemented methods fall through to the
base class, which logs "Unknown method ...". So running this server against a
live Cemu produces an exact trace of the login -> lobby call sequence — which is
the to-do list for which handlers to implement next (Phase 2).
"""
import logging
import time

from nintendo.nex import secure, matchmaking, rmc, common, datastore, nattraversal, streams, notification, messaging

import asyncio

import config
import matchmaking_handlers
import host_roster_free
import limits

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


async def push_participation_left(gid, leaving_pid, ntype=3007):
    """Push a participation-ended NEX NotificationEvent (proto 0xE m1, server->client RMC)
    to each REMAINING member of room `gid` so their game natively removes the leaver from
    the CNEXSystem participant roster — the table whose stale slot causes the rejoin
    stall/drift that host_roster_free.py pokes by hand.

    Grounding (Ghidra 2026-07-02): the NEX-backend notification dispatcher FUN_030dd51c
    (NOT the inert game-side handler FUN_02e4f8a4 the 2026-06-19/21 digs probed) switches
    on type/1000; major 3 subtype 7/8 = "Participation Event[End/Disconnect]: PID=%u" ->
    FUN_030c8ef8(CNEXSystem, event.param2) = the native roster remove (clears the used-flag
    +0x30d34, record, membercount, dirty — the same fields host_roster_free writes). So:
    type=3007 (EndParticipation) / 3008 (Disconnect), param2 = leaver pid. The old
    experiment pushed type=4000 (the ownership-change branch) and watched the wrong
    handler, which is why it "delivered cleanly but did nothing".

    Unlike the pymem poke this reaches REMOTE hosts and the other guests of a 3-4 player
    room (every peer keeps its own roster copy). LIVE-PROVEN 2026-07-02, all three cases
    with the poke disabled: clean leave/rejoin vs a local host (native free RAM-verified,
    slot reuse, no drift), clean leave/rejoin vs a REMOTE host, and hard-drop (reaper ->
    3008 -> native free RAM-verified -> clean rejoin). Default ON:
      MH3U_NOTIFY_ON=0    disable (fall back to the legacy pymem poke via MH3U_HOST_FREE=1)
      MH3U_NOTIFY_TYPE    (int, overrides the ntype arg for live hunting)
      MH3U_NOTIFY_PARAM2  (leaver|gid, default leaver)
    """
    if os.environ.get("MH3U_NOTIFY_ON", "1") != "1":
        return
    sess = matchmaking_handlers.REGISTRY.sessions.get(gid)
    if not sess:
        return
    ntype = int(os.environ.get("MH3U_NOTIFY_TYPE", ntype))
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
        # Connection caps keyed on SOURCE IP (PIDs are attacker-chosen). A reconnect (pid
        # already present) is never blocked; a new PID is rejected when the server is full.
        # Loopback (the co-located host) is exempt from the per-IP cap.
        ip = limits.remote_ip(client)
        is_new_pid = pid not in matchmaking_handlers.CLIENTS
        ok, reason = limits.global_connection_ok(is_new_pid, len(matchmaking_handlers.CLIENTS))
        if not ok:
            logger.warning("register: REJECT pid=%s ip=%s -> %s", pid, ip, reason)
            raise common.RMCError("RendezVous::MaxConnectionsReached")
        ok, reason = limits.ip_can_connect(ip)
        if not ok:
            logger.warning("register: REJECT pid=%s -> %s", pid, reason)
            raise common.RMCError("RendezVous::MaxConnectionsReached")

        prev = matchmaking_handlers.CLIENTS.get(pid)
        if prev is not None and prev is not client:
            idle = _conn_idle(prev)
            idle_s = ("%.0fs" % idle) if idle is not None else "unknown"
            prev_ip = getattr(prev, "_mh3u_ip", None)
            # Same IP = ordinary reconnect; a DIFFERENT IP claiming a live PID is the
            # impersonation shape (or a real collision) — flag it loud.
            same_ip = (prev_ip is not None and ip is not None and prev_ip == ip)
            logger.warning(
                "register: pid=%s already held by another connection (last-rx idle=%s, "
                "incumbent ip=%s, new ip=%s, same_ip=%s) -> treating NEW connection as "
                "authoritative. Expected for a reconnect (same IP); a DIFFERENT IP here means "
                "two players' PIDs COLLIDED or a PID is being impersonated -- have the newer "
                "player re-run make_account.py for a fresh PID.", pid, idle_s, prev_ip, ip, same_ip)
            prev_cid = getattr(prev, "_mh3u_cid", None)
            if prev_cid is not None and matchmaking_handlers.CID_TO_PID.get(prev_cid) == pid:
                matchmaking_handlers.CID_TO_PID.pop(prev_cid, None)

        # Count this connection against its source IP exactly once (decremented in logout).
        if not getattr(client, "_mh3u_ip_counted", False):
            client._mh3u_ip = ip
            client._mh3u_ip_counted = True
            limits.ip_add(ip)
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

        # Release this connection's per-IP slot (guarded to run once).
        if getattr(client, "_mh3u_ip_counted", False):
            limits.ip_remove(getattr(client, "_mh3u_ip", None))
            client._mh3u_ip_counted = False

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
            for a, g, r in affected:
                if a == "left" and r > 0:
                    await push_participation_left(g, pid, ntype=3008)
            halls = mh.COMMUNITY.leave_all(pid)
            # Destroy runtime communities this pid owned + drop its rate-limit state.
            reaped = mh.COMMUNITY.reap_owner(pid)
            limits.forget_pid(pid)
            logger.info("LOGOUT pid=%s cid=%s -> cleaned up; rooms affected=%s; halls left=%s%s",
                        pid, cid, pretty, [hex(g) for g in halls],
                        ("; runtime-communities destroyed=%s" % [hex(g) for g in reaped]) if reaped else "")
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
        pid = _pid(client)
        status = matchmaking_handlers.REGISTRY.destroy(gid, owner_pid=pid)
        if status == "denied":
            logger.warning("unregister_gathering: DENY gid=0x%x (pid=%s not the room host)", gid, pid)
        else:
            logger.info("unregister_gathering: gid=0x%x (pid=%s) -> %s", gid, pid, status)
        return True   # always ack (an error here makes the host client show 'disconnecting')

    async def unregister_gatherings(self, client, gids):
        # Plural variant (same NotImplemented trap); destroy each own room + ack True.
        pid = _pid(client)
        gids = limits.bound_list(gids)
        gone, denied = [], 0
        for g in gids:
            status = matchmaking_handlers.REGISTRY.destroy(g, owner_pid=pid)
            if status == "destroyed":
                gone.append(hex(g))
            elif status == "denied":
                denied += 1
        logger.info("unregister_gatherings: gids=%s (pid=%s) -> destroyed %s%s",
                    [hex(g) for g in gids], pid, gone,
                    ("; DENIED %d (not host)" % denied) if denied else "")
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
                # THE FIX: without a leave signal, every remaining peer keeps a stale participant
                # roster slot -> the leaver's next rejoin drifts/stalls. The type-3007 notification
                # makes each peer run the game's own native remove (see push_participation_left).
                await push_participation_left(agid, pid, ntype=3007)
                # Legacy fallback (MH3U_HOST_FREE=1): poke the co-located host Cemu's memory
                # directly. Off by default since the notification fix; kept for emergencies.
                if host_roster_free.ENABLED:
                    result = await asyncio.to_thread(host_roster_free.free_guest_slot, pid)
                    logger.info("end_participation: host-free pid=%s -> %s", pid, result)
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

    async def handle_search_object(self, client, input, output):
        # MH3U is NEX 3.0.0 — it predates structure headers (settings["nex.struct_header"]
        # is False), so structures decode with NO version gating: NintendoClients' load()
        # reads the *latest* DataStoreSearchParam field set straight off the wire. MH3U's
        # retail param omits the trailing use_cache/total_count_enabled/data_types fields
        # (added in a later DataStore revision), so the generic extract() runs off the end
        # of the buffer -> OverflowError -> RMC returns an error -> the game treats the world
        # as broken and crashes the moment you accept the join. We never use the search
        # params (we always answer empty), so decode best-effort and never let a short
        # buffer become an RMC error.
        try:
            input.extract(datastore.DataStoreSearchParam)
        except Exception as e:
            logger.info("search_object: tolerated incompatible DataStoreSearchParam (%s)",
                        type(e).__name__)
        response = await self.search_object(client, None)
        output.add(response)

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
        caller = _pid(client)
        logger.info("request_probe_initiation_ext: targets=%s probe=%s (pid=%s)",
                    [str(u) for u in target_urls], station_to_probe, caller)
        # The server sends a packet to the target on the caller's behalf, so skip targets that
        # share no room with the caller. FAIL-OPEN (the hole-punch is critical): if the caller
        # is in no tracked room yet, `mates` is empty and we allow all.
        mates = set()
        try:
            for s in matchmaking_handlers.REGISTRY.sessions.values():
                if caller in s.participants:
                    mates |= set(s.participants)
        except Exception:
            mates = set()
        # Re-stamp the probe-back station onto the caller's REFLEXIVE endpoint -- the addr+port the
        # server OBSERVED the caller connect from (what _build_public publishes and get_session_urls
        # hands every joiner). Why it's needed: the client fills station_to_probe from its OWN NAT
        # discovery, which reads its real ISP NAT over the default route, NOT the overlay it reached
        # us on. On an overlay that doesn't own the default route (Radmin), that self-report is the
        # raw public IP, so forwarding it verbatim fires the hole-punch across the open internet
        # instead of the VPN => cross-plane, punch fails, "see the room but can't join it."
        #
        # Gate on ADDRESS divergence: only rewrite when the self-reported address != the reflexive
        # one. When they're equal -- the pure-public / PORT-FORWARD case, where NAT discovery and
        # the observed source are the same public IP -- leave the probe UNTOUCHED, so we never
        # rewrite a working public P2P port (over raw NAT the port IS the hole). That makes the fix
        # a strict no-op for public hosting; it only fires on a real overlay-plane split. When it
        # does fire we swap both address and port to the reflexive endpoint: the address puts the
        # punch back on the overlay, and the overlay routes whatever port. natf/natm are left as
        # reported. Fail-open: no reflexive station => forward verbatim.
        #
        # Verified live 2026-07-05 (Radmin, incl. a remote friend + cross-region JP<->US): baseline
        # forwarded the public IP verbatim => result=False; this restamp => reflexive 26.x =>
        # result=True + in-game join. Tailscale can't exercise this path -- it owns the default
        # route, so the self-report is already the 100.x overlay IP (no divergence, gate no-ops).
        probe = station_to_probe
        reflexive = matchmaking_handlers.STATIONS.get(caller)
        if reflexive is not None and reflexive["address"] != station_to_probe["address"]:
            probe = station_to_probe.copy()
            probe["address"] = reflexive["address"]
            probe["port"] = reflexive["port"]
            logger.info("  -> restamp probe pid=%s: %s:%s (self-reported) -> %s:%s (reflexive)",
                        caller, station_to_probe["address"], station_to_probe["port"],
                        probe["address"], probe["port"])
        for url in limits.bound_list(target_urls):
            rvcid = url["RVCID"]
            target_pid = matchmaking_handlers.CID_TO_PID.get(rvcid)
            if mates and target_pid is not None and target_pid not in mates:
                logger.warning("  -> DENY probe forward: RVCID=%s pid=%s shares no room with caller pid=%s",
                               rvcid, target_pid, caller)
                continue
            target_client = matchmaking_handlers.CLIENTS.get(target_pid)
            if target_client is None:
                logger.info("  -> no live connection for RVCID=%s (pid=%s); cannot forward probe",
                            rvcid, target_pid)
                continue
            try:
                out = streams.StreamOut(target_client.settings)
                out.stationurl(probe)
                await target_client.request(
                    nattraversal.NATTraversalProtocol.PROTOCOL_ID,
                    nattraversal.NATTraversalProtocol.METHOD_INITIATE_PROBE,
                    out.get(), noresponse=True)
                logger.info("  -> forwarded InitiateProbe(joiner=%s) to host pid=%s RVCID=%s",
                            probe, target_pid, rvcid)
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


def _shout_text(raw):
    """Best-effort: pull the readable tab-delimited payload (...\\t<shout text>) for logging.
    MH3U packs the shout plus context (lobby, room name, account id, name, lang, ...) as a
    tab-separated string inside the message body; the last field is the typed/quick-chat text."""
    try:
        import re
        runs = re.findall(r"[\x20-\x7e\t]{4,}", raw.decode("latin-1", "replace"))
        body = max((r for r in runs if "\t" in r), key=len, default="")
        return body.replace("\t", " | ") if body else (max(runs, key=len, default="") if runs else "")
    except Exception:
        return ""


def _shout_targets(sender):
    """Live pids to deliver a shout to: the sender's MOST-SPECIFIC gathering. MH3U's
    UserMessage layout does NOT match NintendoClients' (the decoded recipient comes out
    garbage), so we route by the SENDER's memberships, not the message's recipient field.

    Precedence matters: hall/lobby community membership PERSISTS while inside a room, so
    unioning room + hall (the pre-2026-07-06 behavior) fanned every room shout out to the
    whole hall = chat leaked across rooms. Rules now:
      - sender inside a room session  -> that room's participants only
      - sender in the hall/lobby only -> hall members who are NOT inside a room themselves
        (symmetric isolation: lobby chat doesn't pierce into rooms either)
    Fallback (sender in no tracked gathering): every connected client (beta default)."""
    live = set(matchmaking_handlers.CLIENTS.keys())
    pids = set()
    try:
        in_room = set()                # every pid currently inside ANY room session
        for s in matchmaking_handlers.REGISTRY.sessions.values():
            in_room |= set(s.participants)
            if sender in s.participants:
                pids |= set(s.participants)
        if not pids:                   # not in a room -> hall/lobby scope
            for c in matchmaking_handlers.COMMUNITY.communities.values():
                if sender in getattr(c, "participants", ()):
                    pids |= set(c.participants)
            pids -= in_room
    except Exception as e:
        logger.info("  -> SHOUT target-resolve error: %s", e)
    pids &= live
    if not pids:                       # sender not in a tracked gathering
        if limits.SHOUT_BROADCAST_FALLBACK:
            pids = set(live)           # beta default: broadcast to all (keeps shouts working)
        else:
            pids = {sender} & live     # hardened: sender-only, no all-players amplification
    # KEEP the sender in the target set (do NOT discard it). MH3U displays a shout only when
    # it RECEIVES one over the network (no local echo), so the server must echo each shout
    # back to the sender too. Without that echo the sender never sees their own message AND
    # -- observed live 2026-06-30 -- the client's shout send-gate never clears, blocking every
    # shout after the first (2nd+ shout never even reaches the compose/send buffer). Echoing
    # to the sender can't loop: receiving a DeliverMessage only displays, it never re-sends.
    return pids


class MessageDeliveryServer(_Trace, messaging.MessageDeliveryServer):
    """MH3U gathering-hall / room shoutouts ("quick chats"). The game sends each shout as
    MessageDelivery.DeliverMessage (proto 0x1B m1) and only DISPLAYS a shout when it RECEIVES
    one back from the network. Two independent things had to be fixed for shouts to work:
      1. RELAY each shout to the gathering's participants -- including the SENDER, so it sees
         its own message (no local echo). See _shout_targets().
      2. REPLY to the shout's RMC call. The client WAITS for that reply before re-arming its
         chat send-gate; without it only the first shout per login goes out. See __init__ /
         NORESPONSE (confirmed live 2026-06-30). NOT fire-and-forget, despite the lib default.
    (The in-game "too many shoutouts" warning is a separate client-side spam throttle.)

    We forward the original anydata bytes VERBATIM (no decode/re-encode) so any MH3U-vs-
    NintendoClients UserMessage layout drift can't corrupt the relayed message; the decode is
    best-effort, only for routing + logging."""
    LABEL = "MessageDelivery"

    def __init__(self):
        super().__init__()
        # CONFIRMED FIX 2026-06-30 (live, 2 players): MH3U's shout send-gate stayed shut after
        # the FIRST shout of each NEX login -- 2nd+ shout never even left the client, reset only
        # on reconnect, never on time. Cause: MH3U's client WAITS for an RMC reply to its
        # DeliverMessage (0x1B m1) before re-arming the chat. NintendoClients marks that protocol
        # NORESPONSE=True (fire-and-forget), so rmc.handle_request relayed the shout then returned
        # WITHOUT replying (proto=27 never appeared in the [RMC] response log). The client sat
        # forever awaiting that ack -> gate locked. Sending ANY success reply re-arms it: matt
        # spammed 10 shouts/login once we replied (was hard-capped at 1). An EMPTY success body
        # is sufficient -- no structured payload needed. The earlier _shout_targets self-echo fix
        # is still required too (it's what makes the SENDER display its own shout); this reply
        # fix is what makes the gate re-open. MH3U_SHOUT_REPLY: "empty"=empty success (default,
        # the confirmed fix), "struct"=Messaging(0x17)-shaped body (untested fallback),
        # "0"/"none"=old fire-and-forget no-reply (reproduces the bug; for A/B only).
        self._reply_mode = os.environ.get("MH3U_SHOUT_REPLY", "empty").lower()
        self.NORESPONSE = self._reply_mode in ("0", "", "none", "no", "off")

    async def handle_deliver_message(self, client, input, output):
        sender = _pid(client)
        raw = input.get()                      # exact request body (anydata message) -- forwarded verbatim
        logger.info("SHOUT pid=%s raw=%dB text=%r", sender, len(raw), _shout_text(raw))

        # Rate-limit the RELAY only (a modified client can spam DeliverMessage; each fans out
        # 1->N). Over the bucket we drop the relay but STILL reply below — gating the reply
        # would re-lock the client's send-gate (the 2026-06-30 bug).
        targets = set()
        if limits.shout_allowed(sender):
            targets = _shout_targets(sender)
            relayed = 0
            for pid in targets:
                conn = matchmaking_handlers.CLIENTS.get(pid)
                if conn is None:
                    continue
                try:
                    await conn.request(
                        messaging.MessageDeliveryProtocol.PROTOCOL_ID,
                        messaging.MessageDeliveryProtocol.METHOD_DELIVER_MESSAGE,
                        raw, noresponse=True)
                    relayed += 1
                except Exception as e:
                    logger.info("  -> SHOUT relay to pid=%s failed: %s", pid, e)
            logger.info("  -> SHOUT relayed to %d participant(s) [reply_mode=%s]", relayed, self._reply_mode)
        else:
            logger.warning("  -> SHOUT from pid=%s RATE-LIMITED (relay dropped; RMC reply still sent)", sender)

        # Optional RMC reply to the sender's own DeliverMessage (see __init__). With NORESPONSE
        # False, rmc.handle_request sends a success response carrying whatever we write here;
        # "empty" writes nothing -> an empty-body success (most likely just needs the call to
        # complete). "struct" mirrors the 0x17 response shape as a fallback if empty isn't enough.
        if self._reply_mode == "struct":
            output.anydata(raw)                       # modified_message (echo verbatim)
            output.list([], output.u32)               # sandbox_node_ids
            output.list([p for p in sorted(targets) if p != sender], output.pid)  # participants


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
        MessageDeliveryServer(),
    ]

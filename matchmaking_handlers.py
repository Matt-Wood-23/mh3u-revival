"""MH3U matchmaking — server-side logic (Phase 2).

Implements the core gathering-hall loop MH3U uses (confirmed from the .elf: it
calls CreateMatchmakeSession / BrowseMatchmakeSession / JoinMatchmakeSession +
the Community methods). The wire format is standard NEX (NintendoClients knows
it); this supplies the missing piece — an in-memory gathering registry and the
create/browse/join handlers.

Scope: enough to demonstrate "client A hosts a hunt room, client B searches and
joins" end-to-end against Python test clients (tests/test_matchmaking.py), no Cemu/dump.

Attribute structure DECODED by RE: NEX `MatchmakeSession.attribs[0..5]` =
MH3U `CRoom.value[3..8]`, and `game_mode` = `CRoom.value[0]` (host+search both run
the same 9-value loop; `CRoom_SetAttribute(index,value)` @0x0309a858). The *human
label* of each slot (target monster / quest / HR range / language) is still TBD —
one live Cemu room-host reveals the slot->meaning map instantly (the server logs
the session struct). The mechanics here are game-agnostic and already correct.
"""
import asyncio
import logging
import os
import secrets

from nintendo.nex import rmc, common, matchmaking

import host_roster_free
import limits

logger = logging.getLogger("mh3u.matchmaking")


async def _prefree_host_slot(pid):
    """Before admitting a (re)joiner, clear any STALE slot it still occupies in the host Cemu's
    roster. Covers the hard-drop path (Cemu crash/close sends no EndParticipation, so the leave-time
    free never fires and the reaper is 120s away) AND is a harmless no-op for a clean first/rejoin
    (nothing matches the pid). Runs off-thread; fail-safe. See host_roster_free."""
    result = await asyncio.to_thread(host_roster_free.free_guest_slot, pid)
    if "freed" in result:
        logger.info("join: pre-cleared stale host slot for pid=%s -> %s", pid, result)


def _pid(client):
    p = getattr(client, "pid", None)
    if callable(p):
        try:
            return p()
        except TypeError:
            pass
    return p


class _Session:
    def __init__(self, gid, gathering, host_pid, key):
        self.gid = gid
        self.gathering = gathering          # MatchmakeSession
        self.host_pid = host_pid
        self.key = key
        self.participants = {host_pid}


class GatheringRegistry:
    """In-memory store of live MatchmakeSessions (hunt rooms)."""
    def __init__(self):
        self._next_gid = 0x1000
        self.sessions = {}                   # gid -> _Session

    def create(self, gathering, host_pid):
        # Global room cap — stops a PID-cycling attacker growing sessions without bound.
        if len(self.sessions) >= limits.MAX_ROOMS:
            logger.warning("room cap: %d live rooms >= MAX_ROOMS(%d); rejecting create by pid=%s",
                           len(self.sessions), limits.MAX_ROOMS, host_pid)
            raise common.RMCError("RendezVous::LimitExceeded")
        self._next_gid += 1
        gid = self._next_gid
        gathering.id = gid
        gathering.owner = host_pid
        gathering.host = host_pid
        gathering.num_participants = 1
        sess = _Session(gid, gathering, host_pid, secrets.token_bytes(32))
        self.sessions[gid] = sess
        return sess

    def browse(self, criteria):
        out = []
        for s in self.sessions.values():
            g = s.gathering
            if criteria.game_mode not in ("", str(g.game_mode)):
                continue
            if criteria.vacant_only and g.num_participants >= g.max_participants:
                continue
            # each non-empty attribs filter must equal the session's attrib slot
            ok = True
            for i, want in enumerate(criteria.attribs):
                if want and i < len(g.attribs) and str(g.attribs[i]) != str(want):
                    ok = False
                    break
            if ok:
                out.append(g)
        return out

    def join(self, gid, pid):
        s = self.sessions.get(gid)
        if not s:
            raise common.RMCError("RendezVous::SessionVoid")
        # Fail-safe ceiling only, NOT the game's 4-player max: the real cap is client/P2P, and
        # rejecting near the operating point would bounce a legit rejoin during the ~45s ghost
        # window after a peer's Cemu crash (its slot is held until the reaper clears it).
        if pid not in s.participants and len(s.participants) >= limits.MAX_ROOM_PARTICIPANTS:
            logger.warning("room ceiling: gid=0x%x has %d participants >= MAX_ROOM_PARTICIPANTS(%d); "
                           "rejecting join by pid=%s", gid, len(s.participants),
                           limits.MAX_ROOM_PARTICIPANTS, pid)
            raise common.RMCError("RendezVous::SessionFull")
        s.participants.add(pid)
        s.gathering.num_participants = len(s.participants)
        return s.key

    def leave(self, pid):
        """Drop `pid` from every room it's in (called on disconnect).

        If the room's HOST leaves, the room is destroyed (so it stops showing up in
        browse / find_by_single_id and a stranded joiner bounces cleanly instead of
        spinning on a dead room). A guest leaving just decrements the room. Returns a
        list of (action, gid, remaining) describing what changed, for logging/notify.
        """
        affected = []
        for gid in list(self.sessions.keys()):
            s = self.sessions.get(gid)
            if not s or pid not in s.participants:
                continue
            if pid == s.host_pid:
                del self.sessions[gid]
                affected.append(("destroyed", gid, 0))
            else:
                s.participants.discard(pid)
                s.gathering.num_participants = len(s.participants)
                affected.append(("left", gid, len(s.participants)))
        return affected

    def leave_gathering(self, gid, pid):
        """Drop `pid` from ONE specific room — the in-game 'back out of room' signal
        (EndParticipation, proto 0x32 m1). Unlike leave() (connection-close, all rooms),
        this is the clean explicit leave MH3U sends the instant a player exits a room, so
        the browse/find count is correct immediately without waiting on a socket teardown.
        HOST backing out destroys the room; a guest just decrements. Returns
        (action, gid, remaining) or None if pid wasn't a member of that gid."""
        s = self.sessions.get(gid)
        if not s or pid not in s.participants:
            return None
        if pid == s.host_pid:
            del self.sessions[gid]
            return ("destroyed", gid, 0)
        s.participants.discard(pid)
        s.gathering.num_participants = len(s.participants)
        return ("left", gid, len(s.participants))

    def destroy(self, gid, owner_pid=None):
        """Remove a room by gid (the host's UnregisterGathering teardown; a guest uses
        EndParticipation instead). owner_pid gates it to the room's own host — gids are
        guessable, so this must not let anyone close anyone's room; None = unconditional for
        internal callers. Returns "destroyed" / "not_found" / "denied"."""
        s = self.sessions.get(gid)
        if s is None:
            return "not_found"
        if owner_pid is not None and s.host_pid != owner_pid:
            return "denied"
        del self.sessions[gid]
        return "destroyed"

    def reap_host(self, pid):
        """Destroy every room `pid` currently hosts. A host runs exactly one room at a
        time, so calling this right before it opens a new room clears any orphan left by a
        prior session that dropped without a clean leave (Cemu closed; or a reconnect under
        the same account whose stale-connection logout was skipped by the race guard — the
        cross-reconnect ghost room seen 2026-06-19, e.g. 0x1001 surviving into a new day).
        Returns the list of destroyed gids."""
        gone = []
        for gid in list(self.sessions.keys()):
            if self.sessions[gid].host_pid == pid:
                del self.sessions[gid]
                gone.append(gid)
        return gone


REGISTRY = GatheringRegistry()


# Beta is hard-capped at 4 players (one room per server). The hall/lobby LIST screens render the
# displayed max as (max_participants - offset) (world offset 2, lobby offset 1), so a raw max of
# 100 showed 98/99 — made it look like a 100-slot server. Tie hall, lobby, and room to this.
MAX_PLAYERS = 4

# Number of official Worlds (gathering halls) to advertise. Rooms are global (not tied to a
# hall), so multiple worlds all routed to the same room — pointless for a single-room beta.
# One world + its one lobby keeps the world-select screen honest. Bump to seed more later.
NUM_WORLDS = 1


def _make_official(gid, name):
    # Values chosen to pass the game's validation: server-owned, nonzero
    # participant counts (the lobby phase computes max/num - 1 and - 2, so 0
    # would underflow), a valid participation window (NEX DateTime is a packed
    # Y/M/D bitfield, so 0 = month0/day0 is an invalid date), default flags=512.
    c = matchmaking.PersistentGathering()
    c.id = gid
    c.owner = 2                 # SECURE_SERVER_PID — official halls are server-owned
    c.host = 2
    c.min_participants = 1
    c.max_participants = MAX_PLAYERS + 2     # placeholder; _Community sets the real per-type max
    c.participation_policy = 1
    c.policy_argument = 0
    c.flags = 512
    c.state = 0
    c.description = name
    c.type = 1                  # persistent/official
    c.password = ""
    # attribs[0] = the paired CHAT-LOBBY community gid (CNEXLobby reads attribs[0] via
    # FUN_02fa7d90 -> lobby_entry[1] -> CNEXLobby+0x1e4). On hall ENTER the game joins
    # TWO communities: the main lobby (this gid) AND a "chat lobby" (attribs[0]).
    # PhaseLoginLobbyAndChatLobbyCheck (FUN_030d9844) requires BOTH joins to succeed
    # (flags 0x40 main + 0x100 chat) or it aborts -> PhaseLogoutLobby -> disconnect.
    # attribs[0]=0 -> chat join uses gid 0 -> fails -> the "you have been disconnected"
    # on enter (root-caused 2026-06-18 via CNEXLobby phase RE). Use the hall's own gid so
    # the chat lobby == this (already-seeded) community and the second join succeeds.
    # attribs[2] = region bitmask. PhaseUpdateWorldWait (FUN_030ccd88) filters each
    # returned world by (attrib[2] & console_region_mask); 0xFFFFFFFF = match every region.
    c.attribs = [gid, 0, 0xFFFFFFFF, 0, 0, 0]
    c.application_buffer = b""
    c.participation_start = common.DateTime.make(2013, 1, 1)
    c.participation_end = common.DateTime.future()
    c.matchmake_session_count = 0
    # num_participants is now owned by _Community (set on construct + every join/leave) as
    # real_member_count + offset, so each list screen renders the LIVE population. The offset
    # also keeps the world occupancy (num-2) non-negative -> never trips the UpdateWorldWait
    # negative-occupancy join stall (FUN_030ccd88, 2026-06-16). A placeholder here is fine; it
    # is immediately overwritten by _Community.__init__.
    c.num_participants = 0
    return c


class _Community:
    # offset = what the list screen subtracts from num_participants to render Population.
    # Confirmed from live screenshots 2026-06-19: the WORLD list shows pop=(num-2)/max=(maxp-2)
    # (e.g. 2/98 from num=4,maxp=100), the LOBBY list shows pop=(num-1)/max=(maxp-1) (3/99). So
    # keeping num_participants = len(participants) + offset makes each screen display the REAL
    # live member count (world offset 2, lobby offset 1), and keeps the world occupancy non-
    # negative so it never trips the UpdateWorldWait join stall.
    def __init__(self, pg, official=False, offset=2):
        self.pg = pg
        self.participants = set()
        self.official = official
        self.offset = offset
        pg.num_participants = offset
        # Display the real beta cap (not 98/99): list screens render max as
        # (max_participants - offset), so max = MAX_PLAYERS + offset shows /MAX_PLAYERS.
        pg.max_participants = MAX_PLAYERS + offset

    def recount(self):
        self.pg.num_participants = len(self.participants) + self.offset


class CommunityRegistry:
    """Persistent gathering halls. Pre-seeds a few "official" halls players join.

    HIERARCHY (decoded 2026-06-18): the client treats a hall as a *World* and, right
    after joining it, calls FindLobbys ( = MatchMaking.find_by_owner, method 22 ) to
    enumerate the *Lobbys* inside that world. An EMPTY FindLobbys result is FATAL:
    CNEXLobby::PhaseFindLobbysWait (FUN_030d8358) sets error 0x4a000205 "Failed to find
    lobby" + flag 0x8, so PhaseLobbyLoadFinal (needs flags 0x4 AND 0x10) marks done-FAIL
    -> CNEXSystem "Update lobbys Failure" -> "you have been disconnected". (GetLobbysCommunity
    / find_community_by_gathering_id returning empty is, by contrast, TOLERATED.)
    So every world needs >=1 lobby gathering, returned from find_by_owner and resolvable
    via find_community_by_gathering_id."""
    def __init__(self):
        self._next_gid = 0x2000
        self.communities = {}                # gid -> _Community
        # gids of client-created communities (the only ones the caps/cleanup touch). Tracked
        # explicitly, NOT via the `official` flag — pre-seeded LOBBIES are official=False (to
        # stay out of the hall list) yet must never be reaped.
        self._runtime_gids = set()
        for i in range(1, NUM_WORLDS + 1):
            gid = 0x100 + i
            # Hall display name. The EUR build (region==4) parses names as a multi-
            # language ':'-separated packed string (EN:FR:DE:IT:ES); a SINGLE-segment
            # name makes its parser over-read -> wcslen(null+2) crash (root-caused
            # 2026-06-26). Sending the name as repeated ':'-segments keeps the EUR
            # parser in-bounds AND renders cleanly on every region: US/JP (region!=4)
            # skip the language formatter and take the first segment, so all regions
            # show "Gathering Hall N" (verified live US+EU 2026-06-27). Unconditional —
            # there is no downside on any region, so no per-client region detection is
            # needed. 8 segments (> the 5 languages) gives the parser extra margin.
            _name = ("Gathering Hall %d" % i)
            _hallname = ":".join([_name] * 8)
            self.communities[gid] = _Community(
                _make_official(gid, _hallname), official=True, offset=2)
        # One lobby per world (non-official so it never appears in the world/hall list).
        # gid scheme: world 0x10N -> lobby 0x20N. attribs[0]=self gid = paired chat lobby.
        self.lobbies = {}                    # world_gid -> lobby gid
        for i in range(1, NUM_WORLDS + 1):
            world_gid = 0x100 + i
            lobby_gid = 0x200 + i
            self.communities[lobby_gid] = _Community(
                _make_official(lobby_gid, "Lobby %d" % i), official=False, offset=1)
            self.lobbies[world_gid] = lobby_gid

    def officials(self):
        # Pre-seeded official halls (NOT filtered by owner — they are server-owned
        # now, owner=SECURE_SERVER_PID, so an owner==0 filter would drop them all).
        return [c.pg for c in self.communities.values() if c.official]

    def lobby_gatherings(self):
        # The lobbys (sub-gatherings) returned by FindLobbys (find_by_owner). For now
        # every world advertises the same lobby set; refine to per-world once the
        # world->lobby selection (tgt_lobby) is mapped live.
        return [self.communities[g].pg for g in self.lobbies.values()]

    def by_gids(self, gids):
        return [self.communities[g].pg for g in gids if g in self.communities]

    def by_participant(self, pid):
        return [c.pg for c in self.communities.values() if pid in c.participants]

    def _runtime(self):
        return [(gid, self.communities[gid]) for gid in self._runtime_gids if gid in self.communities]

    def create(self, pg, owner):
        # Cap client community creation (global + per-owner): it had no cap and no removal path,
        # so one client could loop it to exhaust memory. Cleanup is reap_owner() on logout.
        runtime = self._runtime()
        if len(runtime) >= limits.MAX_RUNTIME_COMMUNITIES:
            logger.warning("community cap: %d runtime communities >= MAX_RUNTIME_COMMUNITIES(%d); "
                           "rejecting create by owner=%s", len(runtime), limits.MAX_RUNTIME_COMMUNITIES, owner)
            raise common.RMCError("RendezVous::PersistentGatheringCreationMax")
        mine = sum(1 for _, c in runtime if c.pg.owner == owner)
        if mine >= limits.MAX_COMMUNITIES_PER_OWNER:
            logger.warning("community cap: owner=%s already owns %d runtime communities "
                           ">= per-owner cap(%d); rejecting", owner, mine, limits.MAX_COMMUNITIES_PER_OWNER)
            raise common.RMCError("RendezVous::PersistentGatheringCreationMax")
        self._next_gid += 1
        gid = self._next_gid
        pg.id = gid
        pg.owner = owner
        pg.host = owner
        c = _Community(pg, offset=2)
        c.participants.add(owner)
        c.recount()
        self.communities[gid] = c
        self._runtime_gids.add(gid)
        return gid

    def reap_owner(self, pid):
        """Destroy client-created communities owned by pid (cleanup on logout/reap); never
        touches pre-seeded halls or lobbies. Returns the gids removed."""
        gone = []
        for gid, c in self._runtime():
            if c.pg.owner == pid:
                del self.communities[gid]
                self._runtime_gids.discard(gid)
                gone.append(gid)
        return gone

    def leave(self, gid, pid):
        """Drop pid from ONE hall/lobby community and recount its live population (the
        explicit hall-exit: EndParticipation fires for the world gid (0x10N) and its lobby
        (0x20N) when a player backs out to the online menu). Returns True if pid was in it."""
        c = self.communities.get(gid)
        if not c or pid not in c.participants:
            return False
        c.participants.discard(pid)
        c.recount()
        return True

    def leave_all(self, pid):
        """Drop pid from every community + recount (connection-close cleanup, so a dropped
        player doesn't inflate world/lobby populations forever). Returns the gids it left."""
        left = []
        for gid, c in self.communities.items():
            if pid in c.participants:
                c.participants.discard(pid)
                c.recount()
                left.append(gid)
        return left

    def join(self, gid, pid):
        c = self.communities.get(gid)
        if not c:
            raise common.RMCError("RendezVous::SessionVoid")
        c.participants.add(pid)
        c.recount()


COMMUNITY = CommunityRegistry()


# pid -> hunter display name, learned opportunistically (e.g. from update_notification_data /
# the session app-buffer once that's decoded). Until then participant_details() falls back to a
# placeholder so the count is right even when the name isn't.
NAMES = {}


def participant_details(gid):
    """Build the live ParticipantDetails roster for a gid (a hunt room OR a hall/lobby) from
    real membership. This drives the in-lobby 'Connected players' headcount (the game polls
    get_detailed_participants(0x20N) while sitting in the Lobby Menu) and any roster UI — an
    empty list reads as 0/99 even when players are present. Names are placeholders for now
    (the hunter name isn't carried in the matchmaking layer yet); the count is the point."""
    sess = REGISTRY.sessions.get(gid)
    if sess:
        pids = sorted(sess.participants)
    else:
        comm = COMMUNITY.communities.get(gid)
        pids = sorted(comm.participants) if comm else []
    out = []
    for pid in pids:
        d = matchmaking.ParticipantDetails()
        d.pid = pid
        d.name = NAMES.get(pid, "Hunter%d" % (pid % 100000))
        d.message = ""
        d.participants = 1
        out.append(d)
    return out


# pid -> public StationURL (filled by SecureConnectionServer.register). The joiner fetches
# the host's StationURL from here (get_session_urls / get_participants_urls) to reach it P2P.
STATIONS = {}

# pid -> live RMCClient connection, and RVCID(connection id) -> pid (both filled by
# SecureConnectionServer.register). These let the server do server->client RMC: when the
# joiner asks to probe the host (NAT RequestProbeInitiationExt), we look up the host's
# connection by the target StationURL's RVCID and forward an InitiateProbe to it, so the
# host fires a probe packet back at the joiner (completes the P2P hole-punch).
CLIENTS = {}
CID_TO_PID = {}


def _placeholder_session():
    """A FULLY-POPULATED MatchmakeSession so output.anydata() can encode it (browse +
    find_by_single_id responses). NB: MH3U's real session wire layout differs (its create
    REQUEST decode overflows), so the joiner may still mis-read some fields — capturing the
    raw m6 bytes (run server with MH3U_RAW=1) is how we'll align the layout. Field set per
    MatchmakeSession.save() at nex.version=30000."""
    g = matchmaking.MatchmakeSession()
    # base Gathering
    g.id = 0
    g.owner = 0
    g.host = 0
    g.min_participants = 1
    g.max_participants = MAX_PLAYERS
    g.participation_policy = 0
    g.policy_argument = 0
    g.flags = 0
    g.state = 0
    g.description = ""
    # MatchmakeSession (v30000 encode order). MH3U uses 9 attribs (the CRoom 9-value loop).
    g.game_mode = 0
    g.attribs = [0, 0, 0, 0, 0, 0, 0, 0, 0]
    g.open_participation = True
    g.matchmake_system = 0
    g.application_data = b""
    g.num_participants = 1
    g.session_key = b""
    return g


class MatchmakeExtensionServer(matchmaking.MatchmakeExtensionServer):
    async def handle_create_matchmake_session(self, client, input, output):
        # MH3U's CreateMatchmakeSession (m6) carries a 2013-era MatchmakeSession whose wire
        # layout doesn't match NintendoClients' schema, so the stock decoder
        # (anydata -> string -> u16) runs off the end -> 0x80040001 -> the game bounces to the
        # village. Bypass the strict decode: create a room with a placeholder gathering and
        # return the gid + session_key the client needs. (Decoding the real session struct +
        # attribs is the follow-up; for now this unblocks hosting a room.)
        host = _pid(client)
        # A host runs one room at a time. Reap any room this pid still owns before opening
        # a new one — kills the cross-reconnect orphan (a stale room from a previous session
        # that never got a clean leave; deterministic, doesn't depend on socket-timeout).
        reaped = REGISTRY.reap_host(host)
        if reaped:
            logger.info("create_matchmake_session: reaped stale room(s) %s previously hosted by pid=%s",
                        [hex(g) for g in reaped], host)
        # MH3U create = anydata(MatchmakeSession) + string(message). It does NOT send a
        # trailing num_participants u16 -- that spurious read was the 0x80040001 "crash".
        # The anydata decodes cleanly: MH3U's MatchmakeSession layout == NintendoClients at
        # nex.version=30000 (9 attribs + a ~309B application_data blob w/ room name/host).
        # So decode + store the REAL room -> browse / find_by_single_id return the actual
        # session and the joiner decodes it correctly.
        message = ""
        try:
            gathering = input.anydata()
            try:
                message = input.string()
            except Exception:
                pass
        except Exception as e:
            logger.info("create_matchmake_session: decode failed, using placeholder (%s)", e)
            gathering = _placeholder_session()
        if not isinstance(gathering, matchmaking.MatchmakeSession):
            gathering = _placeholder_session()
        sess = REGISTRY.create(gathering, host)
        sess.gathering.session_key = sess.key
        logger.info("create_matchmake_session: gid=0x%x host=%s msg=%r game_mode=%s attribs=%s applen=%d",
                    sess.gid, host, message, getattr(gathering, "game_mode", "?"),
                    getattr(gathering, "attribs", "?"), len(getattr(gathering, "application_data", b"")))
        output.u32(sess.gid)
        output.buffer(sess.key)

    async def create_matchmake_session(self, client, gathering, description, num_participants):
        host = _pid(client)
        sess = REGISTRY.create(gathering, host)
        logger.info("create: gid=0x%x host=%s game_mode=%s max=%s",
                    sess.gid, host, getattr(gathering, "game_mode", "?"),
                    getattr(gathering, "max_participants", "?"))
        resp = rmc.RMCResponse()
        resp.gid = sess.gid
        resp.session_key = sess.key
        return resp

    async def browse_matchmake_session(self, client, search_criteria, range):
        # Return ALL live rooms regardless of criteria for now (MH3U's search-criteria
        # semantics not mapped yet) so the joiner reliably sees the host's room.
        results = [s.gathering for s in REGISTRY.sessions.values()]
        logger.info("browse: %d live room(s) gids=%s (pid=%s)",
                    len(results), [hex(g.id) for g in results], _pid(client))
        off = getattr(range, "offset", 0) or 0
        size = getattr(range, "size", 0) or 0
        return results[off:off + size] if size else results[off:]

    async def join_matchmake_session(self, client, gid, message):
        pid = _pid(client)
        await _prefree_host_slot(pid)   # clear any stale host slot (hard-drop rejoin)
        key = REGISTRY.join(gid, pid)
        logger.info("join: pid=%s -> gid=0x%x  (now %d participants)",
                    pid, gid, REGISTRY.sessions[gid].gathering.num_participants)
        return key

    async def handle_join_matchmake_session_ex(self, client, input, output):
        # MH3U's JoinMatchmakeSessionEx (m30) wire = gid:u32 + strMessage:string + bool(ignore_block_list).
        # It does NOT send the trailing num_participants u16 that NintendoClients' stock decoder reads
        # -> OverflowError "Buffer overflow" -> 0x80040001 -> joiner kicked. Exact same phantom-u16 bug
        # as create (m6). Decode only what MH3U sends, register the joiner as a participant, and return
        # the room's session_key (output.buffer) so the joiner can open the P2P link to the host.
        pid = _pid(client)
        gid = input.u32()
        message, ignore_block_list = "", False
        try:
            message = input.string()
            ignore_block_list = input.bool()
        except Exception:
            pass
        await _prefree_host_slot(pid)   # clear any stale host slot (hard-drop rejoin)
        key = REGISTRY.join(gid, pid)   # raises SessionVoid if the room is gone (clean RMC error)
        logger.info("join_matchmake_session_ex: pid=%s -> gid=0x%x msg=%r ignore_block=%s (now %d participants)",
                    pid, gid, message, ignore_block_list,
                    REGISTRY.sessions[gid].gathering.num_participants)
        output.buffer(key)

    async def open_participation(self, client, gid):
        # Called right after create_matchmake_session to open the new room for joiners.
        # NotImplemented here aborts the host flow -> bounce to village. Accept it.
        s = REGISTRY.sessions.get(gid)
        if s:
            s.gathering.flags = getattr(s.gathering, "flags", 0)
        logger.info("open_participation: gid=0x%x (pid=%s) -> ok", gid, _pid(client))
        return None

    async def close_participation(self, client, gid):
        logger.info("close_participation: gid=0x%x (pid=%s) -> ok", gid, _pid(client))
        return None

    async def update_application_buffer(self, *args):
        # MH3U sets per-session app data; accept + ignore for now.
        return None

    # --- friend / notification stubs (no friends backend) ------------------
    async def get_friend_notification_data(self, client, type):
        # Called right after register on entering online mode. No friend-presence
        # backend yet -> return an empty notification list.
        logger.info("get_friend_notification_data: type=%s (pid=%s) -> []", type, _pid(client))
        return []

    async def get_friend_notification_data_list(self, client, types):
        logger.info("get_friend_notification_data_list: types=%s (pid=%s) -> []", types, _pid(client))
        return []

    async def update_notification_data(self, client, type, param1, param2, param3):
        # Called right after entering online mode (once the fp friend-login completes).
        # It's a "set my notification data" op with an empty response; just accept it.
        logger.info("update_notification_data: type=%s p1=%s p2=%s p3=%r (pid=%s) -> ok",
                    type, param1, param2, param3, _pid(client))
        return None

    # --- Community (gathering hall) methods --------------------------------
    async def find_official_community(self, client, available_only, range):
        halls = COMMUNITY.officials()
        logger.info("find_official_community: %d hall(s) (pid=%s)", len(halls), _pid(client))
        off = getattr(range, "offset", 0) or 0
        size = getattr(range, "size", 0) or 0
        result = halls[off:off + size] if size else halls[off:]
        import os
        if os.environ.get("MH3U_EMPTY_OFFICIAL") == "1":
            logger.info("  (MH3U_EMPTY_OFFICIAL=1 -> returning [])")
            return []
        # DIAGNOSTIC 2026-06-15: full PersistentGathering elements are rejected by the
        # game (disconnect, no decode). Hypothesis: MH3U's older NEX findOfficialCommunity
        # returns lightweight SimpleCommunity (gid + matchmake_session_count), feeding the
        # GID list into FindCommunityByGatheringId. Test that wire shape.
        if os.environ.get("MH3U_SIMPLE_COMM") == "1":
            simple = []
            for pg in result:
                sc = matchmaking.SimpleCommunity()
                sc.gid = pg.id
                sc.matchmake_session_count = 0
                simple.append(sc)
            logger.info("  (MH3U_SIMPLE_COMM=1 -> returning %d SimpleCommunity)", len(simple))
            return simple
        return result

    async def find_community_by_gathering_id(self, client, gids):
        # MH3U calls this right after join_community with an EMPTY gid list, then leaves
        # the hall within ~1s if it returns [] (synchronous bail, not a timeout). The
        # game is doing a post-join "refresh my communities" — treat an empty list as
        # "return all officials" so the client's community state populates. Reuses the
        # same PersistentGathering encode that find_official_community already ships OK.
        out = COMMUNITY.by_gids(gids) if gids else COMMUNITY.officials()
        logger.info("find_community_by_gathering_id: gids=%s -> %d hall(s)", gids, len(out))
        return out

    async def find_community_by_participant(self, client, pid, range):
        out = COMMUNITY.by_participant(pid)
        logger.info("find_community_by_participant: pid=%s in %d hall(s)", pid, len(out))
        return out

    async def join_community(self, client, gid, message, password):
        pid = _pid(client)
        COMMUNITY.join(gid, pid)
        logger.info("join_community: pid=%s -> hall 0x%x (now %d)",
                    pid, gid, COMMUNITY.communities[gid].pg.num_participants)

    async def create_community(self, client, community, message):
        gid = COMMUNITY.create(community, _pid(client))
        logger.info("create_community: gid=0x%x owner=%s", gid, _pid(client))
        return gid

    async def update_community(self, client, community):
        return None

    async def update_privacy_setting(self, client, online_status, community_participation):
        return None

    async def get_my_block_list(self, client):
        return []

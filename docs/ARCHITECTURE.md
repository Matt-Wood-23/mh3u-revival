# MH3U Revival — Architecture & Design Decisions

> Status: **beta**. This document describes how the self-hosted MH3U online stack
> works and *why* it's built this way. Sections marked **(provisional)** are not yet
> end-to-end tested at the time of writing.
>
> **Just want to play?** This is the under-the-hood deep-dive — for plain step-by-step setup
> see **[HOSTING.md](HOSTING.md)** (running a game) or **[PLAYING.md](PLAYING.md)** (joining one).

Self-hosted Monster Hunter 3 Ultimate (Wii U) online multiplayer on Cemu, with **no
console dump**. The model is **"I host, friends join"**: one person runs the server and
their friends point their Cemu at it. Hunts are peer-to-peer — the server only brokers
matchmaking and presence; it never relays gameplay.

---

## 1. The layers

```text
  patched Cemu (each player)                  host machine
  ┌─────────────────────────┐         ┌──────────────────────────────┐
  │ MH3U game               │         │ NEX server (this repo)        │
  │  └ nn::act ACT_GetNex…  │──auth──▶│  auth server   :1223 (UDP)    │
  │     redirected to host  │         │   mints kerberos ticket       │
  │  └ NEX/PRUDP client     │─secure─▶│  secure server :1224 (UDP)    │
  │                         │         │   matchmaking / presence      │
  │  └ P2P (nNetwork)       │◀──────▶ │  (brokers hole-punch only)    │
  └─────────────────────────┘  P2P    └──────────────────────────────┘
            ▲   hole-punched UDP, Cemu◀▶Cemu (NOT through the server)   │
            └──────────────────────────────────────────────────────────┘
```

1. **Patched Cemu** (the `mh3u-revival` Cemu fork). Stock Cemu would try to reach
   Nintendo's (dead) servers. The fork redirects the game's `ACT_GetNexToken` account
   call to the host's server and hands the game a fixed `nexPassword`, from which the
   game derives its kerberos key. No Nintendo credentials, certs, or keys are used.
2. **Auth server (UDP 1223)** — Quazal Rendez-Vous authentication. Validates the login
   and mints a kerberos ticket for the secure server. See `server.py`.
3. **Secure server (UDP 1224)** — where matchmaking, gathering halls, rooms, and NAT
   traversal live. See `protocols.py` + `matchmaking_handlers.py`.
4. **P2P** — once two players are in a room, the actual hunt traffic flows **directly
   Cemu ↔ Cemu** over hole-punched UDP. The server only helps them find each other and
   coordinates the hole-punch; it is **not** in the gameplay path.

Credentials are not secrets — they're baked into the retail game and were recovered by
RE: `GAME_SERVER_ID = 0x10104d00`, `ACCESS_KEY = "cb2b2f5a"`, `NEX_VERSION = 30000`
(see `config.py`). Built on the open-source
[NintendoClients](https://github.com/kinnay/NintendoClients) library — the one dependency
that isn't on pip, so a host clones it next to the repo (see [HOSTING.md §1](HOSTING.md)).

---

## 2. Identity model (PIDs) — no central accounts

There is **no account server and no registration**. A player's identity is a NEX
**PrincipalId (PID)** stored locally in their Cemu `account.dat`. The server
auto-provisions any numeric PID it sees (`users.py:resolve`) and keys everything on it.

- **PIDs are random and local.** Each player generates a unique random PID once
  (`dist/make_account.py`, or the `PLAY MH3U ONLINE.bat` launcher in the MH3U Online Bundle).
  Range `0x40000000–0x6fffffff`; within a 4-player room the collision chance is ~6e-9.
- **Why random, not assigned.** The PID is baked client-side and the game roots its
  whole identity (and kerberos key derivation) in it, so the server *cannot* silently
  reassign it. An earlier manual scheme ("host=1, friends 2,3,4…") guaranteed collisions
  at scale; randomization is the fix.
- **Server-side guard.** `protocols.py:register` detects a same-PID collision (a
  *different* live connection already holding a PID) and logs it, but stays
  **last-writer-wins** — it never rejects, because a same-PID re-register is
  overwhelmingly a legitimate **reconnect**, which must not be broken (see §4).

---

## 3. Matchmaking & room lifecycle

State lives in `matchmaking_handlers.py`:

- `REGISTRY` — matchmake sessions (rooms): gid → participants.
- `COMMUNITY` — gathering halls (the lobby layer): hall → members.
- `CLIENTS` — pid → live RMC connection (for server→client RMC).
- `STATIONS` — pid → the player's P2P `StationURL` (what a joiner connects to).
- `CID_TO_PID` — connection-id → pid (for NAT-traversal forwarding).

**Join flow:** a joiner authenticates, `register`s its P2P station URL, then calls
`JoinMatchmakeSessionEx` (method 30 — the path MH3U uses). The server adds them to the
session and hands back the host's station URL. NAT traversal: the server forwards an
`InitiateProbe` between the two peers so their Cemus hole-punch a direct UDP path.

**Co-location advertise fix:** when the host *player* shares a machine with the server,
its Cemu connects via loopback, so the server observes `127.x` — useless to a remote
joiner. `MH3U_ADVERTISE=<reachable-ip>` substitutes the host's real address for
loopback-observed peers only (genuinely remote peers keep their observed address).

---

## 4. The rejoin problem and its fix (the hard part)

MH3U's host has **no native "a guest left the room" path** — no leave packet, no
P2P-disconnect detection for a lobby-persistent peer, and its NEX notification handler is
inert. So when a guest backs out, the host keeps a **stale participant**, and the next
rejoin drifts to a new roster slot (→ eventual out-of-bounds → "retrieving room info"
stall) *and* desyncs the roster vs. the station array (→ "host thinks peer is still
here" → disconnect).

Root cause is in the **host Cemu's memory**, not the server: the CNEXSystem participant
roster (`cnx+0x30d3c`, 0x70-stride) allocates the first slot whose **used-flag**
(`cnx+0x30d34`) is 0, so a stale used-flag makes it skip the slot and drift.

**Fix — the server mirrors the game's own "remove" across every view the host keeps in
sync** (`host_roster_free.py`): the roster record, the used-flag (the slot-alloc key),
the flag2 array, the membercount, the **station array** (`cnx+0x304`, fixes the
roster/station conn mismatch), and the **dirty flags** (`cnx+0x30d2c |= 0x7`, forces a
member-list recompute + UI redraw). Live-proven across repeated leave/rejoin cycles with
the guest pinned to its slot — no drift, no disconnect.

This is wired in two places:
- **`end_participation` (clean leave)** → free the slot immediately.
- **Join-time prefree (hard drop)** → on `JoinMatchmakeSession[Ex]`, pre-clear any stale
  slot for that PID *before* re-adding. A hard close (Cemu killed) sends no leave packet,
  so this covers it with no timing race; it's a no-op on a clean join.

**Important architectural constraint:** `host_roster_free` reaches into the host Cemu's
RAM (via pymem). It therefore only works when **the server runs on the same machine as
the host's Cemu** — which is exactly the "I host" model. Set `MH3U_HOST_FREE=0` to
disable it for any deployment where the host Cemu is *not* co-located with the server.

**Population layer — the reaper** (`reaper.py`): a hard drop also leaves the player
inflating the world/lobby count (PRUDP is UDP; no FIN). The reaper stamps a last-rx time
on every inbound packet and force-cleans any connection silent past `REAP_TIMEOUT`
(default 45s, 15s sweep) → decrements halls + rooms. It won't false-reap a live player
(they keep sending PRUDP pings); the one exception is a Cemu paused at a debugger
breakpoint (`MH3U_REAP_TIMEOUT=0` disables it for that case).

---

## 5. Reachability / networking

The gameplay P2P needs the two Cemus to reach each other. Three models, in order of how
we recommend them:

| Model | How | Exposes host IP? | CGNAT-proof? | Notes |
|---|---|---|---|---|
| **Overlay VPN** (Tailscale) | both ends join a private overlay; host advertises its `100.x` overlay IP | No | Yes | **Recommended.** Private, invite-only, no router config. Only the host organizes the tailnet; joiners just install the client + join it. |
| **Port-forward** | host forwards UDP 1223+1224, shares public IP | Yes | No | Power-user alternative, **untested so far (provisional)**. Dies behind CGNAT. |
| **Raw NAT hole-punch** | rely on NEX NATTraversal between two home routers, no overlay | minimal | partial | Best-effort. Works for cone NATs, fails for symmetric/CGNAT. **(provisional)** — only ever proven *inside* Tailscale (which already flattens NAT); never tested on the bare internet. |

The overlay is the **guaranteed fallback**: hole-punch alone can't connect symmetric-NAT
/ CGNAT players, so an overlay (or a future relay) is required for universal
connectivity. "Masking" the overlay behind a join-code launcher so players never see it
is on the roadmap (§7).

---

## 6. Why decentralized (and not "one big server")

A public, central matchmaking server everyone connects to would be a hosting/cost/
moderation/legal commitment — effectively a Nintendo-replacement service. That's
explicitly **out of scope** (it's what projects like Pretendo do). Instead:

- **Each host runs their own server for their own group.** Hundreds of users spread
  across hundreds of tiny independent servers — inherently horizontally scaled, zero
  central infrastructure, far less legal exposure.
- **Discovery is social** (e.g. a Discord "LFG"), not an in-app global server list. For
  pickup games, a community can run a shared "hub" server and post its join code.
- **No Nintendo data ever ships.** `otp.bin`/`seeprom.bin` are zeros; the "certs" are
  4-byte empty stubs that only satisfy Cemu's file-existence check. Every player brings
  their own legal dump.

---

## 7. Scope, status, and roadmap

**Beta scope (deliberate):**
- **Hard cap 4 players** → every server is exactly one room, the only configuration that
  has been hardened (the rejoin/reaper work above). This sidesteps the untested
  many-players / multi-room load profile.
- Open-source, non-commercial, dumpless, self-hosted. **Not** a public service.

**Tested:** identity generation (format + uniqueness + idempotency); clean leave/rejoin
and hard-drop rejoin (self-healing); reaper on a true abrupt close; four players P2P over
an overlay (Tailscale), cross-machine.

**Not yet tested (provisional):** Cemu loading a launcher-generated account end-to-end;
raw bare-internet hole-punch (only ever proven *inside* Tailscale, which already flattens
NAT); port-forwarded hosting over the open internet.

**Roadmap:** masked overlay (a join-code launcher that hides Tailscale setup); a relay
fallback for symmetric/CGNAT pairs; larger-capacity / community-hub hosting (under
investigation — the host explicitly does not run central infra for everyone).

---

## 8. Repo map

| Path | What |
|---|---|
| `server.py` | entry point; auth (1223) + secure (1224) servers, ticketing |
| `protocols.py` | secure-server RMC handlers (register, matchmaking, NAT traversal) + the PID guard |
| `matchmaking_handlers.py` | session/hall/client/station registries + join logic |
| `host_roster_free.py` | the host-Cemu roster free (the rejoin fix); co-located host only |
| `reaper.py` | liveness reaper (ghost-population cleanup) |
| `users.py` / `config.py` | PID resolution + kerberos derivation / RE'd credentials |
| `dist/` | player-distribution: `make_account.py`, `make_online_files.py` |
| `tests/` | in-process, dump-free self-tests (auth / matchmaking / community) + `udp_probe_listen.py` reachability diagnostic |

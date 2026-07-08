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
[NintendoClients](https://github.com/kinnay/NintendoClients) library — specifically a small
MH3U-patched [fork](https://github.com/Matt-Wood-23/NintendoClients) (legacy PRUDP v1
signature; upstream lacks it and breaks on Python 3.13). It's the one dependency that isn't on
pip, so a host clones it next to the repo (see [HOSTING.md §1](HOSTING.md)).

---

## 2. Identity model (PIDs) — no central accounts

There is **no account server and no registration**. A player's identity is a NEX
**PrincipalId (PID)** stored locally in their Cemu `account.dat`. The server
auto-provisions any numeric PID it sees (`users.py:resolve`) and keys everything on it.

- **PIDs are random and local.** Each player generates a unique random PID once
  (`dist/make_account.py`, or the `MH3U_Online.exe` launcher in the MH3U Online Bundle).
  Range `0x40000000–0x6fffffff`; within a 4-player room the collision chance is ~6e-9.
- **Why random, not assigned.** The PID is baked client-side and the game roots its
  whole identity (and kerberos key derivation) in it, so the server *cannot* silently
  reassign it. An earlier manual scheme ("host=1, friends 2,3,4…") guaranteed collisions
  at scale; randomization is the fix.
- **Server-side guard.** `protocols.py:register` detects a same-PID collision (a
  *different* live connection already holding a PID) and logs it, but stays
  **last-writer-wins** — it never rejects, because a same-PID re-register is
  overwhelmingly a legitimate **reconnect**, which must not be broken (see §4).

### Satisfying Cemu's online gate — without a dump

Before MH3U will even *attempt* Network Mode, Cemu has to consider the account
"online-ready." That's **three independent checks**, and the project satisfies each with
right-shaped *local* data — never Nintendo data — because the patched fork sends the real
connection to the host's server, so none of these checks needs a real Nintendo handshake:

1. **`HasRequiredOnlineFiles()`** — `otp.bin` / `seeprom.bin` / certificates must *exist*.
   We ship zeros + 4-byte stubs (`dist/make_online_files.py`); it's a file-*existence* check,
   not a crypto check (see §6).
2. **`IsValidOnlineAccount()`** — the `account.dat` must have a non-empty `AccountId`, a cached
   password (`IsPasswordCacheEnabled=1` + nonzero `AccountPasswordCache`), and a nonzero
   `PrincipalId` (Cemu's `Account::GetOnlineAccountError`). The launcher mints exactly that.
   **Failure mode that bit early testers:** if Cemu is ever launched *before* the launcher runs,
   it auto-creates a **blank offline** account (all those fields zero) and the gate fails with
   *"not linked to a NNID or PNID."* So the launcher **self-repairs** — it detects a blank
   account and re-mints (backing the blank up to `account.dat.offline.bak`) — and launch order
   no longer matters.
3. **NetworkService = Nintendo** — a per-account value in `settings.xml`
   (`<SelectedService … Service="1"/>`; the bundle pre-bakes it). The *Network Service* radio in
   Cemu's GUI is only editable when checks 1+2 already pass *and* no game is running
   (Cemu's `GeneralSettings2`), so a **greyed-out radio is a symptom of an unmet gate, never the
   cause** — the fix is repairing the account (re-run the launcher), not clicking the radio.

All three are Cemu-local preconditions; satisfying them with dummies + a self-consistent local
account is what makes dumpless online possible. (The player-facing version of this lives in
[PLAYING.md](PLAYING.md) troubleshooting.)

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

Root cause: every peer keeps a CNEXSystem participant roster (`cnx+0x30d3c`, 0x70-stride)
that allocates the first slot whose **used-flag** (`cnx+0x30d34`) is 0, and nothing P2P
ever clears a leaver's slot — on the real servers that was the job of a **server-pushed
NEX NotificationEvent** our server didn't send.

**Fix — send that notification** (`protocols.push_participation_left`): a NotificationEvent
(protocol 0xE) with **type 3007 (EndParticipation) / 3008 (Disconnect), param2 = leaver
PID** to each remaining room member. The game's NEX-backend notification dispatcher
(`FUN_030dd51c`) routes participation subtype 7/8 to its **native roster remove**
(`FUN_030c8ef8`): clears the used-flag, the record, decrements membercount, sets the dirty
flag. Because it's a plain server→client RMC it works for **remote hosts** and fixes the
*other guests'* roster copies too. Live-proven 2026-07-02: clean leave/rejoin vs local and
remote hosts, and hard-drop → reaper → 3008, all with zero memory writes.

This is wired in two places:
- **`end_participation` (clean leave)** → push type 3007 to the remaining members.
- **`logout` (hard drop / reaper)** → push type 3008 per affected room. A hard close
  (Cemu killed) sends no leave packet; the reaper detects the silence (~45–60s) and its
  cleanup fires the push.

**Legacy fallback:** `host_roster_free.py` (+ the join-time prefree) pokes the same fields
directly in a co-located host Cemu's RAM via pymem — the original fix from before the
notification path was found. Off by default; `MH3U_HOST_FREE=1` re-enables it. Only
scenario it still uniquely covers: a rejoin faster than the reaper window (<45s), which a
real Cemu relaunch can't achieve.

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
| **Overlay VPN** (Tailscale or Radmin) | both ends join a private overlay; host advertises its overlay IP (Tailscale `100.x`, Radmin `26.x`) | No | Yes | **Recommended.** Private, invite-only, no router config. The server re-stamps each P2P endpoint to the overlay plane, so hunts ride the VPN even though Cemu reports its public IP for the NAT probe — this is what makes **Radmin** work (verified live, incl. cross-region JP↔US). |
| **Public path** (port-forward / DMZ / passthrough) | host opens UDP 1223+1224 (or DMZ/passthroughs the PC), shares public IP | Yes | joiners yes, host no | **Proven live 2026-07** (DMZ/passthrough form): real session incl. a cellular-CGNAT joiner, no overlay. Host's line must have a real public IPv4. Guide: [PUBLIC_HOSTING.md](PUBLIC_HOSTING.md). |
| **Raw NAT hole-punch** | rely on NEX NATTraversal between two home routers, no overlay | minimal | partial | Best-effort. The reachable-host topology (NAT'd joiner → open host) is **proven on the bare internet** (2026-07, part of the public path above). NAT'd-peer ↔ NAT'd-peer (a joiner-hosted room) remains **(provisional)** — only ever proven *inside* Tailscale, which already flattens NAT. |

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
- **4 players per hunt room** → the game's own P2P limit, not raisable server-side
  (`MH3U_ROOM_MAX`, leave at 4). **Gathering halls hold more** — default 16
  (`MH3U_HALL_MAX`), server-tunable, since the hall is server-roster-fed and P2P is
  room-scoped. Multiple 4-player rooms per server are supported (the rejoin/reaper +
  multi-room churn hardening above); larger live halls are the current beta test.
- Open-source, non-commercial, dumpless, self-hosted. **Not** a public service.

**Tested:** identity generation (format + uniqueness + idempotency); a launcher-generated
random-PID account loaded by Cemu online end-to-end (a remote friend's bundle, in a real
session); clean leave/rejoin and hard-drop rejoin (self-healing); reaper on a true abrupt
close; four players P2P over an overlay (Tailscale), cross-machine; **public-internet
hosting with no overlay** — a 2-player session against the host's bare public IP,
including a cellular-CGNAT joiner P2P-connecting into the host's room
(see [PUBLIC_HOSTING.md](PUBLIC_HOSTING.md)).

**Not yet tested (provisional):** NAT'd-peer ↔ NAT'd-peer hole-punch on the bare internet
(a *joiner-hosted* room; the reachable-host direction is proven); the per-port-forward
variant of the public path (proven in its DMZ/passthrough form).

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
| `host_roster_free.py` | legacy pymem roster poke (pre-notification rejoin fix); off by default, co-located host only |
| `reaper.py` | liveness reaper (ghost-population cleanup) |
| `users.py` / `config.py` | PID resolution + kerberos derivation / RE'd credentials |
| `dist/` | player-distribution: `MH3U_Online.exe` launcher (JOIN/HOST GUI) + `PLAY MH3U ONLINE.bat` antivirus fallback (both mint/repair identity + launch), `make_account.py`, `make_online_files.py`, `bundle_settings.xml` (pre-baked online gate) |
| `tests/` | in-process, dump-free self-tests (auth / matchmaking / community) + `udp_probe_listen.py` reachability diagnostic |

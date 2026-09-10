# The guest-pair problem, and the room-host rule

*Findings from the first 3-player session with two real Wii U consoles, 2026-09-09.*

## The rule

> **The player with the most restrictive NAT must be the one who creates the room.**

In practice: whoever reports `natm=2` in `report_nat_properties`. If that player creates
the room, every link they are part of works. If anyone else creates it, that player ends
up in a guest-to-guest pair which cannot be established, and one of the two players in
that pair is ejected from the room a few seconds after joining.

This is a rule about **who clicks "create room"**, not a code change. Nothing in the
server currently surfaces it, so from a player's point of view the failure looks like a
random ejection.

## Why there is such a thing as a "guest pair"

MH3U meshes every player with every other player. The server brokers each link
separately, and links come in two kinds:

- **host pairs** - one end is the room host
- **guest pairs** - neither end is the room host

The two are not brokered the same way, and that asymmetry is the whole story.

| Players | Total pairs | Host pairs | Guest pairs |
|---:|---:|---:|---:|
| 2 | 1 | 1 | **0** |
| 3 | 3 | 2 | **1** |
| 4 | 6 | 3 | **3** |

**A 2-player room has no guest pairs at all.** This is why the problem was invisible until
a third player joined, and why every 2-player test - including the public-internet
console-to-PC session on 2026-09-03 - passed without a hint of it. The same two people who
fail as two guests connect fine when one of them hosts.

## Why host pairs survive and guest pairs do not

A host pair learns the relay endpoint through **two** independent channels:

1. the NAT-traversal probe exchange (`request_probe_initiation_ext` -> `InitiateProbe`), and
2. **the room's own station URL**, which `_host_station()` rewrites to the relay address.
   Every guest receives this simply by being in the room.

Channel 2 means both ends are already sending packets at the relay before the probe
handshake matters. That is directly visible in the logs as buffered datagrams being
delivered the moment the second endpoint appears:

```
relay (..., HOST, GUEST):27101 learned endpoint 1 (<addr-a>)
relay (..., HOST, GUEST):27101 learned endpoint 2 (<addr-b>)
relay (..., HOST, GUEST):27101 flushing 8 buffered datagram(s) to (<addr-b>)
```

A guest pair has only channel 1. Neither end *is* the room, so the probe exchange is the
only thing that ever tells them about each other.

**What the data actually shows (corrected 2026-09-09 after re-reading run 2).** An earlier
draft of this document blamed the `probeinit=0` flag - the probe exchange marks one side
passive, and the theory was that the passive side waits to receive before it sends. **Run 2
falsifies that**: `CONSOLE-A` was `probeinit=1`, the *initiator*, and still sent nothing to
the guest relay. The flag is not the discriminator.

What survives every run is narrower and is about the delivery channel, not the flag:

> `CONSOLE-A` acts on a relay address delivered via `get_session_urls` (channel 2), and
> never on one delivered only via `InitiateProbe` (channel 1). `CONSOLE-B` acts on both.

Consequences either way:

- **direct** (`MH3U_RELAY_PROBES=host`): a symmetric NAT on either end makes the punch
  impossible. Neither peer ever reports a result.
- **relayed** (`MH3U_RELAY_PROBES=all`): the relay learns a peer's endpoint only from a
  packet that peer sends. `CONSOLE-A` never sends to the guest relay, so the relay never
  learns where it is, so nothing can be forwarded to it. The guest relay port logs one
  endpoint, or none, and never flushes.

Relaying the guest pair therefore does **not** fix it. This was tested directly (see below)
and the failure was identical either way.

Whether the discriminator is the NAT type, console firmware, or something else about that
specific console is **not established** - the server-side logs cannot distinguish them.
Separating those needs client-side instrumentation, not more server logs.

## Evidence

Three participants, one evening, one server build, `MH3U_RELAY=force`:

| Label | Kind | NAT |
|---|---|---|
| `CEMU` | PC (Cemu), same machine as the server | `natm=1 natf=2` |
| `CONSOLE-A` | real Wii U | **`natm=2` natf=2** |
| `CONSOLE-B` | real Wii U | `natm=1 natf=2` |

Every 3-player attempt, by who created the room:

| Room host | Exposed guest pair | Contains `natm=2`? | Outcome |
|---|---|---|---|
| `CEMU` | `CONSOLE-A` <-> `CONSOLE-B` | yes | **fail** (x4, both join orders, both probe modes) |
| **`CONSOLE-A`** | `CEMU` <-> `CONSOLE-B` | no | **works** - full mesh, held 5.5 min |
| `CONSOLE-B` | `CEMU` <-> `CONSOLE-A` | yes | **fail** (x2) |

The failing pair is always the one containing `CONSOLE-A` while `CONSOLE-A` is not
hosting. Two of these outcomes were **predicted in advance** from the rule and both
confirmed.

Aggregate across every run: **12 `result=True` and zero `result=False`.** Every failure is
the *absence* of a result, never a reported failure - the pair simply goes silent and the
client leaves 3-8 seconds later. Worth knowing when reading logs: do not grep for
`result=False`, grep for a pair that never reports at all.

### The session that worked

With `CONSOLE-A` hosting:

```
relay allocated gid=0x1001 host=CONSOLE-A guest=CEMU      on :27100
relay allocated gid=0x1001 host=CONSOLE-A guest=CONSOLE-B on :27101
probe relay skipped (guest<->guest, MH3U_RELAY_PROBES=host): CEMU <-> CONSOLE-B
report_nat_traversal_result: result=True   CEMU      <-> CONSOLE-A   (relayed)
report_nat_traversal_result: result=True   CONSOLE-B <-> CONSOLE-A   (relayed)
report_nat_traversal_result: result=True   CONSOLE-B <-> CEMU        (direct)
STATUS players=3 rooms=1        # held for 5+ consecutive minutes
SHOUT ... -> relayed to 3 participant(s)   # from all three, two languages
```

Both console links relayed, the one guest pair direct between the two `natm=1` endpoints,
in-room chat flowing all three ways. **Participants confirmed completing a quest
together.** (Gameplay is P2P, so the server cannot observe a hunt directly - the
server-side evidence is the sustained 3-player room and the chat traffic.)

## Firsts established in this session

- Two real Wii U consoles and a Cemu client in one room over the public internet.
- **Console-to-console P2P established** - a link no 2-player test can exercise.
- **A Wii U can create a room** that other players find and join. Previously unknown.

## Consequences

- **4 players is harder, not equally hard.** Three guest pairs instead of one, so a single
  restrictive NAT among the guests breaks more of the mesh. Untested.
- **The privacy goal is not met above 2 players.** Guest pairs go direct under
  `MH3U_RELAY_PROBES=host`, so those two players exchange real addresses. Closing that
  needs the mechanism below, not a config change.
- **`MH3U_RELAY_PROBES=all` is not the answer** and should not be recommended as one. It
  relays guest pairs but they still deadlock, and it was the original suspect for
  "ejects the 3rd player".

## What would actually fix it

The relay cannot forward to a peer whose endpoint it has not learned, and the affected
peer never sends to a guest relay at all. Breaking that needs one of:

1. **Prime the relay from the server side.** The server sees each peer's self-reported
   probe address. Seeding the relay's peer list with it would let buffered datagrams flow
   immediately. *Known problem:* a symmetric NAT uses a different source port per
   destination - measured here, a console reported port `52958` while the relay actually
   observed `52942` - so the seeded address is wrong for exactly the peers that need it.
2. **Give guest pairs a second channel**, mirroring what the room station URL does for
   host pairs. This is the principled fix, but there is **no existing hook to hang it on**
   (measured 2026-09-09): `get_participants_urls` - the one method that would naturally
   carry a peer's StationURL - is **never called by the game**, either overload, across
   every session logged. `get_detailed_participants` *is* called constantly (108x in one
   evening) but its NEX return type carries no station URL. So this is
   **investigation-first**: find whether the game has any other RMC method or notification
   event that makes a client resolve a peer address, which needs client-side RE (Ghidra on
   the game binary, or Cemu instrumentation) rather than server work. If no such channel
   exists, this is not fixable at the NEX layer.
3. **Steer room creation toward the worst-NAT player** - implements the rule above
   automatically. Least effort, does not fix the underlying asymmetry, and cannot help a
   room where two players are `natm=2`.

## Reproducing / reading the logs

Run with `MH3U_RELAY=force MH3U_RELAY_PROBES=host` and watch for:

| Log line | Meaning |
|---|---|
| `relay allocated ... host=X guest=Y` | which player is in the host seat for this pair |
| `learned endpoint 1` / `2` | both ends found the relay; **one without the other is the failure** |
| `flushing N buffered datagram(s)` | the pre-pairing buffer delivering - healthy host pair |
| `probe relay skipped (guest<->guest...)` | this pair is going direct |
| `report_nat_traversal_result: result=True` | the link is up. Expect `n*(n-1)/2` of them |
| pair with no result at all | **the failure signature** - ejection follows in 3-8 s |

`report_nat_properties` logs each player's `natm`/`natf` at connect time, which is where
the `natm=2` player is identified.

## Status

Rule confirmed, mechanism strongly evidenced but not instrumented at the station-URL path
specifically. No code changes were made as a result of this session - the server build
used was the current `console-relay` branch.

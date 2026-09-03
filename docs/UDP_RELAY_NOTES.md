# UDP Relay

This fork adds an optional UDP relay for MH3U gameplay peer links. The normal
NEX flow advertises each player's direct `StationURL` and relies on UDP NAT
traversal. That can fail for players behind CGNAT, symmetric NAT, strict router
rules, or other networks that do not allow reliable peer-to-peer UDP.

When the relay is selected, the server advertises a relay endpoint instead of the
peer player's direct UDP endpoint. Both clients send their encrypted gameplay UDP
to the relay port, and the relay forwards packets between the two observed
endpoints. Relays are allocated per peer pair, so this can cover host-to-guest
links and guest-to-guest mesh links in 3-4 player rooms.

## Relay modes

The relay is disabled by default:

```powershell
$env:MH3U_RELAY="off"
```

Enable forced relay:

```powershell
$env:MH3U_RELAY="force"
```

Enable automatic relay learning:

```powershell
$env:MH3U_RELAY="auto"
```

Supported values:

| Value | Behavior |
|---|---|
| `off` | Advertise normal direct peer-to-peer endpoints. |
| `force` | Advertise relay endpoints for every eligible room peer link. |
| `auto` | Start with direct peer-to-peer. If a direct NAT traversal fails, remember that PID pair in memory and relay that pair on later attempts during this server uptime. |

## Auto mode memory

Auto mode keeps process-local state only. It is not written to a database or file,
and restarting the server clears it.

Client state is keyed by the player's NEX PID, which is stable for the same local
`account.dat`. Connection IDs (`cid` / `RVCID`) are generated per connection and
are only used to resolve a NAT traversal result back to the other currently
connected PID. Learned relay decisions are stored by PID pair:

```text
(min(pid_a, pid_b), max(pid_a, pid_b))
```

Default in-memory caps and TTLs:

```powershell
$env:MH3U_RELAY_AUTO_MAX_CLIENTS="500"
$env:MH3U_RELAY_AUTO_MAX_PAIRS="2000"
$env:MH3U_RELAY_AUTO_PAIR_TTL="259200"
$env:MH3U_RELAY_AUTO_CLIENT_TTL="3600"
```

`MH3U_RELAY_AUTO_PAIR_TTL` controls how long a failed direct pair should be
relayed after the failure. `MH3U_RELAY_AUTO_CLIENT_TTL` is used when a client's
NAT flags are configured as relay-worthy. Setting either max cap to `0` disables
storage for that category.

The server records endpoint-plane mismatches for diagnostics, but mismatch alone
does not currently force relay. The Radmin/Tailscale restamp path may still make
direct P2P work without relay.

Optional NAT flag forcing is available once the game's `natm` / `natf` values are
decoded from live captures:

```powershell
$env:MH3U_RELAY_AUTO_BAD_NATM="3"
$env:MH3U_RELAY_AUTO_BAD_NATF="2,4"
```

Leave these unset until those constants are known.

## Advertised address

The relay advertises this address to clients:

```powershell
$env:MH3U_RELAY_ADVERTISE="YOUR_PUBLIC_IP_OR_HOSTNAME"
```

## Relay ports and capacity

The relay uses one UDP socket per relayed **peer pair**, and a 4-player room meshes
fully — so a full room needs **6 ports**, not 1. Size the range against `MH3U_MAX_ROOMS`:

```
ports needed = MH3U_MAX_ROOMS x 6
```

At the default `MH3U_MAX_ROOMS=48` that is 288 ports, e.g.:

```powershell
$env:MH3U_RELAY_PORT_START="27100"
$env:MH3U_RELAY_PORT_END="27387"
```

The server prints a warning at startup if the pool is smaller than that, naming the
exact `MH3U_RELAY_PORT_END` to set. Whatever range you choose must be open in the
host's firewall.

## Mixed LAN + internet rooms

`MH3U_RELAY_ADVERTISE` is published to every player, and one address cannot suit both
halves of a mixed room. Hand out the public address and a player on the **server's own
LAN** must hairpin out through the router and back in, which many routers refuse; hand
out the LAN address and remote players cannot reach it at all.

So when the relay is published on a **public** address, peers the server observes on a
**private** address are given a LAN address instead:

```powershell
$env:MH3U_RELAY_ADVERTISE_LAN="192.168.1.50"
```

Auto-detected from the default route when unset, and only accepted if that address is
actually private — on an IP-passthrough host the default route is the public address,
which would be useless here, so it is rejected and the field stays empty. **Set it
explicitly if your host has several NICs**, or if auto-detection picks a Radmin /
Tailscale / Hyper-V adapter.

This mirrors what the server already does for direct connections, where `_build_public()`
stamps each peer with the address it was actually observed on.

Unchanged in every other case: pure-LAN deployments, overlay networks (Radmin `26.x` and
Tailscale `100.64/10` do not read as private), and any host where no private address is
known all keep using the single `MH3U_RELAY_ADVERTISE` value for everyone.

## Behaviour when the pool is exhausted

This differs by mode, on purpose:

| Mode | On allocation failure |
|---|---|
| `auto` | Falls back to direct P2P. Correct: auto is best-effort NAT rescue, and direct is simply what would have happened anyway. |
| `force` | **Fails closed** — the join is refused and no address is returned. |

`force` deliberately does *not* fall back. An operator running force has asked for
every link to be relayed, usually to keep players' IP addresses private; quietly
handing out a real StationURL instead would revoke that guarantee with nothing but a
log line to show for it. A refused join is visible and fixable; a silent privacy
regression is neither.

## Endpoint pinning (`MH3U_RELAY_STRICT`)

A relay port otherwise belongs to the first two endpoints that send to it, with no tie
to the NEX session. Strict mode drops datagrams whose **source IP** is not one of the
pair's registered addresses:

```powershell
$env:MH3U_RELAY_STRICT="1"
```

**Off by default, and pinning is IP-only.** Port pinning is impossible: measured on
real hardware (2026-09-03) the game opens a *separate* UDP socket for gameplay, so a
Wii U registered on PRUDP `:61906` sent from `:55250`, and a Cemu client `:58828` sent
from `:64005`. IP pinning is workable but not free either — on an overlay network a
peer can legitimately send from its Radmin/Tailscale address rather than the one its
NEX connection was observed on. Mismatches are therefore **always logged** even with
strict off; turn it on once your own logs show no false positives.

## Limitations

This relay is intentionally lightweight. A relay port learns the first two UDP
endpoints that send packets to it, then forwards datagrams between them. It does
not authenticate relay users independently from the surrounding NEX session
state.

That is usually acceptable for small hosted deployments. `MH3U_RELAY_STRICT=1` adds
source-IP validation (see above); it is not a substitute for a properly hardened relay
service if you run a large public server.

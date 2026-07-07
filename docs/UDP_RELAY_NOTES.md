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

## Relay ports

The relay uses one UDP socket per relayed peer pair. Choose a contiguous UDP
range large enough for the number of simultaneous relayed peer pairs you want to
support.

Example 64-port range:

```powershell
$env:MH3U_RELAY_PORT_START="27100"
$env:MH3U_RELAY_PORT_END="27163"
```

## Limitations

This relay is intentionally lightweight. A relay port learns the first two UDP
endpoints that send packets to it, then forwards datagrams between them. It does
not authenticate relay users independently from the surrounding NEX session
state.

That is usually acceptable for small hosted deployments, but it is not a general
purpose hardened relay service. If you run a large public server, consider adding
stronger endpoint validation before accepting traffic on a relay port.

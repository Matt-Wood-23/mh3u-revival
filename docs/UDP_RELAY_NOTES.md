# UDP Relay

This fork adds an optional UDP relay for MH3U gameplay peer links. The normal
NEX flow advertises each player's direct `StationURL` and relies on UDP NAT
traversal. That can fail for players behind CGNAT, symmetric NAT, strict router
rules, or other networks that do not allow reliable peer-to-peer UDP.

When the relay is forced, the server advertises a relay endpoint instead of the
host player's direct UDP endpoint. Both clients send their encrypted gameplay UDP
to the relay port, and the relay forwards packets between the two observed
endpoints.

## Relay modes

The relay is disabled by default:

```powershell
$env:MH3U_RELAY="off"
```

Enable forced relay:

```powershell
$env:MH3U_RELAY="force"
```

Supported values:

| Value | Behavior |
|---|---|
| `off` | Advertise normal direct peer-to-peer endpoints. |
| `force` | Advertise relay endpoints for every room host-to-guest gameplay link. |

## Advertised address

The relay advertises this address to clients:

```powershell
$env:MH3U_RELAY_ADVERTISE="YOUR_PUBLIC_IP_OR_HOSTNAME"
```

## Relay ports

The relay uses one UDP socket per host-to-guest pair. Choose a contiguous UDP
range large enough for the number of simultaneous relayed player pairs you want
to support.

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

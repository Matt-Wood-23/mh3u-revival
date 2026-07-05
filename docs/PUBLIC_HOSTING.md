# Hosting over the public internet (no VPN)

Host your MH3U Revival server on your **bare public IP** so friends join with nothing but
the bundle and your address — no Tailscale, no overlay, no setup on their end at all.

**Status: proven end-to-end.** A real two-player session has run this way — auth,
matchmaking, and the P2P hunt link — including a joiner behind **cellular CGNAT** (the
most hostile NAT there is). The joiner needs zero network config; all the work is on the
host side, once.

> **Should you use this instead of an overlay (Tailscale / Radmin)?** The overlay
> ([HOSTING.md §3](HOSTING.md#3-make-the-server-reachable)) is still the recommended
> default: it's private, needs no router access, and works even if *you* are behind CGNAT.
> Choose the public path when you can't or don't want to put friends on an overlay, and
> you're OK with the trade-offs: your **public IP is exposed** to everyone you invite, you
> need **admin access to your router**, and your line must have a **real public IPv4**.

**Why this works for CGNAT friends:** the game's rooms are hosted by *you*. Joiners only
ever make **outbound** connections — to your server (matchmaking) and to your Cemu (the
hunt). Outbound works from behind any NAT. So only the host's side needs to accept
unsolicited inbound traffic, and that's exactly what the steps below open up.

What has to be reachable on the host, all **UDP**:

| Port | What |
|---|---|
| `1223` | NEX auth server |
| `1224` | NEX secure server (matchmaking) |
| dynamic | your Cemu's P2P port (game picks it per session — see the firewall step) |

---

## Step 0 — Confirm you're not behind CGNAT

If your ISP puts you behind carrier-grade NAT, no router setting can make inbound work —
stop here and use the overlay. Two quick checks:

1. `tracert -d 8.8.8.8` — the **first** hop is your router. If the **second** hop is
   already a public address, you're fine. If you see more private-range hops
   (`10.x`, `172.16–31.x`, `192.168.x`) or anything in `100.64.x–100.127.x` before
   reaching public space, that's CGNAT.
2. Compare the WAN/Internet IP shown in your **router's status page** with what the world
   sees (`curl ifconfig.me`). If they differ, you're behind CGNAT.

Note your public IP — it's the address friends will type in. It can change when your
ISP renews your lease, so re-check it (`curl ifconfig.me`) before each session and tell
your friends the current one.

## Step 1 — Router: deliver inbound traffic to your PC

Every router UI is different; you're looking for one of these two features. Both are
usually under names like *Port Forwarding*, *NAT*, *Gaming*, *Virtual Server*, *DMZ*, or
*IP Passthrough*.

**Option A — port forwarding (the surgical one).** Forward **UDP 1223 and 1224** to your
PC's LAN IP. Gotchas seen in the wild:

- **TCP and UDP are forwarded independently.** A rule that only says TCP does nothing for
  the game. Pick UDP (or both).
- **Device dropdowns lie.** Routers that make you pick a *device* instead of typing an IP
  often hold stale/duplicate entries (a PC with a VPN adapter or virtual switch can appear
  several times). If the forward silently doesn't work, this is a prime suspect.
- Some routers don't apply new forwards until **rebooted**.
- Some gateways run a separate **firewall / packet-filter layer on top of forwarding** —
  a forward alone may not be enough until a matching "Pass"/allow rule (your ports +
  protocols to your PC) exists there too. Conversely, filter rules pinned to your PC's
  **LAN IP** go inert under Option B (inbound traffic is then addressed to the *public*
  IP, so they no longer match) — don't count on them, and don't be confused by them.
- Your Cemu's P2P port is dynamic, so a per-port forward can't cover it — this still works
  for most sessions (the joiner punches outward first), but if hunts fail to start while
  the hall works, that's the gap. Option B doesn't have it.

**Option B — DMZ / IP Passthrough (the sledgehammer — and what's actually proven).** Tell
the router to send **all** inbound traffic to your PC (some gateways can even hand the PC
the public IP itself). Prefer a mode that binds to your PC's **MAC address** — that
sidesteps the stale-device-list problem entirely. Notes:

- Protocol-agnostic and port-agnostic: covers 1223, 1224, *and* the dynamic P2P port.
- Your PC is then **directly exposed** — Windows Firewall becomes your only shield. That's
  manageable (Step 2), but read the security section before choosing this.
- May need a router reboot to take effect — or just `ipconfig /release` + `ipconfig /renew`
  on the PC if the router hands over the public IP via DHCP.
- Other devices on your LAN are unaffected (they keep using the router's NAT).

## Step 2 — Windows Firewall (where working setups secretly die)

Two parts. The first is the obvious one; the second is the trap that produces
"I forwarded everything and it still times out."

**2a. Allow the server ports.** In an **admin** terminal:

```bat
netsh advfirewall firewall add rule name="MH3U NEX 1223" dir=in action=allow protocol=UDP localport=1223
netsh advfirewall firewall add rule name="MH3U NEX 1224" dir=in action=allow protocol=UDP localport=1224
```

**2b. Hunt down hidden Block rules.** ⚠️ **In Windows Firewall, a Block rule always beats
an Allow rule.** When any program first listens on a network, Windows pops an "Allow this
app?" dialog — and if it was ever **dismissed or cancelled**, Windows silently created
**Block** rules for that program (usually on the *Public* profile). Two programs matter
here, and both are famous for having these:

- **your Python** (runs the server) — blocks kill ports 1223/1224 even with the 2a rules
  in place
- **your Cemu** (`Cemu_release.exe`) — blocks kill the P2P hunt link even when
  matchmaking works

Audit (admin PowerShell):

```powershell
Get-NetFirewallRule -Direction Inbound -Enabled True -Action Block |
  Format-Table DisplayName, Profile
```

If Python or Cemu (or any rule naming them) shows up, fix it — either flip the rule to
Allow (keeps it scoped to that program):

```powershell
Get-NetFirewallRule -DisplayName '<name from the list>' |
  Where-Object { $_.Action -eq 'Block' } | Set-NetFirewallRule -Action Allow
```

or disable it (`... | Disable-NetFirewallRule`). Re-run the audit until neither program
appears.

> **Why your Tailscale-tested setup can still be broken here:** VPN/overlay adapters
> register as **Private** networks, but your internet-facing connection — especially under
> DMZ/passthrough — is classified **Public**. Rules are per-profile, so a setup that
> worked perfectly over Tailscale can be fully blocked on the public path and you'd never
> have noticed. Check the *Public* profile's rules specifically, and make sure the 2a
> rules apply to all profiles (the commands above do).

Don't "fix" this by reclassifying the network as Private — on the public path the Public
profile's stricter defaults are exactly what you want. Fix the specific rules instead.

## Step 3 — Start the server advertising your public IP

```bat
set MH3U_ADVERTISE=<your-public-ip> & python server.py
```

This matters more than it looks: joiners auth at `<your-public-ip>:1223`, but everything
after that follows addresses **the server hands out** (the secure-server ticket, and your
Cemu's P2P station URL). `MH3U_ADVERTISE` is what gets baked into those. If you advertise
a LAN/overlay/loopback address, friends will log in fine and then fail — the classic
symptom is "connected to the internet", then dropped to the village.

You play as normal on the same PC (`127.0.0.1` in `mh3u_server.txt` — the server
substitutes your public IP when advertising you to others). An IP always fits the
15-character `mh3u_server.txt` limit, so friends just enter your public IP.

## Step 4 — Test it (from OUTSIDE your network)

> **The golden rule: a test from inside your own LAN proves nothing.** Traffic from your
> LAN to your own public IP depends on your router's "hairpin" support, and many home
> networks also block PC↔PC traffic outright. A failure tells you nothing, and a pass
> doesn't prove the internet path either. Use a genuinely external vantage point — a
> laptop on a **phone hotspot** is perfect (and doubles as a realistic CGNAT joiner).

Climb this ladder; each rung isolates a different layer.

**Tier 0 — TCP sanity check (DMZ/passthrough only).** With a TCP listener on 1223 (and a
temporary TCP allow rule), submit your IP/port at [canyouseeme.org](https://canyouseeme.org).
"Success" proves the router is delivering inbound. ⚠️ canyouseeme is **TCP-only** and the
game is **UDP** — under *per-port forwarding* (Option A) a TCP result proves nothing about
your UDP rules, in either direction. Only under DMZ/passthrough (protocol-agnostic
routing) is it meaningful. Delete the temp TCP rule afterwards.

**Tier 1 — raw UDP reachability.** On the host (with the live server **stopped** — it
owns the ports): `python tests/udp_probe_listen.py 1223 1224`. On the external box:
`python tests/udp_probe_send.py <your-public-ip> 1223 1224`. The sender prints PASS when
the host's echo comes back.

**Tier 2 — the real protocol.** Start the server as in Step 3. The external box needs the
repo *and* the patched NintendoClients laid out as siblings (same layout as
[HOSTING.md §1](HOSTING.md#1-get-the-server-and-run-it)), plus
`pip install -r requirements.txt`. Then:

```bat
python tests/extkit/check_server_leg.py <your-public-ip>
```

This drives one headless player through the full life cycle — UDP auth on 1223, kerberos
ticket, secure register on 1224 *via the advertised address*, hall join, room create. All
phases passing = the server leg is proven end-to-end; the script explains what each
failing phase means.

**Tier 3 — a real joiner.** A friend (or your hotspot laptop running the bundle) enters
your public IP and joins your room. The room join exercises the last layer Tier 2 can't:
the game-to-game P2P link.

### When a tier fails: find out *who* ate the packet

Windows ships a packet sniffer. In an admin terminal:

```bat
pktmon filter remove
pktmon filter add -p 1223
pktmon start --capture --file-name %TEMP%\mh3u_cap.etl
```

Re-run the failing probe, then:

```bat
pktmon stop
pktmon etl2txt %TEMP%\mh3u_cap.etl -o %TEMP%\mh3u_cap.txt
```

(The output text is UTF-16 — open it in an editor rather than grepping it raw.) Read it
like this:

| You see | Meaning | Fix |
|---|---|---|
| nothing inbound from the prober's IP | packet never reached the PC | router (Step 1) — or CGNAT/ISP filtering (Step 0) |
| inbound packet **and** a `Drop … INET: accept inspection` line | the router delivered it; **Windows Firewall** rejected it | hidden Block rules (Step 2b) or missing allow (2a) |
| inbound packet, no drop, but the app never reacts | delivered and admitted, wrong destination | is the listener/server actually running on that port? |

This one capture turns "it times out, could be anything" into a definite router-vs-local
answer in about a minute.

## Security notes (read me before going live)

- **Your public IP is a secret you hand to every player.** Anyone with it can probe you,
  and a griefer can DoS you. Invite accordingly — for strangers, prefer the overlay.
- Under **DMZ/passthrough**, *every* port on your PC faces the internet and Windows
  Firewall is the only guard. Audit what else is allowed inbound on the **Public** profile
  — broad program rules like "python.exe, any port" are now internet-facing. Tighten to
  the port-scoped rules from 2a where you can. Per-port forwarding (Option A) doesn't have
  this blast radius.
- Undo is cheap and worth knowing: turn off the DMZ/passthrough or delete the forwards,
  and delete the 2a rules (`netsh advfirewall firewall delete rule name="MH3U NEX 1223"`,
  same for 1224).

## What's proven vs. not (as of 2026-07)

**Proven live:** the full public path — external UDP auth/matchmaking, and a 2-player
session where a **cellular-CGNAT** joiner P2P'd into a room hosted on a
passthrough-exposed host (`NAT traversal result=True`).

**Not yet proven:** a *joiner-hosted* room between two NAT'd players over the bare
internet (irrelevant for the normal "you host, friends join" topology); per-port
forwarding specifically (Option A — proven only in the DMZ/passthrough form, Option B);
UDP tunnel services (playit.gg-style) are **unsupported** — the server can't yet advertise
a port different from the one it binds, which tunnels require.

**Alternative if your router/ISP won't cooperate:** a cheap VPS has a real public IP with
no router at all — the server runs there with `MH3U_HOST_FREE=0` (see
[HOSTING.md — environment variables](HOSTING.md#environment-variables); the rejoin
auto-fix needs the server co-located with the host's Cemu, so remote hosting loses it).
Or just use the overlay.

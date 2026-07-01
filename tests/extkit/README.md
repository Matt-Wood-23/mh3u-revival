# External test kit — validating the public port-forward path

The goal: prove a remote friend can reach the host's NEX server at
`<public-ip>:1223/1224` WITHOUT Tailscale. You can **only** test this from a network
that is NOT behind the host's own router (LAN traffic to the public IP depends on
hairpin support and gives false passes AND false failures). A **phone hotspot on a
laptop** is a perfect vantage — it's cellular, genuinely off the home NAT.

> Why not canyouseeme.org? It's **TCP-only**. NEX/PRUDP is **UDP**. A TCP timeout does
> NOT mean the UDP forward is broken, and most routers forward TCP/UDP independently.
> The probes below test the real (UDP) path.

## Topology

```text
  [Machine A: HOST]  behind the home router  (forward target, e.g. LAN 192.168.1.50)
        run the LISTENER here (NEX server STOPPED)
                         |  port-forward 1223,1224
                    public IP  <public-ip>
                         |
  [Machine B: EXTERNAL]  on the PHONE HOTSPOT  (off the home NAT)
        run the SENDER here, aimed at the host's PUBLIC IP
```

## Tier 1 — UDP reachability (zero deps, answers the port-forward question)

**On Machine A (host, behind the router):** stop the live NEX server first (it owns
1223/1224), then:

```sh
cd mh3u_server/tests
python udp_probe_listen.py 1223 1224
```

Get the public IP to aim at (also on A): `curl -4 ifconfig.me`

**On Machine B (laptop on the phone hotspot):** copy just `udp_probe_send.py` over
(it's single-file stdlib — no repo needed), then:

```sh
python udp_probe_send.py <HOST_PUBLIC_IP> 1223 1224
```

- **PASS** on a port = the router forwards UDP inbound AND lets the reply back out =
  that NEX leg is publicly reachable. The forward works; move to Tier 2.
- **FAIL** on a port = no echo came back = router still isn't delivering UDP there
  (or the listener isn't running / server still holds the port). This is the
  definitive UDP result the TCP checker couldn't give you.

## Tier 2 — full PRUDP handshake (confirms the server actually answers)

Once Tier 1 PASSes: **start the live server on A advertising its PUBLIC IP** —
`MH3U_RAW=1 MH3U_ADVERTISE=<HOST_PUBLIC_IP> python server.py` (critical: in external
mode the client follows the StationURL the auth server hands back, which is whatever
the host advertises — a LAN/Tailscale/127 advertise here will fail the external test).

Then from B (needs the repo + NintendoClients — easiest on a VPS, or a 2nd checkout)
run the wrapper, which encodes the flags + the advertise gotcha and prints which leg
broke on failure:

```sh
python tests/extkit/check_server_leg.py <HOST_PUBLIC_IP> 1223
```

(equivalent raw form: `python tests/load_sim.py --mode external --host <HOST_PUBLIC_IP>
--auth-port 1223 --clients 1 --scenario rooms --players 1`.) All phases PASS = the
real auth -> secure -> join handshake completed over the public path = the **server
leg** works end-to-end.

## Not covered here — the P2P leg

Tiers 1-2 validate the **server** is reachable; the game-to-game P2P link is a separate
layer these probes don't touch. The host-hosted topology (NAT'd/CGNAT joiner → reachable
host) **is proven live** on the bare internet; a *joiner-hosted* room between two NAT'd
players is not. The final check is always Tier 3: a real joiner entering a real room —
see [docs/PUBLIC_HOSTING.md](../../docs/PUBLIC_HOSTING.md) for the full runbook.

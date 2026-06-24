# Hosting a MH3U Revival game

You run the server; your friends point their patched Cemu at you. The server does auth +
matchmaking + presence — the hunt itself is peer-to-peer. **Beta: 4 players (one room).**

## What you need
As the host you run a small program (the server) and you also play. Four things — you
probably already have the last two:

- **Python** (free) — the server is a Python program. [Install it](https://www.python.org/downloads/),
  and on the **first installer screen tick "Add python.exe to PATH."** (Easy to miss, and
  without it the commands below won't be recognized.)
- **This server** — the files in *this repo*. The ready-to-play **bundle** you may have seen is
  what your *friends* use to join — it does **not** include the server, so to host you need the repo.
- The **patched Cemu** build (`Cemu_release.exe`, the `mh3u-revival` Cemu fork) — you play too.
- Your **own legal MH3U dump** — nothing is distributed.

> **Where do I type the commands?** In a **terminal** — Command Prompt, PowerShell, or Windows
> Terminal. You don't need a code editor or anything else. Open one and you're ready.

## 1. Get the server and run it
Download this repo, then grab the one extra library it needs (NintendoClients) and put it
right where the server looks for it. The commands use **Git** to download — if you don't
have it, [install Git](https://git-scm.com/downloads) first (or download each repo as a ZIP
from its GitHub page). In a terminal:
```bash
# 1. get the server
git clone https://github.com/Matt-Wood-23/mh3u-revival.git

# 2. get the one library it needs, in the exact spot the server expects it
git clone https://github.com/kinnay/NintendoClients.git external/NintendoClients

# 3. install the small pip deps and start it
cd mh3u-revival
pip install -r requirements.txt        # pin anynet==1.1.0 (1.2.x breaks import on 3.13)
python server.py
```
**Don't skip step 2** — it's the one thing that isn't pip-installable, and without it the
server quits right away with an `import nintendo` error. It binds `0.0.0.0:1223` (auth) +
`0.0.0.0:1224` (secure).

## 2. Tell the server your reachable IP
So your co-located host player (and remote joiners) are advertised a usable address:
```bash
# Windows
set MH3U_ADVERTISE=<your-reachable-ip> & python server.py
# Linux/macOS
MH3U_ADVERTISE=<your-reachable-ip> python server.py
```
`<your-reachable-ip>` is the **same** address your players will use (see step 3).

## 3. Make the server reachable
| Players are… | Do this | `<reachable-ip>` |
|---|---|---|
| **over an overlay (recommended)** | you + friends join a Tailscale network | your Tailscale `100.x` IP |
| on your LAN | nothing | your LAN IP (e.g. `192.168.1.50`) |

> Hosting over the bare internet by port-forwarding UDP 1223+1224 *should* work but is
> **untested so far** — and it exposes your IP and dies behind CGNAT. It's a power-user path,
> not the supported beta route. See [ARCHITECTURE.md §5](ARCHITECTURE.md#5-reachability--networking).

**Overlay (the recommended path) — using Tailscale (the proven path):**
1. Install [Tailscale](https://tailscale.com/download) and sign in (free). Only *you* organize
   the tailnet.
2. **Add each friend to your tailnet** (this is the fiddly part — read the gotcha box):
   1. Admin console → **Users → Invite external users** → send each friend the invite link.
   2. They open it, sign in with their own account, **accept** → now they're a *member*.
   3. They install Tailscale on their **gaming PC** and sign in with that **same** account.
   4. They make their **client** actually use *your* tailnet, not their own (the gotcha below).
3. Find your Tailscale IP: `tailscale ip -4` (a `100.x` address). Run the server with
   `MH3U_ADVERTISE=<that 100.x IP>`. **Confirm you can see each friend's device first** — your
   `tailscale status` should list it with a `100.x` IP (and approve it under **Machines** if your
   tailnet requires device approval). Then they confirm the tunnel: `tailscale ping <your 100.x>`
   → "pong".

> **⚠️ The #1 Tailscale gotcha — "I invited them but their device never shows up."**
> Accepting your invite makes them a *user* on your tailnet, but their **client** usually stays
> connected to **their own** tailnet (Tailscale auto-creates one per account). Their device then
> shows in *their* Tailscale popout but never in your `tailscale status`. **Fix (what worked
> live):** the friend switches to *your* tailnet in the Tailscale UI, **then logs out and back in
> on the client** to re-auth and bind the device. Alternative: hand them an **auth key**
> (Settings → Keys → *Generate auth key* — an **auth** key, **not** an *API access token*, which
> errors "unable to validate api key"; tick **Pre-approved**) and have them run
> `tailscale up --authkey=tskey-auth-… --force-reauth`.

> Tested end-to-end on Tailscale — a **4-player** hunt including a **genuinely remote friend** on
> his own PC and ISP; all P2P links established.

> **Why an overlay:** it's private (no IP exposure), needs no router config, and works
> behind CGNAT — which raw hole-punch and port-forwarding don't. See
> [ARCHITECTURE.md §5](ARCHITECTURE.md#5-reachability--networking).

## 4. Your own Cemu (you play too)
- Generate your player identity once: run `dist/make_account.py` (random unique PID), or use
  the launcher from the MH3U Online Bundle. Pin a fixed PID with `--player 1` if you like.
- Generate the dummy online-gate files: `dist/make_online_files.py "<cemu_data>"`.
- Set your Cemu's `mh3u_server.txt` to your `<reachable-ip>` (with `MH3U_ADVERTISE` set,
  `127.0.0.1` also works for the co-located host).
- **Turn online on in Cemu:** *Options → General Settings → Account* — set **Network Service =
  Nintendo** and make sure online play is enabled (the online-requirements status should be all
  green; that's what the dummy gate files above satisfy). **Restart Cemu** for it to take effect.
- **Bringing an existing save?** If you already played MH3U in another Cemu, copy your save
  folder into this Cemu's data (`mlc01\usr\save\00050000\10118300\...`) so you keep your hunter.

## 5. Play
Launch MH3U → Network Mode → enter a Gathering Hall → **Create a Room**. Friends join the
same hall and enter your room.

---

## Environment variables
| Var | Default | Purpose |
|---|---|---|
| `MH3U_ADVERTISE` | (none) | reachable IP handed to joiners; substitutes loopback for co-located peers |
| `MH3U_BIND` | `0.0.0.0` | bind address (set `127.0.0.1` to restrict to local) |
| `MH3U_HOST_FREE` | `1` | auto-free a departed guest's slot in the **host Cemu's** roster (the rejoin fix). Requires the server to run **on the same machine as the host Cemu**. Set `0` for remote-host deployments. |
| `MH3U_HOST_HINT` | `e:\cemu-src` | exe-path hint to find the host Cemu process |
| `MH3U_REAP_TIMEOUT` | `45` | seconds of silence before a ghost connection is reaped (`0` disables — use while debugging with a paused Cemu) |

> **Co-location note:** the rejoin auto-fix (`host_roster_free.py`) reaches into the host
> Cemu's RAM, so it only works when the server and the host's Cemu are on the **same
> machine** — which is the normal "I host and play" setup. If you run the server on a
> separate box, set `MH3U_HOST_FREE=0`. See [ARCHITECTURE.md §4](ARCHITECTURE.md#4-the-rejoin-problem-and-its-fix-the-hard-part).

## Troubleshooting
- **A friend's device never appears in your `tailscale status`** = their Tailscale client is on
  *their own* tailnet, not yours. They switch to your tailnet in the Tailscale UI and **log out /
  back in** on the client (or join via an auth key + `--force-reauth`). See the gotcha box in step 3.
- **Joiner shows "connected to the internet" then drops to the village** = they can't reach
  your server. Confirm they can reach your `<reachable-ip>` (overlay up? `tailscale ping`
  → "pong"?). 99% of the time it's the overlay, not the build.
- **Server sees zero packets from a LAN joiner** = many home/Wi-Fi networks block PC↔PC UDP
  (client/AP isolation). Don't fight it — use an overlay, which tunnels past it.
- **`mh3u_server.txt` must be ≤15 chars** (a Wii U field limit) — use an **IP**, not a domain.

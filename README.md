# MH3U Revival — self-hosted online for Monster Hunter 3 Ultimate (Wii U)

> **Status: public beta.** Self-host online multiplayer for MH3U on
> [Cemu](https://cemu.info), with **no console dump**. One person runs the server,
> their friends join — hunts are peer-to-peer; the server only does matchmaking and
> presence. Built on [Kinnay's NintendoClients](https://github.com/kinnay/NintendoClients).

Monster Hunter 3 Ultimate's official Wii U servers are gone, and many of us have waited quite
a long time for someone to bring it back! This brings the online gathering halls and 
co-op hunts back, **privately, for you and your friends** — not as a
public replacement service. I don't have the resources to host for everyone unfortunately,
Pretendo is already working on this too supposedly.
You bring your own legal game dump; nothing from Nintendo is distributed.

---

## ⚠️ Legal / disclaimer

This is an unofficial, **non-commercial** fan project, not affiliated with or endorsed by
Nintendo or Capcom. Monster Hunter and Monster Hunter 3 Ultimate are trademarks of their
respective owners.

- It ships **no Nintendo or Capcom code, keys, certificates, or game data.** The online
  "gate" files it generates are right-sized dummies (zeros + 4-byte empty stubs) that only
  satisfy Cemu's file-existence check.
- **Every player supplies their own legal copy/dump** of the game. None is included or
  distributed.
- It reimplements an interoperable game server from black-box reverse engineering of
  publicly-shipped client behavior. The credentials it uses are values baked into the
  retail game, not secrets.

If you represent a rights-holder with a concern, please open an issue.

---

## What works today (beta)

- ✅ Dumpless auth → gathering halls → room create/browse/join → **P2P hunts**.
- ✅ Four players connected cross-machine over an overlay VPN (Tailscale), hole-punched.
- ✅ **Public-internet hosting (no VPN)** — verified live: a joiner on a cellular network
  (behind CGNAT) authenticated and P2P'd into a hosted room via the host's bare public IP.
  Host-side setup guide: [docs/PUBLIC_HOSTING.md](docs/PUBLIC_HOSTING.md).
- 🧪 **Linux / Steam Deck (experimental):** a community-built Linux bundle
  (`MH3U_Online_Linux.zip` on Releases, contributed by **jM5557**) — the patched Cemu as an
  AppImage + a bash launcher. See [docs/PLAYING.md](docs/PLAYING.md#linux--steam-deck-experimental).
- ✅ Self-healing room churn: clean leave, **hard-drop (Cemu killed) rejoin**, and
  ghost-population cleanup all recover automatically (see
  [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §4).
- ✅ Per-player random unique identity — no central accounts, no sign-up.
- ✅ **Zero-setup joining:** a ready-to-run bundle with online **pre-enabled** — bring your
  own dump, double-click the launcher, play. No Cemu account/settings fiddling, no Python.

**Game version:** the **US**, **EU/PAL** and **JP** versions are all tested end-to-end —
including verified **cross-region rooms** (EU + US, and JP + US, hunting together). An
EUR-build crash on entering Network Mode is fixed since v0.1.4, and a **JP boot hang** (an
upstream Cemu regression) is fixed in the bundle's Cemu since **v0.1.6**. The JP version
(*MH3G HD Ver.*) needs a couple of extra system files on any Cemu — see
[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md#jp-version-mh3g-hd-ver--extra-setup).

**Still being tested (don't expect polish yet):** *joiner-hosted* rooms
between two NAT'd players on the bare internet (host-hosted rooms are the verified path); the
Linux bundle beyond LAN play. This is a **beta** — it's scoped to **4 players (one room) per
server** on purpose, because that's the configuration that's been hardened.

---

## Reporting bugs

This is a beta — expect rough edges and bugs that haven't surfaced yet. If you hit one,
please report it on the
**[issue tracker](https://github.com/Matt-Wood-23/mh3u-revival/issues)**. What helps most:
what you were doing, whether you were the host or a joiner, your reachability method
(Tailscale / LAN), and — if you're the host — the relevant server log
lines.

---

## Get started

- **Hosting a game?** → [docs/HOSTING.md](docs/HOSTING.md)
- **Joining a friend's game?** → [docs/PLAYING.md](docs/PLAYING.md)
- **Something not working?** → [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- **How it works / design decisions** → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

> **Tried an earlier build and got stuck on the online checkmark** — greyed-out *Network Service*,
> or *"not linked to a NNID or PNID"*? **That's fixed.** Grab the current bundle and just run
> `PLAY MH3U ONLINE.bat`; the launcher now sets up (or repairs) your online identity on launch, so
> the green checkmark appears on its own — no Cemu account settings to touch.

**Joining** is the easy path: grab the **MH3U Online Bundle** from the
[Releases](https://github.com/Matt-Wood-23/mh3u-revival/releases) page — a ready-to-run patched
Cemu with online pre-enabled. Add your own dump, double-click `PLAY MH3U ONLINE.bat`, enter the
host's IP, play. See [docs/PLAYING.md](docs/PLAYING.md). **On Linux or a Steam Deck?** Grab the
experimental **`MH3U_Online_Linux.zip`** instead — same flow with a bash launcher
([docs/PLAYING.md § Linux](docs/PLAYING.md#linux--steam-deck-experimental)).

**Hosting — no Python (easiest):** grab the **MH3U Host Add-on** (`server.exe` + `HOST_MH3U.bat`)
from [Releases](https://github.com/Matt-Wood-23/mh3u-revival/releases) and drop both files next to
the bundle you play with. Double-click `HOST_MH3U.bat` — it auto-detects your Tailscale IP, prints
the address friends type in, and runs the self-contained server (nothing to install). Then play
normally and enter `127.0.0.1` as the host IP. Full details in [docs/HOSTING.md](docs/HOSTING.md).

**Hosting — from source (advanced):** if you'd rather run or modify the server in Python:

```bash
git clone https://github.com/Matt-Wood-23/mh3u-revival.git
git clone --branch mh3u-revival https://github.com/Matt-Wood-23/NintendoClients.git external/NintendoClients   # patched fork, not on pip
cd mh3u-revival
pip install -r requirements.txt          # pin anynet==1.1.0
MH3U_ADVERTISE=<your-reachable-ip> python server.py
```

Binds UDP `1223` (auth) + `1224` (secure). Players point their patched Cemu at
`<your-reachable-ip>` and join your room.

---

## Scope & non-goals

- **Decentralized, not centralized.** Each host runs their own server for their own group.
  There is intentionally **no** global public matchmaking service to operate (that would be
  a hosting/cost/moderation/legal commitment this project does not take on).
- **Private/invite, not public.** Reachability is via a private overlay (Tailscale), or —
  for hosts who opt in — their own public IP ([docs/PUBLIC_HOSTING.md](docs/PUBLIC_HOSTING.md)).
  Either way it's invite-only, not "post your IP for the world."
- **Beta, 4 players/room.** Larger-capacity / community-hub hosting is under investigation,
  not shipped.
- **No resources to host for everyone** — and that's by design; see decentralized, above.

---

## Roadmap

Beta is deliberately small (Tailscale, 4 players, one room — the hardened config). Things
being explored for later — **not promised, and the order isn't fixed**:

- **One-click overlay.** A join-code launcher that sets Tailscale up for the player
  automatically, so it's "install → paste code → play" with no manual tailnet fiddling.
- **Relay fallback.** An optional host-run relay for player pairs that can't hole-punch
  (symmetric NAT / CGNAT), for when even an overlay isn't enough.
- **First-class Linux support.** The experimental community bundle graduating to a maintained
  release artifact — ideally CI-built AppImages from the Cemu fork instead of hand-built ones.
- **Larger lobbies / community hubs.** More than 4 players, and/or a shared "hub" server a
  group can point an LFG at — needs the multi-room churn hardened first.
- **Mod menu / cheats in online sessions (experimental, untested).** The reverse-engineering
  behind this project also produced a whole MH3U cheat suite — a full Python **mod menu** plus
  all kinds of trainers (player / monster / item). I haven't tested any of it **while online**
  yet, but it could make for some fun multiplayer experiences. I'll get around to trying it
  online, and release it as a companion if there's interest — say so on the issue tracker.

Have a request? Open an issue.

---

## License

Server code: **GNU AGPL-3.0** (see [LICENSE](LICENSE)). The network-copyleft clause means
anyone who runs a *modified* version as a server must publish their source — this keeps the
revival open and prevents closed or commercial forks.

The patched Cemu client is a fork of [Cemu](https://github.com/cemu-project/Cemu) and
remains under its own **MPL-2.0** license; it is distributed separately. Full source for the
fork — so anyone can audit the exact changes or rebuild `Cemu_release.exe` themselves —
is the **[mh3u-revival branch of the Cemu fork](https://github.com/Matt-Wood-23/Cemu/tree/mh3u-revival)**
(it's only a couple of commits ahead of upstream; GitHub shows the precise diff).

> The provided build is unsigned, so Windows Defender / SmartScreen flags it as
> "unrecognized" — normal for a custom emulator build. Players who'd rather not trust the
> binary can build it from the fork above.

---

## Credits

- [NintendoClients](https://github.com/kinnay/NintendoClients) (Kinnay) — the NEX/PRUDP/RMC
  library this server is built on. MH3U needs a small patch (legacy PRUDP v1 signature),
  carried in a fork:
  [Matt-Wood-23/NintendoClients @ mh3u-revival](https://github.com/Matt-Wood-23/NintendoClients/tree/mh3u-revival)
  (MIT, same as upstream).
- The [Cemu](https://cemu.info) project — the emulator the patched client forks.
- **jM5557** — the Linux / SteamOS / Steam Deck port: the Cemu-fork AppImage build (and its
  reproducible build recipe) and the `SETUP-ONLINE.sh` launcher.
- [cemu-re-mcp](https://github.com/Matt-Wood-23/cemu-re-mcp) — the GDB-stub / pymem
  reverse-engineering bridge used to decode MH3U's online protocol and memory layout.
- [ghidra-mcp](https://github.com/bethington/ghidra-mcp) (an extended fork of
  [LaurieWired's GhidraMCP](https://github.com/LaurieWired/GhidraMCP)) — the Ghidra MCP
  server used to decompile and reverse-engineer the MH3U binary.
- [Claude Code](https://claude.com/claude-code) (Anthropic — Claude Opus 4.8 & Fable 5) —
  AI pair-programmer across the protocol RE, server implementation, and docs.
- The MH3U / Wii U reverse-engineering community.

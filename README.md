# MH3U Revival — self-hosted online for Monster Hunter 3 Ultimate (Wii U)

> **Status: public beta.** Self-host online multiplayer for MH3U — on
> [Cemu](https://cemu.info) with **no console dump**, or on a **real Wii U** running
> [Aroma](https://wiiu.hacks.guide/). Emulator and console play together in the same room.
> One person runs the server, their friends join — hunts are peer-to-peer; the server only
> does matchmaking and presence. Built on
> [Kinnay's NintendoClients](https://github.com/kinnay/NintendoClients).

Monster Hunter 3 Ultimate's official Wii U servers are gone, and many of us have waited quite
a long time for someone to bring it back! This brings the online gathering halls and 
co-op hunts back, **privately, for you and your friends** — not as a
public replacement service. I don't have the resources to host for everyone unfortunately,
Pretendo is already working on this too supposedly.
You bring your own legal game dump; nothing from Nintendo is distributed.

> 💬 **Community & LFG — [discord.gg/HTEWJDYgzJ](https://discord.gg/HTEWJDYgzJ)**
> The semi-official Discord for the revival: find people to hunt with, look for a host / post
> LFG, get setup help, and hear about updates. Come say hi.

---

## Get started

- **Hosting a game?** → [docs/HOSTING.md](docs/HOSTING.md)
- **Joining a friend's game (Cemu)?** → [docs/PLAYING.md](docs/PLAYING.md)
- **Playing on a real Wii U?** → [docs/WIIU_CONSOLE.md](docs/WIIU_CONSOLE.md)
- **Something not working?** → [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- **How it works / design decisions** → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

**On Cemu**, everything runs from one app. Grab the **MH3U Online Bundle** from
[Releases](https://github.com/Matt-Wood-23/mh3u-revival/releases), add your own dump, and
double-click **`MH3U_Online.exe`** — **Join** to play on someone's server, **Host** to run one
for your friends. The server is built in; there's no separate Host Add-on. On Linux or a Steam
Deck, take the experimental `MH3U_Online_Linux.zip` instead.

**On a real Wii U**, it's one plugin file and an IP you type on the GamePad —
[docs/WIIU_CONSOLE.md](docs/WIIU_CONSOLE.md).

Prefer to run the server from source in Python, or modify it? That path is in
[docs/HOSTING.md](docs/HOSTING.md#1-get-the-server-and-run-it).

---

## What works today (beta)

- ✅ Dumpless auth → gathering halls → room create/browse/join → **P2P hunts**.
- ✅ Four players cross-machine over an overlay VPN (**Tailscale or Radmin**), hole-punched.
  The server re-stamps each hunt's P2P endpoint to the plane it reached you on, which is what
  makes **Radmin** groups connect.
- ✅ **Public-internet hosting (no VPN)** — including joiners behind CGNAT.
  [docs/PUBLIC_HOSTING.md](docs/PUBLIC_HOSTING.md).
- 🧪 **Linux / Steam Deck (experimental)** — a community bundle from **jM5557**
  (`MH3U_Online_Linux.zip`). [docs/PLAYING.md](docs/PLAYING.md#linux--steam-deck-experimental).
- 🧪 **Android (experimental, join only)** — a community Cemu port by **jM5557** with the
  revival patches carried over. It joins a host's server by IP but can't host one. Released
  separately, not in this project's bundle:
  [jM5557/Cemu-Android-MH3U-Revival](https://github.com/jM5557/Cemu-Android-MH3U-Revival/releases).
  [docs/PLAYING.md](docs/PLAYING.md#android-experimental).
- 🧪 **Cemu Enhanced (optional, experimental)** — the same patched Cemu plus save states, pause,
  cheats, screen layouts and a controller-first Game Mode. Swap it into either bundle; save
  states and pause are blocked while you're online.
  [Release](https://github.com/Matt-Wood-23/Cemu/releases/tag/enhanced-v0.1.1) ·
  [docs/PLAYING.md](docs/PLAYING.md#cemu-enhanced-optional-experimental).
- ✅ Self-healing room churn — clean leave, hard-drop rejoin and ghost cleanup all recover
  on their own ([docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §4).
- 🆕 **Real Wii U consoles** (v0.2.0-beta) — an Aroma plugin points the console at your
  server, so console and Cemu players share rooms. Proven over the public internet with two
  consoles and a PC. [docs/WIIU_CONSOLE.md](docs/WIIU_CONSOLE.md).
- 🆕 **Optional UDP relay** (v0.2.0-beta) — routes hunt traffic through the server, so
  joiners need no port forwarding and players never see each other's IPs. Costs host
  bandwidth, and has a [known limit at 3+ players](docs/GUEST_PAIR_PROBLEM.md).
  [docs/HOSTING.md](docs/HOSTING.md#optional-the-udp-relay).
- ✅ Per-player random unique identity — no central accounts, no sign-up.
- ✅ **Zero-setup joining** — the bundle ships with online pre-enabled: add your dump,
  double-click, play. No Cemu settings to fiddle with, no Python.

**Game version:** the **US**, **EU/PAL** and **JP** versions are all tested end-to-end —
including verified **cross-region rooms** (EU + US, and JP + US, hunting together). An
EUR-build crash on entering Network Mode is fixed since v0.1.4, and a **JP boot hang** (an
upstream Cemu regression) is fixed in the bundle's Cemu since **v0.1.6**. The JP version
(*MH3G HD Ver.*) needs a couple of extra system files on any Cemu — see
[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md#jp-version-mh3g-hd-ver--extra-setup).

---

## Reporting bugs

This is a beta — expect rough edges and bugs that haven't surfaced yet. If you hit one,
please report it on the
**[issue tracker](https://github.com/Matt-Wood-23/mh3u-revival/issues)**. What helps most:
what you were doing, whether you were the host or a joiner, your reachability method
(Tailscale / Radmin / LAN / public IP), and — if you're the host — the relevant server log
lines.

For quicker back-and-forth — or just to find people to hunt with — there's a community
**[Discord](https://discord.gg/HTEWJDYgzJ)** too. Use the issue tracker for anything that needs
a fix, though, so it doesn't get lost in chat.

---

## Scope & what's next

**What this is.** Each host runs their own server for their own group. There is
intentionally **no** global public matchmaking service — that would be a
hosting/cost/moderation/legal commitment this project doesn't take on, and it's why I can't
host for everyone. Reachability is a private overlay (Tailscale/Radmin) or, for hosts who opt
in, their own public IP ([docs/PUBLIC_HOSTING.md](docs/PUBLIC_HOSTING.md)) — invite-only
either way, not "post your IP for the world."

**Sizes.** A hunt is **4 players** — the game's own P2P limit, not a setting worth changing.
A **gathering hall** holds 16 by default (`MH3U_HALL_MAX`) with multiple hunt rooms per
server; that's the part still being proven at scale.

**Rough edges right now.** Rooms hosted by a *joiner* rather than the server operator, the
Linux bundle beyond LAN play, halls with many live hunters in them, and console support
generally — all work, none are polished.

**Being explored** — not promised, and the order isn't fixed:

- **One-click overlay.** A join-code launcher that sets Tailscale up automatically, so it's
  "install → paste code → play" with no manual tailnet fiddling.
- **Relay coverage for every link.** The relay covers host↔guest hunt links. Links between two
  non-host players in a 3+ player room stay direct, which is why the worst-connected player
  should create the room. Closing that gap needs client-side work and may not be reachable —
  analysis in [docs/GUEST_PAIR_PROBLEM.md](docs/GUEST_PAIR_PROBLEM.md).
- **First-class Linux support.** The community bundle graduating to a maintained release
  artifact — ideally CI-built AppImages from the Cemu fork rather than hand-built ones.
- **A shared "hub" server** a group can point an LFG at, on the back of the larger halls.

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

## Credits

- [NintendoClients](https://github.com/kinnay/NintendoClients) (Kinnay) — the NEX/PRUDP/RMC
  library this server is built on. MH3U needs a small patch (legacy PRUDP v1 signature),
  carried in a fork:
  [Matt-Wood-23/NintendoClients @ mh3u-revival](https://github.com/Matt-Wood-23/NintendoClients/tree/mh3u-revival)
  (MIT, same as upstream).
- The [Cemu](https://cemu.info) project — the emulator the patched client forks.
- **jM5557** — the Linux / SteamOS / Steam Deck port: the Cemu-fork AppImage build (and its
  reproducible build recipe) and the `SETUP-ONLINE.sh` launcher. Also the Android port
  ([Cemu-Android-MH3U-Revival](https://github.com/jM5557/Cemu-Android-MH3U-Revival)) and fixes
  to custom texture loading.
- **[Dogchydios](https://github.com/dogchydios)** — the UDP relay. `relay.py`, the
  `MH3U_RELAY=auto` learning policy in `relay_policy.py`, and the matchmaking hooks that
  make it work originated in their fork
  ([mh3u-revival-relay](https://github.com/dogchydios/mh3u-revival-relay)) and are carried
  here with their commits intact. It's what lets players behind CGNAT hunt together without
  port forwarding.
- [cemu-re-mcp](https://github.com/Matt-Wood-23/cemu-re-mcp) — the GDB-stub / pymem
  reverse-engineering bridge used to decode MH3U's online protocol and memory layout.
- [ghidra-mcp](https://github.com/bethington/ghidra-mcp) (an extended fork of
  [LaurieWired's GhidraMCP](https://github.com/LaurieWired/GhidraMCP)) — the Ghidra MCP
  server used to decompile and reverse-engineer the MH3U binary.
- [Claude Code](https://claude.com/claude-code) (Anthropic — Claude Opus 4.8 & Fable 5) —
  AI pair-programmer across the protocol RE, server implementation, and docs.
- The MH3U / Wii U reverse-engineering community.

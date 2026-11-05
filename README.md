# MH3U Revival — self-hosted online for Monster Hunter 3 Ultimate (Wii U)

> **Status: public beta.** Play on [Cemu](https://cemu.info) or a real Wii U running
> [Aroma](https://wiiu.hacks.guide/); emulator and console players can share a room.

The official MH3U servers are gone. This brings back the gathering halls and co-op hunts
for **you and your friends**: one person runs a server, everyone else joins it. It isn't a
public replacement service, and I can't host for everyone (Pretendo is also working on
MH3U). You bring your own legal game dump; nothing from Nintendo is distributed.

> 💬 **Community & LFG — [discord.gg/HTEWJDYgzJ](https://discord.gg/HTEWJDYgzJ)**
> Find people to hunt with or a host to join, get setup help, and hear about updates.

---

## Get started

- **Hosting a game?** → [docs/HOSTING.md](docs/HOSTING.md)
- **Joining a friend's game on Cemu?** → [docs/PLAYING.md](docs/PLAYING.md)
- **Playing on a real Wii U?** → [docs/WIIU_CONSOLE.md](docs/WIIU_CONSOLE.md)
- **Something not working?** → [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- **Want to edit quests or make your own?** → [MH3U Quest Studio](https://github.com/Matt-Wood-23/mh3u-quest-studio)

**On Cemu (Windows):** download `MH3U_Online_Bundle.zip` from the
[latest release](https://github.com/Matt-Wood-23/mh3u-revival/releases/latest), add your own
dump, and open **`MH3U_Online.exe`**. **Join** plays on someone's server; **Host** runs one
for your friends. No Cemu settings to change, and the app offers updates when a new version
is out.

**On a real Wii U:** one plugin file, and the server's IP typed in on the GamePad —
[docs/WIIU_CONSOLE.md](docs/WIIU_CONSOLE.md).

**On Linux / Steam Deck** (experimental), use jM5557's `MH3U_Online_Linux.zip` —
[docs/PLAYING.md](docs/PLAYING.md#linux--steam-deck-experimental). **On Android**
(experimental, join only), use jM5557's
[Cemu-Android-MH3U-Revival](https://github.com/jM5557/Cemu-Android-MH3U-Revival/releases) —
[docs/PLAYING.md](docs/PLAYING.md#android-experimental).

Want to run the server from source, or change it? See
[docs/HOSTING.md](docs/HOSTING.md#1-get-the-server-and-run-it). How it all works is in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## What works

- Gathering halls, creating and joining rooms, and full **4-player hunts**.
- **Real Wii U consoles** in the same rooms as Cemu players, proven over the public internet.
- **US, EU/PAL and JP** versions, including cross-region rooms. The JP version
  (*MH3G HD Ver.*) needs a couple of extra system files —
  [see here](docs/TROUBLESHOOTING.md#jp-version-mh3g-hd-ver--extra-setup).
- **Connecting:** a VPN (Tailscale or Radmin), or the host's public IP with port forwarding
  ([docs/PUBLIC_HOSTING.md](docs/PUBLIC_HOSTING.md)), including players behind CGNAT.
- **Optional relay:** hunt traffic goes through the server, so joiners need no port
  forwarding and players never see each other's IPs. It uses the host's upload, and has a
  [known limit at 3+ players](docs/GUEST_PAIR_PROBLEM.md).
  [docs/HOSTING.md](docs/HOSTING.md#optional-the-udp-relay)
- No accounts or sign-up: each player gets a random identity automatically.
- Leaving, crashing and rejoining don't leave halls or rooms stuck for everyone else.

---

## Mods & tools

Optional extras that work alongside online play.

- **60 FPS fix** (Cemu graphic pack, in this repo): caps MH3U at 30, 45 or 60 fps using the
  game's own frame limiter, and fixes what runs at the wrong speed above 30: camera turning,
  lance charge stamina, buff icons, the hammer golf swing and Alatreon's running turn. US and
  EU tested, JP not yet. Each player chooses for themselves.
  [docs/FPS_FIX.md](docs/FPS_FIX.md).
- **[MH3U Quest Studio](https://github.com/Matt-Wood-23/mh3u-quest-studio)**: a quest editor
  for monsters, difficulty, rewards, text and more, which can also create new event quests.
  Online, **event quests come from the host**, so only the host needs them. **Base-game quest
  edits must be installed by everyone in the room**, since each game reads its own copy.
- **[Loc Lac City](https://github.com/Matt-Wood-23/mh3u-loc-lac)**: the city from Monster
  Hunter Tri, in place of Port Tanzia, with its shops, tavern, music, day and night, and the
  Jhen Mohran sandstorm. A Cemu graphic pack for the US or EU game with the v1.3 update; your
  game files are never changed. Cemu players with and without the pack can share a room
  (in town you'll just see each other in odd spots). **Not for rooms with a real Wii U:** a
  console can't run the pack, and it may crash a console in the same room.

---

## Reporting bugs

It's a beta, so expect bugs. Please report them on the
**[issue tracker](https://github.com/Matt-Wood-23/mh3u-revival/issues)** with what you were
doing, whether you were the host or a joiner, how you connect (Tailscale / Radmin / LAN /
public IP), and, if you host, the relevant server log lines.

The **[Discord](https://discord.gg/HTEWJDYgzJ)** is good for quick questions, but put anything
that needs a fix in the tracker so it doesn't get lost in chat.

---

## Scope & what's next

**What this is.** Each host runs their own server for their own group. There is
intentionally **no** global public matchmaking service: that would be a hosting, cost,
moderation and legal commitment this project doesn't take on. Groups connect over a private
VPN (Tailscale/Radmin) or the host's own public IP
([docs/PUBLIC_HOSTING.md](docs/PUBLIC_HOSTING.md)), invite-only either way.

**Sizes.** A hunt is **4 players**, the game's own limit. A **gathering hall** holds 16 by
default (`MH3U_HALL_MAX`), with multiple hunt rooms per server; big halls are still being
tested at scale.

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
  reproducible build recipe) and the Linux launcher. Also the Android port
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

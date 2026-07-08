# Troubleshooting & FAQ

Fixes for the most-reported problems, all regions and platforms. Setup steps live in
[PLAYING.md](PLAYING.md) (joining) and [HOSTING.md](HOSTING.md) /
[PUBLIC_HOSTING.md](PUBLIC_HOSTING.md) (hosting) — this page is only for when something
goes wrong.

---

## "Everything works — halls, chat, seeing each other — but the moment we join a Room, it disconnects"

This is the single most-reported problem, and it is almost never the server. Here's why:
the **Gathering Hall lives on the server**, but a **Room is a direct peer-to-peer
connection between the players' PCs**. Joining a room is the first moment the game needs
player↔player UDP traffic, so a setup where the hall works fine but rooms instantly
disconnect means exactly one thing: **the direct connection between the two PCs is being
blocked** — usually by Windows Firewall on one of them.

**Fix — do this on BOTH PCs** (the room creator's PC matters most):

1. Press `Win+R`, run `wf.msc` → **Inbound Rules** → sort by name and look for **Cemu**
   entries. Any with a **red block icon** — delete them. (These get created when someone
   clicks *Cancel* on Windows' "allow network access" popup, and a Block rule silently
   **overrides** any Allow rule.)
2. Then make sure Cemu is *allowed*: Windows Security → *Firewall & network protection* →
   *Allow an app through firewall* → find your `Cemu_release.exe` and tick **both Private
   and Public**. Public matters: VPN adapters (RadminVPN especially) are often classified
   as Public networks, so a Private-only rule does nothing there.
3. When Windows pops the "allow access" dialog on a fresh PC, tick **both** checkboxes.

Things that are **not** the problem when halls work but rooms don't:

- **UPnP / your router** — if you're on a VPN (Tailscale/Radmin), the VPN bypasses your
  router entirely; router settings are irrelevant.
- **The game region** — US, EU and JP have all been verified in cross-region rooms.

**Still failing?** The host can confirm the diagnosis: search the server console/log for
`report_nat_traversal_result`. `result=True` means the connection punched through; if
that line never appears (or says `False`), the direct connection is being blocked —
firewall, or the two PCs genuinely can't reach each other (on Tailscale, run
`tailscale ping <the other player's 100.x IP>` in both directions first; on Radmin, ping
their `26.x` IP).

---

## Two specific players can't share a Room — every other combination works

The telltale version of the room disconnect: A+B+C works, A+B+D works, but any room
containing **both C and D** kicks whoever joined last — no matter who hosts, no matter
the room. The server log looks clean because it *is* clean; the problem is between C's
and D's PCs.

**Why this happens:** a Room is not "everyone connects to the host" — it's a **full
mesh**. Every player holds a direct UDP connection to *every other player*, and a
joiner must connect to **all** current members before the join completes. So one broken
player↔player link stays invisible until those two specific players are in the same
room — then the second one in gets "disconnected," while both play fine with everyone
else.

**Confirm it** (takes two minutes):

1. Have just the two affected players try a room **alone** (either one hosts). If it
   fails with only them in it, the pair link is the problem — the "4th player" framing
   was a coincidence.
2. The host can see the failing edge: search the server console for
   `report_nat_traversal_result` right after the failed join. A `result=False` (or a
   `request_probe_initiation_ext` with no `True` afterwards) from one of the pair's
   `pid=` values is the smoking gun.

**Fixes, in order of likelihood:**

1. **Both** affected players redo the firewall steps from the section above. A Block
   rule on either side breaks exactly one direction of one pair — which is why the rest
   of the group is unaffected.
2. **Check what internet each of the two is on.** Cellular/5G home internet (T-Mobile,
   Verizon), Starlink, phone hotspots, and campus/apartment shared WiFi all use
   **carrier-grade NAT (CGNAT)** — and two players who are *both* behind CGNAT (or other
   strict NAT) genuinely cannot open a direct connection to each other. No firewall or
   Cemu setting changes this. Quick check: if your router's WAN address starts with
   `100.64`–`100.127`, or differs from what [whatismyip.com](https://www.whatismyip.com)
   shows, you're behind CGNAT.
3. **Already on Tailscale/Radmin and still hitting this?** Being *on* the VPN is not
   enough — the game has to **connect through it**. The server advertises each player
   to their peers at whatever address it sees them connect *from*. A player whose
   `portable/mh3u_server.txt` contains the host's **public** IP is advertised at their
   raw internet address (their CGNAT), and their room connections skip the VPN
   entirely — even with the VPN installed and running. **Check every player's
   `mh3u_server.txt`: it must be the host's VPN IP (Tailscale `100.x.y.z`, or Radmin
   `26.x.y.z`), the same line for everyone.** One player with the public IP in that file
   reproduces exactly the "these two specific players can't share a room" symptom.

   **Radmin — the subtle one (now fixed server-side):** even with the correct VPN IP in
   *every* `mh3u_server.txt`, older servers still failed for **Radmin** users specifically.
   Cemu reports its raw *public* IP for the peer-to-peer probe even on Radmin (Radmin doesn't
   sit on the default route the way Tailscale does), so the hole-punch leaked onto the open
   internet and failed — the exact "see the room, can't join it" symptom, even with everything
   else correct. **Recent server builds auto-correct this:** the server re-stamps each P2P
   probe to the same VPN plane you reached it on, so Radmin groups connect. If a Radmin player
   still can't join, **the host should update their server.**
4. **If it's CGNAT and there's no VPN yet**, the VPN path is the fix: the whole group
   (server included) on the same Tailscale/Radmin network — see [PLAYING.md](PLAYING.md).
   The VPN carries the player↔player traffic, so NAT stops mattering. Failing that, the
   two simply can't share a room until one of them is on a different network — a
   server-side relay that would remove this limitation entirely is being investigated.

---

## JP version (MH3G HD Ver.) — extra setup

The JP release is a different game packaging (title ID `0005000010104D00` — *not*
`1014F100` as some older docs said) and needs **extra system files** that the US/EU
versions don't, on **any** Cemu build:

1. **Sound libraries:** real `snd_user.rpl` and `snduser2.rpl` in the bundle's
   `portable/cafeLibs/` folder (create the folder if missing). The JP game uses sound
   features Cemu doesn't emulate built-in; without these it hangs at boot.
2. **Japanese system files (fonts etc.):** use
   [CemuMegaDownloader](https://github.com/Xpl0itU/CemuMegaDownloader) to fetch the JPN
   system titles, then merge its `mlc01` output into the bundle's `portable/mlc01`.
   Without them the game crashes at the name-entry keyboard.

As with the game dump itself, these are Nintendo files — the bundle can't include them;
you bring your own.

**Known issues:**

- **Black screen at boot** (log ends right after an `IOSU_ACT:` line): fixed in the
  bundle's Cemu as of **v0.1.6** — grab the current bundle. On an older bundle (or stock
  Cemu 2.7+, [upstream bug](https://github.com/cemu-project/Cemu/issues/1977)), the
  workaround is: copy `swkbd.rpl` from the JP game's own `code/` folder into
  `portable/cafeLibs/`. Copy only that file — leave `erreula.rpl` alone.
- **The keyboard doesn't appear when naming your hunter:** it's on the **GamePad screen**.
  The JP game ships the real Wii U keyboard, which renders on the GamePad like real
  hardware (the US/EU versions use Cemu's built-in keyboard on the TV instead). In Cemu,
  **hold Tab** to peek at the GamePad screen or **Ctrl+Tab** to switch to it; mouse
  clicks act as touch.

---

## "Failed to retrieve OAuth token" / "Invalid CA certificate"

The game is trying to reach Nintendo instead of the host's server. One of:

- You're running **stock Cemu**, not the bundle's `Cemu_release.exe` — only the patched
  build redirects the connection.
- Your bundle predates **v0.1.4** and you're on the **EU** game — older builds only
  redirected the US title. Re-download the current bundle.
- `portable/mh3u_server.txt` is missing or has the wrong host IP — it's one line, just
  the IP; edit and relaunch.

---

## Game crashes the moment you enter Network Mode

A save whose region doesn't match the game (e.g. an EU/Spanish save on a US game). The
save's `system` + `phraseX` files carry the region; mixing them crashes online. Use a
save made on your game's own region, or start a fresh hunter.

(If you're on the **EU game with an EU save** and still crash: that was a real EUR-build
bug, fixed since v0.1.4 — re-download the bundle and make sure the host's server is
current.)

---

## Chat: one shout works, then chat goes silent until relog

The host is running a **pre-v0.1.5 server**. The game waits for a reply to each shout
before letting you send another, and older servers never replied. Host updates their
bundle (or `git pull`), done.

---

## Can I put a tunnel/proxy (playit.gg, ngrok, …) in `mh3u_server.txt`?

`mh3u_server.txt` does accept `host:port`, but tunnels **don't work end-to-end**: the
server hands clients a ticket pointing at its real address/port, so a tunnel's remapped
port breaks the second connection. Hosts should expose their real IP (VPN or public —
see [PUBLIC_HOSTING.md](PUBLIC_HOSTING.md)). Note that hunts are **peer-to-peer**, so
players' IPs are visible to each other during a hunt regardless of how the server is
reached — a tunnel in front of the server wouldn't change that.

---

## What to include in a bug report

Report on the [issue tracker](https://github.com/Matt-Wood-23/mh3u-revival/issues). What
helps most:

- What you were doing, and whether you were the **host or a joiner**.
- Game **region** (US / EU / JP) and how you connect (Tailscale / Radmin / LAN / public IP).
- **Joiner:** the bundle's `portable/log.txt` (overwritten each launch — grab it right
  after the failure).
- **Host:** the server console output around the failure — especially any lines
  containing `probe`, `report_nat_traversal_result`, `Connection was closed`, or `LOGOUT`.

"It didn't work" with a log beats a paragraph without one, every time.

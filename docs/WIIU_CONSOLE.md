# Playing on a real Wii U

You can join a MH3U Revival server from an actual Wii U — no emulator, no game dump. You
need a console running [Aroma](https://wiiu.hacks.guide/) and one plugin file.

> **Experimental.** Console support is new in v0.2.0-beta. It works — two real consoles and
> a PC have hunted together over the internet — but expect rough edges, and read the
> "who creates the room" section below, because it will bite you otherwise.

---

## Read this first: the host needs a public IP

Most of this project's docs tell you to put everyone on **Tailscale or Radmin**. **A Wii U
cannot do that** — there is no VPN client for the console, so it can only reach a server at
a plain internet address.

So if anyone is playing on a real console, the person running the server has to be
reachable on their **public IP**, which means port-forwarding. See
[PUBLIC_HOSTING.md](PUBLIC_HOSTING.md).

This affects the **server operator only**. Other players — including other console
players — do not need to forward anything.

---

## What you need

- A Wii U with **Aroma** installed ([setup guide](https://wiiu.hacks.guide/))
- Your own copy of **Monster Hunter 3 Ultimate** (US, EU or JP all work)
- The console signed in to an **NNID** — the game reads its player ID from the account.
  It does not need to be online or valid any more; the account just has to exist
- `mh3u_revival.wps` from the [Releases](https://github.com/Matt-Wood-23/mh3u-revival/releases) page
- The server's **IP address**, from whoever is hosting

---

## Setup

1. **Copy the plugin.** Put `mh3u_revival.wps` in
   `sd:/wiiu/environments/aroma/plugins/` on your SD card.

2. **Boot Aroma.** At the Wii U menu you should see a notification:

   > `MH3U Revival v0.4.0 loaded - no server address set yet (L + DPAD-Down + Minus)`

   If you see *nothing at all*, the plugin is not loading — jump to Troubleshooting.

3. **Set the server address.** Hold **L + DPAD-Down + Minus** on the GamePad to open
   Aroma's plugin config menu, then pick **MH3U Revival**.

   | Row | What to do |
   |---|---|
   | **Server IP address** | **A** to edit, **left/right** between the four numbers, **up/down** to change one, **A** to confirm |
   | **Server port** | Leave at **1223** unless your host says otherwise |

   Press **B** to close. Everything below those two rows is read-only status.

   > The `In use:` row only refreshes when you **reopen** the menu — that is normal. Close
   > it and open it again to confirm your address took.

4. **Launch MH3U** and go to **Network Mode**. You should see
   `NEX token redirected -> <the IP you set>`, and the host's server should log you
   connecting at the same moment.

That's it. The address is saved on the console and survives a reboot, so steps 1–3 are
one-time.

---

## Who creates the room matters

**If your group has three or more players, the person with the most restrictive internet
connection should be the one who CREATES the room.** Everyone else joins it.

Get this wrong and the third person to join gets kicked back to single-player a few seconds
after entering the room — repeatedly, with no error message that explains why.

The host can identify who that is: their server log prints a warning naming the player when
this is about to happen. Cellular/5G home internet, Starlink, hotspots and shared
apartment/campus WiFi are the usual culprits.

Two players are never affected — this only appears at three or more. The full explanation
is in [GUEST_PAIR_PROBLEM.md](GUEST_PAIR_PROBLEM.md).

---

## Changing the server address later

Repeat step 3. You never need to remove the SD card.

There is also an optional `sd:/wiiu/mh3u_server.txt` (one line, `<ip>` or `<ip>:<port>`)
if you prefer editing a file. **You do not need it** — the config menu is the normal way.
If you use both, whichever you edited most recently wins, and the menu's `Set from:` row
tells you which one is currently in effect.

---

## Troubleshooting

**No notification at the Wii U menu, at all.**
The plugin is not loading. Check `mh3u_revival.wps` is in
`sd:/wiiu/environments/aroma/plugins/` (not a subfolder), and that you are booting **Aroma**
rather than plain Wii U menu. Some older Aroma builds lack the notification module — open
the config menu (step 3) instead, which does not depend on it. If the plugin appears there,
it is loaded and only the notifications are missing.

**`106-0502` on entering Network Mode.**
Transport failure — the console reached nothing. The address is wrong, the host's server
isn't running, or their port forwarding isn't set up. Check the `In use:` row matches what
the host gave you.

**`106-0612`.**
You reached the server but the room join failed. Usually the "who creates the room" problem
above.

**It worked yesterday and now it doesn't.**
If your host is on a home connection their public IP may have changed. Ask them to check,
then update it in the config menu.

**Anything else** — the plugin writes `sd:/wiiu/mh3u_plugin.log`. Send that to your host
along with which of the notifications you saw. Its `[nex] REDIRECTED` line proves the
plugin did its job and the problem is further along.

---

## For developers

The plugin source, how it works, and how to build it are in
[`wiiu_plugin/`](../wiiu_plugin/README.md). Short version: on a real console the game's
NEX-token fetch is a real HTTPS request with a pinned Nintendo certificate, so DNS
redirection cannot work. The plugin replaces the `nn::act::AcquireNexServiceToken` call
itself and hands the game your server's address directly — no TLS, no account server, and
no server-side changes.

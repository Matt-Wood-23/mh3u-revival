# Joining a host's MH3U Revival game

> **On a real Wii U rather than an emulator?** This page is for Cemu. See [WIIU_CONSOLE.md](WIIU_CONSOLE.md) instead.

You join someone who is hosting. The easiest way is the **MH3U Online Bundle** they give you —
a ready-to-run patched Cemu with a one-click launcher. No Python, no account to make, no
Nintendo files, and **online is already switched on for you**. You bring only your
**own legal MH3U dump**.

> **⚠️ Windows will warn you about the `.exe` files.** Both `MH3U_Online.exe` and
> `Cemu_release.exe` are **custom, unsigned builds** (`Cemu_release.exe` is the `mh3u-revival`
> Cemu fork), so Windows Defender / SmartScreen flags them as "unrecognized" or "not commonly
> downloaded" — expected for any unsigned tool, not a sign of malware. To run them:
> *More info → Run anyway* (and/or allow them in Defender). If you'd rather build them yourself
> or read exactly what's changed, the source is linked from the
> [project README](https://github.com/Matt-Wood-23/mh3u-revival).
>
> **If antivirus outright deletes `MH3U_Online.exe`,** use the included
> `If antivirus blocks the launcher - JOIN.bat` instead — it's plain text (nothing to
> quarantine) and does the same **Join** setup. (Hosting still needs the launcher.)

## Steps
1. **Unzip the bundle** anywhere (e.g. `C:\MH3U_Online`). Keep `MH3U_Online.exe`,
   `Cemu_release.exe`, `server.exe`, `resources`, `gameProfiles`, and `portable` together.

2. **Join the host's Tailscale network** ([download](https://tailscale.com/download)) so your
   PC can reach theirs over the internet, with no router setup: install, sign in, accept the
   host's invite — **then make sure your client is on the HOST's tailnet, not your own.**
   Tailscale auto-makes you a personal tailnet, and the invite alone often leaves your client
   on it (so the host can't see your device). If the host says you're not showing up: switch
   to *their* tailnet in the Tailscale UI, then **log out and back in** on the app to re-bind
   (or run `tailscale up --authkey=<key the host gives you> --force-reauth`).

   The host gives you their Tailscale IP (a `100.x` address). Make sure you can reach it before
   playing: `tailscale ping <ip>` → "pong".

   **Prefer Radmin VPN?** Same idea, often less fiddly: install
   [Radmin VPN](https://www.radmin-vpn.com/), choose **Network → Join an existing network**, and
   enter the network name + password the host gives you. Both PCs then show `26.x.x.x` IPs — the
   host gives you *their* `26.x` to enter in the game. Confirm you can reach it first:
   `ping <host's 26.x>` → reply.

3. **Add your MH3U game files (your "dump")** — the same game data you'd use to play MH3U in
   Cemu (not included; bring your own legal copy). You need both the base game
   `[0005000010118300]` and the update `[0005000e10118300]`. Pick **either** way:

   - **(a) Point Cemu at them (easiest, no copying):** *File → Add games directory →* select
     the **parent folder that contains those two dump folders** (e.g. `…\Wii U\Games`) — **not
     a `[Game]` folder itself**. Cemu lists the games it finds *inside* the folder you pick, so
     if you choose the `[Game]` folder directly the list stays empty.
   - **(b) Or copy them into the bundle:** put the dump's `code`, `content`, `meta` folders
     inside `portable\mlc01\usr\title\00050000\10118300\` (and the update's into
     `…\0005000e\10118300\`).

   > The launcher may print **"No MH3U game found"** — it only checks the copy-in location (b).
   > If you used a Game Path (a) and Cemu lists the game, ignore that line.

   > **Not on the US version?** EU/PAL (`10117200`) and JP (`10104D00`, *MH3G HD Ver.*) work
   > too — use *your* game's title ID in the paths above. The **JP version needs extra system
   > files** (sound libraries + Japanese fonts) on any Cemu — see
   > [TROUBLESHOOTING.md](TROUBLESHOOTING.md#jp-version-mh3g-hd-ver--extra-setup).

   > **Already have an MH3U save in another Cemu?** This bundle is a *fresh* portable Cemu, so
   > your existing save isn't in it. **Launch the game once first** (step 4) so Cemu creates the
   > save folder, then **close it** and copy your existing save's contents into
   > `portable\mlc01\usr\save\00050000\10118300\user\80000001\` — that `user\80000001` folder
   > doesn't exist until that first launch. (A new save is fine too if you'd rather start clean;
   > the dump in step 3 is the game, not your save.) The save's **region must match the game's**
   > region — see the Network-Mode crash note in Troubleshooting.

4. **Double-click `MH3U_Online.exe`, then click *Join*.** Paste the **host's IP** (the overlay
   IP from step 2) and hit **Save + Play**. The first time, the launcher:
   - creates your own **unique online identity** (a random NEX PID — nobody else gets the
     same one), and
   - saves the host's IP and launches Cemu.

   After this first run your identity is saved permanently — you can launch from the launcher
   *or* by running `Cemu_release.exe` directly; both work online. The host-IP field stays
   editable, so you can switch hosts any time.

   > **Use the launcher for your first launch** so your unique identity is set before Cemu
   > makes its own. Opened `Cemu_release.exe` first by mistake? No harm — Cemu creates a
   > blank *offline* account, and the next time you run the launcher (*Join → Save + Play*) it
   > detects that and replaces it with your real online identity automatically (your old blank
   > one is kept as `account.dat.offline.bak`).

5. **Online is already on — you can skip the old account step.** The bundle ships pre-set to
   **Network Service = Nintendo** with a valid online account and the dummy gate files, so the
   green online checkmark is there from first launch — you don't touch Cemu's account settings.
   *Only* if that checkmark is ever **missing** (it reads *"not linked to a NNID or PNID"*):
   close Cemu and run **`MH3U_Online.exe`** again → *Join* → *Save + Play* — it re-mints a valid
   identity and the check goes green. (Don't try to set *Network Service* by hand: it's already on Nintendo, and
   it's greyed-out until the account is valid anyway — see Troubleshooting.)

6. **Play:** make sure the host is running their server and sitting in a room, then launch
   MH3U → Network Mode → enter the **same** Gathering Hall → **Enter a Room** → join theirs.

## Troubleshooting

More in **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — including the #1 reported issue
(**halls work but joining a Room disconnects** → Windows Firewall on one of the PCs) and
the JP version's extra setup.

- **You can share a Gathering Hall, but joining a Room instantly disconnects** = the direct
  player↔player connection is blocked, almost always Windows Firewall **Block** rules for
  Cemu on one of the PCs (rooms are P2P; halls aren't). Full fix:
  [TROUBLESHOOTING.md](TROUBLESHOOTING.md#everything-works--halls-chat-seeing-each-other--but-the-moment-we-join-a-room-it-disconnects).
- **The host can't see your device on their tailnet** = your Tailscale client is on your *own*
  tailnet. Switch to the host's tailnet, then **log out and back in** on the Tailscale app to
  re-bind your device — accepting the invite alone doesn't do it. Verify with
  `tailscale ping <host's 100.x>` → "pong" before launching.
- **"Connected to the internet" then back to the village** = can't reach the host's server.
  99% of the time it's Tailscale — confirm you can reach their `100.x` IP (`tailscale ping`
  → "pong"; step 2).
- **Wrong host IP?** Reopen `MH3U_Online.exe` → *Join*, type the new IP, and hit *Save + Play*.
  (Using the fallback `.bat`? It shows the saved host and gives a 5-second window to change it.)
- **Game not in Cemu's list** after *Add games directory* = you picked a `[Game]` folder
  itself. Pick its **parent** folder instead (the one that contains it).
- **The "Network Service" options look grayed out** = that's **normal, not a problem.** Cemu
  only lets you *edit* the network-service choice when **no game is running** *and* the green
  online checkmark is present — but the bundle already ships set to **Nintendo**, so it works
  fine while grayed. (Open *General Settings* while MH3U is running and the whole Account tab is
  locked — that's expected; close the game if you actually need to change it.) What matters is
  the **green check** next to *Online play requirements*, not whether the radio is clickable. If
  that check is **red**, read the status line under it — it names the missing piece
  (OTP/SEEPROM, certificates, or account). If it says **"not linked to a NNID or PNID,"** your
  `account.dat` is a blank offline one (Cemu made it before you ran the launcher) — **close Cemu
  and run `MH3U_Online.exe` again → *Join* → *Save + Play***; it replaces the blank account with a
  valid online identity, and the check goes green.
- **Game crashes the moment you enter Network Mode** = a save whose region/language doesn't
  match the game (e.g. an **EU/Spanish** save on a **US** game). The save's `system` +
  `phraseX` files carry the region; mixing them crashes online. Fix: use a save made on the
  matching region, or make a fresh character in this game's region.
- **Don't** use Cemu's "Launch with GDB stub" — just the launcher or `Cemu_release.exe`.

## Setting up by hand (no bundle)
If you have the patched Cemu but not the bundle, do the equivalent once:
```bash
python dist/make_online_files.py "<cemu_data>"                                   # gate dummies
python dist/make_account.py "<cemu_data>/mlc01/usr/save/system/act/80000001"     # random unique PID
```
then put the host's IP in `<cemu_data>/mh3u_server.txt`. In your Cemu, set *Options → General
Settings → Account* → **Network Service = Nintendo** and **restart Cemu** (the bundle pre-sets
this for you, but a hand setup doesn't). The online-requirements check should be green — then
play (step 6). `make_account.py` already wrote a valid identity, so if it isn't green, you ran it
against the wrong `act/80000001` folder.

## Linux / Steam Deck (experimental)

A community-built **Linux bundle** — `MH3U_Online_Linux.zip` on the
[Releases](https://github.com/Matt-Wood-23/mh3u-revival/releases) page, contributed by
**jM5557**. Same patched Cemu fork as an **AppImage**, the same pre-configured `portable/`
folder, plus a launcher of its own. x86-64 Linux and **SteamOS / Steam Deck**.
**New in v0.2.0: it can host, not just join** — the server ships in the bundle, so a group
needs no Windows machine at all.

1. Unzip, then add your dump exactly as in step 3 above (same folder layout, forward
   slashes).
2. Run `./MH3U_Online` — already executable, no `chmod` needed. Mouse, keyboard
   (arrows + Enter + Esc) and **controller** (D-Pad + A/B) all work, which is what makes it
   usable on a Deck.

| Menu item | What it does |
|---|---|
| **Join Online** | Asks for the host's IP and mints your online identity (saved in `portable/mh3u_server.txt`) |
| **Host Server** | Runs the server on this machine — see below |
| **Launch Game** | Point it at your `.wua` / `.wud` / `.wux` / `.rpx`; it remembers the path and boots straight in |
| **Launch Cemu** | Just opens Cemu |

**Hosting from Linux.** The Host screen has an **Advertise IP** field (the address your
players type), a **Relay:** toggle cycling `off` / `auto` / `force`, and Start / Stop /
**View Server Log**. That's the same relay as the Windows launcher's checkbox — read
[HOSTING.md](HOSTING.md#optional-the-udp-relay) before enabling it, and with three or more
players read the room-creator rule in [GUEST_PAIR_PROBLEM.md](GUEST_PAIR_PROBLEM.md) first.

**On a Steam Deck**, run the launcher once in **Desktop mode**, then right-click →
**Add to Steam** to start it from your library in Gaming Mode.

Everything else on this page (dump layout, saves, troubleshooting, the
`portable/mh3u_server.txt` IP file) applies unchanged; the Windows antivirus warnings don't.

> **No auto-updater on Linux.** The Windows launcher checks GitHub for new releases; this
> one doesn't, and the bundle carries no version marker — watch the Releases page and
> re-download by hand.

**Experimental status:** the port is proven by the contributor on SteamOS and Arch via
**LAN** play. Hosting from Linux is new in this build and untested by the project — please
report how it goes. Tailscale and the public-IP path are transport-level and expected to
work from a Linux joiner. To build the AppImage yourself, the source is the
[Cemu fork](https://github.com/Matt-Wood-23/Cemu/tree/mh3u-revival).

## Android (experimental)

**jM5557** maintains an Android build of Cemu with this project's online patches carried over:
[jM5557/Cemu-Android-MH3U-Revival](https://github.com/jM5557/Cemu-Android-MH3U-Revival/releases).
It **joins** a host's server by IP; it can't host one, so somebody in the group still runs the
server on a PC (or from the Linux bundle).

It isn't part of this project's releases: the APK, its setup and its updates all come from that
page. It's early and experimental, and its README asks people not to open issues there yet.
When the online client changes here, the Android build gets the change once jM5557 ports it,
so it can lag a release behind.

## Cemu Enhanced (optional, experimental)

A heavier build of the same patched Cemu, released on its own from the
[Cemu fork](https://github.com/Matt-Wood-23/Cemu/releases/tag/enhanced-v0.1.1) rather than in the bundle. Online play and custom textures work as in the
bundle's Cemu, and it adds:

- **Save states**: File → Save state / Load state, 10 slots per game.
- **Pause**: File → Pause emulation, plus an option to pause when Cemu loses focus.
- **Cheats**: Citra-style cheat files, edited under Tools → Cheats. See jM5557's QOL set below.
- **Screen layouts**: TV and GamePad arrangements under View → Screen Layout.
- **Game Mode**: a controller-first launcher (View → Game Mode), and an in-game menu on
  **F10**. From a controller, press Guide (SDL controllers), or hold the menu button for about
  a second; a quick press of that button still goes to the game. Set the button under
  Options → Hotkey settings.

Pause, cheats, screen layouts and Game Mode are jM5557's work.

**Online:** save states and pause are blocked while the game is online, because either one
drops you from the room: a paused game stops answering, and a save state can't hold the
connection. Go offline first (back to the village) to use them.

**Installing** means swapping the Cemu inside a bundle you already have. Everything else stays,
including the `portable/` folder with your online setup, saves and server IP.

- **Windows:** in the bundle folder, keep a copy of `Cemu_release.exe`, then put the one from
  `Cemu-Enhanced-Windows.zip` in its place. The launcher starts it as before.
- **Linux / Steam Deck:** replace `Cemu.AppImage` with the release's AppImage (`x86_64` for a
  Deck), renamed to `Cemu.AppImage`, then `chmod +x Cemu.AppImage`.

To go back, put the original file back.

> Save states belong to the build that made them, so after updating Enhanced, older states may
> refuse to load. Your in-game saves aren't affected.

**jM5557's QOL cheats.** His [MH3U-Cemu-Cheats](https://github.com/jM5557/MH3U-Cemu-Cheats)
set brings in quality-of-life touches from newer Monster Hunter games: hold A to carve and
gather, skip the end-of-quest timer, send all rewards to the box, change equipment from Port
Tanzia's tavern box, and more. To add them, download the file for your game from his repo and
put it in the bundle's `portable/cheats/` folder (create the folder if it isn't there):

| Game | File |
|---|---|
| MH3U US (v32) | `0005000010118300.txt` |
| MH3U EU (v32) | `0005000010117200.txt` |
| MH3G JP (v96) | `0005000010104d00.txt` |

The main QOL cheats are on as soon as the file is there; his variants and experimental ones
start off. Toggle them under Tools → Cheats or Cheats in the in-game menu. Turning one off
takes effect after a game restart, or straight away by ticking its matching `DISABLE` entry.
His README describes each one. Back up your save before trying the experimental ones.

---

No Nintendo files are involved: the online "certs" are 4-byte empty stubs and otp/seeprom
are zeros — they only satisfy Cemu's file-existence check, because the patched build sends
the real connection to the host's server, not Nintendo.

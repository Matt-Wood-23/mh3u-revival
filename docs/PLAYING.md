# Joining a host's MH3U Revival game

You join someone who is hosting. The easiest way is the **MH3U Online Bundle** they give you —
a ready-to-run patched Cemu with a one-click launcher. No Python, no account to make, no
Nintendo files, and **online is already switched on for you**. You bring only your
**own legal MH3U dump**.

> **⚠️ Windows will warn you about `Cemu_release.exe`.** It's a **custom build of Cemu**
> (the `mh3u-revival` Cemu fork), so it isn't signed and Windows Defender / SmartScreen will
> flag it as "unrecognized" or "not commonly downloaded" — that's expected for any unsigned
> emulator build, not a sign of malware. If you'd rather build it yourself or read exactly
> what's changed, the full source fork is linked from the
> [project README](https://github.com/Matt-Wood-23/mh3u-revival). To run the provided build:
> *More info → Run anyway* (and/or allow it in Defender).

## Steps
1. **Unzip the bundle** anywhere (e.g. `C:\MH3U_Online`). Keep `PLAY MH3U ONLINE.bat`,
   `Cemu_release.exe`, `resources`, `gameProfiles`, and `portable` together.

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

4. **Double-click `PLAY MH3U ONLINE.bat`.** The first time, it:
   - creates your own **unique online identity** (a random NEX PID — nobody else gets the
     same one), and
   - asks for the **host's IP** (paste the overlay IP from step 2).

   Then it launches Cemu. After this first run your identity is saved permanently — you can
   launch with the `.bat` *or* `Cemu_release.exe` directly; both work online. (Always using
   the `.bat` is fine too.)

   > **Use the `.bat` for your first launch** so your unique identity is set before Cemu
   > makes its own. Opened `Cemu_release.exe` first by mistake? No harm — Cemu creates a
   > blank *offline* account, and the next time you run the `.bat` it detects that and
   > replaces it with your real online identity automatically (your old blank one is kept
   > as `account.dat.offline.bak`).

5. **Online is already on — you can skip the old account step.** The bundle ships pre-set to
   **Network Service = Nintendo** with a valid online account and the dummy gate files, so the
   green online checkmark is there from first launch — you don't touch Cemu's account settings.
   *Only* if that checkmark is ever **missing** (it reads *"not linked to a NNID or PNID"*):
   close Cemu and run **`PLAY MH3U ONLINE.bat`** again — it re-mints a valid identity and the
   check goes green. (Don't try to set *Network Service* by hand: it's already on Nintendo, and
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
- **Wrong host IP?** Edit `portable\mh3u_server.txt` (one line, just the IP) and relaunch.
  The `.bat` only asks the first time.
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
  and run `PLAY MH3U ONLINE.bat` again**; it replaces the blank account with a valid online
  identity, and the check goes green.
- **Game crashes the moment you enter Network Mode** = a save whose region/language doesn't
  match the game (e.g. an **EU/Spanish** save on a **US** game). The save's `system` +
  `phraseX` files carry the region; mixing them crashes online. Fix: use a save made on the
  matching region, or make a fresh character in this game's region.
- **Don't** use Cemu's "Launch with GDB stub" — just the `.bat` or `Cemu_release.exe`.

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

A community-built **Linux bundle** exists — `MH3U_Online_Linux.zip` on the
[Releases](https://github.com/Matt-Wood-23/mh3u-revival/releases) page, contributed by
**jM5557**. It's the same patched Cemu fork built as a Linux **AppImage**, with
`SETUP-ONLINE.sh` replacing `PLAY MH3U ONLINE.bat` (same identity minting, same host-IP
prompt) and the same pre-configured `portable/` folder. Works on x86-64 Linux and
**SteamOS / Steam Deck**.

1. Unzip, then add your dump exactly as in step 3 above (same folder layout, forward
   slashes).
2. First run, from a terminal in the bundle folder:
   ```bash
   chmod +x SETUP-ONLINE.sh
   ./SETUP-ONLINE.sh
   ```
   It mints your identity, asks for the host's IP, and launches Cemu.
3. Later runs: `./SETUP-ONLINE.sh` again, or just run `Cemu.AppImage` directly — on a
   Steam Deck you can add it to Steam as a **Non-Steam Game**.

Everything else on this page (dump layout, saves, troubleshooting, the
`portable/mh3u_server.txt` IP file) applies unchanged.

**Experimental status:** proven by the contributor on SteamOS and Arch via **LAN** play.
Tailscale (available on Linux) and the public-IP path haven't been tested from a Linux
joiner yet but are transport-level — expected to work; please report either way. The zip's
`BUILD.txt` documents the full reproducible build against the
[Cemu fork](https://github.com/Matt-Wood-23/Cemu/tree/mh3u-revival) if you'd rather build
the AppImage yourself.

---

No Nintendo files are involved: the online "certs" are 4-byte empty stubs and otp/seeprom
are zeros — they only satisfy Cemu's file-existence check, because the patched build sends
the real connection to the host's server, not Nintendo.

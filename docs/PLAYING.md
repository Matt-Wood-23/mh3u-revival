# Joining a host's MH3U Revival game

You join someone who is hosting. The easiest way is the **MH3U Online Bundle** they give you —
a ready-to-run patched Cemu with a one-click launcher. No Python, no account to make, no
Nintendo files. You bring only your **own legal MH3U dump**.

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

3. **Copy your MH3U dump** to this PC (not included — bring your own). You need both the
   base game `[0005000010118300]` and the update `[0005000e10118300]`. In Cemu:
   *File → Add games directory →* the folder containing both.

   > **Already have an MH3U save in another Cemu?** This bundle is a *fresh* portable Cemu, so
   > your existing save isn't in it. Copy your save folder into this Cemu's data —
   > `portable\mlc01\usr\save\00050000\10118300\` — to keep your hunter. (A new save is fine
   > too if you'd rather start clean; the dump in step 3 is the game, not your save.)

4. **Double-click `PLAY MH3U ONLINE.bat`.** The first time, it:
   - creates your own **unique online identity** (a random NEX PID — nobody else gets the
     same one), and
   - asks for the **host's IP** (paste the overlay IP from step 2).

   Then it launches Cemu. After this first run your identity is saved permanently — you can
   launch with the `.bat` *or* `Cemu_release.exe` directly; both work online. (Always using
   the `.bat` is fine too.)

   > **Use the `.bat` for your first launch.** It must set your unique identity *before*
   > Cemu auto-creates its own (which would collide with everyone else's).

5. **Enable online once:** Cemu → *Options → General Settings → Account* — set **Network
   Service = Nintendo** and make sure online play is enabled (the online-requirements status
   should read all green; the bundle's dummy gate files are what satisfy it). Then **restart
   Cemu** for it to take effect.

6. **Play:** make sure the host is running their server and sitting in a room, then launch
   MH3U → Network Mode → enter the **same** Gathering Hall → **Enter a Room** → join theirs.

## Troubleshooting
- **The host can't see your device on their tailnet** = your Tailscale client is on your *own*
  tailnet. Switch to the host's tailnet, then **log out and back in** on the Tailscale app to
  re-bind your device — accepting the invite alone doesn't do it. Verify with
  `tailscale ping <host's 100.x>` → "pong" before launching.
- **"Connected to the internet" then back to the village** = can't reach the host's server.
  99% of the time it's Tailscale — confirm you can reach their `100.x` IP (`tailscale ping`
  → "pong"; step 2).
- **Wrong host IP?** Edit `portable\mh3u_server.txt` (one line, just the IP) and relaunch.
  The `.bat` only asks the first time.
- **Don't** use Cemu's "Launch with GDB stub" — just the `.bat` or `Cemu_release.exe`.

## Setting up by hand (no bundle)
If you have the patched Cemu but not the bundle, do the equivalent once:
```bash
python dist/make_online_files.py "<cemu_data>"                                   # gate dummies
python dist/make_account.py "<cemu_data>/mlc01/usr/save/system/act/80000001"     # random unique PID
```
then put the host's IP in `<cemu_data>/mh3u_server.txt` and do steps 5–6 above.

---

No Nintendo files are involved: the online "certs" are 4-byte empty stubs and otp/seeprom
are zeros — they only satisfy Cemu's file-existence check, because the patched build sends
the real connection to the host's server, not Nintendo.

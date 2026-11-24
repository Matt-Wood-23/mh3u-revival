# MH3U Revival — unified launcher

A single tkinter window — the **primary entry point** of the all-in-one bundle — with
dead-simple **JOIN** / **HOST** buttons for non-technical friends, replacing the old
two-batch flow (`PLAY MH3U ONLINE.bat` + `HOST_MH3U.bat`). It is **stdlib-only** so it
freezes to a self-contained `MH3U_Online.exe` and drops into the bundle root next to
`Cemu_release.exe` and `server.exe`. (The join batch still ships, renamed
`If antivirus blocks the launcher - JOIN.bat`, as a fallback for when AV quarantines the
unsigned exe.)

## What it does

**Home** — two big buttons: `JOIN A GAME` / `HOST A SERVER`, plus a status strip
showing the bundle version and update state.

**Join** — ports `PLAY MH3U ONLINE.bat` exactly:
- game-dump presence check (friendly guidance if `portable\…\10118300\code` is missing);
- first-run NEX identity **mint**, or **repair** of a blank offline Cemu account
  (detected by the missing `IsPasswordCacheEnabled=1` marker; the blank one is
  moved to `account.dat.offline.bak` and re-minted) — **byte-identical** account
  format to the .bat / `make_account.py` (random PID `0x40000000–0x6fffffff`,
  random TransferableIdBase/Uuid/AccountPasswordCache, stock Mii,
  `AccountId=CemuMH3U<last4>`, LF line endings);
- writes the host IP to `portable\mh3u_server.txt` (pre-filled if already set);
- with "Add the official event quests" ticked: puts the official event quests (downloaded
  from `events/`) **and the 38 quests Capcom used to offer as downloads** into the US/EU save
  packs: the 28 event quests go into `quest3`, then `quest1`, then `quest2`, the packs the
  game's Event Quests list reads; the 10 Challenge Quests (61000-61009) go into `quest4`,
  which the Arena's Challenge list reads. A pack that is a renamed copy of another (its
  header still names the original, so the game skips it, e.g. a `quest1` copied to `quest2`
  by hand) gets no quests, and quests the launcher put there move out. It closes up any pack
  it changes, since the game stops reading a pack early when there's an empty slot in it.
  Capcom's are copied from the player's own game (`content\nativeCafe\quest\us`, found in
  Cemu's mlc01, recently launched games or Game Paths; unpacked games only), so nothing
  from the game ships with the bundle. They are exactly what the download servers (Capcom's,
  now the goshawk replacements) offered for US/EU. The 9 collab quests (DUMMY in the Western
  files) are left out; quests a player already has, e.g. from the old downloads, are left alone;
- before launching: rebuilds the name tables of the cross-version event quest fix
  (`portable\graphicPacks\MH3U_EventQuestFix`, see `eventfix_names.py`) from the same
  game files, and makes sure that pack is switched on in `portable\settings.xml`;
- launches `Cemu_release.exe` from the launcher's own directory
  (skippable with `MH3U_NOLAUNCH=1`, same as the .bat).

**Host** — ports `HOST_MH3U.bat`:
- detects Radmin (`26.x`, pure-Python socket scan), Tailscale (`100.x`,
  `tailscale ip -4` with the `%ProgramFiles%\Tailscale\tailscale.exe` fallback),
  and LAN IPs, shown as radio choices **plus** a free-text override — nothing is
  silently picked; preselect priority is Radmin > Tailscale > LAN > loopback,
  same as the .bat;
- `Start Server` sets `MH3U_ADVERTISE` and spawns `server.exe` (or
  `python server.py` for a source checkout), streaming stdout/stderr into a
  scrolling log and showing a copyable **"Friends connect to: `<ip>`"** banner;
- `Stop Server` terminates the child cleanly (also on window close);
- `Host + Play (127.0.0.1)` starts the server **and** runs the join flow against
  loopback;
- `server.exe` now ships in every (all-in-one) bundle, so the Host tab is always live;
  the "no server found" branch is a fallback that only fires if `server.exe` was removed
  (e.g. AV quarantine) and tells the user to re-download the bundle.

All subprocess/network work runs on background threads; the UI never freezes.

## Languages

The launcher speaks the six languages the games use: English, French, German, Italian,
Spanish and Japanese. It starts in the PC's display language when it has it (English
otherwise), and the **Language** picker in the top bar switches it; the choice is saved in
`portable\mh3u_launcher.json`. Switching rebuilds the window and keeps the open tab and a
typed IP; it's refused while the Host tab's server is running.

**Translations other than English are machine-made and may be inaccurate**; the Home tab
says so in the chosen language. All the text lives in `launcher_i18n.py`, one entry per
English sentence. To fix a translation, edit it there and keep every `{word}` in braces
exactly as it is. `python launcher.py --selftest` reports a missing translation, a changed
`{word}`, or a launcher sentence with no entry. The server list's names and news line come
from `servers.json` and are shown as written.

## Official servers (`servers.json`)

The Join tab offers the official server(s) next to "A friend's server". The list comes
from [`servers.json`](../../servers.json) in the repo root, which the launcher downloads
from the `main` branch at every start (cached in `portable\mh3u_servers_cache.json` for
offline starts). So moving the server or posting a notice is a commit to that file, not a
launcher release.

```json
{
  "schema": 1,
  "news": "Server maintenance Sunday 18:00 UTC.",
  "servers": [
    {"id": "us", "name": "Official server (US Central)",
     "host": "mh3u.example.org", "status_port": 8080}
  ]
}
```

- `host` is a DNS name or an IPv4. The launcher looks it up at every launch and writes the
  IP into `mh3u_server.txt` (Cemu needs an IP).
- `status_port` is the server's `MH3U_STATUS_PORT`. With it, the Join tab and Home show
  "12 hunters online · 3 rooms", refreshed every minute. Leave it out to show no count.
- `news` is shown on Home and Join when it isn't empty.
- With an empty `servers` list, the Join tab says the official server isn't available yet.

The player's choice is saved in `portable\mh3u_launcher.json` (protected from updates).
A fresh install starts on the first official server. An install that already had a
friend's IP saved stays on it.

**Test connection** sends the game's NAT-check question to the chosen server on UDP 10025
(the same packet as `tests/extkit/check_natcheck.py`), reports the address the server
sees, and for an official server also reads its status page.

## Auto-updater

- `version.txt` sits next to the exe (bundle root). The launcher reads it;
  missing → `unknown`.
- On startup a background thread GETs the GitHub latest-release API (10 s
  timeout, fails silent to *"update check failed — offline?"*), then compares the
  release tag to `version.txt` **numerically** (so `v0.1.10-beta` > `v0.1.7-beta`;
  a local dev/unknown version is never *downgraded*).
- If newer, a non-blocking banner offers `Update now`. The update flow:
  downloads the single `MH3U_Online_Bundle.zip` (all-in-one — it carries `server.exe`,
  so hosts and players update from the same asset) with a progress bar, then extracts
  over the bundle.
- **User state is never touched** — `portable\mh3u_server.txt`,
  `portable\mlc01\usr\save\**` (account.dat + game saves), and
  `portable\mlc01\usr\title\**` (the dump) are excluded from the overwrite set.
  `version.txt` is rewritten **last**, only after a successful extract.
- It refuses to update while `Cemu_release.exe` / `server.exe` are running
  (checked via `tasklist`).
- **Self-update:** a running exe can't overwrite itself, so the new launcher is
  staged as `MH3U_Online.exe.new` and a tiny `_mh3u_update_replace.bat` waits for
  the parent to exit, swaps the files, relaunches, and deletes itself.

The updater is built from **pure functions** (`plan_overwrite`,
`is_protected_path`, `is_newer`, `parse_latest_release`, `apply_update_zip`,
`download_file`) separated from tkinter, so they're testable headless.

### Bundle zip layout (discovered from `dist_build`)

The all-in-one release zip extracts at the **root** (no wrapping folder):

```
MH3U_Online_Bundle.zip   ->  MH3U_Online.exe, server.exe, Cemu_release.exe,
                             version.txt, QUICKSTART.txt,
                             "If antivirus blocks the launcher - JOIN.bat",
                             gameProfiles/, resources/,
                             portable/  (mh3u_server.txt, otp.bin, seeprom.bin,
                                         settings.xml, mlc01/…)
```

So members extract directly under the bundle root — that's what
`apply_update_zip` assumes. (The separate `MH3U_Host_AddOn.zip` is retired; `server.exe`
now ships inside the main bundle.)

## Build

```bash
python build_launcher.py                 # -> dist/MH3U_Online.exe
python build_launcher.py --stamp v0.1.7-beta   # also writes dist/version.txt
```

Uses PyInstaller onefile + `--noconsole` + UPX, mirroring how `server.exe` is
frozen in `dist_build/pyi/server.spec`. Because the launcher is stdlib-only, no
`hiddenimports` / `collect_all` are needed (tkinter is picked up by PyInstaller's
built-in hooks).

## Bundle integration

Copy `dist/MH3U_Online.exe`, `dist/version.txt`, **and** `server.exe`
(`dist_build/pyi/dist/server.exe`) into the bundle root — the all-in-one layout, next
to `Cemu_release.exe`. The bundle build should **stamp `version.txt` with the release
tag** so the updater has a baseline. The join batch ships alongside, renamed
`If antivirus blocks the launcher - JOIN.bat`, as the no-exe fallback.

Copy `graphic_packs/MH3U_EventQuestFix/` (as built in the repo: our nine quest names only)
to the bundle's `portable/graphicPacks/MH3U_EventQuestFix/`. Never ship a copy the
launcher has filled in: that one holds the game's quest text. `dist/bundle_settings.xml`
already lists the pack as switched on.

Copy `graphic_packs/MH3U_FPS_Cap/` to `portable/graphicPacks/MH3U_FPS_Cap/` too.
`dist/bundle_settings.xml` switches it on with the 60 FPS preset (players can change it; the
launcher doesn't force it on).

## Self-test

```bash
python launcher.py --selftest
```

Runs headless (no GUI, no network) and asserts: account.dat mint format + PID
range + LF-only bytes; repair-detection (`new` / `repair` / no-op, incl. the
LF-only false-positive guard); `mh3u_server.txt` read/write; version ordering
(`v0.1.7-beta` vs `v0.1.10-beta`, unknown/missing handling); the update
file-filter (protected paths never in the overwrite set); `servers.json` parsing (bad
hosts and duplicate ids dropped); the NAT-check probe against a loopback responder; the
status line; and which Join choice is preselected. The NAT-check test uses loopback
only. tkinter is imported
lazily inside `_run_gui()`, so the module imports and self-tests fine without a
display.

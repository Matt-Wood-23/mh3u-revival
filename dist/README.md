# `dist/` — player setup pieces

The files that prepare a player's Cemu for MH3U Revival: two small, dependency-free Python
scripts, plus the batch launcher here (`PLAY MH3U ONLINE.bat`) that now ships as the
**antivirus fallback** for joining. The primary entry point is the GUI launcher in
[`launcher/`](launcher/) — `MH3U_Online.exe` — which does **JOIN and HOST** from one window.
They ship **no Nintendo data** — see the note at the bottom.

For the actual walkthroughs, see:

- **[../docs/HOSTING.md](../docs/HOSTING.md)** — running the server + setup if you host.
- **[../docs/PLAYING.md](../docs/PLAYING.md)** — joining a friend's game.

## `make_online_files.py`

Generates the right-sized dummy Wii U online-gate files Cemu checks before enabling online
mode (`otp.bin`/`seeprom.bin` = zeros; cert files = 4-byte empty stubs). No real keys or
certificates.

```bash
python make_online_files.py "<cemu_data>"
```

`<cemu_data>` = the folder holding Cemu's `settings.xml` (the `portable` folder for a
portable install, else `%APPDATA%\Cemu`).

## `make_account.py`

Generates a Cemu `account.dat` with a **random, unique NEX PID** — every player just runs
it; no coordination needed. Contains no personal data.

```bash
python make_account.py "<cemu_data>/mlc01/usr/save/system/act/80000001"
```

Add `--player N` to pin a fixed PID (`1000000000+N`) instead of random — rarely needed.

## `PLAY MH3U ONLINE.bat` (ships as the antivirus fallback)

The pure-batch join path. In the all-in-one bundle this file ships **renamed** to
`If antivirus blocks the launcher - JOIN.bat` — insurance for anyone whose antivirus
quarantines the unsigned `MH3U_Online.exe` (plain text can't be quarantined, and it needs no
Python). It does the same JOIN setup the GUI launcher does: on first run it mints a random
unique NEX identity (`account.dat`) and asks for the host's IP (saved to `mh3u_server.txt`),
then starts Cemu; later runs show the saved host with a 5-second window to change it. The dummy
gate files come pre-made in the bundle, so it doesn't need `make_online_files.py`. (Hosting is
launcher-only — the fallback bat covers joining.)

This copy is the **canonical source**, kept byte-identical to the fallback bat packed in the
distributed bundle — repack the bundle from this file if you change it.

> **Maintainer gotcha — escape parens in `echo`.** Inside an `if (...)` block, a literal `(`
> or `)` in an `echo` line must be written `^(` / `^)`. An unescaped `)` closes the block
> early and cmd dies with `. was unexpected at this time` — even on runs that *skip* that
> block, because cmd parses the whole block every time. (This bit the IP-prompt text once; the
> identity block was already escaped.)

## Note

The server auto-provisions any numeric PID, so adding players needs **no server change**. If
two players ever collide on a PID (astronomically unlikely with random assignment), the
server logs a `register: pid=… already held` warning and the newer player just re-runs
`make_account.py` for a fresh one. No Nintendo files are produced or shipped.

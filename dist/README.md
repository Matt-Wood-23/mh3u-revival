# `dist/` — player setup scripts

Two small, dependency-free scripts that prepare a player's Cemu for MH3U Revival. They
ship **no Nintendo data** — see the note at the bottom.

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

> The MH3U Online Bundle wraps this in a one-click `PLAY MH3U ONLINE.bat` launcher (no
> Python), which generates the identity on first run. These scripts are the manual equivalent.

## Note

The server auto-provisions any numeric PID, so adding players needs **no server change**. If
two players ever collide on a PID (astronomically unlikely with random assignment), the
server logs a `register: pid=… already held` warning and the newer player just re-runs
`make_account.py` for a fresh one. No Nintendo files are produced or shipped.

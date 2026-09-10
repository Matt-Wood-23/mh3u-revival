# MH3U Revival — Wii U plugin

Hardware counterpart to the patched Cemu fork. Lets a **real Wii U** connect to a
self-hosted MH3U revival server.

## Why a plugin and not DNS

On a console, the game's NEX-token fetch is a real HTTPS request:

```
POST https://account.nintendo.net/v1/api/provider/nex_token/@me?game_server_id=10104D00
```

IOSU pins the server certificate to **Nintendo CA-G3** and authenticates with the
console's Nintendo-issued client certificate. A DNS redirect therefore dies at the TLS
handshake — you cannot present a chain the console trusts. (This is why Pretendo ships
Inkay, a URL + CA patch, rather than a DNS service.)

So instead of redirecting the request, we **replace the call**:

```
AcquireNexServiceToken__Q2_2nn3actFP26ACTNexAuthenticationResultUi
= nn::act::AcquireNexServiceToken(ACTNexAuthenticationResult *token, u32 serverId)
```

When `serverId == 0x10104d00` (MH3U's NEX game-server-id, identical in US/EU/JP) the
plugin fills the 0x25C-byte result struct itself and returns success. The call never
reaches IOSU: no TLS, no account server, no NNID handshake — and **no server-side
changes**. This mirrors `ACT_GetNexToken_WithCache()` in the Cemu fork's
`napi_act.cpp:327-359`.

## v0.2.0 — the devoptab gotcha (first field failure)

`WUPS_PLUGIN_NAME()` expands to `WUT_MALLOC` / `SOCKETS` / `NEWLIB` / `STDCPP` /
`THREAD` — but **not** `WUT_DEVOPTAB` (see `wups/meta.h:45`; the official
`example_plugin_cpp` opts in on its own line). Without it the `fs:` device is
never registered and **every `fopen()` returns NULL**.

v0.1.0 missed that line, and the failure mode was maximally misleading: no log
file was created, `mh3u_server.txt` was never read, `gHost` silently kept its
`127.0.0.1` default, and the game was handed a loopback address it could never
reach. From the outside the plugin looked completely dead while it was in fact
running and patching correctly.

The tester's error code was the tell: **`106-0502`** is module 106 (NEX game
servers), code 0502 (`Transport::ConnectionFailure`) — a *transport* failure,
not the `102-xxxx` account error you would get if the token fetch had actually
reached Nintendo's dead NNAS. The hook had fired; it just pointed at localhost.

Verifying the fix is a one-liner, and worth doing after any toolchain bump:

```sh
grep -c on_init_wut_devoptab mh3u_revival.elf   # 0 in v0.1.0, non-zero now
```

## v0.4.0 — the address is editable on-console

Through v0.3.0 the only way to retarget the server was to power off, eject the SD
card, edit `mh3u_server.txt` on a PC and put it back. That is the single most-repeated
action in a test session, and it dominated the turnaround on every field test.

The address now lives in **WUPS storage** and is edited with the GamePad from the
plugin config menu (**L + DPAD-Down + Minus**). No SD removal, no FTP, no PC.

`mh3u_server.txt` still works and is still read. The two are reconciled by
**last edit wins**:

- the plugin remembers the file's contents as of the last time it adopted them
  (`txt_host_seen` / `txt_port_seen` in storage)
- if the file differs from that record, a human edited the file → adopt the file
- otherwise the stored value wins, because the config menu is the only other place
  an edit can have come from

So neither editor silently loses to the other, and there is no "which source?" toggle
to get wrong. The config menu always shows which one the running value came from.

A consequence worth knowing: **`mh3u_server.txt` is now optional.** Once an address has
been set on-console, the file can be deleted and the plugin keeps working.

### Storage init ordering is not assumed

`wups/hooks.h` lists `INIT_STORAGE` *after* `INIT_PLUGIN` in the hook enum, but that
enum is a type list, not a dispatch order — `INIT_WUT_DEVOPTAB` is listed early too and
demonstrably runs before `INITIALIZE_PLUGIN` (the v0.2.0 fix depends on exactly that).
Rather than bet on either reading, every storage access goes through `storageReady()`,
which retries at the next entry point if the API reports `INTERNAL_NOT_INITIALIZED`.
The config menu reports whether storage answered, so a wrong guess is visible rather
than silent.

## Installing

1. Copy `mh3u_revival.wps` to `sd:/wiiu/environments/aroma/plugins/`
2. Boot Aroma. At the Wii U menu an on-screen notification confirms the plugin
   loaded and shows the address it will use.
3. Set the server address — **either** way works:
   - **On-console (v0.4.0+, no SD removal):** hold **L + DPAD-Down + Minus**, pick
     *MH3U Revival*, set **Server IP address** with the D-pad, press B to close.
   - **SD card:** create `sd:/wiiu/mh3u_server.txt` containing the address (see below).
4. Launch MH3U, enter Network Mode

To uninstall, delete the `.wps`. The plugin only acts on MH3U's server-id and stays
silent for every other title.

## Configuration

### On-console (v0.4.0+) — the normal way

Hold **L + DPAD-Down + Minus** → **MH3U Revival**. The first two rows are editable:

| Row | Notes |
|---|---|
| **Server IP address** | Press **A** to edit, **left/right** to move between octets, **up/down** to change one, **A** to confirm |
| **Server port** | Defaults to 1223, which is what the server uses. Rarely needs touching |

The rows below are read-only status, including **Set from:**, which names whichever
source the running value came from. Changes are saved on the console and survive a
reboot; the game picks them up the next time it launches.

This menu opens from anywhere, including the Wii U menu, so the address can be changed
without launching the game first.

### `sd:/wiiu/mh3u_server.txt` — still supported, now optional

Same format as the Cemu fork's file, so one build works against any server:

```
# host or host:port  (port defaults to 1223)
192.168.1.50:1223
```

The host field in the token struct is `char[0x10]`, so the address must be **15
characters or fewer** — an IPv4 literal always fits, a long hostname does not. An
invalid entry is rejected (and logged) rather than silently truncated.

Config is re-read every time the game starts and every time the config menu opens, so
changing servers via the file is: edit the file, relaunch the game. No reboot, no new
build.

Editing this file always wins over a value set in the config menu, because a changed
file is unambiguous evidence of a newer edit. Editing the menu then wins again. See
the v0.4.0 note above.

## Diagnostics

Three independent channels, so "the plugin never loaded" can never again be
confused with "the plugin ran but could not write":

**1. On-screen notifications** (libnotifications — no SD access needed)

| When | Message |
|---|---|
| Wii U menu | `MH3U Revival v0.4.0 active - server <host>:<port>` — proof of life |
| Wii U menu, red | Loaded, but no server address is set anywhere |
| MH3U start | `will redirect NEX to <host>:<port>` |
| Hook fires | `NEX token redirected -> <host>:<port>` (first 2 only, to avoid burying the screen) |

**2. Plugin config menu** — hold **L + DPAD-Down + Minus**, pick *MH3U Revival*.
Depends only on WUPS itself, so it still works if the notification module is
absent. As of v0.4.0 this is also where the address is **set**. Shows the address
in use, which source it came from, whether the SD file was read, whether settings
could be saved on-console, whether the log is writing, and the redirect count.

**3. `sd:/wiiu/mh3u_plugin.log`** — every relevant `nn_act` call, flushed per
line so it survives a hang. Also mirrored to `OSReport`, so a UDP log catcher
sees it even with no SD write access.

| Log tag | Meaning |
|---|---|
| `[cfg]` | Which endpoint was parsed, and any rejected input |
| `[nex] REDIRECTED` | **The hook fired.** The game asked for MH3U's token and got ours |
| `[nex] passthrough` | The game asked for a *different* server-id (should not happen in MH3U) |
| `[act] GetPrincipalId` | The console's real NNID PID — match this against the server log |
| `[act] HasNfsAccount` | Cemu hardcodes this true; this is what real hardware says |

## Building

Requires Docker (no local devkitPro needed):

```sh
docker build -t mh3u-revival-plugin .
docker run --rm -v "$PWD:/project" mh3u-revival-plugin make
```

Output: `mh3u_revival.wps`.

The toolchain images are pinned in the `Dockerfile`
(`devkitppc:20260225` + `wiiupluginsystem:20260418` + `libnotifications:20260404`).

## Known caveats

- **Region.** The server-id gate is region-agnostic, so US/EU/JP all redirect. However
  the PRUDP access key in the server's `config.py` was only ever verified against US.
  If a EU/JP console reaches the server but its SYN signature is rejected, that
  region's access key differs and must be added server-side.
- **NNID.** The console should be signed into an NNID — the game reads its PID from the
  account. That PID lands inside the server's auto-provisioning range, so no server
  change is needed.
- **Hardware status: WORKING.** v0.2.0 was confirmed end-to-end on a real Wii U
  (2026-09-03): console → self-hosted server → matchmaking → P2P session shared
  with a Cemu client on the same LAN. Real hardware and emulator interoperate.
  (v0.1.0 loaded and its hook fired, but the devoptab bug above pinned it to
  localhost, so the server was never contacted.)

  The optional **UDP relay** (`MH3U_RELAY=force`, server side) was also proven on
  hardware the same day: 8m52s of relayed play, both peers' addresses hidden behind
  the relay, so no joiner needs port forwarding. The console needs no changes for it.

  **The public-internet path is also proven** (2026-09-03): a real EU console reached
  the server across the open internet and held a relayed P2P session with a Cemu
  client. Same peer pair, direct hole-punch reported `result=False` twice, then
  `result=True` once relayed — so the relay was doing real work, not riding a
  connection that would have formed anyway. Server side: `MH3U_RELAY=force
  MH3U_RELAY_PROBES=host`.

- **`AcquireIndependentServiceToken` is never called.** Three sessions on a real EU
  console produced zero `[indep]` lines while the NEX hook fired normally, so v0.3.0
  drops that hook and its `stub_independent_token` flag. If a future title update or
  an unexercised online feature turns out to need it, the v0.2.0 source has it.

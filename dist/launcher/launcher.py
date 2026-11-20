#!/usr/bin/env python3
"""MH3U Revival — unified Windows launcher.

A single-window app that replaces the two setup .bats (`PLAY MH3U ONLINE.bat`
and `HOST_MH3U.bat`) with dead-simple JOIN / HOST buttons for non-technical
friends. STDLIB ONLY (tkinter + urllib + zipfile + json + subprocess + …) so it
freezes to a self-contained `MH3U_Online.exe` with PyInstaller onefile and drops
into the bundle root next to `Cemu_release.exe`.

It ports the .bat behaviour byte-for-byte:
  * JOIN  — game-dump presence check, first-run NEX identity mint / repair into
            account.dat, host-IP prompt persisted to mh3u_server.txt, launch Cemu.
  * HOST  — detect Radmin/Tailscale/local IPs, set MH3U_ADVERTISE, run the server
            (server.exe preferred, `python server.py` fallback), stream its log.

The account-mint, mh3u_server.txt, version-compare and update file-filter logic
all live as PURE FUNCTIONS (no tkinter, no network) so they are unit-testable
headless via `python launcher.py --selftest`.

Run:
    python launcher.py             # GUI
    python launcher.py --selftest  # headless logic self-test (no GUI, no network)
"""
import os
import re
import sys
import json
import hashlib
import secrets
import shutil
import time
import zipfile
import tempfile
import subprocess
import threading
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants shared with the .bats / bundle layout
# ---------------------------------------------------------------------------
APP_TITLE = "MH3U Revival"
GITHUB_REPO = "Matt-Wood-23/mh3u-revival"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"

BUNDLE_ZIP = "MH3U_Online_Bundle.zip"
# Legacy: server.exe now ships INSIDE BUNDLE_ZIP (all-in-one), so there is no
# separate host add-on to download or update. Kept only so the release-JSON
# parser test still exercises multi-asset parsing.
HOST_ZIP = "MH3U_Host_AddOn.zip"

CEMU_EXE = "Cemu_release.exe"
SERVER_EXE = "server.exe"
SERVER_PY = "server.py"
VERSION_FILE = "version.txt"

# paths relative to the bundle root (mirror the .bats exactly)
GAMEDIR_REL = os.path.join("portable", "mlc01", "usr", "title", "00050000", "10118300")
ACTDIR_REL = os.path.join("portable", "mlc01", "usr", "save", "system", "act", "80000001")
SRVFILE_REL = os.path.join("portable", "mh3u_server.txt")
PLACEHOLDER = "PASTE_HOST_IP_HERE"

# The official server list is a small JSON file in the repo, fetched at every start, so
# the server can move or post a news line without a launcher release. The last good copy
# is cached for offline starts. Format: see servers.json in the repo root.
SERVERS_URL = (os.environ.get("MH3U_SERVERS_URL", "").strip()     # testing: another list
               or f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/servers.json")
SERVERS_CACHE_REL = os.path.join("portable", "mh3u_servers_cache.json")
# The player's Join choice (official server or a friend's IP). User state.
LAUNCHER_SETTINGS_REL = os.path.join("portable", "mh3u_launcher.json")
# Official event quests: a list in the repo (events/events.json + the .quest files next to
# it) that the launcher copies into the player's event quest packs before starting Cemu.
EVENTS_BASE = (os.environ.get("MH3U_EVENTS_BASE", "").strip().rstrip("/")   # testing
               or f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/events")
EVENTS_CACHE_REL = os.path.join("portable", "mh3u_events_cache")
EVENTS_STATE_REL = os.path.join("portable", "mh3u_events_state.json")
STATUS_POLL_SECONDS = 60

# stock default Mii — cosmetic only, identical to the .bat's MIID / MIIN
DEFAULT_MII = ("010001100000d73e030034330100010001000100010001000100640065006600610075"
               "006c0074000000000000000100010001000100010001000106010001000100010001"
               "000100010001000100010001000100010001000100010001000100")
DEFAULT_MIINAME = "00640065006600610075006c00740000000000000000"  # "default" UTF-16LE

# the substring that marks a *valid online* account (vs a blank offline Cemu one)
ACCT_VALID_MARKER = "IsPasswordCacheEnabled=1"

# Paths (relative to bundle root) the updater must NEVER overwrite — user state.
# NB: `version.txt` is intentionally NOT here; it is rewritten LAST after success.
PROTECTED_PREFIXES = (
    SRVFILE_REL,                                                      # host IP the user typed
    LAUNCHER_SETTINGS_REL,                                            # official vs friend choice
    EVENTS_STATE_REL,                                                 # which quest slots are ours
    os.path.join("portable", "mlc01", "usr", "save"),                # account.dat + game saves
    os.path.join("portable", "mlc01", "usr", "title"),               # the user's game dump
)


# ===========================================================================
# PURE LOGIC  (no tkinter, no network) — unit-testable via --selftest
# ===========================================================================

def _norm(p):
    """Normalise a zip-member / relative path to forward-slash, no leading slash."""
    return p.replace("\\", "/").lstrip("/")


def is_protected_path(rel_path):
    """True if `rel_path` (relative to bundle root) is user state the updater
    must never overwrite. Matches on path-segment boundaries so a sibling like
    `portable/mlc01/usr/savedata` is NOT falsely protected by `.../save`."""
    rel = _norm(rel_path)
    for prot in PROTECTED_PREFIXES:
        prot_n = _norm(prot)
        if rel == prot_n or rel.startswith(prot_n + "/"):
            return True
    return False


def plan_overwrite(zip_members):
    """Given the member list of an update zip, return the subset that should be
    written (i.e. everything that is NOT a directory entry and NOT protected).
    Pure — takes/returns plain strings so it is trivially testable."""
    out = []
    for m in zip_members:
        if m.endswith("/"):
            continue                       # directory entry
        if is_protected_path(m):
            continue                       # user state — never touch
        out.append(m)
    return out


def make_pid():
    """Random NEX PID matching the .bat's :randpid — 8 hex chars, high nibble
    4/5/6 -> range 0x40000000-0x6fffffff. Returns (pid_int, pid_hex_str)."""
    hi = secrets.choice("456")
    rest = "".join(secrets.choice("0123456789abcdef") for _ in range(7))
    hx = hi + rest
    return int(hx, 16), hx


def account_dat_text(pid_hex, tib=None, uuid=None, apc=None):
    """Build the exact account.dat body the .bat writes, given a lowercase 8-hex
    PID string. Random TransferableIdBase/Uuid/AccountPasswordCache unless pinned
    (pinning is only for the selftest). LF line endings, trailing newline —
    byte-identical to `>>` echo output run through normal Windows text.

    AccountId = CemuMH3U<last 4 of PID> (the .bat uses `%PID:~-4%`)."""
    tib = tib if tib is not None else secrets.token_hex(8)     # 16 hex
    uuid = uuid if uuid is not None else secrets.token_hex(16)  # 32 hex
    apc = apc if apc is not None else secrets.token_hex(32)     # 64 hex
    last4 = pid_hex[-4:]
    lines = [
        "AccountInstance_20120705",
        "PersistentId=80000001",
        f"TransferableIdBase={tib}",
        f"Uuid={uuid}",
        f"MiiData={DEFAULT_MII}",
        f"MiiName={DEFAULT_MIINAME}",
        f"AccountId=CemuMH3U{last4}",
        "BirthYear=0",
        "BirthMonth=0",
        "BirthDay=0",
        "Gender=0",
        "EmailAddress=",
        "Country=0",
        "SimpleAddressId=0",
        f"PrincipalId={pid_hex}",
        "IsPasswordCacheEnabled=1",
        f"AccountPasswordCache={apc}",
    ]
    return "\n".join(lines) + "\n"


def account_needs_mint(acct_path):
    """Return 'new' (missing), 'repair' (exists but blank offline account — no
    valid-online marker), or None (valid, leave alone). Mirrors the .bat's
    findstr /c: substring test — a substring test, NOT whole-line, so LF-only
    files (make_account.py output) still match."""
    p = Path(acct_path)
    if not p.exists():
        return "new"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "repair"
    if ACCT_VALID_MARKER in text:
        return None
    return "repair"


def write_account(act_dir, pid_hex=None):
    """Mint a fresh account.dat into `act_dir`. Returns (path, pid_int, pid_hex).
    Does NOT do the repair-backup move — the caller handles that so the pure
    write stays reusable."""
    if pid_hex is None:
        _, pid_hex = make_pid()
    pid_int = int(pid_hex, 16)
    os.makedirs(act_dir, exist_ok=True)
    path = os.path.join(act_dir, "account.dat")
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write(account_dat_text(pid_hex))
    return path, pid_int, pid_hex


def read_host_ip(srvfile_path):
    """Read the persisted host IP; return "" if unset or still the placeholder."""
    p = Path(srvfile_path)
    if not p.exists():
        return ""
    val = p.read_text(encoding="utf-8", errors="replace").splitlines()
    val = val[0].strip() if val else ""
    if not val or val == PLACEHOLDER:
        return ""
    return val


def write_host_ip(srvfile_path, ip):
    """Persist the host IP one-per-line, LF, matching the .bat's `> file echo`."""
    p = Path(srvfile_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="\n", encoding="utf-8") as f:
        f.write(f"{ip.strip()}\n")


_VER_NUM_RE = re.compile(r"\d+")


def _ver_key(tag):
    """Numeric tuple key for a version string like 'v0.1.10-beta' -> (0,1,10).
    Non-numeric suffixes (-beta) are dropped for the *ordering* compare. Empty /
    unknown -> None (so it never wins a 'newer' check)."""
    if not tag:
        return None
    t = tag.strip()
    if t.lower() in ("unknown", "unknown version", ""):
        return None
    nums = _VER_NUM_RE.findall(t)
    if not nums:
        return None
    return tuple(int(n) for n in nums)


def is_newer(remote_tag, local_tag):
    """True if `remote_tag` is a strictly newer release than `local_tag`.

    * Numeric-part comparison so v0.1.10-beta > v0.1.7-beta (string compare would
      wrongly say '10' < '7').
    * Unknown / missing local version -> treat remote as newer (offer update)
      ONLY if remote parses; a dev/local build that doesn't parse never downgrades.
    * If tags are numerically equal, fall back to raw string inequality so a
      genuinely different tag (rebuild) can still be flagged — but equal strings
      are never 'newer'."""
    rk = _ver_key(remote_tag)
    if rk is None:
        return False                        # can't parse remote — never claim newer
    lk = _ver_key(local_tag)
    if lk is None:
        return True                         # unknown local, valid remote -> offer it
    # pad to equal length for tuple compare
    n = max(len(rk), len(lk))
    rk_p = rk + (0,) * (n - len(rk))
    lk_p = lk + (0,) * (n - len(lk))
    if rk_p > lk_p:
        return True
    if rk_p < lk_p:
        return False
    return False                            # numerically equal -> not newer


def read_version(bundle_root):
    """Read version.txt next to the launcher; 'unknown' if missing/empty."""
    p = Path(bundle_root) / VERSION_FILE
    if not p.exists():
        return "unknown"
    v = p.read_text(encoding="utf-8", errors="replace").strip()
    return v or "unknown"


def write_version(bundle_root, tag):
    """Rewrite version.txt LAST after a successful update."""
    p = Path(bundle_root) / VERSION_FILE
    with open(p, "w", newline="\n", encoding="utf-8") as f:
        f.write(f"{tag.strip()}\n")


def parse_latest_release(api_json_bytes):
    """Parse the GitHub latest-release JSON into (tag, {asset_name: url}).
    Pure — takes the raw bytes so it is testable without network."""
    data = json.loads(api_json_bytes)
    tag = data.get("tag_name", "")
    assets = {}
    for a in data.get("assets", []):
        name = a.get("name")
        url = a.get("browser_download_url")
        if name and url:
            assets[name] = url
    return tag, assets


# ---------------------------------------------------------------------------
# Official servers (servers.json) and the Join choice
# ---------------------------------------------------------------------------

_HOST_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
EMPTY_SERVERS = {"news": "", "servers": []}


def parse_servers(raw):
    """servers.json (bytes or str) -> {"news": str, "servers": [{id, name, host,
    status_port}]}. Entries without an id or a plain host name / IPv4 are dropped (the
    host is used to build a URL, so nothing else gets through). Not JSON -> ValueError."""
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("servers.json is not a JSON object")
    servers, seen = [], set()
    for s in data.get("servers") or []:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("id") or "").strip()
        host = str(s.get("host") or "").strip()
        if not sid or sid in seen or not _HOST_RE.match(host):
            continue
        seen.add(sid)
        try:
            port = int(s.get("status_port") or 0)
        except (TypeError, ValueError):
            port = 0
        servers.append({
            "id": sid,
            "name": str(s.get("name") or host).strip(),
            "host": host,
            "status_port": port if 0 < port < 65536 else 0,
        })
    news = data.get("news")
    return {"news": news.strip() if isinstance(news, str) else "", "servers": servers}


def load_servers(root, fetch=True, timeout=8):
    """The official server list: fetched live (and cached), else the cached copy, else
    none. Returns (data, source) with source "live", "cache" or "none"."""
    cache = Path(root) / SERVERS_CACHE_REL
    if fetch:
        try:
            req = urllib.request.Request(SERVERS_URL, headers={
                "User-Agent": "MH3U-Revival-Launcher", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read(256 * 1024)
            data = parse_servers(raw)
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(raw)
            except OSError:
                pass
            return data, "live"
        except Exception:
            pass
    try:
        return parse_servers(cache.read_bytes()), "cache"
    except Exception:
        return dict(EMPTY_SERVERS), "none"


def resolve_host(host):
    """A server's host name -> IPv4 string (an IPv4 is returned as is). Cemu's
    mh3u_server.txt takes an IP, so the launcher looks the name up at every launch and a
    moved server needs no change on the player's side. Raises OSError on failure."""
    import socket
    host = host.strip()
    if _IPV4_RE.match(host):
        return host
    infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_DGRAM)
    if not infos:
        raise OSError(f"no IPv4 address for {host}")
    return infos[0][4][0]


def fetch_status(host, port, timeout=4):
    """GET the server's status page (status_http.py) -> dict."""
    req = urllib.request.Request(f"http://{host}:{port}/status",
                                 headers={"User-Agent": "MH3U-Revival-Launcher"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read(64 * 1024))
    if not isinstance(data, dict):
        raise ValueError("status is not a JSON object")
    return data


NATCHECK_PORT = 10025


def natcheck_probe(ip, port=NATCHECK_PORT, timeout=2.0, tries=3):
    """Ask the server's NAT-check responder (natcheck.py) "what's my address?" over UDP,
    the first thing the game does online. Returns (True, "a.b.c.d:port" as the server
    sees us) or (False, reason). Same packet as tests/extkit/check_natcheck.py."""
    import socket
    import struct
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    reason = "no answer"
    try:
        for _ in range(tries):
            try:
                s.sendto(struct.pack(">IIII", 0x65, 0, 0, 0), (ip, port))
                data, _addr = s.recvfrom(64)
            except socket.timeout:
                continue
            except ConnectionResetError:
                # Windows reports an ICMP "port unreachable" this way: the machine is
                # there, but nothing listens on that port.
                reason = "port closed (the server isn't running)"
                continue
            except OSError as e:
                return False, str(e)
            if len(data) >= 16:
                _t, seen_port, seen_ip, _srv = struct.unpack(">IIII", data[:16])
                return True, f"{socket.inet_ntoa(struct.pack('>I', seen_ip))}:{seen_port}"
            reason = f"unexpected {len(data)}-byte reply"
    finally:
        s.close()
    return False, reason


def format_status(snap):
    """Status dict -> one short line, e.g. "12 hunters online · 3 rooms"."""
    try:
        p = int(snap.get("players", 0))
        r = int(snap.get("rooms", 0))
    except (TypeError, ValueError):
        return "status unreadable"
    hunters = "1 hunter" if p == 1 else f"{p} hunters"
    rooms = "1 room" if r == 1 else f"{r} rooms"
    return f"{hunters} online · {rooms}"


# ---------------------------------------------------------------------------
# Official event quests
#
# The game keeps event quests in four "packs" in the save folder (quest1..quest4, 20 slots
# each; quest4 is where Challenge Quests are read from). The launcher puts the official
# event quests into free slots of quest3, then quest2, then quest1, and remembers a
# fingerprint of every slot it wrote. It only ever changes or clears a slot that still
# matches that fingerprint, so quests a player added themselves are never touched. Each
# pack is backed up once (questN.revival_backup) before the launcher first changes it.
#
# The quest number sets the rank the game lists it under: 201xx low, 202xx high, 203xx G
# rank. The official ones use the top half of each block, clear of Capcom's own event
# quests (20102-20104, 20201-20210, 20302-20324).
# ---------------------------------------------------------------------------
EVENT_NO_RANGES = ((20150, 20199), (20250, 20299), (20350, 20399))   # low, high, G rank


def event_number_ok(no):
    return any(lo <= no <= hi for lo, hi in EVENT_NO_RANGES)


EVENT_NO_TEXT = ", ".join(f"{lo}-{hi}" for lo, hi in EVENT_NO_RANGES)
EVENT_PACKS = ("quest3", "quest2", "quest1")
EVENT_TITLES = ("10118300", "10117200")          # US, EU (the JP game's quests differ)
PACK_HEADER, PACK_SLOT, PACK_DATA, PACK_NAME, PACK_SLOTS = 0x28, 0x2010, 0x2000, 16, 20


def quest_record_no(rec):
    """Quest number of a QTDS quest record, or None if it isn't one we can read."""
    try:
        if rec[:4] != b"QTDS" or int.from_bytes(rec[4:8], "little") != 5:
            return None
        pos = 8
        for _ in range(5):                       # the quest name, in 5 languages
            pos += 4 + int.from_bytes(rec[pos:pos + 4], "little")
        if pos + 2 > len(rec):
            return None
        return int.from_bytes(rec[pos:pos + 2], "little")
    except (TypeError, IndexError):
        return None


def parse_events(raw):
    """events.json -> [{"file", "sha256"}]. Entries that aren't a plain q_NNNNN.quest
    file name with a sha256 are dropped."""
    data = json.loads(raw)
    out = []
    for q in data.get("quests", []) if isinstance(data, dict) else []:
        if not isinstance(q, dict):
            continue
        f, h = q.get("file"), q.get("sha256")
        if (isinstance(f, str) and re.fullmatch(r"q_\d{5}\.quest", f)
                and isinstance(h, str) and re.fullmatch(r"[0-9a-f]{64}", h.lower())):
            out.append({"file": f, "sha256": h.lower()})
    return out


def check_event_record(name, rec, sha256):
    """The record if it's a valid official event quest matching its listed hash, else
    raise ValueError saying why."""
    if hashlib.sha256(rec).hexdigest() != sha256:
        raise ValueError(f"{name}: checksum doesn't match the list")
    no = quest_record_no(rec)
    if no is None:
        raise ValueError(f"{name}: not a quest file")
    if not event_number_ok(no) or name != f"q_{no:05d}.quest":
        raise ValueError(f"{name}: quest number {no} is outside {EVENT_NO_TEXT}")
    body = rec.rstrip(b"\0")
    if len(body) > PACK_DATA:
        raise ValueError(f"{name}: too big for a quest slot")
    return body


def load_event_quests(root, fetch=True, timeout=8, log=print):
    """{quest number: record} for the official event quests: downloaded (and cached), or
    the cached copies when offline. None if there is no list at all yet."""
    cache = Path(root) / EVENTS_CACHE_REL
    listing = None
    if fetch:
        try:
            req = urllib.request.Request(EVENTS_BASE + "/events.json", headers={
                "User-Agent": "MH3U-Revival-Launcher", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read(256 * 1024)
            listing = parse_events(raw)
            cache.mkdir(parents=True, exist_ok=True)
            (cache / "events.json").write_bytes(raw)
        except Exception as e:
            log(f"[Events] Couldn't get the event quest list ({e}); using the saved copy.")
    if listing is None:
        try:
            listing = parse_events((cache / "events.json").read_bytes())
        except (OSError, ValueError):
            return None
    quests = {}
    for q in listing:
        path = cache / q["file"]
        rec = path.read_bytes() if path.exists() else b""
        if hashlib.sha256(rec).hexdigest() != q["sha256"] and fetch:
            try:
                with urllib.request.urlopen(EVENTS_BASE + "/" + q["file"], timeout=timeout) as r:
                    rec = r.read(PACK_DATA + 1)
            except Exception as e:
                log(f"[Events] Couldn't download {q['file']} ({e}).")
                continue
        try:
            body = check_event_record(q["file"], rec, q["sha256"])
        except ValueError as e:
            log(f"[Events] Skipped {e}.")
            continue
        path.write_bytes(rec)
        quests[quest_record_no(body)] = body
    return quests


def event_save_dirs(root):
    """Save folders (US/EU) whose event quest packs exist; the game creates them. Only
    Cemu's own account folders (8 hex digits, e.g. 80000001): a copy someone made next
    to it ("80000001_BACKUP") is left alone."""
    base = Path(root) / "portable" / "mlc01" / "usr" / "save" / "00050000"
    out = []
    for title in EVENT_TITLES:
        users = base / title / "user"
        if users.is_dir():
            out += [d for d in sorted(users.iterdir())
                    if d.is_dir() and re.fullmatch(r"[0-9a-fA-F]{8}", d.name)
                    and all((d / p).is_file() for p in EVENT_PACKS)]
    return out


def _slot(pack, i):
    o = PACK_HEADER + i * PACK_SLOT
    return pack[o:o + PACK_SLOT]


def _slot_record(rec, no):
    name = f"q_{no:05d}.quest".encode("ascii")
    return rec + bytes(PACK_DATA - len(rec)) + name + bytes(PACK_NAME - len(name))


def sync_event_packs(save_dir, quests, owned):
    """Bring one save folder's packs in line with `quests` ({number: record}).
    `owned` ({"quest3/0": {"no", "sha256"}}) says which slots the launcher wrote; it's
    updated in place. Returns (added, updated, removed, notes)."""
    save_dir = Path(save_dir)
    packs = {}
    for name in EVENT_PACKS:
        data = bytearray((save_dir / name).read_bytes())
        if len(data) < PACK_HEADER + PACK_SLOTS * PACK_SLOT:
            return 0, 0, 0, [f"{name} looks damaged; left alone"]
        packs[name] = data
    notes = []
    added = updated = removed = 0
    # Forget slots that no longer hold exactly what we wrote (the player changed them).
    for key, info in list(owned.items()):
        name, _, idx = key.partition("/")
        if (name not in packs or not idx.isdigit() or int(idx) >= PACK_SLOTS
                or hashlib.sha256(_slot(packs[name], int(idx))).hexdigest() != info.get("sha256")):
            del owned[key]
    placed = set()
    for key, info in list(owned.items()):
        name, _, idx = key.partition("/")
        o = PACK_HEADER + int(idx) * PACK_SLOT
        no = info.get("no")
        if no not in quests or no in placed:          # event over (or a duplicate)
            packs[name][o:o + PACK_SLOT] = bytes(PACK_SLOT)
            del owned[key]
            removed += 1
            continue
        new = _slot_record(quests[no], no)
        if bytes(packs[name][o:o + PACK_SLOT]) != new:
            packs[name][o:o + PACK_SLOT] = new
            info["sha256"] = hashlib.sha256(new).hexdigest()
            updated += 1
        placed.add(no)
    # Quest numbers already in the packs that aren't ours (the player added them).
    theirs = set()
    for name, data in packs.items():
        for i in range(PACK_SLOTS):
            key = f"{name}/{i}"
            if key not in owned and _slot(data, i)[:4] == b"QTDS":
                theirs.add(quest_record_no(_slot(data, i)))
    for no in sorted(set(quests) - placed):
        if no in theirs:
            notes.append(f"quest {no} is already in your packs (not added by the launcher); left alone")
            continue
        free = next(((n, i) for n in EVENT_PACKS for i in range(PACK_SLOTS)
                     if f"{n}/{i}" not in owned and not any(_slot(packs[n], i))), None)
        if free is None:
            notes.append(f"no free event quest slot for quest {no}")
            continue
        name, i = free
        new = _slot_record(quests[no], no)
        o = PACK_HEADER + i * PACK_SLOT
        packs[name][o:o + PACK_SLOT] = new
        owned[f"{name}/{i}"] = {"no": no, "sha256": hashlib.sha256(new).hexdigest()}
        added += 1
    for name in EVENT_PACKS:
        path = save_dir / name
        if bytes(packs[name]) == path.read_bytes():
            continue
        bak = save_dir / (name + ".revival_backup")
        if not bak.exists():
            shutil.copy2(path, bak)
        tmp = save_dir / (name + ".revival_tmp")
        tmp.write_bytes(bytes(packs[name]))
        os.replace(tmp, path)
    return added, updated, removed, notes


def install_event_quests(root, log=print, fetch=True):
    """Download the official event quests and put them into every US/EU save in this
    bundle. Never runs while Cemu is open (the game would overwrite the packs)."""
    root = Path(root)
    if is_running(CEMU_EXE):
        log("[Events] Cemu is open; close it to update the event quests.")
        return
    saves = event_save_dirs(root)
    if not saves:
        return              # no save yet: the game creates the packs on its first save
    quests = load_event_quests(root, fetch=fetch, log=log)
    if quests is None:
        return
    state_path = root / EVENTS_STATE_REL
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    if not isinstance(state, dict):
        state = {}
    for save in saves:
        key = str(save.relative_to(root)).replace("\\", "/")
        owned = state.setdefault(key, {})
        try:
            added, updated, removed, notes = sync_event_packs(save, quests, owned)
        except OSError as e:
            log(f"[Events] Couldn't update the event quests in {key} ({e}).")
            continue
        for n in notes:
            log(f"[Events] Note: {n}.")
        if added or updated or removed:
            log(f"[Events] Event quests in save {save.name}: {added} added, {updated} updated, "
                f"{removed} removed ({len(owned)} installed).")
    try:
        state_path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    except OSError:
        pass


def read_launcher_settings(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_launcher_settings(path, settings):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="\n", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")


def initial_join_choice(settings, saved_ip, servers):
    """What the Join tab preselects: "official:<id>" or "custom".

    An explicit earlier choice wins. An install that already has a friend's IP saved
    from before the official server existed stays on it (we don't move people silently).
    Everyone else starts on the first official server, when there is one."""
    ids = [s["id"] for s in servers]
    mode = settings.get("join_mode")
    if mode == "official":
        sid = settings.get("server_id")
        if sid in ids:
            return f"official:{sid}"
        return f"official:{ids[0]}" if ids else "custom"
    if mode == "custom" or saved_ip:
        return "custom"
    return f"official:{ids[0]}" if ids else "custom"


# ---------------------------------------------------------------------------
# IP detection (pure Python where possible; subprocess for tailscale)
# ---------------------------------------------------------------------------

def _run(cmd, timeout=6):
    """Run a command hidden (no console flash), return stdout text or ''."""
    try:
        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            creationflags=flags,
        )
        return (out.stdout or "").strip()
    except Exception:
        return ""


def detect_radmin_ip():
    """Radmin VPN address = a local IPv4 starting '26.' — same as the .bat's
    PowerShell Get-NetIPAddress filter, but done in pure Python via socket."""
    import socket
    candidates = set()
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            candidates.add(info[4][0])
    except Exception:
        pass
    # also try the all-interfaces enumeration Windows exposes via gethostbyname_ex
    try:
        _, _, addrs = socket.gethostbyname_ex(socket.gethostname())
        candidates.update(addrs)
    except Exception:
        pass
    for ip in sorted(candidates):
        if ip.startswith("26."):
            return ip
    return None


def detect_tailscale_ip():
    """Tailscale 100.x via `tailscale ip -4`, with the ProgramFiles fallback the
    .bat uses when tailscale isn't on PATH."""
    out = _run(["tailscale", "ip", "-4"])
    if out:
        return out.splitlines()[0].strip()
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    exe = os.path.join(pf, "Tailscale", "tailscale.exe")
    if os.path.exists(exe):
        out = _run([exe, "ip", "-4"])
        if out:
            return out.splitlines()[0].strip()
    return None


def detect_local_ip():
    """Best-guess LAN IPv4 (the address that routes to the internet)."""
    import socket
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        if s:
            s.close()


def host_ip_choices():
    """Return an ordered list of (label, ip) host-IP options, preselect priority
    matching the .bat: Radmin > Tailscale > LAN. Radmin/Tailscale only appear
    when detected. Loopback is NOT offered as a normal choice — advertising
    127.0.0.1 only works for two Cemu instances on the same PC and breaks P2P
    for friends (the server publishes loopback as your peer address). It's kept
    only as a last-resort fallback so the picker is never empty; users who want
    a specific address can still type it in the override box."""
    choices = []
    rv = detect_radmin_ip()
    ts = detect_tailscale_ip()
    lan = detect_local_ip()
    if rv:
        choices.append((f"Radmin VPN — {rv}", rv))
    if ts:
        choices.append((f"Tailscale — {ts}", ts))
    if lan and lan != "127.0.0.1":
        choices.append((f"LAN — {lan}", lan))
    if not choices:
        # No routable address detected — degenerate fallback (same-PC only).
        choices.append(("This PC only — 127.0.0.1", "127.0.0.1"))
    return choices


# ---------------------------------------------------------------------------
# Process helpers
# ---------------------------------------------------------------------------

def is_running(exe_name):
    """True if a process named exe_name is running (Windows tasklist)."""
    if os.name != "nt":
        return False
    out = _run(["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/NH"], timeout=8)
    return exe_name.lower() in out.lower()


def bundle_root():
    """The directory the launcher lives in — frozen exe dir, or this file's dir."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# ===========================================================================
# JOIN flow (ported from PLAY MH3U ONLINE.bat) — returns log lines
# ===========================================================================

def run_join_flow(root, host_ip, launch=True, log=print, host_label=None):
    """Execute the full join flow against bundle `root`.

      1. game-dump presence check (guidance if missing)
      2. mint OR repair account.dat (identical format + repair semantics)
      3. write host IP to mh3u_server.txt
      4. launch Cemu_release.exe (unless launch=False or MH3U_NOLAUNCH=1)

    `log` is a callable taking one string (so the GUI can stream it). Returns
    True on success (Cemu launched or launch suppressed)."""
    root = Path(root)

    # 1) game-dump presence check
    gamedir = root / GAMEDIR_REL
    if not (gamedir / "code").exists():
        log("[MH3U Online] No MH3U game found in this bundle yet.")
        log("  Cemu will still open, but its game list stays empty until you add")
        log("  YOUR own legal MH3U dump. Two ways:")
        log(f"    1) copy your dump's code/content/meta folders into:")
        log(f"         {gamedir}")
        log("    2) or in Cemu: Options > General Settings > Game Paths > add its folder")

    # 2) account mint / repair
    act_dir = root / ACTDIR_REL
    acct = act_dir / "account.dat"
    need = account_needs_mint(acct)
    if need == "repair":
        # move the blank offline account aside, exactly like the .bat
        try:
            bak = acct.with_suffix(".dat.offline.bak")
            if bak.exists():
                bak.unlink()
            acct.replace(bak)
        except OSError:
            pass
        log("[MH3U Online] Your Cemu account has no online identity yet — setting one up...")
    elif need == "new":
        log("[MH3U Online] First run — creating your unique online identity...")
    if need:
        path, pid_int, pid_hex = write_account(str(act_dir))
        log(f"[MH3U Online] Identity ready (NEX PID {pid_int}).")

    # 3) persist host IP
    ip = (host_ip or "").strip()
    if ip and ip != PLACEHOLDER:
        write_host_ip(root / SRVFILE_REL, ip)
        log(f"[MH3U Online] Saved host = {host_label or ip}")
    else:
        log("[MH3U Online] WARNING: no host IP set — enter the host's IP and Save first.")

    # 4) launch Cemu
    if not launch or os.environ.get("MH3U_NOLAUNCH") == "1":
        log("[MH3U Online] (launch suppressed)")
        return True
    cemu = root / CEMU_EXE
    if not cemu.exists():
        log(f"[MH3U Online] ERROR: {CEMU_EXE} not found next to the launcher.")
        return False
    log(f"[MH3U Online] Host = {ip} — launching Cemu...")
    try:
        subprocess.Popen([str(cemu)], cwd=str(root))
    except OSError as e:
        log(f"[MH3U Online] ERROR launching Cemu: {e}")
        return False
    return True


# ===========================================================================
# HOST flow helpers
# ===========================================================================

def server_available(root):
    """Return 'exe', 'py', or None depending on what host backend is present."""
    root = Path(root)
    if (root / SERVER_EXE).exists():
        return "exe"
    if (root / SERVER_PY).exists():
        return "py"
    return None


def build_server_command(root):
    """Command list + kind for starting the server. server.exe preferred, then
    `python server.py` (or `py server.py`) fallback for source checkouts."""
    root = Path(root)
    if (root / SERVER_EXE).exists():
        return [str(root / SERVER_EXE)], "exe"
    if (root / SERVER_PY).exists():
        py = sys.executable or "python"
        return [py, str(root / SERVER_PY)], "py"
    return None, None


# ===========================================================================
# UPDATER (pure-ish; download/extract separated from GUI)
# ===========================================================================

def fetch_latest_release(timeout=10):
    """GET the GitHub latest-release API. Returns (tag, assets_dict) or raises."""
    req = urllib.request.Request(
        RELEASES_API, headers={"Accept": "application/vnd.github+json",
                               "User-Agent": "MH3U-Revival-Launcher"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return parse_latest_release(r.read())


def download_file(url, dest, progress=None, timeout=60):
    """Download `url` to `dest`, calling progress(fraction 0..1) as it goes."""
    req = urllib.request.Request(url, headers={"User-Agent": "MH3U-Revival-Launcher"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        total = int(r.headers.get("Content-Length", 0) or 0)
        got = 0
        chunk = 1024 * 128
        with open(dest, "wb") as f:
            while True:
                buf = r.read(chunk)
                if not buf:
                    break
                f.write(buf)
                got += len(buf)
                if progress and total:
                    progress(min(1.0, got / total))
    if progress:
        progress(1.0)


def apply_update_zip(zip_path, root, log=print):
    """Extract an update zip over `root`, skipping protected user-state paths and
    the running launcher exe (which can't overwrite itself). Returns the path of
    the extracted-but-deferred launcher exe (as MH3U_Online.exe.new) or None."""
    root = Path(root)
    deferred_launcher = None
    launcher_name = os.path.basename(sys.executable) if getattr(sys, "frozen", False) else "MH3U_Online.exe"
    with zipfile.ZipFile(zip_path) as zf:
        members = zf.namelist()
        for m in plan_overwrite(members):
            target = root / _norm(m)
            # the running exe: stage as .new and let a helper .bat swap it post-exit
            if _norm(m).lower() == launcher_name.lower():
                new_path = root / (launcher_name + ".new")
                with zf.open(m) as src, open(new_path, "wb") as dst:
                    dst.write(src.read())
                deferred_launcher = new_path
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with zf.open(m) as src, open(target, "wb") as dst:
                    dst.write(src.read())
            except PermissionError:
                log(f"  skip (in use): {m}")
    return deferred_launcher


def write_self_replace_bat(root, launcher_name):
    """Write replace.bat that waits for this exe to exit, swaps in the .new
    build, relaunches it, then deletes itself. Returns the .bat path."""
    root = Path(root)
    bat = root / "_mh3u_update_replace.bat"
    old = launcher_name
    new = launcher_name + ".new"
    content = (
        "@echo off\r\n"
        "rem auto-generated by MH3U launcher self-update; safe to delete\r\n"
        f'cd /d "{root}"\r\n'
        ":wait\r\n"
        "ping -n 2 127.0.0.1 >nul\r\n"
        f'tasklist /FI "IMAGENAME eq {old}" /NH 2>nul | find /I "{old}" >nul && goto wait\r\n'
        f'del /q "{old}" >nul 2>nul\r\n'
        f'ren "{new}" "{old}" >nul 2>nul\r\n'
        # Let Defender finish its on-write scan of the just-renamed exe before we
        # launch it. A freshly-written PyInstaller ONEFILE exe that runs instantly
        # can lose the _MEI python3xx.dll extraction race to the AV first-run scan
        # and pop "Failed to load Python DLL ... LoadLibrary: module not found".
        # A short settle makes the relaunch reliable (a second launch always worked).
        "ping -n 4 127.0.0.1 >nul\r\n"
        f'start "" "{old}"\r\n'
        '(goto) 2>nul & del "%~f0"\r\n'
    )
    with open(bat, "w", newline="") as f:
        f.write(content)
    return bat


# ===========================================================================
# SELF-TEST  (headless, no GUI, no network)
# ===========================================================================

def _selftest():
    import tempfile
    import shutil
    ok = True

    def check(cond, msg):
        nonlocal ok
        status = "PASS" if cond else "FAIL"
        if not cond:
            ok = False
        print(f"  [{status}] {msg}")

    print("== account.dat mint format ==")
    pid_int, pid_hex = make_pid()
    check(len(pid_hex) == 8, f"PID hex is 8 chars ({pid_hex})")
    check(pid_hex[0] in "456", f"PID high nibble in 4/5/6 ({pid_hex[0]})")
    check(0x40000000 <= pid_int <= 0x6fffffff, f"PID in range 0x40000000-0x6fffffff ({pid_int:#x})")

    text = account_dat_text(pid_hex)
    required_keys = [
        "AccountInstance_20120705", "PersistentId=80000001",
        "TransferableIdBase=", "Uuid=", "MiiData=", "MiiName=",
        "AccountId=CemuMH3U", "BirthYear=0", "PrincipalId=",
        "IsPasswordCacheEnabled=1", "AccountPasswordCache=",
    ]
    for k in required_keys:
        check(k in text, f"account.dat contains {k!r}")
    check(text.endswith("\n") and "\r" not in text, "account.dat is LF-only with trailing newline")
    check(f"PrincipalId={pid_hex}" in text, "PrincipalId matches minted PID hex")
    check(f"AccountId=CemuMH3U{pid_hex[-4:]}" in text, "AccountId uses last 4 hex of PID")
    # hex field lengths
    m = re.search(r"^TransferableIdBase=([0-9a-f]+)$", text, re.M)
    check(bool(m) and len(m.group(1)) == 16, "TransferableIdBase is 16 hex chars")
    m = re.search(r"^Uuid=([0-9a-f]+)$", text, re.M)
    check(bool(m) and len(m.group(1)) == 32, "Uuid is 32 hex chars")
    m = re.search(r"^AccountPasswordCache=([0-9a-f]+)$", text, re.M)
    check(bool(m) and len(m.group(1)) == 64, "AccountPasswordCache is 64 hex chars")

    print("== account repair-detection ==")
    tmp = Path(tempfile.mkdtemp(prefix="mh3u_selftest_"))
    try:
        act = tmp / "act"
        act.mkdir()
        acct = act / "account.dat"

        # missing -> 'new'
        check(account_needs_mint(acct) == "new", "missing account.dat -> 'new'")

        # blank offline account (no marker) -> 'repair'
        acct.write_text("AccountInstance_20120705\nPersistentId=80000001\nPrincipalId=0\n",
                        encoding="utf-8", newline="\n")
        check(account_needs_mint(acct) == "repair", "blank offline account -> 'repair'")

        # valid LF-only file (make_account.py style) -> None (no re-mint)
        write_account(str(act), pid_hex=pid_hex)
        check(account_needs_mint(acct) is None, "valid LF-only account -> None (no spurious re-mint)")
        # confirm the on-disk file has the marker and no CR
        disk = acct.read_text(encoding="utf-8")
        check(ACCT_VALID_MARKER in disk, "written account has IsPasswordCacheEnabled=1")
        check("\r" not in disk, "written account is CRLF-free")

        print("== mh3u_server.txt read/write ==")
        srv = tmp / "portable" / "mh3u_server.txt"
        check(read_host_ip(srv) == "", "missing srvfile -> ''")
        write_host_ip(srv, "26.1.2.3")
        check(read_host_ip(srv) == "26.1.2.3", "round-trip host IP")
        raw = srv.read_text(encoding="utf-8")
        check(raw == "26.1.2.3\n", "srvfile is 'ip\\n' LF-only")
        write_host_ip(srv, PLACEHOLDER)
        check(read_host_ip(srv) == "", "placeholder reads back as ''")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("== version comparison ==")
    check(is_newer("v0.1.10-beta", "v0.1.7-beta"), "v0.1.10-beta > v0.1.7-beta (numeric)")
    check(not is_newer("v0.1.7-beta", "v0.1.10-beta"), "v0.1.7-beta is NOT newer than v0.1.10-beta")
    check(not is_newer("v0.1.7-beta", "v0.1.7-beta"), "equal tags are not newer")
    check(is_newer("v0.1.7-beta", "unknown"), "valid remote beats 'unknown' local")
    check(is_newer("v0.1.7-beta", ""), "valid remote beats missing local")
    check(not is_newer("unknown", "v0.1.7-beta"), "unknown remote never downgrades")
    check(not is_newer("", "v0.1.7-beta"), "empty remote never downgrades")
    check(is_newer("v0.2.0-beta", "v0.1.99-beta"), "minor bump beats larger patch")
    check(not is_newer("v0.1.7", "v0.1.7-beta"), "same numeric (suffix diff) not newer")

    print("== update file-filter (protected paths) ==")
    members = [
        "Cemu_release.exe",
        "If antivirus blocks the launcher - JOIN.bat",
        "MH3U_Online.exe",
        "version.txt",
        "portable/",                                             # dir entry
        "portable/settings.xml",
        "portable/mh3u_server.txt",                              # PROTECTED
        "portable/mlc01/usr/save/system/act/80000001/account.dat",  # PROTECTED
        "portable/mlc01/usr/save/00050000/10118300/user/80000001/game.sav",  # PROTECTED
        "portable/mlc01/usr/title/00050000/10118300/code/x.rpx",  # PROTECTED
        "portable/mlc01/sys/title/0005001b/10054000/content/scerts/COMODO_CA.der",
    ]
    plan = plan_overwrite(members)
    protected = [
        "portable/mh3u_server.txt",
        "portable/mlc01/usr/save/system/act/80000001/account.dat",
        "portable/mlc01/usr/save/00050000/10118300/user/80000001/game.sav",
        "portable/mlc01/usr/title/00050000/10118300/code/x.rpx",
    ]
    for p in protected:
        check(p not in plan, f"protected NOT in overwrite set: {p}")
    for p in ["Cemu_release.exe", "If antivirus blocks the launcher - JOIN.bat", "portable/settings.xml",
              "portable/mlc01/sys/title/0005001b/10054000/content/scerts/COMODO_CA.der"]:
        check(p in plan, f"non-protected IS in overwrite set: {p}")
    check("portable/" not in plan, "directory entry excluded from overwrite set")
    # the sys/ certs must be updatable (they are NOT under usr/save or usr/title)
    check(not is_protected_path("portable/mlc01/sys/title/x"), "sys/ tree is not protected")
    # a lookalike sibling must NOT be falsely protected
    check(not is_protected_path("portable/mlc01/usr/savedata/x"), "usr/savedata is not falsely protected")

    print("== release JSON parse ==")
    fake = json.dumps({
        "tag_name": "v0.1.8-beta",
        "assets": [
            {"name": BUNDLE_ZIP, "browser_download_url": "https://x/bundle.zip"},
            {"name": HOST_ZIP, "browser_download_url": "https://x/host.zip"},
            {"name": "MH3U_Online_Linux.zip", "browser_download_url": "https://x/linux.zip"},
        ],
    }).encode()
    tag, assets = parse_latest_release(fake)
    check(tag == "v0.1.8-beta", "parsed tag")
    check(assets.get(BUNDLE_ZIP) == "https://x/bundle.zip", "parsed bundle asset URL")
    check(HOST_ZIP in assets, "parsed host asset present")

    print("== servers.json parse ==")
    raw = json.dumps({
        "schema": 1,
        "news": "  Maintenance Sunday 18:00 UTC  ",
        "servers": [
            {"id": "us", "name": "Official (US)", "host": "mh3u.example.org", "status_port": 8080},
            {"id": "ip", "host": "203.0.113.7"},
            {"id": "us", "host": "dup.example.org"},                 # duplicate id
            {"id": "bad", "host": "evil.org/x?y"},                   # not a plain host
            {"id": "bad2", "host": "a b"},
            {"host": "no-id.example.org"},
            {"id": "port", "host": "p.example.org", "status_port": "99999"},
            "not a dict",
        ],
    })
    d = parse_servers(raw)
    ids = [x["id"] for x in d["servers"]]
    check(ids == ["us", "ip", "port"], f"valid entries kept, bad/dup dropped ({ids})")
    check(d["news"] == "Maintenance Sunday 18:00 UTC", "news trimmed")
    check(d["servers"][1]["name"] == "203.0.113.7", "name defaults to host")
    check(d["servers"][0]["status_port"] == 8080, "status_port kept")
    check(d["servers"][2]["status_port"] == 0, "out-of-range status_port -> 0")
    check(parse_servers(b'{"servers": null}') == EMPTY_SERVERS, "null server list -> empty")
    for junk in (b"[1,2]", b"not json"):
        try:
            parse_servers(junk)
            check(False, f"rejects {junk!r}")
        except ValueError:
            check(True, f"rejects {junk!r}")
    check(resolve_host(" 203.0.113.7 ") == "203.0.113.7", "IPv4 host needs no lookup")

    print("== NAT-check probe (loopback) ==")
    import socket
    import struct
    resp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    resp.bind(("127.0.0.1", 0))
    rport = resp.getsockname()[1]

    def answer_once():
        data, addr = resp.recvfrom(64)
        ip_u32 = struct.unpack(">I", socket.inet_aton(addr[0]))[0]
        resp.sendto(struct.pack(">IIII", struct.unpack(">I", data[:4])[0], addr[1], ip_u32, 0),
                    addr)
    t = threading.Thread(target=answer_once, daemon=True)
    t.start()
    got, info = natcheck_probe("127.0.0.1", port=rport, timeout=2)
    check(got and info.startswith("127.0.0.1:"), f"probe gets our address back ({info})")
    resp.close()
    got, info = natcheck_probe("127.0.0.1", port=rport, timeout=0.3, tries=1)
    check(not got, f"no responder -> failure ({info})")

    print("== status line ==")
    check(format_status({"players": 12, "rooms": 3}) == "12 hunters online · 3 rooms",
          "plural status line")
    check(format_status({"players": 1, "rooms": 1}) == "1 hunter online · 1 room",
          "singular status line")
    check(format_status({"players": "x"}) == "status unreadable", "junk status handled")

    print("== Join choice ==")
    srv = [{"id": "us"}, {"id": "eu"}]
    check(initial_join_choice({}, "", srv) == "official:us", "fresh install -> official")
    check(initial_join_choice({}, "", []) == "custom", "no official server -> custom")
    check(initial_join_choice({}, "26.1.2.3", srv) == "custom",
          "old install with a friend's IP stays on it")
    check(initial_join_choice({"join_mode": "official", "server_id": "eu"}, "x", srv)
          == "official:eu", "remembered official server")
    check(initial_join_choice({"join_mode": "official", "server_id": "gone"}, "", srv)
          == "official:us", "removed server -> first official")
    check(initial_join_choice({"join_mode": "official"}, "", []) == "custom",
          "official chosen but list empty -> custom")
    check(initial_join_choice({"join_mode": "custom"}, "", srv) == "custom",
          "remembered friend choice")
    check(is_protected_path("portable/mh3u_launcher.json"), "launcher settings are protected")
    check(not is_protected_path("portable/mh3u_servers_cache.json"), "server cache is not")
    tmp = Path(tempfile.mkdtemp(prefix="mh3u_selftest_"))
    try:
        sp = tmp / "portable" / "mh3u_launcher.json"
        check(read_launcher_settings(sp) == {}, "missing settings -> {}")
        write_launcher_settings(sp, {"join_mode": "official", "server_id": "us"})
        check(read_launcher_settings(sp) == {"join_mode": "official", "server_id": "us"},
              "settings round-trip")
        sp.write_text("[]", encoding="utf-8")
        check(read_launcher_settings(sp) == {}, "non-object settings -> {}")
        cache = tmp / SERVERS_CACHE_REL
        check(load_servers(tmp, fetch=False) == (EMPTY_SERVERS, "none"), "no cache -> none")
        cache.write_text(raw, encoding="utf-8")
        data, source = load_servers(tmp, fetch=False)
        check(source == "cache" and len(data["servers"]) == 3, "offline start uses the cache")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- event quests ---
    def qrec(no, filler=b"x" * 40):
        names = b"".join(len(t).to_bytes(4, "little") + t
                         for t in (b"Event", b"Ev", b"Ev", b"Ev", b"Ev"))
        return b"QTDS" + (5).to_bytes(4, "little") + names + no.to_bytes(2, "little") + filler

    def pack(slots=None):
        data = bytearray(b"H" * PACK_HEADER + bytes(PACK_SLOTS * PACK_SLOT) + bytes(0x14))
        for i, (rec, no) in (slots or {}).items():
            o = PACK_HEADER + i * PACK_SLOT
            data[o:o + PACK_SLOT] = _slot_record(rec, no)
        return bytes(data)

    check(quest_record_no(qrec(20350)) == 20350, "quest number read from a record")
    check(quest_record_no(b"NOPE" + bytes(40)) is None, "non-quest -> None")
    good = qrec(20350)
    sha = hashlib.sha256(good).hexdigest()
    ev = parse_events(json.dumps({"quests": [
        {"file": "q_20350.quest", "sha256": sha},
        {"file": "../evil.quest", "sha256": sha},
        {"file": "q_20351.quest"}]}))
    check(ev == [{"file": "q_20350.quest", "sha256": sha}], "event list: unsafe/incomplete dropped")
    check(check_event_record("q_20350.quest", good + bytes(8), hashlib.sha256(good + bytes(8)).hexdigest())
          == good, "valid event record accepted (padding trimmed)")
    for bad, why in ((qrec(20102), "Capcom number"), (qrec(20350), "wrong hash")):
        try:
            check_event_record("q_20350.quest", bad,
                               "0" * 64 if why == "wrong hash" else hashlib.sha256(bad).hexdigest())
            check(False, f"rejects {why}")
        except ValueError:
            check(True, f"rejects {why}")
    check([event_number_ok(n) for n in (20150, 20199, 20250, 20399, 20149, 20200, 20210, 20324)]
          == [True] * 4 + [False] * 4, "low/high/G rank blocks, clear of Capcom's numbers")
    tmp = Path(tempfile.mkdtemp(prefix="mh3u_selftest_"))
    try:
        save = tmp / "portable/mlc01/usr/save/00050000/10118300/user/80000001"
        save.mkdir(parents=True)
        mine = qrec(20301, b"player's own")
        (save / "quest1").write_bytes(pack({0: (mine, 20301)}))
        (save / "quest2").write_bytes(pack())
        (save / "quest3").write_bytes(pack({0: (qrec(20360, b"player-made 20360"), 20360)}))
        (save / "quest4").write_bytes(pack())
        copy = save.with_name("80000001_BACKUP")              # a player's own backup copy
        shutil.copytree(save, copy)
        check(event_save_dirs(tmp) == [save], "finds the US save, skips a backup copy of it")
        shutil.rmtree(copy)
        owned = {}
        a, u, r, notes = sync_event_packs(save, {20350: qrec(20350), 20360: qrec(20360)}, owned)
        q3 = (save / "quest3").read_bytes()
        check((a, u, r) == (1, 0, 0) and any("20360" in n for n in notes),
              "adds new quest, leaves a player's quest with the same number alone")
        check(_slot(q3, 1)[:4] == b"QTDS" and quest_record_no(_slot(q3, 1)) == 20350,
              "first free slot of quest3 used")
        check((save / "quest3.revival_backup").exists(), "pack backed up before the first change")
        check((save / "quest1").read_bytes() == pack({0: (mine, 20301)}), "quest1 untouched")
        a, u, r, _ = sync_event_packs(save, {20350: qrec(20350, b"v2")}, owned)
        check((a, u, r) == (0, 1, 0), "updated in place")
        a, u, r, _ = sync_event_packs(save, {20350: qrec(20350, b"v2")}, owned)
        check((a, u, r) == (0, 0, 0), "no change -> nothing written")
        q3 = bytearray((save / "quest3").read_bytes())
        o = PACK_HEADER + 1 * PACK_SLOT
        q3[o + 100] ^= 0xFF                                  # the player edits our quest
        (save / "quest3").write_bytes(bytes(q3))
        a, u, r, _ = sync_event_packs(save, {}, owned)
        check((a, u, r) == (0, 0, 0) and owned == {}, "an edited slot is no longer ours")
        check(_slot((save / "quest3").read_bytes(), 1)[:4] == b"QTDS", "and is never cleared")
        (save / "quest3").write_bytes(pack())
        owned = {}
        sync_event_packs(save, {20350: qrec(20350)}, owned)
        a, u, r, _ = sync_event_packs(save, {}, owned)
        check((a, u, r) == (0, 0, 1) and not any(_slot((save / "quest3").read_bytes(), 0)),
              "event over -> our slot cleared")
        full = {i: (qrec(20100 + i), 20100 + i) for i in range(PACK_SLOTS)}
        for n in EVENT_PACKS:
            (save / n).write_bytes(pack(full))
        a, u, r, notes = sync_event_packs(save, {20350: qrec(20350)}, {})
        check(a == 0 and any("no free" in n for n in notes), "full packs -> a note, nothing lost")
        # offline: the cached list and quests are used
        cache = tmp / EVENTS_CACHE_REL
        cache.mkdir(parents=True)
        (cache / "events.json").write_text(json.dumps({"quests": [
            {"file": "q_20350.quest", "sha256": sha}]}), encoding="utf-8")
        (cache / "q_20350.quest").write_bytes(good)
        check(load_event_quests(tmp, fetch=False, log=lambda s: None) == {20350: good},
              "offline start uses the cached event quests")
        check(is_protected_path(EVENTS_STATE_REL), "event slot ownership is protected")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("SELFTEST", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


# ===========================================================================
# GUI  (tkinter — imported lazily so --selftest works without a display)
# ===========================================================================

def _run_gui(smoke=False):
    # smoke=True builds the whole window (every widget + the update thread) then
    # tears it down after ~0.4s WITHOUT blocking — used by `--smoke` to prove the
    # frozen exe's bundled tkinter and widget construction work headlessly.
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox

    ROOT_DIR = bundle_root()

    app = tk.Tk()
    app.title(APP_TITLE)
    app.geometry("640x520")
    app.minsize(560, 440)

    # shared update state (set by background thread)
    state = {"remote_tag": None, "assets": {}, "update_available": False}

    # --- top status strip -------------------------------------------------
    top = ttk.Frame(app, padding=(12, 8))
    top.pack(fill="x")
    ttk.Label(top, text=APP_TITLE, font=("Segoe UI", 16, "bold")).pack(side="left")
    local_ver = read_version(ROOT_DIR)
    ver_var = tk.StringVar(value=f"version {local_ver}")
    ttk.Label(top, textvariable=ver_var).pack(side="right")

    update_bar = ttk.Frame(app, padding=(12, 0))
    update_var = tk.StringVar(value="checking for updates…")
    update_lbl = ttk.Label(update_bar, textvariable=update_var, foreground="#555")
    update_lbl.pack(side="left")
    update_btn = ttk.Button(update_bar, text="Update now")
    # packed later only if an update exists
    update_bar.pack(fill="x")

    # --- notebook: Home / Join / Host ------------------------------------
    nb = ttk.Notebook(app)
    nb.pack(fill="both", expand=True, padx=12, pady=8)

    # ---------------- HOME ----------------
    home = ttk.Frame(nb, padding=20)
    nb.add(home, text="Home")
    ttk.Label(home, text="What do you want to do?",
              font=("Segoe UI", 12)).pack(pady=(10, 20))
    btn_join = ttk.Button(home, text="JOIN A GAME", width=28,
                          command=lambda: nb.select(join))
    btn_join.pack(pady=6, ipady=8)
    btn_host = ttk.Button(home, text="HOST A SERVER", width=28,
                          command=lambda: nb.select(host))
    btn_host.pack(pady=6, ipady=8)
    ttk.Label(home, text="JOIN = play on the official server or a friend's.\n"
                         "HOST = run the server for your friends.",
              foreground="#555", justify="center").pack(pady=(20, 8))
    home_status_var = tk.StringVar(value="")
    ttk.Label(home, textvariable=home_status_var, foreground="#555",
              justify="center").pack()
    NEWS_FG = "#8a5a00"
    home_news_var = tk.StringVar(value="")
    ttk.Label(home, textvariable=home_news_var, foreground=NEWS_FG, wraplength=520,
              justify="center").pack(pady=(8, 0))

    # ---------------- JOIN ----------------
    join = ttk.Frame(nb, padding=16)
    nb.add(join, text="Join")
    settings_path = os.path.join(ROOT_DIR, LAUNCHER_SETTINGS_REL)
    jsettings = read_launcher_settings(settings_path)
    saved_ip = read_host_ip(os.path.join(ROOT_DIR, SRVFILE_REL))
    # mh3u_server.txt holds the official server's IP after an official launch, so the
    # friend's-IP box only falls back to it for installs that predate the choice.
    if jsettings.get("join_mode") == "official":
        start_custom_ip = jsettings.get("custom_ip", "")
    else:
        start_custom_ip = jsettings.get("custom_ip") or saved_ip

    ttk.Label(join, text="Where do you want to play?",
              font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 4))
    choice_var = tk.StringVar(value="custom")
    jstate = {"servers": [], "touched": False, "status": {}}

    def touched(*_):
        jstate["touched"] = True

    official_frame = ttk.Frame(join)            # filled in once servers.json is loaded
    official_frame.pack(fill="x", anchor="w")
    ttk.Label(official_frame, text="Official server: checking…",
              foreground="#555").pack(anchor="w")

    custom_row = ttk.Frame(join)
    custom_row.pack(fill="x", anchor="w", pady=(2, 0))
    ttk.Radiobutton(custom_row, text="A friend's server, IP:", variable=choice_var,
                    value="custom", command=touched).pack(side="left")
    ip_var = tk.StringVar(value=start_custom_ip)
    ip_entry = ttk.Entry(custom_row, textvariable=ip_var, width=24)
    ip_entry.pack(side="left", padx=6)

    def ip_focus(_e):
        choice_var.set("custom")
        touched()
    ip_entry.bind("<FocusIn>", ip_focus)
    ttk.Label(join, text="Ask the host for their Tailscale (100.x), Radmin (26.x), "
                         "LAN or public IP.", foreground="#555").pack(anchor="w", padx=(22, 0))
    join_news_var = tk.StringVar(value="")
    ttk.Label(join, textvariable=join_news_var, foreground=NEWS_FG, wraplength=560,
              justify="left").pack(anchor="w", pady=(6, 0))
    events_var = tk.BooleanVar(value=jsettings.get("events", True) is not False)
    ttk.Checkbutton(join, variable=events_var,
                    text="Add the official event quests to my game (your own quests "
                         "are never changed)").pack(anchor="w", pady=(6, 0))
    join_btns = ttk.Frame(join)
    join_btns.pack(anchor="w", pady=10)
    join_play = ttk.Button(join_btns, text="Save + Play")
    join_play.pack(side="left")
    join_test = ttk.Button(join_btns, text="Test connection")
    join_test.pack(side="left", padx=6)
    join_log = scrolledtext.ScrolledText(join, height=10, wrap="word", state="disabled")
    join_log.pack(fill="both", expand=True)

    def jlog(line):
        join_log.configure(state="normal")
        join_log.insert("end", line + "\n")
        join_log.see("end")
        join_log.configure(state="disabled")

    def chosen_server(choice, log):
        """The picked official server and its IP, or (None, None) after logging why."""
        sid = choice.split(":", 1)[1]
        srv = next((s for s in jstate["servers"] if s["id"] == sid), None)
        if srv is None:
            log("[MH3U Online] That server isn't in the list anymore; pick one again.")
            return None, None
        try:
            ip = resolve_host(srv["host"])
        except OSError as e:
            log(f"[MH3U Online] ERROR: couldn't look up {srv['name']} ({e}). "
                "Check your internet connection.")
            return None, None
        return srv, ip

    def do_test():
        choice = choice_var.get()
        custom_ip = ip_var.get().strip()
        join_test.configure(state="disabled")

        def worker():
            log = lambda s: app.after(0, jlog, s)  # noqa: E731
            try:
                if choice.startswith("official:"):
                    srv, ip = chosen_server(choice, log)
                    if srv is None:
                        return
                    name = srv["name"]
                else:
                    srv, ip, name = None, custom_ip, "your friend's server"
                    if not ip or ip == PLACEHOLDER:
                        log("[Test] Type your friend's IP first.")
                        return
                log(f"[Test] Asking {name} ({ip}) on UDP {NATCHECK_PORT} ...")
                ok, info = natcheck_probe(ip)
                if ok:
                    log(f"[Test] OK: the server answered and sees you at {info}. "
                        "Your connection to it works.")
                elif srv is not None:
                    log(f"[Test] FAILED ({info}). Either the server is down, or something "
                        "on your side blocks UDP: a firewall, a VPN, or a school/work "
                        "network.")
                else:
                    log(f"[Test] FAILED ({info}). Check that your friend's server is "
                        f"running, that their router forwards UDP 1223, 1224 and "
                        f"{NATCHECK_PORT} to their PC, and their firewall allows them.")
                if srv is not None and srv["status_port"]:
                    try:
                        snap = fetch_status(srv["host"], srv["status_port"])
                        log(f"[Test] Server status: {format_status(snap)}")
                    except Exception as e:
                        log(f"[Test] Status page didn't answer ({e}).")
            finally:
                app.after(0, lambda: join_test.configure(state="normal"))
        threading.Thread(target=worker, daemon=True).start()

    join_test.configure(command=do_test)

    def do_join():
        choice = choice_var.get()
        custom_ip = ip_var.get().strip()
        join_play.configure(state="disabled")

        def worker():
            log = lambda s: app.after(0, jlog, s)  # noqa: E731
            try:
                if choice.startswith("official:"):
                    srv, ip = chosen_server(choice, log)
                    if srv is None:
                        return
                    label = srv["name"]      # the official server's address isn't shown
                    new = {"join_mode": "official", "server_id": srv["id"]}
                else:
                    ip = label = custom_ip
                    new = {"join_mode": "custom"}
                settings = dict(read_launcher_settings(settings_path))
                settings.update(new, custom_ip=custom_ip, events=bool(events_var.get()))
                try:
                    write_launcher_settings(settings_path, settings)
                except OSError:
                    pass
                if events_var.get():
                    try:
                        install_event_quests(ROOT_DIR, log=log)
                    except Exception as e:          # never let this block playing
                        log(f"[Events] Skipped the event quests ({e}).")
                run_join_flow(ROOT_DIR, ip, launch=True, log=log, host_label=label)
            finally:
                app.after(0, lambda: join_play.configure(state="normal"))
        threading.Thread(target=worker, daemon=True).start()

    join_play.configure(command=do_join)

    # --- official server list + live player counts --------------------------
    OK_FG, BAD_FG, IDLE_FG = "#1a8f3a", "#c0392b", "#999"

    def set_status(sid, text, color):
        w = jstate["status"].get(sid)
        if w:
            w[0].configure(foreground=color)
            w[1].set(text)
        servers = jstate["servers"]
        if servers and servers[0]["id"] == sid:
            home_status_var.set(f"{servers[0]['name']}: {text}")

    def show_servers(data, source):
        servers = data["servers"]
        jstate["servers"] = servers
        jstate["status"] = {}
        for w in official_frame.winfo_children():
            w.destroy()
        if not servers:
            msg = ("Official server: not available yet." if source != "none" else
                   "Official server: couldn't load the server list (offline?).")
            ttk.Label(official_frame, text=msg, foreground="#555").pack(anchor="w")
        for s in servers:
            row = ttk.Frame(official_frame)
            row.pack(fill="x", anchor="w")
            ttk.Radiobutton(row, text=s["name"], variable=choice_var,
                            value="official:" + s["id"], command=touched).pack(side="left")
            dot = ttk.Label(row, text="●", foreground=IDLE_FG)
            text = tk.StringVar(value="checking…" if s["status_port"] else "")
            if s["status_port"]:
                dot.pack(side="left", padx=(8, 2))
                ttk.Label(row, textvariable=text, foreground="#555").pack(side="left")
            jstate["status"][s["id"]] = (dot, text)
        if not jstate["touched"]:
            choice_var.set(initial_join_choice(jsettings, saved_ip, servers))
        join_news_var.set(data["news"])
        home_news_var.set(data["news"])
        if servers and not servers[0]["status_port"]:
            home_status_var.set(f"Official server: {servers[0]['name']}")

    def servers_worker():
        data, source = load_servers(ROOT_DIR)
        try:
            app.after(0, show_servers, data, source)
        except Exception:
            return                              # window already closed
        while True:
            for s in data["servers"]:
                if not s["status_port"]:
                    continue
                try:
                    text, color = format_status(fetch_status(s["host"], s["status_port"])), OK_FG
                except Exception:
                    text, color = "not responding", BAD_FG
                try:
                    app.after(0, set_status, s["id"], text, color)
                except Exception:
                    return                      # window already closed
            time.sleep(STATUS_POLL_SECONDS)

    threading.Thread(target=servers_worker, daemon=True).start()

    # ---------------- HOST ----------------
    host = ttk.Frame(nb, padding=16)
    nb.add(host, text="Host")

    server_kind = server_available(ROOT_DIR)
    if server_kind is None:
        ttk.Label(host, text="server.exe is missing from this folder.",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(4, 2))
        ttk.Label(host, text="The all-in-one bundle ships server.exe next to this "
                             "launcher.\nIf it's gone (antivirus quarantine or a partial "
                             "unzip), re-download\nthe latest bundle from Releases and "
                             "extract it fully.", foreground="#555",
                  justify="left").pack(anchor="w")
        def open_releases():
            try:
                os.startfile(RELEASES_PAGE)  # noqa
            except Exception:
                pass
        ttk.Button(host, text="Open Releases page", command=open_releases).pack(anchor="w", pady=8)
    else:
        ttk.Label(host, text="Which IP will friends connect to?",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ipframe = ttk.Frame(host)
        ipframe.pack(fill="x", pady=4)
        sel_ip = tk.StringVar()
        choices = host_ip_choices()
        for i, (label, ip) in enumerate(choices):
            rb = ttk.Radiobutton(ipframe, text=label, variable=sel_ip, value=ip)
            rb.pack(anchor="w")
            if i == 0:
                sel_ip.set(ip)  # preselect top-priority option
        override_row = ttk.Frame(host)
        override_row.pack(fill="x", pady=(4, 8))
        ttk.Label(override_row, text="or type any IP:").pack(side="left")
        override_var = tk.StringVar()
        ttk.Entry(override_row, textvariable=override_var, width=22).pack(side="left", padx=6)

        relay_var = tk.BooleanVar(value=False)
        relay_row = ttk.Frame(host)
        relay_row.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(relay_row, text="Relay hunt traffic through this PC (experimental)",
                        variable=relay_var).pack(anchor="w")
        ttk.Label(relay_row,
                  text="Friends won't need port forwarding, including on cellular / CGNAT,\n"
                       "and players won't see each other's IP addresses. All hunt traffic\n"
                       "uses your upload, and UDP 27100-27387 must be open too.",
                  foreground="#555", justify="left").pack(anchor="w", padx=(20, 0))

        banner_var = tk.StringVar(value="")
        banner = ttk.Entry(host, textvariable=banner_var, state="readonly",
                           font=("Consolas", 11))
        # packed on start

        btnrow = ttk.Frame(host)
        btnrow.pack(fill="x")
        start_btn = ttk.Button(btnrow, text="Start Server")
        start_btn.pack(side="left")
        stop_btn = ttk.Button(btnrow, text="Stop Server", state="disabled")
        stop_btn.pack(side="left", padx=6)
        hostplay_btn = ttk.Button(btnrow, text="Host + Play")
        hostplay_btn.pack(side="left", padx=6)

        host_log = scrolledtext.ScrolledText(host, height=12, wrap="word", state="disabled")
        host_log.pack(fill="both", expand=True, pady=(8, 0))

        proc_holder = {"proc": None, "reader": None}

        def hlog(line):
            host_log.configure(state="normal")
            host_log.insert("end", line.rstrip("\n") + "\n")
            host_log.see("end")
            host_log.configure(state="disabled")

        def chosen_ip():
            return (override_var.get().strip() or sel_ip.get().strip() or "127.0.0.1")

        def start_server(ip=None):
            if proc_holder["proc"] is not None:
                hlog("[Host] Server already running.")
                return
            ip = ip or chosen_ip()
            cmd, kind = build_server_command(ROOT_DIR)
            if not cmd:
                hlog("[Host] ERROR: no server.exe or server.py found.")
                return
            env = dict(os.environ)
            env["MH3U_ADVERTISE"] = ip
            relay_on = bool(relay_var.get())
            if relay_on:
                # Deliberately not setting MH3U_RELAY_PROBES: "host" is the correct
                # default and "all" breaks 3-player rooms. See docs/GUEST_PAIR_PROBLEM.md.
                env["MH3U_RELAY"] = "force"
            banner_var.set(f"Friends connect to:  {ip}")
            if not banner.winfo_ismapped():
                banner.pack(fill="x", pady=6, before=btnrow)
            hlog(f"[Host] Starting server ({kind}), advertising {ip}"
                 f"{', relay ON' if relay_on else ''} ...")
            try:
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
                proc = subprocess.Popen(
                    cmd, cwd=ROOT_DIR, env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL, text=True, bufsize=1,
                    creationflags=flags)
            except OSError as e:
                hlog(f"[Host] ERROR starting server: {e}")
                return
            proc_holder["proc"] = proc
            start_btn.configure(state="disabled")
            stop_btn.configure(state="normal")

            def reader():
                try:
                    for line in iter(proc.stdout.readline, ""):
                        if not line:
                            break
                        app.after(0, hlog, line)
                except Exception:
                    pass
                app.after(0, on_server_exit)
            t = threading.Thread(target=reader, daemon=True)
            proc_holder["reader"] = t
            t.start()

        def on_server_exit():
            hlog("[Host] Server stopped.")
            proc_holder["proc"] = None
            start_btn.configure(state="normal")
            stop_btn.configure(state="disabled")

        def _kill_proc_tree(proc):
            """server.exe is a PyInstaller *onefile*: the process we spawned is
            the bootloader, which launches the REAL server as a child that binds
            1223/1224/10025. terminate()/kill() on the parent alone orphans that
            child and leaves the ports held -- so kill the whole tree. On Windows
            taskkill /T walks the child tree; do it FIRST (before the parent dies,
            or the child gets reparented and slips the /T)."""
            if os.name == "nt":
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        timeout=10)
                except Exception:
                    pass
            else:
                try:
                    proc.terminate()
                except Exception:
                    pass
            try:
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        def stop_server():
            proc = proc_holder["proc"]
            if proc is None:
                return
            hlog("[Host] Stopping server ...")
            try:
                _kill_proc_tree(proc)
            except Exception as e:
                hlog(f"[Host] stop error: {e}")

        def host_and_play():
            # Use the SAME picked IP for advertise and for our own Cemu's connect.
            # They must match: the server publishes each peer's reflexive address
            # from how they connected, so if we host + play over loopback it hands
            # 127.0.0.1 to friends and nobody can reach us. Connecting over the
            # chosen plane (Radmin/Tailscale/LAN) makes the published address
            # reachable — and works for solo too (you reach your own overlay/LAN
            # IP locally, no P2P peers to publish to).
            ip = chosen_ip()
            start_server(ip)
            run_join_flow(ROOT_DIR, ip, launch=True,
                          log=lambda s: app.after(0, hlog, s))

        start_btn.configure(command=lambda: start_server())
        stop_btn.configure(command=stop_server)
        hostplay_btn.configure(command=host_and_play)

        def on_close():
            if proc_holder["proc"] is not None:
                stop_server()
            app.destroy()
        app.protocol("WM_DELETE_WINDOW", on_close)

    # --- background update check -----------------------------------------
    def do_update():
        if not state["update_available"]:
            return
        if is_running(CEMU_EXE) or is_running(SERVER_EXE):
            messagebox.showwarning(
                APP_TITLE, "Close Cemu and the server before updating.")
            return
        update_btn.configure(state="disabled")
        win = tk.Toplevel(app)
        win.title("Updating")
        win.geometry("380x120")
        ttk.Label(win, text=f"Downloading update {state['remote_tag']} …").pack(pady=8)
        pb = ttk.Progressbar(win, length=340, mode="determinate")
        pb.pack(pady=4)
        pstat = tk.StringVar(value="")
        ttk.Label(win, textvariable=pstat).pack()

        def prog(frac):
            app.after(0, lambda: (pb.configure(value=frac * 100),
                                  pstat.set(f"{int(frac * 100)}%")))

        def worker():
            try:
                tmpdir = Path(tempfile.mkdtemp(prefix="mh3u_update_"))
                assets = state["assets"]
                # All-in-one bundle carries server.exe too, so applying
                # BUNDLE_ZIP updates both player and host files in one shot —
                # no separate add-on download.
                want = [BUNDLE_ZIP]
                deferred = None
                for name in want:
                    url = assets.get(name)
                    if not url:
                        continue
                    dest = tmpdir / name
                    download_file(url, dest, progress=prog)
                    d = apply_update_zip(dest, ROOT_DIR,
                                         log=lambda s: app.after(0, jlog, s))
                    deferred = deferred or d
                # rewrite version LAST
                write_version(ROOT_DIR, state["remote_tag"])
                if deferred:
                    launcher_name = (os.path.basename(sys.executable)
                                     if getattr(sys, "frozen", False) else "MH3U_Online.exe")
                    bat = write_self_replace_bat(ROOT_DIR, launcher_name)
                    app.after(0, lambda: (messagebox.showinfo(
                        APP_TITLE, "Update ready — the launcher will restart."),
                        subprocess.Popen(["cmd", "/c", str(bat)],
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)),
                        app.destroy()))
                else:
                    app.after(0, lambda: (messagebox.showinfo(
                        APP_TITLE, f"Updated to {state['remote_tag']}."),
                        ver_var.set(f"version {state['remote_tag']}"),
                        update_var.set("up to date"),
                        win.destroy()))
            except Exception as e:
                # Python unbinds `e` when this block ends, before the callback runs.
                err = str(e)
                app.after(0, lambda: (messagebox.showerror(
                    APP_TITLE, f"Update failed: {err}"), win.destroy(),
                    update_btn.configure(state="normal")))
        threading.Thread(target=worker, daemon=True).start()

    update_btn.configure(command=do_update)

    def check_updates():
        try:
            tag, assets = fetch_latest_release()
        except Exception:
            app.after(0, lambda: update_var.set("update check failed — offline?"))
            return
        state["remote_tag"] = tag
        state["assets"] = assets
        newer = is_newer(tag, local_ver)
        state["update_available"] = newer

        def show():
            if newer:
                update_var.set(f"Update {tag} available")
                update_btn.pack(side="left", padx=8)
            else:
                update_var.set("up to date" if local_ver != "unknown"
                               else f"latest is {tag}")
        app.after(0, show)

    threading.Thread(target=check_updates, daemon=True).start()

    if smoke:
        app.after(400, app.destroy)         # construct, settle, auto-close
    app.mainloop()


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if "--selftest" in argv:
        return _selftest()
    _run_gui(smoke="--smoke" in argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())

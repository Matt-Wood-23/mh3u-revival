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
import secrets
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
    matching the .bat: Radmin > Tailscale > LAN > loopback. Radmin/Tailscale only
    appear when detected. Always includes loopback + LAN so nothing is silently
    picked."""
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

def run_join_flow(root, host_ip, launch=True, log=print):
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
        log(f"[MH3U Online] Saved host = {ip}")
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
    ttk.Label(home, text="JOIN = play on a friend's server.\n"
                         "HOST = run the server for your friends.",
              foreground="#555", justify="center").pack(pady=20)

    # ---------------- JOIN ----------------
    join = ttk.Frame(nb, padding=16)
    nb.add(join, text="Join")
    ttk.Label(join, text="Host's IP address", font=("Segoe UI", 11, "bold")).pack(anchor="w")
    ttk.Label(join, text="Ask the host — their Tailscale (100.x), Radmin (26.x), "
                         "LAN or public IP.", foreground="#555").pack(anchor="w", pady=(0, 6))
    ip_var = tk.StringVar(value=read_host_ip(os.path.join(ROOT_DIR, SRVFILE_REL)))
    ip_entry = ttk.Entry(join, textvariable=ip_var, width=40)
    ip_entry.pack(anchor="w")
    join_play = ttk.Button(join, text="Save + Play")
    join_play.pack(anchor="w", pady=10)
    join_log = scrolledtext.ScrolledText(join, height=12, wrap="word", state="disabled")
    join_log.pack(fill="both", expand=True)

    def jlog(line):
        join_log.configure(state="normal")
        join_log.insert("end", line + "\n")
        join_log.see("end")
        join_log.configure(state="disabled")

    def do_join():
        ip = ip_var.get().strip()
        join_play.configure(state="disabled")

        def worker():
            try:
                run_join_flow(ROOT_DIR, ip, launch=True, log=lambda s: app.after(0, jlog, s))
            finally:
                app.after(0, lambda: join_play.configure(state="normal"))
        threading.Thread(target=worker, daemon=True).start()

    join_play.configure(command=do_join)

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
        hostplay_btn = ttk.Button(btnrow, text="Host + Play (127.0.0.1)")
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
            banner_var.set(f"Friends connect to:  {ip}")
            if not banner.winfo_ismapped():
                banner.pack(fill="x", pady=6, before=btnrow)
            hlog(f"[Host] Starting server ({kind}), advertising {ip} ...")
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

        def stop_server():
            proc = proc_holder["proc"]
            if proc is None:
                return
            hlog("[Host] Stopping server ...")
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except Exception as e:
                hlog(f"[Host] stop error: {e}")

        def host_and_play():
            start_server("127.0.0.1")
            run_join_flow(ROOT_DIR, "127.0.0.1", launch=True,
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
                app.after(0, lambda: (messagebox.showerror(
                    APP_TITLE, f"Update failed: {e}"), win.destroy(),
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

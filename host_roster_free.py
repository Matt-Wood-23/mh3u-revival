"""Auto-free a departed guest's slot in the HOST Cemu's CNEXSystem roster.

Root cause (fully RE'd 2026-06-21, see handoffs/2026-06-20_guest_rejoin_mediator_stall.md):
MH3U's host has NO native "guest left the room" path — no leave packet, no P2P-disconnect
detection for a lobby-persistent peer, and its NEX notification handler is inert (field_4 null).
So when a guest backs out of a room the host keeps a stale participant forever; the next rejoin
drifts to a new slot (station climbs 2->3->4 -> 4-slot OOB -> stall) AND the roster/station conn
mismatch -> "host thinks peer is still here" stall + disconnect.

The server DOES know the exact instant + identity of a room-leave (end_participation). Since the
server is co-located with the host Cemu in the "I host" model, we mirror the game's own remove
across every view the host keeps in sync:
  roster record (roster+slot*0x70): member +0x30, conn +0x34, active +0x38  -> 0
  used-flag  *(cnx+0x30d34)+slot*4 = 0    (THE slot-allocation key — fixes drift)
  flag2      *(cnx+0x30d4c)+slot*4 = 0
  membercount u16 (cnx+0x30d30) -= 1
  station array entry cnx+0x304 + slot*0x60 = 0   (fixes roster/station conn mismatch)
  dirty flags cnx+0x30d2c |= 0x7   (forces the host to recompute member list + redraw)
Live-proven across 3 clean leave/rejoin cycles (guest pinned to slot 1, no drift/disconnect).

PORTABLE (2026-06-24): self-contained — the Cemu memory access (guest<->host translation via the
committed-region entry-signature scan) is vendored here, so this works on ANY host machine running
the bundled Cemu, not just the dev box. The host Cemu process is found by exe name (Cemu_release.exe
or Cemu.exe); the static guest offsets below are fixed for MH3U US v1.3 (the version this project
targets) so they carry across installs. Needs `pymem` (bundled into the frozen server.exe).

Fail-safe: any error (no host Cemu, pymem missing, offsets moved) is caught and logged; the server
keeps running. Enabled by default; set MH3U_HOST_FREE=0 to disable (e.g. remote-host deployments
where the host Cemu is not on the server machine). If several Cemu processes run on one machine
(e.g. a dev host+guest pair), set MH3U_HOST_HINT to a substring of the HOST Cemu's exe path to pick
it; otherwise the first Cemu found is used.
"""
import os
import ctypes
import logging
from ctypes import wintypes

logger = logging.getLogger("mh3u.hostfree")

ENABLED = os.environ.get("MH3U_HOST_FREE", "1") not in ("0", "", "false", "False")
# Optional exe-path substring to disambiguate when MULTIPLE Cemu processes run (dev only).
# Empty by default -> a normal host has exactly one Cemu, so no hint is needed.
HOST_HINT = os.environ.get("MH3U_HOST_HINT", "").lower()

# CNEXSystem-relative offsets (v1.3 US; see handoff)
O_ROSTER = 0x30d3c
O_USED = 0x30d34
O_FLAG2 = 0x30d4c
O_COUNT = 0x30d30
O_MAX = 0x30ab0
O_STATION = 0x304
O_DIRTY = 0x30d2c
ST_STRIDE = 0x60
REC = 0x70

# ---- Cemu guest<->host memory (vendored from cemu_re_mcp PymemBridge) ----
# Cemu maps the WiiU's 32-bit guest space as one big committed region inside the host
# process; host = region_base + (guest - GUEST_BASE). region_base is per-launch (ASLR),
# found by scanning committed readable regions for the PPC entry signature at guest 0x02000000.
GUEST_BASE = 0x02000000
ENTRY_SIG = bytes.fromhex("600000004e800020")   # nop ; blr  (first 8 bytes of guest code)
_MEM_COMMIT = 0x1000
_READABLE = {0x02, 0x04, 0x20, 0x40}             # PAGE_READ*/EXECUTE_READ*


class _MBI(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_ulonglong), ("AllocationBase", ctypes.c_ulonglong),
        ("AllocationProtect", wintypes.DWORD), ("__a", wintypes.DWORD),
        ("RegionSize", ctypes.c_ulonglong), ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD), ("Type", wintypes.DWORD), ("__b", wintypes.DWORD),
    ]


class _PE32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_char * 260),
    ]


def _be(b):
    return int.from_bytes(b, "big")


def _iter_procs():
    """Yield (pid, exe_name) for every running process (Toolhelp32, no wmic dependency)."""
    k = ctypes.windll.kernel32
    snap = k.CreateToolhelp32Snapshot(0x2, 0)   # TH32CS_SNAPPROCESS
    if snap in (-1, 0xFFFFFFFFFFFFFFFF):
        return
    try:
        pe = _PE32(); pe.dwSize = ctypes.sizeof(_PE32)
        ok = k.Process32First(snap, ctypes.byref(pe))
        while ok:
            yield pe.th32ProcessID, pe.szExeFile.decode("latin1", "ignore")
            ok = k.Process32Next(snap, ctypes.byref(pe))
    finally:
        k.CloseHandle(snap)


def _proc_path(pid):
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(32768)
        sz = wintypes.DWORD(len(buf))
        if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(sz)):
            return buf.value
        return ""
    finally:
        k.CloseHandle(h)


def _host_pid():
    """PID of the host Cemu. CEMU_PID wins; else the (hint-matched) Cemu_release.exe/Cemu.exe."""
    if os.environ.get("CEMU_PID"):
        try:
            return int(os.environ["CEMU_PID"])
        except ValueError:
            pass
    cands = [pid for pid, name in _iter_procs()
             if name.lower() in ("cemu_release.exe", "cemu.exe")]
    if not cands:
        return None
    if HOST_HINT:
        for pid in cands:
            if HOST_HINT in _proc_path(pid).lower():
                return pid
    return cands[0]


class _CemuMem:
    """Minimal guest<->host reader/writer for one Cemu process (no numpy, small ops only)."""

    def __init__(self, pid):
        import pymem
        self.pm = pymem.Pymem()
        self.pm.open_process_from_id(pid)
        self.base = self._find_region()

    def _find_region(self):
        h = self.pm.process_handle
        vq = ctypes.windll.kernel32.VirtualQueryEx
        vq.restype = ctypes.c_ulonglong
        vq.argtypes = [wintypes.HANDLE, ctypes.c_ulonglong, ctypes.POINTER(_MBI), ctypes.c_ulonglong]
        addr = 0
        best = None
        while addr < 0x7FFFFFFFFFFF:
            mbi = _MBI()
            if not vq(h, addr, ctypes.byref(mbi), ctypes.sizeof(mbi)):
                break
            if (mbi.State == _MEM_COMMIT and (mbi.Protect & 0xFF) in _READABLE
                    and mbi.RegionSize > (256 << 20)):
                try:
                    if self.pm.read_bytes(mbi.BaseAddress, 8) == ENTRY_SIG:
                        return mbi.BaseAddress
                except Exception:
                    pass
                if best is None or mbi.RegionSize > best[1]:
                    best = (mbi.BaseAddress, mbi.RegionSize)
            addr = mbi.BaseAddress + mbi.RegionSize if mbi.RegionSize else addr + 0x1000
        if best is None:
            raise RuntimeError("could not locate Cemu guest region (entry sig not found)")
        return best[0]

    def read(self, guest, length):
        return self.pm.read_bytes(self.base + (guest - GUEST_BASE), length)

    def write(self, guest, data):
        self.pm.write_bytes(self.base + (guest - GUEST_BASE), data, len(data))
        return len(data)


def free_guest_slot(nex_pid):
    """Free the host roster slot whose member-id == nex_pid. Returns a short status string.
    Synchronous + pymem-based; call via asyncio.to_thread so it never blocks the event loop."""
    if not ENABLED:
        return "disabled"
    pid = _host_pid()
    if pid is None:
        return "no host Cemu process found (Cemu_release.exe / Cemu.exe)"
    try:
        br = _CemuMem(pid)
    except Exception as e:  # pragma: no cover  (pymem missing or region not found)
        return f"cemu mem unavailable ({e})"
    try:
        nexb = _be(br.read(0x102f95d0, 4)); cnx = nexb + 0x16378
        roster = _be(br.read(cnx + O_ROSTER, 4))
        used_p = _be(br.read(cnx + O_USED, 4))
        flag2_p = _be(br.read(cnx + O_FLAG2, 4))
        maxc = _be(br.read(cnx + O_MAX, 2))
        cnt = _be(br.read(cnx + O_COUNT, 2))
        # locate the slot (members start at index 1; index 0 is the host)
        slot = None
        for i in range(1, max(2, maxc)):
            if _be(br.read(roster + i * REC + 0x30, 4)) == (nex_pid & 0xffffffff):
                slot = i
                break
        if slot is None:
            return f"pid {nex_pid} not in host roster (already clean)"
        rec = roster + slot * REC
        st = cnx + O_STATION + slot * ST_STRIDE
        br.write(rec + 0x30, b"\x00\x00\x00\x00")             # member
        br.write(rec + 0x34, b"\x00\x00\x00\x00")             # conn
        br.write(rec + 0x38, b"\x00\x00\x00\x00")             # active
        br.write(used_p + slot * 4, b"\x00\x00\x00\x00")      # used-flag (slot-alloc key)
        br.write(flag2_p + slot * 4, b"\x00\x00\x00\x00")     # flag2
        br.write(cnx + O_COUNT, max(0, cnt - 1).to_bytes(2, "big"))  # membercount--
        br.write(st, b"\x00" * ST_STRIDE)                     # station-array entry
        br.write(cnx + O_DIRTY, (_be(br.read(cnx + O_DIRTY, 4)) | 0x7).to_bytes(4, "big"))  # resync/redraw
        return f"freed slot[{slot}] (pid {nex_pid}) on host Cemu pid={pid}"
    except Exception as e:  # pragma: no cover
        return f"error: {e!r}"

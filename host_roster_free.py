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

Fail-safe: any error (no host Cemu, pymem missing, offsets moved) is caught and logged; the server
keeps running. Enabled by default; set MH3U_HOST_FREE=0 to disable (e.g. remote-host deployments
where the host Cemu is not on the server machine). Host process disambiguated by exe-path hint
MH3U_HOST_HINT (default 'e:\\cemu-src').
"""
import os
import logging

logger = logging.getLogger("mh3u.hostfree")

HOST_HINT = os.environ.get("MH3U_HOST_HINT", r"e:\cemu-src").lower()
ENABLED = os.environ.get("MH3U_HOST_FREE", "1") not in ("0", "", "false", "False")

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


def _be(b):
    return int.from_bytes(b, "big")


def _host_pid():
    import subprocess
    out = subprocess.run(["wmic", "process", "where", "name='Cemu_release.exe'",
                          "get", "ProcessId,ExecutablePath"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if HOST_HINT in line.lower():
            for t in line.split()[::-1]:
                if t.isdigit():
                    return int(t)
    return None


def free_guest_slot(nex_pid):
    """Free the host roster slot whose member-id == nex_pid. Returns a short status string.
    Synchronous + pymem-based; call via asyncio.to_thread so it never blocks the event loop."""
    if not ENABLED:
        return "disabled"
    try:
        import sys
        sys.path.insert(0, r"E:\cemu_re_mcp\src")
        import pymem
        from cemu_re_mcp.pymem_backend import PymemBridge
    except Exception as e:  # pragma: no cover
        return f"pymem unavailable ({e})"
    try:
        pid = _host_pid()
        if pid is None:
            return f"no host Cemu (hint={HOST_HINT})"
        br = PymemBridge(); pm = pymem.Pymem(); pm.open_process_from_id(pid); br.pm = pm
        base, size = br._find_region(); br.host_region, br.region_size = base, size
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

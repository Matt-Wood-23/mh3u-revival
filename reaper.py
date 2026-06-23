"""Liveness reaper — evicts abruptly-disconnected players (Cemu closed / crashed) from the
world/lobby/room population in ~REAP_TIMEOUT seconds instead of the ~50 minutes that PRUDP's
resend_limit=100 would otherwise take to notice.

WHY ghosts happen: PRUDP is UDP, so a closed client sends no FIN. The server only declares a
connection dead after its keep-alive ping has gone unacked resend_limit (100) x resend_timeout
(30s) ~= 50 min, at which point cleanup()->logout() finally runs REGISTRY.leave + COMMUNITY.
leave_all. Until then the dead pid sits in the participant sets -> inflated "X/98" population
(matches the 2026-06-21 observation: both Cemus closed yet world 2/98, lobby 2/99).

HOW this fixes it: stamp a last-inbound-packet time on every PRUDP packet (pings included), then
a background task force-runs cleanup() on any SECURE-connection client silent past REAP_TIMEOUT.
cleanup()->logout() decrements the world/lobby (COMMUNITY.leave_all) AND the room (REGISTRY.leave,
which also DESTROYS an orphaned host-room so it stops showing in browse/find).

WHY it won't false-reap a live player: a loading or in-hunt client still sends its own PRUDP
keep-alive pings, so its last-rx stays fresh. The ONE exception is a Cemu PAUSED at a debugger
breakpoint (game clock frozen -> no pings) — that's also why prudp.resend_limit is cranked to 100.
So set MH3U_REAP_TIMEOUT=0 to DISABLE the reaper while doing live breakpoint debugging.

Tunables (env): MH3U_REAP_TIMEOUT (seconds of silence before reap; default 45; 0 = disabled).
NOTE: default was 120 during breakpoint-debugging (paused Cemu sends no pings); debugging is
done as of 2026-06-21, so it's back to 45 — worst-case ghost window ~= REAP_TIMEOUT + sweep.
"""
import os
import time
import asyncio
import logging

from nintendo.nex import prudp
import matchmaking_handlers as mh

logger = logging.getLogger("mh3u.reaper")

REAP_TIMEOUT = float(os.environ.get("MH3U_REAP_TIMEOUT", "45"))   # silence before reap; 0 disables
REAP_INTERVAL = 15.0                                              # how often to sweep


def install_rx_stamp():
    """Monkey-patch PRUDPClient.handle so every inbound packet records a last-rx timestamp.
    Patches the class (affects all instances), idempotent, must run before serving."""
    if getattr(prudp.PRUDPClient, "_mh3u_stamped", False):
        return
    _orig_handle = prudp.PRUDPClient.handle

    async def _stamped_handle(self, packet):
        self._mh3u_last_rx = time.monotonic()
        return await _orig_handle(self, packet)

    prudp.PRUDPClient.handle = _stamped_handle
    prudp.PRUDPClient._mh3u_stamped = True
    logger.info("rx-stamp installed on PRUDPClient.handle")


async def reaper_task():
    if REAP_TIMEOUT <= 0:
        logger.info("liveness reaper DISABLED (MH3U_REAP_TIMEOUT=%g) — ghosts rely on the "
                    "~50min PRUDP resend timeout (use this mode for breakpoint debugging)", REAP_TIMEOUT)
        return
    logger.info("liveness reaper ON: silence > %.0fs -> cleanup; sweep every %.0fs",
                REAP_TIMEOUT, REAP_INTERVAL)
    while True:
        await asyncio.sleep(REAP_INTERVAL)
        now = time.monotonic()
        for pid, rmc_client in list(mh.CLIENTS.items()):
            try:
                conn = getattr(rmc_client, "client", None)
                last = getattr(conn, "_mh3u_last_rx", None)
                if last is None:
                    continue
                idle = now - last
                # re-check the mapping: only reap if this is STILL the live connection for pid
                # (a fresh reconnect under the same account replaces CLIENTS[pid]).
                if idle > REAP_TIMEOUT and mh.CLIENTS.get(pid) is rmc_client:
                    logger.info("REAP pid=%s idle=%.0fs -> cleanup (ghost: abrupt disconnect)", pid, idle)
                    await rmc_client.cleanup()   # -> logout() -> REGISTRY.leave + COMMUNITY.leave_all
            except Exception as e:
                logger.warning("reaper: error reaping pid=%s: %s", pid, e)

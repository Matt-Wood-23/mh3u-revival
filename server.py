"""MH3U NEX server — entry point.

Stands up the two NEX servers MH3U expects:
  * authentication server (port 1223): validates login, mints a kerberos ticket,
    and hands back the secure server's StationURL.
  * secure server (port 1224): hosts SecureConnection + MatchMaking +
    MatchmakeExtension (the gathering hall).

Run:  python server.py        (from this directory)

Credentials come from config.py (recovered by RE of the retail client). The NEX
version is a tunable — see README. Real (patched) Cemu authenticates against this
end-to-end; the account-server token is handled client-side by the Cemu fork.
"""
import os
import sys
import secrets
import logging
from logging.handlers import RotatingFileHandler

# Make the cloned NintendoClients importable, plus this dir for local modules.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "external", "NintendoClients"))
sys.path.insert(0, _HERE)

import asyncio
import concurrent.futures
import contextlib
import aioconsole

from nintendo.nex import rmc, authentication, common, settings

import config
import users
import protocols
import reaper
import limits
import natcheck

def _log_dir():
    # Frozen (PyInstaller onefile): sys.executable is the real .exe path (the bundle
    # root), NOT the ephemeral _MEIxxx extraction dir that __file__ lives in. Writing
    # the log next to the exe keeps it with the bundle. Non-frozen: this script's dir.
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return _HERE


def _build_log_handlers():
    """Console (stderr) + a size-capped rotating file.

    The console handler stays because the launcher's Host tab streams stdout/stderr
    live into its log view. The rotating file gives a DURABLE, bounded on-disk record
    (the GUI stream is ephemeral, and a shell redirect grows without limit) so a long
    unattended session can't fill the host's disk. Tunables (env):
      MH3U_LOG_FILE  - filename (or abs path); "" disables the file (console only)
      MH3U_LOG_MAX_MB / MH3U_LOG_BACKUPS - size cap per file and how many to keep
    """
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    handlers = [console]
    log_name = os.environ.get("MH3U_LOG_FILE", "server.log")
    if not log_name:
        return handlers, None
    try:
        max_mb = float(os.environ.get("MH3U_LOG_MAX_MB", "5"))
        backups = int(os.environ.get("MH3U_LOG_BACKUPS", "5"))
    except (ValueError, TypeError):
        max_mb, backups = 5.0, 5
    path = log_name if os.path.isabs(log_name) else os.path.join(_log_dir(), log_name)
    try:
        fileh = RotatingFileHandler(path, maxBytes=int(max_mb * 1024 * 1024),
                                    backupCount=backups, encoding="utf-8")
    except OSError as e:
        # Read-only dir / locked file: keep running on console alone rather than crash.
        print("WARNING: could not open log file %r (%s) - logging to console only"
              % (path, e), file=sys.stderr)
        return handlers, None
    fileh.setFormatter(fmt)
    handlers.append(fileh)
    return handlers, path


_log_handlers, _log_path = _build_log_handlers()
logging.basicConfig(level=logging.INFO, handlers=_log_handlers)
logger = logging.getLogger("mh3u.server")
if _log_path:
    logger.info("logging to %s (rotating: %s MB x %s backups)", _log_path,
                os.environ.get("MH3U_LOG_MAX_MB", "5"), os.environ.get("MH3U_LOG_BACKUPS", "5"))

# Kerberos key derivation is ~65k rounds of MD5 — CPU-bound pure-Python, so it holds the GIL.
# Run it on a SINGLE dedicated worker thread (not asyncio.to_thread's default ~32-thread pool):
# with one worker, the event loop competes with exactly one CPU thread for the GIL and keeps
# getting time-slices to ack PRUDP, so a login surge no longer freezes the loop into 30s+ resend
# cascades. A bigger pool can't go faster (the GIL serializes the MD5 loops anyway) and only
# starves the loop more. Derivations thus serialize but stay off the loop. (load test 2026-06-23)
_AUTH_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="mh3u-auth")

# PRUDP logs EVERY packet (pings included) at WARNING — handy while reverse-engineering the
# handshake, but it floods the log and burns CPU/IO on every packet at scale. Quiet it to
# ERROR by default; set MH3U_PKT_LOG=1 to restore per-packet tracing for debugging.
if os.environ.get("MH3U_PKT_LOG") != "1":
    logging.getLogger("nintendo.nex.prudp").setLevel(logging.ERROR)


def build_settings():
    s = settings.load(config.SETTINGS_BASE)
    s.configure(config.ACCESS_KEY, config.NEX_VERSION)
    # Live Cemu debugging: pausing the emulator at a breakpoint freezes the GAME's
    # clock but NOT the server's, so the server's keep-alive pings go unacked and it
    # drops the session after ~3s (confirmed 2026-06-16: breakpoint halt after m21 ->
    # server ping timeout -> connection closed -> game stuck on loading screen).
    # Crank keep-alive/resend tolerances way up so a long breakpoint halt is survivable.
    # The client drives its own keep-alive, so a long server ping_timeout is harmless.
    s["prudp.ping_timeout"] = 120.0
    s["prudp.resend_timeout"] = 30.0
    s["prudp.resend_limit"] = 100
    return s


class AuthenticationServer(authentication.AuthenticationServer):
    def __init__(self, s):
        super().__init__()
        self.settings = s

    async def login(self, client, username):
        logger.info("LOGIN attempt: username=%r", username)
        user = users.resolve(username)
        if not user:
            logger.warning("  -> unknown username %r (add to users.py)", username)
            raise common.RMCError("RendezVous::InvalidUsername")

        server = users.by_pid(config.SECURE_SERVER_PID)

        url = common.StationURL(
            scheme="prudps", address=config.SERVER_ADDRESS, port=config.SECURE_PORT,
            PID=server.pid, CID=1, type=2, sid=1, stream=10,
        )
        conn_data = authentication.RVConnectionData()
        conn_data.main_station = url
        conn_data.special_protocols = []
        conn_data.special_station = common.StationURL()

        response = rmc.RMCResponse()
        response.result = common.Result.success()
        response.pid = user.pid
        response.ticket = await self._issue_ticket(user, server)
        response.connection_data = conn_data
        response.server_name = config.SERVER_DISPLAY_NAME
        logger.info("  -> issued ticket for pid=%s, pointing at %s:%s",
                    user.pid, config.SERVER_ADDRESS, config.SECURE_PORT)
        return response

    async def login_ex(self, client, username, extra_data):
        # The Wii U game logs in via LoginEx with a NEX token in extra_data. We
        # control both ends (the patched Cemu minted that token), so we ignore the
        # token and authenticate by PID — same path as login().
        logger.info("LOGIN_EX attempt: username=%r (token ignored)", username)
        return await self.login(client, username)

    async def request_ticket(self, client, source, target):
        # Old-NEX flow: after loginEx, the game calls RequestTicket(source, target)
        # to obtain the kerberos ticket for the secure server (target). Mint a fresh,
        # self-consistent ticket (client+internal halves share one session key).
        logger.info("REQUEST_TICKET: source=%s target=%s", source, target)
        src = users.by_pid(source) or users.resolve(str(source))
        tgt = users.by_pid(target) or users.by_pid(config.SECURE_SERVER_PID)
        response = rmc.RMCResponse()
        response.result = common.Result.success()
        response.ticket = await self._issue_ticket(src, tgt)
        logger.info("  -> issued ticket for %s -> %s (secure %s:%s)",
                    source, target, config.SERVER_ADDRESS, config.SECURE_PORT)
        return response

    async def _issue_ticket(self, source, target):
        # Ticket construction is dominated by two ~65k-round MD5 key derivations (CPU-bound,
        # GIL-held). Run it on the single dedicated _AUTH_POOL worker so the event loop stays
        # responsive enough to ack PRUDP during a login surge — without this, a burst of
        # simultaneous logins froze the loop into 30–90s PRUDP resend cascades that dropped
        # most clients (load test 2026-06-23). Keys are memoized (users.derive_key), so the
        # server key is free after the first login. MH3U_AUTH_FAST=0 forces the old inline,
        # on-the-loop-thread, uncached path (for A/B measurement).
        if os.environ.get("MH3U_AUTH_FAST") == "0":
            return self._ticket(source, target)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_AUTH_POOL, self._ticket, source, target)

    def _ticket(self, source, target):
        s = self.settings
        user_key = users.derive_key(source)
        server_key = users.derive_key(target)
        session_key = secrets.token_bytes(s["kerberos.key_size"])

        internal = kerberos_server_ticket(session_key, source.pid)
        ticket = kerberos_client_ticket(session_key, target.pid,
                                         internal.encrypt(server_key, s))
        return ticket.encrypt(user_key, s)


def kerberos_server_ticket(session_key, source_pid):
    from nintendo.nex import kerberos
    t = kerberos.ServerTicket()
    t.timestamp = common.DateTime.now()
    t.source = source_pid
    t.session_key = session_key
    return t


def kerberos_client_ticket(session_key, target_pid, internal):
    from nintendo.nex import kerberos
    t = kerberos.ClientTicket()
    t.session_key = session_key
    t.target = target_pid
    t.internal = internal
    return t


# ---------------------------------------------------------------------------
# Background-task supervision.
#
# The reaper and the notify-file watcher run as detached background tasks. A
# plain asyncio.create_task() that isn't awaited is fire-and-forget: if its
# coroutine raises, the task just vanishes (asyncio emits only an easily-missed
# "exception was never retrieved" warning). For the reaper that's a real hazard
# — a crash in its sweep loop would SILENTLY disable ghost cleanup for the rest
# of the session, degrading back to the ~50-minute PRUDP resend timeout the
# reaper exists to avoid. So we retain the task handles (this also stops the GC
# from collecting a task mid-flight) and watch them: log loudly on unexpected
# death, and respawn critical tasks a bounded number of times so a persistent
# bug can't spin-loop forever.
# ---------------------------------------------------------------------------
_BG_TASKS = set()
_RESPAWN_LIMIT = 5          # total runs of a respawnable task before giving up
_RESPAWN_BACKOFF = 10.0     # seconds before respawn, multiplied by the attempt number


def _supervise(coro_factory, name, *, respawn=False, _attempt=0):
    """Launch coro_factory() as a supervised background task. On unexpected death
    log it loudly; if respawn=True, relaunch (bounded, with backoff)."""
    task = asyncio.create_task(coro_factory())
    _BG_TASKS.add(task)

    def _done(t):
        _BG_TASKS.discard(t)
        if t.cancelled():
            return   # normal shutdown — stay quiet
        exc = t.exception()
        if exc is None:
            logger.info("background task %r exited", name)
            return
        logger.error("background task %r DIED: %r", name, exc, exc_info=exc)
        if not respawn:
            return
        if _attempt + 1 < _RESPAWN_LIMIT:
            delay = _RESPAWN_BACKOFF * (_attempt + 1)
            logger.error("  -> respawning %r in %.0fs (run %d/%d)",
                         name, delay, _attempt + 2, _RESPAWN_LIMIT)
            loop = asyncio.get_running_loop()
            loop.call_later(delay,
                            lambda: _supervise(coro_factory, name,
                                               respawn=respawn, _attempt=_attempt + 1))
        else:
            logger.error("  -> %r has crashed %d times; giving up. The liveness reaper is now "
                         "OFF: disconnected players ('ghosts') will linger until the ~50-minute "
                         "PRUDP timeout. Restart the server to restore it.", name, _RESPAWN_LIMIT)

    task.add_done_callback(_done)
    return task


def _fatal_bind(port, name, exc):
    """Turn a port-already-in-use bind failure into a message a host can act on,
    instead of dumping a raw asyncio/Winsock traceback, then exit non-zero."""
    logger.error("Could not bind UDP %d (%s server): %s", port, name, exc)
    logger.error("  That port is already in use - most likely another copy of this server is "
                 "already running.")
    logger.error("  Close it (or press \"Stop Server\" in the launcher), then start this one "
                 "again.")
    raise SystemExit(1)


async def main():
    s = build_settings()
    reaper.install_rx_stamp()   # stamp last-inbound time on every PRUDP packet (before serving)
    logger.info("MH3U NEX server  |  game_server_id=0x%08X  access_key=%s  nex_version=%d",
                config.GAME_SERVER_ID, config.ACCESS_KEY, config.NEX_VERSION)
    limits.log_config()   # print the active abuse/DoS guardrail caps at startup

    auth = [AuthenticationServer(s)]
    secure = protocols.secure_servers()
    server_key = users.derive_key(users.by_pid(config.SECURE_SERVER_PID))

    async with contextlib.AsyncExitStack() as stack:
        # Enter each server separately so a bind failure names the exact port.
        # rmc.serve raises OSError (WinError 10048 on Windows) if the UDP port is
        # already held — the common "started it twice" mistake. Catch it and print
        # something actionable instead of a raw traceback.
        try:
            await stack.enter_async_context(
                rmc.serve(s, auth, config.HOST, config.AUTH_PORT))
        except OSError as e:
            _fatal_bind(config.AUTH_PORT, "auth", e)
        try:
            await stack.enter_async_context(
                rmc.serve(s, secure, config.HOST, config.SECURE_PORT, key=server_key))
        except OSError as e:
            _fatal_bind(config.SECURE_PORT, "secure", e)

        logger.info("listening: auth=%s:%d  secure=%s:%d  (Ctrl-C / enter to stop)",
                    config.HOST, config.AUTH_PORT, config.HOST, config.SECURE_PORT)
        await natcheck.start(config.HOST)
        _supervise(protocols.notify_trigger_watcher, "notify-watcher")
        _supervise(reaper.reaper_task, "reaper", respawn=True)
        try:
            await aioconsole.ainput("")
        except (EOFError, RuntimeError):
            # No interactive stdin (detached/background). Run until killed.
            logger.info("no interactive stdin; running until terminated")
            await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, EOFError):
        print("\nserver stopped")

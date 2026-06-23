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

# Make the cloned NintendoClients importable, plus this dir for local modules.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "external", "NintendoClients"))
sys.path.insert(0, _HERE)

import asyncio
import aioconsole

from nintendo.nex import rmc, authentication, common, settings

import config
import users
import protocols
import reaper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mh3u.server")


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
        response.ticket = self._ticket(user, server)
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
        response.ticket = self._ticket(src, tgt)
        logger.info("  -> issued ticket for %s -> %s (secure %s:%s)",
                    source, target, config.SERVER_ADDRESS, config.SECURE_PORT)
        return response

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


async def main():
    s = build_settings()
    reaper.install_rx_stamp()   # stamp last-inbound time on every PRUDP packet (before serving)
    logger.info("MH3U NEX server  |  game_server_id=0x%08X  access_key=%s  nex_version=%d",
                config.GAME_SERVER_ID, config.ACCESS_KEY, config.NEX_VERSION)

    auth = [AuthenticationServer(s)]
    secure = protocols.secure_servers()
    server_key = users.derive_key(users.by_pid(config.SECURE_SERVER_PID))

    async with rmc.serve(s, auth, config.HOST, config.AUTH_PORT):
        async with rmc.serve(s, secure, config.HOST, config.SECURE_PORT, key=server_key):
            logger.info("listening: auth=%s:%d  secure=%s:%d  (Ctrl-C / enter to stop)",
                        config.HOST, config.AUTH_PORT, config.HOST, config.SECURE_PORT)
            asyncio.create_task(protocols.notify_trigger_watcher())
            asyncio.create_task(reaper.reaper_task())
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

"""In-process end-to-end check: start the MH3U NEX servers and log in with a
NintendoClients test client in the same event loop. Validates the
auth -> kerberos ticket -> secure connection -> register pipeline (and fires the
protocol trace) WITHOUT needing Cemu. Proves the server logic is sound; the
Cemu-specific part is only the auth front-end.

Run:  python tests/test_local.py   (from the mh3u_server/ dir)
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # mh3u_server/ (tests live one level down)
sys.path.insert(0, os.path.join(_ROOT, "..", "external", "NintendoClients"))
sys.path.insert(0, _ROOT)

import asyncio

from nintendo.nex import rmc, backend

import config
import users
import protocols
import server


async def main():
    s = server.build_settings()
    auth = [server.AuthenticationServer(s)]
    secure = protocols.secure_servers()
    server_key = users.derive_key(users.by_pid(config.SECURE_SERVER_PID))

    async with rmc.serve(s, auth, config.HOST, config.AUTH_PORT):
        async with rmc.serve(s, secure, config.HOST, config.SECURE_PORT, key=server_key):
            print(">>> connecting test client ...")
            async with backend.connect(s, config.HOST, config.AUTH_PORT) as be:
                async with be.login_guest() as client:
                    pid = client.pid()
                    pid = pid() if callable(pid) else pid
                    print(f">>> CLIENT LOGGED IN + SECURE-CONNECTED, pid={pid}")
    print(">>> PIPELINE OK")


if __name__ == "__main__":
    asyncio.run(main())

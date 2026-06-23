"""Phase-2 end-to-end check (no Cemu/dump): two NEX clients exercise the gathering
hall. Client A logs in and CREATES a hunt-room MatchmakeSession; client B logs in,
BROWSES, finds it, and JOINS. Validates the create/browse/join server logic +
that the wire format round-trips, with the real MH3U access key.

Run:  python tests/test_matchmaking.py   (from the mh3u_server/ dir)
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # mh3u_server/ (tests live one level down)
sys.path.insert(0, os.path.join(_ROOT, "..", "external", "NintendoClients"))
sys.path.insert(0, _ROOT)

import asyncio

from nintendo.nex import rmc, backend, matchmaking, common

import config
import users
import protocols
import server


def make_session():
    s = matchmaking.MatchmakeSession()
    s.game_mode = 1                       # MH3U semantics TBD (target/quest type)
    s.attribs = [101, 0, 0, 0, 0, 0]      # e.g. attribs[0] = target monster id
    s.min_participants = 1
    s.max_participants = 4
    s.open_participation = True
    return s


def make_criteria():
    c = matchmaking.MatchmakeSessionSearchCriteria()
    c.attribs = ["", "", "", "", "", ""]  # wildcards
    c.game_mode = "1"                     # match game_mode == 1
    c.min_participants = "1"
    c.max_participants = "4"
    c.matchmake_system = "0"
    c.vacant_only = True
    c.exclude_locked = False
    return c


async def main():
    s = server.build_settings()
    auth = [server.AuthenticationServer(s)]
    secure = protocols.secure_servers()
    server_key = users.derive_key(users.by_pid(config.SECURE_SERVER_PID))

    ok = False
    async with rmc.serve(s, auth, config.HOST, config.AUTH_PORT):
        async with rmc.serve(s, secure, config.HOST, config.SECURE_PORT, key=server_key):
            # --- Client A: host a room ---
            async with backend.connect(s, config.HOST, config.AUTH_PORT) as beA:
                async with beA.login("hunter1", "huntpass1") as ca:
                    mmA = matchmaking.MatchmakeExtensionClient(ca)
                    created = await mmA.create_matchmake_session(make_session(), "MH3U test room", 1)
                    print(f">>> A created session gid=0x{created.gid:x}")

                    # --- Client B: search + join (A stays connected as host) ---
                    async with backend.connect(s, config.HOST, config.AUTH_PORT) as beB:
                        async with beB.login_guest() as cb:
                            mmB = matchmaking.MatchmakeExtensionClient(cb)
                            results = await mmB.browse_matchmake_session(
                                make_criteria(), common.ResultRange(0, 10))
                            gids = [g.id for g in results]
                            print(f">>> B browse found {len(results)} session(s): "
                                  f"{['0x%x' % g for g in gids]}")
                            assert created.gid in gids, "B did not find A's session!"

                            key = await mmB.join_matchmake_session(created.gid, "let's hunt")
                            print(f">>> B joined gid=0x{created.gid:x}, "
                                  f"session_key match={key == created.session_key}")
                            ok = key == created.session_key

    print(">>> MATCHMAKING OK" if ok else ">>> FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

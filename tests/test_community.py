"""Phase-2 community (gathering-hall) check, dump-free: a client lists the official
halls, joins one, and confirms membership via find_community_by_participant. Then a
second client joins the same hall and hosts a MatchmakeSession inside it — the full
"sit in a hall, host a room, others join from the hall" flow.

Run:  python tests/test_community.py   (from the mh3u_server/ dir)
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


def _pid(client):
    p = client.pid()
    return p() if callable(p) else p


async def main():
    s = server.build_settings()
    auth = [server.AuthenticationServer(s)]
    secure = protocols.secure_servers()
    server_key = users.derive_key(users.by_pid(config.SECURE_SERVER_PID))

    ok = False
    async with rmc.serve(s, auth, config.HOST, config.AUTH_PORT):
        async with rmc.serve(s, secure, config.HOST, config.SECURE_PORT, key=server_key):
            async with backend.connect(s, config.HOST, config.AUTH_PORT) as beA:
                async with beA.login("hunter1", "huntpass1") as ca:
                    mmA = matchmaking.MatchmakeExtensionClient(ca)
                    pidA = _pid(ca)

                    halls = await mmA.find_official_community(True, common.ResultRange(0, 10))
                    hall_ids = [h.id for h in halls]
                    print(f">>> A sees {len(halls)} official hall(s): {['0x%x' % g for g in hall_ids]}")
                    assert halls, "no official halls!"

                    hall = hall_ids[0]
                    await mmA.join_community(hall, "hello hall", "")
                    print(f">>> A joined hall 0x{hall:x}")

                    mine = await mmA.find_community_by_participant(pidA, common.ResultRange(0, 10))
                    print(f">>> A is in {len(mine)} hall(s): {['0x%x' % h.id for h in mine]}")
                    assert any(h.id == hall for h in mine), "A not listed in the hall!"

                    # B joins the same hall and hosts a room in it
                    async with backend.connect(s, config.HOST, config.AUTH_PORT) as beB:
                        async with beB.login_guest() as cb:
                            mmB = matchmaking.MatchmakeExtensionClient(cb)
                            await mmB.join_community(hall, "me too", "")
                            session = matchmaking.MatchmakeSession()
                            session.game_mode = 1
                            session.attribs = [101, 0, 0, 0, 0, 0]
                            session.min_participants = 1
                            session.max_participants = 4
                            created = await mmB.create_matchmake_session(session, "room in hall", 1)
                            print(f">>> B joined hall 0x{hall:x} and hosted room gid=0x{created.gid:x}")
                            ok = True

    print(">>> COMMUNITY OK" if ok else ">>> FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

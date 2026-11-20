"""Planned restarts that don't cut hunts short.

A restart is requested through the admin port (admin_http.py), normally right after the
host has pulled new code. The server then restarts by itself at the first good moment:

    wait=idle   once nobody is in a room (no hunt can be cut short)   <- default
    wait=empty  once nobody is online at all
    wait=now    straight away (after a short in-game warning)

Players hear about it in the chat ("Server") as it's scheduled, every 15 minutes while
it waits, and at 5 and 1 minutes before the deadline (max_minutes, default 60) when it
gives up waiting. Restarting = a clean shutdown with exit code 75, which the systemd
unit's Restart=on-failure turns into a restart a few seconds later.
"""
import asyncio
import logging
import math
import time

import announce
import matchmaking_handlers as mh

logger = logging.getLogger("mh3u.maintenance")

RESTART_EXIT_CODE = 75
TICK = 5.0
REMIND_EVERY = 15 * 60
FINAL_PAUSE = 15.0          # between "restarting now" and the actual stop

# The notices, in each language the games chat in (announce.send picks each player's).
# Each fits one chat message: 45 characters in the Western games, one 20-character line
# in the JP game (tested in game 2026-11-20; tests/test_announce.py checks the lengths).
MSG_PENDING = {
    "eng": "Server update soon: restart after hunts end.",
    "jpn": "サーバー更新：狩猟終了後に再起動します。",
    "fre": "Mise à jour : redémarrage après les chasses.",
    "ger": "Server-Update: Neustart nach den Jagden.",
    "ita": "Aggiornamento: riavvio a fine cacce.",
    "spa": "Actualización: reinicio tras las cacerías.",
}
MSG_NOW = {
    "eng": "Server restarting now. Back in a minute!",
    "jpn": "サーバーを再起動します。すぐ戻ります！",
    "fre": "Redémarrage du serveur. À tout de suite !",
    "ger": "Server startet jetzt neu. Gleich wieder da!",
    "ita": "Riavvio del server. Torniamo subito!",
    "spa": "Reiniciando el servidor. ¡Volvemos enseguida!",
}


def msg_soon(n):
    """"Restarts in n minutes", in each language."""
    one = n == 1
    return {
        "eng": f"Server restarts in {n} minute{'' if one else 's'} for an update.",
        "jpn": f"サーバー更新：{n}分後に再起動します。",
        "fre": f"Redémarrage du serveur dans {n} minute{'' if one else 's'}.",
        "ger": f"Server-Neustart in {n} Minute{'' if one else 'n'} (Update).",
        "ita": f"Riavvio del server tra {n} minut{'o' if one else 'i'}.",
        "spa": f"Reinicio del servidor en {n} minuto{'' if one else 's'}.",
    }


on_restart = None           # set by server.py: performs the clean shutdown + exit code
_plan = None


class _Plan:
    def __init__(self, wait, max_minutes):
        now = time.monotonic()
        self.wait = wait
        self.created = now
        self.deadline = now + max_minutes * 60
        self.last_notice = -1e9
        self.warned = set()          # deadline warnings already given (minutes)
        self.firing = False


def players_in_rooms():
    return sum(len(s.participants & set(mh.CLIENTS)) for s in mh.REGISTRY.sessions.values())


def ready(wait):
    if wait == "now":
        return True
    if wait == "empty":
        return not mh.CLIENTS
    return players_in_rooms() == 0


def schedule(wait="idle", max_minutes=60):
    global _plan
    if wait not in ("idle", "empty", "now"):
        raise ValueError("wait must be idle, empty or now")
    max_minutes = max(1, min(int(max_minutes), 24 * 60))
    _plan = _Plan(wait, max_minutes)
    logger.warning("restart scheduled: wait=%s, at most %d min", wait, max_minutes)
    return status()


def cancel():
    global _plan
    was = _plan is not None and not _plan.firing
    if was:
        _plan = None
        logger.warning("restart cancelled")
    return was


def status():
    if _plan is None:
        return {"scheduled": False}
    now = time.monotonic()
    return {"scheduled": True, "wait": _plan.wait, "firing": _plan.firing,
            "waiting_s": int(now - _plan.created),
            "deadline_in_s": max(0, int(_plan.deadline - now)),
            "players": len(mh.CLIENTS), "players_in_rooms": players_in_rooms()}


async def _say(text):
    if mh.CLIENTS:
        await announce.send(text)


async def _fire(reason):
    _plan.firing = True
    logger.warning("restarting now (%s)", reason)
    if mh.CLIENTS:
        await announce.send(MSG_NOW)
        await asyncio.sleep(FINAL_PAUSE)
    if on_restart:
        on_restart()


async def loop():
    """Supervised background task: carry out a scheduled restart."""
    while True:
        await asyncio.sleep(TICK)
        plan = _plan
        if plan is None or plan.firing:
            continue
        now = time.monotonic()
        if ready(plan.wait):
            await _fire(f"wait={plan.wait} satisfied")
            continue
        left = plan.deadline - now
        if left <= 0:
            await _fire("deadline reached")
            continue
        for n in (1, 5):
            if left <= n * 60 and n not in plan.warned:
                plan.warned |= {m for m in (1, 5) if m >= n}
                plan.last_notice = now
                mins = math.ceil(left / 60)      # a short deadline can start inside 5 min
                await _say(msg_soon(mins))
                break
        else:
            if now - plan.last_notice >= REMIND_EVERY:
                plan.last_notice = now
                await _say(MSG_PENDING)

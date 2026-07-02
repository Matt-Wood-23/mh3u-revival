"""Abuse / DoS guardrails for the MH3U NEX server.

Additive, env-tunable caps + rate limits that are invisible to the normal friends-only
flow and only bite on abuse. Two facts shape the design:

  * Auth is effectively OPEN (any numeric PID + the public NEX password authenticates) and
    PIDs are attacker-chosen, so the identity for abuse-accounting is the SOURCE IP, not the
    PID.
  * Handler exceptions are already contained per-request by NintendoClients' rmc.handle_request
    (no crash-all / RCE surface), so these guards target availability + griefing.

Every guard is fail-OPEN (an internal error allows, never breaks a handler), defaults to
beta-safe values, and logs each rejection.
"""
import os
import time
import logging

logger = logging.getLogger("mh3u.limits")


def _int_env(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _float_env(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _bool_env(name, default):
    v = os.environ.get(name)
    if v is None:
        return default
    return v not in ("0", "", "false", "False", "no", "off")


# --- caps (beta-safe defaults; the stress harness raises these via env) ---------------
MAX_CONNECTIONS           = _int_env("MH3U_MAX_CONNECTIONS", 128)          # global live secure connections
MAX_CONNECTIONS_PER_IP    = _int_env("MH3U_MAX_CONNECTIONS_PER_IP", 16)    # per source IP (loopback exempt)
MAX_ROOMS                 = _int_env("MH3U_MAX_ROOMS", 48)                 # global live hunt rooms
MAX_ROOM_PARTICIPANTS     = _int_env("MH3U_MAX_ROOM_PARTICIPANTS", 32)     # fail-safe per-room ceiling
MAX_RUNTIME_COMMUNITIES   = _int_env("MH3U_MAX_RUNTIME_COMMUNITIES", 64)   # global runtime-created halls
MAX_COMMUNITIES_PER_OWNER = _int_env("MH3U_MAX_COMMUNITIES_PER_OWNER", 4)
MAX_GID_LIST              = _int_env("MH3U_MAX_GID_LIST", 64)              # bound on client-supplied id/url lists
SHOUTS_PER_SEC            = _float_env("MH3U_SHOUTS_PER_SEC", 4.0)
SHOUT_BURST               = _int_env("MH3U_SHOUT_BURST", 8)
# Broadcast a shout to ALL live clients when the sender isn't in a tracked gathering.
# Beta default ON (the current, shout-working behavior — never break shouts). A bigger /
# public server should set 0 so a shout only reaches the sender's own gathering, removing
# the all-players amplification vector.
SHOUT_BROADCAST_FALLBACK  = _bool_env("MH3U_SHOUT_BROADCAST_FALLBACK", True)


def log_config():
    logger.info(
        "guardrails: conns=%d/ip=%d rooms=%d/room=%d comms=%d/owner=%d shout=%.1f/s burst=%d "
        "bcast_fallback=%s gidlist=%d",
        MAX_CONNECTIONS, MAX_CONNECTIONS_PER_IP, MAX_ROOMS, MAX_ROOM_PARTICIPANTS,
        MAX_RUNTIME_COMMUNITIES, MAX_COMMUNITIES_PER_OWNER, SHOUTS_PER_SEC, SHOUT_BURST,
        SHOUT_BROADCAST_FALLBACK, MAX_GID_LIST)


def remote_ip(client):
    """Source IP of a live RMC client, or None if unavailable (fail-open)."""
    try:
        addr = client.remote_address()
        return addr[0] if addr else None
    except Exception:
        return None


def is_loopback(ip):
    return bool(ip) and (ip.startswith("127.") or ip in ("::1", "localhost"))


# --- global connection cap -----------------------------------------------------------
def global_connection_ok(is_new_pid, current_count):
    """(ok, reason). A reconnect (pid already present) is never blocked. Fail-open."""
    try:
        if is_new_pid and current_count >= MAX_CONNECTIONS:
            return False, "global connection cap (%d) reached" % MAX_CONNECTIONS
        return True, ""
    except Exception:
        return True, ""


# --- per-IP live-connection accounting -----------------------------------------------
_ip_conns = {}   # ip -> count of live connections (loopback not tracked)


def ip_can_connect(ip):
    """(ok, reason). Loopback (the co-located host) is exempt. Fail-open."""
    try:
        if not ip or is_loopback(ip):
            return True, ""
        if _ip_conns.get(ip, 0) >= MAX_CONNECTIONS_PER_IP:
            return False, "per-IP connection cap (%d) reached for %s" % (MAX_CONNECTIONS_PER_IP, ip)
        return True, ""
    except Exception:
        return True, ""


def ip_add(ip):
    if not ip or is_loopback(ip):
        return
    _ip_conns[ip] = _ip_conns.get(ip, 0) + 1


def ip_remove(ip):
    if not ip or is_loopback(ip):
        return
    n = _ip_conns.get(ip, 0) - 1
    if n <= 0:
        _ip_conns.pop(ip, None)
    else:
        _ip_conns[ip] = n


# --- shout token bucket (per sender pid) ---------------------------------------------
_shout_buckets = {}   # pid -> (tokens, last_monotonic)


def shout_allowed(pid):
    """Token-bucket rate limit for shout RELAY only — NEVER gates the RMC reply (gating the
    reply would re-lock the client's send-gate, the 2026-06-30 bug). Fail-open."""
    try:
        now = time.monotonic()
        tokens, last = _shout_buckets.get(pid, (float(SHOUT_BURST), now))
        tokens = min(float(SHOUT_BURST), tokens + (now - last) * SHOUTS_PER_SEC)
        if tokens >= 1.0:
            _shout_buckets[pid] = (tokens - 1.0, now)
            return True
        _shout_buckets[pid] = (tokens, now)
        return False
    except Exception:
        return True


def forget_pid(pid):
    """Drop per-pid abuse state on logout so the bucket dict can't grow unbounded."""
    _shout_buckets.pop(pid, None)


def bound_list(seq, limit=None):
    """Clamp a client-supplied list to a sane length (fail-open to [] on error)."""
    try:
        n = MAX_GID_LIST if limit is None else limit
        return list(seq)[:n]
    except Exception:
        return []

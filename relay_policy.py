"""In-memory auto-relay policy.

This module stores only process-local hints. It does not persist endpoint data or
operator settings; a restart returns auto relay to a clean slate.
"""
import logging
import time

import config

logger = logging.getLogger("mh3u.relay_policy")

CLIENTS = {}  # pid -> state
PAIRS = {}    # (low_pid, high_pid) -> state
RECENT_RESULTS = {}  # (pid, cid, success) -> monotonic timestamp

_RESULT_DEDUPE_TTL = 5.0


def _now():
    return time.monotonic()


def _pair_key(a, b):
    if a is None or b is None or a == b:
        return None
    return (a, b) if a < b else (b, a)


def _csv_ints(text):
    out = set()
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part, 0))
        except ValueError:
            logger.warning("auto relay: ignoring invalid NAT flag value %r", part)
    return out


def _bad_nat(natm, natf):
    bad_natm = _csv_ints(config.RELAY_AUTO_BAD_NATM)
    bad_natf = _csv_ints(config.RELAY_AUTO_BAD_NATF)
    return (natm in bad_natm) or (natf in bad_natf)


def _client(pid, now=None):
    if pid is None:
        return None
    now = _now() if now is None else now
    st = CLIENTS.get(pid)
    if st is None:
        st = {
            "pid": pid,
            "natm": None,
            "natf": None,
            "rtt": None,
            "last_seen": now,
            "plane_mismatch": 0,
            "direct_failures": 0,
            "direct_successes": 0,
            "relay_until": 0.0,
            "bad_nat": False,
        }
        CLIENTS[pid] = st
    else:
        st["last_seen"] = now
    return st


def _prune(now=None):
    now = _now() if now is None else now
    for key, ts in list(RECENT_RESULTS.items()):
        if now - ts > _RESULT_DEDUPE_TTL:
            RECENT_RESULTS.pop(key, None)

    max_clients = max(0, config.RELAY_AUTO_MAX_CLIENTS)
    if max_clients == 0:
        CLIENTS.clear()
    elif len(CLIENTS) > max_clients:
        victims = sorted(
            CLIENTS.values(),
            key=lambda st: (st.get("relay_until", 0) > now, st.get("last_seen", 0)),
        )
        for st in victims[:len(CLIENTS) - max_clients]:
            CLIENTS.pop(st["pid"], None)

    max_pairs = max(0, config.RELAY_AUTO_MAX_PAIRS)
    if max_pairs == 0:
        PAIRS.clear()
    elif len(PAIRS) > max_pairs:
        expired = [k for k, st in PAIRS.items() if st.get("relay_until", 0) <= now]
        for key in sorted(expired, key=lambda k: PAIRS[k].get("last_seen", 0)):
            if len(PAIRS) <= max_pairs:
                break
            PAIRS.pop(key, None)
        if len(PAIRS) > max_pairs:
            victims = sorted(PAIRS, key=lambda k: PAIRS[k].get("last_seen", 0))
            for key in victims[:len(PAIRS) - max_pairs]:
                PAIRS.pop(key, None)


def record_seen(pid, now=None):
    _client(pid, now)
    _prune(now)


def record_nat_properties(pid, natm, natf, rtt, now=None):
    now = _now() if now is None else now
    st = _client(pid, now)
    if st is None:
        return
    st["natm"] = natm
    st["natf"] = natf
    st["rtt"] = rtt
    st["bad_nat"] = _bad_nat(natm, natf)
    if st["bad_nat"]:
        st["relay_until"] = max(st.get("relay_until", 0), now + config.RELAY_AUTO_CLIENT_TTL)
        logger.info("auto relay: pid=%s marked relay-worthy by NAT flags natm=%s natf=%s until %.0f",
                    pid, natm, natf, st["relay_until"])
    _prune(now)


def nat_of(pid):
    """Last (natm, natf) this pid reported, or (None, None) if it never did.

    Read-only view for callers that need to explain a link failure rather than decide
    relay policy -- see the guest-pair warning in protocols.py.
    """
    st = CLIENTS.get(pid)
    if st is None:
        return None, None
    return st.get("natm"), st.get("natf")


def record_plane_mismatch(pid, self_reported, reflexive, now=None):
    st = _client(pid, now)
    if st is None:
        return
    st["plane_mismatch"] = st.get("plane_mismatch", 0) + 1
    st["last_self_reported"] = self_reported
    st["last_reflexive"] = reflexive
    _prune(now)


def record_pair_result(a, b, success, now=None):
    key = _pair_key(a, b)
    if key is None:
        return
    now = _now() if now is None else now
    for pid in key:
        st = _client(pid, now)
        if st is not None:
            if success:
                st["direct_successes"] = st.get("direct_successes", 0) + 1
            else:
                st["direct_failures"] = st.get("direct_failures", 0) + 1
    st = PAIRS.get(key)
    if st is None:
        st = {
            "failures": 0,
            "successes": 0,
            "last_seen": now,
            "last_failure": 0.0,
            "relay_until": 0.0,
        }
        PAIRS[key] = st
    st["last_seen"] = now
    if success:
        st["successes"] = st.get("successes", 0) + 1
    else:
        st["failures"] = st.get("failures", 0) + 1
        st["last_failure"] = now
        st["relay_until"] = now + config.RELAY_AUTO_PAIR_TTL
        logger.info("auto relay: pair %s:%s marked for relay after direct failure until %.0f",
                    key[0], key[1], st["relay_until"])
    _prune(now)


def record_probe_result(a, b, cid, success, now=None):
    if _pair_key(a, b) is None:
        return False
    now = _now() if now is None else now
    result_key = (a, cid, bool(success))
    prev = RECENT_RESULTS.get(result_key)
    if prev is not None and now - prev <= _RESULT_DEDUPE_TTL:
        return False
    RECENT_RESULTS[result_key] = now
    record_pair_result(a, b, success, now)
    return True


def decide(host_pid, guest_pid, now=None):
    key = _pair_key(host_pid, guest_pid)
    if key is None:
        return False, "invalid_pair"
    now = _now() if now is None else now
    pair = PAIRS.get(key)
    if pair and pair.get("relay_until", 0) > now:
        return True, "recent_pair_failure"
    for pid in key:
        st = CLIENTS.get(pid)
        if st and st.get("relay_until", 0) > now:
            return True, "client_nat_flags"
    return False, "no_risk_signal"


def should_relay(host_pid, guest_pid, now=None):
    selected, _reason = decide(host_pid, guest_pid, now)
    return selected


def reset_for_tests():
    CLIENTS.clear()
    PAIRS.clear()
    RECENT_RESULTS.clear()

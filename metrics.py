"""Play metrics for the host: busiest hours, unique players, playtime, connection health.

Admin only: the dashboard's Metrics section reads GET /metrics on the admin port
(admin_http.py). The public status page never shows any of it.

What is kept, one JSON line each, in <state dir>/metrics/events-YYYY-MM.jsonl:
  session  one per finished session: PID, hunter name and HR, start/end, time in rooms,
           hall, game build (JP or not), round trip to the server, how it ended, and
           country + state/province (from the IP, when geoip.py has a database)
  hour     one per UTC hour: players online (average, most), rooms, players in rooms,
           relay bytes sent, chat messages
  room     one per room: when, host, most players at once, who was in it
  join     one per join into a room that already had players: did the joiner stay?
  link     one per player-to-player link the server brokered: did it come up, how fast,
           host or guest pair, relayed or direct
  start/stop  server starts (and whether the last run crashed) and stops
No IP addresses (or cities). Files older than MH3U_METRICS_MONTHS (default 13) months are deleted.

On where the other saved counters are (a public server: status page or Discord), unless
MH3U_METRICS=0; MH3U_METRICS=1 turns it on anywhere. deploy/metrics_backfill.py builds the
same records from the server's journal for the time before this existed.

A player counts once their game sends its status with a hunter name: load-test clients
and connections that never reach a hall don't. Every hook does nothing while metrics are
off, and none of them raises.
"""
import asyncio
import json
import logging
import os
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

import geoip
import limits

logger = logging.getLogger("mh3u.metrics")

STATE_DIR = Path(os.environ.get("MH3U_STATE_DIR") or os.environ.get("STATE_DIRECTORY")
                 or "state")
SUBDIR = "metrics"
OPEN_FILE = "open.json"
KEEP_MONTHS = max(1, limits._int_env("MH3U_METRICS_MONTHS", 13))
SWITCH = os.environ.get("MH3U_METRICS", "").strip().lower()
SAMPLE_SECONDS = 60
JOIN_WINDOW = 60       # a joiner still in the room this long after joining "stayed"
LINK_WINDOW = 30       # a brokered link with no result=True by then failed
NO_NAME = {"", "No Name"}
REPORT_CACHE_SECONDS = 60

_rec = None            # the live Recorder, once start() has run
_report_cache = {}


def _hour(t):
    return int(t // 3600) * 3600


def _month(t):
    return time.strftime("%Y-%m", time.gmtime(t))


class Recorder:
    """The state behind the hooks. live=True keeps open.json (open sessions survive a
    crash as 'ended at the last save'); the backfill runs one with live=False."""

    def __init__(self, folder, live=True, backfill=False):
        self.dir = Path(folder)
        self.live = live
        self.tag = {"bf": 1} if backfill else {}
        self.sessions = {}      # pid -> session dict
        self.rooms = {}         # gid -> room dict
        self.joins = []         # joins not yet decided
        self.links = {}         # (gid, low pid, high pid) -> link not yet decided
        self.hour = None        # this hour's running totals
        self.relay_last = None  # [UTC day, relay bytes sent today] at the last sample

    # --- files -------------------------------------------------------------------
    def _write(self, rec):
        rec.update(self.tag)
        t = rec.get("t1", rec.get("t"))
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            with open(self.dir / f"events-{_month(t)}.jsonl", "a", encoding="utf-8",
                      newline="\n") as f:
                f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
        except OSError as e:
            logger.warning("metrics: can't write %s (%s)", self.dir, e)

    def _save_open(self, now, running=True):
        if not self.live:
            return
        state = {"running": running, "t": now, "hour": self.hour,
                 "relay_last": self.relay_last,
                 "sessions": {str(p): s for p, s in self.sessions.items()} if running else {}}
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = self.dir / (OPEN_FILE + ".tmp")
            tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.dir / OPEN_FILE)
        except OSError as e:
            logger.warning("metrics: can't save %s (%s)", self.dir / OPEN_FILE, e)

    def _load_open(self):
        try:
            st = json.loads((self.dir / OPEN_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return st if isinstance(st, dict) else None

    def _prune(self, now):
        y, m = map(int, _month(now).split("-"))
        idx = y * 12 + m - 1 - KEEP_MONTHS
        oldest = "%04d-%02d" % (idx // 12, idx % 12 + 1)
        for p in self.dir.glob("events-*.jsonl"):
            if p.stem[len("events-"):] < oldest:
                try:
                    p.unlink()
                    logger.info("metrics: deleted %s (older than %d months)", p.name, KEEP_MONTHS)
                except OSError:
                    pass

    # --- server life -------------------------------------------------------------
    def start(self, now):
        crash, down_from = False, None
        if self.live:
            st = self._load_open()
            if st and st.get("running"):
                # The last run never said goodbye: close what it had open at its last save.
                crash, down_from = True, st.get("t") or now
                for s in (st.get("sessions") or {}).values():
                    if isinstance(s, dict) and "pid" in s:
                        self._close(s, down_from, "crash")
                if isinstance(st.get("hour"), dict):
                    self.hour = st["hour"]
                    self._flush_hour()
            if st and isinstance(st.get("relay_last"), list):
                self.relay_last = st["relay_last"]
            self._prune(now)
        self._write({"k": "start", "t": int(now), "crash": crash,
                     "down_from": int(down_from) if down_from else None})
        self._save_open(now)

    def stop(self, now, restart=False):
        self.joins.clear()                   # undecided at shutdown: not counted
        self.links.clear()
        for gid in list(self.rooms):
            self.room_closed(gid, now)
        for pid in list(self.sessions):
            self._end(pid, now, "shutdown")
        self._flush_hour()
        self._write({"k": "stop", "t": int(now), "restart": bool(restart)})
        self._save_open(now, running=False)

    # --- players -----------------------------------------------------------------
    def login(self, pid, now, place=None):
        s = self.sessions.get(pid)
        if s is not None:                    # a reconnect before the old connection closed
            s["reconnects"] += 1
        else:
            s = self.sessions[pid] = {
                "pid": pid, "t0": now, "name": "", "hr": None, "hall": "", "jp": None,
                "rtt": None, "room_s": 0.0, "room": None, "room_since": None, "rooms": 0,
                "hosted": 0, "reconnects": 0, "dropped": False}
        if place:
            s["cc"], s["region"] = place

    def logout(self, pid, now):
        s = self.sessions.get(pid)
        if s is None:
            return
        if s["room"] is not None:
            self.room_left(s["room"], pid, "logout", now)
        self._end(pid, now, "logout")

    def _end(self, pid, now, how):
        s = self.sessions.pop(pid, None)
        if s is None:
            return
        self._close(s, now, how)

    def _close(self, s, now, how):
        if s.get("room_since") is not None:
            s["room_s"] += max(0.0, now - s["room_since"])
        self._write({"k": "session", "pid": s["pid"], "t0": int(s["t0"]), "t1": int(now),
                     "name": s.get("name", ""), "hr": s.get("hr"), "hall": s.get("hall", ""),
                     "jp": s.get("jp"), "rtt": s.get("rtt"), "room_s": int(s["room_s"]),
                     "rooms": s.get("rooms", 0), "hosted": s.get("hosted", 0),
                     "reconnects": s.get("reconnects", 0), "dropped": bool(s.get("dropped")),
                     "end": how,
                     **({"cc": s["cc"], "region": s.get("region", "")} if s.get("cc") else {})})

    def presence(self, pid, raw, now):
        f = str(raw or "").split("\t")
        if len(f) < 10:
            return
        name = f[8].strip()[:32]
        if name in NO_NAME:
            return
        s = self.sessions.get(pid)
        if s is None:                        # (backfill: logged in before the log starts)
            self.login(pid, now)
            s = self.sessions[pid]
        new = not s["name"]
        s["name"] = name
        if f[9].isdigit() and int(f[9]) > 0:
            s["hr"] = int(f[9])
        if new:
            if s["room"] is not None:
                r = self.rooms.get(s["room"])
                if r is not None and s["jp"] is not None:
                    r["games"].add(s["jp"])
            a = self._acc(now)
            a["max"] = max(a["max"], self._named())

    def hall(self, pid, label, jp, now):
        s = self.sessions.get(pid)
        if s is not None:
            s["hall"] = str(label or "")[:40]
            s["jp"] = bool(jp)

    def rtt(self, pid, ms, now):
        s = self.sessions.get(pid)
        if s is not None and s["rtt"] is None and isinstance(ms, int) and ms > 0:
            s["rtt"] = ms

    def chat(self, pid, now):
        self._acc(now)["chat"] += 1

    def _named(self):
        return sum(1 for s in self.sessions.values() if s["name"])

    # --- rooms -------------------------------------------------------------------
    def _new_room(self, gid, host, now):
        hs = self.sessions.get(host) if host is not None else None
        r = {"gid": gid, "t0": now, "host": host, "members": set(), "seen": set(), "max": 0,
             "done": set(), "games": set(), "hall": hs["hall"] if hs else ""}
        self.rooms[gid] = r
        return r

    def _enter(self, r, pid, now):
        r["members"].add(pid)
        r["seen"].add(pid)
        r["max"] = max(r["max"], len(r["members"]))
        s = self.sessions.get(pid)
        if s is not None:
            if s["room"] is not None and s["room"] != r["gid"]:
                self._leave_time(s, now)
            s["room"], s["room_since"] = r["gid"], now
            if s["jp"] is not None:
                r["games"].add(s["jp"])

    def _leave_time(self, s, now):
        if s["room_since"] is not None:
            s["room_s"] += max(0.0, now - s["room_since"])
        s["room"], s["room_since"] = None, None

    def room_created(self, gid, host, now):
        if gid in self.rooms:
            self.room_closed(gid, now)
        r = self._new_room(gid, host, now)
        self._enter(r, host, now)
        s = self.sessions.get(host)
        if s is not None:
            s["hosted"] += 1

    def room_joined(self, gid, pid, now):
        r = self.rooms.get(gid) or self._new_room(gid, None, now)
        if pid in r["members"]:
            return
        others = len(r["members"])
        self._enter(r, pid, now)
        s = self.sessions.get(pid)
        if s is not None:
            s["rooms"] += 1
        if others:
            self.joins.append({"t": now, "pid": pid, "gid": gid, "host": r["host"],
                               "others": others})

    def room_left(self, gid, pid, how, now):
        r = self.rooms.get(gid)
        if r is None or pid not in r["members"]:
            return
        r["members"].discard(pid)
        r["done"] = {k for k in r["done"] if pid not in k}
        s = self.sessions.get(pid)
        if s is not None and s["room"] == gid:
            self._leave_time(s, now)
            if how == "logout" and r["members"]:
                s["dropped"] = True
        self._decide_joins(lambda j: j["pid"] == pid and j["gid"] == gid, now, how)
        for key in [k for k in self.links if k[0] == gid and pid in k[1:]]:
            self._decide_link(key, now, False)

    def room_closed(self, gid, now):
        r = self.rooms.pop(gid, None)
        if r is None:
            return
        for pid in r["members"]:
            s = self.sessions.get(pid)
            if s is not None and s["room"] == gid:
                self._leave_time(s, now)
        self._decide_joins(lambda j: j["gid"] == gid, now, "closed")
        for key in [k for k in self.links if k[0] == gid]:
            del self.links[key]              # the room went away first: not counted
        self._write({"k": "room", "gid": gid, "t0": int(r["t0"]), "t1": int(now),
                     "host": r["host"], "max": r["max"], "members": sorted(r["seen"]),
                     "jp_mix": len(r["games"]) > 1, "hall": r["hall"]})

    def _decide_joins(self, pred, now, how):
        keep = []
        for j in self.joins:
            if not pred(j):
                keep.append(j)
                continue
            self._write({"k": "join", "t": int(j["t"]), "pid": j["pid"], "gid": j["gid"],
                         "host": j["host"], "others": j["others"],
                         "stayed": None if how == "closed" else (how is None),
                         "secs": None if how is None else round(now - j["t"], 1),
                         "how": how})
        self.joins = keep

    # --- links -------------------------------------------------------------------
    def probe(self, caller, target, relayed, now):
        r = next((r for r in self.rooms.values()
                  if caller in r["members"] and target in r["members"]), None)
        if r is None or caller == target:
            return
        lo, hi = sorted((caller, target))
        key = (r["gid"], lo, hi)
        if key in self.links:
            self.links[key]["relayed"] |= bool(relayed)
            return
        if (lo, hi) in r["done"]:
            return                           # decided already while both stayed in the room
        host = r["host"]
        self.links[key] = {"t": now, "a": lo, "b": hi, "host": host,
                           "guest": None if host is None else host not in (lo, hi),
                           "relayed": bool(relayed)}

    def link_result(self, pid, other, ok, now):
        if other is None:
            return
        pair = tuple(sorted((pid, other)))
        for key in list(self.links):
            if key[1:] == pair:
                self._decide_link(key, now, bool(ok))
                return

    def _decide_link(self, key, now, ok):
        l = self.links.pop(key)
        r = self.rooms.get(key[0])
        if r is not None:
            r["done"].add(key[1:])
        self._write({"k": "link", "t": int(l["t"]), "a": l["a"], "b": l["b"],
                     "host": l["host"], "guest": l["guest"], "relayed": l["relayed"],
                     "ok": ok, "secs": round(now - l["t"], 1)})

    # --- time --------------------------------------------------------------------
    def _acc(self, now):
        h = _hour(now)
        if self.hour is not None and self.hour["t"] != h:
            self._flush_hour()
        if self.hour is None:
            self.hour = {"t": h, "n": 0, "sum": 0, "max": 0, "rooms": 0, "in_rooms": 0,
                         "relay_out": 0, "chat": 0}
        return self.hour

    def _hour_record(self):
        a = self.hour
        if not a or not (a["n"] or a["chat"] or a["relay_out"]):
            return None
        n = a["n"] or 1
        return {"k": "hour", "t": a["t"], "n": a["n"], "avg": round(a["sum"] / n, 2),
                "max": a["max"], "rooms": a["rooms"], "in_rooms": round(a["in_rooms"] / n, 2),
                "relay_out": a["relay_out"], "chat": a["chat"]}

    def _flush_hour(self):
        rec = self._hour_record()
        self.hour = None
        if rec:
            self._write(rec)

    def open_hour(self):
        """This hour so far, shaped like a written hour (for the report)."""
        rec = self._hour_record()
        return [rec] if rec else []

    def tick(self, now):
        self._decide_joins(lambda j: now - j["t"] >= JOIN_WINDOW, now, None)
        for key in [k for k, l in self.links.items() if now - l["t"] >= LINK_WINDOW]:
            self._decide_link(key, now, False)

    def sample(self, now, relay_out_today=None):
        """Once a minute: decide timed-out joins/links and add a sample to this hour."""
        self.tick(now)
        a = self._acc(now)
        named = self._named()
        a["n"] += 1
        a["sum"] += named
        a["max"] = max(a["max"], named)
        live_rooms = [r for r in self.rooms.values()
                      if any(self.sessions.get(p, {}).get("name") for p in r["members"])]
        a["rooms"] = max(a["rooms"], len(live_rooms))
        a["in_rooms"] += sum(1 for r in live_rooms for p in r["members"]
                             if self.sessions.get(p, {}).get("name"))
        if relay_out_today is not None:
            day = time.strftime("%Y-%m-%d", time.gmtime(now))
            last = self.relay_last
            if last is None:
                delta = 0                    # no baseline yet
            elif last[0] == day and relay_out_today >= last[1]:
                delta = relay_out_today - last[1]
            else:
                delta = relay_out_today      # a new UTC day: its count started at 0
            a["relay_out"] += int(delta)
            self.relay_last = [day, int(relay_out_today)]
        self._save_open(now)

    def open_sessions(self, now):
        """The sessions still open, shaped like finished ones (for the report)."""
        out = []
        for s in self.sessions.values():
            room_s = s["room_s"] + (now - s["room_since"] if s["room_since"] is not None else 0)
            out.append({"k": "session", "pid": s["pid"], "t0": int(s["t0"]), "t1": int(now),
                        "name": s["name"], "hr": s["hr"], "hall": s["hall"], "jp": s["jp"],
                        "rtt": s["rtt"], "room_s": int(room_s), "rooms": s["rooms"],
                        "hosted": s["hosted"], "reconnects": s["reconnects"],
                        "dropped": False, "end": "open"})
        return out


# --- module API: the hooks the server calls -------------------------------------

def enabled():
    return _rec is not None


def start(persist, folder=None, now=None):
    """Call once at startup. persist=True on a public server (status page or Discord)."""
    global _rec
    on = SWITCH in ("1", "true", "yes", "on") or (persist and SWITCH not in ("0", "false",
                                                                             "no", "off"))
    if not on:
        return False
    _rec = Recorder(folder or STATE_DIR / SUBDIR)
    _rec.start(time.time() if now is None else now)
    logger.info("metrics: recording to %s (admin page: Metrics)", _rec.dir)
    _geoip_load()
    return True


def _geoip_load():
    try:
        geoip.load()
    except Exception:
        logger.warning("metrics: geoip load failed", exc_info=True)


def stop(restart=False, now=None):
    global _rec
    if _rec is not None:
        _call("stop", restart=restart, now=now)
        _rec = None


def _call(name, *args, now=None, **kw):
    """Run Recorder.<name>(*args, now, **kw); metrics must never break the server."""
    if _rec is None:
        return
    try:
        getattr(_rec, name)(*args, time.time() if now is None else now, **kw)
    except Exception:
        logger.warning("metrics: %s failed", name, exc_info=True)


def login(pid, ip=None, now=None):
    """ip: the address the player connects from; only its country/region is kept."""
    if _rec is None:
        return
    try:
        where = geoip.place(ip)
    except Exception:
        where = None
    _call("login", pid, now=now, place=where)


def logout(pid, now=None):
    _call("logout", pid, now=now)


def presence(pid, raw, now=None):
    _call("presence", pid, raw, now=now)


def hall(pid, label, jp, now=None):
    _call("hall", pid, label, jp, now=now)


def rtt(pid, ms, now=None):
    _call("rtt", pid, ms, now=now)


def chat(pid, now=None):
    _call("chat", pid, now=now)


def room_created(gid, host, now=None):
    _call("room_created", gid, host, now=now)


def room_joined(gid, pid, now=None):
    _call("room_joined", gid, pid, now=now)


def room_left(gid, pid, how, now=None):
    _call("room_left", gid, pid, how, now=now)


def room_closed(gid, now=None):
    _call("room_closed", gid, now=now)


def probe(caller, target, relayed, now=None):
    _call("probe", caller, target, relayed, now=now)


def link_result(pid, other, ok, now=None):
    _call("link_result", pid, other, ok, now=now)


def sample(now=None):
    if _rec is None:
        return
    _geoip_load()                            # picks up a new monthly database
    try:
        import server_stats
        out_today = server_stats.relay_totals()["bytes_out_today"]
    except Exception:
        out_today = None
    try:
        _rec.sample(time.time() if now is None else now, out_today)
    except Exception:
        logger.warning("metrics: sample failed", exc_info=True)


async def loop():
    """Supervised background task: one sample a minute."""
    while True:
        await asyncio.sleep(SAMPLE_SECONDS)
        sample()


# --- the report (GET /metrics) ----------------------------------------------------

def load_records(folder):
    out = []
    for p in sorted(Path(folder).glob("events-*.jsonl")):
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(r, dict) and "k" in r:
                        out.append(r)
        except OSError:
            continue
    return out


def open_snapshot(now=None):
    """The open sessions and this hour so far, copied (call on the event loop; report()
    may run in a thread)."""
    if _rec is None:
        return []
    return _rec.open_sessions(time.time() if now is None else now) + _rec.open_hour()


def report(now=None, tz_minutes=0, open_now=None, days=30):
    """The dashboard's numbers for the last `days` days (0 = all). tz_minutes = the
    browser's getTimezoneOffset() (minutes behind UTC), so days and hours are the viewer's
    own. open_now = open_snapshot() taken on the event loop. Cached for a minute."""
    if _rec is None:
        return {"enabled": False}
    now = time.time() if now is None else now
    tz_minutes = max(-14 * 60, min(14 * 60, int(tz_minutes)))
    days = days if days in (7, 30) else 0
    key = (tz_minutes, days)
    hit = _report_cache.get(key)
    if hit and now - hit[0] < REPORT_CACHE_SECONDS:
        return hit[1]
    recs = load_records(_rec.dir) + (open_snapshot(now) if open_now is None else open_now)
    out = build_report(recs, now, tz_minutes, days)
    for k in [k for k, v in _report_cache.items() if now - v[0] >= REPORT_CACHE_SECONDS]:
        del _report_cache[k]
    _report_cache[key] = (now, out)
    return out


def _median(xs):
    return statistics.median(xs) if xs else None


def build_report(recs, now, tz_minutes=0, days=30):
    """Pure: records -> the report dict. Every section covers the same window, the last
    `days` days (None or 0 = everything recorded); the player counts at the top keep their
    own fixed windows (today, 7 and 30 days, all time)."""
    shift = -tz_minutes * 60                 # UTC seconds -> the viewer's local seconds
    DAY = 86400

    def lday(t):
        return int((t + shift) // DAY)       # local day number

    def dstr(d):
        return time.strftime("%Y-%m-%d", time.gmtime(d * DAY))

    def day_bounds(d):
        return d * DAY - shift, (d + 1) * DAY - shift

    today = lday(now)
    by_kind = defaultdict(list)
    for r in recs:
        by_kind[r.get("k")].append(r)
    sessions = [s for s in by_kind["session"] if s.get("name")]
    named = {s["pid"] for s in sessions}
    since = min([r.get("t0", r.get("t", now)) for r in recs] or [now])
    w0 = max(since, now - days * DAY) if days else since
    first_day = max(lday(w0), today - 89)    # daily series: at most 90 days
    day_range = range(first_day, today + 1)

    # Who is who: a PID's most-played hunter name; HR from its latest session.
    name_time = defaultdict(Counter)
    latest, first, last = {}, {}, {}
    by_pid = defaultdict(list)
    for s in sessions:
        p = s["pid"]
        by_pid[p].append(s)
        name_time[p][s["name"]] += max(1, s["t1"] - s["t0"])
        if s.get("hr") and (p not in latest or s["t1"] >= latest[p][0]):
            latest[p] = (s["t1"], s["hr"])
        first[p] = min(first.get(p, s["t0"]), s["t0"])
        last[p] = max(last.get(p, s["t1"]), s["t1"])

    def who(p):
        names = [n for n, _ in name_time[p].most_common()]
        return {"pid": p, "name": names[0] if names else "?", "others": names[1:4],
                "hr": latest.get(p, (0, None))[1]}

    def active(t0, t1):
        return {s["pid"] for s in sessions if s["t1"] >= t0 and s["t0"] <= t1}

    win = [s for s in sessions if s["t1"] >= w0]

    # Players.
    players = {
        "today": len(active(day_bounds(today)[0], now)),
        "week": len(active(now - 7 * DAY, now)),
        "month": len(active(now - 30 * DAY, now)),
        "all": len(named),
        "period": len({s["pid"] for s in win}),
        "new_period": sum(1 for p in named if first[p] >= w0),
    }
    players["days"] = []
    for d in day_range:
        a, b = day_bounds(d)
        players["days"].append({"day": dstr(d), "unique": len(active(a, b - 1)),
                                "new": sum(1 for p in named if a <= first[p] < b)})
    eligible = [p for p in named if w0 <= first[p] <= now - 7 * DAY]
    returned = 0
    for p in eligible:
        cut = day_bounds(lday(first[p]))[1]
        if any(cut <= s["t0"] <= first[p] + 7 * DAY for s in by_pid[p]):
            returned += 1
    players["returning"] = {"eligible": len(eligible), "returned": returned}

    # Hours: merge records of one hour (a restart splits it), weighted by samples.
    hours = {}
    for h in by_kind["hour"]:
        m = hours.setdefault(h["t"], {"n": 0, "sum": 0.0, "max": 0, "relay_out": 0, "chat": 0})
        m["n"] += h.get("n", 0)
        m["sum"] += h.get("avg", 0) * h.get("n", 0)
        m["max"] = max(m["max"], h.get("max", 0))
        m["relay_out"] += h.get("relay_out", 0)
        m["chat"] += h.get("chat", 0)
    heat = [[[] for _ in range(24)] for _ in range(7)]
    by_hour = [[] for _ in range(24)]
    peak_all = {"players": 0, "t": None}
    peak_win = {"players": 0, "t": None}
    peak_today = 0
    for t in sorted(hours):
        m = hours[t]
        if m["max"] > peak_all["players"]:
            peak_all = {"players": m["max"], "t": t}
        if t + 3600 <= w0:
            continue
        if m["max"] > peak_win["players"]:
            peak_win = {"players": m["max"], "t": t}
        if lday(t) == today:
            peak_today = max(peak_today, m["max"])
        if m["n"]:
            avg = m["sum"] / m["n"]
            local = t + shift
            wd = (int(local // DAY) + 3) % 7        # 0 = Monday (day 0 was a Thursday)
            hr = int(local % DAY // 3600)
            heat[wd][hr].append(avg)
            by_hour[hr].append(avg)
    busiest = {
        "heat": [[round(sum(c) / len(c), 2) if c else None for c in row] for row in heat],
        "by_hour": [round(sum(c) / len(c), 2) if c else None for c in by_hour],
        "days_covered": len({lday(t) for t in hours if t + 3600 > w0}),
    }

    # Leaderboard: time in rooms (and online) inside the window.
    room, online, count = Counter(), Counter(), Counter()
    for s in win:
        span = max(1, s["t1"] - s["t0"])
        inside = s["t1"] - max(s["t0"], w0)
        room[s["pid"]] += s.get("room_s", 0) * inside / span   # clip a session begun earlier
        online[s["pid"]] += inside
        count[s["pid"]] += 1
    leaderboard = [{**who(p), "room_h": round(room[p] / 3600, 2),
                    "online_h": round(online[p] / 3600, 2), "sessions": count[p],
                    "last_seen": last.get(p)}
                   for p in sorted(online, key=lambda p: (-room[p], -online[p]))[:10]]

    lens = [s["t1"] - s["t0"] for s in win if s.get("end") != "open"]
    session_stats = {"count": len(lens),
                     "median_min": round(_median(lens) / 60, 1) if lens else None,
                     "short": sum(1 for x in lens if x < 120),
                     "dropped": sum(1 for s in win if s.get("dropped")),
                     "reconnects": sum(s.get("reconnects", 0) for s in win)}

    # Connection health.
    joins = [j for j in by_kind["join"] if j["pid"] in named and j["t"] >= w0
             and j.get("stayed") is not None]
    links = [l for l in by_kind["link"] if (l["a"] in named or l["b"] in named)
             and l["t"] >= w0]
    health = {"joins": len(joins), "stayed": sum(1 for j in joins if j["stayed"]),
              "how": dict(Counter(j["how"] for j in joins if not j["stayed"]))}
    for kind, want in (("guest", True), ("host", False)):
        sel = [l for l in links if l.get("guest") is want]
        ok = [l["secs"] for l in sel if l["ok"]]
        health[kind] = {"n": len(sel), "ok": len(ok),
                        "median_s": round(_median(ok), 1) if ok else None}
    rel = [l for l in links if l.get("relayed")]
    health["relayed"] = {"n": len(rel), "ok": sum(1 for l in rel if l["ok"])}
    health["days"] = []
    for d in day_range:
        a, b = day_bounds(d)
        js = [j for j in joins if a <= j["t"] < b]
        g = [l for l in links if a <= l["t"] < b and l.get("guest") is True]
        health["days"].append({"day": dstr(d), "joins": len(js),
                               "stayed": sum(1 for j in js if j["stayed"]),
                               "guest": len(g), "guest_ok": sum(1 for l in g if l["ok"])})
    tries, failed = Counter(), Counter()
    for j in joins:
        tries[j["pid"]] += 1
        if not j["stayed"]:
            failed[j["pid"]] += 1
    health["trouble"] = [{**who(p), "failed": n, "joins": tries[p]}
                         for p, n in failed.most_common(5)]

    # Where players are.
    halls, hall_hours, games = defaultdict(set), Counter(), {"US/EU": set(), "JP": set()}
    rtts = defaultdict(list)
    for s in win:
        if s.get("hall"):
            halls[s["hall"]].add(s["pid"])
            hall_hours[s["hall"]] += (s["t1"] - max(s["t0"], w0)) / 3600
        if s.get("jp") is not None:
            games["JP" if s["jp"] else "US/EU"].add(s["pid"])
        if s.get("rtt"):
            rtts[s["pid"]].append(s["rtt"])
    ping = {p: _median(v) for p, v in rtts.items()}          # each player's usual round trip
    per_player_rtt = sorted(ping.values())
    # Each player counts once, at the place of their latest session in the period.
    at, place_hours = {}, Counter()
    for s in win:
        if s.get("cc"):
            if s["pid"] not in at or s["t1"] >= at[s["pid"]][0]:
                at[s["pid"]] = (s["t1"], s["cc"], s.get("region") or "")
            place_hours[s["cc"]] += (s["t1"] - max(s["t0"], w0)) / 3600
    countries = Counter(cc for _, cc, _ in at.values())
    # Room links (join -> linked up with each other player) per player and per country: a
    # link counts for both of its players, and once for a country with both of them in it.
    p_links, p_ok, p_secs = Counter(), Counter(), defaultdict(list)
    c_links, c_ok, c_secs = Counter(), Counter(), defaultdict(list)
    for l in links:
        for p in {l["a"], l["b"]}:
            p_links[p] += 1
            p_ok[p] += bool(l["ok"])
            if l["ok"] and l.get("secs") is not None:
                p_secs[p].append(l["secs"])
        for cc in {at[p][1] for p in (l["a"], l["b"]) if p in at}:
            c_links[cc] += 1
            c_ok[cc] += bool(l["ok"])
            if l["ok"] and l.get("secs") is not None:
                c_secs[cc].append(l["secs"])
    c_ping = defaultdict(list)
    for p, (_, cc, _) in at.items():
        if ping.get(p):
            c_ping[cc].append(ping[p])

    def rnd(v, n=0):
        return None if v is None else (round(v) if n == 0 else round(v, n))

    by_player = [{**who(p), "cc": at[p][1] if p in at else None,
                  "region": at[p][2] if p in at else "", "ping": rnd(ping.get(p)),
                  "link_s": rnd(_median(p_secs[p]), 1), "links": p_links[p],
                  "links_ok": p_ok[p]}
                 for p in {s["pid"] for s in win}]
    by_player.sort(key=lambda r: (r["cc"] is None, r["cc"] or "", r["ping"] is None,
                                  r["ping"] or 0, r["name"].lower()))
    regions = Counter((cc, rg) for _, cc, rg in at.values() if rg)
    buckets = [("Under 50 ms", 0, 50), ("50-100 ms", 50, 100), ("100-150 ms", 100, 150),
               ("150-250 ms", 150, 250), ("250 ms or more", 250, 10 ** 9)]
    where = {
        "halls": [{"hall": h, "players": len(v), "hours": round(hall_hours[h], 1)}
                  for h, v in sorted(halls.items(), key=lambda x: -len(x[1]))],
        "games": {k: len(v) for k, v in games.items()},
        "countries": [{"cc": cc, "players": n, "hours": round(place_hours[cc], 1),
                       "ping": rnd(_median(c_ping[cc])), "pinged": len(c_ping[cc]),
                       "link_s": rnd(_median(c_secs[cc]), 1), "links": c_links[cc],
                       "links_ok": c_ok[cc]}
                      for cc, n in sorted(countries.items(), key=lambda x: (-x[1], x[0]))],
        "by_player": by_player,
        "regions": [{"cc": cc, "region": rg, "players": n}
                    for (cc, rg), n in sorted(regions.items(),
                                              key=lambda x: (-x[1], x[0]))][:12],
        "region_count": len(regions),
        "located": len(at),
        "unlocated": len({s["pid"] for s in win} - set(at)),
        "geoip": geoip.loaded(),
        "rtt": {"players": len(per_player_rtt),
                "median": round(_median(per_player_rtt)) if per_player_rtt else None,
                "over_150": sum(1 for x in per_player_rtt if x >= 150),
                "buckets": [{"label": b[0], "players": sum(1 for x in per_player_rtt
                                                           if b[1] <= x < b[2])}
                            for b in buckets]},
    }

    # Rooms (those with at least one named player).
    rooms = [r for r in by_kind["room"] if r["t1"] >= w0
             and any(p in named for p in r.get("members", ()))]
    room_days = []
    for d in day_range:
        a, b = day_bounds(d)
        rs = [r for r in rooms if a <= r["t0"] < b]
        room_days.append({"day": dstr(d), "rooms": len(rs),
                          "three_plus": sum(1 for r in rs if r["max"] >= 3)})
    rooms_out = {"count": len(rooms),
                 "size": [{"label": "%d player%s" % (n, "" if n == 1 else "s"),
                           "rooms": sum(1 for r in rooms if min(r["max"], 4) == n)}
                          for n in (1, 2, 3, 4)],
                 "cross_version": sum(1 for r in rooms if r.get("jp_mix")),
                 "days": room_days}

    # Relay traffic and chat per local day.
    traffic, chat = Counter(), Counter()
    for t, m in hours.items():
        if t + 3600 > w0:
            traffic[lday(t)] += m["relay_out"]
            chat[lday(t)] += m["chat"]
    daily = [{"day": dstr(d), "relay_out": traffic[d], "chat": chat[d]} for d in day_range]

    # Uptime: starts, crashes, downtime before each start.
    life = sorted(by_kind["start"] + by_kind["stop"], key=lambda r: r["t"])
    starts, prev_stop = [], None
    for r in life:
        if r["k"] == "stop":
            prev_stop = r["t"]
            continue
        down_from = r.get("down_from") if r.get("crash") else prev_stop
        starts.append({"t": r["t"], "crash": bool(r.get("crash")),
                       "down_s": (r["t"] - down_from) if down_from else None})
        prev_stop = None
    in_win = [s for s in starts if s["t"] >= w0]
    uptime = {"starts": len(in_win), "crashes": sum(1 for s in in_win if s["crash"]),
              "last": in_win[-8:][::-1]}

    # HR spread of everyone active in the window (latest HR each).
    hr_buckets = [("HR 1-9", 1, 9), ("HR 10-29", 10, 29), ("HR 30-99", 30, 99),
                  ("HR 100-998", 100, 998), ("HR 999", 999, 999)]
    hrs = [latest[p][1] for p in {s["pid"] for s in win} if p in latest]
    hr = [{"label": b[0], "players": sum(1 for x in hrs if b[1] <= x <= b[2])}
          for b in hr_buckets]

    return {"enabled": True, "now": int(now), "since": int(since), "from": int(w0),
            "days": days or None, "tz_minutes": tz_minutes, "players": players,
            "peak": {"all": peak_all, "period": peak_win, "today": peak_today},
            "busiest": busiest, "leaderboard": leaderboard, "sessions": session_stats,
            "health": health, "where": where, "rooms": rooms_out, "daily": daily,
            "uptime": uptime, "hr": hr}

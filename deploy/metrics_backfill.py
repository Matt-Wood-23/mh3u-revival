"""Build metrics records (metrics.py) from the server's journal, for the time before the
server recorded them itself. Run once on the server, after the first start of a version
with metrics:

    sudo /opt/mh3u/venv/bin/python deploy/metrics_backfill.py \\
        --env /etc/mh3u.env --dir /var/lib/mh3u/metrics --owner mh3u

It replays the INFO log lines (logins, with the player's country from geoip.py; logouts,
in-game status, hall joins, rooms, probes, link results, chat, the once-a-minute STATUS
line, starts and stops) through the same code the live server uses, up to the server's first metrics start, and appends the records
marked "bf": 1. Run it again with --replace to drop those and redo them. --input FILE reads
a saved `journalctl -o short-iso` dump instead of calling journalctl.
"""
import argparse
import ast
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Same imports as server.py: the cloned NintendoClients next to the repo, then the repo.
sys.path.insert(0, str(HERE.parent.parent / "external" / "NintendoClients"))
sys.path.insert(0, str(HERE.parent))

import geoip  # noqa: E402


def load_hall_env(path):
    """Only the hall settings: they decide each hall's label (Americas, Europe, ...)."""
    if not path:
        return
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        k, sep, v = line.strip().partition("=")
        if sep and k.startswith("MH3U_HALL"):
            os.environ[k] = v


def first_live_start(folder):
    import metrics
    ts = [r["t"] for r in metrics.load_records(folder) if r["k"] == "start" and not r.get("bf")]
    return min(ts) if ts else None


def drop_backfill(folder):
    n = 0
    for p in Path(folder).glob("events-*.jsonl"):
        keep = []
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                if json.loads(line).get("bf"):
                    n += 1
                    continue
            except ValueError:
                pass
            keep.append(line)
        p.write_text("".join(l + "\n" for l in keep), encoding="utf-8", newline="\n")
    return n


UNITS = {"B": 1, "KB": 10 ** 3, "MB": 10 ** 6, "GB": 10 ** 9, "TB": 10 ** 12}
RX = {k: re.compile(v) for k, v in {
    "start": r"mh3u\.server: MH3U NEX server",
    "stop": r"mh3u\.server: shutting down( for a planned restart)?|systemd\[1\]: Stopping ",
    "status": r"STATUS players=\d+ .*?(?:relay_out_today=([\d.]+)([KMGT]?B))?$",
    "register": r"mh3u\.proto: REGISTER pid=(\d+) (?:.*?-> public=\S*?address=([^;\s]+))?",
    "logout": r"mh3u\.proto: LOGOUT pid=(\d+) cid=\S+ -> cleaned up; rooms affected=(\[.*?\]);",
    "presence": r"update_notification_data: type=101 p1=\S+ p2=\S+ p3=('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\") \(pid=(\d+)\)",
    "hall": r"join_community: pid=(\d+) -> hall 0x([0-9a-f]+)",
    "reaped": r"create_matchmake_session: reaped stale room\(s\) (\[.*?\])",
    "create": r"create_matchmake_session: gid=0x([0-9a-f]+) host=(\d+)",
    "join": r"(?:join|join_matchmake_session_ex): pid=(\d+) -> gid=0x([0-9a-f]+)",
    "end_room": r"end_participation: ROOM gid=0x([0-9a-f]+) \(pid=(\d+)\) -> (left|destroyed)",
    "unregister": r"unregister_gathering: gid=0x([0-9a-f]+) \(pid=\d+\) -> destroyed",
    "unregister_many": r"unregister_gatherings: .* -> destroyed (\[.*?\])",
    "rtt": r"report_nat_properties: .*rtt=(\d+) \(pid=(\d+)\)",
    "probe_req": r"request_probe_initiation_ext: .*\(pid=(\d+)\)$",
    "probe_fwd": r"-> forwarded InitiateProbe\(.*\) to host pid=(\d+) RVCID=\S+ (via relay|direct)",
    "result": r"report_nat_traversal_result(?:_detail)?: cid=\S+ result=(True|False).*\(pid=(\d+) other_pid=(\d+)\)",
    "shout": r"mh3u\.proto: SHOUT pid=(\d+) ",
}.items()}


def replay(lines, rec, until, hall_label):
    """Feed journal lines (short-iso) to a Recorder. Returns (lines used, last time)."""
    running, last_t, caller, used = False, None, None, 0
    for line in lines:
        if len(line) < 26 or not line[:4].isdigit():
            continue
        try:
            t = datetime.fromisoformat(line[:25]).timestamp()
        except ValueError:
            continue
        if until is not None and t >= until:
            break
        msg = line[26:]
        m = RX["start"].search(msg)
        if m:
            if running:                       # the last process never shut down: a crash
                rec.joins.clear()
                rec.links.clear()
                for gid in list(rec.rooms):
                    rec.room_closed(gid, last_t)
                for pid in list(rec.sessions):
                    rec._end(pid, last_t, "crash")
                rec._flush_hour()
            rec._write({"k": "start", "t": int(t), "crash": running,
                        "down_from": int(last_t) if running and last_t else None})
            running, last_t, used = True, t, used + 1
            continue
        if not running:
            continue
        last_t = t
        m = RX["stop"].search(msg)
        if m:
            rec.stop(t, restart=bool(m.group(1)))
            running = False
            used += 1
            continue
        for kind in ("register", "logout", "presence", "hall", "reaped", "create", "join",
                     "end_room", "unregister", "unregister_many", "rtt", "probe_req",
                     "probe_fwd", "result", "shout", "status"):
            m = RX[kind].search(msg)
            if not m:
                continue
            used += 1
            g = m.groups()
            if kind == "register":
                rec.login(int(g[0]), t, place=geoip.place(g[1]))
            elif kind == "logout":
                pid = int(g[0])
                for action, gid, _left in ast.literal_eval(g[1]):
                    if action == "left":
                        rec.room_left(int(gid, 16), pid, "logout", t)
                    else:
                        rec.room_closed(int(gid, 16), t)
                rec.logout(pid, t)
            elif kind == "presence":
                rec.presence(int(g[1]), ast.literal_eval(g[0]), t)
            elif kind == "hall":
                found = hall_label(int(g[1], 16))
                if found:
                    rec.hall(int(g[0]), found[0], found[1], t)
            elif kind in ("reaped", "unregister_many"):
                for gid in ast.literal_eval(g[0]):
                    rec.room_closed(int(gid, 16), t)
            elif kind == "create":
                rec.room_created(int(g[0], 16), int(g[1]), t)
            elif kind == "join":
                rec.room_joined(int(g[1], 16), int(g[0]), t)
            elif kind == "end_room":
                if g[2] == "left":
                    rec.room_left(int(g[0], 16), int(g[1]), "left", t)
                else:
                    rec.room_closed(int(g[0], 16), t)
            elif kind == "unregister":
                rec.room_closed(int(g[0], 16), t)
            elif kind == "rtt":
                rec.rtt(int(g[1]), int(g[0]), t)
            elif kind == "probe_req":
                caller = int(g[0])
            elif kind == "probe_fwd":
                if caller is not None:
                    rec.probe(caller, int(g[0]), g[1] == "via relay", t)
            elif kind == "result":
                rec.link_result(int(g[1]), int(g[2]), g[0] == "True", t)
            elif kind == "shout":
                rec.chat(int(g[0]), t)
            elif kind == "status":
                out = round(float(g[0]) * UNITS[g[1]]) if g[0] else None
                rec.sample(t, out)
            break
    if running and last_t is not None:        # log ends mid-run (no --until): close it
        rec.stop(last_t)
    return used, last_t


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dir", required=True, help="the metrics folder (<state dir>/metrics)")
    ap.add_argument("--env", help="the server's env file (only MH3U_HALL* is read)")
    ap.add_argument("--input", help="a saved journalctl -o short-iso dump")
    ap.add_argument("--unit", default="mh3u")
    ap.add_argument("--until", type=float,
                    help="stop at this Unix time (default: the first live metrics start)")
    ap.add_argument("--replace", action="store_true", help="drop earlier backfill records first")
    ap.add_argument("--owner", help="give the folder's files to this user (the server's)")
    ap.add_argument("--geoip", help="player-location database (default: the server's, "
                    "see geoip.py); without one, sessions get no country")
    a = ap.parse_args()
    load_hall_env(a.env)
    if not geoip.load(a.geoip):
        print("no geoip database: sessions get no country (deploy/geoip_update.py)")

    import matchmaking_handlers as mh
    import metrics

    folder = Path(a.dir)
    if any(r.get("bf") for r in metrics.load_records(folder)):
        if not a.replace:
            sys.exit("Backfill records are already there; use --replace to redo them.")
        print("dropped %d earlier backfill record(s)" % drop_backfill(folder))
    until = a.until if a.until is not None else first_live_start(folder)
    if until is None:
        sys.exit("No live metrics start found in %s; pass --until <unix time>." % folder)

    def hall_label(gid):
        c = mh.COMMUNITY.communities.get(gid)
        if gid not in mh.COMMUNITY.lobbies or c is None:
            return None
        return getattr(c, "label", ""), gid in mh.COMMUNITY.jp_gids

    if a.input:
        lines = Path(a.input).read_text(encoding="utf-8", errors="replace").splitlines()
    else:
        lines = subprocess.run(
            ["journalctl", "-u", a.unit, "--no-pager", "-o", "short-iso",
             "--until", "@%d" % int(until)],
            capture_output=True, text=True, errors="replace", check=True).stdout.splitlines()
    rec = metrics.Recorder(folder, live=False, backfill=True)
    used, last_t = replay(lines, rec, until, hall_label)
    n = sum(1 for r in metrics.load_records(folder) if r.get("bf"))
    print("replayed %d log line(s) up to %s: %d record(s) written to %s"
          % (used, datetime.fromtimestamp(until).isoformat(timespec="seconds"), n, folder))
    if a.owner:
        import pwd
        u = pwd.getpwnam(a.owner)
        for p in [folder, *folder.iterdir()]:
            os.chown(p, u.pw_uid, u.pw_gid)


if __name__ == "__main__":
    main()

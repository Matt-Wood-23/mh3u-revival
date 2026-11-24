"""Play metrics (metrics.py): what gets recorded, and the admin report built from it.

Run:  pytest tests/test_metrics.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "..", "external", "NintendoClients"))
sys.path.insert(0, _ROOT)

import asyncio
import json
import types

import pytest

import admin_http
import matchmaking_handlers as mh
import metrics

T0 = 1_795_000_000 - 1_795_000_000 % 86400 + 12 * 3600   # a UTC noon


def status(name, hr=5):
    """A presence string as the game sends it (update_notification_data type 101)."""
    return "\t".join(["3", "0x1", "0x2", "0x1001", "0x1", "room", "1", "4", name, str(hr),
                      "16", "1", "0", "0", "0", ""])


def records(folder, kind=None):
    out = metrics.load_records(folder)
    return [r for r in out if kind is None or r["k"] == kind]


@pytest.fixture
def rec(tmp_path):
    r = metrics.Recorder(tmp_path)
    r.start(T0)
    return r


def online(r, pid, name, t, hall="Americas", jp=False):
    r.login(pid, t)
    r.hall(pid, hall, jp, t)
    r.presence(pid, status(name), t)


def test_session_is_recorded_with_name_hall_and_room_time(rec, tmp_path):
    online(rec, 1, "Mira", T0)
    rec.rtt(1, 140, T0)
    rec.room_created(0x1001, 1, T0 + 60)
    rec.room_closed(0x1001, T0 + 660)
    rec.logout(1, T0 + 900)
    (s,) = records(tmp_path, "session")
    assert (s["name"], s["hall"], s["jp"], s["rtt"]) == ("Mira", "Americas", False, 140)
    assert (s["t1"] - s["t0"], s["room_s"], s["hosted"], s["end"]) == (900, 600, 1, "logout")
    (room,) = records(tmp_path, "room")
    assert room["members"] == [1] and room["max"] == 1


def test_placeholder_names_and_hr_zero_are_ignored(rec, tmp_path):
    rec.login(1, T0)
    rec.presence(1, status("No Name", 0), T0)
    rec.presence(1, status("Mira", 0), T0 + 1)
    rec.logout(1, T0 + 5)
    (s,) = records(tmp_path, "session")
    assert s["name"] == "Mira" and s["hr"] is None


def test_join_that_stays_and_its_link(rec, tmp_path):
    online(rec, 1, "Host", T0)
    online(rec, 2, "Guest", T0)
    rec.room_created(0x1001, 1, T0)
    rec.room_joined(0x1001, 2, T0 + 10)
    rec.probe(2, 1, True, T0 + 11)
    rec.probe(1, 2, False, T0 + 11)              # the same pair again: still one link
    rec.link_result(1, 2, True, T0 + 13)
    rec.link_result(2, 1, True, T0 + 13)         # the other end's report: ignored
    rec.sample(T0 + 75)                          # 65 s after the join
    (j,) = records(tmp_path, "join")
    assert (j["stayed"], j["others"], j["how"]) == (True, 1, None)
    (l,) = records(tmp_path, "link")
    assert (l["ok"], l["guest"], l["relayed"], l["secs"]) == (True, False, True, 2.0)


def test_joiner_who_drops_fails_the_join_and_the_link(rec, tmp_path):
    for pid, name in ((1, "Host"), (2, "G1"), (3, "G2")):
        online(rec, pid, name, T0)
    rec.room_created(0x1001, 1, T0)
    rec.room_joined(0x1001, 2, T0)
    rec.sample(T0 + 61)
    rec.room_joined(0x1001, 3, T0 + 100)
    rec.probe(3, 1, True, T0 + 101)
    rec.probe(3, 2, True, T0 + 101)
    rec.link_result(3, 1, True, T0 + 103)
    rec.room_left(0x1001, 3, "logout", T0 + 108)    # the guest pair never came up
    rec.logout(3, T0 + 108)
    joins = {j["pid"]: j for j in records(tmp_path, "join")}
    assert joins[2]["stayed"] is True
    assert (joins[3]["stayed"], joins[3]["how"], joins[3]["secs"]) == (False, "logout", 8.0)
    links = {(l["a"], l["b"]): l for l in records(tmp_path, "link")}
    assert links[(1, 3)]["ok"] is True and links[(1, 3)]["guest"] is False
    assert links[(2, 3)]["ok"] is False and links[(2, 3)]["guest"] is True
    s3 = [s for s in records(tmp_path, "session") if s["pid"] == 3][0]
    assert s3["dropped"] is True


def test_link_without_a_result_fails_after_the_window(rec, tmp_path):
    online(rec, 1, "Host", T0)
    online(rec, 2, "Guest", T0)
    rec.room_created(0x1001, 1, T0)
    rec.room_joined(0x1001, 2, T0)
    rec.probe(2, 1, False, T0 + 1)
    rec.sample(T0 + 20)
    assert not records(tmp_path, "link")
    rec.sample(T0 + 40)
    (l,) = records(tmp_path, "link")
    assert l["ok"] is False


def test_room_closed_by_the_host_is_not_a_failed_join(rec, tmp_path):
    online(rec, 1, "Host", T0)
    online(rec, 2, "Guest", T0)
    rec.room_created(0x1001, 1, T0)
    rec.room_joined(0x1001, 2, T0)
    rec.probe(2, 1, False, T0 + 1)
    rec.room_closed(0x1001, T0 + 5)
    (j,) = records(tmp_path, "join")
    assert j["stayed"] is None and j["how"] == "closed"
    assert not records(tmp_path, "link")


def test_reconnect_keeps_one_session(rec, tmp_path):
    online(rec, 1, "Mira", T0)
    rec.login(1, T0 + 50)                         # new connection before the old closed
    rec.logout(1, T0 + 100)
    (s,) = records(tmp_path, "session")
    assert (s["t1"] - s["t0"], s["reconnects"]) == (100, 1)


def test_hours_flush_and_count_only_named_players(rec, tmp_path):
    online(rec, 1, "Mira", T0)
    rec.login(2, T0)                              # never sends a name (a load-test client)
    rec.sample(T0 + 60)
    rec.sample(T0 + 120)
    rec.chat(1, T0 + 130)
    rec.sample(T0 + 3600)                         # next hour: the first one is written
    (h,) = records(tmp_path, "hour")
    assert (h["t"], h["n"], h["avg"], h["max"], h["chat"]) == (T0, 2, 1.0, 1, 1)


def test_relay_bytes_per_hour_follow_the_daily_counter(rec, tmp_path):
    rec.sample(T0, relay_out_today=1000)          # baseline only
    rec.sample(T0 + 60, relay_out_today=1500)
    rec.sample(T0 + 3600, relay_out_today=4000)
    rec.stop(T0 + 3700)
    hours = {h["t"]: h for h in records(tmp_path, "hour")}
    assert hours[T0]["relay_out"] == 500 and hours[T0 + 3600]["relay_out"] == 2500


def test_crash_closes_open_sessions_at_the_last_save(tmp_path):
    a = metrics.Recorder(tmp_path)
    a.start(T0)
    online(a, 1, "Mira", T0)
    a.room_created(0x1001, 1, T0)
    a.sample(T0 + 600)                            # saves open.json; then the process dies
    b = metrics.Recorder(tmp_path)
    b.start(T0 + 900)
    (s,) = records(tmp_path, "session")
    assert (s["end"], s["t1"], s["room_s"]) == ("crash", T0 + 600, 600)
    starts = records(tmp_path, "start")
    assert starts[-1]["crash"] is True and starts[-1]["down_from"] == T0 + 600


def test_clean_stop_is_not_a_crash(tmp_path):
    a = metrics.Recorder(tmp_path)
    a.start(T0)
    online(a, 1, "Mira", T0)
    a.stop(T0 + 100, restart=True)
    metrics.Recorder(tmp_path).start(T0 + 110)
    (s,) = records(tmp_path, "session")
    assert s["end"] == "shutdown"
    assert records(tmp_path, "start")[-1]["crash"] is False


def test_report_counts_players_leaderboard_and_health(rec, tmp_path):
    day = 86400
    # Mira: 3 h online, 2 h in rooms; Sam: 1 h, all in rooms; Bot: no name.
    online(rec, 1, "Mira", T0 - 2 * day)
    rec.room_created(0x1001, 1, T0 - 2 * day + 3600)
    rec.room_closed(0x1001, T0 - 2 * day + 3 * 3600)
    rec.logout(1, T0 - 2 * day + 3 * 3600)
    online(rec, 2, "Sam", T0)
    rec.room_created(0x1002, 2, T0)
    online(rec, 1, "Mira", T0 + 60)
    rec.room_joined(0x1002, 1, T0 + 60)
    rec.sample(T0 + 200)                          # Mira stayed
    rec.room_closed(0x1002, T0 + 3600)
    rec.logout(2, T0 + 3600)
    rec.logout(1, T0 + 3600)
    rec.login(9, T0)
    rec.logout(9, T0 + 10)
    out = metrics.build_report(metrics.load_records(tmp_path), T0 + 3700, days=0)
    assert out["players"]["all"] == 2 and out["players"]["today"] == 2
    top = out["leaderboard"]
    assert [r["name"] for r in top] == ["Mira", "Sam"]
    assert top[0]["room_h"] == pytest.approx(2.0 + 3540 / 3600, abs=0.05)
    assert out["health"]["joins"] == 1 and out["health"]["stayed"] == 1
    assert out["rooms"]["count"] == 2 and out["rooms"]["size"][1]["rooms"] == 1
    week = metrics.build_report(metrics.load_records(tmp_path) + rec.open_hour(),
                                T0 + 3700, days=7)     # the unfinished hour counts too
    assert week["players"]["period"] == 2 and week["peak"]["all"]["players"] >= 1
    assert out["where"]["halls"][0]["hall"] == "Americas"


def test_report_busiest_hours_use_the_viewers_clock(rec, tmp_path):
    online(rec, 1, "Mira", T0)
    rec.sample(T0 + 60)
    rec.sample(T0 + 3600)                         # writes the 12:00 UTC hour
    utc = metrics.build_report(metrics.load_records(tmp_path), T0 + 3700, 0)
    cst = metrics.build_report(metrics.load_records(tmp_path), T0 + 3700, 360)
    assert utc["busiest"]["by_hour"][12] == 1.0
    assert cst["busiest"]["by_hour"][6] == 1.0 and cst["busiest"]["by_hour"][12] is None


def test_a_restart_inside_an_hour_merges_into_one_hour(tmp_path):
    a = metrics.Recorder(tmp_path)
    a.start(T0)
    online(a, 1, "Mira", T0)
    a.sample(T0 + 60)
    a.stop(T0 + 100)
    b = metrics.Recorder(tmp_path)
    b.start(T0 + 200)
    b.sample(T0 + 260)
    b.sample(T0 + 3600)
    assert len([h for h in records(tmp_path, "hour") if h["t"] == T0]) == 2
    out = metrics.build_report(metrics.load_records(tmp_path), T0 + 3700)
    assert out["busiest"]["by_hour"][12] == 0.5   # 1 then 0 players, one sample each
    assert out["uptime"]["starts"] == 2 and out["uptime"]["last"][0]["down_s"] == 100


def test_hooks_do_nothing_while_off_and_never_raise(tmp_path, monkeypatch):
    monkeypatch.setattr(metrics, "_rec", None)
    metrics.login(1)
    metrics.room_left(0x1001, 1, "left")
    assert metrics.report() == {"enabled": False}
    broken = metrics.Recorder(tmp_path)
    broken.sessions = None                        # every hook now hits a TypeError
    monkeypatch.setattr(metrics, "_rec", broken)
    metrics.login(1)
    metrics.presence(1, status("Mira"))
    metrics.sample()


def test_registry_and_admin_endpoint_record_a_room(tmp_path, monkeypatch):
    monkeypatch.setattr(metrics, "_rec", None)
    monkeypatch.setattr(metrics, "SWITCH", "1")
    assert metrics.start(False, folder=tmp_path, now=T0)
    try:
        metrics.login(1, now=T0)
        metrics.presence(1, status("Mira"), now=T0)
        metrics.login(2, now=T0)
        metrics.presence(2, status("Sam"), now=T0)
        reg = mh.GatheringRegistry()
        g = types.SimpleNamespace(attribs=[], game_mode=1, max_participants=4)
        sess = reg.create(g, 1)
        reg.join(sess.gid, 2)
        reg.leave_gathering(sess.gid, 2)
        reg.destroy(sess.gid)
        (j,) = records(tmp_path, "join")
        assert (j["stayed"], j["how"]) == (False, "left")
        (room,) = records(tmp_path, "room")
        assert room["members"] == [1, 2] and room["max"] == 2
        body = asyncio.run(admin_http.handle("GET", "/metrics?tz=360&days=7", b""))
        data = json.loads(body.split(b"\r\n\r\n", 1)[1])
        assert data["enabled"] is True and data["tz_minutes"] == 360 and data["days"] == 7
        assert data["players"]["all"] == 2
    finally:
        metrics.stop(now=T0 + 100)
    assert metrics._rec is None


def _ip4(s):
    a, b, c, d = map(int, s.split("."))
    return a << 24 | b << 16 | c << 8 | d


@pytest.fixture
def geo(tmp_path, monkeypatch):
    """A tiny location database: 8.x.x.x = California, 81.x.x.x = England."""
    import geoip
    path = tmp_path / "geoip.bin"
    path.write_bytes(geoip.pack(
        [0, _ip4("8.0.0.0"), _ip4("9.0.0.0"), _ip4("81.0.0.0"), _ip4("82.0.0.0")],
        [0, 1, 0, 2, 0], [["", ""], ["US", "California"], ["GB", "England"]], "test"))
    monkeypatch.setattr(geoip, "PATH", path)
    monkeypatch.setattr(geoip, "_table", None)
    monkeypatch.setattr(geoip, "_stamp", None)
    assert geoip.load()
    return geoip


def test_geoip_places_public_addresses_only(geo, tmp_path):
    assert geo.place("8.8.8.8") == ("US", "California")
    assert geo.place("::ffff:81.2.3.4") == ("GB", "England")
    for ip in ("9.1.1.1", "192.168.1.5", "100.100.1.1", "127.0.0.1", "2001:db8::1",
               "nonsense", "", None):
        assert geo.place(ip) is None, ip
    # A new file is picked up on the next load (the monthly update, no restart).
    geo.PATH.write_bytes(geo.pack([0, _ip4("8.0.0.0"), _ip4("9.0.0.0")], [0, 1, 0],
                                  [["", ""], ["CA", "Ontario"]], "test2"))
    os.utime(geo.PATH, (1, 1))
    assert geo.load() and geo.place("8.8.8.8") == ("CA", "Ontario")
    geo.PATH.write_bytes(b"junk")
    os.utime(geo.PATH, (2, 2))
    assert not geo.load() and geo.place("8.8.8.8") is None


def test_geoip_update_converts_db_ip_rows():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "geoip_update", os.path.join(_ROOT, "deploy", "geoip_update.py"))
    gu = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gu)
    rows = [["0.0.0.0", "0.255.255.255", "ZZ", "ZZ", "", "", "0", "0"],
            ["8.0.0.0", "8.0.0.255", "NA", "US", "California", "A", "0", "0"],
            ["8.0.1.0", "8.0.1.255", "NA", "US", "California", "B", "0", "0"],   # merged
            ["8.0.3.0", "8.0.3.255", "EU", "GB", "England", "C", "0", "0"],      # after a gap
            ["2001::", "2001::ffff", "EU", "GB", "England", "C", "0", "0"]]      # IPv6: skipped
    starts, idx, labels = gu.convert(rows)
    assert labels == [["", ""], ["US", "California"], ["GB", "England"]]
    assert starts == [0, _ip4("8.0.0.0"), _ip4("8.0.2.0"), _ip4("8.0.3.0"), _ip4("8.0.4.0")]
    assert idx == [0, 1, 0, 2, 0]
    country = gu.convert([["1.0.0.0", "1.0.0.255", "AU"]])
    assert country[2] == [["", ""], ["AU", ""]]
    import geoip
    assert geoip.parse(geoip.pack(starts, idx, labels, "x"))[2] == [tuple(l) for l in labels]


def test_sessions_keep_the_place_and_the_report_counts_it(geo, tmp_path, monkeypatch):
    monkeypatch.setattr(metrics, "SWITCH", "1")
    assert metrics.start(False, folder=tmp_path, now=T0)
    try:
        for pid, name, ip in ((1, "Mira", "8.8.8.8"), (2, "Sam", "81.2.3.4"),
                              (3, "Ren\xe9e", "8.1.2.3"), (4, "O'Neil", "10.0.0.9")):
            metrics.login(pid, ip, now=T0)
            metrics.presence(pid, status(name), now=T0)
        for pid in (1, 2, 3, 4):
            metrics.logout(pid, now=T0 + 3600)
    finally:
        metrics.stop(now=T0 + 3700)
    s = {r["pid"]: r for r in records(tmp_path, "session")}
    assert (s[1]["cc"], s[1]["region"], s[2]["cc"]) == ("US", "California", "GB")
    assert "cc" not in s[4] and not any("ip" in r or "8.8.8.8" in json.dumps(r)
                                        for r in records(tmp_path))
    w = metrics.build_report(records(tmp_path), T0 + 4000, days=0)["where"]
    assert w["countries"] == [{"cc": "US", "players": 2, "hours": 2.0},
                              {"cc": "GB", "players": 1, "hours": 1.0}]
    assert w["regions"][0] == {"cc": "US", "region": "California", "players": 2}
    assert (w["located"], w["unlocated"], w["region_count"]) == (3, 1, 2)


def _backfill_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "metrics_backfill", os.path.join(_ROOT, "deploy", "metrics_backfill.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LOG = r"""2026-11-22T20:00:00+00:00 vm python[1]: 20:00:00 INFO    mh3u.server: MH3U NEX server  |  game_server_id=0x10104D00
2026-11-22T20:00:05+00:00 vm python[1]: 20:00:05 INFO    mh3u.proto: REGISTER pid=11 cid=4097 urls=['prudp:/address=10.0.0.2;port=1'] -> public=prudp:/address=8.8.4.4;port=50000;PID=11
2026-11-22T20:00:06+00:00 vm python[1]: 20:00:06 INFO    mh3u.matchmaking: join_community: pid=11 -> hall 0x101 (now 1)
2026-11-22T20:00:07+00:00 vm python[1]: 20:00:07 INFO    mh3u.matchmaking: update_notification_data: type=101 p1=11 p2=1 p3='1\t0x1\t0x0\t0x0\t0x1\tNot Login\t0\t0\tRen\xe9e\t7\t16\t0\t0\t0\t0\t' (pid=11) -> ok
2026-11-22T20:00:08+00:00 vm python[1]: 20:00:08 INFO    mh3u.proto: REGISTER pid=22 cid=4098 urls=[] -> public=x
2026-11-22T20:00:09+00:00 vm python[1]: 20:00:09 INFO    mh3u.matchmaking: update_notification_data: type=101 p1=22 p2=1 p3="1\t0x1\t0x0\t0x0\t0x1\tNot Login\t0\t0\tO'Neil\t40\t16\t0\t0\t0\t0\t" (pid=22) -> ok
2026-11-22T20:00:10+00:00 vm python[1]: 20:00:10 INFO    mh3u.proto: report_nat_properties: natm=1 natf=2 rtt=231 (pid=22)
2026-11-22T20:01:00+00:00 vm python[1]: 20:01:00 INFO    mh3u.matchmaking: create_matchmake_session: gid=0x1001 host=11 msg='x' game_mode=1001 attribs=[1] applen=309
2026-11-22T20:01:05+00:00 vm python[1]: 20:01:05 INFO    mh3u.matchmaking: join_matchmake_session_ex: pid=22 -> gid=0x1001 msg='x' ignore_block=False (now 2 participants)
2026-11-22T20:01:06+00:00 vm python[1]: 20:01:06 INFO    mh3u.proto: request_probe_initiation_ext: targets=['prudp:/RVCID=4097'] probe=prudp:/RVCID=4098 (pid=22)
2026-11-22T20:01:06+00:00 vm python[1]: 20:01:06 INFO    mh3u.proto:   -> forwarded InitiateProbe(joiner=prudp:/x) to host pid=11 RVCID=4097 via relay gid=0x1001
2026-11-22T20:01:08+00:00 vm python[1]: 20:01:08 INFO    mh3u.proto: report_nat_traversal_result: cid=4097 result=True (pid=22 other_pid=11)
2026-11-22T20:01:09+00:00 vm python[1]: 20:01:09 INFO    mh3u.proto: SHOUT pid=22 raw=120B text='hi'
2026-11-22T20:02:00+00:00 vm python[1]: 20:02:00 INFO    mh3u.server: STATUS players=2 rooms=1 halls=12 uptime=2m00s relay_out_today=1.5MB
2026-11-22T20:03:00+00:00 vm python[1]: 20:03:00 INFO    mh3u.server: STATUS players=2 rooms=1 halls=12 uptime=3m00s relay_out_today=2.0MB
2026-11-22T20:30:00+00:00 vm python[1]: 20:30:00 INFO    mh3u.proto: LOGOUT pid=22 cid=4098 -> cleaned up; rooms affected=[('left', '0x1001', 1)]; halls left=[]
2026-11-22T20:40:00+00:00 vm python[1]: 20:40:00 INFO    mh3u.server: shutting down for a planned restart
"""


def test_backfill_finds_the_geoip_file_next_to_the_metrics_folder(tmp_path, monkeypatch):
    bf = _backfill_module()
    monkeypatch.setattr(bf.geoip, "PATH", tmp_path / "nowhere" / "geoip.bin")
    want = (tmp_path / "state" / "geoip" / "geoip.bin").resolve()
    assert bf.geoip_path(None, tmp_path / "state" / "metrics") == want
    assert str(bf.geoip_path("given.bin", tmp_path / "state" / "metrics")) == "given.bin"


def test_backfill_replays_the_journal_through_the_same_code(tmp_path, geo):
    bf = _backfill_module()
    rec = metrics.Recorder(tmp_path, live=False, backfill=True)
    labels = {0x101: ("Americas", False)}
    bf.replay(LOG.splitlines(), rec, None, labels.get)
    got = records(tmp_path)
    assert all(r.get("bf") == 1 for r in got)
    s = {r["pid"]: r for r in got if r["k"] == "session"}
    assert (s[11]["name"], s[11]["hall"], s[11]["hr"]) == ("Ren\xe9e", "Americas", 7)
    assert (s[22]["name"], s[22]["rtt"], s[22]["end"]) == ("O'Neil", 231, "logout")
    assert (s[11]["cc"], s[11]["region"]) == ("US", "California")   # the observed address
    assert "cc" not in s[22]                                         # no address logged
    assert s[11]["end"] == "shutdown" and s[22]["room_s"] == 30 * 60 - 5 - 60
    (j,) = [r for r in got if r["k"] == "join"]
    assert j["stayed"] is True
    (l,) = [r for r in got if r["k"] == "link"]
    assert (l["ok"], l["relayed"], l["guest"]) == (True, True, False)
    (h,) = [r for r in got if r["k"] == "hour"]
    assert (h["relay_out"], h["chat"], h["max"]) == (500_000, 1, 2)
    stop = [r for r in got if r["k"] == "stop"][0]
    assert stop["restart"] is True

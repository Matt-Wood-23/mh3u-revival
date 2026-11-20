"""Outside uptime check for the official server(s), run by .github/workflows/uptime.yml.

The server alerts Discord when it starts, stops or crashes, but it can't report its own
machine going away (VM reclaimed, network down, host frozen). This runs somewhere else
(GitHub Actions, every 5 minutes) and checks each server in servers.json:

    status page   GET http://<host>:<status_port>/status answers {"online": true}
    game UDP      the NAT-check responder on UDP 10025 answers (the game's first contact)

A server is "suspect" after one failed run and "down" after two in a row, so a single
network blip doesn't page anyone. Discord hears about down and back-up only (webhook in
the DISCORD_WEBHOOK environment variable; without one, results are only printed).

    python deploy/uptime_check.py servers.json --state .uptime-state

The state file is JSON: {server id: {"state": "up|suspect|down", "since": unix time}}.
"changed=true" goes to $GITHUB_OUTPUT when it changed, so the workflow saves it.
"""
import argparse
import json
import os
import socket
import struct
import sys
import time
import urllib.request

NATCHECK_PORT = 10025
TRIES = 3
RETRY_PAUSE = 15
USER_AGENT = "MH3U-Revival-Uptime (https://github.com/Matt-Wood-23/mh3u-revival)"


def check_status(host, port, timeout=10):
    try:
        req = urllib.request.Request(f"http://{host}:{port}/status",
                                     headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read(64 * 1024))
        return (True, "ok") if data.get("online") is True else (False, "not online")
    except Exception as e:
        return False, type(e).__name__


def check_natcheck(host, timeout=3.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        for _ in range(3):
            try:
                s.sendto(struct.pack(">IIII", 0x65, 0, 0, 0), (host, NATCHECK_PORT))
                data, _ = s.recvfrom(64)
                if len(data) >= 16:
                    return True, "ok"
            except socket.timeout:
                continue
            except OSError as e:
                return False, type(e).__name__
        return False, "no answer"
    finally:
        s.close()


def check(server, tries=TRIES, pause=RETRY_PAUSE):
    """(healthy, details) after up to `tries` attempts."""
    detail = {}
    for attempt in range(tries):
        if attempt:
            time.sleep(pause)
        ok_s, detail["status page"] = check_status(server["host"], server["status_port"])
        ok_n, detail["game UDP"] = check_natcheck(server["host"])
        if ok_s and ok_n:
            return True, detail
    return False, detail


def step(prev, healthy, now):
    """Next state for one server -> (state dict, event). event: "down", "up" or None."""
    state = (prev or {}).get("state", "up")
    since = (prev or {}).get("since", now)
    if healthy:
        if state == "down":
            return {"state": "up", "since": now, "was_down": now - since}, "up"
        return ({"state": "up", "since": since if state == "up" else now}, None)
    if state == "up":
        return {"state": "suspect", "since": now}, None
    if state == "suspect":
        return {"state": "down", "since": since}, "down"
    return {"state": "down", "since": since}, None


def _minutes(secs):
    m = max(1, round(secs / 60))
    return f"{m} min" if m < 120 else f"{m / 60:.1f} h"


def message(server, event, detail, new):
    name = server.get("name") or server["id"]
    if event == "down":
        why = ", ".join(f"{k}: {v}" for k, v in detail.items())
        return (f"🔴 **{name}** isn't answering (checked from outside, twice in a row). "
                f"{why}. Down since <t:{int(new['since'])}:t>.")
    return f"🟢 **{name}** is answering again (was down about {_minutes(new['was_down'])})."


def post(webhook, text):
    req = urllib.request.Request(
        webhook, data=json.dumps({"content": text, "allowed_mentions": {"parse": []}}).encode(),
        method="POST", headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=10):
        pass


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("servers")
    ap.add_argument("--state", default=".uptime-state")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):          # emoji in the log on any console
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    servers = [s for s in json.load(open(args.servers, encoding="utf-8")).get("servers", [])
               if s.get("id") and s.get("host") and s.get("status_port")]
    try:
        old = json.load(open(args.state, encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    webhook = os.environ.get("DISCORD_WEBHOOK", "").strip()
    now = time.time()
    new = {}
    for srv in servers:
        healthy, detail = check(srv)
        new[srv["id"]], event = step(old.get(srv["id"]), healthy, now)
        print(f"{srv['id']}: {'UP' if healthy else 'FAILING'} {detail} -> {new[srv['id']]['state']}")
        if event:
            text = message(srv, event, detail, new[srv["id"]])
            print("  alert:", text)
            if webhook:
                try:
                    post(webhook, text)
                except Exception as e:
                    print(f"  Discord post failed: {type(e).__name__}", file=sys.stderr)
    for v in new.values():
        v.pop("was_down", None)
    changed = {k: v["state"] for k, v in new.items()} != {k: v.get("state") for k, v in old.items()}
    with open(args.state, "w", encoding="utf-8") as f:
        json.dump(new, f)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"changed={'true' if changed else 'false'}\n")
    print("state changed" if changed else "state unchanged")


if __name__ == "__main__":
    main()

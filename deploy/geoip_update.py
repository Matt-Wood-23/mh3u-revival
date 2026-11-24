"""Build the player-location database (geoip.py) from DB-IP's free IP to City Lite file
(CC BY 4.0, "IP Geolocation by DB-IP", https://db-ip.com). Run on the server:

    sudo /opt/mh3u/venv/bin/python deploy/geoip_update.py --dir /var/lib/mh3u/geoip --owner mh3u

It downloads this month's file (last month's if this month's isn't out yet; about 85 MB,
read as it arrives, nothing saved but the result), keeps only IPv4 country and state /
province, and writes geoip.bin (a few MB). A running server picks it up within a minute.
DB-IP updates the file once a month; run this again (e.g. monthly from cron) to refresh.

--country uses DB-IP's smaller country-only file (no states / provinces). --input FILE
converts a .csv or .csv.gz you downloaded yourself instead.
"""
import argparse
import csv
import gzip
import io
import os
import shutil
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import geoip  # noqa: E402

URL = "https://download.db-ip.com/free/dbip-{kind}-lite-{month}.csv.gz"
REGION_MAX = 60


def _ip4(s):
    return int.from_bytes(socket.inet_aton(s), "big")


def convert(rows):
    """CSV rows (start, end, [continent,] country, [state/province, city, ...]) ->
    (starts, label numbers, labels). IPv6 rows are skipped; gaps get label 0 (no data)."""
    labels, index = [["", ""]], {("", ""): 0}
    starts, idx = [], []
    expect = 0

    def add(start, lab):
        if idx and idx[-1] == lab:
            return                            # same place as the range before: merge
        starts.append(start)
        idx.append(lab)

    for row in rows:
        if len(row) < 3 or "." not in row[0]:
            continue
        a, b = _ip4(row[0]), _ip4(row[1])
        if a < expect or b < a:
            raise ValueError(f"ranges out of order at {row[0]}")
        if len(row) >= 5:                     # city file: start,end,continent,country,region,...
            cc, region = row[3].strip(), row[4].strip()[:REGION_MAX]
        else:                                 # country file: start,end,country
            cc, region = row[2].strip(), ""
        if not cc or cc == "ZZ":
            cc, region = "", ""
        key = (cc, region)
        if key not in index:
            index[key] = len(labels)
            labels.append([cc, region])
            if len(labels) > 0xFFFF:
                raise ValueError("too many places for a u16 label")
        if a > expect:
            add(expect, 0)
        add(a, index[key])
        expect = b + 1
    if expect <= 0xFFFFFFFF:
        add(expect, 0)
    return starts, idx, labels


def open_source(args):
    """(text stream, source name)."""
    if args.input:
        p = Path(args.input)
        raw = open(p, "rb")
        if p.suffix == ".gz":
            raw = gzip.GzipFile(fileobj=raw)
        return io.TextIOWrapper(raw, encoding="utf-8", newline=""), p.name.split(".csv")[0]
    kind = "country" if args.country else "city"
    now = time.gmtime()
    months = [time.strftime("%Y-%m", now)]
    y, m = now.tm_year, now.tm_mon - 1
    months.append("%04d-%02d" % (y - (m == 0), m or 12))
    for month in months:
        url = URL.format(kind=kind, month=month)
        req = urllib.request.Request(url, headers={"User-Agent": "mh3u-revival geoip_update"})
        try:
            resp = urllib.request.urlopen(req, timeout=60)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise
        print(f"downloading {url}")
        return (io.TextIOWrapper(gzip.GzipFile(fileobj=resp), encoding="utf-8", newline=""),
                f"dbip-{kind}-lite-{month}")
    sys.exit("DB-IP's file for this month and last month isn't there; try --input")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=str(geoip.PATH.parent),
                    help="where geoip.bin goes (default %(default)s)")
    ap.add_argument("--country", action="store_true", help="country only, smaller download")
    ap.add_argument("--input", help="a DB-IP .csv or .csv.gz you downloaded")
    ap.add_argument("--owner", help="user to own the file (the server's user, e.g. mh3u)")
    args = ap.parse_args()

    stream, source = open_source(args)
    with stream:
        starts, idx, labels = convert(csv.reader(stream))
    data = geoip.pack(starts, idx, labels, source)
    geoip.parse(data)                         # check it reads back
    out = Path(args.dir)
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / "geoip.bin.tmp"
    tmp.write_bytes(data)
    if args.owner:
        shutil.chown(out, args.owner, args.owner)
        shutil.chown(tmp, args.owner, args.owner)
    os.replace(tmp, out / "geoip.bin")
    countries = len({cc for cc, _ in labels if cc})
    print(f"{out / 'geoip.bin'}: {len(starts)} ranges, {countries} countries, "
          f"{len(labels) - 1} places, {len(data) / 1e6:.1f} MB ({source})")


if __name__ == "__main__":
    main()

"""Country and state/province for an IP address, from a database on this machine.

deploy/geoip_update.py builds the database (geoip.bin) from DB-IP's free "IP to City
Lite" file (CC BY 4.0: "IP Geolocation by DB-IP", https://db-ip.com). Addresses are looked
up here and never sent anywhere. Metrics keep only the place (country code and state /
province), never the address or the city. With no database there are no places.

The file is <state dir>/geoip/geoip.bin, or MH3U_GEOIP. It is reloaded when it changes
(metrics check once a minute), so a monthly update needs no restart.

geoip.bin, little-endian: b"MH3UGEO1", u32 range count n, u32 header length h, a JSON
header of h bytes ({"source": ..., "labels": [[country, region], ...]}, label 0 = no data),
then n u32 range starts (IPv4, ascending; a range runs up to the next start) and n u16
label numbers.
"""
import array
import bisect
import ipaddress
import json
import logging
import os
import struct
import sys
from pathlib import Path

logger = logging.getLogger("mh3u.geoip")

MAGIC = b"MH3UGEO1"
STATE_DIR = Path(os.environ.get("MH3U_STATE_DIR") or os.environ.get("STATE_DIRECTORY")
                 or "state")
PATH = Path(os.environ.get("MH3U_GEOIP") or STATE_DIR / "geoip" / "geoip.bin")
ATTRIBUTION = "IP Geolocation by DB-IP"
ATTRIBUTION_URL = "https://db-ip.com"

_table = None          # (starts, labels index, labels, source)
_stamp = None          # (path, mtime, size) of the loaded file, or the missing one
_said_missing = False


def _u32_array():
    for code in ("I", "L"):
        if array.array(code).itemsize == 4:
            return array.array(code)
    raise RuntimeError("no 4-byte array type")


def pack(starts, label_idx, labels, source=""):
    """The geoip.bin bytes (deploy/geoip_update.py and the tests)."""
    head = json.dumps({"source": source, "labels": labels}, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")
    s, i = _u32_array(), array.array("H")
    s.extend(starts)
    i.extend(label_idx)
    if sys.byteorder == "big":
        s.byteswap()
        i.byteswap()
    return MAGIC + struct.pack("<II", len(s), len(head)) + head + s.tobytes() + i.tobytes()


def parse(data):
    if data[:8] != MAGIC:
        raise ValueError("not a geoip.bin file")
    n, h = struct.unpack_from("<II", data, 8)
    o = 16
    head = json.loads(data[o:o + h].decode("utf-8"))
    o += h
    starts, idx = _u32_array(), array.array("H")
    starts.frombytes(data[o:o + 4 * n])
    idx.frombytes(data[o + 4 * n:o + 6 * n])
    if sys.byteorder == "big":
        starts.byteswap()
        idx.byteswap()
    labels = [tuple(x) for x in head["labels"]]
    if len(starts) != n or len(idx) != n or (idx and max(idx) >= len(labels)):
        raise ValueError("geoip.bin is cut short or damaged")
    return starts, idx, labels, str(head.get("source", ""))


def load(path=None):
    """(Re)load the database if it changed. Cheap when it didn't (one stat)."""
    global _table, _stamp, _said_missing
    p = Path(path) if path else PATH
    try:
        st = p.stat()
    except OSError:
        if not _said_missing:
            logger.info("geoip: no database at %s (deploy/geoip_update.py builds it); "
                        "no player locations", p)
            _said_missing = True
        _table, _stamp = None, None
        return False
    stamp = (str(p), st.st_mtime, st.st_size)
    if stamp == _stamp:
        return _table is not None
    _stamp = stamp
    try:
        _table = parse(p.read_bytes())
    except (OSError, ValueError, KeyError) as e:
        logger.warning("geoip: can't read %s (%s); no player locations", p, e)
        _table = None
        return False
    _said_missing = False
    logger.info("geoip: %d ranges from %s", len(_table[0]), _table[3] or p.name)
    return True


def place(ip):
    """(country code, state/province or "") for a public IPv4 address, else None."""
    t = _table
    if t is None or not ip:
        return None
    try:
        a = ipaddress.ip_address(str(ip).strip())
    except ValueError:
        return None
    if a.version == 6:
        a = a.ipv4_mapped
        if a is None:
            return None
    if not a.is_global:                       # LAN, loopback, CGNAT/VPN ranges
        return None
    starts, idx, labels, _ = t
    i = bisect.bisect_right(starts, int(a)) - 1
    if i < 0:
        return None
    cc, region = labels[idx[i]]
    if not cc or cc == "ZZ":
        return None
    return cc, region


def loaded():
    return _table is not None

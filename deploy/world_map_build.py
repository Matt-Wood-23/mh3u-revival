"""Build admin_world.py, the world map on the admin page's Metrics section, from Natural Earth's
countries (public domain, https://www.naturalearthdata.com). Run from the repo root:

    python deploy/world_map_build.py

It downloads the 1:110m countries for the outlines and the 1:50m ones for the point each
country's circle sits on (the 1:50m set also has small countries, e.g. Singapore), projects them
with the Natural Earth projection, simplifies the outlines and writes admin_world.py (about
35 KB). --src DIR reads ne_110m.geojson and ne_50m.geojson from DIR instead of downloading.
Only needed again to change the map's look.
"""
import argparse
import json
import math
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/"
       "ne_{}_admin_0_countries.geojson")
WIDTH = 2000                 # viewBox units; the page draws it about 1000 px wide
LAT_MIN, LAT_MAX = -56.0, 84.0
TOLERANCE = 1.1              # simplification, in viewBox units
SKIP = {"AQ"}                # Antarctica


def project(lon, lat):
    """Natural Earth projection (d3-geo's naturalEarth1Raw), radians in, unit-free out."""
    lam, phi = math.radians(lon), math.radians(max(LAT_MIN, min(LAT_MAX, lat)))
    p2 = phi * phi
    p4 = p2 * p2
    x = lam * (0.8707 - 0.131979 * p2 + p4 * (-0.013791 + p4 * (0.003971 * p2 - 0.001529 * p4)))
    y = phi * (1.007226 + p2 * (0.015085 + p4 * (-0.044475 + 0.028874 * p2 - 0.005916 * p4)))
    return x, y


X0, _ = project(-180, 0)
_, Y1 = project(0, LAT_MAX)
_, Y0 = project(0, LAT_MIN)
SCALE = WIDTH / (2 * -X0)
HEIGHT = round((Y1 - Y0) * SCALE)


def to_view(lon, lat):
    x, y = project(lon, lat)
    return (x - X0) * SCALE, (Y1 - y) * SCALE


def simplify_ring(pts, tol):
    """Douglas-Peucker on a closed ring: split it at the point farthest from the first one,
    since a line from the first point to itself (the closing point) measures nothing."""
    if len(pts) < 4:
        return pts
    x0, y0 = pts[0]
    far = max(range(len(pts)), key=lambda i: (pts[i][0] - x0) ** 2 + (pts[i][1] - y0) ** 2)
    return simplify(pts[:far + 1], tol)[:-1] + simplify(pts[far:], tol)


def simplify(pts, tol):
    """Douglas-Peucker on an open line (both ends kept)."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = pts[a], pts[b]
        dx, dy = bx - ax, by - ay
        n = math.hypot(dx, dy) or 1e-9
        best, at = -1.0, None
        for i in range(a + 1, b):
            px, py = pts[i]
            d = abs(dy * (px - ax) - dx * (py - ay)) / n
            if d > best:
                best, at = d, i
        if at is not None and best > tol:
            keep[at] = True
            stack += [(a, at), (at, b)]
    return [p for p, k in zip(pts, keep) if k]


def ring_path(ring):
    pts = simplify_ring([to_view(lon, lat) for lon, lat in ring], TOLERANCE)
    pts = [(round(x), round(y)) for x, y in pts]
    out = [pts[0]]
    for p in pts[1:]:
        if p != out[-1]:
            out.append(p)
    if len(out) < 4:                         # too small to see at this size
        return ""
    d = "M%d %d" % out[0]
    for (x0, y0), (x1, y1) in zip(out, out[1:]):
        d += "l%d %d" % (x1 - x0, y1 - y0)
    return d.replace(" -", "-") + "z"


def code(props):
    for k in ("ISO_A2_EH", "ISO_A2", "WB_A2"):
        v = props.get(k)
        if v and v != "-99" and len(v) == 2:
            return v
    return None


def load(name, src):
    if src:
        return json.loads((Path(src) / f"ne_{name}.geojson").read_text(encoding="utf-8"))
    with urllib.request.urlopen(URL.format(name), timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", help="folder with ne_110m.geojson and ne_50m.geojson")
    ap.add_argument("--out", default=str(ROOT / "admin_world.py"))
    a = ap.parse_args()

    shapes = {}
    for f in load("110m", a.src)["features"]:
        cc = code(f["properties"])
        if not cc or cc in SKIP:
            continue
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        d = "".join(ring_path(poly[0]) for poly in polys)     # outer rings only
        if d:
            shapes[cc] = shapes.get(cc, "") + d
    points = {}
    for f in load("50m", a.src)["features"]:
        p = f["properties"]
        cc = code(p)
        if not cc or cc in SKIP or p.get("LABEL_X") is None:
            continue
        if cc not in points or p.get("TYPE") in ("Sovereign country", "Country"):
            x, y = to_view(p["LABEL_X"], p["LABEL_Y"])
            points[cc] = [round(x), round(y)]

    world = {"w": WIDTH, "h": HEIGHT, "shapes": dict(sorted(shapes.items())),
             "points": dict(sorted(points.items()))}
    text = ('"""World map for the admin page (admin_page.py), made by deploy/world_map_build.py '
            "from\nNatural Earth's countries (public domain). Generated: don't edit by hand.\n\n"
            "shapes: ISO 3166 two-letter code -> SVG path (viewBox 0 0 w h, Natural Earth "
            "projection).\npoints: code -> [x, y] where that country's circle goes.\n\"\"\"\n"
            "WORLD = " + json.dumps(world, separators=(",", ":")) + "\n")
    Path(a.out).write_text(text, encoding="utf-8", newline="\n")
    print(f"{a.out}: {len(shapes)} outlines, {len(points)} points, {len(text) // 1024} KB, "
          f"viewBox 0 0 {WIDTH} {HEIGHT}")


if __name__ == "__main__":
    sys.exit(main())

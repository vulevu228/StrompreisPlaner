"""
One-time build of the Europe map outline used by the website.

Downloads Natural Earth 1:50m country borders (public domain), projects them
(Lambert azimuthal equal-area, centred on Germany), clips them to a Europe
window, simplifies them and writes SVG path strings to docs/data/europe-map.json.
The website then draws the map without loading anything from other servers.

Only needed again if the map window or detail should change.
Extra dependency (not needed in GitHub Actions):  pip install shapely

Run:  python scripts/build_map.py
"""

import json
import math
from pathlib import Path

import requests
from shapely.geometry import box, shape, MultiPolygon, Polygon
from shapely.ops import transform

SRC = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"
OUT = Path(__file__).resolve().parent.parent / "docs" / "data" / "europe-map.json"
LON0, LAT0 = math.radians(10), math.radians(52)   # projection centre
WIDTH = 600                                       # SVG units
WINDOW = (-11.5, 35.0, 32.0, 64.5)                # lon/lat box that stays visible
TOLERANCE = 0.35                                  # simplification in SVG units


def laea(lon, lat):
    lon, lat = math.radians(lon), math.radians(lat)
    k = math.sqrt(2 / (1 + math.sin(LAT0) * math.sin(lat) + math.cos(LAT0) * math.cos(lat) * math.cos(lon - LON0)))
    x = k * math.cos(lat) * math.sin(lon - LON0)
    y = k * (math.cos(LAT0) * math.sin(lat) - math.sin(LAT0) * math.cos(lat) * math.cos(lon - LON0))
    return x, y


def main() -> None:
    features = requests.get(SRC, timeout=120).json()["features"]
    # visible window in projected units: project a dense outline of the lon/lat box
    lo0, la0, lo1, la1 = WINDOW
    edge = [laea(lo0 + (lo1 - lo0) * i / 40, la) for i in range(41) for la in (la0, la1)] + \
           [laea(lo, la0 + (la1 - la0) * i / 40) for i in range(41) for lo in (lo0, lo1)]
    xs, ys = [p[0] for p in edge], [p[1] for p in edge]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    scale = WIDTH / (x1 - x0)
    height = round((y1 - y0) * scale)
    to_svg = lambda x, y, z=None: ((x - x0) * scale, (y1 - y) * scale)  # SVG y points down
    clip = box(-2, -2, WIDTH + 2, height + 2)
    near = box(-30, 25, 50, 75)  # drop overseas territories before projecting

    out = {}
    for f in features:
        p = f["properties"]
        code = p.get("ADM0_A3")
        geom = shape(f["geometry"]).intersection(near)
        if geom.is_empty:
            continue
        geom = transform(lambda x, y, z=None: laea(x, y), geom)
        geom = transform(to_svg, geom).intersection(clip).simplify(TOLERANCE, preserve_topology=True)
        if geom.is_empty or geom.area < 4:
            continue
        polys = [geom] if isinstance(geom, Polygon) else [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]
        d = ""
        for poly in polys:
            if poly.area < 1.5:  # tiny islands
                continue
            for ring in [poly.exterior, *poly.interiors]:
                pts = list(ring.coords)[:-1]
                d += "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z"
        if d:
            # label anchor: centre of the largest piece
            big = max(polys, key=lambda g: g.area).representative_point()
            out[code] = {"d": d, "c": [round(big.x, 1), round(big.y, 1)]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"viewBox": f"0 0 {WIDTH} {height}", "countries": out}, separators=(",", ":")), encoding="utf-8")
    print(f"{len(out)} countries, viewBox 0 0 {WIDTH} {height}, {OUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()

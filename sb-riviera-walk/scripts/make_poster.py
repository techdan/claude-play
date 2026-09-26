"""Render the illustrated Loma Staircase Loop poster (SVG inside an HTML shell).

Geometry is the same as the plain map: streets, footpaths, steps, buildings and
parks come from Overture Maps (OpenStreetMap-derived) and the route is
route.geojson from route.py. The illustration layer (paper texture, roof
colours, tree canopy, mountains, vignettes) is decoration only. It never moves
a street, path, stair or the route.

usage: python3 make_poster.py DATA_DIR ROUTE_GEOJSON OUT_HTML
"""
import base64
import html
import json
import math
import random
import sys
from pathlib import Path

import numpy as np
from shapely import transform
from shapely.geometry import LineString, Point, Polygon, box, shape
from shapely.ops import linemerge, substring, unary_union
from shapely.prepared import prep

DATA, ROUTE, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
# "poster" (default) renders the full poster; "base" renders only the painted map
# (no route, labels, header, panel or pictures) for the GPS page to draw over.
MODE = sys.argv[4] if len(sys.argv) > 4 else "poster"
HERE = Path(__file__).resolve().parent
rng = random.Random(1828)

# ------------------------------------------------------------ projection
W, H = 1800, 1900           # poster size, px
S = 1.9                     # px per metre
KX = 111320 * math.cos(math.radians(34.438))
KY = 110950
LON0 = -119.7078 - 70 / (S * KX)      # route's west edge sits 70 px from the left
LAT1 = 34.4407 + 460 / (S * KY)       # route's north edge sits 460 px from the top
LON1 = LON0 + W / (S * KX)
LAT0 = LAT1 - H / (S * KY)
WINDOW = box(LON0, LAT0, LON1, LAT1)


def xy(lon, lat):
    return ((lon - LON0) * KX * S, (LAT1 - lat) * KY * S)


def to_px(g):
    return transform(g, lambda c: np.column_stack(((c[:, 0] - LON0) * KX * S, (LAT1 - c[:, 1]) * KY * S)))


def d_of(g):
    out = []
    for p in getattr(g, "geoms", [g]):
        if p.is_empty:
            continue
        if p.geom_type == "Polygon":
            for ring in [p.exterior, *p.interiors]:
                out.append("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in ring.coords) + "Z")
        elif p.geom_type == "LineString":
            out.append("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in p.coords))
        else:
            out.append(d_of(p))
    return " ".join(out)


def load(kind):
    return json.load(open(f"{DATA}/{kind}.geojson"))["features"]


# ------------------------------------------------------------ data
ROAD_W = {"primary": 13, "secondary": 12, "tertiary": 11, "residential": 8.5,
          "unclassified": 8, "living_street": 7, "service": 4.6}
roads = {k: [] for k in ROAD_W}
foot, steps, named = [], [], {}
for f in load("segment"):
    p = f["properties"]
    g = shape(f["geometry"])
    if p["subtype"] != "road" or not g.intersects(WINDOW.buffer(0.001)):
        continue
    gm = to_px(g)
    c = p["class"]
    if c in ROAD_W:
        roads[c].append(gm)
        n = (p["names"] or {}).get("primary")
        if n:
            named.setdefault(n, []).append(gm)
    elif c in ("footway", "path", "pedestrian", "cycleway"):
        foot.append(gm)
    elif c == "steps":
        steps.append(gm)

parks, pitches = [], []
for f in load("land_use"):
    g = shape(f["geometry"])
    if g.intersects(WINDOW):
        if f["properties"]["subtype"] == "park":
            parks.append(to_px(g))
        elif f["properties"]["subtype"] == "recreation":
            pitches.append(to_px(g))
pools = []
for f in load("water"):
    g = shape(f["geometry"])
    if g.intersects(WINDOW) and f["properties"]["class"] == "swimming_pool":
        pools.append(to_px(g))
real_trees = [to_px(shape(f["geometry"])) for f in load("land")
              if f["properties"]["class"] == "tree" and shape(f["geometry"]).intersects(WINDOW)]

HOME_PT = Point(-119.70592, 34.43753)
buildings, hotel, home = [], None, None
for f in load("building"):
    g = shape(f["geometry"])
    if not g.intersects(WINDOW) or g.geom_type not in ("Polygon", "MultiPolygon"):
        continue
    if g.contains(HOME_PT):
        home = to_px(g)
    elif f["properties"].get("class") == "hotel":
        hotel = to_px(g)
    else:
        buildings.append(to_px(g))

route = json.load(open(ROUTE))
rfeats, wps = route["features"], route["waypoints"]
ordered = []
for f in rfeats:
    cs = f["geometry"]["coordinates"]
    ordered.extend(cs if not ordered else cs[1:])
route_line = to_px(LineString(ordered))
total_m = route["properties"]["length_m"]

# El Encanto loop ring, traced by the route itself (see make_map.py).
alv = next(f for f in rfeats if f["properties"]["name"] == "Alvarado Place")
i0 = ordered.index(alv["geometry"]["coordinates"][0])
CORNER = [-119.7046891, 34.4384814]
i1 = next(i for i in range(i0 + 5, len(ordered)) if ordered[i] == CORNER)
loop_poly = to_px(Polygon(ordered[i0:i1 + 1])).buffer(0)

# ------------------------------------------------------------ svg pieces
defs, base, top = [], [], []
defs.append("""
<filter id="paper" x="0" y="0" width="100%" height="100%">
  <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7" result="n"/>
  <feColorMatrix in="n" type="matrix" values="0 0 0 0 0.45  0 0 0 0 0.36  0 0 0 0 0.25  0 0 0 0.10 0"/>
</filter>
<filter id="wash" x="-5%" y="-5%" width="110%" height="110%">
  <feTurbulence type="fractalNoise" baseFrequency="0.018" numOctaves="3" seed="4" result="t"/>
  <feDisplacementMap in="SourceGraphic" in2="t" scale="9" xChannelSelector="R" yChannelSelector="G" result="d"/>
  <feGaussianBlur in="d" stdDeviation="0.6"/>
</filter>
<filter id="blob" x="-20%" y="-20%" width="140%" height="140%">
  <feTurbulence type="fractalNoise" baseFrequency="0.09" numOctaves="2" seed="11" result="t"/>
  <feDisplacementMap in="SourceGraphic" in2="t" scale="4" xChannelSelector="R" yChannelSelector="G"/>
</filter>
<filter id="shadow" x="-10%" y="-10%" width="130%" height="130%">
  <feDropShadow dx="3" dy="5" stdDeviation="5" flood-color="#3a2a18" flood-opacity=".28"/>
</filter>
<radialGradient id="canopy" cx=".35" cy=".3" r=".75">
  <stop offset="0" stop-color="#9DBB6E"/><stop offset=".6" stop-color="#6E9A4E"/><stop offset="1" stop-color="#4E7A3C"/>
</radialGradient>
<radialGradient id="canopy2" cx=".35" cy=".3" r=".75">
  <stop offset="0" stop-color="#B4C98A"/><stop offset=".6" stop-color="#86A864"/><stop offset="1" stop-color="#5F8748"/>
</radialGradient>
<radialGradient id="canopy3" cx=".35" cy=".3" r=".75">
  <stop offset="0" stop-color="#8FB08A"/><stop offset=".6" stop-color="#5C8A62"/><stop offset="1" stop-color="#3F6A4A"/>
</radialGradient>
<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#CFE3EE"/><stop offset=".55" stop-color="#EEF1E8"/><stop offset="1" stop-color="#F4EEDD"/>
</linearGradient>
<linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#F4EEDD" stop-opacity="1"/><stop offset="1" stop-color="#F4EEDD" stop-opacity="0"/>
</linearGradient>
<linearGradient id="sea" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#8CC3D3"/><stop offset="1" stop-color="#3F86A3"/>
</linearGradient>
""")

# Ground and lawns.
base.append(f'<rect width="{W}" height="{H}" fill="#EDE6CF"/>')
base.append(f'<rect width="{W}" height="{H}" fill="#DCE3C0" opacity=".55" filter="url(#wash)"/>')
base.append(f'<path d="{d_of(loop_poly)}" fill="#F3D27A" fill-opacity=".45" filter="url(#wash)"/>')
for g in parks:
    base.append(f'<path d="{d_of(g)}" fill="#AFCB86" stroke="#8FB06A" stroke-width="2" filter="url(#wash)"/>')
for g in pitches:
    base.append(f'<path d="{d_of(g)}" fill="#A9C98A" stroke="#fff" stroke-width="1.5"/>')

# Roads: soft casing then cream fill.
order = ["service", "living_street", "unclassified", "residential", "tertiary", "secondary", "primary"]
for k in order:
    if roads[k]:
        base.append(f'<path d="{" ".join(d_of(g) for g in roads[k])}" fill="none" stroke="#C9BBA0" '
                    f'stroke-width="{ROAD_W[k]*S+3:.1f}" stroke-linecap="round" stroke-linejoin="round"/>')
for k in order:
    if roads[k]:
        base.append(f'<path d="{" ".join(d_of(g) for g in roads[k])}" fill="none" stroke="#FBF6EA" '
                    f'stroke-width="{ROAD_W[k]*S:.1f}" stroke-linecap="round" stroke-linejoin="round"/>')
base.append(f'<path d="{" ".join(d_of(g) for g in foot)}" fill="none" stroke="#A89574" stroke-width="1.6" '
            f'stroke-dasharray="4 3" stroke-linecap="round"/>')
base.append(f'<path d="{" ".join(d_of(g) for g in steps)}" fill="none" stroke="#8A6A45" stroke-width="7" '
            f'stroke-dasharray="1.4 1.8"/>')

# Pools.
for g in pools:
    if g.geom_type == "Point":
        base.append(f'<rect x="{g.x-4:.1f}" y="{g.y-3:.1f}" width="8" height="6" rx="1.5" fill="#7FC0D6" stroke="#fff"/>')
    else:
        base.append(f'<path d="{d_of(g)}" fill="#7FC0D6" stroke="#fff"/>')

# Illustrative tree canopy: only where there is no street, path or building.
blocked = unary_union(
    [g.buffer(ROAD_W[k] * S / 2 + 4) for k in ROAD_W for g in roads[k]]
    + [g.buffer(4) for g in foot + steps]
    + [g.buffer(2) for g in buildings]
    + ([home.buffer(3)] if home else []) + ([hotel.buffer(3)] if hotel else []))
blocked_p = prep(blocked)
parks_p = prep(unary_union(parks)) if parks else None
loop_p = prep(loop_poly)
tree_marks = []
step = 15
for gx in np.arange(0, W, step):
    for gy in np.arange(300, H, step):
        x, y = gx + rng.uniform(-6, 6), gy + rng.uniform(-6, 6)
        pt = Point(x, y)
        if blocked_p.contains(pt):
            continue
        in_park = parks_p is not None and parks_p.contains(pt)
        chance = 0.75 if in_park else (0.55 if loop_p.contains(pt) else 0.34)
        if rng.random() > chance:
            continue
        r = rng.uniform(5, 10) if not in_park else rng.uniform(7, 12)
        kind = "palm" if (not in_park and rng.random() < 0.07) else "tree"
        tree_marks.append((y, x, r, kind))
for g in real_trees:
    tree_marks.append((g.y, g.x, 9, "tree"))
tree_marks.sort()

bld = []
roof_tones = ["#C9674A", "#D0775A", "#BF5E43", "#C98463", "#B9A48C"]
for g in buildings + ([hotel] if hotel else []):
    tone = "#E2A83E" if g is hotel else rng.choice(roof_tones)
    dd = d_of(g)
    bld.append(f'<path d="{dd}" transform="translate(2.6,3.2)" fill="#5A4430" fill-opacity=".22"/>')
    bld.append(f'<path d="{dd}" fill="#FBF5EA" stroke="#C7B59C" stroke-width=".8"/>')
    bld.append(f'<path d="{dd}" transform="translate(-.8,-3)" fill="{tone}" stroke="#8E4A33" stroke-width=".7"/>')
    mrr = g.minimum_rotated_rectangle
    if mrr.geom_type == "Polygon":
        c = list(mrr.exterior.coords)
        e1 = LineString([c[0], c[1]]); e2 = LineString([c[1], c[2]])
        a, b = (c[1], c[2]) if e1.length >= e2.length else (c[0], c[1])
        long_edge = LineString([a, b])
        if long_edge.length > 10:
            cx, cy = g.centroid.x, g.centroid.y
            dx = (b[0] - a[0]) / 2 * .8; dy = (b[1] - a[1]) / 2 * .8
            bld.append(f'<path d="M{cx-dx-.8:.1f},{cy-dy-3:.1f} L{cx+dx-.8:.1f},{cy+dy-3:.1f}" stroke="#FBE3CF" '
                       f'stroke-opacity=".7" stroke-width="1.1"/>')

canopy = []
for (y, x, r, kind) in tree_marks:
    if kind == "palm":
        fr = []
        for k in range(7):
            ang = k * (360 / 7) + rng.uniform(-10, 10)
            fr.append(f'<path d="M0,0 q{r*.6:.1f},-{r*.5:.1f} {r*1.3:.1f},0" transform="rotate({ang:.0f})"/>')
        canopy.append(f'<g transform="translate({x:.1f},{y:.1f})"><ellipse cx="3" cy="4" rx="{r*.9:.1f}" ry="{r*.45:.1f}" '
                      f'fill="#3a2a18" fill-opacity=".16"/><g fill="none" stroke="#5E8A3C" stroke-width="2.3" '
                      f'stroke-linecap="round">{"".join(fr)}</g><circle r="1.8" fill="#7A5A3A"/></g>')
    else:
        grad = rng.choice(["canopy", "canopy2", "canopy3"])
        canopy.append(f'<ellipse cx="{x+3:.1f}" cy="{y+4:.1f}" rx="{r:.1f}" ry="{r*.7:.1f}" fill="#3a2a18" fill-opacity=".16"/>'
                      f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="url(#{grad})"/>')

base.append('<g>' + "".join(bld) + '</g>')
base.append('<g filter="url(#blob)">' + "".join(canopy) + '</g>')
if home is not None:
    hd = d_of(home)
    base.append(f'<path d="{hd}" transform="translate(2.6,3.2)" fill="#5A4430" fill-opacity=".25"/>'
                f'<path d="{hd}" fill="#FBF5EA" stroke="#2B5C9A" stroke-width="1"/>'
                f'<path d="{hd}" transform="translate(-.8,-3)" fill="#C13C6E" stroke="#fff" stroke-width="1.4"/>')

# ------------------------------------------------------------ route
BLUE, ORANGE, NAVY = "#2B6CB0", "#E07A2E", "#1F3B63"
rd = d_of(route_line)
top.append(f'<path d="{rd}" fill="none" stroke="#fff" stroke-width="13" stroke-linecap="round" stroke-linejoin="round" stroke-opacity=".95"/>')
top.append(f'<path d="{rd}" fill="none" stroke="{BLUE}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>')
sd = " ".join(d_of(to_px(shape(f["geometry"]))) for f in rfeats if f["properties"]["class"] == "steps")
top.append(f'<path d="{sd}" fill="none" stroke="#fff" stroke-width="16" stroke-linecap="butt"/>')
top.append(f'<path d="{sd}" fill="none" stroke="{ORANGE}" stroke-width="14" stroke-dasharray="2.2 1.6"/>')
dist = 55
while dist < route_line.length - 25:
    a = route_line.interpolate(dist); b = route_line.interpolate(dist + 3)
    ang = math.degrees(math.atan2(b.y - a.y, b.x - a.x))
    top.append(f'<path d="M-5,-5.5 L6,0 L-5,5.5Z" fill="{BLUE}" stroke="#fff" stroke-width="1.6" '
               f'stroke-linejoin="round" transform="translate({a.x:.1f},{a.y:.1f}) rotate({ang:.1f})"/>')
    dist += 105

# ------------------------------------------------------------ street labels
LABELS = {
    "Loma Street": ("Loma St", True, (-119.7051, 34.43700)),
    "Grand Avenue": ("Grand Ave", True, (-119.7074, 34.43688)),
    "Sierra Street": ("Sierra St", True, (-119.70765, 34.43745)),
    "Alameda Padre Serra": ("Alameda Padre Serra", True, (-119.70290, 34.43757)),
    "Lasuen Road": ("Lasuen Rd", True, (-119.70310, 34.43855)),
    "Alvarado Place": ("Alvarado Pl", True, (-119.70470, 34.43935)),
    "Mission Ridge Road": ("Mission Ridge Rd", True, (-119.70290, 34.44035)),
    "San Carlos Road": ("San Carlos Rd", True, (-119.70178, 34.43965)),
    "Moreno Road": ("Moreno Rd", False, (-119.70410, 34.43690)),
    "East Pedregosa Street": ("E Pedregosa St", False, (-119.70715, 34.43605)),
    "Cleveland Avenue": ("Cleveland Ave", False, (-119.7072, 34.43585)),
    "Via Granada": ("Via Granada", False, (-119.70795, 34.43930)),
    "Las Tunas Road": ("Las Tunas Rd", False, (-119.70560, 34.44095)),
    "Arguello Road": ("Arguello Rd", False, (-119.70200, 34.43670)),
    "Paterna Road": ("Paterna Rd", False, (-119.69960, 34.43860)),
    "El Encanto Road": ("El Encanto Rd", False, (-119.70225, 34.43914)),
    "Mira Vista Avenue": ("Mira Vista Ave", False, (-119.70230, 34.43981)),
    "Emerson Avenue": ("Emerson Ave", False, (-119.70780, 34.43600)),
    "Laguna Street": ("Laguna St", False, (-119.70760, 34.43480)),
    "Garden Street": ("Garden St", False, (-119.70560, 34.43460)),
    "East Valerio Street": ("E Valerio St", False, (-119.70400, 34.43560)),
    "Prospect Avenue": ("Prospect Ave", False, (-119.70560, 34.43510)),
    "Loma Media Road": ("Loma Media Rd", False, (-119.69950, 34.44000)),
}
for i, (name, (text, on_route, hint_ll)) in enumerate(LABELS.items()):
    if name not in named:
        continue
    u = unary_union(named[name])
    merged = u if u.geom_type == "LineString" else linemerge(u)
    hint = Point(*xy(*hint_ll))
    lines = list(getattr(merged, "geoms", [merged]))
    ln = min(lines, key=lambda l: l.distance(hint))
    if ln.distance(hint) > 60:
        continue
    at = ln.project(hint)
    half = max(len(text) * 4.6 + 12, 34)
    a, b = max(0, at - half), min(ln.length, at + half)
    seg = substring(ln, a, b).simplify(3)
    if on_route:
        off = seg.offset_curve(ROAD_W["residential"] * S / 2 + 10)
        if not off.is_empty and off.geom_type == "LineString":
            seg = off
    cs = list(seg.coords)
    if cs[-1][0] < cs[0][0]:
        cs = cs[::-1]
    defs.append(f'<path id="sl{i}" d="M' + " L".join(f"{x:.1f},{y:.1f}" for x, y in cs) + '"/>')
    cls = "sl on" if on_route else "sl"
    top.append(f'<text class="{cls}"><textPath href="#sl{i}" startOffset="50%" text-anchor="middle">{html.escape(text)}</textPath></text>')

# ------------------------------------------------------------ stops on the map
leglen = {}
for f in rfeats:
    leglen[f["properties"]["leg"]] = leglen.get(f["properties"]["leg"], 0) + f["properties"]["length_m"]
cum = [0.0]
for i in range(len(wps) - 1):
    cum.append(cum[-1] + leglen.get(i, 0))

STOPS = [
    # n, lon/lat, pin offset, label anchor, label offset from pin, name, stair?, waypoint
    (1, tuple(wps[0]["coord"]), (0, 0), "end", (-24, 6), "1828 Loma St", False, 0),
    (2, (-119.70671, 34.43680), (30, 4), "start", (22, 6), "Loma–Pedregosa Stairs", True, 1),
    (3, (-119.70741, 34.43791), (-30, 8), "middle", (0, 42), "Sierra St Stairs", True, 4),
    (4, (-119.70584, 34.43858), (-32, 0), "end", (-22, 6), "Riviera Stairway", True, 6),
    (5, (-119.70533, 34.43934), (0, -34), "middle", (0, -24), "Riviera Park Gardens", False, 8),
    (6, (-119.70435, 34.43892), (0, 0), "start", (22, 6), "Belmond El Encanto", False, 9),
    (7, (-119.70540, 34.43795), (0, 34), "start", (22, 6), "Orpet Park", False, 13),
]
for n, ll, (pdx, pdy), anchor, (ldx, ldy), name, stair, _ in STOPS:
    x, y = xy(*ll)
    px_, py_ = x + pdx, y + pdy
    col = ORANGE if stair else BLUE
    if pdx or pdy:
        top.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{px_:.1f}" y2="{py_:.1f}" stroke="{NAVY}" stroke-width="2"/>'
                   f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="{NAVY}"/>')
    top.append(f'<g class="pin" transform="translate({px_:.1f},{py_:.1f})"><circle r="16.5" fill="{col}"/>'
               f'<text y="6.2" text-anchor="middle">{n}</text></g>')
    top.append(f'<text class="stopname" x="{px_+ldx:.1f}" y="{py_+ldy:.1f}" text-anchor="{anchor}">{html.escape(name)}</text>')
sx, sy = xy(*wps[0]["coord"])
top.append(f'<text class="tag" x="{sx-24:.1f}" y="{sy+26:.1f}" text-anchor="end">START &amp; FINISH</text>')

# ------------------------------------------------------------ header (north: the Santa Ynez Mountains)
hdr = []
hdr.append(f'<rect width="{W}" height="360" fill="url(#sky)"/>')
def ridge(ybase, amp, seed, color, opacity, bottom=352):
    r = random.Random(seed)
    pts, x = [], -40
    p1, p2 = r.uniform(140, 260), r.uniform(60, 110)
    while x <= W + 40:
        y = ybase - amp * (0.55 + 0.3 * math.sin(x / p1 + seed) + 0.15 * math.sin(x / p2 + 2 * seed))
        pts.append((x, y)); x += 40
    d = f"M-40,{bottom} L{pts[0][0]:.0f},{pts[0][1]:.0f} "
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        d += f"Q{xa:.0f},{ya:.0f} {(xa+xb)/2:.0f},{(ya+yb)/2:.0f} "
    d += f"L{W+40},{bottom}Z"
    return f'<path d="{d}" fill="{color}" fill-opacity="{opacity}" filter="url(#wash)"/>'
hdr.append(ridge(250, 120, 3, "#A9BBD2", .8))
hdr.append(ridge(300, 90, 8, "#8AA0BF", .8))
hdr.append(ridge(345, 55, 13, "#93AE8C", .9))
hdr.append(f'<rect y="348" width="{W}" height="70" fill="url(#fade)"/>')
hdr.append('<text class="t1" x="900" y="118" text-anchor="middle">Santa Barbara</text>')
hdr.append('<text class="t2" x="900" y="178" text-anchor="middle">LOWER RIVIERA STAIRCASE WALK</text>')
hdr.append(f'<text class="t3" x="900" y="220" text-anchor="middle">STAIRWAYS · GARDENS · HILLSIDE STREETS · {total_m/1609.34:.2f}-MILE LOOP</text>')
hdr.append('<text class="t4" x="900" y="262" text-anchor="middle">From 1828 Loma Street and back again</text>')
hdr.append('<text class="t5" x="1540" y="310" text-anchor="middle">Santa Ynez Mountains (north)</text>')

def palm(x, y, h, lean, s=1.0):
    fr = []
    tx, ty = x + lean, y - h
    for k, (ang, ln) in enumerate([(-160, 70), (-130, 80), (-95, 60), (-60, 80), (-25, 72), (10, 60), (170, 55), (200, 60)]):
        a = math.radians(ang)
        ex, ey = tx + math.cos(a) * ln * s, ty + math.sin(a) * ln * s
        cx, cy = tx + math.cos(a) * ln * .5 * s, ty + math.sin(a) * ln * .5 * s - 22 * s
        fr.append(f'<path d="M{tx:.0f},{ty:.0f} Q{cx:.0f},{cy:.0f} {ex:.0f},{ey:.0f}" stroke="#4F7F3A" stroke-width="{7*s:.1f}" fill="none" stroke-linecap="round"/>')
        fr.append(f'<path d="M{tx:.0f},{ty:.0f} Q{cx:.0f},{cy:.0f} {ex:.0f},{ey:.0f}" stroke="#7FAE5A" stroke-width="{2.4*s:.1f}" fill="none" stroke-linecap="round"/>')
    trunk = f'<path d="M{x},{y} Q{x+lean*.2:.0f},{y-h*.5:.0f} {tx:.0f},{ty:.0f}" stroke="#8A6A48" stroke-width="{9*s:.1f}" fill="none" stroke-linecap="round"/>'
    return f'<g filter="url(#blob)">{trunk}{"".join(fr)}</g>'
hdr.append(palm(70, 380, 300, 20, 1.1))
hdr.append(palm(150, 380, 220, -18, .85))
hdr.append(palm(1720, 380, 290, -24, 1.1))
hdr.append(palm(1640, 380, 200, 14, .8))
# Bougainvillea clusters at the header's lower corners.
for (bx, by) in [(20, 360), (120, 372), (1700, 366), (1780, 352)]:
    for _ in range(26):
        rx, ry = bx + rng.uniform(-60, 60), by + rng.uniform(-30, 20)
        hdr.append(f'<circle cx="{rx:.0f}" cy="{ry:.0f}" r="{rng.uniform(4,8):.1f}" fill="{rng.choice(["#C2306B","#D8497F","#E26A98","#A92660"])}" fill-opacity=".9"/>')
    for _ in range(10):
        rx, ry = bx + rng.uniform(-60, 60), by + rng.uniform(-20, 25)
        hdr.append(f'<ellipse cx="{rx:.0f}" cy="{ry:.0f}" rx="9" ry="5" fill="#5E8A3C" transform="rotate({rng.uniform(0,180):.0f} {rx:.0f} {ry:.0f})"/>')

# ------------------------------------------------------------ itinerary panel
PX, PY, PW = 1318, 440, 452
panel = [f'<g filter="url(#shadow)"><rect x="{PX}" y="{PY}" width="{PW}" height="1085" rx="10" fill="#FBF7EC" stroke="#D8CCB4"/></g>']
panel.append(f'<text class="ph" x="{PX+PW/2}" y="{PY+50}" text-anchor="middle">A Walking Tour Itinerary</text>')
panel.append(f'<path d="M{PX+40},{PY+68} H{PX+PW-40}" stroke="#C9B99B" stroke-width="1.2"/>')
ITEMS = [
    (1, "1828 Loma St", "Start and finish, below Orpet Park", False, 0),
    (2, "Loma–Pedregosa Stairs", "Two hidden flights down to Grand Ave", True, 1),
    (3, "Sierra St Stairs", "From the dead end up to Alameda Padre Serra", True, 4),
    (4, "Riviera Stairway", "Seven short runs up to Riviera Park", True, 6),
    (5, "Riviera Park Gardens", "Garden circle on the old college campus", False, 8),
    (6, "Belmond El Encanto Loop", "Alvarado Pl, Mission Ridge Rd, San Carlos Rd, Lasuen Rd", False, 9),
    (7, "Orpet Park", "Park steps and path back down to Loma St", False, 13),
]
yy = PY + 112
for n, name, sub, stair, w in ITEMS:
    col = ORANGE if stair else BLUE
    panel.append(f'<circle cx="{PX+42}" cy="{yy-7}" r="17" fill="{col}"/><text class="pn" x="{PX+42}" y="{yy-1}" text-anchor="middle">{n}</text>')
    panel.append(f'<text class="pi" x="{PX+74}" y="{yy-4}">{html.escape(name)}</text>')
    panel.append(f'<text class="pm" x="{PX+PW-28}" y="{yy-4}" text-anchor="end">mi {cum[w]/1609.34:.2f}</text>')
    words, lines, cur = sub.split(), [], ""
    for wd in words:
        if len(cur) + len(wd) > 38:
            lines.append(cur); cur = wd
        else:
            cur = (cur + " " + wd).strip()
    lines.append(cur)
    for j, l in enumerate(lines):
        panel.append(f'<text class="ps" x="{PX+74}" y="{yy+20+j*21}">{html.escape(l)}</text>')
    yy += 58 + 21 * len(lines)
panel.append(f'<text class="pi" x="{PX+74}" y="{yy-4}">Back to 1828 Loma St</text>'
             f'<text class="pm" x="{PX+PW-28}" y="{yy-4}" text-anchor="end">mi {total_m/1609.34:.2f}</text>')
yy += 30
panel.append(f'<path d="M{PX+40},{yy} H{PX+PW-40}" stroke="#C9B99B" stroke-width="1.2"/>')
yy += 36
LEG = [
    (f'<path d="M0,0 H44" stroke="#fff" stroke-width="13" stroke-linecap="round"/><path d="M0,0 H44" stroke="{BLUE}" stroke-width="7" stroke-linecap="round"/><path d="M17,-5.5 L28,0 L17,5.5Z" fill="{BLUE}" stroke="#fff" stroke-width="1.4"/>', "Walking route (direction of travel)"),
    (f'<path d="M0,0 H44" stroke="{ORANGE}" stroke-width="14" stroke-dasharray="2.2 1.6"/>', "Stairs on the route"),
    ('<path d="M0,0 H44" stroke="#A89574" stroke-width="1.8" stroke-dasharray="4 3"/>', "Other mapped footpaths"),
    ('<rect x="2" y="-10" width="40" height="20" rx="3" fill="#F3D27A" fill-opacity=".7"/>', "Loop around Belmond El Encanto"),
    ('<rect x="2" y="-10" width="40" height="20" rx="3" fill="#AFCB86"/>', "Park"),
    ('<rect x="10" y="-9" width="24" height="18" fill="#C13C6E" stroke="#fff"/>', "1828 Loma St"),
]
for sym, txt in LEG:
    panel.append(f'<g transform="translate({PX+40},{yy})">{sym}</g><text class="pl" x="{PX+100}" y="{yy+6}">{txt}</text>')
    yy += 34
# North arrow and scale bar (true to the projection).
yy += 18
m100, ft500 = 100 * S, 500 * 0.3048 * S
panel.append(f'<g transform="translate({PX+40},{yy+8})">'
             f'<path d="M0,0 H{m100:.1f} M0,-6 V0 M{m100:.1f},-6 V0" stroke="{NAVY}" stroke-width="2" fill="none"/>'
             f'<text class="pl" x="{m100+8:.1f}" y="4">100 m</text>'
             f'<path d="M0,12 H{ft500:.1f} M0,18 V12 M{ft500:.1f},18 V12" stroke="{NAVY}" stroke-width="2" fill="none"/>'
             f'<text class="pl" x="{ft500+8:.1f}" y="23">500 ft</text></g>')
panel.append(f'<g transform="translate({PX+PW-60},{yy-78})"><circle r="24" fill="#FBF7EC" stroke="{NAVY}" stroke-width="1.5"/>'
             f'<path d="M0,-18 L8,10 L0,5 L-8,10Z" fill="{NAVY}"/><text class="pl" y="-30" text-anchor="middle">N</text></g>')

# ------------------------------------------------------------ vignettes (illustrations, not photos)
def stairs_scene():
    s = ['<rect width="320" height="210" fill="#DCEBF2"/>',
         '<path d="M0,40 Q80,20 160,36 T320,30 V210 H0Z" fill="#9FB2CC" opacity=".6"/>',
         '<path d="M0,0 H92 L118,210 H0Z" fill="#F1E4CC"/>', '<path d="M320,0 H228 L202,210 H320Z" fill="#EAD9BD"/>']
    for i in range(12):
        t0, t1 = i / 12, (i + 1) / 12
        y0, y1 = 210 - t0 * 150, 210 - t1 * 150
        w0, w1 = 90 - t0 * 55, 90 - t1 * 55
        s.append(f'<path d="M{160-w0:.1f},{y0:.1f} L{160+w0:.1f},{y0:.1f} L{160+w1:.1f},{y1:.1f} L{160-w1:.1f},{y1:.1f}Z" '
                 f'fill="{"#E7DCC8" if i % 2 == 0 else "#CDBDA2"}"/>')
    s.append('<path d="M86,210 L128,60 M234,210 L192,60" stroke="#5A4A3A" stroke-width="3"/>')
    for _ in range(60):
        x = rng.choice([rng.uniform(0, 100), rng.uniform(220, 320)]); y = rng.uniform(0, 120)
        s.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{rng.uniform(5,11):.0f}" fill="{rng.choice(["#C2306B","#D8497F","#E26A98","#5E8A3C","#7FAE5A"])}" fill-opacity=".9"/>')
    for _ in range(26):
        x = rng.choice([rng.uniform(0, 90), rng.uniform(230, 320)]); y = rng.uniform(140, 210)
        s.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{rng.uniform(8,16):.0f}" fill="{rng.choice(["#5E8A3C","#6E9A4E","#86A864"])}"/>')
    return "".join(s)

def park_scene():
    s = ['<rect width="320" height="210" fill="#DDEEF3"/>',
         '<path d="M0,95 Q70,60 150,82 T320,70 V210 H0Z" fill="#9FB2CC" opacity=".55"/>',
         '<path d="M0,130 Q160,95 320,125 V210 H0Z" fill="#9FC27A"/>', '<path d="M0,165 Q160,140 320,168 V210 H0Z" fill="#86B066"/>',
         '<path d="M150,210 Q170,170 210,150 L222,152 Q186,176 176,210Z" fill="#E9DFC9"/>']
    for (x, y, r) in [(70, 88, 50), (240, 96, 40), (300, 110, 28)]:
        s.append(f'<path d="M{x},{y+r*1.3:.0f} V{y+r*.2:.0f}" stroke="#6B4A2F" stroke-width="{r/5:.0f}"/>')
        for _ in range(14):
            s.append(f'<circle cx="{x+rng.uniform(-r,r)*.8:.0f}" cy="{y+rng.uniform(-r,r)*.45:.0f}" r="{rng.uniform(r*.3,r*.5):.0f}" fill="{rng.choice(["#4F7A3C","#5E8A47","#6E9A52","#86A864"])}"/>')
    s.append('<g fill="#D6CCB8" stroke="#9A8C74" stroke-width="1"><rect x="120" y="180" width="40" height="9"/><rect x="126" y="171" width="34" height="9"/><rect x="132" y="162" width="28" height="9"/></g>')
    s.append('<path d="M230,176 H286 M234,176 V190 M282,176 V190 M230,168 H286" stroke="#6B4A2F" stroke-width="4"/>')
    return "".join(s)

def encanto_scene():
    s = ['<rect width="320" height="210" fill="#DCEBF2"/>', '<path d="M0,150 H320 V210 H0Z" fill="#9FC27A"/>',
         '<rect x="36" y="86" width="170" height="74" fill="#FBF7EF"/>', '<path d="M24,90 L121,48 L218,90Z" fill="#C0553A"/>',
         '<path d="M24,90 L121,48 L218,90" fill="none" stroke="#8E3A26" stroke-width="3"/>']
    for x in (56, 100, 144):
        s.append(f'<path d="M{x},160 V122 a14,14 0 0 1 28,0 V160Z" fill="#6B4A2F"/>')
    s.append('<path d="M214,160 V104 H300 V160" stroke="#8E6B3E" stroke-width="5" fill="none"/><path d="M208,104 H306" stroke="#8E6B3E" stroke-width="7"/>')
    for _ in range(40):
        s.append(f'<circle cx="{rng.uniform(210,306):.0f}" cy="{rng.uniform(96,138):.0f}" r="{rng.uniform(4,8):.0f}" fill="{rng.choice(["#C2306B","#D8497F","#E26A98","#5E8A3C"])}"/>')
    s.append('<ellipse cx="150" cy="186" rx="80" ry="12" fill="#7FC0D6" stroke="#fff" stroke-width="2"/>')
    for x in (132, 156, 176):
        s.append(f'<ellipse cx="{x}" cy="{186+rng.uniform(-3,3):.0f}" rx="7" ry="3" fill="#5E8A3C"/>')
    s.append(palm(20, 170, 150, 10, .7).replace('filter="url(#blob)"', ''))
    return "".join(s)

VIGS = [(2, "Loma–Pedregosa Stairs", "Hidden flights to Grand Ave", stairs_scene(), 60, 1420, -2.5, ORANGE),
        (7, "Orpet Park", "Oaks, lawns and park steps", park_scene(), 470, 1440, 1.8, BLUE),
        (6, "Belmond El Encanto", "Loop it on public streets", encanto_scene(), 880, 1418, -1.5, BLUE)]
vig = []
for n, title, sub, scene, vx, vy, rot, col in VIGS:
    vig.append(f'<g transform="translate({vx},{vy}) rotate({rot})" filter="url(#shadow)">'
               f'<rect x="-14" y="-14" width="348" height="300" fill="#FFFDF7"/>'
               f'<g filter="url(#blob)"><svg x="0" y="0" width="320" height="210" viewBox="0 0 320 210">{scene}</svg></g>'
               f'<circle cx="24" cy="244" r="17" fill="{col}"/><text class="pn" x="24" y="250" text-anchor="middle">{n}</text>'
               f'<text class="vt" x="52" y="240">{html.escape(title)}</text><text class="vs" x="52" y="264">{html.escape(sub)}</text></g>')

# ------------------------------------------------------------ footer: pointer south
foot_g = [f'<rect y="{H-92}" width="{W}" height="92" fill="url(#sea)" filter="url(#wash)"/>',
          f'<path d="M0,{H-92} Q450,{H-110} 900,{H-92} T1800,{H-92} V{H-84} H0Z" fill="#F4EEDD" fill-opacity=".6"/>',
          f'<text class="ft" x="60" y="{H-40}">↓ Downhill to the south: downtown, the County Courthouse (1.2 mi walk, not on this loop) and the Pacific</text>',
          f'<text class="fs" x="{W-60}" y="{H-40}" text-anchor="end">Map data © OpenStreetMap contributors · Overture Maps 2026-09-23 · trees and pictures are illustrative</text>']

paper = f'<rect width="{W}" height="{H}" filter="url(#paper)" style="mix-blend-mode:multiply"/>'

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" class="poster">'
       f'<defs>{"".join(defs)}</defs>' + "".join(base) + "".join(top) + "".join(hdr)
       + "".join(panel) + "".join(vig) + "".join(foot_g) + paper + "</svg>")

font_css = []
for f in json.load(open(HERE / "fonts" / "fonts.json")):
    b64 = base64.b64encode((HERE / "fonts" / f["file"]).read_bytes()).decode()
    font_css.append(f'@font-face{{font-family:"{f["family"]}";font-style:{f["style"]};font-weight:{f["weight"]};'
                    f'src:url(data:font/woff2;base64,{b64}) format("woff2");unicode-range:{f["range"]};}}')

css = """
body{margin:0;background:#EDE6CF}
.poster{display:block;width:100%;height:auto}
.poster text{font-family:"Alegreya Sans",sans-serif}
.poster .t1{font:italic 800 112px "Alegreya",serif;fill:#1F3B63;paint-order:stroke;stroke:#F4EEDD;stroke-width:6px}
.poster .t2{font:800 50px "Alegreya SC",serif;fill:#1F3B63;letter-spacing:.04em;paint-order:stroke;stroke:#F4EEDD;stroke-width:5px}
.poster .t3{font:700 19px "Alegreya Sans",sans-serif;fill:#3B4E6B;letter-spacing:.22em;paint-order:stroke;stroke:#F4EEDD;stroke-width:4px}
.poster .t4{font:italic 700 30px "Alegreya",serif;fill:#1F3B63;paint-order:stroke;stroke:#F4EEDD;stroke-width:5px}
.poster .t5{font:italic 500 19px "Alegreya Sans",sans-serif;fill:#34465F;paint-order:stroke;stroke:#EEF1E8;stroke-width:4px}
.poster .sl{font:italic 500 14px "Alegreya Sans",sans-serif;fill:#6A5A45;paint-order:stroke;stroke:#FBF6EA;stroke-width:4px}
.poster .sl.on{font:italic 700 17px "Alegreya",serif;fill:#1F3B63;stroke:#F6F0DF;stroke-width:5px}
.poster .pin circle{stroke:#fff;stroke-width:3px}
.poster .pin text,.poster .pn{font:800 19px "Alegreya SC",serif;fill:#fff}
.poster .stopname{font:italic 800 21px "Alegreya",serif;fill:#1F3B63;paint-order:stroke;stroke:#FBF6EA;stroke-width:6px;stroke-linejoin:round}
.poster .tag{font:700 13px "Alegreya Sans",sans-serif;letter-spacing:.12em;fill:#C13C6E;paint-order:stroke;stroke:#fff;stroke-width:4px}
.poster .ph{font:italic 800 32px "Alegreya",serif;fill:#1F3B63}
.poster .pi{font:800 21px "Alegreya SC",serif;fill:#1F3B63}
.poster .pm{font:700 15px "Alegreya Sans",sans-serif;fill:#C13C6E;letter-spacing:.06em}
.poster .ps{font:italic 400 18px "Alegreya Sans",sans-serif;fill:#4A4038}
.poster .pl{font:500 17px "Alegreya Sans",sans-serif;fill:#2E2A26}
.poster .vt{font:800 22px "Alegreya SC",serif;fill:#1F3B63}
.poster .vs{font:italic 400 18px "Alegreya Sans",sans-serif;fill:#4A4038}
.poster .ft{font:700 21px "Alegreya Sans",sans-serif;fill:#fff}
.poster .fs{font:italic 400 15px "Alegreya Sans",sans-serif;fill:#EAF4F7}
"""
# Pieces the GPS page reuses: label paths and the vector layer above the paint.
overlay_defs = "".join(defs[1:])
overlay = "".join(top)
if MODE == "base":
    base_svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" class="poster">'
                f'<defs>{defs[0]}</defs>' + "".join(base) + paper + "</svg>")
    Path(OUT).write_text(f"<style>body{{margin:0}}.poster{{display:block;width:100%;height:auto}}</style>{base_svg}")
else:
    Path(OUT).write_text(f"<title>Lower Riviera Staircase Walk</title><style>{''.join(font_css)}{css}</style>{svg}")
print(f"wrote {OUT}: {len(svg)/1024:.0f} KB svg, {len(tree_marks)} canopy marks, {len(buildings)} buildings")

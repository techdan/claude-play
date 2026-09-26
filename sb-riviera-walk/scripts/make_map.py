"""Render the Loma Staircase Loop brochure (HTML with an inline SVG map).

The base map is drawn only from Overture Maps data (OpenStreetMap-derived):
streets, footpaths, steps, buildings, parks, pools and mapped trees. The walking
line is route.geojson from route.py, which is snapped to that same network.
Nothing on the map is hand-drawn except the stop illustrations on the cards.

usage: python3 make_map.py DATA_DIR ROUTE_GEOJSON OUT_HTML
"""
import html
import json
import math
import string
import sys
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box, shape
from shapely.ops import linemerge, unary_union

DATA, ROUTE, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
HERE = Path(__file__).resolve().parent

# Map window (lon/lat) and projection: local equirectangular, metres.
LON0, LON1, LAT0, LAT1 = -119.7087, -119.7005, 34.43575, 34.44125
KX = 111320 * math.cos(math.radians((LAT0 + LAT1) / 2))
KY = 110950
S = 1.55  # SVG units per metre
W = (LON1 - LON0) * KX * S
H = (LAT1 - LAT0) * KY * S
WINDOW = box(LON0, LAT0, LON1, LAT1)


def xy(lon, lat):
    return ((lon - LON0) * KX * S, (LAT1 - lat) * KY * S)


def to_m(g):
    """Project a shapely geometry to SVG units."""
    from shapely import transform
    import numpy as np

    def f(c):
        return np.column_stack(((c[:, 0] - LON0) * KX * S, (LAT1 - c[:, 1]) * KY * S))
    return transform(g, f)


def path_d(g):
    parts = []
    geoms = getattr(g, "geoms", [g])
    for p in geoms:
        if p.is_empty:
            continue
        if p.geom_type == "Polygon":
            for ring in [p.exterior, *p.interiors]:
                cs = list(ring.coords)
                parts.append("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in cs) + "Z")
        elif p.geom_type == "LineString":
            cs = list(p.coords)
            parts.append("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in cs))
        elif p.geom_type in ("MultiLineString", "MultiPolygon", "GeometryCollection"):
            parts.append(path_d(p))
    return " ".join(parts)


def load(kind):
    return json.load(open(f"{DATA}/{kind}.geojson"))["features"]


def clip(g):
    return to_m(g.intersection(WINDOW.buffer(0.0006)))


# ---------------------------------------------------------------- base layers
svg = []
add = svg.append

parks, pitches, pools, fountains, trees = [], [], [], [], []
for f in load("land_use"):
    g = shape(f["geometry"])
    if not g.intersects(WINDOW):
        continue
    p = f["properties"]
    if p["subtype"] == "park":
        parks.append(clip(g))
    elif p["subtype"] == "recreation":
        pitches.append(clip(g))
for f in load("water"):
    g = shape(f["geometry"])
    if g.intersects(WINDOW) and f["properties"]["class"] == "swimming_pool":
        pools.append(to_m(g))
for f in load("infrastructure"):
    g = shape(f["geometry"])
    if g.intersects(WINDOW) and f["properties"]["class"] == "fountain":
        fountains.append(to_m(g))
for f in load("land"):
    g = shape(f["geometry"])
    if g.intersects(WINDOW) and f["properties"]["class"] == "tree":
        trees.append(to_m(g))

buildings, hotel, home = [], None, None
HOME_PT = Point(-119.70592, 34.43753)  # 1828 Loma St address point (Overture addresses)
for f in load("building"):
    g = shape(f["geometry"])
    if not g.intersects(WINDOW):
        continue
    if g.contains(HOME_PT):
        home = to_m(g)
        continue
    if (f["properties"].get("class") == "hotel"):
        hotel = to_m(g)
        continue
    buildings.append(to_m(g))

ROAD_W = {"primary": 13, "secondary": 12, "tertiary": 11, "residential": 8.5,
          "unclassified": 8, "living_street": 7, "service": 4.6}
roads = {k: [] for k in ROAD_W}
foot, steps = [], []
named = {}
for f in load("segment"):
    p = f["properties"]
    g = shape(f["geometry"])
    if p["subtype"] != "road" or not g.intersects(WINDOW.buffer(0.0008)):
        continue
    c = p["class"]
    gm = to_m(g)
    if c in ROAD_W:
        roads[c].append(gm)
    elif c in ("footway", "path", "pedestrian", "cycleway"):
        foot.append(gm)
    elif c == "steps":
        steps.append(gm)
    name = (p["names"] or {}).get("primary")
    if name and c in ROAD_W:
        named.setdefault(name, []).append(gm)

route = json.load(open(ROUTE))
rfeats = route["features"]
wps = route["waypoints"]
route_m = [to_m(shape(f["geometry"])) for f in rfeats]
route_all = linemerge(unary_union(route_m))

# ---------------------------------------------------------------- palette
C = dict(ground="#EFEBE1", block="#E7E1D3", park="#C9D8B4", park_edge="#A9BF8F",
         bldg="#DCCFBF", bldg_edge="#C9B8A4", road="#FFFFFF", case="#CFC4B2",
         foot="#9C8F7C", steps="#5B4E3E", route="#B7245C", halo="#FFFFFF",
         ink="#2E2A26", water="#9CC7D6", loop="#F2D48A", home="#B7245C", tree="#8FAE78")

add(f'<rect width="{W:.0f}" height="{H:.0f}" fill="{C["ground"]}"/>')

# El Encanto loop tint: the ring the route itself traces around the hotel,
# from where it joins Alvarado Pl back round to the Lasuen Rd / Alvarado Pl corner.
ordered = []
for f in rfeats:
    cs = f["geometry"]["coordinates"]
    ordered.extend(cs if not ordered else cs[1:])
alv = next(f for f in rfeats if f["properties"]["name"] == "Alvarado Place")
i0 = ordered.index(alv["geometry"]["coordinates"][0])
CORNER = [-119.7046891, 34.4384814]  # Lasuen Rd / Alvarado Pl node
i1 = next(i for i in range(i0 + 5, len(ordered)) if ordered[i] == CORNER)
loop_pts = ordered[i0:i1 + 1]
loop_poly = to_m(Polygon(loop_pts)).buffer(0)
add(f'<path d="{path_d(loop_poly)}" fill="{C["loop"]}" fill-opacity=".45"/>')

for g in parks:
    add(f'<path d="{path_d(g)}" fill="{C["park"]}" stroke="{C["park_edge"]}" stroke-width="1.2"/>')
for g in pitches:
    add(f'<path d="{path_d(g)}" fill="#BFD3A6" stroke="#fff" stroke-width="1"/>')

add(f'<g fill="{C["bldg"]}" stroke="{C["bldg_edge"]}" stroke-width=".7">')
for g in buildings:
    add(f'<path d="{path_d(g)}"/>')
add("</g>")
if hotel is not None:
    add(f'<path d="{path_d(hotel)}" fill="#E9B44C" stroke="#A8792A" stroke-width="1"/>')
for g in pools:
    if g.geom_type == "Point":
        add(f'<rect x="{g.x-3:.1f}" y="{g.y-2:.1f}" width="6" height="4" rx="1" fill="{C["water"]}"/>')
    else:
        add(f'<path d="{path_d(g)}" fill="{C["water"]}"/>')
for g in fountains:
    add(f'<path d="{path_d(g)}" fill="{C["water"]}" stroke="#fff" stroke-width="1"/>')
for g in trees:
    add(f'<circle cx="{g.x:.1f}" cy="{g.y:.1f}" r="4.2" fill="{C["tree"]}" fill-opacity=".85"/>')

# Roads: casings then fills, thinnest first so bigger streets sit on top.
order = ["service", "living_street", "unclassified", "residential", "tertiary", "secondary", "primary"]
for k in order:
    if roads[k]:
        d = " ".join(path_d(g) for g in roads[k])
        add(f'<path d="{d}" fill="none" stroke="{C["case"]}" stroke-width="{ROAD_W[k]*S+2.2:.1f}" '
            f'stroke-linecap="round" stroke-linejoin="round"/>')
for k in order:
    if roads[k]:
        d = " ".join(path_d(g) for g in roads[k])
        add(f'<path d="{d}" fill="none" stroke="{C["road"]}" stroke-width="{ROAD_W[k]*S:.1f}" '
            f'stroke-linecap="round" stroke-linejoin="round"/>')
if foot:
    add(f'<path d="{" ".join(path_d(g) for g in foot)}" fill="none" stroke="{C["foot"]}" '
        f'stroke-width="1.3" stroke-dasharray="3 2.2" stroke-linecap="round"/>')
if steps:
    add(f'<path d="{" ".join(path_d(g) for g in steps)}" fill="none" stroke="{C["steps"]}" '
        f'stroke-width="6" stroke-dasharray="1.1 1.5"/>')

# ---------------------------------------------------------------- route
rd = " ".join(path_d(g) for g in route_m)
add(f'<path d="{rd}" fill="none" stroke="{C["halo"]}" stroke-width="10" stroke-linecap="round" '
    f'stroke-linejoin="round" stroke-opacity=".9"/>')
add(f'<path d="{rd}" fill="none" stroke="{C["route"]}" stroke-width="5" stroke-linecap="round" '
    f'stroke-linejoin="round"/>')
# Stair parts of the route: ladder rungs over the line.
sd = " ".join(path_d(to_m(shape(f["geometry"]))) for f in rfeats if f["properties"]["class"] == "steps")
add(f'<path d="{sd}" fill="none" stroke="{C["ink"]}" stroke-width="11" stroke-dasharray="1.3 1.9"/>')

# Direction chevrons along the ordered route, every ~95 m.
line = to_m(LineString(ordered))
step_m = 95 * S
dist = 60 * S
while dist < line.length - 30 * S:
    a = line.interpolate(dist)
    b = line.interpolate(dist + 3)
    ang = math.degrees(math.atan2(b.y - a.y, b.x - a.x))
    add(f'<path d="M-3.4,-3.6 L1.8,0 L-3.4,3.6" fill="none" stroke="#fff" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round" transform="translate({a.x:.1f},{a.y:.1f}) rotate({ang:.1f})"/>')
    dist += step_m

# Home footprint on top of everything but labels.
if home is not None:
    add(f'<path d="{path_d(home)}" fill="{C["home"]}" stroke="#fff" stroke-width="1.6"/>')

# ---------------------------------------------------------------- street labels
LABELS = {
    # name: (display text, route street -> offset label beside the line)
    "Loma Street": ("Loma St", True),
    "Grand Avenue": ("Grand Ave", True),
    "Sierra Street": ("Sierra St", True),
    "Alameda Padre Serra": ("Alameda Padre Serra", True),
    "Lasuen Road": ("Lasuen Rd", True),
    "Alvarado Place": ("Alvarado Pl", True),
    "Mission Ridge Road": ("Mission Ridge Rd", True),
    "San Carlos Road": ("San Carlos Rd", True),
    "Moreno Road": ("Moreno Rd", False),
    "East Pedregosa Street": ("E Pedregosa St", False),
    "Cleveland Avenue": ("Cleveland Ave", False),
    "Via Granada": ("Via Granada", False),
    "Paseo Almeria": ("Paseo Almeria", False),
    "Las Tunas Road": ("Las Tunas Rd", False),
    "Arguello Road": ("Arguello Rd", False),
    "Paterna Road": ("Paterna Rd", False),
    "Mira Vista Avenue": ("Mira Vista Ave", False),
    "El Encanto Road": ("El Encanto Rd", False),
    "Orena Street": ("Orena St", False),
    "Emerson Avenue": ("Emerson Ave", False),
}
# Label anchor hints (lon, lat) so each name sits on a clean stretch.
HINT = {
    "Loma Street": (-119.7051, 34.43700), "Grand Avenue": (-119.7074, 34.43688),
    "Sierra Street": (-119.70765, 34.43745), "Alameda Padre Serra": (-119.70300, 34.43760),
    "Lasuen Road": (-119.70330, 34.43855), "Alvarado Place": (-119.70470, 34.43930),
    "Mission Ridge Road": (-119.70260, 34.44040), "San Carlos Road": (-119.70178, 34.43960),
    "Moreno Road": (-119.70410, 34.43690), "East Pedregosa Street": (-119.70710, 34.43610),
    "Cleveland Avenue": (-119.7078, 34.43635), "Via Granada": (-119.70795, 34.43930),
    "Paseo Almeria": (-119.70705, 34.43960), "Las Tunas Road": (-119.70560, 34.44095),
    "Arguello Road": (-119.70270, 34.43655), "Paterna Road": (-119.70140, 34.43855),
    "Mira Vista Avenue": (-119.70230, 34.43981), "El Encanto Road": (-119.70225, 34.43914),
    "Orena Street": (-119.70830, 34.43735), "Emerson Avenue": (-119.70840, 34.43650),
}
defs, labels = [], []
for i, (name, (text, on_route)) in enumerate(LABELS.items()):
    if name not in named or name not in HINT:
        continue
    u = unary_union(named[name])
    merged = u if u.geom_type == "LineString" else linemerge(u)
    hint = Point(*xy(*HINT[name]))
    lines = list(getattr(merged, "geoms", [merged]))
    ln = min(lines, key=lambda l: l.distance(hint))
    at = ln.project(hint)
    half = max(len(text) * 3.6 + 14, 30)
    a, b = max(0, at - half), min(ln.length, at + half)
    if b - a < 2 * half:  # slide window to fit inside the line
        a, b = max(0, min(a, ln.length - 2 * half)), min(ln.length, max(b, 2 * half))
    from shapely.ops import substring
    seg = substring(ln, a, b).simplify(2.5)
    if on_route:
        off = seg.offset_curve(ROAD_W["residential"] * S / 2 + 7.5)
        if not off.is_empty and off.geom_type == "LineString":
            seg = off
    cs = list(seg.coords)
    if cs[-1][0] < cs[0][0]:
        cs = cs[::-1]
    pid = f"st{i}"
    defs.append(f'<path id="{pid}" d="M' + " L".join(f"{x:.1f},{y:.1f}" for x, y in cs) + '"/>')
    cls = "st on" if on_route else "st"
    labels.append(f'<text class="{cls}"><textPath href="#{pid}" startOffset="50%" '
                  f'text-anchor="middle">{html.escape(text)}</textPath></text>')

# Area labels.
AREA = [("Orpet Park", -119.70470, 34.43755, "area park"),
        ("Riviera Park", -119.70610, 34.43955, "area"),
        ("Belmond El Encanto", -119.70320, 34.43965, "area hotel"),
        ("Riviera Theatre", -119.70700, 34.43905, "area small")]
for text, lon, lat, cls in AREA:
    x, y = xy(lon, lat)
    labels.append(f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}" text-anchor="middle">{text}</text>')

# ---------------------------------------------------------------- stops
# Cumulative distance along the route to each waypoint.
leglen = {}
for f in rfeats:
    leglen[f["properties"]["leg"]] = leglen.get(f["properties"]["leg"], 0) + f["properties"]["length_m"]
cum = [0.0]
for i in range(len(wps) - 1):
    cum.append(cum[-1] + leglen.get(i, 0))
total = cum[-1]

STOPS = [
    # n, map position (lon, lat), label offset (dx, dy in svg units), waypoint index for distance
    (1, tuple(wps[0]["coord"]), (-26, -8), 0),
    (2, (-119.70671, 34.43680), (-24, 4), 1),
    (3, (-119.70741, 34.43791), (-24, 2), 4),
    (4, (-119.70584, 34.43858), (-22, 0), 6),
    (5, (-119.70533, 34.43934), (0, -24), 8),
    (6, (-119.70435, 34.43892), (22, -16), 9),
    (7, (-119.70540, 34.43795), (0, 22), 13),
]
for n, (lon, lat), (dx, dy), _ in STOPS:
    x, y = xy(lon, lat)
    cx, cy = x + dx, y + dy
    if dx or dy:
        labels.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{cx:.1f}" y2="{cy:.1f}" stroke="{C["ink"]}" stroke-width="1.4"/>')
        labels.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="{C["ink"]}"/>')
    labels.append(f'<g class="pin" transform="translate({cx:.1f},{cy:.1f})"><circle r="12.5"/>'
                  f'<text y="4.6" text-anchor="middle">{n}</text></g>')

sx, sy = xy(*wps[0]["coord"])
labels.append(f'<text class="tag" x="{sx-26:.1f}" y="{sy-25:.1f}" text-anchor="middle">START &amp; FINISH</text>')

# Courthouse pointer (excluded stop): bearing from the start toward 1100 Anacapa St.
hx, hy = xy(-119.70592, 34.43753)
cx_, cy_ = xy(-119.7024716, 34.424303)
ang = math.atan2(cy_ - hy, cx_ - hx)
edge_y = H - 26
edge_x = hx + (edge_y - hy) / math.tan(ang)
labels.append(
    f'<g class="offmap" transform="translate({edge_x:.1f},{edge_y:.1f})">'
    f'<path d="M0,-18 L0,8 M-6,2 L0,9 L6,2" fill="none" stroke="{C["ink"]}" stroke-width="1.6" '
    f'stroke-linecap="round" transform="rotate({math.degrees(ang)-90:.1f})"/>'
    f'<text x="12" y="-4">Courthouse 1.2 mi each way</text>'
    f'<text x="12" y="10" class="sub">downhill, not on this loop</text></g>')

# Scale bar (true to the projection) and north arrow.
sb_x, sb_y = 22, H - 30
m100 = 100 * S
ft500 = 500 * 0.3048 * S
labels.append(
    f'<g class="scale" transform="translate({sb_x},{sb_y})">'
    f'<rect x="-8" y="-24" width="{max(m100, ft500)+60:.0f}" height="44" rx="4" fill="{C["ground"]}" fill-opacity=".92"/>'
    f'<path d="M0,0 H{m100:.1f} M0,-5 V0 M{m100:.1f},-5 V0" stroke="{C["ink"]}" stroke-width="1.6" fill="none"/>'
    f'<text x="{m100+6:.1f}" y="-1">100 m</text>'
    f'<path d="M0,6 H{ft500:.1f} M0,11 V6 M{ft500:.1f},11 V6" stroke="{C["ink"]}" stroke-width="1.6" fill="none"/>'
    f'<text x="{ft500+6:.1f}" y="15">500 ft</text></g>')
labels.append(
    f'<g class="north" transform="translate({W-34:.1f},40)"><circle r="19" fill="{C["ground"]}" fill-opacity=".92" '
    f'stroke="{C["ink"]}" stroke-width="1.2"/><path d="M0,-13 L6,8 L0,4 L-6,8Z" fill="{C["ink"]}"/>'
    f'<text y="-23" text-anchor="middle">N</text></g>')

map_svg = (
    f'<svg class="map" viewBox="0 0 {W:.0f} {H:.0f}" role="img" '
    f'aria-label="Map of the Loma Staircase Loop on the Santa Barbara Riviera">'
    f'<defs>{"".join(defs)}</defs>' + "".join(svg) + "".join(labels) + "</svg>"
)

# ---------------------------------------------------------------- page
mi = lambda m: f"{m/1609.34:.2f}"
stop_mi = {n: mi(cum[w]) for n, _, _, w in STOPS}
steps_on_route = sum(f["properties"]["length_m"] for f in rfeats if f["properties"]["class"] == "steps")

import base64
font_css = []
for f in json.load(open(HERE / "fonts" / "fonts.json")):
    b64 = base64.b64encode((HERE / "fonts" / f["file"]).read_bytes()).decode()
    font_css.append(f'@font-face{{font-family:"{f["family"]}";font-style:{f["style"]};'
                    f'font-weight:{f["weight"]};font-display:swap;'
                    f'src:url(data:font/woff2;base64,{b64}) format("woff2");unicode-range:{f["range"]};}}')

tpl = string.Template((HERE / "brochure_template.html").read_text())
page = tpl.substitute(
    MAP=map_svg,
    FONTS="\n".join(font_css),
    TOTAL_MI=mi(total),
    TOTAL_KM=f"{total/1000:.1f}",
    **{f"MI{n}": v for n, v in stop_mi.items()},
    STEPS_FT=f"{steps_on_route/0.3048:.0f}",
)
Path(OUT).write_text(page)
print(f"wrote {OUT}: {len(page)/1024:.0f} KB, route {total:.0f} m, map {W:.0f}x{H:.0f}")

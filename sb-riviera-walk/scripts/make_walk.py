"""Build the GPS walking page (docs/index.html) and GPX/KML route exports.

The page has two base maps that share the GPS logic:
  * painted: the poster's illustrated map, pre-rendered to a JPEG (make_poster.py
    in "base" mode), with the route, stairs, labels and stop pins drawn on top
    as crisp vectors;
  * plain: the detail map from make_map.py.
Both are true-scale, north-up linear projections of the same Overture/OSM
geometry. The route, stops and GPS fixes are kept in lat/lon and projected into
whichever map is showing, so the blue dot lands in the same place on either.

The page is one self-contained file (map image embedded), so once it is open it
needs no network. Requires Node + Playwright for the one-off image render.

usage: python3 make_walk.py DATA_DIR ROUTE_GEOJSON OUT_DIR
"""
import base64
import io
import json
import math
import os
import runpy
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image

DATA, ROUTE, OUT_DIR = sys.argv[1], sys.argv[2], Path(sys.argv[3])
HERE = Path(__file__).resolve().parent


def run_script(name, *args):
    saved = sys.argv
    sys.argv = [name, *args]
    try:
        return runpy.run_path(str(HERE / name), run_name=name.removesuffix(".py"))
    finally:
        sys.argv = saved


with tempfile.TemporaryDirectory() as tmp:
    M = run_script("make_map.py", DATA, ROUTE, f"{tmp}/brochure.html")
    PM = run_script("make_poster.py", DATA, ROUTE, f"{tmp}/base.html", "base")
    # Render the painted base at 2x (3600x3800 px, ~13.7 MP: sharp at street
    # level and still within what older phones decode comfortably).
    env = dict(os.environ)
    if "PLAYWRIGHT_MODULE" not in env:
        root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()
        env["PLAYWRIGHT_MODULE"] = f"{root}/playwright/index.mjs"
    subprocess.run(["node", str(HERE / "screenshot.mjs"), f"{tmp}/base.html", f"{tmp}/base.png", str(PM["W"])],
                   check=True, env=env)
    img = Image.open(f"{tmp}/base.png").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80, optimize=True, progressive=True)
    base_jpg = base64.b64encode(buf.getvalue()).decode()
    print(f"painted base {img.size[0]}x{img.size[1]}, {len(buf.getvalue())/1e6:.1f} MB")

ordered, wps = M["ordered"], M["wps"]

# Route distances in metres (projection-independent within this small area).
KX, KY = M["KX"], M["KY"]
cum = [0.0]
for (lo0, la0), (lo1, la1) in zip(ordered, ordered[1:]):
    cum.append(cum[-1] + math.hypot((lo1 - lo0) * KX, (la1 - la0) * KY))
total = cum[-1]


def at_coord(c, after=0.0):
    for i, oc in enumerate(ordered):
        if cum[i] >= after - 1e-6 and abs(oc[0] - c[0]) < 1e-7 and abs(oc[1] - c[1]) < 1e-7:
            return cum[i]
    raise ValueError(c)


wp_at, last = [], 0.0
for w in wps:
    last = at_coord(w["coord"], last)
    wp_at.append(last)
wp_at[-1] = total
alv = next(f for f in M["rfeats"] if f["properties"]["name"] == "Alvarado Place")
alv_at = at_coord(alv["geometry"]["coordinates"][0], wp_at[9])

STEPS = [
    (wp_at[0], "Walk downhill (south) on Loma St to the hairpin bend."),
    (wp_at[1], "Take the stairs on your right, down two flights to Grand Ave at E Pedregosa St."),
    (wp_at[2], "Turn right on Grand Ave and walk northwest to Sierra St."),
    (wp_at[3], "Turn right up Sierra St to its dead end, then climb the Sierra St stairs."),
    (wp_at[5], "Turn right on Alameda Padre Serra. Bear left onto Lasuen Rd; the Riviera stairway is on your left."),
    (wp_at[6], "Climb the Riviera stairway. At the top go right, then left up the central walk to the garden circle."),
    (wp_at[8], "Go back down the central walk, turn left along the lane, and take the steps down to Alvarado Pl."),
    (alv_at, "Turn left and walk north on Alvarado Pl, with El Encanto on your right."),
    (wp_at[10], "Turn right on Mission Ridge Rd."),
    (wp_at[11], "Turn right on San Carlos Rd, downhill."),
    (wp_at[12], "Turn right on Lasuen Rd and follow it west, past Moreno Rd and Alvarado Pl."),
    (wp_at[13], "Just before the corner, take the Orpet Park path on your left and the short steps down. Cross Alameda Padre Serra."),
    (wp_at[14], "Follow the park path east alongside Alameda Padre Serra, then down beside Moreno Rd."),
    (wp_at[16], "Turn right on Loma St and follow it west and up around the bend back to 1828."),
    (total, "You're back at 1828 Loma St. Loop complete."),
]
# Itinerary (same wording as the poster panel). Stair stops are orange.
ITIN = {
    1: ("1828 Loma St", "Start and finish, below Orpet Park", False),
    2: ("Loma–Pedregosa Stairs", "Two hidden flights down to Grand Ave", True),
    3: ("Sierra St Stairs", "From the dead end up to Alameda Padre Serra", True),
    4: ("Riviera Stairway", "Seven short runs up to Riviera Park", True),
    5: ("Riviera Park Gardens", "Garden circle on the old college campus. Private: skip if posted closed", False),
    6: ("Belmond El Encanto Loop", "Alvarado Pl, Mission Ridge Rd, San Carlos Rd, Lasuen Rd", False),
    7: ("Orpet Park", "Park steps and path back down to Loma St", False),
}
stops = []
for n, ll, _, w in M["STOPS"]:
    name, sub, stair = ITIN[n]
    stops.append({"n": n, "name": name, "sub": sub, "stair": stair, "at": round(wp_at[w], 1),
                  "lon": round(ll[0], 7), "lat": round(ll[1], 7)})


def proj(G):
    return {"lon0": G["LON0"], "lat1": G["LAT1"], "kx": G["KX"], "ky": G["KY"], "s": G["S"], "w": G["W"], "h": G["H"]}


data = {
    "maps": {"paint": proj(PM), "plain": proj(M)},
    "route": [[round(lon, 7), round(lat, 7)] for lon, lat in ordered],
    "cum": [round(c, 1) for c in cum],
    "total": round(total, 1),
    "steps": [{"at": round(a, 1), "text": t} for a, t in STEPS],
    "stops": stops,
}

W, H = PM["W"], PM["H"]
paint_svg = (f'<svg class="map paint" data-map="paint" viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="Illustrated map of the Lower Riviera Staircase Walk">'
             f'<defs>{PM["overlay_defs"]}</defs>'
             f'<image href="data:image/jpeg;base64,{base_jpg}" x="0" y="0" width="{W}" height="{H}" preserveAspectRatio="none"/>'
             f'{PM["overlay"]}</svg>')
plain_svg = M["map_svg"].replace('<svg class="map"', '<svg class="map plain" data-map="plain" hidden', 1)

page = (HERE / "walk_template.html").read_text()
# Plain token replacement: the page's own JavaScript uses ${...} template literals.
for token, value in {"${PAINT_MAP}": paint_svg, "${PLAIN_MAP}": plain_svg,
                     "${DATA}": json.dumps(data, separators=(",", ":"), ensure_ascii=False),
                     "${FONTS}": "\n".join(M["font_css"]), "${TOTAL_MI}": f"{total/1609.34:.2f}"}.items():
    page = page.replace(token, value)
OUT_DIR.mkdir(parents=True, exist_ok=True)
(OUT_DIR / "index.html").write_text(page)

# ---------------------------------------------------------------- GPX / KML
name = "Loma Staircase Loop"
gpx = ['<?xml version="1.0" encoding="UTF-8"?>',
       '<gpx version="1.1" creator="claude-play make_walk.py" xmlns="http://www.topografix.com/GPX/1/1">',
       f'<metadata><name>{name}</name><desc>{total/1609.34:.2f} mi loop from 1828 Loma St, Santa Barbara. '
       'Map data (c) OpenStreetMap contributors, Overture Maps.</desc></metadata>']
for s in stops:
    gpx.append(f'<wpt lat="{s["lat"]:.7f}" lon="{s["lon"]:.7f}"><name>{s["n"]}. {escape(s["name"])}</name></wpt>')
gpx.append(f"<trk><name>{name}</name><trkseg>")
gpx += [f'<trkpt lat="{lat:.7f}" lon="{lon:.7f}"/>' for lon, lat in ordered]
gpx.append("</trkseg></trk></gpx>")
(OUT_DIR / "loma-staircase-loop.gpx").write_text("\n".join(gpx) + "\n")

kml = ['<?xml version="1.0" encoding="UTF-8"?>', '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
       f"<name>{name}</name>",
       '<Style id="route"><LineStyle><color>ffb06c2b</color><width>5</width></LineStyle></Style>']
for s in stops:
    kml.append(f'<Placemark><name>{s["n"]}. {escape(s["name"])}</name><description>{escape(s["sub"])}</description>'
               f'<Point><coordinates>{s["lon"]:.7f},{s["lat"]:.7f},0</coordinates></Point></Placemark>')
kml.append(f'<Placemark><name>{name}</name><styleUrl>#route</styleUrl><LineString><tessellate>1</tessellate><coordinates>'
           + " ".join(f"{lon:.7f},{lat:.7f},0" for lon, lat in ordered) + "</coordinates></LineString></Placemark>")
kml.append("</Document></kml>")
(OUT_DIR / "loma-staircase-loop.kml").write_text("\n".join(kml) + "\n")
print(f"wrote {OUT_DIR}/index.html ({len(page)/1e6:.1f} MB), GPX and KML; route {total:.0f} m")

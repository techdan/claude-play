"""Build the GPS walking page (docs/index.html) and GPX/KML route exports.

Reuses make_map.py for the base map and projection, so the blue dot, the route
and the streets all share one coordinate system. The page is a single file with
no external requests, so it keeps working with a weak signal once loaded.

usage: python3 make_walk.py DATA_DIR ROUTE_GEOJSON OUT_DIR
"""
import html
import json
import math
import runpy
import sys
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

DATA, ROUTE, OUT_DIR = sys.argv[1], sys.argv[2], Path(sys.argv[3])
HERE = Path(__file__).resolve().parent

with tempfile.TemporaryDirectory() as tmp:
    saved = sys.argv
    sys.argv = ["make_map.py", DATA, ROUTE, f"{tmp}/brochure.html"]
    M = runpy.run_path(str(HERE / "make_map.py"), run_name="make_map")
    sys.argv = saved

ordered, wps, S = M["ordered"], M["wps"], M["S"]
KX, KY = M["KX"], M["KY"]

# Route polyline in map units, with cumulative metres at each vertex.
pts = [M["xy"](lon, lat) for lon, lat in ordered]
cum = [0.0]
for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
    cum.append(cum[-1] + math.hypot(x1 - x0, y1 - y0) / S)
total = cum[-1]


def at_coord(c, after=0.0):
    """Route distance (m) of the first vertex equal to c at or after `after` metres."""
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
STOP_NAMES = {1: "1828 Loma St", 2: "Loma–Pedregosa stairs", 3: "Sierra Street stairs",
              4: "Riviera stairway", 5: "Riviera Park gardens", 6: "Belmond El Encanto loop", 7: "Orpet Park"}
stops = []
for n, ll, _, w in M["STOPS"]:
    x, y = M["xy"](*ll)
    stops.append({"n": n, "name": STOP_NAMES[n], "at": round(wp_at[w], 1), "x": round(x, 1), "y": round(y, 1)})

data = {
    "proj": {"lon0": M["LON0"], "lat1": M["LAT1"], "kx": KX, "ky": KY, "s": S, "w": M["W"], "h": M["H"]},
    "route": [[round(x, 1), round(y, 1)] for x, y in pts],
    "cum": [round(c, 1) for c in cum],
    "total": round(total, 1),
    "steps": [{"at": round(a, 1), "text": t} for a, t in STEPS],
    "stops": stops,
}

# Plain token replacement: the page's own JavaScript uses ${...} template literals.
page = (HERE / "walk_template.html").read_text()
for token, value in {"${MAP}": M["map_svg"], "${DATA}": json.dumps(data, separators=(",", ":")),
                     "${FONTS}": "\n".join(M["font_css"]), "${TOTAL_MI}": f"{total/1609.34:.2f}"}.items():
    page = page.replace(token, value)
OUT_DIR.mkdir(parents=True, exist_ok=True)
(OUT_DIR / "index.html").write_text(page)

# ---------------------------------------------------------------- GPX / KML
name = "Loma Staircase Loop"
stop_ll = {n: ll for n, ll, _, _ in M["STOPS"]}
gpx = ['<?xml version="1.0" encoding="UTF-8"?>',
       '<gpx version="1.1" creator="claude-play make_walk.py" xmlns="http://www.topografix.com/GPX/1/1">',
       f'<metadata><name>{name}</name><desc>1.63 mi loop from 1828 Loma St, Santa Barbara. '
       'Map data (c) OpenStreetMap contributors, Overture Maps.</desc></metadata>']
for s in stops:
    lon, lat = stop_ll[s["n"]]
    gpx.append(f'<wpt lat="{lat:.7f}" lon="{lon:.7f}"><name>{s["n"]}. {escape(s["name"])}</name></wpt>')
gpx.append(f"<trk><name>{name}</name><trkseg>")
gpx += [f'<trkpt lat="{lat:.7f}" lon="{lon:.7f}"/>' for lon, lat in ordered]
gpx.append("</trkseg></trk></gpx>")
(OUT_DIR / "loma-staircase-loop.gpx").write_text("\n".join(gpx) + "\n")

kml = ['<?xml version="1.0" encoding="UTF-8"?>', '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
       f"<name>{name}</name>",
       '<Style id="route"><LineStyle><color>ff5c24b7</color><width>5</width></LineStyle></Style>']
for s in stops:
    lon, lat = stop_ll[s["n"]]
    kml.append(f'<Placemark><name>{s["n"]}. {escape(s["name"])}</name>'
               f"<Point><coordinates>{lon:.7f},{lat:.7f},0</coordinates></Point></Placemark>")
kml.append(f'<Placemark><name>{name}</name><styleUrl>#route</styleUrl><LineString><tessellate>1</tessellate><coordinates>'
           + " ".join(f"{lon:.7f},{lat:.7f},0" for lon, lat in ordered) + "</coordinates></LineString></Placemark>")
kml.append("</Document></kml>")
(OUT_DIR / "loma-staircase-loop.kml").write_text("\n".join(kml) + "\n")
print(f"wrote {OUT_DIR}/index.html ({len(page)/1024:.0f} KB), GPX and KML; route {total:.0f} m")

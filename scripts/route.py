"""Route the Loma staircase loop over the Overture/OSM walking network.

Every leg is a shortest path on real segments. Waypoints are existing network
nodes (staircase ends, street junctions) so the line can only follow mapped
streets, footpaths and steps. Nothing is drawn freehand.
"""
import json
import math
import sys

import networkx as nx
from shapely.geometry import shape, LineString

DATA = sys.argv[1] if len(sys.argv) > 1 else "data"
OUT = sys.argv[2] if len(sys.argv) > 2 else "route.geojson"

LAT0 = 34.437
KX = 111320 * math.cos(math.radians(LAT0))  # metres per degree lon
KY = 110950                                  # metres per degree lat

# Relative cost per metre. Streets are preferred over parallel sidewalks so the
# line reads cleanly; driveways and parking aisles are private-ish, so avoid them.
COST = {"footway": 1.0, "path": 1.0, "steps": 1.0, "pedestrian": 1.0,
        "residential": 1.0, "tertiary": 1.0, "secondary": 1.1, "living_street": 1.0,
        "unclassified": 1.0, "service": 1.6}
SUBCLASS_COST = {"sidewalk": 1.25, "driveway": 6.0, "parking_aisle": 2.5, "alley": 2.0}


def key(pt):
    return (round(pt[0], 7), round(pt[1], 7))


def dist(a, b):
    return math.hypot((a[0] - b[0]) * KX, (a[1] - b[1]) * KY)


def build_graph():
    G = nx.Graph()
    for f in json.load(open(f"{DATA}/segment.geojson"))["features"]:
        p = f["properties"]
        if p["subtype"] != "road" or p["class"] not in COST:
            continue
        name = (p["names"] or {}).get("primary")
        factor = SUBCLASS_COST.get(p["subclass"], COST[p["class"]])
        g = shape(f["geometry"])
        for line in getattr(g, "geoms", [g]):
            cs = [key(c) for c in line.coords]
            for a, b in zip(cs, cs[1:]):
                if a == b:
                    continue
                d = dist(a, b)
                G.add_edge(a, b, length=d, cost=d * factor, cls=p["class"],
                           subclass=p["subclass"], name=name)
    return G


def nearest(G, pt, name=None, cls=None, subclass=None):
    best, bd = None, 1e18
    for n in G.nodes:
        if name or cls or subclass:
            ok = any((name is None or e.get("name") == name) and (cls is None or e["cls"] == cls)
                     and (subclass is None or e["subclass"] == subclass)
                     for e in G[n].values())
            if not ok:
                continue
        d = dist(n, pt)
        if d < bd:
            best, bd = n, d
    return best, bd


# Ordered via-points: (label, lon/lat hint, street name or class filter).
# Each hint is snapped to an existing node; the snap distance is reported.
VIA = [
    ("1828 Loma St (start)",             (-119.70592, 34.43753), {"name": "Loma Street"}),
    ("Loma stairs: top",                 (-119.706607, 34.437171), {"cls": "footway"}),
    ("Loma stairs: bottom at Grand Ave", (-119.706756, 34.43658), {"cls": "steps"}),
    ("Grand Ave & Sierra St",            (-119.707836, 34.437232), {"name": "Sierra Street"}),
    ("Sierra stairs: bottom",            (-119.707423, 34.437799), {"cls": "steps"}),
    ("Sierra stairs: top at APS",        (-119.707385, 34.438026), {"cls": "footway"}),
    ("Riviera stairway: bottom",         (-119.70584, 34.43837), {"cls": "steps"}),
    ("Riviera stairway: top",            (-119.70592, 34.43882), {"subclass": "parking_aisle"}),
    ("Riviera Park garden circle",       (-119.70533, 34.43934), {"cls": "footway"}),
    ("Riviera Park lower steps",         (-119.70511, 34.43868), {"cls": "steps"}),
    ("Alvarado Pl & Mission Ridge Rd",   (-119.70471, 34.43990), {"name": "Alvarado Place"}),
    ("Mission Ridge Rd & San Carlos Rd", (-119.70137, 34.44069), {"name": "San Carlos Road"}),
    ("San Carlos Rd & Lasuen Rd",        (-119.70176, 34.43910), {"name": "San Carlos Road"}),
    ("Orpet Park steps: top",            (-119.705721, 34.438210), {"cls": "footway"}),
    ("Orpet Park steps: bottom",         (-119.705720, 34.438138), {"cls": "footway"}),
    ("Orpet Park path along APS",        (-119.70450, 34.43770), {"cls": "footway"}),
    ("Orpet Park path: Loma St end",     (-119.70485, 34.43683), {"cls": "footway"}),
    ("1828 Loma St (finish)",            (-119.70592, 34.43753), {"name": "Loma Street"}),
]


def main():
    G = build_graph()
    nodes = []
    for label, hint, filt in VIA:
        n, d = nearest(G, hint, **filt)
        print(f"  snap {label:36s} -> {n}  ({d:.1f} m)")
        nodes.append(n)

    legs, total = [], 0.0
    for i, (a, b) in enumerate(zip(nodes, nodes[1:])):
        path = nx.shortest_path(G, a, b, weight="cost")
        for u, v in zip(path, path[1:]):
            e = G[u][v]
            legs.append({"leg": i, "a": u, "b": v, **{k: e[k] for k in ("cls", "subclass", "name", "length")}})
            total += e["length"]

    # Merge consecutive edges with the same leg/class/name into features.
    feats, cur = [], None
    for e in legs:
        k = (e["leg"], e["cls"], e["name"])
        if cur and cur["k"] == k and cur["coords"][-1] == e["a"]:
            cur["coords"].append(e["b"]); cur["length"] += e["length"]
        else:
            cur = {"k": k, "coords": [e["a"], e["b"]], "length": e["length"]}
            feats.append(cur)
    out = {"type": "FeatureCollection", "properties": {"length_m": round(total)},
           "features": [{"type": "Feature",
                         "properties": {"leg": c["k"][0], "class": c["k"][1], "name": c["k"][2],
                                        "length_m": round(c["length"], 1)},
                         "geometry": {"type": "LineString", "coordinates": c["coords"]}}
                        for c in feats],
           "waypoints": [{"label": l, "coord": n} for (l, _, _), n in zip(VIA, nodes)]}
    json.dump(out, open(OUT, "w"), indent=1)

    print(f"\nTotal: {total:.0f} m ({total/1609.34:.2f} mi)")
    last = None
    for c in feats:
        tag = (c["k"][2] or c["k"][1])
        if tag != last:
            print(f"  leg {c['k'][0]:2d} {tag:28s} {c['length']:6.0f} m")
        last = tag


if __name__ == "__main__":
    main()

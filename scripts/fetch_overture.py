"""Download Overture Maps features for the Lower Riviera walk area.

Overture's transportation, buildings, places and base themes are derived from
OpenStreetMap (plus other open sources). We read the public GeoParquet release
straight from S3 and keep only rows whose bbox intersects the study area.
"""
import os
import sys
import json

import pyarrow.dataset as ds
import pyarrow.compute as pc
import pyarrow.fs as fs
import shapely

RELEASE = "2026-09-23.0"
BBOX = (-119.720, 34.415, -119.675, 34.450)  # xmin, ymin, xmax, ymax
OUT = sys.argv[1] if len(sys.argv) > 1 else "data"

TYPES = {
    "segment": ("transportation", ["id", "subtype", "class", "subclass", "names", "geometry"]),
    "address": ("addresses", ["id", "number", "street", "unit", "postcode", "geometry"]),
    "place": ("places", ["id", "names", "categories", "confidence", "geometry"]),
    "building": ("buildings", ["id", "names", "class", "height", "geometry"]),
    "land_use": ("base", ["id", "subtype", "class", "names", "geometry"]),
    "water": ("base", ["id", "subtype", "class", "names", "geometry"]),
    "land": ("base", ["id", "subtype", "class", "names", "geometry"]),
    "infrastructure": ("base", ["id", "subtype", "class", "names", "geometry"]),
}


def fetch(kind):
    theme, cols = TYPES[kind]
    s3 = fs.S3FileSystem(anonymous=True, region="us-west-2",
                         proxy_options=os.environ.get("HTTPS_PROXY"))
    path = f"overturemaps-us-west-2/release/{RELEASE}/theme={theme}/type={kind}/"
    dataset = ds.dataset(path, filesystem=s3, format="parquet")
    xmin, ymin, xmax, ymax = BBOX
    flt = ((pc.field("bbox", "xmin") < xmax) & (pc.field("bbox", "xmax") > xmin)
           & (pc.field("bbox", "ymin") < ymax) & (pc.field("bbox", "ymax") > ymin))
    names = set(dataset.schema.names)
    table = dataset.to_table(columns=[c for c in cols if c in names], filter=flt)
    feats = []
    for row in table.to_pylist():
        geom = shapely.from_wkb(row.pop("geometry"))
        feats.append({"type": "Feature", "properties": row,
                      "geometry": shapely.geometry.mapping(geom)})
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, f"{kind}.geojson"), "w") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f, default=str)
    print(kind, len(feats), flush=True)


if __name__ == "__main__":
    for kind in (sys.argv[2:] or TYPES):
        fetch(kind)

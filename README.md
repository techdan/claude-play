# Loma Staircase Loop

A 1.63 mi (2.6 km) walking loop from 1828 Loma St, Santa Barbara, over five public
stairways, the Riviera Park gardens, the streets around Belmond El Encanto, and Orpet Park.

- `docs/loma-staircase-loop.html`: the brochure page (self-contained, inline SVG map)
- `docs/loma-staircase-loop.png`: the same page as an image
- `data/route.geojson`: the walking line, stop waypoints and per-leg distances

## How the map is kept accurate

Nothing on the map is drawn by hand. Streets, footpaths, steps, buildings and parks come
from the Overture Maps release `2026-09-23.0`, which is built from OpenStreetMap. The
route is a shortest path over that same network between fixed waypoints (staircase ends
and street corners), so it can only follow mapped streets, footways and steps.

## Rebuild

```sh
pip install pyarrow shapely networkx
AWS_CA_BUNDLE=... python3 scripts/fetch_overture.py data/overture   # ~16 MB, not committed
python3 scripts/route.py data/overture data/route.geojson
python3 scripts/make_map.py data/overture data/route.geojson docs/loma-staircase-loop.html
node scripts/screenshot.mjs docs/loma-staircase-loop.html docs/loma-staircase-loop.png 1400
```

Map data © OpenStreetMap contributors, Overture Maps Foundation. Fonts: Alegreya SC and
Alegreya Sans (SIL Open Font License).

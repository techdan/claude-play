# Loma Staircase Loop

Live: https://techdan.github.io/claude-play/sb-riviera-walk/ (GPS walking page)

A 1.63 mi (2.6 km) walking loop from 1828 Loma St, Santa Barbara, over five public
stairways, the Riviera Park gardens, the streets around Belmond El Encanto, and Orpet Park.

- `index.html`: phone walking page on the painted poster map (switchable to the plain
  map) with a live GPS blue dot, route progress, itinerary and turn-by-turn steps. One
  self-contained file; needs https hosting for GPS, e.g. GitHub Pages
- `loma-staircase-loop.gpx` / `.kml`: the route for Google My Maps or any GPS app
- `loma-staircase-loop.html`: the brochure page (self-contained, inline SVG map)
- `loma-staircase-loop.png`: the same page as an image
- `lower-riviera-staircase-walk.jpg` (1800×1900) and `-print.jpg` (3600×3800): the illustrated poster
- `lower-riviera-staircase-walk.html`: the poster as vector SVG
- `data/route.geojson`: the walking line, stop waypoints and per-leg distances

## How the map is kept accurate

Nothing on the map is drawn by hand. Streets, footpaths, steps, buildings and parks come
from the Overture Maps release `2026-09-23.0`, which is built from OpenStreetMap. The
route is a shortest path over that same network between fixed waypoints (staircase ends
and street corners), so it can only follow mapped streets, footways and steps.

The poster adds decoration on top (paper texture, roof colours, tree canopy placed only
where no street, path or building is mapped, mountains along the north edge, and drawn
stop pictures). None of it moves a street, stair or the route.

## Rebuild

Run from this folder (`sb-riviera-walk/`):

```sh
pip install pyarrow shapely networkx
AWS_CA_BUNDLE=... python3 scripts/fetch_overture.py data/overture   # ~16 MB, git-ignored
python3 scripts/route.py data/overture data/route.geojson
python3 scripts/make_map.py data/overture data/route.geojson loma-staircase-loop.html
node scripts/screenshot.mjs loma-staircase-loop.html loma-staircase-loop.png 1400
python3 scripts/make_walk.py data/overture data/route.geojson .   # renders the painted base with Playwright
python3 scripts/make_poster.py data/overture data/route.geojson lower-riviera-staircase-walk.html
node scripts/screenshot.mjs lower-riviera-staircase-walk.html poster.png 1800
```

Map data © OpenStreetMap contributors, Overture Maps Foundation. Fonts: Alegreya SC and
Alegreya Sans (SIL Open Font License).

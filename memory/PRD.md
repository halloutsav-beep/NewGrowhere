# GROWhere — PRD

## Original problem statement
GROWhere is a satellite-guided reforestation tool. Users drop a pin, the app reads land suitability, and recommends native species for community planting.

## Core requirements (current state)
1. Deterministic climate zone detection (Köppen-style) from lat/lng — no LLM inference.
2. Species diversity: 15 native species per pin (6 trees / 5 shrubs / 4 ground cover), weighted randomisation per grid cell.
3. Polygon-based land classification via Overpass/OSM — flags rivers, lakes, roads, buildings.
4. Marker precision: non-plantable pins refuse species recommendations with an explicit reason.
5. Full determinism: same lat/lng ⇒ same response, always (grid-snapped caching).
6. Static fallback when Overpass/GBIF fail.

## Architecture
```
/app/backend/
  server.py              # FastAPI routes
  climate_zones.py       # Köppen classifier (NEW)
  land_classifier.py     # Overpass polygon checker (NEW)
  regional_species.py    # Curated DB, now with categories
  gbif_lookup.py         # GBIF + category inference
  tests/test_climate_species.py   # pytest suite
/app/frontend/src/
  pages/MapDashboard.jsx # Categorised species UI + non-plantable banner
  pages/Landing.jsx      # WhatsApp CTA (community URL wired)
```

## Implemented (Feb 2026 iteration)
- Deterministic Köppen classifier with ~40 regional overrides (Sahara, Thar, Indian monsoon belt, Mediterranean, SE-Asia rainforest, etc.).
- Overpass-backed polygon land classifier (cache-by-grid, UA header, 2-endpoint failover, shapely point-in-polygon + line-proximity). Footways/paths/tracks exempted from road blocking so park edges remain plantable.
- Species DB expanded: every bioregion now has trees + shrubs + ground cover entries; new `pick_species_categorised()` returns 6/5/4 buckets deterministically.
- GBIF results auto-categorised via family + genus heuristics (`_categorise`).
- LLM prompt overhauled to demand `species_by_category` output; server robustly parses both categorised and flat LLM responses.
- Non-plantable pins (river / road / building) short-circuit with `plantable=false`, empty species, and a user-facing reason.
- Frontend: categorised species rendering (Trees / Shrubs / Ground cover sections), non-plantable warning banner, disabled CTA on blocked pins, Köppen-code badge.
- WhatsApp community URL wired: `https://chat.whatsapp.com/GbNE9LQ7yRQL0X0rRZHUIX`.

## Backlog (P1)
- Replace WhatsApp direct-chat placeholder link with real client number.
- Swap heuristic climate boxes for WWF TEOW shapefile if higher precision is needed.
- Persist `_SPECIES_CACHE` to MongoDB for determinism across process restarts.

## Testing
- Backend: 13/13 pass in `/app/backend/tests/test_climate_species.py` (iter 5).
- Frontend: smoke screenshot OK; full categorised flow verified visually pending user acceptance.

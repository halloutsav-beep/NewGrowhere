"""
Polygon-based land classifier.

Given a (lat, lng), determine whether the point falls on something it is
physically / legally unsafe to plant on — rivers, lakes, roads, buildings,
dense urban tarmac — by querying the Overpass (OSM) API and running precise
point-in-polygon (and point-near-line) checks with Shapely.

Design priorities:
1. Deterministic per ~1.1 km grid cell — results are cached by grid key so
   the SAME coordinate always returns the SAME classification.
2. Non-destructive — returns a structured dict; callers decide how to use it.
3. Graceful fallback — if Overpass is unreachable or slow, return a neutral
   "unknown" result and let the caller keep using the existing heuristics.

Classifications returned by ``classify_point``::

    {
      "plantable": bool,               # False if inside water / on road / on building
      "reason":   str | None,          # e.g. "River", "Lake", "Road", "Building"
      "feature":  str | None,          # OSM tag that matched, e.g. "waterway=river"
      "source":   "overpass" | "fallback" | "cache",
    }
"""

from __future__ import annotations

import logging
import math
from typing import Optional, Dict, Any

import httpx

try:
    from shapely.geometry import Point, Polygon, LineString
    _HAS_SHAPELY = True
except Exception:  # pragma: no cover - shapely is installed in requirements
    _HAS_SHAPELY = False

log = logging.getLogger(__name__)

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Metres per degree latitude is ~111_320; we convert road "nearness"
# thresholds with this constant.
_M_PER_DEG_LAT = 111_320.0

# Classification cache keyed by grid cell. Keeps responses deterministic and
# avoids hammering Overpass on every click.
_CACHE: Dict[tuple, Dict[str, Any]] = {}
_CACHE_MAX = 1000
_GRID_STEP = 0.001  # ~110 m grid — finer than the zone grid so we distinguish
                    # a pin on a road from a pin 50 m off the road.


def _grid_key(lat: float, lng: float) -> tuple:
    return (round(lat / _GRID_STEP) * _GRID_STEP,
            round(lng / _GRID_STEP) * _GRID_STEP)


def _cache_set(key: tuple, val: dict) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[key] = val


def _bbox(lat: float, lng: float, radius_m: float = 200.0):
    """Tight bbox around the point for the Overpass query."""
    dlat = radius_m / _M_PER_DEG_LAT
    dlng = radius_m / (_M_PER_DEG_LAT * max(math.cos(math.radians(lat)), 0.01))
    return (lat - dlat, lng - dlng, lat + dlat, lng + dlng)


def _overpass_query(lat: float, lng: float, radius_m: float = 200.0) -> str:
    s, w, n, e = _bbox(lat, lng, radius_m)
    bbox = f"{s},{w},{n},{e}"
    # Keep the query tight: only the feature types we actually classify on.
    return f"""
[out:json][timeout:6];
(
  way["waterway"]({bbox});
  way["natural"="water"]({bbox});
  relation["natural"="water"]({bbox});
  way["water"]({bbox});
  way["highway"]({bbox});
  way["building"]({bbox});
  way["landuse"="residential"]({bbox});
  way["landuse"="industrial"]({bbox});
  way["landuse"="commercial"]({bbox});
);
out geom 200;
""".strip()


async def _fetch_overpass(lat: float, lng: float, timeout: float = 7.0) -> Optional[dict]:
    """Try the primary and mirror endpoints. Return parsed JSON or None."""
    q = _overpass_query(lat, lng)
    headers = {
        # Overpass mirrors 406 requests without a UA.
        "User-Agent": "GROWhere/1.0 (+https://growhere.app) land-plantability-check",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        for url in OVERPASS_ENDPOINTS:
            try:
                r = await client.post(url, data={"data": q})
                if r.status_code == 200:
                    return r.json()
                log.warning("Overpass %s non-200: %s (%s)", url, r.status_code, r.text[:120])
            except Exception as e:
                log.warning("Overpass %s failed: %s", url, e)
    return None


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _coords(geom_list) -> list:
    """Overpass returns {lat, lon}; convert to (lng, lat) tuples for shapely."""
    return [(g["lon"], g["lat"]) for g in geom_list if "lat" in g and "lon" in g]


def _point_in_polygon(pt, elements) -> Optional[dict]:
    """Check water / building / residential POLYGON features for containment."""
    for el in elements:
        tags = el.get("tags") or {}
        geom = el.get("geometry") or []
        if len(geom) < 3:
            continue
        if "waterway" in tags and tags.get("waterway") != "riverbank":
            # waterway=river/stream/canal are LINES, handled separately.
            continue
        # Polygon candidates: natural=water, water=*, building, landuse=...
        is_water_poly = (tags.get("natural") == "water" or "water" in tags)
        is_building = "building" in tags
        is_urban = tags.get("landuse") in {"residential", "industrial", "commercial"}
        if not (is_water_poly or is_building or is_urban):
            continue
        try:
            coords = _coords(geom)
            if len(coords) < 3:
                continue
            poly = Polygon(coords)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.contains(pt) or poly.touches(pt):
                if is_water_poly:
                    label = (tags.get("water") or tags.get("natural") or "water").title()
                    return {"plantable": False, "reason": f"Water body ({label})",
                            "feature": f"natural=water/{tags.get('water','')}".rstrip("/")}
                if is_building:
                    return {"plantable": False, "reason": "Built-up structure",
                            "feature": f"building={tags.get('building', 'yes')}"}
                if is_urban:
                    # Urban zoning is not automatically un-plantable — we only
                    # flag it as a caveat, not a hard block.
                    return {"plantable": True, "reason": None,
                            "feature": f"landuse={tags.get('landuse')}",
                            "urban": True}
        except Exception as e:  # noqa: BLE001
            log.debug("polygon check failed: %s", e)
            continue
    return None


def _point_near_line(pt, elements, lat: float) -> Optional[dict]:
    """Flag pins that land on a road or inside a mapped river/stream line.

    Uses a small buffer because OSM ways are centerlines, not footprints."""
    # Convert metre thresholds to degrees at this latitude.
    road_buffer_m = 6.0        # ~ one car lane width
    water_buffer_m = 3.0
    m_per_deg_lng = _M_PER_DEG_LAT * max(math.cos(math.radians(lat)), 0.01)
    road_thresh = road_buffer_m / ((_M_PER_DEG_LAT + m_per_deg_lng) / 2)
    water_thresh = water_buffer_m / ((_M_PER_DEG_LAT + m_per_deg_lng) / 2)

    best = None  # closest hit overall
    for el in elements:
        tags = el.get("tags") or {}
        geom = el.get("geometry") or []
        if len(geom) < 2:
            continue

        if "highway" in tags:
            label_type = tags.get("highway", "road")
            # Footpaths, tracks and bridleways inside parks are not "roads"
            # for planting purposes — skip them to avoid false-positive blocks.
            if label_type in {"footway", "path", "track", "bridleway",
                              "steps", "pedestrian", "cycleway"}:
                continue
            thresh = road_thresh
            reason = f"Road ({label_type})"
            feature = f"highway={label_type}"
        elif tags.get("waterway") in {"river", "stream", "canal", "drain"}:
            thresh = water_thresh
            label_type = tags["waterway"].title()
            reason = label_type
            feature = f"waterway={tags['waterway']}"
        else:
            continue

        try:
            coords = _coords(geom)
            if len(coords) < 2:
                continue
            line = LineString(coords)
            d = line.distance(pt)
            if d <= thresh:
                if best is None or d < best[0]:
                    best = (d, {"plantable": False, "reason": reason,
                                "feature": feature})
        except Exception as e:  # noqa: BLE001
            log.debug("line check failed: %s", e)
            continue

    return best[1] if best else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_UNKNOWN = {"plantable": True, "reason": None, "feature": None, "source": "fallback"}


async def classify_point(lat: float, lng: float) -> Dict[str, Any]:
    """Classify whether this point is safely plantable (not water/road/building).

    Cached by ~110 m grid — same coord ⇒ same answer. Never raises: on any
    failure it returns a neutral "plantable=True, source=fallback" result so
    the caller can keep serving recommendations.
    """
    key = _grid_key(lat, lng)
    cached = _CACHE.get(key)
    if cached is not None:
        return {**cached, "source": "cache"}

    if not _HAS_SHAPELY:
        return {**_UNKNOWN}

    payload = await _fetch_overpass(lat, lng)
    if payload is None:
        # Store the fallback too — prevents retrying a dead endpoint every click.
        _cache_set(key, _UNKNOWN)
        return {**_UNKNOWN}

    elements = payload.get("elements") or []
    pt = Point(lng, lat)

    # 1) Inside a water polygon / building footprint?
    hit = _point_in_polygon(pt, elements)
    if hit and not hit.get("plantable", True):
        result = {"plantable": False, "reason": hit["reason"],
                  "feature": hit["feature"], "source": "overpass",
                  "urban": False}
        _cache_set(key, result)
        return result

    urban_flag = bool(hit and hit.get("urban"))

    # 2) On a road or river/stream line?
    hit2 = _point_near_line(pt, elements, lat)
    if hit2:
        result = {"plantable": False, "reason": hit2["reason"],
                  "feature": hit2["feature"], "source": "overpass",
                  "urban": urban_flag}
        _cache_set(key, result)
        return result

    result = {"plantable": True, "reason": None, "feature": None,
              "source": "overpass", "urban": urban_flag}
    _cache_set(key, result)
    return result

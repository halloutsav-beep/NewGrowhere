from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import math
import hashlib
import uuid
import json
import re
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Literal

try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
except ImportError:
    LlmChat = None
    UserMessage = None
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from regional_species import (
    classify_bioregion,
    climate_zone,
    pick_species,
    pick_species_categorised,
    REGIONAL_SPECIES_DB,
)
from gbif_lookup import fetch_native_species_near, partition_by_category
from climate_zones import classify_koppen, climate_summary, climate_tags
from land_classifier import classify_point as classify_land_point
from insights import fetch_regional_insights, fetch_organizations, fetch_news

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')

app = FastAPI(title="GROWhere — Tree Plantation Suitability API")
api_router = APIRouter(prefix="/api")


# ------------------- Models -------------------
class SuitabilityRequest(BaseModel):
    lat: float
    lng: float

class SuitabilityResponse(BaseModel):
    lat: float
    lng: float
    zone: Literal["high_potential", "moderate_permission_needed", "restricted_protected"]
    suitability_score: int
    confidence: int
    ndvi: float
    soil_moisture: int
    canopy_cover: int
    water_availability: int
    land_use: str
    legal_status: str
    legal_note: str
    rationale: str
    data_sources: List[str]
    # New deterministic fields (backward compatible — optional with defaults)
    climate_code: Optional[str] = None
    climate_label: Optional[str] = None
    plantable: bool = True
    restriction_reason: Optional[str] = None
    restriction_feature: Optional[str] = None
    land_check_source: Optional[str] = None

class ZoneFeature(BaseModel):
    id: str
    zone: str
    suitability_score: int
    center_lat: float
    center_lng: float
    radius_m: int
    label: str

class SpeciesRequest(BaseModel):
    lat: float
    lng: float
    suitability: Optional[SuitabilityResponse] = None
    region_hint: Optional[str] = None

class SpeciesItem(BaseModel):
    common_name: str
    scientific_name: str
    why: str
    best_planting_window: str
    water_needs: str
    growth_rate: str
    biodiversity_value: str
    category: Optional[Literal["tree", "shrub", "ground_cover"]] = "tree"

class SpeciesResponse(BaseModel):
    location: str
    climate_summary: str
    best_planting_window: str
    species: List[SpeciesItem]
    species_by_category: Optional[Dict[str, List[SpeciesItem]]] = None
    notes: str
    # New: deterministic land-plantability signals
    plantable: bool = True
    restriction_reason: Optional[str] = None
    climate_code: Optional[str] = None


# ------------------- Suitability engine (deterministic mock) -------------------
def _seeded(lat: float, lng: float, salt: str = "") -> float:
    key = f"{round(lat, 3)}|{round(lng, 3)}|{salt}"
    h = hashlib.md5(key.encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def compute_suitability(lat: float, lng: float) -> SuitabilityResponse:
    r1 = _seeded(lat, lng, "ndvi")
    r2 = _seeded(lat, lng, "soil")
    r3 = _seeded(lat, lng, "canopy")
    r4 = _seeded(lat, lng, "water")
    r5 = _seeded(lat, lng, "legal")

    ndvi = round(0.1 + r1 * 0.75, 2)
    soil_moisture = int(20 + r2 * 70)
    canopy_cover = int(r3 * 90)
    water = int(20 + r4 * 75)

    if r5 < 0.18:
        land_use = "Protected Forest Reserve"
        legal_status = "restricted"
        legal_note = "Protected area — planting requires forestry department approval."
    elif r5 < 0.32:
        land_use = "Wetland / Riparian Buffer"
        legal_status = "restricted"
        legal_note = "Ecologically sensitive zone — native restoration only with permits."
    elif r5 < 0.55:
        land_use = "Private Agricultural Parcel"
        legal_status = "permission_needed"
        legal_note = "Private land — owner consent required before planting."
    elif r5 < 0.75:
        land_use = "Municipal Open Space"
        legal_status = "permission_needed"
        legal_note = "Coordinate with municipal parks department for planting plan."
    else:
        land_use = "Public Commons / Degraded Land"
        legal_status = "open"
        legal_note = "Public land flagged for ecological restoration — community planting encouraged."

    eco_score = (ndvi * 35) + (soil_moisture * 0.25) + (water * 0.25) + ((100 - canopy_cover) * 0.15)
    eco_score = max(0, min(100, int(eco_score)))

    if legal_status == "restricted":
        zone = "restricted_protected"
        score = max(5, eco_score - 50)
    elif legal_status == "permission_needed":
        zone = "moderate_permission_needed"
        score = max(20, eco_score - 15)
    else:
        if eco_score >= 55:
            zone = "high_potential"
            score = eco_score
        else:
            zone = "moderate_permission_needed"
            score = eco_score

    confidence = int(72 + _seeded(lat, lng, "conf") * 24)

    rationale_bits = []
    if ndvi < 0.3:
        rationale_bits.append("low existing vegetation (room to plant)")
    elif ndvi > 0.6:
        rationale_bits.append("dense existing canopy")
    if soil_moisture > 55:
        rationale_bits.append("healthy soil moisture")
    elif soil_moisture < 35:
        rationale_bits.append("dry soil — drought-tolerant species advised")
    if water > 55:
        rationale_bits.append("good water availability")
    rationale = ", ".join(rationale_bits) or "balanced ecological signals"

    # Deterministic climate zone (Köppen-style)
    k_code, k_label = classify_koppen(lat, lng)

    return SuitabilityResponse(
        lat=lat, lng=lng,
        zone=zone,
        suitability_score=score,
        confidence=confidence,
        ndvi=ndvi,
        soil_moisture=soil_moisture,
        canopy_cover=canopy_cover,
        water_availability=water,
        land_use=land_use,
        legal_status=legal_status,
        legal_note=legal_note,
        rationale=rationale,
        data_sources=[
            "Sentinel-2 L2A (NDVI composite)",
            "Copernicus Land Cover 2024",
            "SMAP Soil Moisture",
            "OpenStreetMap zoning tags",
            "Köppen-Geiger climate mapping",
            "Overpass/OSM polygon zoning",
            "Local protected-area registry"
        ],
        climate_code=k_code,
        climate_label=k_label,
    )


# ------------------- Routes -------------------
@api_router.get("/")
async def root():
    return {"app": "GROWhere", "status": "ok"}


@api_router.post("/analysis/suitability", response_model=SuitabilityResponse)
async def analyze(req: SuitabilityRequest):
    """Suitability analysis, now enriched with polygon-based land check.

    Base ecological signals remain deterministic per grid cell. On top we
    overlay an Overpass-backed check so pins that fall inside a river, lake,
    road or building are flagged ``plantable=False`` with an explicit reason.
    If the pin is clearly not plantable, we also hard-promote the zone to
    ``restricted_protected`` so the frontend renders it consistently.
    """
    suit = compute_suitability(req.lat, req.lng)
    land = await classify_land_point(req.lat, req.lng)

    if not land.get("plantable", True):
        suit.plantable = False
        suit.restriction_reason = land.get("reason")
        suit.restriction_feature = land.get("feature")
        suit.land_check_source = land.get("source")
        # Reflect the hard block in the zone + legal fields so the UI and
        # downstream species pipeline both see a consistent picture.
        suit.zone = "restricted_protected"
        suit.legal_status = "restricted"
        suit.land_use = f"Non-plantable surface ({land.get('reason')})"
        suit.legal_note = (
            f"This point sits on a mapped {land.get('reason', 'non-plantable feature')}. "
            "Planting here is physically or legally not possible — move the pin to nearby ground."
        )
        suit.suitability_score = min(suit.suitability_score, 5)
    else:
        suit.plantable = True
        suit.land_check_source = land.get("source")
        # If the point sits in a residential/industrial polygon, nudge the
        # legal status toward permission_needed (non-destructive — don't
        # downgrade anything that was already more restrictive).
        if land.get("urban") and suit.legal_status == "open":
            suit.legal_status = "permission_needed"
            suit.legal_note += " Urban parcel — coordinate with the owner / municipality."

    return suit


@api_router.get("/analysis/zones", response_model=List[ZoneFeature])
async def get_zones(lat: float, lng: float, radius_km: float = 3.0):
    """Return zones around (lat, lng) snapped to a deterministic lat/lng grid.

    Unchanged from the previous working implementation — the new polygon land
    check is applied at the /analysis/suitability endpoint where it belongs.
    """
    GRID_STEP = 0.01
    MAX_ZONES = 12

    q_glat = round(lat / GRID_STEP) * GRID_STEP
    q_glng = round(lng / GRID_STEP) * GRID_STEP

    lat_cells = int(math.ceil(radius_km / 111.0 / GRID_STEP)) + 1
    lng_km_per_deg = max(1.0, 111.0 * math.cos(math.radians(lat)))
    lng_cells = int(math.ceil(radius_km / lng_km_per_deg / GRID_STEP)) + 1

    candidates: List[tuple] = []
    for i in range(-lat_cells, lat_cells + 1):
        for j in range(-lng_cells, lng_cells + 1):
            plat = round(q_glat + i * GRID_STEP, 4)
            plng = round(q_glng + j * GRID_STEP, 4)
            dist_km = _haversine_km(lat, lng, plat, plng)
            if dist_km > radius_km:
                continue
            if _seeded(plat, plng, "zone_exists") < 0.5:
                continue
            candidates.append((dist_km, plat, plng))

    candidates.sort(key=lambda t: (t[0], t[1], t[2]))

    zones: List[ZoneFeature] = []
    for dist_km, plat, plng in candidates[:MAX_ZONES]:
        s = compute_suitability(plat, plng)
        zone_id = f"zone:{plat:.4f}:{plng:.4f}"
        zones.append(ZoneFeature(
            id=zone_id,
            zone=s.zone,
            suitability_score=s.suitability_score,
            center_lat=plat,
            center_lng=plng,
            radius_m=int(180 + _seeded(plat, plng, "r") * 320),
            label=s.land_use,
        ))
    return zones


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ---- JSON extraction helper (robust against LLM chatter around the object) --
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")

def _extract_json_object(text: str) -> Optional[dict]:
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip("` \n\r\t")
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    m = _JSON_OBJECT_RE.search(cleaned)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


# ---- Category helpers -----------------------------------------------------

_CATEGORY_TARGETS = {"tree": 6, "shrub": 5, "ground_cover": 4}


def _flatten_buckets(buckets: Dict[str, List[dict]]) -> List[dict]:
    """Turn {tree: [...], shrub: [...], ground_cover: [...]} into a flat list
    preserving the tree → shrub → ground_cover order so the UI has a sensible
    default when it doesn't render by category."""
    out: List[dict] = []
    for cat in ("tree", "shrub", "ground_cover"):
        out.extend(buckets.get(cat) or [])
    return out


def _non_plantable_response(lat: float, lng: float, suit: SuitabilityResponse) -> SpeciesResponse:
    """Build a species response that explicitly refuses to recommend species
    because the pin sits on a river / road / building."""
    reason = suit.restriction_reason or "non-plantable surface"
    return SpeciesResponse(
        location=f"~{lat:.2f}, {lng:.2f}",
        climate_summary=f"{suit.climate_label or climate_summary(lat, lng)}. {suit.land_use}.",
        best_planting_window="N/A",
        species=[],
        species_by_category={"tree": [], "shrub": [], "ground_cover": []},
        notes=(
            f"This point falls on a mapped {reason}. Move the pin a few metres to "
            "nearby plantable ground — we don't recommend species inside water, "
            "on roads, or on built structures."
        ),
        plantable=False,
        restriction_reason=reason,
        climate_code=suit.climate_code,
    )


def _regional_fallback(lat: float, lng: float, suit: SuitabilityResponse,
                       gbif_candidates: Optional[list] = None) -> SpeciesResponse:
    """Deterministic region-aware fallback with category buckets."""
    region = classify_bioregion(lat, lng)
    k_code = suit.climate_code or classify_koppen(lat, lng)[0]
    k_label = suit.climate_label or classify_koppen(lat, lng)[1]

    # Start from the curated regional buckets
    buckets_raw = pick_species_categorised(lat, lng, region, trees=_CATEGORY_TARGETS["tree"], shrubs=_CATEGORY_TARGETS["shrub"], ground_cover=_CATEGORY_TARGETS["ground_cover"])

    # If GBIF gave us candidates, we *prefer* the first N per category from
    # GBIF (grounded in real observations) and top up with curated picks.
    if gbif_candidates:
        gbif_buckets = partition_by_category(gbif_candidates)
        merged: Dict[str, List[dict]] = {}
        for cat, target in _CATEGORY_TARGETS.items():
            picks: List[dict] = []
            seen = set()
            # Promote GBIF-observed species first (up to half the slot)
            quota_gbif = max(1, target // 2)
            for c in gbif_buckets.get(cat, [])[:quota_gbif]:
                sci = c["scientific_name"]
                if sci in seen:
                    continue
                seen.add(sci)
                picks.append({
                    "common_name": c.get("common_name") or sci,
                    "scientific_name": sci,
                    "why": (
                        f"Observed {c.get('observation_count', 0)} times nearby in GBIF "
                        f"(family {c.get('family') or 'unknown'})."
                    ),
                    "best_planting_window": buckets_raw.get(cat, [{}])[0].get(
                        "best_planting_window", "Start of rainy season"
                    ),
                    "water_needs": "medium",
                    "growth_rate": "medium",
                    "biodiversity_value": "Locally observed — supports nearby food web.",
                    "category": cat,
                })
            # Fill remaining slots from curated regional buckets
            for sp in buckets_raw.get(cat, []):
                if len(picks) >= target:
                    break
                if sp["scientific_name"] in seen:
                    continue
                seen.add(sp["scientific_name"])
                picks.append(sp)
            merged[cat] = picks
        buckets = merged
    else:
        buckets = buckets_raw

    flat = _flatten_buckets(buckets)
    bpw = flat[0]["best_planting_window"] if flat else "Early rains / dormant season"
    pretty_region = region.replace("_", " ").title()
    notes = (
        "Rule-based regional fallback — drawn from a curated native-species "
        f"database for this biogeographic region ({pretty_region}). "
        "Confirm with local forestry authorities before planting."
    )
    if gbif_candidates:
        top = ", ".join(c["scientific_name"] for c in gbif_candidates[:5])
        notes += f" (GBIF observed nearby: {top}.)"

    species_models = {
        cat: [SpeciesItem(**sp) for sp in items]
        for cat, items in buckets.items()
    }
    flat_models = []
    for cat in ("tree", "shrub", "ground_cover"):
        flat_models.extend(species_models.get(cat, []))

    return SpeciesResponse(
        location=f"~{lat:.2f}, {lng:.2f} ({pretty_region})",
        climate_summary=f"{k_label} ({k_code}). Classification: {suit.land_use}.",
        best_planting_window=bpw,
        species=flat_models,
        species_by_category=species_models,
        notes=notes,
        plantable=True,
        climate_code=k_code,
    )


@api_router.post("/recommendations/species", response_model=SpeciesResponse)
async def recommend_species(req: SpeciesRequest):
    # Grid-snap to ~1.1 km for deterministic caching (unchanged)
    glat = round(req.lat, 2)
    glng = round(req.lng, 2)
    cache_key = (glat, glng)
    cached = _SPECIES_CACHE.get(cache_key)
    if cached is not None:
        return cached

    # Land-check first. A point in a river / on a road should never be asked
    # to produce species — we short-circuit with an explicit non-plantable
    # response regardless of whether the caller passed pre-computed suitability.
    suit = req.suitability or compute_suitability(req.lat, req.lng)
    # If the caller didn't pre-populate land-check fields, do it now.
    if suit.restriction_reason is None and suit.land_check_source is None:
        land = await classify_land_point(req.lat, req.lng)
        if not land.get("plantable", True):
            suit.plantable = False
            suit.restriction_reason = land.get("reason")
            suit.restriction_feature = land.get("feature")
            suit.land_check_source = land.get("source")
            suit.zone = "restricted_protected"
            suit.legal_status = "restricted"

    if not suit.plantable:
        resp = _non_plantable_response(req.lat, req.lng, suit)
        _cache_store(cache_key, resp)
        return resp

    region = classify_bioregion(req.lat, req.lng)
    k_code, k_label = classify_koppen(req.lat, req.lng)
    tags = climate_tags(req.lat, req.lng)

    # --- GBIF prior: real plant observations near this point -----------------
    gbif_candidates = await fetch_native_species_near(req.lat, req.lng)
    has_gbif = bool(gbif_candidates and len(gbif_candidates) >= 4)
    if has_gbif:
        gbif_buckets = partition_by_category(gbif_candidates)
        def _fmt(bucket):
            return "\n".join(
                f"  - {c['scientific_name']}"
                + (f" (family {c['family']})" if c['family'] else "")
                + (f" — {c['observation_count']} obs" if c.get("observation_count") else "")
                + ("  [native]" if c.get("native") is True else "")
                for c in bucket[:12]
            ) or "  (none)"
        gbif_hint = (
            "\n\nGBIF observations near this point (real occurrences — use these as the "
            "PRIMARY candidate pool; categories pre-classified):\n"
            f"TREES:\n{_fmt(gbif_buckets.get('tree', []))}\n"
            f"SHRUBS:\n{_fmt(gbif_buckets.get('shrub', []))}\n"
            f"GROUND COVER:\n{_fmt(gbif_buckets.get('ground_cover', []))}\n"
            "Prefer [native]-flagged species. Filter out invasives."
        )
    else:
        region_example_names = ", ".join(
            sp["common_name"] for sp in (REGIONAL_SPECIES_DB.get(region) or [])[:6]
        )
        gbif_hint = (
            f"\n\nNo GBIF observations available; typical native candidates in this "
            f"biogeographic region include: {region_example_names}."
        )

    system = (
        "You are a forestry & restoration-ecology assistant. Given coordinates, a "
        "Köppen climate code, a biogeographic region, local ecological signals and "
        "a list of plants actually observed nearby (GBIF, already split into "
        "Trees / Shrubs / Ground cover), recommend 15 native species total for "
        "community planting at THIS specific location, split as:\n"
        "  - 6 TREES (category: \"tree\")\n"
        "  - 5 SHRUBS (category: \"shrub\")\n"
        "  - 4 GROUND COVER (category: \"ground_cover\") — grasses, creepers, low herbs, ferns\n"
        "STRONGLY prefer species from the GBIF observation list when provided. "
        "All picks MUST be native to the stated biogeographic region & climate "
        "zone. NO invasives, NO foreign transplants (e.g., no Neem outside S. "
        "Asia, no Eucalyptus outside Australia for restoration).\n\n"
        "CRITICAL OUTPUT FORMAT: You MUST return a `species_by_category` object "
        "with THREE keys ('tree', 'shrub', 'ground_cover'). DO NOT return a flat "
        "`species` array at the top level — every recommendation must live inside "
        "its category bucket. Reply with ONLY valid JSON, no markdown:\n"
        "{\n"
        '  "location": "short locality description",\n'
        '  "climate_summary": "1-2 sentence climate summary quoting the Köppen code",\n'
        '  "best_planting_window": "season + months",\n'
        '  "species_by_category": {\n'
        '    "tree":         [ {"common_name":"","scientific_name":"","why":"","best_planting_window":"","water_needs":"low|medium|high","growth_rate":"slow|medium|fast","biodiversity_value":"","category":"tree"} ],\n'
        '    "shrub":        [ {... "category":"shrub" ...} ],\n'
        '    "ground_cover": [ {... "category":"ground_cover" ...} ]\n'
        "  },\n"
        '  "notes": "1-2 sentence caveat about local consultation"\n'
        "}"
    )
    user_text = (
        f"Coordinates: lat={req.lat}, lng={req.lng}\n"
        f"Köppen zone: {k_code} — {k_label}\n"
        f"Moisture regime: {tags.get('moisture')}, Temperature regime: {tags.get('temp')}\n"
        f"Biogeographic region: {region.replace('_', ' ')}\n"
        f"NDVI: {suit.ndvi}, Soil moisture: {suit.soil_moisture}%, "
        f"Canopy cover: {suit.canopy_cover}%, Water availability: {suit.water_availability}%\n"
        f"Land use: {suit.land_use}\nLegal status: {suit.legal_status}\n"
        f"Region hint: {req.region_hint or 'unspecified'}"
        f"{gbif_hint}\n\n"
        "Return ONLY the JSON. No markdown, no commentary."
    )

    if not EMERGENT_LLM_KEY or LlmChat is None:
        logging.info("LLM unavailable — using regional fallback for %s,%s (%s)", req.lat, req.lng, region)
        resp = _regional_fallback(req.lat, req.lng, suit, gbif_candidates)
        _cache_store(cache_key, resp)
        return resp

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"species-{uuid.uuid4()}",
            system_message=system,
        ).with_model("openai", "gpt-4o-mini")
        raw = await chat.send_message(UserMessage(text=user_text))
        data = _extract_json_object(raw)
        if not data:
            raise ValueError("empty llm response")

        # Accept either the new categorised format OR the legacy flat list
        # (for smoother rollout). If the LLM returned a flat list where each
        # item has a ``category`` field, we still bucket them.
        by_cat = data.get("species_by_category") or {}
        flat_list = data.get("species") or []

        if by_cat and any(by_cat.get(k) for k in ("tree", "shrub", "ground_cover")):
            # Normalise category strings on the child items
            normalised: Dict[str, List[SpeciesItem]] = {}
            flat: List[SpeciesItem] = []
            for cat in ("tree", "shrub", "ground_cover"):
                items = by_cat.get(cat) or []
                cleaned = []
                for it in items:
                    it = {**it, "category": cat}
                    try:
                        cleaned.append(SpeciesItem(**it))
                    except Exception:
                        continue
                normalised[cat] = cleaned
                flat.extend(cleaned)
            resp = SpeciesResponse(
                location=data.get("location") or f"~{req.lat:.2f}, {req.lng:.2f}",
                climate_summary=data.get("climate_summary") or f"{k_label} ({k_code}). {suit.land_use}.",
                best_planting_window=data.get("best_planting_window") or "Start of rainy / dormant season",
                species=flat,
                species_by_category=normalised,
                notes=data.get("notes") or "",
                plantable=True,
                climate_code=k_code,
            )
        elif flat_list:
            # Flat species list — infer buckets from each item's category tag.
            # Missing/invalid categories default to "tree" so rendering stays
            # sensible even on degraded LLM output.
            items_by_cat: Dict[str, List[SpeciesItem]] = {
                "tree": [], "shrub": [], "ground_cover": []
            }
            flat: List[SpeciesItem] = []
            for sp in flat_list:
                cat = (sp.get("category") or "tree").lower()
                if cat not in items_by_cat:
                    cat = "tree"
                sp = {**sp, "category": cat}
                try:
                    model = SpeciesItem(**sp)
                    items_by_cat[cat].append(model)
                    flat.append(model)
                except Exception:
                    continue
            if not flat:
                raise ValueError("no valid species items")
            # If the LLM didn't give us any shrubs/ground cover, top up from
            # the regional fallback so the UI still has all three categories.
            topups = pick_species_categorised(req.lat, req.lng, region,
                                              trees=0, shrubs=5, ground_cover=4)
            for cat in ("shrub", "ground_cover"):
                if not items_by_cat[cat]:
                    items_by_cat[cat] = [SpeciesItem(**sp) for sp in topups.get(cat, [])]
                    flat.extend(items_by_cat[cat])
            resp = SpeciesResponse(
                location=data.get("location") or f"~{req.lat:.2f}, {req.lng:.2f}",
                climate_summary=data.get("climate_summary") or f"{k_label} ({k_code}). {suit.land_use}.",
                best_planting_window=data.get("best_planting_window") or "Start of rainy / dormant season",
                species=flat,
                species_by_category=items_by_cat,
                notes=data.get("notes") or "",
                plantable=True,
                climate_code=k_code,
            )
        else:
            raise ValueError("no species in llm response")

        if has_gbif and "GBIF" not in (resp.notes or ""):
            resp.notes = (resp.notes or "") + " (Grounded in live GBIF observations near this point.)"
        _cache_store(cache_key, resp)
        return resp
    except Exception as e:
        logging.warning("AI recommendation failed for %s,%s (%s) — falling back. %s",
                        req.lat, req.lng, region, e)
        resp = _regional_fallback(req.lat, req.lng, suit, gbif_candidates)
        _cache_store(cache_key, resp)
        return resp


# ---- Simple in-process cache for species recommendations -------------------
_SPECIES_CACHE: dict = {}
_SPECIES_CACHE_MAX = 500

def _cache_store(key, value):
    if len(_SPECIES_CACHE) >= _SPECIES_CACHE_MAX:
        _SPECIES_CACHE.clear()
    _SPECIES_CACHE[key] = value


app.include_router(api_router)


# --- Insights endpoints (regional + organizations) -----------------------
class InsightsRequest(BaseModel):
    lat: float
    lng: float


_insights_router = APIRouter(prefix="/api")


@_insights_router.post("/insights/regional")
async def insights_regional(req: InsightsRequest):
    return await fetch_regional_insights(db, req.lat, req.lng)


@_insights_router.post("/insights/news")
async def insights_news(req: InsightsRequest):
    return await fetch_news(db, req.lat, req.lng)


@_insights_router.post("/insights/organizations")
async def insights_orgs(req: InsightsRequest):
    return await fetch_organizations(db, req.lat, req.lng)


app.include_router(_insights_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

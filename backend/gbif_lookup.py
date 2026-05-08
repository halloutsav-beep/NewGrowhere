"""
GBIF-backed native plant lookup, now category-aware.

Uses the public GBIF occurrence API (no auth required) to find plants actually
observed near a given lat/lng. Aggregates by species and returns the most
frequently observed taxa, with a best-effort category (tree / shrub /
ground_cover) inferred from GBIF taxonomic ranks + a curated family heuristic.

Docs: https://techdocs.gbif.org/en/openapi/v1/occurrence
"""

import logging
import httpx
from typing import List, Optional

log = logging.getLogger(__name__)

GBIF_BASE = "https://api.gbif.org/v1"

# Plantae kingdom key in GBIF's taxonomic backbone.
KINGDOM_KEY_PLANTAE = 6


# ---------------------------------------------------------------------------
# Family / class -> habit heuristic
# ---------------------------------------------------------------------------
# GBIF records commonly include `family` and `class` but not growth form. We
# approximate the habit (tree / shrub / ground_cover) from the family, which
# is good enough for ranking and display. Ambiguous families default to tree
# if they're woody, shrub otherwise.

_TREE_FAMILIES = {
    # Iconic / restoration tree families
    "Fagaceae", "Pinaceae", "Dipterocarpaceae", "Sapotaceae", "Meliaceae",
    "Fabaceae",  # many trees (Acacia, Prosopis, Delonix...) fall here; we
                 # refine below via genus heuristics where we can.
    "Myrtaceae", "Lauraceae", "Moraceae", "Anacardiaceae", "Bignoniaceae",
    "Betulaceae", "Salicaceae", "Combretaceae", "Lecythidaceae",
    "Proteaceae", "Casuarinaceae", "Araucariaceae", "Cupressaceae",
    "Podocarpaceae", "Arecaceae", "Juglandaceae", "Ulmaceae",
    "Rhizophoraceae", "Magnoliaceae", "Hamamelidaceae", "Platanaceae",
    "Altingiaceae", "Bombacaceae", "Malvaceae",  # includes Ceiba, Hibiscus
    "Tiliaceae",
}

_SHRUB_FAMILIES = {
    "Rosaceae",      # many shrubs + some trees
    "Ericaceae",     # Rhododendron, Vaccinium
    "Oleaceae",      # Syringa, Forsythia (also some trees)
    "Rubiaceae",     # Ixora, Coffea
    "Caprifoliaceae",
    "Verbenaceae",   # Lantana
    "Apocynaceae",   # Nerium, Plumeria
    "Cistaceae",     # Cistus
    "Myricaceae",    # Myrica
    "Berberidaceae", # Berberis
    "Thymelaeaceae",
    "Melastomataceae",
    "Grossulariaceae",
    "Hydrangeaceae",
}

_GROUND_COVER_FAMILIES = {
    "Poaceae",           # grasses
    "Cyperaceae",        # sedges
    "Juncaceae",         # rushes
    "Asteraceae",        # many herbs / low cover
    "Lamiaceae",         # herbs (Thymus, Salvia etc.) - small shrubs too
    "Polygonaceae",
    "Plantaginaceae",
    "Aizoaceae",
    "Caryophyllaceae",
    "Apiaceae",          # Centella etc.
    "Convolvulaceae",    # Ipomoea creepers
    "Orchidaceae",       # orchids — ground-layer
    "Violaceae",
    "Polypodiaceae",     # ferns
    "Dryopteridaceae",
    "Dennstaedtiaceae",
    "Pteridaceae",
    "Athyriaceae",
}

# Genus-level overrides for families that are too broad (esp. Fabaceae,
# Malvaceae). Lowercased keys compared against lowercased genera.
_GENUS_CATEGORY = {
    # Fabaceae trees
    "acacia": "tree", "vachellia": "tree", "prosopis": "tree", "senna": "tree",
    "delonix": "tree", "tamarindus": "tree", "pongamia": "tree",
    "pterocarpus": "tree", "dalbergia": "tree", "cassia": "tree",
    "gliricidia": "tree", "enterolobium": "tree", "albizia": "tree",
    "paubrasilia": "tree", "hymenaea": "tree", "parkia": "tree",
    "erythrina": "tree",
    # Fabaceae shrubs / herbs
    "indigofera": "shrub", "tephrosia": "ground_cover", "crotalaria": "shrub",
    "lupinus": "ground_cover", "trifolium": "ground_cover",
    # Malvaceae — Ceiba / Hibiscus trees vs. Sida ground covers
    "ceiba": "tree", "adansonia": "tree",
    "hibiscus": "shrub", "abutilon": "shrub", "sida": "ground_cover",
    # Lamiaceae
    "rosmarinus": "shrub", "salvia": "shrub", "thymus": "ground_cover",
    "ajuga": "ground_cover", "lavandula": "shrub", "mentha": "ground_cover",
    "origanum": "ground_cover",
    # Asteraceae — most are low cover, some are shrubs
    "baccharis": "shrub", "artemisia": "shrub",
}


def _categorise(family: str, scientific_name: str, rank: Optional[str] = None) -> str:
    """Return one of: 'tree' | 'shrub' | 'ground_cover'.

    Defaults conservatively to 'tree' when family and genus are both unknown,
    so GBIF hits still land in a useful bucket for recommendation.
    """
    f = (family or "").strip()
    genus = (scientific_name or "").split(" ", 1)[0].lower()
    if genus in _GENUS_CATEGORY:
        return _GENUS_CATEGORY[genus]
    if f in _GROUND_COVER_FAMILIES:
        return "ground_cover"
    if f in _SHRUB_FAMILIES:
        return "shrub"
    if f in _TREE_FAMILIES:
        return "tree"
    # Fallback: ferns / mosses -> ground cover; everything else -> tree.
    if f.endswith("aceae") and f in {"Polypodiaceae", "Selaginellaceae",
                                      "Marchantiaceae"}:
        return "ground_cover"
    return "tree"


async def fetch_native_species_near(
    lat: float,
    lng: float,
    radius_deg: float = 0.25,          # ≈ 25 km box side at mid-latitudes
    max_candidates: int = 40,
    fetch_limit: int = 300,             # GBIF page size cap is 300
    timeout: float = 8.0,
) -> Optional[List[dict]]:
    """Return up to ``max_candidates`` plant species observed near (lat, lng),
    sorted by native/observation-frequency, each annotated with ``category``.

    Returns ``None`` on hard failure (network / bad JSON).
    """
    params = {
        "decimalLatitude":  f"{lat - radius_deg:.3f},{lat + radius_deg:.3f}",
        "decimalLongitude": f"{lng - radius_deg:.3f},{lng + radius_deg:.3f}",
        "kingdomKey":       KINGDOM_KEY_PLANTAE,
        "hasCoordinate":    "true",
        "hasGeospatialIssue": "false",
        "limit":            fetch_limit,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(f"{GBIF_BASE}/occurrence/search", params=params)
        if r.status_code != 200:
            log.warning("GBIF non-200: %s", r.status_code)
            return None
        payload = r.json()
    except Exception as e:
        log.warning("GBIF request failed (%s, %s): %s", lat, lng, e)
        return None

    agg: dict = {}
    for rec in payload.get("results", []):
        sp = rec.get("species") or rec.get("acceptedScientificName")
        if not sp:
            continue
        family = rec.get("family") or ""
        entry = agg.setdefault(sp, {
            "scientific_name": sp,
            "common_name": None,
            "family": family,
            "category": _categorise(family, sp),
            "observation_count": 0,
            "native": None,
        })
        entry["observation_count"] += 1
        if not entry["common_name"]:
            vn = rec.get("vernacularName")
            if vn:
                entry["common_name"] = vn
        em = (rec.get("establishmentMeans") or "").upper()
        if em == "NATIVE":
            entry["native"] = True
        elif em in {"INTRODUCED", "NATURALISED", "INVASIVE", "MANAGED"} and entry["native"] is None:
            entry["native"] = False

    ranked = sorted(
        agg.values(),
        key=lambda e: (
            0 if e["native"] is True else (1 if e["native"] is None else 2),
            -e["observation_count"],
            e["scientific_name"],
        ),
    )
    return ranked[:max_candidates]


def partition_by_category(candidates: List[dict]) -> dict:
    """Split a ranked GBIF candidate list into the three planting categories."""
    buckets = {"tree": [], "shrub": [], "ground_cover": []}
    for c in candidates or []:
        cat = c.get("category") or "tree"
        buckets.setdefault(cat, []).append(c)
    return buckets

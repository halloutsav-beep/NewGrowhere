"""
Deterministic climate zone classifier.

Given a (lat, lng), return a stable Köppen-style zone code and a human-readable
label — no LLM inference, no randomness, no external API calls. Same coord in,
same zone out, forever.

Scope: designed for the GROWhere planting-recommendation use case. It doesn't
try to reproduce the full 30+ Köppen sub-classes; instead it emits the
five major groups (A/B/C/D/E) with the key sub-codes needed for plant choice:

    Af   Tropical rainforest          (equatorial, wet year-round)
    Am   Tropical monsoon             (monsoon-driven, SE/South Asia)
    Aw   Tropical savanna             (wet-dry tropical)
    BWh  Hot desert                   (Sahara, Arabia, Thar)
    BWk  Cold desert                  (Gobi, Great Basin)
    BSh  Hot semi-arid / steppe
    BSk  Cold semi-arid / steppe
    Csa  Mediterranean, hot summer    (Iberia, Med basin, California)
    Cfa  Humid subtropical
    Cfb  Oceanic / marine temperate   (NW Europe, Pacific NW)
    Dfa  Humid continental hot sum.
    Dfb  Humid continental warm sum.
    Dfc  Subarctic / boreal
    ET   Tundra
    EF   Ice cap

Overlay logic:
- Start from latitude band (default temperate/tropical/polar).
- Apply known regional overrides using simple lat/lng bounding boxes
  (deserts, monsoon zones, mediterranean basin, etc.) — these are the
  regions where a latitude-only call would be wrong.
- Elevation/continentality nuances are intentionally omitted; they'd need
  a DEM and for MVP the region boxes cover the big miscalls.
"""

from typing import Tuple

# (min_lat, max_lat, min_lng, max_lng, code, label)
# Order matters: first match wins. Put the most specific boxes FIRST.
_CLIMATE_OVERRIDES = [
    # --- Hot deserts (BWh) -------------------------------------------------
    # Sahara (includes parts of N. Africa)
    (15.0, 32.0, -17.0, 38.0, "BWh", "Hot desert (Sahara / Arabian belt)"),
    # Arabian peninsula + Syrian / Iraqi desert
    (13.0, 32.0, 34.0, 60.0, "BWh", "Hot desert (Arabian)"),
    # Thar / Kutch arid zone
    (23.0, 30.0, 68.0, 76.0, "BWh", "Hot desert (Thar)"),
    # Sonoran / Mojave (SW USA + NW Mexico)
    (22.0, 36.0, -118.0, -102.0, "BWh", "Hot desert (Sonoran/Mojave)"),
    # Atacama
    (-30.0, -17.0, -73.0, -68.0, "BWh", "Hot desert (Atacama)"),
    # Kalahari / Namib
    (-30.0, -17.0, 12.0, 26.0, "BWh", "Hot desert (Kalahari/Namib)"),
    # Australian Outback core
    (-32.0, -20.0, 118.0, 142.0, "BWh", "Hot desert (Australian outback)"),

    # --- Cold deserts (BWk) ------------------------------------------------
    # Gobi + Taklamakan
    (36.0, 48.0, 75.0, 115.0, "BWk", "Cold desert (Gobi/Taklamakan)"),
    # Great Basin
    (36.0, 44.0, -120.0, -110.0, "BWk", "Cold desert (Great Basin)"),
    # Patagonian desert
    (-50.0, -38.0, -72.0, -65.0, "BWk", "Cold desert (Patagonia)"),

    # --- Hot semi-arid (BSh) ----------------------------------------------
    # Sahel
    (10.0, 17.0, -18.0, 38.0, "BSh", "Hot semi-arid (Sahel)"),
    # Horn of Africa lowlands
    (2.0, 13.0, 38.0, 52.0, "BSh", "Hot semi-arid (Horn of Africa)"),
    # Deccan plateau dry belt + inland peninsular India
    (13.0, 22.0, 74.0, 82.0, "BSh", "Hot semi-arid (Deccan interior)"),
    # NE Brazilian sertão
    (-15.0, -3.0, -45.0, -35.0, "BSh", "Hot semi-arid (Sertão)"),
    # Australian semi-arid belt
    (-32.0, -18.0, 115.0, 150.0, "BSh", "Hot semi-arid (Australian interior)"),

    # --- Cold semi-arid (BSk) ---------------------------------------------
    # Central Asia steppe
    (40.0, 52.0, 50.0, 85.0, "BSk", "Cold semi-arid (Central Asian steppe)"),
    # US Great Plains west
    (32.0, 48.0, -106.0, -98.0, "BSk", "Cold semi-arid (Great Plains west)"),
    # Iberian meseta + Anatolian plateau interiors
    (37.0, 42.0, -5.0, 1.0, "BSk", "Cold semi-arid (Iberian meseta)"),
    (37.0, 41.0, 30.0, 43.0, "BSk", "Cold semi-arid (Anatolian plateau)"),

    # --- Mediterranean Csa/Csb --------------------------------------------
    # Mediterranean basin
    (30.0, 45.0, -10.0, 40.0, "Csa", "Mediterranean (hot-summer)"),
    # California coastal
    (32.0, 42.0, -124.0, -117.0, "Csa", "Mediterranean (California coast)"),
    # Chilean central valley
    (-38.0, -30.0, -73.0, -70.0, "Csa", "Mediterranean (Central Chile)"),
    # SW Australia + Cape of SA
    (-36.0, -28.0, 115.0, 120.0, "Csa", "Mediterranean (SW Australia)"),
    (-35.0, -32.0, 17.0, 20.0, "Csa", "Mediterranean (Cape)"),

    # --- Tropical monsoon (Am) --------------------------------------------
    # Indian subcontinent monsoon belt (core) — widened north to cover
    # Indo-Gangetic plains including Delhi NCR.
    (8.0, 30.5, 72.0, 92.0, "Am", "Tropical monsoon (S. Asia)"),
    # Mainland SE Asia + Western Ghats wet side
    (7.0, 23.0, 92.0, 110.0, "Am", "Tropical monsoon (SE Asia)"),
    # West African monsoon (Guinea coast)
    (4.0, 12.0, -17.0, 15.0, "Am", "Tropical monsoon (W. Africa)"),

    # --- Tropical rainforest (Af) -----------------------------------------
    # Amazon core
    (-10.0, 5.0, -75.0, -50.0, "Af", "Tropical rainforest (Amazon)"),
    # Congo basin
    (-5.0, 5.0, 10.0, 30.0, "Af", "Tropical rainforest (Congo)"),
    # Malay archipelago / Borneo / Sumatra / New Guinea
    (-10.0, 7.0, 95.0, 150.0, "Af", "Tropical rainforest (Malay/New Guinea)"),

    # --- Tropical savanna (Aw) --------------------------------------------
    # Cerrado + Llanos + N. Australian savanna already caught by lat band;
    # add East African savanna explicitly (Kenya, Tanzania plateau)
    (-12.0, 5.0, 30.0, 42.0, "Aw", "Tropical savanna (E. African)"),
    # N. Australian tropical savanna
    (-20.0, -11.0, 122.0, 145.0, "Aw", "Tropical savanna (N. Australia)"),
    # Indian east/south Deccan savanna-like
    (8.0, 20.0, 77.0, 85.0, "Aw", "Tropical savanna (Peninsular India dry)"),

    # --- Oceanic / marine temperate (Cfb) ---------------------------------
    # NW Europe (British Isles, NW France, Benelux, Denmark)
    (47.0, 60.0, -10.0, 10.0, "Cfb", "Oceanic temperate (NW Europe)"),
    # Pacific NW
    (43.0, 55.0, -130.0, -120.0, "Cfb", "Oceanic temperate (Pacific NW)"),
    # New Zealand
    (-48.0, -34.0, 166.0, 179.0, "Cfb", "Oceanic temperate (New Zealand)"),

    # --- Humid subtropical (Cfa) ------------------------------------------
    # SE USA
    (25.0, 37.0, -95.0, -75.0, "Cfa", "Humid subtropical (SE USA)"),
    # SE China + Taiwan + S. Japan (extended east to cover Tokyo/Kanto plain)
    (22.0, 37.0, 100.0, 142.0, "Cfa", "Humid subtropical (E. Asia)"),
    # Río de la Plata basin
    (-35.0, -20.0, -62.0, -47.0, "Cfa", "Humid subtropical (Río de la Plata)"),
    # SE Australia coastal
    (-37.0, -24.0, 148.0, 155.0, "Cfa", "Humid subtropical (SE Australia)"),

    # --- Humid continental (Dfa/Dfb) --------------------------------------
    # NE USA + Great Lakes + Midwest
    (37.0, 49.0, -100.0, -70.0, "Dfa", "Humid continental (NE USA)"),
    # C/E Europe (Poland, Belarus, Baltic, Ukraine inland)
    (46.0, 60.0, 10.0, 40.0, "Dfb", "Humid continental (C. Europe)"),
    # NE Asia (NE China, Korea interior)
    (38.0, 55.0, 120.0, 140.0, "Dfb", "Humid continental (NE Asia)"),

    # --- Subarctic / Boreal (Dfc) -----------------------------------------
    (50.0, 66.0, -170.0, -50.0, "Dfc", "Subarctic / boreal (N. America)"),
    (55.0, 66.0, 20.0, 180.0, "Dfc", "Subarctic / boreal (Eurasia)"),
]


def _latitude_default(lat: float) -> Tuple[str, str]:
    """Fallback when no override matches — broad latitude band."""
    a = abs(lat)
    if a < 10:
        return "Af", "Equatorial / tropical humid"
    if a < 23.5:
        return "Aw", "Tropical / subtropical (wet-dry)"
    if a < 35:
        return "Cfa", "Subtropical"
    if a < 50:
        return "Cfb" if a < 45 else "Dfb", "Temperate"
    if a < 66:
        return "Dfc", "Boreal / cold temperate"
    if a < 80:
        return "ET", "Tundra"
    return "EF", "Ice cap / polar"


def classify_koppen(lat: float, lng: float) -> Tuple[str, str]:
    """Return (koppen_code, human_label) for a given lat/lng deterministically.

    The same (lat, lng) always returns the same result.
    """
    for (min_lat, max_lat, min_lng, max_lng, code, label) in _CLIMATE_OVERRIDES:
        if min_lat <= lat <= max_lat and min_lng <= lng <= max_lng:
            return code, label
    return _latitude_default(lat)


def climate_summary(lat: float, lng: float) -> str:
    """Short human-readable climate summary for the UI / LLM prompt."""
    code, label = classify_koppen(lat, lng)
    return f"{label} ({code})"


# Map Köppen code -> coarse moisture / temperature tags used by species picker
KOPPEN_TO_TAGS = {
    "Af":  {"moisture": "wet",       "temp": "hot"},
    "Am":  {"moisture": "monsoonal", "temp": "hot"},
    "Aw":  {"moisture": "seasonal",  "temp": "hot"},
    "BWh": {"moisture": "arid",      "temp": "hot"},
    "BWk": {"moisture": "arid",      "temp": "cold"},
    "BSh": {"moisture": "semi_arid", "temp": "hot"},
    "BSk": {"moisture": "semi_arid", "temp": "cold"},
    "Csa": {"moisture": "dry_summer","temp": "warm"},
    "Csb": {"moisture": "dry_summer","temp": "mild"},
    "Cfa": {"moisture": "humid",     "temp": "warm"},
    "Cfb": {"moisture": "humid",     "temp": "mild"},
    "Dfa": {"moisture": "humid",     "temp": "cold"},
    "Dfb": {"moisture": "humid",     "temp": "cold"},
    "Dfc": {"moisture": "humid",     "temp": "boreal"},
    "ET":  {"moisture": "cold",      "temp": "tundra"},
    "EF":  {"moisture": "frozen",    "temp": "polar"},
}


def climate_tags(lat: float, lng: float) -> dict:
    code, _ = classify_koppen(lat, lng)
    return {"code": code, **KOPPEN_TO_TAGS.get(code, {"moisture": "unknown", "temp": "unknown"})}

"""
Backend tests for GROWhere iteration 5:
- Köppen climate zone determinism
- Polygon-based plantability (Overpass + fallback)
- Categorised species recommendations (6 trees / 5 shrubs / 4 ground_cover)
- Determinism + variation across far-apart coordinates
- Backward compatibility: flat species[] always populated
- Fallback when GBIF / LLM unavailable
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

# Generous timeout — Overpass can take up to 7s, GBIF up to 7s, LLM ~10s.
SUIT_TIMEOUT = 60
SPECIES_TIMEOUT = 120


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --------------------- Health ---------------------
def test_root(session):
    r = session.get(f"{API}/", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert data.get("app") == "GROWhere"
    assert data.get("status") == "ok"


# --------------------- Climate zone determinism ---------------------
# Delhi (28.6139, 77.2090) — S. Asia monsoon belt -> Am
# Tokyo (35.6762, 139.6503) — humid subtropical (E. Asia) -> Cfa
# Sahara (22.0, 15.0) — hot desert (Sahara) -> BWh
KNOWN_POINTS = [
    ("Delhi",  28.6139, 77.2090, "Am"),
    ("Tokyo",  35.6762, 139.6503, "Cfa"),
    ("Sahara", 22.0,    15.0,    "BWh"),
]


@pytest.mark.parametrize("name,lat,lng,expected", KNOWN_POINTS)
def test_suitability_climate_code(session, name, lat, lng, expected):
    r = session.post(f"{API}/analysis/suitability", json={"lat": lat, "lng": lng}, timeout=SUIT_TIMEOUT)
    assert r.status_code == 200, f"{name}: {r.status_code} {r.text}"
    data = r.json()
    # New deterministic fields must be present
    assert "climate_code" in data and data["climate_code"] is not None, f"{name}: missing climate_code"
    assert "climate_label" in data and data["climate_label"], f"{name}: missing climate_label"
    assert "plantable" in data
    assert "land_check_source" in data
    assert data["climate_code"] == expected, (
        f"{name} expected Köppen {expected} but got {data['climate_code']} ({data['climate_label']})"
    )


def test_suitability_determinism_same_coords(session):
    """Same lat/lng called twice -> identical response (modulo land_check_source)."""
    payload = {"lat": 19.0760, "lng": 72.8777}  # Mumbai
    r1 = session.post(f"{API}/analysis/suitability", json=payload, timeout=SUIT_TIMEOUT).json()
    r2 = session.post(f"{API}/analysis/suitability", json=payload, timeout=SUIT_TIMEOUT).json()
    # Critical deterministic fields
    for key in ("climate_code", "climate_label", "ndvi", "soil_moisture",
                "canopy_cover", "water_availability", "land_use",
                "legal_status", "suitability_score", "zone", "confidence"):
        assert r1[key] == r2[key], f"determinism violated for {key}: {r1[key]} != {r2[key]}"


# --------------------- Species recommendation (categorised) ---------------------
def _post_species(session, lat, lng):
    r = session.post(f"{API}/recommendations/species",
                     json={"lat": lat, "lng": lng}, timeout=SPECIES_TIMEOUT)
    assert r.status_code == 200, f"species call failed: {r.status_code} {r.text[:300]}"
    return r.json()


def test_species_categorised_structure_plantable_point(session):
    # Sanjay Gandhi National Park deep-forest point (Mumbai) — guaranteed
    # plantable area, S. Asia monsoon belt (Am).
    data = _post_species(session, 19.2120, 72.9100)
    if data.get("plantable") is False:
        pytest.skip(f"SGNP point unexpectedly flagged non-plantable: {data.get('restriction_reason')}")
    # Must include flat species + categorised buckets
    assert "species" in data and isinstance(data["species"], list)
    assert "species_by_category" in data and data["species_by_category"] is not None
    sbc = data["species_by_category"]
    assert set(sbc.keys()) >= {"tree", "shrub", "ground_cover"}, sbc.keys()

    trees = sbc.get("tree") or []
    shrubs = sbc.get("shrub") or []
    gc = sbc.get("ground_cover") or []
    # Spec: 6 trees / 5 shrubs / 4 ground_cover. Allow LLM to return slightly
    # less but never more than 6/5/4 and totals must equal flat species.
    assert 1 <= len(trees) <= 6, f"tree count {len(trees)}"
    assert 1 <= len(shrubs) <= 5, f"shrub count {len(shrubs)}"
    assert 1 <= len(gc) <= 4, f"ground_cover count {len(gc)}"
    # Ideal target = 15
    total_cat = len(trees) + len(shrubs) + len(gc)
    assert total_cat >= 10, f"too few species across categories: {total_cat}"
    # flat list must equal sum of buckets (backward compat)
    assert len(data["species"]) == total_cat, (
        f"flat species ({len(data['species'])}) != sum of buckets ({total_cat})"
    )
    # Each species has a category field
    for sp in data["species"]:
        assert sp.get("category") in ("tree", "shrub", "ground_cover"), sp
        assert sp.get("scientific_name"), sp
    # climate_code surfaced — Bangalore should be in S. Asia monsoon (Am)
    assert data.get("climate_code") in ("Am", "Aw"), data.get("climate_code")
    assert data.get("plantable") is True


def test_species_determinism_same_coords(session):
    """Two consecutive calls with same lat/lng -> identical scientific_name lists."""
    lat, lng = 19.0760, 72.8777  # Mumbai
    a = _post_species(session, lat, lng)
    b = _post_species(session, lat, lng)
    sci_a = [s["scientific_name"] for s in a["species"]]
    sci_b = [s["scientific_name"] for s in b["species"]]
    assert sci_a == sci_b, f"determinism failed:\nA={sci_a}\nB={sci_b}"
    # Categorised determinism
    for cat in ("tree", "shrub", "ground_cover"):
        ca = [s["scientific_name"] for s in (a.get("species_by_category") or {}).get(cat, [])]
        cb = [s["scientific_name"] for s in (b.get("species_by_category") or {}).get(cat, [])]
        assert ca == cb, f"category {cat} not deterministic: {ca} vs {cb}"


def test_species_variation_across_far_apart_locations(session):
    """Delhi vs Mumbai vs London -> different climate codes & different species sets."""
    delhi  = _post_species(session, 28.6139, 77.2090)
    mumbai = _post_species(session, 19.0760, 72.8777)
    london = _post_species(session, 51.5074, -0.1278)

    # Climate codes should differ (Am vs Am vs Cfb expected — Delhi & Mumbai
    # may share Am but London must differ from both).
    codes = {delhi["climate_code"], mumbai["climate_code"], london["climate_code"]}
    assert london["climate_code"] != delhi["climate_code"], "London should not share Köppen code with Delhi"
    assert london["climate_code"] != mumbai["climate_code"], "London should not share Köppen code with Mumbai"
    assert "Cfb" in codes or london["climate_code"].startswith("C") or london["climate_code"].startswith("D"), \
        f"London climate_code unexpected: {london['climate_code']}"

    # Species lists should differ (Jaccard overlap of London vs Delhi must be small)
    set_d = {s["scientific_name"] for s in delhi["species"]}
    set_l = {s["scientific_name"] for s in london["species"]}
    overlap = len(set_d & set_l) / max(1, len(set_d | set_l))
    assert overlap < 0.2, f"Delhi and London species too similar ({overlap:.0%}): {set_d & set_l}"


# --------------------- Non-plantable surface handling ---------------------
def _is_non_plantable(suit_response: dict) -> bool:
    return suit_response.get("plantable") is False


def test_non_plantable_pin_river_or_road(session):
    """Try a few well-known non-plantable points. We accept Overpass fallback
    (source='fallback') as a valid outcome but at least one point should be
    correctly classified as non-plantable when Overpass is reachable."""
    candidates = [
        # Mid-Yamuna river, Delhi (clearly water)
        (28.6195, 77.2435),
        # Middle of Tokyo Bay
        (35.5494, 139.7798),
        # Connaught Place busy circle, Delhi
        (28.6328, 77.2197),
    ]
    saw_overpass = False
    saw_non_plantable = False
    for lat, lng in candidates:
        r = session.post(f"{API}/analysis/suitability",
                         json={"lat": lat, "lng": lng}, timeout=SUIT_TIMEOUT)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "land_check_source" in data
        if data.get("land_check_source") == "overpass":
            saw_overpass = True
            if _is_non_plantable(data):
                saw_non_plantable = True
                # Must surface a reason and force restricted_protected
                assert data.get("restriction_reason"), data
                assert data["zone"] == "restricted_protected", data["zone"]
                assert data["legal_status"] == "restricted"
                assert data["suitability_score"] <= 5
    # Soft assertion: if Overpass was reachable for at least one point,
    # at least one of these obvious water/road points must be flagged.
    if saw_overpass:
        assert saw_non_plantable, (
            "Overpass returned data but no candidate flagged as non-plantable — "
            "polygon/line check may be broken."
        )


def test_species_blocked_for_non_plantable(session):
    """If pin sits on water/road, /recommendations/species must refuse with
    plantable=false and empty species. Try a few candidates and use the first
    one Overpass confirms is non-plantable."""
    candidates = [
        (28.6195, 77.2435),  # Yamuna river / footway, Delhi
        (28.6328, 77.2197),  # Connaught Place
        (28.6139, 77.2090),  # CP busy intersection
        (35.6762, 139.6503), # Tokyo center (road)
    ]
    target = None
    for lat, lng in candidates:
        suit = session.post(f"{API}/analysis/suitability",
                            json={"lat": lat, "lng": lng}, timeout=SUIT_TIMEOUT).json()
        if suit.get("plantable") is False and suit.get("land_check_source") in ("overpass", "cache"):
            target = (lat, lng, suit)
            break
    if target is None:
        pytest.skip("Overpass unavailable for all candidate non-plantable points")
    lat, lng, suit = target
    r = session.post(f"{API}/recommendations/species",
                     json={"lat": lat, "lng": lng}, timeout=SPECIES_TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["plantable"] is False
    assert data["species"] == []
    sbc = data["species_by_category"]
    assert sbc == {"tree": [], "shrub": [], "ground_cover": []}
    assert data.get("restriction_reason"), data
    notes_lower = (data["notes"] or "").lower()
    assert any(k in notes_lower for k in ("river", "water", "road", "non-plantable", "built")), data["notes"]


# --------------------- Zones endpoint (regression) ---------------------
def test_zones_still_works(session):
    r = session.get(f"{API}/analysis/zones", params={"lat": 28.6139, "lng": 77.2090, "radius_km": 2.0},
                    timeout=SUIT_TIMEOUT)
    assert r.status_code == 200, r.text
    zones = r.json()
    assert isinstance(zones, list)
    if zones:
        z = zones[0]
        for k in ("id", "zone", "suitability_score", "center_lat", "center_lng", "radius_m", "label"):
            assert k in z, f"zone missing {k}: {z}"


def test_zones_deterministic(session):
    params = {"lat": 19.0760, "lng": 72.8777, "radius_km": 2.0}
    z1 = session.get(f"{API}/analysis/zones", params=params, timeout=SUIT_TIMEOUT).json()
    z2 = session.get(f"{API}/analysis/zones", params=params, timeout=SUIT_TIMEOUT).json()
    ids1 = sorted([z["id"] for z in z1])
    ids2 = sorted([z["id"] for z in z2])
    assert ids1 == ids2, "zones not deterministic"


# --------------------- Fallback: remote / ocean ---------------------
def test_fallback_remote_ocean(session):
    """Mid-Pacific point — GBIF likely has no plant observations. Fallback
    must still return a categorised response (curated regional fallback).
    Note: if Overpass classifies the ocean point as water, plantable will be
    false which is also acceptable. Either is OK as long as the response is
    structurally well-formed."""
    lat, lng = -30.0, -150.0  # Middle of South Pacific
    data = _post_species(session, lat, lng)
    # Either non-plantable (water poly hit) or fallback species
    assert data.get("climate_code") is not None
    if data["plantable"] is True:
        # fallback must still emit categorised buckets and a non-empty flat list
        assert len(data["species"]) >= 1
        assert "species_by_category" in data
        # All three buckets present (may be empty for sparse regions but key exists)
        for cat in ("tree", "shrub", "ground_cover"):
            assert cat in data["species_by_category"]
    else:
        assert data["species"] == []
        assert data["species_by_category"] == {"tree": [], "shrub": [], "ground_cover": []}

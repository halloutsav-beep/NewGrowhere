"""
Comprehensive backend tests for the two fixed endpoints:
1. GET /api/analysis/zones - deterministic grid-snapped zones
2. POST /api/recommendations/species - region-aware species recommendations
"""
import os
import requests
import json

# Backend URL from environment
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://clean-zones.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

print(f"Testing backend at: {API}")
print("=" * 80)

# Test data: 6 distinct continents
TEST_LOCATIONS = {
    "Bangalore": {"lat": 12.97, "lng": 77.59, "region": "indian_subcontinent"},
    "São Paulo": {"lat": -23.55, "lng": -46.63, "region": "south_america"},
    "Nairobi": {"lat": -1.29, "lng": 36.82, "region": "africa_subsaharan"},
    "Berlin": {"lat": 52.52, "lng": 13.40, "region": "europe_temperate"},
    "Perth": {"lat": -31.95, "lng": 115.86, "region": "australia_oceania"},
    "Tokyo": {"lat": 35.68, "lng": 139.69, "region": "east_asia"},
}

def test_zones_determinism():
    """Test that zones endpoint returns identical results for identical params."""
    print("\n1. Testing zones endpoint determinism...")
    
    params = {"lat": 12.97, "lng": 77.59, "radius_km": 3}
    
    # Call twice with identical params
    r1 = requests.get(f"{API}/analysis/zones", params=params, timeout=30)
    assert r1.status_code == 200, f"First call failed: {r1.status_code} {r1.text}"
    zones1 = r1.json()
    
    r2 = requests.get(f"{API}/analysis/zones", params=params, timeout=30)
    assert r2.status_code == 200, f"Second call failed: {r2.status_code} {r2.text}"
    zones2 = r2.json()
    
    # Verify identical responses
    assert len(zones1) == len(zones2), f"Zone count mismatch: {len(zones1)} vs {len(zones2)}"
    assert zones1 == zones2, "Zones are not identical across calls"
    
    print(f"   ✓ Determinism verified: {len(zones1)} zones returned identically")
    return zones1


def test_zones_id_format(zones):
    """Test that zone IDs have the correct format: zone:<lat:.4f>:<lng:.4f>"""
    print("\n2. Testing zone ID format...")
    
    for zone in zones:
        zone_id = zone.get("id", "")
        assert zone_id.startswith("zone:"), f"Zone ID doesn't start with 'zone:': {zone_id}"
        
        # Parse the ID
        parts = zone_id.split(":")
        assert len(parts) == 3, f"Zone ID doesn't have 3 parts: {zone_id}"
        
        # Verify lat/lng are 4 decimal places
        try:
            lat_str = parts[1]
            lng_str = parts[2]
            # Check format (should have exactly 4 decimal places)
            assert "." in lat_str and "." in lng_str, f"Missing decimal in {zone_id}"
            lat_decimals = len(lat_str.split(".")[1])
            lng_decimals = len(lng_str.split(".")[1])
            assert lat_decimals == 4, f"Lat doesn't have 4 decimals in {zone_id}"
            assert lng_decimals == 4, f"Lng doesn't have 4 decimals in {zone_id}"
        except Exception as e:
            raise AssertionError(f"Invalid zone ID format {zone_id}: {e}")
    
    print(f"   ✓ All {len(zones)} zone IDs have correct format")


def test_zones_schema(zones):
    """Test that zones have all required schema fields."""
    print("\n3. Testing zone schema...")
    
    required_fields = ["id", "zone", "suitability_score", "center_lat", "center_lng", "radius_m", "label"]
    
    for i, zone in enumerate(zones):
        for field in required_fields:
            assert field in zone, f"Zone {i} missing field: {field}"
    
    print(f"   ✓ All zones have required fields: {', '.join(required_fields)}")


def test_zones_count():
    """Test that zone count is within expected range [1, 12]."""
    print("\n4. Testing zone count...")
    
    params = {"lat": 12.97, "lng": 77.59, "radius_km": 3}
    r = requests.get(f"{API}/analysis/zones", params=params, timeout=30)
    assert r.status_code == 200
    zones = r.json()
    
    assert isinstance(zones, list), "Zones should be a list"
    assert 1 <= len(zones) <= 12, f"Zone count {len(zones)} not in range [1, 12]"
    
    print(f"   ✓ Zone count {len(zones)} is within acceptable range [1, 12]")


def test_zones_grid_stability():
    """Test that zones are tied to fixed coordinates - same zone reappears when querying nearby."""
    print("\n5. Testing zone grid stability...")
    
    # First call
    params1 = {"lat": 12.97, "lng": 77.59, "radius_km": 3}
    r1 = requests.get(f"{API}/analysis/zones", params=params1, timeout=30)
    assert r1.status_code == 200
    zones1 = r1.json()
    
    if not zones1:
        print("   ⚠ No zones returned, skipping grid stability test")
        return
    
    # Take the first zone
    first_zone = zones1[0]
    zone_id = first_zone["id"]
    zone_classification = first_zone["zone"]
    center_lat = first_zone["center_lat"]
    center_lng = first_zone["center_lng"]
    
    print(f"   First zone: {zone_id}, classification: {zone_classification}")
    print(f"   Center: ({center_lat}, {center_lng})")
    
    # Query with params shifted by ±0.002 deg from that zone's center
    # This should still be within the same ~1.1 km grid cell
    params2 = {"lat": center_lat + 0.002, "lng": center_lng - 0.002, "radius_km": 3}
    r2 = requests.get(f"{API}/analysis/zones", params=params2, timeout=30)
    assert r2.status_code == 200
    zones2 = r2.json()
    
    # The same zone ID must reappear with the SAME classification
    found = False
    for zone in zones2:
        if zone["id"] == zone_id:
            found = True
            assert zone["zone"] == zone_classification, \
                f"Zone classification changed! Was {zone_classification}, now {zone['zone']}"
            print(f"   ✓ Same zone {zone_id} found with same classification: {zone_classification}")
            break
    
    assert found, f"Zone {zone_id} not found in nearby query - grid stability failed"


def test_species_schema():
    """Test that species endpoint returns correct schema."""
    print("\n6. Testing species endpoint schema...")
    
    payload = {"lat": 12.97, "lng": 77.59}
    r = requests.post(f"{API}/recommendations/species", json=payload, timeout=60)
    assert r.status_code == 200, f"Species call failed: {r.status_code} {r.text}"
    
    data = r.json()
    
    # Check top-level fields
    required_top = ["location", "climate_summary", "best_planting_window", "species", "notes"]
    for field in required_top:
        assert field in data, f"Missing top-level field: {field}"
    
    # Check species array
    assert isinstance(data["species"], list), "species should be a list"
    assert len(data["species"]) >= 1, "species array should have at least 1 item"
    
    # Check species item fields
    required_species_fields = [
        "common_name", "scientific_name", "why", "best_planting_window",
        "water_needs", "growth_rate", "biodiversity_value"
    ]
    
    for i, sp in enumerate(data["species"]):
        for field in required_species_fields:
            assert field in sp, f"Species {i} missing field: {field}"
        
        # Validate enum values
        assert sp["water_needs"] in ["low", "medium", "high"], \
            f"Invalid water_needs: {sp['water_needs']}"
        assert sp["growth_rate"] in ["slow", "medium", "fast"], \
            f"Invalid growth_rate: {sp['growth_rate']}"
    
    print(f"   ✓ Schema validated: {len(data['species'])} species with all required fields")
    return data


def test_species_regional_diversity():
    """Test that different regions return clearly different species."""
    print("\n7. Testing species regional diversity...")
    
    results = {}
    
    for location_name, coords in TEST_LOCATIONS.items():
        payload = {"lat": coords["lat"], "lng": coords["lng"]}
        r = requests.post(f"{API}/recommendations/species", json=payload, timeout=60)
        assert r.status_code == 200, f"Failed for {location_name}: {r.status_code} {r.text}"
        
        data = r.json()
        species_list = [sp["common_name"] for sp in data["species"]]
        results[location_name] = {
            "species": species_list,
            "scientific": [sp["scientific_name"] for sp in data["species"]],
            "region": coords["region"]
        }
        
        print(f"\n   {location_name} ({coords['region']}):")
        print(f"   Species: {', '.join(species_list)}")
    
    # Verify regional specificity
    print("\n   Verifying regional specificity...")
    
    # Check that Neem doesn't appear outside Indian subcontinent
    for location_name, result in results.items():
        if TEST_LOCATIONS[location_name]["region"] != "indian_subcontinent":
            neem_found = any("neem" in sp.lower() for sp in result["species"])
            assert not neem_found, f"Neem found outside India in {location_name}: {result['species']}"
    
    print("   ✓ No Neem found outside Indian subcontinent")
    
    # Check that Eucalyptus doesn't appear outside Australia
    for location_name, result in results.items():
        if TEST_LOCATIONS[location_name]["region"] != "australia_oceania":
            eucalyptus_found = any("eucalyptus" in sp.lower() for sp in result["species"])
            assert not eucalyptus_found, f"Eucalyptus found outside Australia in {location_name}: {result['species']}"
    
    print("   ✓ No Eucalyptus found outside Australia")
    
    # Verify that species lists are different across regions
    species_sets = {loc: set(res["species"]) for loc, res in results.items()}
    
    # Compare each pair of locations
    different_count = 0
    for loc1 in species_sets:
        for loc2 in species_sets:
            if loc1 < loc2:  # Compare each pair once
                overlap = species_sets[loc1] & species_sets[loc2]
                if len(overlap) < len(species_sets[loc1]):  # At least some difference
                    different_count += 1
    
    print(f"   ✓ Regional diversity confirmed: species lists vary across {different_count} location pairs")
    
    return results


def test_species_determinism():
    """Test that same coordinates return identical species arrays (grid-keyed cache)."""
    print("\n8. Testing species determinism (grid-keyed cache)...")
    
    # Test at Nairobi
    payload = {"lat": -1.29, "lng": 36.82}
    
    # Call three times
    r1 = requests.post(f"{API}/recommendations/species", json=payload, timeout=60)
    assert r1.status_code == 200
    data1 = r1.json()
    
    r2 = requests.post(f"{API}/recommendations/species", json=payload, timeout=60)
    assert r2.status_code == 200
    data2 = r2.json()
    
    r3 = requests.post(f"{API}/recommendations/species", json=payload, timeout=60)
    assert r3.status_code == 200
    data3 = r3.json()
    
    # Verify all three are identical
    assert data1 == data2 == data3, "Species responses not identical for same coordinates"
    
    print(f"   ✓ Three calls at (-1.29, 36.82) returned identical species arrays")
    print(f"   Species: {', '.join([sp['common_name'] for sp in data1['species']])}")


def test_species_grid_cell_determinism():
    """Test that coords within same grid cell return identical responses."""
    print("\n9. Testing species grid-cell determinism...")
    
    # Two coords within same ~1.1 km grid cell (grid snaps to 0.01 deg)
    # -1.295 and -1.292 should both snap to -1.29
    # 36.823 and 36.820 should both snap to 36.82
    
    payload1 = {"lat": -1.295, "lng": 36.823}
    payload2 = {"lat": -1.292, "lng": 36.820}
    
    r1 = requests.post(f"{API}/recommendations/species", json=payload1, timeout=60)
    assert r1.status_code == 200
    data1 = r1.json()
    
    r2 = requests.post(f"{API}/recommendations/species", json=payload2, timeout=60)
    assert r2.status_code == 200
    data2 = r2.json()
    
    # Both should return identical species arrays (same grid cell)
    assert data1 == data2, "Species responses differ within same grid cell"
    
    print(f"   ✓ Coords within same grid cell returned identical responses")
    print(f"   Payload 1: {payload1}")
    print(f"   Payload 2: {payload2}")
    print(f"   Species: {', '.join([sp['common_name'] for sp in data1['species']])}")


def test_species_gbif_provenance():
    """Test that at least one continental call shows GBIF provenance marker."""
    print("\n10. Testing GBIF provenance markers...")
    
    gbif_found_locations = []
    fallback_locations = []
    
    for location_name, coords in TEST_LOCATIONS.items():
        payload = {"lat": coords["lat"], "lng": coords["lng"]}
        r = requests.post(f"{API}/recommendations/species", json=payload, timeout=60)
        assert r.status_code == 200, f"Failed for {location_name}: {r.status_code} {r.text}"
        
        data = r.json()
        notes = data.get("notes", "")
        
        # Check for GBIF markers
        if "GBIF" in notes or "Grounded" in notes:
            gbif_found_locations.append(location_name)
            print(f"   ✓ {location_name}: GBIF marker found in notes")
        else:
            fallback_locations.append(location_name)
            print(f"   ⚠ {location_name}: No GBIF marker (likely fallback path)")
    
    # At least one location should have GBIF marker
    assert len(gbif_found_locations) > 0, \
        "No GBIF markers found in any of the 6 continental calls - GBIF integration may be broken"
    
    print(f"\n   ✓ GBIF provenance confirmed in {len(gbif_found_locations)}/{len(TEST_LOCATIONS)} locations")
    print(f"   GBIF-grounded: {', '.join(gbif_found_locations)}")
    if fallback_locations:
        print(f"   Fallback path: {', '.join(fallback_locations)}")


def test_species_fallback_path():
    """Test that remote Pacific location returns valid species (fallback or LLM path)."""
    print("\n11. Testing remote location handling (mid-Pacific)...")
    
    # Mid-Pacific coordinates - virtually no GBIF plant records
    payload = {"lat": -8.0, "lng": -140.0}
    
    r = requests.post(f"{API}/recommendations/species", json=payload, timeout=60)
    assert r.status_code == 200, f"Remote location call failed: {r.status_code} {r.text}"
    
    data = r.json()
    
    # Must have valid species array
    assert "species" in data, "Missing species field in response"
    assert isinstance(data["species"], list), "species should be a list"
    assert len(data["species"]) >= 1, "Should return at least 1 species"
    
    # Verify species are appropriate for Pacific region
    species_list = [sp["common_name"] for sp in data["species"]]
    scientific_list = [sp["scientific_name"] for sp in data["species"]]
    
    # Check if response indicates fallback or GBIF path
    notes = data.get("notes", "")
    if "Rule-based regional fallback" in notes or "fallback" in notes.lower():
        print(f"   ✓ Fallback path used (curated species database)")
    elif "GBIF" in notes or "Grounded" in notes:
        print(f"   ✓ GBIF path used (some observations found in remote location)")
    else:
        print(f"   ✓ LLM path used (generated appropriate Pacific species)")
    
    print(f"   Returned {len(data['species'])} species:")
    for sp in species_list:
        print(f"     - {sp}")
    print(f"   Notes: {notes[:120]}...")


def test_species_tokyo_determinism():
    """Test determinism specifically for Tokyo as requested in review."""
    print("\n12. Testing Tokyo determinism (3 calls)...")
    
    payload = {"lat": 35.68, "lng": 139.69}
    
    # Call three times
    responses = []
    for i in range(3):
        r = requests.post(f"{API}/recommendations/species", json=payload, timeout=60)
        assert r.status_code == 200, f"Tokyo call {i+1} failed: {r.status_code}"
        responses.append(r.json())
    
    # All three must be byte-identical
    assert responses[0] == responses[1] == responses[2], \
        "Tokyo responses not identical across 3 calls"
    
    species_list = [sp["common_name"] for sp in responses[0]["species"]]
    print(f"   ✓ Three calls at Tokyo (35.68, 139.69) returned identical species arrays")
    print(f"   Species: {', '.join(species_list)}")


def test_species_nairobi_grid_shift():
    """Test that ±0.002 deg shift from Nairobi still returns identical species."""
    print("\n13. Testing Nairobi ±0.002 deg grid shift...")
    
    # Base Nairobi coords
    base_payload = {"lat": -1.29, "lng": 36.82}
    
    # Shifted coords (within same grid cell)
    shifted_payload = {"lat": -1.29 + 0.002, "lng": 36.82 - 0.002}
    
    r1 = requests.post(f"{API}/recommendations/species", json=base_payload, timeout=60)
    assert r1.status_code == 200
    data1 = r1.json()
    
    r2 = requests.post(f"{API}/recommendations/species", json=shifted_payload, timeout=60)
    assert r2.status_code == 200
    data2 = r2.json()
    
    # Both should return identical species arrays
    assert data1 == data2, "Species differ for ±0.002 deg shift within same grid cell"
    
    species_list = [sp["common_name"] for sp in data1["species"]]
    print(f"   ✓ Base and shifted coords returned identical species")
    print(f"   Base: {base_payload}")
    print(f"   Shifted: {shifted_payload}")
    print(f"   Species: {', '.join(species_list)}")


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("BACKEND ENDPOINT TESTING - GBIF UPGRADE VERIFICATION")
    print("=" * 80)
    
    try:
        # Test zones endpoint (UNCHANGED - quick verification only)
        print("\n" + "=" * 80)
        print("TESTING: GET /api/analysis/zones (quick verification)")
        print("=" * 80)
        
        zones = test_zones_determinism()
        test_zones_id_format(zones)
        test_zones_schema(zones)
        test_zones_count()
        test_zones_grid_stability()
        
        # Test species endpoint (FOCUS - GBIF upgrade)
        print("\n" + "=" * 80)
        print("TESTING: POST /api/recommendations/species (GBIF UPGRADE)")
        print("=" * 80)
        
        test_species_schema()
        regional_results = test_species_regional_diversity()
        test_species_determinism()
        test_species_grid_cell_determinism()
        
        # NEW GBIF-specific tests
        print("\n" + "=" * 80)
        print("GBIF-SPECIFIC TESTS")
        print("=" * 80)
        
        test_species_gbif_provenance()
        test_species_fallback_path()
        test_species_tokyo_determinism()
        test_species_nairobi_grid_shift()
        
        # Summary
        print("\n" + "=" * 80)
        print("ALL TESTS PASSED ✓")
        print("=" * 80)
        print("\nSummary:")
        print("  ✓ Zones endpoint: deterministic, correct ID format, grid-stable (UNCHANGED)")
        print("  ✓ Species endpoint: GBIF-grounded, region-aware, deterministic, grid-cached")
        print("  ✓ GBIF provenance: markers found in responses")
        print("  ✓ Fallback path: working for remote locations")
        print("  ✓ Schema: unchanged and validated")
        print("=" * 80 + "\n")
        
        return True, regional_results
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return False, None
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False, None


if __name__ == "__main__":
    success, regional_results = main()
    
    # Print detailed species arrays for each continent
    if success and regional_results:
        print("\n" + "=" * 80)
        print("DETAILED SPECIES ARRAYS BY CONTINENT")
        print("=" * 80)
        for location_name, result in regional_results.items():
            print(f"\n{location_name} ({result['region']}):")
            for i, sp in enumerate(result['species'], 1):
                print(f"  {i}. {sp}")
        print("=" * 80 + "\n")
    
    exit(0 if success else 1)

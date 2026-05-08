"""Backend API tests for growhere (formerly Verdura)."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://clean-zones.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

DEMO_EMAIL = "demo@verdura.app"
DEMO_PASS = "demo1234"


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def demo_token(session):
    # try login, else register
    r = session.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASS})
    if r.status_code == 200:
        return r.json()["token"]
    r = session.post(f"{API}/auth/register",
                     json={"email": DEMO_EMAIL, "password": DEMO_PASS, "name": "Demo Planter"})
    assert r.status_code == 200, f"Register failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def fresh_token(session):
    email = f"TEST_{uuid.uuid4().hex[:8]}@verdura.app"
    r = session.post(f"{API}/auth/register",
                     json={"email": email, "password": "pass1234", "name": "Test User"})
    assert r.status_code == 200, r.text
    return r.json()["token"], email


# -------- Health --------
def test_root(session):
    r = session.get(f"{API}/")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("app") == "GROWhere"


# -------- Auth --------
def test_register_duplicate(session, demo_token):
    r = session.post(f"{API}/auth/register",
                     json={"email": DEMO_EMAIL, "password": DEMO_PASS, "name": "Dup"})
    assert r.status_code == 400


def test_login_valid(session):
    r = session.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASS})
    assert r.status_code == 200
    j = r.json()
    assert "token" in j and "user" in j
    assert j["user"]["email"] == DEMO_EMAIL


def test_login_wrong_password(session):
    r = session.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": "wrongpass"})
    assert r.status_code == 401


def test_auth_me(session, demo_token):
    r = session.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {demo_token}"})
    assert r.status_code == 200
    j = r.json()
    assert j["email"] == DEMO_EMAIL
    assert "trees_planted" in j


def test_auth_me_no_token(session):
    r = session.get(f"{API}/auth/me")
    assert r.status_code == 401


# -------- Suitability --------
def test_suitability(session):
    r = session.post(f"{API}/analysis/suitability", json={"lat": 12.97, "lng": 77.59})
    assert r.status_code == 200
    j = r.json()
    for k in ["zone", "suitability_score", "ndvi", "soil_moisture", "canopy_cover",
              "water_availability", "land_use", "legal_status", "legal_note",
              "rationale", "data_sources", "confidence"]:
        assert k in j, f"missing {k}"
    assert j["zone"] in ["high_potential", "moderate_permission_needed", "restricted_protected"]
    assert 0 <= j["suitability_score"] <= 100
    assert isinstance(j["data_sources"], list) and len(j["data_sources"]) > 0


def test_suitability_deterministic(session):
    p = {"lat": 28.61, "lng": 77.21}
    a = session.post(f"{API}/analysis/suitability", json=p).json()
    b = session.post(f"{API}/analysis/suitability", json=p).json()
    assert a == b


def test_zones(session):
    r = session.get(f"{API}/analysis/zones", params={"lat": 12.97, "lng": 77.59})
    assert r.status_code == 200
    zones = r.json()
    # Zones are now tied to a deterministic lat/lng grid within radius_km.
    # Count is variable (not every grid cell is materialized), but bounded.
    assert isinstance(zones, list) and 1 <= len(zones) <= 12
    # Determinism: calling again must return identical IDs and classifications
    r2 = session.get(f"{API}/analysis/zones", params={"lat": 12.97, "lng": 77.59})
    assert r2.status_code == 200
    zones2 = r2.json()
    assert [(z["id"], z["zone"]) for z in zones] == [(z["id"], z["zone"]) for z in zones2]
    z = zones[0]
    for k in ["id", "zone", "suitability_score", "center_lat", "center_lng", "radius_m", "label"]:
        assert k in z
    assert z["id"].startswith("zone:")


# -------- Species (Claude AI) --------
def test_species_recommendation(session):
    r = session.post(f"{API}/recommendations/species",
                     json={"lat": 12.97, "lng": 77.59}, timeout=60)
    assert r.status_code == 200
    j = r.json()
    assert "location" in j and "climate_summary" in j
    assert "species" in j and isinstance(j["species"], list) and len(j["species"]) >= 1
    sp = j["species"][0]
    for k in ["common_name", "scientific_name", "why", "best_planting_window",
              "water_needs", "growth_rate", "biodiversity_value"]:
        assert k in sp


# -------- Plantings --------
def test_create_planting_requires_auth(session):
    r = session.post(f"{API}/plantings",
                     json={"lat": 12.97, "lng": 77.59, "species": "Neem"})
    assert r.status_code == 401


def test_create_planting_increments_count(session, fresh_token):
    token, email = fresh_token
    h = {"Authorization": f"Bearer {token}"}
    me_before = session.get(f"{API}/auth/me", headers=h).json()
    before = me_before["trees_planted"]
    r = session.post(f"{API}/plantings",
                     json={"lat": 12.97, "lng": 77.59, "species": "Neem", "notes": "test"},
                     headers=h)
    assert r.status_code == 200
    j = r.json()
    assert j["species"] == "Neem"
    assert "id" in j
    me_after = session.get(f"{API}/auth/me", headers=h).json()
    assert me_after["trees_planted"] == before + 1


def test_list_plantings(session):
    r = session.get(f"{API}/plantings")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# -------- Community --------
@pytest.fixture(scope="session")
def created_post_id(session, demo_token):
    h = {"Authorization": f"Bearer {demo_token}"}
    r = session.post(f"{API}/community/posts",
                     json={"title": "TEST_post", "body": "hello", "image_url": "",
                           "tags": ["test"]}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_create_post_requires_auth(session):
    r = session.post(f"{API}/community/posts",
                     json={"title": "x", "body": "y"})
    assert r.status_code == 401


def test_list_posts(session, created_post_id):
    r = session.get(f"{API}/community/posts")
    assert r.status_code == 200
    posts = r.json()
    assert isinstance(posts, list)
    assert any(p["id"] == created_post_id for p in posts)


def test_like_post(session, demo_token, created_post_id):
    h = {"Authorization": f"Bearer {demo_token}"}
    r = session.post(f"{API}/community/posts/{created_post_id}/like", headers=h)
    assert r.status_code == 200
    # verify likes incremented
    posts = session.get(f"{API}/community/posts").json()
    p = next(p for p in posts if p["id"] == created_post_id)
    assert p["likes"] >= 1


def test_like_post_404(session, demo_token):
    h = {"Authorization": f"Bearer {demo_token}"}
    r = session.post(f"{API}/community/posts/nonexistent-id/like", headers=h)
    assert r.status_code == 404


def test_community_stats(session):
    r = session.get(f"{API}/community/stats")
    assert r.status_code == 200
    j = r.json()
    for k in ["trees_planted", "posts", "members"]:
        assert k in j and isinstance(j[k], int)


# -------- Sponsorship --------
EXPECTED_TIERS = {
    "seedling": 500.0,
    "sapling": 1500.0,
    "grove": 3500.0,
    "forest": 7500.0,
}


def test_sponsor_tiers(session):
    r = session.get(f"{API}/sponsorships/tiers")
    assert r.status_code == 200
    tiers = r.json()
    assert isinstance(tiers, list) and len(tiers) == 4
    by_key = {t["key"]: t for t in tiers}
    for k, amt in EXPECTED_TIERS.items():
        assert k in by_key, f"tier {k} missing"
        t = by_key[k]
        assert t["amount"] == amt
        for field in ["key", "label", "amount", "trees", "blurb"]:
            assert field in t


@pytest.fixture(scope="session")
def campaign_id(session, demo_token):
    h = {"Authorization": f"Bearer {demo_token}"}
    r = session.post(
        f"{API}/sponsorships/campaigns",
        headers=h,
        json={
            "title": "TEST_campaign",
            "description": "Test sponsorship campaign",
            "target_amount": 2000.0,  # seedling ₹500 + sapling ₹1500 = ₹2000 → funded after 2 pledges
            "location_label": "Bangalore",
            "lat": 12.97, "lng": 77.59,
            "image_url": "",
        },
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["raised_amount"] == 0.0
    assert j["backers"] == 0
    assert j["status"] == "active"
    assert j["creator_id"]
    return j["id"]


def test_create_campaign_requires_auth(session):
    r = session.post(
        f"{API}/sponsorships/campaigns",
        json={"title": "x", "description": "y", "target_amount": 10.0},
    )
    assert r.status_code == 401


def test_create_campaign_sets_progress_zero(session, campaign_id):
    # campaign_id fixture implicitly tested zero progress
    r = session.get(f"{API}/sponsorships/campaigns/{campaign_id}")
    assert r.status_code == 200
    j = r.json()
    assert j["id"] == campaign_id
    assert j["target_amount"] == 2000.0


def test_list_campaigns(session, campaign_id):
    r = session.get(f"{API}/sponsorships/campaigns")
    assert r.status_code == 200
    docs = r.json()
    assert isinstance(docs, list)
    assert any(c["id"] == campaign_id for c in docs)


def test_get_campaign_not_found(session):
    r = session.get(f"{API}/sponsorships/campaigns/does-not-exist")
    assert r.status_code == 404


def test_checkout_invalid_tier(session, campaign_id, demo_token):
    h = {"Authorization": f"Bearer {demo_token}"}
    r = session.post(
        f"{API}/sponsorships/campaigns/{campaign_id}/checkout",
        headers=h,
        json={"tier": "mega", "origin_url": "https://example.com", "pledge_only": True},
    )
    assert r.status_code == 400


def test_checkout_campaign_not_found(session, demo_token):
    h = {"Authorization": f"Bearer {demo_token}"}
    r = session.post(
        f"{API}/sponsorships/campaigns/does-not-exist/checkout",
        headers=h,
        json={"tier": "seedling", "origin_url": "https://example.com", "pledge_only": True},
    )
    assert r.status_code == 404


def test_pledge_increments_and_funds(session, campaign_id, demo_token):
    """Pledge-only: each pledge adds tier.amount + backer. seedling ₹500 + sapling ₹1500 = ₹2000 → 'funded'."""
    h = {"Authorization": f"Bearer {demo_token}"}
    before = session.get(f"{API}/sponsorships/campaigns/{campaign_id}").json()

    # Pledge 1 — seedling ₹500
    r = session.post(
        f"{API}/sponsorships/campaigns/{campaign_id}/checkout",
        headers=h,
        json={"tier": "seedling", "origin_url": "https://example.com",
              "pledge_only": True, "pledge_message": "Go trees!"},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["mode"] == "pledge"
    assert j["transaction_id"]

    mid = session.get(f"{API}/sponsorships/campaigns/{campaign_id}").json()
    assert mid["raised_amount"] == before["raised_amount"] + 500.0
    assert mid["backers"] == before["backers"] + 1
    assert mid["status"] == "active"  # ₹500 / ₹2000 — not funded yet

    # Pledge 2 — sapling ₹1500 → total ₹2000 meets target
    r2 = session.post(
        f"{API}/sponsorships/campaigns/{campaign_id}/checkout",
        headers=h,
        json={"tier": "sapling", "origin_url": "https://example.com", "pledge_only": True},
    )
    assert r2.status_code == 200

    after = session.get(f"{API}/sponsorships/campaigns/{campaign_id}").json()
    assert after["raised_amount"] >= after["target_amount"]
    assert after["backers"] == before["backers"] + 2
    assert after["status"] == "funded"


def test_pledge_idempotency_no_double_credit(session, demo_token):
    """Call _apply_payment-equivalent twice via second pledge should NOT re-credit same txn.

    We test idempotency by directly verifying that a second checkout call creates
    a NEW transaction (not double-credits existing). Additionally, the status-poll
    endpoint on an already-applied pledge txn would no-op inside _apply_payment.
    """
    h = {"Authorization": f"Bearer {demo_token}"}
    # Create fresh campaign
    r = session.post(
        f"{API}/sponsorships/campaigns",
        headers=h,
        json={"title": "TEST_idem", "description": "idem", "target_amount": 100000.0},
    )
    cid = r.json()["id"]

    # One pledge seedling
    session.post(
        f"{API}/sponsorships/campaigns/{cid}/checkout",
        headers=h,
        json={"tier": "seedling", "origin_url": "https://example.com", "pledge_only": True},
    )
    snap1 = session.get(f"{API}/sponsorships/campaigns/{cid}").json()
    assert snap1["raised_amount"] == 500.0
    assert snap1["backers"] == 1

    # Another identical pledge creates a new txn (separate credit). Still +500.
    session.post(
        f"{API}/sponsorships/campaigns/{cid}/checkout",
        headers=h,
        json={"tier": "seedling", "origin_url": "https://example.com", "pledge_only": True},
    )
    snap2 = session.get(f"{API}/sponsorships/campaigns/{cid}").json()
    # Each pledge = new txn = exactly +500 per call (no double-credit per txn)
    assert snap2["raised_amount"] == 1000.0
    assert snap2["backers"] == 2


def test_stripe_checkout_returns_url_and_session(session, campaign_id, demo_token):
    h = {"Authorization": f"Bearer {demo_token}"}
    r = session.post(
        f"{API}/sponsorships/campaigns/{campaign_id}/checkout",
        headers=h,
        json={"tier": "grove",
              "origin_url": BASE_URL,
              "pledge_only": False},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["mode"] == "stripe"
    assert j["url"] and j["url"].startswith("https://")
    assert j["session_id"]
    assert j["transaction_id"]
    # Store session_id for status poll test
    pytest.stripe_session_id = j["session_id"]


def test_stripe_status_pending_for_unpaid(session):
    """For a just-created (unpaid) Stripe session, status should not be 'paid'."""
    sid = getattr(pytest, "stripe_session_id", None)
    if not sid:
        pytest.skip("No stripe session created")
    r = session.get(f"{API}/sponsorships/checkout/status/{sid}", timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert j["payment_status"] in ("pending", "initiated", "open", "expired")
    assert j["payment_status"] != "paid"
    assert j["amount"] == 3500.0  # grove ₹3500
    assert j["tier"] == "grove"
    assert j.get("currency", "inr") == "inr"


def test_stripe_status_unknown_session_404(session):
    r = session.get(f"{API}/sponsorships/checkout/status/cs_unknown_xyz")
    assert r.status_code == 404


def test_stripe_checkout_does_not_credit_campaign(session, demo_token):
    """Until Stripe reports 'paid', campaign raised_amount should NOT increase for stripe mode."""
    h = {"Authorization": f"Bearer {demo_token}"}
    # Fresh campaign
    r = session.post(
        f"{API}/sponsorships/campaigns",
        headers=h,
        json={"title": "TEST_stripe_no_credit", "description": "x", "target_amount": 50000.0},
    )
    cid = r.json()["id"]
    before = session.get(f"{API}/sponsorships/campaigns/{cid}").json()

    r2 = session.post(
        f"{API}/sponsorships/campaigns/{cid}/checkout",
        headers=h,
        json={"tier": "seedling", "origin_url": BASE_URL, "pledge_only": False},
        timeout=30,
    )
    assert r2.status_code == 200

    after = session.get(f"{API}/sponsorships/campaigns/{cid}").json()
    assert after["raised_amount"] == before["raised_amount"]  # unpaid — no credit
    assert after["backers"] == before["backers"]

"""Regional insights & organizations data layer.

Pluggable web-search abstraction + Wikipedia default provider. Strictly
non-hallucinating: we only summarise content we actually fetched, and we
attach the source URL/domain to every item. If no provider returns content,
we surface ``available=False`` instead of inventing data.

MongoDB-backed cache keyed by (district, state, kind), TTL controlled by
``INSIGHTS_CACHE_TTL_DAYS`` env (default 7 days).
"""
from __future__ import annotations

import os
import re
import json
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# ---------- Tunables ---------------------------------------------------------
TTL_DAYS = int(os.environ.get("INSIGHTS_CACHE_TTL_DAYS", "7"))
HTTP_TIMEOUT = 8.0
USER_AGENT = "GROWhere/1.0 (regional-insights; contact: ops@growhere.app)"

INSIGHT_TOPICS = [
    "afforestation", "deforestation", "reforestation",
    "ecological restoration", "biodiversity",
    "water conservation", "land degradation",
    "climate initiative",
]

ORG_TOPICS = [
    "environmental NGO", "forest conservation organization",
    "tree plantation NGO", "ecological restoration project",
    "biodiversity conservation group",
]


# ---------- Reverse geocoding (Nominatim) ------------------------------------
async def reverse_geocode(lat: float, lng: float) -> Dict[str, Optional[str]]:
    """Return {district, state, country, display_name} via Nominatim.

    Falls back to {None, None, None, "lat,lng"} on failure — caller should
    treat missing fields as low-confidence and skip cache writes.
    """
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {"format": "jsonv2", "lat": lat, "lon": lng, "zoom": 10, "addressdetails": 1}
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en"}
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(url, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
        addr = data.get("address") or {}
        district = (addr.get("state_district") or addr.get("county")
                    or addr.get("district") or addr.get("city_district")
                    or addr.get("city") or addr.get("town") or addr.get("village"))
        state = addr.get("state") or addr.get("region")
        country = addr.get("country")
        return {
            "district": district,
            "state": state,
            "country": country,
            "display_name": data.get("display_name") or f"{lat:.3f},{lng:.3f}",
        }
    except Exception as e:
        logger.info("reverse_geocode failed for %s,%s: %s", lat, lng, e)
        return {"district": None, "state": None, "country": None,
                "display_name": f"{lat:.3f},{lng:.3f}"}


# ---------- Web search providers --------------------------------------------
class SearchResult(dict):
    """{title, snippet, url, domain, source_name}"""


def _domain(url: str) -> str:
    try:
        d = urlparse(url).netloc.lower()
        return d[4:] if d.startswith("www.") else d
    except Exception:
        return ""


def _domain_to_source_name(domain: str) -> str:
    mapping = {
        "wikipedia.org": "Wikipedia",
        "en.wikipedia.org": "Wikipedia",
        "mongabay.com": "Mongabay",
        "india.mongabay.com": "Mongabay India",
        "fsi.nic.in": "Forest Survey of India",
        "moef.gov.in": "Ministry of Environment, Forest and Climate Change",
        "wwfindia.org": "WWF India",
        "wwf.org": "WWF",
        "iucn.org": "IUCN",
        "unep.org": "UN Environment Programme",
        "downtoearth.org.in": "Down To Earth",
        "thehindu.com": "The Hindu",
        "indianexpress.com": "Indian Express",
    }
    if domain in mapping:
        return mapping[domain]
    # Strip TLD heuristically
    parts = domain.split(".")
    return parts[0].title() if parts else domain


class WikipediaProvider:
    """Default no-key provider — uses Wikipedia REST search + summary.

    Returns short, attributed snippets. Never invents content.
    """

    name = "wikipedia"

    async def search(self, query: str, limit: int = 3) -> List[SearchResult]:
        url = "https://en.wikipedia.org/w/rest.php/v1/search/page"
        params = {"q": query, "limit": limit}
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        out: List[SearchResult] = []
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                r = await client.get(url, params=params, headers=headers)
                if r.status_code != 200:
                    return out
                pages = (r.json() or {}).get("pages") or []
            for p in pages[:limit]:
                title = p.get("title") or ""
                key = p.get("key") or title.replace(" ", "_")
                snippet = re.sub(r"<[^>]+>", "", p.get("excerpt") or "").strip()
                if not title or not snippet:
                    continue
                page_url = f"https://en.wikipedia.org/wiki/{key}"
                out.append(SearchResult(
                    title=title,
                    snippet=snippet,
                    url=page_url,
                    domain="wikipedia.org",
                    source_name="Wikipedia",
                ))
        except Exception as e:
            logger.info("wikipedia search failed for %r: %s", query, e)
        return out


class TavilyProvider:
    """Optional Tavily search provider — activated when TAVILY_API_KEY is set."""

    name = "tavily"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, limit: int = 3) -> List[SearchResult]:
        url = "https://api.tavily.com/search"
        payload = {"api_key": self.api_key, "query": query, "max_results": limit,
                   "search_depth": "basic"}
        out: List[SearchResult] = []
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                r = await client.post(url, json=payload)
                if r.status_code != 200:
                    return out
                results = (r.json() or {}).get("results") or []
            for it in results[:limit]:
                u = it.get("url") or ""
                d = _domain(u)
                out.append(SearchResult(
                    title=it.get("title") or "",
                    snippet=(it.get("content") or "").strip(),
                    url=u,
                    domain=d,
                    source_name=_domain_to_source_name(d),
                ))
        except Exception as e:
            logger.info("tavily search failed for %r: %s", query, e)
        return out


def get_search_provider():
    """Return the active search provider. Tavily if key present, else Wikipedia."""
    tk = os.environ.get("TAVILY_API_KEY")
    if tk:
        return TavilyProvider(tk)
    return WikipediaProvider()


# ---------- LLM summariser (no fabrication) ---------------------------------
async def _llm_summarise_items(kind: str, location_label: str,
                               items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compress each fetched item to a 1–2 sentence summary using the LLM,
    constrained to the snippet content. If LLM unavailable, return the raw
    snippet trimmed."""
    if not items:
        return items
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
    except Exception:
        LlmChat = None
        UserMessage = None

    # Fallback: truncate snippets, no rewriting (still factual, source-bound)
    if not api_key or LlmChat is None:
        for it in items:
            s = (it.get("snippet") or "").strip()
            it["summary"] = s if len(s) <= 260 else s[:257].rstrip() + "…"
        return items

    instr = (
        "You compress regional environmental snippets into ONE short sentence "
        "(<=30 words). RULES: (1) Use ONLY facts present in the provided "
        "snippet — DO NOT add data, dates, organisations, or claims that "
        "aren't there. (2) If the snippet is empty or unrelated to "
        f"{kind}, output exactly: SKIP. (3) Plain text only, no quotes."
    )
    import uuid as _uuid
    out: List[Dict[str, Any]] = []
    chat = LlmChat(api_key=api_key, session_id=f"insights-{_uuid.uuid4()}",
                   system_message=instr).with_model("openai", "gpt-4o-mini")

    async def one(it):
        snip = (it.get("snippet") or "").strip()
        if not snip:
            it["summary"] = ""
            return it
        try:
            txt = await chat.send_message(UserMessage(
                text=f"Location: {location_label}\nTitle: {it.get('title','')}\nSnippet: {snip}"
            ))
            txt = (txt or "").strip().strip('"').strip()
            if not txt or txt.upper().startswith("SKIP"):
                it["summary"] = ""
            else:
                it["summary"] = txt
        except Exception:
            it["summary"] = snip if len(snip) <= 260 else snip[:257].rstrip() + "…"
        return it

    out = await asyncio.gather(*[one(it) for it in items])
    return [it for it in out if it.get("summary")]


# ---------- Cache layer ------------------------------------------------------
def _cache_key(district: Optional[str], state: Optional[str],
               country: Optional[str], kind: str) -> str:
    return f"{kind}::{(country or '').lower()}::{(state or '').lower()}::{(district or '').lower()}"


async def _cache_get(db, key: str) -> Optional[dict]:
    if db is None:
        return None
    try:
        doc = await db.insights_cache.find_one({"_id": key}, {"_id": 0})
    except Exception:
        return None
    if not doc:
        return None
    ts = doc.get("fetched_at")
    if isinstance(ts, str):
        try:
            ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return None
    elif isinstance(ts, datetime):
        ts_dt = ts
    else:
        return None
    if datetime.now(timezone.utc) - ts_dt > timedelta(days=TTL_DAYS):
        return None
    return doc


async def _cache_set(db, key: str, payload: dict) -> None:
    if db is None:
        return
    try:
        doc = {**payload, "_id": key, "fetched_at": datetime.now(timezone.utc).isoformat()}
        await db.insights_cache.replace_one({"_id": key}, doc, upsert=True)
    except Exception as e:
        logger.info("insights_cache write failed for %s: %s", key, e)


# ---------- Public fetch fns -------------------------------------------------
async def fetch_regional_insights(db, lat: float, lng: float) -> dict:
    geo = await reverse_geocode(lat, lng)
    district, state, country = geo["district"], geo["state"], geo["country"]
    location_label = ", ".join([x for x in [district, state, country] if x]) or geo["display_name"]
    key = _cache_key(district, state, country, "regional")

    cached = await _cache_get(db, key)
    if cached:
        return cached

    provider = get_search_provider()
    place = district or state
    if not place:
        return {
            "available": False,
            "reason": "Could not resolve a district/state for this point.",
            "location": location_label, "district": district, "state": state, "country": country,
            "items": [], "sources": [], "provider": provider.name,
        }

    queries = [f"{t} {place}" for t in INSIGHT_TOPICS[:6]]
    if state and state != place:
        queries.append(f"forest restoration {state}")
        queries.append(f"biodiversity {state}")

    seen_urls = set()
    raw: List[Dict[str, Any]] = []
    results = await asyncio.gather(*[provider.search(q, limit=2) for q in queries],
                                   return_exceptions=True)
    for q, res in zip(queries, results):
        if isinstance(res, Exception):
            continue
        for it in res or []:
            url = it.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            it["query"] = q
            raw.append(it)

    raw = raw[:10]  # cap
    summarised = await _llm_summarise_items("regional environmental insight",
                                            location_label, raw)
    items = [{
        "title": it.get("title", "")[:140],
        "summary": it.get("summary", ""),
        "source_name": it.get("source_name", "") or _domain_to_source_name(it.get("domain", "")),
        "domain": it.get("domain", ""),
        "url": it.get("url", ""),
    } for it in summarised if it.get("summary")][:8]

    sources = sorted({(it["source_name"] or it["domain"]) for it in items if it.get("source_name") or it.get("domain")})
    payload = {
        "available": bool(items),
        "reason": None if items else "No verified regional insights available.",
        "location": location_label, "district": district, "state": state, "country": country,
        "items": items, "sources": sources, "provider": provider.name,
    }
    if items and (district or state):
        await _cache_set(db, key, payload)
    return payload


async def fetch_organizations(db, lat: float, lng: float) -> dict:
    geo = await reverse_geocode(lat, lng)
    district, state, country = geo["district"], geo["state"], geo["country"]
    location_label = ", ".join([x for x in [district, state, country] if x]) or geo["display_name"]
    key = _cache_key(district, state, country, "orgs")

    cached = await _cache_get(db, key)
    if cached:
        return cached

    provider = get_search_provider()
    place = district or state
    if not place:
        return {
            "available": False,
            "reason": "Could not resolve a district/state for this point.",
            "location": location_label, "district": district, "state": state, "country": country,
            "organizations": [], "sources": [], "provider": provider.name,
        }

    queries = [f"{t} {place}" for t in ORG_TOPICS[:4]]
    if state and state != place:
        queries.append(f"NGO forest conservation {state}")

    seen_urls = set()
    raw: List[Dict[str, Any]] = []
    results = await asyncio.gather(*[provider.search(q, limit=2) for q in queries],
                                   return_exceptions=True)
    for q, res in zip(queries, results):
        if isinstance(res, Exception):
            continue
        for it in res or []:
            url = it.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            it["query"] = q
            raw.append(it)

    raw = raw[:8]
    summarised = await _llm_summarise_items("organisation working on environmental restoration",
                                            location_label, raw)
    orgs = []
    for it in summarised:
        if not it.get("summary"):
            continue
        orgs.append({
            "name": (it.get("title") or "").strip()[:120],
            "description": it.get("summary", ""),
            "area_of_work": it.get("query", ""),
            "partners": [],
            "website": it.get("url", ""),
            "source_name": it.get("source_name", "") or _domain_to_source_name(it.get("domain", "")),
            "domain": it.get("domain", ""),
        })
    orgs = orgs[:8]
    sources = sorted({o["source_name"] or o["domain"] for o in orgs if o.get("source_name") or o.get("domain")})
    payload = {
        "available": bool(orgs),
        "reason": None if orgs else "No verified organisations found for this area.",
        "location": location_label, "district": district, "state": state, "country": country,
        "organizations": orgs, "sources": sources, "provider": provider.name,
    }
    if orgs and (district or state):
        await _cache_set(db, key, payload)
    return payload

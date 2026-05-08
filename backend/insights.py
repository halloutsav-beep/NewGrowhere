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
    """Return {district, state, country, country_code, display_name} via Nominatim.

    Falls back to None fields on failure — caller should treat missing
    fields as low-confidence and skip cache writes.
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
        cc = (addr.get("country_code") or "").upper() or None
        return {
            "district": district,
            "state": state,
            "country": country,
            "country_code": cc,
            "display_name": data.get("display_name") or f"{lat:.3f},{lng:.3f}",
        }
    except Exception as e:
        logger.info("reverse_geocode failed for %s,%s: %s", lat, lng, e)
        return {"district": None, "state": None, "country": None,
                "country_code": None,
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


# ---------- Google News RSS (recent articles, no API key) -------------------
import xml.etree.ElementTree as _ET
from email.utils import parsedate_to_datetime as _parsedate

# Domains we boost / drop for "trusted environmental journalism" feel
_TRUSTED_DOMAINS = {
    "mongabay.com", "india.mongabay.com",
    "downtoearth.org.in",
    "fsi.nic.in", "moef.gov.in",
    "wwfindia.org", "wwf.org",
    "unep.org",
    "thehindu.com", "indianexpress.com", "hindustantimes.com",
    "thethirdpole.net", "ndtv.com", "scroll.in", "thequint.com",
    "reuters.com", "bbc.com", "bbc.co.uk",
}
_BLOCKED_DOMAINS = {"wikipedia.org", "en.wikipedia.org"}


def _strip_source_suffix(title: str) -> str:
    # Google News appends " - Source Name" to titles; strip the last suffix.
    m = re.match(r"^(.*) - ([^-]+)$", title.strip())
    return (m.group(1).strip() if m else title.strip())[:200]


async def fetch_google_news(query: str, limit: int = 6,
                            country_hint: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch recent items from Google News RSS for a query.

    Returns raw items with title, snippet, url, domain, source_name, published.
    """
    gl = "IN" if (country_hint and country_hint.lower() == "india") else "US"
    hl = "en-IN" if gl == "IN" else "en-US"
    ceid = f"{gl}:en"
    url = "https://news.google.com/rss/search"
    params = {"q": query, "hl": hl, "gl": gl, "ceid": ceid}
    headers = {"User-Agent": USER_AGENT}
    out: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            r = await client.get(url, params=params, headers=headers)
            if r.status_code != 200 or not r.text:
                return out
        root = _ET.fromstring(r.text)
        channel = root.find("channel")
        if channel is None:
            return out
        for item in channel.findall("item")[: limit * 3]:
            link_el = item.find("link")
            title_el = item.find("title")
            desc_el = item.find("description")
            pub_el = item.find("pubDate")
            src_el = item.find("source")
            link = (link_el.text or "").strip() if link_el is not None else ""
            title = (title_el.text or "").strip() if title_el is not None else ""
            if not link or not title:
                continue
            # Strip HTML from description
            snippet = re.sub(r"<[^>]+>", " ", desc_el.text or "").strip() if desc_el is not None else ""
            snippet = re.sub(r"\s+", " ", snippet)
            published = None
            if pub_el is not None and pub_el.text:
                try:
                    dt = _parsedate(pub_el.text)
                    if dt:
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        published = dt.astimezone(timezone.utc).isoformat()
                except Exception:
                    pass
            source_name = (src_el.text.strip() if src_el is not None and src_el.text else "")
            source_url = (src_el.get("url") if src_el is not None else "") or ""
            domain = _domain(source_url) or _domain(link)
            if domain in _BLOCKED_DOMAINS:
                continue
            out.append({
                "title": _strip_source_suffix(title),
                "snippet": snippet,
                "url": link,
                "domain": domain,
                "source_name": source_name or _domain_to_source_name(domain),
                "published": published,
            })
    except Exception as e:
        logger.info("google news rss failed for %r: %s", query, e)
    return out[: limit * 3]


# ---------- Google News redirect resolver -----------------------------------
# Cache resolved URLs in memory (process-local) — Google news URLs are stable
# enough to cache, and we re-fetch the cluster anyway every TTL.
_GN_URL_CACHE: Dict[str, str] = {}
_GN_URL_CACHE_MAX = 2000


def _resolve_google_news_url_sync(url: str) -> Optional[str]:
    """Decode a Google News rss/articles URL into the publisher URL.

    Uses the ``googlenewsdecoder`` package which performs the encrypted
    handshake against Google's servers. Returns None on failure.
    """
    try:
        from googlenewsdecoder import gnewsdecoder
        out = gnewsdecoder(url, interval=1)
        if isinstance(out, dict) and out.get("status") and out.get("decoded_url"):
            return out["decoded_url"]
    except Exception as e:
        logger.info("gnewsdecoder failed for %s: %s", url[:60], e)
    return None


async def resolve_google_news_urls(items: List[Dict[str, Any]],
                                   max_concurrency: int = 5,
                                   timeout_per: float = 5.0) -> List[Dict[str, Any]]:
    """For each news item with a news.google.com URL, resolve to the
    publisher's article URL in parallel. Updates ``url`` and ``domain``
    in-place. Items that fail resolution keep their Google URL but get
    the publisher's homepage URL from ``source_url`` if available."""
    sem = asyncio.Semaphore(max_concurrency)

    async def _one(it: Dict[str, Any]):
        url = it.get("url") or ""
        if "news.google.com" not in url:
            return
        if url in _GN_URL_CACHE:
            real = _GN_URL_CACHE[url]
        else:
            async with sem:
                try:
                    real = await asyncio.wait_for(
                        asyncio.to_thread(_resolve_google_news_url_sync, url),
                        timeout=timeout_per,
                    )
                except (asyncio.TimeoutError, Exception):
                    real = None
            if real:
                if len(_GN_URL_CACHE) >= _GN_URL_CACHE_MAX:
                    _GN_URL_CACHE.clear()
                _GN_URL_CACHE[url] = real
        if real:
            it["url"] = real
            it["domain"] = _domain(real) or it.get("domain", "")
            # Prefer publisher domain for source name when generic
            if not it.get("source_name") or it["source_name"].lower() == "google news":
                it["source_name"] = _domain_to_source_name(it["domain"])

    await asyncio.gather(*[_one(it) for it in items], return_exceptions=True)
    return items


# ---------- NGOBase.org scraper ---------------------------------------------
# Country code → page suffix (the slug after /cwa/<CC>/ENC/ is just used
# for SEO; any non-empty value works). We ping a stable URL.
_NGOBASE_BASE = "https://ngobase.org"


async def fetch_ngobase_orgs(country_code: Optional[str],
                             district: Optional[str] = None,
                             state: Optional[str] = None,
                             limit: int = 8) -> List[Dict[str, Any]]:
    """Scrape NGOBase.org's country-level Environment & Climate listing.

    Returns a list of {name, profile_url, locations[], work_areas[]}.
    Filters by district / state name match where possible. Never invents
    partnerships or descriptions — only fields actually present on the
    listing card.
    """
    if not country_code:
        return []
    url = f"{_NGOBASE_BASE}/cwa/{country_code.upper()}/ENC/x"
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}
    out: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            if r.status_code != 200 or not r.text:
                return out
            html = r.text
    except Exception as e:
        logger.info("ngobase fetch failed for %s: %s", country_code, e)
        return out

    blocks = re.findall(
        r'<div[^>]*class="my_border ngo_listing_div"[^>]*>(.*?)</div>\s*</div>\s*</div>',
        html, re.S,
    )
    district_l = (district or "").strip().lower()
    state_l = (state or "").strip().lower()

    matched: List[Dict[str, Any]] = []
    fallback: List[Dict[str, Any]] = []
    for b in blocks:
        name_m = re.search(r'itemprop="name"[\s\S]*?<a[^>]*>(.*?)</a>', b, re.S)
        link_m = re.search(r'<a\s+href="(/profile/\d+|https?://ngobase\.org/profile/\d+)"', b)
        locs = [l.strip() for l in re.findall(r'class="listing_locations"[^>]*>([^<]+)<', b)]
        works = [w.strip() for w in re.findall(
            r'class="ngo_listing_work_area_li"[^>]*>(?:\s*<a[^>]*>)?([^<]+)', b
        )]
        # Dedup work_areas while preserving order
        seen = set(); works_unique = []
        for w in works:
            wl = w.lower()
            if wl in seen or not w:
                continue
            seen.add(wl); works_unique.append(w)
        name = (name_m.group(1).strip() if name_m else "")
        if not name:
            continue
        profile = link_m.group(1) if link_m else ""
        if profile.startswith("/"):
            profile = _NGOBASE_BASE + profile
        locs_l = [l.lower() for l in locs]
        item = {
            "name": name[:120],
            "profile_url": profile,
            "locations": locs[:3],
            "work_areas": works_unique[:4],
        }
        is_match = False
        if district_l and any(district_l in l for l in locs_l):
            is_match = True
        elif state_l and any(state_l in l for l in locs_l):
            is_match = True
        (matched if is_match else fallback).append(item)

    # Prefer locality-matching first, then fall back to country-level entries.
    out = (matched + fallback)[:limit]
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
    """Organizations relevant to the area, sourced from NGOBase.org.

    We never invent NGOs or partnerships — fields are only filled when
    NGOBase actually exposed them on the card. The optional Wikipedia /
    Tavily provider is used only as a soft fallback for areas where
    NGOBase has no entries (rare).
    """
    geo = await reverse_geocode(lat, lng)
    district, state, country = geo["district"], geo["state"], geo["country"]
    country_code = geo.get("country_code")
    location_label = ", ".join([x for x in [district, state, country] if x]) or geo["display_name"]
    key = _cache_key(district, state, country, "orgs")

    cached = await _cache_get(db, key)
    if cached:
        return cached

    # ---- Primary: NGOBase ---------------------------------------------------
    ngo_items = await fetch_ngobase_orgs(country_code, district=district,
                                         state=state, limit=8)
    organizations: List[Dict[str, Any]] = []
    for it in ngo_items:
        works = it.get("work_areas") or []
        locs = it.get("locations") or []
        # Description is intentionally short, derived only from listing fields.
        if works and locs:
            description = f"Works on {', '.join(works[:3])} — based in {', '.join(locs[:2])}."
        elif works:
            description = f"Works on {', '.join(works[:3])}."
        elif locs:
            description = f"Based in {', '.join(locs[:2])}."
        else:
            description = "Listed environmental NGO."
        organizations.append({
            "name": it["name"],
            "description": description,
            "area_of_work": ", ".join(works[:3]) if works else "Environment & Climate",
            "partners": [],
            "website": it.get("profile_url", ""),
            "source_name": "NGOBase",
            "domain": "ngobase.org",
        })

    # ---- Fallback: search-provider sweep (Wikipedia or Tavily) -------------
    if not organizations:
        provider = get_search_provider()
        place = district or state
        if place:
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
            summarised = await _llm_summarise_items(
                "organisation working on environmental restoration",
                location_label, raw)
            for it in summarised:
                if not it.get("summary"):
                    continue
                organizations.append({
                    "name": (it.get("title") or "").strip()[:120],
                    "description": it.get("summary", ""),
                    "area_of_work": it.get("query", ""),
                    "partners": [],
                    "website": it.get("url", ""),
                    "source_name": it.get("source_name", "")
                                    or _domain_to_source_name(it.get("domain", "")),
                    "domain": it.get("domain", ""),
                })

    organizations = organizations[:8]
    sources = sorted({o["source_name"] or o["domain"] for o in organizations
                      if o.get("source_name") or o.get("domain")})
    payload = {
        "available": bool(organizations),
        "reason": None if organizations else "No verified organisations found for this area.",
        "location": location_label, "district": district, "state": state, "country": country,
        "organizations": organizations, "sources": sources,
        "provider": "ngobase" if any(o["source_name"] == "NGOBase" for o in organizations) else "fallback",
    }
    if organizations and (district or state):
        await _cache_set(db, key, payload)
    return payload



# ---------- News (Google News RSS — recent articles) ------------------------
NEWS_TOPICS = [
    "afforestation", "deforestation", "reforestation",
    "biodiversity", "ecological restoration",
    "forest conservation", "tree plantation",
]

# Recency window — drop items older than this. Override with NEWS_MAX_AGE_DAYS.
NEWS_MAX_AGE_DAYS = int(os.environ.get("NEWS_MAX_AGE_DAYS", "30"))


def _is_recent(published_iso: Optional[str]) -> bool:
    if not published_iso:
        return False
    try:
        dt = datetime.fromisoformat(published_iso.replace("Z", "+00:00"))
    except Exception:
        return False
    return (datetime.now(timezone.utc) - dt) <= timedelta(days=NEWS_MAX_AGE_DAYS)


def _trust_rank(domain: str) -> int:
    if not domain:
        return 5
    if domain in _TRUSTED_DOMAINS:
        return 0
    # subdomain match (e.g. india.mongabay.com)
    for d in _TRUSTED_DOMAINS:
        if domain.endswith("." + d) or domain == d:
            return 1
    return 3


# ---------- Direct-publisher RSS aggregator (replaces Google News) ----------
# Adapter pattern: each source has its own feed URL(s) and a "regional"
# bias hint. Failures in one source never break the whole pipeline.
RSS_USER_AGENT = (
    "Mozilla/5.0 (compatible; GROWhereBot/1.0; +https://growhere.app/bot)"
)

# country-iso → list of feed adapters
NEWS_FEEDS: Dict[str, List[Dict[str, Any]]] = {
    "IN": [
        {"name": "Mongabay India", "url": "https://india.mongabay.com/feed/", "domain": "india.mongabay.com"},
        {"name": "Down To Earth", "url": "https://www.downtoearth.org.in/feed", "domain": "downtoearth.org.in"},
        {"name": "The Third Pole", "url": "https://www.thethirdpole.net/feed/", "domain": "thethirdpole.net"},
        {"name": "The Hindu — Energy & Environment", "url": "https://www.thehindu.com/sci-tech/energy-and-environment/feeder/default.rss", "domain": "thehindu.com"},
        {"name": "The Indian Express — India", "url": "https://indianexpress.com/section/india/feed/", "domain": "indianexpress.com"},
        {"name": "The Indian Express — Cities", "url": "https://indianexpress.com/section/cities/feed/", "domain": "indianexpress.com"},
    ],
    # Generic / default — Mongabay global & TTP work everywhere; UN feed is
    # often XML-malformed so we leave it out for now (graceful skip).
    "*": [
        {"name": "Mongabay", "url": "https://news.mongabay.com/feed/", "domain": "news.mongabay.com"},
        {"name": "The Third Pole", "url": "https://www.thethirdpole.net/feed/", "domain": "thethirdpole.net"},
    ],
}

# Topic keywords used both for relevance scoring and as a soft topical filter.
NEWS_TOPIC_KEYWORDS = [
    "afforestation", "deforestation", "reforestation",
    "biodiversity", "ecological restoration", "ecology",
    "forest", "wildlife", "wetland", "mangrove",
    "tree plantation", "conservation", "nature", "ngt",
    "climate", "ecosystem", "habitat", "sanctuary",
    "tiger reserve", "national park", "green cover",
]


async def _fetch_rss_items(adapter: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Fetch a single RSS feed → list of normalised items.
    Returns [] on any error so one bad feed never breaks the pipeline."""
    out: List[Dict[str, Any]] = []
    headers = {"User-Agent": RSS_USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml"}
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            r = await client.get(adapter["url"], headers=headers)
            if r.status_code != 200 or not r.text:
                return out
            text = r.text
        root = _ET.fromstring(text)
        channel = root.find("channel") or root  # tolerate both rss & atom-ish
        items = channel.findall("item") if channel is not None else []
        for it in items:
            link = (it.findtext("link") or "").strip()
            title = (it.findtext("title") or "").strip()
            if not link or not title:
                continue
            desc = it.findtext("description") or ""
            desc = re.sub(r"<[^>]+>", " ", desc)
            desc = re.sub(r"\s+", " ", desc).strip()
            pub_raw = (it.findtext("pubDate")
                       or it.findtext("{http://purl.org/dc/elements/1.1/}date")
                       or "")
            published = None
            if pub_raw:
                try:
                    dt = _parsedate(pub_raw)
                    if dt:
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        published = dt.astimezone(timezone.utc).isoformat()
                except Exception:
                    pass
            domain = _domain(link) or adapter.get("domain") or ""
            out.append({
                "title": title[:200],
                "snippet": desc[:600],
                "url": link,
                "domain": domain,
                "source_name": adapter["name"],
                "published": published,
            })
    except Exception as e:
        logger.info("rss fetch failed [%s]: %s", adapter.get("name"), e)
    return out


def _score_relevance(item: Dict[str, Any], district: Optional[str],
                     state: Optional[str], country: Optional[str]) -> int:
    """Lightweight regional + topical relevance score.

    +4 district-name hit, +2 state, +1 country, +1 per topic keyword (cap +3),
    +1 trusted-domain bonus. Items below threshold are dropped.
    """
    text = f"{item.get('title','')} {item.get('snippet','')}".lower()
    if not text.strip():
        return 0
    score = 0
    if district and district.lower() in text:
        score += 4
    if state and state.lower() in text:
        score += 2
    if country and country.lower() in text:
        score += 1
    topic_hits = sum(1 for kw in NEWS_TOPIC_KEYWORDS if kw in text)
    score += min(topic_hits, 3)
    if (item.get("domain") or "") in _TRUSTED_DOMAINS:
        score += 1
    return score


async def fetch_news(db, lat: float, lng: float) -> dict:
    """Recent regional environmental news, sourced directly from publisher
    RSS feeds. No Google News redirects. Each source failing in isolation
    never breaks the tab."""
    geo = await reverse_geocode(lat, lng)
    district, state, country = geo["district"], geo["state"], geo["country"]
    country_code = (geo.get("country_code") or "").upper()
    location_label = ", ".join([x for x in [district, state, country] if x]) or geo["display_name"]
    key = _cache_key(district, state, country, "news")

    cached = await _cache_get(db, key)
    if cached:
        return cached

    if not (district or state):
        return {
            "available": False,
            "reason": "Could not resolve a district/state for this point.",
            "location": location_label, "district": district, "state": state, "country": country,
            "items": [], "sources": [], "provider": "rss_aggregator",
        }

    adapters = NEWS_FEEDS.get(country_code) or NEWS_FEEDS["*"]
    raw_lists = await asyncio.gather(
        *[_fetch_rss_items(a) for a in adapters],
        return_exceptions=True,
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=NEWS_MAX_AGE_DAYS)
    seen_urls: set = set()
    seen_titles: set = set()
    candidates: List[Dict[str, Any]] = []
    for res in raw_lists:
        if isinstance(res, Exception) or not res:
            continue
        for it in res:
            url = it.get("url") or ""
            if not url or url in seen_urls:
                continue
            if it.get("domain") in _BLOCKED_DOMAINS:
                continue
            # Recency filter (must have a date and be within window).
            pub = it.get("published")
            if not pub:
                continue
            try:
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except Exception:
                continue
            if dt < cutoff:
                continue
            # Topical + regional relevance — drop if irrelevant.
            score = _score_relevance(it, district, state, country)
            if score < 2:
                continue
            # Title-fuzzy dedupe
            t_norm = re.sub(r"[^a-z0-9]+", "", it.get("title", "").lower())[:60]
            if t_norm and t_norm in seen_titles:
                continue
            seen_urls.add(url)
            if t_norm:
                seen_titles.add(t_norm)
            it["score"] = score
            it["_dt"] = dt
            candidates.append(it)

    # Sort: score desc, then recency desc.
    candidates.sort(key=lambda x: (-(x.get("score", 0)), -x["_dt"].timestamp()))
    candidates = candidates[:14]
    for c in candidates:
        c.pop("_dt", None)

    # LLM summariser (no fabrication — see _llm_summarise_items).
    summarised = await _llm_summarise_items(
        "recent environmental news", location_label, candidates,
    )

    final: List[Dict[str, Any]] = []
    for it in summarised:
        if not it.get("summary"):
            continue
        final.append({
            "title": it.get("title", "")[:220],
            "summary": it.get("summary", ""),
            "source_name": it.get("source_name", "")
                            or _domain_to_source_name(it.get("domain", "")),
            "domain": it.get("domain", ""),
            "url": it.get("url", ""),
            "published": it.get("published"),
        })
    final = final[:10]

    sources = sorted({(it["source_name"] or it["domain"]) for it in final
                      if it.get("source_name") or it.get("domain")})
    payload = {
        "available": bool(final),
        "reason": None if final else "No recent regional environmental news found.",
        "location": location_label, "district": district, "state": state, "country": country,
        "items": final, "sources": sources, "provider": "rss_aggregator",
    }
    if final:
        await _cache_set(db, key, payload)
    return payload

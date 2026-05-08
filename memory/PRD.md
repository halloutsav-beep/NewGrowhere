# GROWhere — PRD (incremental)

## Latest changes (2026-01)
- Suitability panel converted to 3 tabs: Overview / Regional / Organizations
- New backend endpoints:
  - POST /api/insights/regional
  - POST /api/insights/organizations
- Pluggable web-search provider (default: Wikipedia REST; Tavily activated when TAVILY_API_KEY env is set)
- LLM (Emergent key, gpt-4o-mini) used ONLY to compress fetched snippets into 1 sentence; instruction-bound to never add facts not in the snippet
- MongoDB cache `insights_cache` keyed by (kind, country, state, district), TTL 7 days (INSIGHTS_CACHE_TTL_DAYS)
- Restricted-zone circles no longer rendered on map (logic still computed server-side)
- Lazy fetch on tab open; in-memory per-coord cache to make tab switching free

## Files touched
- backend/insights.py (new)
- backend/server.py (added insights endpoints + import)
- frontend/src/components/SuitabilityTabs.jsx (new)
- frontend/src/pages/MapDashboard.jsx (tabs wrapping + restricted-zone filter)

## Backlog / Future
- Plug Tavily/Brave key for richer non-Wikipedia sources (gov, NGO, news)
- Fuzzy district aliasing
- Per-source quality weighting

import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Leaf, Map as MapIcon, Search, X, Loader2, MapPin } from 'lucide-react';

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

// Nominatim suggestion -> a clean primary + secondary label.
function splitName(displayName = '') {
  const [primary, ...rest] = displayName.split(',');
  return {
    primary: (primary || '').trim(),
    secondary: rest.join(',').trim(),
  };
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

export default function Navbar() {
  const loc = useLocation();
  const navigate = useNavigate();

  const [q, setQ] = useState('');
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false);

  // Suggestion state (shared by desktop + mobile dropdowns)
  const [suggestions, setSuggestions] = useState([]);
  const [suggLoading, setSuggLoading] = useState(false);
  const [showSugg, setShowSugg] = useState(false);
  const [activeIdx, setActiveIdx] = useState(-1);

  const debounceRef = useRef(null);
  const abortRef = useRef(null);
  const desktopWrapRef = useRef(null);
  const mobileWrapRef = useRef(null);

  /* ------------ suggestion fetching ------------ */
  const fetchSuggestions = (val) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (abortRef.current) {
      try { abortRef.current.abort(); } catch (_) { /* noop */ }
    }
    const trimmed = (val || '').trim();
    if (trimmed.length < 2) {
      setSuggestions([]);
      setSuggLoading(false);
      return;
    }
    setSuggLoading(true);
    debounceRef.current = setTimeout(async () => {
      const ac = new AbortController();
      abortRef.current = ac;
      try {
        // Nominatim: free, no key. addressdetails=0 keeps response small.
        const url = `https://nominatim.openstreetmap.org/search?format=json&addressdetails=0&limit=5&q=${encodeURIComponent(trimmed)}`;
        const res = await fetch(url, {
          signal: ac.signal,
          headers: { 'Accept': 'application/json' },
        });
        if (!res.ok) throw new Error('http ' + res.status);
        const data = await res.json();
        setSuggestions(Array.isArray(data) ? data : []);
        setActiveIdx(-1);
      } catch (e) {
        if (e.name !== 'AbortError') {
          // Silent fallback: empty list. Submit-Enter still works (geocodes on /map).
          setSuggestions([]);
        }
      } finally {
        setSuggLoading(false);
      }
    }, 280);
  };

  const onChange = (e) => {
    const v = e.target.value;
    setQ(v);
    setShowSugg(true);
    fetchSuggestions(v);
  };

  /* ------------ navigation / submit ------------ */
  const goToCoords = (name, lat, lng) => {
    const params = new URLSearchParams();
    if (name) params.set('q', name);
    if (Number.isFinite(lat) && Number.isFinite(lng)) {
      params.set('lat', String(lat));
      params.set('lng', String(lng));
    }
    navigate(`/map?${params.toString()}`);
  };

  const selectSuggestion = (s) => {
    const lat = parseFloat(s.lat);
    const lng = parseFloat(s.lon);
    const { primary } = splitName(s.display_name);
    const name = primary || (q || '').trim();
    setQ(name);
    setShowSugg(false);
    setSuggestions([]);
    setMobileSearchOpen(false);
    goToCoords(name, lat, lng);
  };

  const handleSearch = (e) => {
    e.preventDefault();
    const value = (q || '').trim();
    if (!value) return;
    if (showSugg && activeIdx >= 0 && suggestions[activeIdx]) {
      selectSuggestion(suggestions[activeIdx]);
      return;
    }
    // No suggestion picked: fall back to free-text search (MapDashboard will geocode).
    setShowSugg(false);
    setMobileSearchOpen(false);
    navigate(`/map?q=${encodeURIComponent(value)}`);
  };

  const handleKeyDown = (e) => {
    if (!showSugg) {
      if (e.key === 'ArrowDown' && suggestions.length > 0) {
        setShowSugg(true);
      }
      return;
    }
    if (suggestions.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, -1));
    } else if (e.key === 'Escape') {
      setShowSugg(false);
    }
  };

  /* ------------ click outside to close ------------ */
  useEffect(() => {
    if (!showSugg) return;
    const onDocClick = (ev) => {
      const t = ev.target;
      if (
        (desktopWrapRef.current && desktopWrapRef.current.contains(t)) ||
        (mobileWrapRef.current && mobileWrapRef.current.contains(t))
      ) return;
      setShowSugg(false);
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [showSugg]);

  /* ------------ rendering helpers ------------ */
  const linkCls = (path) => `text-sm font-semibold transition-colors ${
    loc.pathname === path ? 'text-forest-700' : 'text-forest-900/70 hover:text-forest-700'
  }`;

  const renderDropdown = (idPrefix) => {
    const trimmed = (q || '').trim();
    const showEmpty = showSugg && trimmed.length >= 2 && !suggLoading && suggestions.length === 0;
    const showList = showSugg && suggestions.length > 0;
    if (!showList && !showEmpty && !(showSugg && suggLoading && trimmed.length >= 2)) return null;

    return (
      <div
        className="absolute left-0 right-0 top-full mt-2 bg-white border border-[#E3DFD5] rounded-2xl shadow-lg overflow-hidden z-[60]"
        role="listbox"
        data-testid={`${idPrefix}-suggestions`}
      >
        {suggLoading && trimmed.length >= 2 && (
          <div className="flex items-center gap-2 px-4 py-3 text-xs text-bark">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> Searching…
          </div>
        )}
        {showEmpty && (
          <div className="px-4 py-3 text-xs text-bark">No results for "{trimmed}"</div>
        )}
        {showList && suggestions.map((s, i) => {
          const { primary, secondary } = splitName(s.display_name);
          const active = i === activeIdx;
          return (
            <button
              type="button"
              key={`${s.place_id || s.osm_id || i}-${i}`}
              role="option"
              aria-selected={active}
              onMouseEnter={() => setActiveIdx(i)}
              onMouseDown={(ev) => { ev.preventDefault(); selectSuggestion(s); }}
              className={`w-full flex items-start gap-3 px-4 py-2.5 text-left transition-colors ${active ? 'bg-bonewarm' : 'hover:bg-bonewarm/70'}`}
              data-testid={`${idPrefix}-suggestion-${i}`}
            >
              <MapPin className="w-4 h-4 text-forest-700 mt-0.5 shrink-0" />
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold text-forest-900 truncate">{primary || s.display_name}</span>
                {secondary && (
                  <span className="block text-xs text-bark truncate">{secondary}</span>
                )}
              </span>
            </button>
          );
        })}
      </div>
    );
  };

  return (
    <header
      className="sticky top-0 z-40 bg-bone/85 backdrop-blur-md border-b border-[#E3DFD5]"
      data-testid="site-header"
    >
      <div className="container-narrow flex items-center justify-between gap-4 py-4">
        {/* Logo */}
<Link to="/" className="flex items-center gap-2 shrink-0" data-testid="nav-logo">
  <div className="w-9 h-9 rounded-full bg-forest-700 grid place-items-center">
    <Leaf className="w-5 h-5 text-bone" strokeWidth={2.4} />
  </div>
  <div className="flex flex-col">
    <span className="font-serif text-2xl text-forest-900 tracking-tight leading-tight">GROWhere</span>
    <span className="text-[10px] text-bark/60 leading-none tracking-wide">An experiment for a greener world</span>
  </div>
</Link>
        
        {/* Floating search bar (desktop / tablet) */}
        <div ref={desktopWrapRef} className="hidden sm:block flex-1 max-w-md mx-2 lg:mx-6 relative">
          <form
            onSubmit={handleSearch}
            className="flex items-center bg-white/80 hover:bg-white focus-within:bg-white focus-within:ring-2 focus-within:ring-forest-700/30 border border-[#E3DFD5] rounded-full px-4 py-2 gap-2 shadow-sm transition"
            data-testid="header-search-form"
          >
            <Search className="w-4 h-4 text-bark shrink-0" />
            <input
              type="text"
              value={q}
              onChange={onChange}
              onKeyDown={handleKeyDown}
              onFocus={() => { if (suggestions.length > 0) setShowSugg(true); }}
              placeholder="Search a place, city or pincode…"
              aria-label="Search"
              autoComplete="off"
              className="bg-transparent text-sm flex-1 outline-none placeholder:text-bark/60 text-forest-900 min-w-0"
              data-testid="header-search-input"
            />
            {suggLoading && <Loader2 className="w-3.5 h-3.5 text-bark animate-spin shrink-0" />}
            {q && !suggLoading && (
              <button
                type="button"
                onClick={() => { setQ(''); setSuggestions([]); setShowSugg(false); }}
                className="text-bark/70 hover:text-forest-900 shrink-0"
                aria-label="Clear search"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </form>
          {renderDropdown('desktop')}
        </div>

        {/* Right side */}
        <div className="flex items-center gap-2 sm:gap-4 shrink-0">
          {/* Mobile search toggle */}
          <button
            type="button"
            onClick={() => setMobileSearchOpen((v) => !v)}
            className="sm:hidden w-10 h-10 grid place-items-center rounded-full border border-[#E3DFD5] bg-white/80 text-forest-900 hover:bg-white transition"
            aria-label={mobileSearchOpen ? 'Close search' : 'Open search'}
            data-testid="mobile-search-toggle"
          >
            {mobileSearchOpen ? <X className="w-4 h-4" /> : <Search className="w-4 h-4" />}
          </button>

          {/* Single primary CTA (renamed: "Find Land" with map icon) */}
          <Link
            to="/map"
            className={`btn-primary text-sm py-2 px-4 sm:px-5 ${loc.pathname === '/map' ? 'ring-2 ring-forest-700/30' : ''}`}
            data-testid="nav-cta"
          >
            <MapIcon className="w-4 h-4" />
            Find Land
          </Link>
        </div>
      </div>

      {/* Mobile expanded search */}
      {mobileSearchOpen && (
        <div className="sm:hidden border-t border-[#E3DFD5] bg-bone/95 backdrop-blur-md">
          <div ref={mobileWrapRef} className="container-narrow py-3 relative">
            <form
              onSubmit={handleSearch}
              data-testid="mobile-search-form"
            >
              <div className="flex items-center bg-white border border-[#E3DFD5] rounded-full px-4 py-2 gap-2 shadow-sm focus-within:ring-2 focus-within:ring-forest-700/30">
                <Search className="w-4 h-4 text-bark shrink-0" />
                <input
                  type="text"
                  autoFocus
                  value={q}
                  onChange={onChange}
                  onKeyDown={handleKeyDown}
                  onFocus={() => { if (suggestions.length > 0) setShowSugg(true); }}
                  placeholder="Search a place, city or pincode…"
                  aria-label="Search"
                  autoComplete="off"
                  className="bg-transparent text-sm flex-1 outline-none placeholder:text-bark/60 text-forest-900 min-w-0"
                  data-testid="mobile-search-input"
                />
                {suggLoading && <Loader2 className="w-3.5 h-3.5 text-bark animate-spin shrink-0" />}
                {q && !suggLoading && (
                  <button
                    type="button"
                    onClick={() => { setQ(''); setSuggestions([]); setShowSugg(false); }}
                    className="text-bark/70 hover:text-forest-900 shrink-0"
                    aria-label="Clear search"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </form>
            {renderDropdown('mobile')}
          </div>
        </div>
      )}
    </header>
  );
}

import { useEffect, useMemo, useRef, useState } from 'react';
import { MapContainer, TileLayer, Circle, Marker, Popup, useMap, useMapEvents, LayersControl } from 'react-leaflet';
import L from 'leaflet';
import { useSearchParams } from 'react-router-dom';
import { api } from '../lib/api';
import { toast } from 'sonner';
import {
  Locate, Layers as LayersIcon, Sparkles, Droplets, Trees, ShieldCheck, X,
  Info, Loader2, ChevronUp, ChevronDown, ListFilter, MapPin, Shrub, Sprout, AlertTriangle,
  Copy, Bookmark, BookmarkCheck
} from 'lucide-react';

// Fix Leaflet default icon
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

const ZONE_STYLES = {
  high_potential:        { color: '#4A7C59', fill: '#4A7C59', label: 'High potential', desc: 'Plant freely', icon: Trees },
  moderate_permission_needed: { color: '#D4A373', fill: '#D4A373', label: 'Permission needed', desc: 'Coordinate with owners', icon: ShieldCheck },
  restricted_protected:  { color: '#C16645', fill: '#C16645', label: 'Restricted', desc: 'Protected — do not plant', icon: X },
};

function FlyTo({ pos }) {
  const map = useMap();
  const lat = pos ? pos[0] : null;
  const lng = pos ? pos[1] : null;
  useEffect(() => {
    if (lat != null && lng != null) map.flyTo([lat, lng], 14, { duration: 1.2 });
  }, [lat, lng, map]);
  return null;
}

function ClickHandler({ onPick }) {
  useMapEvents({ click(e) { onPick([e.latlng.lat, e.latlng.lng]); } });
  return null;
}

export default function MapDashboard() {
  const [center, setCenter] = useState([28.6139, 77.2090]); // Delhi default
  const [picked, setPicked] = useState(null);
  const [zones, setZones] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [recommendation, setRecommendation] = useState(null);
  const [recoBusy, setRecoBusy] = useState(false);
  const [showLayers, setShowLayers] = useState({ suitability: true });
  const [panelOpen, setPanelOpen] = useState(true);
  const [layersOpen, setLayersOpen] = useState(false);
  const [zoneFilter, setZoneFilter] = useState('all');
  const [allowedListOpen, setAllowedListOpen] = useState(false);
  const [bookmarks, setBookmarks] = useState(() => {
    try { return JSON.parse(localStorage.getItem('growhere:bookmarks') || '[]'); } catch { return []; }
  });
  const [bookmarksOpen, setBookmarksOpen] = useState(false);
  const inflightRef = useRef(0);
  const lastSearchedRef = useRef(null);
  // Client-side cache for /analysis/suitability + /recommendations/species.
  // Keyed by lat/lng rounded to 4 decimals (~11 m) — matches backend determinism.
  // Seeded from localStorage so cache survives reloads & tab-switches.
  const analysisCacheRef = useRef(new Map(
    (() => { try { return JSON.parse(localStorage.getItem('growhere:analysisCache') || '[]'); } catch { return []; } })()
  ));
  const recoCacheRef = useRef(new Map(
    (() => { try { return JSON.parse(localStorage.getItem('growhere:recoCache') || '[]'); } catch { return []; } })()
  ));
  const pickDebounceRef = useRef(null);
  const _persistCache = (ref, storageKey) => {
    try {
      // Cap to newest 200 entries to stay within localStorage quotas.
      const entries = Array.from(ref.current.entries()).slice(-200);
      localStorage.setItem(storageKey, JSON.stringify(entries));
    } catch {}
  };

  // Keywords in restriction_reason that mean "pin is in/on water".
  // Backend may return: "Water body (River)", "River", "Stream", "Canal",
  // "Lake", "Pond", "Sea", "Ocean", "Drain".
  const _isWater = (reason) => {
    if (!reason) return false;
    return /water|river|stream|canal|drain|lake|pond|sea|ocean|reservoir|lagoon|bay/i.test(reason);
  };

  // ---------------------------------------------------------------------
  // Coordinate-based water heuristic (fallback for when backend fails).
  // Conservative bboxes — only flags points CLEARLY inside major water
  // bodies (ocean interiors + big seas/gulfs/lakes). Near-coast and small
  // rivers still rely on the backend Overpass check.
  // Shape: [latMin, latMax, lngMin, lngMax]
  // ---------------------------------------------------------------------
  const _WATER_BBOXES = [
    // Ocean interiors (conservative, away from coasts) ------------------
    // North Atlantic interior
    [20, 55, -55, -22],
    // South Atlantic interior (between S. America and Africa)
    [-50, -5, -30, 5],
    // North Pacific interior (wraps the antimeridian -> split)
    [10, 50, 155, 180],
    [10, 50, -180, -135],
    // South Pacific interior
    [-50, -5, 165, 180],
    [-50, -5, -180, -100],
    // Indian Ocean interior
    [-45, -8, 55, 105],
    // Arctic
    [78, 90, -180, 180],
    // Southern Ocean
    [-90, -65, -180, 180],
    // Seas, gulfs, major lakes -----------------------------------------
    [36, 47, 46.5, 55],      // Caspian Sea
    [41, 46.5, 28, 41.5],    // Black Sea
    [12, 30, 32, 44],        // Red Sea
    [24, 30, 48, 57],        // Persian Gulf
    [8, 22, 82, 94],         // Bay of Bengal (offshore)
    [3, 22, 108, 120],       // South China Sea
    [35, 50, 128, 142],      // Sea of Japan
    [54, 66, 15, 30],        // Baltic Sea
    [51, 61, -4, 9],         // North Sea
    [51, 63, -95, -77],      // Hudson Bay
    [18, 29, -97, -82],      // Gulf of Mexico
    [10, 22, -86, -62],      // Caribbean interior
    [46.3, 49, -92, -84.3],  // Lake Superior
    [41.5, 46.3, -88, -84.5],// Lake Michigan
    [43, 46.3, -84.5, -79.7],// Lake Huron
    [41.3, 43, -83.5, -78.7],// Lake Erie
    [43.1, 44.3, -79.9, -76.2], // Lake Ontario
    [-3.1, 0.6, 31.5, 34.9], // Lake Victoria
    [-9, -3, 28.5, 31],      // Lake Tanganyika
    [-15, -8.5, 33.8, 35.5], // Lake Malawi
    [45, 54, 31, 43],        // Sea of Azov + part of Black Sea N.
    [26, 30, 32, 36],        // Gulf of Suez + N. Red Sea
    [36, 46, -6, 16],        // W. Mediterranean (coarse)
    [30, 37, 15, 36],        // E. Mediterranean (coarse)
  ];
  const _isWaterCoord = (lat, lng) => {
    for (const [laMin, laMax, lnMin, lnMax] of _WATER_BBOXES) {
      if (lat >= laMin && lat <= laMax && lng >= lnMin && lng <= lnMax) return true;
    }
    return false;
  };
  // Combined: either signal is enough to treat as water.
  const _isWaterPoint = (lat, lng, reason) => _isWaterCoord(lat, lng) || _isWater(reason);

  // Read ?q=... (and optional ?lat=&lng=) from URL (set by header search bar)
  const [searchParams] = useSearchParams();
  const queryParam = searchParams.get('q');
  const latRaw = searchParams.get('lat');
  const lngRaw = searchParams.get('lng');
  const latParam = latRaw != null ? parseFloat(latRaw) : NaN;
  const lngParam = lngRaw != null ? parseFloat(lngRaw) : NaN;
  const hasCoords = Number.isFinite(latParam) && Number.isFinite(lngParam);

  // Reference point used by zone loading, distance calc, and map fly-to.
  // Priority: dropped pin -> current center (fallback preserves old behavior).
  const refLat = picked ? picked[0] : center[0];
  const refLng = picked ? picked[1] : center[1];

  // initial location & data
  useEffect(() => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => setCenter([pos.coords.latitude, pos.coords.longitude]),
        () => {},
        { timeout: 4000 }
      );
    }
  }, []);

  // load zones whenever the reference point changes (pin drop OR center change)
  useEffect(() => { loadZones(refLat, refLng); }, [refLat, refLng]);

  // Geocode ?q= (header search) -> drop a pin at the result.
  // If ?lat=&lng= are present (chosen from the autocomplete), skip geocoding.
  // Non-destructive: only runs when params change.
  useEffect(() => {
    // Fast path: explicit coords from autocomplete selection.
    if (hasCoords) {
      const key = `coords:${latParam},${lngParam}`;
      if (lastSearchedRef.current === key) return;
      lastSearchedRef.current = key;
      if (queryParam) toast.success(`Found ${queryParam}`);
      onPick([latParam, lngParam]);
      return;
    }
    if (!queryParam) return;
    const q = queryParam.trim();
    if (!q) return;

    let cancelled = false;
    (async () => {
      try {
        const url = `https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(q)}`;
        const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
        if (!res.ok) throw new Error('geocode http ' + res.status);
        const arr = await res.json();
        if (cancelled) return;
        // Dedupe AFTER fetch completes so StrictMode double-mount doesn't skip the work.
        const key = `q:${q}`;
        if (lastSearchedRef.current === key) return;
        if (!Array.isArray(arr) || arr.length === 0) {
          lastSearchedRef.current = key;
          toast.error(`No results for "${q}"`);
          return;
        }
        const lat = parseFloat(arr[0].lat);
        const lng = parseFloat(arr[0].lon);
        if (Number.isNaN(lat) || Number.isNaN(lng)) {
          lastSearchedRef.current = key;
          toast.error('Invalid location returned');
          return;
        }
        lastSearchedRef.current = key;
        const niceName = (arr[0].display_name || q).split(',')[0];
        toast.success(`Found ${niceName}`);
        // Dropping a pin updates refPoint -> zones reload + map flies + analysis runs
        onPick([lat, lng]);
      } catch (e) {
        if (!cancelled) toast.error('Search failed. Please try again.');
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryParam, latParam, lngParam, hasCoords]);

  const loadZones = async (lat, lng) => {
    try {
      const { data } = await api.get('/analysis/zones', { params: { lat, lng, radius_km: 4 } });
      setZones(data);
    } catch (e) { console.error(e); }
  };

  const findNearMe = () => {
    if (!navigator.geolocation) return toast.error('Location unavailable');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        // Clear any dropped pin so center (current location) becomes the reference point again.
        setPicked(null);
        setCenter([pos.coords.latitude, pos.coords.longitude]);
        toast.success('Centered on your location');
      },
      () => toast.error('Could not get your location')
    );
  };

  // Round a coordinate to a stable cache key (~11 m grid, matches backend).
  const _ckey = (lat, lng) => `${lat.toFixed(4)},${lng.toFixed(4)}`;

  // Core picker: runs analysis with cache + in-flight dedupe.
  const _runPick = async (latlng) => {
    // Frontend water fallback — block BEFORE any state change / API call.
    if (_isWaterCoord(latlng[0], latlng[1])) {
      toast.error('Cannot analyze water. Drop the pin on land.');
      setPicked(null);
      setAnalyzing(false);
      return;
    }
    setAnalyzing(true); setRecommendation(null);
    const key = _ckey(latlng[0], latlng[1]);
    const cached = analysisCacheRef.current.get(key);
    if (cached) {
      if (_isWaterPoint(latlng[0], latlng[1], cached.restriction_reason) && cached.plantable === false) {
        toast.error(`Cannot analyze water (${cached.restriction_reason || 'water body'}). Move the pin to land.`);
        setPicked(null);
        setAnalyzing(false);
        return;
      }
      setAnalysis(cached);
      setPanelOpen(true);
      setAnalyzing(false);
      return;
    }
    const myCall = ++inflightRef.current;
    try {
      const { data } = await api.post('/analysis/suitability', { lat: latlng[0], lng: latlng[1] });
      if (myCall === inflightRef.current) {
        analysisCacheRef.current.set(key, data);
        _persistCache(analysisCacheRef, 'growhere:analysisCache');
        // Hard-block water: skip the panel entirely, drop the pin, toast the user.
        if (_isWaterPoint(latlng[0], latlng[1], data.restriction_reason) && data.plantable === false) {
          toast.error(`Cannot analyze water (${data.restriction_reason || 'water body'}). Move the pin to land.`);
          setPicked(null);
        } else {
          setAnalysis(data);
          setPanelOpen(true);
        }
      }
    } catch (e) { toast.error('Analysis failed'); }
    finally { if (myCall === inflightRef.current) setAnalyzing(false); }
  };

  // Debounced public handler — avoids firing on every rapid click / drag.
  const onPick = (latlng) => {
    // Block pin placement on water outright — no debounce wait, no pin shown.
    if (_isWaterCoord(latlng[0], latlng[1])) {
      toast.error('That spot is water. Pick a point on land.');
      return;
    }
    setPicked(latlng);
    if (pickDebounceRef.current) clearTimeout(pickDebounceRef.current);
    pickDebounceRef.current = setTimeout(() => _runPick(latlng), 350);
  };

  const getRecommendation = async () => {
    if (!analysis) return;
    const key = _ckey(analysis.lat, analysis.lng);
    const cached = recoCacheRef.current.get(key);
    if (cached) { setRecommendation(cached); return; }
    setRecoBusy(true);
    try {
      const { data } = await api.post('/recommendations/species', {
        lat: analysis.lat, lng: analysis.lng, suitability: analysis,
      });
      recoCacheRef.current.set(key, data);
      _persistCache(recoCacheRef, 'growhere:recoCache');
      setRecommendation(data);
    } catch { toast.error('AI recommendation failed'); }
    finally { setRecoBusy(false); }
  };

  const copyCoords = () => {
    if (!analysis) return;
    const txt = `${analysis.lat.toFixed(5)}, ${analysis.lng.toFixed(5)}`;
    try {
      navigator.clipboard.writeText(txt);
      toast.success(`Copied ${txt}`);
    } catch { toast.error('Copy failed'); }
  };

  const currentBookmarkKey = analysis ? _ckey(analysis.lat, analysis.lng) : null;
  const isBookmarked = currentBookmarkKey &&
    bookmarks.some(b => _ckey(b.lat, b.lng) === currentBookmarkKey);

  const toggleBookmark = () => {
    if (!analysis) return;
    const key = _ckey(analysis.lat, analysis.lng);
    let next;
    if (bookmarks.some(b => _ckey(b.lat, b.lng) === key)) {
      next = bookmarks.filter(b => _ckey(b.lat, b.lng) !== key);
      toast.success('Removed bookmark');
    } else {
      next = [{ lat: analysis.lat, lng: analysis.lng, label: analysis.land_use || 'Pinned spot', ts: Date.now() }, ...bookmarks].slice(0, 30);
      toast.success('Bookmarked');
    }
    setBookmarks(next);
    try { localStorage.setItem('growhere:bookmarks', JSON.stringify(next)); } catch {}
  };

  const removeBookmark = (key) => {
    const next = bookmarks.filter(b => _ckey(b.lat, b.lng) !== key);
    setBookmarks(next);
    try { localStorage.setItem('growhere:bookmarks', JSON.stringify(next)); } catch {}
  };

  const stats = useMemo(() => {
    const counts = { high_potential: 0, moderate_permission_needed: 0, restricted_protected: 0 };
    zones.forEach(z => { counts[z.zone] = (counts[z.zone] || 0) + 1; });
    return counts;
  }, [zones]);

  const isAllowed = (z) => z.zone === 'high_potential' || z.zone === 'moderate_permission_needed';

  const filterMatch = (z) => {
    if (zoneFilter === 'all') return true;
    if (zoneFilter === 'allowed') return isAllowed(z);
    if (zoneFilter === 'free') return z.zone === 'high_potential';
    return true;
  };

  const visibleZones = useMemo(
    () => zones.filter(z => filterMatch(z) && !_isWaterCoord(z.center_lat, z.center_lng)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [zones, zoneFilter]
  );

  const haversineKm = (a, b) => {
    const toR = (x) => (x * Math.PI) / 180;
    const R = 6371;
    const dLat = toR(b[0] - a[0]);
    const dLng = toR(b[1] - a[1]);
    const s = Math.sin(dLat/2)**2 + Math.cos(toR(a[0]))*Math.cos(toR(b[0]))*Math.sin(dLng/2)**2;
    return R * 2 * Math.atan2(Math.sqrt(s), Math.sqrt(1-s));
  };

  const allowedNearby = useMemo(() => {
    const ref = [refLat, refLng];
    return zones
      .filter(z => isAllowed(z) && !_isWaterCoord(z.center_lat, z.center_lng))
      .map(z => ({ ...z, distance_km: haversineKm(ref, [z.center_lat, z.center_lng]) }))
      .sort((a, b) => {
        // Prefer high_potential first, then closer + higher-scoring
        const za = a.zone === 'high_potential' ? 0 : 1;
        const zb = b.zone === 'high_potential' ? 0 : 1;
        if (za !== zb) return za - zb;
        return a.distance_km - b.distance_km;
      });
  }, [zones, refLat, refLng]);

  return (
    <div className="relative h-[calc(100vh-72px)] w-full bg-bonewarm" data-testid="map-dashboard">
      {/* Map */}
      <MapContainer center={center} zoom={13} className="h-full w-full z-0" zoomControl={false}>
        <LayersControl position="bottomright">
          <LayersControl.BaseLayer checked name="Map">
            <TileLayer attribution='&copy; OpenStreetMap'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer name="Satellite">
            <TileLayer attribution='Tiles © Esri'
              url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}" />
          </LayersControl.BaseLayer>
          <LayersControl.BaseLayer name="Topographic">
            <TileLayer attribution='&copy; OpenTopoMap'
              url="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png" />
          </LayersControl.BaseLayer>
        </LayersControl>

        <FlyTo pos={[refLat, refLng]} />
        <ClickHandler onPick={onPick} />

        {showLayers.suitability && visibleZones.map(z => {
          const s = ZONE_STYLES[z.zone];
          return (
            <Circle key={z.id} center={[z.center_lat, z.center_lng]} radius={z.radius_m}
              pathOptions={{ color: s.color, fillColor: s.fill, fillOpacity: 0.32, weight: 2 }}
              bubblingMouseEvents={true}
              eventHandlers={{ click: (e) => onPick([e.latlng.lat, e.latlng.lng]) }}>
              <Popup>
                <div className="font-sans">
                  <div className="font-bold uppercase text-xs tracking-wider" style={{color: s.color}}>{s.label}</div>
                  <div className="font-serif text-lg mt-1">{z.label}</div>
                  <div className="text-xs mt-1 text-bark">Score {z.suitability_score}/100</div>
                  <button onClick={() => onPick([z.center_lat, z.center_lng])}
                    className="mt-2 text-xs font-semibold text-forest-700 underline">
                    Analyze this spot
                  </button>
                </div>
              </Popup>
            </Circle>
          );
        })}

        {picked && (
          <Marker position={picked}>
            <Popup>Selected location</Popup>
          </Marker>
        )}
      </MapContainer>

      {/* Top floating controls */}
      <div className="absolute top-5 left-5 z-[500] flex flex-col gap-3" data-testid="map-controls">
        <button onClick={findNearMe} className="panel-glass p-3 hover:-translate-y-0.5 transition-transform"
          title="Find near me" data-testid="locate-btn">
          <Locate className="w-5 h-5 text-forest-700" />
        </button>
        <button onClick={() => setLayersOpen(v=>!v)}
          className={`panel-glass p-3 hover:-translate-y-0.5 transition-transform ${layersOpen ? 'ring-2 ring-forest-700' : ''}`}
          title="Layers" data-testid="layers-btn">
          <LayersIcon className="w-5 h-5 text-forest-700" />
        </button>
        <button onClick={() => setAllowedListOpen(v=>!v)}
          className={`panel-glass p-3 hover:-translate-y-0.5 transition-transform relative ${allowedListOpen ? 'ring-2 ring-forest-700' : ''}`}
          title="Allowed places nearby" data-testid="allowed-list-btn">
          <ListFilter className="w-5 h-5 text-forest-700" />
          {allowedNearby.length > 0 && (
            <span className="absolute -top-1 -right-1 bg-suit-high text-bone text-[10px] font-bold rounded-full w-5 h-5 grid place-items-center">
              {allowedNearby.length}
            </span>
          )}
        </button>
        <button onClick={() => setBookmarksOpen(v=>!v)}
          className={`panel-glass p-3 hover:-translate-y-0.5 transition-transform relative ${bookmarksOpen ? 'ring-2 ring-forest-700' : ''}`}
          title="Bookmarked spots" data-testid="bookmarks-btn">
          <Bookmark className="w-5 h-5 text-forest-700" />
          {bookmarks.length > 0 && (
            <span className="absolute -top-1 -right-1 bg-forest-700 text-bone text-[10px] font-bold rounded-full w-5 h-5 grid place-items-center">
              {bookmarks.length}
            </span>
          )}
        </button>
      </div>

      {/* Layers panel */}
      {layersOpen && (
        <div className="absolute top-5 left-20 z-[500] panel-glass p-5 w-72 fade-in-up" data-testid="layers-panel">
          <div className="flex items-center justify-between mb-4">
            <span className="small-label">Map layers</span>
            <button onClick={()=>setLayersOpen(false)}><X className="w-4 h-4 text-bark" /></button>
          </div>
          <div className="space-y-3">
            {[
              { k: 'suitability', label: 'Suitability zones', icon: Trees },
            ].map(({k, label, icon: Icon}) => (
              <label key={k} className="flex items-center gap-3 cursor-pointer text-sm">
                <input type="checkbox" checked={showLayers[k]}
                  onChange={e=>setShowLayers(s=>({...s,[k]:e.target.checked}))}
                  className="w-4 h-4 accent-forest-700" data-testid={`toggle-${k}`} />
                <Icon className="w-4 h-4 text-forest-700" />
                <span className="font-medium">{label}</span>
              </label>
            ))}
          </div>
          <hr className="my-4 border-[#E3DFD5]" />
          <span className="small-label">Legend</span>
          <div className="space-y-2 mt-3">
            {Object.entries(ZONE_STYLES).map(([k, s]) => (
              <div key={k} className="flex items-center gap-2 text-sm">
                <span className="w-3.5 h-3.5 rounded-full" style={{ backgroundColor: s.color }} />
                <span className="font-medium">{s.label}</span>
                <span className="text-bark text-xs ml-auto">{stats[k] || 0}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Bookmarks panel */}
      {bookmarksOpen && (
        <div className="absolute top-5 left-20 z-[500] panel-glass p-5 w-80 fade-in-up max-h-[calc(100vh-110px)] overflow-y-auto" data-testid="bookmarks-panel">
          <div className="flex items-center justify-between mb-3">
            <span className="small-label">Bookmarked spots ({bookmarks.length})</span>
            <button onClick={()=>setBookmarksOpen(false)} data-testid="bookmarks-close"><X className="w-4 h-4 text-bark" /></button>
          </div>
          {bookmarks.length === 0 ? (
            <p className="text-sm text-bark py-6 text-center">No bookmarks yet. Analyze a spot and hit <span className="inline-flex items-center gap-1 font-semibold text-forest-700"><Bookmark className="w-3 h-3" /> Bookmark</span>.</p>
          ) : (
            <div className="space-y-2">
              {bookmarks.map(b => {
                const key = _ckey(b.lat, b.lng);
                return (
                  <div key={key} className="flex items-start gap-2 p-3 rounded-xl border border-[#E3DFD5] bg-white" data-testid={`bookmark-item-${key}`}>
                    <button onClick={() => { onPick([b.lat, b.lng]); setCenter([b.lat, b.lng]); }}
                      className="flex-1 text-left min-w-0">
                      <div className="font-serif text-base text-forest-900 truncate">{b.label}</div>
                      <div className="text-xs text-bark mt-0.5">{b.lat.toFixed(4)}, {b.lng.toFixed(4)}</div>
                    </button>
                    <button onClick={() => removeBookmark(key)}
                      className="p-1 rounded-full hover:bg-bonewarm transition-colors"
                      data-testid={`bookmark-remove-${key}`} aria-label="Remove bookmark">
                      <X className="w-4 h-4 text-bark" />
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Allowed-only list panel */}
      {allowedListOpen && (
        <div className="absolute top-5 left-20 z-[500] panel-glass p-5 w-80 fade-in-up max-h-[calc(100vh-110px)] overflow-y-auto" data-testid="allowed-list-panel">
          <div className="flex items-center justify-between mb-3">
            <span className="small-label">Plant-friendly nearby</span>
            <button onClick={()=>setAllowedListOpen(false)} data-testid="allowed-list-close"><X className="w-4 h-4 text-bark" /></button>
          </div>
          <div className="flex gap-1.5 mb-4">
            {[
              { k: 'all', label: 'All' },
              { k: 'allowed', label: 'Allowed' },
              { k: 'free', label: 'Free' },
            ].map(({k, label}) => (
              <button key={k} onClick={()=>setZoneFilter(k)}
                className={`flex-1 text-xs font-bold uppercase tracking-wider rounded-full px-3 py-1.5 transition-colors ${zoneFilter === k ? 'bg-forest-700 text-bone' : 'bg-bonewarm text-forest-700 hover:bg-[#E3DFD5]'}`}
                data-testid={`filter-${k}`}>
                {label}
              </button>
            ))}
          </div>
          <p className="text-xs text-bark/80 mb-3">
            {zoneFilter === 'free' ? 'Public commons & open land — plant freely.' :
             zoneFilter === 'allowed' ? 'Spots where planting is allowed (some need owner permission).' :
             'All scanned zones around you.'}
          </p>
          <div className="space-y-2">
            {allowedNearby.length === 0 && (
              <p className="text-sm text-bark py-6 text-center">No allowed spots in this radius. Try moving the map.</p>
            )}
            {allowedNearby.map(z => {
              const s = ZONE_STYLES[z.zone];
              return (
                <button key={z.id}
                  onClick={() => { onPick([z.center_lat, z.center_lng]); setCenter([z.center_lat, z.center_lng]); }}
                  className="w-full text-left p-3 rounded-xl border border-[#E3DFD5] bg-white hover:bg-bonewarm hover:-translate-y-0.5 transition-all duration-200"
                  data-testid={`allowed-item-${z.id}`}>
                  <div className="flex items-start gap-3">
                    <span className="mt-1 w-2.5 h-2.5 rounded-full flex-shrink-0" style={{backgroundColor: s.color}} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="font-serif text-base text-forest-900 truncate">{z.label}</span>
                        <span className="text-xs font-bold text-forest-700 flex-shrink-0">{z.suitability_score}</span>
                      </div>
                      <div className="flex items-center gap-2 mt-1 text-xs text-bark">
                        <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{z.distance_km.toFixed(1)} km</span>
                        <span className="text-[10px] uppercase tracking-wider font-bold" style={{color: s.color}}>{s.label}</span>
                      </div>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Top right zone-summary */}
      <div className="absolute top-5 right-5 z-[500] panel-glass px-3 py-3 hidden md:flex items-center gap-1" data-testid="zone-summary">
        {Object.entries(ZONE_STYLES).map(([k, s]) => {
          const isActive =
            (zoneFilter === 'free' && k === 'high_potential') ||
            (zoneFilter === 'allowed' && (k === 'high_potential' || k === 'moderate_permission_needed')) ||
            (zoneFilter === 'all');
          const onClick = () => {
            if (k === 'high_potential') setZoneFilter(zoneFilter === 'free' ? 'all' : 'free');
            else if (k === 'moderate_permission_needed') setZoneFilter(zoneFilter === 'allowed' ? 'all' : 'allowed');
            else setZoneFilter('all');
          };
          return (
            <button key={k} onClick={onClick}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-full transition-all ${isActive ? 'bg-bonewarm' : 'opacity-50 hover:opacity-100'}`}
              data-testid={`zone-chip-${k}`}>
              <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: s.color }} />
              <div className="text-left">
                <div className="text-[10px] uppercase tracking-wider text-bark font-bold leading-tight">{s.label}</div>
                <div className="text-xs font-bold text-forest-900 leading-tight">{stats[k] || 0}</div>
              </div>
            </button>
          );
        })}
      </div>

      {/* Hint */}
      {!analysis && !analyzing && (
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-[500] panel-glass px-5 py-3 flex items-center gap-2 text-sm fade-in-up">
          <Info className="w-4 h-4 text-forest-700" />
          <span className="text-forest-900 font-medium">Tap anywhere on the map to analyze a spot.</span>
        </div>
      )}

      {/* Analysis bottom-sheet / panel */}
      {(analysis || analyzing) && (
        <div className={`absolute right-0 bottom-0 z-[500] w-full md:w-[440px] md:right-5 md:bottom-5 transition-transform duration-300`}
          data-testid="analysis-panel">
          {/* Floating close button (outside the scroll area) */}
          <button
            onClick={() => {
              setAnalysis(null);
              setRecommendation(null);
              setAnalyzing(false);
            }}
            className="absolute top-3 right-3 z-10 w-9 h-9 grid place-items-center rounded-full bg-white shadow-md border border-[#E3DFD5] hover:bg-bonewarm transition-colors"
            data-testid="analysis-close"
            aria-label="Close suitability analysis"
            title="Close"
          >
            <X className="w-5 h-5 text-bark" />
          </button>
          <div className="panel-glass p-6 md:p-7 max-h-[78vh] overflow-y-auto">
            <div className="flex items-start justify-between mb-3 pr-10">
              <div>
                <span className="small-label">Suitability analysis</span>
                {analysis && (
                  <h3 className="font-serif text-2xl mt-1 leading-tight">{analysis.land_use}</h3>
                )}
              </div>
              <div className="flex items-center gap-1 -mr-1">
                <button
                  onClick={()=>setPanelOpen(p=>!p)}
                  className="md:hidden p-1.5 rounded-full hover:bg-bonewarm transition-colors"
                  data-testid="panel-toggle"
                  aria-label={panelOpen ? 'Collapse panel' : 'Expand panel'}
                >
                  {panelOpen ? <ChevronDown className="w-5 h-5"/> : <ChevronUp className="w-5 h-5"/>}
                </button>
              </div>
            </div>

            {analyzing && (
              <div className="py-12 text-center">
                <Loader2 className="w-8 h-8 mx-auto animate-spin text-forest-700" />
                <p className="mt-3 text-sm text-bark">Reading satellite & zoning…</p>
              </div>
            )}

            {analysis && !analyzing && (
              <div className={`${panelOpen ? '' : 'hidden md:block'}`}>
                {/* Score */}
                <div className="flex items-center gap-4 mt-2">
                  <div className="relative w-20 h-20">
                    <svg viewBox="0 0 36 36" className="w-20 h-20 -rotate-90">
                      <circle cx="18" cy="18" r="15.9" fill="none" stroke="#E3DFD5" strokeWidth="3" />
                      <circle cx="18" cy="18" r="15.9" fill="none"
                        stroke={ZONE_STYLES[analysis.zone].color} strokeWidth="3"
                        strokeDasharray={`${analysis.suitability_score}, 100`} strokeLinecap="round" />
                    </svg>
                    <div className="absolute inset-0 grid place-items-center">
                      <span className="font-serif text-2xl text-forest-900">{analysis.suitability_score}</span>
                    </div>
                  </div>
                  <div>
                    <span className="badge-soft text-bone" style={{backgroundColor: ZONE_STYLES[analysis.zone].color}}>
                      {ZONE_STYLES[analysis.zone].label}
                    </span>
                    <p className="text-sm text-bark mt-2">{analysis.rationale}.</p>
                    <p className="text-xs text-bark/70 mt-1">Confidence {analysis.confidence}%</p>
                  </div>
                </div>

                {/* Quick actions: copy coords + bookmark */}
                <div className="flex gap-2 mt-4">
                  <button onClick={copyCoords}
                    className="flex-1 flex items-center justify-center gap-2 text-xs font-bold uppercase tracking-wider rounded-full px-3 py-2 bg-bonewarm text-forest-700 hover:bg-[#E3DFD5] transition-colors"
                    data-testid="copy-coords-btn" title="Copy lat, lng">
                    <Copy className="w-3.5 h-3.5" /> Copy coordinates
                  </button>
                  <button onClick={toggleBookmark}
                    className={`flex-1 flex items-center justify-center gap-2 text-xs font-bold uppercase tracking-wider rounded-full px-3 py-2 transition-colors ${isBookmarked ? 'bg-forest-700 text-bone hover:bg-forest-800' : 'bg-bonewarm text-forest-700 hover:bg-[#E3DFD5]'}`}
                    data-testid="bookmark-btn" title="Save this spot (local)">
                    {isBookmarked ? <><BookmarkCheck className="w-3.5 h-3.5" /> Saved</> : <><Bookmark className="w-3.5 h-3.5" /> Bookmark</>}
                  </button>
                </div>

                {/* Metrics */}
                <div className="grid grid-cols-2 gap-3 mt-5">
                  <Metric label="NDVI" value={analysis.ndvi} hint="vegetation index" />
                  <Metric label="Soil moisture" value={`${analysis.soil_moisture}%`} hint="topsoil" />
                  <Metric label="Canopy cover" value={`${analysis.canopy_cover}%`} hint="existing" />
                  <Metric label="Water access" value={`${analysis.water_availability}%`} hint="proximity" />
                </div>

                {/* Non-plantable banner (river / road / building) */}
                {analysis.plantable === false && (
                  <div className="mt-4 p-4 rounded-xl bg-[#F8E5DE] border border-[#E6B9A8] flex gap-3" data-testid="not-plantable-banner">
                    <AlertTriangle className="w-5 h-5 text-terracotta flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-bold text-forest-900">Not plantable here</p>
                      <p className="text-xs text-bark mt-1">
                        This pin falls on a {analysis.restriction_reason || 'non-plantable surface'}. Move it a few metres to nearby soil.
                      </p>
                    </div>
                  </div>
                )}

                {/* Legal */}
                <div className="mt-5 p-4 rounded-xl bg-bonewarm border border-[#E3DFD5]">
                  <span className="small-label">Legal status</span>
                  <p className="text-sm font-semibold text-forest-900 mt-1 capitalize">{analysis.legal_status.replace('_',' ')}</p>
                  <p className="text-sm text-bark mt-1">{analysis.legal_note}</p>
                </div>

                {/* AI recommendation */}
                <div className="mt-5">
                  {!recommendation ? (
                    <button onClick={getRecommendation} disabled={recoBusy || analysis.plantable === false}
                      className="btn-primary w-full justify-center disabled:opacity-50 disabled:cursor-not-allowed" data-testid="get-species-btn">
                      {analysis.plantable === false ? <><AlertTriangle className="w-4 h-4" /> Move pin to plantable ground</> :
                       recoBusy ? <><Loader2 className="w-4 h-4 animate-spin" /> Asking the forest…</> :
                                  <><Sparkles className="w-4 h-4" /> Recommend native species</>}
                    </button>
                  ) : (
                    <div className="space-y-4">
                      <div className="flex items-center gap-2">
                        <Sparkles className="w-4 h-4 text-forest-700" />
                        <span className="small-label">AI recommendation</span>
                        {recommendation.climate_code && (
                          <span className="ml-auto text-[10px] font-mono uppercase tracking-wider bg-bonewarm text-forest-700 px-2 py-0.5 rounded-full" data-testid="climate-code-badge">
                            {recommendation.climate_code}
                          </span>
                        )}
                      </div>

                      {recommendation.plantable === false ? (
                        <div className="p-4 rounded-xl bg-[#F8E5DE] border border-[#E6B9A8]" data-testid="reco-non-plantable">
                          <p className="text-sm font-bold text-forest-900">Nothing to plant here.</p>
                          <p className="text-xs text-bark mt-1">{recommendation.notes}</p>
                        </div>
                      ) : (
                        <>
                          <p className="text-sm text-bark"><strong className="text-forest-900">Climate:</strong> {recommendation.climate_summary}</p>
                          <p className="text-sm text-bark"><strong className="text-forest-900">Plant in:</strong> {recommendation.best_planting_window}</p>

                          {/* Categorised species rendering */}
                          {recommendation.species_by_category ? (
                            <>
                              <SpeciesCategorySection
                                title="Trees"
                                icon={Trees}
                                items={recommendation.species_by_category.tree || []}
                                testPrefix="tree"
                              />
                              <SpeciesCategorySection
                                title="Shrubs"
                                icon={Shrub}
                                items={recommendation.species_by_category.shrub || []}
                                testPrefix="shrub"
                              />
                              <SpeciesCategorySection
                                title="Ground cover"
                                icon={Sprout}
                                items={recommendation.species_by_category.ground_cover || []}
                                testPrefix="groundcover"
                              />
                            </>
                          ) : (
                            <div className="space-y-2">
                              {(recommendation.species || []).map((sp, i) => (
                                <SpeciesCard key={i} sp={sp} testId={`species-card-${i}`} />
                              ))}
                            </div>
                          )}

                          {recommendation.notes && <p className="text-xs text-bark italic">{recommendation.notes}</p>}
                        </>
                      )}
                    </div>
                  )}
                </div>

                {/* Sources */}
                <div className="mt-5 pt-4 border-t border-[#E3DFD5]">
                  <span className="small-label flex items-center gap-1"><ShieldCheck className="w-3 h-3" /> Data sources</span>
                  <ul className="text-xs text-bark mt-2 space-y-1">
                    {analysis.data_sources.map((s, i) => <li key={i}>· {s}</li>)}
                  </ul>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, hint }) {
  return (
    <div className="p-3 rounded-xl bg-white border border-[#E3DFD5]">
      <div className="small-label">{label}</div>
      <div className="font-serif text-2xl text-forest-900 mt-1">{value}</div>
      <div className="text-[10px] uppercase tracking-wider text-bark/70 mt-0.5">{hint}</div>
    </div>
  );
}

function SpeciesCard({ sp, testId }) {
  return (
    <div className="p-3 rounded-lg bg-white border border-[#E3DFD5]" data-testid={testId}>
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="font-serif text-lg text-forest-900">{sp.common_name}</h4>
        <span className="text-xs italic text-bark">{sp.scientific_name}</span>
      </div>
      <p className="text-xs text-bark mt-1">{sp.why}</p>
      <div className="flex flex-wrap gap-2 mt-2 text-[10px] uppercase tracking-wider font-bold">
        <span className="badge-soft bg-forest-50 text-forest-700">{sp.water_needs} water</span>
        <span className="badge-soft bg-bonewarm text-forest-700">{sp.growth_rate}</span>
      </div>
    </div>
  );
}

function SpeciesCategorySection({ title, icon: Icon, items, testPrefix }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="space-y-2" data-testid={`species-section-${testPrefix}`}>
      <div className="flex items-center gap-2 pt-2">
        <Icon className="w-4 h-4 text-forest-700" />
        <span className="small-label">{title}</span>
        <span className="text-[10px] text-bark/70 ml-1">({items.length})</span>
      </div>
      {items.map((sp, i) => (
        <SpeciesCard key={i} sp={sp} testId={`species-card-${testPrefix}-${i}`} />
      ))}
    </div>
  );
}

import { useEffect, useRef, useState } from 'react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { api } from '../lib/api';
import { Loader2, ExternalLink, ShieldCheck, Info } from 'lucide-react';

/**
 * Tabbed wrapper for the Suitability Analysis panel.
 *
 * Tab 1 ("Overview") shows whatever the parent passes as `overview` — i.e.
 * the existing UI is preserved 1:1.
 * Tab 2 ("Regional Insights") and Tab 3 ("Organizations") lazy-fetch from
 * the new /api/insights/* endpoints only when their tab is opened.
 *
 * Caches per-coordinate results in-memory so tab switching is free.
 */
export default function SuitabilityTabs({ analysis, overview }) {
  const [tab, setTab] = useState('overview');
  const lat = analysis?.lat;
  const lng = analysis?.lng;

  return (
    <Tabs value={tab} onValueChange={setTab} className="mt-3" data-testid="suitability-tabs">
      <TabsList className="grid w-full grid-cols-3 h-auto bg-bonewarm p-1 rounded-full">
        <TabsTrigger value="overview" className="rounded-full text-xs font-bold uppercase tracking-wider py-1.5 data-[state=active]:bg-forest-700 data-[state=active]:text-bone" data-testid="tab-overview">
          Overview
        </TabsTrigger>
        <TabsTrigger value="regional" className="rounded-full text-xs font-bold uppercase tracking-wider py-1.5 data-[state=active]:bg-forest-700 data-[state=active]:text-bone" data-testid="tab-regional">
          News
        </TabsTrigger>
        <TabsTrigger value="organizations" className="rounded-full text-xs font-bold uppercase tracking-wider py-1.5 data-[state=active]:bg-forest-700 data-[state=active]:text-bone" data-testid="tab-organizations">
          Organizations
        </TabsTrigger>
      </TabsList>

      <TabsContent value="overview" className="mt-4" data-testid="tab-content-overview">
        {overview}
      </TabsContent>

      <TabsContent value="regional" className="mt-4" data-testid="tab-content-regional">
        {tab === 'regional' && <RegionalInsightsTab lat={lat} lng={lng} />}
      </TabsContent>

      <TabsContent value="organizations" className="mt-4" data-testid="tab-content-organizations">
        {tab === 'organizations' && <OrganizationsTab lat={lat} lng={lng} />}
      </TabsContent>
    </Tabs>
  );
}

// In-memory cache per session (parent panel persists across tab switches).
const _regionalCache = new Map();
const _orgsCache = new Map();
const _ckey = (lat, lng) => `${lat.toFixed(4)},${lng.toFixed(4)}`;

const _fmtDate = (iso) => {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  } catch { return ''; }
};

function useLazyFetch(lat, lng, path, cache) {
  const [state, setState] = useState({ loading: true, data: null, error: null });
  const reqRef = useRef(0);
  useEffect(() => {
    if (lat == null || lng == null) return;
    const key = _ckey(lat, lng);
    const cached = cache.get(key);
    if (cached) { setState({ loading: false, data: cached, error: null }); return; }
    const my = ++reqRef.current;
    setState({ loading: true, data: null, error: null });
    (async () => {
      try {
        const { data } = await api.post(path, { lat, lng });
        if (my !== reqRef.current) return;
        cache.set(key, data);
        setState({ loading: false, data, error: null });
      } catch (e) {
        if (my !== reqRef.current) return;
        setState({ loading: false, data: null, error: 'Could not load. Try again later.' });
      }
    })();
  }, [lat, lng, path, cache]);
  return state;
}

function LocationHeader({ data }) {
  if (!data) return null;
  const place = [data.district, data.state, data.country].filter(Boolean).join(', ') || data.location;
  return (
    <div className="text-xs text-bark mb-3" data-testid="insights-location">
      <span className="small-label">Area</span>
      <span className="ml-2 text-forest-900 font-semibold">{place || '—'}</span>
    </div>
  );
}

function SourcesFooter({ sources, provider }) {
  if (!sources || sources.length === 0) return null;
  return (
    <div className="mt-3 pt-3 border-t border-[#E3DFD5] text-xs text-bark" data-testid="insights-sources">
      <span className="small-label flex items-center gap-1"><ShieldCheck className="w-3 h-3" /> Sources</span>
      <p className="mt-1">{sources.slice(0, 6).join(', ')}{provider ? ` · via ${provider}` : ''}</p>
    </div>
  );
}

function EmptyState({ message }) {
  return (
    <div className="p-4 rounded-xl bg-bonewarm border border-[#E3DFD5] text-sm text-bark flex gap-2" data-testid="insights-empty">
      <Info className="w-4 h-4 text-forest-700 flex-shrink-0 mt-0.5" />
      <span>{message}</span>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="py-10 text-center" data-testid="insights-loading">
      <Loader2 className="w-6 h-6 mx-auto animate-spin text-forest-700" />
      <p className="mt-2 text-xs text-bark">Fetching verified sources…</p>
    </div>
  );
}

function RegionalInsightsTab({ lat, lng }) {
  const { loading, data, error } = useLazyFetch(lat, lng, '/insights/news', _regionalCache);
  if (loading) return <LoadingState />;
  if (error) return <EmptyState message={error} />;
  if (!data) return null;
  if (!data.available || !data.items?.length) {
    return (
      <>
        <LocationHeader data={data} />
        <EmptyState message={data.reason || 'No recent regional environmental news found.'} />
      </>
    );
  }
  return (
    <div data-testid="regional-insights">
      <LocationHeader data={data} />
      <div className="space-y-2">
        {data.items.map((it, i) => (
          <a key={i} href={it.url} target="_blank" rel="noreferrer noopener"
             className="block p-3 rounded-lg bg-white border border-[#E3DFD5] hover:bg-bonewarm transition-colors"
             data-testid={`regional-item-${i}`}>
            <div className="flex items-start justify-between gap-2">
              <h4 className="font-serif text-base text-forest-900 leading-snug">{it.title}</h4>
              <ExternalLink className="w-3.5 h-3.5 text-bark flex-shrink-0 mt-1" />
            </div>
            <p className="text-xs text-bark mt-1.5 leading-relaxed">{it.summary}</p>
            <div className="flex items-center justify-between gap-2 mt-2">
              <span className="text-[10px] uppercase tracking-wider text-forest-700 font-bold">
                {it.source_name || it.domain}
              </span>
              {it.published && (
                <span className="text-[10px] text-bark/70 font-mono" data-testid={`regional-date-${i}`}>
                  {_fmtDate(it.published)}
                </span>
              )}
            </div>
          </a>
        ))}
      </div>
      <SourcesFooter sources={data.sources} provider={data.provider} />
    </div>
  );
}

function OrganizationsTab({ lat, lng }) {
  const { loading, data, error } = useLazyFetch(lat, lng, '/insights/organizations', _orgsCache);
  if (loading) return <LoadingState />;
  if (error) return <EmptyState message={error} />;
  if (!data) return null;
  if (!data.available || !data.organizations?.length) {
    return (
      <>
        <LocationHeader data={data} />
        <EmptyState message={data.reason || 'No verified organizations found for this area.'} />
      </>
    );
  }
  return (
    <div data-testid="organizations">
      <LocationHeader data={data} />
      <div className="space-y-2">
        {data.organizations.map((o, i) => (
          <div key={i} className="p-3 rounded-lg bg-white border border-[#E3DFD5]" data-testid={`org-item-${i}`}>
            <div className="flex items-start justify-between gap-2">
              <h4 className="font-serif text-base text-forest-900 leading-snug">{o.name}</h4>
              {o.website && (
                <a href={o.website} target="_blank" rel="noreferrer noopener"
                   className="text-bark hover:text-forest-700 flex-shrink-0 mt-1"
                   data-testid={`org-link-${i}`} aria-label="Open source">
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              )}
            </div>
            <p className="text-xs text-bark mt-1.5 leading-relaxed">{o.description}</p>
            {o.area_of_work && (
              <p className="text-[10px] uppercase tracking-wider text-bark/70 font-bold mt-2">
                Focus: {o.area_of_work}
              </p>
            )}
            {(o.source_name || o.domain) && (
              <p className="text-[10px] uppercase tracking-wider text-forest-700 font-bold mt-1">
                Source: {o.source_name || o.domain}
              </p>
            )}
          </div>
        ))}
      </div>
      <SourcesFooter sources={data.sources} provider={data.provider} />
    </div>
  );
}

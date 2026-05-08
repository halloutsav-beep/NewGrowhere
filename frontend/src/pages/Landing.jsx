import { Link } from 'react-router-dom';
import { ArrowRight, Layers, Sparkles, ShieldCheck, Leaf, MapPinned, Users } from 'lucide-react';

// TODO: Replace these placeholder links with real numbers / invite codes when available.
const WHATSAPP_CHAT_URL = 'https://wa.me/910000000000?text=Hi%20GROWhere%2C%20I%27d%20like%20to%20know%20more.';
const WHATSAPP_COMMUNITY_URL = 'https://chat.whatsapp.com/GbNE9LQ7yRQL0X0rRZHUIX';

// WhatsApp glyph (lucide-react doesn't ship a brand icon)
function WhatsAppIcon({ className = 'w-5 h-5' }) {
  return (
    <svg viewBox="0 0 32 32" fill="currentColor" className={className} aria-hidden="true">
      <path d="M19.11 17.55c-.27-.14-1.6-.79-1.85-.88-.25-.09-.43-.14-.61.14-.18.27-.7.88-.86 1.06-.16.18-.32.2-.59.07-.27-.14-1.14-.42-2.17-1.34-.8-.71-1.34-1.59-1.5-1.86-.16-.27-.02-.42.12-.55.12-.12.27-.32.41-.48.14-.16.18-.27.27-.45.09-.18.05-.34-.02-.48-.07-.14-.61-1.47-.84-2.02-.22-.53-.45-.46-.61-.47-.16-.01-.34-.01-.52-.01-.18 0-.48.07-.73.34-.25.27-.95.93-.95 2.27 0 1.34.98 2.63 1.11 2.81.14.18 1.92 2.93 4.65 4.11.65.28 1.16.45 1.55.58.65.21 1.24.18 1.71.11.52-.08 1.6-.65 1.83-1.28.23-.63.23-1.17.16-1.28-.07-.11-.25-.18-.52-.32zM16.04 5.33c-5.91 0-10.71 4.8-10.71 10.71 0 1.89.49 3.74 1.43 5.36L5.27 26.67l5.42-1.42a10.71 10.71 0 0 0 5.35 1.43h.01c5.91 0 10.71-4.8 10.71-10.71 0-2.86-1.11-5.55-3.13-7.57a10.65 10.65 0 0 0-7.59-3.07zm0 19.62h-.01a8.91 8.91 0 0 1-4.54-1.24l-.33-.19-3.22.84.86-3.13-.21-.32a8.92 8.92 0 0 1-1.36-4.74c0-4.92 4-8.92 8.92-8.92 2.38 0 4.62.93 6.31 2.61a8.86 8.86 0 0 1 2.61 6.31c0 4.92-4 8.92-8.93 8.92z"/>
    </svg>
  );
}

const HERO_BG = 'https://static.prod-images.emergentagent.com/jobs/4a62282e-bd47-4dcc-a739-eaabd1f602e2/images/9ee59f2c6c68687b5a73195012f6e735486ee478d9b2e5540d12759dbe15105d.png';
const SAPLING = 'https://static.prod-images.emergentagent.com/jobs/4a62282e-bd47-4dcc-a739-eaabd1f602e2/images/738b985aab963d3ff31d9d54749e9096bb43c4a66699c438688ef7a9d54318ba.png';
const COMMUNITY2 = 'https://images.unsplash.com/photo-1758599668429-121d54188b9c?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2Njl8MHwxfHNlYXJjaHwyfHxjb21tdW5pdHklMjBwbGFudGluZyUyMHRyZWVzfGVufDB8fHx8MTc3NzY1MzEyOXww&ixlib=rb-4.1.0&q=85';
const SATTEX = 'https://images.unsplash.com/photo-1624841934400-6abf1c91625b?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDk1ODB8MHwxfHNlYXJjaHwyfHxzYXRlbGxpdGUlMjB2aWV3JTIwZm9yZXN0JTIwbWFwfGVufDB8fHx8MTc3NzY1MzEyOXww&ixlib=rb-4.1.0&q=85';

export default function Landing() {
  return (
    <main className="bg-bone text-forest-900 topo-bg" data-testid="landing-page">
      {/* Hero */}
      <section className="relative pt-32 pb-24 overflow-hidden">
        <img src={HERO_BG} alt="" className="absolute inset-0 w-full h-full object-cover opacity-25 mix-blend-multiply" />
        <div className="absolute inset-0 bg-gradient-to-b from-bone/30 via-bone/60 to-bone" />
        <div className="container-narrow relative">
          <div className="max-w-3xl">
            <span className="small-label inline-flex items-center gap-2 mb-6"><Leaf className="w-3.5 h-3.5" /> Satellite-guided reforestation</span>
            <h1 className="font-serif text-5xl sm:text-6xl lg:text-7xl leading-[0.95] tracking-tight text-forest-900 fade-in-up">
              Plant where<br/>the land<br/><em className="text-terracotta italic">truly needs it.</em>
            </h1>
            <p className="mt-8 text-lg text-bark max-w-xl leading-relaxed fade-in-up" style={{animationDelay:'120ms'}}>
              GROWhere reads the latest satellite imagery, soil moisture, canopy cover and zoning data—so every tree
              your community plants lands on suitable, legal, ecologically grateful ground.
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-4 fade-in-up" style={{animationDelay:'200ms'}}>
              <Link to="/map" className="btn-primary" data-testid="hero-cta-find">
                Find planting spots near me <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
            <div className="mt-12 flex flex-wrap items-center gap-x-10 gap-y-3 text-sm text-bark">
              <span className="flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-forest-700" /> Sentinel-2 + Landsat composites</span>
              <span className="flex items-center gap-2"><Sparkles className="w-4 h-4 text-forest-700" /> Native species AI</span>
              <span className="flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-forest-700" /> Legal zoning baked in</span>
            </div>
          </div>
        </div>
      </section>

      {/* Bento Tetris features */}
      <section className="py-20">
        <div className="container-narrow">
          <div className="flex items-end justify-between mb-12 flex-wrap gap-6">
            <div className="max-w-xl">
              <span className="small-label">How it works</span>
              <h2 className="font-serif text-4xl sm:text-5xl mt-3 leading-tight">A map that<br/>understands the ground.</h2>
            </div>
            <p className="text-bark max-w-md leading-relaxed">
              Open the map and we'll read your surroundings — vegetation health, water access, legal zoning, soil tone — and tell you, plainly, where to plant and what to plant.
            </p>
          </div>

          <div className="grid grid-cols-12 gap-6">
            {/* Big card */}
            <div className="col-span-12 lg:col-span-8 relative rounded-2xl overflow-hidden border border-[#E3DFD5] bg-white min-h-[380px] group">
              <img src={SATTEX} alt="" className="absolute inset-0 w-full h-full object-cover opacity-90 group-hover:scale-105 transition-transform duration-700" />
              <div className="absolute inset-0 bg-gradient-to-tr from-forest-900/70 via-forest-900/30 to-transparent" />
              <div className="relative p-8 lg:p-10 h-full flex flex-col justify-between min-h-[380px]">
                <span className="small-label text-bone/80">01 — Satellite suitability</span>
                <div>
                  <h3 className="font-serif text-3xl lg:text-4xl text-bone leading-tight max-w-md">
                    NDVI, canopy & soil read in seconds.
                  </h3>
                  <p className="text-bone/85 mt-3 max-w-md">
                    We blend Sentinel-2, Landsat and SMAP into a single suitability layer that updates as the seasons shift.
                  </p>
                </div>
              </div>
            </div>

            {/* Side small */}
            <div className="col-span-12 lg:col-span-4 rounded-2xl bg-forest-700 text-bone p-8 flex flex-col justify-between min-h-[380px]">
              <span className="small-label text-bone/70">02 — Legal first</span>
              <div>
                <Layers className="w-10 h-10 text-ochre mb-4" />
                <h3 className="font-serif text-3xl leading-tight">Zoning & protected areas, baked in.</h3>
                <p className="text-bone/80 mt-3">Restricted forests, wetlands and private parcels are flagged before you ever pick up a sapling.</p>
              </div>
            </div>

            {/* AI species */}
            <div className="col-span-12 lg:col-span-7 rounded-2xl bg-bonewarm border border-[#E3DFD5] p-8 flex gap-6 items-center min-h-[260px]">
              <img src={SAPLING} alt="" className="w-32 h-32 object-contain" />
              <div>
                <span className="small-label">03 — AI species</span>
                <h3 className="font-serif text-3xl mt-2 leading-tight">Native trees, native logic.</h3>
                <p className="text-bark mt-2 text-sm leading-relaxed">Claude-powered recommendations weigh climate, soil and biodiversity—never invasives.</p>
              </div>
            </div>

            {/* Suitability filter */}
            <div className="col-span-12 lg:col-span-5 rounded-2xl overflow-hidden border border-[#E3DFD5] min-h-[260px] relative group">
              <img src={COMMUNITY2} alt="Aerial land" className="absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-700" />
              <div className="absolute inset-0 bg-gradient-to-t from-forest-900/85 to-transparent" />
              <div className="absolute bottom-0 left-0 right-0 p-6">
                <span className="small-label text-bone/85">04 — Filter</span>
                <h3 className="font-serif text-2xl text-bone mt-1">Show only where planting is allowed.</h3>
              </div>
            </div>

            {/* WhatsApp — direct chat (lives in the bento grid for consistent gap-6 spacing) */}
            <div className="col-span-12 lg:col-span-5 rounded-2xl border border-[#E3DFD5] bg-bonewarm p-8 flex flex-col justify-between min-h-[220px]" data-testid="whatsapp-chat-card">
              <div>
                <span className="small-label flex items-center gap-2">
                  <WhatsAppIcon className="w-3.5 h-3.5 text-[#25D366]" /> Talk to us
                </span>
                <h3 className="font-serif text-3xl mt-3 leading-tight">Have a patch in mind? Ping us on WhatsApp.</h3>
                <p className="text-bark mt-3 text-sm leading-relaxed max-w-md">
                  Share a location, a question, or a planting plan — we'll reply with a quick read of the land.
                </p>
              </div>
              <div className="mt-6">
                <a
                  href={WHATSAPP_CHAT_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 rounded-full bg-[#25D366] hover:bg-[#1ebe5b] text-white font-semibold text-sm px-5 py-3 shadow-sm transition-colors"
                  data-testid="whatsapp-chat-btn"
                >
                  <WhatsAppIcon className="w-4 h-4" />
                  Chat on WhatsApp
                  <ArrowRight className="w-4 h-4" />
                </a>
              </div>
            </div>

            {/* WhatsApp — community */}
            <div className="col-span-12 lg:col-span-7 rounded-2xl border border-[#E3DFD5] bg-white p-8 flex flex-col sm:flex-row items-start sm:items-center gap-6 justify-between min-h-[220px]" data-testid="whatsapp-community-box">
              <div className="flex items-start gap-4 max-w-xl">
                <div className="w-12 h-12 rounded-full bg-[#25D366]/15 grid place-items-center shrink-0">
                  <Users className="w-6 h-6 text-[#1f8f4d]" />
                </div>
                <div>
                  <span className="small-label">Community</span>
                  <h3 className="font-serif text-2xl sm:text-3xl mt-2 leading-tight">Join our WhatsApp Community</h3>
                  <p className="text-bark mt-2 text-sm leading-relaxed">
                    Get planting alerts, satellite-season updates, and chat with restorers near you.
                  </p>
                </div>
              </div>
              <a
                href={WHATSAPP_COMMUNITY_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-full bg-forest-700 hover:bg-forest-800 text-bone font-semibold text-sm px-5 py-3 shadow-sm transition-colors shrink-0"
                data-testid="whatsapp-community-btn"
              >
                <WhatsAppIcon className="w-4 h-4" />
                Join Community
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* Trust strip */}
      <section className="py-20 bg-forest-900 text-bone">
        <div className="container-narrow grid grid-cols-1 md:grid-cols-3 gap-12">
          <div>
            <span className="small-label text-bone/60">Transparency</span>
            <h3 className="font-serif text-3xl mt-3 leading-tight">Every layer cites its source.</h3>
            <p className="text-bone/75 mt-3 text-sm leading-relaxed">Confidence scores, satellite tile dates and zoning provenance are visible in every analysis—because trust is the soil this app grows in.</p>
          </div>
          <div>
            <span className="small-label text-bone/60">Accessibility</span>
            <h3 className="font-serif text-3xl mt-3 leading-tight">Low-data, low-jargon.</h3>
            <p className="text-bone/75 mt-3 text-sm leading-relaxed">Color-coded zones, plain-language summaries and a coming offline tile mode so the app works wherever the soil does.</p>
          </div>
          <div>
            <span className="small-label text-bone/60">Stewardship</span>
            <h3 className="font-serif text-3xl mt-3 leading-tight">Built with restorers.</h3>
            <p className="text-bone/75 mt-3 text-sm leading-relaxed">GROWhere is shaped by foresters, ecologists and community organisers — not extracted from data alone.</p>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-24">
        <div className="container-narrow text-center max-w-3xl mx-auto">
          <MapPinned className="w-12 h-12 mx-auto text-forest-700" />
          <h2 className="font-serif text-5xl sm:text-6xl mt-6 leading-tight">Open the map.<br/>Find your patch.</h2>
          <p className="text-bark mt-6 text-lg">It takes 30 seconds to see the trees your neighbourhood is asking for.</p>
          <div className="mt-10">
            <Link to="/map" className="btn-primary text-base" data-testid="bottom-cta">Find planting spots near me <ArrowRight className="w-4 h-4" /></Link>
          </div>
        </div>
      </section>

   <footer className="py-10 border-t border-[#E3DFD5]">
  <div className="container-narrow flex flex-wrap items-center justify-between gap-4 text-sm text-bark">
    <div className="flex items-center gap-2">
      <Leaf className="w-4 h-4 text-forest-700" />
      <span className="font-serif text-lg text-forest-900">GROWhere</span>
      <span className="text-bark/70">— grow what belongs.</span>
    </div>
    <div className="text-xs text-bark/70">Data: Sentinel-2 · Landsat-9 · SMAP · OSM · local registries</div>
    <p className="w-full text-xs text-bark/50 pt-2 border-t border-[#E3DFD5] mt-2">
      GROWhere uses AI and can make mistakes. Please double check responses.
    </p>
  </div>
</footer>
    </main>
  );
}

# Performance Verification & Map/Shipping Fixes — 2026-09-27

Rasti-azmaii report claims vs. code truth, plus the applied fixes and
Lighthouse-oriented performance plan implementation.

## 1. Verdicts (code-verified)

### 1.1 Map rendering & network bypass — CONFIRMED WITH CORRECTIONS
- `apps/web/src/components/LocationMapPicker.tsx:31-53` — CARTO voyager default
  (`https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png`) is real.
  `apps/web/src/components/ShippingRouteMap.tsx:222` — same tile URL is real.
- `ResizeObserver + invalidateSize()` is real in both components.
- Corrections applied this change (were docs/code gaps):
  - Old `tileerror` handler only did `console.warn`, never switched layers.
    Now voyager → dark → osm switches for real after 4 tile errors
    (`LocationMapPicker.tsx` `applyTileLayer`, `ShippingRouteMap.tsx` `addTileLayer`).
  - Old `ResizeObserver` called `invalidateSize()` synchronously per event (burst risk).
    Now debounced trailing call at 120ms (`scheduleInvalidate`).
  - Staged mount recalculation unified to `[50, 200, 500]ms` in both components
    (was `100/350/800` vs `150/500` inconsistently).
  - `TILE_SERVERS.osm` is intentionally kept as last-resort fallback, not removed.

### 1.2 A11y & UI — CONCEPT CONFIRMED, DETAILS CORRECTED
- `apps/web/src/app/globals.css:109-123` — truth is cyan `#06b6d4`,
  `pulse-marker 2s infinite ease-in-out`, scale `1 → 1.08`
  (report claimed `#3b82f6` / `custom-leaflet-marker-pulse` / scale 1.5 — wrong).
- ARIA truth is richer than the report's single string:
  `LocationMapPicker.tsx:283-286` `role="region"`,
  inner map `tabIndex={0} aria-label="ناحیه نقشه قابل جابجایی"`,
  plus two `role="status" aria-live="polite"` banners. No code change needed;
  this document is now the corrected record.

### 1.3 Android / auto-complete shipping — PATHS CORRECTED, LOGIC CONFIRMED
- Report paths were wrong and are corrected here:
  - `app/workers/shipping.py` does NOT exist → real: `app/workers/shipping_worker.py`
  - `app/automation/travel/providers.py` does NOT exist → real: `app/travel/providers.py`
- Report pseudo-functions do NOT exist:
  `create_two_point_gps_evidence` / `utcms_client.post` / `mark_job_as_delivered`.
- Real chain (verified):
  `shipping_worker._auto_complete_due_trips`
  → `gps_shipping_manager.get_due_in_transit_jobs` + `auto_complete_shipping`
  → `utcms_mobile_client.register_end_of_shipping(DocId/docId/gpsList)`
  → 4011 → `mode="self_declared_auto_complete"`
  → `save_shipping_state` + `WaybillJob.status="success"`.
- Beat schedule confirmed: `app/workers/celery_app.py:174-181` `crontab(minute="*/2")`.
- Two-point GPS evidence confirmed: `app/automation/gps_shipping_manager.py:1098-1113`.
- Tracking codes `1350058567` / `1350285211` appear nowhere in the repo;
  no code link from those codes to delivered status could be verified.

### 1.4 Test/build logs in the report — NOT REPRODUCIBLE AS QUOTED
- Quoted `146 passed in 9.72s` over
  `test_api / test_automation / test_shipping_options_pipeline / test_models / test_workers`
  is not reproducible: `test_automation.py`, `test_models.py`, `test_workers.py`
  do not exist; `tests/` holds 155 `test_*.py` files.
- Quoted `Next.js 15.0.0` with `/dashboard`, `/dashboard/waybills` is wrong:
  real `apps/web/package.json` is `next ^15.5.23`; there is no top-level `/dashboard`
  route (real routes below).
- `tests/test_shipping_options_pipeline.py` uncommitted fix
  (`_click_step_next` / `_force_step_transition` / `_wait_for_step_marker` AsyncMocks)
  is real and now committed by this change.
- Fresh evidence from this change (measured 2026-09-27, current checkout):
  - `pytest tests/test_shipping_options_pipeline.py tests/test_shipping_worker.py
    tests/test_automated_shipping_lifecycle.py` → **50 passed**.
  - `npm run typecheck` → clean. `npm run lint` → clean.
  - `npm run build` → success, 19 static routes (see §3.5).

## 2. Fixes applied

- `LocationMapPicker.tsx` — real tile fallback chain, debounced observer,
  unified staged invalidate, `scheduleInvalidate` cleanup on unmount.
- `ShippingRouteMap.tsx` — same tile fallback + debounce, abort-safe `fetchStatus`
  via `AbortController` (no setState after unmount / no wasted in-flight status polls).
- `apps/web/src/app/new/page.tsx` — `LocationMapPicker` is now
  `next/dynamic(ssr:false)` with skeleton (was static import pulling Leaflet
  into the initial `/new` bundle).
- `apps/web/next.config.mjs` — Workbox `StaleWhileRevalidate` for
  `basemaps.cartocdn.com` + `tile.openstreetmap.org` (7d, 200 entries);
  `/api/*` stays `NetworkOnly`.
- `apps/web/src/app/layout.tsx` — `preconnect` (a/b CARTO) + `dns-prefetch` (c/d).
- Images — `priority` + `sizes` on above-fold logos:
  `Header.tsx`, `Sidebar.tsx`, `auth/page.tsx` (already priority, added `sizes`),
  `admin/layout.tsx` (added `sizes`).

## 3. Performance plan implementation

### 3.1 Resource bundling & splitting
- Leaflet (~150KB, browser-only) is now code-split on both entry points:
  `/history` (already dynamic) and `/new` (fixed this change).
- `globals.css:1` `@import 'leaflet/dist/leaflet.css'` stays global (Next global-CSS
  constraint); JS is what was bloating First Load — now deferred until the map mounts.
- Next step (not done): run `ANALYZE=true next build` and split `framer-motion`
  (only used on `/new`) behind a second dynamic boundary if `/new` First Load
  needs to drop below 240KB.

### 3.2 Image optimization
- `sharp 0.35.0` present; logos are SVG (no raster cost).
- Above-fold `next/image` now has explicit `priority` + `sizes` so no layout shift
  and no oversized decode.
- Map tiles bypass `next/image` (Leaflet `<img>`); they are covered by PWA +
  preconnect instead (§3.4).

### 3.3 JavaScript & CSS
- `lucide-react` + `@heroicons/react` imported per-icon (no barrel import) — kept.
- Debounced `invalidateSize` removes ResizeObserver layout thrash on modal open.
- Abort-safe status polling removes overlapping `/shipping/status` requests.

### 3.4 Caching & CDN
- Nginx already sends `Cache-Control: public, max-age=31536000, immutable` for
  `/_next/static/` (`infra/nginx/http-server.conf:118-127`); `/` stays `no-cache`.
- New: Service Worker caches map tiles SWR 7d; API never cached.
- No external CDN for the app shell (single-IP port-80 deployment); tile CDN is CARTO.

### 3.5 Progressive loading (measured)
- Skeletons on both dynamic map boundaries (`h-80` / `h-[350px]` pulse blocks).
- Build output (this change, `npm run build`):
  `/` 8.69kB/222kB · `/new` 18.1kB/240kB · `/history` 16.3kB/213kB ·
  `/batches` 7kB/212kB · shared 105kB · 19 static routes total.
  `/new` still heaviest (form + validation + dynamic map chunk) — expected.

## 4. Files changed
`apps/web/src/components/LocationMapPicker.tsx`,
`apps/web/src/components/ShippingRouteMap.tsx`,
`apps/web/src/app/new/page.tsx`,
`apps/web/next.config.mjs`,
`apps/web/src/app/layout.tsx`,
`Header.tsx`, `Sidebar.tsx`, `auth/page.tsx`, `admin/layout.tsx`,
plus pre-existing uncommitted `globals.css` pulse keyframes and
`test_shipping_options_pipeline.py` step-marker mocks committed here.

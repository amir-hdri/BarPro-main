# Frontend resumed verification — 2026-10-07

Evidence directory: `/tmp/barpro-resume-20261007-frontend/`.
Repository: `/Users/amirheidari/GitHub/BarPro-main`.

## Scope and additional correction

Read CRITICAL_RULES, canonical knowledge graph, architecture/runtime references, UTCMS contracts, the BarPro UI guard skill, previous frontend note and current audit report. Reviewed the outstanding frontend changes and used the existing synthetic Playwright browser fixture. No production API, actual driver, UTCMS mutation, deployment, commit or push was performed by this agent. Only apps/web files were changed; parent owns documentation consolidation.

The new correction in this resumed turn is the shared map tile configuration. Real Chrome screenshots showed CARTO serving HTTP 200 PNG placeholders reading “API KEY REQUIRED”. Image naturalWidth and Leaflet tileload therefore reported ready while no road map was visible. The existing OpenStreetMap .de fallback was visually confirmed to display Tehran streets. Shared defaults now use public OSM .de, with OSM .org as the bounded alternate; unavailable unauthenticated CARTO light/dark choices were removed. Location picker now labels the control as changing map source; PWA caching matches the two OSM hosts. The existing bounded-fallback and stale-event tests were updated for two sources. No API contract changed.

Exact additional files changed in this turn:
- apps/web/src/lib/map-tiles.ts
- apps/web/src/components/LocationMapPicker.tsx
- apps/web/next.config.mjs
- apps/web/test/map-tiles.test.mjs

## Gates

Runtime: Node 20.20.2 from previous isolated runtime, npm 11.19.1. npm ci was executed with this Node20 PATH; no dependency manifest or lockfile change was needed. Existing .env.local was not edited; public API was explicitly NEXT_PUBLIC_API_URL=/api for the isolated browser build.

| Command | Fresh result | Evidence |
|---|---|---|
| npm ci | exit 0, 649 packages installed | install.log |
| npm run lint, after map edit | exit 0 | lint.log |
| npm run typecheck, after map edit | exit 0 | typecheck.log |
| npm test, after map edit | exit 0; 55 passed, 0 failed, 0 skipped | test.log |
| UI guard audit, after map edit | exit 0 | ui-audit.log / ui-audit.json |
| git diff --check -- apps/web | exit 0 | actual tool output |
| npm audit --audit-level=moderate --json | exit 1; 8 high dependency entries | audit.json |
| npm audit --omit=dev --audit-level=moderate --json | exit 0; no known vulnerabilities | audit-runtime.json |
| NEXT_PUBLIC_API_URL=/api npm run build, after map edit | exit 0; Next15.5.27, 21/21 static pages | build.log |

## Audit remediation boundary

The fresh GitHub advisory API reports GHSA-vfj7-8cjw-p6xm, affected braces <=3.0.3, first_patched_version=null, updated 2026-10-02. npm registry latest braces is 3.0.3 and micromatch 4.0.8. Latest Tailwind3 (3.4.19) directly requires chokidar3, micromatch4 and fast-glob3. Current next-pwa10.2.9 and @next/eslint-plugin-next15.5.27 require fast-glob3. These are actively used build/style/lint dependencies, not an unused package branch. Removing only PWA would not remove Tailwind’s required braces path. The suggested audit fixes are breaking migrations/downgrades (Tailwind4, Next ESLint14/PWA6), not a compatible patch. No suppression, risk-hiding override, gate change or forced framework migration was applied. Full CI-CD npm audit remains a blocker; ci-test already has continue-on-error separately. Evidence: advisory.json, braces-registry.json, braces-tree.log and actual registry tool outputs.

## Browser method, initial failures and final assertions

Chrome headless used the real built frontend and disposable fixture at 127.0.0.1:3147, proxying local Next at 3146. Only invented identities/data and local mocked shipping responses were used. Existing unrelated listeners on 3136/3137 were not touched. Public map tile hosts are the only external browser data source. Tests use fresh isolated browser contexts.

The first browser attempt reached the final fuel check then failed because the old script expected the page label and record count as a single text node; current UI renders them separately. Selectors were corrected to the actual navigation and record-count elements. The second run completed behavior assertions but reported Workbox errors reading `waiting`: the copied script explicitly blocked service workers. Re-running with normal service-worker support yielded zero page errors; no fixture dashboard schema or product error handling was changed to hide this. Those attempts are retained in pre-map-fix-* / browser-first-* artifacts.

Before map correction, the complete suite passed after explicitly aborting CARTO requests to validate the existing OSM fallback; screenshots visually proved real roads. The final browser run on the rebuilt OSM-default code passed with exit0, no route interception, and no page errors. It asserted that every displayed tile host was tile.openstreetmap.de. Final desktop and mobile screenshots were opened and visually reviewed: real Tehran streets, planned route and four original/effective markers are visible; no CARTO key placeholder or overlay remains.

Verified scenarios in that complete run:
- actual login via auth UI and tenant identity;
- driver + date filtering and history pagination (25 selected-day records; page2 has5; previous-day boundary excluded);
- fixture-1 delayed timeline cannot replace selected fixture-2 after delay;
- start and finish POST use effective road anchors, explicit422 yields error and no success toast;
- unverified road disables start;
- requested/effective markers remain distinct and map filter is none;
- shipping mobile does not overflow;
- same-page account A→B clears previous dialog, selected driver and tenant text;
- native date input triggers expected driver/date query, 20 independent visible fuel records;
- mobile fuel has no overflow and date font16px;
- page_errors=[] with normal browser service workers.

This is frontend contract/UI evidence with synthetic backend responses, not proof of server shipping authorization, map road snap correctness, physical GPS, actual fuel data, production reachability, capacity, Docker or deployed state. Tile rendering is point-in-time evidence from this host; .org alternate availability in Iran was not validated.

Final verification: build exit0; browser exit0 and page_errors=[]; final browser results in browser-final-results.json. Owned Next PID32870 and fixture PID27423 were stopped after verification (kill succeeded); previous owned Next PID27421 had been stopped before rebuild. Existing3136/3137 listeners were preserved. All deliverable edits are stable; no further work in apps/web is pending from this agent. Full npm audit remains the disclosed dependency blocker.

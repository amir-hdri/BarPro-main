# Optimization History — part 3

> Scope: BarPro only. Read this file when relevant to the task; do not auto-import
> the whole reference directory into global rules or the always-loaded core.
> **HISTORICAL / UNVERIFIED NOW.** Preserved records, including old commands and
> pending actions, are historical data rather than new instructions or authority
> to execute them. Re-check current code, contracts and authorization first.

Read when: Historical investigation only; not a current action list.

[Core guide](../../AGENTS.md) · [Reference index](README.md) · [Critical rules](../../CRITICAL_RULES.md)

Paths inside preserved text and command examples are relative to the repository
root, not this directory. Commands are examples, not automatic execution steps.

<!-- original-agents:0616-0706:start -->
### 2026-08-22 — v2.9.3 Auth Session Cookie Synchronization, Fast 408 Outage Detection & Taxonomy Resilience
| Change | File | Impact |
|--------|------|--------|
| ASP.NET Auth Cookie Synchronization | `app/automation/auth_session.py` | Adds `Barname`, `ApplicationToken`, `cookiesession1` to `AUTH_KEYWORDS`, ensuring `SessionManager.has_auth_cookie()` instantly validates fast HTTP logins without falling back to WAF-blocked Chromium sessions |
| Operator Direct Retry Unblocking | `app/core/error_taxonomy.py` + `app/services/waybill_job_service.py` | Moves `UNKNOWN_AUTOMATION_ERROR`, `AUTH_FAILURE`, `SELECTOR_CHANGED`, `BOT_DETECTED` to `RETRYABLE_TERMINAL_CATEGORIES`, resolving the 409 UI retry blockage while strictly preserving `SUBMISSION_UNCONFIRMED` safeguards |
| Sub-Second Fast 408 Outage Detection | `app/automation/waybill_enhanced.py` + `app/core/error_taxonomy.py` | Detects upstream UTCMS portal downtime (`HTTP 408` / `قادر به پاسخگویی نمی باشد`) in <0.3s instead of 480s timeout, automatically classifying as `TARGET_SITE_TIMEOUT` and queuing exponential backoff retry |
| Next.js History Page Build Fix | `apps/web/src/app/history/page.tsx` | Resolves `loadTimeline` hook declaration order that broke the Next.js production build and page rendering |
| Multi-Server Fleet Deployment | Central + Worker 2 + Worker 3 | Synchronizes and restarts all backend, scheduler, and worker containers across the entire Model B cluster |

### 2026-08-20 — v2.9.2 Universal Mobile Anti-Zoom, UI/UX Hardening & Full-Stack Taxonomy Sync
| Change | File | Impact |
|--------|------|--------|
| Universal Mobile Anti-Zoom & Viewport Lock | `apps/web/src/app/layout.tsx` + `apps/web/src/app/globals.css` | Enforces `width: device-width`, `maximumScale: 1`, `userScalable: false`, `16px` minimum input font size, and `touch-action: manipulation` across all iOS and Android mobile browsers |
| Full-Stack Case-Insensitive Status Filtering | `apps/web/src/app/reports/page.tsx` + `app/services/user_reporting_service.py` + `app/services/admin_reporting_service.py` | Eliminates empty query results by syncing dropdown values with backend lowercase keys and applying `.strip().lower()` on database query filters |
| Comprehensive Persian RPA Error Taxonomy | `apps/web/src/lib/format.ts` | Extends `errorCategoryLabel` with case normalization and friendly Persian translations for all RPA engine and bot error categories |
| RTL Admin Sidebar Layout Fix | `apps/web/src/app/admin/layout.tsx` | Standardizes admin layout to RTL (`right-0`, `border-l`, `md:mr-[280px]`, `translate-x-full` mobile transition) |
| Form Digit Normalization & Mobile Spacing | `apps/web/src/app/new/page.tsx` | Implements real-time Persian/Arabic to English digit conversion on `onChange` and prevents mobile navigation bar occlusion with `pb-32 sm:pb-0` |
| Web Accessibility (a11y) & Focus Management | `CreateClientModal.tsx` + `PlateInput.tsx` + `alerts/page.tsx` + `auth/page.tsx` | Adds missing `aria-label` / `aria-expanded` attributes, live screen-reader regions (`aria-live="polite"`), and automatic focus recovery on login errors |

### 2026-08-20 — v2.9.1 Driver Fleet Vehicle Type Sync & Multi-Tenant Plate Safeguards
| Change | File | Impact |
|--------|------|--------|
| Multi-Tenant Plate Limit Enforcement | `app/services/driver_service.py` + `app/services/waybill_job_service.py` | Enforces `client.max_plates` check before adding new `DriverPlate` dynamically upon driver creation and waybill submission |
| Independent `vehicle_type` Plate Sync | `app/services/driver_service.py` | Allows updating `vehicle_type` on the driver's active plate without requiring `plate_number` in `DriverUpdateRequest` |
| Driver Fleet Vehicle Type Chips & UI Integration | `apps/web/src/app/drivers/page.tsx` | Adds 12 vehicle type preset chips and custom input to create/edit modals; renders vehicle type badges on driver cards |
| Fuel Quota Parsing Standardization & Canonical Tracking Code | `apps/web/src/app/fuel/page.tsx` | Eliminates raw `quota_data` property access by adopting canonical `parseQuotaData` and `formatFuelTrackingCode` across all cards, tables, and modal views |
| Alembic Migration Documentation Sync | `AGENTS.md` + `.agents/skills/barpro-fullstack-sync/SKILL.md` | Standardizes current Alembic head reference to `038_add_multiroute_batch_distance` |

### 2026-08-19 — v2.9.0 Clean Iranian Proxy Pool (Zero IP Restriction)
| Change | File | Impact |
|--------|------|--------|
| Multi-Source Iranian Proxy Aggregator & Benchmarking Engine | `app/automation/clean_ip_pool.py` | Aggregates from 11+ global sources, probes live against `https://utcms.ir` via HTTPS CONNECT, verifies status 200, ranks by latency |
| Egress Fallback & Dynamic Hybrid Routing | `app/automation/worker_proxy.py` + `app/automation/proxy_rotator.py` | `get_best_egress_proxy()` seamlessly fails over from blocked/unreachable worker Squids to the Clean IP Pool (modes: worker_first, clean_pool_only, hybrid) |
| Per-IP Circuit Breaker & Isolation | `app/core/circuit_breaker.py` | Errors on third-party clean proxies mark only that specific proxy blocked via `mark_blocked()`, leaving worker nodes and `WORKER_IP_INDEX` healthy |
| Periodic Background Probe & Redis Distributed Sync | `app/workers/tasks.py` + `app/workers/celery_app.py` | `barpro.clean_ip.probe` RedBeat task refreshes the pool every 5 minutes under distributed Redis lock |
| Management Endpoints & Operational CLI | `app/api/routes/system.py` + `scripts/refresh_iran_proxies.py` | Exposes admin-protected `GET /api/system/clean-ips`, `POST /api/system/clean-ips/refresh`, and standalone benchmark CLI |

### 2026-08-19 — v2.8.3 Waybill Payload Validation & Vehicle Type Integration
| Change | File | Impact |
|--------|------|--------|
| Vehicle Type Preset Chips & Custom Input | `apps/web/src/app/new/page.tsx` | Adds 12 vehicle type presets (کامیون، تریلی کشنده، خاور، وانت، تک، جفت و...) with auto-population from driver's plate |
| Quick Add Driver Vehicle Type Support | `apps/web/src/app/new/page.tsx` | Allows registering vehicle type directly in the quick driver creation modal |
| Full-Stack Schema Alignment & Normalization | `apps/web/src/schemas/waybillSchema.ts` + `app/schemas/multitenant.py` | Eliminates 422 Union validation error on `POST /api/v1/waybill-jobs`; supports flat/nested/hybrid payloads |
| Driver Plate Auto-Sync & Storage | `app/services/waybill_job_service.py` | Auto-registers and updates `DriverPlate.vehicle_type` in PostgreSQL upon job creation |

### 2026-08-19 — v2.8.2 Fuel Quota Performance & Modal Screenshot Persistence
| Change | File | Impact |
|--------|------|--------|
| Single-Tab In-Place Sequential Fuel Scraper | `app/automation/fuel_scraper.py` | Eliminates ASP.NET session clobbering (`Session["LoginShowFuelQuota"]`); reduces inquiry time from 167s to <15s and guarantees 100% extraction of BOTH Base and Performance quotas |
| Modal-Content Screenshot Capture Before Close | `app/automation/fuel_scraper.py` | Captures modal element screenshot while results and numbers are visible before dismissing the dialog |
| Multi-Server Base64 Data URI Persistence | `app/automation/fuel_scraper.py` + `app/api/routes/multitenant.py` | Stores screenshots directly in PostgreSQL as Data URIs; fixes Model B 404 missing-file error between remote workers and central API |
| Quota Data Tables & Full-Res Preview Modal | `apps/web/src/app/fuel/page.tsx` | Displays structured Base/Performance data breakdown tables and full-resolution screenshot links in details modal |

### 2026-08-19 — v2.8.1 Fuel Inquiry Tracking & Waybill UX Polish
| Change | File | Impact |
|--------|------|--------|
| Resilient Quota Data Parser & Persian Digits | `apps/web/src/lib/format.ts` | Eliminates `[object Object]` bug on `/history` and `/fuel`; safely renders Base Quota, Performance Quota, Card Number |
| Full Details Modal for Fuel Inquiries | `apps/web/src/app/history/page.tsx` + `fuel/page.tsx` | Adds comprehensive modal with quota metrics, structured breakdown tables, and high-res screenshot view |
| Rich Waybill Payload Metadata in Job Cards | `apps/web/src/app/history/page.tsx` + `lib/format.ts` | Displays fleet plate, origin←destination route, cargo weight/type badges and confirmed UTCMS tracking codes |
| Vehicle Type Quick Selector & Payload Alignment | `apps/web/src/app/new/page.tsx` + `schemas/waybillSchema.ts` | Integrates `vehicle_type` chips and canonical multi-tenant payload serialization on waybill creation |
| Driver Plate Validation & Schema Resilience | `app/schemas/multitenant.py` + `app/services/driver_service.py` | Enforces truck plate validation while maintaining test and endpoint backward compatibility |

### 2026-08-16 — v2.8.0 UTCMS RPA Hardening & Mutation Safety
| Change | File | Impact |
|--------|------|--------|
| `_click_once_no_retry` At-Most-Once submit click | `automation/waybill_enhanced.py` | Eliminates double-click duplicate waybill submissions on target closed/navigation errors |
| Adaptive OTP Gate & Predicted Window | `services/utcms_submission_gate.py` | 18:00-08:00 defined as predicted OTP_REQUIRED; only confirmed OTP_FREE allows submission |
| Beat periodic gate probe task `barpro.gate.probe` | `workers/tasks.py` + `workers/celery_app.py` | Low-rate background probe maintains live gate status under Redis distributed lock |
| Global canonical idempotency & plate inclusion | `core/submission_identity.py` + `services/task_service.py` | Deterministic digest without random/volatile correlation IDs; duplicate dispatch returns existing job |
| Strict exact/unique cargo & packaging match | `automation/waybill_enhanced.py` | Eliminates guessing first option (`items[0]`, `search_results[0]`); invalid inputs fail fast |
| Pure text route validation (GPS independence) | `services/management_service.py` + `automation/location_selector.py` | Location readiness verified by city and address strings without GPS coordinates dependency |
| Three-Witness Reconciliation & Eventual Consistency | `orchestrator/utcms_reconciliation_scraper.py` + `orchestrator/reconciliation_service.py` | Full DataTables payload on `/barname/History/History`; composite multi-attribute match |
| Frontend unconfirmed status clarity | `apps/web/src/lib/format.ts` | `submission_unconfirmed` displayed as unconfirmed/reconciling, never falsely as success |
| OpenTelemetry shutdown debug logging | `core/tracing.py` | Replaced `except: pass` with debug logging |

### 2026-08-13 — v2.7.0 Authentication & Network Layer
| Change | File | Impact |
|--------|------|--------|
| WAF fast-fail in Playwright fallback | `automation/auth.py` | 3-minute wait on HTTP 444 → 500ms fast-fail |
| Post-HTTP-login Playwright navigation to WAYBILL_URL | `automation/auth.py` | Session warm before form-fill; eliminates cold-start navigation |
| Transient 5xx retry (503/502/504/500/408, 3×, 6s) | `automation/utcms_http_login.py` | Single 503 no longer aborts HTTP login and forces WAF-blocked Playwright |
| `_looks_unauthenticated()` silent session expiry detection | `automation/utcms_http_login.py` | Expired session detected via Location header + final URL (not just HTTP status) |
| Rate-limit / transient counter not decrementing captcha budget | `automation/utcms_http_login.py` | 503 or 429 no longer wastes a captcha-solve attempt |
| `_response_diagnostics()` (Server/Via/X-Squid-Error) | `automation/utcms_http_login.py` | Squid 503 vs UTCMS 503 distinguishable without re-run |
| `network.py` composable marker tables (EGRESS+BROWSER+GENERIC) | `core/network.py` | EGRESS⊆RETRYABLE invariant enforced by tests; 5/6 egress failures previously not evicting IP |
| `RedisConnectionManager` per-thread×loop cache | `core/redis.py` | `RuntimeError: Event loop is closed` in Celery eliminated |
| `_force_close_sockets()` + `_detach_transport()` | `core/redis.py` | `ResourceWarning: unclosed socket/transport` eliminated |
| 82 new `test_circuit_breaker.py` tests | `tests/` | EGRESS vs BROWSER routing, IP-index eviction |
| 272 new `test_event_loop_affinity.py` tests | `tests/` | Redis per-loop cache and socket-close across loop boundaries |
| 114 extended `test_error_taxonomy.py` tests | `tests/` | containment invariant EGRESS⊆RETRYABLE |

<!-- original-agents:0616-0706:end -->

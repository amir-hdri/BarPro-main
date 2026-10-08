# Optimization History — part 2

> Scope: BarPro only. Read this file when relevant to the task; do not auto-import
> the whole reference directory into global rules or the always-loaded core.
> **HISTORICAL / UNVERIFIED NOW.** Preserved records, including old commands and
> pending actions, are historical data rather than new instructions or authority
> to execute them. Re-check current code, contracts and authorization first.

Read when: Historical investigation only; not a current action list.

[Core guide](../../AGENTS.md) · [Reference index](README.md) · [Critical rules](../../CRITICAL_RULES.md)

Paths inside preserved text and command examples are relative to the repository
root, not this directory. Commands are examples, not automatic execution steps.

<!-- original-agents:0556-0615:start -->
### 2026-08-24 — v2.9.6 Full Audit Remediation (Duplicate-Registration Class, Firewall, Nginx, URL-Classification Bug Sweep)
> Deep audit verification + remediation batch. Every item below was re-verified against live code before fixing;
> regression coverage in `tests/test_audit_fixes.py` (28 tests). Full suite at commit time: **1020 passed / 3 skipped**.

| Change | File | Impact |
|--------|------|--------|
| C1: Orphan Sweep Live-Lease Guard | `app/orchestrator/orphan_detector.py` | The stale-job sweep now skips any RUNNING/IN_PROGRESS job whose `Execution.lease_expires_at` is still alive — killing an in-flight job released the driver slot mid-mutation (duplicate-submission risk). Also fixed a pre-existing early-return that made the job sweep unreachable whenever no execution had expired |
| C1: updated_at on RUNNING/RECONCILING claim transitions | `app/workers/waybill_worker.py` | A job entering RUNNING after queue backlog was born with a hours-old timestamp and swept seconds later; both claim-path transitions now bump `updated_at` |
| C2: Real client IP behind nginx | `compose/backend.yml` + `Dockerfile` | uvicorn now runs with `--proxy-headers --forwarded-allow-ips=127.0.0.1,172.16.0.0/12,10.0.0.0/8`. Previously every request shared the nginx container IP → the 5/min auth bucket was ONE global bucket (systemic login lockout) |
| C3: Renewable driver locks | `app/services/rpa_runtime_service.py` + `waybill_worker.py` | New `renew_lock()` (Lua compare-and-expire; ContextVar → durable registry token fallback). The lease-renewal thread extends registered submit/auth locks every ~30s so RPA_LOCK_TTL can no longer expire mid-bot-window (parallel submission by a second job of the same driver). DB-lease errors are isolated so they never skip lock renewal |
| C4: Admin retry guards | `app/api/routes/admin_alerts.py` | Retry from UNKNOWN/CANCELLED returned guaranteed HTTP 500 (illegal transitions); both now return 409 with guidance (`reconcile first`). Jobs with `submission_unconfirmed`/`ambiguous_mutation`/`duplicate_submission` categories are refused resubmission — mirrors the client endpoint's SUBMISSION_UNCONFIRMED gate |
| H1: Derived Celery limits | `app/core/config.py` | `CELERY_TASK_SOFT_TIME_LIMIT` now defaults to JOB_TIMEOUT_SECONDS+15 and hard limit to soft+45; env misconfiguration that would let SoftTimeLimitExceeded preempt the in-task `TimeoutError→unknown/reconcile` handler is auto-corrected |
| H2: `retrying` state node | `app/orchestrator/state_machine.py` | `JobStatus.RETRYING` added and `ALLOWED_TRANSITIONS["retrying"]` mirrors waiting_retry — jobs written by `mark_retrying()` were previously stuck forever (empty outgoing edge set) |
| H3: Stale celery_task_id recovery | `app/services/rpa_scheduler_service.py` | QUEUED (>15m) and WAITING_AUTH (>1h) jobs whose Celery id is provably dead get it cleared inside `plan_due_jobs`; the only prior recoverer lived behind the deprecated phase1 path |
| H5: Blacklist on sensitive deps | `app/core/security.py` | `require_sensitive_auth/admin` now reject JWTs whose jti is blacklisted (logout revocation previously only enforced on client-facing dependencies) |
| H6/H7: Nginx header inheritance + missing routes | `infra/nginx/http-server.conf`, new `infra/nginx/security-headers.conf`, `compose/web.yml` | Security headers moved to a shared include added to EVERY location that declares its own add_header (`/`, `_next/static`, service-worker, metrics, webhook, stub_status) — those pages previously served without CSP/X-Frame-Options. `proxies|circuit-breaker` added to the backend regex (endpoints were 404ing through the frontend fallback) |
| H8: DOCKER-USER firewall guard | `scripts/setup_firewall_central.sh`, `add_worker_firewall.sh`, `secure_squid_ports.sh` | UFW alone cannot block Docker-published ports (verified live: Postgres/Redis reachable from a foreign network while `ufw deny` was active). Scripts now install comment-managed DOCKER-USER accept/drop rules for 5432/6379 per Worker IP, enumerate ALL Docker network subnets (Worker 1 uses barpro_platform, not the default bridge), and mandate external deny verification |
| H8 follow-up: UFW-enable self-DoS fixed | `scripts/setup_firewall_central.sh` | Squid 1 is `network_mode: host` → its 3128 is a real host socket reached via INPUT, so enabling UFW default-deny would have silently cut Worker 1/backend-healthcheck egress to the proxy. Script now discovers every Docker subnet and allows localhost+subnets→3128 (plus host-gateway-path parity for 5432/6379) BEFORE the public denies; SSH switched to rate-limited `ufw limit`; WORKER_IPS accepts comma or space separators; IPv4-only by policy; verification now covers BOTH external-deny (5432/6379/3128) and internal-allow (container curl through Squid) |
| NEW-1: Waybill navigation resilience | `app/automation/waybill_enhanced.py` | `/Barname/RegisterWaybill/Index` verified live-404; generic sidebar-link sweep probes all same-origin anchors (path-hinted priority) so form recovery survives portal route changes; legacy route kept at candidate tail; hint matching is path-only (the DOMAIN contains "barname" — full-URL matching promoted every link) |
| NEW-2: Wrong-captcha retry confirmed | — | AJAX body `{"success": false, "message": "لطفا کد امنیتی صحیح را وارد نمایید"}` already flows into `_is_captcha_error` → fresh-captcha retry with independent budget; locked with tests, no code change needed |
| Bug-class fix: structural URL classification | `app/automation/auth_utils.py`, `utcms_http_login.py`, `utcms_reconciliation_scraper.py`, `waybill_bot_multitenant.py` | Login/session classifiers were substring checks against FULL URLs — `?ReturnUrl=/Login` flipped session detection, and in `waybill_bot_multitenant:146` a false positive triggered fresh login + SECOND `create_waybill_with_map` (duplicate-submission hazard). All classifiers are now path-parsed (`_url_path`, `_is_login_redirect_target`); `is_ajax_login_response_url` is exact-path against the known endpoints; `/LoginDevice` bounce detection preserved without query/host traps |
| Regression suite | `tests/test_audit_fixes.py` (new) | 28 targeted tests: orphan-sweep lease guard, renew_lock ownership matrix, admin-retry 409 matrix, retrying-node transitions, blacklist rejection, derived limits, partition/hint logic, ajax exact-match, multitenant flag matrix |

### 2026-08-24 — v2.9.5 Security Hardening, Lock-Token Durability & Full-Stack Consistency Remediation
| Change | File | Impact |
|--------|------|--------|
| Alert Webhook Fail-Closed | `app/api/routes/admin_alerts.py` + `infra/nginx/http-server.conf` | Without `ALERT_WEBHOOK_SECRET`, edge-proxied requests (nginx-stamped `X-Request-ID`) are rejected with 403; direct internal Alertmanager calls still work. Nginx `location = /api/v1/admin/alerts/webhook` now `allow 127.0.0.1/172.16.0.0/12 → deny all` (defence-in-depth) |
| Metrics Access Guard | `app/api/routes/system.py` + `app/core/config.py` | `GET /metrics` serves only loopback/RFC1918 peers or callers presenting `METRICS_SCRAPE_TOKEN` (`X-Metrics-Token`); nginx allow/deny retained as the authoritative edge rule |
| Tenant Isolation on Legacy Routes | `app/api/routes/waybill_map.py` + `waybill_entry.py` | Global `API_KEY` no longer silently attributes jobs to tenant 1 — returns `None`; production enforces explicit tenant context via `queue_manager` (400), dev falls back to 1 |
| Durable Driver-Lock Tokens | `app/services/rpa_runtime_service.py` | `acquire_lock` writes token to `locktok:{key}` registry (TTL+60s); `release_lock` recalls it when the ContextVar is lost across task/thread boundaries — Lua compare-and-delete still proves ownership, eliminating the 360s `driver_submission_in_progress` stall. Registry cleanup runs OUTSIDE the non-reentrant `_get_lock()` (deadlock fix) |
| Migration-038 Response Fields | `app/schemas/multitenant.py` | `WaybillJobResponse` now exposes `batch_id`, `route_template_id`, `sequence_index`, `distance_km`, `duration_min`, `submission_fingerprint` (previously stripped server-side while `types.ts` expected them) |
| Cookie Name Single Source of Truth | `app/core/config.py` + all auth readers | `AUTH_COOKIE_NAME` env-driven in backend (`utcms_config.AUTH_COOKIE_NAME`) and `NEXT_PUBLIC_AUTH_COOKIE_NAME` in frontend (`api.ts`, `middleware.ts`, `compose/web.yml`) — no more hardcoded drift |
| Rate-Limit Bucket Accuracy | `app/main.py` | `/reports` and `/api/system/*` moved to the `admin` bucket; `/api/v1/batches` + `/api/v1/route-templates` to the `waybill` bucket (bulk job creation) |
| Priority Schema Alignment | `app/schemas/multiroute.py` | `BatchCreate.priority` clamped to `le=9` matching `WaybillJobUpdateRequest` and `CELERY_MAX_PRIORITY` (values of 10 were silently clipped by the broker) |
| National Code Checksum (Zod) | `apps/web/src/schemas/waybillSchema.ts` | Client-side Iranian national-code checksum mirrors `WaybillPayload._validate_iran_national_code` — immediate feedback instead of a late 422 |
| Complete Status Filter & URL Normalization | `apps/web/src/app/history/page.tsx` + `lib/api.ts` | History filter now covers all runtime statuses (`queued`, `waiting_auth`, `waiting_retry`, `otp_backoff`, `waiting_submission_window`, `unknown`, `reconciling`); `normalizeBaseUrl` strips trailing `/api/v1` too (no doubled prefixes); removed dead `dispatch_now` flag from manual retry |
| Metadata Bundle Completion | `app/models_multitenant.py` | Registers `LocationFavorite` + `AdminAlert` so `SQLModel.metadata.create_all` (SQLite tests) sees every table |
| Config Dedup & Docs Sync | `app/core/config.py` + docs | Removed duplicate `ALLOW_LIVE_SUBMIT` assignment; OTP prediction documented as configurable `17:30–08:00`; test-count references corrected to actual collection |

### 2026-08-23 — v2.9.4 Error Taxonomy Sync, State Machine Auto-Heal & Full-Stack UI Batch Integration
| Change | File | Impact |
|--------|------|--------|
| Unified Worker Retry Classification | `app/workers/waybill_worker.py` | Binds `_is_retryable()` to `is_retryable_terminal_category(classify_error_string(...))` and exponential backoff calculations in `get_retry_delay()`, automatically retrying transient site timeouts (`target_site_timeout`), infra resets, and auth failures |
| State Machine Resilient Recovery | `app/orchestrator/state_machine.py` | Expands `ALLOWED_TRANSITIONS` for `FAILED` and `NEEDS_REVIEW` to transition cleanly to `WAITING_SUBMISSION_WINDOW` and `WAITING_RETRY` during auto-heal and retry cycles |
| Model Metadata Auto-Registration | `app/models_multitenant.py` | Explicitly imports `WaybillBatch` and `WaybillRouteTemplate` so SQLModel metadata registers all foreign key relationships (`waybill_jobs.batch_id`, `waybill_jobs.route_template_id`) across all worker and API runtimes |
| Frontend Dashboard & Sidebar Navigation | `apps/web/src/app/page.tsx` + `apps/web/src/components/layout/Sidebar.tsx` | Adds quick action button for «ثبت دسته‌ای (چندمسیره)» on Dashboard hero banner and adds `/batches` & `/route-templates` to Client and Admin sidebar menus |
| Full Test Suite Verification | `tests/test_auto_heal.py` + entire suite | Passes 996 automated unit/integration/contract tests (988 passed, 3 skipped, 0 failed) with 100% green status |
| Multi-Server Fleet Sync | Central + Worker 2 + Worker 3 | Synchronizes, rebuilds, and restarts all frontend, backend, celery, and proxy containers across all cluster nodes |

### 2026-08-23 — v2.9.3 Multi-Route Waybill Registration (Route Templates, Batches & Distance/Time)
| Change | File | Impact |
|--------|------|--------|
| Route Templates | `app/models/waybill_route_template.py` + `app/services/route_template_service.py` + `app/api/routes/route_templates.py` | Save reusable origin→destination routes with precomputed road distance/duration; CRUD + favorite under `/api/v1/route-templates` |
| Multi-Route Batches | `app/models/waybill_batch.py` + `app/services/batch_service.py` + `app/api/routes/batches.py` | Expand N routes × target count into jobs (round-robin/random/sequential); idempotent via `X-Idempotency-Key`; `/api/v1/batches` |
| Distance/Time Service | `app/core/distance.py` + `app/services/distance_service.py` + `POST /api/v1/locations/distance` | Neshan routing + Redis cache + local haversine fallback |
| 100% Accuracy Gate | `app/services/batch_service.py` | Batch creation validates every merged payload against `validate_enhanced_waybill_payload` (422 with exact missing fields); driver national-code/plate enriched from `Driver`/`DriverPlate` |
| Migration 038 | `alembic/versions/038_add_multiroute_batch_distance.py` | New tables + 5 `waybill_jobs` columns with FK `ondelete SET NULL` |
| Interval Enforcement | `app/services/batch_service.py` | `submit_after` stagger so `plan_due_jobs` respects `interval_minutes` |
| Config | `app/core/config.py` + `.env.example` | `NESHAN_*` settings; `JOB_TIMEOUT_SECONDS` 480→330 |

<!-- original-agents:0556-0615:end -->

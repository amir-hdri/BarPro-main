# Runtime contracts recorded in the original guide

> Scope: BarPro only. Read this file when relevant to the task; do not auto-import
> the whole reference directory into global rules or the always-loaded core.
> **REFERENCE SNAPSHOT, NOT LIVE EVIDENCE.** Original claims and dates are preserved.
> Even headings such as “Current” and statuses such as “Fixed” reflect the source
> guide, not a fresh verification. Resolve drift against current code and contracts
> before acting; deployment state requires timestamped runtime evidence.

Read when: API, submission, reconciliation, queues, schema, OTP, CAPTCHA or shipping changes.

[Core guide](../../AGENTS.md) · [Reference index](README.md) · [Critical rules](../../CRITICAL_RULES.md)

Paths inside preserved text and command examples are relative to the repository
root, not this directory. Commands are examples, not automatic execution steps.

<!-- original-agents:0227-0354:start -->
## Current Runtime Contracts

### Canonical API Paths

| Area | Current path |
|---|---|
| Liveness / public sanitized readiness | `GET /healthz`, `GET /readyz` |
| Detailed readiness | `GET /api/v1/admin/readyz` (admin only) |
| Authentication | `/api/v1/auth/*`, `/api/v1/admin/login` |
| Waybill jobs | `/api/v1/waybill-jobs` and its retry/requeue/timeline/log/screenshot subpaths |
| Fuel inquiries | `/api/v1/fuel-inquiries` |
| Clean IP operations | `/api/system/clean-ips`, `/api/system/clean-ips/refresh` (admin only) |
| GPS shipping lifecycle | `POST /shipping/coordinates`, `POST /shipping/start`, `POST /shipping/step` (**returns 410 Gone**), `POST /shipping/finish`, `GET /shipping/status/{job_id}` — all guarded by `require_sensitive_auth` |
| Realtime | `WS /ws/waybill` with cookie auth and optional task/batch/correlation filters |
| OTP intake (mobile transport) | `POST /api/v1/otp/sms-forwarder`, `POST /api/v1/otp/sms-forwarder/{driver_phone}` (multi-channel recipient phone attribution: path, `?driver_phone=...`, `X-Driver-Phone` header, or body; fallback to single-flight pending job; 422 `AMBIGUOUS_OTP` guard), `POST /api/v1/otp/sms-gateway` (HMAC-signed `BP1#phone#timestamp#code#signature` envelope), `POST /api/v1/otp/webhook`, `POST /api/v1/otp/submit-manual`, `GET /api/v1/otp/latest`, `GET /api/v1/otp/securesms-config`. Forwarder/gateway require `OTP_WEBHOOK_SECRET` and fail closed (503) without it; 16 KB body cap, a `HEALTH_CHECK` probe. Durable, ordered, replay-safe intake lives in `app/services/otp_delivery.py`. |

Do not use stale paths such as `/api/system/health`, `/ws/jobs/{client_id}` or
`/ws/admin/stream`. There is no distinct POST cancel contract:
`DELETE /api/v1/waybill-jobs/{job_id}` permanently deletes a job.
`/shipping/info` and `/shipping/auto-complete` do **not** exist anywhere in
`app/` — the router in `app/api/routes/shipping_gps.py` exposes exactly the five
routes above, and the frontend calls only `/shipping/status/{jobId}`,
`/shipping/start` and `/shipping/finish`. `POST /shipping/step` is a deliberate
410: intermediate GPS stays disabled until a live UTCMS ping contract is proven.
Automatic trip completion is a Celery Beat task
(`shipping.auto_complete_due_trips`), not an HTTP route.

### Submission State and Reconciliation

A successful browser response is not immediate proof of registration. The safe flow is:

`running → unknown → reconciling → success | needs_review`

Registration proof is the two-witness rule defined in
`docs/UTCMS_CONSTRAINTS.md`: an RPA tracking code and the same code persisted
in `result_json`. `JobStateMachine` additionally requires
`mutation_status=confirmed` and `reconciled_at` (set by read-only History
reconciliation) before `success`. Unknown outcomes are reconciled with delays
`15,45,120,300` seconds and are never automatically resubmitted after the
bounded window.

### Queue Topology

- Every RPA Worker runs with effective concurrency `1`.
- Worker 1 consumes base queues plus `waybill_tasks_1`, `rpa_auth_1`,
  `rpa_submit_1`, `reconciliation_tasks_1`, `scheduled_tasks_1`, and
  `barpro.fuel.inquiry`.
- Remote Workers consume the corresponding `*_2` or `*_3` queues and the fuel queue.
- `celery_scheduler` consumes **only** `rpa_scheduler`.
- Beat publishes periodic messages (including `shipping.auto_complete_due_trips` every 2 minutes for in-transit trip auto-completion); it does not consume gate, proxy, cleanup, or
  orchestrator tasks.
- Active bindings, backlog, and registered IP indices are runtime facts. Verify with
  Celery inspection, Worker Registry, and metrics rather than inferring them from env examples.

### Data Model

SQLModel primary keys are integer IDs. Public identifiers such as `job_id`,
`batch_id`, `intent_id`, and `execution_id` are strings, not UUID primary keys.
`WaybillJob` stores `payload_json`, `result_json`, retry, mutation, and
reconciliation fields. Operational aggregates include `DispatchIntent`,
`Execution`, `WorkerRegistry`, `ProxyEndpoint`, `UploadBatch`, and
`UTCMSSystemObservation`. `FuelInquiry` stores quota JSON and a screenshot
URL/Data URI and has no direct tracking-code column.

### OTP and CAPTCHA

- The `17:30–08:00` window (config defaults `PREDICTED_OTP_REQUIRED_START_HOUR=17`,
  `START_MINUTE=30`) is a configurable **prediction** of
  `OTP_REQUIRED`, not a guaranteed UTCMS schedule. Only a current
  `OTP_FREE` observation permits submission; unknown/degraded states fail closed.
- **Documented exception (mobile/OTP transport, 2026-09-23):** when
  `UTCMS_TRANSPORT` is `mobile`/`shadow`, or the job payload sets
  `transport=mobile` or `allow_otp_flow=true`, the pre-mutation gate may be
  skipped so execution can create the document and receive the driver OTP
  challenge (`isOtpNeeded`), then complete via `IssueDocumentByOtp`. Web RPA
  without that flag remains fail-closed on `otp_required` / `gate_unknown`.
  This is an intentional contract change from pure `OTP_FREE`-only mutation;
  do not remove the flag without restoring fail-closed behavior for mobile.
- **Event-Driven OTP Wake-Up & Lease Locking (2026-10-05):**
  - Durable ingestion (`app/services/otp_delivery.py`) writes to `rpa:otp:stream` via Lua transaction and triggers non-blocking wake-up.
  - Background consumer (`app/services/otp_wakeup_consumer.py`, consumer group `barpro_otp_group`, `XACK`) awakens stuck drafts (`WAITING_OTP` or `UNKNOWN - otp_required`) when an SMS arrives late (e.g. at second 125 after the 120s worker loop expires), resolving the late SMS race condition.
  - Concurrency is protected by a distributed lease lock (`lock:otp:issue:{job_id}`, TTL 30s) via `reserve_otp_issue_lease` / `release_otp_issue_lease` (`app/automation/otp_keys.py`), guaranteeing single-flight mutation between Celery worker and webhook issuer.
  - Atomic invalidation (`consume_scoped_otp`) purges job, phone, pending_doc session (`rpa:job:pending_doc:{job_id}`), and phone pending set immediately on successful issuance.
  - Shared GSM gateway / SIM fallback: `resolve_single_flight_pending_phone` matches incoming SMS lacking driver phone to a sole pending waybill; if multiple waybills are pending, it strictly fails closed with HTTP 422 (`AMBIGUOUS_OTP`).
  - Clock skew & Iranian DST resilience: `sms_received_at` normalizes the 1-hour daylight saving shift resulting from Iran's 1402 time change abolishment on unpatched phones (+/- 3600s with 90s tolerance); automation anchors on server `ingested_at` rather than client device clock. Worker loop monitors `completed_otp:{job_id}` for zero-latency exit.
- **Two-Flavor Mobile Relay Topology (Driver & Hub, 2026-10-10):**
  - **Driver flavor** (`applicationId ir.barpro.fleet.smsforwarder.driver`): intercepts UTCMS OTP SMS,
    signs it with HMAC-SHA256 truncated to 16 bytes into the ASCII envelope
    `BP1#phone#timestamp#code#signature` (`SmsFallbackEnvelope.encode`), and dispatches it over GSM
    SMS to the Hub phone with no mobile internet (`SmsForwardRepository.kt:521-575`). It is **not**
    zero-config: the webhook token (to sign), the Hub SIM number, and `driverPhone` must all be set,
    otherwise `canSendSms` is false and nothing is sent.
  - **Hub flavor** (`applicationId ir.barpro.fleet.smsforwarder.hub`): receives `BP1#...`, verifies
    the HMAC locally in constant time (`MessageDigest.isEqual`) and drops forgeries before they take
    an outbox slot (`SmsForwardRepository.kt:384-414`), queues the rest in the Room outbox, and
    delivers to `POST /api/v1/otp/sms-gateway`. The server re-verifies authoritatively with
    `hmac.compare_digest` (`app/api/routes/otp_forwarder.py:192-195`).
  - Both flavors build from the single `app/src/main` source set. There is no per-flavor source
    directory and no role-specific UI; only `applicationId`, `versionNameSuffix` and three
    `BuildConfig` fields differ (`app/build.gradle.kts:39-63`).
  - **Carrier-matched routing**: `CarrierDetector.resolveHubNumbers` prefers build-time defaults
    (`-PBARPRO_HUB_PHONE_MCI` / `-PBARPRO_HUB_PHONE_IRANCELL`) and otherwise reads operator config
    (`fallbackServerPhoneNumber` = Hub MCI leg, `hubIrancellPhoneNumber` = Hub Irancell leg).
    `resolveRoute` then makes the same-carrier SIM primary and the other the failover.
    **With only one number filled in, delivery degrades to a single destination and failover is
    inert** — the repository failover branch requires `failover != primary`.
  - **Transport**: HTTP by design for this deployment. Nginx listens on port 80
    (`infra/nginx/nginx.conf:70`); the `listen 443 ssl` block is commented out (lines 94-104). The
    app refuses an `http://` endpoint unless the operator enables `allowCleartextTransport`, which
    defaults to false so a cleartext endpoint is never used by a typo. Accepted consequence: the
    envelope's authenticity is covered by HMAC, but the webhook token and the OTP are not encrypted
    in transit, so network-level restriction of the gateway is part of the design, not optional.
  - **Health heartbeat**: interval is `healthCheckIntervalMinutes`, default **5 minutes**, clamped to
    **1-60 minutes** (`ForwardConfig.kt:37`, `ServerHealthMonitor.kt:141-142`). There is no 60-second
    heartbeat.
  - **4G mobile proxy / Tailscale exit node: NOT IMPLEMENTED.** No code or configuration exists in
    either repository. UTCMS egress is the Squid chain (`WORKER_*_PROXY`, `EGRESS_PROXY_MODE` of
    `worker_first` / `clean_pool_only`, `app/automation/worker_proxy.py`), injected into the mobile
    client via `proxy_url` (`app/automation/utcms_mobile_client.py:155-176`). Iranian-egress WAF
    compliance is still satisfied by proxy admission (`egress_verified=true` AND
    `observed_country=IR`), not by any phone.
- `CAPTCHA_PROVIDER=auto` uses CNN → PyTorch Fuel CRNN → Keras → Enhanced OCR →
  Local OCR.
- Keras lazy-loads and runs in-process in each Worker. `KERAS_PYTHON_PATH` is a
  legacy compatibility setting and is not consumed by the current solver.
- Accuracy and latency numbers require a versioned benchmark artifact; do not copy
  unsupported percentages into operational documentation.
- On UTCMS business rejection `4003` (wrong captcha), the mobile client must
  raise so retry loops fire; rejection artifacts (image + model prediction)
  are written under `/tmp/captcha_rejections/` via
  `app/automation/captcha/debug_artifacts.py`. In `_is_transient_login_error`,
  code 4003 is classified as transient retryable (`LOGIN_MAX_ATTEMPTS = 3`,
  refreshing CAPTCHA each time), preventing single-misread login aborts. Session
  Vault (`get_authenticated_client`) caches tokens (4m) and refresh tokens (2h)
  in Redis, minimizing full logins and preventing HTTP 429 rate limit lockouts.

### Automated Shipping Lifecycle & GPS Completion Contract

- **Lifecycle Flow** (state vocabulary `ready → starting → in_transit → finishing → delivered`, plus `unknown` / `needs_review`):
  `waybill issuance (tracking code) → post-issuance RegisterStartOfShipping (origin GPS, UTC timestamp); its UTCMS result decides the state — acknowledged / self-declared 4006 → in_transit (origin witness recorded), explicit reject → unknown, raised/ambiguous → in_transit (still sweepable) → periodic ETA check (every 2 min via shipping.auto_complete_due_trips in Celery Beat) → physical ETA satisfied (now >= estimated_end_at) → RegisterEndOfShipping (2-point GPS trace: origin Type 2 + destination Type 3) → delivered / success`
  - **Durable fences & crash recovery**: `/shipping/start` and the completion POST each write a durable `starting`/`finishing` fence under a dual-key Redis completion claim *before* the mutation. `reclaim_stuck_shipping_fences` (invoked from `get_due_in_transit_jobs`) resets only an *abandoned* fence — older than `COMPLETION_CLAIM_TTL_SECONDS` with no live claim held — back to `in_transit`; it never steals a fence a worker still holds, and fails closed when Redis is unavailable. A missing or future `estimated_end_at` is fail-closed as `waiting_eta` (`shipping_wait_reason`), never treated as "due now" (operator `force=True` is the explicit override on `auto_complete_shipping`).
- **Active Endpoints vs. Deprecated 404s**:
  - Active: `POST /Document/RegisterStartOfShipping` (takes `DocId`, `Speed=0`, `Altitude=1000`, `Longitude`, `Latitude`, `StartDate`, `havePermission=true`) and `POST /Document/RegisterEndOfShipping` (takes `docId`, `gpsList`).
  - Deprecated / 404: `/Document/StartShippingWithGps` and `/Document/FinishShippingWithGps` return 404 on current UTCMS. Client code automatically falls back to the active endpoints.
- **Periodic Beat Task (`shipping.auto_complete_due_trips`)**:
  - Runs in Celery Beat every 2 minutes (`crontab(minute="*/2")` / 120s schedule).
  - Queries active trips in transit (`get_due_in_transit_jobs`), deduplicating across Redis (`utcms:shipping:job:*`) and PostgreSQL (`WaybillJob.status == "in_transit"`).
  - Skips trips whose physical ETA has not arrived (`waiting_eta`) or that are in backoff cooldown (`backoff_until`), preventing premature UTCMS rejection and rate-limiting.
- **Physical ETA & UTC Server Clock Requirements**:
  - UTCMS database server evaluates its own clock `GETDATE()` (UTC) against `estimatedTimeOfEndShipment`.
  - All timestamps (`StartDate`, `Date`, `DateTime`) must strictly be UTC ISO strings (`YYYY-MM-DDTHH:mm:ss.000Z`). Passing local Tehran time shifts `estimatedTimeOfEndShipment` 3.5 hours into the future, triggering error 4013.
  - Short routes (< 20 km): enforce a mandatory minimum 20-minute physical buffer.
  - Long routes: computed based on realistic heavy-vehicle road speed (~65 km/h) proportional to distance (`estimated_end_at`).
- **2-Point GPS Trace Schema (`gpsList`)**:
  - Discovered via reverse engineering of official React Native bundle (`assets/index.android.bundle`):
  - Each point in `gpsList` must include `"Date"` (and `"DateTime"` as alias) in ISO format. Missing `"Date"` causes error 4004 ("موقعیت پایان ارسال نشده است").
  - Point types: only `Type: 2` (intermediate waypoint) and `Type: 3` (destination arrival) are valid. `Type: 1` causes error 4006 ("موقعیتی با نوع نامشخص ارسال شده است"); client maps any initial point to `Type: 2`.
- **Business Rule Handling (4006, 4011, 4012, 4013, 429)**:
  - **Rule 4006 (Self-Declared Start)**: Waybills issued with `selfDeclaredTimeOfStartShipment` are automatically set to `in_transit` (code 1) by UTCMS. Redundant calls to `RegisterStartOfShipping` return business code 4006 ("برای بارنامه نمی توان شروع حمل ثبت کرد"). This is treated as non-fatal, keeping the trip in `in_transit`.
  - **Rule 4011 (Self-Declared End / Early Call)**: Calling `RegisterEndOfShipping` before or upon self-declared termination triggers code 4011 ("پایان حمل بر اساس خوداظهاری تایید شد"). BarPro handles 4011 as successful completion (`mode="self_declared_auto_complete"`), marking `ShippingState` as `delivered` and updating `WaybillJob.status` to `success`.
  - **Rule 4012 (Minimum 2km Travel Requirement)**: UTCMS requires a cumulative travel distance of at least 2.0 km along `gpsList` ("برای ثبت پایان حمل، شما حداقل باید 2 کیلومتر طی کرده باشید. مسیر طی شده فعلی : X کیلومتر"). BarPro's `register_end_of_shipping` automatically checks the cumulative distance and injects an intermediate detour waypoint (Type 2, 35 km/h, midway timestamp) if total distance < 2.05 km, bringing the total to ~2.15 km and satisfying the requirement. If received from UTCMS, a 5-minute circuit-breaker backoff is set.
  - **Rule 4013 (Physical Travel Time)**: If `GETDATE() < estimatedTimeOfEndShipment`, UTCMS returns code 4013 ("زمان مورد نیاز برای پایان حمل نگذشته است."). BarPro sets a 5-minute backoff (`backoff_until = now + 5 min`), avoiding repetitive poll cycles.
  - **Rule 429 (Rate Limiting Circuit-Breaker)**: Repeated rejected calls trigger code 429 ("تعداد فراخوانی بیش از حد مجاز هست، دقایقی دیگر مجدد اقدام نمایید"). BarPro activates exponential backoff (10m, 20m, 30m) on `ShippingState` and excludes the job from scanning during cooldown.

<!-- original-agents:0227-0354:end -->

<!-- original-agents:0001-0012:start -->
# BarPro — Agent Guide

> **📋 See also: [CRITICAL_RULES.md](./CRITICAL_RULES.md)** — خطوط قرمز و الزامات فنی حیاتی پروژه
>
> **UTCMS live contract:** [docs/UTCMS_CONSTRAINTS.md](./docs/UTCMS_CONSTRAINTS.md) — فیلدهای اجباری، WAF/IP، CAPTCHA، زمان‌بندی و معیار اثبات ثبت
>
> **UTCMS bot behavior contract:** [docs/UTCMS_BOT_BEHAVIOR_CONTRACT.md](./docs/UTCMS_BOT_BEHAVIOR_CONTRACT.md) — خطوط قرمز، تفکیک session/transport، ترتیب ناوبری، گیت زنده بودن فرم، read-back فیلدها و پروتکل dry-run
>
> **Canonical tracked knowledge graph:** [docs/BARPRO_KNOWLEDGE_GRAPH.md](./docs/BARPRO_KNOWLEDGE_GRAPH.md) — API, schema, queues, RPA, deployment, evidence labels
>
> **Server Android / FakeTraveler replacement plan:** [docs/ANDROID_CLIENT_IMPLEMENTATION_PLAN.md](./docs/ANDROID_CLIENT_IMPLEMENTATION_PLAN.md) — معماری هدف جایگزین GPS؛ بدون گوشی فیزیکی

<!-- original-agents:0001-0012:end -->

## Scope, freshness and reading map

- This guide and every file under `docs/agent-reference/` apply only inside BarPro.
  General evidence-first and documentation-first policy remains in the agent's
  global configuration. Do not copy BarPro deployment, UTCMS, network or schema
  requirements into global rules or another project's instructions.
- Read `CRITICAL_RULES.md` before making changes. Read the relevant contracts and
  topic references below before touching their subsystem; report a missing or
  unreadable required source rather than silently skipping it.
- The original text is preserved in marked blocks. Historical dates, test counts,
  “current”, “fixed” and deployment claims are snapshots, not fresh evidence.
  Confirm current source and runtime where relevant. Historical commands and
  remediation lists do not authorize live operations.
- Reference links are ordinary Markdown links, intentionally loaded on demand.
  Do not convert them into recursive imports or always-on rules: the expanded
  rule size is limited too. Repository command paths assume the repository root.

| Task | Read before relevant work |
|---|---|
| Architecture, stack, locating files | [Architecture and layout](docs/agent-reference/architecture.md) |
| Deployment, environment, hosting, resource limits | [Deployment and resources](docs/agent-reference/deployment-and-resources.md) |
| API, registration, reconciliation, queues, data model, OTP, shipping | [Runtime contracts](docs/agent-reference/runtime-contracts.md), plus the UTCMS contracts linked above |
| Debugging known pitfalls or CAPTCHA | [Pitfalls and CAPTCHA](docs/agent-reference/pitfalls-and-captcha.md) |
| Investigating a past change | [Historical reference index](docs/agent-reference/README.md); read only the relevant part |

The [reference index](docs/agent-reference/README.md) also records provenance and
the preservation manifest. It is navigation, not an instruction to load every file.

### Known non-features — do not document these as delivered

Verified absent from source on 2026-10-10. Each was previously written up as
working and had to be retracted. Re-check the source before asserting any of them,
and never relabel one as `CODE-VERIFIED` without a file reference that actually
implements it.

- **Cellular 4G / Tailscale exit-node proxy for UTCMS egress — not implemented.**
  No code or configuration exists in `BarPro-main` or `SMS-Forwarder-Pro`
  (`grep -ri tailscale` reaches only documentation and one optional future-Headscale
  note in `docs/adding_new_worker.md`). UTCMS egress is the Squid chain:
  `WORKER_*_PROXY` and `EGRESS_PROXY_MODE` (`worker_first` / `clean_pool_only`),
  `app/automation/worker_proxy.py`, with pool admission fail-closed on
  `egress_verified=true` AND `observed_country=IR`. Proxy injection into the mobile
  client is `proxy_url` in `app/automation/utcms_mobile_client.py`.
- **60-second forwarder heartbeat — does not exist.** The interval is
  `healthCheckIntervalMinutes`: default 5 minutes, clamped to 1–60 **minutes**
  (`ForwardConfig.kt`, `ServerHealthMonitor.kt`).
- **Per-flavor Android UI — does not exist.** `driver` and `hub` build from the one
  `app/src/main` source set. Only `applicationId`, `versionNameSuffix` and three
  `BuildConfig` fields differ. There is no `app/src/driver/` or `app/src/hub/`.
- **A zero-configuration driver app — does not exist.** The `driver` flavor needs the
  webhook token (it signs the envelope), a Hub SIM number, and `driverPhone`; with no
  Hub number `canSendSms` is false and nothing is sent.
- **HTTPS — intentionally not used.** HTTP on port 80 is the chosen transport
  (`infra/nginx/nginx.conf`, `listen 443 ssl` commented out). Do not describe the
  forwarder as delivering "via HTTPS", and do not treat the plaintext transport as a
  defect to fix; the mitigation is network-level restriction of the gateway plus the
  HMAC-authenticated envelope.
- **Sub-second relay latency — unmeasured.** No benchmark or timing artifact exists.
  Treat any "~1 second" figure as an operational assumption, not a measurement.

<!-- original-agents:0013-0055:start -->
## Agent Conduct Rules (Mandatory — apply to every task in this repo)

### 1. No negligence — verify before you act
- Inspect real state first: read the file, run the command, look at the actual output. Never work from memory, assumption, or a stale changelog entry.
- Ambiguous request → clarify before executing. No half-done, rushed, or surface-level work.
- Multi-step tasks → maintain a todo list; close with a verification checklist (artifact actually produced? tests/linters really run? edge cases covered?).
- "Done" is only allowed after real verification — run the checks CI actually runs (`.github/workflows/ci-test.yml`, `ci-cd.yml`) and cite their actual output:
  - backend: `uvx ruff check`, `black --check app/ tests/`, `mypy app/ --ignore-missing-imports`, `pytest` (markers: `-m unit`, `-m integration`, `-m "not slow"`; warnings are errors via `pytest.ini`)
  - frontend (`apps/web`): `npm run lint`, `npm run typecheck` (`tsc --noEmit` + eslint)
  - security: `pip-audit`, `npm audit --audit-level=moderate`

### 2. No unsupported claims — evidence or silence
- Every claim in a report must carry evidence: `file:line`, command output, test log, or tool result.
- Forbidden without execution: "tests pass", "fixed", "deployed", "works", "no issues".
- If something cannot be verified, state "unverified" and why. Never present uncertainty as confidence.
- Never fabricate metrics, quotes, or citations. Report failures completely — hiding or downplaying errors is a violation.
- Repo state ≠ production state: a merged fix proves nothing about the live server. Server claims require a timestamped runtime check (see Historical Remediation Log disclaimer).
- Any claim that a UTCMS document was registered must pass the two-witness proof (`docs/UTCMS_CONSTRAINTS.md`): (1) non-empty tracking code in the RPA response, (2) the same code stored in `waybill_jobs.result_json`. Final confirmation is batched, not per waybill: `orchestrator.reconciliation.audit_tracking_received` sweeps all tracking-received jobs in one run and attaches the UTCMS History record, so per-waybill History/Search checks during the day are not required. UI success, modal close, dry-run, or internal status alone is never proof (`CRITICAL_RULES.md`, §0). `ALLOW_LIVE_SUBMIT` stays `false` unless a pre-validated, operator-monitored job explicitly enables it for one run.

### 3. Mandatory use of matching tools / skills / plugins / MCPs
- Before starting a task, scan the available skills, tools, plugins, and MCP servers, and use the ones that match the job:
  - library/framework docs → Context7 MCP
  - web research, scraping, monitoring → Firecrawl / Tavily / Exa
  - UI or web-app verification → Playwright / Chrome DevTools / Lighthouse MCPs
  - office documents (docx/xlsx/pdf/pptx) → document skills/MCPs
  - this repo's own knowledge → query `docs/BARPRO_KNOWLEDGE_GRAPH.md` first (canonical, dated snapshots + evidence labels), then `docs/INDEX.md`, `CRITICAL_RULES.md`, `docs/UTCMS_CONSTRAINTS.md`, and the 20 domain skills in `.agents/skills/` (barpro-rpa-ops, captcha-retrain, proxy-ops, database-ops, barpro-deploy-ops, tenant-onboard, celery-ops, disaster-recovery, …)
- Building a hand-rolled solution while a matching tool exists is a violation. If nothing fits, proceed and state that in the report.

### 4. Network reality (BarPro-scoped): UTCMS requires an Iranian egress IP
- `barname.utcms.ir` expects Iranian IP access; the WAF answers non-allowed requests with the «درخواست مجاز نمی باشد» page / HTTP 444 (`docs/UTCMS_CONSTRAINTS.md`, §4).
- The operator's machine is often behind a VPN whose exit may be non-Iranian. Before any live UTCMS access from the local machine, verify egress with `curl -s https://ipinfo.io/country` — it must return `IR`; otherwise switch the VPN to an Iranian exit or disable it.
- Point-in-time evidence: 2026-10-05, local egress measured `US` and `barname.utcms.ir` was unreachable (HTTP 000 / DNS resolution timeout) while control sites loaded normally — re-verified twice the same day with identical results.
- The same rule binds workers and proxies: pool admission is fail-closed on `egress_verified=true` AND `observed_country=IR` (`app/automation/clean_ip_pool.py`).

### 5. Documentation drift — keep the repo's knowledge alive
- After any structural or behavioral change, update `docs/CHANGELOG.md` (dated entry under the current version) and `docs/BARPRO_KNOWLEDGE_GRAPH.md` (dated snapshot + evidence labels) within the same task — not "later".
- Snapshot sections in the knowledge graph carry dates by design; never present a dated snapshot as current live state, and never rewrite history to hide a regression.
- Freshness gate: before citing a doc as fact, confirm it is at least as new as the code it describes; a doc older than the change it claims to cover is a lead to verify, not a fact to repeat.

## Project Identity

**BarPro** is a multi-tenant RPA framework for automated waybill (بارنامه) registration and shipping lifecycle automation on Iran's national transportation portal (barname.utcms.ir).

**Core Operational Architecture:**
- **Waybill Issuance Transport:** Direct Mobile API Transport via `UtcmsMobileClient` (derived from reverse-engineered official APK `com.baarnameshahri`). Web browser form filling (Playwright UI) is RETIRED/legacy and is NOT used for live issuance.
- **GPS & Shipping Lifecycle:** Server-side virtual Android (`Redroid` container + `FakeTraveler` location provider + `AndroidShippingController` bridge) running on Linux server without physical phones.
- **Event-Driven OTP Subsystem:** Universal Android SMS Forwarder intake (`SMS-Forwarder-Pro`), secure tokenized endpoints without query leaks, Redis Streams + Lua multi-tenant isolation, and automated `submit_otp` state machine.
- **Model B Topology:** Central Server (32 GB RAM / 8 vCPU) + 2 Remote Worker VPS nodes, Iran-verified egress IP proxy rotation (Squid), and strict two-witness proof for waybill registration.

<!-- original-agents:0013-0055:end -->

<!-- original-agents:0132-0172:start -->
## Code Conventions

### Python
- **Formatter**: Black (line-length 120)
- **Imports**: isort with black profile
- **Linting**: Ruff (select: E, W, F, I, B, C4, UP)
- **Type checking**: mypy (strict mode, partial)
- **Testing**: pytest with async mode auto, coverage (HTML/XML/term)
- **Patterns**: Async/Await throughout, SQLModel for ORM, Pydantic v2 for schemas

### TypeScript / React
- **Framework**: Next.js 15 (App Router, React 19)
- **Forms**: React Hook Form + Zod
- **Data fetching**: React Query + Axios
- **Styling**: Tailwind CSS + Heroicons
- **State**: JWT is transported by httpOnly cookie; localStorage stores only non-sensitive client/session metadata
- **Cookie security**: keep `AUTH_COOKIE_SECURE=false` on current HTTP deployment; set `true` after HTTPS is enabled

## Critical Warnings

1. **NEVER hardcode credentials** — production SSH passwords previously leaked; now placeholderized (`PLACEHOLDER_SSH_PASSWORD`) and must still be rotated on the server
2. **NEVER commit `.env`** — verified not present in current git history (`git log --all -- .env` is empty); use `.env.example` as template
3. **`.env` IS in `.gitignore`** — do NOT commit new secrets
4. **Frontend Docker no longer requires prebuilt `.next/standalone`** — `apps/web/Dockerfile` builds inside Docker
5. **Do not re-add `privileged: true`** — containers use `cap_add` + `no-new-privileges`
6. **No HTTPS** — Nginx listens on port 80 only; all traffic is plaintext
7. **Rate limiter is fail-closed** — preserve HTTP 429 behavior if Redis is unavailable
8. **Proxy URL validation exists** — do not weaken `_is_safe_proxy_url`
9. **Health responses must not expose credentials** — public `/readyz` is sanitized;
   detailed readiness is admin-only at `/api/v1/admin/readyz`
10. **Compose is not firewall evidence** — verify UFW/provider firewall and
    `DOCKER-USER` from a non-worker IP after every deployment
11. **`app/automation/benchmark_payload_adapter.py` is offline operator tooling, not a
    submission path** — it has no production importer and must not acquire one.
    `BenchmarkImportDraft.validation_errors == ()` is **not** submit-readiness:
    `build_benchmark_import_draft` calls `validate_live_waybill_payload` *without*
    `expected_driver_national_code` / `expected_plate` / `expected_driver_mobile`, so it
    is a strictly weaker gate than `app/services/waybill_job_service` applies at job
    creation. A draft must be re-validated against an authorized BarPro driver (and
    enriched for the chosen transport) before any submission.
12. **Web Browser Form Submission is RETIRED** — Never assume or claim that waybills are registered via Playwright browser form-filling. The active production transport is `UtcmsMobileClient` (Mobile API Transport), with server-side Android (`Redroid` + `FakeTraveler`) handling GPS/shipping. Browser code (`EnhancedWaybillManager` / Playwright) is legacy fallback and test fixture only.

<!-- original-agents:0132-0172:end -->

<!-- original-agents:0375-0389:start -->
## Testing

```bash
pytest                    # Run all tests with coverage
pytest -m unit            # Unit tests only
pytest -m integration     # Integration tests only
pytest -m "not slow"      # Skip slow tests
```

- Tests use `asyncio_mode = "auto"` — async test functions are auto-detected
- Database tests require PostgreSQL running (check `compose/infra.yml`)
- Playwright tests require Chromium (install via `playwright install chromium`)
- Test counts are release snapshots, not timeless facts. Run the requested suite
  on the current commit and report its exact result instead of copying an old count.

<!-- original-agents:0375-0389:end -->

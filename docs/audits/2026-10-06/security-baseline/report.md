# Security Review: BarPro-main

## Scope

Security diff e664e544..6c5564e; all10 production inventory rows reviewed.

- Scan mode: branch_diff
- Target kind: git_diff
- Target ID: target_sha256_c6736a28c3b34c5f3fce57a0f19ef17a240825709ce94c7a776811a0d4e003fd
- Revision range: e664e54478da852b1db6674fa515fcd6b1e57f11...6c5564ea7483f127f2e23e785148009114bae49b
- Snapshot digest: codex-security-snapshot/v1:sha256:70fbdc62eb5e54dfdfce8836268e320a08c4d7cc707b869e82acc6076cf6ce9b
- Inventory strategy: diff
- Included paths: .
- Excluded paths: none
- Runtime or test status: No production access

### Scan Summary

| Field | Value |
| --- | --- |
| Scan outcome | completed |
| Reportable findings | 2 |
| Severity mix | medium: 2 |
| Confidence mix | high: 2 |
| Coverage | partial |
| Validation mode | Isolated local ASGI/SQLite/Redis; mocked external mutation |

Canonical artifacts: `scan-manifest.json`, `findings.json`, and `coverage.json`. This report is a deterministic projection of those files.

## Threat Model

Text: # BarPro security threat model — 2026-10-06 ## Overview BarPro exposes FastAPI tenant and OTP endpoints through Nginx, stores waybill/driver ownership in SQLModel/PostgreSQL, uses Redis OTP keys and Streams plus Celery workers, and invokes the authenticated external UTCMS mobile service to issue documents (app/main.py:445-454; infra/nginx/http-server.conf:50-60; app/models_multitenant.py:324-339; app/services/otp_wakeup_consumer.py:312-354; app/services/waybill_job_service.py:738-742). The supplied canonical knowledge graph describes central plus remote Iranian-egress workers; actual production topology is unverified in this offline review. ## Assets, boundaries and assumptions Tenant assets are driver credentials, phone OTPs, pending document/session pointers, job state and registration integrity. The API authenticates clients by JWT plus active tenant record; manual OTP ingress verifies job.client_id before storing the job key (app/auth_multitenant.py:421-464; app/api/routes/otp_forwarder.py:486-518). Background completion reconstructs master_admin authority from an event rather than preserving caller identity (app/services/otp_wakeup_consumer.py:279-289), so every passed job/phone association must be trusted and bound. Redis keys are global by normalized phone, not tenant prefix (app/automation/otp_keys.py:52-61); cleanup can delete both OTP and pending pointers (app/automation/otp_keys.py:135-151). Forwarder ingress has a deployment-wide OTP_WEBHOOK_SECRET credential, accepted from headers/Bearer/query; gateway also checks a signed envelope and origin match (app/api/routes/otp_forwarder.py:47-78,172-198). Durable OTP intake validates recipient/time and uses Lua for ordering/dedup/write (app/services/otp_delivery.py:77-118). Nginx separately logs the full request line to access.log (infra/nginx/nginx.conf:44-47); Python sanitization does not apply to that edge sink. The Compose edge mounts those exact Nginx files (compose/web.yml:69-71). The committed edge config serves HTTP:80 and has disabled TLS example (infra/nginx/nginx.conf:69-95); runtime TLS and whether a forwarder actually uses query authentication remain unverified. Realistic attackers include authenticated tenant clients controlling manual-OTP JSON and knowing another driver's phone, untrusted network clients without secrets, and actors who can read operational edge logs but cannot read server .env. Ordinary operators already holding the global ingress secret have ingress-wide authority; do not invent an extra driver-scoped boundary for that credential. The new driver fallback lookup includes tenant filters when client_id is set (app/services/waybill_job_service.py:703-715), and job.client_id is required (app/models_multitenant.py:328). ## Hypotheses and controls Investigate caller-provided phone passing through an owned-job authorization into privileged cleanup; investigate newly accepted query credentials reaching Nginx full request logs. Hypotheses require separate validation. The route alias retains the same auth dependency; health/ping expose no credential values; React renders changed fields as text rather than raw HTML. Replay time normalization, Stream recovery and lease semantics can affect integrity/availability, but attacker capability gain must be distinguished from ordinary correctness failures and existing baselines. Security objectives: no cross-tenant mutation/read/delete; secrets never enter logs; OTP freshness and consume semantics survive retries; mutations require authorized job/driver/session; ALLOW_LIVE_SUBMIT remains false in this audit. No production calls, SSH, deployment or persistent security configuration changes are authorized here. Source and isolated local HTTP/SQLite/Redis experiments provide code evidence only, not live server evidence. ## Calibration and coverage High severity requires meaningful cross-tenant compromise or credential disclosure with broad usable authority. Medium covers authenticated cross-tenant disruption and conditional exposure of a shared ingress secret to a distinct log-reader audience. Self-only malformed input or privileged actors performing already-authorized operations are not vulnerabilities without further evidence. The range is e664e54478da852b1db6674fa515fcd6b1e57f11..6c5564ea7483f127f2e23e785148009114bae49b. Ten changed production source files are in the authoritative inventory; tests/docs are supporting context. Architecture pass was sequential because all four agent slots were occupied; not an independent architecture review.

## Findings

| Finding | Severity | Confidence | Detailed write-up |
| --- | --- | --- | --- |
| [Forwarder query authentication exposes shared secret to access logs](#finding-1) | medium | high | inline below |
| [An owned job allows deletion of another tenant's pending OTP state](#finding-2) | medium | high | inline below |

### Confidence Scale

| Label | Meaning |
| --- | --- |
| high | Direct evidence supports the finding with no material unresolved blocker. |
| medium | Evidence supports a plausible issue, but material runtime or reachability proof remains. |
| low | Evidence is incomplete and the item is retained only for explicit follow-up. |

<a id="finding-1"></a>

### [1] Forwarder query authentication exposes shared secret to access logs

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | Baseline source traced and validated in isolated ASGI/SQLite/private Redis reproduction. |
| Category | Credential exposure |
| CWE | CWE-532, CWE-598 |
| Affected lines | app/api/routes/otp_forwarder.py:68-70, infra/nginx/nginx.conf:44-47 |

#### Summary

At baseline6c5564e valid query token authenticates HEALTH_CHECK withHTTP200; Nginx logs the entire $request including query. Log readers can obtain the shared ingress credential when an operator uses this supported transport.

#### Validation

Validation outcomes are recorded below.

Validation method: Local ASGI with real SQLite/Redis and mocked external issuer

- **Status:** confirmed

Evidence:
- artifacts/02_discovery/validation_artifacts/candidate-011dcef62fee3a7a/security-reproductions.log

Limitations:
- No production access; SQLite substitutes PostgreSQL.

#### Dataflow

query token -\> webhook authentication; Nginx $request -\> access.log -\> log reader

#### Reachability

Reachability was not recorded beyond the canonical finding summary and affected locations.

Preconditions:
- Operator sends secret in supported query parameter
- Attacker reads edge logs without environment-secret access

Limitations:
- Runtime deployment/access unverified; no registration compromise claimed.

#### Severity

**Medium** — Conditional disclosure to distinct log-reader audience; actual query usage and log access unverified.

Additional runtime or deployment evidence could raise or lower this severity.

**Impact assessment:** Conditional disclosure to distinct log-reader audience; actual query usage and log access unverified.

#### Remediation

Remove query authentication; use headers/Bearer. Update configuration guidance and rotate if historical query usage is confirmed.

Tests:
- Assert malicious input rejected before dispatch or cleanup
- Retain intended authenticated workflow

Preventive controls:
- Bind credentials and resource authorization at ingress

<a id="finding-2"></a>

### [2] An owned job allows deletion of another tenant's pending OTP state

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | Baseline source traced and validated in isolated ASGI/SQLite/private Redis reproduction. |
| Category | Tenant authorization |
| CWE | CWE-639, CWE-862 |
| Affected lines | app/api/routes/otp_forwarder.py:522, app/services/otp_wakeup_consumer.py:254-274, app/automation/otp_keys.py:135-151 |

#### Summary

At baseline6c5564e caller phone bypasses job ownership boundary into privileged cleanup. Tenant1's owned successful job and tenant2's phone returnedHTTP200 and deleted victim Redis keys2-\>0. External issuer was not called.

#### Validation

Validation outcomes are recorded below.

Validation method: Local ASGI with real SQLite/Redis and mocked external issuer

- **Status:** confirmed

Evidence:
- artifacts/02_discovery/validation_artifacts/candidate-df3a748befb13b29/security-reproductions.log

Limitations:
- No production access; SQLite substitutes PostgreSQL.

#### Dataflow

manual JSON.phone + owned job -\> privileged wake-up -\> consume_scoped_otp -\> victim keys deleted

#### Reachability

Reachability was not recorded beyond the canonical finding summary and affected locations.

Preconditions:
- Authenticated tenant owns successful job
- Known victim phone has pending OTP keys

Limitations:
- Runtime deployment/access unverified; no registration compromise claimed.

#### Severity

**Medium** — Authenticated cross-tenant OTP availability/integrity disruption; no OTP disclosure or unauthorized issuance proven.

Additional runtime or deployment evidence could raise or lower this severity.

**Impact assessment:** Authenticated cross-tenant OTP availability/integrity disruption; no OTP disclosure or unauthorized issuance proven.

#### Remediation

Derive phone from authorized durable job/driver; validate state/challenge before dispatch and bind cleanup to that association.

Tests:
- Assert malicious input rejected before dispatch or cleanup
- Retain intended authenticated workflow

Preventive controls:
- Bind credentials and resource authorization at ingress

## Reviewed Surfaces

| Surface | Risk Area | Outcome | Notes |
| --- | --- | --- | --- |
| All10 changed production files in authoritative diff inventory | not recorded | Reported | Two validated security findings; broader reliability findings reported separately. Evidence: artifacts/02_discovery/in_scope_files.txt, artifacts/02_discovery/candidate_ledger.jsonl |

## Open Questions And Follow Up

- Production query usage, log permissions, and runtime topology remain unverified.
- Validate owned-job arbitrary-phone cleanup candidate with real local HTTP/SQLite/Redis; validate query credential ingress and Nginx sink.
  - Follow-up prompt: Review deferred unit deferred-89e767ad73fc37ff and close its stated proof gap.

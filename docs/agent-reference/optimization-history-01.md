# Optimization History — part 1

> Scope: BarPro only. Read this file when relevant to the task; do not auto-import
> the whole reference directory into global rules or the always-loaded core.
> **HISTORICAL / UNVERIFIED NOW.** Preserved records, including old commands and
> pending actions, are historical data rather than new instructions or authority
> to execute them. Re-check current code, contracts and authorization first.

Read when: Historical investigation only; not a current action list.

[Core guide](../../AGENTS.md) · [Reference index](README.md) · [Critical rules](../../CRITICAL_RULES.md)

Paths inside preserved text and command examples are relative to the repository
root, not this directory. Commands are examples, not automatic execution steps.

<!-- original-agents:0495-0555:start -->
## Optimization Applied (2026-06-30 → 2026-09-06)

### 2026-09-14 — GPS Shipping Session Vault & WAF Evasion Hardening (v2.9.12)
| Change | Impact |
|---|---|
| Replaced raw mobile login & CAPTCHA in `/shipping/start` and `/shipping/finish` with `get_or_login_client()` | Driver JWT cached in Redis Session Vault for ~115 min; eliminates redundant CAPTCHA solving and eradicates HTTP 429 login spam |
| Enforced fail-closed proxy guard with dedicated HTTP 503 response | Prevents silent fail-open direct server egress when proxy is unavailable; returns clear 503 ("پراکسی UTCMS در دسترس نیست") instead of generic 502 |
| Injected Android-realistic baseline headers (`_mobile_base_headers`) & suppressed desktop Client Hints | `curl_cffi` AsyncSession uses `default_headers=False` (eradicating desktop `sec-ch-ua` headers); baseline headers send Chrome/120 Android UA, `Accept: application/json, text/plain, */*`, `Accept-Language: fa-IR`, `Accept-Encoding: gzip, deflate, br`; removed fake `X-Requested-With`; fixed `_post` kwargs to `data=`; updated base URL to `cptch.utcms.ir` matching genuine APK |
| Formalized start vs finish dual-endpoint shipping contract | Proved that `/start` using `StartShippingWithGps` alone and `/finish` using `FinishShippingWithGps` + `RegisterEndOfShipping` is correct business architecture, not a state defect |

### 2026-09-13 — Deep WAF Evasion & Mobile TLS Hardening (v2.9.11)
| Change | Impact |
|---|---|
| Migrated `UtcmsMobileClient` from `httpx` to `curl_cffi` (`impersonate="chrome120"`) | Eradicates Python JA3/TLS fingerprints, bypassing the strict WAF HTTP 444 blocks completely |
| Auto-normalization of Android/Chrome security headers | Prevents `python-httpx` User-Agent leaks and missing `Accept-Encoding: br` anomalies |
| Enforced Elite Anonymity on all `infra/squid/*.conf` proxies | `forwarded_for delete`, `via off`, and `X-Forwarded-For deny all` prevents proxy footprinting |
| Realigned contract tests & live execution verification | Proved protected Mobile API (Fleet list) is fully accessible without WAF detection |

### 2026-09-06 — UTCMS End-to-End Submission & OTP Lifecycle Hardening (v2.9.10)
| Change | Impact |
|---|---|
| Auto-populate `citySourceMap`, `CityDestMap` & default coordinates (`sourceLatM`/`destLatM`) | Resolves unhandled HTTP 500 on `UpdateRegisterNewOld` caused by ASP.NET Core parsing empty decimal strings |
| Enforce fare/rent (`#txtkeraye` / `rent` / `postRent` = 5,000,000 Rials default) | Resolves UTCMS rejection 400 (Error 4025: "مقدار کرایه را باید وارد کنید") |
| Neuter `window.validateTime` & transport-level auto-heal of `SelfDeclaredTimeOfStartShipment` | Resolves UTCMS rejection 200 ("تبدیل تاریخ بدرستی انجام نگرفت") caused by client-side clearing of `#loadingTime` |
| Live Document Creation & Evening OTP Lifecycle Integration | Successful live submission of Job 56 resulting in UTCMS Document ID `214489653` and handled two-step OTP workflow |

### 2026-08-27 — Session-Aware 408 and Shared Clean Pool Hardening (v2.9.8)
| Change | Impact |
|---|---|
| Anonymous Clean IP probe moved from `HagigiHogugi` to stable login surface | Cold deep-link 408 no longer rejects every healthy candidate |
| Operational pool requires measured Iranian egress and fresh shared Redis state | Remote Workers consume the same verified pool; stale URL-only fallbacks are rejected |
| Generic 408 removed from Worker-IP breaker evidence | UTCMS target outage/session behavior cannot drain the entire fleet |
| Exact-selector location read-back | Origin/destination value, label and address evidence matches the actual DOM element used |

> Local release verification: **1061 passed / 3 skipped**, plus successful codebase, RPA network,
> proxy, memory, topology, schema, auth and WebSocket audits.

### 2026-08-26 — Clean IP Pool Pipeline Overhaul (v2.9.7)
> Live-verified root causes on Central; all fixes regression-tested. Full suite at commit time: 1035 passed / 3 skipped / 2 pre-existing doc-file failures (`test_queue_routing_contract` → missing `docs/runbook_worker_registration.md`, unrelated).

| Change | File | Impact |
|--------|------|--------|
| Round-robin selection over the ENTIRE verified pool (async + sync) instead of always returning the single lowest-latency record | `app/automation/clean_ip_pool.py` | Stops funneling every worker's UTCMS traffic through one address — the per-IP concentration pattern WAFs punish regardless of pool "cleanliness" |
| Probe rewritten to curl_cffi `impersonate="chrome120"` with login-path header set (urllib fallback only for http/https when curl_cffi missing) | `app/automation/clean_ip_pool.py` | Screening fingerprint now matches production login/health-check traffic; SOCKS4/5 candidates verifiable natively |
| 4-way probe verdict: `healthy / waf_challenge / target_rejected(403,429) / unacceptable` with differentiated score penalties (-25 dead, -50 rejected/challenge) and `utcms_rejected`/`waf_challenge` tags | `app/automation/clean_ip_pool.py` (`classify_probe_response`) | A target-rejected IP can no longer be stored as "working"; a 200 WAF-challenge page is no longer "healthy" |
| Measured egress truth: `_verify_egress_country()` (GeoIP through the tunnel) on the shortlist; non-Iranian measured egress demoted (`non_iranian_egress` tag); `observed_country`/`egress_verified` persisted on records | `app/automation/clean_ip_pool.py` | Source-declared country is no longer trusted — global-mirror entries default to UNKNOWN, never to IR |
| Dedup identity `protocol://ip:port` via pure `_dedupe_candidates`; harvesters run in parallel then dedupe | `app/automation/clean_ip_pool.py` | Same ip:port offering HTTP and SOCKS5 stays two candidates; first-responder protocol hijack removed |
| Sync path staleness guard: `_pool_is_stale()` vs `CLEAN_IP_POOL_MAX_AGE_SECONDS` (default 1800) kicks a daemon background `refresh_pool()` from sync callers | `app/automation/clean_ip_pool.py`, `app/core/config.py` | Worker hot loop can no longer serve the same dead `best_iran_proxy.txt` forever between successful Beat cycles (live logs showed alternating "verified 0" cycles) |
| `mark_blocked()` now calls `invalidate_worker_proxy_cache()` immediately | `app/automation/clean_ip_pool.py`, `app/automation/worker_proxy.py` | Just-blocked clean proxies can't ride out the 60s worker success-cache TTL |
| Circuit breaker: clean-pool failure WITHOUT proxy identity logs and returns — never blocks the healthy worker's own IP index | `app/core/circuit_breaker.py` | Prevents 30-minute worker drain from third-party-proxy problems |
| `CleanIPRecord.from_dict` validates url/protocol/ip/port before accepting Redis/file state | `app/automation/clean_ip_pool.py` | Malformed/stale state can't re-enter the runtime pool |
| Rotator clean-pool fallback uses full record metadata (`get_clean_record_sync`) instead of hardcoding `country="IR"` | `app/automation/proxy_rotator.py` | Geo decisions downstream use measured data |
| Regression suite: rotation, verdict matrix, 403≠dead, WAF-challenge page, SOCKS skip, egress demotion, stale kick, cache invalidation, unidentified-failure isolation, from_dict validation (39 tests in file) | `tests/test_clean_ip_pool.py`, `tests/test_worker_proxy_and_rotator.py` | Locks the exact defect classes found live |

> **Historical deploy note, superseded:** the 07:10 deployment at `644ae79` was healthy, but its conclusion that anonymous `ISSUANCE_PROBE_URL` 408 proved an IP soft-block was incorrect. Later same-session testing showed the form opens through Login → Notification → menu. v2.9.8 replaces that probe contract; current live status must be re-verified after deployment.

### 2026-08-24 — Dependabot Version Updates Disabled
| Change | File | Impact |
|--------|------|--------|
| Dependabot version updates off | `.github/dependabot.yml` (deleted) | Weekly PRs from pip/npm/github-actions ecosystems had accumulated ~24 stale branches/PRs (all deleted in the v2.9.6 cleanup). Re-enable only deliberately: restore the file per github.com/docs/code-security/dependabot/working-with-dependabot. **Keep ON in repo Settings → Code security:** `Dependabot alerts` and `Dependabot security updates` are UI-level toggles unaffected by this deletion — CVE-driven PRs still work. Manual hygiene cadence: `pip-audit` + `npm audit --omit=dev` quarterly |

<!-- original-agents:0495-0555:end -->

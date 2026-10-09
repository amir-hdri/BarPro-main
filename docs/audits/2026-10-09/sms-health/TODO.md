# SMS health correction & Security Remediation — 2026-10-09

- [x] Re-read current changes in BarPro and SMS-Forwarder-Pro; preserve pre-existing work.
- [x] Reproduce each prior finding against current source and correct any unsupported prior claim.
- [x] Preserve health observations atomically; reject stale/replayed probes; fail closed on probe storage errors.
- [x] Separate provisioning from current health in API and web UI; show observation times and unknown states.
- [x] Make Android SMS test results truthful and correlate a probe with server receipt; refresh permission observations.
- [x] Validate Room 8→9 migration and Android transport/health behavior with regression tests.
- [x] Run backend/frontend/Android checks and dependency audits required for changed subsystems.
- [x] Reconcile documentation, graph artifacts and Codex concurrency claim with fresh evidence.
- [x] Independently review final diffs and publish exact validation results and remaining runtime limitations.
- [x] Rotated leaked secrets in .env (JWT, Postgres, Redis, API_KEY); enforced loopback bindings (127.0.0.1).
- [x] Configured OTP_WEBHOOK_SECRET and ALERT_WEBHOOK_SECRET; wired fail-closed validate_environment() in app/main.py:lifespan.
- [x] Formatted all Python files with black; resolved all Mypy type-narrowing and Ruff issues; verified 2,342 passing backend tests and 55 frontend tests.

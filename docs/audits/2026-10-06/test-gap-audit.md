# Test isolation and integration coverage audit — 2026-10-06

Scope: static review at `6c5564e`, prompted by the long-running broad pytest run. No additional browser test or live request was executed by this reviewer. The parent run later progressed past the E2E test before interruption, so this report does **not** claim a permanent hang.

## P2 — the supposed local E2E test can access live UTCMS

`tests/test_e2e_bot.py:3–4` describes an in-memory HTML test, and `132–136` supplies a `data:` login URL. Its mocks at `128–130` only replace the result/post-login checks, not login itself or network access.

Two unmocked paths defeat this isolation:

1. `UTCMSAuthenticator.login` invokes `_try_http_login_first` **before** handling the supplied URL (`app/automation/auth.py:908–917`). `_try_http_login_first` creates `UtcmsHttpLogin()` without passing the data URL (`829–830`). The constructor chooses configured `LOGIN_URL` (`app/automation/utcms_http_login.py:175`); the feature flag defaults true (`app/core/config.py:162`). Its actual root and login GETs have 10s and 30s timeouts (`utcms_http_login.py:611–622`), with three transport retries and exponential backoff (`233–235`, `378–403`). If login-page processing succeeds, this is the full authentication flow, not a read-only mock.
2. If Playwright fallback is needed, `AuthNavigator.candidate_login_urls` appends the live `https://barname.utcms.ir/Account/Login` for a data URL (`app/automation/auth_navigator.py:158–165`). A local fixture failure can therefore navigate the browser to UTCMS too.

The shared `tests/conftest.py:44–58` mocks database startup, selected infrastructure tasks, and proxy-health checking, but neither HTTP-first authentication nor candidate URL construction. Mocking `check_proxy_health` also does not mock `get_worker_proxy_url` or its selection/probe behavior.

The slow path also has a deterministic local component: `AuthNavigator.find_selector` loops over each selector and gives each a full 8s budget (`auth_navigator.py:130–149`, `auth.py:972–975`). In the test HTML, username is the sixth candidate, password the fourth, and submit the seventh (`tests/test_e2e_bot.py:61–65`; `selectors.py:196–215`, `258–265`). Missing selectors therefore consume approximately `5×8 + 3×8 + 6×8 = 112 seconds` before these three fields are found, even if all network paths are disabled. Captcha lookup and other waits add more. This is a code-derived timeout budget, not a measured wall-clock attribution for the parent's run.

No enclosing test timeout or `slow` marker is present (`tests/test_e2e_bot.py:26–27`, `84–178`); `-m "not slow"` does not exclude it. HTTP retries plus sequential selector budgets are a credible explanation for several minutes, but the precise location of every second in the parent run was not instrumented.

Recommended repair: explicitly disable/mock HTTP-first login, force candidate URLs to the data page only, reject all external browser/network requests, reduce per-selector test budgets or test fallback through a single shared budget, and put a bounded timeout around this scenario. Fix the duplicate nested `<form>` fixture (`59–60`) as well. Do not rerun the unmodified test as proof of a hermetic suite.

## P2 — CI's integration job does not test its provisioned PostgreSQL or Redis

The integration job provisions Redis 7 and PostgreSQL 16 (`.github/workflows/ci-test.yml:174–186`) and executes exactly `tests/test_integration/` and `tests/integration/` (`208`). Those directories currently contain:

- `tests/test_integration/test_placeholder.py:1–3`: only `assert True`.
- `tests/integration/test_worker_lifecycle.py:15–25`: a real but narrow lifecycle test using in-memory SQLite `StaticPool`, patching `_WorkerSession` and the heartbeat thread (`35–40`). It does not use the CI PostgreSQL/Redis services.

Neither file has an integration marker; repository search found no `pytest.mark.integration`/integration `pytestmark`. The parent audit independently executed marker selection and observed no selected integration tests. The directory-based CI command still selects the two tests, so do not conflate "zero marked tests" with "CI runs zero tests".

The practical coverage gap is the absence of service-backed verification of Redis Lua/Streams/lease semantics and PostgreSQL transactions in that job. This matters directly for the OTP defects: the current OTP MemoryRedis replaces Redis consumer-group and TTL semantics with list operations (`tests/test_otp_wakeup_and_lifecycle.py:48–52`, `123–137`), while the separate audit's private real Redis reproduced stream-loss and lease failures.

Recommended repair: replace the placeholder with meaningful PostgreSQL/Redis integration cases, consistently mark those cases, and keep the current SQLite lifecycle test as a useful unit/component test. Passing this CI integration job alone is not evidence that delivery recovery, locking, and database side effects work together.

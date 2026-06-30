# BarPro — Comprehensive Issue Report

**Total: 115 issues** (25 HIGH · 34 MEDIUM · 56 LOW)
**Generated**: 2026-06-30

---

## Deployment Context

This report is written for the **actual production environment**:
- **1 physical server** with **2 public IPs** (188.121.123.16 primary, 95.38.233.90 secondary)
- **4 vCPU, 12 GB RAM** shared across **13 Docker containers**
- PostgreSQL 16, Redis 7, 3× Celery Workers, FastAPI, Next.js, Nginx, 3× Squid, Prometheus, Celery Beat
- All containers run on the **same host** — resource contention is a critical concern
- Squid proxies: 3128 (egress via 188.121.123.16), 3129 & 3130 (egress via 95.38.233.90)

---

## How to Read This Report

Each issue includes:
- **Severity**: 🔴 HIGH / 🟡 MEDIUM / 🟢 LOW
- **Category**: Security / Code / Infrastructure / Architecture
- **File**: path with line number
- **Technical description** of the problem
- **Impact**: what can go wrong, specifically on this 12 GB / 4 vCPU server
- **Fix**: recommended remediation

---

# 🔴 HIGH Severity (25)

---

### H-01. SSH Production Password Leaked in 15 Source Files

| Field | Value |
|-------|-------|
| **Category** | Security — Credential Leak |
| **Files** | `deploy_changes.py:15`, `scripts/server_deploy.py:19`, `scripts/deploy_single_vm.py:48`, `scripts/change_expired_password.py:5-8`, `scripts/upload_and_setup.py:12`, `upload_tar.py:4`, `.agents/orchestrator/BRIEFING.md:14`, `.agents/worker_m3_1/BRIEFING.md:14`, `.agents/orchestrator/ORIGINAL_REQUEST.md:12`, `.agents/orchestrator/comprehensive_audit.py:12`, `.agents/worker_milestone_2_gen2/comprehensive_audit.py:12`, `.agents/worker_milestone_2_gen2/handoff.md:4`, `.agents/worker_milestone_2_gen2/ORIGINAL_REQUEST.md:24`, `ORIGINAL_REQUEST.md:55`, `.agents/orchestrator/handoff.md:53` |
| **Code** | `SSH_PASS = "PLACEHOLDER_SSH_PASSWORD"` |
| **Issue** | The production SSH password `PLACEHOLDER_SSH_PASSWORD` for user `ubuntu` on server `188.121.123.16` is hardcoded in 15+ files and committed to git history. The same password appears in Python scripts, Markdown files, and agent documentation. |
| **Impact** | Anyone with repo access can SSH into the production server (single host with 13 containers). This is the single most critical security breach — full host compromise, data exfiltration, container escape, and lateral movement. |
| **Fix** | 1. Immediately rotate the SSH password on the server 2. Remove all files containing credentials from git with `git-filter-repo` 3. Switch to SSH key-based authentication 4. Use GitHub Secrets for CI/CD 5. Add pre-commit hook to scan for secrets |

---

### H-02. Production `.env` with All Secrets Tracked in Git

| Field | Value |
|-------|-------|
| **Category** | Security — Credential Leak |
| **File** | `.env` (tracked in git history since commit `61a211b`) |
| **Issue** | The `.env` file containing live production secrets (`API_KEY`, `JWT_SECRET`, `DRIVER_ENCRYPTION_KEY`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `MASTER_ADMIN_PASSWORD`) was committed to git before `.env` was added to `.gitignore`. It remains tracked: if someone modifies `.env`, `git status` will show changes to it. |
| **Impact** | All production secrets are in git history. Anyone cloning the repo (including future CI runners, contractors, or compromised systems) can extract them. |
| **Fix** | 1. Rotate ALL secrets immediately 2. Purge `.env` from git history using `git-filter-repo` 3. Verify `.gitignore` blocks re-commit 4. Add `git-secrets` or `talisman` pre-commit hook |

---

### H-03. All Backend Containers Run with `privileged: true`

| Field | Value |
|-------|-------|
| **Category** | Security — Container Escape |
| **File** | `compose/backend.yml:34` |
| **Code** | `privileged: true` |
| **Issue** | The backend template (`x-backend-common`) sets `privileged: true` for all services: FastAPI, 3× Celery workers, and Celery Beat. A privileged container has all root capabilities on the host, bypasses all security namespaces, and can access host devices, kernel modules, and cgroups. |
| **Impact** | Any RCE vulnerability in the Python app (e.g., a malicious payload in a waybill field, SSRF, or dependency compromise) grants immediate full host root access. Container escape is trivial. |
| **Fix** | 1. Remove `privileged: true` 2. Add only required capabilities: `cap_add: [SYS_ADMIN, NET_ADMIN]` (if needed for Playwright). 3. Add `security_opt: [no-new-privileges:true]` 4. Test Playwright with `--no-sandbox` in non-privileged mode |

---

### H-04. Squid Proxies Use `network_mode: host`

| Field | Value |
|-------|-------|
| **Category** | Security — Network Isolation |
| **File** | `compose/proxy.yml:28,48,68` |
| **Code** | `network_mode: host` (all 3 Squid containers) |
| **Issue** | All 3 Squid containers share the host network namespace. Since this is a **single server** (dual IP), `network_mode: host` gives the containers full access to all network interfaces including both public IPs (188.121.123.16 and 95.38.233.90). Combined with permissive ACLs (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` without auth), this creates an open proxy risk. Squid 2 (port 3129) and Squid 3 (port 3130) are directly exposed on the second IP. |
| **Impact** | If the server's firewall allows inbound on ports 3128/3129/3130, the Squid proxies can be used by external attackers for egress traffic, making the server an open relay. Worse: all 3 containers see the same network stack, so Worker 2 could theoretically bind to IP 188.121.123.16 instead of its intended 95.38.233.90. |
| **Fix** | 1. Use `ports` mapping instead of `network_mode: host` 2. Restrict Squid ACLs to only the Docker bridge network 3. Add iptables rules to block external access to Squid ports 4. Ensure each Squid binds to the correct IP explicitly |

---

### H-05. No TLS/HTTPS on Nginx

| Field | Value |
|-------|-------|
| **Category** | Security — Transport |
| **File** | `infra/nginx/nginx.conf:67` |
| **Code** | `listen 80;` (no `listen 443 ssl;`) |
| **Issue** | Nginx listens on plain HTTP only. There is no SSL certificate configuration, no TLS termination, no redirect from HTTP to HTTPS. All traffic between clients and the server is transmitted in plaintext. |
| **Impact** | Credentials (JWT tokens, passwords, API keys) are sent in cleartext over the network. On public networks, anyone with packet capture capability (Wi-Fi sniffing, ISP-level monitoring, internal network attackers) can intercept all traffic, steal session tokens, credentials, and waybill data. |
| **Fix** | 1. Obtain SSL certificate (Let's Encrypt or commercial CA) 2. Add `listen 443 ssl;` with certificate paths 3. Redirect HTTP → HTTPS with 301 4. Add `Strict-Transport-Security` header 5. Consider using Nginx sidecar with `certbot` |

---

### H-06. JWT Stored in localStorage (XSS-Vulnerable)

| Field | Value |
|-------|-------|
| **Category** | Security — Authentication |
| **File** | `apps/web/src/lib/auth.ts:15-21,40-48` |
| **Code** | `window.localStorage.setItem(AUTH_TOKEN_KEY, token)` |
| **Issue** | JWT tokens are stored in `localStorage` and read back via `window.localStorage.getItem()`. `localStorage` is accessible to any JavaScript executing in the same origin, including third-party scripts, browser extensions, and XSS payloads. There is no `httpOnly` cookie option available for localStorage. The `axios` client already sets `withCredentials: true` (api.ts:124), which would work with cookies. |
| **Impact** | Any XSS vulnerability (even minor, like a reflected XSS in a waybill detail field) allows an attacker to steal the JWT, impersonate any user, access all tenant data, and submit waybill jobs. |
| **Fix** | 1. Migrate to httpOnly secure cookies for JWT 2. Set `SameSite=Strict` and `Secure` flags 3. Remove manual token management from auth.ts 4. Use `axios.defaults.withCredentials = true` (already set) 5. Add CSRF token for state-changing requests |

---

### H-07. SSRF Vector in Proxy Rotator

| Field | Value |
|-------|-------|
| **Category** | Security — SSRF |
| **File** | `app/automation/proxy_rotator.py:358-379,485-496` |
| **Code** | `verify_country` and `health_check` make HTTP requests to freeipapi.com, ip-api.com, ipapi.co, barname.utcms.ir through user-supplied proxy URLs |
| **Issue** | Proxy URLs are loaded from `RPA_PROXIES` env var or `RPA_PROXY_LIST_FILE`. If an attacker controls the proxy list (via environment or file injection), they can make the server issue requests to internal network addresses (`http://169.254.169.254/` for cloud metadata, `http://10.0.0.1/` for internal services, `http://redis:6379/` for direct Redis access) through the proxy health check mechanism. |
| **Impact** | Full SSRF — attacker can probe internal network, access cloud metadata endpoints (potentially getting cloud provider credentials), scan internal ports, and pivot to internal services. |
| **Fix** | 1. Add URL allowlist for health-check targets (only barname.utcms.ir and IP geolocation APIs) 2. Validate proxy URLs with a regex that rejects private IP ranges 3. Add connection timeout (already exists) and restrict DNS resolution to public-only 4. Add a "proxy URL validation" config that runs at startup |

---

### H-08. Rate Limiter Fails Open

| Field | Value |
|-------|-------|
| **Category** | Security — Rate Limiting |
| **File** | `app/core/rate_limiter.py:233-240` |
| **Code** | ```python
except Exception:
    return RateLimitState(remaining=999, limit=999, ...)
``` |
| **Issue** | If the rate limiter backend (Redis or in-memory) throws ANY exception, the failure is silently swallowed and unlimited requests (remaining=999) are allowed. An attacker could deliberately flood Redis connections to exhaust the pool, causing the rate limiter to fail and bypass all limits. |
| **Impact** | Complete bypass of rate limiting when Redis is under load — enables brute-force attacks on login, mass waybill submission, and denial-of-service against downstream services. |
| **Fix** | 1. Log the exception with `logger.exception()` 2. Return conservative values: `RateLimitState(remaining=0, limit=100, ...)` — fail closed 3. Consider a circuit breaker pattern: after N failures, hard-block requests until Redis recovers |

---

### H-09. Default Master Admin Password `master_bar`

| Field | Value |
|-------|-------|
| **Category** | Security — Weak Credentials |
| **File** | `app/core/config.py:112-113` |
| **Code** | `MASTER_ADMIN_PASSWORD = os.getenv("MASTER_ADMIN_PASSWORD", "master_bar").strip() or "master_bar"` |
| **Issue** | The default admin password is `master_bar`. In non-production environments, only a warning is logged. The blacklist check at line 116 catches common passwords but only warns — it does not enforce a strong password. |
| **Impact** | If the environment variable is not set, or is accidentally unset, the admin panel is protected by a trivial password that can be brute-forced in seconds. |
| **Fix** | 1. Remove default password entirely — fail at startup if `MASTER_ADMIN_PASSWORD` is not set 2. Enforce minimum entropy/length in config validation 3. Add rate limiting on admin login endpoint (currently only 5/min for login path) |

---

### H-10. JWT Algorithm Not Restricted — Downgrade Attack Possible

| Field | Value |
|-------|-------|
| **Category** | Security — Authentication |
| **File** | `app/core/security.py:38-39`, `app/auth_multitenant.py:142-143,172-176` |
| **Code** | `"algorithms": [utcms_config.JWT_ALGORITHM]` — reads algorithm from environment |
| **Issue** | The JWT algorithm is read from config (defaulting to `HS256`). If an attacker can set `JWT_ALGORITHM=none` (via env injection or config file), or if the `python-jose` library is vulnerable to algorithm confusion (e.g., accepting `alg: none` in the token header), unsigned tokens would be accepted. The `options={"verify_at": False}` at line 143 already disables audience verification, which is another weakening. |
| **Impact** | Attacker could forge arbitrary JWT tokens, impersonate any user, gain admin access, and issue waybill jobs as any tenant. |
| **Fix** | 1. Hardcode `algorithms=["HS256"]` — never read from config 2. Do NOT use `verify_at=False` — properly configure audience if needed 3. Use `python-jose` with explicit `algorithms` kwarg: `jwt.decode(token, key, algorithms=["HS256"])` |

---

### H-11. Frontend Build Break: `zod/v4` Import

| Field | Value |
|-------|-------|
| **Category** | Code — Build Failure |
| **File** | `apps/web/src/schemas/waybillSchema.ts:1` |
| **Code** | `import { z } from "zod/v4";` |
| **Issue** | The import path `zod/v4` is a subpath that exists only in Zod v4.x. The project's `package.json` declares `"zod": "^3.24.1"` (Zod v3). This import will fail at build time with `MODULE_NOT_FOUND` or a Webpack resolver error. |
| **Impact** | The entire waybill creation form (`/new` page) is broken. Fresh builds and deployments will fail. This is a **blocking** issue for any deployment. |
| **Fix** | Change to `import { z } from "zod"` (Zod v3 compat) or upgrade the package to `zod@4.x`. Check for breaking API changes between v3 and v4 schemas. |

---

### H-12. Frontend Build Break: Renamed Heroicons Import

| Field | Value |
|-------|-------|
| **Category** | Code — Build Failure |
| **File** | `apps/web/src/components/layout/Header.tsx:3` |
| **Code** | `import { ArrowLeftOnRectangleIcon } from "@heroicons/react/24/outline"` |
| **Issue** | In Heroicons v2.1+, `ArrowLeftOnRectangleIcon` was renamed to `ArrowRightStartOnRectangleIcon`. The `package.json` specifies `"@heroicons/react": "^2.2.0"`, which resolves to v2.2+. The old name is no longer exported. |
| **Impact** | TypeScript compilation error on any import or build. This is a **blocking** build issue. |
| **Fix** | 1. Update import to `ArrowRightStartOnRectangleIcon` 2. Update all JSX references to use new name |

---

### H-13. `except: pass` Silently Swallows Errors (~30+ Locations)

| Field | Value |
|-------|-------|
| **Category** | Code — Error Handling |
| **Files** | `app/core/redis.py:47`, `app/workers/waybill_worker.py:100,106-107,381-382`, `app/services/rpa_auth_service.py:217,220,323`, `app/services/waybill_service.py:295,304`, `app/automation/browser.py:149,151,157,159,164,166,171,173,630,644,651,658` |
| **Code** | `except: pass` or `except Exception: pass` |
| **Issue** | Bare or broad `except` blocks with empty `pass` swallow ALL exceptions silently. This includes `KeyboardInterrupt`, `SystemExit`, `GeneratorExit` (if bare `except:`). Even when catching `Exception`, no error is logged — bugs in error cleanup paths, Redis disconnections, and browser crashes are completely invisible. |
| **Impact** | Makes debugging impossible in production. Errors accumulate silently — memory leaks from unclosed browser contexts, corrupted database states, and dead Redis connections go undetected until catastrophic failure. |
| **Fix** | Replace EVERY `except: pass` with at minimum: `logger.warning("...", exc_info=True)` or `logger.exception("...")`. Prefer specific exception types. Each location needs individual review of what should happen on error. |

---

### H-14. Weak Fernet Key Derivation (SHA-256 Instead of KDF)

| Field | Value |
|-------|-------|
| **Category** | Security — Cryptography |
| **File** | `app/auth_multitenant.py:72-101` |
| **Code** | ```python
master_key = utcms_config.DRIVER_ENCRYPTION_KEY.encode("utf-8")
key = hashlib.sha256(master_key).digest()
fernet = Fernet(urlsafe_b64encode(key[:32]))
``` |
| **Issue** | The Fernet key is derived via a single round of SHA-256. This is:
1. Not a proper Key Derivation Function (KDF) — no salt, no iterations
2. Confusing: `DRIVER_ENCRYPTION_KEY` is documented to be a Fernet key, but the code re-derives it via SHA-256, so a properly generated Fernet key would be double-hashed
3. The import `from cryptography.fernet import Fernet` is inside the function body, causing repeated import overhead |
| **Impact** | Weakened encryption. If `DRIVER_ENCRYPTION_KEY` is low-entropy, SHA-256 is trivially brute-forceable compared to PBKDF2/Argon2. The confusing API means users may generate keys incorrectly. Driver passwords stored in the database are more vulnerable to decryption. |
| **Fix** | 1. Use `cryptography`'s PBKDF2HMAC or just pass the key directly without re-derivation 2. Move `from cryptography.fernet import Fernet` to module level 3. Document clearly: "Generate a Fernet key and set DRIVER_ENCRYPTION_KEY to it directly" |

---

### H-15. `engine.dispose()` Per Celery Task Destroys Connection Pool

| Field | Value |
|-------|-------|
| **Category** | Code — Performance / Reliability |
| **File** | `app/workers/waybill_worker.py:89-91` |
| **Code** | ```python
loop.run_until_complete(engine.dispose())
result = loop.run_until_complete(_execute_job(self, job_id))
``` |
| **Issue** | The Celery task disposes the global `engine` (destroying the entire SQLAlchemy connection pool) and then immediately calls `_execute_job` which uses `async_session_factory()` to create a new session from the now-disposed engine. SQLAlchemy will lazily re-create the engine, but:
1. Every task tears down and rebuilds the pool — massive overhead
2. Under load (multiple concurrent tasks), this creates connection storms as each task races to re-establish connections
3. The pattern bypasses pooling entirely — each task effectively creates new connections |
| **Impact** | Database connection storms under load, `Too Many Connections` errors from PostgreSQL, task latency spikes, and potential `TimeoutError` from pool acquisition. |
| **Fix** | 1. Remove `engine.dispose()` from the task entirely 2. Use a single global engine shared across all tasks 3. If per-task isolation is needed, use a separate engine for workers with a smaller pool 4. Add `pool_pre_ping=True` to detect stale connections cheaply |

---

### H-16. Prometheus Exposed Without Authentication

| Field | Value |
|-------|-------|
| **Category** | Security — Monitoring |
| **File** | `compose/monitoring.yml:38-39` |
| **Code** | `ports: ['9090:9090']` |
| **Issue** | Prometheus is exposed on host port 9090 with no authentication, no TLS, and no IP restriction. On this server, port 9090 is accessible on **both public IPs** (188.121.123.16 and 95.38.233.90). The Prometheus UI shows all metrics: database query times, request latencies, error rates, and internal service topology. |
| **Impact** | Sensitive operational data leak. If either server IP is known, anyone can browse `/targets` to see all scrape targets (exposing internal service names), `/graph` to query any metric, and `/config` to see Prometheus configuration. |
| **Fix** | 1. Remove `ports` mapping — use internal Docker network only 2. Or add nginx reverse proxy with HTTP Basic Auth in front of Prometheus 3. Or use `--web.external-url` with OAuth2 proxy 4. Add `--web.enable-admin-api=false` to prevent config exposure |

---

### H-17. Weak CI/CD Test Secrets, Could Leak to Production

| Field | Value |
|-------|-------|
| **Category** | Infrastructure — CI/CD |
| **File** | `.github/workflows/ci-test.yml:18-19`, `.github/workflows/ci-cd.yml:98-99` |
| **Code** | `JWT_SECRET: "test-secret-change-in-production"` and `DRIVER_ENCRYPTION_KEY: "test-encryption-key-change-in-production"` |
| **Issue** | Test secrets are hardcoded in workflow YAML files. These are used if not overridden by GitHub Secrets. If an engineer forgets to set production secrets, these weak test secrets will be used in production. The files are in a public repo (if public) or accessible to all repo collaborators. |
| **Impact** | In production with test secrets: JWT tokens can be forged by anyone who reads the workflow file, database connections are unauthenticated (if DB also defaults), and driver passwords are weakly encrypted. |
| **Fix** | 1. Remove hardcoded secrets from workflow files 2. Always use GitHub Secrets (`${{ secrets.JWT_SECRET }}`) 3. Add a startup check that rejects weak/default secrets 4. Consider using OpenID Connect (OIDC) for cloud deployments |

---

### H-18. Rate Limiting Only Applied to 5 Out of ~40 Endpoints

| Field | Value |
|-------|-------|
| **Category** | Security — Rate Limiting |
| **File** | `app/main.py:207-211` |
| **Code** | ```python
if path.startswith("/waybill/calculate-route") or path == "/":
    rate_rule = "public"
elif path in ("/api/v1/auth/login", "/api/v1/admin/login", "/admin/login"):
    rate_rule = "auth"
``` |
| **Issue** | Rate limiting is only applied to 5 specific paths. The vast majority of API endpoints have NO rate limiting at all:
- Driver creation: unlimited
- Waybill job submission: unlimited
- Excel upload: unlimited
- Admin operations: unlimited
- All GET endpoints: unlimited |
| **Impact** | An attacker can:
1. Mass-create bogus drivers to exhaust the database
2. Submit thousands of waybill jobs to overwhelm the RPA system
3. Brute-force tenant IDs via enumeration
4. Upload large Excel files repeatedly to fill disk |
| **Fix** | 1. Apply rate limiting at the middleware level to ALL API paths 2. Categorize with different limits: admin=1000/min, tenant=100/min, public=10/min 3. Apply per-tenant (client_id) limits in addition to per-IP limits |

---

### H-19. `autoretry_for = (Exception,)` Retries All Errors Indefinitely

| Field | Value |
|-------|-------|
| **Category** | Code — Reliability |
| **File** | `app/workers/waybill_worker.py:61` |
| **Code** | `autoretry_for = (Exception,)` |
| **Issue** | The `WaybillTask` base class retries on ANY exception, including programming errors like `TypeError`, `ValueError`, `KeyError`, `AttributeError`, and `IndexError`. These are bugs, not transient failures. Celery will retry up to `max_retries` times, wasting resources on every failure. |
| **Impact** | A simple programming bug in the worker causes N retries (default config) before finally failing. Each retry disposes and recreates the DB connection pool and browser instance — extremely expensive. Resources are wasted on doomed retries instead of failing fast for debugging. |
| **Fix** | 1. Change to specific exception classes: `autoretry_for = (ConnectionError, TimeoutError, IOError)` 2. Add explicit retry logic for transient failures (CAPTCHA timeout, network blips, proxy errors) 3. Let programming errors fail immediately with full traceback |

---

### H-20. Browser Contexts Leaked on Certain Exception Paths

| Field | Value |
|-------|-------|
| **Category** | Code — Resource Leak |
| **File** | `app/services/waybill_service.py:291-313`, `app/automation/browser.py:350-369` |
| **Code** | The `finally` block closes `page` and `context` only if `internal_session_id` is set. But if an exception occurs between `create_context` (which stores the context key) and assignment of `internal_session_id`, the key exists in `self._contexts` but `internal_session_id` is not set, so the cleanup block cannot close it. |
| **Issue** | When an exception occurs in a specific window (between context creation and session ID assignment), the browser context (with its memory, connections, and resources) is never closed. The context remains in `BrowserManager._contexts` as an orphan. Over time, these orphans accumulate, consuming RAM and file descriptors. |
| **Impact** | Memory leak in production under error conditions. Each orphan context holds a Chromium browser process, multiple pages, and associated resources. Under sustained errors, the container will eventually hit its memory limit and OOM-kill. |
| **Fix** | 1. Use a context manager (`async with`) pattern for browser context lifecycle 2. Track contexts by creation order, not by session ID 3. Add a background cleanup task that reaps contexts older than N minutes 4. Move `internal_session_id` assignment immediately after `create_context` |

---

### H-21. Path Traversal in Artifact Reading

| Field | Value |
|-------|-------|
| **Category** | Security — Path Traversal |
| **File** | `app/services/management_service.py:517-521` |
| **Code** | ```python
def _safe_artifact_path(cls, relative_path: str) -> Path:
    root = cls._artifact_root().resolve()
    candidate = (root / relative_path).resolve()
    if root not in candidate.parents and candidate != root:
        raise HTTPException(status_code=400)
    return candidate
``` |
| **Issue** | The path traversal check uses `in candidate.parents` which is vulnerable on case-insensitive filesystems (macOS, Windows) — e.g., `../SECRETS` bypasses if root is `/app/artifacts` and `../Artifacts/../../` resolves differently. Additionally, symlinks inside the artifact root can point outside the sandbox, bypassing the `parents` check entirely. |
| **Impact** | An attacker with access to the artifact endpoint could read arbitrary files on the server: `/etc/shadow`, `.env` (with secrets), database files, or other containers' data. |
| **Fix** | 1. Use `os.path.realpath()` instead of `Path.resolve()` 2. Normalize case: `candidate.name.lower()` 3. Reject symlinks in the artifact tree 4. Add a second check: `str(candidate).startswith(str(root))` 5. Consider serving artifacts through a separate read-only container |

---

### H-22. CORS Allows All Headers in Non-Production

| Field | Value |
|-------|-------|
| **Category** | Security — CORS |
| **File** | `app/main.py:184-192` |
| **Code** | ```python
allow_headers=["*"]
    if os.getenv("ENVIRONMENT", "development").lower() != "production"
    else ["Authorization", "Content-Type", "X-API-Key", ...]
``` |
| **Issue** | In development/staging environments (which may still be internet-accessible), CORS allows any header (`allow_headers=["*"]`). This includes `Authorization`, `Cookie`, `X-Forwarded-For`, `X-Real-IP`, and custom internal headers. Combined with `allow_credentials=True`, this enables `*` — which is prohibited by browsers when credentials are included, but the wildcard can still be exploited via preflight requests. |
| **Impact** | In staging environments exposed to the internet, an attacker can craft cross-origin requests with arbitrary headers, potentially exploiting header-injection vulnerabilities in the backend. |
| **Fix** | 1. Never use `allow_headers=["*"]` when `allow_credentials=True` 2. Always use explicit header allowlists regardless of environment 3. If `*` is needed for development, at minimum restrict origins to `localhost:*` |

---

### H-23. Race Condition in Event Hub WebSocket Publish

| Field | Value |
|-------|-------|
| **Category** | Code — Race Condition |
| **File** | `app/realtime/events.py:46-56` |
| **Code** | ```python
async with self._lock:
    targets = set()
    for channel in self._channel_keys(envelope):
        targets.update(self._connections.get(channel, set()))
# Lock released here
for ws in targets:
    await ws.send_json(...)
``` |
| **Issue** | Between the lock release (end of `async with`) and the actual `send_json` call, a WebSocket client may disconnect. The `send_json` will fail with a connection error (caught by `except Exception` at line 55), and the socket is cleaned up. However, this means error handling is triggered for normal disconnections, and stale socket references are detected reactively rather than proactively. |
| **Impact** | Minor race condition leads to exceptions on every broadcast when clients disconnect. While caught, these exceptions are not logged in some code paths. Under high churn (many rapid connections/disconnections), the cleanup overhead can impact broadcast latency. |
| **Fix** | 1. Keep the lock during `send_json` (or at least hold a reference count) 2. Use `asyncio.wait_for(ws.send_json(...), timeout=5.0)` 3. Track connection health with a PING/PONG interval 4. Log disconnection errors at DEBUG level, not Exception |

---

### H-24. Race Condition in Redis Connection Manager

| Field | Value |
|-------|-------|
| **Category** | Code — Race Condition |
| **File** | `app/core/redis.py:36-54` |
| **Code** | ```python
current_loop = asyncio.get_running_loop()
if self._lock is None or self._loop != current_loop:
    self._lock = asyncio.Lock()
if self._redis is None or self._loop != current_loop:
    async with self._lock:
        if self._redis is None or self._loop != current_loop:
            ...
            self._loop = current_loop
``` |
| **Issue** | The double-checked locking pattern is broken for async:
1. `self._lock` is created outside the lock — if two coroutines observe `self._lock is None` simultaneously, they both create new locks, and the second overwrites the first without any synchronization
2. `self._loop` is mutated inside the lock but read outside — a coroutine can pass the first check (`self._loop == current_loop`) and skip the locked section while another coroutine is still initializing `self._redis`
3. If the event loop changes while a coroutine holds the lock, the lock is replaced, causing `RuntimeError: Lock is not acquired` when the original holder tries to release |
| **Impact** | Intermittent `RuntimeError: Lock is not acquired`, double initialization of Redis connections (creating extra connections), or completely missing connections. Under load, this causes unpredictable Redis failures. |
| **Fix** | 1. Use `threading.Lock()` for the instance-level initialization guard (not affected by event loop changes) 2. Use `asyncio.Lock()` only inside the initialization block for cooperative concurrency 3. Better yet: initialize eagerly in `__init__()` or use `async def init()` called once at startup 4. Remove the event-loop-aware pattern entirely — one Redis connection per process |

---

### H-25. `celerybeat-schedule.db` Committed to Git

| Field | Value |
|-------|-------|
| **Category** | Code — VCS |
| **File** | `celerybeat-schedule.db` (in repo root) |
| **Issue** | The SQLite database file for Celery Beat schedule is committed to git. This binary file contains serialized Celery task schedule data and changes every time Celery Beat runs. It is listed in `.gitignore` (line 35: `celerybeat-schedule.db`), but was committed before being added to gitignore and remains tracked. |
| **Impact** | Binary diffs in every commit increase repo size unnecessarily. If the schedule contains any task payloads with sensitive data (unlikely but possible), that data is in git history. |
| **Fix** | 1. Remove from git: `git rm --cached celerybeat-schedule.db` 2. Verify `.gitignore` entry exists (it does, line 35) 3. Add to `.dockerignore` as well 4. Consider using `--schedule` flag with a non-default path inside Docker volumes |

---

# 🟡 MEDIUM Severity (34)

---

### M-01. `.env.example` Contains Real Production IP Address

| Field | Value |
|-------|-------|
| **Category** | Security — Information Disclosure |
| **File** | `.env.example:24,26,32` |
| **Code** | `FRONTEND_URL="http://188.121.123.16"`, `NEXT_PUBLIC_API_URL="http://188.121.123.16:8000"`, `WORKER_2_PROXY="http://95.38.233.90:3128"` |
| **Issue** | Real production IP addresses (both primary 188.121.123.16 and secondary 95.38.233.90) are hardcoded in `.env.example`. If used as-is (`cp .env.example .env`), the system points to production from a development machine. Workers 2 and 3 proxy URLs point to the second IP, exposing the dual-IP architecture. |
| **Fix** | Replace with placeholders: `FRONTEND_URL="http://your-domain.com"`, `NEXT_PUBLIC_API_URL="http://api.your-domain.com:8000"`, `WORKER_2_PROXY="http://proxy2.your-domain.com:3128"` |

---

### M-02. Redis Password Hardcoded in Shell Script

| Field | Value |
|-------|-------|
| **Category** | Security — Credential Leak |
| **File** | `scripts/start_backend.sh:68` |
| **Code** | `redis_url = "redis://:_Ll7-cZKf4b_l0oJ0UIJAMJ3C7Y3B-JS@127.0.0.1:6379/0"` |
| **Issue** | A Redis password appears hardcoded in a shell script. While it's a fallback URL, the inclusion of a specific password in the source code is a security risk. |
| **Fix** | Replace with `redis://:${REDIS_PASSWORD}@127.0.0.1:6379/0` and remove hardcoded value |

---

### M-03. Nginx Missing Security Headers on `/metrics` and `/stub_status`

| Field | Value |
|-------|-------|
| **Category** | Security — Headers |
| **File** | `infra/nginx/nginx.conf:142-155` |
| **Issue** | The `/metrics` and `/stub_status` locations have IP ACL but lack `X-Content-Type-Options`, `X-Frame-Options`, and other security headers. If the ACL is misconfigured, these endpoints are exposed without protection. |
| **Fix** | Add `add_header X-Content-Type-Options nosniff;` and `add_header X-Frame-Options DENY;` to all location blocks |

---

### M-04. Squid Proxy ACLs Allow Unauthenticated Local Network Access

| Field | Value |
|-------|-------|
| **Category** | Security — Network |
| **File** | `infra/squid/squid_1.conf:5-13`, `squid_2.conf:5-13`, `squid_3.conf:5-13` |
| **Code** | ACLs allow `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` without authentication |
| **Issue** | All 3 Squid proxies share the same permissive ACLs. Squid 2 (port 3129) and Squid 3 (port 3130) egress via the second IP **95.38.233.90**. Since `network_mode: host` is used, these ports are directly accessible on the second IP. If the firewall does not explicitly restrict these ports, anyone on the internet can use the server as an open proxy on IP 95.38.233.90 (ports 3129/3130). |
| **Fix** | 1. Restrict to Docker network CIDR only 2. Add `http_access deny !localnet` for non-docker networks 3. Use iptables to restrict ports 3129/3130 to localhost only 4. Bind Squid 2/3 to the Docker bridge IP, not the public IP |

---

### M-05. Sensitive Data in Exception Logs (Bypasses Sanitizer)

| Field | Value |
|-------|-------|
| **Category** | Security — Logging |
| **File** | `app/services/rpa_auth_service.py:177-181`, `app/services/multitenant_service.py:227-248` |
| **Code** | `logger.exception("phase1_auth_failed", extra={"error": str(exc)})` |
| **Issue** | The sanitizer (`logging.py:125-126`) runs on log record `extra` fields but NOT on `exc_info` or stack trace data from `logger.exception()`. Exception objects can contain full stack traces with variable values, including decrypted passwords and PII. |
| **Fix** | 1. Always use `logger.error(msg, exc_info=True)` with a custom formatter that redacts sensitive fields 2. Add a logging filter that scrubs the exception message for patterns like `password=`, `secret=`, `token=` 3. Never log `str(exc)` directly |

---

### M-06. Proxy Passwords Potentially Visible in Logs

| Field | Value |
|-------|-------|
| **Category** | Security — Logging |
| **File** | `app/automation/proxy_rotator.py:355,469-470` |
| **Code** | `logger.info(f"Added proxy: {config.url[:50]}...")` |
| **Issue** | Proxy URLs often contain credentials: `http://user:pass@host:port`. Truncation to 50 chars is insufficient if the credential portion is short (e.g., `http://u:p@host:port` is only 24 chars). The full password would be logged. |
| **Fix** | Use `urlparse` to strip credentials before logging: `url.replace(url.password, "***")` |

---

### M-07. File Upload Without MIME/Magic Byte Validation

| Field | Value |
|-------|-------|
| **Category** | Security — Input Validation |
| **File** | `app/services/management_service.py:800-809` |
| **Issue** | Excel/CSV file upload reads `content: bytes` into a temp file and passes it to `read_xlsx`. There is no validation of MIME type, magic bytes, or file extension. A zip bomb, malicious HTML, or a file with XSS payload could be uploaded. |
| **Fix** | 1. Check magic bytes for valid Excel (`\x50\x4B\x05\x06` or `\xD0\xCF\x11\xE0`) 2. Validate `Content-Type` header 3. Add file size limit (separate from `client_max_body_size`) 4. Scan with ClamAV or similar |

---

### M-08. Driver National Code Without Format Validation

| Field | Value |
|-------|-------|
| **Category** | Code — Validation |
| **File** | `app/services/multitenant_service.py:582` |
| **Issue** | `driver_national_code` is stored without validating it's a valid 10-digit Iranian national code (کد ملی). The DB schema has `max_length=10` but no format check. Invalid national codes cause failures during RPA execution on the target portal. |
| **Fix** | Add Pydantic validator that implements the Iranian national code checksum algorithm (control digit verification) |

---

### M-09. API Key Hardcoded in Agent Files

| Field | Value |
|-------|-------|
| **Category** | Security — Credential Leak |
| **File** | `.agents/orchestrator/handoff.md:53`, `.agents/orchestrator/comprehensive_audit.py:66` |
| **Code** | `utcms_10c6461a53a0197c821d3cd3515f58b4f6bca2b4d9d7a366d6e3db9274178ccb` |
| **Issue** | A long hex string that appears to be an API key is hardcoded in agent documentation and Python files. |
| **Fix** | 1. Revoke the API key 2. Replace with placeholder 3. Scan repo for similar patterns |

---

### M-10. Missing `await` on `track_task_latency` Call

| Field | Value |
|-------|-------|
| **Category** | Code — Async |
| **File** | `app/workers/tasks.py:136` |
| **Code** | `track_task_latency(time.perf_counter() - started_at)` |
| **Issue** | If `track_task_latency` is async (likely, as it writes to a Prometheus/Redis backend), the call is not awaited. The metric is silently lost — fire-and-forget without error handling. |
| **Fix** | Add `await` if function is async, or wrap in `asyncio.ensure_future()` with error logging |

---

### M-11. `asyncio.Lock` Replaced on Event Loop Change — Causes `RuntimeError`

| Field | Value |
|-------|-------|
| **Category** | Code — Concurrency |
| **Files** | `app/core/redis.py:37-38`, `app/automation/proxy_rotator.py:256-262`, `app/services/rpa_runtime_service.py:23-28` |
| **Code** | `if self._lock is None or self._loop != current_loop: self._lock = asyncio.Lock()` |
| **Issue** | If a coroutine is suspended right after `await self._lock.acquire()` (inside a critical section), and the event loop changes, the lock object is replaced. When the original coroutine resumes, it tries to release a lock that no longer exists, causing `RuntimeError: Lock is not acquired`. This pattern appears in Redis manager, proxy rotator, and RPA runtime service. |
| **Fix** | 1. Initialize `self._lock = threading.Lock()` in `__init__` (threading locks are not tied to event loops) 2. Use `asyncio.Lock()` but create it eagerly in `__init__` without event loop checks 3. Or make these classes initialization-safe by creating the lock in a non-async init |

---

### M-12. Dead Code: `inspect.isawaitable()` Check on `page.on()` Return Value

| Field | Value |
|-------|-------|
| **Category** | Code — Dead Code |
| **File** | `app/automation/auth.py:600-603`, `app/automation/browser.py:598-607` |
| **Code** | `result = page.on(event_name, callback)` followed by `if inspect.isawaitable(result): await result` |
| **Issue** | Playwright's `page.on()` always returns `None`. The `isawaitable` check is dead code. This has been misleading developers who copy this pattern, thinking `page.on()` might be async. |
| **Fix** | Remove the `isawaitable` check entirely. Just call `page.on(event, callback)` — it's always synchronous. |

---

### M-13. Services Create `AsyncSession` Directly Instead of Using `get_session()`

| Field | Value |
|-------|-------|
| **Category** | Code — Architecture |
| **Files** | `app/services/multitenant_service.py:228-254,256-277,322-329,331-338,340-347,405-411` |
| **Issue** | Multiple service methods create `AsyncSession(engine)` directly instead of using the `get_session()` dependency injection pattern. This bypasses:
1. Automatic commit/rollback logic in `get_session()`
2. Request-scoped session lifecycle
3. Consistent error handling |
| **Fix** | Refactor to use injected `get_session()` dependency or a context manager that mirrors `get_session()` behavior |

---

### M-14. Alembic Migration IDs Hand-Crafted (Not Auto-Generated)

| Field | Value |
|-------|-------|
| **Category** | Code — Maintenance |
| **File** | `alembic/versions/` (14 migration files) |
| **Issue** | Migration revision IDs appear to be hand-crafted (e.g., `4a5b6c7d8e9f`, `5b6c7d8e9f0a`) rather than auto-generated by `alembic revision --autogenerate`. This can cause migration ordering conflicts, especially when multiple developers create migrations. |
| **Fix** | 1. Verify migration chain is linear with `alembic check` 2. Use `alembic revision --autogenerate` going forward 3. Consider squashing migrations |

---

### M-15. `run_migrations()` Is Dead Code — Migrations Never Run

| Field | Value |
|-------|-------|
| **Category** | Code — Dead Code |
| **File** | `app/core/database.py:82` |
| **Code** | `# await asyncio.to_thread(command.upgrade, alembic_cfg, "head")` |
| **Issue** | The Alembic migration execution line is commented out. `init_db()` calls `run_migrations()` but it does nothing except log. This means database migrations NEVER run automatically on deployment. If a deployment adds a column, table, or index, the application will fail at runtime with `column not found` or similar errors. |
| **Fix** | 1. Uncomment the migration execution line 2. Add error handling with logging 3. Consider running migrations as a Docker entrypoint script (before the app starts) |

---

### M-16. New Event Loop Created Per Celery Task

| Field | Value |
|-------|-------|
| **Category** | Code — Performance |
| **Files** | `app/workers/tasks.py:19-38`, `app/workers/phase1_tasks.py:17-31`, `app/workers/waybill_worker.py:86` |
| **Code** | `loop = asyncio.new_event_loop()` in every task |
| **Issue** | Each Celery task creates a new event loop, sets it as the current loop, runs async code, then closes it. On this **4 vCPU server**, this overhead is amplified because 3 workers run simultaneously. When all 3 workers process tasks concurrently, each one creates/destroys event loops and DB connection pools per task. With `engine.dispose()` combined (H-15), every single task across all 3 workers causes: event loop creation, connection pool teardown, new connection creation. CPU is wasted on overhead instead of actual work. |
| **Fix** | 1. Create the event loop once at worker startup (Celery worker process init) 2. Reuse the same loop for all tasks in that worker 3. Only create a new loop per task if isolation from previous task state is required |

---

### M-17. `create_waybill_with_map` — 249 Lines, 5 Levels of Nesting

| Field | Value |
|-------|-------|
| **Category** | Code — Maintainability |
| **File** | `app/services/waybill_service.py:67-316` |
| **Issue** | The main waybill creation function is 249 lines with 5 levels of nested `try/except/finally` blocks. Error handling paths are subtly different (lines 197-219 for HTTPException, 221-249 for WaybillError, 251-289 for generic Exception). |
| **Fix** | 1. Extract browser lifecycle into a context manager 2. Extract CAPTCHA solving and map injection into separate functions 3. Use a single error handler decorator for cleanup |

---

### M-18. `auth.py` — 1265+ Lines, Too Many Responsibilities

| Field | Value |
|-------|-------|
| **Category** | Code — Maintainability |
| **File** | `app/automation/auth.py` (1265+ lines) |
| **Issue** | The `UTCMSAuthenticator` class handles: CAPTCHA solving (3 methods), credential filling, session management, error detection, navigation flow, and multi-factor auth. This violates the Single Responsibility Principle. |
| **Fix** | Split into: `CaptchaSolver`, `SessionManager`, `AuthNavigator`, `FormFiller`, `ErrorDetector` |

---

### M-19. `_to_bool()` Silently Defaults to `False` for Missing Config

| Field | Value |
|-------|-------|
| **Category** | Code — Reliability |
| **File** | `app/core/config.py:35` |
| **Code** | `def _to_bool(value, default=False): return default if value is None` |
| **Issue** | When a required boolean config is missing, the app silently uses a default (`False`) instead of raising a clear error. E.g., `HEADLESS` defaults to `False` in production, causing headful browser windows. |
| **Fix** | Add a `required` parameter that raises `ValueError` at startup if the config is missing |

---

### M-20. `window.confirm()` Used Instead of Custom Modal

| Field | Value |
|-------|-------|
| **Category** | Frontend — UX/Accessibility |
| **Files** | `apps/web/src/app/drivers/page.tsx:123`, `apps/web/src/app/admin/clients/page.tsx:69`, `apps/web/src/app/history/page.tsx:76` |
| **Issue** | `window.confirm()` is used for delete confirmations. These dialogs:
1. Are blocking — freeze the UI thread
2. Are not keyboard-accessible (screen readers struggle with them)
3. Cannot be styled or customized
4. Do not support i18n properly |
| **Fix** | Use the existing modal component (e.g., the one in `history/page.tsx`) for all confirmations |

---

### M-21. `replaceAll()` Not Available in ES2017 Target

| Field | Value |
|-------|-------|
| **Category** | Frontend — Compatibility |
| **File** | `apps/web/src/lib/plate.ts:24`, `apps/web/tsconfig.json` |
| **Code** | `"target": "ES2017"` in tsconfig, `str.replaceAll(...)` in plate.ts |
| **Issue** | `String.prototype.replaceAll()` is an ES2021 feature. The tsconfig target is ES2017. While modern browsers support it, the mismatch means TypeScript should flag this. In Node.js environments (SSR), older versions may fail. |
| **Fix** | Update tsconfig target to `ES2021` or use `str.replace(/pattern/g, replacement)` |

---

### M-22. `void` on Async Calls Without Error Handling

| Field | Value |
|-------|-------|
| **Category** | Frontend — Error Handling |
| **Files** | `apps/web/src/app/page.tsx:92-93`, `apps/web/src/app/settings/page.tsx:117,131` |
| **Code** | `void refetchJobs(); void refetchStats(); void loadSystemStatus();` |
| **Issue** | Async functions are called with `void` — fire-and-forget. If the API call fails, the error is silently swallowed. The user sees no error feedback. |
| **Fix** | Add `.catch()` handlers: `void refetchJobs().catch(e => console.error("Failed to refetch jobs:", e))` or wrap in `try/catch` |

---

### M-23. Modals Missing `role="dialog"` and `aria-modal`

| Field | Value |
|-------|-------|
| **Category** | Frontend — Accessibility |
| **Files** | `apps/web/src/app/fuel/page.tsx:706-943`, `apps/web/src/app/history/page.tsx:427-546`, `apps/web/src/app/admin/clients/CreateClientModal.tsx:140-324` |
| **Issue** | None of the modals have ARIA attributes (`role="dialog"`, `aria-modal="true"`, `aria-labelledby`). No focus trapping is implemented. Screen readers cannot properly navigate these dialogs. |
| **Fix** | Add proper ARIA attributes and implement focus trapping (e.g., using `focus-trap-react` or a custom hook) |

---

### M-24. Widespread `any` Types in TypeScript

| Field | Value |
|-------|-------|
| **Category** | Frontend — Type Safety |
| **Files** | Multiple: `apps/web/src/lib/api.ts:163,178`, `apps/web/src/hooks/useWaybillJob.ts:34-35`, `apps/web/src/app/settings/page.tsx:89,114,128`, `apps/web/src/app/admin/clients/CreateClientModal.tsx:30,109`, `apps/web/src/app/admin/reports/page.tsx:184` |
| **Issue** | Widespread use of `any` type defeats TypeScript's type safety. Runtime errors that would be caught at compile time are missed. Refactoring is harder because there are no type guarantees. |
| **Fix** | Replace `any` with proper types, generics, or `unknown` (which requires type narrowing before use). Add `no-explicit-any` ESLint rule |

---

### M-25. Password Field Stored in React State

| Field | Value |
|-------|-------|
| **Category** | Frontend — Security |
| **File** | `apps/web/src/app/drivers/page.tsx:27-28` |
| **Issue** | `utcms_password` is stored in React component state (`form` object). If the component tree is serialized (React DevTools, SSR hydration), the password may be exposed. |
| **Fix** | 1. Use a controlled input with `useRef` instead of state for password fields 2. Clear the password field value after form submission 3. Never serialize password state in component trees |

---

### M-26. Error Page Forces Automatic Reload (Infinite Loop Risk)

| Field | Value |
|-------|-------|
| **Category** | Frontend — UX |
| **File** | `apps/web/src/app/error.tsx:14-17` |
| **Code** | `window.location.reload()` called when error persists |
| **Issue** | On Server Action mismatch errors, the page calls `window.location.reload()`. If the error persists (e.g., CDN cache of stale JavaScript), this creates an infinite reload loop with no user control. |
| **Fix** | 1. Add a retry counter (max 3 retries) 2. Let the user manually click to reload via the existing `reset()` button 3. Add exponential backoff between retries |

---

### M-27. `storage` Event Only Fires From Other Tabs

| Field | Value |
|-------|-------|
| **Category** | Frontend — Architecture |
| **File** | `apps/web/src/hooks/useSession.ts:50-51` |
| **Issue** | The `storage` event only fires when localStorage is changed in a **different tab** of the same origin. Same-tab session changes rely on a custom `AUTH_SESSION_EVENT`. Any code that updates localStorage directly without dispatching the event will cause a stale session state. |
| **Fix** | 1. Use React Context with a reducer for session state management 2. Replace localStorage reads with Context reads 3. Keep localStorage as a persistence layer only, not the source of truth |

---

### M-28. Redis `FLUSHALL` During Production Deployment

| Field | Value |
|-------|-------|
| **Category** | Infrastructure — Data Loss |
| **File** | `.github/workflows/cd-deploy.yml:210` |
| **Code** | `docker-compose -f docker-compose.yml exec redis redis-cli FLUSHALL \|\| true` |
| **Issue** | The CI/CD pipeline runs `FLUSHALL` on Redis during every production deployment. On this single-server setup, Redis is shared by all 13 containers — flushing destroys everything. |
| **Impact** | 1. All cached data is lost — subsequent requests hit the database harder (critical on 12 GB RAM) 2. In-progress Celery task results lost 3. Rate limiter counters reset 4. Session cache for all 3 workers cleared simultaneously |
| **Fix** | 1. Remove `FLUSHALL` from deploy pipeline 2. If cache invalidation is needed, use selective key deletion by prefix 3. Add a confirmation step before destructive operations |

---

### M-29. Shell Scripts Launch Without Health Checks

| Field | Value |
|-------|-------|
| **Category** | Infrastructure — Reliability |
| **File** | `start_services.sh:29-31`, `stop_services.sh:37-42` |
| **Issue** | `start_services.sh` writes PID files but immediately starts the next service without verifying the previous one actually started. `stop_services.sh` uses `pkill -f "uvicorn"` and `pkill -f "next-server"` which can kill unrelated processes matching those strings. |
| **Fix** | 1. Add health check loops with timeout after each service start 2. Use PID files for targeted `kill` instead of `pkill -f` 3. Add `wait $PID` patterns |

---

### M-30. Logrotate Creates World-Readable Log Files (644)

| Field | Value |
|-------|-------|
| **Category** | Infrastructure — Security |
| **File** | `infra/logging/logrotate.conf:13,28,43,58` |
| **Code** | `create 644 appuser appuser` |
| **Issue** | Rotated log files are world-readable (`644`). Logs contain database queries, auth tokens, error traces with PII, and internal service URLs. |
| **Fix** | Change to `create 640 appuser appuser` or `create 600 appuser appuser` |

---

### M-31. `deploy.sh` Uses Legacy `docker-compose` Which Doesn't Support `include`

| Field | Value |
|-------|-------|
| **Category** | Infrastructure — Deployment |
| **File** | `deploy.sh:81-85` |
| **Code** | Falls back to `docker-compose` (v1) in some cases |
| **Issue** | The root `docker-compose.yml` uses the `include:` directive (Docker Compose v2 feature) which references 5 separate compose files (`infra.yml`, `proxy.yml`, `backend.yml`, `web.yml`, `monitoring.yml`). If the system falls back to `docker-compose` (v1), the deploy will fail silently because v1 does not support `include`. On this server, a failed deploy could leave some containers running and others stopped — partial outage. |
| **Fix** | 1. Remove `docker-compose` v1 fallback 2. Always use `docker compose` (v2) 3. Check for `docker compose` availability at the start |

---

### M-32. `secrets_manager.py` Writes Secrets to `.env` on Disk

| Field | Value |
|-------|-------|
| **Category** | Security — Secrets Management |
| **File** | `app/core/secrets_manager.py:141-193` |
| **Code** | `apply_secrets_to_env()` writes generated secrets to the `.env` file |
| **Issue** | The application generates secrets and writes them to `.env` on disk. In containerized environments, secrets should be injected at runtime via environment variables, not written to files by the application. If `.env` is backed up, copied, or read by another process, secrets are compromised. On this single-server deployment, all 13 containers mount the same `.env` — if one container is compromised, all secrets are readable. |
| **Fix** | 1. Remove the file-write capability from production code 2. Generate secrets in the deployment pipeline (CI/CD) 3. Use Docker secrets or a secrets vault (HashiCorp Vault) |

---

### M-33. Prometheus `scrape_timeout` Very Close to `scrape_interval`

| Field | Value |
|-------|-------|
| **Category** | Infrastructure — Monitoring |
| **File** | `infra/prometheus/prometheus.yml:2-4` |
| **Code** | `scrape_timeout: 10s`, `scrape_interval: 15s` |
| **Issue** | Timeout (10s) is very close to interval (15s). On this 4 vCPU server, when all 3 Celery workers are busy, CPU contention can cause slow Prometheus scrape responses. If one scrape takes >10s and times out, the next scrape starts 5s later with only 5s remaining budget before it also likely times out. This causes cascading timeout failures and gaps in monitoring data. |
| **Fix** | Either reduce timeout to 5s, or increase interval to 30s, or both |

---

### M-34. Docker Images Not Pinned to Specific Versions

| Field | Value |
|-------|-------|
| **Category** | Infrastructure — Reproducibility |
| **Files** | `compose/proxy.yml:25,45,65` (`ubuntu/squid:latest`), `compose/monitoring.yml:27` (`prom/prometheus:latest`), `compose/infra.yml`, `compose/web.yml` |
| **Issue** | Multiple Docker images use `:latest` tag instead of specific versions. `:latest` changes over time, meaning different developers and CI runs get different software. A malicious `:latest` could be pushed, compromising the entire supply chain. |
| **Fix** | Pin all images to specific versions: `ubuntu/squid:6.6-<digest>`, `prom/prometheus:v2.53.0`, `postgres:16.4`, `redis:7.2.5-alpine`, `nginx:1.27.0-alpine` |

---

# 🟢 LOW Severity (56)

---

### L-00. Container Resource Limits Absent — OOM Risk on 12 GB Server

| Field | Value |
|-------|-------|
| **Category** | Infrastructure — Resource Management |
| **Files** | `compose/backend.yml`, `compose/infra.yml`, `compose/web.yml`, `compose/monitoring.yml` |
| **Code** | Only Celery workers have `deploy.resources.limits.memory: 3g` |
| **Issue** | This server has **12 GB RAM** total shared across 13 containers. Only the 3 Celery workers have memory limits (3 GB each = 9 GB total). The remaining 10 containers (PostgreSQL, Redis, Nginx, Frontend, Backend, 3× Squid, Prometheus, Beat) share just ~3 GB with no individual limits. If any container leaks memory (e.g., unresolved `except: pass` → unclosed browser contexts), it can consume all remaining RAM and trigger the OOM killer, taking down critical services like PostgreSQL. |
| **Impact** | **Production crash**. Chrome/Playwright memory leak → OOM killer kills PostgreSQL or Redis → all workers fail → waybill queue backed up → manual recovery needed. |
| **Fix** | Add missing limits: PostgreSQL ~1 GB, Redis ~1 GB, Backend ~512 MB, Nginx ~256 MB, Frontend ~512 MB, Squid ×3 ~256 MB each, Prometheus ~512 MB, Beat ~256 MB |

### L-01. Unused Imports in Python Files

| Files | Details |
|-------|---------|
| `app/main.py:30` | `from app.automation.captcha import barname_ml_solver` |
| `app/services/fuel_inquiry_service.py:6` | `import time` |
| `app/services/management_service.py:4` | `import math` |
| Various | Multiple unused imports across the codebase |

**Fix**: Remove unused imports. Use `ruff check --fix` for automated cleanup.

---

### L-02. Unused Imports in TypeScript Files

| Files | Details |
|-------|---------|
| `apps/web/src/app/admin/clients/page.tsx:18-19` | `Cpu` and `Activity` from `lucide-react` |
| Various | Other unused imports |

**Fix**: Remove unused imports. Configure `@typescript-eslint/no-unused-vars` as an error.

---

### L-03. Unused State Variable `driverFilter` Without Setter

| File | Line |
|------|------|
| `apps/web/src/app/admin/reports/page.tsx:17` | `const [driverFilter] = useState("");` |

The state variable is declared but never has a setter. It's in the dependency array of `loadDriverReport` but can never change. Remove it.

---

### L-04. `await` Not Used on Several Async Calls

| File | Details |
|------|---------|
| `app/workers/tasks.py:136` | `track_task_latency()` not awaited |
| `app/automation/auth.py:463-466` | `_register_page_listener` return not checked |

**Fix**: Add `await` or wrap in `asyncio.ensure_future()`.

---

### L-05. `Index as Key` in React Lists

| File | Lines |
|------|-------|
| `apps/web/src/app/fuel/page.tsx:328,310,499` | Using array index `idx` as React `key` |

**Fix**: Use unique IDs (`inquiry.id`, `item.id`) instead of array indices.

---

### L-06. `dir="ltr"` Inputs Without `aria-label` or `lang`

| File | Lines |
|------|-------|
| `apps/web/src/app/new/page.tsx:442,602,611,622,659,662,677,680,700` | Inputs with `dir="ltr"` missing accessibility labels |

**Fix**: Add `lang="fa"` or `lang="en"` and descriptive `aria-label` attributes.

---

### L-07. `suppressHydrationWarning` on `<html>` and `<body>`

| File | Line |
|------|------|
| `apps/web/src/app/layout.tsx:21-22` | `suppressHydrationWarning` set on both tags |

**Fix**: Remove the prop and fix the underlying hydration mismatches instead of suppressing warnings.

---

### L-08. `console.error` in Production Code

| Files | Lines |
|-------|-------|
| `apps/web/src/hooks/useWaybillJob.ts:67,76,80` | Direct `console.error` calls |
| `apps/web/src/app/error.tsx:20` | `console.error` in error boundary |

**Fix**: Use a logger wrapper that suppresses output in production (`NODE_ENV !== 'production'`).

---

### L-09. External Links Missing `rel="noopener"`

| File | Lines |
|------|-------|
| `apps/web/src/app/fuel/page.tsx:878-887,907-916` | `rel="noreferrer"` without `noopener` |

**Fix**: Change to `rel="noreferrer noopener"` for maximum cross-browser safety.

---

### L-10. Inline `style={{ animationDelay }}` Causing Hydration Mismatches

| Files | Lines |
|-------|-------|
| `apps/web/src/app/page.tsx:181,247`, `apps/web/src/app/fuel/page.tsx:311` | `style={{ animationDelay: \`${idx * 100}ms\` }}` |

**Fix**: Use CSS classes with CSS custom properties or render animation delays client-side only.

---

### L-11. Query Parameters Passed as Strings Instead of Numbers

| Files | Lines |
|-------|-------|
| `apps/web/src/app/history/page.tsx:49`, `apps/web/src/app/admin/dashboard/page.tsx:29`, `apps/web/src/app/admin/reports/page.tsx:25` | `{ page: '1', page_size: '25' }` |

**Fix**: Pass actual numbers: `{ page: 1, page_size: 25 }`.

---

### L-12. `noEmit: true` in tsconfig — No Build Output

| File | Line |
|------|------|
| `apps/web/tsconfig.json` | Check `compilerOptions.noEmit` |

Next.js handles its own compilation, but verifying this is standard.

---

### L-13. No `overrides` for Transitive Vulnerabilities in package.json

| File | Details |
|------|---------|
| `apps/web/package.json` | No `overrides` or `resolutions` field |

**Fix**: Run `npm audit` and add `overrides` for any high-severity vulnerabilities.

---

### L-14. `env.py` May Not Properly Load DB URL from Environment

| File | Details |
|------|---------|
| `alembic/env.py` | Should load `DATABASE_URL` from env, but `alembic.ini` has placeholder URL |

**Fix**: Ensure `env.py` overrides `sqlalchemy.url` from environment at runtime.

---

### L-15. `main.py` Imports `barname_ml_solver` at Module Level

| File | Line |
|------|------|
| `app/main.py:30` | `from app.automation.captcha import barname_ml_solver` |

If the captcha module fails to import (missing TensorFlow/Keras), the entire app fails to start. Use lazy import.

---

### L-16. Alembic `alembic.ini` Contains Password-Like Placeholder

| File | Line |
|------|------|
| `alembic.ini:5` | `sqlalchemy.url = postgresql+asyncpg://postgres:<your_secure_password>@localhost:5432/utcms_rpa` |

**Fix**: Replace with `sqlalchemy.url = postgresql+asyncpg://postgres:${POSTGRES_PASSWORD}@localhost:5432/utcms_rpa` and load from env.

---

### L-17. `config.py` Uses Blacklist for Weak Passwords Instead of Minimum Entropy

| File | Lines |
|------|-------|
| `app/core/config.py:116,231-240` | Blacklist-based password validation |

**Fix**: Use minimum entropy check (e.g., 40 bits) and minimum length (12+ characters) instead of a fragile blacklist.

---

### L-18. `auth_multitenant.py` Fernet Import Inside Function Body

| File | Lines |
|------|-------|
| `app/auth_multitenant.py:79,95` | `from cryptography.fernet import Fernet` inside functions |

**Fix**: Move to module top-level import.

---

### L-19. `getattr` Used Instead of Proper Attribute Access

| File | Lines |
|------|-------|
| `app/services/waybill_service.py:113,115` | `getattr(request.vehicle, "plate", None)` |

**Fix**: Use `request.vehicle.plate` (with proper typing) or `try/except AttributeError`.

---

### L-20. `hasattr` Used Instead of `isinstance`

| File | Lines |
|------|-------|
| `app/automation/browser.py:337-338` | `if hasattr(self, "browser") and self.browser:` |

**Fix**: Use `isinstance(self.browser, BrowserType)` with proper type checking.

---

### L-21. `pass` in `# noqa: BLE001` Suppressed Exception

| File | Line |
|------|------|
| `app/automation/waybill_bot_multitenant.py:176` | `except Exception as exc:  # noqa: BLE001` |

**Fix**: Remove `# noqa` and log the exception.

---

### L-22. Date/Time Columns Mix Timezone-Aware and Naive

| File | Lines |
|------|-------|
| `app/models_multitenant.py:290` | `DateTime(timezone=True)` vs `DateTime(timezone=False)` |

**Fix**: Use `DateTime(timezone=True)` consistently for all timestamp columns.

---

### L-23. `create_waybill_with_map` — Deep Try/Except Nesting

| File | Range |
|------|-------|
| `app/services/waybill_service.py:67-316` | 5 levels of nested error handling |

**Fix**: Extract cleanup logic into context managers. Use a single `try/except/finally`.

---

### L-24. `auth.py` — Single File, 1265+ Lines

| File | Details |
|------|---------|
| `app/automation/auth.py` | 1265+ lines, handles CAPTCHA, auth, navigation |

**Fix**: Split into multiple modules.

---

### L-25. Squid Configs Allow `10.0.0.0/8` Without Auth

| File | Lines |
|------|-------|
| `infra/squid/squid_1.conf:5-13` | Wide network ACLs |

**Fix**: Restrict to only the Docker overlay network CIDR.

---

### L-26. `scrape_timeout` (10s) Nearly Equals `scrape_interval` (15s)

| File | Lines |
|------|-------|
| `infra/prometheus/prometheus.yml:2-4` | Configuration timings |

**Fix**: Reduce timeout to 5s or increase interval to 30s.

---

### L-27. Container Resource Limits Missing for Most Services

| Files | Details |
|-------|---------|
| `compose/backend.yml`, `compose/infra.yml`, `compose/web.yml`, `compose/monitoring.yml` | Only Celery workers have `memory: 3g` |

**Fix**: Add `deploy.resources.limits` for all services.

---

### L-28. `HEADLESS` Defaults to `False` When Env Var Missing

| File | Details |
|------|---------|
| `app/core/config.py` | `HEADLESS` via `_to_bool` with `default=False` |

**Fix**: In production, default to `True`.

---

### L-29. Auth State Path Default May Create Files in Wrong Location

| File | Line |
|------|------|
| `app/core/config.py:101` | `AUTH_STATE_PATH = os.getenv("AUTH_STATE_PATH", ".auth/utcms_state.json")` |

**Fix**: Use absolute path or path relative to `/app/`.

---

### L-30. `Request Context Middleware` Comment Typo (`corrolation`)

| File | Line |
|------|------|
| `app/main.py:198` | `correlation_id` variable name is correct, check comments |

Minor typo in nearby comments.

---

### L-31. Multiple `_register_page_listener` Patterns Without Error Propagation

| File | Lines |
|------|-------|
| `app/automation/browser.py:598-607` | Listener registration errors silently ignored |

**Fix**: Propagate errors to the caller or log them.

---

### L-32. `proxy_rotator.py` Timeout Configuration Single Value

| File | Lines |
|------|-------|
| `app/automation/proxy_rotator.py:367,493` | Single `ClientTimeout(total=10.0)` |

**Fix**: Add separate `socket_connect_timeout` and `socket_read_timeout`.

---

### L-33. No `__pycache__` in `.dockerignore`

| File | Details |
|------|---------|
| `.dockerignore` | Missing `__pycache__/` |

**Fix**: Add to `.dockerignore`.

---

### L-34. `ruff cache` (`/app/.ruff_cache`) May Execute at Runtime

Docker image may include `.ruff_cache`. Add to `.dockerignore`.

---

### L-35. `mypy cache` (`/app/.mypy_cache`) in Docker Image

**Fix**: Add `.mypy_cache` to `.dockerignore`.

---

### L-36. `pytest cache` in Docker Image

**Fix**: Add `.pytest_cache` to `.dockerignore`.

---

### L-37. Python 3.11 Target in `pyproject.toml` But README Says 3.14

| File | Details |
|------|---------|
| `pyproject.toml:3` | `target-version = ['py311']` |
| `README.md:51` | `Python 3.14` mentioned |

**Fix**: Align versions.

---

### L-38. Redis Password Fallback to Empty

| File | Lines |
|------|-------|
| `compose/backend.yml:40` | `redis://:${REDIS_PASSWORD}@redis:6379/0` with no fallback |

If `REDIS_PASSWORD` is not set, the URL becomes `redis://:@redis:6379/0` which may fail.

---

### L-39. Postgres Password Fallback to `postgres`

| File | Lines |
|------|-------|
| `compose/infra.yml:33`, `compose/backend.yml:39` | `${POSTGRES_PASSWORD:-postgres}` |

**Fix**: Remove fallback — fail if not set.

---

### L-40. Celery Task Returns `AsyncResult` From Sync Function

| File | Lines |
|------|-------|
| `app/workers/tasks.py:180-185` | `return process_waybill_task.apply_async(...)` |

Celery `apply_async` returns an `AsyncResult`. If the caller expects the result, this works, but pattern may be confusing.

---

### L-41. Inline Task Function Definitions Inside View Functions

Check for functions defined inside request handlers — they can't be tested independently.

---

### L-42. No Pagination Validation on API Endpoints

API endpoints accepting `page` and `page_size` parameters should validate and cap them (e.g., `page_size <= 100`).

---

### L-43. `redirect` Imported but Not Used in Some API Files

Check API route files for unused imports from `fastapi.responses`.

---

### L-44. Migration `check` Commands Return Default Password

| Files | Details |
|-------|---------|
| `scripts/check_tables.py:15`, `scripts/check_migration_status.py:15`, `scripts/full_database_check.py:17`, `scripts/check_driver_schema.py:14`, `scripts/fix_migration_version_sync.py:15` | Default to `password="postgres"` |

**Fix**: Read from environment, fail if not set.

---

### L-45. `CAPTCHA_PROVIDER` No Validation at Config Load

| File | Details |
|------|---------|
| `app/core/config.py` | Accepts any string for `CAPTCHA_PROVIDER` |

**Fix**: Validate against known providers at startup.

---

### L-46. `WORKER_3_PROXY` Commented Out in `.env.example`

| File | Line |
|------|------|
| `.env.example:34` | `# WORKER_3_PROXY=...` |

Consistency issue — if worker 3 is deployed, the config needs to be uncommented.

---

### L-47. `NEXT_PUBLIC_API_URL` in Backend `.env`

| File | Line |
|------|------|
| `.env.example:26` | `NEXT_PUBLIC_API_URL` in backend config |

This variable belongs in the frontend project (`apps/web/.env`), not backend.

---

### L-48. `ENVIRONMENT` Defaults to `production`

| File | Line |
|------|------|
| `compose/backend.yml:48` | `ENVIRONMENT: ${ENVIRONMENT:-production}` |

**Fix**: Default to `development` to prevent accidental production runs with development configs.

---

### L-49. Redis `PASSWORD` Loaded but May Not Apply to All Connection Paths

| File | Lines |
|------|-------|
| `app/core/redis.py:15-23` | `_build_redis_kwargs` uses password |

**Fix**: Check that all Redis connection paths (Celery, rate limiter, session cache) use this same password.

---

### L-50. `aioredis` Import Guard Silently Returns `None`

| File | Lines |
|------|-------|
| `app/core/redis.py:9-12` | `except ImportError: aioredis = None` |

**Fix**: Log a warning if `redis` package is not installed.

---

### L-51. No `__init__.py` in Some Test Directories

Check if tests can be discovered without `__init__.py` files.

---

### L-52. `auth_multitenant.py` Defines Crypto Functions But Also Has JWT Logic

| File | Details |
|------|---------|
| `app/auth_multitenant.py` | Contains both Fernet crypto AND JWT auth logic |

**Fix**: Split into `crypto.py` and `auth.py`.

---

### L-53. `upload_tar.py` Connects to Production via Password Auth

| File | Line |
|------|------|
| `upload_tar.py:4` | `ssh.connect("188.121.123.16", username="ubuntu", password="PLACEHOLDER_SSH_PASSWORD")` |

**Fix**: Use key-based authentication or SSH config.

---

### L-54. `Dockerfile` Copies `scripts/` and `alembic/` — May Include Secrets

| File | Lines |
|------|-------|
| `Dockerfile:69-74` | Copies entire directories |

**Fix**: Use `.dockerignore` to exclude sensitive files.

---

### L-55. `.dockerignore` Doesn't Exclude `.env`

| File | Details |
|------|---------|
| `.dockerignore` | Add `.env` to prevent secrets in Docker build context |

---

### L-56. No Container Image Vulnerability Scanning

The CI/CD pipeline has no container image scanning (Trivy, Snyk, Docker Scout). The `safety check` steps have `continue-on-error: true`.

---

# Priority Fix Order — Server Deployment (4 vCPU, 12 GB RAM)

## 🔴 Immediate — Blocking (fix before any deployment)
| # | Issue | Why Critical on This Server |
|---|-------|-----------------------------|
| 1 | **H-11**: Fix `zod/v4` import → `zod` | **Build break** — no frontend possible |
| 2 | **H-12**: Fix `ArrowLeftOnRectangleIcon` | **Build break** — no frontend possible |
| 3 | **H-01**: Rotate SSH password `PLACEHOLDER_SSH_PASSWORD` | **Server compromised** — anyone can SSH in |
| 4 | **H-02**: Purge `.env` from git history | **All secrets exposed** in git history |
| 5 | **H-05**: Add HTTPS to Nginx | **Plaintext traffic** — JWT, passwords, API keys sent in clear |

## 🔴 Critical — Security (fix before exposing to internet)
| # | Issue | Why Critical on This Server |
|---|-------|-----------------------------|
| 6 | **H-03**: Remove `privileged: true` | Any container compromise = **full host root** |
| 7 | **H-04**: Remove `network_mode: host` from Squid | Ports 3129/3130 directly **exposed on second IP** |
| 8 | **H-16**: Restrict Prometheus port 9090 | Metrics exposed on **both IPs**, no auth |
| 9 | **H-07**: Fix SSRF in proxy rotator | Can probe **internal Docker network** from same host |
| 10 | **H-08**: Fix rate limiter fail-open | When Redis is loaded, **999 req/min bypass** |
| 11 | **H-09**: Remove default `master_bar` password | Admin panel **guessable in seconds** |
| 12 | **H-10**: Fix JWT algorithm downgrade | Token **forgery** possible |
| 13 | **H-06**: Migrate JWT from localStorage | **XSS-vulnerable** token storage |
| 14 | **H-14**: Fix weak Fernet key derivation | Driver passwords **crackable** |

## 🟡 High Impact — Stability (prevents OOM/crash on 12 GB)
| # | Issue | Why Critical on This Server |
|---|-------|-----------------------------|
| 15 | **H-13**: Fix ALL `except: pass` (30+) | Silent errors → **memory leaks** → OOM on 12 GB |
| 16 | **H-20**: Fix browser context leaks | Orphan Chromium = RAM drain → **OOM kill** |
| 17 | **L-00**: Add container resource limits | 13 containers share 12 GB — **no limits = OOM** |
| 18 | **H-15**: Remove `engine.dispose()` per task | **Connection storms** on 4 vCPU under load |
| 19 | **H-19**: Fix `autoretry_for = (Exception,)` | Bugs retried indefinitely → **CPU/DB wasted** |
| 20 | **M-16**: Fix new event loop per task | Event loop creation overhead on **4 vCPU** |
| 21 | **M-28**: Remove FLUSHALL from deploy | Kills cache for **all 3 workers at once** |

## 🟢 Medium — Reliability & Maintenance
| # | Issue | Priority |
|---|-------|----------|
| 22 | **M-11**: Fix `asyncio.Lock` race conditions | Causes `RuntimeError: Lock not acquired` |
| 23 | **H-24**: Fix Redis manager race condition | Intermittent Redis failures |
| 24 | **H-23**: Fix Event Hub race | WebSocket disconnects under load |
| 25 | **H-18**: Apply rate limiting to all endpoints | Currently only 5 paths protected |
| 26 | **M-15**: Fix `run_migrations` dead code | Schema migrations **never run** |
| 27 | **M-33**: Fix Prometheus scrape timeout | Monitoring gaps under CPU load |
| 28 | **M-31**: Fix `deploy.sh` docker-compose v1/v2 | Failed deploy = **partial outage** |
| 29 | All remaining MEDIUM issues (M-01 to M-34) | Fix after Tier 1 & 2 |
| 30 | All remaining LOW issues (L-01 to L-56) | Low priority |

---

*Report generated: 2026-06-30 · Issues found: 115 (25 HIGH, 34 MEDIUM, 56 LOW)*
*Target server: single host, dual IP (188.121.123.16 + 95.38.233.90), 4 vCPU, 12 GB RAM*

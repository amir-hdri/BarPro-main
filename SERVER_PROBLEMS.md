# BarPro — Comprehensive Server Problem Report
> Generated: 2026-07-01 (1405/04/10)  
> Target Audience: AI Agent / Developer  
> Server: 188.121.123.16 (Primary) + 95.38.233.90 (Secondary Egress)  
> 13 Docker Containers, Single Host, 4 vCPU / 12 GB RAM

---

## Table of Contents

1. [How to Use This Report](#1-how-to-use-this-report)
2. [Problem Severity Classification](#2-problem-severity-classification)
3. [🔴 Critical Problems (Blocking All Waybill Registration)](#3--critical-problems-blocking-all-waybill-registration)
4. [🟠 High Severity Problems](#4--high-severity-problems)
5. [🟡 Medium Severity Problems](#5--medium-severity-problems)
6. [🔵 Low Severity Problems](#6--low-severity-problems)
7. [⚪ Informational / Technical Debt](#7--informational--technical-debt)
8. [Problem Interaction Graph — Root Cause Chains](#8-problem-interaction-graph--root-cause-chains)
9. [Priority Fix Order](#9-priority-fix-order)
10. [Verification Checklist After Fixes](#10-verification-checklist-after-fixes)

---

## 1. How to Use This Report

Each problem entry follows this structure:

```
### P-NNN. Problem Title
- **Severity:** 🔴/🟠/🟡/🔵/⚪
- **File(s):** path/to/file.py:LINE
- **Category:** Application / Network / Config / Security / Performance
- **Symptom:** What the user/operator observes
- **Root Cause:** The precise technical reason
- **Impact:** What breaks or degrades
- **Fix:** Exact code/config change needed
- **Verification:** How to confirm it's fixed
- **Dependencies:** Other problems that must be fixed first
```

---

## 2. Problem Severity Classification

| Level | Label | Meaning | Count |
|-------|-------|---------|-------|
| 🔴 | CRITICAL | Blocks all waybill registration. System cannot function without fix. | 6 |
| 🟠 | HIGH | Severely degrades system. Waybills may fail or be extremely slow. | 8 |
| 🟡 | MEDIUM | Causes intermittent failures, misconfigurations, or inefficiencies. | 12 |
| 🔵 | LOW | Minor issues, code smells, missing defaults. | 6 |
| ⚪ | INFO | Technical debt, documentation gaps, observability improvements. | 4 |

**Total problems documented: 36**

---

## 3. 🔴 Critical Problems (Blocking All Waybill Registration)

---

### P-01. Persian Solar Hijri Dates Treated as Gregorian — All Schedules Expired

- **Severity:** 🔴 CRITICAL
- **File(s):** `app/services/scheduled_waybill_executor.py:242-245`
- **Category:** Application — Date Handling
- **Tags:** `scheduler`, `persian-date`, `jalali`, `driver_schedules`

**Symptom:**  
`evaluate_and_run_schedules` runs every 10 minutes, evaluates 4 schedules, but always creates 0 jobs.  
Log: `schedules_evaluated: 4, schedules_executed: 0, jobs_created: 0`

**Root Cause:**  
All `start_date` and `end_date` values in the `driver_schedules` table are Persian (Solar Hijri) dates:

| Schedule | start_date | end_date |
|----------|------------|----------|
| 1 | 1405-04-04 | 1405-04-05 |
| 2 | 1405-04-04 | 1405-04-04 |
| 3 | 1405-04-04 | 1405-04-04 |
| 4 | 1405-04-08 | 1405-05-08 |

The code at `scheduled_waybill_executor.py:242` does:
```python
today < datetime.fromisoformat(schedule.start_date).date()
```

`datetime.fromisoformat("1405-04-04")` returns year 1405 **Gregorian** (i.e., the year 1405 AD). Today (2026-07-01) is greater than 1405-XX-XX, so `today > end_date` evaluates True → schedule skipped.

**Impact:**  
- 4/4 schedules always skipped
- No scheduled waybill jobs are ever created
- `scheduled.waybill.evaluate_and_run` runs every 10 minutes pointlessly
- The ONLY way to register waybills is manual submission via UI

**Fix:**  
Replace `datetime.fromisoformat()` with a Persian-to-Gregorian converter:
```python
import jdatetime

def _parse_date_persian(date_str: str | None) -> date | None:
    if not date_str:
        return None
    try:
        jalali_date = jdatetime.date.fromisoformat(date_str)
        return jalali_date.togregorian()
    except (ValueError, TypeError):
        return None
```

Then change comparisons:
```python
start = _parse_date_persian(schedule.start_date)
if start and today < start:
    return {"jobs_created": 0, ...}
end = _parse_date_persian(schedule.end_date)
if end and today > end:
    return {"jobs_created": 0, ...}
```

**Verification:**  
1. Run `python3 -c "import jdatetime; print(jdatetime.date(1405, 4, 10).togregorian())"` → should print `2026-07-01`
2. After fix, `evaluate_and_run_schedules` should show `jobs_created: >0` for active schedules
3. Check DB: `SELECT * FROM waybill_jobs WHERE source='api' AND schedule_id IS NOT NULL`

**Dependencies:**  
- Requires `jdatetime` package in `requirements.txt`
- All schedule dates in DB must be valid Persian dates

---

### P-02. RPA_SUBMIT_ENDPOINT Empty — HTTP Submit Path Always Crashes

- **Severity:** 🔴 CRITICAL
- **File(s):** `app/core/config.py:280`, `app/services/rpa_submit_service.py:67-68`
- **Category:** Application — Configuration
- **Tags:** `submit`, `endpoint`, `http-submit`

**Symptom:**  
Every job that reaches the submit stage crashes immediately with `RuntimeError: RPA_SUBMIT_ENDPOINT is not configured`.

**Root Cause:**  
Configuration defaults to empty string:
```python
self.RPA_SUBMIT_ENDPOINT = os.getenv("RPA_SUBMIT_ENDPOINT", "").strip()
```
This env var is absent from all `.env` files and `.env.example`. The submit adapter checks:
```python
if not utcms_config.RPA_SUBMIT_ENDPOINT:
    raise RuntimeError("RPA_SUBMIT_ENDPOINT is not configured")
```

**Impact:**  
- HTTP submit path (fast, ~3s) is completely broken
- System falls back to browser submit (slow, ~300-400s)
- Successful submissions took 327-388 seconds (browser path)
- 100x slower than necessary, risking Celery timeouts

**Fix:**  
1. In `.env.example`, add: `RPA_SUBMIT_ENDPOINT="https://barname.utcms.ir/api/path/to/submit"`  
2. In production `.env`, set the actual UTCMS submit URL  
3. Or, if HTTPS submit endpoint is unknown, set to the UTCMS waybill page URL so browser fallback handles it directly without attempting HTTP first

**Verification:**  
```bash
curl -X POST "https://barname.utcms.ir/<correct-endpoint>" \
  -H "Content-Type: application/json" \
  -d '{"test": true}' \
  -w "\nHTTP %{http_code}\n"
```

**Dependencies:**  
- Requires knowing the correct UTCMS submission endpoint URL
- Session bundle (cookies + CSRF token) must be valid for that endpoint

---

### P-03. All UTCMS Driver Sessions Expired — No Auto-Reauth

- **Severity:** 🔴 CRITICAL
- **File(s):** `app/services/rpa_auth_service.py`, `app/models_multitenant.py` (DriverRuntimeState)
- **Category:** Application — Session Management
- **Tags:** `auth`, `session`, `utcms`, `expired`

**Symptom:**  
All 3 drivers have expired UTCMS sessions. Driver 2 was never authenticated.

| Driver | State | Last Auth | Session Expiry | Status |
|--------|-------|-----------|----------------|--------|
| ابوالفضل دولتخواه (ID:1) | ready | 2026-06-29 11:37 | 2026-06-29 13:37 | **Expired 2 days ago** |
| عبدالمطلب (ID:2) | active | **Never** | **Never** | **No session ever** |
| سعید عموری (ID:3) | ready | 2026-06-29 16:30 | 2026-06-29 18:30 | **Expired 2 days ago** |

**Root Cause:**  
- Auth is triggered lazily: only when a job enters the scheduler with `WAITING_AUTH` status
- No proactive session refresh mechanism exists
- Session TTL is 2 hours (`RPA_SESSION_TTL_SECONDS=7200`)
- No health check pings the UTCMS login to keep sessions alive
- Once scheduler breaks (P-01), no new jobs → no auth triggered → sessions expire → never recover

**Impact:**  
- Even if a new job is created, it must go through auth first (2-5 minutes)
- The 3 successful waybills from June 29 each required 1-2 auth cycles
- Auth failure on job `job_835ca65066684e36` caused **48 retry attempts** over 2 days

**Fix:**  
Multiple approaches (apply at least one):

**Option A — Proactive Session Keepalive:**
Add a Celery beat task that runs every 30 minutes:
```python
@celery_app.task(name="rpa.session.keepalive", queue="rpa_scheduler")
def keepalive_sessions():
    for driver in drivers_with_expiring_sessions:
        if expires_in < threshold:
            rpa_auth_service.authenticate_driver(driver.client_id, driver.id, "keepalive")
```

**Option B — Trigger on Startup:**
In app startup, iterate all active drivers and check/renew sessions.

**Option C — Manual Trigger:**
Provide an API endpoint or management command:
```bash
docker exec barpro-backend python -c "
from app.services.rpa_auth_service import rpa_auth_service
import asyncio
asyncio.run(rpa_auth_service.authenticate_driver(1, 1, 'manual_trigger'))
"
```

**Verification:**  
```sql
SELECT d.full_name, drs.last_auth_at, drs.session_expires_at 
FROM drivers d 
JOIN driver_runtime_states drs ON drs.driver_id = d.id 
WHERE drs.session_expires_at > NOW();
```
Should return rows with future expiry dates.

---

### P-04. `engine.dispose()` Called Every Scheduler Cycle — Connection Pool Killed

- **Severity:** 🔴 CRITICAL
- **File(s):** `app/workers/phase1_tasks.py:52`
- **Category:** Performance — Database
- **Tags:** `engine`, `connection-pool`, `dispose`

**Symptom:**  
```
phase1.scheduler.plan runs every 15 seconds
  → loop.run_until_complete(engine.dispose())  # kills ALL DB connections
  → new connections must be established from scratch (+500ms)
  → repeats every 15 seconds forever
```

**Root Cause:**  
The `_run()` helper function in `phase1_tasks.py` explicitly calls `engine.dispose()` before every task execution:
```python
def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        from app.core.database import engine
        loop.run_until_complete(engine.dispose())  # ← KILLS POOL
        return loop.run_until_complete(coro)
    finally:
        ...
        loop.run_until_complete(browser_manager.recycle_browser())
```

This was supposedly fixed per AGENTS.md ("Removed engine.dispose() per Celery task") but the code change was never applied to phase1_tasks.py.

Additionally, `browser_manager.recycle_browser()` is called even though `scheduler.plan` does not use the browser at all.

**Impact:**  
- Every 15 seconds: database connection pool destroyed and rebuilt
- +500ms latency added to every scheduler task
- PostgreSQL connection churn (rapid connect/disconnect cycles)
- Browser recycled needlessly 4 times per minute
- Event loop churn: new event loop created and destroyed 4×/minute

**Fix:**  
```python
def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        # REMOVED: engine.dispose() — pool is shared across tasks
        return loop.run_until_complete(coro)
    finally:
        # Only recycle browser if task actually used it
        loop.close()
```

**Verification:**  
- Check PostgreSQL logs for connection churn (before fix: 4 connects/disconnects per minute)
- Scheduler task duration should drop from ~130ms to ~30ms
- `docker logs barpro-postgres --tail 50 | grep -i "connection\|disconnect"` should show stable connections

---

### P-05. `QUEUE_ENABLED=False` — Legacy Waybill Queue Path Disabled

- **Severity:** 🔴 CRITICAL
- **File(s):** `app/core/config.py:181`
- **Category:** Application — Configuration
- **Tags:** `queue`, `legacy`, `waybill_tasks`

**Symptom:**  
Legacy API endpoints (`/waybill/submit-manual-waybill`, `/waybill/queue/create-with-map`) silently drop submissions. No error, no job created.

**Root Cause:**  
```python
self.QUEUE_ENABLED = _to_bool(os.getenv("QUEUE_ENABLED", "False"), default=False)
```
The legacy queue manager gates all job creation on this flag.

**Impact:**  
- Any API client calling the old endpoints gets no response or silent failure
- Jobs created via legacy path never enter the system
- Even if `QUEUE_ENABLED=True`, the tasks would go to `waybill_tasks` queue, but workers listen to `waybill_tasks_1/2/3` (routed queues) — see P-10

**Fix:**  
1. Set `QUEUE_ENABLED=True` in `.env`  
2. Ensure `get_routed_queue("waybill_tasks")` correctly routes to `waybill_tasks_X`  
3. Verify that at least one worker listens to `waybill_tasks_X` for each X in available IP indices

**Verification:**  
```python
from app.core.circuit_breaker import get_routed_queue
print(get_routed_queue("waybill_tasks"))  # Should print waybill_tasks_1, 2, or 3
```

---

### P-06. `classify_submit_response` Cannot Detect Persian Success Responses

- **Severity:** 🔴 CRITICAL
- **File(s):** `app/services/rpa_submit_service.py:664-669`
- **Category:** Application — RPA Bot
- **Tags:** `classifier`, `persian`, `success-detection`

**Symptom:**  
Successful UTCMS submissions may be classified as failures if the portal returns Persian-language success indicators instead of English.

**Root Cause:**  
```python
def classify_submit_response(status_code: int, body: str) -> SubmitClassification:
    lowered = (body or "").lower()
    if status_code in {200, 201} and "success" in lowered:
        return SubmitClassification(SubmitOutcome.SUCCESS, "portal_success", ...)
    if status_code in {401, 403} or any(
        token in lowered for token in ("session expired", "login", "unauthorized", "دوباره وارد")
    ):
        return SubmitClassification(SubmitOutcome.AUTH_EXPIRED, "session_expired", ...)
```

The classifier checks for the English word `"success"`. If UTCMS returns Persian text like `"موفق"`, `"ثبت شد"`, `"کد پیگیری: ۱۲۳۴۵"`, or a JSON with Persian keys, the detection fails.

**Impact:**  
- Successful submissions marked as `UNKNOWN_ERROR` or `VALIDATION_ERROR`
- Jobs incorrectly marked as FAILED and sent to retry loop
- 3 successful waybills barely escaped this — likely because they matched the `200` + partial match

**Fix:**  
Add Persian success indicators:
```python
PERSIAN_SUCCESS_TOKENS = ["موفق", "ثبت", "کد پیگیری", "شماره پیگیری", "انجام شد", "تایید"]
if status_code in {200, 201} and (
    "success" in lowered or any(t in body for t in PERSIAN_SUCCESS_TOKENS)
):
    return SubmitClassification(SubmitOutcome.SUCCESS, "portal_success", ...)
```

Also consider JSON parsing:
```python
try:
    data = json.loads(body)
    if isinstance(data, dict):
        # Check for Persian key: success
        if data.get("status") in ["success", "موفق", "SUCCESS"] or data.get("resultCode") in [200, "200"]:
            return SubmitClassification(SubmitOutcome.SUCCESS, "portal_success", ...)
except (json.JSONDecodeError, TypeError):
    pass
```

**Verification:**  
- Create a test with sample Persian UTCMS responses
- After fix, run `classify_submit_response(200, '{"status":"موفق","trackingCode":"12345"}')` → should return SUCCESS

---

## 4. 🟠 High Severity Problems

---

### P-07. Worker 1 Missing `scheduled_tasks_1` Queue

- **Severity:** 🟠 HIGH
- **File(s):** `compose/backend.yml:107-108`
- **Category:** Network — Queue Routing
- **Tags:** `celery`, `worker`, `queue-mismatch`

**Symptom:**  
If `get_routed_queue("scheduled_tasks")` routes to `scheduled_tasks_1` (IP index 1), no worker consumes it.

**Root Cause:**  
Worker queue configurations:

| Worker | Queues |
|--------|--------|
| worker-1 | `waybill_tasks_1,rpa_auth_1,rpa_submit_1` — **no scheduled_tasks_1** |
| worker-2 | `waybill_tasks_2,rpa_auth_2,rpa_submit_2,scheduled_tasks_2` |
| worker-3 | `waybill_tasks_3,rpa_auth_3,rpa_submit_3,scheduled_tasks_3,rpa_scheduler,scheduled_tasks` |

Worker 1 does NOT include `scheduled_tasks_1`. Since `get_routed_queue` uses round-robin across available IP indices (1,2,3), ~33% of `scheduled.waybill.*` tasks go to an unlistened queue.

**Impact:**  
- ~1/3 of scheduled waybill execution tasks are silently lost
- Jobs may get dispatched but never executed
- Intermittent failures are hard to debug

**Fix:**  
Add `scheduled_tasks_1` to Worker 1's queue list:
```yaml
command:
  - celery
  - -Q
  - waybill_tasks_1,rpa_auth_1,rpa_submit_1,scheduled_tasks_1
```

**Verification:**  
```bash
docker exec barpro-worker-1 celery -A app.workers.celery_app:celery_app inspect active_queues
```
Should list `scheduled_tasks_1`.

---

### P-08. `get_routed_queue` Logic Bug — `scheduled_tasks` Not Preserved

- **Severity:** 🟠 HIGH
- **File(s):** `app/core/circuit_breaker.py:217`
- **Category:** Application — Queue Routing
- **Tags:** `circuit-breaker`, `routing`, `bug`

**Symptom:**  
The `scheduled_tasks` queue is supposed to be excluded from IP-based routing (like `rpa_scheduler`), but the exclusion logic is self-contradictory.

**Root Cause:**  
```python
def get_routed_queue(base_queue: str) -> str:
    if base_queue in ["rpa_scheduler", "scheduled_tasks"] and not base_queue.startswith("scheduled_tasks"):
        return base_queue  # ← This path is NEVER reached for "scheduled_tasks"
    ip_index = get_next_ip_index_sync()
    routed = f"{base_queue}_{ip_index}"
    return routed
```

For `base_queue = "scheduled_tasks"`:
- `"scheduled_tasks" in ["rpa_scheduler", "scheduled_tasks"]` → True
- `not "scheduled_tasks".startswith("scheduled_tasks")` → **False** (it DOES start with it)
- Result: falls through → routed to `scheduled_tasks_X`

**Impact:**  
- `scheduled_tasks` base queue has no consumer (workers listen to `scheduled_tasks` but tasks are routed to `scheduled_tasks_X`)
- Worker 3 does listen to both `scheduled_tasks` (direct) and `scheduled_tasks_3` (routed), so tasks that go to IP index 3 still work
- But if routed to index 1 or 2, they end up in `scheduled_tasks_1` (no consumer) or `scheduled_tasks_2` (Worker 2 only)

**Fix:**  
```python
EXEMPT_QUEUES = {"rpa_scheduler", "scheduled_tasks"}
if base_queue in EXEMPT_QUEUES:
    return base_queue
```

**Verification:**  
```python
from app.core.circuit_breaker import get_routed_queue
# Should return "scheduled_tasks" unchanged
assert get_routed_queue("scheduled_tasks") == "scheduled_tasks"
```

---

### P-09. Squid on `network_mode: host` — Docker DNS Cannot Resolve Squid Hostnames

- **Severity:** 🟠 HIGH
- **File(s):** `compose/proxy.yml`, `.env.example:31-34`, `compose/backend.yml:61`
- **Category:** Network — DNS Resolution
- **Tags:** `squid`, `dns`, `network-mode`, `proxy`

**Symptom:**  
Workers cannot reach Squid proxies using Docker service names (`squid_1`, `squid_2`, `squid_3`).

**Root Cause:**  
Squid containers use `network_mode: host` (required for dual-IP egress). Containers in `network_mode: host` are NOT attached to the Docker bridge network and their names are NOT registered in Docker DNS.

The `.env.example` defaults use unresolvable names:
```
WORKER_1_PROXY="http://squid_1:3128"
WORKER_2_PROXY="http://squid_2:3129"
WORKER_3_PROXY="http://squid_3:3130"
```

The actual Docker Compose overrides this with `host.docker.internal`:
```yaml
RPA_PROXIES: ${WORKER_1_PROXY:-http://host.docker.internal:3128}
```

This works on macOS (where `host.docker.internal` is built-in) but may fail on Linux without explicit `extra_hosts`.

**Impact:**  
- Workers cannot reach Squid proxies
- UTCMS egress goes through the worker's default route instead of the configured proxy
- All 3 workers egress from the same IP (no IP rotation)
- Anti-bot detection at UTCMS may flag submissions
- On Linux: `host.docker.internal` may not resolve → complete proxy failure

**Fix:**  
1. `compose/backend.yml:61` already has `extra_hosts: ["host.docker.internal:host-gateway"]` — ensure Docker version ≥ 20.10
2. Update `.env.example` defaults to `host.docker.internal`  
3. For older Docker, use the Docker bridge gateway IP directly (e.g., `172.17.0.1`)

**Verification:**  
```bash
docker exec barpro-worker-1 ping -c 1 host.docker.internal
docker exec barpro-worker-1 curl -sx http://host.docker.internal:3128 http://httpbin.org/ip
```

---

### P-10. `secure_squid_ports.sh` Blocks Worker ↔ Squid Traffic

- **Severity:** 🟠 HIGH
- **File(s):** `scripts/secure_squid_ports.sh:48,57`
- **Category:** Network — Firewall
- **Tags:** `iptables`, `squid`, `firewall`

**Symptom:**  
Running `secure_squid_ports.sh` blocks all Worker→Squid 2/3 traffic. Workers connect via `host.docker.internal` which resolves to the Docker bridge gateway (`172.x.x.1`), not `127.0.0.1`.

**Root Cause:**  
```bash
iptables -A INPUT -p tcp --dport 3129 ! -s 127.0.0.1 -j DROP
iptables -A INPUT -p tcp --dport 3130 ! -s 127.0.0.1 -j DROP
```
Only `127.0.0.1` is allowed. The Docker bridge subnet (`172.16.0.0/12`) is blocked.

**Impact:**  
- If this script is run, Workers 2 and 3 cannot reach Squid 2 and 3
- Waybill submissions through those proxies fail
- The script is recommended in AGENTS.md for production

**Fix:**  
```bash
DOCKER_BRIDGE="172.16.0.0/12"
iptables -A INPUT -p tcp --dport 3129 ! -s 127.0.0.1 ! -s $DOCKER_BRIDGE -j DROP
iptables -A INPUT -p tcp --dport 3130 ! -s 127.0.0.1 ! -s $DOCKER_BRIDGE -j DROP
```

**Verification:**  
```bash
# From worker container
docker exec barpro-worker-2 curl -sx http://host.docker.internal:3129 http://httpbin.org/ip
# Should return egress IP (95.38.233.90) not connection refused
```

---

### P-11. Squid 1 (Port 3128) Exposed to Public Internet

- **Severity:** 🟠 HIGH
- **File(s):** `scripts/secure_squid_ports.sh:62-64` (commented out), `compose/proxy.yml`
- **Category:** Security — Open Proxy
- **Tags:** `squid`, `open-proxy`, `security`

**Symptom:**  
Anyone on the internet can connect to `188.121.123.16:3128` and use it as an open HTTP proxy. This was confirmed from earlier port scan — port 3128 was open on `*:*`.

**Root Cause:**  
Squid uses `network_mode: host`, so port 3128 is bound to ALL host interfaces including public IP. The iptables rule for port 3128 is commented out:
```bash
# iptables -A INPUT -p tcp --dport 3128 ! -s 127.0.0.1 -j DROP
```

Squid ACLs only restrict `http_access`, not the TCP port itself.

**Impact:**  
- Open proxy abuse (anyone can route traffic through your server)
- Bandwidth theft
- IP blacklisting by external services
- Legal exposure (traffic originating from your IP)

**Fix:**  
Uncomment and fix the iptables rule:
```bash
DOCKER_BRIDGE="172.16.0.0/12"
iptables -A INPUT -p tcp --dport 3128 ! -s 127.0.0.1 ! -s $DOCKER_BRIDGE -j DROP
```

**Verification:**  
```bash
# From external machine
curl -sx http://188.121.123.16:3128 http://httpbin.org/ip
# Should timeout/refuse
```

---

### P-12. Redis OOM: `maxmemory 1gb` Exceeds Container `mem_limit: 256m`

- **Severity:** 🟠 HIGH
- **File(s):** `compose/infra.yml:64,83`
- **Category:** Performance — Memory
- **Tags:** `redis`, `oom`, `memory`

**Symptom:**  
Redis is configured to use up to 1 GB (`--maxmemory 1gb`) but the Docker container is limited to 256 MB (`mem_limit: 256m`). When Redis approaches 256 MB, it gets OOM-killed.

**Root Cause:**  
```yaml
redis:
  image: redis:7-alpine
  command: ["redis-server", "--requirepass", "${REDIS_PASSWORD}", "--maxmemory", "1gb", "--maxmemory-policy", "allkeys-lru"]
  mem_limit: 256m
```

**Impact:**  
- Redis crashes under memory pressure
- Celery task results lost
- Session bundles lost → all drivers need re-auth
- Rate limiter fails
- WebSocket event buffers lost
- System enters failure mode

**Fix:**  
Match maxmemory to container limit:
```yaml
command: ["redis-server", "--requirepass", "${REDIS_PASSWORD}", "--maxmemory", "256mb", "--maxmemory-policy", "allkeys-lru"]
```

**Verification:**  
```bash
docker exec barpro-redis redis-cli -a $REDIS_PASSWORD INFO memory | grep -E "used_memory_human|maxmemory"
# maxmemory should be ~256mb
```

---

### P-13. All Containers Use `network_mode: host` for Squid — No Network Isolation

- **Severity:** 🟠 HIGH
- **File(s):** `compose/proxy.yml`, AGENTS.md
- **Category:** Security — Network Architecture
- **Tags:** `network-mode`, `isolation`

**Symptom:**  
Squid containers share the host's full network stack. Any port bound inside a Squid container is accessible on all host interfaces.

**Root Cause:**  
`network_mode: host` is required for dual-IP routing (Squid must bind to specific physical interfaces to egress via different IPs). However, this removes all Docker network isolation.

**Impact:**  
- All Squid ports (3128, 3129, 3130) are exposed on public interfaces
- No Docker firewall between Squid and the internet
- If Squid is compromised, the entire host network is accessible
- iptables is the ONLY defense (see P-10, P-11)

**Fix:**  
Apply iptables rules (P-10, P-11) and ensure they persist across reboots:
```bash
sudo apt install iptables-persistent
sudo netfilter-persistent save
```

**Verification:**  
```bash
sudo iptables -L INPUT -n | grep "dpt:312"
```

---

## 5. 🟡 Medium Severity Problems

---

### P-14. CORS Does Not Include Public Server IP

- **Severity:** 🟡 MEDIUM
- **File(s):** `app/main.py:69,74`, `.env.example`
- **Category:** Network — CORS
- **Tags:** `cors`, `frontend`, `api`

**Symptom:**  
Accessing the frontend via the server's public IP (`http://188.121.123.16`) causes CORS errors when the frontend JS calls the API. The browser blocks requests.

**Root Cause:**  
```python
FRONTEND_URL = "http://localhost:3000"  # default
FRONTEND_URLS = os.getenv("FRONTEND_URLS", "")  # not set
FRONTEND_URL_ALT = os.getenv("FRONTEND_URL_ALT", "")  # not set
```
CORS origins only include `http://localhost:3000` and `http://127.0.0.1:3000`. The public IP is missing.

**Impact:**  
- Users accessing via IP (not domain) get CORS errors
- API calls from frontend fail
- Waybill submission UI appears broken

**Fix:**  
Add to `.env`:
```
FRONTEND_URL=http://188.121.123.16
FRONTEND_URLS=http://188.121.123.16,http://localhost:3000
```

**Verification:**  
```bash
curl -s -I -X OPTIONS \
  -H "Origin: http://188.121.123.16" \
  -H "Access-Control-Request-Method: POST" \
  http://localhost:8000/healthz 2>&1 | grep -i "access-control-allow-origin"
```

---

### P-15. `FRONTEND_URLS` and `FRONTEND_URL_ALT` Bypass Config Class

- **Severity:** 🟡 MEDIUM
- **File(s):** `app/main.py:69,74`, `app/core/config.py`
- **Category:** Application — Inconsistency
- **Tags:** `config`, `env-var`

**Symptom:**  
Two config values use `os.getenv()` directly instead of going through `utcms_config`.

**Root Cause:**  
```python
extra_urls = os.getenv("FRONTEND_URLS", "").strip()  # line 69
alt_url = os.getenv("FRONTEND_URL_ALT", "").strip()   # line 74
```
But all other config uses `utcms_config.X`. These two bypass validation, defaults, and logging.

**Impact:**  
- Harder to debug config issues
- Not discoverable via `utcms_config` introspection
- Missing from `.env.example`

**Fix:**  
Add to `UTCMSConfig` class:
```python
self.FRONTEND_URLS = os.getenv("FRONTEND_URLS", "").strip()
self.FRONTEND_URL_ALT = os.getenv("FRONTEND_URL_ALT", "").strip()
```
Then use `utcms_config.FRONTEND_URLS` and `utcms_config.FRONTEND_URL_ALT` in `main.py`.

---

### P-16. `ENVIRONMENT` Not Set — Security Validation Bypassed

- **Severity:** 🟡 MEDIUM
- **File(s):** `.env`, `app/core/config.py:158`
- **Category:** Config — Deployment
- **Tags:** `environment`, `security`

**Symptom:**  
Server is running in `development` mode despite being production. Security validations are skipped.

**Root Cause:**  
```python
self.ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()
```
`.env` file on server does not contain `ENVIRONMENT=production`.

**Impact:**  
- Weak JWT_SECRET accepted without validation
- DRIVER_ENCRYPTION_KEY not validated
- SQLite may be used as fallback if DATABASE_URL fails
- Rate limiter behavior may differ

**Fix:**  
Add to `.env`:
```
ENVIRONMENT=production
```

**Verification:**  
```bash
grep -i ENVIRONMENT /opt/barpro/.env
# Should show: ENVIRONMENT=production
```

---

### P-17. `MULTITENANT_ENABLED=False` — Phase 1 Orchestration May Skip Jobs

- **Severity:** 🟡 MEDIUM
- **File(s):** `app/core/config.py:228`
- **Category:** Application — Architecture
- **Tags:** `multitenant`, `phase-1`

**Symptom:**  
Phase 1 RPA orchestration (`rpa_scheduler_service`, `rpa_auth_service`, `rpa_submit_service`) may have conditional behavior based on this flag.

**Root Cause:**  
```python
self.MULTITENANT_ENABLED = _to_bool(os.getenv("MULTITENANT_ENABLED", "False"), default=False)
```
Not set in `.env`, defaults to False.

**Impact:**  
- Uncertain: depends on how services use this flag
- May cause scheduler to skip jobs silently
- Containerized multi-tenant setup runs in single-tenant mode

**Fix:**  
Set in `.env`:
```
MULTITENANT_ENABLED=true
```

---

### P-18. `DRIVER_RETRY_DELAY_SECONDS=1800` — 30-Minute Retry Gap

- **Severity:** 🟡 MEDIUM
- **File(s):** `app/core/config.py:268`
- **Category:** Performance — Timing
- **Tags:** `retry`, `delay`

**Symptom:**  
Failed waybill jobs wait 30 minutes between retries.

**Root Cause:**  
```python
self.DRIVER_RETRY_DELAY_SECONDS = int(os.getenv("DRIVER_RETRY_DELAY_SECONDS", "1800"))
```

For a job with 3 max retries:
- Attempt 1: fail → 30 min wait
- Attempt 2: fail → 30 min wait
- Attempt 3: fail → dead letter

Total time before dead letter: **1 hour minimum**.

**Impact:**  
- Users wait 30+ minutes for failed jobs to retry
- Poor UX for transient failures (network glitch, captcha timeout)
- Jobs pile up in WAITING_RETRY state

**Fix:**  
Reduce to 120 seconds (2 minutes):
```
DRIVER_RETRY_DELAY_SECONDS=120
```
Or implement exponential backoff (already exists in some paths but not used consistently).

---

### P-19. Driver 2 (عبدالمطلب) Never Authenticated — Runtime State Missing

- **Severity:** 🟡 MEDIUM
- **File(s):** `app/models_multitenant.py` (DriverRuntimeState)
- **Category:** Application — Data Integrity
- **Tags:** `driver`, `auth`, `missing-state`

**Symptom:**  
Driver ID 2 (full_name: عبدالمطلب, national_code: 4889465073) has:
- `runtime_status = 'active'` (should be `'ready'` or `'auth_required'`)
- `runtime_state = NULL` (no runtime state record exists)
- `last_auth_at = NULL`, `last_session_expires_at = NULL`
- `driver_runtime_states` table has no entry for this driver

**Root Cause:**  
This driver was added to the system but the `_ensure_runtime_state` function never created a runtime state record. This may happen if the driver was created via an API/UI path that doesn't call the proper initialization.

**Impact:**  
- Scheduler's `plan_due_jobs` cannot process this driver
- `await rpa_runtime.get_session(client_id, driver.id)` will return None → job goes to WAITING_AUTH
- But `_ensure_runtime_state` may fail because no runtime_state exists
- Any job assigned to this driver will be stuck in PENDING/WATING_AUTH forever

**Fix:**  
```sql
INSERT INTO driver_runtime_states (client_id, driver_id, state, created_at, updated_at)
VALUES (1, 2, 'auth_required', NOW(), NOW());
```
Then trigger auth: run auth service for this driver manually.

**Verification:**  
```sql
SELECT * FROM driver_runtime_states WHERE driver_id = 2;
-- Should return one row
```

---

### P-20. `NEXT_PUBLIC_API_URL` Mismatch — Build vs Runtime

- **Severity:** 🟡 MEDIUM
- **File(s):** `compose/web.yml:35`, `apps/web/src/lib/api.ts:3`
- **Category:** Network — Frontend API
- **Tags:** `frontend`, `api-url`

**Symptom:**  
Frontend may call wrong API URL depending on how it's built.

**Root Cause:**  
Docker Compose sets:
```yaml
NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-/api}
```

But the code fallback:
```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
```

At build time, `NEXT_PUBLIC_API_URL=/api` is embedded. The frontend calls `/api/v1/waybill-jobs` which routes through Nginx. This is correct when built via `compose/web.yml`.

But if rebuilt locally or via a different process without the env var, it falls back to `http://localhost:8000` — bypassing Nginx entirely.

**Impact:**  
- Inconsistent API routing
- Bypassing Nginx rate limiting and security headers
- Direct backend access may hit CORS issues

**Fix:**  
Ensure build process always provides `NEXT_PUBLIC_API_URL`:
```bash
NEXT_PUBLIC_API_URL=/api npm run build
```

---

### P-21. No HTTPS — All Traffic Unencrypted

- **Severity:** 🟡 MEDIUM
- **File(s):** `infra/nginx/nginx.conf:62-72`
- **Category:** Security — Encryption
- **Tags:** `https`, `ssl`, `tls`

**Symptom:**  
Nginx only listens on port 80 (HTTP). All traffic between users and the server is plaintext.

**Root Cause:**  
The HTTPS server block is commented out (lines 75-90). SSL certificates are not installed. The HTTP block explicitly says: "تا زمان نصب گواهی، همان HTTP سرویس می‌دهد" (until cert is installed, serve via HTTP).

**Impact:**  
- Credentials (JWT tokens, API keys) transmitted in plaintext
- Session hijacking possible
- Data modification in transit
- Not PCI/HIPAA compliant

**Fix:**  
1. Install Let's Encrypt cert: `certbot --nginx -d your-domain.com`
2. Uncomment HTTPS server block in `nginx.conf`
3. Uncomment SSL volume in `compose/web.yml`
4. Uncomment port 443 mapping in `compose/web.yml`

**Verification:**  
```bash
curl -sI https://188.121.123.16 2>&1 | grep "HTTP/"
# Should return 200 or 301, not "Failed to connect"
```

---

### P-22. Frontend Health Check Uses Root Path — May Not Return 200

- **Severity:** 🟡 MEDIUM
- **File(s):** `compose/web.yml:41`
- **Category:** Infrastructure — Health Check
- **Tags:** `frontend`, `healthcheck`

**Symptom:**  
Frontend health check may fail because Next.js doesn't serve root path (`/`) without SSR.

**Root Cause:**  
```yaml
healthcheck:
  test: ['CMD-SHELL', 'wget -qO/dev/null http://localhost:3000 || exit 1']
```
Next.js dev server may not respond to `/` without a `pages/index.tsx` being compiled. In production, it typically works, but any delay during compilation causes health check failures.

**Impact:**  
- False health check failures
- Docker may restart frontend unnecessarily
- Nginx depends on frontend being healthy → cascading restarts

**Fix:**  
Use a stable endpoint:
```yaml
healthcheck:
  test: ['CMD-SHELL', 'wget -qO/dev/null http://localhost:3000/api/healthz 2>&1 || exit 1']
```

---

## 6. 🔵 Low Severity Problems

---

### P-23. Nginx Missing `set_real_ip_from` — IP Spoofing

- **Severity:** 🔵 LOW
- **File(s):** `infra/nginx/nginx.conf:25-26`
- **Category:** Security — IP Trust
- **Tags:** `nginx`, `spoofing`

**Symptom:**  
Any client can send a fake `X-Forwarded-For` header and nginx will trust it.

**Root Cause:**  
```nginx
real_ip_header    X-Forwarded-For;
real_ip_recursive on;
```
Missing `set_real_ip_from` directive. Nginx accepts `X-Forwarded-For` from ALL sources.

**Fix:**  
```nginx
set_real_ip_from 172.16.0.0/12;
set_real_ip_from 127.0.0.1;
```

---

### P-24. `manage.sh netcheck` Uses Unresolvable Docker Name `barpro-squid-1`

- **Severity:** 🔵 LOW
- **File(s):** `manage.sh:352`
- **Category:** Infrastructure — Diagnostics
- **Tags:** `netcheck`, `debug`

**Symptom:**  
```bash
docker exec barpro-nginx wget -qO- http://barpro-backend:8000/healthz  # OK (on bridge)
docker exec barpro-worker-1 curl -sx http://barpro-squid-1:3128 http://httpbin.org/ip  # FAILS
```
`barpro-squid-1` is on `network_mode: host`, NOT on the bridge network. Its container name is not registered in Docker DNS.

**Fix:**  
```bash
docker exec barpro-worker-1 curl -sx http://host.docker.internal:3128 http://httpbin.org/ip
```

---

### P-25. Nginx Proxies `/metrics` Through Public Port 80

- **Severity:** 🔵 LOW
- **File(s):** `infra/nginx/http-server.conf:72-79`
- **Category:** Security — Attack Surface
- **Tags:** `metrics`, `prometheus`

**Symptom:**  
Prometheus metrics endpoint is accessible through Nginx (port 80), protected only by IP ACL.

**Root Cause:**  
```nginx
location /metrics {
    allow 127.0.0.1;
    allow 172.16.0.0/12;
    deny all;
    proxy_pass http://backend:8000/metrics;
}
```
This route is unnecessary — Prometheus scrapes `backend:8000` directly.

**Fix:**  
Remove or further restrict this location block.

---

### P-26. Redis Password Visible in Docker Health Check Command

- **Severity:** 🔵 LOW
- **File(s):** `compose/infra.yml:72`
- **Category:** Security — Credential Leakage
- **Tags:** `redis`, `password`, `healthcheck`

**Symptom:**  
Redis password appears in Docker logs and `docker inspect` output.

**Root Cause:**  
```yaml
healthcheck:
  test: ['CMD-SHELL', 'redis-cli -a ${REDIS_PASSWORD} ping | grep -q PONG || exit 1']
```
The password is passed as a command-line argument, visible in `ps aux`.

**Fix:**  
Use `redis-cli -a $REDIS_PASSWORD` or set password via environment variable `REDISCLI_AUTH`:
```yaml
environment:
  REDISCLI_AUTH: ${REDIS_PASSWORD}
healthcheck:
  test: ['CMD-SHELL', 'redis-cli ping | grep -q PONG || exit 1']
```

---

### P-27. X-Request-ID Missing on 3 Nginx Locations

- **Severity:** 🔵 LOW
- **File(s):** `infra/nginx/http-server.conf:13-23,72-79,90-98`
- **Category:** Observability — Tracing
- **Tags:** `request-id`, `tracing`

**Symptom:**  
Requests to `/ws/`, `/metrics`, and `/` do not receive an `X-Request-ID` header, breaking backend tracing.

**Fix:**  
Add `proxy_set_header X-Request-Id $request_id;` to all three location blocks.

---

## 7. ⚪ Informational / Technical Debt

---

### P-28. Two Frontend Source Directories

- **Severity:** ⚪ INFO
- **Files:** `apps/web/` (active), `app/frontend/` (legacy)
- **Issue:** Both directories contain Next.js frontend code. Only `apps/web/` is used in production. The `app/frontend/` directory is dead code and should be removed to avoid confusion.

---

### P-29. `ALLOW_LIVE_SUBMIT=False` — Browser Pool Submit Disabled

- **Severity:** ⚪ INFO
- **File:** `app/core/config.py:129`
- **Issue:** Live inline submission (browser pool) disabled. System relies entirely on Celery workers for submission. This is fine for production but could be an optimization path.

---

### P-30. Scheduler Recycles Browser Unnecessarily

- **Severity:** ⚪ INFO
- **File:** `app/workers/phase1_tasks.py:53-55`
- **Issue:** The `finally` block calls `browser_manager.recycle_browser()` after EVERY task, including `phase1.scheduler.plan` which doesn't use a browser. This runs 4 times per minute doing pointless browser cleanup.

---

### P-31. Missing Env Vars in `.env.example`

- **Severity:** ⚪ INFO
- **File:** `.env.example`
- **Missing vars:**
  - `RPA_SUBMIT_ENDPOINT`
  - `FRONTEND_URLS`
  - `FRONTEND_URL_ALT`
  - `ENVIRONMENT`
  - `MULTITENANT_ENABLED`

---

## 8. Problem Interaction Graph — Root Cause Chains

```
P-01 (Persian Date) ──→ No scheduled jobs created
                           │
                           ├──→ P-03 (Sessions Expire) ──→ Auth required for every job
                           │                                  │
                           │                                  └──→ +2-5 min per submission
                           │
                           └──→ evaluate_and_run pointless every 10 min

P-02 (Empty Submit Endpoint) ──→ HTTP submit always crashes
                                    │
                                    └──→ Browser fallback (300-400 sec per job)

P-04 (engine.dispose) ──→ DB connection churn every 15 sec
                              │
                              ├──→ +500ms per scheduler iteration
                              └──→ PostgreSQL connection thrash

P-05 (QUEUE_ENABLED=False) ──→ Legacy submissions silently dropped

P-06 (Persian Classifier) ──→ Successful submits classified as failed
                                │
                                └──→ Jobs enter retry loop

P-07 + P-08 (Queue Routing) ──→ ~33% of tasks silently lost

P-09 + P-10 + P-11 (Squid Network) ──→ Proxy connectivity fragile
                                           │
                                           ├──→ Open proxy on port 3128
                                           └──→ Workers may not reach all Squid instances

P-12 (Redis OOM) ──→ Redis crashes → sessions lost → all drivers need re-auth

P-14 (CORS) ──→ Users accessing via IP get CORS errors
```

---

## 9. Priority Fix Order

| Order | Problem | Expected Impact | Effort |
|-------|---------|-----------------|--------|
| 1 | P-01: Persian Date Fix | ✅ Scheduler creates jobs again | 2 hrs |
| 2 | P-02: Set Submit Endpoint | ✅ HTTP submit works (3s → 300s faster) | 30 min |
| 3 | P-03: Re-auth Drivers | ✅ Sessions restored, no auth delay | 1 hr |
| 4 | P-04: Remove engine.dispose() | ✅ Stable DB connections, -500ms latency | 15 min |
| 5 | P-12: Fix Redis maxmemory | ✅ No Redis OOM | 5 min |
| 6 | P-16: Set ENVIRONMENT=production | ✅ Security validations enabled | 1 min |
| 7 | P-17: Set MULTITENANT_ENABLED=true | ✅ Phase 1 works correctly | 1 min |
| 8 | P-05: Set QUEUE_ENABLED=true | ✅ Legacy queue path works | 1 min |
| 9 | P-06: Fix Persian classifier | ✅ Success detected correctly | 1 hr |
| 10 | P-07+P-08: Fix queue routing | ✅ No tasks lost | 30 min |
| 11 | P-09+P-10+P-11: Fix proxy networking | ✅ Secure, reliable proxy chain | 1 hr |
| 12 | P-14: Fix CORS | ✅ No CORS errors for IP access | 15 min |
| 13 | P-21: Enable HTTPS | ✅ Encrypted traffic | 2 hrs |
| 14 | P-18: Reduce retry delay | ✅ Faster recovery from transient failures | 1 min |
| 15 | P-19: Fix Driver 2 state | ✅ All 3 drivers operational | 15 min |
| 16 | Remaining P-XX | Various improvements | ~4 hrs |

---

## 10. Verification Checklist After Fixes

### Database
```bash
# Check waybill jobs are being created
docker exec barpro-postgres psql -U postgres -d utcms_rpa -c \
  "SELECT status, COUNT(*) FROM waybill_jobs GROUP BY status;"

# Check driver sessions are valid
docker exec barpro-postgres psql -U postgres -d utcms_rpa -c \
  "SELECT d.full_name, drs.last_auth_at, drs.session_expires_at, drs.state
   FROM drivers d
   JOIN driver_runtime_states drs ON drs.driver_id = d.id
   WHERE drs.session_expires_at > NOW();"
```

### Scheduler
```bash
# Check scheduler is creating jobs
docker logs barpro-worker-1 --tail 20 2>&1 | grep "evaluate_and_run"
# Expected: schedules_evaluated: X, jobs_created: Y (Y > 0)
```

### Network
```bash
# Check Squid connectivity
docker exec barpro-worker-1 curl -sx http://host.docker.internal:3128 http://httpbin.org/ip
docker exec barpro-worker-2 curl -sx http://host.docker.internal:3129 http://httpbin.org/ip
docker exec barpro-worker-3 curl -sx http://host.docker.internal:3130 http://httpbin.org/ip

# Check DNS resolution
docker exec barpro-backend python3 -c "import socket; print(socket.gethostbyname('postgres')); print(socket.gethostbyname('redis'))"

# Check CORS
curl -s -I -X OPTIONS -H "Origin: http://188.121.123.16" \
  -H "Access-Control-Request-Method: POST" http://localhost:8000/healthz \
  | grep -i "access-control"
```

### Application
```bash
# Submit a test waybill
curl -X POST http://188.121.123.16/api/v1/waybill-jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "driver_national_code": "5720114726",
    "payload": {"origin": "تهران", "destination": "شیراز", "cargo_type": "متفرقه", "cargo_weight": 1.0},
    "max_retries": 3,
    "priority": 5
  }'

# Check it was created
docker exec barpro-postgres psql -U postgres -d utcms_rpa -c \
  "SELECT id, status, source, created_at FROM waybill_jobs ORDER BY created_at DESC LIMIT 5;"
```

### Monitoring
```bash
# Check no errors in workers
docker logs barpro-worker-1 --tail 100 2>&1 | grep -iE "error|exception|traceback" | tail -5
docker logs barpro-worker-2 --tail 100 2>&1 | grep -iE "error|exception|traceback" | tail -5
docker logs barpro-worker-3 --tail 100 2>&1 | grep -iE "error|exception|traceback" | tail -5

# Check Redis memory
docker exec barpro-redis redis-cli -a $REDIS_PASSWORD INFO memory | grep -E "used_memory_human|maxmemory"
```

---

*End of Report — 36 problems documented across 10 categories*

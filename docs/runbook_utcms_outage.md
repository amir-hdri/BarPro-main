# Runbook: UTCMS Portal Outage Handling

This runbook guides operators on how to detect, manage, and recover from partial or complete outages of Iran's national transportation portal (barname.utcms.ir).

> **Updated: 2026-08-27** — Corrected the anonymous deep-link 408 diagnosis and Clean IP/Circuit Breaker behavior.

> Contract reference: [UTCMS_CONSTRAINTS.md](UTCMS_CONSTRAINTS.md). The 2026-08-13
> controlled run confirmed successful HTTP login but repeated TLS resets on
> `/barname/DocumentList/Index`; no tracking code was produced.

---

## 1. Outage Detection

An outage is suspected if:
- Prometheus triggers the **JobSuccessRateLow** alert (success rate below 80% over 1 hour).
- Celery worker logs show repeated connection timeouts (`PlaywrightTimeoutError` or `ConnectError`) accessing `barname.utcms.ir`.
- Admin dashboard reports high number of jobs in `waiting_retry` or `failed` status with error category `network_error`.
- Logs contain **`auth_playwright_waf_blocked`** — means the WAF is blocking headless Chromium (HTTP 444 / «درخواست مجاز نمی‌باشد»).
- Logs contain **`utcms_http_login_transient_status_retry`** with `status: 503` repeatedly — means Squid or UTCMS upstream is returning 5xx.

Do not diagnose an outage from a cold request to
`/Barname/Document/HagigiHogugi`. That endpoint requires the authenticated
Notification/menu flow and may return 408 to an otherwise healthy IP.

---

## 2. Diagnosing WAF vs Proxy vs Portal Down

### Step 1 — Check if HTTP (curl_cffi) login is failing

```bash
# From inside a worker container:
docker exec barpro-celery-worker grep "utcms_http_login_post_bad_status\|utcms_http_login_transient_status_retry\|auth_http_login_failed" /proc/1/fd/1 2>/dev/null | tail -20
# Or view recent Celery logs:
docker logs --tail 50 barpro-celery-worker | grep -E "http_login|waf_blocked|transient"
```

**Reading the log events:**
| Log Event | Meaning | Action |
|-----------|---------|--------|
| `utcms_http_login_transient_status_retry` + `status: 503` | Squid or UTCMS upstream returning 503 | Wait for portal to recover; system retries 3× automatically |
| `utcms_http_login_post_bad_status` + `Server: squid` in diagnostics | **Squid proxy** is the source of the 503 | Check Squid container: `docker logs barpro-squid-worker` |
| `utcms_http_login_post_bad_status` without Squid headers | **UTCMS/WAF** is the source | Portal outage or IP ban |
| `auth_playwright_waf_blocked` | WAF blocking headless Chromium (HTTP 444) | Normal fallback behavior; HTTP login must succeed |
| `auth_http_login_failed_falling_back` | HTTP login exhausted all retries | See Step 2 |

### Step 2 — Test connectivity from worker container via Squid proxy

```bash
# Check if Squid proxy itself is reachable:
docker exec barpro-celery-worker curl -x http://localhost:3128 -I https://barname.utcms.ir/ --max-time 15
```

| Result | Diagnosis |
|--------|-----------|
| `HTTP/2 200` | Login surface reachable via proxy; issuance still requires authenticated menu flow |
| `HTTP/1.1 503 Service Unavailable` + `X-Squid-Error` | Squid cannot reach portal → portal outage or egress IP banned |
| Connection refused / timeout | Squid container is down |

```bash
# Check if direct (non-proxy) access works — from the host:
curl -I https://barname.utcms.ir/ --max-time 15
```
- Both fail → portal is completely down or this IP is banned.
- Only proxy fails → Squid misconfiguration or egress IP banned.

### Step 3 — Check Squid container health

```bash
docker ps | grep squid
docker logs barpro-squid-worker --tail 30
```

---

## 3. Emergency Mitigation — Activate Circuit Breaker

To prevent connection storms, OOM on workers, and potential IP blocks, open the circuit breaker. This causes waybill submissions to fail-fast without launching Playwright.

### Via API Request (Admin Token Required)

```bash
curl -X POST "http://<YOUR_CENTRAL_SERVER_IP>/api/v1/admin/circuit-breaker/toggle?enabled=true" \
  -H "Authorization: Bearer <ADMIN_TOKEN>"
```

### Expected Behavior
- Any new waybill submissions will immediately transition to `waiting_retry` without launching Playwright.
- System metrics will reflect `itmb_circuit_breaker_state = 2` (Open).

---

## 4. Recovery Procedures

### Scenario A: Squid container down / misconfigured

```bash
# Restart Squid (Worker Node):
docker compose -f compose/worker-node.yml restart squid

# Verify after restart:
docker exec barpro-celery-worker curl -x http://localhost:3128 -I https://barname.utcms.ir/ --max-time 15
```

### Scenario B: UTCMS portal intermittent 503s (transient errors)

No action needed. Since v2.7.0, `UtcmsHttpLogin` automatically retries up to 3 times with 6-second backoff:
```
TRANSIENT_STATUS_CODES = (408, 500, 502, 503, 504)
TRANSIENT_MAX_RETRIES  = 3
TRANSIENT_BACKOFF_SECONDS = 6.0
```
Monitor logs for `utcms_http_login_transient_status_retry`. If retries persist beyond 20 minutes, open the circuit breaker (Scenario C).

### Scenario B2: HTTP 408 on issuance deep-link

1. Confirm `/Barname/Account/Login` returns a real HTTP response through the same proxy.
2. Run the authenticated flow: Login → Notification → click the waybill menu.
3. If the form opens, the IP/tunnel is healthy and the cold 408 is expected portal behavior.
4. If the authenticated flow also returns 408, classify it as `TARGET_SITE_TIMEOUT`, apply backoff,
   and compare timestamped results across more than one worker before declaring an IP-specific block.
5. Never block every Worker index from one generic 408 message.

### Scenario C: Extended portal outage (> 30 minutes)

```bash
# 1. Open circuit breaker to stop Playwright launches:
curl -X POST "http://<CENTRAL_IP>/api/v1/admin/circuit-breaker/toggle?enabled=true" \
  -H "Authorization: Bearer <ADMIN_TOKEN>"

# 2. Monitor portal status every 10 minutes:
docker exec barpro-celery-worker curl -x http://localhost:3128 -s -o /dev/null -w "%{http_code}" https://barname.utcms.ir/ --max-time 15

# 3. When portal returns 200, close circuit breaker:
curl -X POST "http://<CENTRAL_IP>/api/v1/admin/circuit-breaker/toggle?enabled=false" \
  -H "Authorization: Bearer <ADMIN_TOKEN>"
```

### Scenario D: WAF blocking Playwright (HTTP 444 / «درخواست مجاز نمی‌باشد»)

This is the normal state — Playwright is the fallback when HTTP login fails. Since v2.7.0 the system detects this within 500ms and fast-fails rather than waiting 3 minutes. The HTTP login path (curl_cffi with Chrome 120 TLS fingerprint) bypasses the WAF; focus debugging on why HTTP login is failing:

```bash
# Check if HTTP login itself is being blocked:
docker logs --tail 50 barpro-celery-worker | grep -E "http_login_failed|transient_status|post_bad_status"
```

---

## 5. Post-Outage Recovery

Once the national portal is verified as operational again:

1. **Close the circuit breaker:**
   ```bash
   curl -X POST "http://<YOUR_CENTRAL_SERVER_IP>/api/v1/admin/circuit-breaker/toggle?enabled=false" \
     -H "Authorization: Bearer <ADMIN_TOKEN>"
   ```

2. **Reconcile jobs in `unknown` status** to fetch their actual tracking code from UTCMS:
   ```bash
   curl -X POST "http://<YOUR_CENTRAL_SERVER_IP>/api/v1/admin/reconcile/<job_id>" \
     -H "Authorization: Bearer <ADMIN_TOKEN>"
   ```

3. **Monitor** system metrics to ensure job success rate climbs back above 80%.

---

## 6. Key Log Events Reference (v2.7.0+)

| Log Event | Level | Meaning |
|-----------|-------|---------|
| `auth_playwright_waf_blocked` | WARNING | Playwright detected WAF «درخواست مجاز نمی‌باشد» page — fast-failed |
| `auth_http_login_post_nav_failed` | WARNING | Post-login `page.goto(WAYBILL_URL)` threw (non-fatal; session still valid) |
| `utcms_http_login_transient_status_retry` | WARNING | 5xx transient retry with backoff |
| `utcms_http_login_fetch_unauthenticated` | WARNING | Session expired; fetch returned login page |
| `utcms_http_login_post_bad_status` | WARNING | POST response was not 2xx/3xx; includes Server/Via/X-Squid-Error headers |
| `utcms_http_login_get_bad_status` | WARNING | GET login page returned non-200 |
| `utcms_http_login_rate_limited_backoff` | WARNING | HTTP 429 from WAF; sleeping 25s |
| `auth_http_login_succeeded` | INFO | HTTP login + cookie inject OK; Playwright navigating to WAYBILL_URL |
| `auth_http_login_failed_falling_back` | INFO | HTTP login exhausted retries; trying Playwright login form |

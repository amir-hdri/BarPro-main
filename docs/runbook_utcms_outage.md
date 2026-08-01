# Runbook: UTCMS Portal Outage Handling

This runbook guides operators on how to detect, manage, and recover from partial or complete outages of Iran's national transportation portal (barname.utcms.ir).

---

## 1. Outage Detection
An outage is suspected if:
- Prometheus triggers the **JobSuccessRateLow** alert (success rate below 80% over 1 hour).
- Celery worker logs show repeated connection timeouts (`PlaywrightTimeoutError` or `ConnectError`) accessing `barname.utcms.ir`.
- Admin dashboard reports high number of jobs in `waiting_retry` or `failed` status with error category `network_error`.

---

## 2. Emergency Mitigation (Activate Circuit Breaker)
To prevent connection storms, OOM on workers, and potential IP blocks from the national portal, open the circuit breaker immediately. This causes waybill submissions to fail-fast.

### Via API Request (Admin Token Required)
Open the circuit breaker:
```bash
curl -X POST "http://<YOUR_CENTRAL_SERVER_IP>/api/v1/admin/circuit-breaker/toggle?enabled=true" \
  -H "Authorization: Bearer <ADMIN_TOKEN>"
```

### Expected Behavior
- Any new waybill submissions will immediately transition to `waiting_retry` without launching Playwright.
- System metrics will reflect `itmb_circuit_breaker_state = 2` (Open).

---

## 3. Diagnostics
Check if the outage is geo-blocking or a general portal crash:
1. Try fetching the landing page from inside a worker container via Squid proxy:
   ```bash
   curl -x http://localhost:3128 -I https://barname.utcms.ir/
   ```
2. If it returns `HTTP 200` but non-proxy curl fails, it is an IP/geo-blocking issue. Rotate proxy credentials or notify VPN/Squid proxy providers.
3. If both fail, the national portal is completely down.

---

## 4. Post-Outage Recovery
Once the national portal is verified as operational again:
1. Close the circuit breaker:
   ```bash
   curl -X POST "http://<YOUR_CENTRAL_SERVER_IP>/api/v1/admin/circuit-breaker/toggle?enabled=false" \
     -H "Authorization: Bearer <ADMIN_TOKEN>"
   ```
2. Trigger reconciliation for any jobs left in `unknown` status to fetch their actual tracking code from UTCMS:
   ```bash
   curl -X POST "http://<YOUR_CENTRAL_SERVER_IP>/api/v1/admin/reconcile/<job_id>" \
     -H "Authorization: Bearer <ADMIN_TOKEN>"
   ```
3. Monitor system metrics to ensure job success rate climbs back above 80%.

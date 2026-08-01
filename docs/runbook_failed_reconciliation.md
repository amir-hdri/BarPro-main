# Runbook: Failed Reconciliation Handling

This runbook guides operators on how to handle jobs that encounter `submission_unknown` repeatedly and trigger high-severity system alerts.

---

## 1. Context
When a worker submits a waybill but the connection is interrupted before the final confirmation screen, the database state becomes `unknown`. The Reconciliation Scheduler automatically queries the UTCMS list page to resolve it. If reconciliation yields `ambiguous` or `not_found` repeatedly (3 consecutive times), an `AdminAlert` is triggered.

---

## 2. Step-by-Step Resolution

### Step 1: Locate the Alert and Job
Log in to the Admin Dashboard under `/admin/alerts` or query the webhook alerts.
Identify the `job_id` and driver credentials involved.

---

### Step 2: Perform Manual Lookup
Since the automated scraper encountered ambiguous results (e.g., matching plates but conflicting dates), a human operator must verify the status on the national portal:
1. Obtain the driver's login from the database/Session Vault.
2. Log in directly to `barname.utcms.ir` (using a VPN with an Iranian IP).
3. Search for registered waybills in the document list.
4. Verify if the waybill matching our job parameters (cargo, date, destination) was registered:
   - **Case A: Registered**: Copy the tracking code (`UTC-YYMM-XXXXXX`).
   - **Case B: Not Registered**: No matching waybill exists on the portal.

---

### Step 3: Apply the DB Updates

#### If the Waybill was Registered (Case A)
Force the system to match the UTCMS status and record the tracking code. Trigger manual reconciliation:
```bash
curl -X POST "http://<YOUR_CENTRAL_SERVER_IP>/api/v1/admin/reconcile/<job_id>" \
  -H "Authorization: Bearer <ADMIN_TOKEN>"
```
This queries UTCMS again or matches the status and updates the database records to `success`.

#### If the Waybill was NOT Registered (Case B)
It is safe to submit the job again. You must clear the `unknown` status and reschedule the job. Trigger a protected manual retry:
```bash
# Obtain the fencing token from the active execution in DB if conflicting
curl -X POST "http://<YOUR_CENTRAL_SERVER_IP>/api/v1/admin/jobs/<job_id>/retry" \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Verified not registered on UTCMS during failed reconciliation runbook"}'
```
This transitions the job to `pending` and clears `consecutive_unknowns` back to 0.

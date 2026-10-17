# Phase 6: Manual Waybill Adoption & Shipping Lifecycle Completion — Context

## Problem Statement
Three waybills (Tracking codes `1363223066`, `1363273428`, and document issued at `14:14:43`) were issued manually on the official mobile app (`com.baarnameshahri`) by driver Hamidreza Mohammadzadeh (`5720138129`, Plate `۲۸ ع ۸۵۶ ایران ۲۸`) on 1405/07/25 (2026-10-17).
These waybills remained in status «صادر شده» (Issued) with blank traversed distance (`----`) because:
1. UTCMS never automatically transitions waybills to «در حال حمل» (In Transit) or «پایان حمل» (Finished Transit). It requires two explicit REST API calls: `RegisterStartOfShipping` and `RegisterEndOfShipping`.
2. BarPro lacked an automated ingestion mechanism (`External Waybill Adoption Worker`) to scan and adopt waybills issued manually on driver devices.
3. Systemic shipping lifecycle issues in BarPro:
   - When origin and destination coordinates are identical (as occurred in Job 14, template 4), routing returned `requires_reselection=True`, causing `waybill_bot_multitenant.py` to quietly drop `RegisterStartOfShipping`.
   - When UTCMS returns HTTP 429 (Rate Limit) on `RegisterStartOfShipping` (as occurred in Job 8), the step is flagged `unknown`, but `shipping_worker.py` only scanned `in_transit` jobs and lacked retry logic for rate-limited start attempts.
   - The default 20s mobile API timeout caused premature worker timeouts during peak portal traffic, pushing drivers to issue documents manually on their phones.

## Scope of Work

### Step 1: Execute Start & End Shipping for the 3 Manual Waybills
- Query driver's issued documents via `UtcmsMobileClient.get_issued_documents` to extract `doc_id`, origin, and destination coordinates for tracking codes `1363223066`, `1363273428`, and the `14:14:43` waybill.
- Execute `RegisterStartOfShipping` with valid origin coordinates and start timestamp.
- Generate valid polyline `gpsList` with $>2\text{ km}$ traversed distance (Rule 4012), respect required transit time (Rule 4013), and execute `RegisterEndOfShipping`.
- Verify the final status transitions and traversed km in UTCMS.

### Step 2: Core Structural Hardening
- **External Waybill Adoption Worker (`app/workers/tasks.py`, `app/workers/celery_app.py`, `app/orchestrator/adoption_service.py`)**:
  - Implement periodic Celery Beat task `barpro.waybill.adopt_external` running every 10 minutes.
  - Queries active drivers for unadopted issued documents and creates tracked `WaybillJob` records to drive their full shipping lifecycle.
- **Mobile API Timeout Hardening (`app/core/config.py`, `.env.example`)**:
  - Increase `UTCMS_MOBILE_API_TIMEOUT_SECONDS` from 20s to 45s.
- **Shipping Worker Unknown/429 Retry (`app/workers/shipping_worker.py`, `app/automation/gps_shipping_manager.py`)**:
  - Extend worker to scan `unknown` / rate-limited shipping starts after cooldown and retry `RegisterStartOfShipping`.
- **Identical-Coordinate Detour (`app/services/route_authority.py`, `app/automation/waybill_bot_multitenant.py`)**:
  - Automatically apply standard 200m micro-detour when origin and destination coordinates are identical to ensure valid route polyline generation.

## Acceptance Criteria
1. The 3 manually issued waybills have start and end of shipping registered and verified on UTCMS.
2. `External Waybill Adoption Worker` runs cleanly without duplicate adoptions or session invalidations.
3. Unit and integration tests verify adoption logic, 429 retry, identical-coordinate detour, and timeout settings.

---
issues: [104, 105, 106]
---
# Phase 6: Manual Waybill Adoption & Shipping Lifecycle Completion — Plan

## Tasks

### Wave 1: Core Systemic Hardening (Issue #106)
- [ ] Task 1.1: Increase `UTCMS_MOBILE_API_TIMEOUT_SECONDS` default from 20s to 45s in `app/core/config.py` and `.env.example`.
- [ ] Task 1.2: Add micro-detour handling in `app/services/route_authority.py` and `app/automation/waybill_bot_multitenant.py` when origin and destination coordinates are identical (< 15 meters) to ensure valid route polyline generation.
- [ ] Task 1.3: Extend `app/workers/shipping_worker.py` and `app/automation/gps_shipping_manager.py` to scan and retry `unknown` / rate-limited (HTTP 429) shipping starts after cooldown.

### Wave 2: External Waybill Adoption Worker in Celery Beat (Issue #105)
- [ ] Task 2.1: Implement `ExternalWaybillAdoptionService` in `app/orchestrator/adoption_service.py` to query issued documents, avoid duplicates, and create tracked `WaybillJob` records.
- [ ] Task 2.2: Register periodic Celery Beat task `barpro.waybill.adopt_external` (every 10 minutes) in `app/workers/celery_app.py` and `app/workers/tasks.py`.
- [ ] Task 2.3: Implement unit and integration tests for external waybill adoption.

### Wave 3: Execute Shipping Lifecycle for the 3 Manual Waybills (Issue #104)
- [ ] Task 3.1: Query driver Hamidreza Mohammadzadeh's issued documents to get numerical `doc_id`s, origin, and destination coordinates for tracking codes `1363223066`, `1363273428`, and the `14:14:43` waybill.
- [ ] Task 3.2: Execute `RegisterStartOfShipping` with proper departure timestamps.
- [ ] Task 3.3: Construct valid `gpsList` with $>2\text{ km}$ distance, respect required travel time (Rule 4013), and execute `RegisterEndOfShipping`.
- [ ] Task 3.4: Verify traversed distance in UTCMS and close Issue #104 with evidence.

### Wave 4: Full-Stack Verification & Delivery
- [ ] Task 4.1: Run full test suite (`pytest`) and verify all tests pass.
- [ ] Task 4.2: Update `docs/CHANGELOG.md` and `docs/BARPRO_KNOWLEDGE_GRAPH.md`.

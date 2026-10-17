---
issues: [107, 108, 109, 110]
---
# Phase 5: Recurring Waybill Cycling & Intelligent Scheduling — Plan

## Tasks

### Wave 1: Recurring Waybill Cycling Engine: Multi-Route Modes & Smart Payload Inversion (Issue #107)
- [x] Task 1.1: Implement multi-route operational modes (`standard`, `round_trip_cycling`, and `one_way_repeated`) and schema extensions in `app/schemas/multiroute.py` and `app/models_multitenant.py`. `verify: ./.venv/bin/pytest tests/test_recurring_cycling_batches.py -k test_multiroute_schema`
- [x] Task 1.2: Implement `invert_waybill_payload` in `app/services/batch_service.py` to perform symmetric origin $\leftrightarrow$ destination and sender $\leftrightarrow$ receiver postal code inversion for return legs. `verify: ./.venv/bin/pytest tests/test_recurring_cycling_batches.py -k test_smart_inversion`
- [x] Task 1.3: Enforce Iran 31-province adjacency matrix (`IRAN_ADJACENT_PROVINCES`) and `validate_driver_fleet_scope` pre-dispatch gate against UTCMS Rules 4028 and 4045. `verify: ./.venv/bin/pytest tests/test_recurring_cycling_batches.py -k test_fleet_scope`

### Wave 2: Intelligent Road Distance, Speed Models & Highway Snapping Buffers (Issue #108)
- [x] Task 2.1: Implement `calculate_cycling_times` in `app/core/distance.py` and `app/services/distance_service.py` using realistic vehicle speed profiles (intercity 60 km/h, urban 28 km/h) and configurable rest buffers (min 45 min). `verify: ./.venv/bin/pytest tests/test_recurring_cycling_batches.py -k test_cycling_times`
- [x] Task 2.2: Implement `snap_coordinate_to_road` with Neshan reverse geocoding and resilient fallback to ensure valid roadway coordinates. `verify: ./.venv/bin/pytest tests/test_recurring_cycling_batches.py -k test_road_snapping`

### Wave 3: Fail-Safe Chain Halt & Multi-Route Scheduler Resilience (Issue #109)
- [x] Task 3.1: Enhance `SchedulerService` in `app/orchestrator/scheduler_service.py` with fail-safe chain halt to abort or hold subsequent batch legs when a preceding leg fails or enters `NEEDS_REVIEW`. `verify: ./.venv/bin/pytest tests/test_recurring_cycling_batches.py -k test_chain_halt`
- [x] Task 3.2: Implement exponential backoff window (900s–1800s) on HTTP 429 rate limits in `app/automation/gps_shipping_manager.py` to prevent cascading worker backpressure. `verify: ./.venv/bin/pytest tests/test_recurring_cycling_batches.py -k test_backoff`

### Wave 4: Multi-Route Scenario Timeline UI & Cycling Regression Test Suite (Issue #110)
- [x] Task 4.1: Build interactive scenario selector tabs (Standard, Round-Trip Cycling, One-Way Repeated) and schedule preview timeline table in `apps/web/src/app/batches/page.tsx`. `verify: cd apps/web && npx tsc --noEmit`
- [x] Task 4.2: Execute end-to-end regression test suite for recurring cycling batches verifying 100% pass rate. `verify: ./.venv/bin/pytest tests/test_recurring_cycling_batches.py`

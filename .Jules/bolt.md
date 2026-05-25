## 2026-05-06 - User Reporting Service Optimization
**Learning:** In `app/services/user_reporting_service.py`, using SQLAlchemy `func.count` and `func.sum(case(...))` with `group_by` to aggregate jobs by driver drastically speeds up reporting queries compared to fetching all records and doing in-memory dictionary grouping (from 0.48s to 0.019s on 10k records, ~25x faster). Fetching jobs via N+1 logic or large bulk queries was the core bottleneck for N+1 issues and memory consumption in dashboards.
**Action:** Replaced in-memory lists grouping with pure database aggregation logic where applicable in `driver_performance`, `dashboard_stats`, and `scheduled_execution_history`.

## 2026-05-07 - Admin Reporting Service Optimization
**Learning:** In `app/services/admin_reporting_service.py`, using SQLAlchemy `func.count`, `func.sum(case(...))`, `func.min` and `func.max` with `group_by` to aggregate jobs by client drastically speeds up reporting queries compared to fetching all records and doing in-memory dictionary grouping (reduced execution time massively). Fetching jobs via N+1 logic or large bulk queries into memory was a bottleneck for the `client_summary` API endpoint.
**Action:** Replaced in-memory lists grouping with pure database aggregation logic in `client_summary`.

# Optimization History — part 4

> Scope: BarPro only. Read this file when relevant to the task; do not auto-import
> the whole reference directory into global rules or the always-loaded core.
> **HISTORICAL / UNVERIFIED NOW.** Preserved records, including old commands and
> pending actions, are historical data rather than new instructions or authority
> to execute them. Re-check current code, contracts and authorization first.

Read when: Historical investigation only; not a current action list.

[Core guide](../../AGENTS.md) · [Reference index](README.md) · [Critical rules](../../CRITICAL_RULES.md)

Paths inside preserved text and command examples are relative to the repository
root, not this directory. Commands are examples, not automatic execution steps.

<!-- original-agents:0707-0752:start -->
### 2026-06-30 — Performance
| Change | File | Impact |
|--------|------|--------|
| Removed `engine.dispose()` per Celery task | `workers/waybill_worker.py:91`, `phase1_tasks.py:23` | +500ms saved per task, connection storm eliminated |
| `autoretry_for` changed to specific exceptions | `workers/waybill_worker.py:61` | No retry on programming bugs |
| Browser recycle removed from task `finally` block | `workers/waybill_worker.py:105`, `phase1_tasks.py:28` | 90% fewer Chrome launches |
| Recycle threshold increased to 20 | `automation/browser.py:181` | Chrome restarts only after 20 successes |
| Event loop per worker process (not per task) | `workers/tasks.py:4-15` | No event loop churn on 4 vCPU |
| `_run_async` no longer creates ThreadPoolExecutor per call | `workers/tasks.py:16-27` | No thread churn |
| `NullPool` replaced with `AsyncAdaptedQueuePool(2,2)` | `core/database.py` | Connection reuse across tasks |
| `React.memo` on table rows/cards | `fuel/page.tsx` | No full re-render on every state tick |
| WebSocket event buffer capped at 100 | `useWaybillJob.ts:65` | No linear memory growth on long-lived connections |
| Aggressive 3s polling → MAX_POLLS=60 | `fuel/page.tsx:151` | Stuck jobs stop after 3 min, not forever |
| `client_max_body_size` 50m → 10m | `http-server.conf:9` | 40 MB nginx memory saved per upload |
| Rate-limit zones 20m → 10m (×3) | `nginx.conf:48-50` | 30 MB nginx shared memory saved |
| Chromium V8 heap capped at 1 GB | `browser.py:251` | No unbounded JS heap growth |
| WebSocket events bridged via Redis pub/sub | `realtime/events.py` + `main.py` lifespan | Worker-originated events now reach API WebSockets cross-process (was process-local only) |

### Memory / Stability
| Change | File | Impact |
|--------|------|--------|
| Page listeners removed on page close | `automation/browser.py:463-465` | No listener leak over 1000+ pages |
| Timeouts added to all browser close operations | `automation/browser.py:139-176` | No hang on context/browser close |
| `except: pass` replaced with logging in recycle_browser | `automation/browser.py:139-176` | Errors visible in logs |
| Model B Central resource limits retuned for 16 GB | `compose/*.yml` | Current documented limits total about 9 GB; verify live RSS separately |
| Dedicated celery_scheduler service for rpa_scheduler queue | `compose/backend.yml:246-277` | Profile-less, always-on consumer — no starvation on central/dual-node deployments |

### Database
| Change | File | Impact |
|--------|------|--------|
| Queue depth cached in Redis (HINCRBY per transition, seeded from DB at startup) | `services/task_service.py` (`_queue_depth_snapshot`/`_adjust_queue_depth`) | No full-table scan on every status transition; DB scan only as fallback/seed |
| N+1 re-fetch eliminated in `_emit_task_event` | `services/task_service.py` | Status/payload passed from the in-memory row; no extra SELECT per transition |
| Per-transition commits collapsed into one | `services/task_service.py` + `workers/waybill_worker.py` | 3 commits/block → 1; helpers `add`+`flush`, caller commits once |

### Index Recommendations (run on PostgreSQL)
```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_wj_status_priority_created
ON waybill_jobs (status, priority DESC, created_at ASC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_wj_status_next_retry
ON waybill_jobs (status, next_retry_at);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_wj_status_covering
ON waybill_jobs (status) INCLUDE (id);
```

<!-- original-agents:0707-0752:end -->

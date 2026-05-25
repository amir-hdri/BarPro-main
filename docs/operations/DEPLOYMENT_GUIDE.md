# راهنمای استقرار بهینه‌سازی‌ها

> **📌 معماری جدید:** پروژه به معماری monorepo ارتقا یافته است. فرانت‌اند اصلی با Next.js و Tailwind در پوشه `apps/web/` و بک‌اند در `app/` قرار دارد. تمامی مستندات در راستای این تغییرات به‌روزرسانی شده‌اند.


## پیش‌نیازها

- Python 3.11+
- PostgreSQL 13+ (برای production)
- SQLite (برای development/testing)
- Redis (اختیاری - برای caching)

## مراحل استقرار

### 1. بررسی محیط

```bash
# بررسی نسخه Python
python --version

# بررسی وابستگی‌ها
pip list | grep -E "sqlalchemy|alembic|pytest|asyncpg"
```

### 2. اجرای تست‌ها

```bash
# تست‌های سریع جدید
pytest tests/test_waybill_enhanced_fast.py -v

# تست‌های integration (اختیاری)
pytest tests/test_enhanced_waybill_manager.py -v -k "test_initialization"

# اجرای همه تست‌ها
pytest tests/ -v --tb=short
```

**نتیجه مورد انتظار:**
- ✅ 16 تست سریع در ~2-3 ثانیه
- ✅ همه تست‌ها PASSED

### 3. بررسی Database Connection

```bash
# بررسی DATABASE_URL در .env
cat .env | grep DATABASE_URL

# تست اتصال
python -c "
import asyncio
from app.core.database import engine

async def test():
    async with engine.begin() as conn:
        result = await conn.execute('SELECT 1')
        print('✅ Database connection OK')

asyncio.run(test())
"
```

### 4. اعمال Migrations (فقط برای Production)

⚠️ **هشدار**: این مرحله فقط زمانی اجرا شود که database در دسترس باشد.

```bash
# بررسی وضعیت فعلی
alembic current

# مشاهده migrations در انتظار
alembic history

# اعمال migration جدید
alembic upgrade head

# بررسی indexes جدید
psql $DATABASE_URL -c "\d+ waybilltask"
psql $DATABASE_URL -c "\d+ waybilljob"
```

**Indexes جدید:**
- `idx_waybilltask_status_created`
- `idx_waybilltask_worker_status`
- `idx_waybilltask_retryable_attempt`
- `idx_waybilljob_client_status`
- `idx_waybilljob_driver_status`
- `idx_waybilljob_created_status`
- `idx_domainevent_client_timestamp`
- `idx_domainevent_event_type`
- `idx_driverruntimestate_state`

### 5. تحلیل Database (اختیاری)

```bash
# اجرای script تحلیل
python scripts/analyze_database.py
```

**خروجی مورد انتظار:**
- Table statistics (size, row count)
- Index list
- Slow queries (اگر pg_stat_statements فعال باشد)
- Connection pool settings
- Optimization suggestions

### 6. بررسی Monitoring Integration

```bash
# بررسی import‌ها
python -c "
from app.monitoring.event_bridge import monitoring_bridge
from app.realtime.events import event_hub
print('✅ Monitoring modules OK')
"

# تست event emission
python -c "
import asyncio
from app.monitoring.event_bridge import monitoring_bridge

async def test():
    await monitoring_bridge.emit(
        'test_event',
        {'message': 'test'},
        tags={'source': 'deployment_test'}
    )
    print('✅ Event emission OK')

asyncio.run(test())
"
```

### 7. راه‌اندازی Application

```bash
# Development
uvicorn app.main:app --reload --port 8000

# Production (با Gunicorn)
gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
```

### 8. راه‌اندازی Celery Workers

```bash
# Worker برای waybill tasks
celery -A app.workers.celery_app worker \
  --loglevel=info \
  --concurrency=4 \
  --queue=waybill_tasks \
  --max-tasks-per-child=100

# Beat scheduler (برای periodic tasks)
celery -A app.workers.celery_app beat \
  --loglevel=info
```

## بررسی عملکرد

### 1. Health Check

```bash
curl http://localhost:8000/health
# Expected: {"status": "healthy"}
```

### 2. Metrics Endpoint

```bash
curl http://localhost:8000/metrics
# Expected: Prometheus metrics
```

### 3. WebSocket Connection

```bash
# با wscat
wscat -c ws://localhost:8000/ws/events?channels=all

# یا با Python
python -c "
import asyncio
import websockets

async def test():
    async with websockets.connect('ws://localhost:8000/ws/events?channels=all') as ws:
        msg = await ws.recv()
        print(f'✅ Received: {msg}')

asyncio.run(test())
"
```

### 4. Database Performance

```bash
# بررسی query performance
psql $DATABASE_URL -c "
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan DESC
LIMIT 10;
"
```

## Rollback (در صورت مشکل)

### Rollback Migration

```bash
# برگشت به migration قبلی
alembic downgrade -1

# برگشت به migration خاص
alembic downgrade 005_fix_constraint_conflicts
```

### Rollback Code

```bash
# برگشت به commit قبلی
git log --oneline -5
git revert <commit-hash>

# یا
git reset --hard <commit-hash>
git push --force
```

## Monitoring در Production

### 1. Prometheus Queries

```promql
# Request rate
rate(waybill_requests_total[5m])

# Success rate
rate(waybill_success_total[5m]) / rate(waybill_requests_total[5m])

# Error rate by category
rate(waybill_failure_total[5m]) by (category)

# Queue depth
waybill_queue_depth

# Task latency (p95)
histogram_quantile(0.95, rate(waybill_task_latency_seconds_bucket[5m]))
```

### 2. Database Monitoring

```sql
-- Active connections
SELECT count(*) FROM pg_stat_activity WHERE state = 'active';

-- Long running queries
SELECT pid, now() - query_start as duration, query
FROM pg_stat_activity
WHERE state = 'active' AND now() - query_start > interval '5 seconds'
ORDER BY duration DESC;

-- Index usage
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan,
    pg_size_pretty(pg_relation_size(indexrelid)) as size
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
ORDER BY idx_scan DESC;
```

### 3. Log Monitoring

```bash
# Monitoring events
tail -f logs/app.log | grep "waybill_pill_trace\|waybill_selector_inventory_audit"

# Errors
tail -f logs/app.log | grep "ERROR"

# Performance
tail -f logs/app.log | grep "latency\|duration"
```

## Troubleshooting

### مشکل: تست‌ها fail می‌شوند

```bash
# بررسی dependencies
pip install -r requirements.txt

# پاک کردن cache
pytest --cache-clear
rm -rf .pytest_cache __pycache__

# اجرای مجدد
pytest tests/test_waybill_enhanced_fast.py -v
```

### مشکل: Migration fail می‌شود

```bash
# بررسی وضعیت
alembic current
alembic history

# Stamp manual (اگر لازم باشد)
alembic stamp head

# یا rollback و retry
alembic downgrade -1
alembic upgrade head
```

### مشکل: Connection pool exhausted

```python
# در app/core/database.py
engine = create_async_engine(
    DATABASE_URL,
    pool_size=30,        # افزایش از 20
    max_overflow=20,     # افزایش از 10
    pool_timeout=60,     # افزایش از 30
)
```

### مشکل: Slow queries

```sql
-- Enable pg_stat_statements
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- بررسی slow queries
SELECT 
    substring(query, 1, 100) as query,
    calls,
    mean_exec_time,
    total_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

## Checklist نهایی

- [ ] تست‌های سریع pass می‌شوند (16/16)
- [ ] Database connection موفق است
- [ ] Migrations اعمال شده‌اند (در production)
- [ ] Indexes جدید ایجاد شده‌اند
- [ ] Monitoring events به timeline می‌روند
- [ ] Prometheus metrics در دسترس هستند
- [ ] WebSocket connection کار می‌کند
- [ ] Application راه‌اندازی شده است
- [ ] Celery workers در حال اجرا هستند
- [ ] Health check موفق است

## پشتیبانی

برای مشکلات یا سوالات:
1. بررسی `docs/OPTIMIZATION_SUMMARY.md`
2. بررسی `docs/FLOW_VERIFICATION.md`
3. اجرای `python scripts/analyze_database.py`
4. بررسی logs در `logs/app.log`

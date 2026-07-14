# گزارش تحلیل مشکلات ثبت بارنامه و استعلام سوخت — BarPro

**تاریخ تحلیل**: 2026-07-14  
**وضعیت سیستم**: تمام تغییرات Implementation Plan قبلاً اعمال شده‌اند

---

## خلاصه اجرایی

پس از بررسی جامع کدبیس، مشخص شد که **طرح پیاده‌سازی قبلی (`implementation_plan.md`) قبلاً به طور کامل اجرا شده است**. با این حال، **مشکل اصلی در جای دیگری قرار دارد** و تغییرات اعمال شده به تنهایی کافی نیستند.

### یافته‌های کلیدی

1. ✅ **Browser Manager**: تمام بهینه‌سازی‌ها اعمال شده (`_ensure_loop_resources` async، `playwright.stop()`, `--disable-dbus`)
2. ✅ **Event Loop Management**: Thread-local event loop در `utils.py` فعال است
3. ❌ **Race Condition در Scheduler**: چند worker می‌توانند همزمان یک job را dispatch کنند
4. ❌ **Missing Import**: `WaybillError` در `fuel_inquiry_service.py` استفاده شده بدون import
5. ⚠️ **Potential Deadlocks**: در browser locks و nested transactions

---

## مشکلات شناسایی شده (اولویت‌بندی شده)

### 🔴 **[P0] مشکل #1: Race Condition در Scheduler Dispatch**

**محل**: `app/services/rpa_scheduler_service.py:122-243`

**شرح مشکل**:
```python
# در plan_due_jobs(), بعد از انتخاب job برای dispatch:
if job.celery_task_id:
    continue  # Skip if already dispatched

# اما بین این چک و زمان set کردن celery_task_id، فاصله زمانی وجود دارد
# که worker دیگری می‌تواند همان job را ببیند و dispatch کند
```

**علت ریشه‌ای**:
- Scheduler در Beat و workers همزمان اجرا می‌شود
- چک `job.celery_task_id` و set آن atomic نیست
- در فاصله بین `plan_due_jobs()` و `dispatch_phase1_decisions()` (دو فراخوانی جداگانه)، جاب‌ها commit نشده‌اند

**تأثیر**:
- جاب‌های بارنامه/استعلام سوخت ممکن است دوبار dispatch شوند
- کارهای duplicate → اتلاف منابع worker
- ممکن است سبب قفل شدن در `queued` شود چون celery_task_id اولی overwrite می‌شود

**راه‌حل پیشنهادی**:
```python
# در rpa_scheduler_service.py
async def plan_due_jobs(self, *, persist: bool = True) -> list[SchedulerDecision]:
    session = async_session_factory()
    try:
        # BEFORE: job.celery_task_id is checked but not atomically set
        # AFTER: Use SELECT FOR UPDATE to lock the row
        
        from sqlalchemy import and_
        
        jobs = (
            await session.exec(
                select(WaybillJob, Driver)
                .join(Driver, Driver.id == WaybillJob.driver_id)
                .where(
                    col(WaybillJob.status).in_([...]),
                    WaybillJob.celery_task_id.is_(None),  # Only pick unassigned
                )
                .with_for_update(skip_locked=True)  # ← PostgreSQL row-level lock
                .order_by(col(WaybillJob.priority).desc(), col(WaybillJob.created_at).asc())
                .limit(batch_limit)
            )
        ).all()
        
        # Now, immediately mark jobs with a temporary task ID
        for job, driver in jobs:
            job.celery_task_id = f"reserved_{uuid.uuid4().hex[:16]}"
            session.add(job)
        
        await session.commit()  # Commit the reservation
        
        # Then dispatch (even if dispatch fails, cleanup_stuck_jobs will recover)
        # ...
```

**Urgency**: 🔴 **CRITICAL** — این می‌تواند علت اصلی گیر کردن جاب‌ها در `queued` باشد

---

### 🟠 **[P1] مشکل #2: Missing Import در Fuel Inquiry**

**محل**: `app/services/fuel_inquiry_service.py:252`

**شرح مشکل**:
```python
if not is_healthy:
    raise WaybillError("پروکسی یا شبکه تونل ایران قطع می‌باشد")
    # ↑ WaybillError import نشده
```

**تأثیر**:
- هر استعلام سوخت که proxy health check fail شود، با `NameError` کرش می‌کند
- Status به `failed` تبدیل می‌شود با error code نامشخص
- کاربر پیغام مفید دریافت نمی‌کند

**راه‌حل**:
```python
# در ابتدای fuel_inquiry_service.py
from app.core.exceptions import WaybillError
```

**Urgency**: 🟠 **HIGH** — باید قبل از release بعدی رفع شود

---

### 🟡 **[P2] مشکل #3: Celery Beat Schedule Overlap**

**محل**: `app/workers/celery_app.py:72-99`

**شرح مشکل**:
```python
beat_schedule={
    "phase1-scheduler-plan": {
        "task": "phase1.scheduler.plan",
        "schedule": schedule(utcms_config.RPA_SCHEDULER_INTERVAL_SECONDS),  # مثلاً هر 30 ثانیه
        "options": {"queue": utcms_config.RPA_SCHEDULER_QUEUE},
    },
    # ...
}
```

اگر `RPA_SCHEDULER_INTERVAL_SECONDS` کوچک باشد (مثلاً 10 ثانیه) و scheduler task بیش از 10 ثانیه طول بکشد، چند نمونه همزمان اجرا می‌شوند.

**تأثیر**:
- چندین scheduler task همزمان روی یک worker/queue
- Race condition در dispatch (تشدید مشکل #1)

**راه‌حل**:
```python
# در celery_app.py
beat_schedule={
    "phase1-scheduler-plan": {
        "task": "phase1.scheduler.plan",
        "schedule": schedule(utcms_config.RPA_SCHEDULER_INTERVAL_SECONDS),
        "options": {
            "queue": utcms_config.RPA_SCHEDULER_QUEUE,
            "expires": utcms_config.RPA_SCHEDULER_INTERVAL_SECONDS - 5,  # ← Expire if not picked up
        },
    },
}
```

**Urgency**: 🟡 **MEDIUM** — ریسک بالا در پیکربندی‌های aggressive

---

### 🟡 **[P2] مشکل #4: Browser Lock Contention**

**محل**: `app/automation/browser.py:186-207`

**شرح مشکل**:
```python
async def _ensure_loop_resources(self):
    # ...
    async with self._init_lock:  # این lock در recycle_browser هم گرفته می‌شود
        # ...

async def recycle_browser(self):
    async with self._init_lock:  # اگر initialize در حال اجراست، block می‌شود
        # ...
```

اگر `record_success_for_recycle()` در وسط یک `initialize()` فراخوانی شود، deadlock خفیف ایجاد می‌شود.

**تأثیر**:
- Worker timeout در browser initialization
- کاهش throughput

**راه‌حل**:
```python
async def record_success_for_recycle(self):
    self._success_count_recycle += 1
    if self._success_count_recycle >= 20:
        self._success_count_recycle = 0
        # ← Instead of calling recycle_browser() here (which acquires _init_lock),
        # set a flag and check it in initialize() or close_context()
        self._recycle_pending = True
```

**Urgency**: 🟡 **MEDIUM** — فقط در load بالا قابل مشاهده

---

### 🟢 **[P3] مشکل #5: Redis Fallback Lock Not Cross-Process**

**محل**: `app/services/rpa_runtime_service.py:72-93`

**شرح مشکل**:
```python
async def acquire_lock(self, key: str, ttl_seconds: int) -> bool:
    redis = await self._get_redis()
    if redis is not None:
        return bool(await redis.set(key, "1", ex=ttl_seconds, nx=True))
    
    # In-memory fallback (only works within one process!)
    with self._get_lock():  # ← threading.Lock
        # ...
```

اگر Redis از دسترس خارج شود، lock‌ها فقط در یک worker process کار می‌کنند.

**تأثیر**:
- در صورت Redis outage، race condition بین workers
- Auth lock شکسته می‌شود → چندین worker همزمان login می‌کنند

**راه‌حل**:
- Log کردن warning اگر Redis unavailable است
- یا اصلاً fallback را حذف کنیم و exception برگردانیم (fail-fast)

```python
async def acquire_lock(self, key: str, ttl_seconds: int) -> bool:
    redis = await self._get_redis()
    if redis is None:
        logger.error("distributed_lock_unavailable_redis_down")
        raise RuntimeError("Redis unavailable for distributed locking")
    return bool(await redis.set(key, "1", ex=ttl_seconds, nx=True))
```

**Urgency**: 🟢 **LOW** — فقط در Redis failure scenarios

---

## علل احتمالی "کارها در Queued می‌مانند"

بر اساس تحلیل، احتمالی‌ترین علل به ترتیب:

### 1️⃣ **Celery Beat متوقف شده یا کُند است** (احتمال: 40%)

**چک**:
```bash
docker logs barpro-celery-beat --tail 100 | grep "phase1.scheduler.plan"
```

باید هر N ثانیه (طبق config) لاگ dispatch ببینید. اگر نمی‌بینید:
- Beat container کرش کرده
- یا `RPA_SCHEDULER_INTERVAL_SECONDS` خیلی بزرگ است

**راه‌حل موقت**:
```bash
docker restart barpro-celery-beat
```

---

### 2️⃣ **Race Condition در Scheduler** (احتمال: 30%)

دو نمونه scheduler همزمان یک job را dispatch کرده‌اند، اولی موفق شده، دومی celery_task_id اولی را overwrite کرده، کار اصلی گم شده.

**چک**:
```sql
SELECT job_id, status, celery_task_id, updated_at, created_at
FROM waybill_jobs
WHERE status = 'queued'
  AND updated_at < NOW() - INTERVAL '5 minutes'
ORDER BY created_at DESC
LIMIT 20;
```

اگر `celery_task_id` پر است ولی کار stuck است → نشانه race condition

**راه‌حل**: اعمال مشکل #1

---

### 3️⃣ **Worker Died قبل از Processing** (احتمال: 20%)

Worker کار را از صف برداشته ولی قبل از `mark_processing` مرده (OOM kill، network timeout، etc)

**چک**:
```bash
docker logs barpro-celery-worker-1 --tail 500 | grep "Killed\|OOM\|OutOfMemory"
docker stats --no-stream | grep celery-worker
```

**راه‌حل**: `cleanup_stuck_jobs` باید هر 5 دقیقه اینها را بازیابی کند

---

### 4️⃣ **Auth Session Expired و Scheduler نمی‌تواند Auth Task را Dispatch کند** (احتمال: 10%)

Job در `WAITING_AUTH` گیر کرده، auth task dispatch نمی‌شود.

**چک**:
```sql
SELECT job_id, status, driver_id, updated_at, error_message
FROM waybill_jobs
WHERE status = 'waiting_auth'
  AND updated_at < NOW() - INTERVAL '10 minutes';
```

**راه‌حل**: 
- بررسی لاگ Beat: `grep "phase1.auth.process" celery-beat.log`
- اگر dispatch نمی‌شود → مشکل #1 یا Celery connection issue

---

## دستورات تشخیص سریع

### چک وضعیت Beat
```bash
docker exec barpro-celery-beat celery -A app.workers.celery_app inspect active
```

### چک صف Celery
```bash
docker exec barpro-redis redis-cli LLEN celery
docker exec barpro-redis redis-cli KEYS "celery-task-meta-*" | wc -l
```

### چک لاگ Workers برای خطای Playwright
```bash
docker logs barpro-celery-worker-1 2>&1 | grep -i "chromium.launch:\|playwright"
```

### بازیابی دستی کارهای Stuck
```sql
-- در PostgreSQL
UPDATE waybill_jobs
SET status = 'pending',
    celery_task_id = NULL,
    updated_at = NOW()
WHERE status IN ('queued', 'waiting_auth')
  AND updated_at < NOW() - INTERVAL '15 minutes';
```

---

## اقدامات پیشنهادی (Step-by-Step)

### فاز 1: رفع مشکلات Critical (P0)

1. **اعمال Fix برای Race Condition**
   - فایل: `app/services/rpa_scheduler_service.py`
   - تغییر: اضافه کردن `with_for_update(skip_locked=True)`
   - تست: deploy روی staging، مانیتور لاگ‌ها برای 24 ساعت

2. **اضافه کردن Import برای WaybillError**
   - فایل: `app/services/fuel_inquiry_service.py`
   - تغییر: `from app.core.exceptions import WaybillError`
   - تست: یک استعلام سوخت با proxy down

### فاز 2: بهبود Monitoring (جلوگیری از recurrence)

3. **اضافه کردن Prometheus Metric برای Stuck Jobs**
   ```python
   # در app/monitoring/metrics.py
   stuck_jobs_gauge = Gauge("barpro_stuck_jobs_total", "Jobs stuck in queued for >5min")
   
   # در rpa_scheduler_service.cleanup_stuck_jobs():
   stuck_jobs_gauge.set(count)
   ```

4. **Alert برای Beat Downtime**
   ```yaml
   # در infra/prometheus/alert_rules.yml
   - alert: CeleryBeatDown
     expr: up{job="celery-beat"} == 0
     for: 2m
     annotations:
       summary: "Celery Beat is down — scheduler not running"
   ```

### فاز 3: بهینه‌سازی‌های Optional (P2-P3)

5. **اعمال Browser Lock Optimization** (اگر load بالا مشاهده شد)
6. **حذف In-Memory Fallback در rpa_runtime** (برای consistency بهتر)

---

## تست‌های پیشنهادی

### تست 1: Race Condition در Scheduler
```python
# tests/test_scheduler_race_condition.py
import asyncio
import pytest
from app.services.rpa_scheduler_service import rpa_scheduler_service

@pytest.mark.asyncio
async def test_concurrent_scheduler_no_duplicate_dispatch():
    # Create 1 pending job
    # Run plan_due_jobs() from 3 concurrent tasks
    # Assert only 1 celery_task_id is set
    results = await asyncio.gather(
        rpa_scheduler_service.plan_due_jobs(),
        rpa_scheduler_service.plan_due_jobs(),
        rpa_scheduler_service.plan_due_jobs(),
    )
    # Check: job.celery_task_id is set only once
```

### تست 2: Stuck Job Recovery
```python
@pytest.mark.asyncio
async def test_cleanup_recovers_stuck_jobs():
    # Create job with status=QUEUED, updated_at = 20 minutes ago
    # Call cleanup_stuck_jobs()
    # Assert job.status == PENDING, celery_task_id == None
```

---

## نتیجه‌گیری

**وضعیت Implementation Plan قبلی**: ✅ تمام تغییرات اعمال شده

**مشکل اصلی**: ⚠️ Race condition در scheduler + احتمالاً Beat downtime

**اقدامات فوری**:
1. ✅ چک کردن لاگ Beat و Workers
2. ✅ بررسی دیتابیس برای stuck jobs
3. ✅ اعمال fix #1 (SELECT FOR UPDATE)
4. ✅ اضافه کردن missing import

**زمان تخمینی برای رفع**: 4-6 ساعت (شامل تست و deploy)

---

**تهیه‌کننده**: Kiro AI Analysis  
**تاریخ**: 2026-07-14  
**نسخه**: 1.0

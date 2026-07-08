# گزارش تحلیل ۳ بارنامه اخیر در سرور (RCA Report)

بر اساس بررسی‌های انجام شده در سرور `188.121.123.16` (از طریق اتصال SSH با کاربری `ubuntu`) و دیتابیس PostgreSQL کانتینر `barpro-postgres` (دیتابیس `utcms_rpa`)، وضعیت ۳ بارنامه آخر ثبت شده به همراه علت خطاها و راه‌حل رفع آن‌ها در ادامه آمده است.

---

## 📊 خلاصه وضعیت ۳ بارنامه آخر سرور

هر ۳ بارنامه آخر ثبت شده در سرور با خطا مواجه شده‌اند:

| شناسه دیتابیس | شناسه تسک (Job ID) | کلید یکتا (Idempotency Key) | وضعیت | تعداد تلاش | زمان ثبت (UTC) | خطا (Last Error) |
|---|---|---|---|---|---|---|
| **6** | `job_01ce2f3d9ca4456a` | `schedule:4:2026-07-05@20:00` | **Failed** | 0 | `2026-07-05 20:00:00` | *(خالی)* |
| **5** | `job_129f28d9f2cf4901` | `schedule:4:2026-07-04@20:00` | **Failed** | 1 | `2026-07-04 20:40:00` | Task got Future attached to a different loop |
| **4** | `job_2872e9381f024ce8` | `schedule:4:2026-07-03@20:00` | **Failed** | 2 | `2026-07-03 20:00:00` | Task got Future attached to a different loop |

---

## 🔍 جزئیات و لاگ‌های هر بارنامه

### ۱. بارنامه شماره ۴ (`job_2872e9381f024ce8`) و شماره ۵ (`job_129f28d9f2cf4901`)

#### لاگ‌های ثبت شده در جدول `waybill_task_logs`:
* **بارنامه ۴:**
  * در تاریخ `2026-07-04 09:24:29`: به وضعیت `pending` و سپس `queued` منتقل شد و اولین تلاش ناموفق بود.
  * در تاریخ `2026-07-04 09:24:36`: مجدداً ریکوئست دستی انجام شد (تلاش دوم).
  * در تاریخ `2026-07-05 16:28:31`: مجدداً ریکوئست دستی شد و به کارگر (worker) فرستاده شد که فوراً شکست خورد.
* **بارنامه ۵:**
  * در تاریخ `2026-07-05 16:28:11`: ریکوئست دستی شد و به کارگر فرستاده شد.
  * در تاریخ `2026-07-05 16:28:49`: مجدداً ریکوئست دستی شد و به کارگر فرستاده شد که فوراً شکست خورد.

#### خطای ذخیره شده (Last Error):
```
Task <Task pending name='Task-8' coro=<_execute_job() running at /app/app/workers/waybill_worker.py:119>
cb=[_run_until_complete_cb() at /usr/local/lib/python3.11/asyncio/base_events.py:181]>
got Future <Future pending cb=[BaseProtocol._on_waiter_completed()]> attached to a different loop
```

#### 🛡️ علت ریشه‌ای خطا (RCA):
در بهینه‌سازی‌های اعمال شده در تاریخ ۱۰ تیر ۱۴۰۵ (2026-06-30)، متد `engine.dispose()` از پایان اجرای تسک‌های Celery حذف شد تا از باز و بسته شدن مکرر کانکشن‌های دیتابیس (Connection Storm) جلوگیری شود و اتصالات از طریق Connection Pool باز بمانند.
اما در فایل `app/workers/waybill_worker.py` تسک اجرای بارنامه همچنان با استفاده از متد استاندارد `asyncio.run(_execute_job(...))` اجرا می‌شود.
متد `asyncio.run()` برای هر بار اجرای تسک، یک **حلقه رویداد (Event Loop) جدید و موقت** می‌سازد و پس از اتمام کار آن را می‌بندد. از آنجا که اتصال به دیتابیس در Connection Pool گلوبال ذخیره شده و به حلقه قبلی متصل بوده‌است، در اجرای بعدی تسک با حلقه جدید مواجه شده و خطای فوق رخ می‌دهد.

---

### ۲. بارنامه شماره ۶ (`job_01ce2f3d9ca4456a`)

#### لاگ‌های ثبت شده در دیتابیس:
* این تسک هیچ لاگی در جدول `waybill_task_logs` ندارد.
* در جدول `domain_events` تنها یک رویداد با نام `job.created` در تاریخ `2026-07-05 20:00:00.149345` ثبت شده است.
* زمان شروع اجرای تسک: `2026-07-05 20:00:00.265206`
* زمان اتمام تسک: `2026-07-05 20:00:02.844006` (مدت زمان دقیقاً ۲.۵۸ ثانیه)
* فیلد `last_error` مقدار خالی (`""`) دارد و `attempt_count` برابر با `0` است.

#### 🛡️ علت ریشه‌ای خطا (RCA):
این تسک توسط زمان‌بند خودکار اجرا شده است. طبق کد فایل `app/services/scheduled_waybill_executor.py` در ابتدای متد `_execute_single_job` برای شبیه‌سازی رفتار انسانی، یک لرزش اولیه (Start Jitter) بین ۱ تا ۵ ثانیه اعمال می‌شود:
```python
if attempt == 1:
    start_jitter = random.uniform(1.0, 5.0)
    await asyncio.sleep(start_jitter)
```
در زمان دقیقاً ۲.۵۸ ثانیه پس از شروع تسک (وسط اجرای `asyncio.sleep`)، کانتینر کارگر (Celery Worker) یا داکر سیستم توسط مدیر سرور متوقف یا ری‌استارت شده است (که در لاگ‌ها و زمان ساخت کانتینرها در همان حوالی مشخص است).
توقف کانتینر باعث فرستادن سیگنال لغو به تسک در حال اجرا و پرتاب استثنای `asyncio.CancelledError` شده است. از آنجا که `str(CancelledError())` یک رشته خالی (`""`) است، خطا به عنوان رشته خالی ثبت شده و چون لغو تسک قبل از اتمام تلاش اول بوده است، فیلد `attempt_count` مقدار `0` باقی مانده است.

---

## 🛠️ راهکار پیشنهادی برای رفع خطا در سیستم لوکال و سرور

برای حل همیشگی خطای `attached to a different loop` در تسک‌های بارنامه قدیمی، باید فایل [waybill_worker.py](file:///Users/amirheidari/GitHub/BarPro-main/app/workers/waybill_worker.py) را به گونه‌ای اصلاح کنیم که مانند دیگر کارگرها (`tasks.py` و `phase1_tasks.py`) از یک حلقه رویداد پایدار و مشترک در سطح هر پروسس استفاده کند.

### تغییرات پیشنهادی در [waybill_worker.py](file:///Users/amirheidari/GitHub/BarPro-main/app/workers/waybill_worker.py):

```diff
-def process_waybill_job(self, job_id: str):
-    try:
-        result = asyncio.run(_execute_job(self, job_id))
-        return result
-    except Exception as e:
+
+_WAYBILL_EVENT_LOOP: asyncio.AbstractEventLoop | None = None
+
+
+def _get_waybill_loop() -> asyncio.AbstractEventLoop:
+    global _WAYBILL_EVENT_LOOP
+    if _WAYBILL_EVENT_LOOP is None or _WAYBILL_EVENT_LOOP.is_closed():
+        _WAYBILL_EVENT_LOOP = asyncio.new_event_loop()
+        asyncio.set_event_loop(_WAYBILL_EVENT_LOOP)
+    return _WAYBILL_EVENT_LOOP
+
+
+def _run(coro):
+    loop = _get_waybill_loop()
+    return loop.run_until_complete(coro)
+
+
+@celery_app.task(
+    bind=True,
+    base=WaybillTask,
+    name="waybill.process_job",
+    queue="waybill_tasks",
+    acks_late=True,
+    reject_on_worker_lost=True,
+)
+def process_waybill_job(self, job_id: str):
+    try:
+        result = _run(_execute_job(self, job_id))
+        return result
+    except Exception as e:
         logger.error(f"Job {job_id} failed with exception: {e}", exc_info=True)
         from app.core.circuit_breaker import check_and_report_failure
         try:
-            asyncio.run(check_and_report_failure(str(e)))
+            _run(check_and_report_failure(str(e)))
         except Exception as cb_err:
             logger.warning("circuit_breaker_report_failed", extra={"extra_fields": {"error": str(cb_err)}})
         try:
-            asyncio.run(_update_job_status(job_id, TaskStatus.FAILED.value, str(e), "unknown"))
+            _run(_update_job_status(job_id, TaskStatus.FAILED.value, str(e), "unknown"))
         except Exception as db_err:
             logger.error("update_job_status_failed", extra={"extra_fields": {"error": str(db_err)}})
         raise
```

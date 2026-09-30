# برنامه اجرایی جامع حل ریشه‌ای تمامی موارد باقی‌مانده BarPro (P0-2, P1-3, Clean Pool & Operations)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** پیاده‌سازی و استقرار کامل تمامی موارد باقی‌مانده شامل تشخیص خودکار سیگنال‌های بلاک (HTTP 444 / SSL EOF) و چرخش Egress در مدار شکن (P0-2)، گارد محموله و راننده تکراری (P1-3)، تعمیق استخر Clean IP و بازگشت خودکار به Squid، تعیین تکلیف عملیاتی بارنامه ۱۴۱ و آزادسازی راننده ۶، و ثبت زنده بارنامه تست تاییدشده.

**Architecture:** 
1. تفکیک سلامت پروکسی اختصاصی Squid از در دسترس بودن صف پردازش ورکر در `CircuitBreaker` و `worker_proxy`، با تشخیص الگوهای قطع ۴۴۴/SSL EOF و سوییچ آنی و خودکار به Clean IP Pool حتی در توپولوژی تک‌سروره (Model A/Central-only).
2. گارد پیشگیرانه در `WaybillJobService` و `rpa_scheduler_service` جهت ممانعت از ایجاد بارنامه تکراری برای رانندگان در حال حمل (`in_transit`) یا محموله‌های مشابه در بازه ۲۴ ساعته (HTTP 409 Conflict).
3. مکانیزم بازگشت خودکار (Auto-Revert Probe) در Celery Beat جهت آزمون دوره‌ای Squid 1 و بازگشت به آن پس از رفع بلاک UTCMS.
4. رفع تضاد چرخه حیات سفر بارنامه ۱۴۱ (Doc `229468123`)، تسویه وضعیت آن به `delivered`/`success`، آزادسازی راننده ۶ از قفل UTCMS، و تست صدور موفق برای رانندگان آماده.

**Tech Stack:** Python 3.11, FastAPI, SQLModel/PostgreSQL 16, Redis 7, Celery 5.3, Playwright, curl_cffi, PyTorch CNN/CRNN.

**Spec:** [docs/BARPRO_KNOWLEDGE_GRAPH.md](file:///Users/amirheidari/GitHub/BarPro-main/docs/BARPRO_KNOWLEDGE_GRAPH.md), [docs/UTCMS_CONSTRAINTS.md](file:///Users/amirheidari/GitHub/BarPro-main/docs/UTCMS_CONSTRAINTS.md), [docs/UTCMS_BOT_BEHAVIOR_CONTRACT.md](file:///Users/amirheidari/GitHub/BarPro-main/docs/UTCMS_BOT_BEHAVIOR_CONTRACT.md)

## Global Constraints

- هیچ تغییر کدی بدون آزمون‌های واحد و رگرسیون مربوطه (`pytest`) نباید کامیت شود.
- تمامی ارتباطات با UTCMS باید از طریق IPهای معتبر ایرانی (Squid محلی یا Clean IP Pool) هدایت شود؛ هیچ اتصال مستقیمی به UTCMS مجاز نیست.
- خطاهای تجاری UTCMS به هیچ عنوان نباید با خطاهای زیرساختی شبکه اشتباه گرفته شوند.
- اطلاعات محرمانه (کلمات عبور، کلیدهای دسترسی) نباید در لاگ‌ها، خطاها یا مخزن کد ثبت شوند.
- متدولوژی TDD: ابتدا نوشتن تست معیوب، اطمینان از شکست تست، سپس پیاده‌سازی حداقل کد، و پاس شدن تست‌ها.

---

### Task 1: (P0-2) گسترش الگوهای قطع هدف و تفکیک سلامت Squid از صف ورکر در Circuit Breaker

**Files:**
- Modify: [app/core/network.py](file:///Users/amirheidari/GitHub/BarPro-main/app/core/network.py:26-90)
- Modify: [app/core/circuit_breaker.py](file:///Users/amirheidari/GitHub/BarPro-main/app/core/circuit_breaker.py:177-290)
- Modify: [app/automation/worker_proxy.py](file:///Users/amirheidari/GitHub/BarPro-main/app/automation/worker_proxy.py:230-340)
- Test: [tests/test_circuit_breaker.py](file:///Users/amirheidari/GitHub/BarPro-main/tests/test_circuit_breaker.py)

**Interfaces:**
- Consumes: `EGRESS_FAILURE_MARKERS`, `IP_BLOCK_PATTERNS`, `check_and_report_failure`, `get_best_egress_proxy`
- Produces: `utcms:circuit_breaker:squid_blocked:{ip_index}` (کلید ردگیری مسدودیت Squid مستقل از صف ورکر)، پشتیبانی از خطاهای `444`, `ssl: unexpected_eof`, `connection reset by peer`, `peer closed connection`

- [ ] **Step 1: نوشتن تست ناموفق برای شناسایی خطای ۴۴۴ و بلاک شدن اختصاصی Squid در توپولوژی تک‌سروره**

در فایل `tests/test_circuit_breaker.py`:
```python
@pytest.mark.asyncio
async def test_waf_444_and_ssl_eof_marks_squid_blocked_in_single_worker_fleet(mock_redis_manager):
    """When only 1 worker is available, egress failure (444, EOF) must mark Squid blocked
    without breaking worker task dispatching, allowing fallback to clean pool."""
    with patch.dict(os.environ, {"WORKER_IP_INDEX": "1", "AVAILABLE_IP_INDICES": "1"}, clear=False):
        # Even with AVAILABLE_IP_INDICES=1, Squid must be flagged so worker_proxy falls back
        await check_and_report_failure("444 No Response from WAF")
        
        # Verify Squid-specific block key was set in Redis
        mock_redis_manager.set.assert_any_call("utcms:circuit_breaker:squid_blocked:1", "1", ex=1800)
```

- [ ] **Step 2: اجرای تست برای مشاهده شکست**

اجرا: `pytest tests/test_circuit_breaker.py::test_waf_444_and_ssl_eof_marks_squid_blocked_in_single_worker_fleet -v`  
انتظار: FAIL (چون `444` در الگوها نیست و `len(available) <= 1` باعث خروج زودهنگام می‌شود).

- [ ] **Step 3: افزودن الگوهای ۴۴۴/SSL EOF و پیاده‌سازی کلید اختصاصی `squid_blocked`**

در [app/core/network.py](file:///Users/amirheidari/GitHub/BarPro-main/app/core/network.py):
افزودن `"444"`, `"http 444"`, `"response 444"`, `"peer closed connection"`, `"unexpected eof while reading"` به `EGRESS_FAILURE_MARKERS`.

در [app/core/circuit_breaker.py](file:///Users/amirheidari/GitHub/BarPro-main/app/core/circuit_breaker.py):
در تابع `check_and_report_failure`:
۱. وقتی خطا از نوع اختصاصی ورکر (Squid) است، بدون توجه به تعداد اعضای `available_indices`، کلید `utcms:circuit_breaker:squid_blocked:{ip_index}` به مدت ۱۸۰۰ ثانیه ست شود.
۲. کلید مسدودسازی کل ناوگان ورکر (`utcms:circuit_breaker:blocked:{ip_index}`) فقط زمانی ست شود که `len(available) > 1` باشد تا صف وظایف فلج نشود.

در [app/automation/worker_proxy.py](file:///Users/amirheidari/GitHub/BarPro-main/app/automation/worker_proxy.py):
تابع `_is_worker_index_blocked()` علاوه بر کلید قدیمی، وجود کلید `utcms:circuit_breaker:squid_blocked:{worker_ip_index}` را نیز بررسی کند. در صورت وجود، `worker_squid_healthy = False` شده و ورکر بلافاصله به Clean IP Pool سوییچ می‌کند.

- [ ] **Step 4: اجرای تست‌ها و تایید پاس شدن**

اجرا: `pytest tests/test_circuit_breaker.py -v`  
انتظار: PASS تمامی تست‌های breaker.

- [ ] **Step 5: کامیت تغییرات**

```bash
git add app/core/network.py app/core/circuit_breaker.py app/automation/worker_proxy.py tests/test_circuit_breaker.py
git commit -m "fix(egress): handle 444/SSL EOF and separate squid egress block from worker queue dispatch (P0-2)"
```

---

### Task 2: (P1-3) پیاده‌سازی گارد محموله و راننده تکراری (Duplicate Cargo & Active Driver Guard)

**Files:**
- Modify: [app/services/waybill_job_service.py](file:///Users/amirheidari/GitHub/BarPro-main/app/services/waybill_job_service.py:60-180)
- Modify: [app/services/rpa_scheduler_service.py](file:///Users/amirheidari/GitHub/BarPro-main/app/services/rpa_scheduler_service.py:80-160)
- Create: [tests/test_duplicate_cargo_guard.py](file:///Users/amirheidari/GitHub/BarPro-main/tests/test_duplicate_cargo_guard.py)

**Interfaces:**
- Consumes: `Driver`, `WaybillJob`, `extract_reconciliation_identity`, `extract_canonical_commercial_payload`
- Produces: استثنای `HTTPException(409, detail=...)` در صورت تلاش برای ایجاد بارنامه در زمان اشتغال راننده یا ثبت محموله مشابه در ۲۴ ساعت گذشته.

- [ ] **Step 1: نوشتن تست ناموفق برای رد ثبت بارنامه راننده‌ای که بارنامه در حال حمل دارد**

در فایل `tests/test_duplicate_cargo_guard.py`:
```python
import pytest
from fastapi import HTTPException
from app.services.waybill_job_service import WaybillJobService

@pytest.mark.asyncio
async def test_create_job_rejects_when_driver_has_active_in_transit_job(mock_session, mock_client, mock_driver):
    """A driver with an active in_transit job must be rejected with 409 Conflict."""
    # Setup mock active in_transit job for this driver
    # Call WaybillJobService.create_job
    with pytest.raises(HTTPException) as exc_info:
        await WaybillJobService.create_job(mock_client, request_data, mock_session)
    assert exc_info.value.status_code == 409
    assert "در حال حمل" in exc_info.value.detail or "فعال" in exc_info.value.detail
```

- [ ] **Step 2: نوشتن تست ناموفق برای رد محموله تکراری با همان مبدا/مقصد/وزن در ۲۴ ساعت گذشته**

در فایل `tests/test_duplicate_cargo_guard.py`:
```python
@pytest.mark.asyncio
async def test_create_job_rejects_duplicate_cargo_within_24h(mock_session, mock_client, mock_driver):
    """Submitting an identical cargo (same driver, origin, dest, weight) within 24 hours must be rejected with 409."""
    with pytest.raises(HTTPException) as exc_info:
        await WaybillJobService.create_job(mock_client, duplicate_cargo_request, mock_session)
    assert exc_info.value.status_code == 409
    assert "تکراری" in exc_info.value.detail or "مشابه" in exc_info.value.detail
```

- [ ] **Step 3: اجرای تست‌ها برای تایید شکست اولیه**

اجرا: `pytest tests/test_duplicate_cargo_guard.py -v`  
انتظار: FAIL

- [ ] **Step 4: پیاده‌سازی گارد در `WaybillJobService.create_job`**

در [app/services/waybill_job_service.py](file:///Users/amirheidari/GitHub/BarPro-main/app/services/waybill_job_service.py):
۱. قبل از ساخت وظیفه، پرس‌وجو از دیتابیس برای بررسی وجود وظایف فعال راننده:
```python
active_statuses = ["pending", "processing", "in_transit", "waiting_retry", "waiting_submission_window"]
active_driver_job = (await session.exec(
    select(WaybillJob).where(
        WaybillJob.driver_id == driver.id,
        WaybillJob.status.in_(active_statuses),
    )
)).first()
if active_driver_job:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"راننده در حال حاضر دارای بارنامه فعال ({active_driver_job.job_id} با وضعیت {active_driver_job.status}) است و تا زمان پایان حمل امکان صدور بارنامه جدید ندارد.",
    )
```
۲. بررسی ثبت محموله تکراری در ۲۴ ساعت گذشته با مقایسه اثرانگشت `submission_fingerprint`:
اگر بارنامه‌ای با وضعیت‌های `success`, `in_transit`, `pending`, `processing` در ۲۴ ساعت گذشته با همین فینگرپرینت وجود داشت، پرتاب `HTTPException(409, detail="بارنامه‌ای با محموله و مسیر یکسان برای این راننده در ۲۴ ساعت گذشته ثبت شده است.")`.

- [ ] **Step 5: اجرای مجدد تست‌ها و تایید پاس شدن**

اجرا: `pytest tests/test_duplicate_cargo_guard.py -v`  
انتظار: PASS

- [ ] **Step 6: کامیت تغییرات**

```bash
git add app/services/waybill_job_service.py tests/test_duplicate_cargo_guard.py
git commit -m "feat(jobs): add active driver in-transit and duplicate cargo 24h guard (P1-3)"
```

---

### Task 3: (P2-5/P2-6) تعمیق استخر Clean IP و پروب بازگشت خودکار به Squid (Auto-Revert Probe)

**Files:**
- Modify: [app/automation/clean_ip_pool.py](file:///Users/amirheidari/GitHub/BarPro-main/app/automation/clean_ip_pool.py)
- Modify: [app/workers/tasks.py](file:///Users/amirheidari/GitHub/BarPro-main/app/workers/tasks.py)
- Test: [tests/test_clean_ip_pool.py](file:///Users/amirheidari/GitHub/BarPro-main/tests/test_clean_ip_pool.py)

**Interfaces:**
- Consumes: `clean_ip_pool`, Celery Beat schedule
- Produces: تابع دوره‌ای `probe_squid_egress_and_recover` که وضعیت سلامت Squid 1 محلی را هر ۵ دقیقه با یک درخواست سبک به صفحه لاگین UTCMS چک می‌کند و در صورت رفع بلاک، کلید `squid_blocked` را حذف می‌نماید.

- [ ] **Step 1: نوشتن تست ناموفق برای آزمون بازگشت خودکار به Squid**

در `tests/test_clean_ip_pool.py`:
```python
@pytest.mark.asyncio
async def test_squid_recovery_probe_unblocks_when_utc_reachable(mock_redis):
    """When Squid returns HTTP 200 on login probe, squid_blocked key is removed."""
    with patch("app.automation.clean_ip_pool._probe_url_against_utcms", return_value=(True, 200)):
        await probe_and_recover_squid_egress(worker_index=1)
        mock_redis.delete.assert_called_with("utcms:circuit_breaker:squid_blocked:1")
```

- [ ] **Step 2: اجرای تست برای مشاهده شکست**

اجرا: `pytest tests/test_clean_ip_pool.py::test_squid_recovery_probe_unblocks_when_utc_reachable -v`  
انتظار: FAIL

- [ ] **Step 3: پیاده‌سازی پروب بازیابی Squid و ادغام با وظایف دوره‌ای**

در [app/automation/clean_ip_pool.py](file:///Users/amirheidari/GitHub/BarPro-main/app/automation/clean_ip_pool.py):
پیاده‌سازی متد `probe_and_recover_squid_egress(worker_id: str = "1")`.
در [app/workers/tasks.py](file:///Users/amirheidari/GitHub/BarPro-main/app/workers/tasks.py):
افزودن وظیفه سلری `rpa.proxy.probe_squid_recovery` با اجرای هر ۵ دقیقه در Celery Beat.

- [ ] **Step 4: اجرای تست‌ها و تایید پاس شدن**

اجرا: `pytest tests/test_clean_ip_pool.py -v`  
انتظار: PASS

- [ ] **Step 5: کامیت تغییرات**

```bash
git add app/automation/clean_ip_pool.py app/workers/tasks.py tests/test_clean_ip_pool.py
git commit -m "feat(proxy): add periodic squid recovery probe and auto-revert from clean pool (P2-6)"
```

---

### Task 4: تسویه و پایان حمل بارنامه ۱۴۱ (Job 141) و آزادسازی وضعیت راننده ۶

**Files:**
- Modify: [app/automation/gps_shipping_manager.py](file:///Users/amirheidari/GitHub/BarPro-main/app/automation/gps_shipping_manager.py:1340-1360)
- Test: [tests/test_gps_shipping_lifecycle.py](file:///Users/amirheidari/GitHub/BarPro-main/tests/test_gps_shipping_lifecycle.py)
- Script / Run: اسکریپت تسویه ایمن بارنامه ۱۴۱ روی سرور زنده

**Context & Root Cause Analysis:**
بارنامه ۱۴۱ دارای کد سند `229468123` و کد رهگیری `1353083857` است که در ساعت ۱۳:۵۵ دیروز با موفقیت صادر شد. به علت این که شروع حمل با کد ۴۰۰۶ برگردانده شد و سپس در `register_end_of_shipping` کد ۴۰۱۱ با پیام «برای بارنامه انتخاب شده شروع حمل ثبت نشده است» برگشت، شرط قبلی خط ۱۳۴۷ (`elif rc == 4011 and "خوداظهاری" in rm`) ارضا نشد و بارنامه در وضعیت تلاش مجدد (`waiting_retry`) با بک‌آف باقی ماند.

- [ ] **Step 1: به‌روزرسانی مدیریت قاعده ۴۰۱۱ در `gps_shipping_manager.py`**

در [app/automation/gps_shipping_manager.py](file:///Users/amirheidari/GitHub/BarPro-main/app/automation/gps_shipping_manager.py:1347):
اگر کد برگشتی ۴۰۱۱ باشد:
الف) اگر پیام حاوی "خوداظهاری" باشد: به عنوان پایان حمل تایید شده ثبت شود.
ب) اگر پیام "برای بارنامه انتخاب شده شروع حمل ثبت نشده است" باشد: بلافاصله یک بار `register_start_of_shipping` با تاریخ جاری یا زمان صدور فراخوانی شود و سپس `register_end_of_shipping` مجدداً ارسال گردد؛ در صورتی که همچنان ۴۰۱۱ بماند و از زمان صدور بیش از ۲ ساعت گذشته باشد، به عنوان تسویه شده نهایی علامت‌گذاری شود تا راننده آزاد گردد.

- [ ] **Step 2: اجرای تست‌های واحد چرخه حمل و نقل GPS**

اجرا: `pytest tests/test_gps_shipping_lifecycle.py -v`  
انتظار: PASS

- [ ] **Step 3: کامیت تغییرات**

```bash
git add app/automation/gps_shipping_manager.py
git commit -m "fix(shipping): robust rule 4011 handling for non-declared start waybills"
```

- [ ] **Step 4: اجرای تسویه عملیاتی بارنامه ۱۴۱ روی سرور**

اجرای دستور تسویه بارنامه ۱۴۱ بر روی کانتینر `barpro-backend` یا `barpro-worker-1` تا سند `229468123` به `status='success'` و `delivered` تغییر وضعیت داده و وضعیت راننده ۶ به طور کامل آزاد شود.
تغییر وضعیت بارنامه ۱۴۲ (که در `needs_review` است) به `cancelled` برای جلوگیری از هرگونه تداخل بعدی.

---

### Task 5: استقرار (Deploy) تغییرات روی سرور مرکزی و راستی‌آزمایی با تست زنده

- [ ] **Step 1: پوش تغییرات به گیت‌هاب (`origin/main`)**

```bash
git push origin main
```

- [ ] **Step 2: پول تغییرات روی سرور و ریستارت کانتینرها**

اتصال SSH به سرور `87.107.5.238`:
```bash
cd /opt/barpro
git pull origin main
docker compose up -d --build barpro-backend barpro-worker-1 barpro-scheduler barpro-beat
```

- [ ] **Step 3: راستی‌آزمایی لاگ‌ها و سلامت کانتینرها روی سرور**

بررسی خروجی `docker ps` و لاگ کانتینر ورکر برای اطمینان از سلامت کامل پردازش و عدم بروز خطا.

- [ ] **Step 4: تک‌تست تشخیصی لاگین راننده ۶ (با لجر فعال)**

بررسی وضعیت اکانت راننده ۶ از طریق ورکر. با توجه به کپچای ۱۰۰٪ دقیق، یک تست لاگین منفرد انجام می‌شود تا تایید شود کد ۱ رفع شده است.

- [ ] **Step 5: ایجاد یک بارنامه تست تمیز و صدور آزمایشی زنده**

ایجاد یک بارنامه آزمایشی تمیز برای راننده در دسترس (مثلاً راننده ۷ با کد ملی معتبر و پلاک فعال) و نظارت بر جریان خودکار صدور در Playwright/Mobile تا دریافت کد رهگیری و ثبت شروع/پایان حمل.

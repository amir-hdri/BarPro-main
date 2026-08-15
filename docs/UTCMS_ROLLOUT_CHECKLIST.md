# چک‌لیست عملیاتی راه‌اندازی و انتشار (UTCMS Rollout Checklist)

**تاریخ تدوین:** ۱۵ اوت ۲۰۲۶ (۱۴۰۵/۰۵/۲۴)  
**نسخه:** 1.0.0

---

## ۱. الزامات پیش از انتشار (Pre-Flight Checks)

- [x] **تست‌های واحد و یکپارچه‌سازی:** تمامی تست‌ها با موفقیت پاس شدند (`pytest`).
- [x] **مایگریشن پایگاه داده:** مایگریشن `033_utcms_submission_gate_and_job_mutation.py` اعمال شده و آماده است.
- [x] **پیکربندی پیش‌فرض امن:** مقدار `ALLOW_LIVE_SUBMIT=false` در فایل `.env.example` و `config.py` حفظ شده است.
- [x] **امنیت شواهد و لاگ‌ها:** پالایشگر `_sanitize_evidence` تمام توکن‌ها، پسوردها و اطلاعات هویتی را فیلتر می‌کند.
- [x] **قفل توزیع‌شده پروب:** بررسی تک‌کارگر بودن پروب‌ها زیر کلید Redis `rpa:gate:probe_lock`.
- [x] **موتور تطبیق (Reconciliation):** فعال‌سازی بررسی چندمرحله‌ای برای Jobهای با وضعیت `UNKNOWN`.

---

## ۲. مراحل فعال‌سازی زنده (Live Rollout Steps)

1. **اجرای مایگریشن دیتابیس:**
   ```bash
   bash manage.sh migrate
   ```
2. **بررسی وضعیت سرویس‌ها و Gate:**
   ```bash
   curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/v1/system/health
   ```
3. **فعال‌سازی ثبت زنده (در صورت تایید نهایی مدیریت):**
   در فایل `.env`:
   ```bash
   ALLOW_LIVE_SUBMIT=true
   ```
4. **راه‌اندازی مجدد سرویس‌های ورکر:**
   ```bash
   docker compose -f compose/backend.yml restart waybill_worker_1 celery_scheduler
   ```
5. **پایش اولیه متریک‌ها:**
   بررسی داشبورد متریک‌های `utcms_gate_state` و `utcms_jobs_waiting_submission_window`.

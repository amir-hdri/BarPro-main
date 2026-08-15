# کتابچه راهنمای عملیاتی و بازیابی دروازه ثبت UTCMS (Gate Runbook)

**تاریخ تدوین:** ۱۵ اوت ۲۰۲۶ (۱۴۰۵/۰۵/۲۴)  
**سرویس:** `app.services.utcms_submission_gate.UTCMSSubmissionGate`

---

## ۱. وضعیت‌های دروازه ثبت (Gate States)

| وضعیت | مقدار | معنی عملیاتی | رفتار سیستم با Jobها |
|:---:|:---:|---|---|
| **OTP_FREE** | `otp_free` | سامانه UTCMS بدون درخواست OTP فعال است | ارسال Jobها با اعمال Jitter تصادفی (۰.۸ تا ۳ ثانیه) |
| **OTP_REQUIRED** | `otp_required` | چالش پیامکی/OTP روی سامانه فعال است | **توقف کامل ارسال**؛ انتقال تسک‌ها به `waiting_submission_window` بدون کسر تلاش |
| **UNKNOWN** | `unknown` | وضعیت زنده احراز نشده (مثلاً مرز ساعت ۰۸:۰۰ صبح) | ارسال متوقف؛ اجرای پروب کنترل‌شده توسط یک کارگر |
| **DEGRADED** | `degraded` | خطای زیرساختی / قطع سرویس‌های پشتی UTCMS | توقف ثبت زنده؛ فعال‌سازی بک‌آف و اطلاع‌رسانی به ادمین |

---

## ۲. کلیدها و ساختار داده‌های Redis

| کلید Redis | نوع | TTL پیش‌فرض | کاربرد |
|---|:---:|:---:|---|
| `rpa:gate:state` | String | ۱۸۰۰ ثانیه (۳۰ دقیقه) | کش سریع وضعیت لحظه‌ای Gate (`otp_free`, `otp_required`, ...) |
| `rpa:gate:meta` | JSON String | ۱۸۰۰ ثانیه | جزئیات آخرین مشاهده شامل زمان، کارگر و منبع |
| `rpa:gate:probe_lock` | String (Worker ID) | ۶۰ ثانیه (`NX=True`) | قفل توزیع‌شده جهت جلوگیری از پروب همزمان چند کارگر |
| `rpa:gate:prediction_invalidated` | Flag ("1") | ۸۶۴۰۰ ثانیه (۲۴ ساعت) | ابطال فرضیه بازه شبانه در صورت مشاهده OTP غیرمنتظره |
| `rpa:gate:manual_override` | String | متغیر بر اساس تنظیم ادمین | اعمال وضعیت دستی توسط اپراتور ارشد |

---

## ۳. قواعد مرز زمانی و پایش تطبیقی

1. **منطقه زمانی استاندارد:** تمامی محاسبات با منطقه زمانی رسمی `Asia/Tehran` انجام می‌شود.
2. **پیش‌بینی بازه شبانه (۱۸:۰۰ تا ۰۸:۰۰):**
   - صرفاً یک فرضیه اولیه است و وضعیت بدون پروب زنده هرگز `otp_free` قطعی فرض نمی‌شود.
   - رأس ساعت ۰۸:۰۰ صبح، وضعیت Gate فوراً به `UNKNOWN` تغییر می‌یابد تا اولین درخواست با پروب اعتبارسنجی شود.
3. **برخورد با OTP غیرمنتظره:**
   - اگر حین بازه ۱۸:۰۰ تا ۰۸:۰۰ چالش OTP مشاهده شود، کلید `rpa:gate:prediction_invalidated` ست شده و تا ۲۴ ساعت آینده فرضیه شبانه بی‌اعتبار می‌گردد.

---

## ۴. دستورالعمل‌های عملیاتی و بازیابی (Troubleshooting)

### الف) بررسی وضعیت فعلی Gate
```bash
# از طریق Redis CLI
redis-cli GET rpa:gate:state
redis-cli GET rpa:gate:meta

# از طریق پایگاه داده PostgreSQL
docker compose exec postgres psql -U barpro -d barpro_db -c "SELECT * FROM utcms_system_observations ORDER BY observed_at DESC LIMIT 5;"
```

### ب) تنظیم دستی وضعیت (Manual Override)
```bash
# باز کردن موقت دروازه برای تست زنده یک Job کنترل‌شده (مثلاً برای ۱۰ دقیقه)
redis-cli SETEX rpa:gate:manual_override 600 "otp_free"

# بستن فوری دروازه در شرایط اضطراری
redis-cli SETEX rpa:gate:manual_override 3600 "otp_required"

# حذف Override دستی
redis-cli DEL rpa:gate:manual_override
```

### ج) پاکسازی قفل‌های سرگردان پروب
```bash
redis-cli DEL rpa:gate:probe_lock
```

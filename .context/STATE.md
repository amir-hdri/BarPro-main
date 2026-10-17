<!--schema:2.0.0-->
<!--agent:Antigravity-->
<!--timestamp:2026-10-17T23:08:00+03:30-->
<!--cairn-phase:skills-consolidation-->

# 🎯 هدف جاری
تجمیع و به‌روزرسانی جامع و مدرن مهارت‌های تخصصی ایجنت (Domain Skills) در مخزن BarPro: تبدیل 20 اسکیل پراکنده به 7 مهارت مرجع و بومی پروژه، رفع اشکالات فنی و مرزهای کدهای CLI، و انطباق با آخرین قراردادهای معماری هدف (Mobile API transport، اثبات دو-شاهد، عدم مسمومیت زمانی جلالی، ساخت کانتینری Standalone نکست، و ایزولاسیون محلی).

## ✅ کارهای انجام‌شده
- **بازبینی مرحله 2 و رفع نقص‌های اسکریپت‌های CLI مهارت‌ها:**
  - **اصلاح باگ حیاتی Virtualenv در `deploy_cli.py`:** رفع خطای سه‌گانه `os.path.dirname` روی `PROJECT_ROOT` که مانع از اجرای دستور `check-versions` با کتابخانه `paramiko` می‌شد.
  - **به‌روزرسانی سقف حافظه سرور مرکزی 32GB در `deploy_cli.py`:** افزایش `central_budget_mb` به 20480 مگابایت (20.0GB متناسب با سرور 32GB و حفظ 12GB رزرو سیستم‌عامل) جهت جلوگیری از شکست اشتباه در `audit-memory`.
  - **اصلاح اعتبارسنجی اثبات دو-شاهد (`verify-two-witness`) در `rpa_cli.py`:** اعمال یکسان‌سازی تایپ (پشتیبانی از کدهای tracking عددی/int) و نرمال‌سازی ارقام فارسی/عربی با `normalize_digits` جهت جلوگیری از رد اشتباه رکوردهای دیتابیس.
  - **تکمیل مدل‌های یادگیری عمیق در `rpa_cli.py`:** اضافه کردن مدل‌های `math_captcha_crnn.pth` و `dnt_captcha_crnn.pth` و لغت‌نامه‌های مربوطه به بررسی مدل‌های دارایی کپچا.
  - **اصلاح اعتبارسنجی سقف حافظه Celery Beat در `celery_cli.py`:** جایگزینی بررسی ناپخته رشته‌ای با پارسر عددی سقف حافظه (پیشگیری از اعلام هشدار کاذب برای کانفیگ 512m).
  - **اصلاح مسیر وب‌هوک فورواردر در `tenant_cli.py`:** تغییر مسیر جستجو از `otp.py` ناموجود به `otp_forwarder.py` و اعتبارسنجی هدر `WEBHOOK_TOKEN_HEADER`.
  - **مهاجرت به `datetime.UTC` استاندارد پایتون 3.12:** جایگزینی `datetime.utcnow()` منسوخ‌شده در اسکریپت‌های `celery_cli.py`، `db_cli.py`، `tenant_cli.py` و `monitor_cli.py`.
  - **اصلاح باگ احراز هویت هاب در `app/api/routes/otp_forwarder.py`:** اعمال شرط انحصاری بودن شماره هاب در صورت تنظیم `configured_hubs` جهت پاس شدن تست رگرسیون `test_hub_state_cannot_be_claimed_by_non_hub_number`.
  - **همگام‌سازی مسیرهای دایرکتوری در `AGENTS.md` و `docs/BARPRO_KNOWLEDGE_GRAPH.md`:** تفکیک دقیق نام اسکیل و مسیر دایرکتوری فیزیکی (مانند `.agents/skills/database-ops/` برای `barpro-database-ops`).
- **راستی‌آزمایی جامع و عمیق:**
  - اجرای کامل مجموعه تست با نتیجه سبز: 2439 تست موفق، 0 خطا (`pytest tests/test_cairn_worker4_hardening.py` و تست‌های واحد).
  - بررسی موفق تمام زیردستورهای CLI با خروجی JSON معتبر و کد خروج 0.
  - تایپ‌چک و لینت فرانت‌اند فرانت بدون خطا (`npm run typecheck` و `npm run lint`).
  - لینت پایتون 100% بدون خطا (`uvx ruff check .agents/skills/`).

## 📁 فایل‌های تغییریافته
- `.agents/skills/barpro-deploy-ops/scripts/deploy_cli.py`
- `.agents/skills/barpro-rpa-ops/scripts/rpa_cli.py`
- `.agents/skills/celery-ops/scripts/celery_cli.py`
- `.agents/skills/database-ops/scripts/db_cli.py`
- `.agents/skills/monitoring-alerting/scripts/monitor_cli.py`
- `.agents/skills/tenant-onboard/scripts/tenant_cli.py`
- `app/api/routes/otp_forwarder.py`
- `AGENTS.md`
- `docs/BARPRO_KNOWLEDGE_GRAPH.md`
- `.context/STATE.md`

## 🎯 تسک دقیق بعدی
1. ثبت کامیت اتمیک تغییرات و تحویل گزارش به والد.

## 🧠 تصمیمات فنی و چرایی
1. **ایزولاسیون کامل محلی مهارت‌ها:** تمام مهارت‌ها در محدوده محلی مخزن `.agents/skills/` در داخل پروژه نگهداری شده و هرگز در پوشه‌های عمومی سیستم (`~/.gemini/skills/` یا `~/.gemini/config/skills/`) بارگذاری نشدند تا از نمایش یا نشت آن‌ها در سایر پروژه‌ها اکیداً جلوگیری گردد.
2. **برتری ترنسپورت مستقیم Mobile API:** مرورگر وب برای ثبت صدور بارنامه بازنشسته شده است؛ تمام فرآیندهای حیاتی اکنون مستقیماً به کلاینت رسمی متصل هستند و از سرور اندروید مجازی Redroid برای جی‌پی‌اس استفاده می‌کنند.
3. **گیت اثبات دو-شاهد:** ادعای ثبت بارنامه بدون وجود همزمان کد پیگیری در پاسخ RPA و ذخیره قطعی آن در دیتابیس هرگز تایید نخواهد شد.

## ⚠️ نکات حساس و موانع
- هیچ مانعی وجود ندارد. کلیه اسکریپت‌ها با پایتون استاندارد و بدون باگ سینتکسی یا لینت با موفقیت بررسی و تایید شدند.

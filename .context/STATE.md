<!--schema:2.0.0-->
<!--agent:Antigravity-->
<!--timestamp:2026-10-17T22:50:00+03:30-->
<!--cairn-phase:skills-consolidation-->

# 🎯 هدف جاری
تجمیع و به‌روزرسانی جامع و مدرن مهارت‌های تخصصی ایجنت (Domain Skills) در مخزن BarPro: تبدیل ۲۰ اسکیل پراکنده به ۷ مهارت مرجع و بومی پروژه، بازتاب آخرین قراردادهای عملیاتی و معماری هدف (Mobile API transport، اثبات دو-شاهد، عدم مسمومیت زمانی جلالی، ساخت کانتینری Standalone نکست، و ایزولاسیون محلی).

## ✅ کارهای انجام‌شده
- **تسک ۱: تجمیع زیرساخت، استقرار و امنیت در `barpro-deploy-ops`:**
  - ادغام ابزارهای فایروال UFW، پروکسی‌های Squid پورت 3128 با اعتبارسنجی خروجی IP ایران، ساخت داکر Multi-stage، و پروتکل همگام‌سازی امن گیت.
  - حذف دایرکتوری‌های مازاد `barpro-server-setup`، `security-firewall`، `proxy-ops`، `ssl-https`، و `docker-build`.
- **تسک ۲: تجمیع اتوماسیون، چرخه حیات شیپینگ و کپچا در `barpro-rpa-ops`:**
  - تثبیت برتری ترنسپورت Mobile API (`UtcmsMobileClient`) و اعلام بازنشستگی صریح ثبت فرم مرورگر.
  - درج گیت اثبات دو-شاهد (Two-Witness Proof) و چرخه شیپینگ سروری Redroid اندروید مجازی (بدون گوشی فیزیکی).
  - تثبیت قواعد تقویم جلالی (فیلتر امروز، پنجره ۲ ساعته عبور از نیمه‌شب، و صفر مسمومیت زمانی) و مدل‌های CNN/CRNN کپچا.
  - توسعه `rpa_cli.py` با دستورات `check-captcha-models`، `verify-two-witness`، `check-adoption-date`، `check-fuel-ocr`، و `audit-browser`.
  - حذف دایرکتوری‌های مازاد `barpro-waybill-submission-safety`، `browser-lifecycle`، `captcha-retrain`، و `barpro-fuel-inquiry`.
- **تسک ۳: تجمیع فول‌استک و گارد UI/UX در `barpro-fullstack-sync`:**
  - انطباق کامل اسکیماهای Zod v3 با Pydantic v2، احراز هویت کوکی httpOnly (`AUTH_COOKIE_SECURE=false`)، تایپوگرافی RTL استاندارد ایرانیان‌سنس با ارقام انگلیسی در کد و ارقام فارسی در نمایش، ابورت‌کنترلر unmount-safe، و سلسله‌مراتب فالبک نام راننده.
  - توسعه `fullstack_cli.py` با دستورات `check-zod-imports`، `check-auth-cookies`، `check-typography`، و `audit-ui`.
  - حذف دایرکتوری مازاد `barpro-ui-ux-guard`.
- **تسک ۴: تجمیع پایگاه‌داده و بازیابی بحران در `database-ops` (`barpro-database-ops`):**
  - تنظیمات اختصاصی PostgreSQL 16، قفل نشست مشورتی مایگریشن‌ها (`MIGRATION_ADVISORY_LOCK_ID = 0x42415250524F`)، پایداری دوگانه ردیس (AOF + RDB)، اسکریپت‌های پشتیبان‌گیری pg_dump، و ترمیم توالی‌ها.
  - توسعه `db_cli.py` با دستورات `check-advisory-lock`، `check-redis-persistence`، و `verify-backup`.
  - حذف دایرکتوری مازاد `disaster-recovery`.
- **تسک ۵: تجمیع رصدپذیری، هشدارها و آزمون بار در `monitoring-alerting` (`barpro-monitoring-alerting`):**
  - پشته پرومتئوس ۲.۵۳، آلرت‌منجر، داشبوردهای گرافانا، اکسترودرهای داخلی چهارگانه، و آزمون بار ۵۰۰ بارنامه در ساعت Locust.
  - توسعه `monitor_cli.py` با دستورات `check-exporters` و `run-load-baseline`.
  - حذف دایرکتوری مازاد `load-testing`.
- **تسک ۶: بازسازی چرخه مستاجران و بایگانی نقشه راه ارتقا:**
  - به‌روزرسانی `tenant-onboard` با تمرکز بر مرزهای کلاینت، رمزنگاری AES رمزهای راننده (`decrypt_driver_password`)، پیوند وب‌هوک فورواردر، و سهمیه‌های روزانه.
  - بایگانی فایل تاریخی `barpro-master-upgrade/SKILL.md` به مسیر `docs/agent-reference/historical-master-upgrade.md` و حذف دایرکتوری آن.
- **تسک ۷: به‌روزرسانی مستندات مرجع و اعتبارسنجی جامع:**
  - به‌روزرسانی بخش ۳ در `AGENTS.md` برای استناد به ۷ مهارت تخصصی تجمیع‌شده.
  - ثبت بخش ۲۲.۱ در گراف دانشی پروژه `docs/BARPRO_KNOWLEDGE_GRAPH.md`.
  - اعتبارسنجی ۱۰۰٪ موفق دستورات `--help` و لینوکس/پایتون در تمام ۷ اسکریپت CLI.
  - اجرای کامل `uvx ruff check .agents/skills/` با نتیجه سبز (`All checks passed!`).

## 📁 فایل‌های تغییریافته
- `.agents/skills/barpro-deploy-ops/SKILL.md`
- `.agents/skills/barpro-deploy-ops/scripts/server_ssh.py`
- `.agents/skills/barpro-rpa-ops/SKILL.md`
- `.agents/skills/barpro-rpa-ops/scripts/rpa_cli.py`
- `.agents/skills/barpro-fullstack-sync/SKILL.md`
- `.agents/skills/barpro-fullstack-sync/scripts/fullstack_cli.py`
- `.agents/skills/database-ops/SKILL.md`
- `.agents/skills/database-ops/scripts/db_cli.py`
- `.agents/skills/celery-ops/SKILL.md`
- `.agents/skills/monitoring-alerting/SKILL.md`
- `.agents/skills/monitoring-alerting/scripts/monitor_cli.py`
- `.agents/skills/tenant-onboard/SKILL.md`
- `.agents/skills/tenant-onboard/scripts/tenant_cli.py`
- `docs/agent-reference/historical-master-upgrade.md`
- `AGENTS.md`
- `docs/BARPRO_KNOWLEDGE_GRAPH.md`
- `.context/STATE.md`

## 🎯 تسک دقیق بعدی
1. تکمیل گزارش تحلیلی برای ایجنت ارشد و کاربر.

## 🧠 تصمیمات فنی و چرایی
1. **ایزولاسیون کامل محلی مهارت‌ها:** طبق الزام کاربر، تمام مهارت‌ها در محدوده محلی مخزن `.agents/skills/` در داخل پروژه نگهداری شده و هرگز در پوشه‌های عمومی سیستم (`~/.gemini/skills/` یا `~/.gemini/config/skills/`) بارگذاری نشدند تا از نمایش یا نشت آن‌ها در سایر پروژه‌ها اکیداً جلوگیری گردد.
2. **برتری ترنسپورت مستقیم Mobile API:** مرورگر وب برای ثبت صدور بارنامه بازنشسته شده است؛ تمام فرآیندهای حیاتی اکنون مستقیماً به کلاینت رسمی متصل هستند و از سرور اندروید مجازی Redroid برای جی‌پی‌اس استفاده می‌کنند.
3. **گیت اثبات دو-شاهد:** ادعای ثبت بارنامه بدون وجود همزمان کد پیگیری در پاسخ RPA و ذخیره قطعی آن در دیتابیس هرگز تایید نخواهد شد.

## ⚠️ نکات حساس و موانع
- هیچ مانعی وجود ندارد. کلیه اسکریپت‌ها با پایتون استاندارد و بدون باگ سینتکسی یا لینت با موفقیت بررسی و تایید شدند.

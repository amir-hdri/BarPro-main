# گزارش وضعیت عملیاتی 2026-09-19 (شب)

## تغییرات کد — CODE-VERIFIED

- کامیت `5af5cd3` روی برنچ `codex/session-recovery-20260917`
  (`fix: executor ack parity, select read-back, loud fare defaults`)، ۷ فایل، `+204/-21`:
  - `app/services/scheduled_waybill_executor.py`: نرمال‌سازی ack خام با
    `build_tracking_received_result` (برابری با worker) + `document_id` +
    `needs_reconciliation=False`. تست بازتولیدکننده شکاف اضافه شد
    (`test_raw_bot_tracking_code_normalized_to_worker_contract`).
  - `app/automation/waybill_enhanced.py`: هلپر `_select_readback_confirms` و
    read-back در fast-path `_select_dropdown`؛ مغایرتِ خوانا رد می‌شود،
    ناخوانا پذیرش legacy. سه تست fast-path اضافه شد.
  - کرایه پیش‌فرض ۵٬۰۰۰٬۰۰۰ (قانون UTCMS 4025) حفظ شد ولی بلند:
    هشدار `default_fare_applied` در آداپتر (هر دو مسیر)، فرم، و auto-heal
    ترنسپورت. تست‌های caplog/assertLogs اضافه شد.
- گیت‌ها: `1556 passed / 3 skipped` در ۹۹۸ ثانیه (full suite)، فرانت‌اند
  `35 passed`، `tsc --noEmit`، ESLint، Ruff، Black، `git diff --check` — همه سبز.

## شواهد زنده — LIVE-OBSERVED (فقط‌خواندنی، 2026-09-19 ~15:31–16:35Z)

- همه کانتینرهای مرکزی healthy (backend/worker-1/beat/scheduler حدود ۳۰ ساعت تا ۲ روز؛ postgres/redis دو هفته).
- Worker 1 و scheduler heartbeat تازه (~۹ ثانیه). Worker 2/3 stale از ~۱۷ روز پیش.
- گیت خالی: `rpa:gate:state` در Redis وجود ندارد (TTL=-2)، بدون override دستی → `unknown` (fail-closed).
- پروب‌های دوره‌ای گیت هر ۵ دقیقه `unknown` با `utcms_gate_evidence_unavailable_fail_closed`
  در ~۰٫۰۲ ثانیه برمی‌گردند — by design فقط کش را می‌خوانند، I/O زنده به پورتال ندارند.
- جاب‌ها: ۸ عدد `waiting_submission_window/gate_unknown` (attempts مشکوک ۱۱۰–۳۱۴، ولی درست نگه داشته شده‌اند)؛
  ۳ عدد `needs_review/submission_unconfirmed/ambiguous` (۱۰۶/۱۰۷/۱۰۸ — هرگز resubmit نشوند)؛
  بقیه failed/cancelled. هیچ سشن GPS فعالی در Redis نیست.
- آخرین ثبت موفق: job شماره ۶۱، ترکینگ `215477251`، تاریخ 2026-09-08. در ۴ روز اخیر هیچ successای نبوده.

## اقدام عملیاتی — با مجوز اپراتور

- `ALLOW_LIVE_SUBMIT` روی سرور مرکزی `false` → `true` شد (بکاپ `.env` گرفته شد،
  بک‌اند recreate و healthz تأیید شد). درس: `docker restart` به‌تنهایی env جدید را
  اعمال نمی‌کند؛ recreate باید با همان پروژه compose زنده (`compose` از
  `/opt/barpro/compose` با `--env-file /opt/barpro/.env`) انجام شود.

## مشاهدات لاگین زنده (read-only، بدون ثبت/پیامک)

- راننده جدیدترین جاب معلق → خطای JSON پورتال: «خطا در سامانه (code: 1)».
- راننده job 109 (لاگین موفق 09-17) → «non-JSON response».
- نتیجه: پورتال امشب لاگین را قبول نمی‌کند (credential؟ قفل اکانت؟ نگهداری؟ WAF؟) — مستقل از گیت.

## خودداری‌شده (با دلیل فنی)

- حذف شرط شاهد OTP: مسیر شروع/پایان GPS هیچ ارجاعی به gate/otp ندارد (`shipping_gps.py`)،
  پس حذفش اثری نداشت؛ پروب‌ها اصلاً از گیت رد نشدند و باز شکست خوردند؛
  override دستی هم در پروداکشن طبق طراحی نادیده گرفته می‌شود.

## باقی‌مانده

- بارنامه دستی ۲–۳ روز پیش در BarPro نیست (ثبت دستی در پورتال). برای شروع/پایان GPS آن لازم است:
  `doc_no` + راننده + مختصات GPS مبدأ (operator-confirmed).
- بررسی/به‌روزرسانی پسورد راننده‌ها در پورتال (مظنون اصلی خطای سامانه).
- استقرار کد `5af5cd3` (نیازمند push + deploy).
- Worker 2/3 (دسترسی SSH/کلید).

## تکمیل 2026-09-19 (شب، ادامه)

- استقرار انجام شد: ایمیج `barpro_backend:latest` بازسازی و هر ۴ سرویس
  (backend/worker-1/scheduler/beat) recreate شدند؛ `ALLOW_LIVE_SUBMIT=true` زنده تأیید شد.
- لاگین راننده job 109 دو بار موفق (`login_ok=True, fleet_ok=True`) — مسیر باز است.
- تلاش ثبت واقعی via `execute_scheduled_job_by_id(109)`: سیستم درست نگه داشت
  (`waiting_submission_window/gate_unknown`، صفر mutation). گیت فقط با مشاهده زنده باز می‌شود.
- فیکس ناپایداری لاگین: `get_or_login_client` حالا خطای گذرا (transport، non-JSON،
  ‏429/5xx/408) را حداکثر یک بار retry می‌کند؛ رد قطعی پورتال (`result_code`، ‏401/403/444)
  هرگز retry نمی‌شود. تست‌های TDD اضافه شد.
- ورکر ۲: پورت ۲۲ timeout (هاست پایین/فایروال). ورکر ۳: SSH زنده ولی host key عوض شده —
  اثر انگشت‌ها برای تأیید اپراتور ثبت شد، بدون تأیید قبول نمی‌شود.
- شمارش attempts بالا (۱۱۰–۳۱۴) بررسی شد: claim+hold بدون مصرف مرورگر، بی‌ضرر، بدون سقف مرگبار.

## ریشه‌یابی کپچای ثبت نهایی — LIVE-PROVEN 2026-09-19/20

- تلاش نظارتی ثبت job 109 تا مرحله نهایی رفت و روی کپچا متوقف شد (بدون mutation).
- لاگ زنده: CNN هر سه بار **درست** حل کرد (`8`، `7`، `7`) ولی
  `_final_captcha_min_length()=2` جواب تک‌رقمی درست را رد کرد (`normalized=None`).
  فرض «چالش‌های نهایی چندرقمی‌اند» غلط بود: جمع‌های ۰–۱۸ اغلب تک‌رقمی‌اند.
- اسکرین‌شات مرحله نهایی (`11_final_preview_validated.png`) فرم کامل و کپچای ریاضی را نشان داد.
- فیکس: حداقل به ۱ برگشت (pattern، سقف طول و confidence همچنان garbage را رد می‌کنند) + تست TDD.
- نکته محیطی: checkout لوکال بین دو سشن به main رفته بود؛ کارها روی گیتهاب سالم ماند و برگردانده شد.

# بازیابی سشن Antigravity و اصلاحات ۲۰۲۶-۰۹-۲۳

## مبنای بررسی

- آخرین سشن BarPro در Antigravity: `f011319a-3d3e-4be4-98a4-c545decc19df`،
  «رفع موانع ثبت نام»، ۱۶۶۹ step، بازه تقریبی
  `2026-09-22T19:35Z` تا `2026-09-23T03:38Z`.
- سشن با ۸ خطای پی‌درپی `RESOURCE_EXHAUSTED (429)` روی stream مدل قطع شد؛
  **گزارش پایانی «با سند و مدرک» هرگز به کاربر تحویل داده نشد.**
- ورودی کاربر: (۱) پیشبرد ثبت تا مرحله OTP و رفع موانع؛
  (۲) راستی‌آزمایی عمیق و گزارش کامل بدون اغراق.
- کامیت‌های آن سشن (شاخه محلی، روی سرور نیز `078544a`):
  `9ce05d7`, `e244d28`, `6c6749a`, `078544a`.
- پایان سشن زنده روی سرور مرکزی: ۱۰/۱۰ تلاش InsertDocument با
  `resultCode=4003` (کد امنیتی نامعتبر) رد شد؛ یک بار نیز `4017`
  (نوع کالا). هیچ `docId` موفقی ثبت نشد.

## ریشه‌یابی ۴۰۳/۴۰۰۳ — CODE-VERIFIED

- `UtcmsMobileClient._post` فقط برای HTTP خارج از 2xx یا `resultCode ∈ {3000,3001}`
  raise می‌کرد؛ پاسخ HTTP 200 + `resultCode=4003` **بدون exception** برمی‌گشت.
- در نتیجه حلقهٔ retry کپچا در `waybill_bot_multitenant` و اسکریپت‌های زنده
  که فقط `except UtcmsMobileApiError` را می‌دیدند، **هرگز فعال نمی‌شدند**؛
  عملیات مثل موفقیت ادامه می‌یافت یا در حلقهٔ بیرونی گم می‌شد.
- اصلاح: `insert_document` و `issue_document_by_otp` اکنون
  `require_successful_mutation(...)` را اعمال می‌کنند — هر resultCode غیر از
  `200` (از جمله 4003 و 4017) raise می‌کند.

## اصلاح لاگر جعلی موفقیت — CODE-VERIFIED

- `scripts/execute_job_109_mobile.py` قبلاً:
  - `🎉 INSERT DOCUMENT RESULT` را بدون بررسی `resultCode` چاپ می‌کرد؛
  - موفقیت را فقط با وجود `doc_no` (حتی بدون `docId`) می‌پذیرفت؛
  - در پایان بدون قید موفقیتِ تجاری، `status=SUCCESS` و
    `mutation_status=confirmed` روی Job 109 می‌نوشت.
- اکنون موفقیت فقط وقتی تأیید می‌شود که **هر سه** شرط برقرار باشد:
  1. `resultCode ∈ {0, 200}` (تجاری، نه فقط HTTP 200)
  2. `docId` خالی نباشد
  3. اگر `isOtpNeeded=true` بود، `IssueDocumentByOtp` نیز با resultCode موفق
     برگشته باشد (وگرنه SUCCESS ثبت نمی‌شود)
- نوشتن DB فقط پس از این دروازه انجام می‌شود؛ شکست بدون
  `🎉 SUCCESS` ثبت می‌شود.

## شواهد کپچا کنار هم (4003) — CODE-VERIFIED

- `CaptchaResult.meta` اکنون از CNN پیش‌بینی را حمل می‌کند
  (`expression`, `answer`, `confidence`, `characters`).
- `UtcmsMobileClient.last_captcha_debug` تصویر + پیش‌بینی آخرین solve را نگه
  می‌دارد؛ `dump_captcha_rejection()` هنگام 4003 اجرا می‌شود.
- `app/automation/captcha/debug_artifacts.py`: نوشتن `<ts>.png` + `<ts>.json`
  در `/tmp/captcha_rejections/` (تصویر و پیش‌بینی مدل کنار هم؛ هرگز raise
  نمی‌کند).
- اتصال در `waybill_bot_multitenant` (حلقهٔ 4003) و
  `scripts/execute_job_109_mobile.py` و
  `scripts/live_insert_otp_probe.py`.

## سیاست گیت OTP — DECISION DOCUMENTED

- **تصمیم:** عبور `allow_otp_flow` / `transport=mobile` / `UTCMS_TRANSPORT ∈
  {mobile,shadow}` از گیت پیش‌جهش حفظ می‌شود.
- **دلیل:** مسیر موبایل خودش چالش OTP راننده را با `IssueDocumentByOtp`
  می‌پذیرد؛ اعمال صرف `OTP_FREE` روی این مسیر، ثبت شبانه را بدون دلیل
  مسدود می‌کند.
- **قید:** Web RPA بدون آن flag همچنان fail-closed روی
  `otp_required` / `gate_unknown` است.
- متن قرارداد در `AGENTS.md` → «OTP and CAPTCHA» →
  *Documented exception (mobile/OTP transport, 2026-09-23)* درج شد.
- چهار نقطهٔ اجرای گیت (worker / submit / scheduler / scheduled executor)
  با همان شرط یکسان‌اند.

## پاکسازی فایل‌های Untracked

| مورد | محل | اقدام |
|------|-----|--------|
| `.env.bak.20260919T125827Z` | سرور `/opt/barpro` | حذف از working tree؛ الگوی `.env.bak.*` به `.gitignore` اضافه شد |
| `captcha_cnn_v12_torch_*.pkl` | محلی + سرور | حذف؛ فقط v13 ردیابی می‌شود |
| `test_insert_live_otp.py` (ریشه) | سرور | حذف از ریشه؛ جایگزین: `scripts/live_insert_otp_probe.py` (گیت‌شده) |
| ردیابی `*.pkl` در `_model_cache` | `.gitignore` | الگوی نادیده‌گرفتن v12 اضافه شد |

وضعیت محلی پس از اصلاح (پیش از commit):

```
 M .gitignore
 M AGENTS.md
 M app/automation/captcha/base.py
 M app/automation/captcha/cnn_provider.py
 M app/automation/utcms_mobile_client.py
 M app/automation/waybill_bot_multitenant.py
 M scripts/execute_job_109_mobile.py
?? app/automation/captcha/debug_artifacts.py
?? scripts/live_insert_otp_probe.py
?? tests/test_captcha_rejection_and_success_gate.py
```

## آزمون‌ها — LOCAL RUN 2026-09-23

- `pytest` هدفمند (mobile contract, bot, gate, mutation, captcha, OTP forwarder,
  سطح جدید): **100 passed**.
- فایل جدید `tests/test_captcha_rejection_and_success_gate.py`: 6 passed.
- `ruff check` روی فایل‌های لمس‌شده: All checks passed.
- `black -l 120` روی فایل‌های لمس‌شده: اعمال شد.

این اعداد نتیجهٔ اجراهای همین بازبینی‌اند، نه snapshot قدیمی.

## شواهد زنده — LIVE (به‌روزرسانی پس از اجرا)

- **قبل از این اصلاحات (سشن Antigravity، task-1577):** ۱۰/۱۰ رد با 4003؛
  `Document ID: None`؛ بدون artifact سمت‌به‌سمت.
- **پس از deploy این تغییرات:** بخش زیر پس از اجرای
  `scripts/live_insert_otp_probe.py` روی سرور مرکزی تکمیل می‌شود.

<!-- LIVE_E2E_RESULT -->
### نتیجهٔ اجراهای زنده — 2026-09-23 (ثبت‌شده، بدون ادعای موفقیت)

دستور همهٔ اجراها داخل کانتینر `barpro-backend`:
`docker compose -f compose/backend.yml exec -T backend python scripts/live_insert_otp_probe.py`
لاگ‌ها: `/tmp/live_e2e_probe_20260923*.log` روی سرور.

- **پیش‌شرط deploy (verified):** هر ۱۱ فایل tar روی `/opt/barpro` با hash
  محلی تطبیق کرد؛ فایل‌های `._*` مک حذف شدند؛ `barpro-backend` و
  `barpro-worker-1` healthy؛ اسکریپت‌ها با همان hash داخل کانتینر کپی شدند
  (`scripts/` در ایمیج mount نیست، فقط `app/` و `alembic/` mountاند).
- **اجرای 13:55 — توقف در login:** `UTCMS mobile login failed: خطا در
  سامانه (code: 1)`؛ هیچ insert، هیچ artifact.
- **اجرای 14:38 — login موفق، سپس 401 بی‌پیام:** `login_ok`، یک insert با
  کپچای `7+6=13`، رد `401` با پیام گم‌شده. همین شکاف باعث فیکس
  `require_successful_mutation` (نگه‌داشتن message و body sanitizeشده) شد.
- **اجرای 14:41 — طبقه‌بندی کامل، دو artifact واقعی:**
  - تلاش ۳: کپچای `0+6=6` با conf=0.61 → رد `4003` («کد امنیتی وارد شده
    نامعتبر») + artifact سمت‌به‌سمت `/tmp/captcha_rejections/20260923T144152.json`
    و `20260923T144152.png` (prediction/expression/confidence/image کنار هم).
  - تلاش ۴: کپچای `7+6=13` با conf=0.736 → رد `401` با پیام دقیق:
    «ورود شما منقضی شده است. لطفا دوباره وارد حساب کاربری خود شوید!»
  - artifact نهایی `/tmp/barpro_live_e2e/20260923T111201Z_result.json` با
    `rejection_body` کامل. **نتیجه: 401 یعنی انقضای سشن** — توکن درایور
    حدود ۵ دقیقه عمر دارد و از حلقهٔ ۸تلاشه کوتاه‌تر است.
- **فیکس 401:** پروب و `execute_job_109_mobile.py` اکنون روی 401 حاوی
  «منقضی» حداکثر ۳ لاگین/۷ تلاش، سشن را تازه و تکرار می‌کنند (bounded).
- **اجرای 14:44 — اثبات کارکرد لاگ جدید:** همان `code 1` این‌بار با envelope
  کامل لاگ شد: `sanitized_body={"resultCode": 1, "resultMessage": "خطا در
  سامانه", "obj": null}` — یعنی **پاکت code 1 واقعاً تهی است**؛ سیگنال
  دیگری از سمت UTCMS نمی‌آید.
- **اجرای 14:46 — سه مد جدید پشت سر هم (دلیل توقف تلاش‌های زنده):**
  ۱) fallback کلید PoW با لاگ جدید کار کرد؛ ۲) `code 1` آمد و retry تکی
  تازه با PoW جدید اجرا شد؛ ۳) retry به **429 محدودیت ورود** خورد («تعداد
  ورود به حساب کاربری شما به بیش از حد مجاز رسیده است») و پس از cooldown
  هم POST لاگین با **timeout انتقالی curl 28 (20s, 0 bytes)** شکست خورد.
- **وضعیت نهایی:** هیچ `docId`، هیچ `isOtpNeeded`، هیچ SUCCESS (واقعی یا
  کاذب). مرحلهٔ OTP لمس نشد. login امروز ناپایدار است (رد 13:55، قبول
  14:38، رد 14:44، سپس 429+timeout) — مشکل سمت UTCMS/مسیر است، نه کد ما.
  تلاش زندهٔ بیشتر تا رفع cooldown و پایداری endpoint ممنوع‌المنطق است.

## پذیرش و کار باقی‌مانده

- اثبات ثبت واقعی جدید نیاز به اجرای زنده و دریافت `docId` + `resultCode`
  موفق (و در پنجرهٔ OTP، `isOtpNeeded` یا tracking نهایی) دارد؛ بدون آن،
  SUCCESS ادعایی نیست.
- Jobهای مبهم نباید دوباره ارسال شوند.
- تفاوت CNN روی تصویر با آنچه UTCMS می‌پذیرد فقط با artifactهای
  `/tmp/captcha_rejections/` قابل بستن است.

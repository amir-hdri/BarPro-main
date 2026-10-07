# راستی‌آزمایی اصلاح هشدارهای Bandit — 2026-10-06

این سند اصلاح شش هشدار medium/high ثبت‌شده در `backend-bandit.log` را توضیح می‌دهد؛ تأییدیه وضعیت production نیست.

| هشدار | اقدام و دلیل | شاهد |
|---|---|---|
| B108 — فایل‌های رد CAPTCHA | پوشه اختصاصی 0700 با احراز مالکیت و رد symlink؛ نام یکتا برای هر تلاش و ایجاد انحصاری فایل‌های 0600. فایل‌های هم‌ثانیه دیگر یکدیگر را بازنویسی نمی‌کنند. basename قابل کشف `captcha_rejections` و پارامتر `directory` حفظ شده‌اند. | `app/core/private_storage.py`, `app/automation/captcha/debug_artifacts.py`; تست هم‌زمانی ۱۲ ثبت و symlink |
| B108 — cache دارایی‌های مرورگر | descriptor پوشه برای جلوگیری از تغییر مسیر حین I/O، خواندن محدود و بدون دنبال‌کردن symlink، scratch یکتا و جایگزینی اتمیک. SHA256 بدنه در metadata از معتبر شمردن جفت body/meta ناسازگار هنگام رقابت جلوگیری می‌کند. کلیدهای قبلی metadata و `UTCMS_ASSET_CACHE_DIR` حفظ شدند. | `app/automation/http_browser_bridge.py`; تست scratch آلوده، symlink هنگام read، جابه‌جایی پوشه و نوشتن هم‌زمان |
| دو B614 — DNT و Math CRNN | `torch.load(..., weights_only=True)` صریح و پذیرش صرفاً state_dict با کلید متنی و مقدار Tensor؛ wrapper فعلی `model_state` مدل Math حفظ شد. | `app/automation/captcha/dnt_captcha_solver.py`, `math_crnn_solver.py`; بارگذاری دو فایل مدل موجود، هرکدام ۵۳ Tensor، با torch 2.13.0 |
| دو B324 — SecurityKey | **استثنای قرارداد، نه ارتقای رمزنگاری:** دو محاسبه در `_wire_security_key` تجمیع و فقط همان فراخوانی MD5 با `# nosec B324` مستند شد. قرارداد ثبت‌شده APK به MD5 همان JSON فشرده UTF-8 نیاز دارد؛ تغییر الگوریتم درخواست را ناسازگار می‌کرد. این مقدار برای تصمیم امنیتی داخلی استفاده نمی‌شود. | `app/automation/utcms_mobile_client.py`; `docs/UTCMS_MOBILE_TRANSPORT_REPORT.md:48`; تست ثابت JSON فارسی برای GET و POST |

پوشه قدیمیِ متعلق به همین کاربر با mode برابر 0755 به 0700 تبدیل می‌شود. پوشه متعلق به کاربر دیگر یا قابل‌نوشتن توسط group/others رد می‌شود؛ فایل‌های قدیمی حذف نمی‌شوند. در این حالت cache miss یا هشدار ثبت artifact صادر می‌شود و operator باید مالکیت مسیر پیکربندی‌شده را اصلاح کند. این helper مخصوص محیط‌های POSIX پروژه است.

راستی‌آزمایی اجراشده:

- `security-gates-before.log`: پیش از اصلاح، ۸ تست شکست و ۴ تست موفق؛ شامل بازنویسی قربانی symlink و نبود گزینه صریح `weights_only`.
- `security-gates-focused.log`: **119 passed in 11.31s**؛ ۱۴ تست جدید امنیتی به همراه تست‌های bridge، قرارداد mobile، CAPTCHA، نبود torch و شروع حمل.
- `uvx --from bandit==1.9.4 bandit -r app/ -ll -ii`: exit 0، **Medium: 0 / High: 0**؛ ۳۰۸ مورد Low در آمار اسکن باقی است و خارج از آستانه CI این فرمان قرار دارد. سه suppression اختصاصی کل مخزن شامل دو مورد قبلی و یک مورد قرارداد MD5 است (`backend-bandit-after.log`).
- Ruff و Black فایل‌های تغییرکرده موفق (`security-gates-ruff.log`, `security-gates-black.log`).
- ابزار اسکیل `barpro-captcha-retrain`: بررسی فایل مدل‌ها موفق (`captcha-models-after.json`)؛ ابزار `barpro-rpa-ops`: audit-network موفق (`security-rpa-network-audit.json`).

هیچ مدل بازآموزی یا جایگزین نشد. تست بارگذاری، معیار دقت OCR نیست؛ benchmark دقت جدید یا فراخوانی زنده UTCMS در این بخش انجام نشده است.

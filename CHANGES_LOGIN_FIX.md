# 🔧 اصلاحات برای حل مشکل ورود به سایت barname.utcms.ir

## 📋 خلاصه مشکل

سایت `https://barname.utcms.ir/Barname/Account/Login` درخواست‌های Playwright را با کد **HTTP 444** رد می‌کرد و باعث می‌شد:
- خطاهای `ERR_SSL_PROTOCOL_ERROR`
- Timeout در انتظار selectorها
- عدم تشخیص فرم ورود

## ✅ تغییرات اعمال شده

### 1. 🎯 اصلاح HTTP Headers (اولویت: ⭐⭐⭐⭐⭐)
**فایل:** `app/automation/browser.py` (خطوط 252-265)

**تغییرات:**
- حذف `Sec-Ch-Ua`, `Sec-Ch-Ua-Mobile`, `Sec-Ch-Ua-Platform` (تکنولوژی‌های ضد تشخیص)
- حذف `Sec-Fetch-Dest`, `Sec-Fetch-Mode`, `Sec-Fetch-User` (Headers مشکوک)
- **تغییر `Sec-Fetch-Site: none` به `Sec-Fetch-Site: same-origin`** ← **مهم‌ترین اصلاح**
- حذف `Upgrade-Insecure-Requests: 1` (برای سایت HTTPS غیرضروری)
- حذف تکرار `ignore_https_errors` (خطوط 241 و 247)

**دلیل:** سایت از این headers برای تشخیص bot استفاده می‌کند و `Sec-Fetch-Site: none` نشان‌دهنده درخواست از context غیرعادی است.

---

### 2. 🚫 غیرفعال کردن موقت Route Interceptor (اولویت: ⭐⭐⭐⭐)
**فایل:** `app/automation/browser.py` (خطوط 438-444)

**تغییرات:**
```python
# قبل:
await page.route("**/*", block_map_tiles_and_trackers)

# بعد:
if getattr(utcms_config, 'BLOCK_MAP_TILES', True):
    await page.route("**/*", block_map_tiles_and_trackers)
else:
    logger.info("Route interceptor disabled via BLOCK_MAP_TILES=False")
```

**دلیل:** Route interceptor ممکن است منابع حیاتی سایت را block کند و باعث اختلال در لود صفحه شود.

**تنظیمات جدید در config.py:**
```python
self.BLOCK_MAP_TILES = _to_bool(os.getenv("BLOCK_MAP_TILES", "True"), default=True)
```

**تنظیم در .env:**
```ini
BLOCK_MAP_TILES=false  # برای دیباگ غیرفعال کنید
```

---

### 3. 🗑️ پاک کردن Auth State قدیمی (اولویت: ⭐⭐⭐⭐)
**دستور:**
```bash
rm -rf /Users/amirheidari/GitHub/BarPro-main/.auth/utcms_state.json
```

**دلیل:** فایل auth state قدیمی یا فاسد باعث می‌شود سایت session را رد کند.

---

### 4. ⚡ افزایش Timeout برای AJAX Login (اولویت: ⭐⭐⭐)
**فایل:** `app/automation/auth.py` (خطوط 1214-1217)

**تغییرات:**
```python
# قبل:
timeout=12000

# بعد:
timeout=25000  # Increased from 12000 to 25000 for better reliability
```

**دلیل:** سایت UTCMS ممکن است کند باشد و 12 ثانیه برای wait_for_response کافی نباشد.

---

### 5. 🎯 اولویت‌دهی به Selectorهای NationalCode (اولویت: ⭐⭐⭐)
**فایل:** `app/automation/selectors.py` (خطوط 196-207)

**تغییرات:**
```python
USERNAME_SELECTORS = (
    # UTCMS uses NationalCode for username (priority first)
    "input[name='NationalCode']",      # ✅ اولویت اول
    "input[id='NationalCode']",       # ✅ اولویت دوم
    "input[name*='national' i][type='text']",
    "input[name*='National' i][type='text']",  # ✅ جدید: برای case-sensitive
    # Fallback selectors for other systems
    "input[name='Username']",
    ...
)
```

**دلیل:** سایت از فیلد `NationalCode` (کد ملی/شناسه ملی) به جای `Username` استفاده می‌کند.

---

### 6. 🔧 تنظیمات دیباگ در .env (اولویت: ⭐⭐⭐)
**فایل:** `.env`

**تغییرات:**
```ini
# Browser settings for debugging login issues
HEADLESS=false         # برای مشاهده مرورگر در حین اجرا
BLOCK_MAP_TILES=false  # غیرفعال کردن route interceptor
```

**دلیل:** این تنظیمات به دیباگ کردن مشکل کمک می‌کنند.

---
---

## 📊 جدول تغییرات

| # | مشکل | فایل | تغییر | اولویت | وضعیت |
|---|------|------|--------|---------|--------|
| 1 | `Sec-Fetch-Site: none` | browser.py:262 | → `same-origin` | ⭐⭐⭐⭐⭐ | ✅ انجام شد |
| 2 | Route Interceptor | browser.py:447 | غیرفعال کردن موقت | ⭐⭐⭐⭐ | ✅ انجام شد |
| 3 | Auth State قدیمی | .auth/ | پاک کردن فایل | ⭐⭐⭐⭐ | ✅ انجام شد |
| 4 | تکرار `ignore_https_errors` | browser.py:241,247 | حذف تکرار | ⭐⭐⭐ | ✅ انجام شد |
| 5 | selectorهای اشتباه | selectors.py | اولویت به NationalCode | ⭐⭐⭐ | ✅ انجام شد |
| 6 | AJAX timeout کم | auth.py:1216 | 12000 → 25000 | ⭐⭐ | ✅ انجام شد |

---

## 🚀 نحوه تست

### تست سریع:
```bash
# 1. پاک کردن auth state
rm -rf .auth/utcms_state.json

# 2. اجرا با تنظیمات جدید
source .venv/bin/activate
./scripts/start_system.sh
```

### تست دستی با Python:
```python
import asyncio
from app.automation.browser import BrowserManager
from app.automation.auth import UTCMSAuthenticator

async def test_login():
    manager = BrowserManager()
    await manager.initialize()
    session_id, context = await manager.create_context()
    page = await manager.new_page(context)
    
    auth = UTCMSAuthenticator(page, context)
    success = await auth.login(
        username="YOUR_NATIONAL_CODE",
        password="YOUR_PASSWORD"
    )
    print(f"Login {'successful' if success else 'failed'}: {auth.last_error}")

asyncio.run(test_login())
```

---

## 🔍 دیباگ پیشرفته

اگر هنوز مشکل وجود داشت:

1. **چک کردن لاگ‌ها:**
   ```bash
   tail -f backend.log | grep -E "444|SSL|timeout|login"
   ```

2. **غیرفعال کردن کامل stealth mode:**
   در `browser.py` خط 444:
   ```python
   # await apply_stealth_mode(page)  # موقتاً کامنت کنید
   ```

3. **تست با headers پیش‌فرض Playwright:**
   در `browser.py`، تمام `extra_http_headers` را حذف کنید و تنها:
   ```python
   extra_http_headers = {
       "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
   }
   ```

4. **چک کردن که آیا سایت شما را بلوک کرده:**
   ```bash
   curl -v "https://barname.utcms.ir/Barname/Account/Login" -H "Sec-Fetch-Site: none"
   ```
   اگر 444 گرفتید، مشکل از سایت است.

---

## 📝 یادداشت‌ها

- **همه تغییرات غیرمخرب** هستند و قابل برگشت هستند.
- تنظیمات `HEADLESS=false` و `BLOCK_MAP_TILES=false` تنها برای دیباگ هستند.
- در محیط production، می‌توانید آنها را به مقادیر پیش‌فرض برگردانید:
  ```ini
  HEADLESS=true
  BLOCK_MAP_TILES=true
  ```
- اگر مشکل حل شد، می‌توانید Route Interceptor را دوباره فعال کنید.

---

## 🎉 وضعیت نهایی

✅ **همه ۶ اصلاح اعمال شده‌اند**
✅ **تست با Playwright ساده: موفق**
✅ **ready برای تست کامل سیستم**

تاریخ اعمال: 2026-06-09

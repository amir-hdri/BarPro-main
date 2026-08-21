> Legacy scenario catalogue. Current success requires three-witness UTCMS
> reconciliation; test counts and runtime outcomes must be re-run for the current
> commit. See docs/BARPRO_KNOWLEDGE_GRAPH.md.

## ۶. سناریوهای موفق و ناموفق (Test Scenarios & Edge Cases)

1. **Successful Path**: آپلود اکسل > تایید API > ارسال به صف Redis > دریافت توسط Worker > باز کردن مرورگر و دور زدن ربات‌گیری > ورود اطلاعات بدون خطا > ثبت موفق در سامانه > بروزرسانی دیتابیس داخلی.
2. **Captcha Failure Loop**: کپچا غیرخوانا است > سیستم خطا می‌گیرد > `SmartLocator` به صورت هوشمند روی دکمه Refresh کلیک می‌کند > تا N بار (تنظیم شده در کانفیگ) تلاش می‌کند > اگر حل نشد Job را به حالت Failed-Retry میبرد.
3. **Session Timeout/Invalidation**: در وسط کار سامانه مبدا Session را باطل می‌کند > `UTCMSAuthenticator` وضعیت را با `last_error` آپدیت می‌کند > ربات در Context جدید کانکشن را بازیابی کرده و از ابتدا لاگین می‌کند.
4. **OTP Triggered**: سامانه نیازمند پیامک یکبار مصرف است > Worker موقتاً متوقف شده (Graceful Exit)، و به کاربر پیغام می‌دهد که باید کد را وارد کند.

---

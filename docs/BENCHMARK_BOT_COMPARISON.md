# مقایسهٔ ربات مرجع با BarPro — بررسی آفلاین ۲۰۲۶-۱۰-۰۲

این بررسی روی فایل‌های موجود در `GitHub/scrapy/bot_extraction` انجام شده است؛
هیچ درخواست زنده به ربات مرجع، UTCMS یا سرور BarPro ارسال نشده است. شواهد زیر
وضعیت فایل‌های ذخیره‌شده را ثابت می‌کنند، نه وضعیت جاری سرویس را. مقادیر واقعی
حساب، رمز، توکن، پلاک و اشخاص از فایل‌های مرجع به مخزن BarPro کپی نشده‌اند.

## شواهد قابل بازتولید

| فایل در `bot_extraction/` | نتیجهٔ بررسی محلی | SHA-256 |
|---|---|---|
| `source/bot_main.html` | ۱۳۰٬۹۹۸ بایت؛ ۵۲۰۵ خط منطقی، ۵۲۰۴ newline؛ آخرین خط newline ندارد | `6cfcc812fd7d07a50a9c68bd8a59769ff476fa0420c49ad45bad9f8b10fc874d` |
| `source/p_enter.html` | ۱۰۵۹ خط منطقی، ۱۰۵۸ newline | `fda9f850e921757a4b2461a05bb187d63df31686c83448e178e531b98796f5cd` |
| `data/barname_status0_all.json` | JSON معتبر؛ ۵۵ مدل: ۵۴ مدل با ۲۷ کلید و یک مدل با ۳۱ کلید | `6a6908d6035f262d58f751f5f81fd8e744a5a06e8bb1f1d75f68e68279e1ca68` |
| `data/drivers_limit1.json` | `total=76, pages=77, count=1, page=1` | `bfbe0b70885acd8b2a9f99c2412c89eb6ca4927be31cd9b0e31f94f4baec51b9` |
| `data/barname_status3_sample.json` | ۶۶۵۱ بایت؛ JSON بریده‌شده و نامعتبر، موقعیت خطای parser برابر ۵۴۳۱ | `37333292fb470f2435c0fffff1b4cf0a50cb705edf8cd15ba1c40a624ff3d13b` |
| `data/barname_status4_sample.json` | ۶۶۵۱ بایت؛ JSON بریده‌شده و نامعتبر، موقعیت خطای parser برابر ۵۷۵۴ | `ebd66d2c82929eded493a444b51487b214b506481bff646d7acca91290dcc01e` |

فایل‌های نمونهٔ وضعیت ۱، ۲ و ۵ JSON معتبر با
`total=0, pages=1, count=0, page=1` هستند. نمونه‌های بریده‌شدهٔ وضعیت ۳ و ۴
به‌عنوان پاسخ کامل parse یا تأیید نشده‌اند؛ بخشی از متن آن‌ها نمی‌تواند شاهد
کامل pagination یا ثبت موفق باشد. اعداد snapshotهای مختلف را نباید یک اجرای
هم‌زمان فرض کرد.

## قرارداد مرجع و تصمیم برای BarPro

| موضوع | شاهد مرجع | تصمیم در BarPro |
|---|---|---|
| `model` | `populate()` در `bot_main.html:3272–3321`، ۲۷ فیلد رشته‌ای را در JSON رشته‌ای می‌گذارد؛ دادهٔ ذخیره‌شده چهار فیلد `sent_*` نیز دارد | واژگان دقیقاً ۳۱ کلید است؛ هر رکورد لزوماً ۳۱ کلید ندارد. مبدل آفلاین ۲۷ پایه یا ۲۷+۴ را می‌پذیرد |
| `load_description` | تنها occurrence در خط ۱۸۷۶؛ در `populate()` نیست | در ورودی مرجع نادیده گرفته می‌شود؛ فیلد مستقل `cargo.description` خود BarPro حذف نشده است |
| randomizer | خطوط ۲۰۷۱–۲۰۸۰: ۹ checkbox فعال؛ `_x_type` داخل comment HTML است | فقط به‌عنوان قرارداد مرجع ثبت می‌شود؛ تولید نام، موبایل، کرایه یا مختصات تصادفی به BarPro اضافه نمی‌شود |
| `req()` | خطوط ۱۱۴۰–۱۲۵۰: بدنهٔ truthy یعنی POST، بدون بدنه GET؛ `method` صریح مقدم است؛ object به JSON تبدیل می‌شود و FormData جداست | رفتار متعلق به transport ربات مرجع است؛ درخواست‌های BarPro همچنان method صریح خود را دارند |
| `x-token` | خطوط ۱۲۳۷–۱۲۴۰ و `p_enter.html:737–740`: اول `sessionStorage.token`، سپس `localStorage.token` | JWT بارپرو همچنان در کوکی httpOnly است؛ توکن ربات مرجع به API یا WebSocket بارپرو وارد نمی‌شود |
| `secret` | خطوط ۱۱۵۸–۱۱۷۵ و `p_enter.html:658–675`: فقط هنگام وجود secret؛ شاخهٔ شرط localStorage مقدار را از sessionStorage می‌خواند | باگ شرط/منبع مقدار تأیید شد. BarPro این wrapper را ندارد؛ به کد آن منتقل نشده است. در هر اتصال آتی انتخاب منبع و خواندن مقدار باید یک‌بار و از همان منبع انجام شود |
| توقف سرویس | خط ۸۰۵: تنها `req("/service?action=stop", null, ...)`؛ طبق wrapper، GET است | هیچ شاهد POST برای این عمل در سورس نیست؛ API توقف فرضی در BarPro ساخته نشده است |
| pagination | `drivers_limit1.json` و نمونه‌های تهی با `floor(total/limit)+1` سازگارند | قرارداد مصرف ربات مرجع باید صفحهٔ اضافه/تهی را تحمل کند؛ این رفتار به محاسبهٔ صفحات API بارپرو منتقل نشده است |
| نمونهٔ `total=47, limit=5, pages=10` | با `ceil` و `floor+1` هر دو سازگار است | شاهد off-by-one محسوب نمی‌شود؛ فرمول backend در این corpus موجود نیست |
| موبایل طرفین | خطوط ۳۶۲۰ و ۳۶۴۰: ۱۱ رقم با `09` یا ۱۰ رقم با `9` | مبدل آفلاین فرم ۱۰رقمی معتبر را به `09` تبدیل می‌کند؛ اعتبارسنجی و تشخیص یکسان‌بودن با موبایل راننده برقرار است |
| استان و واحد وزن | مدل استان ندارد؛ فرم `load_weight` در خط ۱۸۷۰ فقط «وزن» می‌گوید | هر دو استان و واحد وزن هنگام تبدیل باید صریحاً وارد شوند؛ مبدل از شهر یا بزرگی عدد حدس نمی‌زند |
| اعتبارنامه در پاسخ | پاسخ‌های driver دارای password و بارنامه دارای `driver.password` هستند | فقط model allowlist وارد پیش‌نویس می‌شود؛ کل envelope، credential و وضعیت اجرایی کنار گذاشته می‌شوند |

فرمول صفحه‌بندی، **رفتار سازگار با snapshotهای موجود** است، نه کد backend
بازبینی‌شده. مصرف‌کنندهٔ احتمالی باید `total/count` و items خالی را لحاظ کند و
صفحهٔ تهی پایانی را خطای ثبت یا نیاز به تکرار mutation تلقی نکند. BarPro در این
تغییر transport زنده‌ای برای ربات مرجع ندارد.

## واژگان دقیق مدل

۲۷ کلید پایه، به ترتیب `populateSafe()`:

```text
sender_national_code, sender_firstname, sender_lastname, sender_mobile,
receiver_national_code, receiver_firstname, receiver_lastname, receiver_mobile,
source_address, source_lat, source_lng, source_city,
dest_address, dest_lat, dest_lng, dest_city,
load, box, load_count, load_weight, load_price, cost,
driver_national_code, plack_region, plack_2, plack_char, plack_3
```

چهار کلید افزودهٔ مشاهده‌شده در پاسخ ذخیره‌شده:

```text
sent_source_lat, sent_source_lng, sent_dest_lat, sent_dest_lng
```

۹ randomizer فعال، پس از حذف پیشوند `_x_`:

```text
sender_firstname, sender_lastname, sender_mobile,
receiver_firstname, receiver_lastname, receiver_mobile,
rent, latlng, value
```

کلیدهای baseline `cost` و `load_price` با نام randomizerهای `rent` و `value`
یکی نیستند. `sent_*` گواه GPS فیزیکی، مسیر پیموده‌شده یا پذیرش UTCMS نیست؛
هیچ‌کدام نباید مختصات اصلی مدل را بی‌صدا جایگزین کند. مدل ۳۱کلیدی ربات مرجع با
DTO موبایل UTCMS (`source`, `destination`, `load`, `truck`, …) یک قرارداد نیست.

## تبدیل آفلاین پیاده‌شده

`app/automation/benchmark_payload_adapter.py` دو ورودی می‌پذیرد: مدل مستقیم
یا رکوردی دارای `model` رشته‌ای/آبجکت. `read_benchmark_model()` فقط کلیدهای
ثبت‌شده را می‌پذیرد؛ کلید تازه، مقدار غیررشته‌ای، JSON نامعتبر/کلید تکراری یا
چهارگانهٔ ناقص `sent_*` خطا می‌دهد. متن خطا مقادیر ورودی را بازتاب نمی‌دهد.

`build_benchmark_import_draft()` طرفین، کالا، کرایه، پلاک و مختصات اصلی را به
ساختار nested بارپرو تبدیل می‌کند و اعتبارسنج فعلی BarPro را اجرا می‌کند.
پیش‌نویس همواره `requires_review=True` دارد؛ `validation_errors` فقط نتیجهٔ
اعتبارسنجی کسب‌وکاری است و خالی‌بودنش مجوز submit نیست. `sent_*` صرفاً در
`sent_coordinate_reference` و بیرون از payload اجرایی حفظ می‌شود. `repr` نتیجه
دادهٔ طرفین یا مختصات را چاپ نمی‌کند.

نمونهٔ استفاده با متغیر موجود در حافظه، بدون چاپ دادهٔ اشخاص:

```python
from app.automation.benchmark_payload_adapter import build_benchmark_import_draft

draft = build_benchmark_import_draft(
    saved_record,
    origin_province="تهران",
    destination_province="تهران",
    weight_unit="kg",  # Must be known from the source data, never inferred.
)
errors = draft.validation_errors
```

مبدل هیچ API، صف، DB یا فایل خروجی حاوی اطلاعات اشخاص ایجاد نمی‌کند. پیش از
استفاده از payload، رانندهٔ BarPro و مالکیت tenant باید مستقل انتخاب/تأیید و
`validate_live_waybill_payload()` با شناسه و پلاک همان راننده اجرا شود. کدپستی،
بیمه، شناسهٔ کالا/بسته‌بندی و مشخصات خودرو برای transport موبایل همچنان باید
از دادهٔ معتبر تأمین شوند؛ این مبدل آن‌ها را جعل نمی‌کند. مدل مرجع تفکیک شخص
حقوقی ندارد؛ تبدیل فعلی برای شخص حقیقی است و اشخاص حقوقی نیاز به اصلاح دستی
پیش‌نویس دارند. پلاک منطقه آزاد نیز ممکن است به review و تطبیق با قرارداد
پلاک BarPro نیاز داشته باشد.

تست‌های آفلاین در `tests/test_benchmark_payload_adapter.py` با مقادیر ساختگی،
تبدیل و عدم‌تغییر ورودی، جداسازی credential/state، مختصات اصلی در برابر sent،
واحد وزن صریح، موبایل، drift مدل و حفظ گیت transport موبایل را پوشش می‌دهند.

## حدود استناد

نام‌های WS01/03/06/04، قواعد WS22/C01–C05، کدهای 445xxx، `otpValidityPeriod=5`
و نتیجه‌های لاگی WAF از این HTML/JSON به‌تنهایی تأیید نمی‌شوند. گزارش آن‌ها
نیازمند corpus ارجاع‌شدهٔ `utcms_scraper` یا شواهد لاگی مستقل است. وضعیت
`barname_id`، status داخلی یا shipping داخل snapshot ربات مرجع نیز جای قاعدهٔ
دوشاهدی + تأیید یکجای History در [UTCMS_CONSTRAINTS.md](UTCMS_CONSTRAINTS.md) را نمی‌گیرد.

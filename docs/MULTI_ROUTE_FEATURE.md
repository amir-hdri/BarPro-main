# قابلیت چندمسیره + فاصله/زمان (Multi-Route)

> نسخه: v2.9.3 — آخرین هم‌ترازی: 2026-08-23

ثبت بارنامه به‌صورت **چندمسیره**: تعریف چند مسیر (مبدأ→مقصد)، سپس گسترش آن‌ها به تعداد دلخواه بارنامه با رعایت فاصلهٔ زمانی ضد اسپم.

## ۱) اجزای اصلی

| مؤلفه | مسیر / جدول | شرح |
|---|---|---|
| قالب مسیر | `waybill_route_template` | مسیر ذخیره‌شده با فاصله/زمان پیش‌محاسبه‌شده |
| دستهٔ چندمسیره | `waybill_batch` | گسترش N قالب × target_count به job واقعی |
| سرویس فاصله/زمان | `app/services/distance_service.py` | Neshan → کش Redis → fallback هاورساین |
| migration | `038_add_multiroute_batch_distance` | جداول + ۵ ستون `waybill_jobs` |
| endpoint فاصله | `POST /api/v1/locations/distance` | محاسبهٔ فاصله/زمان دو مختصات |
| endpoint قالب‌ها | `/api/v1/route-templates` | CRUD + favorite |
| endpoint دسته‌ها | `/api/v1/batches` | ایجاد دسته + پیشرفت |

## ۲) قرارداد payload (دقت ۱۰۰٪ ثبت)

هر job از ساختار کامل `WaybillMapRequest` ساخته می‌شود. `base_payload_json` (اجباری در `POST /api/v1/batches`) باید شامل باشد:

- `sender`: `{"name": "نام نام‌خانوادگی" (حداقل ۲ کلمه), "national_code": کد ملی معتبر (اختیاری)}`
- `receiver`: مشابه sender
- `cargo`: `{"type", "packaging", "weight" (>0), "value"}` — هر چهار فیلد **اجباری**
- `vehicle`: `{"driver_national_code": کد ملی معتبر, "plate": پلاک}` — هر دو **اجباری**
- مبدأ/مقصد از قالب مسیر override می‌شوند؛ استان/شهر/آدرس هر مسیر **اجباری** (حداقل ۲ کاراکتر).

هنگام ایجاد دسته، سرویس payload ادغام‌شده را با `validate_enhanced_waybill_payload` اعتبارسنجی می‌کند و در صورت ناقص بودن، `422` با فهرست دقیق فیلدهای غایب برمی‌گرداند — به‌جای آنکه jobها بعداً در وضعیت `NEEDS_REVIEW` شکست بخورند.

## ۳) اجرای فاصلهٔ زمانی (ضد اسپم)

- `submit_after` هر job با `step × interval_minutes` پلکانی می‌شود.
- `plan_due_jobs` برای وضعیت `pending` فقط `submit_after` را می‌سنجد؛ بنابراین رعایت `interval_minutes` تضمین می‌شود.
- `driver_id` اجباری است (jobهای بدون راننده توسط `plan_due_jobs` که روی `Driver` inner join می‌زند دیده نمی‌شوند).

## ۴) تنظیمات Neshan (`.env`)

| متغیر | پیش‌فرض | شرح |
|---|---|---|
| `NESHAN_API_KEY` | `""` | کلید API مسیریابی نشان؛ خالی = فقط هاورساین (بدون فراخوانی خارجی) |
| `NESHAN_TIMEOUT_SECONDS` | `3.0` | timeout فراخوانی |
| `NESHAN_CACHE_TTL_SECONDS` | `604800` | TTL کش (۷ روز)؛ فقط نتایج Neshan کش می‌شوند |

> سرویس Neshan **فقط** برای محاسبهٔ read-only فاصله/زمان استفاده می‌شود؛ هرگز فیلدهای خالی province/city/address را پر/حدس نمی‌زند (مطابق قرارداد `USER_TEXT_ROUTE_CONTRACT.md`).

## ۵) نکتهٔ استقرار

```bash
alembic upgrade head   # یا: bash manage.sh migrate
```

پس از اجرا، head باید `038_add_multiroute_batch_distance` باشد.

# وضعیت عملیاتی BarPro — 2026-09-09

این سند وضعیت همین انتشار را از «کد»، «runtime» و «ثبت واقعی UTCMS» جدا می‌کند. باز بودن سرویس‌ها یا موفقیت مرورگر به‌تنهایی سند ثبت بارنامه نیست.

## وضعیت انتشار

| حوزه | وضعیت | معیار اثبات |
|---|---|---|
| کد محلی | تغییرات امنیتی و session آماده‌ی انتشار | تست و diff همین commit |
| Central | healthy در آخرین بررسی ثبت‌شده | `healthz`، `readyz`، inventory و image checksum |
| Worker 1 | قابل استفاده با `AVAILABLE_IP_INDICES=1` | heartbeat تازه، proxy egress و queue consumer |
| Worker 2/3 | قابل اعتماد فرض نمی‌شوند | heartbeat قبلی stale و SSH در دسترس نبوده است |
| TLS | فعال نشده | nginx فعلاً HTTP است؛ `AUTH_COOKIE_SECURE` نباید بدون TLS تغییر کند |
| Deep Security Scan | انجام نشده | ابزار به managed filesystem permission profile نیاز داشت |

## وضعیت بارنامه‌ها

- Job `61` تنها موردی است که در آخرین بررسی سه شاهد لازم را داشت: tracking code، ذخیره در `result_json` و رکورد متناظر History؛ سند UTCMS آن `215477251` است.
- Jobهای `62`, `63`, `64`, `66`, `67`, `68`, `69`, `71` در وضعیت `needs_review/submission_unconfirmed` باقی مانده‌اند و بدون tracking code معتبر نباید دوباره submit شوند.
- هیچ Job مبهمی به‌صورت خودکار resubmit نمی‌شود؛ این رفتار برای جلوگیری از ثبت تکراری الزامی است.

## رفتار خودکار صبح

چرخه‌ی مجاز چنین است:

1. scheduler به‌صورت دوره‌ای وضعیت زنده‌ی دروازه را می‌خواند.
2. پیش‌بینی ساعت `17:30–08:00` فقط telemetry است و مجوز ثبت نیست.
3. تا وقتی observation معتبر `OTP_FREE` موجود نباشد، Jobهای آماده در `WAITING_SUBMISSION_WINDOW` یا backoff باقی می‌مانند.
4. پس از observation معتبر `OTP_FREE`، scheduler فقط Jobهای دارای payload معتبر، زمان `next_retry_at/submit_after` رسیده، driver lock آزاد و worker/proxy سالم را به صف می‌فرستد.
5. فاصله‌گذاری ضد محدودیت UTCMS و concurrency مؤثر ۱ برای هر Worker حفظ می‌شود.
6. نتیجه‌ی موفق فقط بعد از سه شاهد reconciliation به `success` تبدیل می‌شود؛ هر نتیجه‌ی مبهم به `needs_review` می‌رود و resubmit خودکار ندارد.

بنابراین با برداشته‌شدن OTP، سیستم می‌تواند ثبت Jobهای آماده را خودکار آغاز کند، اما «بدون هیچ مشکلی» از قبل قابل تضمین نیست؛ سلامت واقعی UTCMS، CAPTCHA، proxy، payload و History باید در همان لحظه تأیید شوند.

## چک پیش از live submit

```bash
bash manage.sh health
docker compose -f compose/backend.yml exec celery_scheduler \
  python -c 'from app.services.utcms_submission_gate import UTCMSSubmissionGate; print("gate probe is owned by scheduler")'
docker compose -f compose/infra.yml exec postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "SELECT job_id,status,mutation_status,reconciled_at FROM waybill_jobs ORDER BY updated_at DESC LIMIT 20;"
```

ثبت واقعی فقط از مسیر API/scheduler رسمی و با payload واقعی انجام می‌شود. manual override، داده‌ی ساختگی، یا اجرای مستقیم POST ثبت برای دور زدن gate مجاز نیست.

## انتشار و پایش

پس از push به GitHub، روی Central ابتدا backup و fast-forward انجام می‌شود، سپس migration قفل‌شده، build، recreate سرویس‌ها و health verification اجرا می‌شود. روی Workerهای ریموت فقط در صورت دسترسی SSH و heartbeat تازه deploy انجام می‌شود؛ timeout آن‌ها موفقیت deployment را ثابت نمی‌کند.

برای پایش زنده، لاگ‌های scheduler و worker و وضعیت queue را بررسی کنید:

```bash
docker logs --since 10m barpro-celery-scheduler
docker logs --since 10m barpro-celery-worker-1
docker ps --format 'table {{.Names}}\t{{.Status}}'
```

## کارهای باز

1. نصب TLS و تنظیم `AUTH_COOKIE_SECURE=true` پس از تهیه‌ی دامنه/گواهی.
2. کاهش بدهی mypy و افزودن contract test برای frontend/backend.
3. بازگرداندن Worker 2/3 فقط پس از حل SSH، heartbeat و egress verification.
4. اجرای dry-run جدید برای هر payload قبل از live submit.

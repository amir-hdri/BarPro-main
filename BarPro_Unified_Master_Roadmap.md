# 🚀 BarPro — نقشه‌راه نهایی یکپارچه (Unified Master Roadmap v2.0)

> **هدف سند:** ادغام دو پلان قبلی (`plan.rtf` و `MASTER_ROADMAP.md`)، رفع تناقض‌ها و باگ‌های شناسایی‌شده، و ارائه یک نقشه‌راه واحد، بدون تصادم Migration، آماده اجرا توسط یک ایجنت کدنویسی هوش مصنوعی (مثل Claude Code).
> **نسخه:** 2.0 | **وضعیت:** Ready for Agent Execution — مشروط به تکمیل بخش «تصمیمات باز» در بخش ۵
> **معماری منتخب هسته:** الگوی **Dispatch Intent** (از `plan.rtf`) به‌عنوان معماری کانونیک، چون تنها الگویی است که مشکل ریشه‌ای «سه مسیر اجرای موازی» را واقعاً حل می‌کند.

---

## ⚠️ صداقت روش‌شناختی (قبل از هر چیز بخوانید)

این سند از تحلیل و ادغام دو سند ورودی (`plan.rtf` و `MASTER_ROADMAP.md`) ساخته شده، **نه از دسترسی مستقیم به ریپوی کد BarPro**. یعنی:

- تمام ارجاعات `فایل:خط` که در این سند آمده، از دو سند مبدأ کپی شده‌اند و **باید قبل از هرگونه تغییر کد توسط ایجنت، در ریپوی واقعی تأیید شوند** (ممکن است کد از زمان نوشتن آن اسناد تغییر کرده باشد).
- هر جا که یک ادعای فنی در یکی از دو سند مبدأ **بدون شاهد کد** ارائه شده بود (مهم‌ترین مورد: URL و CSS selectorهای صفحه لیست بارنامه UTCMS در `MASTER_ROADMAP.md`)، در این سند با برچسب **`⚠️ UNVERIFIED`** علامت‌گذاری شده و اجرای آن مشروط به تأیید مستقل شده است.
- یک باگ فنی واقعی در `MASTER_ROADMAP.md` (ترکیب نادرست `asyncio.create_task` و `asyncio.run` داخل تابع سینکرون Celery، و register/deregister کردن Worker به‌ازای هر job به‌جای یک‌بار در startup) در این سند **اصلاح شده** است (بخش ۷، فاز ۲).

**دستور به ایجنت اجراکننده:** هیچ تسکی از این سند را بدون Verification مرحله «پیش‌نیاز» آن شروع نکن. اگر ارجاع فایل:خطی که در سند آمده با کد واقعی مطابقت نداشت، سند را نادیده نگیر — همان الگو/قصد را در محل واقعی کد پیاده کن و در گزارش پیشرفت این تفاوت را ثبت کن.

---

## ۰. دستورالعمل اجرا برای ایجنت هوش مصنوعی

1. **ترتیب اجرا خطی نیست ولی وابستگی‌ها الزامی است.** به بخش ۸ (Dependency Graph) مراجعه کن؛ هرگز فازی را قبل از تکمیل فازهای پیش‌نیازش شروع نکن.
2. **هر فاز = یک Feature Branch جدا + یک PR جدا.** هرگز مستقیم روی `main` کار نکن.
3. **قبل از شروع هر فاز:** پیش‌نیازهای Verification آن فاز را چک کن (بخش‌های `🔍 Verification قبل از شروع`).
4. **قبل از شروع هر Task کد:** فایل مقصد را واقعاً باز و بخوان؛ اگر مسیر/خط ذکرشده در سند با واقعیت فرق داشت، بر اساس کد واقعی عمل کن.
5. **بعد از هر فاز:** تمام معیارهای پذیرش (Acceptance Criteria) آن فاز را چک‌باکس بزن؛ تست‌های موجود (baseline) + تست‌های جدید فاز باید Pass باشند؛ سپس PR را برای تأیید انسانی باز بگذار.
6. **در چهار نقطهٔ Gate (زیر) اجرا را متوقف کن و منتظر تأیید انسانی بمان:**
   - قبل از فاز ۰: تأیید سه تصمیم باز (بخش ۵)
   - قبل از فاز ۶ (Reconciliation): نتیجهٔ Health Probe (فاز ۵) باید توسط انسان تأیید شود
   - قبل از اعمال هر Migration روی Production: تأیید صریح انسانی + بکاپ دیتابیس
   - قبل از فاز ۱۳ (Go-Live): چک‌لیست کامل بخش ۱۱ باید سبز باشد
7. **هرگز** یک مسیر اجرای جدید کنار مسیرهای قدیمی اضافه نکن — هدف فاز ۱ *حذف* مسیرهای موازی است، نه افزودن مسیر چهارم.
8. در پایان هر فاز، فایل `PROGRESS.md` را (اگر وجود ندارد بساز) با وضعیت فاز، تاریخ، و لینک PR به‌روزرسانی کن.

---

## ۱. خلاصه اجرایی

**مسئله:** BarPro در حال حاضر روی یک سرور با ۳ Celery Worker هاردکدشده کار می‌کند؛ سه مسیر اجرای موازی به یک جدول می‌نویسند (ریسک race condition)، heartbeat فقط در حافظهٔ محلی است (crash worker قابل تشخیص در سطح سیستم نیست)، session‌ها روی فایل‌سیستم محلی‌اند (قابل اشتراک بین سرورها نیستند)، و هیچ مکانیزم Reconciliation با پورتال UTCMS وجود ندارد.

**راه‌حل:** معماری **Central (۱ سرور) + N Worker (سرورهای مجزا)** با:
- PostgreSQL به‌عنوان **تنها منبع حقیقت** برای ترتیب و وضعیت (نه Redis، نه حافظه)
- الگوی **Dispatch Intent**: Scheduler → جدول `dispatch_intents` → Dispatcher → Worker claim با `fencing_token`
- **State Machine مرکزی** برای جلوگیری از transition‌های نامعتبر
- **Driver FIFO** با Partial Unique Index در PostgreSQL (نه فقط Redis lock)
- **Session Vault** روی Redis با رفتار fail-closed
- **Reconciliation** مشروط به نتیجهٔ Health Probe واقعی روی UTCMS
- **WireGuard VPN** برای اتصال امن Worker‌های Remote
- **Beat HA** با ترجیح استفاده از کتابخانهٔ اثبات‌شدهٔ `celery-redbeat` به‌جای leader-election دستی

**افق زمانی تخمینی:** ~۲۰-۲۲ هفته (بسته به موازی‌سازی فازها و تعداد نیروی توسعه)

---

## ۲. اصول بنیادی و تعاریف

### ۲.۱ اصول (غیرقابل‌مذاکره در طول اجرا)

| اصل | دلیل |
|---|---|
| PostgreSQL = منبع حقیقت | ترتیب و وضعیت Job باید در restart/failover قابل بازسازی باشد |
| Redis = فقط سیگنال سریع، هرگز منبع حقیقت | قطع Redis نباید داده را از بین ببرد یا وضعیت را گم کند |
| هر Execution یک `fencing_token` دارد | جلوگیری از duplicate submit وقتی Worker crash می‌کند و دوباره claim می‌شود |
| بدون هیچ Worker Count هاردکد | افزودن Worker جدید نباید نیازمند تغییر کد Scheduler/API باشد |
| **یک مسیر اجرای کانونیک** | فاز ۱ باید هر سه مسیر موازی فعلی را ادغام کند؛ افزودن مسیر جدید ممنوع |
| Session بین Worker‌ها مشترک است | Worker Remote نباید مجبور به login دوباره شود |
| بدون Silent Exception (`except: pass`) | هر خطا باید log/classify شود |
| هیچ فرض تأییدنشده به‌عنوان واقعیت اجرا نمی‌شود | مورد UTCMS selectors — باید Health Probe واقعی اجرا شود |

### ۲.۲ واژه‌نامه

| مفهوم | تعریف |
|---|---|
| **Job** | درخواست ثبت بارنامه؛ ثابت می‌ماند |
| **Execution** | هر بار اجرای واقعی یک Job؛ متغیر است، چند بار می‌تواند تکرار شود |
| **Dispatch Intent** | رکورد PostgreSQL که نشان می‌دهد Scheduler می‌خواهد یک Operation را به یک Queue بفرستد — منبع حقیقت ترتیب |
| **fencing_token** | عدد monotonically افزاینده که مالکیت یک Execution را تضمین می‌کند؛ Worker بدون token معتبر نمی‌تواند commit کند |
| **Lease** | قفل زمان‌دار (۱۲۰ ثانیه) در PostgreSQL + heartbeat تأییدی در Redis |
| **Operation** | نوع عملیات: `WAYBILL_SUBMIT`, `WAYBILL_AUTH`, `FUEL_INQUIRY`, `RECOVERY`, `RECONCILIATION` |
| **Queue** | صف Operation-Based بدون suffix عددی: `barpro.waybill.submit`, `barpro.waybill.auth`, `barpro.fuel.inquiry`, `barpro.recovery`, `barpro.reconciliation`, `barpro.scheduled` |

---

## ۳. خلاصهٔ Audit وضعیت فعلی (ادغام‌شده، با برچسب اعتبار)

| یافته | منبع | برچسب |
|---|---|---|
| سه مسیر اجرای موازی روی `waybill_jobs` می‌نویسند (`tasks.py`, `phase1_tasks.py`, `scheduled_waybill_executor.py`) | هر دو سند | ✅ تأیید متقاطع (هر دو سند مستقل به آن اشاره کرده‌اند) |
| Heartbeat فقط در حافظهٔ محلی پروسه (`worker_heartbeat.py`) | هر دو سند | ✅ تأیید متقاطع |
| `QUEUE_ENABLED` پیش‌فرض `False` در production | هر دو سند | ✅ تأیید متقاطع |
| Worker count هاردکد `(1,2,3)` در چند فایل | هر دو سند | ✅ تأیید متقاطع |
| Session روی فایل‌سیستم محلی، غیرقابل‌اشتراک بین سرورها | هر دو سند | ✅ تأیید متقاطع |
| Webhook alert بدون HMAC signature | هر دو سند | ✅ تأیید متقاطع |
| رمز SSH سرور در تاریخچهٔ git لو رفته و rotate نشده | هر دو سند | ✅ تأیید متقاطع — **بحرانی، اقدام فوری خارج از کد لازم است** |
| Beat یک نمونهٔ تک‌نقطه‌ای (SPOF) | هر دو سند | ✅ تأیید متقاطع |
| State Machine در ۳+ فایل به‌صورت پراکنده و مستقیم نوشته می‌شود | فقط `plan.rtf` | ⚠️ نیاز به تأیید مستقل در کد |
| منطق طبقه‌بندی خطا در ۳ فایل مختلف با روش‌های متفاوت (substring/mapping/hardcoded codes) | فقط `plan.rtf` | ⚠️ نیاز به تأیید مستقل در کد |
| URL و selector صفحهٔ لیست بارنامهٔ UTCMS (`barname.utcms.ir/.../HagigiHogugi`, `#TrackingCode`, `.search-btn`) | فقط `MASTER_ROADMAP.md` | ❌ **`UNVERIFIED`** — هیچ شاهد کدی برای این selectorها ارائه نشده؛ ممکن است حدسی/نمونه باشند. **قبل از فاز ۶ باید با Health Probe واقعی روی staging تأیید شوند.** |

---

## ۴. معماری هدف

```
┌────────────────────────────────────────────────────────────────────┐
│                         USER / BROWSER                              │
│                     Next.js (apps/web)                              │
└──────────────────────────────┬───────────────────────────────────────┘
                                │ HTTPS
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│                    NGINX (Reverse Proxy) — Port 80/443              │
└──────────────────────────────┬───────────────────────────────────────┘
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│                     CENTRAL SERVER (≈10 GB RAM)                     │
│  ┌──────────┐ ┌────────┐ ┌────────────┐ ┌───────────┐ ┌──────────┐│
│  │ FastAPI  │ │  Beat  │ │ Dispatcher │ │ Prometheus│ │WebSocket ││
│  │ 512MB    │ │(redbeat)│ │ Service   │ │ + Alerts  │ │   Hub    ││
│  └────┬─────┘ └───┬────┘ └─────┬──────┘ └─────┬─────┘ └────┬─────┘│
│       └───────────┴────────────┴──────────────┴────────────┘      │
│  ┌──────────────────────┐   ┌──────────────────────┐              │
│  │ PostgreSQL 16 (1.5GB) │   │ Redis 7 (256MB)      │              │
│  │ SOURCE OF TRUTH       │   │ Heartbeat + Session   │              │
│  │ dispatch_intents      │   │ Cache + Beat lock     │              │
│  │ executions            │   └──────────────────────┘              │
│  │ worker_registry       │                                          │
│  └──────────────────────┘                                          │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ WireGuard: Address 10.10.0.1/24, ListenPort 51820             │ │
│  └──────────────────────────────────────────────────────────────┘ │
└──────────────────────────────┬───────────────────────────────────────┘
                                │ WireGuard tunnel (TLS + AES-256)
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│ WORKER NODE 1  │      │ WORKER NODE 2  │ ...  │ WORKER NODE N  │
│  (4-6 GB)      │      │  (4-6 GB)      │      │  (4-6 GB)      │
│ Celery Worker  │      │ Celery Worker  │      │ Celery Worker  │
│ heartbeat(bg   │      │                │      │                │
│  thread→Redis) │      │                │      │                │
│ lease renewal  │      │                │      │                │
│  (→PostgreSQL) │      │                │      │                │
│ Squid Proxy    │      │ Squid Proxy    │      │ Squid Proxy    │
│ (network_mode: │      │ (network_mode: │      │ (network_mode: │
│  host)         │      │  host)         │      │  host)         │
└───────────────┘      └───────────────┘      └───────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │   UTCMS Portal          │
                    │   barname.utcms.ir      │
                    │   (بدون API عمومی)      │
                    └────────────────────────┘
```

### ۴.۱ Queue Topology (بدون suffix عددی — همهٔ Worker‌ها همهٔ Queueها را consume می‌کنند)

| Queue | Producer | Consumer | Workload |
|---|---|---|---|
| `barpro.waybill.submit` | Dispatcher | همهٔ Worker‌ها | ثبت بارنامه |
| `barpro.waybill.auth` | Dispatcher | همهٔ Worker‌ها | Refresh session |
| `barpro.fuel.inquiry` | API | همهٔ Worker‌ها | استعلام سوخت |
| `barpro.recovery` | Recovery Loop | Worker اختصاصی | Lease reclaim |
| `barpro.reconciliation` | API + Recovery | Worker اختصاصی | تأیید UTCMS |
| `barpro.scheduled` | Beat | همهٔ Worker‌ها | Cron schedules |

---

## ۵. تصمیمات باز — نیازمند تأیید انسانی قبل از شروع فاز ۰

| # | تصمیم | گزینه‌ها | پیشنهاد این سند |
|---|---|---|---|
| ۱ | Health Probe برای UTCMS | (الف) تیم جدا قبل از فاز ۶ بررسی کند (ب) تا فاز ۶ صبر و همان‌جا انجام شود | (ب) — به‌عنوان فاز ۵ رسمی در این سند گنجانده شده، نه یک وظیفهٔ جانبی |
| ۲ | Backend اشتراک Session | Redis / NFS / PostgreSQL JSONB | **Redis** — atomic، TTL بومی، هر دو سند مبدأ هم به آن رسیده بودند |
| ۳ | برنامهٔ فیزیکی Scale | Central ۱۰GB + N Worker ۴-۶GB با WireGuard | تأیید‌شده در هر دو سند — بدون تغییر |
| ۴ | مکانیزم Beat HA | Leader-election دستی روی Redis / کتابخانهٔ `celery-redbeat` | **`celery-redbeat`** — راه‌حل اثبات‌شدهٔ صنعتی؛ هیچ‌کدام از دو سند مبدأ به آن اشاره نکرده بودند و leader-election دستی هر دو سند دارای اشکالات پیاده‌سازی بود (بخش ۷، فاز ۹) |
| ۵ | آیا مسیرهای قدیمی (`tasks.py`, `phase1_tasks.py`) بلافاصله حذف شوند یا ابتدا Deprecate و بعد حذف؟ | حذف فوری / Deprecate با Feature Flag سپس حذف در فاز بعد | **Deprecate با Feature Flag** — کاهش ریسک Canary، مطابق پیشنهاد Risk Matrix هر دو سند |

**⛔ ایجنت نباید فاز ۰ را بدون تأیید صریح انسانی روی این ۵ مورد شروع کند.**

---

## ۶. برنامهٔ یکپارچهٔ Migration دیتابیس (شماره‌گذاری واحد، بدون تصادم)

> **نکتهٔ اصلاحی مهم:** دو سند مبدأ از شماره‌های ۰۲۰ تا ۰۲۴ برای Migration های کاملاً متفاوتی استفاده کرده بودند (تصادم مستقیم). این جدول شماره‌گذاری واحد و نهایی است.

| # | نام فایل | توضیح | جایگزین کدام پیشنهاد قبلی |
|---|---|---|---|
| 020 | `020_dispatch_intents.py` | جدول اصلی dispatch (منبع حقیقت ترتیب) | `plan.rtf` #020 |
| 021 | `021_worker_registry.py` | ثبت Worker برای heartbeat توزیع‌شده | مشترک هر دو سند، schema بر اساس `plan.rtf` |
| 022 | `022_executions.py` | Lease + fencing_token + نتیجهٔ اجرا | `plan.rtf` #022 (جایگزین رویکرد سادهٔ MASTER_ROADMAP #020) |
| 023 | `023_driver_active_slot.py` | ستون‌های `driver_runtime_states` + Partial Unique Index برای FIFO | مشترک هر دو سند (مفهوم یکسان، شماره یکی شد) |
| 024 | `024_admin_alerts.py` | جدول alert‌های ادمین + dedupe key | `plan.rtf` #024 |
| 025 | `025_auth_lock_coherency.py` | `auth_lock_owner`, `auth_lock_acquired_at`, `auth_lock_ttl_seconds` روی `driver_runtime_states` | از `MASTER_ROADMAP.md` #023 گرفته شد؛ در `plan.rtf` معادل کد نداشت |
| 026 | `026_error_category_backfill.py` | Data migration یکسان‌سازی مقادیر قدیمی `error_category` | از `MASTER_ROADMAP.md` #024 گرفته شد — **باید همراه با Task 1.7 (رفع کد) اجرا شود، نه به‌تنهایی** |

**تصمیم طراحی آگاهانه:** جدول جداگانهٔ `reconciliation_logs` (پیشنهاد `MASTER_ROADMAP.md` #022) ایجاد **نمی‌شود** — چون جداول موجود `WaybillTaskLog` و `DomainEvent` (طبق `plan.rtf`) همان نقش را بدون افزودن جدول تکراری پوشش می‌دهند. این یک اصلاح برای کاهش پیچیدگی schema است.

**ترتیب اجرا:** `020 → 021 → 022 → 023 → 024 → 025 → 026` (هرکدام ممکن است به قبلی FK داشته باشد؛ ترتیب باید رعایت شود)

**Rollback هر Migration:** هر فایل Migration باید تابع `downgrade()` معکوسِ کامل داشته باشد (drop column/table به‌ترتیب معکوس). قبل از اجرای هر Migration روی Production: بکاپ کامل دیتابیس الزامی است (`bash manage.sh backup-db` یا معادل).

---

## ۷. فاز‌به‌فاز

### Pre-0 — امنیت (قبل از هرگونه کدنویسی)
**اولویت:** بحرانی | **مدت:** ۱-۲ روز | **وابستگی:** هیچ

| # | کار | دلیل |
|---|---|---|
| Pre-0.1 | چرخش رمز SSH واقعی سرور تولید + ذخیره در secret manager (Vault/1Password) | رمز در `AGENTS.md` لو رفته و rotate نشده — ریسک فعال |
| Pre-0.2 | اسکن کامل git history برای credential‌های دیگر لو‌رفته | جلوگیری از تکرار مشکل |
| Pre-0.3 | افزودن `.env.example` کامل با تمام متغیرهای جدید که در فازهای بعد لازم می‌شوند (`ALERT_WEBHOOK_SECRET`, `WIREGUARD_ENDPOINT`, ...) | جلوگیری از کشف دیرهنگام متغیرهای گم‌شده |

**Acceptance:** سرور با رمز تازه + هیچ credential لورفته در ریپو + `.env.example` به‌روز.
**Rollback:** ندارد (تغییر فقط در سطح سرور/secret manager، نه کد).

---

### Phase 0 — Configuration Hardening
**اولویت:** بحرانی | **مدت:** ۲-۳ روز | **وابستگی:** Pre-0

| # | Task | فایل هدف (نیازمند تأیید مسیر واقعی) | تغییر |
|---|---|---|---|
| 0.1 | `QUEUE_ENABLED=true` در production | `app/core/config.py`, `.env` | `_to_bool(os.getenv("QUEUE_ENABLED", "True"))` |
| 0.2 | `QUEUE_INLINE_FALLBACK=false` | همان | جلوگیری از اجرای مخفیانهٔ inline |
| 0.3 | حذف binding صف‌های مرده (`_1`/`_2` بدون consumer) | `compose/backend.yml` | حذف از دستور `-Q` هر Worker |
| 0.4 | `--prefetch-multiplier=1` صریح برای همهٔ Worker | `compose/backend.yml` | هر Worker با browser slot محدود، دو Job رزرو نکند |
| 0.5 | HMAC-SHA256 + timestamp nonce روی webhook | `app/core/alerts.py` | نمونه کد در فاز ۱۰ (بخش Admin Alerts) |
| 0.6 | بررسی و رفع باقیماندهٔ `except: pass` | سراسر کدبیس | جایگزینی با log صریح یا طبقه‌بندی خطا |

**Acceptance:**
- [ ] تست‌های baseline موجود ۱۰۰٪ pass
- [ ] هیچ Job در production از مسیر inline عبور نکند (بررسی با log scraping)
- [ ] Webhook امضا‌شده + پنجرهٔ replay ۵ دقیقه
- [ ] رمز SSH واقعی rotate شده (از Pre-0)

**Rollback:** برگرداندن env varها به مقدار قبلی؛ بدون نیاز به Migration.

---

### Phase 1 — یکپارچه‌سازی بنیادین: State Machine + مسیر واحد + Error Taxonomy
**اولویت:** بحرانی (پایهٔ همهٔ فازهای بعد) | **مدت:** ۱.۵-۲ هفته | **وابستگی:** Phase 0

این فاز مهم‌ترین و پرریسک‌ترین فاز است چون رفتار موجود را تغییر می‌دهد. باید پشت Feature Flag و با Canary rollout انجام شود.

#### 1.1 State Machine مرکزی

**فایل جدید: `app/orchestrator/state_machine.py`**
```python
from enum import StrEnum


class JobStatus(StrEnum):
    PENDING = "pending"
    WAITING_AUTH = "waiting_auth"
    WAITING_RETRY = "waiting_retry"
    OTP_BACKOFF = "otp_backoff"
    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
    RECONCILING = "reconciling"


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending":        {"queued", "waiting_auth", "waiting_retry", "cancelled"},
    "waiting_auth":   {"queued", "pending", "cancelled"},
    "waiting_retry":  {"pending", "dead_letter", "cancelled"},
    "otp_backoff":    {"pending", "dead_letter", "cancelled"},
    "queued":         {"claimed", "waiting_retry", "cancelled"},
    "claimed":        {"running", "waiting_retry", "cancelled"},
    "running":        {"success", "failed", "needs_review", "waiting_retry", "otp_backoff", "unknown"},
    "needs_review":   {"pending"},
    "failed":         {"dead_letter"},
    "unknown":        {"reconciling"},
    "reconciling":    {"success", "failed", "needs_review"},
    "dead_letter":    set(),
    "cancelled":      set(),
    "success":        set(),
}


class StateTransitionError(Exception):
    pass


class JobStateMachine:
    @classmethod
    def transition(cls, session, job, target: str, *, expected_from: set[str] | None = None, **fields):
        if expected_from is None:
            expected_from = {job.status}
        if job.status not in expected_from:
            raise StateTransitionError(f"current {job.status!r} not in {expected_from}")
        if target not in ALLOWED_TRANSITIONS.get(job.status, set()):
            raise StateTransitionError(f"{job.status!r} → {target!r} not allowed")
        for key, value in fields.items():
            setattr(job, key, value)
        job.status = target
        session.add(job)
        return job

    @classmethod
    def assert_allowed(cls, current: str, target: str) -> None:
        if target not in ALLOWED_TRANSITIONS.get(current, set()):
            raise StateTransitionError(f"{current!r} → {target!r} not allowed")
```

#### 1.2–1.4 جایگزینی transition‌های مستقیم
- در هر فایلی که `job.status = X` مستقیم می‌نویسد (شناسایی با `grep -rn "\.status = " app/`) → جایگزین با `JobStateMachine.transition(...)`.
- **⚠️ Verification لازم:** خطوط دقیق ذکرشده در اسناد مبدأ (`waybill_worker.py:140,166,285,318,424-432,477`؛ `scheduled_waybill_executor.py:401-419`) باید در کد واقعی تأیید شوند — ممکن است شماره خط تغییر کرده باشد.

#### 1.5 ادغام سه مسیر اجرا در یک مسیر
- `app/workers/tasks.py` (`process_waybill_task`) → **Deprecate با Feature Flag** (طبق تصمیم #۵ بخش ۵)؛ در این فاز فقط warning-level log بنویسد و به مسیر جدید redirect کند.
- `app/workers/phase1_tasks.py` (`plan_phase1_jobs`) → منطق آن به Scheduler جدید (فاز ۲) منتقل و این فایل حذف می‌شود.
- `app/services/scheduled_waybill_executor.py` → منطق cron آن از طریق Dispatch Intent با `operation=SCHEDULED` یکپارچه می‌شود.
- همهٔ dispatch از این پس **فقط** از طریق `dispatch_intents` (فاز ۲) انجام می‌شود.

#### 1.6 هم‌ترازی Auth Lock
- قبل از acquire شدن `submit_lock_key`، ابتدا `auth_lock_key` نیز acquire شود.
- ستون‌های Migration 025 (`auth_lock_owner`, `auth_lock_acquired_at`, `auth_lock_ttl_seconds`) برای ثبت پایدار مالکیت قفل استفاده شوند (نه فقط Redis lock موقت).

#### 1.7 یکسان‌سازی واقعی Error Taxonomy (نه فقط Data Migration)
این تسک از هر دو سند ترکیب شده و **کامل‌تر از هرکدام به‌تنهایی** است:
- منطق substring matching در `waybill_worker.py` → جایگزین با `classify_exception()` از `app/core/error_taxonomy.py`
- کدهای هاردکد `"101"`/`"102"`/`"103"`/`"104"` در `fuel_inquiry_service.py` → جایگزین با `ErrorCategory` enum
- Mapping function در `rpa_submit_service.py` → جایگزین با همان `ErrorCategory` enum
- Migration 026 (data backfill مقادیر قدیمی) **بعد از** این تغییرات کد اجرا شود، نه قبل — در غیر این صورت رکوردهای جدید همچنان با مقادیر قدیمی نوشته می‌شوند.

#### 1.8 `where_for_update` روی همهٔ query‌های claim
در Scheduler: فقط Job‌هایی claim شوند که برای driverشان Execution فعالی وجود ندارد (پیش‌نیاز فاز ۳).

**Acceptance Criteria فاز ۱:**
- [ ] همهٔ transition‌ها از `JobStateMachine.transition()` عبور می‌کنند؛ هیچ `job.status = X` مستقیم خارج از `state_machine.py` باقی نمانده
- [ ] `tests/test_state_machine.py` با حداقل ۲۰ تست (مجاز/غیرمجاز) نوشته و pass شده
- [ ] هر سه مسیر قدیمی در یک مسیر ادغام شده‌اند (Feature Flag فعال، مسیر قدیمی فقط log می‌کند)
- [ ] `classify_exception()` در هر سه فایل استفاده می‌شود؛ هیچ substring matching یا کد هاردکد باقی نمانده
- [ ] Migration 026 بعد از استقرار کد جدید اجرا شده
- [ ] تست‌های baseline + تست‌های جدید فاز، ۱۰۰٪ pass

**Rollback:** Feature Flag را خاموش کن تا مسیر قدیمی دوباره فعال شود؛ Migration 026 دارای `downgrade()` برای بازگردانی مقادیر قدیمی از بکاپ.

---

### Phase 2 — Dispatch Intents + Worker Registry + Lease (با رفع باگ asyncio)
**اولویت:** بالا | **مدت:** ۲-۳ هفته | **وابستگی:** Phase 1

#### 2.1–2.3 Migration ها
طبق بخش ۶: `020_dispatch_intents.py`, `021_worker_registry.py`, `022_executions.py` — schema دقیق مطابق `plan.rtf` بخش Task 2.1–2.3 (شامل ایندکس‌های `idx_dispatch_intents_queue_pending`, `idx_executions_orphaned` و غیره).

#### 2.4 Scheduler (`app/orchestrator/scheduler_service.py`)
Job‌های آمادهٔ اجرا را با `SELECT ... FOR UPDATE SKIP LOCKED` می‌خواند و به `dispatch_intents` تبدیل می‌کند (کد کامل در `plan.rtf` Task 2.4).

#### 2.5 Dispatcher (`app/orchestrator/dispatcher_service.py`)
Intent‌های pending را با polling + `SKIP LOCKED` claim کرده و به Celery `send_task` می‌فرستد.

#### 2.6 Worker Claim Flow (اصلاح‌شده)
```python
# app/workers/waybill_worker.py
@celery_app.task(base=WaybillTask, name="barpro.waybill.execute")
def execute_dispatched_intent(intent_id: str):
    # الگوی موجود _run() برای اجرای کوروتین از داخل تسک سینکرون Celery
    return _run(_claim_and_execute(intent_id))


async def _claim_and_execute(intent_id: str):
    async with async_session_factory() as session:
        intent = await session.get(DispatchIntent, intent_id, with_for_update=True)
        if intent is None or intent.status != "claimed":
            raise StateTransitionError("intent not claimable")

        execution = Execution(
            job_id=intent.job_id,
            attempt_no=intent.attempt_no,
            operation=intent.operation,
            worker_id=WORKER_ID,
            fencing_token=intent.fencing_token,
            lease_expires_at=_utcnow_naive() + timedelta(seconds=120),
        )
        session.add(execution)
        await session.commit()
        execution_id = execution.execution_id

    # تمدید Lease در یک Thread پس‌زمینه (نه asyncio.create_task بدون event loop)
    stop_event = threading.Event()
    renewal_thread = threading.Thread(
        target=_renew_lease_sync_loop,
        args=(execution_id, intent.fencing_token, stop_event),
        daemon=True,
    )
    renewal_thread.start()
    try:
        result = await bot.execute_waybill_job(...)
        await _finalize(execution_id, intent_id, result)
        return result
    finally:
        stop_event.set()
        renewal_thread.join(timeout=5)
```

**🔧 رفع باگ نسبت به `MASTER_ROADMAP.md`:** در نسخهٔ اصلی، `asyncio.create_task(...)` بدون event loop در حال اجرا فراخوانی شده بود که خطای `RuntimeError: no running event loop` می‌دهد. در نسخهٔ بالا، تمدید Lease با یک **Thread سینکرون معمولی** انجام می‌شود (نه با یک coroutine معلق)، که در معماری Celery prefork واقعی و قابل‌اتکا است.

#### 2.7 تمدید Lease (نسخهٔ سینکرون صحیح)
```python
def _renew_lease_sync_loop(execution_id: str, fencing_token: int, stop_event: threading.Event):
    """اجرا در Thread جدا؛ از یک session/engine سینک یا event loop مستقل خودش استفاده می‌کند."""
    while not stop_event.wait(timeout=30):
        try:
            _run_sync_update_lease(execution_id, fencing_token)
        except Exception:
            logger.exception("lease_renewal_failed", extra={"execution_id": execution_id})
```

#### 2.8 Worker Registry + Startup (اصلاح‌شده — یک‌بار در startup، نه به‌ازای هر job)
```python
# app/orchestrator/worker_lifecycle.py
from celery.signals import worker_process_init, worker_process_shutdown

_heartbeat_stop = threading.Event()


@worker_process_init.connect
def on_worker_start(**kwargs):
    worker_id = os.environ.get("WORKER_ID", socket.gethostname())
    _run(register_worker(worker_id, hostname=socket.gethostname(),
                          capabilities=["waybill", "fuel"], capacity=1))
    threading.Thread(target=_heartbeat_loop, args=(worker_id,), daemon=True).start()


@worker_process_shutdown.connect
def on_worker_stop(**kwargs):
    _heartbeat_stop.set()
    worker_id = os.environ.get("WORKER_ID", socket.gethostname())
    _run(deregister_worker(worker_id))


def _heartbeat_loop(worker_id: str):
    while not _heartbeat_stop.wait(timeout=30):
        _run(send_heartbeat(worker_id))
```

**🔧 رفع باگ نسبت به `MASTER_ROADMAP.md`:** نسخهٔ اصلی `register_worker`/`deregister_worker` را داخل خودِ تابع `process_waybill_job` (یعنی به‌ازای هر Job!) صدا می‌زد. این هم از نظر کارایی غلط است (overhead دیتابیس در هر Job) و هم از نظر معنایی (Worker باید یک‌بار در طول عمر پروسه رجیستر شود، نه هر بار که یک Job می‌گیرد). نسخهٔ بالا از سیگنال‌های رسمی Celery (`worker_process_init`/`worker_process_shutdown`) استفاده می‌کند.

#### 2.9 Orphan Detector
`app/orchestrator/orphan_detector.py` — Execution‌هایی که `lease_expires_at` گذشته را `orphan` علامت زده و یک Dispatch Intent با `operation=RECONCILIATION` می‌سازد (کد کامل مطابق `plan.rtf` Task 2.9).

#### 2.10 حذف `worker_heartbeat.py`
بعد از مهاجرت کامل، فایل قدیمی حذف و `RecoveryManager.watchdog_loop` فقط از PostgreSQL/Redis جدید بخواند.

**Acceptance Criteria فاز ۲:**
- [ ] اگر یک Worker بمیرد، `lease_expires_at` آن در کمتر از ۹۰ ثانیه expire می‌شود
- [ ] Orphan Detector در کمتر از ۶۰ ثانیه بعد، Reconciliation ایجاد می‌کند
- [x] `worker_heartbeat.py` کاملاً deprecated و حذف شده
- [ ] هیچ `asyncio.create_task` بدون event loop در حال اجرا در کدبیس وجود ندارد (بررسی با grep + تست integration)
- [ ] Worker فقط یک‌بار در startup رجیستر می‌شود (نه به‌ازای هر Job) — قابل تأیید با شمارش ردیف‌های `worker_registry` نسبت به تعداد Job پردازش‌شده
- [ ] `tests/test_dispatch_intents.py`, `tests/test_execution_lease.py`, `tests/test_fencing_token.py` نوشته و pass شده

**Rollback:** Migration های 020-022 دارای `downgrade()`؛ Feature Flag برای بازگشت موقت به Scheduler قدیمی (تا زمانی که فاز ۱ کاملاً حذف نشده).

---

### Phase 3 — Driver FIFO Serialization
**اولویت:** بالا | **مدت:** ۱ هفته | **وابستگی:** Phase 2

- Migration `023_driver_active_slot.py`: ستون `active_execution_id` + Partial Unique Index روی `driver_runtime_states`.
- Scheduler فقط Job‌هایی را انتخاب می‌کند که راننده‌شان `active_execution_id IS NULL` دارد.
- بعد از اتمام هر Execution (موفق/ناموفق)، slot آزاد می‌شود.
- Fairness بین Tenant‌ها به PostgreSQL منتقل می‌شود (`COUNT(*)` روی وضعیت فعال به‌ازای `client_id`).

**Acceptance:**
- [ ] سه Job موازی برای یک راننده → فقط اولی اجرا می‌شود، بقیه در DB منتظر می‌مانند
- [ ] پس از تکمیل اولی، دومی در tick بعدی Scheduler شروع می‌شود
- [ ] Tenant slice در Scheduler چند-نمونه‌ای رعایت می‌شود
- [ ] `tests/test_driver_fifo.py` pass

**Rollback:** حذف ستون و ایندکس (`downgrade()` Migration 023).

---

### Phase 4 — Shared Auth State (Redis Session Vault) — موازی با فاز ۳
**اولویت:** بالا | **مدت:** ۱ هفته | **وابستگی:** Phase 1

- Backend: **Redis** (طبق تصمیم #۲ بخش ۵).
- `app/services/session_vault.py` بازنویسی می‌شود تا `store`/`load`/`delete`/`refresh` را روی Redis با TTL انجام دهد؛ متد قدیمی `auth_state_path_for_account` برای سازگاری عقب‌رو نگه داشته می‌شود.
- **رفتار fail-closed:** اگر Redis در دسترس نباشد، Worker باید Job را با وضعیت خطا متوقف کند، **نه** به یک fallback ناامن (مثل فایل محلی) سوییچ کند. این باید در `main.py` lifespan با health-check صریح تست شود.
- Session Versioning: هر بار login موفق، یک شمارندهٔ `session_version` افزایش می‌یابد؛ Worker با `version_mismatch` باید شکست بخورد (نه ادامه دهد با session قدیمی).

**Acceptance:**
- [ ] Worker A روی سرور یک login می‌کند → Worker B روی سرور دیگر بدون login دوباره اجرا می‌کند
- [ ] قطع Redis (شبیه‌سازی‌شده) → Worker‌ها fail-closed می‌شوند (alert صادر می‌شود، بدون data corruption)
- [ ] `tests/test_session_vault_redis.py`, `tests/chaos/test_redis_unavailable.py` pass

**Rollback:** بازگشت به فایل‌سیستم محلی از طریق Feature Flag (فقط برای اضطرار؛ single-server mode).

---

### Phase 5 — UTCMS Health Probe (فاز رسمی مستقل، نه زیرمجموعه)
**اولویت:** بحرانی برای فاز ۶ | **مدت:** ۲-۴ روز | **وابستگی:** Phase 4 (نیاز به Session Vault برای login)

این فاز **باید روی staging اجرا شود، نه production**، و صرفاً بررسی/مستندسازی است — بدون تغییر رفتار سیستم.

| گام | پرسش | خروجی مورد انتظار |
|---|---|---|
| H.1 | آیا صفحه‌ای برای «لیست بارنامه‌های ثبت‌شده» در `barname.utcms.ir` وجود دارد؟ | URL تأییدشدهٔ واقعی، یا نتیجهٔ صریح «یافت نشد» |
| H.2 | اگر بله، selectorهای جدول/رکورد چیست؟ | HTML snippet واقعی (نه حدسی) |
| H.3 | آیا WAF یا محدودیت دیگری وجود دارد؟ | بله/خیر + جزئیات |
| H.4 | نرخ Rate Limit چقدر است؟ | تعداد query مجاز در دقیقه |

**⚠️ توجه صریح به ایجنت:** URL و selectorهایی که در `MASTER_ROADMAP.md` (`https://barname.utcms.ir/barname/Document/HagigiHogugi`, `input[name='TrackingCode']`, `.search-btn`) آمده بودند **تأیید کد نداشتند** و نباید به‌عنوان مبنای پیاده‌سازی فاز ۶ استفاده شوند مگر این‌که در همین فاز ۵ به‌صورت مستقل روی UTCMS واقعی بازآزمایی و تأیید شوند.

**خروجی این فاز:** سند `docs/utcms_list_search_investigation.md` با نتیجهٔ H.1 تا H.4 — این سند تعیین می‌کند فاز ۶ در حالت Auto Reconciliation اجرا شود یا Manual-Only.

**Gate انسانی:** نتیجهٔ این فاز باید توسط یک انسان بازبینی و تأیید شود قبل از شروع فاز ۶.

---

### Phase 6 — Reconciliation Engine + Admin Alerts (مشروط به نتیجهٔ فاز ۵)
**اولویت:** متوسط | **مدت:** ۱.۵-۲ هفته | **وابستگی:** Phase 2, Phase 5 (Gate شده)

#### حالت الف — اگر Health Probe موفق بود (Auto Reconciliation)
- `app/orchestration/utcms_reconciliation_scraper.py` با selectorهای **واقعاً تأییدشده** از فاز ۵ نوشته می‌شود.
- `app/orchestrator/reconciliation_service.py`: برای هر Execution با وضعیت `unknown`/orphan، از `SessionVault` برای bypass login استفاده کرده، وضعیت را با UTCMS تطبیق می‌دهد، و بر اساس نتیجه (`REGISTERED`/`NOT_FOUND`/`AMBIGUOUS`) از طریق `JobStateMachine.transition` وضعیت را به‌روزرسانی می‌کند.
- Trigger ها: زمان‌بندی هر ۱۵ دقیقه (Beat)، بعد از بازیابی crash، و دستی از داشبورد ادمین.

#### حالت ب — اگر Health Probe ناموفق بود (Manual-Only Mode)
- صف `barpro.reconciliation` فقط Job‌های قطعاً ناموفق را دریافت می‌کند.
- بررسی توسط ادمین در UI (بدون auto-resolve).
- Alert با `severity=high` وقتی یک Job سه بار متوالی `submission_unknown` شود.

#### Admin Alert System (مستقل از نتیجهٔ Probe، همیشه پیاده‌سازی می‌شود)
- Migration `024_admin_alerts.py`.
- `app/orchestrator/alert_manager.py`: `INSERT ... ON CONFLICT (dedupe_key) DO NOTHING` برای idempotency؛ برای severity بالا، وب‌هوک HMAC-signed ارسال می‌شود.
- صفحهٔ ادمین `apps/web/src/app/admin/alerts/page.tsx`: لیست real-time (WebSocket)، دکمهٔ Acknowledge، فیلتر severity.

**Acceptance:**
- [ ] نتیجهٔ Health Probe مستند و توسط انسان تأیید شده
- [ ] بسته به نتیجه: Auto Reconciliation *یا* Manual-Only Mode پیاده‌سازی شده (هر دو کد نباید هم‌زمان نوشته شوند — فقط مسیر منطبق با نتیجهٔ واقعی)
- [ ] Alert سه‌بار `submission_unknown` → severity=high + webhook + dashboard
- [ ] Manual retry در UI بدون duplicate submission (با fencing_token چک می‌شود)
- [ ] `tests/test_reconciliation_service.py`, `tests/test_admin_alerts.py` pass

**Rollback:** غیرفعال‌سازی Beat task دوره‌ای؛ Migration 024 دارای `downgrade()`.

---

### Phase 7 — Scale-Out (WireGuard + حذف Worker Count هاردکد)
**اولویت:** بالا | **مدت:** ۱.۵-۲ هفته | **وابستگی:** Phase 4 + Phase 2

- حذف `for i in (1, 2, 3):` در `app/api/routes/system.py` → جایگزین با تابعی که از `worker_registry` واقعی می‌خواند.
- الگوی regex `squid_1/2/3` در `proxy_rotator.py` → جایگزین با pattern پویا `squid_\d+`.
- WireGuard: پیکربندی Central (`wg0.conf`) و Worker (`wg0-worker.conf`) طبق نمونهٔ بخش ۴.
- محدودسازی پورت PostgreSQL فقط به شبکهٔ WireGuard (`10.10.0.1:5432:5432`).
- **Role دیتابیس با کمترین دسترسی برای Worker‌ها:**
```sql
CREATE ROLE barpro_worker LOGIN PASSWORD '...';
GRANT CONNECT ON DATABASE utcms_rpa TO barpro_worker;
GRANT USAGE ON SCHEMA public TO barpro_worker;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO barpro_worker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO barpro_worker;
REVOKE CREATE, DROP, DELETE, TRUNCATE ON DATABASE utcms_rpa FROM barpro_worker;
```
- `compose/worker-node.yml` (Template) با `WORKER_ID` منحصربه‌فرد به‌ازای هر Node، `security_opt: [no-new-privileges:true]`، و محدودیت منابع.

**Acceptance:**
- [ ] Worker جدید فقط با تنظیم `WORKER_ID` + کلید WireGuard اضافه می‌شود — بدون تغییر Scheduler/Compose مرکزی
- [ ] تونل WireGuard از Worker به `10.10.0.1:5432` فعال و پایدار
- [ ] Worker‌ها نمی‌توانند `DELETE`/`CREATE`/`DROP` روی دیتابیس بزنند (`tests/test_wireguard_security.py`)
- [ ] همهٔ Container ها در بودجهٔ حافظهٔ سرور مرکزی (۱۰GB، headroom ≥ ۳GB) جا می‌شوند

**Rollback:** بازگشت به دسترسی IP عمومی (بدون WireGuard) به‌عنوان fallback موقت طبق Risk Matrix (بخش ۹).

---

### Phase 8 — Auto-Heal
**اولویت:** متوسط | **مدت:** ۳-۵ روز | **وابستگی:** Phase 2, Phase 7

| خطا | Auto-Heal | محل پیاده‌سازی |
|---|---|---|
| `proxy_failed` | تعویض پروکسی + retry | چک `check_proxy_health()` قبل از claim |
| `browser_crashed` | Recycle مرورگر | `browser_manager.recycle_browser()` |
| `network_error` | backoff نمایی + تعویض پروکسی | Retry logic موجود گسترش می‌یابد |
| بیش از ۳ شکست در ۱ دقیقه | Worker به حالت `draining` می‌رود | شمارندهٔ Redis `worker_retry_attempts` |

**Acceptance:**
- [ ] Proxy fail → Job بعدی در دقیقهٔ بعد با پروکسی دیگر
- [ ] Browser crash → recycle + retry خودکار
- [ ] تست شبیه‌سازی proxy dead

**Rollback:** غیرفعال‌سازی منطق Auto-Heal با Feature Flag، بازگشت به retry ساده.

---

### Phase 9 — Beat High Availability (با کتابخانهٔ اثبات‌شده به‌جای Leader-Election دستی)
**اولویت:** متوسط | **مدت:** ۳-۵ روز | **وابستگی:** Phase 2

**🔧 اصلاح نسبت به هر دو سند مبدأ:** هر دو سند leader-election دستی روی Redis برای Beat پیشنهاد داده بودند، اما پیاده‌سازی نمونه‌شان معیوب بود (تلاش برای ترکیب کوروتین async درون متد سینکرون/بلاکینگ `beat.start()` که عملاً heartbeat را در طول اجرای Beat مسدود می‌کند). **پیشنهاد این سند:**

1. **راه‌حل اصلی:** استفاده از کتابخانهٔ `celery-redbeat` (پکیج شناخته‌شده و production-ready برای Beat توزیع‌شده روی Redis) به‌جای leader-election دستی.
   ```bash
   pip install celery-redbeat
   ```
   ```python
   # celery_app.py
   app.conf.beat_scheduler = "redbeat.RedBeatScheduler"
   app.conf.redbeat_redis_url = REDIS_URL
   app.conf.redbeat_lock_timeout = 30
   ```
2. **راه‌حل مکمل (لایهٔ دوم دفاعی، ساده و مستقل):** Watchdog Cron خارجی که سلامت container را چک می‌کند و در صورت down بودن، restart می‌کند — این بخش از هر دو سند مبدأ حفظ می‌شود چون ساده و قوی است:
```bash
#!/bin/bash
# scripts/beat_watchdog.sh — هر دقیقه از crontab اجرا می‌شود
CONTAINER_NAME="barpro-beat"
if ! docker inspect --format='{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null | grep -q "true"; then
    echo "$(date): Beat container down, restarting..." >> /var/log/barpro/beat_watchdog.log
    docker start "$CONTAINER_NAME"
fi
```

**Acceptance:**
- [ ] فقط یک نمونهٔ Beat فعال، حتی اگر چند Container اجرا شود (تضمین‌شده توسط `redbeat`)
- [ ] اگر Beat container بمیرد، Watchdog در کمتر از ۵ دقیقه restart می‌کند
- [ ] تست: کشتن دستی Beat container → مشاهدهٔ ریکاوری خودکار

**Rollback:** بازگشت به Beat تک‌نمونه‌ای ساده بدون HA (فقط برای دورهٔ کوتاه اضطراری).

---

### Phase 10 — Observability
**اولویت:** بالا (باید همزمان با Production Hardening باشد) | **مدت:** ۱ هفته | **وابستگی:** Phase 2, 6, 8

| SLO | آستانه | Alert |
|---|---|---|
| نرخ موفقیت Job | کمتر از ۸۰٪ در ۱ ساعت | high |
| عمق صف به‌ازای هر Worker | بیشتر از ۱۰۰ | warning |
| Reconciliation backlog | بیشتر از ۲۰ در ۱۰ دقیقه | warning |
| Worker liveness | Heartbeat بیش از ۹۰ ثانیه قطع | critical |
| نرخ شکست کپچا | بیشتر از ۵۰٪ در ۵ دقیقه | high |
| سلامت پروکسی | کمتر از ۲ پروکسی سالم | critical |
| Connection pool دیتابیس | بیشتر از ۸۰٪ | warning |

- `infra/prometheus/alerts.yml` با rule های بالا.
- Alertmanager → webhook HMAC-signed به `ADMIN_ALERT_WEBHOOK_URL`.
- داشبورد Grafana: تعداد Worker فعال، عمق صف، نرخ موفقیت، Alertهای باز.
- فید Real-time WebSocket برای پنل ادمین (`event_hub.publish({"type": "admin.alert", ...})`).
- صفحهٔ `apps/web/src/app/admin/workers/page.tsx` برای نمایش Worker Registry (کد نمونه در Appendix).

**Acceptance:**
- [ ] Rule های Alertmanager فعال و تست‌شده
- [ ] داشبورد Grafana در دسترس در ناحیهٔ ادمین
- [ ] هر SLO نقض‌شده Alert صادر می‌کند

---

### Phase 11 — Test Suite (می‌تواند طی همهٔ فازها موازی پیش برود؛ این‌جا Gate نهایی است)
**اولویت:** بحرانی برای Go-Live | **مدت:** موازی، جمع‌بندی ۱ هفته آخر | **وابستگی:** همهٔ فازهای قبل

| فایل تست | هدف |
|---|---|
| `tests/test_state_machine.py` | ≥۲۰ تست transition مجاز/غیرمجاز |
| `tests/test_driver_fifo.py` | سه Job موازی برای یک راننده → فقط اولی اجرا |
| `tests/test_execution_lease.py` | مرگ Worker → orphan → صف Reconciliation |
| `tests/test_fencing_token.py` | Token mismatch → fail (جلوگیری از duplicate submit) |
| `tests/test_dispatch_intents.py` | چند نمونهٔ Scheduler → ترتیب DB-backed |
| `tests/test_reconciliation_service.py` | Mock پاسخ UTCMS → وضعیت درست |
| `tests/test_admin_alerts.py` | امضای webhook، dedupe، مسیریابی severity |
| `tests/test_wireguard_security.py` | Worker نمی‌تواند DELETE بزند |
| `tests/test_session_vault_redis.py` | اشتراک session بین Worker‌ها |
| `tests/load/test_500_jobs_per_hour.py` | تست بار |
| `tests/chaos/test_redis_unavailable.py` | قطع Redis → fail-closed |
| `tests/chaos/test_db_failover.py` | Restart Postgres → retry ایمن |
| `tests/integration/test_worker_lifecycle.py` | Startup → heartbeat → lease → shutdown (تأیید یک‌بار رجیستر شدن، نه به‌ازای هر Job) |

**Acceptance:**
- [ ] مجموع تست‌ها: ≥ (baseline موجود) + ۸۰ تست جدید
- [ ] صفر Failed، صفر Flaky در ۳ اجرای متوالی
- [ ] Load test: ۵۰۰ Job/ساعت بدون crash

---

### Phase 12 — Documentation & Runbook
**اولویت:** بالا | **مدت:** ۳-۵ روز | **وابستگی:** همهٔ فازهای قبل

| سند | محتوا |
|---|---|
| `docs/architecture.md` | نمودار معماری نهایی + جدول جریان داده |
| `docs/runbook_worker_registration.md` | چگونگی افزودن Worker Node جدید |
| `docs/runbook_utcms_outage.md` | اقدام هنگام قطعی UTCMS |
| `docs/runbook_failed_reconciliation.md` | بررسی Job با `submission_unknown × 3` |
| `docs/runbook_scale_out.md` | مراحل افزایش تعداد Worker |
| `docs/security_audit_checklist.md` | چک‌لیست پیش از هر Deploy |
| `docs/utcms_list_search_investigation.md` | خروجی فاز ۵ (Health Probe) |

---

### Phase 13 — Production Deployment & Go-Live
**اولویت:** بحرانی | **مدت:** ۱ هفته (شامل بافر برای مشکلات غیرمنتظره) | **وابستگی:** همهٔ فازهای قبل + چک‌لیست بخش ۱۱

#### مراحل استقرار
```bash
# ۱. بکاپ کامل دیتابیس
bash manage.sh backup-db

# ۲. استقرار سرور مرکزی
docker compose -f compose/infra.yml up -d
docker compose -f compose/wireguard.yml up -d
docker compose -f compose/backend.yml up -d
docker compose -f compose/web.yml up -d
docker compose -f compose/monitoring.yml up -d

# ۳. استقرار Worker ها (به‌ازای هر Worker Node، با WORKER_ID منحصربه‌فرد)
for node in worker-1 worker-2 worker-3; do
    ssh "$node" "cd /opt/barpro && docker compose -f compose/worker-node.yml up -d"
done

# ۴. بررسی سلامت
bash manage.sh health

# ۵. اجرای Smoke Test
pytest tests/smoke/ -v
```

#### برنامهٔ Rollback
```bash
git checkout <previous-commit>
docker compose down
docker compose -f compose/infra.yml up -d
docker compose -f compose/backend.yml up -d
docker compose -f compose/web.yml up -d
```

---

## ۷.۵ قابلیت چندمسیره + فاصله/زمان (Implemented — v2.9.3، 2026-08-23)

> این بخش خارج از فازهای ۰–۱۳ است و به‌عنوان یک قابلیت تکمیل‌شده ثبت می‌شود.

### هدف
ثبت بارنامه به‌صورت چندمسیره: تعریف چند مسیر (مبدأ→مقصد)، سپس گسترش آن‌ها به تعداد دلخواه بارنامه با رعایت فاصلهٔ زمانی ضد اسپم.

### اجزای پیاده‌سازی‌شده
| مؤلفه | مسیر / جدول |
|---|---|
| قالب مسیر | `waybill_route_template` (+ `app/services/route_template_service.py`) |
| دستهٔ چندمسیره | `waybill_batch` (+ `app/services/batch_service.py`) |
| سرویس فاصله/زمان | `app/services/distance_service.py` (Neshan → Redis → haversine) |
| migration | `038_add_multiroute_batch_distance` |
| API | `POST /api/v1/locations/distance`، `/api/v1/route-templates`، `/api/v1/batches` |
| تنظیمات | `NESHAN_API_KEY` / `NESHAN_TIMEOUT_SECONDS` / `NESHAN_CACHE_TTL_SECONDS` |

### نکات کلیدی صحت (تفاوت با نسخهٔ اولیهٔ پیشنهادی)
- PK ها `int` هستند (نه UUID)؛ `job_id` و `idempotency_key` رشته‌ای unique تولید می‌شوند.
- payload کامل `WaybillMapRequest`-سازگار ساخته می‌شود (sender/receiver/cargo/vehicle + origin/destination تودرتو).
- **دقت ۱۰۰٪:** ایجاد دسته، payload ادغام‌شده را با `validate_enhanced_waybill_payload` اعتبارسنجی می‌کند و کد ملی/پلاک راننده از `Driver`/`DriverPlate` غنی‌سازی می‌شود.
- فاصلهٔ زمانی با `submit_after` پلکانی می‌شود (نه `next_retry_at`)، تا `plan_due_jobs` آن را رعایت کند.
- `driver_id` اجباری است (job بدون راننده توسط `plan_due_jobs` دیده نمی‌شود).

### مستندات مرتبط
- `docs/MULTI_ROUTE_FEATURE.md`


## ۸. نمودار وابستگی و ترتیب اجرا

```
Pre-0 (SSH rotate)
  └─► Phase 0 (Config Hardening)
        └─► Phase 1 (State Machine + مسیر واحد + Error Taxonomy)   ◄── پرریسک‌ترین فاز
              ├─► Phase 2 (Dispatch Intents + Lease + Registry)
              │     ├─► Phase 3 (Driver FIFO)
              │     ├─► Phase 8 (Auto-Heal)
              │     └─► Phase 9 (Beat HA)
              │
              ├─► Phase 4 (Shared Auth State)         ◄── می‌تواند موازی با فاز ۲/۳ پیش برود
              │     └─► Phase 5 (UTCMS Health Probe)  ◄── Gate انسانی
              │           └─► Phase 6 (Reconciliation, مشروط)
              │
              └─► Phase 7 (Scale-Out / WireGuard)      ◄── نیازمند Phase 2 + Phase 4

بعد از پایداری هستهٔ ۱-۴:
  ├─► Phase 10 (Observability)     — باید طول Hardening تولید باشد
  ├─► Phase 11 (Test Suite)        — می‌تواند طی همهٔ فازها آغاز شود
  └─► Phase 12 (Documentation)     — طی پروژه به‌روزرسانی می‌شود

Phase 13 (Go-Live) ◄── فقط بعد از سبز شدن کامل چک‌لیست بخش ۱۱
```

**حداقل مسیر بحرانی:** `Pre-0 → 0 → 1 → 2 → 3 → 6 → 7 → 13`
**حداکثر موازی‌سازی:** فاز ۴ با فاز ۲/۳ موازی؛ فاز ۸/۹ با فاز ۷ موازی؛ فاز ۱۰/۱۱/۱۲ در طول کل پروژه جاری.

---

## ۹. ماتریس ریسک یکپارچه

| ریسک | احتمال | تأثیر | Mitigation | فاز |
|---|---|---|---|---|
| Selector/URL صفحهٔ لیست UTCMS نادرست از آب دربیاید | بالا (تا تأیید فاز ۵) | بلاک‌کنندهٔ فاز ۶ | Health Probe مستقل قبل از هرگونه کدنویسی Reconciliation | ۵ |
| ادغام سه مسیر اجرا شکست بخورد و duplicate submit ایجاد کند | متوسط | تکرار ثبت بارنامه (هزینهٔ واقعی/قانونی) | Feature Flag + Canary rollout + fencing_token | ۱ |
| اشتراک Session بین Worker‌ها پیچیده از آب دربیاید | متوسط | کندی Worker‌های Remote | Redis-backed session با تست chaos صریح | ۴ |
| Beat تک‌نقطه‌ای شکست بخورد | متوسط | توقف Job‌های زمان‌بندی‌شده | `celery-redbeat` + Watchdog دوگانه | ۹ |
| رمز SSH rotate نشود | قطعی اگر انجام نشود | ریسک امنیتی جدی | Pre-0 اجباری قبل از هر کد | Pre-0 |
| Webhook جعل شود | متوسط | Alert جعلی/گمراه‌کننده | HMAC signing + پنجرهٔ replay ۵ دقیقه | ۰، ۶ |
| RAM سرور Worker Remote کافی نباشد | کم | OOM در Worker | Load test قبل از افزودن Node جدید | ۷ |
| Role دیتابیس Worker به همهٔ query پاسخ ندهد | کم | شکست Worker در تولید | تست کامل در staging قبل از production | ۷ |
| Tenant slice در Scheduler چند-نمونه‌ای نشت کند | متوسط | یک Tenant تمام Worker‌ها را اشغال کند | شمارش DB-backed به‌جای شمارش حافظه‌ای | ۳ |
| fencing_token در میانهٔ اجرا منقضی شود | کم | علامت‌گذاری اشتباه orphan | Backoff + retry با margin زمانی کافی | ۲ |
| کد پیاده‌سازی‌شده با ارجاعات فایل:خط این سند مطابقت نداشته باشد | متوسط (چون سند از audit قبلی ساخته شده) | تأخیر جزئی، نه ریسک داده | ایجنت باید همیشه Verification مستقل انجام دهد (بخش «صداقت روش‌شناختی») | همهٔ فازها |

---

## ۱۰. خلاصهٔ گپ‌های رفع‌شده نسبت به دو سند مبدأ

۱. **تصادم شماره‌گذاری Migration (020-024 در هر دو سند برای چیزهای متفاوت)** → یکپارچه‌سازی به ۰۲۰-۰۲۶ با شرح دلیل هر انتخاب (بخش ۶).
۲. **ادعای selector/URL تأییدنشدهٔ UTCMS در `MASTER_ROADMAP.md`** → تبدیل به فاز رسمی مستقل Health Probe با Gate انسانی (فاز ۵)، بدون آن فاز ۶ اصلاً شروع نمی‌شود.
۳. **باگ `asyncio.create_task` بدون event loop + register/deregister Worker به‌ازای هر Job** → بازطراحی با Thread سینکرون + سیگنال‌های رسمی Celery (فاز ۲).
۴. **عدم ادغام سه مسیر اجرای موازی در `MASTER_ROADMAP.md`** → این ادغام اکنون Task صریح ۱.۵ در فاز ۱ است.
۵. **یکسان‌سازی سطحی Error Category (فقط Data Migration، بدون تغییر کد) در `MASTER_ROADMAP.md`** → Task 1.7 اکنون هم کد و هم داده را اصلاح می‌کند، با ترتیب صحیح اجرا (کد اول، Migration بعد).
۶. **عدم رسیدگی به State Machine پراکنده در `MASTER_ROADMAP.md`** → اکنون Task 1.1 است.
۷. **Leader-election دستی Beat با پیاده‌سازی معیوب در هر دو سند** → جایگزین با `celery-redbeat` (راه‌حل صنعتی اثبات‌شده) + Watchdog به‌عنوان لایهٔ دوم.
۸. **جدول `reconciliation_logs` تکراری در `MASTER_ROADMAP.md`** → حذف شد؛ جداول موجود `WaybillTaskLog`/`DomainEvent` استفاده می‌شوند.
۹. **عدم Rollback صریح برای Migration‌های فاز ۲ به بعد در `plan.rtf`** → هر Migration اکنون الزام `downgrade()` و بکاپ اجباری قبل از اجرای production دارد (بخش ۶، ۰، دستورالعمل ایجنت بند ۶).
۱۰. **فقدان دستورالعمل صریح برای یک ایجنت هوش مصنوعی در هر دو سند** → بخش ۰ این سند.

---

## ۱۱. معیارهای پذیرش نهایی (Go-Live)

### ۱۱.۱ عملکردی
- [ ] تمام تست‌های بخش ۱۱ (Phase 11) سبز، صفر Flaky در ۳ اجرای متوالی
- [ ] Load test: ۵۰۰ Job/ساعت بدون crash
- [ ] Worker crash در حین اجرا → Reconciliation در کمتر از ۹۰ ثانیه
- [ ] سه Job موازی برای یک راننده → فقط اولی اجرا، بقیه در DB
- [ ] قطع Redis → fail-closed، بدون data corruption
- [ ] Reconciliation UTCMS با نتیجهٔ Health Probe واقعی کار می‌کند (Auto یا Manual، هرکدام که تأیید شده)

### ۱۱.۲ امنیتی
- [ ] رمز SSH واقعی rotate شده و در secret manager است
- [ ] Webhook با HMAC + پنجرهٔ replay ۵ دقیقه
- [ ] تونل WireGuard بین Central و همهٔ Worker فعال
- [ ] Role دیتابیس Worker فقط دسترسی حداقلی دارد (بدون DELETE/CREATE/DROP)
- [ ] هیچ credential لورفته در ریپو باقی نمانده (اسکن نهایی)

### ۱۱.۳ زیرساختی
- [ ] سرور مرکزی در بودجهٔ ۱۰GB با headroom ≥ ۳GB
- [ ] افزودن Worker جدید فقط با `WORKER_ID` (بدون تغییر Scheduler/Compose مرکزی)
- [ ] Beat HA (`celery-redbeat` + Watchdog) فعال و تست‌شده

### ۱۱.۴ عملیاتی
- [ ] Admin Alert برای `submission_unknown × 3` ارسال می‌شود
- [ ] Manual retry در UI بدون duplicate submission
- [ ] تمام Runbook های بخش ۱۲ نوشته شده
- [ ] `PROGRESS.md` تمام فازها را با تاریخ و لینک PR ثبت کرده

---

## ضمیمه: فهرست تجمیعی فایل‌های تغییریافته

| دسته | تعداد تخمینی | نمونه |
|---|---|---|
| Migration جدید | ۷ | `020_dispatch_intents.py` ... `026_error_category_backfill.py` |
| ماژول جدید (orchestrator) | ۹ | `state_machine.py`, `scheduler_service.py`, `dispatcher_service.py`, `orphan_detector.py`, `worker_lifecycle.py`, `reconciliation_service.py`, `alert_manager.py`, `utcms_health_probe.py`, `utcms_reconciliation_scraper.py` |
| فایل‌های موجود تغییریافته | ۲۰+ | `waybill_worker.py`, `rpa_submit_service.py`, `rpa_auth_service.py`, `session_vault.py`, `fuel_inquiry_service.py`, `proxy_rotator.py`, `circuit_breaker.py`, `alerts.py`, `system.py`, `config.py`, `error_taxonomy.py`, `main.py`, `celery_app.py`, `worker_heartbeat.py` (حذف) |
| Frontend جدید | ۲ | `apps/web/src/app/admin/alerts/page.tsx`, `apps/web/src/app/admin/workers/page.tsx` |
| Compose | ۲+ | `compose/backend.yml` (اصلاح)، `compose/worker-node.yml` (جدید، Template) |
| Test جدید | ۱۳+ | جدول کامل در فاز ۱۱ |
| Documentation جدید | ۷ | جدول کامل در فاز ۱۲ |

### متغیرهای پیکربندی جدید

| متغیر | پیش‌فرض | توضیح | فاز |
|---|---|---|---|
| `QUEUE_ENABLED` | `True` | فعال‌سازی صف واقعی (نه inline) | ۰ |
| `ALERT_WEBHOOK_SECRET` | `""` | کلید HMAC برای امضای webhook | ۰، ۶ |
| `RPA_SESSION_TTL_SECONDS` | `7200` | TTL نشست در Redis | ۴ |
| `WORKER_STALL_TIMEOUT_SECONDS` | `90` | آستانهٔ تشخیص Worker مرده | ۲ |
| `WIREGUARD_ENDPOINT` | `""` | آدرس عمومی سرور مرکزی برای WireGuard | ۷ |
| `redbeat_lock_timeout` | `30` | تنظیمات `celery-redbeat` | ۹ |

---

**پایان سند.** این سند نسخهٔ ۲.۰ است و باید به‌عنوان منبع واحد حقیقت (Single Source of Truth) برای اجرای پروژهٔ بازطراحی معماری BarPro استفاده شود — نه در کنار دو سند مبدأ، بلکه **جایگزین** آن‌ها.

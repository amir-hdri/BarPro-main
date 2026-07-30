بله. این بار بررسی را روی خود repository فعلی amir-hdri/BarPro-main انجام دادم و تمرکز را فقط روی چهار بخش موردنظر شما گذاشتم:

1. زمان‌بندی (Scheduling)
2. صف و Dispatch
3. تخصیص عملیات به Worker
4. پیگیری، Recovery و وضعیت واقعی عملیات

نتیجه مهم این است که معماری فعلی BarPro از نظر مفهومی پایه‌های خوبی دارد، اما برای هدف نهایی شما یعنی:

Central 10GB + N Workerهای 4–6GB که هرکدام هم Waybill و هم Fuel را اجرا کنند و بتوانیم Worker جدید را بدون تغییر معماری اضافه کنیم

هنوز چند Gap مهم دارد که اگر الان اصلاح نشوند، با افزایش تعداد Workerها احتمالاً با Duplicate Execution، Race Condition، Job Orphan، Recovery اشتباه، Starvation و تخصیص نادرست Worker مواجه می‌شویم.

من نقشه راه را به شکل زیر نهایی می‌کنم.

⸻

1. وضعیت فعلی پروژه را چگونه ارزیابی می‌کنم؟

در حال حاضر پروژه اجزای مهمی دارد:

* Celery
* Redis
* PostgreSQL
* Scheduler
* Priority
* Idempotency
* Heartbeat
* Recovery
* Runtime State برای Driver
* Daily Counter
* Event Tracking
* Retry
* Dead Letter
* Multi-tenant

مثلاً در WaybillQueueManager ابتدا Job در DB ایجاد می‌شود و سپس Celery Task Dispatch می‌شود؛ همچنین Idempotency و celery_task_id ثبت می‌شود.

در Worker نیز acks_late=True و task_track_started=True فعال است و Retry و Time Limit وجود دارد.

Scheduler نیز از SELECT ... FOR UPDATE SKIP LOCKED استفاده می‌کند که برای جلوگیری از Race Condition بین Schedulerهای همزمان تصمیم خوبی است.

بنابراین پروژه از صفر نیست؛ بلکه نیاز به یک Refactoring معماری دارد تا اجزای فعلی واقعاً با هم یک سیستم Distributed Scheduler/Dispatcher/Execution بسازند.

⸻

2. مشکل اصلی فعلی: سه مفهوم با هم مخلوط شده‌اند

در معماری نهایی باید این سه مفهوم کاملاً جدا باشند:

Scheduler
    │
    │ تصمیم می‌گیرد:
    │ "چه عملیاتی الان باید انجام شود؟"
    ▼
Dispatcher
    │
    │ تصمیم می‌گیرد:
    │ "این عملیات به کدام Queue برود؟"
    ▼
Worker Pool
    │
    │ انتخاب می‌کند:
    │ "کدام Worker ظرفیت آزاد دارد؟"
    ▼
Worker

یعنی:

Scheduler ≠ Dispatcher ≠ Worker

پیشنهاد من این است که این تفکیک را به‌صورت رسمی در معماری BarPro اعمال کنیم.

⸻

3. معماری Scheduling نهایی

من Scheduler را به چهار مرحله تقسیم می‌کنم:

                         Scheduler
                             │
                             ▼
                   1. Find Eligible Jobs
                             │
                             ▼
                   2. Apply Business Rules
                             │
                             ▼
                   3. Create Dispatch Intent
                             │
                             ▼
                   4. Publish Task

Scheduler نباید خودش Worker را انتخاب کند.

این بسیار مهم است.

Scheduler فقط می‌گوید:

Job 123
Operation = WAYBILL
Priority = 8
Tenant = 12
Driver = 500
Ready = TRUE

بعد:

Dispatcher
    │
    ▼
Queue = waybill.submit

و سپس Worker Pool کار را می‌گیرد.

⸻

4. Scheduler فعلی: نقاط قوت

در Scheduler فعلی موارد خوبی وجود دارد.

مثلاً:

PENDING
QUEUED
WAITING_RETRY
WAITING_AUTH
OTP_BACKOFF

در انتخاب Job لحاظ شده‌اند.

همچنین:

* Priority
* Tenant Slice
* Batch Size
* Driver Daily Success Cap
* Driver Daily Attempt Cap
* Tenant Cooldown
* Runtime State
* Session Readiness
* Retry Time
* Submit After

در فرآیند Scheduling بررسی می‌شوند.

این پایه بسیار خوبی است.

⸻

5. اما یک Gap مهم در Scheduler وجود دارد

در حال حاضر Scheduler تصمیم می‌گیرد:

AUTH_REQUIRED
    ↓
RPA_AUTH_QUEUE
SESSION_READY
    ↓
RPA_SUBMIT_QUEUE

این منطق در Scheduler فعلی دیده می‌شود.

مشکل این است که:

Scheduler نباید مسئولیت اجرای مستقیم عملیات و وضعیت Queue را بیش از حد بر عهده بگیرد.

معماری بهتر:

Scheduler
   │
   ├── WAYBILL_SUBMIT
   ├── AUTH
   ├── FUEL_INQUIRY
   ├── OTP_WAIT
   ├── RECOVERY
   └── RECONCILIATION

هرکدام یک Task Type مشخص داشته باشند.

⸻

6. مدل نهایی Job

من پیشنهاد می‌کنم هر Job دارای این مدل منطقی باشد:

Job
│
├── job_id
├── tenant_id
├── operation_type
├── business_key
├── priority
├── status
├── desired_at
├── available_at
├── deadline_at
│
├── attempt_count
├── max_attempts
│
├── assigned_worker_id
├── execution_id
├── celery_task_id
│
├── lease_owner
├── lease_expires_at
│
├── current_step
├── progress_percent
│
├── last_heartbeat_at
├── last_error
├── error_category
│
├── external_reference
├── external_status
│
└── created_at / updated_at

در وضعیت فعلی بخشی از این مفاهیم وجود دارد، اما باید Execution Lease و Execution ID به‌صورت رسمی وارد مدل شوند.

⸻

7. تفاوت Job ID و Execution ID

این موضوع بسیار مهم است.

فرض کنید:

Job ID = JOB-123

این Job سه بار Retry شده:

Attempt 1 → Worker 1
Attempt 2 → Worker 3
Attempt 3 → Worker 5

باید داشته باشیم:

JOB-123
│
├── Execution 1
│     Worker 1
│
├── Execution 2
│     Worker 3
│
└── Execution 3
      Worker 5

پس:

job_id

همیشه ثابت است.

اما:

execution_id

در هر اجرای واقعی جدید تغییر می‌کند.

این برای Tracking و Debugging ضروری است.

⸻

8. Queue Architecture نهایی

من پیشنهاد می‌کنم Queueها بر اساس نوع عملیات باشند، نه Worker.

Queueها:

barpro.waybill.submit
barpro.waybill.auth
barpro.fuel.inquiry
barpro.recovery
barpro.reconciliation
barpro.dlq

در صورت نیاز:

barpro.priority.high
barpro.priority.normal
barpro.priority.low

اما ترجیح من این است که Priority داخل Queue حفظ شود و تعداد Queueها بیش از حد زیاد نشود.

⸻

9. اشتباه مهمی که باید حذف شود

نباید داشته باشیم:

worker1_queue
worker2_queue
worker3_queue

بلکه:

waybill.submit
fuel.inquiry
recovery

و:

W1 ─┐
W2 ─┼──► waybill.submit
W3 ─┤
W4 ─┘

همه Workerها Consumer هستند.

پس اضافه شدن:

W5

نیاز به هیچ تغییر در Scheduler ندارد.

⸻

10. مشکل مهم فعلی در Dispatch

در dispatch_waybill_task Queue با get_routed_queue() انتخاب می‌شود و Task با apply_async ارسال می‌شود.

این یک نقطه مهم معماری است.

من پیشنهاد می‌کنم get_routed_queue() در آینده Worker Routing انجام ندهد.

بلکه فقط:

Operation Routing

انجام دهد.

یعنی:

get_routed_queue()

نباید بگوید:

Worker 1
Worker 2
Worker 3

بلکه باید بگوید:

waybill.submit
fuel.inquiry

انتخاب Worker باید کاملاً بر عهده Broker + Worker Pool باشد.

⸻

11. Worker Allocation نهایی

من پیشنهاد می‌کنم Workerها Capability-Based باشند.

هر Worker هنگام Startup اعلام کند:

worker_id = UUID
capabilities:
    WAYBILL
    FUEL
concurrency:
    2
browser_slots:
    2
captcha_slots:
    2
proxy_slots:
    1
version:
    1.5.0

مثلاً:

W1
├── WAYBILL ✓
├── FUEL ✓
└── Capacity = 2
W2
├── WAYBILL ✓
├── FUEL ✓
└── Capacity = 2
W3
├── WAYBILL ✓
├── FUEL ✓
└── Capacity = 2

و بعد:

W4
├── WAYBILL ✓
├── FUEL ✓
└── Capacity = 2

به‌صورت خودکار وارد Pool می‌شود.

⸻

12. نکته بسیار مهم: Celery Worker ≠ Capacity واقعی

این یکی از Gapهای مهمی است که باید در BarPro حل شود.

فرض کنیم:

Worker 1
Concurrency = 2

اما:

Browser Slots = 1

پس Worker واقعاً فقط یک Job RPA را می‌تواند اجرا کند.

بنابراین Capacity باید بر اساس Resource واقعی باشد:

Effective Capacity =
min(
    celery_slots,
    browser_slots,
    captcha_slots,
    proxy_slots,
    external_rate_limit
)

پس Worker نباید فقط بگوید:

I am alive

بلکه باید:

I have 2 free execution slots

را اعلام کند.

⸻

13. پیشنهاد من: Worker Lease

برای هر Execution:

JOB-123
    │
    ▼
Execution-ABC
    │
    ▼
Worker-7
    │
    ▼
Lease

مثلاً:

lease_owner = worker-7
lease_expires_at = T+60s

Worker هر چند ثانیه تمدید کند.

اگر:

Heartbeat Lost

و:

lease_expires_at < NOW

آن‌وقت Job قابل Recovery است.

این از Heartbeat فعلی قوی‌تر است.

⸻

14. مشکل بزرگ Heartbeat فعلی

در حال حاضر WorkerHeartbeatRegistry در حافظه Process نگهداری می‌شود:

self._leases: dict[str, WorkerLease]

یعنی Heartbeat فعلی Local Memory است.

این در معماری چند Worker و چند Server یک Gap جدی است.

مثلاً:

Central
   │
   X
   │
Worker 2

Central نمی‌تواند به Registry حافظه Worker 2 دسترسی مستقیم داشته باشد.

پس Heartbeat باید به:

Redis

یا یک Store مشترک منتقل شود.

پیشنهاد:

barpro:worker:{worker_id}:heartbeat
barpro:execution:{execution_id}:lease

⸻

15. Recovery فعلی نیز باید اصلاح شود

Recovery فعلی از worker_heartbeat_registry.detect_stalled() استفاده می‌کند.

پس چون Heartbeat Local است، Recovery در معماری Multi-Server کامل قابل اتکا نیست.

همچنین Recovery فعلی تلاش می‌کند Celery Task را revoke کند و سپس Job را Retry یا Dead Letter کند.

این باید تغییر کند.

معماری صحیح:

Worker Lost
    │
    ▼
Lease Expired
    │
    ▼
Recovery Candidate
    │
    ▼
External Outcome Unknown?
    │
    ├── YES → Reconciliation
    │
    └── NO
          │
          ▼
      Retry

نباید صرفاً با Worker Crash فوراً دوباره Submit کنیم.

چون ممکن است:

UTCMS = SUCCESS
BarPro = PROCESSING
Worker = CRASH

و Retry باعث Duplicate شود.

⸻

16. من وضعیت Job را به این State Machine تبدیل می‌کنم

                         ┌───────────────┐
                         │    CREATED    │
                         └───────┬───────┘
                                 ▼
                            ELIGIBILITY
                                 │
                 ┌───────────────┼───────────────┐
                 │               │               │
                 ▼               ▼               ▼
              WAIT_AUTH       WAIT_TIME      READY
                 │               │               │
                 └───────────────┴───────────────┘
                                 │
                                 ▼
                             DISPATCHED
                                 │
                                 ▼
                              CLAIMED
                                 │
                                 ▼
                              RUNNING
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
                    ▼            ▼            ▼
                 SUCCESS      RETRYABLE     UNKNOWN
                    │            │            │
                    ▼            ▼            ▼
                 COMPLETE    BACKOFF      RECONCILE
                                 │            │
                                 ▼            │
                              READY ◄─────────┘
                                 │
                                 ▼
                           MAX ATTEMPTS
                                 │
                                 ▼
                              DLQ

این State Machine باید تنها منبع حقیقت وضعیت Job باشد.

⸻

17. Tracking باید Event-Based شود

در حال حاضر Eventها در Scheduler ثبت می‌شوند؛ مثلاً JOB_CREATED و JOB_QUEUED_SUBMIT.

این مسیر درست است، اما باید کامل‌تر شود.

من پیشنهاد می‌کنم هر Job یک Event Timeline داشته باشد:

JOB_CREATED
JOB_ELIGIBILITY_CHECKED
JOB_SCHEDULED
JOB_DISPATCHED
JOB_CLAIMED
JOB_STARTED
AUTH_STARTED
AUTH_SUCCESS
BROWSER_STARTED
CAPTCHA_STARTED
CAPTCHA_SUCCESS
FORM_SUBMITTED
EXTERNAL_ACCEPTED
TRACKING_RECEIVED
JOB_SUCCEEDED

در خطا:

JOB_FAILED
RETRY_SCHEDULED
RETRY_STARTED
WORKER_LOST
LEASE_EXPIRED
RECONCILIATION_STARTED
RECONCILIATION_SUCCESS

این به شما امکان می‌دهد هر عملیات را از لحظه ورود تا پایان به‌صورت کامل Trace کنید.

⸻

18. یک Tracking ID واحد لازم داریم

برای هر عملیات:

job_id

ولی برای Trace کل سیستم:

correlation_id

و برای هر اجرای واقعی:

execution_id

پس:

Correlation
    │
    ├── Job
    │
    ├── Execution 1
    │
    ├── Execution 2
    │
    └── Reconciliation

این سه ID باید در:

* PostgreSQL
* Redis
* Celery
* Logs
* Events
* WebSocket
* Metrics

ثبت شوند.

⸻

19. وضعیت فعلی Tracking خوب است ولی باید تکمیل شود

در Worker فعلی worker_id از self.request.hostname گرفته می‌شود.

این برای Production کافی نیست.

بهتر است:

worker_id = UUID
worker_hostname
worker_instance_id
worker_version

جدا باشند.

چون:

hostname

ممکن است در Containerها تکراری یا ephemeral باشد.

⸻

20. Scheduling باید Fairness داشته باشد

در Scheduler فعلی tenant_slice وجود دارد.

این خوب است، اما من پیشنهاد می‌کنم الگوریتم کامل‌تر شود:

Priority
    +
Tenant Fairness
    +
Age
    +
Deadline
    +
Driver Constraints
    +
Worker Capacity

مثلاً:

Score =
Priority Weight
+
Waiting Time
+
Deadline Urgency

ولی Tenant نباید بتواند با هزار Job، کل Queue را پر کند.

پس:

Per Tenant Concurrency Limit

نیاز داریم.

مثلاً:

Tenant A
Max Running = 3
Tenant B
Max Running = 10

این Limit باید Dynamic باشد.

⸻

21. Backpressure باید اضافه شود

اگر:

1000 Jobs

و:

3 Workers

نباید همه 1000 Job را یکباره Dispatch کنیم.

بهتر:

DB
 │
 ▼
Scheduler
 │
 ▼
Dispatch Window
 │
 ▼
Queue
 │
 ▼
Workers

مثلاً:

Workers = 3
Effective Capacity = 6
Dispatch:
6 Running
+ 12 Prefetched

نه:

1000 Celery Messages

این باعث می‌شود:

* Queue کنترل شود
* Retryها کنترل شوند
* Priority درست‌تر کار کند
* Jobهای جدید گرسنه نشوند

⸻

22. Celery Prefetch باید با RPA هماهنگ شود

در حال حاضر:

worker_prefetch_multiplier

فعال است.

برای عملیات Browser/RPA بهتر است:

worker_prefetch_multiplier = 1

یا مقدار بسیار محدود.

چون اگر:

Worker 1
Concurrency = 2
Prefetch = 10

ممکن است Worker ده Job را رزرو کند ولی فقط دو تا را اجرا کند.

این باعث می‌شود Workerهای دیگر بیکار بمانند.

برای Scale-Out واقعی:

Prefetch ≈ 1

برای Jobهای سنگین RPA انتخاب مناسب‌تری است.

⸻

23. مشکل Retry فعلی

در Waybill:

Retryable
    ↓
self.retry()

و mark_retrying انجام می‌شود.

این خوب است.

اما باید Retry را از:

Celery Retry

و:

Business Retry

جدا کنیم.

مثلاً:

Network Retry
    30s
    60s
    120s
CAPTCHA Retry
    Policy-based
Auth Retry
    Login Queue
OTP Retry
    Wait Until
External Unknown
    Reconciliation

همه اینها نباید فقط یک self.retry() باشند.

⸻

24. Scheduling نهایی پیشنهادی

من پیشنهاد می‌کنم یک Scheduler مرکزی منطقی داشته باشیم:

                Scheduler Service
                       │
             ┌─────────┴─────────┐
             │                   │
             ▼                   ▼
       Eligibility          Capacity
             │                   │
             └─────────┬─────────┘
                       ▼
                 Dispatch Plan
                       │
           ┌───────────┼───────────┐
           ▼           ▼           ▼
        Waybill       Fuel       Recovery
           │           │           │
           └───────────┼───────────┘
                       ▼
                    Redis
                       │
               Worker Pool N

⸻

25. Worker Allocation نهایی

به‌نظر من Worker را نباید Job به Job توسط Central انتخاب کنیم.

بهتر:

Central
    │
    ▼
Queue
    │
    ▼
Available Worker

اما Worker باید با Capability و Capacity خود Queue را Consume کند.

مثلاً:

W1
waybill ✓
fuel ✓
W2
waybill ✓
fuel ✓
W3
waybill ✓
fuel ✓
W4
waybill ✓
fuel ✓

همه Active-Active.

⸻

26. تخصیص Proxy

در معماری فعلی Proxy در زمان Worker Process Init از Environment یا File بارگذاری می‌شود.

برای سه Worker خوب است، ولی برای N Worker مناسب نیست.

در معماری نهایی:

Proxy Pool
    │
    ▼
Proxy Manager
    │
    ├── Health
    ├── Capacity
    ├── Cooldown
    ├── Failure Rate
    └── Assignment

Worker هنگام اجرای Job:

Acquire Proxy Lease
    ↓
Execute
    ↓
Release

و Proxy نیز:

proxy_lease_id

داشته باشد.

این اجازه می‌دهد Worker 4، 5، 6 بدون تغییر معماری اضافه شوند.

⸻

27. Reconciliation باید جزء Scheduler باشد

یکی از مهم‌ترین بخش‌های نقشه راه من:

Reconciliation Scheduler

مثلاً:

UNKNOWN
SUBMISSION_UNKNOWN
WORKER_LOST
TIMEOUT_AFTER_SUBMIT

این Jobها نباید مستقیماً Retry شوند.

باید:

External Status Check
      │
      ├── SUCCESS → Mark Success
      │
      ├── FAILED → Retry
      │
      └── UNKNOWN → Needs Review

این برای ثبت بارنامه حیاتی است.

⸻

28. یک Gap مهم در Recovery فعلی

در cleanup_stuck_jobs اگر Job در وضعیت IN_PROGRESS باشد، در صورت Timeout به NEEDS_REVIEW می‌رود، چون نتیجه ثبت خارجی ممکن است نامشخص باشد. این تصمیم از نظر ایمنی درست است.

اما باید این وضعیت به‌صورت خودکار وارد:

Reconciliation Queue

شود.

نه اینکه فقط:

NEEDS_REVIEW

بماند.

پس:

IN_PROGRESS timeout
       │
       ▼
UNKNOWN
       │
       ▼
RECONCILIATION
       │
       ├── SUCCESS
       ├── RETRY
       └── MANUAL_REVIEW

⸻

29. مشکل دیگری که باید اصلاح شود: دو مسیر اجرای عملیات

در WaybillQueueManager اگر Queue فعال نباشد، امکان اجرای Inline وجود دارد.

و در Fuel نیز اگر Celery در دسترس نباشد، Thread محلی اجرا می‌شود.

برای Production Distributed Architecture من این را توصیه نمی‌کنم.

چون:

Central API
    └── Inline Execution

باعث می‌شود Central تبدیل به Worker شود.

و:

Worker Pool

دیگر تنها محل اجرای عملیات نباشد.

پیشنهاد:

Production:
QUEUE REQUIRED
Development:
Inline Fallback ENABLED

یعنی Inline فقط Development/Test.

⸻

30. معماری کامل نهایی

                         USER / API
                              │
                              ▼
                     ┌─────────────────┐
                     │   CENTRAL API   │
                     │     10 GB       │
                     └────────┬────────┘
                              │
                              ▼
                        PostgreSQL
                              │
                              ▼
                     SCHEDULER SERVICE
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
          Eligibility      Fairness        Capacity
              │               │               │
              └───────────────┼───────────────┘
                              │
                              ▼
                       DISPATCH PLAN
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
          ▼                   ▼                   ▼
    Waybill Queue        Fuel Queue         Recovery Queue
          │                   │                   │
          └───────────────────┼───────────────────┘
                              │
                             Redis
                              │
                    ┌─────────┴─────────┐
                    │   Worker Pool N   │
                    │                   │
                    │ Dynamic Discovery │
                    │ Heartbeat         │
                    │ Lease             │
                    │ Capability        │
                    │ Capacity          │
                    └─────────┬─────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
         ▼                    ▼                    ▼
       W1 6GB               W2 6GB               W3 6GB
       W4 6GB               W5 6GB               WN 6GB
         │                    │                    │
         ├── Waybill          ├── Waybill          ├── Waybill
         ├── Fuel             ├── Fuel             ├── Fuel
         ├── Browser          ├── Browser          ├── Browser
         └── CAPTCHA          └── CAPTCHA          └── CAPTCHA
                              │
                              ▼
                       PROXY MANAGER
                              │
                              ▼
                         PROXY POOL
                              │
                              ▼
                            UTCMS
                              │
                              ▼
                     RECONCILIATION
                              │
                              ▼
                        PostgreSQL
                              │
                              ▼
                       EVENT STREAM
                              │
                              ▼
                      Dashboard / WebSocket

⸻

31. نقشه راه نهایی BarPro

من Roadmap را به ۱۰ Phase تقسیم می‌کنم.

Phase 0 — تثبیت مدل داده

اولین کار

* مشخص کردن Job Model
* Execution Model
* Attempt Model
* Event Model
* Worker Model
* Worker Lease
* Proxy Lease

خروجی:

Job
Execution
Attempt
Event
Worker
Lease
ProxyLease

⸻

Phase 1 — State Machine

تمام وضعیت‌ها استاندارد شوند:

CREATED
PENDING
ELIGIBLE
WAITING_AUTH
WAITING_RETRY
OTP_BACKOFF
DISPATCHED
CLAIMED
RUNNING
SUCCEEDED
FAILED
UNKNOWN
RECONCILING
NEEDS_REVIEW
DEAD_LETTER
CANCELLED

و Transitionها فقط از طریق State Machine انجام شوند.

⸻

Phase 2 — Scheduler

Scheduler:

Find
→ Validate
→ Fairness
→ Priority
→ Capacity
→ Dispatch

با:

* Tenant Fairness
* Per-Tenant Concurrency
* Driver Limits
* Cooldown
* Deadline
* Backpressure

⸻

Phase 3 — Queue

Queueهای استاندارد:

waybill.submit
waybill.auth
fuel.inquiry
recovery
reconciliation
dlq

Worker-specific Queue حذف شود.

⸻

Phase 4 — Worker Pool

پیاده‌سازی:

Worker Registration
Worker UUID
Capabilities
Capacity
Heartbeat
Lease
Graceful Shutdown
Version

Worker جدید:

Deploy
→ Register
→ Health Check
→ Ready
→ Consume

⸻

Phase 5 — Execution Lease

هر Job:

Job
→ Execution
→ Lease

و:

Heartbeat
+
Lease Expiry

مبنای Recovery شود.

⸻

Phase 6 — Proxy Manager

پیاده‌سازی:

Proxy Registry
Proxy Health
Proxy Capacity
Proxy Cooldown
Proxy Lease
Proxy Failover

⸻

Phase 7 — Recovery & Reconciliation

سه مسیر:

Retryable
    ↓
Retry
Worker Lost
    ↓
Reconcile
External Unknown
    ↓
Reconcile

⸻

Phase 8 — Tracking

Dashboard باید نشان دهد:

Total Jobs
Queued
Dispatched
Claimed
Running
Succeeded
Failed
Retrying
Unknown
Reconciliation
DLQ

برای هر Job:

Timeline
Worker
Execution
Attempt
Proxy
Current Step
Last Heartbeat
External Reference

⸻

Phase 9 — Scaling

ابتدا:

Central 10GB
W1 6GB
W2 6GB
W3 6GB

سپس:

W4
W5
W6
...
WN

بدون تغییر:

Scheduler
API
Database Schema
Business Logic

⸻

Phase 10 — Production Hardening

در پایان:

* Load Test
* Soak Test
* Worker Crash Test
* Redis Restart Test
* PostgreSQL Restart Test
* Network Failure
* Proxy Failure
* UTCMS Timeout
* Duplicate Submission Test
* Worker Rolling Upgrade
* Worker Scale-Out Test
* Worker Scale-In Test
* Graceful Shutdown Test

⸻

32. ترتیب اولویت اصلاحات

اگر بخواهم دقیقاً برای پروژه فعلی اولویت بدهم:

P0 — بحرانی

1. Distributed Worker Heartbeat
2. Execution Lease
3. Job State Machine
4. Idempotent Dispatch
5. Duplicate Execution Prevention
6. Recovery/Reconciliation
7. Shared Operation Queues
8. Remove Production Inline Execution

P1 — بسیار مهم

9. Dynamic Worker Registration
10. Worker Capability/Capacity
11. Backpressure
12. Fair Scheduling
13. Per-Tenant Concurrency
14. Proxy Manager
15. Proxy Lease
16. Execution/Attempt Model

P2 — مهم

17. Event Timeline
18. Dashboard Tracking
19. DLQ Management
20. Graceful Worker Shutdown
21. Version Compatibility
22. Rolling Deployment

P3 — Scale آینده

23. Redis HA
24. PostgreSQL HA
25. Multiple API Nodes
26. Separate Scheduler Nodes
27. Dedicated Reconciliation Workers

⸻

نتیجه نهایی من درباره BarPro

بعد از بررسی مجدد کد، من معماری نهایی را این‌طور تعریف می‌کنم:

BarPro باید یک Distributed Job Orchestration Platform باشد، نه صرفاً یک FastAPI + Celery Application.

و مسیر هر عملیات باید دقیقاً این باشد:

User Request
    ↓
Create Job
    ↓
Idempotency Check
    ↓
Persist Job
    ↓
Scheduler
    ↓
Eligibility
    ↓
Fairness
    ↓
Priority
    ↓
Capacity
    ↓
Dispatch
    ↓
Queue
    ↓
Worker Claim
    ↓
Execution Lease
    ↓
Browser / CAPTCHA / UTCMS
    ↓
Heartbeat
    ↓
External Result
    ↓
Success
    │
    ├── Retry
    │
    ├── Recovery
    │
    └── Reconciliation
    ↓
Final State
    ↓
Event Timeline
    ↓
Dashboard

مهم‌ترین اصلاحی که از بررسی کد فعلی به دست آمد این است که Heartbeat فعلی Local-Memory است و بنابراین برای معماری چندسروره کافی نیست؛ همچنین Recovery فعلی مستقیماً به همان Registry محلی وابسته است. این دو باید قبل از Scale کردن از ۳ Worker به N Worker اصلاح شوند.

از طرف دیگر، Scheduler فعلی با SKIP LOCKED، Priority، Tenant Slice، Driver Limits و Runtime State پایه مناسبی دارد، بنابراین لازم نیست آن را از صفر بازنویسی کنیم؛ باید آن را به یک Scheduler مستقل از Worker تبدیل کنیم و Dispatch/Worker Allocation را از آن جدا کنیم.

معماری هدف نهایی:

1 Central
    +
N Stateless Active-Active Workers
    +
Shared Operation Queues
    +
Distributed Job Lease
    +
Distributed Heartbeat
    +
Idempotent Execution
    +
Dynamic Worker Discovery
    +
Capability/Capacity Based Workers
    +
Proxy Pool
    +
Reconciliation
    +
Event-Based Tracking

با این مدل، اضافه کردن Worker 4 یا Worker 20 نباید نیازمند تغییر در Scheduler، API یا Business Logic باشد؛ Worker جدید فقط باید ثبت شود، Health Check را پاس کند و وارد Queue Consumer Pool شود.

قدم بعدی منطقی برای خود Repository این است که همین معماری را به یک برنامه اصلاح کد تبدیل کنیم: ابتدا worker_heartbeat_registry و Recovery را به Distributed Lease تبدیل کنیم، سپس Job/Execution/Attempt را اضافه کنیم، بعد Scheduler و Dispatch را از هم جدا کنیم، سپس Queueهای Waybill/Fuel/Recovery/Reconciliation را استاندارد کنیم و در نهایت Dynamic Worker Registration و Proxy Manager را پیاده کنیم. این ترتیب کمترین ریسک را برای منطق فعلی BarPro دارد و اجازه می‌دهد هر مرحله جداگانه تست شود.
# Worker 4 — خروجی خانگی/موبایل‌کلاس (Home Egress)

> هدف: افزودن یک egress خانگی/موبایل‌کلاس به fleet. توجه: HTTP 408 روی درخواست
> مستقیم `/Barname/Document/*` بدون session، معیار معتبر تشخیص دیتاسنتری یا خانگی
> بودن IP نیست؛ آمادگی صدور فقط با flow احرازشده سنجیده می‌شود.

## معماری

```
Home Box (mini-PC / لپ‌تاپ، اینترنت FTTH یا TD-LTE)
├── WireGuard client ──► 10.8.0.1 (Central)     ← فقط کنترل‌پلین: Postgres/Redis/Broker
├── Squid (پورت 3128 داخلی) ──► خروجی از IP خانگی ← ترافیک RPA/UTCMS
└── Celery worker (WORKER_IP_INDEX=4, صف‌های *_4)
```

اصل طلایی: **تونل فقط برای کنترل‌پلین است** (`AllowedIPs = 10.8.0.0/24`)؛ هیچ
DefaultRoute‌ای از تونل نمی‌رود، پس UTCMS آی‌پی خانگیِ ISP را می‌بیند.

## انتخاب سخت‌افزار/اینترنت

| گزینه | کیفیت اقبال نزد UTCMS | توصیه |
|---|---|---|
| FTTH/ADSL ثابت (مخابرات/های‌وب/...) | بهترین — رنج خانگی واقعی | ⭐ اولویت اول |
| TD-LTE ثابت‌نما | خوب | گزینه دوم |
| 4G/5G موبایل (CGNAT مشترک) | متغیر؛ رنج اشتراکی و پرترافیک | فال‌بک |

هر mini-PC کم‌مصرف (Intel N100 / Raspberry Pi 5 با Debian 12) کافی است؛ بار
کار فقط یک مرورگر Playwright با concurrency=1 است.

## نصب (سه دستور)

```bash
# 1) روی مرکزی:
bash scripts/setup_wireguard_central.sh        # کلیدها + UFW + wg0 + worker4.conf

# 2) انتقال امن شناسه به جعبه‌ی خانگی:
scp root@<central>:/root/barpro-worker4/worker4.conf homebox:/root/worker4.conf
scp root@<central>:/opt/barpro/.env            homebox:/tmp/central.env   # فقط بار اول

# 3) روی جعبه‌ی خانگی:
REPO_URL=https://github.com/amir-hdri/BarPro-main.git \
  bash setup_worker_home.sh /root/worker4.conf
```

اسکریپت خانگی: `.env` مرکزی را کپی‌شده فرض می‌کند، host های DB/Redis را به
`10.8.0.1` (تونل) تبدیل و `WORKER_IP_INDEX=4` ست می‌کند، سپس
`compose/worker-node.yml` را بالا می‌آورد. خروجی UTCMS از خط خانگی می‌ماند.

> چرخش IP خانگی (PPPoE/LTE): بی‌اهمیت است — تونل WG با Endpoint جدید خودش
> برمی‌گردد و UFW مرکزی به IP عمومی خانه نیازی ندارد.

## فعال‌سازی در ناوگان (روی مرکزی، بعد از اولین heartbeat)

```env
AVAILABLE_IP_INDICES="1,2,3,4"
```
سپس redeploy بک‌اند تا routing/circuit-breaker شاخص 4 را بپذیرد (فیلتر
Worker-Registry خودکار است).

## راستی‌آزمایی موفقیت

1. `wg show wg0` روی مرکزی → latest handshake برای peer کارگر ۴
2. `SELECT * FROM worker_registry WHERE worker_id='4';` → active
3. تست tunnel روی جعبه‌ی خانگی:
   `curl -m 15 -x http://127.0.0.1:3128 -o /dev/null -w '%{http_code}' "https://barname.utcms.ir/Barname/Account/Login"`
   → پاسخ واقعی HTTP بدون `X-Squid-Error` سلامت tunnel را ثابت می‌کند.
4. تست تعیین‌کننده: یک dry-run کنترل‌شده باید Login → Notification → منوی ثبت
   بارنامه را طی کند و DOM فرم + read-back مبدا/مقصد را ثبت کند. فقط این flow
   آمادگی صدور را ثابت می‌کند؛ curl مستقیم به HagigiHogugi معتبر نیست.

## امنیت

- کلید خصوصی کارگر فقط روی جعبه‌ی خانگی؛ `worker4.conf` پس از کپی حذف شود.
- DB/Redis همچنان از اینترنت عمومیِ مرکزی بسته است؛ مسیر تونل UFW-limit شده.
- DOCKER-USER: قانون accept فقط برای `-i wg0 -s 10.8.0.0/24`.

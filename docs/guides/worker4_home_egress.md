# Worker 4 — خروجی خانگی/موبایل‌کلاس (Home Egress)

> هدف: عبور از محدودیت انتخابی ماژول صدور UTCMS که از 2026-08-24 به رنج‌های
> دیتاسنتر/VPS روی `/Barname/Document/*` پاسخ HTTP 408 می‌دهد، در حالی که
> خانه/موبایل همان مسیر را عادی باز می‌کند. (اثبات زنده: ماتریس 2026-08-26 —
> خانه=200، History=302 زنده، فقط Document/* =408 از IP سرورها)

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
3. تست تعیین‌کننده روی جعبه‌ی خانگی:
   `curl -m 15 -x http://127.0.0.1:3128 -o /dev/null -w '%{http_code}' "https://barname.utcms.ir/Barname/Document/HagigiHogugi"`
   → اگر **200/302** شد (به‌جای 408)، ماژول صدور این IP را پذیرفته و ثبت
   بارنامه از صف `waybill_tasks_4` جاری می‌شود.

## امنیت

- کلید خصوصی کارگر فقط روی جعبه‌ی خانگی؛ `worker4.conf` پس از کپی حذف شود.
- DB/Redis همچنان از اینترنت عمومیِ مرکزی بسته است؛ مسیر تونل UFW-limit شده.
- DOCKER-USER: قانون accept فقط برای `-i wg0 -s 10.8.0.0/24`.

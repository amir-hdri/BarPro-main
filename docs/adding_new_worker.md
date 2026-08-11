# افزودن Worker Node جدید به BarPro

این راهنما فرآیند کامل افزودن یک Worker Node جدید (VPS جدید) به سیستم BarPro را توضیح می‌دهد.

> **معماری امنیت شبکه:** از UFW Firewall + IP ثابت استفاده می‌کنیم.  
> هر VPS یک IP ثابت اختصاصی دارد، پس محدود کردن پورت‌های حساس با `ufw` کافی است.  
> اگر بعداً تعداد Worker‌ها زیاد شد و مدیریت IP لیست دستی خسته‌کننده شد، می‌توان به **Headscale** (خودمیزبان روی سرور مرکزی) مهاجرت کرد.

---

## پیش‌نیازها

- سرور مرکزی: `<YOUR_CENTRAL_SERVER_IP>`
- VPS جدید Worker: IP اختصاصی ثابت (مثلاً `185.x.x.y`)
- Docker روی هر دو سرور نصب باشد
- دسترسی SSH به هر دو سرور

---

## گام ۱ — خرید و آماده‌سازی VPS Worker جدید

۱. از vpsmarket.org یک VPS ایران تهیه کنید
۲. IP ثابت اختصاصی آن را یادداشت کنید
۳. Docker را نصب کنید:
   ```bash
   curl -fsSL https://get.docker.com | bash
   ```

---

## گام ۲ — باز کردن فایروال سرور مرکزی

روی سرور مرکزی (`<YOUR_CENTRAL_SERVER_IP>`) اجرا کنید:

```bash
# WORKER_IP = IP ثابت VPS جدید
# WORKER_ID = شناسه عددی IP ایندکس (2 یا 3 — باید در AVAILABLE_IP_INDICES مرکزی باشد)
sudo bash scripts/add_worker_firewall.sh <WORKER_IP> <WORKER_ID>
```

این دستور:
- UFW rules اضافه می‌کند تا Worker IP بتواند به PostgreSQL (5432) و Redis (6379) وصل شود
- دستورالعمل‌های گام بعد را چاپ می‌کند

اگر اولین بار است که فایروال را تنظیم می‌کنید:
```bash
# ابتدا WORKER_IPS را تنظیم کنید
export WORKER_IPS="185.x.x.1 185.x.x.2 185.x.x.3"
sudo bash scripts/setup_firewall_central.sh
```

---

## گام ۳ — ایجاد role کم‌دسترسی در PostgreSQL (فقط یک‌بار)

روی سرور مرکزی:

```bash
# جایگزین <strong-password> با یک رمز تصادفی قوی کنید
docker exec -i barpro-postgres psql -U postgres -d utcms_rpa \
  -v WORKER_DB_PASSWORD="<strong-password>" \
  -f /opt/barpro/scripts/create_worker_db_role.sql
```

این role فقط `SELECT/INSERT/UPDATE` دارد — بدون `DELETE/CREATE/DROP`.

---

## گام ۴ — تنظیم محیط روی Worker جدید

روی VPS جدید (`<WORKER_IP>`):

```bash
git clone https://github.com/amir-hdri/BarPro-main.git /opt/barpro
cd /opt/barpro
```

فایل `.env` را بسازید:

```bash
cat > /opt/barpro/.env << 'EOF'
# شناسه عددی IP ایندکس — باید در AVAILABLE_IP_INDICES مرکزی باشد
# ورکر اول ریموت → WORKER_ID=2 ، ورکر دوم ریموت → WORKER_ID=3
# صف‌های Celery با همین عدد ساخته می‌شوند: waybill_tasks_2 ، rpa_auth_3 و ...
WORKER_ID=2
WORKER_IP_INDEX=2

# IP سرور مرکزی
CENTRAL_IP=<YOUR_CENTRAL_SERVER_IP>

# دیتابیس (با role کم‌دسترسی)
DATABASE_URL=postgresql+asyncpg://barpro_worker:<WORKER_DB_PASSWORD>@<YOUR_CENTRAL_SERVER_IP>:5432/utcms_rpa

# Redis (همان رمز سرور مرکزی) — ⚠️ CELERY_BROKER_URL باید DB 0 باشد
# چون مرکزی task ها را روی DB 0 منتشر می‌کند؛ DB 1/2 باعث می‌شود task ها هرگز به ورکر نرسند
REDIS_URL=redis://:<REDIS_PASSWORD>@<YOUR_CENTRAL_SERVER_IP>:6379/0
CELERY_BROKER_URL=redis://:<REDIS_PASSWORD>@<YOUR_CENTRAL_SERVER_IP>:6379/0
CELERY_RESULT_BACKEND=redis://:<REDIS_PASSWORD>@<YOUR_CENTRAL_SERVER_IP>:6379/0

# Squid Proxy محلی
WORKER_PROXY_PORT=3128

# IP عمومی این VPS — برای tcp_outgoing_address در Squid (egress اختصاصی به UTCMS)
WORKER_EGRESS_IP=<IP این VPS>

# مرورگر و کپچا
CAPTCHA_PROVIDER=auto
HEADLESS=true

# Feature flags
QUEUE_ENABLED=true
QUEUE_INLINE_FALLBACK=false
EOF
```

قبل از اولین اجرا، placeholder های کانفیگ Squid را جایگزین کرده و به `squid_worker.runtime.conf` رندر کنید (IP اگریس این VPS و IP سرور مرکزی برای health check). `compose/worker-node.yml` همین فایل `runtime` را mount می‌کند — رندر روی خودِ قالب، قالب git را خراب می‌کند. ابتدا مقدارهای واقعی را جای `.env` بگذارید و آن را در شل load کنید (گارد `:?` اگر متغیری نباشد، خطا می‌دهد به‌جای اینکه کانفیگ خراب بسازد):

```bash
cd /opt/barpro
set -a; source .env; set +a
sed -e "s/__WORKER_EGRESS_IP__/${WORKER_EGRESS_IP:?WORKER_EGRESS_IP is required in .env}/g" \
    -e "s/__CENTRAL_IP__/${CENTRAL_IP:?CENTRAL_IP is required in .env}/g" \
    infra/squid/squid_worker.conf > infra/squid/squid_worker.runtime.conf
```

> صف کنترلی `rpa_scheduler` را نودهای ریموت مصرف **نمی‌کنند** — فقط سرویس اختصاصی `celery_scheduler` روی سرور مرکزی (در `compose/backend.yml`). بنابراین `WORKER_IP_INDEX` این ورکر باید فقط در `AVAILABLE_IP_INDICES` مرکزی باشد و صف‌های سافیکس‌دار آن (`waybill_tasks_<n>` و ...) را مصرف می‌کند.

---

## گام ۵ — راه‌اندازی Worker

```bash
cd /opt/barpro
# --env-file .env: compose interpolation باید از /opt/barpro/.env بخواند، نه
# ./compose/.env — وگرنه WORKER_IP_INDEX/CENTRAL_IP در قالب worker-node.yml
# مقدار placeholder می‌گیرند و ورکر به صف‌های اشتباه وصل می‌شود (X5).
docker compose --env-file .env -f compose/worker-node.yml up -d
```

بررسی وضعیت:
```bash
docker compose --env-file .env -f compose/worker-node.yml ps
docker compose --env-file .env -f compose/worker-node.yml logs -f worker
```

---

## گام ۶ — تأیید ثبت Worker

روی سرور مرکزی، بررسی کنید که Worker جدید در `worker_registry` ثبت شده:

```bash
# داخل psql
docker exec -it barpro-postgres psql -U postgres -d utcms_rpa -c \
  "SELECT worker_id, hostname, status, last_heartbeat_at FROM worker_registry ORDER BY created_at;"
```

یا از طریق API (با توکن ادمین):
```bash
curl -s http://<YOUR_CENTRAL_SERVER_IP>/api/system/proxies/health \
  -H "Authorization: Bearer <ADMIN_TOKEN>" | python3 -m json.tool
```

Worker جدید باید در لیست `proxies` ظاهر شود با `status: healthy`.

---

## نکات مهم

### اگر Worker نمی‌تواند به دیتابیس وصل شود
```bash
# روی Worker
nc -zv <YOUR_CENTRAL_SERVER_IP> 5432
# اگر خطا داد: UFW rule اضافه نشده یا IP اشتباه است
```

### اگر Worker در worker_registry ثبت نشد
```bash
# بررسی لاگ Worker
docker logs barpro-celery-worker | grep -i "worker\|register\|error"
```

### حذف Worker از سیستم
```bash
# روی سرور مرکزی
sudo ufw delete allow from <WORKER_IP> to any port 5432
sudo ufw delete allow from <WORKER_IP> to any port 6379

# روی Worker
docker compose -f compose/worker-node.yml down
```

---

## مهاجرت آینده به Headscale (اختیاری)

اگر تعداد Worker‌ها از ۵ بیشتر شد و مدیریت IP لیست دستی خسته‌کننده شد:

1. **Headscale** را روی سرور مرکزی نصب کنید (یک Container اضافه)
2. هر Worker یک کلید WireGuard می‌گیرد و از طریق Headscale متصل می‌شود
3. UFW rules به جای IP عمومی، فقط شبکه `100.64.0.0/10` (Tailscale subnet) را قبول می‌کنند

این مهاجرت در یک روز قابل انجام است و نیازی به تغییر کد ندارد.

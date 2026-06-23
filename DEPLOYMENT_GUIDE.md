# راهنمای استقرار سیستم BarPro در محیط عملیاتی (معماری مبتنی بر ۲ سرور ابری)

این سند راهنمای گام‌به‌گام برای استقرار سیستم اتوماسیون **BarPro** بر روی دو سرور ابری (ابرک) تهیه‌شده در ابر آروان با مشخصات زیر است:

*   **سرور اصلی (Node 1):**
    *   آی‌پی اینترنتی: `188.121.123.16`
    *   سخت‌افزار: 4 vCPU - 12 GB RAM
    *   وظیفه: اجرای کل پایگاه داده، ردیس، بک‌اند، فرانت‌اند، ورکر شماره ۱، ورکر شماره ۲ و سرویس‌های کمکی.
*   **سرور کمکی/پروکسی (Node 2):**
    *   آی‌پی اینترنتی: `95.38.233.90`
    *   سخت‌افزار: 4 vCPU - 12 GB RAM
    *   وظیفه: اجرای پراکسی خروجی Squid 2 (ترافیک ورکر شماره ۲ از این سرور خارج می‌شود تا سیستم هدف درخواست‌ها را با آی‌پی این سرور ببیند).

---

## 🗺️ نمای کلی معماری ارتباطات

```mermaid
graph TD
    subgraph Server_1_188.121.123.16 ["سرور اصلی Node 1"]
        Backend[Backend API / Nginx] --> Redis[(Redis)]
        Backend --> Postgres[(PostgreSQL)]
        Worker_1[Celery Worker 1] -- "Local Proxy" --> Squid_1[Squid Proxy 1]
        Worker_2[Celery Worker 2] -- "Remote Proxy (Port 3128)" --> WAN2
        Squid_1 -- "Egress IP: 188.121.123.16" --> UTCMS_1[UTCMS System]
    end

    subgraph Server_2_95.38.233.90 ["سرور پراکسی Node 2"]
        Squid_2[Squid Proxy 2]
    end

    WAN2 -- "Protected by Firewall" --> Squid_2
    Squid_2 -- "Egress IP: 95.38.233.90" --> UTCMS_2[UTCMS System]

    style Server_1_188.121.123.16 fill:#f5f7ff,stroke:#2b579a,stroke-width:2px;
    style Server_2_95.38.233.90 fill:#fff9f0,stroke:#d9534f,stroke-width:2px;
```

---

## 🔒 مرحله ۱: تنظیمات فایروال و امنیت در پنل ابر آروان

برای جلوگیری از سوءاستفاده از پراکسی سرور کمکی، باید پورت `3128` سرور دوم را **فقط و فقط** به روی آی‌پی سرور اول باز کنید.

1.  وارد پنل ابر آروان شوید.
2.  به بخش **سرور ابری** > **گروه‌های فایروال** (arDefault یا گروه اختصاصی) بروید.
3.  برای **سرور دوم (Node 2 - 95.38.233.90)** یک قانون ورودی (Inbound Rule) به شکل زیر اضافه کنید:
    *   **نوع پروتکل:** TCP
    *   **پورت:** `3128`
    *   **آدرس منبع (Source IP):** `188.121.123.16` (آی‌پی سرور اصلی)
    *   **عملیات:** Allow (مجاز)
4.  سایر درخواست‌ها به این پورت از اینترنت باید مسدود (Deny) باشند.

---

## 🛠️ مرحله ۲: آماده‌سازی سرور دوم (Node 2 - `95.38.233.90`)

بر روی سرور دوم فقط کافیست سرویس پراکسی Squid را با داکر بالا بیاورید.

1.  وارد سرور دوم شوید (از طریق SSH).
2.  داکر و داکر کامپوز را نصب کنید (در صورت عدم نصب):
    ```bash
    sudo apt update
    sudo apt install -y docker.io docker-compose
    ```
3.  یک پوشه برای تنظیمات پراکسی بسازید:
    ```bash
    mkdir -p /opt/squid
    cd /opt/squid
    ```
4.  فایل `squid.conf` را بسازید:
    ```bash
    nano squid.conf
    ```
    محتوای زیر را درون آن قرار دهید (آی‌پی سرور اول برای دسترسی مجاز تعریف شده است):
    ```squid
    # Squid Proxy Configuration on Node 2
    http_port 3128

    # Access Control List (ACL)
    # اجازه دسترسی فقط به آی‌پی سرور اصلی
    acl server1 src 188.121.123.16
    
    http_access allow server1
    http_access allow localhost
    http_access deny all

    # تنظیم آی‌پی خروجی سرور دوم
    tcp_outgoing_address 95.38.233.90

    # غیرفعال کردن کش
    cache deny all
    ```
5.  فایل `docker-compose.yml` را بسازید:
    ```bash
    nano docker-compose.yml
    ```
    محتوای زیر را درون آن قرار دهید:
    ```yaml
    version: '3.8'

    services:
      squid:
        image: ubuntu/squid:latest
        container_name: remote_squid
        restart: unless-stopped
        volumes:
          - ./squid.conf:/etc/squid/squid.conf:ro
        ports:
          - "3128:3128"
    ```
6.  سرویس پراکسی را اجرا کنید:
    ```bash
    sudo docker compose up -d
    ```

---

## 🚀 مرحله ۳: آماده‌سازی و اجرای سرور اصلی (Node 1 - `188.121.123.16`)

1.  وارد سرور اصلی شوید.
2.  کد پروژه را در مسیر `/opt/barpro` یا هر مسیر دلخواه دیگری کلون یا آپلود کنید.
3.  فایل تنظیمات محیطی `.env` را به صورت زیر پیکربندی کنید:
    ```env
    API_KEY="utcms_10c6461a53a0197c821d3cd3515f58b4f6bca2b4d9d7a366d6e3db9274178ccb"
    JWT_SECRET="Nf9o^A=9Ze)mAvK3)2AeCd(9yxRJhJ(CI85NneA$@Gqb1bGWF*(H8NSs&Oo#kTRQ"
    DRIVER_ENCRYPTION_KEY="xmq4TjTW_G@T9Yo@tCZgZ7HT)YjBKft9R4^va3n(6x-fzeh=2Fp$-5dqfojMP^G0"
    POSTGRES_PASSWORD="your_secure_postgres_password_here"
    REDIS_PASSWORD="your_secure_redis_password_here"
    DATABASE_URL="postgresql+asyncpg://postgres:your_secure_postgres_password_here@postgres:5432/utcms_rpa"
    REDIS_URL="redis://:your_secure_redis_password_here@redis:6379/0"
    FRONTEND_URL="http://188.121.123.16"
    NEXT_PUBLIC_API_URL="http://188.121.123.16:8000"
    ENVIRONMENT="production"
    MASTER_ADMIN_USERNAME=admin
    MASTER_ADMIN_PASSWORD=your_master_admin_password

    # تنظیمات معماری دو آی‌پی
    AVAILABLE_IP_INDICES="1,2"
    WORKER_1_PROXY="http://squid_1:3128"
    WORKER_2_PROXY="http://95.38.233.90:3128" # آدرس سرور دوم

    # تلگرام جهت دریافت هشدارهای خرابی آی‌پی یا مصرف رم بالا
    TELEGRAM_BOT_TOKEN="your_bot_token"
    TELEGRAM_CHAT_ID="your_chat_id"

    # تنظیمات مرورگر در سرور
    HEADLESS=true
    BLOCK_MAP_TILES=true
    ```
4.  فایل پراکسی محلی سرور اول `infra/squid/squid_1.conf` را ویرایش کرده و آی‌پی این سرور را جایگزین کنید:
    ```squid
    # Squid proxy configuration for IP 1
    http_port 3128

    acl localnet src 10.0.0.0/8
    acl localnet src 172.16.0.0/12
    acl localnet src 192.168.0.0/16

    http_access allow localnet
    http_access allow localhost
    http_access deny all

    # آی‌پی اینترنتی همین سرور
    tcp_outgoing_address 188.121.123.16

    cache deny all
    ```

5.  اجرای سرویس‌ها به استثنای سرویس‌های مربوط به آی‌پی شماره ۳ (زیرا فقط ۲ آی‌پی داریم):
    ```bash
    # اجرای بک‌اند، دیتابیس، ردیس، پراکسی محلی و ۲ ورکر
    docker compose --profile docker-backend up -d --build postgres redis squid_1 backend celery_worker_1 celery_worker_2 celery_beat frontend nginx prometheus
    ```

    > [!NOTE]
    > با اجرای دستور بالا، سرویس‌های غیرضروری مانند `squid_2` (چون پراکسی سرور دوم مستقل روی سرور خودش است)، `squid_3` و `celery_worker_3` اجرا نخواهند شد تا منابع رم سرور اصلی بیهوده هدر نرود.

---

## 💾 مرحله ۴: راه‌اندازی نسخه‌های پشتیبان روزانه (Google Drive Backups)

برای بکاپ‌گیری منظم و ارسال مستقیم فایل‌ها به گوگل درایو:

1.  ابزار `rclone` را روی سرور اصلی نصب کنید:
    ```bash
    sudo apt update
    sudo apt install -y rclone
    ```
2.  پیکربندی اتصال گوگل درایو با نام `gdrive`:
    ```bash
    rclone config
    ```
    *   گزینه `n` (New remote) را وارد کنید.
    *   نام آن را `gdrive` بگذارید.
    *   نوع فضای ذخیره‌سازی را `drive` (Google Drive) انتخاب کنید.
    *   سایر فیلدها را با مقادیر پیش‌فرض رد کرده و مراحل احراز هویت را در مرورگر سیستم خود تکمیل کنید تا مجوزهای دسترسی داده شود.
3.  تنظیم اسکریپت بکاپ در cron جهت اجرای هر روز راس ساعت ۳ صبح:
    ```bash
    crontab -e
    ```
    خط زیر را به انتهای فایل اضافه کنید:
    ```cron
    0 3 * * * /opt/barpro/scripts/db_backup.sh >> /opt/barpro/output/backups.log 2>&1
    ```
4.  فایل اسکریپت بک‌آپ را قابل‌اجرا کنید:
    ```bash
    chmod +x /opt/barpro/scripts/db_backup.sh
    ```

---

## 📊 مرحله ۵: راه‌اندازی مانیتورینگ و هشدارهای تلگرام

برای دریافت لحظه‌ای وضعیت قطع شدن موقت آی‌پی‌ها (توسط Circuit Breaker) یا پر شدن رم سرور:

1.  وابستگی‌های پایتون مانیتورینگ را نصب کنید:
    ```bash
    pip3 install redis psutil
    ```
2.  برای اجرای مانیتور به‌صورت یک پس‌زمینه (Background Daemon) دائمی:
    ```bash
    nohup python3 /opt/barpro/scripts/monitor_alerts.py > /opt/barpro/output/monitor.log 2>&1 &
    ```
    همچنین می‌توانید آن را به عنوان یک سیستم‌سرویس (`systemd`) ثبت کنید تا با ری‌استارت شدن سرور مجدداً بالا بیاید.

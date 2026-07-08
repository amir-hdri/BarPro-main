# راهنمای راه‌اندازی Docker در ایران

## مشکل
دسترسی به Docker Hub از ایران بدون VPN امکان‌پذیر نیست و mirrorهای ایرانی ناپایدار هستند.

## راه‌حل‌های پیشنهادی

### راه‌حل 1: استفاده از VPN (توصیه می‌شود)
1. VPN خود را روشن کنید
2. فایل‌های docker-compose.yml را به حالت اصلی برگردانید:
   ```bash
    cd /opt/barpro
    git checkout compose/infra.yml compose/proxy.yml compose/backend.yml compose/web.yml compose/monitoring.yml
   ```
3. سیستم را اجرا کنید:
   ```bash
   bash scripts/start_system.sh
   ```

### راه‌حل 2: تنظیم Mirror در Docker Desktop
1. Docker Desktop را باز کنید
2. به Settings > Docker Engine بروید
3. این تنظیمات را اضافه کنید:
   ```json
   {
     "registry-mirrors": [
       "https://registry.docker.ir",
       "https://docker.arvancloud.ir"
     ]
   }
   ```
4. Apply & Restart را بزنید
5. فایل‌های docker-compose.yml را به حالت اصلی برگردانید
6. دوباره تلاش کنید

### راه‌حل 3: دانلود دستی imageها
اگر دسترسی موقت به VPN دارید:
```bash
# VPN را روشن کنید
docker pull postgres:16-alpine
docker pull redis:7-alpine
docker pull nginx:1.27-alpine
docker pull prom/prometheus:v2.54.1
docker pull node:20-bookworm

# حالا می‌توانید VPN را خاموش کنید
# فایل‌های docker-compose.yml را به حالت اصلی برگردانید
cd /opt/barpro
git checkout compose/infra.yml compose/proxy.yml compose/backend.yml compose/web.yml compose/monitoring.yml scripts/start_system.sh

# سیستم را اجرا کنید
bash scripts/start_system.sh
```

### راه‌حل 4: استفاده از Shecan DNS
1. DNS سیستم خود را به Shecan تغییر دهید:
   - Primary DNS: 178.22.122.100
   - Secondary DNS: 185.51.200.2
2. Docker Desktop را restart کنید
3. فایل‌های docker-compose.yml را به حالت اصلی برگردانید
4. دوباره تلاش کنید

## بازگرداندن فایل‌ها به حالت اصلی
```bash
cd /opt/barpro
git checkout compose/infra.yml compose/proxy.yml compose/backend.yml compose/web.yml compose/monitoring.yml scripts/start_system.sh
```

## تست اتصال
```bash
# تست دسترسی به Docker Hub
docker pull hello-world

# اگر موفق شد، ادامه دهید
bash scripts/start_system.sh
```

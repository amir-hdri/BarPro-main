# 📋 Rollback Plan — بازگشت به نسخه قبل در صورت مشکل

**تاریخ تهیه**: 2026-07-14  
**تغییرات**: Race condition fix در scheduler

---

## 🎯 سناریوهای Rollback

### سناریو 1: مشکلات فوری (Critical Issues)
اگر بعد از deploy مشکلات زیر رخ دهد، **فوراً rollback کنید**:

- ❌ Workers کرش می‌کنند یا start نمی‌شوند
- ❌ Beat scheduler متوقف می‌شود
- ❌ خطای PostgreSQL: `syntax error` در FOR UPDATE
- ❌ تمام jobs به `failed` می‌روند
- ❌ CPU یا Memory spike شدید (>90%)

### سناریو 2: مشکلات غیر حاد (Monitor و تصمیم‌گیری)
این مشکلات نیاز به مانیتورینگ 1-2 ساعته دارند:

- ⚠️ بعضی jobs stuck می‌مانند (اما نه همه)
- ⚠️ Success rate کاهش یافته (اما نه صفر)
- ⚠️ Latency افزایش یافته (اما سرویس up است)

---

## 🔄 روش‌های Rollback

### روش 1: Rollback سریع (فقط کد — 2 دقیقه)

**استفاده**: برای مشکلات فوری که نیاز به برگشت سریع دارند

```bash
# 1. SSH به سرور
ssh ubuntu@188.121.123.16

cd /opt/barpro

# 2. بازگشت فایل‌ها از git
git log --oneline | head -5  # یافتن commit قبلی
git checkout HEAD~1 -- app/services/rpa_scheduler_service.py
git checkout HEAD~1 -- app/services/fuel_inquiry_service.py
git checkout HEAD~1 -- app/workers/celery_app.py

# 3. Restart backend
docker compose -f compose/backend.yml restart

# 4. چک کردن health
docker ps | grep barpro
docker logs barpro-celery-beat --tail 20
```

**زمان**: ~2 دقیقه  
**Downtime**: ~15 ثانیه (فقط restart workers)

---

### روش 2: Rollback کامل (تمام تغییرات — 5 دقیقه)

**استفاده**: اگر مطمئن نیستید کدام commit مشکل دارد

```bash
ssh ubuntu@188.121.123.16
cd /opt/barpro

# 1. لیست commits اخیر
git log --oneline --graph --decorate | head -10

# 2. Rollback به commit قبل از race fix
git reset --hard <COMMIT_HASH_BEFORE_RACE_FIX>

# مثال:
# git reset --hard a1b2c3d

# 3. Rebuild (اختیاری - فقط اگر Dockerfile تغییر کرده)
docker compose -f compose/backend.yml build

# 4. Restart
docker compose -f compose/backend.yml down
docker compose -f compose/backend.yml up -d

# 5. Verify
docker ps
docker logs barpro-backend --tail 30
```

**زمان**: ~5 دقیقه (با rebuild ~10 دقیقه)  
**Downtime**: ~30 ثانیه (down + up)

---

### روش 3: Restore از Backup (آخرین راه‌حل — 15 دقیقه)

**استفاده**: فقط اگر دیتابیس corrupt شده (خیلی بعید)

```bash
ssh ubuntu@188.121.123.16

# 1. لیست backups
ls -lh /opt/barpro/output/backups/

# 2. Restore از آخرین backup
cd /opt/barpro
latest_backup=$(ls -t output/backups/*.sql.gz | head -1)
echo "Restoring from: $latest_backup"

docker exec -i barpro-postgres psql -U postgres -d utcms_rpa < <(gunzip -c "$latest_backup")

# 3. Restart همه چیز
bash manage.sh restart

# 4. Verify
bash manage.sh health
```

**زمان**: ~15 دقیقه  
**Downtime**: ~2 دقیقه

---

## 🔍 تشخیص نیاز به Rollback

### چک‌های فوری (در 5 دقیقه اول)

```bash
# 1. وضعیت containers
docker ps | grep -E "barpro-(backend|worker|beat)"
# همه باید "healthy" یا "Up" باشند

# 2. لاگ Beat
docker logs barpro-celery-beat --tail 50 | grep -i "error\|failed"
# نباید ERROR زیاد باشد

# 3. لاگ Workers
docker logs barpro-worker-1 --tail 30 | grep -i "error\|crash"
# نباید crash loop باشد

# 4. PostgreSQL syntax
docker exec barpro-postgres psql -U postgres utcms_rpa -c \
  "SELECT job_id FROM waybill_jobs WHERE status = 'pending' LIMIT 1 FOR UPDATE SKIP LOCKED;"
# باید بدون خطا اجرا شود
```

### چک‌های تأخیری (بعد از 30 دقیقه)

```bash
# 1. Stuck jobs count
docker exec barpro-postgres psql -U postgres utcms_rpa -t -c \
  "SELECT COUNT(*) FROM waybill_jobs WHERE status = 'queued' AND updated_at < NOW() - INTERVAL '15 minutes';"

# اگر > 10 باشد → مشکل است

# 2. Success rate
docker exec barpro-postgres psql -U postgres utcms_rpa -c \
  "SELECT status, COUNT(*) FROM waybill_jobs WHERE created_at > NOW() - INTERVAL '1 hour' GROUP BY status;"

# Success rate باید > 50% باشد

# 3. Worker memory
docker stats --no-stream | grep worker
# Memory usage باید < 90% باشد
```

---

## 📊 Decision Tree

```
Deploy → Wait 5 min → Containers Up?
                            │
                     ┌──────┴──────┐
                   NO              YES
                    │               │
            Rollback روش 1    Wait 30 min → Jobs Processing?
                                              │
                                       ┌──────┴──────┐
                                     NO              YES
                                      │               │
                              Rollback روش 1    Monitor 24h
                                                      │
                                               Success rate > 80%?
                                                      │
                                               ┌──────┴──────┐
                                             NO              YES
                                              │               │
                                      Consider rollback   ✅ Success
```

---

## 📝 Rollback Checklist

```
[ ] 1. تأیید مشکل با چک‌های بالا
[ ] 2. اعلام به تیم (اگر production است)
[ ] 3. گرفتن snapshot فعلی (اختیاری):
       docker exec barpro-postgres pg_dump -U postgres utcms_rpa | gzip > /tmp/pre_rollback.sql.gz
[ ] 4. اجرای یکی از روش‌های rollback
[ ] 5. Verify با همان چک‌های deploy
[ ] 6. مانیتور کردن برای 1 ساعت
[ ] 7. مستند کردن علت rollback در TROUBLESHOOTING_LOG.md
```

---

## 🎯 نکات مهم

1. **Rollback سریع بهتر از debug طولانی است**  
   اگر در 30 دقیقه اول مشکل حل نشد، rollback کنید.

2. **Database rollback معمولاً لازم نیست**  
   تغییرات ما فقط code هستند، نه schema.

3. **Backup اتوماتیک**  
   قبل از deploy، backup اتوماتیک گرفته می‌شود:
   ```bash
   ls /opt/barpro/output/backups/pre_race_fix_*
   ```

4. **Git history همیشه موجود است**  
   می‌توانید به هر commit برگردید:
   ```bash
   git reflog  # نشان می‌دهد حتی بعد از reset
   ```

5. **صفر data loss**  
   Rollback فقط کد را برمی‌گرداند، دیتا دست نخورده می‌ماند.

---

## 📞 در صورت مشکلات غیرمنتظره

اگر rollback هم کار نکرد:

1. لاگ‌ها را ذخیره کنید:
   ```bash
   docker logs barpro-celery-beat > /tmp/beat.log
   docker logs barpro-worker-1 > /tmp/worker1.log
   bash manage.sh status > /tmp/status.log
   ```

2. مراجعه به `DIAGNOSIS_REPORT.md` → بخش troubleshooting

3. اجرای cleanup:
   ```bash
   docker compose -f compose/backend.yml down
   docker system prune -f
   docker compose -f compose/backend.yml up -d
   ```

---

**تهیه‌کننده**: Kiro AI  
**تاریخ**: 2026-07-14  
**نسخه**: 1.0

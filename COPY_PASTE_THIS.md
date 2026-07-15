# 📋 دستورالعمل Copy-Paste

**چون من نمی‌توانم مستقیماً به سرور شما متصل شوم، شما باید این کارها را انجام دهید:**

---

## ✅ گام 1: وارد سرور شوید

از یکی از این روش‌ها:
- Console سرور (از پنل ArvanCloud)
- VNC
- SSH محلی (اگر در شبکه سرور هستید)

---

## ✅ گام 2: این دستور را Copy-Paste کنید

```bash
cd /opt/barpro && cat > EXECUTE_ON_SERVER.sh << 'SCRIPT_EOF'
```

سپس محتوای کامل فایل `EXECUTE_ON_SERVER.sh` را copy کنید و paste کنید، و در آخر:

```bash
SCRIPT_EOF
```

---

## ✅ گام 3: اجرا کنید

```bash
chmod +x EXECUTE_ON_SERVER.sh
bash EXECUTE_ON_SERVER.sh
```

---

## 📊 نتیجه انتظاری

### موفقیت 100% ✅
```
🎉 تبریک! سیستم با 100% موفقیت کار می‌کند!
Success Rate: 100%
```

### موفقیت 80-99% ⚠️
```
✓ خوب! سیستم با 85% موفقیت کار می‌کند
```
→ دوباره اجرا کنید

### شکست <80% ❌
```
⚠️ نیاز به بهبود: Success Rate = 60%
```
→ لاگ‌ها را بررسی کنید:
```bash
docker logs --tail 100 barpro-celery-worker-1
```

---

## 🆘 اگر مشکلی بود

1. محتوای فایل `EXECUTE_ON_SERVER.sh` را از GitHub بگیرید
2. یا از فایل محلی `/Users/amirheidari/GitHub/BarPro-main/EXECUTE_ON_SERVER.sh`
3. Manual copy-paste کنید

---

**زمان کل:** 15-20 دقیقه ⏱️

# TODO - ایجاد کاربر/کلاینت و تست اجرای واقعی سیستم

- [x] اجرای واقعی پروژه (start_system)
- [x] بررسی سلامت سیستم (check_health)
- [x] آماده‌سازی دیتابیس/مهاجرت‌ها در صورت نیاز (init_database / alembic upgrade)
- [x] لاگین به Master Admin برای گرفتن JWT (POST /api/v1/admin/login)
- [x] ثبت کلاینت با مشخصات داده‌شده (POST /api/v1/auth/register) با:
  - client_code: hamid
  - name: hamid
  - phone: 09184111222
  - email: hamid@gmail.com
  - password: Aa123456
- [x] لاگین کلاینت (POST /api/v1/auth/login) و گرفتن JWT
- [x] تست صحت کارکرد با GET /api/v1/auth/me (با Authorization Bearer)
- [ ] (اختیاری) تست GET /api/v1/auth/stats برای اطمینان از tenant isolation
- [ ] گزارش نتیجه نهایی و در صورت خطا، بررسی لاگ‌ها و اصلاح

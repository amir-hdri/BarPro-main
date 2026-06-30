#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  run_migrations.sh — اجرای Alembic migrations روی دیتابیس تولید
#
#  این اسکریپت migrationهای معوق دیتابیس را اجرا می‌کند.
#  در صورت نیاز به migration دستی (مثلاً ایندکس‌های بهینه‌سازی)،
#  می‌توان از این اسکریپت استفاده کرد.
#
#  استفاده:
#    bash scripts/run_migrations.sh
#
#  معادل دستی (در صورت عدم دسترسی به اسکریپت):
#    docker exec barpro-backend alembic upgrade head
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

log_info()  { echo -e "\033[1;34mℹ️  $*\033[0m"; }
log_ok()    { echo -e "\033[1;32m✅  $*\033[0m"; }
log_error() { echo -e "\033[1;31m❌  $*\033[0m"; }

# اطمینان از در حال اجرا بودن دیتابیس
if ! docker inspect barpro-postgres &>/dev/null; then
  log_error "کانتینر barpro-postgres در حال اجرا نیست."
  log_info "دستور: bash manage.sh start infra"
  exit 1
fi

# انتخاب کانتینر برای اجرای migration
if docker inspect barpro-backend &>/dev/null; then
  CONTAINER="barpro-backend"
elif docker inspect barpro-celery-beat &>/dev/null; then
  CONTAINER="barpro-celery-beat"
else
  log_error "هیچ کانتینر بک‌اندی (backend/celery_beat) در حال اجرا نیست."
  log_info "دستور: bash manage.sh start backend"
  exit 1
fi

log_info "اجرای migrationها روی کانتینر: $CONTAINER"
docker exec "$CONTAINER" alembic upgrade head

log_ok "✅ migrationها با موفقیت اجرا شدند!"

# نمایش ایندکس‌های جدید
echo ""
echo "ایندکس‌های دیتابیس:"
docker exec barpro-postgres psql -U postgres -d utcms_rpa -c "
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'waybill_jobs'
ORDER BY indexname;
" 2>/dev/null || echo "(نمی‌توان ایندکس‌ها را نمایش داد)"

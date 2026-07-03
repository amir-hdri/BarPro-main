# ═══════════════════════════════════════════════════════════════
#  BarPro — Dockerfile
#  Registry : docker.arvancloud.ir  (مخزن ایرانی)
# PyPI     : pypi.org (قابل دسترس از سرور آروان‌کلود — Tsinghua mirror unstable from Iran)
#  PyTorch  : download.pytorch.org/whl/cpu
# ═══════════════════════════════════════════════════════════════

# ── مرحله ۱: نصب وابستگی‌های Python ──────────────────────────
FROM python:3.11-slim AS builder


ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build


COPY requirements.txt ./

# First install torch (CPU version) which is the heaviest
RUN pip install --no-cache-dir \
    --index-url https://mirror-pypi.runflare.com/simple \
    --extra-index-url https://pypi.org/simple \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    --retries 30 \
    --timeout 1000 \
    "torch>=2.5.1"

# Then install tensorflow-cpu and playwright which are also heavy
RUN pip install --no-cache-dir \
    --index-url https://mirror-pypi.runflare.com/simple \
    --extra-index-url https://pypi.org/simple \
    --retries 30 \
    --timeout 1000 \
    "tensorflow-cpu>=2.16.0" "playwright>=1.49.0"

# Finally copy requirements.txt and install the rest of the packages
COPY requirements.txt ./
RUN pip install --no-cache-dir \
    --index-url https://mirror-pypi.runflare.com/simple \
    --extra-index-url https://pypi.org/simple \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    --retries 30 \
    --timeout 1000 \
    -r requirements.txt

# ── مرحله ۲: image تولید ──────────────────────────────────────
FROM python:3.11-slim AS production

RUN sed -i 's/deb.debian.org/mirror.iranserver.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's/deb.debian.org/mirror.iranserver.com/g' /etc/apt/sources.list 2>/dev/null || true

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    # مسیر نصب Playwright (به عنوان root قبل از تغییر user)
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers \
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
    PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium

WORKDIR /app

# کتابخانه‌های سیستمی مورد نیاز Playwright/Chromium و خود Chromium
RUN apt-get -o Acquire::Check-Valid-Until=false update && apt-get install -y --no-install-recommends \
    # Chromium core
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 \
    libatspi2.0-0 libx11-6 libxcomposite1 libxdamage1 \
    libxext6 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 libxshmfence1 \
    libx11-xcb1 libxcb1 libxcursor1 libxi6 libxtst6 \
    # ابزارهای سیستمی و Chromium
    curl wget ca-certificates chromium \
    && rm -rf /var/lib/apt/lists/*

# کپی Python packages از مرحله builder
COPY --from=builder /usr/local/lib/python3.11/site-packages \
                    /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

RUN mkdir -p /opt/playwright-browsers

# کپی کد اپلیکیشن
COPY app         ./app
COPY scripts     ./scripts
COPY alembic     ./alembic
COPY alembic.ini ./alembic.ini
COPY persian_number_ocr.keras ./persian_number_ocr.keras

# ساخت پوشه‌های مورد نیاز
RUN mkdir -p /app/output/backups /app/output/logs

# کاربر غیر-root برای امنیت
RUN useradd --system --uid 10001 --no-create-home appuser \
    && chown -R appuser:appuser /app /opt/playwright-browsers

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--loop", "uvloop", \
     "--timeout-keep-alive", "30"]

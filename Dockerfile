# ═══════════════════════════════════════════════════════════════
#  BarPro — Dockerfile
#  Registry : Docker Hub (upstream)
# PyPI     : pypi.org (upstream; no regional mirror)
#  PyTorch  : download.pytorch.org/whl/cpu
# ═══════════════════════════════════════════════════════════════

# ── مرحله ۱: نصب وابستگی‌های Python ──────────────────────────
FROM python:3.11-slim AS builder


# Optional build-only egress for package/model downloads.  Values are supplied
# by the deployment environment and are intentionally not copied to the final
# image; this is needed on hosts whose direct egress is filtered.
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG ALL_PROXY
ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    ALL_PROXY=${ALL_PROXY}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN python -m pip install --no-cache-dir --upgrade "pip==26.2.1"

COPY requirements.txt ./

# First install torch (CPU version) which is the heaviest
RUN pip install --no-cache-dir \
    --index-url https://pypi.org/simple \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    --retries 30 \
    --timeout 1000 \
    "torch>=2.13.0"

# Then install TensorFlow from the upstream PyPI index. Retries only improve
# resilience; they do not switch to a regional mirror.
RUN if [ "$(uname -m)" = "x86_64" ]; then TF_PACKAGE="tensorflow-cpu>=2.18.0"; else TF_PACKAGE="tensorflow>=2.18.0"; fi \
    && pip install --no-cache-dir \
    --index-url https://pypi.org/simple \
    --retries 30 \
    --timeout 1000 \
    "$TF_PACKAGE"

# Install Playwright from the upstream PyPI index with a version fallback
RUN pip install --no-cache-dir \
    --index-url https://pypi.org/simple \
    --retries 30 \
    --timeout 1000 \
    "playwright>=1.49.0" || \
    pip install --no-cache-dir \
    --index-url https://pypi.org/simple \
    --retries 10 \
    --timeout 600 \
    "playwright==1.49.0"

# Finally install the rest of the packages
COPY requirements.txt ./
RUN pip install --no-cache-dir \
    --index-url https://pypi.org/simple \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    --retries 30 \
    --timeout 1000 \
    -r requirements.txt

# ── مرحله ۲: image تولید ──────────────────────────────────────
FROM python:3.11-slim AS production

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG ALL_PROXY

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    # مسیر نصب Playwright (به عنوان root قبل از تغییر user)
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers

WORKDIR /app

# کتابخانه‌های سیستمی مورد نیاز Playwright/Chromium
RUN apt-get -o Acquire::Check-Valid-Until=false update && apt-get install -y --no-install-recommends \
    # Chromium core
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 \
    libatspi2.0-0 libx11-6 libxcomposite1 libxdamage1 \
    libxext6 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 libxshmfence1 \
    libx11-xcb1 libxcb1 libxcursor1 libxi6 libxtst6 \
    # ابزارهای سیستمی
    curl wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# کپی Python packages از مرحله builder
COPY --from=builder /usr/local/lib/python3.11/site-packages \
                    /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

RUN mkdir -p /opt/playwright-browsers \
    && export HTTP_PROXY HTTPS_PROXY ALL_PROXY \
    && playwright install chromium

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
     "--loop", "auto", \
     "--timeout-keep-alive", "30", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "127.0.0.1,172.16.0.0/12,10.0.0.0/8"]

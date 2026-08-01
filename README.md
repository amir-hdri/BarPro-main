<div align="center">
  <img src="https://img.shields.io/badge/Status-Production%20Ready-success?style=for-the-badge" alt="Status" />
  <img src="https://img.shields.io/badge/Version-1.2.0-blue?style=for-the-badge" alt="Version" />
  <img src="https://img.shields.io/badge/Tests-414%20Passed-brightgreen?style=for-the-badge" alt="Tests" />
  <img src="https://img.shields.io/badge/License-Proprietary-red?style=for-the-badge" alt="License" />
</div>

<br />

<div align="center">
  <h1 align="center">🚀 BarPro</h1>
  <p align="center">
    <strong>Enterprise Multi-tenant RPA & Waybill Automation Framework</strong>
    <br />
    <em>سیستم اتوماسیون هوشمند بارنامه UTCMS</em>
    <br /><br />
    <a href="#-architecture">Architecture</a>
    ·
    <a href="#-quick-start">Quick Start</a>
    ·
    <a href="#-operational-commands">Operations</a>
    ·
    <a href="./CRITICAL_RULES.md">⚠️ Critical Rules</a>
    ·
    <a href="./AGENTS.md">AI Agent Guide</a>
  </p>
</div>

---

## ⚠️ مهم — قبل از هر تغییر بخوانید

> **[CRITICAL_RULES.md](./CRITICAL_RULES.md)** — خطوط قرمز و قوانین حیاتی پروژه را پیش از هر توسعه مطالعه کنید.

---

## 🌟 Key Features

### 🏢 Real Multi-tenancy
- **Data Isolation:** Strict data separation at the database level using scoped access
- **Independent Profiles:** Manage fleets, drivers, and routes per tenant securely
- **Master Admin Dashboard:** Centralized control for onboarding, quota management, and global live monitoring
- **Universal Admin Access:** Master admin can view and manage all tenant resources globally

### 🤖 Advanced RPA Engine
- **Human-like Behavior:** Sophisticated simulation of human interactions (typing delays, parabolic mouse movements) to bypass WAFs and anti-bot mechanisms
- **Smart Map Injection:** Direct coordinate injection into JavaScript globals to bypass interactive search bottlenecks
- **Intelligent Captcha Solver:** ML-powered CNN (login math), PyTorch CRNN (fuel Persian), and Keras OCR fallback — all in-process (no subprocess OOM risk)
- **Self-Healing Navigation:** Dynamic element detection and "Loading Overlay" management for resilient web interactions
- **Browser Context Pooling:** Chrome instances recycled after 20 successful jobs — 90% fewer cold starts
- **Pre-flight Proxy Health Check:** Squid proxy is validated before each browser session

### 🛡️ Enterprise-Grade Security & Resilience
- **JWT in httpOnly Cookies:** Tokens never exposed to JavaScript — XSS-safe authentication
- **Fail-closed Rate Limiter:** Returns HTTP 429 even when Redis is unavailable — no bypass possible
- **Token Blacklist Fail-closed:** Revoked tokens remain invalid even during Redis outages
- **IP Spoofing Prevention:** Rate limiter uses `request.client.host` (Nginx-set), ignores `X-Forwarded-For`
- **Automatic Stuck Job Recovery:** Periodic cleanup of jobs stuck in `QUEUED` or `IN_PROGRESS` states
- **Driver Submission Locking:** Serializes concurrent jobs for the same driver to prevent UTCMS conflicts
- **Idempotency:** Jobs already holding a UTCMS tracking code are skipped automatically

### ⚡ Performance Optimizations
- **Redis Queue Depth:** HINCRBY counters replace full table scans on every status transition
- **WebSocket pub/sub Bridge:** Worker-originated events reach API process cross-process via Redis
- **Connection Pool Reuse:** `AsyncAdaptedQueuePool(2,2)` — no connection storms
- **bcrypt Off Event Loop:** Hashing/verification runs via `asyncio.to_thread` — non-blocking
- **Bulk DB Fetches:** Admin job list uses `Client.id.in_(...)` — no N+1 queries
- **React.memo:** Table rows and cards don't re-render on every WebSocket tick

---

## 🏗️ Architecture

```
Client Browser → Nginx (port 80/443) → FastAPI Backend (port 8000)
                                             ├── PostgreSQL 16 (SQLModel/AsyncPG)
                                             ├── Redis 7 (cache/queue/pub-sub)
                                             ├── Celery Workers ×3 (via Squid proxies)
                                             └── Prometheus (monitoring)
Frontend: Next.js 15 (TypeScript, Tailwind CSS, React 19)
```

**Single-server deployment** — 13 Docker containers on one host with 2 public IPs.

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend | Python / FastAPI | 3.11 / latest |
| Frontend | Next.js / TypeScript | 15 / 5.x |
| Database | PostgreSQL + SQLModel | 16 |
| Queue | Celery + Redis | latest |
| RPA | Playwright (Chromium) | latest |
| Proxy | Squid | latest |
| Monitoring | Prometheus | latest |
| Reverse Proxy | Nginx | 1.27-alpine |

### Proxy Topology
| Proxy | Port | Egress IP | Used By |
|-------|------|-----------|---------|
| Squid 1 | 3128 | <CENTRAL_IP>    | Worker 1 |
| Squid 2 | 3129 | <SECONDARY_EGRESS_IP>  | Worker 2 |
| Squid 3 | 3130 | <SECONDARY_EGRESS_IP>  | Worker 3 |

### Captcha Models
| Page | Solver | Model |
|------|--------|-------|
| Login (math: "2+3") | PyTorch CNN | `assets/captcha_cnn.pth` |
| Fuel Inquiry (Persian words) | PyTorch CRNN | `assets/fuel_captcha_crnn.pth` |
| Fuel Inquiry fallback | Keras OCR | `persian_number_ocr.keras` |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 20+
- Docker & Docker Compose

### Installation

```bash
# Clone
git clone <repository_url>
cd BarPro

# Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Playwright browser
playwright install chromium

# Frontend
cd apps/web && npm install && cd ../..
```

### Environment Setup

```bash
cp .env.example .env
# Edit .env — fill in all required values
# JWT_SECRET must be ≥32 characters
# See CRITICAL_RULES.md for security requirements
```

### Run Tests

```bash
.venv/bin/pytest tests/ -q --tb=short
# Expected: ≥414 passed, 0 failed
```

### Start System

```bash
bash manage.sh start    # Full system bootstrap
bash manage.sh health   # Verify all services
```

---

## 🛠️ Operational Commands

| Command | Description |
|---------|-------------|
| `bash manage.sh start` | Full system bootstrap (respects layer order) |
| `bash manage.sh stop` | Graceful shutdown (data retained) |
| `bash manage.sh status` | CPU/RAM/disk/container status |
| `bash manage.sh health` | Verify DB/Redis/API/Frontend health |
| `bash manage.sh deploy` | Pull from GitHub, run migrations, restart |
| `bash manage.sh migrate` | Run Alembic migrations manually |
| `bash manage.sh backup-db` | PostgreSQL snapshot |
| `.venv/bin/pytest tests/` | Full test suite |

### Docker Compose Layers (in order)

```bash
docker compose -f compose/infra.yml up -d       # PostgreSQL + Redis
docker compose -f compose/proxy.yml up -d       # Squid ×3
docker compose -f compose/backend.yml up -d     # FastAPI + Workers + Beat
docker compose -f compose/web.yml up -d         # Nginx + Next.js
docker compose -f compose/monitoring.yml up -d  # Prometheus
```

---

## 📋 Current Status

### Tests
```
414 passed, 4 skipped, 0 failed  (as of 2026-07-27)
```

### Alembic Migration Head
```
015_add_client_subscription_dates
```

### Required ML Assets
- `persian_number_ocr.keras` (root — Keras OCR for fuel captcha)
- `app/automation/captcha/assets/captcha_cnn.pth` (login math CNN)
- `app/automation/captcha/assets/fuel_captcha_crnn.pth` (fuel CRNN)
- `app/automation/captcha/assets/fuel_captcha_vocab.json` (CRNN vocab)

### Remaining Server-Side Actions
- [ ] Install Let's Encrypt cert → uncomment `listen 443` in nginx.conf → set `AUTH_COOKIE_SECURE=true`
- [ ] Run `bash manage.sh migrate` on production DB
- [ ] Run `sudo bash scripts/secure_squid_ports.sh` (lock down Squid 3129/3130)
- [ ] Add to crontab: `@reboot sudo bash /opt/barpro/scripts/secure_squid_ports.sh`
- [ ] Run PostgreSQL optimization indexes (see `CRITICAL_RULES.md`)

---

## 📁 Project Structure

```
BarPro/
├── app/                    # Backend (FastAPI)
│   ├── api/                # Route handlers
│   ├── automation/         # RPA engine (browser, captcha, proxy)
│   ├── core/               # Config, database, redis, security, rate_limiter
│   ├── models/             # SQLModel database models
│   ├── bot/                # Smart locators + captcha interception
│   ├── services/           # Business logic layer
│   ├── workers/            # Celery tasks
│   ├── realtime/           # WebSocket + Redis pub/sub event hub
│   └── rpa/                # RPA services (auth, submit, scheduler)
├── apps/web/               # Frontend (Next.js 15)
│   └── src/
│       ├── app/            # App Router pages
│       ├── components/     # Shared React components
│       ├── hooks/          # Custom hooks (useWaybillJob, etc.)
│       ├── lib/            # Utilities (api, auth, plate, format)
│       └── schemas/        # Zod validation schemas
├── compose/                # Docker Compose layered files
├── infra/                  # Nginx, Squid, Prometheus configs
├── alembic/                # Database migrations
├── tests/                  # Pytest test suite (414+ tests)
├── scripts/                # Utility and deploy scripts
├── CRITICAL_RULES.md       # ⚠️ خطوط قرمز و قوانین حیاتی
├── AGENTS.md               # AI agent guide
└── manage.sh               # System management script
```

---

## 🔐 Security Notes

- **Never hardcode credentials** — use `.env` only
- **Never commit `.env`** — it's in `.gitignore`
- **JWT_SECRET** must be ≥32 characters
- **AUTH_COOKIE_SECURE** must be `false` on HTTP, `true` after HTTPS
- **Prometheus** port 9090 is internal-only (`expose`, not `ports`)
- See **[CRITICAL_RULES.md](./CRITICAL_RULES.md)** for complete security requirements

---

## 📄 Documentation Index

| Document | Contents |
|----------|----------|
| [CRITICAL_RULES.md](./CRITICAL_RULES.md) | ⚠️ خطوط قرمز — must read before any change |
| [AGENTS.md](./AGENTS.md) | AI agent guide with full architecture overview |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Detailed system architecture |
| [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) | Step-by-step deployment |
| [ISSUES.md](./ISSUES.md) | Known issues and status |
| [.env.example](./.env.example) | Environment variables template |

---

*For Persian documentation, see the فارسی section below.*

## 🇮🇷 راهنمای فارسی

**BarPro** یک فریم‌ورک پیشرفته و صنعتی برای خودکارسازی فرآیندهای ثبت بارنامه در سامانه کشوری UTCMS است. این سیستم با معماری مدرن چند مستاجره، پایداری عملیات در مقیاس سازمانی را تضمین می‌کند.

### ویژگی‌های کلیدی
- معماری چند مستاجره با جداسازی کامل داده
- موتور RPA با شبیه‌سازی رفتار انسانی و حل خودکار کپچا
- JWT در کوکی httpOnly — امنیت بالا در برابر XSS
- Rate Limiter fail-closed — بسته شدن در صورت قطع Redis
- بازیابی خودکار jobهای stuck
- هدف: ≥414 تست پاس شده، 0 شکست

### راه‌اندازی سریع
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # تنظیم متغیرهای محیطی
bash manage.sh start
```

> **پیش از هر تغییر:** [CRITICAL_RULES.md](./CRITICAL_RULES.md) را مطالعه کنید.

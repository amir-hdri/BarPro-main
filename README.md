# 🚀 BarPro: Enterprise Multi-tenant RPA & Waybill Automation

[![Architecture](https://img.shields.io/badge/Architecture-Monorepo-blue.svg)]()
[![Backend](https://img.shields.io/badge/Backend-FastAPI-green.svg)](https://fastapi.tiangolo.com/)
[![Frontend](https://img.shields.io/badge/Frontend-Next.js%2015-black.svg)](https://nextjs.org/)
[![Automation](https://img.shields.io/badge/Automation-Playwright-orange.svg)](https://playwright.dev/python/)
[![Database](https://img.shields.io/badge/Database-PostgreSQL-blue.svg)](https://www.postgresql.org/)
[![Caching](https://img.shields.io/badge/Caching-Redis-red.svg)](https://redis.io/)
[![Queue](https://img.shields.io/badge/Queue-Celery-green.svg)](https://docs.celeryq.dev/)

**BarPro** is an advanced, industrial-grade RPA (Robotic Process Automation) framework designed for automated waybill registration on the **UTCMS** national portal. Built with a modern full-stack architecture, it combines high-performance backend processing with a seamless user experience, ensuring reliability even under heavy enterprise workloads.

[فارسی (Persian)](#-سیستم-اتوماسیون-جامع-بارنامه-utcms-barpro)

---

## ✨ Key Features

### 🏢 Real Multi-tenancy

* **Data Isolation:** Strict data separation at the database level using `client_id` scoping.
* **Independent Profiles:** Separate management for fleets, drivers, and routes for each tenant.
* **Master Admin Dashboard:** Centralized control for tenant onboarding, quota management, and live monitoring.

### 🤖 Advanced RPA Engine

* **Human-like Behavior:** Sophisticated simulation of human interactions to bypass anti-bot mechanisms.
* **Smart Map Injection:** Direct coordinate injection into JavaScript globals (`LatSource`/`LngSource`) to bypass search bottlenecks.
* **Intelligent Captcha Solver:** ML-powered math and visual OCR solver with automatic retry logic.
* **Self-Healing Navigation:** Dynamic element detection and "Loading Overlay" management for resilient web interactions.

### 🛡️ Enterprise-Grade Resilience

* **Automatic Stuck Job Recovery:** Periodic cleanup of jobs stuck in `QUEUED` or `IN_PROGRESS` states.
* **Global Safety Net:** Integrated error handling that prevents processing deadlocks during unexpected browser crashes.
* **Session Persistence:** Intelligent session bundle storage to minimize redundant logins.

---

## 🏗️ Architecture & Stack

### Technology Stack

* **Backend:** FastAPI (Python 3.11)
* **Frontend:** Next.js 15 (TypeScript, Tailwind CSS)
* **Database:** PostgreSQL 16 (via SQLModel/AsyncPG)
* **Task Queue:** Celery + Redis
* **Automation:** Playwright (Headless/Headful)
* **Monitoring:** Prometheus + Custom RPA Inspector

### Directory Structure

```text
.
├── app/                # Backend Core (FastAPI)
│   ├── api/            # REST API Routes
│   ├── automation/     # RPA Engine (Playwright logic)
│   ├── services/       # Business Logic & Orchestration
│   └── workers/        # Celery Task Workers
├── apps/
│   └── web/            # Frontend (Next.js)
├── alembic/            # Database Migrations
├── scripts/            # DevOps & Management Scripts
└── output/             # Logs, Snapshots, and Reports
```

---

## 🚀 Quick Start

### Prerequisites

* Python 3.11+
* Node.js 20+
* Docker & Docker Compose (for Postgres/Redis)

### 1. Installation

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Install Frontend dependencies
cd apps/web && npm install
```

### 2. Environment Setup

Create a `.env` file in the root directory. Use the provided documentation to configure your database and security keys.

### 3. Running the System

The system is managed via unified shell scripts for easy operation:

```bash
# Start all services (Backend, Frontend, Workers, Redis, Postgres)
./scripts/start_system.sh

# Stop all services and generate a health report
./scripts/stop_system.sh
```

---

## 🛠️ Operational Commands

| Command | Description |
| :--- | :--- |
| `./scripts/start_system.sh` | Full system bootstrap in background |
| `./scripts/stop_system.sh` | Graceful shutdown of all components |
| `./scripts/check_health.sh` | Instant health check of DB, Redis, and API |
| `pytest` | Run comprehensive integration & unit tests |
| `alembic upgrade head` | Apply latest database schema migrations |

---

## 🏥 System Resilience (Self-Healing)

BarPro is designed to be "always-on." It includes:

* **Watcher Daemon:** Monitor active jobs and recover orphans.
* **Circuit Breakers:** Prevent overloading the target portal during downtime.
* **Diagnostic Reports:** Automated generation of JSON reports on every shutdown.

---

# 🚀 سیستم اتوماسیون جامع بارنامه UTCMS (BarPro)

**BarPro** یک فریم‌ورک پیشرفته و صنعتی برای خودکارسازی فرآیندهای ثبت بارنامه در سامانه کشوری **UTCMS** است. این سیستم با معماری مدرن و قابلیت اطمینان بالا، پایداری عملیات در مقیاس سازمانی را تضمین می‌کند.

### 💎 ویژگی‌های برتر

* **معماری چند مستاجره:** جداسازی کامل داده‌ها و مدیریت کوتای هر مشتری.
* **رباتیک پیشرفته:** شبیه‌سازی دقیق رفتار انسانی و حل خودکار کپچا.
* **تاب‌آوری هوشمند:** بازیابی خودکار تسک‌های متوقف شده و مدیریت خطاهای بحرانی.
* **مانیتورینگ زنده:** مجهز به سیستم بازرس RPA برای پایش لحظه‌ای عملیات.

### 🚦 راه اندازی سریع

1. نصب وابستگی‌های پایتون: `pip install -r requirements.txt`
2. نصب مرورگر: `playwright install chromium`
3. نصب فرانت‌اند: `cd apps/web && npm install`
4. اجرای سیستم: `./scripts/start_system.sh`

---
**Status:** Production Ready ✅  
**Last Updated:** June 2026  
**License:** Enterprise Proprietary  

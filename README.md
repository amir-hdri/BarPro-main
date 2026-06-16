<div align="center">
  <img src="https://img.shields.io/badge/Status-Production%20Ready-success?style=for-the-badge" alt="Status" />
  <img src="https://img.shields.io/badge/Version-1.0.0-blue?style=for-the-badge" alt="Version" />
  <img src="https://img.shields.io/badge/License-Proprietary-red?style=for-the-badge" alt="License" />
</div>

<br />

<div align="center">
  <h1 align="center">🚀 BarPro</h1>
  <p align="center">
    <strong>Enterprise Multi-tenant RPA & Waybill Automation Framework</strong>
    <br />
    <br />
    <a href="#-سیستم-اتوماسیون-جامع-بارنامه-utcms-barpro">🇮🇷 مستندات فارسی (Persian)</a>
    ·
    <a href="docs/architecture/PROJECT_STRUCTURE.md">Architecture Docs</a>
    ·
    <a href="docs/operations/TROUBLESHOOTING.md">Troubleshooting</a>
  </p>
</div>

---

**BarPro** is an advanced, industrial-grade RPA (Robotic Process Automation) framework designed for automated waybill registration on the national portal. Built with a modern full-stack architecture, it combines high-performance backend processing with a seamless user experience, ensuring reliability even under heavy enterprise workloads.

## 🌟 Key Features

### 🏢 Real Multi-tenancy
* **Data Isolation:** Strict data separation at the database level using scoped access.
* **Independent Profiles:** Manage fleets, drivers, and routes for each tenant securely.
* **Master Admin Dashboard:** Centralized control for onboarding, quota management, and global live monitoring.

### 🤖 Advanced RPA Engine
* **Human-like Behavior:** Sophisticated simulation of human interactions (typing delays, parabolic mouse movements) to bypass WAFs and anti-bot mechanisms.
* **Smart Map Injection:** Direct coordinate injection into JavaScript globals to bypass interactive search bottlenecks.
* **Intelligent Captcha Solver:** ML-powered math and visual OCR solver with automatic retry logic.
* **Self-Healing Navigation:** Dynamic element detection and "Loading Overlay" management for resilient web interactions.

### 🛡️ Enterprise-Grade Resilience
* **Automatic Stuck Job Recovery:** Periodic cleanup of jobs stuck in `QUEUED` or `IN_PROGRESS` states.
* **Global Safety Net:** Integrated error handling that prevents processing deadlocks during unexpected browser crashes.
* **Session Persistence:** Intelligent session bundle storage to minimize redundant logins and reduce detection footprints.

---

## 🏗️ Technology Stack

| Layer       | Technology |
| ----------- | ---------- |
| **Backend** | [FastAPI](https://fastapi.tiangolo.com/) (Python 3.14) |
| **Frontend**| [Next.js 15](https://nextjs.org/) (TypeScript, Tailwind CSS) |
| **Database**| [PostgreSQL 16](https://www.postgresql.org/) (SQLModel/AsyncPG) |
| **Queue**   | [Celery](https://docs.celeryq.dev/) + [Redis](https://redis.io/) |
| **Automation**| [Playwright](https://playwright.dev/python/) |
| **Monitoring**| Custom RPA Inspector Event Bridge |

---

## 🚀 Quick Start

### Prerequisites
* Python 3.11+ (Recommended 3.14)
* Node.js 20+
* Docker & Docker Compose

### 1. Installation

```bash
# Clone the repository
git clone <repository_url>
cd BarPro

# Set up Python virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Install Playwright browsers for the automation engine
playwright install chromium

# Install Frontend dependencies
cd apps/web && npm install
```

### 2. Environment Setup
Create a `.env` file in the root directory. Configure your database, Redis, and security keys based on the provided `.env.example` (or internal documentation).

### 3. Running the System
The system is managed via unified shell scripts for easy operation:

```bash
# Start all services (Backend, Frontend, Workers, Redis, Postgres)
./scripts/start_system.sh

# Stop all services gracefully
./scripts/stop_system.sh
```

---

## 🛠️ Operational Commands

| Command | Description |
| :--- | :--- |
| `./scripts/start_system.sh` | Full system bootstrap in the background. |
| `./scripts/stop_system.sh` | Graceful shutdown of all components. |
| `./scripts/check_health.sh` | Instant health check of DB, Redis, and API. |
| `pytest` | Run comprehensive integration & unit tests (Optimized to be extremely fast). |
| `alembic upgrade head` | Apply the latest database schema migrations. |

---

# 🚀 سیستم اتوماسیون جامع بارنامه UTCMS (BarPro)

**BarPro** یک فریم‌ورک پیشرفته و صنعتی برای خودکارسازی فرآیندهای ثبت بارنامه در سامانه کشوری است. این سیستم با معماری مدرن و قابلیت اطمینان بالا، پایداری عملیات در مقیاس سازمانی را تضمین می‌کند و تمامی مراحل وقت‌گیر را برای شرکت‌های حمل و نقل کاملا اتوماتیک می‌سازد.

### 💎 ویژگی‌های برتر

* **معماری چند مستاجره واقعی (Multi-tenant):** جداسازی کامل و امن داده‌های شرکت‌های مختلف.
* **موتور رباتیک پیشرفته:** شبیه‌سازی فوق‌العاده دقیق رفتار انسانی (تایپ، حرکت موس، مکث‌ها) و حل خودکار کپچاهای پیچیده تصویری و ریاضی.
* **سرعت بالا و بهینه‌سازی شده:** تزریق مستقیم موقعیت‌های جغرافیایی روی نقشه و حذف تاخیرهای استاتیک جهت تسریع بی‌نظیر صدور بارنامه.
* **تاب‌آوری هوشمند:** بازیابی خودکار عملیات متوقف شده (Self-Healing) و مقاومت در برابر قطعی‌های موقت شبکه یا اختلال در مرورگر.

### 🚦 راه اندازی سریع

1. **نصب وابستگی‌های پایتون:** 
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. **نصب مرورگر مورد نیاز ربات:** `playwright install chromium`
3. **نصب وابستگی‌های رابط کاربری (Frontend):** `cd apps/web && npm install`
4. **اجرای سیستم:** `./scripts/start_system.sh`

---
*For extensive architecture and operational documentation, please refer to the `docs/` folder.*

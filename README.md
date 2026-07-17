<div align="center">
  <img src="https://img.shields.io/badge/Status-Production%20Ready-success?style=for-the-badge" alt="Status" />
  <img src="https://img.shields.io/badge/Version-1.0.1-blue?style=for-the-badge" alt="Version" />
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
* **Intelligent Captcha Solver:** ML-powered login math CAPTCHA, PyTorch fuel CAPTCHA, and Keras OCR fallback with automatic retry logic.
* **Self-Healing Navigation:** Dynamic element detection and "Loading Overlay" management for resilient web interactions.
* **Optimized Browser Context Management:** Enhanced cleanup of browser contexts and pages to prevent memory leaks and improve stability.

### 🛡️ Enterprise-Grade Resilience
* **Automatic Stuck Job Recovery:** Periodic cleanup of jobs stuck in `QUEUED` or `IN_PROGRESS` states.
* **Global Safety Net:** Integrated error handling that prevents processing deadlocks during unexpected browser crashes.
* **Session Persistence:** Intelligent session bundle storage to minimize redundant logins and reduce detection footprints.
* **Event Loop Stability:** Critical fix implemented in Celery workers to ensure stable asynchronous operations and prevent `RuntimeError: Event loop is already running` issues.
* **Streamlined Database Transactions:** Optimized database commit frequency to reduce load and improve performance under high concurrency.

---

## 🏗️ Technology Stack

| Layer       | Technology |
| ----------- | ---------- |
| **Backend** | [FastAPI](https://fastapi.tiangolo.com/) (Python 3.11) |
| **Frontend**| [Next.js 15](https://nextjs.org/) (TypeScript, Tailwind CSS) |
| **Database**| [PostgreSQL 16](https://www.postgresql.org/) (SQLModel/AsyncPG) |
| **Queue**   | [Celery](https://docs.celeryq.dev/) + [Redis](https://redis.io/) |
| **Automation**| [Playwright](https://playwright.dev/python/) |
| **Monitoring**| Custom RPA Inspector Event Bridge |

---

## 🚀 Quick Start

### Prerequisites
* Python 3.11+
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

**Important Security Note:** After enabling HTTPS for your Nginx setup, ensure you update `AUTH_COOKIE_SECURE=true` in your `.env` file for enhanced cookie security.

### 3. Running the System
The system is managed via a unified management script for easy operations:

```bash
# Start all services (Backend, Frontend, Workers, Redis, Postgres)
bash manage.sh start

# Check real-time service status and resources
bash manage.sh status
```

---

## 🛠️ Operational Commands

| Command | Description |
| :--- | :--- |
| `bash manage.sh start` | Full system bootstrap in the background. |
| `bash manage.sh stop` | Graceful shutdown of all components (retaining data). |
| `bash manage.sh status` | Show CPU, RAM, disk usage, and container status. |
| `bash manage.sh health` | Verify active database, Redis, API, and UI endpoints. |
| `bash manage.sh deploy` | Build backend/frontend images, run migrations, and restart services. |
| `bash manage.sh migrate` | Run Alembic migrations manually. |
| `bash manage.sh backup` | Quick Postgres database snapshot compression. |
| `pytest` | Run comprehensive integration & unit tests. |

---

# 🚀 سیستم اتوماسیون جامع بارنامه UTCMS (BarPro)

**BarPro** یک فریم‌ورک پیشرفته و صنعتی برای خودکارسازی فرآیندهای ثبت بارنامه در سامانه کشوری است. این سیستم با معماری مدرن و قابلیت اطمینان بالا، پایداری عملیات در مقیاس سازمانی را تضمین می‌کند و تمامی مراحل وقت‌گیر را برای شرکت‌های حمل و نقل کاملا اتوماتیک می‌سازد.

### 💎 ویژگی‌های برتر

*   **معماری چند مستاجره واقعی (Multi-tenant):** جداسازی کامل و امن داده‌های شرکت‌های مختلف.
*   **موتور رباتیک پیشرفته:** شبیه‌سازی فوق‌العاده دقیق رفتار انسانی (تایپ، حرکت موس، مکث‌ها) و حل خودکار کپچاهای پیچیده تصویری و ریاضی. مدیریت بهینه Context مرورگر برای جلوگیری از نشت حافظه.
*   **احراز هویت امن‌تر:** JWT در کوکی `httpOnly` نگهداری می‌شود و فرانت‌اند فقط اطلاعات غیرحساس کاربر را در localStorage ذخیره می‌کند. (با فعالسازی HTTPS، `AUTH_COOKIE_SECURE=true` را تنظیم کنید).
*   **سرعت بالا و بهینه‌سازی شده:** تزریق مستقیم موقعیت‌های جغرافیایی روی نقشه و حذف تاخیرهای استاتیک جهت تسریع بی‌نظیر صدور بارنامه. بهینه‌سازی مدیریت تراکنش‌های دیتابیس.
*   **تاب‌آوری هوشمند:** بازیابی خودکار عملیات متوقف شده (Self-Healing) و مقاومت در برابر قطعی‌های موقت شبکه یا اختلال در مرورگر. رفع مشکل تداخل Event Loop در Workerها.

### 🚦 راه اندازی سریع

1.  **نصب وابستگی‌های پایتون:** 
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```
2.  **نصب مرورگر مورد نیاز ربات:** `playwright install chromium`
3.  **نصب وابستگی‌های رابط کاربری (Frontend):** `cd apps/web && npm install`
4.  **اجرای سیستم:** 
    ```bash
    # راه‌اندازی کل سرویس‌ها با اسکریپت مدیریت
    bash manage.sh start
    ```

---
*For extensive architecture and operational documentation, please refer to the `docs/` folder.*

## Current Server Readiness Notes

- Frontend and backend Docker images build from a clean checkout; `.next/standalone` no longer needs to be uploaded manually.
- Current HTTP deployment must keep `AUTH_COOKIE_SECURE=false`; after enabling HTTPS, set `AUTH_COOKIE_SECURE=true`.
- Required runtime ML assets are `persian_number_ocr.keras`, `app/automation/captcha/assets/fuel_captcha_crnn.pth`, and `app/automation/captcha/assets/fuel_captcha_vocab.json`.
- Current Alembic head is `015_add_client_subscription_dates`.
- **Nginx HTTPS Enabled**: The Nginx configuration has been updated to enable HTTPS and redirect HTTP traffic. Ensure SSL certificates (`fullchain.pem` and `privkey.pem`) are properly configured in `/etc/nginx/ssl/` on your server.

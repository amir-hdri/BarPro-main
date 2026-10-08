# Deployment, configuration and resources

> Scope: BarPro only. Read this file when relevant to the task; do not auto-import
> the whole reference directory into global rules or the always-loaded core.
> **REFERENCE SNAPSHOT, NOT LIVE EVIDENCE.** Original claims and dates are preserved.
> Even headings such as “Current” and statuses such as “Fixed” reflect the source
> guide, not a fresh verification. Resolve drift against current code and contracts
> before acting; deployment state requires timestamped runtime evidence.

Read when: Deployment, infrastructure, environment configuration, Android hosting or resource work.

[Core guide](../../AGENTS.md) · [Reference index](README.md) · [Critical rules](../../CRITICAL_RULES.md)

Paths inside preserved text and command examples are relative to the repository
root, not this directory. Commands are examples, not automatic execution steps.

<!-- original-agents:0080-0118:start -->
## Server Specifications

### Server-side Android, Automated Shipping Lifecycle & Live Execution Status (2026-09-26)

- **Redroid & FakeTraveler Deployed**:
  - Container `barpro-redroid` is active on Central Server (`172.20.0.80:5555`, loopback `127.0.0.1:5555`) with `privileged: false`, `cap_add: [SYS_ADMIN, NET_ADMIN]`, binderfs nodes in `/dev/binderfs/`, and fstab persistence.
  - `cl.coders.faketraveler` and `com.baarnameshahri` installed. Mock location permission granted (`appops set cl.coders.faketraveler android:mock_location allow`).
  - Squid 1 proxy configured on Redroid (`172.20.0.1:3128`), verified egress IP `<CENTRAL_IP>`.
  - Android Bridge controller (`app/android_bridge/controller.py`) implemented and verified.
  - Official APK decompilation revealed React Native + Hermes v94 + custom `SecurityNativeModule` with root, emulator, and mock-location checks. Direct Mobile Transport in Python remains the primary resilient path.
- **Automated GPS Shipping Lifecycle & Periodic Beat Task (`shipping.auto_complete_due_trips`)**:
  - Waybill issuance automatically triggers start of shipping at origin coordinates via `/Document/RegisterStartOfShipping` (`POST`, `speed=0`, `altitude=1000`, `havePermission=true`), initializing `ShippingState` in Redis (`utcms:shipping:job:{job_id}`) and DB envelope `WaybillJob.result_json['_shipping_state']`.
  - New periodic shipping task `shipping.auto_complete_due_trips` runs in Celery Beat every 2 minutes (`crontab(minute="*/2")` / 120s schedule).
  - Evaluates in-transit trips against physical ETA requirements (minimum 20-minute buffer for short routes, ~65 km/h proportional velocity for long routes).
  - Terminal destination arrival registration is executed via `/Document/RegisterEndOfShipping` with a 2-point GPS trace (origin point with start timestamp + destination point with arrival timestamp).
  - Legacy endpoints `/Document/StartShippingWithGps` and `/Document/FinishShippingWithGps` return 404 on current UTCMS and automatically fall back to `RegisterStartOfShipping` and `RegisterEndOfShipping`.
  - Handled business rules: Rule 4006 (self-declared start non-fatal, retains `in_transit`) and Rule 4011 (self-declared end handling recorded as `mode="self_declared_auto_complete"` with `status="success"`).
- **Live Confirmed Waybills on UTCMS**:
  - Waybill 1 (Job 125): Doc `226157460`, Track `1349750688`, Driver 7 (`0321410408`), Plate `23ع965ایران78`, Taleqan Mir to Keshrud. Status on UTCMS: `درحال حمل` (code 1), DB: `SUCCESS`.
  - Waybill 2 (Job 127): Doc `226164459`, Track `1349757758`, Driver 8 (`4929889601`), Plate `32ع444ایران27`, Shot Dizaj to Mergan. Status on UTCMS: `درحال حمل` (code 1), DB: `SUCCESS`.
  - Waybill 3 (Job 140, 2026-09-28): Doc `228074398`, Track `1351676782`, Driver 6 (`0084575948`), Plate `27ع799ایران32`, Kashmar intra-city route. Status on UTCMS: `پایان حمل` (code 2), full end-of-shipping registered via `RegisterEndOfShipping` with auto-detour waypoint injection (Rule 4012 satisfied, `resultCode: 200`), DB: `SUCCESS` / `delivered`.

| Role | vCPU | RAM |
|------|------|-----|
| Central Server — UFW Firewall + Nginx (port 80), Backend, Frontend, Redroid, Squid 1 egress | 8 | 32 GB |
| Worker Nodes — Remote VPS with static Iranian IP + local Squid proxy | — | ~6 GB each |

Core platform containers run on the **central server**. In Model B, Workers 2/3 and
their local Squids run on remote VPS nodes and are not part of the central host's
resource budget.

### Resource Constraints & Implications (32 GB RAM / 8 vCPU Profile)
- **32 GB RAM** on central server — Workers 2/3 are on remote nodes (Model B), not counted in central budget
- Container limit allocation in Model B: **~20.0 GB** total (Postgres 4 GB, Celery Worker 1 4.5 GB with `shm_size: 1.5g`, Redroid 4 GB with `cpus: 2.0`, Backend API 1.5 GB with 4 Uvicorn workers, Redis 1.0 GB, Frontend 1.5 GB, Scheduler 1.0 GB, Beat 512 MB, Squid 256 MB, Monitoring 1.2 GB)
- **~12.0 GB headroom** reserved for Linux OS kernel, page cache, and I/O buffers (38% of host RAM)
- In All-in-One profile (Workers 2/3 local), container limits total **~27.5 GB**, preserving 4.5 GB OS headroom
- **8 vCPUs** eliminates CPU contention under load: dedicated 2 cores for Worker 1 (Playwright/OCR), 2 cores for Backend (4 Uvicorn workers), 2 cores for Redroid (Android 11), 1 core for Postgres, 1 core for Frontend/OS
- Disk: ensure <90% utilization

<!-- original-agents:0080-0118:end -->

<!-- original-agents:0173-0226:start -->
## Deployment Topology

> **Deployment target (Model B — scale-out):** the central server has a **single public IP**.
> Multi-IP egress is provided by **remote Worker VPSes**, each with its own
> static Iranian IP and a local Squid proxy. Postgres/Redis bind `0.0.0.0` on the central
> server (`POSTGRES_BIND`/`REDIS_BIND` in `.env`) and **must be protected** by UFW,
> provider firewall, and `DOCKER-USER`
> (`scripts/setup_firewall_central.sh`, `scripts/add_worker_firewall.sh`).
> Workers 2/3 run on the remote nodes via `compose/worker-node.yml`; on the central server
> they are disabled by default (compose profile `scale-out`).
> This is a configuration target; live IPs, listeners and firewall denial require runtime verification.

```
Central Server (single IP: <CENTRAL_IP>, 32 GB RAM, 8 vCPUs)
├── PostgreSQL (port 5432, bind 0.0.0.0, 4 GB limit, firewall target: workers only)
├── Redis (port 6379, bind 0.0.0.0, 1 GB limit, firewall target: workers only)
├── Redroid (Android 11, container IP 172.20.0.80, ADB 127.0.0.1:5555, 4 GB limit, 2 cpus)
├── Squid 1 (port 3128, egress via <CENTRAL_IP>)    ← Worker 1 (local)
├── FastAPI Backend (port 8000, 1.5 GB limit, 4 uvicorn workers, internal)
├── Celery Worker 1 → Squid 1 → UTCMS               ← 4.5 GB limit, shm_size 1.5g
├── Celery Beat (periodics scheduler, 512 MB limit)
├── Celery Scheduler → rpa_scheduler                 ← 1.0 GB limit, dedicated rpa_scheduler consumer
├── Next.js Frontend (port 3000, 1.5 GB limit, internal)
├── Nginx (port 80, public) → reverse proxy
└── Monitoring stack (Prometheus/Alertmanager/Grafana/exporters; internal or loopback only, 1.2 GB limit)

Remote Worker Nodes (each: 2 vCPU / ~6 GB / own static Iranian IP)
├── Squid (port 3128, egress via the Worker's own IP)   ← Workers 2/3
└── Celery Worker 2/3 → local Squid → UTCMS
    (via compose/worker-node.yml; DB/Redis at <CENTRAL_IP>)
```

### Squid Proxy Ports
| Proxy | Port | Egress IP | Used By | Topology |
|-------|------|-----------|---------|----------|
| Squid 1 | 3128 | <CENTRAL_IP> | Worker 1 | Both Model A & B |
| Squid 2 | 3129 | <CENTRAL_IP> (Model A) / N/A (Model B) | Worker 2 | Model A only (central) |
| Squid 3 | 3130 | <CENTRAL_IP> (Model A) / N/A (Model B) | Worker 3 | Model A only (central) |
| Remote Worker Squid | 3128 | Worker's own IP | Worker 2/3 | Model B only (remote nodes) |

> **Note:** In Model B, Squid 2 and 3 must not run on Central. They are guarded by
> the explicit `model-a` Compose profile; Workers 2/3 use their own remote Squid
> on port 3128. Confirm the live host has no unexpected Model A containers/listeners.

### Network Flow
- **Public entry**: port 80 (HTTP). Port 443 is only a disabled template until a
  certificate, active listener, redirect, TLS handshake, and secure cookie are verified.
- **Internal**: Docker bridge network `barpro_platform`
- **UTCMS egress**: via Squid proxies using different IPs (anti-bot bypass)
- **Inter-node security target**: UFW/provider firewall must restrict database
  (5432) and Redis (6379) to registered Worker IPs only; verify this at runtime
  because bind addresses and Compose files do not prove packet filtering
- **Squid 2/3 ports (3129, 3130)**: should be firewall-restricted to localhost only (`scripts/secure_squid_ports.sh`)
- **DNS resolution**: Nginx uses Docker internal DNS (127.0.0.11) with 30s cache for dynamic container IP resolution

<!-- original-agents:0173-0226:end -->

<!-- original-agents:0439-0483:start -->
## Deployment

```bash
bash manage.sh start        # Full system bootstrap (respects layer order)
bash manage.sh stop         # Graceful shutdown
bash manage.sh status       # CPU/RAM/disk/container status
bash manage.sh health       # Verify DB/Redis/API/Frontend health
bash manage.sh deploy       # Pull from GitHub and redeploy
bash manage.sh backup-db    # PostgreSQL snapshot
```

### Docker Compose Layers (in order)
```bash
docker compose -f compose/infra.yml up       # PostgreSQL + Redis only
docker compose -f compose/proxy.yml up       # Model B: Squid 1 only
docker compose -f compose/proxy.yml --profile model-a up  # Model A: Squid 1/2/3
docker compose -f compose/backend.yml up     # Backend + workers
docker compose -f compose/web.yml up         # Nginx + Frontend
docker compose -f compose/monitoring.yml up  # Full monitoring stack
```

## Environment Variables (`.env`)

**Critical**: `.env` must NEVER contain real production secrets. Use `.env.example` as template.

| Variable | Purpose |
|----------|---------|
| `API_KEY` | Backend API key authentication |
| `JWT_SECRET` | JWT signing key (min 32 chars) |
| `DRIVER_ENCRYPTION_KEY` | Fernet key for driver password encryption |
| `MASTER_ADMIN_PASSWORD` | Master admin login password |
| `POSTGRES_PASSWORD` | Database password |
| `REDIS_PASSWORD` | Redis password |
| `HEADLESS` | Browser headless mode (true/false) |
| `CAPTCHA_PROVIDER` | Solver: auto/composite/cnn/pytorch_fuel/keras_ocr/enhanced_ocr/local_ocr/off |
| `AUTH_COOKIE_SECURE` | Secure flag for httpOnly JWT cookie; false on HTTP, true after HTTPS |
| `CAPTCHA_MODE` | Validated mode: local_only / provider_only / provider_first / manual_only |
| `CAPTCHA_TIMEOUT_SECONDS` | Max time to solve captcha (default 120) |
| `CAPTCHA_MAX_RETRIES` | Max auto retries (default 2) |
| `KERAS_PYTHON_PATH` | Legacy compatibility setting; current Keras provider does not execute a subprocess |
| `KERAS_MODEL_PATH` | Keras .keras model file for fuel inquiry captchas |
| `CAPTCHA_LOCAL_FALLBACK_ENABLED` | Enable Tesseract/local OCR fallback |
| `AVAILABLE_IP_INDICES` | Comma-separated routing indices; topology-specific and filtered against fresh Worker Registry entries. The intended 3-worker Model B fleet uses `"1,2,3"`; smaller fleets must narrow it. |
| `RPA_PROXIES` | Comma-separated proxy URLs for workers (SSRF risk — see ISSUES.md) |

<!-- original-agents:0439-0483:end -->

<!-- original-agents:0753-0777:start -->
## Memory Budget (16 GB RAM — Central Server)

> **سرور مرکزی 16 GB RAM** — Workers 2/3 روی Remote Worker VPSها اجرا می‌شوند (Model B Scale-out)

| Container | Limit | Reservation | shm_size | تغییر |
|-----------|-------|-------------|----------|-------|
| PostgreSQL | **1.5 GB** | 768 MB | — | ↑ از 1 GB |
| Redis | **512 MB** | 256 MB | — | ↑ از 256 MB |
| Backend API | **512 MB** | 256 MB | 256 MB | ↑ از 256 MB |
| Celery Worker 1 | **3 GB** | 2.5 GB | 512 MB | ↑ از 2.5 GB |
| Celery Scheduler | **768 MB** | 384 MB | 128 MB | Dedicated rpa_scheduler consumer (FIX-A1) |
| Celery Beat | **256 MB** | 128 MB | — | ↑ از 128 MB (OOM fix) |
| Frontend (Next.js) | **1 GB** | 512 MB | — | ↑ از 512 MB |
| Nginx | **512 MB** | 256 MB | — | ↑ از 256 MB |
| Squid 1 (Model B Central) | 128 MB | 64 MB | — | Squid 2/3 are Model A only |
| Prometheus | 256 MB | 128 MB | — | — |
| Alertmanager | 128 MB | 64 MB | — | — |
| Grafana | 256 MB | 128 MB | — | — |
| Exporters ×4 | 64 MB each | 32 MB each | — | node/Redis/Postgres/Nginx |
| **Model B Central total limits** | **~9.0 GB** ← based on current Compose limits | | | |

> Workers 2/3 روی Remote Worker VPS اجرا می‌شوند و در بودجه سرور مرکزی نیستند.
> عدد بالا budget کد است، نه مصرف زنده؛ `docker stats` و host memory باید جداگانه
> بررسی شوند. Squid 2/3 فقط در استقرار تک‌سروره Model A وجود دارند.

<!-- original-agents:0753-0777:end -->

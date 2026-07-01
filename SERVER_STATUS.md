# BarPro Server Status & Diagnostics Report

This file provides a snapshot of the server status and connection diagnostics for future AI agents and developers.

## 📅 Report Information
* **Date of Check:** 2026-07-01 (1405-04-10)
* **Status:** 🟢 All Core Services Running & Healthy

---

## 🔗 Server & Network Metadata

| Parameter | Value / Status | Notes |
|---|---|---|
| **Primary IP** | `188.121.123.16` | Hosts Nginx, Backend, Frontend, Squid 1 |
| **Secondary IP** | `95.38.233.90` | Egress for Squid 2 and Squid 3 |
| **SSH (Port 22)** | 🟢 Accessible | Connection successful via `ubuntu` |
| **HTTP (Port 80)** | 🟡 Internal Only / Filtered | Nginx listens on 80. External requests timeout (likely blocked by provider firewall/security group). |

---

## 📊 System Resource Utilization

* **CPU Load:** Very Low (`uptime` load average: `0.42, 0.32, 0.28` on 4 vCPU)
* **RAM Usage:** ~2.2 GiB Used / 11 GiB Total (~7.7 GiB Free, 9.5 GiB Available)
* **Disk Space (Root `/`):** 58% Used (39 GiB Used, 29 GiB Available on 70 GiB total). Target is $<90\%$.

---

## 📦 Docker Container Status (13 / 13 Running)

All containers are up and healthy in the `barpro_platform` bridge network.

| Container Name | Image / Port | Status | Internal Health Check |
|---|---|---|---|
| `barpro-nginx` | `nginx:1.27.0-alpine` (80->80) | 🟢 Up (healthy) | `/healthz` -> HTTP 200 |
| `barpro-backend` | FastAPI App (8000/tcp) | 🟢 Up (healthy) | `/healthz` -> HTTP 200 |
| `barpro-frontend` | Next.js App (3000/tcp) | 🟢 Up (healthy) | Port 3000 accessible |
| `barpro-worker-1` | Celery Worker (8000/tcp) | 🟢 Up (healthy) | Running |
| `barpro-worker-2` | Celery Worker (8000/tcp) | 🟢 Up (healthy) | Running |
| `barpro-worker-3` | Celery Worker (8000/tcp) | 🟢 Up (healthy) | Running |
| `barpro-beat` | Celery Beat (8000/tcp) | 🟢 Up (healthy) | Running |
| `barpro-postgres` | PostgreSQL 16 (5432/tcp) | 🟢 Up (healthy) | Running |
| `barpro-redis` | Redis 7 (6379/tcp) | 🟢 Up (healthy) | Running |
| `barpro-squid-1` | Squid Proxy | 🟢 Up (healthy) | Egress via `188.121.123.16` |
| `barpro-squid-2` | Squid Proxy | 🟢 Up (healthy) | Egress via `95.38.233.90` |
| `barpro-squid-3` | Squid Proxy | 🟢 Up (healthy) | Egress via `95.38.233.90` |
| `barpro-prometheus` | Prometheus (9090/tcp) | 🟢 Up (healthy) | Running (internal port) |

---

## 🛡️ Firewall & Proxy Diagnostics

### 1. iptables rules for Squid Ports
Squid ports 3128, 3129, and 3130 are restricted to localhost and the Docker bridge subnet (`172.17.0.0/16`) to prevent unauthorized external access.
* **UFW:** Inactive
* **iptables Squid Rules:** Applied and blocking public access.

### 2. Squid Proxy Routing & Target Reachability (UTCMS)
Each proxy routes traffic via the correct egress IP, and all have verified connection to `https://barname.utcms.ir/`:

* **Squid 1 (Port 3128):** 
  * Egress IP: `188.121.123.16`
  * UTCMS connection: 🟢 Success (`HTTP/1.1 200 Connection established`)
* **Squid 2 (Port 3129):** 
  * Egress IP: `95.38.233.90`
  * UTCMS connection: 🟢 Success (`HTTP/1.1 200 Connection established`)
* **Squid 3 (Port 3130):** 
  * Egress IP: `95.38.233.90`
  * UTCMS connection: 🟢 Success (`HTTP/1.1 200 Connection established`)
* **Direct Connection (No Proxy):** 
  * Egress IP: `95.38.233.90`
  * UTCMS connection: 🟢 Success (`HTTP/1.1 200 OK`)

---

## 📝 Key Notes for the Next AI Agent

1. **Architecture & Routing:** Both `188.121.123.16` and `95.38.233.90` point to the same physical host (dual networking setup). Egress routing is critical for avoiding target rate limits and bot-blocking on `barname.utcms.ir`.
2. **Ports Exposure:** Only Nginx binds to Port 80 public interface. If external HTTP/HTTPS curl requests fail, ensure you are testing through VPN or check security groups in the cloud provider panel. SSH remains open on Port 22.
3. **Database & Redis:** Database is accessible by the application using ORM and asyncpg pool. Migrations are managed via Alembic and run on startup using a distributed Redis lock.

# Known pitfalls and CAPTCHA chain

> Scope: BarPro only. Read this file when relevant to the task; do not auto-import
> the whole reference directory into global rules or the always-loaded core.
> **REFERENCE SNAPSHOT, NOT LIVE EVIDENCE.** Original claims and dates are preserved.
> Even headings such as “Current” and statuses such as “Fixed” reflect the source
> guide, not a fresh verification. Resolve drift against current code and contracts
> before acting; deployment state requires timestamped runtime evidence.

Read when: Related debugging, dependency compatibility or CAPTCHA work.

[Core guide](../../AGENTS.md) · [Reference index](README.md) · [Critical rules](../../CRITICAL_RULES.md)

Paths inside preserved text and command examples are relative to the repository
root, not this directory. Commands are examples, not automatic execution steps.

<!-- original-agents:0355-0374:start -->
## Common Pitfalls

| Pitfall | Details | Status |
|---------|---------|--------|
| `except: pass` | Used extensively (~55+ locations); never catch silently — log at minimum | ✅ Fixed |
| `engine.dispose()` per Celery task | Destroys connection pool, causing connection storms | ✅ Fixed |
| `asyncio.Lock` on class instances | Race condition when event loop changes; use `threading.Lock` for init | ✅ Fixed |
| `autoretry_for = (Exception,)` | Retries programming bugs indefinitely; use specific exceptions | ✅ Fixed |
| Migration startup | `run_migrations()` is active with a PostgreSQL session-level advisory lock; avoid raw Alembic startup runners | ✅ Fixed |
| Event loop per Celery task | `asyncio.new_event_loop()` per task is extremely expensive | ✅ Fixed |
| Session not injected | Services create `AsyncSession` directly instead of using `get_session()` dependency | ✅ Fixed |
| Race condition in Redis manager | Double-checked locking pattern is broken for async (redis.py:36-53) | ✅ Fixed |
| Zod v3 ↔ v4 mismatch | Keep imports from `zod`, not `zod/v4`, because package is `zod@3.24.1` | ✅ Fixed |
| Heroicons rename | Use current Heroicons v2 names such as `ArrowRightStartOnRectangleIcon` | ✅ Fixed |
| Hardcoded secrets in workflows | CI/CD workflows had fallback hardcoded credentials | ✅ Fixed |
| Missing security headers | Backend responses lacked security headers | ✅ Fixed |
| Missing Redis connection pool settings | No timeout/retry configuration | ✅ Fixed |
| Docker Compose V1 (`docker-compose`) usage | CI/CD and deploy scripts must use `docker compose` V2 — root `docker-compose.yml` uses `include:` (Compose >= 2.20) which V1 does not support | ✅ Fixed (.github/workflows/cd-deploy.yml) |
| Multi-IP proxy routing — topology mismatch | `AVAILABLE_IP_INDICES` is topology-specific and must match fresh Worker Registry entries. The intended 3-worker Model B fleet uses indices `1,2,3`; smaller deployments must narrow the set. | ✅ Runtime filtering prevents unregistered indices, but effective values still require deployment verification |

<!-- original-agents:0355-0374:end -->

<!-- original-agents:0484-0494:start -->
## CAPTCHA Model Chain

| Page | Solver | Model | Provider Name |
|------|--------|-------|---------------|
| **Login** (math: "2+3") | PyTorch CNN | `app/automation/captcha/assets/captcha_cnn.pth` | `cnn` |
| **Fuel Inquiry** (Persian words) | PyTorch CRNN | `app/automation/captcha/assets/fuel_captcha_crnn.pth` + vocab | `pytorch_fuel` |
| **Fuel Inquiry fallback** | Keras OCR | `persian_number_ocr.keras` (project root) | `keras_ocr` |

Default `CAPTCHA_PROVIDER=auto` tries CNN → PyTorch fuel → Keras → Enhanced → Local in sequence.
All current providers execute within the Worker process; Keras is lazy-loaded once and reused.

<!-- original-agents:0484-0494:end -->

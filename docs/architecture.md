# BarPro System Architecture Overview

This document is a compact companion to
[ARCHITECTURE.md](../ARCHITECTURE.md). It describes the current code contract,
not proof of live firewall, container, queue, or TLS state. Any item without
direct server evidence requires runtime verification.

## High-Level Diagram

    Browser / Mobile PWA
       | HTTP and WebSocket; port 80
       v
    Nginx
       |-- Next.js :3000
       |-- FastAPI :8000
              |-- PostgreSQL 16
              |-- Redis 7: cache, Celery, pub/sub, locks
              |-- WS /ws/waybill
       |
       |-- Central Worker 1, concurrency 1 -> Squid 1 :3128
       |-- Beat -> publishes periodic tasks
       |-- celery_scheduler -> consumes only rpa_scheduler
       |
       |-- Remote Worker 2, concurrency 1 -> local Squid :3128
       |-- Remote Worker 3, concurrency 1 -> local Squid :3128

    Monitoring: Prometheus + Alertmanager + Grafana
                + node/Redis/Postgres/Nginx exporters

Production uses Model B: Worker/Squid 2 and 3 run on remote VPS nodes. Central
copies of those services belong to the explicit Model A profile and must not run
on a Model B Central host.

## Gateway and API

- Nginx currently listens on port 80. HTTPS/443 is a disabled template until
  certificate, listener, redirect, external handshake, and cookie behavior are
  verified.
- FastAPI exposes health at GET /healthz, sanitized readiness at GET /readyz,
  detailed admin readiness at GET /api/v1/admin/readyz, tenant APIs under
  /api/v1, and authenticated realtime updates at WS /ws/waybill.
- Clean IP management is admin-only under /api/system/clean-ips and its refresh
  subpath.
- Multi-route: `/api/v1/route-templates` (saved routes), `/api/v1/batches`
  (batch expansion + progress, idempotent via `X-Idempotency-Key`), and
  `POST /api/v1/locations/distance` (road distance/time).
- /api/system/health, /ws/jobs/{client_id}, and /ws/admin/stream are not current
  contracts.
- DELETE /api/v1/waybill-jobs/{job_id} is permanent deletion; it is not a POST
  cancel endpoint.

## Waybill Flow

    create and validate
      -> pending / waiting_auth / waiting_submission_window
      -> DispatchIntent
      -> queued -> claimed -> running
      -> at-most-once UTCMS mutation
      -> unknown -> reconciling
      -> success | needs_review

A browser success message is not final. Success requires:

1. a non-empty tracking code in the RPA result;
2. the same code persisted in waybill_jobs.result_json;
3. a matching record in UTCMS History/Search.

The state guard also requires mutation_status=confirmed and reconciled_at.
Unconfirmed results are never automatically resubmitted after the bounded
reconciliation window.

## Queues

- Worker 1 consumes base queues plus queue suffix 1 and barpro.fuel.inquiry.
- Remote Workers consume the corresponding suffix 2 or 3 queues and the fuel
  queue.
- celery_scheduler consumes only rpa_scheduler.
- Beat publishes periodic tasks; it is not a consumer.
- Active bindings, backlog, concurrency, and Worker Registry indices must be
  checked on the live deployment.

## CAPTCHA, Login, and OTP

- CAPTCHA auto order is CNN -> Fuel CRNN -> Keras -> Enhanced -> Local.
- Keras is lazy-loaded and reused in-process; KERAS_PYTHON_PATH does not select
  a subprocess in the current solver.
- Login may use curl_cffi HTTP authentication, session transfer, and a limited
  document/xhr/fetch bridge before Playwright fallback.
- 17:30-08:00 (config default) is a configurable OTP_REQUIRED prediction, not an official UTCMS
  window. Only a current OTP_FREE observation permits submission.

## Data Model

SQLModel primary keys are integer IDs. Public job_id, batch_id, intent_id, and
execution_id values are strings. Core operational models include:

- Client, Driver, DriverPlate, DriverSchedule, WaybillJob, FuelInquiry;
- UploadBatch, DispatchIntent, Execution, WorkerRegistry;
- WaybillRouteTemplate (saved route + distance/duration) and WaybillBatch (multi-route batch);
- ProxyEndpoint and UTCMSSystemObservation.

WaybillJob stores payload_json, result_json, retry, mutation, and reconciliation
fields, plus multi-route linkage (batch_id, route_template_id, sequence_index,
distance_km, duration_min). FuelInquiry stores quota JSON and a screenshot URL/Data URI and has no
direct tracking-code column.

## Security and Monitoring Boundaries

- PostgreSQL/Redis may bind to all interfaces for remote Workers, but UFW,
  provider firewall, and DOCKER-USER must restrict them to registered Worker
  IPs. This requires an external denial probe after deployment.
- Rate limiting is a Redis sliding window, not Token Bucket. Code rules are
  public=60, auth=5, waybill=30, driver=60, tenant=100, and admin=200 per minute.
- Prometheus, Alertmanager, and exporters are internal-only; Grafana binds to
  loopback. Compose presence does not prove healthy targets or alert delivery.

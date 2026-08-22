# Operations Deployment Checklist

The canonical production procedure is
[../../DEPLOYMENT_GUIDE.md](../../DEPLOYMENT_GUIDE.md). This file records the
short operations checklist and must not diverge from that guide.

## Deployment Contract

- Production defaults to Model B with BARPRO_TOPOLOGY=model-b.
- Central runs Worker 1 and Squid 1. Worker/Squid 2 and 3 run on their remote
  VPS nodes; Central Model A services require explicit opt-in.
- Nginx currently serves HTTP on port 80. The commented TLS template is not
  operational HTTPS.
- AUTH_COOKIE_SECURE=false remains required until certificate, listener,
  redirect, external handshake, login, logout, and WebSocket tests all pass.
- Keras CAPTCHA inference is lazy-loaded in-process. KERAS_PYTHON_PATH does
  not select a subprocess in the current solver.
- Alembic head expected by this checkout is
  038_add_multiroute_batch_distance.

## Start or Update

    cd /opt/barpro
    BARPRO_TOPOLOGY=model-b bash manage.sh start

    # Existing installation
    git pull
    BARPRO_TOPOLOGY=model-b bash manage.sh deploy

Do not pass production passwords on the command line or store them in this
repository.

## Required Runtime Verification

After deployment, record evidence for:

1. Git SHA and Alembic head on Central and both Workers.
2. Full container inventory, including detection of unexpected containers.
3. No Central squid_2, squid_3, celery_worker_2, or celery_worker_3 in Model B.
4. Worker Registry heartbeats/IP indices and Celery active queues.
5. Worker concurrency of one and celery_scheduler consuming only rpa_scheduler.
6. Actual egress IP through each Worker-local Squid.
7. PostgreSQL/Redis/Squid denial from a non-worker source IP.
8. Sanitized public /readyz; detailed /api/v1/admin/readyz only with admin authentication.
9. Admin-only /api/system/clean-ips and refresh route.
10. Prometheus targets, Alertmanager, Grafana, and node/Redis/Postgres/Nginx exporters.
11. Reconciliation backlog and successful jobs carrying all three UTCMS witnesses.

Any item without direct evidence is requires runtime verification; Compose
configuration or .env.example is not sufficient.

## Monitoring Inventory

compose/monitoring.yml defines Prometheus, Alertmanager, Grafana,
node-exporter, redis-exporter, postgres-exporter, and nginx-exporter.
Prometheus/Alertmanager/exporters are internal-only and Grafana binds to
loopback. A healthy Compose render does not prove that targets scrape or alerts
are delivered.

## Safe Result Interpretation

Waybill success follows:

    running -> unknown -> reconciling -> success | needs_review

Do not treat a browser success message as final. Success requires a tracking
code from RPA, the same value persisted in result_json, and a matching UTCMS
History/Search record.

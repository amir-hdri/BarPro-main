# Phase 1: server-diagnostics-and-failure-root-cause-audit — Context

## Locked decisions

1. Direct Mobile API Transport (`UtcmsMobileClient`) is the sole live issuance mechanism; Playwright form filling is retired.
2. Two-Witness proof is mandatory for any confirmed waybill registration claim.
3. Iranian Egress IP is required for all UTCMS operations.
4. Purposeful and scheduled driver login architecture to prevent account lockout.

## Approaches considered

### A — Live container log audit and root-cause remediation
Inspect real-time container logs on the central server (`barpro-scheduler`, `barpro-worker-1`, `barpro-beat`, `barpro-backend`), pinpoint exact error messages and crash stacks, resolve them at source and database, and verify container health.
What it buys: Exact root cause identification, eliminates active crashes/warnings, real-time proof.
What it costs: Requires direct SSH server access and container log inspection.

### B — Static code review and synthetic probes without container audit
Review code repositories locally without live container log correlation.
What it buys: Faster, no server execution required.
What it costs: Misses production-specific crashes such as orphan job loops, sinkhole IPs, and queue task drops.

chosen: A — because live logs reveal real-time production issues (orphaned scheduler jobs, geometry crashes, proxy sinkholes, celery expires).

---
issues: [93, 94]
---
# Phase 1: server-diagnostics-and-failure-root-cause-audit — Plan

## Tasks

- [ ] Audit server logs across backend, scheduler, beat, and worker containers to identify waybill registration defects and determine root causes. `verify: ssh root@87.107.160.251 "docker logs --tail 30 barpro-scheduler && docker logs --tail 30 barpro-worker-1"`
- [ ] Diagnose and remediate session drops, WAF rejections, and OTP reception defects. `verify: uv run pytest tests/test_login_attempt_ledger.py`

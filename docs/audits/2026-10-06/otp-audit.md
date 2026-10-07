# OTP reliability audit — 2026-10-06

Scope: checkout `6c5564e`, recent `HEAD~20..HEAD`, with particular attention to `e664e54`, `47b909c`, `858b689`, and `6c5564e`. Read-only review of application code; the only new files are audit artifacts. Production, live UTCMS, and actual delivery behavior were not contacted or verified.

Applied skills: `.agents/skills/barpro-rpa-ops/SKILL.md`, `.agents/skills/celery-ops/SKILL.md`, `.agents/skills/barpro-waybill-submission-safety/SKILL.md`. Read canonical `docs/BARPRO_KNOWLEDGE_GRAPH.md` first, followed by `CRITICAL_RULES.md` and `docs/UTCMS_CONSTRAINTS.md`.

Reproduce with:

```sh
.venv/bin/python docs/audits/2026-10-06/otp-reproductions.py
```

Latest execution exited **0**, confirming **11 defect scenarios**. `otp-reproductions.log` contains individual results. Assertions deliberately assert the existing defective behavior; this is an audit reproduction suite, not passing acceptance tests for the intended behavior. Redis uses a fresh, isolated Unix socket, port zero, no persistence; UTCMS client, credentials and DB session boundaries are synthetic/mocked. The network skill's offline audit also exited zero (`/tmp/barpro-otp-network-audit.json`: `status=passed`, `violations=[]`). Broad project gates belong to the parent audit.

## OTP-01 — P1: already-issued jobs can reach IssueDocumentByOtp again

References: `app/services/waybill_job_service.py:582–590`, `644–660`, `738–742`; `app/services/otp_wakeup_consumer.py:270–289`; the normal writer in `app/workers/waybill_worker.py:1700–1730`.

The new guard only recognizes `status == success`. The regular worker intentionally persists a received tracking code as `unknown` with `confirmation_status=tracking_received` until batch reconciliation. Such a job already satisfies the no-resubmit evidence boundary, but a delayed OTP stream event or manual submission reaches the issuance POST again. This is separate from the documented exception allowing the mobile OTP path to mark success before History.

Additionally, the job is read before acquiring the lease and is only refreshed when acquisition fails. A contender can read the old UNKNOWN job, pause, acquire after the first request has committed success and released the lease, then issue from its stale ORM instance. The lock does not fix this sequential race.

Verified results:

- `persisted_tracking_does_not_prevent_reissue`: input UNKNOWN already contains tracking `99100001`; actual issue call count **1**, instead of zero.
- `stale_prelease_job_allows_repeat_mutation`: two requests for document `991` both call issue and both return success. Separate session identity maps are modeled, network calls are mocked.

Required change: under an owned claim, refresh/re-read the durable job and reject any persisted tracking code irrespective of status; use a durable issuance fence so a successful or ambiguous POST cannot be repeated after a crash. Tests need the regular worker's UNKNOWN/tracking_received shape, not just SUCCESS.

## OTP-02 — P1: lease expiration permits overlap and stale owners can delete a new lease

References: `app/automation/otp_keys.py:85–114`; `app/services/waybill_job_service.py:649`, `679–741`, `823–909`; `app/automation/waybill_bot_multitenant.py:948–988`.

All owners write the constant `"1"`, lease TTL is 30 seconds, no renewal occurs, and release is an unconditional DEL. The protected section includes login, issuance, shipping initialization/start and database writes. There is no upper bound keeping the full section below the lease duration. If A runs longer than the TTL, B acquires; A's eventual release then deletes B's lock, allowing C to enter while B is still running.

Verified with real Redis and the same public lease APIs: A acquires with a shortened one-second test TTL, time passes, B acquires, A releases, C acquires while B remains active. All three acquisitions return true. Shortening the configurable duration does not alter the ownership logic.

Required change: random owner token, atomic compare-and-delete release, controlled renewal/expiry fencing, and durable idempotency from OTP-01. A longer constant TTL alone does not repair ownership.

## OTP-03 — P1: durable stream does not actually guarantee retry/restart delivery

References: `app/services/otp_wakeup_consumer.py:304–309`, `323–356`.

Three separately reproduced failure modes share the incomplete delivery protocol:

1. Initial `XGROUP CREATE ... $` starts after existing events. An OTP already durably appended before the first sweep is skipped. Real Redis result: stream length 1, processed 0, callback calls 0.
2. `XREADGROUP ... >` only reads never-delivered events. There is no read of pending IDs or XAUTOCLAIM. After a consumer obtains an event then crashes, the restart leaves it pending forever. Real Redis result: pending 1, processed 0, callback calls 0.
3. The resolver catches failures and returns `{success: false}`, while the sweep ignores that return and XACKs anyway. A synthetic transient HTTP 503 from the actual resolver path produces processed 1, pending 0, next sweep 0. A missing target similarly returns None and is acknowledged.

Immediate background tasks are not durable and therefore do not repair these cases if the process restarts or the first attempt fails. The five-second Beat sweep does not reclaim or retry the lost work.

Required change: initialize groups to include backlog, recover pending entries after a bounded idle interval, classify terminal versus retryable completion outcomes and only ACK when durably resolved or explicitly dead-lettered. Preserve ambiguity fencing: a retryable delivery is not permission to repeat an uncertain UTCMS mutation.

## OTP-04 — P2: queued OTP codes are executed after their expiry

References: `app/services/otp_delivery.py:90–97`; `app/services/otp_wakeup_consumer.py:342–352`; `app/services/waybill_job_service.py:647–648`.

Intake attaches `expires_at`, but the stream consumer extracts only phone/code/job_id. Redis Stream entries do not inherit the TTL of the separate phone key. After a scheduler delay or backlog, an expired event still calls the resolver; submit_otp rewrites its code into a fresh 300-second job key with current received_at. Phone-only events are resolved against the current pending job, not the original challenge.

Verified: an event whose expiry is one hour in the past still causes one resolver dispatch and is counted as processed. This confirms an expiry-contract breach and potential stale-code issuance attempts; no claim is made that UTCMS accepts the expired code.

Required change: validate expiry and challenge/job association on consumption and before issuance, preserve original timestamps, and never refresh an expired code as a side effect of replay. Cross-tenant and webhook replay vulnerabilities are reviewed separately by the security audit.

## OTP-05 — P1: a pending job can be mutated before discovering its state transition is illegal

References: candidate inclusion at `app/services/otp_wakeup_consumer.py:213–220`; `app/services/waybill_job_service.py:738–765`, `778–796`; `app/orchestrator/state_machine.py:29–39`.

The resolver explicitly includes pending jobs. submit_otp validates no permitted source-state set before issuing. After a valid upstream tracking response, it handles unknown/needs_review and waiting_retry/retrying specially, but pending falls through to the illegal `pending -> success` transition. The external side effect has already happened while database commit has not.

Verified: synthetic PENDING job containing a document ID invokes issue once; the response yields `StateTransitionError: 'pending' → 'success' not allowed`; DB commit count is zero. This creates an unrecorded upstream result and makes the next invocation capable of repeating the mutation.

Required change: validate pending-challenge eligibility and legal transition before any POST; record issued/ambiguous outcomes durably even if a downstream update fails. Do not broaden transitions indiscriminately; cancelled/terminal jobs also require explicit eligibility handling.

## OTP-06 — P2: auto-completion ignores the assigned worker's egress

References: `app/services/otp_wakeup_consumer.py:44–52`, `284–289`; `app/services/waybill_job_service.py:665–674`; `app/automation/worker_proxy.py:235–237`, `279–282`; `app/workers/celery_app.py:219–224`; `app/workers/tasks.py:390–395`; `compose/backend.yml:278–310`.

The webhook runs issuance directly in an API background task; the fallback runs it synchronously inside the dedicated control scheduler. `get_worker_proxy_url()` selects the current process's WORKER_ID and does not inspect the job's worker_id or the original document-session egress. In the scheduler WORKER_ID is literally `scheduler`. Cached pending sessions also do not preserve a proxy binding (`waybill_bot_multitenant.py:879–887`).

Verified using actual proxy selection with DNS/socket probes mocked: a job assigned to worker 2, with worker-2 proxy `192.0.2.20`, is completed using the scheduler's generic proxy `192.0.2.10`. If that generic proxy and clean pool are absent, selection fails instead of routing to worker 2. The logged IPs are reserved documentation addresses, not production endpoints.

Implication: the per-worker/IP contract is not enforced for OTP completion; the single-concurrency scheduler also performs issuance/login/start-shipping while its control queue waits. Live rejection, actual production proxy values, and latency remain unverified.

Required change: enqueue a scoped completion command on the assigned worker's queue and reuse that execution's authenticated egress context. Keep stream routing/ACK work bounded on the control scheduler.

## OTP-07 — P2: an all-stale pending set remains permanently ambiguous

References: `app/services/otp_wakeup_consumer.py:71–85`, `87–114`.

Stale entries are collected, but SREM is performed only when at least one valid live job exists. With two or more stale IDs and no pending_doc records, the final branch counts the original set, returns AMBIGUOUS and skips DB fallback. The set has no TTL. This defeats the stale-pruning fix for its all-expired case, so phone-less forwarders can keep receiving ambiguity errors even with no real pending challenge.

Verified on real Redis: two stale IDs without pending_doc yield `AMBIGUOUS`, and both IDs remain in the set.

Required change: remove stale IDs before all cardinality decisions, then base ambiguity only on validated live candidates; test zero, one and multiple valid entries mixed with stale entries.

## Conditional defensive gap, not an ordinary network-outage finding

`WaybillJobService.submit_otp` skips lease acquisition and proceeds when redis_manager.get() is None (`644–660`). The reproduction confirms one mock issue call and success with no Redis client. However, the real manager returns None only when aioredis is unavailable (`app/core/redis.py:200–202`); a normal network outage returns a lazy client and its first SET raises. Therefore this is a dependency-disabled fail-open gap, not proof that standard Redis connection outages permit submissions. Treat as P3 hardening unless a production path returning None is demonstrated.

## Why current OTP tests miss the stream and lease defects

`tests/test_otp_wakeup_and_lifecycle.py:48–52` ignores `ex` expiry; `123–137` models XREADGROUP by removing list entries, makes XGROUP CREATE a no-op, and makes XACK unconditional. Those doubles do not model group offsets or Redis's pending entries list. `test_lease_locking_prevents_concurrent_issue` only exercises immediate acquire/release, not expiry or distinct owner identity. Passing those tests does not validate restart recovery or lease fencing.

## Exclusions and verification limits

- `docs/BARPRO_KNOWLEDGE_GRAPH.md` explicitly documents the mobile OTP exception to History-before-success, accepted on 2026-10-02. This audit does not label that exception alone a new bug.
- Network/proxy API calls were mocked in reproductions; real Redis command semantics were used for stream and lease behavior. No external mutation was made.
- The duplicate-call reproduction proves application invocation, not that UTCMS creates two distinct documents. UTCMS may reject a repeat; that does not restore the application's exactly-once invocation contract.
- No app-code fixes, deployment, broad test claim, or current production-state claim is included here.

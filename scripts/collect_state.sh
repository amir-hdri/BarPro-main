#!/usr/bin/env bash
# Read-only state collector for BarPro's three servers.
#
# WHY: verification of the deploy fixes needs a faithful snapshot of the live
# platform, but the analysis session has no network access. This script gathers
# everything sections 1-3 of the review need in one pass, mutates nothing, and
# never fails the whole run because one probe failed.
#
# Usage — run on EACH server:
#   cd /opt/barpro && bash scripts/collect_state.sh 2>&1 | tee /tmp/barpro-state-$(hostname).txt
#
# Then send the resulting file back. Contains no passwords; review before sharing.

# Deliberately NOT `set -e`: a failing probe is itself a finding, and aborting
# here would hide every later section.
set -uo pipefail

UTCMS_HOST="${UTCMS_HOST:-barname.utcms.ir}"

sec() { printf '\n\n===== %s =====\n' "$*"; }
run() { printf '\n$ %s\n' "$*"; eval "$@" 2>&1 | head -80; }

sec "IDENTITY"
run 'hostname'
run 'date -u "+%Y-%m-%dT%H:%M:%SZ (UTC)"'
run 'uptime -p'
run 'uname -sr'

sec "1-A / 2-A  CONTAINERS + RESTART COUNTS"
run 'docker ps -a --format "{{.Names}}\t{{.Status}}\t{{.Ports}}"'
run 'docker ps -aq | wc -l'
for c in barpro-backend barpro-nginx barpro-frontend barpro-prometheus \
         barpro-postgres barpro-redis barpro-beat; do
  run "docker inspect -f '$c restarts={{.RestartCount}} running={{.State.Running}} exit={{.State.ExitCode}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' $c"
done

sec "1-B  GIT DIVERGENCE FROM ORIGIN/MAIN"
run 'git -C /opt/barpro status --short'
run 'git -C /opt/barpro rev-parse --short HEAD'
run 'git -C /opt/barpro log --oneline -15'
run 'git -C /opt/barpro log --oneline origin/main..HEAD'
run 'git -C /opt/barpro log --oneline HEAD..origin/main'
run 'git -C /opt/barpro stash list'
# Any real server-side edits must be salvaged before any reset.
run 'git -C /opt/barpro diff --stat'
run 'git -C /opt/barpro diff'

sec "1-C  PORT 8000 MUST NOT BE PUBLISHED"
run 'ss -tulnp | grep -E ":8000|:5432|:6379|:3128|:3129|:3130" || echo "(no matches)"'
run 'curl -sS -o /dev/null -w "localhost/healthz -> %{http_code}\n" --max-time 15 http://localhost/healthz'
run 'curl -sS --max-time 15 http://localhost/healthz'

sec "1-D  REAL HEALTH CHECK"
run 'bash /opt/barpro/manage.sh health; echo "manage.sh health exit=$?"'

sec "2-B  IS APP CODE BIND-MOUNTED OR BAKED INTO THE IMAGE?"
run 'docker exec barpro-backend sh -c "ls -la /app/app | head -5"'
run 'docker exec barpro-backend sh -c "mount | grep -E \"/app\" || echo (no /app mounts)"'
run 'docker inspect -f "{{range .Mounts}}{{.Type}} {{.Source}} -> {{.Destination}} ro={{.RO}}{{println}}{{end}}" barpro-backend'
run 'docker inspect -f "{{.Config.Image}} {{.Image}}" barpro-backend'

sec "3-A  FIREWALL"
run 'ufw status verbose'
run 'iptables -S 2>/dev/null | head -40'

sec "3-B  MIGRATIONS"
run 'docker exec barpro-backend alembic current'
run 'docker exec barpro-backend alembic heads'
run 'docker exec barpro-backend sh -c "alembic history | wc -l"'
run 'docker exec barpro-postgres psql -U postgres -d barpro -c "\di" 2>/dev/null | head -60'

sec "3-C  WORKER REGISTRY / QUEUES / EGRESS"
run 'docker exec barpro-postgres psql -U postgres -d barpro -c "select worker_id, ip_index, status, last_heartbeat_at, now() - last_heartbeat_at as age from worker_registry order by ip_index;" 2>/dev/null'
run 'docker exec barpro-redis redis-cli keys "utcms:circuit_breaker:blocked:*"'
run 'docker exec barpro-redis redis-cli --scan --pattern "*waybill*" | head -20'
for q in waybill_tasks_1 waybill_tasks_2 waybill_tasks_3 rpa_auth rpa_submit rpa_scheduler; do
  run "docker exec barpro-redis redis-cli llen $q"
done
run 'echo "WORKER_IP_INDEX=$(docker exec barpro-backend printenv WORKER_IP_INDEX 2>/dev/null || echo UNSET)"'
run 'echo "AVAILABLE_IP_INDICES=$(docker exec barpro-backend printenv AVAILABLE_IP_INDICES 2>/dev/null || echo UNSET)"'

sec "EGRESS -> UTCMS  (the current outage question)"
run "getent hosts $UTCMS_HOST || echo '(getent failed)'"
run "dig +short $UTCMS_HOST @1.1.1.1"
run "dig +short $UTCMS_HOST @8.8.8.8"
# Probe BOTH schemes: hitting an http-only service over https surfaces as a TLS
# handshake abort, which is indistinguishable from a real TLS failure in logs.
for scheme in http https; do
  run "curl -sS -o /dev/null -w '$scheme direct: code=%{http_code} conn=%{time_connect} tls=%{time_appconnect} total=%{time_total}\n' --max-time 25 $scheme://$UTCMS_HOST/"
done
run "curl -sSI --max-time 25 http://$UTCMS_HOST/ | head -15"
run "echo | timeout 15 openssl s_client -connect $UTCMS_HOST:443 -servername $UTCMS_HOST | head -15"
run "nc -vz $UTCMS_HOST 80"
run "nc -vz $UTCMS_HOST 443"
for p in 3128 3129 3130; do
  for scheme in http https; do
    run "curl -sS -o /dev/null -w 'proxy$p $scheme: code=%{http_code} total=%{time_total}\n' --max-time 25 -x http://127.0.0.1:$p $scheme://$UTCMS_HOST/"
  done
done
run "curl -sS --max-time 20 https://api.ipify.org; echo '  <- egress IP (direct)'"
for p in 3128 3129 3130; do
  run "curl -sS --max-time 20 -x http://127.0.0.1:$p https://api.ipify.org; echo \"  <- egress IP via $p\""
done
# Intermittent vs hard block: 10 samples is what distinguishes them.
sec "IS IT INTERMITTENT? (10 samples per scheme, ~60s)"
for scheme in http https; do
  run "for n in 1 2 3 4 5 6 7 8 9 10; do curl -sS -o /dev/null -w '$scheme %{http_code} %{time_total}\n' --max-time 20 $scheme://$UTCMS_HOST/ || echo '$scheme curl-failed'; sleep 3; done"
done

sec "RECENT ERRORS (24h)"
run 'docker logs --since 24h barpro-backend 2>&1 | grep -icE "error|exception|traceback" || echo 0'
run 'docker logs --since 24h barpro-backend 2>&1 | grep -iE "ERR_CONNECTION|TLS|circuit.?breaker|UNKNOWN_AUTOMATION|TRANSIENT_INFRA" | tail -40'
run 'docker ps --format "{{.Names}}" | grep -i worker | while read -r w; do echo "--- $w ---"; docker logs --since 24h "$w" 2>&1 | tail -25; done'

sec "COLLECTION COMPLETE"

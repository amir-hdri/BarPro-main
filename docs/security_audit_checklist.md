# Pre-Deployment Security Audit Checklist

This checklist must be fully executed and signed off before deploying any changes to the production environment of BarPro.

---

## 1. Secrets & Credentials Management
- [ ] **No Leaked Secrets**: Verify that no real credentials (SSH passwords, private keys, Redis/Postgres passwords) are committed in the git repository.
- [ ] **Leaked Passwords Rotated**: Confirm the actual server passwords have been rotated and are not matching any historical repository strings (`PLACEHOLDER_SSH_PASSWORD`).
- [ ] **Git History Checked**: Verify that `.env` and `celerybeat-schedule.db` files are purged from all historical commits using `git filter-repo`.
- [ ] **Gitignore Compliance**: Ensure `.env` is tracked in `.gitignore`.

---

## 2. API & Network Security
- [ ] **HMAC Webhook Validation**: Verify that the Alertmanager webhook receiver validates signatures using `X-Barpro-Signature` and a configured `ALERT_WEBHOOK_SECRET`.
- [ ] **Replay Window Enforcement**: Confirm the webhook timestamp drift checks reject any requests older than 300 seconds (5 minutes).
- [ ] **Restricted Port Exposure**: Verify that only ports `80` (and `443` after SSL setup) are exposed publicly.
- [ ] **Squid Egress Port Block**: Run `sudo bash /opt/barpro/scripts/secure_squid_ports.sh` to restrict Squid ports `3129` and `3130` to localhost and internal Docker network only. Add it to `@reboot` crontab.
- [ ] **UFW Allowlist**: Verify only registered worker IPs can access database port `5432` and Redis port `6379`.

---

## 3. Container & Operating System Isolation
- [ ] **No Privileged Containers**: Ensure `privileged: true` is not present in any Compose files.
- [ ] **Restricted Capabilities**: Confirm containers use `cap_add: [SYS_ADMIN, NET_ADMIN]` and `security_opt: [no-new-privileges:true]`.
- [ ] **Database Role Enforcement**: Ensure remote workers use the low-privilege database user role (`barpro_worker`), which has no `DELETE`/`CREATE`/`DROP` permissions.

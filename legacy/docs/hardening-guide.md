# Hardening Guide — cove-apps-fusion (FUSION Platform)

Post-deployment security hardening for the FUSION platform. This guide covers
solution-specific hardening only. Baseline OS hardening (STIG, CIS) is applied
by the platform team prior to solution deployment.

## Scope

- **Solution:** FUSION Platform (cove-apps-fusion)
- **Target OS:** RHEL 9 (primary); Ubuntu 22.04 (Stage 1 dev acceptable)
- **Compliance frameworks:** NIST 800-53 Rev 5, CMMC 2.0, DISA STIG RHEL 9 (Stage 3+)
- **Deployment model:** K3s single-node (Stage 1–2); hardened K8s cluster (Stage 3+)

## File and Directory Permissions

~~~bash
# Set correct ownership and permissions on solution files
chown -R fusion-api:fusion-api /opt/cove-apps-fusion
chmod 750 /opt/cove-apps-fusion
chmod 640 /opt/cove-apps-fusion/.env
chmod 750 /opt/cove-apps-fusion/backend
chmod 640 /opt/cove-apps-fusion/backend/*.js
~~~

| Path | Owner | Permissions | Reason |
|---|---|---|---|
| `/opt/cove-apps-fusion/` | `fusion-api:fusion-api` | `750` | Service files — no world read |
| `/opt/cove-apps-fusion/.env` | `fusion-api:fusion-api` | `640` | Env vars — never world-readable |
| `/opt/cove-apps-fusion/backend/` | `fusion-api:fusion-api` | `750` | Backend process files |
| `/var/log/fusion/` | `fusion-api:fusion-api` | `750` | Log directory |

## Secrets and Credentials

- [ ] No credentials stored in plaintext on disk — all secrets via AWS Secrets Manager
- [ ] `.env` file (if used in lab) has permissions `640` — readable only by the service account
- [ ] `AUTH_BYPASS` is NOT set or is explicitly `false` in production
- [ ] Service account has least-privilege IAM policy — Secrets Manager `GetSecretValue` scoped to FUSION secrets only
- [ ] OIDC client secret is stored in Secrets Manager, not in `.env`

~~~bash
# Verify .env permissions
stat -c "%a %U:%G %n" /opt/cove-apps-fusion/.env
# Expected: 640 fusion-api:fusion-api /opt/cove-apps-fusion/.env

# Verify AUTH_BYPASS is not set in the process environment
ps eww $(pgrep -f "node.*main") | grep -c AUTH_BYPASS
# Expected: 0

# Verify no raw secrets in the repo
gitleaks detect --source . --log-opts="--all"
# Expected: no output (exit code 0)
~~~

## Network Hardening

FUSION listens on the following ports. All others should be blocked by the host firewall:

| Port | Protocol | Service | Restrict to |
|---|---|---|---|
| 3000 | TCP | Fastify backend API | Z-UI → Z-API (internal only) |
| 5432 | TCP | PostgreSQL | Z-API → Z-DB (internal only) |
| 443 | TCP | Frontend (HTTPS) | Public / user browsers |
| 80 | TCP | HTTP redirect to HTTPS | Public (redirect only) |

~~~bash
# Verify listening ports
ss -tlnp | grep -E "3000|5432|443|80"

# Verify TLS 1.2 minimum (TLS 1.3 preferred)
openssl s_client -connect <host>:443 -tls1_2 2>&1 | grep "Protocol"
# Expected: TLSv1.2 or TLSv1.3

# Block 3000 and 5432 from external access (firewalld example)
firewall-cmd --permanent --add-rich-rule='rule family="ipv4" port port="3000" protocol="tcp" reject'
firewall-cmd --permanent --add-rich-rule='rule family="ipv4" port port="5432" protocol="tcp" reject'
firewall-cmd --reload
~~~

## Service Account

~~~bash
# Create a dedicated non-root service account
useradd -r -s /sbin/nologin -d /opt/cove-apps-fusion fusion-api

# Verify the service runs as fusion-api, not root
ps -o user,pid,cmd -p $(pgrep -f "node.*main")
# Expected: fusion-api <pid> node /opt/cove-apps-fusion/backend/main.js
~~~

- [ ] Backend process runs as `fusion-api` — never as `root`
- [ ] `fusion-api` has no interactive login shell (`/sbin/nologin`)
- [ ] `fusion-api` home directory is restricted to `/opt/cove-apps-fusion`
- [ ] K3s Pod `securityContext.runAsNonRoot: true` (Stage 2+)
- [ ] K3s Pod `securityContext.readOnlyRootFilesystem: true` (Stage 2+)
- [ ] K3s Pod `securityContext.allowPrivilegeEscalation: false` (Stage 2+)

## Logging and Auditing

- [ ] All authenticated actions emit OCSF audit events to `AUDIT_SINK_URL` (see `docs/audit-spec.md`)
- [ ] Audit sink is append-only — no update or delete possible
- [ ] No secrets or PII written to application logs (`no-console` ESLint rule enforced)
- [ ] Log retention: minimum 30 days (AU-11); 90 days for audit events (AU-11) [S2+]
- [ ] `AUDIT_SINK_URL` uses HTTPS in all non-local environments

~~~bash
# Verify logging is active
journalctl -u fusion-api --since "1 hour ago" | head -20

# Verify no secrets appear in recent logs
journalctl -u fusion-api --since "24 hours ago" | \
  grep -iE "password|secret|token|api_key|authorization" | wc -l
# Expected: 0
~~~

## FIPS Cryptography

- [ ] Node.js runtime reports FIPS mode active
- [ ] Base container image is Red Hat UBI9 FIPS (not standard UBI9)

~~~bash
# Verify FIPS mode in the running process
node -e "require('crypto').getFips() === 1 || process.exit(1)" && echo FIPS OK
# Expected: FIPS OK

# Verify OpenSSL FIPS provider
openssl list -providers | grep fips
# Expected: fips (loaded)
~~~

See `docs/stack.md` for the FIPS cryptographic algorithm allow-list.

## Compliance Alignment

| Control | Framework | Status | Notes |
|---|---|---|---|
| AU-2 | NIST 800-53 | Partial | authn.success/failure audit missing (F-001 BLOCKS_S2) |
| AU-5 | NIST 800-53 | Partial | Audit fail-open at S1; fail-closed required at S3+ |
| AU-12 | NIST 800-53 | Partial | Audit fields incomplete (F-002 BLOCKS_S2) |
| SC-8 | NIST 800-53 | Partial | TLS enforced at network level; http.ts lacks HTTPS-only guard |
| SC-13 | NIST 800-53 | Partial | FIPS runtime assertion not yet in code (F-028) |
| IA-2 | NIST 800-53 | Partial | OIDC/PKCE flow in place; MFA enforcement per OIDC provider config |
| CM-3 | NIST 800-53 | Implemented | All changes via PR; CODEOWNERS enforced |
| SI-10 | NIST 800-53 | Partial | Zod validation on input; no Fastify route schema (F-019) |
| IA-5 | NIST 800-53 | Implemented | No raw secrets committed; gitleaks blocking |

## Hardening Verification Checklist

Run after every deployment and after any configuration change:

- [ ] `gitleaks detect --source . --log-opts="--all"` — no output
- [ ] `node -e "require('crypto').getFips()"` returns `1` (on FIPS-enabled host)
- [ ] `GET /health` returns HTTP 200
- [ ] Process runs as `fusion-api`, not `root`
- [ ] `.env` permissions are `640`
- [ ] Port 3000 is not reachable from outside the cluster
- [ ] Port 5432 is not reachable from outside the cluster
- [ ] `AUTH_BYPASS` is absent from the production process environment
- [ ] Audit events are flowing to the sink (check sink logs for recent entries)

## Known Hardening Gaps (Stage 1)

These are accepted risks at Stage 1 with documented payback triggers. See `docs/risks.md`.

- **AU-2 gap:** Backend does not emit `authn.success` / `authn.failure` audit events (F-001 BLOCKS_S2). Must be resolved before Stage 2.
- **SC-8 gap:** `backend/src/common/http.ts` has no HTTPS-only URL enforcement. Resolved at Stage 2 with TLS guard.
- **SC-13 gap:** No runtime `crypto.getFips()` startup assertion — FIPS mode could be silently inactive (F-028). Resolved at Stage 2.
- **Audit fail-open:** Emit errors are silently swallowed at Stage 1 (documented SHORTCUT). Fail-closed required at Stage 3 (AU-5).
- **mTLS absent:** Service-to-service mTLS (Z-API ↔ Z-DB ↔ Z-AUDIT) deferred to Stage 3 via service mesh ([CONFIRM-06]).

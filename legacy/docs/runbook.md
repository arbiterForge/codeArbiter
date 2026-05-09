# Runbook: cove-apps-fusion (FUSION Platform)

Day-2 operations guide for the FUSION platform. Assumes the platform is deployed
and running. For initial deployment, see `docs/deploy-guide.md`.

## Services and Ports

| Service | Port | Zone | Process |
|---|---|---|---|
| Backend API (Fastify) | 3000 | Z-API | `node backend/src/main.js` |
| Frontend (Vite dev) | 5173 | Z-UI | `npm run dev` (dev only) |
| Frontend (built) | 80 / 443 | Z-UI | Served by nginx or CDN |
| PostgreSQL | 5432 | Z-DB | `postgres` |
| Audit Sink | per `AUDIT_SINK_URL` | Z-AUDIT | External — see `docs/audit-spec.md` |

## Health Checks

~~~bash
# Backend API health
curl -s http://localhost:3000/health
# Expected: {"status":"ok","ts":"<ISO8601>"}

# Check the process is running
ps aux | grep node

# Check the port is listening
ss -tlnp | grep 3000

# Check recent logs (systemd)
journalctl -u fusion-api --since "1 hour ago" -f

# Check recent logs (Docker/Podman)
docker logs fusion-api --since 1h --follow
~~~

## Restart Procedures

~~~bash
# Systemd service restart
sudo systemctl restart fusion-api

# Docker/Podman restart
docker restart fusion-api

# Full stack restart (local dev)
make down && make up

# Graceful backend restart (K3s)
kubectl rollout restart deployment/fusion-api -n fusion
kubectl rollout status deployment/fusion-api -n fusion
~~~

## Common Failure Scenarios

### Backend returns 500 on all routes

1. Check database connectivity: `psql $DATABASE_URL -c "SELECT 1;"`
2. Check `DATABASE_URL` is set: `echo $DATABASE_URL` (should not be empty)
3. Check Drizzle schema is migrated: `cd backend && npx drizzle-kit status`
4. Review recent logs for the error: `journalctl -u fusion-api -n 100 --no-pager`

### OIDC login fails / 401 on authenticated routes

1. Verify `OIDC_JWKS_URI` is reachable from the backend host: `curl -s $OIDC_JWKS_URI | jq .`
2. Verify `OIDC_ISSUER` matches the `iss` claim in issued tokens (decode with `jwt decode <token>`)
3. Check that `AUTH_BYPASS` is NOT set to `true` in the production environment
4. Verify the OIDC client is configured with the correct redirect URI in the identity provider

### Audit events not appearing in sink

1. Verify `AUDIT_SINK_URL` is reachable: `curl -s -o /dev/null -w "%{http_code}" $AUDIT_SINK_URL`
2. Check backend logs for audit emit errors — at Stage 1, emit errors are swallowed silently.
   Search for HTTP errors in the audit path: `journalctl -u fusion-api | grep audit`
3. Confirm the frontend's `VITE_AUDIT_SINK_URL` is correct (browser network tab → XHR requests)

### Pre-commit hook fails on commit

~~~bash
# Run hooks manually to see what is failing
pre-commit run --all-files

# Run only the failing hook
pre-commit run backend-test --all-files

# If gitleaks fires, a secret may be staged — do NOT use --no-verify
# See SECURITY.md for the correct procedure to remove a committed secret
~~~

### CI job fails on Gitea Actions

1. Check the Gitea Actions run log: `gitea.cove.gdit/<org>/<repo>/actions`
2. For the `test` job: verify `AUTH_BYPASS: "true"` is set at the job level in `ci-linux.yml`
3. For the `lockfile` job: run `npm install` locally and commit updated `package-lock.json` files
4. For the `secrets` job: gitleaks found a secret pattern — rotate the secret, remove from history per `SECURITY.md`

## Database Operations

~~~bash
# Run pending migrations
cd backend && npx drizzle-kit migrate

# Check migration status
cd backend && npx drizzle-kit status

# Connect to the database interactively
psql $DATABASE_URL

# Backup (before any migration on a live environment)
pg_dump $DATABASE_URL > backup-$(date +%Y%m%d-%H%M%S).sql
~~~

> **Warning:** Never hand-edit the database schema directly. Never modify a migration file
> after it has been applied to any environment. See `docs/coding-standards.md`.

## Audit Log Inspection

~~~bash
# Query recent audit events from the sink (if sink is a local HTTP service)
curl -s "$AUDIT_SINK_URL/events?limit=50" | jq .

# If audit events are written to a local file or stdout, inspect with:
journalctl -u fusion-audit-sink --since "1 hour ago" | jq -R 'try fromjson'
~~~

Audit event fields are defined in `docs/audit-spec.md`. At Stage 1, the sink is a
direct HTTP POST endpoint. The sink URL is configured via `AUDIT_SINK_URL`.

## Log Retention and Rotation

At Stage 1, log rotation follows the host OS defaults (logrotate / systemd-journald).
Minimum retention: 30 days for audit events (AU-11). Secrets must never appear in logs.

## Escalation

1. Check `docs/open-questions.md` for unresolved `[CONFIRM-NN]` items that may be blocking
2. Check the latest checkpoint document in `docs/checkpoints/` for known issues
3. For security incidents (suspected secret leak, auth bypass): follow `SECURITY.md` immediately

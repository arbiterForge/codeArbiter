# Deploy Guide: cove-apps-fusion (FUSION Platform)

This guide covers deploying the FUSION platform to a target environment. FUSION runs as
a containerized stack on K3s (Stage 1–2) or a hardened K8s cluster (Stage 3+).

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Node.js | 22 LTS | Control node only — for build artifacts |
| npm | >= 10 | Bundled with Node.js 22 |
| Ansible | >= 2.15 | Required on the control node |
| OpenTofu | >= 1.8 | Infrastructure provisioning |
| kubectl | >= 1.30 | K3s cluster access |
| Helm | >= 3.15 | Chart deployment |
| Docker / Podman | any | Image build |
| AWS CLI | >= 2.15 | Secrets Manager + S3 access |

## Target Environment

- **OS:** RHEL 9 (production target); Ubuntu 22.04 (acceptable for Stage 1 dev)
- **Platform:** AWS EC2 / K3s single-node (Stage 1–2); hardened K8s cluster (Stage 3+)
- **Access required:** SSH key to control node; IAM role with Secrets Manager read + S3 write

## Pre-Deployment Checklist

- [ ] Target hosts are reachable from the control node (`ansible -m ping all`)
- [ ] IAM role or credentials are in place and can read from Secrets Manager
- [ ] `.env` is populated with real values (copied from `.env.example`)
- [ ] OIDC provider endpoint is reachable from the target environment ([CONFIRM-01])
- [ ] Audit sink URL is reachable from the target environment
- [ ] Inventory file is updated with target hosts
- [ ] A pre-deployment snapshot or backup has been taken (if applicable)
- [ ] `make ci` passes locally on the branch being deployed

## Configuration

~~~bash
# Copy and populate the environment file
cp .env.example .env
# Edit .env — required variables:
#   DATABASE_URL        — PostgreSQL connection string
#   OIDC_JWKS_URI       — OIDC provider JWKS endpoint (e.g. https://keycloak.internal/realms/fusion/protocol/openid-connect/certs)
#   OIDC_ISSUER         — Expected JWT issuer
#   AUDIT_SINK_URL      — HTTP endpoint for audit event POSTs
#   VITE_OIDC_ISSUER    — Frontend OIDC issuer (build-time)
#   VITE_OIDC_CLIENT_ID — OIDC client ID (build-time)
#   VITE_API_BASE_URL   — Backend API base URL (build-time)
#   VITE_AUDIT_SINK_URL — Audit sink URL (build-time, browser-visible)

# Update the inventory with your target hosts
cp ansible/inventory/hosts.example ansible/inventory/hosts
vi ansible/inventory/hosts
~~~

## Build

~~~bash
# Install dependencies
npm install

# Build frontend production bundle
cd frontend && npm run build && cd ..

# The backend runs directly via Node.js — no separate build step required
~~~

## Deploy

~~~bash
# Stage 1 — local dev stack (requires docker-compose.yml — not yet authored, see CLAUDE.md §8)
make up

# Stage 1 — Ansible deploy to target RHEL/Ubuntu host
ansible-playbook playbooks/site.yml \
  -i ansible/inventory/hosts \
  --extra-vars "@.env"

# Stage 2+ — OpenTofu infrastructure + Helm chart
cd terraform && tofu init && tofu apply
helm upgrade --install fusion deploy/helm/fusion \
  --namespace fusion \
  --values deploy/helm/fusion/values.yaml \
  --set image.tag=$(git rev-parse --short HEAD)
~~~

> **Note:** `playbooks/pre-check.yml` and `playbooks/main.yml` are not yet populated.
> `make up` is inoperable until `docker-compose.yml` is authored. See CLAUDE.md §8.

## Post-Deployment Validation

~~~bash
# Verify backend health
curl -s https://<host>/health | jq .
# Expected: {"status":"ok","ts":"<ISO timestamp>"}

# Verify frontend loads
curl -s -o /dev/null -w "%{http_code}" https://<host>/
# Expected: 200

# Run Ansible verify playbook (when populated)
ansible-playbook playbooks/verify.yml -i ansible/inventory/hosts
~~~

- [ ] `GET /health` returns `{"status":"ok"}` with HTTP 200
- [ ] Frontend loads and shows the FUSION catalog page
- [ ] OIDC login redirects correctly to the configured provider
- [ ] Audit events appear in the sink (check `AUDIT_SINK_URL` logs)
- [ ] `gitleaks detect --source . --log-opts="--all"` returns no secrets

## Rollback

~~~bash
# Helm rollback to previous release
helm rollback fusion -n fusion

# Ansible rollback (when playbook is populated)
ansible-playbook playbooks/rollback.yml -i ansible/inventory/hosts

# Database: Drizzle migrations are forward-only by default.
# For column drops or destructive changes, see the migration's rollback comment.
~~~

## Known Deployment Issues

- `make up` requires `docker-compose.yml` which does not yet exist (Stage 1 gap — see CLAUDE.md §8 and checkpoint F-010)
- Ansible playbooks `pre-check.yml` and `main.yml` are stubs — `ansible-playbook playbooks/site.yml` will fail until they are populated (checkpoint F-025)
- `AUTH_BYPASS=true` MUST NOT be set in any non-local environment. If CI sets it (scoped to the test job), verify it is not present in deployment environment variables.

# Architecture — Trust Zones

Reference diagram: `docs/architecture/fusion-c4.puml` (not yet authored; tracked in CLAUDE.md §8).

Default-deny between zones. Cross-zone calls MUST go through a named,
authenticated interface. (SC-7, SC-7(5), AC-4) [S2+]

**Open question (architectural):** The frontend audit library currently POSTs directly to
Z-AUDIT (bypassing Z-API). `trust-zones.md` only authorizes Z-API and Z-WORKER as Z-AUDIT
callers. A decision is required before Stage 2: either route frontend audit events through a
Z-API relay endpoint, or explicitly authorize the Z-UI → Z-AUDIT path here and update
`deploy/egress-allowlist.yaml`. See checkpoint F-005.

| Zone | Contents | Allowed Inbound | Allowed Outbound |
|---|---|---|---|
| Z-UI | React canvas (Vite/React Router) | User browser via TLS 1.3 | Z-API only |
| Z-API | Fastify control plane (Node.js 22) | Z-UI | Z-DB, Z-SECRETS, Z-WORKER, Z-AUDIT |
| Z-DB | PostgreSQL | Z-API | none |
| Z-SECRETS | KMS / Secrets Manager | Z-API, Z-WORKER | none |
| Z-WORKER | Job execution (subprocess→Argo) | Z-API | Z-TARGET, Z-SECRETS, Z-AUDIT, internet (allow-list only) |
| Z-TARGET | Provisioned solution infra | Z-WORKER (during deploy only) | varies per solution |
| Z-AUDIT | Append-only audit sink | Z-API, Z-WORKER | none |

## Verification

- NetworkPolicy manifests live at `deploy/k8s/netpol/`.
- `make netpol-check` validates that every Pod selector is covered by an explicit policy.
- mTLS between Z-API ↔ Z-WORKER ↔ Z-DB ↔ Z-AUDIT [S3+] via service mesh ([CONFIRM-06] or Linkerd default).

## Egress Allow-List

`deploy/egress-allowlist.yaml` is the single source of truth for outbound
destinations from any zone. Adding a destination requires CODEOWNER approval
AND a Decision Log entry.

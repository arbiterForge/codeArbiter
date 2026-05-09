# ALLOWED_LICENSES.md

License allow-list enforced by `make license-scan`. Default-deny: anything not
on this list MUST NOT be added without a Decision Log entry recording the
exception and its supersede target.

## Permissive (auto-allowed)

- MIT
- BSD-2-Clause
- BSD-3-Clause
- Apache-2.0
- ISC
- Python-2.0 / PSF-2.0
- PostgreSQL
- Unlicense
- 0BSD

## Conditional / Weak Copyleft (requires Decision Log entry)

- MPL-2.0 — file-level copyleft. Approved for OpenTofu only.
- LGPL-2.1 / LGPL-3.0 — dynamic linking only. Case-by-case.

## Risk-Flagged (existing exception only)

- GPL-3.0 — Ansible-core under R-01. No new GPL deps. MUST be removed by Stage 3 promotion or covered by legal sign-off.

## Default-Deny

- AGPL (any)
- BSL (Business Source License) — covers HashiCorp Terraform, Sentry, etc.
- SSPL (Server Side Public License) — covers MongoDB, Elastic
- Commons Clause
- Elastic License v2
- Confluent Community License
- Any "non-commercial only" or custom non-OSI license
- Any license missing from the package metadata (`license-checker` reports `UNKNOWN`)

## Verification

```bash
make license-scan
```

CI job: `license-scan` (required check on `main`).

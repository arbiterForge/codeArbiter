# ADR 0002 — Adopt `@xyflow/react@12` in Place of `reactflow@11`

- **Date:** 2026-05-04
- **Status:** Accepted
- **Owners:** Arch lead
- **Supersedes:** `docs/stack.md` entry "React 18, RF 11"

## Context

`docs/stack.md` pinned the frontend graph library at "RF 11" (React Flow v11),
which shipped under the npm package name `reactflow`. In late 2023 the upstream
maintainers (xyflow GmbH) renamed the package to `@xyflow/react` and released
v12 as the only supported major under the new name. `reactflow@11` is no longer
receiving active releases or CVE patches.

When the FUSION UI scaffold was initiated, the dependency reviewer flagged a hard
block: the proposed `@xyflow/react@12` constitutes a major-version and package-
name drift from the pinned stack entry, requiring a formal Decision Log entry
before the dep can be merged.

A license review of `@xyflow/react@12` was conducted as part of this ADR:

| Field | Value |
|---|---|
| SPDX | MIT |
| Commercial use | Permitted — no Commons Clause, no BSL, no non-commercial restriction |
| Upstream confirmation | xyflow.com/open-source: "We'll keep our software MIT Licensed forever." |
| CVEs | None in OSV / GitHub Advisory Database as of 2026-05-04 |
| Last release | 12.10.2 (2025-02-24) — within 18-month maintenance window |
| Transitive production deps | +3: `zustand@^4` (MIT), `classcat@^5` (MIT), `@xyflow/system` (MIT) |

## Decision

Adopt `@xyflow/react@12` as the pinned React Flow major for `fusion-core`.
Update `docs/stack.md` to replace "RF 11" with "`@xyflow/react` 12".

The `reactflow@11` package name is retired and MUST NOT be introduced.

## Consequences

**Positive.** Project is on the actively maintained package with ongoing CVE
coverage. v12 ships improved TypeScript types, a smaller bundle, and a cleaner
API surface compared to v11 — reducing integration friction as the node/adapter
graph canvas grows.

**Negative.** v12 introduces a new `@xyflow/system` internal package as a
transitive dep; this package has no independent release history outside the
xyflow monorepo and should be treated as part of the `@xyflow/react` supply
chain, not an independent dep.

**Trade-off level cited (per CLAUDE.md §0):** Level 3 (Maintainability &
reviewability) — adopting the actively maintained package over the retired one
is a maintainability decision. License and CVE posture are both clean; no
security or correctness tradeoff is made.

## Verification

- `npm ls @xyflow/react` returns `12.x.x`
- `make license-scan` exits 0 (MIT is on the ALLOWED_LICENSES.md allow-list)
- `reactflow` does NOT appear in `package.json` or `package-lock.json`

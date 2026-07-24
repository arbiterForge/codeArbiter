# Cut docs — never scaffolded

The canonical list of project-state docs that codeArbiter v2 deliberately does NOT create. Shared by
the two initialization skills (`decompose`, `context-creation`) so the list cannot drift between them.

**Never scaffold any of these:**

- `audit-spec.md`
- `observability-spec.md`
- `trust-zones.md`
- `secrets-policy.md`
- `dependency-policy.md`
- a separate `stage` file

Maturity is the single `stage:` value in `CONTEXT.md` frontmatter — there is no separate stage file and
no promotion ladder. Security posture lives thin in `security-controls.md`, not in a cut spec.

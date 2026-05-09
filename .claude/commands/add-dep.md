---
description: Vet, then add a new third-party dependency through the full FUSION supply-chain workflow
argument-hint: "<package-name> [version]"
---

You are about to add a third-party dependency. This action requires CODEOWNER
approval before merge. Follow the workflow exactly.

1. Read `docs/dependency-policy.md` and `ALLOWED_LICENSES.md` in full.
2. Look up `${1:?package name required}` metadata:
   - Declared license (SPDX)
   - Latest stable version
   - Last release date
   - Repository URL and most recent commit date
3. Compare the license to `ALLOWED_LICENSES.md`. If on the default-deny list,
   STOP and tell the user. Do NOT add it.
4. If the license is `MPL-2.0`, `LGPL-2.1`, or `LGPL-3.0`: STOP, tell the user
   a Decision Log entry is required first.
5. Determine which dependency manager applies (Poetry / npm / etc.) by
   inspecting the repo. Do NOT add to multiple managers.
6. Run the manager's add command with the version pinned. If no version was
   provided as `${2}`, propose the latest stable; ASK USER before accepting.
7. Regenerate the lockfile.
8. Run `make deps-scan` and `make license-scan`. If either fails, REVERT the
   addition.
9. Compute transitive count delta:
   - Python: `pipdeptree | wc -l` before and after
   - Node: `npm ls --all | wc -l` before and after
10. Invoke the `dependency-reviewer` subagent.
11. Draft a PR description with the four required fields: name, version,
    license, transitive count delta, plus maintenance signal (last release date).

MUST NOT merge. CODEOWNER approval required, comment with literal text
`Approved by <name> for adding ${1}`.

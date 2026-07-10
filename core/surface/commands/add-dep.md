---
description: Vet a new or changed third-party dependency for license, provenance, and supply-chain risk before any install runs.
argument-hint: "<package[@version]>"
---

# {{CMD:add-dep}} — dependency review

Gate a new or changed third-party dependency through review before it lands. When you route through
this command, the orchestrator runs no install until the `dependency-reviewer` agent clears the
package. Specify the exact version if you have one; without one, the reviewer evaluates the latest
available version.

## Routes to

The `dependency-reviewer` agent (`{{PLUGIN_ROOT}}/agents/dependency-reviewer.md`). The agent
reads `{{PROJECT_DIR}}/.codearbiter/security-controls.md` (allowed/denied licenses, provenance
and supply-chain policy) and `{{PROJECT_DIR}}/.codearbiter/tech-stack.md` (stack fit, dependency
manager) to judge the package.

After the agent clears it, the orchestrator surfaces the install command for confirmation. The lock
file change is committed alongside the manifest change — never one without the other.

## When NOT to use

- Removing a dependency → `{{CMD:fix}}` or `{{CMD:feature}}` with the change described.
- Updating an existing dependency as part of a code change → `{{CMD:feature}}` / `{{CMD:fix}}`; manifest
  changes route to review at `{{CMD:pr}}`.
- Asking about a package without installing it → `{{CMD:btw}}`.

## Hard gate

MUST NOT install before `dependency-reviewer` clears the package. BLOCK on a denied license or any
unresolved supply-chain or provenance concern.

This gate is **orchestrator-enforced, not hook-enforced**: unlike the crypto/secret gate
(`pre-bash.py` H-09b/H-10b), there is no pre-bash rule that blocks a bare `npm`/`pip`/`yarn`/`pnpm
install` typed outside this command. The discipline depends on routing installs through `{{CMD:add-dep}}`.
A hook-level install block (parallel to the security-gate marker) would be a stronger posture, but is a
deliberate behavior change — a possible future enhancement, not the current contract.

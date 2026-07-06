---
description: Vet a new or changed third-party dependency for license, provenance, and supply-chain risk before any install runs.
argument-hint: "<package[@version]>"
---

# /ca:add-dep — dependency review

Gate a new or changed third-party dependency through review before it lands. When you route through
this command, the orchestrator runs no install until the `dependency-reviewer` agent clears the
package. Specify the exact version if you have one; without one, the reviewer evaluates the latest
available version.

## Dispatches

The `dependency-reviewer` agent (`${CLAUDE_PLUGIN_ROOT}/agents/dependency-reviewer.md`) — the one
command that dispatches an agent directly, with no owning skill in between. The agent
reads `${CLAUDE_PROJECT_DIR}/.codearbiter/security-controls.md` (allowed/denied licenses, provenance
and supply-chain policy) and `${CLAUDE_PROJECT_DIR}/.codearbiter/tech-stack.md` (stack fit, dependency
manager) to judge the package.

After the agent clears it, the orchestrator surfaces the install command for confirmation. The lock
file change is committed alongside the manifest change — never one without the other.

## When NOT to use

- Removing a dependency → `/ca:fix` or `/ca:feature` with the change described.
- Updating an existing dependency as part of a code change → `/ca:feature` / `/ca:fix`; manifest
  changes route to review at `/ca:pr`.
- Asking about a package without installing it → `/ca:btw`.

## Hard gate

MUST NOT install before `dependency-reviewer` clears the package. BLOCK on a denied license or any
unresolved supply-chain or provenance concern — then propose a vetted alternative, or the user may
proceed via `/ca:override "reason"` (logged). This gate is orchestrator-enforced: every install
routes through `/ca:add-dep`, whether or not a hook would catch a bare install typed around it.

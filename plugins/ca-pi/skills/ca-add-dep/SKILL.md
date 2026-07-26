---
name: ca-add-dep
description: Vet a new or changed third-party dependency for license, provenance, and supply-chain risk before any install runs.
argument-hint: "<package[@version]>"
---

# /ca-add-dep — dependency review

Gate a new or changed third-party dependency through review before it lands. When you route through
this command, the orchestrator runs no install until the `dependency-reviewer` agent clears the
package. Specify the exact version if you have one; without one, the reviewer evaluates the latest
available version.

## Routes to

The `dependency-reviewer` agent (`<plugin-root>/agents/dependency-reviewer.md`). The agent
reads `<project-root>/.codearbiter/security-controls.md` (allowed/denied licenses, provenance
and supply-chain policy) and `<project-root>/.codearbiter/tech-stack.md` (stack fit, dependency
manager) to judge the package.

After the agent clears it, the orchestrator surfaces the install command for confirmation. The lock
file change is committed alongside the manifest change — never one without the other.

## When NOT to use

- Removing a dependency → `/ca-fix` or `/ca-feature` with the change described.
- Updating an existing dependency as part of a code change → `/ca-feature` / `/ca-fix`; manifest
  changes route to review at `/ca-pr`.
- Asking about a package without installing it → `/ca-btw`.

## Ephemeral tool run — one invocation, nothing adopted

A one-time developer tool is not a dependency, and reviewing it as one is what
issue #346 records going wrong: a duplicate-code investigation was interrupted
and pushed toward project-dependency review for `jscpd`, which the operator had
explicitly said must never be listed as a dependency. The redirect loop then
reached for `/ca-override`, a bypass invented to cover missing coverage. This
section is that coverage.

**The distinction is the dependency GRAPH, not the download.** Adopting or
changing anything that enters `package.json`, a lockfile, or a base image is the
review above, unchanged. Running a pinned tool once, against the repository,
adopting nothing, is this.

Route here when ALL of these hold. If any is unclear, it is a dependency and
takes the full review:

1. The operator asked for this specific tool, by name, in this session.
2. It runs ONCE, for inspection or analysis. It is not wired into a script, a
   hook, or CI.
3. Nothing it does may change a manifest, a lockfile, or a committed artifact.

Then:

- **Pin the exact version.** `npx jscpd@4.0.5 .`, never bare `npx jscpd` — an
  unpinned invocation resolves to whatever was published this morning, which is
  the supply-chain exposure the review exists for and the one part of it that
  still applies at full strength.
- **Use the approved registry.** `https://registry.npmjs.org` is the only one
  (`security-controls.md`); no `git+`, no `file:`, no non-TLS source.
- **Confirm before running**, naming the exact command. One approval, not a
  review — the operator has already made the adoption decision, which is "no".
- **Isolate what you can.** Prefer a cache directory under the system temp dir
  over the project tree, and write any report there too, so the run leaves no
  residue a later commit could pick up.
- **Report what ran** — the pinned command and where its output went.

**Hard gate: MUST NOT modify a manifest or a lockfile.** If the tool writes one,
that is adoption, and it stops here and routes to the review above. Verify
rather than trust: `git status --porcelain` over the manifest and lockfile paths
must be unchanged after the run. A tool that requires adoption to run at all is
a dependency, and saying so is the correct answer.

This is a bounded carve-out inside this command, not a command of its own
(ADR-0023). A new command would add a public surface — the catalog, the Pi
command catalog, the README counts, the site sidebar — to govern an action whose
whole definition is that it changes nothing.

## Hard gate

MUST NOT install before `dependency-reviewer` clears the package. BLOCK on a denied license or any
unresolved supply-chain or provenance concern.

This gate is **orchestrator-enforced, not hook-enforced**: unlike the crypto/secret gate
(`pre-bash.py` H-09b/H-10b), there is no pre-bash rule that blocks a bare `npm`/`pip`/`yarn`/`pnpm
install` typed outside this command. The discipline depends on routing installs through `/ca-add-dep`.
A hook-level install block (parallel to the security-gate marker) would be a stronger posture, but is a
deliberate behavior change — a possible future enhancement, not the current contract.

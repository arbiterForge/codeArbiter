---
entity: commands/add-dep
related: [agents/dependency-reviewer, review]
gates:
  - gate: dependency review
    when: before any install runs
    effect: the dependency-reviewer agent must clear the package first — a denied license or unresolved supply-chain concern blocks the install
---

## What it does

Gates a new or changed third-party dependency through review before anything installs. Naming the
package here — with a version if you have one, or without one to have the reviewer evaluate the
latest available — hands the decision to the `dependency-reviewer` agent, which reads
`.codearbiter/security-controls.md` for the allowed/denied license list and supply-chain policy,
and `.codearbiter/tech-stack.md` for stack fit and the project's dependency manager.

Once the agent clears the package, the install command is surfaced for confirmation rather than
run silently, and the resulting lock-file update ships in the same commit as the manifest edit,
so the two never drift apart.

This gate is orchestrator-enforced, not hook-enforced: there's no pre-bash rule blocking a bare
install command run outside this channel the way the crypto/secret gate blocks a raw shell
command. The discipline depends on actually routing installs through here.

## Usage

```
/ca:add-dep <package[@version]>
```

Version is optional; omitting it evaluates the latest available release.

## Example

```text
> /ca:add-dep left-pad@1.3.0

dependency-reviewer: left-pad@1.3.0
  license: MIT (allowed)
  provenance: npm registry, 6M+ weekly downloads, maintained
  supply-chain: no known advisories

Cleared. Install command ready:
  npm install left-pad@1.3.0
Run it? (lock-file change will be committed alongside package.json)
```

## When to reach for it

Removing a dependency, or a code change that happens to bump one, goes through `/ca:fix` or
`/ca:feature` instead (the manifest change is reviewed at `/ca:pr`); asking about a package
without installing it is `/ca:btw`'s job.

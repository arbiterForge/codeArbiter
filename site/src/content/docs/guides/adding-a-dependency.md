---
title: "Add a Dependency Safely"
description: "Use /ca:add-dep to vet a new third-party package for license compliance, provenance, and supply-chain risk before any install runs."
journey:
  level: Practitioner
  time: 10–20 min
  outcome: "a version-pinned dependency decision backed by the target repository's license, provenance, maintenance, CVE, and stack-fit policy."
  prerequisites:
    - An initialized repository
    - A concrete package and purpose
  proof: "The reviewed version matches the installed version, the audit command is green at the governing threshold, and manifest and lockfile move together."
---

Route every new dependency through `/ca:add-dep` before touching the package manifest. The command holds installation until the `dependency-reviewer` agent clears the package on license, provenance, and supply-chain posture.

<div class="ca-host-syntax">
  <strong>Host syntax:</strong> Claude Code uses <code>/ca:add-dep</code>; Codex uses
  <code>$ca-add-dep</code>; Pi uses <code>/ca-add-dep</code>. Examples below use Claude Code syntax.
</div>

<figure class="ca-diagram">
  <img
    src="/codeArbiter/diagrams/lane-add-dep.svg"
    alt="The /ca:add-dep lane in two rows: Commands (/ca:add-dep) and Agents (dependency-reviewer), with a connector from the command to the agent. The skills row is omitted because this lane uses no skills."
    loading="lazy"
    width="920"
    height="190"
  />
  <figcaption>The <code>/ca:add-dep</code> lane by piece type: the command (gold) dispatches the reviewer agent (green), which clears the package before any install runs. This lane uses no skills.</figcaption>
</figure>

## Run the Command

Specify the package name and, when you know it, the exact version:

```text
/ca:add-dep zod@3.22.4
```

Without a pinned version, the reviewer evaluates the latest available. The version you supply here is the version that gets installed if the review clears, so pinning avoids drift between review time and install time.

## What the Reviewer Checks

`dependency-reviewer` reads `.codearbiter/security-controls.md` and `.codearbiter/tech-stack.md` before evaluating the package. It works through four areas:

**License.** The package's SPDX identifier must appear in the approved list (see below). The agent does not infer equivalence; the identifier must match.

**Provenance.** The package must resolve from an approved source. For npm projects, only `https://registry.npmjs.org` is permitted. A `git+` URL, a `file:` reference, or a plain `http:` source fails immediately, regardless of license.

**Supply-chain risk.** The agent checks maintenance signal: publish recency, ownership patterns, and known typosquat or dependency-confusion indicators.

**Stack fit.** The agent confirms the package is appropriate for the dependency manager and runtime described in `tech-stack.md`.

## The Repository's License Policy

The reviewer reads the allowed and denied SPDX identifiers from the target repository's
`.codearbiter/security-controls.md`. That project-owned policy wins; codeArbiter does not impose one
universal allowlist on every repository.

For orientation, the codeArbiter repository itself currently approves:

- MIT
- ISC
- Apache-2.0
- BSD-2-Clause
- BSD-3-Clause
- BlueOak-1.0.0
- CC0-1.0

A package outside your repository's approved list cannot be added without resolving the policy
decision or using a documented override. The reviewer does not have authority to silently expand
the list.

The codeArbiter repository also documents narrow package-specific mislabels in its own security
controls. Those exceptions do not transfer to another project unless that project's policy records
them too.

## The CVE Gate

Once license and provenance pass, the agent runs the audit command declared by
`.codearbiter/tech-stack.md`. In this repository that command is:

```text
npm audit --omit=dev --audit-level=critical
```

A CRITICAL advisory blocks the install unless the project's security controls contain a documented
justification. HIGH advisories are surfaced for user evaluation. The target repository's declared
command and policy are the source of truth; do not copy this npm command into a non-npm project.

## After Clearance

When the reviewer clears the package, the orchestrator surfaces the install command for your confirmation. Read it before approving. After the install runs, the manifest change and the lock file change are committed together. Committing one without the other is a gap the reviewer flags at PR time.

Verify the reviewed artifact actually landed:

1. Confirm the installed version matches the version in the review.
2. Inspect the manifest and lockfile diff together; no unrelated package should appear.
3. Re-run the repository's declared audit command.
4. Run the project's tests and type/lint checks.
5. At PR time, confirm the dependency reviewer evaluates the exact current diff rather than an
   earlier lockfile.

## When the Review Fails

A denied license or unresolved supply-chain concern blocks the install. The agent states the specific reason. From there:

- Choose an alternative package with an approved license.
- For a genuine license mislabel you can document, open an explicit review and record the decision in `overrides.log`.
- For a CRITICAL CVE, wait for a patched release or select a version without the advisory.

One important limit: no hook blocks a bare `npm install` run outside this command. The gate is orchestrator-enforced, not hook-enforced. Bypassing `/ca:add-dep` bypasses the review.

If you edit `package.json` or a lock file directly, the H-07 advisory fires after the write:

```text
[H-07] dependency manifest changed — route new packages through /ca:add-dep before committing.
```

This is advisory only. It does not block the write. The install gate depends on using the command in the first place.

## When Not to Use This Command

- **Removing a dependency.** Use `/ca:fix` or `/ca:feature` and describe the removal.
- **Updating an existing dependency as part of a code change.** Use `/ca:feature` or `/ca:fix`. Manifest changes reach the `dependency-reviewer` through the PR review at `/ca:pr`.
- **Researching a package without a plan to install it.** Use `/ca:btw`.

## Related

- [add-dep command reference](/reference/commands/add-dep/)
- [dependency-reviewer agent](/reference/agents/dependency-reviewer/)
- [Enforcement & Security](/enforcement/): H-07 advisory and the full gate catalog

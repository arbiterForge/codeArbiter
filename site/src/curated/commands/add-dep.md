---
entity: commands/add-dep
related: [agents/dependency-reviewer, review]
gates:
  - gate: dependency review
    when: before dependency adoption through this command
    effect: the dependency-reviewer must clear the package before the separately confirmed install; a bounded one-time inspection follows the explicit exception below
---

## What it does

Reviews a new or changed third-party dependency before adoption. The read-only
`dependency-reviewer` uses the target repository's `.codearbiter/security-controls.md` and
`.codearbiter/tech-stack.md` for license, source, maintenance, audit and stack requirements.
It produces findings without running installs or editing files.

For adoption, clearance is followed by confirmation of the exact install command. The installed
version must match the review; manifest and lockfile changes are delivered together. Unknown or
denied licenses, unapproved sources and unresolved supply-chain concerns must not be presented
as clearance. Follow the project's declared advisory thresholds and documented justifications.

The gate is orchestrator-enforced, not hook-enforced. There is no pre-bash rule blocking every
package-manager install outside this route; H-07 is a manifest-change advisory.

## Usage

```text
/ca:add-dep <package[@version]>
```

Omitting the version evaluates the latest available. Confirm the resolved exact version before
execution. Codex uses `$ca-add-dep`; Pi uses `/ca-add-dep`.

## One-time inspection

The command has a bounded ephemeral-tool exception, not a separate public command. It applies
only when the operator names that specific tool in the current session, it runs once for
inspection or analysis, and no manifest, lockfile or committed artifact changes. Adopting the
tool in scripts, hooks, CI or a base image does not qualify. Unclear scope takes full review.

Pin the exact version, use the approved registry, and confirm the exact command before running.
The current npm one-time path specifies `https://registry.npmjs.org`, excluding `git+`, `file:`
and non-TLS sources. Prefer a system temporary directory for cache and reports. This is not a
sandbox, a network restriction, or a guarantee about third-party code.

Verify manifest and lockfile state before and after, account for other artifact changes, and
report the command and output location. A manifest or lockfile write stops this path and routes
to adoption review. Existing dirty files need content comparisons, not only status-code checks.
An inspection approval does not authorize recurring execution or future adoption.

## Example

This is an illustrative request, not a captured run or a current package assessment:

```text wrap
Use jscpd once for this duplicate-code investigation without adopting it.
Propose a pinned command, registry and temporary output location.
Wait for my confirmation. Preserve project artifacts and verify the result.
```

No version or safety verdict is supplied by this example. The exact command still needs to be
resolved and confirmed. Follow [Add a dependency safely](/guides/adding-a-dependency/) for the
adoption-versus-inspection decision and before/after verification.

## When to reach for it

Use it for dependency adoption or the bounded one-time exception. Removing a dependency or
updating one as part of a code change belongs in `fix` or `feature`; dependency changes receive
review in the PR lane. Ask package questions directly when no execution is intended. The
legacy `btw` reference in the embedded source is not a prerequisite for a read-only question.

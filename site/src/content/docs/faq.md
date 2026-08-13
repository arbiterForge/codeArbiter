---
title: FAQ
description: "Honest answers to the objections a skeptical adopter raises before trying codeArbiter: blocking, bypass, uninstall, speed, data, teams, and misfitted gates."
journey:
  level: "Reference"
  time: "Lookup"
  outcome: "Resolve common operational questions and follow the linked workflow for deeper action."
  prerequisites: []
  proof: "The answer leads to a command, guide, or source-backed reference rather than a guess."
---

## Why would I let a plugin block my commits?

Because the class of mistake it blocks is exactly the kind that's easy to miss under normal
review pressure: a banned crypto primitive, a hardcoded secret, a direct push to `main`. The
[blocking gates](/enforcement/#blocking-commit-time-gates) are narrow and specific, not a general
"looks risky" heuristic, and each one names exactly what it caught and how to clear it. You don't
have to trust the framework's judgment in the abstract; the
[first protected repository](/getting-started/quickstart/) runs doctor's harmless live-fire probe
and requires the host to honor a real H-03 block.

## Can a determined session bypass a hook?

Yes. Hooks cover supported host tool calls, and the installed Git backstop covers matching commit
and push operations, but the repository owner ultimately controls the machine. They can uninstall
the plugin, remove hooks, use an external tool, or disable the repository.

The precise guarantee is that **every sanctioned bypass is logged**. `/ca:override` appends an
attributed line to `overrides.log`; the `mode --dangerous`/`--ops` posture flip records its own
entry and exit the same way. An out-of-band bypass is not
magically observable, and codeArbiter does not claim otherwise. Uninstalling leaves existing audit
files on disk, but the uninstall itself is not recorded unless the user records it. See the
[Hooks reference](/hooks/) for the boundaries each hook actually covers.

## What happens if I uninstall mid-feature?

`.codearbiter/` is a root-level directory, not inside `.claude/`, specifically so it survives an
uninstall: your specs, plans, decisions, and audit trail stay on disk. What you lose is
enforcement: no orchestrator persona, no gates, no statusline. Reinstalling and re-enabling
(`arbiter: enabled` still needs to be in `CONTEXT.md`'s frontmatter) picks back up against
whatever state is still there. See
[The `.codearbiter/` Directory Reference](/codearbiter-directory/#contextmd) for exactly what that
file controls.

## Does this slow me down?

Yes, at commit time, by design: that's when the blocking gates run. A test-first change, a
review chain, a commit gate: none of that is free. The honest trade is that the cost lands
predictably (at the gate, with a specific finding) instead of unpredictably (in production, or in
a review three weeks later). For low-risk work (docs, dependency bumps, reverts), the small
`/ca:chore` lane exists precisely because prose edits don't need the same TDD ceremony as feature
code. See [The Gated-Lane Model](/concepts/gated-lanes/) for how gates scale to the work.

## What data leaves my machine?

The blocking enforcement core sends nothing. Its Python guards are stdlib-only and make no network
calls while evaluating shell, write, crypto, secret, or migration gates.

Other features have narrower, documented network behavior:

- SessionStart may run a detached, read-only `git fetch` against the repository's configured
  remote for hygiene status. That uses normal Git transport and credentials.
- A once-daily, fail-silent update check sends an unauthenticated GET to GitHub's public Releases
  API. It sends no repository content.
- `/ca:sprint --farm` is opt-in and sends byte-capped, secret-redacted task context to the
  OpenAI-compatible endpoint you configure. It is inert without the flag and provider key.
- Installing plugins, Pi tags, or sandbox container images uses the network in the ordinary way
  for those package sources.

Your `.codearbiter/` state is repository data; codeArbiter has no hosted account or telemetry
service that receives it. See [Compatibility: Network Calls](/getting-started/compatibility/#network-calls)
for the source-level inventory.

## Can I use it on a team?

Yes. `.codearbiter/` is meant to be committed. The board, the decision log, the audit trail, and
the specs are shared project state, not personal configuration, so everyone working in the repo
sees the same gates and the same history. The persona and hooks activate per-session for whoever
has the plugin installed and the repo opted in. Core enforcement has no server component or
per-seat account; the optional farm uses the provider endpoint you configure.

## Can two users mix Claude Code and Codex in one repository?

Yes. This mixed-host workflow is why project state lives in `.codearbiter/` instead of a host-owned
settings directory. One user can run Claude Code while another runs Codex, or one user can alternate
between them. Both adapters read the same context, decisions, task state, and audit records. Install
and trust the appropriate plugin on each machine; do not initialize a second store. The
[verified parity boundary](/getting-started/claude-code-and-codex/) lists the intentional host
differences.

## What if the gates are wrong for my project?

Start with the project contracts: `security-controls.md`, `tech-stack.md`, and
`coding-standards.md` are hand-editable living documents that reviewers read before judging a
change. If a default pattern does not fit your stack, correct the governing contract or the gate
implementation instead of normalizing repeated bypasses.

`stage` in `CONTEXT.md` is a displayed maturity signal, not an enforcement tuning knob. Changing it
does not weaken or strengthen a gate. For a one-off exception,
[`/ca:override`](/guides/overriding-a-gate/) is the sanctioned, logged path: it's for individual
bypasses, not a substitute for fixing a gate that's structurally wrong for the project.

## What's the difference between an advisory and a blocking gate?

An [advisory](/glossary/#advisory) surfaces right after a write and never stops anything: it's a
nudge so a later blocking gate isn't a surprise. A [blocking gate](/glossary/#blocking-gate) stops
the tool call outright. codeArbiter reserves blocking for damage that lands the moment code
ships (a committed secret, a banned crypto primitive); things that only do damage once merged or
deployed (a bad CI workflow, an IaC manifest change) are advisory, with the real enforcement point
at PR review. See [Enforcement & Security](/enforcement/) for the full breakdown.

## Does codeArbiter write code for me, or just gate it?

Both, depending on the lane. `/ca:fix`, `/ca:feature`, and `/ca:sprint` route to author agents
that write code test-first; `/ca:refactor` restructures with proof of behavioral parity. But
codeArbiter never freelances past a slash command; see
[What Is codeArbiter](/overview/) for the request-to-ship flow, and
[The Gated-Lane Model](/concepts/gated-lanes/) for how each lane's gates scale to its risk.

## Where do I go if a rule from the docs conflicts with what a reviewer agent says?

`/ca:conflict`. codeArbiter never silently reconciles a conflict between persona, docs, and code.
It stops, presents both sides and the level at which they clash (security and audit-trail
correctness outranks maintainability, which outranks velocity; see
[What Is codeArbiter](/overview/)), and you decide.

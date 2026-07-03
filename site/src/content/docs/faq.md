---
title: FAQ
description: "Honest answers to the objections a skeptical adopter raises before trying codeArbiter: blocking, bypass, uninstall, speed, data, teams, and misfitted gates."
---

## Why would I let a plugin block my commits?

Because the class of mistake it blocks is exactly the kind that's easy to miss under normal
review pressure: a banned crypto primitive, a hardcoded secret, a direct push to `main`. The
[blocking gates](/enforcement/#blocking-commit-time-gates) are narrow and specific, not a general
"looks risky" heuristic, and each one names exactly what it caught and how to clear it. You don't
have to trust the framework's judgment in the abstract; the [Quickstart](/getting-started/quickstart/)
walks a real MD5 mistake getting caught at commit time so you can see the mechanism, not just a
claim about it.

## Can a determined session bypass a hook?

Yes, and that's by design, not a gap. Hooks fire at the Claude Code tool-call boundary and fail
closed: an ambiguous spelling of a destructive command is blocked, not guessed at. Direct `git`
usage outside the tool-call path is covered by a `.git/hooks` backstop
([Enforcement & Security](/enforcement/)). But a user can always uninstall the plugin, edit
`CONTEXT.md` to disable it, or run [`/ca:override`](/glossary/#override). The actual design goal
isn't that bypass is impossible. It's that **every bypass is logged**. An override appends a
permanent line to `overrides.log`; uninstalling removes the enforcement, not the record that it
was there. See the [Hooks reference](/hooks/) for what each hook actually checks.

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

None, from the enforcement hooks themselves: they're Python, stdlib-only, and the code that
actually blocks/reminds/warns (`pre-bash.py`, `pre-write.py`, `pre-edit.py`, `post-write-edit.py`,
the crypto/secret/migration gates) makes no network calls; this was verified directly against the
hooks' imports, not assumed. There is one narrow exception, separate from enforcement: a
once-daily, off-hot-path check against GitHub's public releases API to notify you when a newer
plugin version exists. It sends no project data, just an unauthenticated GET to a public
endpoint, and it's fail-silent (a network error just means no notice, never a broken session).
Everything else (your code, your `.codearbiter/` state, your commit history) stays local.

## Can I use it on a team?

Yes. `.codearbiter/` is meant to be committed. The board, the decision log, the audit trail, and
the specs are shared project state, not personal configuration, so everyone working in the repo
sees the same gates and the same history. The persona and hooks activate per-session for whoever
has the plugin installed and the repo opted in; there's no server component and no per-seat
account to manage.

## What if the gates are wrong for my project?

Two knobs exist before you'd reach for a bypass. First, `stage` in `CONTEXT.md`'s frontmatter is a
maturity signal the project can carry; see
[The `.codearbiter/` Directory Reference](/codearbiter-directory/#contextmd). Second,
`security-controls.md`, `tech-stack.md`, and `coding-standards.md` are hand-editable living docs
that every reviewer agent reads before judging a change. If a default pattern doesn't fit your
stack, that's the place to correct it, not the gate. For a one-off exception,
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

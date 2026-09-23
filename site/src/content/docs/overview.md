---
title: What Is codeArbiter
description: How codeArbiter orchestrates shared gated workflows in Claude Code, Codex, and Pi.
journey:
  level: "Foundation"
  time: "6 minutes"
  outcome: "Explain the command-to-skill-to-agent flow and choose the next learning module."
  prerequisites: []
  proof: "You can identify who routes, who implements, who reviews, and who resolves a gate."
---

codeArbiter coordinates governed development inside Claude Code, Codex, and Pi. You describe the
work; the owning lane brings in the context, authoring, tests, reviews and decision boundaries
that work needs. Project records live in your repository rather than depending on one chat.

## What you receive

Start with the result, not the catalog. A greenfield project produces an architecture breakdown,
phased build plan and task backlog for your review. Existing source produces inspected project
context instead. A full feature produces a specification and an execution plan; a small change
uses a lighter confirmed mini-spec. Decisions and audit records retain the reasons and exceptions.

The [product tour](/product-tour/) lets you inspect actual native-rendered draft documents and
runnable example tests. The [artifact model](/concepts/artifacts/) explains which record owns what.
These examples are labelled fixtures, not evidence that your installed package has been verified.

## codeArbiter Holds the Gates; You Hold the Decisions

Enforcement and judgment are distinct. Some protections refuse a supported tool operation;
other reviews depend on routing through the owning lane. The product does not make an external
editor or an unrestricted machine owner unable to bypass it. Read [Enforcement](/enforcement/)
for the actual boundaries instead of treating every instruction as a mechanical block.

Under an autonomous sprint, approved non-hard choices can use SMARTS and be recorded. Missing
user authority, security boundaries, irreversible operations and other hard gates remain stops.
Approval of an architectural decision is not proof that it was implemented or verified.

## How a Request Flows

1. **Describe the outcome.** State the intended behavior, scope, constraints and spending limits.
   Explicit commands are available, but a clear request does not require command ceremony.
2. **Review the definition.** The owning lane clarifies the problem and exposes genuine unknowns.
   You review the relevant artifacts and make decisions that require your authority.
3. **Implement and verify.** The workflow selects the roles needed for the change, connects tests
   to the requirements and obtains review. A passing test alone is not complete delivery.
4. **Resolve stops.** A gate can require repair, a current decision or fresh evidence. Autonomous
   work can recover within its approved scope, but cannot manufacture missing user authority.
5. **Commit and propose delivery.** Work follows the governed commit and PR path. Publication and
   merging retain their own authorization boundaries.

<figure class="ca-diagram">
  <img src="/diagrams/lane-flow.svg" alt="A request reaches its owning lane, clears the relevant gate and proceeds to the governed shipping boundary." loading="lazy" />
  <figcaption>The internal route serves a human outcome: defined work, inspected evidence, and an authorized delivery boundary.</figcaption>
</figure>

Follow [Complete one feature](/guides/first-feature/) for a continuous example rather than trying
to learn every internal skill before starting.

## One Core, Three Host Adapters

The governance adapters are `ca` for Claude Code, `ca-codex` for Codex, and `ca-pi` for Pi.
They share the policy core and repository-owned `.codearbiter/` records, while entry spelling,
trust, role execution and supported environments differ. Pi remains a Feature Forge `preview`.
The separate `ca-sandbox` plugin is infrastructure, not a fourth governance host.

Claude Code dispatches plugin agents. Codex uses host-provided agent threads with packaged role
instructions. An inline fallback is allowed only where the owning workflow permits it and isolation
is not mandatory. Pi launches hardened child processes through its trusted parent. These mechanisms
are not interchangeable guarantees; the host-specific evidence below states their qualified limits.

The [compatibility matrix](/getting-started/compatibility/) and the dated
[Claude Code + Codex evidence](/getting-started/claude-code-and-codex/) own exact support details.
Do not infer a release guarantee from current development documentation or identical-looking
commands. The [Pi guide](/getting-started/pi/) owns its installation and parent-process boundary.

## Context Minimization

Internal skills, role instructions and detailed references load when the owning workflow needs
them. You do not need to choose an author agent or remember the internal call graph for ordinary
work. Public command references remain available for explicit invocation and exact lookup.
Repository context can enter your configured host or model provider; local storage is not a
claim that no data ever leaves the machine. See [Trust & Lifecycle](/trust/).

## The Lanes

Choose a user job: initialize a project, build a feature, repair a defect, review a change,
record a decision, or release your own project. [Guides](/guides/) groups those tasks in working
order. The [Reference](/reference/) preserves exact operations and compatibility routes without
requiring you to treat every alias or internal protocol as a new thing to learn.

To begin, [choose your host](/getting-started/choose-your-host/), install and trust its adapter,
initialize a disposable repository, then [prove enforcement](/getting-started/quickstart/).
For deeper practice, use [Arbiter Academy](/academy/) with its published lesson prerequisites.

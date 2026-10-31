---
title: What is Code Arbiter?
description: "What is Code Arbiter? Open-source agentic coding governance for Claude Code, Codex, and Pi, with development gates and repository-owned project records."
journey:
  level: "Foundation"
  time: "6 minutes"
  outcome: "Explain the command-to-skill-to-agent flow and choose the next learning module."
  prerequisites: []
  proof: "You can identify who routes, who implements, who reviews, and who resolves a gate."
---

codeArbiter is an open-source governance layer for Claude Code, Codex, and Pi. It stops an AI coding
agent at the gates you care about (tests, reviews, security checks, decisions) and keeps the record
of that work in your repository, in `.codearbiter/`.

## What you receive

Ask for an outcome and you get the documents a careful team would produce for it:

- **A new project** gets an architecture breakdown, a phased build plan and a task backlog to review.
- **An existing codebase** gets inspected project context instead.
- **A feature** gets a specification and an execution plan; a small change gets a short confirmed mini-spec.
- **Every decision and exception** is recorded with its reason.

The [product tour](/product-tour/) shows real draft documents and runnable tests from one example,
and the [artifact model](/concepts/artifacts/) explains which record owns what.

## codeArbiter Holds the Gates; You Hold the Decisions

codeArbiter enforces; you decide. A gate stops a supported tool call before it runs, such as a
commit without passing tests or a broad `git add`. Choices that need your judgment, such as approving
a plan or accepting a trade-off, come back to you. In an autonomous sprint, routine choices are
scored with SMARTS and logged so you can review them later, while anything that needs your authority
still stops and asks. [Enforcement](/enforcement/) lists exactly what is blocked and where the limits are.

## How a Request Flows

1. **Describe the outcome.** State the behavior you want, the scope and any limits. You can use a
   command such as `/ca:feature`, but a clear request works too.
2. **Review the definition.** The owning lane clarifies the problem and asks only what it cannot
   decide for you.
3. **Implement and verify.** Tests are written against the requirements, the code is reviewed, and
   failures are fixed before work moves on.
4. **Resolve stops.** A gate may ask for a fix, a decision or fresh evidence. Work continues once it
   is satisfied.
5. **Commit and open a pull request.** Changes go through the governed commit and PR path. Merging
   and publishing stay your call.

<figure class="ca-diagram">
  <img src="/diagrams/lane-flow.svg" alt="A request reaches its owning lane, clears the relevant gate and proceeds to the governed shipping boundary." loading="lazy" />
  <figcaption>Every request reaches its owning lane, clears the gates that apply, and ends at a pull request you approve.</figcaption>
</figure>

[Complete one feature](/guides/first-feature/) walks through this end to end.

## One Core, Three Host Adapters

codeArbiter is one governance product with three host adapters: `ca` for Claude Code, `ca-codex` for Codex,
and `ca-pi` for Pi. They share the same policy core and the same `.codearbiter/` records, so a project
can move between hosts. Command spelling differs (`/ca:feature` in Claude Code, `$ca-feature` in
Codex, `/ca-feature` in Pi). Claude Code and Codex are stable; Pi is a Feature Forge `preview`.

The [compatibility matrix](/getting-started/compatibility/) lists exact requirements, and
[Choose your host](/getting-started/choose-your-host/) helps you pick one.

<details class="ca-evidence">
<summary>Limits and evidence: how each host runs reviewers</summary>

Claude Code dispatches plugin agents. Published releases from 0.7.5 include the complete packaged
resource charter set for that release for Codex host-provided agent threads, with static-package
and route-closure checks at release. A bounded 0.9.4 receipt records one exact installed-charter
review. A bounded inline fallback is allowed only where the canonical workflow explicitly permits
it and isolation is not mandatory. Pi launches hardened child processes through its trusted parent.
These mechanisms are not interchangeable guarantees; the
[Claude Code + Codex evidence](/getting-started/claude-code-and-codex/) page records what has been
verified on each host, and the
[typed-artifact authority matrix](/guides/review-artifacts/#check-your-hosts-authority-capability)
shows which hosts can verify and review structured HTML documents.

The Claude Code marketplace also carries `ca-sandbox`, an infrastructure plugin rather than a fourth
host. The Codex marketplace carries `ca-codex`. Pi installs from npm or from pinned Git tags; the
[Pi guide](/getting-started/pi/) covers its trust boundary. Product tour examples are labelled fixtures, not a check of your installed package.

</details>

## What Stays on Your Machine

Skills, role instructions and reference material load only when a workflow needs them, so you do not
need to learn the internals first. Your repository context still goes to whichever host and model
provider you use; codeArbiter adds no telemetry service. See [Trust & Lifecycle](/trust/).

## Where to Go Next

[Choose your host](/getting-started/choose-your-host/), [install it](/getting-started/install/), and
[protect your first repository](/getting-started/quickstart/). Then [complete one feature](/guides/first-feature/).
[Guides](/guides/) are grouped by task, and the [Reference](/reference/) holds every exact command.
For hands-on practice, [Arbiter Academy](/academy/) adds verified exercises.

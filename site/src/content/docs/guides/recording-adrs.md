---
title: Record an Architecture Decision
description: "Create, supersede, and monitor user-attributed Architecture Decision Records without rewriting prior decisions."
journey:
  level: "Practitioner"
  time: "10 minutes"
  outcome: "Create, inspect, and supersede an attributable ADR without rewriting history."
  prerequisites:
    - "An initialized repository"
    - "A durable architectural choice"
  proof: "The ADR and decision log agree, and a superseding record names the full prior filename stem."
---

Use this guide when a choice will shape later implementation: a storage model, trust boundary,
public contract, dependency policy, or other decision future work must respect. The result is a
numbered record under `.codearbiter/decisions/`, attributed to the person who made the call and
linked to the paths it governs.

<figure class="ca-diagram">
  <img
    src="/codeArbiter/diagrams/lane-adr.svg"
    alt="The architecture decision lane from a decision prompt through numbered ADR authoring, user attribution, validation, and the decision log."
    loading="lazy"
  />
  <figcaption>The ADR lane gives one consequential choice a numbered, user-attributed, forward-only record.</figcaption>
</figure>

<div class="ca-host-syntax">
  <strong>Host syntax:</strong> Claude Code uses <code>/ca:adr</code>; Codex uses <code>$ca-adr</code>;
  Pi uses <code>/ca-adr</code>. Examples below use Claude Code syntax.
</div>

## Before you start

- Set `git config user.email`. The record and decision ledger use that identity.
- Be ready to decide the material trade-off. codeArbiter can structure and challenge the options,
  but it cannot attribute its own preference to you.
- If the question is still exploratory, use `/ca:btw` or a spike first. An ADR records a decision;
  it is not a scratchpad.

## Create a decision

Invoke the command with a short title:

```text
/ca:adr "Store durable workflow state in the repository"
```

The decision-lifecycle skill gathers context, the options considered, the decision, consequences,
and the paths the decision governs. Any fact only you can supply becomes a numbered
`[CONFIRM-NN]`; it is not guessed.

Review the proposed record. On approval, codeArbiter writes:

```text
.codearbiter/decisions/0017-store-durable-workflow-state.md
```

The number is gap-free and the slug is derived from the title. The companion
`.codearbiter/decisions/decision-log.md` receives the corresponding ledger entry.

## Verify the result

Open the new ADR and confirm:

- the status is `accepted` only if you explicitly accepted it;
- `decided-by` matches your Git identity;
- `governs` lists the intended path globs, not the whole repository by accident;
- the options and consequences reflect the choice you made; and
- any `[CONFIRM-NN]` still present also appears in `.codearbiter/open-questions.md`.

Run `/ca:adr-status --adr 17` (Codex: `$ca-adr-status --adr 17`) to read the decision's current
health and any challenge result.

## Supersede a decision

Do not edit history to make an old ADR look current. Create a new ADR and tell the command which
accepted decision it replaces:

```text
/ca:adr "Move durable workflow state to a signed event store"
```

The new record receives `supersedes: 0017-store-durable-workflow-state`, using the prior ADR's full
filename stem rather than an ambiguous bare number. The earlier file is left byte-for-byte unchanged.
Supersession is a forward-only chain: the newest record names what it replaces, and the decision
ledger records the transition.

Verify the chain with:

```text
/ca:adr-status --adr 17
/ca:adr-status --adr 24
```

The first report should identify the newer governing decision; the second should name `0017` as its
predecessor.

## Common stops and recovery

| Stop | Why it happens | What to do |
|---|---|---|
| Git identity is missing | Decisions require real attribution | Set `git config user.email`, then invoke the command again |
| A `[CONFIRM-NN]` is unresolved | Only you can supply the missing fact | Answer it, or leave the ADR proposed until you can |
| The number or file already exists | Another decision won the next sequence number | Re-run through `/ca:adr`; never hand-renumber files |
| A direct edit is blocked | ADR files have a protected authoring lane | Use `/ca:adr` to create a replacement or superseding record |

## Next steps

- Read [ADRs and the Decision Log](/concepts/adrs/) for the enforcement and JIT-context model.
- Inspect the exact [`adr` command](/reference/commands/adr/) and
  [`decision-lifecycle` skill](/reference/skills/decision-lifecycle/).
- Use [Auditability](/concepts/auditability/) to see how decisions appear in a range audit.

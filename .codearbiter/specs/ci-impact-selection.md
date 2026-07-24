# CI impact selection and evidence design

## Purpose

Keep every sensible validation contract while making CI select only work that
the repository can prove is relevant. Give Codex, Claude, and a human
maintainer a concise explanation of what ran, why it ran, what was advisory,
and how to reproduce a failure.

The initial release is shadow mode. It does not skip an existing check. It
collects evidence that supports a later, conservative selection policy.

## Current state

`ci.yml` uses path filters to select plugin lanes, but `core/**` conservatively
fans out to multiple hosts. The Pi adapter lane runs a three operating system by
two supported Pi version matrix. The upstream Pi latest canary is advisory and
currently runs on Pi changes. A separate GitHub default CodeQL configuration
also scans repository languages, while the in-workflow Pi CodeQL job runs the
Pi-specific `security-extended` contract and high-severity gate.

The existing CI workflow does not cancel an obsolete run when a newer commit is
pushed to the same pull request. The docs and checked-in CodeQL workflows do.

## Design principles

1. Skip only when the dependency map proves irrelevance.
2. Ambiguity, a map error, or an unmapped path expands to the broad affected
   lane. It never produces a silent skip.
3. The map is declared and tested. It is not an inference made by an agent at
   run time.
4. CI check names describe a contract. They do not use generic activity labels
   such as Build when a job actually combines several validations.
5. The planner writes evidence for agents and maintainers without adding noisy
   pull request comments.

## Dependency map

The repository owns a version-controlled impact manifest. Its graph contains
source groups, generated artifacts, shipped payloads, validation contracts, and
platform or runtime variants.

Each edge has an explicit relationship:

```text
source group -> generated artifact -> validation contract
```

Examples:

```text
core/pysrc/** -> shared hook payloads -> CA, Codex, and Pi hook checks
Codex-only surface fragment -> Codex rendered surface -> Codex surface check
plugins/ca-pi/** -> Pi runtime payload -> Pi matrix, security, package checks
```

Host-specific surface metadata, plus generator output, determines whether a
surface change affects one host or every host. A source group that lacks a
complete path to an artifact or contract is unknown and selects the broad lane.

The planner compiles the manifest into both a Markdown job summary and an
`impact.json` artifact. In shadow mode, the receipt says which checks would
have been selected or skipped. Existing workflow behavior remains unchanged.

## Check presentation

Every owned check name follows this display grammar:

```text
[LANE ] | [SCOPE] | Contract  <typed dimensions>
```

`LANE` uses a fixed five-character vocabulary: `CHECK`, `WATCH`, `GATE`, and
`SHIP`. `SCOPE` uses a fixed vocabulary: `REPO`, `CORE`, `CA`, `CDX`, `PI`, and
`SBX`. The contract is a controlled name such as Adapter contract, Hook
contract, Generated surface, Security analysis, or Merge readiness. Dimensions
are optional and typed, in a fixed order.

Examples:

```text
[CHECK] | [PI  ] | Adapter contract  <os: Windows · runtime: Pi 0.80.5>
[CHECK] | [CORE] | Hook contract  <os: macOS>
[CHECK] | [CDX ] | Reference graph
[WATCH] | [PI  ] | Upstream compatibility  <runtime: npm latest>
[GATE ] | [REPO] | Merge readiness
```

GitHub renders check names in a proportional font, so the padded tags create a
stable visual cell pattern without claiming pixel-perfect alignment.

## Receipt and failure behavior

The receipt is written to the workflow job summary and stored as `impact.json`.
It does not post a pull request comment by default. Every selected contract
records its identity, reason, required or advisory status, variant, and a
reproduction command when one is available.

```text
[CHECK] | [PI  ] | Adapter contract  <os: Windows · runtime: Pi 0.80.5>
Reason: plugins/ca-pi/tools/src/extension.ts -> Pi runtime payload
Reproduce: npm --prefix plugins/ca-pi/tools test -- <targeted suite>
```

If map evaluation fails, a path is unmapped, or generator evidence disagrees
with the map, the receipt reports the condition and selects the broad lane. The
planner must not silently omit validation.

## Immediate improvement

Add concurrency cancellation to `ci.yml`, scoped to the workflow and pull
request or ref. A superseded run is obsolete once a later commit on the same
pull request starts a new run. The new run validates the current pull request
head. This reduces wasted matrix work without changing coverage for the current
commit.

Do not consolidate the default GitHub CodeQL scan with the Pi CodeQL contract.
They overlap on JavaScript and TypeScript but have different scopes and
responsibilities. Do not alter the Pi matrix or canary cadence until shadow-mode
evidence proves a narrower rule.

## Validation plan

The implementation must prove the map and its fallback behavior with fixture
diffs:

1. A Codex-only surface change predicts Codex checks and does not predict Pi.
2. A shared Python core change predicts every dependent host check.
3. A Pi runtime payload change predicts the Pi matrix, package, and security
   contracts.
4. An unknown path selects the broad lane and is visible in the receipt.
5. Generator-reported outputs agree with the manifest edges.
6. Every emitted check name satisfies the display grammar and vocabulary.
7. Shadow-mode output records predicted skips and observed job durations.

The planner itself has no authority to skip checks in the first release. A later
selection design requires historical shadow evidence, explicit map coverage,
and a separate approved change.

## Out of scope

This design does not introduce Semgrep or OpenGrep. Static taint analysis is a
separate security decision that needs a threat-modelled source and sink set,
seeded vulnerable fixtures, and a false-positive policy before it becomes a
merge requirement.

This design does not add AI triage or automatic remediation. It gives an agent
the evidence required to diagnose and reproduce a failure.

# Merge and completeness checklist

This checklist is intentionally uncompleted. Supplied author review and local test results do not check these boxes for the merging reviewer.

## Preserve the contract

- [ ] Verify `design/ORIGINAL-CONTRACT.json` against the included reference spec, plan, schemas and tools. Review the documented reference and runtime version boundaries.
- [ ] Read all normative sections, not just the criterion table. Map every original AC and task to actual code and behavioral evidence; inspect counterexamples and unmet clauses.
- [ ] Resolve schema 0.2.0 → implementation 0.3.x differences and other documented deviations explicitly. Verify the original safe-integer canonical profile with conformance vectors; do not misclassify it as a broader-number deviation or weaken the original documents to close a gap.

## Respect codeArbiter

- [ ] Read the actual checkout's instructions, CONTEXT, tech stack, security rules, accepted ADRs and authoritative CI. Verify the structured-artifact architecture ADR through the real lifecycle; it is Accepted/Planned here and does not claim implementation, verification, or rollout authority.
- [ ] Inventory every spec/plan producer and consumer, including `/feature`, `/sprint`, alternative authoring, TDD, execution, resume, governing-spec injection, farm/canary and commit gates.
- [ ] Change canonical shared source, regenerate all descriptor-selected hosts, and prove parity. Do not hand-edit generated outputs or invent another host registry.
- [ ] Prove no added public command, agent, skill registration, persistent tool or startup schema load. The new package AGENTS.md must not replace the repository AGENTS.md.
- [ ] Exercise the existing governed execution and real authority-event paths. A cooperative receipt's self-reported identity is not independent evidence of a human decision.

## Test the behavior, not just its shape

- [ ] Run both sets of retained regression tests and fresh behavioral checks. Confirm required named tests actually execute; do not accept zero-test exits or skip counts.
- [ ] Exercise full spec-to-plan authoring and both workflow entry paths in real hosts, including interrupted work, current binding, provisional dependencies, atomic scope acceptance and stale-input revalidation.
- [ ] Verify the input policy covers all declared source/test paths and actual dependencies, toolchain/environment inputs, directory membership and approved output exclusions. Included symlinks must fail; excluded links must never be followed.
- [ ] Exercise conflict/replay, process interruption, repair, single-file export, legacy pair conversion and rollback, preserving intervening edits and original bytes.
- [ ] Implement and test actual HTML farm projection, RED-test binding, canary admission, authorized model enrichment and final execution seals. A prose “blocked” instruction is not a runtime guard.
- [ ] Qualify every declared native target. Linux and Windows have local native evidence; macOS still requires exact-host CI. Do not mix native Windows Git and WSL Git on one physical checkout.
- [ ] Run current mandatory repository/CI tests. Core changes also trigger the Pi tools checks in the pinned tech-stack; read current CI if it has changed. Preserve release versions, changelogs, promotion, licensing and package/resource closure.

## Merge disposition

- [ ] State **full feature**, **foundation-only**, or **blocked**. A foundation-only merge must keep rollout disabled and leave all unmet original obligations tracked.
- [ ] Record independent findings and evidence against all 26 criteria and 24 tasks. No original task is pre-marked ACCEPTED by this package.
- [ ] Pass genuine applicable governance and review gates before any commit/push/release. Synthetic fixture approvals and historical reports are never transferable.

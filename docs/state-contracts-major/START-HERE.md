# codeArbiter major state-contract program

## Receiving-agent instruction

Execute this corpus against **arbiterForge/codeArbiter**. Start on a dedicated integration branch named **major/state-contracts** and keep this program there until all implementation, migration, recovery, documentation and qualification acceptance criteria are complete. Short-lived task branches target that integration branch. The final promotion is one integrated change to main, followed by the new major product release through the repository's sanctioned publisher.

This packet is an implementation handoff. The source audit is complete and frozen; the proposed changes are not implemented by the packet. All task statuses start PLANNED and all new qualification evidence starts NOT_RUN. Do not report a green plan validator as product test success.

## Read in this order

1. `DECISIONS.md`: B's settled decisions and the remaining scoped choices.
2. `PROGRAM.md` and `BRANCH-AND-RELEASE.md`: scope, branch isolation, CI bootstrap, version handling and exact-artifact publication barrier.
3. `SMARTS-PROGRESS-EVIDENCE.md`: discuss the material progress/evidence alternatives with B before implementing that semantic migration. Independent fixes continue.
4. `PI-DELEGATION.md` and `INTERRUPTION-RECOVERY.md`: concrete authority and recovery designs.
5. `IMPLEMENTATION-TASKS.md`: dependency-ordered tasks, finding IDs, source paths, tests and completion evidence.
6. `TEST-AND-QUALIFICATION.md`, `MIGRATION-AND-ROLLBACK.md`, `ADR-PROPOSALS.md` and `CLAIM-REGISTRY-DELTA.md`.
7. `AGENT-ROLES.md`, read `EXECUTION-RECORDS.md`, then initialize `execution/CHECKPOINT.md` from the template.

Use `contracts/tasks.json`, `contracts/finding-dispositions.json`, `contracts/machine-coverage.json`, `contracts/transition-coverage.json` and `contracts/scenarios.json` as the machine-readable corpus. The complete original state table and evidence are under `audit/`.

## First executable actions

- Inspect the actual repository origin, local status, worktrees, branch heads, repository instructions, and live main/tag identities. Confirm exact owner casing `arbiterForge` and repo `codeArbiter` before writes.
- Run `python3 tools/validate_packet.py` from the extracted corpus root. This validates the packet only.
- If the integration branch already exists, inspect/resume it. Do not reset or overwrite it. If absent, create it from the newly inspected base in a clean worktree without disturbing unrelated work.
- Copy the planning corpus into a documented branch-owned location, preferably `docs/state-contracts-major/`. Do not place ad hoc files into native-owned artifact directories.
- Complete P-00/P-01/P-02. Establish actual integration CI before accepting task PRs. Then dispatch independent owner work in parallel.
- Hold the SMARTS discussion for D-PROGRESS and resolve the narrower D-HIGH/D-GOV-PRETAG choices with B. These are scoped decisions, not permission prompts for every ordinary action.

## Operating rules

The explicit user decisions persist. Do not ask B to reapprove dependent-only conflicts, corrected resubmission, functional scoped Pi authorship, nonblocking durable recovery, or branch isolation. Preserve genuine host/user authority and repository protections. If a needed permission or runtime is unavailable, record exactly what is unavailable and continue independent work.

Read the actual owning file and caller/callee before changing it. Audit rows are an index, not a substitute for source. Revalidate any source that changed after the pinned audit commit. Challenge comments and ADR claims against implementation and evidence. Preserve source versus package versus installed-host qualification distinctions.

Every completed task must include the actual diff, exact source SHA, meaningful executed tests, remaining limits and rollback boundary. Every checkpoint identifies the next concrete task. Never silently downgrade a required feature to a TODO, optional item, read-only mode, unavailable test or documentation-only promise to finish the program.

The program's required final outcome is the entire accepted scope implemented and tested before major publication. Follow the release sequence in `BRANCH-AND-RELEASE.md`; current main CI automatically triggers publication, so exact-artifact readiness must be enforced before the first public effect.

Keep the intake specifications immutable. Record live progress, later decisions, new findings and executed evidence under execution/ as described in EXECUTION-RECORDS.md. On resume, current Git state and those records take precedence over historical PLANNED/NOT_RUN labels.

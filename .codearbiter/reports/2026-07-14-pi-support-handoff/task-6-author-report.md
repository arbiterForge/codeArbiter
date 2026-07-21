# Task 6 author report - hardened Pi child isolation

## Obligation checklist (written before production edits)

- [ ] O1 - Build the child environment from explicit Windows, macOS, or Linux runtime allowlists; reject unknown platforms and providers.
- [ ] O2 - Admit only the selected provider's reviewed Pi 0.80.5/0.80.6 variables, retain only opaque host-auth location/runtime variables, and remove `FARM_API_KEY` plus `CLAUDE_CODE_OAUTH_TOKEN` after all merges.
- [ ] O3 - Keep task/prompt content out of argv, environment, and files; build the exact discovery-disabled RPC argv with absolute Node, Pi CLI, child extension, skill, charter, and cwd identities.
- [ ] O4 - Launch the absolute Node executable with an argv array, `shell: false`, an explicit cwd, and a minimal child environment; validate every executable/resource as a canonical real file before spawning.
- [ ] O5 - Send one bounded strict RPC `prompt` request on stdin with a random correlation ID and one-use nonce; never derive identifiers from task content.
- [ ] O6 - Accept only bounded, strict JSONL response/event schemas and keys; reject malformed/oversized protocol data with fixed redacted diagnostics that never echo raw JSONL, provider errors, task text, or credentials.
- [ ] O7 - Return inline/failure behavior only as terminal `degraded`; failed isolation can never be represented as promoted or completed child execution.
- [ ] O8 - Generate the role catalog from canonical agent frontmatter with exact author/reviewer classification, Pi tool mapping, generated charter path, and explicit skill paths; reject unknown or malformed roles.
- [ ] O9 - Make the child adapter enforcement-only: install Task 4 wrappers/notices and the bootstrap/unknown-tool guard, with no public aliases, dispatch tool, farm tool, recursive orchestration, or project-trust grant.
- [ ] O10 - Treat an ambient `CODEARBITER_SUBAGENT=1` marker without a one-use stdin nonce handshake as unhealthy and fail closed; consume a valid nonce once and keep H-03 enforcement active.
- [ ] O11 - Prove fresh child PIDs and contexts, no session file, no ambient discovery, exact tools/resources, and no recursive registration through isolated fixtures and a deterministic live-child harness.
- [ ] O12 - Pin and parse Pi 0.80.6 help, compare the reviewed isolation flags/provider variables with 0.80.5 evidence, and fail fixture-only verification on drift.
- [ ] O13 - Do not read or stat Pi auth stores; structural tests must reject auth-store filesystem access from Task 6 runtime sources.
- [ ] O14 - Preserve all pre-existing Batch 1/2 behavior, deterministic builds, branch identity, and an empty index; do not begin Task 7.

Stage 2 coverage expectations apply. The slice follows ADR-0014 and the `Pi adapter and child-process security` control. No network, database, dependency, or unauthenticated HTTP endpoint is introduced.

## SMARTS decisions

### T6-D01 - one-use stdin nonce handshake

**Verdict: choose (a), a private bounded internal RPC handshake consumed before the unchanged task prompt. Strength: strong. Confidence: high.**

| Option | Scalable | Maintainable | Available | Reliable | Testable | Securable | Strength |
|---|---|---|---|---|---|---|---|
| (a) Private internal RPC handshake | One protocol works for every role and later bounded orchestration mode. | Isolated helper and private command use Pi's stable RPC seam. | Supported in both approved Pi versions without another dependency. | Ack-before-task prevents execution after handshake failure. | Fake-spawn and live tests prove ordering, one use, and blocked failure. | Keeps task unchanged on stdin and nonce out of argv/environment. | Strong |
| (b) Prompt-prefix stripping | Every task needs host-specific framing and cleanup. | Depends on an event that cannot replace the submitted prompt. | Event exists, but required prompt removal does not. | Caught handler errors can continue with the prefixed task. | Cannot prove the model never receives the prefix. | Exposes control framing and weakens fail-closed behavior. | Weak |
| (c) Argv/environment nonce | Simple across roles but expands observable launch state. | Easy implementation, permanent contract violation. | Available on all platforms. | Launch succeeds, but nonce validity does not protect task ordering. | Channel assertions are easy. | Violates the approved minimal environment and argv secrecy boundary. | Rejected |

The internal command is isolation machinery, not a `/ca-*` alias or orchestration surface. It accepts one bounded nonce, enables enforcement for one fresh child process, and cannot dispatch or recurse. The sprint-log append is currently H-05-blocked for Codex `apply_patch`; this task report is the immediate durable audit location and no gate bypass is used.

### T6-D02 - inherited anonymous capability pipe

**Verdict: choose an inherited anonymous fd 3 capability pipe carrying the runner-generated expected nonce; stdin presents the same nonce in the private handshake. Strength: strong. Confidence: high.**

| Option | Scalable | Maintainable | Available | Reliable | Testable | Securable | Strength |
|---|---|---|---|---|---|---|---|
| (a) Anonymous fd 3 capability plus stdin presentation | One fixed channel works for every generated role. | Capability read and launch write stay isolated in runner/child helpers. | Node extra stdio pipes are supported on approved Windows, macOS, and Linux runtimes. | Exact equality binds readiness to the spawning runner; missing, malformed, mismatched, and replayed values fail closed. | Fake spawn, pipe-reader, mismatch, replay, and later live negative cases cover both ends. | Nonce never enters argv, environment, task, session, or disk. | Strong |
| (b) Any well-shaped stdin nonce | No extra channel, but every process with the marker can manufacture readiness. | Less code but no meaningful parent binding. | Available wherever RPC stdin works. | Shape alone cannot distinguish an ambient marker from a validated launch. | Easy to test, unable to prove spawning-parent possession. | Leaves the ambient-marker reuse boundary open. | Weak |
| (c) Argv/environment/file capability | Simple transport but creates a persistent or observable launch channel. | Adds cleanup and redaction obligations. | Platform support varies for safe temporary files. | Values can be inherited, inspected, or left behind. | Presence tests are simple. | Violates the approved nonce secrecy and minimal-environment boundary. | Rejected |

The public `runPiChild(request, signal)` entry accepts no dependency or validation override. Tests replace Node and runtime modules through Vitest module mocks while exercising that public two-argument entry. There is no `runner-core.ts`, testkit, dependency-bearing spawn helper, or third public argument in the shipping tree.

### T6-D03 - explicit canonical role metadata

**Verdict: add explicit `classification` and `pi-skills` fields to every canonical agent frontmatter block, then strip only those Pi-only fields from Claude/Codex renders. Strength: strong. Confidence: high.**

| Option | Scalable | Maintainable | Available | Reliable | Testable | Securable | Strength |
|---|---|---|---|---|---|---|---|
| (a) Explicit canonical metadata | New roles declare intent at the source of truth. | One generator validates names, classifications, skill names, duplicates, and resources. | Uses the existing frontmatter/generator seam. | No suffix or prose guess can silently change authority. | Full 28-role bijection, exact mappings, resource existence, and negative fixtures are deterministic. | Author/reviewer authority and injected routines are reviewable data. | Strong |
| (b) Infer from role-name suffixes | Naming conventions must remain globally frozen. | Special cases accumulate as roles evolve. | Easy initially. | `author`, `reviewer`, mapper, grader, and aggregator semantics are not suffix-complete. | Tests can only lock heuristics, not intent. | Misclassification can grant write-capable author behavior. | Weak |
| (c) Parse charter prose | Reuses text but couples authority to wording. | Copy edits become schema migrations. | Parser is technically available. | Natural-language ambiguity fails unpredictably. | Fixtures are brittle and incomplete. | Security classification becomes implicit and hard to audit. | Rejected |

All 28 canonical agents now carry explicit fields. The Pi generator maps declared routines to `routines/<name>/SKILL.md`, verifies every rendered resource, and preserves the existing Claude/Codex bytes by removing exactly the two Pi-only frontmatter lines on those hosts.

### T6-D04 - child readiness over supported Pi RPC UI

**Verdict: bind readiness to an exact digest-only `context.ui.confirm` exchange after fd 3 capability validation and before either prompt acknowledgement or task release. Strength: strong. Confidence: high.**

| Option | Scalable | Maintainable | Available | Reliable | Testable | Securable | Strength |
|---|---|---|---|---|---|---|---|
| (a) RPC extension UI confirm | One fixed exchange covers every role/provider. | Uses Pi's documented extension UI request/response protocol. | Verified in local 0.80.5 and 0.80.6 package sources. | Runner validates one exact phase-ordered request before acknowledging the private command. | Digest mismatch, schema drift, replay, timeout, and ordering have focused tests. | Digest binds nonce, challenge, cwd, provider, model, sorted tools, untrusted project state, and RPC mode without exposing raw capability material. | Strong |
| (b) Raw stdout readiness record | Simple custom line. | Competes with Pi's RPC ownership of stdout and invents a second protocol. | Not a supported extension seam in approved versions. | Framing/order can collide with host JSONL. | Synthetic tests would not prove real Pi behavior. | A spoofable unowned channel weakens launch binding. | Rejected |
| (c) Prompt acknowledgement alone | No extra exchange. | Minimal code. | Available. | Confirms command dispatch, not the actual child context or active tools. | Cannot prove cwd/model/trust/tool binding. | Leaves configuration substitution undetected. | Weak |

The child fails before confirmation unless the mode is RPC, UI is available, saved/default project trust is false, provider/model are present, and active tools are the exact classified built-ins. The runner accepts only the fixed title, fixed 5-second timeout, and expected SHA-256 digest, then replies with the exact `extension_ui_response`. The task remains withheld until Pi later acknowledges the internal prompt. The UI request is tested not to contain the raw nonce, challenge, or provider key, and a duplicate attestation is rejected as replay.

### T6-D05 - one shared process-tree cleanup utility

**Verdict: consume Task 7's single shared `terminateProcessTree` utility in the runner instead of adding a Task 6-specific killer. Strength: strong. Confidence: high.**

| Option | Scalable | Maintainable | Available | Reliable | Testable | Securable | Strength |
|---|---|---|---|---|---|---|---|
| (a) Shared Task 7 utility | One implementation serves child runner and dispatch orchestration. | OS-specific cleanup remains centralized. | Task 7 owns and tests the required utility. | Timeout, abort, overflow, and protocol failure converge on one tree boundary. | Shared unit and live descendant tests cover Windows/POSIX behavior. | Prevents orphan descendants without duplicated drift. | Strong |
| (b) Duplicate runner-local killer | Works immediately for one path. | Two OS implementations drift and must be reviewed together. | Available. | Fixes may land in only one caller. | Duplicated fixtures can disagree. | Inconsistent cleanup leaves an avoidable containment gap. | Weak |
| (c) Direct-child `kill()` only | Minimal. | No helper. | Available. | Descendants can survive failure or timeout. | Root-process tests can pass while grandchildren leak. | Does not meet the process containment boundary. | Rejected |

Task 6 deliberately did not duplicate the killer. Acceptance remains pending until Task 7 lands the shared utility in `runner.ts` and the combined tests prove the integrated boundary.

## RED evidence

1. `npm --prefix plugins/ca-pi/tools exec vitest run test/child-env.test.ts`
   - Exit 1; 6 tests ran and all 6 failed only because `src/child-env.ts` did not exist.
   - The first attempt exposed test-only import/syntax mistakes; those were corrected before this accepted RED run and are not counted as feature evidence.
2. `npm --prefix plugins/ca-pi/tools exec vitest run test/child-env.test.ts test/runner-isolation.test.ts`
   - Exit 1; 2 files, 13 tests, 13 intended failures.
   - Six failures named the absent child environment implementation; four named absent runner/role modules; two found the existing child placeholder lacked `installChild`; launch validation remained absent.
3. `python .github/scripts/test_pi_child_live.py --fixture-only`
   - Exit 1; the checked-in Pi 0.80.6 help contract passed.
   - The expected failing boundary named only missing `child-env.ts`, `runner.ts`, `roles.ts`, and generated `roles.json`.
4. `npm test -- --run test/child-env.test.ts test/runner-isolation.test.ts`
   - Exit 1; 18 tests ran, with 6 intended failures for newly added task-ack ordering, process-lifetime nonce consumption, exact dual-version help/environment drift, strict required JSONL shapes, and degraded failure branches.
   - Two fake-process scenarios initially consumed the test timeout because the fixture did not emit `close`; the fixture was corrected so GREEN proves runner behavior without waiting for timeout.
5. `npm test -- --run test/runner-isolation.test.ts test/child-env.test.ts`
   - Exit 1; 22 tests ran, with 5 intended hardening failures for nested protocol schemas, fd 3 transport, final assistant semantics, trusted executable/package origins, and capability mismatch.
6. `npm test -- --run test/runner-isolation.test.ts`
   - Exit 1; 20 tests ran, with 9 intended failures for the nonce+challenge encoding, exact RPC UI schema, prompt-withholding order, digest/context binding, and child confirmation flow.
7. `python .github/scripts/test_pi_child_live.py --fixture-only`
   - Exit 1 after the live/fixture contract was strengthened; five source/catalog/help tests passed and the sole remaining intended failure proved the checked-in child bundle had not yet been rebuilt with the attestation implementation.

## Pi 0.80.5 help provenance

The 0.80.5 evidence was obtained independently on 2026-07-15 by installing exact package `@earendil-works/pi-coding-agent@0.80.5` into `%TEMP%/ca-pi-0805-evidence-online` with scripts disabled, then running its absolute `dist/cli.js` through the active absolute Node executable:

```powershell
npm install --prefix $env:TEMP\ca-pi-0805-evidence-online --ignore-scripts --no-audit --no-fund @earendil-works/pi-coding-agent@0.80.5
node $env:TEMP\ca-pi-0805-evidence-online\node_modules\@earendil-works\pi-coding-agent\dist\cli.js --version
node $env:TEMP\ca-pi-0805-evidence-online\node_modules\@earendil-works\pi-coding-agent\dist\cli.js --help
```

The version command returned `0.80.5`. Its reviewed isolation flags and environment-variable section were byte-identical to the independently checked Pi 0.80.6 fixture. Both checked-in reviewed fixtures have SHA-256 `9EFDC21FD1293BD57C88B3B8840FABFF8F0C9903DB5643BEC21283E4F9B23596`; the test also asserts byte equality before comparing their parsed exact contracts.

## GREEN evidence

1. `npm test -- --run test/child-env.test.ts test/runner-isolation.test.ts`
   - Exit 0; 2 files, 22 tests passed after the five-fix and first hardening patch.
2. `npm test -- --run test/runner-isolation.test.ts`
   - Exit 0; 17 tests passed after removing the public dependency seam and adding direct fd 3 reader/missing-pipe negatives.
3. `npm run typecheck`
   - Exit 0 after the hardened protocol, trusted-path, capability, and production/test entry split.
4. `python .github/scripts/test_build_surface.py`
   - Exit 0; 36 tests passed, including the complete 28-role metadata/catalog bijection, declared routine mapping/resource checks, invalid-classification/missing-skill negatives, and Claude byte-preservation proof.
5. `npm test -- --run test/runner-isolation.test.ts`
   - Exit 0; 20 tests passed after the exact digest-only UI confirmation flow and again after distinct nonce/challenge, duplicate-attestation replay, and secret non-exposure hardening.

Full build, fixture-only, live-child, shared process-tree integration, and repository regression evidence remain pending.

## Files and limitations

Pending.

# Tasks 13-14 independent preclosure review

Date: 2026-07-16
Branch: `feat/pi-support`
Scope: Task 13 provisional promotion evidence, Task 14 two-phase verifier, and closure of the Tasks 10-12 integrated-review findings
Verdict: **PASS FOR THE CHECKPOINT PR — zero BLOCK findings**

## Boundary of this verdict

This is a preclosure verdict, not final Pi promotion. The local Windows evidence for Pi 0.80.5 and
0.80.6 is green, while the six hosted Windows/Linux/macOS cells and CodeQL are still represented by
their exact pending states. That is the honest state required by the approved two-phase sequencing
decision. Task 13 and Task 14 therefore remain `IN_PROGRESS`; PI-AC-35, PI-AC-37, and PI-AC-38
remain `OPEN` until the checkpoint PR produces hosted evidence.

No hosted result was inferred from local execution, and the nonblocking latest canary was not
promoted into the supported-version envelope.

## Promotion-evidence review

- `docs/reports/pi-support/promotion.json` has the exact four-field envelope and exactly ten rows:
  two passing local supported-version rows, six explicit hosted-pending rows, one explicit
  CodeQL-pending row, and one latest-canary row.
- The latest row records the resolved version, Pi 0.80.9, rather than the ambiguous token `latest`.
  It honestly records `VERSION_UNSUPPORTED` and remains nonblocking.
- Every evidence string is constrained to bounded tokens. Architecture is restricted to
  `x64`/`arm64`/`pending`; result and diagnostic fields reject prose, paths, auth material, task
  text, provider output, and other unbounded values. Contradictory canary pass/diagnostic states are
  rejected.
- `promotion.md` is an exact deterministic rendering of the JSON evidence. Missing or drifted
  Markdown fails the verifier, so the prose surface cannot add unsanitized claims.
- Preclosure accepts only the exact pending tuples with `architecture: pending`, zero timing, a
  false pass bit, and a null commit. Final evidence requires positive timings, concrete
  architectures, successful supported-version/CodeQL tuples, and one commit identifier.

## Final-mode attestation review

The final path now binds all six exact supported matrix check names plus the CodeQL check to the
same evidence SHA. Every required check must be completed successfully with that exact `head_sha`.
The evidence SHA must exist and be an ancestor of `HEAD`.

Because the later evidence/status commit is necessarily a descendant of the attested checkpoint,
the verifier also compares that SHA with the complete current index/worktree. Only the explicit
plan, parity, promotion-evidence, gate-event, and handoff-report paths may differ. Committed,
staged, unstaged, or untracked code/CI drift after the attested SHA fails closed. The regression
suite proves both the allowed evidence-only descendant and rejected Pi-source mutations.

## Plan and binding review

- Tasks 1-12 are `ACCEPTED`; Tasks 13-14 are `IN_PROGRESS`.
- PI-AC-01 through PI-AC-34 and PI-AC-36 are `COVERED`; PI-AC-35, PI-AC-37, and PI-AC-38 are
  `OPEN`.
- All 38 obligations appear once in the ledger and once in an owning task.
- All 38 verifier bindings name concrete gate labels. A binding passes only when every referenced
  label exists and succeeded in the current verifier run; placeholder ownership cannot certify an
  obligation.
- The second preclosure phase is no longer deadlocked: Task 13 may be `ACCEPTED` with PI-AC-35
  `COVERED` and final hosted evidence while Task 14 remains `IN_PROGRESS`. Final mode then requires
  Tasks 1-14 accepted and all obligations covered.

## Closure of the previous integrated-review findings

All three prior MEDIUM findings are closed:

1. The `ca-pi` CI filter includes `.github/scripts/test_pi_security.py` and
   `.github/workflows/codeql.yml`, with filter-contract mutation coverage.
2. Platform and verifier idempotency use real generators in isolated trees, write twice, and compare
   resulting bytes; repeated read-only `--check` calls are no longer presented as write-idempotency
   evidence.
3. README prerequisite prose now states the actual failure direction: missing Python leaves Pi's
   final TypeScript boundary fail closed for mutations, while Claude/Codex surface an interpreter
   breadcrumb.

The production-bundle enforcement-registration regression found during preclosure is also closed.
If enforcement installation fails after bootstrap activation, the parent remains active but
unready, so mutating tool calls stay blocked until shutdown or a successful later activation. The
real isolated RPC package test proves the shipped bundle, not only TypeScript source tests.

## Independent verification

- `python .github/scripts/test_verify_pi_support.py` — **17/17 PASS**.
- `python .github/scripts/verify_pi_support.py --mode preclosure` — **PASS in 170.4 s**: all 42
  command gates, three structural gates, 38 obligation bindings, plan/status checks, exact evidence,
  parity, package inventory, branch, and twice-written generation passed.
- `python .github/scripts/test_pi_package.py` — **23/23 PASS**, including the real RPC
  enforcement-registration fail-closed regression.
- `python .github/scripts/test_pi_platform_contract.py --fixtures-only` — **PASS**, including the
  descriptor suite and real write-idempotency aggregate.
- `python .github/scripts/test_pi_security.py --evidence docs/reports/pi-support/promotion.json` —
  **PASS** with bounded result-code JSON.
- `python .github/scripts/test_public_pi_docs.py` — **11/11 PASS**.
- `python tools/build-surface.py --check`, `python tools/build-host-packages.py --check`, and
  `python tools/sync-core.py --check` — **PASS**.
- `git diff --check` — **PASS**.

The refreshed Task 14 author report now records the final 17-test verifier result, exact public-doc
and focused real-RPC commands, and the descendant/dirty-tree, canary, Markdown, and hosted-check
remediation reproduced by this review.

## Remaining terminal gates

The branch is safe to enter the sanctioned checkpoint commit/PR sequence. Final acceptance still
requires:

1. the checkpoint commit and PR;
2. successful hosted Windows/Linux/macOS jobs for Pi 0.80.5 and 0.80.6 plus CodeQL on the one
   attested SHA;
3. sanitized final evidence and independent review of those results;
4. Task 13 / PI-AC-35 acceptance;
5. the second preclosure run, Task 14 / PI-AC-37 / PI-AC-38 acceptance, and final-mode verifier;
6. the evidence/status update on the same PR followed by affected CI and review to green.

No merge, tag, release, or publication is authorized by this verdict.

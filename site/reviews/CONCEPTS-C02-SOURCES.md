# C02: decisions and evidence source record

## Scope and baseline

Approved by `site/CONCEPTS-OVERHAUL.md`; continuation of merged #857. Baseline:
`arbiterForge/codeArbiter@6860daa3c974ae32cd9584d3e60e0a51c185a613:/`.
C02 changes Concepts explanations and their directly affected curated references, not runtime
controls, decisions, approvals, releases or Academy. C03 and C04 remain open in #856.

## Owning sources and normalized meanings

All paths below belong to that exact repository and baseline.

| Topic | Owning source | Meaning preserved |
| --- | --- | --- |
| SMARTS | `core/surface/includes/smarts/core.md` | Recorded-intent Step 0 applies to sprint/brainstorming, not arbitration; verdict words and recommendation strength differ. |
| Autonomous choices | `core/surface/SPRINT.md` | Moderate/tied choices proceed inside approved non-hard-gate scope; confidence and intent are logged. |
| Typed methods | `core/surface/SPRINT.md`, `core/surface/includes/artifacts.md` | Explicit method delegation permits bounded steps-only mutation through the private producer; not prerequisite/security/backend authority. |
| Reconciliation | `core/surface/commands/reconcile.md`, `core/surface/skills/decision-variance/SKILL.md` | Exact project inputs, optional helpers, explicit user choices, append-only records and downstream recommendations. |
| Decision log | `core/surface/includes/smarts/decision-log-format.md` | Full path is decisions/decision-log.md; the hash binds the cited artifact section, not the entry or source code. |
| ADR lifecycle | `core/surface/skills/decision-lifecycle/SKILL.md`, `core/pysrc/_adrlifecycle.py`, `core/pysrc/_adrlifecyclegit.py` | Full-stem identity, Accepted/Planned versus derived evidence state, immutable accepted content, current sealed obligations and forward supersession. |
| Checkpoint | `core/surface/commands/checkpoint.md`, `core/surface/agents/checkpoint-aggregator.md` | Read-only verdict precedes separate persistence; suffix-safe report, complete findings, counter-only last-checkpoint. |
| Packet | `core/surface/commands/audit.md` | Triage means small-lane classifications; current questions/latest open findings accompany range-bound events; assembly only writes the packet. |
| Overrides | `core/surface/commands/override.md` | Attributed record before the immediate sanctioned exception, heavier security path, no standing bypass. |

Teaching data in `site/scripts/decision-evidence.ts` binds source excerpts for drift checks. The
checkpoint result-flow map uses the existing three-role renderer and its own source model. These
are editorial data, not a runtime routing language. Matching excerpts only alerts to drift; it is
not semantic certification or actual host-execution evidence.

## Contradictions retained, not repaired by prose

### C02-SOURCE-01: audit checkpoint range

The checkpoint command writes `.codearbiter/last-checkpoint` as a bare override count. The audit
command uses that record for `--since-checkpoint` and fallback range selection without defining
how the integer resolves to commits or time. The finalization skill also historically describes
that same path as gate evidence. Current source still contains that wording.

The new explanations keep the counter's writer-owned meaning, prefer an explicit demonstrated
commit/time window and do not invent a timestamp or receipt. A runtime change must locate the
proper proof/range producer and every consumer. This discrepancy is OPEN, not documentation-closed.

### C02-SOURCE-02: stale arbitration hash retention

Decision-variance Phase 1 offers keep-as-is with an instruction to update the recorded hash. Its
hard rule and the log-format owner prohibit editing any previous entry. C02 does not publish an
in-place update recipe or fabricate a successor record. It explains the hash's actual source and
requires explicit disposition through the owning path. Clarifying the append-only preservation
operation is separate runtime-contract work. State: OPEN.

### Caller versus checkpoint template language

The checkpoint caller specifies a whole-tree sweep and no promotion sign-off. The writer template
uses change-oriented fleet/disposition language. C02 attributes actual fleet scope to the caller,
retains complete actual results, and distinguishes severity from a new gate. No optional challenger
or authoring agent is inserted into the runtime route merely to fill a diagram row.

## Reader and visual acceptance

The four pages must teach a concrete example, actual record/output, inspection task, common
category error, evidence boundary and useful next action. Existing URLs and heading anchors
remain. New examples are clearly hypothetical; no native approval/lifecycle JSON is emitted.

Desktop diagrams have Commands/Skills/Agents rows; narrow layouts retain every numbered reading
step. The seven-step periodic checkpoint ends in a report/counter, not a PR. SMARTS comparisons
retain both options under every lens. Evidence selection changes reading visibility only and has
no network, storage or authority side effect. No-script and print retain all cases.

Tests cover source relationships, cell rules, content/route retention, negative data cases,
responsive text bounds, repeated selection, no-script/print, keyboard, forced colors and exact
browser captures. Broader screen-reader/cross-browser and real-user acceptance are not inferred
from automated checks. Actual observed validation is recorded in the PR, not predeclared here.

## Rollback

Revert C02 pages, components, editorial models, curated references and tests together, preserving
the existing public routes, C01 feature execution maps and earlier guide/mobile work. Restore the
prior C02 state in the plan only with a recorded disposition. Never rewrite runtime authority,
publication receipts, decision history or learner storage as a documentation rollback.

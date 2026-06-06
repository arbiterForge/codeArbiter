# codeArbiter v2 — Phase 1 Assessment (read-only)

**Branch:** `rewrite/v2`  ·  **Date:** 2026-06-03  ·  **Scope:** the current `.agents/` framework tree (~13,626 lines: 20 skills, 18 agents, ~29 public + 5 internal commands, 8 hooks, plus `AGENTS.md`/`COMMANDS.md`).

**This is the document that authorizes Phases 3–6.** It is analysis only. Nothing in the framework tree has been deleted, moved, or rewritten. The cut/keep/fix list at the end is the gate — it executes only on explicit approval.

---

## 0. How this was produced (so you can trust the evidence)

A dynamic workflow fanned out **33 read-only sub-agents** across the five vectors plus the superpowers borrow list. The three *factual* vectors (linkage, terminology, repeated-rules) were **pipelined into adversarial verification**: every dangling-reference, terminology-leak, and duplication claim was handed to a second agent told to *refute it* unless it could reproduce the exact `grep`/`ls` evidence. That pass paid for itself — it overturned or corrected eight first-draft claims. Where a claim was downgraded, this document reports the **corrected** reality, not the original overstatement. Corrections are flagged inline as **[verified-down]** / **[verified-flip]** / **[verified-clean]**.

Disposition legend: **cut** · **simplify** · **merge** (single-source) · **defer-to-optional** · **keep** · **fix**.

**The lens for every disposition** is the locked v2 direction, not enterprise norms: a *personal* framework for one expert, shipping as a *native Claude Code plugin*, state in a root-level `.codearbiter/`, Terminator tone, soul preserved (orchestration, gates, SMARTS, audit trail, hidden `/dev`).

---

## 1. Executive summary

codeArbiter is structurally sound but **carries an enterprise-compliance skin it was never going to wear.** Roughly a third of the line count exists to serve a multi-team, regulated-SaaS, multi-platform-vendored world that does not exist for a solo developer on Claude Code. The rewrite is mostly *subtraction*, plus a small number of high-value *additions* borrowed from `obra/superpowers` that turn isolated gate-skills into a sequenced, spec-driven, optionally-autonomous pipeline.

**Three headlines:**

1. **Cut the two biggest dead-weight blocks.** (a) The vendoring/dual-root machinery you already decided to kill (~350+ dedicated lines + a `${FRAMEWORK_ROOT}/${PROJECT_ROOT}` prefix tax across **1,205** occurrences in 94 files + 43 shim files). (b) An entire compliance stratum — `audit-emit`, `observability-emit`, `rotation`, `stage-gating`, `doc-review-gate`, the dual-variant `ticketing-router`, and `/hotfix` — totalling **~2,150+ lines** that a personal project can never satisfy (`/hotfix` literally cannot: its second-identity BLOCK is unsatisfiable for a solo dev).

2. **The gaps map cleanly onto superpowers.** Every missing capability you named — spec-iteration before TDD, a subagent-team primitive, a dynamic plan/execute loop, verification-before-completion, `/sprint` autonomy — has a named donor skill. One structural blocker: `decision-variance`'s **Rule 1 "Never decide alone"** is the exact opposite of `/sprint`'s "decide as me," so `/sprint` must reuse the SMARTS *scoring* but **not** that skill's decision-authority rule.

3. **The framework's hygiene is better than feared in one place, worse in another.** The plan hypothesized §3 Hard Rules were echoed across skill bodies — **[verified-clean]**: they are centralized, no duplication. But the terminology lock leaks more than expected, including a violation in `decision-variance` itself (it labels its phases "Stage 1–5").

**Estimated reduction:** ~4,500–5,500 lines of source removed outright, before per-file prefix/header savings — a **~35–40%** shrink of surviving prose, with the highest-value cut landing in the *always-loaded* `AGENTS.md` §3/§7.1 (loaded every turn).

---

## 2. Vector 1 — Overdone / low value

Eighteen findings. Skew: **10 cut · 7 simplify · 1 defer-to-optional**, all high/medium confidence.

| ID | Item (lines) | Disposition | Evidence | Why |
|---|---|---|---|---|
| OV-01 | **Vendoring / dual-root machinery** — `init-vendor.md` (148), `_paths.md` (62), `AGENTS.md` §0.1.1 + §1 Phase 0 (~63), the `${FRAMEWORK_ROOT}/${PROJECT_ROOT}` prefix (**1,205** hits / 94 files), 27 cmd + 16 agent shims | **cut** | `init-vendor.md:1`; `_paths.md:20-43`; `AGENTS.md:13-15`; `.claude/commands/feature.md` is a 1-line `@`-import shim | Plugin runtime owns registration. Shims, dual-root prefixes, `SELF-EDIT-MODE`, `AGENTS-CODEARBITER-ROOT`, monolith/vendored modes all evaporate. Single biggest block. |
| OV-02 | **`/hotfix`** command (196) | **cut** | `hotfix.md:8,61-63` "attesting identity MUST differ from operator identity … BLOCKS"; `:116-129` post-hoc ADR ≤72h | SRE incident-management for a pager rotation. Solo dev is both operator and approver → BLOCK is unsatisfiable without forging identity. `/override` already covers logged single-actor bypass. |
| OV-17 | **§7.1 Hotfix Protocol + 2 always-loaded §3 Hard Rules + `hotfixes.log`** | **cut** | `AGENTS.md` §3 "MUST NOT close a hotfix log entry without an authoring ADR…", "MUST NOT issue a /hotfix using a single identity…"; §7.1 | Tied to OV-02. Frees the most expensive real estate in the framework — the §3 list loaded *every turn*. |
| OV-05 | **`audit-emit`** skill (254) | **cut** | `audit-emit/SKILL.md:18-24` action-classification vs `audit-spec.md`; `:157-162` fail-closed-per-stage; `:198-200` dispatches `audit-emitter` | Auditor-facing compliance event stream with a registered taxonomy. No solo project ships this. |
| OV-06 | **`observability-emit`** skill (336) | **cut** | `observability-emit/SKILL.md:171-173` cardinality BLOCK; `:202-203` "MUST NOT introduce an alert rule without a paired SLO" | SLOs, alert-rule pairing, cardinality budgets = platform-SRE. Largest single compliance file; near-zero solo payoff. |
| OV-07 | **`rotation`** skill (400) + **`/rotate`** (116) | **cut** | `rotation/SKILL.md:139-145` cadence table; `:185-212` dual-running window + named approver | Credential-lifecycle for a production fleet with real signing keys/OIDC. 516 lines for a lifecycle a personal project lacks. |
| OV-09 | **`stage-gating`** skill (127) + the 4-stage model | **cut** | `stage-gating/SKILL.md:75-80` Stage 1–4 ladder; `:69` "approver MUST be a person … MUST NOT accept codeArbiter" | A prototype→production compliance ladder with named-human sign-off. Cutting it de-bloats every skill that branches on stage and kills the `[Sn]` tag dialect threaded through audit/rotation/release. "Maturity" can be one config value. |
| OV-12 | **`doc-review-gate`** skill (216) | **cut** | `doc-review-gate/SKILL.md:41-73` "prove you read it this session"; `:` framework-wide staleness scan | Documentation-governance for a large multi-hand corpus. Subsumed by §4 Reference Map + ordinary plugin context loading. |
| OV-13 | **`ticketing-router`** + plane + in-repo (102+200+205 = **507**) | **cut** | `ticketing-router/SKILL.md:21-25` mode select; `plane/SKILL.md:17-21` on-prem Plane MCP + API keys | Issue-tracker integration for a team. Solo dev runs neither on-prem Plane nor a reinvented in-repo ticket store. Keep at most a trivial inline out-of-scope marker. |
| OV-16 | **Compliance reviewer agents** — `audit-emitter` (120), `trust-zone-reviewer` (109) | **cut** | `agents/INDEX.md` rows; `_routing-table.md:49-58` "Also Dispatch" | Orphaned once their parent skills (OV-05/06/08/09) are cut. *Author/reviewer agents tied to surviving flows stay.* `decision-challenger` **stays** (still dispatched by the kept `decision-variance`). |
| OV-04 | **`crypto-compliance`** skill (151) | **simplify** | `crypto-compliance/SKILL.md:54-66` FIPS allow-list; `:114-120` CODEOWNER merge gate | FIPS/CODEOWNER = regulated env. **Keep** a thin banned-primitive check (no MD5/SHA1/DES/RC4, don't disable TLS verify, don't roll your own) — security tier survives §2. Six phases → one scan. |
| OV-03 | **`/override`** (82) + §7 | **simplify** | `override.md:35-40` 4-step identity ladder (GITHUB_ACTOR/GITEA/gh auth); `:62-63` double-confirm | **Keep** `/override` + its append-only log (audit trail is soul). Collapse identity to one `git config user.email`; drop the platform ladder and second-confirm ceremony. |
| OV-10 | **`release`** skill (442) + **`/release`** (196) | **simplify** | `release/SKILL.md:18-22` re-runs checkpoint+ADR-challenge+stage thresholds; 7 phases | Largest skill in the repo. Phases 5–6 only exist to serve cut skills. Collapses to SemVer-from-commits + changelog + tag (~2 phases) once dependencies are gone. |
| OV-11 | **`decision-lifecycle`** skill (270) | **simplify** | `decision-lifecycle/SKILL.md:60-66` 12-week aging; `:150-180` forced `decision-challenger`; `:256` mandatory challenge | **Keep** lightweight ADR author/list (`/adr`, `/adr-status`). Cut the 12-week aging clock, forced challenge routing, and stage-promotion block. Aligns with `/sprint` "decide as me" — don't nag the dev to re-litigate their own decisions. |
| OV-14 | **SMARTS corpus** — `decision-variance` refs ~1,245 (`SKILL` 350 + `smarts-framework` 172 + `decision-categories` 148 + `decision-log-format` 208 + `downstream-artifacts` 260 + `known-open-decisions` 107) | **simplify** | `smarts-framework.md:100-120` 25-word-cell table rules; 800+ lines of reference docs | **SMARTS is soul** (powers `/sprint`). But the 6-lens scored table + ~800-line reference corpus is over-built. Compress to a short heuristic prompt + one lean note. Decide, don't tabulate. |
| OV-08 | **`security-architecture`** skill (151) + **`/threat-model`** (59) | **defer-to-optional** | `security-architecture/SKILL.md:47-61` STRIDE; `:78-89` NIST/ISO/SOC2 control-family mapping | Threat-modeling has *occasional* solo value; NIST mapping + egress-allowlist CODEOWNER gate are enterprise. Make a lightweight `/threat-model` an optional capability, not a core 6-phase skill. *(User decision — see §8.)* |
| OV-15 | **Per-skill boilerplate** — "does not trigger" disclaimer + rules stated 3× (phase Gate + Decision-Gates table + Hard Rules) + Interactions/Failure-Modes | **simplify** | disclaimer in 18 skills; every skill triple-states its rules | The My-Little-Pony tone tax. Drop the disclaimer (terminology locked once in the orchestrator); state each rule once. Cuts 20–40% off most surviving skills with zero behavior loss. |
| OV-18 | **`/checkpoint`** (104) 7-reviewer fleet | **simplify** | `release:126-128`; `hotfix.md:104-109` "/checkpoint MUST scan hotfixes.log … BLOCK stage promotion" | **Keep** a lean multi-reviewer code sweep. Strip its role as enforcer of hotfix windows + stage-promotion (those callers are cut in OV-02/09/11). |

---

## 3. Vector 2 — Gaps / things not done

Ten findings: **9 fix (build it) · 1 defer-to-optional.** Each maps to a superpowers donor (§6). High confidence throughout — corroborated against your own `ultraplan.md` line references.

| ID | Gap | Disposition | Evidence of absence | Donor / how |
|---|---|---|---|---|
| GAP-01 | **No spec-iteration before TDD.** `/feature` → `tdd` "all phases"; the first thing a one-line idea meets is an audit/trust-zone obligation scan | **fix** | `feature.md:24`; `tdd/SKILL.md:39-49`; `_routing-table.md` "New feature → tdd"; no brainstorming skill exists | `brainstorming` → spec doc → `tdd` Phase 1 runs against the agreed spec. Spec to `.codearbiter/specs/`. |
| GAP-02 | **No subagent-TEAM primitive** (fresh-agent-per-task, two-stage spec-then-quality review) | **fix** | `grep "two-stage\|spec compliance\|fresh agent"` → 0 hits; dispatch is fixed-roster (`checkpoint.md:24`) | `subagent-driven-development` + `dispatching-parallel-agents`. Reuse `scout`/`grader`/`finding-triage` as plumbing; impl agents = `backend/frontend/infra-author`. |
| GAP-03 | **No dynamic per-feature plan/execute loop.** `decompose` emits a *static* backlog once at greenfield; mid-project a feature is one monolithic TDD pass | **fix** | `decompose/SKILL.md:432-444` one-time `03-task-backlog.md`; no per-feature plan skill | `writing-plans` (2–5 min tasks w/ paths + verification) + `executing-plans` (batch w/ checkpoints). |
| GAP-04 | **No verification-before-completion** distinct from commit-gate; "passes the suite" conflated with "does the thing" | **fix** | `commit-gate/SKILL.md:119-143` is test/lint/secrets bound to a commit; `tdd` Phase 4 is coverage bookkeeping | `verification-before-completion` folded into `commit-gate` as a behavioral pre-commit phase (per `ultraplan.md:179`). Low-cost, high-value. |
| GAP-05 | **No `/sprint` autonomy.** And the one skill owning SMARTS *forbids* deciding for the user | **fix** | no `commands/sprint.md`; `decision-variance/SKILL.md:22-30` Rule 1 "Never decide alone" rejects "use your best judgment" | Build `/sprint` reusing SMARTS *scoring* + the `/dev` secrecy pattern; **do not** inherit Rule 1. Highest-value gap to you. |
| GAP-10 | **No mandatory workflow pipeline.** Skills are independently-routed gates; nothing chains brainstorm→plan→build→verify→review→finish | **fix** | skills compose only via routing handoffs; `decompose` returns to plain orchestration | The meta-gap. P4 dynamic-workflow layer; superpowers' sequenced pipeline. Keep gate soul, add sequencing. |
| GAP-09 | **No root-level `.codearbiter/`** state store gated by `arbiter: enabled` frontmatter | **fix** | all state is `${PROJECT_ROOT}/.agents/projectContext/…`; sentinel is `<!--INITIALIZED-->`, not a frontmatter flag | Build-it, not a rename: new activation gate replaces the sentinel; every state path migrates. Drives both orchestrator injection and statusline gating (P2). |
| GAP-06 | **No closed reproduce→fix→verify debug loop.** `debug` investigates then hands off (MUST NOT modify code); regression test deferred to `/fix` | **fix** | `debug/SKILL.md:25-28`, `:330-332` | `systematic-debugging` framing merged into the *stronger* existing `debug` (see §6 note). Unify the 3-hop handoff into one loop. |
| GAP-08 | **No plan-aware review / branch-finish.** Reviews are severity-by-path, never "did this match the plan"; no merge/PR/discard ritual | **fix** | `_routing-table.md:45-58`; `checkpoint.md:24-37`; no finishing skill | `requesting-code-review` + `finishing-a-development-branch`. Falls out of GAP-02/03. |
| GAP-07 | **No git-worktree isolation** for parallel agent work | **defer-to-optional** | `grep worktree` hits only planning docs | `using-git-worktrees`. Convenience, not soul; build only once GAP-02 lands. |

---

## 4. Vector 3 — Broken / weak skill linkage *(factual — every row grep-verified)*

| ID | Finding | Verdict | Disposition | Note |
|---|---|---|---|---|
| LINK-01 | `/decision-variance` has a command body (`.agents/commands/decision-variance.md`, 4945 B) but **no `.claude/commands/` shim** | **confirmed** | **fix** | Referenced by `COMMANDS.md:34`, routing table, `skills/INDEX.md` — but not wired as a native command (and was absent from this session's command list). In v2 the flat `commands/` layout makes it a first-class command. |
| LINK-02 | `/decompose` — same: body exists, **no shim** | confirmed *(verified-down: 2 of 28 public commands, not "systematic")* | **fix** | The only two shim gaps. Resolve in the v2 flat layout. |
| LINK-11 | **Strike-2 redirect list omits kept commands `/debug` and `/decision-variance`** *(my own check)* | confirmed | **fix** | `_redirect.md:38-43` lists 22 commands; `/debug`, `/decision-variance`, `/rotate`, `/release`, `/hotfix` absent. The latter three are cut anyway; `/debug` + `/decision-variance` survive → real drift. v2 should generate redirect lists from the command set, not hand-maintain. |
| LINK-07 | Routing table claims `crypto-compliance` & `secret-handling` "Also Dispatch `auth-crypto-reviewer`" — **neither skill body does** | confirmed | **fix** | `_routing-table.md:51-52` vs skill bodies (no dispatch call). Reconcile in v2: either wire it or drop the claim. |
| LINK-04 | `observability-emitter` agent dispatched "(if defined)" — **agent does not exist**, and `observability-emit` never dispatches it | confirmed | **cut** | Resolves automatically: `observability-emit` is cut (OV-06). |
| LINK-03 | "`decompose` missing from routing table" | **[verified-flip] — NOT a defect** | keep | By design: `decompose` is routed by §1 Initialization, which runs *before* the §5 runtime routing table is consulted. At most a doc-clarity nit. |
| LINK-05 | "`init-vendor` orphaned relic" | **[verified-down]** | cut **via OV-01** | Not a broken link — `init-vendor` is *deliberately* outside `COMMANDS.md`/routing (admin command). It's removed in v2 because **vendoring is dropped**, not because it dangles. Belongs to Vector 1. |
| LINK-06 | `schema-validator` `[OPTIONAL PLUGIN]` reference with no body | confirmed | **keep** | Correctly gated/annotated as consumer-supplied. No action. |
| LINK-08 | All 18 agents indexed + shimmed, zero mismatches | confirmed | **keep** | Target state. |
| LINK-09 | All 20 skills indexed + bodied; variants nested correctly | confirmed | **keep** | Target state. |
| LINK-10 | Agent-dispatch references in skill/command bodies all resolve on disk | confirmed | **keep** | Linkage is sound across the sampled flows. |

**Net real defects to fix:** LINK-01, LINK-02, LINK-07, LINK-11 (+ LINK-04 resolves by deletion). The framework's index/shim/dispatch hygiene is otherwise **verified sound** — the originally-alleged "6 critical issues" reduced to 4 on verification.

---

## 5. Vector 4 — Vague / violated terminology *(factual — grep-verified)*

| ID | Finding | Verdict | Disposition | Corrected scope |
|---|---|---|---|---|
| TERM-01 | **`invoke` used for skill→agent dispatch** (locked: that's `dispatch`) | confirmed | **fix** | ~15 instances: 14 agent bodies ("invoke the ticketing-router skill") + `decision-variance/SKILL.md:231`. Note: several offending agents are themselves cut (OV-16); fix the survivors. |
| TERM-05 | **`decision-variance` labels its skill *phases* "Stage 1–5"** | **[verified-flip]** — finder said "no violation"; verifier + my check found the violation | **fix** | `decision-variance/SKILL.md:96,116,131,154,192,233` use `### Stage N` for workflow steps. `stage` is reserved for lifecycle 1–4; these are **phases**. Real defect surfaced *by* the adversarial pass. |
| TERM-02 | **Lowercase "Do not" inside a Hard Rules section** (locked: MUST/MUST NOT only) | confirmed *(verified-down: 2 not 3)* | **fix** | `audit-emit/SKILL.md:229`, `observability-emit/SKILL.md:256`. The cited `crypto-compliance:94` is a phase-body line, not Hard Rules. **Both offending files are cut (OV-05/06) → resolves by deletion.** |
| TERM-04 | **"layer" used outside `decompose`** (locked: decompose interview only) | confirmed | **simplify** | 4 instances: `audit-emitter.md:73`, `security-reviewer.md:63`, + `init-vendor`/`_paths`/`_dev` (all cut). Rephrase to tier/level in survivors; consider formalizing an "engineering-layer" exception. Low priority. |
| TERM-03 | **`[NEEDS-TRIAGE]` parallel to `[CONFIRM-NN]`** | **[verified-down]** — deliberate finding-routing marker, semantically distinct from unknown-markers | **defer-to-optional** | 14 agents + `ticketing-router` (cut). The §0.1 ban targets unknown-resolution schemes (`[OPEN-DECISION]`, `[NEEDS-INPUT]`); `[NEEDS-TRIAGE]` routes findings. In v2 either formalize the exception or fold into a one-line inline marker when ticketing is gone. |
| TERM-07 | **`trigger` as a verb** | **[verified-down]** — mostly compliant | **simplify** | One real leak in a framework file: `_routing-table.md:21` "When a trigger fires". (The other cited hits were in the untracked `ultraplansession.md`, not framework.) The "does not trigger" disclaimer ironically uses the word — dropped anyway by OV-15. |
| TERM-06 | gate / severity distinction | confirmed clean | **keep** | No violation. |

---

## 6. Vector 5 — Repeated rules wasting context *(factual — corrected counts)*

| ID | Duplication | Verdict | Disposition | Corrected cost |
|---|---|---|---|---|
| DUP-05 | **Copyright/author header block** in nearly every file | confirmed *(verified-down)* | **cut** | **828 lines** (133 `.md` × 6 + 6 `.sh` × 5), *not* the claimed 834. Author always `suadtl`, year always 2026. Move to plugin manifest / git history. Biggest mechanical win. |
| DUP-02 | **`/dev` spec stated twice** | confirmed *(verified-down: location)* | **merge** | `AGENTS.md` ~21-line `/dev` section (precedes §0, not "in §0") + `_dev.md:8-96` (~90 lines) restate the same secrecy invariants/behavior/rules. `/dev` is soul — the *duplication* is the waste. Single-source it. |
| DUP-03/04 | **SMARTS constraints + strength levels** in `smarts-framework.md` *and* `grader.md` | partial | **merge** | `smarts-framework.md:100-119,138-148` vs `grader.md:142-150,132-140`. Real but moderate (grader is a reference doc; wording not verbatim). Grader should *cite*, not restate. Folds into OV-14's SMARTS compression. |
| DUP-01 | **`## Trigger` disclaimer** in skill bodies | **[verified-down]** — claim of "all 20 × 2 lines = 40" was wrong | **simplify** | **18 of 20** skills, **1 line** each (~18 lines); `decision-variance` lacks it, `rotation` has it un-blockquoted. Delete entirely (OV-15) — terminology is locked once in the orchestrator. |
| DUP-06 | **Read-on-invocation guarantee** in `AGENTS.md` §6 + `COMMANDS.md` | partial | **simplify** | Nearly-identical wording, but `COMMANDS.md` is a surface-scan, not always-loaded — so the "double context tax" premise is weak. State once, cite. Minor. |
| DUP-10 | **INDEX disclaimers** in `agents/INDEX.md` + `skills/INDEX.md` | partial | **simplify** | Parallel intent, wording differs ("dispatch" vs "route"). Single template if INDEX is auto-generated in v2. ~10 lines. |
| DUP-07 | **Path-resolution prose** across `AGENTS.md` §0.1.1 + `_paths.md` + bodies | partial | **cut via OV-01** | Resolves with the vendoring cut. |
| DUP-08 | SMARTS five-lens descriptions | **[verified-clean]** | **keep** | Defined once in `smarts-framework.md`; the only "duplicate" was in the untracked `ultraplansession.md`, not the framework. No action. |
| DUP-09 | §3 Hard Rules echoed in skill bodies | **[verified-clean]** | **keep** | **The plan's hypothesis is false.** Hard rules are centralized in `AGENTS.md` §3; skills enforce without restating. Good hygiene — preserve it. |

---

## 7. Superpowers borrow list

Source: **[obra/superpowers](https://github.com/obra/superpowers)** (open source). Adopt shamelessly; preserve codeArbiter's gates, SMARTS, audit trail, and terminology lock in every merge.

| Superpowers skill | Action | Merges with / replaces | How it lands in v2 |
|---|---|---|---|
| **brainstorming** | adopt-new | *(no equivalent)* | Front of `/feature`: Socratic idea→spec, hard-gate "no code until design approved." Spec → `.codearbiter/specs/`; routes into `tdd` Phase 1. Feeds `/sprint` planning. **GAP-01.** |
| **writing-plans** | adopt-new | *(no equivalent)* | Bridges brainstorming→tdd: design → 2–5 min tasks w/ exact paths + verification. Each task's verification *maps to* a tdd obligation (doesn't replace it). Plan → `.codearbiter/plans/`. **GAP-03.** |
| **executing-plans** | adopt-new | *(no equivalent)* | Inline batch execution w/ human checkpoints — the *non-autonomous* counterpart. `/feature` uses it *with* checkpoints; `/sprint` uses subagent-driven *without*. **GAP-03.** |
| **subagent-driven-development** | adopt-new | new loop; reuses `backend/frontend/infra-author` | Engine of `/sprint`: fresh subagent per task → stage-1 spec-compliance → stage-2 quality. Hard-stops on tdd BLOCK, commit-gate, security CRITICAL, CONFIRM-NN. **GAP-02.** |
| **dispatching-parallel-agents** | merge-into-existing | `checkpoint.md:24`, `decision-variance` scout/grader | Generalize the existing parallel dispatch into a reusable fan-out for `/sprint` + parallel `/review`. Keep the `finding-triage`→`checkpoint-aggregator` funnel. **GAP-02.** |
| **verification-before-completion** | merge-into-existing | `commit-gate` Phase 4, `tdd` Phase 3/4 | Fold in (no new skill): run the proving command *fresh*, read output+exit code, claim done only with evidence; never trust a subagent's self-report. **GAP-04.** |
| **finishing-a-development-branch** | adopt-new | `/pr`, `/release` | Terminal step of `/feature` & `/sprint`: present merge / open-PR / discard. Merge stays a hard gate (no direct-to-main); under `/sprint`, auto-select open-PR, surface merge to you. **GAP-08.** |
| **requesting-code-review** | merge-into-existing | `/pr`, `/review`, reviewer path matrix | Pre-review checklist (change-vs-plan, tests pass, scope clean) at the front of `/pr` and as the impl-subagent self-check before stage-1. Does **not** replace reviewer agents or the CRITICAL/HIGH BLOCK. **GAP-08.** |
| **receiving-code-review** | merge-into-existing | `finding-triage` + BLOCK loop in `/review`,`/pr` | Triage each comment, address or push back (push-back routes via `/surface-conflict`); re-verify reuses verification-before-completion. Preserve severity taxonomy. |
| **systematic-debugging** | defer-to-optional *(borrow framing only)* | existing `debug` skill | **Do not replace** — `debug` is a *superset* (minimal-repro gate, 3+ hypotheses incl. a "boring" one, no-code-change ledger, forced exit). Borrow the terse reproduce→verify framing to *close the loop* (GAP-06); keep all gates. |
| **writing-skills** | defer-to-optional *(borrow heuristics)* | existing `skill-author` | Don't replace `skill-author` (gap-challenge evidence gate, routing integration). Borrow quality heuristics into its self-review phase; strip its dual-root authoring guidance (v2 cut). |
| **test-driven-development** | defer-to-optional *(borrow cheat-sheet)* | existing `tdd` | Don't replace — `tdd` is far stronger (6 gated phases, obligation scan, stage coverage thresholds). Borrow only the anti-patterns cheat-sheet + "verify the test fails for the right reason" into Phase 2. |
| **using-git-worktrees** | defer-to-optional | *(no equivalent)* | Optional per-task isolation for autonomous parallel work; opt-in flag; branches still feed commit-gate + `/pr`. **GAP-07.** |

**Pattern:** codeArbiter's existing skills are *stronger* than their superpowers counterparts for `tdd`, `debug`, and `skill-author` (keep ours, borrow framing). The genuinely *new* value is the **front half of the pipeline** — brainstorming, writing/executing plans, subagent-driven development, finishing-a-branch — which is exactly the connective tissue GAP-10 identified as missing.

---

## 8. The gate — consolidated cut / keep / fix list

This is the authorization. On approval, it drives Phases 2–7.

### CUT (delete outright)
- **Vendoring/dual-root machinery** — `init-vendor.md`, `_paths.md`, `.claude/` shim mirror, `${FRAMEWORK_ROOT}/${PROJECT_ROOT}` scheme, `AGENTS-CODEARBITER-ROOT`, `SELF-EDIT-MODE`, monolith/vendored modes, `AGENTS.md` §0.1.1 + §1 Phase 0. *(OV-01, LINK-05, DUP-07)*
- **`/hotfix`** + §7.1 + its 2 always-loaded §3 rules + `hotfixes.log`. *(OV-02, OV-17)*
- **Skills:** `audit-emit`, `observability-emit`, `rotation` (+`/rotate`), `stage-gating` + the 4-stage model, `doc-review-gate`, `ticketing-router` (+plane+in-repo). *(OV-05/06/07/09/12/13)*
- **Agents:** `audit-emitter`, `trust-zone-reviewer` (orphaned by the cuts). *(OV-16)*
- **Copyright/author headers** — 828 lines → manifest/git. *(DUP-05)*

### SIMPLIFY
- `crypto-compliance` → thin banned-primitive check *(OV-04)* · `/override` → single-identity, no platform ladder *(OV-03)* · `release` → SemVer+changelog+tag *(OV-10)* · `decision-lifecycle` → lean ADR author/list, no aging clock *(OV-11)* · SMARTS corpus → heuristic prompt + one note *(OV-14)* · `/checkpoint` → lean review sweep, no promotion-policing *(OV-18)* · per-skill boilerplate / triple-stated rules *(OV-15)*.

### MERGE (single-source)
- `/dev` spec → one authoritative location *(DUP-02)* · SMARTS constraints → `smarts-framework.md` only, grader cites *(DUP-03/04)* · read-on-invocation + INDEX disclaimers *(DUP-06/10)*.

### FIX (defects)
- Wire `/decision-variance` + `/decompose` as real commands *(LINK-01/02)* · reconcile the `auth-crypto-reviewer` dispatch claim *(LINK-07)* · generate redirect lists from the command set *(LINK-11)* · `invoke`→`dispatch` in agent bodies *(TERM-01)* · `decision-variance` "Stage"→"Phase" *(TERM-05)* · residual modal/`layer`/`trigger` leaks in survivors *(TERM-02/04/07)*.

### KEEP (soul — preserve, re-ground to plugin)
- Orchestration persona + §2 conflict hierarchy + the centralized §3 hard rules *(DUP-09 verified-clean)* · `tdd` (6-phase) · `commit-gate` · `decision-variance` SMARTS engine · `debug` · `refactor` · `context-creation` · `decompose` · lean `/adr`/`/adr-status` · the genuinely-useful reviewer/author agents (`backend/frontend/infra-author`, `security-reviewer`, `dependency-reviewer`, `migration-reviewer`, `coverage-auditor`, `scout`, `grader`, `finding-triage`, `decision-challenger`, `checkpoint-aggregator`) · `secret-handling` (slimmed) · hidden `/dev` (verbatim behavior) · the statusline renderer.

### BUILD (new — from superpowers + your brief)
- `brainstorming` · `writing-plans` · `executing-plans` · `subagent-driven-development` · spec-driven `/feature` · hidden `/sprint` (SMARTS "decide as me", NOT `decision-variance` Rule 1) · `verification-before-completion` (into commit-gate) · `finishing-a-development-branch` · root-level `.codearbiter/` + `arbiter: enabled` activation · the sequenced pipeline (GAP-10).

### Estimated savings
| Block | Lines removed |
|---|---|
| Compliance skills cut (audit/observability/rotation/stage-gating/doc-review/ticketing) | ~1,956 |
| `/hotfix` + `/rotate` + simplified release/decision-lifecycle/crypto (net) | ~1,000 |
| Vendoring machinery (dedicated) | ~350 |
| Copyright headers | 828 |
| Orphaned agents + SMARTS-corpus compression + boilerplate | ~700+ |
| **Total (pre prefix/header tax)** | **~4,800–5,500 (~35–40%)** |

Highest-value cut is in the *always-loaded* `AGENTS.md` §3/§7.1 — context reclaimed every single turn.

---

## 9. Decisions that are yours (surfaced, not assumed)

Four dispositions are genuine judgment calls that change the cut list:

1. **`.codearbiter/` vs root `context/` vs `.claude/codearbiter/`** for project state — you flagged this open in the interview.
2. **`/threat-model` + `security-architecture`** — cut entirely, or keep a lightweight optional? *(OV-08 currently: defer-to-optional.)*
3. **How thin to cut decision ceremony** — keep a lean SMARTS heuristic + ADR author/list (proposed), or retain a fuller SMARTS table? *(OV-11/14.)*
4. **Out-of-scope findings with `ticketing-router` gone** — trivial inline `[NEEDS-TRIAGE]` marker, or drop entirely?

These do not block approval of the overall list — they refine it.

---

## 10. Gate resolution — approved 2026-06-04

The cut/keep/fix list is **approved** as the authorization for Phases 2–7. The four §9 dispositions resolved:

1. **Project state → `.codearbiter/`** (root-level, survives plugin uninstall). Confirmed.
2. **`/threat-model` + `security-architecture` → lightweight-optional.** Strip the NIST/ISO/SOC2 control-family mapping and the egress-allowlist CODEOWNER gate; keep a lean STRIDE-style threat pass as an opt-in capability for sensitive features.
3. **Decision / SMARTS → compress, but preserve the commercialization on-ramp.** Refines OV-11 and OV-14:
   - **Compress** the ~800-line SMARTS *reference corpus* (`decision-categories`, `decision-log-format`, `downstream-artifacts`, `known-open-decisions`) to a lean heuristic prompt.
   - **Drop** pure-overhead governance: the 12-week ADR aging clock and the forced `decision-challenger` dispatch (OV-11).
   - **KEEP** the structural soul that doubles as commercialization scaffolding: the **SMARTS 6-lens evaluation** (Scalable/Maintainable/Available/Reliable/Testable/Securable), the **append-only ADR/decision log with user attribution**, and the **audit trail**. These are exactly what a future "fundable / sellable / SOC2-able" review wants, and they are cheap to keep.
   - `stage-gating`'s 4-stage named-human-approver promotion **still goes** (team process, not commercialization readiness), but **project maturity survives as a single config value** rather than disappearing.
4. **Out-of-scope findings (ticketing cut) →** trivial inline `[NEEDS-TRIAGE]` marker; no router, no variants.

**Net steer:** decision-making gets terser and stops nagging, but the audit trail + SMARTS rigor + ADR record remain a clean foundation any project can lean on if it becomes worth monetizing.

Proceeding to **Phase 2**: plugin skeleton, activation hook, gated statusline, `.codearbiter/`, `ORCHESTRATOR.md`, and `tdd` migrated as the reference pattern.

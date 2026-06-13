# Routing table

Loaded on a scope-touch or `/command` — not every turn. Follow the primary route; the gate is a hard
stop, not a suggestion. A command is **invoked**; the orchestrator **routes** to a skill; a skill
**dispatches** an agent.

| Invocation cue | Primary route | Also dispatch | Hard gate |
|---|---|---|---|
| New feature | `/feature` Step 0 triage → full lane `brainstorming` → `writing-plans` → `executing-plans` → `tdd`, or logged small lane straight to `tdd` | `backend-`/`frontend-`/`infra-author` | No spec, no code; no code before `tdd` Phase 1; small lane only on all triage criteria, logged to `triage.log` |
| Autonomous sprint | `/sprint` → `SPRINT.md` (brainstorm → plan → `subagent-driven-development`) | per-task impl authors + reviewers | One interactive spec gate; hard gates never auto-decided; every auto-decision logged |
| Bug fix | `/fix` → `tdd` (bug variant) | impl author | Failing regression test before any fix code |
| Docs edit / dep bump / revert | `/chore` (type-scaled gates) | `dependency-reviewer` for deps | No behavioral code; suite green for deps/revert; exits via `commit-gate` |
| Exploratory question needing code | `/spike` → `spike/<slug>` branch | — | Never merges or PRs; exits to a findings note or `/feature` |
| Behavior-preserving restructure | `/refactor` → `refactor` skill | `tdd` Phase 1 (new seams only) | No refactor without parity-coverage proof |
| Unknown defect / investigation | `/debug` → `debug` skill | — | No code change in the skill; one named exit |
| Commit | `/commit` → `commit-gate` | — | No commit without all nine gates green |
| Open a PR / finish a branch | `/pr` → `finishing-a-development-branch` | reviewer fleet per path | PR only; no direct-to-default, no force-push |
| Watch a PR's CI / babysit checks | `/watch` → detached `gh pr checks --watch` | on-red diagnose (propose\|branch) | Never auto-merges; green → notify + offer; merge-to-default routes through the hard gate; no poll loop |
| Code review of the diff | `/review` → `dispatching-parallel-agents` | reviewer fleet → `finding-triage` → `checkpoint-aggregator` | BLOCK on any CRITICAL/HIGH |
| Periodic sweep | `/checkpoint` → `dispatching-parallel-agents` | reviewer fleet → triage → aggregator | Surfaces a triaged report; not a promotion gate |
| Governance record for a window | `/audit` | — | Read-only; never overwrites a packet; audit lines quoted verbatim |
| Release / version tag | `/release` → `release` skill | `commit-gate` (release commit) | No tag on a red suite; tag not pushed unbidden |
| Code uses crypto / hashing / signing / TLS / random | `crypto-compliance` skill | `auth-crypto-reviewer` | BLOCK on any banned primitive |
| Code reads / writes / passes a secret | `secret-handling` skill | `auth-crypto-reviewer` | BLOCK on a secret outside the approved store |
| Auth / crypto / key change | `auth-crypto-reviewer` | `security-reviewer` | BLOCK on banned primitive, exposed secret, shell injection |
| Migration file added or changed | `migration-reviewer` | — | BLOCK on missing classification or irreversible destructive op |
| `package.json` / lockfile / base image changed | `/add-dep` → `dependency-reviewer` | — | BLOCK on denied license or supply-chain concern |
| Sensitive feature / attack-surface change | `/threat-model` → `security-architecture` (optional) | `security-reviewer`, `auth-crypto-reviewer` | STOP only on a critical unmitigated threat |
| Arbitration / variance / ADR reconciliation | `/reconcile` → `decision-variance` | `scout`, `grader`, `decision-challenger` | No decision recorded without user attribution |
| New / aged ADR, unresolved `[CONFIRM-NN]` | `/adr`, `/adr-status` → `decision-lifecycle` | `decision-challenger` (optional) | No `[CONFIRM-NN]` resolved by guessing |
| Rule conflict (persona vs docs vs code) | `/conflict` | — | STOP all other work immediately |
| Unsure `/reconcile` vs `/conflict`? | rules contradict and work cannot safely continue → `/conflict`; artifacts drifted, work continues → `/reconcile` | — | When genuinely ambiguous, `/conflict` wins — stopping is recoverable, drifting past a rule conflict is not |
| New skill needed | `/new-skill` → `skill-author` | — | No skill until the gap is proven uncovered |
| Subagent raises an out-of-scope finding | inline `[NEEDS-TRIAGE]` marker | — | Never an ADR disposition; never silently dropped |
| Session context bloated / want longer sessions | `/ca:prune` → `prune-transcript.py` | — | Never `--execute` the live transcript; dry-run by default; resume/compaction gains only, not live |
| Sitting down to code / repo hygiene cleanup | `/ca:standup` → orchestrator git actions | — | ff-only pull on a clean tree; each branch/worktree delete confirmed individually; stash/dirty/un-pushed report-only; never touch the default branch |

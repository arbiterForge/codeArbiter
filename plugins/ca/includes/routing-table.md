# Routing table

Loaded on a scope-touch or `/command` — not every turn. Follow the primary route; the gate is a hard
stop, not a suggestion. A command is **invoked**; the orchestrator **routes** to a skill; a skill
**dispatches** an agent.

| Invocation cue | Primary route | Also dispatch | Hard gate |
|---|---|---|---|
| New feature | `/feature` → `brainstorming` → `writing-plans` → `executing-plans` → `tdd` | `backend-`/`frontend-`/`infra-author` | No spec, no code; no code before `tdd` Phase 1 |
| Bug fix | `/fix` → `tdd` (bug variant) | impl author | Failing regression test before any fix code |
| Behavior-preserving restructure | `/refactor` → `refactor` skill | `tdd` Phase 1 (new seams only) | No refactor without parity-coverage proof |
| Unknown defect / investigation | `/debug` → `debug` skill | — | No code change in the skill; one named exit |
| Commit | `/commit` → `commit-gate` | — | No commit without all nine gates green |
| Open a PR / finish a branch | `/pr` → `finishing-a-development-branch` | reviewer fleet per path | PR only; no direct-to-default, no force-push |
| Code review of the diff | `/review` → `dispatching-parallel-agents` | reviewer fleet → `finding-triage` → `checkpoint-aggregator` | BLOCK on any CRITICAL/HIGH |
| Periodic sweep | `/checkpoint` → `dispatching-parallel-agents` | reviewer fleet → triage → aggregator | Surfaces a triaged report; not a promotion gate |
| Release / version tag | `/release` → `release` skill | `commit-gate` (release commit) | No tag on a red suite; tag not pushed unbidden |
| Code uses crypto / hashing / signing / TLS / random | `crypto-compliance` skill | `auth-crypto-reviewer` | BLOCK on any banned primitive |
| Code reads / writes / passes a secret | `secret-handling` skill | `auth-crypto-reviewer` | BLOCK on a secret outside the approved store |
| Auth / crypto / key change | `auth-crypto-reviewer` | `security-reviewer` | BLOCK on banned primitive, exposed secret, shell injection |
| Migration file added or changed | `migration-reviewer` | — | BLOCK on missing classification or irreversible destructive op |
| `package.json` / lockfile / base image changed | `/add-dep` → `dependency-reviewer` | — | BLOCK on denied license or supply-chain concern |
| Sensitive feature / attack-surface change | `/threat-model` → `security-architecture` (optional) | `security-reviewer`, `auth-crypto-reviewer` | STOP only on a critical unmitigated threat |
| Arbitration / variance / ADR reconciliation | `/decision-variance` → `decision-variance` | `scout`, `grader`, `decision-challenger` | No decision recorded without user attribution |
| New / aged ADR, unresolved `[CONFIRM-NN]` | `/adr`, `/adr-status` → `decision-lifecycle` | `decision-challenger` (optional) | No `[CONFIRM-NN]` resolved by guessing |
| Rule conflict (persona vs docs vs code) | `/surface-conflict` | — | STOP all other work immediately |
| New skill needed | `/new-skill` → `skill-author` | — | No skill until the gap is proven uncovered |
| Subagent raises an out-of-scope finding | inline `[NEEDS-TRIAGE]` marker | — | Never an ADR disposition; never silently dropped |

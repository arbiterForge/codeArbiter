# Cost estimate, model recommendation & concurrency

## Sizing commands

Prefer `tokei` or `cloc` if present; else `git ls-files | xargs wc -l`. Capture total LOC, file count, and the top languages. Read `tech-stack.md` for the language set first.

## v0 token estimate (crude, self-calibrating)

An order-of-magnitude band, not a quote. Refined over runs by the `tokens_estimated`/`tokens_actual` telemetry pair.

```
repo_tokens   = LOC * 10                     # ~8-12 tokens/line; 10 default
per_lens      = repo_tokens * 0.5 * 3        # 0.5 coverage fraction * 3 read+reason+write on high-reasoning
lenses_total  = per_lens * active_lens_count
mapping       = repo_tokens * 1.2
total_point   = mapping + lenses_total
band          = [total_point * 0.5, total_point * 2]
```

Present the band, the inputs, and that high-reasoning output tokens dominate. On a large repo this is routinely millions of tokens — say so.

## Model recommendation (state at Phase 0)

Drive this lane with the highest-reasoning model available at high effort. A cheap model inflates false positives, and this lane files real issues. Dispatch models per role:

| Role | Model | Effort |
|---|---|---|
| orchestrator (the skill) | Opus 4.8 | high |
| tribunal-appsec-reviewer | Opus 4.8 | high |
| tribunal-reliability-reviewer | Opus 4.8 | high |
| tribunal-architecture-reviewer | Opus 4.8 | high |
| tribunal-secrets-supply-reviewer | Sonnet 5 | high |
| tribunal-migration-reviewer | Sonnet 5 | high |
| tribunal-test-fidelity-reviewer | Sonnet 5 | high |
| tribunal-performance-reviewer | Sonnet 5 | medium |
| tribunal-observability-reviewer | Sonnet 5 | medium |
| tribunal-typesafety-reviewer | Sonnet 5 | medium |
| tribunal-coverage-reviewer | Sonnet 5 | medium |
| optional mappers (`map-structure`, `map-deps`) | Haiku 4.5 | low |

API strings: `claude-opus-4-8`, `claude-sonnet-5`, `claude-haiku-4-5-20251001`. On proprietary code all tiers must be approved (Anthropic) models — never an external worker.

## Default wave partition

The default dispatch order (Phase 2), aligned with the model tiers above:

| Wave | Lenses |
|---|---|
| 1 | appsec, architecture, reliability |
| 2 | secrets-supply, migration, test-fidelity |
| 3 | coverage, observability, performance, typesafety |

A lens dropped from the roster at Phase 1 (scope-inapplicable) is simply absent from its wave — no renumbering. Phase 0/1 MAY choose a different partition for cause (e.g. a migration-heavy repo pulling `migration` into wave 1), but whichever partition is used MUST be recorded in `run-started` (`schemas.md`) — resume reads the recorded partition, never re-derives it.

## Concurrency & cost control

Concurrency ≤5 lenses in flight regardless of roster size — the roster is a budget, not a simultaneous-dispatch target. Cost levers offered at Phase 0: narrow scope to a subtree; trim the Tier-2 lenses (`performance`, `observability`, `typesafety`); lower concurrency.

## Optional mappers

On a large/sprawling repo, offload raw file-reading to two cheap mapper subagents so it stays out of the orchestrator's retained context: `map-structure` (tree, languages, entry points, core/shared/test locations, churn) and `map-deps` (manifests, lockfiles, integration surface, env/secret-usage surface). On a small repo, map inline and skip them. Either way, produce the same `inventory.md`. These are the only subagents beyond the ten lenses, and they carry no `tribunal-` prefix because they are generic extractors, not judges.

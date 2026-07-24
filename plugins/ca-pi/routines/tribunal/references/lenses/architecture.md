# architecture — lens mandate

Executed by `tribunal-architecture-reviewer`. Write contract + evidence discipline: `finding-record.md`.

## Checklist
- Orphan/dead modules: zero active callers; a module tested but never called in production is dead code masquerading as live.
- Pattern consistency: identify the primary pattern and verify it holds across all modules; deviating modules are typically later-added where context was lost.
- Cosmetic abstractions: an interface/abstract class whose removal changes no behavior, or with a single implementation adding no isolation. The diagnostic is whether it *encapsulates* complexity or merely *relocates* it — relocation creates leaky layers that force consumers to know internals.
- Dead code paths: unreachable branches, functions whose return is never consumed, imported symbols never referenced.
- God modules, over-consumed shared dependencies — structural thresholds: `ai-markers.md`. Monolith accretion in oversized files.

## Exposure
Count of modules in the import/caller map (`inventory.md`).

## Out of scope
Conformance to accepted ADRs — that is `architecture-drift-reviewer`, a different agent. Do not re-flag ADR drift.

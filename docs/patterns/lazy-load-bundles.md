# Pattern: lazy-load reference bundles

How to add a large body of reference knowledge to codeArbiter without violating the orchestrator's
"load bodies on invocation only, no bulk reads" rule, and without it rotting into drift. Reach for
this when a reference is too big to always-load and naturally splits by sub-topic (medium, domain,
phase) so a given task needs only a slice.

Worked example: `plugins/ca/includes/anti-slop-design/` — a cross-medium design reference where a
website task pulls the web slice and never loads slide or chart guidance. The invariants below were
distilled from the failure modes a three-reviewer pass surfaced while building it.

## When this pattern fits

- The knowledge is **reference**, not a workflow. It has no gated phases, so it is NOT a skill. If it
  enforces a sequence with gates, write a skill instead.
- It is large enough that always-loading it would waste context on every unrelated task.
- It partitions cleanly: most tasks need one "leaf," not the whole thing.

If it is small, just put it in an existing `includes/*.md`. If it is enforcement (a reviewer), it is
an agent. This pattern is specifically for **big, partitionable reference knowledge**.

## The shape

A directory under `includes/<bundle>/`:

- **`INDEX.md`** — the router. A scope statement, a deterministic load map (medium/topic → exact
  leaves), and a one-line surface scan of every leaf. Always read first; tiny.
- **`core.md`** — the always-loaded decision layer: the irreducible rules that apply to every task.
- **craft leaves** — cross-cutting sub-topics loaded as the map dictates.
- **medium/domain leaves** — the partition; a task loads exactly one.

A consumer reads `INDEX` → `core` → exactly the leaves its row names. Nothing else.

## Five invariants (each is a failure mode caught in review)

1. **Deterministic load map.** The router selects leaves by a fact known *before* doing the work
   (the medium, the file type), never by a judgment that requires having already done it ("load if
   visually composed" fails this). Two agents on the same artifact must load the same leaves, or the
   work is not reproducible.
2. **No rule in two tiers.** A rule lives in exactly one place. If `core` states it, a leaf does not
   restate it — it points back ("universal tells live in core §8"). Duplication guarantees drift the
   day one copy is edited.
3. **Every leaf is reachable, and claims only what it is loaded for.** If a leaf asserts it applies to
   a medium, the INDEX map must route that medium to it. A leaf that says "reports need images" while
   the map never loads it for reports is orphaned guidance.
4. **Registration moves in lockstep.** A new bundle/agent touches several surfaces at once; updating
   one and not its siblings leaves the routing inconsistent. For codeArbiter that means: the bundle's
   own `INDEX`, plus `includes/reference-map.md`, plus `includes/routing-table.md`, plus (for a
   reviewer) `agents/INDEX.md`. Update them together.
5. **Scope boundary stated once, honored everywhere.** Say what the bundle governs and what it does
   not, in the `INDEX`, and have any reviewer agent self-enforce it. A reference for *generated*
   output must not silently start governing the framework's own internal docs.

Two legibility corollaries the reviews also flagged:

- If `core` uses a numbering scheme shared with the leaves and therefore skips numbers, say so in
  `core`, or a reader who only loads `core` reads the gaps as missing content.
- If the bundle bounds its own coverage (mediums with no leaf yet), name the uncovered cases in the
  `INDEX` rather than letting the absence read as "covered."

## Wiring checklist

When adding a lazy-load bundle:

- [ ] `includes/<bundle>/INDEX.md` with scope, a deterministic load map, and a leaf surface scan.
- [ ] `core.md` holds only the always-true rules; leaves hold the partitioned rest.
- [ ] No rule duplicated across tiers; leaves cross-reference `core` instead.
- [ ] Every leaf is reachable from the load map; no leaf claims a medium the map does not route to it.
- [ ] Consumers point at `INDEX` and load per the map; none bulk-reads the bundle.
- [ ] `includes/reference-map.md` row added (with the correct `${CLAUDE_PLUGIN_ROOT}` path).
- [ ] `includes/routing-table.md` updated for any command/skill that now has a load obligation.
- [ ] For an enforcing agent: `agents/<name>.md` + an `agents/INDEX.md` row; its "dispatched by" claim
      matches reality (an inline-applying consumer is not a dispatcher).
- [ ] Scope boundary stated in `INDEX` and self-enforced by any reviewer agent.
- [ ] Ship through `commit-gate`. The bundle and leaf edits are a `docs`/`/chore` change; adding an
      enforcing reviewer agent is behavioral and routes through the feature lane (`/feature` → `tdd`),
      not `/chore`. Classify the change set by its heaviest part.

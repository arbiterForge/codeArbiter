# Kickoff Prompt 1 — Context Drift Detection + Scout Provenance

Paste the block below into a fresh terminal to start a `/ca:brainstorming` session.

---

/ca:brainstorming context drift detection + scout provenance layer

Before anything, read `docs/reports/deepdive-2026-06-26-project-context/README.md` in FULL — it is the verdict from a deep dive that compared our `.codearbiter` context handling against four external memory/context tools (claims verified against their source + against Anthropic docs). Read its Appendix "codeArbiter internals" especially; it maps the exact files and mechanisms you'll be designing against. Do not re-discover what's already documented there.

**The problem this fixes (the one real flaw found):** our project context is built ONCE (brownfield scouts in `skills/context-creation/`, greenfield interview in `skills/decompose/`) and then NEVER reconciled against the code as it changes. There is no staleness detection and no incremental re-scan. At ~200k LOC over a long project life the `.codearbiter/*.md` docs silently drift from reality — and wrong context is worse than none, because agents trust it.

**Goal:** design a drift + provenance layer.
- At creation time, persist each scout's `file:line → claim` findings plus a **content hash** of every source file a doc was derived from, into something like `.codearbiter/.provenance/`. (Today these scout findings are synthesized into docs and then thrown away — capture them instead.)
- At check time, a `/ca:context-check` skill (and/or a SessionStart line) re-hashes those source files and reports: "N source files behind X docs changed since context was built — these docs may be stale."
- The prize: re-scan becomes **incremental** — re-scout only the regions whose sources changed, not the whole repo.

**Design forks to resolve in the session:**
1. Drift granularity — **per-file content hash** (simple, robust; flags any change to a derived file) vs **line-anchor hashing** (precise; flags only when the relevant lines move, but more fragile). Lean per-file to start; add anchors only if too noisy.
2. Where provenance lives and its schema (`.codearbiter/.provenance/`? one file per doc? a single index?). Must be git-friendly and human-auditable, in the spirit of the rest of `.codearbiter/`.
3. Surface: a pull skill (`/ca:context-check`), a passive SessionStart staleness line, or both. Keep any SessionStart addition token-cheap.
4. How `create-context` / `decompose` write provenance without bloating their existing gated phases; how re-scan reuses it.

**Hard constraints (from the report — do not violate):**
- Content **hash**, not mtime (mtime gives false positives on checkout/touch, false negatives on clock skew).
- NO vector DB / embeddings / semantic index. NO background daemon or worker service. NO transcript-JSONL parsing. Keep it plain files + cheap hashing, consistent with our curated-markdown philosophy.
- Build on the existing scout pattern (`agents/scout.md` — scouts return paths+lines only, run as isolated subagents) and the existing creation skills; do not rebuild them.

**Out of scope:** file-scoped just-in-time injection (that's the separate Kickoff-2 feature, though it will later consume the provenance map you design here), and anything cross-project.

Produce a spec in `.codearbiter/specs/` per the normal brainstorming flow.

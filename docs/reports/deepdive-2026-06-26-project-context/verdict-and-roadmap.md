# Deep Dive: Project Context (`.codearbiter/`) — Verdict & Roadmap

**Date:** 2026-06-26
**Question:** Is our single-project context handling sound, are there massive flaws, and is it worth more effort? Benchmarked against four external "memory/context" tools — every external claim verified against *source code*, every Claude-Code-mechanism assumption verified against *official Anthropic docs*.
**Out of scope (by request):** cross-project memory. We want a solid mapped understanding of *the one project we're in*.

> External tools are referred to by the **concept/archetype** they represent, not by name.

> **Status (2026-06-28):** All three prioritized recommendations below **shipped in v2.6.0** — the drift/staleness layer and scout-evidence provenance index (recs 1–2) via **#145** (`feat/context-drift-provenance`), and file-scoped just-in-time injection (rec 3) via **#146** (`feat/file-scoped-context-injection`). #146 also resolved the item-3 plugin-hook risk this report flagged (`additionalContext` on a plugin-scoped `PreToolUse:Read`, claude-code #16538). This document is retained as the **decision record** — the reusable "do NOT add vectors/daemons/transcript-mining" verdict and the Anthropic-docs constraint table outlive the shipped work. The two companion `kickoff-*.md` brainstorming prompts were consumed by those PRs and have been removed.

---

## VERDICT: GO — the architecture is sound. One real weakness (staleness) is worth fixing; almost everything the alternative archetypes add is not.

Our model — curated, human-readable `.codearbiter/*.md` docs, created once (scouts / interview), git-versioned, read selectively on demand, no embeddings/DB/daemon — is the **correct** primitive for "a mapped understanding of the project it's in." The alternative archetypes validate this largely **by negative example**: their "smarter" machinery is either oversold, broken, unavailable to a CLI plugin, or aimed at cross-session recall we don't want.

The single genuine gap is **drift / staleness**: context is built once and never reconciled against the code as it changes. At ~200k LOC over a long project life, the docs *will* diverge — and wrong context is worse than none, because agents *trust* it.

---

## The five archetypes (claims vs. code)

### A. The file/markdown archetype — *a mirror of ours*
- **Validating:** per-project context as plain Markdown, read per-task, written directly by fresh-context mapper agents while the orchestrator keeps only pointers (line counts). This is the same philosophy we already run with scouts, and it is the part that **works** and is **independent of Claude Code internals**. A concern-split codebase map (stack / architecture / structure / conventions / testing / integrations / concerns) and a per-task **context manifest** (resolve a minimal file set, not the whole map) are the ideas worth borrowing.
- **Cautionary:** its bolt-on **vector layer is broken** — it ingests with one vector method and queries with a different one, so the vector spaces don't match and similarity scores are meaningless; it then falls back to lexical **silently**. This is the headline "semantic" feature, and it is the part that does not work. Direct evidence for "don't add embeddings just because they look smart."
- **Shared weakness with us:** capture is *prompt-discipline*, not enforced — nothing verifies an agent actually updated state.

### B. The vector/embedding archetype — *real, but heavy and overclaimed*
- **Real:** local embeddings + FTS5-in-SQLite kept in sync by triggers; LLM-generated summaries off the hot path; a vector store wired in by default.
- **Overclaimed:** documented hook count was wrong; the "~50-100 token" session injection is really **600-1,000+ tokens every session**; "N MCP tools" undercounts by ~5×; "10× token savings" / "hybrid search" are marketing (no score fusion, no benchmark).
- **Single best transferable idea:** **file-scoped just-in-time injection** — when an agent is about to read a file, inject prior knowledge *about that specific file*, gated on `mtime` so stale notes don't fire. Documented-to-work and directly applicable.
- **Cost:** an always-on background daemon + a separate embedding subprocess + global toolchain installs — heavy infra for cross-session recall we don't want.
- **Gap (our exact pattern):** its session-injection matcher excludes `resume`, so resumed sessions get no memory — the "works on compact/clear, not live resume" shape.

### C. The graph archetype — *oversold*
- **Real:** SQLite + FTS5 + embeddings, incremental indexing, an MCP server exposing search/recall, and an explainable hybrid score (`semantic + recency + complexity`).
- **Oversold:** the "knowledge graph" is a per-session **linked list** (`turn[i] → turn[i+1]`); the "drift detection" is a one-line **mtime equality** check between transcript files and the index — *index sync*, **not** code-vs-knowledge. "Auto-tagging" is vaporware.
- **Lesson:** the *names* promise more than the *mechanism* delivers. If we borrow the idea, borrow the mechanism (a cheap freshness check) — and upgrade mtime to a **content hash** (mtime gives false positives on checkout/touch, false negatives on clock skew).

### D. The wrapper/harness archetype — *only works if you own the loop*
- **Real:** genuine local semantic search (auto-downloaded embedder, quantized brute-force vectors in one SQLite file, fused with keyword search via reciprocal-rank fusion). Worth copying as *storage/retrieval plumbing* if we ever need retrieval at scale — no external vector service required.
- **Critical caveat:** its slick "index on every turn" works **only because it embeds the agent SDK and *is* the harness** — capture fires on its own idle event, not a Claude Code hook. **We are a plugin on the real CLI; we do not own the loop, so that freshness mechanism is unavailable to us. We are structurally dependent on hooks.**
- **Wrong primitive:** it indexes *conversation text by session* — there is no codebase-structure model. Steal the plumbing, never the data model.

### E. The proxy/daemon archetype — *avoid*
- A man-in-the-middle proxy on the model API endpoint to count tokens. It **bypasses our CA/proxy setup**, hardcodes a stale model→context table, and is a single point of total API failure for a "ring a bell at 85%" feature. We already do this safely in `statusline.py`. Do not adopt.

---

## Ground truth from Anthropic docs (the adjudication key)

| Mechanism | Reality (documented) |
|---|---|
| **Context-injecting hooks** | Only **SessionStart, UserPromptSubmit, PostToolUse** can inject (`additionalContext` / stdout). **Stop, SessionEnd, PreCompact = observe/block only — cannot inject.** |
| **After compaction** | **SessionStart re-fires with `source:"compact"`** — the *only* documented post-compaction injection path. PreCompact can only *block*, never steer what is kept. |
| **PreToolUse** | `additionalContext` injection works (the file-scoped idea is legitimate). |
| **Transcript JSONL** | Path/location documented & stable; **per-line field schema is NOT a guaranteed interface.** Anything parsing it is exposed to silent breakage. |
| **CLAUDE.md** | Loaded in full at session start; `@imports` up to 4 hops; target <200 lines for adherence. |
| **Skills** | Name+description at session start; **body loads only on invocation** (progressive disclosure is real but advisory). |
| **Subagents** | Fresh isolated context; return only a summary. (Our scouts already exploit this correctly.) |
| **MCP** | Tool defs deferred/pull-only; resources are **not** auto-injected — no proactive push. |

**Implication:** our honesty about pruning ("gains land at `--resume`/compact, not live") is **exactly correct and now doc-confirmed** — the running CLI sends in-memory history to the API; only SessionStart-on-compact / resume re-reads disk. Keep that discipline; it's a feature, not a confession.

---

## What this says about us

**Strengths confirmed (don't regress these):**
- Curated docs > opaque vectors for *auditable* project understanding. Every vector layer studied was broken, overhead-heavy, or off-target.
- Lean token budget (~400 tok SessionStart + 200-800 per skill preflight) vs the vector archetype's 600-1k *every* session.
- Independent of Claude Code internals — we don't parse transcripts for anything load-bearing. The tools that do are the fragile ones.
- Scouts already implement "fresh-context agents write findings, orchestrator keeps only pointers."
- **SessionStart correctly re-injects on `compact`** (matcher-less hook in `hooks.json:3-10`; `session-start.py:459-516`) — the persona and live state survive auto-compaction, the failure the wrapper/daemon archetypes got wrong.
- "No versioning" is **overstated** — `.codearbiter/` is in git; we already have history + rollback.

**The one massive flaw — STALENESS / DRIFT (the thing to fix):**
- Context is built once; nothing detects when `tech-stack.md`'s test command, `security-controls.md`'s auth model, or the architecture map diverge from the code. No incremental re-scan. No provenance linking a doc back to the source it was derived from.

**Smaller gaps:**
- Scout evidence is ephemeral (synthesized then discarded) — regeneration is all-or-nothing; no doc→source provenance map.
- Static injection: whole docs at preflight; no *file-scoped just-in-time* knowledge when an agent opens a specific file.

---

## Prioritized recommendations (effort → payoff)

### 1. Drift/staleness layer — **LOW effort, HIGH payoff. Do this.**
At context-creation, record provenance per doc: the **set of source files (ideally line anchors) it was derived from**, plus a **content hash** of each. A cheap checker (a `/ca:context-check` skill, and/or a SessionStart line) reports "N source files behind X docs changed since context was built — may be stale." Use a **content hash, not mtime**. This is the only place worth real effort — and the one place every alternative archetype either faked (the graph's "drift") or punted to manual (the file archetype's re-map).

### 2. Persist scout evidence as a provenance index — **LOW effort, compounding payoff.**
Write each brownfield scout's `file:line → claim` findings to `.codearbiter/.provenance/` instead of discarding them. Feeds (1) for free, makes re-scan **incremental** (re-scout only changed regions), and gives an audit trail of *why* each doc says what it says.

### 3. File-scoped just-in-time injection — **MEDIUM effort, HIGH payoff.**
A `PreToolUse:Read` hook that, when an agent opens a file, injects the governing `.codearbiter/` knowledge about that file/module (the decision, the standard, the spec) via `additionalContext`, gated on freshness. Turns the static doc set into just-in-time context. Keep the payload budgeted (≤~150 tok) so we don't drift toward the vector archetype's bloat.

### Explicitly DO NOT (the "not worth it" list):
- ❌ Vector DB / embeddings. Broken or overkill in every case studied. For ~10-50 curated docs, `grep`/Read already wins. *If* retrieval over a large set ever becomes necessary, the minimal proven pattern is **FTS5-in-one-SQLite-file**, optionally brute-force quantized vectors — never a daemon or external vector service.
- ❌ Always-on worker daemon / background service.
- ❌ Transcript-JSONL parsing for anything load-bearing (schema not guaranteed stable).
- ❌ MITM proxy for token tracking — we already have `statusline.py`.
- ❌ Cross-session / cross-project recall machinery — out of scope and the source of most of these tools' complexity.

---

## Bottom line on "is the effort worth the payoff?"

**Most of what these tools market is not worth it for our goal** — and several headline features don't even work as claimed. The payoff concentrates in a **small, cheap, hooks-based drift + provenance layer** (items 1-2) that fixes the one real flaw, plus an optional **file-scoped injection** (item 3) that makes the existing docs work harder. Everything heavier (vectors, daemons, transcript mining) is cost without commensurate benefit for "a solid mapped understanding of the project it's in."

---

## Appendix: codeArbiter internals (grounding for implementation)

Concrete map of how `.codearbiter` context works today, so a fresh session can design against it without re-discovery. All paths under `plugins/ca/` unless noted.

### Creation
- **Brownfield** — `/ca:create-context` → `skills/context-creation/SKILL.md` (6 gated phases). Phase 2 dispatches **6 parallel scouts** (`agents/scout.md`): A tech-stack, B infrastructure, C architecture, D security, E testing, F data-model. **Scouts return paths + line numbers ONLY — never code/secrets** (`scout.md`; `context-creation/SKILL.md` Phase 2). Under ~50 files → no scout, orchestrator scans inline. Phase 3 synthesizes scout reports into docs; **scout reports are then discarded** (gap #2 — the provenance we want to persist).
- **Greenfield** — `/ca:decompose` → `skills/decompose/SKILL.md` (6-layer interview). Each layer written to `.codearbiter/.decompose-draft/layer-*.md` immediately (compaction-resilient), ADRs written at decision time; draft dir deleted at Phase 6 lock.
- Both end by writing the `<!--INITIALIZED-->` marker into `CONTEXT.md`.

### Storage — `.codearbiter/` at repo root
- `CONTEXT.md` — frontmatter `arbiter: enabled` (activation flag) + `stage: N` (maturity, gates thresholds) + `<!--INITIALIZED-->` marker; body = problem / users / NOT-building / identity.
- `tech-stack.md` (exact test/lint/typecheck/build/coverage commands from CI), `coding-standards.md`, `security-controls.md` (thin; some skills BLOCK on it).
- `open-questions.md` (`CONFIRM-NN` items), `open-tasks.md`, `overrides.log` (append-only audit), `decisions/NNNN-<slug>.md` (ADRs), `plans/`, `specs/<slug>.md`, `checkpoints/`, `.markers/` (e.g. `standup-YYYY-MM-DD`, `dev-active`), `last-checkpoint`.

### Consumption
- **SessionStart hook** `hooks/session-start.py` — registered **matcher-less** in `hooks/hooks.json:3-10`, so it fires on **all** sources (startup/resume/clear/compact). It injects `ORCHESTRATOR.md` (~147 lines) + live startup state via **plain stdout** (NOT `hookSpecificOutput.additionalContext` — see the file header: plugin-scoped `additionalContext` was unreliable, claude-code #16538; plain stdout is added to context dependably). Live state = stage, BLOCKING `CONFIRM-NN` list, in-flight task count, first-of-day standup briefing. Dormant (exit 0) if `CONTEXT.md` lacks `arbiter: enabled`.
- **Per-skill Pre-flight** — every skill opens by explicitly Reading the `.codearbiter/` docs it needs (e.g. `skills/tdd/SKILL.md` reads CONTEXT/tech-stack/coding-standards/spec/security). Skills MUST NOT guess commands — read them.
- **Routing** — `includes/reference-map.md`: scope-touch → read governing doc → route to owning skill.

### Maintenance (the gap)
- **No incremental indexing, no staleness detection.** Docs are edited in place by the owning skill; freshness is assumed. No doc→source provenance, no re-scan trigger. This is exactly what items 1-2 add.

### Pruning (confirmed "not live")
- `hooks/prune-transcript.py` + `hooks/_prunelib.py`, registered on **UserPromptSubmit** and **PreCompact** (`hooks.json:43-58`), gated by env `CODEARBITER_PRUNE` (`off`/`dry`/`on`), `CODEARBITER_PRUNE_TIER` (gentle/standard/aggressive), `CODEARBITER_PRUNE_KEEP_RECENT` (default 10). Operates on the **session transcript only**, never `.codearbiter/`. Gains land at `--resume`/restart/compaction, not the current turn (the running CLI sends in-memory history to the API). `commands/prune.md` states this honestly.

### Existing hook surface (for item 3)
- `hooks/hooks.json` currently registers PreToolUse matchers **`Bash|PowerShell`, `Write`, `Edit|MultiEdit`** (`pre-bash.py`/`pre-write.py`/`pre-edit.py`) — **`Read` is NOT yet hooked**, so item 3 adds a new `PreToolUse: Read` matcher. PostToolUse matches `Write|Edit` (`post-write-edit.py`). ⚠️ Item-3 risk: our SessionStart deliberately avoids `additionalContext` for plugins (#16538); PreToolUse injection *requires* `additionalContext` (stdout from PreToolUse is not added to context). The vector archetype proved PreToolUse:Read `additionalContext` works in practice — but **verify it for a plugin-scoped hook before committing the design.**

### Anthropic-docs facts that constrain the design
- Inject-capable hooks: **SessionStart, UserPromptSubmit, PostToolUse** only. Stop/SessionEnd/PreCompact cannot inject. SessionStart re-fires on `source:"compact"` (only post-compaction inject path). Transcript JSONL field schema is **not** a guaranteed-stable interface. Subagents (scouts) get fresh isolated context and return only a summary.

---

## Appendix: brainstorming kickoff prompts (consumed)

Two self-contained `/ca:brainstorming` kickoff prompts originally lived alongside this report and seeded the implementation work. Both have been **consumed and removed** now that the features shipped:
- `kickoff-1-drift-provenance.md` — context drift detection + scout provenance → shipped in **#145** (`feat/context-drift-provenance`).
- `kickoff-2-file-scoped-injection.md` — file-scoped JIT injection → shipped in **#146** (`feat/file-scoped-context-injection`).

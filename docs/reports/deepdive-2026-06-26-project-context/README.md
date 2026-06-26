# Deep Dive: Project Context (`.codearbiter/`) — Verdict & Roadmap

**Date:** 2026-06-26
**Question:** Is our single-project context handling sound, are there massive flaws, and is it worth more effort? Benchmarked against four external "memory/context" tools — every external claim verified against *source code*, every Claude-Code-mechanism assumption verified against *official Anthropic docs*.
**Out of scope (by request):** cross-project memory. We want a solid mapped understanding of *the one project we're in*.

> External tools are referred to by the **concept/archetype** they represent, not by name.

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

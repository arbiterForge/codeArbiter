# Spec — file-scoped just-in-time context injection on Read

**Slug:** `file-scoped-context-injection` · **Lane:** full · **Status:** approved (2026-06-26)
**Governs:** plugins/ca/hooks/pre-read.py, plugins/ca/hooks/_readinjectlib.py

> Source of truth: `docs/reports/deepdive-2026-06-26-project-context/README.md`
> (branch `research-project-context-improvements`) — recommendation item **#3**
> "file-scoped just-in-time injection." Consumes the provenance map built by the
> shipped `context-drift-provenance` feature (#145) as an **enrichment tier**, but does
> **not** depend on it for MVP value.

---

## 0. Feasibility finding (RESOLVED — spike GO)

PreToolUse adds context to the model **only** via `hookSpecificOutput.additionalContext`
(`hookEventName: "PreToolUse"`, `permissionDecision: "allow"`). Plain stdout is **not**
injected on PreToolUse (unlike SessionStart, where this repo relies on plain stdout).

The load-bearing risk was **claude-code #16538** (closed "Not Planned"): plugin-scoped
`additionalContext` is broken **on SessionStart**. Whether it extended to **PreToolUse
plugin-scope** was undocumented — and that gated the wiring choice.

**Resolved by the spike `spike/pretooluse-additionalcontext` (see
`.codearbiter/spikes/pretooluse-additionalcontext.md` → ## Answer): GO.** A plugin-scoped
`PreToolUse:Read` hook's `additionalContext` (sentinel `CA_SPIKE_PLUGIN_7F3A`) reached the
model directly, alongside the settings-scoped control. **#16538 is SessionStart-specific and
does NOT extend to PreToolUse.**

**Consequence for wiring:** ship as a plugin `hooks.json` `PreToolUse` matcher `Read` (best
UX, zero install). The settings.json-installer fallback — the entire no-go branch, including
its `/ca:statusline`-style command and the `reference-map`/`routing-table`/catalog lockstep —
is **dropped from scope**. The spike branch never merges; its probe residue is cleaned
separately (tracked, not an AC of this feature).

No blocking `CONFIRM-NN` remains.

---

## Problem

`.codearbiter/` knowledge is injected **statically** — `ORCHESTRATOR.md` + live state at
SessionStart, whole docs read at each skill's pre-flight. Nothing is surfaced about the
**specific file** an agent is about to touch. So an author subagent opens `plugins/ca/tools/farm.ts`
without ADR-0003's "HTTPS-only, secret-via-env" constraint in view — exactly the drift that
ADR-0003 was written to remediate. The governing decision/control/spec exists on disk but is
not delivered at the file, at the moment of touch.

**Caller who feels it:** any agent (orchestrator or a fresh-context subagent — scout, author)
about to `Read` a governed source file, whose context does not already hold the whole doc set.

**Done looks like:** on a Read of a *governed* file, a ≤150-token, freshness-gated note naming
the governing decision/control/spec lands in that agent's context; on a Read of anything else,
**nothing** fires and nothing slows down.

---

## Scope

**In scope**
- A `PreToolUse:Read` hook (plugin-scoped or settings-installed per AC-01/02) that injects a
  small, budgeted, file-relevant payload via `additionalContext` while always allowing the Read.
- A pure, fully-testable `_readinjectlib.py` (stdlib only, zero import-time side effects, never
  raises — mirroring `_provenancelib.py` / `_taskboardlib.py`) holding the file→knowledge map,
  the budget assembler, and the freshness gate.
- File→knowledge map, four tiers (priority order = `.codearbiter/` conflict hierarchy §2:
  security & audit > correctness > maintainability):
  1. **security-controls.md** — matched via the shipped `_provenancelib.classify_source()`
     security-entry predicate (auth/middleware/jwt/crypto/secret files). No provenance needed.
  2. **decisions/** — matched via the ADR `governs:` frontmatter glob list; `status: accepted` only.
  3. **specs/** — matched via a new `**Governs:** <globs>` header line; approved specs only.
  4. **Enrichment (post-backfill):** provenance inversion (source→doc+claim) for
     tech-stack/coding-standards/security-controls claims, freshness-gated by `git hash-object`.
- A new optional `**Governs:** <comma-separated globs>` line in the spec header format, plus
  best-effort backfill of existing specs (non-blocking).

**Out of scope**
- Drift *detection* (shipped in #145) and the provenance store's creation/backfill.
- Cross-project / cross-session memory.
- Vector/embedding retrieval; any daemon; transcript-JSONL parsing.
- Injecting on non-Read tools, or on Reads of non-source files.

---

## Design notes (constraints the ACs encode)

- **Zero-cost on miss.** The overwhelmingly common Read matches nothing; that path must do a
  cheap index lookup only — **no git call, no provenance hashing** — mirroring
  `heal_worklist`'s cost guarantee (provenance AC-13).
- **Freshness, per tier.** Tiers 1–3 gate on document status (`accepted`/`approved`) — an
  accepted ADR is durable by nature. Tier 4 gates on `git hash-object` equality: a **drifted**
  (hash-mismatched) provenance claim is **suppressed, never injected** — a stale note is worse
  than none, and the drift system already nudges separately.
- **Dedup.** At most one injection per `(session, file)` via a per-session marker under
  `.codearbiter/.markers/`; subsequent Reads of the same file inject nothing.
- **Fail-open, always.** Any error (malformed index, git failure, exception, timeout) degrades
  to allow-with-no-injection. A hook failure MUST NOT block or stall a Read.
- **Provenance dependency is enrichment only.** `.codearbiter/.provenance/` is empty in any
  repo whose context predates #145 (including this one today). MVP value comes from tiers 1–3,
  which need no provenance. Tier 4 lights up only once a re-scout backfills the store.

---

## Acceptance criteria

Each criterion is one `tdd` Phase-1 obligation, verifiable by a single test.

**Feasibility / wiring**
- **AC-01** — RESOLVED (not a `tdd` obligation). The spike `spike/pretooluse-additionalcontext`
  wired a plugin-scoped `PreToolUse:Read` hook emitting a sentinel and recorded the result:
  **GO** — the sentinel reached the model. Carried as a recorded decision, not a test.
- **AC-02** — The feature is wired as a plugin `hooks.json` `PreToolUse` matcher `Read` (the
  GO path; the no-go settings-installer branch is dropped). The entry uses the
  `python3 "…/pre-read.py" || python "…/pre-read.py"` fallback pattern. Testable: parse the
  shipped `plugins/ca/hooks/hooks.json` and assert the `PreToolUse`/`Read` entry resolves to
  `pre-read.py` with the dual-interpreter fallback.
- **AC-03** — The hook emits exactly `{"hookSpecificOutput":{"hookEventName":"PreToolUse",
  "permissionDecision":"allow","additionalContext":"…"}}` and ALWAYS allows the Read, including
  when `additionalContext` is empty.

**File → knowledge map (pure functions)**
- **AC-04** — `governing_docs(path, index)` returns the security-controls.md pointer for any
  path where `classify_source(path)` is True (e.g. `src/auth/jwt.ts`), with **no** provenance
  data present, and nothing for a non-security path (e.g. `src/ui/Button.tsx`).
- **AC-05** — For an ADR with `governs: plugins/ca/tools/farm.ts` and `status: accepted`, a Read
  of `plugins/ca/tools/farm.ts` returns that ADR's id+title; a Read of an unmatched path returns
  nothing; a `status: superseded` ADR is never returned even on a glob match.
- **AC-06** — A spec carrying `**Governs:** plugins/ca/hooks/pre-read.py` is returned for a Read
  of that path; a spec with no `Governs:` line matches nothing.
- **AC-07** — (enrichment) With a populated `.provenance/`, a Read of a path present as a
  provenance entry whose stored `hash` **equals** the file's current `git hash-object` returns
  that doc+claim; an entry whose hash **diverges** is **suppressed** (returns nothing).

**Budget**
- **AC-08** — The assembled `additionalContext` is ≤150 tokens by the defined proxy (e.g.
  `ceil(chars/4)`); when matched docs exceed budget, they are included in priority order
  (security-controls > decisions > specs > standards) and the payload is truncated at the cap
  with a trailing ellipsis marker.

**Noise / dedup / cost**
- **AC-09** — A `(session, file)` pair injects at most once: after the first injecting Read, a
  per-session `.codearbiter/.markers/` entry suppresses injection on subsequent Reads of that
  same file; a different file in the same session still injects.
- **AC-10** — A Read of a file under `.codearbiter/` itself, and a Read of any path with no
  governing match, produce an allow with empty `additionalContext` (no injection).
- **AC-11** — A non-matching Read performs zero git subprocess calls and parses no provenance
  hashes (cost guarantee — assert via an injected runner that records call count = 0).

**Robustness**
- **AC-12** — Every failure mode (missing/corrupt index, ADR with malformed frontmatter, git
  unavailable, exception in any pure function) degrades to allow-with-empty-`additionalContext`;
  no input makes the hook raise or deny the Read.

**Format change**
- **AC-13** — The spec header format documents an optional `**Governs:** <comma-separated globs>`
  line, and the matcher (AC-06) parses it; adding the line to a spec is sufficient to enroll it
  with no other change.

---

## Open questions

None blocking. Two non-blocking notes carried forward:
- **Tier-4 activation** depends on a re-scout backfilling `.codearbiter/.provenance/` (empty in
  pre-#145 repos). MVP (tiers 1–3) ships without it; tier-4 tests use a synthetic provenance
  fixture, so they do not depend on a live backfill.
- **Subagent injection.** Whether PreToolUse fires for a subagent's Read (the ideal target — a
  fresh-context author opening a governed file) is assumed yes and confirmed by the AC-01 spike;
  if it does not, the value narrows to the orchestrator's own Reads. Recorded, not gating.

## Dependencies / follow-ups
- Reuses `_provenancelib.classify_source()` (tier 1) and `batch_hash()` (tier 4) verbatim — no
  re-implementation.
- **Spike cleanup (precondition, not an AC).** `spike/pretooluse-additionalcontext` left probe
  residue OUTSIDE its branch: a `Read` matcher in the plugin **cache** `hooks.json` and a
  `hooks` key in repo `.claude/settings.json`. Both must be removed (and the spike branch +
  `.codearbiter/spikes/probe/` deleted) before/while wiring AC-02, or a stale matcher could
  collide with the real hook. Harvested to `open-tasks.md`.

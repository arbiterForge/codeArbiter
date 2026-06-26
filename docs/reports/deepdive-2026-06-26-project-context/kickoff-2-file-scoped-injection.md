# Kickoff Prompt 2 — File-Scoped Just-In-Time Context Injection

Paste the block below into a fresh (separate) terminal to start a `/ca:brainstorming` session.

> Sequencing note: this feature's file→knowledge map is best fed by the provenance index from Kickoff-1. Brainstorming the two in parallel is fine, but call out that dependency in the spec — implement #1 first.

---

/ca:brainstorming file-scoped just-in-time context injection on file Read

Before anything, read `docs/reports/deepdive-2026-06-26-project-context/README.md` in FULL — the verdict from a deep dive comparing our `.codearbiter` context handling against four external memory/context tools. Read its Appendix "codeArbiter internals" especially (hook surface, injection mechanics, the #16538 caveat). Do not re-discover what's already documented there.

**The opportunity (best transferable idea found, from the "vector" archetype):** today our docs are injected statically — `ORCHESTRATOR.md` + state at SessionStart, and whole docs read at each skill's Pre-flight. There is no knowledge surfaced *about the specific file an agent is about to touch*. The idea: when an agent is about to **Read** a file, inject the governing `.codearbiter` knowledge about THAT file/module — the decision that governs it (`decisions/`), the standard that applies (`coding-standards.md`/`security-controls.md`), the spec it implements (`specs/`) — gated on freshness so stale notes never fire. Turns the static doc set into just-in-time context exactly where it's needed.

**Goal:** design a `PreToolUse: Read` hook that injects a small, budgeted, file-relevant context payload.

**Critical mechanism risk to resolve FIRST (do not skip):**
- `PreToolUse` injection REQUIRES `hookSpecificOutput.additionalContext` — stdout from PreToolUse is NOT added to the model's context (unlike SessionStart, where we use plain stdout).
- BUT our SessionStart hook deliberately avoids `additionalContext` because plugin-scoped `additionalContext` was unreliable (see `hooks/session-start.py` header, claude-code #16538). The external "vector" tool DID use `PreToolUse: Read` + `additionalContext` and it worked in practice.
- → The session must settle: does `additionalContext` reliably inject from a plugin-scoped `PreToolUse` hook on the current Claude Code? Verify against Anthropic docs and a quick probe before designing on top of it. If unreliable, the whole feature may be infeasible as a plugin hook — surface that early.

**Design forks to resolve:**
1. File → knowledge mapping: how does the hook know which `.codearbiter` docs are relevant to `path/X`? Best answer reuses the **provenance index from Kickoff-1** (source-file → doc). Note the dependency; if provenance isn't built yet, what's the cheap interim (path/dir matching against `decisions`/`specs` frontmatter)?
2. Token budget: cap the injected payload (≤~150 tokens) so we never drift toward the bloat the report calls out (the vector archetype injected 600-1000 tokens/session).
3. Freshness gating: only fire when the stored knowledge is newer than / consistent with the file (mtime or the Kickoff-1 hash), so stale notes don't mislead.
4. Dedup / noise: don't re-inject the same file's context on every Read in a session; don't fire on trivial reads. Where's the per-session marker (we already use `.codearbiter/.markers/`).
5. New hook wiring: `hooks.json` has no `Read` matcher today (only Bash/PowerShell, Write, Edit|MultiEdit). Add a `PreToolUse: Read` entry following the existing `python3 ... || python ...` fallback pattern.

**Hard constraints (from the report):** budgeted/token-cheap; no daemon; no vector store; no transcript parsing. Must degrade silently (a hook failure must never block a Read).

**Out of scope:** drift detection itself (Kickoff-1), and cross-project memory.

Produce a spec in `.codearbiter/specs/` per the normal brainstorming flow, leading with the `additionalContext`-feasibility finding.

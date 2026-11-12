# Context audit — Path 1: the composed persona

Baseline: `origin/main` @ `94d90189`. Edit source is `core/surface/` (templated); `plugins/ca*`
are build outputs of `tools/build-surface.py`.

## What this path is

`prompt-submit.py` composes `includes/safety-core.md` plus one mode body (`arbiter.md`,
`dangerous-mode.md` or `ops-mode.md`) and injects it once per (session, mode, compaction
generation). It is **resident**: it stays in context for the whole session and is paid again
after every compaction. It is not re-added on each turn.

Token figures below use the repo's own `ceil(len/4)` proxy (`_readinjectlib.token_estimate`).
They are estimates, not tokenizer counts.

| Host | arbiter | dangerous | ops | HTML comments inside arbiter composition |
|---|---|---|---|---|
| ca (Claude) | ~3,520 | ~2,245 | ~2,663 | ~196 |
| ca-codex | ~3,626 | ~2,252 | ~2,670 | ~197 |
| ca-pi | ~3,597 | ~2,242 | ~2,660 | ~192 |

All three are well under Codex's `CODEX_ADDITIONAL_CONTEXT_LIMIT = 8000`, so trimming buys
context quality and cache cost, not a truncation fix.

Only repeats **inside one composition** count as context cost below. Text shared between
`dangerous-mode.md` and `ops-mode.md` (hook-ID list, `.codearbiter/` doc list, entry/exit-log
paragraph) is never loaded together; that is a maintenance cost only and is out of scope here.

> **Revised 2026-11-07 after reading ADR-0026, ADR-0030 and ADR-0036.** B10, B11, C4 and D1
> below are ADR-mandated restatements and are now **kept**. B3, B4 and part of C3 sit in arbiter §6
> and depend on how far ADR-0036's freeze reaches (plan DEC-1). A1 gains a second defect. Every
> item below is marked with its revised status; the correction plan is
> [`path-01-plan.md`](path-01-plan.md).

**Outcome (implemented, 2026-11-07):** arbiter composition ~3,520 → ~2,738 tokens on Claude
(−22%), with Codex and Pi within a few tokens of that; dangerous −12%, ops −11%. See the plan for
what shipped and what was dropped.

**Estimated recoverable in the arbiter composition (revised): ~680 of ~3,520 tokens (~19%)**
with no ADR question, ~815 (~23%) if DEC-1 resolves narrow. (First estimate was ~1,000 / ~28%.)

**Provenance caution.** The current persona shape came from an A/B test (#609 → #611, n=1/cell,
"directional"), and the intent-routing wording was iterated again in #843. Some repetition may be
deliberate reinforcement. A and C1 are safe on correctness/mechanics grounds; for B, run a
behaviour check on the trimmed persona rather than trusting the suite alone — the suite proves
pinned phrases exist, not that behaviour held. (Revision: no reusable #609 harness exists; #611
was a bespoke n=1/cell run. The plan's T-09 builds a minimal one.)

---

## A. Correctness — fix first

**A1. ops-mode quotes arbiter text that no longer exists.**
`ops-mode.md:28-30` says it narrows arbiter's §0 non-negotiable *("route; never implement
directly")* and §6 rule *("no command owns this" is a routing gap, not a permission)*. Neither
phrase is in `arbiter.md` any more (grep across `core/surface/` hits only the ops-mode quote).
The model in ops mode is told it is relaxing rules it can't find. Rewrite the parenthetical
quotes; keep the pinned anchor `This narrows §0 and §6 only` and the `§3 … §2 … §7 … are
unchanged` sentence (`test_persona_composition.py` ANCHOR_OPS_*).

*Second defect (added in revision):* the ops composition is safety-core + ops-mode, with no
arbiter body. So a bare "§6" there resolves to **safety-core §6, the irreversible-action set**,
and "This narrows §0 and §6 only" reads as narrowing that set. The unchanged-list names §3, §2 and
§7 but not §6. Fix: say these are arbiter mode's §0/§6 and state that safety-core §6 is unchanged.

**A2. arbiter §7 restates `/override` from memory and describes the escape hatch as the procedure.**
`arbiter.md` §7 (~123 tok) says "Append one line to `.codearbiter/overrides.log` … then
proceed". `commands/override.md` step 3 makes the locked `append-override.py` helper the ordinary
path, says the overridden action **must not proceed unless the row lands**, and keeps a raw append
only as a "cooperative operator escape hatch" that must not run concurrently with conflict
resolution. The persona omits all three, and its own §3 says bodies are loaded on invocation,
never acted on from memory. Replace §7's body with one line routing to the command. **Keep the
`## §7 ` heading:** `orchestrator_section_six()` in `test_routing_and_cleanup_surface.py` uses it
to bound §6 (corrected in revision). ~73 tok net.

**A3. arbiter §3 orders mode-transition logging that the model can never act on.**
"MUST log … every mode transition (`mode --dangerous`, `mode --ops`, and the return to
`mode --arbiter`)". The flip token is intercepted in `prompt-submit.py` before the model sees it
(Claude: exit 2; Codex: block envelope), `_modelib.flip()` writes the `MODE: <mode> enter|exit`
row itself, and the arbiter body isn't resident in dangerous/ops mode, so the return can't be
read either. At best dead text; at worst a model hand-appends a duplicate row to an append-only
log. (The `AC-11 residual` note at `prompt-submit.py:52` is a root-resolution split in the hook's
own writes — the persona clause doesn't compensate for it.) Drop the mode-transition clause; keep
"/override" and "material sprint decisions". ~25 tok.

---

## B. Prose trims (revised: these change wording the model acts on, so they ship behind a behaviour check, not as a chore)

| # | Where | Duplicates | ~tok saved | Revised status |
|---|---|---|---|---|
| B1 | arbiter §4/§5 first sentence ("Before acting on a scope-touch …") | safety-core §5, near-verbatim | ~47 | plan T-06 |
| B2 | arbiter §0 "natural-language requests retain its scope…" + "Safety-core binds by protection, not spelling." | arbiter intro line 12-13; safety-core Precedence para; safety-core anti-circumvention sentence (3× in one composition) | ~33 | plan T-06 |
| B3 | arbiter "Clarity and risk…" — the clause "there the confirmation *is* the gate, not friction" | safety-core §6, same phrase | ~14 | arbiter §6 → plan T-07, only if DEC-1 = narrow |
| B4 | arbiter methods para tail: "Choose among them within safety-core's decision-authority limits … Do not invent a product decision, resolve a `[CONFIRM-NN]`, or assume missing authorization." Keep the two test-pinned sentences. | safety-core §6 decision-authority paragraph | ~40 | arbiter §6 → plan T-07, only if DEC-1 = narrow |
| B5 | arbiter `/ca:sprint` bullet: keep "load and follow SPRINT.md" + `--farm` passthrough; drop the behaviour summary | `SPRINT.md`, which it orders loaded (every dropped clause verified present there; "artifact state adds no permission gate" stays — it came from a behaviour fix) | ~80 | plan T-06 |
| B6 | §4/§5 "— load them when a scope-touch or route needs them, not every turn" → "on demand". (§3's load-on-invocation bullet stays: early position; §6's sentence is pinned.) | §3 bullet | ~14 | plan T-06 |
| B7 | arbiter §7 trailer "Safety-core's §7 governs … not repeated here." | announces non-duplication; no instruction content | (in A2) | plan T-02 |
| B9 | safety-core §3 secrets bullet: hook-floor implementation detail ("The hook floor covers only commit time … `pre-write.py` classifies by path…"). Keep one clause: the hooks only scan at commit, so don't rely on them. ADR-0030 requires the rule restated in safety-core, not the mechanism. | none — it's mechanism, not instruction | ~43 | plan T-06 |

~~B10~~ / ~~B11~~ — **withdrawn in revision.** The dangerous/ops "overrides.log is never
rewritten" line and dangerous-mode's safety-invariant parenthetical are deliberate: ADR-0030
has each mode body restate the non-suspendable subset so that rule loss is explicit.

## C. Maintainer notes shipped to the model (recommendation; reverses a stated choice or needs code/test change)

**C1. HTML comments are injected verbatim.** Neither `prompt-submit.py` nor `build-surface.py`
strips them; the generated `plugins/ca/arbiter.md` still carries its 8-line header. ~196 tok in
the arbiter composition, ~120–166 in the others, all maintainer notes (file history, which ADR
moved what). Options: strip `<!-- … -->` in `_compose_persona`, or in the build for these four
files. Catch: `test_arbiter_moved_not_copied` requires `(formerly ORCHESTRATOR.md)`, which lives
in that comment — update the test to read the source file, or keep the phrase visible.
*(Revision: that test already reads `core/surface/`, and Pi composes separately in TypeScript, so
build-time stripping of the leading header only is the recommended option — plan DEC-2, T-04.
Other comments in the build are functional markers and must survive.)*

**C2. safety-core "Section numbers are a public interface" paragraph (~114 tok).** Its own text
says it was put in the visible body deliberately so editing agents see it. But the invariant is
already enforced mechanically (`test_mode_surface.py` hook-citation check;
`test_persona_composition.py` `test_section_citations_resolve` and the §N heading check), and
every session pays for it while only a maintainer editing the file benefits. An agent editing the
file reads the raw source, where a comment is equally visible — so C1 and C2 conflict: if you
adopt C1, this paragraph can move into the (stripped) comment.

**C3. ADR history in arbiter.md.** The "A gates-off posture is a deterministic `mode --dangerous`
token flip, intercepted before this document is ever loaded…" paragraph (~85 tok) and "ADR-0030
supersedes ADR-0022's tier-2 confirmation clause for dangerous-mode entry alone; the other four
members are unchanged" (~60 tok). The arbiter-mode model never acts on the history; the
actionable residue is one sentence: mode tokens are hook-intercepted, don't load or route them,
and they are not in the destructive set.
*(Revision: the first paragraph sits outside §6 → plan T-06. The ADR-history sentence and the
"compared item-for-item in CI" framing sit in arbiter §6 → plan T-07, only if DEC-1 = narrow.)*

~~C4~~ — **withdrawn in revision.** Safety-core's "What survives every mode" list is the T-18
residual-invariant enumeration, kept for the same ADR-0030 reason as B10/B11.

## D. ~~Needs a decision~~ — withdrawn in revision

~~D1~~ — moving the destructive set into safety-core §6 would reword safety-core §6, which
**ADR-0036** freezes ("No wording in safety-core.md §6 or its dependents changes until a later
ADR"), and would relocate ADR-0026's resident copy. The third copy stays. Revisit only inside the
ADR that eventually supersedes ADR-0036's gating clause.

## E. Test gap that let this accumulate

`test_arbiter_moved_not_copied` exists to stop safety-core text being duplicated into
arbiter.md, but it only matches exact anchor sentences. Paraphrased copies (B1, B3, B4) pass.
A guard for this needs an allowlist for the ADR-0030/ADR-0026 restatements, or it fights the
ADRs (plan T-08, optional).
Meanwhile ~20 `assertIn` prose pins in `test_routing_and_cleanup_surface.py` make any rewording
of arbiter §6 a test edit. Worth considering a cheap n-gram-overlap check between safety-core and
each mode body, and loosening pins to anchor phrases rather than whole sentences.

---

## Verification plan for any edit

Edit `core/surface/`, rebuild (`tools/build-surface.py`), then run — several are plain scripts
with `main()`, not pytest:
`test_persona_composition.py`, `test_mode_surface.py`, `check_destructive_registry.py`,
`test_routing_and_cleanup_surface.py`, `test_build_surface.py`, `test_prompt_submit.py`.
Re-measure per host from the rendered output; Codex/Pi copies differ from Claude's.
A grep for "not pinned" is not proof — several anchors are line-wrapped literals compared after
whitespace normalisation.

## Next paths (ranked)

1. **Skill / command / agent descriptions** — upper bound ~3.3k tok from `origin/main`
   frontmatter (22 skills ~1.1k, 33 commands ~1.1k, 20 agents ~1.0k), resident on every request
   in every session, including dormant repos. The live Claude listing shows only a subset (no
   `tdd`, `brainstorming`, `writing-plans`, `secret-handling`; ~19 of 33 commands), and the
   installed plugin may not match `origin/main` — measure from the live listing.
2. **Startup-state block** (`session-start.py`) — dynamic, small, but also every session.
3. **`pre-read.py` / `_readinjectlib`** — injects up to 150 tok of pointers on Read; check
   per-session dedup and how often it fires before ranking it above #2.
4. Per-command load chains (e.g. `/ca:feature` → command → skill → includes), one at a time.

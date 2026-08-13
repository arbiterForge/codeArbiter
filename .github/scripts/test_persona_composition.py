#!/usr/bin/env python3
"""Content-anchor tests for Lane D's persona-body split (T-17..T-21, T-40).

`arbiter.md` used to be the always-on kernel (ORCHESTRATOR.md). It is now one mode body
among three (`arbiter`, `dangerous`, `ops`); the injected persona is `safety-core.md` +
the active mode's body. These are prose/content changes, so the obligations are
content-presence, content-absence, and byte-offset-ordering assertions rather than
behavioral unit tests (precedent: test_ux_conversion.py).

Anchors are deliberately EXACT sentences/headings, never single words, so a paraphrase-to-
nothing edit fails. Substring checks are done against whitespace-normalized text (runs of
whitespace collapsed to one space) so markdown line-wrapping cannot break an anchor that is
otherwise byte-identical.

R-3 (plan ruling): safety-core.md preserves the live `ORCHESTRATOR §N` section numbering used
by ~36 hook block messages in core/pysrc/*.py, so every citation resolves in every mode. The
numbered headings therefore live in safety-core.md (the shared prefix of every composition),
not in any one mode body.

Run: python .github/scripts/test_persona_composition.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SURFACE = ROOT / "core" / "surface"
INCLUDES = SURFACE / "includes"
PYSRC = ROOT / "core" / "pysrc"

ARBITER = SURFACE / "arbiter.md"
SAFETY_CORE = INCLUDES / "safety-core.md"
DANGEROUS = INCLUDES / "dangerous-mode.md"
OPS = INCLUDES / "ops-mode.md"  # T-22
REDIRECT = INCLUDES / "redirect.md"
ROUTING_TABLE = INCLUDES / "routing-table.md"

# Mode-body files composed after safety-core, per the spec's decided-parameters "Bodies" line.
MODE_BODIES = {
    "arbiter": ARBITER,
    "dangerous": DANGEROUS,
    "ops": OPS,
}

_failures = []


def check(cond, msg):
    if not cond:
        _failures.append(msg)


def read(p):
    return p.read_text(encoding="utf-8")


def read_or_empty(p):
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def norm(text):
    """Collapse whitespace runs to a single space, so a markdown line-wrap cannot break an
    otherwise byte-identical anchor sentence."""
    return re.sub(r"\s+", " ", text).strip()


# T-22: the exact sentence that scopes the carve-out's blast radius — narrows §0/§6 only,
# leaves §3/§2/§7 untouched. Anchored as a whole sentence (not the bare tokens "§3"/"§2"/"§7"),
# because a mutant reading "safety-core's §3 hard rules are relaxed in this mode" keeps every
# symbol a token-presence check would look for while reversing the claim entirely.
ANCHOR_OPS_NARROWS_ONLY = norm("This narrows §0 and §6 only")
ANCHOR_OPS_REST_UNCHANGED = norm(
    "§3 hard rules, §2 conflict ladder, and §7 diagnose-don't-bypass discipline "
    "are unchanged"
)

# ---- Anchors (exact sentences/headings, sourced from safety-core.md) ----------------------
# T-17: what MUST be in safety-core.md, asserted by named anchor.
ANCHOR_S2_LADDER = norm(
    "When rules pull apart, resolve in this order; if unresolvable, invoke `/conflict` — "
    "never guess: 1. Security & correctness of the audit trail — 2. Correctness & data "
    "integrity — 3. Maintainability & reviewability — 4. Performance — 5. Developer "
    "velocity."
)
ANCHOR_S7_DIAGNOSE = norm(
    "**A gate that looks wrong is diagnosed, not bypassed.** The instrument is the suspect, "
    "not the rule: reproduce the block, read what the guard actually keyed on, name the "
    "defect. Until diagnosed, the gate stands. A confirmed false positive is a bug filed "
    "through its lane; `/override` remains for the judged exception, and its log line says "
    "which of the two it was."
)
ANCHOR_SECRETS = "MUST NOT store a raw secret in repo, log, container image, or prompt."
ANCHOR_IRREVERSIBLE_SET = norm(
    "The irreversible-action set draws a confirmation even when intent is obvious, because "
    "the confirmation is the gate, not friction: merge to the default branch, branch or "
    "worktree deletion, release and tag publication, and the logged bypass itself"
)
ANCHOR_STATE_IS_READ = (
    "State is read, not remembered — a claim about now uses an instrument run now."
)
ANCHOR_DECISION_AUTHORITY = norm(
    "A parameter is yours to decide only when it is reversible, has one sensible answer, "
    "and is recorded where the user will review it"
)
ANCHOR_SURFACE_DONT_RECONCILE = "MUST NOT silently reconcile a conflict — invoke `/conflict`."

# T-19: safety-core declares its own precedence over every mode body.
ANCHOR_PRECEDENCE = norm(
    "This file is prepended to every mode body and binds over it: no mode body may weaken, "
    "omit, or override a clause stated here."
)

# The anti-circumvention sentence (T-18's ordering pivot).
ANCHOR_ANTI_CIRCUMVENTION = norm(
    "The rules bind by what they protect, not by their spelling: a path that satisfies a "
    "rule's letter while defeating its protection is a violation with extra steps."
)

REQUIRED_ANCHORS = {
    "§2 conflict ladder": ANCHOR_S2_LADDER,
    "§7 diagnose-don't-bypass": ANCHOR_S7_DIAGNOSE,
    "secrets prohibition": ANCHOR_SECRETS,
    "§6 irreversible-action set (excl. dev-entry)": ANCHOR_IRREVERSIBLE_SET,
    "state-is-read": ANCHOR_STATE_IS_READ,
    "decision-authority rule": ANCHOR_DECISION_AUTHORITY,
    "surface-don't-reconcile duty": ANCHOR_SURFACE_DONT_RECONCILE,
}


# ---- T-17: safety-core.md carries every required anchor, § numbering preserved ------------
def test_safety_core_anchors():
    t = norm(read(SAFETY_CORE))
    for name, anchor in REQUIRED_ANCHORS.items():
        check(anchor in t, f"safety-core.md: missing required anchor — {name}")

    # R-3: preserve the existing numbering. Headings must be literally "§N", not renumbered.
    for n in (2, 3, 5, 6, 7):
        check(
            re.search(rf"^#{{1,6}}\s.*§{n}\b", read(SAFETY_CORE), re.MULTILINE) is not None,
            f"safety-core.md: missing a §{n} heading (R-3 requires preserved numbering)",
        )

    # The dev-entry item is explicitly omitted from the irreversible set (superseded). Checked
    # as a regex tolerant of markdown punctuation between the macro and "entry" (a literal
    # substring check on "{{CMD:dev}} entry" was tried first and missed a backtick-adjacent
    # phrasing like "`{{CMD:dev}}` entry." during mutation testing — regex catches that too).
    check(
        re.search(r"\{\{CMD:dev\}\}", read(SAFETY_CORE), re.IGNORECASE) is None,
        "safety-core.md: irreversible-action set must OMIT the dev-entry item "
        "({{CMD:dev}} must not appear anywhere in safety-core.md)",
    )


# ---- T-18: residual-invariant enumeration precedes the anti-circumvention sentence ---------
def test_safety_core_ordering():
    raw = read(SAFETY_CORE)
    anti_offset = raw.find("The rules bind by what they protect")
    check(anti_offset != -1, "safety-core.md: anti-circumvention sentence not found at all")

    # Every named residual-invariant anchor must appear strictly BEFORE the anti-circumvention
    # sentence — not merely be present somewhere in the file. A test that only checked heading
    # presence could pass with the anchors moved after the sentence, which would make "The
    # rules" a dangling referent binding over nothing.
    # Compare offsets within the SAME normalized string, so markdown line-wrapping cannot
    # perturb the ordering check (whitespace runs collapse identically on both sides).
    norm_text = norm(raw)
    for name, anchor in REQUIRED_ANCHORS.items():
        anchor_off = norm_text.find(anchor)
        anti_off_norm = norm_text.find(ANCHOR_ANTI_CIRCUMVENTION)
        check(
            anchor_off != -1 and anti_off_norm != -1 and anchor_off < anti_off_norm,
            f"safety-core.md: ordering — '{name}' must appear BEFORE the anti-circumvention "
            f"sentence (found anchor at {anchor_off}, anti-circumvention at {anti_off_norm})",
        )


# ---- T-19: safety-core declares its own precedence over every mode body -------------------
def test_safety_core_precedence():
    t = norm(read(SAFETY_CORE))
    check(ANCHOR_PRECEDENCE in t, "safety-core.md: missing the precedence-over-mode-bodies anchor")
    # Precedence must be stated near the top — before any numbered section — so a reader (or a
    # mode body) encounters it before the rules it governs.
    raw = read(SAFETY_CORE)
    prec_off = raw.find("This file is prepended to every mode body")
    first_heading_off = re.search(r"^#{1,6}\s.*§2\b", raw, re.MULTILINE)
    check(
        prec_off != -1 and first_heading_off is not None and prec_off < first_heading_off.start(),
        "safety-core.md: precedence statement must precede the first numbered section",
    )


# ---- T-20: arbiter.md — moved, not copied; non-empty; mode-distinct -----------------------
def test_arbiter_moved_not_copied():
    t = read(ARBITER)
    check(len(t.strip()) > 0, "arbiter.md: must be non-empty")
    nt = norm(t)
    for name, anchor in REQUIRED_ANCHORS.items():
        check(anchor not in nt, f"arbiter.md: safety-core anchor still present (not moved) — {name}")
    check(
        ANCHOR_PRECEDENCE not in nt,
        "arbiter.md: safety-core's precedence anchor still present (not moved)",
    )
    check(
        ANCHOR_ANTI_CIRCUMVENTION not in nt,
        "arbiter.md: the anti-circumvention sentence still present (not moved)",
    )
    # AC-37: header records the former filename.
    check(
        "(formerly ORCHESTRATOR.md)" in t,
        "arbiter.md: header must still record the former filename (T-02, mandated)",
    )


# ---- T-21: dangerous-mode.md — general gates-off posture, no maintainer/CODEARBITER_DEV ---
def test_dangerous_mode_general_posture():
    check(not (INCLUDES / "dev-mode.md").exists(), "includes/dev-mode.md must be renamed (git mv), not left behind")
    check(DANGEROUS.is_file(), "includes/dangerous-mode.md must exist (git mv target)")
    t = read(DANGEROUS)
    check(len(t.strip()) > 0, "dangerous-mode.md: must be non-empty")
    low = t.lower()
    check("codearbiter_dev" not in low, "dangerous-mode.md: must contain no CODEARBITER_DEV reference")
    check("maintainer" not in low, "dangerous-mode.md: must contain no maintainer-only framing")
    check(
        "codearbiter itself" not in low,
        "dangerous-mode.md: must not be scoped to editing codeArbiter itself (must be general-purpose)",
    )
    # "gates-off is persona-off, not enforcement-off" — asserted by named anchor, not paraphrase.
    check(
        "persona-off" in low and "not enforcement-off" in low,
        "dangerous-mode.md: must state plainly that gates-off is persona-off, not enforcement-off",
    )
    for hook in ("H-01", "H-02", "H-05", "H-09b", "H-10b", "H-11", "H-18", "H-19", "H-22"):
        check(hook in t, f"dangerous-mode.md: must name {hook} as still-firing")
    check(
        ".git/hooks" in t or ".git\\hooks" in t,
        "dangerous-mode.md: must mention the .git/hooks backstop that closes --no-verify",
    )
    check(
        "--no-verify" in t,
        "dangerous-mode.md: must mention that the backstop closes --no-verify",
    )
    # Mode-distinct: dangerous-mode.md's text must differ from arbiter.md's and safety-core's.
    check(t != read(ARBITER), "dangerous-mode.md must be mode-distinct from arbiter.md")
    check(t != read(SAFETY_CORE), "dangerous-mode.md must be mode-distinct from safety-core.md")


def test_dangerous_mode_names_project_state_docs():
    """The descriptive project-state docs are TWO-HOP orphans without this.

    `tech-stack.md`, `coding-standards.md`, and `security-controls.md` are named nowhere in
    `arbiter.md` — they appear only in `includes/reference-map.md`, which the arbiter body
    merely points AT. Drop the arbiter body and the pointer to the pointer goes with it, so a
    non-arbiter mode has no way to learn they exist. `pre-read.py` only partly covers this: its
    tier-4 injection is provenance-gated on FRESH hashes, so it goes silent exactly when the
    docs have drifted.

    The rule (plan, "The orphaned-context problem"): non-arbiter bodies name the DESCRIPTIVE
    docs as flat facts, and name NO dispatch surface — pointing at reference-map.md would drag
    its "Route to" column into a mode that has no routing.
    """
    t = read(DANGEROUS)
    for doc in ("CONTEXT.md", "tech-stack.md", "coding-standards.md", "security-controls.md"):
        check(doc in t, f"dangerous-mode.md: must name the project-state doc {doc} (two-hop orphan otherwise)")
    # Absence side: no dispatch surface may be named, or the mode re-imports routing.
    for surface in ("reference-map.md", "routing-table.md", "COMMANDS.md", "redirect.md", "SPRINT.md"):
        check(
            surface not in t,
            f"dangerous-mode.md: must NOT name the dispatch surface {surface} — it has no routing",
        )


def test_dangerous_mode_does_not_suppress_blocking_questions():
    """SMARTS ruled (strength `strong`) AGAINST wholesale startup suppression.

    The decisive lens was Securable: `[CONFIRM-NN]` and the override count are pinned ON in
    every mode, because the lines wholesale suppression would remove are precisely the ones a
    gates-off session most needs. The old `dev-mode.md:21` clause "no `[CONFIRM-NN]` surfacing"
    is therefore superseded, not carried forward — and this test exists because it WAS carried
    forward verbatim through the rename.

    Positive assertion, not merely absence: a paraphrase-to-nothing edit that simply deletes the
    clause would leave the mode silent on whether blocking questions survive.
    """
    t = read(DANGEROUS)
    n = norm(t)
    check(
        "CONFIRM-NN" in t,
        "dangerous-mode.md: must state what happens to [CONFIRM-NN] in this mode, not go silent",
    )
    check(
        "no [CONFIRM-NN] surfacing" not in n and "no `[CONFIRM-NN]` surfacing" not in n,
        "dangerous-mode.md: must NOT claim [CONFIRM-NN] surfacing is suppressed — SMARTS pinned it on in every mode",
    )
    check(
        "still surface" in n or "still surfaced" in n or "still asked" in n,
        "dangerous-mode.md: must state positively that blocking questions still surface",
    )
    # The OTHER half of what SMARTS pinned on. Securable was the decisive lens precisely
    # because a gates-off session is the one where an unnoticed override count matters most,
    # so this is asserted separately — a body could keep [CONFIRM-NN] and still drop it.
    check(
        "override count" in n,
        "dangerous-mode.md: must state that the override count still reports — SMARTS pinned it on alongside [CONFIRM-NN]",
    )


# ---- T-40: every hook §N citation resolves to a heading in the composed persona -----------
def extract_section_citations():
    """Extract every `§N` cited in a user-visible hook block message under core/pysrc/*.py.

    Deliberately NOT pinned to a fixed count (36 today): a sibling lane (prompt-submit.py) is
    adding files to core/pysrc/ concurrently, and a pinned count would either false-fail on an
    unrelated addition or (if loosened incorrectly) silently stop checking new citations. The
    real guard is: the extracted set must be non-empty and a superset of the sections R-3 is
    actually about — a vacuous extraction (empty set) must not silently pass.
    """
    # Only citations of the persona's own numbering, e.g. "ORCHESTRATOR §2". This is
    # deliberately narrower than a bare `§(\d+)` scan: core/pysrc/_releaselib.py cites
    # "SemVer §10"/"SemVer §11" in unrelated prose, and a bare scan would wrongly demand
    # safety-core carry §10/§11 headings that have nothing to do with the persona.
    pattern = re.compile(r"ORCHESTRATOR §(\d+)")
    sections = set()
    for f in PYSRC.glob("*.py"):
        text = read(f)
        for m in pattern.finditer(text):
            sections.add(int(m.group(1)))
    return sections


def heading_present(text, n):
    return re.search(rf"^#{{1,6}}\s.*§{n}\b", text, re.MULTILINE) is not None


def test_section_citations_resolve():
    sections = extract_section_citations()
    # Guard against a vacuous pass (a-green-job-can-measure-nothing): the extraction itself
    # must have found something, and it must cover what R-3 is actually about.
    check(len(sections) > 0, "T-40: extraction found NO §N citations at all — test is vacuous")
    check(
        {2, 3, 5, 6, 7}.issubset(sections),
        f"T-40: extraction is missing an expected section; found {sorted(sections)}",
    )

    safety_core_text = read(SAFETY_CORE)
    for mode, path in MODE_BODIES.items():
        mode_text = read_or_empty(path)
        composed = safety_core_text + "\n" + mode_text
        for n in sorted(sections):
            check(
                heading_present(composed, n),
                f"T-40: §{n} citation does not resolve to a heading in the composed "
                f"'{mode}' persona (mode body present: {path.is_file()})",
            )


# ---- T-22/T-23: ops-mode.md — the advisory runtime carve-out (AC-43, AC-44) ----------------
# The discriminator wording, sourced verbatim from the ruling that scoped this task (not
# paraphrased — a paraphrase-to-nothing edit must fail this test).
ANCHOR_OPS_PERMITTED = norm(
    "An operation that starts, observes, or exercises a running system and leaves no change "
    "in tracked files or git history may be performed in-channel, named in one line as it is "
    "taken."
)
ANCHOR_OPS_REFUSED = norm(
    "Anything that mutates tracked files, the index, git history, or published state stays "
    "routed and refused."
)
# The set AC-44 requires named explicitly — infrastructure OUTSIDE this repo, never covered by
# the durable-artifact discriminator because none of it leaves a git-visible trace to review.
OPS_NAMED_REFUSALS = (
    "infrastructure teardown",
    "cluster or namespace deletion",
    "package publication",
    "live-database migration",
    "volume destruction",
)
# AC-44's three ambiguous cases, each requiring an explicit verdict (not left implicit).
OPS_AMBIGUOUS_CASES = ("npm test", "npm ci", "docker compose up")


def test_ops_mode_permitted_and_refused_sets():
    """T-22/AC-43: ops-mode.md enumerates its permitted and refused sets, bound by literal
    anchor to the persona the injector emits (safety-core + ops-mode.md, per MODE_BODIES)."""
    check(OPS.is_file(), "includes/ops-mode.md must exist")
    composed = read(SAFETY_CORE) + "\n" + read_or_empty(OPS)
    composed_n = norm(composed)
    check(ANCHOR_OPS_PERMITTED in composed_n,
          "ops-mode.md: missing the permitted-set anchor (start/observe/exercise, no tracked "
          "change) in the composed ops persona")
    check(ANCHOR_OPS_REFUSED in composed_n,
          "ops-mode.md: missing the refused-set anchor (mutates tracked files/index/history/"
          "published state) in the composed ops persona")
    # AC-21/T-25: the carve-out narrows §0/§6 only, never §3/§2/§7 — asserted by the EXACT
    # scoping sentences, not bare section-number tokens. A token check would still pass a
    # mutant that kept every "§N" symbol while reversing the claim (e.g. "§3 hard rules ...
    # are relaxed in this mode").
    check(ANCHOR_OPS_NARROWS_ONLY in composed_n,
          "ops-mode.md: missing the exact 'narrows §0 and §6 only' scoping sentence")
    check(ANCHOR_OPS_REST_UNCHANGED in composed_n,
          "ops-mode.md: missing the exact '§3/§2/§7 ... are unchanged' sentence")


def test_ops_mode_named_refusals_and_ambiguous_verdicts():
    """T-23/AC-44: the refused set names infra teardown / cluster-ns deletion / publication /
    live-DB migration / volume destruction; each of npm test, npm ci, docker compose up
    carries an explicit verdict token (not left ambiguous)."""
    t = read_or_empty(OPS)
    low = t.lower()
    for item in OPS_NAMED_REFUSALS:
        check(item in low, f"ops-mode.md: refused set must explicitly name '{item}'")
    check("outside this repo" in low,
          "ops-mode.md: the named refusals must be scoped as action against state OUTSIDE this repo")
    for case in OPS_AMBIGUOUS_CASES:
        check(f"`{case}`" in t, f"ops-mode.md: ambiguous case '{case}' must be named literally (code span)")
    # A verdict, not silence: each named case must sit near an explicit permitted/refused word
    # — scoped to that bullet's OWN line (up to the next bullet or blank line), never a fixed
    # character window: a window wide enough to reach past a short verdict word is also wide
    # enough to reach into the NEXT bullet and pick up its verdict instead, silently passing
    # a case whose own verdict was deleted. Caught exactly this way during mutation testing.
    lines = t.splitlines()
    for case in OPS_AMBIGUOUS_CASES:
        needle = f"`{case}`"
        owning_line = next((ln for ln in lines if needle in ln), None)
        check(owning_line is not None, f"ops-mode.md: '{case}' anchor not found for verdict-proximity check")
        low_line = (owning_line or "").lower()
        check(
            "permitted" in low_line or "refused" in low_line,
            f"ops-mode.md: '{case}' has no verdict word (permitted/refused) on its own bullet line",
        )


def test_ops_mode_no_dispatch_surface_named():
    """Like dangerous-mode.md: the project-state docs are named as flat facts; no dispatch
    surface is named, or ops silently re-imports routing it does not have."""
    t = read_or_empty(OPS)
    for doc in ("CONTEXT.md", "tech-stack.md", "coding-standards.md", "security-controls.md"):
        check(doc in t, f"ops-mode.md: must name the project-state doc {doc} (two-hop orphan otherwise)")
    for surface in ("reference-map.md", "routing-table.md", "COMMANDS.md", "redirect.md", "SPRINT.md"):
        check(surface not in t, f"ops-mode.md: must NOT name the dispatch surface {surface}")
    check(t.strip() != "", "ops-mode.md: must be non-empty")
    check(t != read(ARBITER), "ops-mode.md must be mode-distinct from arbiter.md")
    check(t != read(DANGEROUS), "ops-mode.md must be mode-distinct from dangerous-mode.md")


# ---- T-24: redirect.md + routing-table.md carry a runtime-ops row (AC-45) -----------------
OPS_TOKEN_STRING = "mode --ops"


def test_ops_token_bound_across_redirect_and_routing():
    """AC-45: both surfaces gain a runtime-operations entry naming the ops token, and the
    documented string is bound — by actually calling the interceptor's own matcher, not by
    a second hand-copied literal — to what the interceptor accepts as a flip-to-ops token.

    `_modelib` is imported HERE, not at module scope: it transitively imports `_hooklib`
    (Lane F, live in this same checkout) and `_activationlib`. A mid-edit syntax error in
    either would otherwise kill this whole suite at import time, before `main()`'s per-test
    `except` can report anything — every other test in this file would report nothing and the
    failure would look like a regression in THIS file's own prose checks. Scoping the import
    to the one test that needs it means a transitive breakage surfaces as exactly one named
    failure, and the other twelve tests still run and report.
    """
    sys.path.insert(0, str(PYSRC))
    import _modelib  # noqa: E402 — T-24: bind the documented ops token to the interceptor's own matcher

    # The interceptor side: `_modelib.match_mode_token` is the ONE matcher every host's
    # prompt-seam interceptor imports (Decided parameters). If the documented string does not
    # flip to "ops" through this exact function, the docs and the code have silently diverged.
    check(
        _modelib.match_mode_token(OPS_TOKEN_STRING) == "ops",
        f"the token this test binds to docs ({OPS_TOKEN_STRING!r}) does not resolve to 'ops' "
        f"via _modelib.match_mode_token — test's own premise is broken",
    )
    for name, path in (("redirect.md", REDIRECT), ("routing-table.md", ROUTING_TABLE)):
        t = read_or_empty(path)
        check(f"`{OPS_TOKEN_STRING}`" in t,
              f"{name}: must name the documented ops token `{OPS_TOKEN_STRING}` in a runtime-operations entry")
        check("ops-mode.md" in t,
              f"{name}: the runtime-operations entry must point at includes/ops-mode.md")
    # Conflict map (plan): "D does both the ops row AND the {{CMD:}} strip; G must not touch
    # it." redirect.md's tier-2 destructive-set sentence used to list `{{CMD:dev}}` entry —
    # superseded already in safety-core.md's own irreversible-action set (T-17); this is the
    # matching strip in the OTHER surface that lists the same set, and it is NOT the locked
    # act (test_routing_and_cleanup_surface.py pins `{{CMD:dev}}` only across arbiter.md's
    # four host renders, never redirect.md — verified before this edit was made).
    check(
        "{{CMD:dev}}" not in read(REDIRECT) and "{{CMD:arbiter}}" not in read(REDIRECT),
        "redirect.md: must not reference the retired {{CMD:dev}}/{{CMD:arbiter}} macros",
    )


# ---- T-25/AC-21: no mode body contradicts a safety-core anchor (table is data) ------------
# Each entry: a safety-core clause label -> phrases that would represent that mode body
# WEAKENING or reversing the clause. None may appear in ANY composed mode body. The mapping
# itself is the data under test — extending it to a newly-authored mode body costs one line,
# never a new function (a-green-job-can-measure-nothing: a table that stops growing goes silent
# on the next mode, which is why this is a plain dict, not inlined per-mode assertions).
CONTRADICTION_PHRASES = {
    "secrets prohibition (§3)": (
        "may store a raw secret",
        "secrets may be committed",
        "secret scanning is disabled",
    ),
    "no direct default-branch write / no force-push (§3)": (
        "may write directly to the default branch",
        "force-push is permitted",
        "force-push is allowed",
    ),
    "ADR immutability (§3)": (
        "may edit an adr outside /adr",
        "adrs may be edited directly",
    ),
    "surface-don't-reconcile duty (§3/§7)": (
        "may silently reconcile",
        "reconcile without /conflict",
        "conflicts may be resolved without /conflict",
    ),
    "§7 diagnose-don't-bypass": (
        "gates may be bypassed without diagnosis",
        "bypass a gate that looks wrong",
    ),
}


def test_no_mode_body_contradicts_safety_core():
    for mode, path in MODE_BODIES.items():
        text = read_or_empty(path).lower()
        if not text:
            continue
        for anchor_name, phrases in CONTRADICTION_PHRASES.items():
            for phrase in phrases:
                check(
                    phrase not in text,
                    f"{path.name} ({mode}): contains a phrase contradicting safety-core's "
                    f"{anchor_name} — '{phrase}'",
                )


TESTS = [
    test_safety_core_anchors,
    test_safety_core_ordering,
    test_safety_core_precedence,
    test_arbiter_moved_not_copied,
    test_dangerous_mode_general_posture,
    test_dangerous_mode_names_project_state_docs,
    test_dangerous_mode_does_not_suppress_blocking_questions,
    test_section_citations_resolve,
    test_ops_mode_permitted_and_refused_sets,
    test_ops_mode_named_refusals_and_ambiguous_verdicts,
    test_ops_mode_no_dispatch_surface_named,
    test_ops_token_bound_across_redirect_and_routing,
    test_no_mode_body_contradicts_safety_core,
]


def main():
    for t in TESTS:
        before = len(_failures)
        try:
            t()
        except Exception as exc:  # noqa: BLE001 — report as a failure, keep running the rest
            _failures.append(f"{t.__name__} raised {exc!r}")
        status = "PASS" if len(_failures) == before else "FAIL"
        print(f"[{status}] {t.__name__}")
    if _failures:
        print(f"\n{len(_failures)} failure(s):")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print("\nAll persona-composition checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

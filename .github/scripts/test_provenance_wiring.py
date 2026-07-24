#!/usr/bin/env python3
"""Structural tests for the commit-gate provenance auto-heal wiring (AC-14).

These are prose/command-doc assertions — content-presence checks that make the
spec's acceptance criteria (AC-14) executable and CI-enforced.

Assertions are deliberately COARSE — durable marker phrases, not exact wording —
so ordinary copy edits do not break the test.  Copy quality is carried by review,
not by this test.

Extending this harness (later tasks T-18..T-21):
  1. Add a ``test_*`` function above the "APPEND NEW" anchor.
  2. Register it in TESTS (see the anchor in that list).
  3. Add any new required file to REQUIRED_FILES (see anchor there).

Run: python .github/scripts/test_provenance_wiring.py
Run (filtered): python .github/scripts/test_provenance_wiring.py commit_gate_heal
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]


def read_repo(relative_path):
    """Read a repo file by path relative to the repository root."""
    return (ROOT / relative_path).read_text(encoding="utf-8")


_failures = []


def check(cond, msg):
    if not cond:
        _failures.append(msg)


# ---- AC-14: commit-gate Phase 5.5 provenance auto-heal (T-17) -----------------
def test_commit_gate_heal_phase():
    t = read_repo("plugins/ca/skills/commit-gate/SKILL.md")

    # Phase 5.5 heading must exist between Phase 5 and Phase 6
    check(
        "## Phase 5.5" in t,
        "commit-gate SKILL.md: '## Phase 5.5' heading must exist "
        "(provenance auto-heal phase, AC-14)",
    )

    # No-renumber guard: Phase 6 and Phase 7 must still carry their original headings
    check(
        "## Phase 6" in t,
        "commit-gate SKILL.md: '## Phase 6' heading must still exist "
        "(no-renumber guard -- test_board_sync.py asserts this heading)",
    )
    check(
        "## Phase 7" in t,
        "commit-gate SKILL.md: '## Phase 7' heading must still exist "
        "(no-renumber guard -- test_board_sync.py asserts this heading)",
    )

    # Slice Phase 5.5 for targeted assertions (between Phase 5.5 and Phase 6)
    phase55_start = t.find("## Phase 5.5")
    phase6_start = t.find("## Phase 6")
    if phase55_start == -1 or phase6_start == -1:
        # Already flagged above; bail to avoid spurious index errors.
        return
    phase55 = t[phase55_start:phase6_start]

    # heal_worklist helper must be named
    check(
        "heal_worklist" in phase55,
        "commit-gate SKILL.md Phase 5.5: must name the helper 'heal_worklist' "
        "(from _provenancelib, AC-14)",
    )

    # Re-scout must be incremental / scoped to those paths only
    check(
        any(phrase in phase55.lower() for phrase in [
            "scoped to those paths",
            "those paths only",
            "incremental re-scout",
        ]),
        "commit-gate SKILL.md Phase 5.5: must state the re-scout is scoped "
        "to those paths only (not the full repo, AC-14)",
    )

    # re-baseline / rebaseline must be named
    check(
        any(phrase in phase55.lower() for phrase in ["re-baseline", "rebaseline"]),
        "commit-gate SKILL.md Phase 5.5: must name the re-baseline action "
        "('re-baseline' or 'rebaseline', AC-14)",
    )

    # claim-changed must route to diff review / Phase 6
    check(
        any(phrase in phase55.lower() for phrase in [
            "diff review",
            "phase 6",
            "diff-review",
        ]),
        "commit-gate SKILL.md Phase 5.5: must state that a claim-changed "
        "finding routes to the diff-review phase (Phase 6, AC-14)",
    )

    # Empty-worklist cost guarantee must be stated
    check(
        any(phrase in phase55.lower() for phrase in [
            "empty worklist",
            "skip",
            "most commits pay nothing",
            "pay nothing",
            "ordinary commits",
        ]),
        "commit-gate SKILL.md Phase 5.5: must state the empty-worklist cost "
        "guarantee (most commits pay nothing, AC-14)",
    )

    # .provenance/ must appear in Phase 5.5 (file path for the re-baselined record)
    check(
        ".provenance/" in phase55,
        "commit-gate SKILL.md Phase 5.5: must reference '.provenance/' "
        "(the path where re-baselined records are staged, AC-14)",
    )

    # Re-scan instruction: auto-heal-staged files must pass the secrets scan even
    # when staged after Phase 4 (ordering gap — Phase 4 runs before Phase 5.5 stages
    # the provenance file, so a re-scan instruction is required here).
    check(
        "secrets scan" in phase55
        and any(
            phrase in phase55
            for phrase in ["newly-staged", "staged after Phase 4"]
        ),
        "commit-gate SKILL.md Phase 5.5: must instruct re-running the secrets scan "
        "over auto-heal-staged provenance files (marker: 'secrets scan' + "
        "'newly-staged' or 'staged after Phase 4') — files staged after Phase 4 "
        "must still be covered by the automated scanner, not only the Phase 6 manual check",
    )

    # Phase 6 must retain .provenance/ files (not flag as scope creep)
    phase7_start = t.find("## Phase 7")
    phase6 = t[phase6_start:phase7_start] if phase7_start != -1 else t[phase6_start:]
    check(
        ".provenance/" in phase6,
        "commit-gate SKILL.md Phase 6: must reference '.provenance/' "
        "in the exemption / retention clause (AC-14)",
    )
    check(
        any(phrase in phase6.lower() for phrase in ["retained", "not scope creep"]),
        "commit-gate SKILL.md Phase 6: must state that re-baselined "
        ".provenance/ files are retained / not scope creep (AC-14)",
    )

    # Phase 7 must stage .provenance/ files by explicit path
    if phase7_start == -1:
        check(False, "commit-gate SKILL.md: Phase 7 section not found")
        return
    next_section_start = t.find("\n## ", phase7_start + 1)
    phase7 = (
        t[phase7_start:next_section_start]
        if next_section_start != -1
        else t[phase7_start:]
    )
    check(
        ".provenance/" in phase7,
        "commit-gate SKILL.md Phase 7: must reference '.provenance/' "
        "in the selective-stage clause so re-baselined records ride the commit (AC-14)",
    )


# ---- AC-17: context-creation emits provenance + code-map (T-18) ---------------
def test_context_creation_provenance():
    scout = read_repo("plugins/ca/agents/scout.md")
    skill = read_repo("plugins/ca/skills/context-creation/SKILL.md")

    # --- agents/scout.md: Output Template carries a hash field (AC-17) ----------
    check(
        "hash" in scout,
        "agents/scout.md: Output Template must carry a hash field (marker: 'hash', AC-17)",
    )
    check(
        "git hash-object" in scout,
        "agents/scout.md: Output Template must reference 'git hash-object' (AC-17)",
    )

    # --- context-creation SKILL.md Phase 2: git hash-object per cited file ------
    phase2_start = skill.find("## Phase 2")
    phase3_start = skill.find("## Phase 3")
    if phase2_start == -1 or phase3_start == -1:
        check(False, "context-creation SKILL.md: Phase 2 or Phase 3 section not found")
        return
    phase2 = skill[phase2_start:phase3_start]
    check(
        "git hash-object" in phase2,
        "context-creation SKILL.md Phase 2: must mention 'git hash-object' "
        "per cited file (AC-17)",
    )

    # --- context-creation SKILL.md Phase 5: provenance per derived doc + code-map.md ---
    phase5_start = skill.find("## Phase 5")
    phase6_start = skill.find("## Phase 6")
    if phase5_start == -1 or phase6_start == -1:
        check(False, "context-creation SKILL.md: Phase 5 or Phase 6 section not found")
        return
    phase5 = skill[phase5_start:phase6_start]
    check(
        any(phrase in phase5 for phrase in [".provenance/", "write_provenance"]),
        "context-creation SKILL.md Phase 5: must mention writing provenance "
        "('.provenance/' or 'write_provenance') per derived doc (AC-17)",
    )
    check(
        "code-map.md" in phase5,
        "context-creation SKILL.md Phase 5: must mention synthesizing 'code-map.md' (AC-17)",
    )


# ---- AC-18: decompose writes provenance stubs + code-map stub (T-19) ----------
def test_decompose_provenance_stub():
    skill = read_repo("plugins/ca/skills/decompose/SKILL.md")

    # write_stub or "provenance stub" must appear
    check(
        any(phrase in skill for phrase in ["write_stub", "provenance stub"]),
        "decompose SKILL.md: must mention 'write_stub' or 'provenance stub' "
        "(AC-18: greenfield stubs written via _provenancelib.write_stub)",
    )

    # interview_derived must appear
    check(
        "interview_derived" in skill,
        "decompose SKILL.md: must mention 'interview_derived' "
        "(AC-18: stubs carry interview_derived: true)",
    )

    # code-map stub must appear
    check(
        "code-map" in skill,
        "decompose SKILL.md: must mention a 'code-map' stub "
        "(AC-18: greenfield code-map.md stub written alongside provenance stubs)",
    )


# ---- AC-16: code-map is read-on-demand (T-20) ---------------------------------
def test_code_map_read_on_demand():
    tdd_skill = read_repo("plugins/ca/skills/tdd/SKILL.md")
    feature_cmd = read_repo("plugins/ca/commands/feature.md")
    fix_cmd = read_repo("plugins/ca/commands/fix.md")
    session_start = read_repo("plugins/ca/hooks/session-start.py")

    # code-map.md must appear in tdd SKILL.md, within the ## Pre-flight section
    preflight_start = tdd_skill.find("## Pre-flight")
    phase1_start = tdd_skill.find("## Phase 1")
    if preflight_start == -1:
        check(False, "tdd SKILL.md: '## Pre-flight' heading not found")
    else:
        preflight_end = phase1_start if phase1_start != -1 else len(tdd_skill)
        preflight_section = tdd_skill[preflight_start:preflight_end]
        check(
            "code-map.md" in preflight_section,
            "tdd SKILL.md ## Pre-flight: must mention 'code-map.md' "
            "(AC-16: task-authoring skills read it on demand, not at SessionStart)",
        )

    # code-map.md must appear in feature.md
    check(
        "code-map.md" in feature_cmd,
        "commands/feature.md: must mention 'code-map.md' "
        "(AC-16: read-on-demand orientation step in opening/pre-flight flow)",
    )

    # code-map.md must appear in fix.md
    check(
        "code-map.md" in fix_cmd,
        "commands/fix.md: must mention 'code-map.md' "
        "(AC-16: read-on-demand orientation step in opening/pre-flight flow)",
    )

    # session-start.py must NOT contain code-map or code_map
    check(
        "code-map" not in session_start and "code_map" not in session_start,
        "hooks/session-start.py: must NOT contain 'code-map' or 'code_map' "
        "(AC-16: read-on-demand discipline -- code map is NOT loaded at SessionStart)",
    )


# ---- AC-19: /ca:context-check skill + command (T-21) --------------------------
def test_context_check_command():
    skill = read_repo("plugins/ca/skills/context-check/SKILL.md")
    cmd = read_repo("plugins/ca/commands/context-check.md")
    catalog = read_repo("plugins/ca/COMMANDS.md")

    # Command doc must be non-trivial (file exists and contains its own name)
    check(
        "context-check" in cmd,
        "commands/context-check.md: must contain 'context-check' (AC-19)",
    )

    # Catalog must list the command
    check(
        "/ca:context-check" in catalog,
        "plugins/ca/COMMANDS.md: must contain '/ca:context-check' (AC-19)",
    )

    # SKILL.md: re-scout marker
    check(
        any(phrase in skill.lower() for phrase in ["re-scout", "rescout"]),
        "context-check SKILL.md: must contain 're-scout' or 'rescout' (AC-19)",
    )

    # SKILL.md: re-baseline marker
    check(
        any(phrase in skill.lower() for phrase in ["re-baseline", "rebaseline"]),
        "context-check SKILL.md: must contain 're-baseline' or 'rebaseline' (AC-19)",
    )

    # SKILL.md: defer marker
    check(
        "defer" in skill.lower(),
        "context-check SKILL.md: must contain 'defer' (AC-19)",
    )

    # SKILL.md: report / stale-doc notion
    check(
        any(phrase in skill.lower() for phrase in ["report", "stale"]),
        "context-check SKILL.md: must contain 'report' or 'stale' (AC-19)",
    )


def test_context_creation_scout_isolation():
    skill = read_repo("plugins/ca/skills/context-creation/SKILL.md")
    codex_skill = read_repo("plugins/ca-codex/routines/context-creation/SKILL.md")
    scout = read_repo("plugins/ca/agents/scout.md")
    codex_notes = read_repo("plugins/ca-codex/includes/codex-host-notes.md")

    phase2_start = skill.find("## Phase 2")
    phase3_start = skill.find("## Phase 3")
    codex_phase2_start = codex_skill.find("## Phase 2")
    codex_phase3_start = codex_skill.find("## Phase 3")
    if min(phase2_start, phase3_start, codex_phase2_start, codex_phase3_start) == -1:
        check(False, "context-creation scout-isolation sections must exist")
        return
    phase2 = skill[phase2_start:phase3_start]
    codex_phase2 = codex_skill[codex_phase2_start:codex_phase3_start]
    scout_words = " ".join(scout.lower().split())

    check(
        "isolated subagent" in phase2.lower() and "block" in phase2.lower(),
        "context-creation Phase 2 must block when isolated scout subagents are unavailable",
    )
    check(
        "inline one scope" not in codex_phase2.lower(),
        "Codex context-creation must not claim inline scopes preserve report-only isolation",
    )
    check(
        "`context-creation` always" in scout_words
        and "decision-variance" in scout_words,
        "scout charter must scope the small-repo shortcut away from context-creation",
    )
    check(
        "context-creation" in codex_notes.lower()
        and "must not run inline" in codex_notes.lower(),
        "Codex host notes must record the context-creation exception to inline fallback",
    )


# --- APPEND NEW test_* FUNCTIONS ABOVE THIS LINE --------------------------------
# Each new function must also be added to TESTS and (if it reads a new file)
# to REQUIRED_FILES below.


# ---------------------------------------------------------------------------
# Files that must exist before any test runs.
# Append new paths alongside new test_* functions above.
REQUIRED_FILES = [
    "plugins/ca/skills/commit-gate/SKILL.md",
    # --- APPEND NEW REQUIRED FILES HERE ----------------------------------------
    "plugins/ca/skills/context-creation/SKILL.md",
    "plugins/ca-codex/routines/context-creation/SKILL.md",
    "plugins/ca-codex/includes/codex-host-notes.md",
    "plugins/ca/agents/scout.md",
    "plugins/ca/skills/decompose/SKILL.md",
    "plugins/ca/skills/tdd/SKILL.md",
    "plugins/ca/commands/feature.md",
    "plugins/ca/commands/fix.md",
    "plugins/ca/hooks/session-start.py",
    "plugins/ca/skills/context-check/SKILL.md",
    "plugins/ca/commands/context-check.md",
]

TESTS = [
    test_commit_gate_heal_phase,
    # --- APPEND NEW TESTS HERE --------------------------------------------------
    test_context_creation_provenance,
    test_context_creation_scout_isolation,
    test_decompose_provenance_stub,
    test_code_map_read_on_demand,
    test_context_check_command,
]
# ---------------------------------------------------------------------------


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    missing = [r for r in REQUIRED_FILES if not (ROOT / r).exists()]
    if missing:
        for m in missing:
            print(f"FATAL: missing file {m}")
        return 2

    # Optional substring filter: python test_provenance_wiring.py commit_gate_heal
    tests = TESTS
    if argv:
        filter_str = argv[0]
        tests = [fn for fn in TESTS if filter_str in fn.__name__]
        if not tests:
            print(f"No tests match filter: {filter_str!r}")
            return 2

    for fn in tests:
        before = len(_failures)
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            _failures.append(f"{fn.__name__} raised {type(e).__name__}: {e}")
        if len(_failures) > before:
            print(f"FAIL  {fn.__name__} ({len(_failures) - before} assertion(s))")
        else:
            print(f"PASS  {fn.__name__}")

    if _failures:
        print(f"\nFAIL: {len(_failures)} assertion(s) total")
        for m in _failures:
            print(f"  - {m}")
        return 1
    print(f"\nOK: {len(tests)} check(s) green")
    return 0


if __name__ == "__main__":
    sys.exit(main())

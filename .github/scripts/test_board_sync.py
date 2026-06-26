#!/usr/bin/env python3
"""Structural tests for the commit-gate board-sync chokepoint (ADR-0008).

These are prose/command-doc assertions — content-presence checks that make the
spec's acceptance criteria (AC-07, AC-04, AC-05, AC-06, AC-11, and more)
executable and CI-enforced.

Assertions are deliberately COARSE — durable marker phrases, not exact wording —
so ordinary copy edits do not break the test.  Copy quality is carried by review,
not by this test.

Extending this harness (later tasks T-05/06/07/08/09):
  1. Add a ``test_*`` function above the "APPEND NEW" anchor.
  2. Register it in TESTS (see the anchor in that list).
  3. Add any new required file to REQUIRED_FILES (see anchor there).

Run: python .github/scripts/test_board_sync.py
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


# ---- AC-07: /ca:task doc states commit co-location (T-10) ----------------------
def test_task_doc_states_commit_colocation():
    t = read_repo("plugins/ca/commands/task.md").lower()
    check(
        "commit-gate" in t,
        "task.md: must name commit-gate as the board-sync chokepoint (ADR-0008)",
    )
    check(
        "work commit" in t,
        "task.md: must state that transitions ride the work commit",
    )
    check(
        "chore(board)" in t,
        "task.md: must name the chore(board) anti-pattern being eliminated",
    )


# ---- AC-04: commit-gate Phase 6 board-edit exemption (T-06) --------------------
def test_commit_gate_phase6_board_edit_exemption():
    t = read_repo("plugins/ca/skills/commit-gate/SKILL.md")
    phase6_start = t.find("## Phase 6")
    phase7_start = t.find("## Phase 7")
    if phase6_start == -1:
        check(False, "commit-gate SKILL.md: Phase 6 section not found")
        return
    if phase7_start == -1:
        check(False, "commit-gate SKILL.md: Phase 7 section not found")
        return
    phase6 = t[phase6_start:phase7_start]
    check(
        "classify_board_diff" in phase6,
        "commit-gate SKILL.md Phase 6: must name the classifier 'classify_board_diff'",
    )
    check(
        "open-tasks.md" in phase6,
        "commit-gate SKILL.md Phase 6: must reference 'open-tasks.md' in the board-edit exemption",
    )
    check(
        any(
            phrase in phase6.lower()
            for phrase in ["retained", "not scope creep", "not flagged as scope creep", "is expected"]
        ),
        "commit-gate SKILL.md Phase 6: must state that a clean transition board edit is retained / not scope creep",
    )


# ---- AC-05: commit-gate Phase 7 stages the board edit by explicit path (T-07) --
def test_commit_gate_phase7_stages_board_edit_by_path():
    t = read_repo("plugins/ca/skills/commit-gate/SKILL.md")
    phase7_start = t.find("## Phase 7")
    if phase7_start == -1:
        check(False, "commit-gate SKILL.md: Phase 7 section not found")
        return
    # Slice Phase 7 to the next "## " heading so the assertion cannot
    # be satisfied by the Phase 6 mention of open-tasks.md.
    next_section_start = t.find("\n## ", phase7_start + 1)
    phase7 = (
        t[phase7_start:next_section_start]
        if next_section_start != -1
        else t[phase7_start:]
    )
    check(
        "open-tasks.md" in phase7,
        "commit-gate SKILL.md Phase 7: must reference 'open-tasks.md' — "
        "the board edit retained by Phase 6 must be explicitly included in the selective stage",
    )
    check(
        any(
            phrase in phase7.lower()
            for phrase in [
                "git add",
                "by path",
                "by explicit path",
                "explicit path",
                "staged by path",
            ]
        ),
        "commit-gate SKILL.md Phase 7: must state that open-tasks.md is staged "
        "by explicit path (not wildcard)",
    )


# ---- AC-06: commit-gate harvest runs pre-commit at Phase 7 (T-08) ---------------
def test_commit_gate_harvest_pre_commit():
    t = read_repo("plugins/ca/skills/commit-gate/SKILL.md")
    phase7_start = t.find("## Phase 7")
    if phase7_start == -1:
        check(False, "commit-gate SKILL.md: Phase 7 section not found")
        return
    next_section_start = t.find("\n## ", phase7_start + 1)
    phase7 = (
        t[phase7_start:next_section_start]
        if next_section_start != -1
        else t[phase7_start:]
    )
    hard_rules_start = t.find("## Hard rules")
    hard_rules = t[hard_rules_start:] if hard_rules_start != -1 else ""

    # harvest must be mentioned in Phase 7 (this is the pre-commit timing addition)
    check(
        "harvest" in phase7.lower(),
        "commit-gate SKILL.md Phase 7: must mention the harvest step "
        "(raised tasks must ride the work commit, AC-06)",
    )
    # harvest must run before the commit — raised tasks ride the work commit
    check(
        any(
            phrase in phase7.lower()
            for phrase in [
                "before the commit",
                "before staging",
                "ride the work commit",
                "work commit",
            ]
        ),
        "commit-gate SKILL.md Phase 7: must state that the harvest runs before "
        "the commit so raised tasks ride the work commit (AC-06)",
    )
    # must-survive follow-ups go to a GitHub issue (stated in Phase 7 or hard-rules)
    check(
        "issue" in phase7.lower() or "issue" in hard_rules.lower(),
        "commit-gate SKILL.md: must state that a must-survive follow-up is filed "
        "as a GitHub issue, not the board (AC-06 atomicity rule)",
    )


# ---- AC-06: harvest.md documents commit-gate pre-commit timing (T-09) ----------
def test_harvest_md_commit_gate_pre_commit():
    t = read_repo("plugins/ca/includes/harvest.md").lower()
    # harvest.md must reference commit-gate in the context of pre-commit timing
    check(
        "commit-gate" in t,
        "harvest.md: must reference 'commit-gate' (pre-commit harvest timing, AC-06)",
    )
    # harvest.md must state that raised tasks ride the work commit / run before staging
    check(
        any(
            phrase in t
            for phrase in [
                "work commit",
                "ride the",
                "before staging",
                "pre-commit",
            ]
        ),
        "harvest.md: must state that raised tasks ride the work commit / "
        "harvest runs before staging (commit-gate pre-commit timing, AC-06)",
    )
    # harvest.md must document the must-survive → GitHub issue atomicity rule
    check(
        "issue" in t,
        "harvest.md: must state that a must-survive follow-up is filed as a "
        "GitHub issue, not the board (atomicity rule, AC-06)",
    )


# ---- AC-11: /ca:standup wires the advisory board-drift sweep (T-05) ------------
def test_standup_advisory_board_sweep():
    t = read_repo("plugins/ca/commands/standup.md").lower()
    check(
        "boardsync.py" in t or "reconcile" in t,
        "standup.md: must reference 'boardsync.py' or the 'reconcile' subcommand "
        "(advisory board-drift sweep, AC-11)",
    )
    check(
        any(phrase in t for phrase in ["advisory", "drift"]),
        "standup.md: must use 'advisory' or 'drift' to characterise the sweep (AC-11)",
    )
    check(
        any(phrase in t for phrase in ["never auto", "not auto", "never flip", "not flip",
                                       "never mutate", "not mutate", "never writes", "not written",
                                       "writes nothing", "does not write", "read-only"]),
        "standup.md: must state the sweep never auto-flips or mutates the board (AC-11)",
    )
    check(
        "/ca:task" in read_repo("plugins/ca/commands/standup.md"),
        "standup.md: must name '/ca:task' as the fix route for drifted tasks (AC-11)",
    )


# --- APPEND NEW test_* FUNCTIONS ABOVE THIS LINE --------------------------------
# Each new function must also be added to TESTS and (if it reads a new file)
# to REQUIRED_FILES below.


# ---------------------------------------------------------------------------
# Files that must exist before any test runs.
# Append new paths alongside new test_* functions above.
REQUIRED_FILES = [
    "plugins/ca/commands/task.md",
    "plugins/ca/skills/commit-gate/SKILL.md",
    # --- APPEND NEW REQUIRED FILES HERE ----------------------------------------
    "plugins/ca/includes/harvest.md",
    "plugins/ca/commands/standup.md",
]

TESTS = [
    test_task_doc_states_commit_colocation,
    test_commit_gate_phase6_board_edit_exemption,
    test_commit_gate_phase7_stages_board_edit_by_path,
    test_commit_gate_harvest_pre_commit,
    # --- APPEND NEW TESTS HERE --------------------------------------------------
    test_harvest_md_commit_gate_pre_commit,
    test_standup_advisory_board_sweep,
]
# ---------------------------------------------------------------------------


def main():
    missing = [r for r in REQUIRED_FILES if not (ROOT / r).exists()]
    if missing:
        for m in missing:
            print(f"FATAL: missing file {m}")
        return 2

    for fn in TESTS:
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
    print(f"\nOK: {len(TESTS)} check(s) green")
    return 0


if __name__ == "__main__":
    sys.exit(main())

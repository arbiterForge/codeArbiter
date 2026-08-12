#!/usr/bin/env python3
"""Structural test for the UX-conversion-trio sprint (#82 + #84 + #83).

These are prose/skill-body changes, so the obligations are content-presence and
content-absence assertions rather than behavioral unit tests. The test makes the
otherwise-inspectable obligations executable and CI-enforced.

Assertions are deliberately COARSE — durable marker phrases and a bold
`**Stakes:**` lead-in — not exact wording, so ordinary copy edits do not break
the test. Copy *quality* is carried by the two-pass review, not by this test.

Run: python .github/scripts/test_ux_conversion.py
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
CA = ROOT / "plugins" / "ca"

ORCH = CA / "arbiter.md"
SPRINT = CA / "SPRINT.md"
FINISH = CA / "skills" / "finishing-a-development-branch" / "SKILL.md"
TDD = CA / "skills" / "tdd" / "SKILL.md"
SECRET = CA / "skills" / "secret-handling" / "SKILL.md"
COMMIT = CA / "skills" / "commit-gate" / "SKILL.md"

ALL_FILES = [ORCH, SPRINT, FINISH, TDD, SECRET, COMMIT]

_failures = []


def check(cond, msg):
    if not cond:
        _failures.append(msg)


def read(p):
    return p.read_text(encoding="utf-8")


def section(text, heading_substr):
    """Return the body of the `## ...heading_substr...` block up to the next `## `.

    Heading match is case-insensitive on the substring. Returns "" if absent.
    """
    lines = text.splitlines()
    out, capturing = [], False
    for ln in lines:
        if ln.startswith("## "):
            if capturing:
                break
            capturing = heading_substr.lower() in ln.lower()
            continue
        if capturing:
            out.append(ln)
    return "\n".join(out)


# ---- #83 register split (T-01) -------------------------------------------------
def test_register_split():
    t = read(ORCH).lower()
    check("terse" in t, "ORCHESTRATOR: terse default must be retained")
    # 'exactly one' and 'warm' may be split by markdown emphasis (**exactly one** warm),
    # so assert the components rather than a brittle contiguous substring.
    check("exactly one" in t and "warm" in t,
          "ORCHESTRATOR: must permit exactly one warm synthesizing sentence")
    check("synthesi" in t, "ORCHESTRATOR: warm sentence must be 'synthesizing'")
    check("close" in t, "ORCHESTRATOR: warmth permitted 'at the close'")
    check("caught" in t, "ORCHESTRATOR: warmth permitted at a genuine 'caught' finding")
    check("routine green" in t,
          "ORCHESTRATOR: must forbid warmth on 'routine green' commits")
    check("no emojis" in t or "no emoji" in t, "ORCHESTRATOR: must forbid emojis")
    check("flattery" in t, "ORCHESTRATOR: must forbid flattery")


# ---- #82 Receipt close (T-02) --------------------------------------------------
def test_receipt_close():
    t = read(FINISH)
    low = t.lower()
    check("receipt" in low, "finishing: must add a Receipt close")
    check("obligations" in low, "Receipt: must list obligations covered")
    check("caught" in low, "Receipt: must list gates fired + what each caught")
    check("smarts" in low, "Receipt: must list the SMARTS decisions the user made")
    check("secret" in low and "prevented" in low,
          "Receipt: must list secrets/regressions prevented")
    check("suite time" in low, "Receipt: must list suite time")
    # sourcing: Phase-1 state + last-checkpoint only, no fresh crawl
    check("last-checkpoint" in low, "Receipt: must source from last-checkpoint")
    check("phase 1" in low, "Receipt: must source from Phase 1 state")
    check("no fresh audit" in low or "not a fresh audit" in low,
          "Receipt: must forbid a fresh audit-trail crawl")
    check("warm" in low, "finishing: must wire the one warm closing sentence")


# ---- #82 + #83 sprint summary aligned (T-03) -----------------------------------
def test_sprint_summary_aligned():
    body = section(read(SPRINT), "Land & summarize")
    low = body.lower()
    check("receipt" in low, "SPRINT Phase 3: summary must align to the Receipt shape")
    check("suite time" in low or "obligations" in low,
          "SPRINT Phase 3: summary must carry Receipt fields")
    check("warm" in low, "SPRINT Phase 3: must wire the one warm closing sentence")


# ---- #84 stakes on tdd finding blocks (T-04) -----------------------------------
def test_tdd_stakes():
    t = read(TDD)
    verify = section(t, "Obligation verify")  # Phase 4 — MISSING
    check("**stakes:**" in verify.lower(),
          "tdd Phase 4: a **Stakes:** line must state the consequence of a MISSING obligation")
    coverage = section(t, "Coverage")  # Phase 5 — below threshold
    check("**stakes:**" in coverage.lower(),
          "tdd Phase 5: a **Stakes:** line must state the consequence of coverage below threshold")
    # mechanical surfaces stay terse
    scan = section(t, "Obligation scan")  # Phase 1
    check("**stakes:**" not in scan.lower(),
          "tdd Phase 1 (obligation scan) must stay terse — no Stakes line")
    pre = t.split("## Phase 1")[0]  # pre-flight
    check("**stakes:**" not in pre.lower(),
          "tdd pre-flight must stay terse — no Stakes line")


# ---- #84 stakes on caught-secret (T-05) ----------------------------------------
def test_secret_stakes():
    t = read(SECRET)
    src = section(t, "Source")  # Phase 2 — hardcoded literal = the classic caught secret
    check("**stakes:**" in src.lower(),
          "secret-handling Phase 2: a **Stakes:** line must state the consequence of a caught secret")
    check("warm" in t.lower(),
          "secret-handling: must wire the one warm sentence on a genuine catch")


# ---- #84 stakes on commit-gate findings + mechanical terse (T-06) --------------
def test_commit_gate_stakes():
    t = read(COMMIT)
    proof = section(t, "Behavioral proof")  # Phase 5
    diff = section(t, "Diff review")        # Phase 6
    check("**stakes:**" in proof.lower(),
          "commit-gate Phase 5: a **Stakes:** line must state the consequence of a behavioral-proof mismatch")
    check("**stakes:**" in diff.lower(),
          "commit-gate Phase 6: a **Stakes:** line must state the consequence of a scope/credential finding")
    # mechanical gates stay terse
    for h in ("Branch", "Selective stage", "Message"):
        check("**stakes:**" not in section(t, h).lower(),
              f"commit-gate {h} must stay terse — no Stakes line")


# ---- global negatives: no ledger/counter/statusline (T-07) ---------------------
def test_no_ledger_or_statusline():
    banned = ("saves ledger", "saves-ledger", "per-gate counter",
              "statusline segment", "saves counter")
    for p in ALL_FILES:
        low = read(p).lower()
        for b in banned:
            check(b not in low,
                  f"{p.name}: must not introduce a '{b}' (rejected under challenge)")


def test_standup_sweep():
    """B-24/T-64: /ca:standup owns the archival sweep, PER ITEM.

    The sweep needs a lane with per-action confirmation and a
    never-destructive-without-a-yes contract, which is verbatim what D-2
    asked for. standup is that lane -- but only if it proposes each item
    separately. A batched "archive all 12?" turns twelve decisions into
    one, and the helper's per-item ordering (append to done-tasks first,
    then remove from open-tasks) is what makes an interrupted sweep
    recoverable; a batch loop answered once would throw that away.
    """
    for relative in ("core/surface/commands/standup.md",
                     "plugins/ca/commands/standup.md"):
        path = ROOT / relative
        if not path.exists():
            continue
        text = read(path)
        check("taskwrite.py" in text and "archive" in text,
              f"{relative}: the sweep does not name the archive helper")
        # BOTH, not either. A first draft used
        # `"each one" or "per item"`, and the section HEADING contains
        # "per item" on its own -- so mutating the instruction to "ask
        # once for all of them" left the check green. An OR across
        # phrases that appear independently in the same document asserts
        # almost nothing.
        # Anchored on the full instruction, not the bare phrase: "each
        # one" also appears in this file's opening paragraph about
        # confirmations, so a check keyed on it alone survives mutating
        # the instruction it is supposed to guard. Verified unique.
        check("ask about **each one" in text,
              f"{relative}: the instruction does not say to ask about each "
              "item separately")
        check("One confirmation per item, one helper call per item" in text,
              f"{relative}: the 1:1 confirmation-to-call contract is not stated")
        check("--allow-undated" in text,
              f"{relative}: undated items have no stated handling")
        check("Never archive without a yes" in text
              or "never archive without a yes" in text.lower(),
              f"{relative}: the never-without-a-yes contract is not stated")
        check("Declining is always available" in text,
              f"{relative}: declining is not offered as a first-class outcome")


TESTS = [
    test_standup_sweep,
    test_register_split,
    test_receipt_close,
    test_sprint_summary_aligned,
    test_tdd_stakes,
    test_secret_stakes,
    test_commit_gate_stakes,
    test_no_ledger_or_statusline,
]


def main():
    for p in ALL_FILES:
        if not p.exists():
            print(f"FATAL: missing file {p}")
            return 2
    for fn in TESTS:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            _failures.append(f"{fn.__name__} raised {type(e).__name__}: {e}")
    if _failures:
        print(f"FAIL: {len(_failures)} assertion(s)")
        for m in _failures:
            print(f"  - {m}")
        return 1
    print(f"OK: {len(TESTS)} obligation groups green")
    return 0


if __name__ == "__main__":
    sys.exit(main())

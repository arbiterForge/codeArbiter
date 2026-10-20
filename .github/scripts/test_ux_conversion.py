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


def test_delivery_report():
    body = " ".join(section(read(FINISH), "Delivery report").lower().split())
    check("phase 1 state" in body and "observed action result" in body,
          "delivery report must use observed branch/check evidence")
    check("remaining work" in body and "pending" in read(FINISH).lower(),
          "delivery must preserve outstanding work and missing evidence")
    check("verification, merge and publication distinct" in body,
          "delivery must distinguish checks, merge, and publication")
    check("infer verification from a checkpoint counter" in body,
          "checkpoint counters cannot establish verification")


# ---- #82 + #83 sprint summary aligned (T-03) -----------------------------------
def test_sprint_summary_aligned():
    # The assistive sprint reports work and actual checks, not an invented
    # receipt/approval certification. Retain the useful closing information
    # while explicitly refusing to promote local DONE into released proof.
    body = section(read(SPRINT), "Return an honest result")
    low = body.lower()
    check("implemented changes" in low and "actually run" in low,
          "SPRINT Phase 3: must report implemented work and checks actually run")
    check("unresolved defects/decisions" in low and "risk findings" in low,
          "SPRINT Phase 3: must retain unresolved issues and risks")
    check("what still requires verification" in low,
          "SPRINT Phase 3: must identify verification not yet performed")
    check("local `done` batch is not a shipped release" in low,
          "SPRINT Phase 3: local DONE must not imply a release")
    check("must not merge" in low and "without the appropriate separate authority" in low,
          "SPRINT Phase 3: must preserve actual Git/release permissions")


def test_verification_approaches():
    t = " ".join(read(TDD).lower().split())
    check("regression failing for the defect before repair" in t,
          "confirmed fixes require genuine regression evidence")
    check("an initially passing test is a valid baseline" in t,
          "characterization accepts existing correct behavior")
    check("record only observed results" in t,
          "verification must not invent test history")
    check("reuse current results" in t and "relevant source and inputs are unchanged" in t,
          "verification reuse must remain source-applicable")


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
    checked = 0
    for relative in ("core/surface/commands/standup.md",
                     "plugins/ca/commands/standup.md"):
        path = ROOT / relative
        if not path.exists():
            continue
        text = read(path)
        checked += 1
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
    check(checked > 0,
          "standup: all candidate surfaces are missing; sweep checked no files")


TESTS = [
    test_standup_sweep,
    test_register_split,
    test_delivery_report,
    test_sprint_summary_aligned,
    test_verification_approaches,
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

#!/usr/bin/env python3
# Fixture hook exercising the extractor's real-world call shapes.


def block(tag, msg):
    print(f"BLOCKED [{tag}]: {msg}")


def remind(tag, msg):
    print(f"REMINDER [{tag}]: {msg}")


def run():
    # Multi-line f-string call, with a placeholder split across the args.
    rel = "foo.md"
    count = 3
    remind("H-13", f"{rel}: found {count} issue(s) on line(s) "
                   f"{count} (nested check) — please fix before "
                   f"committing.")

    # Nested parens inside a plain string literal (must not be mistaken for
    # the call's own closing paren).
    block("H-05", "The audit log (overrides.log, triage.log) is append-only "
                  "(see ORCHESTRATOR §7). Truncation is prohibited.")

    # Explicit `+` concatenation, including a trailing non-literal call whose
    # own parens must be depth-tracked correctly.
    block("H-01", "Direct commit to main is prohibited." + _hint())

    # A second tag in the same file.
    remind("H-07", "Dependency manifest changed.")

    # A call whose tag is a variable, not a literal — must land in `skipped`,
    # not silently dropped.
    tag = "H-09b"
    block(tag, "sensitive content detected.")


def _hint():
    return " Retry."

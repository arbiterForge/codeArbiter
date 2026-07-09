#!/usr/bin/env python3
# codeArbiter — ORCHESTRATOR.md drift guard (issue #262, architecture-010).
#
# plugins/ca/ORCHESTRATOR.md and plugins/ca-codex/ORCHESTRATOR.md are
# hand-duplicated (ADR-0011 named a core/surface/ + tools/build-surface.py
# generator that would let the two controllably diverge, but that generator
# does not exist yet). Until it does, the correct contract is that the two
# files stay BYTE-IDENTICAL — an edit to one that forgets its twin silently
# ships divergent governance between the two hosts, with nothing to catch it.
# This is a drift GUARD, not the generator: it only asserts today's identity
# invariant. If a deliberate host-specific divergence is ever needed, that is
# a future change to this script (and ideally the real generator), not a
# reason to skip the guard now.
#
# Design invariants (mirror check_license_consistency.py / tools/sync-core.py):
#   - Stdlib only; zero side effects at import.
#   - Pure comparison function over already-read text; filesystem access
#     isolated to the named reader (read_text).
#   - Never raise on malformed/missing input — degrade to a surfaced finding.
#
# Public API:
#   first_diff_line(a, b) -> int | None
#   differs(a, b) -> bool
#   read_text(path) -> str | None
#   run_all(repo_root) -> list[str]
#   main(argv) -> int

import os
import sys

CA_ORCHESTRATOR = os.path.join("plugins", "ca", "ORCHESTRATOR.md")
CA_CODEX_ORCHESTRATOR = os.path.join("plugins", "ca-codex", "ORCHESTRATOR.md")


def differs(a, b):
    """True if the two texts are not identical."""
    return a != b


def first_diff_line(a, b):
    """1-based line number of the first line at which `a` and `b` diverge, or
    None if the texts are identical. A length mismatch (one text has fewer
    lines) reports the first line past the shorter text's end."""
    if a == b:
        return None
    a_lines = a.splitlines()
    b_lines = b.splitlines()
    for i, (la, lb) in enumerate(zip(a_lines, b_lines)):
        if la != lb:
            return i + 1
    return min(len(a_lines), len(b_lines)) + 1


def read_text(path):
    """File text, or None if missing / unreadable."""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def run_all(repo_root):
    """Read both ORCHESTRATOR.md surfaces under `repo_root` and return all
    findings (empty = the two files are byte-identical). A missing surface is
    itself a finding, never an exception."""
    ca_path = os.path.join(repo_root, CA_ORCHESTRATOR)
    codex_path = os.path.join(repo_root, CA_CODEX_ORCHESTRATOR)
    ca_text = read_text(ca_path)
    codex_text = read_text(codex_path)

    findings = []
    if ca_text is None:
        findings.append(f"{CA_ORCHESTRATOR}: missing or unreadable")
    if codex_text is None:
        findings.append(f"{CA_CODEX_ORCHESTRATOR}: missing or unreadable")
    if findings:
        return findings

    if differs(ca_text, codex_text):
        line = first_diff_line(ca_text, codex_text)
        findings.append(
            f"{CA_ORCHESTRATOR} and {CA_CODEX_ORCHESTRATOR} have diverged "
            f"(first differing line: {line}). These two files are "
            f"hand-duplicated (no generator yet, ADR-0011) and must stay "
            f"byte-identical — sync the edit to both, or if a deliberate "
            f"per-host divergence is intended, update this guard "
            f"(.github/scripts/check_orchestrator_parity.py) to reflect the "
            f"new contract.")
    return findings


def main(argv):
    """CLI: `check_orchestrator_parity.py [repo_root]`. Prints findings; exit 1 if any."""
    repo_root = argv[0] if argv else "."
    findings = run_all(repo_root)
    if findings:
        sys.stderr.write("orchestrator-parity check FAILED:\n")
        for f in findings:
            sys.stderr.write(f"  - {f}\n")
        return 1
    print("ORCHESTRATOR.md is byte-identical across plugins/ca and plugins/ca-codex")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
# codeArbiter — license-consistency CI check.
#
# Guards against a partial relicense: asserts the project's own license-
# declaration surfaces all agree with the canonical SPDX (ca's plugin.json
# `license`). Reads ONLY the enumerated surfaces below — never a repo-wide grep
# — so third-party (package-lock) and historical (CHANGELOG / ADR) license
# mentions can't false-positive. Motivated by the v2.6.0 relicense, which left
# the ca manifest, the README callout, and sibling manifests on stale
# declarations that human review kept missing.
#
# Design invariants (mirror the other .github/scripts checks and _*lib.py):
#   - Stdlib only; zero side effects at import.
#   - Pure functions over synthetic input; filesystem access isolated to the
#     named readers (read_manifest_license / read_text).
#   - Never raise on malformed input — degrade to a surfaced finding, since a
#     CI check that crashes is worse than one that reports a problem.
#
# Public API:
#   resolve_family(spdx) -> dict | None
#   check_manifest_agreement(canonical_spdx, manifest_licenses) -> list[str]
#   check_license_file(family, license_text) -> list[str]
#   check_readme_badge(family, readme_text) -> list[str]
#   check_readme_notice(family, readme_text) -> list[str]
#   check_offering_prose(readme_text) -> list[str]
#   read_manifest_license(path) -> str | None
#   read_text(path) -> str | None
#   evaluate(canonical_spdx, manifest_licenses, license_text, readme_text) -> list[str]
#   run_all(repo_root) -> list[str]
#   main(argv) -> int

import json
import os
import sys

# The canonical license lives in ca's manifest; every other surface must agree.
CANONICAL_MANIFEST = "plugins/ca/.claude-plugin/plugin.json"
MANIFESTS = [
    "plugins/ca/.claude-plugin/plugin.json",
    "plugins/ca-sandbox/.claude-plugin/plugin.json",
    "plugins/ca-codex/.codex-plugin/plugin.json",
    "plugins/ca-pi/package.json",
    "package.json",
]
LICENSE_FILE = "LICENSE"
README_FILE = "README.md"

# Prior licenses the project has moved off of. A manifest still declaring one is
# a stale (incomplete) relicense, called out distinctly from a generic mismatch
# so the failure reads as "this surface wasn't updated", not just "wrong value".
KNOWN_PRIOR_LICENSES = {"MIT"}

# Retired commercial-OFFERING phrasing. License-agnostic prose guard: the owner
# reserves the right to dual-license but does not offer it, so phrasing that
# implies an active commercial offering must not reappear in the README.
FORBIDDEN_OFFERING_PHRASES = ["available separately", "offers the same code"]

# Per-SPDX identifying markers on each surface. A future relicense adds an entry
# here (and changes ca's manifest); the check then forces every other surface to
# match — so the check is license-agnostic, not pinned to AGPL.
LICENSE_FAMILIES = {
    "AGPL-3.0-only": {
        "license_file_markers": ["GNU AFFERO GENERAL PUBLIC LICENSE", "Version 3"],
        "badge_marker": "license-AGPL_v3",
        "prose_marker": "AGPLv3",
    },
}


def resolve_family(spdx):
    """Return the family token map for `spdx`, or None if there is no entry."""
    if not isinstance(spdx, str):
        return None
    return LICENSE_FAMILIES.get(spdx)


def check_manifest_agreement(canonical_spdx, manifest_licenses):
    """Findings for any manifest whose `license` != `canonical_spdx`. A value in
    KNOWN_PRIOR_LICENSES is flagged as a stale relicense; any other mismatch as a
    generic disagreement. `manifest_licenses` maps path -> license string."""
    findings = []
    for path, val in sorted(manifest_licenses.items()):
        if val == canonical_spdx:
            continue
        if val in KNOWN_PRIOR_LICENSES:
            findings.append(
                f"{path}: declares prior license '{val}'; expected canonical "
                f"'{canonical_spdx}' (relicense incomplete)")
        else:
            findings.append(
                f"{path}: license '{val}' does not match canonical '{canonical_spdx}'")
    return findings


def check_license_file(family, license_text):
    """Findings if the LICENSE text is missing any family-identifying marker."""
    if not isinstance(family, dict) or not isinstance(license_text, str):
        return [f"{LICENSE_FILE}: unreadable, or no license family to match against"]
    return [f"{LICENSE_FILE}: missing expected marker '{marker}'"
            for marker in family.get("license_file_markers", []) if marker not in license_text]


def check_readme_badge(family, readme_text):
    """Findings if the README lacks the family's license badge marker."""
    if not isinstance(family, dict) or not isinstance(readme_text, str):
        return [f"{README_FILE}: unreadable, or no license family to match against"]
    marker = family.get("badge_marker", "")
    if marker and marker not in readme_text:
        return [f"{README_FILE}: license badge '{marker}' not found"]
    return []


def check_readme_notice(family, readme_text):
    """Findings if the README never names the canonical license (family prose marker)."""
    if not isinstance(family, dict) or not isinstance(readme_text, str):
        return [f"{README_FILE}: unreadable, or no license family to match against"]
    marker = family.get("prose_marker", "")
    if marker and marker not in readme_text:
        return [f"{README_FILE}: license notice does not name '{marker}'"]
    return []


def check_offering_prose(readme_text):
    """Findings for any retired commercial-offering phrase present in the README."""
    if not isinstance(readme_text, str):
        return []
    low = readme_text.lower()
    return [f"{README_FILE}: retired offering phrase '{p}' present"
            for p in FORBIDDEN_OFFERING_PHRASES if p in low]


def read_manifest_license(path):
    """The `license` field of a JSON manifest, or None if missing / unparseable / absent."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    val = data.get("license") if isinstance(data, dict) else None
    return val if isinstance(val, str) else None


def read_text(path):
    """File text, or None if missing / unreadable."""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def evaluate(canonical_spdx, manifest_licenses, license_text, readme_text):
    """Aggregate every check over already-read inputs. An unknown canonical SPDX
    (no LICENSE_FAMILIES entry) is itself a finding, and the family-dependent
    surface checks are skipped (there is nothing to match against)."""
    findings = list(check_manifest_agreement(canonical_spdx, manifest_licenses))
    family = resolve_family(canonical_spdx)
    if family is None:
        findings.append(
            f"{CANONICAL_MANIFEST}: canonical license '{canonical_spdx}' has no license "
            f"family mapping (no LICENSE_FAMILIES entry) — add one so the surfaces can be checked")
    else:
        findings += check_license_file(family, license_text)
        findings += check_readme_badge(family, readme_text)
        findings += check_readme_notice(family, readme_text)
    findings += check_offering_prose(readme_text)
    return findings


def run_all(repo_root):
    """Read every surface under `repo_root` and return all findings (empty = consistent).
    A missing required surface is a finding, never an exception."""
    canonical = read_manifest_license(os.path.join(repo_root, CANONICAL_MANIFEST))
    if canonical is None:
        return [f"{CANONICAL_MANIFEST}: missing or no readable `license` field "
                f"(cannot determine the canonical license)"]

    findings = []
    manifest_licenses = {}
    for rel in MANIFESTS:
        val = read_manifest_license(os.path.join(repo_root, rel))
        if val is None:
            findings.append(f"{rel}: missing or no readable `license` field")
        else:
            manifest_licenses[rel] = val

    license_text = read_text(os.path.join(repo_root, LICENSE_FILE))
    if license_text is None:
        findings.append(f"{LICENSE_FILE}: missing or unreadable")
    readme_text = read_text(os.path.join(repo_root, README_FILE))
    if readme_text is None:
        findings.append(f"{README_FILE}: missing or unreadable")

    findings += evaluate(canonical, manifest_licenses, license_text or "", readme_text or "")

    seen, deduped = set(), []  # a missing-file finding can echo a downstream check finding
    for f in findings:
        if f not in seen:
            seen.add(f)
            deduped.append(f)
    return deduped


def main(argv):
    """CLI: `check_license_consistency.py [repo_root]`. Prints findings; exit 1 if any."""
    repo_root = argv[0] if argv else "."
    findings = run_all(repo_root)
    if findings:
        sys.stderr.write("license-consistency check FAILED:\n")
        for f in findings:
            sys.stderr.write(f"  - {f}\n")
        return 1
    print("license declarations consistent across all surfaces")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

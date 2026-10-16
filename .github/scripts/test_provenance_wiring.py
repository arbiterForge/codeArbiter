#!/usr/bin/env python3
"""Tests for provenance auto-heal and current context evidence wiring.

Prose assertions preserve the workflow boundaries; read-only v2 assessment
checks the enrolled code map's actual source and document identities. Temporary
negative fixtures are not current repository or host-qualification evidence.

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
import copy
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "plugins/ca/hooks"))

import _contextsnapshotlib as snapshots  # noqa: E402
import _provenancelib as provenance  # noqa: E402


def read_repo(relative_path):
    """Read a repo file by path relative to the repository root."""
    return (ROOT / relative_path).read_text(encoding="utf-8")


_failures = []


def check(cond, msg):
    if not cond:
        _failures.append(msg)


def claim_names_version(claim, claim_prefix, version):
    """Return whether a provenance claim names the expected manifest version."""
    return re.match(
        rf"^{re.escape(claim_prefix)} \(v{re.escape(version)}(?:\)|,)", claim
    ) is not None


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

    # Context evidence records its actual method; the decision-variance recipe
    # above is not a required collector for ordinary context inspection.
    phase2_start = skill.find("## Phase 2")
    phase3_start = skill.find("## Phase 3")
    if phase2_start == -1 or phase3_start == -1:
        check(False, "context-creation SKILL.md: Phase 2 or Phase 3 section not found")
        return
    phase2 = skill[phase2_start:phase3_start]
    words = " ".join(phase2.split())
    for phrase in ("searched scope and predicates", "path/line citation",
                   "digest and its method", "observed/inferred/unknown",
                   "git-blob-normalized-sha1", "sha256-raw",
                   "not verify a claim's meaning", "Never forward secret values"):
        check(phrase in words,
              f"context-creation evidence must retain {phrase!r}")

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
    words = " ".join(phase5.split())
    for phrase in ("context-preview", "context-apply", "preview_ref",
                   "preview_sha256", "each selected document and its v2",
                   "Never write either side of this pair directly",
                   "does not stand in for semantic review"):
        check(phrase in words, f"context native-writer contract must retain {phrase!r}")


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
    words = " ".join(skill.split())
    for phrase in ("Never change an unselected derived document",
                   "exact expected document/provenance hashes",
                   "selected fields", "preview_ref", "preview_sha256",
                   "rechecks", "under its lock", "semantic: unverified",
                   "verified_fresh: false", "never authorizes raw Write/Edit fallback"):
        check(phrase in words, f"context-check must retain {phrase!r}")


def test_context_creation_bounded_optional_delegation():
    skill = read_repo("plugins/ca/skills/context-creation/SKILL.md")
    codex_skill = read_repo("plugins/ca-codex/routines/context-creation/SKILL.md")
    scout = read_repo("plugins/ca/agents/scout.md")
    codex_notes = read_repo("plugins/ca-codex/includes/codex-host-notes.md")

    phase2_start = skill.find("## Phase 2")
    phase3_start = skill.find("## Phase 3")
    codex_phase2_start = codex_skill.find("## Phase 2")
    codex_phase3_start = codex_skill.find("## Phase 3")
    if min(phase2_start, phase3_start, codex_phase2_start, codex_phase3_start) == -1:
        check(False, "context-creation bounded-inspection sections must exist")
        return
    phase2 = skill[phase2_start:phase3_start]
    codex_phase2 = codex_skill[codex_phase2_start:codex_phase3_start]
    scout_words = " ".join(scout.lower().split())

    for host, phase in (("Claude", phase2), ("Codex", codex_phase2)):
        phase_words = " ".join(phase.lower().split())
        for phrase in (
            "direct bounded inspection or optional scoped agents",
            "six categories do not require six agents or parallel execution",
            "actual host permissions", "excluded paths and secret-handling rules",
            "finite path/category assignment", "current source identity",
            "output limit and stopping condition", "failed, partial and conflicting",
            "not evidence of containment or independent verification",
            "separately required containment policy still applies",
            "failed or missing work never counts as inspected coverage",
        ):
            check(phrase in phase_words,
                  f"{host} bounded context inspection must retain {phrase!r}")
        for obsolete in ("block before dispatch unless", "no inline fallback"):
            check(obsolete not in phase_words,
                  f"{host} ordinary context inspection must not require {obsolete!r}")
    check(
        "under ~50 files, `decision-variance` scans inline" in scout_words
        and "direct bounded inspection or optional scoped agents" in scout_words
        and "six logical categories do not require six children" in scout_words,
        "scout charter must distinguish decision-variance sizing from optional context agents",
    )
    for phrase in ("do not modify files, execute repository scripts or spawn further agents",
                   "not evidence of containment", "do not invent an envelope or receipt",
                   "do not turn a missing report or an incomplete search into a negative finding"):
        check(phrase in scout_words, f"scout evidence boundary must retain {phrase!r}")
    notes_words = " ".join(codex_notes.lower().split())
    check(
        "context inspection may run directly or use optional scoped agents" in notes_words
        and "a role label does not prove isolation or verification" in notes_words
        and "never label self-review independent" in notes_words,
        "Codex host notes must support direct inspection without false independence claims",
    )


def record_snapshot(record, root=ROOT):
    """Acquire only the source identities declared by this enrolled v2 record."""
    evidence = [item for field in record["fields"] for claim in field["claims"]
                for item in claim["evidence"]]
    return snapshots.context_snapshot(
        root,
        source_paths=sorted({item["path"] for item in evidence if item["kind"] == "content"}),
        membership=sorted({(item["predicate"], tuple(item["scope_paths"]))
                           for item in evidence if item["kind"] == "membership"}),
        target_paths=(record["document"]["path"],),
    )


def test_code_map_provenance_identities_are_current():
    """Native v2 adoption binds actual document/source bytes, not frozen prose."""
    record = json.loads(read_repo(".codearbiter/.provenance/code-map.json"))
    valid = provenance.valid_provenance_record(record) and record.get("schema") == 2
    check(valid and record.get("doc") == "code-map", "code-map must retain valid enrolled v2 provenance")
    if not valid:
        return
    status = provenance.assess_context_provenance(
        ROOT / ".codearbiter/.provenance", ["code-map"], record_snapshot(record))
    check(status["coverage"] == "complete" and status["identity"] == "current"
          and status["documents"] == {"code-map": "v2_current"},
          f"code-map document/source identities must match current bytes: {status}")
    check(status["semantic"] == "unverified" and not status["verified_fresh"],
          "current source/document identities must not manufacture semantic verification")


def test_code_map_provenance_rejects_stale_or_incomplete_evidence():
    """A fixture probe cannot make stale, malformed or legacy evidence current."""
    good = json.loads(read_repo(".codearbiter/.provenance/code-map.json"))
    snapshot = record_snapshot(good)
    stale_document = copy.deepcopy(good)
    stale_document["document"]["digest"] = "0" * 64
    stale_source = copy.deepcopy(good)
    stale_source["fields"][0]["claims"][0]["evidence"][0]["digest"] = "0" * 64
    empty = copy.deepcopy(good)
    empty["fields"][0]["claims"][0]["evidence"] = []
    wrong_method = copy.deepcopy(good)
    wrong_method["document"]["digest_method"] = "git-blob-normalized-sha1"
    for name, record in (("document drift", stale_document), ("source drift", stale_source),
                         ("missing evidence", empty), ("wrong digest method", wrong_method),
                         ("legacy stub", provenance.new_record("code-map"))):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "code-map.json").write_text(json.dumps(record), encoding="utf-8")
            status = provenance.assess_context_provenance(
                directory, ["code-map"], snapshot,
                snapshot_probe=lambda _: {"source_current": True, "targets_current": True})
        check(status["identity"] != "current"
              and status["documents"].get("code-map") != "v2_current",
              f"{name} must not count as current v2 evidence")
        check(status["semantic"] == "unverified" and not status["verified_fresh"],
              f"{name} must not become semantic proof")


def test_code_map_manifest_ownership_matches_sources():
    """The coarse map points to current manifest owners without pinning versions."""
    text = read_repo(".codearbiter/code-map.md")
    entries = dict(re.findall(r"^- `([^`]+)` [—–-]+ (.+)$", text, re.MULTILINE))
    for path, owner in (("plugins/ca/.claude-plugin/plugin.json", "Claude"),
                        ("plugins/ca-codex/.codex-plugin/plugin.json", "Codex")):
        manifest = json.loads(read_repo(path))
        root = str(Path(path).parent.parent.as_posix()) + "/"
        role = entries.get(root, "")
        check(Path(root).name == manifest["name"] and f"{owner} manifest" in role,
              f"code-map host ownership must match the actual manifest at {path}")
    pi = json.loads(read_repo("plugins/ca-pi/package.json"))
    for extension in pi["pi"]["extensions"]:
        directory = (Path("plugins/ca-pi") / extension).parent.as_posix() + "/"
        check("Built" in entries.get(directory, "") and "Pi" in entries[directory],
              f"code-map must locate the built Pi extension declared in {extension}")
    check("owning manifests and catalogs" in " ".join(text.split()),
          "the coarse map must direct mutable version/catalog queries to their owners")


def test_context_provenance_preserves_checkout_bytes():
    """A real autocrlf checkout preserves bound bytes; genuine edits stay stale."""
    record_paths = [f".codearbiter/.provenance/{doc}.json"
                    for doc in provenance.V2_DOCUMENTS]
    records = [json.loads(read_repo(path)) for path in record_paths]
    if not all(provenance.valid_provenance_record(record)
               and record.get("schema") == 2 for record in records):
        raise ValueError("checkout fixture requires valid enrolled v2 records")
    sources = {item["path"] for record in records for field in record["fields"]
               for claim in field["claims"] for item in claim["evidence"]
               if item["kind"] == "content"}
    paths = sorted(sources | set(record_paths) | {".gitattributes"}
                   | {record["document"]["path"] for record in records})
    expected = {path: (ROOT / path).read_bytes() for path in paths}
    with tempfile.TemporaryDirectory(prefix="ca-context-checkout-") as directory:
        checkout = Path(directory).resolve()

        def git(*args, **kwargs):
            return subprocess.run(["git", "-C", str(checkout), *args],
                                  check=True, capture_output=True, **kwargs)

        # Index the actual selected worktree bytes, including uncommitted
        # attributes or native provenance updates. Never substitute HEAD's
        # older records or change the source repository's index/configuration.
        git("init", "--quiet")
        git("config", "core.autocrlf", "false")
        for path, raw in expected.items():
            target = checkout / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        git("add", "--", *paths)
        git("config", "core.autocrlf", "true")
        # Force materialization through Git's filters rather than letting its
        # unchanged-index stat cache retain the bytes used to seed the fixture.
        for path in paths:
            (checkout / path).unlink()
        git("checkout-index", "--force", "--all")
        for path, raw in expected.items():
            check((checkout / path).read_bytes() == raw,
                  f"autocrlf checkout must preserve exact context/evidence bytes: {path}")

        store = checkout / ".codearbiter/.provenance"
        for record in records:
            snapshot = record_snapshot(record, checkout)
            status = provenance.assess_context_provenance(store, [record["doc"]], snapshot)
            check(status["coverage"] == "complete" and status["identity"] == "current"
                  and status["documents"] == {record["doc"]: "v2_current"},
                  f"unaltered autocrlf checkout must retain current {record['doc']} identity")
            check(status["semantic"] == "unverified" and not status["verified_fresh"],
                  "byte-preserving checkout must not manufacture semantic verification")
        record = next(record for record in records if record["doc"] == "code-map")
        source = next(item["path"] for field in record["fields"]
                      for claim in field["claims"] for item in claim["evidence"]
                      if item["kind"] == "content")
        for path in (record["document"]["path"], source):
            before = (checkout / path).read_bytes()
            snapshot = record_snapshot(record, checkout)
            (checkout / path).write_bytes(before + b"\nActual content edit.\n")
            status = provenance.assess_context_provenance(store, ["code-map"], snapshot)
            check(status["identity"] == "stale"
                  and status["documents"].get("code-map") == "v2_stale"
                  and not status["verified_fresh"],
                  f"real edit must remain stale after byte-preserving checkout: {path}")
            (checkout / path).write_bytes(before)


def test_code_map_manifest_claim_rejects_version_prefix_collision():
    """Retained legacy version claims still need exact matching when present."""
    claim = "npm package manifest for ca-pi (v0.14.30, @arbiterforge/ca-pi)"
    check(claim_names_version(claim, "npm package manifest for ca-pi", "0.14.30"),
          "an exact legacy manifest version must match")
    check(
        not claim_names_version(claim, "npm package manifest for ca-pi", "0.14.3"),
        "code-map provenance version matching must reject longer prefix collisions",
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
    ".codearbiter/code-map.md",
    ".codearbiter/.provenance/code-map.json",
    ".codearbiter/CONTEXT.md",
    ".codearbiter/.provenance/CONTEXT.json",
    ".codearbiter/tech-stack.md",
    ".codearbiter/.provenance/tech-stack.json",
    ".codearbiter/coding-standards.md",
    ".codearbiter/.provenance/coding-standards.json",
    ".codearbiter/security-controls.md",
    ".codearbiter/.provenance/security-controls.json",
    ".gitattributes",
    "plugins/ca/.claude-plugin/plugin.json",
    "plugins/ca-codex/.codex-plugin/plugin.json",
    "plugins/ca-pi/package.json",
]

TESTS = [
    test_commit_gate_heal_phase,
    # --- APPEND NEW TESTS HERE --------------------------------------------------
    test_context_creation_provenance,
    test_context_creation_bounded_optional_delegation,
    test_decompose_provenance_stub,
    test_code_map_read_on_demand,
    test_context_check_command,
    test_code_map_provenance_identities_are_current,
    test_code_map_provenance_rejects_stale_or_incomplete_evidence,
    test_code_map_manifest_ownership_matches_sources,
    test_context_provenance_preserves_checkout_bytes,
    test_code_map_manifest_claim_rejects_version_prefix_collision,
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

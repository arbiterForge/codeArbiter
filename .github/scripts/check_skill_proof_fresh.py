#!/usr/bin/env python3
"""Fail when the recorded agent-judgment proof no longer covers the shipped
release skill (T-79, .codearbiter/plans/portable-release-and-protected-
state.md; AC-6.8, .codearbiter/specs/release-portable-fixture.md).

Non-mutating: reads the proof artifact and the shipped skill, prints a
report, and exits 0 or 1. Never writes anything.

WIRING (now done). This script is a declared `pre-tag` command on the `ca`
row of `.codearbiter/release-targets.md` (DECISION-0034: check-only,
non-mutating pre-tag commands), modeled on the existing
`check_badge_consistency.py` row.

It was deliberately left unwired when first written, because the artifact
it reads (`.codearbiter/reports/agent-lane-proof.json`) then recorded
`proof_current: false`: the first agent-judgment exercise had run against a
pre-remediation skill, and every finding it drove had since edited that
skill. Wiring it then would have shipped a permanently-red command on
`ca`'s row, violating this repo's own "declared rows run green" bar.

Three blind exercises were run in total, each against the skill as the
previous one left it, finding 4 HIGHs, then 2, then 0. The third run is
what made the artifact recordable: it found no HIGH-severity defect, so
its hash could be written as a current proof without a pending fix
immediately invalidating it. That hash is what this script now enforces.

The standing consequence, stated plainly: ANY edit to
`plugins/ca/skills/release/SKILL.md` now fails `ca`'s pre-tag gate until a
fresh exercise is run and the artifact refreshed. That is the point, not a
side effect. Hand-editing `proof_current` back to true without re-running
the exercise defeats the only check in this repo that covers whether an
agent can actually follow the release prose — a property all three runs
showed a green mechanical suite does not imply.

WHICH PAYLOAD THIS PROOF COVERS, AND WHY
-----------------------------------------
The release skill ships as FIVE rendered payloads (core/hosts.json's three
governance hosts, times two source templates — see the "Source of truth"
table in .codearbiter/specs/release-portable-fixture.md, and
`_RELEASE_SKILL_PAYLOADS` in .github/scripts/test_consumer_smoke.py, which
enumerates the same five for a different purpose). THREE carry the skill's
full prose, rendered from the one shared source template
`core/surface/skills/release/SKILL.md`:

  - plugins/ca/skills/release/SKILL.md              (claude)
  - plugins/ca-codex/routines/release/SKILL.md       (codex)
  - plugins/ca-pi/routines/release/SKILL.md          (pi)

TWO are thin per-host router stubs rendered from `commands/release.md`
(`plugins/ca-codex/skills/ca-release/SKILL.md`,
`plugins/ca-pi/skills/ca-release/SKILL.md`); they carry no prose of their
own — proven directly by
`test_consumer_smoke.py::test_stub_release_skills_contribute_no_unresolved_refs`
— so a prose-freshness hash has nothing of substance to say about them.

The T-78 agent-judgment exercise (`.codearbiter/reports/agent-lane-
proof.json`) was run EXACTLY ONCE, by handing an agent the INSTALLED
`claude`-host rendering (`plugins/ca/skills/release/SKILL.md`) with no
other artifact and no expected-outcome briefing. That is the only
rendering any agent has actually read and acted on, so it is the only
rendering this checker's hash can honestly attest to. The artifact records
exactly one proof-grade hash pair
(`exercise.exercised_skill_path`/`exercise.exercised_skill_sha256`); its
separate `post_remediation_skill_sha256` block, which additionally records
hashes for the `ca-codex`/`ca-pi` routine copies and the `core/surface/`
source template, is explicitly self-disclaimed inside the artifact as "NOT
a proof hash" and is deliberately never read as a proof source here.

This is a NARROW scope, stated rather than silently assumed. The
`ca-codex`/`ca-pi` routine renderings share the same `core/surface/` source
prose as `ca`'s, and are proven byte-consistent with it — unconditionally,
on every PR — by `tools/sync-core.py --check` / `tools/build-surface.py
--check` elsewhere in this repo's CI. But neither has been independently
exercised by an agent, and this script does not fabricate that coverage by
hashing a payload nobody has actually read. A prose edit that desynced
`claude`'s rendering from the other two without tripping build-surface
--check would not be caught here either; that is a build-surface defect,
guarded by its own suite, not this one's job. Extending the agent-judgment
proof itself to the other two hosts needs a second (and third) exercise
run and a second (and third) recorded hash — a future, explicit widening of
the artifact schema, not something this script should silently claim it
already does.

The candidate PAYLOAD SET (which paths are release-skill payloads, and
which host renders the recorded path) is DERIVED from core/hosts.json via
tools/build-surface.py's own descriptor-resolution logic
(`load_host_descriptors` + `_output_rel`), never hardcoded as a literal
path list. `.github/scripts/known-unresolved-refs.txt`'s ratchet
under-scoped itself exactly this way, twice, before the spec's "Source of
truth" table caught it (missed `ca-pi`'s routines copy, then missed
`ca-codex`'s too) — this script does not repeat that mistake for its own,
narrower, single-recorded-path check.

FAILURE MODES (each is a distinguishable, declared reason; every one is
exercised by a revert-and-restore test in test_check_skill_proof_fresh.py)
--------------------------------------------------------------------------
Returns at least one error string, never raising, when:
  - the artifact file at `.codearbiter/reports/agent-lane-proof.json` is
    missing or unreadable
  - the artifact is not parseable JSON
  - `proof_current` is not literally `true` (missing, `false`, or any other
    value)
  - the artifact's `exercise` object is missing, or is missing
    `exercised_skill_path` / `exercised_skill_sha256`
  - `exercised_skill_path` does not name a payload that core/hosts.json's
    descriptors currently render from `skills/release/SKILL.md` (the
    source template may have moved, or the recorded path was never a real
    payload)
  - the file at `exercised_skill_path` no longer exists on disk
  - the current sha256 of that file's raw bytes does not equal
    `exercised_skill_sha256`

Run: python .github/scripts/check_skill_proof_fresh.py   (exit 1 on drift)
"""
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_PATH = REPO_ROOT / ".codearbiter" / "reports" / "agent-lane-proof.json"
_BUILD_SURFACE_PATH = REPO_ROOT / "tools" / "build-surface.py"

# The one source template every full-prose release-skill payload renders
# from. Rendered path differs per host (`_output_rel`); the source path
# does not.
_RELEASE_SKILL_SOURCE_REL = "skills/release/SKILL.md"


class ProofFreshnessError(Exception):
    """The payload derivation itself no longer holds — a declared, named
    reason, never a silent skip."""


def _load_build_surface():
    """Load tools/build-surface.py by path, the same pattern
    test_ci_impact.py already uses for its own tools/ dependencies."""
    spec = importlib.util.spec_from_file_location(
        "check_skill_proof_fresh_build_surface", _BUILD_SURFACE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def full_prose_release_skill_payloads(repo=REPO_ROOT, build_surface=None):
    """{plugin-relative path (with plugin_dir): host name} for every
    FULL-PROSE release-skill payload, derived from core/hosts.json's
    descriptor resolution of `skills/release/SKILL.md` — never hardcoded
    (see the module docstring's "WHICH PAYLOAD" section).

    Deliberately excludes the two per-host router STUBS
    (`skills/ca-release/SKILL.md`, rendered from a DIFFERENT source
    template, `commands/release.md`): they carry no prose of their own and
    are out of scope for a prose-freshness hash.

    `build_surface` is injectable for testing against a synthetic
    descriptor set with no dependency on core/hosts.json; defaults to the
    real tools/build-surface.py loaded by path.
    """
    build_surface = build_surface or _load_build_surface()
    descriptors = build_surface.load_host_descriptors(repo)
    payloads = {}
    for descriptor in descriptors:
        dst, _rule = build_surface._output_rel(_RELEASE_SKILL_SOURCE_REL, descriptor)
        if dst is None:
            raise ProofFreshnessError(
                f"core/hosts.json's {descriptor.name!r} host descriptor no "
                f"longer renders a release-skill payload from "
                f"core/surface/{_RELEASE_SKILL_SOURCE_REL} — the payload "
                "derivation this checker relies on no longer holds; a "
                "human needs to reconcile this script with the new "
                "core/hosts.json shape before it can be trusted again"
            )
        payloads[f"{descriptor.plugin_dir}/{dst}"] = descriptor.name
    return payloads


def sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def check(repo=REPO_ROOT, artifact_path=ARTIFACT_PATH, build_surface=None):
    """Return a list of freshness errors — empty means the recorded T-78
    proof still covers the shipped release skill. Never raises and never
    mutates anything on disk."""
    repo = str(repo)
    artifact_path = str(artifact_path)

    if not os.path.isfile(artifact_path):
        return [f"missing proof artifact: {artifact_path!r}"]
    try:
        with open(artifact_path, encoding="utf-8") as fh:
            document = json.load(fh)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return [f"{artifact_path!r} is not parseable JSON: {error}"]

    if not isinstance(document, dict):
        return [
            f"{artifact_path!r} is valid JSON but not a JSON object "
            f"(got {type(document).__name__}) — cannot read proof_current "
            "or exercise from it"
        ]

    if document.get("proof_current") is not True:
        return [
            f"{artifact_path!r} records proof_current={document.get('proof_current')!r}, "
            "not true — the recorded T-78 agent-judgment exercise does not "
            "currently cover the shipped release skill. Re-run the "
            "exercise against the shipped skill, then set proof_current "
            "to true and record the hash actually exercised."
        ]

    exercise = document.get("exercise")
    if not isinstance(exercise, dict):
        return [f"{artifact_path!r} carries no 'exercise' object to read a proof hash from"]

    recorded_path = exercise.get("exercised_skill_path")
    recorded_hash = exercise.get("exercised_skill_sha256")
    if not isinstance(recorded_path, str) or not recorded_path:
        return [f"{artifact_path!r}'s exercise.exercised_skill_path is missing or empty"]
    if not isinstance(recorded_hash, str) or not recorded_hash:
        return [f"{artifact_path!r}'s exercise.exercised_skill_sha256 is missing or empty"]

    try:
        payloads = full_prose_release_skill_payloads(repo, build_surface)
    except ProofFreshnessError as error:
        return [str(error)]

    if recorded_path not in payloads:
        return [
            f"{recorded_path!r} (recorded in {artifact_path!r}) is not a "
            "full-prose release-skill payload core/hosts.json currently "
            "renders — the recorded path no longer names a shipped skill"
        ]

    absolute = os.path.join(repo, *recorded_path.split("/"))
    if not os.path.isfile(absolute):
        return [
            f"{recorded_path!r} (recorded in {artifact_path!r}) no longer "
            "exists on disk"
        ]

    current_hash = sha256_file(absolute)
    if current_hash.lower() != recorded_hash.lower():
        return [
            f"{recorded_path!r} has changed since the T-78 agent-judgment "
            f"exercise ran: recorded sha256={recorded_hash}, current "
            f"sha256={current_hash}. Re-run the exercise against the "
            f"shipped skill, update {artifact_path!r}, and only then set "
            "proof_current back to true."
        ]
    return []


def main(repo=None, artifact_path=None):
    """CLI entry. Exit 0 when the proof still covers the shipped skill.

    `repo`/`artifact_path` are pass-throughs to `check`, present ONLY so a
    test can drive the FAILING branch below against a fixture. Without them
    `main` could only ever be exercised on the live repo, where the proof is
    green by definition -- so the error path, the one that has to work on
    the day it fires, was never run.
    """
    errors = check(**{k: v for k, v in
                      (("repo", repo), ("artifact_path", artifact_path))
                      if v is not None})
    if errors:
        print("::error::the T-78 agent-judgment proof no longer covers the shipped release skill:")
        for e in errors:
            print("  - " + e)
        return 1
    print("T-78 agent-judgment proof still covers the shipped release skill")
    return 0


if __name__ == "__main__":
    sys.exit(main())

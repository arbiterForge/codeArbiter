#!/usr/bin/env python3
"""Unit tests for check_skill_proof_fresh — the T-79 proof-freshness guard
(AC-6.8, .codearbiter/specs/release-portable-fixture.md).

Run: python .github/scripts/test_check_skill_proof_fresh.py

Covers the payload-derivation function against the live repo (it must
resolve exactly the three full-prose release-skill payloads named in the
spec's "Source of truth" table, never hardcoded here as the checker's own
truth — only as this test's independent expectation), the derivation's own
declared failure mode via a synthetic descriptor set, and every one of
`check()`'s named failure causes via synthetic artifact fixtures — most
importantly the live, current state of this repo's own artifact, which is
genuinely stale (`proof_current: false`) and must fail this guard for
exactly that reason.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import check_skill_proof_fresh as G

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_ARTIFACT = REPO_ROOT / ".codearbiter" / "reports" / "agent-lane-proof.json"
REAL_PAYLOAD = REPO_ROOT / "plugins" / "ca" / "skills" / "release" / "SKILL.md"


def _write_json(directory, document):
    path = Path(directory) / "artifact.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _real_hash():
    with open(REAL_PAYLOAD, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _fresh_document():
    """A synthetic artifact that WOULD be fresh against the live repo —
    proof_current true, pointing at the real ca payload with its real,
    live hash. Every failure-mode test below perturbs exactly one field
    away from this baseline."""
    return {
        "proof_current": True,
        "exercise": {
            "exercised_skill_path": "plugins/ca/skills/release/SKILL.md",
            "exercised_skill_sha256": _real_hash(),
        },
    }


class PayloadDerivationTest(unittest.TestCase):
    """The payload set is DERIVED from core/hosts.json, never hardcoded in
    the checker — this test's own expectation IS hardcoded, deliberately,
    as the independent oracle a derivation bug would disagree with."""

    def test_derives_exactly_the_three_full_prose_payloads_on_live_repo(self):
        payloads = G.full_prose_release_skill_payloads()
        self.assertEqual(
            payloads,
            {
                "plugins/ca/skills/release/SKILL.md": "claude",
                "plugins/ca-codex/routines/release/SKILL.md": "codex",
                "plugins/ca-pi/routines/release/SKILL.md": "pi",
            },
        )

    def test_stub_payloads_are_not_derived(self):
        # The two per-host router stubs render from a DIFFERENT source
        # template (commands/release.md) and carry no prose of their own
        # (test_consumer_smoke.py proves that directly); this function
        # only ever resolves skills/release/SKILL.md, so neither stub path
        # can appear here regardless of what core/hosts.json says.
        payloads = G.full_prose_release_skill_payloads()
        self.assertNotIn("plugins/ca-codex/skills/ca-release/SKILL.md", payloads)
        self.assertNotIn("plugins/ca-pi/skills/ca-release/SKILL.md", payloads)

    def test_a_host_that_no_longer_renders_the_source_raises(self):
        # A synthetic build_surface stub whose lone descriptor's
        # `_output_rel` always reports "no matching rule" for the release-
        # skill source — the shape a host_descriptors change that dropped
        # the `skills/` rule would produce. The derivation must fail
        # LOUDLY and name the host, never silently omit it from the map.
        fake_descriptor = SimpleNamespace(name="ghost", plugin_dir="plugins/ghost")
        fake_build_surface = SimpleNamespace(
            load_host_descriptors=lambda repo: (fake_descriptor,),
            _output_rel=lambda rel, descriptor: (None, None),
        )
        with self.assertRaises(G.ProofFreshnessError) as ctx:
            G.full_prose_release_skill_payloads(
                repo="/does/not/matter", build_surface=fake_build_surface
            )
        self.assertIn("ghost", str(ctx.exception))


class CheckLiveRepoTest(unittest.TestCase):
    """The live artifact is genuinely stale right now (T-78's exercise ran
    pre-remediation). This guard exists to fail loudly on exactly that
    state — proving it fails for the RIGHT reason on the real repo, not
    merely on synthetic fixtures, is the point (per the standing
    "a gate that cannot fail is worse than none" discipline)."""

    def test_head_currently_fails_on_stale_proof_current(self):
        errors = G.check()
        self.assertTrue(errors, "expected the live, stale artifact to fail this guard")
        self.assertTrue(
            any("proof_current" in e for e in errors),
            f"expected a proof_current-shaped failure, got: {errors}",
        )

    def test_real_artifact_is_parseable_json_at_least(self):
        # Guards the guard's own JSON-parse path against the real file: if
        # the artifact were ever hand-edited into invalid JSON, this
        # documents that check() would report THAT, not proof_current.
        with open(REAL_ARTIFACT, encoding="utf-8") as fh:
            document = json.load(fh)
        self.assertIn("proof_current", document)


class CheckFailureModeTest(unittest.TestCase):
    """Each of check()'s named failure causes, isolated via a synthetic
    artifact that perturbs exactly one field away from a fresh baseline."""

    def test_missing_artifact_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.json"
            errors = G.check(artifact_path=missing)
            self.assertTrue(errors)
            self.assertIn("missing proof artifact", errors[0])

    def test_unparseable_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "artifact.json"
            path.write_text("{not json", encoding="utf-8")
            errors = G.check(artifact_path=path)
            self.assertTrue(errors)
            self.assertIn("not parseable JSON", errors[0])

    def test_proof_current_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            document = _fresh_document()
            document["proof_current"] = False
            path = _write_json(tmp, document)
            errors = G.check(artifact_path=path)
            self.assertTrue(errors)
            self.assertIn("proof_current", errors[0])

    def test_proof_current_missing_entirely(self):
        with tempfile.TemporaryDirectory() as tmp:
            document = _fresh_document()
            del document["proof_current"]
            path = _write_json(tmp, document)
            errors = G.check(artifact_path=path)
            self.assertTrue(errors)
            self.assertIn("proof_current", errors[0])

    def test_exercise_object_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            document = _fresh_document()
            del document["exercise"]
            path = _write_json(tmp, document)
            errors = G.check(artifact_path=path)
            self.assertTrue(errors)
            self.assertIn("exercise", errors[0])

    def test_exercised_skill_path_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            document = _fresh_document()
            del document["exercise"]["exercised_skill_path"]
            path = _write_json(tmp, document)
            errors = G.check(artifact_path=path)
            self.assertTrue(errors)
            self.assertIn("exercised_skill_path", errors[0])

    def test_exercised_skill_sha256_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            document = _fresh_document()
            del document["exercise"]["exercised_skill_sha256"]
            path = _write_json(tmp, document)
            errors = G.check(artifact_path=path)
            self.assertTrue(errors)
            self.assertIn("exercised_skill_sha256", errors[0])

    def test_recorded_path_is_not_a_rendered_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            document = _fresh_document()
            document["exercise"]["exercised_skill_path"] = (
                "plugins/ca/skills/does-not-exist/SKILL.md"
            )
            path = _write_json(tmp, document)
            errors = G.check(artifact_path=path)
            self.assertTrue(errors)
            self.assertIn("not a full-prose release-skill payload", errors[0])

    def test_recorded_path_no_longer_exists_on_disk(self):
        # Isolated from the "not a rendered payload" cause above via
        # dependency injection: a synthetic build_surface whose descriptor
        # legitimately resolves the recorded path, but the file is simply
        # absent under the scratch `repo` this test supplies.
        fake_descriptor = SimpleNamespace(name="claude", plugin_dir="plugins/ca")
        fake_build_surface = SimpleNamespace(
            load_host_descriptors=lambda repo: (fake_descriptor,),
            _output_rel=lambda rel, descriptor: ("skills/release/SKILL.md", None),
        )
        with tempfile.TemporaryDirectory() as tmp:
            document = _fresh_document()
            document["exercise"]["exercised_skill_path"] = "plugins/ca/skills/release/SKILL.md"
            document["exercise"]["exercised_skill_sha256"] = "0" * 64
            artifact_path = _write_json(tmp, document)
            errors = G.check(
                repo=tmp, artifact_path=artifact_path, build_surface=fake_build_surface
            )
            self.assertTrue(errors)
            self.assertIn("no longer exists on disk", errors[0])

    def test_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            document = _fresh_document()
            document["exercise"]["exercised_skill_sha256"] = "0" * 64
            path = _write_json(tmp, document)
            errors = G.check(artifact_path=path)
            self.assertTrue(errors)
            self.assertIn("has changed since", errors[0])

    def test_fresh_document_passes(self):
        # The positive path: proof_current true, recorded path a real
        # rendered payload, recorded hash the REAL live hash of that file.
        # Proves this guard is not permanently red by construction — once
        # a genuine fresh proof is recorded, it reports clean.
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_json(tmp, _fresh_document())
            self.assertEqual(G.check(artifact_path=path), [])


class MainCLITest(unittest.TestCase):
    """The script actually run as a subprocess, exercising `main()` and its
    exit-code contract end to end against the live (currently stale) repo
    state — not merely `check()` called in-process."""

    def test_cli_exits_1_on_the_live_stale_artifact(self):
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / ".github" / "scripts" / "check_skill_proof_fresh.py")],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("no longer covers the shipped release skill", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Public documentation contract for the supported governance hosts."""

import copy
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[2]
REQUIRE_CURRENT_CANDIDATE = "--require-current-candidate" in sys.argv
if REQUIRE_CURRENT_CANDIDATE:
    sys.argv.remove("--require-current-candidate")
PRINT_LIVE_CANDIDATE = "--print-live-candidate" in sys.argv
if PRINT_LIVE_CANDIDATE:
    sys.argv.remove("--print-live-candidate")
VALIDATE_LIVE_CANDIDATE_RUN = "--validate-live-candidate-run" in sys.argv
if VALIDATE_LIVE_CANDIDATE_RUN:
    sys.argv.remove("--validate-live-candidate-run")


def live_baseline_marker(runbook):
    """Return the single machine-readable live-proof marker."""
    marker_declarations = re.findall(
        r"<!--\s*CODEX-LIVE-BASELINE-META\b[^\n]*?-->",
        runbook,
    )
    if len(marker_declarations) != 1:
        raise ValueError(
            "the current Codex live baseline must have exactly one "
            "machine-readable metadata marker"
        )
    marker_match = re.fullmatch(
        r"<!-- CODEX-LIVE-BASELINE-META (?P<meta>\{[^\n]+\}) -->",
        marker_declarations[0],
    )
    if marker_match is None:
        raise ValueError(
            "the current Codex live baseline metadata marker is malformed"
        )
    return json.loads(marker_match.group("meta"))


def _require_sha(value, label):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ValueError(f"{label} is malformed")
    return value


def _successful_jobs(jobs, exact_name=None, prefix=None):
    matches = []
    for job in jobs.get("jobs", []):
        name = job.get("name", "")
        if (exact_name is not None and name == exact_name) or (
            prefix is not None and name.startswith(prefix)
        ):
            matches.append(job)
    if any(job.get("status") != "completed" or job.get("conclusion") != "success"
           for job in matches):
        raise ValueError("live candidate qualification contains a non-successful required job")
    return matches


def validate_live_candidate_run(marker, evidence):
    """Bind live proof to its exact protected-main or qualified-preview origin."""
    candidate = marker.get("candidate_commit")
    _require_sha(candidate, "live candidate commit")
    if marker.get("schema_version") == 3:
        run = evidence.get("run", {})
        jobs = evidence.get("jobs", {})
        artifact = evidence.get("artifact", {})
        expected_run = {
            "id": marker.get("candidate_ci_run_id"),
            "run_attempt": marker.get("candidate_ci_run_attempt"),
            "head_sha": marker.get("run_head_sha"),
            "status": "completed",
            "event": "pull_request",
            "head_branch": marker.get("pr_head_ref"),
            "repository_id": 1233366728,
            "repository": "arbiterForge/codeArbiter",
            "path": ".github/workflows/ci.yml",
        }
        observed_run = {
            "id": run.get("id"),
            "run_attempt": run.get("run_attempt"),
            "head_sha": run.get("head_sha"),
            "status": run.get("status"),
            "event": run.get("event"),
            "head_branch": run.get("head_branch"),
            "repository_id": (run.get("head_repository") or {}).get("id"),
            "repository": (run.get("head_repository") or {}).get("full_name"),
            "path": run.get("path"),
        }
        if observed_run != expected_run:
            raise ValueError("live candidate is not bound to the exact approved preview run")
        pull = evidence.get("pull", {})
        pull_commits = evidence.get("pull_commits", [])
        if marker.get("pr_head_sha") != marker.get("run_head_sha"):
            raise ValueError("live candidate preview head is not the exact run head")
        expected_pull = {
            "number": marker.get("pr_number"),
            "head_ref": marker.get("pr_head_ref"),
            "base": marker.get("pr_base_sha"),
            "base_ref": "main",
            "head_repo": 1233366728,
            "base_repo": 1233366728,
        }
        observed_pull = {
            "number": pull.get("number"),
            "head_ref": (pull.get("head") or {}).get("ref"),
            "base": (pull.get("base") or {}).get("sha"),
            "base_ref": (pull.get("base") or {}).get("ref"),
            "head_repo": ((pull.get("head") or {}).get("repo") or {}).get("id"),
            "base_repo": ((pull.get("base") or {}).get("repo") or {}).get("id"),
        }
        if observed_pull != expected_pull:
            raise ValueError("live candidate preview pull-request identity drifted")
        if not isinstance(pull_commits, list) or marker.get("run_head_sha") not in {
            commit.get("sha") for commit in pull_commits if isinstance(commit, dict)
        }:
            raise ValueError("live candidate run head is absent from the pull-request history")
        expected_artifact = {
            "id": marker.get("candidate_artifact_id"),
            "name": f"artifact-release-packages-{candidate}",
            "digest": f"sha256:{marker.get('candidate_artifact_sha256')}",
            "expired": False,
            "run_id": marker.get("candidate_ci_run_id"),
        }
        observed_artifact = {
            "id": artifact.get("id"),
            "name": artifact.get("name"),
            "digest": artifact.get("digest"),
            "expired": artifact.get("expired"),
            "run_id": (artifact.get("workflow_run") or {}).get("id"),
        }
        if observed_artifact != expected_artifact:
            raise ValueError("live candidate artifact identity drifted")
        if len(_successful_jobs(jobs, exact_name=(
            "[CHECK] | [CORE] | Structured artifact package assembly"
        ))) != 1:
            raise ValueError("live candidate has no exact successful package assembly job")
        if len(_successful_jobs(jobs, prefix=(
            "[CHECK] | [CORE] | Structured artifact  <"
        ))) != 6:
            raise ValueError("live candidate does not have six successful native qualifications")
        if len(_successful_jobs(jobs, prefix=(
            "[CHECK] | [CORE] | Structured artifact cold package  <"
        ))) != 18:
            raise ValueError("live candidate does not have eighteen successful cold qualifications")
        return candidate

    run = evidence
    expected = {
        "id": marker.get("candidate_ci_run_id"),
        "head_sha": candidate,
        "status": "completed",
        "conclusion": "success",
        "event": "push",
        "head_branch": "main",
        "repository": "arbiterForge/codeArbiter",
        "path": ".github/workflows/ci.yml",
    }
    observed = {
        "id": run.get("id"),
        "head_sha": run.get("head_sha"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "event": run.get("event"),
        "head_branch": run.get("head_branch"),
        "repository": (run.get("head_repository") or {}).get("full_name"),
        "path": run.get("path"),
    }
    if observed != expected:
        raise ValueError("live candidate is not bound to exact protected main CI")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", candidate, "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if ancestry.returncode != 0:
        raise ValueError("live candidate is not an ancestor of the publishing revision")
    return candidate


class PublicCodexDocsTest(unittest.TestCase):
    def _candidate_package_contract(self, commit=None):
        """Validate current bytes or one immutable committed ca-codex candidate."""
        with tempfile.TemporaryDirectory() as temporary:
            candidate = pathlib.Path(temporary) / "ca-codex.zip"
            if commit is None:
                listed = subprocess.run(
                    ["git", "ls-files", "-z", "--", "plugins/ca-codex"],
                    cwd=ROOT,
                    capture_output=True,
                    check=True,
                ).stdout.split(b"\0")
                with zipfile.ZipFile(candidate, "w", zipfile.ZIP_STORED) as archive:
                    for raw_path in listed:
                        if not raw_path:
                            continue
                        relative = raw_path.decode("utf-8")
                        source = ROOT / relative
                        self.assertTrue(
                            source.is_file(), f"tracked candidate file is missing: {relative}"
                        )
                        self.assertFalse(
                            source.is_symlink(), f"tracked candidate file is a symlink: {relative}"
                        )
                        archive.writestr(relative.replace("\\", "/"), source.read_bytes())
            else:
                self.assertRegex(commit, r"^[0-9a-f]{40}$")
                ancestry = subprocess.run(
                    ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    0,
                    ancestry.returncode,
                    "the recorded Codex live candidate commit is not an ancestor of HEAD",
                )
                subprocess.run(
                    [
                        "git",
                        "archive",
                        "--format=zip",
                        f"--output={candidate}",
                        commit,
                        "plugins/ca-codex",
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    check=True,
                )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / ".github" / "scripts" / "check_codex_skill_resources.py"),
                    "--candidate-contract-only",
                    "--candidate-package",
                    str(candidate),
                    "--json",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            )
        contract = json.loads(result.stdout)
        self.assertEqual("PASS", contract["verdict"])
        return contract

    def _tracked_candidate_package_sha256(self):
        """Hash the exact tracked ca-codex bytes through the canonical checker."""
        return self._candidate_package_contract()["package_sha256"]

    def _assert_live_baseline_marker(
        self, runbook, manifest, require_current_candidate=REQUIRE_CURRENT_CANDIDATE
    ):
        """Bind retained live proof; require exact current bytes only for release."""
        marker = live_baseline_marker(runbook)
        self.assertIn(marker["schema_version"], (2, 3))
        self.assertEqual("ca-codex", marker["adapter"])
        if marker["schema_version"] == 2:
            recorded = self._candidate_package_contract(marker.get("candidate_commit"))
            self.assertEqual(
                recorded["plugin_version"],
                marker["adapter_version"],
                "the Codex live baseline version does not match its recorded candidate commit",
            )
            self.assertEqual(
                recorded["package_sha256"],
                marker.get("candidate_package_sha256"),
                "the Codex live baseline is stale for the exact recorded candidate package",
            )
        else:
            for field in (
                "candidate_commit", "candidate_source_tree", "run_head_sha",
                "pr_head_sha", "pr_base_sha",
            ):
                self.assertRegex(marker.get(field, ""), r"^[0-9a-f]{40}$")
            for field in (
                "candidate_package_sha256", "candidate_artifact_sha256",
                "candidate_archive_sha256",
            ):
                self.assertRegex(marker.get(field, ""), r"^[0-9a-f]{64}$")
            self.assertEqual(829, marker.get("pr_number"))
            self.assertEqual("codex/prerequisite-adapter", marker.get("pr_head_ref"))
            self.assertIsInstance(marker.get("candidate_ci_run_attempt"), int)
            self.assertIsInstance(marker.get("candidate_artifact_id"), int)
        if require_current_candidate:
            self.assertEqual(
                manifest["version"],
                marker["adapter_version"],
                "release preflight requires live proof for the current package manifest",
            )
            self.assertEqual(
                self._tracked_candidate_package_sha256(),
                marker["candidate_package_sha256"],
                "release preflight requires live proof for the exact current candidate package",
            )
        self.assertRegex(marker["verified_on"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertIsInstance(marker.get("candidate_ci_run_id"), int)
        self.assertGreater(marker["candidate_ci_run_id"], 0)
        self.assertTrue(marker["host"])
        self.assertTrue(marker["proof"])

    def _assert_valid_dispatch_receipt(self, receipt):
        """Require the receipt to bind the published package and named charter."""
        self.assertEqual(1, receipt["schema_version"])
        self.assertEqual("ca-codex", receipt["package"]["name"])
        self.assertEqual("0.9.4", receipt["package"]["version"])
        self.assertEqual(
            f"ca-codex-v{receipt['package']['version']}",
            receipt["package"]["tag"],
        )

        published = json.loads(
            (ROOT / ".github" / "published-tags.json").read_text(encoding="utf-8")
        )["tags"][receipt["package"]["tag"]]
        self.assertEqual("tag", published["object_type"])
        self.assertEqual(published["object_sha"], receipt["package"]["tag_object_sha"])
        self.assertEqual(published["commit_sha"], receipt["package"]["release_commit_sha"])

        charter_relative_path = "agents/architecture-drift-reviewer.md"
        self.assertEqual(
            charter_relative_path,
            receipt["charter"]["path_within_package"],
        )
        charter_path = ROOT / "plugins" / "ca-codex" / charter_relative_path
        charter_sha256 = hashlib.sha256(charter_path.read_bytes()).hexdigest()
        self.assertEqual(charter_sha256, receipt["charter"]["sha256_before"])
        self.assertEqual(charter_sha256, receipt["charter"]["sha256_after"])
        self.assertTrue(receipt["charter"]["matched_exact_main_source"])
        self.assertTrue(receipt["controller_verification"]["installed_manifest_version_matched"])
        self.assertTrue(receipt["controller_verification"]["installed_and_source_charter_hashes_matched"])
        self.assertTrue(receipt["controller_verification"]["remote_tag_and_committed_publication_receipt_matched"])

    @classmethod
    def setUpClass(cls):
        """Load the repository README once for the public documentation checks."""
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_the_codex_support_claim_separates_continuous_from_manual(self):
        """Issue #408 AC-2, closed by SCOPING the claim rather than satisfying it.

        Proving a hook FIRES needs a turn, a turn needs a model, and a provider
        credential cannot be a required check on fork PRs. So that half is manual
        — which is a legitimate answer, but only while the manifest says so. A
        claim that reads as continuous while resting on one manual afternoon is
        the defect #408 was filed about, and it is invisible once written.

        Pinned here so the distinction cannot quietly erode back into an
        unqualified promise.
        """
        import json
        manifest = json.loads(
            (ROOT / "plugins" / "ca-codex" / ".codex-plugin" / "plugin.json")
            .read_text(encoding="utf-8"))
        description = manifest["description"]

        # It must name the manual half explicitly, and point at the record.
        self.assertRegex(
            description, r"(?i)by hand|manual",
            "the ca-codex description does not disclose that live hook firing is "
            "verified manually - #408 AC-2 was closed on that disclosure")
        self.assertIn(
            "docs/codex-parity-testing.md", description,
            "the description claims manual verification but does not name the runbook "
            "that records it")

        # ...and the runbook must actually carry a baseline to be the record.
        runbook = (ROOT / "docs" / "codex-parity-testing.md").read_text(encoding="utf-8")
        self.assertIn(
            "<!-- CODEX-LIVE-BASELINE -->", runbook,
            "the runbook has no machine-findable baseline marker, so 'verified per "
            "release' has nothing to point at")
        baseline = runbook.split("<!-- CODEX-LIVE-BASELINE -->", 1)[1]
        self.assertRegex(
            baseline[:2000], r"Codex CLI \d+\.\d+\.\d+",
            "the recorded baseline names no Codex version")
        self.assertRegex(
            baseline[:2000], r"ca-codex[^0-9]{0,12}\d+\.\d+\.\d+",
            "the recorded baseline names no ca-codex version, so staleness cannot be judged")

        self._assert_live_baseline_marker(runbook, manifest)

    def test_codex_live_checkpoint_retains_observed_and_historical_evidence(self):
        """The release record keeps current observations and prior immutable bindings."""
        runbook = (ROOT / "docs" / "codex-parity-testing.md").read_text(encoding="utf-8")
        current = runbook.split("Current verified checkpoint:", 1)[1]
        current = current.split("The earlier verified checkpoint remains", 1)[0]
        for claim in (
            "repository startup state through SessionStart context, including `host: codex`",
            "doctor reported 13 OK, 0 WARN, and 0 FAIL",
            "Windows/AMD64 artifact capability",
            "denied exactly once with `[H-03]` before execution",
            "does not\nclaim that the full scenario matrices below were rerun",
        ):
            self.assertIn(claim, current)

        prior = runbook.split("`ca-codex` **0.13.3**", 1)[1]
        prior = prior.split("The earlier verified checkpoint remains", 1)[0]
        for binding in (
            "defaf325b047afd5e3ddd20419609e5902ad21d5",
            "77263ad68e6cc29a0da52dd7497ccd82bb7b9dcbe9ac5d56b8d0060a11cc3d09",
            "35429401061",
        ):
            self.assertIn(binding, prior)

    def test_codex_live_baseline_rejects_candidate_digest_corruption(self):
        """A current-candidate package-byte change invalidates release proof."""
        runbook = (ROOT / "docs" / "codex-parity-testing.md").read_text(encoding="utf-8")
        marker_match = re.search(
            r"<!-- CODEX-LIVE-BASELINE-META (?P<meta>\{[^\n]+\}) -->",
            runbook,
        )
        self.assertIsNotNone(marker_match)
        marker = json.loads(marker_match.group("meta"))
        # Pin the control manifest's version to the marker's own recorded
        # version rather than reading the live (possibly since-advanced)
        # plugin.json -- this test's subject is digest-corruption rejection,
        # not version-currency, which test_codex_live_baseline_may_lag_the_
        # development_candidate already covers. Without this pin, an
        # ordinary version bump between releases trips the version check
        # before the digest check ever runs, for a reason unrelated to what
        # this test claims to prove.
        manifest = {"version": marker["adapter_version"]}
        corrupted = dict(marker)
        corrupted["candidate_package_sha256"] = "0" * 64
        corrupted_runbook = runbook.replace(
            marker_match.group("meta"),
            json.dumps(corrupted, separators=(",", ":")),
            1,
        )
        with self.assertRaisesRegex(AssertionError, "exact current candidate package"):
            self._assert_live_baseline_marker(
                corrupted_runbook, manifest, require_current_candidate=True
            )

    def test_codex_live_baseline_rejects_duplicate_metadata_markers(self):
        """Release proof is ambiguous unless the runbook has exactly one marker."""
        runbook = (
            '<!-- CODEX-LIVE-BASELINE-META {"candidate_commit":"first"} -->\n'
            '<!-- CODEX-LIVE-BASELINE-META {"candidate_commit":"second"} -->\n'
        )
        with self.assertRaisesRegex(ValueError, "exactly one"):
            live_baseline_marker(runbook)

    def test_codex_live_baseline_rejects_duplicate_marker_when_one_is_malformed(self):
        """A malformed second declaration cannot hide behind one valid marker."""
        runbook = (
            '<!-- CODEX-LIVE-BASELINE-META {"candidate_commit":"valid"} -->\n'
            '<!-- CODEX-LIVE-BASELINE-META malformed -->\n'
        )
        with self.assertRaisesRegex(ValueError, "exactly one"):
            live_baseline_marker(runbook)

    def test_codex_live_baseline_may_lag_the_development_candidate(self):
        """Ordinary CI preserves truthful prior proof while the next version develops."""
        runbook = (ROOT / "docs" / "codex-parity-testing.md").read_text(encoding="utf-8")
        manifest = json.loads(
            (ROOT / "plugins" / "ca-codex" / ".codex-plugin" / "plugin.json")
            .read_text(encoding="utf-8")
        )
        marker_match = re.search(
            r"<!-- CODEX-LIVE-BASELINE-META (?P<meta>\{[^\n]+\}) -->",
            runbook,
        )
        self.assertIsNotNone(marker_match)
        historical = {
            "schema_version": 2,
            "adapter": "ca-codex",
            "adapter_version": "0.10.1",
            "candidate_commit": "388da0b393f6a5bd62fb0830905d3096f683bb7a",
            "candidate_package_sha256": (
                "05ef5eac8711204ad0179468af6c690a1fb90e9e19b1eaa65a46a1fad61a5c90"
            ),
            "candidate_ci_run_id": 35210216630,
            "host": "Codex CLI 0.145.0 on Windows",
            "verified_on": "2026-09-14",
            "proof": "fixture of the retained live H-03 checkpoint",
        }
        self.assertNotEqual(manifest["version"], historical["adapter_version"])
        historical_runbook = runbook.replace(
            marker_match.group("meta"),
            json.dumps(historical, separators=(",", ":")),
            1,
        )
        self._assert_live_baseline_marker(
            historical_runbook, manifest, require_current_candidate=False
        )

    def test_ca_codex_release_preflight_enforces_live_baseline_freshness(self):
        """The ca-codex release row runs the public proof contract check-only."""
        targets = (ROOT / ".codearbiter" / "release-targets.md").read_text(
            encoding="utf-8"
        )
        codex_row = targets.split("[ca-codex]", 1)[1].split("\n[ca-sandbox]", 1)[0]
        self.assertIn(
            'pre-tag: "$PY" .github/scripts/test_public_codex_docs.py '
            "--require-current-candidate",
            codex_row,
        )
        release = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("Validate Codex live candidate CI", release)
        self.assertIn("--print-live-candidate", release)
        self.assertIn("actions: read", release)

    def test_codex_live_candidate_ci_binding_fails_closed(self):
        """Legacy proof accepts only an exact successful protected-main CI run."""
        marker = {
            "schema_version": 2,
            "candidate_commit": "b68a77b83db89a165f5481cb848932ae316583e6",
            "candidate_ci_run_id": 35468553909,
        }
        valid = {
            "id": marker["candidate_ci_run_id"],
            "head_sha": marker["candidate_commit"],
            "status": "completed",
            "conclusion": "success",
            "event": "push",
            "head_branch": "main",
            "head_repository": {"full_name": "arbiterForge/codeArbiter"},
            "path": ".github/workflows/ci.yml",
        }
        self.assertEqual(marker["candidate_commit"], validate_live_candidate_run(marker, valid))
        corruptions = {
            "id": 1,
            "head_sha": "0" * 40,
            "status": "in_progress",
            "conclusion": "failure",
            "event": "pull_request",
            "head_branch": "feature",
            "head_repository": {"full_name": "fork/codeArbiter"},
            "path": ".github/workflows/other.yml",
        }
        for field, value in corruptions.items():
            with self.subTest(field=field):
                altered = copy.deepcopy(valid)
                altered[field] = value
                with self.assertRaisesRegex(ValueError, "protected main CI"):
                    validate_live_candidate_run(marker, altered)
        unrelated = copy.deepcopy(marker)
        unrelated["candidate_commit"] = "f" * 40
        unrelated_run = copy.deepcopy(valid)
        unrelated_run["head_sha"] = unrelated["candidate_commit"]
        with self.assertRaisesRegex(ValueError, "not an ancestor"):
            validate_live_candidate_run(unrelated, unrelated_run)

    def test_codex_preview_live_proof_binds_run_pull_artifact_and_required_jobs(self):
        """Schema 3 proof is content-bound without pretending a future squash exists."""
        candidate = "a" * 40
        head = "b" * 40
        base = "c" * 40
        marker = {
            "schema_version": 3,
            "candidate_commit": candidate,
            "candidate_ci_run_id": 123,
            "candidate_ci_run_attempt": 2,
            "candidate_artifact_id": 456,
            "candidate_artifact_sha256": "d" * 64,
            "run_head_sha": head,
            "pr_number": 828,
            "pr_head_sha": head,
            "pr_head_ref": "codex/fix-release-premerge-canary",
            "pr_base_sha": base,
        }
        run = {
            "id": 123,
            "run_attempt": 2,
            "head_sha": head,
            "status": "completed",
            "conclusion": "failure",
            "event": "pull_request",
            "head_branch": marker["pr_head_ref"],
            "head_repository": {"id": 1233366728, "full_name": "arbiterForge/codeArbiter"},
            "path": ".github/workflows/ci.yml",
        }
        pull = {
            "number": 828,
            "head": {"sha": "e" * 40, "ref": marker["pr_head_ref"],
                     "repo": {"id": 1233366728}},
            "base": {"sha": base, "ref": "main", "repo": {"id": 1233366728}},
        }
        jobs = {"jobs": [
            {"name": "[CHECK] | [CORE] | Structured artifact package assembly",
             "status": "completed", "conclusion": "success"},
            *[{"name": f"[CHECK] | [CORE] | Structured artifact  <native-{i}>",
               "status": "completed", "conclusion": "success"} for i in range(6)],
            *[{"name": f"[CHECK] | [CORE] | Structured artifact cold package  <cold-{i}>",
               "status": "completed", "conclusion": "success"} for i in range(18)],
        ]}
        artifact = {
            "id": 456,
            "name": f"artifact-release-packages-{candidate}",
            "digest": f"sha256:{'d' * 64}",
            "expired": False,
            "workflow_run": {"id": 123},
        }
        evidence = {
            "run": run,
            "jobs": jobs,
            "artifact": artifact,
            "pull": pull,
            "pull_commits": [{"sha": head}, {"sha": "e" * 40}],
        }
        self.assertEqual(candidate, validate_live_candidate_run(marker, evidence))

        for area, field, value in (
            ("run", "head_sha", "e" * 40),
            ("artifact", "digest", f"sha256:{'e' * 64}"),
        ):
            with self.subTest(area=area, field=field):
                corrupted = copy.deepcopy(evidence)
                corrupted[area][field] = value
                with self.assertRaises(ValueError):
                    validate_live_candidate_run(marker, corrupted)
        missing_cold = copy.deepcopy(evidence)
        missing_cold["jobs"]["jobs"].pop()
        with self.assertRaisesRegex(ValueError, "eighteen"):
            validate_live_candidate_run(marker, missing_cold)
        missing_head = copy.deepcopy(evidence)
        missing_head["pull_commits"] = [{"sha": "e" * 40}]
        with self.assertRaisesRegex(ValueError, "absent from the pull-request history"):
            validate_live_candidate_run(marker, missing_head)

    def test_readme_announces_all_hosts_and_shared_parity(self):
        """The README presents one product and all supported host adapters."""
        self.assertIn(
            "Shared enforcement and project-context parity across Claude Code, Codex CLI, and Pi",
            self.readme,
        )
        opening = self.readme.split("## See it catch something", 1)[0]
        self.assertNotIn("codeArbiter is a native Claude Code plugin", opening)
        self.assertIn("ca-codex", opening)
        self.assertIn("ca-pi", opening)
        self.assertIn(".codearbiter/", opening)

    def test_readme_contains_codex_install_and_verification_path(self):
        """The README keeps the current Codex install and verification route."""
        for text in (
            "codex plugin marketplace add arbiterForge/codeArbiter",
            "codex plugin add ca-codex@codearbiter",
            "$ca-init",
            "$ca-doctor",
            "/hooks",
            "available now",
            "v2.8.13",
            "ca-codex 0.2.4",
        ):
            self.assertIn(text, self.readme)
        self.assertNotIn("available after the Codex-support release", self.readme)
        self.assertIn(
            "current adapter version is read from "
            "`plugins/ca-codex/.codex-plugin/plugin.json`",
            self.readme,
        )
        self.assertNotRegex(
            self.readme,
            r"repository currently ships `ca-codex \d+\.\d+\.\d+`",
        )

    def test_readme_links_catalog_and_evidence(self):
        """The README links the command catalog and pinned support evidence."""
        self.assertIn("plugins/ca-codex/COMMANDS.md", self.readme)
        self.assertIn("getting-started/claude-code-and-codex", self.readme)
        self.assertRegex(self.readme, re.compile(r"Codex CLI\s+0\.144\.1"))

    def test_project_context_assigns_kernel_and_adapter_ownership(self):
        """Project context assigns canonical source and adapter ownership."""
        context = (ROOT / ".codearbiter" / "CONTEXT.md").read_text(encoding="utf-8")
        tech_stack = (ROOT / ".codearbiter" / "tech-stack.md").read_text(encoding="utf-8")

        self.assertIn("canonical governance kernel", context)
        self.assertIn("Claude Code adapter", context)
        self.assertIn("Codex adapter", context)
        self.assertIn("Pi adapter", context)
        self.assertNotIn("— the kernel.", context)
        self.assertNotIn("Beta until live-Codex verification", context)

        for path in (
            "core/pysrc/",
            "core/surface/",
            "plugins/ca/",
            "plugins/ca-codex/",
            "plugins/ca-pi/",
        ):
            with self.subTest(path=path):
                self.assertIn(path, tech_stack)
        self.assertIn("canonical shared source", tech_stack)
        self.assertIn("Published releases from 0.7.5", tech_stack)
        self.assertNotIn("source candidate", tech_stack)

    def test_contributor_and_security_guides_describe_the_multi_host_product(self):
        """Contributor, security, and install prose matches the host topology."""
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        enforcement = (
            ROOT / "site" / "src" / "content" / "docs" / "enforcement.md"
        ).read_text(encoding="utf-8")

        self.assertNotIn("codeArbiter is a Claude Code plugin", contributing)
        self.assertNotIn("**both** plugins", contributing)
        self.assertIn("three governance adapters", contributing)
        self.assertIn("affected adapter's SemVer", contributing)
        self.assertIn("Claude Code can leave", contributing)
        self.assertIn("Codex reports", contributing)
        self.assertIn("Pi blocks", contributing)
        self.assertIn("shipped adapter-payload change", contributing)

        self.assertNotIn("codeArbiter is a Claude Code plugin", security)
        self.assertNotIn("ships from a single plugin", security)
        self.assertIn("host and adapter version", security)
        self.assertIn("Older adapter releases", security)
        self.assertIn("GitHub Releases API", security)
        self.assertIn("Git common directory", security)
        self.assertIn("~/.codearbiter/", security)
        self.assertIn("marketplace release", security)
        self.assertIn("matching npm release", security)
        self.assertNotIn("with no network calls", security)
        for host in ("Claude Code", "Codex", "Pi"):
            with self.subTest(host=host):
                self.assertIn(host, security)

        self.assertIn("All three governance adapters", enforcement)
        self.assertNotIn("Both plugins vendor the same guard core", enforcement)

        for path in (
            "site/src/content/docs/overview.md",
            "site/src/content/docs/getting-started/install.md",
        ):
            with self.subTest(path=path):
                text = (ROOT / path).read_text(encoding="utf-8")
                self.assertIn("one governance product", text)
                self.assertNotIn("codeArbiter ships four sibling plugins", text)
                self.assertNotIn("The same marketplace", text)

        overview = (
            ROOT / "site" / "src" / "content" / "docs" / "overview.md"
        ).read_text(encoding="utf-8")
        install = (
            ROOT / "site" / "src" / "content" / "docs" / "getting-started" / "install.md"
        ).read_text(encoding="utf-8")
        for text in (overview, install):
            self.assertIn("Claude Code marketplace", text)
            self.assertIn("Codex marketplace", text)
            self.assertIn("pinned Git", text)

        for path in (
            "site/src/content/docs/getting-started/pi.md",
            "site/src/content/docs/guides/uninstalling.md",
        ):
            with self.subTest(pi_distribution_path=path):
                text = (ROOT / path).read_text(encoding="utf-8")
                self.assertNotIn("Git-only", text)
                self.assertNotIn("no npm release", text)
                self.assertIn("npm is the convenience channel", text)

    def test_contributor_marketplace_example_uses_the_current_repository(self):
        """The local marketplace command resolves after entering the clone."""
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        self.assertIn("/plugin marketplace add .", contributing)
        self.assertNotIn("/plugin marketplace add ./codeArbiter", contributing)

    def test_pi_uninstall_channels_are_separate_copyable_alternatives(self):
        """Pi uninstall guidance never combines both package channels."""
        uninstall = (
            ROOT / "site" / "src" / "content" / "docs" / "guides" / "uninstalling.md"
        ).read_text(encoding="utf-8")
        self.assertRegex(
            uninstall,
            re.compile(
                r"(?s)```sh\s+pi remove npm:@arbiterforge/ca-pi\s+```"
                r"\s+```sh\s+pi remove git:github\.com/arbiterForge/codeArbiter@"
                r"ca-pi-v<version>\s+```"
            ),
        )

    def test_active_codex_role_docs_name_packaged_resource_charters(self):
        """Active Codex prose names packaged charters without overclaiming release."""
        paths = (
            "docs/architecture.md",
            "docs/parity.md",
            "site/src/content/docs/overview.md",
            "site/src/content/docs/concepts/persona-and-context.md",
            "site/src/content/docs/glossary.md",
            "site/src/content/docs/getting-started/claude-code-and-codex.md",
            "site/src/curated/commands/checkpoint.md",
            "site/src/curated/commands/pr.md",
            "site/src/curated/commands/review.md",
            "site/src/curated/commands/tribunal.md",
        )
        for path in paths:
            with self.subTest(path=path):
                text = (ROOT / path).read_text(encoding="utf-8")
                self.assertRegex(text, re.compile(r"(?is)packaged.{0,80}resource charter"))
                self.assertNotIn("does not vendor custom agent definitions", text)

        charter_files = sorted(
            path.name
            for path in (ROOT / "plugins" / "ca-codex" / "agents").glob("*.md")
            if path.name != "INDEX.md"
        )
        self.assertEqual(19, len(charter_files))

        parity = (ROOT / "docs" / "parity.md").read_text(encoding="utf-8")
        self.assertRegex(
            parity,
            re.compile(r"(?m)^\| Codex packaged agents \| SUPPORTED \|"),
        )
        self.assertIn("plugins/ca-codex/agents/", parity)
        self.assertNotIn("plugins/ca-codex/resources/agents/", parity)
        self.assertIn("published releases from 0.7.5", parity)
        receipt_path = (
            ROOT
            / "docs"
            / "reports"
            / "evidence"
            / "codex-agent-dispatch"
            / "ca-codex-0.9.4-architecture-drift-reviewer.json"
        )
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self._assert_valid_dispatch_receipt(receipt)
        self.assertEqual("confirmed", receipt["review"]["verdict"])
        self.assertIn(receipt_path.relative_to(ROOT).as_posix(), parity)
        self.assertNotIn("source candidate", parity)

        public_role_docs = (
            "site/src/content/docs/overview.md",
            "site/src/content/docs/concepts/persona-and-context.md",
            "site/src/content/docs/glossary.md",
            "site/src/content/docs/getting-started/claude-code-and-codex.md",
            "site/src/curated/commands/checkpoint.md",
            "site/src/curated/commands/pr.md",
            "site/src/curated/commands/review.md",
            "site/src/curated/commands/tribunal.md",
        )
        for path in public_role_docs:
            with self.subTest(candidate_path=path):
                text = (ROOT / path).read_text(encoding="utf-8")
                normalized = " ".join(text.split())
                self.assertRegex(
                    text,
                    re.compile(r"(?is)published releases from 0\.7\.5.{0,160}packaged.{0,80}resource charter"),
                )
                self.assertNotIn("source candidate", text)
                self.assertNotIn("exact-candidate proof gates release", text)
                self.assertRegex(normalized, re.compile(r"(?i)bounded 0\.9\.4 receipt"))
                self.assertRegex(
                    normalized,
                    re.compile(
                        r"(?i)(?:bounded )?inline fallback.{0,180}canonical workflow"
                        r".{0,100}(?:isolation is not mandatory|non-isolated)"
                    ),
                )
                self.assertNotIn("Adapters before 0.7.5 may use", text)

        for path in (
            "site/src/content/docs/overview.md",
            "site/src/content/docs/concepts/persona-and-context.md",
            "site/src/content/docs/glossary.md",
        ):
            with self.subTest(release_scoped_charters_path=path):
                text = (ROOT / path).read_text(encoding="utf-8")
                normalized = " ".join(text.split())
                self.assertIn("complete packaged resource charter set for that release", normalized)

        roster = (
            ROOT / "site" / "src" / "content" / "docs" / "concepts" / "persona-and-context.md"
        ).read_text(encoding="utf-8")
        for charter in charter_files:
            with self.subTest(roster_charter=charter):
                self.assertIn(charter.removesuffix(".md"), roster)

    def test_codex_dispatch_receipt_rejects_identity_corruption(self):
        """Reject mutations to any published-package or charter identity field."""
        receipt_path = (
            ROOT
            / "docs"
            / "reports"
            / "evidence"
            / "codex-agent-dispatch"
            / "ca-codex-0.9.4-architecture-drift-reviewer.json"
        )
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        corruptions = (
            (("package", "tag_object_sha"), "0" * 40),
            (("package", "release_commit_sha"), "1" * 40),
            (("charter", "path_within_package"), "agents/security-reviewer.md"),
            (("charter", "sha256_before"), "2" * 64),
            (("charter", "sha256_after"), "3" * 64),
        )
        for path, value in corruptions:
            with self.subTest(path=".".join(path)):
                corrupted = copy.deepcopy(receipt)
                corrupted[path[0]][path[1]] = value
                with self.assertRaises(AssertionError):
                    self._assert_valid_dispatch_receipt(corrupted)


if __name__ == "__main__":
    if VALIDATE_LIVE_CANDIDATE_RUN:
        marker = live_baseline_marker(
            (ROOT / "docs" / "codex-parity-testing.md").read_text(encoding="utf-8")
        )
        try:
            print(validate_live_candidate_run(marker, json.load(sys.stdin)))
        except (KeyError, TypeError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
    elif PRINT_LIVE_CANDIDATE:
        runbook = (ROOT / "docs" / "codex-parity-testing.md").read_text(
            encoding="utf-8"
        )
        marker = live_baseline_marker(runbook)
        print(json.dumps({
            "candidate_commit": marker["candidate_commit"],
            "candidate_ci_run_id": marker["candidate_ci_run_id"],
            "candidate_ci_run_attempt": marker.get("candidate_ci_run_attempt", 1),
            "candidate_artifact_id": marker.get("candidate_artifact_id"),
            "pr_number": marker.get("pr_number"),
        }, separators=(",", ":")))
    else:
        unittest.main()

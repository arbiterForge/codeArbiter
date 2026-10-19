#!/usr/bin/env python3
"""Attest ship-set evidence-input behavior by named native Go test."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "core/artifacts"


def _linux_only(package: str) -> bool:
    """True when any test file in the package is gated by `//go:build linux`."""
    tests = sorted((MODULE / package).glob("*_test.go"))
    return any(
        f.read_text(encoding="utf-8").splitlines()[:1] == ["//go:build linux"]
        for f in tests)


def _wsl_path(path: Path) -> str:
    drive, rest = os.path.splitdrive(str(path.resolve()))
    return "/mnt/" + drive.rstrip(":").lower() + rest.replace("\\", "/")


def _run_via_wsl(name: str, package: str) -> tuple[int, str, str]:
    """Cross-compile a Linux test binary and run it under WSL; return
    (returncode, test2json events, stderr). The binary's own exit code is kept."""
    with tempfile.TemporaryDirectory(prefix="ship-set-go-") as tmp:
        binary = Path(tmp) / "package.test"
        env = dict(os.environ, GOOS="linux", GOARCH="amd64", CGO_ENABLED="0")
        build = subprocess.run(
            ["go", "test", "-c", "-buildvcs=false", "-o", str(binary), package],
            cwd=MODULE, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace")
        if build.returncode:
            return build.returncode, build.stdout, build.stderr
        wsl = ["wsl.exe"] + (
            ["-d", os.environ["CA_WSL_DISTRO"]] if os.environ.get("CA_WSL_DISTRO") else [])
        run = subprocess.run(
            wsl + ["--cd", _wsl_path(MODULE / package), "--exec", _wsl_path(binary),
                   "-test.v=test2json", "-test.count=1", "-test.run", f"^{name}$"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        converted = subprocess.run(
            ["go", "tool", "test2json", "-p", package], cwd=MODULE, input=run.stdout,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout = converted.stdout.decode("utf-8", "replace")
        stderr = (run.stderr + converted.stderr).decode("utf-8", "replace")
        return run.returncode or converted.returncode, stdout, stderr


def run_go_test(name: str, package: str, host_native: bool = False, wsl: bool = False) -> None:
    """Pass only when the event stream shows Action=pass for exactly `name`.

    Linux-only packages run through WSL on non-Linux hosts; the same strict
    rule applies (one pass, no skip, zero exit). host_native forces the host
    toolchain so a portable (Windows/macOS) backend is exercised too; wsl forces
    the cross-compiled Linux binary on a non-Linux host."""
    if sys.platform != "linux" and (wsl or (not host_native and _linux_only(package))):
        returncode, stdout, stderr = _run_via_wsl(name, package)
    else:
        result = subprocess.run(
            ["go", "test", "-json", "-buildvcs=false", "-count=1",
             "-run", f"^{name}$", package],
            cwd=MODULE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace")
        returncode, stdout, stderr = result.returncode, result.stdout, result.stderr
    passed = skipped = 0
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("Test") == name:
            passed += event.get("Action") == "pass"
            skipped += event.get("Action") == "skip"
    if returncode or passed != 1 or skipped:
        raise AssertionError(
            f"{name} did not pass exactly once: " + stdout + " " + stderr)


HOOK_FILES = ("plugins/ca/hooks/hooks.json", "plugins/ca-codex/hooks/hooks.json")
PROMPT_SUBMIT_TIMEOUT_SECONDS = 600
# These digests pin the pre-T-09 registration shape (every manifest field except
# the UserPromptSubmit prompt-submit.py timeouts). Changing any other
# registration requires deliberately updating them.
REGISTRATION_DIGESTS = {
    "plugins/ca/hooks/hooks.json":
        "795a2c483fc89579e8a209e635cebd668542da19483f063b2d48427e97b47721",
    "plugins/ca-codex/hooks/hooks.json":
        "b946af8f60516120a0b59732618b34f0399e8db609f1b311cac53c4b3a4b32b6",
}


def _hook_entries(config: dict, event: str) -> list[dict]:
    return [hook for group in config["hooks"][event] for hook in group["hooks"]]


def _prompt_submit_entries(config: dict) -> list[dict]:
    return [hook for hook in _hook_entries(config, "UserPromptSubmit")
            if "prompt-submit.py" in hook["command"]]


def _load_json(rel: str) -> dict:
    return json.loads((REPO / rel).read_text(encoding="utf-8"))


def _without_prompt_submit_timeout(config: dict) -> dict:
    stripped = json.loads(json.dumps(config))
    for hook in _prompt_submit_entries(stripped):
        hook.pop("timeout", None)
    return stripped


PROTOCOL_DOC = "docs/artifacts/PROTOCOL.md"
# Detailed ship-set attestation is intentionally a cold reference. The
# always-loaded artifact include remains small and assistive; it points to
# the exact same strict policy only for actual explicit proof consumers.
ARTIFACT_INCLUDES = (
    "core/surface/includes/artifacts-attestation.md",
    "plugins/ca/includes/artifacts-attestation.md",
    "plugins/ca-codex/includes/artifacts-attestation.md",
    "plugins/ca-pi/includes/artifacts-attestation.md",
)
# Each phrase is matched against the document with all whitespace runs collapsed,
# so hard line wrapping cannot hide or fake a statement.
SHIP_SET_STATEMENTS = (
    "git index entries present on disk",
    "untracked non-ignored files",
    ".codearbiter/gate-events.log",
    "never counted",
    "audit trail",
    "membership: filesystem",
    "INPUT_MEMBERSHIP_UNAVAILABLE",
    "codearbiter.verification-inputs/0.2.0",
    "0.1.0",
    "read as stale",
    "at most once",
    "64 MiB",
    "unmerged",
)
OLD_GITIGNORE_SENTENCE = re.compile(r"does not define (this|the) policy", re.IGNORECASE)
# The positive claim that replaced it; a rewording must keep the meaning.
INCLUDE_GITIGNORE_STATEMENT = "In a git work tree `.gitignore` already keeps untracked ignored files out of it"


def _normalized(rel: str) -> str:
    return " ".join((REPO / rel).read_text(encoding="utf-8").split())


CI_WORKFLOW = ".github/workflows/ci.yml"
SUITE_COMMAND = "python .github/scripts/test_ship_set_inputs.py"
# The `artifacts` path filter starts the artifact-engine job; the ship-set
# suite must be reachable from every path whose change can alter its verdict.
REQUIRED_ARTIFACT_FILTER_PATHS = (
    "core/artifacts/**",
    "plugins/ca/hooks/hooks.json",
    "plugins/ca-codex/hooks/hooks.json",
    ".github/scripts/test_ship_set_inputs.py",
    # The ship-set documents the suite pins (AC-11).
    "docs/artifacts/**",
    "core/surface/**",
    "plugins/ca/includes/artifacts-attestation.md",
    "plugins/ca-codex/includes/artifacts-attestation.md",
    "plugins/ca-pi/includes/artifacts-attestation.md",
)


def _ci_block(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


class ShipSetInputs(unittest.TestCase):
    def test_suite_wired_into_ci(self):
        text = (REPO / CI_WORKFLOW).read_text(encoding="utf-8")
        job = _ci_block(text, "\n  artifact-engine:\n", "\n  artifact-browser:\n")
        self.assertIn("if: needs.changes.outputs.artifacts == 'true'", job)
        self.assertIn(SUITE_COMMAND, job)
        self.assertLess(job.index("Verify exact Go toolchain"), job.index(SUITE_COMMAND))
        end = job.index(SUITE_COMMAND) + len(SUITE_COMMAND)
        step = job[job.rindex("\n      - name:", 0, end):end]
        # Linux only: the wrapper drives Linux-only packages through WSL elsewhere.
        self.assertIn("if: matrix.os == 'ubuntu-24.04'", step)
        self.assertNotIn("continue-on-error", job)
        # The filter block ends at the next sibling key or the next step.
        filter_block = re.split(
            r"\n            [A-Za-z-]+:\n|\n      - name:",
            text.split("\n            artifacts:\n", 1)[1])[0]
        for path in REQUIRED_ARTIFACT_FILTER_PATHS:
            self.assertIn(f"- '{path}'", filter_block, f"impact filter lacks {path}")

    def _assert_describes_ship_set(self, rel):
        text = _normalized(rel)
        for statement in SHIP_SET_STATEMENTS:
            self.assertIn(statement, text, f"{rel} does not state {statement!r}")
        self.assertIsNone(OLD_GITIGNORE_SENTENCE.search(text),
                          f"{rel} still says .gitignore does not define the policy")

    def test_protocol_describes_ship_set(self):
        self._assert_describes_ship_set(PROTOCOL_DOC)

    def test_opt_in_artifact_attestation_describes_ship_set(self):
        for rel in ARTIFACT_INCLUDES:
            self._assert_describes_ship_set(rel)
            self.assertIn(INCLUDE_GITIGNORE_STATEMENT, _normalized(rel),
                          f"{rel} no longer says .gitignore keeps ignored files out")

    def _assert_prompt_submit_timeout(self, rel):
        entries = _prompt_submit_entries(_load_json(rel))
        self.assertTrue(entries, f"{rel} registers no UserPromptSubmit prompt-submit.py")
        for hook in entries:
            self.assertEqual(hook.get("timeout"), PROMPT_SUBMIT_TIMEOUT_SECONDS, hook)

    def test_claude_prompt_submit_timeout(self):
        self._assert_prompt_submit_timeout("plugins/ca/hooks/hooks.json")

    def test_codex_prompt_submit_timeout(self):
        self._assert_prompt_submit_timeout("plugins/ca-codex/hooks/hooks.json")

    def test_other_registrations_unchanged(self):
        for rel in HOOK_FILES:
            canonical = json.dumps(
                _without_prompt_submit_timeout(_load_json(rel)),
                sort_keys=True, separators=(",", ":"))
            self.assertEqual(
                hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                REGISTRATION_DIGESTS[rel], rel)
        # PreCompact carries no timeout on any entry.
        claude = "plugins/ca/hooks/hooks.json"
        for hook in _hook_entries(_load_json(claude), "PreCompact"):
            self.assertNotIn("timeout", hook)

    def test_ship_set_membership(self):
        run_go_test("TestSnapshotShipSetMembership", "./internal/evidence/")

    def test_deleted_index_entry_absent(self):
        run_go_test("TestSnapshotDeletedIndexEntryAbsent", "./internal/evidence/")

    def test_gitlink_pointer_only(self):
        run_go_test("TestSnapshotGitlinkPointerOnly", "./internal/evidence/")
        run_go_test("TestSnapshotGitlinkNotCheckedOutUsesIndexPointer", "./internal/evidence/")

    def test_executable_from_index_mode(self):
        run_go_test("TestSnapshotExecutableFromIndexMode", "./internal/evidence/")

    def test_gate_events_append_exempt(self):
        run_go_test("TestSnapshotGateEventsAppendExempt", "./internal/evidence/")

    def test_overrides_append_counts(self):
        run_go_test("TestSnapshotOverridesAppendCounts", "./internal/evidence/")

    def test_plan_cannot_exclude_codearbiter(self):
        run_go_test("TestSnapshotPlanCannotExcludeCodearbiter", "./internal/evidence/")

    def test_gate_events_exempt_without_git(self):
        run_go_test("TestSnapshotGateEventsExemptWithoutGit", "./internal/evidence/")

    def test_gate_events_explicit_root_exempt(self):
        run_go_test("TestSnapshotGateEventsExplicitRootExempt", "./internal/evidence/")

    def test_non_git_root_filesystem_membership(self):
        run_go_test("TestSnapshotNonGitRootFilesystemMembership", "./internal/evidence/")

    def test_git_probe_failure_fails_closed(self):
        run_go_test("TestSnapshotGitProbeFailureFailsClosed", "./internal/evidence/")

    def test_redundant_ignored_exclude_accepted(self):
        run_go_test("TestSnapshotRedundantIgnoredExcludeAccepted", "./internal/evidence/")

    def test_excludes_narrow_ship_set(self):
        run_go_test("TestSnapshotExcludesNarrowShipSet", "./internal/evidence/")

    def test_progress_only_update_keeps_identity(self):
        run_go_test("TestSnapshotProgressOnlyUpdateKeepsIdentity", "./internal/evidence/")

    def test_case_renamed_tracked_file_fails_closed(self):
        run_go_test("TestSnapshotCaseRenamedTrackedFileFailsClosed", "./internal/evidence/")

    def test_case_mismatched_explicit_root_fails_closed(self):
        run_go_test("TestSnapshotCaseMismatchedExplicitRootFailsClosed", "./internal/evidence/")

    def test_untracked_nested_repo_counts_head(self):
        run_go_test("TestSnapshotUntrackedNestedRepoCountsHead", "./internal/evidence/")

    def test_gitlink_fake_dot_git_fails_closed(self):
        run_go_test("TestSnapshotGitlinkFakeDotGitFailsClosed", "./internal/evidence/")

    def test_gitlink_explicit_root(self):
        run_go_test("TestSnapshotGitlinkExplicitRoot", "./internal/evidence/")

    def test_root_inside_gitlink_rejected(self):
        run_go_test("TestSnapshotRootInsideGitlinkRejected", "./internal/evidence/")

    def test_ignored_explicit_file_root_excluded(self):
        run_go_test("TestSnapshotIgnoredExplicitFileRootExcluded", "./internal/evidence/")

    def test_fake_root_dot_git_fails_closed(self):
        run_go_test("TestSnapshotFakeRootDotGitFailsClosed", "./internal/evidence/")

    def test_unmerged_index_fails_closed(self):
        run_go_test("TestSnapshotUnmergedIndexFailsClosed", "./internal/evidence/")

    def test_portable_snapshot_opens_bounded(self):
        run_go_test("TestPortableSnapshotOpensBounded", "./internal/evidence/")

    def test_portable_snapshot_normative_artifacts_open_once(self):
        run_go_test("TestPortableSnapshotNormativeArtifactsOpenOnce", "./internal/evidence/")

    def test_portable_snapshot_output_receipts_open_once(self):
        run_go_test("TestPortableSnapshotOutputReceiptsOpenOnce", "./internal/evidence/")

    def test_portable_snapshot_farm_bindings_anchor_projections_once(self):
        run_go_test("TestPortableSnapshotFarmBindingsAnchorProjectionsOnce", "./internal/evidence/")

    def test_portable_snapshot_scoped_roots_share_anchored_prefixes(self):
        run_go_test("TestPortableSnapshotScopedRootsShareAnchoredPrefixes", "./internal/evidence/")

    def test_receipt_chain_fixture_is_real_and_inspect_with_fails_closed(self):
        run_go_test("TestReceiptChainFixtureIsRealAndInspectWithFailsClosed", "./internal/evidence/")

    def test_evidence_objects_read_once(self):
        for name in ("TestEvidenceObjectsReadOnce",
                     "TestEvidenceReuseNeverCachesErrorsOrAbsence",
                     "TestSnapshotNeverFallsBackToRootRelativeReadForChainObject",
                     "TestSnapshotChecksUnreferencedEvidenceObjects"):
            run_go_test(name, "./internal/operations/", host_native=True)
            run_go_test(name, "./internal/operations/", wsl=True)

    def test_evidence_memo_hardening(self):
        for name in ("TestEvidenceReuseServesCopiesNotTheMemosBytes",
                     "TestNonStoreReaderNeverSeedsReuse",
                     "TestMismatchedBytesAreNeverRecorded",
                     "TestRawReadBudgetStopsRecording"):
            run_go_test(name, "./internal/operations/", host_native=True)

    def test_snapshot_refuses_oversized_receipt(self):
        run_go_test("TestSnapshotRefusesOversizedReceipt", "./internal/evidence/")

    def test_non_canonical_root_fails_closed(self):
        run_go_test("TestSnapshotNonCanonicalRootFailsClosed", "./internal/evidence/")

    def test_unreadable_dot_git_fails_closed(self):
        run_go_test("TestSnapshotUnreadableDotGitFailsClosed", "./internal/evidence/")

    def test_gitlink_sharing_parent_git_dir_fails_closed(self):
        run_go_test("TestSnapshotGitlinkSharingParentGitDirFailsClosed", "./internal/evidence/")

    def test_contract_accepts_legacy_manifest_format(self):
        run_go_test("TestContractAcceptsLegacyManifestFormat", "./internal/observation/")

    def test_load_rejects_mutated_content_addressed_observation(self):
        run_go_test("TestLoadRejectsMutatedContentAddressedObservation", "./internal/observation/")

    def test_legacy_manifest_receipt_reads_stale(self):
        run_go_test("TestEligibleReadsLegacyManifestAsStale", "./internal/operations/")

    def _store_dir_test(self, name):
        run_go_test(name, "./internal/store/", host_native=True)
        run_go_test(name, "./internal/store/")

    def test_dir_entry_type_swapped_after_listing(self):
        self._store_dir_test("TestDirEntryTypeSwappedAfterListing")

    def test_dir_rejects_non_single_component_names(self):
        self._store_dir_test("TestDirRejectsNonSingleComponentNames")

    def test_dir_entries_is_idempotent(self):
        self._store_dir_test("TestDirEntriesIsIdempotent")

    def test_open_dir_regular_file_is_unsafe_not_absent(self):
        self._store_dir_test("TestOpenDirRegularFileIsUnsafeNotAbsent")

    def test_portable_read_refuses_symlink(self):
        self._store_dir_test("TestPortableReadRefusesSymlink")

    def test_portable_read_detects_mid_read_change(self):
        self._store_dir_test("TestPortableReadDetectsMidReadChange")

    def test_snapshot_rejects_differing_scans(self):
        run_go_test("TestSnapshotRejectsDifferingScans", "./internal/evidence/", host_native=True)
        run_go_test("TestSnapshotRejectsDifferingScans", "./internal/evidence/", wsl=True)

    def test_artifacts_module_passes(self):
        # Whole-module regression: no failing action and a zero exit.
        result = subprocess.run(
            ["go", "test", "-json", "-buildvcs=false", "-count=1", "./..."],
            cwd=MODULE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            env=dict(os.environ, CGO_ENABLED="0"))
        failed = []
        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("Action") == "fail":
                failed.append(f"{event.get('Package')} {event.get('Test', '(package)')}")
        self.assertFalse(failed, "failing actions: " + ", ".join(failed))
        self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr)

    def test_unsupported_goos_builds(self):
        # L-5: the counting seam must exist on every GOOS the module builds for.
        result = subprocess.run(
            ["go", "vet", "./..."], cwd=MODULE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            env=dict(os.environ, GOOS="freebsd", GOARCH="amd64", CGO_ENABLED="0"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

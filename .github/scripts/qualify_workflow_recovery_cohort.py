#!/usr/bin/env python3
"""Run recovery journeys against explicit retained host archives; never rebuild.

Usage: python -B .github/scripts/qualify_workflow_recovery_cohort.py
       --cohort <artifact-package-cohort.json> --output <receipt.json>
       --trusted-source-commit <sha> --trusted-workflow <workflow>
       --trusted-workflow-run <run> --release-package-stage <promoted-stage>
       --promotion-receipt-sha256 <sha256>
Missing, development-only, foreign or modified inputs fail rather than skip.
This proves installed CLI/event seams, not a visible parent TUI or user consent.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

import test_workflow_recovery_cli as cli
import test_workflow_recovery_hosts as hosts
from _contextverificationlib import (_bind_candidate_package, _native_platform,
                                     _object_without_duplicate_keys)


class RetainedRecoveryTests(cli.InstalledRecoveryFixture, unittest.TestCase):
    cohort_path = None

    @classmethod
    def setUpClass(cls):
        cls.isolate_environment()
        cls.cohort = None
        cls.cohort_sha256 = None
        spec = importlib.util.spec_from_file_location("recovery_cohort_packager", cli.ROOT / "tools/build-host-packages.py")
        packager = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = packager
        spec.loader.exec_module(packager)
        if cls.cohort_path.name != "artifact-package-cohort.json":
            raise ValueError("retained cohort requires its canonical filename")
        installer = packager._artifact_installer_module()
        raw = installer.read_regular(cls.cohort_path, 4 << 20)
        # The caller supplies the independent trusted context, exactly as the
        # existing cold-package lane does. Cohort metadata cannot approve itself.
        cohort = packager.verify_artifact_release_packages(
            package_root=cls.cohort_path.parent, source_repo=cli.ROOT,
            source_commit=cls.trusted_source_commit, workflow=cls.trusted_workflow,
            run_id=cls.trusted_workflow_run,
            promotion_receipt_sha256=cls.promotion_receipt_sha256,
            stage=cls.release_package_stage, require_production=True)
        if json.loads(raw, object_pairs_hook=_object_without_duplicate_keys) != cohort:
            raise ValueError("verified retained cohort changed during admission")
        cls.host_owner = tempfile.TemporaryDirectory(prefix="ca-recovery-retained-")
        cls.addClassCleanup(cls.host_owner.cleanup)
        candidate = Path(cls.host_owner.name).resolve()
        manifest = candidate / "artifact-package-cohort.json"
        manifest.write_bytes(raw)
        cls.hosts = {}
        for host, prefix in (("claude", "plugins/ca"), ("codex", "plugins/ca-codex"), ("pi", "package/plugins/ca-pi")):
            entry = cohort["packages"][host]
            archive = cls.cohort_path.parent / entry["file"]
            archive_bytes = installer.read_regular(archive, entry["size"])
            if (Path(entry["file"]).name != entry["file"] or archive.is_symlink()
                    or len(archive_bytes) != entry["size"]
                    or hashlib.sha256(archive_bytes).hexdigest() != entry["sha256"]):
                raise ValueError("retained archive identity mismatch: " + host)
            extracted = candidate / host
            packager.extract_artifact_release_package(archive, extracted, host=host)
            plugin = extracted / prefix
            release = json.loads((plugin / "helpers/artifacts/release.json").read_bytes(),
                                 object_pairs_hook=_object_without_duplicate_keys)
            binary = release["binaries"][_native_platform()]
            _bind_candidate_package(candidate, plugin, host, manifest, hashlib.sha256(raw).hexdigest(),
                                    cohort["source_commit"], cohort["source_tree"], binary["sha256"])
            cls.hosts[host] = plugin
        cls.cohort = cohort
        cls.cohort_sha256 = hashlib.sha256(raw).hexdigest()

    @classmethod
    def tearDownClass(cls):
        pass  # addClassCleanup also handles a partially failed admission.

    # Reuse the exact observable journeys without invoking source-fixture setup
    # or copying current checkout helpers/native bytes into the installation.
    test_shared_store = cli.InstalledRecoveryTest.test_all_three_authenticated_helpers_capture_and_observe_same_local_store
    test_native_response_loss = cli.InstalledRecoveryTest.test_real_native_work_effect_is_reconciled_after_actual_process_death
    test_foreign_helper = cli.InstalledRecoveryTest.test_unknown_helper_foreign_manifest_and_arbitrary_storage_argument_refuse
    test_credential_boundary = cli.InstalledRecoveryTest.test_automatic_scan_child_environment_has_no_provider_credentials
    test_changed_owner = cli.InstalledRecoveryTest.test_changed_native_project_and_dual_owner_hold_only_affected_obligation
    store_snapshot = hosts.RecoveryHostTest.store_snapshot
    register = hosts.RecoveryHostTest.register
    script = hosts.RecoveryHostTest.script
    test_host_reentry = hosts.RecoveryHostTest.test_real_startup_prompt_and_compaction_keep_notice_separate_from_persona
    test_codex_pretool = hosts.RecoveryHostTest.test_codex_pretool_context_does_not_synthesize_allow_or_change_block
    test_pi_codec = hosts.RecoveryHostTest.test_pi_closed_snapshot_codec_reads_pending_state_without_any_effect
    test_dormant = hosts.RecoveryHostTest.test_dormant_snapshot_and_missing_ledger_create_no_state
    test_corrupt_inventory = hosts.RecoveryHostTest.test_corrupt_inventory_notice_never_repairs_or_blocks_real_host_entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--trusted-source-commit", required=True)
    parser.add_argument("--trusted-workflow", required=True)
    parser.add_argument("--trusted-workflow-run", required=True)
    parser.add_argument("--release-package-stage", required=True, type=Path)
    parser.add_argument("--promotion-receipt-sha256", required=True)
    args = parser.parse_args()
    RetainedRecoveryTests.cohort_path = args.cohort.absolute()
    RetainedRecoveryTests.trusted_source_commit = args.trusted_source_commit
    RetainedRecoveryTests.trusted_workflow = args.trusted_workflow
    RetainedRecoveryTests.trusted_workflow_run = args.trusted_workflow_run
    RetainedRecoveryTests.release_package_stage = args.release_package_stage.resolve(strict=True)
    RetainedRecoveryTests.promotion_receipt_sha256 = args.promotion_receipt_sha256
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RetainedRecoveryTests))
    receipt = {"format": "codearbiter.workflow-recovery-cohort-observation/1",
               "cohort_sha256": getattr(RetainedRecoveryTests, "cohort_sha256", None),
               "source_commit": (getattr(RetainedRecoveryTests, "cohort", None) or {}).get("source_commit"),
               "source_tree": (getattr(RetainedRecoveryTests, "cohort", None) or {}).get("source_tree"),
               "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
               "skipped": len(result.skipped),
               "verdict": "PASS" if result.wasSuccessful() and result.testsRun == 10 and not result.skipped else "FAIL",
               "scope": "retained archive CLI and hook event seams; no visible parent TUI, consent or publication proof"}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    return 0 if receipt["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

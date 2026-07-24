#!/usr/bin/env python3
"""Adversarial tests for canonical planning-file CAS publication."""

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("planfilelib", ROOT / "core" / "pysrc" / "_planfilelib.py")
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)


class PlanFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        (self.root / ".codearbiter" / "specs").mkdir(parents=True)
        (self.root / ".codearbiter" / "plans").mkdir()
        self.spec = self.root / ".codearbiter" / "specs" / "demo.md"
        self.plan = self.root / ".codearbiter" / "plans" / "demo.md"
        self.spec.write_text("# original\n", encoding="utf-8")
        self.plan.write_text("| Task | Status |\n|---|---|\n| T-01 | PENDING |\n", encoding="utf-8")
        self.lock_root = self.root / "locks"

    def tearDown(self):
        self.temp.cleanup()

    def read(self, kind="spec"):
        return P.plan_file_operation(str(self.root), {"slug": "demo", "kind": kind, "action": "read"},
                                     lock_root=str(self.lock_root))

    def replace(self, content, expected=None, kind="spec", fault=None):
        if expected is None:
            expected = self.read(kind)["hash"]
        return P.plan_file_operation(str(self.root), {
            "slug": "demo", "kind": kind, "action": "replace",
            "expectedHash": expected, "content": content,
        }, lock_root=str(self.lock_root), fault=fault)

    def assert_no_artifacts(self, parent=None):
        parent = parent or self.spec.parent
        self.assertFalse([name for name in os.listdir(parent) if ".ca-plan-" in name])

    def test_successful_read_create_replace_and_conflict(self):
        initial = self.read()
        self.assertEqual(initial["status"], "unchanged")
        committed = self.replace("# replacement\n", initial["hash"])
        self.assertEqual(committed["status"], "committed")
        self.assertEqual(self.spec.read_text(encoding="utf-8"), committed["content"])
        self.assertEqual(self.replace("stale\n", initial["hash"])["status"], "conflict")
        self.spec.unlink()
        created = self.replace("created\n", expected=None)
        self.assertEqual(created["status"], "committed")
        self.assertEqual(self.spec.read_text(encoding="utf-8"), "created\n")
        self.assert_no_artifacts()

    def test_partial_temp_write_and_sync_fail_without_touching_original(self):
        original_write = P._write_all
        def partial(fd, data):
            os.write(fd, data[: max(1, len(data) // 2)])
            raise OSError("partial")
        failures = [
            mock.patch.object(P, "_write_all", partial),
            mock.patch.object(P, "_sync_temp", side_effect=OSError("sync")),
        ]
        for index, patcher in enumerate(failures):
            with self.subTest(index=index), patcher:
                self.assertEqual(self.replace("new bytes\n")["status"], "error")
                self.assertEqual(self.spec.read_text(encoding="utf-8"), "# original\n")
                self.assert_no_artifacts()
        P._write_all = original_write

    def test_temp_handle_close_failure_after_publish_cannot_reverse_commit(self):
        def fail_close(fd):
            os.close(fd)
            raise OSError("close")
        with mock.patch.object(P, "_close_temp", side_effect=fail_close):
            result = self.replace("committed before close\n")
        self.assertEqual(result["status"], "committed")
        self.assertEqual(self.spec.read_text(encoding="utf-8"), "committed before close\n")

    def test_publish_failure_and_failed_creation_cleanup(self):
        with mock.patch.object(P, "_publish", side_effect=OSError("publish")):
            self.assertEqual(self.replace("new\n")["status"], "error")
        self.assertEqual(self.spec.read_text(encoding="utf-8"), "# original\n")
        self.assert_no_artifacts()
        self.spec.unlink()
        with mock.patch.object(P, "_sync_temp", side_effect=OSError("sync")):
            result = P.plan_file_operation(str(self.root), {
                "slug": "demo", "kind": "spec", "action": "replace",
                "expectedHash": None, "content": "created\n",
            }, lock_root=str(self.lock_root))
        self.assertEqual(result["status"], "error")
        self.assertFalse(self.spec.exists())
        self.assert_no_artifacts()

    def test_same_size_concurrent_write_conflicts_by_hash(self):
        def mutate(_phase, _path):
            self.spec.write_bytes(b"X" * (len(b"# original\n") - 1) + b"\n")
        result = self.replace("replacement\n", fault=lambda phase, path: mutate(phase, path) if phase == "before_publish" else None)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(self.spec.read_bytes(), b"X" * (len(b"# original\n") - 1) + b"\n")
        self.assert_no_artifacts()

    def test_target_swap_before_publish_never_writes_outside(self):
        outside = self.root / "outside.md"
        moved = self.root / "moved.md"
        outside.write_text("outside\n", encoding="utf-8")
        def swap(phase, _path):
            if phase != "before_publish":
                return
            self.spec.rename(moved)
            self.spec.symlink_to(outside)
        self.assertEqual(self.replace("attack\n", fault=swap)["status"], "conflict")
        self.assertEqual(outside.read_text(encoding="utf-8"), "outside\n")
        self.assertEqual(moved.read_text(encoding="utf-8"), "# original\n")
        self.assert_no_artifacts(self.root / ".codearbiter" / "specs")

    def test_ancestor_swap_before_publish_never_writes_outside(self):
        parent = self.spec.parent
        moved = self.root / "moved-specs"
        outside = self.root / "outside-specs"
        outside.mkdir()
        (outside / "demo.md").write_text("outside\n", encoding="utf-8")
        def swap(phase, _path):
            if phase != "before_publish":
                return
            parent.rename(moved)
            parent.symlink_to(outside, target_is_directory=True)
        result = self.replace("attack\n", fault=swap)
        self.assertIn(result["status"], ("conflict", "error"))
        self.assertEqual((outside / "demo.md").read_text(encoding="utf-8"), "outside\n")
        original = moved / "demo.md" if moved.exists() else self.spec
        self.assertEqual(original.read_text(encoding="utf-8"), "# original\n")

    def test_links_hardlinks_and_nonregular_targets_reject(self):
        outside = self.root / "outside.md"
        outside.write_text("outside\n", encoding="utf-8")
        self.spec.unlink()
        self.spec.symlink_to(outside)
        self.assertEqual(self.read()["status"], "error")
        self.spec.unlink()
        self.spec.write_text("original\n", encoding="utf-8")
        os.link(self.spec, self.root / "alias.md")
        self.assertEqual(self.read()["status"], "error")
        os.unlink(self.root / "alias.md")
        self.spec.unlink()
        self.spec.mkdir()
        self.assertEqual(self.read()["status"], "error")

    def test_create_race_conflicts_and_cleans_temp(self):
        self.spec.unlink()
        def race(phase, _path):
            if phase == "before_publish":
                self.spec.write_text("competitor\n", encoding="utf-8")
        result = P.plan_file_operation(str(self.root), {
            "slug": "demo", "kind": "spec", "action": "replace",
            "expectedHash": None, "content": "ours\n",
        }, lock_root=str(self.lock_root), fault=race)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(self.spec.read_text(encoding="utf-8"), "competitor\n")
        self.assert_no_artifacts()

    def test_same_inode_same_size_change_during_stable_read_is_not_overwritten(self):
        changed = False
        def mutate(phase, _path):
            nonlocal changed
            if phase == "read_between" and not changed:
                changed = True
                with self.spec.open("r+b", buffering=0) as handle:
                    handle.write(b"# changed!!\n")
        result = self.replace("replacement\n", fault=mutate)
        self.assertNotEqual(result["status"], "committed")
        self.assertEqual(self.spec.read_bytes(), b"# changed!!\n")
        self.assert_no_artifacts()

    def test_late_replace_competitor_is_not_overwritten(self):
        changed = False
        def compete(phase, _path):
            nonlocal changed
            if phase == "publish" and not changed:
                changed = True
                self.spec.write_text("competitor\n", encoding="utf-8")
        result = self.replace("ours\n", fault=compete)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(self.spec.read_text(encoding="utf-8"), "competitor\n")
        self.assert_no_artifacts()

    def test_late_create_competitor_is_not_overwritten(self):
        self.spec.unlink()
        def compete(phase, _path):
            if phase == "publish" and not self.spec.exists():
                self.spec.write_text("competitor\n", encoding="utf-8")
        result = P.plan_file_operation(str(self.root), {
            "slug": "demo", "kind": "spec", "action": "replace",
            "expectedHash": None, "content": "ours\n",
        }, lock_root=str(self.lock_root), fault=compete)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(self.spec.read_text(encoding="utf-8"), "competitor\n")
        self.assert_no_artifacts()

    def test_successful_rename_is_committed_even_when_postwork_fails(self):
        with mock.patch.object(P, "_sync_parent", side_effect=OSError("sync")):
            result = self.replace("committed\n")
        self.assertEqual(result["status"], "committed")
        self.assertFalse(result["directoryDurable"])
        self.assertEqual(result["postCommitDiagnostic"], "directory_sync_failed")
        self.assertEqual(self.spec.read_text(encoding="utf-8"), "committed\n")
        self.assert_no_artifacts()

    @unittest.skipIf(os.name == "nt", "POSIX lock permissions")
    def test_posix_lock_root_and_leaf_permissions_are_enforced(self):
        self.lock_root.mkdir(mode=0o755)
        os.chmod(self.lock_root, 0o755)
        self.assertEqual(self.read()["status"], "error")
        os.chmod(self.lock_root, 0o700)
        lock_name = P._lock_name(str(self.spec))
        leaf = self.lock_root / lock_name
        leaf.write_bytes(b"\0")
        os.chmod(leaf, 0o644)
        self.assertEqual(self.read()["status"], "error")

    @unittest.skipIf(os.name == "nt", "POSIX lock replacement")
    def test_posix_lock_leaf_replacement_after_acquisition_is_rejected(self):
        import fcntl
        self.lock_root.mkdir(mode=0o700)
        leaf = self.lock_root / P._lock_name(str(self.spec))
        leaf.write_bytes(b"\0")
        os.chmod(leaf, 0o600)
        original = fcntl.flock
        replaced = False
        def replace(fd, operation):
            nonlocal replaced
            result = original(fd, operation)
            if operation & fcntl.LOCK_EX and not replaced:
                replaced = True
                leaf.rename(leaf.with_suffix(".old"))
                leaf.write_bytes(b"\0")
                os.chmod(leaf, 0o600)
            return result
        with mock.patch.object(fcntl, "flock", side_effect=replace):
            self.assertEqual(self.read()["status"], "error")

    @unittest.skipUnless(os.name == "nt", "Windows named mutex semantics")
    def test_abandoned_mutex_is_recovered_and_release_error_cannot_reverse_commit(self):
        with mock.patch.object(P, "_windows_wait_mutex", return_value=0x00000080), \
                mock.patch.object(P, "_windows_release_mutex", side_effect=OSError("release")):
            result = self.replace("recovered\n")
        self.assertEqual(result["status"], "committed")
        self.assertEqual(self.spec.read_text(encoding="utf-8"), "recovered\n")

    def test_postcommit_verification_failure_cannot_reverse_commit(self):
        original = P._read_target
        calls = 0
        def fail_postcommit(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 4:
                raise OSError("verify")
            return original(*args, **kwargs)
        expected = self.read()["hash"]
        with mock.patch.object(P, "_read_target", side_effect=fail_postcommit):
            result = self.replace("committed anyway\n", expected)
        self.assertEqual(result["status"], "committed")
        self.assertFalse(result["observed"])
        self.assertFalse(result["directoryDurable"])
        self.assertEqual(result["postCommitDiagnostic"], "postcommit_unobserved")
        self.assertEqual(self.spec.read_text(encoding="utf-8"), "committed anyway\n")

    def test_temp_name_swap_never_publishes_attacker_bytes(self):
        captured = self.spec.parent / "captured-owned-temp"
        replacement = None
        def swap(phase, path):
            nonlocal replacement
            if phase != "publish":
                return
            candidates = [name for name in os.listdir(path["parent"]) if ".ca-plan-tmp-" in name]
            self.assertEqual(len(candidates), 1)
            replacement = self.spec.parent / candidates[0]
            replacement.rename(captured)
            replacement.write_text("attacker\n", encoding="utf-8")
        result = self.replace("ours\n", fault=swap)
        self.assertNotEqual(result["status"], "committed")
        self.assertEqual(self.spec.read_text(encoding="utf-8"), "# original\n")
        self.assertEqual(replacement.read_text(encoding="utf-8"), "attacker\n")

    def test_postcommit_change_returns_observed_bytes_and_hash(self):
        def overwrite(phase, _path):
            if phase == "after_publish":
                self.spec.write_text("observed competitor\n", encoding="utf-8")
        result = self.replace("requested\n", fault=overwrite)
        self.assertEqual(result["status"], "committed")
        self.assertTrue(result["observed"])
        self.assertEqual(result["content"], "observed competitor\n")
        self.assertEqual(result["hash"], P.hashlib.sha256(b"observed competitor\n").hexdigest())
        self.assertEqual(result["postCommitDiagnostic"], "postcommit_changed")

    @unittest.skipIf(os.name == "nt", "portable POSIX create publication")
    def test_posix_create_does_not_depend_on_renameat2(self):
        self.spec.unlink()
        with mock.patch.object(P.ctypes, "CDLL", side_effect=AssertionError("renameat2 unavailable")):
            result = P.plan_file_operation(str(self.root), {
                "slug": "demo", "kind": "spec", "action": "replace",
                "expectedHash": None, "content": "portable\n",
            }, lock_root=str(self.lock_root))
        self.assertEqual(result["status"], "committed")
        self.assertEqual(self.spec.read_text(encoding="utf-8"), "portable\n")

    @unittest.skipIf(os.name == "nt", "POSIX postcommit cleanup truth")
    def test_posix_create_cleanup_stat_failure_cannot_reverse_commit(self):
        self.spec.unlink()
        original_stat = P.os.stat
        def fail_owned_temp_stat(name, *args, **kwargs):
            if isinstance(name, str) and ".ca-plan-tmp-" in name and self.spec.exists():
                raise PermissionError("postcommit temp stat")
            return original_stat(name, *args, **kwargs)
        with mock.patch.object(P.os, "stat", side_effect=fail_owned_temp_stat):
            result = P.plan_file_operation(str(self.root), {
                "slug": "demo", "kind": "spec", "action": "replace",
                "expectedHash": None, "content": "committed create\n",
            }, lock_root=str(self.lock_root))
        self.assertEqual(result["status"], "committed")
        self.assertEqual(result["postCommitDiagnostic"], "postcommit_cleanup_failed")
        self.assertFalse(result["directoryDurable"])
        self.assertEqual(self.spec.read_text(encoding="utf-8"), "committed create\n")

    @unittest.skipUnless(os.name == "nt", "Windows NT rename semantics")
    def test_positive_ntstatus_is_a_committed_rename(self):
        original = P._windows_rename_status
        def positive(*args):
            self.assertGreaterEqual(original(*args), 0)
            return 1
        with mock.patch.object(P, "_windows_rename_status", side_effect=positive):
            result = self.replace("positive\n")
        self.assertEqual(result["status"], "committed")
        self.assertEqual(self.spec.read_text(encoding="utf-8"), "positive\n")
        self.assert_no_artifacts()
        P._windows_rename_status = original

    @unittest.skipUnless(os.name == "nt", "Windows held-handle identity")
    def test_windows_held_handle_identity_mismatch_is_rejected(self):
        expected = self.read()["hash"]
        original = P._windows_handle_identity
        calls = 0
        def mismatch(handle):
            nonlocal calls
            calls += 1
            identity = original(handle)
            return identity if calls <= 3 else (identity[0], identity[1] + 1, identity[2])
        with mock.patch.object(P, "_windows_handle_identity", side_effect=mismatch):
            result = self.replace("attack\n", expected)
        self.assertEqual(result["status"], "error")
        self.assertEqual(self.spec.read_text(encoding="utf-8"), "# original\n")


if __name__ == "__main__":
    unittest.main()

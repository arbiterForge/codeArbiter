"""End-to-end contract for the sanctioned H-05 conflict resolver (#671)."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


HOOKS = Path(__file__).resolve().parents[1]
HELPER = HOOKS / "resolve-append-only-conflict.py"
TARGET = ".codearbiter/overrides.log"
sys.path.insert(0, str(HOOKS))
import _appendonlyconflictlib as resolver  # noqa: E402


class AppendOnlyConflictJourneyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.git("init", "--initial-branch=main")
        self.git("config", "user.name", "Conflict Fixture")
        self.git("config", "user.email", "fixture@example.test")

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args, check=True):
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def commit(self, message):
        self.git("add", "--", TARGET)
        self.git("commit", "-m", message)

    def conflict(self, *, left=None, right=None):
        base = b"# append-only audit\nbaseline\n"
        left = left if left is not None else base + b"left append\n"
        right = right if right is not None else base + b"right append\n"
        self.write(TARGET, base)
        self.commit("base")
        self.git("switch", "-c", "left-history")
        self.write(TARGET, left)
        self.commit("left")
        self.git("switch", "main")
        self.write(TARGET, right)
        self.commit("right")
        merged = self.git("merge", "left-history", check=False)
        self.assertNotEqual(merged.returncode, 0, merged.stdout + merged.stderr)
        self.assertEqual(len(self.unmerged()), 3)
        return base, right[len(base) :], left[len(base) :]

    def unmerged(self):
        output = self.git("ls-files", "-u", "--", TARGET).stdout
        return [line for line in output.splitlines() if line]

    def gate_events_conflict(self):
        gate_events = ".codearbiter/gate-events.log"
        overrides = b"# append-only overrides\n"
        base = b"# append-only gate events\nbaseline\n"
        self.write(TARGET, overrides)
        self.write(gate_events, base)
        self.git("add", "--", TARGET, gate_events)
        self.git("commit", "-m", "base")
        self.git("switch", "-c", "left-history")
        self.write(gate_events, base + b"left append\n")
        self.git("add", "--", gate_events)
        self.git("commit", "-m", "left")
        self.git("switch", "main")
        self.write(gate_events, base + b"right append\n")
        self.git("add", "--", gate_events)
        self.git("commit", "-m", "right")
        self.assertNotEqual(self.git("merge", "left-history", check=False).returncode, 0)
        return gate_events, overrides, base

    def dual_audit_conflict(self):
        gate_events = ".codearbiter/gate-events.log"
        overrides = b"# append-only overrides\n"
        events = b"# append-only gate events\n"
        self.write(TARGET, overrides)
        self.write(gate_events, events)
        self.git("add", "--", TARGET, gate_events)
        self.git("commit", "-m", "base")
        self.git("switch", "-c", "left-history")
        self.write(TARGET, overrides + b"left override\n")
        self.write(gate_events, events + b"left event\n")
        self.git("add", "--", TARGET, gate_events)
        self.git("commit", "-m", "left")
        self.git("switch", "main")
        self.write(TARGET, overrides + b"right override\n")
        self.write(gate_events, events + b"right event\n")
        self.git("add", "--", TARGET, gate_events)
        self.git("commit", "-m", "right")
        self.assertNotEqual(self.git("merge", "left-history", check=False).returncode, 0)
        return gate_events

    def audit_state(self, *paths):
        return {
            relative: (
                (self.root / relative).read_bytes(),
                self.git("ls-files", "--stage", "--", relative).stdout,
            )
            for relative in paths
        }

    def run_helper(self, *extra):
        self.assertTrue(
            HELPER.is_file(),
            "the sanctioned append-only conflict helper is missing",
        )
        return subprocess.run(
            [sys.executable, str(HELPER), TARGET, "--reason", "preserve both histories", *extra],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "PYTHONUTF8": "1"},
        )

    def test_real_conflict_preserves_both_histories_records_override_and_stages(self):
        base, ours, theirs = self.conflict()
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        raw = (self.root / TARGET).read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r\n", raw)
        self.assertTrue(raw.startswith(base + ours + theirs), raw)
        self.assertIn(b"BY: fixture@example.test | GATE: H-05", raw)
        self.assertIn(b"REASON: preserve both histories", raw)
        self.assertEqual(self.unmerged(), [])
        self.assertEqual(self.git("diff", "--cached", "--name-only").stdout, TARGET + "\n")

    def test_rejects_a_branch_that_edits_the_preexisting_prefix_without_mutation(self):
        base = b"# append-only audit\nbaseline\n"
        self.conflict(left=b"# append-only audit\nchanged\nleft append\n")
        before = (self.root / TARGET).read_bytes()
        index_before = self.git("ls-files", "-u", "--", TARGET).stdout
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not append-only", result.stderr)
        self.assertEqual((self.root / TARGET).read_bytes(), before)
        self.assertEqual(self.git("ls-files", "-u", "--", TARGET).stdout, index_before)
        self.assertNotEqual(base, (self.root / TARGET).read_bytes())

    def test_rejects_deletion_and_reordering_of_preexisting_bytes_without_mutation(self):
        base = b"# append-only audit\nfirst\nsecond\n"
        invalid_sides = (
            b"# append-only audit\nsecond\nleft append\n",
            b"# append-only audit\nsecond\nfirst\nleft append\n",
        )
        for left in invalid_sides:
            with self.subTest(left=left):
                with tempfile.TemporaryDirectory() as temporary:
                    nested = AppendOnlyConflictJourneyTests(methodName="runTest")
                    nested.temp = None
                    nested.root = Path(temporary)
                    nested.git("init", "--initial-branch=main")
                    nested.git("config", "user.name", "Conflict Fixture")
                    nested.git("config", "user.email", "fixture@example.test")
                    nested.write(TARGET, base)
                    nested.commit("base")
                    nested.git("switch", "-c", "left-history")
                    nested.write(TARGET, left)
                    nested.commit("left")
                    nested.git("switch", "main")
                    nested.write(TARGET, base + b"right append\n")
                    nested.commit("right")
                    self.assertNotEqual(nested.git("merge", "left-history", check=False).returncode, 0)
                    before = nested.audit_state(TARGET)
                    result = subprocess.run(
                        [sys.executable, str(HELPER), TARGET, "--reason", "preserve both histories"],
                        cwd=nested.root,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("not append-only", result.stderr)
                    self.assertEqual(nested.audit_state(TARGET), before)

    def test_rejects_missing_three_stage_conflict_and_cannot_be_replayed(self):
        self.write(TARGET, b"# append-only audit\nbaseline\n")
        self.commit("base")
        before = (self.root / TARGET).read_bytes()
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("three-stage conflict", result.stderr)
        self.assertEqual((self.root / TARGET).read_bytes(), before)

    def test_successful_resolution_cannot_be_replayed_or_append_a_second_override(self):
        self.conflict()
        first = self.run_helper()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        worktree_before = (self.root / TARGET).read_bytes()
        index_before = self.git("ls-files", "--stage", "--", TARGET).stdout

        replay = self.run_helper()

        self.assertNotEqual(replay.returncode, 0)
        self.assertIn("three-stage conflict", replay.stderr)
        self.assertEqual((self.root / TARGET).read_bytes(), worktree_before)
        self.assertEqual(self.git("ls-files", "--stage", "--", TARGET).stdout, index_before)
        self.assertEqual(worktree_before.count(b"GATE: H-05"), 1)

    def test_rejects_unsupported_path_before_mutation(self):
        self.conflict()
        before = (self.root / TARGET).read_bytes()
        result = subprocess.run(
            [sys.executable, str(HELPER), "README.md", "--reason", "preserve both histories"],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("supported append-only", result.stderr)
        self.assertEqual((self.root / TARGET).read_bytes(), before)
        self.assertEqual(len(self.unmerged()), 3)

    def test_supported_audit_allowlist_is_exact_and_other_h05_paths_refuse(self):
        self.assertEqual(
            resolver.SUPPORTED_AUDIT_PATHS,
            frozenset({TARGET, ".codearbiter/gate-events.log"}),
        )
        for relative in (
            ".codearbiter/triage.log",
            ".codearbiter/sprint-log.md",
            ".codearbiter/decisions/decision-log.md",
        ):
            with self.subTest(relative=relative):
                self.write(relative, b"# append-only audit\n")
                before = (self.root / relative).read_bytes()
                with self.assertRaisesRegex(resolver.ResolutionError, "not a supported"):
                    resolver._relative_target(self.root, relative)
                self.assertEqual((self.root / relative).read_bytes(), before)

    def test_relative_target_realpaths_divergent_root_spelling_before_containment(self):
        """Equivalent 8.3/symlink spellings must reach the allowlist decision."""
        relative = ".codearbiter/triage.log"
        target = self.root / relative
        self.write(relative, b"# append-only audit\n")
        real_realpath = os.path.realpath
        canonical_root = str(self.root.parent / "canonical-repository-root")
        canonical_target = str(Path(canonical_root) / relative)

        def divergent_realpath(path, *args, **kwargs):
            spelling = os.fspath(path)
            if spelling == os.fspath(self.root):
                return canonical_root
            if spelling == os.fspath(target):
                return canonical_target
            return real_realpath(path, *args, **kwargs)

        with mock.patch.object(resolver.os.path, "realpath", side_effect=divergent_realpath):
            with self.assertRaisesRegex(resolver.ResolutionError, "not a supported"):
                resolver._relative_target(self.root, relative)

    def test_relative_target_rejects_supported_path_resolving_outside_root(self):
        target = self.root / TARGET
        self.write(TARGET, b"# append-only overrides\n")
        real_realpath = os.path.realpath
        outside = str(self.root.parent / "outside-repository" / "overrides.log")

        def escaping_realpath(path, *args, **kwargs):
            if os.fspath(path) == os.fspath(target):
                return outside
            return real_realpath(path, *args, **kwargs)

        with mock.patch.object(resolver.os.path, "realpath", side_effect=escaping_realpath):
            with self.assertRaisesRegex(resolver.ResolutionError, "target escapes"):
                resolver._relative_target(self.root, TARGET)

    def test_relative_target_rejects_supported_final_link_resolving_inside_root(self):
        target = self.root / TARGET
        self.write(TARGET, b"# append-only overrides\n")
        real_realpath = os.path.realpath
        alias_destination = str(
            Path(real_realpath(self.root)) / ".codearbiter" / "real-overrides.log"
        )

        def linked_realpath(path, *args, **kwargs):
            if os.fspath(path) == os.fspath(target):
                return alias_destination
            return real_realpath(path, *args, **kwargs)

        with mock.patch.object(resolver.os.path, "realpath", side_effect=linked_realpath):
            with mock.patch.object(Path, "is_symlink", return_value=True):
                with self.assertRaisesRegex(resolver.ResolutionError, "regular non-link"):
                    resolver._relative_target(self.root, TARGET)

    def test_rejects_empty_reason_before_mutation(self):
        self.conflict()
        before = (self.root / TARGET).read_bytes()
        result = subprocess.run(
            [sys.executable, str(HELPER), TARGET, "--reason", "   "],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-empty reason", result.stderr)
        self.assertEqual((self.root / TARGET).read_bytes(), before)
        self.assertEqual(len(self.unmerged()), 3)

    def test_post_stage_verification_failure_restores_worktree_and_conflict_index(self):
        self.conflict()
        before = (self.root / TARGET).read_bytes()
        index_before = self.git("ls-files", "-u", "--", TARGET).stdout
        real_git = resolver._git

        def fail_index_verification(cwd, *args, **kwargs):
            if args == ("show", f":0:{TARGET}"):
                raise resolver.ResolutionError("injected staged-blob read failure")
            return real_git(cwd, *args, **kwargs)

        with mock.patch.object(resolver, "_git", side_effect=fail_index_verification):
            with self.assertRaisesRegex(resolver.ResolutionError, "injected staged-blob"):
                resolver.resolve(TARGET, "preserve both histories", cwd=self.root)

        self.assertEqual((self.root / TARGET).read_bytes(), before)
        self.assertEqual(self.git("ls-files", "-u", "--", TARGET).stdout, index_before)

    def test_rejects_an_embedded_utf8_bom_before_mutation(self):
        self.conflict(left=b"# append-only audit\nbaseline\n\xef\xbb\xbfleft append\n")
        before = (self.root / TARGET).read_bytes()
        index_before = self.git("ls-files", "-u", "--", TARGET).stdout
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("UTF-8 BOM", result.stderr)
        self.assertEqual((self.root / TARGET).read_bytes(), before)
        self.assertEqual(self.git("ls-files", "-u", "--", TARGET).stdout, index_before)

    def test_rejects_noncanonical_blob_bytes_and_empty_append(self):
        cases = {
            "not valid UTF-8": b"\xff\n",
            "NUL byte": b"left\x00append\n",
            "canonical LF": b"left append\r\n",
            "does not end with LF": b"left append",
        }
        for expected, raw in cases.items():
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(resolver.ResolutionError, expected):
                    resolver._validate_bytes("branch", raw)

        records = [("100644", "base", 1, TARGET), ("100644", "ours", 2, TARGET), ("100644", "theirs", 3, TARGET)]
        blobs = {"base": b"base\n", "ours": b"base\n", "theirs": b"base\ntheirs\n"}
        with mock.patch.object(resolver, "_blob", side_effect=lambda _root, oid, _label: blobs[oid]):
            with self.assertRaisesRegex(resolver.ResolutionError, "non-empty history"):
                resolver._build_union(self.root, records)

    def test_real_conflict_with_invalid_utf8_preserves_worktree_and_index(self):
        base = b"# append-only audit\nbaseline\n"
        self.conflict(left=base + b"left \xff append\n")
        before = self.audit_state(TARGET)
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not valid UTF-8", result.stderr)
        self.assertEqual(self.audit_state(TARGET), before)

    def test_post_conflict_audit_append_is_never_discarded(self):
        for relative in (TARGET, ".codearbiter/gate-events.log"):
            with self.subTest(relative=relative):
                with tempfile.TemporaryDirectory() as temporary:
                    nested = AppendOnlyConflictJourneyTests(methodName="runTest")
                    nested.temp = None
                    nested.root = Path(temporary)
                    nested.git("init", "--initial-branch=main")
                    nested.git("config", "user.name", "Conflict Fixture")
                    nested.git("config", "user.email", "fixture@example.test")
                    base = b"# append-only audit\nbaseline\n"
                    if relative != TARGET:
                        nested.write(TARGET, b"# append-only overrides\n")
                    nested.write(relative, base)
                    nested.git("add", "--", TARGET, relative)
                    nested.git("commit", "-m", "base")
                    nested.git("switch", "-c", "left-history")
                    nested.write(relative, base + b"left append\n")
                    nested.git("add", "--", relative)
                    nested.git("commit", "-m", "left")
                    nested.git("switch", "main")
                    nested.write(relative, base + b"right append\n")
                    nested.git("add", "--", relative)
                    nested.git("commit", "-m", "right")
                    self.assertNotEqual(nested.git("merge", "left-history", check=False).returncode, 0)
                    with (nested.root / relative).open("ab") as handle:
                        handle.write(b"live append after conflict\n")
                    observed_paths = (TARGET,) if relative == TARGET else (TARGET, relative)
                    before = nested.audit_state(*observed_paths)

                    result = subprocess.run(
                        [sys.executable, str(HELPER), relative, "--reason", "preserve both histories"],
                        cwd=nested.root,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )

                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("conflicted worktree", result.stderr)
                    self.assertEqual(nested.audit_state(*observed_paths), before)

    def test_append_between_final_check_and_replace_is_restored_and_refused(self):
        self.conflict()
        index_before = self.git("ls-files", "-u", "--", TARGET).stdout
        real_write = resolver._write_bytes_atomic
        injected = False

        def append_before_replace(path, raw, *args, **kwargs):
            nonlocal injected
            if not injected and os.path.samefile(path, self.root / TARGET):
                injected = True
                with Path(path).open("ab") as handle:
                    handle.write(b"concurrent append during resolution\n")
            return real_write(path, raw, *args, **kwargs)

        with mock.patch.object(resolver, "_write_bytes_atomic", side_effect=append_before_replace):
            with self.assertRaisesRegex(resolver.ResolutionError, "concurrent append"):
                resolver.resolve(TARGET, "preserve both histories", cwd=self.root)

        self.assertIn(b"concurrent append during resolution\n", (self.root / TARGET).read_bytes())
        self.assertEqual(self.git("ls-files", "-u", "--", TARGET).stdout, index_before)

    def test_atomic_publish_and_concurrent_rollback_sync_the_parent_directory(self):
        path = self.root / "atomic-audit.log"
        before = b"before\n"
        path.write_bytes(before)

        with mock.patch.object(resolver, "_sync_parent") as sync_parent:
            resolver._write_bytes_atomic(path, b"after\n")
        sync_parent.assert_called_once_with(path)

        path.write_bytes(before)
        with mock.patch.object(
            resolver.Path,
            "read_bytes",
            side_effect=(before, b"concurrent append\n"),
        ), mock.patch.object(resolver, "_sync_parent") as sync_parent:
            with self.assertRaises(resolver.ConcurrentAppendError):
                resolver._write_bytes_atomic(path, b"after\n", expected=before)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(sync_parent.call_args_list, [mock.call(path), mock.call(path)])

    def test_parent_directory_sync_is_platform_aware_and_closes_its_descriptor(self):
        path = self.root / "atomic-audit.log"
        with mock.patch.object(resolver.os, "name", "nt"), \
             mock.patch.object(resolver.os, "open") as open_parent:
            self.assertFalse(resolver._sync_parent(path))
        open_parent.assert_not_called()

        with mock.patch.object(resolver.os, "name", "posix"), \
             mock.patch.object(resolver.os, "open", return_value=123) as open_parent, \
             mock.patch.object(resolver.os, "fsync") as fsync_parent, \
             mock.patch.object(resolver.os, "close") as close_parent:
            self.assertTrue(resolver._sync_parent(path))
        self.assertEqual(open_parent.call_args.args[0], path.parent)
        fsync_parent.assert_called_once_with(123)
        close_parent.assert_called_once_with(123)

        with mock.patch.object(resolver.os, "name", "posix"), \
             mock.patch.object(resolver.os, "open", return_value=456), \
             mock.patch.object(resolver.os, "fsync", side_effect=OSError("sync failed")), \
             mock.patch.object(resolver.os, "close") as close_parent:
            with self.assertRaisesRegex(OSError, "sync failed"):
                resolver._sync_parent(path)
        close_parent.assert_called_once_with(456)

    def test_rejects_malformed_index_and_authorization_boundaries(self):
        malformed = mock.Mock(stdout=b"not-an-index-record\0")
        with mock.patch.object(resolver, "_git", return_value=malformed):
            with self.assertRaisesRegex(resolver.ResolutionError, "malformed unmerged"):
                resolver._unmerged(self.root, TARGET)

        missing_identity = mock.Mock(returncode=1, stdout=b"", stderr=b"")
        with mock.patch.object(resolver, "_git", return_value=missing_identity):
            with self.assertRaisesRegex(resolver.ResolutionError, "user.email is required"):
                resolver._authorization(self.root, "specific reason")

        for reason in ("x" * 501, "contains | pipe", "contains\nnewline"):
            with self.subTest(reason=reason[:20]):
                with self.assertRaisesRegex(resolver.ResolutionError, "at most 500"):
                    resolver._authorization(self.root, reason)

    def test_rejects_incomplete_wrong_mode_and_wrong_path_index_states_without_mutation(self):
        self.conflict()
        before = self.audit_state(TARGET)
        raw = resolver._git(self.root, "ls-files", "-u", "-z", "--", TARGET).stdout
        entries = [entry for entry in raw.split(b"\0") if entry]
        malformed_outputs = (
            b"\0".join(entries[:2]) + b"\0",
            entries[0].replace(b"100644", b"100755", 1) + b"\0" + b"\0".join(entries[1:]) + b"\0",
            entries[0].replace(TARGET.encode(), b".codearbiter/sprint-log.md", 1) + b"\0" + b"\0".join(entries[1:]) + b"\0",
        )
        real_git = resolver._git
        for malformed in malformed_outputs:
            with self.subTest(malformed=malformed[:40]):
                def substitute_unmerged(cwd, *args, **kwargs):
                    if args == ("ls-files", "-u", "-z", "--", TARGET):
                        return mock.Mock(returncode=0, stdout=malformed, stderr=b"")
                    return real_git(cwd, *args, **kwargs)

                with mock.patch.object(resolver, "_git", side_effect=substitute_unmerged):
                    with self.assertRaises(resolver.ResolutionError):
                        resolver.resolve(TARGET, "preserve both histories", cwd=self.root)
                self.assertEqual(self.audit_state(TARGET), before)

    def test_invalid_repository_root_output_is_a_surfaced_resolution_error(self):
        with mock.patch.object(
            resolver,
            "_git",
            return_value=mock.Mock(returncode=0, stdout=b"\xff", stderr=b""),
        ):
            with self.assertRaisesRegex(resolver.ResolutionError, "repository root"):
                resolver._repository_root(self.root)

    def test_pre_mutation_file_read_failure_leaves_conflict_unchanged(self):
        self.conflict()
        before = self.audit_state(TARGET)
        with mock.patch.object(Path, "read_bytes", side_effect=OSError("injected read failure")):
            with self.assertRaisesRegex(OSError, "injected read failure"):
                resolver.resolve(TARGET, "preserve both histories", cwd=self.root)
        self.assertEqual(self.audit_state(TARGET), before)

    def test_lock_contention_refuses_before_mutation(self):
        self.conflict()
        before = (self.root / TARGET).read_bytes()
        index_before = self.git("ls-files", "-u", "--", TARGET).stdout
        with mock.patch.object(resolver, "acquire_lock", return_value=None):
            with self.assertRaisesRegex(resolver.ResolutionError, "holds the repository lock"):
                resolver.resolve(TARGET, "preserve both histories", cwd=self.root)
        self.assertEqual((self.root / TARGET).read_bytes(), before)
        self.assertEqual(self.git("ls-files", "-u", "--", TARGET).stdout, index_before)

    def test_every_changed_audit_path_is_locked_through_staging(self):
        gate_events, _overrides, _base = self.gate_events_conflict()
        handles = [object(), object(), object()]
        acquired = []
        released = []

        def acquire(path):
            acquired.append(Path(path))
            return handles[len(acquired) - 1]

        with mock.patch.object(resolver, "acquire_lock", side_effect=acquire), \
             mock.patch.object(resolver, "release_lock", side_effect=released.append):
            resolver.resolve(gate_events, "preserve both histories", cwd=self.root)

        self.assertEqual(
            acquired[1:],
            [
                Path(resolver.audit_lock_key(self.root, self.root / relative))
                for relative in sorted((TARGET, gate_events))
            ],
        )
        self.assertEqual(released, list(reversed(handles)))

    def test_changed_audit_path_lock_contention_refuses_before_mutation(self):
        gate_events, _overrides, _base = self.gate_events_conflict()
        before = self.audit_state(TARGET, gate_events)
        repository_handle = object()
        first_path_handle = object()

        with mock.patch.object(
            resolver,
            "acquire_lock",
            side_effect=(repository_handle, first_path_handle, None),
        ), mock.patch.object(resolver, "release_lock") as release:
            with self.assertRaisesRegex(resolver.ResolutionError, "audit path lock"):
                resolver.resolve(gate_events, "preserve both histories", cwd=self.root)

        self.assertEqual(self.audit_state(TARGET, gate_events), before)
        self.assertEqual(release.call_args_list, [mock.call(first_path_handle), mock.call(repository_handle)])

    def test_real_preopened_official_writer_lock_refuses_without_losing_row(self):
        self.conflict()
        before = self.audit_state(TARGET)
        script = r"""
import os
import sys
from _hooklib import acquire_lock, audit_lock_key, release_lock

path = sys.argv[1]
root = sys.argv[2]
lock = acquire_lock(audit_lock_key(root, path))
if lock is None:
    raise SystemExit("writer could not acquire audit lock")
handle = open(path, "ab")
print("READY", flush=True)
sys.stdin.readline()
handle.write(b"official concurrent append retained\n")
handle.flush()
os.fsync(handle.fileno())
handle.close()
release_lock(lock)
"""
        writer = subprocess.Popen(
            [sys.executable, "-c", script, str(self.root / TARGET), str(self.root)],
            cwd=self.root,
            env={**os.environ, "PYTHONPATH": str(HOOKS)},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertEqual(writer.stdout.readline().strip(), "READY")
            with self.assertRaisesRegex(resolver.ResolutionError, "audit path lock"):
                resolver.resolve(TARGET, "preserve both histories", cwd=self.root)
            self.assertEqual(self.audit_state(TARGET), before)
            writer.stdin.write("release\n")
            writer.stdin.flush()
            stdout, stderr = writer.communicate(timeout=10)
            self.assertEqual(writer.returncode, 0, stdout + stderr)
        finally:
            if writer.poll() is None:
                writer.kill()
                writer.communicate()

        self.assertTrue((self.root / TARGET).read_bytes().endswith(
            b"official concurrent append retained\n"
        ))
        self.assertEqual(self.git("ls-files", "-u", "--", TARGET).stdout, before[TARGET][1])

    def test_dirty_override_sink_refuses_other_audit_resolution_before_mutation(self):
        gate_events, _overrides, _base = self.gate_events_conflict()
        self.write(TARGET, b"# append-only overrides\nuncommitted append\n")
        gate_events_before = (self.root / gate_events).read_bytes()
        index_before = self.git("ls-files", "-u", "--", gate_events).stdout

        with self.assertRaisesRegex(resolver.ResolutionError, "audit sink must be clean"):
            resolver.resolve(gate_events, "preserve both histories", cwd=self.root)

        self.assertEqual((self.root / gate_events).read_bytes(), gate_events_before)
        self.assertEqual(self.git("ls-files", "-u", "--", gate_events).stdout, index_before)

    def test_unmerged_override_sink_refuses_other_audit_resolution_before_mutation(self):
        gate_events = self.dual_audit_conflict()
        before = self.audit_state(TARGET, gate_events)
        with self.assertRaisesRegex(resolver.ResolutionError, "audit sink is itself unmerged"):
            resolver.resolve(gate_events, "preserve both histories", cwd=self.root)
        self.assertEqual(self.audit_state(TARGET, gate_events), before)

    def test_two_file_post_stage_failure_restores_both_files_and_indexes(self):
        gate_events, overrides, _base = self.gate_events_conflict()
        gate_events_before = (self.root / gate_events).read_bytes()
        gate_events_index_before = self.git("ls-files", "-u", "--", gate_events).stdout
        override_index_before = self.git("ls-files", "--stage", "--", TARGET).stdout
        real_git = resolver._git

        def fail_gate_events_verification(cwd, *args, **kwargs):
            if args == ("show", f":0:{gate_events}"):
                raise resolver.ResolutionError("injected gate-events staged-blob failure")
            return real_git(cwd, *args, **kwargs)

        with mock.patch.object(resolver, "_git", side_effect=fail_gate_events_verification):
            with self.assertRaisesRegex(resolver.ResolutionError, "injected gate-events"):
                resolver.resolve(gate_events, "preserve both histories", cwd=self.root)

        self.assertEqual((self.root / gate_events).read_bytes(), gate_events_before)
        self.assertEqual((self.root / TARGET).read_bytes(), overrides)
        self.assertEqual(self.git("ls-files", "-u", "--", gate_events).stdout, gate_events_index_before)
        self.assertEqual(self.git("ls-files", "--stage", "--", TARGET).stdout, override_index_before)

    def test_partial_write_and_git_add_failures_restore_both_files_and_indexes(self):
        injections = ("second-write", "git-add")
        for injection in injections:
            with self.subTest(injection=injection):
                with tempfile.TemporaryDirectory() as temporary:
                    nested = AppendOnlyConflictJourneyTests(methodName="runTest")
                    nested.temp = None
                    nested.root = Path(temporary)
                    nested.git("init", "--initial-branch=main")
                    nested.git("config", "user.name", "Conflict Fixture")
                    nested.git("config", "user.email", "fixture@example.test")
                    gate_events, _overrides, _base = nested.gate_events_conflict()
                    before = nested.audit_state(TARGET, gate_events)
                    if injection == "second-write":
                        real_write = resolver._write_bytes_atomic
                        write_count = 0

                        def fail_second_write(path, raw, *args, **kwargs):
                            nonlocal write_count
                            write_count += 1
                            if write_count == 2:
                                raise OSError("injected second write failure")
                            return real_write(path, raw, *args, **kwargs)

                        patcher = mock.patch.object(resolver, "_write_bytes_atomic", side_effect=fail_second_write)
                        expected = OSError
                    else:
                        real_git = resolver._git

                        def fail_git_add(cwd, *args, **kwargs):
                            if args[:2] == ("add", "--"):
                                return mock.Mock(returncode=1, stdout=b"", stderr=b"injected add failure")
                            return real_git(cwd, *args, **kwargs)

                        patcher = mock.patch.object(resolver, "_git", side_effect=fail_git_add)
                        expected = resolver.ResolutionError
                    with patcher:
                        with self.assertRaises(expected):
                            resolver.resolve(gate_events, "preserve both histories", cwd=nested.root)
                    self.assertEqual(nested.audit_state(TARGET, gate_events), before)

    def test_staged_blob_mismatch_restores_both_files_and_indexes(self):
        gate_events, _overrides, _base = self.gate_events_conflict()
        before = self.audit_state(TARGET, gate_events)
        real_git = resolver._git

        def mismatch_override(cwd, *args, **kwargs):
            if args == ("show", f":0:{TARGET}"):
                return mock.Mock(returncode=0, stdout=b"mismatched staged bytes", stderr=b"")
            return real_git(cwd, *args, **kwargs)

        with mock.patch.object(resolver, "_git", side_effect=mismatch_override):
            with self.assertRaisesRegex(resolver.ResolutionError, "staged blob does not match"):
                resolver.resolve(gate_events, "preserve both histories", cwd=self.root)
        self.assertEqual(self.audit_state(TARGET, gate_events), before)

    def test_rollback_index_failure_is_surfaced_after_worktree_restoration(self):
        self.conflict()
        worktree_before = (self.root / TARGET).read_bytes()
        real_git = resolver._git

        def fail_verification(cwd, *args, **kwargs):
            if args == ("show", f":0:{TARGET}"):
                raise resolver.ResolutionError("injected verification failure")
            return real_git(cwd, *args, **kwargs)

        with mock.patch.object(resolver, "_git", side_effect=fail_verification):
            with mock.patch.object(
                resolver,
                "_restore_index",
                side_effect=resolver.ResolutionError("injected rollback failure"),
            ):
                with self.assertRaisesRegex(resolver.ResolutionError, "injected rollback failure"):
                    resolver.resolve(TARGET, "preserve both histories", cwd=self.root)
        self.assertEqual((self.root / TARGET).read_bytes(), worktree_before)

    def test_authorization_identity_and_exact_reason_boundaries(self):
        invalid_identities = (
            b"\xff",
            b"",
            (b"a" * 255),
            b"bad|identity@example.test",
            b"bad\nidentity@example.test",
            b"bad\ridentity@example.test",
        )
        for identity in invalid_identities:
            with self.subTest(identity=identity[:20]):
                response = mock.Mock(returncode=0, stdout=identity, stderr=b"")
                with mock.patch.object(resolver, "_git", return_value=response):
                    with self.assertRaisesRegex(resolver.ResolutionError, "user.email"):
                        resolver._authorization(self.root, "specific reason")

        valid_identity = mock.Mock(returncode=0, stdout=b"fixture@example.test\n", stderr=b"")
        with mock.patch.object(resolver, "_git", return_value=valid_identity):
            record = resolver._authorization(self.root, "x" * 500)
            self.assertIn(b"REASON: " + (b"x" * 500), record)
            with self.assertRaisesRegex(resolver.ResolutionError, "at most 500"):
                resolver._authorization(self.root, "carriage\rreturn")

    def test_gate_events_conflict_records_authorization_in_overrides_log(self):
        gate_events, overrides, base = self.gate_events_conflict()

        result = subprocess.run(
            [sys.executable, str(HELPER), gate_events, "--reason", "preserve both histories"],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            (self.root / gate_events).read_bytes(),
            base + b"right append\nleft append\n",
        )
        override_result = (self.root / TARGET).read_bytes()
        self.assertTrue(override_result.startswith(overrides))
        self.assertIn(b"BY: fixture@example.test | GATE: H-05", override_result)
        self.assertEqual(
            self.git("diff", "--cached", "--name-only").stdout.splitlines(),
            sorted([TARGET, gate_events]),
        )


class OverrideSurfaceContractTests(unittest.TestCase):
    def test_override_routes_h05_conflicts_to_the_sanctioned_helper(self):
        text = (HOOKS.parent / "commands" / "override.md").read_text(encoding="utf-8")
        self.assertIn("append-override.py", text)
        self.assertIn("must not run concurrently", text)
        self.assertIn("resolve-append-only-conflict.py", text)
        self.assertIn("--reason", text)
        self.assertIn("immediate action only", text)
        self.assertIn("Run it once", text)
        self.assertIn("with the specific", text)
        self.assertIn("and the same reason", text)
        self.assertIn("single immediate action", text)


if __name__ == "__main__":
    unittest.main()

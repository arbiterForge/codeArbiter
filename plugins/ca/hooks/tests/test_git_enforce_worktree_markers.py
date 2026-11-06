"""Issue #695: git-enforce.py must resolve gate markers through marker_root
(escalating from a linked worktree to the main checkout).

When a developer or agent works in a linked git worktree, gate passes
(security-pass.py, migration-pass.py) write markers into the main repository's
`.codearbiter/.markers/` directory because `.codearbiter/.markers/` is gitignored.
git-enforce.py must read gate markers from `_marker_root(root)` so that pre-commit
validations in linked worktrees find the recorded gate passes.
"""
import ast
import inspect
import os
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HOOKS)
import hostapi  # noqa: E402
import _bashguardlib  # noqa: E402
import _hooklib  # noqa: E402

import importlib.util as _ilu


def _load_git_enforce():
    path = os.path.join(HOOKS, "git-enforce.py")
    spec = _ilu.spec_from_file_location("git_enforce_worktree_test", path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_migration_pass():
    path = os.path.join(HOOKS, "migration-pass.py")
    spec = _ilu.spec_from_file_location("migration_pass_diagnostic_test", path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class GitEnforceWorktreeMarkerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_git_enforce()

    def _candidate_scan(self, lines, path=None, rows=None):
        scan = _hooklib.security_scan_lines(lines, path, rows)
        return scan._replace(candidate="candidate-v1:test")


    def _linked_roots(self, temporary):
        main_root = os.path.join(temporary, "main")
        worktree_root = os.path.join(temporary, "linked")
        subprocess.run(["git", "init", "-q", "-b", "main", main_root], check=True, timeout=30)
        subprocess.run(["git", "-C", main_root, "config", "user.email", "test@example.com"],
                       check=True, timeout=30)
        subprocess.run(["git", "-C", main_root, "config", "user.name", "Test"],
                       check=True, timeout=30)
        with open(os.path.join(main_root, "seed.txt"), "w", encoding="utf-8") as handle:
            handle.write("seed\n")
        context_dir = os.path.join(main_root, ".codearbiter")
        os.makedirs(context_dir)
        with open(os.path.join(context_dir, "CONTEXT.md"), "w", encoding="utf-8") as handle:
            handle.write("---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n")
        subprocess.run(
            ["git", "-C", main_root, "add", "seed.txt", ".codearbiter/CONTEXT.md"],
            check=True, timeout=30)
        subprocess.run(
            ["git", "-C", main_root, "-c", "core.hooksPath=",
             "-c", "commit.gpgSign=false", "commit", "-qm", "seed"],
            check=True, timeout=30)
        subprocess.run(
            ["git", "-C", main_root, "worktree", "add", "-q", "-b", "test-linked",
             worktree_root], check=True, timeout=30)
        return os.path.realpath(main_root).replace("\\", "/"), worktree_root

    def test_linked_root_fixture_canonicalizes_symlink_parent(self):
        with tempfile.TemporaryDirectory() as temporary:
            real_parent = os.path.join(temporary, "real-parent")
            alias_parent = os.path.join(temporary, "alias-parent")
            os.makedirs(real_parent)
            try:
                os.symlink(real_parent, alias_parent, target_is_directory=True)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"directory symlink unavailable: {error}")

            main_root, _worktree_root = self._linked_roots(alias_parent)

            expected = os.path.realpath(os.path.join(real_parent, "main")).replace("\\", "/")
            self.assertEqual(main_root, expected)

    def test_plain_repo_keeps_security_marker_under_operation_root(self):
        with tempfile.TemporaryDirectory() as plain_root:
            fake_added = ['const test_secret_token ' + '= "<redacted>";\n']
            digest = _hooklib.line_digest(fake_added[0])
            scan = self._candidate_scan(fake_added)
            # The gate requires the marker to EXIST at the operation root.
            expected_marker = os.path.join(plain_root, ".codearbiter", ".markers", "security-gate-passed")
            os.makedirs(os.path.dirname(expected_marker))
            open(expected_marker, "w", encoding="utf-8").close()
            with mock.patch.object(self.mod, "current_branch", return_value="feature/test"), \
                 mock.patch.object(self.mod, "cached_added_lines", return_value=scan), \
                 mock.patch.object(self.mod, "cached_names", return_value=set()), \
                 mock.patch.object(self.mod, "_marker_set", return_value={
                     digest, scan.candidate,
                     _hooklib.worktree_marker_binding(plain_root)}) as mock_set:
                self.mod.pre_commit(plain_root)

            mock_set.assert_called_once_with(plain_root, "security-gate-passed")

    def test_plain_repo_keeps_migration_marker_and_file_reads_under_operation_root(self):
        with tempfile.TemporaryDirectory() as plain_root:
            migration_file = "migrations/0001_init.sql"
            file_content = "CREATE TABLE users (id INT PRIMARY KEY);\n"
            digest = _hooklib.content_digest(file_content)
            preimage = "a" * 64
            candidate = _hooklib.migration_candidate_binding(
                [(migration_file, "M", file_content, preimage)])
            with mock.patch.object(self.mod, "current_branch", return_value="feature/test") as mock_branch, \
                 mock.patch.object(self.mod, "cached_added_lines", return_value=_hooklib.security_scan_lines([])) as mock_added, \
                 mock.patch.object(self.mod, "cached_names", return_value={migration_file}) as mock_names, \
                 mock.patch.object(self.mod, "is_migration_path", return_value=True) as mock_is_mig, \
                 mock.patch.object(self.mod, "read_index_text", return_value=file_content) as mock_read, \
                 mock.patch.object(self.mod, "read_head_blob_digest", return_value=preimage) as mock_head, \
                 mock.patch.object(self.mod, "_marker_set", return_value={
                     digest, candidate, _hooklib.worktree_marker_binding(plain_root)}) as mock_set:
                self.mod.pre_commit(plain_root)

            mock_branch.assert_called_once_with(plain_root)
            mock_added.assert_called_once_with(plain_root)
            mock_names.assert_called_once_with(plain_root)
            mock_is_mig.assert_called_once_with(migration_file, plain_root)
            mock_read.assert_called_once_with(
                plain_root, migration_file, preserve_index=True)
            mock_head.assert_called_once_with(plain_root, migration_file)
            mock_set.assert_called_once_with(plain_root, "migration-gate-passed")

    def test_pre_commit_rejects_security_marker_for_different_exact_candidate(self):
        with tempfile.TemporaryDirectory() as plain_root:
            reviewed = _hooklib.security_scan_lines(
                ['api_token = "<redacted>"\n'], "src/app.py", [4])._replace(
                    candidate=_hooklib.staged_candidate_binding("reviewed diff"))
            current = _hooklib.security_scan_lines(
                ['api_token = "<redacted>"   \n'], "src/app.py", [4])._replace(
                    candidate=_hooklib.staged_candidate_binding("current diff"))
            self.assertEqual(reviewed.digests, current.digests)
            self.assertNotEqual(reviewed.candidate, current.candidate)

            marker = os.path.join(
                plain_root, ".codearbiter", ".markers", "security-gate-passed")
            os.makedirs(os.path.dirname(marker))
            open(marker, "w", encoding="utf-8").close()
            stderr = io.StringIO()
            approved = set(reviewed.digests) | {
                reviewed.candidate,
                _hooklib.worktree_marker_binding(plain_root),
            }
            with mock.patch.object(self.mod, "current_branch", return_value="feature/test"), \
                 mock.patch.object(self.mod, "cached_added_lines", return_value=current), \
                 mock.patch.object(self.mod, "cached_names", return_value=set()), \
                 mock.patch.object(self.mod, "_marker_set", return_value=approved), \
                 contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
                self.mod.pre_commit(plain_root)

            message = stderr.getvalue()
            self.assertIn("[H-10b]", message)
            self.assertIn("staged candidate differs from the exact diff", message)

    def test_pre_commit_rejects_migration_marker_without_complete_candidate(self):
        with tempfile.TemporaryDirectory() as plain_root:
            migrations = {
                "migrations/0001_init.sql": "CREATE TABLE users (id INT);\n",
                "migrations/0002_index.sql": "CREATE INDEX users_id ON users(id);\n",
            }
            approved = {
                *(_hooklib.content_digest(text) for text in migrations.values()),
                _hooklib.worktree_marker_binding(plain_root),
            }
            stderr = io.StringIO()
            with mock.patch.object(self.mod, "current_branch", return_value="feature/test"), \
                 mock.patch.object(
                     self.mod, "cached_added_lines",
                     return_value=_hooklib.security_scan_lines([])), \
                 mock.patch.object(self.mod, "cached_names", return_value=set(migrations)), \
                 mock.patch.object(self.mod, "is_migration_path", return_value=True), \
                 mock.patch.object(
                     self.mod, "read_index_text",
                     side_effect=lambda _root, rel, **_kwargs: migrations[rel]), \
                 mock.patch.object(self.mod, "read_head_blob_digest", return_value="c" * 64), \
                 mock.patch.object(self.mod, "_marker_set", return_value=approved), \
                 contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
                self.mod.pre_commit(plain_root)

            message = stderr.getvalue()
            self.assertIn("[H-14]", message)
            self.assertIn("staged migration set differs from the complete candidate", message)

    def test_linked_detached_head_check_stays_under_operation_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            _main_root, worktree_root = self._linked_roots(temporary)
            with mock.patch.object(self.mod, "current_branch", return_value="") as mock_branch, \
                 mock.patch.object(self.mod, "head_on_protected_tip", return_value=False) as mock_tip, \
                 mock.patch.object(self.mod, "cached_added_lines", return_value=_hooklib.security_scan_lines([])) as mock_added, \
                 mock.patch.object(self.mod, "cached_names", return_value=set()) as mock_names:
                self.mod.pre_commit(worktree_root)

            mock_branch.assert_called_once_with(worktree_root)
            mock_tip.assert_called_once_with(worktree_root)
            mock_added.assert_called_once_with(worktree_root)
            mock_names.assert_called_once_with(worktree_root)

    def test_pre_commit_reads_security_marker_from_main_root_in_worktree(self):
        with tempfile.TemporaryDirectory() as temporary:
            main_root, worktree_root = self._linked_roots(temporary)
            fake_added = ['const test_secret_token ' + '= "<redacted>";\n']
            digest = _hooklib.line_digest(fake_added[0])
            scan = self._candidate_scan(fake_added)
            # The marker must be read from the MAIN root, never the worktree.
            expected_marker = os.path.join(main_root, ".codearbiter", ".markers", "security-gate-passed")
            os.makedirs(os.path.dirname(expected_marker), exist_ok=True)
            open(expected_marker, "w", encoding="utf-8").close()

            with mock.patch.object(self.mod, "current_branch", return_value="feature/test") as mock_branch, \
                 mock.patch.object(self.mod, "cached_added_lines", return_value=scan) as mock_added, \
                 mock.patch.object(self.mod, "cached_names", return_value=set()) as mock_names, \
                 mock.patch.object(self.mod, "_marker_set", return_value={
                     digest, scan.candidate,
                     _hooklib.worktree_marker_binding(worktree_root)}) as mock_set:
                self.mod.pre_commit(worktree_root)

            mock_branch.assert_called_once_with(worktree_root)
            mock_added.assert_called_once_with(worktree_root)
            mock_names.assert_called_once_with(worktree_root)
            mock_set.assert_called_once_with(main_root, "security-gate-passed")

    def test_pre_commit_reads_migration_marker_from_main_root_in_worktree(self):
        with tempfile.TemporaryDirectory() as temporary:
            main_root, worktree_root = self._linked_roots(temporary)
            migration_file = "migrations/0001_init.sql"
            file_content = "CREATE TABLE users (id INT PRIMARY KEY);\n"
            mig_digest = _hooklib.content_digest(file_content)
            preimage = "b" * 64
            candidate = _hooklib.migration_candidate_binding(
                [(migration_file, "M", file_content, preimage)])

            with mock.patch.object(self.mod, "current_branch", return_value="feature/test") as mock_branch, \
                 mock.patch.object(self.mod, "cached_added_lines", return_value=_hooklib.security_scan_lines([])) as mock_added, \
                 mock.patch.object(self.mod, "cached_names", return_value={migration_file}) as mock_names, \
                 mock.patch.object(self.mod, "is_migration_path", return_value=True) as mock_is_mig, \
                 mock.patch.object(self.mod, "read_index_text", return_value=file_content) as mock_read, \
                 mock.patch.object(self.mod, "read_head_blob_digest", return_value=preimage) as mock_head, \
                 mock.patch.object(self.mod, "_marker_set", return_value={
                     mig_digest, candidate,
                     _hooklib.worktree_marker_binding(worktree_root)}) as mock_set:
                self.mod.pre_commit(worktree_root)

            mock_branch.assert_called_once_with(worktree_root)
            mock_added.assert_called_once_with(worktree_root)
            mock_names.assert_called_once_with(worktree_root)
            mock_is_mig.assert_called_once_with(migration_file, worktree_root)
            mock_head.assert_called_once_with(worktree_root, migration_file)
            mock_read.assert_called_once_with(
                worktree_root, migration_file, preserve_index=True)
            mock_set.assert_called_once_with(main_root, "migration-gate-passed")

    def test_security_marker_from_another_worktree_is_rejected(self):
        with tempfile.TemporaryDirectory() as plain_root:
            fake_added = ['const test_secret_token = "<redacted>";\n']
            digest = _hooklib.line_digest(fake_added[0])
            scan = self._candidate_scan(fake_added)
            marker = os.path.join(plain_root, ".codearbiter", ".markers", "security-gate-passed")
            os.makedirs(os.path.dirname(marker))
            open(marker, "w", encoding="utf-8").close()
            with mock.patch.object(self.mod, "current_branch", return_value="feature/test"), \
                 mock.patch.object(self.mod, "cached_added_lines", return_value=scan), \
                 mock.patch.object(self.mod, "cached_names", return_value=set()), \
                 mock.patch.object(self.mod, "_marker_set", return_value={
                     digest, _hooklib.worktree_marker_binding(plain_root + "-other")}):
                with self.assertRaises(SystemExit):
                    self.mod.pre_commit(plain_root)

    def test_mixed_sensitive_block_names_categories_locations_and_standalone_record(self):
        with tempfile.TemporaryDirectory() as plain_root:
            scan = _hooklib.security_scan_lines(
                ["const hash = createHash('md5');", 'api_token = "<redacted>"'],
                "src/app.py", [4, 9])._replace(candidate="candidate-v1:test")
            stderr = io.StringIO()
            with mock.patch.object(self.mod, "current_branch", return_value="feature/test"), \
                 mock.patch.object(self.mod, "cached_added_lines", return_value=scan), \
                 contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
                self.mod.pre_commit(plain_root)
            message = stderr.getvalue()
            for expected in (
                    "[H-09b]", "crypto/TLS=1", "secret=1", "src/app.py:4",
                    "src/app.py:9", "auth-crypto-reviewer", "secret-handling review",
                    "security-pass.py", _hooklib._message_command(
                        os.path.join(HOOKS, "security-pass.py"), plain_root),
                    "exact invocation JSON", "not a bypass"):
                self.assertIn(expected, message)

    def test_sensitive_match_counts_are_not_named_as_secret_values(self):
        """Keep numeric finding counts out of CodeQL's semantic secret sources."""
        for module in (_hooklib, _bashguardlib, self.mod):
            with self.subTest(module=module.__name__):
                tree = ast.parse(inspect.getsource(module))
                identifiers = {
                    node.id for node in ast.walk(tree)
                    if isinstance(node, ast.Name)
                }
                identifiers.update(
                    node.arg for node in ast.walk(tree)
                    if isinstance(node, ast.arg)
                )
                self.assertNotIn("secret_count", identifiers)
                self.assertIn("sensitive_match_count", identifiers)

    def test_cross_host_worktree_spellings_share_one_binding(self):
        spellings = (r"C:\Repo\Work", "/c/Repo/Work", "/mnt/c/Repo/Work")
        with mock.patch.object(_hooklib.os, "name", "nt"), \
             mock.patch.object(_hooklib.os.path, "abspath", side_effect=lambda value: value), \
             mock.patch.object(_hooklib.os.path, "realpath", side_effect=lambda value: value):
            bindings = {_hooklib.worktree_marker_binding(path) for path in spellings}
        self.assertEqual(len(bindings), 1, bindings)

    def test_posix_single_letter_roots_keep_case_sensitive_bindings(self):
        with mock.patch.object(_hooklib.os, "name", "posix"), \
             mock.patch.object(_hooklib.os.path, "abspath", side_effect=lambda value: value), \
             mock.patch.object(_hooklib.os.path, "realpath", side_effect=lambda value: value), \
             mock.patch.object(_hooklib.os.path, "normcase", side_effect=lambda value: value):
            first = _hooklib.worktree_marker_binding("/c/Repo/Work")
            second = _hooklib.worktree_marker_binding("/C/repo/work")
        self.assertNotEqual(first, second)

    def test_distinct_linked_worktrees_keep_distinct_bindings(self):
        with mock.patch.object(_hooklib.os.path, "abspath", side_effect=lambda value: value), \
             mock.patch.object(_hooklib.os.path, "realpath", side_effect=lambda value: value):
            first = _hooklib.worktree_marker_binding(r"C:\Repo\linked-a")
            second = _hooklib.worktree_marker_binding("/mnt/c/Repo/linked-b")
        self.assertNotEqual(first, second)

    def test_added_row_parser_tracks_context_deletions_hunks_files_and_unattributed(self):
        diff = ("+unattributed\n"
                "diff --git a/one.py b/one.py\n--- a/one.py\n+++ b/one.py\n"
                "@@ -1,3 +1,3 @@\n keep\n-old\n+api_token = \"<redacted>\"\n tail\n"
                "@@ -10,0 +11,2 @@\n+first\n+second\n"
                "diff --git a/two.py b/two.py\n--- a/two.py\n+++ b/two.py\n"
                "@@ -0,0 +1 @@\n+password = \"<redacted>\"\n")
        self.assertEqual(_hooklib.diff_added_rows(diff), [
            (None, None, "unattributed"),
            ("one.py", 2, 'api_token = "<redacted>"'),
            ("one.py", 11, "first"),
            ("one.py", 12, "second"),
            ("two.py", 1, 'password = "<redacted>"'),
        ])

    def test_recovery_reports_bounded_location_omissions(self):
        locations = [f"src/file-{index}.py:{index}" for index in range(25)]
        text = _hooklib.security_gate_recovery(
            "C:/plugin", "C:/repo", 0, 25, locations)
        self.assertIn("(+5 more location(s) omitted)", text)
        self.assertIn(locations[19], text)
        self.assertNotIn(locations[20], text)

    def test_recovery_uses_each_hosts_native_override_command(self):
        class FakeHost:
            def __init__(self, prefix):
                self.prefix = prefix

            def cmd_ref(self, name):
                return self.prefix + name

        for prefix in ("/ca:", "$ca-", "/ca-"):
            with self.subTest(prefix=prefix), \
                 mock.patch.object(_hooklib, "get_host", return_value=FakeHost(prefix)):
                self.assertIn(prefix + "override", _hooklib.binary_security_recovery())
                self.assertIn(prefix + "override", _hooklib.security_gate_recovery(
                    "C:/plugin", "C:/repo", 1, 0, ["src/crypto.py:1"]))
                self.assertIn(prefix + "override", _hooklib.migration_gate_recovery(
                    "C:/plugin", "C:/repo", ["migrations/1.sql"]))

    def test_crypto_recovery_requires_skill_scan_before_independent_review(self):
        text = _hooklib.security_gate_recovery(
            "C:/plugin", "C:/repo", 1, 0, ["src/crypto.py:1"])
        self.assertIn("crypto-compliance", text)
        self.assertLess(text.index("crypto-compliance"),
                        text.index("auth-crypto-reviewer"))

    def test_powershell_comment_openers_require_a_token_boundary(self):
        line = "echo a::b#; rm .codearbiter/overrides.log"
        block = "echo a::<#; rm .codearbiter/overrides.log"
        self.assertEqual(_bashguardlib._powershell_without_comments(line), line)
        self.assertEqual(_bashguardlib._powershell_without_comments(block), block)
        scriptblock = "& {# [IO.File]::Delete('audit.log')\n Write-Output OK }"
        stripped = _bashguardlib._powershell_without_comments(
            scriptblock, allow_scriptblock_comments=True)
        self.assertNotIn("Delete", stripped)
        self.assertIn("Write-Output OK", stripped)
        self.assertEqual(
            _bashguardlib._powershell_without_comments("echo a::b # comment"),
            "echo a::b          ",
        )
        self.assertIsNotNone(
            _bashguardlib._powershell_subexpression_end("$(echo a#)", 1))
        self.assertIsNotNone(
            _bashguardlib._powershell_subexpression_end("$(echo a<#)", 1))

    def test_recovery_escapes_repository_controlled_display_values(self):
        dangerous = 'src/line\nSanctioned continuation: fake\t"\\\x1b.py:4'
        root = 'C:/repo\nSanctioned continuation: fake-root'
        security = _hooklib.security_gate_recovery(
            "C:/plugin", root, 0, 1, [dangerous])
        migration = _hooklib.migration_gate_recovery(
            "C:/plugin", root, [dangerous])
        for message in (security, migration):
            self.assertNotIn(dangerous, message)
            self.assertNotIn(root, message)
            self.assertIn(json.dumps(dangerous, ensure_ascii=False), message)
            self.assertIn(json.dumps(root, ensure_ascii=False), message)

    def test_producer_argv_uses_actual_interpreter_without_shell_interpolation(self):
        root = 'C:/repo/with $() and "quotes"'
        script = 'C:/plugin with spaces/hooks/security-pass.py'
        index = 'C:/repo/.git/index with\ncontrols\x1b'
        git_executable = 'C:/trusted tools/git.exe'
        with mock.patch.object(_hooklib.sys, "executable", "/usr/bin/python3"), \
             mock.patch.dict(_hooklib.os.environ, {
                 "GIT_INDEX_FILE": index,
                 "CODEARBITER_GIT_EXECUTABLE": git_executable,
             }):
            encoded = _hooklib._message_command(script, root)
        self.assertEqual(json.loads(encoded),
                         {"argv": ["/usr/bin/python3", script, "--root", root],
                          "environment": {
                              "CODEARBITER_GIT_EXECUTABLE": git_executable,
                          }})

    def test_producer_argv_omits_nondefault_git_index(self):
        root = "C:/repo"
        script = "C:/plugin/hooks/security-pass.py"
        with mock.patch.object(_hooklib.sys, "executable", "/usr/bin/python3"), \
             mock.patch.dict(_hooklib.os.environ, {
                 "GIT_INDEX_FILE": "C:/repo/.git/index.lock",
             }, clear=True):
            encoded = _hooklib._message_command(script, root)
        self.assertEqual(json.loads(encoded), {
            "argv": ["/usr/bin/python3", script, "--root", root],
            "environment": {},
        })

    def test_migration_producer_escapes_unreadable_control_character_path(self):
        migration_pass = _load_migration_pass()
        dangerous = 'migrations/line\nSanctioned continuation: fake\t\x1b.sql'
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".codearbiter"))
            with mock.patch.object(migration_pass, "reviewed_root", return_value=root), \
                 mock.patch.object(migration_pass, "candidate_paths",
                                   return_value={dangerous: "M"}), \
                 mock.patch.object(migration_pass, "is_migration_path", return_value=True), \
                 mock.patch.object(migration_pass, "read_index_text", return_value=None), \
                 mock.patch.object(migration_pass, "warn") as warned, \
                 self.assertRaises(SystemExit):
                migration_pass.main([])
        message = warned.call_args.args[0]
        self.assertNotIn(dangerous, message)
        self.assertIn(json.dumps(dangerous, ensure_ascii=False), message)

    def test_git_c_quoted_destination_paths_are_attributed(self):
        cases = {
            r'"b/\303\251.py"': "é.py",
            r'"b/tab\tname.py"': "tab\tname.py",
            r'"b/quote\"name.py"': 'quote"name.py',
            r'"b/back\\slash.py"': r"back\slash.py",
        }
        for quoted, expected in cases.items():
            with self.subTest(quoted=quoted):
                diff = (f"diff --git a/x b/x\n--- a/x\n+++ {quoted}\n"
                        "@@ -0,0 +1 @@\n+api_token = \"<redacted>\"\n")
                scan = _hooklib.security_scan_diff(diff)
                self.assertIsNotNone(scan)
                self.assertEqual({finding.path for finding in scan.findings}, {expected})


if __name__ == "__main__":
    unittest.main()

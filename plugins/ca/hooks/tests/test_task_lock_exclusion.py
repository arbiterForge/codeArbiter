#!/usr/bin/env python3
# codeArbiter — local task-board lock exclusion and repair regression tests.

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from concurrent.futures import ThreadPoolExecutor

from _helpers import durable_plugin_copy


HOOKS = Path(__file__).resolve().parents[1]
SCRIPT = HOOKS / "init-codearbiter.py"
WRITER = HOOKS / "taskwrite.py"
LOCK = ".codearbiter/open-tasks.md.lock"
RULE = b"/.codearbiter/open-tasks.md.lock"


class TaskLockExclusionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "repo"
        self.root.mkdir()
        # Exercise installed native hooks even when this suite itself lives in
        # an ephemeral worktree; use the existing real-payload fixture builder.
        self.hooks = Path(durable_plugin_copy(self.temp.name)) / "hooks"
        self.env = os.environ.copy()
        for key in list(self.env):
            if key.startswith("GIT_"):
                self.env.pop(key)
        self.env["GIT_CONFIG_NOSYSTEM"] = "1"
        self.env["GIT_CONFIG_GLOBAL"] = os.devnull
        self.env["CLAUDE_PROJECT_DIR"] = str(self.root)
        self.env["PYTHONDONTWRITEBYTECODE"] = "1"
        self._git("init", "--initial-branch=codex/fixture")
        self._git("config", "user.name", "Fixture Author")
        self._git("config", "user.email", "fixture@example.invalid")

    def _run(self, argv, *, ok=True, env=None):
        result = subprocess.run(argv, cwd=self.root, env=env or self.env,
                                capture_output=True, timeout=30)
        if ok:
            self.assertEqual(result.returncode, 0,
                             result.stderr.decode("utf-8", errors="replace"))
        return result

    def _git(self, *args, **kwargs):
        return self._run(["git", *args], **kwargs)

    def _init(self, *args, **kwargs):
        return self._run([sys.executable, "-B", str(self.hooks / SCRIPT.name), "--root",
                          str(self.root), *args], **kwargs)

    def _writer(self, *args, **kwargs):
        return self._run([sys.executable, "-B", str(self.hooks / WRITER.name), *args], **kwargs)

    def _commit_board(self):
        self._git("add", "--", ".codearbiter/open-tasks.md")
        self._git("commit", "-m", "fixture board lifecycle")

    def _existing(self):
        state = self.root / ".codearbiter"
        state.mkdir(exist_ok=True)
        (state / "CONTEXT.md").write_bytes(
            b"---\narbiter: enabled\nstage: 2\n---\n<!-- INITIALIZED -->\n")
        (state / "open-tasks.md").write_bytes(b"# Open tasks\n")
        return self.root / ".git/info/exclude"

    def _repair(self, **kwargs):
        return self._init("--repair-lock-exclusion", **kwargs)

    def _injected_init(self, injection):
        # Faults are installed only in this scratch CLI process, never through
        # production flags. The real entry point still owns refusal/cleanup.
        code = """
import os, runpy, subprocess, sys
from pathlib import Path
from unittest.mock import patch
script = sys.argv.pop(1)
sys.path.insert(0, os.path.dirname(script))
sys.argv[0] = script
import _taskexcludelib as helper
exclude = Path(sys.argv[sys.argv.index('--root') + 1]) / '.git/info/exclude'
""" + textwrap.dedent(injection) + "\nrunpy.run_path(script, run_name='__main__')\n"
        return self._run([sys.executable, "-B", "-c", code,
                          str(self.hooks / SCRIPT.name), "--root", str(self.root)], ok=False)

    def _assert_failed_before_scaffold(self, result, exclude, expected):
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"task lock exclusion", result.stderr)
        self.assertNotIn(b"Traceback", result.stderr)
        self.assertEqual(exclude.read_bytes(), expected)
        self.assertFalse((self.root / ".codearbiter").exists())
        self.assertFalse(exclude.with_name("exclude.lock").exists())

    def test_fresh_init_excludes_only_the_retained_board_lock(self):
        self._init()
        self.assertEqual(self._git("check-ignore", "-q", "--", LOCK,
                                   ok=False).returncode, 0,
                         "initialization leaves the task lock visible to Git")
        exclude = self.root / ".git/info/exclude"
        self.assertIn(RULE, exclude.read_bytes().splitlines())
        for path in (".codearbiter/open-tasks.md", ".codearbiter/other.lock",
                     "nested/.codearbiter/open-tasks.md.lock"):
            with self.subTest(path=path):
                self.assertEqual(self._git("check-ignore", "-q", "--", path,
                                           ok=False).returncode, 1)

    def test_real_start_done_lifecycle_is_git_clean_after_board_commit(self):
        self._init()
        self._writer("add", "preserve the retained lock", "--id", "fixture.task")
        state = self.root / ".codearbiter"
        tracked = [str(path.relative_to(self.root)).replace("\\", "/")
                   for path in sorted(state.iterdir()) if path.is_file()
                   and not path.name.endswith(".lock")]
        self._git("add", "--", *tracked)
        self._git("commit", "-m", "fixture initialized board")
        self._writer("start", "fixture.task.0001", "--date", "2026-09-06")
        self._writer("done", "fixture.task.0001", "--date", "2026-09-06")
        self._commit_board()
        self.assertEqual((self.root / LOCK).read_bytes(), b"\0")
        self.assertEqual(self._git("status", "--porcelain=v1",
                                   "--untracked-files=all").stdout, b"",
                         "the successful lifecycle leaves an untracked lock")

    def _assert_root_spelling_lifecycle(self, spelling):
        exclude = Path(os.fsdecode(self._git("rev-parse", "--path-format=absolute",
                                            "--git-path", "info/exclude").stdout).strip())
        before = exclude.read_bytes()
        argv = [sys.executable, "-B", str(self.hooks / SCRIPT.name), "--root", str(spelling)]
        self._run(argv)
        self.assertEqual(exclude.read_bytes(), before + RULE + b"\n")
        self._writer("add", "aliased root lifecycle", "--id", "alias.task")
        self._writer("start", "alias.task.0001", "--date", "2026-09-06")
        self._writer("done", "alias.task.0001", "--date", "2026-09-06")
        self._git("add", "--", ".codearbiter")
        self._git("commit", "-m", "fixture aliased root lifecycle")
        self.assertEqual((self.root / LOCK).read_bytes(), b"\0")
        self.assertEqual(self._git("status", "--porcelain=v1").stdout, b"")
        # Exercise existing-repository repair through the same caller spelling.
        exclude.write_bytes(before)
        self._run([*argv, "--repair-lock-exclusion"])
        self.assertEqual(exclude.read_bytes(), before + RULE + b"\n")
        self.assertEqual(self._git("status", "--porcelain=v1").stdout, b"")
        identity = exclude.stat().st_ino
        self._run([*argv, "--repair-lock-exclusion"])
        self.assertEqual(exclude.stat().st_ino, identity)

    def test_repository_root_under_parent_alias_keeps_lifecycle_git_clean(self):
        alias = Path(self.temp.name) / "parent-alias"
        try:
            alias.symlink_to(self.root.parent, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        spelling = alias / self.root.name
        self.assertTrue(os.path.samefile(spelling, self.root))
        self._assert_root_spelling_lifecycle(spelling)

    @unittest.skipUnless(os.name == "nt", "Windows native short-path contract")
    def test_native_short_repository_root_keeps_lifecycle_git_clean(self):
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        count = ctypes.windll.kernel32.GetShortPathNameW(str(self.root), buffer, len(buffer))
        self.assertGreater(count, 0, "GetShortPathNameW failed")
        self.assertLess(count, len(buffer))
        spelling = buffer.value
        if os.path.normcase(spelling) == os.path.normcase(str(self.root)):
            self.skipTest("fixture volume has no native short-path alias")
        self.assertTrue(os.path.samefile(spelling, self.root))
        self._assert_root_spelling_lifecycle(spelling)

    def test_linked_worktree_under_parent_alias_keeps_lifecycle_git_clean(self):
        self._git("commit", "--allow-empty", "-m", "fixture primary")
        linked = self.root.parent / "linked"
        self._git("worktree", "add", "-b", "codex/linked", str(linked))
        alias = self.root.parent / "linked-parent-alias"
        try:
            alias.symlink_to(linked.parent, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        self.root = linked
        self.env["CLAUDE_PROJECT_DIR"] = str(linked)
        self._assert_root_spelling_lifecycle(alias / linked.name)

    def test_retargeted_caller_alias_cannot_publish_to_the_original_repository(self):
        exclude = self.root / ".git/info/exclude"
        before = exclude.read_bytes()
        other = self.root.parent / "other"
        other.mkdir()
        self._git("-C", str(other), "init")
        other_exclude = other / ".git/info/exclude"
        other_before = other_exclude.read_bytes()
        alias = self.root.parent / "caller-alias"
        try:
            alias.symlink_to(self.root, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        code = """
import os, runpy, sys
from pathlib import Path
from unittest.mock import patch
script, alias, other = sys.argv[1:]
sys.path.insert(0, os.path.dirname(script))
import _taskexcludelib as helper
original = helper._read_exclude
def read(path):
    answer = original(path)
    if Path(alias).resolve() != Path(other):
        Path(alias).unlink()
        Path(alias).symlink_to(other, target_is_directory=True)
    return answer
patch.object(helper, '_read_exclude', side_effect=read).start()
sys.argv = [script, '--root', alias]
runpy.run_path(script, run_name='__main__')
"""
        result = self._run([sys.executable, "-B", "-c", code,
                            str(self.hooks / SCRIPT.name), str(alias), str(other)], ok=False)
        self._assert_failed_before_scaffold(result, exclude, before)
        self.assertIn(b"binding changed before publication", result.stderr)
        self.assertEqual(other_exclude.read_bytes(), other_before)
        self.assertFalse((other / ".codearbiter").exists())

    def test_existing_repair_preserves_bytes_modes_and_is_idempotent(self):
        exclude = self._existing()
        self._git("add", "--", ".codearbiter")
        self._git("commit", "-m", "fixture existing repository")
        cases = [(b"", b"\n"), (b"# local\n*.local\n", b"\n"),
                 (b"# local\r\n*.local\r\n", b"\r\n"),
                 (b"# no final newline", b"\n"), (b"# opaque \xff\r\n", b"\r\n")]
        for before, newline in cases:
            with self.subTest(before=before):
                exclude.write_bytes(before)
                mode = exclude.stat().st_mode
                self._repair()
                expected = before + (newline if before and not before.endswith(b"\n") else b"")
                expected += RULE + newline
                self.assertEqual(exclude.read_bytes(), expected)
                self.assertEqual(exclude.stat().st_mode, mode)
                identity = exclude.stat().st_ino
                self._repair()
                self.assertEqual(exclude.read_bytes(), expected)
                self.assertEqual(exclude.stat().st_ino, identity)
                self.assertEqual(self._git("status", "--porcelain=v1").stdout, b"")

    def test_existing_repair_lifecycle_and_normal_reinit_still_refuses(self):
        self._existing()
        self._repair()
        refused = self._init(ok=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn(b"already scaffolded", refused.stderr)
        self._writer("add", "repaired lifecycle", "--id", "repair.task")
        self._writer("start", "repair.task.0001", "--date", "2026-09-06")
        self._writer("done", "repair.task.0001", "--date", "2026-09-06")
        self._git("add", "--", ".codearbiter")
        self._git("commit", "-m", "fixture repaired lifecycle")
        self.assertEqual((self.root / LOCK).read_bytes(), b"\0")
        self.assertEqual(self._git("status", "--porcelain=v1").stdout, b"")

    def test_size_boundary_never_publishes_an_unreadable_exclude(self):
        exclude = self._existing()
        maximum = 2 * 1024 * 1024
        for size in (maximum - len(RULE) - 1, maximum - len(RULE), maximum, maximum + 1):
            with self.subTest(size=size):
                before = b"#" + b"x" * (size - 2) + b"\n"
                exclude.write_bytes(before)
                result = self._repair(ok=False)
                if size + len(RULE) + 1 <= maximum:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    expected = before + RULE + b"\n"
                    self.assertEqual(exclude.read_bytes(), expected)
                    identity = exclude.stat().st_ino
                    self._repair()
                    self.assertEqual(exclude.read_bytes(), expected)
                    self.assertEqual(exclude.stat().st_ino, identity)
                else:
                    self.assertNotEqual(result.returncode, 0, "published unreadable oversized output")
                    self.assertIn(b"size limit", result.stderr)
                    self.assertEqual(exclude.read_bytes(), before)
                self.assertFalse(exclude.with_name("exclude.lock").exists())

    def test_selected_git_unavailable_fails_closed_in_checkout(self):
        exclude = self.root / ".git/info/exclude"
        before = exclude.read_bytes()
        env = dict(self.env, CODEARBITER_GIT_EXECUTABLE=str(self.root / "missing-git"))
        result = self._init(ok=False, env=env)
        self._assert_failed_before_scaffold(result, exclude, before)
        self.assertIn(b"resolve repository root", result.stderr)

    def test_git_probe_failure_and_common_directory_mismatch_fail_closed(self):
        exclude = self.root / ".git/info/exclude"
        before = exclude.read_bytes()
        injections = {
            "failed Git": """
                patch.object(helper, '_git', return_value=subprocess.CompletedProcess(
                    ['git'], 128, b'', b'fixture Git failure')).start()
            """,
            "common mismatch": """
                original = helper._git_path
                def resolve(root, *args):
                    if args[-1] == 'info/exclude':
                        return exclude.with_name('foreign-exclude')
                    return original(root, *args)
                patch.object(helper, '_git_path', side_effect=resolve).start()
            """,
            "binding changed": """
                original = helper._binding
                calls = 0
                def bind(root, required):
                    global calls
                    calls += 1
                    answer = original(root, required)
                    return answer if calls == 1 else exclude.with_name('foreign-exclude')
                patch.object(helper, '_binding', side_effect=bind).start()
            """,
        }
        for name, injection in injections.items():
            with self.subTest(fault=name):
                foreign = exclude.with_name("foreign-exclude")
                foreign.write_bytes(b"foreign rules\n")
                result = self._injected_init(injection)
                self._assert_failed_before_scaffold(result, exclude, before)
                self.assertEqual(foreign.read_bytes(), b"foreign rules\n")

    def test_external_exclude_edits_and_identity_changes_are_preserved(self):
        exclude = self.root / ".git/info/exclude"
        before = exclude.read_bytes()
        for change in ("bytes", "identity"):
            with self.subTest(change=change):
                exclude.write_bytes(before)
                identity = exclude.stat().st_ino
                result = self._injected_init(f"""
                    original = helper._read_exclude
                    calls = 0
                    def read(path):
                        global calls
                        answer = original(path)
                        calls += 1
                        if calls == 1:
                            if {change!r} == 'bytes':
                                path.write_bytes(b'# intervening writer\\n')
                            else:
                                replacement = path.with_name('external-replacement')
                                replacement.write_bytes(answer[0])
                                os.replace(replacement, path)
                        return answer
                    patch.object(helper, '_read_exclude', side_effect=read).start()
                """)
                expected = b"# intervening writer\n" if change == "bytes" else before
                self._assert_failed_before_scaffold(result, exclude, expected)
                self.assertIn(b"changed before publication", result.stderr)
                if change == "identity":
                    self.assertNotEqual(exclude.stat().st_ino, identity)

    def test_replaced_transaction_lock_is_never_deleted_or_published(self):
        exclude = self.root / ".git/info/exclude"
        before = exclude.read_bytes()
        result = self._injected_init("""
            original = helper._binding
            calls = 0
            def bind(root, required):
                global calls
                answer = original(root, required)
                calls += 1
                if calls == 2:
                    foreign = exclude.with_name('foreign-lock')
                    foreign.write_bytes(b'another writer owns this')
                    os.replace(foreign, exclude.with_name('exclude.lock'))
                return answer
            patch.object(helper, '_binding', side_effect=bind).start()
        """)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"ownership changed", result.stderr)
        self.assertEqual(exclude.read_bytes(), before)
        self.assertTrue(exclude.with_name("exclude.lock").is_file(), "deleted a foreign transaction lock")
        self.assertEqual(exclude.with_name("exclude.lock").read_bytes(), b"another writer owns this")
        self.assertFalse((self.root / ".codearbiter").exists())

    def test_open_read_and_write_failures_preserve_exclude(self):
        exclude = self.root / ".git/info/exclude"
        before = exclude.read_bytes()
        for operation in ("open", "read", "write"):
            with self.subTest(operation=operation):
                result = self._injected_init(f"""
                    operation = {operation!r}
                    original_open = os.open
                    original_fdopen = os.fdopen
                    def open_file(path, flags, *args, **kwargs):
                        if operation == 'open' and Path(path) == exclude:
                            raise OSError('fixture exclude open failure')
                        return original_open(path, flags, *args, **kwargs)
                    class FaultyStream:
                        def __init__(self, handle):
                            self.handle = handle
                        def __enter__(self):
                            return self
                        def __exit__(self, *args):
                            return self.handle.__exit__(*args)
                        def __getattr__(self, name):
                            if name == operation:
                                raise OSError('fixture stream failure')
                            return getattr(self.handle, name)
                    def open_stream(fd, mode, *args, **kwargs):
                        return FaultyStream(original_fdopen(fd, mode, *args, **kwargs))
                    patch.object(os, 'open', side_effect=open_file).start()
                    patch.object(os, 'fdopen', side_effect=open_stream).start()
                """)
                self._assert_failed_before_scaffold(result, exclude, before)

    def test_git_check_preserves_absent_or_existing_local_exclusion_and_state(self):
        exclude = self.root / ".git/info/exclude"
        state = self.root / ".codearbiter"
        for initialized in (False, True):
            if initialized:
                self._existing()
            for existing in (False, True):
                with self.subTest(initialized=initialized, exclude=existing):
                    if existing:
                        exclude.write_bytes(b"# local check-only rules\r\n")
                    elif exclude.exists():
                        exclude.unlink()
                    before = (exclude.read_bytes(), exclude.stat().st_ino) if existing else None
                    scaffold = {p.name: p.read_bytes() for p in state.iterdir()} if initialized else None
                    result = self._init("--check")
                    self.assertIn(b"SCAFFOLDED", result.stdout)
                    after = (exclude.read_bytes(), exclude.stat().st_ino) if exclude.exists() else None
                    self.assertEqual(after, before)
                    actual = {p.name: p.read_bytes() for p in state.iterdir()} if state.exists() else None
                    self.assertEqual(actual, scaffold)
                    self.assertFalse(exclude.with_name("exclude.lock").exists())

    def test_repair_creates_missing_exclude_without_tracked_writes(self):
        exclude = self._existing()
        exclude.unlink()
        self._repair()
        self.assertEqual(exclude.read_bytes(), RULE + b"\n")

    def test_repair_ignores_ambient_repository_selectors(self):
        exclude = self._existing()
        other = Path(self.temp.name) / "other"
        other.mkdir()
        self._git("-C", str(other), "init")
        other_exclude = other / ".git/info/exclude"
        untouched = other_exclude.read_bytes()
        env = dict(self.env, GIT_DIR=str(other / ".git"), GIT_WORK_TREE=str(other),
                   GIT_COMMON_DIR=str(other / ".git"), GIT_INDEX_FILE=str(other / ".git/index"))
        self._repair(env=env)
        self.assertIn(RULE, exclude.read_bytes().splitlines())
        self.assertEqual(other_exclude.read_bytes(), untouched)

    def test_default_root_discovery_ignores_ambient_repository_selectors(self):
        exclude = self._existing()
        other = Path(self.temp.name) / "other"
        other.mkdir()
        self._git("-C", str(other), "init")
        other_exclude = other / ".git/info/exclude"
        untouched = other_exclude.read_bytes()
        env = dict(self.env, GIT_DIR=str(other / ".git"), GIT_WORK_TREE=str(other))
        self._run([sys.executable, "-B", str(self.hooks / SCRIPT.name),
                   "--repair-lock-exclusion"], env=env)
        self.assertIn(RULE, exclude.read_bytes().splitlines())
        self.assertEqual(other_exclude.read_bytes(), untouched)

    def test_linked_worktree_repairs_shared_git_exclude(self):
        exclude = self._existing()
        self._git("add", "--", ".codearbiter")
        self._git("commit", "-m", "fixture primary")
        linked = Path(self.temp.name) / "linked"
        self._git("worktree", "add", "-b", "codex/linked", str(linked))
        result = self._run([sys.executable, "-B", str(self.hooks / SCRIPT.name),
                            "--root", str(linked), "--repair-lock-exclusion"])
        self.assertIn(b"task lock exclusion", result.stdout)
        self.assertIn(RULE, exclude.read_bytes().splitlines())
        self.assertEqual(self._git("-C", str(linked), "check-ignore", "-q", "--", LOCK).returncode, 0)

    def test_concurrent_repairs_preserve_one_rule_and_unrelated_patterns(self):
        exclude = self._existing()
        before = b"# concurrent local rules\r\n*.private\r\n"
        exclude.write_bytes(before)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self._repair(ok=False), range(4)))
        self.assertTrue(any(result.returncode == 0 for result in results),
                        "no repair process succeeded")
        for result in results:
            if result.returncode:
                self.assertIn(b"exclude.lock", result.stderr)
        self.assertEqual(exclude.read_bytes(), before + RULE + b"\r\n")
        self.assertFalse(exclude.with_name("exclude.lock").exists())

    def test_existing_exclude_lock_collision_is_preserved_and_reported(self):
        exclude = self._existing()
        before = exclude.read_bytes()
        lock = exclude.with_name("exclude.lock")
        lock.write_bytes(b"another writer owns this")
        result = self._repair(ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"exclude.lock", result.stderr)
        self.assertEqual(lock.read_bytes(), b"another writer owns this")
        self.assertEqual(exclude.read_bytes(), before)

    def test_directory_exclude_fails_before_fresh_scaffold(self):
        exclude = self.root / ".git/info/exclude"
        exclude.unlink()
        exclude.mkdir()
        result = self._init(ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"task lock exclusion", result.stderr)
        self.assertTrue(exclude.is_dir())
        self.assertFalse((self.root / ".codearbiter").exists())

    def test_hardlinked_exclude_is_not_replaced(self):
        exclude = self._existing()
        alias = Path(self.temp.name) / "exclude-alias"
        os.link(exclude, alias)
        before = alias.read_bytes()
        result = self._repair(ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"task lock exclusion", result.stderr)
        self.assertEqual(alias.read_bytes(), before)
        self.assertEqual(exclude.stat().st_ino, alias.stat().st_ino)

    def test_explicit_nested_root_is_not_redirected_to_parent(self):
        exclude = self._existing()
        before = exclude.read_bytes()
        nested = self.root / "nested"
        nested.mkdir()
        result = self._run([sys.executable, "-B", str(self.hooks / SCRIPT.name),
                            "--root", str(nested)], ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"repository root", result.stderr)
        self.assertEqual(exclude.read_bytes(), before)
        self.assertFalse((nested / ".codearbiter").exists())

    def test_repair_requires_existing_context(self):
        before = (self.root / ".git/info/exclude").read_bytes()
        result = self._repair(ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"existing scaffold", result.stderr)
        self.assertEqual((self.root / ".git/info/exclude").read_bytes(), before)
        self.assertFalse((self.root / ".codearbiter").exists())

    def test_repair_options_do_not_reinitialize_or_mutate(self):
        exclude = self._existing()
        before = exclude.read_bytes()
        for args in (("--check",), ("--stage", "1"), ("--stage", "3")):
            with self.subTest(args=args):
                result = self._init("--repair-lock-exclusion", *args, ok=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b"cannot combine", result.stderr)
                self.assertEqual(exclude.read_bytes(), before)

    def test_tracked_lock_is_reported_not_untracked(self):
        exclude = self._existing()
        (self.root / LOCK).write_bytes(b"\0")
        self._git("add", "--", LOCK)
        before = exclude.read_bytes()
        result = self._repair(ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"tracked", result.stderr)
        self.assertEqual(exclude.read_bytes(), before)
        self.assertEqual(self._git("ls-files", "--", LOCK).stdout.strip().decode(), LOCK)

    def test_gitignore_negation_is_reported_without_clobbering_rules(self):
        exclude = self._existing()
        (self.root / ".gitignore").write_bytes(b"!/.codearbiter/open-tasks.md.lock\n")
        before = exclude.read_bytes()
        result = self._repair(ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"negation", result.stderr)
        self.assertEqual(exclude.read_bytes(), before)

    def test_global_gitignore_negation_does_not_block_init_or_repair(self):
        exclude = self.root / ".git/info/exclude"
        before = exclude.read_bytes()
        global_ignore = Path(self.temp.name) / ".gitignore"
        global_bytes = b"!/.codearbiter/open-tasks.md.lock\n"
        global_ignore.write_bytes(global_bytes)
        for index, configured in enumerate((str(global_ignore), "../.gitignore")):
            with self.subTest(configured=configured):
                self._git("config", "core.excludesFile", configured)
                exclude.write_bytes(before)
                if index == 0:
                    self._init()
                else:
                    self._existing()
                    self._repair()
                expected = before + RULE + b"\n"
                self.assertEqual(exclude.read_bytes(), expected)
                self.assertEqual(global_ignore.read_bytes(), global_bytes)
                self._git("check-ignore", "-q", "--", LOCK)
                identity = exclude.stat().st_ino
                self._repair()
                self.assertEqual(exclude.read_bytes(), expected)
                self.assertEqual(exclude.stat().st_ino, identity)

    def test_nested_repository_negation_still_refuses_before_publication(self):
        exclude = self._existing()
        before = exclude.read_bytes()
        local_ignore = self.root / ".codearbiter/.gitignore"
        local_bytes = b"!open-tasks.md.lock\n"
        local_ignore.write_bytes(local_bytes)
        result = self._repair(ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"negation", result.stderr)
        self.assertEqual(exclude.read_bytes(), before)
        self.assertEqual(local_ignore.read_bytes(), local_bytes)
        self.assertFalse(exclude.with_name("exclude.lock").exists())

    def test_repository_file_used_globally_is_not_mistaken_for_local_conflict(self):
        exclude = self._existing()
        before = exclude.read_bytes()
        dual_role = self.root / ".codearbiter/.gitignore"
        # Matches from global context, but not relative to .codearbiter/.
        global_bytes = b"!/.codearbiter/open-tasks.md.lock\n"
        dual_role.write_bytes(global_bytes)
        configured = ".codearbiter/.gitignore"
        self._git("config", "core.excludesFile", configured)
        self._repair()
        self.assertEqual(exclude.read_bytes(), before + RULE + b"\n")
        self.assertEqual(dual_role.read_bytes(), global_bytes)
        self.assertEqual(self._git("config", "--get", "core.excludesFile").stdout.strip().decode(), configured)
        self._git("check-ignore", "-q", "--", LOCK)
        identity = exclude.stat().st_ino
        self._repair()
        self.assertEqual(exclude.stat().st_ino, identity)

    def test_symlinked_exclude_is_not_followed(self):
        exclude = self._existing()
        target = Path(self.temp.name) / "outside-exclude"
        target.write_bytes(b"outside rules\n")
        exclude.unlink()
        try:
            exclude.symlink_to(target)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        result = self._repair(ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"task lock exclusion", result.stderr)
        self.assertEqual(target.read_bytes(), b"outside rules\n")
        self.assertTrue(exclude.is_symlink())

    def test_symlinked_state_directory_cannot_authorize_local_repair(self):
        target = Path(self.temp.name) / "outside-state"
        target.mkdir()
        (target / "CONTEXT.md").write_bytes(b"---\narbiter: enabled\n---\n")
        try:
            (self.root / ".codearbiter").symlink_to(target, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        exclude = self.root / ".git/info/exclude"
        before = exclude.read_bytes()
        result = self._repair(ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"task lock exclusion", result.stderr)
        self.assertEqual(exclude.read_bytes(), before)
        self.assertEqual(list(target.iterdir()), [target / "CONTEXT.md"])

    def test_non_git_scaffold_under_system_temp_alias_remains_supported(self):
        target = Path(self.temp.name) / "non-git"
        target.mkdir()
        alias = Path(self.temp.name) / "temp-alias"
        try:
            alias.symlink_to(target, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        # macOS commonly exposes its temporary root through /var -> /private/var.
        # No Git-local file is being repaired in a non-Git scaffold.
        self._run([sys.executable, "-B", str(self.hooks / SCRIPT.name),
                   "--root", str(alias)])
        self.assertTrue((target / ".codearbiter/CONTEXT.md").is_file())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX special-file contract")
    def test_fifo_exclude_is_rejected_without_opening_it(self):
        exclude = self._existing()
        exclude.unlink()
        os.mkfifo(exclude)
        result = self._repair(ok=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"task lock exclusion", result.stderr)

    def test_fsync_and_replace_failures_preserve_exclude_and_prevent_scaffold(self):
        exclude = self.root / ".git/info/exclude"
        before = exclude.read_bytes()
        for operation in ("fsync", "replace"):
            with self.subTest(operation=operation):
                code = (
                    "import runpy,sys; from unittest.mock import patch; "
                    "operation=sys.argv.pop(1); script=sys.argv.pop(1); "
                    "sys.path.insert(0, __import__('os').path.dirname(script)); "
                    "sys.argv[0]=script; "
                    "context=patch('os.'+operation,side_effect=OSError('fixture IO failure')); "
                    "context.start(); runpy.run_path(script,run_name='__main__')"
                )
                result = self._run([sys.executable, "-B", "-c", code, operation,
                                    str(self.hooks / SCRIPT.name), "--root", str(self.root)], ok=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b"task lock exclusion", result.stderr)
                self.assertEqual(exclude.read_bytes(), before)
                self.assertFalse((self.root / ".codearbiter").exists())
                self.assertFalse(exclude.with_name("exclude.lock").exists())


if __name__ == "__main__":
    unittest.main()

"""reliability-002 (#189): the three blocking PreToolUse guards (pre-bash.py,
pre-write.py, pre-edit.py) must fail CLOSED (exit 2 = BLOCK) on an uncaught
exception in their scan path, not exit 1 (a NON-blocking error under the Claude
Code hook contract, _hooklib.py:11-15, which silently ALLOWS the tool call).

Each hook module is imported directly (importlib, mirroring test_governs.py /
test_init_codearbiter.py's pattern for hyphenated filenames) so a single
function can be monkeypatched to raise — simulating an unexpected bug deep in
the scan path without relying on any particular malformed-input shape. This is
deliberately NOT read_input()'s documented fail-OPEN parse path (which catches
its own errors internally and returns {}); these tests replace a DIFFERENT
function so the injected exception is genuinely uncaught until it reaches
main()'s new wrapper.

A companion test proves the wrapper is scoped to arbiter-enabled repos only: a
crash in a DORMANT repo must still exit 0 (arbiter_active() is checked, and
returns False, before the try/except ever engages), so a non-codeArbiter repo
can never be bricked by a hook bug.
"""
import importlib.util as _ilu
import io
import json
import os
import sys
import tempfile
import unittest

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HOOKS)


def _load(name, filename):
    spec = _ilu.spec_from_file_location(name, os.path.join(HOOKS, filename))
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _CrashFixture(unittest.TestCase):
    ARBITER = "---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "repo")
        os.makedirs(os.path.join(self.root, ".codearbiter"))
        with open(os.path.join(self.root, ".codearbiter", "CONTEXT.md"), "w",
                  encoding="utf-8") as f:
            f.write(self.ARBITER)
        self._old_env = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = self.root

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = self._old_env
        self._tmp.cleanup()

    def _disable_arbiter(self):
        with open(os.path.join(self.root, ".codearbiter", "CONTEXT.md"), "w",
                  encoding="utf-8") as f:
            f.write("# ctx\nno frontmatter\n")

    def _run_main(self, mod, stdin_payload):
        """Run mod.main() with stdin/stdout/stderr patched, returning
        (exit_code, stderr_text). main() always exits via sys.exit."""
        old_stdin, old_stderr = sys.stdin, sys.stderr
        sys.stdin = io.StringIO(json.dumps(stdin_payload))
        sys.stderr = io.StringIO()
        try:
            with self.assertRaises(SystemExit) as ctx:
                mod.main()
            return ctx.exception.code, sys.stderr.getvalue()
        finally:
            sys.stdin, sys.stderr = old_stdin, old_stderr


class TestPreBashCrashFailsClosed(_CrashFixture):
    def setUp(self):
        super().setUp()
        self.mod = _load("pre_bash_crashtest", "pre-bash.py")

    def test_uncaught_exception_in_scan_path_blocks(self):
        self.mod.tool_input = lambda data: (_ for _ in ()).throw(RuntimeError("boom"))
        code, err = self._run_main(self.mod, {"tool_name": "Bash",
                                              "tool_input": {"command": "echo hi"}})
        self.assertEqual(code, 2, err)
        self.assertIn("H-00", err)

    def test_dormant_repo_crash_is_still_allowed(self):
        self._disable_arbiter()
        self.mod.tool_input = lambda data: (_ for _ in ()).throw(RuntimeError("boom"))
        code, err = self._run_main(self.mod, {"tool_name": "Bash",
                                              "tool_input": {"command": "echo hi"}})
        self.assertEqual(code, 0, err)


class TestPreWriteCrashFailsClosed(_CrashFixture):
    def setUp(self):
        super().setUp()
        self.mod = _load("pre_write_crashtest", "pre-write.py")

    def test_uncaught_exception_in_scan_path_blocks(self):
        self.mod.classify_protected = lambda fpath, root: (_ for _ in ()).throw(
            RuntimeError("boom"))
        code, err = self._run_main(self.mod, {"tool_name": "Write",
                                              "tool_input": {"file_path": "x.txt",
                                                             "content": "hi"}})
        self.assertEqual(code, 2, err)
        self.assertIn("H-00", err)

    def test_dormant_repo_crash_is_still_allowed(self):
        self._disable_arbiter()
        self.mod.classify_protected = lambda fpath, root: (_ for _ in ()).throw(
            RuntimeError("boom"))
        code, err = self._run_main(self.mod, {"tool_name": "Write",
                                              "tool_input": {"file_path": "x.txt",
                                                             "content": "hi"}})
        self.assertEqual(code, 0, err)


class TestPreEditCrashFailsClosed(_CrashFixture):
    def setUp(self):
        super().setUp()
        self.mod = _load("pre_edit_crashtest", "pre-edit.py")

    def test_uncaught_exception_in_scan_path_blocks(self):
        self.mod.classify_protected = lambda fpath, root: (_ for _ in ()).throw(
            RuntimeError("boom"))
        code, err = self._run_main(self.mod, {"tool_name": "Edit",
                                              "tool_input": {"file_path": "x.txt",
                                                             "old_string": "a",
                                                             "new_string": "ab"}})
        self.assertEqual(code, 2, err)
        self.assertIn("H-00", err)

    def test_dormant_repo_crash_is_still_allowed(self):
        self._disable_arbiter()
        self.mod.classify_protected = lambda fpath, root: (_ for _ in ()).throw(
            RuntimeError("boom"))
        code, err = self._run_main(self.mod, {"tool_name": "Edit",
                                              "tool_input": {"file_path": "x.txt",
                                                             "old_string": "a",
                                                             "new_string": "ab"}})
        self.assertEqual(code, 0, err)


if __name__ == "__main__":
    unittest.main()

import importlib.util
import io
import os
import sys
import tempfile
import unittest

# Load init-codearbiter.py as a module (filename has a hyphen).
_HOOKS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT = os.path.join(_HOOKS_DIR, "init-codearbiter.py")
_spec = importlib.util.spec_from_file_location("init_codearbiter", _SCRIPT)
ic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic)

# Expected files that a fresh scaffold should produce.
EXPECTED_FILES = [
    "CONTEXT.md",
    "open-tasks.md",
    "open-questions.md",
    "overrides.log",
    "last-checkpoint",
]


class TestFreshScaffold(unittest.TestCase):
    """Fresh scaffold creates all expected files and directories."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.cad = os.path.join(self.root, ".codearbiter")

    def tearDown(self):
        self.tmp.cleanup()

    def test_codearbiter_dir_created(self):
        ic.main(["--root", self.root])
        self.assertTrue(os.path.isdir(self.cad))

    def test_all_expected_files_created(self):
        ic.main(["--root", self.root])
        for fname in EXPECTED_FILES:
            path = os.path.join(self.cad, fname)
            self.assertTrue(os.path.isfile(path),
                            f"expected {fname} to be created")

    def test_context_md_has_arbiter_enabled(self):
        ic.main(["--root", self.root])
        with open(os.path.join(self.cad, "CONTEXT.md"), encoding="utf-8") as f:
            content = f.read()
        self.assertIn("arbiter: enabled", content)

    def test_context_md_no_initialized_sentinel(self):
        """Fresh scaffold must NOT write the <!--INITIALIZED--> sentinel."""
        ic.main(["--root", self.root])
        with open(os.path.join(self.cad, "CONTEXT.md"), encoding="utf-8") as f:
            content = f.read()
        # The word INITIALIZED must not appear — even in any form — per the
        # module-level comment in init-codearbiter.py.
        self.assertNotIn("INITIALIZED", content)

    def test_stage_default_is_1(self):
        ic.main(["--root", self.root])
        with open(os.path.join(self.cad, "CONTEXT.md"), encoding="utf-8") as f:
            content = f.read()
        self.assertIn("stage: 1", content)


class TestStageFlag(unittest.TestCase):
    """--stage N writes stage: N in CONTEXT.md."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.cad = os.path.join(self.root, ".codearbiter")

    def tearDown(self):
        self.tmp.cleanup()

    def test_stage_3_written(self):
        ic.main(["--root", self.root, "--stage", "3"])
        with open(os.path.join(self.cad, "CONTEXT.md"), encoding="utf-8") as f:
            content = f.read()
        self.assertIn("stage: 3", content)

    def test_stage_2_written(self):
        ic.main(["--root", self.root, "--stage", "2"])
        with open(os.path.join(self.cad, "CONTEXT.md"), encoding="utf-8") as f:
            content = f.read()
        self.assertIn("stage: 2", content)

    def test_stage_3_no_initialized_sentinel(self):
        ic.main(["--root", self.root, "--stage", "3"])
        with open(os.path.join(self.cad, "CONTEXT.md"), encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("INITIALIZED", content)


class TestIdempotencyGuard(unittest.TestCase):
    """Re-run without --check raises SystemExit (idempotency guard)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        # First scaffold
        ic.main(["--root", self.root])

    def tearDown(self):
        self.tmp.cleanup()

    def test_rerun_raises_system_exit(self):
        with self.assertRaises(SystemExit):
            ic.main(["--root", self.root])

    def test_rerun_exit_message_mentions_refusing(self):
        try:
            ic.main(["--root", self.root])
        except SystemExit as e:
            self.assertIn("REFUSING", str(e))

    def test_existing_files_unchanged_after_failed_rerun(self):
        cad = os.path.join(self.root, ".codearbiter")
        ctx_before = open(os.path.join(cad, "CONTEXT.md"), encoding="utf-8").read()
        try:
            ic.main(["--root", self.root])
        except SystemExit:
            pass
        ctx_after = open(os.path.join(cad, "CONTEXT.md"), encoding="utf-8").read()
        self.assertEqual(ctx_before, ctx_after)


class TestCheckMode(unittest.TestCase):
    """--check on scaffolded vs un-scaffolded dirs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _run_check(self, argv):
        """Run main with --check, capture stdout, return (stdout_str, exit_code)."""
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        exit_code = 0
        try:
            ic.main(argv)
        except SystemExit as e:
            exit_code = e.code if e.code is not None else 0
        finally:
            sys.stdout = old_stdout
        return captured.getvalue(), exit_code

    def test_check_on_scaffolded_exits_0(self):
        ic.main(["--root", self.root])
        _, code = self._run_check(["--root", self.root, "--check"])
        self.assertEqual(code, 0)

    def test_check_on_scaffolded_reports_already_scaffolded(self):
        ic.main(["--root", self.root])
        output, _ = self._run_check(["--root", self.root, "--check"])
        self.assertIn("ALREADY SCAFFOLDED", output)

    def test_check_on_scaffolded_reports_enabled(self):
        ic.main(["--root", self.root])
        output, _ = self._run_check(["--root", self.root, "--check"])
        self.assertIn("enabled", output)

    def test_check_on_scaffolded_reports_uninitialized(self):
        """Fresh scaffold has no INITIALIZED sentinel; --check should say so."""
        ic.main(["--root", self.root])
        output, _ = self._run_check(["--root", self.root, "--check"])
        self.assertIn("no", output.lower())

    def test_check_on_nonscaffolded_exits_0_and_reports_not_scaffolded(self):
        """--check on a dir that has never been scaffolded exits 0 and says NOT SCAFFOLDED."""
        output, code = self._run_check(["--root", self.root, "--check"])
        self.assertEqual(code, 0)
        self.assertIn("NOT SCAFFOLDED", output)

    def test_check_does_not_create_files(self):
        """--check must never create any files."""
        output, _ = self._run_check(["--root", self.root, "--check"])
        cad = os.path.join(self.root, ".codearbiter")
        self.assertFalse(os.path.exists(cad),
                         "--check must not create .codearbiter/")


if __name__ == "__main__":
    unittest.main()

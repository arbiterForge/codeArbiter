#!/usr/bin/env python3
"""Issue #442 AC-3 — the test suites must not write outside their own temp dirs.

Running the sanctioned hook suite mutated the developer's REAL home directory:
`~/.claude/settings.json` was rewritten (both `statusLine.command` and
`_codearbiterStatuslineOwner` repointed at whatever plugin root the test process
resolved), and `~/.codearbiter/` gained a ledger, its lock, five session shards,
and an update-state cache. Four modules on main did it, none of them using the
`redirect_home` helper that already sat beside them.

That is worse than untidy. It broke the maintainer's statusline three times in
one day; it makes the suite non-hermetic, so two developers running it get
different global config afterwards; and it is why a subagent tripped an
"irreversible local destruction" check trying to clean up the mess. CI never
noticed, because a fresh runner has no pre-existing settings to clobber.

HOW THIS GUARD WORKS, AND WHY NOT A REAL-HOME SNAPSHOT
------------------------------------------------------
The obvious guard — hash the developer's real `~` before and after — is
destructive by observation: it can only detect damage that has already been
done, on the machine you care about. Instead this runs each suite in a
subprocess whose home is a PRISTINE temp directory, seeded with a plausible
stale-but-real `~/.claude/settings.json`, and asserts that directory comes back
BYTE-IDENTICAL: nothing created, nothing modified, nothing deleted.

This detects persistent changes under the redirected home. It is not an OS
sandbox: hard-coded paths, write-then-restore activity, and other global
locations require separate controls.

The seeded `settings.json` matters: `heal_statusline_wiring` returns early when
no settings file exists, so an EMPTY fake home would hide exactly the write this
issue is about.

Every home variable `os.path.expanduser("~")` consults is redirected, not just
`HOME`: on Windows `ntpath` reads `USERPROFILE` first, then `HOMEDRIVE` +
`HOMEPATH`, and ignores `HOME` entirely — the precise reason the original
offenders escaped notice on the maintainer's machine.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# Every key expanduser("~") consults, on any platform.
HOME_KEYS = ("HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH")

# A stale-but-real owner pin, so the statusline self-heal has something to
# rewrite. Without this the write under test cannot happen at all.
SEEDED_SETTINGS = """{
  "statusLine": {
    "type": "command",
    "command": "\\"python\\" \\"/opt/acme/codearbiter/ca/1.0.0/hooks/statusline.py\\""
  },
  "_codearbiterStatuslineOwner": "codearbiter/ca/1.0.0/hooks/statusline.py"
}
"""

SUITES = (
    (
        "ca hook suite",
        [sys.executable, "-m", "unittest", "discover",
         "-s", "plugins/ca/hooks/tests", "-p", "test_*.py", "-t", "."],
    ),
    # AC-4: the same audit, applied to the .github/scripts tests. Listed
    # explicitly rather than discovered, so a new script test is a deliberate
    # addition here rather than a silent omission.
    (
        "hook-guard matrix",
        [sys.executable, ".github/scripts/test_hook_guards.py"],
    ),
    (
        "codex adapter parity",
        [sys.executable, ".github/scripts/test_codex_adapter.py"],
    ),
    (
        "dual-host store",
        [sys.executable, ".github/scripts/test_dual_host_store.py"],
    ),
)


def snapshot(root: Path) -> dict[str, str]:
    """Path -> content digest for every file under `root`, dirs included as
    markers so an empty directory left behind is still a difference."""
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            out[rel + "/"] = "<dir>"
        elif path.is_file():
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def seeded_home(root: Path) -> None:
    claude = root / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "settings.json").write_text(SEEDED_SETTINGS, encoding="utf-8", newline="\n")


def run_suite(command: list[str], home: Path) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    for key in HOME_KEYS:
        environment.pop(key, None)
    environment["HOME"] = str(home)
    environment["USERPROFILE"] = str(home)
    # Deliberately NOT setting CODEARBITER_LEDGER / CODEARBITER_UPDATE_STATE.
    # Those are the seams a well-behaved test uses to point its own state at its
    # own temp dir; pinning them here would force correct code to look incorrect
    # and, worse, would let an offender pass by writing to a path this guard
    # itself supplied. Unset, the production fallback applies -- expanduser("~"),
    # which is the fake home -- so any suite that neglects the seam is caught.
    for seam in ("CODEARBITER_LEDGER", "CODEARBITER_UPDATE_STATE"):
        environment.pop(seam, None)
    return subprocess.run(
        command, cwd=REPO, env=environment, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=900,
    )


HOOK_TESTS = REPO / "plugins/ca/hooks/tests"
STATUSLINE_MODULES = frozenset(("test_wire_statusline", "test_durabilitylib", "test_atomic_writes"))
STATUSLINE_RESULTS_FORMAT = "codearbiter.hermetic-statusline-results/1"
MAX_STATUSLINE_RESULTS_BYTES = 128 * 1024
RAN = re.compile(r"^Ran (\d+) tests? in ", re.M)
# Scheduling order only: the longest observed modules start first so the
# queue does not end on one of them. Discovery still owns membership.
SLOW_FIRST = (
    "test_contextmergelib", "test_crypto_context", "test_release_workflow_followup",
    "test_append_only_conflict", "test_tribunal_run", "test_tribunal_workflow",
    "test_pre_edit", "test_doctor",
)


def _text(value: str | bytes | None) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else (value or "")


def hook_modules() -> list[str]:
    return sorted(path.stem for path in HOOK_TESTS.glob("test_*.py"))


class _NamedStatuslineResult(unittest.TextTestResult):
    """Keep original test callbacks while observing only the outer runner."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rows = []
        self.current_id = None

    def startTest(self, test):
        self.current_id = id(test)
        self.rows.append({"id": test.id(), "result": None})
        super().startTest(test)

    def stopTest(self, test):
        self.current_id = None
        super().stopTest(test)

    def _record(self, test, outcome):
        if id(test) == self.current_id:
            self.rows[-1]["result"] = outcome

    def addSuccess(self, test):
        self._record(test, "passed")
        super().addSuccess(test)

    def addSkip(self, test, reason):
        self._record(getattr(test, "test_case", test), "skipped")
        super().addSkip(test, reason)

    def addExpectedFailure(self, test, error):
        self._record(test, "expected-failure")
        super().addExpectedFailure(test, error)

    def named_results(self):
        if any(row["result"] is None for row in self.rows):
            raise ValueError("statusline discovery yielded a case without an outcome")
        return self.rows


def _discovery_args(module, start, top):
    return ["discover", "-s", start, "-p", f"{module}.py", *(["-t", top] if top else [])]


def _write_named_results(path, document):
    raw = (json.dumps(document, ensure_ascii=True, separators=(",", ":")) + "\n").encode("ascii")
    if len(raw) > MAX_STATUSLINE_RESULTS_BYTES:
        raise ValueError("statusline named results exceed bound")
    with path.open("xb") as stream:
        stream.write(raw)


def _capture_statusline_child(module, start, top, output):
    if module not in STATUSLINE_MODULES or output.exists() or output.is_symlink():
        raise ValueError("statusline child requires an allowed module and a new output")
    # Match the original `python -m unittest discover` process search path and
    # use its own loader/runner settings. A result subclass records the exact
    # existing discovery, without observing nested fixture runners.
    sys.path[0] = str(Path.cwd())
    sys.argv[:] = [f"{Path(sys.executable).name} -m unittest", *_discovery_args(module, start, top)]
    class ObservingRunner(unittest.TextTestRunner):
        resultclass = _NamedStatuslineResult

        def run(self, suite):
            result = super().run(suite)
            if result.wasSuccessful() and result.testsRun:
                try:
                    _write_named_results(output, result.named_results())
                except (OSError, ValueError) as error:
                    # The parent separately requires a complete capture.
                    print(f"statusline child capture failed: {error}", file=sys.stderr)
            return result

    unittest.main(module=None, testRunner=ObservingRunner)


def _read_statusline_child(output, module, start, top, result):
    if not output.is_file() or output.is_symlink():
        raise ValueError("missing owned statusline child results")
    with output.open("rb") as stream:
        raw = stream.read(MAX_STATUSLINE_RESULTS_BYTES + 1)
    if len(raw) > MAX_STATUSLINE_RESULTS_BYTES:
        raise ValueError("statusline child results exceed bound")
    rows = json.loads(raw)
    count = RAN.search(result.stderr)
    if not isinstance(rows, list) or not count or len(rows) != int(count[1]) or not rows:
        raise ValueError("statusline child results differ from the original test population")
    filename = Path(start, f"{module}.py").resolve()
    stem = ".".join(filename.relative_to(Path(top).resolve()).with_suffix("").parts) if top else module
    names = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"id", "result"}:
            raise ValueError("invalid named statusline result")
        name = row["id"]
        if (not isinstance(name, str) or not name.startswith(stem + ".")
                or len(name) > 512 or name in names
                or row["result"] not in ("passed", "skipped", "expected-failure")):
            raise ValueError("invalid or repeated name in statusline child results")
        names.add(name)
    return rows


def run_hook_modules(modules: list[str], workers: int | None = None,
                     start: str = "plugins/ca/hooks/tests", top: str | None = None,
                     *, statusline_results: dict[str, list[dict[str, str]]] | None = None) -> dict[str, tuple]:
    """Run each module in a separate child and pristine home; return results and snapshots.

    The start directory is the import root, exactly as in a plain `discover -s`
    run, so each module imports its sibling helpers without relying on an
    earlier module having extended sys.path. Optional named results come from
    the same original invocation and live outside the redirected home."""
    def run(command, home):
        try:
            return run_suite(command, home)
        except subprocess.TimeoutExpired as expired:
            # A wedged module is that module's failure, reported with its output.
            return subprocess.CompletedProcess(
                command, -1, _text(expired.stdout), _text(expired.stderr) + "\nchild timed out")

    def one(module):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            seeded_home(home)
            before = snapshot(home)
            command = [sys.executable, "-W", "always::ResourceWarning"]
            rows = None
            if statusline_results is not None and module in STATUSLINE_MODULES:
                with tempfile.TemporaryDirectory() as capture_dir:
                    output = Path(capture_dir) / "named-results.json"
                    result = run([*command, str(Path(__file__).resolve()), "--statusline-child",
                                  module, start, top or "", str(output)], home)
                    if result.returncode == 0:
                        try:
                            rows = _read_statusline_child(output, module, start, top, result)
                        except (OSError, ValueError) as error:
                            # Retain the original return code and snapshots.
                            result.stderr += f"\nstatusline child capture refused: {error}"
            else:
                result = run([*command, "-m", "unittest", *_discovery_args(module, start, top)], home)
            return module, (result, before, snapshot(home)), rows
    order = sorted(modules, key=lambda m: (SLOW_FIRST.index(m) if m in SLOW_FIRST else len(SLOW_FIRST), m))
    # Hosted runners have three or four cores; more children only contend.
    default = min(4, max(2, os.cpu_count() or 2))
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers or default) as pool:
        for module, outcome, named in pool.map(one, order):
            results[module] = outcome
            if named is not None:
                statusline_results[module] = named
    return results


class TestSuitesStayInsideTheirTempDirs(unittest.TestCase):
    maxDiff = None

    def assert_home_untouched(self, name: str, command: list[str]) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            seeded_home(home)
            before = snapshot(home)
            result = run_suite(command, home)
            after = snapshot(home)
        self.assert_result_hermetic(name, result, before, after)

    def assert_result_hermetic(self, name, result, before, after) -> None:
        self.assertEqual(
            result.returncode, 0,
            f"{name} did not pass under a redirected home:\n{result.stdout[-4000:]}\n{result.stderr[-4000:]}",
        )
        created = sorted(set(after) - set(before))
        removed = sorted(set(before) - set(after))
        modified = sorted(key for key in set(before) & set(after) if before[key] != after[key])
        self.assertEqual(
            (created, removed, modified), ([], [], []),
            f"{name} wrote outside its temp dirs. On a developer machine these are "
            f"paths under the REAL home.\n"
            f"  created:  {created}\n  removed:  {removed}\n  modified: {modified}",
        )

    def test_github_script_suites_leave_the_user_home_byte_identical(self):
        # This is these suites' only CI execution. Each has its own pristine
        # home, so they run side by side; each is still judged on its own.
        def one(suite):
            name, command = suite
            with tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                seeded_home(home)
                before = snapshot(home)
                result = run_suite(command, home)
                return name, result, before, snapshot(home)

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(SUITES) - 1) as pool:
            outcomes = list(pool.map(one, SUITES[1:]))
        for name, result, before, after in outcomes:
            with self.subTest(suite=name):
                self.assert_result_hermetic(name, result, before, after)
                # unittest reports "Ran N tests"; the guard matrix reports
                # "N assertions, 0 failed". Either way, zero is not a pass.
                output = result.stdout + result.stderr
                ran = RAN.findall(output) or re.findall(r"^(\d+) assertions, 0 failed$", output, re.M)
                self.assertTrue(ran and int(ran[-1]) > 0, f"{name} ran no tests")

    def test_color_suites_isolate_and_restore_ambient_no_color(self):
        # Color assertions must establish their own rendering environment;
        # intentional NO_COLOR behavior is still tested inside these modules.
        for value in ("", "1"):
            with self.subTest(no_color=value):
                script = (
                    "import os,sys,unittest;"
                    f"os.environ['NO_COLOR']={value!r};"
                    "sys.path.insert(0,'plugins/ca/hooks/tests');"
                    "suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromName(name) "
                    "for name in ('test_colorlib','test_statusline')]);"
                    "result=unittest.TextTestRunner().run(suite);"
                    f"assert os.environ.get('NO_COLOR')=={value!r}, 'ambient NO_COLOR was not restored';"
                    "sys.exit(not result.wasSuccessful())")
                self.assert_home_untouched("color environment isolation", [sys.executable, "-c", script])


class TestTheSuiteLeaksNoHandlesOrProcesses(unittest.TestCase):
    """Issue #462 — the intermittent-red half.

    The same tree, unchanged, produced `FAILED (errors=2)` on one run and `OK`
    on the next three. The signal was in the warnings: unclosed `settings.json`
    and `CONTEXT.md` handles, five leaked subprocesses, and an implicitly
    reclaimed `HTTPError`. On Windows an unclosed handle blocks
    `TemporaryDirectory` cleanup and a live child holds a temp path, so teardown
    RAISES instead of the assertion failing — intermittent ERRORS, not failures,
    with no code change between runs.

    That erodes the signal the suite exists to provide. This sweep already
    showed the failure mode: a genuinely red Windows cell was hit five times and
    each time the correct-but-corrosive response was "re-run it." A suite that
    is red once in four trains everyone to re-run first and diagnose never,
    which is precisely how a real regression gets waved through. It also makes
    bisecting unreliable, since a clean step cannot be trusted on one run.

    So the warnings are the assertion. `Enable tracemalloc` lines are dropped:
    they are the interpreter's advice about a warning, not a warning."""

    ADVICE = "Enable tracemalloc"
    statusline_results = None

    @classmethod
    def setUpClass(cls):
        # This is the CI's only execution of the complete ca hook suite. Each
        # discovered module runs in its own child with its own pristine home,
        # several at once, so an unclean module is named and the runner's cores
        # are used. Class fixtures are recreated on each run; no result cache.
        cls.results = run_hook_modules(hook_modules(), statusline_results=cls.statusline_results)

    def test_every_hook_module_ran_and_passed(self):
        self.assertEqual(sorted(self.results), hook_modules())
        for module, (result, _before, _after) in sorted(self.results.items()):
            with self.subTest(module=module):
                self.assertEqual(result.returncode, 0, f"{module} failed:\n{result.stdout}\n{result.stderr}")
                ran = RAN.search(result.stderr)
                self.assertTrue(ran and int(ran[1]) > 0, f"{module} ran no tests:\n{result.stderr[-4000:]}")

    def test_ca_hook_suite_leaves_the_user_home_byte_identical(self):
        for module, (_result, before, after) in sorted(self.results.items()):
            created = sorted(set(after) - set(before))
            removed = sorted(set(before) - set(after))
            modified = sorted(
                key for key in set(before) & set(after) if before[key] != after[key]
            )
            with self.subTest(module=module):
                self.assertEqual(
                    (created, removed, modified),
                    ([], [], []),
                    f"{module} mutated redirected HOME: "
                    f"created={created}, removed={removed}, modified={modified}",
                )

    def test_the_ca_hook_suite_emits_no_resource_warnings(self):
        for module, (result, _before, _after) in sorted(self.results.items()):
            warnings = [
                line.strip()
                for line in (result.stdout + result.stderr).splitlines()
                if "ResourceWarning" in line and self.ADVICE not in line
            ]
            with self.subTest(module=module):
                self.assertEqual(
                    warnings, [],
                    f"{module} leaked a handle or a process. On Windows these turn a "
                    "later teardown into an intermittent ERROR:\n  " + "\n  ".join(warnings),
                )


class TestTheGuardItselfCanFail(unittest.TestCase):
    """A hermeticity guard that cannot fail is decoration. This proves the
    detector sees a write, so a green result above means something."""

    def test_a_suite_that_writes_to_home_is_caught(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            seeded_home(home)
            before = snapshot(home)
            result = run_suite(
                [sys.executable, "-c",
                 "import os,pathlib;"
                 "p=pathlib.Path(os.path.expanduser('~'))/'.codearbiter';"
                 "p.mkdir(parents=True,exist_ok=True);"
                 "(p/'ledger.json').write_text('{}')"],
                home,
            )
            after = snapshot(home)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(before, after, "the detector did not notice a write to ~")
        self.assertIn(".codearbiter/ledger.json", set(after) - set(before))

    def test_the_parallel_module_run_attributes_each_defect_to_its_module(self):
        modules = {
            "test_clean": "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self): pass\n",
            "test_fails": "import unittest\nclass T(unittest.TestCase):\n    def test_no(self): self.fail('red')\n",
            "test_writes_home": ("import os, pathlib, unittest\nclass T(unittest.TestCase):\n"
                                 "    def test_w(self): (pathlib.Path(os.path.expanduser('~')) / 'stray').write_text('x')\n"),
            "test_empty": "import unittest\n",
            "test_atomic_writes": (
                "import io, unittest\n"
                "class T(unittest.TestCase):\n"
                "    @unittest.expectedFailure\n"
                "    def test_expected(self): self.fail('expected')\n"
                "    def test_outer(self):\n"
                "        class Nested(unittest.TestCase):\n"
                "            def test_inner(self): pass\n"
                "        suite = unittest.defaultTestLoader.loadTestsFromTestCase(Nested)\n"
                "        self.assertTrue(unittest.TextTestRunner(stream=io.StringIO()).run(suite).wasSuccessful())\n"
                "    def test_skips(self):\n"
                "        with self.subTest(): self.skipTest('fixture subtest')\n"
            ),
            "test_durabilitylib": "import unittest\nclass T(unittest.TestCase):\n"
                                  "    def test_fails(self): self.fail('original failure')\n",
            "test_leaks": ("import unittest\nclass T(unittest.TestCase):\n"
                           "    def test_l(self): open(__file__)\n"),
        }
        with tempfile.TemporaryDirectory() as top:
            package = Path(top) / "suite"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            for name, body in modules.items():
                (package / f"{name}.py").write_text(body, encoding="utf-8")
            captured = {}
            results = run_hook_modules(sorted(modules), workers=3, start=str(package), top=top,
                                       statusline_results=captured)
        self.assertEqual(sorted(results), sorted(modules))
        code = {name: result.returncode for name, (result, _, _) in results.items()}
        self.assertEqual(code["test_clean"], 0)
        self.assertIn("-m", results["test_clean"][0].args)
        self.assertIn("--statusline-child", results["test_atomic_writes"][0].args)
        self.assertEqual(code["test_atomic_writes"], 0)
        self.assertEqual(code["test_durabilitylib"], 1)
        self.assertEqual(results["test_atomic_writes"][1], results["test_atomic_writes"][2])
        self.assertEqual(captured, {"test_atomic_writes": [
            {"id": "suite.test_atomic_writes.T.test_expected", "result": "expected-failure"},
            {"id": "suite.test_atomic_writes.T.test_outer", "result": "passed"},
            {"id": "suite.test_atomic_writes.T.test_skips", "result": "skipped"},
        ]})
        self.assertNotEqual(code["test_fails"], 0)
        ran = {name: RAN.search(result.stderr) for name, (result, _, _) in results.items()}
        self.assertEqual(ran["test_empty"][1], "0")
        _, before, after = results["test_writes_home"]
        self.assertEqual(sorted(set(after) - set(before)), ["stray"])
        self.assertEqual(results["test_clean"][1], results["test_clean"][2])
        self.assertIn("ResourceWarning", results["test_leaks"][0].stderr)
        self.assertNotIn("ResourceWarning", results["test_clean"][0].stderr)

    def test_a_suite_that_modifies_the_seeded_settings_is_caught(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            seeded_home(home)
            before = snapshot(home)
            result = run_suite(
                [sys.executable, "-c",
                 "import os,pathlib;"
                 "p=pathlib.Path(os.path.expanduser('~'))/'.claude'/'settings.json';"
                 "p.write_text('{}')"],
                home,
            )
            after = snapshot(home)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(
            before[".claude/settings.json"], after[".claude/settings.json"],
            "the detector did not notice settings.json being rewritten",
        )


def main():
    args = sys.argv[1:]
    if args[:1] == ["--statusline-child"]:
        if len(args) != 5:
            raise ValueError("invalid statusline child invocation")
        _, module, start, top, output = args
        return _capture_statusline_child(module, start, top or None, Path(output))
    if args[:1] == ["--statusline-results"]:
        if len(args) != 2:
            raise ValueError("statusline results require the complete hermeticity suite")
        output = Path(args[1]).absolute()
        if output.exists() or output.is_symlink():
            raise ValueError("statusline capture requires a new output")
        records = {}
        owner = TestTheSuiteLeaksNoHandlesOrProcesses
        previous = owner.statusline_results
        owner.statusline_results = records
        try:
            program = unittest.main(argv=sys.argv[:1], verbosity=2, exit=False)
        finally:
            owner.statusline_results = previous
        if not program.result.wasSuccessful():
            return 1
        missing = STATUSLINE_MODULES - records.keys()
        if missing:
            raise ValueError("statusline capture missing original modules: " + ", ".join(sorted(missing)))
        _write_named_results(output, {"format": STATUSLINE_RESULTS_FORMAT, "modules": records})
        return 0
    unittest.main(verbosity=2)


if __name__ == "__main__":
    raise SystemExit(main())

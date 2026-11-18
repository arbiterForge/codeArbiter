#!/usr/bin/env python3
# codeArbiter — execute the release skill's guards and post-adoption window.
"""Regression coverage for the follow-up to PR #845 (RR-01, RR-02, RR-03).

Execute shell definitions extracted from the installed skill, not Python
transcriptions of their decisions. All Git writes are confined to temporary
consumer repositories and a temporary local bare remote. No host approval,
commit-gate review, hosted publisher, or live publication is simulated as proof.
"""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock
from types import SimpleNamespace

PLUGIN = Path(__file__).resolve().parents[2]
SKILL = PLUGIN / "skills" / "release" / "SKILL.md"
HOOKS = PLUGIN / "hooks"
GIT = shutil.which("git")


def same_runtime_bash():
    if os.name != "nt":
        return shutil.which("bash")
    spec = importlib.util.spec_from_file_location(
        "release_followup_shell_resolver", HOOKS / "_releaselib.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._resolve_posix_shell()


BASH = same_runtime_bash()


def shell_definition(text, name):
    """Read a uniquely named, complete fenced shell definition from the skill."""
    blocks = re.findall(r"^[ \t]*```sh\n(.*?)^[ \t]*```", text, re.M | re.S)
    matches = [textwrap.dedent(block) for block in blocks
               if re.search(r"^\s*" + re.escape(name) + r"\(\)\s*\(", block, re.M)]
    if len(matches) != 1:
        raise AssertionError(f"expected one fenced definition for {name}, got {len(matches)}")
    definition = re.search(r"^" + re.escape(name) + r"\(\)\s*\(\n.*?^\)\n",
                           matches[0], re.M | re.S)
    if definition is None:
        raise AssertionError(f"incomplete shell definition for {name}")
    return definition[0]


def isolated_env():
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("GIT_") and k not in
           ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT", "PLUGIN_ROOT", "PYTHONPATH",
            "PYTHONHOME", "BASH_ENV", "ENV", "CDPATH")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT="0", PY=sys.executable)
    return env


_PHASES = (b"bash-entered", b"definition-ready", b"invocation-entered", b"invocation-returned")
_PHASE_BYTES = 128


def _phase_regular(info):
    return stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and not (
        getattr(info, "st_file_attributes", 0) & 0x400)


def _phase_version(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _last_fixture_phase(path, identity):
    if path is None:
        return "unavailable"
    try:
        before = path.lstat()
        if not _phase_regular(before) or (before.st_dev, before.st_ino) != identity:
            return "unavailable"
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not _phase_regular(opened) or _phase_version(opened) != _phase_version(before):
                return "unavailable"
            raw = stream.read(_PHASE_BYTES + 1)
            after = os.fstat(stream.fileno())
        final = path.lstat()
        if (len(raw) > _PHASE_BYTES or not _phase_regular(final) or
                _phase_version(after) != _phase_version(before) or
                _phase_version(final) != _phase_version(before)):
            return "unavailable"
        if not raw:
            return "entry-not-observed"
        rows = raw[:-1].split(b"\n")
        if not raw.endswith(b"\n") or tuple(rows) != _PHASES[:len(rows)] or len(rows) > len(_PHASES):
            return "unavailable"
        return rows[-1].decode("ascii")
    except OSError:
        return "unavailable"


class Consumer:
    """A real history, declaration PR, published ledger, and fresh release branch."""

    def __init__(self, base, method="merge", missing_footer=False, ledger="valid",
                 plugin_root=PLUGIN):
        self.base = Path(base)
        self.plugin_root = Path(plugin_root)
        self.hooks = self.plugin_root / "hooks"
        self.root = self.base / "consumer with spaces"
        self.remote = self.base / "origin.git"
        self.env = isolated_env()
        self.root.mkdir(parents=True)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Release regression fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.write("package.json", '{"name":"sample","version":"0.1.0"}\n')
        self.write("CHANGELOG.md", "# Changelog\n\n## [Unreleased]\n")
        self.write("app.py", "value = 1\n")
        subject = "feat: initial application"
        if not missing_footer:
            subject += "\n\nCHANGELOG: Add the initial application."
        self.commit(subject)
        self.application = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("init", "--bare", "-q", str(self.remote))
        self.git("remote", "add", "origin", str(self.remote))
        self.git("push", "-q", "origin", "main")
        self.git("checkout", "-qb", "declare-release")
        self.write(".codearbiter/tech-stack.md", "# Fixture commands\n\ntest: true\n")
        helper = subprocess.run(
            [sys.executable, str(self.hooks / "_releaselib.py"), "backfill-detect"],
            cwd=self.root, env={**self.env, "CLAUDE_PROJECT_DIR": str(self.root)},
            text=True, capture_output=True, timeout=15)
        if helper.returncode:
            raise AssertionError(helper.stderr)
        self.write(".codearbiter/release-targets.md", helper.stdout)
        entries = []
        if missing_footer and ledger == "valid":
            entries = [{"target": "app", "commit_sha": self.application,
                        "changelog": "Add the initial application.",
                        "reason": "Published before adopting changelog footers.",
                        "authorization": "Explicit fixture operator input; not production authority."}]
        draft = self.base / "ledger-draft.json"
        draft.write_text(json.dumps({"schema_version": 1, "entries": entries}) + "\n",
                         encoding="utf-8")
        checked = subprocess.run(
            [sys.executable, str(self.hooks / "_releaselib.py"), "validate-reconciliations", "app", str(draft)],
            cwd=self.root, env=self.env, text=True, capture_output=True, timeout=15)
        if checked.returncode:
            raise AssertionError(checked.stderr)
        self.write(".codearbiter/release-changelog-reconciliations.json",
                   draft.read_text(encoding="utf-8"))
        self.commit("chore: declare release targets and changelog reconciliation")
        self.declaration = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("checkout", "-q", "main")
        if method == "merge":
            self.git("merge", "-q", "--no-ff", "declare-release", "-m", "Merge declaration PR")
        elif method == "squash":
            self.git("merge", "--squash", "declare-release")
            self.commit("chore: squash declaration PR")
        elif method == "ff":
            self.git("merge", "-q", "--ff-only", "declare-release")
        else:
            raise ValueError(method)
        self.git("push", "-q", "origin", "main")
        self.git("fetch", "-q", "origin", "main")
        self.git("checkout", "-qb", "release-first", "origin/main")
        self.head = self.git("rev-parse", "HEAD").stdout.strip()
        self.env.update(CLAUDE_PROJECT_DIR=str(self.root),
                        CLAUDE_PLUGIN_ROOT=str(self.plugin_root), PROJECT_ROOT=str(self.root),
                        TARGET="app", DEFAULT_BRANCH="main", LAST_TAG="<none>")
        log = self.git("log", "--diff-filter=A", "--format=%H", "--",
                       ".codearbiter/CONTEXT.md", ".codearbiter/release-targets.md").stdout
        result = self.helper("adoption-commit", input=log)
        if result.returncode:
            raise AssertionError(result.stderr)
        self.adopted = result.stdout.strip()
        self.env.update(ADOPTED=self.adopted, EFFECTIVE_WINDOW=self.adopted + "^..HEAD")
        paths = self.helper("payload-pathspec", "app")
        if paths.returncode:
            raise AssertionError(paths.stderr)
        self.pathspecs = paths.stdout.splitlines()
        if method in ("squash", "merge") and self.head == self.declaration:
            raise AssertionError("fixture did not allocate the required distinct merge identity")

    def git(self, *args, check=True):
        result = subprocess.run([GIT, *args], cwd=self.root, env=self.env,
                                text=True, capture_output=True, timeout=15)
        if check and result.returncode:
            raise AssertionError(f"git {args!r}: {result.stderr}")
        return result

    def helper(self, *args, input=None):
        return subprocess.run([sys.executable, str(self.hooks / "_releaselib.py"), *args],
                              cwd=self.root, env=self.env, input=input,
                              text=True, capture_output=True, timeout=15)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def commit(self, message):
        self.git("add", "--all")
        self.git("commit", "-qm", message)

    def fingerprint(self):
        files = tuple(sorted((str(p.relative_to(self.root)), hashlib.sha256(p.read_bytes()).hexdigest())
                             for p in self.root.rglob("*")
                             if p.is_file() and ".git" not in p.relative_to(self.root).parts))
        return files, self.git("status", "--porcelain").stdout, self.git("for-each-ref").stdout


@unittest.skipUnless(BASH and GIT, "requires same-runtime bash and git")
class ReleaseWorkflowFollowupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ca-release-followup-")
        self.addCleanup(self.tmp.cleanup)
        self.text = SKILL.read_text(encoding="utf-8")

    def consumer(self, **kwargs):
        return Consumer(self.tmp.name, **kwargs)

    def run_definition(self, consumer, name, *, env=None, args=(), trailer=None):
        body = shell_definition(self.text, name)
        # This is the installed Claude rendering. No canonical source lookup
        # or Python reimplementation of the shell decision is involved.
        script = "set -eu\n" + body + "\n" + (trailer or name + ' "$@"\n')
        phase = None
        identity = None
        diagnostic_ready = False
        try:
            fd, filename = tempfile.mkstemp(prefix="release-fixture-phase-", dir=self.tmp.name)
            phase = Path(filename)
            try:
                info = os.fstat(fd)
                identity = info.st_dev, info.st_ino
            finally:
                os.close(fd)
            quoted = shlex.quote(os.path.relpath(phase, consumer.root).replace(os.sep, "/"))
            def announce(value):
                return "printf '%s\\n' " + value + " 2>/dev/null >> " + quoted + " || :\n"
            script = ("set -eu\n" + announce("bash-entered") + body + "\n" +
                      announce("definition-ready") + announce("invocation-entered") +
                      (trailer or name + ' "$@"\n') + "_release_fixture_status=$?\n" +
                      announce("invocation-returned") + 'exit "$_release_fixture_status"\n')
            diagnostic_ready = True
        except (OSError, ValueError):
            # Diagnostics are best-effort and never replace the original invocation.
            pass
        try:
            return subprocess.run([BASH, "--noprofile", "--norc", "-c", script, "release-test", *args],
                                  cwd=consumer.root, env={**consumer.env, **(env or {})},
                                  text=True, capture_output=True, timeout=20)
        except subprocess.TimeoutExpired as failure:
            failure.add_note("release fixture last observed phase: " +
                             (_last_fixture_phase(phase, identity) if diagnostic_ready else "unavailable") +
                             "; announcement only, not effect or exit completion")
            raise
        finally:
            if phase is not None:
                try:
                    current = phase.lstat()
                    if _phase_regular(current) and (current.st_dev, current.st_ino) == identity:
                        phase.unlink()
                except OSError:
                    pass

    def test_first_release_reentry_for_every_merge_method(self):
        for method in ("ff", "squash", "merge"):
            with self.subTest(method=method), tempfile.TemporaryDirectory() as tmp:
                c = Consumer(tmp, method=method, missing_footer=True)
                self.assertEqual(c.git("tag", "-l").stdout, "")
                self.assertEqual(c.git("log", c.env["EFFECTIVE_WINDOW"], "--format=%H", "--",
                                       *c.pathspecs).stdout, "")
                before = c.fingerprint()
                offer = self.run_definition(c, "release_window_state", args=c.pathspecs)
                self.assertEqual(offer.returncode, 0, offer.stderr)
                self.assertEqual(offer.stdout.strip(), "confirm-first-release-window")
                self.assertEqual(before, c.fingerprint(), "asking must not write or move refs")
                self.assertEqual(c.env["EFFECTIVE_WINDOW"], c.adopted + "^..HEAD")
                # The fixture now supplies an explicit operator choice. The
                # production helper only proposes; it cannot supply consent.
                selected = {"EFFECTIVE_WINDOW": "HEAD"}
                ready = self.run_definition(c, "release_window_state", env=selected, args=c.pathspecs)
                self.assertEqual(ready.returncode, 0, ready.stderr)
                self.assertEqual(ready.stdout.strip(), "ready")
                log = c.git("log", "HEAD", "--format=%H%x00%s%x00%b%x00", "--",
                            *c.pathspecs).stdout
                classified = c.helper("classify-window", "app", "main", input=log)
                self.assertEqual(classified.returncode, 0, classified.stderr)
                self.assertIn("[RECONCILED]", classified.stdout)
                self.assertIn("Add the initial application.", classified.stdout)
                self.assertEqual(before, c.fingerprint())

    def test_missing_published_reconciliation_still_blocks_after_confirmation(self):
        c = self.consumer(missing_footer=True, ledger="empty")
        ready = self.run_definition(c, "release_window_state", env={"EFFECTIVE_WINDOW": "HEAD"},
                                    args=c.pathspecs)
        self.assertEqual(ready.stdout.strip(), "ready")
        log = c.git("log", "HEAD", "--format=%H%x00%s%x00%b%x00", "--", *c.pathspecs).stdout
        before = c.fingerprint()
        verdict = c.helper("classify-window", "app", "main", input=log)
        self.assertEqual(verdict.returncode, 1, verdict.stderr)
        self.assertIn("[NEEDS-TRIAGE]", verdict.stdout)
        self.assertEqual(before, c.fingerprint())

    def test_nonempty_adoption_window_is_not_widened(self):
        c = self.consumer()
        c.write("app.py", "value = 2\n")
        c.commit("fix: change value\n\nCHANGELOG: Change the value.")
        result = self.run_definition(c, "release_window_state", args=c.pathspecs)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "ready")

    def test_tagged_empty_window_does_not_offer_first_release_widening(self):
        c = self.consumer()
        c.git("tag", "v0.1.0")
        result = self.run_definition(c, "release_window_state", args=c.pathspecs,
                                     env={"LAST_TAG": "v0.1.0", "EFFECTIVE_WINDOW": "v0.1.0..HEAD"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "empty")

    def test_unresolvable_adoption_and_window_are_failures_not_empty_history(self):
        c = self.consumer()
        for change in ({"ADOPTED": "missing-commit"}, {"EFFECTIVE_WINDOW": "missing-range..HEAD"}):
            with self.subTest(change=change):
                before = c.fingerprint()
                result = self.run_definition(c, "release_window_state", env=change, args=c.pathspecs)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("confirm-first-release-window", result.stdout)
                self.assertEqual(before, c.fingerprint())

    def test_empty_full_history_is_terminal_not_another_confirmation_loop(self):
        c = self.consumer()
        result = self.run_definition(c, "release_window_state", env={"EFFECTIVE_WINDOW": "HEAD"},
                                     args=("does-not-exist/",))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "empty")

    def test_actual_missing_prerequisite_refuses_before_a_write_attempt(self):
        c = self.consumer()
        (c.root / ".codearbiter/tech-stack.md").unlink()
        before = c.fingerprint()
        result = self.run_definition(c, "release_require_commit_path", trailer=
                                    'release_require_commit_path || exit "$?"\n'
                                    'printf mutation > must-not-exist\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tech-stack.md", result.stderr)
        self.assertFalse((c.root / "must-not-exist").exists())
        self.assertEqual(before, c.fingerprint())

    def test_actual_default_and_detached_branches_refuse_before_a_write_attempt(self):
        c = self.consumer()
        for branch in ("main", "--detach"):
            with self.subTest(branch=branch):
                c.git("checkout", "-q", branch)
                before = c.fingerprint()
                result = self.run_definition(c, "release_require_commit_path", trailer=
                                            'release_require_commit_path || exit "$?"\n'
                                            'printf mutation > must-not-exist\n')
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((c.root / "must-not-exist").exists())
                self.assertEqual(before, c.fingerprint())

    def test_prepared_nondefault_branch_passes_actual_guard(self):
        c = self.consumer()
        before = c.fingerprint()
        result = self.run_definition(c, "release_require_commit_path")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, c.fingerprint())

    def test_real_clean_and_dirty_probes_do_not_share_a_success_verdict(self):
        c = self.consumer()
        clean = self.run_definition(c, "release_require_clean_tree")
        self.assertEqual(clean.returncode, 0, clean.stderr)
        c.write("app.py", "value = 99\n")
        before = c.fingerprint()
        dirty = self.run_definition(c, "release_require_clean_tree", trailer=
                                     'release_require_clean_tree || exit "$?"\n'
                                     'printf mutation > must-not-exist\n')
        self.assertNotEqual(dirty.returncode, 0)
        self.assertIn("app.py", dirty.stderr)
        self.assertEqual(before, c.fingerprint())

    def test_valid_but_nonancestor_adoption_is_refused(self):
        c = self.consumer()
        c.git("checkout", "-qb", "unmerged-adoption")
        c.write("other.py", "value = 3\n")
        c.commit("chore: unrelated branch")
        unrelated = c.git("rev-parse", "HEAD").stdout.strip()
        c.git("checkout", "-q", "release-first")
        before = c.fingerprint()
        result = self.run_definition(c, "release_window_state",
                                     env={"ADOPTED": unrelated}, args=c.pathspecs)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, c.fingerprint())

    def test_no_payload_arguments_is_not_a_whole_repository_fallback(self):
        c = self.consumer()
        result = self.run_definition(c, "release_window_state")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pathspecs", result.stderr)

    def test_clean_guard_reaches_the_controlled_write_only_on_success(self):
        c = self.consumer()
        result = self.run_definition(c, "release_require_clean_tree", trailer=
                                    'release_require_clean_tree || exit "$?"\n'
                                    'printf allowed > success-control\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((c.root / "success-control").read_text(), "allowed")

    def test_calls_are_wired_before_each_write_boundary(self):
        backfill = self.text.split("## Back-fill", 1)[1].split("## Pre-flight", 1)[0]
        self.assertLess(backfill.index('release_require_commit_path || exit "$?"'),
                        backfill.index('touch "$(git rev-parse'))
        preflight = self.text.split("## Pre-flight", 1)[1].split("## Phase 1", 1)[0]
        self.assertIn('release_require_commit_path || exit "$?"', preflight)
        phase1 = self.text.split("## Phase 1", 1)[1].split("## Dry run", 1)[0]
        phase3 = self.text.split("## Phase 3", 1)[1]
        self.assertIn('release_require_clean_tree || exit "$?"', phase1)
        self.assertGreaterEqual(phase3.count('release_require_clean_tree || exit "$?"'), 4)
        self.assertIn('WINDOW_STATE=$(release_window_state "$@") || exit "$?"', phase1)
        self.assertIn("Only after that choice is actually supplied", phase1)
        self.assertIn("Tagged-release windows never take", phase1)

    def test_empty_stdout_failed_and_timed_out_probes_stop_before_side_effect(self):
        c = self.consumer()
        for mode in ("failure", "timeout"):
            with self.subTest(mode=mode):
                driver = Path(self.tmp.name) / (mode + " plugin") / "hooks" / "_releaselib.py"
                driver.parent.mkdir(parents=True)
                # Execute the REAL mechanism's CLI and timeout handler; only
                # its subprocess boundary is fault-injected. Keep real Git
                # discovery and target parsing outside that injection.
                driver.write_text(textwrap.dedent(f'''\
                    import importlib.util, subprocess, sys
                    from unittest import mock
                    spec = importlib.util.spec_from_file_location("tested_release", {str(HOOKS / '_releaselib.py')!r})
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    module.git_executable()
                    if {mode!r} == "timeout":
                        fault = subprocess.TimeoutExpired(["git", "status"], 30)
                        with mock.patch.object(module.subprocess, "run", side_effect=fault):
                            result = module.main(sys.argv[1:])
                    else:
                        failed = subprocess.CompletedProcess(["git", "status"], 128, "", "injected probe failure")
                        with mock.patch.object(module.subprocess, "run", return_value=failed):
                            result = module.main(sys.argv[1:])
                    raise SystemExit(result)
                    '''), encoding="utf-8")
                before = c.fingerprint()
                result = self.run_definition(c, "release_require_clean_tree",
                                             env={"CLAUDE_PLUGIN_ROOT": str(driver.parents[1])},
                                             trailer='release_require_clean_tree || exit "$?"\n'
                                                     'printf mutation > must-not-exist\n')
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn("timed out" if mode == "timeout" else "injected probe failure", result.stderr)
                self.assertEqual(before, c.fingerprint())


class ReleaseFixtureDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ca-release-phase-control-")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name) / "consumer"
        root.mkdir()
        self.consumer = SimpleNamespace(root=root, env={"FIXTURE": "inert"})
        self.driver = ReleaseWorkflowFollowupTest("test_prepared_nondefault_branch_passes_actual_guard")
        self.driver.tmp = self.tmp
        self.driver.text = SKILL.read_text(encoding="utf-8")

    def test_timeout_retains_last_closed_phase_and_the_original_exception(self):
        captured = {}
        def timeout(argv, **kwargs):
            captured.update(argv=argv, kwargs=kwargs)
            for phase in Path(self.tmp.name).glob("release-fixture-phase-*"):
                phase.write_bytes(b"bash-entered\ndefinition-ready\ninvocation-entered\n")
            failure = subprocess.TimeoutExpired(argv, 20, output=b"original output", stderr=b"original error")
            captured["failure"] = failure
            raise failure
        with mock.patch.object(subprocess, "run", side_effect=timeout):
            with self.assertRaises(subprocess.TimeoutExpired) as raised:
                self.driver.run_definition(self.consumer, "release_require_commit_path", args=("one value",))
        self.assertIs(raised.exception, captured["failure"])
        self.assertEqual(raised.exception.timeout, 20)
        self.assertEqual(raised.exception.output, b"original output")
        self.assertEqual(raised.exception.stderr, b"original error")
        self.assertEqual(captured["kwargs"], dict(cwd=self.consumer.root, env=self.consumer.env,
                                                text=True, capture_output=True, timeout=20))
        self.assertEqual(captured["argv"][:4], [BASH, "--noprofile", "--norc", "-c"])
        self.assertEqual(captured["argv"][5:], ["release-test", "one value"])
        self.assertIn(shell_definition(self.driver.text, "release_require_commit_path"), captured["argv"][4])
        self.assertIn('release_require_commit_path "$@"\n', captured["argv"][4])
        self.assertEqual(getattr(raised.exception, "__notes__", []), [
            "release fixture last observed phase: invocation-entered; announcement only, not effect or exit completion"])


    def _timeout_with_phase(self, raw, mutate=None):
        before = set(Path(self.tmp.name).glob("release-fixture-phase-*"))
        def timeout(argv, **kwargs):
            phases = set(Path(self.tmp.name).glob("release-fixture-phase-*")) - before
            self.assertEqual(len(phases), 1)
            phase = phases.pop()
            phase.write_bytes(raw)
            if mutate:
                mutate(phase)
            raise subprocess.TimeoutExpired(argv, 20, output=b"kept output", stderr=b"kept error")
        with mock.patch.object(subprocess, "run", side_effect=timeout):
            with self.assertRaises(subprocess.TimeoutExpired) as raised:
                self.driver.run_definition(self.consumer, "release_require_commit_path")
        self.assertEqual(raised.exception.output, b"kept output")
        self.assertEqual(raised.exception.stderr, b"kept error")
        return raised.exception.__notes__

    def test_empty_prefix_malformed_and_oversized_progress_have_closed_notes(self):
        for raw, expected in (
            (b"", "entry-not-observed"),
            (b"bash-entered\n", "bash-entered"),
            (b"bash-entered\ndefinition-ready\n", "definition-ready"),
            (b"bash-entered\ndefinition-ready\ninvocation-entered\ninvocation-returned\n", "invocation-returned"),
            (b"invocation-entered\n", "unavailable"),
            (b"bash-entered\r\n", "unavailable"),
            (b"bash-entered", "unavailable"),
            (b"bash-entered\nraw-secret-path-environment-canary\n", "unavailable"),
            (b"x" * 129, "unavailable"),
        ):
            with self.subTest(expected=expected, bytes=len(raw)):
                notes = self._timeout_with_phase(raw)
                self.assertEqual(notes, ["release fixture last observed phase: " + expected +
                                         "; announcement only, not effect or exit completion"])
                self.assertNotIn("canary", str(notes))

    def test_nonregular_replaced_linked_or_unreadable_progress_is_unavailable(self):
        def directory(path):
            path.unlink()
            path.mkdir()
        def replaced(path):
            original = path.with_suffix(".prior")
            path.rename(original)
            path.write_bytes(b"bash-entered\n")
        def linked(path):
            os.link(path, path.with_suffix(".linked"))
        for mutation in (directory, replaced, linked):
            with self.subTest(mutation=mutation.__name__):
                self.assertIn("phase: unavailable;", self._timeout_with_phase(b"bash-entered\n", mutation)[0])
        path = Path(self.tmp.name) / "unreadable-control"
        path.write_bytes(b"bash-entered\n")
        info = path.stat()
        with mock.patch.object(os, "open", side_effect=PermissionError("must not enter a note")) as denied:
            self.assertEqual(_last_fixture_phase(path, (info.st_dev, info.st_ino)), "unavailable")
        denied.assert_called_once()

    def test_real_shell_sink_denial_preserves_streams_arguments_and_exit_status(self):
        real_run = subprocess.run
        for status in (0, 17):
            self.driver.text = '```sh\nfixture_control() (\n  printf "%s" "$1"\n  printf "kept stderr" >&2\n  exit ' + str(status) + '\n)\n```\n'
            for denial in ("create", "write"):
                with self.subTest(status=status, denial=denial):
                    before = set(Path(self.tmp.name).glob("release-fixture-phase-*"))
                    def invoke(argv, **kwargs):
                        self.assertEqual(kwargs["timeout"], 20)
                        self.assertEqual(argv[5:], ["release-test", "one literal $value with spaces"])
                        if denial == "write":
                            phases = set(Path(self.tmp.name).glob("release-fixture-phase-*")) - before
                            self.assertEqual(len(phases), 1)
                            phase = phases.pop()
                            phase.unlink()
                            phase.mkdir()  # Real shell redirection refusal, never an arbitrary file.
                        return real_run(argv, **kwargs)
                    with mock.patch.object(subprocess, "run", side_effect=invoke):
                        if denial == "create":
                            with mock.patch.object(tempfile, "mkstemp", side_effect=PermissionError("private trace denied")):
                                result = self.driver.run_definition(self.consumer, "fixture_control", args=("one literal $value with spaces",))
                        else:
                            result = self.driver.run_definition(self.consumer, "fixture_control", args=("one literal $value with spaces",))
                    self.assertEqual(result.returncode, status)
                    self.assertEqual(result.stdout, "one literal $value with spaces")
                    self.assertEqual(result.stderr, "kept stderr")

    def test_ordinary_completed_process_is_returned_without_projection(self):
        result = subprocess.CompletedProcess(["fixed original argv"], 23, "original stdout", "original stderr")
        with mock.patch.object(subprocess, "run", return_value=result):
            observed = self.driver.run_definition(self.consumer, "release_require_commit_path", env={"EXTRA": "inert"})
        self.assertIs(observed, result)
        self.assertEqual((observed.returncode, observed.stdout, observed.stderr), (23, "original stdout", "original stderr"))


if __name__ == "__main__":
    unittest.main()

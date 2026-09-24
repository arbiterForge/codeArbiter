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
import subprocess
import sys
import tempfile
import textwrap
import unittest

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
           ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT", "BASH_ENV", "ENV", "CDPATH")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT="0", PY=sys.executable)
    return env


class Consumer:
    """A real history, declaration PR, published ledger, and fresh release branch."""

    def __init__(self, base, method="merge", missing_footer=False, ledger="valid"):
        self.base = Path(base)
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
            [sys.executable, str(HOOKS / "_releaselib.py"), "backfill-detect"],
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
            [sys.executable, str(HOOKS / "_releaselib.py"), "validate-reconciliations", "app", str(draft)],
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
                        CLAUDE_PLUGIN_ROOT=str(PLUGIN), PROJECT_ROOT=str(self.root),
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
        return subprocess.run([sys.executable, str(HOOKS / "_releaselib.py"), *args],
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
        return subprocess.run([BASH, "--noprofile", "--norc", "-c", script, "release-test", *args],
                              cwd=consumer.root, env={**consumer.env, **(env or {})},
                              text=True, capture_output=True, timeout=20)

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
                log = c.git("log", "HEAD", "--pretty=format:%H%n%s%n%b%n----", "--",
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
        log = c.git("log", "HEAD", "--pretty=format:%H%n%s%n%b%n----", "--", *c.pathspecs).stdout
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


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# codeArbiter — execute release guards from exact committed host payloads.
"""PR #852 slice 3: distribution-faithful guard and adoption qualification.

This is deterministic package-boundary evidence, not an independent agent
exercise or a live Claude/Codex/Pi session. Host placeholders are bound to
fixture-owned directories; executable definitions and helpers come only from
`git archive HEAD`. No canonical source directory is copied into the install.
"""

import hashlib
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile
import unittest

from test_release_workflow_followup import (
    BASH, GIT, PLUGIN, Consumer, isolated_env, shell_definition,
)

ROOT = PLUGIN.parents[1]
HOSTS = (
    ("claude", "plugins/ca", "skills/release/SKILL.md"),
    ("codex", "plugins/ca-codex", "routines/release/SKILL.md"),
    ("pi", "plugins/ca-pi", "routines/release/SKILL.md"),
)


@unittest.skipUnless(BASH and GIT, "requires same-runtime bash and git")
class CommittedReleaseDistributionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="ca-release-distribution-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.base = Path(cls.tmp.name)
        cls.payloads = {}
        cls.commit = subprocess.check_output(
            [GIT, "rev-parse", "HEAD"], cwd=ROOT, env=isolated_env(),
            text=True, timeout=15).strip()
        for host, prefix, skill in HOSTS:
            install = cls.base / (host + " installed payload")
            install.mkdir()
            archive = cls.base / (host + ".tar")
            with archive.open("wb") as output:
                subprocess.run(
                    [GIT, "archive", "--format=tar", cls.commit, "--", prefix],
                    cwd=ROOT, env=isolated_env(), stdout=output, check=True, timeout=30)
            # Only regular files below the selected package are admitted. Do
            # not extract links or trust a member's path outside that prefix.
            with tarfile.open(archive) as tar:
                for member in tar:
                    path = PurePosixPath(member.name)
                    if member.isdir():
                        continue
                    if not member.isfile() or path.is_absolute() or ".." in path.parts:
                        raise AssertionError(f"unsafe archived member: {member.name}")
                    relative = path.relative_to(prefix)
                    target = install.joinpath(*relative.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(tar.extractfile(member).read())
            cls.payloads[host] = (install, prefix, skill)

    def run_guard(self, host, consumer, name, *, env=None, args=(), trailer=None):
        install, _, skill = self.payloads[host]
        text = (install / skill).read_text(encoding="utf-8")
        definition = shell_definition(text, name)
        # Only host-owned root substitutions; no rewriting of decisions.
        definition = definition.replace("<plugin-root>", "${PLUGIN_ROOT}")
        definition = definition.replace("<project-root>", "${PROJECT_ROOT}")
        script = "set -eu\n" + definition + "\n" + (trailer or name + ' "$@"\n')
        return subprocess.run(
            [BASH, "--noprofile", "--norc", "-c", script, "release-test", *args],
            cwd=consumer.root, env={**consumer.env, "PLUGIN_ROOT": str(install),
                "CLAUDE_PLUGIN_ROOT": str(install), **(env or {})},
            text=True, capture_output=True, timeout=20)

    def consumer(self, host, tmp, **kwargs):
        return Consumer(tmp, plugin_root=self.payloads[host][0], **kwargs)

    def test_archive_identity_and_resource_closure_for_all_hosts(self):
        self.assertEqual(set(self.payloads), {"claude", "codex", "pi"})
        for host, (install, prefix, skill) in self.payloads.items():
            with self.subTest(host=host):
                for relative in (skill, "hooks/_releaselib.py", "hooks/_gitexec.py"):
                    expected = subprocess.check_output(
                        [GIT, "show", f"{self.commit}:{prefix}/{relative}"],
                        cwd=ROOT, env=isolated_env(), timeout=15)
                    self.assertEqual(hashlib.sha256((install / relative).read_bytes()).digest(),
                                     hashlib.sha256(expected).digest())
                for absent in ("core", ".github", ".codearbiter", ".git"):
                    self.assertFalse((install / absent).exists())
                text = (install / skill).read_text(encoding="utf-8")
                for name in ("release_window_state", "release_require_clean_tree",
                             "release_require_commit_path"):
                    self.assertTrue(shell_definition(text, name))

    def test_all_hosts_reenter_after_every_merge_method_without_silent_widening(self):
        for host in self.payloads:
            for method in ("ff", "squash", "merge"):
                with self.subTest(host=host, method=method), tempfile.TemporaryDirectory() as tmp:
                    c = self.consumer(host, tmp, method=method, missing_footer=True)
                    before = c.fingerprint()
                    narrow = c.env["EFFECTIVE_WINDOW"]
                    result = self.run_guard(host, c, "release_window_state", args=c.pathspecs)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), "confirm-first-release-window")
                    self.assertEqual(c.env["EFFECTIVE_WINDOW"], narrow)
                    self.assertEqual(before, c.fingerprint())
                    # Fixture-owned explicit choice, never a production receipt.
                    ready = self.run_guard(host, c, "release_window_state", args=c.pathspecs,
                                           env={"EFFECTIVE_WINDOW": "HEAD"})
                    self.assertEqual((ready.returncode, ready.stdout.strip()), (0, "ready"), ready.stderr)
                    log = c.git("log", "HEAD", "--pretty=format:%H%n%s%n%b%n----", "--", *c.pathspecs).stdout
                    verdict = c.helper("classify-window", "app", "main", input=log)
                    self.assertEqual(verdict.returncode, 0, verdict.stderr)
                    self.assertIn("[RECONCILED]", verdict.stdout)
                    self.assertEqual(before, c.fingerprint())

    def test_missing_published_ledger_entry_remains_blocking_in_every_host(self):
        for host in self.payloads:
            with self.subTest(host=host), tempfile.TemporaryDirectory() as tmp:
                c = self.consumer(host, tmp, missing_footer=True, ledger="empty")
                before = c.fingerprint()
                log = c.git("log", "HEAD", "--pretty=format:%H%n%s%n%b%n----", "--", *c.pathspecs).stdout
                verdict = c.helper("classify-window", "app", "main", input=log)
                self.assertEqual(verdict.returncode, 1, verdict.stderr)
                self.assertIn("[NEEDS-TRIAGE]", verdict.stdout)
                self.assertEqual(before, c.fingerprint())

    def test_clean_dirty_and_missing_setup_guards_execute_before_writes_in_every_host(self):
        for host in self.payloads:
            with self.subTest(host=host), tempfile.TemporaryDirectory() as tmp:
                c = self.consumer(host, tmp)
                clean = self.run_guard(host, c, "release_require_clean_tree")
                self.assertEqual(clean.returncode, 0, clean.stderr)
                prepared = self.run_guard(host, c, "release_require_commit_path")
                self.assertEqual(prepared.returncode, 0, prepared.stderr)
                c.write("app.py", "changed = True\n")
                before = c.fingerprint()
                dirty = self.run_guard(host, c, "release_require_clean_tree", trailer=
                    'release_require_clean_tree || exit "$?"\nprintf unwanted > must-not-exist\n')
                self.assertNotEqual(dirty.returncode, 0)
                self.assertIn("app.py", dirty.stderr)
                self.assertEqual(before, c.fingerprint())
                (c.root / ".codearbiter/tech-stack.md").unlink()
                before = c.fingerprint()
                missing = self.run_guard(host, c, "release_require_commit_path", trailer=
                    'release_require_commit_path || exit "$?"\nprintf unwanted > must-not-exist\n')
                self.assertNotEqual(missing.returncode, 0)
                self.assertIn("tech-stack.md", missing.stderr)
                self.assertEqual(before, c.fingerprint())


if __name__ == "__main__":
    unittest.main()

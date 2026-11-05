"""Branch coverage for security-pass.py.

The guard-logic matrix (.github/scripts/test_hook_guards.py) exercises only the
happy path (case 6c: one sensitive line, committed repo). This file covers the
branches it doesn't: no-.codearbiter exit, empty-digest write, reviewed staged
scope, root binding, and the unborn-branch (no HEAD) path.

Same subprocess style as the other guard tests: run security-pass.py via the
current interpreter, cwd'd into a throwaway repo, and read the marker it writes.
Stdlib only.
"""
import json
import hashlib
import importlib.util
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HOOKS)
import _hooklib  # noqa: E402
import _gitexec  # noqa: E402
import _overrideappendlib  # noqa: E402

SECURITY_PASS = os.path.join(HOOKS, "security-pass.py")
GIT_ENFORCE = os.path.join(HOOKS, "git-enforce.py")
PRE_BASH = os.path.join(HOOKS, "pre-bash.py")
CRYPTO_LINE = "const h = createHash('md5');\n"  # matches CRYPTO_RE


def _sh(args, cwd, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60, **kw)


def _git(args, cwd):
    r = _sh(["git"] + args, cwd)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}")
    return r


class _Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "repo")
        os.makedirs(self.root)
        _git(["init", "-q", "-b", "feat/work", self.root], self._tmp.name)
        _git(["config", "user.email", "h@example.com"], self.root)
        _git(["config", "user.name", "h"], self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _ca(self):
        os.makedirs(os.path.join(self.root, ".codearbiter"), exist_ok=True)
        self._write(
            ".codearbiter/CONTEXT.md",
            "---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n")

    def _write(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def run_pass(self, args=None, cwd=None, env=None):
        argv = [sys.executable, SECURITY_PASS]
        argv.extend(["--root", self.root] if args is None else args)
        return _sh(argv, cwd or self.root, env=env)

    def marker(self):
        p = os.path.join(self.root, ".codearbiter", ".markers", "security-gate-passed")
        if not os.path.isfile(p):
            return None
        with open(p, encoding="utf-8") as f:
            return f.read()

    def run_commit_hook(self):
        payload = json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m binary-fixture"},
        })
        return _sh([sys.executable, PRE_BASH], self.root, input=payload)


class TestSecurityPassBranches(_Fixture):
    def test_binary_override_audit_failure_cannot_create_or_replace_marker(self):
        self._ca()
        marker = os.path.join(
            self.root, ".codearbiter", ".markers", "security-gate-passed")
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        with open(marker, "w", encoding="utf-8") as stream:
            stream.write("existing-marker\n")
        spec = importlib.util.spec_from_file_location(
            "_security_pass_audit_order_test", SECURITY_PASS)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        binary = _hooklib.BinarySecurityContext(
            "candidate-v1:test", False, (), ())
        with (mock.patch.object(module, "candidate_scan", return_value=binary),
              mock.patch.object(module, "binary_candidate_binding",
                                return_value="binary-candidate-v1:" + "1" * 64),
              mock.patch.object(module, "write_text_atomic") as write_marker,
              mock.patch.object(
                  _overrideappendlib, "append_override",
                  side_effect=_overrideappendlib.OverrideAppendError("audit unavailable"))):
            with self.assertRaises(SystemExit) as refused:
                module.main([
                    "--root", self.root, "--binary-override",
                    "--security-finding", "opaque fixture",
                    "--reason", "required release asset",
                ])
        self.assertEqual(refused.exception.code, 1)
        write_marker.assert_not_called()
        with open(marker, encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "existing-marker\n")

    def test_untracked_symlink_is_outside_the_reviewed_staged_set(self):
        self._ca()
        target = os.path.join(self._tmp.name, "outside.txt")
        with open(target, "w", encoding="utf-8") as stream:
            stream.write("finite ordinary target\n")
        link = os.path.join(self.root, "untracked-link")
        for destination in (target, os.path.abspath(os.devnull)):
            with self.subTest(destination=destination):
                os.symlink(destination, link)
                try:
                    self.assertTrue(stat.S_ISLNK(os.lstat(link).st_mode))
                    result = self.run_pass()
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertRegex(self.marker(),
                                     r"^root-v1:[0-9a-f]{64}\ncandidate-v1:[0-9a-f]{64}\n$")
                finally:
                    os.unlink(link)

    def test_no_codearbiter_exits_1(self):
        # No .codearbiter/ dir -> refuse, exit 1, record nothing.
        res = self.run_pass()
        self.assertEqual(res.returncode, 1)
        self.assertIn("no .codearbiter", res.stderr.lower())

    def test_empty_digest_when_no_sensitive_lines(self):
        # A benign committed repo with a benign change -> marker written empty.
        self._ca()
        self._write("notes.txt", "hello\n")
        _git(["add", "notes.txt"], self.root)
        _git(["commit", "-q", "-m", "seed"], self.root)
        self._write("notes.txt", "hello\nworld\n")
        res = self.run_pass()
        self.assertEqual(res.returncode, 0)
        self.assertIn("0 sensitive line", res.stdout)
        self.assertRegex(self.marker(),
                         r"^root-v1:[0-9a-f]{64}\ncandidate-v1:[0-9a-f]{64}\n$")

    def test_untracked_sensitive_line_is_not_silently_recorded(self):
        # #1037: an untracked row was not in the staged diff reviewed by the
        # independent reviewer, so the producer must not absorb it.
        self._ca()
        self._write("auth.js", CRYPTO_LINE)  # untracked, never added
        res = self.run_pass()
        self.assertEqual(res.returncode, 0)
        self.assertIn("0 sensitive line", res.stdout)
        self.assertNotIn("path-v1:", self.marker())

    def test_staged_sensitive_line_is_recorded_with_root_binding(self):
        self._ca()
        self._write("auth.js", CRYPTO_LINE)
        _git(["add", "auth.js"], self.root)
        res = self.run_pass()
        self.assertEqual(res.returncode, 0, res.stderr)
        records = self.marker().splitlines()
        self.assertEqual(len(records), 3, records)
        self.assertRegex(records[0], r"^root-v1:[0-9a-f]{64}$")
        self.assertRegex(records[1], r"^candidate-v1:[0-9a-f]{64}$")
        self.assertRegex(records[2], r"^path-v1:[0-9a-f]{64}$")

    def test_alternate_index_is_scanned_by_producer_and_precommit(self):
        self._ca()
        self._write("seed.txt", "seed\n")
        _git(["add", "seed.txt", ".codearbiter/CONTEXT.md"], self.root)
        _git(["commit", "-q", "-m", "seed"], self.root)
        alternate = os.path.join(self.root, ".git", "alternate-index")
        shutil.copyfile(os.path.join(self.root, ".git", "index"), alternate)
        self._write("auth.js", CRYPTO_LINE)
        env = {**os.environ, "GIT_INDEX_FILE": alternate}
        staged = _sh(["git", "add", "auth.js"], self.root, env=env)
        self.assertEqual(staged.returncode, 0, staged.stderr)
        blocked = _sh([sys.executable, GIT_ENFORCE, "pre-commit"], self.root, env=env)
        self.assertEqual(blocked.returncode, 1, blocked.stderr)
        self.assertIn("[H-09b]", blocked.stderr)
        encoded = blocked.stderr.split("reviewed checkout: ", 1)[1].split(
            ". Verify", 1)[0]
        invocation = json.loads(encoded)
        self.assertEqual(invocation["environment"], {"GIT_INDEX_FILE": alternate})
        recorded = _sh(invocation["argv"], self.root,
                       env={**os.environ, **invocation["environment"]})
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        allowed = _sh([sys.executable, GIT_ENFORCE, "pre-commit"], self.root, env=env)
        self.assertEqual(allowed.returncode, 0, allowed.stderr)

    def test_rename_only_sensitive_move_requires_a_fresh_review(self):
        self._ca()
        self._write("legacy/auth.js", CRYPTO_LINE)
        _git(["add", "legacy/auth.js", ".codearbiter/CONTEXT.md"], self.root)
        _git(["commit", "-q", "-m", "seed sensitive source"], self.root)
        _git(["config", "diff.renames", "true"], self.root)
        os.makedirs(os.path.join(self.root, "runtime"))
        _git(["mv", "legacy/auth.js", "runtime/auth.js"], self.root)

        blocked = _sh([sys.executable, GIT_ENFORCE, "pre-commit"], self.root)
        self.assertEqual(blocked.returncode, 1, blocked.stderr)
        self.assertIn("[H-09b]", blocked.stderr)
        self.assertIn("runtime/auth.js", blocked.stderr)

        recorded = self.run_pass()
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        allowed = _sh([sys.executable, GIT_ENFORCE, "pre-commit"], self.root)
        self.assertEqual(allowed.returncode, 0, allowed.stderr)

    def test_binary_attribute_cannot_hide_text_crypto_or_secret_rows(self):
        self._ca()
        self._write(".gitattributes", "*.js binary\n")
        self._write("runtime/auth.js",
                    "const h = createHash('md5');\napi_token = '<redacted>';\n")
        _git(["add", ".gitattributes", "runtime/auth.js", ".codearbiter/CONTEXT.md"],
             self.root)

        blocked = _sh([sys.executable, GIT_ENFORCE, "pre-commit"], self.root)
        self.assertEqual(blocked.returncode, 1, blocked.stderr)
        self.assertIn("[H-09b]", blocked.stderr)
        self.assertIn(".gitattributes", blocked.stderr)
        self.assertIn("/ca:override", blocked.stderr)
        refused = self.run_pass()
        self.assertEqual(refused.returncode, 1, refused.stderr)
        self.assertIn(".gitattributes", refused.stderr)
        self.assertIn("/ca:override", refused.stderr)

        # Removing the misleading attribute restores the ordinary review lane.
        self._write(".gitattributes", "")
        _git(["add", ".gitattributes"], self.root)
        review_block = _sh([sys.executable, GIT_ENFORCE, "pre-commit"], self.root)
        self.assertEqual(review_block.returncode, 1, review_block.stderr)
        self.assertIn("crypto/TLS=1", review_block.stderr)
        self.assertIn("secret=1", review_block.stderr)
        recorded = self.run_pass()
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        allowed = _sh([sys.executable, GIT_ENFORCE, "pre-commit"], self.root)
        self.assertEqual(allowed.returncode, 0, allowed.stderr)

    def test_genuine_binary_refusal_names_the_explicit_audited_route(self):
        self._ca()
        path = os.path.join(self.root, "assets", "payload.bin")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as stream:
            stream.write(b"\x00\xffbinary payload\x00")
        _git(["add", "assets/payload.bin", ".codearbiter/CONTEXT.md"], self.root)

        blocked = _sh([sys.executable, GIT_ENFORCE, "pre-commit"], self.root)
        self.assertEqual(blocked.returncode, 1, blocked.stderr)
        self.assertIn("genuine binary", blocked.stderr)
        self.assertIn("/ca:override", blocked.stderr)
        refused = self.run_pass()
        self.assertEqual(refused.returncode, 1, refused.stderr)
        self.assertIn("genuine binary", refused.stderr)
        self.assertIn("/ca:override", refused.stderr)

    def test_genuine_binary_override_is_audited_exact_and_executable(self):
        self._ca()
        self._write(".codearbiter/overrides.log", "# append-only overrides\n")
        _git(["config", "core.abbrev", "4"], self.root)
        path = os.path.join(self.root, "assets", "payload.bin")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as stream:
            payload_v1 = b"\x00\xffbinary payload v1\x00"
            stream.write(payload_v1)
        _git(["add", "assets/payload.bin", ".codearbiter/CONTEXT.md"], self.root)
        binary_diff = _sh(["git", *_hooklib.SECURITY_DIFF_GIT_ARGS, "--cached"], self.root)
        self.assertEqual(binary_diff.returncode, 0, binary_diff.stderr)
        self.assertNotIn("--binary", _hooklib.SECURITY_DIFF_GIT_ARGS)
        self.assertNotIn("GIT binary patch", binary_diff.stdout)
        self.assertRegex(binary_diff.stdout, r"(?m)^index [0-9a-f]{40,64}\.\.[0-9a-f]{40,64}")
        _mode, staged_sha256 = _gitexec.read_index_blob_identity(
            self.root, "assets/payload.bin", preserve_index=True)
        self.assertEqual(staged_sha256, hashlib.sha256(payload_v1).hexdigest())
        binary_candidate = _gitexec.binary_candidate_binding(
            self.root, preserve_index=True)
        self.assertRegex(binary_candidate, r"^binary-candidate-v1:[0-9a-f]{64}$")

        overridden = self.run_pass(args=[
            "--root", self.root, "--binary-override",
            "--security-finding", "genuine binary assets/payload.bin",
            "--reason", "required opaque release fixture",
        ])
        self.assertEqual(overridden.returncode, 0, overridden.stderr)
        self.assertIn("binary security override recorded", overridden.stdout)
        with open(os.path.join(self.root, ".codearbiter", "overrides.log"),
                  encoding="utf-8") as stream:
            audit = stream.read()
        self.assertIn("SECURITY-OVERRIDE", audit)
        self.assertIn("genuine binary assets/payload.bin", audit)
        self.assertRegex(self.marker(),
                         r"^root-v1:[0-9a-f]{64}\nbinary-override-v1:[0-9a-f]{64}\n$")
        self.assertIn(_hooklib.binary_override_binding(binary_candidate), self.marker())
        allowed = _sh([sys.executable, GIT_ENFORCE, "pre-commit"], self.root)
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        allowed_hook = self.run_commit_hook()
        self.assertEqual(allowed_hook.returncode, 0, allowed_hook.stderr)

        with open(path, "wb") as stream:
            stream.write(b"\x00\xffbinary payload v2\x00")
        _git(["add", "assets/payload.bin"], self.root)
        changed = _sh([sys.executable, GIT_ENFORCE, "pre-commit"], self.root)
        self.assertEqual(changed.returncode, 1, changed.stderr)
        self.assertIn("[H-09b]", changed.stderr)
        changed_hook = self.run_commit_hook()
        self.assertEqual(changed_hook.returncode, 2, changed_hook.stderr)
        self.assertIn("[H-09b]", changed_hook.stderr)

    def test_binary_override_binds_every_binary_in_one_candidate(self):
        self._ca()
        self._write(".codearbiter/overrides.log", "# append-only overrides\n")
        paths = []
        for name, payload in (("one.bin", b"\x00one-v1\xff"),
                              ("two.bin", b"\x00two-v1\xff")):
            path = os.path.join(self.root, "assets", name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as stream:
                stream.write(payload)
            paths.append(path)
        _git(["add", "assets/one.bin", "assets/two.bin",
              ".codearbiter/CONTEXT.md"], self.root)
        real_run = subprocess.run
        with mock.patch.object(_gitexec.subprocess, "run", wraps=real_run) as run:
            candidate = _gitexec.binary_candidate_binding(
                self.root, preserve_index=True)
        self.assertRegex(candidate, r"^binary-candidate-v1:[0-9a-f]{64}$")
        self.assertLessEqual(run.call_count, 6, "binary hashing regressed to per-file Git calls")

        def record(reason):
            result = self.run_pass(args=[
                "--root", self.root, "--binary-override",
                "--security-finding", "two exact opaque fixtures",
                "--reason", reason,
            ])
            self.assertEqual(result.returncode, 0, result.stderr)

        record("first exact two-file candidate")
        self.assertEqual(_sh([sys.executable, GIT_ENFORCE, "pre-commit"],
                             self.root).returncode, 0)
        with open(paths[0], "wb") as stream:
            stream.write(b"\x00one-v2\xff")
        _git(["add", "assets/one.bin"], self.root)
        self.assertEqual(_sh([sys.executable, GIT_ENFORCE, "pre-commit"],
                             self.root).returncode, 1)

        record("second exact two-file candidate")
        self.assertEqual(_sh([sys.executable, GIT_ENFORCE, "pre-commit"],
                             self.root).returncode, 0)
        with open(paths[1], "wb") as stream:
            stream.write(b"\x00two-v2\xff")
        _git(["add", "assets/two.bin"], self.root)
        self.assertEqual(_sh([sys.executable, GIT_ENFORCE, "pre-commit"],
                             self.root).returncode, 1)
        self.assertEqual(self.run_commit_hook().returncode, 2)

    def test_binary_deletion_override_binds_committed_head_preimage(self):
        self._ca()
        self._write(".codearbiter/overrides.log", "# append-only overrides\n")
        path = os.path.join(self.root, "assets", "delete.bin")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as stream:
            stream.write(b"\x00head-v1\xff")
        _git(["add", "assets/delete.bin", ".codearbiter/CONTEXT.md",
              ".codearbiter/overrides.log"], self.root)
        _git(["commit", "-q", "-m", "seed binary preimage"], self.root)
        _git(["rm", "-q", "assets/delete.bin"], self.root)
        recorded = self.run_pass(args=[
            "--root", self.root, "--binary-override",
            "--security-finding", "delete exact opaque fixture",
            "--reason", "remove obsolete fixture",
        ])
        self.assertEqual(recorded.returncode, 0, recorded.stderr)
        self.assertEqual(_sh([sys.executable, GIT_ENFORCE, "pre-commit"],
                             self.root).returncode, 0)

        _git(["restore", "--staged", "assets/delete.bin"], self.root)
        _git(["restore", "assets/delete.bin"], self.root)
        with open(path, "wb") as stream:
            stream.write(b"\x00head-v2\xff")
        _git(["add", "assets/delete.bin"], self.root)
        _git(["commit", "-q", "-m", "replace binary preimage",
              "--", "assets/delete.bin"], self.root)
        _git(["rm", "-q", "assets/delete.bin"], self.root)
        stale = _sh([sys.executable, GIT_ENFORCE, "pre-commit"], self.root)
        self.assertEqual(stale.returncode, 1, stale.stderr)
        self.assertIn("[H-09b]", stale.stderr)
        stale_hook = self.run_commit_hook()
        self.assertEqual(stale_hook.returncode, 2, stale_hook.stderr)
        self.assertIn("[H-09b]", stale_hook.stderr)

    def test_binary_override_refuses_concurrent_reviewable_sensitive_text(self):
        self._ca()
        self._write(".codearbiter/overrides.log", "# append-only overrides\n")
        path = os.path.join(self.root, "assets", "payload.bin")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as stream:
            stream.write(b"\x00opaque payload\xff")
        self._write("auth.js", "const h = createHash('md5');\napi_token = '<redacted>';\n")
        _git(["add", "assets/payload.bin", "auth.js", ".codearbiter/CONTEXT.md"], self.root)

        refused = self.run_pass(args=[
            "--root", self.root, "--binary-override",
            "--security-finding", "genuine binary assets/payload.bin",
            "--reason", "required opaque release fixture",
        ])
        self.assertEqual(refused.returncode, 1, refused.stderr)
        self.assertIn("binary changes separately", refused.stderr)
        with open(os.path.join(self.root, ".codearbiter", "overrides.log"),
                  encoding="utf-8") as stream:
            self.assertNotIn("SECURITY-OVERRIDE", stream.read())
        backstop = _sh([sys.executable, GIT_ENFORCE, "pre-commit"], self.root)
        hook = self.run_commit_hook()
        self.assertEqual(backstop.returncode, 1, backstop.stderr)
        self.assertEqual(hook.returncode, 2, hook.stderr)
        self.assertIn("binary changes separately", backstop.stderr)
        self.assertIn("binary changes separately", hook.stderr)

    def test_binary_override_audit_ignores_hostile_repository_selectors(self):
        self._ca()
        self._write(".codearbiter/overrides.log", "# repo-a overrides\n")
        path = os.path.join(self.root, "assets", "payload.bin")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as stream:
            stream.write(b"\x00repo-a payload\xff")
        _git(["add", "assets/payload.bin", ".codearbiter/CONTEXT.md"], self.root)

        other = os.path.join(self._tmp.name, "repo-b")
        os.makedirs(other)
        _git(["init", "-q", "-b", "feat/other", other], self._tmp.name)
        _git(["config", "user.email", "other@example.com"], other)
        _git(["config", "user.name", "other"], other)
        os.makedirs(os.path.join(other, ".codearbiter"))
        with open(os.path.join(other, ".codearbiter", "overrides.log"),
                  "w", encoding="utf-8") as stream:
            stream.write("# repo-b overrides\n")
        env = {**os.environ, "GIT_DIR": os.path.join(other, ".git"),
               "GIT_WORK_TREE": other}
        result = self.run_pass(args=[
            "--root", self.root, "--binary-override",
            "--security-finding", "genuine binary assets/payload.bin",
            "--reason", "required opaque release fixture",
        ], env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(os.path.join(self.root, ".codearbiter", "overrides.log"),
                  encoding="utf-8") as stream:
            self.assertIn("SECURITY-OVERRIDE", stream.read())
        with open(os.path.join(other, ".codearbiter", "overrides.log"),
                  encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "# repo-b overrides\n")

    def test_unattributed_binary_markers_stay_on_malformed_context_route(self):
        for malformed in (
                "GIT binary patch\n",
                "Binary files a/payload.bin and b/payload.bin differ\n"):
            with self.subTest(malformed=malformed):
                self.assertIsNone(_hooklib.security_scan_diff(malformed))

    def test_large_untracked_file_is_outside_reviewed_staged_set(self):
        # Size cannot pull an untracked file into the independently reviewed
        # staged candidate.
        self._ca()
        big = ("x" * 1_000_001) + "\n" + CRYPTO_LINE
        self._write("blob.js", big)
        res = self.run_pass()
        self.assertEqual(res.returncode, 0)
        self.assertIn("0 sensitive line", res.stdout)

    def test_unborn_branch_records_staged_sensitive_line(self):
        # No commit yet (unborn HEAD): `git diff HEAD` fails, fall back to ls-files.
        self._ca()
        self._write("auth.js", CRYPTO_LINE)
        _git(["add", "auth.js"], self.root)  # tracked, but no HEAD exists
        res = self.run_pass()
        self.assertEqual(res.returncode, 0)
        self.assertIn("1 sensitive line", res.stdout)

    def test_unstaged_sensitive_line_is_not_silently_recorded(self):
        # #1037: a worktree-only row is not in the staged review candidate.
        self._ca()
        self._write("auth.js", "const ok = 1;\n")
        _git(["add", "auth.js"], self.root)
        _git(["commit", "-q", "-m", "seed"], self.root)
        self._write("auth.js", "const ok = 1;\n" + CRYPTO_LINE)
        res = self.run_pass()
        self.assertEqual(res.returncode, 0)
        self.assertIn("0 sensitive line", res.stdout)
        self.assertNotIn("path-v1:", self.marker())

    def test_gate_events_log_untracked_contributes_no_digests(self):
        # #279: gate-events.log is the gate's own machine-written audit sink —
        # its REMIND text ("no MD5/SHA1/DES/3DES/RC2/RC4/Blowfish") matches
        # CRYPTO_RE just as well as a genuine algorithm choice would, so an
        # UNTRACKED gate-events.log full of such lines must contribute ZERO
        # digests to the marker (the untracked-file branch of candidate_lines).
        self._ca()
        self._write(".codearbiter/gate-events.log", CRYPTO_LINE * 3)
        res = self.run_pass()
        self.assertEqual(res.returncode, 0)
        self.assertIn("0 sensitive line", res.stdout)
        self.assertRegex(self.marker(),
                         r"^root-v1:[0-9a-f]{64}\ncandidate-v1:[0-9a-f]{64}\n$")

    def test_gate_events_log_diff_contributes_no_digests(self):
        # #279: same exemption via the `git diff HEAD` branch — a COMMITTED
        # gate-events.log with a new, uncommitted REMIND line appended must
        # still contribute zero digests, proving the diff walk (not just the
        # untracked-file walk) is path-aware.
        self._ca()
        self._write(".codearbiter/gate-events.log", "seed\n")
        _git(["add", ".codearbiter/gate-events.log"], self.root)
        _git(["commit", "-q", "-m", "seed log"], self.root)
        self._write(".codearbiter/gate-events.log", "seed\n" + CRYPTO_LINE)
        res = self.run_pass()
        self.assertEqual(res.returncode, 0)
        self.assertIn("0 sensitive line", res.stdout)
        self.assertRegex(self.marker(),
                         r"^root-v1:[0-9a-f]{64}\ncandidate-v1:[0-9a-f]{64}\n$")

    def test_invalid_explicit_roots_preserve_prior_marker(self):
        self._ca()
        marker_dir = os.path.join(self.root, ".codearbiter", ".markers")
        os.makedirs(marker_dir)
        marker_path = os.path.join(marker_dir, "security-gate-passed")
        with open(marker_path, "w", encoding="utf-8") as stream:
            stream.write("prior-marker\n")
        nested = os.path.join(self.root, "nested")
        os.makedirs(nested)
        cases = (
            (["--root", nested], self.root),
            (["--root", os.path.join(self.root, "missing")], self.root),
            (["--wrong", self.root], self.root),
            (["--root"], self.root),
        )
        for args, cwd in cases:
            with self.subTest(args=args):
                result = self.run_pass(args, cwd)
                self.assertEqual(result.returncode, 1, result)
                self.assertEqual(self.marker(), "prior-marker\n")

    def test_explicit_root_is_used_from_another_cwd(self):
        self._ca()
        self._write("auth.js", CRYPTO_LINE)
        _git(["add", "auth.js"], self.root)
        result = self.run_pass(cwd=self._tmp.name)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("candidate-v1:", self.marker())

    def test_non_utf8_staged_candidate_is_unreadable_and_preserves_marker(self):
        self._ca()
        marker_dir = os.path.join(self.root, ".codearbiter", ".markers")
        os.makedirs(marker_dir)
        marker = os.path.join(marker_dir, "security-gate-passed")
        with open(marker, "w", encoding="utf-8") as stream:
            stream.write("prior-marker\n")
        path = os.path.join(self.root, "auth.js")
        with open(path, "wb") as stream:
            stream.write(b'api_token = "\xff"\n')
        _git(["add", "auth.js"], self.root)
        result = self.run_pass()
        self.assertEqual(result.returncode, 1, result)
        self.assertIn("unavailable or malformed", result.stderr)
        self.assertEqual(self.marker(), "prior-marker\n")

    def test_gate_events_log_exemption_is_narrow(self):
        # #279 non-weakening proof: the SAME sensitive line, in a DIFFERENT
        # file, must still be recorded — only gate-events.log is exempt.
        self._ca()
        self._write(".codearbiter/overrides.log", CRYPTO_LINE)
        _git(["add", ".codearbiter/overrides.log"], self.root)
        res = self.run_pass()
        self.assertEqual(res.returncode, 0)
        self.assertIn("1 sensitive line", res.stdout)
        self.assertTrue(self.marker().strip())

    def test_marker_write_leaves_no_temp_file(self):
        # migration-002: the marker is written atomically (temp + os.replace), so
        # after a successful run the .markers dir holds the marker and no .tmp.
        self._ca()
        self._write("auth.js", CRYPTO_LINE)
        res = self.run_pass()
        self.assertEqual(res.returncode, 0)
        markers_dir = os.path.join(self.root, ".codearbiter", ".markers")
        entries = sorted(os.listdir(markers_dir))
        self.assertEqual(entries, ["security-gate-passed"],
                         f"only the marker should remain, got {entries}")


if __name__ == "__main__":
    unittest.main()

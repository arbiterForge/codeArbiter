#!/usr/bin/env python3
"""codeArbiter — unit tests for the preview diff-collection helper (T-03).

Proves _previewlib.collect_diff over the three change kinds it must union
(tracked-unstaged, staged, untracked) and the two graceful edges that must NOT
raise: a non-repo directory and a clean repo. Every case runs inside a throwaway
temp git repo built with tempfile + git init so the real working tree is never
touched; cwd is captured in setUp and restored in tearDown.

Stdlib only. Run as: python .github/scripts/test_preview_lib.py
Exit 0 = all tests pass; non-zero = failure.
"""

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOOKS = os.path.join(REPO, "plugins", "ca", "hooks")
sys.path.insert(0, HOOKS)

import _previewlib  # noqa: E402  — needs sys.path mutation above


def git(args, cwd):
    r = subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}")
    return r


def write(root, rel, text):
    path = os.path.join(root, rel)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def init_repo(root):
    """A repo with one commit so HEAD exists for diff vs HEAD."""
    git(["init", "-q", "-b", "main", root], os.path.dirname(root))
    git(["config", "user.email", "test@example.com"], root)
    git(["config", "user.name", "test"], root)
    write(root, "seed.txt", "seed\n")
    git(["add", "seed.txt"], root)
    git(["commit", "-q", "-m", "seed"], root)


def paths_of(result):
    """The set of changed paths from a collect_diff result, normalized to
    forward slashes. Tolerant of either a dict-of-entries or a list/iterable of
    entries that carry a `path` attribute or key."""
    out = set()
    items = result.values() if isinstance(result, dict) else result
    for entry in items:
        if isinstance(entry, str):
            p = entry
        elif isinstance(entry, dict):
            p = entry.get("path")
        else:
            p = getattr(entry, "path", None)
        if p:
            out.add(p.replace("\\", "/"))
    return out


class CollectDiffTest(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self.base = tempfile.mkdtemp(prefix="ca-previewlib-")

    def tearDown(self):
        os.chdir(self._cwd)
        import shutil
        shutil.rmtree(self.base, ignore_errors=True)

    def _repo(self, name):
        root = os.path.join(self.base, name)
        os.makedirs(root)
        init_repo(root)
        return root

    def test_unions_all_three_change_kinds(self):
        root = self._repo("repo")
        # (a) tracked file modified, left unstaged
        write(root, "seed.txt", "seed\nmodified line\n")
        # (b) a second file, staged
        write(root, "staged.txt", "staged content\n")
        git(["add", "staged.txt"], root)
        # (c) a brand-new untracked file
        write(root, "untracked.txt", "untracked content\n")

        result = _previewlib.collect_diff(root)
        paths = paths_of(result)
        self.assertIn("seed.txt", paths, "unstaged tracked change missing")
        self.assertIn("staged.txt", paths, "staged change missing")
        self.assertIn("untracked.txt", paths, "untracked file missing")

    def test_non_repo_is_empty_and_does_not_raise(self):
        plain = os.path.join(self.base, "plain")
        os.makedirs(plain)
        result = _previewlib.collect_diff(plain)
        self.assertEqual(paths_of(result), set(),
                         "non-repo dir must yield no changed paths")

    def test_clean_repo_is_empty(self):
        root = self._repo("clean")
        result = _previewlib.collect_diff(root)
        self.assertEqual(paths_of(result), set(),
                         "clean repo must yield no changed paths")

    def test_default_root_uses_cwd(self):
        root = self._repo("cwd-repo")
        write(root, "untracked.txt", "x\n")
        os.chdir(root)
        result = _previewlib.collect_diff()  # no root -> cwd
        self.assertIn("untracked.txt", paths_of(result))


def findings_for(findings, rel):
    """Findings (path/line_no/snippet bearing) whose path matches `rel`,
    normalized to forward slashes. Tolerant of namedtuple, dict, or 3-tuple
    shapes so the test does not over-constrain scan_secrets' return type."""
    out = []
    for f in findings:
        if isinstance(f, dict):
            p, ln = f.get("path"), f.get("line_no")
        elif hasattr(f, "path"):
            p, ln = f.path, getattr(f, "line_no", None)
        else:  # plain tuple (path, line_no, snippet)
            p, ln = f[0], f[1]
        if p and p.replace("\\", "/") == rel:
            out.append((p.replace("\\", "/"), ln))
    return out


class ScanSecretsTest(unittest.TestCase):
    # A literal the shared SECRET_RE genuinely matches: keyword=quoted-value,
    # value length >= 4. Verified against _hooklib.SECRET_RE in setUp so the
    # test fails loudly if the regex ever drifts out from under it, rather than
    # silently asserting on a string that no longer matches.
    #
    # Deliberately an obviously-fake sentinel (not an sk-ant-shaped key) so the
    # repo's own test source never trips GitHub push-protection / secret
    # scanners, while STILL matching SECRET_RE (keyword=quoted-value, len >= 4).
    SECRET_VALUE = "DUMMY-not-a-real-key"
    SECRET_LINE = 'api_key = "%s"' % SECRET_VALUE

    def setUp(self):
        self._cwd = os.getcwd()
        self.base = tempfile.mkdtemp(prefix="ca-scansecrets-")
        # Guard: prove our sample really matches the regex we reuse.
        import _hooklib  # noqa: E402 — same sys.path mutation as _previewlib
        self.assertTrue(
            _hooklib.SECRET_RE.search(self.SECRET_LINE),
            "sample SECRET_LINE no longer matches _hooklib.SECRET_RE",
        )

    def tearDown(self):
        os.chdir(self._cwd)
        import shutil
        shutil.rmtree(self.base, ignore_errors=True)

    def _repo(self, name):
        root = os.path.join(self.base, name)
        os.makedirs(root)
        init_repo(root)
        return root

    def test_reports_changed_file_with_secret_and_line(self):
        root = self._repo("secret-repo")
        # A changed (untracked) file whose 2nd line carries the credential.
        write(root, "config.py", "clean = 1\n" + self.SECRET_LINE + "\n")
        findings = _previewlib.scan_secrets(root)
        hits = findings_for(findings, "config.py")
        self.assertTrue(hits, "secret in a changed file was not reported")
        self.assertIn(2, [ln for _, ln in hits],
                      "secret reported on the wrong line (expected line 2)")

    def test_finding_snippet_redacts_the_secret_value(self):
        # Detection must still fire, but the returned snippet must NOT echo the
        # plaintext secret value back out of the function (security review,
        # MEDIUM). Guards against silent regression of the redaction.
        root = self._repo("redact-repo")
        write(root, "config.py", "clean = 1\n" + self.SECRET_LINE + "\n")
        findings = _previewlib.scan_secrets(root)
        snippets = [
            getattr(f, "snippet", None) if hasattr(f, "snippet")
            else (f.get("snippet") if isinstance(f, dict) else f[2])
            for f in findings
            if (getattr(f, "path", None) or
                (f.get("path") if isinstance(f, dict) else f[0]))
            and (getattr(f, "path", None) or
                 (f.get("path") if isinstance(f, dict) else f[0])
                 ).replace("\\", "/") == "config.py"
        ]
        self.assertTrue(snippets, "redacted secret finding was not reported")
        for snippet in snippets:
            self.assertNotIn(
                self.SECRET_VALUE, snippet,
                "snippet leaked the plaintext secret value: %r" % snippet,
            )
            # The keyword context must survive so the preview stays useful.
            self.assertIn("api_key", snippet,
                          "redaction stripped the useful keyword context")

    def test_clean_changed_file_yields_no_finding(self):
        root = self._repo("clean-repo")
        write(root, "ok.py", "x = 1\ndef f():\n    return 2\n")
        findings = _previewlib.scan_secrets(root)
        self.assertEqual(findings_for(findings, "ok.py"), [],
                         "clean file must produce no secret finding")

    def test_unreadable_or_deleted_file_does_not_raise(self):
        root = self._repo("missing-repo")
        # Stage+commit then delete: the file is a tracked change (vs HEAD) that
        # no longer exists on disk. scan_secrets must skip it, not raise.
        write(root, "gone.txt", self.SECRET_LINE + "\n")
        git(["add", "gone.txt"], root)
        git(["commit", "-q", "-m", "add gone"], root)
        os.remove(os.path.join(root, "gone.txt"))
        # A binary blob alongside it must also be skipped without raising.
        bin_path = os.path.join(root, "blob.bin")
        with open(bin_path, "wb") as fh:
            fh.write(b"\x00\x01\x02\xff\xfe secret token here \x00")
        try:
            findings = _previewlib.scan_secrets(root)
        except Exception as e:  # noqa: BLE001
            self.fail(f"scan_secrets raised on unreadable/deleted input: {e!r}")
        self.assertEqual(findings_for(findings, "gone.txt"), [],
                         "deleted file must not be reported")

    def test_oversize_file_is_skipped(self):
        # A file larger than MAX_SCAN_BYTES is skipped without raising and never
        # scanned, even if it carries a credential line (security review, LOW —
        # size cap consistent with security-pass.py's MAX_UNTRACKED_BYTES).
        root = self._repo("oversize-repo")
        cap = _previewlib.MAX_SCAN_BYTES
        padding = "x = 1\n" * ((cap // 6) + 1)  # comfortably over the cap
        write(root, "huge.py", self.SECRET_LINE + "\n" + padding)
        self.assertGreater(
            os.path.getsize(os.path.join(root, "huge.py")), cap,
            "fixture must exceed MAX_SCAN_BYTES to exercise the cap",
        )
        findings = _previewlib.scan_secrets(root)
        self.assertEqual(findings_for(findings, "huge.py"), [],
                         "oversize file must be skipped, not scanned")

    def test_default_root_uses_cwd(self):
        root = self._repo("cwd-secret-repo")
        write(root, "creds.env", self.SECRET_LINE + "\n")
        os.chdir(root)
        findings = _previewlib.scan_secrets()  # no root -> cwd
        self.assertTrue(findings_for(findings, "creds.env"),
                        "scan_secrets() must default root to cwd")


if __name__ == "__main__":
    unittest.main(verbosity=2)

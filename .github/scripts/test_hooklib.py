#!/usr/bin/env python3
"""codeArbiter — unit tests for the shared hook helpers (_hooklib).

Direct coverage for the security-detection regexes (CRYPTO_RE, SECRET_RE) and the
path/frontmatter/marker/digest helpers that every enforcement hook routes through.
Before this suite they were exercised only indirectly via the hook integration
tests, so a regex blind spot (the 2026-06-22 checkpoint HIGH: CRYPTO_RE could not
see the Node/TS TLS-disable forms) had no direct guard.

Stdlib only. Exit 0 = all tests pass; non-zero = failure.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOOKS = os.path.join(REPO, "plugins", "ca", "hooks")
SECRET_CORPUS = os.path.join(HOOKS, "secret-detection-corpus.json")
sys.path.insert(0, HOOKS)

import _hooklib  # noqa: E402 — needs sys.path mutation above


def _sym_ok():
    """Windows CI runners often lack symlink privilege; skip symlink-dependent
    cases there (ubuntu/macos exercise them fully)."""
    try:
        with tempfile.TemporaryDirectory() as d:
            os.symlink(os.path.join(d, "t"), os.path.join(d, "l"))
        return True
    except (OSError, NotImplementedError, AttributeError):
        return False


class CryptoReTest(unittest.TestCase):
    """CRYPTO_RE drives the H-09/H-09b crypto gate. It must see the TLS-disable
    and banned-primitive forms in BOTH Python and Node/TS, since all networked
    first-party code in this repo is TS."""

    def _matches(self, s):
        return bool(_hooklib.CRYPTO_RE.search(s))

    # --- the checkpoint HIGH: Node/TS TLS-disable forms ---
    def test_matches_node_reject_unauthorized_object_form(self):
        self.assertTrue(self._matches("ssl: { rejectUnauthorized: false }"))

    def test_matches_node_reject_unauthorized_assignment_form(self):
        self.assertTrue(self._matches("opts.rejectUnauthorized = false"))

    def test_matches_node_reject_unauthorized_no_space(self):
        self.assertTrue(self._matches("rejectUnauthorized:false"))

    def test_matches_node_tls_reject_unauthorized_env(self):
        self.assertTrue(self._matches("process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0'"))

    # --- regression: existing forms still caught ---
    def test_still_matches_python_verify_false(self):
        self.assertTrue(self._matches("requests.get(url, verify=False)"))

    def test_still_matches_go_insecure_skip_verify(self):
        self.assertTrue(self._matches("InsecureSkipVerify: true"))

    def test_still_matches_banned_primitives(self):
        for s in ("createHash('md5')", "import bcrypt", "new DES()", "x509 cert"):
            self.assertTrue(self._matches(s), s)

    # --- secrets-001: RC2 and Blowfish are forbidden by security-controls.md
    #     but were absent from CRYPTO_RE, so a commit adding either passed the
    #     H-09b gate with no crypto-compliance review. ---
    def test_matches_rc2(self):
        for s in ("createCipheriv('rc2-cbc', key, iv)", "new RC2(key)"):
            self.assertTrue(self._matches(s), s)

    def test_matches_blowfish(self):
        for s in ("new Blowfish(key)", "cipher = blowfish.new(key)",
                  "algorithm: BLOWFISH"):
            self.assertTrue(self._matches(s), s)

    # --- direct coverage for every CRYPTO_RE branch (checkpoint 2026-06-22
    #     NEEDS-TRIAGE: ~18 branches were exercised only indirectly). Each string
    #     is chosen to match via its named branch only (no incidental RSA/sha1). ---
    def test_matches_each_banned_branch(self):
        cases = {
            "createCipher": "crypto.createCipher('aes', key)",
            "createHmac": "createHmac('sha256', key)",
            "sha1": "hashlib.sha1(data)",
            "rc4": "cipher = RC4(key)",
            "3des": "algorithm: 3DES",
            "RSA": "RSA.generate(2048)",
            "crypto.subtle": "crypto.subtle.digest('SHA-256', buf)",
            "crypto.sign": "crypto.sign('sha256', data, key)",
            "crypto.verify": "crypto.verify('sha256', data, key, sig)",
            "crypto.createSign": "crypto.createSign('sha256')",
            "crypto.createVerify": "crypto.createVerify('sha256')",
            "crypto.generateKey": "crypto.generateKey('aes', opts, cb)",
            "crypto.publicEncrypt": "crypto.publicEncrypt(key, buf)",
            "crypto.privateDecrypt": "crypto.privateDecrypt(key, buf)",
            "crypto.pbkdf2": "crypto.pbkdf2(pw, salt, 1000, 64, 'sha512', cb)",
            "crypto.scrypt": "crypto.scrypt(pw, salt, 64, cb)",
            "crypto.randomBytes": "crypto.randomBytes(32)",
            "crypto.createDiffieHellman": "crypto.createDiffieHellman(2048)",
        }
        for branch, s in cases.items():
            with self.subTest(branch=branch):
                self.assertTrue(self._matches(s), "%s should match: %r" % (branch, s))

    # --- narrowness: a crypto.* member NOT in the banned set must not match ---
    def test_does_not_match_unlisted_crypto_member(self):
        self.assertFalse(self._matches("crypto.timingSafeEqual(a, b)"))

    # --- the deliberate exemption must stay exempt ---
    def test_does_not_match_benign_randomness(self):
        for s in ("crypto.randomUUID()", "crypto.getRandomValues(buf)"):
            self.assertFalse(self._matches(s), s)


class SecretReTest(unittest.TestCase):
    """SECRET_RE drives the H-10/H-10b secret gate. It must catch hardcoded
    secret literals in the colon/object forms that dominate a TS/JSON repo, not
    just `key = "value"` assignments — while staying narrow enough (a quoted
    value is required) to avoid firing on every `token:` reference."""

    def _matches(self, s):
        return bool(_hooklib.SECRET_RE.search(s))

    # --- existing assignment form ---
    def test_matches_equals_assignment(self):
        self.assertTrue(self._matches('api_key = "abcd1234"'))

    # --- the checkpoint MEDIUM: colon / object-literal forms ---
    def test_matches_json_object_key(self):
        self.assertTrue(self._matches('"api_key": "sk-test-abcd1234"'))

    def test_matches_ts_object_key(self):
        self.assertTrue(self._matches('apiKey: "longsecretvalue"'))

    def test_matches_aws_secret_keyword(self):
        self.assertTrue(self._matches('aws_secret_access_key = "wJalrXUtnFEMI1234"'))

    # --- secrets-002: compound names like FARM_API_KEY. The leading `\b` on the
    #     keyword alternation did NOT fire before `api_key` when the char to its
    #     left is a word char (the `_` in FARM_API_KEY), so a hardcoded
    #     `FARM_API_KEY = "..."` silently passed the H-10b secret gate. ---
    def test_matches_compound_name_underscore_prefix(self):
        self.assertTrue(self._matches('const FARM_API_KEY = "sk-CVlQvxKsecretvalue123";'))

    def test_matches_compound_name_object_form(self):
        self.assertTrue(self._matches('MY_SECRET: "longsecretvalue123"'))

    # --- known high-entropy key prefixes (keyword-independent) ---
    def test_matches_aws_access_key_id_prefix(self):
        self.assertTrue(self._matches("AKIAIOSFODNN7EXAMPLE"))

    def test_matches_github_pat_prefix(self):
        self.assertTrue(self._matches("ghp_abcdefghijklmnopqrstuvwxyz0123456789"))

    def test_matches_anthropic_key_prefix(self):
        self.assertTrue(self._matches("sk-ant-api03-AbCdEf1234567890abcdef"))

    # --- narrowness: no quoted value -> no match (avoid false-positive storms) ---
    def test_does_not_match_unquoted_reference(self):
        self.assertFalse(self._matches("token: someConfigVariable"))

    def test_does_not_match_prose_mention(self):
        self.assertFalse(self._matches("# load the secret from the env store"))


class SecretCorpusTest(unittest.TestCase):
    """architecture-001: the SECRET_RE commit gate and farm.ts's SECRET_LINE
    outbound redactor are deliberately distinct in shape, but must never drift
    apart on the AGREEMENT region — real secret shapes both must flag, and benign
    lines both must pass. This pins the Python (SECRET_RE) side of that shared
    corpus; plugins/ca/tools/farm.unit.test.ts pins the TS (SECRET_LINE) side
    against the SAME file, so a divergence on any entry fails CI on one side."""

    @classmethod
    def setUpClass(cls):
        with open(SECRET_CORPUS, encoding="utf-8") as f:
            cls.corpus = json.load(f)

    def _matches(self, s):
        return bool(_hooklib.SECRET_RE.search(s))

    def test_corpus_has_both_sets(self):
        self.assertTrue(self.corpus.get("must_match"), "corpus must_match is empty")
        self.assertTrue(self.corpus.get("must_not_match"), "corpus must_not_match is empty")

    def test_secret_re_flags_every_must_match(self):
        for s in self.corpus["must_match"]:
            with self.subTest(line=s):
                self.assertTrue(self._matches(s),
                                "SECRET_RE must flag corpus secret: %r" % s)

    def test_secret_re_passes_every_must_not_match(self):
        for s in self.corpus["must_not_match"]:
            with self.subTest(line=s):
                self.assertFalse(self._matches(s),
                                 "SECRET_RE must NOT flag benign corpus line: %r" % s)


class AuditPathHelperTest(unittest.TestCase):
    """architecture-004: the append-only-log and ADR-decisions path sets were
    triplicated inline across pre-write/pre-edit/pre-bash. They now live once in
    _hooklib (the same home as CRYPTO_RE/SECRET_RE/MIGRATION globs) so adding an
    audit artifact touches one file. These pin the centralized API + its scope."""

    def test_is_audit_log_matches_the_three_append_only_files(self):
        for rel in (".codearbiter/overrides.log",
                    ".codearbiter/triage.log",
                    ".codearbiter/sprint-log.md"):
            with self.subTest(rel=rel):
                self.assertTrue(_hooklib.is_audit_log(rel), rel)

    def test_is_audit_log_normalizes_windows_separators(self):
        self.assertTrue(_hooklib.is_audit_log(".codearbiter\\overrides.log"))

    def test_is_audit_log_rejects_non_audit_paths(self):
        for rel in (".codearbiter/CONTEXT.md", "src/overrides.log.bak",
                    ".codearbiter/open-tasks.md"):
            with self.subTest(rel=rel):
                self.assertFalse(_hooklib.is_audit_log(rel), rel)

    def test_is_decisions_path_matches_adrs(self):
        for rel in (".codearbiter/decisions/0001-seed.md",
                    ".codearbiter/decisions/draft.md",
                    ".codearbiter/decisions/sub/0002-x.md"):
            with self.subTest(rel=rel):
                self.assertTrue(_hooklib.is_decisions_path(rel), rel)

    def test_is_decisions_path_normalizes_windows_separators(self):
        self.assertTrue(_hooklib.is_decisions_path(".codearbiter\\decisions\\0001-x.md"))

    def test_is_decisions_path_rejects_non_decisions(self):
        for rel in (".codearbiter/CONTEXT.md", "src/decisions/x.md"):
            with self.subTest(rel=rel):
                self.assertFalse(_hooklib.is_decisions_path(rel), rel)


class PathGlobTest(unittest.TestCase):
    """is_migration_path / is_ci_path / is_deploy_path against default globs
    (no security-controls.md in the tmp root, so defaults only)."""

    def setUp(self):
        self._root = tempfile.mkdtemp()

    def test_migration_default_globs(self):
        self.assertTrue(_hooklib.is_migration_path("db/migrate/001_init.rb", self._root))
        self.assertTrue(_hooklib.is_migration_path("app/prisma/migrations/x/migration.sql", self._root))
        self.assertFalse(_hooklib.is_migration_path("src/app.ts", self._root))

    def test_ci_default_globs(self):
        self.assertTrue(_hooklib.is_ci_path(".github/workflows/ci.yml", self._root))
        self.assertFalse(_hooklib.is_ci_path("src/index.ts", self._root))

    def test_deploy_default_globs(self):
        self.assertTrue(_hooklib.is_deploy_path("Dockerfile", self._root))
        self.assertTrue(_hooklib.is_deploy_path("infra/k8s/deploy.yaml", self._root))
        self.assertFalse(_hooklib.is_deploy_path("README.md", self._root))

    def test_windows_backslash_path_normalizes(self):
        self.assertTrue(_hooklib.is_ci_path(".github\\workflows\\ci.yml", self._root))


def _write_controls(root, content):
    """Write content to .codearbiter/security-controls.md in root."""
    ca_dir = os.path.join(root, ".codearbiter")
    os.makedirs(ca_dir, exist_ok=True)
    with open(os.path.join(ca_dir, "security-controls.md"), "w", encoding="utf-8") as f:
        f.write(content)


class CiPathCustomGlobTest(unittest.TestCase):
    """scope_globs + is_ci_path with a <!-- ci-paths --> declaration block in
    security-controls.md — mirrors OB-02/OB-03 from test_migration_backstop.py."""

    def setUp(self):
        self._root = tempfile.mkdtemp()

    def test_ci_paths_extend_matches_custom_path(self):
        """A `+ glob` in <!-- ci-paths --> makes a non-default path detected."""
        _write_controls(self._root,
                        "# sc\n<!-- ci-paths -->\n+ custom/ci/**\n<!-- /ci-paths -->\n")
        self.assertTrue(_hooklib.is_ci_path("custom/ci/pipeline.yml", self._root))

    def test_ci_paths_extend_does_not_break_defaults(self):
        """Extending must not suppress the default globs."""
        _write_controls(self._root,
                        "# sc\n<!-- ci-paths -->\n+ custom/ci/**\n<!-- /ci-paths -->\n")
        self.assertTrue(_hooklib.is_ci_path(".github/workflows/ci.yml", self._root))

    def test_ci_paths_exclude_narrows_detection(self):
        """A `- glob` in <!-- ci-paths --> drops a path that would otherwise match."""
        _write_controls(self._root,
                        "# sc\n<!-- ci-paths -->\n- .circleci/**\n<!-- /ci-paths -->\n")
        self.assertFalse(_hooklib.is_ci_path(".circleci/config.yml", self._root))

    def test_ci_paths_exclude_does_not_over_suppress(self):
        """An exclude on one glob must leave other default globs intact."""
        _write_controls(self._root,
                        "# sc\n<!-- ci-paths -->\n- .circleci/**\n<!-- /ci-paths -->\n")
        self.assertTrue(_hooklib.is_ci_path(".github/workflows/ci.yml", self._root))


class DeployPathCustomGlobTest(unittest.TestCase):
    """scope_globs + is_deploy_path with a <!-- deploy-paths --> declaration block
    in security-controls.md — mirrors OB-02/OB-03 from test_migration_backstop.py."""

    def setUp(self):
        self._root = tempfile.mkdtemp()

    def test_deploy_paths_extend_matches_custom_path(self):
        """A `+ glob` in <!-- deploy-paths --> makes a non-default path detected."""
        _write_controls(self._root,
                        "# sc\n<!-- deploy-paths -->\n+ deploy/scripts/**\n<!-- /deploy-paths -->\n")
        self.assertTrue(_hooklib.is_deploy_path("deploy/scripts/rollout.sh", self._root))

    def test_deploy_paths_extend_does_not_break_defaults(self):
        """Extending must not suppress the default globs."""
        _write_controls(self._root,
                        "# sc\n<!-- deploy-paths -->\n+ deploy/scripts/**\n<!-- /deploy-paths -->\n")
        self.assertTrue(_hooklib.is_deploy_path("Dockerfile", self._root))

    def test_deploy_paths_exclude_narrows_detection(self):
        """A `- glob` in <!-- deploy-paths --> drops a path that would otherwise match."""
        _write_controls(self._root,
                        "# sc\n<!-- deploy-paths -->\n- **/Procfile\n<!-- /deploy-paths -->\n")
        self.assertFalse(_hooklib.is_deploy_path("Procfile", self._root))

    def test_deploy_paths_exclude_does_not_over_suppress(self):
        """An exclude on one glob must leave other default globs intact."""
        _write_controls(self._root,
                        "# sc\n<!-- deploy-paths -->\n- **/Procfile\n<!-- /deploy-paths -->\n")
        self.assertTrue(_hooklib.is_deploy_path("Dockerfile", self._root))


class ControlsCacheTest(unittest.TestCase):
    """performance-001/002: _read_controls is process-cached keyed by
    (root, mtime) of security-controls.md, and the cache is mtime-invalidated so
    an intra-process change to the file takes effect. ZERO behaviour change to
    scope verdicts is the hard constraint — these tests pin both the cache hit
    (no re-read) and the cache-bust (mtime change re-reads)."""

    def setUp(self):
        self._root = tempfile.mkdtemp()

    def test_read_controls_returns_same_text_within_process(self):
        _write_controls(self._root, "# sc\nhello\n")
        first = _hooklib._read_controls(self._root)
        second = _hooklib._read_controls(self._root)
        self.assertEqual(first, second)
        self.assertEqual(first, "# sc\nhello\n")

    def test_cache_invalidated_on_mtime_change(self):
        """Changing the controls content AND mtime between two scope checks must
        make the new scope take effect — the cache is mtime-keyed, not permanent.
        custom/ci/** is not a default CI path, so detection flips only if the
        re-written controls file is actually re-read."""
        _write_controls(self._root, "# sc\n")
        self.assertFalse(_hooklib.is_ci_path("custom/ci/pipeline.yml", self._root))

        # Rewrite with a ci-paths extend block and bump the mtime forward so the
        # (root, mtime) cache key changes even on coarse-resolution filesystems.
        controls = os.path.join(self._root, ".codearbiter", "security-controls.md")
        _write_controls(self._root,
                        "# sc\n<!-- ci-paths -->\n+ custom/ci/**\n<!-- /ci-paths -->\n")
        future = os.path.getmtime(controls) + 10
        os.utime(controls, (future, future))

        self.assertTrue(_hooklib.is_ci_path("custom/ci/pipeline.yml", self._root))

    def test_cache_invalidated_when_controls_file_created(self):
        """Going from no-controls (defaults only) to a controls file with an
        exclude must take effect — the absent-file cache state must not pin."""
        self.assertTrue(_hooklib.is_ci_path(".circleci/config.yml", self._root))
        _write_controls(self._root,
                        "# sc\n<!-- ci-paths -->\n- .circleci/**\n<!-- /ci-paths -->\n")
        self.assertFalse(_hooklib.is_ci_path(".circleci/config.yml", self._root))


class DefaultGlobPrecompileTest(unittest.TestCase):
    """performance-002: the default glob sets are pre-compiled to regex once at
    module load. Verdicts for default-glob paths must be unchanged, and the
    module-level compiled tuples must exist and line up 1:1 with their string
    tuples."""

    def setUp(self):
        self._root = tempfile.mkdtemp()

    def test_compiled_default_tuples_exist_and_align(self):
        for strings, compiled in (
            (_hooklib.MIGRATION_DEFAULT_GLOBS, _hooklib._MIGRATION_DEFAULT_RES),
            (_hooklib.CI_DEFAULT_GLOBS, _hooklib._CI_DEFAULT_RES),
            (_hooklib.DEPLOY_DEFAULT_GLOBS, _hooklib._DEPLOY_DEFAULT_RES),
        ):
            self.assertEqual(len(strings), len(compiled))
            for r in compiled:
                self.assertTrue(hasattr(r, "match"))

    def test_default_ci_path_still_detected(self):
        self.assertTrue(_hooklib.is_ci_path(".github/workflows/x.yml", self._root))

    def test_default_migration_path_still_detected(self):
        self.assertTrue(_hooklib.is_migration_path("db/migrate/001_init.rb", self._root))

    def test_default_deploy_path_still_detected(self):
        self.assertTrue(_hooklib.is_deploy_path("Dockerfile", self._root))

    def test_default_non_matches_still_negative(self):
        self.assertFalse(_hooklib.is_ci_path("src/index.ts", self._root))
        self.assertFalse(_hooklib.is_migration_path("src/app.ts", self._root))
        self.assertFalse(_hooklib.is_deploy_path("README.md", self._root))


class FrontmatterTest(unittest.TestCase):
    """frontmatter_enabled: enabled / malformed / dormant."""

    def _write(self, text):
        fd, path = tempfile.mkstemp(suffix=".md")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_enabled_when_closed_block_has_marker(self):
        p = self._write("---\narbiter: enabled\nstage: 2\n---\n# body\n")
        self.assertEqual(_hooklib.frontmatter_enabled(p), (True, False))

    def test_malformed_when_block_never_closes(self):
        p = self._write("---\narbiter: enabled\nno closing delimiter\n")
        self.assertEqual(_hooklib.frontmatter_enabled(p), (False, True))

    def test_dormant_when_no_frontmatter(self):
        p = self._write("# just a heading, no frontmatter\n")
        self.assertEqual(_hooklib.frontmatter_enabled(p), (False, False))


class WriteAtomicTest(unittest.TestCase):
    """migration-002: write_text_atomic writes via a sibling temp file then
    os.replace() so a crash mid-write never leaves a half-written file at the
    destination — the marker writers (migration-pass/security-pass) rely on this
    so a partial digest set can't force a spurious gate re-run. ZERO behaviour
    change on the happy path is the constraint."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()

    def test_creates_file_with_exact_content(self):
        p = os.path.join(self._tmp, "marker")
        _hooklib.write_text_atomic(p, "a\nb\n")
        with open(p, encoding="utf-8") as f:
            self.assertEqual(f.read(), "a\nb\n")

    def test_overwrites_existing_atomically(self):
        p = os.path.join(self._tmp, "marker")
        _hooklib.write_text_atomic(p, "old\n")
        _hooklib.write_text_atomic(p, "new\n")
        with open(p, encoding="utf-8") as f:
            self.assertEqual(f.read(), "new\n")

    def test_replace_failure_leaves_original_intact_and_no_tmp(self):
        """If os.replace raises (the crash-equivalent), the destination keeps its
        PRIOR content (never truncated) and no stray .tmp is left behind."""
        p = os.path.join(self._tmp, "marker")
        _hooklib.write_text_atomic(p, "original\n")
        with mock.patch("os.replace", side_effect=OSError("simulated crash")):
            with self.assertRaises(OSError):
                _hooklib.write_text_atomic(p, "corrupt-partial")
        with open(p, encoding="utf-8") as f:
            self.assertEqual(f.read(), "original\n", "destination must not be truncated")
        leftovers = [n for n in os.listdir(self._tmp) if n != "marker"]
        self.assertEqual(leftovers, [], f"no temp file should linger: {leftovers}")


class MarkerDigestTest(unittest.TestCase):
    """marker_fresh + line_digest/content_digest."""

    def test_marker_fresh_true_for_new_file(self):
        fd, path = tempfile.mkstemp()
        os.close(fd)
        self.assertTrue(_hooklib.marker_fresh(path, minutes=30))

    def test_marker_fresh_false_when_absent(self):
        self.assertFalse(_hooklib.marker_fresh("/no/such/marker", minutes=30))

    def test_line_digest_ignores_trailing_whitespace(self):
        self.assertEqual(_hooklib.line_digest("x = 1"), _hooklib.line_digest("x = 1   "))

    def test_content_digest_ignores_trailing_ws(self):
        self.assertEqual(
            _hooklib.content_digest("a\nb\n"),
            _hooklib.content_digest("a  \nb  \n"),
        )

    def test_content_digest_ignores_crlf(self):
        self.assertEqual(
            _hooklib.content_digest("a\nb\n"),
            _hooklib.content_digest("a\r\nb\r\n"),
        )

    def test_content_digest_differs_on_real_change(self):
        self.assertNotEqual(_hooklib.content_digest("a\nb\n"), _hooklib.content_digest("a\nc\n"))


class ActivationAndMarkerHelpersTest(unittest.TestCase):
    """#159/#160/#162 path classifiers and the text-based frontmatter check."""

    def test_is_context_md(self):
        self.assertTrue(_hooklib.is_context_md(".codearbiter/CONTEXT.md"))
        self.assertTrue(_hooklib.is_context_md("/a/b/.codearbiter/CONTEXT.md"))
        self.assertTrue(_hooklib.is_context_md(r".codearbiter\CONTEXT.md"))
        self.assertFalse(_hooklib.is_context_md(".codearbiter/other.md"))
        self.assertFalse(_hooklib.is_context_md("CONTEXT.md"))

    def test_is_marker_path(self):
        self.assertTrue(_hooklib.is_marker_path(".codearbiter/.markers/security-gate-passed"))
        self.assertTrue(_hooklib.is_marker_path("x/.codearbiter/.markers/adr-authoring-active"))
        self.assertFalse(_hooklib.is_marker_path(".codearbiter/CONTEXT.md"))
        self.assertFalse(_hooklib.is_marker_path(".codearbiter/markers/x"))  # no dot

    def test_frontmatter_enabled_text(self):
        self.assertEqual(_hooklib.frontmatter_enabled_text("---\narbiter: enabled\n---\n"),
                         (True, False))
        self.assertEqual(_hooklib.frontmatter_enabled_text("---\narbiter: disabled\n---\n"),
                         (False, False))
        # opened, never closed -> malformed
        self.assertEqual(_hooklib.frontmatter_enabled_text("---\narbiter: enabled\n"),
                         (False, True))
        # no frontmatter at all -> dormant, not malformed
        self.assertEqual(_hooklib.frontmatter_enabled_text("# ctx\n"), (False, False))

    @unittest.skipUnless(_sym_ok(), "symlink creation not permitted here")
    def test_classify_protected_resolves_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            ca = os.path.join(d, ".codearbiter")
            os.makedirs(ca)
            with open(os.path.join(ca, "overrides.log"), "w") as f:
                f.write("x")
            os.symlink(ca, os.path.join(d, "alias"))
            # raw path lacks .codearbiter/, but realpath resolves inside it.
            hits = _hooklib.classify_protected(os.path.join(d, "alias", "overrides.log"), d)
            self.assertIn("audit", hits)


class DiffAddedLinesTest(unittest.TestCase):
    """#279 review (three rounds): `diff_added_lines` must attribute added
    lines to the correct file using ONLY:
      (1) a bare `diff ` section header (`--git`/`--cc`/`--combined`) to mark
          a NEW section and reset attribution to None (content can't forge an
          unprefixed line at column 0) — never inheriting the PREVIOUS
          section's path (round 3, MEDIUM-2: combined/merge diffs);
      (2) within that section's PREAMBLE (before its first `@@`), a `+++
          b/<path>` line, read via a FIXED 6-character prefix strip — never a
          regex search for a separator, which is ambiguous when the path
          itself contains " b/" (round 3, HIGH) — and never trusted once
          INSIDE the hunk body, where an identical-looking string is content,
          not a header (round 2)."""

    def _one_file_diff(self, path, added_lines, removed_lines=()):
        lines = [
            f"diff --git a/{path} b/{path}",
            "index 1111111..2222222 100644",
            f"--- a/{path}",
            f"+++ b/{path}",
            "@@ -1,1 +1,2 @@",
        ]
        for ln in removed_lines:
            lines.append("-" + ln)
        for ln in added_lines:
            lines.append("+" + ln)
        return "\n".join(lines) + "\n"

    def test_simple_single_file_diff(self):
        diff = self._one_file_diff("src/app.py", ["print('hi')"])
        self.assertEqual(_hooklib.diff_added_lines(diff),
                          [("src/app.py", "print('hi')")])

    def test_multi_file_diff_attributes_each_hunk(self):
        diff = (self._one_file_diff("a.py", ["line a"]) +
                self._one_file_diff("b.py", ["line b"]))
        self.assertEqual(_hooklib.diff_added_lines(diff),
                          [("a.py", "line a"), ("b.py", "line b")])

    def test_forged_plusplusplus_header_does_not_hijack_attribution(self):
        # A genuine source file adds a line whose CONTENT is the text
        # "++ b/.codearbiter/gate-events.log" — in real `git diff` output this
        # renders as "+++ b/.codearbiter/gate-events.log" (one '+' prefix +
        # the two-'+' content), byte-identical to a real hunk header. Every
        # added line must still attribute to the REAL file (src/auth.js), not
        # get silently reassigned to gate-events.log.
        diff = self._one_file_diff(
            "src/auth.js",
            [
                "++ b/.codearbiter/gate-events.log",
                "const h = createHash('md5');",
            ],
        )
        result = _hooklib.diff_added_lines(diff)
        self.assertEqual(len(result), 2)
        for path, _line in result:
            self.assertEqual(path, "src/auth.js")

    def test_forged_full_plusplusplus_content_line(self):
        # Same shape, but the forged content line is itself "+++ b/<path>"
        # (three literal plus signs in the source) — renders in the diff as
        # "++++ b/<path>", which must ALSO never be mistaken for the header
        # (the header line is never `+`-prefixed at all).
        diff = self._one_file_diff(
            "src/auth.js",
            [
                "+++ b/.codearbiter/gate-events.log",
                "const h = createHash('md5');",
            ],
        )
        result = _hooklib.diff_added_lines(diff)
        self.assertEqual(len(result), 2)
        for path, _line in result:
            self.assertEqual(path, "src/auth.js")

    def test_ambiguous_diff_git_path_does_not_hijack_attribution(self):
        # #279 review HIGH: a real repo file named "x b/.codearbiter/
        # gate-events.log" renders its `diff --git` header as
        #   diff --git a/x b/.codearbiter/gate-events.log b/x b/.codearbiter/gate-events.log
        # A greedy regex parse of that line resolves group(1) to
        # ".codearbiter/gate-events.log" (the LAST " b/" split), exempting the
        # whole unrelated source file. The fix must NOT parse `diff --git` for
        # the path at all — attribution comes only from the fixed-prefix
        # `+++ b/<path>` strip, which is unambiguous no matter what the path
        # contains.
        odd_path = "x b/.codearbiter/gate-events.log"
        diff = (
            f"diff --git a/{odd_path} b/{odd_path}\n"
            "index 1111111..2222222 100644\n"
            f"--- a/{odd_path}\n"
            f"+++ b/{odd_path}\n"
            "@@ -1,1 +1,2 @@\n"
            " context\n"
            "+const h = createHash('md5');\n"
            '+api_key="abcd1234efgh"\n'
        )
        result = _hooklib.diff_added_lines(diff)
        self.assertEqual(len(result), 2, f"expected 2 added lines, got {result!r}")
        for path, _line in result:
            self.assertEqual(path, odd_path,
                              f"lines must attribute to the REAL path {odd_path!r}, "
                              f"not the exempt log; got {path!r}")
        # And the sensitive-scan-exempt check on that real path must be False
        # (it is a source file, not the audit log itself).
        self.assertFalse(_hooklib.is_sensitive_scan_exempt(odd_path))

    def test_combined_diff_cc_section_does_not_inherit_prior_path(self):
        # #279 review MEDIUM-2: a merge commit's `git diff --cached` can emit
        # `diff --cc <path>` combined-diff sections. If attribution resets
        # only on `diff --git` (not on `diff --cc`), a `--cc` section that
        # follows an exempt gate-events.log section would silently inherit
        # that path and its added lines would be dropped from the scan — the
        # dangerous (exempting) direction. Attribution must reset to None on
        # ANY `diff ` header and pick up the `--cc` section's OWN `+++
        # b/<path>` line.
        diff = (
            "diff --git a/.codearbiter/gate-events.log b/.codearbiter/gate-events.log\n"
            "index 1111111..2222222 100644\n"
            "--- a/.codearbiter/gate-events.log\n"
            "+++ b/.codearbiter/gate-events.log\n"
            "@@ -1,0 +1,1 @@\n"
            "+REMIND: no MD5/SHA1/DES/3DES/RC2/RC4/Blowfish\n"
            "diff --cc src/evil.py\n"
            "index 1111111,3333333..4444444\n"
            "--- a/src/evil.py\n"
            "+++ b/src/evil.py\n"
            "@@@ -1,2 -1,2 +1,3 @@@\n"
            "  context\n"
            "+const h = createHash('md5');\n"
        )
        result = _hooklib.diff_added_lines(diff)
        evil_lines = [ln for path, ln in result if path == "src/evil.py"]
        self.assertTrue(any("createHash" in ln for ln in evil_lines),
                         f"the --cc section's crypto line must attribute to "
                         f"src/evil.py, not inherit gate-events.log; got {result!r}")
        gate_events_lines = [ln for path, ln in result
                             if path == ".codearbiter/gate-events.log"]
        self.assertEqual(len(gate_events_lines), 1)

    def test_unattributed_line_is_not_silently_dropped(self):
        # A stray '+' line before any `diff --git` header (not producible by
        # real git output) attributes to path=None, not to a guess.
        diff = "+orphan added line\n"
        self.assertEqual(_hooklib.diff_added_lines(diff), [(None, "orphan added line")])

    def test_dev_null_destination_has_no_added_lines(self):
        # A deleted file's diff only has removed lines; nothing to attribute.
        diff = self._one_file_diff("gone.py", [], removed_lines=["bye"])
        self.assertEqual(_hooklib.diff_added_lines(diff), [])


class SensitiveScanAddedLinesTest(unittest.TestCase):
    """#279: sensitive_scan_added_lines applies the gate-events.log exemption
    using diff_added_lines' unspoofable attribution."""

    def test_gate_events_log_lines_excluded(self):
        diff = (
            "diff --git a/.codearbiter/gate-events.log b/.codearbiter/gate-events.log\n"
            "index 1111111..2222222 100644\n"
            "--- a/.codearbiter/gate-events.log\n"
            "+++ b/.codearbiter/gate-events.log\n"
            "@@ -1,0 +1,1 @@\n"
            "+REMIND: no MD5/SHA1/DES/3DES/RC2/RC4/Blowfish\n"
        )
        self.assertEqual(_hooklib.sensitive_scan_added_lines(diff), [])

    def test_forged_header_line_does_not_exempt_real_source(self):
        diff = (
            "diff --git a/src/auth.js b/src/auth.js\n"
            "index 1111111..2222222 100644\n"
            "--- a/src/auth.js\n"
            "+++ b/src/auth.js\n"
            "@@ -1,1 +1,3 @@\n"
            "+++ b/.codearbiter/gate-events.log\n"
            "+const h = createHash('md5');\n"
        )
        result = _hooklib.sensitive_scan_added_lines(diff)
        self.assertTrue(any("createHash" in ln for ln in result),
                         f"the real crypto line must still be scanned, got {result!r}")

    def test_other_audit_logs_stay_in_scope(self):
        diff = (
            "diff --git a/.codearbiter/overrides.log b/.codearbiter/overrides.log\n"
            "index 1111111..2222222 100644\n"
            "--- a/.codearbiter/overrides.log\n"
            "+++ b/.codearbiter/overrides.log\n"
            "@@ -1,0 +1,1 @@\n"
            '+api_key="abcd1234efgh"\n'
        )
        result = _hooklib.sensitive_scan_added_lines(diff)
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

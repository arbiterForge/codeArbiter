#!/usr/bin/env python3
"""codeArbiter — unit tests for the shared hook helpers (_hooklib).

Direct coverage for the security-detection regexes (CRYPTO_RE, SECRET_RE) and the
path/frontmatter/marker/digest helpers that every enforcement hook routes through.
Before this suite they were exercised only indirectly via the hook integration
tests, so a regex blind spot (the 2026-06-22 checkpoint HIGH: CRYPTO_RE could not
see the Node/TS TLS-disable forms) had no direct guard.

Stdlib only. Exit 0 = all tests pass; non-zero = failure.
"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOOKS = os.path.join(REPO, "plugins", "ca", "hooks")
sys.path.insert(0, HOOKS)

import _hooklib  # noqa: E402 — needs sys.path mutation above


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


if __name__ == "__main__":
    unittest.main(verbosity=2)

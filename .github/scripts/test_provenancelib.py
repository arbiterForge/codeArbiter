#!/usr/bin/env python3
"""codeArbiter — unit tests for the provenance-store helper (_provenancelib).

Proves the write_provenance / read_provenance round-trip and the canonical
record shape, per spec `.codearbiter/specs/context-drift-provenance.md`:

  AC-01  write_provenance then read_provenance round-trips an equal record;
         on-disk file is valid JSON with schema/doc/created/interview_derived/
         entries[]

  AC-02  batch_hash(paths, runner) issues a single git hash-object --stdin-paths
         call (asserted via an injected runner) and returns {path: oid}
         preserving input order.

Stdlib only. Exit 0 = all tests pass; non-zero = failure.
"""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOOKS = os.path.join(REPO, "plugins", "ca", "hooks")
sys.path.insert(0, HOOKS)

import _provenancelib as pl  # noqa: E402 — needs sys.path mutation above


class RoundTripTest(unittest.TestCase):
    """AC-01: write_provenance + read_provenance round-trip with a full record."""

    def test_round_trip(self):
        record = pl.new_record(
            "tech-stack",
            created="2026-06-26",
            interview_derived=False,
            entries=[
                {
                    "path": "plugins/ca/tools/package.json",
                    "hash": "abc1234def5678901234567890abcdef12345678",
                    "drift_trigger": True,
                    "claims": [
                        {
                            "lines": "1-10",
                            "claim": "Node 20 runtime declared in package.json",
                            "confidence": "strong",
                        }
                    ],
                }
            ],
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(
                tmp, ".codearbiter", ".provenance", "tech-stack.json"
            )
            # write_provenance must create the parent directory
            pl.write_provenance(path, record)
            loaded = pl.read_provenance(path)

            # The round-tripped record must equal the original.
            self.assertEqual(loaded, record)

            # The on-disk file must be valid JSON (json.load) carrying all five
            # required keys.
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            for key in ("schema", "doc", "created", "interview_derived", "entries"):
                self.assertIn(
                    key, raw, f"required key {key!r} missing from on-disk JSON"
                )


class WriteProvenanceAtomicTest(unittest.TestCase):
    """reliability-016: write_provenance is routed through the temp-file +
    os.replace atomic-write pattern, so a crash mid-write never truncates or
    corrupts a previously-written provenance record."""

    def test_crash_mid_write_leaves_previous_record_intact(self):
        from unittest.mock import patch

        record_v1 = pl.new_record("tech-stack", created="2026-06-26")
        record_v2 = pl.new_record("tech-stack", created="2026-07-01")

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, ".codearbiter", ".provenance", "tech-stack.json")
            pl.write_provenance(path, record_v1)
            self.assertEqual(pl.read_provenance(path), record_v1)

            # Simulate a crash between the temp-file write and the atomic
            # rename (the exact window write_text_atomic exists to close).
            with patch("os.replace", side_effect=OSError("simulated crash")):
                with self.assertRaises(OSError):
                    pl.write_provenance(path, record_v2)

            # The destination must still hold the PRIOR, complete record —
            # never truncated, never partially overwritten.
            self.assertEqual(pl.read_provenance(path), record_v1)

            # No stray .tmp file should linger in the provenance directory.
            leftovers = [
                n for n in os.listdir(os.path.dirname(path)) if n != "tech-stack.json"
            ]
            self.assertEqual(leftovers, [], f"no temp file should linger: {leftovers}")

    def test_crash_during_json_serialization_leaves_previous_record_intact(self):
        """A crash while dumping JSON (before the atomic write even starts)
        must also never touch the previously-written file."""
        from unittest.mock import patch

        record_v1 = pl.new_record("tech-stack", created="2026-06-26")

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, ".codearbiter", ".provenance", "tech-stack.json")
            pl.write_provenance(path, record_v1)
            self.assertEqual(pl.read_provenance(path), record_v1)

            with patch("json.dumps", side_effect=ValueError("simulated crash")):
                with self.assertRaises(ValueError):
                    pl.write_provenance(path, pl.new_record("tech-stack", created="2026-07-01"))

            self.assertEqual(pl.read_provenance(path), record_v1)


class BatchHashTest(unittest.TestCase):
    """AC-02: batch_hash issues a single git hash-object --stdin-paths call, order-preserving."""

    def _make_runner(self, oids):
        """Return (runner, call_log). runner records every call and returns oids joined."""
        call_log = []

        def fake_runner(args, stdin_text):
            call_log.append({"args": list(args), "stdin": stdin_text})
            return "\n".join(oids) + "\n"

        return fake_runner, call_log

    def test_batch_hash_single_call(self):
        """Runner is called exactly once; returned dict maps paths→oids in input order."""
        paths = ["a.py", "b.py", "c.py"]
        oids = [
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "cccccccccccccccccccccccccccccccccccccccc",
        ]
        runner, call_log = self._make_runner(oids)

        result = pl.batch_hash(paths, runner)

        # Runner called exactly once — the heart of AC-02
        self.assertEqual(len(call_log), 1, "runner must be called exactly once")

        # Runner received the correct git subcommand
        self.assertEqual(
            call_log[0]["args"],
            ["hash-object", "--stdin-paths"],
            "runner must receive ['hash-object', '--stdin-paths']",
        )

        # All paths were on stdin, newline-joined with a trailing newline
        self.assertEqual(
            call_log[0]["stdin"],
            "a.py\nb.py\nc.py\n",
            "runner stdin must be paths newline-joined with trailing newline",
        )

        # Result maps each path to its oid
        self.assertEqual(
            result,
            {"a.py": oids[0], "b.py": oids[1], "c.py": oids[2]},
        )

        # Order preserved: keys must match input order
        self.assertEqual(list(result.keys()), paths)

    def test_batch_hash_empty_paths(self):
        """Empty paths list → {} with zero runner calls."""
        call_count = []

        def counting_runner(args, stdin_text):
            call_count.append(1)
            return ""

        result = pl.batch_hash([], counting_runner)
        self.assertEqual(result, {})
        self.assertEqual(len(call_count), 0, "runner must not be called for empty paths")

    def test_batch_hash_runner_raises(self):
        """Runner that raises must not propagate — batch_hash returns {} gracefully."""
        def bad_runner(args, stdin_text):
            raise RuntimeError("git not found")

        result = pl.batch_hash(["a.py", "b.py"], bad_runner)
        # Must not raise; degrades to {}
        self.assertIsInstance(result, dict)

    def test_batch_hash_fewer_oids_than_paths(self):
        """Runner returning fewer oids than paths must not crash (safely-zippable subset)."""
        paths = ["a.py", "b.py", "c.py"]
        short_oid = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

        def short_runner(args, stdin_text):
            return short_oid + "\n"  # only one oid for three paths

        # Must not raise; result is the zippable subset (at most len(short oids) entries)
        result = pl.batch_hash(paths, short_runner)
        self.assertIsInstance(result, dict)
        self.assertLessEqual(len(result), len(paths))

    def test_batch_hash_single_path(self):
        """Single path: one call, dict with one entry, correct stdin."""
        paths = ["README.md"]
        oid = "dddddddddddddddddddddddddddddddddddddddd"
        runner, call_log = self._make_runner([oid])

        result = pl.batch_hash(paths, runner)

        self.assertEqual(len(call_log), 1)
        self.assertEqual(call_log[0]["stdin"], "README.md\n")
        self.assertEqual(result, {"README.md": oid})


class ClassifySourceTest(unittest.TestCase):
    """AC-10: classify_source(path) -> True for config/manifest/schema/security-entry, False for general source."""

    # --- True: package manifests ---

    def test_classify_source_package_json(self):
        self.assertTrue(pl.classify_source("package.json"))

    def test_classify_source_package_lock_json(self):
        self.assertTrue(pl.classify_source("package-lock.json"))

    def test_classify_source_pyproject_toml(self):
        self.assertTrue(pl.classify_source("pyproject.toml"))

    def test_classify_source_go_mod(self):
        self.assertTrue(pl.classify_source("go.mod"))

    def test_classify_source_cargo_toml(self):
        self.assertTrue(pl.classify_source("Cargo.toml"))

    def test_classify_source_gemfile(self):
        self.assertTrue(pl.classify_source("Gemfile"))

    def test_classify_source_gemfile_lock(self):
        self.assertTrue(pl.classify_source("Gemfile.lock"))

    # --- True: lockfiles ---

    def test_classify_source_yarn_lock(self):
        self.assertTrue(pl.classify_source("yarn.lock"))

    def test_classify_source_pnpm_lock_yaml(self):
        self.assertTrue(pl.classify_source("pnpm-lock.yaml"))

    def test_classify_source_requirements_txt(self):
        self.assertTrue(pl.classify_source("requirements.txt"))

    def test_classify_source_requirements_dev_txt(self):
        self.assertTrue(pl.classify_source("requirements-dev.txt"))

    # --- True: CI / pipeline yaml ---

    def test_classify_source_ci_yml(self):
        self.assertTrue(pl.classify_source(".github/workflows/ci.yml"))

    def test_classify_source_deploy_yaml(self):
        self.assertTrue(pl.classify_source(".github/workflows/deploy.yaml"))

    # --- True: schema / migrations ---

    def test_classify_source_sql_file(self):
        self.assertTrue(pl.classify_source("db/schema.sql"))

    def test_classify_source_migrations_segment(self):
        """Any path containing a migrations/ segment is a drift_trigger."""
        self.assertTrue(pl.classify_source("db/migrations/001_init.sql"))

    def test_classify_source_prisma_schema(self):
        self.assertTrue(pl.classify_source("prisma/schema.prisma"))

    # --- True: env templates ---

    def test_classify_source_env_example(self):
        self.assertTrue(pl.classify_source(".env.example"))

    def test_classify_source_env_sample(self):
        self.assertTrue(pl.classify_source(".env.sample"))

    def test_classify_source_env_template(self):
        self.assertTrue(pl.classify_source(".env.template"))

    # --- True: security-entry basenames (auth / middleware / jwt) ---

    def test_classify_source_auth_ts(self):
        self.assertTrue(pl.classify_source("src/auth.ts"))

    def test_classify_source_middleware_py(self):
        self.assertTrue(pl.classify_source("middleware.py"))

    def test_classify_source_jwt_go(self):
        self.assertTrue(pl.classify_source("utils/jwt.go"))

    # --- False: general source (no security keyword, no manifest pattern) ---

    def test_classify_source_ts_service_false(self):
        self.assertFalse(pl.classify_source("src/services/userService.ts"))

    def test_classify_source_py_util_false(self):
        self.assertFalse(pl.classify_source("lib/util.py"))

    def test_classify_source_readme_false(self):
        self.assertFalse(pl.classify_source("README.md"))

    def test_classify_source_go_main_false(self):
        """A plain .go file with no security-entry basename is False."""
        self.assertFalse(pl.classify_source("cmd/main.go"))

    def test_classify_source_tsx_component_false(self):
        self.assertFalse(pl.classify_source("components/Button.tsx"))

    # --- Edge: Windows-style backslash normalization ---

    def test_classify_source_windows_backslash_middleware(self):
        """Backslash path must classify identically to forward-slash path."""
        self.assertTrue(pl.classify_source("src\\middleware.py"))

    def test_classify_source_windows_backslash_ci_yaml(self):
        """Windows path .github\\workflows\\ci.yml is a drift_trigger after normalization."""
        self.assertTrue(pl.classify_source(".github\\workflows\\ci.yml"))

    # --- Edge: None / empty path returns False without raising ---

    def test_classify_source_none_returns_false(self):
        """None path must return False without raising."""
        self.assertFalse(pl.classify_source(None))

    def test_classify_source_empty_string_returns_false(self):
        """Empty string must return False without raising."""
        self.assertFalse(pl.classify_source(""))

    # --- Token-boundary correctness (anti-noise pillar 2) ---
    # Security-entry keywords must match as whole tokens, not as substrings.
    # 'author' contains 'auth' but is NOT the token 'auth' → must be False.
    # A path segment equal to 'middleware' in any directory → must be True.

    def test_classify_source_author_py_false(self):
        """'author' contains 'auth' as a substring but is not the token 'auth' — must be False."""
        self.assertFalse(pl.classify_source("lib/author.py"))

    def test_classify_source_authorcard_tsx_false(self):
        """AuthorCard contains 'auth' substring but camelCase token is 'Author', not 'auth' — must be False."""
        self.assertFalse(pl.classify_source("components/AuthorCard.tsx"))

    def test_classify_source_middleware_path_segment_true(self):
        """A file under a middleware/ path segment is a drift_trigger even if the basename has no keyword."""
        self.assertTrue(pl.classify_source("src/middleware/cors.py"))

    def test_classify_source_camel_auth_middleware_true(self):
        """camelCase authMiddleware splits into tokens 'auth' and 'middleware' — both are entry tokens."""
        self.assertTrue(pl.classify_source("authMiddleware.ts"))

    def test_classify_source_jwt_underscore_utils_true(self):
        """jwt_utils.py: underscore splits 'jwt' as a standalone token — must be True."""
        self.assertTrue(pl.classify_source("jwt_utils.py"))


class ComputeDriftTest(unittest.TestCase):
    """AC-04: compute_drift detects changed-hash entries (changed-kind only).

    Tests named to match both -k compute_drift and more specific -k filters such
    as -k drift_diverged.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _entry(self, path, hash_, drift_trigger=True):
        return {
            "path": path,
            "hash": hash_,
            "drift_trigger": drift_trigger,
            "claims": [],
        }

    def _record(self, doc, entries):
        return pl.new_record(doc, entries=entries, created="2026-06-26")

    # ------------------------------------------------------------------
    # AC-04 core: one diverged entry across two docs
    # ------------------------------------------------------------------

    def test_compute_drift_one_diverged(self):
        """One diverged path → appears under its doc with kind='changed'; no other doc/path appears."""
        # Two docs, multiple entries; only ONE entry has a mismatched hash.
        entry_a1 = self._entry("src/a.py", "aaaa1111")
        entry_a2 = self._entry("src/b.py", "bbbb2222")
        entry_b1 = self._entry("src/c.ts", "cccc3333")
        entry_b2 = self._entry("src/d.ts", "dddd4444")

        provenance_map = {
            "doc-alpha": self._record("doc-alpha", [entry_a1, entry_a2]),
            "doc-beta":  self._record("doc-beta",  [entry_b1, entry_b2]),
        }

        # current_hashes: all match EXCEPT src/c.ts, which has a changed oid.
        current_hashes = {
            "src/a.py": "aaaa1111",   # equal — no drift
            "src/b.py": "bbbb2222",   # equal — no drift
            "src/c.ts": "cccc9999",   # CHANGED — must appear
            "src/d.ts": "dddd4444",   # equal — no drift
        }

        result = pl.compute_drift(provenance_map, current_hashes)

        # Exactly one doc key in result: "doc-beta"
        self.assertEqual(set(result.keys()), {"doc-beta"},
                         "Only the doc with a diverged entry must appear in the result")

        # That doc has exactly one drift record
        drifts = result["doc-beta"]
        self.assertEqual(len(drifts), 1,
                         "Exactly one drift record expected under doc-beta")

        drift = drifts[0]
        self.assertEqual(drift["path"], "src/c.ts")
        self.assertEqual(drift["kind"], "changed")

        # doc-alpha must NOT appear
        self.assertNotIn("doc-alpha", result,
                         "doc-alpha has no drift so must be omitted from the result")

    # ------------------------------------------------------------------
    # Clean case: all hashes equal → empty dict
    # ------------------------------------------------------------------

    def test_compute_drift_all_equal_returns_empty(self):
        """When every entry hash matches current_hashes, result is {}."""
        entries = [
            self._entry("x.py", "1111"),
            self._entry("y.py", "2222"),
        ]
        provenance_map = {"doc-x": self._record("doc-x", entries)}
        current_hashes = {"x.py": "1111", "y.py": "2222"}

        result = pl.compute_drift(provenance_map, current_hashes)
        self.assertEqual(result, {},
                         "All-equal hashes must produce an empty dict")

    # ------------------------------------------------------------------
    # Degrade: None record in the map must not raise
    # ------------------------------------------------------------------

    def test_compute_drift_none_record_does_not_raise(self):
        """A None record value in provenance_map must be skipped, not crash."""
        provenance_map = {
            "doc-good": self._record("doc-good", [self._entry("ok.py", "abcd")]),
            "doc-null": None,
        }
        current_hashes = {"ok.py": "abcd"}

        try:
            result = pl.compute_drift(provenance_map, current_hashes)
        except Exception as exc:
            self.fail(f"compute_drift raised on None record: {exc}")

        # doc-null must not appear (it was degraded/skipped)
        self.assertNotIn("doc-null", result)

    # ------------------------------------------------------------------
    # Entry whose path is absent from current_hashes is SKIPPED (T-06
    # adds missing-kind; for now: do not crash, do not record missing)
    # ------------------------------------------------------------------

    def test_compute_drift_absent_path_skipped(self):
        """AC-05 (T-06): a drift_trigger:true entry whose path is absent from current_hashes
        must be reported as kind='missing', not silently skipped.

        Updated from the pre-T-06 placeholder that asserted 'skipped'; the behavior
        changed per AC-05 — absent drift_trigger:true paths are now surfaced as missing
        so the heal/report logic can treat 'file moved/deleted' differently from 'content changed'.
        """
        entries = [self._entry("gone.py", "dead1111")]
        provenance_map = {"doc-gone": self._record("doc-gone", entries)}
        current_hashes = {}  # gone.py not present

        result = pl.compute_drift(provenance_map, current_hashes)
        # Must not raise; gone.py must appear with kind='missing' (AC-05 / T-06)
        self.assertIn(
            "doc-gone",
            result,
            "drift_trigger:true entry absent from current_hashes must be reported (AC-05)",
        )
        drifts = result["doc-gone"]
        self.assertEqual(len(drifts), 1)
        self.assertEqual(drifts[0]["path"], "gone.py")
        self.assertEqual(drifts[0]["kind"], "missing")

    # ------------------------------------------------------------------
    # AC-09: drift_trigger filtering (T-05)
    # Only entries with drift_trigger == True can ever be reported.
    # drift_trigger: False or absent → treated as False → never reported.
    # ------------------------------------------------------------------

    def test_compute_drift_drift_trigger_false_never_reported(self):
        """AC-09: drift_trigger:false entries with a diverged hash must NOT be reported.

        Also asserts that a drift_trigger:true diverged entry IS still reported —
        proving the filter is selective, not a blanket suppress.
        """
        # drift_trigger:false — hash is diverged but must be suppressed
        entry_false = {
            "path": "src/impl.py",
            "hash": "old1111",
            "drift_trigger": False,
            "claims": [],
        }
        # drift_trigger:true — hash is diverged and must be reported
        entry_true = {
            "path": "package.json",
            "hash": "old2222",
            "drift_trigger": True,
            "claims": [],
        }

        provenance_map = {
            "doc-mixed": self._record("doc-mixed", [entry_false, entry_true]),
        }
        current_hashes = {
            "src/impl.py": "new1111",   # diverged, drift_trigger=False → must NOT appear
            "package.json": "new2222",  # diverged, drift_trigger=True  → must appear
        }

        result = pl.compute_drift(provenance_map, current_hashes)

        # doc-mixed must appear because at least one drift_trigger:true entry diverged
        self.assertIn("doc-mixed", result,
                      "doc with a diverged drift_trigger:true entry must appear in result")

        paths_reported = [d["path"] for d in result["doc-mixed"]]

        self.assertIn("package.json", paths_reported,
                      "drift_trigger:true diverged entry must be reported as changed")
        self.assertNotIn("src/impl.py", paths_reported,
                         "drift_trigger:false entry must NOT be reported even when its hash diverged")

    def test_compute_drift_drift_trigger_absent_treated_as_false(self):
        """AC-09: absent drift_trigger key is treated as False and must NOT be reported.

        Conservative default: only an explicit True fires drift.
        """
        # No drift_trigger key at all — must be treated as False
        entry_no_key = {
            "path": "src/nokey.py",
            "hash": "old9999",
            "claims": [],
        }

        provenance_map = {
            "doc-nokey": self._record("doc-nokey", [entry_no_key]),
        }
        current_hashes = {
            "src/nokey.py": "new9999",  # diverged, but no drift_trigger key → not reported
        }

        result = pl.compute_drift(provenance_map, current_hashes)
        self.assertNotIn(
            "doc-nokey",
            result,
            "Entry with absent drift_trigger is treated as False and must not be reported",
        )

    def test_compute_drift_drift_trigger_false_only_doc_omitted(self):
        """AC-09: doc whose only diverged entries all have drift_trigger:false must be omitted entirely."""
        entry_a = {
            "path": "src/service.py",
            "hash": "aaa111",
            "drift_trigger": False,
            "claims": [],
        }
        entry_b = {
            "path": "src/utils.py",
            "hash": "bbb222",
            "drift_trigger": False,
            "claims": [],
        }

        provenance_map = {
            "doc-all-false": self._record("doc-all-false", [entry_a, entry_b]),
        }
        current_hashes = {
            "src/service.py": "aaa999",  # diverged, but drift_trigger=False
            "src/utils.py": "bbb999",    # diverged, but drift_trigger=False
        }

        result = pl.compute_drift(provenance_map, current_hashes)
        self.assertEqual(
            result,
            {},
            "Doc with only drift_trigger:false diverged entries must be omitted entirely (clean → {})",
        )


class ComputeDriftMissingTest(unittest.TestCase):
    """AC-05: compute_drift reports drift_trigger:true entries absent from current_hashes as kind='missing'.

    Tests named to satisfy -k drift_missing.
    """

    # ------------------------------------------------------------------
    # Helpers (mirror ComputeDriftTest)
    # ------------------------------------------------------------------

    def _entry(self, path, hash_, drift_trigger=True):
        return {
            "path": path,
            "hash": hash_,
            "drift_trigger": drift_trigger,
            "claims": [],
        }

    def _record(self, doc, entries):
        return pl.new_record(doc, entries=entries, created="2026-06-26")

    # ------------------------------------------------------------------
    # AC-05 core: absent drift_trigger:true path → kind='missing'
    # ------------------------------------------------------------------

    def test_compute_drift_missing_path_reported(self):
        """AC-05: a drift_trigger:true entry whose path is absent from current_hashes
        must appear under its doc with kind='missing'."""
        entries = [self._entry("gone.py", "dead1111")]
        provenance_map = {"doc-gone": self._record("doc-gone", entries)}
        current_hashes = {}  # gone.py not in current_hashes

        result = pl.compute_drift(provenance_map, current_hashes)

        self.assertIn(
            "doc-gone",
            result,
            "Doc with a drift_trigger:true absent entry must appear in result",
        )
        drifts = result["doc-gone"]
        self.assertEqual(len(drifts), 1, "Exactly one drift record expected")
        drift = drifts[0]
        self.assertEqual(drift["path"], "gone.py")
        self.assertEqual(drift["kind"], "missing")

    def test_compute_drift_missing_drift_trigger_false_not_reported(self):
        """AC-05: the missing-kind rule respects drift_trigger — a drift_trigger:false
        entry absent from current_hashes must NOT be reported."""
        entries = [self._entry("gone-false.py", "dead2222", drift_trigger=False)]
        provenance_map = {"doc-false": self._record("doc-false", entries)}
        current_hashes = {}  # gone-false.py not in current_hashes

        result = pl.compute_drift(provenance_map, current_hashes)

        self.assertNotIn(
            "doc-false",
            result,
            "drift_trigger:false absent entry must NOT be reported as missing",
        )

    def test_compute_drift_missing_does_not_raise(self):
        """AC-05: compute_drift must not raise when a drift_trigger:true entry's path
        is absent from current_hashes."""
        entries = [self._entry("vanished.py", "abc12345")]
        provenance_map = {"doc-vanished": self._record("doc-vanished", entries)}
        current_hashes = {}

        try:
            result = pl.compute_drift(provenance_map, current_hashes)
        except Exception as exc:
            self.fail(f"compute_drift raised on absent path: {exc}")

        # Sanity: result must be a dict (the function returned normally)
        self.assertIsInstance(result, dict)

    def test_compute_drift_missing_and_changed_both_reported(self):
        """AC-05: a doc with one drift_trigger:true changed entry and one drift_trigger:true
        absent entry must report BOTH with their correct kinds."""
        entry_changed = self._entry("package.json", "old-hash-pkg")
        entry_missing = self._entry("src/auth.ts", "old-hash-auth")

        provenance_map = {
            "doc-mix": self._record("doc-mix", [entry_changed, entry_missing]),
        }
        # package.json is present but hash changed; src/auth.ts is absent entirely.
        current_hashes = {
            "package.json": "new-hash-pkg",  # diverged → kind='changed'
            # src/auth.ts is intentionally absent → kind='missing'
        }

        result = pl.compute_drift(provenance_map, current_hashes)

        self.assertIn("doc-mix", result, "doc-mix must appear in result")
        drifts = result["doc-mix"]
        self.assertEqual(
            len(drifts), 2, "Both the changed and missing entries must be reported"
        )

        kinds_by_path = {d["path"]: d["kind"] for d in drifts}

        self.assertEqual(
            kinds_by_path.get("package.json"),
            "changed",
            "package.json hash diverged → kind must be 'changed'",
        )
        self.assertEqual(
            kinds_by_path.get("src/auth.ts"),
            "missing",
            "src/auth.ts absent from current_hashes → kind must be 'missing'",
        )


class EolNormalizationTest(unittest.TestCase):
    """AC-03: git hash-object honors EOL normalization → no CRLF false-drift.

    Uses REAL git in a throwaway repo (not the injected fake runner).
    A pure LF↔CRLF flip under .gitattributes eol=lf must produce the same
    blob oid so compute_drift returns {} (no false drift).
    """

    def _make_tmp_runner(self, tmp):
        """Return a runner bound to the tmp git repo.

        Inserts ``-C <tmp>`` so git hash-object resolves paths relative to
        the throwaway repo, not the test process cwd.
        """
        import subprocess as _sp

        def runner(args, stdin_text):
            r = _sp.run(
                ["git", "-C", tmp] + list(args),
                input=stdin_text,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            return r.stdout

        return runner

    def test_eol_normalization_no_false_drift(self):
        """AC-03: LF↔CRLF flip under eol=lf must NOT register as drift (real git).

        Steps:
          1. Build a throwaway git repo in a tempdir; add .gitattributes
             with '* text=auto eol=lf'; set core.autocrlf=false.
          2. Hash doc.md with LF endings via batch_hash → BASELINE oid.
          3. Rewrite doc.md with CRLF endings; hash again → CURRENT oid.
          4. Assert baseline == current (git normalised CRLF→LF per eol=lf).
          5. Assert compute_drift(provenance_map, current_hashes) == {}.

        Meaningfulness verification (done before adding this test):
          With a temporary assertNotEqual the test FAILED when .gitattributes
          was present (both oids were 0c5b5a... — git did normalise), proving
          the test exercises real git and would catch a regression.  The probe
          without .gitattributes confirmed LF vs CRLF produce DIFFERENT oids
          (LF=0c5b5a..., CRLF=a00b8a...), confirming git IS the gate.

        Skips rather than fails when git is unavailable (mirrors the
        docker-gated self-skip pattern used in ca-sandbox tests).
        """
        import shutil
        import subprocess

        # Skip gracefully when git is not available on this host.
        try:
            probe = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if probe.returncode != 0:
                self.skipTest("git not available (--version returned non-zero)")
        except FileNotFoundError:
            self.skipTest("git not available (FileNotFoundError)")

        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)

        def run_git(*args):
            return subprocess.run(
                ["git", "-C", tmp] + list(args),
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        # --- Step 1: initialise a throwaway repo with a deterministic identity ---
        run_git("init")
        run_git("config", "user.email", "test@example.com")
        run_git("config", "user.name", "Test")
        # Disable core.autocrlf so EOL behaviour is controlled only by
        # .gitattributes — the mechanism under proof for AC-03.
        run_git("config", "core.autocrlf", "false")

        # Write .gitattributes that pins LF for all text files and stage it so
        # git hash-object picks up the attribute when hashing doc.md.
        gitattributes_path = os.path.join(tmp, ".gitattributes")
        with open(gitattributes_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("* text=auto eol=lf\n")
        run_git("add", ".gitattributes")

        # Build a runner bound to the tmp repo (the default runner uses process
        # cwd which is NOT the tmp repo — we MUST inject a tmp-repo runner).
        runner = self._make_tmp_runner(tmp)

        # --- Step 2: hash doc.md with LF endings → BASELINE oid ---
        doc_abs = os.path.join(tmp, "doc.md")
        lf_bytes = b"# Title\n\nLine one.\nLine two.\n"
        with open(doc_abs, "wb") as fh:
            fh.write(lf_bytes)

        baseline_map = pl.batch_hash(["doc.md"], runner)
        if not baseline_map or "doc.md" not in baseline_map:
            self.skipTest(
                "git hash-object --stdin-paths returned no hash; "
                "EOL normalization cannot be verified on this host"
            )
        baseline_oid = baseline_map["doc.md"]

        # --- Step 3: rewrite doc.md with CRLF endings → CURRENT oid ---
        crlf_bytes = lf_bytes.replace(b"\n", b"\r\n")
        with open(doc_abs, "wb") as fh:
            fh.write(crlf_bytes)

        current_map = pl.batch_hash(["doc.md"], runner)
        self.assertIn(
            "doc.md",
            current_map,
            "batch_hash must return an oid for doc.md (CRLF variant)",
        )
        current_oid = current_map["doc.md"]

        # --- Step 4: AC-03 blob-oid assertion ---
        # git must have normalised CRLF→LF per eol=lf so both variants
        # produce the same blob oid.  A mismatch here means git hash-object
        # is NOT applying the eol=lf clean filter → false-drift regression.
        self.assertEqual(
            baseline_oid,
            current_oid,
            (
                f"LF and CRLF variants must produce the same git oid under "
                f"eol=lf (LF={baseline_oid!r}, CRLF={current_oid!r}). "
                f"A mismatch would cause false-drift on any Windows CRLF edit."
            ),
        )

        # --- Step 5: AC-03 compute_drift assertion ---
        # With baseline oid == current oid, compute_drift must return {} (clean).
        record = pl.new_record(
            "tech-stack",
            created="2026-06-26",
            entries=[
                {
                    "path": "doc.md",
                    "hash": baseline_oid,
                    "drift_trigger": True,
                    "claims": [],
                }
            ],
        )
        drift = pl.compute_drift({"tech-stack": record}, {"doc.md": current_oid})
        self.assertEqual(
            drift,
            {},
            f"compute_drift must return {{}} for LF↔CRLF flip under eol=lf, "
            f"got: {drift!r}",
        )


class StartupDriftLineSilentTest(unittest.TestCase):
    """AC-06: startup_drift_line returns '' when drift is zero (clean docs)."""

    def test_startup_drift_line_silent_when_clean(self):
        """AC-06: no diverged entry → startup_drift_line returns '' (spec pillar 4).

        Builds a tempdir root with a .provenance JSON file whose drift_trigger:true
        entries all point at files that exist under root. Injects a fake runner that
        returns oids EQUAL to the stored hashes → compute_drift sees no divergence →
        startup_drift_line returns ''.

        Also asserts that a root with NO .provenance dir returns ''.
        """
        import shutil

        known_oid = "abcdef1234567890abcdef1234567890abcdef12"

        def fake_runner(args, stdin_text):
            """Return known_oid for every path handed in (simulates clean git state)."""
            paths = [p for p in stdin_text.strip().split("\n") if p]
            return "\n".join([known_oid] * len(paths)) + "\n"

        # --- Case 1: root with .provenance/ dir and clean hashes → '' ---
        tmp = tempfile.mkdtemp()
        try:
            root = tmp
            provenance_dir = os.path.join(root, ".codearbiter", ".provenance")
            os.makedirs(provenance_dir, exist_ok=True)

            # Create an actual source file under root so it counts as existing
            src_rel = "package.json"
            src_abs = os.path.join(root, src_rel)
            with open(src_abs, "w", encoding="utf-8") as fh:
                fh.write('{"name": "test"}\n')

            # Write provenance: drift_trigger:true entry, stored hash == known_oid
            record = pl.new_record(
                "tech-stack",
                created="2026-06-26",
                entries=[
                    {
                        "path": src_rel,
                        "hash": known_oid,
                        "drift_trigger": True,
                        "claims": [],
                    }
                ],
            )
            pl.write_provenance(
                os.path.join(provenance_dir, "tech-stack.json"),
                record,
            )

            result = pl.startup_drift_line(root, runner=fake_runner)
            self.assertEqual(
                result,
                "",
                "No drift → startup_drift_line must return '' (AC-06)",
            )
        finally:
            shutil.rmtree(tmp, True)

        # --- Case 2: root with NO .provenance/ dir must also return '' ---
        tmp2 = tempfile.mkdtemp()
        try:
            result2 = pl.startup_drift_line(tmp2, runner=fake_runner)
            self.assertEqual(
                result2,
                "",
                "Missing .provenance dir → startup_drift_line must return '' (AC-06)",
            )
        finally:
            shutil.rmtree(tmp2, True)


class StartupDriftLinePathConfinementTest(unittest.TestCase):
    """v2.harden.0001: untrusted provenance paths never reach git hashing."""

    def _write_record(self, root, entries):
        provenance_dir = os.path.join(root, ".codearbiter", ".provenance")
        os.makedirs(provenance_dir, exist_ok=True)
        record = pl.new_record(
            "tech-stack",
            created="2026-07-20",
            entries=entries,
        )
        pl.write_provenance(os.path.join(provenance_dir, "tech-stack.json"), record)

    def test_startup_drift_line_drops_unsafe_paths_before_hashing(self):
        known_oid = "abcdef1234567890abcdef1234567890abcdef12"
        with tempfile.TemporaryDirectory() as sandbox:
            root = os.path.join(sandbox, "repo")
            os.makedirs(root)
            with open(os.path.join(root, "package.json"), "w", encoding="utf-8") as fh:
                fh.write('{"name": "test"}\n')
            with open(os.path.join(sandbox, "outside.json"), "w", encoding="utf-8") as fh:
                fh.write('{"outside": true}\n')
            self._write_record(
                root,
                [
                    {
                        "path": "package.json",
                        "hash": known_oid,
                        "drift_trigger": True,
                        "claims": [],
                    },
                    {"path": "../outside.json", "drift_trigger": True},
                    {"path": os.path.join(sandbox, "outside.json"), "drift_trigger": True},
                    {"path": r"C:\outside.json", "drift_trigger": True},
                    {"path": "/outside.json", "drift_trigger": True},
                    {"path": ".", "drift_trigger": True},
                ],
            )
            calls = []

            def fake_runner(args, stdin_text):
                calls.append((args, stdin_text))
                return known_oid + "\n"

            self.assertEqual(pl.startup_drift_line(root, runner=fake_runner), "")
            self.assertEqual(calls, [(["hash-object", "--stdin-paths"], "package.json\n")])

    def test_startup_drift_line_drops_control_paths_without_losing_valid_hashes(self):
        known_oid = "abcdef1234567890abcdef1234567890abcdef12"
        for unsafe_path in ("bad\x00path", "bad\npath", "bad\rpath"):
            with self.subTest(unsafe_path=repr(unsafe_path)), tempfile.TemporaryDirectory() as root:
                with open(os.path.join(root, "package.json"), "w", encoding="utf-8") as fh:
                    fh.write('{"name": "test"}\n')
                self._write_record(
                    root,
                    [
                        {
                            "path": "package.json",
                            "hash": known_oid,
                            "drift_trigger": True,
                            "claims": [],
                        },
                        {"path": unsafe_path, "drift_trigger": True},
                    ],
                )
                calls = []

                def fake_runner(args, stdin_text):
                    calls.append((args, stdin_text))
                    return known_oid + "\n"

                self.assertEqual(pl.startup_drift_line(root, runner=fake_runner), "")
                self.assertEqual(calls, [(["hash-object", "--stdin-paths"], "package.json\n")])

    def test_startup_drift_line_drops_symlink_escape_before_hashing(self):
        known_oid = "abcdef1234567890abcdef1234567890abcdef12"
        with tempfile.TemporaryDirectory() as sandbox:
            root = os.path.join(sandbox, "repo")
            outside = os.path.join(sandbox, "outside")
            os.makedirs(root)
            os.makedirs(outside)
            with open(os.path.join(root, "package.json"), "w", encoding="utf-8") as fh:
                fh.write('{"name": "test"}\n')
            with open(os.path.join(outside, "data.json"), "w", encoding="utf-8") as fh:
                fh.write('{"outside": true}\n')
            try:
                os.symlink(outside, os.path.join(root, "linked"), target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                self.skipTest("symlink fixture unavailable: {}".format(exc))

            self._write_record(
                root,
                [
                    {
                        "path": "package.json",
                        "hash": known_oid,
                        "drift_trigger": True,
                        "claims": [],
                    },
                    {"path": "linked/data.json", "drift_trigger": True},
                ],
            )
            calls = []

            def fake_runner(args, stdin_text):
                calls.append((args, stdin_text))
                return known_oid + "\n"

            self.assertEqual(pl.startup_drift_line(root, runner=fake_runner), "")
            self.assertEqual(calls, [(["hash-object", "--stdin-paths"], "package.json\n")])


class StartupDriftLineEmitTest(unittest.TestCase):
    """AC-07: startup_drift_line returns exactly one informative line when drift > 0.

    Tests named to satisfy -k drift_line_emit.
    """

    def test_startup_drift_line_emits_counts_and_pointer(self):
        """AC-07: drift > 0 -> startup_drift_line returns exactly one line naming
        stale-source count and doc count, and pointing to /ca:context-check.

        Setup: 3 stale sources across 2 docs:
          doc 'tech-stack':       package.json (changed) + src/auth.ts (missing) = 2
          doc 'coding-standards': .github/workflows/ci.yml (changed)            = 1
        Fake runner returns a diverged oid for every existing path -> 'changed'.
        src/auth.ts has no on-disk file -> compute_drift reports it as 'missing'.
        Total: N=3 stale sources, M=2 affected docs.
        """
        import shutil

        stored_oid = "1111111111111111111111111111111111111111"
        diverged_oid = "9999999999999999999999999999999999999999"

        def fake_runner(args, stdin_text):
            """Return a diverged oid for every path -> all existing paths are 'changed'."""
            paths = [p for p in stdin_text.strip().split("\n") if p]
            return "\n".join([diverged_oid] * len(paths)) + "\n"

        tmp = tempfile.mkdtemp()
        try:
            root = tmp
            provenance_dir = os.path.join(root, ".codearbiter", ".provenance")
            os.makedirs(provenance_dir, exist_ok=True)

            # Create real files for the 'changed' entries (they exist on disk).
            pkg_json = os.path.join(root, "package.json")
            with open(pkg_json, "w", encoding="utf-8") as fh:
                fh.write('{"name": "test"}\n')

            ci_dir = os.path.join(root, ".github", "workflows")
            os.makedirs(ci_dir, exist_ok=True)
            ci_yml = os.path.join(ci_dir, "ci.yml")
            with open(ci_yml, "w", encoding="utf-8") as fh:
                fh.write("name: CI\n")

            # src/auth.ts intentionally NOT created -> will be kind='missing'.

            # Doc 1: tech-stack -- 2 drift_trigger entries
            record1 = pl.new_record(
                "tech-stack",
                created="2026-06-26",
                entries=[
                    {
                        "path": "package.json",
                        "hash": stored_oid,
                        "drift_trigger": True,
                        "claims": [],
                    },
                    {
                        "path": "src/auth.ts",
                        "hash": stored_oid,
                        "drift_trigger": True,
                        "claims": [],
                    },
                ],
            )
            pl.write_provenance(
                os.path.join(provenance_dir, "tech-stack.json"),
                record1,
            )

            # Doc 2: coding-standards -- 1 drift_trigger entry
            record2 = pl.new_record(
                "coding-standards",
                created="2026-06-26",
                entries=[
                    {
                        "path": ".github/workflows/ci.yml",
                        "hash": stored_oid,
                        "drift_trigger": True,
                        "claims": [],
                    },
                ],
            )
            pl.write_provenance(
                os.path.join(provenance_dir, "coding-standards.json"),
                record2,
            )

            result = pl.startup_drift_line(root, runner=fake_runner)

            # AC-07: non-empty
            self.assertNotEqual(result, "", "drift > 0 must produce a non-empty line")

            # AC-07: exactly one physical line (no embedded newline)
            self.assertNotIn("\n", result, "result must contain no embedded newline")
            self.assertEqual(result.count("\n"), 0, "result.count('\\n') must be 0")

            # AC-07: stale-source count (3) and doc count (2) present in the line
            self.assertIn("3", result, "result must name the stale-source count (3)")
            self.assertIn("2", result, "result must name the affected-doc count (2)")

            # AC-07: pointer to /ca:context-check
            self.assertIn("/ca:context-check", result,
                          "result must contain '/ca:context-check'")

            # AC-07: ASCII-only (Windows console safety)
            try:
                result.encode("ascii")
            except UnicodeEncodeError as exc:
                self.fail(f"result is not ASCII: {exc}")

        finally:
            shutil.rmtree(tmp, True)

        # AC-06 regression guard: clean root (no .provenance/) must still return ''.
        tmp2 = tempfile.mkdtemp()
        try:
            result2 = pl.startup_drift_line(tmp2, runner=fake_runner)
            self.assertEqual(
                result2,
                "",
                "Missing .provenance dir must still return '' (AC-06 regression guard)",
            )
        finally:
            shutil.rmtree(tmp2, True)


class DegradeTest(unittest.TestCase):
    """AC-08: degrade-not-fail — missing/corrupt provenance and git unavailability
    must all degrade to '' on the SessionStart linchpin path, never crash or
    emit a false-alarm drift line.

    Tests named to satisfy -k degrade:
      test_degrade_missing_provenance_dir      (lock-in: already works)
      test_degrade_corrupt_json                (lock-in: already works)
      test_degrade_compute_drift_malformed_no_raise  (lock-in: already works)
      test_degrade_hash_failure_stays_silent   (HARDENING — must be RED before fix)
    """

    def test_degrade_missing_provenance_dir(self):
        """AC-08: missing .provenance/ dir -> load_provenance_dir returns {} ->
        startup_drift_line returns '' and never raises.

        lock-in: proves existing degrade path stays intact.
        """
        import shutil

        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)

        # No .codearbiter/.provenance directory created — just an empty root.
        pm = pl.load_provenance_dir(
            os.path.join(tmp, ".codearbiter", ".provenance")
        )
        self.assertEqual(pm, {}, "Missing .provenance/ dir must yield empty map")

        try:
            result = pl.startup_drift_line(tmp)
        except Exception as exc:
            self.fail(f"startup_drift_line raised on missing provenance dir: {exc}")
        self.assertEqual(result, "", "Missing .provenance dir must degrade to ''")

    def test_degrade_corrupt_json(self):
        """AC-08: corrupt JSON files in .provenance/:
          • read_provenance returns None on each corrupt file (never raises).
          • All-corrupt provenance dir -> load_provenance_dir returns {} ->
            startup_drift_line returns ''.
          • Mix (one valid, one corrupt) -> only valid doc evaluated, no crash.

        lock-in: proves existing degrade path stays intact.
        """
        import shutil

        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        root = tmp
        provenance_dir = os.path.join(root, ".codearbiter", ".provenance")
        os.makedirs(provenance_dir, exist_ok=True)

        # Write two corrupt provenance files.
        corrupt1 = os.path.join(provenance_dir, "corrupt1.json")
        with open(corrupt1, "w", encoding="utf-8") as fh:
            fh.write("{this is not valid JSON!!")
        corrupt2 = os.path.join(provenance_dir, "corrupt2.json")
        with open(corrupt2, "wb") as fh:
            fh.write(b"\x00\x01\x02truncated garbage")

        # read_provenance must return None for each corrupt file, never raise.
        self.assertIsNone(
            pl.read_provenance(corrupt1),
            "Malformed JSON must return None from read_provenance",
        )
        self.assertIsNone(
            pl.read_provenance(corrupt2),
            "Truncated/binary garbage must return None from read_provenance",
        )

        # All-corrupt dir -> empty map.
        pm_all_corrupt = pl.load_provenance_dir(provenance_dir)
        self.assertEqual(
            pm_all_corrupt, {}, "All-corrupt provenance dir must yield empty map"
        )

        # startup_drift_line must return '' (empty map -> silent) and not raise.
        try:
            result_all_corrupt = pl.startup_drift_line(root)
        except Exception as exc:
            self.fail(
                f"startup_drift_line raised on all-corrupt provenance: {exc}"
            )
        self.assertEqual(
            result_all_corrupt,
            "",
            "All-corrupt provenance must degrade to ''",
        )

        # Mix: add one valid record alongside the two corrupt files.
        src_rel = "package.json"
        src_abs = os.path.join(root, src_rel)
        with open(src_abs, "w", encoding="utf-8") as fh:
            fh.write('{"name": "test"}\n')

        known_oid = "abcdef1234567890abcdef1234567890abcdef12"
        valid_record = pl.new_record(
            "tech-stack",
            created="2026-06-26",
            entries=[
                {
                    "path": src_rel,
                    "hash": known_oid,
                    "drift_trigger": True,
                    "claims": [],
                }
            ],
        )
        pl.write_provenance(
            os.path.join(provenance_dir, "tech-stack.json"),
            valid_record,
        )

        # Mix load: only the valid doc survives, no crash.
        pm_mix = pl.load_provenance_dir(provenance_dir)
        self.assertIn(
            "tech-stack", pm_mix, "Valid doc must survive corrupt neighbours"
        )
        self.assertEqual(len(pm_mix), 1, "Only valid doc must be in the map")

        # startup_drift_line with mix must not crash; inject a clean runner so
        # the test does not depend on real git.
        def fake_clean_runner(args, stdin_text):
            paths = [p for p in stdin_text.strip().split("\n") if p]
            return "\n".join([known_oid] * len(paths)) + "\n"

        try:
            result_mix = pl.startup_drift_line(root, runner=fake_clean_runner)
        except Exception as exc:
            self.fail(
                f"startup_drift_line raised on mix of corrupt+valid: {exc}"
            )
        # Hashes match -> no drift -> ''.
        self.assertEqual(
            result_mix,
            "",
            "Mix (corrupt+valid, hashes match) must return '' (AC-08 / degrade)",
        )

    def test_degrade_compute_drift_malformed_no_raise(self):
        """AC-08: compute_drift must not raise on malformed provenance maps:
          • record missing 'entries' key
          • record with entries=None
          • entry missing 'path' key
          • entry missing 'hash' key
          • None record value
          • non-dict provenance_map
        Returns {} or skips the bad record/entry — never raises.

        lock-in: proves existing degrade path stays intact.
        """
        # Record missing 'entries' key entirely.
        pm_no_entries = {
            "doc-no-entries": {
                "schema": 1,
                "doc": "doc-no-entries",
                "created": "2026-06-26",
                "interview_derived": False,
            }
        }
        try:
            r = pl.compute_drift(pm_no_entries, {"path.py": "abc"})
        except Exception as exc:
            self.fail(f"compute_drift raised on record missing 'entries': {exc}")
        self.assertIsInstance(r, dict)

        # Record with entries=None.
        pm_entries_none = {
            "doc-entries-none": {
                "schema": 1,
                "doc": "doc-entries-none",
                "created": "2026-06-26",
                "interview_derived": False,
                "entries": None,
            }
        }
        try:
            r2 = pl.compute_drift(pm_entries_none, {})
        except Exception as exc:
            self.fail(f"compute_drift raised on entries=None: {exc}")
        self.assertIsInstance(r2, dict)

        # None record value.
        pm_null = {"doc-null": None}
        try:
            r3 = pl.compute_drift(pm_null, {})
        except Exception as exc:
            self.fail(f"compute_drift raised on None record value: {exc}")
        self.assertIsInstance(r3, dict)
        self.assertNotIn("doc-null", r3, "None record must be skipped entirely")

        # Entry missing 'path' key.
        pm_no_path = {
            "doc-no-path": {
                "schema": 1,
                "doc": "doc-no-path",
                "created": "2026-06-26",
                "interview_derived": False,
                "entries": [
                    {"hash": "abc123", "drift_trigger": True, "claims": []}
                ],
            }
        }
        try:
            r4 = pl.compute_drift(pm_no_path, {})
        except Exception as exc:
            self.fail(f"compute_drift raised on entry missing 'path': {exc}")
        self.assertIsInstance(r4, dict)

        # Entry missing 'hash' key (path present in current_hashes but no stored hash).
        pm_no_hash = {
            "doc-no-hash": {
                "schema": 1,
                "doc": "doc-no-hash",
                "created": "2026-06-26",
                "interview_derived": False,
                "entries": [
                    {"path": "src/thing.py", "drift_trigger": True, "claims": []}
                ],
            }
        }
        try:
            r5 = pl.compute_drift(pm_no_hash, {"src/thing.py": "abc123"})
        except Exception as exc:
            self.fail(f"compute_drift raised on entry missing 'hash': {exc}")
        self.assertIsInstance(r5, dict)

        # Totally non-dict provenance_map.
        try:
            r6 = pl.compute_drift("not-a-dict", {})
        except Exception as exc:
            self.fail(
                f"compute_drift raised on non-dict provenance_map: {exc}"
            )
        self.assertIsInstance(r6, dict)
        self.assertEqual(r6, {})

    def test_degrade_hash_failure_stays_silent(self):
        """AC-08 HARDENING: when the runner RAISES, startup_drift_line must
        return '' (not a false drift line) and must not raise.

        The gap: batch_hash returns {} on runner failure -> compute_drift sees
        every existing drift_trigger file as 'missing' -> emits a false alarm.
        The fix: if existing_paths is non-empty but current_hashes is empty,
        degrade to silence.

        Part A: runner raises -> must return '' for existing drift_trigger files.
        Part B: genuine missing still surfaces when hashing SUCCEEDS (regression
                guard confirming the guard did not break the normal alarm path).
        """
        import shutil

        stored_oid = "1111111111111111111111111111111111111111"

        # ------------------------------------------------------------------ #
        # Part A: runner raises -> false-alarm gap -> must degrade to ''      #
        # ------------------------------------------------------------------ #

        def raising_runner(args, stdin_text):
            raise RuntimeError("git gone — simulating unavailable git")

        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        root = tmp
        provenance_dir = os.path.join(root, ".codearbiter", ".provenance")
        os.makedirs(provenance_dir, exist_ok=True)

        # Create a real drift_trigger file on disk so existing_paths is non-empty.
        pkg_json = os.path.join(root, "package.json")
        with open(pkg_json, "w", encoding="utf-8") as fh:
            fh.write('{"name": "test"}\n')

        record = pl.new_record(
            "tech-stack",
            created="2026-06-26",
            entries=[
                {
                    "path": "package.json",
                    "hash": stored_oid,
                    "drift_trigger": True,
                    "claims": [],
                }
            ],
        )
        pl.write_provenance(
            os.path.join(provenance_dir, "tech-stack.json"),
            record,
        )

        try:
            result_a = pl.startup_drift_line(root, runner=raising_runner)
        except Exception as exc:
            self.fail(
                f"startup_drift_line raised when the runner raised: {exc}"
            )

        self.assertEqual(
            result_a,
            "",
            "Runner failure (git gone) with existing drift_trigger files must "
            "degrade to '' — NOT emit a false 'N stale source(s)' alarm",
        )

        # ------------------------------------------------------------------ #
        # Part B: genuine absent file still surfaces when hashing SUCCEEDS    #
        # ------------------------------------------------------------------ #
        # package.json EXISTS -> hashed successfully.
        # src/auth.ts does NOT exist on disk -> genuinely missing -> must alarm.
        # The guard must NOT suppress this legitimate missing-detection.

        tmp2 = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp2, True)
        root2 = tmp2
        provenance_dir2 = os.path.join(root2, ".codearbiter", ".provenance")
        os.makedirs(provenance_dir2, exist_ok=True)

        # package.json exists.
        pkg_json2 = os.path.join(root2, "package.json")
        with open(pkg_json2, "w", encoding="utf-8") as fh:
            fh.write('{"name": "test"}\n')
        # src/auth.ts intentionally NOT created -> genuinely absent drift_trigger.

        record2 = pl.new_record(
            "tech-stack",
            created="2026-06-26",
            entries=[
                {
                    "path": "package.json",
                    "hash": stored_oid,
                    "drift_trigger": True,
                    "claims": [],
                },
                {
                    "path": "src/auth.ts",
                    "hash": stored_oid,
                    "drift_trigger": True,
                    "claims": [],
                },
            ],
        )
        pl.write_provenance(
            os.path.join(provenance_dir2, "tech-stack.json"),
            record2,
        )

        # Runner succeeds: returns stored_oid for existing files (package.json
        # hash matches -> no 'changed'; src/auth.ts not on disk -> 'missing').
        def fake_success_runner(args, stdin_text):
            paths = [p for p in stdin_text.strip().split("\n") if p]
            return "\n".join([stored_oid] * len(paths)) + "\n"

        result_b = pl.startup_drift_line(root2, runner=fake_success_runner)

        self.assertNotEqual(
            result_b,
            "",
            "A genuinely absent drift_trigger file must still surface as drift "
            "when the hash step succeeds (guard must NOT suppress real alarms)",
        )
        self.assertIn(
            "1",
            result_b,
            "Stale-source count (1 genuinely missing file) must appear in the line",
        )
        self.assertIn(
            "/ca:context-check",
            result_b,
            "Line must contain /ca:context-check pointer",
        )

    def test_degrade_partial_hash_stays_silent(self):
        """AC-08 HARDENING (partial): when the runner returns FEWER oids than
        existing paths (partial stdout — git aborted mid-stream or TOCTOU),
        startup_drift_line must return '' rather than falsely reporting the
        un-hashed existing files as 'missing'.

        Setup: 2 drift_trigger files on disk, runner returns only 1 oid.
        Guard: len(current_hashes) < len(existing_paths) -> return ''.
        The weaker `and not current_hashes` guard does NOT fire for a 1-of-2
        partial, so this test is RED before the tightened guard and GREEN after.
        """
        import shutil

        stored_oid = "1111111111111111111111111111111111111111"

        # Runner that returns exactly one oid regardless of how many paths it
        # receives — simulates a partial git hash-object stdout (e.g. TOCTOU
        # abort after the first oid).
        def partial_runner(args, stdin_text):
            return "onlyoid1111111111111111111111111111111111\n"

        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        root = tmp
        provenance_dir = os.path.join(root, ".codearbiter", ".provenance")
        os.makedirs(provenance_dir, exist_ok=True)

        # Create TWO real drift_trigger files on disk so existing_paths has 2
        # entries; partial_runner only returns 1 oid -> len mismatch.
        pkg_json = os.path.join(root, "package.json")
        with open(pkg_json, "w", encoding="utf-8") as fh:
            fh.write('{"name": "test"}\n')

        ci_dir = os.path.join(root, ".github", "workflows")
        os.makedirs(ci_dir, exist_ok=True)
        ci_yml = os.path.join(ci_dir, "ci.yml")
        with open(ci_yml, "w", encoding="utf-8") as fh:
            fh.write("name: CI\n")

        record = pl.new_record(
            "tech-stack",
            created="2026-06-26",
            entries=[
                {
                    "path": "package.json",
                    "hash": stored_oid,
                    "drift_trigger": True,
                    "claims": [],
                },
                {
                    "path": ".github/workflows/ci.yml",
                    "hash": stored_oid,
                    "drift_trigger": True,
                    "claims": [],
                },
            ],
        )
        pl.write_provenance(
            os.path.join(provenance_dir, "tech-stack.json"),
            record,
        )

        try:
            result = pl.startup_drift_line(root, runner=partial_runner)
        except Exception as exc:
            self.fail(
                f"startup_drift_line raised on partial-hash runner: {exc}"
            )

        self.assertEqual(
            result,
            "",
            "Partial hash result (1 of 2 existing paths hashed) must degrade "
            "to '' — not emit a false 'N stale source(s)' alarm for the "
            "un-hashed file",
        )


class ChangedScopeTest(unittest.TestCase):
    """AC-11: changed_scope returns ONLY the drifted paths for the given doc.

    Tests named to satisfy -k changed_scope.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _drift(self):
        """Two docs, each with one changed and one missing path (all distinct)."""
        return {
            "doc-alpha": [
                {"path": "package.json", "kind": "changed"},
                {"path": "src/auth.ts", "kind": "missing"},
            ],
            "doc-beta": [
                {"path": ".github/workflows/ci.yml", "kind": "changed"},
                {"path": "src/middleware.py", "kind": "missing"},
            ],
        }

    def _prov(self, doc):
        return {"doc": doc, "schema": 1, "entries": []}

    # ------------------------------------------------------------------
    # AC-11 core: per-doc locality
    # ------------------------------------------------------------------

    def test_changed_scope_returns_only_target_doc_paths(self):
        """AC-11: changed_scope for doc-alpha returns both of doc-alpha's paths
        (changed + missing) and NONE of doc-beta's paths."""
        result = pl.changed_scope(self._prov("doc-alpha"), self._drift())

        self.assertIn("package.json", result,
                      "changed_scope must include doc-alpha's 'changed' path")
        self.assertIn("src/auth.ts", result,
                      "changed_scope must include doc-alpha's 'missing' path")
        self.assertEqual(len(result), 2,
                         "changed_scope must return exactly doc-alpha's 2 paths")
        # Doc-beta paths must NOT appear
        self.assertNotIn(".github/workflows/ci.yml", result,
                         "changed_scope must NOT include doc-beta paths")
        self.assertNotIn("src/middleware.py", result,
                         "changed_scope must NOT include doc-beta paths")

    def test_changed_scope_preserves_drift_order(self):
        """AC-11: paths are returned in the order they appear under the doc in drift."""
        result = pl.changed_scope(self._prov("doc-alpha"), self._drift())
        self.assertEqual(result, ["package.json", "src/auth.ts"],
                         "changed_scope must preserve drift order for the doc")

    def test_changed_scope_doc_beta_isolation(self):
        """AC-11: changed_scope for doc-beta returns only doc-beta's paths,
        not doc-alpha's."""
        result = pl.changed_scope(self._prov("doc-beta"), self._drift())

        self.assertIn(".github/workflows/ci.yml", result)
        self.assertIn("src/middleware.py", result)
        self.assertEqual(len(result), 2)
        self.assertNotIn("package.json", result,
                         "changed_scope must NOT include doc-alpha paths when called for doc-beta")
        self.assertNotIn("src/auth.ts", result,
                         "changed_scope must NOT include doc-alpha paths when called for doc-beta")

    def test_changed_scope_no_drift_entry_returns_empty(self):
        """AC-11: if the doc has no entry in drift, changed_scope returns []."""
        result = pl.changed_scope(self._prov("doc-gamma"), self._drift())
        self.assertEqual(result, [], "Doc with no drift entry must return []")

    # ------------------------------------------------------------------
    # Degrade-not-fail: malformed inputs
    # ------------------------------------------------------------------

    def test_changed_scope_none_doc_provenance_returns_empty(self):
        """AC-11: None doc_provenance must return [] without raising."""
        try:
            result = pl.changed_scope(None, self._drift())
        except Exception as exc:
            self.fail(f"changed_scope raised on None doc_provenance: {exc}")
        self.assertEqual(result, [])

    def test_changed_scope_malformed_doc_provenance_no_doc_field_returns_empty(self):
        """AC-11: doc_provenance missing the 'doc' field must return [] without raising."""
        try:
            result = pl.changed_scope({"schema": 1}, self._drift())
        except Exception as exc:
            self.fail(f"changed_scope raised on provenance with no 'doc' field: {exc}")
        self.assertEqual(result, [])

    def test_changed_scope_malformed_drift_returns_empty(self):
        """AC-11: non-dict drift must return [] without raising."""
        try:
            result = pl.changed_scope(self._prov("doc-alpha"), "not-a-dict")
        except Exception as exc:
            self.fail(f"changed_scope raised on malformed drift: {exc}")
        self.assertEqual(result, [])


class RebaselineTest(unittest.TestCase):
    """AC-12: rebaseline(provenance, current_hashes) updates each entry's hash
    to current_hashes[path], leaves claims/doc/schema untouched, and a
    subsequent compute_drift returns {}.

    Tests named to satisfy -k rebaseline.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_claims(self):
        return [{"lines": "1-10", "claim": "Node 20 runtime declared", "confidence": "strong"}]

    def _entry(self, path, hash_, drift_trigger=True, claims=None):
        return {
            "path": path,
            "hash": hash_,
            "drift_trigger": drift_trigger,
            "claims": claims if claims is not None else self._make_claims(),
        }

    def _record(self, doc, entries):
        return pl.new_record(doc, entries=entries, created="2026-06-26")

    # ------------------------------------------------------------------
    # AC-12 core: hashes updated, claims/doc untouched, drift clears
    # ------------------------------------------------------------------

    def test_rebaseline_updates_each_entry_hash(self):
        """AC-12: rebaseline sets every entry's hash to current_hashes[path]."""
        old_oid_a = "aaaa1111111111111111111111111111aaaaaaaa"
        old_oid_b = "bbbb2222222222222222222222222222bbbbbbbb"
        new_oid_a = "aaaa9999999999999999999999999999aaaaaaaa"
        new_oid_b = "bbbb9999999999999999999999999999bbbbbbbb"

        entries = [
            self._entry("package.json", old_oid_a),
            self._entry("src/auth.ts", old_oid_b),
        ]
        record = self._record("tech-stack", entries)
        current_hashes = {"package.json": new_oid_a, "src/auth.ts": new_oid_b}

        rebaselined = pl.rebaseline(record, current_hashes)

        by_path = {e["path"]: e for e in rebaselined["entries"]}
        self.assertEqual(by_path["package.json"]["hash"], new_oid_a,
                         "package.json hash must equal the new current oid")
        self.assertEqual(by_path["src/auth.ts"]["hash"], new_oid_b,
                         "src/auth.ts hash must equal the new current oid")

    def test_rebaseline_leaves_claims_byte_for_byte_unchanged(self):
        """AC-12: rebaseline must not modify claims on any entry."""
        old_oid = "cccc1111111111111111111111111111cccccccc"
        new_oid = "cccc9999999999999999999999999999cccccccc"
        claims = [{"lines": "10-20", "claim": "specific claim text", "confidence": "strong"}]

        entries = [
            self._entry("package.json", old_oid, claims=claims),
            self._entry("src/auth.ts", old_oid, claims=claims),
        ]
        record = self._record("tech-stack", entries)
        current_hashes = {"package.json": new_oid, "src/auth.ts": new_oid}

        rebaselined = pl.rebaseline(record, current_hashes)

        for entry in rebaselined["entries"]:
            self.assertEqual(entry["claims"], claims,
                             f"claims on {entry['path']} must be byte-for-byte unchanged")

    def test_rebaseline_leaves_doc_field_unchanged(self):
        """AC-12: record's doc field must be unchanged after rebaseline."""
        old_oid = "dddd1111111111111111111111111111dddddddd"
        new_oid = "dddd9999999999999999999999999999dddddddd"
        record = self._record("tech-stack", [self._entry("package.json", old_oid)])
        current_hashes = {"package.json": new_oid}

        rebaselined = pl.rebaseline(record, current_hashes)

        self.assertEqual(rebaselined["doc"], "tech-stack",
                         "record's doc field must be unchanged")
        self.assertEqual(rebaselined["schema"], record["schema"],
                         "record's schema field must be unchanged")
        self.assertEqual(rebaselined["created"], record["created"],
                         "record's created field must be unchanged")
        self.assertEqual(rebaselined["interview_derived"], record["interview_derived"],
                         "record's interview_derived field must be unchanged")

    def test_rebaseline_drift_clears(self):
        """AC-12 KEY ASSERTION: compute_drift returns {} after rebaseline."""
        old_oid = "eeee1111111111111111111111111111eeeeeeee"
        new_oid = "eeee9999999999999999999999999999eeeeeeee"

        entries = [
            self._entry("package.json", old_oid),
            self._entry("src/auth.ts", old_oid),
        ]
        record = self._record("tech-stack", entries)
        current_hashes = {"package.json": new_oid, "src/auth.ts": new_oid}

        rebaselined = pl.rebaseline(record, current_hashes)

        drift = pl.compute_drift({rebaselined["doc"]: rebaselined}, current_hashes)
        self.assertEqual(drift, {},
                         "compute_drift must return {} on the rebaselined record (drift cleared)")

    # ------------------------------------------------------------------
    # Absent-path case: entry not in current_hashes keeps its old hash
    # ------------------------------------------------------------------

    def test_rebaseline_absent_path_keeps_old_hash(self):
        """AC-12: entry whose path is absent from current_hashes is left as-is."""
        old_oid_a = "ffff1111111111111111111111111111ffffffff"
        old_oid_b = "gggg2222222222222222222222222222gggggggg"
        new_oid_a = "ffff9999999999999999999999999999ffffffff"

        entries = [
            self._entry("package.json", old_oid_a),
            self._entry("src/auth.ts", old_oid_b),  # intentionally absent
        ]
        record = self._record("tech-stack", entries)
        # src/auth.ts deliberately NOT in current_hashes
        current_hashes = {"package.json": new_oid_a}

        rebaselined = pl.rebaseline(record, current_hashes)

        by_path = {e["path"]: e for e in rebaselined["entries"]}
        self.assertEqual(by_path["package.json"]["hash"], new_oid_a,
                         "package.json hash must be updated")
        self.assertEqual(by_path["src/auth.ts"]["hash"], old_oid_b,
                         "src/auth.ts hash must be unchanged (absent from current_hashes)")

    # ------------------------------------------------------------------
    # Functional-style: caller's input must not be mutated
    # ------------------------------------------------------------------

    def test_rebaseline_returns_new_record_does_not_mutate_input(self):
        """AC-12: rebaseline must not mutate the caller's input record."""
        old_oid = "hhhh1111111111111111111111111111hhhhhhhh"
        new_oid = "hhhh9999999999999999999999999999hhhhhhhh"
        entries = [self._entry("package.json", old_oid)]
        record = self._record("tech-stack", entries)
        current_hashes = {"package.json": new_oid}

        rebaselined = pl.rebaseline(record, current_hashes)

        # The original record's entry hash must be unchanged
        self.assertEqual(record["entries"][0]["hash"], old_oid,
                         "caller's input record must not be mutated by rebaseline")
        # The returned record must carry the updated hash
        self.assertEqual(rebaselined["entries"][0]["hash"], new_oid,
                         "returned record must carry the updated hash")
        # They must be distinct objects
        self.assertIsNot(record, rebaselined,
                         "rebaseline must return a new dict, not the original")

    # ------------------------------------------------------------------
    # Malformed / None input: never raise
    # ------------------------------------------------------------------

    def test_rebaseline_none_provenance_does_not_raise(self):
        """AC-12: None provenance must not raise; returns None."""
        try:
            result = pl.rebaseline(None, {"package.json": "some-oid"})
        except Exception as exc:
            self.fail(f"rebaseline raised on None provenance: {exc}")
        self.assertIsNone(result)

    def test_rebaseline_malformed_provenance_does_not_raise(self):
        """AC-12: non-dict provenance must not raise; returns input unchanged."""
        try:
            result = pl.rebaseline("not-a-dict", {"package.json": "some-oid"})
        except Exception as exc:
            self.fail(f"rebaseline raised on non-dict provenance: {exc}")
        self.assertEqual(result, "not-a-dict")

    def test_rebaseline_none_current_hashes_does_not_raise(self):
        """AC-12: None current_hashes must not raise."""
        old_oid = "iiii1111111111111111111111111111iiiiiiii"
        record = self._record("tech-stack", [self._entry("package.json", old_oid)])
        try:
            result = pl.rebaseline(record, None)
        except Exception as exc:
            self.fail(f"rebaseline raised on None current_hashes: {exc}")
        # No hashes provided — entry hash should remain unchanged
        self.assertIsNotNone(result)


class HealWorklistTest(unittest.TestCase):
    """AC-13: heal_worklist(staged_paths, provenance, current_hashes) -> list[str]

    Returns only staged paths that are drift_trigger:true entries with diverged
    hashes (or absent from current_hashes). Empty when no staged file is tracked
    — the cost guarantee that ordinary commits pay zero re-scout work.

    Tests named to satisfy -k heal_worklist.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _entry(self, path, hash_, drift_trigger=True):
        return {
            "path": path,
            "hash": hash_,
            "drift_trigger": drift_trigger,
            "claims": [],
        }

    def _record(self, doc, entries):
        return pl.new_record(doc, entries=entries, created="2026-06-26")

    def _provenance(self):
        """Two-doc provenance map covering several paths with mixed drift_trigger values."""
        return {
            "tech-stack": self._record("tech-stack", [
                self._entry("package.json", "pkg-stored-oid", drift_trigger=True),
                self._entry("src/auth.ts", "auth-stored-oid", drift_trigger=True),
                self._entry("src/impl.py", "impl-stored-oid", drift_trigger=False),
            ]),
            "coding-standards": self._record("coding-standards", [
                self._entry(".github/workflows/ci.yml", "ci-stored-oid", drift_trigger=True),
            ]),
        }

    # ------------------------------------------------------------------
    # AC-13 core: diverged drift_trigger:true entry IS included
    # ------------------------------------------------------------------

    def test_heal_worklist_diverged_drift_trigger_true_included(self):
        """AC-13: staged drift_trigger:true entry with a diverged hash IS in the worklist."""
        prov = self._provenance()
        staged = ["package.json", "src/auth.ts"]
        current_hashes = {
            "package.json": "pkg-NEW-oid",       # diverged → must be included
            "src/auth.ts": "auth-stored-oid",    # matches stored → must be excluded
        }

        result = pl.heal_worklist(staged, prov, current_hashes)

        self.assertIn("package.json", result,
                      "diverged drift_trigger:true entry must be in worklist")
        self.assertNotIn("src/auth.ts", result,
                         "matching drift_trigger:true entry must NOT be in worklist")

    # ------------------------------------------------------------------
    # AC-13: matching hash is NOT included
    # ------------------------------------------------------------------

    def test_heal_worklist_matching_hash_not_included(self):
        """AC-13: staged drift_trigger:true entry whose hash MATCHES is NOT in worklist."""
        prov = self._provenance()
        staged = ["package.json"]
        current_hashes = {
            "package.json": "pkg-stored-oid",  # exact match → excluded
        }

        result = pl.heal_worklist(staged, prov, current_hashes)

        self.assertNotIn("package.json", result,
                         "matching hash must not be in worklist")
        self.assertEqual(result, [])

    # ------------------------------------------------------------------
    # AC-13 anti-noise: drift_trigger:false entry is NEVER included
    # ------------------------------------------------------------------

    def test_heal_worklist_drift_trigger_false_not_included(self):
        """AC-13 anti-noise: staged drift_trigger:false entry must NOT be in worklist
        even when its hash is diverged."""
        prov = self._provenance()
        staged = ["src/impl.py"]
        current_hashes = {
            "src/impl.py": "impl-NEW-oid",  # diverged, but drift_trigger=False → excluded
        }

        result = pl.heal_worklist(staged, prov, current_hashes)

        self.assertNotIn("src/impl.py", result,
                         "drift_trigger:false entry must NOT be in worklist even when diverged")
        self.assertEqual(result, [])

    # ------------------------------------------------------------------
    # AC-13: staged path not in any provenance entry is NOT included
    # ------------------------------------------------------------------

    def test_heal_worklist_untracked_path_not_included(self):
        """AC-13: staged path not present in any provenance entry must NOT be in worklist."""
        prov = self._provenance()
        staged = ["untracked/file.ts"]
        current_hashes = {"untracked/file.ts": "some-oid"}

        result = pl.heal_worklist(staged, prov, current_hashes)

        self.assertNotIn("untracked/file.ts", result,
                         "path not in any provenance entry must not be in worklist")
        self.assertEqual(result, [])

    # ------------------------------------------------------------------
    # AC-13: staged drift_trigger path absent from current_hashes IS included
    # ------------------------------------------------------------------

    def test_heal_worklist_absent_from_current_hashes_included(self):
        """AC-13: staged drift_trigger:true path absent from current_hashes
        (staged deletion/rename) IS in the worklist."""
        prov = self._provenance()
        staged = ["package.json"]
        current_hashes = {}  # package.json absent → staged deletion

        result = pl.heal_worklist(staged, prov, current_hashes)

        self.assertIn("package.json", result,
                      "dt:true path absent from current_hashes must be included "
                      "(staged deletion/rename)")

    # ------------------------------------------------------------------
    # AC-13: empty staged_paths → []
    # ------------------------------------------------------------------

    def test_heal_worklist_empty_staged_paths_returns_empty(self):
        """AC-13: empty staged_paths → []."""
        prov = self._provenance()
        result = pl.heal_worklist([], prov, {"package.json": "some-oid"})
        self.assertEqual(result, [], "empty staged_paths must return []")

    # ------------------------------------------------------------------
    # AC-13 COST GUARANTEE: no staged file is a provenance entry → []
    # ------------------------------------------------------------------

    def test_heal_worklist_no_staged_file_is_provenance_entry_returns_empty(self):
        """AC-13 COST GUARANTEE: when no staged file appears in any provenance entry,
        heal_worklist must return [] — ordinary commits pay zero re-scout cost."""
        prov = self._provenance()
        staged = ["README.md", "src/newfeature.ts", "docs/guide.md"]
        current_hashes = {
            "README.md": "readme-oid",
            "src/newfeature.ts": "newfeature-oid",
            "docs/guide.md": "guide-oid",
        }

        result = pl.heal_worklist(staged, prov, current_hashes)

        self.assertEqual(
            result,
            [],
            "no staged file tracked as provenance entry → must return [] "
            "(cost guarantee: ordinary commit pays zero re-scout work)",
        )

    # ------------------------------------------------------------------
    # AC-13: staged_paths order preserved
    # ------------------------------------------------------------------

    def test_heal_worklist_order_preserved(self):
        """AC-13: output must preserve staged_paths order (not entry order)."""
        prov = self._provenance()
        # Both diverged; order in staged_paths is reversed relative to provenance entry order.
        staged = [".github/workflows/ci.yml", "package.json"]
        current_hashes = {
            ".github/workflows/ci.yml": "ci-NEW-oid",  # diverged
            "package.json": "pkg-NEW-oid",              # diverged
        }

        result = pl.heal_worklist(staged, prov, current_hashes)

        self.assertEqual(
            result,
            [".github/workflows/ci.yml", "package.json"],
            "worklist must preserve staged_paths order",
        )

    # ------------------------------------------------------------------
    # AC-13: dedup — same path twice in staged_paths appears once in output
    # ------------------------------------------------------------------

    def test_heal_worklist_dedup(self):
        """AC-13: if the same path appears twice in staged_paths, it must appear
        at most once in the output."""
        prov = self._provenance()
        staged = ["package.json", "package.json"]  # duplicate
        current_hashes = {"package.json": "pkg-NEW-oid"}  # diverged

        result = pl.heal_worklist(staged, prov, current_hashes)

        self.assertEqual(
            result.count("package.json"),
            1,
            "duplicate staged path must appear at most once in worklist",
        )

    # ------------------------------------------------------------------
    # AC-13: degrade-not-fail — malformed / None inputs → [] without raising
    # ------------------------------------------------------------------

    def test_heal_worklist_none_provenance_does_not_raise(self):
        """AC-13: None provenance must return [] without raising."""
        try:
            result = pl.heal_worklist(["package.json"], None, {"package.json": "oid"})
        except Exception as exc:
            self.fail(f"heal_worklist raised on None provenance: {exc}")
        self.assertEqual(result, [])

    def test_heal_worklist_malformed_provenance_does_not_raise(self):
        """AC-13: non-dict provenance must return [] without raising."""
        try:
            result = pl.heal_worklist(["package.json"], "not-a-dict", {"package.json": "oid"})
        except Exception as exc:
            self.fail(f"heal_worklist raised on non-dict provenance: {exc}")
        self.assertEqual(result, [])

    def test_heal_worklist_none_staged_paths_does_not_raise(self):
        """AC-13: None staged_paths must return [] without raising."""
        prov = self._provenance()
        try:
            result = pl.heal_worklist(None, prov, {"package.json": "oid"})
        except Exception as exc:
            self.fail(f"heal_worklist raised on None staged_paths: {exc}")
        self.assertEqual(result, [])


class LintCodeMapTest(unittest.TestCase):
    """AC-15: lint_code_map enforces module/concern granularity:
    entry cap and one-line-per-role rules.

    Tests named to satisfy -k lint_code_map.
    """

    # ------------------------------------------------------------------
    # Helper: build a code-map markdown string with n entries
    # ------------------------------------------------------------------

    @staticmethod
    def _make_map(n, concern="Auth"):
        """Build a code-map markdown string with n entries under one concern heading."""
        lines = ["## {}".format(concern)]
        for i in range(n):
            lines.append("- `path/to/module{}.py` -- role {}".format(i, i))
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # AC-15 happy path: clean small map -> []
    # ------------------------------------------------------------------

    def test_lint_code_map_clean_small(self):
        """AC-15: a clean small map (3 entries, well under cap) -> []."""
        text = (
            "## Auth\n"
            "- `src/auth.py` -- handles login\n"
            "- `src/token.py` -- manages tokens\n"
            "## Database\n"
            "- `src/db.py` -- database connection pool\n"
        )
        result = pl.lint_code_map(text)
        self.assertEqual(result, [], "clean small map must return []")

    # ------------------------------------------------------------------
    # AC-15: over-cap -> warning naming count and cap
    # ------------------------------------------------------------------

    def test_lint_code_map_over_cap(self):
        """AC-15: map with > CODE_MAP_MAX_ENTRIES entries -> warning naming count and cap.

        Builds cap+5 entries programmatically via pl.CODE_MAP_MAX_ENTRIES so
        the test survives a cap tweak without needing to hard-code 50.
        """
        n = pl.CODE_MAP_MAX_ENTRIES + 5
        text = self._make_map(n)
        result = pl.lint_code_map(text)
        self.assertTrue(
            len(result) >= 1,
            "over-cap map must produce at least one warning",
        )
        cap_warning = result[0]
        self.assertIn(str(n), cap_warning,
                      "warning must name the actual entry count")
        self.assertIn(str(pl.CODE_MAP_MAX_ENTRIES), cap_warning,
                      "warning must name the cap")
        self.assertIn("coarsen", cap_warning.lower(),
                      "warning must reference coarsening to module/concern granularity")
        # ASCII-only (Windows console safety)
        try:
            cap_warning.encode("ascii")
        except UnicodeEncodeError as exc:
            self.fail("cap warning is not ASCII-only: {}".format(exc))

    # ------------------------------------------------------------------
    # AC-15: multi-line role -> warning naming entry number and path
    # ------------------------------------------------------------------

    def test_lint_code_map_multi_line_role(self):
        """AC-15: entry bullet immediately followed by indented continuation line
        -> warning naming the offending entry path."""
        text = (
            "## Auth\n"
            "- `src/auth.py` -- handles login\n"
            "  and token refresh\n"   # indented continuation -> multi-line role
            "- `src/utils.py` -- utilities\n"
        )
        result = pl.lint_code_map(text)
        self.assertTrue(
            len(result) >= 1,
            "multi-line role must produce at least one warning",
        )
        warning = result[0]
        self.assertIn("multi-line", warning,
                      "warning must mention 'multi-line'")
        self.assertIn("src/auth.py", warning,
                      "warning must name the offending path")
        # Clean entry after the bad one must not itself trigger a warning
        paths_warned = [w for w in result if "src/utils.py" in w]
        self.assertEqual(paths_warned, [],
                         "the clean entry after the multi-line one must NOT be warned")

    # ------------------------------------------------------------------
    # AC-15 boundary: exactly at cap -> [] (not over the cap)
    # ------------------------------------------------------------------

    def test_lint_code_map_at_cap_clean(self):
        """AC-15 boundary: a clean map with exactly CODE_MAP_MAX_ENTRIES entries -> [].

        At the cap is not over the cap; must return [] (no warning).
        """
        text = self._make_map(pl.CODE_MAP_MAX_ENTRIES)
        result = pl.lint_code_map(text)
        self.assertEqual(result, [],
                         "map at exactly CODE_MAP_MAX_ENTRIES entries must return []")

    # ------------------------------------------------------------------
    # AC-15: None / empty -> [] without raising
    # ------------------------------------------------------------------

    def test_lint_code_map_none(self):
        """AC-15: None text -> [] without raising."""
        try:
            result = pl.lint_code_map(None)
        except Exception as exc:
            self.fail("lint_code_map raised on None: {}".format(exc))
        self.assertEqual(result, [], "None must return []")

    def test_lint_code_map_empty(self):
        """AC-15: empty string -> [] without raising."""
        try:
            result = pl.lint_code_map("")
        except Exception as exc:
            self.fail("lint_code_map raised on empty string: {}".format(exc))
        self.assertEqual(result, [], "empty string must return []")


class WriteStubTest(unittest.TestCase):
    """AC-18 (lib half): write_stub produces the greenfield stub shape:
    interview_derived=True, entries=[], schema set, doc set.

    Tests named to satisfy -k write_stub.
    """

    # ------------------------------------------------------------------
    # Happy path: correct stub shape written and round-tripped
    # ------------------------------------------------------------------

    def test_write_stub_happy_path(self):
        """write_stub(tmpfile, 'tech-stack') writes a valid provenance JSON stub:
        schema == pl.SCHEMA_VERSION, doc == 'tech-stack',
        interview_derived is True, entries == [].
        On-disk file is valid JSON. Tempfile is cleaned up.
        """
        import tempfile as _tf
        fd, path = _tf.mkstemp(suffix=".json")
        os.close(fd)
        try:
            pl.write_stub(path, "tech-stack")

            # Round-trip via read_provenance
            record = pl.read_provenance(path)
            self.assertIsNotNone(record, "read_provenance must return a dict after write_stub")

            # doc must be set correctly
            self.assertEqual(record["doc"], "tech-stack",
                             "write_stub must set doc='tech-stack'")

            # interview_derived must be True (identity check)
            self.assertIs(record["interview_derived"], True,
                          "write_stub must set interview_derived=True")

            # entries must be exactly [] (not missing, not None)
            self.assertIn("entries", record,
                          "entries key must be present in the stub JSON")
            self.assertEqual(record["entries"], [],
                             "write_stub entries must be exactly []")

            # schema must equal SCHEMA_VERSION
            self.assertEqual(record["schema"], pl.SCHEMA_VERSION,
                             "write_stub must set schema == pl.SCHEMA_VERSION")

            # On-disk file must be valid JSON (json.load succeeds)
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
            self.assertIsInstance(raw, dict,
                                  "on-disk file must be valid JSON producing a dict")
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Boundary: entries is exactly empty — not missing, not None
    # ------------------------------------------------------------------

    def test_write_stub_entries_exactly_empty_list(self):
        """write_stub entries must be exactly [] — not missing and not None.
        Asserts isinstance(entries, list) and len == 0 on the read-back record.
        """
        import tempfile as _tf
        fd, path = _tf.mkstemp(suffix=".json")
        os.close(fd)
        try:
            pl.write_stub(path, "coding-standards")
            record = pl.read_provenance(path)
            self.assertIsNotNone(record)
            entries = record.get("entries")
            self.assertIsNotNone(entries,
                                 "entries must not be None — must be []")
            self.assertIsInstance(entries, list,
                                  "entries must be a list, not any other type")
            self.assertEqual(len(entries), 0,
                             "entries list must have length 0 (exactly empty)")
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Parent-directory creation (delegates to write_provenance)
    # ------------------------------------------------------------------

    def test_write_stub_creates_parent_dirs(self):
        """write_stub creates intermediate parent directories via write_provenance."""
        import tempfile as _tf
        import shutil
        tmp = _tf.mkdtemp()
        try:
            path = os.path.join(tmp, ".codearbiter", ".provenance", "tech-stack.json")
            pl.write_stub(path, "tech-stack")
            record = pl.read_provenance(path)
            self.assertIsNotNone(record)
            self.assertIs(record["interview_derived"], True,
                          "stub written into nested dir must still have interview_derived=True")
            self.assertEqual(record["entries"], [])
        finally:
            shutil.rmtree(tmp, True)

    # ------------------------------------------------------------------
    # created kwarg passes through to new_record
    # ------------------------------------------------------------------

    def test_write_stub_created_passthrough(self):
        """write_stub passes the created kwarg through to new_record."""
        import tempfile as _tf
        fd, path = _tf.mkstemp(suffix=".json")
        os.close(fd)
        try:
            pl.write_stub(path, "tech-stack", created="2026-01-01")
            record = pl.read_provenance(path)
            self.assertIsNotNone(record)
            self.assertEqual(record["created"], "2026-01-01",
                             "created kwarg must propagate to the written record")
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # interview_derived kwarg is overridable (default True, but can be False)
    # ------------------------------------------------------------------

    def test_write_stub_interview_derived_kwarg_overridable(self):
        """write_stub interview_derived kwarg is overridable — defaults to True
        but the caller may pass False."""
        import tempfile as _tf
        fd, path = _tf.mkstemp(suffix=".json")
        os.close(fd)
        try:
            pl.write_stub(path, "tech-stack", interview_derived=False)
            record = pl.read_provenance(path)
            self.assertIsNotNone(record)
            self.assertIs(record["interview_derived"], False,
                         "overriding interview_derived=False must produce False in the stub")
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


class TimeoutHardeningTest(unittest.TestCase):
    """Timeout hardening — both subprocess.run call sites in _provenancelib carry
    timeout=GIT_TIMEOUT, preventing a hung git process from stalling SessionStart.

    Tests named to satisfy -k timeout.
    """

    # ------------------------------------------------------------------
    # Wiring proof: _default_hash_runner passes timeout=GIT_TIMEOUT
    # ------------------------------------------------------------------

    def test_timeout_wiring_default_hash_runner(self):
        """Wiring proof: _default_hash_runner must pass timeout=GIT_TIMEOUT kwarg
        to subprocess.run.

        Mocks subprocess.run so no real git call is made; inspects call_args.kwargs
        to assert that timeout== pl.GIT_TIMEOUT is present.
        RED before adding timeout= to _default_hash_runner; GREEN after.
        """
        from unittest.mock import patch, MagicMock

        mock_result = MagicMock()
        mock_result.stdout = "aabbcc1234567890aabbcc1234567890aabbcc12\n"

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            pl._default_hash_runner(["hash-object", "--stdin-paths"], "x.py\n")

        call_kwargs = mock_run.call_args.kwargs
        self.assertIn(
            "timeout",
            call_kwargs,
            "_default_hash_runner must pass a timeout= kwarg to subprocess.run",
        )
        self.assertEqual(
            call_kwargs["timeout"],
            pl.GIT_TIMEOUT,
            "_default_hash_runner must pass timeout=GIT_TIMEOUT to subprocess.run",
        )

    # ------------------------------------------------------------------
    # Wiring proof: root-bound runner from _make_root_runner passes timeout=GIT_TIMEOUT
    # ------------------------------------------------------------------

    def test_timeout_wiring_root_runner(self):
        """Wiring proof: the git -C root runner returned by _make_root_runner must
        pass timeout=GIT_TIMEOUT to subprocess.run.

        Calls pl._make_root_runner('/fake/root') to obtain the closure, then
        invokes it under a subprocess.run mock and inspects call_args.kwargs.
        RED before adding timeout= to the root-bound runner; GREEN after.
        """
        from unittest.mock import patch, MagicMock

        mock_result = MagicMock()
        mock_result.stdout = "aabbcc1234567890aabbcc1234567890aabbcc12\n"

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            runner = pl._make_root_runner("/fake/root")
            runner(["hash-object", "--stdin-paths"], "x.py\n")

        call_kwargs = mock_run.call_args.kwargs
        self.assertIn(
            "timeout",
            call_kwargs,
            "_make_root_runner runner must pass a timeout= kwarg to subprocess.run",
        )
        self.assertEqual(
            call_kwargs["timeout"],
            pl.GIT_TIMEOUT,
            "_make_root_runner runner must pass timeout=GIT_TIMEOUT to subprocess.run",
        )

    # ------------------------------------------------------------------
    # Behavioral degrade: TimeoutExpired into batch_hash → {} (no raise)
    # ------------------------------------------------------------------

    def test_timeout_degrade_batch_hash_timeout_expired(self):
        """Behavioral degrade: batch_hash with a runner that raises TimeoutExpired
        must return {} without raising.

        subprocess.TimeoutExpired is a subclass of Exception, so the existing
        'except Exception: return {}' in batch_hash already catches it — this
        test proves the degrade path works end-to-end without any logic change.
        """
        import subprocess

        def timeout_runner(args, stdin_text):
            raise subprocess.TimeoutExpired(cmd="git", timeout=5)

        result = pl.batch_hash(["package.json", "src/auth.ts"], runner=timeout_runner)
        self.assertEqual(
            result,
            {},
            "batch_hash must return {} when the runner raises TimeoutExpired "
            "(existing except Exception catches subprocess.TimeoutExpired)",
        )

    # ------------------------------------------------------------------
    # Behavioral degrade: TimeoutExpired into startup_drift_line → '' (no raise)
    # ------------------------------------------------------------------

    def test_timeout_degrade_startup_drift_line_timeout_expired(self):
        """Behavioral degrade: startup_drift_line must return '' (not a false alarm)
        when the runner raises TimeoutExpired for an existing drift_trigger file.

        Flow: TimeoutExpired → batch_hash returns {} (caught by except Exception)
        → len(current_hashes)==0 < len(existing_paths)==1 → AC-08 guard fires →
        startup_drift_line returns '' (degrade to silence, not a false alarm).
        No logic change required; the existing AC-08 guard already handles this.
        """
        import subprocess
        import shutil

        def timeout_runner(args, stdin_text):
            raise subprocess.TimeoutExpired(cmd="git", timeout=5)

        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        root = tmp
        provenance_dir = os.path.join(root, ".codearbiter", ".provenance")
        os.makedirs(provenance_dir, exist_ok=True)

        # Create a real drift_trigger file so existing_paths is non-empty.
        pkg_json = os.path.join(root, "package.json")
        with open(pkg_json, "w", encoding="utf-8") as fh:
            fh.write('{"name": "test"}\n')

        stored_oid = "1111111111111111111111111111111111111111"
        record = pl.new_record(
            "tech-stack",
            created="2026-06-26",
            entries=[
                {
                    "path": "package.json",
                    "hash": stored_oid,
                    "drift_trigger": True,
                    "claims": [],
                }
            ],
        )
        pl.write_provenance(
            os.path.join(provenance_dir, "tech-stack.json"),
            record,
        )

        try:
            result = pl.startup_drift_line(root, runner=timeout_runner)
        except Exception as exc:
            self.fail(
                f"startup_drift_line raised when runner raised TimeoutExpired: {exc}"
            )

        self.assertEqual(
            result,
            "",
            "startup_drift_line must return '' (not a false alarm) when the runner "
            "raises TimeoutExpired — a git hang degrades to silent, not a stall",
        )


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""codeArbiter — unit tests for the read-inject helper (_readinjectlib, T-01).

Proves allow_output(additional_context) builds the exact hookSpecificOutput
dict shape required by AC-03 of the file-scoped-context-injection spec:

  T-01  allow_output(s) returns exactly {"hookSpecificOutput": {"hookEventName":
        "PreToolUse", "permissionDecision": "allow", "additionalContext": s}};
        called with "" or None (coerced to ""), the dict is still well-formed
        and additionalContext is "".

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

import _readinjectlib as ril  # noqa: E402 — needs sys.path mutation above


class AllowOutputTest(unittest.TestCase):
    """T-01 / AC-03: allow_output builds the exact hookSpecificOutput dict."""

    HOOK_EVENT = "PreToolUse"
    DECISION = "allow"

    def _expected(self, ctx):
        return {
            "hookSpecificOutput": {
                "hookEventName": self.HOOK_EVENT,
                "permissionDecision": self.DECISION,
                "additionalContext": ctx,
            }
        }

    def test_allow_output_normal_string(self):
        """Normal string -> exact dict with additionalContext set to that string."""
        ctx = "security-controls.md governs this file — HTTPS only, secret via env."
        result = ril.allow_output(ctx)
        self.assertEqual(result, self._expected(ctx))

    def test_allow_output_empty_string(self):
        """Empty string -> well-formed dict with additionalContext ''."""
        result = ril.allow_output("")
        self.assertEqual(result, self._expected(""))

    def test_allow_output_none_coerced_to_empty(self):
        """None -> coerced to '' -> well-formed dict with additionalContext ''."""
        result = ril.allow_output(None)
        self.assertEqual(result, self._expected(""))

    def test_allow_output_always_allow(self):
        """permissionDecision is always 'allow', regardless of context value."""
        for ctx in ("something", "", None):
            result = ril.allow_output(ctx)
            decision = result["hookSpecificOutput"]["permissionDecision"]
            self.assertEqual(
                decision, "allow",
                "permissionDecision must be 'allow', got {!r} for ctx={!r}".format(
                    decision, ctx
                ),
            )

    def test_allow_output_always_pretooluse(self):
        """hookEventName is always 'PreToolUse', regardless of context value."""
        for ctx in ("something", "", None):
            result = ril.allow_output(ctx)
            event = result["hookSpecificOutput"]["hookEventName"]
            self.assertEqual(
                event, "PreToolUse",
                "hookEventName must be 'PreToolUse', got {!r} for ctx={!r}".format(
                    event, ctx
                ),
            )

    def test_allow_output_returns_dict(self):
        """allow_output must return a dict (not None, not raise)."""
        result = ril.allow_output("hello")
        self.assertIsInstance(result, dict)

    def test_allow_output_dict_shape_keys(self):
        """Outer dict has exactly key 'hookSpecificOutput'; inner has the three required keys."""
        result = ril.allow_output("test")
        self.assertIn("hookSpecificOutput", result)
        inner = result["hookSpecificOutput"]
        self.assertIsInstance(inner, dict)
        for key in ("hookEventName", "permissionDecision", "additionalContext"):
            self.assertIn(key, inner, "inner dict must contain key {!r}".format(key))

    def test_allow_output_never_raises_on_arbitrary_string(self):
        """allow_output must never raise even on unusual string input."""
        unusual_inputs = [
            "x" * 10000,
            "\x00\x01\x02",
            "unicode: 中文",
        ]
        for inp in unusual_inputs:
            try:
                result = ril.allow_output(inp)
            except Exception as exc:
                self.fail("allow_output raised on input {!r}: {}".format(inp[:40], exc))
            self.assertIsInstance(result, dict)


class TokenEstimateTest(unittest.TestCase):
    """T-02 / AC-08: token_estimate(s) == ceil(len(s) / 4); 0 for empty/None; never raises."""

    def test_none_returns_zero(self):
        """None -> 0."""
        self.assertEqual(ril.token_estimate(None), 0)

    def test_empty_string_returns_zero(self):
        """Empty string -> 0."""
        self.assertEqual(ril.token_estimate(""), 0)

    def test_single_char(self):
        """1 char: ceil(1/4) = 1."""
        self.assertEqual(ril.token_estimate("a"), 1)

    def test_exactly_four_chars(self):
        """4 chars: ceil(4/4) = 1."""
        self.assertEqual(ril.token_estimate("abcd"), 1)

    def test_five_chars(self):
        """5 chars: ceil(5/4) = 2."""
        self.assertEqual(ril.token_estimate("abcde"), 2)

    def test_eight_chars(self):
        """8 chars: ceil(8/4) = 2."""
        self.assertEqual(ril.token_estimate("a" * 8), 2)

    def test_exactly_budget_times_four(self):
        """600 chars (150*4): exactly 150 tokens — the default-budget boundary."""
        self.assertEqual(ril.token_estimate("x" * 600), 150)

    def test_one_over_budget(self):
        """601 chars: ceil(601/4) = 151, one token over default budget."""
        self.assertEqual(ril.token_estimate("x" * 601), 151)

    def test_never_raises(self):
        """Never raises on any input."""
        for inp in [None, "", "a", "x" * 10000, "中文", "\x00\x01"]:
            try:
                ril.token_estimate(inp)
            except Exception as exc:
                self.fail(
                    "token_estimate raised on {!r}: {}".format(repr(inp)[:40], exc)
                )


class AssembleContextTest(unittest.TestCase):
    """T-02 / AC-08: assemble_context(pointers, budget=150) assembles additionalContext."""

    # ------------------------------------------------------------------
    # Degenerate / empty inputs
    # ------------------------------------------------------------------

    def test_empty_list_returns_empty(self):
        """Empty list -> ''."""
        self.assertEqual(ril.assemble_context([]), "")

    def test_all_malformed_pointers_returns_empty(self):
        """All pointers with missing/None/non-string text -> ''."""
        pointers = [
            {},
            {"text": None},
            {"text": 42},
            {"text": ["a", "b"]},
        ]
        self.assertEqual(ril.assemble_context(pointers), "")

    def test_non_list_input_returns_empty_without_raising(self):
        """Non-list input (None, dict, str, int) -> '' without raising."""
        for bad in [None, "string", 42, {}]:
            try:
                result = ril.assemble_context(bad)
            except Exception as exc:
                self.fail(
                    "assemble_context raised on {!r}: {}".format(repr(bad)[:40], exc)
                )
            self.assertEqual(
                result, "", "Expected '' for {!r}, got {!r}".format(bad, result)
            )

    def test_non_dict_items_in_list_are_skipped(self):
        """Non-dict entries within the list are skipped; valid dicts are included."""
        pointers = ["not-a-dict", None, 42, {"text": "valid"}]
        self.assertEqual(ril.assemble_context(pointers), "valid")

    # ------------------------------------------------------------------
    # Happy-path: single and multiple under-budget pointers
    # ------------------------------------------------------------------

    def test_single_valid_pointer_returns_text(self):
        """Single under-budget pointer -> its text, no ellipsis."""
        text = "security-controls.md: HTTPS only, secret via env."
        result = ril.assemble_context([{"text": text}])
        self.assertEqual(result, text)

    def test_multiple_under_budget_joined_with_newline(self):
        """Multiple under-budget pointers -> joined with newline separators, no ellipsis."""
        pointers = [
            {"text": "A: security note"},
            {"text": "B: decision note"},
            {"text": "C: spec note"},
        ]
        self.assertEqual(
            ril.assemble_context(pointers),
            "A: security note\nB: decision note\nC: spec note",
        )

    def test_priority_order_preserved(self):
        """Input order is preserved: front pointer text appears before later pointer text."""
        pointers = [{"text": "First"}, {"text": "Second"}, {"text": "Third"}]
        result = ril.assemble_context(pointers)
        self.assertLess(result.index("First"), result.index("Second"))
        self.assertLess(result.index("Second"), result.index("Third"))

    def test_under_budget_no_ellipsis(self):
        """Under-budget result must NOT end with the ellipsis marker."""
        pointers = [{"text": "short"}, {"text": "note"}]
        result = ril.assemble_context(pointers)
        self.assertFalse(
            result.endswith("…"),
            "Under-budget result must not carry a trailing '…'",
        )

    def test_exact_budget_boundary_no_ellipsis(self):
        """Pointer whose text is exactly budget*4 chars (150 tokens) fits without ellipsis."""
        text = "x" * 600  # 600 chars == 150 tokens == budget
        result = ril.assemble_context([{"text": text}], budget=150)
        self.assertEqual(result, text)
        self.assertLessEqual(ril.token_estimate(result), 150)

    # ------------------------------------------------------------------
    # Budget cap: truncation with trailing ellipsis
    # ------------------------------------------------------------------

    def test_over_budget_ends_with_ellipsis(self):
        """Over-budget result MUST end with the ellipsis marker '…'."""
        # 5 * 200 chars = 1000 chars => 250 tokens, well over 150
        pointers = [{"text": "x" * 200} for _ in range(5)]
        result = ril.assemble_context(pointers)
        self.assertTrue(
            result.endswith("…"),
            "Over-budget result must end with '…', got: {!r}".format(result[-10:]),
        )

    def test_over_budget_token_estimate_within_budget(self):
        """Truncated result's token_estimate must be <= 150."""
        pointers = [{"text": "x" * 200} for _ in range(5)]
        result = ril.assemble_context(pointers)
        self.assertLessEqual(
            ril.token_estimate(result),
            150,
            "token_estimate({!r}…) = {} > 150".format(result[:20], ril.token_estimate(result)),
        )

    def test_first_pointer_over_budget_truncates_with_content(self):
        """T-10 fix: if even the first pointer exceeds budget, its text is truncated
        and content is preserved — the result is never a bare '…' marker.

        Before the T-10 fix, assemble_context([{'text': 'x'*601}], budget=150)
        returned a bare '…' (all content silently lost).  After the fix it returns
        'x'*599 + '…' — the highest-priority governing note is truncated but present.
        token_estimate of the result must still be <= budget.
        """
        pointers = [{"text": "x" * 601}]  # 601 chars = 151 tokens > 150
        result = ril.assemble_context(pointers, budget=150)
        # Must not be a bare ellipsis (pre-fix bug).
        self.assertNotEqual(
            result, "…",
            "bare '…' means the highest-priority pointer's content was silently lost",
        )
        # Must contain the first pointer's content.
        self.assertTrue(
            result.startswith("x"),
            "truncated result must start with first-pointer content, not a bare '…'",
        )
        # Must end with the ellipsis marker.
        self.assertTrue(result.endswith("…"))
        # Must still satisfy the token budget.
        self.assertLessEqual(ril.token_estimate(result), 150)

    def test_front_pointers_included_when_truncating(self):
        """When truncating, highest-priority (front) pointers are included first."""
        # P1: 400 chars (100 tokens) fits alone.
        # P1 + sep + P2: 801 chars (ceil=201 tokens) > 150 — P2 excluded.
        pointers = [{"text": "A" * 400}, {"text": "B" * 400}]
        result = ril.assemble_context(pointers, budget=150)
        self.assertTrue(
            result.startswith("A"),
            "Front pointer's text must appear first in the result",
        )
        self.assertTrue(result.endswith("…"))
        self.assertLessEqual(ril.token_estimate(result), 150)

    def test_custom_budget_respected(self):
        """budget parameter overrides default 150; result must be <= custom budget tokens."""
        # P1: 8 chars (2 tokens) fits in budget=3.
        # P1 + sep + P2: 17 chars (ceil=5 tokens) > 3.
        pointers = [{"text": "A" * 8}, {"text": "B" * 8}, {"text": "C" * 8}]
        result = ril.assemble_context(pointers, budget=3)
        self.assertLessEqual(ril.token_estimate(result), 3)
        self.assertTrue(result.endswith("…"))

    # ------------------------------------------------------------------
    # Malformed pointer skip
    # ------------------------------------------------------------------

    def test_skip_pointer_missing_text_key(self):
        """Pointer missing the 'text' key is skipped; others are included."""
        pointers = [{"summary": "irrelevant"}, {"text": "valid note"}]
        self.assertEqual(ril.assemble_context(pointers), "valid note")

    def test_skip_pointer_with_none_text(self):
        """Pointer with text=None is skipped; others are included."""
        pointers = [{"text": None}, {"text": "keep this"}]
        self.assertEqual(ril.assemble_context(pointers), "keep this")

    def test_skip_pointer_with_nonstring_text(self):
        """Pointer with non-string text value is skipped; others are included."""
        pointers = [{"text": 123}, {"text": "keep this"}]
        self.assertEqual(ril.assemble_context(pointers), "keep this")

    # ------------------------------------------------------------------
    # Never raises
    # ------------------------------------------------------------------

    def test_never_raises(self):
        """assemble_context never raises, even on garbage input."""
        bad_inputs = [
            None,
            "string",
            42,
            {},
            [None, "a", {"text": None}, {"text": 42}],
        ]
        for inp in bad_inputs:
            try:
                ril.assemble_context(inp)
            except Exception as exc:
                self.fail(
                    "assemble_context raised on {!r}: {}".format(repr(inp)[:40], exc)
                )


class SecurityPointerTest(unittest.TestCase):
    """T-03 / AC-04: security_pointer(path) — tier 1 file→knowledge map.

    Returns a pointer dict {text, tier} for a security-entry path (auth/
    middleware/jwt) and None otherwise.  Reuses _provenancelib's token
    machinery; whole-token rule prevents "author"/"AuthorCard" from firing.
    Pure; never raises.
    """

    # ------------------------------------------------------------------
    # Happy path: security-entry paths that must produce a pointer
    # ------------------------------------------------------------------

    def test_auth_jwt_returns_pointer(self):
        """src/auth/jwt.ts → pointer dict with tier and non-empty text mentioning security-controls."""
        result = ril.security_pointer("src/auth/jwt.ts")
        self.assertIsNotNone(result, "src/auth/jwt.ts must return a pointer, not None")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("tier"), "security-controls")
        text = result.get("text", "")
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 0, "pointer text must be non-empty")
        self.assertIn(
            "security-controls",
            text,
            "pointer text must mention 'security-controls'",
        )

    def test_middleware_cors_returns_pointer(self):
        """src/middleware/cors.py → pointer via 'middleware' token."""
        result = ril.security_pointer("src/middleware/cors.py")
        self.assertIsNotNone(result, "middleware path must return a pointer")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("tier"), "security-controls")

    # ------------------------------------------------------------------
    # Non-security paths that must return None
    # ------------------------------------------------------------------

    def test_ui_button_returns_none(self):
        """src/ui/Button.tsx → None (non-security path)."""
        self.assertIsNone(ril.security_pointer("src/ui/Button.tsx"))

    def test_package_json_returns_none(self):
        """package.json → None.

        package.json is a drift_trigger (classify_source returns True) but it
        is NOT a security-entry — it matches _DRIFT_FIXED_NAMES, not
        _SECURITY_ENTRY_TOKENS.  This test locks the scoping decision: tier 1
        must NOT fire on manifests, only on auth/middleware/jwt files.
        """
        self.assertIsNone(
            ril.security_pointer("package.json"),
            "package.json must return None — it is a drift_trigger but not a security-entry",
        )

    # ------------------------------------------------------------------
    # Whole-token rule: "author"/"Author" must NOT match "auth"
    # ------------------------------------------------------------------

    def test_author_py_returns_none(self):
        """author.py → None — whole-token rule: 'author' != 'auth'."""
        self.assertIsNone(
            ril.security_pointer("author.py"),
            "author.py must return None — 'author' is not a security-entry token",
        )

    def test_author_card_tsx_returns_none(self):
        """AuthorCard.tsx → None — camelCase split gives 'Author'/'Card', neither is 'auth'."""
        self.assertIsNone(
            ril.security_pointer("AuthorCard.tsx"),
            "AuthorCard.tsx must return None — 'Author'/'Card' are not security-entry tokens",
        )

    # ------------------------------------------------------------------
    # None and garbage inputs: must return None, never raise
    # ------------------------------------------------------------------

    def test_none_path_returns_none(self):
        """None → None without raising."""
        try:
            result = ril.security_pointer(None)
        except Exception as exc:
            self.fail("security_pointer(None) raised: {}".format(exc))
        self.assertIsNone(result)

    def test_garbage_value_returns_none(self):
        """A non-string garbage value → None without raising."""
        try:
            result = ril.security_pointer(42)
        except Exception as exc:
            self.fail("security_pointer(42) raised: {}".format(exc))
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # Token budget: pointer text must be short enough
    # ------------------------------------------------------------------

    def test_text_within_token_budget(self):
        """pointer['text'] must satisfy token_estimate(text) <= 150."""
        result = ril.security_pointer("src/auth/jwt.ts")
        self.assertIsNotNone(result)
        text = result["text"]
        est = ril.token_estimate(text)
        self.assertLessEqual(
            est,
            150,
            "pointer text token_estimate={} exceeds 150-token budget".format(est),
        )


class AdrIndexTest(unittest.TestCase):
    """T-04 / AC-05: accepted_adr_index(root) + adr_pointers(rel, index) — tier 2.

    accepted_adr_index: filesystem reader that scans .codearbiter/decisions/ for
    [0-9]+-.+\\.md files; returns entries ONLY when status == 'accepted' (case-
    insensitive) AND governs: is non-empty.

    adr_pointers: pure function; fnmatch-matches rel against each index entry's
    globs and returns a pointer dict per match.

    CRITICAL STATUS RULE: ONLY 'accepted' is kept. 'superseded', 'rejected',
    'draft', 'proposed', and missing status are ALL excluded — stricter than
    post-write-edit.py's governs_index (which keeps anything not in
    {superseded, rejected}).
    """

    # ------------------------------------------------------------------
    # Fixture helpers
    # ------------------------------------------------------------------

    def _decisions_dir(self, tmpdir):
        """Return the decisions dir path, creating it if needed."""
        ddir = os.path.join(tmpdir, ".codearbiter", "decisions")
        os.makedirs(ddir, exist_ok=True)
        return ddir

    def _write_adr(self, tmpdir, filename, status=None, title="", governs=None):
        """Write a synthetic ADR file into tmpdir/.codearbiter/decisions/."""
        ddir = self._decisions_dir(tmpdir)
        lines = ["---\n"]
        if title:
            lines.append("title: {}\n".format(title))
        if status is not None:
            lines.append("status: {}\n".format(status))
        if governs is not None:
            lines.append("governs: {}\n".format(governs))
        lines.append("---\n\n# Body\n")
        path = os.path.join(ddir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    # ------------------------------------------------------------------
    # Happy path: accepted ADR with a governs glob
    # ------------------------------------------------------------------

    def test_accepted_adr_matched_path_returns_pointer(self):
        """ADR with status:accepted + governs:plugins/ca/tools/farm.ts → pointer naming
        ADR-0003 and title when rel=plugins/ca/tools/farm.ts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_adr(
                tmpdir, "0003-x.md",
                status="accepted",
                title="HTTPS and secret handling",
                governs="plugins/ca/tools/farm.ts",
            )
            index = ril.accepted_adr_index(tmpdir)
            self.assertEqual(len(index), 1, "accepted ADR must be indexed")
            self.assertEqual(index[0]["adr"], "0003")
            self.assertEqual(index[0]["title"], "HTTPS and secret handling")
            pointers = ril.adr_pointers("plugins/ca/tools/farm.ts", index)
            self.assertEqual(len(pointers), 1)
            p = pointers[0]
            self.assertIn("ADR-0003", p["text"])
            self.assertIn("HTTPS and secret handling", p["text"])
            self.assertEqual(p["tier"], "decisions")

    def test_accepted_adr_unmatched_path_returns_empty(self):
        """ADR with status:accepted and governs:plugins/ca/tools/farm.ts → [] for src/other.py."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_adr(
                tmpdir, "0003-x.md",
                status="accepted",
                title="HTTPS and secret handling",
                governs="plugins/ca/tools/farm.ts",
            )
            index = ril.accepted_adr_index(tmpdir)
            pointers = ril.adr_pointers("src/other.py", index)
            self.assertEqual(pointers, [])

    def test_pointer_tier_is_decisions(self):
        """Each returned pointer must have tier == 'decisions'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_adr(
                tmpdir, "0003-x.md",
                status="accepted",
                title="Tier check",
                governs="some/path.ts",
            )
            index = ril.accepted_adr_index(tmpdir)
            pointers = ril.adr_pointers("some/path.ts", index)
            self.assertEqual(len(pointers), 1)
            self.assertEqual(pointers[0]["tier"], "decisions")

    # ------------------------------------------------------------------
    # CRITICAL: stricter than post-write-edit.py — accepted ONLY
    # ------------------------------------------------------------------

    def test_superseded_adr_never_in_index(self):
        """ADR with status:superseded is EXCLUDED from the index even when governs matches.
        This locks the accepted-only rule vs. post-write-edit.py which keeps
        any status not in {superseded, rejected}.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_adr(
                tmpdir, "0009-y.md",
                status="superseded",
                title="Old approach",
                governs="plugins/ca/tools/farm.ts",
            )
            index = ril.accepted_adr_index(tmpdir)
            self.assertEqual(index, [], "superseded ADR must NOT appear in the index")
            pointers = ril.adr_pointers("plugins/ca/tools/farm.ts", index)
            self.assertEqual(
                pointers, [],
                "adr_pointers must return [] for a superseded-excluded index",
            )

    def test_rejected_adr_not_in_index(self):
        """ADR with status:rejected is excluded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_adr(
                tmpdir, "0010-rejected.md",
                status="rejected",
                title="Rejected ADR",
                governs="plugins/ca/tools/farm.ts",
            )
            index = ril.accepted_adr_index(tmpdir)
            self.assertEqual(index, [])

    def test_draft_status_not_in_index(self):
        """ADR with status:draft is NOT in the index (unlike post-write-edit.py which would
        include it — this is the stricter accepted-only predicate)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_adr(
                tmpdir, "0005-draft.md",
                status="draft",
                title="Draft ADR",
                governs="plugins/ca/tools/farm.ts",
            )
            index = ril.accepted_adr_index(tmpdir)
            self.assertEqual(index, [], "draft ADR must NOT appear in the index")

    def test_proposed_status_not_in_index(self):
        """ADR with status:proposed is NOT in the index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_adr(
                tmpdir, "0006-proposed.md",
                status="proposed",
                title="Proposed ADR",
                governs="plugins/ca/tools/farm.ts",
            )
            index = ril.accepted_adr_index(tmpdir)
            self.assertEqual(index, [])

    def test_missing_status_not_in_index(self):
        """ADR with no status line is NOT in the index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_adr(
                tmpdir, "0007-nostatus.md",
                status=None,
                title="No status ADR",
                governs="plugins/ca/tools/farm.ts",
            )
            index = ril.accepted_adr_index(tmpdir)
            self.assertEqual(index, [], "ADR with no status must not appear in the index")

    def test_status_accepted_case_insensitive(self):
        """status: ACCEPTED (upper-case) is treated as accepted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_adr(
                tmpdir, "0011-upper.md",
                status="ACCEPTED",
                title="Upper Case Status",
                governs="some/path.ts",
            )
            index = ril.accepted_adr_index(tmpdir)
            self.assertEqual(len(index), 1, "ACCEPTED (uppercase) must be indexed")

    # ------------------------------------------------------------------
    # Robustness: missing dir, malformed files, no governs
    # ------------------------------------------------------------------

    def test_missing_decisions_dir_returns_empty_no_raise(self):
        """Missing .codearbiter/decisions/ dir → [] without raising."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Deliberately NOT creating .codearbiter/decisions/
            try:
                result = ril.accepted_adr_index(tmpdir)
            except Exception as exc:
                self.fail(
                    "accepted_adr_index raised on missing decisions dir: {}".format(exc)
                )
            self.assertEqual(result, [])

    def test_malformed_file_skipped_no_raise(self):
        """A file with binary garbage is skipped; other valid ADRs are still indexed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ddir = self._decisions_dir(tmpdir)
            # Write binary non-UTF-8 garbage (will be read with errors='replace')
            with open(os.path.join(ddir, "0001-garbage.md"), "wb") as f:
                f.write(b"\xff\xfe\x80\x81garbage\xff\x00")
            # Write a second valid accepted ADR
            self._write_adr(
                tmpdir, "0002-valid.md",
                status="accepted",
                title="Valid ADR",
                governs="some/path.ts",
            )
            try:
                index = ril.accepted_adr_index(tmpdir)
            except Exception as exc:
                self.fail(
                    "accepted_adr_index raised on malformed file: {}".format(exc)
                )
            # The garbage file is skipped; the valid one is indexed
            self.assertEqual(
                len(index), 1,
                "Valid ADR must still be indexed when malformed file is present",
            )
            self.assertEqual(index[0]["adr"], "0002")

    def test_adr_without_governs_line_not_indexed(self):
        """ADR with status:accepted but no governs: line is not indexed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_adr(
                tmpdir, "0004-nogoverns.md",
                status="accepted",
                title="No Governs ADR",
                governs=None,
            )
            index = ril.accepted_adr_index(tmpdir)
            self.assertEqual(index, [], "ADR with no governs: must not be indexed")

    def test_non_matching_filenames_ignored(self):
        """Files not matching [0-9]+-.+\\.md pattern are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ddir = self._decisions_dir(tmpdir)
            # decision-log.md does not match the numeric-prefix pattern
            with open(os.path.join(ddir, "decision-log.md"), "w", encoding="utf-8") as f:
                f.write("status: accepted\ngoverns: some/path.ts\ntitle: ignored\n")
            index = ril.accepted_adr_index(tmpdir)
            self.assertEqual(index, [])

    # ------------------------------------------------------------------
    # Glob matching: wildcards
    # ------------------------------------------------------------------

    def test_wildcard_glob_matches(self):
        """governs: plugins/ca/tools/*.ts matches plugins/ca/tools/farm.ts via fnmatch."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_adr(
                tmpdir, "0003-x.md",
                status="accepted",
                title="Wildcard match",
                governs="plugins/ca/tools/*.ts",
            )
            index = ril.accepted_adr_index(tmpdir)
            pointers = ril.adr_pointers("plugins/ca/tools/farm.ts", index)
            self.assertEqual(len(pointers), 1)
            self.assertIn("ADR-0003", pointers[0]["text"])

    def test_multiple_accepted_adrs_multiple_pointers(self):
        """Multiple accepted ADRs with matching globs → multiple pointers returned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_adr(
                tmpdir, "0003-a.md",
                status="accepted",
                title="First ADR",
                governs="src/api/handler.ts",
            )
            self._write_adr(
                tmpdir, "0008-b.md",
                status="accepted",
                title="Second ADR",
                governs="src/api/handler.ts",
            )
            index = ril.accepted_adr_index(tmpdir)
            self.assertEqual(len(index), 2)
            pointers = ril.adr_pointers("src/api/handler.ts", index)
            self.assertEqual(len(pointers), 2)
            texts = [p["text"] for p in pointers]
            self.assertTrue(any("ADR-0003" in t for t in texts))
            self.assertTrue(any("ADR-0008" in t for t in texts))

    # ------------------------------------------------------------------
    # Token budget
    # ------------------------------------------------------------------

    def test_pointer_text_within_token_budget(self):
        """Every returned pointer's token_estimate(text) must be <= 150."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_adr(
                tmpdir, "0003-x.md",
                status="accepted",
                title="HTTPS and secret handling",
                governs="plugins/ca/tools/farm.ts",
            )
            index = ril.accepted_adr_index(tmpdir)
            pointers = ril.adr_pointers("plugins/ca/tools/farm.ts", index)
            for p in pointers:
                est = ril.token_estimate(p["text"])
                self.assertLessEqual(
                    est, 150,
                    "pointer text token_estimate={} exceeds 150-token budget".format(est),
                )

    # ------------------------------------------------------------------
    # adr_pointers robustness
    # ------------------------------------------------------------------

    def test_adr_pointers_empty_index_returns_empty(self):
        """adr_pointers with empty index → []."""
        self.assertEqual(ril.adr_pointers("plugins/ca/tools/farm.ts", []), [])

    def test_adr_pointers_none_index_returns_empty_no_raise(self):
        """adr_pointers with None index → [] without raising."""
        try:
            result = ril.adr_pointers("plugins/ca/tools/farm.ts", None)
        except Exception as exc:
            self.fail("adr_pointers raised on None index: {}".format(exc))
        self.assertEqual(result, [])

    def test_adr_pointers_garbage_index_returns_empty_no_raise(self):
        """adr_pointers with non-list garbage → [] without raising."""
        for bad in ["string", 42, {}, object()]:
            try:
                result = ril.adr_pointers("some/path.py", bad)
            except Exception as exc:
                self.fail(
                    "adr_pointers raised on index={!r}: {}".format(repr(bad)[:40], exc)
                )
            self.assertEqual(result, [])

    def test_adr_pointers_none_rel_returns_empty(self):
        """adr_pointers with None rel → []."""
        index = [{"adr": "0003", "title": "T", "globs": ["*"]}]
        result = ril.adr_pointers(None, index)
        self.assertEqual(result, [])

    def test_adr_pointers_empty_rel_returns_empty(self):
        """adr_pointers with empty rel → []."""
        index = [{"adr": "0003", "title": "T", "globs": ["*"]}]
        result = ril.adr_pointers("", index)
        self.assertEqual(result, [])

    def test_accepted_adr_index_never_raises_on_garbage_root(self):
        """accepted_adr_index never raises on None or garbage root."""
        for bad in [None, "", 42, "/no/such/path/xyz123"]:
            try:
                result = ril.accepted_adr_index(bad)
            except Exception as exc:
                self.fail(
                    "accepted_adr_index raised on root={!r}: {}".format(
                        repr(bad)[:40], exc
                    )
                )
            self.assertIsInstance(result, list)


class SpecIndexTest(unittest.TestCase):
    """T-05 / AC-06 / AC-13: parse_spec_governs + approved_spec_index + spec_pointers.

    Tier-3 maps APPROVED specs (status begins with "approved") to source files via
    a **Governs:** header line.

      parse_spec_governs  — PURE: extracts the Governs glob list from spec text.
      approved_spec_index — FS reader: approved + non-empty-governs only.
      spec_pointers       — PURE matcher: fnmatch against rel path.

    Fixtures used:
      alpha.md — status:approved + Governs line → enrolled; matched path → pointer.
      beta.md  — status:approved but NO Governs line → not enrolled (AC-06).
      gamma.md — Governs line but status:draft → NOT enrolled (approved-only gate).
      delta.md — inline status (·-delimited header) → enrolled (AC-13).
    """

    # ------------------------------------------------------------------
    # Fixture helpers
    # ------------------------------------------------------------------

    def _specs_dir(self, tmpdir):
        """Return the specs dir path, creating it if needed."""
        sdir = os.path.join(tmpdir, ".codearbiter", "specs")
        os.makedirs(sdir, exist_ok=True)
        return sdir

    def _write_spec(self, tmpdir, filename, header_lines=None, body="# Body\n"):
        """Write a synthetic spec .md file into tmpdir/.codearbiter/specs/."""
        sdir = self._specs_dir(tmpdir)
        content = ("\n".join(header_lines) + "\n\n") if header_lines else ""
        content += body
        path = os.path.join(sdir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    # ------------------------------------------------------------------
    # parse_spec_governs — pure parser
    # ------------------------------------------------------------------

    def test_parse_spec_governs_single_glob(self):
        """Single-glob Governs line -> list containing that glob."""
        text = "**Governs:** plugins/ca/hooks/pre-read.py\n"
        self.assertEqual(
            ril.parse_spec_governs(text), ["plugins/ca/hooks/pre-read.py"]
        )

    def test_parse_spec_governs_multiple_globs(self):
        """Comma-separated globs -> list of stripped globs, empties dropped."""
        text = "**Governs:** a/b.py, c/d.ts ,  e/f.js\n"
        self.assertEqual(
            ril.parse_spec_governs(text), ["a/b.py", "c/d.ts", "e/f.js"]
        )

    def test_parse_spec_governs_no_governs_line_returns_empty(self):
        """AC-06 / beta fixture: text with NO **Governs:** line -> []."""
        text = "**Status:** approved (2026-06-26)\n\n# Body\n"
        self.assertEqual(ril.parse_spec_governs(text), [])

    def test_parse_spec_governs_case_insensitive_word(self):
        """**GOVERNS:** is treated the same as **Governs:** (case-insensitive)."""
        text = "**GOVERNS:** some/path.ts\n"
        self.assertEqual(ril.parse_spec_governs(text), ["some/path.ts"])

    def test_parse_spec_governs_empties_dropped(self):
        """Trailing comma or double comma -> empty entries dropped."""
        text = "**Governs:** a.py, , b.py,\n"
        self.assertEqual(ril.parse_spec_governs(text), ["a.py", "b.py"])

    def test_parse_spec_governs_non_string_returns_empty_no_raise(self):
        """Non-string input -> [] without raising."""
        for bad in [None, 42, [], {}]:
            try:
                result = ril.parse_spec_governs(bad)
            except Exception as exc:
                self.fail(
                    "parse_spec_governs raised on {!r}: {}".format(repr(bad)[:40], exc)
                )
            self.assertEqual(result, [], "Expected [] for {!r}".format(bad))

    def test_parse_spec_governs_returns_first_match(self):
        """When multiple **Governs:** lines are present, only the FIRST is used."""
        text = "**Governs:** first/path.py\n**Governs:** second/path.py\n"
        result = ril.parse_spec_governs(text)
        self.assertEqual(result, ["first/path.py"])

    # ------------------------------------------------------------------
    # alpha fixture: approved spec with Governs -> pointer for matched path
    # ------------------------------------------------------------------

    def test_alpha_approved_spec_in_index(self):
        """AC-06 / alpha: status:approved + Governs -> spec appears in index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_spec(
                tmpdir, "alpha.md",
                header_lines=[
                    "**Status:** approved (2026-06-26)",
                    "**Governs:** plugins/ca/hooks/pre-read.py",
                ],
            )
            index = ril.approved_spec_index(tmpdir)
            self.assertEqual(len(index), 1, "alpha must be in the index")
            self.assertEqual(index[0]["spec"], "alpha")
            self.assertIn("plugins/ca/hooks/pre-read.py", index[0]["globs"])

    def test_alpha_matched_path_returns_pointer(self):
        """AC-06 / alpha: spec_pointers yields a pointer naming 'alpha' for governed path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_spec(
                tmpdir, "alpha.md",
                header_lines=[
                    "**Status:** approved (2026-06-26)",
                    "**Governs:** plugins/ca/hooks/pre-read.py",
                ],
            )
            index = ril.approved_spec_index(tmpdir)
            pointers = ril.spec_pointers("plugins/ca/hooks/pre-read.py", index)
            self.assertEqual(len(pointers), 1)
            p = pointers[0]
            self.assertIn("alpha", p["text"])
            self.assertEqual(p["tier"], "specs")

    def test_alpha_unmatched_path_returns_empty(self):
        """AC-06 / alpha: unmatched path -> [] from spec_pointers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_spec(
                tmpdir, "alpha.md",
                header_lines=[
                    "**Status:** approved (2026-06-26)",
                    "**Governs:** plugins/ca/hooks/pre-read.py",
                ],
            )
            index = ril.approved_spec_index(tmpdir)
            pointers = ril.spec_pointers("src/other.py", index)
            self.assertEqual(pointers, [])

    # ------------------------------------------------------------------
    # beta fixture: approved but NO Governs -> not indexed
    # ------------------------------------------------------------------

    def test_beta_no_governs_line_not_indexed(self):
        """AC-06 / beta: spec with no **Governs:** line contributes nothing to the index,
        even when status is approved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_spec(
                tmpdir, "beta.md",
                header_lines=["**Status:** approved (2026-06-26)"],
            )
            index = ril.approved_spec_index(tmpdir)
            self.assertEqual(index, [], "beta (no Governs) must NOT be indexed")

    def test_beta_parse_spec_governs_returns_empty(self):
        """AC-06 / beta: parse_spec_governs on text with no Governs line -> []."""
        text = "**Status:** approved (2026-06-26)\n\n# Body\n"
        self.assertEqual(ril.parse_spec_governs(text), [])

    # ------------------------------------------------------------------
    # gamma fixture: Governs present but status NOT approved -> not indexed
    # ------------------------------------------------------------------

    def test_gamma_draft_status_not_indexed(self):
        """AC-06 / gamma: Governs present but status:'draft (pending approval)'
        must NOT appear in the index (approved-only gate)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_spec(
                tmpdir, "gamma.md",
                header_lines=[
                    "**Status:** draft (pending approval)",
                    "**Governs:** plugins/ca/hooks/pre-read.py",
                ],
            )
            index = ril.approved_spec_index(tmpdir)
            self.assertEqual(index, [], "gamma with draft status must NOT be in index")

    def test_gamma_matching_path_yields_no_pointer(self):
        """AC-06 / gamma: draft spec excluded from index, so spec_pointers -> []."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_spec(
                tmpdir, "gamma.md",
                header_lines=[
                    "**Status:** draft (pending approval)",
                    "**Governs:** plugins/ca/hooks/pre-read.py",
                ],
            )
            index = ril.approved_spec_index(tmpdir)
            pointers = ril.spec_pointers("plugins/ca/hooks/pre-read.py", index)
            self.assertEqual(
                pointers, [],
                "gamma's draft status must prevent any pointer for governed path",
            )

    # ------------------------------------------------------------------
    # Inline-status form: status sits after · separator on the same line
    # ------------------------------------------------------------------

    def test_inline_status_approved_enrolled(self):
        """AC-13 / inline-status: header '**Slug:** `d` · **Lane:** full ·
        **Status:** approved (2026-06-26)' on the SAME LINE must be parsed correctly
        and the spec enrolled (locks the · delimited status capture)."""
        SEP = "·"  # U+00B7 MIDDLE DOT — same char confirmed in the real spec file
        inline_header = (
            "**Slug:** `d` {sep} **Lane:** full {sep} **Status:** approved (2026-06-26)".format(
                sep=SEP
            )
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_spec(
                tmpdir, "delta.md",
                header_lines=[
                    inline_header,
                    "**Governs:** plugins/ca/hooks/pre-read.py",
                ],
            )
            index = ril.approved_spec_index(tmpdir)
            self.assertEqual(
                len(index), 1,
                "inline-status approved spec must be enrolled; got index={!r}".format(index),
            )
            self.assertEqual(index[0]["spec"], "delta")

    def test_inline_status_spec_pointers_match(self):
        """Inline-status enrolled spec yields a pointer via spec_pointers."""
        SEP = "·"
        inline_header = (
            "**Slug:** `d` {sep} **Lane:** full {sep} **Status:** approved (2026-06-26)".format(
                sep=SEP
            )
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_spec(
                tmpdir, "delta.md",
                header_lines=[
                    inline_header,
                    "**Governs:** plugins/ca/hooks/pre-read.py",
                ],
            )
            index = ril.approved_spec_index(tmpdir)
            pointers = ril.spec_pointers("plugins/ca/hooks/pre-read.py", index)
            self.assertEqual(len(pointers), 1)
            self.assertIn("delta", pointers[0]["text"])
            self.assertEqual(pointers[0]["tier"], "specs")

    # ------------------------------------------------------------------
    # Missing specs dir
    # ------------------------------------------------------------------

    def test_missing_specs_dir_returns_empty_no_raise(self):
        """Missing .codearbiter/specs/ dir -> [] without raising."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Deliberately NOT creating .codearbiter/specs/
            try:
                result = ril.approved_spec_index(tmpdir)
            except Exception as exc:
                self.fail(
                    "approved_spec_index raised on missing specs dir: {}".format(exc)
                )
            self.assertEqual(result, [])

    # ------------------------------------------------------------------
    # Token budget: pointer text must be <= 150 tokens
    # ------------------------------------------------------------------

    def test_pointer_text_within_token_budget(self):
        """AC-06: every pointer's token_estimate(text) must be <= 150."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_spec(
                tmpdir, "alpha.md",
                header_lines=[
                    "**Status:** approved (2026-06-26)",
                    "**Governs:** plugins/ca/hooks/pre-read.py",
                ],
            )
            index = ril.approved_spec_index(tmpdir)
            pointers = ril.spec_pointers("plugins/ca/hooks/pre-read.py", index)
            for p in pointers:
                est = ril.token_estimate(p["text"])
                self.assertLessEqual(
                    est,
                    150,
                    "pointer text token_estimate={} exceeds 150-token budget".format(est),
                )

    # ------------------------------------------------------------------
    # Pointer dict shape: must have 'text' (str) and 'tier' (str)
    # ------------------------------------------------------------------

    def test_pointer_has_text_and_tier_keys(self):
        """Each pointer must have 'text' (str) and 'tier' == 'specs'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_spec(
                tmpdir, "alpha.md",
                header_lines=[
                    "**Status:** approved (2026-06-26)",
                    "**Governs:** plugins/ca/hooks/pre-read.py",
                ],
            )
            index = ril.approved_spec_index(tmpdir)
            pointers = ril.spec_pointers("plugins/ca/hooks/pre-read.py", index)
            self.assertEqual(len(pointers), 1)
            p = pointers[0]
            self.assertIn("text", p)
            self.assertIsInstance(p["text"], str)
            self.assertGreater(len(p["text"]), 0)
            self.assertIn("tier", p)
            self.assertEqual(p["tier"], "specs")

    # ------------------------------------------------------------------
    # Wildcard glob matching
    # ------------------------------------------------------------------

    def test_wildcard_glob_matches_via_fnmatch(self):
        """Governs: plugins/ca/hooks/*.py matches plugins/ca/hooks/pre-read.py."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_spec(
                tmpdir, "wildcard.md",
                header_lines=[
                    "**Status:** approved (2026-06-26)",
                    "**Governs:** plugins/ca/hooks/*.py",
                ],
            )
            index = ril.approved_spec_index(tmpdir)
            pointers = ril.spec_pointers("plugins/ca/hooks/pre-read.py", index)
            self.assertEqual(len(pointers), 1)
            self.assertIn("wildcard", pointers[0]["text"])

    # ------------------------------------------------------------------
    # Edge cases: missing status, malformed file
    # ------------------------------------------------------------------

    def test_spec_without_status_line_not_indexed(self):
        """Spec with non-empty Governs but no **Status:** line is NOT indexed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_spec(
                tmpdir, "nostatus.md",
                header_lines=["**Governs:** plugins/ca/hooks/pre-read.py"],
            )
            index = ril.approved_spec_index(tmpdir)
            self.assertEqual(index, [], "spec without **Status:** must not be indexed")

    def test_malformed_file_skipped_no_raise(self):
        """Binary garbage file is skipped; other valid specs are still indexed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sdir = self._specs_dir(tmpdir)
            with open(os.path.join(sdir, "garbage.md"), "wb") as f:
                f.write(b"\xff\xfe\x80\x81garbage\xff\x00")
            self._write_spec(
                tmpdir, "good.md",
                header_lines=[
                    "**Status:** approved (2026-06-26)",
                    "**Governs:** src/api/handler.ts",
                ],
            )
            try:
                index = ril.approved_spec_index(tmpdir)
            except Exception as exc:
                self.fail(
                    "approved_spec_index raised on malformed file: {}".format(exc)
                )
            self.assertEqual(len(index), 1, "valid spec must be indexed despite garbage file")
            self.assertEqual(index[0]["spec"], "good")

    # ------------------------------------------------------------------
    # spec_pointers robustness
    # ------------------------------------------------------------------

    def test_spec_pointers_empty_index_returns_empty(self):
        """spec_pointers with empty index -> []."""
        self.assertEqual(ril.spec_pointers("some/path.py", []), [])

    def test_spec_pointers_none_index_returns_empty_no_raise(self):
        """spec_pointers with None index -> [] without raising."""
        try:
            result = ril.spec_pointers("some/path.py", None)
        except Exception as exc:
            self.fail("spec_pointers raised on None index: {}".format(exc))
        self.assertEqual(result, [])

    def test_spec_pointers_none_rel_returns_empty(self):
        """spec_pointers with None rel -> []."""
        index = [{"spec": "alpha", "globs": ["*"]}]
        self.assertEqual(ril.spec_pointers(None, index), [])

    def test_spec_pointers_empty_rel_returns_empty(self):
        """spec_pointers with empty rel -> []."""
        index = [{"spec": "alpha", "globs": ["*"]}]
        self.assertEqual(ril.spec_pointers("", index), [])

    def test_approved_spec_index_never_raises_on_garbage_root(self):
        """approved_spec_index never raises on None or garbage root."""
        for bad in [None, "", 42, "/no/such/path/xyz999"]:
            try:
                result = ril.approved_spec_index(bad)
            except Exception as exc:
                self.fail(
                    "approved_spec_index raised on root={!r}: {}".format(
                        repr(bad)[:40], exc
                    )
                )
            self.assertIsInstance(result, list)

    def test_parse_spec_governs_never_raises(self):
        """parse_spec_governs never raises on any input."""
        bad_inputs = [None, "", 42, [], {}, "x" * 10000, "\x00\x01\x02"]
        for inp in bad_inputs:
            try:
                ril.parse_spec_governs(inp)
            except Exception as exc:
                self.fail(
                    "parse_spec_governs raised on {!r}: {}".format(repr(inp)[:40], exc)
                )

    def test_spec_pointers_never_raises(self):
        """spec_pointers never raises on garbage inputs."""
        bad_combos = [
            (None, None),
            ("path.py", "not-a-list"),
            ("path.py", [None, 42, {}, {"spec": "x"}]),
        ]
        for rel, index in bad_combos:
            try:
                ril.spec_pointers(rel, index)
            except Exception as exc:
                self.fail(
                    "spec_pointers raised on rel={!r} index={!r}: {}".format(
                        rel, repr(index)[:40], exc
                    )
                )


class ProvenancePointerTest(unittest.TestCase):
    """T-06 / AC-07: provenance_pointer(rel, provenance, current_hashes) — tier 4.

    PURE comparator — no git calls.  Emits one pointer per FRESH entry (stored
    hash non-null AND rel in current_hashes AND hashes match).  SUPPRESSES
    diverged / unverifiable / null-hash entries.

    Fixtures use synthetic provenance dicts and current_hashes dicts — no real
    git subprocess is invoked anywhere in this test class.
    """

    # ------------------------------------------------------------------
    # Shared fixture helpers
    # ------------------------------------------------------------------

    def _fresh_provenance(self):
        """Minimal provenance map used by the happy-path (FRESH) tests."""
        return {
            "tech-stack": {
                "doc": "tech-stack",
                "entries": [
                    {
                        "path": "package.json",
                        "hash": "abc123",
                        "drift_trigger": True,
                        "claims": [
                            {
                                "lines": "12-40",
                                "claim": "Node 20 runtime declared",
                                "confidence": "strong",
                            }
                        ],
                    }
                ],
            }
        }

    # ------------------------------------------------------------------
    # T-06-01: FRESH — hash match → pointer emitted
    # ------------------------------------------------------------------

    def test_fresh_returns_one_pointer(self):
        """FRESH: stored hash == current_hashes[path] → one pointer returned."""
        result = ril.provenance_pointer(
            "package.json",
            self._fresh_provenance(),
            {"package.json": "abc123"},
        )
        self.assertEqual(len(result), 1, "expected exactly one pointer for FRESH entry")

    def test_fresh_pointer_tier_is_standards(self):
        """FRESH: returned pointer must have tier == 'standards'."""
        result = ril.provenance_pointer(
            "package.json",
            self._fresh_provenance(),
            {"package.json": "abc123"},
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["tier"], "standards")

    def test_fresh_pointer_text_mentions_doc_name(self):
        """FRESH: pointer text must mention the doc name ('tech-stack')."""
        result = ril.provenance_pointer(
            "package.json",
            self._fresh_provenance(),
            {"package.json": "abc123"},
        )
        self.assertEqual(len(result), 1)
        self.assertIn("tech-stack", result[0]["text"])

    def test_fresh_pointer_text_mentions_claim(self):
        """FRESH: pointer text must include the first claim's text."""
        result = ril.provenance_pointer(
            "package.json",
            self._fresh_provenance(),
            {"package.json": "abc123"},
        )
        self.assertEqual(len(result), 1)
        self.assertIn("Node 20 runtime declared", result[0]["text"])

    def test_fresh_pointer_text_includes_lines_range(self):
        """FRESH: pointer text must include the lines range when the claim has one
        (e.g. 'lines 12-40')."""
        result = ril.provenance_pointer(
            "package.json",
            self._fresh_provenance(),
            {"package.json": "abc123"},
        )
        self.assertEqual(len(result), 1)
        self.assertIn("12-40", result[0]["text"])

    def test_fresh_pointer_text_within_token_budget(self):
        """FRESH: token_estimate(pointer['text']) must be <= 150."""
        result = ril.provenance_pointer(
            "package.json",
            self._fresh_provenance(),
            {"package.json": "abc123"},
        )
        self.assertEqual(len(result), 1)
        est = ril.token_estimate(result[0]["text"])
        self.assertLessEqual(
            est,
            150,
            "pointer text token_estimate={} exceeds 150-token budget".format(est),
        )

    def test_fresh_pointer_text_without_lines_range(self):
        """FRESH: when the claim has no 'lines' key, text still includes doc + claim."""
        provenance = {
            "coding-standards": {
                "doc": "coding-standards",
                "entries": [
                    {
                        "path": "src/app.py",
                        "hash": "def456",
                        "drift_trigger": True,
                        "claims": [
                            {
                                "claim": "snake_case enforced for all identifiers",
                                "confidence": "strong",
                            }
                        ],
                    }
                ],
            }
        }
        result = ril.provenance_pointer(
            "src/app.py",
            provenance,
            {"src/app.py": "def456"},
        )
        self.assertEqual(len(result), 1)
        self.assertIn("coding-standards", result[0]["text"])
        self.assertIn("snake_case enforced for all identifiers", result[0]["text"])

    # ------------------------------------------------------------------
    # T-06-02: DIVERGED — hash mismatch → [] (the core suppression case)
    # ------------------------------------------------------------------

    def test_diverged_returns_empty(self):
        """DIVERGED (core suppression): stored hash != current_hashes[path] → []."""
        result = ril.provenance_pointer(
            "package.json",
            self._fresh_provenance(),
            {"package.json": "DIFFERENT"},
        )
        self.assertEqual(
            result,
            [],
            "DIVERGED hash must be suppressed — got {!r}".format(result),
        )

    def test_diverged_suppression_is_total(self):
        """DIVERGED: even when other metadata is intact, a mismatched hash returns []."""
        provenance = {
            "tech-stack": {
                "doc": "tech-stack",
                "entries": [
                    {
                        "path": "package.json",
                        "hash": "original_abc",
                        "drift_trigger": True,
                        "claims": [{"lines": "1-5", "claim": "Some claim", "confidence": "strong"}],
                    }
                ],
            }
        }
        # Provide a current_hash that is close but not equal
        result = ril.provenance_pointer(
            "package.json",
            provenance,
            {"package.json": "original_abc_CHANGED"},
        )
        self.assertEqual(result, [], "any hash mismatch must suppress the pointer")

    # ------------------------------------------------------------------
    # T-06-03: UNVERIFIABLE — path absent from current_hashes → []
    # ------------------------------------------------------------------

    def test_unverifiable_empty_current_hashes_returns_empty(self):
        """UNVERIFIABLE: current_hashes == {} (path not hashed) → []."""
        result = ril.provenance_pointer(
            "package.json",
            self._fresh_provenance(),
            {},
        )
        self.assertEqual(
            result,
            [],
            "path absent from current_hashes must be suppressed — got {!r}".format(result),
        )

    def test_unverifiable_path_not_in_current_hashes(self):
        """UNVERIFIABLE: current_hashes has other paths but not the target → []."""
        result = ril.provenance_pointer(
            "package.json",
            self._fresh_provenance(),
            {"other-file.ts": "some-oid"},
        )
        self.assertEqual(result, [])

    # ------------------------------------------------------------------
    # T-06-04: NULL stored hash → []
    # ------------------------------------------------------------------

    def test_null_stored_hash_returns_empty(self):
        """Stored hash is None → suppressed (unverifiable)."""
        provenance = {
            "tech-stack": {
                "doc": "tech-stack",
                "entries": [
                    {
                        "path": "package.json",
                        "hash": None,
                        "drift_trigger": True,
                        "claims": [{"lines": "1-5", "claim": "Some claim", "confidence": "strong"}],
                    }
                ],
            }
        }
        result = ril.provenance_pointer(
            "package.json",
            provenance,
            {"package.json": "abc123"},
        )
        self.assertEqual(
            result,
            [],
            "null stored hash must be suppressed — got {!r}".format(result),
        )

    # ------------------------------------------------------------------
    # T-06-05: No path match → []
    # ------------------------------------------------------------------

    def test_no_path_match_returns_empty(self):
        """No entry's path matches rel → []."""
        result = ril.provenance_pointer(
            "other.py",
            self._fresh_provenance(),
            {"other.py": "abc123"},
        )
        self.assertEqual(result, [], "non-matching rel must return []")

    def test_no_path_match_different_extension(self):
        """Exact path match only — 'package.lock' is not 'package.json'."""
        result = ril.provenance_pointer(
            "package.lock",
            self._fresh_provenance(),
            {"package.json": "abc123", "package.lock": "abc123"},
        )
        self.assertEqual(result, [])

    # ------------------------------------------------------------------
    # T-06-06: Empty provenance {} → []
    # ------------------------------------------------------------------

    def test_empty_provenance_returns_empty(self):
        """Empty provenance {} (live state before re-scout backfill) → []."""
        result = ril.provenance_pointer(
            "package.json",
            {},
            {"package.json": "abc123"},
        )
        self.assertEqual(result, [], "empty provenance must return []")

    # ------------------------------------------------------------------
    # T-06-07: Malformed inputs → [], no raise
    # ------------------------------------------------------------------

    def test_non_dict_provenance_returns_empty_no_raise(self):
        """Non-dict provenance → [] without raising."""
        for bad in [None, "string", 42, []]:
            try:
                result = ril.provenance_pointer("package.json", bad, {"package.json": "x"})
            except Exception as exc:
                self.fail(
                    "provenance_pointer raised on provenance={!r}: {}".format(
                        repr(bad)[:40], exc
                    )
                )
            self.assertEqual(
                result,
                [],
                "Expected [] for provenance={!r}, got {!r}".format(bad, result),
            )

    def test_non_dict_current_hashes_returns_empty_no_raise(self):
        """Non-dict current_hashes → [] without raising."""
        for bad in [None, "string", 42, []]:
            try:
                result = ril.provenance_pointer("package.json", self._fresh_provenance(), bad)
            except Exception as exc:
                self.fail(
                    "provenance_pointer raised on current_hashes={!r}: {}".format(
                        repr(bad)[:40], exc
                    )
                )
            self.assertEqual(result, [])

    def test_none_record_value_skipped_no_raise(self):
        """A None record value in the provenance map is skipped without raising."""
        provenance = {"tech-stack": None}
        try:
            result = ril.provenance_pointer("package.json", provenance, {"package.json": "x"})
        except Exception as exc:
            self.fail("provenance_pointer raised on None record: {}".format(exc))
        self.assertEqual(result, [])

    def test_non_dict_entry_in_entries_skipped_no_raise(self):
        """A non-dict entry inside entries[] is skipped without raising."""
        provenance = {
            "tech-stack": {
                "doc": "tech-stack",
                "entries": [
                    None,
                    "string-entry",
                    42,
                    {
                        "path": "package.json",
                        "hash": "abc123",
                        "drift_trigger": True,
                        "claims": [{"lines": "1-5", "claim": "valid claim", "confidence": "strong"}],
                    },
                ],
            }
        }
        try:
            result = ril.provenance_pointer("package.json", provenance, {"package.json": "abc123"})
        except Exception as exc:
            self.fail("provenance_pointer raised on non-dict entries: {}".format(exc))
        # The valid entry should still produce a pointer
        self.assertEqual(len(result), 1)
        self.assertIn("valid claim", result[0]["text"])

    def test_malformed_record_no_entries_key_skipped(self):
        """A record without 'entries' key is skipped gracefully."""
        provenance = {"tech-stack": {"doc": "tech-stack"}}
        try:
            result = ril.provenance_pointer("package.json", provenance, {"package.json": "x"})
        except Exception as exc:
            self.fail("provenance_pointer raised on record with no entries key: {}".format(exc))
        self.assertEqual(result, [])

    def test_entry_with_no_claims_skipped_no_raise(self):
        """An entry that would otherwise be FRESH but has no claims is skipped."""
        provenance = {
            "tech-stack": {
                "doc": "tech-stack",
                "entries": [
                    {
                        "path": "package.json",
                        "hash": "abc123",
                        "drift_trigger": True,
                        "claims": [],  # empty
                    }
                ],
            }
        }
        try:
            result = ril.provenance_pointer("package.json", provenance, {"package.json": "abc123"})
        except Exception as exc:
            self.fail("provenance_pointer raised on empty claims list: {}".format(exc))
        self.assertEqual(result, [])

    def test_empty_rel_returns_empty_no_raise(self):
        """Empty rel → [] without raising."""
        try:
            result = ril.provenance_pointer("", self._fresh_provenance(), {"package.json": "abc123"})
        except Exception as exc:
            self.fail("provenance_pointer raised on empty rel: {}".format(exc))
        self.assertEqual(result, [])

    def test_none_rel_returns_empty_no_raise(self):
        """None rel → [] without raising."""
        try:
            result = ril.provenance_pointer(None, self._fresh_provenance(), {"package.json": "abc123"})
        except Exception as exc:
            self.fail("provenance_pointer raised on None rel: {}".format(exc))
        self.assertEqual(result, [])

    # ------------------------------------------------------------------
    # T-06-08: Token budget — all returned pointers satisfy the 150-token cap
    # ------------------------------------------------------------------

    def test_all_pointers_satisfy_token_budget(self):
        """Every returned pointer must satisfy token_estimate(text) <= 150."""
        # Build a provenance with a very long claim to trigger truncation path.
        long_claim = "x" * 700  # well over 150 tokens when combined with prefix
        provenance = {
            "tech-stack": {
                "doc": "tech-stack",
                "entries": [
                    {
                        "path": "package.json",
                        "hash": "abc123",
                        "drift_trigger": True,
                        "claims": [
                            {"lines": "1-999", "claim": long_claim, "confidence": "strong"}
                        ],
                    }
                ],
            }
        }
        result = ril.provenance_pointer("package.json", provenance, {"package.json": "abc123"})
        self.assertEqual(len(result), 1, "should still emit a (truncated) pointer")
        for p in result:
            est = ril.token_estimate(p["text"])
            self.assertLessEqual(
                est,
                150,
                "pointer text token_estimate={} exceeds 150-token budget".format(est),
            )

    # ------------------------------------------------------------------
    # T-06-09: Multiple docs — only the FRESH one produces a pointer
    # ------------------------------------------------------------------

    def test_multiple_docs_only_fresh_emits_pointer(self):
        """When multiple docs have an entry for the same path, only FRESH ones emit."""
        provenance = {
            "tech-stack": {
                "doc": "tech-stack",
                "entries": [
                    {
                        "path": "package.json",
                        "hash": "abc123",  # FRESH
                        "drift_trigger": True,
                        "claims": [{"claim": "Tech stack claim", "confidence": "strong"}],
                    }
                ],
            },
            "coding-standards": {
                "doc": "coding-standards",
                "entries": [
                    {
                        "path": "package.json",
                        "hash": "STALE",  # DIVERGED
                        "drift_trigger": True,
                        "claims": [{"claim": "Standards claim", "confidence": "strong"}],
                    }
                ],
            },
        }
        result = ril.provenance_pointer(
            "package.json",
            provenance,
            {"package.json": "abc123"},
        )
        # Only the fresh tech-stack entry should produce a pointer
        self.assertEqual(len(result), 1)
        self.assertIn("tech-stack", result[0]["text"])
        # coding-standards entry is DIVERGED — must be suppressed
        texts = [p["text"] for p in result]
        self.assertFalse(
            any("coding-standards" in t for t in texts),
            "DIVERGED coding-standards entry must be suppressed",
        )

    def test_never_raises_on_arbitrary_garbage(self):
        """provenance_pointer never raises on arbitrary garbage inputs."""
        garbage_combos = [
            ("path.py", None, None),
            (None, None, None),
            (42, {}, {}),
            ("path.py", {"doc": object()}, {}),
            ("path.py", {"doc": {"entries": [object()]}}, {}),
        ]
        for rel, prov, hashes in garbage_combos:
            try:
                ril.provenance_pointer(rel, prov, hashes)
            except Exception as exc:
                self.fail(
                    "provenance_pointer raised on rel={!r}: {}".format(repr(rel)[:20], exc)
                )


class DeduplicationTest(unittest.TestCase):
    """T-08 / AC-09: marker_path, already_injected, record_injection.

    At most ONE injection per (session, file) pair.  Markers live under
    <root>/.codearbiter/.markers/ with filenames derived from
    sha256(session_id + NUL + rel) so they are filesystem-safe regardless of
    session_id or rel content.
    """

    # ------------------------------------------------------------------
    # Fresh state: no marker → already_injected returns False
    # ------------------------------------------------------------------

    def test_fresh_state_not_injected(self):
        """Fresh state: already_injected(tmp, 'sess1', 'a/b.py') → False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = ril.already_injected(tmpdir, "sess1", "a/b.py")
            self.assertFalse(
                result,
                "fresh state must return False before any record_injection call",
            )

    # ------------------------------------------------------------------
    # After record_injection: already_injected returns True
    # ------------------------------------------------------------------

    def test_record_then_already_injected_true(self):
        """After record_injection(tmp, 'sess1', 'a/b.py'): already_injected → True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertFalse(ril.already_injected(tmpdir, "sess1", "a/b.py"))
            ril.record_injection(tmpdir, "sess1", "a/b.py")
            self.assertTrue(
                ril.already_injected(tmpdir, "sess1", "a/b.py"),
                "after record_injection the marker must exist and already_injected must return True",
            )

    # ------------------------------------------------------------------
    # AC-09 core: different file, same session → still injects
    # ------------------------------------------------------------------

    def test_different_file_same_session_not_injected(self):
        """AC-09 core: record_injection for 'a/b.py' does NOT suppress 'a/OTHER.py'
        in the same session — a different file in the same session still injects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ril.record_injection(tmpdir, "sess1", "a/b.py")
            result = ril.already_injected(tmpdir, "sess1", "a/OTHER.py")
            self.assertFalse(
                result,
                "a different file in the same session must NOT be suppressed (AC-09): "
                "each (session, file) pair is independent",
            )

    # ------------------------------------------------------------------
    # Per-session: different session, same file → still injects
    # ------------------------------------------------------------------

    def test_different_session_same_file_not_injected(self):
        """Per-session dedup: record_injection for sess1 does NOT suppress sess2
        for the same file — markers are scoped to (session, file) pairs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ril.record_injection(tmpdir, "sess1", "a/b.py")
            result = ril.already_injected(tmpdir, "sess2", "a/b.py")
            self.assertFalse(
                result,
                "a different session for the same file must NOT be suppressed",
            )

    # ------------------------------------------------------------------
    # marker_path determinism and collision-freeness
    # ------------------------------------------------------------------

    def test_marker_path_is_deterministic(self):
        """marker_path returns the same string on two calls with identical args."""
        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = ril.marker_path(tmpdir, "sess1", "a/b.py")
            p2 = ril.marker_path(tmpdir, "sess1", "a/b.py")
            self.assertEqual(p1, p2, "marker_path must be deterministic")

    def test_marker_path_different_rel_different_path(self):
        """Different rel values produce different marker paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = ril.marker_path(tmpdir, "sess1", "a/b.py")
            p2 = ril.marker_path(tmpdir, "sess1", "a/OTHER.py")
            self.assertNotEqual(
                p1, p2,
                "different rel values must produce different marker paths",
            )

    def test_marker_path_different_session_different_path(self):
        """Different session_ids produce different marker paths for the same rel."""
        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = ril.marker_path(tmpdir, "sess1", "a/b.py")
            p2 = ril.marker_path(tmpdir, "sess2", "a/b.py")
            self.assertNotEqual(
                p1, p2,
                "different sessions must produce different marker paths",
            )

    def test_marker_path_is_under_markers_dir(self):
        """marker_path returns a path inside <root>/.codearbiter/.markers/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            p = ril.marker_path(tmpdir, "sess1", "a/b.py")
            markers_dir = os.path.join(tmpdir, ".codearbiter", ".markers")
            self.assertTrue(
                p.startswith(markers_dir),
                "marker_path must be under .codearbiter/.markers/",
            )

    # ------------------------------------------------------------------
    # record_injection creates .markers/ dir when it does not exist
    # ------------------------------------------------------------------

    def test_record_injection_creates_markers_dir(self):
        """record_injection creates .codearbiter/.markers/ when it does not exist yet,
        and does not raise."""
        with tempfile.TemporaryDirectory() as tmpdir:
            markers_dir = os.path.join(tmpdir, ".codearbiter", ".markers")
            self.assertFalse(
                os.path.isdir(markers_dir),
                "dir must not exist before record_injection",
            )
            try:
                ril.record_injection(tmpdir, "sess1", "a/b.py")
            except Exception as exc:
                self.fail(
                    "record_injection raised when .markers/ was absent: {}".format(exc)
                )
            self.assertTrue(
                os.path.isdir(markers_dir),
                "record_injection must create .codearbiter/.markers/ dir",
            )

    # ------------------------------------------------------------------
    # Robustness: None/garbage args must not raise
    # ------------------------------------------------------------------

    def test_already_injected_garbage_args_does_not_raise(self):
        """already_injected with garbage session_id/rel values returns False without raising.

        Root is always a fresh hermetic tempdir or a genuinely non-existent path
        (which cannot be written to) — never None, an int, or a CWD-relative
        root — so the 'returns False' assertion is deterministic across runs and
        no filesystem state escapes the tempdir.  Exercises garbage session_id
        and rel values (None, empty string, int, list) per AC-09 robustness.
        """
        # Garbage (session_id, rel) pairs — each uses an independent clean tempdir
        # so no prior-run marker can influence the result.
        garbage_pairs = [
            (None, None),
            ("", ""),
            (42, []),
        ]
        for session_id, rel in garbage_pairs:
            with tempfile.TemporaryDirectory() as tmpdir:
                try:
                    result = ril.already_injected(tmpdir, session_id, rel)
                except Exception as exc:
                    self.fail(
                        "already_injected raised on (session_id={!r}, rel={!r}): {}".format(
                            repr(session_id)[:20], repr(rel)[:20], exc
                        )
                    )
                self.assertFalse(
                    result,
                    "already_injected must return False on a clean tempdir "
                    "(session_id={!r}, rel={!r}), got {!r}".format(
                        session_id, rel, result
                    ),
                )

        # Non-existent root: degrades gracefully to False.  No filesystem
        # writes can occur here (makedirs would fail), so this case cannot
        # pollute the working tree and is safe to leave outside a tempdir.
        try:
            result = ril.already_injected("/no/such/path/xyz999abc", "sess", "a/b.py")
        except Exception as exc:
            self.fail(
                "already_injected raised on non-existent root: {}".format(exc)
            )
        self.assertFalse(
            result,
            "non-existent root must return False, got {!r}".format(result),
        )

    def test_record_injection_garbage_args_does_not_raise(self):
        """record_injection with garbage session_id/rel values swallows all errors silently.

        Root is always a fresh tempdir so no filesystem state escapes to the
        working tree.  Exercises garbage session_id and rel values (None, empty
        string, int, list) per AC-09 robustness requirement.
        """
        garbage_pairs = [
            (None, None),
            ("", ""),
            (42, []),
        ]
        for session_id, rel in garbage_pairs:
            with tempfile.TemporaryDirectory() as tmpdir:
                try:
                    ril.record_injection(tmpdir, session_id, rel)
                except Exception as exc:
                    self.fail(
                        "record_injection raised on (session_id={!r}, rel={!r}): {}".format(
                            repr(session_id)[:20], repr(rel)[:20], exc
                        )
                    )


class GoverningDocsTest(unittest.TestCase):
    """T-07 / AC-04/05/06/08/11: governing_docs(rel, index, runner=None) — four-tier composer.

    Composes security-controls > decisions > specs > standards in priority order.
    The LAZY hashing gate (AC-11) ensures batch_hash is called ONLY when rel appears
    as a provenance entry path — a non-provenance Read must make ZERO git calls.

    All index values are synthetic; no real filesystem or git subprocess is used.
    """

    # ------------------------------------------------------------------
    # Counting runner factory
    # ------------------------------------------------------------------

    @staticmethod
    def _make_runner(canned_oid):
        """Return (runner, counter_list).

        runner(args, stdin_text) -> str: increments counter_list[0] on each call;
        returns one canned_oid line per non-empty line in stdin_text, mimicking
        the git hash-object --stdin-paths stdout format.
        """
        counter = [0]

        def _runner(args, stdin_text):
            counter[0] += 1
            lines = [ln for ln in stdin_text.splitlines() if ln]
            if not lines:
                return ""
            return "\n".join(canned_oid for _ in lines) + "\n"

        return _runner, counter

    # ------------------------------------------------------------------
    # Synthetic index builder
    # ------------------------------------------------------------------

    @staticmethod
    def _make_index(adr_globs=None, spec_globs=None, prov_path=None, prov_hash=None):
        """Build a minimal synthetic index for governing_docs.

        adr_globs  — list of fnmatch globs for a single accepted ADR entry, or None.
        spec_globs — list of fnmatch globs for a single approved spec entry, or None.
        prov_path  — path string for a provenance entry, or None.
        prov_hash  — stored hash for that entry, or None (treats entry as null-hash).
        """
        adr = (
            [{"adr": "0001", "title": "Test ADR", "globs": adr_globs}]
            if adr_globs
            else []
        )
        spec = (
            [{"spec": "test-spec", "globs": spec_globs}]
            if spec_globs
            else []
        )
        provenance = {}
        if prov_path is not None:
            provenance = {
                "tech-stack": {
                    "doc": "tech-stack",
                    "entries": [
                        {
                            "path": prov_path,
                            "hash": prov_hash,
                            "drift_trigger": True,
                            "claims": [
                                {
                                    "claim": "Tech stack claim for {}".format(prov_path),
                                    "confidence": "strong",
                                }
                            ],
                        }
                    ],
                }
            }
        return {"adr": adr, "spec": spec, "provenance": provenance}

    # ------------------------------------------------------------------
    # T-07-01: Priority order — all four tiers fire in order
    # ------------------------------------------------------------------

    def test_priority_order_all_four_tiers(self):
        """Priority order: rel matching security-controls AND accepted ADR AND approved spec
        AND FRESH provenance entry → tier sequence ['security-controls', 'decisions',
        'specs', 'standards'] (in that exact order).

        rel = 'src/middleware/auth.ts':
          - tier 1: security-controls — 'middleware' and 'auth' are security-entry tokens
          - tier 2: decisions — ADR governs 'src/middleware/*.ts'
          - tier 3: specs   — spec governs 'src/middleware/*.ts'
          - tier 4: standards — provenance entry for the same path, FRESH hash
        """
        rel = "src/middleware/auth.ts"
        stored_hash = "aabbcc112233"
        index = self._make_index(
            adr_globs=["src/middleware/*.ts"],
            spec_globs=["src/middleware/*.ts"],
            prov_path=rel,
            prov_hash=stored_hash,
        )
        runner, _counter = self._make_runner(stored_hash)  # FRESH: oid matches stored
        pointers = ril.governing_docs(rel, index, runner)
        tiers = [p["tier"] for p in pointers]

        # All four tiers must be present.
        for expected_tier in ("security-controls", "decisions", "specs", "standards"):
            self.assertIn(
                expected_tier,
                tiers,
                "tier '{}' missing from result; tiers = {!r}".format(expected_tier, tiers),
            )

        # Priority order must be preserved: sec < dec < spec < std.
        sec_idx = tiers.index("security-controls")
        dec_idx = tiers.index("decisions")
        spec_idx = tiers.index("specs")
        std_idx = tiers.index("standards")
        self.assertLess(sec_idx, dec_idx, "security-controls must come before decisions")
        self.assertLess(dec_idx, spec_idx, "decisions must come before specs")
        self.assertLess(spec_idx, std_idx, "specs must come before standards")

    # ------------------------------------------------------------------
    # T-07-02a: AC-11 cost guarantee — rel matches nothing, zero git calls
    # ------------------------------------------------------------------

    def test_cost_guarantee_rel_matches_nothing_zero_calls(self):
        """AC-11 cost guarantee: rel that matches NO tier (not a security-entry, no ADR/spec
        glob match, absent from provenance) → [] result AND runner called exactly 0 times."""
        rel = "src/utils/helper.py"  # non-security-entry; no glob match; not in provenance
        # Provenance has an entry for a DIFFERENT path to prove the lazy gate works
        index = self._make_index(prov_path="package.json", prov_hash="deadbeef")
        runner, counter = self._make_runner("deadbeef")

        result = ril.governing_docs(rel, index, runner)

        self.assertEqual(result, [], "non-matching rel must produce []")
        self.assertEqual(
            counter[0],
            0,
            "AC-11: runner must NOT be called when rel is absent from provenance; "
            "call count = {}".format(counter[0]),
        )

    # ------------------------------------------------------------------
    # T-07-02b: AC-11 cost guarantee — matches tiers 1-3 but absent from provenance
    # ------------------------------------------------------------------

    def test_cost_guarantee_matches_tiers_1_to_3_absent_from_provenance(self):
        """AC-11 cost guarantee: rel that fires tiers 1-3 (security-controls, decisions,
        specs) but is NOT in any provenance entry → runner called exactly 0 times.

        Provenance only tracks 'package.json'; 'src/middleware/auth.ts' is absent.
        Tiers 1-3 are pure and must never call batch_hash; tier 4 is guarded by the
        provenance-entry-path set check.
        """
        rel = "src/middleware/auth.ts"  # hits tiers 1, 2, 3
        index = self._make_index(
            adr_globs=["src/middleware/*.ts"],
            spec_globs=["src/middleware/*.ts"],
            prov_path="package.json",   # different path — rel is absent
            prov_hash="deadbeef",
        )
        runner, counter = self._make_runner("deadbeef")

        pointers = ril.governing_docs(rel, index, runner)
        tiers = [p["tier"] for p in pointers]

        # Tiers 1-3 must be present.
        self.assertIn("security-controls", tiers)
        self.assertIn("decisions", tiers)
        self.assertIn("specs", tiers)
        # Tier 4 must be absent (rel not in provenance).
        self.assertNotIn(
            "standards",
            tiers,
            "rel absent from provenance must not yield a 'standards' pointer",
        )
        # KEY ASSERTION: zero git calls.
        self.assertEqual(
            counter[0],
            0,
            "AC-11: runner must NOT be called for rel absent from provenance; "
            "call count = {}".format(counter[0]),
        )

    # ------------------------------------------------------------------
    # T-07-03a: Lazy hash fires exactly once — FRESH → standards pointer
    # ------------------------------------------------------------------

    def test_lazy_hash_fires_once_fresh_yields_standards_pointer(self):
        """Lazy tier-4 gate: rel present as a provenance entry → runner called ONCE;
        FRESH stored hash (runner oid matches) → 'standards' pointer in result."""
        rel = "package.json"
        stored_hash = "cafebabe"
        index = self._make_index(prov_path=rel, prov_hash=stored_hash)
        runner, counter = self._make_runner(stored_hash)  # FRESH: same oid

        pointers = ril.governing_docs(rel, index, runner)

        # Runner must be called exactly once.
        self.assertEqual(
            counter[0],
            1,
            "runner must be called exactly ONCE for a provenance-matched rel; "
            "call count = {}".format(counter[0]),
        )
        tiers = [p["tier"] for p in pointers]
        self.assertIn(
            "standards",
            tiers,
            "FRESH provenance entry must produce a 'standards' pointer",
        )

    # ------------------------------------------------------------------
    # T-07-03b: Lazy hash fires exactly once — DIVERGED → no standards pointer
    # ------------------------------------------------------------------

    def test_lazy_hash_fires_once_diverged_suppresses_standards_pointer(self):
        """Lazy tier-4 gate: rel present as a provenance entry → runner called ONCE;
        DIVERGED hash (runner oid differs from stored) → NO 'standards' pointer,
        but the runner WAS still called (gate fired, result suppressed by freshness check)."""
        rel = "package.json"
        stored_hash = "cafebabe"
        diverged_oid = "00000000"  # different from stored_hash → DIVERGED
        index = self._make_index(prov_path=rel, prov_hash=stored_hash)
        runner, counter = self._make_runner(diverged_oid)  # DIVERGED

        pointers = ril.governing_docs(rel, index, runner)

        # Runner must still have been called exactly once (the gate fires regardless).
        self.assertEqual(
            counter[0],
            1,
            "runner must be called exactly ONCE even when hash diverges; "
            "call count = {}".format(counter[0]),
        )
        tiers = [p["tier"] for p in pointers]
        self.assertNotIn(
            "standards",
            tiers,
            "DIVERGED hash must suppress the 'standards' pointer",
        )

    # ------------------------------------------------------------------
    # T-07-04: Empty index → [], zero runner calls
    # ------------------------------------------------------------------

    def test_empty_index_returns_empty_zero_calls(self):
        """Empty index {'adr': [], 'spec': [], 'provenance': {}} → [] and zero runner calls
        for any rel (no provenance entry paths exist, so tier-4 gate never opens)."""
        empty_index = {"adr": [], "spec": [], "provenance": {}}
        runner, counter = self._make_runner("any_oid")

        result = ril.governing_docs("package.json", empty_index, runner)

        self.assertEqual(result, [], "empty index must produce []")
        self.assertEqual(
            counter[0],
            0,
            "empty index must not trigger any runner calls; "
            "call count = {}".format(counter[0]),
        )

    # ------------------------------------------------------------------
    # T-07-05: Malformed index → [], never raises
    # ------------------------------------------------------------------

    def test_malformed_index_missing_all_keys(self):
        """Malformed index: {} (no 'adr'/'spec'/'provenance' keys) → [] without raising.

        Uses a non-security-entry rel so that tier 1 does not fire independently
        of the index.  The test isolates index-malformation handling, not tier-1 logic.
        """
        runner, counter = self._make_runner("any_oid")
        try:
            result = ril.governing_docs("src/utils/helper.py", {}, runner)
        except Exception as exc:
            self.fail("governing_docs raised on missing-keys index: {}".format(exc))
        self.assertEqual(result, [])
        self.assertEqual(counter[0], 0, "missing-keys index must make zero runner calls")

    def test_malformed_index_none_values(self):
        """Malformed index: None for all sub-keys → [] without raising; zero runner calls."""
        bad_index = {"adr": None, "spec": None, "provenance": None}
        runner, counter = self._make_runner("any_oid")
        try:
            result = ril.governing_docs("src/middleware/auth.ts", bad_index, runner)
        except Exception as exc:
            self.fail("governing_docs raised on None-value index: {}".format(exc))
        self.assertIsInstance(result, list)
        self.assertEqual(counter[0], 0, "None-value index must make zero runner calls")

    def test_malformed_index_none_itself(self):
        """None index → [] without raising."""
        runner, _counter = self._make_runner("any_oid")
        try:
            result = ril.governing_docs("package.json", None, runner)
        except Exception as exc:
            self.fail("governing_docs raised on None index: {}".format(exc))
        self.assertEqual(result, [])

    def test_governing_docs_never_raises_on_garbage(self):
        """governing_docs never raises on any combination of garbage inputs."""
        runner, _ = self._make_runner("oid")
        combos = [
            (None, None, None),
            ("path.py", "not-a-dict", None),
            (42, {}, runner),
            ("path.py", {"adr": "not-a-list", "spec": 99, "provenance": "bad"}, runner),
        ]
        for rel, idx, r in combos:
            try:
                ril.governing_docs(rel, idx, r)
            except Exception as exc:
                self.fail(
                    "governing_docs raised on rel={!r} index={!r}: {}".format(
                        repr(rel)[:20], repr(idx)[:20], exc
                    )
                )

    # ------------------------------------------------------------------
    # T-07-06: Return type is always a list
    # ------------------------------------------------------------------

    def test_return_type_is_always_list(self):
        """governing_docs always returns a list (including no-match and empty-index cases)."""
        cases = [
            ("src/utils/helper.py", {"adr": [], "spec": [], "provenance": {}}),
            ("src/middleware/auth.ts", {"adr": [], "spec": [], "provenance": {}}),
        ]
        for rel, index in cases:
            result = ril.governing_docs(rel, index)
            self.assertIsInstance(
                result,
                list,
                "governing_docs must return list; got {!r} for rel={!r}".format(
                    type(result).__name__, rel
                ),
            )

    # ------------------------------------------------------------------
    # T-07-07: Pointer dicts have 'text' (str) and 'tier' (str)
    # ------------------------------------------------------------------

    def test_all_returned_pointers_have_text_and_tier(self):
        """Every pointer in the returned list must have 'text' (str) and 'tier' (str)."""
        rel = "src/middleware/auth.ts"
        stored_hash = "freshoid"
        index = self._make_index(
            adr_globs=["src/middleware/*.ts"],
            spec_globs=["src/middleware/*.ts"],
            prov_path=rel,
            prov_hash=stored_hash,
        )
        runner, _ = self._make_runner(stored_hash)
        pointers = ril.governing_docs(rel, index, runner)
        self.assertGreater(len(pointers), 0, "expected at least one pointer")
        for p in pointers:
            self.assertIsInstance(p, dict, "each pointer must be a dict")
            self.assertIn("text", p, "pointer must have 'text' key")
            self.assertIsInstance(p["text"], str, "pointer['text'] must be a str")
            self.assertGreater(len(p["text"]), 0, "pointer['text'] must be non-empty")
            self.assertIn("tier", p, "pointer must have 'tier' key")
            self.assertIsInstance(p["tier"], str, "pointer['tier'] must be a str")

    # ------------------------------------------------------------------
    # T-07-08: No runner argument → defaults gracefully (no crash)
    # ------------------------------------------------------------------

    def test_no_runner_argument_with_empty_provenance(self):
        """governing_docs(rel, index) with no runner arg + empty provenance → []
        without raising (batch_hash is never called when provenance is empty)."""
        empty_index = {"adr": [], "spec": [], "provenance": {}}
        try:
            result = ril.governing_docs("package.json", empty_index)
        except Exception as exc:
            self.fail("governing_docs raised with no runner on empty provenance: {}".format(exc))
        self.assertEqual(result, [])


class BuildIndexTest(unittest.TestCase):
    """T-09: build_index(root) -> dict — prebuilt index with mtime caching.

    Returns {"adr": [...], "spec": [...], "provenance": {...}}.
    adr and spec are cached in readinject-index-cache.json under .markers/;
    provenance is always loaded fresh.  Missing dirs -> empty sub-structures.
    Cache errors degrade to a fresh build.  Never raises.
    """

    # ------------------------------------------------------------------
    # Fixture helpers
    # ------------------------------------------------------------------

    def _write_adr(self, tmpdir, filename, status="accepted", title="Test ADR",
                   governs="src/app.py"):
        """Write a fixture ADR into tmpdir/.codearbiter/decisions/."""
        ddir = os.path.join(tmpdir, ".codearbiter", "decisions")
        os.makedirs(ddir, exist_ok=True)
        path = os.path.join(ddir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write("---\ntitle: {}\nstatus: {}\ngoverns: {}\n---\n# Body\n".format(
                title, status, governs,
            ))

    # ------------------------------------------------------------------
    # Structure: required keys
    # ------------------------------------------------------------------

    def test_build_index_has_required_keys(self):
        """build_index returns a dict with 'adr', 'spec', 'provenance' keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = ril.build_index(tmpdir)
            self.assertIsInstance(result, dict)
            for key in ("adr", "spec", "provenance"):
                self.assertIn(
                    key, result,
                    "build_index result must have key {!r}".format(key),
                )

    def test_build_index_adr_contains_accepted_entry(self):
        """With a fixture accepted ADR, build_index['adr'] contains the entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_adr(tmpdir, "0003-x.md", title="ADR-0003 title",
                            governs="src/app.py")
            result = ril.build_index(tmpdir)
            adr_list = result.get("adr", [])
            self.assertEqual(len(adr_list), 1, "exactly one ADR entry expected")
            self.assertEqual(adr_list[0].get("adr"), "0003")

    def test_build_index_value_types(self):
        """adr and spec sub-values are lists; provenance is a dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = ril.build_index(tmpdir)
            self.assertIsInstance(result.get("adr"), list,
                                  "build_index['adr'] must be a list")
            self.assertIsInstance(result.get("spec"), list,
                                  "build_index['spec'] must be a list")
            self.assertIsInstance(result.get("provenance"), dict,
                                  "build_index['provenance'] must be a dict")

    # ------------------------------------------------------------------
    # Caching
    # ------------------------------------------------------------------

    def test_build_index_creates_cache_file(self):
        """After build_index is called, the cache file exists under .markers/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_adr(tmpdir, "0003-x.md")
            ril.build_index(tmpdir)
            cache_path = os.path.join(
                tmpdir, ".codearbiter", ".markers", "readinject-index-cache.json"
            )
            self.assertTrue(
                os.path.isfile(cache_path),
                "readinject-index-cache.json must exist after build_index call",
            )

    def test_build_index_second_call_returns_same_result(self):
        """Two consecutive build_index calls produce identical adr and spec lists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_adr(tmpdir, "0003-x.md", title="ADR-0003 title",
                            governs="src/app.py")
            result1 = ril.build_index(tmpdir)
            result2 = ril.build_index(tmpdir)
            self.assertEqual(
                result1.get("adr"), result2.get("adr"),
                "second build_index call must return same adr as first",
            )
            self.assertEqual(
                result1.get("spec"), result2.get("spec"),
                "second build_index call must return same spec as first",
            )

    def test_build_index_cache_write_failure_does_not_raise(self):
        """When the cache write fails (.markers is a file), build_index still returns
        valid data and does not raise."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a FILE at .markers — blocks directory creation and cache write.
            codearbiter_dir = os.path.join(tmpdir, ".codearbiter")
            os.makedirs(codearbiter_dir, exist_ok=True)
            markers_path = os.path.join(codearbiter_dir, ".markers")
            with open(markers_path, "w", encoding="utf-8") as f:
                f.write("I am a file, not a directory")
            # Set up a valid ADR.
            decisions_dir = os.path.join(codearbiter_dir, "decisions")
            os.makedirs(decisions_dir, exist_ok=True)
            with open(os.path.join(decisions_dir, "0003-x.md"), "w",
                      encoding="utf-8") as f:
                f.write("---\ntitle: Test\nstatus: accepted\n"
                        "governs: src/app.py\n---\n")
            try:
                result = ril.build_index(tmpdir)
            except Exception as exc:
                self.fail("build_index raised when cache write fails: {}".format(exc))
            self.assertIsInstance(result, dict)
            self.assertEqual(len(result.get("adr", [])), 1,
                             "valid ADR must still be returned on cache-write failure")

    # ------------------------------------------------------------------
    # Robustness: missing dirs
    # ------------------------------------------------------------------

    def test_build_index_missing_dirs_returns_empty_structures(self):
        """Missing .codearbiter/ dirs -> build_index returns empty adr/spec/provenance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # No .codearbiter/ at all.
            result = ril.build_index(tmpdir)
            self.assertEqual(result.get("adr"), [],
                             "adr must be [] when decisions/ is missing")
            self.assertEqual(result.get("spec"), [],
                             "spec must be [] when specs/ is missing")
            self.assertIsInstance(result.get("provenance"), dict,
                                  "provenance must be a dict (empty when dir missing)")

    def test_build_index_never_raises_on_nonexistent_root(self):
        """build_index never raises when root is a non-existent absolute path."""
        # Use absolute paths that do not exist so no directories can be created.
        # Do NOT use None, int, or relative values as root — those can create
        # relative directories in the CWD (discipline: only tempfile roots).
        bad_root = "/no/such/path/xyz123abc"
        try:
            result = ril.build_index(bad_root)
        except Exception as exc:
            self.fail("build_index raised on root={!r}: {}".format(
                repr(bad_root)[:40], exc))
        self.assertIsInstance(result, dict,
                               "build_index must return a dict for non-existent root")


class ComputeInjectionTest(unittest.TestCase):
    """T-09: compute_injection(root, session_id, rel, runner=None) -> str.

    End-to-end orchestrator.  Validates AC-09 (dedup), AC-10 (self-read guard
    and no-match fast-path), and AC-11 (cost guarantee — miss makes zero runner
    calls).  Every test uses a fresh hermetic tempfile root; no state escapes.
    """

    # ------------------------------------------------------------------
    # Fixture helpers
    # ------------------------------------------------------------------

    def _write_adr(self, tmpdir, filename, status="accepted", title="ADR title",
                   governs="src/app.py"):
        """Write a fixture ADR into tmpdir/.codearbiter/decisions/."""
        ddir = os.path.join(tmpdir, ".codearbiter", "decisions")
        os.makedirs(ddir, exist_ok=True)
        path = os.path.join(ddir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write("---\ntitle: {}\nstatus: {}\ngoverns: {}\n---\n# Body\n".format(
                title, status, governs,
            ))

    @staticmethod
    def _counting_runner():
        """Return (runner_fn, call_count_list) for zero-cost assertions."""
        call_count = [0]

        def runner(args, stdin_text):
            call_count[0] += 1
            return ""

        return runner, call_count

    # ------------------------------------------------------------------
    # AC-09: governed path injects once, then dedups
    # ------------------------------------------------------------------

    def test_governed_path_injects_once_then_dedups(self):
        """AC-09: first compute_injection on a governed path returns a non-empty
        string mentioning ADR-0003; a second call with the same (session, rel)
        returns '' (marker suppresses)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_adr(tmpdir, "0003-x.md", title="HTTPS handling",
                            governs="src/app.py")
            # First call: must inject.
            result1 = ril.compute_injection(tmpdir, "s1", "src/app.py")
            self.assertIsInstance(result1, str)
            self.assertGreater(
                len(result1), 0,
                "first call on governed path must return non-empty string",
            )
            self.assertIn(
                "ADR-0003", result1,
                "injected context must mention ADR-0003; got {!r}".format(
                    result1[:80]),
            )
            # Second call: same (session_id, rel) -> dedup -> ''.
            result2 = ril.compute_injection(tmpdir, "s1", "src/app.py")
            self.assertEqual(
                result2, "",
                "second call with same (session, rel) must return '' (AC-09 dedup)",
            )

    # ------------------------------------------------------------------
    # AC-10: self-read guard
    # ------------------------------------------------------------------

    def test_self_read_guard(self):
        """AC-10: rel under .codearbiter/ -> '' AND zero runner calls AND no marker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            runner, call_count = self._counting_runner()
            rel = ".codearbiter/specs/whatever.md"
            result = ril.compute_injection(tmpdir, "s1", rel, runner=runner)
            # Must return ''.
            self.assertEqual(
                result, "",
                "self-read guard must return '' for .codearbiter/ path",
            )
            # Must make zero runner calls.
            self.assertEqual(
                call_count[0], 0,
                "self-read guard must make zero runner calls; "
                "call count = {}".format(call_count[0]),
            )
            # Must NOT write a dedup marker.
            self.assertFalse(
                ril.already_injected(tmpdir, "s1", rel),
                "self-read guard must NOT write a dedup marker",
            )

    def test_self_read_guard_backslash_path(self):
        """AC-10: backslash-normalised .codearbiter path also fires the guard."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = ril.compute_injection(
                tmpdir, "s1", ".codearbiter\\specs\\whatever.md"
            )
            self.assertEqual(
                result, "",
                "guard must fire for backslash-normalised .codearbiter paths",
            )

    # ------------------------------------------------------------------
    # AC-11: miss fast-path / cost guarantee
    # ------------------------------------------------------------------

    def test_miss_cost_guarantee(self):
        """AC-11 cost guarantee: unmatched path -> '' AND zero runner calls."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set up an ADR for a different path (not the one we will query).
            self._write_adr(tmpdir, "0003-x.md", governs="src/app.py")
            runner, call_count = self._counting_runner()
            result = ril.compute_injection(
                tmpdir, "s1", "src/unmatched.py", runner=runner
            )
            self.assertEqual(result, "", "miss must return ''")
            self.assertEqual(
                call_count[0], 0,
                "AC-11 cost guarantee: miss must make zero runner calls; "
                "call count = {}".format(call_count[0]),
            )

    def test_miss_does_not_record_marker(self):
        """AC-11: no marker written on a miss (marker only for injecting reads)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_adr(tmpdir, "0003-x.md", governs="src/app.py")
            rel = "src/unmatched.py"
            ril.compute_injection(tmpdir, "s1", rel)
            self.assertFalse(
                ril.already_injected(tmpdir, "s1", rel),
                "miss must NOT record a dedup marker",
            )

    # ------------------------------------------------------------------
    # Robustness
    # ------------------------------------------------------------------

    def test_missing_dirs_returns_empty(self):
        """Robustness: no .codearbiter/ dirs -> '' without raising."""
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                result = ril.compute_injection(tmpdir, "s1", "src/app.py")
            except Exception as exc:
                self.fail(
                    "compute_injection raised with missing dirs: {}".format(exc)
                )
            self.assertEqual(result, "",
                             "missing dirs must yield '' (nothing to inject)")

    def test_never_raises_on_garbage_session_and_rel(self):
        """compute_injection never raises when session_id or rel are garbage values.
        Root is always a tempdir; only session_id and rel are garbage here."""
        with tempfile.TemporaryDirectory() as tmpdir:
            garbage_combos = [
                (tmpdir, None, None, None),
                (tmpdir, 42, [], None),
                (tmpdir, "", "", None),
            ]
            for root, session_id, rel, runner in garbage_combos:
                try:
                    result = ril.compute_injection(root, session_id, rel, runner)
                except Exception as exc:
                    self.fail(
                        "compute_injection raised on (session_id={!r}, rel={!r}): "
                        "{}".format(repr(session_id)[:20], repr(rel)[:20], exc)
                    )
                self.assertIsInstance(
                    result, str,
                    "compute_injection must return str, not raise",
                )

    def test_never_raises_on_nonexistent_root(self):
        """compute_injection never raises when root is a non-existent absolute path."""
        # Use a non-existent absolute path so no directories can be created.
        # Do NOT use None, int, or relative values as root.
        bad_root = "/no/such/path/xyz999abc"
        try:
            result = ril.compute_injection(bad_root, "s", "a/b.py", None)
        except Exception as exc:
            self.fail(
                "compute_injection raised on non-existent root: {}".format(exc)
            )
        self.assertIsInstance(result, str)


class FailOpenAC12Test(unittest.TestCase):
    """T-10 / AC-12: every failure mode degrades to a safe result; NO input raises.

    Sweeps all public functions with adversarial / corrupt inputs to prove the
    fail-open guarantee: exceptions are always caught internally; callers always
    receive a well-formed, safe result (str / [] / dict as appropriate).

    Test discipline (hard constraint from the spec):
      - Every test that writes/reads under a root uses tempfile.TemporaryDirectory().
      - NEVER passes None, an int, '.', '', or the real repo root to any function
        that writes/reads under a root.
      - The suite leaves NO files outside its tempdirs; git status --porcelain
        shows no stray dirs/markers after two consecutive runs.
    """

    # ------------------------------------------------------------------
    # Part A validation: single-oversized-pointer preserves content (T-10 fix)
    # ------------------------------------------------------------------

    def test_assemble_context_single_oversized_pointer_preserves_content(self):
        """T-10 fix: first pointer alone > budget → truncated content, never bare '…'.

        This is the key regression guard for the assemble_context fix.  Before
        the fix, a single pointer whose text exceeded the budget caused accumulated
        to stay '' and the result to be '…' (highest-priority governing note lost).
        After the fix, the first pointer's text is truncated to fit and content is
        preserved.
        """
        pointers = [{"text": "x" * 601}]  # 151 tokens > default budget 150
        result = ril.assemble_context(pointers, budget=150)
        # The bare '…' is the pre-fix bug — content was silently lost.
        self.assertNotEqual(result, "…", "bare '…' means content was lost — fix regression")
        # First-pointer content must appear in the result.
        self.assertTrue(
            result.startswith("x"),
            "result must contain first-pointer content, not be a bare '…'",
        )
        # Must end with the ellipsis marker (indicating truncation).
        self.assertTrue(result.endswith("…"), "truncated result must end with '…'")
        # Token budget must still be satisfied.
        self.assertLessEqual(
            ril.token_estimate(result),
            150,
            "truncated result must satisfy token_estimate <= budget",
        )

    def test_assemble_context_single_oversized_high_priority_content_not_lost(self):
        """T-10 fix: a high-priority security-controls pointer > budget is truncated, not lost.

        Simulates an unusually long security-controls pointer whose text alone
        exceeds the 150-token budget.  The fix ensures the 'security-controls.md'
        prefix is still present in the output so the model sees the source.
        """
        long_sec = "security-controls.md governs this file — " + "x" * 600
        # len = 41 + 600 = 641 chars → ceil(641/4) = 161 tokens > 150
        pointers = [{"text": long_sec}]
        result = ril.assemble_context(pointers, budget=150)
        self.assertNotEqual(result, "…", "highest-priority content must not be lost")
        self.assertIn("security-controls", result, "security-controls mention must survive truncation")
        self.assertTrue(result.endswith("…"))
        self.assertLessEqual(ril.token_estimate(result), 150)

    # ------------------------------------------------------------------
    # assemble_context: non-list / None / dict-of-junk
    # ------------------------------------------------------------------

    def test_assemble_context_dict_of_junk_input(self):
        """assemble_context with a dict-of-junk argument → '', never raises."""
        junk = {"a": [1, 2], "b": None, "text": 42}
        try:
            result = ril.assemble_context(junk)
        except Exception as exc:
            self.fail("assemble_context raised on dict-of-junk: {}".format(exc))
        self.assertEqual(result, "")

    def test_assemble_context_none_input(self):
        """assemble_context(None) → '', never raises."""
        try:
            result = ril.assemble_context(None)
        except Exception as exc:
            self.fail("assemble_context raised on None: {}".format(exc))
        self.assertEqual(result, "")

    # ------------------------------------------------------------------
    # adr_pointers / spec_pointers: dict-of-junk index
    # ------------------------------------------------------------------

    def test_adr_pointers_dict_of_junk_index(self):
        """adr_pointers with a dict-of-junk index → [], never raises."""
        junk = {"a": 1, "b": [None], "text": "x"}
        try:
            result = ril.adr_pointers("src/app.py", junk)
        except Exception as exc:
            self.fail("adr_pointers raised on dict-of-junk index: {}".format(exc))
        self.assertEqual(result, [])

    def test_spec_pointers_dict_of_junk_index(self):
        """spec_pointers with a dict-of-junk index → [], never raises."""
        junk = {"spec": 99, "globs": None}
        try:
            result = ril.spec_pointers("src/app.py", junk)
        except Exception as exc:
            self.fail("spec_pointers raised on dict-of-junk index: {}".format(exc))
        self.assertEqual(result, [])

    # ------------------------------------------------------------------
    # provenance_pointer: None / dict-of-junk
    # ------------------------------------------------------------------

    def test_provenance_pointer_all_none(self):
        """provenance_pointer(None, None, None) → [], never raises."""
        try:
            result = ril.provenance_pointer(None, None, None)
        except Exception as exc:
            self.fail("provenance_pointer raised on all-None: {}".format(exc))
        self.assertEqual(result, [])

    def test_provenance_pointer_dict_of_junk_provenance(self):
        """provenance_pointer with dict-of-junk provenance values → [] or list, never raises."""
        junk_prov = {
            "doc1": {"entries": [{"path": "a", "hash": None, "claims": [{"claim": object()}]}]},
            "doc2": None,
            "doc3": "not-a-dict",
        }
        try:
            result = ril.provenance_pointer("a", junk_prov, {"a": "h"})
        except Exception as exc:
            self.fail("provenance_pointer raised on dict-of-junk: {}".format(exc))
        self.assertIsInstance(result, list)

    # ------------------------------------------------------------------
    # governing_docs: malformed index shapes
    # ------------------------------------------------------------------

    def test_governing_docs_missing_all_keys(self):
        """governing_docs with {} (missing all keys) → list, never raises."""
        try:
            result = ril.governing_docs("src/utils/helper.py", {})
        except Exception as exc:
            self.fail("governing_docs raised on empty index {{}}: {}".format(exc))
        self.assertIsInstance(result, list)

    def test_governing_docs_none_sub_values(self):
        """governing_docs with None for all sub-values → list, never raises."""
        bad = {"adr": None, "spec": None, "provenance": None}
        try:
            result = ril.governing_docs("src/app.py", bad)
        except Exception as exc:
            self.fail("governing_docs raised on None sub-values: {}".format(exc))
        self.assertIsInstance(result, list)

    def test_governing_docs_provenance_not_a_dict(self):
        """governing_docs with provenance='bad-string' → list, never raises."""
        bad = {"adr": [], "spec": [], "provenance": "bad-string"}
        try:
            result = ril.governing_docs("src/app.py", bad)
        except Exception as exc:
            self.fail("governing_docs raised when provenance is a string: {}".format(exc))
        self.assertIsInstance(result, list)

    def test_governing_docs_entries_not_list(self):
        """governing_docs with adr/spec as non-list values → list, never raises."""
        bad = {"adr": "not-list", "spec": 99, "provenance": {}}
        try:
            result = ril.governing_docs("src/app.py", bad)
        except Exception as exc:
            self.fail("governing_docs raised on non-list adr/spec: {}".format(exc))
        self.assertIsInstance(result, list)

    # ------------------------------------------------------------------
    # git-unavailable path: runner RAISES → degrade gracefully, no exception
    # ------------------------------------------------------------------

    def test_git_unavailable_governing_docs_no_raise_tiers_1_3_intact(self):
        """AC-12 git-unavailable: runner RAISES → tier-4 suppressed, tiers 1-3 still
        work, and no exception escapes governing_docs.

        batch_hash (_provenancelib) wraps runner exceptions and returns {}, so
        provenance_pointer's UNVERIFIABLE gate fires (rel absent from current_hashes)
        and suppresses tier 4.  Tiers 1-3 are pure and complete before batch_hash
        is even called; they survive the git failure.
        """
        def raising_runner(args, stdin_text):
            raise RuntimeError("git: command not found (simulated)")

        rel = "src/middleware/auth.ts"  # tier 1 fires: 'middleware' + 'auth' tokens
        stored_hash = "abc123def456"
        index = {
            "adr": [],
            "spec": [],
            "provenance": {
                "tech-stack": {
                    "doc": "tech-stack",
                    "entries": [{
                        "path": rel,
                        "hash": stored_hash,
                        "drift_trigger": True,
                        "claims": [{"claim": "some claim", "confidence": "strong"}],
                    }],
                }
            },
        }

        try:
            result = ril.governing_docs(rel, index, raising_runner)
        except Exception as exc:
            self.fail(
                "governing_docs raised when runner raises (git-unavailable): {}".format(exc)
            )

        # Result must be a well-formed list.
        self.assertIsInstance(result, list, "result must be a list even when git is unavailable")

        tiers = [p.get("tier") for p in result if isinstance(p, dict)]

        # Tier 4 must be absent — batch_hash returns {} when runner raises, so
        # provenance_pointer suppresses the entry (path absent from current_hashes).
        self.assertNotIn(
            "standards",
            tiers,
            "tier-4 must be suppressed when git is unavailable; tiers = {!r}".format(tiers),
        )
        # Tier 1 must still work — security_pointer is pure and runs before batch_hash.
        self.assertIn(
            "security-controls",
            tiers,
            "tier-1 must survive git failure; tiers = {!r}".format(tiers),
        )

    def test_git_unavailable_compute_injection_no_raise(self):
        """AC-12 git-unavailable: runner RAISES inside compute_injection → str, no raise."""
        def raising_runner(args, stdin_text):
            raise RuntimeError("git not installed (simulated)")

        with tempfile.TemporaryDirectory() as root:
            rel = "src/middleware/auth.ts"
            # Write a provenance entry for rel so the lazy tier-4 gate fires and
            # invokes the runner.  batch_hash will catch the runner exception and
            # return {}, which provenance_pointer treats as UNVERIFIABLE.
            pdir = os.path.join(root, ".codearbiter", ".provenance")
            os.makedirs(pdir, exist_ok=True)
            prov_record = {
                "schema": 1,
                "doc": "tech-stack",
                "entries": [{
                    "path": rel,
                    "hash": "abc123",
                    "drift_trigger": True,
                    "claims": [{"claim": "claim text", "confidence": "strong"}],
                }],
            }
            with open(
                os.path.join(pdir, "tech-stack.json"), "w", encoding="utf-8"
            ) as fh:
                json.dump(prov_record, fh)

            try:
                result = ril.compute_injection(root, "sess-git-unavail", rel, runner=raising_runner)
            except Exception as exc:
                self.fail(
                    "compute_injection raised when runner raises (git-unavailable): {}".format(exc)
                )

            self.assertIsInstance(
                result, str, "compute_injection must return str, never raise"
            )

    # ------------------------------------------------------------------
    # accepted_adr_index / approved_spec_index: dirs-as-files + garbage files
    # ------------------------------------------------------------------

    def test_accepted_adr_index_decisions_is_a_file(self):
        """accepted_adr_index: .codearbiter/decisions is a FILE (not a dir) → [], never raises."""
        with tempfile.TemporaryDirectory() as root:
            cb = os.path.join(root, ".codearbiter")
            os.makedirs(cb, exist_ok=True)
            with open(os.path.join(cb, "decisions"), "w", encoding="utf-8") as fh:
                fh.write("I am a file masquerading as the decisions directory")
            try:
                result = ril.accepted_adr_index(root)
            except Exception as exc:
                self.fail(
                    "accepted_adr_index raised when decisions is a file: {}".format(exc)
                )
            self.assertEqual(result, [], "decisions-as-file must degrade to []")

    def test_accepted_adr_index_garbage_file_in_decisions(self):
        """accepted_adr_index: decisions/ contains an unreadable binary-garbage file → degrade,
        never raise.  The garbage file is skipped; valid ADRs (if any) are still indexed."""
        with tempfile.TemporaryDirectory() as root:
            ddir = os.path.join(root, ".codearbiter", "decisions")
            os.makedirs(ddir, exist_ok=True)
            with open(os.path.join(ddir, "0001-garbage.md"), "wb") as fh:
                fh.write(b"\xff\xfe\x00\x01\xff\xfe\x00\x01garbage\x80\x81\x82")
            try:
                result = ril.accepted_adr_index(root)
            except Exception as exc:
                self.fail(
                    "accepted_adr_index raised on binary-garbage ADR file: {}".format(exc)
                )
            self.assertIsInstance(result, list)

    def test_approved_spec_index_specs_is_a_file(self):
        """approved_spec_index: .codearbiter/specs is a FILE (not a dir) → [], never raises."""
        with tempfile.TemporaryDirectory() as root:
            cb = os.path.join(root, ".codearbiter")
            os.makedirs(cb, exist_ok=True)
            with open(os.path.join(cb, "specs"), "w", encoding="utf-8") as fh:
                fh.write("I am a file masquerading as the specs directory")
            try:
                result = ril.approved_spec_index(root)
            except Exception as exc:
                self.fail(
                    "approved_spec_index raised when specs is a file: {}".format(exc)
                )
            self.assertEqual(result, [], "specs-as-file must degrade to []")

    def test_approved_spec_index_garbage_file_in_specs(self):
        """approved_spec_index: specs/ contains a binary-garbage file → degrade, never raise."""
        with tempfile.TemporaryDirectory() as root:
            sdir = os.path.join(root, ".codearbiter", "specs")
            os.makedirs(sdir, exist_ok=True)
            with open(os.path.join(sdir, "garbage.md"), "wb") as fh:
                fh.write(b"\xff\xfe\x80\x81garbage\x00\x01\xff")
            try:
                result = ril.approved_spec_index(root)
            except Exception as exc:
                self.fail(
                    "approved_spec_index raised on binary-garbage spec file: {}".format(exc)
                )
            self.assertIsInstance(result, list)

    # ------------------------------------------------------------------
    # build_index: dirs-as-files
    # ------------------------------------------------------------------

    def test_build_index_decisions_is_a_file(self):
        """build_index: .codearbiter/decisions is a FILE → adr=[], never raises."""
        with tempfile.TemporaryDirectory() as root:
            cb = os.path.join(root, ".codearbiter")
            os.makedirs(cb, exist_ok=True)
            with open(os.path.join(cb, "decisions"), "w", encoding="utf-8") as fh:
                fh.write("not a directory")
            try:
                result = ril.build_index(root)
            except Exception as exc:
                self.fail(
                    "build_index raised when decisions is a file: {}".format(exc)
                )
            self.assertIsInstance(result, dict)
            self.assertEqual(
                result.get("adr", []), [],
                "adr must be [] when decisions is a file",
            )

    def test_build_index_specs_is_a_file(self):
        """build_index: .codearbiter/specs is a FILE → spec=[], never raises."""
        with tempfile.TemporaryDirectory() as root:
            cb = os.path.join(root, ".codearbiter")
            os.makedirs(cb, exist_ok=True)
            with open(os.path.join(cb, "specs"), "w", encoding="utf-8") as fh:
                fh.write("not a directory")
            try:
                result = ril.build_index(root)
            except Exception as exc:
                self.fail(
                    "build_index raised when specs is a file: {}".format(exc)
                )
            self.assertIsInstance(result, dict)
            self.assertEqual(
                result.get("spec", []), [],
                "spec must be [] when specs is a file",
            )

    # ------------------------------------------------------------------
    # compute_injection: corrupt ADR, corrupt provenance, weird rel/session_id
    # ------------------------------------------------------------------

    def test_compute_injection_corrupt_adr_frontmatter(self):
        """compute_injection: root with a CORRUPT ADR (garbage frontmatter) → str, never raises."""
        with tempfile.TemporaryDirectory() as root:
            ddir = os.path.join(root, ".codearbiter", "decisions")
            os.makedirs(ddir, exist_ok=True)
            with open(os.path.join(ddir, "0001-corrupt.md"), "wb") as fh:
                fh.write(b"\xff\xfe garbage: frontmatter \x00\x01status: not-yaml\n")
            try:
                result = ril.compute_injection(root, "sess-corrupt-adr", "src/app.py")
            except Exception as exc:
                self.fail(
                    "compute_injection raised on corrupt ADR frontmatter: {}".format(exc)
                )
            self.assertIsInstance(result, str)

    def test_compute_injection_corrupt_provenance_json(self):
        """compute_injection: root with a CORRUPT provenance JSON → str, never raises."""
        with tempfile.TemporaryDirectory() as root:
            pdir = os.path.join(root, ".codearbiter", ".provenance")
            os.makedirs(pdir, exist_ok=True)
            with open(
                os.path.join(pdir, "tech-stack.json"), "w", encoding="utf-8"
            ) as fh:
                fh.write("NOT VALID JSON {{{broken {{{{ ")
            try:
                result = ril.compute_injection(root, "sess-corrupt-prov", "package.json")
            except Exception as exc:
                self.fail(
                    "compute_injection raised on corrupt provenance JSON: {}".format(exc)
                )
            self.assertIsInstance(result, str)

    def test_compute_injection_none_rel(self):
        """compute_injection: rel=None → str, never raises."""
        with tempfile.TemporaryDirectory() as root:
            try:
                result = ril.compute_injection(root, "sess-none-rel", None)
            except Exception as exc:
                self.fail("compute_injection raised on None rel: {}".format(exc))
            self.assertIsInstance(result, str)

    def test_compute_injection_int_rel(self):
        """compute_injection: rel=42 → str, never raises."""
        with tempfile.TemporaryDirectory() as root:
            try:
                result = ril.compute_injection(root, "sess-int-rel", 42)
            except Exception as exc:
                self.fail("compute_injection raised on int rel: {}".format(exc))
            self.assertIsInstance(result, str)

    def test_compute_injection_weird_unicode_rel(self):
        """compute_injection: weird-unicode rel → str, never raises."""
        with tempfile.TemporaryDirectory() as root:
            weird = "\u200b\ufffd/weird\u2603path.py"
            try:
                result = ril.compute_injection(root, "sess-unicode", weird)
            except Exception as exc:
                self.fail(
                    "compute_injection raised on weird-unicode rel: {}".format(exc)
                )
            self.assertIsInstance(result, str)

    def test_compute_injection_none_session_id(self):
        """compute_injection: session_id=None → str, never raises."""
        with tempfile.TemporaryDirectory() as root:
            try:
                result = ril.compute_injection(root, None, "src/app.py")
            except Exception as exc:
                self.fail("compute_injection raised on None session_id: {}".format(exc))
            self.assertIsInstance(result, str)

    def test_compute_injection_int_session_id(self):
        """compute_injection: session_id=42 → str, never raises."""
        with tempfile.TemporaryDirectory() as root:
            try:
                result = ril.compute_injection(root, 42, "src/app.py")
            except Exception as exc:
                self.fail("compute_injection raised on int session_id: {}".format(exc))
            self.assertIsInstance(result, str)


if __name__ == "__main__":
    unittest.main()

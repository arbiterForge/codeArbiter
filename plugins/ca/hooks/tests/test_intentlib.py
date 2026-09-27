import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _intentlib as I  # noqa: E402
import _artifactlib as A  # noqa: E402


FULLY_COVERED_SPEC = """## Problem

Consumers cannot tell whether a shipped skill hardcodes a plugin table.

## Scope

- Add a guard script that flags a hardcoded plugin table in any shipped skill.
- Rewrite the release skill so it reads targets from a declared file instead.

**Out of scope:**

- Rewriting the unrelated documentation generator.

## Acceptance criteria

1. The guard script exits non-zero when a shipped skill hardcodes a plugin table.
2. The release skill reads every declared target from release-targets.md, never a hardcoded table.
"""

SPEC_WITH_UNCITED_SCOPE_BULLET = """## Scope

- Add a guard script that flags a hardcoded plugin table in any shipped skill.
- Migrate every existing per-target configuration file to the new layout.

## Acceptance criteria

1. The guard script exits non-zero when a shipped skill hardcodes a plugin table.
"""

# Deliberately worded WITHOUT "plugin" -- ISSUE_BODY_HOLE_2 below carries
# that word in unrelated prose ("...outside the plugin payload"), and a
# shared word is exactly what the citation heuristic keys on; sharing it
# by accident here would falsely mark the checkbox as cited.
SPEC_WITHOUT_PORTABILITY_CRITERION = """## Scope

- Add a guard script that flags a hardcoded lookup table in any shipped skill.

## Acceptance criteria

1. The guard script exits non-zero when a shipped skill hardcodes a lookup table.
"""

# Regression fixture: a non-bulleted closing sentence sits under the
# Acceptance criteria heading, AFTER the numbered list, and happens to
# reuse the scope bullet's own words ("migration", "per-target",
# "configuration"). If that prose line were ever counted as a criterion
# (as it was before this fixture was added), its vocabulary would falsely
# "cite" the bullet below and the finding would vanish -- exactly the
# false-negative direction #566 exists to close.
SPEC_WITH_TRAILING_PROSE_UNDER_CRITERIA = """## Scope

- Add a guard script that flags a hardcoded lookup table in any shipped skill.
- Migrate every existing per-target configuration file to the new layout.

## Acceptance criteria

1. The guard exits non-zero on a hardcoded lookup table.

These criteria were reviewed and approved; the migration effort for
per-target configuration remains for a future spec.

## Open questions

None.
"""

ISSUE_BODY_WITH_UNCITED_CHECKBOX = (
    "## Acceptance\n\n"
    "- [ ] A fresh clone installs and runs without touching anything "
    "beyond its own directory.\n"
)

ISSUE_BODY_WITH_CITED_CHECKBOX = (
    "## Acceptance\n\n"
    "- [ ] The guard script flags a hardcoded plugin table.\n"
)

# #563's own hole-2 wording, reproduced verbatim as the regression fixture
# named in #566's acceptance: this acceptance checkbox never became a
# numbered criterion, so bijection between plan and ledger passed while
# the property it names went unbuilt.
ISSUE_BODY_HOLE_2 = (
    "## Acceptance\n\n"
    "- [ ] a consumer repo with one artifact can run `/ca:release` end "
    "to end with no file outside the plugin payload\n"
)


class UncoveredIntentTest(unittest.TestCase):

    def test_uncited_scope_bullet_is_flagged(self):
        findings = I.uncovered_intent(SPEC_WITH_UNCITED_SCOPE_BULLET)
        self.assertEqual(len(findings), 1)
        self.assertTrue(findings[0].startswith("[UNCOVERED-SCOPE]"))
        self.assertIn("Migrate", findings[0])

    def test_uncited_acceptance_checkbox_is_flagged(self):
        findings = I.uncovered_intent(
            SPEC_WITHOUT_PORTABILITY_CRITERION, ISSUE_BODY_WITH_UNCITED_CHECKBOX)
        checkbox_findings = [f for f in findings if f.startswith("[UNCOVERED-CHECKBOX]")]
        self.assertEqual(len(checkbox_findings), 1)
        self.assertIn("fresh clone", checkbox_findings[0])

    def test_cited_acceptance_checkbox_is_not_flagged(self):
        findings = I.uncovered_intent(FULLY_COVERED_SPEC, ISSUE_BODY_WITH_CITED_CHECKBOX)
        self.assertEqual(findings, [])

    def test_fully_covered_spec_returns_empty(self):
        self.assertEqual(I.uncovered_intent(FULLY_COVERED_SPEC), [])

    def test_spec_with_no_linked_issue(self):
        # issue_body omitted entirely -- must not raise, and only the
        # scope check can fire (there is nothing to read a checkbox from).
        findings = I.uncovered_intent(SPEC_WITH_UNCITED_SCOPE_BULLET)
        self.assertTrue(all(not f.startswith("[UNCOVERED-CHECKBOX]") for f in findings))
        self.assertEqual(I.uncovered_intent(FULLY_COVERED_SPEC, None), [])

    def test_out_of_scope_bullets_are_never_flagged(self):
        # The out-of-scope bullet below deliberately shares no distinctive
        # word with either criterion, so if the boundary were not honored
        # it would be flagged -- this assertion is load-bearing, not
        # coincidentally satisfied by an accidental token overlap.
        findings = I.uncovered_intent(FULLY_COVERED_SPEC)
        self.assertEqual(findings, [])
        self.assertTrue(all("documentation generator" not in f for f in findings))

    def test_reproduces_hole_2_uncited_acceptance_checkbox(self):
        # Regression fixture (#566 acceptance): a spec whose criteria say
        # nothing about end-to-end portability, paired with the real issue
        # checkbox that named it. This must return non-empty -- the exact
        # case bijection alone let through.
        findings = I.uncovered_intent(SPEC_WITHOUT_PORTABILITY_CRITERION, ISSUE_BODY_HOLE_2)
        checkbox_findings = [f for f in findings if f.startswith("[UNCOVERED-CHECKBOX]")]
        self.assertEqual(len(checkbox_findings), 1)
        self.assertIn("end", checkbox_findings[0])
        self.assertIn("outside the plugin payload", checkbox_findings[0])

    def test_absent_scope_heading_yields_no_scope_findings(self):
        spec = "## Acceptance criteria\n\n1. Something happens.\n"
        self.assertEqual(I.uncovered_intent(spec), [])

    def test_non_string_spec_text_does_not_raise(self):
        self.assertEqual(I.uncovered_intent(None), [])

    def test_empty_issue_body_yields_no_checkbox_findings(self):
        self.assertEqual(I.uncovered_intent(FULLY_COVERED_SPEC, ""), [])

    def test_item_with_no_distinctive_tokens_is_not_flagged(self):
        spec = "## Scope\n\n- Do it now.\n\n## Acceptance criteria\n\n1. It works.\n"
        self.assertEqual(I.uncovered_intent(spec), [])

    def test_trailing_prose_under_criteria_heading_is_not_a_criterion(self):
        # See the fixture's own comment: a closing sentence under
        # Acceptance criteria, not itself numbered/bulleted, must not
        # contribute citation tokens -- the scope bullet it coincidentally
        # shares words with is still genuinely uncited.
        findings = I.uncovered_intent(SPEC_WITH_TRAILING_PROSE_UNDER_CRITERIA)
        scope_findings = [f for f in findings if f.startswith("[UNCOVERED-SCOPE]")]
        self.assertEqual(len(scope_findings), 1)
        self.assertIn("Migrate", scope_findings[0])


class CLITest(unittest.TestCase):

    @staticmethod
    def _write(tmp_dir, name, content):
        path = os.path.join(tmp_dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    def test_cli_exit_0_and_silent_on_full_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = self._write(tmp, "spec.md", FULLY_COVERED_SPEC)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = I.main(["uncovered-intent", spec])
            self.assertEqual(code, 0)
            self.assertEqual(out.getvalue(), "")

    def test_cli_exit_1_and_prints_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = self._write(tmp, "spec.md", SPEC_WITH_UNCITED_SCOPE_BULLET)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = I.main(["uncovered-intent", spec])
            self.assertEqual(code, 1)
            self.assertIn("[UNCOVERED-SCOPE]", out.getvalue())

    def test_cli_reads_issue_body_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = self._write(tmp, "spec.md", SPEC_WITHOUT_PORTABILITY_CRITERION)
            issue = self._write(tmp, "issue.txt", ISSUE_BODY_HOLE_2)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = I.main(["uncovered-intent", spec, "--issue-body", issue])
            self.assertEqual(code, 1)
            self.assertIn("[UNCOVERED-CHECKBOX]", out.getvalue())

    def test_cli_bad_invocation_exits_2(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = I.main([])
        self.assertEqual(code, 2)

    def test_cli_unknown_subcommand_exits_2(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = I.main(["not-a-subcommand"])
        self.assertEqual(code, 2)

    def test_cli_missing_spec_file_exits_2(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = I.main(["uncovered-intent", "/no/such/file.md"])
        self.assertEqual(code, 2)

    def test_cli_missing_issue_body_flag_value_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = self._write(tmp, "spec.md", FULLY_COVERED_SPEC)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = I.main(["uncovered-intent", spec, "--issue-body"])
            self.assertEqual(code, 2)

    def test_cli_missing_issue_body_file_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = self._write(tmp, "spec.md", FULLY_COVERED_SPEC)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = I.main(["uncovered-intent", spec, "--issue-body", "/no/such/issue.txt"])
            self.assertEqual(code, 2)


class HTMLCLITest(unittest.TestCase):
    def _run(self, *, valid=True, diagnostics=None, stale=False, issue=None):
        client = mock.Mock()
        client.call.side_effect = lambda operation, *args, **kwargs: (
            {"artifact_id": "SPEC-TEST", "gate": "ready", "valid": valid, "diagnostics": diagnostics, "model_sha256": "a" * 64}
            if operation == "validate" else
            {"artifact_id": "SPEC-TEST", "model_sha256": "b" * 64 if stale else "a" * 64}
        )
        client.outline.return_value = []
        with tempfile.TemporaryDirectory() as tmp:
            spec = CLITest._write(tmp, "spec.html", "<html></html>")
            argv = ["uncovered-intent", spec]
            if issue is not None:
                argv += ["--issue-body", CLITest._write(tmp, "issue.md", issue)]
            out, err = io.StringIO(), io.StringIO()
            with (
                mock.patch.object(A, "resolve_spec_file", return_value=(client, {"artifact_id": "SPEC-TEST"})),
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err),
            ):
                code = I.main(argv)
            return code, out.getvalue(), err.getvalue()

    def test_html_null_diagnostics_passes_valid_spec_only(self):
        for diagnostics in (None, []):
            with self.subTest(diagnostics=diagnostics):
                self.assertEqual(self._run(diagnostics=diagnostics), (0, "", ""))

    def test_html_null_diagnostics_does_not_override_invalid_verdict(self):
        self.assertEqual(self._run(valid=False), (1, "", ""))
        finding = {"code": "UNCOVERED_SCOPE", "message": "A scope item has no criterion."}
        for valid in (True, False):
            with self.subTest(valid=valid):
                code, out, err = self._run(valid=valid, diagnostics=[finding])
                self.assertEqual(code, 1)
                self.assertIn("[INVALID-HTML-SPEC] UNCOVERED_SCOPE", out)
                self.assertEqual(err, "")

    def test_html_malformed_diagnostics_fail_closed(self):
        for diagnostics in ({}, "", False, 0, "bad", {"code": "bad"}):
            with self.subTest(diagnostics=diagnostics):
                code, out, err = self._run(diagnostics=diagnostics)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertIn("diagnostics must be a list or null", err)

    def test_html_null_diagnostics_preserves_stale_read_block(self):
        code, out, err = self._run(stale=True)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("HTML spec changed during intent verification", err)

    def test_html_null_diagnostics_still_checks_issue_requirements(self):
        code, out, err = self._run(issue="- [ ] Preserve export ordering.\n")
        self.assertEqual(code, 1)
        self.assertIn("[UNCOVERED-CHECKBOX]", out)
        self.assertEqual(err, "")


class HTMLIntentResponseTest(unittest.TestCase):
    """Exercise the real CLI branch with explicitly synthetic bridge responses."""

    def invoke(self, result, *, issue=None, fresh=None, failure=None, retired=False):
        import copy
        import types
        from pathlib import Path
        from unittest import mock
        calls = []
        identity = {"artifact_id": "SPEC-TEST", "model_sha256": "a" * 64}
        fresh = identity if fresh is None else fresh

        def call(operation, request, **kwargs):
            calls.append((operation, request, kwargs))
            if failure is not None:
                raise failure
            if operation == "validate":
                return copy.deepcopy(result)
            if operation == "identity":
                return copy.deepcopy(fresh)
            if operation == "read":
                return {"record": {"statement": "The guard detects deployment mistakes."}}
            self.fail("unexpected bridge operation: " + operation)

        client = types.SimpleNamespace(
            call=call, outline=lambda _: [
                {"id": "AC-001", "kind": "criteria", "retired": retired}])
        bridge = types.ModuleType("_artifactlib")
        bridge.helper_installation = lambda _: "synthetic-installation"
        bridge.resolve_spec_file = lambda *args: (client, {"artifact_id": "SPEC-TEST"})
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "spec.html")
            with open(path, "w", encoding="utf-8") as file:
                file.write("<!doctype html>\n")
            argv = ["uncovered-intent", path]
            if issue is not None:
                issue_path = os.path.join(tmp, "issue.txt")
                with open(issue_path, "w", encoding="utf-8") as file:
                    file.write(issue)
                argv += ["--issue-body", issue_path]
            before = {name: Path(tmp, name).read_bytes()
                      for name in os.listdir(tmp)}
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.dict(sys.modules, {"_artifactlib": bridge}),                     contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = I.main(argv)
            after = {name: Path(tmp, name).read_bytes()
                     for name in os.listdir(tmp)}
            self.assertEqual(before, after, "intent checking must not modify input files")
        self.assertTrue(all(op in {"validate", "identity", "read"} for op, _, _ in calls))
        return code, out.getvalue(), err.getvalue(), calls

    @staticmethod
    def response(valid=True, diagnostics=None):
        return {"artifact_id": "SPEC-TEST", "gate": "ready",
                "model_sha256": "a" * 64, "valid": valid, "diagnostics": diagnostics}

    def test_native_null_diagnostics_succeeds_without_approval(self):
        code, out, err, calls = self.invoke(self.response())
        self.assertEqual((code, out, err), (0, "", ""))
        self.assertEqual(calls[0], ("validate", {"artifact_id": "SPEC-TEST", "gate": "ready"}, {"permit_invalid": True}))

    def test_native_empty_list_diagnostics_succeeds(self):
        self.assertEqual(self.invoke(self.response(diagnostics=[]))[:3], (0, "", ""))

    def test_invalid_result_with_empty_diagnostics_stays_invalid(self):
        for diagnostics in (None, []):
            with self.subTest(diagnostics=diagnostics):
                self.assertEqual(self.invoke(self.response(False, diagnostics))[0], 1)

    def test_native_diagnostics_remain_visible(self):
        result = self.response(False, [{"code": "NOT_READY", "message": "criterion missing"}])
        self.assertEqual(self.invoke(result)[:3],
                         (1, "[INVALID-HTML-SPEC] NOT_READY: criterion missing\n", ""))

    def test_diagnostics_cannot_hide_behind_valid_true(self):
        result = self.response(True, [{"code": "NOT_READY", "message": "criterion missing"}])
        self.assertEqual(self.invoke(result)[0], 1)

    def test_malformed_diagnostics_are_errors_not_empty_success(self):
        for diagnostics in ({}, False, 0, "", "bad", [None], [{}],
                            [{"code": 1, "message": "bad"}],
                            [{"code": "BAD", "message": []}]):
            with self.subTest(diagnostics=diagnostics):
                self.assertEqual(self.invoke(self.response(diagnostics=diagnostics))[0], 2)

    def test_valid_flag_requires_actual_boolean(self):
        for valid in (None, 0, 1, "false", "true", [], {}):
            with self.subTest(valid=valid):
                self.assertEqual(self.invoke(self.response(valid, []))[0], 2)

    def test_response_must_name_selected_artifact_and_ready_gate(self):
        for field, value in (("artifact_id", "SPEC-OTHER"), ("gate", "structural")):
            with self.subTest(field=field):
                result = self.response(diagnostics=[])
                result[field] = value
                self.assertEqual(self.invoke(result)[0], 2)

    def test_missing_required_response_field_is_an_error(self):
        for field in ("artifact_id", "gate", "model_sha256", "valid"):
            with self.subTest(field=field):
                result = self.response(diagnostics=[])
                del result[field]
                self.assertEqual(self.invoke(result)[0], 2)

    def test_changed_identity_still_refuses_success(self):
        fresh = {"artifact_id": "SPEC-TEST", "model_sha256": "b" * 64}
        self.assertEqual(self.invoke(self.response(diagnostics=[]), fresh=fresh)[0], 2)

    def test_fresh_identity_must_name_same_artifact(self):
        fresh = {"artifact_id": "SPEC-OTHER", "model_sha256": "a" * 64}
        self.assertEqual(self.invoke(self.response(diagnostics=[]), fresh=fresh)[0], 2)

    def test_bridge_failure_stays_error(self):
        code, out, err, _ = self.invoke(self.response(), failure=RuntimeError("CAPABILITY_MISSING"))
        self.assertEqual((code, out), (2, ""))
        self.assertIn("CAPABILITY_MISSING", err)

    def test_issue_checkbox_coverage_and_retirement_are_preserved(self):
        result = self.response()
        self.assertEqual(self.invoke(result, issue="- [ ] guard detects deployment mistakes")[0], 0)
        self.assertEqual(self.invoke(result, issue="- [ ] zebraprotocol interoperability")[0], 1)
        self.assertEqual(self.invoke(result, issue="- [ ] guard detects deployment mistakes", retired=True)[0], 1)


if __name__ == "__main__":
    unittest.main()

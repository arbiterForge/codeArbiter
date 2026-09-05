#!/usr/bin/env python3
"""Read-only merge-readiness and ADR source-preserving settings audit tests.

Run: python .github/scripts/test_branch_protection.py

The audit checks current-base enforcement and settings compatible with exact ADR
source-preserving merges. It must handle the absence of a privileged token in ordinary
CI, because `GET /repos/{owner}/{repo}/branches/{branch}/protection` requires
Administration:read and the workflow `permissions:` block has no key that
grants it.  Every field the audit reads is therefore three-valued: True, False,
or None for "this run could not see it". A definitely incompatible value is a
violation; None is a SKIP that says so out loud. These tests pin both halves, plus the
CLI's no-token exit, entirely offline - no network, no token, no fixtures on
disk.
"""
import importlib.util
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOL = REPO_ROOT / ".github" / "scripts" / "check_branch_protection.py"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

_spec = importlib.util.spec_from_file_location("check_branch_protection", _TOOL)
module = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(module)


# The live response measured on 2026-07-25, verbatim in shape.  This is the
# defect #383 reports: one required context, and `strict: false` behind it.
LIVE_PROTECTION = {
    "required_status_checks": {
        "strict": False,
        "contexts": ["[GATE ] | [REPO] | Merge readiness"],
        "checks": [{"context": "[GATE ] | [REPO] | Merge readiness", "app_id": 15368}],
    },
    "required_pull_request_reviews": {"required_approving_review_count": 0},
    "enforce_admins": {"enabled": True},
    "required_linear_history": {"enabled": True},
    "required_conversation_resolution": {"enabled": True},
}

# Isolate #383's freshness rule from the separately guarded ADR ancestry policy.
FRESHNESS_PROTECTION = dict(LIVE_PROTECTION, required_linear_history={"enabled": False})


def settings_reader(protection=FRESHNESS_PROTECTION, repository=None):
    """Route the two REST resources; never substitute one document for another."""
    if repository is None:
        repository = {"allow_merge_commit": True}
    return lambda path: (200, protection if path.endswith("/protection") else repository)


def enforcement(**overrides):
    """An Enforcement with everything readable and compliant unless overridden."""
    fields = {
        "protected": True,
        "strict": True,
        "merge_queue": False,
        "contexts": (module.MERGE_READINESS_CONTEXT,),
    }
    fields.update(overrides)
    return module.Enforcement(**fields)


class AuditTest(unittest.TestCase):
    def test_strict_required_checks_satisfy_the_current_base_contract(self):
        # AC-1, first of the two sanctioned answers: an up-to-date branch
        # cannot carry a required check computed before main advanced.
        self.assertEqual(module.audit(enforcement(strict=True, merge_queue=False)), [])

    def test_an_enabled_merge_queue_satisfies_the_current_base_contract(self):
        # AC-1, the ruled-on answer.  The queue synthesises the prospective
        # merge commit and runs the gate on THAT, so `strict` is redundant and
        # is expected to stay false once the queue is switched on.  An audit
        # that demanded both would fail the moment the fix landed.
        self.assertEqual(module.audit(enforcement(strict=False, merge_queue=True)), [])

    def test_neither_strict_nor_a_queue_is_the_defect_this_audit_exists_for(self):
        # AC-3.  This is the live state on 2026-07-25 and the exact regression
        # the audit has to keep detecting after the maintainer's settings
        # change: enforcement silently switched back off.
        findings = module.audit(enforcement(strict=False, merge_queue=False))
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("strict", findings[0])
        self.assertIn("merge queue", findings[0])

    def test_a_dropped_merge_readiness_context_is_reported(self):
        # #383 asks for the single stable context to REMAIN the required check.
        # Un-requiring it makes every other guarantee vacuous - there would be
        # nothing whose passing SHA the base has to be current with.
        findings = module.audit(enforcement(contexts=()))
        self.assertEqual(len(findings), 1, findings)
        self.assertIn(module.MERGE_READINESS_CONTEXT, findings[0])

    def test_extra_required_contexts_are_not_a_weakening(self):
        # Requiring MORE is not the failure this audit hunts, and reporting it
        # would turn a deliberate hardening into a red merge gate.
        self.assertEqual(
            module.audit(
                enforcement(contexts=(module.MERGE_READINESS_CONTEXT, "[CHECK] | [REPO] | Other"))
            ),
            [],
        )

    def test_deleted_branch_protection_is_reported_on_its_own(self):
        # A 404 from the protection endpoint means "branch not protected" -
        # GitHub answers 403 when the token merely lacks rights, so this is a
        # real finding and not an unreadable field.  It short-circuits: listing
        # a missing context on an unprotected branch is noise.
        findings = module.audit(
            module.Enforcement(protected=False, strict=None, merge_queue=None, contexts=None)
        )
        self.assertEqual(len(findings), 1, findings)
        self.assertIn("no branch protection", findings[0].lower())

    def test_an_unreadable_field_is_a_skip_and_never_a_violation(self):
        # The ordinary-CI path.  Without Administration:read nothing is
        # readable, and a check that failed here would jam every merge for a
        # permission the default GITHUB_TOKEN cannot be granted.
        blind = module.Enforcement(protected=None, strict=None, merge_queue=None, contexts=None)
        self.assertEqual(module.audit(blind), [])
        self.assertNotEqual(module.unreadable(blind), [])

    def test_a_readable_merge_queue_alone_still_clears_the_base_contract(self):
        # Partial visibility is still worth something: `mergeQueue` is plain
        # repository-read in GraphQL, so a run that cannot see `strict` can
        # still prove the queue is on - and must not be reported as blind.
        partial = module.Enforcement(
            protected=None, strict=None, merge_queue=True, contexts=None
        )
        self.assertEqual(module.audit(partial), [])
        self.assertNotIn("strict", " ".join(module.unreadable(partial)))


class ProtectionParsingTest(unittest.TestCase):
    def test_enforcement_is_read_out_of_the_freshness_protection_document(self):
        read = module.enforcement_from_protection(FRESHNESS_PROTECTION, merge_queue=False)
        self.assertIs(read.protected, True)
        self.assertIs(read.strict, False)
        self.assertIs(read.merge_queue, False)
        self.assertEqual(read.contexts, (module.MERGE_READINESS_CONTEXT,))
        # The whole point: this document is the defect, so it must report one.
        self.assertEqual(len(module.audit(read)), 1)

    def test_contexts_fall_back_to_the_checks_array(self):
        # `contexts` is deprecated in favour of `checks`; a response that only
        # carries the newer array must not read as "the context was dropped".
        document = json.loads(json.dumps(FRESHNESS_PROTECTION))
        del document["required_status_checks"]["contexts"]
        read = module.enforcement_from_protection(document, merge_queue=True)
        self.assertEqual(read.contexts, (module.MERGE_READINESS_CONTEXT,))
        self.assertEqual(module.audit(read), [])

    def test_a_protection_document_with_no_required_status_checks_reports(self):
        document = {"required_linear_history": {"enabled": False}}
        read = module.enforcement_from_protection(document, merge_queue=False)
        self.assertIs(read.strict, False)
        self.assertEqual(read.contexts, ())
        self.assertEqual(len(module.audit(read)), 2, module.audit(read))


class ReadEnforcementTest(unittest.TestCase):
    """The transport seams, exercised with fakes - never a live request."""

    def test_a_forbidden_protection_read_degrades_to_unreadable(self):
        def rest(path):
            return 403, {"message": "Must have admin rights to Repository."}

        def graphql(query, variables):
            return 200, {"data": {"repository": {"mergeQueue": None}}}

        read = module.read_enforcement("o/n", "main", rest=rest, graphql=graphql)
        self.assertIsNone(read.protected)
        self.assertIsNone(read.strict)
        self.assertIsNone(read.contexts)
        # The queue answer came from GraphQL, which needs no admin rights.
        self.assertIs(read.merge_queue, False)
        self.assertEqual(module.audit(read), [], "a 403 must never be a violation")

    def test_an_unprotected_branch_is_read_as_a_definite_absence(self):
        def rest(path):
            return 404, {"message": "Branch not protected"}

        def graphql(query, variables):
            return 200, {"data": {"repository": {"mergeQueue": None}}}

        read = module.read_enforcement("o/n", "main", rest=rest, graphql=graphql)
        self.assertIs(read.protected, False)
        self.assertEqual(len(module.audit(read)), 1)

    def test_an_enabled_queue_is_read_out_of_the_graphql_response(self):
        rest = settings_reader()

        def graphql(query, variables):
            return 200, {"data": {"repository": {"mergeQueue": {"id": "MQ_kwDO"}}}}

        read = module.read_enforcement("o/n", "main", rest=rest, graphql=graphql)
        self.assertIs(read.merge_queue, True)
        self.assertEqual(module.audit(read), [], "strict is redundant once the queue is on")

    def test_a_graphql_error_leaves_the_queue_unreadable_rather_than_absent(self):
        # Reporting "no merge queue" because a query errored would fail the
        # audit for a transport problem, which is how a read-only check turns
        # into a merge jam.
        rest = settings_reader()

        def graphql(query, variables):
            return 200, {"errors": [{"message": "Something went wrong"}]}

        read = module.read_enforcement("o/n", "main", rest=rest, graphql=graphql)
        self.assertIsNone(read.merge_queue)
        self.assertEqual(module.audit(read), [])
        self.assertNotEqual(module.unreadable(read), [])


class CommandTest(unittest.TestCase):
    def test_the_cli_skips_cleanly_and_loudly_without_a_token(self):
        # The ordinary-CI contract: no token, exit 0, and an explanation of
        # what was NOT checked plus how to check it.  Silence here would be a
        # green check that proved nothing.
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = module.main(["--repo", "arbiterForge/codeArbiter", "--branch", "main"], token="")
        self.assertEqual(code, 0)
        printed = buffer.getvalue()
        self.assertIn("SKIP", printed)
        self.assertIn("GH_TOKEN", printed)

    def test_the_cli_fails_on_a_definite_violation(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = module.main(
                ["--repo", "arbiterForge/codeArbiter", "--branch", "main"],
                token="x",
                rest=settings_reader(),
                graphql=lambda query, variables: (
                    200,
                    {"data": {"repository": {"mergeQueue": None}}},
                ),
            )
        self.assertEqual(code, 1)
        self.assertIn(module.MERGE_READINESS_CONTEXT, buffer.getvalue())

    def test_the_cli_passes_once_the_merge_queue_is_enabled(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = module.main(
                ["--repo", "arbiterForge/codeArbiter", "--branch", "main"],
                token="x",
                rest=settings_reader(),
                graphql=lambda query, variables: (
                    200,
                    {"data": {"repository": {"mergeQueue": {"id": "MQ_kwDO"}}}},
                ),
            )
        self.assertEqual(code, 0)
        self.assertIn("OK", buffer.getvalue())


class SourcePreservingMergePolicyTest(unittest.TestCase):
    """PR #748 / Option A: settings must permit selector-required true merges."""

    def run_audit(self, *, protection=None, repository=None, protection_status=200,
                  repository_status=200):
        if protection is None:
            protection = dict(FRESHNESS_PROTECTION, required_status_checks={
                "strict": True, "contexts": [module.MERGE_READINESS_CONTEXT],
            })
        if repository is None:
            repository = {"allow_merge_commit": True}
        calls = []

        def rest(path):
            calls.append(path)
            if path == "/repos/o/n":
                return repository_status, repository
            self.assertEqual(path, "/repos/o/n/branches/main/protection")
            return protection_status, protection

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = module.main(
                ["--repo", "o/n", "--branch", "main"], token="private-token-sentinel",
                rest=rest, graphql=lambda *_args: (
                    200, {"data": {"repository": {"mergeQueue": None}}}),
            )
        self.assertNotIn("private-token-sentinel", buffer.getvalue())
        return code, buffer.getvalue(), calls

    def test_each_incompatible_setting_fails_even_with_current_base_proof(self):
        # BP-1: the two settings are independent requirements, not alternatives.
        for linear, allow in ((True, True), (False, False), (True, False)):
            with self.subTest(linear=linear, allow=allow):
                protection = dict(LIVE_PROTECTION, required_linear_history={"enabled": linear},
                                  required_status_checks={"strict": True,
                                                          "contexts": [module.MERGE_READINESS_CONTEXT]})
                code, output, _calls = self.run_audit(
                    protection=protection, repository={"allow_merge_commit": allow})
                self.assertEqual(code, 1, output)
                if linear:
                    self.assertIn("required_linear_history", output)
                if not allow:
                    self.assertIn("allow_merge_commit", output)
                self.assertIn("ADR", output)

    def test_lifecycle_findings_combine_with_existing_freshness_and_context_failures(self):
        # BP-1/4: a lifecycle conflict must not hide either #383 check.
        protection = dict(LIVE_PROTECTION, required_status_checks={"strict": False, "contexts": []})
        code, output, _calls = self.run_audit(protection=protection,
                                            repository={"allow_merge_commit": False})
        self.assertEqual(code, 1)
        for finding in ("required_linear_history", "allow_merge_commit", "strict",
                        module.MERGE_READINESS_CONTEXT):
            self.assertIn(finding, output)

    def test_missing_or_malformed_policy_booleans_are_unreadable_not_ok(self):
        # BP-2/3: no truthiness coercion or absent-field success.
        for field in ("required_linear_history", "allow_merge_commit"):
            for value in (None, 0, 1, "true", "false", [], {}):
                with self.subTest(field=field, value=value):
                    protection = dict(FRESHNESS_PROTECTION, required_status_checks={
                        "strict": True, "contexts": [module.MERGE_READINESS_CONTEXT]})
                    repository = {"allow_merge_commit": True}
                    if field == "required_linear_history":
                        protection[field] = {"enabled": value}
                    else:
                        repository[field] = value
                    code, output, _calls = self.run_audit(protection=protection, repository=repository)
                    self.assertEqual(code, 0, output)
                    self.assertIn("SKIP (partial)", output)
                    self.assertIn(field, output)
                    self.assertNotIn("OK:", output)
        for protection, repository, field in (({}, {"allow_merge_commit": True}, "required_linear_history"),
                                               (FRESHNESS_PROTECTION, {}, "allow_merge_commit")):
            _code, output, _calls = self.run_audit(protection=protection, repository=repository)
            self.assertIn(field, output)
            self.assertNotIn("OK:", output)

    def test_independent_setting_read_survives_other_endpoint_failure(self):
        # BP-2: inaccessible protection does not hide disabled repository merges.
        for status in (0, 401, 403, 404, 500):
            with self.subTest(endpoint="protection", status=status):
                code, output, _calls = self.run_audit(protection_status=status,
                                                    repository={"allow_merge_commit": False})
                self.assertEqual(code, 1, output)
                self.assertIn("allow_merge_commit", output)
            with self.subTest(endpoint="repository", status=status):
                code, output, _calls = self.run_audit(protection=LIVE_PROTECTION,
                                                    repository_status=status)
                self.assertEqual(code, 1, output)
                self.assertIn("required_linear_history", output)
                self.assertIn("SKIP (partial)", output)

    def test_complete_proof_reads_both_exact_rest_resources_and_reports_policy(self):
        # BP-3: the all-readable success is stronger than a partial audit.
        code, output, calls = self.run_audit()
        self.assertEqual(code, 0, output)
        self.assertIn("OK:", output)
        self.assertNotIn("SKIP", output)
        self.assertIn("source-preserving", output)
        self.assertCountEqual(calls, ["/repos/o/n", "/repos/o/n/branches/main/protection"])

    def test_malformed_resource_documents_remain_unreadable_without_crashing(self):
        # BP-2/3: a successful HTTP response is not itself a settings document.
        for value in (None, False, 1, "bad", []):
            for endpoint, field in (("/repos/o/n", "allow_merge_commit"),
                                    ("/repos/o/n/branches/main/protection", "required_linear_history")):
                with self.subTest(endpoint=endpoint, value=value):
                    buffer = io.StringIO()
                    valid = settings_reader(dict(FRESHNESS_PROTECTION, required_status_checks={
                        "strict": True, "contexts": [module.MERGE_READINESS_CONTEXT]}))
                    with redirect_stdout(buffer):
                        try:
                            code = module.main(["--repo", "o/n"], token="x",
                                               rest=lambda path: (200, value) if path == endpoint else valid(path),
                                               graphql=lambda *_args: (200, {"data": {"repository": {
                                                   "mergeQueue": None}}}))
                        except (AttributeError, TypeError) as error:
                            self.fail(f"malformed settings crashed instead of remaining unreadable: {error}")
                    self.assertEqual(code, 0, buffer.getvalue())
                    self.assertIn(field, buffer.getvalue())
                    self.assertIn("SKIP (partial)", buffer.getvalue())
                    self.assertNotIn("OK:", buffer.getvalue())
        for value in (None, False, 1, "bad", []):
            protection = dict(FRESHNESS_PROTECTION, required_linear_history=value,
                              required_status_checks={"strict": True,
                                                      "contexts": [module.MERGE_READINESS_CONTEXT]})
            code, output, _calls = self.run_audit(protection=protection)
            self.assertEqual(code, 0, output)
            self.assertIn("required_linear_history", output)
            self.assertNotIn("OK:", output)

    def test_malformed_graphql_queue_evidence_never_satisfies_freshness(self):
        # BP-6: only a null queue or the queried queue object is evidence.
        payloads = [None, False, [], "bad", {}, {"data": []}, {"data": {"repository": []}},
                    {"data": {"repository": {}}}]
        payloads.extend({"data": {"repository": {"mergeQueue": value}}}
                        for value in (False, True, 0, 1, "MQ_id", [], {}, {"id": None}, {"id": 1},
                                      {"id": ""}, {"id": "   "}))
        payloads.extend({"data": {"repository": {"mergeQueue": {"id": "MQ_id"}}}, "errors": errors}
                        for errors in ([], None, [{"message": "private-response-sentinel"}]))
        for payload in payloads:
            with self.subTest(payload=payload):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    try:
                        code = module.main(["--repo", "o/n"], token="x", rest=settings_reader(),
                                           graphql=lambda *_args: (200, payload))
                    except (AttributeError, TypeError) as error:
                        self.fail(f"malformed queue evidence crashed instead of staying unknown: {error}")
                self.assertEqual(code, 0, buffer.getvalue())
                self.assertIn("SKIP (partial)", buffer.getvalue())
                self.assertIn("merge queue", buffer.getvalue())
                self.assertNotIn("OK:", buffer.getvalue())
                self.assertNotIn("private-response-sentinel", buffer.getvalue())

    def test_malformed_required_status_check_evidence_is_partial_not_ok(self):
        # BP-7: nested freshness evidence has the same exact-schema boundary as
        # the Option A settings. Truthy strings and malformed collections must
        # never be coerced into current-base or required-context proof.
        malformed = [
            {"strict": value, "contexts": [module.MERGE_READINESS_CONTEXT]}
            for value in (None, 0, 1, "true", "false", [], {})
        ]
        malformed.extend((False, 1, "bad", [], {}))
        malformed.extend((
            {"strict": True, "contexts": module.MERGE_READINESS_CONTEXT},
            {"strict": True, "contexts": [module.MERGE_READINESS_CONTEXT, 1]},
            {"strict": True, "checks": "bad"},
            {"strict": True, "checks": [{"context": module.MERGE_READINESS_CONTEXT},
                                          {"context": 1}]},
        ))
        for checks in malformed:
            with self.subTest(checks=checks):
                protection = dict(FRESHNESS_PROTECTION, required_status_checks=checks)
                try:
                    code, output, _calls = self.run_audit(protection=protection)
                except (AttributeError, TypeError) as error:
                    self.fail(f"malformed required-status-check evidence crashed: {error}")
                self.assertEqual(code, 0, output)
                self.assertIn("SKIP (partial)", output)
                self.assertNotIn("OK:", output)


class WorkflowWiringTest(unittest.TestCase):
    def test_ordinary_ci_audits_public_merge_capability_without_an_admin_secret(self):
        # BP-5: optional Administration:read must not disable public policy reads.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        job = ci.split("  branch-protection:\n", 1)[1].split("\n  ci-passed:", 1)[0]
        self.assertIn("GH_TOKEN: ${{ secrets.BRANCH_PROTECTION_AUDIT_TOKEN }}", job)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", job)
        self.assertIn("contents: read", job)

    def test_the_audit_runs_in_a_job_the_merge_gate_actually_waits_for(self):
        # An audit nothing dispatches is a file, not a control.  The job is
        # registered in BOTH of ci-passed's registrations, the same way every
        # other enforced job is (issue #390's contract).
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  branch-protection:\n", ci)
        self.assertIn('name: "[CHECK] | [REPO] | Branch protection"', ci)
        self.assertIn("python .github/scripts/check_branch_protection.py", ci)
        aggregate = ci.split("  ci-passed:\n", 1)[1]
        self.assertIn("      - branch-protection\n", aggregate)
        self.assertIn("${{ needs['branch-protection'].result }}", aggregate)

    def test_the_audit_job_carries_no_path_gate_that_could_skip_it(self):
        # Enforcement can be switched off in the settings UI with no diff at
        # all, so a `needs: changes` gate would mean the audit never runs on
        # the change that mattered - there is none.
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        job = ci.split("  branch-protection:\n", 1)[1].split("\n  ", 1)[0]
        self.assertNotIn("needs: changes", job)
        self.assertNotIn("needs.changes.outputs", job)


if __name__ == "__main__":
    unittest.main(verbosity=2)

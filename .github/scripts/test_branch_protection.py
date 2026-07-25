#!/usr/bin/env python3
"""Unit tests for the read-only branch-protection audit (issue #383 AC-3).

Run: python .github/scripts/test_branch_protection.py

The audit answers one question - is main's merge-readiness enforcement still
switched on? - and it has to answer it WITHOUT a privileged token in ordinary
CI, because `GET /repos/{owner}/{repo}/branches/{branch}/protection` requires
Administration:read and the workflow `permissions:` block has no key that
grants it.  Every field the audit reads is therefore three-valued: True, False,
or None for "this run could not see it".  A definite False is a violation; a
None is a SKIP that says so out loud.  These tests pin both halves, plus the
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
    def test_enforcement_is_read_out_of_the_live_protection_document(self):
        read = module.enforcement_from_protection(LIVE_PROTECTION, merge_queue=False)
        self.assertIs(read.protected, True)
        self.assertIs(read.strict, False)
        self.assertIs(read.merge_queue, False)
        self.assertEqual(read.contexts, (module.MERGE_READINESS_CONTEXT,))
        # The whole point: this document is the defect, so it must report one.
        self.assertEqual(len(module.audit(read)), 1)

    def test_contexts_fall_back_to_the_checks_array(self):
        # `contexts` is deprecated in favour of `checks`; a response that only
        # carries the newer array must not read as "the context was dropped".
        document = json.loads(json.dumps(LIVE_PROTECTION))
        del document["required_status_checks"]["contexts"]
        read = module.enforcement_from_protection(document, merge_queue=True)
        self.assertEqual(read.contexts, (module.MERGE_READINESS_CONTEXT,))
        self.assertEqual(module.audit(read), [])

    def test_a_protection_document_with_no_required_status_checks_reports(self):
        document = {"required_linear_history": {"enabled": True}}
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
        def rest(path):
            return 200, LIVE_PROTECTION

        def graphql(query, variables):
            return 200, {"data": {"repository": {"mergeQueue": {"id": "MQ_kwDO"}}}}

        read = module.read_enforcement("o/n", "main", rest=rest, graphql=graphql)
        self.assertIs(read.merge_queue, True)
        self.assertEqual(module.audit(read), [], "strict is redundant once the queue is on")

    def test_a_graphql_error_leaves_the_queue_unreadable_rather_than_absent(self):
        # Reporting "no merge queue" because a query errored would fail the
        # audit for a transport problem, which is how a read-only check turns
        # into a merge jam.
        def rest(path):
            return 200, LIVE_PROTECTION

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
                rest=lambda path: (200, LIVE_PROTECTION),
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
                rest=lambda path: (200, LIVE_PROTECTION),
                graphql=lambda query, variables: (
                    200,
                    {"data": {"repository": {"mergeQueue": {"id": "MQ_kwDO"}}}},
                ),
            )
        self.assertEqual(code, 0)
        self.assertIn("OK", buffer.getvalue())


class WorkflowWiringTest(unittest.TestCase):
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

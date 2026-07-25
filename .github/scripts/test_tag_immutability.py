#!/usr/bin/env python3
"""Unit tests for the read-only published-tag drift audit (issue #386 AC-3).

Run: python .github/scripts/test_tag_immutability.py

The audit answers one question - does every published tag still resolve to the
commit it was published at? - and it answers it from a committed manifest of
tag provenance plus one read-only listing of the live refs.  Like the
branch-protection audit it sits beside, every observation is three-valued:
True, False, or None for "this run could not see it".  A definite mismatch is a
security finding; an unreadable run is a loud SKIP.  These tests pin both
halves, the four governed namespaces, the pagination trap that would turn a
truncated listing into a fake mass-deletion, and the shipped manifest's shape -
entirely offline, with no network and no token.
"""
import importlib.util
import io
import json
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOL = REPO_ROOT / ".github" / "scripts" / "check_tag_immutability.py"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SECURITY_CONTROLS = REPO_ROOT / ".codearbiter" / "security-controls.md"
RELEASE_SKILL = REPO_ROOT / "core" / "surface" / "skills" / "release" / "SKILL.md"

_spec = importlib.util.spec_from_file_location("check_tag_immutability", _TOOL)
module = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(module)


# A slice of the live provenance measured on 2026-07-25, verbatim in shape.
RECORDED = {
    "v2.8.13": {
        "object_sha": "f001f8afa5fef0f37b8ab70a5e23b1fb0a96cb41",
        "object_type": "tag",
        "commit_sha": "1fba34644c85a34c24f4c022f0910744758593e0",
    },
    "ca-sandbox-v0.1.3": {
        "object_sha": "c1f1197ac4afaf8d07d86d8a776ce2380c4736c5",
        "object_type": "tag",
        "commit_sha": "f10385395762b02d66dad23d72aa494603083758",
    },
    "v2.1.0-beta.2": {
        "object_sha": "4371c8af16bb4b7aac4b9ff018123caf3793ab71",
        "object_type": "commit",
        "commit_sha": "4371c8af16bb4b7aac4b9ff018123caf3793ab71",
    },
}

_MOVED = "0" * 40


def recorded(source=None):
    return module.load_recorded(source if source is not None else RECORDED)


def live(**overrides):
    """The live ref map that agrees with RECORDED unless overridden."""
    tags = {name: entry["object_sha"] for name, entry in RECORDED.items()}
    tags.update(overrides)
    return tags


class NamespaceContract(unittest.TestCase):
    """The four release series #386 names, and nothing quietly outside them."""

    def test_all_four_published_namespaces_are_governed(self):
        self.assertEqual(
            ("v*", "ca-sandbox-v*", "ca-codex-v*", "ca-pi-v*"), module.NAMESPACES
        )

    def test_a_tag_in_each_namespace_is_governed(self):
        for name in ("v2.8.13", "ca-sandbox-v0.1.3", "ca-codex-v0.2.4", "ca-pi-v0.1.1"):
            self.assertTrue(module.is_governed(name), f"{name} should be governed")

    def test_a_namespace_prefix_does_not_swallow_an_unrelated_tag(self):
        # `v*` must not match `versioned-thing`, and the plugin prefixes must
        # not match a same-prefixed non-release tag.  A false positive here
        # turns ordinary repository tags into permanent audit noise.
        for name in ("versioned-thing", "ca-sandbox-nightly", "nightly-2026-01-01"):
            self.assertFalse(module.is_governed(name), f"{name} should NOT be governed")


class DriftAudit(unittest.TestCase):
    """A definite mismatch is a finding; anything unread is silence."""

    def test_unchanged_tags_produce_no_findings(self):
        self.assertEqual([], module.audit(recorded(), live()))

    def test_a_retargeted_tag_is_a_finding_naming_both_shas(self):
        findings = module.audit(recorded(), live(**{"v2.8.13": _MOVED}))
        self.assertEqual(1, len(findings), findings)
        self.assertIn("v2.8.13", findings[0])
        self.assertIn(RECORDED["v2.8.13"]["object_sha"], findings[0])
        self.assertIn(_MOVED, findings[0])

    def test_a_deleted_tag_is_a_finding(self):
        remaining = live()
        del remaining["ca-sandbox-v0.1.3"]
        findings = module.audit(recorded(), remaining)
        self.assertEqual(1, len(findings), findings)
        self.assertIn("ca-sandbox-v0.1.3", findings[0])
        self.assertIn("no longer exists", findings[0])

    def test_a_lightweight_tag_is_audited_like_any_other(self):
        # `v2.1.0-beta.2` is a bare commit ref, not an annotated tag object.
        # Force-pushing it is the cheapest possible retarget, so it must not
        # fall through the annotated-tag path unchecked.
        findings = module.audit(recorded(), live(**{"v2.1.0-beta.2": _MOVED}))
        self.assertEqual(1, len(findings), findings)
        self.assertIn("v2.1.0-beta.2", findings[0])

    def test_an_unreadable_run_reports_nothing(self):
        # None is "this run could not see the refs", never "every tag is gone".
        # Conflating the two would fail the merge gate on a token problem.
        self.assertEqual([], module.audit(recorded(), None))

    def test_an_unreadable_run_says_so_out_loud(self):
        self.assertNotEqual([], module.unreadable(None))
        self.assertEqual([], module.unreadable(live()))

    def test_a_new_published_tag_is_a_notice_not_a_finding(self):
        # A release publishes a tag the manifest has not yet recorded.  That is
        # the normal release path, not an attack, so it must never fail CI.
        extended = live(**{"ca-pi-v0.1.1": "a" * 40})
        self.assertEqual([], module.audit(recorded(), extended))
        self.assertEqual(["ca-pi-v0.1.1"], module.unrecorded(recorded(), extended))

    def test_an_ungoverned_live_tag_is_ignored_entirely(self):
        extended = live(**{"nightly-2026-01-01": "b" * 40})
        self.assertEqual([], module.audit(recorded(), extended))
        self.assertEqual([], module.unrecorded(recorded(), extended))

    def test_every_drifted_tag_is_reported_not_just_the_first(self):
        moved = live(**{"v2.8.13": _MOVED})
        del moved["ca-sandbox-v0.1.3"]
        self.assertEqual(2, len(module.audit(recorded(), moved)))


class LiveRefReader(unittest.TestCase):
    """Reading the refs: paginated, read-only, and honest about failure."""

    def test_a_single_page_of_refs_is_read_into_a_name_to_sha_map(self):
        page = [
            {"ref": "refs/tags/v2.8.13", "object": {"sha": "f" * 40, "type": "tag"}},
            {"ref": "refs/tags/ca-pi-v0.1.1", "object": {"sha": "a" * 40, "type": "commit"}},
        ]
        calls = []

        def rest(path):
            calls.append(path)
            return 200, page if len(calls) == 1 else []

        self.assertEqual(
            {"v2.8.13": "f" * 40, "ca-pi-v0.1.1": "a" * 40},
            module.read_live_tags("owner/name", rest=rest),
        )

    def test_a_full_page_is_followed_by_the_next_page(self):
        # THE PAGINATION TRAP.  `GET /git/refs/tags` caps at 100 per page.  A
        # reader that stops after page 1 would, the moment this repo passes 100
        # tags, report every tag on page 2 as DELETED - a fabricated mass
        # security failure that no settings change caused.
        first = [
            {"ref": f"refs/tags/v9.0.{index}", "object": {"sha": f"{index:040d}", "type": "tag"}}
            for index in range(module.PER_PAGE)
        ]
        second = [{"ref": "refs/tags/v9.1.0", "object": {"sha": "c" * 40, "type": "tag"}}]
        pages = [first, second, []]

        def rest(path):
            return 200, pages.pop(0)

        tags = module.read_live_tags("owner/name", rest=rest)
        self.assertEqual(module.PER_PAGE + 1, len(tags))
        self.assertIn("v9.1.0", tags)

    def test_a_failed_page_makes_the_whole_read_unreadable(self):
        # A partial listing must never be handed to the audit: the tags it is
        # missing would read as deletions.  All-or-nothing is the only safe
        # reduction.
        pages = [
            (200, [{"ref": f"refs/tags/v9.0.{i}", "object": {"sha": f"{i:040d}", "type": "tag"}}
                   for i in range(module.PER_PAGE)]),
            (403, {"message": "Forbidden"}),
        ]

        def rest(path):
            return pages.pop(0)

        self.assertIsNone(module.read_live_tags("owner/name", rest=rest))

    def test_a_transport_failure_is_unreadable_rather_than_empty(self):
        self.assertIsNone(module.read_live_tags("owner/name", rest=lambda path: (0, {})))

    def test_an_empty_repository_reads_as_no_tags_not_as_unreadable(self):
        # GitHub answers 404 for `git/refs/tags` when a repository has no tags
        # at all.  That is a definite empty, not a blind spot.
        self.assertEqual({}, module.read_live_tags("owner/name", rest=lambda p: (404, {})))


class ShippedManifest(unittest.TestCase):
    """The committed provenance record itself."""

    def setUp(self):
        self.manifest = json.loads(module.MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_the_manifest_records_every_currently_published_tag(self):
        self.assertGreaterEqual(len(self.manifest["tags"]), 26)

    def test_every_recorded_tag_is_governed_and_fully_specified(self):
        for name, entry in self.manifest["tags"].items():
            self.assertTrue(module.is_governed(name), f"{name} is outside the namespaces")
            self.assertRegex(entry["object_sha"], r"^[0-9a-f]{40}$")
            self.assertRegex(entry["commit_sha"], r"^[0-9a-f]{40}$")
            self.assertIn(entry["object_type"], ("tag", "commit"))

    def test_a_lightweight_tag_records_its_commit_as_its_object(self):
        for name, entry in self.manifest["tags"].items():
            if entry["object_type"] == "commit":
                self.assertEqual(entry["object_sha"], entry["commit_sha"], name)

    def test_the_manifest_pins_the_live_shas_this_lane_verified(self):
        for name, entry in RECORDED.items():
            self.assertEqual(entry, self.manifest["tags"][name], name)

    def test_the_manifest_loads_through_the_tool_it_feeds(self):
        self.assertEqual(
            set(self.manifest["tags"]), set(module.load_recorded(self.manifest["tags"]))
        )


class CommandLine(unittest.TestCase):
    """The CLI's three exits: skip, clean, and a security failure."""

    def _run(self, **kwargs):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = module.main(["--repo", "owner/name"], **kwargs)
        return code, buffer.getvalue()

    def test_no_token_skips_loudly_and_passes(self):
        code, output = self._run(token="")
        self.assertEqual(0, code)
        self.assertIn("SKIP", output)

    def test_an_unreadable_listing_skips_loudly_and_passes(self):
        code, output = self._run(token="t", rest=lambda path: (0, {}), recorded=RECORDED)
        self.assertEqual(0, code)
        self.assertIn("SKIP", output)

    def test_a_clean_read_passes_and_names_what_it_verified(self):
        page = [
            {"ref": f"refs/tags/{name}", "object": {"sha": entry["object_sha"], "type": entry["object_type"]}}
            for name, entry in RECORDED.items()
        ]
        pages = [(200, page), (200, [])]
        code, output = self._run(
            token="t", rest=lambda path: pages.pop(0), recorded=RECORDED
        )
        self.assertEqual(0, code)
        self.assertIn("OK", output)
        self.assertIn(str(len(RECORDED)), output)

    def test_drift_fails_the_build_as_a_security_finding(self):
        page = [
            {"ref": f"refs/tags/{name}", "object": {"sha": _MOVED, "type": entry["object_type"]}}
            for name, entry in RECORDED.items()
        ]
        pages = [(200, page), (200, [])]
        code, output = self._run(
            token="t", rest=lambda path: pages.pop(0), recorded=RECORDED
        )
        self.assertEqual(1, code)
        self.assertIn("::error", output)
        self.assertIn("v2.8.13", output)


class RepositoryWiring(unittest.TestCase):
    """The audit is only a control if something runs it and something says so."""

    def test_the_audit_runs_in_a_job_registered_in_the_merge_gate(self):
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("check_tag_immutability.py", ci)
        self.assertIn('name: "[CHECK] | [REPO] | Published tag immutability"', ci)
        aggregate = ci.split("  ci-passed:", 1)[1]
        needs = re.search(r"(?ms)^    needs:\s*\n(?P<body>(?:      - [A-Za-z0-9_-]+\n)+)", aggregate)
        self.assertIn("      - tag-immutability\n", needs.group("body"))
        required = re.search(r'(?m)^\s+required_results="(?P<body>[^"\n]*)"\s*$', aggregate)
        self.assertIn("tag-immutability", required.group("body"))

    def test_the_audits_own_tests_run_unconditionally_in_that_job(self):
        # The audit skips without a token, so its offline unit tests are the
        # part that is always binding.
        self.assertIn("test_tag_immutability.py", CI_WORKFLOW.read_text(encoding="utf-8"))

    def test_the_release_skill_documents_recovery_as_a_new_version(self):
        # AC-4.  The people who could move a tag are the people reading this
        # file at the moment they would be tempted to.
        skill = RELEASE_SKILL.read_text(encoding="utf-8")
        self.assertIn("MUST NOT move, retarget, delete, or re-point a published tag", skill)
        self.assertIn(".github/published-tags.json", skill)

    def test_security_controls_records_tag_immutability_with_no_break_glass(self):
        controls = SECURITY_CONTROLS.read_text(encoding="utf-8")
        self.assertIn("## Published tag immutability", controls)
        self.assertIn("no break-glass", controls)


if __name__ == "__main__":
    unittest.main()

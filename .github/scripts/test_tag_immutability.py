#!/usr/bin/env python3
"""Unit tests for the read-only published-tag drift audit (issue #386 AC-3).

Run: python .github/scripts/test_tag_immutability.py

The audit answers one question - does every published tag still resolve to the
commit it was published at? - and it answers it from a committed manifest of
tag provenance plus one read-only listing of the live refs.  Like the
branch-protection audit it sits beside, every observation is three-valued:
True, False, or None for "this run could not see it".  A definite mismatch is a
security finding; an unreadable run is a loud SKIP.  These tests pin both
halves, the four governed namespaces, complete matching-ref response handling,
and the shipped manifest's shape -
entirely offline, with no network and no token.
"""
import importlib.util
import hashlib
import io
import json
import re
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOL = REPO_ROOT / ".github" / "scripts" / "check_tag_immutability.py"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SECURITY_CONTROLS = REPO_ROOT / ".codearbiter" / "security-controls.md"
RELEASE_SKILL = REPO_ROOT / "core" / "surface" / "skills" / "release" / "SKILL.md"
RELEASE_TARGETS = REPO_ROOT / ".codearbiter" / "release-targets.md"
LEGACY_MANIFEST = REPO_ROOT / ".github" / "legacy-published-tags.json"
RELEASE_PROVENANCE = REPO_ROOT / ".github" / "RELEASE-PROVENANCE.md"
PUBLISH_ACTION = REPO_ROOT / ".github" / "actions" / "publish-release" / "action.yml"
RECONCILE_TOOL = REPO_ROOT / ".github" / "scripts" / "reconcile_tag_receipt.py"
ADR = REPO_ROOT / ".codearbiter" / "decisions" / "0034-establish-closed-legacy-published-tag-provenance-epoch.md"
ADR_LIFECYCLE = REPO_ROOT / ".codearbiter" / "decisions" / "adr-lifecycle.jsonl"
TECH_STACK = REPO_ROOT / ".codearbiter" / "tech-stack.md"

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
    """Reading the complete matching-refs response honestly and read-only."""

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

    def test_more_than_100_matching_refs_are_read_in_exactly_one_request(self):
        # GitHub's matching-refs endpoint returns the complete array and does
        # not advertise page/per_page parameters. Inventing pagination repeats
        # the same response and makes a valid inventory look unreadable.
        response = [
            {"ref": f"refs/tags/v9.0.{index}", "object": {"sha": f"{index:040d}", "type": "tag"}}
            for index in range(101)
        ]
        calls = []

        def rest(path):
            calls.append(path)
            return 200, response

        tags = module.read_live_tags("owner/name", rest=rest)
        self.assertEqual(101, len(tags))
        self.assertEqual(
            ["/repos/owner/name/git/matching-refs/tags/"],
            calls,
        )

    def test_a_non_list_success_response_is_invalid_inventory(self):
        with self.assertRaises(module.InvalidInventory):
            module.read_live_tags(
                "owner/name", rest=lambda path: (200, {"message": "partial"})
            )

    def test_a_transport_failure_is_unreadable_rather_than_empty(self):
        self.assertIsNone(module.read_live_tags("owner/name", rest=lambda path: (0, {})))

    def test_an_empty_matching_response_reads_as_no_tags(self):
        self.assertEqual({}, module.read_live_tags("owner/name", rest=lambda p: (200, [])))

    def test_a_404_is_unreadable_not_an_empty_repository(self):
        self.assertIsNone(
            module.read_live_tags("owner/name", rest=lambda path: (404, {}))
        )


class ShippedManifest(unittest.TestCase):
    """The committed provenance record itself."""

    def setUp(self):
        self.manifest = json.loads(module.MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_the_manifest_retains_at_least_the_original_inventory(self):
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


class LegacyEpochContract(unittest.TestCase):
    """ADR-0034's closed historical observation epoch, without provenance laundering."""

    def setUp(self):
        self.document = json.loads(LEGACY_MANIFEST.read_text(encoding="utf-8"))
        self.records = module.load_legacy_manifest(self.document)

    def test_legacy_ledger_is_exactly_the_approved_closed_epoch(self):
        self.assertEqual("legacy-published-tags/v1", self.document["schema"])
        self.assertEqual(
            "0034-establish-closed-legacy-published-tag-provenance-epoch",
            self.document["adr"],
        )
        self.assertEqual("2026-09-04T20:45:43Z", self.document["observed_at"])
        self.assertEqual(44, self.document["record_count"])
        self.assertEqual(44, len(self.document["records"]))
        self.assertEqual(
            "26f2d1b06b494dbcc721367e09af52f32ca1a50a71dddb457557af2a48cd8c48",
            self.document["canonical_set_sha256"],
        )
        self.assertEqual(
            "cfb3f66e933edb6b1f075f3e089103115c95837b944d56e2c7338d0d3519e8a6",
            self.document["source_matrix_sha256"],
        )
        canonical = [
            {key: row[key] for key in (
                "tag", "evidence_grade", "source_id", "object_sha", "object_type", "commit_sha"
            )}
            for row in self.document["records"]
        ]
        payload = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(self.document["canonical_set_sha256"], hashlib.sha256(payload).hexdigest())

    def test_legacy_records_preserve_fields_order_and_evidence_grades(self):
        rows = self.document["records"]
        self.assertEqual(sorted(row["tag"] for row in rows), [row["tag"] for row in rows])
        self.assertTrue(all(row["observed_at"] == self.document["observed_at"] for row in rows))
        counts = {}
        for row in rows:
            self.assertEqual(
                {"tag", "object_sha", "object_type", "commit_sha", "observed_at", "source_id", "evidence_grade"},
                set(row),
            )
            counts[row["evidence_grade"]] = counts.get(row["evidence_grade"], 0) + 1
        self.assertEqual(
            {"publisher-log-corroborated": 15, "associated-run-metadata-only": 28,
             "current-release-metadata-only": 1},
            counts,
        )

    def test_schema_rejects_every_closed_set_and_metadata_mutation(self):
        mutations = []
        for key, value in (
            ("adr", "0035-other"), ("observed_at", "2026-09-05T00:00:00Z"),
            ("record_count", 45), ("canonical_set_sha256", "0" * 64),
            ("source_matrix_sha256", "0" * 64),
        ):
            changed = json.loads(json.dumps(self.document))
            changed[key] = value
            mutations.append(changed)
        for field, value in (("evidence_grade", "original-publication"),
                             ("object_sha", "0" * 40), ("source_id", "not-a-run")):
            changed = json.loads(json.dumps(self.document))
            changed["records"][0][field] = value
            mutations.append(changed)
        changed = json.loads(json.dumps(self.document))
        changed["records"].append(dict(changed["records"][0], tag="v99.0.0"))
        mutations.append(changed)
        for changed in mutations:
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    module.load_legacy_manifest(changed)

    def test_original_and_legacy_ledgers_must_be_strict_and_disjoint(self):
        original = module.load_original_manifest(json.loads(module.MANIFEST_PATH.read_text(encoding="utf-8")))
        module.validate_disjoint(original, self.records)
        overlap = dict(self.records)
        overlap[next(iter(original))] = next(iter(self.records.values()))
        with self.assertRaises(ValueError):
            module.validate_disjoint(original, overlap)
        malformed = json.loads(module.MANIFEST_PATH.read_text(encoding="utf-8"))
        malformed["tags"][next(iter(malformed["tags"]))]["extra"] = True
        with self.assertRaises(ValueError):
            module.load_original_manifest(malformed)

    def test_closed_set_is_bound_to_an_accepted_user_attributed_adr(self):
        adr = ADR.read_text(encoding="utf-8")
        frontmatter = adr.split("---", 2)[1]
        self.assertIn("status: accepted", frontmatter)
        self.assertIn("decided-by: SUaDtL@users.noreply.github.com", frontmatter)
        self.assertIn(".github/legacy-published-tags.json", frontmatter)
        self.assertIn(self.document["canonical_set_sha256"], adr)
        rows = [json.loads(line) for line in ADR_LIFECYCLE.read_text(encoding="utf-8").splitlines()]
        binding = [row for row in rows if row.get("event") == "acceptance"
                   and row.get("adr") == self.document["adr"]]
        self.assertEqual(1, len(binding))
        self.assertTrue(binding[0]["obligations_sealed"])
        self.assertEqual(
            "ae0933c619ce0d86f7b405ea35da7763314a966e050e72ae7b84c96df7d1fd18",
            binding[0]["obligations_sha256"],
        )

    def test_legacy_drift_diagnostic_claims_only_post_observation_movement(self):
        name, baseline = next(iter(self.records.items()))
        findings = module.audit_legacy({name: baseline}, {name: "0" * 40})
        self.assertEqual(1, len(findings))
        self.assertIn("legacy baseline", findings[0])
        self.assertIn("after its 2026-09-04T20:45:43Z observation", findings[0])
        self.assertNotIn("originally published", findings[0])
        self.assertNotIn("was published as", findings[0])

    def test_strict_preflight_uses_union_but_requires_receipts_for_future_tags(self):
        original = recorded()
        name, baseline = next(iter(self.records.items()))
        legacy = {name: baseline}
        page = [
            {"ref": f"refs/tags/{tag}", "object": {"sha": entry.object_sha, "type": entry.object_type}}
            for tag, entry in {**original, **legacy}.items()
        ]
        with redirect_stdout(io.StringIO()) as clean:
            code = module.main(["--repo", "owner/name", "--require-recorded"], token="t",
                               recorded=RECORDED, legacy=legacy, rest=lambda path: (200, page))
        self.assertEqual(0, code, clean.getvalue())
        page.append({"ref": "refs/tags/v99.0.0", "object": {"sha": "a" * 40, "type": "tag"}})
        with redirect_stdout(io.StringIO()) as future:
            code = module.main(["--repo", "owner/name", "--require-recorded"], token="t",
                               recorded=RECORDED, legacy=legacy, rest=lambda path: (200, page))
        self.assertEqual(1, code)
        self.assertIn("original-publication receipt", future.getvalue())

    def test_receipt_writers_have_no_legacy_ledger_mutation_surface(self):
        for path in (PUBLISH_ACTION, RECONCILE_TOOL):
            self.assertNotIn("legacy-published-tags.json", path.read_text(encoding="utf-8"), path)

    def test_public_policy_names_epoch_risk_review_and_no_break_glass(self):
        provenance = RELEASE_PROVENANCE.read_text(encoding="utf-8")
        controls = SECURITY_CONTROLS.read_text(encoding="utf-8")
        for text in (provenance, controls):
            self.assertIn("2026-09-04T20:45:43Z", text)
            self.assertIn("legacy-published-tags.json", text)
            self.assertIn("not original-publication proof", text)
            self.assertIn("no break-glass", text)
        self.assertIn("new accepted, user-attributed ADR", provenance)


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

    def test_no_token_cannot_bypass_ledger_schema_validation(self):
        with patch.object(module, "_read_json", side_effect=ValueError("invalid")):
            code, output = self._run(token="")
        self.assertEqual(1, code)
        self.assertIn("invalid publication or legacy provenance ledger", output)

    def test_an_unreadable_listing_skips_loudly_and_passes(self):
        code, output = self._run(token="t", rest=lambda path: (0, {}), recorded=RECORDED)
        self.assertEqual(0, code)
        self.assertIn("SKIP", output)

    def test_a_404_listing_skips_loudly_in_ordinary_observation(self):
        code, output = self._run(token="t", rest=lambda path: (404, {}), recorded=RECORDED)
        self.assertEqual(0, code)
        self.assertIn("SKIP", output)
        self.assertNotIn("no longer exists", output)

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

    def test_legal_working_tag_types_cannot_hide_a_moved_release(self):
        page = [{"ref": f"refs/tags/{name}", "object": {"sha": _MOVED, "type": "tag"}}
                for name in RECORDED]
        for object_type in ("blob", "tree"):
            with self.subTest(object_type=object_type):
                inventory = page + [{"ref": "refs/tags/working-object", "object": {
                    "sha": "d" * 40, "type": object_type}}]
                code, output = self._run(token="t", rest=lambda path: (200, inventory), recorded=RECORDED)
                self.assertEqual(code, 1)
                self.assertIn("MOVED", output)
                self.assertNotIn("SKIP", output)

    def test_malformed_inventory_fails_ordinary_ci_instead_of_skipping(self):
        code, output = self._run(
            token="t", rest=lambda path: (200, [{"ref": "refs/tags/v1.0.0"}]),
            recorded=RECORDED,
        )
        self.assertEqual(1, code)
        self.assertIn("invalid live tag inventory", output)
        self.assertNotIn("SKIP", output)


class StrictReleaseObservation(unittest.TestCase):
    """LG01: unavailable or incomplete prior provenance cannot authorize release."""

    def _run(self, **kwargs):
        arguments = module.argparse.Namespace(
            repo="owner/name", manifest=str(module.MANIFEST_PATH),
            legacy_manifest=str(module.LEGACY_MANIFEST_PATH), require_recorded=True,
        )
        buffer = io.StringIO()
        # Isolate the decision from CLI spelling so the baseline fails on its
        # permissive result, not on argparse rejecting a not-yet-added option.
        with patch.object(module.argparse.ArgumentParser, "parse_args", return_value=arguments):
            with redirect_stdout(buffer):
                result = module.main([], **kwargs)
        return result, buffer.getvalue()

    def test_missing_credentials_refuses_release(self):
        code, output = self._run(token="")
        self.assertEqual(1, code)
        self.assertIn("::error", output)

    def test_prerelease_with_build_metadata_requires_a_record(self):
        tag = "ca-pi-v1.2.3-rc.1+build.4"
        page = [{"ref": "refs/tags/" + tag, "object": {"sha": "a" * 40, "type": "tag"}}]
        code, output = self._run(token="t", recorded={}, rest=lambda path: (200, page))
        self.assertEqual(code, 1)
        self.assertIn(tag, output)

    def test_real_cli_checks_clean_missing_and_moved_inventory(self):
        page = [{"ref": f"refs/tags/{name}", "object": {
            "sha": entry["object_sha"], "type": entry["object_type"]}}
            for name, entry in RECORDED.items()]
        missing = page + [{"ref": "refs/tags/v99.0.0", "object": {
            "sha": "a" * 40, "type": "tag"}}]
        moved = [dict(row, object={"sha": "b" * 40, "type": "tag"}) for row in page]
        for inventory, expected in ((page, 0), (missing, 1), (moved, 1)):
            with self.subTest(expected=expected, inventory=inventory):
                with redirect_stdout(io.StringIO()):
                    result = module.main(["--repo", "owner/name", "--require-recorded"],
                                         token="t", recorded=RECORDED,
                                         rest=lambda path: (200, inventory))
                self.assertEqual(result, expected)

    def test_real_cli_refuses_absent_repository(self):
        with redirect_stdout(io.StringIO()) as output:
            result = module.main(["--repo", "", "--require-recorded"], token="")
        self.assertEqual(result, 1)
        self.assertIn("release requires a repository", output.getvalue())

    def test_large_complete_inventory_reports_real_unrecorded_tags(self):
        response = [{"ref": f"refs/tags/v1.0.{index}", "object": {
            "sha": f"{index:040d}", "type": "tag"}} for index in range(101)]
        code, output = self._run(
            token="t", recorded={}, rest=lambda path: (200, response)
        )
        self.assertEqual(code, 1)
        self.assertIn("Unrecorded published tag", output)
        self.assertNotIn("complete live tag inventory", output)

    def test_malformed_inventory_shapes_fail_closed(self):
        valid = {"ref": "refs/tags/v1.0.0", "object": {"sha": "a" * 40, "type": "tag"}}
        invalid = [None, [], "ref", {"ref": 1, "object": valid["object"]},
                   {"ref": "refs/heads/v1.0.0", "object": valid["object"]},
                   {"ref": "refs/tags/", "object": valid["object"]},
                   dict(valid, object=None), dict(valid, object={"sha": 4, "type": "tag"}),
                   dict(valid, object={"sha": "A" * 40, "type": "tag"}),
                   dict(valid, object={"sha": "a" * 39, "type": "tag"}),
                   dict(valid, object={"sha": "a" * 40, "type": "unknown"})]
        for row in invalid:
            with self.subTest(row=row):
                code, output = self._run(token="t", recorded={}, rest=lambda path: (200, [row]))
                self.assertEqual(code, 1)
                self.assertIn("complete live tag inventory", output)

    def test_unavailable_inventory_refuses_release(self):
        code, output = self._run(token="t", rest=lambda path: (503, {}), recorded=RECORDED)
        self.assertEqual(1, code)
        self.assertIn("::error", output)

    def test_a_404_inventory_refuses_release_as_unreadable(self):
        code, output = self._run(token="t", rest=lambda path: (404, {}), recorded=RECORDED)
        self.assertEqual(1, code)
        self.assertIn("complete live tag inventory", output)
        self.assertNotIn("no longer exists", output)

    def test_unrecorded_tag_refuses_release(self):
        page = [
            {"ref": f"refs/tags/{name}", "object": {"sha": entry["object_sha"], "type": entry["object_type"]}}
            for name, entry in RECORDED.items()
        ]
        page.append({"ref": "refs/tags/v9.0.0", "object": {"sha": "a" * 40, "type": "tag"}})
        code, output = self._run(token="t", rest=lambda path: (200, page), recorded=RECORDED)
        self.assertEqual(1, code)
        self.assertIn("::error", output)
        self.assertIn("v9.0.0", output)

    def test_malformed_or_duplicate_inventory_cannot_authorize_release(self):
        page = [
            {"ref": f"refs/tags/{name}", "object": {"sha": entry["object_sha"], "type": entry["object_type"]}}
            for name, entry in RECORDED.items()
        ]
        for extra in ({}, page[0]):
            with self.subTest(extra=extra):
                code, output = self._run(
                    token="t", rest=lambda path: (200, page + [extra]), recorded=RECORDED,
                )
                self.assertEqual(1, code)
                self.assertIn("::error", output)


class RawHttpInventoryBoundary(unittest.TestCase):
    """A successful HTTP response must not become an unreadable-network skip."""

    class _Response:
        status = 200

        def __init__(self, body):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *unused):
            return False

        def read(self):
            return self._body

    def _send(self, body):
        response = self._Response(body)
        request = module.urllib.request.Request("https://example.invalid")
        with patch.object(module.urllib.request, "urlopen", return_value=response):
            return module._send(request)

    def test_duplicate_nested_key_in_http_200_is_invalid_inventory(self):
        body = (b'[{"ref":"refs/tags/v1.0.0","object":'
                b'{"sha":"0000000000000000000000000000000000000000",'
                b'"sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
                b'"type":"tag"}}]')
        with self.assertRaises(module.InvalidInventory):
            self._send(body)

    def test_malformed_http_200_body_is_invalid_inventory(self):
        for body in (b'[{', b'\xff'):
            with self.subTest(body=body), self.assertRaises(module.InvalidInventory):
                self._send(body)


class RepositoryWiring(unittest.TestCase):
    """The audit is only a control if something runs it and something says so."""

    def test_release_preflights_require_prior_tag_records(self):
        workflow = (REPO_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
        for job in ("preflight", "auto-preflight"):
            with self.subTest(job=job):
                body = re.search(
                    rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:|\Z)",
                    workflow,
                )
                self.assertIsNotNone(body, f"missing release preflight {job}")
                self.assertIn("check_tag_immutability.py", body.group(1))
                self.assertIn("--require-recorded", body.group(1))
                self.assertIn("--legacy-manifest .github/legacy-published-tags.json", body.group(1))

    def test_required_ci_audit_names_both_ledgers_explicitly(self):
        ci = CI_WORKFLOW.read_text(encoding="utf-8")
        job = ci.split("  tag-immutability:", 1)[1].split("  branch-protection:", 1)[0]
        self.assertIn("--manifest .github/published-tags.json", job)
        self.assertIn("--legacy-manifest .github/legacy-published-tags.json", job)

    def test_local_governance_matrix_names_all_provenance_suites(self):
        commands = TECH_STACK.read_text(encoding="utf-8")
        for script in ("test_tag_immutability.py", "test_tag_publication_receipt.py",
                       "test_reconcile_tag_receipt.py"):
            self.assertIn(f"python .github/scripts/{script}", commands)

    def test_publisher_retains_tag_identity_receipt_after_partial_failure(self):
        action = (REPO_ROOT / ".github/actions/publish-release/action.yml").read_text(encoding="utf-8")
        self.assertIn("Capture published tag identity receipt", action)
        receipt_steps = action.split("Capture published tag identity receipt", 1)[1]
        self.assertIn("always()", receipt_steps)
        self.assertIn("actions/upload-artifact@", receipt_steps)
        self.assertIn("if-no-files-found: error", receipt_steps)

    def test_receipt_capture_precedes_readback_and_survives_publish_failure(self):
        action = (REPO_ROOT / ".github/actions/publish-release/action.yml").read_text(encoding="utf-8")
        self.assertIn("id: publish", action)
        capture = re.search(
            r"(?ms)^    - name: Capture published tag identity receipt\n(.*?)(?=^    - |\Z)", action)
        self.assertIsNotNone(capture, "publication identity must survive a later release failure")
        body = capture.group(1)
        self.assertIn("always()", body)
        self.assertIn("steps.publish.outcome != 'skipped'", body)
        self.assertNotIn("steps.publish.outcome == 'success'", body)
        self.assertIn("tag_publication_receipt.py", body)
        for flag in ("--repo", "--tag", "--expected-commit", "--run-id",
                     "--run-attempt", "--workflow-sha", "--output"):
            self.assertIn(flag, body)
        self.assertLess(action.index("Capture published tag identity receipt"),
                        action.index("Verify the published Release names"))
        self.assertLess(action.index("actions/upload-artifact@"),
                        action.index("Verify the published Release names"))

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

    def test_receipt_logic_tests_are_registered_in_required_audit_job(self):
        job = CI_WORKFLOW.read_text(encoding="utf-8").split("  tag-immutability:", 1)[1].split("  branch-protection:", 1)[0]
        self.assertTrue("python .github/scripts/test_tag_publication_receipt.py" in job,
                        "required tag audit must exercise receipt capture failures offline")

    def test_reconciliation_tests_are_registered_in_required_audit_job(self):
        job = CI_WORKFLOW.read_text(encoding="utf-8").split("  tag-immutability:", 1)[1].split("  branch-protection:", 1)[0]
        self.assertTrue("python .github/scripts/test_reconcile_tag_receipt.py" in job,
                        "required tag audit must exercise append-only reconciliation offline")

    def test_the_release_skill_documents_recovery_as_a_new_version(self):
        # AC-4.  The people who could move a tag are the people reading this
        # file at the moment they would be tempted to.
        skill = RELEASE_SKILL.read_text(encoding="utf-8")
        self.assertIn("MUST NOT move, retarget, delete, or re-point a published tag", skill)
        # The skill must still make the provenance record load-bearing, and
        # must still name the one edit that destroys the evidence.
        self.assertIn("PROVENANCE_MANIFEST", skill)
        self.assertIn("MUST record every newly published tag", skill)
        self.assertIn("silence a red tag-immutability drift check", skill)

    def test_this_repos_ledger_path_is_declared_rather_than_hardcoded(self):
        # This assertion used to live above, as `assertIn(
        # ".github/published-tags.json", skill)`. That became wrong when the
        # release lane was made portable (#563): the skill ships to
        # consumers who have no `.github/` of ours, so naming our ledger
        # path in it is an unfollowable instruction, and
        # `check_skill_portability.py` now fails exactly that. The two
        # guards wanted opposite things and the skill could not satisfy both.
        #
        # The fact is still worth pinning — it just belongs against the
        # DECLARED file, which is where a this-repo fact now lives. If the
        # ledger were silently dropped from our rows, the drift audit would
        # go blind and nothing else would notice.
        declared = RELEASE_TARGETS.read_text(encoding="utf-8")
        self.assertIn("provenance-manifest: .github/published-tags.json", declared)

    def test_security_controls_records_tag_immutability_with_no_break_glass(self):
        controls = SECURITY_CONTROLS.read_text(encoding="utf-8")
        self.assertIn("## Published tag immutability", controls)
        self.assertIn("no break-glass", controls)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Hermetic tests for RA-11 release-state classification."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout


HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "check_command_route_release_state.py"
SPEC = importlib.util.spec_from_file_location("command_route_release_state", MODULE_PATH)
RELEASE_STATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RELEASE_STATE)


EXPECTED_TAG = "v2.17.0"
EXPECTED_COMMIT = "a" * 40


def evidence(**overrides):
    value = {
        "lookup": "available",
        "tagExists": True,
        "tagCommit": EXPECTED_COMMIT,
        "tagContainsRegistry": True,
        "tagRegistryMatches": True,
        "tagManifestVersion": "2.17.0",
        "release": {
            "draft": False,
            "tag_name": EXPECTED_TAG,
            "target_commitish": EXPECTED_COMMIT,
        },
    }
    value.update(overrides)
    return value


class ReleaseStateClassifierTest(unittest.TestCase):
    def classify(self, **overrides):
        return RELEASE_STATE.classify_release_state(
            expected_tag=EXPECTED_TAG,
            expected_version="2.17.0",
            evidence=evidence(**overrides),
        )

    def test_absent_tag_and_absent_release_is_a_planned_candidate(self):
        self.assertEqual(
            self.classify(
                lookup="missing",
                tagExists=False,
                tagCommit=None,
                tagContainsRegistry=False,
                tagRegistryMatches=False,
                tagManifestVersion=None,
                release=None,
            ),
            "planned",
        )

    def test_exact_non_draft_release_is_published(self):
        self.assertEqual(self.classify(), "published")

    def test_tag_without_a_release_is_not_publication(self):
        self.assertEqual(self.classify(lookup="missing", release=None), "tag-only")

    def test_draft_release_is_not_publication(self):
        release = dict(evidence()["release"], draft=True)
        self.assertEqual(self.classify(release=release), "draft")

    def test_api_unavailability_is_distinct_and_fail_closed(self):
        self.assertEqual(
            self.classify(lookup="unavailable", release=None),
            "api-unavailable",
        )

    def test_release_tag_mismatch_is_not_publication(self):
        release = dict(evidence()["release"], tag_name="v2.17.1")
        self.assertEqual(self.classify(release=release), "mismatch")

    def test_release_target_mismatch_is_not_publication(self):
        release = dict(evidence()["release"], target_commitish="b" * 40)
        self.assertEqual(self.classify(release=release), "mismatch")

    def test_tag_payload_mismatch_is_not_publication(self):
        for field, value in (
            ("tagContainsRegistry", False),
            ("tagRegistryMatches", False),
            ("tagManifestVersion", "2.17.1"),
        ):
            with self.subTest(field=field):
                self.assertEqual(self.classify(**{field: value}), "mismatch")


class DeclarationTest(unittest.TestCase):
    def metadata(self):
        return {
            "publishedWithoutMetadata": "2.16.0",
            "firstContainingRelease": "2.17.0",
            "retainThrough": "2.x",
            "earliestRemoval": "3.0.0",
        }

    def test_first_candidate_accepts_its_initial_manifest(self):
        declaration = RELEASE_STATE.validate_target_declaration(
            "claude", self.metadata(), "2.17.0", "v"
        )
        self.assertEqual(declaration.version, "2.17.0")
        self.assertEqual(declaration.tag, "v2.17.0")

    def test_later_manifest_does_not_rebase_the_first_release_or_force_a_bump(self):
        declaration = RELEASE_STATE.validate_target_declaration(
            "claude", self.metadata(), "2.18.0", "v"
        )
        self.assertEqual(declaration.version, "2.17.0")
        self.assertEqual(declaration.tag, "v2.17.0")

    def test_manifest_behind_the_declared_first_release_fails_closed(self):
        with self.assertRaisesRegex(RELEASE_STATE.ContractError, "behind"):
            RELEASE_STATE.validate_target_declaration(
                "claude", self.metadata(), "2.16.1", "v"
            )


class ApiResponseTest(unittest.TestCase):
    def test_http_404_is_missing_while_transport_failure_is_unavailable(self):
        missing = "HTTP/2.0 404 Not Found\ncontent-type: application/json\n\n{}\n"
        self.assertEqual(RELEASE_STATE.parse_api_response(1, missing), ("missing", None))
        self.assertEqual(RELEASE_STATE.parse_api_response(1, ""), ("unavailable", None))

    def test_http_200_returns_release_json(self):
        response = (
            "HTTP/2.0 200 OK\ncontent-type: application/json\n\n"
            '{"draft":false,"tag_name":"v2.17.0","target_commitish":"' +
            EXPECTED_COMMIT + '"}\n'
        )
        lookup, release = RELEASE_STATE.parse_api_response(0, response)
        self.assertEqual(lookup, "available")
        self.assertEqual(release["tag_name"], EXPECTED_TAG)


class PrePublishReleaseListTest(unittest.TestCase):
    def classify(self, pages, *, exit_code=0):
        return RELEASE_STATE.classify_release_list(
            EXPECTED_TAG,
            exit_code,
            json.dumps(pages),
        )

    def test_an_authenticated_complete_empty_list_is_missing(self):
        self.assertEqual(
            self.classify([[]]),
            "missing",
        )

    def test_exact_non_draft_release_in_any_page_is_published(self):
        self.assertEqual(
            self.classify([
                [{"draft": False, "tag_name": "v2.16.0"}],
                [{"draft": False, "tag_name": EXPECTED_TAG}],
            ]),
            "published",
        )

    def test_an_exact_draft_is_detected_instead_of_hidden_as_missing(self):
        self.assertEqual(
            self.classify([[{"draft": True, "tag_name": EXPECTED_TAG}]]),
            "draft",
        )

    def test_api_failure_malformed_entries_and_duplicate_tags_fail_closed(self):
        cases = (
            (1, "[]", "api-unavailable"),
            (0, "not-json", "mismatch"),
            (0, json.dumps([{"draft": False, "tag_name": EXPECTED_TAG}]), "mismatch"),
            (0, json.dumps([[["not-a-release"]]]), "mismatch"),
            (0, json.dumps([[{"draft": "false", "tag_name": EXPECTED_TAG}]]), "mismatch"),
            (
                0,
                json.dumps([[
                    {"draft": False, "tag_name": EXPECTED_TAG},
                    {"draft": True, "tag_name": EXPECTED_TAG},
                ]]),
                "mismatch",
            ),
        )
        for exit_code, response, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    RELEASE_STATE.classify_release_list(EXPECTED_TAG, exit_code, response),
                    expected,
                )


class ObserveIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "repo"
        self.evidence_dir = Path(self.temporary.name) / "evidence"
        self.repo.mkdir()
        self.evidence_dir.mkdir()
        subprocess.run(["git", "init", "--quiet"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"],
            cwd=self.repo,
            check=True,
        )
        registry = {
            "compatibility": {
                "clockStarts": "confirmed-non-draft-github-release",
                "targets": {
                    "claude": {
                        "publishedWithoutMetadata": "2.16.0",
                        "firstContainingRelease": "2.17.0",
                        "retainThrough": "2.x",
                        "earliestRemoval": "3.0.0",
                    },
                    "codex": {
                        "publishedWithoutMetadata": "0.8.0",
                        "firstContainingRelease": "0.9.0",
                        "retainThrough": "0.x",
                        "earliestRemoval": "1.0.0",
                    },
                    "pi": {
                        "publishedWithoutMetadata": "0.9.0",
                        "firstContainingRelease": "0.10.0",
                        "retainThrough": "0.x",
                        "earliestRemoval": "1.0.0",
                    },
                },
            },
        }
        self._write("core/surface/command-routes.json", registry)
        self._write("plugins/ca/.claude-plugin/plugin.json", {"version": "2.17.0"})
        self._write("plugins/ca-codex/.codex-plugin/plugin.json", {"version": "0.9.0"})
        self._write("plugins/ca-pi/package.json", {"version": "0.10.0"})
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "--quiet", "-m", "candidate"], cwd=self.repo, check=True)
        self.commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        for target, tag in (
            ("claude", "v2.17.0"),
            ("codex", "ca-codex-v0.9.0"),
            ("pi", "ca-pi-v0.10.0"),
        ):
            subprocess.run(["git", "tag", tag], cwd=self.repo, check=True)
            self._write_response(target, tag)

    def _write(self, relative: str, document: dict):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document) + "\n", encoding="utf-8")

    def _write_response(self, target: str, tag: str):
        release = {
            "draft": False,
            "tag_name": tag,
            "target_commitish": self.commit,
        }
        response = (
            "HTTP/2.0 200 OK\ncontent-type: application/json\n\n"
            + json.dumps(release)
            + "\n"
        )
        (self.evidence_dir / f"{target}.http").write_text(response, encoding="utf-8")
        (self.evidence_dir / f"{target}.exit").write_text("0\n", encoding="utf-8")

    def observe(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = RELEASE_STATE.main(
                [
                    "observe",
                    "--repo",
                    str(self.repo),
                    "--evidence-dir",
                    str(self.evidence_dir),
                ]
            )
        return code, output.getvalue()

    def test_exact_tags_payloads_and_release_responses_pass_end_to_end(self):
        code, output = self.observe()
        self.assertEqual(code, 0, output)
        self.assertEqual(output.count(": published"), 3)

    def test_tag_only_response_fails_the_aggregate_end_to_end(self):
        (self.evidence_dir / "claude.http").write_text(
            "HTTP/2.0 404 Not Found\ncontent-type: application/json\n\n{}\n",
            encoding="utf-8",
        )
        (self.evidence_dir / "claude.exit").write_text("1\n", encoding="utf-8")
        code, output = self.observe()
        self.assertEqual(code, 1)
        self.assertIn("claude: v2.17.0: tag-only", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)

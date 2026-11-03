#!/usr/bin/env python3
"""Contracts for immutable Arbiter Academy source promotion."""

from __future__ import annotations

import importlib.util
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO / ".github" / "scripts" / "academy_promotion.py"
WORKFLOW_PATH = REPO / ".github" / "workflows" / "academy-promotion.yml"
COMMIT = "54e8a42874664ee2f484dee433024f80b0aa128b"
TAG_OBJECT = "4638cce05b589a2f00eebe91e85b0d846339a4a1"


def load_module():
    spec = importlib.util.spec_from_file_location("academy_promotion", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("academy promotion module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def candidate_documents() -> tuple[dict, dict, dict, dict]:
    release = {
        "tag_name": "preview-0.33",
        "draft": False,
        "prerelease": False,
        "immutable": True,
    }
    ref = {"ref": "refs/tags/preview-0.33", "object": {"type": "tag", "sha": TAG_OBJECT}}
    tag = {"tag": "preview-0.33", "object": {"type": "commit", "sha": COMMIT}}
    manifest = {
        "release": "preview-0.33",
        "available_labs": ["F01-fork-clone-doctor", "P01-practice", "U01-operate"],
        "runnable_labs": ["F01-fork-clone-doctor", "P01-practice", "U01-operate"],
        "guided_labs": ["F01-fork-clone-doctor", "P01-practice", "U01-operate"],
    }
    return release, ref, tag, manifest


class CandidateIdentityTests(unittest.TestCase):
    def test_accepts_the_exact_preview_033_identity(self):
        module = load_module()
        candidate = module.validate_candidate(*candidate_documents(), current_release="preview-0.32")

        self.assertEqual(candidate.release, "preview-0.33")
        self.assertEqual(candidate.tag_object, TAG_OBJECT)
        self.assertEqual(candidate.commit, COMMIT)

    def test_rejects_every_mutable_or_inconsistent_identity(self):
        module = load_module()
        mutations = {
            "draft": lambda release, ref, tag, manifest: release.update(draft=True),
            "prerelease": lambda release, ref, tag, manifest: release.update(prerelease=True),
            "mutable release": lambda release, ref, tag, manifest: release.update(immutable=False),
            "wrong release tag": lambda release, ref, tag, manifest: release.update(tag_name="preview-0.34"),
            "lightweight tag": lambda release, ref, tag, manifest: ref["object"].update(type="commit"),
            "wrong ref": lambda release, ref, tag, manifest: ref.update(ref="refs/tags/preview-0.34"),
            "wrong annotated tag": lambda release, ref, tag, manifest: tag.update(tag="preview-0.34"),
            "non-commit target": lambda release, ref, tag, manifest: tag["object"].update(type="tree"),
            "invalid commit": lambda release, ref, tag, manifest: tag["object"].update(sha="not-a-sha"),
            "manifest mismatch": lambda release, ref, tag, manifest: manifest.update(release="preview-0.34"),
            "inventory mismatch": lambda release, ref, tag, manifest: manifest.update(runnable_labs=[]),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                documents = candidate_documents()
                mutate(*documents)
                with self.assertRaises(module.PromotionError):
                    module.validate_candidate(*documents, current_release="preview-0.32")

    def test_rejects_non_preview_and_non_advancing_versions(self):
        module = load_module()
        for release in ("v0.33", "preview-0.33.1", "preview-0.32", "preview-0.31"):
            with self.subTest(release=release):
                documents = list(candidate_documents())
                documents[0]["tag_name"] = release
                documents[1]["ref"] = f"refs/tags/{release}"
                documents[2]["tag"] = release
                documents[3]["release"] = release
                with self.assertRaises(module.PromotionError):
                    module.validate_candidate(*documents, current_release="preview-0.32")

    def test_read_only_watcher_can_confirm_the_consumer_is_current(self):
        module = load_module()

        candidate = module.validate_candidate(
            *candidate_documents(),
            current_release="preview-0.33",
            allow_current=True,
        )

        self.assertEqual(candidate.release, "preview-0.33")
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "outputs"
            module._write_outputs(output, candidate, "preview-0.33", up_to_date=True)
            self.assertIn("up_to_date=true\n", output.read_text(encoding="utf-8"))

    def test_current_watcher_rejects_an_exact_pin_contract_mismatch(self):
        module = load_module()
        candidate = module.validate_candidate(
            *candidate_documents(),
            current_release="preview-0.33",
            allow_current=True,
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            contract = root / "site" / "scripts" / "academy-source.test.ts"
            contract.parent.mkdir(parents=True)
            contract.write_text(
                'expect(source.commit).toBe("dcdc1b0ab023cd8f346e89d41a1bcb6f8a027acf");\n',
                encoding="utf-8",
            )
            with mock.patch.object(module, "_verify_submodule") as verify_submodule:
                with self.assertRaises(module.PromotionError):
                    module._verify_current_source(root, candidate)
                verify_submodule.assert_called_once_with(root, candidate.commit)

    def test_current_resolve_checks_exact_local_source_before_reporting(self):
        module = load_module()
        candidate = module.Candidate("preview-0.33", TAG_OBJECT, COMMIT)
        with mock.patch.object(module, "resolve_candidate", return_value=candidate), mock.patch.object(
            module, "_verify_current_source"
        ) as verify_current:
            result = module.main(["resolve", "--current-release", "preview-0.33"])

        self.assertEqual(result, 0)
        verify_current.assert_called_once_with(Path.cwd(), candidate)

    def test_apply_updates_only_the_declared_release_literal(self):
        module = load_module()
        candidate = module.validate_candidate(*candidate_documents(), current_release="preview-0.32")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "site" / "scripts" / "academy-source.ts"
            source.parent.mkdir(parents=True)
            source.write_text(
                'const RELEASE = "preview-0.32";\nconst unrelated = "preview-0.32";\n',
                encoding="utf-8",
            )
            contract = root / "site" / "scripts" / "academy-source.test.ts"
            contract.write_text(
                'const fixtureRelease = "preview-0.32";\n'
                'expect(source.release).toBe("preview-0.32");\n'
                'expect(source.commit).toBe("dcdc1b0ab023cd8f346e89d41a1bcb6f8a027acf");\n',
                encoding="utf-8",
            )

            changed = module.apply_candidate(root, candidate, expected_current="preview-0.32")

            self.assertEqual(changed, [
                Path("site/scripts/academy-source.ts"),
                Path("site/scripts/academy-source.test.ts"),
            ])
            self.assertEqual(
                source.read_text(encoding="utf-8"),
                'const RELEASE = "preview-0.33";\nconst unrelated = "preview-0.32";\n',
            )
            self.assertEqual(
                contract.read_text(encoding="utf-8"),
                f'const fixtureRelease = "preview-0.33";\n'
                f'expect(source.release).toBe("preview-0.33");\n'
                f'expect(source.commit).toBe("{COMMIT}");\n',
            )

    def test_apply_fails_closed_on_ambiguous_or_unexpected_source(self):
        module = load_module()
        candidate = module.validate_candidate(*candidate_documents(), current_release="preview-0.32")
        for text in (
            'const RELEASE = "preview-0.31";\n',
            'const RELEASE = "preview-0.32";\nconst RELEASE = "preview-0.32";\n',
        ):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                source = root / "site" / "scripts" / "academy-source.ts"
                source.parent.mkdir(parents=True)
                source.write_text(text, encoding="utf-8")
                (source.parent / "academy-source.test.ts").write_text(
                    'const fixtureRelease = "preview-0.32";\n'
                    'expect(source.release).toBe("preview-0.32");\n'
                    'expect(source.commit).toBe("dcdc1b0ab023cd8f346e89d41a1bcb6f8a027acf");\n',
                    encoding="utf-8",
                )
                with self.assertRaises(module.PromotionError):
                    module.apply_candidate(root, candidate, expected_current="preview-0.32")


class ResolverTransportTests(unittest.TestCase):
    def test_unrequested_candidate_selects_highest_published_preview_release(self):
        module = load_module()
        release, ref, tag, manifest = candidate_documents()
        content = {
            "encoding": "base64",
            "content": base64.b64encode(json.dumps(manifest).encode()).decode(),
        }
        releases = [
            {"tag_name": "v3.8.3", "draft": False, "prerelease": False, "immutable": True},
            {"tag_name": "preview-0.99", "draft": True, "prerelease": False, "immutable": True},
            {"tag_name": "preview-0.98", "draft": False, "prerelease": True, "immutable": True},
            {**release, "tag_name": "preview-0.32"},
            release,
        ]
        urls: list[str] = []

        def fetch(url: str):
            urls.append(url)
            if url == module._api_path("releases", query={"per_page": "100", "page": "1"}):
                return releases
            if "/git/ref/tags/" in url:
                return ref
            if "/git/tags/" in url:
                return tag
            if "/contents/academy/publication/" in url:
                return content
            raise AssertionError(f"unexpected URL: {url}")

        with mock.patch.object(module, "_read_json", side_effect=fetch):
            candidate = module.resolve_candidate(None, "preview-0.32")

        self.assertEqual(candidate.release, "preview-0.33")
        self.assertEqual(urls[0], module._api_path("releases", query={"per_page": "100", "page": "1"}))
        self.assertNotIn(module._api_path("releases/latest"), urls)

    def test_unrequested_candidate_fails_closed_on_malformed_or_truncated_inventory(self):
        module = load_module()
        with mock.patch.object(module, "_read_json", return_value={}):
            with self.assertRaisesRegex(module.PromotionError, "must be an array"):
                module.resolve_candidate(None, "preview-0.32")

        with mock.patch.object(module, "_read_json", return_value=[]):
            with self.assertRaisesRegex(module.PromotionError, "no published Preview Release"):
                module.resolve_candidate(None, "preview-0.32")

        full_non_preview_page = [
            {"tag_name": f"v1.0.{index}", "draft": False, "prerelease": False}
            for index in range(module.RELEASES_PER_PAGE)
        ]
        with mock.patch.object(module, "_read_json", return_value=full_non_preview_page) as read_json:
            with self.assertRaisesRegex(module.PromotionError, "bounded page limit"):
                module.resolve_candidate(None, "preview-0.32")
        self.assertEqual(read_json.call_count, module.MAX_RELEASE_PAGES)

    def test_unrequested_candidate_selects_the_highest_preview_across_pages(self):
        module = load_module()
        release, ref, tag, manifest = candidate_documents()
        lower = {**release, "tag_name": "preview-0.9"}
        higher = {**release, "tag_name": "preview-0.10"}
        ref = {**ref, "ref": "refs/tags/preview-0.10"}
        tag = {**tag, "tag": "preview-0.10"}
        manifest = {**manifest, "release": "preview-0.10"}
        first_page = [lower] + [
            {"tag_name": f"v1.0.{index}", "draft": False, "prerelease": False}
            for index in range(module.RELEASES_PER_PAGE - 1)
        ]
        second_page = [higher]
        content = {
            "encoding": "base64",
            "content": base64.b64encode(json.dumps(manifest).encode()).decode(),
        }
        first_url = module._api_path("releases", query={"per_page": "100", "page": "1"})
        second_url = module._api_path("releases", query={"per_page": "100", "page": "2"})
        urls: list[str] = []

        def fetch(url: str):
            urls.append(url)
            if url == first_url:
                return first_page
            if url == second_url:
                return second_page
            if "/git/ref/tags/" in url:
                return ref
            if "/git/tags/" in url:
                return tag
            if "/contents/academy/publication/" in url:
                return content
            raise AssertionError(f"unexpected URL: {url}")

        with mock.patch.object(module, "_read_json", side_effect=fetch):
            candidate = module.resolve_candidate(None, "preview-0.8")

        self.assertEqual(candidate.release, "preview-0.10")
        self.assertEqual(urls[:2], [first_url, second_url])

    def test_resolver_binds_manifest_read_to_the_peeled_commit(self):
        module = load_module()
        release, ref, tag, manifest = candidate_documents()
        content = {
            "encoding": "base64",
            "content": base64.b64encode(json.dumps(manifest).encode()).decode(),
        }
        urls: list[str] = []

        def fetch(url: str):
            urls.append(url)
            if "/releases/tags/" in url:
                return release
            if "/git/ref/tags/" in url:
                return ref
            if "/git/tags/" in url:
                return tag
            if "/contents/academy/publication/" in url:
                return content
            raise AssertionError(f"unexpected URL: {url}")

        with mock.patch.object(module, "_read_json", side_effect=fetch):
            candidate = module.resolve_candidate("preview-0.33", "preview-0.32")

        self.assertEqual(candidate.commit, COMMIT)
        self.assertEqual(len(urls), 4)
        self.assertEqual(urls[1], module._api_path("git/ref/tags/preview-0.33"))
        self.assertEqual(urls[2], module._api_path(f"git/tags/{TAG_OBJECT}"))
        manifest_url = urls[-1]
        self.assertIn("/academy/publication/preview-0.33.json", manifest_url)
        self.assertEqual(module.urllib.parse.parse_qs(module.urllib.parse.urlsplit(manifest_url).query), {"ref": [COMMIT]})

    def test_resolver_rejects_invalid_base64_manifest_content(self):
        module = load_module()
        release, ref, tag, _manifest = candidate_documents()
        responses = iter([release, ref, tag, {"encoding": "base64", "content": "%%%"}])
        with mock.patch.object(module, "_read_json", side_effect=lambda _url: next(responses)):
            with self.assertRaises(module.PromotionError):
                module.resolve_candidate("preview-0.33", "preview-0.32")

    def test_http_reader_rejects_redirect_oversize_and_invalid_json(self):
        module = load_module()

        class Response:
            def __init__(self, url: str, payload: bytes):
                self.url = url
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self):
                return self.url

            def read(self, _limit: int):
                return self.payload

        url = f"{module.API_ROOT}/releases/latest"
        cases = [
            Response(f"{url}/redirected", b"{}"),
            Response(url, b"x" * (module.MAX_RESPONSE_BYTES + 1)),
            Response(url, b"not-json"),
        ]
        for response in cases:
            with self.subTest(response=response), mock.patch.object(
                module.urllib.request, "urlopen", return_value=response
            ):
                with self.assertRaises(module.PromotionError):
                    module._read_json(url)


class WorkflowContractTests(unittest.TestCase):
    def test_schedule_and_dispatch_are_strictly_read_only(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        header = workflow.split("\njobs:\n", 1)[0]
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("schedule:", workflow)
        self.assertEqual(header.count("\npermissions:\n"), 1)
        self.assertEqual(header.split("\npermissions:\n", 1)[1].split("\n\n", 1)[0], "  contents: read")
        self.assertNotIn(": write", header)
        self.assertNotIn("pull_request_target", workflow)
        self.assertNotIn(": write", workflow)
        self.assertNotIn("GH_TOKEN:", workflow)
        self.assertNotIn("gh pr create", workflow)
        self.assertNotIn("gh pr merge", workflow)
        self.assertNotIn("actions/deploy-pages", workflow)

    def test_candidate_validation_is_bound_to_exact_git_identity(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        validate = workflow.split("\n  validate:\n", 1)[1]
        self.assertIn("academy_promotion.py resolve", validate)
        self.assertEqual(workflow.count('rev-parse "$ACADEMY_RELEASE^{tag}"'), 1)
        self.assertEqual(workflow.count('rev-parse "$ACADEMY_RELEASE^{commit}"'), 1)
        self.assertIn("npm run test:academy-source", validate)
        self.assertNotIn("contents: write", validate)
        self.assertNotIn("\n    permissions:", validate)
        self.assertNotIn("GH_TOKEN:", validate)
        self.assertIn("persist-credentials: false", workflow)

    def test_schedule_signals_only_after_successful_candidate_validation(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        signal = workflow.split("- name: Signal a scheduled promotion is pending", 1)[1]
        self.assertIn("github.event_name == 'schedule'", signal)
        self.assertIn("steps.candidate.outputs.up_to_date != 'true'", signal)
        self.assertIn("exit 1", signal)

    def test_default_branch_value_is_data_not_shell_source(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        trusted_branch = workflow.split("- name: Require trusted default-branch workflow code", 1)[1].split(
            "      - ", 1
        )[0]
        self.assertIn("DEFAULT_BRANCH: ${{ github.event.repository.default_branch }}", trusted_branch)
        self.assertIn('run: test "${GITHUB_REF}" = "refs/heads/${DEFAULT_BRANCH}"', trusted_branch)
        self.assertNotIn("${{ github.event.repository.default_branch }}", trusted_branch.split("run:", 1)[1])

    def test_ci_runs_the_workflow_contract_for_workflow_only_changes(self):
        ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        guarded = ".github/workflows/academy-promotion.yml"
        self.assertGreaterEqual(ci.count(guarded), 2)
        self.assertIn("python .github/scripts/test_academy_promotion.py", ci)


if __name__ == "__main__":
    unittest.main()

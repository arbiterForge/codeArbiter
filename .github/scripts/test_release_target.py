#!/usr/bin/env python3
"""Contracts for the per-target release planner (release_target.py)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("release_target", HERE / "release_target.py")
RT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RT)

SOURCE = "a" * 40
OTHER = "b" * 40
TAG_OBJECT = "c" * 40


def remote(tag: str, commit: str, annotated: bool = True) -> str:
    if annotated:
        return f"{TAG_OBJECT}\trefs/tags/{tag}\n{commit}\trefs/tags/{tag}^{{}}\n"
    return f"{commit}\trefs/tags/{tag}\n"


def release(tag: str, *, draft: bool, assets=(), rid: int = 7) -> dict:
    return {"id": rid, "tag_name": tag, "draft": draft,
            "assets": [{"name": name} for name in assets]}


class PlanTests(unittest.TestCase):
    def plan(self, remote_text="", pages=None, assets=("pkg.tgz",)):
        return RT.plan(tag="v1.2.3", source=SOURCE, remote_tag=remote_text,
                       pages=[pages or []], assets=list(assets))

    def test_fresh_release_creates_everything(self):
        self.assertEqual(self.plan(), {"tag": "create", "release": "create",
                                       "release-id": "", "missing-assets": "pkg.tgz"})

    def test_tag_at_source_with_draft_resumes_without_retagging(self):
        result = self.plan(remote("v1.2.3", SOURCE), [release("v1.2.3", draft=True)])
        self.assertEqual((result["tag"], result["release"], result["release-id"]),
                         ("present", "draft", "7"))

    def test_lightweight_tag_is_peeled_too(self):
        self.assertEqual(self.plan(remote("v1.2.3", SOURCE, annotated=False))["tag"], "present")

    def test_published_with_asset_needs_nothing(self):
        result = self.plan(remote("v1.2.3", SOURCE),
                           [release("v1.2.3", draft=False, assets=["pkg.tgz"])])
        self.assertEqual((result["release"], result["missing-assets"]), ("published", ""))

    def test_missing_asset_on_existing_release_is_reported(self):
        result = self.plan(remote("v1.2.3", SOURCE),
                           [release("v1.2.3", draft=True, assets=["other"])])
        self.assertEqual(result["missing-assets"], "pkg.tgz")

    def test_tag_at_a_different_commit_is_a_hard_conflict(self):
        with self.assertRaisesRegex(ValueError, "spent"):
            self.plan(remote("v1.2.3", OTHER))

    def test_duplicate_releases_are_refused(self):
        with self.assertRaisesRegex(ValueError, "2 Releases"):
            self.plan(pages=[release("v1.2.3", draft=True, rid=1),
                             release("v1.2.3", draft=False, rid=2)])

    def test_similarly_named_tags_do_not_match(self):
        result = self.plan(remote("v1.2.30", OTHER),
                           [release("v1.2.30", draft=False)])
        self.assertEqual((result["tag"], result["release"]), ("create", "create"))

    def test_short_source_is_refused(self):
        with self.assertRaisesRegex(ValueError, "full lowercase"):
            RT.plan(tag="v1", source="abc", remote_tag="", pages=[], assets=[])


class EligibleTests(unittest.TestCase):
    def test_first_release_of_a_series_is_eligible(self):
        self.assertTrue(RT.eligible("0.1.0", "ca-x-v", ["v2.0.0"], [[]]))

    def test_strict_advance_is_eligible(self):
        self.assertTrue(RT.eligible("2.0.1", "v", ["v2.0.0"], [[]]))

    def test_unchanged_published_version_is_not_eligible(self):
        pages = [[release("v2.0.0", draft=False)]]
        self.assertFalse(RT.eligible("2.0.0", "v", ["v2.0.0"], pages))

    def test_tagged_but_draft_release_is_eligible_to_finish(self):
        pages = [[release("v2.0.0", draft=True)]]
        self.assertTrue(RT.eligible("2.0.0", "v", ["v2.0.0"], pages))

    def test_tagged_without_any_release_is_eligible_to_finish(self):
        self.assertTrue(RT.eligible("2.0.0", "v", ["v2.0.0"], [[]]))

    def test_older_manifest_is_not_eligible(self):
        self.assertFalse(RT.eligible("1.9.0", "v", ["v2.0.0"], [[]]))


class CliTests(unittest.TestCase):
    def test_plan_cli_writes_outputs_and_conflict_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "remote").write_text(remote("v1.2.3", SOURCE), encoding="utf-8")
            (root / "releases").write_text(json.dumps([[release("v1.2.3", draft=True)]]),
                                           encoding="utf-8")
            output = root / "out"
            code = RT.main(["plan", "--tag", "v1.2.3", "--source", SOURCE,
                            "--remote-tag", str(root / "remote"), "--releases",
                            str(root / "releases"), "--asset", "pkg", "--output", str(output)])
            self.assertEqual(code, 0)
            self.assertIn("release=draft\n", output.read_text(encoding="utf-8"))
            (root / "remote").write_text(remote("v1.2.3", OTHER), encoding="utf-8")
            code = RT.main(["plan", "--tag", "v1.2.3", "--source", SOURCE,
                            "--remote-tag", str(root / "remote"), "--releases",
                            str(root / "releases")])
            self.assertEqual(code, 1)

    def test_receipt_records_the_observed_release_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "receipt.json"
            RT.main(["receipt", "--target", "ca", "--host", "claude", "--tag", "v1",
                     "--version", "1", "--source", SOURCE, "--package-file", "p",
                     "--package-sha256", "d", "--channel", "ca-marketplace",
                     "--channel-ref", OTHER, "--release-state", "published",
                     "--output", str(output)])
            receipt = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(receipt["release_state"], "published")
            self.assertEqual(receipt["channel_ref"], OTHER)


if __name__ == "__main__":
    unittest.main()

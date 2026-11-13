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
                                       "release-id": "", "missing-assets": "pkg.tgz",
                                       "complete": "false",
                                       "effects": "tag draft asset channel publish"})

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
        # Complete means public AND carrying its final receipt (C-F01): a
        # published Release with no receipt is not "unchanged and done".
        pages = [[release("v2.0.0", draft=False, assets=[RT.RECEIPT_ASSET])]]
        self.assertFalse(RT.eligible("2.0.0", "v", ["v2.0.0"], pages))

    def test_public_release_missing_its_receipt_is_eligible_for_recovery(self):
        # The exact C-F01 probe (audit-work/probe_release_recovery_results.json):
        # an exact tag + public Release + zero assets used to be ineligible
        # while plan() still listed the receipt as missing.
        pages = [[release("v2.0.0", draft=False, assets=[])]]
        self.assertTrue(RT.eligible("2.0.0", "v", ["v2.0.0"], pages))
        planned = RT.plan(tag="v2.0.0", source=SOURCE, remote_tag=remote("v2.0.0", SOURCE),
                          pages=pages, assets=[RT.RECEIPT_ASSET])
        self.assertEqual(planned["missing-assets"], RT.RECEIPT_ASSET)
        self.assertEqual(planned["effects"], "receipt")

    def test_malformed_release_listing_is_not_read_as_absent(self):
        # An unavailable/garbled API response must not become "create".
        for pages in ({"message": "API rate limit exceeded"}, [[{"tag_name": "v2.0.0"}]]):
            with self.subTest(pages=pages), self.assertRaises(ValueError):
                RT.eligible("2.0.0", "v", ["v2.0.0"], pages)

    def test_tagged_but_draft_release_is_eligible_to_finish(self):
        pages = [[release("v2.0.0", draft=True)]]
        self.assertTrue(RT.eligible("2.0.0", "v", ["v2.0.0"], pages))

    def test_tagged_without_any_release_is_eligible_to_finish(self):
        self.assertTrue(RT.eligible("2.0.0", "v", ["v2.0.0"], [[]]))

    def test_older_manifest_is_not_eligible(self):
        self.assertFalse(RT.eligible("1.9.0", "v", ["v2.0.0"], [[]]))


PKG = "codearbiter-ca-2.0.0.tar.gz"
PKG_SHA = "d" * 64
REQUIRED = [PKG, "codearbiter-publication.json"]


def asset(name: str, digest: str | None = None, state: str = "uploaded") -> dict:
    found = {"name": name, "state": state}
    if digest:
        found["digest"] = f"sha256:{digest}"
    return found


class CompletionModelTests(unittest.TestCase):
    """eligible() and plan() are projections of one observation (R-01)."""

    STATES = {
        "no tag, no release": (None, None),
        "tag only": (SOURCE, None),
        "draft, nothing attached": (SOURCE, {"draft": True, "assets": []}),
        "draft with package": (SOURCE, {"draft": True, "assets": [asset(PKG, PKG_SHA)]}),
        "public, package, no receipt": (SOURCE, {"draft": False, "assets": [asset(PKG, PKG_SHA)]}),
        "public, receipt, package deleted": (SOURCE, {"draft": False, "assets": [
            asset("codearbiter-publication.json")]}),
        "public and complete": (SOURCE, {"draft": False, "assets": [
            asset(PKG, PKG_SHA), asset("codearbiter-publication.json")]}),
    }
    EXPECTED_EFFECTS = {
        "no tag, no release": "tag draft asset channel publish receipt",
        "tag only": "draft asset channel publish receipt",
        "draft, nothing attached": "asset channel publish receipt",
        "draft with package": "asset channel publish receipt",
        "public, package, no receipt": "receipt",
        "public, receipt, package deleted": "asset",
        "public and complete": "",
    }

    def fixture(self, name):
        tagged, found = self.STATES[name]
        listing = remote("v2.0.0", tagged) if tagged else ""
        pages = [[{"id": 7, "tag_name": "v2.0.0", **found}]] if found else [[]]
        return listing, pages

    def test_eligible_and_plan_agree_for_every_publication_state(self):
        for name in self.STATES:
            with self.subTest(state=name):
                listing, pages = self.fixture(name)
                planned = RT.plan(tag="v2.0.0", source=SOURCE, remote_tag=listing,
                                  pages=pages, assets=REQUIRED, digests={PKG: PKG_SHA})
                self.assertEqual(planned["effects"], self.EXPECTED_EFFECTS[name])
                go = RT.eligible("2.0.0", "v", [], pages, refs=RT.tag_refs(listing),
                                 source=SOURCE, assets=REQUIRED)
                if listing:
                    self.assertEqual(go, planned["effects"] != "", name)
                    self.assertEqual(planned["complete"] == "true", not go, name)
                else:
                    # No tag yet: a strict advance is the new-release path.
                    self.assertTrue(go)

    def test_another_sources_finished_version_is_a_no_op(self):
        listing, pages = self.fixture("public and complete")
        listing = listing.replace(SOURCE, OTHER)
        self.assertFalse(RT.eligible("2.0.0", "v", [], pages, refs=RT.tag_refs(listing),
                                     source=SOURCE, assets=REQUIRED))

    def test_another_sources_unfinished_version_is_refused_with_its_owner(self):
        listing, pages = self.fixture("public, package, no receipt")
        listing = listing.replace(SOURCE, OTHER)
        with self.assertRaisesRegex(RT.Conflict, OTHER):
            RT.eligible("2.0.0", "v", [], pages, refs=RT.tag_refs(listing),
                        source=SOURCE, assets=REQUIRED)
        with self.assertRaisesRegex(ValueError, "spent"):
            RT.plan(tag="v2.0.0", source=SOURCE, remote_tag=listing, pages=pages,
                    assets=REQUIRED)

    def test_conflicting_or_interrupted_assets_are_never_papered_over(self):
        listing, _ = self.fixture("tag only")
        cases = {
            "wrong digest": [asset(PKG, "e" * 64)],
            "interrupted upload": [asset(PKG, state="open")],
            "duplicate name": [asset(PKG, PKG_SHA), asset(PKG, PKG_SHA)],
        }
        for case, assets in cases.items():
            pages = [[{"id": 7, "tag_name": "v2.0.0", "draft": False, "assets": assets}]]
            with self.subTest(case=case):
                with self.assertRaises(RT.Conflict):
                    RT.plan(tag="v2.0.0", source=SOURCE, remote_tag=listing, pages=pages,
                            assets=REQUIRED, digests={PKG: PKG_SHA})

    def test_public_release_without_its_tag_is_an_inconsistent_observation(self):
        _, pages = self.fixture("public and complete")
        with self.assertRaisesRegex(RT.Conflict, "re-observe"):
            RT.plan(tag="v2.0.0", source=SOURCE, remote_tag="", pages=pages, assets=REQUIRED)

    def test_malformed_tag_listing_is_refused(self):
        with self.assertRaisesRegex(ValueError, "malformed object id"):
            RT.tag_refs("not-a-sha\trefs/tags/v2.0.0\n")

    def test_hostless_target_needs_only_tag_release_and_receipt(self):
        self.assertEqual(RT.required_assets("ca-sandbox", "0.1.0"), [RT.RECEIPT_ASSET])
        planned = RT.plan(tag="ca-sandbox-v0.1.0", source=SOURCE, remote_tag="",
                          pages=[[]], assets=RT.required_assets("ca-sandbox", "0.1.0"))
        self.assertEqual(planned["effects"], "tag draft publish receipt")

    def test_package_asset_names_mirror_the_ci_package_owner(self):
        builder = (HERE.parents[1] / "tools" / "build-host-packages.py").read_text(encoding="utf-8")
        for host, pattern in RT.PACKAGE_ASSET.items():
            shipped = '"%s": f"%s"' % (host, pattern.replace("{version}", "{versions['%s']}" % host))
            self.assertIn(shipped, builder, host)
        self.assertEqual(RT.required_assets("ca-pi", "0.27.5"),
                         ["arbiterforge-ca-pi-0.27.5.tgz", RT.RECEIPT_ASSET])

    def test_plan_cli_refuses_a_cohort_file_that_is_not_the_declared_asset(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "remote").write_text("", encoding="utf-8")
            (root / "releases").write_text("[[]]", encoding="utf-8")
            base = ["plan", "--tag", "v2.0.0", "--source", SOURCE, "--remote-tag",
                    str(root / "remote"), "--releases", str(root / "releases"),
                    "--target", "ca", "--version", "2.0.0", "--package-sha256", PKG_SHA]
            self.assertEqual(RT.main(base + ["--package-file", "other.tar.gz"]), 1)
            self.assertEqual(RT.main(base + ["--package-file", PKG]), 0)


class ReceiptReadbackTests(unittest.TestCase):
    EXPECTED = {"target": "ca", "host": "claude", "tag": "v2.0.0", "version": "2.0.0",
                "source_commit": SOURCE, "package_file": PKG, "package_sha256": PKG_SHA,
                "channel": "ca-marketplace", "channel_ref": OTHER}

    def receipt(self, **changes):
        return {"format": RT.RECEIPT_FORMAT, "release_state": "published",
                **self.EXPECTED, **changes}

    def test_matching_attached_receipt_is_accepted(self):
        RT.verify_receipt(self.receipt(), self.EXPECTED)

    def test_same_named_receipt_with_other_content_is_refused(self):
        for changes in ({"source_commit": OTHER}, {"package_sha256": "e" * 64},
                        {"format": "x"}, {"release_state": "draft"}, {"tag": "v2.0.1"}):
            with self.subTest(changes=changes), self.assertRaises(RT.Conflict):
                RT.verify_receipt(self.receipt(**changes), self.EXPECTED)


ACTION = HERE.parents[1] / ".github" / "actions" / "publish-target" / "action.yml"
NPM_SPEC = importlib.util.spec_from_file_location("npm_publishlib", HERE / "_npm_publishlib.py")
NPM = importlib.util.module_from_spec(NPM_SPEC)
NPM_SPEC.loader.exec_module(NPM)
INTEGRITY = "sha512-" + "A" * 86 + "=="


class Crash(Exception):
    """The job died after an effect landed (or its response was lost)."""


class FakeRemote:
    """Remote publication state: tags, Releases/assets, channel and npm."""

    def __init__(self, host: str | None):
        self.host = host
        self.tags: dict[str, str] = {}
        self.releases: list[dict] = []
        self.channel: list[tuple[str, str, str]] = []  # (commit, dist, version)
        self.npm: dict[str, str] = {}
        self.landed: dict[str, int] = {}

    def land(self, effect: str) -> None:
        self.landed[effect] = self.landed.get(effect, 0) + 1

    def listing(self) -> str:
        return "".join(f"{sha}\trefs/tags/{tag}\n" for tag, sha in self.tags.items())

    def pages(self) -> list:
        return [[json.loads(json.dumps(found)) for found in self.releases]]

    def registry_lookup(self, version: str):
        if version not in self.npm:
            body = json.dumps({"error": {"code": "E404"}})
            return 1, body, "npm error code E404"
        url = f"https://registry.npmjs.org/-/npm/v1/attestations/@arbiterforge%2fca-pi@{version}"
        return 0, json.dumps({"version": version, "dist": {
            "integrity": self.npm[version], "attestations": {
                "url": url,
                "provenance": {"predicateType": NPM.PROVENANCE_PREDICATE}}}}), ""


class PublicationRun:
    """Drive one release job through the composite's effect order.

    Each step mirrors the shipped action.yml gate (pinned by
    CompositionContractTests): observe-then-act, with a readback after every
    effect. `crash_after` kills the job right after that effect lands.
    """

    PHASES = ("tag", "draft", "asset", "channel", "publish", "receipt")

    def __init__(self, remote: FakeRemote, target: str, version: str, *, source=SOURCE,
                 package_sha=PKG_SHA, workflow_sha=SOURCE):
        self.remote, self.target, self.version = remote, target, version
        self.source, self.package_sha, self.workflow_sha = source, package_sha, workflow_sha
        self.prefix = {"ca": "v", "ca-codex": "ca-codex-v", "ca-pi": "ca-pi-v",
                       "ca-sandbox": "ca-sandbox-v"}[target]
        self.tag = self.prefix + version
        self.host = RT.TARGET_HOSTS[target]
        self.assets = RT.required_assets(target, version)
        self.package = self.assets[0] if self.host else None

    def eligible(self) -> bool:
        return RT.eligible(self.version, self.prefix, [], self.remote.pages(),
                           refs=RT.tag_refs(self.remote.listing()), source=self.source,
                           assets=self.assets)

    def run(self, crash_after: str | None = None) -> dict | None:
        remote = self.remote
        if not self.eligible():
            return None
        digests = {self.package: self.package_sha} if self.package else {}
        planned = RT.plan(tag=self.tag, source=self.source, remote_tag=remote.listing(),
                          pages=remote.pages(), assets=self.assets, digests=digests)
        effects = planned["effects"].split()
        missing = planned["missing-assets"].split()

        def landed(effect):
            remote.land(effect)
            if crash_after == effect:
                raise Crash(effect)

        if planned["tag"] == "create":
            remote.tags[self.tag] = self.source
            landed("tag")
        if remote.tags.get(self.tag) != self.source:
            raise AssertionError("tag readback differs")
        if planned["release"] == "create":
            remote.releases.append({"id": 7, "tag_name": self.tag, "draft": True, "assets": []})
            landed("draft")
        found = next(r for r in remote.releases if r["tag_name"] == self.tag)
        if self.host:
            if self.package in missing:
                found["assets"].append(asset(self.package, self.package_sha))
                landed("asset")
            digest = next(a.get("digest") for a in found["assets"] if a["name"] == self.package)
            if digest != f"sha256:{self.package_sha}":
                raise AssertionError("package asset readback differs")
        channel_ref = "none"
        dist = f"dist-{self.target}-{self.version}-{self.package_sha[:8]}"
        if self.host in ("claude", "codex"):
            carried = [c for c, d, _ in remote.channel if d == dist]
            if "channel" in effects:
                if not carried:
                    head = remote.channel[-1][2] if remote.channel else None
                    if head and RT._releaselib.semver_greater(head, self.version):
                        raise ValueError("marketplace channel cannot roll back")
                    remote.channel.append((f"c{len(remote.channel)}", dist, self.version))
                    landed("channel")
            elif not carried:
                raise ValueError("channel readback: never promoted")
            channel_ref = [c for c, d, _ in remote.channel if d == dist][-1]
        if self.host == "pi":
            state = NPM.classify_registry_lookup(*remote.registry_lookup(self.version),
                                                 self.version, INTEGRITY)
            if state != "present" and "channel" in effects:
                if self.workflow_sha != self.source:
                    raise ValueError("npm provenance workflow commit differs; refusing publish")
                remote.npm[self.version] = INTEGRITY
                landed("channel")
            if NPM.classify_registry_lookup(*remote.registry_lookup(self.version),
                                            self.version, INTEGRITY) != "present":
                raise ValueError("npm publication not observable with expected integrity")
        if found["draft"]:
            found["draft"] = False
            landed("publish")
        receipt = {"format": RT.RECEIPT_FORMAT, "target": self.target,
                   "host": self.host or "none", "tag": self.tag, "version": self.version,
                   "source_commit": self.source, "package_file": self.package or "none",
                   "package_sha256": self.package_sha if self.package else "none",
                   "channel": RT.channel_name(self.host or "", self.version),
                   "channel_ref": channel_ref, "release_state": "published"}
        if RT.RECEIPT_ASSET in missing:
            found["assets"].append(asset(RT.RECEIPT_ASSET))
            found["receipt"] = receipt
            landed("receipt")
        RT.verify_receipt(found["receipt"], {k: v for k, v in receipt.items()
                                             if k not in ("format", "release_state")})
        return planned


class FaultInjectionTests(unittest.TestCase):
    TARGETS = {"ca": "2.0.0", "ca-codex": "0.20.0", "ca-pi": "0.27.0", "ca-sandbox": "0.1.0"}

    def converge(self, run, crash_after):
        with self.assertRaises(Crash):
            run.run(crash_after=crash_after)
        before = dict(run.remote.landed)
        if crash_after == "receipt":
            # The receipt landed but its response was lost: the observation
            # is already complete, so the rerun performs nothing at all.
            self.assertFalse(run.eligible())
            self.assertIsNone(run.run())
            return before, None
        self.assertTrue(run.eligible(), f"{crash_after}: interrupted publication not eligible")
        resumed = run.run()
        self.assertIsNotNone(resumed)
        self.assertFalse(run.eligible(), "complete publication must be a no-op")
        self.assertIsNone(run.run(), "a third run must perform nothing")
        return before, resumed

    def test_every_phase_interruption_resumes_only_missing_effects(self):
        for target, version in self.TARGETS.items():
            for phase in PublicationRun.PHASES:
                host = RT.TARGET_HOSTS[target]
                if not host and phase in ("asset", "channel"):
                    continue
                with self.subTest(target=target, crash_after=phase):
                    remote = FakeRemote(host)
                    run = PublicationRun(remote, target, version, package_sha=PKG_SHA)
                    self.converge(run, phase)
                    # Every effect landed exactly once across both runs: no
                    # retag, re-upload, re-promotion, npm republish or second
                    # public transition.
                    for effect, count in remote.landed.items():
                        self.assertEqual(count, 1, (target, phase, effect))
                    expected = set(PublicationRun.PHASES) - (
                        set() if host else {"asset", "channel"})
                    self.assertEqual(set(remote.landed), expected)

    def test_receipt_failure_after_public_schedules_only_the_receipt(self):
        for target, version in self.TARGETS.items():
            with self.subTest(target=target):
                remote = FakeRemote(RT.TARGET_HOSTS[target])
                run = PublicationRun(remote, target, version)
                _, resumed = self.converge(run, "publish")
                self.assertEqual(resumed["effects"], "receipt")
                self.assertEqual((resumed["tag"], resumed["release"]), ("present", "published"))

    def test_receipt_recovery_survives_a_channel_that_moved_on(self):
        # A later release advanced the marketplace before the receipt was
        # recovered: re-promoting would be a refused rollback, so recovery
        # must read the channel back rather than repeat the promotion.
        for target, newer in (("ca", "2.1.0"), ("ca-codex", "0.21.0")):
            with self.subTest(target=target):
                remote = FakeRemote(RT.TARGET_HOSTS[target])
                run = PublicationRun(remote, target, self.TARGETS[target])
                with self.assertRaises(Crash):
                    run.run(crash_after="publish")
                remote.channel.append(("c-newer", f"dist-{target}-{newer}", newer))
                resumed = run.run()
                self.assertEqual(resumed["effects"], "receipt")
                self.assertEqual(remote.landed["channel"], 1)

    def test_moved_tag_after_interruption_is_refused_not_completed(self):
        remote = FakeRemote("claude")
        run = PublicationRun(remote, "ca", "2.0.0")
        with self.assertRaises(Crash):
            run.run(crash_after="draft")
        remote.tags["v2.0.0"] = OTHER
        with self.assertRaisesRegex(RT.Conflict, OTHER):
            run.run()
        self.assertNotIn("publish", remote.landed)

    def test_wrong_package_bytes_on_rerun_are_refused(self):
        remote = FakeRemote("claude")
        with self.assertRaises(Crash):
            PublicationRun(remote, "ca", "2.0.0").run(crash_after="asset")
        rebuilt = PublicationRun(remote, "ca", "2.0.0", package_sha="e" * 64)
        with self.assertRaisesRegex(RT.Conflict, "never replaced"):
            rebuilt.run()
        self.assertNotIn("publish", remote.landed)

    def test_registry_mismatch_is_not_completed(self):
        remote = FakeRemote("pi")
        run = PublicationRun(remote, "ca-pi", "0.27.0")
        with self.assertRaises(Crash):
            run.run(crash_after="asset")
        remote.npm["0.27.0"] = "sha512-" + "B" * 86 + "=="
        with self.assertRaisesRegex(ValueError, "integrity does not match"):
            run.run()
        self.assertNotIn("publish", remote.landed)

    def test_public_pi_release_never_republishes_npm(self):
        # Public Release, npm version gone (unpublished out of band): the
        # receipt-only plan must fail readback, not run a fresh npm publish.
        remote = FakeRemote("pi")
        run = PublicationRun(remote, "ca-pi", "0.27.0")
        with self.assertRaises(Crash):
            run.run(crash_after="publish")
        del remote.npm["0.27.0"]
        with self.assertRaisesRegex(ValueError, "not observable"):
            run.run()
        self.assertEqual(remote.landed["channel"], 1)

    def test_pi_new_publish_still_requires_matching_workflow_commit(self):
        remote = FakeRemote("pi")
        run = PublicationRun(remote, "ca-pi", "0.27.0", workflow_sha=OTHER)
        with self.assertRaisesRegex(ValueError, "provenance"):
            run.run()
        self.assertNotIn("channel", remote.landed)


class CompositionContractTests(unittest.TestCase):
    """Pin the simulator's step gates to the shipped composite action."""

    def step(self, name):
        text = ACTION.read_text(encoding="utf-8")
        steps = [s for s in text.split("\n    - name: ")[1:] if s.startswith(name)]
        self.assertEqual(len(steps), 1, name)
        return steps[0]

    def test_effect_steps_run_in_the_simulated_order(self):
        text = ACTION.read_text(encoding="utf-8")
        order = ["Create and push the annotated tag", "Create the draft Release",
                 "Upload and read back the package asset", "Publish the Claude marketplace channel",
                 "Publish the Codex marketplace channel", "Publish @arbiterforge/ca-pi to npm",
                 "Read back the npm publication", "Publish the Release",
                 "Attach the publication receipt"]
        positions = [text.index(f"- name: {name}") for name in order]
        self.assertEqual(positions, sorted(positions))

    def test_plan_receives_the_declared_assets_and_verified_digest(self):
        plan = self.step("Observe remote state and plan")
        for flag in ('--target "$TARGET"', '--version "$VERSION"', '--package-file "$ASSET"',
                     '--package-sha256 "$ASSET_SHA256"'):
            self.assertIn(flag, plan)
        self.assertNotIn("--asset codearbiter-publication.json", plan)

    def test_channel_steps_promote_only_when_the_plan_schedules_it(self):
        for name in ("Publish the Claude marketplace channel", "Publish the Codex marketplace channel"):
            body = self.step(name)
            self.assertIn("EFFECTS: ${{ steps.plan.outputs.effects }}", body)
            self.assertIn('case " $EFFECTS " in', body)
            self.assertIn("--readback", body)
        npm = self.step("Publish @arbiterforge/ca-pi to npm")
        self.assertIn("contains(steps.plan.outputs.effects, 'channel')", npm)

    def test_existing_receipt_is_read_back_and_verified(self):
        body = self.step("Attach the publication receipt")
        self.assertNotIn('echo "receipt already attached"; exit 0', body)
        self.assertIn("release_target.py verify-receipt", body)
        self.assertIn('-H "Accept: application/octet-stream"', body)


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

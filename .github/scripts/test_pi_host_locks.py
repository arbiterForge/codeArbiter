#!/usr/bin/env python3
"""Regression tests for reviewed, repository-owned Pi host dependency graphs."""
from __future__ import annotations

import importlib.util
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace


REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / ".github" / "scripts" / "pi_host_locks.py"
LOCK_ROOT = REPO / ".github" / "fixtures" / "pi-hosts"
SUPPORTED_VERSION = "0.84.1"


def load_helper():
    # This assertion is deliberately the first RED boundary: exact main has no
    # repository-owned verifier/installer for the graph it executes in CI.
    if not HELPER.is_file():
        raise AssertionError("reviewed Pi host-lock verifier is missing")
    spec = importlib.util.spec_from_file_location("pi_host_locks_contract", HELPER)
    if spec is None or spec.loader is None:
        raise AssertionError("reviewed Pi host-lock verifier is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PiHostLocksTest(unittest.TestCase):
    def test_reviewed_fixture_bytes_are_forced_to_lf_on_every_checkout(self):
        fixtures = (
            ".github/fixtures/pi-hosts/0.84.1/package-lock.json",
            ".github/fixtures/pi-hosts/0.84.1/.npmrc",
        )
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                completed = subprocess.run(
                    ["git", "check-attr", "text", "eol", "--", fixture],
                    cwd=REPO,
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                self.assertEqual(
                    completed.stdout.splitlines(),
                    [f"{fixture}: text: set", f"{fixture}: eol: lf"],
                )

    def test_only_current_supported_pi_has_a_committed_exact_lock(self):
        manifest_path = LOCK_ROOT / SUPPORTED_VERSION / "package.json"
        lock_path = LOCK_ROOT / SUPPORTED_VERSION / "package-lock.json"
        self.assertTrue(manifest_path.is_file(), "reviewed 0.84.1 manifest is missing")
        self.assertTrue(lock_path.is_file(), "reviewed 0.84.1 lock is missing")
        self.assertFalse((LOCK_ROOT / "0.80.5").exists(), "retired Pi must not have a current host lock")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        expected = {"@earendil-works/pi-coding-agent": SUPPORTED_VERSION}
        self.assertIs(manifest.get("private"), True)
        self.assertEqual(manifest.get("dependencies"), expected)
        self.assertEqual(lock.get("lockfileVersion"), 3)
        self.assertEqual(lock["packages"][""]["dependencies"], expected)

    def test_validator_accepts_reviewed_bytes_and_rejects_graph_mutation(self):
        helper = load_helper()
        validated = helper.validate_host_lock(REPO, SUPPORTED_VERSION)
        self.assertEqual(validated["version"], SUPPORTED_VERSION)
        self.assertEqual(validated["package"], "@earendil-works/pi-coding-agent")

        mutations = {
            "integrity": lambda lock: next(
                value for key, value in lock["packages"].items()
                if key and isinstance(value, dict) and "integrity" in value
            ).__setitem__("integrity", "sha512-intentional-mutation"),
            "registry": lambda lock: lock["packages"]["node_modules/@earendil-works/pi-coding-agent"].__setitem__(
                "resolved", "https://example.invalid/pi.tgz",
            ),
            "version": lambda lock: lock["packages"]["" ]["dependencies"].__setitem__(
                "@earendil-works/pi-coding-agent", "0.84.2",
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory(prefix="ca-pi-host-lock-") as raw:
                root = Path(raw)
                shutil.copytree(LOCK_ROOT, root / ".github" / "fixtures" / "pi-hosts")
                lock_path = root / ".github" / "fixtures" / "pi-hosts" / SUPPORTED_VERSION / "package-lock.json"
                lock = json.loads(lock_path.read_text(encoding="utf-8"))
                mutate(lock)
                lock_path.write_text(json.dumps(lock), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "digest|integrity|registry|version|reviewed"):
                    helper.validate_host_lock(root, SUPPORTED_VERSION)

    def test_validator_rejects_npmrc_mutation(self):
        helper = load_helper()
        with tempfile.TemporaryDirectory(prefix="ca-pi-config-") as raw:
            root = Path(raw)
            target = root / ".github" / "fixtures" / "pi-hosts" / SUPPORTED_VERSION
            shutil.copytree(LOCK_ROOT / SUPPORTED_VERSION, target)
            (target / ".npmrc").write_text(
                "registry=https://registry.npmjs.org/\nignore-scripts=false\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "config|npmrc|digest|reviewed"):
                helper.validate_host_lock(root, SUPPORTED_VERSION)

    def test_validator_rejects_every_non_registry_package_shape(self):
        helper = load_helper()
        review_source = LOCK_ROOT / SUPPORTED_VERSION / "review.json"
        review = json.loads(review_source.read_text(encoding="utf-8"))
        package_key = next(
            key for key, value in json.loads(
                (LOCK_ROOT / SUPPORTED_VERSION / "package-lock.json").read_text(encoding="utf-8")
            )["packages"].items()
            if key != f"node_modules/{helper.PACKAGE}" and isinstance(value, dict)
            and value.get("resolved") and value.get("integrity")
        )
        mutations = {
            "link": lambda value: (value.__setitem__("link", True), value.pop("resolved"), value.pop("integrity")),
            "file": lambda value: value.__setitem__("resolved", "file:../package.tgz"),
            "git": lambda value: value.__setitem__("resolved", "git+https://github.com/example/package.git"),
            "alternate-host": lambda value: value.__setitem__("resolved", "https://example.invalid/package.tgz"),
            "userinfo": lambda value: value.__setitem__("resolved", "https://user@registry.npmjs.org/package.tgz"),
            "query": lambda value: value.__setitem__("resolved", "https://registry.npmjs.org/package.tgz?token=value"),
            "fragment": lambda value: value.__setitem__("resolved", "https://registry.npmjs.org/package.tgz#fragment"),
            "missing-integrity": lambda value: value.pop("integrity"),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory(prefix="ca-pi-source-") as raw:
                root = Path(raw)
                target = root / ".github" / "fixtures" / "pi-hosts" / SUPPORTED_VERSION
                shutil.copytree(LOCK_ROOT / SUPPORTED_VERSION, target)
                lock_path = target / "package-lock.json"
                lock = json.loads(lock_path.read_text(encoding="utf-8"))
                mutate(lock["packages"][package_key])
                lock_path.write_text(json.dumps(lock), encoding="utf-8")
                candidate_review = json.loads(json.dumps(review))
                candidate_review["lock_sha256"] = helper.hashlib.sha256(lock_path.read_bytes()).hexdigest()
                (target / "review.json").write_text(json.dumps(candidate_review), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "link|registry|integrity|source"):
                    helper.validate_host_lock(root, SUPPORTED_VERSION)

    def test_validator_rejects_unsafe_or_unresolved_nested_dependency_edges(self):
        helper = load_helper()
        cases = {
            "git": ("dependencies", "git+https://example.invalid/x.git"),
            "file": ("dependencies", "file:../x"),
            "http": ("optionalDependencies", "https://example.invalid/x.tgz"),
            "workspace": ("peerDependencies", "workspace:*"),
            "link": ("dependencies", "link:../x"),
            "unsafe-alias": ("dependencies", "npm:alias@git+https://example.invalid/x.git"),
            "missing-locked-target": ("dependencies", "1.2.3"),
        }
        for label, (field, specification) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory(prefix="ca-pi-edge-") as raw:
                root = Path(raw)
                target = root / ".github" / "fixtures" / "pi-hosts" / SUPPORTED_VERSION
                shutil.copytree(LOCK_ROOT / SUPPORTED_VERSION, target)
                lock_path = target / "package-lock.json"
                lock = json.loads(lock_path.read_text(encoding="utf-8"))
                agent = lock["packages"][f"node_modules/{helper.PACKAGE}"]
                agent.setdefault(field, {})["missing-edge"] = specification
                lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
                review_path = target / "review.json"
                review = json.loads(review_path.read_text(encoding="utf-8"))
                review["lock_sha256"] = hashlib.sha256(lock_path.read_bytes()).hexdigest()
                review_path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "dependency|registry|locked"):
                    helper.validate_host_lock(root, SUPPORTED_VERSION)

    def test_registry_aliases_are_name_validated_and_identity_bound(self):
        helper = load_helper()
        packages = {
            "": {"dependencies": {"alias": "npm:@scope/real@1.0.0"}},
            "node_modules/alias": {"name": "@scope/real", "version": "1.0.0"},
        }
        helper._validate_locked_dependency_edges(packages)
        for specification in (
            "npm:@scope/../../evil@1.0.0",
            "npm:https://evil.invalid/package@1.0.0",
            "npm:@scope@1.0.0",
        ):
            with self.subTest(specification=specification), self.assertRaisesRegex(
                ValueError, "alias|registry|package",
            ):
                helper._registry_dependency(specification)
        packages["node_modules/alias"]["name"] = "@scope/wrong"
        with self.assertRaisesRegex(ValueError, "alias.*identity"):
            helper._validate_locked_dependency_edges(packages)

    def test_install_plan_is_isolated_frozen_and_disables_scripts(self):
        helper = load_helper()
        with tempfile.TemporaryDirectory(prefix="ca-pi-prefix-") as raw:
            plan = helper.install_plan(REPO, SUPPORTED_VERSION, Path(raw))
        self.assertIn(Path(plan["command"][0]).name.lower(), {"npm", "npm.cmd"})
        self.assertEqual(plan["command"][1], "ci")
        self.assertIn("--ignore-scripts", plan["command"])
        self.assertIn("--registry=https://registry.npmjs.org", plan["command"])
        self.assertIn("--@earendil-works:registry=https://registry.npmjs.org", plan["command"])
        self.assertIn("--cache", plan["command"])
        self.assertNotIn("--global", plan["command"])
        self.assertEqual(Path(plan["cwd"]), LOCK_ROOT / SUPPORTED_VERSION)
        self.assertIn("node_modules/.bin", plan["path_entry"].replace("\\", "/"))

    def test_npm_environment_discards_ambient_config_and_credentials(self):
        helper = load_helper()
        with tempfile.TemporaryDirectory(prefix="ca-pi-npm-env-") as raw:
            destination = Path(raw)
            ambient = {
                "PATH": os.environ.get("PATH", ""),
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
                "NPM_CONFIG_REGISTRY": "https://attacker.invalid",
                "npm_config_userconfig": "attacker.npmrc",
                "NODE_AUTH_TOKEN": "secret",
                "NPM_TOKEN": "secret",
                "NPMJS_TOKEN": "publish-secret",
                "GH_TOKEN": "repository-write-secret",
                "GITHUB_TOKEN": "repository-write-secret",
                "FARM_API_KEY": "farm-secret",
                "CLAUDE_CODE_OAUTH_TOKEN": "oauth-secret",
                "AWS_SECRET_ACCESS_KEY": "cloud-secret",
                "UNRECOGNIZED_PROVIDER_CREDENTIAL": "unknown-secret",
                "GIT_ASKPASS": "credential-helper",
                "SSH_AUTH_SOCK": "agent-socket",
                "ACTIONS_RUNTIME_TOKEN": "runtime-secret",
                "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "oidc-secret",
            }
            clean = helper._npm_environment(destination, ambient)
            self.assertEqual(clean["PATH"], ambient["PATH"])
            self.assertNotEqual(clean.get("NPM_CONFIG_REGISTRY"), ambient["NPM_CONFIG_REGISTRY"])
            self.assertNotIn("NODE_AUTH_TOKEN", clean)
            self.assertNotIn("NPM_TOKEN", clean)
            self.assertNotIn("NPMJS_TOKEN", clean)
            self.assertNotIn("GH_TOKEN", clean)
            self.assertNotIn("GITHUB_TOKEN", clean)
            self.assertNotIn("FARM_API_KEY", clean)
            self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", clean)
            self.assertNotIn("AWS_SECRET_ACCESS_KEY", clean)
            self.assertNotIn("UNRECOGNIZED_PROVIDER_CREDENTIAL", clean)
            self.assertNotIn("GIT_ASKPASS", clean)
            self.assertNotIn("SSH_AUTH_SOCK", clean)
            self.assertNotIn("ACTIONS_RUNTIME_TOKEN", clean)
            self.assertNotIn("ACTIONS_ID_TOKEN_REQUEST_TOKEN", clean)
            self.assertEqual(Path(clean["NPM_CONFIG_CACHE"]), destination / ".npm-cache")
            self.assertEqual(Path(clean["NPM_CONFIG_USERCONFIG"]), destination / ".npm-config" / "user.npmrc")
            self.assertEqual(Path(clean["NPM_CONFIG_GLOBALCONFIG"]), destination / ".npm-config" / "global.npmrc")
            self.assertTrue(Path(clean["NPM_CONFIG_USERCONFIG"]).is_file())
            self.assertTrue(Path(clean["NPM_CONFIG_GLOBALCONFIG"]).is_file())

    def test_pending_review_graph_cannot_become_supported_evidence(self):
        helper = load_helper()
        with tempfile.TemporaryDirectory(prefix="ca-pi-pending-review-") as raw:
            root = Path(raw)
            target = root / ".github" / "fixtures" / "pi-hosts" / SUPPORTED_VERSION
            shutil.copytree(LOCK_ROOT / SUPPORTED_VERSION, target)
            review_path = target / "review.json"
            review = json.loads(review_path.read_text(encoding="utf-8"))
            review["result"] = "PENDING_REVIEW"
            review_path.write_text(json.dumps(review), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "pending dependency review"):
                helper.validate_host_lock(root, SUPPORTED_VERSION)

    def test_review_receipt_is_exact_structured_and_fail_closed(self):
        helper = load_helper()
        review_source = LOCK_ROOT / SUPPORTED_VERSION / "review.json"
        required = {
            "schema", "package", "version", "registry", "root_integrity", "lock_sha256", "config_sha256",
            "source_repository", "source_tag", "source_commit", "reviewed_at", "reviewer",
            "licenses", "audits", "lifecycle_scripts", "signatures", "provenance", "result",
        }
        review = json.loads(review_source.read_text(encoding="utf-8"))
        self.assertEqual(set(review), required)
        self.assertEqual(review["result"], "PASS")

        for label, mutate in {
            "wrong-config-digest": lambda value: value.__setitem__("config_sha256", "0" * 64),
            "pass-prefix": lambda value: value.__setitem__("result", "PASS without evidence"),
            "missing-reviewer": lambda value: value.pop("reviewer"),
            "unknown-field": lambda value: value.__setitem__("unreviewed_note", "trust me"),
            "wrong-source-repository": lambda value: value.__setitem__("source_repository", None),
            "wrong-source-tag": lambda value: value.__setitem__("source_tag", "v0.84.2"),
            "invalid-source-commit": lambda value: value.__setitem__("source_commit", "not-a-commit"),
            "invalid-review-date": lambda value: value.__setitem__("reviewed_at", "not-a-date"),
            "wrong-reviewer": lambda value: value.__setitem__("reviewer", "untrusted-reviewer"),
            "failed-license": lambda value: value["licenses"].__setitem__("result", "FAIL"),
            "nonzero-audit": lambda value: value["audits"]["all"].__setitem__("high", 1),
            "nonzero-production-audit": lambda value: value["audits"]["production"].__setitem__("high", 1),
            "wrong-lifecycle-policy": lambda value: value["lifecycle_scripts"].__setitem__("policy", "allow"),
            "failed-signatures": lambda value: value["signatures"].__setitem__("verified", 0),
            "failed-provenance": lambda value: value["provenance"].__setitem__("attestations_verified", 0),
        }.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory(prefix="ca-pi-review-") as raw:
                root = Path(raw)
                target = root / ".github" / "fixtures" / "pi-hosts" / SUPPORTED_VERSION
                shutil.copytree(LOCK_ROOT / SUPPORTED_VERSION, target)
                candidate = json.loads(json.dumps(review))
                mutate(candidate)
                (target / "review.json").write_text(json.dumps(candidate), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "review|audit|source"):
                    helper.validate_host_lock(root, SUPPORTED_VERSION)

    def test_capture_preflights_registry_metadata_before_lock_resolution_and_disables_scripts(self):
        helper = load_helper()
        calls = []
        metadata_calls = []
        downloads = []
        metadata_preflight_seen = False

        def download(package_name, version, tarball, integrity, destination, **kwargs):
            self.assertTrue(metadata_preflight_seen, "archive download ran before direct registry metadata")
            downloads.append((package_name, version, tarball, integrity))
            destination.write_bytes(b"verified fixture tarball")
            if package_name == helper.PACKAGE:
                return {"manifest": {"name": package_name, "version": version}, "shrinkwrap": {
                    "name": helper.PACKAGE,
                    "version": SUPPORTED_VERSION,
                    "lockfileVersion": 3,
                    "packages": {
                        "": {"name": helper.PACKAGE, "version": SUPPORTED_VERSION},
                        "node_modules/shrinkwrap-only": {
                            "version": "1.2.3",
                            "resolved": "https://registry.npmjs.org/shrinkwrap-only.tgz",
                        },
                    },
                }}
            return {"manifest": {"name": package_name, "version": version}, "shrinkwrap": None}

        def metadata(npm, package_name, specification, environment, deadline):
            nonlocal metadata_preflight_seen
            metadata_calls.append((package_name, specification))
            if (package_name, specification) == (helper.PACKAGE, SUPPORTED_VERSION):
                metadata_preflight_seen = True
                return {
                    "version": SUPPORTED_VERSION,
                    "dist.integrity": "sha512-root",
                    "dist.tarball": "https://registry.npmjs.org/root.tgz",
                    "repository.url": helper.SOURCE_REPOSITORY,
                    "gitHead": "a" * 40,
                    "repository.url": "https://github.com/earendil-works/pi",
                    "gitHead": "a" * 40,
                    "dependencies": {},
                    "optionalDependencies": {},
                    "peerDependencies": {},
                }
            self.assertEqual((package_name, specification), ("shrinkwrap-only", "1.2.3"))
            return {
                "version": "1.2.3",
                "dist.integrity": "sha512-child",
                "dist.tarball": "https://registry.npmjs.org/shrinkwrap-only.tgz",
                "dependencies": {},
                "optionalDependencies": {},
                "peerDependencies": {},
            }

        def run(command, **kwargs):
            calls.append(command)
            operation = command[1]
            if operation == "install":
                self.assertTrue(metadata_preflight_seen, "npm install ran before registry metadata preflight")
                destination = Path(command[command.index("--prefix") + 1])
                lock = {
                    "lockfileVersion": 3,
                    "packages": {
                        "": {"dependencies": {helper.PACKAGE: SUPPORTED_VERSION}},
                        f"node_modules/{helper.PACKAGE}": {
                            "version": SUPPORTED_VERSION,
                            "resolved": "https://registry.npmjs.org/root.tgz",
                        },
                        f"node_modules/{helper.PACKAGE}/node_modules/shrinkwrap-only": {
                            "version": "1.2.3",
                            "resolved": "https://registry.npmjs.org/shrinkwrap-only.tgz",
                        },
                    },
                }
                (destination / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
                return SimpleNamespace(stdout="")
            if "cache" in command and "add" in command:
                return SimpleNamespace(stdout="")
            raise AssertionError(command)

        with tempfile.TemporaryDirectory(prefix="ca-pi-capture-") as raw, mock.patch.object(
            helper.subprocess, "run", side_effect=run,
        ), mock.patch.object(helper, "_run_registry_metadata", side_effect=metadata), mock.patch.object(
            helper, "_download_registry_tarball", side_effect=download,
        ):
            destination = Path(raw) / "candidate"
            helper.capture_candidate(SUPPORTED_VERSION, destination)
            captured = json.loads((destination / "package-lock.json").read_text(encoding="utf-8"))
            self.assertEqual(
                captured["packages"][f"node_modules/{helper.PACKAGE}"]["integrity"], "sha512-root",
            )
            self.assertEqual(
                captured["packages"][f"node_modules/{helper.PACKAGE}/node_modules/shrinkwrap-only"]["integrity"],
                "sha512-child",
            )
        self.assertEqual(calls, [], "capture must not invoke npm resolution or cache commands")
        self.assertEqual(
            downloads,
            [
                (helper.PACKAGE, SUPPORTED_VERSION, "https://registry.npmjs.org/root.tgz", "sha512-root"),
                ("shrinkwrap-only", "1.2.3", "https://registry.npmjs.org/shrinkwrap-only.tgz", "sha512-child"),
            ],
        )
        self.assertEqual(len(metadata_calls), 2)

    def test_root_archive_failure_aborts_before_candidate_lock_generation(self):
        helper = load_helper()
        calls = []
        metadata = {
            "version": SUPPORTED_VERSION,
            "dist.integrity": "sha512-root",
            "dist.tarball": "https://registry.npmjs.org/root.tgz",
            "repository.url": helper.SOURCE_REPOSITORY,
            "gitHead": "a" * 40,
            "dependencies": {},
            "optionalDependencies": {},
            "peerDependencies": {},
        }

        with tempfile.TemporaryDirectory(prefix="ca-pi-seed-fail-") as raw, mock.patch.object(
            helper, "_run_registry_metadata", return_value=metadata,
        ), mock.patch.object(
            helper, "_download_registry_tarball", side_effect=OSError("archive unavailable"),
        ), mock.patch.object(helper.subprocess, "run", side_effect=lambda command, **kwargs: calls.append(command)):
            with self.assertRaisesRegex(OSError, "archive unavailable"):
                helper.capture_candidate(SUPPORTED_VERSION, Path(raw) / "candidate")
        self.assertFalse(any("install" in command for command in calls))

    def test_capture_builds_from_verified_published_shrinkwrap_without_npm_resolution(self):
        helper = load_helper()
        root_metadata = {
            "version": SUPPORTED_VERSION,
            "dist.integrity": "sha512-root",
            "dist.tarball": "https://registry.npmjs.org/root.tgz",
            "repository.url": helper.SOURCE_REPOSITORY,
            "gitHead": "a" * 40,
            "dependencies": {},
            "optionalDependencies": {},
            "peerDependencies": {},
        }
        published = {
            "name": helper.PACKAGE,
            "version": SUPPORTED_VERSION,
            "lockfileVersion": 3,
            "requires": True,
            "packages": {
                "": {
                    "name": helper.PACKAGE,
                    "version": SUPPORTED_VERSION,
                    "license": "MIT",
                    "dependencies": {"child": "1.2.3"},
                },
                "node_modules/child": {
                    "version": "1.2.3",
                    "resolved": "https://registry.npmjs.org/child/-/child-1.2.3.tgz",
                    "integrity": "sha512-child",
                },
            },
        }

        def download(package_name, version, tarball, integrity, destination, **kwargs):
            destination.write_bytes(b"verified package archive")
            return {"manifest": {"name": package_name, "version": version}, "shrinkwrap": published}

        with tempfile.TemporaryDirectory(prefix="ca-pi-published-lock-") as raw, mock.patch.object(
            helper, "_run_registry_metadata", return_value=root_metadata,
        ), mock.patch.object(
            helper, "_download_registry_tarball", side_effect=download,
        ), mock.patch.object(
            helper.subprocess, "run", side_effect=AssertionError("npm resolution must not run"),
        ):
            destination = Path(raw) / "candidate"
            helper.capture_candidate(SUPPORTED_VERSION, destination)
            lock = json.loads((destination / "package-lock.json").read_text(encoding="utf-8"))
        prefix = f"node_modules/{helper.PACKAGE}"
        self.assertEqual(lock["packages"][prefix]["integrity"], "sha512-root")
        self.assertEqual(lock["packages"][prefix]["hasShrinkwrap"], True)
        self.assertEqual(lock["packages"][f"{prefix}/node_modules/child"]["version"], "1.2.3")

    def test_capture_rejects_missing_source_identity_before_download_or_receipt(self):
        helper = load_helper()
        minimized_metadata = {
            "version": SUPPORTED_VERSION,
            "dist.integrity": "sha512-root",
            "dist.tarball": "https://registry.npmjs.org/root.tgz",
            "repository.url": None,
            "gitHead": None,
            "dependencies": {},
            "optionalDependencies": {},
            "peerDependencies": {},
        }
        with tempfile.TemporaryDirectory(prefix="ca-pi-source-identity-") as raw, mock.patch.object(
            helper, "_run_registry_metadata", return_value=minimized_metadata,
        ), mock.patch.object(helper, "_download_registry_tarball") as download:
            destination = Path(raw) / "candidate"
            with self.assertRaisesRegex(ValueError, "source"):
                helper.capture_candidate(SUPPORTED_VERSION, destination)
            download.assert_not_called()
            self.assertFalse((destination / "review.json").exists())

    def test_tarball_download_is_registry_only_integrity_bound_and_identity_bound(self):
        helper = load_helper()
        manifest = json.dumps({"name": helper.PACKAGE, "version": SUPPORTED_VERSION}).encode("utf-8")
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode="w:gz") as archive:
            info = tarfile.TarInfo("package/package.json")
            info.size = len(manifest)
            archive.addfile(info, io.BytesIO(manifest))
        tarball_bytes = payload.getvalue()
        integrity = "sha512-" + base64.b64encode(hashlib.sha512(tarball_bytes).digest()).decode("ascii")

        class Response:
            status = 200

            def __init__(self):
                self.stream = io.BytesIO(tarball_bytes)

            def getheader(self, name):
                return str(len(tarball_bytes)) if name == "Content-Length" else None

            def read(self, size):
                return self.stream.read(size)

        class Connection:
            def __init__(self, host, timeout):
                self.host = host
                self.timeout = timeout

            def request(self, method, path, headers):
                self.requested = (method, path, headers)

            def getresponse(self):
                return Response()

            def close(self):
                pass

        with tempfile.TemporaryDirectory(prefix="ca-pi-tarball-") as raw, mock.patch.object(
            helper.http.client, "HTTPSConnection", Connection,
        ):
            destination = Path(raw) / "package.tgz"
            helper._download_registry_tarball(
                helper.PACKAGE, SUPPORTED_VERSION, "https://registry.npmjs.org/root.tgz",
                integrity, destination, deadline=float("inf"), byte_budget=len(tarball_bytes),
            )
            self.assertEqual(destination.read_bytes(), tarball_bytes)
            with self.assertRaisesRegex(ValueError, "integrity"):
                helper._download_registry_tarball(
                    helper.PACKAGE, SUPPORTED_VERSION, "https://registry.npmjs.org/root.tgz",
                    "sha512-" + base64.b64encode(b"x" * 64).decode("ascii"), destination,
                    deadline=float("inf"), byte_budget=len(tarball_bytes),
                )

    def test_tarball_download_rejects_alternate_hosts_and_ambiguous_identity(self):
        helper = load_helper()

        def build(entries):
            payload = io.BytesIO()
            with tarfile.open(fileobj=payload, mode="w:gz") as archive:
                for name, value, kind in entries:
                    info = tarfile.TarInfo(name)
                    if kind == "file":
                        info.size = len(value)
                        archive.addfile(info, io.BytesIO(value))
                    else:
                        info.type = kind
                        info.linkname = "package/package.json"
                        archive.addfile(info)
            return payload.getvalue()

        def connection_for(payload):
            class Response:
                status = 200
                def __init__(self):
                    self.stream = io.BytesIO(payload)
                def getheader(self, name):
                    return str(len(payload)) if name == "Content-Length" else None
                def read(self, size):
                    return self.stream.read(size)
            class Connection:
                def __init__(self, host, timeout):
                    pass
                def request(self, method, path, headers):
                    pass
                def getresponse(self):
                    return Response()
                def close(self):
                    pass
            return Connection

        good = json.dumps({"name": helper.PACKAGE, "version": SUPPORTED_VERSION}).encode("utf-8")
        wrong_name = json.dumps({"name": "wrong-package", "version": SUPPORTED_VERSION}).encode("utf-8")
        wrong_version = json.dumps({"name": helper.PACKAGE, "version": "0.84.2"}).encode("utf-8")
        cases = {
            "decoy-only": ([("nested/package.json", good, "file")], "canonical"),
            "wrong-name": ([("package/package.json", wrong_name, "file")], "identity"),
            "wrong-version": ([("package/package.json", wrong_version, "file")], "identity"),
            "duplicate": ([
                ("package/package.json", good, "file"),
                ("package/package.json", good, "file"),
            ], "exactly one"),
            "canonical-plus-decoy": ([
                ("package/package.json", good, "file"),
                ("nested/package.json", wrong_name, "file"),
            ], "alternate"),
            "symlink": ([
                ("package/package.json", good, "file"),
                ("package/alias", b"", tarfile.SYMTYPE),
            ], "link or special"),
            "special": ([
                ("package/package.json", good, "file"),
                ("package/device", b"", tarfile.CHRTYPE),
            ], "link or special"),
        }
        with tempfile.TemporaryDirectory(prefix="ca-pi-tarball-adversarial-") as raw:
            destination = Path(raw) / "package.tgz"
            with mock.patch.object(helper.http.client, "HTTPSConnection") as connection:
                with self.assertRaisesRegex(ValueError, "approved registry"):
                    helper._download_registry_tarball(
                        helper.PACKAGE, SUPPORTED_VERSION, "https://evil.invalid/root.tgz",
                        "sha512-" + base64.b64encode(b"x" * 64).decode("ascii"), destination,
                        deadline=float("inf"), byte_budget=1024,
                    )
                connection.assert_not_called()
            for label, (entries, message) in cases.items():
                with self.subTest(label=label):
                    payload = build(entries)
                    integrity = "sha512-" + base64.b64encode(hashlib.sha512(payload).digest()).decode("ascii")
                    with mock.patch.object(helper.http.client, "HTTPSConnection", connection_for(payload)):
                        with self.assertRaisesRegex(ValueError, message):
                            helper._download_registry_tarball(
                                helper.PACKAGE, SUPPORTED_VERSION,
                                "https://registry.npmjs.org/root.tgz", integrity, destination,
                                deadline=float("inf"), byte_budget=len(payload),
                            )

    def test_tarball_download_enforces_archive_bounds_and_stream_deadline(self):
        helper = load_helper()
        manifest = json.dumps({"name": helper.PACKAGE, "version": SUPPORTED_VERSION}).encode("utf-8")
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode="w:gz") as archive:
            info = tarfile.TarInfo("package/package.json")
            info.size = len(manifest)
            archive.addfile(info, io.BytesIO(manifest))
        tarball = payload.getvalue()
        integrity = "sha512-" + base64.b64encode(hashlib.sha512(tarball).digest()).decode("ascii")

        class Response:
            status = 200
            def __init__(self):
                self.stream = io.BytesIO(tarball)
            def getheader(self, name):
                return str(len(tarball)) if name == "Content-Length" else None
            def read(self, size):
                return self.stream.read(size)
        class Connection:
            def __init__(self, host, timeout):
                pass
            def request(self, method, path, headers):
                pass
            def getresponse(self):
                return Response()
            def close(self):
                pass

        limits = {
            "member limit": ("MAX_ARCHIVE_MEMBERS", 0),
            "member byte limit": ("MAX_ARCHIVE_MEMBER_BYTES", len(manifest) - 1),
            "uncompressed byte limit": ("MAX_ARCHIVE_UNCOMPRESSED_BYTES", len(manifest) - 1),
            "compression ratio limit": ("MAX_ARCHIVE_COMPRESSION_RATIO", 0),
        }
        with tempfile.TemporaryDirectory(prefix="ca-pi-tarball-bounds-") as raw:
            destination = Path(raw) / "package.tgz"
            for message, (constant, value) in limits.items():
                with self.subTest(limit=constant), mock.patch.object(
                    helper.http.client, "HTTPSConnection", Connection,
                ), mock.patch.object(helper, constant, value):
                    with self.assertRaisesRegex(ValueError, message):
                        helper._download_registry_tarball(
                            helper.PACKAGE, SUPPORTED_VERSION,
                            "https://registry.npmjs.org/root.tgz", integrity, destination,
                            deadline=float("inf"), byte_budget=len(tarball),
                        )
            with mock.patch.object(
                helper.http.client, "HTTPSConnection", Connection,
            ), mock.patch.object(helper.time, "monotonic", side_effect=[0.0, 2.0]):
                with self.assertRaisesRegex(ValueError, "time budget"):
                    helper._download_registry_tarball(
                        helper.PACKAGE, SUPPORTED_VERSION,
                        "https://registry.npmjs.org/root.tgz", integrity, destination,
                        deadline=1.0, byte_budget=len(tarball),
                    )

    def test_root_tarball_requires_one_exact_identity_bound_shrinkwrap(self):
        helper = load_helper()
        manifest = {"name": helper.PACKAGE, "version": SUPPORTED_VERSION}
        valid = {
            "name": helper.PACKAGE,
            "version": SUPPORTED_VERSION,
            "lockfileVersion": 3,
            "packages": {"": {"name": helper.PACKAGE, "version": SUPPORTED_VERSION}},
        }

        def archive_bytes(shrinkwrap_entries):
            payload = io.BytesIO()
            with tarfile.open(fileobj=payload, mode="w:gz") as archive:
                documents = [("package/package.json", manifest), *shrinkwrap_entries]
                for name, document in documents:
                    value = json.dumps(document).encode("utf-8")
                    info = tarfile.TarInfo(name)
                    info.size = len(value)
                    archive.addfile(info, io.BytesIO(value))
            return payload.getvalue()

        def connection_for(payload):
            class Response:
                status = 200
                def __init__(self):
                    self.stream = io.BytesIO(payload)
                def getheader(self, name):
                    return str(len(payload)) if name == "Content-Length" else None
                def read(self, size):
                    return self.stream.read(size)
                read1 = read
            class Connection:
                def __init__(self, host, timeout):
                    pass
                def request(self, method, path, headers):
                    pass
                def getresponse(self):
                    return Response()
                def close(self):
                    pass
            return Connection

        wrong_name = json.loads(json.dumps(valid))
        wrong_name["name"] = "wrong"
        wrong_version = json.loads(json.dumps(valid))
        wrong_version["version"] = "0.84.2"
        wrong_lock = json.loads(json.dumps(valid))
        wrong_lock["lockfileVersion"] = 2
        wrong_root = json.loads(json.dumps(valid))
        wrong_root["packages"][""]["name"] = "wrong"
        cases = {
            "missing": ([], "exactly one"),
            "duplicate": ([
                ("package/npm-shrinkwrap.json", valid),
                ("package/npm-shrinkwrap.json", valid),
            ], "exactly one"),
            "alternate": ([("other/npm-shrinkwrap.json", valid)], "alternate"),
            "wrong-name": ([("package/npm-shrinkwrap.json", wrong_name)], "identity"),
            "wrong-version": ([("package/npm-shrinkwrap.json", wrong_version)], "identity"),
            "wrong-lockfile": ([("package/npm-shrinkwrap.json", wrong_lock)], "identity"),
            "wrong-root": ([("package/npm-shrinkwrap.json", wrong_root)], "identity"),
        }
        with tempfile.TemporaryDirectory(prefix="ca-pi-root-shrinkwrap-") as raw:
            destination = Path(raw) / "package.tgz"
            payload = archive_bytes([("package/npm-shrinkwrap.json", valid)])
            integrity = "sha512-" + base64.b64encode(hashlib.sha512(payload).digest()).decode("ascii")
            with mock.patch.object(helper.http.client, "HTTPSConnection", connection_for(payload)):
                result = helper._download_registry_tarball(
                    helper.PACKAGE, SUPPORTED_VERSION,
                    "https://registry.npmjs.org/root.tgz", integrity, destination,
                    deadline=float("inf"), byte_budget=len(payload), require_shrinkwrap=True,
                )
            self.assertEqual(result["shrinkwrap"], valid)
            for label, (entries, message) in cases.items():
                with self.subTest(label=label):
                    payload = archive_bytes(entries)
                    integrity = "sha512-" + base64.b64encode(hashlib.sha512(payload).digest()).decode("ascii")
                    with mock.patch.object(helper.http.client, "HTTPSConnection", connection_for(payload)):
                        with self.assertRaisesRegex(ValueError, message):
                            helper._download_registry_tarball(
                                helper.PACKAGE, SUPPORTED_VERSION,
                                "https://registry.npmjs.org/root.tgz", integrity, destination,
                                deadline=float("inf"), byte_budget=len(payload), require_shrinkwrap=True,
                            )

    def test_wrapper_lock_rejects_unsafe_published_paths(self):
        helper = load_helper()
        metadata = {
            "dist.tarball": "https://registry.npmjs.org/root.tgz",
            "dist.integrity": "sha512-root",
        }
        published = {
            "packages": {
                "": {"name": helper.PACKAGE, "version": SUPPORTED_VERSION},
                "node_modules/../escape": {
                    "version": "1.0.0",
                    "resolved": "https://registry.npmjs.org/escape.tgz",
                    "integrity": "sha512-escape",
                },
            },
        }
        with self.assertRaisesRegex(ValueError, "unsafe"):
            helper._wrapper_lock_from_published_shrinkwrap(SUPPORTED_VERSION, metadata, published)

    def test_wrapper_lock_enforces_package_count_and_depth_before_recovery(self):
        helper = load_helper()
        metadata = {
            "dist.tarball": "https://registry.npmjs.org/root.tgz",
            "dist.integrity": "sha512-root",
        }
        root = {"name": helper.PACKAGE, "version": SUPPORTED_VERSION}
        entry = {
            "version": "1.0.0",
            "resolved": "https://registry.npmjs.org/package.tgz",
            "integrity": "sha512-package",
        }
        with mock.patch.object(helper, "MAX_METADATA_PACKAGES", 2):
            helper._wrapper_lock_from_published_shrinkwrap(SUPPORTED_VERSION, metadata, {
                "packages": {"": root, "node_modules/one": entry},
            })
            with self.assertRaisesRegex(ValueError, "package count"):
                helper._wrapper_lock_from_published_shrinkwrap(SUPPORTED_VERSION, metadata, {
                    "packages": {"": root, "node_modules/one": entry, "node_modules/two": entry},
                })
        with mock.patch.object(helper, "MAX_METADATA_DEPTH", 1):
            with self.assertRaisesRegex(ValueError, "depth"):
                helper._wrapper_lock_from_published_shrinkwrap(SUPPORTED_VERSION, metadata, {
                    "packages": {"": root, "node_modules/one/node_modules/two": entry},
                })

    def test_candidate_capture_is_byte_identical_and_never_requeries_seeded_metadata(self):
        helper = load_helper()
        calls = []
        metadata_calls = []

        def metadata(npm, package_name, specification, environment, deadline):
            metadata_calls.append((package_name, specification))
            return {
                "version": SUPPORTED_VERSION,
                "dist.integrity": "sha512-root",
                "dist.tarball": "https://registry.npmjs.org/root.tgz",
                "repository.url": "https://github.com/earendil-works/pi",
                "gitHead": "a" * 40,
                "dependencies": {},
                "optionalDependencies": {},
                "peerDependencies": {},
            }

        def run(command, **kwargs):
            calls.append(command)
            if "cache" in command and "add" in command:
                self.assertTrue(command[command.index("add") + 1].endswith(".tgz"))
                return SimpleNamespace(stdout="")
            if "install" in command:
                destination = Path(command[command.index("--prefix") + 1])
                lock = {
                    "lockfileVersion": 3,
                    "packages": {
                        "": {"dependencies": {helper.PACKAGE: SUPPORTED_VERSION}},
                        f"node_modules/{helper.PACKAGE}": {
                            "version": SUPPORTED_VERSION,
                            "resolved": "https://registry.npmjs.org/root.tgz",
                            "integrity": "sha512-root",
                        },
                    },
                }
                (destination / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
                return SimpleNamespace(stdout="")
            raise AssertionError(command)

        def download(package_name, version, tarball, integrity, destination, **kwargs):
            destination.write_bytes(b"verified fixture tarball")
            return {"manifest": {"name": package_name, "version": version}, "shrinkwrap": {
                "name": helper.PACKAGE,
                "version": SUPPORTED_VERSION,
                "lockfileVersion": 3,
                "packages": {"": {"name": helper.PACKAGE, "version": SUPPORTED_VERSION}},
            }}

        with tempfile.TemporaryDirectory(prefix="ca-pi-double-capture-") as raw, mock.patch.object(
            helper.subprocess, "run", side_effect=run,
        ), mock.patch.object(helper, "_run_registry_metadata", side_effect=metadata), mock.patch.object(
            helper, "_download_registry_tarball", side_effect=download,
        ):
            root = Path(raw)
            first = root / "first"
            second = root / "second"
            first_result = helper.capture_candidate(SUPPORTED_VERSION, first)
            second_result = helper.capture_candidate(SUPPORTED_VERSION, second)
            self.assertEqual(first_result, second_result)
            for name in ("package.json", ".npmrc", "package-lock.json", "review.json"):
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
                self.assertNotIn(b"\r", (first / name).read_bytes())
        self.assertEqual(len(metadata_calls), 2)

    def test_registry_metadata_preflight_rejects_non_registry_specs_before_install(self):
        helper = load_helper()
        calls = []

        def metadata(npm, package_name, specification, environment, deadline):
            return {
                "version": SUPPORTED_VERSION,
                "dist.integrity": "sha512-root",
                "dist.tarball": "https://registry.npmjs.org/root.tgz",
                "repository.url": "https://github.com/earendil-works/pi",
                "gitHead": "a" * 40,
                "dependencies": {"unsafe": "git+https://github.com/example/unsafe.git"},
                "optionalDependencies": {},
                "peerDependencies": {},
            }

        with tempfile.TemporaryDirectory(prefix="ca-pi-egress-") as raw, mock.patch.object(
            helper.subprocess, "run", side_effect=lambda command, **kwargs: calls.append(command),
        ), mock.patch.object(
            helper, "_run_registry_metadata", side_effect=metadata,
        ):
            with self.assertRaisesRegex(ValueError, "registry|dependency specification"):
                helper.capture_candidate(SUPPORTED_VERSION, Path(raw) / "candidate")
        self.assertFalse(any(command[1] == "install" for command in calls))

    def test_registry_metadata_preflight_retries_a_transient_registry_failure(self):
        helper = load_helper()
        attempts = 0
        requests = []

        packument = {
            "versions": {SUPPORTED_VERSION: {
                "name": helper.PACKAGE,
                "version": SUPPORTED_VERSION,
                "dist": {
                    "integrity": "sha512-root",
                    "tarball": "https://registry.npmjs.org/root.tgz",
                },
            }},
            "dist-tags": {"latest": SUPPORTED_VERSION},
        }
        payload = json.dumps(packument).encode("utf-8")

        class Response:
            status = 200
            def __init__(self):
                self.stream = io.BytesIO(payload)
            def getheader(self, name):
                return str(len(payload)) if name == "Content-Length" else None
            def read(self, size):
                return self.stream.read(size)

        class Connection:
            def __init__(self, host, timeout):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise OSError("transient registry failure")
            def request(self, method, path, headers):
                requests.append((method, path, headers))
            def getresponse(self):
                return Response()
            def close(self):
                pass

        with mock.patch.object(helper.http.client, "HTTPSConnection", Connection), mock.patch.object(
            helper.time, "sleep",
        ):
            metadata = helper._fetch_registry_packument(helper.PACKAGE, float("inf"))
        self.assertEqual(metadata["versions"][SUPPORTED_VERSION]["version"], SUPPORTED_VERSION)
        self.assertEqual(attempts, 2)
        self.assertEqual(requests, [(
            "GET", "/@earendil-works%2Fpi-coding-agent",
            {"Accept": "application/json", "User-Agent": "codeArbiter-pi-host-lock/1"},
        )])

    def test_candidate_resolver_returns_only_the_exact_registry_identity(self):
        helper = load_helper()
        metadata = {
            "version": SUPPORTED_VERSION,
            "dist.integrity": "sha512-root",
            "dist.tarball": "https://registry.npmjs.org/root.tgz",
            "repository.url": helper.SOURCE_REPOSITORY,
            "gitHead": "a" * 40,
            "dependencies": {},
            "optionalDependencies": {},
            "peerDependencies": {},
        }
        with mock.patch.object(helper, "_run_registry_metadata", return_value=metadata) as query:
            resolved = helper.resolve_candidate("latest")
        self.assertEqual(resolved, {"package": helper.PACKAGE, "version": SUPPORTED_VERSION})
        self.assertEqual(query.call_args.args[1:3], (helper.PACKAGE, "latest"))

    def test_registry_metadata_permanent_failure_stops_after_three_attempts(self):
        helper = load_helper()
        attempts = 0

        class Connection:
            def __init__(self, host, timeout):
                nonlocal attempts
                attempts += 1
                raise OSError("registry unavailable")

        with mock.patch.object(helper.http.client, "HTTPSConnection", Connection), mock.patch.object(
            helper.time, "sleep",
        ) as sleep, mock.patch.object(helper, "_download_registry_tarball") as download:
            with self.assertRaisesRegex(OSError, "registry unavailable"):
                helper._fetch_registry_packument(helper.PACKAGE, float("inf"))
        self.assertEqual(attempts, 3)
        self.assertEqual(sleep.call_count, 2)
        download.assert_not_called()

    def test_registry_metadata_slow_drip_cannot_outlive_aggregate_deadline(self):
        helper = load_helper()

        class Response:
            status = 200
            def getheader(self, name):
                return None
            def read(self, size):
                return b"x"
            read1 = read
        class Connection:
            def __init__(self, host, timeout):
                pass
            def request(self, method, path, headers):
                pass
            def getresponse(self):
                return Response()
            def close(self):
                pass

        clock = iter([0.0, 0.1, 0.2, 0.4, 0.6, 0.8, 1.1])
        with mock.patch.object(helper.http.client, "HTTPSConnection", Connection), mock.patch.object(
            helper.time, "monotonic", side_effect=lambda: next(clock),
        ):
            with self.assertRaisesRegex(ValueError, "time budget"):
                helper._fetch_registry_packument(helper.PACKAGE, 1.0)

    def test_registry_metadata_redirect_is_rejected_without_following(self):
        helper = load_helper()
        hosts = []

        class Response:
            status = 302
            def getheader(self, name):
                return "https://evil.invalid/package" if name == "Location" else None

        class Connection:
            def __init__(self, host, timeout):
                hosts.append(host)
            def request(self, method, path, headers):
                pass
            def getresponse(self):
                return Response()
            def close(self):
                pass

        with mock.patch.object(helper.http.client, "HTTPSConnection", Connection):
            with self.assertRaisesRegex(ValueError, "HTTP 302"):
                helper._fetch_registry_packument(helper.PACKAGE, float("inf"))
        self.assertEqual(hosts, ["registry.npmjs.org"])

    def test_required_metadata_failure_aborts_before_lock_generation(self):
        helper = load_helper()
        calls = []
        metadata_calls = []

        def metadata(npm, package_name, specification, environment, deadline):
            metadata_calls.append((package_name, specification))
            if len(metadata_calls) == 1:
                return {
                    "version": SUPPORTED_VERSION,
                    "dist.integrity": "sha512-root",
                    "dist.tarball": "https://registry.npmjs.org/root.tgz",
                    "repository.url": helper.SOURCE_REPOSITORY,
                    "gitHead": "a" * 40,
                    "dependencies": {},
                    "optionalDependencies": {},
                    "peerDependencies": {},
                }
            raise OSError("not found")

        published = {
            "name": helper.PACKAGE,
            "version": SUPPORTED_VERSION,
            "lockfileVersion": 3,
            "packages": {
                "": {"name": helper.PACKAGE, "version": SUPPORTED_VERSION},
                "node_modules/required-package": {
                    "version": "1.0.0",
                    "resolved": "https://registry.npmjs.org/required-package/-/required-package-1.0.0.tgz",
                },
            },
        }

        def download(package_name, version, tarball, integrity, destination, **kwargs):
            destination.write_bytes(b"verified fixture tarball")
            return {"manifest": {"name": package_name, "version": version}, "shrinkwrap": published}

        with tempfile.TemporaryDirectory(prefix="ca-pi-required-") as raw, mock.patch.object(
            helper, "_run_registry_metadata", side_effect=metadata,
        ), mock.patch.object(
            helper, "_download_registry_tarball", side_effect=download,
        ), mock.patch.object(helper.subprocess, "run", side_effect=lambda command, **kwargs: calls.append(command)):
            with self.assertRaises(OSError):
                helper.capture_candidate(SUPPORTED_VERSION, Path(raw) / "candidate")
        self.assertEqual(len(metadata_calls), 2)
        self.assertFalse(any("install" in command for command in calls))

    def test_registry_metadata_output_enforces_resource_bound(self):
        helper = load_helper()

        class OversizedResponse:
            status = 200

            def getheader(self, name):
                return "101" if name == "Content-Length" else None

        class Connection:
            def __init__(self, host, timeout):
                pass

            def request(self, method, path, headers):
                pass

            def getresponse(self):
                return OversizedResponse()

            def close(self):
                pass

        with mock.patch.object(
            helper.http.client, "HTTPSConnection", Connection,
        ), mock.patch.object(helper, "MAX_METADATA_OUTPUT_BYTES", 100):
            with self.assertRaisesRegex(ValueError, "output limit"):
                helper._fetch_registry_packument(helper.PACKAGE, float("inf"))

    def test_metadata_query_has_a_per_process_timeout(self):
        helper = load_helper()

        def run(command, **kwargs):
            self.assertGreater(kwargs["timeout"], 0)
            self.assertLessEqual(kwargs["timeout"], helper.MAX_METADATA_QUERY_SECONDS)
            return SimpleNamespace(stdout=SUPPORTED_VERSION)

        packument = {
            "versions": {SUPPORTED_VERSION: {}},
            "dist-tags": {},
        }
        with tempfile.TemporaryDirectory(prefix="ca-pi-timeout-") as raw, mock.patch.object(
            helper.subprocess, "run", side_effect=run,
        ), mock.patch.object(helper, "_npm_semver_module", return_value=Path(raw)):
            selected = helper._select_registry_version("npm", "^0.84.0", packument, {}, float("inf"))
        self.assertEqual(selected, SUPPORTED_VERSION)

    def test_windows_npm_metadata_queries_bypass_the_cmd_wrapper(self):
        helper = load_helper()
        with tempfile.TemporaryDirectory(prefix="ca-pi-npm-cli-") as raw:
            root = Path(raw)
            npm = root / "npm.CMD"
            cli = root / "node_modules" / "npm" / "bin" / "npm-cli.js"
            cli.parent.mkdir(parents=True)
            npm.write_text("@echo off\n", encoding="utf-8")
            cli.write_text("", encoding="utf-8")
            with mock.patch.object(helper.shutil, "which", return_value=str(root / "node.exe")):
                prefix = helper._npm_command_prefix(str(npm))
        self.assertEqual(prefix, [str(root / "node.exe"), str(cli)])

    def test_failed_install_audit_never_publishes_github_path(self):
        helper = load_helper()
        with tempfile.TemporaryDirectory(prefix="ca-pi-install-") as raw:
            root = Path(raw)
            destination = root / "prefix"
            github_path = root / "github-path"
            github_path.write_text("existing\n", encoding="utf-8")
            with mock.patch.object(helper.subprocess, "run", return_value=SimpleNamespace(stdout="")), mock.patch.object(
                helper, "_audit_install", side_effect=ValueError("audit failed"),
            ), mock.patch.dict(os.environ, {"GITHUB_PATH": str(github_path)}):
                with self.assertRaisesRegex(ValueError, "audit failed"):
                    helper.install(REPO, SUPPORTED_VERSION, destination)
            self.assertEqual(github_path.read_text(encoding="utf-8"), "existing\n")

    def test_install_audit_rejects_wrong_installed_pi_version(self):
        helper = load_helper()
        wrong = json.dumps({"dependencies": {helper.PACKAGE: {"version": "0.84.2"}}})
        completed = SimpleNamespace(stdout=wrong)
        with tempfile.TemporaryDirectory(prefix="ca-pi-audit-") as raw, mock.patch.object(
            helper.subprocess, "run", return_value=completed,
        ):
            root = Path(raw)
            with self.assertRaisesRegex(ValueError, "exact reviewed version"):
                helper._audit_install(root, root, SUPPORTED_VERSION)

    def test_install_refuses_a_repository_destination(self):
        helper = load_helper()
        with self.assertRaisesRegex(ValueError, "outside the repository"):
            helper.install(REPO, SUPPORTED_VERSION, REPO / ".pi-host")

    def test_supported_workflows_consume_reviewed_lock_not_global_install(self):
        ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        promotion = (REPO / ".github" / "workflows" / "pi-promotion.yml").read_text(encoding="utf-8")
        self.assertIn("pi_host_locks.py install", ci)
        self.assertIn("pi_host_locks.py install", promotion)
        self.assertIn("pi_host_locks.py capture", promotion)
        self.assertIn("pi_host_locks.py resolve", promotion)
        self.assertNotIn("npm view", promotion)
        self.assertNotIn("pi_host_locks.py install-candidate", promotion)
        self.assertNotIn("pi-host-candidate/node_modules/.bin", promotion)
        self.assertIn("gh pr create --draft", promotion)
        self.assertIn("dependency review is required before candidate code executes", promotion)
        self.assertIn("persist-credentials: false", promotion)
        credential_free_capture = promotion.index("name: Capture candidate graph without write credentials")
        write_authorized = promotion.index("name: Create the deterministic promotion branch contents")
        self.assertLess(credential_free_capture, write_authorized)
        self.assertNotIn("pi_host_locks.py capture", promotion[write_authorized:])
        self.assertNotIn("GH_TOKEN:", promotion[:write_authorized])
        self.assertNotIn("npm install --global @earendil-works/pi-coding-agent@0.84.1", ci)
        self.assertNotIn("npm install --global @earendil-works/pi-coding-agent@${{ needs.resolve.outputs.baseline }}", promotion)

    def test_pending_candidate_has_no_install_api(self):
        helper = load_helper()
        self.assertFalse(
            hasattr(helper, "install_candidate"),
            "a PENDING_REVIEW candidate must remain inert until dependency review records PASS",
        )


if __name__ == "__main__":
    unittest.main()

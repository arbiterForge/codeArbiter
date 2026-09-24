#!/usr/bin/env python3
"""Contracts for promoting the qualified Codex archive as a Git distribution tree."""
from __future__ import annotations

import hashlib
import base64
import argparse
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
import subprocess
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "core" / "pysrc"))
from _gitexec import _ROOT_OVERRIDE_ENV, root_bound_git_env  # noqa: E402


def git_run(argv, **kwargs):
    environment = kwargs.pop("env", None)
    clean = root_bound_git_env()
    if environment is not None:
        clean.update(environment)
    for name in _ROOT_OVERRIDE_ENV:
        clean.pop(name, None)
    return subprocess.run(argv, env=clean, **kwargs)


SPEC = importlib.util.spec_from_file_location(
    "build_host_packages", REPO / "tools" / "build-host-packages.py"
)
PACKAGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGER)
PROMOTION_SPEC = importlib.util.spec_from_file_location(
    "promote_codex_marketplace", REPO / "tools" / "promote-codex-marketplace.py"
)
PROMOTER = importlib.util.module_from_spec(PROMOTION_SPEC)
PROMOTION_SPEC.loader.exec_module(PROMOTER)
RULESET_SPEC = importlib.util.spec_from_file_location(
    "verify_codex_distribution_rulesets", REPO / ".github/scripts/verify_codex_distribution_rulesets.py"
)
RULESETS = importlib.util.module_from_spec(RULESET_SPEC)
RULESET_SPEC.loader.exec_module(RULESETS)
TOKEN_SPEC = importlib.util.spec_from_file_location(
    "create_codex_distribution_token", REPO / ".github/scripts/create_codex_distribution_token.py"
)
TOKEN = importlib.util.module_from_spec(TOKEN_SPEC)
TOKEN_SPEC.loader.exec_module(TOKEN)
NPM_SPEC = importlib.util.spec_from_file_location(
    "npm_publishlib", REPO / ".github/scripts/_npm_publishlib.py"
)
NPM = importlib.util.module_from_spec(NPM_SPEC)
NPM_SPEC.loader.exec_module(NPM)


def archive_bytes(members: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name, data in sorted(members.items()):
            info = tarfile.TarInfo(name)
            info.mode = 0o755 if name.endswith("ca-artifact-linux-amd64") else 0o644
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return stream.getvalue()


class CodexMarketplaceDistributionTests(unittest.TestCase):
    def test_dedicated_app_token_uses_bounded_jwt_exchange_and_refuses_actions_actor(self):
        key = self.root / "app.pem"
        key.write_text("fixture key", encoding="utf-8")

        class Response:
            def __enter__(self):
                return io.BytesIO(b'{"token":"installation-token"}')
            def __exit__(self, *_args):
                return False

        completed = subprocess.CompletedProcess(["openssl"], 0, b"signature", b"")
        opener = mock.Mock()
        opener.open.return_value = Response()
        with mock.patch.object(TOKEN.time, "time", return_value=1000), \
             mock.patch.object(TOKEN.subprocess, "run", return_value=completed) as run, \
             mock.patch.object(TOKEN.urllib.request, "build_opener", return_value=opener) as build_opener:
            self.assertEqual("installation-token", TOKEN.mint(424242, 777, key))
        self.assertEqual(run.call_args.kwargs["input"].count(b"."), 1)
        build_opener.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.github.com/app/installations/777/access_tokens")
        self.assertTrue(request.headers["Authorization"].startswith("Bearer "))
        self.assertIsNone(TOKEN._NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://example.invalid"))
        with self.assertRaisesRegex(ValueError, "dedicated"):
            TOKEN.mint(15368, 777, key)
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        # macOS may spell the temporary root through /var -> /private/var.
        # The packager intentionally requires a canonical, real package root.
        self.root = Path(self.temporary.name).resolve(strict=True)
        self.package_root = self.root / "packages"
        self.package_root.mkdir()
        self.catalog = (
            b'{"name":"codearbiter","plugins":[{"name":"ca-codex",'
            b'"source":{"source":"local","path":"./plugins/ca-codex"},'
            b'"policy":{"installation":"AVAILABLE","authentication":"ON_INSTALL"}}]}\n'
        )
        self.source = self.root / "source"
        (self.source / ".agents/plugins").mkdir(parents=True)
        (self.source / ".agents/plugins/marketplace.json").write_bytes(self.catalog)
        git_run(["git", "init", "--quiet"], cwd=self.source, check=True)
        git_run(["git", "add", "."], cwd=self.source, check=True)
        environment = {**os.environ, "GIT_AUTHOR_NAME":"test",
            "GIT_AUTHOR_EMAIL":"test@example.invalid","GIT_COMMITTER_NAME":"test",
            "GIT_COMMITTER_EMAIL":"test@example.invalid"}
        git_run(["git", "commit", "--quiet", "-m", "source"], cwd=self.source,
                       env=environment, check=True)
        self.source_commit = git_run(["git", "rev-parse", "HEAD"], cwd=self.source,
            check=True, capture_output=True, text=True).stdout.strip()
        release = b'{"format":"codearbiter.artifact-release/0.1.0"}\n'
        binary = b"qualified-native-binary"
        self.members = {
            ".agents/plugins/marketplace.json": self.catalog,
            "plugins/ca-codex/.codex-plugin/plugin.json": (
                b'{"name":"ca-codex","version":"9.8.7"}\n'
            ),
            "plugins/ca-codex/package.json": (
                b'{"name":"@arbiterforge/ca-codex","version":"9.8.7",'
                b'"license":"AGPL-3.0-only","repository":{"type":"git",'
                b'"url":"git+https://github.com/arbiterForge/codeArbiter.git"},'
                b'"publishConfig":{"access":"public","provenance":true}}\n'
            ),
            "plugins/ca-codex/hooks/bridge.py": b"print('bridge')\n",
            "plugins/ca-codex/helpers/artifacts/release.json": release,
            "plugins/ca-codex/helpers/artifacts/ca-artifact-linux-amd64": binary,
        }
        self.archive = self.package_root / "codearbiter-ca-codex-9.8.7.tar.gz"
        self._write_package(self.members)

    def test_fixture_git_commands_ignore_inherited_repository_location(self):
        environment = dict(os.environ)
        environment["GIT_DIR"] = str(self.root / "unrelated.git")
        environment["GIT_WORK_TREE"] = str(self.root)
        environment["GIT_INDEX_FILE"] = str(self.root / "unrelated.index")
        result = subprocess.run(
            [sys.executable, __file__,
             "CodexMarketplaceDistributionTests.test_fixture_repository_is_under_its_own_root"],
            env=environment, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fixture_repository_is_under_its_own_root(self):
        self.assertTrue((self.source / ".git").exists())

    def _write_package(self, members: dict[str, bytes]):
        version = json.loads(members["plugins/ca-codex/.codex-plugin/plugin.json"])["version"]
        self.archive = self.package_root / f"codearbiter-ca-codex-{version}.tar.gz"
        data = archive_bytes(members)
        self.archive.write_bytes(data)
        receipt_members = {}
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in archive.getmembers():
                payload = archive.extractfile(member).read()
                receipt_members[member.name] = {
                    "type": "file",
                    "mode": f"{member.mode:04o}",
                    "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "origin": "promotion" if "/helpers/artifacts/" in member.name else "source",
                    "source": member.name,
                }
        receipt = {
            "format": PACKAGER.ARTIFACT_PACKAGE_FORMAT,
            "source_commit": self.source_commit,
            "packages": {
                "codex": {
                    "file": self.archive.name,
                    "version": version,
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "members": receipt_members,
                }
            },
        }
        self.receipt_path = self.package_root / "artifact-package-cohort.json"
        self.receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        self.receipt_sha256 = hashlib.sha256(self.receipt_path.read_bytes()).hexdigest()

    def test_stages_the_exact_qualified_archive_member_set(self):
        output = self.root / "distribution"
        result = PACKAGER.stage_codex_marketplace_distribution(
            package_root=self.package_root,
            package_cohort_sha256=self.receipt_sha256,
            output=output,
        )
        observed = {
            path.relative_to(output).as_posix(): path.read_bytes()
            for path in output.rglob("*") if path.is_file()
        }
        self.assertEqual(self.members, observed)
        self.assertEqual(sorted(self.members), result["members"])
        self.assertEqual(hashlib.sha256(self.catalog).hexdigest(), result["catalog_sha256"])

    def test_rejects_omitted_or_substituted_archive_payload(self):
        original = self.archive.read_bytes()
        for name, mutation in {
            "omitted": {key: value for key, value in self.members.items()
                        if not key.endswith("ca-artifact-linux-amd64")},
            "substituted": dict(self.members, **{
                "plugins/ca-codex/helpers/artifacts/ca-artifact-linux-amd64": b"different"
            }),
        }.items():
            with self.subTest(name=name):
                self.archive.write_bytes(archive_bytes(mutation))
                with self.assertRaisesRegex(ValueError, "archive|member|digest|size"):
                    PACKAGER.stage_codex_marketplace_distribution(
                        package_root=self.package_root,
                        package_cohort_sha256=self.receipt_sha256,
                        output=self.root / f"distribution-{name}",
                    )
                self.assertFalse((self.root / f"distribution-{name}").exists())
        self.archive.write_bytes(original)

    def test_builds_npm_package_from_exact_qualified_plugin_members(self):
        output = self.root / "npm"
        result = PACKAGER.build_codex_npm_package(
            package_root=self.package_root,
            package_cohort_sha256=self.receipt_sha256,
            output=output,
        )
        package = output / result["file"]
        observed = PACKAGER._read_archive(package)
        expected = {
            "package/" + name.removeprefix("plugins/ca-codex/"): data
            for name, data in self.members.items()
            if name.startswith("plugins/ca-codex/")
        }
        self.assertEqual(expected, {name: value[0] for name, value in observed.items()})
        for name, (_data, mode) in observed.items():
            expected_mode = 0o755 if name.endswith("ca-artifact-linux-amd64") else 0o644
            self.assertEqual(expected_mode, mode, name)
        self.assertEqual("@arbiterforge/ca-codex", result["package"])
        self.assertEqual("9.8.7", result["version"])
        self.assertEqual(self.receipt_sha256, result["cohort_sha256"])
        self.assertRegex(result["integrity"], r"^sha512-[A-Za-z0-9+/]+={0,2}$")

    def test_codex_npm_package_rejects_manifest_identity_drift(self):
        changed = dict(self.members)
        changed["plugins/ca-codex/package.json"] = (
            b'{"name":"lookalike","version":"9.8.7"}\n'
        )
        self._write_package(changed)
        with self.assertRaisesRegex(ValueError, "npm package identity"):
            PACKAGER.build_codex_npm_package(
                package_root=self.package_root,
                package_cohort_sha256=self.receipt_sha256,
                output=self.root / "npm-wrong-identity",
            )

    def test_registry_readback_accepts_only_the_exact_codex_package(self):
        integrity = "sha512-" + base64.b64encode(b"x" * 64).decode("ascii")
        document = {
            "version": "9.8.7",
            "dist": {
                "integrity": integrity,
                "attestations": {
                    "url": (
                        "https://registry.npmjs.org/-/npm/v1/attestations/"
                        "@arbiterforge%2fca-codex@9.8.7"
                    ),
                    "provenance": {"predicateType": NPM.PROVENANCE_PREDICATE},
                },
            },
        }
        self.assertEqual(
            "present",
            NPM.classify_registry_lookup(
                0, json.dumps(document), "", "9.8.7", integrity,
                package="@arbiterforge/ca-codex",
            ),
        )
        with self.assertRaisesRegex(ValueError, "attestation URL"):
            NPM.classify_registry_lookup(
                0, json.dumps(document), "", "9.8.7", integrity,
                package="@arbiterforge/lookalike",
            )

    def test_codex_provenance_subject_binds_the_exact_npm_tarball(self):
        integrity = "sha512-" + base64.b64encode(b"y" * 64).decode("ascii")
        source_sha = "8" * 40
        statement = {
            "_type": "https://in-toto.io/Statement/v1",
            "predicateType": NPM.PROVENANCE_PREDICATE,
            "subject": [{
                "name": "pkg:npm/%40arbiterforge/ca-codex@9.8.7",
                "digest": {"sha512": (b"y" * 64).hex()},
            }],
            "predicate": {
                "buildDefinition": {
                    "externalParameters": {"workflow": {
                        "repository": NPM.SOURCE_REPOSITORY,
                        "ref": NPM.SOURCE_REF,
                        "path": ".github/workflows/release.yml",
                    }},
                    "resolvedDependencies": [{
                        "uri": f"git+{NPM.SOURCE_REPOSITORY}@{NPM.SOURCE_REF}",
                        "digest": {"gitCommit": source_sha},
                    }],
                },
                "runDetails": {"builder": {
                    "id": "https://github.com/actions/runner/github-hosted"
                }},
            },
        }
        document = {"attestations": [{
            "predicateType": NPM.PROVENANCE_PREDICATE,
            "bundle": {"dsseEnvelope": {"payload": base64.b64encode(
                json.dumps(statement).encode("utf-8")
            ).decode("ascii")}},
        }]}
        self.assertEqual(
            source_sha,
            NPM.validate_attestation_document(
                document, "9.8.7", integrity, source_sha,
                package="@arbiterforge/ca-codex",
            ),
        )

    def test_codex_prepare_refuses_registry_drift_before_publication(self):
        tarball = self.root / "qualified.tgz"
        tarball.write_bytes(b"qualified codex npm package")
        integrity = "sha512-" + base64.b64encode(
            hashlib.sha512(tarball.read_bytes()).digest()
        ).decode("ascii")
        metadata = self.root / "codex-npm.json"
        metadata.write_text(json.dumps({
            "package": "@arbiterforge/ca-codex",
            "version": "9.8.7",
            "file": tarball.name,
            "size": tarball.stat().st_size,
            "sha256": hashlib.sha256(tarball.read_bytes()).hexdigest(),
            "integrity": integrity,
            "cohort_sha256": "1" * 64,
            "source_commit": self.source_commit,
            "source_archive": self.archive.name,
            "source_archive_sha256": hashlib.sha256(self.archive.read_bytes()).hexdigest(),
            "members": {},
        }), encoding="utf-8")
        output = self.root / "outputs"
        args = argparse.Namespace(
            metadata=str(metadata), tarball=str(tarball),
            expected_sha=self.source_commit, trusted_sha=self.source_commit,
            expected_cohort_sha256="2" * 64,
            expected_source_archive_sha256=hashlib.sha256(self.archive.read_bytes()).hexdigest(),
            trusted_repo=str(self.source), npm="npm", output=str(output),
            allow_continuation=False,
        )
        mismatched = subprocess.CompletedProcess(
            ["npm"], 0,
            stdout=json.dumps({"version": "9.8.7", "dist": {
                "integrity": "sha512-wrong", "attestations": {}
            }}), stderr="",
        )
        with mock.patch.object(NPM, "validate_release_source_binding"), \
             mock.patch.object(NPM, "registry_lookup", return_value=mismatched):
            with self.assertRaisesRegex(ValueError, "cohort"):
                NPM.prepare_codex(args)
            args.expected_cohort_sha256 = "1" * 64
            with self.assertRaisesRegex(ValueError, "integrity"):
                NPM.prepare_codex(args)
        self.assertFalse(output.exists())

    def _verify_codex_args(self, **overrides):
        values = {
            "version": "9.8.7",
            "integrity": "sha512-" + base64.b64encode(b"v" * 64).decode("ascii"),
            "expected_sha": self.source_commit,
            "trusted_sha": self.source_commit,
            "repo": str(self.source),
            "npm": "npm",
            "attempts": 2,
            "delay_seconds": 0,
            "readback_seconds": 1,
            "allow_continuation": False,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def _present_codex_lookup(self, args):
        return subprocess.CompletedProcess(
            ["npm"], 0,
            stdout=json.dumps({
                "version": args.version,
                "dist": {
                    "integrity": args.integrity,
                    "attestations": {
                        "url": (
                            "https://registry.npmjs.org/-/npm/v1/attestations/"
                            f"@arbiterforge%2fca-codex@{args.version}"
                        ),
                        "provenance": {"predicateType": NPM.PROVENANCE_PREDICATE},
                    },
                },
            }),
            stderr="",
        )

    def test_codex_verify_accepts_exact_registry_and_provenance_readback(self):
        args = self._verify_codex_args()
        evidence = {"attestations": []}
        with mock.patch.object(NPM, "validate_release_source_binding"), \
             mock.patch.object(NPM, "registry_lookup", return_value=self._present_codex_lookup(args)), \
             mock.patch.object(NPM, "verify_registry_authenticity", return_value=evidence) as authentic, \
             mock.patch.object(NPM, "validate_publication_attestation") as provenance:
            self.assertEqual(0, NPM.verify_codex(args))
        authentic.assert_called_once_with(
            "npm", "9.8.7", package="@arbiterforge/ca-codex"
        )
        provenance.assert_called_once()

    def test_codex_verify_rejects_absent_and_unavailable_readback(self):
        args = self._verify_codex_args()
        absent = subprocess.CompletedProcess(
            ["npm"], 1, stdout=json.dumps({"error": {"code": "E404"}}),
            stderr="npm error E404",
        )
        unavailable = subprocess.CompletedProcess(
            ["npm"], 1, stdout=json.dumps({"error": {"code": "E503"}}),
            stderr="npm error E503",
        )
        with mock.patch.object(NPM, "validate_release_source_binding"), \
             mock.patch.object(NPM, "registry_lookup", return_value=absent) as lookup:
            with self.assertRaisesRegex(ValueError, "did not become observable"):
                NPM.verify_codex(args)
            self.assertEqual(2, lookup.call_count)
        with mock.patch.object(NPM, "validate_release_source_binding"), \
             mock.patch.object(NPM, "registry_lookup", return_value=unavailable) as lookup:
            with self.assertRaises(NPM.RegistryUnavailable):
                NPM.verify_codex(args)
            self.assertEqual(2, lookup.call_count)

    def test_codex_verify_rejects_invalid_bounds_version_and_provenance(self):
        with self.assertRaisesRegex(ValueError, "version"):
            NPM.verify_codex(self._verify_codex_args(version="latest"))
        for override in (
            {"attempts": 0}, {"delay_seconds": -1}, {"readback_seconds": 0},
        ):
            with self.subTest(override=override):
                with mock.patch.object(NPM, "validate_release_source_binding"):
                    with self.assertRaisesRegex(ValueError, "bounds"):
                        NPM.verify_codex(self._verify_codex_args(**override))
        args = self._verify_codex_args()
        with mock.patch.object(NPM, "validate_release_source_binding"), \
             mock.patch.object(NPM, "registry_lookup", return_value=self._present_codex_lookup(args)) as lookup, \
             mock.patch.object(NPM, "verify_registry_authenticity", return_value={}), \
             mock.patch.object(
                 NPM, "validate_publication_attestation",
                 side_effect=ValueError("provenance mismatch"),
             ):
            with self.assertRaisesRegex(ValueError, "provenance mismatch"):
                NPM.verify_codex(args)
            self.assertEqual(1, lookup.call_count)

    def test_promoted_catalog_pins_npm_source_to_exact_verified_version(self):
        promoted = json.loads(PACKAGER.promoted_codex_catalog(
            self.catalog,
            package="@arbiterforge/ca-codex",
            version="9.8.7",
            registry="https://registry.npmjs.org",
        ))
        source = promoted["plugins"][0]["source"]
        self.assertEqual({
            "source": "npm",
            "package": "@arbiterforge/ca-codex",
            "version": "9.8.7",
            "registry": "https://registry.npmjs.org",
        }, source)
        with self.assertRaisesRegex(ValueError, "version"):
            PACKAGER.promoted_codex_catalog(
                self.catalog,
                package="@arbiterforge/ca-codex",
                version="latest",
                registry="https://registry.npmjs.org",
            )

    def test_rejects_substituted_package_cohort_receipt(self):
        with self.assertRaisesRegex(ValueError, "cohort digest"):
            PACKAGER.stage_codex_marketplace_distribution(
                package_root=self.package_root,
                package_cohort_sha256="0" * 64,
                output=self.root / "distribution-wrong-cohort",
            )
        self.assertFalse((self.root / "distribution-wrong-cohort").exists())

    def test_git_promotion_is_ordered_immutable_and_fail_closed(self):
        remote = self.root / "remote.git"
        git_run(["git", "init", "--bare", str(remote)], check=True,
                       capture_output=True)

        # Qualification failure is observed before either remote ref can exist.
        with self.assertRaisesRegex(ValueError, "cohort digest"):
            PROMOTER.promote(
                package_root=self.package_root, cohort_sha256="0" * 64,
                source_repo=self.source, source_commit=self.source_commit,
                remote_url=str(remote),
                catalog_url="https://github.com/arbiterForge/codeArbiter.git",
                version="9.8.7", work=self.root / "failed", push=True,
            )
        self.assertEqual("", git_run(
            ["git", "--git-dir", str(remote), "show-ref"], check=False,
            capture_output=True, text=True, encoding="utf-8",
        ).stdout)

        staged = PROMOTER.promote(
            package_root=self.package_root, cohort_sha256=self.receipt_sha256,
            source_repo=self.source, source_commit=self.source_commit,
            remote_url=str(remote),
            catalog_url="https://github.com/arbiterForge/codeArbiter.git",
            version="9.8.7", work=self.root / "promoted", push=True,
        )
        refs = git_run(
            ["git", "--git-dir", str(remote), "show-ref"], check=True,
            capture_output=True, text=True, encoding="utf-8",
        ).stdout
        self.assertIn(staged["distribution_commit"], refs)
        self.assertNotIn("refs/heads/ca-codex-marketplace", refs)
        result = PROMOTER.promote(
            package_root=self.package_root, cohort_sha256=self.receipt_sha256,
            source_repo=self.source, source_commit=self.source_commit,
            remote_url=str(remote), catalog_url="https://github.com/arbiterForge/codeArbiter.git",
            version="9.8.7", work=self.root / "advanced", push=True,
            advance_channel=True, expected_marketplace_head=None,
            expected_npm_integrity=staged["npm_integrity"],
            expected_npm_sha256=staged["npm_sha256"],
        )
        refs = git_run(["git","--git-dir",str(remote),"show-ref"],check=True,
            capture_output=True,text=True,encoding="utf-8").stdout
        self.assertIn(result["marketplace_commit"], refs)
        catalog = json.loads(git_run([
            "git", "--git-dir", str(remote), "show",
            f'{result["marketplace_commit"]}:.agents/plugins/marketplace.json',
        ], check=True, capture_output=True, text=True, encoding="utf-8").stdout)
        self.assertEqual({
            "source": "npm",
            "package": "@arbiterforge/ca-codex",
            "version": "9.8.7",
            "registry": "https://registry.npmjs.org",
        }, catalog["plugins"][0]["source"])
        ledger = json.loads(git_run([
            "git", "--git-dir", str(remote), "show",
            f'{result["marketplace_commit"]}:{PROMOTER.LEDGER_PATH}',
        ], check=True, capture_output=True, text=True, encoding="utf-8").stdout)
        record = ledger["tags"][result["distribution_ref"]]
        self.assertEqual(result["distribution_commit"], record["commit"])
        self.assertEqual(self.source_commit, record["source_commit"])
        self.assertEqual(self.receipt_sha256, record["cohort_sha256"])
        self.assertEqual(result["npm_sha256"], record["npm_sha256"])
        self.assertEqual(result["npm_integrity"], record["npm_integrity"])
        retry = PROMOTER.promote(
            package_root=self.package_root, cohort_sha256=self.receipt_sha256,
            source_repo=self.source, source_commit=self.source_commit,
            remote_url=str(remote),
            catalog_url="https://github.com/arbiterForge/codeArbiter.git",
            version="9.8.7", work=self.root / "retry", push=True, advance_channel=True,
            expected_marketplace_head=result["marketplace_commit"],
            expected_npm_integrity=result["npm_integrity"],
            expected_npm_sha256=result["npm_sha256"],
        )
        self.assertEqual(result["distribution_commit"], retry["distribution_commit"])
        self.assertEqual(result["marketplace_commit"], retry["marketplace_commit"])

        older = dict(self.members)
        older["plugins/ca-codex/.codex-plugin/plugin.json"] = b'{"name":"ca-codex","version":"9.8.6"}\n'
        older["plugins/ca-codex/package.json"] = older["plugins/ca-codex/package.json"].replace(
            b'"version":"9.8.7"', b'"version":"9.8.6"'
        )
        self._write_package(older)
        older_staged = PROMOTER.promote(
            package_root=self.package_root, cohort_sha256=self.receipt_sha256,
            source_repo=self.source, source_commit=self.source_commit,
            remote_url=str(remote), catalog_url="https://github.com/arbiterForge/codeArbiter.git",
            version="9.8.6", work=self.root / "rollback-tag", push=True,
        )
        with self.assertRaisesRegex(ValueError, "cannot roll back"):
            PROMOTER.promote(
                package_root=self.package_root, cohort_sha256=self.receipt_sha256,
                source_repo=self.source, source_commit=self.source_commit,
                remote_url=str(remote), catalog_url="https://github.com/arbiterForge/codeArbiter.git",
                version="9.8.6", work=self.root / "rollback", push=True,
                advance_channel=True, expected_marketplace_head=result["marketplace_commit"],
                expected_npm_integrity=older_staged["npm_integrity"],
                expected_npm_sha256=older_staged["npm_sha256"],
            )
        after_rollback = git_run(
            ["git", "--git-dir", str(remote), "show-ref"], check=True,
            capture_output=True, text=True, encoding="utf-8",
        ).stdout
        self.assertIn(
            f'{result["marketplace_commit"]} refs/heads/ca-codex-marketplace',
            after_rollback,
        )
        self.assertIn("refs/tags/ca-codex-dist-v9.8.6", after_rollback)

        changed = dict(self.members)
        changed["plugins/ca-codex/hooks/bridge.py"] = b"different bytes\n"
        self._write_package(changed)
        with self.assertRaisesRegex(ValueError, "same-version"):
            PROMOTER.promote(
                package_root=self.package_root, cohort_sha256=self.receipt_sha256,
                source_repo=self.source, source_commit=self.source_commit,
                remote_url=str(remote),
                catalog_url="https://github.com/arbiterForge/codeArbiter.git",
                version="9.8.7", work=self.root / "replacement", push=True,
            )
        after = git_run(
            ["git", "--git-dir", str(remote), "show-ref"], check=True,
            capture_output=True, text=True, encoding="utf-8",
        ).stdout
        self.assertEqual(after_rollback, after)

    def test_release_action_stages_before_and_advances_only_after_finalize(self):
        action = (REPO / ".github/actions/publish-release/action.yml").read_text(
            encoding="utf-8"
        )
        verify = action.index("Reverify exact retained package cohort before publication")
        rulesets = action.index("Verify live Codex distribution rulesets")
        cold_receipt = action.index("Retain immutable durable cohort receipt on the Release")
        stage = action.index("Stage immutable qualified Codex distribution tag")
        prepare_npm = action.index("Prepare exact qualified Codex npm package")
        auth_npm = action.index("Configure authenticated npm scope for exact qualified Codex package")
        publish_npm = action.index("Publish exact qualified Codex npm package from authenticated scope")
        verify_npm = action.index("Verify Codex npm integrity and provenance readback")
        cold_npm = action.index("Cold-install exact Codex npm package through a real marketplace")
        finalize = action.index("Publish qualified Release only after receipt readback")
        reverify = action.index("Reverify live Codex distribution rulesets before channel advance")
        advance = action.index("Advance protected Codex marketplace channel")
        self.assertLess(verify, cold_receipt)
        self.assertLess(cold_receipt, stage)
        self.assertLess(rulesets, stage)
        self.assertLess(stage, prepare_npm)
        self.assertLess(prepare_npm, auth_npm)
        self.assertLess(auth_npm, publish_npm)
        self.assertLess(publish_npm, verify_npm)
        self.assertLess(verify_npm, cold_npm)
        self.assertLess(cold_npm, finalize)
        self.assertLess(stage, finalize)
        self.assertLess(finalize, reverify)
        self.assertLess(reverify, advance)
        block = action[stage:finalize]
        self.assertIn("inputs.package-host == 'codex'", block)
        self.assertIn("--cohort-sha256 \"$COHORT_SHA256\"", block)
        self.assertIn("--push", block)
        self.assertNotIn("--advance-channel", block)
        channel_block = action[advance:]
        self.assertIn("--advance-channel", channel_block)
        self.assertNotIn("codex-ruleset-verifier-token", channel_block)
        self.assertNotIn("verify_codex_distribution_rulesets.py", channel_block)
        reverify_block = action[reverify:advance]
        self.assertIn("verify_codex_distribution_rulesets.py", reverify_block)
        self.assertIn("inputs.codex-ruleset-verifier-token", reverify_block)
        self.assertNotIn("inputs.github-token", reverify_block)
        self.assertNotIn("promote-codex-marketplace.py", reverify_block)
        self.assertIn("git remote get-url origin", action)
        self.assertIn("--remote-url \"$REMOTE_URL\"", action)
        auth_block = action[auth_npm:publish_npm]
        self.assertIn("actions/setup-node@820762786026740c76f36085b0efc47a31fe5020", auth_block)
        self.assertIn("registry-url: https://registry.npmjs.org", auth_block)
        self.assertIn("scope: '@arbiterforge'", auth_block)
        publish_block = action[publish_npm:verify_npm]
        self.assertIn("NODE_AUTH_TOKEN: ${{ inputs.npm-token }}", publish_block)
        self.assertIn("--registry=https://registry.npmjs.org/", publish_block)
        cold_block = action[cold_npm:finalize]
        self.assertIn("for CODEX_VERSION in 0.143.0 0.145.0", cold_block)
        self.assertIn('"@openai/codex@$CODEX_VERSION"', cold_block)
        self.assertIn("--npm-marketplace-version \"$VERSION\"", cold_block)
        self.assertIn("--qualified-npm-metadata \"$NPM_METADATA\"", cold_block)
        self.assertIn("NPM_METADATA: ${{ steps.codex-npm.outputs.metadata }}", cold_block)
        self.assertIn("--require-artifact-capability", cold_block)
        self.assertIn("NPM_CONFIG_USERCONFIG:", cold_block)
        self.assertNotIn("NODE_AUTH_TOKEN", cold_block)

    def test_competing_marketplace_update_wins_and_expected_head_lease_fails(self):
        remote = self.root / "race.git"
        git_run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
        current_staged = PROMOTER.promote(
            package_root=self.package_root, cohort_sha256=self.receipt_sha256,
            source_repo=self.source, source_commit=self.source_commit,
            remote_url=str(remote), catalog_url="https://github.com/arbiterForge/codeArbiter.git",
            version="9.8.7", work=self.root / "race-current-tag", push=True,
        )
        current = PROMOTER.promote(
            package_root=self.package_root, cohort_sha256=self.receipt_sha256,
            source_repo=self.source, source_commit=self.source_commit,
            remote_url=str(remote), catalog_url="https://github.com/arbiterForge/codeArbiter.git",
            version="9.8.7", work=self.root / "race-current-channel", push=True,
            advance_channel=True,
            expected_npm_integrity=current_staged["npm_integrity"],
            expected_npm_sha256=current_staged["npm_sha256"],
        )
        newer = dict(self.members)
        newer["plugins/ca-codex/.codex-plugin/plugin.json"] = b'{"name":"ca-codex","version":"9.8.8"}\n'
        newer["plugins/ca-codex/package.json"] = newer["plugins/ca-codex/package.json"].replace(
            b'"version":"9.8.7"', b'"version":"9.8.8"'
        )
        self._write_package(newer)
        newer_staged = PROMOTER.promote(
            package_root=self.package_root, cohort_sha256=self.receipt_sha256,
            source_repo=self.source, source_commit=self.source_commit,
            remote_url=str(remote), catalog_url="https://github.com/arbiterForge/codeArbiter.git",
            version="9.8.8", work=self.root / "race-new-tag", push=True,
        )
        real_git = PROMOTER._git
        competitor_head = None

        def racing_git(repo, *args, **kwargs):
            nonlocal competitor_head
            if args and args[0] == "push" and str(args[-1]).endswith(PROMOTER.MARKETPLACE_REF):
                competitor = self.root / "competitor"
                git_run(["git", "clone", "--quiet", str(remote), str(competitor)], check=True)
                git_run(["git", "-C", str(competitor), "checkout", "--quiet", "ca-codex-marketplace"], check=True)
                git_run(["git", "-C", str(competitor), "config", "user.email", "race@example.invalid"], check=True)
                git_run(["git", "-C", str(competitor), "config", "user.name", "Race"], check=True)
                (competitor / "competitor.txt").write_text("wins\n", encoding="utf-8")
                git_run(["git", "-C", str(competitor), "add", "competitor.txt"], check=True)
                git_run(["git", "-C", str(competitor), "commit", "--quiet", "-m", "competing update"], check=True)
                competitor_head = git_run(
                    ["git", "-C", str(competitor), "rev-parse", "HEAD"], check=True,
                    capture_output=True, text=True, encoding="utf-8",
                ).stdout.strip()
                git_run(["git", "-C", str(competitor), "push", "--quiet", "origin", "HEAD:refs/heads/ca-codex-marketplace"], check=True)
            return real_git(repo, *args, **kwargs)

        with mock.patch.object(PROMOTER, "_git", side_effect=racing_git):
            with self.assertRaises(subprocess.CalledProcessError):
                PROMOTER.promote(
                    package_root=self.package_root, cohort_sha256=self.receipt_sha256,
                    source_repo=self.source, source_commit=self.source_commit,
                    remote_url=str(remote), catalog_url="https://github.com/arbiterForge/codeArbiter.git",
                    version="9.8.8", work=self.root / "race-channel", push=True,
                    advance_channel=True, expected_marketplace_head=current["marketplace_commit"],
                    expected_npm_integrity=newer_staged["npm_integrity"],
                    expected_npm_sha256=newer_staged["npm_sha256"],
                )
        observed = git_run(
            ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/ca-codex-marketplace"],
            check=True, capture_output=True, text=True, encoding="utf-8",
        ).stdout.strip()
        self.assertEqual(competitor_head, observed)

    def test_live_ruleset_contract_rejects_missing_controls_or_open_bypass(self):
        policy = json.loads((REPO / ".github/codex-distribution-policy.json").read_text())
        live = []
        publisher_actor_id = 424242
        for requirement in policy["rulesets"]:
            publisher = dict(requirement["publisher"])
            publisher.pop("actor_id_source")
            publisher["actor_id"] = publisher_actor_id
            live.append({
                "name": requirement["name"], "target": requirement["target"],
                "enforcement": "active",
                "conditions": {"ref_name": {"include": requirement["include"], "exclude": []}},
                "rules": [{"type": name} for name in requirement["rules"]],
                "bypass_actors": [publisher],
            })
        verifier_actor_id = 434343
        RULESETS.verify(policy, live, publisher_actor_id, verifier_actor_id)
        for label, mutate in {
            "inactive": lambda rows: rows[0].update(enforcement="evaluate"),
            "missing force-push guard": lambda rows: rows[0].update(rules=[{"type": "deletion"}, {"type": "update"}]),
            "open publisher": lambda rows: rows[0].update(bypass_actors=[]),
        }.items():
            with self.subTest(label=label):
                candidate = json.loads(json.dumps(live))
                mutate(candidate)
                with self.assertRaises(ValueError):
                    RULESETS.verify(policy, candidate, publisher_actor_id, verifier_actor_id)
        with self.assertRaisesRegex(ValueError, "general Actions"):
            RULESETS.verify(policy, live, 15368, verifier_actor_id)
        with self.assertRaisesRegex(ValueError, "must be distinct"):
            RULESETS.verify(policy, live, publisher_actor_id, publisher_actor_id)

    def test_catalog_comes_from_exact_source_object_not_mutable_checkout(self):
        (self.source / ".agents/plugins/marketplace.json").write_text("{}\n")
        remote = self.root / "source-object.git"
        git_run(["git","init","--bare",str(remote)],check=True,capture_output=True)
        result = PROMOTER.promote(package_root=self.package_root,cohort_sha256=self.receipt_sha256,
            source_repo=self.source,source_commit=self.source_commit,remote_url=str(remote),
            catalog_url="https://github.com/arbiterForge/codeArbiter.git",version="9.8.7",
            work=self.root/"source-object",push=True)
        self.assertEqual(hashlib.sha256(self.catalog).hexdigest(), result["catalog_sha256"])

    def test_distribution_contract_is_wired_into_required_ci(self):
        ci = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python .github/scripts/test_codex_marketplace_distribution.py", ci)

    def test_source_controlled_ref_protection_contract_is_complete(self):
        policy = json.loads((REPO / ".github/codex-distribution-policy.json").read_text())
        self.assertEqual("ca-codex-marketplace", policy["marketplace_branch"])
        self.assertEqual("ca-codex-dist-v*", policy["distribution_tag_pattern"])
        self.assertEqual(PROMOTER.LEDGER_PATH, policy["distribution_ledger"])
        self.assertEqual({
            "branch_deletion": False, "branch_force_push": False,
            "tag_deletion": False, "tag_update": False,
            "restricted_publisher": True, "expected_head_lease": True,
        }, policy["required_controls"])
        docs = (REPO / ".github/CODEX_DISTRIBUTION.md").read_text()
        self.assertRegex(docs, r"reject creation, deletion, and update of\s+`ca-codex-dist-v\*`")
        self.assertRegex(docs, r"reject deletion, update, and force-push of\s+`ca-codex-marketplace`")
        self.assertIn("not\nevidence that the remote rules", docs)
        self.assertIn("fails closed", docs)
        self.assertIn("expected-head lease", docs)
        self.assertIn("dedicated GitHub App", docs)
        self.assertIn("separate verifier", docs)
        self.assertIn("must not\n  be a bypass actor", docs)
        release = (REPO / ".github/workflows/release.yml").read_text()
        self.assertIn("environment: codex-distribution", release)
        self.assertIn("create_codex_distribution_token.py", release)
        self.assertIn("github-token: ${{ steps.codex-publisher.outputs.token }}", release)
        self.assertIn("codex-ruleset-verifier-token: ${{ steps.codex-ruleset-verifier.outputs.token }}", release)
        self.assertIn("codex-ruleset-verifier-actor-id: ${{ secrets.CODEX_RULESET_VERIFIER_APP_ID }}", release)
        self.assertIn("CODEX_RULESET_VERIFIER_APP_PRIVATE_KEY", release)
        self.assertEqual(4, release.count("umask 077"))
        manual = release.split("  release-codex:", 1)[1].split("\n  release-sandbox:", 1)[0]
        automatic = release.split("  auto-release-codex:", 1)[1].split("\n  auto-codex-cohort-gate:", 1)[0]
        for block in (manual, automatic):
            self.assertIn("id-token: write", block)
            self.assertIn("npm-token: ${{ secrets.NPMJS_TOKEN }}", block)
        security = (REPO / ".codearbiter/security-controls.md").read_text()
        self.assertIn("first `@arbiterforge/ca-codex` publication", security)
        self.assertIn("available to all organization repositories", security)
        self.assertIn("npm privilege scope", security)
        self.assertIn("only in the authenticated publish step", security)
        self.assertIn("token-free npm configuration", security)

    def test_public_codex_install_uses_promoted_marketplace_ref(self):
        command = (
            "codex plugin marketplace add arbiterForge/codeArbiter "
            "--ref ca-codex-marketplace"
        )
        for relative in (
            "README.md",
            "site/src/content/docs/getting-started/claude-code-and-codex.md",
            "site/src/content/docs/getting-started/install.md",
        ):
            with self.subTest(path=relative):
                self.assertIn(command, (REPO / relative).read_text(encoding="utf-8"))

        readme = (REPO / "README.md").read_text(encoding="utf-8")
        self.assertIn("exact verified `@arbiterforge/ca-codex` npm version", readme)
        self.assertIn("codex plugin remove ca-codex@codearbiter", readme)
        self.assertIn("codex plugin marketplace remove codearbiter", readme)
        self.assertIn("does not migrate it to the npm-backed channel", readme)


if __name__ == "__main__":
    unittest.main(verbosity=2)

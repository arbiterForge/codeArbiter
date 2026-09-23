#!/usr/bin/env python3
"""Contracts for promoting the qualified Codex archive as a Git distribution tree."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import subprocess
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
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
        subprocess.run(["git", "init", "--quiet"], cwd=self.source, check=True)
        subprocess.run(["git", "add", "."], cwd=self.source, check=True)
        environment = {**__import__("os").environ, "GIT_AUTHOR_NAME":"test",
            "GIT_AUTHOR_EMAIL":"test@example.invalid","GIT_COMMITTER_NAME":"test",
            "GIT_COMMITTER_EMAIL":"test@example.invalid"}
        subprocess.run(["git", "commit", "--quiet", "-m", "source"], cwd=self.source,
                       env=environment, check=True)
        self.source_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.source,
            check=True, capture_output=True, text=True).stdout.strip()
        release = b'{"format":"codearbiter.artifact-release/0.1.0"}\n'
        binary = b"qualified-native-binary"
        self.members = {
            ".agents/plugins/marketplace.json": self.catalog,
            "plugins/ca-codex/.codex-plugin/plugin.json": (
                b'{"name":"ca-codex","version":"9.8.7"}\n'
            ),
            "plugins/ca-codex/hooks/bridge.py": b"print('bridge')\n",
            "plugins/ca-codex/helpers/artifacts/release.json": release,
            "plugins/ca-codex/helpers/artifacts/ca-artifact-linux-amd64": binary,
        }
        self.archive = self.package_root / "codearbiter-ca-codex-9.8.7.tar.gz"
        self._write_package(self.members)

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

    def test_promoted_catalog_pins_git_source_to_exact_commit_and_ref(self):
        commit = "7" * 40
        promoted = json.loads(PACKAGER.promoted_codex_catalog(
            self.catalog,
            distribution_url="https://github.com/arbiterForge/codeArbiter.git",
            distribution_ref="refs/tags/ca-codex-dist-v9.8.7",
            distribution_commit=commit,
        ))
        source = promoted["plugins"][0]["source"]
        self.assertEqual({
            "source": "git-subdir",
            "url": "https://github.com/arbiterForge/codeArbiter.git",
            "path": "plugins/ca-codex",
            "ref": "refs/tags/ca-codex-dist-v9.8.7",
            "sha": commit,
        }, source)
        with self.assertRaisesRegex(ValueError, "commit"):
            PACKAGER.promoted_codex_catalog(
                self.catalog,
                distribution_url="https://github.com/arbiterForge/codeArbiter.git",
                distribution_ref="refs/tags/ca-codex-dist-v9.8.7",
                distribution_commit="main",
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
        subprocess.run(["git", "init", "--bare", str(remote)], check=True,
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
        self.assertEqual("", subprocess.run(
            ["git", "--git-dir", str(remote), "show-ref"], check=False,
            capture_output=True, text=True, encoding="utf-8",
        ).stdout)

        result = PROMOTER.promote(
            package_root=self.package_root, cohort_sha256=self.receipt_sha256,
            source_repo=self.source, source_commit=self.source_commit,
            remote_url=str(remote),
            catalog_url="https://github.com/arbiterForge/codeArbiter.git",
            version="9.8.7", work=self.root / "promoted", push=True,
        )
        refs = subprocess.run(
            ["git", "--git-dir", str(remote), "show-ref"], check=True,
            capture_output=True, text=True, encoding="utf-8",
        ).stdout
        self.assertIn(result["distribution_commit"], refs)
        self.assertNotIn("refs/heads/ca-codex-marketplace", refs)
        result = PROMOTER.promote(
            package_root=self.package_root, cohort_sha256=self.receipt_sha256,
            source_repo=self.source, source_commit=self.source_commit,
            remote_url=str(remote), catalog_url="https://github.com/arbiterForge/codeArbiter.git",
            version="9.8.7", work=self.root / "advanced", push=True,
            advance_channel=True, expected_marketplace_head=None,
        )
        refs = subprocess.run(["git","--git-dir",str(remote),"show-ref"],check=True,
            capture_output=True,text=True,encoding="utf-8").stdout
        self.assertIn(result["marketplace_commit"], refs)
        catalog = json.loads(subprocess.run([
            "git", "--git-dir", str(remote), "show",
            f'{result["marketplace_commit"]}:.agents/plugins/marketplace.json',
        ], check=True, capture_output=True, text=True, encoding="utf-8").stdout)
        self.assertEqual(
            result["distribution_commit"], catalog["plugins"][0]["source"]["sha"]
        )
        ledger = json.loads(subprocess.run([
            "git", "--git-dir", str(remote), "show",
            f'{result["marketplace_commit"]}:{PROMOTER.LEDGER_PATH}',
        ], check=True, capture_output=True, text=True, encoding="utf-8").stdout)
        record = ledger["tags"][result["distribution_ref"]]
        self.assertEqual(result["distribution_commit"], record["commit"])
        self.assertEqual(self.source_commit, record["source_commit"])
        self.assertEqual(self.receipt_sha256, record["cohort_sha256"])
        retry = PROMOTER.promote(
            package_root=self.package_root, cohort_sha256=self.receipt_sha256,
            source_repo=self.source, source_commit=self.source_commit,
            remote_url=str(remote),
            catalog_url="https://github.com/arbiterForge/codeArbiter.git",
            version="9.8.7", work=self.root / "retry", push=True, advance_channel=True,
            expected_marketplace_head=result["marketplace_commit"],
        )
        self.assertEqual(result["distribution_commit"], retry["distribution_commit"])
        self.assertEqual(result["marketplace_commit"], retry["marketplace_commit"])

        older = dict(self.members)
        older["plugins/ca-codex/.codex-plugin/plugin.json"] = b'{"name":"ca-codex","version":"9.8.6"}\n'
        self._write_package(older)
        PROMOTER.promote(
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
            )
        after_rollback = subprocess.run(
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
        after = subprocess.run(
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
        finalize = action.index("Publish qualified Release only after receipt readback")
        reverify = action.index("Reverify live Codex distribution rulesets before channel advance")
        advance = action.index("Advance protected Codex marketplace channel")
        self.assertLess(verify, cold_receipt)
        self.assertLess(cold_receipt, stage)
        self.assertLess(rulesets, stage)
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

    def test_competing_marketplace_update_wins_and_expected_head_lease_fails(self):
        remote = self.root / "race.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
        current = PROMOTER.promote(
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
        )
        newer = dict(self.members)
        newer["plugins/ca-codex/.codex-plugin/plugin.json"] = b'{"name":"ca-codex","version":"9.8.8"}\n'
        self._write_package(newer)
        PROMOTER.promote(
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
                subprocess.run(["git", "clone", "--quiet", str(remote), str(competitor)], check=True)
                subprocess.run(["git", "-C", str(competitor), "checkout", "--quiet", "ca-codex-marketplace"], check=True)
                subprocess.run(["git", "-C", str(competitor), "config", "user.email", "race@example.invalid"], check=True)
                subprocess.run(["git", "-C", str(competitor), "config", "user.name", "Race"], check=True)
                (competitor / "competitor.txt").write_text("wins\n", encoding="utf-8")
                subprocess.run(["git", "-C", str(competitor), "add", "competitor.txt"], check=True)
                subprocess.run(["git", "-C", str(competitor), "commit", "--quiet", "-m", "competing update"], check=True)
                competitor_head = subprocess.run(
                    ["git", "-C", str(competitor), "rev-parse", "HEAD"], check=True,
                    capture_output=True, text=True, encoding="utf-8",
                ).stdout.strip()
                subprocess.run(["git", "-C", str(competitor), "push", "--quiet", "origin", "HEAD:refs/heads/ca-codex-marketplace"], check=True)
            return real_git(repo, *args, **kwargs)

        with mock.patch.object(PROMOTER, "_git", side_effect=racing_git):
            with self.assertRaises(subprocess.CalledProcessError):
                PROMOTER.promote(
                    package_root=self.package_root, cohort_sha256=self.receipt_sha256,
                    source_repo=self.source, source_commit=self.source_commit,
                    remote_url=str(remote), catalog_url="https://github.com/arbiterForge/codeArbiter.git",
                    version="9.8.8", work=self.root / "race-channel", push=True,
                    advance_channel=True, expected_marketplace_head=current["marketplace_commit"],
                )
        observed = subprocess.run(
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
        subprocess.run(["git","init","--bare",str(remote)],check=True,capture_output=True)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)

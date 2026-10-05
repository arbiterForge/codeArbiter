#!/usr/bin/env python3
"""T-02 behavior: AC-10/11 host profiles, AC-12/13 inert inventory, AC-37.

The missing-module baseline returns no observations so a new feature has an
assertion RED, rather than a runner/import error. Once present, only canonical
core code is loaded; failures in that code are never replaced by the baseline.
"""

import html
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


CORE = Path(__file__).resolve().parents[4] / "core" / "pysrc"
sys.path.insert(0, str(CORE))
MODULE_PATH = CORE / "_tribunalinventorylib.py"
INVENTORY = None
if MODULE_PATH.exists():
    SPEC = importlib.util.spec_from_file_location("_tribunalinventory_under_test", MODULE_PATH)
    INVENTORY = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(INVENTORY)


def subject(name, *args, **kwargs):
    if INVENTORY is None:
        return "" if name.endswith(("_json", "_md")) else {}
    return getattr(INVENTORY, name)(*args, **kwargs)


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.git("init", "-q")

    def git(self, *args, data=None):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("GIT_")}
        env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_TERMINAL_PROMPT": "0"})
        result = subprocess.run(
            ["git", "-C", str(self.root), "-c", "user.name=Inventory fixture",
             "-c", "user.email=inventory@example.invalid", *args],
            capture_output=True, env=env, check=True, input=data,
        )
        return result.stdout

    def write(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, dict):
            data = json.dumps(data)
        target.write_text(data, encoding="utf-8", newline="\n")

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")

    def collect(self, **kwargs):
        return subject("collect_inventory", self.root, **kwargs)

    def test_ac12_tracked_sizes_languages_manifests_and_metadata(self):
        self.write("package.json", {"name": "sample", "version": "1.2.3",
                                  "private": True, "license": "MIT"})
        self.write("src/app.py", "answer = 42\n")
        self.write("package-lock.json", {"lockfileVersion": 3})
        self.commit()
        self.write("untracked.py", "untracked = True\n")
        result = self.collect()
        files = {row["path"]: row for row in result.get("files", [])}
        self.assertEqual(sorted(files), ["package-lock.json", "package.json", "src/app.py"])
        self.assertEqual(files["src/app.py"]["bytes"], 12)
        self.assertEqual(files["src/app.py"]["language"], "Python")
        self.assertIn("package-lock.json", result["lockfiles"])
        self.assertEqual(result["package_metadata"][0]["name"], "sample")
        self.assertEqual(result["package_metadata"][0]["version"], "1.2.3")
        self.assertEqual(result["judgment"], "not-performed")

    def test_ac12_direct_dependencies_and_declared_entry_points(self):
        self.write("package.json", {"name": "sample", "source": "src/index.ts",
                                  "main": "dist/index.js", "bin": {"sample": "bin/cli.js"},
                                  "dependencies": {"runtime": "^2"},
                                  "devDependencies": {"runner": "3.1"}})
        self.write("src/index.ts", "export const value = 1;\n")
        self.write("bin/cli.js", "void 0;\n")
        self.commit()
        result = self.collect()
        dependencies = {(row["name"], row["version"], row["group"])
                        for row in result.get("dependencies", [])}
        self.assertEqual(dependencies, {("runtime", "^2", "dependencies"),
                                        ("runner", "3.1", "devDependencies")})
        self.assertTrue(any(row["path"] == "bin/cli.js" for row in result["entry_points"]))
        self.assertIn({"declared_in": "package.json", "source": "src/index.ts",
                       "outputs": ["dist/index.js"], "basis": "package-source-output"},
                      result["generated_relationships"])

    def test_ac12_python_rust_go_and_composer_inert_manifest_parsing(self):
        self.write("pyproject.toml", '[project]\nname = "python-sample"\nversion = "1"\n'
                   'dependencies = ["requests>=2", "local-tool[extra]==3; python_version >= \'3.10\'"]\n'
                   '[project.scripts]\ncli = "pkg.main:run"\n')
        self.write("Cargo.toml", '[package]\nname = "rust-sample"\nversion = "1.0.0"\n'
                   '[dependencies]\nserde = "1"\nhelper = {path = "../helper"}\n')
        self.write("go.mod", 'module example.invalid/sample\n\nrequire (\n'
                   'example.invalid/direct v1.2.3\nexample.invalid/transitive v2.0.0 // indirect\n)\n')
        self.write("composer.json", {"name": "sample/php", "require": {"php": "^8.2"}})
        self.commit()
        result = self.collect()
        names = {row["name"] for row in result.get("dependencies", [])}
        expected = {"example.invalid/direct", "php"}
        if sys.version_info >= (3, 11):
            expected.update({"requests", "local-tool", "serde", "helper"})
        self.assertEqual(names, expected)
        self.assertNotIn("example.invalid/transitive", names)
        if sys.version_info >= (3, 11):
            helper = next(row for row in result["dependencies"] if row["name"] == "helper")
            self.assertIsNone(helper["version"])
            self.assertEqual(helper["version_status"], "not-declared")

    def test_ac12_requirements_unsupported_and_malformed_stay_explicit(self):
        self.write("requirements.txt", "alpha==1.2\nbeta>=2; python_version > '3'\n-r other.txt\n")
        self.write("package.json", "{not-json")
        self.write("setup.py", "raise RuntimeError('never execute')\n")
        self.commit()
        result = self.collect()
        names = {row["name"] for row in result.get("dependencies", [])}
        self.assertEqual(names, {"alpha", "beta"})
        unavailable = result["unavailable"]
        self.assertTrue(any(row.get("path") == "package.json" and
                            row["reason"] == "malformed-manifest" for row in unavailable))
        self.assertTrue(any(row.get("path") == "setup.py" and
                            row["reason"] == "unsupported-format" for row in unavailable))
        self.assertTrue(any(row["field"] == "import_call_graph" for row in unavailable))
        self.assertTrue(any(row.get("path") == "requirements.txt" for row in unavailable))

    def test_ac12_source_test_ci_release_config_and_generation_facts(self):
        self.write("src/widget.py", "x = 1\n")
        self.write("tests/test_widget.py", "assert True\n")
        self.write(".github/workflows/release.yml", "name: release\n")
        self.write("deploy/Dockerfile", "FROM scratch\n")
        self.write("tsconfig.json", {"compilerOptions": {"rootDir": "src", "outDir": "dist"}})
        self.commit()
        result = self.collect()
        self.assertIn({"test": "tests/test_widget.py", "source": "src/widget.py",
                       "basis": "filename-convention"}, result.get("test_source_relationships", []))
        self.assertIn(".github/workflows/release.yml", result["surfaces"]["ci"])
        self.assertIn(".github/workflows/release.yml", result["surfaces"]["release"])
        self.assertIn("deploy/Dockerfile", result["surfaces"]["deploy"])
        self.assertIn("tsconfig.json", result["surfaces"]["config"])
        self.assertIn({"declared_in": "tsconfig.json", "source": "src", "outputs": ["dist"],
                       "basis": "compiler-root-out-dir"}, result["generated_relationships"])

    def test_ac12_declared_host_surface_rules_are_inventoried_without_running_generators(self):
        self.write("core/hosts.json", {"hosts": [{"name": "example", "plugin_dir": "plugins/example",
                   "surface": {"rules": [{"source_prefix": "commands/", "output_pattern": "skills/{relative}/SKILL.md",
                                          "exclude": ["commands/legacy.md"]}]}}]})
        self.write("core/surface/commands/example.md", "# Example\n")
        self.commit()
        result = self.collect()
        self.assertIn({"declared_in": "core/hosts.json", "source": "core/surface/commands",
                       "outputs": ["plugins/example/skills/{relative}/SKILL.md"],
                       "excludes": ["commands/legacy.md"], "basis": "host-surface-rule"},
                      result["generated_relationships"])

    def test_ac12_dirty_paths_churn_and_scope_are_actual_git_facts(self):
        self.write("src/app.py", "x = 1\n")
        self.write("other/app.py", "x = 1\n")
        self.commit()
        self.write("src/app.py", "x = 2\n")
        self.commit()
        self.write("src/app.py", "x = 3\n")
        self.write("src/new.py", "new = True\n")
        self.write("other/app.py", "x = 3\n")
        result = self.collect(scope="src")
        self.assertEqual([row["path"] for row in result.get("files", [])], ["src/app.py"])
        self.assertEqual({row["path"] for row in result["git"]["dirty_paths"]},
                         {"src/app.py", "src/new.py"})
        self.assertEqual(result["git"]["churn"]["by_path"], [{"path": "src/app.py", "changes": 2}])
        self.assertEqual(result["git"]["churn"]["commits_observed"], 2)
        self.assertEqual(result["git"]["head"], self.git("rev-parse", "HEAD").decode().strip())

    def test_ac12_canonical_json_and_readable_projection_are_deterministic(self):
        self.write("src/a.py", "a = 1\n")
        self.commit()
        first = self.collect()
        second = self.collect()
        encoded = subject("canonical_inventory_json", first)
        self.assertTrue(encoded.startswith('{"'), "canonical JSON must be present")
        self.assertEqual(encoded, subject("canonical_inventory_json", second))
        self.assertEqual(json.loads(encoded), first)
        markdown = subject("render_inventory_md", first)
        self.assertIn("src/a.py", markdown)
        self.assertIn("Mechanical facts", markdown)
        self.assertIn("Unavailable", markdown)
        self.assertNotIn("AI-authorship", encoded)

    def test_ac13_scripts_configs_git_drivers_and_fsmonitor_are_never_executed(self):
        marker = self.root / "executed.txt"
        payload = "from pathlib import Path\nPath(%r).write_text('executed')\n" % str(marker)
        self.write("setup.py", payload)
        self.write("hostile.py", payload)
        command = '"%s" "%s"' % (sys.executable, self.root / "hostile.py")
        self.write("package.json", {"scripts": {"preinstall": command, "inventory": command}})
        self.write(".gitattributes", "*.py diff=hostile\n")
        self.commit()
        self.git("config", "core.fsmonitor", command)
        self.git("config", "diff.external", command)
        self.git("config", "diff.hostile.textconv", command)
        self.write("hostile.py", payload + "# dirty\n")
        result = self.collect()
        self.assertEqual(result.get("git", {}).get("status"), "ok")
        self.assertFalse(marker.exists(), "repository execution escaped the inert extractor")
        self.assertNotIn(command, subject("canonical_inventory_json", result))

    def test_ac13_signature_verifier_is_not_executed_during_history(self):
        """S1-SEC-001: Git signature display must not launch a configured verifier."""
        self.write("src/app.py", "value = 1\n")
        self.git("add", "src/app.py")
        tree = self.git("write-tree").decode().strip()
        # An inert test signature invokes Git's verifier path without any key,
        # signing tool, network, or changes to the actual workspace Git config.
        commit = ("tree " + tree + "\n"
                  "author Fixture <fixture@example.invalid> 1700000000 +0000\n"
                  "committer Fixture <fixture@example.invalid> 1700000000 +0000\n"
                  "gpgsig -----BEGIN PGP SIGNATURE-----\n"
                  " dGVzdA==\n -----END PGP SIGNATURE-----\n\nfixture\n")
        oid = self.git("hash-object", "-t", "commit", "-w", "--stdin",
                       data=commit.encode()).decode().strip()
        self.git("update-ref", "HEAD", oid)
        marker = self.root / "signature-executed.txt"
        verifier = self.root / "signature-probe.sh"
        self.write("signature-probe.sh", "#!/bin/sh\nprintf executed > " +
                   shlex.quote(marker.as_posix()) + "\nexit 1\n")
        verifier.chmod(0o700)
        self.git("config", "log.showSignature", "true")
        self.git("config", "gpg.program", verifier.as_posix())
        result = self.collect(scope="src")
        self.assertEqual(result["git"]["churn"]["status"], "ok")
        self.assertFalse(marker.exists(), "configured signature verifier escaped the inert extractor")
        self.assertEqual(result["git"]["churn"]["by_path"], [{"path": "src/app.py", "changes": 1}])

    def test_ac13_read_bounds_keep_sizes_and_explicit_omissions(self):
        self.write("package.json", {"name": "oversized", "padding": "x" * 150})
        self.write("nested/package.json", {"name": "also bounded"})
        self.commit()
        result = self.collect(max_file_bytes=64, max_total_bytes=64)
        self.assertTrue(result.get("files"), "bounded inventory must retain metadata")
        self.assertGreater(next(row["bytes"] for row in result["files"]
                                if row["path"] == "package.json"), 64)
        self.assertTrue(any(row["reason"] == "file-byte-limit" for row in result["unavailable"]))
        result = self.collect(max_file_bytes=1024, max_total_bytes=1)
        self.assertTrue(any(row["reason"] == "total-byte-limit" for row in result["unavailable"]))

    def test_ac13_repository_markup_is_inert_in_the_readable_projection(self):
        self.write("package.json", {"name": "![remote](https://example.invalid/image)",
                                  "description": "[open](https://example.invalid) <script>bad()</script>"})
        self.commit()
        result = self.collect()
        markdown = subject("render_inventory_md", result)
        self.assertNotIn("![remote]", markdown)
        self.assertNotIn("[open](", markdown)
        self.assertNotIn("<script>", markdown)
        self.assertIn("example.invalid", markdown)

    def test_ac13_readable_metadata_preserves_apostrophes_and_ampersands(self):
        metadata = {"name": "O'Reilly & Sons",
                    "description": "[open](https://example.invalid) <script>bad()</script>"}
        self.write("package.json", metadata)
        self.commit()
        markdown = subject("render_inventory_md", self.collect())
        projected = markdown.split("## Package metadata\n\n", 1)[1].splitlines()[0]
        self.assertEqual(json.loads(html.unescape(projected.removeprefix("- "))),
                         {"manifest": "package.json", **metadata})
        self.assertNotIn("[open](", projected)
        self.assertNotIn("<script>", projected)

    def test_ac13_test_name_fanout_has_a_visible_bound(self):
        for number in range(101):
            self.write("packages/p%d/src/same.py" % number, "value = 1\n")
            self.write("packages/p%d/tests/test_same.py" % number, "assert True\n")
        self.commit()
        result = self.collect()
        self.assertLessEqual(len(result["test_source_relationships"]), 10000)
        self.assertTrue(any(row["field"] == "test_source_relationships" and
                            row["reason"] == "relationship-limit" for row in result["unavailable"]))

    def test_ac12_unsupported_config_dialects_do_not_claim_malformed_source(self):
        self.write("tsconfig.json", '// valid JSONC configuration\n{"compilerOptions": {}}\n')
        self.write("package.json", {"dependencies": {"invalid": []}, "exports": {".": "./src/main.js"}})
        self.commit()
        result = self.collect()
        self.assertTrue(any(row.get("path") == "tsconfig.json" and
                            row["reason"] == "unsupported-jsonc-or-malformed" for row in result["unavailable"]))
        self.assertTrue(any(row.get("path") == "package.json" and
                            row["reason"] == "malformed-dependency" for row in result["unavailable"]))
        self.assertTrue(any(row.get("path") == "package.json" and
                            row["reason"] == "export-map-not-resolved" for row in result["unavailable"]))

    def test_ac13_symlink_and_directory_escape_are_not_read(self):
        outside = Path(self.temp.name) / "outside.json"
        outside.write_text('{"name":"outside-secret"}', encoding="utf-8")
        self.write("package.json", {"name": "inside"})
        self.commit()
        (self.root / "package.json").unlink()
        try:
            (self.root / "package.json").symlink_to(outside)
        except OSError:
            # Windows without symlink privilege still exercises a tracked Git
            # symlink: its bytes are a target path, never a manifest.
            self.write("package.json", str(outside))
            oid = self.git("hash-object", "-w", "package.json").decode().strip()
            self.git("update-index", "--cacheinfo", "120000", oid, "package.json")
        result = self.collect()
        self.assertTrue(any(row.get("path") == "package.json" and
                            row["reason"] == "non-regular-file" for row in result.get("unavailable", [])))
        self.assertNotIn("outside-secret", subject("canonical_inventory_json", result))
        invalid = self.collect(scope="../outside.json")
        self.assertEqual(invalid.get("status"), "unavailable")
        self.assertFalse(invalid["files"])

    def test_ac12_unavailable_git_and_invalid_inputs_are_not_empty_success(self):
        result = subject("collect_inventory", Path(self.temp.name) / "missing")
        self.assertEqual(result.get("status"), "unavailable")
        self.assertTrue(result["unavailable"])
        for kwargs in ({"scope": 123}, {"history_limit": -1}, {"max_file_bytes": True}):
            with self.subTest(kwargs=kwargs):
                result = self.collect(**kwargs)
                self.assertEqual(result.get("status"), "unavailable")

    def test_ac13_missing_toml_parser_is_explicit_without_loading_project_code(self):
        self.write("pyproject.toml", '[project]\nname = "sample"\n')
        self.commit()
        if INVENTORY is None:
            result = self.collect()
        else:
            with patch.object(INVENTORY, "tomllib", None):
                result = self.collect()
        self.assertTrue(any(row["reason"] == "stdlib-toml-unavailable"
                            for row in result.get("unavailable", [])))


class ProfileCostTests(unittest.TestCase):
    def test_ac10_only_supplied_supported_settings_are_resolved(self):
        capabilities = {"fresh_threads": True, "model_override": True,
                        "reasoning_override": True, "models": ["host-choice"],
                        "reasoning_levels": ["high"],
                        "profiles": {"deep": {"model": "host-choice", "reasoning": "high"}}}
        result = subject("resolve_profile", "deep", capabilities)
        self.assertEqual(result.get("settings"), {"model": "host-choice", "reasoning": "high"})
        capabilities["models"] = []
        capabilities["reasoning_levels"] = []
        result = subject("resolve_profile", "deep", capabilities)
        self.assertEqual(result["settings"], {})
        self.assertEqual(result["model_source"], "inherited")
        self.assertTrue(result["limitations"])

    def test_ac10_unavailable_overrides_inherit_for_all_profiles(self):
        for profile in ("deep", "standard", "extract"):
            with self.subTest(profile=profile):
                result = subject("resolve_profile", profile, {"fresh_threads": True})
                self.assertEqual(result.get("settings"), {})
                self.assertEqual(result["model_source"], "inherited")
                self.assertTrue(result["limitations"])
        result = subject("resolve_profile", "invented", {})
        self.assertEqual(result.get("status"), "unavailable")

    def test_ac11_registration_false_does_not_disable_actual_fresh_threads(self):
        result = subject("resolve_profile", "standard", {"agents": False, "fresh_threads": True})
        self.assertEqual(result.get("execution"), "fresh-thread")
        self.assertEqual(result["independence"], "fresh-context")

    def test_ac11_absent_threads_report_limited_inline_independence(self):
        for capabilities in ({"agents": True}, {"fresh_threads": False}, None):
            with self.subTest(capabilities=capabilities):
                result = subject("resolve_profile", "standard", capabilities)
                self.assertEqual(result.get("execution"), "inline")
                self.assertEqual(result["independence"], "limited-shared-context")
                self.assertTrue(result["limitations"])

    def test_ac37_cost_uses_packet_profiles_verification_without_prices_or_measured_usage(self):
        baseline = subject("estimate_cost", 12000, {"deep": 2, "standard": 1},
                           verification_candidates=2, extraction_bytes=800)
        self.assertEqual(baseline.get("basis"), "heuristic-not-usage")
        self.assertEqual(baseline["inputs"]["active_lenses"], 3)
        self.assertEqual(baseline["inputs"]["packet_bytes"], 12000)
        self.assertIsNone(baseline["measured_usage"])
        self.assertIsNone(baseline["price"])
        self.assertLess(baseline["token_band"]["low"], baseline["token_band"]["high"])
        for options in ({"packet_bytes": 24000}, {"verification_candidates": 4}):
            arguments = {"packet_bytes": 12000, "profile_counts": {"deep": 2, "standard": 1},
                         "verification_candidates": 2, "extraction_bytes": 800}
            arguments.update(options)
            larger = subject("estimate_cost", **arguments)
            self.assertGreater(larger["token_band"]["high"], baseline["token_band"]["high"])

    def test_ac37_concurrency_changes_resources_not_total_token_band(self):
        serial = subject("estimate_cost", 10000, {"standard": 4}, concurrency=1)
        parallel = subject("estimate_cost", 10000, {"standard": 4}, concurrency=4)
        self.assertIsNotNone(serial.get("token_band"), "a token band must be estimated")
        self.assertEqual(serial["token_band"], parallel["token_band"])
        self.assertEqual(parallel["concurrency"]["in_flight"], 4)
        self.assertFalse(parallel["concurrency"]["reduces_total_tokens"])

    def test_ac37_invalid_cost_inputs_are_explicit_not_estimates(self):
        for packet_bytes, profiles in ((-1, {"deep": 1}), (True, {"deep": 1}),
                                       (10, {"unknown": 1}), (10, {"deep": "2"})):
            with self.subTest(packet_bytes=packet_bytes, profiles=profiles):
                result = subject("estimate_cost", packet_bytes, profiles)
                self.assertEqual(result.get("status"), "unavailable")
                self.assertIsNone(result["token_band"])


if __name__ == "__main__":
    unittest.main()

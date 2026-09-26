#!/usr/bin/env python3
# codeArbiter — native Go statement collection and supported-host union contracts.
"""Real Go fixtures; host projections below test merge semantics, not host qualification."""

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "tools" / "artifact-coverage.py"
PLATFORMS = (
    "linux/amd64", "linux/arm64", "windows/amd64", "windows/arm64",
    "darwin/amd64", "darwin/arm64",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ArtifactCoverageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ca-native-coverage-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / "module"
        self.module.mkdir()
        files = {
            "go.mod": "module example.invalid/coveragefixture\n\ngo 1.20\n",
            "logic/logic.go": (
                'package logic\nimport _ "embed"\n//go:embed fixture.txt\n'
                'var fixture string\nfunc Choose(left bool) int {\n'
                ' if left {\n  return 11\n }\n return 22\n}\n'
                'func Never() int { return 33 }\n'
            ),
            "logic/fixture.txt": "embedded exact bytes\n",
            "integration/doc.go": "package integration\n",
            "integration/logic_test.go": (
                'package integration_test\nimport ("testing"; '
                '"example.invalid/coveragefixture/logic")\n'
                'func TestLeft(t *testing.T) {\n'
                ' if logic.Choose(true) != 11 { t.Fatal("wrong choice") }\n}\n'
            ),
            "unused/unused.go": "package unused\nfunc Uncalled() int { return 44 }\n",
            "cmd/demo/main.go": (
                'package main\nimport "example.invalid/coveragefixture/logic"\n'
                'func main() {\n if logic.Choose(false) != 22 { panic("wrong choice") }\n}\n'
            ),
        }
        for relative, body in files.items():
            path = self.module / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8", newline="\n")
        self.env = {**os.environ, "GOTOOLCHAIN": "local", "GOWORK": "off", "GOFLAGS": ""}
        host = json.loads(self.go("env", "-json", "GOHOSTOS", "GOHOSTARCH").stdout)
        self.host = host["GOHOSTOS"] + "/" + host["GOHOSTARCH"]
        self.number = 0

    def go(self, *args, env=None):
        result = subprocess.run(
            ["go", *args], cwd=self.module, env=env or self.env,
            text=True, encoding="utf-8", capture_output=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def helper(self, *args, success=True, env=None):
        self.assertTrue(
            SCRIPT.is_file(),
            "native statement collector/union is absent; raw Go output has no bound host-union contract",
        )
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)], cwd=REPO,
            env=env or self.env, text=True, encoding="utf-8", capture_output=True, timeout=180,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        if not success:
            self.assertNotEqual(report["status"], "COMPLETE")
        return report

    def load_helper(self):
        self.assertTrue(SCRIPT.is_file(), "source-bound integration sidecar producer is absent")
        spec = importlib.util.spec_from_file_location("artifact_coverage_fixture", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def collect(self, *args, success=True, env=None):
        self.number += 1
        output = self.root / ("collection-" + str(self.number))
        report = self.helper(
            "collect", "--module-root", self.module, "--output", output,
            *args, success=success, env=env,
        )
        return output, report

    def summarize(self, inputs, expected=None, *args, success=True):
        argv = ["summarize", "--module-root", self.module]
        for path in inputs:
            argv += ["--input", path]
        for platform in expected or [self.host]:
            argv += ["--expect-platform", platform]
        return self.helper(*argv, *args, success=success)

    def metadata(self, path):
        return json.loads((path / "metadata.json").read_text(encoding="utf-8"))

    def write_metadata(self, path, value):
        (path / "metadata.json").write_text(json.dumps(value), encoding="utf-8")

    def write_synthetic_profile(self, folder, metadata, rows):
        """Bind intentionally projected counters/layouts; never executed-host proof."""
        profile = folder / "unit.coverage.out"
        profile.write_text("mode: atomic\n" + "\n".join(rows) + "\n", encoding="utf-8")
        blocks = {}
        for row in rows:
            location, statements, _ = row.split()
            filename, span = location.rsplit(":", 1)
            coordinates = tuple(int(number) for point in span.split(",") for number in point.split("."))
            blocks[(filename, *coordinates)] = int(statements)
        inventory = [list(key) + [count] for key, count in sorted(blocks.items())]
        metadata["profiles"][0]["sha256"] = digest(profile)
        metadata["profiles"][0]["blocks_sha256"] = hashlib.sha256(json.dumps(
            inventory, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        self.write_metadata(folder, metadata)

    def test_collect_measures_cross_package_calls_and_unexecuted_production(self):
        # NC-01: a package exercised only by another package's tests must count.
        output, result = self.collect("--expect-platform", self.host)
        metadata = self.metadata(output)
        profile = output / "unit.coverage.out"
        lines = profile.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "mode: atomic")
        self.assertTrue(any("/logic/logic.go:" in row and int(row.rsplit(" ", 1)[1]) > 0 for row in lines[1:]))
        self.assertTrue(any("/unused/unused.go:" in row and row.endswith(" 0") for row in lines[1:]))
        self.assertTrue(any("/cmd/demo/main.go:" in row and row.endswith(" 0") for row in lines[1:]))
        self.assertEqual(metadata["platform"], self.host)
        self.assertEqual(metadata["profiles"][0]["sha256"], digest(profile))
        self.assertIn("logic/fixture.txt", metadata["source"]["files"])
        self.assertIn("integration/logic_test.go", metadata["source"]["files"])
        self.assertEqual(result["metric"], "statements")
        summary = self.summarize([output])
        self.assertEqual(summary["not_measured"], ["lines", "branches"])
        self.assertEqual(summary["integration"]["missing_platforms"], [self.host])
        self.assertGreater(summary["statements"]["covered"], 0)
        self.assertLess(summary["statements"]["covered"], summary["statements"]["total"])
        self.assertNotIn("branches", summary["statements"])

    def test_real_instrumented_cli_profile_adds_hits_without_doubling_statements(self):
        # NC-02: genuine GOCOVERDIR -> covdata textfmt, isolated from host bridge.
        helper = self.load_helper()
        before = helper.source_identity(self.module)
        binary = self.root / ("demo.exe" if os.name == "nt" else "demo")
        self.go("build", "-buildvcs=false", "-cover", "-covermode=atomic", "-coverpkg=./...", "-o", str(binary), "./cmd/demo")
        counters = self.root / "counters"
        counters.mkdir()
        run = subprocess.run([str(binary)], env={**self.env, "GOCOVERDIR": str(counters)}, capture_output=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        profile = self.root / "cli.coverage.out"
        self.go("tool", "covdata", "textfmt", "-i=" + str(counters), "-o=" + str(profile))
        sidecar = helper.integration_metadata(self.module, profile, before)
        Path(str(profile) + ".json").write_text(json.dumps(sidecar), encoding="utf-8")
        unit, _ = self.collect()
        combined, _ = self.collect("--extra-profile", profile)
        unit_summary = self.summarize([unit])
        combined_summary = self.summarize([combined], None, "--require-integration")
        self.assertEqual(combined_summary["statements"]["total"], unit_summary["statements"]["total"])
        self.assertGreater(combined_summary["statements"]["covered"], unit_summary["statements"]["covered"])
        self.assertEqual(combined_summary["integration"]["missing_platforms"], [])
        self.assertEqual(digest(combined / "integration-1.coverage.out"), digest(profile))
        self.assertEqual(sidecar["source_sha256"], before["sha256"])

    def test_six_host_union_counts_each_shared_block_once(self):
        # NC-03: projections are merge fixtures, never six-host execution claims.
        original, _ = self.collect()
        original_summary = self.summarize([original])
        inputs = []
        for index, platform in enumerate(PLATFORMS):
            projected = self.root / ("projected-" + str(index))
            shutil.copytree(original, projected)
            metadata = self.metadata(projected)
            metadata["platform"] = platform
            self.write_metadata(projected, metadata)
            inputs.append(projected)
        union = self.summarize(inputs, PLATFORMS)
        self.assertEqual(union["statements"], original_summary["statements"])
        self.assertEqual(union["platforms"], sorted(PLATFORMS))
        self.assertEqual(union["expected_platforms"], sorted(PLATFORMS))
        self.assertEqual(union["missing_platforms"], [])

    def test_platform_exclusive_blocks_join_once_and_complementary_hits_union(self):
        platform_dir = self.module / "platform"
        platform_dir.mkdir()
        for goos in ("linux", "windows", "darwin"):
            (platform_dir / ("native_" + goos + ".go")).write_text(
                "package platform\nfunc Native() int { return 1 }\n", encoding="utf-8",
            )
        # Go itself selects the OS files. Only the current native platform is
        # executed; the other inventories/counters below are synthetic fixtures.
        selected = {}
        for platform in PLATFORMS:
            goos, goarch = platform.split("/")
            package = json.loads(self.go(
                "list", "-json", "./platform",
                env={**self.env, "GOOS": goos, "GOARCH": goarch},
            ).stdout)
            self.assertEqual(package["GoFiles"], ["native_" + goos + ".go"])
            selected[platform] = package["GoFiles"][0]
        original, _ = self.collect()
        single = self.summarize([original])
        native_file = selected[self.host]
        original_rows = (original / "unit.coverage.out").read_text(encoding="utf-8").splitlines()[1:]
        exclusive_rows = [row for row in original_rows if "/platform/" + native_file + ":" in row]
        self.assertTrue(exclusive_rows)
        self.assertEqual({row.split()[1] for row in exclusive_rows}, {"1"})
        self.assertEqual({row.split()[2] for row in exclusive_rows}, {"0"})
        inputs = []
        for index, platform in enumerate(PLATFORMS):
            projected = self.root / ("synthetic-exclusive-" + str(index))
            shutil.copytree(original, projected)
            metadata = self.metadata(projected)
            metadata["platform"] = platform
            rows = []
            for row in original_rows:
                if "/platform/" + native_file + ":" in row:
                    location, statements, _ = row.split()
                    location = location.replace(native_file + ":", selected[platform] + ":")
                    row = location + " " + statements + " " + str(int(platform.endswith("/arm64")))
                rows.append(row)
            self.write_synthetic_profile(projected, metadata, rows)
            inputs.append(projected)
        union = self.summarize(inputs, PLATFORMS)
        # Two new OS-only files enter the denominator. Each of three OS files
        # is uncovered on its amd64 projection and covered on its arm64 one.
        self.assertEqual(union["statements"]["total"], single["statements"]["total"] + 2)
        self.assertEqual(union["statements"]["covered"], single["statements"]["covered"] + 3)
        self.assertEqual(union["statements"]["percent"], round(
            100 * (single["statements"]["covered"] + 3) / (single["statements"]["total"] + 2), 4,
        ))
        self.assertEqual(union["missing_platforms"], [])

    def test_conflicting_shared_file_layouts_are_rejected_in_either_host_order(self):
        original, _ = self.collect()
        other = next(platform for platform in PLATFORMS if platform != self.host)
        projected = self.root / "synthetic-incompatible-layout"
        shutil.copytree(original, projected)
        metadata = self.metadata(projected)
        metadata["platform"] = other
        rows = (projected / "unit.coverage.out").read_text(encoding="utf-8").splitlines()[1:]
        # Remove a whole block but retain this shared file's other blocks.
        # Rebind both hashes so refusal must come from cross-host consistency.
        removed = next(row.split()[0] for row in rows if "/logic/logic.go:" in row)
        rows = [row for row in rows if row.split()[0] != removed]
        self.assertTrue(any("/logic/logic.go:" in row for row in rows))
        self.write_synthetic_profile(projected, metadata, rows)
        for inputs in ([original, projected], [projected, original]):
            with self.subTest(first=inputs[0].name):
                result = self.summarize(inputs, [self.host, other], success=False)
                self.assertEqual(result["status"], "INVALID")
                self.assertIn("shared source instrumentation differs", result["error"])

    def test_missing_duplicate_or_unexpected_hosts_cannot_form_a_complete_union(self):
        original, _ = self.collect()
        partial = self.summarize([original], PLATFORMS, success=False)
        self.assertEqual(partial["status"], "PARTIAL")
        self.assertEqual(set(partial["missing_platforms"]), set(PLATFORMS) - {self.host})
        self.summarize([original, original], success=False)
        other = next(platform for platform in PLATFORMS if platform != self.host)
        self.summarize([original], [other], success=False)
        self.summarize([original], [self.host, self.host], success=False)

    def test_complementary_host_counters_union_without_averaging_or_recounting(self):
        original, _ = self.collect()
        original_summary = self.summarize([original])
        inputs = []
        # Synthetic counter projections constrain the merger; they are not
        # executed-host coverage and cannot qualify the supported host matrix.
        for index, platform in enumerate(PLATFORMS):
            projected = self.root / ("complementary-" + str(index))
            shutil.copytree(original, projected)
            metadata = self.metadata(projected)
            metadata["platform"] = platform
            profile = projected / "unit.coverage.out"
            lines = profile.read_text(encoding="utf-8").splitlines()
            rows = [line.rsplit(" ", 1)[0] + " " + str(int(position % len(PLATFORMS) == index))
                    for position, line in enumerate(lines[1:])]
            profile.write_text("mode: atomic\n" + "\n".join(rows) + "\n", encoding="utf-8")
            metadata["profiles"][0]["sha256"] = digest(profile)
            self.write_metadata(projected, metadata)
            inputs.append(projected)
        union = self.summarize(inputs, PLATFORMS, "--minimum-statements", "100")
        self.assertEqual(union["statements"]["total"], original_summary["statements"]["total"])
        self.assertEqual(union["statements"]["covered"], union["statements"]["total"])
        self.assertEqual(union["statements"]["percent"], 100.0)

    def test_statement_minimum_and_required_cli_coverage_are_independent(self):
        original, _ = self.collect()
        self.summarize([original], None, "--minimum-statements", "0")
        low = self.summarize([original], None, "--minimum-statements", "100", success=False)
        self.assertEqual(low["status"], "BELOW_MINIMUM")
        self.assertFalse(low["minimum_met"])
        missing = self.summarize([original], None, "--require-integration", success=False)
        self.assertEqual(missing["status"], "MISSING_INTEGRATION")
        for minimum in ("NaN", "inf", "-1", "101"):
            with self.subTest(minimum=minimum):
                self.summarize([original], None, "--minimum-statements", minimum, success=False)

    def test_stale_go_test_or_embedded_inputs_reject_retained_profiles(self):
        original, _ = self.collect()
        for relative in ("logic/logic.go", "integration/logic_test.go", "logic/fixture.txt", "go.mod"):
            path = self.module / relative
            retained = path.read_bytes()
            with self.subTest(source=relative):
                path.write_bytes(retained + b"\n")
                self.summarize([original], success=False)
                path.write_bytes(retained)
        self.summarize([original])

    def test_malformed_tampered_or_incomplete_collection_fails_closed(self):
        original, _ = self.collect()
        cases = ("metadata-missing", "profile-missing", "json", "duplicate-json", "unknown-field", "profile-hash", "mode", "truncated", "foreign", "negative", "statement-mismatch", "toolchain", "platform", "profile-traversal")
        for index, case in enumerate(cases):
            with self.subTest(case=case):
                altered = self.root / ("invalid-" + str(index))
                shutil.copytree(original, altered)
                metadata = self.metadata(altered)
                profile = altered / "unit.coverage.out"
                text = profile.read_text(encoding="utf-8")
                lines = text.splitlines()
                if case == "metadata-missing":
                    (altered / "metadata.json").unlink()
                elif case == "profile-missing":
                    profile.unlink()
                elif case == "json":
                    (altered / "metadata.json").write_text("{", encoding="utf-8")
                elif case == "duplicate-json":
                    (altered / "metadata.json").write_text(json.dumps(metadata)[:-1] + ',"platform":"' + self.host + '"}', encoding="utf-8")
                else:
                    if case == "unknown-field":
                        metadata["branch_percent"] = 100
                    elif case == "profile-hash":
                        location, count, hits = lines[1].split()
                        lines[1] = location + " " + count + " " + str(int(hits) + 1)
                        profile.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    elif case == "toolchain":
                        metadata["go_version"] = "go0.0.0"
                    elif case == "platform":
                        metadata["platform"] = "plan9/amd64"
                    elif case == "profile-traversal":
                        metadata["profiles"][0]["file"] = "../unit.coverage.out"
                    else:
                        if case == "mode":
                            lines[0] = "mode: set"
                        elif case == "truncated":
                            # -coverpkg repeats blocks across test packages.
                            # Remove the complete block, not one duplicate row.
                            removed = lines[-1].split()[0]
                            lines = lines[:1] + [row for row in lines[1:] if row.split()[0] != removed]
                        elif case == "foreign":
                            lines[1] = lines[1].replace("example.invalid/coveragefixture", "example.invalid/other")
                        elif case == "negative":
                            lines[1] = lines[1].rsplit(" ", 1)[0] + " -1"
                        elif case == "statement-mismatch":
                            location, count, hits = lines[1].split()
                            lines.append(location + " " + str(int(count) + 1) + " " + hits)
                        profile.write_text("\n".join(lines) + "\n", encoding="utf-8")
                        metadata["profiles"][0]["sha256"] = digest(profile)
                    self.write_metadata(altered, metadata)
                self.summarize([altered], success=False)

    def test_extra_profile_requires_matching_source_platform_toolchain_and_digest(self):
        helper = self.load_helper()
        original, _ = self.collect()
        profile = self.root / "additional.out"
        shutil.copyfile(original / "unit.coverage.out", profile)
        before = helper.source_identity(self.module)
        valid = helper.integration_metadata(self.module, profile, before)
        sidecar = Path(str(profile) + ".json")
        self.collect("--extra-profile", profile, success=False)
        for field, value in (("source_sha256", "0" * 64), ("platform", "linux/arm64" if self.host != "linux/arm64" else "darwin/amd64"), ("go_version", "go0.0.0"), ("profile_sha256", "0" * 64)):
            with self.subTest(field=field):
                sidecar.write_text(json.dumps({**valid, field: value}), encoding="utf-8")
                output, _ = self.collect("--extra-profile", profile, success=False)
                self.assertFalse((output / "metadata.json").exists())
        (self.module / "logic/fixture.txt").write_text("changed", encoding="utf-8")
        with self.assertRaises(ValueError):
            helper.integration_metadata(self.module, profile, before)

    def test_failed_unit_command_writes_no_usable_metadata(self):
        (self.module / "integration/logic_test.go").write_text(
            'package integration_test\nimport "testing"\nfunc TestFail(t *testing.T) { t.Fatal("intentional fixture failure") }\n', encoding="utf-8",
        )
        output, _ = self.collect(success=False)
        self.assertFalse((output / "metadata.json").exists())

    def test_source_changed_during_unit_collection_cannot_be_reported(self):
        path = self.module / "integration/logic_test.go"
        path.write_text(
            'package integration_test\nimport ("testing"; "os")\n'
            'func TestChangeSource(t *testing.T) {\n'
            ' if err := os.WriteFile("../logic/fixture.txt", []byte("changed"), 0600); err != nil { t.Fatal(err) }\n}\n',
            encoding="utf-8",
        )
        output, _ = self.collect(success=False)
        self.assertFalse((output / "metadata.json").exists())

    def test_unit_text_labelled_as_extra_does_not_hide_unexecuted_cli(self):
        helper = self.load_helper()
        original, _ = self.collect()
        profile = self.root / "no-cli.out"
        shutil.copyfile(original / "unit.coverage.out", profile)
        sidecar = helper.integration_metadata(self.module, profile, helper.source_identity(self.module))
        Path(str(profile) + ".json").write_text(json.dumps(sidecar), encoding="utf-8")
        combined, _ = self.collect("--extra-profile", profile)
        result = self.summarize([combined], None, "--require-integration", success=False)
        self.assertEqual(result["integration"]["missing_platforms"], [self.host])

    def test_collection_refuses_cross_target_reuse_and_module_output(self):
        wrong = next(platform for platform in PLATFORMS if platform != self.host)
        self.collect("--expect-platform", wrong, success=False)
        env = {**self.env, "GOOS": wrong.split("/")[0], "GOARCH": wrong.split("/")[1]}
        self.collect(success=False, env=env)
        original, _ = self.collect()
        retained = (original / "metadata.json").read_bytes()
        self.helper("collect", "--module-root", self.module, "--output", original, success=False)
        self.assertEqual((original / "metadata.json").read_bytes(), retained)
        self.helper("collect", "--module-root", self.module, "--output", self.module / "output", success=False)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Task 11 cross-platform contract runner and its deterministic fixtures."""

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SUPPORTED = ("0.80.5", "0.80.10")
PLATFORM_COMMAND_TIMEOUT_SECONDS = 180


def version_policy(version):
    if version in SUPPORTED:
        return {"version": version, "blocking": True}
    if version == "latest":
        return {"version": version, "blocking": False}
    raise ValueError("Pi version must be 0.80.5, 0.80.10, or latest")


def fixture_commands(fixtures_only):
    python = sys.executable
    npm = str(resolve_executable("npm"))
    commands = [
        [python, ".github/scripts/test_host_descriptors.py"],
        [python, ".github/scripts/test_pi_package.py"],
        # The real-host package fixture owns a Git daemon, temp repository, and
        # external Pi loader. Give it a fresh Vitest process so the platform
        # rerun cannot inherit state from the process-tree fixture files.
        [npm, "--prefix", "plugins/ca-pi/tools", "test", "--", "--run",
         "test/package.test.ts"],
        [npm, "--prefix", "plugins/ca-pi/tools", "test", "--", "--run",
         "test/bridge.test.ts", "test/runner-isolation.test.ts",
         "test/process-tree.test.ts"],
        [python, ".github/scripts/test_pi_parity.py"],
        [python, ".github/scripts/test_pi_process_tree.py", "--fixture-only"],
        [python, ".github/scripts/test_pi_compaction_surface.py"],
        [python, ".github/scripts/test_prune_policy_parity.py"],
        [python, "tools/build-surface.py", "--check"],
        [python, "tools/build-host-packages.py", "--check"],
        [python, ".github/scripts/test_pi_benchmark.py"],
    ]
    if not fixtures_only:
        commands.extend([
            [python, ".github/scripts/test_pi_process_tree.py"],
            [python, ".github/scripts/test_pi_child_live.py"],
            [python, ".github/scripts/pi_benchmark.py", "--samples", "100"],
        ])
    return commands


def decode_jsonl(raw):
    text = raw.decode("utf-8", "strict")
    rows = []
    for line in text.splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def resolve_executable(name):
    candidate = shutil.which(name)
    if candidate is None and os.name == "nt" and not pathlib.Path(name).suffix:
        candidate = shutil.which(name + ".cmd") or shutil.which(name + ".exe")
    if candidate is None:
        raise FileNotFoundError(f"required executable is unavailable: {name}")
    resolved = pathlib.Path(candidate).resolve()
    if not resolved.is_absolute() or not resolved.is_file():
        raise FileNotFoundError(f"required executable did not resolve to a real file: {name}")
    return resolved


class PlatformContractFixtures(unittest.TestCase):
    def test_supported_versions_block_and_only_latest_is_nonblocking(self):
        self.assertEqual(version_policy("0.80.5"), {"version": "0.80.5", "blocking": True})
        self.assertEqual(version_policy("0.80.10"), {"version": "0.80.10", "blocking": True})
        self.assertEqual(version_policy("latest"), {"version": "latest", "blocking": False})
        with self.assertRaisesRegex(ValueError, "0.80.5, 0.80.10, or latest"):
            version_policy("0.81.0")

    def test_utf8_jsonl_accepts_lf_and_crlf_in_a_unicode_space_path(self):
        rows = [{"pathClass": "space-unicode", "value": "pi-π"}, {"cancelled": True}]
        for newline in ("\n", "\r\n"):
            raw = newline.join(json.dumps(row, ensure_ascii=False) for row in rows).encode("utf-8") + newline.encode()
            self.assertEqual(decode_jsonl(raw), rows)
        with tempfile.TemporaryDirectory(prefix="ca pi π platform ") as raw_dir:
            path = pathlib.Path(raw_dir) / "generated path π.jsonl"
            path.write_bytes((json.dumps(rows[0], ensure_ascii=False) + "\r\n").encode("utf-8"))
            self.assertEqual(decode_jsonl(path.read_bytes()), [rows[0]])

    def test_executable_resolution_is_absolute_and_real(self):
        executable = resolve_executable(pathlib.Path(sys.executable).name)
        self.assertTrue(executable.is_absolute())
        self.assertTrue(executable.is_file())
        self.assertEqual(executable, executable.resolve())

    def test_fixture_plan_covers_every_cross_platform_obligation(self):
        commands = fixture_commands(fixtures_only=True)
        rendered = "\n".join(" ".join(command) for command in commands)
        for required in (
            "test_pi_package.py", "bridge.test.ts", "runner-isolation.test.ts",
            "test_pi_process_tree.py --fixture-only", "test_pi_compaction_surface.py",
            "test_prune_policy_parity.py", "build-surface.py --check",
            "build-host-packages.py --check", "test_host_descriptors.py",
            "test_pi_benchmark.py",
        ):
            self.assertIn(required, rendered)

    def test_process_heavy_package_fixture_uses_a_fresh_vitest_process(self):
        commands = fixture_commands(fixtures_only=True)
        vitest_commands = [
            command for command in commands
            if "plugins/ca-pi/tools" in command and "test" in command
        ]
        self.assertEqual(len(vitest_commands), 2)
        self.assertEqual(vitest_commands[0][-1], "test/package.test.ts")
        self.assertNotIn("test/package.test.ts", vitest_commands[1])
        for required in (
            "test/bridge.test.ts",
            "test/runner-isolation.test.ts",
            "test/process-tree.test.ts",
        ):
            self.assertIn(required, vitest_commands[1])

    def test_live_duplicate_host_budget_fits_inside_platform_command_deadline(self):
        package_test = (
            ROOT / "plugins" / "ca-pi" / "tools" / "test" / "package.test.ts"
        ).read_text(encoding="utf-8")
        match = re.search(
            r"const LIVE_DUPLICATE_HOST_TIMEOUT_MS = ([\d_]+);",
            package_test,
        )
        self.assertIsNotNone(match)
        budget_ms = int(match.group(1).replace("_", ""))
        self.assertEqual(budget_ms, 120_000)
        self.assertLess(budget_ms, PLATFORM_COMMAND_TIMEOUT_SECONDS * 1_000)


def run_contract(pi_version, fixtures_only):
    policy = None if pi_version is None else version_policy(pi_version)
    if policy is not None:
        pi = resolve_executable("pi")
        probe = subprocess.run(
            [str(pi), "--version"], cwd=ROOT, check=False, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=15,
        )
        installed = probe.stdout.strip().splitlines()[0] if probe.returncode == 0 and probe.stdout.strip() else "unavailable"
        if policy["blocking"] and installed != pi_version:
            print(json.dumps({"piVersion": pi_version, "blocking": True, "result": "version_mismatch"}))
            return 1

    environment = os.environ.copy()
    environment.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    for index, command in enumerate(fixture_commands(fixtures_only), start=1):
        completed = subprocess.run(
            command, cwd=ROOT, env=environment, check=False, capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=PLATFORM_COMMAND_TIMEOUT_SECONDS,
        )
        label = pathlib.Path(command[1] if len(command) > 1 else command[0]).name
        if completed.returncode != 0:
            detail = (completed.stdout + "\n" + completed.stderr).replace(str(ROOT), "<repo>")[-4000:]
            print(json.dumps({
                "piVersion": pi_version or "fixtures", "blocking": bool(policy and policy["blocking"]),
                "result": "failed", "step": index, "command": label,
            }))
            sys.stderr.write(detail)
            return completed.returncode or 1
        print(json.dumps({"step": index, "command": label, "result": "passed"}))
    print(json.dumps({
        "piVersion": pi_version or "fixtures",
        "blocking": bool(policy and policy["blocking"]),
        "result": "passed",
        "platform": sys.platform,
    }))
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures-only", action="store_true")
    parser.add_argument("--pi-version", choices=(*SUPPORTED, "latest"))
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PlatformContractFixtures)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    if args.fixtures_only or args.pi_version is not None:
        return run_contract(args.pi_version, args.fixtures_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

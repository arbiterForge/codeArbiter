#!/usr/bin/env python3
"""Task 5 Pi doctor and shared Git-backstop integration contract."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOST_HOOKS = {
    "claude": REPO / "plugins" / "ca" / "hooks",
    "codex": REPO / "plugins" / "ca-codex" / "hooks",
    "pi": REPO / "plugins" / "ca-pi" / "hooks",
}


def run(args, cwd, *, input_text=None, check=True):
    result = subprocess.run(
        [str(item) for item in args], cwd=cwd, input=input_text,
        text=True, encoding="utf-8", errors="replace", capture_output=True,
        timeout=30, env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        },
    )
    if check and result.returncode != 0:
        raise AssertionError(f"{args!r} failed ({result.returncode})\n{result.stdout}\n{result.stderr}")
    return result


class RepoFixture(unittest.TestCase):
    def setUp(self):
        self.temp = None
        self.reset_repo()

    def reset_repo(self):
        if self.temp is not None:
            self.temp.cleanup()
        self.temp = tempfile.TemporaryDirectory(prefix="ca-pi-doctor-")
        self.root = Path(self.temp.name)
        run(["git", "init", "-b", "main"], self.root)
        run(["git", "config", "user.email", "pi-doctor@example.invalid"], self.root)
        run(["git", "config", "user.name", "Pi Doctor"], self.root)
        state = self.root / ".codearbiter"
        state.mkdir()
        (state / "CONTEXT.md").write_text(
            "---\narbiter: enabled\n---\n<!--INITIALIZED-->\n", encoding="utf-8", newline="\n"
        )

    def tearDown(self):
        if self.temp is not None:
            self.temp.cleanup()

    def install(self, host):
        return run([sys.executable, HOST_HOOKS[host] / "_githooks.py", "install", self.root], self.root)

    def hook_path(self):
        result = run(["git", "rev-parse", "--git-path", "hooks"], self.root)
        path = Path(result.stdout.strip())
        return path if path.is_absolute() else self.root / path

    def assert_current_and_enforcing(self, final_host):
        expected = str((HOST_HOOKS[final_host] / "git-enforce.py").resolve()).replace("\\", "/")
        for phase in ("pre-commit", "pre-push"):
            body = (self.hook_path() / phase).read_text(encoding="utf-8")
            self.assertEqual(body.count("codeArbiter-managed git hook"), 1)
            self.assertIn(expected, body.replace("\\", "/"))
        (self.root / "probe.txt").write_text("Task 5 subprocess enforcement\n", encoding="utf-8")
        run(["git", "add", "probe.txt"], self.root)
        blocked = run(["git", "commit", "-m", "task 5 hook probe"], self.root, check=False)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("[H-01]", blocked.stdout + blocked.stderr)
        push_input = f"refs/heads/main {'1' * 40} refs/heads/main {'0' * 40}\n"
        pushed = run(
            ["sh", self.hook_path() / "pre-push", "origin", "fixture"],
            self.root,
            input_text=push_input,
            check=False,
        )
        self.assertNotEqual(pushed.returncode, 0)
        self.assertIn("[H-01]", pushed.stdout + pushed.stderr)


class GitBackstopContract(RepoFixture):
    def test_host_install_order_is_idempotent_and_executes_shared_enforcer(self):
        for index, order in enumerate((("claude", "pi"), ("pi", "codex"), ("pi", "pi"))):
            with self.subTest(order=order):
                if index > 0:
                    self.reset_repo()
                for host in order:
                    self.install(host)
                self.assert_current_and_enforcing(order[-1])

    def test_custom_hooks_path_survives_pi_install_and_enforces(self):
        run(["git", "config", "core.hooksPath", ".custom-hooks"], self.root)
        self.install("claude")
        self.install("pi")
        self.assertEqual(self.hook_path().resolve(), (self.root / ".custom-hooks").resolve())
        self.assert_current_and_enforcing("pi")

    def test_pi_session_start_installs_backstop_that_rejects_commit(self):
        request = json.dumps({"version": 1, "event": "session_start", "cwd": str(self.root)})
        bridge = run([sys.executable, HOST_HOOKS["pi"] / "pi-bridge.py"], self.root, input_text=request)
        self.assertEqual(json.loads(bridge.stdout)["version"], 1)
        self.assert_current_and_enforcing("pi")


class SharedDoctorContract(RepoFixture):
    def test_pi_payload_check_uses_package_and_bridge_contract_not_hooks_json(self):
        script = HOST_HOOKS["pi"] / "doctor.py"
        result = run([sys.executable, script], self.root, check=False)
        combined = result.stdout + result.stderr
        self.assertNotIn("hooks/hooks.json unreadable", combined)
        self.assertNotIn("hook script(s) missing", combined)
        self.assertIn("resolved host: pi", combined)
        self.assertIn("package.json", combined)
        self.assertIn("pi-bridge.py", combined)
        self.assertNotIn("live-fire", combined)
        self.assertNotIn("hooks actually fire", combined)
        self.assertIn("wrapper self-test", combined)
        self.assertIn("active-dispatch", combined)

    def test_generated_pi_doctor_is_pi_native_and_not_codex_fallback(self):
        skill = (REPO / "plugins" / "ca-pi" / "skills" / "ca-doctor" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        catalog = json.loads(
            (REPO / "plugins" / "ca-pi" / "generated" / "command-catalog.json").read_text(
                encoding="utf-8"
            )
        )
        index = (REPO / "plugins" / "ca-pi" / "skills" / "INDEX.md").read_text(
            encoding="utf-8"
        )
        doctor = next(entry for entry in catalog if entry["name"] == "doctor")
        expected_description = (
            "Verify the active host install, package, command ownership, enforcement, wrapper "
            "self-test, and active-dispatch coverage gap. Read-only."
        )
        frontmatter = skill.split("---\n", 2)[1]
        description = next(
            line.removeprefix("description: ")
            for line in frontmatter.splitlines()
            if line.startswith("description: ")
        )
        self.assertEqual(description.strip('"'), expected_description)
        self.assertEqual(doctor["description"], expected_description)
        self.assertIn(f"| `/ca-doctor` | {expected_description} |", index)
        self.assertIn("structured Pi doctor report", skill)
        self.assertIn("H-03", skill)
        self.assertIn("wrapper-self-test", skill)
        self.assertIn("active-dispatch", skill)
        self.assertIn("does not traverse Pi's active dispatcher", skill)
        self.assertNotIn("live-fire", skill)
        self.assertNotIn("active wrapped Pi bash executor", skill)
        self.assertNotIn("Restart the Codex session", skill)
        self.assertNotIn("codex plugin", skill)

    def test_claude_and_codex_doctor_live_fire_surface_remains_exact(self):
        expected_description = (
            "Verify the active host install, package, command ownership, enforcement, and harmless "
            "live-fire probe. Read-only."
        )
        claude = (REPO / "plugins" / "ca" / "commands" / "doctor.md").read_text(encoding="utf-8")
        codex = (
            REPO / "plugins" / "ca-codex" / "skills" / "ca-doctor" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn(f"description: {expected_description}\n", claude)
        self.assertIn(f"description: {expected_description}\n", codex)
        for text in (claude, codex):
            self.assertIn("live-fire", text)
            self.assertNotIn("wrapper-self-test", text)
            self.assertNotIn("active-dispatch", text)

    def test_plan_covers_pi_ac_28_without_fabricating_active_dispatch_claim(self):
        plan = (REPO / ".codearbiter" / "plans" / "pi-support.md").read_text(encoding="utf-8")
        ledger = next(line for line in plan.splitlines() if "PI-AC-28 doctor coverage" in line)
        task_5 = plan.split("### Task 5:", 1)[1].split("### Task 6:", 1)[0]
        self.assertTrue(ledger.endswith("| COVERED |"), ledger)
        self.assertIn("**Status:** ACCEPTED", task_5)
        self.assertIn("wrapper self-test", task_5)
        self.assertIn("active dispatcher", task_5)
        self.assertIn("explicit DEGRADED parity", task_5)
        self.assertNotIn("active wrapped bash executor", task_5)
        self.assertNotIn("runs a real non-mutating H-03 probe", task_5)


if __name__ == "__main__":
    unittest.main(verbosity=2)

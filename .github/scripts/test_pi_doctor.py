#!/usr/bin/env python3
"""Task 5 Pi doctor and shared Git-backstop integration contract."""

import json
import os
import re
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


def resolve_posix_shell():
    direct = shutil.which("sh")
    if direct:
        return direct
    git = shutil.which("git")
    if git and os.name == "nt":
        git_dir = Path(git).resolve().parent
        for candidate in (
            git_dir / "sh.exe",
            git_dir.parent / "bin" / "sh.exe",
            git_dir.parent / "usr" / "bin" / "sh.exe",
        ):
            if candidate.is_file():
                return str(candidate)
    raise AssertionError("A POSIX sh executable is required for the real Git-hook probe")


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
        dropin = self.root / ".git" / "codearbiter-hooksd"
        entry = dropin / f"ca-{final_host}.path" if final_host != "claude" else dropin / "ca.path"
        self.assertEqual(entry.read_text(encoding="utf-8").strip(), expected)
        for phase in ("pre-commit", "pre-push"):
            body = (self.hook_path() / phase).read_text(encoding="utf-8")
            self.assertEqual(body.count("codeArbiter-managed git hook"), 1)
            self.assertIn(str(dropin).replace("\\", "/"), body.replace("\\", "/"))
            self.assertNotIn(expected, body.replace("\\", "/"))
        (self.root / "probe.txt").write_text("Task 5 subprocess enforcement\n", encoding="utf-8")
        run(["git", "add", "probe.txt"], self.root)
        blocked = run(["git", "commit", "-m", "task 5 hook probe"], self.root, check=False)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("[H-01]", blocked.stdout + blocked.stderr)
        push_input = f"refs/heads/main {'1' * 40} refs/heads/main {'0' * 40}\n"
        pushed = run(
            [resolve_posix_shell(), self.hook_path() / "pre-push", "origin", "fixture"],
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
    def test_pi_doctor_exposes_only_closed_footer_and_background_health_facts(self):
        doctor = (REPO / "plugins" / "ca-pi" / "tools" / "src" / "doctor.ts").read_text(
            encoding="utf-8"
        )
        self.assertIn("footer: { expected: boolean; initialized: boolean }", doctor)
        self.assertIn("background: { expected: boolean; initialized: boolean; healthy: boolean }", doctor)
        declarations = re.findall(
            r"^  (?:footer|background): \{[^\n]+\};$", doctor, flags=re.MULTILINE
        )
        self.assertEqual(declarations, [
            "  footer: { expected: boolean; initialized: boolean };",
            "  background: { expected: boolean; initialized: boolean; healthy: boolean };",
        ])
        self.assertIn('diagnosis(\n      "footer"', doctor)
        self.assertIn('diagnosis(\n      "background"', doctor)
        self.assertIn("run /ca-doctor before launching another background job", doctor)

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
        catalog_document = json.loads(
            (REPO / "plugins" / "ca-pi" / "generated" / "command-catalog.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(catalog_document["schemaVersion"], 1)
        catalog = catalog_document["commands"].values()
        index = (REPO / "plugins" / "ca-pi" / "SKILLS.md").read_text(
            encoding="utf-8"
        )
        self.assertFalse((REPO / "plugins" / "ca-pi" / "skills" / "INDEX.md").exists())
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


PACKAGE_OK = "package.json declares only the ca-pi extension and generated skills"
PACKAGE_FAIL = "package.json has an invalid ca-pi package/discovery contract"


class PiPackageIdentity(unittest.TestCase):
    """HW-03 (HOOK-F03): the Python doctor compared the manifest name with a
    bare `ca-pi` literal while the real package is `@arbiterforge/ca-pi`, so
    every legitimate install was told to reinstall. The identity now comes
    from the Pi host's own `adapter_name`. Exercised against the source
    layout AND an actual `npm pack` artifact of the repository root."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="ca-pi-doctor-pack-")
        base = Path(cls.temp.name)
        npm = shutil.which("npm")
        if npm is None:
            raise AssertionError("npm is required to pack the installed candidate")
        packed = run([npm, "pack", "--pack-destination", base, "--silent"], REPO)
        tarball = base / packed.stdout.strip().splitlines()[-1]
        import tarfile
        with tarfile.open(tarball) as archive:
            archive.extractall(base / "extract", filter="data")
        cls.packaged_root = base / "extract" / "package" / "plugins" / "ca-pi"
        cls.workdir = base / "work"
        cls.workdir.mkdir()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def doctor(self, plugin_root):
        result = run([sys.executable, Path(plugin_root) / "hooks" / "doctor.py"],
                     self.workdir, check=False)
        return result.stdout + result.stderr

    def mutated_copy(self, mutate):
        target = Path(tempfile.mkdtemp(prefix="ca-pi-mut-", dir=self.temp.name))
        shutil.copytree(self.packaged_root, target / "ca-pi")
        manifest = target / "ca-pi" / "package.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        mutate(data)
        manifest.write_text(json.dumps(data), encoding="utf-8")
        return target / "ca-pi"

    def test_packaged_candidate_is_the_real_scoped_package(self):
        manifest = json.loads((self.packaged_root / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "@arbiterforge/ca-pi")

    def test_source_layout_passes_identity(self):
        output = self.doctor(REPO / "plugins" / "ca-pi")
        self.assertIn(PACKAGE_OK, output)
        self.assertNotIn(PACKAGE_FAIL, output)

    def test_packaged_candidate_passes_identity(self):
        output = self.doctor(self.packaged_root)
        self.assertIn(PACKAGE_OK, output)
        self.assertNotIn(PACKAGE_FAIL, output)
        self.assertIn("Pi shared core present", output)

    def test_bare_or_foreign_name_is_refused_end_to_end(self):
        """The installed entry point refuses a foreign manifest even before
        the payload check (hostapi.resolve_plugin_root); never a healthy line."""
        for name in ("ca-pi", "@other/ca-pi", "@arbiterforge/ca-pi-extra", ""):
            with self.subTest(name=name):
                root = self.mutated_copy(lambda d, n=name: d.__setitem__("name", n))
                output = self.doctor(root)
                self.assertTrue("adapter manifest mismatch" in output or PACKAGE_FAIL in output,
                                output[-400:])
                self.assertNotIn(PACKAGE_OK, output)

    def test_payload_check_compares_with_the_host_identity(self):
        """check_payload itself, with the real Pi host's identity, on a
        manifest whose name is bare/foreign: the FAIL line, not the OK line."""
        hooks = str(REPO / "plugins" / "ca-pi" / "hooks")
        script = (
            "import sys, json, io, contextlib\n"
            f"sys.path.insert(0, {hooks!r})\n"
            "import hostapi, doctor\n"
            "host = hostapi.load_host()\n"
            "doctor.set_host(host)\n"
            "for root in sys.argv[1:]:\n"
            "    del doctor.results[:]\n"
            "    doctor.check_payload(root, host)\n"
            "    print(json.dumps(' | '.join(f'{s} {l}' for s, l in doctor.results)))\n"
        )
        roots = [self.mutated_copy(lambda d, n=n: d.__setitem__("name", n))
                 for n in ("ca-pi", "@other/ca-pi")] + [self.packaged_root]
        result = run([sys.executable, "-c", script] + roots, self.workdir)
        outputs = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(outputs), 3)
        for output in outputs[:2]:
            self.assertIn(PACKAGE_FAIL, output)
            self.assertNotIn(PACKAGE_OK, output)
        self.assertIn(PACKAGE_OK, outputs[2])

    def test_wrong_discovery_contract_still_fails_independently(self):
        root = self.mutated_copy(
            lambda d: d["pi"].__setitem__("extensions", ["./extensions/other.js"]))
        self.assertIn(PACKAGE_FAIL, self.doctor(root))
        root = self.mutated_copy(lambda d: d["pi"].__setitem__("skills", []))
        self.assertIn(PACKAGE_FAIL, self.doctor(root))

    def test_missing_shared_core_still_fails_its_own_check(self):
        root = self.mutated_copy(lambda d: None)
        (root / "hooks" / "pi-bridge.py").unlink()
        output = self.doctor(root)
        self.assertIn(PACKAGE_OK, output)
        self.assertIn("Pi shared core script(s) missing", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)

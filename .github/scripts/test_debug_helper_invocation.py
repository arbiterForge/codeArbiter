"""Source fixtures and installed-resource process checks for debug helpers.

The disposable installed layout is a process probe, not a qualified package or
host journey. Its records cannot satisfy native acceptance or product scenarios.
"""

import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

import test_debug_qualification as qualification


ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT
LITERAL_ARGS = ("add", "--", "--quoted 'text' \"here\"; $(echo no)", "caf\u00e9 path")
STDIN = b"opaque input\x00with newline\n"
HELPER_SOURCE = r'''import base64
import json
import os
from pathlib import Path
import sys

effect_path = Path(os.environ["T025_EFFECT_FILE"])
previous = json.loads(effect_path.read_text(encoding="utf-8")) if effect_path.exists() else {}
effect = {
    "attempt_count": previous.get("attempt_count", 0) + 1,
    "interpreter": sys.executable,
    "runtime_version": list(sys.version_info[:2]),
    "argv": sys.argv[1:],
    "stdin_b64": base64.b64encode(sys.stdin.buffer.read()).decode("ascii"),
    "cwd": os.getcwd(),
    "plugin_root_tokens": {
        "CLAUDE_PLUGIN_ROOT": os.environ.get("CLAUDE_PLUGIN_ROOT"),
        "PLUGIN_ROOT": os.environ.get("PLUGIN_ROOT"),
    },
}
effect_path.write_text(json.dumps(effect, ensure_ascii=False), encoding="utf-8")
code = int(os.environ["T025_EXIT_CODE"])
if code:
    if os.environ.get("T027_STDOUT"):
        sys.stdout.buffer.write(b"controlled result\n")
    sys.stderr.buffer.write(b"controlled refusal\n")
raise SystemExit(code)
'''


def capture_helper_attempt(scratch, argv, stdin, exit_code=0):
    """Run exactly one probe from an isolated installed-layout fixture."""
    helper = scratch / "installed package caf\u00e9" / "hooks" / "debug-helper-probe.py"
    helper.parent.mkdir(parents=True)
    helper.write_text(HELPER_SOURCE, encoding="utf-8", newline="\n")
    cwd = scratch / "arbitrary cwd" / "nested"
    cwd.mkdir(parents=True)
    effects = scratch / "effects"
    effects.mkdir()
    effect_file = effects / "attempt.json"
    env = os.environ.copy()
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    env.pop("PLUGIN_ROOT", None)
    env.update({
        "T025_EFFECT_FILE": str(effect_file),
        "T025_EXIT_CODE": str(exit_code),
        "PYTHONDONTWRITEBYTECODE": "1",
        "TEMP": str(scratch),
        "TMP": str(scratch),
    })
    result = subprocess.run(
        [sys.executable, "-B", str(helper), *argv],
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=env,
        timeout=5,
        check=False,
    )
    effect = json.loads(effect_file.read_text(encoding="utf-8"))
    return {
        **effect,
        "effect": effect,
        "returncode": result.returncode,
        "stdout": result.stdout.decode("utf-8"),
        "stderr": result.stderr.decode("utf-8"),
        "effect_files": [path.relative_to(scratch).as_posix() for path in effects.rglob("*") if path.is_file()],
        "scratch_root": str(scratch),
    }


class TestDebugHelperInvocation(unittest.TestCase):
    def test_emitted_host_links_reach_installed_card_without_root_tokens(self):
        cases = (
            ("plugins/ca/commands/task.md", "plugins/ca/includes/helper-invocation.md"),
            ("plugins/ca-codex/skills/ca-task/SKILL.md", "plugins/ca-codex/includes/helper-invocation.md"),
            ("plugins/ca-pi/skills/ca-task/SKILL.md", "plugins/ca-pi/includes/helper-invocation.md"),
            ("plugins/ca-pi/includes/pi-host-notes.md", "plugins/ca-pi/includes/helper-invocation.md"),
        )
        for entry_relative, card_relative in cases:
            with self.subTest(entry=entry_relative):
                entry = SOURCE_ROOT / entry_relative
                rendered = entry.read_text(encoding="utf-8")
                links = re.findall(r"\[[^]]*helper-invocation\.md\]\(([^)]+)\)", rendered)
                # Pi names the path relative to its installed skill in code;
                # that path is not a link relative to the canonical template.
                links += re.findall(r"`([^`]+/helper-invocation\.md)`", rendered)
                self.assertEqual(len(links), 1, "emitted entry must name the installed helper card once")
                self.assertEqual(
                    (entry.parent / links[0]).resolve(strict=True),
                    (SOURCE_ROOT / card_relative).resolve(strict=True),
                    "emitted relative link must reach the card in the same installed package",
                )

    @staticmethod
    def _emitted_guidance():
        task = (SOURCE_ROOT / "plugins/ca-codex/skills/ca-task/SKILL.md").read_text(encoding="utf-8")
        if "${PLUGIN_ROOT}/hooks/taskwrite.py" in task:
            raise AssertionError("emitted ca-task still uses the hook-only PLUGIN_ROOT token")
        card = SOURCE_ROOT / "plugins/ca-codex/includes/helper-invocation.md"
        if not card.is_file():
            raise AssertionError("emitted installed-helper invocation resource is absent")
        return task, card.read_text(encoding="utf-8")

    @staticmethod
    def _fence(document, heading, language):
        expression = rf"(?m)^### {re.escape(heading)}\n```{re.escape(language)}\n(.*?)\n```"
        match = re.search(expression, document, re.DOTALL)
        if match is None:
            raise AssertionError(f"emitted {heading} {language} invocation is absent")
        return match.group(1)

    @staticmethod
    def _optional_fence(document, heading, language):
        expression = rf"(?m)^### {re.escape(heading)}\n```{re.escape(language)}\n(.*?)\n```"
        match = re.search(expression, document, re.DOTALL)
        return match.group(1) if match else ""

    @staticmethod
    def _interpreter_candidates(scratch, mode):
        """Put controlled application candidates on PATH, never a fake helper."""
        bin_dir = scratch / "interpreter candidates"
        bin_dir.mkdir()
        if os.name == "nt":
            def candidate(name, behavior):
                if behavior == "minor":
                    shutil.copy2(sys.executable, bin_dir / f"{name}.exe")
                    for pattern in ("python*.dll", "vcruntime*.dll"):
                        for library in Path(sys.base_prefix).glob(pattern):
                            shutil.copy2(library, bin_dir / library.name)
                    return
                if behavior == "real":
                    body = f'@echo off\r\n"{sys.executable}" %*\r\nexit /b %errorlevel%\r\n'
                elif behavior == "stub":
                    body = '@echo off\r\necho Python launcher unavailable 1>&2\r\nexit /b 1\r\n'
                else:
                    body = '@echo off\r\necho Python 2.7\r\nexit /b 0\r\n'
                (bin_dir / f"{name}.cmd").write_text(body, encoding="ascii")
        else:
            dirname = shutil.which("dirname")
            if dirname is None:
                raise AssertionError("POSIX installed-resource test requires dirname")
            # Preserve executable mode, not macOS system-file flags.
            shutil.copy(dirname, bin_dir / "dirname")
            def candidate(name, behavior):
                source = sys.executable if behavior in ("real", "minor") else ("/usr/bin/false" if behavior == "stub" else "/usr/bin/true")
                shutil.copy(source, bin_dir / name)
        layouts = {
            "primary": {"python3": "real", "python": "stub"},
            "alternate": {"python3": "stub", "python": "real"},
            "missing": {},
            "stub": {"python3": "stub", "python": "stub"},
            "incompatible": {"python3": "incompatible", "python": "stub"},
            "minor_alternate": {"python3": "minor", "python": "real"},
        }
        for name, behavior in layouts[mode].items():
            candidate(name, behavior)
        if mode == "minor_alternate":
            (bin_dir / "sitecustomize.py").write_text(
                "import os, sys\n"
                "if os.path.basename(sys.executable).lower() in ('python3', 'python3.exe'):\n"
                "    sys.version_info = (3, 7, 0, 'final', 0)\n",
                encoding="utf-8", newline="\n",
            )
        return bin_dir

    def _run_emitted_task_add(self, scratch, helper_present, *, interpreter_mode=None, exit_code=0):
        task, card = self._emitted_guidance()
        package = scratch / "installed package caf\u00e9"
        skill = package / "skills" / "ca-task" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(task, encoding="utf-8")
        helper = package / "hooks" / "taskwrite.py"
        helper.parent.mkdir(parents=True)
        if helper_present:
            helper.write_text(HELPER_SOURCE, encoding="utf-8", newline="\n")
        marker = package / ".codex-plugin" / "plugin.json"
        marker.parent.mkdir()
        marker.write_text('{"name":"ca-codex"}', encoding="utf-8")
        cwd = scratch / "arbitrary cwd" / "nested"
        cwd.mkdir(parents=True)
        effects = scratch / "effects"
        effects.mkdir()
        effect_file = effects / "attempt.json"
        env = os.environ.copy()
        env.pop("CLAUDE_PLUGIN_ROOT", None)
        env.pop("PLUGIN_ROOT", None)
        env.update({
            "T025_EFFECT_FILE": str(effect_file),
            "T025_EXIT_CODE": str(exit_code),
            "T026_LOADED_RESOURCE": str(skill),
            "T026_PYTHON": sys.executable,
            "T026_TEXT": LITERAL_ARGS[2],
            "PYTHONDONTWRITEBYTECODE": "1",
            "TEMP": str(scratch),
            "TMP": str(scratch),
        })
        if exit_code:
            env["T027_STDOUT"] = "1"
        if interpreter_mode is not None:
            candidate_bin = self._interpreter_candidates(scratch, interpreter_mode)
            env["T027_STDOUT"] = "1"
            if interpreter_mode == "minor_alternate":
                env["PYTHONPATH"] = str(candidate_bin)
                env["PYTHONHOME"] = sys.base_prefix
            if os.name == "nt":
                system_root = os.environ.get("SystemRoot", r"C:\Windows")
                env["PATH"] = os.pathsep.join((str(candidate_bin), str(Path(system_root) / "System32")))
            else:
                env["PATH"] = str(candidate_bin)
        if os.name == "nt":
            shell = shutil.which("pwsh")
            self.assertIsNotNone(shell, "Windows installed-resource test requires PowerShell 7")
            resolve = self._fence(card, "Codex PowerShell resolution", "powershell")
            invoke = self._fence(task, "PowerShell add invocation", "powershell")
            select = self._optional_fence(card, "Codex PowerShell interpreter selection", "powershell") if interpreter_mode is not None else ""
            bindings = "\n".join((
                "$ErrorActionPreference = 'Stop'",
                "$caLoadedResource = $env:T026_LOADED_RESOURCE",
                "$caHelperRelative = 'hooks/taskwrite.py'",
                "$caPython = ''" if interpreter_mode is not None else "$caPython = $env:T026_PYTHON",
                "$caDescription = $env:T026_TEXT",
            ))
            command = [shell, "-NoProfile", "-NonInteractive", "-Command", "\n".join((bindings, resolve, select, invoke))]
        else:
            shell = shutil.which("sh")
            self.assertIsNotNone(shell, "installed-resource test requires POSIX sh")
            resolve = self._fence(card, "Codex POSIX resolution", "sh")
            invoke = self._fence(task, "POSIX add invocation", "sh")
            select = self._optional_fence(card, "Codex POSIX interpreter selection", "sh") if interpreter_mode is not None else ""
            bindings = "\n".join((
                "set -eu",
                "PATH=/usr/bin:$PATH" if interpreter_mode is None else "PATH=$PATH",
                "ca_loaded_resource=$T026_LOADED_RESOURCE",
                "ca_helper_relative=hooks/taskwrite.py",
                "ca_python=''" if interpreter_mode is not None else "ca_python=$T026_PYTHON",
                "ca_description=$T026_TEXT",
            ))
            command = [shell, "-c", "\n".join((bindings, resolve, select, invoke))]
        result = subprocess.run(
            command, input=b"", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=cwd, env=env, timeout=10, check=False,
        )
        effect = json.loads(effect_file.read_text(encoding="utf-8")) if effect_file.exists() else None
        return result, effect, helper

    def test_interpreter_is_validated_before_helper_invocation(self):
        for mode, should_invoke in (("primary", True), ("alternate", True),
                                    ("missing", False), ("stub", False),
                                    ("incompatible", False)):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(prefix="t027-interpreter-", dir=ROOT) as owned:
                result, effect, _ = self._run_emitted_task_add(
                    Path(owned), helper_present=True, interpreter_mode=mode,
                )
                diagnostic = (result.stdout + result.stderr).decode("utf-8", errors="replace")
                if should_invoke:
                    self.assertEqual(result.returncode, 0, diagnostic)
                    self.assertIsNotNone(effect, "compatible Python 3 must reach the installed helper")
                    self.assertEqual(effect["attempt_count"], 1)
                    self.assertEqual(effect["argv"], ["add", "--", LITERAL_ARGS[2]])
                else:
                    self.assertNotEqual(result.returncode, 0, "no compatible Python 3 must block")
                    self.assertIsNone(effect, "invalid interpreter must be rejected before helper")
                    self.assertIn("compatible Python 3", diagnostic)

    def test_helper_failure_preserves_original_error_without_second_attempt(self):
        with tempfile.TemporaryDirectory(prefix="t027-refusal-", dir=ROOT) as owned:
            result, effect, _ = self._run_emitted_task_add(
                Path(owned), helper_present=True, exit_code=7,
            )
            self.assertIsNotNone(effect, "controlled refusal must come from the installed helper")
            self.assertEqual(effect["attempt_count"], 1, "do not replay under another interpreter")
            self.assertEqual(effect["argv"], ["add", "--", LITERAL_ARGS[2]])
            self.assertEqual(result.returncode, 7, "preserve the writer's first exit code")
            self.assertEqual(result.stdout, b"controlled result\n")
            self.assertEqual(result.stderr, b"controlled refusal\n")

    def test_incompatible_minor_is_rejected_before_helper_invocation(self):
        with tempfile.TemporaryDirectory(prefix="t027-minor-", dir=ROOT) as owned:
            result, effect, _ = self._run_emitted_task_add(
                Path(owned), helper_present=True, interpreter_mode="minor_alternate",
            )
            diagnostic = (result.stdout + result.stderr).decode("utf-8", errors="replace")
            self.assertEqual(result.returncode, 0, diagnostic)
            self.assertIsNotNone(effect, "compatible alternate must run the installed helper")
            self.assertEqual(effect["attempt_count"], 1)
            self.assertEqual(effect["argv"], ["add", "--", LITERAL_ARGS[2]])
            self.assertGreaterEqual(effect["runtime_version"], [3, 8],
                                    "Python 3.7 cannot import the installed debug validator")
            self.assertEqual(Path(effect["interpreter"]).name.lower(),
                             "python.exe" if os.name == "nt" else "python")

    def test_installed_resource_resolution_handles_absent_tokens_and_arbitrary_cwd(self):
        with tempfile.TemporaryDirectory(prefix="t026-installed-", dir=ROOT) as owned:
            result, effect, helper = self._run_emitted_task_add(Path(owned), helper_present=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
            self.assertIsNotNone(effect, "literal emitted invocation must reach the installed helper")
            self.assertEqual(effect["attempt_count"], 1)
            self.assertEqual(effect["argv"], ["add", "--", LITERAL_ARGS[2]])
            self.assertEqual(effect["plugin_root_tokens"], {"CLAUDE_PLUGIN_ROOT": None, "PLUGIN_ROOT": None})
            self.assertEqual(Path(effect["cwd"]), Path(owned) / "arbitrary cwd" / "nested")
            self.assertTrue(helper.is_file())

    def test_missing_helper_never_falls_back_to_source_or_cache_search(self):
        with tempfile.TemporaryDirectory(prefix="t026-missing-", dir=ROOT) as owned:
            scratch = Path(owned)
            for relative in ("source clone/hooks/taskwrite.py", "plugin cache/hooks/taskwrite.py"):
                decoy = scratch / relative
                decoy.parent.mkdir(parents=True)
                decoy.write_text(HELPER_SOURCE, encoding="utf-8", newline="\n")
            result, effect, helper = self._run_emitted_task_add(scratch, helper_present=False)
            self.assertFalse(helper.exists())
            self.assertNotEqual(result.returncode, 0, "missing installed helper must fail closed")
            self.assertIsNone(effect, "no source or cache decoy may run")
            diagnostic = (result.stdout + result.stderr).decode("utf-8", errors="replace")
            self.assertIn("installed helper missing", diagnostic.lower())

    def test_posix_resolution_rejects_missing_or_relative_loaded_resource(self):
        task, card = self._emitted_guidance()
        resolve = self._fence(card, "Codex POSIX resolution", "sh")
        invoke = self._fence(task, "POSIX add invocation", "sh")
        if os.name == "nt":
            shell = Path(shutil.which("sh") or r"C:\Program Files\Git\usr\bin\sh.exe")
            self.assertTrue(shell.is_file(), "Windows POSIX fixture requires installed Git sh")

            def shell_path(path):
                absolute = Path(path).resolve()
                return "/" + absolute.drive[0].lower() + absolute.as_posix()[2:]
        else:
            shell = shutil.which("sh")
            self.assertIsNotNone(shell, "POSIX fixture requires sh")

            def shell_path(path):
                return str(Path(path).resolve())

        with tempfile.TemporaryDirectory(prefix="t026-posix-resource-", dir=ROOT) as owned:
            scratch = Path(owned)
            package = scratch / "installed package caf\u00e9"
            skill = package / "skills" / "ca-task" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(task, encoding="utf-8")
            missing_skill = package / "skills" / "ca-debug" / "SKILL.md"
            missing_skill.parent.mkdir(parents=True)
            marker = package / ".codex-plugin" / "plugin.json"
            marker.parent.mkdir()
            marker.write_text('{"name":"ca-codex"}', encoding="utf-8")
            helper = package / "hooks" / "taskwrite.py"
            helper.parent.mkdir()
            helper.write_text(HELPER_SOURCE, encoding="utf-8", newline="\n")
            effects = scratch / "effects"
            effects.mkdir()
            arbitrary = scratch / "arbitrary cwd" / "nested"
            arbitrary.mkdir(parents=True)
            bindings = "\n".join((
                "set -eu",
                "PATH=/usr/bin:$PATH",
                "ca_loaded_resource=$T026_LOADED_RESOURCE",
                "ca_helper_relative=hooks/taskwrite.py",
                "ca_python=$T026_PYTHON",
                "ca_description=$T026_TEXT",
            ))
            script = "\n".join((bindings, resolve, invoke))
            for label, resource, cwd, expected_valid in (
                ("valid absolute entry", shell_path(skill), arbitrary, True),
                ("missing absolute entry", shell_path(missing_skill), arbitrary, False),
                ("relative entry", "skills/ca-task/SKILL.md", package, False),
            ):
                with self.subTest(label=label):
                    effect_file = effects / (label.replace(" ", "-") + ".json")
                    env = os.environ.copy()
                    env.pop("CLAUDE_PLUGIN_ROOT", None)
                    env.pop("PLUGIN_ROOT", None)
                    env.update({
                        "T025_EFFECT_FILE": str(effect_file),
                        "T025_EXIT_CODE": "0",
                        "T026_LOADED_RESOURCE": resource,
                        "T026_PYTHON": shell_path(sys.executable),
                        "T026_TEXT": LITERAL_ARGS[2],
                        "PYTHONDONTWRITEBYTECODE": "1",
                        "TEMP": str(scratch),
                        "TMP": str(scratch),
                    })
                    if os.name == "nt":
                        env["PATH"] = str(shell.parent) + os.pathsep + env.get("PATH", "")
                    result = subprocess.run(
                        [str(shell), "-c", script], input=b"", stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, cwd=cwd, env=env, timeout=10, check=False,
                    )
                    diagnostic = (result.stdout + result.stderr).decode("utf-8", errors="replace")
                    if expected_valid:
                        self.assertEqual(result.returncode, 0, diagnostic)
                        self.assertTrue(effect_file.exists(), "valid emitted POSIX call must run installed helper")
                        effect = json.loads(effect_file.read_text(encoding="utf-8"))
                        self.assertEqual(effect["argv"], ["add", "--", LITERAL_ARGS[2]])
                        self.assertEqual(effect["attempt_count"], 1)
                    else:
                        self.assertNotEqual(result.returncode, 0, "invalid loaded entry must stop")
                        self.assertFalse(effect_file.exists(), "invalid entry must not execute helper")
                        self.assertIn("loaded installed resource", diagnostic.lower())

    def test_subprocess_fixtures_capture_real_helper_attempts_and_literal_argv(self):
        with tempfile.TemporaryDirectory(prefix="t025-attempt-", dir=ROOT) as owned:
            observation = capture_helper_attempt(Path(owned), LITERAL_ARGS, STDIN)
            self.assertIsInstance(observation, dict, "fixture must run and observe a child process")
            self.assertEqual(observation["attempt_count"], 1)
            self.assertEqual(observation["argv"], list(LITERAL_ARGS))
            self.assertEqual(base64.b64decode(observation["stdin_b64"]), STDIN)
            self.assertEqual(observation["cwd"], str(Path(owned) / "arbitrary cwd" / "nested"))
            self.assertEqual(observation["plugin_root_tokens"], {"CLAUDE_PLUGIN_ROOT": None, "PLUGIN_ROOT": None})
            self.assertEqual(observation["returncode"], 0)

    def test_fixture_records_owned_scratch_and_observed_effects(self):
        with tempfile.TemporaryDirectory(prefix="t025-effects-", dir=ROOT) as owned:
            scratch = Path(owned)
            observation = capture_helper_attempt(scratch, LITERAL_ARGS, STDIN, exit_code=7)
            self.assertIsInstance(observation, dict, "fixture must record a real refused helper process")
            self.assertEqual(observation["returncode"], 7)
            self.assertEqual(observation["stdout"], "")
            self.assertEqual(observation["stderr"], "controlled refusal\n")
            self.assertEqual(observation["attempt_count"], 1)
            self.assertEqual(observation["effect_files"], ["effects/attempt.json"])
            self.assertEqual(observation["scratch_root"], str(scratch))
            self.assertEqual(observation["effect"]["argv"], list(LITERAL_ARGS))
            self.assertEqual(base64.b64decode(observation["effect"]["stdin_b64"]), STDIN)

    def _run_emitted_literal_call(self, scratch, *, shell_kind, heading, document,
                                  description=None, stdin=b""):
        """Execute one emitted fence against a disposable installed helper."""
        package = scratch / "installed package caf\u00e9"
        skill = package / "skills" / "ca-task" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("installed task entry\n", encoding="utf-8")
        helper = package / "hooks" / "taskwrite.py"
        helper.parent.mkdir(parents=True)
        helper.write_text(HELPER_SOURCE, encoding="utf-8", newline="\n")
        marker = package / ".codex-plugin" / "plugin.json"
        marker.parent.mkdir()
        marker.write_text('{"name":"ca-codex"}', encoding="utf-8")
        cwd = scratch / "arbitrary cwd" / "nested"
        cwd.mkdir(parents=True)
        effects = scratch / "effects"
        effects.mkdir()
        effect_file = effects / "attempt.json"
        env = os.environ.copy()
        env.pop("CLAUDE_PLUGIN_ROOT", None)
        env.pop("PLUGIN_ROOT", None)
        env.update({
            "T025_EFFECT_FILE": str(effect_file),
            "T025_EXIT_CODE": "0",
            "T026_TEXT": description or "",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TEMP": str(scratch),
            "TMP": str(scratch),
        })
        if shell_kind == "powershell":
            shell = shutil.which("pwsh")
            self.assertIsNotNone(shell, "literal invocation requires PowerShell 7")
            bindings = "\n".join((
                "$ErrorActionPreference = 'Stop'",
                "$caPython = $env:T028_PYTHON",
                "$caHelper = $env:T028_HELPER",
                "$caDescription = $env:T026_TEXT",
                "$caId = 'debug.note'",
                "$caOrigin = '-review'",
                "$caBoundaries = 'security,network'",
            ))
            env.update({"T028_PYTHON": sys.executable, "T028_HELPER": str(helper)})
            command = [shell, "-NoProfile", "-NonInteractive", "-Command",
                       "\n".join((bindings, self._fence(document, heading, "powershell")))]
        else:
            shell = Path(shutil.which("sh") or r"C:\Program Files\Git\usr\bin\sh.exe") if os.name == "nt" else shutil.which("sh")
            self.assertTrue(shell and Path(shell).is_file(), "literal invocation requires installed POSIX sh")

            def shell_path(path):
                absolute = Path(path).resolve()
                if os.name == "nt":
                    return "/" + absolute.drive[0].lower() + absolute.as_posix()[2:]
                return str(absolute)

            bindings = "\n".join((
                "set -eu",
                "ca_python=$T028_PYTHON",
                "ca_helper=$T028_HELPER",
                "ca_description=$T026_TEXT",
                "ca_id=debug.note",
                "ca_origin=-review",
                "ca_boundaries=security,network",
            ))
            env.update({"T028_PYTHON": shell_path(sys.executable),
                        "T028_HELPER": shell_path(helper)})
            if os.name == "nt":
                env["PATH"] = str(Path(shell).parent) + os.pathsep + env.get("PATH", "")
            command = [shell, "-c", "\n".join((bindings, self._fence(document, heading, "sh")))]
        result = subprocess.run(command, input=stdin, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, cwd=cwd, env=env,
                                timeout=10, check=False)
        effect = json.loads(effect_file.read_text(encoding="utf-8")) if effect_file.exists() else None
        return result, effect

    def test_quotes_hyphens_metacharacters_and_unicode_remain_literal(self):
        task, _ = self._emitted_guidance()
        descriptions = (
            "--quoted 'text' \"here\"; $(echo no) caf\u00e9 path",
            "- leading * ? ` $HOME ; & | < > snowman \u2603",
        )
        for shell_kind in ("powershell", "posix"):
            if shell_kind == "powershell" and os.name != "nt":
                continue
            heading = "PowerShell add with options" if shell_kind == "powershell" else "POSIX add with options"
            for description in descriptions:
                with self.subTest(shell=shell_kind, description=description), \
                        tempfile.TemporaryDirectory(prefix="t028-literal-", dir=ROOT) as owned:
                    result, effect = self._run_emitted_literal_call(
                        Path(owned), shell_kind=shell_kind, heading=heading,
                        document=task, description=description,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
                    self.assertIsNotNone(effect, "emitted call must reach one installed helper")
                    self.assertEqual(effect["attempt_count"], 1)
                    self.assertEqual(effect["argv"], ["add", "--id", "debug.note",
                                                    "--from=-review", "--boundaries",
                                                    "security,network", "--", description])

    def test_options_precede_separator_and_stdin_remains_bounded(self):
        _, card = self._emitted_guidance()
        # This is the caller's finite transport input. T029 owns the real
        # validator's 65,537-byte rejection; this probe only observes delivery.
        packet = (b'{"text":"caf\xc3\xa9\\n"}\x00' * 3800)[:65536]
        self.assertLessEqual(len(packet), 65536)
        for shell_kind in ("powershell", "posix"):
            if shell_kind == "powershell" and os.name != "nt":
                continue
            heading = "Codex PowerShell validate invocation" if shell_kind == "powershell" else "Codex POSIX validate invocation"
            with self.subTest(shell=shell_kind), \
                    tempfile.TemporaryDirectory(prefix="t028-stdin-", dir=ROOT) as owned:
                result, effect = self._run_emitted_literal_call(
                    Path(owned), shell_kind=shell_kind, heading=heading,
                    document=card, stdin=packet,
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
                self.assertIsNotNone(effect, "emitted call must reach one installed helper")
                self.assertEqual(effect["attempt_count"], 1)
                self.assertEqual(effect["argv"], ["validate"])
                self.assertEqual(base64.b64decode(effect["stdin_b64"]), packet)

    def _actual_validator_fixture(self, scratch):
        """Install the generated Codex resources and real validator, byte for byte."""
        package = scratch / "installed package café"
        for relative in (
            ".codex-plugin/plugin.json", "skills/ca-debug/SKILL.md",
            "includes/helper-invocation.md", "hooks/debug-handoff.py",
            "hooks/_debughandofflib.py",
        ):
            source = SOURCE_ROOT / "plugins/ca-codex" / relative
            self.assertTrue(source.is_file(), f"missing generated installed resource: {relative}")
            target = package / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            target.chmod(0o444)
            self.assertEqual(target.stat().st_mode & 0o222, 0,
                             "installed resource must have read-only file mode")
        project = scratch / "unrelated project café" / "nested"
        project.mkdir(parents=True)
        (project / "sentinel.txt").write_text("unchanged", encoding="utf-8")
        return package, project

    @staticmethod
    def _actual_validator_guard(scratch, package, shell_kind=None):
        """Observe each Python child and reject effects at the actual process boundary."""
        if shell_kind is None:
            shell_kind = "powershell" if os.name == "nt" else "posix"
        card = (package / "includes/helper-invocation.md").read_text(encoding="utf-8")
        if shell_kind == "powershell":
            selection = TestDebugHelperInvocation._fence(
                card, "Codex PowerShell interpreter selection", "powershell")
            probes = re.findall(r'-B -c "([^"]+)"', selection)
        else:
            selection = TestDebugHelperInvocation._fence(
                card, "Codex POSIX interpreter selection", "sh")
            probes = re.findall(r"-B -c '([^']+)'", selection)
        if len(probes) != 2:
            raise AssertionError("emitted interpreter selection must have two bounded probes")
        instrument = scratch / "instrumentation"
        instrument.mkdir()
        effects = scratch / "observed processes"
        effects.mkdir()
        (instrument / "sitecustomize.py").write_text(
            "import atexit, json, os, sys, time\n"
            "from pathlib import Path\n"
            "events=[]\n"
            "commands=[]\n"
            f"expected_probes={probes!r}\n"
            "started_ns=time.monotonic_ns()\n"
            "installed=os.path.normcase(os.path.realpath(os.environ['T029_INSTALLED']))\n"
            "instrument=os.path.normcase(os.path.realpath(os.path.dirname(__file__)))\n"
            "observer=os.path.normcase(os.path.realpath(os.environ['T029_EFFECTS']))\n"
            "guarded=sys.argv[0]!='-c' or os.environ.get('T029_GUARD_CONTROL')=='1'\n"
            "roots=(installed,instrument,os.path.normcase(os.path.realpath(sys.prefix)),"
            "os.path.normcase(os.path.realpath(sys.base_prefix)))\n"
            "def permitted(path):\n"
            " full=os.path.normcase(os.path.realpath(os.fsdecode(path)))\n"
            " return any(full==r or full.startswith(r+os.sep) for r in roots)\n"
            "def audit(event,args):\n"
            " if event=='cpython.run_command':\n"
            "  command=os.fsdecode(args[0])\n"
            "  if command.endswith('\\n'): command=command[:-1]\n"
            "  commands.append(expected_probes.index(command) if command in expected_probes else -1)\n"
            "  return\n"
            " if not guarded: return\n"
            " if event in ('subprocess.Popen','os.system','socket.__new__','socket.connect',"
            "'socket.bind','os.mkdir','os.remove','os.rename','os.rmdir','os.chmod','os.chown'):\n"
            "  events.append(event); raise RuntimeError('T029 forbidden effect')\n"
            " if event=='open':\n"
            "  path=args[0]; mode=args[1] if len(args)>1 else 'r'; flags=args[2] if len(args)>2 else 0\n"
            "  if isinstance(path,(str,bytes)) and os.path.normcase(os.path.realpath(os.fsdecode(path))).startswith(observer+os.sep): return\n"
            "  if (mode and any(c in str(mode) for c in 'wax+') or isinstance(flags,int)"
            " and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):\n"
            "   events.append('write'); raise RuntimeError('T029 forbidden effect')\n"
            "  if isinstance(path,(str,bytes)) and not permitted(path):\n"
            "   events.append('external read'); raise RuntimeError('T029 forbidden effect')\n"
            " if event in ('os.listdir','os.scandir') and not permitted(args[0]):\n"
            "  events.append('external directory read'); raise RuntimeError('T029 forbidden effect')\n"
            "sys.addaudithook(audit)\n"
            "if os.environ.get('T029_FORCE_INPUT_IO')=='1':\n"
            " class Fault:\n"
            "  def read(self,size=-1): raise OSError('T029_PRIVATE_PACKET_CANARY')\n"
            " class Input:\n"
            "  buffer=Fault()\n"
            " sys.stdin=Input()\n"
            "def record():\n"
            " path=Path(os.environ['T029_EFFECTS']) / (str(os.getpid())+'.json')\n"
            " path.write_text(json.dumps({'argv':sys.argv,'cwd':os.getcwd(),'events':events,"
            "'commands':commands,'started_ns':started_ns}),encoding='utf-8')\n"
            "atexit.register(record)\n", encoding="utf-8", newline="\n")
        return instrument, effects

    def _assert_single_actual_validator(self, observed):
        invoked = [row for row in observed if row["argv"] and
                   Path(row["argv"][0]).name == "debug-handoff.py"]
        self.assertEqual(len(invoked), 1, observed)
        self.assertEqual(invoked[0]["argv"][1:], ["validate"])
        probes = [row for row in observed if row["argv"] == ["-c"]]
        self.assertEqual(len(probes), 2, "emitted selection must make only its two probes")
        self.assertEqual(sorted(code for row in probes for code in row["commands"]),
                         [0, 1], "only the two emitted probe bodies may run")
        self.assertTrue(all(row["started_ns"] < invoked[0]["started_ns"]
                            for row in probes), "no interpreter probe may follow the helper")
        self.assertEqual(len(observed), 3, "no fallback child may run after selection")
        self.assertTrue(all(not row["events"] for row in observed), observed)

    @staticmethod
    def _actual_valid_packet():
        data = json.loads((SOURCE_ROOT / ".github/fixtures/debug/handoff-examples.json")
                          .read_text(encoding="utf-8"))
        packet = json.loads(base64.b64decode(
            next(row["payload_b64"] for row in data["examples"]
                 if row["id"] == "valid-code-defect-existing-red")))
        packet["symptom"]["expected"] = "T029_PRIVATE_PACKET_CANARY"
        return json.dumps(packet, ensure_ascii=False).encode("utf-8")

    def _run_actual_validator(self, scratch, package, project, payload, *, instrument=None,
                              effects=None, shell_kind=None, force_input_io=False):
        if shell_kind is None:
            shell_kind = "powershell" if os.name == "nt" else "posix"
        resource = package / "skills/ca-debug/SKILL.md"
        card = (package / "includes/helper-invocation.md").read_text(encoding="utf-8")
        if shell_kind == "powershell":
            shell = shutil.which("pwsh")
            self.assertIsNotNone(shell, "literal PowerShell invocation requires pwsh")
            bindings = "\n".join((
                "$ErrorActionPreference = 'Stop'",
                "$caLoadedResource = $env:T029_RESOURCE",
                "$caHelperRelative = 'hooks/debug-handoff.py'",
            ))
            script = "\n".join((bindings,
                self._fence(card, "Codex PowerShell interpreter selection", "powershell"),
                self._fence(card, "Codex PowerShell resolution", "powershell"),
                self._fence(card, "Codex PowerShell validate invocation", "powershell")))
            command = [shell, "-NoProfile", "-NonInteractive", "-Command", script]
        else:
            shell = shutil.which("sh") or (r"C:\Program Files\Git\usr\bin\sh.exe" if os.name == "nt" else None)
            self.assertTrue(shell and Path(shell).is_file(), "literal POSIX invocation requires sh")
            bindings = "\n".join(("set -eu", "ca_loaded_resource=$T029_RESOURCE",
                                   "ca_helper_relative=hooks/debug-handoff.py"))
            script = "\n".join((bindings,
                self._fence(card, "Codex POSIX interpreter selection", "sh"),
                self._fence(card, "Codex POSIX resolution", "sh"),
                self._fence(card, "Codex POSIX validate invocation", "sh")))
            command = [shell, "-c", script]
        env = os.environ.copy()
        env.pop("CLAUDE_PLUGIN_ROOT", None)
        env.pop("PLUGIN_ROOT", None)
        env.update({"T029_RESOURCE": str(resource), "T029_INSTALLED": str(package),
                    "T029_EFFECTS": str(effects) if effects else "",
                    "T029_FORCE_INPUT_IO": "1" if force_input_io else "0",
                    "PYTHONNOUSERSITE": "1", "TEMP": str(scratch),
                    "TMP": str(scratch), "TMPDIR": str(scratch)})
        if shell_kind == "posix" and os.name == "nt":
            absolute = resource.resolve()
            env["T029_RESOURCE"] = "/" + absolute.drive[0].lower() + absolute.as_posix()[2:]
            env["PATH"] = str(Path(shell).parent) + os.pathsep + env.get("PATH", "")
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        env.pop("PYTHONPYCACHEPREFIX", None)
        if instrument:
            env["PYTHONPATH"] = str(instrument)
        else:
            env.pop("PYTHONPATH", None)
        return subprocess.run(command, input=payload, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, cwd=project, env=env,
                              timeout=15, check=False)

    def test_actual_installed_validator_has_no_write_network_or_child_effects(self):
        valid = self._actual_valid_packet()
        with tempfile.TemporaryDirectory(prefix="t029-effects-", dir=ROOT) as owned:
            scratch = Path(owned)
            package, project = self._actual_validator_fixture(scratch)
            instrument, effects = self._actual_validator_guard(scratch, package)
            before = {p.relative_to(scratch): p.read_bytes() for p in scratch.rglob("*")
                      if p.is_file()}
            shell_kind = "powershell" if os.name == "nt" else "posix"
            for payload, expected in ((valid, 0), (b"{}", 2)):
                with self.subTest(expected=expected):
                    previous = set(effects.glob("*.json"))
                    result = self._run_actual_validator(scratch, package, project, payload,
                                                        instrument=instrument, effects=effects,
                                                        shell_kind=shell_kind)
                    self.assertEqual(result.returncode, expected, result.stderr)
                    self.assertEqual(result.stderr, b"")
                    self.assertNotIn(b"T029_PRIVATE_PACKET_CANARY",
                                     result.stdout + result.stderr)
                    self.assertEqual(json.loads(result.stdout)["valid"], expected == 0)
                    fresh = [json.loads(p.read_text(encoding="utf-8"))
                             for p in set(effects.glob("*.json")) - previous]
                    self._assert_single_actual_validator(fresh)
            observed = [json.loads(p.read_text(encoding="utf-8"))
                        for p in effects.glob("*.json")]
            self.assertTrue(all(not row["events"] for row in observed), observed)
            after = {p.relative_to(scratch): p.read_bytes() for p in scratch.rglob("*")
                     if p.is_file() and effects not in p.parents}
            self.assertEqual(after, before, "validator must not write package, project, cache or temp")
            # A blocked write and a blocked socket prove the observer can see effects.
            for code, expected_event in (
                ("open('blocked.txt','w')", "write"),
                ("import socket; socket.socket()", "socket.__new__"),
                ("import subprocess; subprocess.Popen(['python','-V'])", "subprocess.Popen"),
            ):
                control_env = os.environ.copy()
                control_env.update({"PYTHONPATH": str(instrument),
                                    "T029_INSTALLED": str(package),
                                    "T029_EFFECTS": str(effects),
                                    "T029_GUARD_CONTROL": "1",
                                    "PYTHONNOUSERSITE": "1"})
                previous = set(effects.glob("*.json"))
                control = subprocess.run([sys.executable, "-B", "-c", code], cwd=instrument,
                                         env=control_env, capture_output=True, timeout=5)
                self.assertNotEqual(control.returncode, 0, code)
                self.assertIn(b"T029 forbidden effect", control.stderr)
                fresh = [json.loads(p.read_text(encoding="utf-8"))
                         for p in set(effects.glob("*.json")) - previous]
                self.assertEqual(len(fresh), 1, fresh)
                self.assertIn(expected_event, fresh[0]["events"])
            self.assertFalse((instrument / "blocked.txt").exists())

    def test_actual_validator_invocation_enforces_limits_status_and_no_retry(self):
        valid = self._actual_valid_packet()
        canary = b"T029_PRIVATE_PACKET_CANARY"
        with tempfile.TemporaryDirectory(prefix="t029-limits-", dir=ROOT) as owned:
            scratch = Path(owned)
            package, project = self._actual_validator_fixture(scratch)
            instrument, effects = self._actual_validator_guard(scratch, package)
            cases = ((valid, 0, [], False),
                     (b"{}" + canary, 2, [{"code": "INVALID_JSON", "path": "$"}], False),
                     (b" " * 65537, 2, [{"code": "INPUT_LIMIT", "path": "$"}], False),
                     (valid, 3, [{"code": "INPUT_IO", "path": "$"}], True))
            for shell_kind in (("powershell",) if os.name == "nt" else ("posix",)):
                for payload, expected_exit, errors, force_input_io in cases:
                    with self.subTest(shell=shell_kind, bytes=len(payload)):
                        previous = set(effects.glob("*.json"))
                        result = self._run_actual_validator(
                            scratch, package, project, payload, instrument=instrument,
                            effects=effects, shell_kind=shell_kind,
                            force_input_io=force_input_io)
                        self.assertEqual(result.returncode, expected_exit, result.stderr)
                        self.assertEqual(result.stderr, b"")
                        self.assertNotIn(canary, result.stdout + result.stderr)
                        self.assertLessEqual(len(result.stdout), 8192)
                        self.assertTrue(result.stdout.endswith(b"\n"))
                        self.assertEqual(result.stdout.count(b"\n"), 1)
                        envelope = json.loads(result.stdout)
                        self.assertEqual(list(envelope),
                                         ["protocol", "valid", "errors", "truncated"])
                        self.assertEqual(envelope["protocol"],
                                         "codearbiter.debug-validation/1.0.0")
                        self.assertEqual(envelope["valid"], expected_exit == 0)
                        self.assertEqual(envelope["errors"], errors)
                        self.assertIs(envelope["truncated"], False)
                        self.assertTrue(all(list(row) == ["code", "path"]
                                            for row in envelope["errors"]))
                        fresh = [json.loads(p.read_text(encoding="utf-8"))
                                 for p in set(effects.glob("*.json")) - previous]
                        self._assert_single_actual_validator(fresh)
                # Sensor control: a second real validator process must fail the
                # same no-retry assessment, without changing an emitted command.
                control_env = os.environ.copy()
                control_env.update({"PYTHONPATH": str(instrument),
                                    "T029_INSTALLED": str(package),
                                    "T029_EFFECTS": str(effects),
                                    "PYTHONNOUSERSITE": "1"})
                previous = set(effects.glob("*.json"))
                replay = subprocess.run(
                    [sys.executable, "-B", str(package / "hooks/debug-handoff.py"), "validate"],
                    input=b"{}", cwd=project, env=control_env,
                    capture_output=True, timeout=5, check=False)
                self.assertEqual(replay.returncode, 2, replay.stderr)
                injected = [json.loads(p.read_text(encoding="utf-8"))
                            for p in set(effects.glob("*.json")) - previous]
                self.assertEqual(len(injected), 1, injected)
                with self.assertRaises(AssertionError):
                    self._assert_single_actual_validator(fresh + injected)

    @unittest.skipUnless(os.name == "nt", "Git sh native-Python cell runs on Windows")
    def test_actual_windows_git_sh_selects_native_python_for_installed_validator(self):
        with tempfile.TemporaryDirectory(prefix="t029-git-sh-", dir=ROOT) as owned:
            scratch = Path(owned)
            package, project = self._actual_validator_fixture(scratch)
            instrument, effects = self._actual_validator_guard(
                scratch, package, shell_kind="posix")
            result = self._run_actual_validator(
                scratch, package, project, self._actual_valid_packet(),
                instrument=instrument, effects=effects, shell_kind="posix")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, b"")
            self.assertEqual(json.loads(result.stdout)["valid"], True)
            observed = [json.loads(path.read_text(encoding="utf-8"))
                        for path in effects.glob("*.json")]
            self._assert_single_actual_validator(observed)

    def _actual_writer_fixture(self, scratch):
        """Install the generated writer unchanged beside a disposable Git worktree."""
        package = scratch / "installed package café"
        for relative in (".codex-plugin/plugin.json", "skills/ca-task/SKILL.md",
                         "includes/helper-invocation.md"):
            source = SOURCE_ROOT / "plugins/ca-codex" / relative
            self.assertTrue(source.is_file(), f"missing generated resource: {relative}")
            target = package / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            self.assertEqual(hashlib.sha256(target.read_bytes()).digest(),
                             hashlib.sha256(source.read_bytes()).digest())
        source_hooks = SOURCE_ROOT / "plugins/ca-codex/hooks"
        self.assertTrue((source_hooks / "taskwrite.py").is_file())
        for source in source_hooks.glob("*.py"):
            target = package / "hooks" / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            self.assertEqual(target.read_bytes(), source.read_bytes(),
                             f"installed writer dependency changed: {source.name}")

        seed = scratch / "seed repository"
        seed.mkdir()
        initial = "# Open tasks\n\n## In-flight\n- [ ] seed task\n"
        seed_board = seed / ".codearbiter/open-tasks.md"
        seed_board.parent.mkdir()
        seed_board.write_text(initial, encoding="utf-8", newline="\n")
        commands = (
            ["git", "-c", "core.autocrlf=false", "init", "-q", "-b", "main"],
            ["git", "-c", "core.autocrlf=false", "add", ".codearbiter/open-tasks.md"],
            ["git", "-c", "commit.gpgsign=false", "-c", "user.name=T030 Fixture",
             "-c", "user.email=t030@example.invalid",
             "commit", "-q", "-m", "fixture board"],
        )
        for command in commands:
            result = subprocess.run(command, cwd=seed, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=10, check=False)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        worktree = scratch / "intended worktree"
        result = subprocess.run(["git", "worktree", "add", "--detach", str(worktree), "HEAD"],
                                cwd=seed, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        cwd = worktree / "nested cwd"
        cwd.mkdir()
        return package, seed_board, worktree / ".codearbiter/open-tasks.md", cwd

    @staticmethod
    def _actual_writer_instrument(scratch):
        """Observe real child attempts and the writer's OS rename boundary."""
        instrument = scratch / "writer instrumentation"
        instrument.mkdir()
        (instrument / "sitecustomize.py").write_text(
            "import atexit, json, os, sys\n"
            "from pathlib import Path\n"
            "renames=[]\n"
            "def audit(event,args):\n"
            " if event!='os.rename': return\n"
            " src,dst=os.fspath(args[0]),os.fspath(args[1])\n"
            " renames.append([src,dst])\n"
            " if os.environ.get('T030_FAIL_REPLACE')=='1' and "
            "os.path.normcase(os.path.abspath(dst))=="
            "os.path.normcase(os.path.abspath(os.environ['T030_BOARD'])):\n"
            "  raise OSError('T030 injected replace refusal')\n"
            "sys.addaudithook(audit)\n"
            "def record():\n"
            " path=Path(os.environ['T030_EFFECTS'])/(str(os.getpid())+'.json')\n"
            " path.write_text(json.dumps({'argv':sys.argv,'cwd':os.getcwd(),"
            "'renames':renames}),encoding='utf-8')\n"
            "atexit.register(record)\n",
            encoding="utf-8", newline="\n")
        return instrument

    def _run_actual_writer(self, scratch, package, board, cwd, description, *,
                           instrument, label, fail_replace=False):
        """Run the literal emitted selection, resolution, and add invocation."""
        card = (package / "includes/helper-invocation.md").read_text(encoding="utf-8")
        task = (package / "skills/ca-task/SKILL.md").read_text(encoding="utf-8")
        resource = package / "skills/ca-task/SKILL.md"
        shell_kind = "powershell" if os.name == "nt" else "posix"
        if shell_kind == "powershell":
            shell = shutil.which("pwsh")
            self.assertIsNotNone(shell, "literal PowerShell invocation requires pwsh")
            bindings = "\n".join(("$ErrorActionPreference = 'Stop'",
                                  "$caLoadedResource = $env:T030_RESOURCE",
                                  "$caHelperRelative = 'hooks/taskwrite.py'",
                                  "$caDescription = $env:T030_DESCRIPTION"))
            script = "\n".join((bindings,
                self._fence(card, "Codex PowerShell interpreter selection", "powershell"),
                self._fence(card, "Codex PowerShell resolution", "powershell"),
                self._fence(task, "PowerShell add invocation", "powershell")))
            command = [shell, "-NoProfile", "-NonInteractive", "-Command", script]
        else:
            shell = shutil.which("sh")
            self.assertIsNotNone(shell, "literal POSIX invocation requires sh")
            bindings = "\n".join(("set -eu", "ca_loaded_resource=$T030_RESOURCE",
                                  "ca_helper_relative=hooks/taskwrite.py",
                                  "ca_description=$T030_DESCRIPTION"))
            script = "\n".join((bindings,
                self._fence(card, "Codex POSIX interpreter selection", "sh"),
                self._fence(card, "Codex POSIX resolution", "sh"),
                self._fence(task, "POSIX add invocation", "sh")))
            command = [shell, "-c", script]
        effects = scratch / ("writer effects " + label)
        effects.mkdir()
        env = os.environ.copy()
        env.pop("PLUGIN_ROOT", None)
        env["CLAUDE_PROJECT_DIR"] = str(board.parents[2] / "seed repository")
        env.update({"T030_RESOURCE": str(resource), "T030_DESCRIPTION": description,
                    "T030_EFFECTS": str(effects), "T030_BOARD": str(board),
                    "T030_FAIL_REPLACE": "1" if fail_replace else "0",
                    "PYTHONPATH": str(instrument), "PYTHONNOUSERSITE": "1",
                    "PYTHONDONTWRITEBYTECODE": "1", "TEMP": str(scratch),
                    "TMP": str(scratch), "TMPDIR": str(scratch)})
        result = subprocess.run(command, input=b"", stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, cwd=cwd, env=env,
                                timeout=15, check=False)
        observed = [json.loads(path.read_text(encoding="utf-8"))
                    for path in effects.glob("*.json")]
        return result, observed

    def _assert_one_actual_writer(self, observed, cwd):
        writers = [row for row in observed if row["argv"] and
                   Path(row["argv"][0]).name == "taskwrite.py"]
        self.assertEqual(len(writers), 1, observed)
        self.assertEqual(writers[0]["argv"][1:3], ["add", "--"])
        self.assertEqual(Path(writers[0]["cwd"]), cwd)
        return writers[0]

    def test_codex_invocation_records_actual_helper_paths_and_literal_argv(self):
        with tempfile.TemporaryDirectory(prefix="t038-codex-paths-", dir=ROOT) as owned:
            scratch = Path(owned)
            package, project = self._actual_validator_fixture(scratch)
            instrument, effects = self._actual_validator_guard(scratch, package)
            result = self._run_actual_validator(
                scratch, package, project, self._actual_valid_packet(),
                instrument=instrument, effects=effects)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["valid"])
            observed = [json.loads(path.read_text(encoding="utf-8"))
                        for path in effects.glob("*.json")]
            self._assert_single_actual_validator(observed)
            invoked = next(row for row in observed if row["argv"] and
                           Path(row["argv"][0]).name == "debug-handoff.py")
            self.assertEqual(Path(invoked["argv"][0]), package / "hooks/debug-handoff.py")
            self.assertEqual(invoked["argv"][1:], ["validate"])
            self.assertEqual(Path(invoked["cwd"]), project)
            self.assertNotEqual(Path(invoked["argv"][0]), SOURCE_ROOT / "plugins/ca-codex/hooks/debug-handoff.py")
            self.assertNotEqual(Path(invoked["cwd"]), package)
            self.assertEqual((package / ".codex-plugin/plugin.json").read_bytes(),
                             (SOURCE_ROOT / "plugins/ca-codex/.codex-plugin/plugin.json").read_bytes())

        with tempfile.TemporaryDirectory(prefix="t038-codex-writer-", dir=ROOT) as owned:
            scratch = Path(owned)
            package, seed_board, board, cwd = self._actual_writer_fixture(scratch)
            instrument = self._actual_writer_instrument(scratch)
            description = "--quoted 'text' \"here\"; $(echo no) café path"
            seed_before = seed_board.read_bytes()
            result, observed = self._run_actual_writer(
                scratch, package, board, cwd, description,
                instrument=instrument, label="t038")
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
            writer = self._assert_one_actual_writer(observed, cwd)
            self.assertEqual(Path(writer["argv"][0]), package / "hooks/taskwrite.py")
            self.assertNotEqual(Path(writer["argv"][0]), SOURCE_ROOT / "plugins/ca-codex/hooks/taskwrite.py")
            self.assertEqual(writer["argv"][1:], ["add", "--", description])
            self.assertEqual(Path(writer["cwd"]), cwd)
            self.assertNotEqual(Path(writer["cwd"]), seed_board.parent.parent)
            self.assertEqual(board.read_text(encoding="utf-8").count(description), 1)
            self.assertEqual(seed_board.read_bytes(), seed_before)

    def test_codex_evidence_cannot_inherit_another_host_result(self):
        codex = qualification.sample_record(host="codex", layers=("H",))
        claude = qualification.sample_record(host="claude", layers=("H",))
        self.assertTrue(qualification.assess_cell(
            codex, copy.deepcopy(codex), qualification.sample_decision(codex), ["V01/default"]))
        self.assertFalse(qualification.assess_cell(
            codex, claude, qualification.sample_decision(claude), ["V01/default"]))
        self.assertFalse(qualification.assess_cell(
            codex, copy.deepcopy(codex), qualification.sample_decision(claude), ["V01/default"]))
        inherited = copy.deepcopy(codex)
        inherited["evidence"] = copy.deepcopy(claude["evidence"])
        self.assertFalse(qualification.assess_cell(
            inherited, codex, qualification.sample_decision(codex), ["V01/default"]))
        wrong_host = copy.deepcopy(codex)
        wrong_host["host"] = "claude"
        self.assertFalse(qualification.assess_cell(
            wrong_host, codex, qualification.sample_decision(codex), ["V01/default"]))

    def test_actual_writer_targets_the_intended_worktree_once(self):
        with tempfile.TemporaryDirectory(prefix="t030-target-", dir=ROOT) as owned:
            scratch = Path(owned)
            package, seed_board, board, cwd = self._actual_writer_fixture(scratch)
            instrument = self._actual_writer_instrument(scratch)
            seed_before = seed_board.read_bytes()
            initial = board.read_bytes()
            description = "T030 one intended worktree task"
            result, observed = self._run_actual_writer(
                scratch, package, board, cwd, description,
                instrument=instrument, label="target")
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
            writer = self._assert_one_actual_writer(observed, cwd)
            self.assertEqual(writer["argv"][3:], [description])
            self.assertEqual(seed_board.read_bytes(), seed_before,
                             "the seed repository board must remain untouched")
            after = board.read_bytes()
            self.assertNotEqual(after, initial)
            self.assertEqual(after.decode("utf-8").count(description), 1)
            self.assertEqual(len(writer["renames"]), 1,
                             "the real writer must replace the board once")
            source, destination = map(Path, writer["renames"][0])
            self.assertEqual(destination, board)
            self.assertEqual(source.parent, board.parent)
            self.assertEqual(source.suffix, ".tmp")
            self.assertFalse(source.exists())

    def test_actual_writer_preserves_literal_input_lock_refusal_and_atomicity(self):
        with tempfile.TemporaryDirectory(prefix="t030-integrity-", dir=ROOT) as owned:
            scratch = Path(owned)
            package, seed_board, board, cwd = self._actual_writer_fixture(scratch)
            instrument = self._actual_writer_instrument(scratch)
            seed_before = seed_board.read_bytes()
            description = "--quoted 'text' \"here\"; $(echo no) café path"
            result, observed = self._run_actual_writer(
                scratch, package, board, cwd, description,
                instrument=instrument, label="literal")
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
            writer = self._assert_one_actual_writer(observed, cwd)
            self.assertEqual(writer["argv"][3:], [description])
            self.assertEqual(board.read_text(encoding="utf-8").count(description), 1)
            self.assertEqual(seed_board.read_bytes(), seed_before)

            locked_before = board.read_bytes()
            hold_code = ("import sys; from _hooklib import acquire_lock, release_lock; "
                         "h=acquire_lock(sys.argv[1],wait_seconds=0); "
                         "print('ready' if h is not None else 'failed',flush=True); "
                         "sys.stdin.buffer.read(1); release_lock(h)")
            holder_env = os.environ.copy()
            holder_env["PYTHONPATH"] = str(package / "hooks")
            holder_env["PYTHONDONTWRITEBYTECODE"] = "1"
            holder = subprocess.Popen([sys.executable, "-B", "-c", hold_code, str(board)],
                                      cwd=cwd, env=holder_env, stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            readiness = queue.Queue(maxsize=1)
            reader = threading.Thread(target=lambda: readiness.put(holder.stdout.readline()),
                                      daemon=True)
            reader.start()
            holder_stderr = b""
            try:
                try:
                    ready_line = readiness.get(timeout=5)
                except queue.Empty:
                    self.fail("generated lock holder did not signal readiness within five seconds")
                self.assertEqual(ready_line.strip(), b"ready",
                                 "generated lock must be held before the writer runs")
                refused, attempts = self._run_actual_writer(
                    scratch, package, board, cwd, "T030 locked refusal",
                    instrument=instrument, label="locked")
                self.assertEqual(refused.returncode, 1, refused.stderr.decode("utf-8", "replace"))
                self.assertIn(b"could not acquire the task-board lock", refused.stderr)
                refused_writer = self._assert_one_actual_writer(attempts, cwd)
                self.assertEqual(refused_writer["renames"], [])
                self.assertEqual(board.read_bytes(), locked_before)
            finally:
                try:
                    holder.stdin.write(b"x")
                    holder.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
                try:
                    holder.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    holder.kill()
                    holder.wait(timeout=5)
                reader.join(timeout=1)
                holder_stderr = holder.stderr.read()
                holder.stdout.close()
                holder.stderr.close()
            self.assertEqual(holder.returncode, 0, holder_stderr)

            failed, attempts = self._run_actual_writer(
                scratch, package, board, cwd, "T030 atomic refusal",
                instrument=instrument, label="atomic", fail_replace=True)
            self.assertNotEqual(failed.returncode, 0)
            failed_writer = self._assert_one_actual_writer(attempts, cwd)
            self.assertEqual(len(failed_writer["renames"]), 1,
                             "fault must reach the actual atomic replace")
            self.assertEqual(Path(failed_writer["renames"][0][1]), board)
            self.assertEqual(board.read_bytes(), locked_before,
                             "failed replacement must preserve the complete prior board")
            self.assertEqual(list(board.parent.glob("open-tasks.*.tmp")), [],
                             "a failed replacement must clean its sibling temp file")
            self.assertEqual(seed_board.read_bytes(), seed_before)


def _no_selected_assertions():
    raise AssertionError("zero debug helper invocation assertions selected")


def load_tests(loader, tests, pattern):
    if tests.countTestCases() == 0:
        return unittest.TestSuite([unittest.FunctionTestCase(_no_selected_assertions)])
    return tests

#!/usr/bin/env python3
"""Deterministic source checks for a cold ca-codex debug package.

These disposable fixtures are not a final release candidate or native host proof.
"""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SOURCE = ROOT / "plugins" / "ca-codex"
SCRIPTS = ROOT / ".github" / "scripts"


def load_script(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=repo, capture_output=True, text=True,
        encoding="utf-8", check=False, timeout=20,
    )
    if result.returncode:
        raise AssertionError(f"git {' '.join(arguments)}: {result.stderr}")
    return result.stdout.strip()


def validate_host_journey_package_record(record, *, source, installed, project,
                                         payload, completed, observed, candidate_repo):
    """Check retained D-layer inputs against an exact cold Git artifact.

    This checks record consistency; it does not authenticate an external host.
    """
    verifier = load_script("verify_codex_candidate_provenance")
    checker = load_script("check_codex_skill_resources")
    candidate = record.get("candidate")
    if not isinstance(candidate, dict) or not candidate.get("source_commit"):
        raise ValueError("missing exact candidate identity")
    expected = verifier.verify_static_candidate(
        repo=candidate_repo, final_ref=candidate["source_commit"])
    if candidate != expected or expected["source_tree"] != git(candidate_repo, "rev-parse", "HEAD^{tree}"):
        raise ValueError("candidate commit/tree/digest mismatch")
    if record.get("layer") != "D" or record.get("status") != "SOURCE_OBSERVED_HOST_PENDING":
        raise ValueError("source record cannot claim host authority")
    archive = candidate_repo / "committed-package.zip"
    try:
        verifier._archive(candidate_repo, candidate["source_commit"], archive)
        committed = checker._candidate_package_files(archive)
    finally:
        archive.unlink(missing_ok=True)
    current = checker._candidate_package_files(source)
    if committed != current:
        raise ValueError("source checkout differs from committed package")
    resource = (installed / "skills/ca-debug/SKILL.md").resolve()
    helper = (installed / "hooks/debug-handoff.py").resolve()
    if (Path(record.get("installed_root", "")).resolve() != installed.resolve() or
            Path(record.get("resource_path", "")).resolve() != resource or
            Path(record.get("helper_path", "")).resolve() != helper or
            record.get("cwd") != str(project.resolve())):
        raise ValueError("wrong installed resource/helper/cwd")
    for relative in (".codex-plugin/plugin.json", "skills/ca-debug/SKILL.md",
                     "includes/helper-invocation.md", "hooks/debug-handoff.py",
                     "hooks/_debughandofflib.py"):
        if relative not in committed or (installed / relative).read_bytes() != committed[relative]:
            raise ValueError("installed resource differs from exact candidate")
    if record.get("payload_sha256") != hashlib.sha256(payload).hexdigest():
        raise ValueError("input payload mismatch")
    if (record.get("exit_code") != completed.returncode or
            record.get("stdout") != completed.stdout or
            record.get("stderr") != completed.stderr or
            record.get("processes") != observed):
        raise ValueError("process result mismatch")
    if completed.returncode != 0 or completed.stderr != b"":
        raise ValueError("validator did not complete successfully")
    try:
        valid = json.loads(record["stdout"])["valid"]
    except (ValueError, KeyError, TypeError):
        valid = False
    if valid is not True:
        raise ValueError("validator did not accept payload")
    helper_rows = [row for row in observed if row.get("argv") and
                   Path(row["argv"][0]).name == "debug-handoff.py"]
    probes = [row for row in observed if row.get("argv") == ["-c"]]
    if (len(observed) != 3 or len(helper_rows) != 1 or len(probes) != 2 or
            helper_rows[0]["argv"] != [str(helper), "validate"] or
            helper_rows[0]["cwd"] != str(project) or
            any(row.get("events") for row in observed) or
            sorted(code for row in probes for code in row.get("commands", [])) != [0, 1] or
            any(row["started_ns"] >= helper_rows[0]["started_ns"] for row in probes)):
        raise ValueError("source rescue, fallback, or unbound helper trace")
    return True


class DebugPackageSourceTest(unittest.TestCase):
    def candidate(self, scratch):
        repo = scratch / "committed candidate"
        repo.mkdir()
        shutil.copytree(PACKAGE_SOURCE, repo / "plugins/ca-codex")
        git(repo, "init", "-q")
        git(repo, "config", "core.autocrlf", "false")
        git(repo, "config", "user.name", "T035 Source Fixture")
        git(repo, "config", "user.email", "t035@example.invalid")
        git(repo, "add", "--", "plugins/ca-codex")
        git(repo, "commit", "-qm", "synthetic package fixture")
        verifier = load_script("verify_codex_candidate_provenance")
        return repo, verifier.verify_static_candidate(repo=repo, final_ref=git(repo, "rev-parse", "HEAD"))

    def scratch(self):
        temporary = tempfile.TemporaryDirectory(prefix="t034-package-", dir=ROOT)
        self.addCleanup(temporary.cleanup)
        return Path(temporary.name)

    def installed_probe(self, scratch: Path):
        from test_debug_helper_invocation import TestDebugHelperInvocation

        probe = TestDebugHelperInvocation(
            methodName="test_actual_installed_validator_has_no_write_network_or_child_effects"
        )
        package, project = probe._actual_validator_fixture(scratch)
        instrument, effects = probe._actual_validator_guard(scratch, package)
        return probe, package, project, instrument, effects

    def observations(self, effects: Path):
        return [json.loads(path.read_text(encoding="utf-8"))
                for path in effects.glob("*.json")]

    def test_host_journey_record_binds_exact_cold_package_and_resource_paths(self):
        """A D-layer observation can bind installed bytes; H remains pending."""
        scratch = self.scratch()
        candidate_repo, candidate = self.candidate(scratch)
        probe, package, project, instrument, effects = self.installed_probe(scratch)
        packet = probe._actual_valid_packet()
        result = probe._run_actual_validator(scratch, package, project, packet,
                                             instrument=instrument, effects=effects)
        self.assertEqual(result.returncode, 0, result.stderr)
        observed = self.observations(effects)
        probe._assert_single_actual_validator(observed)
        record = {
            "candidate": candidate,
            "layer": "D", "status": "SOURCE_OBSERVED_HOST_PENDING",
            "installed_root": str(package.resolve()),
            "resource_path": str((package / "skills/ca-debug/SKILL.md").resolve()),
            "helper_path": str((package / "hooks/debug-handoff.py").resolve()),
            "cwd": str(project.resolve()), "payload_sha256": hashlib.sha256(packet).hexdigest(),
            "exit_code": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr, "processes": observed,
        }
        self.assertTrue(validate_host_journey_package_record(
            record, source=PACKAGE_SOURCE, installed=package, project=project,
            payload=packet, completed=result, observed=observed,
            candidate_repo=candidate_repo))

    def test_source_rescue_or_wrong_payload_invalidates_host_evidence(self):
        scratch = self.scratch()
        candidate_repo, candidate = self.candidate(scratch)
        probe, package, project, instrument, effects = self.installed_probe(scratch)
        packet = probe._actual_valid_packet()
        result = probe._run_actual_validator(scratch, package, project, packet,
                                             instrument=instrument, effects=effects)
        self.assertEqual(result.returncode, 0, result.stderr)
        observed = self.observations(effects)
        record = {
            "candidate": candidate,
            "layer": "D", "status": "SOURCE_OBSERVED_HOST_PENDING",
            "installed_root": str(package.resolve()),
            "resource_path": str((package / "skills/ca-debug/SKILL.md").resolve()),
            "helper_path": str((package / "hooks/debug-handoff.py").resolve()),
            "cwd": str(project.resolve()), "payload_sha256": hashlib.sha256(packet).hexdigest(),
            "exit_code": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr, "processes": observed,
        }
        for changed in (
            {**record, "payload_sha256": hashlib.sha256(b"other").hexdigest()},
            {**record, "helper_path": str(PACKAGE_SOURCE / "hooks/debug-handoff.py")},
            {**record, "processes": observed + [{"argv": [str(PACKAGE_SOURCE / "hooks/debug-handoff.py"), "validate"], "cwd": str(project), "events": ["external read"], "commands": [], "started_ns": 0}]},
            {**record, "status": "HOST_PASSED"},
            {**record, "candidate": {**candidate, "package_sha256": "0" * 64}},
            {**record, "stdout": b'{"valid":true}'},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                validate_host_journey_package_record(
                    changed, source=PACKAGE_SOURCE, installed=package,
                    project=project, payload=packet, completed=result,
                    observed=observed,
                    candidate_repo=candidate_repo)
        with self.assertRaisesRegex(ValueError, "payload"):
            validate_host_journey_package_record(
                record, source=PACKAGE_SOURCE, installed=package,
                project=project, payload=b"different input", completed=result,
                observed=observed,
                candidate_repo=candidate_repo)

    def test_exact_candidate_inventory_binds_commit_tree_and_payload_digest(self):
        scratch = self.scratch()
        repo = scratch / "disposable candidate"
        repo.mkdir()
        shutil.copytree(PACKAGE_SOURCE, repo / "plugins" / "ca-codex")
        git(repo, "init", "-q")
        # The synthetic commit must retain the copied package bytes exactly;
        # the host's system Git config may otherwise select text filters.
        git(repo, "config", "core.autocrlf", "false")
        git(repo, "config", "user.name", "T034 Source Fixture")
        git(repo, "config", "user.email", "t034@example.invalid")
        git(repo, "add", "--", "plugins/ca-codex")
        git(repo, "commit", "-qm", "synthetic package fixture")
        commit = git(repo, "rev-parse", "HEAD")
        tree = git(repo, "rev-parse", "HEAD^{tree}")

        verifier = load_script("verify_codex_candidate_provenance")
        checker = load_script("check_codex_skill_resources")
        result = verifier.verify_static_candidate(repo=repo, final_ref=commit)
        archive = scratch / "committed package.zip"
        verifier._archive(repo, commit, archive)
        committed_files = checker._candidate_package_files(archive)
        copied_files = checker._candidate_package_files(repo / "plugins" / "ca-codex")
        self.assertEqual(set(committed_files), set(copied_files),
                         "Git candidate inventory differs from copied package")
        for relative in sorted(copied_files):
            self.assertEqual(committed_files[relative], copied_files[relative],
                             f"Git candidate changed payload bytes: {relative}")
        contract = checker.candidate_static_contract(repo / "plugins" / "ca-codex")
        resources = checker.candidate_resource_contract(repo / "plugins" / "ca-codex")
        self.assertEqual((result["source_commit"], result["source_tree"]), (commit, tree))
        self.assertEqual(result["package_sha256"], contract["package_sha256"])
        self.assertEqual(result["resource_sha256"], resources["sha256"])
        self.assertEqual(result["resource_count"], len(resources["selected_paths"]))
        self.assertIn("skills/ca-debug/SKILL.md", resources["selected_paths"])
        self.assertIn("includes/helper-invocation.md", resources["selected_paths"])
        self.assertEqual(result["relative_read_count"], len(resources["relative_reads"]))
        for relative in ("hooks/debug-handoff.py", "hooks/_debughandofflib.py",
                         "includes/helper-invocation.md"):
            self.assertEqual((repo / "plugins/ca-codex" / relative).read_bytes(),
                             (PACKAGE_SOURCE / relative).read_bytes())
        for field, argument in (("archive_sha256", "expected_archive_sha256"),
                                ("package_sha256", "expected_package_sha256"),
                                ("resource_sha256", "expected_resource_sha256")):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "does not match"):
                verifier.verify_static_candidate(repo=repo, final_ref=commit,
                                                 **{argument: "0" * 64})

        # Dirty source bytes cannot silently change the exact committed candidate.
        (repo / "plugins/ca-codex/hooks/debug-handoff.py").write_bytes(b"tampered\n")
        again = verifier.verify_static_candidate(repo=repo, final_ref=commit)
        self.assertEqual(again, result)

    def test_cold_layout_resolves_actual_resources_without_source_checkout(self):
        scratch = self.scratch()
        probe, package, project, instrument, effects = self.installed_probe(scratch)
        packet = probe._actual_valid_packet()
        self.assertEqual((package / "hooks/debug-handoff.py").read_bytes(),
                         (PACKAGE_SOURCE / "hooks/debug-handoff.py").read_bytes())
        self.assertEqual((package / "includes/helper-invocation.md").read_bytes(),
                         (PACKAGE_SOURCE / "includes/helper-invocation.md").read_bytes())
        result = probe._run_actual_validator(scratch, package, project, packet,
                                             instrument=instrument, effects=effects)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b"")
        self.assertTrue(json.loads(result.stdout)["valid"])
        observed = self.observations(effects)
        probe._assert_single_actual_validator(observed)
        helper = next(row for row in observed
                      if row["argv"] and Path(row["argv"][0]).name == "debug-handoff.py")
        self.assertEqual(Path(helper["argv"][0]).resolve(),
                         (package / "hooks/debug-handoff.py").resolve())
        self.assertEqual(helper["cwd"], str(project))
        self.assertTrue(all(not row["events"] for row in observed), observed)

        # A deliberate source rescue must be denied by the same child audit hook.
        control_env = os.environ.copy()
        control_env.update({"PYTHONPATH": str(instrument), "T029_INSTALLED": str(package),
                            "T029_EFFECTS": str(effects), "PYTHONNOUSERSITE": "1",
                            "TEMP": str(scratch), "TMP": str(scratch)})
        # This synthetic script lives only in the disposable installed fixture.
        # A script-file invocation enables the existing audit guard without
        # Python's -c import/path search obscuring the attempted source read.
        source_path = PACKAGE_SOURCE / "hooks/debug-handoff.py"
        control_script = package / "hooks/t034-synthetic-source-rescue-control.py"
        control_script.write_text(
            f"open({str(source_path)!r}, 'rb').read()\n", encoding="utf-8", newline="\n"
        )
        control = subprocess.run(
            [sys.executable, "-B", str(control_script)],
            cwd=project, env=control_env, capture_output=True, timeout=5, check=False,
        )
        self.assertNotEqual(control.returncode, 0)
        self.assertIn(b"forbidden effect", control.stderr)
        new_rows = [row for row in self.observations(effects) if row not in observed]
        self.assertEqual(len(new_rows), 1, control.stderr)
        self.assertEqual(Path(new_rows[0]["argv"][0]).resolve(),
                         control_script.resolve(), control.stderr)
        self.assertIn("external read", new_rows[0]["events"], control.stderr)

    def test_partial_install_rejects_without_rescue(self):
        scratch = self.scratch()
        probe, package, project, instrument, effects = self.installed_probe(scratch)
        packet = probe._actual_valid_packet()
        for relative, expected in (("hooks/debug-handoff.py", "installed helper missing"),
                                   (".codex-plugin/plugin.json", "package identity missing")):
            with self.subTest(missing=relative):
                target = package / relative
                original = target.read_bytes()
                target.chmod(0o666)
                target.unlink()
                before = len(self.observations(effects))
                result = probe._run_actual_validator(scratch, package, project, packet,
                                                     instrument=instrument, effects=effects)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected.encode(), result.stderr)
                self.assertEqual(len(self.observations(effects)) - before, 2,
                                 "only the two interpreter probes may run")
                self.assertFalse(any(Path(row["argv"][0]).name == "debug-handoff.py"
                                     for row in self.observations(effects) if row["argv"]))
                target.write_bytes(original)
                target.chmod(0o444)


if __name__ == "__main__":
    unittest.main()

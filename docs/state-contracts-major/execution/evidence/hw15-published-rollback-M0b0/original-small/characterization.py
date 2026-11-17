"""PROPOSED ONLY: one retained-package lifecycle case, never the old ten-case suite.

Run only after Root authenticates the new normal integration cohort, original
uploader, successful run/job and stage against its independently selected source.
The JSON configuration supplies those trusted verifier arguments, not authority.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    source = Path(cfg["controller_source_repo"]).resolve(strict=True)
    old_archive = Path(cfg["published_old_archive"]).resolve(strict=True)
    if hashlib.sha256(old_archive.read_bytes()).hexdigest() != "df348d8926a6590346ab333abfefbeba88347dfdc665760d874e37c5f24c09ee":
        raise ValueError("published old archive identity changed")
    observations = args.output.with_name("lifecycle-observations.jsonl")
    with observations.open("x", encoding="utf-8"):
        pass

    def retain(value):
        with observations.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, sort_keys=True) + "\n")
    # Establish a credential-blind profile before all project imports. No native,
    # host CLI, SDK, provider or model process is part of this characterization.
    with tempfile.TemporaryDirectory(prefix="ca-hw15-profile-") as profile:
        safe = {k: os.environ[k] for k in ("SystemRoot", "WINDIR") if k in os.environ}
        safe.update(HOME=profile, USERPROFILE=profile, TEMP=profile, TMP=profile,
                    PATH=str(Path(cfg["git_executable"]).parent),
                    PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
                    PYTHONPYCACHEPREFIX=str(Path(profile) / "pycache"))
        os.environ.clear()
        os.environ.update(safe)
        scripts = source / ".github/scripts"
        sys.path.insert(0, str(scripts))
        import qualify_workflow_recovery_cohort as owning
        spec = importlib.util.spec_from_file_location("hw15_packager", source / "tools/build-host-packages.py")
        packager = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = packager
        spec.loader.exec_module(packager)
        from _contextverificationlib import _bind_candidate_package, _native_platform

        class RetainedLifecycle(owning.RetainedRecoveryTests):
            @classmethod
            def setUpClass(cls):
                super().setUpClass()  # unchanged production verifier and bindings
                cls.old_root = Path(cls.host_owner.name).resolve() / "published-old"
                packager.extract_artifact_release_package(old_archive, cls.old_root, host="codex")
                cls.old = cls.old_root / "plugins/ca-codex"
                if (cls.old / "hooks/workflow-recovery.py").exists():
                    raise ValueError("selected old package is not the pre-ledger package")

            def test_published_downgrade_and_fresh_reinstall_preserve_pending_state(self):
                store = self.root / ".git/codearbiter/workflow-recovery/v1"
                board = self.root / ".codearbiter/open-tasks.md"

                def snapshot():
                    return ({p.relative_to(store).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in store.rglob("*") if p.is_file()},
                            hashlib.sha256(board.read_bytes()).hexdigest(),
                            hashlib.sha256(self.source.read_bytes()).hexdigest())

                def old_read():
                    before = snapshot()
                    result = subprocess.run([sys.executable, "-B", str(self.old / "hooks/work.py"), "list"],
                                            cwd=self.root, env=self.environment("codex", package=self.old),
                                            capture_output=True, timeout=15)
                    retain({"phase": "published-old-read", "exit": result.returncode,
                            "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
                            "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
                            "before": before, "after": snapshot()})
                    self.assertEqual(result.returncode, 0, "published old work list failed")
                    self.assertEqual(snapshot(), before, "old package changed recovery or target bytes")

                def call(action, request=None, *, oid=None, revision=None):
                    process, value = self.cli("codex", action, request, oid=oid, revision=revision)
                    retain({"phase": "current-package", "action": action, "exit": process.returncode,
                            "response": value, "snapshot": snapshot()})
                    self.assertEqual(process.returncode, 0, "current package recovery command refused")
                    self.assertIsInstance(value, dict)
                    return value

                def record(oid):
                    return call("get", oid=oid)["record"]

                # Genuine old -> new: old executable reads the same owned project
                # before any ledger exists, then only new code registers records.
                self.assertFalse(store.exists())
                old_read()
                self.assertFalse(store.exists())
                offers = [self.offer(n) for n in range(3)]
                ids = [call("register", {"candidates": [offer]})["items"][0]["obligation_id"]
                       for offer in offers]
                self.assertEqual(record(ids[0])["state"], "pending")
                claimed = call("claim", oid=ids[1], revision=record(ids[1])["record_revision"])["record"]
                self.assertEqual(claimed["state"], "claimed")
                board_before_settlement = board.read_bytes()
                settled = call("resume", oid=ids[2], revision=record(ids[2])["record_revision"])["record"]
                self.assertEqual(settled["state"], "settled")
                self.assertNotEqual(board.read_bytes(), board_before_settlement)
                old_history = {p.relative_to(store).as_posix(): p.read_bytes()
                               for p in (store / "history").rglob("*.json")}
                compacted = call("compact", oid=ids[2], revision=settled["record_revision"])["record"]
                self.assertEqual(compacted["state"], "settled")
                self.assertEqual(len(compacted["history"]), 1)
                for relative, previous_bytes in old_history.items():
                    self.assertEqual((store / relative).read_bytes(), previous_bytes)
                self.assertEqual(json.loads((store / "history" / ids[2] /
                                             (str(settled["record_revision"]).zfill(12) + ".json")).read_bytes()), settled)
                # A separately edited target is preserved throughout rollback;
                # changing package prefixes never restores an old target image.
                with board.open("ab") as stream:
                    stream.write(b"\n<!-- owned unrelated user edit: retained -->\n")
                # Literal version downgrade. No new recovery writer is invoked
                # during this interval; old installed code has no such writer.
                preserved = snapshot()
                old_read()
                self.assertEqual(snapshot(), preserved)
                # Reinstall means a fresh extraction of exactly the admitted M
                # archive, not copying current checkout helpers into the prefix.
                candidate = Path(self.host_owner.name).resolve()
                reinstall = candidate / "fresh-M"
                entry = self.cohort["packages"]["codex"]
                archive = self.cohort_path.parent / entry["file"]
                packager.extract_artifact_release_package(archive, reinstall, host="codex")
                plugin = reinstall / "plugins/ca-codex"
                release = json.loads((plugin / "helpers/artifacts/release.json").read_bytes())
                native = release["binaries"][_native_platform()]["sha256"]
                _bind_candidate_package(candidate, plugin, "codex", candidate / "artifact-package-cohort.json",
                                        self.cohort_sha256, self.cohort["source_commit"],
                                        self.cohort["source_tree"], native)
                self.hosts["codex"] = plugin
                self.assertEqual(snapshot(), preserved)
                self.assertEqual(record(ids[0])["state"], "pending")
                self.assertEqual(record(ids[1]), claimed)
                self.assertEqual(record(ids[2]), compacted)
                # Readback and replay must retain exact ID/origin dedup, old
                # history and target bytes. Reconciliation does not resend.
                for offer, oid in zip(offers, ids):
                    before = snapshot()
                    reused = call("register", {"candidates": [offer]})["items"][0]
                    self.assertEqual(reused["obligation_id"], oid)
                    self.assertTrue(reused["reused"])
                    self.assertEqual(snapshot(), before)
                before_reconcile = board.read_bytes()
                observed = call("reconcile", oid=ids[1], revision=claimed["record_revision"])
                self.assertEqual(observed["status"], "absent-effect")
                self.assertEqual(observed["record"]["state"], "pending")
                self.assertEqual(board.read_bytes(), before_reconcile)
                before_replay = snapshot()
                call("resume", oid=ids[2], revision=record(ids[2])["record_revision"])
                self.assertEqual(snapshot(), before_replay)

        for key in ("cohort_path", "release_package_stage"):
            setattr(RetainedLifecycle, key, Path(cfg[key]).resolve(strict=True))
        for key in ("trusted_source_commit", "trusted_workflow", "trusted_workflow_run", "promotion_receipt_sha256"):
            setattr(RetainedLifecycle, key, cfg[key])
        name = "test_published_downgrade_and_fresh_reinstall_preserve_pending_state"
        result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([RetainedLifecycle(name)]))
        observed = {"format": "private.hw15-lifecycle-characterization/1", "tests_run": result.testsRun,
                    "failures": len(result.failures), "errors": len(result.errors), "skips": len(result.skipped),
                    "scope": "one Windows/Python installed-helper legacy-board lifecycle; no host/UI/provider/native execution",
                    "status": "PASS" if result.wasSuccessful() and result.testsRun == 1 and not result.skipped else "FAIL"}
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(observed, stream, indent=2)
            stream.write("\n")
        return 0 if observed["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Finite controls for the outer SEQ-12 publication receipt."""

import io
import json
import unittest
from unittest import mock
import zipfile

import major_readiness as owner
import pi_author_readiness as pi


SOURCE, TREE, RUN = "a" * 40, "b" * 40, 12


def archive(name, data):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr(name, data)
    return buffer.getvalue()


class PiAuthorReadinessTest(unittest.TestCase):
    def setUp(self):
        by_system = {system: f"[CHECK] | [PI  ] | Installed retained package <pi: {system} 1.5.0>"
                     for system in ("linux", "darwin")}
        cell_jobs = {pi.CELL: "major qualification / scenarios", "task:BUILD-G01": "Site | [Build] - Astro Pages",
                     **{f"installed:pi:{system}:1.5.0": name for system, name in by_system.items()}}
        self.req = {"source_commit": SOURCE, "source_tree": TREE, "ci_run_id": RUN, "cells": list(cell_jobs),
                    "cell_jobs": cell_jobs, **{pi.SELECTION: [pi.CELL], pi.PIN: "c" * 64}}
        self.running = {"id": RUN, "head_sha": SOURCE, "event": "push", "head_branch": "main",
                        "path": ".github/workflows/ci.yml", "repository": {"full_name": owner.REPOSITORY},
                        "run_attempt": 1, "status": "in_progress", "conclusion": None}
        self.complete = {**self.running, "status": "completed", "conclusion": "success"}
        names = [pi.original.ASSEMBLY_JOB, *by_system.values()]
        self.jobs = [{"id": identity, "name": name, "head_sha": SOURCE, "run_id": RUN,
                      "run_attempt": 1, "status": "completed", "conclusion": "success"}
                     for identity, name in enumerate(names, 1)]
        self.archive_bytes = {}
        self.artifacts = [self.retain(identity, name, archive("entry.json", name))
                          for identity, name in enumerate(["artifact-host-payloads-" + SOURCE,
                              "artifact-release-packages-" + SOURCE, "installed-pi-observation-linux-1",
                              "installed-pi-observation-darwin-1"], 10)]
        self.docs = {"schema": "codearbiter-major-site-source-readiness/1", "core": {"schema": owner.SCHEMA},
                     "build_generation": {"scope": "preserve existing Docs envelope"}}
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(owner, "artifact_bytes", side_effect=self.download).start()
        mock.patch.object(owner, "validate_upload").start()
        self.read_case = mock.patch.object(pi.original, "_read_case", side_effect=self.case).start()

    def retain(self, identity, name, data):
        self.archive_bytes[identity] = data
        return {"id": identity, "name": name, "expired": False, "size_in_bytes": len(data),
                "workflow_run": {"id": RUN, "head_sha": SOURCE}, "digest": "sha256:" + owner.digest(data)}

    def download(self, metadata, req):
        data = self.archive_bytes[metadata["id"]]
        owner.validate_artifact(metadata, req, owner.digest(data))
        return data

    @staticmethod
    def case(req, job, assembly, platform, pin, capture, raw, payloads):
        return {"source_commit": req["source_commit"], "platform": platform, "job_id": job["id"], "capture": capture,
                "assembly_job_id": assembly["id"], "pin": pin, "payload_ids": sorted(p["artifact_id"] for p in payloads.values())}

    def make_record(self):
        with mock.patch.object(owner, "api", return_value=self.running), \
             mock.patch("site_vitest_observation.docs_required", return_value=True), \
             mock.patch("site_vitest_observation.produce", return_value=self.docs) as inner:
            value = owner.produce(self.req, self.artifacts, self.jobs)
        nested_req, artifacts, jobs = inner.call_args.args
        self.assertNotIn(pi.CELL, nested_req["cells"])
        self.assertNotIn(pi.SELECTION, nested_req)
        self.assertIn("task:BUILD-G01", nested_req["cells"])
        self.assertEqual((artifacts, jobs), (self.artifacts, self.jobs))
        return value

    def verify(self, record, run=None):
        return owner.verify(record=record, requirements=self.req, run=run or self.complete, artifact={},
                            archive_digest="", jobs=self.jobs, build_artifacts=self.artifacts, payload_members={})

    def test_composes_original_pair_inside_running_main_and_preserves_docs_envelope(self):
        record = self.make_record()
        self.assertEqual(record["schema"], owner.PI_AUTHOR_SCHEMA)
        self.assertEqual(record["runtime"], self.docs)
        self.assertEqual(set(record["author"]["cases"]), {"linux/amd64", "darwin/arm64"})
        self.assertEqual(owner.runtime_record(record), self.docs["core"])
        with mock.patch("site_vitest_observation.verify", return_value={"state": "PREPUBLICATION_READY"}) as nested:
            self.assertEqual(self.verify(record)["state"], "PREPUBLICATION_READY")
        self.assertEqual(self.read_case.call_count, 4)
        self.assertEqual(nested.call_args.kwargs["record"], self.docs)
        self.assertNotIn(pi.CELL, nested.call_args.kwargs["requirements"]["cells"])

    def test_requires_exact_main_attempt_and_both_successful_original_owners(self):
        self.make_record()
        for label, run, jobs, artifacts in (
            ("program-branch", {**self.running, "head_branch": "major/state-contracts"}, self.jobs, self.artifacts),
            ("retry", {**self.running, "run_attempt": 2}, self.jobs, self.artifacts),
            ("stale-owner", self.running, [*self.jobs[:-1], {**self.jobs[-1], "head_sha": "d" * 40}], self.artifacts),
            ("duplicate-owner", self.running, [*self.jobs, self.jobs[-1]], self.artifacts),
            ("missing-archive", self.running, self.jobs, self.artifacts[:-1]),
            ("duplicate-archive", self.running, self.jobs, [*self.artifacts, self.artifacts[-1]]),
            ("stale-archive", self.running, self.jobs, [*self.artifacts[:-1], {**self.artifacts[-1],
                "workflow_run": {"id": RUN - 1, "head_sha": SOURCE}}]),
        ):
            with self.subTest(label=label), self.assertRaises(ValueError):
                pi.admit(self.req, run, artifacts, jobs, producing=True)

    def test_terminal_verifier_refuses_running_forged_or_absent_outer_evidence(self):
        record = self.make_record()
        with self.assertRaisesRegex(ValueError, "not successful trusted main"):
            self.verify(record, self.running)
        with self.assertRaisesRegex(ValueError, "original requirements"):
            self.verify(self.docs)
        forged_case = {**record["author"]["cases"]["darwin/arm64"], "job_id": 99}
        forged = {**record, "author": {**record["author"], "cases": {**record["author"]["cases"], "darwin/arm64": forged_case}}}
        with self.assertRaisesRegex(ValueError, "authenticated original cases"):
            self.verify(forged)

    def test_release_reconstructs_runtime_and_both_archives_independently(self):
        record = self.make_record()
        artifact = self.retain(44, "major-readiness-" + SOURCE, archive("major-readiness.json", json.dumps(record)))
        with mock.patch.object(owner, "collect", return_value=(self.req, self.complete, [*self.artifacts, artifact], self.jobs)), \
             mock.patch("site_vitest_observation.docs_required", return_value=True), \
             mock.patch("site_vitest_observation.produce", return_value=self.docs) as rebuild, \
             mock.patch("site_vitest_observation.verify", return_value={"state": "PREPUBLICATION_READY"}):
            self.assertEqual(owner.load_verified_receipt(None, SOURCE, RUN), (record, {"state": "PREPUBLICATION_READY"}))
        self.assertEqual(rebuild.call_count, 1)
        self.assertEqual(self.read_case.call_count, 4)

    def test_policy_cannot_drop_or_invent_cells_within_the_closed_selection(self):
        self.assertEqual(pi.requirements({}, [pi.CELL], SOURCE, None), {})
        self.assertEqual(pi.requirements({pi.SELECTION: [pi.CELL]}, [pi.CELL], SOURCE,
                                       lambda source, name: b"exact fixture bytes")[pi.PIN],
                         owner.digest(b"exact fixture bytes"))
        for invalid in ([], [pi.CELL, pi.CELL], ["scenario:SEQ-13"]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                pi.requirements({pi.SELECTION: invalid}, [pi.CELL], SOURCE, None)


if __name__ == "__main__":
    unittest.main()

import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

import docs_release_publication as transport


class ReleasePublicationTransportTest(unittest.TestCase):
    def setUp(self):
        self.owner = transport.owner
        self.repo = Path.cwd()
        self.source = "a" * 40
        self.release_head = "b" * 40  # workflow_run's later default-branch head
        repository = {"id": 8, "full_name": self.owner.REPOSITORY}
        self.run = {"id": 41, "run_attempt": 2, "head_sha": self.release_head,
                    "head_branch": "main", "event": "workflow_run", "status": "completed",
                    "conclusion": "success", "path": transport.RELEASE_WORKFLOW, "workflow_id": 9,
                    "repository": repository, "head_repository": repository}
        self.event = {"action": "completed", "repository": repository, "workflow_run": copy.deepcopy(self.run),
                      "workflow": {"id": 9, "path": transport.RELEASE_WORKFLOW}}
        self.job = {"id": 94, "name": transport.JOB, "run_id": 41, "run_attempt": 2,
                    "head_sha": self.release_head, "status": "completed", "conclusion": "success", "steps": [
            {"name": transport.OBSERVE_STEP, "status": "completed", "conclusion": "success"},
            {"name": transport.UPLOAD_STEP, "status": "completed", "conclusion": "success",
             "started_at": "2026-11-18T12:00:01Z", "completed_at": "2026-11-18T12:00:03Z"}]}
        self.core = {**self.run, "id": 32, "event": "push", "head_sha": self.source,
                     "path": ".github/workflows/ci.yml"}
        self.record = {"format": transport.FORMAT, "observed_at": "2026-11-18T12:00:00Z",
                       "source_commit": self.source, "ci_run_id": "32", "workflow_run": "41",
                       "release_visibility": "public", "clock_starts": "confirmed-non-draft-github-release",
                       "removal_authorization": "not-evaluated", "route_clock_status": "observed",
                       "observations": [{}, {}, {}], "site_observations": []}
        self.artifact_id = 333
        self.artifact_name = "route-publication-observation-41-2"

    def authenticate(self, *, wrong_log=False, wrong_zip=False, artifact_attempt=None):
        content = json.dumps(self.record).encode()
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr(transport.MEMBER, content)
            if wrong_zip:
                archive.writestr("surplus", b"bad")
        raw = stream.getvalue()
        digest = self.owner.digest(raw)
        metadata = {"id": self.artifact_id, "name": self.artifact_name, "expired": False,
                    "size_in_bytes": len(raw), "digest": "sha256:" + digest, "created_at": "2026-11-18T12:00:02Z",
                    "workflow_run": {"id": 41, "head_branch": "main", "head_sha": self.release_head,
                                     "repository_id": 8, "head_repository_id": 8}}
        if artifact_attempt is not None:
            metadata["name"] = f"route-publication-observation-41-{artifact_attempt}"
        finalized = 334 if wrong_log else self.artifact_id
        log = "\n".join(f"2026-11-18T12:00:02Z {line}" for line in (
            "##[group]Run " + self.owner.UPLOAD_ACTION,
            "SHA256 digest of uploaded artifact is " + digest,
            f"Artifact {self.artifact_name} successfully finalized. Artifact ID {finalized}",
        )).encode()
        responses = {
            "actions/runs/41/attempts/2": self.run,
            "actions/runs/41/attempts/2/jobs?per_page=100": {"total_count": 1, "jobs": [self.job]},
            "actions/runs/41/artifacts?name=route-publication-observation-41-2&per_page=100":
                {"total_count": 1, "artifacts": [metadata]},
            "actions/jobs/94/logs": log,
            "actions/artifacts/333/zip": raw,
            "actions/runs/32": self.core,
        }
        with patch.object(self.owner, "api", side_effect=lambda path, **_: responses[path]), \
                patch.object(self.owner, "command") as git:
            accepted = transport.selected_observation(self.event, self.repo)
            git.assert_called_once_with(["git", "--no-lazy-fetch", "merge-base", "--is-ancestor", self.source, "HEAD"],
                                        self.repo)
        self.assertEqual(accepted, content)

    def test_selected_source_is_independent_of_same_repository_release_head(self):
        self.authenticate()

    def test_refuses_foreign_branch_and_head_repository(self):
        mutations = [("head_branch", "feature"), ("head_repository", {"id": 7, "full_name": self.owner.REPOSITORY})]
        for key, foreign in mutations:
            with self.subTest(key=key), patch.dict(self.event["workflow_run"], {key: foreign}):
                with self.assertRaises(self.owner.ReadinessError):
                    self.authenticate()

    def test_refuses_wrong_attempt_failed_owner_and_surplus_member(self):
        with self.assertRaises(ValueError):
            self.authenticate(artifact_attempt=1)
        with self.assertRaises(self.owner.ReadinessError):
            self.authenticate(wrong_log=True)
        with self.assertRaises(self.owner.ReadinessError):
            self.authenticate(wrong_zip=True)
        with patch.dict(self.job, {"conclusion": "failure"}):
            with self.assertRaises(self.owner.ReadinessError):
                self.authenticate()

    def test_legacy_clock_unavailable_retains_exact_source_checks(self):
        with patch.dict(self.record, {"route_clock_status": "declarations-unavailable", "observations": []}):
            self.authenticate()
            with patch.dict(self.core, {"head_sha": "d" * 40}):
                with self.assertRaises(self.owner.ReadinessError):
                    self.authenticate()
        with patch.dict(self.record, {"route_clock_status": "declarations-unavailable"}):
            with self.assertRaises(self.owner.ReadinessError):
                self.authenticate()

    def test_refuses_foreign_source_and_unsuccessful_core(self):
        with patch.dict(self.record, {"source_commit": "c" * 40}):
            with self.assertRaises(self.owner.ReadinessError):
                self.authenticate()
        with patch.dict(self.core, {"conclusion": "failure"}):
            with self.assertRaises(self.owner.ReadinessError):
                self.authenticate()

    def test_docs_path_is_restricted_to_release_trigger_and_separate_from_qualification(self):
        text = (Path(__file__).resolve().parents[1] / "workflows/docs.yml").read_text(encoding="utf8")
        block = """- name: Read the original release publication observation
        if: github.event_name == 'workflow_run' && github.ref == 'refs/heads/main'"""
        self.assertEqual(text.count(block), 2)
        self.assertEqual(text.count('CODEARBITER_PUBLICATION_OBSERVATION: ${{ runner.temp }}/route-publication-observation.json'), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)

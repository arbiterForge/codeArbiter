#!/usr/bin/env python3
# codeArbiter — exact hosted tag observation regression tests (LG02).

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import tag_publication_receipt as receipt


COMMIT = "a" * 40
OBJECT = "b" * 40
WORKFLOW = "c" * 40
TAG = "ca-codex-v0.7.5"
REF = "refs/tags/" + TAG
DIRECT = f"{COMMIT}\t{REF}\n"
ANNOTATED = f"{OBJECT}\t{REF}\n{COMMIT}\t{REF}^{{}}\n"


class ParserTests(unittest.TestCase):
    # LG02-IDENTITY: exact object and dereferenced commit, without normalization.
    def test_lightweight_identity(self):
        self.assertEqual(receipt.parse_remote_refs(DIRECT, TAG, COMMIT), {
            "object_sha": COMMIT, "object_type": "commit", "commit_sha": COMMIT,
        })

    def test_annotated_identity_in_either_order(self):
        for text in (ANNOTATED, "\n".join(reversed(ANNOTATED.splitlines())) + "\n"):
            with self.subTest(text=text):
                self.assertEqual(receipt.parse_remote_refs(text, TAG, COMMIT), {
                    "object_sha": OBJECT, "object_type": "tag", "commit_sha": COMMIT,
                })

    # LG02-REFS: no absent, ambiguous, malformed, extra or oversized observations.
    def test_rejects_untrusted_ref_shapes(self):
        cases = ["", "\n", DIRECT * 2, ANNOTATED + DIRECT,
                 f"{COMMIT}\t{REF}^{{}}\n", DIRECT + f"{COMMIT}\trefs/tags/v1.0.0\n",
                 DIRECT.replace("\t", " "), DIRECT.replace(COMMIT, "g" * 40),
                 DIRECT.replace(COMMIT, COMMIT.upper()), DIRECT.replace(COMMIT, "0" * 40),
                 DIRECT.replace(COMMIT, "a" * 39), DIRECT + "\n", " " + DIRECT,
                 DIRECT + "x" * 4096, DIRECT.replace("\n", "\r\n"),
                 DIRECT.replace(REF, REF + "-extra")]
        for text in cases:
            with self.subTest(text=text[:100]):
                with self.assertRaises(ValueError):
                    receipt.parse_remote_refs(text, TAG, COMMIT)

    def test_rejects_expected_commit_mismatch(self):
        for text in (DIRECT, ANNOTATED):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    receipt.parse_remote_refs(text, TAG, "d" * 40)

    def test_rejects_invalid_parser_identity_arguments(self):
        for tag, commit in (("other-v1.0.0", COMMIT), (TAG, "0" * 40),
                            (TAG, "x"), (TAG + "\n", COMMIT)):
            with self.subTest(tag=tag, commit=commit):
                with self.assertRaises(ValueError):
                    receipt.parse_remote_refs(DIRECT, tag, commit)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "receipt.json"
        self.args = ["capture", "--repo", "arbiterForge/codeArbiter", "--tag", TAG,
                     "--expected-commit", COMMIT, "--run-id", "12345",
                     "--run-attempt", "2", "--workflow-sha", WORKFLOW,
                     "--output", str(self.output)]
        self.runner = Mock(return_value=subprocess.CompletedProcess([], 0, ANNOTATED, ""))

    def invoke(self, args=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = receipt.main(self.args if args is None else args, run=self.runner)
        return result, stdout.getvalue(), stderr.getvalue()

    # LG02-BINDING: real argument parser + JSON serialization, only Git mocked.
    def test_cli_writes_complete_bound_json_and_exact_bounded_query(self):
        result, stdout, stderr = self.invoke()
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(self.output.read_text(encoding="utf-8")), {
            "schema_version": 1, "repo": "arbiterForge/codeArbiter", "tag": TAG,
            "identity": {"object_sha": OBJECT, "object_type": "tag", "commit_sha": COMMIT},
            "source": {"kind": "hosted-tag-observation", "run_id": 12345,
                       "run_attempt": 2, "workflow_sha": WORKFLOW},
        })
        command = self.runner.call_args.args[0]
        self.assertEqual(command, ["git", "ls-remote", "--tags", "origin", REF, REF + "^{}"])
        options = self.runner.call_args.kwargs
        self.assertEqual(options["timeout"], 30)
        self.assertIs(options["shell"], False)
        self.assertEqual(options["stdin"], subprocess.DEVNULL)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "")

    def test_cli_accepts_each_governed_namespace(self):
        for tag in ("v1.0.0", "ca-sandbox-v1.0.0", "ca-codex-v1.0.0", "ca-pi-v1.0.0",
                    "v1.0.0-rc.1+build.3"):
            with self.subTest(tag=tag):
                args = self.args.copy()
                args[args.index("--tag") + 1] = tag
                self.runner.return_value.stdout = f"{COMMIT}\trefs/tags/{tag}\n"
                self.assertEqual(self.invoke(args)[0], 0)
                self.assertEqual(json.loads(self.output.read_text())["tag"], tag)
                self.output.unlink()

    # LG02-METADATA: malformed/oversized claims stop before observation and output.
    def test_cli_rejects_bad_metadata_without_query(self):
        cases = {"--repo": ("repo", "a/b/c", "../repo", "a/..", "a/b\n", "a/" + "b" * 101),
                 "--tag": ("v01.0.0", "v1.0", "v1.0.0-01", "other-v1.0.0", "v1.0.0\n",
                           "v1.0.0+" + "a" * 256),
                 "--expected-commit": ("0" * 40, "a" * 39, "A" * 40),
                 "--workflow-sha": ("x", "0" * 40, "C" * 40),
                 "--run-id": ("0", "-1", "01", "1.1", "9" * 21),
                 "--run-attempt": ("0", "-1", "01", "1\n")}
        for flag, values in cases.items():
            for value in values:
                with self.subTest(flag=flag, value=value):
                    args = self.args.copy()
                    args[args.index(flag) + 1] = value
                    self.assertEqual(self.invoke(args)[0], 1)
                    self.runner.assert_not_called()
                    self.assertFalse(self.output.exists())

    def test_cli_rejects_missing_and_unknown_arguments(self):
        for args in ([], self.args[:-2], self.args + ["--unknown"],
                     self.args + ["--repo", "other/repo"]):
            with self.subTest(args=args):
                self.assertEqual(self.invoke(args)[0], 2)
                self.runner.assert_not_called()
                self.assertFalse(self.output.exists())

    # LG02-FAIL-CLOSED: failed observations emit only fixed, non-secret diagnostics.
    def test_process_failure_timeout_and_spawn_errors_leave_no_receipt(self):
        secret = "DUMMY_PRIVATE_TRANSPORT_DETAIL"
        cases = [subprocess.CompletedProcess([], 1, ANNOTATED, secret),
                 subprocess.TimeoutExpired("git " + secret, 30, output=secret, stderr=secret),
                 OSError(secret), UnicodeDecodeError("ascii", b"\xff", 0, 1, secret)]
        for outcome in cases:
            with self.subTest(outcome=type(outcome).__name__):
                self.runner.side_effect = outcome if isinstance(outcome, Exception) else None
                self.runner.return_value = outcome
                result, stdout, stderr = self.invoke()
                self.assertEqual(result, 1)
                self.assertNotIn(secret, stdout + stderr)
                self.assertFalse(self.output.exists())

    def test_bad_remote_or_mismatched_commit_leaves_no_receipt(self):
        for text in ("", DIRECT * 2, DIRECT.replace(COMMIT, "d" * 40), "x" * 4097):
            with self.subTest(text=text[:100]):
                self.runner.return_value.stdout = text
                self.assertEqual(self.invoke()[0], 1)
                self.assertFalse(self.output.exists())

    # LG02-EXCLUSIVE: collisions and unsafe paths cannot replace prior evidence.
    def test_existing_output_is_not_overwritten(self):
        self.output.write_text("prior evidence", encoding="utf-8")
        self.assertEqual(self.invoke()[0], 1)
        self.assertEqual(self.output.read_text(), "prior evidence")

    def test_missing_parent_or_directory_output_fails(self):
        for output in (self.output / "missing.json", Path(self.temp.name)):
            with self.subTest(output=output):
                args = self.args[:-1] + [str(output)]
                self.assertEqual(self.invoke(args)[0], 1)
                self.assertFalse(self.output.exists())

    def test_symlink_leaf_and_parent_are_rejected(self):
        target = Path(self.temp.name) / "target"
        target.mkdir()
        link = Path(self.temp.name) / "link"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Symlink creation unavailable on this host: {error.errno}")
        for output in (link, link / "receipt.json"):
            with self.subTest(output=output):
                self.assertEqual(self.invoke(self.args[:-1] + [str(output)])[0], 1)
                self.assertEqual(list(target.iterdir()), [])

    def test_output_io_failure_leaves_no_receipt(self):
        with patch.object(os, "fsync", side_effect=OSError("DUMMY_IO_DETAIL")):
            result, stdout, stderr = self.invoke()
        self.assertEqual(result, 1)
        self.assertFalse(self.output.exists())
        self.assertNotIn("DUMMY_IO_DETAIL", stdout + stderr)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_cleanup_failure_cannot_report_valid_published_receipt_as_failure(self):
        with patch.object(os, "unlink", side_effect=OSError("DUMMY_CLEANUP_DETAIL")):
            result, stdout, stderr = self.invoke()
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(self.output.read_text())["identity"]["commit_sha"], COMMIT)
        self.assertNotIn("DUMMY_CLEANUP_DETAIL", stdout + stderr)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Observable crash/replay contracts for the local recovery owner."""
import hashlib
import json
import os
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core/pysrc"))
import _workflowrecoverylib as recovery
import _taskboardlib as boardlib


class RecoveryRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ca-workflow-recovery-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        home = self.root / "disposable-home"
        home.mkdir()
        safe = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP", "PATH") if key in os.environ}
        safe.update(HOME=str(home), USERPROFILE=str(home), PYTHONDONTWRITEBYTECODE="1")
        environment = mock.patch.dict(os.environ, safe, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".codearbiter").mkdir()
        (self.root / ".codearbiter/CONTEXT.md").write_text("---\narbiter: enabled\n---\n<!--INITIALIZED-->\n")
        (self.root / ".codearbiter/open-tasks.md").write_text("# Tasks\n\n## Backlog\n")
        self.source = self.root / "finding.md"
        self.source.write_text("[NEEDS-TRIAGE] A bounded follow-up\n")
        self.store = self.root / ".git/codearbiter/workflow-recovery/v1"

    def request(self, number=0):
        return {"workflow_run_id": "test-run", "kind": "terminal-harvest",
                "origin": "spec:recovery#triage-" + str(number), "work_ref": "none",
                "source": {"workflow": "tdd:phase-6", "locator": "finding.md",
                           "fingerprint": "sha256:" + hashlib.sha256(self.source.read_bytes()).hexdigest()},
                "candidate": {"kind": "work", "blocking": "nonblocking", "title": "Follow-up " + str(number),
                              "description": "Keep the exact source and independent work.", "provenance": "finding.md"}}

    def call(self, action, request=None, **kwargs):
        dispatch = getattr(recovery, "dispatch", None)
        if dispatch is None:
            return {"status": "unavailable", "durable": False, "reason": "runtime-not-implemented"}
        return dispatch(self.root, action, request or {}, **kwargs)

    def snapshot(self):
        result = {}
        for path in self.store.rglob("*"):
            if path.is_file():
                info = path.stat()
                # Windows byte-range locks correctly prevent reading the held
                # byte. Verify the untouched lock inode/size/mtime instead.
                result[str(path.relative_to(self.store))] = (("lock", info.st_ino, info.st_size, info.st_mtime_ns)
                    if path.name.endswith(".lock") else path.read_bytes())
        return result

    def test_scan_is_physically_readonly_and_registration_replay_is_exact(self):
        self.assertEqual(self.call("scan")["status"], "absent")
        self.assertFalse(self.store.exists())
        first = self.call("register", {"candidates": [self.request()]})
        self.assertTrue(first["durable"], first)
        oid = first["items"][0]["obligation_id"]
        before = self.snapshot()
        self.assertEqual(self.call("register", {"candidates": [self.request()]})["items"][0]["obligation_id"], oid)
        self.assertEqual(self.snapshot(), before)
        scan = self.call("scan")
        self.assertEqual(scan["status"], "complete")
        self.assertEqual([item["obligation_id"] for item in scan["items"]], [oid])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual((self.root / ".codearbiter/open-tasks.md").read_text(), "# Tasks\n\n## Backlog\n")

    def test_crash_after_record_cannot_look_empty_and_explicit_repair_recovers(self):
        def crash(point):
            if point == "after-record":
                raise OSError("fixture write failure")
        result = self.call("register", {"candidates": [self.request()]}, fault=crash)
        self.assertFalse(result["durable"], result)
        self.assertNotEqual(self.call("scan")["status"], "complete")
        before = self.snapshot()
        self.call("scan")
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.call("repair")["status"], "repaired")
        replay = self.call("register", {"candidates": [self.request()]})
        self.assertTrue(replay["durable"], replay)
        self.assertEqual(len(self.call("scan")["items"]), 1)

    def test_pages_and_stale_cursor_never_claim_a_complete_empty_scan(self):
        for start in (0, 24):
            result = self.call("register", {"candidates": [self.request(i) for i in range(start, min(start + 24, 37))]})
            self.assertTrue(result["durable"], result)
        first = self.call("scan")
        self.assertEqual(first["status"], "partial")
        self.assertEqual(len(first["items"]), 32)
        self.assertLessEqual(first["bytes_read"], 262144)
        second = self.call("scan", {"cursor": first["cursor"]})
        self.assertEqual(second["status"], "complete")
        self.assertEqual(len(second["items"]), 5)
        self.assertTrue(self.call("register", {"candidates": [self.request(38)]})["durable"])
        stale = self.call("scan", {"cursor": first["cursor"]})
        self.assertEqual(stale["status"], "unavailable")
        self.assertEqual(stale["reason"], "changed-binding")

    def test_changed_source_is_held_without_touching_target(self):
        result = self.call("register", {"candidates": [self.request()]})
        self.assertTrue(result["durable"], result)
        oid = result["items"][0]["obligation_id"]
        self.source.write_text("New independent source bytes\n")
        before = (self.root / ".codearbiter/open-tasks.md").read_bytes()
        held = self.call("resume", {"obligation_id": oid, "expected_revision": 1})
        self.assertEqual(held["reason"], "source-stale")
        self.assertEqual((self.root / ".codearbiter/open-tasks.md").read_bytes(), before)
        record = self.call("get", {"obligation_id": oid})["record"]
        self.assertEqual(record["state"], "unavailable")

    def registered(self, offer=None):
        result = self.call("register", {"candidates": [offer or self.request()]})
        self.assertTrue(result["durable"], result)
        return result["items"][0]["obligation_id"]

    def test_real_legacy_target_response_loss_reconciles_without_duplicate(self):
        oid = self.registered()
        def response_loss(point):
            if point == "after-target":
                raise OSError("fixture lost response")
        attempted = self.call("resume", {"obligation_id": oid, "expected_revision": 1}, fault=response_loss)
        self.assertFalse(attempted["durable"], attempted)
        board = (self.root / ".codearbiter/open-tasks.md").read_bytes()
        self.assertEqual(board.count(b"(from spec:recovery#triage-0)"), 1)
        record = self.call("get", {"obligation_id": oid})["record"]
        self.assertEqual(record["state"], "claimed")
        result = self.call("reconcile", {"obligation_id": oid, "expected_revision": record["record_revision"]})
        self.assertEqual(result["status"], "settled", result)
        self.assertEqual(result["record"]["outcome"]["disposition"], "reused")
        self.assertEqual(board, (self.root / ".codearbiter/open-tasks.md").read_bytes())
        replay = self.call("resume", {"obligation_id": oid, "expected_revision": result["record"]["record_revision"]})
        self.assertEqual(replay["status"], "settled")
        self.assertEqual(board, (self.root / ".codearbiter/open-tasks.md").read_bytes())

    def test_legacy_origin_in_archive_is_reused_without_recreating_work(self):
        (self.root / ".codearbiter/done-tasks.md").write_text(
            "# Done\n\n## Archive\n- [x] Changed independent title (from spec:recovery#triage-0)\n")
        before = (self.root / ".codearbiter/open-tasks.md").read_bytes()
        oid = self.registered()
        result = self.call("resume", {"obligation_id": oid, "expected_revision": 1})
        self.assertEqual(result["status"], "settled", result)
        self.assertEqual(result["record"]["outcome"]["disposition"], "reused")
        self.assertEqual(before, (self.root / ".codearbiter/open-tasks.md").read_bytes())

    def test_deferred_decision_and_decline_commit_once_after_response_loss(self):
        for number, action in ((0, "resume"), (1, "decline")):
            with self.subTest(action=action):
                offer = self.request(number)
                offer["candidate"]["kind"] = "decision"
                oid = self.registered(offer)
                def loss(point):
                    if point == "after-target":
                        raise OSError("fixture response loss")
                self.assertFalse(self.call(action, {"obligation_id": oid, "expected_revision": 1}, fault=loss)["durable"])
                record = self.call("get", {"obligation_id": oid})["record"]
                result = self.call(action, {"obligation_id": oid, "expected_revision": record["record_revision"]})
                self.assertEqual(result["status"], "settled", result)
        questions = (self.root / ".codearbiter/open-questions.md").read_text()
        audit = (self.root / ".codearbiter/triage.log").read_text()
        self.assertEqual(questions.count("(from spec:recovery#triage-0)"), 1)
        self.assertEqual(audit.count("(from spec:recovery#triage-1)"), 1)

    def test_blocking_decision_is_not_demoted_or_confirmed(self):
        offer = self.request()
        offer["candidate"].update(kind="decision", blocking="blocking")
        oid = self.registered(offer)
        result = self.call("resume", {"obligation_id": oid, "expected_revision": 1})
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("user", result["next_action"])
        self.assertFalse((self.root / ".codearbiter/open-questions.md").exists())
        self.assertFalse((self.root / ".codearbiter/triage.log").exists())

    def test_live_os_lock_is_not_stolen_and_stale_cas_cannot_overwrite(self):
        oid = self.registered()
        script = ("import sys,time;from pathlib import Path;sys.path.insert(0,sys.argv[1]);"
                  "import _workflowrecoverylib as r;s=r.RecoveryStore(Path(sys.argv[2])).open();"
                  "\nwith s.lock(sys.argv[3]):\n print('held',flush=True);sys.stdin.readline()\n")
        process = subprocess.Popen([sys.executable, "-c", script, str(ROOT / "core/pysrc"), str(self.root), oid],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), "held")
            before = self.snapshot()
            busy = self.call("resume", {"obligation_id": oid, "expected_revision": 1})
            self.assertEqual(busy["reason"], "busy")
            self.assertEqual(before, self.snapshot())
        finally:
            process.communicate("release\n", timeout=15)
        result = self.call("claim", {"obligation_id": oid, "expected_revision": 1})
        self.assertEqual(result["status"], "claimed", result)
        before = self.snapshot()
        stale = self.call("claim", {"obligation_id": oid, "expected_revision": 1})
        self.assertEqual(stale["status"], "conflict")
        self.assertEqual(before, self.snapshot())

    def test_malformed_record_and_unsafe_intent_never_overwrite_owned_targets(self):
        oid = self.registered()
        record = self.store / "records" / (oid + ".json")
        value = json.loads(record.read_text())
        value["schema_version"] = 99
        record.write_text(json.dumps(value))
        before = self.snapshot()
        self.assertEqual(self.call("get", {"obligation_id": oid})["reason"], "unsupported-version")
        self.assertEqual(before, self.snapshot())
        (self.store / "transaction.json").write_text(json.dumps({"format": recovery._STORE_FORMAT,
            "id": "a" * 32, "writes": [{"path": "../../outside", "before": None, "after": "b" * 64}]}))
        before = self.snapshot()
        self.assertEqual(self.call("repair")["reason"], "corrupt-record")
        self.assertEqual(before, self.snapshot())

    def test_empty_registration_and_dormant_scan_do_not_create_storage(self):
        self.assertEqual(self.call("register", {"candidates": []})["status"], "empty")
        self.assertFalse(self.store.exists())
        (self.root / ".codearbiter/CONTEXT.md").write_text("---\narbiter: disabled\n---\n")
        self.assertEqual(self.call("scan")["status"], "absent")
        self.assertFalse(self.store.exists())

    def test_every_declared_producer_captures_before_terminal_effect(self):
        producers = recovery.CONTRACT["kinds"]["terminal-harvest"]["producers"]
        offers = []
        for number, producer in enumerate(producers):
            offer = self.request(number)
            if producer == "checkpoint:deferrable":
                source, extractor = "### DEFERRABLE\n- Exact checkpoint follow-up\n", boardlib.extract_deferrable
            elif producer == "sprint:low-confidence":
                source, extractor = "### Exact sprint follow-up · confidence: low\n", boardlib.extract_low_confidence
            else:
                source, extractor = "[NEEDS-TRIAGE] Exact producer follow-up\n", boardlib.extract_needs_triage
            candidates = extractor(source, "spec:" + producer)
            self.assertEqual(len(candidates), 1)
            candidate = candidates[0]
            path = self.root / ("producer-" + str(number) + ".md")
            path.write_text(source, encoding="utf-8")
            offer["origin"] = candidate.origin
            offer["candidate"]["title"] = candidate.desc
            offer["source"]["workflow"] = producer
            offer["source"]["locator"] = path.name
            offer["source"]["fingerprint"] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            offers.append(offer)
        result = self.call("register", {"candidates": offers})
        self.assertTrue(result["durable"], result)
        for item, offered in zip(result["items"], offers):
            observed = self.call("get", {"obligation_id": item["obligation_id"]})["record"]
            self.assertEqual(observed["source"]["workflow"], offered["source"]["workflow"])
            self.assertEqual(observed["origin"], offered["origin"])
            self.assertEqual(observed["candidate"]["title"], offered["candidate"]["title"])
        self.assertEqual((self.root / ".codearbiter/open-tasks.md").read_text(), "# Tasks\n\n## Backlog\n")
        # The producer may now terminate. A new invocation uses the durable
        # exact candidate, without terminal-phase conversation state.
        for item in result["items"]:
            settled = self.call("resume", {"obligation_id": item["obligation_id"], "expected_revision": 1})
            self.assertEqual(settled["status"], "settled", settled)
        self.assertEqual((self.root / ".codearbiter/open-tasks.md").read_text().count("(from spec:"), len(offers))

    def test_invalid_unknown_and_oversize_input_leave_no_registered_store(self):
        cases = []
        unknown = self.request()
        unknown["kind"] = "run-arbitrary-instruction"
        cases.append({"candidates": [unknown]})
        fields = self.request()
        fields["handler"] = "not-a-supported-handler"
        cases.append({"candidates": [fields]})
        path = self.request()
        path["source"]["locator"] = "../outside"
        cases.append({"candidates": [path]})
        huge = self.request()
        huge["candidate"]["description"] = "x" * 65536
        cases.append({"candidates": [huge]})
        cases.append({"candidates": [self.request(i) for i in range(33)]})
        for request in cases:
            with self.subTest(request_shape=list(request)):
                result = self.call("register", request)
                self.assertFalse(result["durable"], result)
                self.assertFalse(self.store.exists())

    def child(self, action, request, point=None):
        script = ("import sys,json,os;sys.path.insert(0,sys.argv[1]);import _workflowrecoverylib as r;"
                  "counts={}\ndef crash(p):\n counts[p]=counts.get(p,0)+1\n"
                  " if sys.argv[4] == p+':'+str(counts[p]): os._exit(79)\n"
                  "value=r.dispatch(sys.argv[2],sys.argv[3],json.loads(sys.argv[5]),fault=crash);"
                  "print(json.dumps(value),flush=True)\n")
        return subprocess.run([sys.executable, "-B", "-c", script, str(ROOT / "core/pysrc"), str(self.root),
                               action, point or "none", json.dumps(request)], capture_output=True, text=True, timeout=30)

    def test_process_crash_at_each_registration_commit_boundary(self):
        points = ("after-payloads", "after-intent", "after-record", "after-slot", "after-page", "after-index",
                  "before-clear-intent", "after-commit")
        # A fresh repository per crash avoids converting this into a recovery
        # test of a different earlier interruption.
        for number, point in enumerate(points):
            with self.subTest(point=point), tempfile.TemporaryDirectory(prefix="ca-recovery-crash-") as directory:
                original = self.root, self.source, self.store
                try:
                    self.root = Path(directory).resolve()
                    subprocess.run(["git", "init", "-q", str(self.root)], check=True)
                    (self.root / ".codearbiter").mkdir()
                    (self.root / ".codearbiter/CONTEXT.md").write_text("---\narbiter: enabled\n---\n")
                    self.source = self.root / "finding.md"
                    self.source.write_text("source remains available\n")
                    self.store = self.root / ".git/codearbiter/workflow-recovery/v1"
                    request = {"candidates": [self.request(number)]}
                    crashed = self.child("register", request, point + ":1")
                    self.assertEqual(crashed.returncode, 79, crashed.stderr)
                    before = self.snapshot()
                    observed = self.call("scan")
                    self.assertEqual(self.snapshot(), before)
                    if point in ("after-payloads", "after-commit"):
                        self.assertEqual(observed["status"], "complete", observed)
                        self.assertEqual(len(observed["items"]), int(point == "after-commit"))
                    else:
                        self.assertEqual(observed["status"], "unavailable", observed)
                        self.assertEqual(self.call("repair")["status"], "repaired")
                    replay = self.call("register", request)
                    self.assertTrue(replay["durable"], replay)
                    self.assertEqual(len(self.call("scan")["items"]), 1)
                finally:
                    self.root, self.source, self.store = original

    def test_process_crash_after_target_and_during_settlement_never_duplicates(self):
        for number, point in enumerate(("after-target:1", "after-record:2")):
            oid = self.registered(self.request(number))
            crashed = self.child("resume", {"obligation_id": oid, "expected_revision": 1}, point)
            self.assertEqual(crashed.returncode, 79, crashed.stderr)
            board = (self.root / ".codearbiter/open-tasks.md").read_bytes()
            marker = ("(from spec:recovery#triage-" + str(number) + ")").encode()
            self.assertEqual(board.count(marker), 1)
            if point == "after-record:2":
                self.assertEqual(self.call("scan")["status"], "unavailable")
                self.assertEqual(self.call("repair")["status"], "repaired")
            record = self.call("get", {"obligation_id": oid})["record"]
            result = self.call("reconcile", {"obligation_id": oid, "expected_revision": record["record_revision"]})
            self.assertEqual(result["status"], "settled", result)
            self.assertEqual(board, (self.root / ".codearbiter/open-tasks.md").read_bytes())

    def test_corrected_candidate_cas_preserves_original_and_unknown_effect(self):
        oid = self.registered()
        offered = self.request()
        offered["candidate"]["title"] = "Corrected follow-up"
        result = self.call("correct", {"obligation_id": oid, "expected_revision": 1,
                                       "candidate": offered["candidate"], "source": offered["source"]})
        self.assertEqual(result["status"], "corrected", result)
        historical = json.loads((self.store / "history" / oid / "000000000001.json").read_text())
        self.assertEqual(historical["candidate"]["title"], "Follow-up 0")
        stale = self.call("correct", {"obligation_id": oid, "expected_revision": 1,
                                      "candidate": offered["candidate"], "source": offered["source"]})
        self.assertEqual(stale["status"], "conflict")
        claimed = self.call("claim", {"obligation_id": oid, "expected_revision": 2})
        self.assertEqual(claimed["status"], "claimed", claimed)
        before = self.snapshot()
        refused = self.call("correct", {"obligation_id": oid, "expected_revision": 3,
                                        "candidate": offered["candidate"], "source": offered["source"]})
        self.assertEqual(refused["reason"], "uncertain-effect")
        self.assertEqual(before, self.snapshot())
        reconciled = self.call("reconcile", {"obligation_id": oid, "expected_revision": 3})
        self.assertEqual(reconciled["status"], "absent-effect", reconciled)
        corrected = self.call("correct", {"obligation_id": oid, "expected_revision": 4,
                                          "candidate": offered["candidate"], "source": offered["source"]})
        self.assertEqual(corrected["status"], "corrected", corrected)
        self.assertNotIn("effect", corrected["record"])

    def test_denial_and_explicit_stop_are_not_cleared_by_correction(self):
        for number, reason in enumerate(recovery.CONTRACT["correction_cannot_clear"]):
            oid = self.registered(self.request(number))
            store = recovery.RecoveryStore(self.root).open()
            with store.lock("writer"):
                current = store.record(oid)
                store.save_record(recovery._updated(current, "WR-07", state="unavailable", reason=reason), previous=current)
            with store.lock(oid):
                pass
            before = self.snapshot()
            for action in ("resume", "restore"):
                result = self.call(action, {"obligation_id": oid, "expected_revision": 2})
                self.assertEqual(result["reason"], reason)
            offer = self.request(number)
            result = self.call("correct", {"obligation_id": oid, "expected_revision": 2,
                                           "candidate": offer["candidate"], "source": offer["source"]})
            self.assertEqual(result["reason"], reason)
            self.assertEqual(before, self.snapshot())

    def test_compacted_terminal_record_preserves_exact_dedup_and_old_history(self):
        oid = self.registered()
        result = self.call("resume", {"obligation_id": oid, "expected_revision": 1})
        self.assertEqual(result["status"], "settled", result)
        receipt = result["record"]["outcome"]
        board = (self.root / ".codearbiter/open-tasks.md").read_bytes()
        compact = self.call("compact", {"obligation_id": oid, "expected_revision": result["record"]["record_revision"]})
        self.assertEqual(compact["status"], "compacted", compact)
        self.assertEqual(compact["record"]["outcome"], receipt)
        self.assertEqual(len(compact["record"]["history"]), 1)
        self.assertTrue((self.store / "history" / oid / "000000000003.json").is_file())
        replay = self.call("register", {"candidates": [self.request()]})
        self.assertTrue(replay["durable"], replay)
        self.assertEqual(replay["items"][0]["state"], "settled")
        self.assertEqual(board, (self.root / ".codearbiter/open-tasks.md").read_bytes())

    def held(self, oid, reason):
        store = recovery.RecoveryStore(self.root).open()
        with store.lock("writer"):
            current = store.record(oid)
            value = recovery._updated(current, "WR-14" if current.get("effect") else "WR-07",
                                      state="unavailable", reason=reason)
            store.save_record(value, previous=current)
        return value

    def test_actual_owner_lift_is_explicit_bookkeeping_and_never_a_target_effect(self):
        oid = self.registered()
        held = self.held(oid, "explicit-stop")
        board = (self.root / ".codearbiter/open-tasks.md").read_bytes()
        self.assertEqual(self.call("restore", {"obligation_id": oid, "expected_revision": 2})["reason"], "explicit-stop")
        bad = self.call("restore-authority", {"obligation_id": oid, "expected_revision": 2,
                                              "authority_source": "validation-passed"})
        self.assertEqual(bad["reason"], "invalid")
        restored = self.call("restore-authority", {"obligation_id": oid, "expected_revision": 2,
                                                   "authority_source": "user:actual-lift-fixture-message"})
        self.assertEqual(restored["status"], "restored", restored)
        self.assertEqual(restored["record"]["last_transition"], "WR-16")
        self.assertEqual(restored["record"]["authority_context"], "user:actual-lift-fixture-message")
        self.assertIn("not a grant", restored["record"]["history"][-1]["detail"])
        self.assertNotIn("authorized", restored["record"])
        self.assertEqual(board, (self.root / ".codearbiter/open-tasks.md").read_bytes())
        prior = json.loads((self.store / "history" / oid / "000000000002.json").read_text())
        self.assertEqual(prior, held)

    def test_new_grant_cannot_clear_unknown_effect_or_reconciliation_clear_denial(self):
        oid = self.registered()
        claim = self.call("claim", {"obligation_id": oid, "expected_revision": 1})
        self.assertEqual(claim["status"], "claimed", claim)
        self.held(oid, "authorization-denied")
        refused = self.call("restore-authority", {"obligation_id": oid, "expected_revision": 3,
                                                  "authority_source": "host:actual-new-grant-fixture-event"})
        self.assertEqual(refused["reason"], "uncertain-effect")
        before = (self.root / ".codearbiter/open-tasks.md").read_bytes()
        observed = self.call("reconcile", {"obligation_id": oid, "expected_revision": 3})
        self.assertEqual(observed["status"], "absent-effect", observed)
        self.assertEqual(observed["record"]["state"], "unavailable")
        self.assertEqual(observed["record"]["reason"], "authorization-denied")
        still_denied = self.call("resume", {"obligation_id": oid, "expected_revision": 4})
        self.assertEqual(still_denied["reason"], "authorization-denied")
        restored = self.call("restore-authority", {"obligation_id": oid, "expected_revision": 4,
                                                   "authority_source": "host:actual-new-grant-fixture-event"})
        self.assertEqual(restored["status"], "restored", restored)
        self.assertNotIn("effect", restored["record"])
        self.assertEqual(before, (self.root / ".codearbiter/open-tasks.md").read_bytes())

    def test_direct_child_mutation_needs_parent_and_creates_no_shared_state(self):
        with mock.patch.dict(os.environ, {"CODEARBITER_SUBAGENT": "1"}):
            refused = self.call("register", {"candidates": [self.request()]})
            self.assertFalse(refused["durable"])
            self.assertEqual(refused["reason"], "authorization-denied")
            self.assertIn("parent", refused["next_action"])
            self.assertEqual(self.call("scan")["status"], "absent")
        self.assertFalse(self.store.exists())

    def test_larger_records_continue_mid_page_without_history_enumeration(self):
        for start in range(0, 18, 3):
            offered = [self.request(i) for i in range(start, start + 3)]
            for item in offered:
                item["candidate"]["description"] = "\U0001f642" * 4000
            self.assertTrue(self.call("register", {"candidates": offered})["durable"])
        ids, cursor = [], None
        for page in range(8):
            with mock.patch.object(recovery.os, "scandir", side_effect=AssertionError("automatic history enumeration")):
                result = self.call("scan", {"cursor": cursor} if cursor else {})
            self.assertIn(result["status"], ("complete", "partial"), result)
            self.assertLessEqual(result["bytes_read"], 262144)
            self.assertLessEqual(len(result["items"]), 32)
            ids.extend(item["obligation_id"] for item in result["items"])
            cursor = result["cursor"]
            if cursor is None:
                break
        self.assertIsNone(cursor)
        self.assertEqual(len(ids), 18)
        self.assertEqual(len(set(ids)), 18)

    def test_corrupt_record_and_future_store_are_unavailable_without_repair_write(self):
        oid = self.registered()
        path = self.store / "records" / (oid + ".json")
        value = json.loads(path.read_text())
        value["schema_version"] = 99
        path.write_text(json.dumps(value))
        before = self.snapshot()
        result = self.call("scan")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "unsupported-version")
        self.assertEqual(before, self.snapshot())
        index = self.store / "index.json"
        value = json.loads(index.read_text())
        value["format"] = "codearbiter.workflow-recovery-store/99"
        index.write_text(json.dumps(value))
        before = self.snapshot()
        self.assertEqual(self.call("repair")["reason"], "unsupported-version")
        self.assertEqual(before, self.snapshot())

    def test_symlink_record_path_is_not_followed(self):
        oid = self.registered()
        record = self.store / "records" / (oid + ".json")
        outside = self.root / "outside.json"
        original = record.read_bytes()
        outside.write_bytes(original)
        record.unlink()
        try:
            os.symlink(outside, record)
        except OSError as exc:
            self.skipTest("host cannot create this symlink fixture: " + type(exc).__name__)
        self.assertEqual(self.call("get", {"obligation_id": oid})["reason"], "corrupt-record")
        self.assertEqual(outside.read_bytes(), original)

    def test_hardlink_record_path_is_not_followed(self):
        oid = self.registered()
        record = self.store / "records" / (oid + ".json")
        outside = self.root / "outside.json"
        original = record.read_bytes()
        outside.write_bytes(original)
        record.unlink()
        os.link(outside, record)
        self.assertEqual(self.call("get", {"obligation_id": oid})["reason"], "corrupt-record")
        self.assertEqual(outside.read_bytes(), original)

    def test_partial_registration_retains_exact_completed_and_remaining_ids(self):
        count = 0
        def fail(point):
            nonlocal count
            if point == "after-record":
                count += 1
                if count == 2:
                    raise OSError("fixture second publication failed")
        offers = [self.request(i) for i in range(3)]
        result = self.call("register", {"candidates": offers}, fault=fail)
        self.assertFalse(result["durable"], result)
        self.assertEqual(result["commit"], "uncertain")
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(len(result["remaining"]), 2)
        self.assertNotIn(result["items"][0]["obligation_id"], result["remaining"])
        self.assertEqual(self.call("scan")["status"], "unavailable")
        self.assertEqual(self.call("repair")["status"], "repaired")
        replay = self.call("register", {"candidates": offers})
        self.assertTrue(replay["durable"], replay)
        self.assertEqual([item["reused"] for item in replay["items"]], [True, True, False])
        self.assertEqual(len(self.call("scan")["items"]), 3)

    def test_post_commit_failure_reports_observed_record_without_false_no_effect(self):
        def fail(point):
            if point == "after-commit":
                raise OSError("fixture response lost after commit")
        result = self.call("register", {"candidates": [self.request()]}, fault=fail)
        self.assertFalse(result["durable"])
        self.assertEqual(result["commit"], "uncertain")
        self.assertEqual(result["observed"][0]["observed_state"], "pending")
        self.assertFalse(result["observed"][0]["transaction_pending"])
        self.assertEqual(result["observed"][0]["effect_outcome"], "not-attempted")
        self.assertTrue(self.call("register", {"candidates": [self.request()]})["durable"])

    def race(self, action, requests):
        gate = self.root / ("race-" + action + ".ready")
        script = ("import sys,json,time;from pathlib import Path;sys.path.insert(0,sys.argv[1]);"
                  "import _workflowrecoverylib as r;print('ready',flush=True)\n"
                  "while not Path(sys.argv[5]).exists():time.sleep(.01)\n"
                  "print(json.dumps(r.dispatch(sys.argv[2],sys.argv[3],json.loads(sys.argv[4]))),flush=True)\n")
        processes = [subprocess.Popen([sys.executable, "-B", "-c", script, str(ROOT / "core/pysrc"), str(self.root),
                                      action, json.dumps(request), str(gate)], stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True) for request in requests]
        try:
            for process in processes:
                self.assertEqual(process.stdout.readline().strip(), "ready")
            gate.write_text("start\n")
            results = []
            for process in processes:
                output, error = process.communicate(timeout=30)
                self.assertEqual(process.returncode, 0, error)
                results.append(json.loads(output))
            return results
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=10)

    def test_multiprocess_claim_correct_and_settle_races_preserve_one_winner(self):
        oid = self.registered()
        claims = self.race("claim", [{"obligation_id": oid, "expected_revision": 1}] * 2)
        self.assertEqual(sum(item["status"] == "claimed" for item in claims), 1, claims)
        self.assertTrue(all(item["status"] in ("claimed", "conflict", "unavailable") for item in claims))
        current = self.call("get", {"obligation_id": oid})["record"]
        self.assertEqual(current["record_revision"], 2)
        absent = self.call("reconcile", {"obligation_id": oid, "expected_revision": 2})
        self.assertEqual(absent["status"], "absent-effect", absent)
        requests = []
        for title in ("First correction", "Second correction"):
            offer = self.request()
            offer["candidate"]["title"] = title
            requests.append({"obligation_id": oid, "expected_revision": 3,
                             "candidate": offer["candidate"], "source": offer["source"]})
        corrected = self.race("correct", requests)
        self.assertEqual(sum(item["status"] == "corrected" for item in corrected), 1, corrected)
        current = self.call("get", {"obligation_id": oid})["record"]
        self.assertEqual(current["record_revision"], 4)
        self.assertIn(current["candidate"]["title"], ("First correction", "Second correction"))
        settled = self.race("resume", [{"obligation_id": oid, "expected_revision": 4}] * 2)
        self.assertEqual(sum(item["status"] == "settled" for item in settled), 1, settled)
        current = self.call("get", {"obligation_id": oid})["record"]
        self.assertEqual(current["record_revision"], 6)
        self.assertEqual(current["state"], "settled")
        self.assertEqual((self.root / ".codearbiter/open-tasks.md").read_text().count("(from spec:recovery#triage-0)"), 1)

    def test_crash_after_history_keeps_old_version_and_recoverable_claim(self):
        oid = self.registered()
        crashed = self.child("claim", {"obligation_id": oid, "expected_revision": 1}, "after-history:1")
        self.assertEqual(crashed.returncode, 79, crashed.stderr)
        self.assertEqual(self.call("scan")["status"], "unavailable")
        self.assertEqual(self.call("repair")["status"], "repaired")
        old = json.loads((self.store / "history" / oid / "000000000001.json").read_text())
        self.assertEqual(old["state"], "pending")
        current = self.call("get", {"obligation_id": oid})["record"]
        self.assertEqual(current["state"], "claimed")
        self.assertEqual(current["record_revision"], 2)

    def test_cancel_and_linked_supersession_are_explicit_and_never_touch_target(self):
        first, second = self.registered(), self.registered(self.request(1))
        board = (self.root / ".codearbiter/open-tasks.md").read_bytes()
        refused = self.call("supersede", {"obligation_id": first, "expected_revision": 1, "replacement": first})
        self.assertEqual(refused["reason"], "material-unavailable")
        result = self.call("supersede", {"obligation_id": first, "expected_revision": 1, "replacement": second})
        self.assertEqual(result["record"]["outcome"]["replacement"], second)
        self.assertEqual(result["record"]["outcome"]["disposition"], "superseded")
        self.assertEqual(self.call("get", {"obligation_id": second})["record"]["state"], "pending")
        cancelled = self.call("cancel", {"obligation_id": second, "expected_revision": 1})
        self.assertEqual(cancelled["record"]["outcome"]["disposition"], "cancelled")
        self.assertEqual(board, (self.root / ".codearbiter/open-tasks.md").read_bytes())
        third = self.registered(self.request(2))
        self.call("claim", {"obligation_id": third, "expected_revision": 1})
        held = self.call("cancel", {"obligation_id": third, "expected_revision": 2})
        self.assertEqual(held["reason"], "uncertain-effect")

    def test_projection_refuses_cross_field_corruption_and_notice_failure_is_nonblocking(self):
        for bad in ({"status": "partial"}, {"status": "complete", "cursor": "abcd"},
                    {"status": "absent", "revision": 1}, {"status": "complete", "bytes_read": True},
                    {"status": "complete", "items": ["bad"]}):
            projected = recovery.snapshot(self.root, result=bad)
            self.assertEqual(projected["status"], "unavailable", bad)
            self.assertLessEqual(len(projected["notice"]), 768)
            self.assertRegex(projected["fingerprint"], r"^[a-f0-9]{64}$")
        self.registered()
        before = self.snapshot()
        with mock.patch.object(recovery, "automatic_snapshot", side_effect=RuntimeError("fixture notice failure")):
            selected = recovery.presentation(self.root, "session")
        self.assertIn("Independent authorized work continues", selected["text"])
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.root / ".codearbiter/.markers").exists())

    def test_replaced_git_anchor_cannot_reuse_previous_obligation_binding(self):
        oid = self.registered()
        prior = self.root / ".git-prior"
        (self.root / ".git").rename(prior)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.assertEqual(self.call("scan")["status"], "absent")
        self.assertFalse((self.root / ".git/codearbiter/workflow-recovery").exists())
        self.assertEqual(self.call("resume", {"obligation_id": oid, "expected_revision": 1})["reason"], "storage-unavailable")
        self.assertTrue((prior / "codearbiter/workflow-recovery/v1/records" / (oid + ".json")).exists())

    def test_same_title_different_origin_is_not_reused_and_branch_change_holds(self):
        board = self.root / ".codearbiter/open-tasks.md"
        board.write_text("# Tasks\n\n## Backlog\n- [ ] Follow-up 0 (from other:source#triage-0)\n")
        oid = self.registered()
        result = self.call("resume", {"obligation_id": oid, "expected_revision": 1})
        self.assertEqual(result["record"]["outcome"]["disposition"], "promoted")
        self.assertEqual(board.read_text().count("Follow-up 0"), 2)
        other = self.registered(self.request(1))
        subprocess.run(["git", "-C", str(self.root), "symbolic-ref", "HEAD", "refs/heads/abandoned-source"], check=True)
        before = board.read_bytes()
        held = self.call("resume", {"obligation_id": other, "expected_revision": 1})
        self.assertEqual(held["reason"], "changed-binding")
        self.assertEqual(board.read_bytes(), before)

    def test_real_linked_worktree_reads_shared_inventory_but_cannot_inherit_effect_binding(self):
        subprocess.run(["git", "-C", str(self.root), "add", ".codearbiter", "finding.md"], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Recovery fixture",
                        "-c", "user.email=recovery@example.invalid", "commit", "-qm", "Disposable baseline"], check=True)
        oid = self.registered()
        sibling = self.root / "linked"
        subprocess.run(["git", "-C", str(self.root), "worktree", "add", "-qb", "linked-recovery", str(sibling)], check=True)
        before = self.snapshot()
        observed = recovery.dispatch(sibling, "scan", {})
        self.assertEqual(observed["status"], "complete", observed)
        self.assertEqual(observed["items"][0]["obligation_id"], oid)
        self.assertEqual(before, self.snapshot())
        board = (sibling / ".codearbiter/open-tasks.md").read_bytes()
        held = recovery.dispatch(sibling, "resume", {"obligation_id": oid, "expected_revision": 1})
        self.assertEqual(held["reason"], "changed-binding", held)
        self.assertEqual(board, (sibling / ".codearbiter/open-tasks.md").read_bytes())
        self.assertEqual((self.root / ".codearbiter/open-tasks.md").read_text(), "# Tasks\n\n## Backlog\n")

    def test_real_append_between_decision_preparation_and_publication_is_never_lost(self):
        number = 0
        for action, filename in (("resume", "open-questions.md"), ("decline", "triage.log")):
            for exists in (False, True):
                with self.subTest(action=action, preexisting=exists):
                    path = self.root / ".codearbiter" / filename
                    path.unlink(missing_ok=True)
                    initial = b"Original independent content\n" if exists else b""
                    if exists:
                        path.write_bytes(initial)
                    offer = self.request(number)
                    number += 1
                    offer["candidate"]["kind"] = "decision"
                    oid = self.registered(offer)
                    atomic = recovery._atomic
                    appended = False

                    def race(target, raw, **kwargs):
                        nonlocal appended
                        if target == path and not appended:
                            appended = True
                            subprocess.run([sys.executable, "-B", "-c",
                                "import sys;open(sys.argv[1],'ab').write(b'Independent concurrent entry\\n')", str(path)],
                                check=True)
                        return atomic(target, raw, **kwargs)

                    with mock.patch.object(recovery, "_atomic", side_effect=race):
                        held = self.call(action, {"obligation_id": oid, "expected_revision": 1})
                    self.assertTrue(appended)
                    self.assertEqual(path.read_bytes(), initial + b"Independent concurrent entry\n")
                    self.assertEqual(held["reason"], "changed-binding", held)
                    record = self.call("get", {"obligation_id": oid})["record"]
                    self.assertEqual(record["state"], "unavailable")
                    self.assertIn("effect", record)
                    absent = self.call("reconcile", {"obligation_id": oid, "expected_revision": record["record_revision"]})
                    self.assertEqual(absent["status"], "absent-effect", absent)
                    settled = self.call(action, {"obligation_id": oid, "expected_revision": absent["record"]["record_revision"]})
                    self.assertEqual(settled["status"], "settled", settled)
                    self.assertEqual(path.read_text().count("Independent concurrent entry"), 1)
                    self.assertEqual(path.read_text().count("(from " + offer["origin"] + ")"), 1)


if __name__ == "__main__":
    unittest.main()

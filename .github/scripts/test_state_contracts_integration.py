"""P-02 admission negatives use a real disposable Git history, not product claims."""
import copy
import fnmatch
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import check_state_contracts_integration as owner

REPO = Path(os.environ.get("CODEARBITER_TEST_SOURCE_REPO", Path(__file__).resolve().parents[2]))
SOURCE = subprocess.run(["git", "--no-lazy-fetch", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, check=True).stdout.decode().strip()
C = owner.CORPUS


class IntegrationIntegrityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_blobs = {}
        cls.tmp = tempfile.TemporaryDirectory(prefix="ca-integration-ledger-fixture-")
        cls.repo = Path(cls.tmp.name)
        def git(*args):
            return subprocess.run(["git", *args], cwd=cls.repo, capture_output=True, check=True).stdout.decode().strip()
        cls.git = staticmethod(git)
        git("init", "-q")
        git("config", "user.name", "Disposable integrity fixture")
        git("config", "user.email", "fixture@example.invalid")
        def put(path, data):
            p = cls.repo / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data if isinstance(data, bytes) else json.dumps(data).encode())
        cls.put = staticmethod(put)
        def original(path):
            return subprocess.run(["git", "show", SOURCE + ":" + path], cwd=REPO, capture_output=True, check=True).stdout
        manifest = json.loads(original(C + "MANIFEST.json"))
        put(C + "MANIFEST.json", original(C + "MANIFEST.json"))
        for entry in manifest["files"]:
            put(C + entry["path"], original(C + entry["path"]))
        cls.input = "plugins/ca-pi/tools/test/setup-disposable-home.ts"
        put(cls.input, original(cls.input))
        put(C + "execution/tools/coverage_ledger.py", original(C + "execution/tools/coverage_ledger.py"))
        cls.progress = json.loads(original(C + "execution/progress.json"))
        put(C + "execution/progress.json", cls.progress)
        cls.ledger = json.loads(original(C + "execution/coverage-ledger.json"))
        for group in ("findings", "machines", "transitions", "added_transitions"):
            for row in cls.ledger[group].values():
                row.update(status="PLANNED", evidence=[])
        put(C + "execution/coverage-ledger.json", cls.ledger)
        git("add", ".")
        git("commit", "-qm", "Original partial program fixture")
        cls.tested = git("rev-parse", "HEAD")
        cls.identity = "pi-qualification:disposable-home:01"
        cls.cell = "disposition:transitions:" + cls.identity
        cls.raw_path = "retained/raw.txt"
        put(cls.raw_path, b"explicit test fixture raw observation\n")
        cls.proof_path = "retained/proof.json"
        cls.proof = {"schema": "codearbiter-disposition-evidence/1", "source_commit": cls.tested,
            "kind": "test", "result": "PASSED", "producer": {"class": "local-host", "identity": "explicit admission test fixture"},
            "inputs": {cls.input: hashlib.sha256(original(cls.input)).hexdigest()}, "disposition_ids": [cls.cell],
            "raw_evidence": [{"path": cls.raw_path, "sha256": hashlib.sha256((cls.repo / cls.raw_path).read_bytes()).hexdigest()}],
            "commands": [{"argv": ["python", "fixture.py"], "exit_code": 0}]}
        put(cls.proof_path, cls.proof)
        cls.claimed = copy.deepcopy(cls.ledger)
        cls.claimed["transitions"][cls.identity].update(status="TESTED", evidence=[{"kind": "test", "commit": cls.tested,
            "ref": cls.proof_path, "sha256": hashlib.sha256((cls.repo / cls.proof_path).read_bytes()).hexdigest()}])
        put(C + "execution/coverage-ledger.json", cls.claimed)
        git("add", ".")
        git("commit", "-qm", "Retain original proof")
        cls.current = git("rev-parse", "HEAD")
        put(cls.input, b"changed current owner bytes\n")
        git("add", ".")
        git("commit", "-qm", "Current inputs change without rewriting history")
        cls.stale = git("rev-parse", "HEAD")
        git("rm", "-q", cls.input)
        git("commit", "-qm", "Current input unavailable")
        cls.unavailable = git("rev-parse", "HEAD")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def load(self, commit, path):
        key = (commit, path)
        if key in self.overrides:
            return self.overrides[key]
        if key not in self.original_blobs:
            self.original_blobs[key] = owner.readiness.blob(self.repo, commit, path)
        return self.original_blobs[key]

    def setUp(self):
        self.overrides = {}

    def check(self, source=None):
        return owner.validate(self.repo, source or self.current, self.load)

    def replace_ledger(self, ledger):
        self.overrides[self.current, C + "execution/coverage-ledger.json"] = json.dumps(ledger).encode()

    def test_planned_and_implemented_partial_program_pass_without_publication(self):
        ledger = copy.deepcopy(self.ledger)
        row = ledger["transitions"][self.identity]
        row.update(status="IMPLEMENTED", evidence=[{"kind": "review", "commit": self.tested, "ref": self.input}])
        self.replace_ledger(ledger)
        report = self.check()
        self.assertEqual(report["result"], "PASSED")
        self.assertFalse(report["product_qualification"])
        self.assertEqual(report["publication_readiness"], "NOT_ASSESSED")

    def test_original_proof_passes_and_records_applicable(self):
        self.assertEqual(self.check()["current_applicability"][self.cell]["status"], "APPLICABLE")

    def test_stale_history_passes_integration_but_strict_publication_refuses(self):
        report = self.check(self.stale)
        self.assertEqual(report["current_applicability"][self.cell]["status"], "STALE")
        self.assertFalse(report["recorded_statuses_changed"])
        row = self.claimed["transitions"][self.identity]
        with self.assertRaisesRegex(owner.readiness.ReadinessError, "evidence bytes differ"):
            owner.readiness.authenticate_disposition(self.repo, self.stale, self.cell, row, {self.input}, self.load, {})

    def test_unavailable_current_input_is_unknown_not_passed_applicability(self):
        self.assertEqual(self.check(self.unavailable)["current_applicability"][self.cell]["status"], "UNKNOWN")

    def test_changed_original_raw_proof_refuses_even_when_current_source_stale(self):
        self.overrides[self.stale, self.raw_path] = b"forged retained observation"
        with self.assertRaisesRegex(owner.readiness.ReadinessError, "evidence bytes differ"):
            self.check(self.stale)

    def test_changed_original_input_refuses_even_when_current_source_stale(self):
        self.overrides[self.tested, self.input] = b"forged original input"
        with self.assertRaisesRegex(owner.readiness.ReadinessError, "evidence bytes differ"):
            self.check(self.stale)

    def test_frozen_intake_changed_bytes_refuse(self):
        self.overrides[self.current, C + "PROGRAM.md"] = b"changed frozen contract"
        with self.assertRaisesRegex(owner.readiness.ReadinessError, "frozen intake identity"):
            self.check()

    def test_rehashed_frozen_file_and_manifest_cannot_rebaseline(self):
        original_manifest = json.loads(self.load(self.current, C + "MANIFEST.json"))
        replacement = b"rewritten frozen program contract"
        entry = next(x for x in original_manifest["files"] if x["path"] == "PROGRAM.md")
        entry.update(bytes=len(replacement), sha256=hashlib.sha256(replacement).hexdigest())
        self.overrides[self.current, C + "PROGRAM.md"] = replacement
        self.overrides[self.current, C + "MANIFEST.json"] = json.dumps(original_manifest).encode()
        with self.assertRaisesRegex(owner.readiness.ReadinessError, "accepted frozen intake manifest identity"):
            self.check()

    def test_missing_and_extra_population_refuse(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                ledger = copy.deepcopy(self.ledger)
                if missing:
                    ledger["transitions"].pop(self.identity)
                else:
                    ledger["transitions"]["extra"] = copy.deepcopy(ledger["transitions"][self.identity])
                self.replace_ledger(ledger)
                with self.assertRaisesRegex(owner.readiness.ReadinessError, "population differs"):
                    self.check()

    def test_unknown_owner_status_task_and_bad_reference_refuse(self):
        mutations = [("owner", "invented"), ("status", "DONE"), ("task_ids", ["XX-99"]),
                     ("evidence", [{"kind": "test", "commit": self.tested, "ref": "../escape"}])]
        for field, value in mutations:
            with self.subTest(field=field):
                ledger = copy.deepcopy(self.claimed)
                ledger["transitions"][self.identity][field] = value
                self.replace_ledger(ledger)
                with self.assertRaises(owner.readiness.ReadinessError):
                    self.check()

    def test_missing_commands_and_scope_refuse(self):
        for field in ("commands", "disposition_ids"):
            with self.subTest(field=field):
                proof = copy.deepcopy(self.proof)
                proof[field] = []
                encoded = json.dumps(proof).encode()
                self.overrides[self.current, self.proof_path] = encoded
                ledger = copy.deepcopy(self.claimed)
                ledger["transitions"][self.identity]["evidence"][0]["sha256"] = hashlib.sha256(encoded).hexdigest()
                self.replace_ledger(ledger)
                with self.assertRaises(owner.readiness.ReadinessError):
                    self.check()

    def claim_with_raw_origin(self, producer_class, hosted_field):
        proof = copy.deepcopy(self.proof)
        proof["producer"]["class"] = producer_class
        proof["raw_evidence"][0][hosted_field] = 1
        if producer_class == "hosted":
            # This is the reported bypass: one marker satisfied the hosted
            # class while the valid local path avoided every API observation.
            proof["raw_evidence"][0]["run_id"] = 1
        encoded = json.dumps(proof).encode()
        self.overrides[self.current, self.proof_path] = encoded
        ledger = copy.deepcopy(self.claimed)
        ledger["transitions"][self.identity]["evidence"][0]["sha256"] = hashlib.sha256(encoded).hexdigest()
        self.replace_ledger(ledger)
        return ledger["transitions"][self.identity]

    def test_hosted_claim_cannot_borrow_valid_local_raw_path(self):
        for field in ("run_id", "job_id", "artifact_id"):
            with self.subTest(field=field):
                self.claim_with_raw_origin("hosted", field)
                with self.assertRaisesRegex(owner.readiness.ReadinessError, "mixed original raw evidence origin"):
                    self.check()

    def test_publication_rejects_hosted_identity_fields_on_local_raw_path(self):
        for field in ("run_id", "job_id", "artifact_id"):
            with self.subTest(field=field):
                row = self.claim_with_raw_origin("local-host", field)
                with self.assertRaisesRegex(owner.readiness.ReadinessError, "mixed original raw evidence origin"):
                    owner.readiness.authenticate_disposition(self.repo, self.current, self.cell,
                                                            row, {self.input}, self.load, {})

    def test_added_transition_requires_matching_declared_population(self):
        ledger = copy.deepcopy(self.ledger)
        ledger["added_transitions"]["invented"] = copy.deepcopy(ledger["transitions"][self.identity])
        self.replace_ledger(ledger)
        with self.assertRaisesRegex(owner.readiness.ReadinessError, "population differs"):
            self.check()


    def membership_case(self, *, membership=True, absence=False, wrong_original=False, present_host=False, host_input=False):
        # Synthetic admission fixture, never a product observation/proof.
        module = "core/artifacts"
        self.git("rm", "-rf", "--ignore-unmatch", "core/artifacts", "core/pysrc/_host.py", "core/pysrc/hostapi.py")
        files = {self.input: self.load(self.tested, self.input),
                 module + "/go.mod": b"module fixture.invalid/native\n\ngo 1.24\n",
                 module + "/main.go": b"package main\nfunc main() {}\n"}
        if absence or host_input:
            files["core/pysrc/hostapi.py"] = b"# explicit lookup owner fixture, not executed\n"
        if present_host:
            files["core/pysrc/_host.py"] = b"# existing fixture lookup, never executed\n"
        for path, value in files.items(): self.put(path, value)
        self.git("add", "."); self.git("commit", "-qm", "Original membership fixture", "--allow-empty")
        tested = self.git("rev-parse", "HEAD")
        proof = copy.deepcopy(self.proof)
        proof["source_commit"] = tested
        proof["inputs"] = {p: hashlib.sha256(v).hexdigest() for p, v in files.items() if not p.endswith(("/main.go", "/_host.py"))}
        if membership:
            h = hashlib.sha256()
            for p, data in sorted((p[len(module)+1:], v) for p, v in files.items() if p.startswith(module + "/")):
                name = p.encode(); h.update(len(name).to_bytes(4,"big")); h.update(name)
                h.update(len(data).to_bytes(8,"big")); h.update(hashlib.sha256(data).digest())
            proof["input_membership"] = [{"profile":"go-module-v1", "root":module,
                                          "path_order":"posix", "sha256":"0"*64 if wrong_original else h.hexdigest()}]
        if absence:
            proof["absent_inputs"] = [{"path":"core/pysrc/_host.py", "path_style":"windows"}]
        encoded = json.dumps(proof).encode(); self.put(self.proof_path, encoded)
        ledger = copy.deepcopy(self.ledger)
        row = ledger["transitions"][self.identity]
        row.update(status="TESTED", evidence=[{"kind":"test", "commit":tested, "ref":self.proof_path,
                                               "sha256":hashlib.sha256(encoded).hexdigest()}])
        self.put(C + "execution/coverage-ledger.json", ledger)
        self.git("add", ".");self.git("commit", "-qm", "Retain declared membership proof")
        return self.git("rev-parse", "HEAD"), row

    def test_added_and_removed_native_members_are_stale_not_relabelled(self):
        for removal in (False, True):
            with self.subTest(removal=removal):
                current, row = self.membership_case()
                if removal: self.git("rm", "-q", "core/artifacts/main.go")
                else: self.put("core/artifacts/added.go", b"package main\nfunc init() {}\n")
                self.git("add", "."); self.git("commit", "-qm", "Change membership without positive-byte drift")
                candidate = self.git("rev-parse", "HEAD")
                report = owner.validate(self.repo, candidate)
                self.assertEqual(report["current_applicability"][self.cell]["status"], "STALE")
                self.assertFalse(report["recorded_statuses_changed"])
                with self.assertRaises(owner.readiness.ReadinessError):
                    owner.readiness.authenticate_disposition(self.repo,candidate,self.cell,row,{self.input},self.load,{})
                owner.readiness.authenticate_recorded_disposition(self.repo,candidate,self.cell,row,{self.input},self.load,{})

    def test_explicit_owned_absence_becoming_present_is_stale(self):
        current, row = self.membership_case(absence=True)
        self.put("core/pysrc/_host.py", b"# not executed\n")
        self.git("add", "."); self.git("commit", "-qm", "Formerly absent owned lookup appears")
        candidate=self.git("rev-parse", "HEAD")
        self.assertEqual(owner.validate(self.repo,candidate)["current_applicability"][self.cell]["status"], "STALE")
        with self.assertRaises(owner.readiness.ReadinessError):
            owner.readiness.authenticate_disposition(self.repo,candidate,self.cell,row,{self.input},self.load,{})

    def test_forged_original_module_scope_refuses_historical_authentication(self):
        current, row = self.membership_case(wrong_original=True)
        with self.assertRaisesRegex(owner.readiness.ReadinessError, "membership"):
            owner.validate(self.repo,current)

    def test_legacy_runtime_native_positive_scope_is_unknown_not_complete(self):
        current, row = self.membership_case(membership=False)
        self.assertEqual(owner.validate(self.repo,current)["current_applicability"][self.cell]["status"], "UNKNOWN")
        with self.assertRaises(owner.readiness.ReadinessError):
            owner.readiness.authenticate_disposition(self.repo,current,self.cell,row,{self.input},self.load,{})
        owner.readiness.authenticate_recorded_disposition(self.repo,current,self.cell,row,{self.input},self.load,{})

    def test_valid_declared_scope_and_absence_are_applicable(self):
        current,row=self.membership_case(absence=True)
        self.assertEqual(owner.validate(self.repo,current)["current_applicability"][self.cell]["status"], "APPLICABLE")
        owner.readiness.authenticate_disposition(self.repo,current,self.cell,row,{self.input},self.load,{})


    def test_failed_candidate_inventory_is_unknown_not_absent(self):
        current,row=self.membership_case(absence=True)
        self.git("commit", "--allow-empty", "-qm", "Candidate read failure scope")
        candidate=self.git("rev-parse", "HEAD")
        real=owner.readiness.command
        def read(argv, cwd=None):
            if "ls-tree" in argv and any(x.startswith(candidate) for x in argv):
                raise owner.readiness.ReadinessError("controlled inventory read failure")
            return real(argv,cwd)
        with mock.patch.object(owner.readiness,"command",side_effect=read):
            self.assertEqual(owner.validate(self.repo,candidate)["current_applicability"][self.cell]["status"], "UNKNOWN")
            with self.assertRaises(owner.readiness.ReadinessError):
                owner.readiness.authenticate_disposition(self.repo,candidate,self.cell,row,{self.input},self.load,{})

    def test_declared_absence_already_present_at_original_refuses(self):
        current,row=self.membership_case(absence=True,present_host=True)
        with self.assertRaisesRegex(owner.readiness.ReadinessError,"absence"):
            owner.validate(self.repo,current)


    def test_unsupported_git_membership_objects_are_unknown(self):
        for mode in ("120000", "160000"):
            with self.subTest(mode=mode):
                current,row=self.membership_case()
                oid = (subprocess.run(["git","hash-object","-w","--stdin"],cwd=self.repo,
                       input=b"outside",capture_output=True,check=True).stdout.decode().strip()
                       if mode == "120000" else current)
                self.git("update-index","--add","--cacheinfo",mode+","+oid+",core/artifacts/linked")
                self.git("commit","-qm","Unsupported immutable Git member")
                candidate=self.git("rev-parse","HEAD")
                self.assertEqual(owner.validate(self.repo,candidate)["current_applicability"][self.cell]["status"], "UNKNOWN")
                with self.assertRaises(owner.readiness.ReadinessError):
                    owner.readiness.authenticate_disposition(self.repo,candidate,self.cell,row,{self.input},self.load,{})

    def test_unrelated_host_addition_does_not_invalidate_native_membership(self):
        current,row=self.membership_case()
        self.put("unrelated/_host.py",b"# unrelated lookup, never imported\n")
        self.git("add",".");self.git("commit","-qm","Unrelated host file is outside scope")
        candidate=self.git("rev-parse","HEAD")
        self.assertEqual(owner.validate(self.repo,candidate)["current_applicability"][self.cell]["status"], "APPLICABLE")

    def test_source_conformance_remains_declared_positive_scope(self):
        current,row=self.membership_case(membership=False)
        proof=json.loads(self.load(current,self.proof_path))
        proof.update(kind="conformance-check",result="PRESERVED",producer={"class":"source-conformance","identity":"Instruction fixture only"})
        encoded=json.dumps(proof).encode();self.overrides[current,self.proof_path]=encoded
        ledger=copy.deepcopy(self.ledger);row=ledger["transitions"][self.identity]
        row.update(status="PRESERVED",evidence=[{"kind":"conformance-check","commit":proof["source_commit"],
                   "ref":self.proof_path,"sha256":hashlib.sha256(encoded).hexdigest()}])
        self.overrides[current,C+"execution/coverage-ledger.json"]=json.dumps(ledger).encode()
        self.assertEqual(self.check(current)["current_applicability"][self.cell]["status"], "APPLICABLE")

    def test_unsupported_or_unowned_scope_declarations_refuse(self):
        current,row=self.membership_case()
        baseline=json.loads(self.load(current,self.proof_path))
        for change in ("profile", "path", "extra", "absence", "duplicate"):
            with self.subTest(change=change):
                proof=copy.deepcopy(baseline)
                if change=="profile":proof["input_membership"][0]["profile"]="unknown"
                if change=="path":proof["input_membership"][0]["root"]="../outside"
                if change=="extra":proof["input_membership"][0]["optional"]="unsupported"
                if change=="absence":proof["absent_inputs"]=["unrelated/_host.py"]
                if change=="duplicate":proof["input_membership"]*=2
                encoded=json.dumps(proof).encode();self.overrides[current,self.proof_path]=encoded
                ledger=copy.deepcopy(self.ledger);claim=copy.deepcopy(row)
                claim["evidence"][0]["sha256"]=hashlib.sha256(encoded).hexdigest()
                ledger["transitions"][self.identity]=claim
                self.overrides[current,C+"execution/coverage-ledger.json"]=json.dumps(ledger).encode()
                with self.assertRaises(owner.readiness.ReadinessError):self.check(current)


    def test_runtime_host_owner_without_positive_or_absent_lookup_is_unknown(self):
        current,row=self.membership_case(host_input=True)
        self.assertEqual(owner.validate(self.repo,current)["current_applicability"][self.cell]["status"], "UNKNOWN")
        self.put("core/pysrc/_host.py",b"# formerly unbound host lookup, never imported\n")
        self.git("add",".");self.git("commit","-qm","Unbound host lookup appears")
        candidate=self.git("rev-parse","HEAD")
        self.assertEqual(owner.validate(self.repo,candidate)["current_applicability"][self.cell]["status"], "UNKNOWN")
        with self.assertRaises(owner.readiness.ReadinessError):
            owner.readiness.authenticate_disposition(self.repo,candidate,self.cell,row,{self.input},self.load,{})
        owner.readiness.authenticate_recorded_disposition(self.repo,candidate,self.cell,row,{self.input},self.load,{})


    def test_windows_case_variant_host_lookup_is_not_absent(self):
        current,row=self.membership_case(absence=True)
        self.put("core/pysrc/_HOST.py",b"# inert actual Windows lookup, never imported\n")
        self.git("add",".");self.git("commit","-qm","Case variant optional host lookup appears")
        candidate=self.git("rev-parse","HEAD")
        # On Windows this exact lowercase lookup opens _HOST.py.
        if os.name == "nt":self.assertTrue((self.repo/"core/pysrc/_host.py").is_file())
        self.assertEqual(owner.validate(self.repo,candidate)["current_applicability"][self.cell]["status"], "STALE")
        with self.assertRaises(owner.readiness.ReadinessError):
            owner.readiness.authenticate_disposition(self.repo,candidate,self.cell,row,{self.input},self.load,{})


    def inert_lookup_commit(self, paths):
        # Git-only trees let Windows test both case-distinct names safely.
        blob = subprocess.run(["git","hash-object","-w","--stdin"],cwd=self.repo,
                              input=b"# inert lookup, never imported\n",capture_output=True,check=True).stdout.decode().strip()
        tree = {}
        for path in paths:
            node=tree
            for name in path.split("/")[:-1]:node=node.setdefault(name,{})
            node[path.split("/")[-1]]=blob
        def write(node):
            rows=[]
            for name,value in node.items():
                is_tree=isinstance(value,dict)
                oid=write(value) if is_tree else value
                rows.append((("040000 tree " if is_tree else "100644 blob ")+oid+"\t"+name).encode("utf8")+b"\0")
            return subprocess.run(["git","mktree","-z"],cwd=self.repo,input=b"".join(rows),
                                  capture_output=True,check=True).stdout.decode().strip()
        return self.git("commit-tree",write(tree),"-p",self.current,"-m","Inert case lookup inventory")

    def test_windows_lookup_resolves_each_actual_ancestor_name(self):
        commit=self.inert_lookup_commit(["Core/PySrc/_HOST.py"])
        lookup={"path":"core/pysrc/_host.py","path_style":"windows"}
        self.assertTrue(owner.readiness._lookup_present(self.repo,commit,lookup,{}))
        self.assertFalse(owner.readiness._lookup_present(self.repo,commit,dict(lookup,path_style="posix"),{}))
        self.assertTrue(owner.readiness._lookup_present(self.repo,commit,{"path":"Core/PySrc/_HOST.py","path_style":"posix"},{}))

    def test_windows_ambiguous_ancestor_lookup_refuses(self):
        commit=self.inert_lookup_commit(["core/pysrc/one.py","CORE/pysrc/two.py"])
        with self.assertRaisesRegex(owner.readiness.ReadinessError,"ambiguous"):
            owner.readiness._lookup_present(self.repo,commit,{"path":"core/pysrc/_host.py","path_style":"windows"},{})
        self.assertFalse(owner.readiness._lookup_present(self.repo,commit,{"path":"core/pysrc/_host.py","path_style":"posix"},{}))

    def test_windows_non_ascii_comparison_refuses_but_posix_is_literal(self):
        commit=self.inert_lookup_commit(["core/pysrc/Khost.py"])
        with self.assertRaisesRegex(owner.readiness.ReadinessError,"unsupported Windows"):
            owner.readiness._lookup_present(self.repo,commit,{"path":"core/pysrc/_host.py","path_style":"windows"},{})
        self.assertTrue(owner.readiness._lookup_present(self.repo,commit,{"path":"core/pysrc/Khost.py","path_style":"posix"},{}))

    def test_absence_lookup_descriptor_requires_closed_supported_style(self):
        current,row=self.membership_case(absence=True)
        baseline=json.loads(self.load(current,self.proof_path))
        for lookup in ("core/pysrc/_host.py",{"path":"core/pysrc/_host.py","path_style":"other"},
                       {"path":"core/pysrc/_host.py","path_style":"windows","extra":True},
                       {"path":"cöre/pysrc/_host.py","path_style":"windows"}):
            with self.subTest(lookup=lookup):
                proof=copy.deepcopy(baseline);proof["absent_inputs"]=[lookup]
                encoded=json.dumps(proof).encode();self.overrides[current,self.proof_path]=encoded
                ledger=copy.deepcopy(self.ledger);claim=copy.deepcopy(row)
                claim["evidence"][0]["sha256"]=hashlib.sha256(encoded).hexdigest()
                ledger["transitions"][self.identity]=claim
                self.overrides[current,C+"execution/coverage-ledger.json"]=json.dumps(ledger).encode()
                with self.assertRaises(owner.readiness.ReadinessError):self.check(current)


class IntegrationWorkflowWiringTest(unittest.TestCase):
    COMMANDS = [
        "python docs/state-contracts-major/execution/tools/coverage_ledger.py check",
        "python .github/scripts/check_state_contracts_integration.py",
        "python .github/scripts/test_state_contracts_integration.py",
    ]

    def workflow(self):
        path = Path(os.environ.get("CODEARBITER_TEST_CI_PATH", REPO / ".github/workflows/ci.yml"))
        return path.read_text(encoding="utf-8")

    def job(self, text, name):
        match = re.search(r"(?ms)^  " + re.escape(name) + r":\n(.*?)(?=^  [A-Za-z0-9_-]+:|\Z)", text)
        self.assertIsNotNone(match, "missing " + name + " job")
        return match.group(1)

    def test_actual_owning_ci_runs_partial_check_for_ledger_only_children(self):
        text = self.workflow()
        hooks_filter = re.search(r"(?ms)^            hooks:\n(.*?)(?=^            [A-Za-z0-9_-]+:|\Z)", text).group(1)
        self.assertNotIn("docs/state-contracts-major/**", hooks_filter)
        job = self.job(text, "program-integrity")
        self.assertIn("    needs: changes\n", job)
        self.assertIn("    if: needs.changes.outputs.program_integrity == 'true'\n", job)
        self.assertIn("      fail-fast: false\n", job)
        self.assertIn("        os: [ubuntu-latest, windows-latest, macos-latest]\n", job)
        self.assertIn("    runs-on: ${{ matrix.os }}\n", job)
        self.assertIn("    timeout-minutes: 5\n", job)
        self.assertIn("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", job)
        self.assertIn("actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0", job)
        self.assertIn('python-version: "3.14"', job)
        self.assertIn("fetch-depth: 0", job)
        self.assertIn("persist-credentials: false", job)
        self.assertNotIn("setup-go@", job)
        self.assertNotIn("build-artifacts.py", job)
        self.assertNotIn("continue-on-error:", job)
        self.assertNotIn("--require-complete", job)
        self.assertEqual(re.findall(r"(?m)^        run: (.*)$", job), self.COMMANDS)
        self.assertEqual(re.findall(r"(?m)^        if: (.*)$", job), [])
        hooks = self.job(text, "hooks")
        self.assertIn("    timeout-minutes: 20\n", hooks)
        for command in self.COMMANDS:
            self.assertNotIn(command, hooks)
        aggregate = self.job(text, "ci-passed")
        self.assertIn("      - program-integrity\n", aggregate)
        required = re.search(r'(?m)^          required_results="([^"\n]*)"$', aggregate).group(1)
        self.assertIn("${{ needs['program-integrity'].result }}", required)
        self.assertIn('program_integrity_required="${{ needs.changes.outputs.program_integrity }}"', aggregate)
        self.assertIn('program_integrity_result="${{ needs[\'program-integrity\'].result }}"', aggregate)

    def test_metadata_only_paths_select_integrity_without_full_hooks(self):
        text = self.workflow()
        def patterns(name):
            match = re.search(r"(?ms)^            " + re.escape(name) + r":\n(.*?)(?=^            [A-Za-z0-9_-]+:|\Z)", text)
            self.assertIsNotNone(match, "missing dedicated " + name + " filter")
            return re.findall(r"(?m)^              - '([^']+)'$", match.group(1))
        program, hooks = patterns("program_integrity"), patterns("hooks")
        self.assertEqual(program, ["docs/state-contracts-major/**", ".github/scripts/check_state_contracts_integration.py",
                                   ".github/scripts/test_state_contracts_integration.py", ".github/scripts/major_readiness.py",
                                   ".github/workflows/ci.yml"])
        for path in ("docs/state-contracts-major/execution/coverage-ledger.json",
                     "docs/state-contracts-major/execution/progress.json"):
            with self.subTest(path=path):
                self.assertTrue(any(fnmatch.fnmatchcase(path, pattern) for pattern in program))
                self.assertFalse(any(fnmatch.fnmatchcase(path, pattern) for pattern in hooks))
        self.assertRegex(text, r"(?m)^      program_integrity: \$\{\{ steps\.filter\.outputs\.program_integrity == 'true' ")

    def test_hosted_proof_token_is_step_local_and_job_permissions_are_read_only(self):
        text = self.workflow()
        job = self.job(text, "program-integrity")
        pre = job.split("    steps:\n", 1)[0]
        permissions = re.search(r"(?m)^    permissions:\n((?:      [^\n]+\n)+)", pre).group(1)
        self.assertEqual(permissions, "      contents: read\n      actions: read\n")
        steps = re.split(r"(?m)^      - ", job.split("    steps:\n", 1)[1])[1:]
        consumers = [step for step in steps if "run: python .github/scripts/check_state_contracts_integration.py" in step]
        self.assertEqual(len(consumers), 1)
        self.assertIn("        env:\n          GH_TOKEN: ${{ github.token }}\n", consumers[0])
        for step in steps:
            if step != consumers[0]:
                self.assertNotIn("GH_TOKEN:", step)
        self.assertNotIn("GH_TOKEN:", self.job(text, "hooks"))

    def test_selected_integrity_failure_cancellation_and_skip_refuse_actual_merge_gate(self):
        text = self.workflow()
        self.job(text, "program-integrity")
        aggregate = self.job(text, "ci-passed")
        body = aggregate.split("        run: |\n", 1)[1]
        script = "\n".join(line[10:] for line in body.splitlines() if line.startswith("          "))
        import shutil
        bash = Path("C:/Program Files/Git/bin/bash.exe") if os.name == "nt" else None
        if bash is None or not bash.is_file():
            found = shutil.which("bash")
            self.assertIsNotNone(found, "supported CI requires Bash for its actual merge gate")
            bash = Path(found)
        for selected, result, expected in [(True, "success", 0), (True, "failure", 1),
                                           (True, "cancelled", 1), (True, "skipped", 1), (True, "", 1),
                                           (False, "skipped", 0)]:
            with self.subTest(selected=selected, result=result):
                def value(match):
                    expression = match.group(1).strip()
                    if expression == "needs.changes.outputs.program_integrity":
                        return "true" if selected else "false"
                    if expression == "needs.changes.outputs.hooks":
                        return "false"  # Ledger-only change: full hooks are unselected.
                    if expression == "needs['program-integrity'].result":
                        return result
                    if expression == "needs.changes.outputs.artifacts":
                        return "false"
                    self.assertTrue(expression.endswith(".result"), expression)
                    return "success"
                actual = re.sub(r"\$\{\{(.*?)\}\}", value, script)
                with tempfile.TemporaryDirectory(prefix="ca-merge-gate-fixture-") as home:
                    env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP", "PATH") if key in os.environ}
                    env.update(HOME=home, USERPROFILE=home)
                    process = subprocess.run([str(bash), "--noprofile", "--norc", "-c", actual],
                                             env=env, capture_output=True, text=True, timeout=15)
                self.assertEqual(process.returncode, expected, process.stdout + process.stderr)


if __name__ == "__main__":
    unittest.main()

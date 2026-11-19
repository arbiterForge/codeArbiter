"""Pure guards/protocol only; never starts Pi, a provider, PTY or a subprocess."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("pi_parent_tui_observation", Path(__file__).with_name("pi_parent_tui_observation.py"))
owner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(owner)
NONCE = "0123456789abcdef"

def dialog(operation, cwd="/private/project"):
    text = owner.compact(operation["params"])
    return ("\x1b[32mAllow governed operation?\x1b[0m\r\nDelegated " + operation["tool"] + " in " + cwd
            + "\r\n" + text + "\r\nSHA-256: " + owner.sha(text.encode())
            + "\r\nThe parent executes this exact request on the trusted host.\r\n→ Yes\r\nNo\r\n").encode()

class PromptProtocolTests(unittest.TestCase):
    def test_new_exact_rendered_prompt_is_required_before_each_consent(self):
        gate = owner.PromptGate(NONCE)
        for operation in owner.operations(NONCE):
            self.assertIsNone(gate.consent("/private/project"))
            gate.feed(dialog(operation))
            self.assertEqual(gate.consent("/private/project"), b"\r")
            self.assertIsNone(gate.consent("/private/project"), "old prompt output cannot approve the next operation")
        self.assertEqual(len(gate.events), 3)

    def test_decline_requires_fresh_dialog_and_visible_no_before_enter(self):
        cwd = "/private/project"
        gate = owner.PromptGate(NONCE)
        for operation in owner.operations(NONCE):
            gate.feed(dialog(operation))
            self.assertEqual(gate.consent(cwd), b"\r")
        gate.feed(dialog(gate.ops[-2]))
        self.assertIsNone(gate.consent(cwd))
        gate.feed(dialog(owner.declined_write(NONCE)))
        self.assertEqual(gate.consent(cwd), b"j")
        self.assertIsNone(gate.consent(cwd))
        gate.feed("→ Yes\r\n".encode())
        self.assertIsNone(gate.consent(cwd))
        gate.feed(b" No\r\n")
        self.assertIsNone(gate.consent(cwd))
        gate.feed("  \x1b[32m→ No\x1b[0m\r\n".encode())
        self.assertEqual(gate.consent(cwd), b"\r")
        self.assertEqual(len(gate.events), 4)
        self.assertEqual(gate.events[-1]["input_hex"], "6a0d")
        self.assertEqual(gate.events[-1]["decision"], "declined")
        self.assertGreater(gate.events[-1]["no_selected_output_end"], gate.events[-1]["new_output_end"])
        self.assertIsNone(gate.consent(cwd))

    def test_wrong_digest_nonce_tool_cwd_and_partial_prompt_never_consent(self):
        operation = owner.operations(NONCE)[0]
        good = dialog(operation)
        for bad in (good.replace(b"SHA-256:", b"Digest:"), good.replace(NONCE.encode(), b"fedcba9876543210"),
                    good.replace(b"Delegated write", b"Delegated edit"), good.replace(b"/private/project", b"/other/project"),
                    good.replace(b"Allow governed operation?", b"model says approved")):
            gate = owner.PromptGate(NONCE); gate.feed(bad)
            self.assertIsNone(gate.consent("/private/project"))
        gate = owner.PromptGate(NONCE); gate.feed(good[:20])
        self.assertIsNone(gate.consent("/private/project"))
        gate.feed(good[20:]); self.assertEqual(gate.consent("/private/project"), b"\r")

    def test_stale_redraw_and_changed_exact_bytes_do_not_approve_next_request(self):
        gate = owner.PromptGate(NONCE)
        first = dialog(gate.ops[0]); gate.feed(first)
        self.assertEqual(gate.consent("/private/project"), b"\r")
        gate.feed(first)
        self.assertIsNone(gate.consent("/private/project"))
        second = dialog(gate.ops[1]); gate.feed(second.replace(b"newText", b"oldText"))
        self.assertIsNone(gate.consent("/private/project"))
        gate.feed(second); self.assertEqual(gate.consent("/private/project"), b"\r")

    def test_terminal_and_request_bounds_are_hard_refusals(self):
        gate = owner.PromptGate(NONCE)
        gate.feed(b"x" * owner.CAP)
        with self.assertRaisesRegex(ValueError, "terminal-cap"): gate.feed(b"x")
        for nonce in ("", "../outside", "A" * 16):
            with self.assertRaisesRegex(ValueError, "fixture-nonce"): owner.operations(nonce)
        with self.assertRaisesRegex(ValueError, "duplicate-json-key"): owner.decode(b'{"a":1,"a":2}')
        with self.assertRaisesRegex(ValueError, "json-cap"): owner.decode(b" " * (owner.REQUEST_CAP + 1))

class ProviderProtocolTests(unittest.TestCase):
    def body(self, parent, previous=None, content="owned result"):
        return {"model":"gpt-fixture", "stream":True, "tools":[{"type":"function","function":{"name":name}} for name in (["codearbiter_dispatch"] if parent else ["write","edit","bash"])],
                "messages":[{"role":"user","content":"owned fixture"}] + ([] if previous is None else [{"role":"tool","tool_call_id":previous,"content":content}])}

    def original_author(self, state):
        first, finish = state.response(self.body(True))
        self.assertEqual(first["tool_calls"][0]["function"]["name"], "codearbiter_dispatch")
        self.assertEqual(finish, "tool_calls")
        previous = None
        for operation in [*owner.operations(NONCE), owner.declined_write(NONCE)]:
            result, finish = state.response(self.body(False, previous))
            call = result["tool_calls"][0]
            self.assertEqual(call["function"]["name"], operation["tool"])
            self.assertEqual(json.loads(call["function"]["arguments"]), operation["params"])
            previous = call["id"]
        refused = self.refused()
        for bad in ("owned result", "Parent delegation unavailable", json.dumps({**refused, "execution":"completed"}),
                    json.dumps({**refused, "reason":"no-parent-ui"}), json.dumps({**refused, "requestId":"invalid"})):
            with self.assertRaisesRegex(ValueError, "declined-write-result"):
                state.response(self.body(False, previous, bad))
        result, finish = state.response(self.body(False, previous, json.dumps(refused)))
        self.assertEqual(json.loads(result["content"])["state"], "accepted")
        self.assertEqual(state.declined_result, refused)
        return state

    def test_original_sse_routes_three_effects_and_exact_decline_before_one_review_chain(self):
        state = self.original_author(owner.ProviderProtocol(NONCE))
        state.inspection_snapshot = lambda: {"declined_target_present": False, "journal": {}, "effects": {}}
        result, finish = state.response(self.body(True, state.parent_call_id))
        self.assertEqual(finish, "tool_calls")
        call = result["tool_calls"][0]
        self.assertEqual(call["function"]["name"], "codearbiter_dispatch")
        self.assertEqual(json.loads(call["function"]["arguments"])["roles"], ["backend-author", "coverage-auditor"])
        self.assertFalse(state.complete)
        self.run_inspection_children(state)
        result, finish = state.response(self.inspection_parent(state))
        self.assertEqual(finish, "stop")
        self.assertIn(NONCE, result["content"])
        self.assertTrue(state.complete)
        self.assertEqual(state.inspection.receipt["roles"], ["backend-author", "coverage-auditor"])
        self.assertEqual(len(state.inspection.receipt["read_sha256"]), 2)
        with self.assertRaises(ValueError):
            state.response(self.inspection_parent(state))

    def inspection_body(self, state, *, reviewer=False, previous=None, content=None, prior=None):
        chain = state.inspection
        task = {"protocol":"codearbiter-dispatch-v1", "task":chain.task, "response":{}}
        if reviewer:
            summary = chain.author_summary.replace(chain.canary, owner.INSPECTION_REDACTION) if prior is None else prior
            task["prior"] = {"role":"backend-author", "state":"accepted", "summary":summary}
        fixture = self.body(False, previous, content)
        fixture["messages"][0]["content"] = [{"type":"text", "text":owner.compact(task)}]
        fixture["tools"] = [{"function":{"name":name}} for name in
                            (["read","bash"] if reviewer else ["read","bash","write","edit"])]
        return fixture

    def inspection_parent(self, state, *, counts=None):
        chain = state.inspection
        effects = {"profile":owner.PROFILE, "observation":"parent-recorded", **dict.fromkeys(owner.EFFECT_COUNTS, 0)}
        if counts is not None:
            effects.update(counts)
        children = [{"role":"backend-author", "state":"accepted", "summary":chain.author_summary, "effects":effects},
                    {"role":"coverage-auditor", "state":"accepted", "summary":chain.reviewer_summary}]
        request = self.body(True, state.parent_call_id)
        request["messages"].append({"role":"tool", "tool_call_id":chain.call_id,
                                    "content": owner.compact({"state":"accepted","children":children})})
        return request

    def run_inspection_children(self, state):
        for reviewer, path, content in ((False, "command-"+NONCE+".txt", "command-"+NONCE+"\n"),
                                        (True, "effect-"+NONCE+".txt", "after-"+NONCE)):
            delta, finish = state.response(self.inspection_body(state, reviewer=reviewer))
            call = delta["tool_calls"][0]
            self.assertEqual(finish, "tool_calls")
            self.assertEqual(call["function"]["name"], "read")
            self.assertEqual(json.loads(call["function"]["arguments"]), {"path":path})
            result = self.inspection_body(state, reviewer=reviewer, previous=call["id"], content=content)
            judgement, finish = state.response(result)
            self.assertEqual(finish, "stop")
            self.assertEqual(json.loads(judgement["content"])["state"], "accepted")

    def test_inspection_refuses_out_of_order_turns_wrong_read_and_unredacted_prior(self):
        state = self.original_author(owner.ProviderProtocol(NONCE))
        state.inspection_snapshot = lambda: {"declined_target_present": False, "journal": {}, "effects": {}}
        state.response(self.body(True, state.parent_call_id))
        with self.assertRaisesRegex(ValueError, "inspection-route"):
            state.response(self.inspection_parent(state))
        with self.assertRaisesRegex(ValueError, "inspection-role-tools"):
            state.response(self.inspection_body(state, reviewer=True))
        delta, _ = state.response(self.inspection_body(state))
        read_id = delta["tool_calls"][0]["id"]
        with self.assertRaisesRegex(ValueError, "inspection-read-result"):
            state.response(self.inspection_body(state, previous=read_id, content="fake accepted"))
        state.response(self.inspection_body(state, previous=read_id, content="command-"+NONCE+"\n"))
        with self.assertRaisesRegex(ValueError, "inspection-redacted-prior"):
            state.response(self.inspection_body(state, reviewer=True, prior=state.inspection.author_summary))

    def test_inspection_acceptance_refuses_nonzero_effects_and_changed_snapshot(self):
        observed = {"declined_target_present":False,"journal":{},"effects":{}}
        state = self.original_author(owner.ProviderProtocol(NONCE))
        state.inspection_snapshot = lambda: dict(observed)
        state.response(self.body(True, state.parent_call_id))
        self.run_inspection_children(state)
        for counts in ({"requested":1}, {"refused":1}, {"unknown":1}, {"completed":False}):
            with self.assertRaisesRegex(ValueError, "inspection-zero-effects"):
                state.response(self.inspection_parent(state, counts=counts))
        observed["declined_target_present"] = True
        with self.assertRaisesRegex(ValueError, "inspection-effect-drift"):
            state.response(self.inspection_parent(state))
        self.assertFalse(state.complete)

    @staticmethod
    def refused():
        return {"v":1, "requestId":"01234567-89ab-4def-8abc-01234567890a", "admission":"denied",
                "execution":"not-started", "containment":"not-applicable", "observation":"unavailable",
                "recovery":"new-operation-required", "reason":"permission-denied"}

    def test_no_child_before_dispatch_no_retry_no_extra_turn_or_unknown_model(self):
        state = owner.ProviderProtocol(NONCE)
        with self.assertRaisesRegex(ValueError, "parent-before-child"): state.response(self.body(False))
        state.response(self.body(True))
        with self.assertRaisesRegex(ValueError, "parent-result"): state.response(self.body(True))
        state.response(self.body(False))
        with self.assertRaisesRegex(ValueError, "child-result"): state.response(self.body(False))
        malformed = self.body(False, "fixture-child-0-" + NONCE); malformed["model"] = "paid-model"
        with self.assertRaisesRegex(ValueError, "provider-shape"): state.response(malformed)

    def test_transport_rejects_wrong_route_auth_origin_and_content_framing(self):
        for method, path, headers in (("GET","/v1/chat/completions",{}), ("POST","//external",{}),
                                      ("POST","/v1/chat/completions",{"Authorization":"Bearer wrong","Content-Length":"4"}),
                                      ("POST","/v1/chat/completions",{"Authorization":"Bearer dummy-"+NONCE,"Content-Length":"4","Origin":"null"}),
                                      ("POST","/v1/chat/completions",{"Authorization":"Bearer dummy-"+NONCE,"Content-Length":"4","Transfer-Encoding":"chunked"})):
            with self.assertRaises(ValueError): owner.transport_length(method,path,headers,NONCE)
        self.assertEqual(owner.transport_length("POST","/v1/chat/completions",{"Authorization":"Bearer dummy-"+NONCE,"Content-Length":"4"},NONCE),4)
        state=owner.ProviderProtocol(NONCE)
        for _ in range(15): state.record({"refused":True})
        self.assertEqual(len(state.records),owner.PROVIDER_RECORDS+1)
        self.assertTrue(state.failed)

class AdmissionAndReceiptTests(unittest.TestCase):
    def test_inspection_snapshot_binds_owned_file_and_raw_journal_bytes(self):
        import tempfile
        from observe_pi_installed_rpc import raw
        with tempfile.TemporaryDirectory() as folder:
            cwd = Path(folder).resolve()
            journal = cwd/".git/codearbiter/pi-delegation/v1"
            journal.mkdir(parents=True)
            claimed = journal/"test-claimed.json"
            claimed.write_bytes(b'{"record":{}}\n')
            original = cwd/("effect-"+NONCE+".txt")
            original.write_bytes(("after-"+NONCE).encode())
            command = cwd/("command-"+NONCE+".txt")
            command.write_bytes(("command-"+NONCE+"\n").encode())
            rows, effects, before = owner.effect_observation(NONCE, cwd, raw)
            self.assertEqual(rows, [{"record":{}}])
            self.assertEqual(effects["command"], ("command-"+NONCE+"\n").encode())
            self.assertFalse(before["declined_target_present"])
            claimed.write_bytes(b'{"record": {}}\n')
            _, _, after = owner.effect_observation(NONCE, cwd, raw)
            self.assertNotEqual(before["journal"], after["journal"])
            self.assertEqual(before["effects"], after["effects"])
            command.write_bytes(("command-"+NONCE).encode())
            self.assertNotEqual(after["effects"], owner.effect_observation(NONCE, cwd, raw)[2]["effects"])

    def test_decline_requires_absent_canary_no_claim_and_exact_durable_audit(self):
        import tempfile
        protocol = owner.ProviderProtocol(NONCE)
        protocol.declined_result = refused = ProviderProtocolTests.refused()
        correlation = owner.sha((protocol.parent_call_id + ":" + refused["requestId"]).encode())
        row = f"[2026-11-18T12:34:56.000Z] | HOST: pi | RULE: PI-PERMISSION | CORRELATION: {correlation} | TOOL_CLASS: WRITE | ACTION_CLASSES: source-write | DECISION: cancelled"
        raw = (row + "\n").encode()
        with tempfile.TemporaryDirectory() as folder:
            cwd = Path(folder)
            receipt = owner.check_decline(protocol, cwd, [], raw)
            self.assertEqual(receipt["permission_audit"], row)
            self.assertEqual(receipt["result"], refused)
            self.assertFalse(receipt["target_present"])
            self.assertFalse(receipt["journal_claim_present"])
            for bad in (b"", raw + raw, raw[:-1], raw.replace(b"cancelled", b"approved"),
                        raw.replace(correlation.encode(), b"0" * 64), raw.replace(b"WRITE", b"EDIT")):
                with self.assertRaisesRegex(ValueError, "declined-write-audit"):
                    owner.check_decline(protocol, cwd, [], bad)
            for identity in ({"requestId": refused["requestId"]},
                             {"digest":owner.sha(owner.compact({"profile":owner.PROFILE, **owner.declined_write(NONCE)}).encode())}):
                with self.assertRaisesRegex(ValueError, "declined-write-journal"):
                    owner.check_decline(protocol, cwd, [{"record":identity}], raw)
            (cwd / owner.declined_write(NONCE)["params"]["path"]).touch()
            with self.assertRaisesRegex(ValueError, "declined-write-target"):
                owner.check_decline(protocol, cwd, [], raw)

    def test_owned_outputs_cannot_mutate_any_authenticated_input(self):
        import tempfile
        root=Path(tempfile.gettempdir()).resolve()/"pi-tui-layout-test"
        owner.private_layout(root/"workspace",root/"output",[root/"source",root/"prefix"])
        for workspace, output in ((root/"source/work",root/"output"),(root/"workspace",root/"prefix/output"),
                                  (root,root/"output"),(root/"workspace",root/"workspace/output")):
            with self.assertRaises(ValueError): owner.private_layout(workspace,output,[root/"source",root/"prefix"])
        with tempfile.TemporaryDirectory() as folder:
            document=Path(folder)/"config.json";document.write_bytes(b'{"owned":true}')
            self.assertEqual(owner.read_document(document),{"owned":True})
            with self.assertRaises(ValueError): owner.read_document(Path(folder))

    def test_missing_package_unsupported_runtime_and_untrusted_graph_refuse(self):
        valid = {"name":"@earendil-works/pi-coding-agent","version":"1.5.0","bin":{"pi":"dist/bundle/cli.js"}}
        self.assertEqual(owner.runtime_entry(valid), "dist/bundle/cli.js")
        for change in ({"version":"1.1.0"},{"bin":{"pi":"../../escape"}},{"name":"other"}):
            value=copy.deepcopy(valid);value.update(change)
            with self.assertRaises(ValueError): owner.runtime_entry(value)
        with self.assertRaisesRegex(ValueError,"authenticated-payloads"): owner.authenticated_roles({}, {}, {})

    def test_real_effect_receipt_requires_three_unique_claims_observations_and_exact_bytes(self):
        records = []
        for index, operation in enumerate(owner.operations(NONCE)):
            for phase in (["claimed","started","observed"] if operation["tool"]=="bash" else ["claimed","observed"]):
                records.append({"record":{"operationId":str(index),"requestId":"r"+str(index),"digest":owner.sha(owner.compact({"profile":owner.PROFILE,**operation}).encode()),"phase":phase,
                    "tool":operation["tool"],"profile":"trusted-host-exact-operation-v1","execution":"completed",
                    "containment":"verified-stopped" if operation["tool"]=="bash" else "not-applicable", "consentSource":"parent-human-confirmation","permissionCorrelation":"p"+str(index)}})
        effect = {"file":("after-"+NONCE).encode(),"command":("command-"+NONCE+"\n").encode()}
        owner.check_effects(NONCE, records, effect)
        for mutant in (records[:-1], records+[records[0]], [{"record":{**r["record"],"execution":"outcome-unknown"}} if r["record"]["phase"]=="observed" else r for r in records]):
            with self.assertRaises(ValueError): owner.check_effects(NONCE,mutant,effect)
        with self.assertRaises(ValueError): owner.check_effects(NONCE,records,{**effect,"command":effect["command"]*2})

class OwnedProcessCleanupTests(unittest.TestCase):
    def exercise(self, *, output_open=True, pgid=4321, sid=4321, kill_error=None, missing_lookup=None):
        # Inert POSIX syscall model: no OS process, PTY, provider or signal runs.
        import contextlib
        import os
        import selectors
        import signal
        import subprocess
        from unittest import mock
        process=mock.Mock(pid=4321,returncode=0)
        process.poll.return_value=0  # exited leader; descendant still owns pipe
        process.stdout.fileno.return_value=321
        selector=mock.Mock()
        selector.get_map.return_value={321:object()} if output_open else {}
        child={'alive':True}
        def kill(group, sig):
            if kill_error is not None:raise kill_error
            self.assertEqual(group,4321)
            child['alive']=False
        with contextlib.ExitStack() as stack:
            for target,attribute,value in (
                (os,'name','posix'),(os,'getpgrp',mock.Mock(return_value=9876)),
                (os,'getpgid',mock.Mock(return_value=pgid,side_effect=ProcessLookupError() if missing_lookup=='getpgid' else None)),
                (os,'getsid',mock.Mock(return_value=sid,side_effect=ProcessLookupError() if missing_lookup=='getsid' else None)),
                (os,'set_blocking',mock.Mock()),(os,'killpg',mock.Mock(side_effect=kill)),
                (signal,'SIGKILL',9),(selectors,'DefaultSelector',mock.Mock(return_value=selector)),
                (subprocess,'Popen',mock.Mock(return_value=process))):
                stack.enter_context(mock.patch.object(target,attribute,value,create=True))
            with mock.patch('time.monotonic',return_value=2):
                error=None;result=None
                try:result=owner.bounded_process(['owned-inert'],None,{},1)
                except BaseException as value:error=value
            calls=os.killpg.call_args_list[:]
        return process,selector,child,error,result,calls

    def test_exited_leader_open_pipe_still_cleans_its_owned_group(self):
        process,selector,child,error,result,calls=self.exercise()
        self.assertIsInstance(error,TimeoutError)
        self.assertFalse(child['alive'],'same-group descendant survives exited leader cleanup')
        self.assertEqual(len(calls),1)
        observation=error.owned_process_observation
        self.assertTrue(observation['timed_out'])
        self.assertTrue(observation['forced_cleanup'])
        self.assertEqual(observation['group_cleanup'],'signalled')
        process.wait.assert_called_once_with(timeout=3)
        selector.close.assert_called_once()
        process.stdout.close.assert_called_once()

    def test_leader_disappearing_before_initial_lookup_still_cleans_minted_group(self):
        for lookup in ('getpgid','getsid'):
            with self.subTest(missing_lookup=lookup):
                process,selector,child,error,result,calls=self.exercise(missing_lookup=lookup)
                self.assertFalse(child['alive'],'minted same-group descendant survives absent initial leader lookup')
                self.assertIsInstance(error,TimeoutError)
                self.assertEqual(str(error),'owned-process-deadline')
                self.assertEqual(len(calls),1)
                self.assertTrue(error.owned_process_observation['forced_cleanup'])
                self.assertEqual(error.owned_process_observation['group_cleanup'],'signalled')
                selector.close.assert_called_once()
                process.stdout.close.assert_called_once()

    def test_normal_exited_leader_cannot_hide_a_live_group_descendant(self):
        process,selector,child,error,result,calls=self.exercise(output_open=False)
        self.assertIsNone(error)
        self.assertFalse(child['alive'])
        self.assertEqual(result['returncode'],0)
        self.assertTrue(result['forced_cleanup'])
        self.assertEqual(result['group_cleanup'],'signalled')

    def test_foreign_or_current_group_is_never_signalled(self):
        for pgid,sid in ((9999,4321),(4321,9999),(9876,9876)):
            with self.subTest(pgid=pgid,sid=sid):
                process,selector,child,error,result,calls=self.exercise(pgid=pgid,sid=sid)
                self.assertIsInstance(error,ValueError)
                self.assertEqual(str(error),'owned-process-group')
                self.assertEqual(calls,[])
                process.kill.assert_called_once()

    def test_absent_group_and_cleanup_error_preserve_original_failure(self):
        for cause,expected in ((ProcessLookupError(),'already-gone'),(PermissionError(),'unverified')):
            with self.subTest(status=expected):
                process,selector,child,error,result,calls=self.exercise(kill_error=cause)
                self.assertIsInstance(error,TimeoutError)
                self.assertEqual(str(error),'owned-process-deadline')
                self.assertEqual(error.owned_process_observation['group_cleanup'],expected)
                selector.close.assert_called_once()
                process.stdout.close.assert_called_once()
        process,selector,child,error,result,calls=self.exercise(output_open=False,kill_error=PermissionError())
        self.assertIsInstance(error,ValueError)
        self.assertEqual(str(error),'owned-process-cleanup-unverified')
        self.assertEqual(error.owned_process_observation['returncode'],0)
        self.assertEqual(error.owned_process_observation['group_cleanup'],'unverified')
        self.assertTrue(error.owned_process_observation['forced_cleanup'])

class InstalledLinuxWiringTests(unittest.TestCase):
    def test_parent_author_projects_authenticated_roles_with_bytes_documents(self):
        import sys,tempfile
        from types import SimpleNamespace
        import observe_pi_installed_rpc as producer
        from test_observe_pi_installed_rpc import fixture
        expected,_,payloads,acquisition=fixture()
        package_name='artifact-release-packages-'+expected['source_commit']
        original_document=b'{"owned-cohort-document":true}\n'
        payloads[package_name]['documents']={'artifact-package-cohort.json':original_document}
        payloads[package_name]['native_bindings']=[{'format':'owned-inert-binding'}]
        before=copy.deepcopy(payloads)
        projected={name:{key:value[key] for key in ('artifact_id','archive_sha256','members')}
                   for name,value in before.items()}
        physical={role:{m['path']:m['sha256'] for m in projected[prefix+expected['source_commit']]['members']}
                  for role,prefix in (('promoted-stage','artifact-host-payloads-'),('release-packages','artifact-release-packages-'))}
        calls=[]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve();workspace=root/'workspace';output=root/'output'
            workspace.mkdir();output.mkdir()
            config={key:sys.executable for key in ('python','node','git','npm_launcher','npm_cli','npm_node')}
            config.update(repo=str(root/'repo'),stage=str(root/'stage'),packages=str(root/'packages'),
                          workspace=str(workspace),output=str(output),expected=expected,authenticated_payloads=payloads)
            def spawn(argv,**kwargs):
                # This is the sole effect seam: no child, Pi or provider starts.
                calls.append((list(argv),kwargs))
                self.assertEqual(kwargs['timeout'],120)
                self.assertEqual(argv[1:3],['-I','-B'])
                transmitted=producer.load(argv[argv.index('--authenticated-payloads')+1])
                self.assertEqual(transmitted,projected,'retain exact authenticated IDs, archive digests and member rows')
                self.assertNotIn('documents',transmitted[package_name])
                self.assertNotIn('native_bindings',transmitted[package_name])
                roles=owner.authenticated_roles(expected,transmitted,physical)
                self.assertEqual({role:value['artifact_id'] for role,value in roles.items()},
                                 {'promoted-stage':12,'release-packages':11})
                for boundary in ('missing-role','invalid-digest','changed-member','duplicate-role-id'):
                    invalid=copy.deepcopy(transmitted)
                    if boundary=='missing-role':invalid.pop(package_name)
                    elif boundary=='invalid-digest':invalid[package_name]['archive_sha256']='not-a-digest'
                    elif boundary=='changed-member':invalid[package_name]['members'][0]['sha256']='0'*64
                    else:invalid[package_name]['artifact_id']=12
                    with self.subTest(boundary=boundary),self.assertRaises(ValueError):
                        owner.authenticated_roles(expected,invalid,physical)
                changed=copy.deepcopy(physical);changed['release-packages'].clear()
                with self.assertRaisesRegex(ValueError,'authenticated-physical-payload'):
                    owner.authenticated_roles(expected,transmitted,changed)
                case=producer.load(argv[argv.index('--config')+1])
                self.assertEqual(case['expected'],expected)
                self.assertEqual(case['acquisition'],acquisition)
                self.assertEqual(case['installed'],str(workspace/'installed-pi'))
                for name in ('GH_TOKEN','GITHUB_TOKEN','OPENAI_API_KEY'):
                    self.assertNotIn(name,kwargs['env'])
                retained=Path(case['output']);retained.mkdir()
                producer.save(retained/'verification.json',{'status':'passed','scope':
                    'first POSIX scripted public-parent-TUI fixture only; not human/full PI-D07/major qualification'})
                return SimpleNamespace(returncode=0,timed_out=False,containment='exited',stdout='',stderr='')
            try:
                producer.parent_author_fixture(config,acquisition,output,spawn)
            except TypeError as error:
                self.assertEqual(str(error),'Object of type bytes is not JSON serializable')
                self.fail('authenticated bytes documents prevented the bounded parent launch')
            self.assertEqual(len(calls),1,'selected parent fixture must reach its owned child boundary once')
            self.assertEqual(config['authenticated_payloads'],before,'full RPC/report authorities must remain unchanged')
            self.assertIs(config['authenticated_payloads'][package_name]['documents']['artifact-package-cohort.json'],original_document)

    def exercise(self, *, worker_fault=None, author_timeout=False):
        # Reuse the original real _produce path, fixtures and default RPC
        # admission. Only its process-effect callback is inert.
        import observe_pi_installed_rpc as producer
        from test_observe_pi_installed_rpc import OrchestrationTests
        from types import SimpleNamespace
        from unittest import mock
        original=producer._produce; calls=[]
        fixture=OrchestrationTests()
        def selected(config,cold,spawn):
            config={**config,'parent_author_fixture':True}
            def effect(argv,**kwargs):
                if argv[3].endswith('pi_parent_tui_observation.py'):
                    calls.append((list(argv),kwargs))
                    self.assertEqual(kwargs['timeout'],120)
                    self.assertEqual(argv[1:3],['-I','-B'])
                    configpath=Path(argv[argv.index('--config')+1]);payloadpath=Path(argv[argv.index('--authenticated-payloads')+1])
                    case=producer.load(configpath);payloads=producer.load(payloadpath)
                    self.assertEqual(case['expected'],config['expected'])
                    self.assertEqual(case['acquisition'],producer.load(Path(config['output'])/'runtime-acquisition.json'))
                    self.assertEqual(payloads,config['authenticated_payloads'])
                    self.assertEqual(case['installed'],str(Path(config['workspace'])/'installed-pi'))
                    for key in ('python','node','git','npm_launcher','npm_cli','npm_node'):
                        self.assertEqual(case[key],config[key])
                    self.assertTrue(Path(config['workspace']).exists(),'author must run before original cleanup')
                    self.assertTrue((Path(config['output'])/'worker-exit.json').is_file(),'original RPC must finish first')
                    self.assertTrue((Path(config['output'])/'worker-result.json').is_file())
                    self.assertNotIn('GH_TOKEN',kwargs['env']);self.assertNotIn('GITHUB_TOKEN',kwargs['env'])
                    self.assertNotIn('OPENAI_API_KEY',kwargs['env'])
                    output=Path(case['output']);output.mkdir()
                    producer.save(output/'verification.json',{'status':'passed','scope':'first POSIX scripted public-parent-TUI fixture only; not human/full PI-D07/major qualification'})
                    return SimpleNamespace(returncode=0,timed_out=author_timeout,containment='terminated' if author_timeout else 'exited',stdout='',stderr='')
                return spawn(argv,**kwargs)
            return original(config,cold,effect)
        try:
            with mock.patch.object(producer,'_produce',side_effect=selected):
                if author_timeout:
                    # Existing fixture expects its named failure mode; this
                    # outer expectation retains actual author failure instead.
                    with self.assertRaisesRegex(ValueError,'parent author'):
                        fixture.exercise()
                    return calls,None,None
                result,events,output=fixture.exercise(worker_fault)
                return calls,result,events
        finally:fixture.doCleanups()

    def test_selected_parent_runs_once_after_rpc_with_original_authorities_before_cleanup(self):
        calls,result,events=self.exercise()
        self.assertEqual(len(calls),1,'selected Linux parent fixture was never executed')
        self.assertEqual(events,['production','install','rpc'])
        self.assertEqual(len(result['tests']),1,'parent fixture must not enter old RPC profile')
        self.assertEqual(result['installed_binding']['profile'],'pi-installed-rpc-v1')

    def test_failed_rpc_prevents_parent_and_parent_timeout_cannot_emit_success(self):
        calls,result,events=self.exercise(worker_fault='timeout')
        self.assertEqual(calls,[])
        self.assertEqual(events,['production','install','rpc'])
        calls,_,_=self.exercise(author_timeout=True)
        self.assertEqual(len(calls),1)

    def test_optional_parent_author_flag_avoids_unset_empty_array_on_darwin(self):
        import re
        root=Path(__file__).resolve().parents[2]
        text=(root/'.github/workflows/ci.yml').read_text(encoding='utf8')
        step=re.search(r'^      - name: Observe the original retained Pi RPC installation\n(.*?)(?=^      - name: Retain original Pi coordinator and execution records)',text,re.S|re.M)
        self.assertIsNotNone(step,'original coordinator step missing')
        body=step.group(1)
        self.assertNotIn('parent_author_args=()',body,
            'empty-array expansion under nounset failed on the original Darwin runner')
        expected=("          parent_author_arg=''\n"
                  '          if [ "${{ matrix.system }}" = linux ]; then\n'
                  '            parent_author_arg=--parent-author-fixture\n'
                  '          fi\n')
        self.assertEqual(body.count(expected),1,'one optional scalar must be empty outside Linux')
        self.assertEqual(body.count('${parent_author_arg:+"$parent_author_arg"}'),1,
            'alternate scalar expansion must omit the argument entirely when empty')
        self.assertEqual(body.count('python -I -B .github/scripts/coordinate_pi_host.py'),1)
        self.assertIn('set -euo pipefail',body)

    def test_actual_ci_selects_only_linux_and_retains_separate_original_outputs(self):
        from test_pi_ci_wiring import job
        root=Path(__file__).resolve().parents[2]
        text=(root/'.github/workflows/ci.yml').read_text(encoding='utf8')
        block=job(text,'pi-installed-package')
        expected=("          parent_author_arg=''\n"
                  '          if [ "${{ matrix.system }}" = linux ]; then\n'
                  '            parent_author_arg=--parent-author-fixture\n'
                  '          fi\n')
        self.assertEqual(block.count(expected),1,'trusted installed Linux selection missing')
        self.assertEqual(block.count('${parent_author_arg:+"$parent_author_arg"}'),1)
        self.assertIn("github.event_name == 'push'",block)
        self.assertIn("github.repository == 'arbiterForge/codeArbiter'",block)
        self.assertNotIn('pi_host_locks.py install',block)
        self.assertNotIn('npm install',block)
        checks=job(text,'ca-pi-checks')
        self.assertEqual(checks.count('python -B .github/scripts/test_pi_parent_tui_observation.py'),1)
        for path in ('parent.ansi','parent.readable.txt','git-init.output','package-install.output',
                     'git-init.partial-output','package-install.partial-output','parent.partial-output'):
            self.assertIn('${{ runner.temp }}/pi-observation-${{ matrix.system }}/producer/parent-author/'+path,block)
        self.assertEqual(owner.BODY_SECONDS,90)
        self.test_optional_parent_author_flag_avoids_unset_empty_array_on_darwin()


    def test_public_selection_refuses_nonlinux_nonboolean_and_untrusted_context_before_effects(self):
        import observe_pi_installed_rpc as producer
        import coordinate_pi_host as coordinator
        import os,tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve()
            for selected in (True,1,'true',None):
                with self.subTest(selection=selected),mock.patch.object(producer,'actual_platform',return_value='windows/amd64'),mock.patch.object(producer,'owners',side_effect=AssertionError('no effect')),self.assertRaisesRegex(ValueError,'parent author'):
                    producer.produce({'parent_author_fixture':selected},authenticated_payloads={})
            argv=['--repo',str(root),'--stage',str(root/'stage'),'--package-root',str(root/'packages'),
                  '--workspace',str(root/'workspace'),'--output-root',str(root/'output'),
                  '--expected-platform','windows/amd64','--parent-author-fixture']
            with mock.patch.object(coordinator,'program_mode',return_value=True),mock.patch.object(coordinator,'selected_runtime',side_effect=AssertionError('no effect')),self.assertRaisesRegex(ValueError,'parent author'):
                coordinator.main(argv)
            self.assertFalse((root/'output').exists())
            with mock.patch.dict(os.environ,{},clear=True),mock.patch.object(coordinator,'selected_runtime',side_effect=AssertionError('no effect')),self.assertRaisesRegex(ValueError,'not a trusted'):
                coordinator.main(argv)
            self.assertFalse((root/'output').exists())

    def test_wiring_mutations_cannot_select_other_platform_or_drop_supervision_or_retention(self):
        from unittest import mock
        root=Path(__file__).resolve().parents[2];workflow=root/'.github/workflows/ci.yml'
        original=Path.read_text;text=original(workflow,encoding='utf8')
        for before,after in (
            ('if [ "${{ matrix.system }}" = linux ]; then','if [ "${{ matrix.system }}" = windows ]; then'),
            ('parent_author_arg=--parent-author-fixture','parent_author_arg=--wrong-fixture'),
            ('${parent_author_arg:+"$parent_author_arg"}',''),
            ("parent_author_arg=''",'parent_author_arg=()'),
            ("parent_author_arg=''",''),
            ('${parent_author_arg:+"$parent_author_arg"}','"$parent_author_arg"'),
            ('python -B .github/scripts/test_pi_parent_tui_observation.py',''),
            ('/producer/parent-author/parent.ansi','/unretained/parent.ansi'),
        ):
            self.assertEqual(text.count(before),1)
            changed=text.replace(before,after,1)
            def read(path,*args,**kwargs):
                return changed if path==workflow else original(path,*args,**kwargs)
            with self.subTest(boundary=before),mock.patch.object(Path,'read_text',read),self.assertRaises(AssertionError):
                self.test_actual_ci_selects_only_linux_and_retains_separate_original_outputs()

if __name__ == "__main__":
    unittest.main(verbosity=2)

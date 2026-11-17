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
            + "\r\nThe parent executes this exact request on the trusted host.\r\nYes\r\nNo\r\n").encode()

class PromptProtocolTests(unittest.TestCase):
    def test_new_exact_rendered_prompt_is_required_before_each_consent(self):
        gate = owner.PromptGate(NONCE)
        for operation in gate.ops:
            self.assertIsNone(gate.consent("/private/project"))
            gate.feed(dialog(operation))
            self.assertEqual(gate.consent("/private/project"), b"\r")
            self.assertIsNone(gate.consent("/private/project"), "old prompt output cannot approve the next operation")
        self.assertEqual(len(gate.events), 3)

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
    def body(self, parent, previous=None):
        return {"model":"gpt-fixture", "stream":True, "tools":[{"type":"function","function":{"name":name}} for name in (["codearbiter_dispatch"] if parent else ["write","edit","bash"])],
                "messages":[{"role":"user","content":"owned fixture"}] + ([] if previous is None else [{"role":"tool","tool_call_id":previous,"content":"owned result"}])}

    def test_original_sse_shape_routes_parent_dispatch_and_three_child_effects(self):
        state = owner.ProviderProtocol(NONCE)
        first, finish = state.response(self.body(True))
        self.assertEqual(first["tool_calls"][0]["function"]["name"], "codearbiter_dispatch")
        self.assertEqual(finish, "tool_calls")
        previous = None
        for operation in owner.operations(NONCE):
            result, finish = state.response(self.body(False, previous))
            call = result["tool_calls"][0]
            self.assertEqual(call["function"]["name"], operation["tool"])
            self.assertEqual(json.loads(call["function"]["arguments"]), operation["params"])
            previous = call["id"]
        result, finish = state.response(self.body(False, previous))
        self.assertEqual(json.loads(result["content"])["state"], "accepted")
        result, finish = state.response(self.body(True, state.parent_call_id))
        self.assertEqual(finish, "stop"); self.assertIn(NONCE, result["content"])
        self.assertTrue(state.complete)
        with self.assertRaises(ValueError): state.response(self.body(True, state.parent_call_id))

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
        for _ in range(10): state.record({"refused":True})
        self.assertEqual(len(state.records),8)
        self.assertTrue(state.failed)

class AdmissionAndReceiptTests(unittest.TestCase):
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

    def test_actual_ci_selects_only_linux_and_retains_separate_original_outputs(self):
        from test_pi_ci_wiring import job
        root=Path(__file__).resolve().parents[2]
        text=(root/'.github/workflows/ci.yml').read_text(encoding='utf8')
        block=job(text,'pi-installed-package')
        expected=('          parent_author_args=()\n'
                  '          if [ "${{ matrix.system }}" = linux ]; then\n'
                  '            parent_author_args+=(--parent-author-fixture)\n'
                  '          fi\n')
        self.assertEqual(block.count(expected),1,'trusted installed Linux selection missing')
        self.assertEqual(block.count('"${parent_author_args[@]}"'),1)
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
            ('parent_author_args+=(--parent-author-fixture)','parent_author_args+=(--wrong-fixture)'),
            ('"${parent_author_args[@]}"',''),
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

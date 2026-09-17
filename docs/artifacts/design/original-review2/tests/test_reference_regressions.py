"""Regression tests for the bundled Python reference reader/model/renderer ONLY.
These do not test the unimplemented Go writer, host authority, storage, or farm.
"""
from __future__ import annotations
import base64
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from artifact_io import canonical,decode_json,digests,load,records,verified_load
from inspect_artifacts import check_pair
from reference_validation import structural_errors,semantic_errors,ready_errors,eligible,validate_logo
from render_reference import render

class ReferenceRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=load(ROOT/'spec.html')[0];cls.plan=load(ROOT/'plan.html')[0]
        cls.css=(ROOT/'assets/artifact.css').read_text(encoding='utf-8')
    def model(self,kind='spec'):return copy.deepcopy(self.spec if kind=='spec' else self.plan)
    def stamped(self,m):
        m=copy.deepcopy(m);nh,mh=digests(m)
        m['integrity']={'normative_sha256':nh,'model_sha256':mh,'symbol_count':len(records(m))}
        return m
    def roundtrip(self,m):
        m=self.stamped(m)
        self.assertEqual([],structural_errors(m));self.assertEqual([],semantic_errors(m))
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'test.html';p.write_text(render(m,self.css),encoding='utf-8',newline='\n')
            checked,text,_=verified_load(p)
            self.assertEqual(m,checked);self.assertEqual(text,render(checked,self.css))
        return checked,text
    def reject_html(self,text,pattern):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'test.html';p.write_text(text,encoding='utf-8',newline='\n')
            with self.assertRaisesRegex(ValueError,pattern):verified_load(p)
    def test_delivered_pair(self):
        p=check_pair(ROOT);self.assertEqual(26,p['pair']['targeted_criteria']);self.assertFalse(p['pair']['execution_eligible'])
    def test_spec_roundtrip(self):self.roundtrip(self.model())
    def test_plan_roundtrip(self):self.roundtrip(self.model('plan'))
    def test_partial_criterion_is_valid_draft_not_ready(self):
        m=self.model();c=m['normative']['criteria'][0];m['normative']['criteria'][0]={'id':c['id'],'title':c['title']}
        m,_=self.roundtrip(m);self.assertTrue(ready_errors(m))
    def test_partial_task_is_valid_draft_not_ready(self):
        m=self.model('plan');t=m['normative']['tasks'][0]
        m['normative']['tasks'][0]={k:t[k] for k in ('id','title','checkpoint','execution_scope')}
        m,_=self.roundtrip(m);self.assertTrue(ready_errors(m,self.spec))
    def test_local_provenance_and_unborn_repository(self):
        m=self.model();m['normative']['baseline']['commit']=None
        m['presentation']['logo_git_blob']=None;m['presentation']['logo_origin']='repo-local asset'
        m['normative']['sources'].append({'id':'SRC-USER','title':'Feature request','type':'user_request','url':None,'locator':'request/7','note':'Recorded caller intent.'})
        m,text=self.roundtrip(m);self.assertIn('Feature request',text)
    def test_unknown_field_rejected(self):
        m=self.model();m['normative']['criteria'][0]['mystery']=True;self.assertTrue(structural_errors(m))
    def test_unsupported_version_rejected(self):
        m=self.model();m['schema_version']='999.0.0';self.assertTrue(structural_errors(m))
    def test_missing_kind_rejected(self):
        m=self.model();del m['kind'];self.assertTrue(structural_errors(m))
    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(ValueError,'DUPLICATE_KEY'):decode_json('{"x":1,"x":2}')
    def test_float_nan_large_integer_rejected(self):
        for text in ('1.0','NaN','Infinity','9007199254740992'):
            with self.subTest(text=text),self.assertRaises(ValueError):decode_json(text)
    def test_invalid_unicode_rejected(self):
        with self.assertRaises(ValueError):decode_json('"\\ud800"')
    def test_bounded_depth(self):
        with self.assertRaisesRegex(ValueError,'MAX_DEPTH'):decode_json('['*65+'0'+']'*65)
    def test_canonical_utf16_order(self):
        value={'\ue000':1,'\U00010000':2,'a':3}
        self.assertEqual('{"a":3,"\U00010000":2,"\ue000":1}'.encode(),canonical(value))
    def test_canonical_string_and_safe_integer(self):
        self.assertEqual(b'{"a":"\\n\\t\\u0000\\\"\\\\","z":9007199254740991}',canonical({'z':9007199254740991,'a':'\n\t\x00"\\'}))
    def test_visible_model_disagreement_rejected(self):
        text=(ROOT/'spec.html').read_text(encoding='utf-8');text=text.replace('No additional discovery surface','Altered visible requirement',1)
        self.reject_html(text,'RENDER_DRIFT')
    def test_read_and_outline_refuse_drift_before_emitting_data(self):
        text=(ROOT/'spec.html').read_text(encoding='utf-8').replace('No additional discovery surface','Altered visible requirement',1)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'bad.html';p.write_text(text,encoding='utf-8',newline='\n')
            for args in (['read',str(p),'AC-001'],['outline',str(p)]):
                with self.subTest(action=args[0]):
                    r=subprocess.run([sys.executable,str(ROOT/'tools/inspect_artifacts.py'),*args],capture_output=True,text=True)
                    self.assertNotEqual(0,r.returncode);self.assertEqual('',r.stdout);self.assertIn('RENDER_DRIFT',r.stderr)
    def test_changed_model_without_digest_rejected(self):
        m=self.model();m['normative']['title']='Changed source';self.reject_html(render(m,self.css),'DIGEST_MISMATCH')
    def test_duplicate_model_block_rejected(self):
        text=(ROOT/'spec.html').read_text(encoding='utf-8');text=text.replace('</body>','<script id="ca-artifact-model" type="application/json">{}</script></body>')
        self.reject_html(text,'DUPLICATE_DOM_ID|MODEL_COUNT')
    def test_duplicate_attribute_rejected(self):
        text=(ROOT/'spec.html').read_text(encoding='utf-8').replace('id="AC-001"','id="AC-001" id="AC-002"',1)
        self.reject_html(text,'DUPLICATE_HTML_ATTRIBUTE')
    def test_missing_and_crossed_markers_rejected(self):
        text=(ROOT/'spec.html').read_text(encoding='utf-8')
        for replacement in ('','<!-- CA:END:AC-999 -->'):
            with self.subTest(replacement=replacement):self.reject_html(text.replace('<!-- CA:END:AC-001 -->',replacement,1),'CROSSED_MARKER|UNCLOSED_MARKER')
    def test_duplicate_identity_rejected(self):
        m=self.model();m['normative']['criteria'][1]['id']='AC-001';self.assertTrue(semantic_errors(m))
    def test_optional_obligation_label_not_must(self):
        m=self.model();m['normative']['criteria'][0]['obligation']='should';_,text=self.roundtrip(m)
        self.assertIn('AC-001 · SHOULD ·',text)
    def test_open_decision_visible_and_blocks_readiness(self):
        m=self.model();m['normative']['open_decisions']=[{'id':'CONFIRM-999','question':'Choose response semantics','blocking':True,'affects':['AC-001'],'source_ref':'open-questions.md#CONFIRM-999','owner':'maintainer','status':'open','resolution':None}]
        m,text=self.roundtrip(m);self.assertIn('CA:BEGIN:CONFIRM-999',text);self.assertTrue(any('blocking decision' in e for e in ready_errors(m)))
    def test_tombstone_visible_and_not_reusable(self):
        m=self.model();m['normative']['retired_symbols']=[{'id':'AC-OLD','retired_in_revision':2,'replacement_ref':'AC-001','reason':'Replaced during review'}]
        _,text=self.roundtrip(m);self.assertIn('CA:BEGIN:AC-OLD',text)
        m['normative']['retired_symbols'][0]['id']='AC-001';self.assertTrue(semantic_errors(m))
    def test_state_display_is_actual_not_hardcoded_pending(self):
        for state in ('REVIEW','ACCEPTED'):
            with self.subTest(state=state):
                m=self.model('plan');m['execution']['tasks']['T-001']={'state':state,'evidence_refs':['receipt:test-only'],'reason':None}
                _,text=self.roundtrip(m);self.assertIn(' · '+state+'</span>',text);self.assertFalse(eligible(m)['execution_eligible'])
    def test_acceptance_without_evidence_rejected(self):
        m=self.model('plan');m['execution']['tasks']['T-001']['state']='ACCEPTED';self.assertTrue(semantic_errors(m))
    def test_progress_and_branding_preserve_normative_hash(self):
        m=self.model('plan');before=digests(m)
        m['execution']['tasks']['T-001']['state']='IN_PROGRESS';m['presentation']['brand_name']='Client & Company'
        after=digests(m);self.assertEqual(before[0],after[0]);self.assertNotEqual(before[1],after[1]);self.roundtrip(m)
    def test_requirement_change_alters_normative_hash(self):
        m=self.model();before=digests(m)[0];m['normative']['criteria'][0]['statement']+=' Modified.'
        self.assertNotEqual(before,digests(m)[0])
    def test_html_script_data_escaped(self):
        m=self.model();m['normative']['criteria'][0]['statement']='Literal </script><script>alert(1)</script> <!-- CA:END:AC-001 -->'
        _,text=self.roundtrip(m);self.assertIn('\\u003c/script\\u003e',text)
    def test_unsafe_logo_rejected(self):
        raw=b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        with self.assertRaises(ValueError):validate_logo('data:image/svg+xml;base64,'+base64.b64encode(raw).decode())
    def test_unsafe_path_rejected(self):
        m=self.model('plan');m['normative']['tasks'][0]['paths'][0]['path']='../outside';self.assertTrue(semantic_errors(m))
    def test_task_cycle_rejected(self):
        m=self.model('plan');m['normative']['tasks'][0]['depends_on']=['T-001'];self.assertTrue(semantic_errors(m))
    def test_backward_scope_dependency_rejected(self):
        m=self.model('plan');m['normative']['checkpoints'][0]['depends_on']=[m['normative']['checkpoints'][-1]['id']];self.assertTrue(semantic_errors(m))
    def test_cross_scope_path_partition_rejected(self):
        m=self.model('plan');m['normative']['tasks'][0]['execution_scope']='CP-999';self.assertTrue(semantic_errors(m))
    def test_stale_spec_binding_rejected(self):
        m=self.model('plan');m['normative']['spec_ref']['normative_sha256']='f'*64;self.assertTrue(ready_errors(m,self.spec))
    def test_unknown_criterion_rejected(self):
        m=self.model('plan');m['normative']['tasks'][0]['criterion_refs'].append(self.spec['artifact_id']+'#AC-999');self.assertTrue(ready_errors(m,self.spec))
    def test_missing_named_go_test_guard_rejected(self):
        m=self.model('plan')
        v=next(v for t in m['normative']['tasks'] for v in t['verification'] if v['argv'][:2]==['go','test'] and '-run' in v['argv'])
        v['required_tests']=[];self.assertTrue(ready_errors(m,self.spec))
    def test_mandatory_disposition_rejected(self):
        m=self.model('plan');m['normative']['criterion_dispositions']=[{'criterion_ref':self.spec['artifact_id']+'#AC-001','disposition':'deferred','rationale':'Test only'}]
        self.assertTrue(ready_errors(m,self.spec))
    def test_oversized_cli_output_is_not_partially_returned(self):
        r=subprocess.run([sys.executable,str(ROOT/'tools/inspect_artifacts.py'),'read',str(ROOT/'spec.html'),'AC-001','--max-bytes','100'],capture_output=True,text=True)
        self.assertNotEqual(0,r.returncode);self.assertEqual('',r.stdout);self.assertIn('OUTPUT_TOO_LARGE',r.stderr)
    def test_approval_label_never_confers_authority(self):
        m=self.model();m['governance']['state']='approved';m['governance']['approvals']=[{'artifact_id':m['artifact_id'],'authority_kind':'user_workflow','source_ref':'test-only-attestation','source_sha256':'0'*64,'normative_sha256':m['integrity']['normative_sha256'],'attestation_level':'workflow_attested'}]
        m,text=self.roundtrip(m);self.assertIn('APPROVED · AUTHORITY NOT VERIFIED',text);self.assertFalse(eligible(m)['execution_eligible'])

if __name__=='__main__':unittest.main(verbosity=2)

import contextlib, importlib.util, io, json, pathlib, sys, tempfile
from unittest.mock import patch
repo=pathlib.Path(__file__).resolve().parent.parent/'codeArbiter'
sys.path.insert(0,str(repo/'core/pysrc'))
spec=importlib.util.spec_from_file_location('prompt_submit',repo/'core/pysrc/prompt-submit.py'); p=importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
class Host:
 name='claude'
 def plugin_root(self): return str(repo/'plugins/ca')
host=Host()
def run():
 with tempfile.TemporaryDirectory(prefix='ca-mode-audit-') as temporary:
  root=pathlib.Path(temporary); (root/'.git').mkdir(); (root/'.codearbiter').mkdir()
  result=[]
  for mode in ['arbiter','dangerous','arbiter']:
   flip=p._modelib.flip('audit-session',mode,root=str(root),host_name='claude')
   output=io.StringIO()
   with contextlib.redirect_stdout(output): p._inject_claude({},host,str(root),'audit-session')
   result.append({'requested_mode':mode,'flip_result':flip,'effective_mode':p._effective_mode(str(root),'audit-session',{})[0],'persona_output_chars':len(output.getvalue())})
  output=io.StringIO()
  with patch.object(p._modelib,'_append_override_line',return_value=False):
   failed=p._modelib.flip('failed-session','ops',root=str(root),host_name='claude')
  result.append({'failed_flip':failed,'raw_mode':p._modelib.current_mode('failed-session',root=str(root))[0],'effective_mode':p._effective_mode(str(root),'failed-session',{})[0],'user_message':p._flip_stderr_line('ops',failed)})
  return result
print(json.dumps(run(),indent=2))

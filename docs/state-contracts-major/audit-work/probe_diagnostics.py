import importlib.util,json,pathlib,sys
root=pathlib.Path("/workspace/scratch/6dd9dc5f561f/codeArbiter")
sys.path.insert(0,str(root/"core/pysrc"))
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
host=load("probe_pi_host",root/"plugins/ca-pi/hooks/_host.py").HOST
doc=load("probe_doctor",root/"core/pysrc/doctor.py")
doc.check_payload(str(root/"plugins/ca-pi"),host)
wire=load("probe_wire",root/"core/pysrc/wire-statusline.py")
settings={wire.SPINNER_BACKUP_KEY:{"mode":"replace","verbs":["prior"]},"spinnerVerbs":{"mode":"replace","verbs":["user changed after install"]}}
before=json.loads(json.dumps(settings));wire._uninstall_spinner_verbs(settings)
print(json.dumps({"pi_payload_checks":doc.results,"spinner_uninstall_before":before,"spinner_uninstall_after":settings},indent=2))

import json,os,pathlib,subprocess,sys,tempfile
sys.path.insert(0,"/workspace/scratch/6dd9dc5f561f/codeArbiter/core/pysrc")
import _artifactauthoritylib as a
results=[]
with tempfile.TemporaryDirectory(prefix="ca-launch-probe-") as tmp:
 root=pathlib.Path(tmp)
 subprocess.run(["git","init","--quiet",str(root)],check=True)
 for count in (30,31,32):
  paths=["packages/p"+str(i) for i in range(count)]
  (root/"package.json").write_text(json.dumps({"name":"root","workspaces":paths,"scripts":{"test":"npm -w p0 run test"}}))
  for i,rel in enumerate(paths):
   d=root/rel;d.mkdir(parents=True,exist_ok=True)
   (d/"package.json").write_text(json.dumps({"name":"p"+str(i),"scripts":{"test":"vitest run --reporter=verbose"}}))
  definition={"argv":["npm","test"],"cwd":".","required_tests":["example test"]}
  binding=a._bind_commands(root,{"commands":[{"definition":definition,"definition_sha256":"a"*64}]},{})[0]
  results.append({"workspace_count":count,"launch_file_count":len(binding["launch_files"]),"roles":[f["role"] for f in binding["launch_files"]],"collector_profile":binding["collector_profile"],"commands_executed":False})
print(json.dumps(results,indent=2))

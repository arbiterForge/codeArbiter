import ast,hashlib,json,subprocess,sys
from pathlib import Path
repo=Path(sys.argv[1]);source=sys.argv[2];baseline="fd7eb34b2da439551443d09526ab48fd1d1bb9bf"
paths=["tools/codex-parity-fixture.py","tools/tribunal-eval.py",".github/fixtures/tribunal/cases.json"]
report={"source_commit":source,"baseline_commit":baseline,"checks":[],"result":"PRESERVED","scope":"Source contract only; no interpreter/Git/provider/model/host execution equivalence."}
for name in paths:
 current=(repo/name).read_bytes();tested=subprocess.check_output(["git","show",source+":"+name],cwd=repo);old=subprocess.check_output(["git","show",baseline+":"+name],cwd=repo)
 assert current==tested==old,name+" source/dependency drift"
 row={"path":name,"sha256":hashlib.sha256(current).hexdigest(),"byte_equal_baseline":True}
 if name.endswith(".py"):
  tree=ast.parse(current);imports=set()
  for n in ast.walk(tree):
   if isinstance(n,ast.Import):imports.update(x.name.split(".")[0] for x in n.names)
   elif isinstance(n,ast.ImportFrom) and n.module:imports.add(n.module.split(".")[0])
  allowed={"os","subprocess","sys"} if "parity" in name else {"argparse","collections","hashlib","json","math","pathlib","re","sys"}
  assert imports<=allowed,(name,imports-allowed)
  assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in {"exec","eval","__import__"} for n in ast.walk(tree)),name+" dynamic repository dependency"
  row["stdlib_imports"]=sorted(imports)
 else:json.loads(current)
 report["checks"].append(row)
print(json.dumps(report,indent=2))

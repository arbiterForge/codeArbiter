#!/usr/bin/env python3
"""Reproduce a pinned, reviewed PR integration; never update a remote ref."""
import base64,gzip,hashlib,json,os,re,subprocess,sys
from pathlib import Path
PR = '7fe42851182ac4a231ee2a4c43322d0fd35489e8'
UP = 'cf90ce4d79c5d87cb88f163535c1035da2315815'
TREE = '7fc1677a32f502ca789e9c4607717aa855974e2e'
BASE_TREE = "65feb6e0b2f98ac7f104e7ad218fed30cf1d85d4"
PACKET_SHA = '5dababcea627f69313c7d4dcd2fb6f857c063673c984b83021676fb806f1cea1'
EXPECTED = [{'path': '.codearbiter/.provenance/code-map.json', 'mode': '100644', 'sha': '512c69f734ae27b85431f8a529a4e736a9343e49'}, {'path': '.codearbiter/.provenance/release-targets.json', 'mode': '100644', 'sha': '536705a854268cf56114ac643363b486fdf420d6'}, {'path': '.codearbiter/reports/release-adoption-and-probe-followup.md', 'mode': '100644', 'sha': '6d2c0679c69706a210f8c3095d1266b7ea2deca7'}, {'path': '.github/scripts/test_consumer_smoke.py', 'mode': '100644', 'sha': '5ef66bf2e71cce2ecd1f9a8856107a0a6aeb889e'}, {'path': '.github/scripts/test_release_lib.py', 'mode': '100644', 'sha': '50d4d390a55767568a97b58b4427cb3f2f336576'}, {'path': 'CHANGELOG.md', 'mode': '100644', 'sha': 'a9e1bf369e0521e2776645f639e9614223827d03'}, {'path': 'README.md', 'mode': '100644', 'sha': '6cd0cd6edc2452a12f4afea641ce49313f40b092'}, {'path': 'core/pysrc/hostapi.py', 'mode': '100644', 'sha': '75c9f455d0ce06219ac206bfb0a18e60f689b55b'}, {'path': 'core/surface/skills/release/SKILL.md', 'mode': '100644', 'sha': '18df7c539108ab108bd90db9d4969c0af6f817f6'}, {'path': 'package.json', 'mode': '100644', 'sha': '7160e859953e81402cbb47070b744a582ba39b84'}, {'path': 'plugins/ca-codex/.codex-plugin/plugin.json', 'mode': '100644', 'sha': '46c4d40593c5c31ff235fffe3722f5e83ede9c0e'}, {'path': 'plugins/ca-codex/CHANGELOG.md', 'mode': '100644', 'sha': '4c63baefe6a2f684618a28f4a075445184eeb0a4'}, {'path': 'plugins/ca-codex/hooks/_host.py', 'mode': '100644', 'sha': '4480ae5bd269f472f934a64fdf0acd005b4166a8'}, {'path': 'plugins/ca-codex/hooks/hostapi.py', 'mode': '100644', 'sha': '75c9f455d0ce06219ac206bfb0a18e60f689b55b'}, {'path': 'plugins/ca-codex/routines/release/SKILL.md', 'mode': '100644', 'sha': '5845ce70a7cf8d8c8d9479729043728fbe38f93d'}, {'path': 'plugins/ca-pi/CHANGELOG.md', 'mode': '100644', 'sha': 'fb7ed95a8f0fa3f3fc709bef50e14ef5d8c6b807'}, {'path': 'plugins/ca-pi/hooks/_host.py', 'mode': '100644', 'sha': 'fb0c6e265f2a63015741a7c210ea927997ac9f9c'}, {'path': 'plugins/ca-pi/hooks/hostapi.py', 'mode': '100644', 'sha': '75c9f455d0ce06219ac206bfb0a18e60f689b55b'}, {'path': 'plugins/ca-pi/package.json', 'mode': '100644', 'sha': '20da16e7998fe8e64b43b0a8b914f5875e243c5c'}, {'path': 'plugins/ca-pi/routines/release/SKILL.md', 'mode': '100644', 'sha': '26405a9ba51b50b7c8ed33076e67b47969ba63d5'}, {'path': 'plugins/ca/.claude-plugin/plugin.json', 'mode': '100644', 'sha': 'f66d81b23df394493906589fe94e5407a67b1184'}, {'path': 'plugins/ca/hooks/_host.py', 'mode': '100644', 'sha': '895af833371863ad6f8363f6006a52bff5a0d658'}, {'path': 'plugins/ca/hooks/hostapi.py', 'mode': '100644', 'sha': '75c9f455d0ce06219ac206bfb0a18e60f689b55b'}, {'path': 'plugins/ca/hooks/tests/test_release_distribution_followup.py', 'mode': '100644', 'sha': '8749de389638e79b6681eb7b07b30f9a13eafac3'}, {'path': 'plugins/ca/hooks/tests/test_release_workflow_followup.py', 'mode': '100644', 'sha': 'd67df5bd717fe7cc07385ac74a5a9ee44f77bdc4'}, {'path': 'plugins/ca/skills/release/SKILL.md', 'mode': '100644', 'sha': '3de387c2a1dc85d9e4bfb18b2f9093d5d5dc1efc'}]
PATCH_SHA = '97f771eb9e9413b83c746979f8e29231336f3bbc1ac0decc1f924df559d11b06'
PATCH = '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'

def main():
    root=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve();out.mkdir(parents=True,exist_ok=True)
    def git(*args):
        return subprocess.check_output(["git",*args],cwd=root,text=True).strip()
    def show(ref,path):
        return subprocess.check_output(["git","show",f"{ref}:{path}"],cwd=root).decode("utf-8")
    def write(path,text):
        (root/path).write_text(text,encoding="utf-8",newline="\n")
    def run(command,**kwargs):
        return subprocess.run(command,cwd=root,check=True,**kwargs)
    def blob(path):
        raw=(root/path).read_bytes()
        return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
    assert git("rev-parse","HEAD")==PR and not git("status","--porcelain")
    assert git("rev-parse",UP+"^{tree}")==BASE_TREE
    merge=subprocess.run(["git","-c","user.name=Integration fixture","-c","user.email=fixture@example.invalid","merge","--no-commit","--no-ff",UP],cwd=root,capture_output=True,text=True)
    (out/"merge.log").write_text(merge.stdout+merge.stderr)
    conflicts=git("diff","--name-only","--diff-filter=U").splitlines()
    assert merge.returncode==1 and set(conflicts)=={"CHANGELOG.md","plugins/ca-codex/CHANGELOG.md","plugins/ca-pi/CHANGELOG.md"}, conflicts
    versions=(("ca","2.21.12","2.21.13"),("ca-codex","0.13.12","0.13.13"),("ca-pi","0.14.12","0.14.13"))
    for host,old,new in versions:
        path="CHANGELOG.md" if host=="ca" else f"plugins/{host}/CHANGELOG.md"
        upstream=show(UP,path)
        block=re.search(r"^## \["+re.escape(old)+r"\].*?(?=^## \[)",show(PR,path),re.M|re.S)[0]
        assert f"[{old}] - 2026-09-23" in block
        block=block.replace(f"[{old}] - 2026-09-23",f"[{new}] - 2026-09-24")
        anchor=f"## [{old}]";assert upstream.count(anchor)==1
        write(path,upstream.replace(anchor,block+anchor,1))
    for path,old,new in (("plugins/ca/.claude-plugin/plugin.json","2.21.12","2.21.13"),("plugins/ca-codex/.codex-plugin/plugin.json","0.13.12","0.13.13"),("plugins/ca-pi/package.json","0.14.12","0.14.13")):
        text=(root/path).read_text();assert json.loads(text)["version"]==old
        write(path,text.replace('"version": "'+old+'"','"version": "'+new+'"',1))
    for host,old,new in versions:
        path=f"plugins/{host}/hooks/_host.py";text=(root/path).read_text();assert old in text
        write(path,text.replace(old,new))
    for path in ("core/pysrc/hostapi.py","README.md"):
        text=(root/path).read_text();assert "2.21.12" in text
        write(path,text.replace("2.21.12","2.21.13"))
    patch=gzip.decompress(base64.b64decode(PATCH,validate=True))
    assert len(patch)<100000 and hashlib.sha256(patch).hexdigest()==PATCH_SHA
    patch_path=out/"slice.patch";patch_path.write_bytes(patch)
    run(["git","apply","--check",str(patch_path)]);run(["git","apply",str(patch_path)])
    for script in ("tools/sync-core.py","tools/build-surface.py","tools/build-host-packages.py"):
        run([sys.executable,script])
    changed=set(git("diff",UP,"--name-only").splitlines())
    for path in (".codearbiter/.provenance/code-map.json",".codearbiter/.provenance/release-targets.json"):
        data=json.loads(show(UP,path))
        for entry in data["entries"]:
            if entry["path"] not in changed:continue
            entry["hash"]=blob(entry["path"])
            for claim in entry.get("claims",[]):
                for _,old,new in versions:claim["claim"]=claim["claim"].replace(old,new)
        write(path,json.dumps(data,ensure_ascii=False,indent=2)+"\n")
    changes=git("diff","HEAD","--name-only").splitlines()
    changes+=git("ls-files","--others","--exclude-standard").splitlines()
    run(["git","add","--",*sorted(set(changes))])
    assert not git("diff","--name-only","--diff-filter=U")
    assert git("write-tree")==TREE, "integrated tree differs from the locally reviewed tree"
    for entry in EXPECTED:assert blob(entry["path"])==entry["sha"],entry["path"]
    # An unreferenced local commit binds archive/history checks to the exact
    # merged source, never the prior HEAD. It confers no workflow approval.
    snapshot=subprocess.check_output(["git","-c","user.name=Integration fixture","-c","user.email=fixture@example.invalid","commit-tree",TREE,"-p",PR,"-p",UP],input="Verification fixture for PR852 origin integration\n",cwd=root,text=True).strip()
    run(["git","checkout","--detach",snapshot]);assert not git("status","--porcelain")
    tests=[
      [sys.executable,"-m","unittest","discover","-s","plugins/ca/hooks/tests","-p","test_release*followup.py","-v"],
      [sys.executable,".github/scripts/test_consumer_smoke.py"],
      [sys.executable,".github/scripts/test_release_lib.py"],
      [sys.executable,".github/scripts/test_release_workflow.py"],
      [sys.executable,".github/scripts/test_payload_version_gate.py"],
      [sys.executable,".github/scripts/test_ci_impact.py"],
      [sys.executable,".github/scripts/test_build_surface.py"],
      [sys.executable,".github/scripts/test_host_descriptors.py"],
      [sys.executable,".github/scripts/test_public_codex_docs.py"],
      [sys.executable,".github/scripts/test_auto_release_candidate.py"],
      [sys.executable,".github/scripts/check_auto_release_candidate.py","--candidate","HEAD"],
      [sys.executable,".github/scripts/payload_version_gate.py","--plugin","plugins/ca","--base",UP],
      [sys.executable,".github/scripts/payload_version_gate.py","--plugin","plugins/ca-codex","--base",UP],
      [sys.executable,"tools/build-host-packages.py","--release-guard-base",UP],
      [sys.executable,"tools/sync-core.py","--check"],
      [sys.executable,"tools/build-surface.py","--check"],
      [sys.executable,"tools/build-host-packages.py","--check"],
      ["git","diff","--check"],
    ]
    results=[]
    for index,command in enumerate(tests):
        with (out/f"check-{index:02d}.log").open("w") as log:
            result=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT,timeout=300)
        results.append(dict(command=command,exit_code=result.returncode));print(json.dumps(results[-1]),flush=True)
    with (out/"independent-skill-proof.log").open("w") as log:
        proof=subprocess.run([sys.executable,".github/scripts/check_skill_proof_fresh.py"],cwd=root,stdout=log,stderr=subprocess.STDOUT,timeout=120)
    (out/"results.json").write_text(json.dumps(dict(pr=PR,upstream=UP,tree=TREE,snapshot=snapshot,checks=results,independent_skill_proof_exit=proof.returncode,qualification="Deterministic integration and archived-payload tests; not independent agent judgment"),indent=2)+"\n")
    assert not any(r["exit_code"] for r in results), "candidate check failed"
    assert not git("status","--porcelain"), "checks mutated the candidate"
    files=[]
    for entry in EXPECTED:
        assert blob(entry["path"])==entry["sha"],entry["path"]
        files.append({**entry,"content":(root/entry["path"]).read_text()})
    packet=dict(repository="arbiterForge/codeArbiter",pr=PR,upstream=UP,base_tree=BASE_TREE,tree=TREE,files=files)
    raw=(json.dumps(packet,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()
    assert hashlib.sha256(raw).hexdigest()==PACKET_SHA
    (out/"files.json").write_bytes(raw)

if __name__=="__main__":main()

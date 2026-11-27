import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
REPO = Path(r"C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter")
SOURCE = "2df782d48576e72bd01ef303c9f3546f3b620b05"
GIT = r"C:/Program Files/Git/cmd/git.exe"
NODE = Path(r"C:/Users/brenn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe")
OUT = ROOT / "execution-r1"
WORK = ROOT / "execution" / "source"
TOOLS = WORK / "plugins/ca-sandbox/tools"
digest = lambda data: hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output([GIT, "--no-lazy-fetch", *args], cwd=REPO)


def identity():
    index = Path(git("rev-parse", "--path-format=absolute", "--git-path", "index").decode().strip())
    return {"head": git("rev-parse", "HEAD").decode().strip(), "index_sha256": digest(index.read_bytes())}


def members(directory):
    result = {}
    for parent, dirs, files in os.walk(directory, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name not in (".vite", ".vite-temp", ".cache"))
        for name in dirs:
            path = Path(parent) / name
            info = path.lstat()
            assert not getattr(info, "st_file_attributes", 0) & 0x400 and not path.is_symlink()
        for name in sorted(files):
            path = Path(parent) / name
            info = path.lstat()
            assert stat.S_ISREG(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400
            result[path.relative_to(directory).as_posix()] = digest(path.read_bytes())
    return result


OUT.mkdir(parents=True)
before_identity = identity()
EXECUTION = "ca4966745fa44f1baddd08613702db023d83fe60"
assert before_identity["head"] == EXECUTION
ACTION = Path(r"C:/Users/brenn/AppData/Local/Temp/ca-next-work-inventory-pk_t9ajr/action-packet.json")
assert digest(ACTION.read_bytes()) == "a32c3e3488212f7dbbb27e81a2e271ae88e769c547ca0e38762159585e9ed812"
group = json.loads(ACTION.read_bytes())["next_groups"][1]
assert len(group["new_selectors"]) == 40 and len(group["already_current_reusable"]) == 5
old = json.loads(Path(group["current_proof"]).read_bytes())
assert digest(Path(group["current_proof"]).read_bytes()) == group["current_proof_sha256"]
all_input_names = set(old["inputs"])
for ref in group["old_proofs"]:
    all_input_names.update(json.loads(git("show", EXECUTION+":"+ref))["inputs"])
all_input_names.update(s["file"] for s in group["new_selectors"])
old["inputs"] = {path: digest((REPO/path).read_bytes()) for path in all_input_names}
selection = {"selectors":[s["exact_selector"] for s in group["new_selectors"]]}
inputs = {path: digest((REPO / path).read_bytes()) for path in old["inputs"]}
committed = {path: digest(git("show", SOURCE + ":" + path)) for path in inputs}
current_committed = {path: digest(git("show", EXECUTION + ":" + path)) for path in inputs}
assert inputs == committed == current_committed
for path in inputs:
    target = WORK / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((REPO / path).read_bytes())

# Reuse cached dependency bytes privately, without npm/install or Gov cache writes.
cache = Path(group["runtime_cache_node_modules"])
expected_runtime = json.loads(Path(group["runtime_members"]).read_bytes())
assert digest(Path(group["runtime_members"]).read_bytes()) == group["runtime_members_sha256"]
runtime_before = members(cache)
assert runtime_before == expected_runtime and len(runtime_before) == 1473
for relative in runtime_before:
    target = TOOLS / "node_modules" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cache / relative, target)
private_runtime_before = members(TOOLS / "node_modules")
assert private_runtime_before == runtime_before
vitest = TOOLS / "node_modules/vitest/vitest.mjs"
package = json.loads((TOOLS / "node_modules/vitest/package.json").read_bytes())
lock = json.loads((TOOLS / "package-lock.json").read_bytes())
assert package["version"] == lock["packages"]["node_modules/vitest"]["version"] == "4.1.12"
home = OUT / "private-home"
home.mkdir()
env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if name in os.environ}
env.update(HOME=str(home), USERPROFILE=str(home), APPDATA=str(home), LOCALAPPDATA=str(home),
           TEMP=str(home), TMP=str(home), XDG_CONFIG_HOME=str(home), NO_COLOR="1", FORCE_COLOR="0",
           PYTHONDONTWRITEBYTECODE="1", PATH=os.pathsep.join((str(NODE.parent), str(Path(GIT).parent),
                                                           str(Path(os.environ["SystemRoot"]) / "System32"))))
assert shutil.which("docker", path=env["PATH"]) is None
os.environ.clear()
os.environ.update(env)  # Private HOME exists before project owner imports.
spec = importlib.util.spec_from_file_location("sandbox_capture_boundary", REPO / ".github/scripts/_boundedproc.py")
bounded = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bounded
spec.loader.exec_module(bounded)
pattern = group["argv_template"][group["argv_template"].index("--testNamePattern")+1]
files = sorted(set(Path(s["file"]).name for s in group["new_selectors"]))
assert files == ["build-pinned-base.test.ts", "builder-observation.test.ts", "state-contracts.test.ts"]
argv = [str(NODE), str(vitest), "run", *files, "--testNamePattern", pattern,
        "--no-cache", "--reporter=json", "--outputFile=" + str(OUT / "original-vitest.json")]
runtime_identity = {"node_path": str(NODE), "node_sha256": digest(NODE.read_bytes()),
                    "vitest_version": package["version"], "vitest_entry_sha256": digest(vitest.read_bytes()),
                    "python_path": sys.executable, "python_version": sys.version,
                    "python_sha256": digest(Path(sys.executable).read_bytes()),
                    "transport_path": str(REPO / ".github/scripts/_boundedproc.py"),
                    "transport_sha256": digest((REPO / ".github/scripts/_boundedproc.py").read_bytes())}
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
clock = time.monotonic()
process = bounded.run(argv, timeout=120, cwd=TOOLS, env=env)
seconds = time.monotonic() - clock
(OUT / "original.stdout.log").write_text(process.stdout, encoding="utf-8", newline="\n")
(OUT / "original.stderr.log").write_text(process.stderr, encoding="utf-8", newline="\n")
after = {path: digest((REPO / path).read_bytes()) for path in inputs}
private_after = {path: digest((WORK / path).read_bytes()) for path in inputs}
runtime_after = members(cache)
private_runtime_after = members(TOOLS / "node_modules")
end_identity = identity()
result = {"format": "bounded-current-local-observation/1", "source_commit": SOURCE, "actual_execution_commit": EXECUTION,
          "source_relation": "Exact committed/physical source bytes copied before execution; private cached dependency byte copy, not installation.",
          "started_at": started, "argv": argv, "cwd": str(TOOLS), "exit_code": process.returncode,
          "timed_out": process.timed_out, "containment": process.containment, "seconds": seconds,
          "identity_before": before_identity, "identity_after": end_identity,
          "inputs_before": inputs, "inputs_after": after, "committed_inputs": committed, "actual_execution_committed_inputs": current_committed,
          "private_inputs_after": private_after, "runtime": runtime_identity,
          "runtime_member_count": len(runtime_before), "runtime_member_inventory_sha256": digest(json.dumps(runtime_before, sort_keys=True).encode()),
          "runtime_before_after_private_equal": runtime_before == runtime_after == private_runtime_before == private_runtime_after,
          "environment_keys": sorted(env), "docker_executable_on_explicit_path": False,
          "source_no_cache_option": "Existing locked Vitest4 CLI cache=false; no assertion/source/config mutation. All caches/output remain in private Temp.",
          "limits": ["Pure injected unit controls; no Docker daemon/container or original installed package effects.",
                     "Unselected Docker suites are not qualified by developer-mode collection.",
                     "No product build/typecheck/coverage suite or new dependency/install."]}
(OUT / "runtime-members.json").write_text(json.dumps(runtime_before, sort_keys=True) + "\n", encoding="utf-8")
(OUT / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
assert process.returncode == 0 and not process.timed_out and process.containment == "exited"
assert inputs == after == private_after == committed and before_identity == end_identity
assert runtime_before == runtime_after == private_runtime_before == private_runtime_after
report = json.loads((OUT / "original-vitest.json").read_bytes())
observed = {}
for suite in report["testResults"]:
    for case in suite["assertionResults"]:
        if case["status"] == "passed":
            relative = Path(suite["name"]).relative_to(WORK).as_posix()
            key = "vitest:" + relative + ":" + case["fullName"]
            assert key not in observed
            observed[key] = case["status"]
assert set(observed) == set(selection["selectors"]) and len(observed) == 40
(OUT / "selection.json").write_text(json.dumps(group,indent=2)+"\n",encoding="utf-8")
print(json.dumps({"source": SOURCE, "actual_execution_commit": EXECUTION, "selected": len(observed), "passed": len(observed), "seconds": seconds,
                  "inputs": len(inputs), "runtime_members": len(runtime_before), "no_Gov_cache_changes": True}))

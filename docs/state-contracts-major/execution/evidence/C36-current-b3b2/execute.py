import ast
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

OUT = Path(__file__).resolve().parent
REPO = Path(r"C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter")
GIT = r"C:/Program Files/Git/cmd/git.exe"
NODE = Path(r"C:/Users/brenn/AppData/Local/Temp/ca-node22.19-offline-repro-vtod7t5h/node.EXE")
EXPECTED = "b3b2b5a091c4f3d28366bb29d10ae3fb1b3e22bc"
EPOCH = "2df782d48576e72bd01ef303c9f3546f3b620b05"
digest = lambda data: hashlib.sha256(data).hexdigest()
def save(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
def git(*args):
    return subprocess.check_output([GIT, "--no-lazy-fetch", *args], cwd=REPO)
def identity():
    index = Path(git("rev-parse", "--path-format=absolute", "--git-path", "index").decode().strip())
    return {"head": git("rev-parse", "HEAD").decode().strip(), "index_sha256": digest(index.read_bytes())}
roots = [".github/scripts", "core/pysrc", "plugins/ca/hooks", "plugins/ca-codex/hooks"]
def py_inventory():
    answer = {}
    for root in roots:
        for p in (REPO / root).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            assert not p.is_symlink(), str(p)
            answer[p.relative_to(REPO).as_posix()] = digest(p.read_bytes())
    return dict(sorted(answer.items()))
ts = set()
todo = [REPO / "plugins/ca-pi/tools/test/benchmark-boundary.ts"]
while todo:
    p = todo.pop().resolve()
    if p in ts:
        continue
    ts.add(p)
    for name in re.findall(r'(?:from\s*|import\s*)["\']([^"\']+)["\']', p.read_text(encoding="utf-8")):
        if name.startswith("."):
            child = (p.parent / name).resolve()
            assert child.is_file(), name
            todo.append(child)
        else:
            assert name.startswith("node:"), name
assert len(ts) == 9
fixed = {p.relative_to(REPO).as_posix() for p in ts}
fixed.update(["plugins/ca-pi/tools/package.json", "plugins/ca-pi/tools/package-lock.json", "plugins/ca-pi/tools/tsconfig.json"])
# Capture all actual ancestor package/TS configuration lookups, including absences.
config_lookup = {}
for start in ts:
    for parent in start.parents:
        if parent == REPO.parent:
            break
        for name in ("package.json", "tsconfig.json"):
            p = parent / name
            relative = p.relative_to(REPO).as_posix()
            config_lookup[relative] = digest(p.read_bytes()) if p.is_file() else None
            if p.is_file():
                fixed.add(relative)
def dependency_inventory():
    paths = []
    for relative in ["plugins/ca-pi/tools/node_modules/esbuild", "plugins/ca-pi/tools/node_modules/@esbuild/win32-x64"]:
        paths.extend(p for p in (REPO / relative).rglob("*") if p.is_file())
    return {p.relative_to(REPO).as_posix(): digest(p.read_bytes()) for p in sorted(paths)}
runtime_paths = [Path(sys.executable), Path(sys.base_prefix) / "python314.dll", NODE]
def runtime():
    return {str(p): digest(p.read_bytes()) for p in runtime_paths}
def absent_lookup():
    results = {}
    for base in roots:
        current = REPO
        entries = []
        for component in (base + "/_host.py").split("/"):
            names = sorted(p.name for p in current.iterdir())
            assert all(name.isascii() for name in names), str(current)
            matches = [name for name in names if name.lower() == component.lower()]
            assert len(matches) <= 1
            entries.append({"directory": current.relative_to(REPO).as_posix(), "requested": component, "entries": names, "matches": matches})
            if not matches:
                break
            current /= matches[0]
        results[base + "/_host.py"] = {"exists": current.is_file() if matches else False, "physical_inventory": entries}
    return results

before_id = identity()
assert before_id["head"] == EXPECTED
before_py = py_inventory()
before_fixed = {x: digest((REPO / x).read_bytes()) for x in sorted(fixed)}
before_deps = dependency_inventory()
before_runtime = runtime()
assert before_runtime[str(NODE)] == "995a3fb3cefad590cd3f4b321532a4b9582fb9c6575320ed2e3e894caac3e362"
before_absent = absent_lookup()
# Successful complete immutable tree inventories, not failed blob reads as absence.
trees_before = {base: git("ls-tree", "-r", "-z", EXPECTED, "--", base).decode("utf-8") for base in roots}
save("before.json", {"identity": before_id, "python_inventory": before_py, "fixed_inputs": before_fixed,
    "config_lookups": config_lookup, "dependencies": before_deps, "runtime": before_runtime,
    "host_lookup": before_absent, "immutable_trees": trees_before})
home = OUT / "private-home"
home.mkdir()
for name in ("roaming", "local", "config", "cache", "tmp"):
    (home / name).mkdir()
env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if name in os.environ}
env.update(HOME=str(home), USERPROFILE=str(home), APPDATA=str(home / "roaming"), LOCALAPPDATA=str(home / "local"),
    XDG_CONFIG_HOME=str(home / "config"), XDG_CACHE_HOME=str(home / "cache"), TEMP=str(home / "tmp"), TMP=str(home / "tmp"),
    PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8",
    PYTHONPATH=str(OUT / "observer"), PATH=str(NODE.parent) + os.pathsep + str(Path(os.environ["SystemRoot"]) / "System32"))
argv = [sys.executable, "-B", "-X", "utf8", ".github/scripts/pi_benchmark.py", "--samples", "100"]
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
clock = time.monotonic()
p = subprocess.run(argv, cwd=REPO, env=env, capture_output=True, timeout=100)
seconds = time.monotonic() - clock
(OUT / "original.stdout.log").write_bytes(p.stdout)
(OUT / "original.stderr.log").write_bytes(p.stderr)
after_py = py_inventory()
after_fixed = {x: digest((REPO / x).read_bytes()) for x in sorted(fixed)}
after_deps = dependency_inventory()
after_runtime = runtime()
after_absent = absent_lookup()
after_id = identity()
trees_after = {base: git("ls-tree", "-r", "-z", EXPECTED, "--", base).decode("utf-8") for base in roots}
observed = json.loads((OUT / "boundary-observation.json").read_text(encoding="utf-8"))
loaded = observed["loaded_source_first_call_sha256"]
committed = {name: digest(git("show", EXPECTED + ":" + name)) for name in set(loaded) | fixed}
epoch = {name: digest(git("show", EPOCH + ":" + name)) for name in set(loaded) | fixed}
actual = {**before_py, **before_fixed}
stable = before_py == after_py and before_fixed == after_fixed and before_deps == after_deps and before_runtime == after_runtime and before_id == after_id and before_absent == after_absent and trees_before == trees_after
save("after.json", {"identity": after_id, "python_inventory": after_py, "fixed_inputs": after_fixed,
    "dependencies": after_deps, "runtime": after_runtime, "host_lookup": after_absent, "immutable_trees": trees_after})
result = {"format": "C36-original-benchmark-execution/1", "started_at": started, "actual_execution_commit": EXPECTED,
    "source_input_epoch": EPOCH, "argv": argv, "cwd": str(REPO), "environment": env, "exit_code": p.returncode,
    "seconds": seconds, "before_after_stable": stable, "inputs": {x: actual[x] for x in sorted(set(loaded) | fixed)},
    "literal_git_execution_inputs": committed, "literal_git_2df_inputs": epoch,
    "loaded_source_matches_before": all(actual.get(x) == value for x,value in loaded.items()),
    "git_matches_physical": all(committed[x] == actual[x] for x in committed), "epoch_matches_current": epoch == committed,
    "observer_errors": observed["observer_errors"], "runtime": observed["runtime"],
    "boundary_observation_count": len(observed["observations"]), "public_stdout_utf8": p.stdout.decode("utf-8"),
    "observer_identity": {"execute_sha256": digest(Path(__file__).read_bytes()), "profiler_sha256": digest((OUT / "observer/sitecustomize.py").read_bytes())}}
save("result.json", result)
print(json.dumps({k:result[k] for k in ["exit_code","seconds","before_after_stable","git_matches_physical","epoch_matches_current","loaded_source_matches_before","observer_errors","boundary_observation_count"]}))
assert p.returncode == 0 and stable and result["git_matches_physical"] and result["epoch_matches_current"] and result["loaded_source_matches_before"] and not observed["observer_errors"] and len(observed["observations"]) == 2

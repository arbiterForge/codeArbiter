import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
REPO = Path(r"C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter")
SOURCE = "2df782d48576e72bd01ef303c9f3546f3b620b05"
GIT = r"C:/Program Files/Git/cmd/git.exe"
OLD = "docs/state-contracts-major/execution/evidence/workflow-recovery-ce3a4a91/canonical-runtime.json"
OUT = ROOT / "recovery"
OUT.mkdir(parents=True, exist_ok=True)
digest = lambda data: hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output([GIT, "--no-lazy-fetch", *args], cwd=REPO)


def identity():
    index = Path(git("rev-parse", "--path-format=absolute", "--git-path", "index").decode().strip())
    return {"head": git("rev-parse", "HEAD").decode().strip(), "index_sha256": digest(index.read_bytes())}


def absence():
    physical, immutable = [], []
    parent = REPO
    relative = ""
    for component in ("core", "pysrc", "_host.py"):
        info = parent.lstat()
        assert stat.S_ISDIR(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400
        with os.scandir(parent) as directory:
            names = sorted(entry.name for entry in directory)
        assert all(name.isascii() for name in names)
        matches = [name for name in names if name.lower() == component.lower()]
        physical.append({"parent": relative or ".", "successful_enumeration": True,
                         "names": names, "matches": matches, "directory_identity": [info.st_dev, info.st_ino]})
        raw = git("ls-tree", "-z", SOURCE + (":" + relative if relative else ""))
        entries = []
        for record in raw.split(b"\0"):
            if record:
                header, name = record.split(b"\t", 1)
                assert name.isascii()
                entries.append({"name": name.decode(), "entry": header.decode()})
        found = [item for item in entries if item["name"].lower() == component.lower()]
        immutable.append({"parent": relative or ".", "successful_enumeration": True,
                          "entries": entries, "matches": found, "stdout_sha256": digest(raw)})
        if component == "_host.py":
            assert matches == [] and found == []
        else:
            assert matches == [component] and len(found) == 1 and found[0]["name"] == component
            assert found[0]["entry"].startswith("040000 tree ")
            parent /= component
            relative = (relative + "/" + component).lstrip("/")
    return {"descriptor": {"path": "core/pysrc/_host.py", "path_style": "windows"},
            "physical": physical, "immutable": immutable}


old = json.loads(git("show", SOURCE + ":" + OLD))
selectors = sorted({name for row in old["semantic_mapping"] for name in row["observed_named_assertions"]})
assert len(selectors) == 27
start_identity = identity()
assert start_identity["head"] == SOURCE
inputs = {path: digest((REPO / path).read_bytes()) for path in old["inputs"]}
committed = {path: digest(git("show", SOURCE + ":" + path)) for path in inputs}
assert inputs == committed and len(inputs) == 100
before_absence = absence()
before_members = git("ls-tree", "-z", SOURCE + ":core/pysrc")
home = OUT / "private-home"
home.mkdir()
env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if key in os.environ}
env.update(HOME=str(home), USERPROFILE=str(home), APPDATA=str(home), LOCALAPPDATA=str(home),
           TEMP=str(home), TMP=str(home), XDG_CONFIG_HOME=str(home),
           PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8", PATH=str(Path(GIT).parent))
argv = [sys.executable, "-B", "-X", "utf8", "-m", "unittest", "-v", *selectors]
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
clock = time.monotonic()
process = subprocess.run(argv, cwd=REPO / ".github/scripts", env=env, capture_output=True, timeout=150)
seconds = time.monotonic() - clock
(OUT / "original.stdout.log").write_bytes(process.stdout)
(OUT / "original.stderr.log").write_bytes(process.stderr)
after = {path: digest((REPO / path).read_bytes()) for path in inputs}
after_absence = absence()
end_identity = identity()
text = process.stderr.decode("utf-8")
named = []
for name in selectors:
    method = name.rsplit(".", 1)[1]
    pattern = r"(?m)^" + re.escape(method) + r" \(" + re.escape(name) + r"\) \.\.\. ([^\r\n]+)\r?$"
    values = re.findall(pattern, text)
    named.append({"id": name, "outcomes": values})
result = {"format": "bounded-current-local-observation/1", "source_commit": SOURCE,
          "started_at": started, "argv": argv, "cwd": str(REPO / ".github/scripts"),
          "exit_code": process.returncode, "seconds": seconds,
          "selectors": selectors, "named_results": named,
          "identity_before": start_identity, "identity_after": end_identity,
          "inputs_before": inputs, "inputs_after": after, "committed_inputs": committed,
          "absence_before": before_absence, "absence_after": after_absence,
          "core_membership_before_sha256": digest(before_members),
          "core_membership_after_sha256": digest(git("ls-tree", "-z", SOURCE + ":core/pysrc")),
          "runtime": {"python_executable": sys.executable, "python_version": sys.version,
                      "python_sha256": digest(Path(sys.executable).read_bytes()),
                      "git_executable": GIT, "git_sha256": digest(Path(GIT).read_bytes())},
          "environment_keys": sorted(env), "disposable_home_before_import": True,
          "stdout_sha256": digest(process.stdout), "stderr_sha256": digest(process.stderr),
          "observer_sha256": digest(Path(__file__).read_bytes()),
          "limits": ["Canonical local Windows recovery/legacy board fixtures only.",
                     "No native build, installed/host producer, provider, physical consent, or TUI acceptance.",
                     "Original27 selectors derive only from the22 retained WR clause mappings; not all38 methods."]}
(OUT / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
assert process.returncode == 0
assert all(row["outcomes"] == ["ok"] for row in named)
assert inputs == after == committed and start_identity == end_identity
assert before_absence == after_absence
print(json.dumps({"source": SOURCE, "selected": len(named), "passed": len(named), "seconds": seconds,
                  "inputs": len(inputs), "head_index_inputs_absence_stable": True}))

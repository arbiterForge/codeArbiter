import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
REPO = Path(r"C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter")
SOURCE = "2df782d48576e72bd01ef303c9f3546f3b620b05"
GIT = r"C:/Program Files/Git/cmd/git.exe"
OLD = "docs/state-contracts-major/execution/evidence/reader-integrity-dde4/reader-fixtures.json"
digest = lambda b: hashlib.sha256(b).hexdigest()


def git(*args):
    return subprocess.check_output([GIT, "--no-lazy-fetch", *args], cwd=REPO)


def identity():
    index = Path(git("rev-parse", "--path-format=absolute", "--git-path", "index").decode().strip())
    return {"head": git("rev-parse", "HEAD").decode().strip(), "index_sha256": digest(index.read_bytes())}


old = json.loads(git("show", SOURCE + ":" + OLD))
before = {path: digest((REPO / path).read_bytes()) for path in old["inputs"]}
committed = {path: digest(git("show", SOURCE + ":" + path)) for path in before}
assert before == committed and len(before) == 5
before_identity = identity()
execution_commit = before_identity["head"]
assert {path: digest(git("show", execution_commit + ":" + path)) for path in before} == committed
subprocess.run([GIT, "--no-lazy-fetch", "merge-base", "--is-ancestor", SOURCE, execution_commit], cwd=REPO, check=True)
selectors = [
    "ReadinessWaitTest.test_binary_readiness_preserves_completion_from_one_write",
    "ReadinessWaitTest.test_binary_early_eof_reports_closed_and_finishes_empty",
    "ReadinessWaitTest.test_communicate_without_input_closes_stdin_after_readiness",
    "ReadinessWaitTest.test_communicate_sends_text_or_binary_input_after_readiness",
    "ReadinessWaitTest.test_communicate_timeout_retry_sends_the_original_payload_once",
    "ReadinessWaitTest.test_unread_stdin_stays_bounded_and_cleanup_settles_writer",
    "CodexHostCommandDeadlineTest.test_hanging_codex_command_fails_with_timeout_and_containment",
    "CodexHostCommandDeadlineTest.test_a_timed_out_marketplace_add_is_a_recorded_failure",
    "PiBenchmarkReadinessDeadlineTest.test_no_ready_line_is_a_bounded_failure_with_containment",
    "PiBenchmarkReadinessDeadlineTest.test_partial_ready_line_is_refused",
    "PiBenchmarkReadinessDeadlineTest.test_immediate_exit_is_refused",
    "PiBenchmarkReadinessDeadlineTest.test_hang_after_ready_is_bounded",
    "PiBenchmarkReadinessDeadlineTest.test_well_behaved_boundary_completes",
    "PiBenchmarkReadinessDeadlineTest.test_partial_early_exit_retains_readiness_failure_when_group_signal_is_denied",
]
home = ROOT / "private-home"
home.mkdir()
env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT") if name in os.environ}
env.update(HOME=str(home), USERPROFILE=str(home), APPDATA=str(home), LOCALAPPDATA=str(home),
           TEMP=str(home), TMP=str(home), XDG_CONFIG_HOME=str(home), PYTHONNOUSERSITE="1",
           PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8",
           PATH=str(Path(os.environ["SystemRoot"]) / "System32"))
argv = [sys.executable, "-B", "-X", "utf8", "-m", "unittest", "-v",
        *["test_boundedproc." + name for name in selectors]]
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
clock = time.monotonic()
process = subprocess.run(argv, cwd=REPO / ".github/scripts", env=env, capture_output=True, timeout=90)
seconds = time.monotonic() - clock
(ROOT / "original.stdout.log").write_bytes(process.stdout)
(ROOT / "original.stderr.log").write_bytes(process.stderr)
after = {path: digest((REPO / path).read_bytes()) for path in before}
after_identity = identity()
named = []
text = process.stderr.decode("utf-8")
for name in selectors:
    method = name.rsplit(".", 1)[1]
    pattern = r"(?m)^" + re.escape(method) + r" \(test_boundedproc\." + re.escape(name) + r"\) \.\.\. ([^\r\n]+)\r?$"
    named.append({"id": "test_boundedproc." + name, "outcomes": re.findall(pattern, text)})
result = {"format": "bounded-current-reader-observation/1", "source_commit": SOURCE,
          "actual_execution_commit": execution_commit,
          "source_relation": "Declared executable input epoch2df; actual observed HEAD/index at execution retained independently; all5 inputs literally match both Git subjects and physical source.",
          "started_at": started, "argv": argv, "cwd": str(REPO / ".github/scripts"),
          "exit_code": process.returncode, "seconds": seconds, "selectors": selectors,
          "named_results": named, "inputs_before": before, "inputs_after": after,
          "committed_inputs": committed, "identity_before": before_identity, "identity_after": after_identity,
          "runtime": {"python_executable": sys.executable, "version": sys.version,
                      "sha256": digest(Path(sys.executable).read_bytes()), "platform": sys.platform},
          "environment_keys": sorted(env), "disposable_HOME_before_import": True,
          "module_scope": "All5 explicit project module paths captured; stdlib-only import cone inspected. No hostapi/Go/installed-source lookup is executed, so no invented host absence or native membership declaration.",
          "stdout_sha256": digest(process.stdout), "stderr_sha256": digest(process.stderr),
          "observer_sha256": digest(Path(__file__).read_bytes()),
          "limits": ["14 exact existing fixture methods; neither full23 module nor warm100 benchmark executed.",
                     "No Pi/Codex CLI, Node, esbuild, native/Go, provider, network, install, API or production build.",
                     "Cleanup statuses are the existing Windows process-group/taskkill owner, not Job Object/native rundown guarantees.",
                     "The generic grandchild test was excluded because its untyped Windows liveness helper is not needed or adopted as a stronger oracle."]}
(ROOT / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
assert process.returncode == 0 and all(row["outcomes"] == ["ok"] for row in named)
assert before == after == committed and before_identity == after_identity
print(json.dumps({"source": SOURCE, "selected": len(named), "passed": len(named), "seconds": seconds,
                  "source_inputs": len(before), "head_index_inputs_stable": True}))

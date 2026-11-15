"""Read-only benchmark witness. No target function or process replacement."""
import atexit
import hashlib
import json
import os
from pathlib import Path
import sys

REPO = Path(r"C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter").resolve()
OUT = Path(__file__).resolve().parents[1]
loaded = {}
observations = []
errors = []

def digest(data):
    return hashlib.sha256(data).hexdigest()

def profiler(frame, event, arg):
    if event not in ("call", "return"):
        return
    filename = frame.f_code.co_filename
    if filename.startswith("<"):
        return
    try:
        path = Path(filename).resolve()
        relative = path.relative_to(REPO).as_posix()
    except (ValueError, OSError):
        return
    try:
        if relative not in loaded:
            loaded[relative] = digest(path.read_bytes())
        if event == "return" and relative == ".github/scripts/pi_benchmark.py":
            name = frame.f_code.co_name
            if name == "_boundary_session" and isinstance(arg, tuple) and len(arg) == 3:
                startup, ready, remaining = arg
                bundle = Path(frame.f_locals["argv"][1])
                observations.append({"owner": name, "startup_ms": startup, "ready": ready,
                    "completion": json.loads(remaining), "completion_original_utf8_sha256": digest(remaining.encode("utf-8")),
                    "bundle_sha256": digest(bundle.read_bytes()), "bundle_bytes": bundle.stat().st_size,
                    "child_argv": frame.f_locals["argv"], "child_exit_code": frame.f_locals["process"].returncode})
            elif name == "_production_pi_samples" and isinstance(arg, tuple):
                built = frame.f_locals["built"]
                observations.append({"owner": name, "build_argv": built.args,
                    "build_exit_code": built.returncode,
                    "build_stdout_sha256": digest(built.stdout.encode("utf-8")),
                    "build_stderr_sha256": digest(built.stderr.encode("utf-8")),
                    "validated_sample_count": len(arg[1])})
    except Exception as error:
        errors.append(type(error).__name__)

def finish():
    sys.setprofile(None)
    document = {"format": "C36-read-only-profiler/1", "loaded_source_first_call_sha256": loaded,
        "observations": observations, "observer_errors": errors,
        "runtime": {"python": sys.version, "executable": sys.executable},
        "limits": "Profile hooks read frames and selected fixed fields only; original owner functions/argv/return values are not replaced. Instrumentation overhead means no uninstrumented performance claim."}
    (OUT / "boundary-observation.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8", newline="\n")

atexit.register(finish)
sys.setprofile(profiler)

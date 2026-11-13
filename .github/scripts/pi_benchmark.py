#!/usr/bin/env python3
"""Deterministic relative adapter benchmark for Claude, Codex, and Pi.

The benchmark intentionally measures local adapter/core work only. It never
starts a provider, reads host authentication, or emits fixture payloads.
"""

import argparse
import importlib.util
import json
import math
import pathlib
import platform
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = pathlib.Path(__file__).resolve().parents[2]
HOST_HOOKS = {
    "claude": ROOT / "plugins" / "ca" / "hooks",
    "codex": ROOT / "plugins" / "ca-codex" / "hooks",
    "pi": ROOT / "plugins" / "ca-pi" / "hooks",
}
WARMUP_EVENTS = 5
REQUIRED_SAMPLES = 100
PUBLIC_KEYS = (
    "platform", "host", "sampleCount", "startupMs", "coreP50Ms",
    "adapterP50Ms", "adapterP95Ms",
)
PI_BOUNDARY_SOURCE = ROOT / "plugins" / "ca-pi" / "tools" / "test" / "benchmark-boundary.ts"
PI_TOOLS = ROOT / "plugins" / "ca-pi" / "tools"
PI_BRIDGE_SCRIPT = ROOT / "plugins" / "ca-pi" / "hooks" / "pi-bridge.py"
REAL_SPAWN_WARMUP = 2
REAL_SPAWN_SAMPLES = 8
REAL_SPAWN_PUBLIC_KEYS = ("platform", "host", "mode", "sampleCount", "medianMs", "p95Ms")


def promotion_limit(claude_p95, codex_p95):
    slower = max(float(claude_p95), float(codex_p95))
    return slower + max(slower * 0.25, 10.0)


def benchmark_passes(pi_p95, claude_p95, codex_p95):
    return float(pi_p95) <= promotion_limit(claude_p95, codex_p95)


def percentile(values, percent):
    if not values:
        raise ValueError("percentile requires at least one sample")
    ordered = sorted(float(value) for value in values)
    rank = max(1, math.ceil((float(percent) / 100.0) * len(ordered)))
    return ordered[rank - 1]


def summarize_samples(values):
    if len(values) != REQUIRED_SAMPLES:
        raise ValueError("benchmark requires exactly 100 warm samples")
    return {"p50": percentile(values, 50), "p95": percentile(values, 95)}


def canonical_corpus():
    return (
        {"kind": "read", "path": "fixture π.txt"},
        {"kind": "exec", "command": "git status --short"},
        {"kind": "write", "path": "generated/fixture.txt", "content": "fixture\n"},
    )


def _native_event(host_name, event):
    kind = event["kind"]
    if host_name == "claude":
        if kind == "read":
            return "Read", {"file_path": event["path"]}
        if kind == "exec":
            return "Bash", {"command": event["command"]}
        return "Write", {"file_path": event["path"], "content": event["content"]}
    if host_name == "codex":
        if kind == "read":
            return "Read", {"file_path": event["path"]}
        if kind == "exec":
            return "exec_command", {"command": event["command"]}
        patch = "\n".join((
            "*** Begin Patch", f"*** Add File: {event['path']}",
            "+fixture", "*** End Patch", "",
        ))
        return "apply_patch", {"command": patch}
    if kind == "read":
        return "read", {"path": event["path"]}
    if kind == "exec":
        return "bash", {"command": event["command"]}
    return "write", {"path": event["path"], "content": event["content"]}


def _load_module(path, name, import_root):
    previous_path = list(sys.path)
    previous_hostapi = sys.modules.pop("hostapi", None)
    try:
        sys.path.insert(0, str(import_root))
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load benchmark module {name}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = previous_path
        sys.modules.pop("hostapi", None)
        if previous_hostapi is not None:
            sys.modules["hostapi"] = previous_hostapi


def _load_host(host_name):
    hooks = HOST_HOOKS[host_name]
    module = _load_module(hooks / "_host.py", f"ca_benchmark_host_{host_name}", hooks)
    return module.HOST


def _load_core(host_name):
    core = ROOT / "core" / "pysrc"
    return _load_module(core / "_hooklib.py", f"ca_benchmark_core_{host_name}", core)


def _adapter_once(host_name, host, event):
    tool, native_input = _native_event(host_name, event)
    category = host.normalize_tool(tool)
    normalized = host.normalize_tool_input(tool, native_input)
    operations = host.iter_file_ops({"tool_name": tool, "tool_input": native_input}) if event["kind"] == "write" else []
    # Include the JSON boundary each adapter must cross while retaining only a
    # bounded semantic result. The serialized value is deliberately discarded.
    json.loads(json.dumps({
        "category": category,
        "inputKeys": sorted(normalized),
        "operationCount": len(operations),
    }, ensure_ascii=False))


def _round_ms(nanoseconds):
    return round(nanoseconds / 1_000_000.0, 6)


BOUNDARY_READY_SECONDS = 30.0
BOUNDARY_COMPLETE_SECONDS = 30.0


def _boundary_session(argv, cwd, ready_timeout=BOUNDARY_READY_SECONDS,
                      complete_timeout=BOUNDARY_COMPLETE_SECONDS):
    """Run the boundary child with a deadline on BOTH phases (R-07 / C-F08).

    The readiness line used to block in readline() with no bound, so a child
    that never wrote it waited forever before the 30-second completion
    timeout could apply. Each phase now has a deadline; on a miss the whole
    child tree is terminated and the error states the containment outcome
    plus any partial stderr, never implying the child is quiescent.
    """
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import _boundedproc

    def fail(phase, reason):
        try:
            containment = _boundedproc.terminate_tree(process)
        except OSError:
            containment = "unconfirmed"
        try:
            partial_out, err = process.communicate(timeout=_boundedproc.GRACE_SECONDS)
        except (subprocess.TimeoutExpired, OSError, ValueError):
            partial_out, err = "", ""
        tail = (err or partial_out or ready_raw or "").strip()[-400:]
        raise RuntimeError(
            f"production Pi benchmark boundary {phase} failed: {reason}; "
            f"containment={containment}" + (f"; partial output: {tail}" if tail else ""))

    startup = time.perf_counter_ns()
    process = _boundedproc.start(
        argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    ready_raw, reason = _boundedproc.readline(process, ready_timeout)
    startup_ms = _round_ms(time.perf_counter_ns() - startup)
    if ready_raw is None:
        fail("readiness", reason)
    if ready_raw == "":
        fail("readiness", f"{reason} (exit {process.poll()})")
    try:
        ready = json.loads(ready_raw)
    except json.JSONDecodeError:
        fail("readiness", "ready line is not one complete JSON record")
    try:
        remainder, _stderr = process.communicate(timeout=complete_timeout)
    except subprocess.TimeoutExpired:
        fail("completion", f"no completion within {complete_timeout:g}s")
    if process.returncode != 0:
        raise RuntimeError("production Pi benchmark boundary failed")
    return startup_ms, ready, remainder


def _production_pi_samples(samples, cwd):
    """Measure the bundled production wrapBuiltins/BridgePort boundary."""
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node is required for the Pi adapter benchmark")
    esbuild = PI_TOOLS / "node_modules" / "esbuild" / "bin" / "esbuild"
    if not esbuild.is_file():
        raise RuntimeError("Pi benchmark requires the installed pinned esbuild")
    with tempfile.TemporaryDirectory(prefix="ca pi boundary π ") as raw:
        bundle = pathlib.Path(raw) / "boundary.mjs"
        built = subprocess.run(
            [node, str(esbuild), str(PI_BOUNDARY_SOURCE), "--bundle", "--format=esm",
             "--platform=node", "--target=node22", f"--outfile={bundle}"],
            cwd=PI_TOOLS, capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=False, timeout=30,
        )
        if built.returncode != 0:
            raise RuntimeError("production Pi benchmark boundary did not bundle")
        startup_ms, ready, remainder = _boundary_session(
            [node, str(bundle), str(samples)], cwd)
        try:
            document = json.loads(remainder)
        except json.JSONDecodeError as error:
            raise RuntimeError("production Pi benchmark completion record is malformed") from error
    if ready != {**ready, "phase": "ready"} or ready.get("wrapperCount") != 4:
        raise RuntimeError("production Pi benchmark readiness drifted")
    timings = document.get("timings")
    if not isinstance(timings, list) or len(timings) != REQUIRED_SAMPLES:
        raise RuntimeError("production Pi benchmark emitted an invalid sample set")
    expected_calls = REQUIRED_SAMPLES + WARMUP_EVENTS
    if document.get("phase") != "complete" or document.get("bridgeCallCount") != expected_calls or document.get("nativeCallCount") != expected_calls:
        raise RuntimeError("production Pi benchmark call inventory drifted")
    return startup_ms, [float(value) for value in timings]


def _measure_host(host_name, samples):
    if samples != REQUIRED_SAMPLES:
        raise ValueError("benchmark requires exactly 100 warm samples")
    with tempfile.TemporaryDirectory(prefix=f"ca pi benchmark {host_name} π ") as raw:
        repo = pathlib.Path(raw)
        state = repo / ".codearbiter"
        state.mkdir()
        (state / "CONTEXT.md").write_text(
            "---\narbiter: enabled\n---\n<!--INITIALIZED-->\n",
            encoding="utf-8",
            newline="\n",
        )
        (repo / "fixture π.txt").write_text("fixture\n", encoding="utf-8", newline="\n")

        startup_start = time.perf_counter_ns()
        host = None if host_name == "pi" else _load_host(host_name)
        core = _load_core(host_name)
        startup_ms = _round_ms(time.perf_counter_ns() - startup_start)

        corpus = canonical_corpus()
        adapter_values = []
        core_values = []
        total = WARMUP_EVENTS + samples
        for index in range(total):
            event = corpus[index % len(corpus)]
            if host_name != "pi":
                adapter_start = time.perf_counter_ns()
                _adapter_once(host_name, host, event)
                adapter_elapsed = time.perf_counter_ns() - adapter_start

            core_start = time.perf_counter_ns()
            active = core.arbiter_active(str(repo))
            core_elapsed = time.perf_counter_ns() - core_start
            if not active:
                raise RuntimeError("temporary benchmark repo did not remain enabled")
            if index >= WARMUP_EVENTS:
                if host_name != "pi":
                    adapter_values.append(_round_ms(adapter_elapsed))
                core_values.append(_round_ms(core_elapsed))

        if host_name == "pi":
            startup_ms, adapter_values = _production_pi_samples(samples, repo)

        adapter = summarize_samples(adapter_values)
        shared_core = summarize_samples(core_values)
        return {
            "platform": platform.system().lower(),
            "host": host_name,
            "sampleCount": samples,
            "startupMs": startup_ms,
            "coreP50Ms": shared_core["p50"],
            "adapterP50Ms": adapter["p50"],
            "adapterP95Ms": adapter["p95"],
        }


def run_benchmark(samples=REQUIRED_SAMPLES):
    return [_measure_host(host_name, samples) for host_name in ("claude", "codex", "pi")]


def _real_spawn_python_executable():
    """Locate a real, standalone Python interpreter for the REAL-SPAWN mode.

    Deliberately independent of sys.executable: the mode exists to measure the
    actual cost a host pays when it spawns `python <pi-bridge.py>` as a child
    process, so it resolves the interpreter the same way an external caller
    would (via PATH), and skips gracefully if none is resolvable there.
    """
    names = ("python3", "python") if platform.system().lower() != "windows" else ("py", "python")
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def real_spawn_benchmark(warmup=REAL_SPAWN_WARMUP, samples=REAL_SPAWN_SAMPLES):
    """Measure the REAL python spawn cost of the Pi per-call bridge path.

    Unlike _measure_host("pi", ...), which exercises only the bundled JS
    adapter boundary against a stubbed BridgePort, this drives the actual
    `python pi-bridge.py` child process BridgeClient spawns in production,
    round-tripping one cheap, read-only, idempotent route (tool_call/READ,
    routed to pre-read.py) against a temporary governed project fixture.
    """
    python = _real_spawn_python_executable()
    if python is None:
        return {
            "platform": platform.system().lower(),
            "host": "pi",
            "mode": "REAL-SPAWN-SKIPPED",
            "sampleCount": 0,
            "medianMs": None,
            "p95Ms": None,
        }
    if not PI_BRIDGE_SCRIPT.is_file():
        raise RuntimeError("pi-bridge.py is missing; cannot measure the real spawn path")

    with tempfile.TemporaryDirectory(prefix="ca pi real spawn π ") as raw:
        repo = pathlib.Path(raw)
        state = repo / ".codearbiter"
        state.mkdir()
        (state / "CONTEXT.md").write_text(
            "---\narbiter: enabled\n---\n<!--INITIALIZED-->\n",
            encoding="utf-8",
            newline="\n",
        )
        (repo / "fixture.txt").write_text("fixture\n", encoding="utf-8", newline="\n")

        request_body = json.dumps({
            "version": 1,
            "event": "tool_call",
            "cwd": str(repo),
            "tool": "read",
            "input": {"path": "fixture.txt"},
        }).encode("utf-8")

        timings = []
        for index in range(warmup + samples):
            start = time.perf_counter_ns()
            completed = subprocess.run(
                [python, str(PI_BRIDGE_SCRIPT)],
                input=request_body,
                capture_output=True,
                timeout=10,
                check=False,
            )
            elapsed = time.perf_counter_ns() - start
            if completed.returncode != 0:
                raise RuntimeError("real Pi bridge spawn failed: " + completed.stderr.decode("utf-8", "replace"))
            response = json.loads(completed.stdout.decode("utf-8"))
            if response.get("outcome") != "allow":
                raise RuntimeError("real Pi bridge spawn returned an unexpected outcome")
            if index >= warmup:
                timings.append(_round_ms(elapsed))

    return {
        "platform": platform.system().lower(),
        "host": "pi",
        "mode": "REAL-SPAWN",
        "sampleCount": len(timings),
        "medianMs": percentile(timings, 50),
        "p95Ms": percentile(timings, 95),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=REQUIRED_SAMPLES)
    parser.add_argument(
        "--real-spawn", action="store_true",
        help="Also measure the real python spawn cost of the Pi bridge (adds a REAL-SPAWN record).",
    )
    args = parser.parse_args()
    records = run_benchmark(args.samples)
    for record in records:
        if tuple(record) != PUBLIC_KEYS:
            raise RuntimeError("benchmark record shape drifted")
        print(json.dumps(record, ensure_ascii=True, separators=(",", ":"), sort_keys=False))
    by_host = {record["host"]: record for record in records}
    exit_code = 0 if benchmark_passes(
        by_host["pi"]["adapterP95Ms"],
        by_host["claude"]["adapterP95Ms"],
        by_host["codex"]["adapterP95Ms"],
    ) else 1

    if args.real_spawn:
        real_record = real_spawn_benchmark()
        if tuple(real_record) != REAL_SPAWN_PUBLIC_KEYS:
            raise RuntimeError("real-spawn benchmark record shape drifted")
        print(json.dumps(real_record, ensure_ascii=True, separators=(",", ":"), sort_keys=False))

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

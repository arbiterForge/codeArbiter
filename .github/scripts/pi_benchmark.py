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
        startup = time.perf_counter_ns()
        process = subprocess.Popen(
            [node, str(bundle), str(samples)], cwd=cwd, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
        )
        if process.stdout is None:
            raise RuntimeError("production Pi benchmark boundary has no protocol stream")
        ready_raw = process.stdout.readline()
        startup_ms = _round_ms(time.perf_counter_ns() - startup)
        ready = json.loads(ready_raw)
        remainder, _stderr = process.communicate(timeout=30)
        if process.returncode != 0:
            raise RuntimeError("production Pi benchmark boundary failed")
        document = json.loads(remainder)
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=REQUIRED_SAMPLES)
    args = parser.parse_args()
    records = run_benchmark(args.samples)
    for record in records:
        if tuple(record) != PUBLIC_KEYS:
            raise RuntimeError("benchmark record shape drifted")
        print(json.dumps(record, ensure_ascii=True, separators=(",", ":"), sort_keys=False))
    by_host = {record["host"]: record for record in records}
    return 0 if benchmark_passes(
        by_host["pi"]["adapterP95Ms"],
        by_host["claude"]["adapterP95Ms"],
        by_host["codex"]["adapterP95Ms"],
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())

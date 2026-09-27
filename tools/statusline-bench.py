#!/usr/bin/env python3
"""Deterministic statusline accounting benchmark (spec D-20 / AC-39).

Production runs the statusline as one fresh process per render, so this harness
does the same. Every render is one subprocess through a checkout's real entry point,
`plugins/ca/hooks/statusline.py`, with a JSON status payload on stdin. HOME, the
ledger and the transcript roots are redirected into a scratch tree, and the working
directory is a non-git scratch directory so the git probe does not add noise.

Structural counters are collected INSIDE that child process by this same script's
`--child` mode. That mode wraps `open`, `json.loads` and `os.replace`, then runs the
entry point with `runpy`. The identical harness therefore runs unchanged against the
base commit and the candidate.

Usage:
    python tools/statusline-bench.py run --checkout <repo> --out <report.json>
    python tools/statusline-bench.py compare <base.json> <head.json>

For each scenario the report records these phases:
    first        the first render (ungated: legitimately does the catch-up work)
    warmup       renders until ledger state stops changing (ungated)
    no_change    R identical renders
    host_only    renders whose only change is cost.total_cost_usd
    incremental  a fixed sequence of renders, each after appending new records

`compare` gates no_change, host_only and incremental on two things:
- every structural counter total must be <= base;
- the warm median and p95 wall time must be <= base * 1.05.
"""
import argparse
import builtins
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

TIMING_TOLERANCE = 1.05
# Ledger JSON embeds wall-clock float timestamps whose repr length varies by a few
# bytes run to run (measured: <=60 bytes on multi-MB totals across two identical
# base runs). Those byte counters get this relative slack; opens, replacements and
# transcript bytes are exactly repeatable and are compared exactly.
BYTE_NOISE = 0.001
NOISY_COUNTERS = ("ledger_bytes_read", "ledger_bytes_written", "json_decoded_bytes")
GATED_PHASES = ("no_change", "host_only", "incremental")
GATED_COUNTERS = ("opens", "transcript_bytes_read", "ledger_bytes_read",
                  "json_decoded_bytes", "ledger_bytes_written", "ledger_replacements")
NO_CHANGE_RENDERS = 15
HOST_ONLY_RENDERS = 5
INCREMENTAL_RENDERS = 10
MAX_WARMUP = 80
TS_BASE = "2026-09-27T10:{mm:02d}:{ss:02d}.{ms:03d}Z"


# --------------------------------------------------------------------------- child mode
def _child(entry):
    """Run one statusline render with I/O instrumentation; dump counters to
    $BENCH_COUNTERS. Never lets instrumentation failure change the render."""
    counters = dict.fromkeys(GATED_COUNTERS, 0)
    counters.update(other_bytes_read=0, listdirs=0)
    ledger_root = os.path.normcase(os.path.abspath(os.path.dirname(os.environ["CODEARBITER_LEDGER"])))
    tx_root = os.path.normcase(os.path.abspath(os.environ["BENCH_TX_ROOT"]))

    def kind(path):
        try:
            p = os.path.normcase(os.path.abspath(os.fspath(path)))
        except TypeError:
            return "other"
        if p.startswith(ledger_root + os.sep) or p == ledger_root:
            return "ledger"
        if p.startswith(tx_root + os.sep) and p.endswith(".jsonl"):
            return "transcript"
        return "other"

    class Counted:
        def __init__(self, f, k):
            self._f, self._k = f, k

        def _count_read(self, data):
            n = len(data) if data else 0
            if self._k == "transcript":
                counters["transcript_bytes_read"] += n
            elif self._k == "ledger":
                counters["ledger_bytes_read"] += n
            else:
                counters["other_bytes_read"] += n
            return data

        def read(self, *a):
            return self._count_read(self._f.read(*a))

        def readline(self, *a):
            return self._count_read(self._f.readline(*a))

        def readlines(self, *a):
            lines = self._f.readlines(*a)
            for ln in lines:
                self._count_read(ln)
            return lines

        def readinto(self, b):
            n = self._f.readinto(b)
            if n:
                self._count_read(b"\0" * n)
            return n

        def __iter__(self):
            for ln in self._f:
                yield self._count_read(ln)

        def write(self, s):
            if self._k == "ledger":
                counters["ledger_bytes_written"] += len(s)
            return self._f.write(s)

        def __enter__(self):
            self._f.__enter__()
            return self

        def __exit__(self, *a):
            return self._f.__exit__(*a)

        def __getattr__(self, name):
            return getattr(self._f, name)

    real_open = builtins.open

    def counted_open(file, *a, **k):
        f = real_open(file, *a, **k)
        if isinstance(file, int):
            return f
        counters["opens"] += 1
        return Counted(f, kind(file))

    real_loads = json.loads

    def counted_loads(s, *a, **k):
        try:
            counters["json_decoded_bytes"] += len(s)
        except TypeError:
            pass
        return real_loads(s, *a, **k)

    real_replace = os.replace

    def counted_replace(src, dst, *a, **k):
        if kind(dst) == "ledger":
            counters["ledger_replacements"] += 1
        return real_replace(src, dst, *a, **k)

    real_listdir, real_scandir = os.listdir, os.scandir

    def counted_listdir(*a, **k):
        counters["listdirs"] += 1
        return real_listdir(*a, **k)

    def counted_scandir(*a, **k):
        counters["listdirs"] += 1
        return real_scandir(*a, **k)

    builtins.open = counted_open
    json.loads = counted_loads
    os.replace = counted_replace
    os.listdir = counted_listdir
    os.scandir = counted_scandir
    sys.path.insert(0, os.path.dirname(os.path.abspath(entry)))
    sys.argv = [entry]
    import runpy
    try:
        runpy.run_path(entry, run_name="__main__")
    except SystemExit:
        pass
    finally:
        builtins.open = real_open
        with real_open(os.environ["BENCH_COUNTERS"], "w", encoding="utf-8") as f:
            json.dump(counters, f)


# --------------------------------------------------------------------------- fixtures
def _ts(i):
    i = i % (60 * 60 * 1000)
    return TS_BASE.format(mm=(i // 60000) % 60, ss=(i // 1000) % 60, ms=i % 1000)


def _assistant(rid, i, out, model, sidechain=False):
    return {"type": "assistant", "timestamp": _ts(i), "isSidechain": sidechain,
            "requestId": f"req_bench_{rid}", "uuid": f"u-{rid}-{out}",
            "message": {"id": f"msg_bench_{rid}", "role": "assistant", "model": model,
                        "type": "message",
                        "content": [{"type": "text", "text": "x" * 120}],
                        "usage": {"input_tokens": 3, "output_tokens": out,
                                  "cache_read_input_tokens": 40000 + i,
                                  "cache_creation_input_tokens": 900,
                                  "cache_creation": {"ephemeral_5m_input_tokens": 0,
                                                     "ephemeral_1h_input_tokens": 900},
                                  "service_tier": "standard",
                                  "inference_geo": "not_available", "speed": "standard"}}}


def _user(rid, i, text):
    return {"type": "user", "timestamp": _ts(i), "uuid": f"uu-{rid}",
            "message": {"role": "user", "content": text}}


def _request_lines(prefix, n, model, sidechain=False):
    """One request = a user line + two streaming representations (partial, final)."""
    for k in range(n):
        rid = f"{prefix}{k}"
        yield _user(rid, k, "please continue the task " + "y" * 400)
        yield _assistant(rid, k, 2, model, sidechain)
        yield _assistant(rid, k, 300 + k % 50, model, sidechain)


def _write_jsonl(path, records, mode="w"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode, encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")


SCENARIOS = [
    # name, parent requests, children, requests per child
    ("p10k_c0", 10000, 0, 0),
    ("p1k_c0", 1000, 0, 0),
    ("p1k_c1", 1000, 1, 40),
    ("p1k_c12", 1000, 12, 40),
    ("p1k_c13", 1000, 13, 40),
    ("p1k_c64", 1000, 64, 40),
]


# --------------------------------------------------------------------------- parent mode
def _ledger_state(ledger_dir):
    out = []
    for base, _dirs, names in os.walk(ledger_dir):
        for n in names:
            p = os.path.join(base, n)
            try:
                st = os.stat(p)
            except OSError:
                continue
            out.append((p, st.st_size, st.st_mtime_ns))
    return sorted(out)


def _render(entry, env, cwd, payload, counters_path):
    env = dict(env, BENCH_COUNTERS=counters_path)
    t0 = time.perf_counter()
    proc = subprocess.run([sys.executable, os.path.abspath(__file__), "child", entry],
                          input=json.dumps(payload).encode("utf-8"), env=env, cwd=cwd,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    elapsed = (time.perf_counter() - t0) * 1000.0
    if proc.returncode != 0 or proc.stderr.strip():
        raise RuntimeError(f"render failed rc={proc.returncode}: {proc.stderr.decode()[-800:]}")
    with open(counters_path, encoding="utf-8") as f:
        counters = json.load(f)
    return elapsed, counters, proc.stdout


def _phase(results):
    times = [t for t, _c in results]
    totals = {}
    for _t, c in results:
        for k, v in c.items():
            totals[k] = totals.get(k, 0) + v
    ordered = sorted(times)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return {"renders": len(results), "totals": totals,
            "median_ms": statistics.median(times), "p95_ms": p95}


def run_scenario(entry, name, parent_n, children, child_n):
    scratch = tempfile.mkdtemp(prefix=f"ca-bench-{name}-")
    try:
        home = os.path.join(scratch, "home")
        work = os.path.join(scratch, "work")
        os.makedirs(work)
        projects = os.path.join(home, ".claude", "projects", "bench-project")
        sid = "0b0b0b0b-bench-4000-8000-" + name.replace("_", "")[:12].ljust(12, "0")
        parent = os.path.join(projects, f"{sid}.jsonl")
        _write_jsonl(parent, _request_lines("p", parent_n, "claude-opus-5-5"))
        sub = os.path.join(projects, sid, "subagents")
        for c in range(children):
            _write_jsonl(os.path.join(sub, f"agent-bench{c:03d}.jsonl"),
                         _request_lines(f"c{c}_", child_n, "claude-sonnet-5", sidechain=True))
        ledger = os.path.join(home, ".codearbiter", "ledger.json")
        env = {k: v for k, v in os.environ.items()
               if k not in ("NO_COLOR", "CODEARBITER_STATUSLINE", "COLUMNS")}
        env.update(HOME=home, USERPROFILE=home, CODEARBITER_LEDGER=ledger,
                   CODEARBITER_UPDATE_STATE=os.path.join(scratch, "no-update-state.json"),
                   BENCH_TX_ROOT=projects, NO_COLOR="1", COLUMNS="120",
                   PYTHONDONTWRITEBYTECODE="1")
        counters_path = os.path.join(scratch, "counters.json")

        def payload(cost):
            return {"session_id": sid, "transcript_path": parent, "cwd": work,
                    "workspace": {"current_dir": work},
                    "model": {"id": "claude-opus-5-5", "display_name": "Opus 5.5"},
                    "cost": {"total_cost_usd": cost}}

        report = {}
        report["first"] = _phase([_render(entry, env, work, payload(1.0), counters_path)[:2]])
        warm, prev = [], _ledger_state(os.path.dirname(ledger))
        for _ in range(MAX_WARMUP):
            warm.append(_render(entry, env, work, payload(1.0), counters_path)[:2])
            cur = _ledger_state(os.path.dirname(ledger))
            if cur == prev:
                break
            prev = cur
        report["warmup"] = _phase(warm)
        report["no_change"] = _phase([_render(entry, env, work, payload(1.0), counters_path)[:2]
                                      for _ in range(NO_CHANGE_RENDERS)])
        report["host_only"] = _phase([_render(entry, env, work, payload(1.0 + (i + 1) * 0.25),
                                              counters_path)[:2]
                                      for i in range(HOST_ONLY_RENDERS)])
        final_cost = 1.0 + HOST_ONLY_RENDERS * 0.25
        inc = []
        for i in range(INCREMENTAL_RENDERS):
            _write_jsonl(parent, _request_lines(f"pi{i}_", 3, "claude-opus-5-5"), mode="a")
            if children and i % 2 == 0:
                _write_jsonl(os.path.join(sub, "agent-bench000.jsonl"),
                             _request_lines(f"ci{i}_", 2, "claude-sonnet-5", True), mode="a")
            inc.append(_render(entry, env, work, payload(final_cost), counters_path)[:2])
        report["incremental"] = _phase(inc)
        return report
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def cmd_run(args):
    checkout = os.path.abspath(args.checkout)
    entry = os.path.join(checkout, "plugins", "ca", "hooks", "statusline.py")
    if not os.path.isfile(entry):
        sys.exit(f"no statusline entry point at {entry}")
    rev = subprocess.run(["git", "-C", checkout, "rev-parse", "HEAD"],
                         stdout=subprocess.PIPE, text=True).stdout.strip()
    wanted = set(args.scenario or [])
    out = {"schema": "codearbiter.statusline-bench/v1", "checkout_rev": rev,
           "python": sys.version.split()[0], "platform": platform.platform(),
           "captured": time.strftime("%Y-%m-%dT%H:%M:%S"), "scenarios": {}}
    for name, pn, ch, cn in SCENARIOS:
        if wanted and name not in wanted:
            continue
        print(f"[bench] {name} ...", file=sys.stderr, flush=True)
        out["scenarios"][name] = run_scenario(entry, name, pn, ch, cn)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=2, sort_keys=True)
        f.write("\n")
    print(args.out)


def cmd_compare(args):
    with open(args.base, encoding="utf-8") as f:
        base = json.load(f)
    with open(args.head, encoding="utf-8") as f:
        head = json.load(f)
    failures = []
    rows = []
    for name, bs in sorted(base["scenarios"].items()):
        hs = head["scenarios"].get(name)
        if hs is None:
            failures.append(f"{name}: missing from head")
            continue
        for phase in GATED_PHASES:
            b, h = bs[phase], hs[phase]
            for c in GATED_COUNTERS:
                bv, hv = b["totals"].get(c, 0), h["totals"].get(c, 0)
                rows.append((name, phase, c, bv, hv))
                allowed = bv * (1 + BYTE_NOISE) if c in NOISY_COUNTERS else bv
                if hv > allowed:
                    failures.append(f"{name}/{phase}: {c} head {hv} > base {bv}")
            for t in ("median_ms", "p95_ms"):
                rows.append((name, phase, t, round(b[t], 1), round(h[t], 1)))
                if not args.structural_only and h[t] > b[t] * TIMING_TOLERANCE:
                    failures.append(f"{name}/{phase}: {t} head {h[t]:.1f} > base {b[t]:.1f} x{TIMING_TOLERANCE}")
    width = max(len(r[2]) for r in rows) if rows else 10
    for name, phase, c, bv, hv in rows:
        print(f"{name:10} {phase:12} {c:{width}} base={bv:>14} head={hv:>14}")
    if failures:
        print("\nFAIL:\n  " + "\n  ".join(failures))
        return 1
    print("\nPASS: head <= base on every gated structural counter"
          + ("" if args.structural_only else f" and timing within x{TIMING_TOLERANCE}"))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--checkout", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--scenario", action="append")
    c = sub.add_parser("compare")
    c.add_argument("base")
    c.add_argument("head")
    c.add_argument("--structural-only", action="store_true")
    ch = sub.add_parser("child")
    ch.add_argument("entry")
    args = ap.parse_args(argv)
    if args.cmd == "child":
        _child(args.entry)
        return 0
    if args.cmd == "run":
        cmd_run(args)
        return 0
    return cmd_compare(args)


if __name__ == "__main__":
    sys.exit(main())

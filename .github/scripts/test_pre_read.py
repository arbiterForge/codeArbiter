#!/usr/bin/env python3
# codeArbiter — subprocess integration tests for plugins/ca/hooks/pre-read.py (T-11).
#
# Drives the hook as a subprocess with controlled stdin and a throwaway project
# root. Mirrors the harness pattern from test_hook_guards.py. Uses
# tempfile.TemporaryDirectory() for the project root; NEVER writes under the real
# repo. The suite is designed to pass twice back-to-back with no stray files.
#
# Obligations covered (spec: file-scoped-context-injection.md):
#   AC-03  governed file -> JSON allow output with non-empty additionalContext
#   AC-09  dedup: same (session, file) -> first injects, second silent
#   AC-10  .codearbiter/ self-read -> exit 0, NO stdout (silent allow)
#   AC-12  fail-open: malformed stdin -> exit 0, no stdout, no traceback on stdout
#   done   miss: non-governed file -> exit 0, NO stdout
#   done   dormant: repo without arbiter: enabled -> exit 0, no stdout
#
# Stdlib only. Exit 0 = all assertions pass; non-zero = failure.

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOOKS = os.path.join(REPO, "plugins", "ca", "hooks")
PRE_READ = os.path.join(HOOKS, "pre-read.py")

failures = []
checks = 0


def sh(args, cwd, stdin_text="", **kw):
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60,
        input=stdin_text, **kw
    )


def git(args, cwd):
    r = sh(["git"] + args, cwd)
    if r.returncode != 0:
        sys.exit("FATAL: git {} failed in fixture: {}".format(
            " ".join(args), r.stderr.strip()
        ))
    return r


def run_hook(root, payload_dict):
    """Run pre-read.py with a JSON stdin payload; cwd resolves project_root()."""
    payload = json.dumps(payload_dict)
    return sh([sys.executable, PRE_READ], root, stdin_text=payload)


def check(cond, label, detail):
    global checks
    checks += 1
    if cond:
        return
    failures.append("FAIL [{}] {}".format(label, detail))
    print(failures[-1])


def make_root(base, name, arbiter_enabled=True):
    """Create a throwaway git repo for pre-read.py tests.

    Layout:
      .codearbiter/CONTEXT.md       — arbiter: enabled (or absent)
      .codearbiter/decisions/
        0001-test.md                — accepted ADR, governs: src/governed.py
      src/governed.py               — matched by the ADR glob
      src/ungoverned.py             — not matched by any ADR or spec
    """
    root = os.path.join(base, name)
    os.makedirs(root)
    git(["init", "-q", "-b", "main", root], base)
    git(["config", "user.email", "harness@example.com"], root)
    git(["config", "user.name", "harness"], root)

    ca = os.path.join(root, ".codearbiter")
    os.makedirs(os.path.join(ca, "decisions"), exist_ok=True)

    if arbiter_enabled:
        ctx_text = "---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n"
    else:
        ctx_text = "# Not enabled\n"
    with open(
        os.path.join(ca, "CONTEXT.md"), "w", encoding="utf-8", newline="\n"
    ) as fh:
        fh.write(ctx_text)

    # Accepted ADR governing src/governed.py — must satisfy accepted_adr_index():
    #   status == "accepted" AND governs: field present and non-empty.
    adr_text = (
        "---\n"
        "title: Test ADR\n"
        "status: accepted\n"
        "governs: src/governed.py\n"
        "---\n"
        "# ADR-0001\n"
        "Test decision body.\n"
    )
    with open(
        os.path.join(ca, "decisions", "0001-test.md"), "w",
        encoding="utf-8", newline="\n",
    ) as fh:
        fh.write(adr_text)

    os.makedirs(os.path.join(root, "src"), exist_ok=True)
    for fname in ("governed.py", "ungoverned.py"):
        with open(
            os.path.join(root, "src", fname), "w", encoding="utf-8", newline="\n"
        ) as fh:
            fh.write("# fixture\n")

    return root


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    with tempfile.TemporaryDirectory(prefix="ca-preread-") as base:
        root = make_root(base, "active-root")
        governed_abs = os.path.join(root, "src", "governed.py")
        ungoverned_abs = os.path.join(root, "src", "ungoverned.py")
        self_read_abs = os.path.join(root, ".codearbiter", "CONTEXT.md")

        # ------------------------------------------------------------------
        # AC-03 inject: a governed file path -> JSON allow + non-empty context
        # ------------------------------------------------------------------
        r = run_hook(root, {
            "session_id": "session-ac03",
            "tool_name": "Read",
            "tool_input": {"file_path": governed_abs},
        })
        check(
            r.returncode == 0,
            "AC-03 exit",
            "expected exit 0, got {}".format(r.returncode),
        )
        stdout = r.stdout.strip()
        check(
            bool(stdout),
            "AC-03 stdout-nonempty",
            "expected JSON on stdout; got empty string",
        )
        try:
            out = json.loads(stdout)
            hso = out.get("hookSpecificOutput", {})
            check(
                hso.get("hookEventName") == "PreToolUse",
                "AC-03 hookEventName",
                "expected 'PreToolUse', got {!r}".format(hso.get("hookEventName")),
            )
            check(
                hso.get("permissionDecision") == "allow",
                "AC-03 permissionDecision",
                "expected 'allow', got {!r}".format(hso.get("permissionDecision")),
            )
            check(
                bool(hso.get("additionalContext", "")),
                "AC-03 additionalContext",
                "additionalContext was empty or missing; hso={!r}".format(hso),
            )
        except Exception as exc:  # noqa: BLE001
            check(
                False, "AC-03 json-parse",
                "stdout not valid JSON: {!r}; stdout={!r}".format(exc, stdout),
            )

        # ------------------------------------------------------------------
        # AC-10 self-read: file under .codearbiter/ -> exit 0, NO stdout
        # ------------------------------------------------------------------
        r = run_hook(root, {
            "session_id": "session-selfread",
            "tool_name": "Read",
            "tool_input": {"file_path": self_read_abs},
        })
        check(
            r.returncode == 0,
            "AC-10 exit",
            "expected exit 0, got {}".format(r.returncode),
        )
        check(
            r.stdout.strip() == "",
            "AC-10 silent",
            "expected no stdout on self-read, got {!r}".format(r.stdout),
        )

        # ------------------------------------------------------------------
        # Miss (Done-looks-like): non-governed file -> exit 0, NO stdout
        # ------------------------------------------------------------------
        r = run_hook(root, {
            "session_id": "session-miss",
            "tool_name": "Read",
            "tool_input": {"file_path": ungoverned_abs},
        })
        check(
            r.returncode == 0,
            "miss exit",
            "expected exit 0, got {}".format(r.returncode),
        )
        check(
            r.stdout.strip() == "",
            "miss silent",
            "expected no stdout on miss, got {!r}".format(r.stdout),
        )

        # ------------------------------------------------------------------
        # Dedup (AC-09): same (session_id, file_path) twice.
        # First run emits JSON; second run is silent (marker suppresses).
        # Uses the same temp root + session_id across both subprocess calls
        # so the marker written by the first call persists for the second.
        # ------------------------------------------------------------------
        dedup_session = "session-dedup-xyz"
        dedup_payload = {
            "session_id": dedup_session,
            "tool_name": "Read",
            "tool_input": {"file_path": governed_abs},
        }
        r1 = run_hook(root, dedup_payload)
        r2 = run_hook(root, dedup_payload)

        check(
            r1.returncode == 0,
            "AC-09 r1-exit",
            "expected exit 0 on first call, got {}".format(r1.returncode),
        )
        check(
            r2.returncode == 0,
            "AC-09 r2-exit",
            "expected exit 0 on second call, got {}".format(r2.returncode),
        )
        check(
            bool(r1.stdout.strip()),
            "AC-09 first-emits",
            "first Read should emit JSON; stdout was empty. "
            "stderr={!r}".format(r1.stderr),
        )
        check(
            r2.stdout.strip() == "",
            "AC-09 dedup-silent",
            "second Read should be silent after dedup marker; "
            "got {!r}".format(r2.stdout),
        )

        # ------------------------------------------------------------------
        # Dormant: root WITHOUT arbiter: enabled -> exit 0, no stdout
        # ------------------------------------------------------------------
        dormant_root = make_root(base, "dormant-root", arbiter_enabled=False)
        r = run_hook(dormant_root, {
            "session_id": "session-dormant",
            "tool_name": "Read",
            "tool_input": {
                "file_path": os.path.join(dormant_root, "src", "governed.py"),
            },
        })
        check(
            r.returncode == 0,
            "dormant exit",
            "expected exit 0, got {}".format(r.returncode),
        )
        check(
            r.stdout.strip() == "",
            "dormant silent",
            "expected no stdout in dormant mode, got {!r}".format(r.stdout),
        )

        # ------------------------------------------------------------------
        # Fail-open (AC-12): malformed stdin -> exit 0, no stdout, no traceback
        # ------------------------------------------------------------------
        r = sh([sys.executable, PRE_READ], root, stdin_text="NOT JSON {{{")
        check(
            r.returncode == 0,
            "fail-open exit",
            "expected exit 0 on malformed stdin, got {}".format(r.returncode),
        )
        check(
            r.stdout.strip() == "",
            "fail-open silent",
            "expected no stdout on malformed stdin, got {!r}".format(r.stdout),
        )
        check(
            "Traceback" not in r.stdout,
            "fail-open no-traceback-stdout",
            "traceback found on stdout",
        )

    # TemporaryDirectory context manager cleans up here — no stray files.

    print("\n{} checks, {} failed".format(checks, len(failures)))
    if failures:
        print("FAIL: test_pre_read.py had failures")
        sys.exit(1)
    print("test_pre_read.py: PASS")


if __name__ == "__main__":
    main()

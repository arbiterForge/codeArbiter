#!/usr/bin/env python3
# codeArbiter — first-run scaffolder. Creates the root-level .codearbiter/ project
# state directory that opts a repo into arbiter management. Idempotent: it never
# overwrites a file that already exists, so it is safe to re-run.
#
# The `arbiter: enabled` frontmatter in CONTEXT.md is the single activation flag —
# it gates both the SessionStart persona injection and the arbiter statusline
# segments. CONTEXT.md is scaffolded WITHOUT the <!--INITIALIZED--> body sentinel,
# so the next session routes to /ca:create-context (source exists) or /ca:decompose
# (greenfield) to populate it.
#
# Usage:
#   python init-codearbiter.py [--root PATH] [--stage N]
#   python init-codearbiter.py --check        # report state, create nothing
#   python init-codearbiter.py --check --passive --root PATH  # external pre-session read
#   python init-codearbiter.py --repair-lock-exclusion [--root PATH]
#   python init-codearbiter.py --root PATH --context-request FILE  # bounded writer bridge, including initialized refresh

import argparse
import json
import subprocess
import os
import re
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gitexec import git_executable, root_bound_git_env  # noqa: E402
from _taskboardlib import DONE_TASKS  # noqa: E402 — shared archive template (#625)
import hostapi  # noqa: E402 — host seam (ADR-0011)
import _hooklib  # noqa: E402 — set_host DI seam (#257)
import _entrylib  # noqa: E402 — shared run() dispatch (jscpd dedup)
from _activationlib import passive_activation_inventory  # noqa: E402
import _artifactlib  # noqa: E402

# NOTE: this stub deliberately does NOT contain the initialization sentinel
# (an HTML comment wrapping the word INITIALIZED). The SessionStart hook greps
# for that exact token to decide whether the project is populated, so emitting it
# here — even inside a comment — would falsely mark an empty stub as initialized.
# The populator flow (/ca:create-context or /ca:decompose) adds it on its own line.
CONTEXT = """\
---
arbiter: enabled
stage: {stage}
---

# Project: {name}

<!-- This .codearbiter/ directory is the root-level project-state store. It lives
outside .claude/ so it survives even if the codeArbiter plugin is uninstalled.
The `arbiter: enabled` frontmatter above is the activation flag.

This CONTEXT.md is a stub: it carries no initialization sentinel yet, so the
orchestrator routes you to {create_context} (if source already exists) or
{decompose} (greenfield) to populate the real project context. That flow writes
the sentinel and normal operation begins. -->

_Not yet initialized. Run {create_context} or {decompose} to populate._
"""

OPEN_TASKS = """\
# Open tasks

In-flight and queued work. One top-level `- ` bullet per task; the statusline and
SessionStart hook count these, EXCLUDING done (`- [x]`).

Schema (one task = a lifecycle line + indented content sub-bullets):

```
- [~] poc.auth.0001 - Validate session tokens  (started 2026-06-18)
  - Desc: reject expired/forged tokens at the auth middleware
  - Done when: an expired token returns 401; a valid one passes
  - Boundaries: auth, secrets
```

- Marker: `[ ]` queued | `[~]` in-progress | `[x]` done. In-progress and done
  carry a dated `(started YYYY-MM-DD)` / `(done YYYY-MM-DD)` parenthetical; a
  stale `[~]` is surfaced at SessionStart.
- ID `<group>.<type>.<seq>`: `group` = build phase (poc/mvp1/v1...), `type` =
  domain (auth/api/ui/infra...), `seq` = >=4-digit, numbered within each
  `group.type`. ID + title + marker are required.
- `Desc` / `Done when` / `Boundaries` are filled when known (`TBD` until then).
  Keep `Done when` to one coarse sentence — per-step verification belongs to a
  plan, not here. `Boundaries` names the security/trust boundary the task is
  expected to touch (auth, crypto, secrets, ...).
"""

OPEN_QUESTIONS = """\
# Open questions

Unresolved `[CONFIRM-NN]` items. Each blocks dependent work until resolved.
The SessionStart hook and statusline count `CONFIRM-NN` occurrences here.

_None open._
"""

OVERRIDES = """\
# codeArbiter override log - append-only audit artifact. Never edit or delete prior lines.
# Format: [ISO-8601] | BY: <name> <<email>> | GATE: <gate bypassed> | REASON: <reason>
# Written only by /override. The statusline counts non-comment lines after the
# last-checkpoint marker as "overrides since last checkpoint."
"""

FILES = {
    "open-tasks.md": OPEN_TASKS,
    # B-23: scaffolded at init rather than created on first archive. An
    # append-only file that springs into existence mid-sweep has no
    # reviewed initial content and no header explaining what it is — and
    # `archive`'s first write would be the thing that defines the format.
    "done-tasks.md": DONE_TASKS,
    "open-questions.md": OPEN_QUESTIONS,
    "overrides.log": OVERRIDES,
    "last-checkpoint": "0\n",
}


def project_root(opt):
    if opt:
        return os.path.abspath(opt)
    # prefer git toplevel; fall back to cwd
    try:
        out = subprocess.run([git_executable(), "rev-parse", "--show-toplevel"],
                             env=root_bound_git_env(), capture_output=True, text=True, timeout=2)
        top = out.stdout.strip()
        if out.returncode == 0 and top:
            return os.path.abspath(top)
    except Exception:
        pass
    return os.path.abspath(os.getcwd())


def _regular_scaffold_entry(path, *, directory):
    """Reject aliases and reparse points before reading or creating scaffold state."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    reparse = getattr(info, "st_file_attributes", 0) & getattr(
        stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return not reparse and (stat.S_ISDIR(info.st_mode) if directory
                            else stat.S_ISREG(info.st_mode))


def _scaffold_inventory(cad, ctx, requested_stage):
    """Return absent scaffold names only when surviving state is safe to retain."""
    names = ("CONTEXT.md", *FILES)
    if os.path.lexists(cad) and not _regular_scaffold_entry(cad, directory=True):
        raise SystemExit(f"REFUSING: {cad} is not a regular project-state directory.")
    present = {name for name in names if os.path.lexists(os.path.join(cad, name))}
    if not present:
        if os.path.isdir(cad) and os.listdir(cad):
            raise SystemExit(f"REFUSING: {cad} has existing state without a scaffold; inspect it first.")
        return list(names), False
    for name in present:
        path = os.path.join(cad, name)
        if not _regular_scaffold_entry(path, directory=False):
            raise SystemExit(f"REFUSING: {path} is not a regular scaffold file.")
    if "CONTEXT.md" not in present:
        # A missing stub amid content/provenance may be an interrupted native
        # transaction. Only the known scaffold prefix can be resumed here.
        unexpected = set(os.listdir(cad)) - set(FILES)
        if unexpected:
            raise SystemExit(f"REFUSING: {ctx} is absent amid other project state; inspect prior write outcome.")
    else:
        try:
            with open(ctx, encoding="utf-8") as handle:
                body = handle.read()
        except (OSError, UnicodeError) as exc:
            raise SystemExit(f"REFUSING: cannot inspect {ctx}: {exc}") from None
        enabled, malformed = _hooklib.frontmatter_enabled_text(body)
        lines = body.splitlines()
        boundary = next((index for index, line in enumerate(lines[1:], 1)
                         if line.strip() == "---"), None)
        stages = ([match.group(1) for line in lines[1:boundary]
                   if (match := re.fullmatch(r"\s*stage:\s*([1-9][0-9]*)\s*", line))]
                  if boundary is not None else [])
        if (not enabled or malformed or len(stages) != 1 or
                _hooklib.initialized_body_text(body)):
            raise SystemExit(f"REFUSING: {ctx} is invalid or initialized; inspect before recovery.")
        if requested_stage is not None and int(stages[0]) != requested_stage:
            raise SystemExit(f"REFUSING: {ctx} stage differs from --stage; preserve existing context.")
    headers = {"open-tasks.md": "# Open tasks", "done-tasks.md": "# Done tasks",
               "open-questions.md": "# Open questions",
               "overrides.log": "# codeArbiter override log"}
    for name in present & headers.keys():
        path = os.path.join(cad, name)
        try:
            with open(path, encoding="utf-8") as handle:
                valid = handle.readline().rstrip("\r\n").startswith(headers[name])
        except (OSError, UnicodeError):
            valid = False
        if not valid:
            raise SystemExit(f"REFUSING: {path} has an unrecognized header; preserve it for review.")
    if "last-checkpoint" in present:
        try:
            with open(os.path.join(cad, "last-checkpoint"), encoding="utf-8") as handle:
                valid = bool(re.fullmatch(r"[0-9]+\s*", handle.read()))
        except (OSError, UnicodeError):
            valid = False
        if not valid:
            raise SystemExit("REFUSING: last-checkpoint is malformed; preserve it for review.")
    return [name for name in names if name not in present], True


def _create_scaffold_file(path, content, *, newline=None):
    """Create once; a concurrent new file is a conflict, never an overwrite."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o666)
    except FileExistsError:
        raise SystemExit(f"REFUSING: {path} appeared during scaffold recovery.") from None
    with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as handle:
        handle.write(content)


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--root")
    ap.add_argument("--stage", type=int)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--passive", action="store_true", help=(
        "inspect explicit root before host activation; no Git or network probes"))
    ap.add_argument("--context-request", help=argparse.SUPPRESS)
    ap.add_argument("--repair-lock-exclusion", action="store_true", help=(
        "repair only Git-local info/exclude for an existing scaffold; retain the "
        "task-board OS lock, never rewrite project state (cannot combine with --check/--stage)"))
    args = ap.parse_args(argv)
    if args.context_request:
        if not args.root or args.stage is not None or args.check or args.passive or args.repair_lock_exclusion:
            ap.error("--context-request requires --root and excludes scaffold flags")
        try:
            root = _artifactlib._trusted_directory(args.root, "UNSAFE_ROOT")
            request = _artifactlib.read_context_preview_request(root, args.context_request)
            operation, payload = _artifactlib.validate_context_writer_request(request)
            client = _artifactlib.context_writer_client(root)
            if operation == "preview":
                from _artifactauthoritylib import arm_context_preview
                result = arm_context_preview(root, client, payload)
            else:
                result = client.call("context-apply", payload)
        except RuntimeError as exc:
            raise SystemExit(f"REFUSING context request: {exc}") from None
        print(json.dumps(result, sort_keys=True))
        return
    if args.passive:
        if not args.check or not args.root or args.stage is not None or args.repair_lock_exclusion:
            ap.error("--passive requires --check and --root; excludes --stage and repair")
        try:
            report = passive_activation_inventory(args.root)
        except (OSError, UnicodeError, ValueError) as exc:
            raise SystemExit(f"REFUSING passive inspection: {exc}") from None
        print(json.dumps(report, sort_keys=True))
        return
    if args.repair_lock_exclusion and (args.check or args.stage is not None):
        ap.error("--repair-lock-exclusion cannot combine with --check or --stage")
    requested_stage = args.stage
    if args.stage is None:
        args.stage = 1

    root = project_root(args.root)
    cad = os.path.join(root, ".codearbiter")
    ctx = os.path.join(cad, "CONTEXT.md")
    # Host-native command spellings for every populate pointer this scaffold
    # emits or writes into the stub (codex-support M3): the same text must
    # read /ca:create-context under Claude Code and $ca-create-context under
    # Codex, or the very first thing a Codex-only user sees is a dead pointer.
    _host = _hooklib.get_host()
    _cc = _host.cmd_ref("create-context")
    _dc = _host.cmd_ref("decompose")
    name = os.path.basename(root.rstrip("/\\")) or "project"

    if args.check:
        if os.path.lexists(cad) and not _regular_scaffold_entry(cad, directory=True):
            raise SystemExit(f"REFUSING: {cad} is not a regular project-state directory.")
        if os.path.lexists(ctx) and not _regular_scaffold_entry(ctx, directory=False):
            raise SystemExit(f"REFUSING: {ctx} is not a regular scaffold file.")
        if os.path.exists(ctx):
            print(f"ALREADY SCAFFOLDED: {ctx} exists.")
            with open(ctx, encoding="utf-8", errors="replace") as f:
                text = f.read()
            initd = _hooklib.initialized_body_text(text)
            enabled, _malformed = _hooklib.frontmatter_enabled_text(text)
            print("arbiter: " + ("enabled" if enabled else "not enabled"))
            print("initialized body: " + ("yes" if initd else
                  "no (run " + _cc + " or " + _dc + ")"))
        else:
            print(f"NOT SCAFFOLDED: {cad} would be created. Run without --check to scaffold.")
        return

    from _taskexcludelib import ensure_task_lock_excluded, TaskExclusionError
    if args.repair_lock_exclusion:
        if (not _regular_scaffold_entry(cad, directory=True) or
                not _regular_scaffold_entry(ctx, directory=False)):
            raise SystemExit("REFUSING: task lock exclusion repair requires an existing scaffold.")
        try:
            result = ensure_task_lock_excluded(root, required=True)
        except TaskExclusionError as exc:
            raise SystemExit(f"REFUSING: {exc}") from None
        print(f"task lock exclusion: {result}")
        return

    absent, recovering = _scaffold_inventory(cad, ctx, requested_stage)
    if recovering and not absent:
        raise SystemExit(
            f"REFUSING: {ctx} already exists. .codearbiter/ is already scaffolded here. "
            f"To populate it, run {_cc} or {_dc}; to repair, edit by hand.")

    try:
        result = ensure_task_lock_excluded(root)
    except TaskExclusionError as exc:
        raise SystemExit(f"REFUSING: {exc}") from None
    if result:
        print(f"task lock exclusion: {result}")

    os.makedirs(cad, exist_ok=True)
    created = []
    if "CONTEXT.md" in absent:
        _create_scaffold_file(ctx, CONTEXT.format(stage=args.stage, name=name,
                              create_context=_cc, decompose=_dc))
        created.append("CONTEXT.md")
    for fname, content in FILES.items():
        if fname in absent:
            # Match taskwrite's LF output for this shared append-only template
            # on Windows too; other scaffold files retain their existing EOLs.
            newline = "\n" if fname == "done-tasks.md" else None
            _create_scaffold_file(os.path.join(cad, fname), content, newline=newline)
            created.append(fname)

    # #161: install the git-level enforcement backstop (pre-commit/pre-push) so
    # git mutations are gated at the operation itself, not only at the literal
    # Bash command string. Best-effort — a repo without a git dir, or a foreign
    # existing hook, is reported by install(), never fatal to scaffolding.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _githooks import install as _install_git_hooks
        gh = _install_git_hooks(root)
        if gh:
            print("git hooks: " + ", ".join(gh))
    except Exception as e:  # noqa: BLE001
        print(f"git hooks: install skipped ({e})", file=sys.stderr)

    print(f"{'RECOVERED' if recovering else 'SCAFFOLDED'} .codearbiter/ at {cad}")
    print("created: " + ", ".join(created))
    if recovering and "CONTEXT.md" not in created:
        print("arbiter: enabled; existing uninitialized CONTEXT.md and history retained.")
    else:
        print(f"arbiter: enabled (stage {args.stage}); CONTEXT.md is a stub (no <!--INITIALIZED--> sentinel).")
    print(f"Next: run {_cc} (source exists) or {_dc} (greenfield) to populate.")


def run(host, argv=None):
    """Host-seam entry point (ADR-0011): the __main__ guard calls this with the
    plugin's loaded Host. Wraps main(argv) unchanged — main()'s return value
    stays discarded exactly as the old bare `main()` guard discarded it (so
    the process still exits 0 on a normal fall-through).

    Wires `host` live (#257): primes `_hooklib`'s process-cached Host via
    `set_host()` BEFORE main() runs, so any `get_host()` call downstream
    resolves to the SAME instance the caller passed here — no second
    `hostapi.load_host()`, and `run(fake_host)` genuinely exercises
    `fake_host`."""
    return _entrylib.dispatch(host, argv, main, _hooklib.set_host,
                               pass_argv=True, propagate_result=False)


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)

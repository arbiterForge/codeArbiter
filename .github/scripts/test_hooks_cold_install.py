#!/usr/bin/env python3
"""codeArbiter MR-10 / ADR-0011 infra-002 — cold-install interpreter matrix
for the hook layer, exercised against BOTH host plugins: `ca` (Claude Code)
and `ca-codex` (OpenAI Codex CLI).

Every enforcement hook in plugins/ca/hooks/hooks.json is registered TWICE:

    primary :  python3 "<script>"
    fallback:  python3 -c "" || python "<script>"

`plugins/ca-codex/hooks/hooks.json` carries the same primary+fallback
duplication (reliability-008), but in Codex's native per-entry
`command`/`commandWindows` shape rather than one platform-neutral `command`
string:

    primary :  command="python3 <script>"          commandWindows="python <script>"
    fallback:  command="python3 -c \"\" || python <script>"
               commandWindows="python -c \"\" || python3 <script>"

(rationale in core/pysrc/_hooklib.py; stock Windows ships a Microsoft Store
`python3` alias stub that exits 9009, which would make every gate fail OPEN
and SILENT; the fallback probes the primary interpreter and runs the OTHER
one only when the probe fails; separate entries each get fresh stdin so a
blocking exit 2 is never swallowed by a rerun against drained stdin).

This harness executes every hook command string VERBATIM, the way each host
does (`cmd /d /s /c "<command>"` on Windows, `/bin/sh -c '<command>'` on
POSIX, hook-input JSON piped to stdin, one process per entry with fresh
stdin), under three PATH scenarios:

    REAL  a dir providing real `python3` AND `python` is prepended to PATH.
    STUB  a dir whose `python3` mimics the Store alias (prints "Python was
          not found" to stderr, exits 9009, and logs its invocation to a
          marker file so the run is provable) is prepended FIRST; a dir
          providing only real `python` follows it.
    NONE  PATH is the ambient PATH with every dir that resolves `python` or
          `python3` removed (git, node, system dirs survive).

Expected behavior, asserted per scenario:

    REAL  primary does the work; fallback's probe succeeds so it no-ops
          (exit 0, no output) — no double execution, no double injection.
    STUB  primary fails noisily (the stub), NEVER exit 0 and NEVER exit 2;
          fallback's probe hits the stub, `||` runs `python <script>`, and
          the script does the work — including blocking via exit 2.
    NONE  nothing can run the script: every entry must exit NONZERO with a
          non-empty stderr (fail LOUD), and must never exit 2 (a block it
          did not evaluate) — but also never exit 0 (silent dormancy is the
          failure mode this whole layer exists to prevent).

Dormancy (a repo without `arbiter: enabled`): the hook layer must take no
action — no exit 2, no stdout. Under REAL that means strict silence and
exit 0 from both entries. Under STUB/NONE the *interpreter resolution
failure itself* is unavoidably noisy on stderr (the primary entry IS the
stub) — that noise is environmental, identical for enabled and dormant
repos, and is exactly the loud breadcrumb the design wants. Dormancy is
therefore asserted as: no entry exits 2, no entry produces stdout, and any
entry that actually reaches the script exits 0 silently.

The ca-codex campaign exercises the SAME interpreter-resolution matrix
against Codex-native payload shapes (Bash tool_input.command; apply_patch
envelopes for writes) and the guard tags that payload shape is expected to
trip (H-20 no-verify-commit block, H-05 audit-log-overwrite block) — the
guard-decision CONTENT is exhaustively covered by
.github/scripts/test_codex_adapter.py; this harness's job is proving the
interpreter plumbing carries those verdicts through unchanged, on Codex's
per-OS command/commandWindows entries, exactly as it does for `ca`.

Stdlib only. Exit 0 = all assertions pass; exit 1 = failures (each printed
with the verbatim command string and captured streams).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
# Strip the live harness's project signal: project_root() trusts
# CLAUDE_PROJECT_DIR first, and a value leaking in from a Claude session
# would point every spawned hook at the real repo, not the fixture repo.
os.environ.pop("CLAUDE_PROJECT_DIR", None)


WIN = os.name == "nt"
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
CA_PLUGIN_ROOT = os.path.join(REPO, "plugins", "ca")
CA_HOOKS_JSON = os.path.join(CA_PLUGIN_ROOT, "hooks", "hooks.json")
CODEX_PLUGIN_ROOT = os.path.join(REPO, "plugins", "ca-codex")
CODEX_HOOKS_JSON = os.path.join(CODEX_PLUGIN_ROOT, "hooks", "hooks.json")

PERSONA_MARK = "=== codeArbiter startup state ==="
STORE_STUB_MSG = "Python was not found"

failures = []
checks = 0


# ---------------------------------------------------------------- scaffolding

def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, timeout=60, **kw)


def make_fixture(base, name, enabled):
    """A throwaway git repo; `enabled` controls the arbiter opt-in frontmatter."""
    root = os.path.join(base, name)
    os.makedirs(root)
    r = sh(["git", "init", "-q", root])
    if r.returncode != 0:
        sys.exit(f"FATAL: git init failed for fixture: {r.stderr}")
    if enabled:
        ca = os.path.join(root, ".codearbiter")
        os.makedirs(ca)
        with open(os.path.join(ca, "CONTEXT.md"), "w", encoding="utf-8") as f:
            f.write("---\narbiter: enabled\nstage: 2\n---\n"
                    "<!--INITIALIZED-->\nCold-install harness fixture.\n")
        with open(os.path.join(ca, "overrides.log"), "w", encoding="utf-8") as f:
            f.write("seed\n")
    return root


def make_real_dir(base):
    """A dir resolving both `python3` and `python` to a real interpreter.
    POSIX: symlinks to sys.executable. Windows: a venv's Scripts dir (its
    python.exe is a relocatable redirector keyed off the adjacent pyvenv.cfg,
    so copying it to python3.exe in the same dir yields a working python3 —
    a plain copy of the base python.exe would lose its stdlib)."""
    if not WIN:
        d = os.path.join(base, "real-bin")
        os.makedirs(d)
        for name in ("python3", "python"):
            os.symlink(sys.executable, os.path.join(d, name))
        return d
    venv = os.path.join(base, "real-venv")
    r = sh([sys.executable, "-m", "venv", "--without-pip", venv])
    if r.returncode != 0:
        sys.exit(f"FATAL: venv creation failed: {r.stderr}")
    scripts = os.path.join(venv, "Scripts")
    shutil.copy2(os.path.join(scripts, "python.exe"),
                 os.path.join(scripts, "python3.exe"))
    return scripts


def make_pyonly_dir(base):
    """A dir resolving ONLY `python` (the STUB scenario's later-on-PATH real
    interpreter). Windows: a second venv Scripts dir (has python.exe, no
    python3.exe). POSIX: a single symlink."""
    if not WIN:
        d = os.path.join(base, "py-only-bin")
        os.makedirs(d)
        os.symlink(sys.executable, os.path.join(d, "python"))
        return d
    venv = os.path.join(base, "pyonly-venv")
    r = sh([sys.executable, "-m", "venv", "--without-pip", venv])
    if r.returncode != 0:
        sys.exit(f"FATAL: venv creation failed: {r.stderr}")
    return os.path.join(venv, "Scripts")


def make_stub_dir(base):
    """A dir whose `python3` behaves like the Microsoft Store alias stub:
    stderr noise, exit 9009 (POSIX: 49 — 9009 truncates mod 256 anyway), and
    an invocation log proving the fake was actually exercised."""
    d = os.path.join(base, "stub-bin")
    os.makedirs(d)
    log = os.path.join(d, "python3-invoked.log")
    if WIN:
        with open(os.path.join(d, "python3.bat"), "w", encoding="ascii") as f:
            f.write("@echo off\r\n"
                    "echo invoked>> \"%~dp0python3-invoked.log\"\r\n"
                    "echo Python was not found; run without arguments to install from the"
                    " Microsoft Store, or disable this shortcut from Settings. 1>&2\r\n"
                    "exit /b 9009\r\n")
    else:
        p = os.path.join(d, "python3")
        with open(p, "w", encoding="ascii") as f:
            f.write("#!/bin/sh\n"
                    "echo invoked >> \"$(dirname \"$0\")/python3-invoked.log\"\n"
                    "echo \"Python was not found; run without arguments to install from"
                    " the Microsoft Store.\" >&2\n"
                    "exit 49\n")
        os.chmod(p, 0o755)
    return d, log


def dir_resolves_python(d):
    """True if PATH dir `d` would resolve `python` or `python3`."""
    names = ("python", "python3")
    try:
        if WIN:
            exts = [e.lower() for e in
                    os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(";") if e]
            return any(os.path.isfile(os.path.join(d, n + e)) for n in names for e in exts)
        return any(os.path.isfile(os.path.join(d, n)) and os.access(os.path.join(d, n), os.X_OK)
                   for n in names)
    except OSError:
        return False


def base_path_without_python():
    kept, dropped = [], []
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if d and dir_resolves_python(d):
            dropped.append(d)
        else:
            kept.append(d)
    return os.pathsep.join(kept), dropped


def scenario_env(path_value, fixture):
    env = {k: v for k, v in os.environ.items()
           if k.upper() not in ("PATH", "PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV",
                                 "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH")}
    env["PATH"] = path_value
    env["CLAUDE_PLUGIN_ROOT"] = _CURRENT_PLUGIN_ROOT[0]
    env["CLAUDE_PROJECT_DIR"] = fixture
    # Sandbox the home dir. Hooks resolve ~/.claude/settings.json via
    # expanduser("~") — notably session-start.py's statusLine self-heal, which
    # REWRITES settings.json on every SessionStart. Without this redirect that
    # write escapes into the developer's REAL settings and pins the statusLine to
    # this run's throwaway venv interpreter, blanking the bar when teardown
    # deletes it. expanduser prefers USERPROFILE on Windows and HOME on POSIX; set
    # both (and drop HOMEDRIVE/HOMEPATH) so the home always resolves inside base.
    sandbox_home = os.path.join(os.path.dirname(os.path.abspath(fixture)), "sandbox-home")
    os.makedirs(sandbox_home, exist_ok=True)
    env["HOME"] = sandbox_home
    env["USERPROFILE"] = sandbox_home
    return env


# scenario_env needs to know which plugin's CLAUDE_PLUGIN_ROOT to export for
# the command string currently being resolved — a 1-slot mutable cell rather
# than a parameter, so the function signature stays identical for both
# campaigns' call sites below.
_CURRENT_PLUGIN_ROOT = [CA_PLUGIN_ROOT]


def run_entry(command, hook_input, fixture, env):
    """One hook entry, one process, fresh stdin — exactly how each host
    invokes hook commands (cmd /d /s /c on Windows, sh -c on POSIX)."""
    stdin = json.dumps(hook_input).encode("utf-8")
    if WIN:
        proc = subprocess.run('cmd.exe /d /s /c "' + command + '"',
                              input=stdin, capture_output=True,
                              cwd=fixture, env=env, timeout=60)
    else:
        proc = subprocess.run(["/bin/sh", "-c", command],
                              input=stdin, capture_output=True,
                              cwd=fixture, env=env, timeout=60)
    out = proc.stdout.decode("utf-8", errors="replace")
    err = proc.stderr.decode("utf-8", errors="replace")
    return proc.returncode, out, err


# ----------------------------------------------------------------- assertions

class Entry:
    def __init__(self, label, command, rc, out, err, stub_invoked):
        self.label, self.command = label, command
        self.rc, self.out, self.err = rc, out, err
        self.stub_invoked = stub_invoked


def check(cond, entry, what):
    global checks
    checks += 1
    if cond:
        return
    failures.append(
        f"FAIL [{entry.label}] {what}\n"
        f"  command : {entry.command}\n"
        f"  exit    : {entry.rc}\n"
        f"  stdout  : {entry.out.strip()[:400]!r}\n"
        f"  stderr  : {entry.err.strip()[:400]!r}")
    print(failures[-1])


def assert_noop_allow(e, stub_ok=False):
    """An entry that must take no action. With stub_ok (the STUB scenario's
    fallback), the probe `python3 -c ""` legitimately hits the stub before
    `||` hands off, so stderr may carry the stub's noise — but ONLY that,
    never a hook verdict."""
    check(e.rc == 0, e, "expected exit 0 (no-op allow)")
    check(e.out == "", e, "expected no stdout (no-op allow)")
    if stub_ok:
        check(all(STORE_STUB_MSG in ln for ln in e.err.splitlines() if ln.strip()),
              e, "STUB allow may carry only the stub's stderr noise")
    else:
        check(e.err == "", e, "expected no stderr (no-op allow)")


def assert_loud_failure(e):
    """The NONE scenario: never a block, never a clean exit, never silent."""
    check(e.rc != 0, e, "NONE must fail LOUD — exit 0 here is silent dormancy, "
                        "the exact failure mode this layer exists to prevent")
    check(e.rc != 2, e, "NONE must not exit 2 (a block it never evaluated)")
    check(e.err.strip() != "", e, "NONE must be noisy on stderr")
    check(PERSONA_MARK not in e.out, e, "no persona may inject without an interpreter")


def assert_stub_primary(e):
    """STUB primary entry = the Store-alias stub itself."""
    check(e.rc not in (0, 2), e, "stub primary must fail visibly (not 0) without "
                                 "blocking (not 2)")
    check(e.stub_invoked, e, "the fake python3 was not invoked (stub marker absent)")
    check(STORE_STUB_MSG in e.err, e, "stub stderr breadcrumb missing")
    check(e.out == "", e, "stub primary must not produce stdout")


# ------------------------------------------------------------- hooks.json map

def build_hooks_map(hooks_json_path, plugin_root, field_of, expected_scripts,
                     label):
    """Parse `hooks_json_path`; return {script basename -> {"primary": cmd,
    "fallback": cmd}} with ${CLAUDE_PLUGIN_ROOT} substituted. `field_of(h)`
    extracts the OS-appropriate command string from one hook object — for
    `ca` that is always `h["command"]`; for `ca-codex` it is
    `h["commandWindows"]` on Windows and `h["command"]` on POSIX (Codex's
    native per-OS shape). Structural invariant: every matcher group registers
    exactly one primary and one fallback, and every referenced script exists
    on disk."""
    with open(hooks_json_path, encoding="utf-8") as f:
        config = json.load(f)

    hooks = {}
    for event, groups in config["hooks"].items():
        for group in groups:
            cmds = [field_of(h) for h in group["hooks"]]
            if len(cmds) != 2:
                sys.exit(f"FATAL: {label} {event} group must register exactly 2 "
                         f"entries (primary + fallback), found {len(cmds)}: {cmds}")
            primary = [c for c in cmds if '-c ""' not in c and "-c \\\"\\\"" not in c]
            fallback = [c for c in cmds if c not in primary]
            if len(primary) != 1 or len(fallback) != 1:
                sys.exit(f"FATAL: {label} {event} group lacks a primary/fallback "
                         f"pair: {cmds}")
            script = primary[0].split("/")[-1].rstrip('"')
            script_path = os.path.join(plugin_root, "hooks", script)
            if not os.path.isfile(script_path):
                sys.exit(f"FATAL: {label} hooks.json references a missing script: "
                         f"{script_path}")
            hooks[script] = {
                "primary": primary[0].replace("${CLAUDE_PLUGIN_ROOT}", plugin_root),
                "fallback": fallback[0].replace("${CLAUDE_PLUGIN_ROOT}", plugin_root),
            }
    if set(hooks) != expected_scripts:
        sys.exit(f"FATAL: {label} hook set drifted — update this harness. "
                 f"found {sorted(hooks)}, expected {sorted(expected_scripts)}")
    print(f"{label} hooks.json: {len(hooks)} hooks x 2 entries, all scripts present")
    return hooks


def ca_field(h):
    return h["command"]


def codex_field(h):
    return h["commandWindows"] if WIN else h["command"]


# ------------------------------------------------------------------- the runs

def make_runner(hooks, plugin_root, paths, stub_log):
    """Return a `run(script, kind, scenario, fixture, hook_input)` closure
    bound to one plugin's hooks map, PATH scenarios, and stub-invocation log."""
    def run(script, kind, scenario, fixture, hook_input):
        cmd = hooks[script][kind]
        _CURRENT_PLUGIN_ROOT[0] = plugin_root
        env = scenario_env(paths[scenario], fixture)
        if os.path.exists(stub_log):
            os.remove(stub_log)
        rc, out, err = run_entry(cmd, hook_input, fixture, env)
        label = f"{script}/{kind}/{scenario}"
        return Entry(label, cmd, rc, out, err, os.path.exists(stub_log))
    return run


def run_ca_campaign(hooks, paths, stub_log, enabled, dormant, base):
    """The original `ca` (Claude Code) cold-install campaign."""
    run = make_runner(hooks, CA_PLUGIN_ROOT, paths, stub_log)

    SESSION_IN = {"hook_event_name": "SessionStart", "source": "startup"}
    ADD_A_IN = {"tool_name": "Bash", "tool_input": {"command": "git add -A"}}
    BENIGN_BASH_IN = {"tool_name": "Bash", "tool_input": {"command": "git status"}}

    # ---- 0. harness isolation: scenario_env MUST sandbox the home dir.
    # session-start.py self-heals the statusLine on every SessionStart by
    # writing ~/.claude/settings.json (resolved via expanduser("~")). If the
    # scenario env leaves HOME/USERPROFILE pointed at the developer's real
    # home, that write escapes the harness and pins the user's statusLine to
    # THIS run's throwaway venv interpreter — which teardown then deletes,
    # blanking the bar. The env must redirect the home dir into the temp base.
    real_home = os.path.realpath(os.path.expanduser("~"))
    iso_env = scenario_env(paths["REAL"], dormant)
    iso = Entry("ca/scenario_env/home-isolation", "scenario_env(REAL, fixture)",
                0, "", "", False)
    child_home = iso_env.get("USERPROFILE") if WIN else iso_env.get("HOME")
    check(bool(child_home), iso,
          "scenario_env must set a sandbox home (USERPROFILE on Windows, HOME on POSIX)")
    rp = os.path.realpath(child_home) if child_home else ""
    check(rp != real_home, iso,
          "scenario_env must redirect the home dir AWAY from the real user home — "
          "else a hook's ~/.claude write escapes into the developer's real settings")
    check(rp.startswith(os.path.realpath(base)), iso,
          "the sandbox home must live under the harness temp dir")

    # ---- 1. SessionStart, enabled repo: persona exactly once, never twice
    for scen in ("REAL", "STUB"):
        p = run("session-start.py", "primary", scen, enabled, SESSION_IN)
        fb = run("session-start.py", "fallback", scen, enabled, SESSION_IN)
        total = p.out.count(PERSONA_MARK) + fb.out.count(PERSONA_MARK)
        check(total == 1, p if scen == "REAL" else fb,
              f"persona must inject exactly once across both entries, got {total}")
        if scen == "REAL":
            check(p.rc == 0 and PERSONA_MARK in p.out, p,
                  "REAL primary must inject the persona and exit 0")
            assert_noop_allow(fb)
        else:
            assert_stub_primary(p)
            check(fb.rc == 0 and PERSONA_MARK in fb.out, fb,
                  "STUB fallback must inject the persona via `python` and exit 0")
            check(fb.stub_invoked, fb, "fallback probe must have hit the stub")
    for kind in ("primary", "fallback"):
        assert_loud_failure(run("session-start.py", kind, "NONE", enabled, SESSION_IN))

    # ---- 2. SessionStart, dormant repo: no injection anywhere
    for scen in ("REAL", "STUB", "NONE"):
        for kind in ("primary", "fallback"):
            e = run("session-start.py", kind, scen, dormant, SESSION_IN)
            check(PERSONA_MARK not in e.out and e.out == "", e,
                  "dormant repo must never receive an injection")
            check(e.rc != 2, e, "dormant repo must never block")
            if scen == "REAL" or (scen == "STUB" and kind == "fallback"):
                assert_noop_allow(e, stub_ok=(scen == "STUB"))

    # ---- 3. pre-bash `git add -A`, enabled repo: the H-03 block survives
    p = run("pre-bash.py", "primary", "REAL", enabled, ADD_A_IN)
    check(p.rc == 2 and "H-03" in p.err, p,
          "REAL primary must BLOCK `git add -A` (exit 2, H-03)")
    fb = run("pre-bash.py", "fallback", "REAL", enabled, ADD_A_IN)
    assert_noop_allow(fb)  # fresh-stdin no-op; must not emit a conflicting pass

    p = run("pre-bash.py", "primary", "STUB", enabled, ADD_A_IN)
    assert_stub_primary(p)
    fb = run("pre-bash.py", "fallback", "STUB", enabled, ADD_A_IN)
    check(fb.rc == 2 and "H-03" in fb.err, fb,
          "STUB fallback must BLOCK `git add -A` via `python` (exit 2, H-03)")
    check(fb.stub_invoked, fb, "fallback probe must have hit the stub")

    for kind in ("primary", "fallback"):
        e = run("pre-bash.py", kind, "NONE", enabled, ADD_A_IN)
        assert_loud_failure(e)
        check("H-03" not in e.err, e, "no interpreter, so no H-03 verdict possible")

    # ---- 4. pre-bash benign command, enabled repo: no false block
    for scen, kind in (("REAL", "primary"), ("REAL", "fallback"), ("STUB", "fallback")):
        assert_noop_allow(run("pre-bash.py", kind, scen, enabled, BENIGN_BASH_IN),
                          stub_ok=(scen == "STUB"))

    # ---- 5. pre-bash `git add -A`, dormant repo: dormancy means no block
    for scen in ("REAL", "STUB", "NONE"):
        for kind in ("primary", "fallback"):
            e = run("pre-bash.py", kind, scen, dormant, ADD_A_IN)
            check(e.rc != 2 and "H-03" not in e.err and "BLOCKED" not in e.err, e,
                  "dormant repo must never block")
            check(e.out == "", e, "dormant repo must produce no stdout")
            if scen == "REAL" or (scen == "STUB" and kind == "fallback"):
                assert_noop_allow(e, stub_ok=(scen == "STUB"))

    # ---- 6. pre-write H-05 (audit log overwrite), enabled: block survives STUB
    write_in = {"tool_name": "Write", "tool_input": {
        "file_path": os.path.join(enabled, ".codearbiter", "overrides.log"),
        "content": "rewritten history"}}
    p = run("pre-write.py", "primary", "REAL", enabled, write_in)
    check(p.rc == 2 and "H-05" in p.err, p, "REAL primary must BLOCK the audit-log Write")
    assert_noop_allow(run("pre-write.py", "fallback", "REAL", enabled, write_in))
    fb = run("pre-write.py", "fallback", "STUB", enabled, write_in)
    check(fb.rc == 2 and "H-05" in fb.err, fb,
          "STUB fallback must BLOCK the audit-log Write via `python`")

    # ---- 7. pre-edit benign, enabled: allow in both interpreter routes
    edit_in = {"tool_name": "Edit", "tool_input": {
        "file_path": os.path.join(enabled, "notes.txt"),
        "old_string": "a", "new_string": "b"}}
    for scen, kind in (("REAL", "primary"), ("REAL", "fallback"), ("STUB", "fallback")):
        assert_noop_allow(run("pre-edit.py", kind, scen, enabled, edit_in),
                          stub_ok=(scen == "STUB"))

    # ---- 8. post-write-edit crypto reminder, enabled: advisory fires, exit 0
    post_in = {"tool_name": "Write", "tool_input": {
        "file_path": os.path.join(enabled, "x.js"),
        "content": "const h = createHash('md5')"}}
    p = run("post-write-edit.py", "primary", "REAL", enabled, post_in)
    check(p.rc == 0 and "H-09" in p.err, p,
          "REAL primary must emit the H-09 reminder and exit 0")
    assert_noop_allow(run("post-write-edit.py", "fallback", "REAL", enabled, post_in))
    fb = run("post-write-edit.py", "fallback", "STUB", enabled, post_in)
    check(fb.rc == 0 and "H-09" in fb.err, fb,
          "STUB fallback must emit the H-09 reminder via `python` and exit 0")

    # ---- 9. prune-transcript: CODEARBITER_PRUNE unset → always a no-op
    prune_in = {"hook_event_name": "UserPromptSubmit",
                "session_id": "test-session",
                "transcript_path": "/nonexistent/path.jsonl"}
    assert_noop_allow(run("prune-transcript.py", "primary", "REAL", enabled, prune_in))
    assert_noop_allow(run("prune-transcript.py", "fallback", "REAL", enabled, prune_in))
    assert_stub_primary(run("prune-transcript.py", "primary", "STUB", enabled, prune_in))
    assert_noop_allow(run("prune-transcript.py", "fallback", "STUB", enabled, prune_in),
                      stub_ok=True)
    for kind in ("primary", "fallback"):
        assert_loud_failure(run("prune-transcript.py", kind, "NONE", enabled, prune_in))


def _patch(body):
    return "*** Begin Patch\n" + body + "*** End Patch\n"


# Codex's Windows PRIMARY entry runs `python` directly (not `python3`) —
# already sidestepping the classic Store-alias-`python3` stub by
# construction. The STUB fixture built by make_stub_dir() models exactly
# THAT stub (a fake `python3`; `python` is real in the STUB scenario's
# py-only dir). So on Windows, under THIS fixture, the codex primary entry
# never touches the stub at all and behaves identically to REAL — and its
# fallback's left-hand probe (`python -c ""`) succeeds too, so `||` never
# invokes the right-hand `python3`, making the fallback a true no-op just
# like REAL. On POSIX the primary is `python3` and IS the fixture's stub, so
# STUB behaves the same way it does for `ca`. This flag selects which shape
# the STUB scenario's assertions below take.
CODEX_STUB_IS_REAL_LIKE = WIN


def run_ca_codex_campaign(hooks, paths, stub_log, enabled, dormant):
    """The `ca-codex` (OpenAI Codex CLI) cold-install campaign — same
    interpreter-resolution matrix, driven through Codex's native per-OS
    command/commandWindows entries and payload shapes (Bash tool_input, the
    apply_patch envelope). Guard-decision CONTENT is exhaustively covered by
    test_codex_adapter.py; here the SAME verdict-bearing scenarios (H-20
    no-verify-commit, H-05 audit-log overwrite) prove the interpreter
    plumbing carries the verdict through unchanged under REAL/STUB/NONE."""
    run = make_runner(hooks, CODEX_PLUGIN_ROOT, paths, stub_log)

    def session_in():
        return {"hook_event_name": "SessionStart", "source": "startup"}

    def bash_in(cmd, fixture):
        return {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                "cwd": fixture, "tool_input": {"command": cmd}}

    def patch_in(patch, fixture, tool_name="apply_patch"):
        return {"hook_event_name": "PreToolUse", "tool_name": tool_name,
                "cwd": fixture, "tool_input": {"command": patch}}

    def allow_pairs():
        """(scen, kind, stub_ok) triples an ordinary allow is expected over.
        STUB is included for BOTH entries when CODEX_STUB_IS_REAL_LIKE
        (Windows: the stub is untouched); otherwise (POSIX) only the
        fallback is exercised under STUB, same as `ca`."""
        pairs = [("REAL", "primary", False), ("REAL", "fallback", False)]
        if CODEX_STUB_IS_REAL_LIKE:
            pairs += [("STUB", "primary", False), ("STUB", "fallback", False)]
        else:
            pairs += [("STUB", "fallback", True)]
        return pairs

    NOVERIFY_PATCH = 'git commit --no-verify -m "x"'
    AUDIT_PATCH = _patch("*** Update File: .codearbiter/overrides.log\n"
                         "@@\n-seed\n+rewritten\n")
    ORDINARY_PATCH = _patch("*** Add File: src/util.py\n+x = 1\n")
    PRUNE_IN = {"hook_event_name": "UserPromptSubmit", "prompt": "x"}

    # ---- 1. SessionStart, enabled repo: persona exactly once, never twice
    for scen in ("REAL", "STUB"):
        p = run("session-start.py", "primary", scen, enabled, session_in())
        fb = run("session-start.py", "fallback", scen, enabled, session_in())
        total = p.out.count(PERSONA_MARK) + fb.out.count(PERSONA_MARK)
        check(total == 1, p if scen == "REAL" else fb,
              f"persona must inject exactly once across both entries, got {total}")
        if scen == "REAL" or CODEX_STUB_IS_REAL_LIKE:
            check(p.rc == 0 and PERSONA_MARK in p.out, p,
                  "primary must inject the persona and exit 0")
            assert_noop_allow(fb)
        else:
            assert_stub_primary(p)
            check(fb.rc == 0 and PERSONA_MARK in fb.out, fb,
                  "STUB fallback must inject the persona via the other interpreter and exit 0")
            check(fb.stub_invoked, fb, "fallback probe must have hit the stub")
    for kind in ("primary", "fallback"):
        assert_loud_failure(run("session-start.py", kind, "NONE", enabled, session_in()))

    # ---- 2. SessionStart, dormant repo: no injection anywhere
    for scen in ("REAL", "STUB", "NONE"):
        for kind in ("primary", "fallback"):
            e = run("session-start.py", kind, scen, dormant, session_in())
            check(PERSONA_MARK not in e.out and e.out == "", e,
                  "dormant repo must never receive an injection")
            check(e.rc != 2, e, "dormant repo must never block")
            include = scen == "REAL" or (
                scen == "STUB" and (kind == "fallback" or CODEX_STUB_IS_REAL_LIKE))
            if include:
                stub_ok = (scen == "STUB") and not CODEX_STUB_IS_REAL_LIKE
                assert_noop_allow(e, stub_ok=stub_ok)

    # ---- 3. pre-bash `git commit --no-verify`, enabled: the H-20 block survives
    p = run("pre-bash.py", "primary", "REAL", enabled, bash_in(NOVERIFY_PATCH, enabled))
    check(p.rc == 2 and "H-20" in p.err, p,
          "REAL primary must BLOCK `git commit --no-verify` (exit 2, H-20)")
    fb = run("pre-bash.py", "fallback", "REAL", enabled, bash_in(NOVERIFY_PATCH, enabled))
    assert_noop_allow(fb)  # fresh-stdin no-op; must not emit a conflicting pass

    if CODEX_STUB_IS_REAL_LIKE:
        p = run("pre-bash.py", "primary", "STUB", enabled, bash_in(NOVERIFY_PATCH, enabled))
        check(p.rc == 2 and "H-20" in p.err, p,
              "STUB primary (python, untouched by this python3-only stub) must still BLOCK")
        fb = run("pre-bash.py", "fallback", "STUB", enabled, bash_in(NOVERIFY_PATCH, enabled))
        assert_noop_allow(fb)
    else:
        p = run("pre-bash.py", "primary", "STUB", enabled, bash_in(NOVERIFY_PATCH, enabled))
        assert_stub_primary(p)
        fb = run("pre-bash.py", "fallback", "STUB", enabled, bash_in(NOVERIFY_PATCH, enabled))
        check(fb.rc == 2 and "H-20" in fb.err, fb,
              "STUB fallback must BLOCK `git commit --no-verify` via the other interpreter (exit 2, H-20)")
        check(fb.stub_invoked, fb, "fallback probe must have hit the stub")

    for kind in ("primary", "fallback"):
        e = run("pre-bash.py", kind, "NONE", enabled, bash_in(NOVERIFY_PATCH, enabled))
        assert_loud_failure(e)
        check("H-20" not in e.err, e, "no interpreter, so no H-20 verdict possible")

    # ---- 4. pre-bash benign command, enabled: no false block
    for scen, kind, stub_ok in allow_pairs():
        assert_noop_allow(run("pre-bash.py", kind, scen, enabled, bash_in("ls -la", enabled)),
                          stub_ok=stub_ok)

    # ---- 5. pre-write H-05 (audit log overwrite via apply_patch), enabled
    p = run("pre-write.py", "primary", "REAL", enabled, patch_in(AUDIT_PATCH, enabled))
    check(p.rc == 2 and "H-05" in p.err, p,
          "REAL primary must BLOCK the audit-log apply_patch")
    assert_noop_allow(run("pre-write.py", "fallback", "REAL", enabled,
                          patch_in(AUDIT_PATCH, enabled)))

    if CODEX_STUB_IS_REAL_LIKE:
        p = run("pre-write.py", "primary", "STUB", enabled, patch_in(AUDIT_PATCH, enabled))
        check(p.rc == 2 and "H-05" in p.err, p,
              "STUB primary (python, untouched by this python3-only stub) must still BLOCK")
        assert_noop_allow(run("pre-write.py", "fallback", "STUB", enabled,
                              patch_in(AUDIT_PATCH, enabled)))
    else:
        assert_stub_primary(run("pre-write.py", "primary", "STUB", enabled,
                                patch_in(AUDIT_PATCH, enabled)))
        fb = run("pre-write.py", "fallback", "STUB", enabled, patch_in(AUDIT_PATCH, enabled))
        check(fb.rc == 2 and "H-05" in fb.err, fb,
              "STUB fallback must BLOCK the audit-log apply_patch via the other interpreter")

    for kind in ("primary", "fallback"):
        e = run("pre-write.py", kind, "NONE", enabled, patch_in(AUDIT_PATCH, enabled))
        assert_loud_failure(e)
        check("H-05" not in e.err, e, "no interpreter, so no H-05 verdict possible")

    # ---- 6. pre-write ordinary write, enabled: allow in both interpreter routes
    for scen, kind, stub_ok in allow_pairs():
        assert_noop_allow(run("pre-write.py", kind, scen, enabled,
                              patch_in(ORDINARY_PATCH, enabled)),
                          stub_ok=stub_ok)

    # ---- 7. post-write-edit, enabled: an ungoverned path is a silent allow
    post_in = patch_in(ORDINARY_PATCH, enabled)
    for scen, kind, stub_ok in allow_pairs():
        assert_noop_allow(run("post-write-edit.py", kind, scen, enabled, post_in),
                          stub_ok=stub_ok)
    for kind in ("primary", "fallback"):
        assert_loud_failure(run("post-write-edit.py", kind, "NONE", enabled, post_in))

    # ---- 8. prune-transcript audit staleness-warn: host-neutral, non-blocking
    for kind in ("primary", "fallback"):
        e = run("prune-transcript.py", kind, "REAL", enabled, PRUNE_IN)
        check(e.rc == 0, e, "the audit staleness-warn must never block (exit 0)")
        check(e.out == "", e, "the staleness-warn produces no stdout")

    if CODEX_STUB_IS_REAL_LIKE:
        for kind in ("primary", "fallback"):
            e = run("prune-transcript.py", kind, "STUB", enabled, PRUNE_IN)
            check(e.rc == 0, e, "the audit staleness-warn must never block (exit 0)")
            check(e.out == "", e, "the staleness-warn produces no stdout")
    else:
        assert_stub_primary(run("prune-transcript.py", "primary", "STUB", enabled, PRUNE_IN))
        fb = run("prune-transcript.py", "fallback", "STUB", enabled, PRUNE_IN)
        check(fb.rc == 0, fb, "the audit staleness-warn must never block (exit 0)")
        check(fb.out == "", fb, "the staleness-warn produces no stdout")

    for kind in ("primary", "fallback"):
        assert_loud_failure(run("prune-transcript.py", kind, "NONE", enabled, PRUNE_IN))


# ------------------------------------------------------------------------- main

CA_EXPECTED = {"session-start.py", "pre-bash.py", "pre-write.py",
               "pre-edit.py", "post-write-edit.py", "prune-transcript.py",
               "pre-read.py"}
CODEX_EXPECTED = {"session-start.py", "pre-bash.py", "pre-write.py",
                  "post-write-edit.py", "prune-transcript.py"}


def main():
    for s in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    ca_hooks = build_hooks_map(CA_HOOKS_JSON, CA_PLUGIN_ROOT, ca_field,
                               CA_EXPECTED, "ca")

    # ---- AC-02 Read-matcher wiring assertion (ca only — ca-codex has no
    # read tool and registers no pre-read.py entry, per docs/parity.md). ----
    with open(CA_HOOKS_JSON, encoding="utf-8") as f:
        ca_config = json.load(f)
    pretooluse_groups = ca_config["hooks"].get("PreToolUse", [])
    read_groups = [g for g in pretooluse_groups if g.get("matcher") == "Read"]
    if not read_groups:
        sys.exit("FATAL: ca hooks.json has no PreToolUse entry with matcher == 'Read'")
    rg = read_groups[0]
    read_cmds = [h["command"] for h in rg["hooks"]]
    if not all("pre-read.py" in c for c in read_cmds):
        sys.exit(f"FATAL: Read matcher entries do not all reference pre-read.py: {read_cmds}")
    primary_cmds = [c for c in read_cmds if '-c ""' not in c and "-c \\\"\\\"" not in c]
    fallback_cmds = [c for c in read_cmds if c not in primary_cmds]
    if len(primary_cmds) != 1 or len(fallback_cmds) != 1:
        sys.exit(f"FATAL: Read matcher must have exactly one primary + one fallback, "
                 f"got: {read_cmds}")
    if "||" not in fallback_cmds[0] or "python" not in fallback_cmds[0]:
        sys.exit(f"FATAL: Read matcher fallback lacks python3 || python dual-interpreter "
                 f"shape: {fallback_cmds[0]}")
    print("Read matcher wiring: OK (matcher='Read', pre-read.py, primary+fallback dual-interpreter)")

    codex_hooks = build_hooks_map(CODEX_HOOKS_JSON, CODEX_PLUGIN_ROOT, codex_field,
                                  CODEX_EXPECTED, "ca-codex")

    base = tempfile.mkdtemp(prefix="ca-coldinstall-")
    try:
        enabled = make_fixture(base, "fixture-enabled", enabled=True)
        dormant = make_fixture(base, "fixture-dormant", enabled=False)
        real_dir = make_real_dir(base)
        pyonly_dir = make_pyonly_dir(base)
        stub_dir, stub_log = make_stub_dir(base)
        none_path, dropped = base_path_without_python()
        print(f"NONE PATH drops {len(dropped)} python-bearing dir(s): {dropped}")

        ambient = os.environ.get("PATH", "")
        paths = {
            "REAL": os.pathsep.join([real_dir, ambient]),
            "STUB": os.pathsep.join([stub_dir, pyonly_dir, ambient]),
            "NONE": none_path,
        }

        run_ca_campaign(ca_hooks, paths, stub_log, enabled, dormant, base)
        run_ca_codex_campaign(codex_hooks, paths, stub_log, enabled, dormant)
    finally:
        shutil.rmtree(base, ignore_errors=True)

    print(f"\n{checks} assertions, {len(failures)} failed "
          f"({'cmd /d /s /c' if WIN else '/bin/sh -c'})")
    if failures:
        print("\nRELEASE BLOCKER: a cold-install scenario failed. Do not weaken the "
              "hook — the failing command strings are above.")
        sys.exit(1)
    print("cold-install matrix: PASS (ca + ca-codex, REAL / STUB / NONE)")


if __name__ == "__main__":
    main()

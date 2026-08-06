#!/usr/bin/env python3
# codeArbiter v2 — install-health doctor (the mechanical half of /ca:doctor).
#
# Silent dormancy is the worst failure shape this plugin has: the gates look
# installed but never fire, and nothing says so. It has happened in the wild —
# a stale plugin cache survived `claude plugin update` because the version
# string was unchanged, leaving months-old hooks in place until a full
# uninstall+reinstall. This script checks everything checkable from a single
# process; host-specific command surfaces add their supported execution
# evidence separately.
#
# Output: one OK / WARN / FAIL line per check, then a verdict. Exit 0 when
# nothing FAILed; exit 1 otherwise. Read-only — changes nothing.

import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gitexec import git_executable  # noqa: E402
import hostapi  # noqa: E402 — host seam (ADR-0011): plugin-root resolution
import _entrylib  # noqa: E402 — shared run() dispatch (jscpd dedup)
import _githooks  # noqa: E402 — #556: git-hook drop-in registry freshness
from _hooklib import frontmatter_enabled, get_host, set_host, utf8_stdio  # noqa: E402

HOOK_SCRIPTS = ("session-start.py", "pre-bash.py", "pre-write.py",
                "pre-edit.py", "post-write-edit.py", "prune-transcript.py")
PI_BRIDGE_SCRIPTS = ("pi-bridge.py", "git-enforce.py", "_githooks.py")

# MCP config files are read whole to be counted. `~/.claude.json` also carries
# session history, so it can be large; past this ceiling the source counts as
# unreadable and the check goes quiet rather than stalling /ca:doctor.
MCP_CONFIG_MAX_BYTES = 16 * 1024 * 1024
# Depth ceiling for the `mcpServers` walk below. Claude's deepest real nesting
# is projects -> <path> -> mcpServers (depth 2); the ceiling just stops a
# pathological document from costing a full traversal.
MCP_SCAN_MAX_DEPTH = 6

results = []  # (level, line)


def ok(line):
    results.append(("OK", line))


def warn(line):
    results.append(("WARN", line))


def fail(line):
    results.append(("FAIL", line))


def _run_cmd(args, **kw):
    # Renamed from `run` (ADR-0011): `run(host)` is now the host-seam entry
    # point every hook script exposes, so the subprocess helper cedes the name.
    return subprocess.run(args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=15, **kw)


def plugin_root():
    # Host seam (ADR-0011): CLAUDE_PLUGIN_ROOT then file-relative, exactly the
    # prior inline lookup; abspath preserved from the pre-seam behavior here.
    # get_host() (#257), not a direct hostapi.load_host(): resolves the SAME
    # Host run(host) injected instead of triggering a second disk load.
    return os.path.abspath(get_host().plugin_root())


def check_interpreters():
    """The hooks need python3 OR python on PATH; the dual registration in
    hooks.json tolerates a Store-alias python3 stub as long as real `python`
    exists behind it."""
    p3, p = shutil.which("python3"), shutil.which("python")
    stub = False
    if p3:
        try:
            stub = _run_cmd([p3, "-c", ""]).returncode != 0
        except Exception:  # noqa: BLE001
            stub = True
    if p3 and not stub:
        ok(f"python3 resolves and runs ({p3})")
    elif p3 and stub:
        (warn if p else fail)(
            f"python3 resolves but does not run ({p3}) — the Microsoft Store "
            f"alias stub. " + ("The hook fallback entries cover this via `python`."
                               if p else "And no `python` behind it: EVERY GATE IS "
                               "DORMANT. Install Python or disable the Store alias."))
    elif not p3 and p:
        ok("no python3 on PATH, but `python` resolves — the hook fallback entries cover this")
    else:
        fail("neither python3 nor python resolves on PATH — every hook fails loud, "
             "no gate evaluates. Install Python 3.")
    if p and not (p3 and not stub):
        ok(f"python resolves ({p})")


def check_payload(root, host=None):
    # host-aware manifest path (#263): defaults to get_host() (#257 — not a
    # direct hostapi.load_host(), so this stays the SAME injected instance)
    # so every pre-seam call site (main() below, and every existing test that
    # calls check_payload(root) positionally) keeps resolving the manifest
    # for whichever host is actually running, without threading a host
    # through every caller.
    host = host or get_host()
    manifest = os.path.join(root, host.manifest_relpath())
    version = None
    try:
        with open(manifest, encoding="utf-8") as f:
            version = json.load(f).get("version")
        ok(f"plugin payload at {root} (version {version})")
    except Exception as e:  # noqa: BLE001
        fail(f"plugin.json unreadable at {manifest}: {e}")
    if getattr(host, "name", "unknown") == "pi":
        try:
            with open(manifest, encoding="utf-8") as f:
                package = json.load(f)
            pi_config = package.get("pi") if isinstance(package, dict) else None
            extensions = pi_config.get("extensions") if isinstance(pi_config, dict) else None
            skills = pi_config.get("skills") if isinstance(pi_config, dict) else None
            if (package.get("name") == "ca-pi"
                    and extensions == ["./extensions/codearbiter.js"]
                    and skills == ["./skills"]):
                ok("package.json declares only the ca-pi extension and generated skills")
            else:
                fail("package.json has an invalid ca-pi package/discovery contract; reinstall ca-pi")
        except Exception as e:  # noqa: BLE001
            fail(f"package.json unreadable at {manifest}: {e}")
        required = HOOK_SCRIPTS + PI_BRIDGE_SCRIPTS
        missing = [s for s in required
                   if not os.path.isfile(os.path.join(root, "hooks", s))]
        if missing:
            fail(f"Pi shared core script(s) missing: {', '.join(missing)}")
        else:
            ok(f"Pi shared core present: pi-bridge.py and {len(required) - 1} support scripts")
        return
    hooks_json = os.path.join(root, "hooks", "hooks.json")
    try:
        with open(hooks_json, encoding="utf-8") as f:
            config = json.load(f)["hooks"]
        entries = sum(len(g["hooks"]) for groups in config.values() for g in groups)
        ok(f"hooks.json parses: {len(config)} events, {entries} entries")
    except Exception as e:  # noqa: BLE001
        fail(f"hooks/hooks.json unreadable or malformed: {e} — no gate is registered")
    missing = [s for s in HOOK_SCRIPTS
               if not os.path.isfile(os.path.join(root, "hooks", s))]
    if missing:
        fail(f"hook script(s) missing from the payload: {', '.join(missing)}")
    else:
        ok(f"all {len(HOOK_SCRIPTS)} hook scripts present")

    # The stale-cache trap: `claude plugin update` no-ops when the version
    # string is unchanged, so a cache dir can hold a payload months older
    # than the marketplace. Multiple cached versions are the breadcrumb.
    norm = root.replace("\\", "/")
    if "/plugins/cache/" in norm:
        versions_dir = os.path.dirname(root)
        try:
            siblings = sorted(d for d in os.listdir(versions_dir)
                              if os.path.isdir(os.path.join(versions_dir, d)))
            if len(siblings) > 1:
                warn(f"multiple cached plugin versions ({', '.join(siblings)}) under "
                     f"{versions_dir} — if behavior looks stale, uninstall+reinstall; "
                     f"`claude plugin update` no-ops on an unchanged version string")
            else:
                ok("single cached plugin version (no stale siblings)")
        except Exception:  # noqa: BLE001
            pass


def check_repo():
    """Returns the resolved repo root (for check_git_hook_freshness below), or
    None when this process isn't inside a git repository at all."""
    r = _run_cmd([git_executable(), "rev-parse", "--show-toplevel"])
    if r.returncode != 0:
        warn("not inside a git repository — repo-level checks skipped")
        return None
    root = r.stdout.strip()
    ctx = os.path.join(root, ".codearbiter", "CONTEXT.md")
    if not os.path.isfile(ctx):
        ok(f"no .codearbiter/CONTEXT.md in {root} — codeArbiter is dormant here "
           f"by design (run {get_host().cmd_ref('init')} to opt in)")
        return root
    enabled, malformed = frontmatter_enabled(ctx)
    if malformed:
        fail("CONTEXT.md frontmatter opens with --- but never closes — the "
             "activation check cannot evaluate; fix the frontmatter")
    elif enabled:
        ok("repo is arbiter-enabled (CONTEXT.md frontmatter)")
    else:
        ok("CONTEXT.md present but not arbiter-enabled — gates dormant by design")
    if enabled:
        with open(ctx, encoding="utf-8", errors="replace") as f:
            body = f.read()
        if "<!--INITIALIZED-->" in body:
            ok("project is initialized (<!--INITIALIZED--> marker present)")
        else:
            warn(f"no <!--INITIALIZED--> marker — startup will route to "
                 f"{get_host().cmd_ref('decompose')} or {get_host().cmd_ref('create-context')}")
        email = _run_cmd([git_executable(), "config", "user.email"]).stdout.strip()
        if email:
            ok(f"git identity for audit attribution: {email}")
        else:
            warn("git user.email is unset — overrides/ADRs cannot be attributed; "
                 "set it before gated work")
    return root


def check_git_hook_freshness(root):
    """#556 (AC-3): the git-level hook backstop (#161) can be running from a
    host's plugin cache that nobody has refreshed in a long time — a cache
    that predates a fix THIS checkout already carries (the #279
    sensitive-scan exemption, in the issue that motivated this check) is
    still wired into `.git/hooks` and can still block on stale logic. Before
    this check existed, nothing surfaced that until it produced a false
    block. Runs the SAME freshness probe the generated shim itself runs at
    commit/push time (`_githooks.stale_registered_plugins`), so this can
    never disagree with what actually happens at commit time.

    A no-op (nothing printed) when `root` is None (not inside a git repo —
    already reported by check_repo) or the drop-in registry doesn't exist
    yet (nothing installed, or a host that predates ADR-0014)."""
    if root is None:
        return
    dropin_dir = _githooks._dropin_dir(root)
    if dropin_dir is None or not os.path.isdir(dropin_dir):
        return
    stale = _githooks.stale_registered_plugins(dropin_dir)
    if stale:
        names = ", ".join(sorted(stale))
        plural = "entries" if len(stale) != 1 else "entry"
        warn(f"the git-hook backstop's drop-in registry (#161/#556) has a stale "
             f"enforcer {plural} for: {names} — a fresher registered sibling "
             f"exists (.git/codearbiter-hooksd), and the shim already skips the "
             f"stale {plural} rather than let it false-block. Start a session for "
             f"that host, or reinstall it, to refresh {names}.")
    else:
        ok("git-hook backstop registry (.git/codearbiter-hooksd) has no stale "
           "enforcer entries")


def check_host(host):
    """observability-004 (#268): surface which host was resolved — a dormant
    Codex install (or any broken `_host.py`) was previously indistinguishable
    from a working one, since nothing in doctor's output named the host at
    all. `host.name` is "claude" / "codex" under a working install, or
    "unknown" for the FailClosedHost hostapi.load_host() returns when a
    declared `_host.py` is present but failed to load (#255) — that "unknown"
    case is exactly the dormant install this check exists to surface, so it
    WARNs (not OKs) with an actionable pointer rather than reporting green."""
    name = getattr(host, "name", "unknown")
    if name == "unknown":
        warn("host resolution failed — enforcing as 'unknown' (a declared "
             "_host.py was present but failed to load); writes fail closed. "
             "Reinstall or fix the plugin's _host.py.")
    else:
        ok(f"resolved host: {name}")


def _mcp_json_count(doc, key, depth=0):
    """How many servers a parsed JSON document declares under `key`.

    Walks nested mappings because Claude Code uses the SAME key at two
    depths: `mcpServers` at the top level of `~/.claude.json` (user scope)
    and under `projects.<path>.mcpServers` (local scope). Only the number of
    entries is taken — no name, command, or argument value is ever read out
    (#449: doctor output is redaction-sensitive)."""
    if not isinstance(doc, dict) or depth > MCP_SCAN_MAX_DEPTH:
        return 0
    total = 0
    for k, v in doc.items():
        if k == key and isinstance(v, dict):
            total += len(v)
        elif isinstance(v, dict):
            total += _mcp_json_count(v, key, depth + 1)
    return total


def _mcp_source_count(path, key):
    """Servers declared in one config file: an int, or None when the file
    exists but cannot be read as configuration (unparseable, oversize,
    unreadable, or a format this build cannot parse). An ABSENT file is a
    legitimate "none configured", so it counts 0 — only a file we cannot
    interpret is unknown."""
    if not os.path.isfile(path):
        return 0
    try:
        if os.path.getsize(path) > MCP_CONFIG_MAX_BYTES:
            return None
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if path.lower().endswith(".toml"):
            import tomllib  # 3.11+; older interpreters degrade to unknown
            table = tomllib.loads(text).get(key)
            return len(table) if isinstance(table, dict) else 0
        return _mcp_json_count(json.loads(text), key)
    except Exception:  # noqa: BLE001 — a diagnostic must never be the failure
        return None


def check_mcp(host):
    """#270 (tribunal appsec-002): report that MCP tools are configured, and
    that writes performed through them are outside the write gate.

    The gap is real on every host — `mcp__<server>__<tool>` misses Claude's
    `Write`/`Edit` matchers and normalizes to "OTHER" on Codex — and it is
    ACCEPTED residual risk under ADR-0010, NOT something this check denies.
    What it does is make the acceptance visible where the risk actually
    lives: codeArbiter is BUILT in this repo but RUN in consumers' repos, so
    a build-time check here would never fire and security-controls.md alone
    reaches nobody who is carrying the risk. `/ca:doctor` does.

    Host-agnostic by construction: the config locations come from
    `host.mcp_config_sources()`, never from a hard-coded path. Every failure
    mode degrades to SILENCE — a host too old for the seam, a host that
    declares no sources, a raising seam, an unreadable or oversize file.
    /ca:doctor is the tool of last resort when enforcement misbehaves, so a
    diagnostic that errors is worse than one that is quiet.

    Reports a COUNT only. Server names, commands, arguments, and environment
    are never read out (#449)."""
    try:
        sources = host.mcp_config_sources(host.project_root())
    except Exception:  # noqa: BLE001 — no seam, or a seam that raised
        return
    if not sources:
        return  # this host's MCP surface is unknown — say nothing
    total, unknown = 0, False
    for source in sources or ():
        try:
            path, key = source
            count = _mcp_source_count(path, key)
        except Exception:  # noqa: BLE001 — malformed source descriptor
            count = None
        if count is None:
            unknown = True
        else:
            total += count
    if total > 0:
        warn(f"{total} MCP server{'s' if total != 1 else ''} configured for "
             f"this host — file writes made through an MCP tool "
             f"(mcp__<server>__<tool>) bypass the codeArbiter write gate: no "
             f"pre-write/pre-edit guard evaluates them and no gate event is "
             f"recorded. Accepted residual risk under ADR-0010 — keep "
             f"protected writes on this host's native write tools, or remove "
             f"MCP servers that can write files.")
    elif not unknown:
        ok("no MCP servers configured for this host — nothing bypasses the "
           "write gate through an MCP tool")


def check_statusline(root):
    settings = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
    try:
        with open(settings, encoding="utf-8") as f:
            cmd = (json.load(f).get("statusLine") or {}).get("command", "")
    except Exception:  # noqa: BLE001
        cmd = ""
    if "statusline.py" in cmd:
        ok("statusline wired in ~/.claude/settings.json")
    else:
        ok(f"statusline not wired (optional — "
           f"{get_host().cmd_ref('statusline')} installs it)")


def main():
    utf8_stdio()
    root = plugin_root()
    # get_host() (#257): resolves the SAME Host run(host) already primed via
    # set_host(), instead of a second hostapi.load_host() disk/probe.
    host = get_host()
    check_host(host)
    check_interpreters()
    check_payload(root, host)
    repo_root = check_repo()
    check_git_hook_freshness(repo_root)
    check_mcp(host)
    if getattr(host, "has_statusline", True):
        # A host with no statusline surface (Codex) must not read
        # ~/.claude/settings.json or advertise a statusline install path.
        # getattr with the Claude default so a duck-typed host (tests) that
        # declares no capability flags keeps today's behavior.
        check_statusline(root)
    width = max(len(lvl) for lvl, _ in results)
    for lvl, line in results:
        print(f"{lvl:<{width}}  {line}")
    fails = sum(1 for lvl, _ in results if lvl == "FAIL")
    warns = sum(1 for lvl, _ in results if lvl == "WARN")
    print(f"\ndoctor: {fails} FAIL, {warns} WARN, "
          f"{len(results) - fails - warns} OK")
    if fails:
        print("verdict: UNHEALTHY — at least one gate cannot function as installed")
        sys.exit(1)
    if get_host().name == "pi":
        print("verdict: healthy (static checks) — /ca-doctor adds a wrapper "
              "self-test and reports the active-dispatch coverage gap")
    else:
        print(f"verdict: healthy (static checks) — the live-fire probe in "
              f"{get_host().cmd_ref('doctor')} proves hooks actually fire")


def run(host, argv=None):
    """Host-seam entry point (ADR-0011): the __main__ guard calls this with the
    plugin's loaded Host. Wraps main() unchanged — main() still communicates
    via sys.exit/stdout/stderr, and its return value stays discarded exactly
    as the old bare `main()` guard discarded it (so the process still exits 0
    on a normal fall-through).

    Wires `host` live (#257): primes `_hooklib`'s process-cached Host via
    `set_host()` BEFORE main() runs, so `plugin_root()`/`main()`'s `get_host()`
    calls resolve to the SAME instance the caller passed here — no second
    `hostapi.load_host()`, and `run(fake_host)` genuinely exercises
    `fake_host`."""
    return _entrylib.dispatch(host, argv, main, set_host,
                               pass_argv=False, propagate_result=False)


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)

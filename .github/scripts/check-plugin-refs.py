#!/usr/bin/env python3
"""codeArbiter plugin reference checker (issue #28).

Validates the cross-reference graph of the prose surface — the bulk of a plugin
that JSON-parse and tools-test CI cannot see. Catches exactly the drift this design
is prone to (the kind that produced the /ca:refactor mis-route and the dangling
legacy/ASSESSMENT.md reference). Checks, per plugin:

  A. Every ${CLAUDE_PLUGIN_ROOT}/<concrete path> reference resolves to a real file
     (placeholder paths containing <...> are skipped).
  B. Every relative markdown link [text](path.md) inside the plugin resolves.
  C. agents/INDEX.md and the configured skill catalog list exactly the agents/skills on disk
     (a surface absent from disk is simply not checked — ca-sandbox ships no agents).
  D. The command catalog (COMMANDS.md) and commands/*.md agree — every command
     file is cataloged, every cataloged command has a file. Nothing is hidden.

The check is parameterized over the repository's four sibling plugins. Pass
plugin names as argv to scope the run (for example `check-plugin-refs.py ca-pi`);
with no args every known plugin is checked.

Exits non-zero listing every broken reference.
"""
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "tools"))

from host_descriptors import load_host_descriptors  # noqa: E402

# Each plugin declares the command namespace its COMMANDS.md catalog uses. The two
# sibling plugins are independent (ADR-0007); ca-sandbox commands are
# `/ca-sandbox:<name>`, ca commands are `/ca:<name>`.
PLUGINS = {
    "ca": {"namespace": "ca"},
    "ca-sandbox": {"namespace": "ca-sandbox"},
    # ca-codex (ADR-0011 M3): Codex has no command namespace — the catalog
    # mentions `$ca-<name>` skills and the command bodies live at
    # skills/ca-<name>/SKILL.md. `pending_prefixes` allowlists plugin-root
    # references to surfaces a later milestone ships (agents/ arrives with M4
    # as .codex/agents TOML scaffolding — REMOVE the allowlist entry in M4).
    # tools/ = the farm execution backend (farm.js, plan.schema.json), which
    # ca-codex does not vendor yet — --farm is a Feature Forge preview and its
    # Codex packaging is an M5 distribution decision (docs/parity.md row).
    "ca-codex": {"namespace": None, "skill_prefix": "ca-", "catalog_prefix": "$ca-",
                 "pending_prefixes": ("agents/", "tools/", "tools")},
    # Pi packages generated ca-* entry skills plus /ca-* aliases. Its command
    # catalog uses the alias spelling while the directory bijection remains the
    # same as Codex's namespace-less skill layout.
    "ca-pi": {"namespace": None, "skill_prefix": "ca-", "catalog_prefix": "/ca-"},
}


def plugin_configs(repo=REPO):
    """Return plugin checks with descriptor-owned generated catalog paths."""
    configs = {name: dict(cfg) for name, cfg in PLUGINS.items()}
    for descriptor in load_host_descriptors(repo):
        plugin_name = os.path.basename(descriptor.plugin_dir)
        if plugin_name in configs and descriptor.catalog is not None:
            configs[plugin_name]["skill_catalog"] = descriptor.catalog
    return configs


errors = []


def gitignored(abspath):
    """A reference to a gitignored path (e.g. tools/.env, created at runtime) is
    not drift — the file is intentionally absent from the repo."""
    try:
        return subprocess.run(
            ["git", "check-ignore", "-q", abspath], cwd=REPO, timeout=5
        ).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def rel(p):
    return os.path.relpath(p, REPO)


def md_files(base):
    for cur, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d != "node_modules"]
        for f in files:
            if f.endswith(".md"):
                yield os.path.join(cur, f)


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


PLUGIN_REF = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\s`\"')]+)")
MD_LINK = re.compile(r"\]\(([^)]+)\)")


def check_index(index_path, present, label):
    if not os.path.isfile(index_path):
        errors.append(f"{rel(index_path)}: missing")
        return
    text = read(index_path)
    for name in present:
        if name not in text:
            errors.append(f"{rel(index_path)}: {label} '{name}' on disk but not listed")


def check_plugin(name, cfg):
    namespace = cfg.get("namespace")
    pending = tuple(cfg.get("pending_prefixes", ()))
    plugin = os.path.join(REPO, "plugins", name)
    if not os.path.isdir(plugin):
        errors.append(f"plugins/{name}: plugin directory missing")
        return

    # --- A. ${CLAUDE_PLUGIN_ROOT}/... references --------------------------------
    for path in md_files(plugin):
        for m in PLUGIN_REF.finditer(read(path)):
            target = m.group(1)
            if "<" in target or ">" in target:  # placeholder, e.g. agents/<name>.md
                continue
            target = target.rstrip(".,;:")
            if pending and target.startswith(pending):
                continue  # surface a declared later milestone ships (see PLUGINS)
            full = os.path.join(plugin, target)
            if not os.path.exists(full) and not gitignored(full):
                errors.append(f"{rel(path)}: dangling ${{CLAUDE_PLUGIN_ROOT}}/{target}")

    # --- B. relative markdown links ---------------------------------------------
    for path in md_files(plugin):
        base = os.path.dirname(path)
        for m in MD_LINK.finditer(read(path)):
            link = m.group(1).strip()
            if link.startswith(("http://", "https://", "#", "mailto:")) or "<" in link:
                continue
            if "${" in link:  # handled by check A
                continue
            target = link.split("#", 1)[0]
            if not target.endswith(".md"):
                continue
            if not os.path.exists(os.path.normpath(os.path.join(base, target))):
                errors.append(f"{rel(path)}: dangling link ({link})")

    # --- C. INDEX <-> directory consistency -------------------------------------
    # A surface a plugin doesn't ship (ca-sandbox has no agents/) is not drift —
    # only check the index when the directory exists on disk.
    agents_dir = os.path.join(plugin, "agents")
    if os.path.isdir(agents_dir):
        agent_files = {
            f[:-3] for f in os.listdir(agents_dir)
            if f.endswith(".md") and f != "INDEX.md"
        }
        check_index(os.path.join(agents_dir, "INDEX.md"), agent_files, "agent")

    skills_dir = os.path.join(plugin, "skills")
    if os.path.isdir(skills_dir):
        skill_names = {
            d for d in os.listdir(skills_dir)
            if os.path.isfile(os.path.join(skills_dir, d, "SKILL.md"))
        }
        catalog = cfg.get("skill_catalog", "skills/INDEX.md")
        check_index(os.path.join(plugin, catalog), skill_names, "skill")

    # --- D. command catalog <-> command bodies ----------------------------------
    # A namespace-less plugin (ca-codex) catalogs `$<prefix><name>` entry
    # skills instead of `/<ns>:<name>` command files; same bijection contract.
    prefix = cfg.get("skill_prefix")
    catalog_prefix = cfg.get("catalog_prefix")
    if namespace is None and prefix and catalog_prefix:
        skills_dir = os.path.join(plugin, "skills")
        entry_stems = set()
        if os.path.isdir(skills_dir):
            entry_stems = {
                d[len(prefix):] for d in os.listdir(skills_dir)
                if d.startswith(prefix)
                and os.path.isfile(os.path.join(skills_dir, d, "SKILL.md"))
            }
        commands_md = os.path.join(plugin, "COMMANDS.md")
        catalog = read(commands_md) if os.path.isfile(commands_md) else ""
        mention_re = re.compile(re.escape(catalog_prefix) + r"([a-z][a-z-]*)")
        catalog_cmds = set(mention_re.findall(catalog))
        for stem in entry_stems:
            if stem not in catalog_cmds:
                errors.append(
                    f"plugins/{name}/COMMANDS.md: skill '{catalog_prefix}{stem}' "
                    f"(skills/{prefix}{stem}/SKILL.md) not in the catalog")
        for cmd in catalog_cmds:
            if cmd not in entry_stems:
                errors.append(
                    f"plugins/{name}/COMMANDS.md: '{catalog_prefix}{cmd}' in catalog "
                    f"has no skills/{prefix}{cmd}/SKILL.md")
        return

    commands_dir = os.path.join(plugin, "commands")
    if os.path.isdir(commands_dir):
        command_stems = {
            f[:-3] for f in os.listdir(commands_dir) if f.endswith(".md")
        }
        commands_md = os.path.join(plugin, "COMMANDS.md")
        catalog = read(commands_md) if os.path.isfile(commands_md) else ""
        cmd_re = re.compile(r"/" + re.escape(namespace) + r":([a-z][a-z-]*)")
        catalog_cmds = set(cmd_re.findall(catalog))

        for stem in command_stems:
            if stem not in catalog_cmds:
                errors.append(
                    f"plugins/{name}/COMMANDS.md: command "
                    f"'/{namespace}:{stem}' (commands/{stem}.md) not in the catalog"
                )
        for cmd in catalog_cmds:
            if cmd not in command_stems:
                errors.append(
                    f"plugins/{name}/COMMANDS.md: '/{namespace}:{cmd}' in catalog "
                    f"has no commands/{cmd}.md"
                )


def main():
    plugins = plugin_configs()
    requested = sys.argv[1:]
    if requested:
        unknown = [p for p in requested if p not in plugins]
        if unknown:
            print(f"unknown plugin(s): {', '.join(unknown)}", file=sys.stderr)
            print(f"known: {', '.join(sorted(plugins))}", file=sys.stderr)
            sys.exit(2)
        names = requested
    else:
        names = sorted(plugins)

    for name in names:
        check_plugin(name, plugins[name])

    if errors:
        print("Plugin reference check FAILED:\n")
        for e in sorted(set(errors)):
            print(f"  - {e}")
        sys.exit(1)
    print(f"Plugin reference graph intact ({', '.join(names)}).")


if __name__ == "__main__":
    main()

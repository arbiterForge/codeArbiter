#!/usr/bin/env python3
"""codeArbiter plugin reference checker (issue #28).

Validates the cross-reference graph of the prose surface — the bulk of the plugin
that JSON-parse and farm-test CI cannot see. Catches exactly the drift this design
is prone to (the kind that produced the /ca:refactor mis-route and the dangling
legacy/ASSESSMENT.md reference). Checks:

  A. Every ${CLAUDE_PLUGIN_ROOT}/<concrete path> reference resolves to a real file
     (placeholder paths containing <...> are skipped).
  B. Every relative markdown link [text](path.md) inside plugins/ca resolves.
  C. agents/INDEX.md and skills/INDEX.md list exactly the agents/skills on disk.
  D. The command catalog (COMMANDS.md) and commands/*.md agree (hidden commands —
     sprint, dev, arbiter — are intentionally absent and excluded).

Exits non-zero listing every broken reference.
"""
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PLUGIN = os.path.join(REPO, "plugins", "ca")
HIDDEN_COMMANDS = {"sprint", "dev", "arbiter"}

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


# --- A. ${CLAUDE_PLUGIN_ROOT}/... references ------------------------------------
PLUGIN_REF = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\s`\"')]+)")
for path in md_files(PLUGIN):
    for m in PLUGIN_REF.finditer(read(path)):
        target = m.group(1)
        if "<" in target or ">" in target:  # placeholder, e.g. agents/<name>.md
            continue
        target = target.rstrip(".,;:")
        full = os.path.join(PLUGIN, target)
        if not os.path.exists(full) and not gitignored(full):
            errors.append(f"{rel(path)}: dangling ${{CLAUDE_PLUGIN_ROOT}}/{target}")

# --- B. relative markdown links -------------------------------------------------
MD_LINK = re.compile(r"\]\(([^)]+)\)")
for path in md_files(PLUGIN):
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

# --- C. INDEX ↔ directory consistency -------------------------------------------
def check_index(index_path, present, label):
    if not os.path.isfile(index_path):
        errors.append(f"{rel(index_path)}: missing")
        return
    text = read(index_path)
    for name in present:
        if name not in text:
            errors.append(f"{rel(index_path)}: {label} '{name}' on disk but not listed")


# agents: every agents/*.md (except INDEX) named in INDEX.md
agents_dir = os.path.join(PLUGIN, "agents")
agent_files = {f[:-3] for f in os.listdir(agents_dir) if f.endswith(".md") and f != "INDEX.md"}
check_index(os.path.join(agents_dir, "INDEX.md"), agent_files, "agent")

# skills: every skills/<name>/ named in INDEX.md
skills_dir = os.path.join(PLUGIN, "skills")
skill_names = {
    d for d in os.listdir(skills_dir)
    if os.path.isfile(os.path.join(skills_dir, d, "SKILL.md"))
}
check_index(os.path.join(skills_dir, "INDEX.md"), skill_names, "skill")

# --- D. command catalog ↔ commands/*.md -----------------------------------------
commands_dir = os.path.join(PLUGIN, "commands")
command_stems = {f[:-3] for f in os.listdir(commands_dir) if f.endswith(".md")}
commands_md = os.path.join(PLUGIN, "COMMANDS.md")
catalog = read(commands_md) if os.path.isfile(commands_md) else ""
catalog_cmds = set(re.findall(r"/ca:([a-z][a-z-]*)", catalog))

for stem in command_stems:
    if stem not in catalog_cmds:
        errors.append(f"COMMANDS.md: command '/ca:{stem}' (commands/{stem}.md) not in the catalog")
for cmd in catalog_cmds:
    if cmd in HIDDEN_COMMANDS:
        errors.append(f"COMMANDS.md: hidden command '/ca:{cmd}' must not appear in the catalog")
    elif cmd not in command_stems:
        errors.append(f"COMMANDS.md: '/ca:{cmd}' in catalog has no commands/{cmd}.md")

# --- report ---------------------------------------------------------------------
if errors:
    print("Plugin reference check FAILED:\n")
    for e in sorted(set(errors)):
        print(f"  - {e}")
    sys.exit(1)
print("Plugin reference graph intact.")

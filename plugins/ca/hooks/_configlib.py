"""codeArbiter config core — registry, resolution, settings.json persistence.

The registry (config/registry.json) is the single source of truth for every
user-tunable environment variable across the plugin family (CODEARBITER_*,
FARM_*, CA_SANDBOX_*). This module loads and validates it, resolves each
setting's effective value and provenance, and persists changes into Claude
Code settings.json ``env`` blocks — the one mechanism every existing reader
(Python hooks, the TypeScript farm engine, command prose) already honors,
because the host exports those entries as real environment variables at
session start.

Persistence layers, most- to least-specific:

    session env  >  .claude/settings.local.json  >  .claude/settings.json  >  ~/.claude/settings.json  >  registry default

The session environment is reported as ground truth — it is what hooks see
RIGHT NOW. When a settings layer disagrees with the session, both are
surfaced ("pending restart, or overridden by shell") rather than asserting a
precedence the host does not document.

Everything here is dependency-injectable (environ/paths are parameters) per
hook-lib convention, and stdlib-only per ADR 0004.
"""

import difflib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hooklib  # noqa: E402

VALID_TYPES = ("bool", "enum", "int", "float", "string", "path")
VALID_SCOPES = ("user", "project")          # registry *hints*
WRITE_SCOPES = ("user", "project", "local")  # actual write targets
VALID_STATUS = ("stable", "preview")

_BOOL_TRUE = ("1", "true", "on", "yes")
_BOOL_FALSE = ("0", "false", "off", "no")

# Layer precedence when reporting the "settings" side of the resolution.
_LAYER_ORDER = ("local", "project", "user")


class RegistryError(ValueError):
    """The registry file is malformed — a packaging bug, not a user error."""


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

def plugin_root(explicit=None):
    """`explicit` wins (tests); else CLAUDE_PLUGIN_ROOT; else derived from this
    file's own location — always the ACTUAL running install."""
    return explicit or os.environ.get("CLAUDE_PLUGIN_ROOT") or \
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def registry_path(root=None):
    return os.path.join(plugin_root(root), "config", "registry.json")


def load_registry(path=None):
    """Load and schema-validate the registry. Raises RegistryError on any
    malformation — the registry ships with the plugin and is CI-tested, so a
    failure here means a broken install, never bad user input."""
    p = path or registry_path()
    with open(p, encoding="utf-8") as f:
        reg = json.load(f)
    if not isinstance(reg, dict) or reg.get("version") != 1:
        raise RegistryError("registry version must be 1")
    groups = reg.get("groups")
    if not isinstance(groups, dict) or not groups:
        raise RegistryError("registry needs a non-empty groups map")
    settings = reg.get("settings")
    if not isinstance(settings, list) or not settings:
        raise RegistryError("registry needs a non-empty settings list")

    seen = set()
    for e in settings:
        name = e.get("name")
        if not name or name in seen:
            raise RegistryError("duplicate or missing setting name: %r" % name)
        seen.add(name)
        if e.get("group") not in groups:
            raise RegistryError("%s: unknown group %r" % (name, e.get("group")))
        t = e.get("type")
        if t not in VALID_TYPES:
            raise RegistryError("%s: unknown type %r" % (name, t))
        if t == "enum":
            vals = e.get("values")
            if not isinstance(vals, list) or len(vals) < 2:
                raise RegistryError("%s: enum needs >=2 values" % name)
            if e.get("default") is not None and e["default"] not in vals:
                raise RegistryError("%s: default %r not in values" % (name, e["default"]))
        if not (e.get("description") or "").strip():
            raise RegistryError("%s: empty description" % name)
        if e.get("scope", "user") not in VALID_SCOPES:
            raise RegistryError("%s: bad scope %r" % (name, e.get("scope")))
        if e.get("status", "stable") not in VALID_STATUS:
            raise RegistryError("%s: bad status %r" % (name, e.get("status")))
    return reg


def entries_by_name(reg):
    return {e["name"]: e for e in reg["settings"]}


def find_entry(reg, name):
    """Exact lookup, or (None, suggestion) — suggestion is the closest
    registered name for typo messaging."""
    by_name = entries_by_name(reg)
    if name in by_name:
        return by_name[name], None
    close = difflib.get_close_matches(name, list(by_name), n=1, cutoff=0.6)
    return None, (close[0] if close else None)


# --------------------------------------------------------------------------- #
# Settings.json layers
# --------------------------------------------------------------------------- #

def settings_paths(project_dir=None, home=None):
    """The three writable layers. Project root: explicit > CLAUDE_PROJECT_DIR
    > cwd. Home: explicit > ~ (tests pass both)."""
    proj = project_dir or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    h = home or os.path.expanduser("~")
    return {
        "user": os.path.join(h, ".claude", "settings.json"),
        "project": os.path.join(proj, ".claude", "settings.json"),
        "local": os.path.join(proj, ".claude", "settings.local.json"),
    }


def load_settings(path):
    """(data, existed). Refuses to proceed on unparseable JSON — settings.json
    is the user's whole host configuration; never risk clobbering it
    (pattern lifted from wire-statusline.py)."""
    if not os.path.exists(path):
        return {}, False
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        return (json.loads(text) if text.strip() else {}), True
    except ValueError as e:
        raise SystemExit(
            "REFUSING TO WRITE: %s is not valid JSON (%s). "
            "Fix it by hand, then re-run - I will not clobber an unparseable settings file."
            % (path, e))


def save_settings(path, data):
    """Atomic write via _hooklib.write_text_atomic (unique temp + os.replace,
    reliability-009) — settings.json is user-owned; a race must never leave it
    half-written."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _hooklib.write_text_atomic(path, json.dumps(data, indent=2) + "\n")


def env_layers(paths):
    """Raw ``env`` blocks of every layer that exists. Values coerced to str —
    a hand-edited numeric literal in settings.json must not break rendering."""
    out = {}
    for scope in _LAYER_ORDER:
        data, existed = load_settings(paths[scope])
        block = data.get("env") if existed else None
        if isinstance(block, dict):
            out[scope] = {k: str(v) for k, v in block.items()}
        else:
            out[scope] = {}
    return out


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #

def default_str(entry):
    """Registry default rendered the way it would appear in the environment;
    None (unset-by-default) renders as None."""
    d = entry.get("default")
    if d is None:
        return None
    if entry["type"] == "bool":
        return "1" if d else "0"
    if isinstance(d, float) and d == int(d):
        return str(int(d)) if entry["type"] == "int" else ("%g" % d)
    return str(d)


def resolve(entry, environ, layers):
    """Effective value + provenance for one setting.

    Returns {effective, source, layers, settings_value, settings_source,
    pending} where `pending` flags a settings-layer value that differs from
    the live session (restart not yet taken, or shell override in play)."""
    name = entry["name"]
    settings_value = settings_source = None
    for scope in _LAYER_ORDER:
        if name in layers.get(scope, {}):
            settings_value, settings_source = layers[scope][name], scope
            break

    if name in environ:
        effective, source = environ[name], "session"
    elif settings_source is not None:
        effective, source = settings_value, settings_source
    else:
        effective, source = default_str(entry), "default"

    pending = (source == "session" and settings_source is not None
               and settings_value != effective)
    return {
        "effective": effective,
        "source": source,
        "layers": {s: layers.get(s, {}).get(name) for s in _LAYER_ORDER},
        "settings_value": settings_value,
        "settings_source": settings_source,
        "pending": pending,
    }


def masked(entry, value):
    if value is None:
        return None
    return "********" if entry.get("sensitive") else value


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def validate(entry, raw):
    """(ok, normalized, message). `normalized` is the exact string to persist
    — enum spellings lowercased, bools canonicalized to the 1/0 the strictest
    readers (CODEARBITER_DEV, FARM_ALLOW_EXTERNAL_WORKTREE_ROOT) require."""
    t = entry["type"]
    s = str(raw).strip()
    if not s:
        return False, None, "empty value — use `unset` to clear a setting"
    if t == "enum":
        low = s.lower()
        if low in entry["values"]:
            return True, low, None
        return False, None, "must be one of: %s" % ", ".join(entry["values"])
    if t == "bool":
        low = s.lower()
        if low in _BOOL_TRUE:
            return True, "1", None
        if low in _BOOL_FALSE:
            return True, "0", None
        return False, None, "must be a boolean (1/0, on/off, true/false, yes/no)"
    if t in ("int", "float"):
        try:
            n = int(s) if t == "int" else float(s)
        except ValueError:
            return False, None, "must be a%s number" % ("n integer" if t == "int" else "")
        if "min" in entry and n < entry["min"]:
            return False, None, "must be >= %s" % entry["min"]
        if "max" in entry and n > entry["max"]:
            return False, None, "must be <= %s" % entry["max"]
        return True, ("%d" % n) if t == "int" else ("%g" % n), None
    # string / path: taken verbatim
    return True, s, None


def requires_warning(entry, reg, environ, layers):
    """None, or a one-line warning when this setting's `requires` gate is not
    currently satisfied (warning, never a refusal — the user may be about to
    set the prerequisite too)."""
    req = entry.get("requires")
    if not req:
        return None
    by_name = entries_by_name(reg)
    for dep_name, allowed in req.items():
        dep = by_name.get(dep_name)
        if dep is None:
            continue
        eff = resolve(dep, environ, layers)["effective"]
        if eff not in allowed:
            return ("note: %s only takes effect while %s is %s (currently: %s)"
                    % (entry["name"], dep_name, "/".join(allowed), eff if eff is not None else "unset"))
    return None


# --------------------------------------------------------------------------- #
# Mutation
# --------------------------------------------------------------------------- #

RESTART_NOTICE = ("Applies at the NEXT session start — Claude Code exports "
                  "settings.json env entries when a session launches, not live.")


def set_value(reg, name, raw, scope, paths, environ=None):
    """Validate and persist. Returns a report dict; raises SystemExit with a
    user-actionable message on refusal (unknown key, bad value, sensitive,
    bad scope)."""
    environ = environ if environ is not None else os.environ
    if scope not in WRITE_SCOPES:
        raise SystemExit("unknown scope %r (use: user, project, local)" % scope)
    entry, suggestion = find_entry(reg, name)
    if entry is None:
        hint = (" — did you mean %s?" % suggestion) if suggestion else ""
        raise SystemExit("unknown setting %r%s (see `list` for the full inventory)" % (name, hint))
    if entry.get("sensitive"):
        raise SystemExit(
            "%s is sensitive and is never persisted to settings.json. "
            "Export it in your shell profile instead (e.g. `export %s=...`)."
            % (name, name))
    ok, normalized, msg = validate(entry, raw)
    if not ok:
        raise SystemExit("invalid value for %s: %s" % (name, msg))

    path = paths[scope]
    data, _ = load_settings(path)
    env_block = data.setdefault("env", {})
    prior = env_block.get(name)
    if prior == normalized:
        return {"name": name, "value": normalized, "prior": prior, "scope": scope,
                "path": path, "changed": False,
                "warning": requires_warning(entry, reg, environ, env_layers(paths))}
    env_block[name] = normalized
    save_settings(path, data)
    return {"name": name, "value": normalized, "prior": prior, "scope": scope,
            "path": path, "changed": True,
            "warning": requires_warning(entry, reg, environ, env_layers(paths))}


def unset_value(reg, name, scope, paths):
    if scope not in WRITE_SCOPES:
        raise SystemExit("unknown scope %r (use: user, project, local)" % scope)
    entry, suggestion = find_entry(reg, name)
    if entry is None:
        hint = (" — did you mean %s?" % suggestion) if suggestion else ""
        raise SystemExit("unknown setting %r%s" % (name, hint))
    path = paths[scope]
    data, existed = load_settings(path)
    env_block = data.get("env") or {}
    if name not in env_block:
        return {"name": name, "prior": None, "scope": scope, "path": path, "changed": False}
    prior = env_block.pop(name)
    if not env_block:
        data.pop("env", None)
    save_settings(path, data)
    return {"name": name, "prior": prior, "scope": scope, "path": path, "changed": True}


# --------------------------------------------------------------------------- #
# Doctor
# --------------------------------------------------------------------------- #

_PREFIXES = ("CODEARBITER_", "FARM_", "CA_SANDBOX_")

# Real env vars that are injected by the plugin itself (never user-set), so
# doctor must not flag them as typos.
KNOWN_INTERNAL = {"FARM_MUTATION_FILES", "FARM_MUTATION_TEST_PATH", "FARM_MUTATION_TEST_CMD"}


def doctor(reg, environ, paths):
    """Validate everything currently set; flag unknown plugin-prefixed names
    (typos) and sensitive keys that leaked into a settings file. Returns a
    list of {level, message} findings — empty means healthy."""
    findings = []
    layers = env_layers(paths)
    by_name = entries_by_name(reg)

    def check_value(name, raw, where):
        entry = by_name.get(name)
        if entry is None:
            if name in KNOWN_INTERNAL or not name.startswith(_PREFIXES):
                return
            close = difflib.get_close_matches(name, list(by_name), n=1, cutoff=0.6)
            hint = (" — did you mean %s?" % close[0]) if close else ""
            findings.append({"level": "warn",
                             "message": "unregistered variable %s in %s%s" % (name, where, hint)})
            return
        if entry.get("sensitive") and where != "session env":
            findings.append({"level": "error",
                             "message": "%s is sensitive but persisted in %s — remove it and export in your shell instead" % (name, where)})
        ok, _, msg = validate(entry, raw)
        if not ok:
            findings.append({"level": "error",
                             "message": "%s in %s has invalid value %r: %s" % (name, where, raw, msg)})

    for name, raw in sorted(environ.items()):
        if name.startswith(_PREFIXES):
            check_value(name, raw, "session env")
    for scope in _LAYER_ORDER:
        for name, raw in sorted(layers.get(scope, {}).items()):
            if name.startswith(_PREFIXES):
                check_value(name, raw, "%s settings (%s)" % (scope, paths[scope]))
    return findings


# --------------------------------------------------------------------------- #
# Listing (shared by CLI, --json contract, and the interactive picker)
# --------------------------------------------------------------------------- #

def snapshot(reg, environ, paths, group=None):
    """One resolved record per setting — the `list --json` contract."""
    layers = env_layers(paths)
    out = []
    for entry in reg["settings"]:
        if group and entry["group"] != group:
            continue
        r = resolve(entry, environ, layers)
        out.append({
            "name": entry["name"],
            "group": entry["group"],
            "type": entry["type"],
            "values": entry.get("values"),
            "default": default_str(entry),
            "effective": masked(entry, r["effective"]),
            "source": r["source"],
            "pending": r["pending"],
            "layers": {s: masked(entry, v) for s, v in r["layers"].items()},
            "description": entry["description"],
            "status": entry.get("status", "stable"),
            "scope": entry.get("scope", "user"),
            "sensitive": bool(entry.get("sensitive")),
        })
    return out

# Skill: ticketing-router (router)

## Trigger

> *"This section lists conditions under which the orchestrator routes work to this skill. The skill itself does not 'trigger' — it is routed to."*

Invoke this skill when:

- A subagent encounters a finding outside its scope and needs to file it without
  inlining it (per the subagent out-of-scope contract).
- The user runs any `/ticket` subcommand (`open`, `close`, `show`, `list`, `config`).
- The codeArbiter parent needs to file, triage, or close a scope-overflow inbox item.

This skill is a **thin router**. It reads `${PROJECT_ROOT}/.agents/projectContext/ticketing-config.md`,
selects the variant by `mode`, and `@`-imports only that variant's `SKILL.md`. It
never loads both variants in the same session. When ticketing is disabled, no
variant is loaded.

---

## Pre-Flight

Before any routing decision, confirm:

1. `${PROJECT_ROOT}/.agents/projectContext/ticketing-config.md` is readable. If absent, treat
   ticketing as disabled and return the disabled response below.
2. Read only the frontmatter (top YAML block) of the config file. Do not read
   the prose body — the field reference is for humans, not for routing.

If the file is unreadable for reasons other than absence (permission error,
malformed YAML), STOP and surface the gap to the user. Do not guess defaults.

---

## Phase 1: Resolve mode

**Goal:** Determine whether to invoke a variant and which one.

**Inputs:**
- Frontmatter of `${PROJECT_ROOT}/.agents/projectContext/ticketing-config.md`

**Actions:**

1. If `enabled: false` (or field absent): emit the disabled response and return.
   The disabled response is:

   > Ticketing is disabled. Findings that would normally be filed as tickets
   > are inlined in agent output with a `[NEEDS-TRIAGE]` marker. To enable,
   > edit `${PROJECT_ROOT}/.agents/projectContext/ticketing-config.md` and set `enabled: true`.

2. If `enabled: true` and `mode: in-repo`: `@`-import
   `${FRAMEWORK_ROOT}/.agents/skills/ticketing-router/in-repo/SKILL.md` and hand off the caller's request
   to that variant. Do not read the plane variant.

3. If `enabled: true` and `mode: plane`: confirm `plane_base_url`,
   `plane_workspace_slug`, and `plane_project_id` are populated. If any is
   missing, STOP and instruct the user to complete the config. Then `@`-import
   `${FRAMEWORK_ROOT}/.agents/skills/ticketing-router/plane/SKILL.md` and hand off. Do not read the
   in-repo variant.

4. If `mode` is any other value: STOP and surface as a config error. Do not
   guess a default.

**Output:** Variant loaded and caller's operation delegated, OR disabled
response returned.

**Gate:** BLOCK if both variants are loaded in the same invocation. BLOCK if
the disabled state silently loads a variant.

---

## Hard Rules

- MUST read only the frontmatter of `ticketing-config.md`. The prose body is
  for human reference and is NOT part of the routing contract.
- MUST NOT load both variants in the same session. The router is a one-way
  dispatch.
- MUST NOT guess a default `mode`. An invalid or missing `mode` is a config
  error to surface, not a silent fallback.
- MUST NOT read ticket bodies, write tickets, or call MCP tools directly. The
  router has no operational logic — variants own all behavior.
- MUST NOT silently disable ticketing because of a config parse error. Surface
  the error.

---

## Failure Modes

| Failure | Response |
|---|---|
| `ticketing-config.md` absent | Treat as disabled; emit disabled response |
| Config unreadable / malformed YAML | STOP; surface gap; do not guess defaults |
| `enabled: true` but `mode` missing or unknown | STOP; surface as config error |
| `mode: plane` but Plane fields missing | STOP; instruct user to complete config |
| Variant `SKILL.md` missing on disk | STOP; surface as install gap |

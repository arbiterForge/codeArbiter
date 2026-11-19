---
description: Clone a network repository into a Docker named volume, build with installed nixpacks or the packaged Node/Python fallback, and explore under offline runtime isolation. Requires Docker and Node.
argument-hint: "<repo url> [--net offline|clone-then-cut|allowlist]"
---

# /ca-sandbox:sandbox

Follow `${CLAUDE_PLUGIN_ROOT}/skills/sandbox-lifecycle/SKILL.md` and invoke `node <plugin>/tools/sandbox.js create <url>`. Check `docker info`; never install a builder implicitly. Missing nixpacks uses the supported Node/Python fallback and reports the effective builder. Existing WSL nixpacks may generate the Dockerfile for a host Docker build.

Clone lives in a named volume. Build temporarily stages a copy on the host; the exploration container has no host bind, socket or privileged mode and runs non-root on a read-only root. Dependencies live at `/deps`, source at `/work/repo`.

Report requested/effective policy: ordinary runtime is offline for all currently accepted names, including `clone-then-cut` and `allowlist`. Clone/build still fetch remotely. The experimental allowlist helper is not integrated into ordinary create; do not grant incidental network access. Claude inside the box uses the separate `sandbox-claude-inside` routine.

Return the exact sandbox/container/volume identities. Shell exit detaches. Explicit `sandbox destroy <id>` removes only that instance; broad `sandbox prune` needs its own stated scope. Report uncertain cleanup with retained identities; never silently sweep other sandboxes.

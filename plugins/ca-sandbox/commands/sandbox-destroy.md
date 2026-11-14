---
description: Remove one named sandbox container and volume; --keep-volume preserves its source. Explicit --prune selects a separate broad snapshot. Cached images remain.
argument-hint: "<sandbox id> [--keep-volume] | --prune"
---

# /ca-sandbox:sandbox-destroy

Use `${CLAUDE_PLUGIN_ROOT}/skills/sandbox-lifecycle/SKILL.md` Phase explicit teardown.

Translate a named request to `node <plugin>/tools/sandbox.js destroy <id> [--keep-volume]`. Remove only the plugin-labeled objects of that exact id. Other sandboxes remain intact; shell detachment does not destroy anything. An omitted id is an error, not authority to prune.

Only an explicit broad prune request maps to `node <plugin>/tools/sandbox.js prune`. Its targets are the initial discovery snapshot. Do not add newly created or unrelated instances to this sweep, and never follow named destroy with automatic prune.

Return the driver's removed/kept/remaining/failure fields. Verify absence of targeted containers and volumes, and report discovery or verification failure as unavailable. Teardown failure exits nonzero and retains exact references for inspection. Cached `ca-sbx:v2-<sha256>` and historical cache images are intentionally retained.

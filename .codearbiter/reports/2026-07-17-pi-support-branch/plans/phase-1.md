# Phase plan — wave 1 (appsec / architecture / reliability)

## Group: bridge-hardening (reliability-001 + reliability-003) — one issue
Harden ca-pi bridge.ts failure paths: bounded taskkill (timeout + child.kill fallback +
post-kill settle deadline) and a constructor-attached rejection guard on `ready`.
Acceptance: no wedge when taskkill fails; no unhandled rejection when validatePaths
rejects before first call(). Effort S–M. No dependencies.

## Singles
- reliability-004 — wrap write_standup_marker in the sibling swallow-and-continue guard (S).
- reliability-005 — temp+os.replace atomic writes in sync-core.py (S).
- architecture-001 — extract _bashguardlib.py from pre-bash.py; split _run per gate (M).
- architecture-002 — partition _hooklib.py along concern seams (_activationlib, _sensitivelib) (M–L; sequence AFTER architecture-001 to avoid double-churn on the same sync surface; depends_on: architecture-001).
- architecture-003 — delete 3 dead ca-pi exports, rebuild bundles (S).

## Investigate (not filed)
- reliability-002 (spawn-error listener window — needs repro), architecture-004 (prune accretion — opportunistic).

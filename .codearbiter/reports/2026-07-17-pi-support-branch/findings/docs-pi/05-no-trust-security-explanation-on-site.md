# 05 — No user-facing explanation of the project-trust gate / child env minimization

**Severity:** high

**Page path:** missing page. `site/src/content/docs/enforcement.md` (the
"Enforcement & Security" concept page in the nav) has zero Pi mentions.

**What the user was trying to do:** A security-conscious new user wants to
understand, before or right after installing `ca-pi`, what gate stands
between "plugin installed" and "plugin can act on my repo" — and what a
malicious or misbehaving child/subagent process could or couldn't do.

**What's missing:** `plugins/ca-pi/includes/pi-host-notes.md` states the
parent "registers repository-aware dispatch, farm preview, and native
compaction only after the current session reports affirmative project trust,
the repository is enabled, and the enforcement lifecycle is ready" — and that
"ordinary child environments never receive `FARM_API_KEY`." `README.md` line
125 adds "grant Pi project trust, start a fresh session." None of this
trust-gate mechanic, nor the child-environment minimization guarantee, is
explained anywhere on the site in user-facing terms. The site's own
`enforcement.md` page is the natural home and currently doesn't mention Pi at
all, so a Pi user reading it gets a Claude-Code/Codex-only picture of the
security model.

**What's missing, concretely:**
1. What "affirmative project trust" means as a user-visible action/prompt in
   Pi, and why nothing runs without it.
2. That `codearbiter_dispatch` / `codearbiter_farm_preview` are parent-only
   EXEC tools — a child process cannot escalate itself into repository-aware
   dispatch.
3. That ordinary child/subagent environments do not receive secrets like
   `FARM_API_KEY`.
4. That `/ca:doctor` (or `/ca-doctor` on Pi) can be used to verify all this is
   actually live — self-consistency only, "not publisher authenticity" (per
   `pi-host-notes.md` and enforced by
   `test_public_pi_docs.py::test_module_identity_claim_is_scoped_to_self_consistency`).

**Remediation shape:** Add a "Pi" subsection to `enforcement.md` (or the new
Pi install page from finding 01) explaining the project-trust gate, the
parent-only dispatch tools, and child-env secret minimization in plain
language, plus a pointer to `/ca-doctor`.

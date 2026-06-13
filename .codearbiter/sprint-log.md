# Sprint log — checkpoint-remediation-2026-06-12

Append-only. Every auto-decision logged with SMARTS verdict and confidence flag.
`low` entries = review these in the morning.

---

<!-- entries appended below -->

---

# Sprint log — checkpoint-2026-06-13-remediation
Started 2026-06-13. Append-only. SMARTS-scored auto-decisions; `low` = review these.

## SD-01 — Pre-flight checkpoint-artifact commit path · confidence: low
- **Point:** How to commit the outstanding checkpoint artifacts (2026-06-13.md, last-checkpoint, overrides.log) at task 0 without violating §3 "MUST NOT commit without commit-gate."
- **Options:** (a) direct git commit now; (b) leave staged, land via commit-gate as a separate logical `chore(checkpoint)` commit during the landing phase.
- **SMARTS:** Reliable/Securable favor (b) — honors the §3 hard rule, single gated commit path, no precedent of bypassing commit-gate for "just docs." Maintainable neutral. 
- **Chosen:** (b). Branch + farm.js revert done at task 0; artifacts carried uncommitted into the gated landing. Strength: moderate.

## SD-02 — Apply LOW URL-parse hardening to assertSecureBaseUrl · confidence: low
- **Point:** security-reviewer PASS on Workstream B with one LOW (optional): regex-based scheme/loopback check vs new URL() parsing. "No present vulnerability," remediation provided.
- **Options:** (a) accept PASS as-is, log LOW as deferred; (b) apply the URL-parse hardening now within the same guard function.
- **SMARTS:** Securable/Reliable favor (b) — the guard protects a Bearer token; parse-don't-regex eliminates userinfo/normalization edge cases the reviewer named; reviewer supplied exact code; change is in-scope (same function, workstream B) and small. Maintainable favors (b): URL parsing reads clearer than a hand-anchored regex.
- **Chosen:** (b). Strength: moderate. Re-verify: 62+ vitest green incl. localhost.evil rejection; rebuild farm.js.

## SD-02-note — correction to SD-02 premise
- The hardening agent found the OLD anchored regex already rejected userinfo (`http://localhost@evil`, `http://user:pass@127.0.0.1`) — so there was no userinfo red→green; the regex closed that gap by anchoring.
- Genuine delta of new URL(): HOST NORMALIZATION. `new URL("http://①27.0.0.1")` normalizes to 127.0.0.1 and is now ACCEPTED where the regex REJECTED it. Result is still loopback, so no cleartext-to-remote leak, but it is a behavioral loosening. Author left it unlocked, flagged [NEEDS-TRIAGE].
- Action: re-run security-reviewer on the URL-parse version, focused on the normalization question, before surfacing B at the hard gate. SD-02 still stands (URL parsing is cleaner + explicitly rejects userinfo on the http path), but verification is warranted.

## SD-03 — Decision-log Status field for proposed ADRs · confidence: low
- **Point:** smarts.md decision-log Status enum is {accepted|superseded|deferred}; user chose ADR status `proposed` (declined the "mark accepted" option). No enum value matches.
- **Options:** (a) force Status: accepted (contradicts the user's explicit proposed choice); (b) use Status: proposed per the decision-lifecycle ADR lifecycle, note the reconciliation.
- **SMARTS:** Reliable favors (b) — fidelity to the user's explicit decision over enum-strictness; the conflict is surfaced in the log header (not silently reconciled, per ORCHESTRATOR §0).
- **Chosen:** (b). Strength: moderate. Surfaced to user in the gate message.

## SD-04 — Version bump for the landing commit · confidence: low
- **Point:** CI `version-bump` job fails a payload change (`plugins/ca/**`) on an already-published tagged version. farm.ts/farm.js changed under the published `2.1.0-beta.2`; landing requires a bump.
- **Options:** (a) bump patch-preview `2.1.0-beta.2` → `2.1.0-beta.3`; (b) bump minor `2.1.0` → `2.2.0`.
- **SMARTS:** Maintainable/Reliable favor (a) — the change is a remediation + governance set within the in-flight beta line, not a new feature surface; beta preview increments are the established cadence (beta.1 → beta.2 → beta.3). Bumping the minor would imply a finished feature the sprint did not add.
- **Chosen:** (a). plugin.json + README version badge + CHANGELOG `[2.1.0-beta.3] — 2026-06-13`. Strength: moderate.

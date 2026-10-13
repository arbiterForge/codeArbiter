# Report projection

Regenerate report.md and manifest.yaml from source.json, findings, verification,
leads/dispositions, triage.jsonl and run.jsonl after a successful source check.
These are projections, never authority. Read only necessary records into context;
malformed or incomplete evidence remains an explicit limitation.

Fold triage by finding id while preserving earlier issue_ref values. Group by
proved root_cause_key with all contributing lens/id/dedup identities. Also read
issues-filed.detail.discussion_refs and local bodies/<id>.filing.json receipts;
show their discussion URLs and any unresolved partial filing. This same union
feeds duplicate suppression on resume. Never rewrite the underlying history.

## Structure

- Header: run id, source-binding status, finding/evidence scope, reviewed inputs,
  models/profiles, execution and verification independence, estimate versus
  observable usage, unavailable reasons and extraction limits.
- Launched/skipped lenses: every card, applicability or skip reason, selected
  targets, packet/expansion size, exposures and unresolved boundaries.
- Kept work: calibrated severity then type, only keep/combine with plan_eligible
  true and a passing confidence gate. List id, path:line, surviving claim,
  remediation shape, verification outcome and phase-plan link.
- Verification required: serious factual uncertainty, inconclusive or limited
  verification, failed dispatch and costly inferential recommendations awaiting
  proof. Show the strongest counterargument and next bounded verification.
- Decisions needed: genuine decision-required design forks as questions/options,
  with factual premises distinguished from unverified claims.
- Investigate/refuted/deferred appendix: concise dispositions and rationale;
  refuted serious claims never appear as confirmed defects.
- Lead accounting: promoted/dismissed/deferred, owning finding or next action.
- Follow-ups: filing and telemetry disposition and pending/terminal run state.
  report-written alone is not completion.

Historical finding/v1 and unbound runs remain readable, labelled historical or
legacy-unbound. Do not regenerate them as if their source were current.
Report serious *confirmed* findings as work that should block shipping affected
code, while stating Tribunal itself is an opt-in audit and blocks no workflow.

Apply the anti-slop core and medium-documents guidance. Counts come from records,
not estimates dressed as measurements. Raw findings are not unique defects.
Actual usage includes complete/partial/unavailable status and fixed unavailable
reasons from the usage aggregate; never turn missing usage into zero.

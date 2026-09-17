> Historical design-review rationale. References below to planned or unbuilt components describe the design-review stage, not the current implementation. This edition's fresh reference results are in `validation-report.json`; current engine status is in the parent artifact documentation. Earlier archive bytes are not part of this delivery.

# Final rigor and correctness review

**Disposition:** retain the architecture, replace the preceding reference package with revision 2. The earlier package should not have been treated as final-ready. This is a substantive author review with executable reference tests, not independent security certification.

The design still delivers HTML specifications **and** implementation plans in the first product release, via an internal Go engine and the existing governed execution mechanism. No new slash command, agent, top-level skill or persistent agent-tool registration was added to the proposal. The corrected pair has 26 acceptance contracts, 24 pending tasks and six ordered checkpoint scopes.

## Review scope and evidence

The design-stage review compared the then-current reference archive and HTML. The review examined both embedded models, all criterion/task records, the schemas, reader, renderer and validators; it rechecked targeted repository sources against `main` at `45a17319f9ffda327cbdf3f3d40849bae8e920c0`. This is not a claim that every repository consumer has already been inventoried. T-001 performs that closure inventory before implementation.

A reproduced original defect is recorded in `original-regression-reproduction.json`: after changing visible criterion text without changing the embedded model, the old normal `read` returned a record successfully (exit 0). The revised normal read and outline reject that mismatch before returning content.

## Findings and corrections

### R-01 — High: partial drafts contradicted the schema

The prose allowed incomplete drafts, but an individual criterion/task still required its finished fields. This encouraged fabricated details merely to save progress. The schema now accepts identified partial records and local provenance; readiness checks separately require meaningful typed fields, applicability, guarantees, scenarios, verification definitions and valid relationships. Typed intent, approach and global constraints are now first-class records rather than inferred heading prose. Unborn repository commits and non-public sources are representable.

**Checked here:** partial criterion/task round trips; structural-valid versus not-ready distinction; local request source and nullable baseline/provenance. These checks cannot judge whether plausible prose expresses the correct user intent.

### R-02 — High: dependency selection could deadlock against scope review

The current subagent workflow requires accepted dependencies before selecting a task, while acceptance waits for review of the whole scope after every member has passed task verification. A dependent chain inside one scope can therefore stop before the scope can be reviewed.

The new contract explicitly permits a same-scope predecessor in `REVIEW` to unblock work provisionally after its task-level spec review and fresh verification. Cross-scope dependencies still require accepted predecessor scopes. After all scope members reach `REVIEW`, checks run against one final input snapshot and the combined-diff quality gate runs. `accept-scope` records all members together or none. No provisional state counts as completion or permission to skip final review.

**Changed:** lifecycle section, AC-014, ordered checkpoint model and T-014/T-016/T-023. **Not run here:** the future scheduler/host authority implementation. Its deadlock/interruption/failure scenarios are explicit planned tests, not Python runtime test claims.

Pinned source: [subagent-driven-development](https://github.com/arbiterForge/codeArbiter/blob/45a17319f9ffda327cbdf3f3d40849bae8e920c0/core/surface/skills/subagent-driven-development/SKILL.md).

### R-03 — High: evidence risked invalidating its own acceptance write

A worktree hash that includes the plan's mutable progress, audit receipt or evidence output changes as soon as acceptance is persisted. Broadly excluding `.codearbiter` would hide real policy inputs instead.

The design now requires a versioned verification-input manifest: source, tests, relevant configuration/toolchain, covered-directory membership and normative document projections. Only exact validated control-output/state/evidence fields are excluded. Progress/branding/receipt writes cannot invalidate themselves, while policy/source/test changes still do. Stale verification causes revalidation; it does not automatically demand reimplementation. Final handoff checks remain current against the final snapshot.

**Checked here:** normative/model hash-domain separation. **Planned only:** verification-input collection, dirty-worktree coverage, membership and receipt freshness in Go/host fixtures.

### R-04 — High: exact reads bypassed integrity and model/view validation

The old `read`/`outline` path used a parse-only loader. It could return embedded claims from an artifact whose visible text had changed. Corrected normal reads perform structural and semantic checks, strict decode, marker/DOM/model correspondence, hash checks, stylesheet binding and deterministic re-render comparison first. Errors return no partial record. The local schema dependencies are now mandatory for these reference commands; the README no longer claims they are stdlib-only.

**Checked here:** original defect reproduction, mutated-visible-body rejection, stale digest, duplicate model/attributes/IDs, crossed markers, malformed values and bounded output.

### R-05 — High: contextual cursor identity covered too little

An unchanged plan hash does not prove its referenced spec or approval source is unchanged. The proposed contextual reader now pins a vector of all contributing artifact/model and receipt identities. Global constraints and governing normative sections are included; omissions are explicit. A spec-only change invalidates continuation.

**Changed:** extraction contracts and T-009. **Planned only:** multi-artifact contextual paging. The supplied utility performs verified exact extraction and reports `context_complete: false`.

### R-06 — High: farm projection binding conflicted with dispatch-time enrichment

The actual farm workflow writes `meta.model` and `meta.apiBaseUrl` during model selection and can run a canary before final selection. A hash sealed only at export would reject legitimate enrichment; a receipt never checked at runtime would not enforce anything.

The contract now separates a checked base projection from the final execution seal. Only authorized model/provider enrichment is excluded from the base; base/source binding is checked before canary, and exact full runtime bytes are sealed after enrichment and checked before normal dispatch. The closed farm runtime schema remains unchanged. T-018 must add the actual runtime entry paths discovered by T-001 through reviewed plan refinement; prose-only checking does not satisfy it.

**Planned only:** canary/runtime checks, provider provenance and receipt verification.

Pinned source: [farm-dispatch](https://github.com/arbiterForge/codeArbiter/blob/45a17319f9ffda327cbdf3f3d40849bae8e920c0/core/surface/skills/subagent-driven-development/references/farm-dispatch.md).

### R-07 — Medium: the specimen renderer did not represent legal variants faithfully

The former renderer assumed the supplied golden drafts: mandatory labels, pending state, no open decisions, and no visible retirement records. The corrected renderer presents actual obligation/state values, typed core records, blockers and tombstones. Recorded approval/state remains explicitly unverified by the reference tools. Mobile browsing is available through native disclosure. A new 200% text-scaling run found title overflow at 390 px; heading wrapping was corrected and retested.

**Checked here:** SHOULD labeling, open blocker, retired ID, REVIEW/ACCEPTED labels with evidence references, no evidence/authority escalation, all four browser cells.

### R-08 — Medium: single-file replacement did not define ambiguous completion

A failure after replacement but before acknowledgment is different from rejection before writing. The spec now requires operation identity and reconciliation for ambiguous committed outcomes, without claiming unchanged bytes or blindly applying the mutation twice. Pair cutover/approval still require recovery-aware multi-file handling; ordinary reads do not recover or write.

**Planned only:** actual lock, replacement, interruption, power-loss and multi-file recovery behavior on each supported native host. The Go binary does not exist in this package.

### R-09 — Medium: paths, identity and optional requirements needed stronger boundaries

A companion filename is now a presentation locator, not normative identity. The spec binding is artifact ID plus normative digest. Ambiguous live identities must be rejected. Optional criteria require an explicit disposition rather than disappearing or becoming mandatory accidentally; mandatory criteria cannot be dispositioned away. Sources no longer require a public URL or Git blob for repo-owned assets.

**Checked here:** unsafe paths, wrong spec hash, unresolved refs, cycles, checkpoint ordering/partition, invalid dispositions and schema closure. **Planned only:** repository-wide identity resolution and branch-merge handling.

### R-10 — Medium: the plan needed an executable bootstrap and verification guard

The engine cannot be required to govern its own initial implementation. The plan explicitly uses existing governance for bootstrap and isolated fixtures for the new path before cutover. Task dependencies now include the validators the renderer consumes; storage starts with an injected byte-buffer seam. T-002 freezes the closed per-operation protocol before dispatch code. Named Go verification commands carry required test names so a zero-match or skipped test is not silently credited. Shell text is not synthesized by joining argv for display.

**Checked here:** reference DAG/coverage and presence of required named-test guards. **Planned only:** actual Go test event checking and production protocol implementation.

## Actual results

The final machine reports contain the precise values and test names. In this review, the reference suite has **41 tests, zero failures, zero errors and zero skips**. Both artifacts pass schema/relationship/integrity/render checks; all 26 criteria have targeted task coverage; the graph is acyclic with an ordered checkpoint partition; **880** internal/companion links resolve.

Chromium 144.0.7559.96 passed four cells: spec/plan at 1440 px and 390 px, page JavaScript disabled, embedded logos loaded, no automatic external requests, no page-level horizontal overflow, selected text scaled to 200%, and collapsed native disclosures exposed under print media. Desktop/mobile screenshots of headers and representative records were visually inspected. Local-file browsing was unavailable, so these are in-memory rendering results, not native file-opening certification. This is not a full accessibility or cross-browser audit.

## Remaining implementation gates

The review closes the identified design/reference defects; it does not prove runtime behavior that has not been built. Remaining planned work includes the complete consumer/path inventory, concrete authority receipt mapping, closed production operation schema, Go writer/locking/recovery, full contextual cursor implementation, verification-input capture, farm runtime seals, installers and native Windows/macOS/Linux evidence. Independent assessment of user-intent fidelity and agent coding outcomes is also not replaced by schema checks.

The reference tools never resolve external authority. Both delivered documents remain drafts; all tasks are pending, with no approval or completion evidence. Product target stays **v0.1.0**, document revision is **2**, and the incompatible draft schema refinement is **0.2.0**. No product release or repository mutation occurred.

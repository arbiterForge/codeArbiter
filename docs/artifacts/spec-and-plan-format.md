# Typed HTML specifications and plans

This is guidance for codeArbiter's existing feature and sprint workflows. It
does not introduce a public command, agent, top-level skill, persistent tool or
startup-loaded schema. The capability is an internal, on-demand leaf of the
current brainstorming, planning, TDD, execution and resume paths.

## Rollout status

Typed HTML is the default format for new full-lane feature and sprint work when
the installed host package contains its qualified native payload. Existing
Markdown pairs remain on their exact legacy path and small-lane work remains
inline; there is no implicit migration. A missing, untrusted or unsupported
payload is a capability error, never permission to edit embedded JSON or fall
back from an HTML artifact to an ungoverned write.

HTML farm use is also disabled. Its separate promotion bar requires real
authority adapters, packaged native payloads and a fresh frontier/low-tier model
matrix. The June 2026 farm run is historical only and counts as zero current
qualification evidence.

## What is authoritative

Each `.codearbiter/specs/<slug>.html` or `.codearbiter/plans/<slug>.html` file is
a self-contained, deterministic, offline-reviewable document. The typed JSON
model embedded in the HTML is authoritative; the visible HTML is a generated
view that must match it. The parser rejects duplicate or executable script
content, model/view drift, unsupported renderers and remote branding resources.
Opening the file in a browser performs no mutation and needs no JavaScript or
network access.

The current write schema is `0.3.2`; `0.3.0` and `0.3.1` remain readable without
relabeling or rewriting their historical bytes. Older clients must refuse newer
state they cannot interpret. The document
format is `0.1.0`, the subprocess API is
`codearbiter.artifact-api/0.1.0`, and workflow receipts use their own versioned
formats. Schema, document format, renderer, protocol, artifact revision and
product release are separate identities and must not be conflated.

Specifications own acceptance criteria. Plans reference those stable criterion
IDs and own tasks, dependencies, checkpoints, paths and verification
definitions. Retired records retain their IDs and reasons; IDs are not recycled.
There is no second criterion ledger in the plan.

Three hashes serve different purposes:

- `normative_sha256` covers the normative definition. If that exact definition
  has historical attestation, changing it stales that binding. Current spec
  definitions also bind the plan's criteria and relevant task context.
- `model_sha256` covers the complete model except its integrity fields. Status or
  presentation changes therefore remain guarded without pretending to change
  requirements.
- the render identity covers the exact deterministic HTML bytes.

CAS updates to an existing artifact compare both the last-read revision and
model hash while holding the artifact lock. Create, receipt capture, recovery
and pair migration use their own typed identities; migration binds its preview,
journal and exact endpoint bytes as described in the recovery guide. Hash
consistency is integrity, not authentication or semantic verification. Existing
attestation records retain their historical meaning; ordinary authorized work
does not need to create them.

## Existing workflow

The user still enters through the existing feature or sprint flow:

1. Brainstorming creates a typed draft and preserves genuinely missing content
   as an explicit gap. It never invents a condition, oracle, source, command,
   result or reviewer.
2. `validate` with the ready gate checks structure, references, coverage and
   contracts. It cannot determine whether prose is true or whether a human
   approved it.
3. Respect actual user decisions, unresolved material scope choices and real
   host permissions. An agreed draft does not need a separate artifact approval
   event to permit already-authorized work.
4. Planning reuses stable criterion IDs and binds the current spec with
   `plan-bind`. Draft bindings are valid working state; a changed outcome goes
   to its real owner, while authorized implementation details can be refined.
5. Use `identity`, advisory `eligible` and bounded `task-context` with the
   current model hash. Record ordinary `task-start`, actual `task-check` results
   and `task-review`. `accept-scope` records implementation `DONE`; it does not
   assert independent acceptance or that tests passed.
6. Resume by checking the worktree, workers, recorded user stops and relevant
   source changes. Reconcile actual task state with a reason. Do not rerun a
   reviewer merely because a receipt identity or presentation changed, and
   never clear an unresolved user stop or hide a newer failing check.

All mutations are typed operations. Callers do not write, template or
regular-expression-edit the HTML. `task-context` supplies the task, referenced
criteria and constraints, dependencies, scoped prerequisite observations and
reported checks. It remains `context_complete: false`; expand only necessary
exact symbols. It creates no approval or delivery ticket. Stale hashes and
oversized packets refuse rather than truncate evidence.

Internal readers may use `read-batch` for 1–128 unique symbol IDs under one
required `model_sha256`. Pages return whole exact records with explicit
continuation offsets; repeat the selection, identity and budget to continue.
These reads are context-incomplete and do not certify execution permission.

Reported command results preserve their actual argv, cwd, exit status and
pass/fail/skip/unknown outcome. Command success is not fabricated named-test
proof. Declared-path freshness is partial source applicability, not a full
dependency graph or verified test. A change to unrelated context alone does not
invalidate a task's scoped evidence; an affected contract or source does need
reinspection. Real tests, reviews and user checkpoints retain their own purpose.

## Capability and diagnostics

Each qualified host package carries an installation-owned `release.json` that
pins the correct native executable. The bridge selects that payload only: not
`PATH`, a project-supplied binary or an environment override. The host's
existing governed-execution rules and permissions still apply.

Check the installed capability before authoring; reuse its known operation
shapes during ordinary bounded reads. The response reports the
binary, protocol, schema and renderer versions; selected native platform and
storage backend; available operations; whether repository operations are
available; and the rollout values `public_registrations_added: 0`,
`host_default_enabled: true` and `runtime_downloads: false`. A false write
capability or any bridge failure stops new full-lane HTML authoring while
leaving an existing authoritative legacy workflow unchanged.

The internal protocol shape is:

```text
ca-artifact <operation> --root <repository-root> --request -
```

JSON arrives on standard input and carries
`"protocol": "codearbiter.artifact-api/0.1.0"`. Output is one bounded JSON
envelope. Operation-specific schemas are queried on demand; complete schemas and
artifact bodies are not injected at startup. Nonzero exit is failure. A
structured validation result with `valid: false` reports a failed structural or
coverage check. It must not be called success, but does not invent another
permission requirement for correcting the draft.

Important diagnostics fail closed:

- `CAPABILITY_MISSING`: no matching manifest-pinned native payload is installed;
- `INVALID_INSTALLATION`: the manifest, selected filename or executable shape is
  invalid;
- `PACKAGE_INTEGRITY`: installed executable bytes do not match the manifest;
- `UNVERIFIED_PLATFORM`: a matching binary exists but lacks native-test
  qualification;
- `UNSUPPORTED_PLATFORM`: the host architecture or repository storage backend is
  not supported;
- `AUTHORITY_UNVERIFIED` or `DRAFT_BINDING`: a separately selected historical
  attestation operation lacks its required receipt or binding. These are not
  ordinary draft task-start or context-read prerequisites;
- `REVISION_CONFLICT` or `STALE_CURSOR`: reread and reconsider, never force;
- `LOCK_BUSY`: another bounded writer owns the artifact lock;
- `RECOVERY_REQUIRED` or `COMMIT_OUTCOME_UNKNOWN`: inspect the transaction with
  its operation ID instead of replaying a new write;
- `UNSUPPORTED_VERSION` or `UNSUPPORTED_RENDERER`: upgrade through a reviewed
  compatibility path, never silently reinterpret the file.

## Offline review

Reviewers can open either HTML file directly and inspect its visible criteria,
tasks, blockers, sources, bindings and governance labels. `DONE` describes
implementation progress; verification is displayed separately. A historical
approval is only a recorded claim until its captured workflow event/receipt
and current binding are actually validated. That remains cooperative
attestation, not actor identity authentication.
For machine review, use the engine's validation and scoped-read operations so
the embedded model, visible view, resource closure and hashes are checked
together. Do not use browser rendering, a file digest or a green schema check as
proof of approval or semantic correctness.

Offline presentation review includes keyboard access to native disclosure,
visible anchors, print output, long identifiers and code blocks, doubled text,
and 390 px and 1440 px layouts without container escape. Custom branding must
change the visible name/title and use only a validated embedded local PNG, JPEG
or inert SVG; it must not introduce a remote request, script, template or font.
Current Chromium checks cover those cases. Native multi-browser and full
accessibility certification remain unqualified.

## Evidence boundary

The original local conformance record covered 41 reference regressions,
cross-kind identity vectors, hostile HTML/JSON inputs and the named workflow,
migration, farm and package fixtures. Windows and native WSL Linux test, vet and
Linux race runs passed for that recorded revision. Those historical results
do not substitute for current exact-head Linux/macOS results, a real
production host trace, release-channel provenance, physical power-loss or
network-filesystem qualification.

A historical native-Windows pilot built from clean commit
`12ab0ef2d720420b90265f35675fb961375a439b` additionally observed draft dispatch
rejected with `DRAFT_BINDING`, exact synthetic spec/plan approval and binding
receipts, task transition to `IN_PROGRESS`, process recreation with the same
state, an explicit reconciliation receipt returning the task to `PENDING`, a new
context-bound dispatch, verification/spec-review receipts, `REVIEW`, and one
quality-review-bound atomic scope acceptance ending in `ACCEPTED` with
`all_accepted_and_current: true`. Its release-manifest and executable digests and
the canonical receipt/event bytes plus returned transaction identities are retained in
`docs/artifacts/T024-PILOT-EVIDENCE.json`. The receipts were synthetic fixture
authority, not a claim that a production host or human identity was
authenticated. That pilot predates the assistive schema and is not the default execution
procedure or current installed-host proof. Comparative performance and live
host claims require their own current observations; no such claim follows from
these historical synthetic receipts.

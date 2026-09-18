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

The current write schema is `0.3.1`; `0.3.0` remains readable. The document
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
  has a current approval, changing it stales that approval and downstream
  bindings.
- `model_sha256` covers the complete model except its integrity fields. Status or
  presentation changes therefore remain guarded without pretending to change
  requirements.
- the render identity covers the exact deterministic HTML bytes.

CAS updates to an existing artifact compare both the last-read revision and
model hash while holding the artifact lock. Create, receipt capture, recovery
and pair migration use their own typed identities; migration binds its preview,
journal and exact endpoint bytes as described in the recovery guide. Hash
consistency is integrity, not authentication. Approval is a cooperative workflow
attestation sourced from codeArbiter's existing user, SMARTS or review authority
and bound to exact content.

## Existing workflow

The user still enters through the existing feature or sprint flow:

1. Brainstorming creates a typed draft and preserves genuinely missing content
   as an explicit gap. It never invents a condition, oracle, source, command,
   result or reviewer.
2. `validate` with the ready gate checks structure, references, coverage and
   contracts. It cannot determine whether prose is true or whether a human
   approved it.
3. The existing approval gate is captured as a workflow event and then bound to
   the exact normative identity. Generic editing cannot set an approved state.
4. Planning creates a `draft_preview`, reuses the spec's criterion IDs, binds to
   the approved spec and passes the existing plan approval gate.
5. Execution obtains contextual reads and a final delivery ticket, asks the
   engine for the eligible task, then records start, actual named-test evidence,
   review and one atomic scope acceptance. It does not accept tasks one by one.
6. Resume re-enters the existing feature/sprint ladder. `IN_PROGRESS` requires
   reconciliation and `REVIEW` requires fresh evidence; neither is silently
   promoted after interruption.

All mutations are typed operations. Callers do not write, template or
regular-expression-edit the HTML. Reads proceed from `index` to `outline` to
symbol-scoped/contextual `read`; exact reads are intentionally
context-incomplete. Every cursor and delivery ticket binds the plan, its spec
and contributing authority records. A changed dependency yields a stale cursor,
not partial context.

## Capability and diagnostics

Each qualified host package carries an installation-owned `release.json` that
pins the correct native executable. The bridge selects that payload only: not
`PATH`, a project-supplied binary or an environment override. The host's
existing governed-execution rules and permissions still apply.

Call `capabilities` before repository operations. The response reports the
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
structured validation result with `valid: false` is also a failed gate.

Important diagnostics fail closed:

- `CAPABILITY_MISSING`: no matching manifest-pinned native payload is installed;
- `INVALID_INSTALLATION`: the manifest, selected filename or executable shape is
  invalid;
- `PACKAGE_INTEGRITY`: installed executable bytes do not match the manifest;
- `UNVERIFIED_PLATFORM`: a matching binary exists but lacks native-test
  qualification;
- `UNSUPPORTED_PLATFORM`: the host architecture or repository storage backend is
  not supported;
- `AUTHORITY_UNVERIFIED`: no current receipt from an existing authority source;
- `DRAFT_BINDING`: execution was requested from draft/unapproved content;
- `REVISION_CONFLICT` or `STALE_CURSOR`: reread and reconsider, never force;
- `LOCK_BUSY`: another bounded writer owns the artifact lock;
- `RECOVERY_REQUIRED` or `COMMIT_OUTCOME_UNKNOWN`: inspect the transaction with
  its operation ID instead of replaying a new write;
- `UNSUPPORTED_VERSION` or `UNSUPPORTED_RENDERER`: upgrade through a reviewed
  compatibility path, never silently reinterpret the file.

## Offline review

Reviewers can open either HTML file directly and inspect its visible criteria,
tasks, blockers, sources, bindings and governance labels. A displayed approval
is only a recorded claim until the coordinator validates the corresponding
captured workflow event/receipt and its current binding. That remains cooperative
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

Fresh local conformance covers the original 41 reference regressions, current
cross-kind identity vectors, hostile HTML/JSON inputs and the named workflow,
migration, farm and package fixtures. Windows and native WSL Linux test, vet and
Linux race runs are green. This supports the format behavior described above;
it does not substitute for hosted exact-head Linux/macOS results, a real
production host trace, release-channel provenance, physical power-loss or
network-filesystem qualification.

A native-Windows pilot built from clean commit
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
authenticated. No comparative agent-performance result was run. Any paid
frontier/low-tier pilot requires separate budget approval.

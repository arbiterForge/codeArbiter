package operations

// OperationDescriptor is the compile-time, repository-owned description of
// one implemented protocol operation (N-F02). It is data, not a rule engine:
// domain guards and transitions stay explicit in their owning handlers. Names,
// journaled-replay admission and the advertised capability contract all derive
// from this one table, and tests check it against the request-schema switch and
// the Run dispatcher in both directions.
//
// Traits describe what an operation can actually do, not what it is allowed to
// do: no trait is a permission. In particular Journaled=false does not mean
// "writes nothing" (capture writes immutable events and receipts; a contextual
// read writes delivery tokens).
type OperationDescriptor struct {
	Name string
	// Effect is the operation's broadest effect class:
	//   metadata                 no repository store is opened
	//   store-initialization     creates lock metadata only
	//   observation              reads only
	//   contextual-read          exact mode reads only; contextual mode writes delivery tokens
	//   derived-write            writes immutable content-addressed derived records only
	//   immutable-capture        writes immutable events/receipts (and may consume a source)
	//   journaled-mutation       CAS/journaled canonical or local-state write
	//   owner-journaled-mutation journaled by its owning package, keyed by a recorded preview
	//   recovery                 completes or rolls back a prepared journal
	Effect string
	// Journaled operations get operation-ID replay from Run before dispatch.
	Journaled bool
	// Lock is the repository lock Run takes: none, shared, exclusive, or
	// by-mode (shared only for read mode=exact).
	Lock string
	// Writes names the reserved directories or file classes the operation may
	// create or replace when it succeeds.
	Writes []string
	// Evidence is ordinary (records progress or reports; mints no claim),
	// explicit (consumes or produces an evidence/authority claim), by-request
	// (ordinary unless the request carries a receipt or evidence field), or none.
	Evidence string
}

// OperationContractFormat versions the descriptor projection returned by
// capabilities. Change it whenever a trait vocabulary changes meaning.
const OperationContractFormat = "codearbiter.operation-descriptors/0.1.0"

var (
	canonicalWrite  = []string{"canonical-artifact", "transactions", "history"}
	localStateWrite = []string{"local-work-state", "transactions", "history"}
)

func observe(name string) OperationDescriptor {
	return OperationDescriptor{Name: name, Effect: "observation", Lock: "shared", Evidence: "none"}
}
func exclusiveRead(name, evidence string) OperationDescriptor {
	return OperationDescriptor{Name: name, Effect: "observation", Lock: "exclusive", Evidence: evidence}
}
func journaled(name string, writes []string, evidence string) OperationDescriptor {
	return OperationDescriptor{Name: name, Effect: "journaled-mutation", Journaled: true, Lock: "exclusive", Writes: writes, Evidence: evidence}
}
func derived(name, directory, evidence string) OperationDescriptor {
	return OperationDescriptor{Name: name, Effect: "derived-write", Lock: "exclusive", Writes: []string{directory}, Evidence: evidence}
}

var descriptors = []OperationDescriptor{
	{Name: "capabilities", Effect: "metadata", Lock: "none", Evidence: "none"},
	{Name: "schema", Effect: "metadata", Lock: "none", Evidence: "none"},
	{Name: "init-store", Effect: "store-initialization", Lock: "exclusive", Writes: []string{"lock-metadata"}, Evidence: "none"},

	journaled("create", canonicalWrite, "ordinary"),
	journaled("apply", canonicalWrite, "ordinary"),
	{Name: "read", Effect: "contextual-read", Lock: "by-mode", Writes: []string{"context-tokens"}, Evidence: "none"},
	observe("read-batch"),
	observe("plan-verification"),
	observe("outline"),
	exclusiveRead("validate", "none"),
	exclusiveRead("index", "none"),
	observe("identity"),
	observe("snapshot"),
	derived("evidence-context", "evidence-contexts", "explicit"),
	derived("context-evidence-context", "evidence-contexts", "explicit"),
	derived("context-finalize-evidence-context", "evidence-contexts", "explicit"),
	derived("context-preview", "context-previews", "ordinary"),
	derived("context-finalize-preview", "context-previews", "ordinary"),
	{Name: "context-apply", Effect: "owner-journaled-mutation", Lock: "exclusive", Writes: []string{"canonical-context", "transactions", "history"}, Evidence: "by-request"},
	journaled("rebrand", canonicalWrite, "ordinary"),
	exclusiveRead("repair-preview", "none"),
	journaled("repair-apply", canonicalWrite, "ordinary"),
	journaled("approve", canonicalWrite, "explicit"),
	journaled("plan-bind", canonicalWrite, "by-request"),
	derived("sprint-approval-context", "evidence-contexts", "explicit"),
	{Name: "sprint-approve", Effect: "journaled-mutation", Journaled: true, Lock: "exclusive", Writes: []string{"canonical-artifact", "observations", "authority-sources", "transactions", "history"}, Evidence: "explicit"},
	journaled("smarts-apply", canonicalWrite, "explicit"),
	observe("eligible"),
	observe("task-context"),
	{Name: "verification-status", Effect: "observation", Lock: "shared", Evidence: "explicit"},
	journaled("task-start", canonicalWrite, "ordinary"),
	journaled("task-check", canonicalWrite, "ordinary"),
	journaled("task-review", canonicalWrite, "by-request"),
	journaled("task-block", canonicalWrite, "ordinary"),
	journaled("task-reconcile", canonicalWrite, "by-request"),
	journaled("scope-reconcile", canonicalWrite, "explicit"),
	journaled("accept-scope", canonicalWrite, "by-request"),
	journaled("prerequisite", canonicalWrite, "by-request"),
	{Name: "farm-project", Effect: "journaled-mutation", Journaled: true, Lock: "exclusive", Writes: []string{"canonical-artifact", "farm-projection", "farm-bindings", "farm-markers", "transactions", "history"}, Evidence: "explicit"},
	derived("farm-seal", "farm-seals", "explicit"),
	exclusiveRead("farm-verify", "explicit"),
	{Name: "recover", Effect: "recovery", Journaled: true, Lock: "exclusive", Writes: []string{"canonical-artifact", "local-work-state", "transactions", "history"}, Evidence: "none"},
	exclusiveRead("diff", "none"),
	{Name: "capture", Effect: "immutable-capture", Lock: "exclusive", Writes: []string{"events", "receipts"}, Evidence: "explicit"},
	{Name: "capture-observation", Effect: "immutable-capture", Lock: "exclusive", Writes: []string{"events", "receipts"}, Evidence: "explicit"},
	{Name: "export", Effect: "journaled-mutation", Journaled: true, Lock: "exclusive", Writes: []string{"standalone-export", "transactions", "history"}, Evidence: "none"},
	exclusiveRead("migration-preview", "none"),
	journaled("migration-apply", canonicalWrite, "ordinary"),
	journaled("migration-rollback", canonicalWrite, "ordinary"),
	observe("knowledge-context"),
	journaled("knowledge-initialize", canonicalWrite, "ordinary"),
	journaled("knowledge-cutover", canonicalWrite, "ordinary"),
	journaled("knowledge-merge", canonicalWrite, "ordinary"),
	journaled("work-create", localStateWrite, "ordinary"),
	journaled("work-adopt", localStateWrite, "ordinary"),
	observe("work-get"),
	journaled("work-update", localStateWrite, "ordinary"),
	observe("work-context"),
	observe("work-view"),
	observe("work-list"),
	observe("work-origins"),
	observe("project-view"),
	observe("cycle-view"),
	observe("work-provider-get"),
	journaled("work-provider-configure", localStateWrite, "ordinary"),
	observe("work-transition-map-get"),
	journaled("work-transition-map-configure", localStateWrite, "ordinary"),
	journaled("work-coordinate-resume", localStateWrite, "ordinary"),
	journaled("work-effect-stage", localStateWrite, "ordinary"),
	journaled("work-effect-claim", localStateWrite, "ordinary"),
	journaled("work-effect-record", localStateWrite, "ordinary"),
	journaled("work-effect-conflict", localStateWrite, "ordinary"),
	journaled("work-effect-adopt", localStateWrite, "ordinary"),
	observe("work-project-get"),
	journaled("work-project-configure", localStateWrite, "ordinary"),
	journaled("work-project-stage", localStateWrite, "ordinary"),
	journaled("work-project-stage-field", localStateWrite, "ordinary"),
	journaled("work-project-claim", localStateWrite, "ordinary"),
	journaled("work-project-record", localStateWrite, "ordinary"),
	journaled("work-project-conflict", localStateWrite, "ordinary"),
}

var descriptorIndex = func() map[string]OperationDescriptor {
	index := make(map[string]OperationDescriptor, len(descriptors))
	for _, d := range descriptors {
		if _, duplicate := index[d.Name]; duplicate {
			panic("duplicate operation descriptor: " + d.Name)
		}
		index[d.Name] = d
	}
	return index
}()

// Descriptor returns the declared traits of an implemented operation.
func Descriptor(op string) (OperationDescriptor, bool) {
	d, ok := descriptorIndex[op]
	return d, ok
}

// operationContract is the versioned descriptor projection in capabilities.
func operationContract() object {
	rows := make([]any, 0, len(descriptors))
	for _, name := range Names() {
		d := descriptorIndex[name]
		writes := make([]any, 0, len(d.Writes))
		for _, w := range d.Writes {
			writes = append(writes, w)
		}
		rows = append(rows, object{"name": d.Name, "effect": d.Effect, "journaled": d.Journaled,
			"lock": d.Lock, "writes": writes, "evidence": d.Evidence})
	}
	// Accepted stored vocabulary that no implemented operation produces is
	// labeled, so a reader never infers a transition from a schema enum (N-F06).
	schemaOnly := []any{object{"field": "work.execution.check_status",
		"produced_values": []any{"unknown"}, "produced_by": []any{"work-create", "work-adopt"},
		"values":  []any{"passed", "failed"},
		"meaning": "accepted and preserved when stored by another writer; no native operation sets it and it is not a verification event"}}
	return object{"format": OperationContractFormat, "operations": rows, "schema_only_values": schemaOnly,
		"note": "Traits describe actual effects; none is a permission or a verification claim."}
}

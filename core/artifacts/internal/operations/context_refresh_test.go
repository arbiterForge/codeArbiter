package operations

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/contextdocument"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

// Fixture observation records below exercise the production preview, capture,
// receipt and apply path. They do not assert a live host or provider approval.
func TestContextSelectedProvenanceRefreshReceipt(t *testing.T) {
	root, request := contextFixture(t)
	docPath := filepath.Join(root, ".codearbiter", "CONTEXT.md")
	provenancePath := filepath.Join(root, ".codearbiter", ".provenance", "CONTEXT.json")
	oldDocument := []byte("---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n# Project: Fixture Project\n\n## Human\nKeep these bytes.\n")
	oldProvenance := model.M(request["proposed_provenance"])
	model.M(oldProvenance["document"])["digest"] = canonical.BytesHash(oldDocument)
	oldProvenanceBytes, err := canonical.Marshal(oldProvenance)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Dir(provenancePath), 0755); err != nil {
		t.Fatal(err)
	}
	for path, content := range map[string][]byte{
		docPath: oldDocument, provenancePath: oldProvenanceBytes,
		filepath.Join(root, ".codearbiter", "open-tasks.md"): []byte("# Human tasks\n"),
		filepath.Join(root, ".codearbiter", "overrides.log"): []byte("# Human audit\n"),
	} {
		if err := os.WriteFile(path, content, 0644); err != nil {
			t.Fatal(err)
		}
	}
	newSource := []byte("reinspected source\n")
	if err := os.WriteFile(filepath.Join(root, "source.txt"), newSource, 0644); err != nil {
		t.Fatal(err)
	}
	proposedBytes, err := canonical.Marshal(oldProvenance)
	if err != nil {
		t.Fatal(err)
	}
	proposed, err := canonical.Object(proposedBytes)
	if err != nil {
		t.Fatal(err)
	}
	claim := model.M(model.A(model.M(model.A(proposed["fields"])[0])["claims"])[0])
	model.M(model.A(claim["evidence"])[0])["digest"] = canonical.BytesHash(newSource)
	model.M(claim["semantic_review"])["reference"] = "review:fixture-reinspection"
	request["mode"] = "update"
	request["operation_id"] = "context-refresh-0001"
	request["selections"] = []any{object{"entry_id": "FIELD-NAME", "anchor": "project_name"}}
	request["expected_document_sha256"] = canonical.BytesHash(oldDocument)
	request["expected_provenance_sha256"] = canonical.BytesHash(oldProvenanceBytes)
	request["proposed_provenance"] = proposed
	typed, err := canonical.Marshal(request["typed"])
	if err != nil {
		t.Fatal(err)
	}
	rendered, err := contextdocument.RenderPreview(typed, oldDocument, true,
		[]contextdocument.PreviewSelection{{EntryID: "FIELD-NAME", Anchor: "project_name"}})
	if err != nil || !bytes.Equal(rendered.Bytes, oldDocument) {
		t.Fatalf("fixture must select an owned field without changing its text: %v", err)
	}
	prompt := "approve-context CONTEXT-CONTEXT fixture-refresh-token"
	request["prompt_sha256"] = canonical.BytesHash([]byte(prompt))
	issuedValue, err := Run(root, "context-evidence-context", request)
	if err != nil {
		t.Fatalf("selected provenance refresh preview rejected: %v", err)
	}
	issued := model.M(issuedValue)
	binding := model.S(issued["preview_binding_sha256"])
	subject := model.M(issued["subject"])
	payload := object{"preview_binding_sha256": binding}
	producer := object{"host": "fixture", "session_id": "refresh", "prompt_sha256": request["prompt_sha256"]}
	observed := object{"format": "codearbiter.observation/0.2.0", "kind": "context_approval",
		"subject": subject, "context_ref": issued["context_ref"], "context_sha256": issued["context_sha256"],
		"payload_sha256": mustHashFixture(t, payload), "producer_profile": "host-user-context-preview/0.1.0",
		"producer_run_id": "fixture:refresh", "producer_result": producer,
		"producer_result_sha256": mustHashFixture(t, producer)}
	observationRef, observationHash := contextSourceFixture(t, root, "observations", observed)
	event := object{"format": "codearbiter.workflow-event/0.2.0", "kind": "context_approval",
		"authority_kind": "user_workflow", "subject": subject, "actor": "fixture user",
		"origin": "fixture:UserPromptSubmit:refresh", "verdict": "approved", "payload": payload,
		"source_text": prompt, "observation_ref": observationRef, "observation_sha256": observationHash}
	sourceRef, sourceHash := contextSourceFixture(t, root, "authority-sources", event)
	capturedValue, err := Run(root, "capture-observation", object{"protocol": Protocol, "source_ref": sourceRef, "source_sha256": sourceHash})
	if err != nil {
		t.Fatalf("fixture refresh observation refused: %v", err)
	}
	receipt := model.S(model.M(capturedValue)["receipt"])
	if !bytes.Equal(mustReadRefresh(t, docPath), oldDocument) || !bytes.Equal(mustReadRefresh(t, provenancePath), oldProvenanceBytes) {
		t.Fatal("preview or capture changed initialized state")
	}
	if err := os.WriteFile(docPath, append(bytes.Clone(oldDocument), '\n'), 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := Run(root, "context-apply", object{"protocol": Protocol, "receipt": receipt}); err == nil {
		t.Fatal("changed document preimage was accepted")
	}
	if !bytes.Equal(mustReadRefresh(t, provenancePath), oldProvenanceBytes) {
		t.Fatal("failed preimage apply changed provenance")
	}
	if err := os.WriteFile(docPath, oldDocument, 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "source.txt"), []byte("later source edit\n"), 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := Run(root, "context-apply", object{"protocol": Protocol, "receipt": receipt}); fault.Code(err) != "SOURCE_EVIDENCE_CONFLICT" {
		t.Fatalf("stale source accepted during refresh: %v", err)
	}
	if !bytes.Equal(mustReadRefresh(t, provenancePath), oldProvenanceBytes) {
		t.Fatal("failed stale apply changed provenance")
	}
	if err := os.WriteFile(filepath.Join(root, "source.txt"), newSource, 0644); err != nil {
		t.Fatal(err)
	}
	appliedValue, err := Run(root, "context-apply", object{"protocol": Protocol, "receipt": receipt})
	if err != nil {
		t.Fatalf("receipt-only refresh refused: %v", err)
	}
	transaction := appliedValue.(map[string]any)["transaction"].(store.Outcome)
	if transaction.State != "committed" || transaction.Replay {
		t.Fatalf("expected fresh committed receipt-only update: %+v", transaction)
	}
	if !bytes.Equal(mustReadRefresh(t, docPath), oldDocument) {
		t.Fatal("refresh changed marker or human document bytes")
	}
	newProvenance, err := canonical.Marshal(proposed)
	if err != nil || !bytes.Equal(mustReadRefresh(t, provenancePath), newProvenance) {
		t.Fatalf("selected provenance was not committed exactly: %v", err)
	}
	if got := string(mustReadRefresh(t, filepath.Join(root, ".codearbiter", "open-tasks.md"))); got != "# Human tasks\n" {
		t.Fatal("refresh changed task history")
	}
	if got := string(mustReadRefresh(t, filepath.Join(root, ".codearbiter", "overrides.log"))); got != "# Human audit\n" {
		t.Fatal("refresh changed audit history")
	}
	secondProposed, err := canonical.Object(newProvenance)
	if err != nil {
		t.Fatal(err)
	}
	secondClaim := model.M(model.A(model.M(model.A(secondProposed["fields"])[0])["claims"])[0])
	model.M(secondClaim["semantic_review"])["reference"] = "review:fixture-second-approval-needed"
	secondBytes, err := canonical.Marshal(secondProposed)
	if err != nil {
		t.Fatal(err)
	}
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	unlock, err := f.Lock(true, 2*time.Second)
	if err != nil {
		f.Close()
		t.Fatal(err)
	}
	second := contextdocument.Mutation{OperationID: "context-refresh-0002", Mode: "update", Typed: typed,
		Selections:       []contextdocument.PreviewSelection{{EntryID: "FIELD-NAME", Anchor: "project_name"}},
		ExpectedDocument: oldDocument, ExpectedProvenance: newProvenance, ProposedProvenance: secondBytes}
	if _, err := contextdocument.ApplyWithReceipt(f, second, "unobserved-context-receipt"); err == nil {
		t.Fatal("unobserved authority authorized metadata refresh")
	}
	if _, err := contextdocument.ApplyWithReceipt(f, second, receipt); err == nil {
		t.Fatal("old approval receipt authorized a different metadata refresh")
	}
	unlock()
	f.Close()
	if !bytes.Equal(mustReadRefresh(t, provenancePath), newProvenance) {
		t.Fatal("old receipt attempt changed provenance")
	}
	replayedValue, err := Run(root, "context-apply", object{"protocol": Protocol, "receipt": receipt})
	if err != nil || !replayedValue.(map[string]any)["transaction"].(store.Outcome).Replay {
		t.Fatalf("durable receipt replay failed: %v", err)
	}
}

func mustReadRefresh(t *testing.T, path string) []byte {
	t.Helper()
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return content
}

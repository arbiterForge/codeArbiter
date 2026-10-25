package operations

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
)

func knowledgeRecord(typ, title, statement, basis string, paths []string, related ...string) object {
	r := object{"type": typ, "title": title, "statement": statement, "basis": basis,
		"scope": object{"paths": model.List(paths...)}, "related_refs": model.List(related...), "source_refs": empty()}
	if typ == "command" {
		r["command"] = object{"argv": model.List("go", "test", "./..."), "cwd": ".", "purpose": "test", "run_state": "unrun"}
	}
	if typ == "question" {
		r["status"] = "open"
		r["answer"] = nil
	}
	return r
}

func (f *assistiveFixture) createKnowledge(kind, id, slug string) {
	f.t.Helper()
	f.call("create", object{"operation_id": f.next(), "kind": kind, "artifact_id": id, "slug": slug, "title": slug, "summary": "Repository " + slug + " knowledge."})
}

func (f *assistiveFixture) knowledgeDoc(id string) *model.Document {
	f.t.Helper()
	p := filepath.Join(f.root, filepath.FromSlash(".codearbiter/"+map[bool]string{true: "context", false: "decomposition"}[strings.HasPrefix(id, "CTX-")]+"/"+strings.ToLower(id[strings.Index(id, "-")+1:])+".html"))
	b, err := os.ReadFile(p)
	if err != nil {
		f.t.Fatal(err)
	}
	d, err := render.Parse(b)
	if err != nil {
		f.t.Fatal(err)
	}
	return d
}

func (f *assistiveFixture) addKnowledge(id string, records ...object) []string {
	f.t.Helper()
	d := f.knowledgeDoc(id)
	changes := []any{}
	for _, r := range records {
		changes = append(changes, object{"op": "record.add", "collection": "records", "record": r})
	}
	f.call("apply", object{"artifact_id": id, "operation_id": f.next(),
		"expected": object{"revision": d.Revision(), "model_sha256": d.Hash()}, "changes": changes})
	return f.knowledgeDoc(id).Symbols.Order[len(d.Symbols.Order):]
}

// The task in the plan fixture touches src/stage1.go.
func seedTaskKnowledge(f *assistiveFixture) {
	f.t.Helper()
	f.createKnowledge("knowledge", "CTX-TECH-STACK", "tech-stack")
	f.createKnowledge("knowledge", "CTX-SECURITY-CONTROLS", "security-controls")
	f.createKnowledge("knowledge", "CTX-CODE-MAP", "code-map")
	f.createKnowledge("decomposition", "DECOMP-PROJECT", "project")
	f.addKnowledge("CTX-TECH-STACK",
		knowledgeRecord("command", "Unit tests", "Runs every Go test.", "proposed", nil),
		knowledgeRecord("fact", "Database", "Not decided.", "unknown", nil))
	f.addKnowledge("CTX-SECURITY-CONTROLS",
		knowledgeRecord("constraint", "Session tokens", "Never log session tokens.", "user-reported", []string{"src/**"}),
		knowledgeRecord("constraint", "Billing secrets", "Card data stays in the vault.", "user-reported", []string{"billing/**"}))
	f.addKnowledge("CTX-CODE-MAP",
		knowledgeRecord("component", "Stage one", "Parses stage one input.", "inferred", []string{"src/stage1.go"}, "CTX-SECURITY-CONTROLS#CON-002", "CTX-TECH-STACK#FACT-001"))
	f.addKnowledge("DECOMP-PROJECT",
		knowledgeRecord("question", "Billing provider", "Which payment provider?", "unknown", []string{"billing/**"}))
}

func knowledgeRefs(packet object, field string) map[string]object {
	out := map[string]object{}
	for _, v := range model.A(packet[field]) {
		out[model.S(model.M(v)["ref"])] = model.M(v)
	}
	return out
}

func assertNoPermissionFields(t *testing.T, packet object) {
	t.Helper()
	b, err := json.Marshal(packet)
	if err != nil {
		t.Fatal(err)
	}
	for _, field := range []string{"requires_actor_check", "\"blocked\"", "admission", "permission_granted", "approved_to_execute", "context_ticket"} {
		if strings.Contains(string(b), field) {
			t.Fatalf("task packet carries a permission field %s", field)
		}
	}
}

func TestKnowledgeDraftHoldsUnknownAndProposedWithoutEvidence(t *testing.T) {
	f := newAssistiveFixture(t)
	f.createKnowledge("knowledge", "CTX-TECH-STACK", "tech-stack")
	ids := f.addKnowledge("CTX-TECH-STACK",
		knowledgeRecord("fact", "Database", "Not decided.", "unknown", nil),
		knowledgeRecord("command", "Unit tests", "Runs every Go test.", "proposed", nil))
	if strings.Join(ids, ",") != "FACT-001,CMD-001" {
		t.Fatalf("records were not named by type: %v", ids)
	}
	d := f.knowledgeDoc("CTX-TECH-STACK")
	command := model.M(d.Symbols.ByID["CMD-001"].Value["command"])
	if command["run_state"] != "unrun" {
		t.Fatalf("saving a declared command claimed it ran: %v", command)
	}
	if d.Data["governance"].(map[string]any)["state"] != "draft" {
		t.Fatal("a knowledge draft was promoted without a request")
	}
	f.assertNoAuthorityFiles()

	_, err := f.request("apply", object{"artifact_id": "CTX-TECH-STACK", "operation_id": f.next(),
		"expected": object{"revision": d.Revision(), "model_sha256": d.Hash()},
		"changes":  []any{object{"op": "record.add", "collection": "records", "record": knowledgeRecord("fact", "Language", "Go 1.27.", "source-observed", nil)}}})
	if fault.Code(err) != "MISSING_SOURCE" {
		t.Fatalf("an uncited source-observed claim was accepted: %v", err)
	}
}

func TestKnowledgeIDsSurviveRenameAndReorder(t *testing.T) {
	f := newAssistiveFixture(t)
	f.createKnowledge("knowledge", "CTX-CODE-MAP", "code-map")
	f.addKnowledge("CTX-CODE-MAP",
		knowledgeRecord("component", "Auth", "Session handling.", "inferred", []string{"src/auth/**"}),
		knowledgeRecord("interface", "Login API", "POST /login.", "inferred", nil, "COMP-001"))
	d := f.knowledgeDoc("CTX-CODE-MAP")
	f.call("apply", object{"artifact_id": "CTX-CODE-MAP", "operation_id": f.next(),
		"expected": object{"revision": d.Revision(), "model_sha256": d.Hash()},
		"changes": []any{
			object{"op": "record.update", "symbol": "COMP-001", "fields": object{"title": "Authentication"}},
			object{"op": "record.reorder", "collection": "records", "ids": model.List("IFACE-001", "COMP-001")},
		}})
	d = f.knowledgeDoc("CTX-CODE-MAP")
	if d.Symbols.Order[0] != "IFACE-001" || d.Symbols.ByID["COMP-001"].Value["title"] != "Authentication" {
		t.Fatalf("rename or reorder lost identity: %v", d.Symbols.Order)
	}
	if model.Strings(d.Symbols.ByID["IFACE-001"].Value["related_refs"])[0] != "COMP-001" {
		t.Fatal("a reference did not survive the rename")
	}
	exact := f.call("read", object{"artifact_id": "CTX-CODE-MAP", "symbol": "COMP-001", "mode": "exact"})
	if model.M(exact["record"])["title"] != "Authentication" {
		t.Fatal("structured read disagrees with the rendered document")
	}
}

func TestTaskContextReturnsRelevantKnowledgeWithoutAuthority(t *testing.T) {
	f := newAssistiveFixture(t)
	seedTaskKnowledge(f)
	packet := packetFor(f, "T-001")
	got := knowledgeRefs(packet, "knowledge")
	for _, want := range []string{"CTX-TECH-STACK#CMD-001", "CTX-SECURITY-CONTROLS#CON-001", "CTX-CODE-MAP#COMP-001", "CTX-TECH-STACK#FACT-001"} {
		if got[want] == nil {
			t.Fatalf("relevant knowledge %s missing from task packet: %v", want, got)
		}
	}
	if got["DECOMP-PROJECT#Q-001"] != nil {
		t.Fatal("the unrelated billing question was loaded into the task packet")
	}
	if got["CTX-CODE-MAP#COMP-001"]["selection_reason"] != "path" || got["CTX-TECH-STACK#FACT-001"]["selection_reason"] != "linked" {
		t.Fatalf("selection reasons are wrong: %v", got)
	}
	// Only the billing question stays unmatched; its sibling billing constraint
	// arrives through the component's explicit link.
	if packet["knowledge_unmatched_records"] != int64(1) {
		t.Fatalf("unrelated records were not counted as omitted: %v", packet["knowledge_unmatched_records"])
	}
	if packet["context_complete"] != false {
		t.Fatal("task packet claimed complete context")
	}
	assertNoPermissionFields(t, packet)
	f.assertNoAuthorityFiles()
}

func TestKnowledgeScopeDoesNotMatchUnrelatedWildcardPath(t *testing.T) {
	if scopeOverlaps("**/*.py", "site/foo.md") {
		t.Fatal("Python-only scope matched an unrelated Markdown file")
	}
}

func TestKnowledgeContextBoundsOmissionMetadata(t *testing.T) {
	f := newAssistiveFixture(t)
	f.createKnowledge("knowledge", "CTX-CODE-MAP", "code-map")
	records := []object{}
	for i := 0; i < 80; i++ {
		records = append(records, knowledgeRecord("component", strings.Repeat("Component", 10),
			strings.Repeat("large detail ", 80), "inferred", []string{"src/**"}))
	}
	f.addKnowledge("CTX-CODE-MAP", records...)
	packet := f.call("knowledge-context", object{"paths": model.List("src/app.py"), "budget": int64(4096)})
	b, err := json.Marshal(packet)
	if err != nil {
		t.Fatal(err)
	}
	if len(b) > 4096 {
		t.Fatalf("omission metadata exceeded the requested budget: %d bytes", len(b))
	}
}

func TestTaskContextFollowsOnlyOneExplicitHop(t *testing.T) {
	f := newAssistiveFixture(t)
	seedTaskKnowledge(f)
	packet := packetFor(f, "T-001")
	got := knowledgeRefs(packet, "knowledge")
	// COMP-001 links CON-002 (billing). It is included by the hop, but the
	// billing question it does not link stays out.
	if got["CTX-SECURITY-CONTROLS#CON-002"]["selection_reason"] != "linked" {
		t.Fatal("hop target carries the wrong reason")
	}
	if got["DECOMP-PROJECT#Q-001"] != nil {
		t.Fatal("selection recursed past one explicit hop")
	}
}

func TestUnrelatedMalformedKnowledgeDoesNotVetoTask(t *testing.T) {
	f := newAssistiveFixture(t)
	seedTaskKnowledge(f)
	bad := filepath.Join(f.root, ".codearbiter", "decomposition", "billing.html")
	if err := os.WriteFile(bad, []byte("<html>damaged</html>"), 0o644); err != nil {
		t.Fatal(err)
	}
	packet := packetFor(f, "T-001")
	if knowledgeRefs(packet, "knowledge")["CTX-CODE-MAP#COMP-001"] == nil {
		t.Fatal("a damaged unrelated document hid relevant knowledge")
	}
	unreadable := model.A(packet["knowledge_unreadable"])
	if len(unreadable) != 1 || model.M(unreadable[0])["path"] != ".codearbiter/decomposition/billing.html" {
		t.Fatalf("damaged document was not reported: %v", unreadable)
	}
	// A specification read never scans optional knowledge at all.
	f.call("read", object{"artifact_id": "SPEC-EXAMPLE", "symbol": "AC-001", "mode": "exact"})
	assertNoPermissionFields(t, packet)
}

func TestTaskContextNamesKnowledgeThatDoesNotFit(t *testing.T) {
	f := newAssistiveFixture(t)
	seedTaskKnowledge(f)
	large := strings.Repeat("Session constraint detail. ", 400)
	records := []object{}
	for i := 0; i < 6; i++ {
		records = append(records, knowledgeRecord("constraint", "Large", large, "user-reported", []string{"src/**"}))
	}
	f.addKnowledge("CTX-SECURITY-CONTROLS", records...)
	plan := f.doc("PLAN-EXAMPLE")
	packet := f.call("task-context", object{"artifact_id": "PLAN-EXAMPLE", "task": "T-001", "model_sha256": plan.Hash(), "budget": int64(32768)})
	omitted := model.A(packet["knowledge_omitted"])
	if len(omitted) == 0 {
		t.Fatal("oversized knowledge was silently dropped instead of named")
	}
	for _, v := range model.A(packet["knowledge"]) {
		r := model.M(v)
		if r["type"] == "constraint" && r["title"] == "Large" && r["statement"] != large {
			t.Fatal("a governing record was truncated")
		}
	}
	for _, v := range omitted {
		if model.S(model.M(v)["ref"]) == "" {
			t.Fatal("omitted record has no reference to read it by")
		}
	}
}

func TestKnowledgeMarkupIsInertAndLinksResolveByIdentity(t *testing.T) {
	f := newAssistiveFixture(t)
	seedTaskKnowledge(f)
	f.addKnowledge("CTX-TECH-STACK", knowledgeRecord("fact", "Hostile", `<script>alert(1)</script><a href="https://evil.example">x</a>`, "unknown", nil, "CTX-SECURITY-CONTROLS#CON-001"))
	b, err := os.ReadFile(filepath.Join(f.root, ".codearbiter", "context", "tech-stack.html"))
	if err != nil {
		t.Fatal(err)
	}
	html := string(b)
	body := html[:strings.Index(html, `<script id="ca-artifact-model"`)]
	if strings.Contains(body, "<script>alert") || strings.Contains(body, `href="https://evil.example"`) {
		t.Fatal("record text was rendered as markup")
	}
	if !strings.Contains(body, `href="../context/security-controls.html#CON-001"`) {
		t.Fatal("cross-document link does not open the record the model read")
	}
}

func TestKnowledgeWritersConflictOnlyOnTheSameDocument(t *testing.T) {
	f := newAssistiveFixture(t)
	seedTaskKnowledge(f)
	tech, security := f.knowledgeDoc("CTX-TECH-STACK"), f.knowledgeDoc("CTX-SECURITY-CONTROLS")
	edit := func(id string, d *model.Document, op string) (any, error) {
		return f.request("apply", object{"artifact_id": id, "operation_id": op,
			"expected": object{"revision": d.Revision(), "model_sha256": d.Hash()},
			"changes":  []any{object{"op": "record.update", "symbol": d.Symbols.Order[0], "fields": object{"title": "Edited " + op}}}})
	}
	if _, err := edit("CTX-TECH-STACK", tech, "writer-one-0001"); err != nil {
		t.Fatal(err)
	}
	if _, err := edit("CTX-SECURITY-CONTROLS", security, "writer-two-0001"); err != nil {
		t.Fatalf("an edit to an unrelated document conflicted: %v", err)
	}
	// Retrying the lost response replays; it does not apply twice.
	replay, err := edit("CTX-TECH-STACK", tech, "writer-one-0001")
	encoded, _ := json.Marshal(replay)
	if err != nil || !strings.Contains(string(encoded), `"replay":true`) {
		t.Fatalf("an exact retry was not a replay: %v %v", replay, err)
	}
	if _, err := edit("CTX-TECH-STACK", tech, "writer-three-001"); fault.Code(err) != "REVISION_CONFLICT" {
		t.Fatalf("a stale write overwrote newer work: %v", err)
	}
}

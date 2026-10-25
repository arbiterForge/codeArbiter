package operations

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

const legacyContext = "---\narbiter: enabled\nstage: 3\ncustom-key: keep me\n---\n<!--INITIALIZED-->\n\n# Project: Example\n\nA billing service.\n\n## Scope\n\nInvoices only.\n"
const legacyControls = "# Security controls\n\n## Auth\n\nSessions expire after 15 minutes.\npassword = hunter2hunter2\n\n<!-- migration-paths -->\n+ db/changes/**\n- db/changes/seed/**\n<!-- /migration-paths -->\n\n## Other\n\n<!-- ci-paths -->\n+ build/pipelines/**\n<!-- /ci-paths -->\n"
const legacyTech = "# Tech stack\n\n## Commands\n\n```\n## not a heading inside a fence\nnpm test\n```\n\n## Runtime\n\nNode 22.\n"

type legacyRepo struct {
	*assistiveFixture
}

func newLegacyRepo(t *testing.T) legacyRepo {
	t.Helper()
	root := testutil.Root(t)
	f := &assistiveFixture{t: t, root: root}
	write := func(rel, body string) {
		p := filepath.Join(root, filepath.FromSlash(rel))
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, []byte(body), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	write(".codearbiter/CONTEXT.md", legacyContext)
	write(".codearbiter/security-controls.md", legacyControls)
	write(".codearbiter/tech-stack.md", legacyTech)
	write(".codearbiter/code-map.md", "# Code map\n\n- `src/` — everything\n")
	write(".codearbiter/.provenance/tech-stack.json", `{"schema":2}`)
	write(".codearbiter/plans/decomposition/_session.md", "# Session\n\nPhase 4.\n")
	write(".codearbiter/plans/01-architecture-breakdown.md", "# Architecture\n\n## Components\n\nAPI and worker.\n")
	write(".codearbiter/open-tasks.md", "# Open tasks\n")
	return legacyRepo{f}
}

func (r legacyRepo) read(rel string) (string, bool) {
	b, err := os.ReadFile(filepath.Join(r.root, filepath.FromSlash(rel)))
	if os.IsNotExist(err) {
		return "", false
	}
	if err != nil {
		r.t.Fatal(err)
	}
	return string(b), true
}

// prepare creates the empty knowledge documents the agent converts into, as
// knowledge.py convert does, and records one entry for each document whose
// Markdown has content, standing in for the agent's inference.
func (r legacyRepo) prepare() {
	r.t.Helper()
	r.createDocuments()
	r.record()
}

func (r legacyRepo) createDocuments() {
	r.t.Helper()
	for _, slug := range []string{"project", "tech-stack", "coding-standards", "security-controls", "code-map"} {
		r.createKnowledge("knowledge", knowledgeID(slug), slug)
	}
	r.createKnowledge("decomposition", "DECOMP-PROJECT", "project")
}

func (r legacyRepo) record() {
	r.t.Helper()
	r.addKnowledge("CTX-PROJECT", knowledgeRecord("scope", "Invoices", "Invoices only.", "user-reported", nil))
	r.addKnowledge("CTX-TECH-STACK", knowledgeRecord("fact", "Runtime", "Node 22.", "user-reported", nil))
	r.addKnowledge("CTX-TECH-STACK", knowledgeRecord("command", "Tests", "Run npm test.", "user-reported", nil))
	r.addKnowledge("CTX-SECURITY-CONTROLS", knowledgeRecord("constraint", "Sessions", "Sessions expire after 15 minutes.", "user-reported", nil))
	r.addKnowledge("CTX-CODE-MAP", knowledgeRecord("component", "Everything", "src/ holds everything.", "user-reported", []string{"src/**"}))
	r.addKnowledge("DECOMP-PROJECT", knowledgeRecord("component", "API and worker", "Two components.", "user-reported", nil))
}

func (r legacyRepo) sectionCoverage() []any {
	r.t.Helper()
	inventory := r.call("knowledge-cutover", object{"operation_id": r.next(), "mode": "sections"})
	covered := []any{}
	for _, value := range model.A(inventory["sections"]) {
		section := model.M(value)
		refs := []any{}
		if section["content"] == true {
			ref := map[string]string{
				"CTX-PROJECT":           "SCOPE-001",
				"CTX-TECH-STACK":        "FACT-001",
				"CTX-SECURITY-CONTROLS": "CON-001",
				"CTX-CODE-MAP":          "COMP-001",
				"DECOMP-PROJECT":        "COMP-001",
			}[model.S(section["artifact_id"])]
			if model.S(section["heading"]) == "Commands" {
				ref = "CMD-001"
			}
			refs = append(refs, model.S(section["artifact_id"])+"#"+ref)
		}
		covered = append(covered, object{"section": section["id"], "records": refs})
	}
	return covered
}

func (r legacyRepo) cutover(op string) object {
	r.t.Helper()
	coverage := r.sectionCoverage()
	preview := r.call("knowledge-cutover", object{"operation_id": op, "mode": "preview", "coverage": coverage})
	return r.call("knowledge-cutover", object{"operation_id": op, "mode": "apply", "expected": preview["expected"], "coverage": coverage})
}

func TestKnowledgeCutoverPreservesSettingsAndScopeBlocks(t *testing.T) {
	r := newLegacyRepo(t)
	r.prepare()
	before, _ := r.read(".codearbiter/CONTEXT.md")
	r.call("knowledge-cutover", object{"operation_id": "cutover-0000001", "mode": "preview", "coverage": r.sectionCoverage()})
	if after, _ := r.read(".codearbiter/CONTEXT.md"); after != before {
		t.Fatal("preview wrote to the repository")
	}
	r.cutover("cutover-0000001")

	ctx, _ := r.read(".codearbiter/CONTEXT.md")
	for _, want := range []string{"arbiter: enabled\n", "stage: 3\n", "custom-key: keep me\n", "context-format: html\n", "<!--INITIALIZED-->\n"} {
		if !strings.Contains(ctx, want) {
			t.Fatalf("CONTEXT.md lost %q:\n%s", want, ctx)
		}
	}
	if strings.Contains(ctx, "Invoices only.") {
		t.Fatal("CONTEXT.md still carries the narrative; two narratives are active")
	}
	controls, _ := r.read(".codearbiter/security-controls.md")
	for _, block := range []string{"<!-- migration-paths -->\n+ db/changes/**\n- db/changes/seed/**\n<!-- /migration-paths -->", "<!-- ci-paths -->\n+ build/pipelines/**\n<!-- /ci-paths -->"} {
		if !strings.Contains(controls, block) {
			t.Fatalf("an operative scope block changed:\n%s", controls)
		}
	}
	if strings.Contains(controls, "Sessions expire") {
		t.Fatal("narrative stayed in the configuration file")
	}
	for _, gone := range []string{".codearbiter/tech-stack.md", ".codearbiter/code-map.md", ".codearbiter/.provenance/tech-stack.json", ".codearbiter/plans/decomposition/_session.md", ".codearbiter/plans/01-architecture-breakdown.md"} {
		if _, ok := r.read(gone); ok {
			t.Fatalf("%s is still an active narrative after cutover", gone)
		}
	}
	attributes, _ := r.read(".codearbiter/.gitattributes")
	if !strings.Contains(attributes, "context/*.html -text\n") || !strings.Contains(attributes, "decomposition/*.html -text\n") {
		t.Fatalf("knowledge pages are exposed to line-ending conversion:\n%s", attributes)
	}
	if got := r.knowledgeDoc("CTX-TECH-STACK"); len(model.A(got.Norm()["records"])) != 2 {
		t.Fatal("the cutover changed the agent's recorded knowledge")
	}
}

func TestKnowledgeCutoverRefusesUnrecordedContent(t *testing.T) {
	r := newLegacyRepo(t)
	if _, err := r.request("knowledge-cutover", object{"operation_id": "cutover-0000005", "mode": "preview"}); fault.Code(err) != "NOT_PREPARED" {
		t.Fatalf("a cutover without knowledge documents was not refused: %v", err)
	}
	r.createDocuments()
	before, _ := r.read(".codearbiter/tech-stack.md")
	_, err := r.request("knowledge-cutover", object{"operation_id": "cutover-0000006", "mode": "preview"})
	if fault.Code(err) != "UNCOVERED_SECTION" {
		t.Fatalf("Markdown with content but no records was accepted for removal: %v", err)
	}
	if after, ok := r.read(".codearbiter/tech-stack.md"); !ok || after != before {
		t.Fatal("a refused cutover changed the Markdown")
	}
	// coding-standards.md is absent and needs nothing; every present document
	// with content needs at least one record before its file is removed.
	r.record()
	r.cutover("cutover-0000006")
}

func TestKnowledgeCutoverRefusesUnmappedSections(t *testing.T) {
	r := newLegacyRepo(t)
	r.prepare()
	if _, err := r.request("knowledge-cutover", object{"operation_id": "cutover-sections-0001", "mode": "preview"}); fault.Code(err) != "UNCOVERED_SECTION" {
		t.Fatalf("cutover accepted Markdown sections without an explicit record mapping: %v", err)
	}
	coverage := r.sectionCoverage()
	for _, value := range coverage {
		row := model.M(value)
		if refs := model.A(row["records"]); len(refs) > 0 {
			row["records"] = []any{"CTX-CODE-MAP#COMP-001"}
			break
		}
	}
	if _, err := r.request("knowledge-cutover", object{"operation_id": "cutover-sections-0002", "mode": "preview", "coverage": coverage}); fault.Code(err) != "INVALID_COVERAGE" {
		t.Fatalf("cutover accepted a mapping to another document: %v", err)
	}
}

func TestKnowledgeCutoverRequiresCoverageForUninitializedNarrative(t *testing.T) {
	r := newLegacyRepo(t)
	p := filepath.Join(r.root, ".codearbiter", "CONTEXT.md")
	if err := os.WriteFile(p, []byte(strings.Replace(legacyContext, "<!--INITIALIZED-->\n", "", 1)), 0o644); err != nil {
		t.Fatal(err)
	}
	inventory := r.call("knowledge-cutover", object{"operation_id": r.next(), "mode": "sections"})
	meaningful := 0
	for _, value := range model.A(inventory["sections"]) {
		section := model.M(value)
		if section["source"] == contextPath && section["content"] == true {
			meaningful++
		}
	}
	if meaningful == 0 {
		t.Fatal("uninitialized but authored CONTEXT.md narrative was classified as empty")
	}
}

func TestKnowledgeCutoverPagesLargeSectionInventory(t *testing.T) {
	r := newLegacyRepo(t)
	p := filepath.Join(r.root, ".codearbiter", "tech-stack.md")
	var markdown strings.Builder
	markdown.WriteString("# Tech stack\n")
	for i := 0; i < 300; i++ {
		markdown.WriteString("\n## Rule ")
		markdown.WriteString(strings.Repeat("x", 32))
		markdown.WriteString("\nKeep the rule.\n")
	}
	if err := os.WriteFile(p, []byte(markdown.String()), 0o644); err != nil {
		t.Fatal(err)
	}
	count, cursor := 0, int64(0)
	for {
		page := r.call("knowledge-cutover", object{"operation_id": r.next(), "mode": "sections", "cursor": cursor})
		encoded, err := canonical.Marshal(page)
		if err != nil || len(encoded) > 60_000 {
			t.Fatalf("section page exceeds bridge budget: bytes=%d err=%v", len(encoded), err)
		}
		count += len(model.A(page["sections"]))
		if page["next_cursor"] == nil {
			break
		}
		next := model.I(page["next_cursor"])
		if next <= cursor {
			t.Fatal("section cursor did not advance")
		}
		cursor = next
	}
	if count < 300 {
		t.Fatalf("paged inventory lost sections: %d", count)
	}
}

func TestKnowledgeCutoverRejectsCursorBeyondNativeInt(t *testing.T) {
	r := newLegacyRepo(t)
	_, err := r.request("knowledge-cutover", object{
		"operation_id": r.next(), "mode": "sections", "cursor": int64(1 << 32),
	})
	if fault.Code(err) != "INVALID_CURSOR" {
		t.Fatalf("large cursor must be rejected before int conversion: %v", err)
	}
}

func TestKnowledgeCutoverRetryKeepsLaterWorkAndStaleApplyFails(t *testing.T) {
	r := newLegacyRepo(t)
	r.prepare()
	coverage := r.sectionCoverage()
	preview := r.call("knowledge-cutover", object{"operation_id": "cutover-0000002", "mode": "preview", "coverage": coverage})
	r.call("knowledge-cutover", object{"operation_id": "cutover-0000002", "mode": "apply", "expected": preview["expected"], "coverage": coverage})
	r.addKnowledge("CTX-TECH-STACK", knowledgeRecord("fact", "Later", "Written after the cutover.", "user-reported", nil))
	after := r.knowledgeDoc("CTX-TECH-STACK").Hash()

	replay := r.call("knowledge-cutover", object{"operation_id": "cutover-0000002", "mode": "apply", "expected": preview["expected"], "coverage": coverage})
	if !strings.Contains(canonicalString(t, replay), `"replay":true`) {
		t.Fatalf("an exact retry did not replay: %v", replay)
	}
	if r.knowledgeDoc("CTX-TECH-STACK").Hash() != after {
		t.Fatal("retrying the cutover overwrote later work")
	}
	_, err := r.request("knowledge-cutover", object{"operation_id": "cutover-0000003", "mode": "apply", "expected": preview["expected"], "coverage": coverage})
	if fault.Code(err) != "ALREADY_CONVERTED" {
		t.Fatalf("a second cutover over converted state was not refused: %v", err)
	}

	stale := newLegacyRepo(t)
	stale.prepare()
	staleCoverage := stale.sectionCoverage()
	old := stale.call("knowledge-cutover", object{"operation_id": "cutover-0000004", "mode": "preview", "coverage": staleCoverage})
	if err := os.WriteFile(filepath.Join(stale.root, ".codearbiter", "tech-stack.md"), []byte("# Tech stack\n\nEdited after it was read.\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := stale.request("knowledge-cutover", object{"operation_id": "cutover-0000004", "mode": "apply", "expected": old["expected"], "coverage": staleCoverage}); fault.Code(err) != "REVISION_CONFLICT" {
		t.Fatalf("a cutover over Markdown edited after it was read was accepted: %v", err)
	}
	if body, _ := stale.read(".codearbiter/tech-stack.md"); !strings.Contains(body, "Edited after it was read.") {
		t.Fatal("the refused cutover still changed the file")
	}
}

func TestReadsNeverMigrate(t *testing.T) {
	r := newLegacyRepo(t)
	r.call("init-store", object{})
	r.call("knowledge-context", object{"paths": model.List("src/app.ts")})
	r.call("index", object{})
	if ctx, _ := r.read(".codearbiter/CONTEXT.md"); ctx != legacyContext {
		t.Fatal("a read changed the repository format")
	}
	if _, ok := r.read(".codearbiter/tech-stack.md"); !ok {
		t.Fatal("a read removed a Markdown narrative")
	}
}

func canonicalString(t *testing.T, v any) string {
	t.Helper()
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}

func newGreenfield(t *testing.T) *assistiveFixture {
	t.Helper()
	root := testutil.Root(t)
	f := &assistiveFixture{t: t, root: root}
	for rel, body := range map[string]string{
		".codearbiter/CONTEXT.md":    "---\narbiter: enabled\nstage: 1\ncontext-format: html\n---\n",
		".codearbiter/open-tasks.md": "# Open tasks\n",
	} {
		p := filepath.Join(root, filepath.FromSlash(rel))
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, []byte(body), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	return f
}

func (f *assistiveFixture) initializeKnowledge() (any, error) {
	b, err := os.ReadFile(filepath.Join(f.root, ".codearbiter", "CONTEXT.md"))
	if err != nil {
		f.t.Fatal(err)
	}
	return f.request("knowledge-initialize", object{"operation_id": f.next(), "expected": object{".codearbiter/CONTEXT.md": canonical.BytesHash(b)}})
}

func TestGreenfieldInitializesWithUnknownsAndKeepsActivation(t *testing.T) {
	f := newGreenfield(t)
	for _, slug := range []string{"project", "tech-stack", "coding-standards", "security-controls"} {
		f.createKnowledge("knowledge", "CTX-"+strings.ToUpper(slug), slug)
	}
	if _, err := f.initializeKnowledge(); fault.Code(err) != "INVALID_CONTEXT_OUTPUT" {
		t.Fatalf("initialization succeeded without the code map: %v", err)
	}
	f.createKnowledge("knowledge", "CTX-CODE-MAP", "code-map")
	f.addKnowledge("CTX-TECH-STACK", knowledgeRecord("fact", "Database", "Undecided.", "unknown", nil))
	if _, err := f.initializeKnowledge(); err != nil {
		t.Fatalf("an unanswered question blocked structural initialization: %v", err)
	}
	b, _ := os.ReadFile(filepath.Join(f.root, ".codearbiter", "CONTEXT.md"))
	if string(b) != "---\narbiter: enabled\nstage: 1\ncontext-format: html\n---\n<!--INITIALIZED-->\n" {
		t.Fatalf("initialization changed activation or stage: %q", b)
	}
	if model.S(f.knowledgeDoc("CTX-TECH-STACK").Symbols.ByID["FACT-001"].Value["basis"]) != "unknown" {
		t.Fatal("the unresolved database lost its unknown label")
	}
	f.assertNoAuthorityFiles()
	if _, err := f.initializeKnowledge(); fault.Code(err) != "ALREADY_INITIALIZED" {
		t.Fatalf("a second initialization was not refused: %v", err)
	}
}

func TestKnowledgeContextIsolatesDamagedDocuments(t *testing.T) {
	f := newGreenfield(t)
	seedTaskKnowledge(f)
	if err := os.WriteFile(filepath.Join(f.root, ".codearbiter", "context", "coding-standards.html"), []byte("<p>broken</p>"), 0o644); err != nil {
		t.Fatal(err)
	}
	out := f.call("knowledge-context", object{"paths": model.List("src/auth/session.ts")})
	got := knowledgeRefs(out, "knowledge")
	if got["CTX-SECURITY-CONTROLS#CON-001"] == nil || got["CTX-TECH-STACK#CMD-001"] == nil {
		t.Fatalf("path lookup missed relevant knowledge: %v", got)
	}
	if len(model.A(out["knowledge_unreadable"])) != 1 {
		t.Fatalf("the damaged document was not reported: %v", out["knowledge_unreadable"])
	}
	assertNoPermissionFields(t, out)
	_ = render.Version
}

func mergeFixture(t *testing.T) (*assistiveFixture, string, []byte) {
	t.Helper()
	f := newGreenfield(t)
	f.createKnowledge("knowledge", "CTX-TECH-STACK", "tech-stack")
	f.addKnowledge("CTX-TECH-STACK", knowledgeRecord("fact", "Runtime", "Node 22.", "user-reported", nil))
	p := filepath.Join(f.root, ".codearbiter", "context", "tech-stack.html")
	base, err := os.ReadFile(p)
	if err != nil {
		t.Fatal(err)
	}
	return f, p, base
}

func (f *assistiveFixture) branch(p string, base []byte, records ...object) []byte {
	f.t.Helper()
	if err := os.WriteFile(p, base, 0o644); err != nil {
		f.t.Fatal(err)
	}
	f.addKnowledge("CTX-TECH-STACK", records...)
	b, err := os.ReadFile(p)
	if err != nil {
		f.t.Fatal(err)
	}
	return b
}

func TestKnowledgeMergeKeepsBothSidesAndRenamesCollidingIDs(t *testing.T) {
	f, p, base := mergeFixture(t)
	ours := f.branch(p, base, knowledgeRecord("command", "Unit tests", "npm test.", "proposed", nil))
	theirs := f.branch(p, base, knowledgeRecord("command", "Lint", "npm run lint.", "proposed", nil),
		knowledgeRecord("fact", "Linter", "ESLint, run by the lint command.", "user-reported", nil, "CMD-001"))
	conflicted := []byte("<<<<<<< ours\nconflict\n>>>>>>> theirs\n")
	if err := os.WriteFile(p, conflicted, 0o644); err != nil {
		t.Fatal(err)
	}
	out := f.call("knowledge-merge", object{"operation_id": f.next(), "path": ".codearbiter/context/tech-stack.html",
		"base": string(base), "ours": string(ours), "theirs": string(theirs), "expected_current_sha256": canonical.BytesHash(conflicted)})
	if out["merged"] != true || model.M(out["renamed"])["CMD-001"] != "CMD-002" {
		t.Fatalf("colliding new records were not both kept: %v", out)
	}
	d := f.knowledgeDoc("CTX-TECH-STACK")
	if d.Symbols.ByID["CMD-001"].Value["title"] != "Unit tests" || d.Symbols.ByID["CMD-002"].Value["title"] != "Lint" {
		t.Fatal("merge lost a side's record")
	}
	if got := model.Strings(d.Symbols.ByID["FACT-002"].Value["related_refs"]); len(got) != 1 || got[0] != "CMD-002" {
		t.Fatalf("an incoming link did not follow its renamed record: %v", got)
	}
}

func TestKnowledgeMergeRewritesIncomingEditReferences(t *testing.T) {
	f, p, base := mergeFixture(t)
	ours := f.branch(p, base, knowledgeRecord("command", "Unit tests", "npm test.", "proposed", nil))
	f.branch(p, base, knowledgeRecord("command", "Lint", "npm run lint.", "proposed", nil))
	d := f.knowledgeDoc("CTX-TECH-STACK")
	f.call("apply", object{"artifact_id": "CTX-TECH-STACK", "operation_id": f.next(),
		"expected": object{"revision": d.Revision(), "model_sha256": d.Hash()},
		"changes": []any{object{"op": "record.update", "symbol": "FACT-001",
			"fields": object{"related_refs": model.List("CMD-001")}}}})
	theirs, err := os.ReadFile(p)
	if err != nil {
		t.Fatal(err)
	}
	conflicted := []byte("<<<<<<< ours\nconflict\n>>>>>>> theirs\n")
	if err := os.WriteFile(p, conflicted, 0o644); err != nil {
		t.Fatal(err)
	}
	f.call("knowledge-merge", object{"operation_id": f.next(), "path": ".codearbiter/context/tech-stack.html",
		"base": string(base), "ours": string(ours), "theirs": string(theirs),
		"expected_current_sha256": canonical.BytesHash(conflicted)})
	d = f.knowledgeDoc("CTX-TECH-STACK")
	if got := model.Strings(d.Symbols.ByID["FACT-001"].Value["related_refs"]); len(got) != 1 || got[0] != "CMD-002" {
		t.Fatalf("incoming edit linked to the wrong colliding record: %v", got)
	}
}

func TestKnowledgeMergeRefusesTheSameRecordChangedTwice(t *testing.T) {
	f, p, base := mergeFixture(t)
	edit := func(title string) []byte {
		if err := os.WriteFile(p, base, 0o644); err != nil {
			t.Fatal(err)
		}
		d := f.knowledgeDoc("CTX-TECH-STACK")
		f.call("apply", object{"artifact_id": "CTX-TECH-STACK", "operation_id": f.next(),
			"expected": object{"revision": d.Revision(), "model_sha256": d.Hash()},
			"changes":  []any{object{"op": "record.update", "symbol": "FACT-001", "fields": object{"statement": title}}}})
		b, _ := os.ReadFile(p)
		return b
	}
	ours, theirs := edit("Node 22."+" LTS."), edit("Node 24.")
	if err := os.WriteFile(p, []byte("conflicted"), 0o644); err != nil {
		t.Fatal(err)
	}
	out := f.call("knowledge-merge", object{"operation_id": f.next(), "path": ".codearbiter/context/tech-stack.html",
		"base": string(base), "ours": string(ours), "theirs": string(theirs), "expected_current_sha256": canonical.BytesHash([]byte("conflicted"))})
	if out["merged"] != false || len(model.A(out["conflicts"])) != 1 {
		t.Fatalf("a real conflict was silently resolved: %v", out)
	}
	if b, _ := os.ReadFile(p); string(b) != "conflicted" {
		t.Fatal("a refused merge wrote the file")
	}
}

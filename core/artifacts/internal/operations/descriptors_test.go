package operations

// NT-03 / N-F02: one descriptor table owns operation discovery and finite
// traits. Transition rows: N01:01, N01:03, N01:04, N27:01, N27:02, N37:01.

import (
	"bytes"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

// Frozen pre-NT-03 sets. The refactor must keep each one exactly, except the
// deliberate addition of the already-implemented repair-apply to discovery.
var (
	legacyAdvertised = strings.Fields(`capabilities schema create apply read read-batch plan-verification outline validate index identity snapshot evidence-context context-evidence-context context-finalize-evidence-context context-preview context-finalize-preview context-apply rebrand repair-preview approve plan-bind sprint-approval-context sprint-approve smarts-apply eligible task-context verification-status task-start task-check task-review task-block task-reconcile scope-reconcile accept-scope prerequisite farm-project farm-seal farm-verify recover diff capture capture-observation export migration-preview migration-apply migration-rollback init-store knowledge-context knowledge-initialize knowledge-cutover knowledge-merge work-create work-adopt work-get work-update work-context work-view work-list work-origins project-view cycle-view work-provider-get work-provider-configure work-transition-map-get work-transition-map-configure work-coordinate-resume work-effect-stage work-effect-claim work-effect-record work-effect-conflict work-effect-adopt work-project-get work-project-configure work-project-stage work-project-stage-field work-project-claim work-project-record work-project-conflict`)
	legacyJournaled = strings.Fields(`knowledge-initialize knowledge-cutover knowledge-merge work-create work-adopt work-update work-provider-configure work-transition-map-configure work-coordinate-resume work-effect-stage work-effect-claim work-effect-record work-effect-conflict work-effect-adopt work-project-configure work-project-stage work-project-stage-field work-project-claim work-project-record work-project-conflict migration-rollback export migration-apply create apply rebrand repair-apply approve plan-bind sprint-approve smarts-apply task-start task-check task-review task-block task-reconcile scope-reconcile accept-scope prerequisite farm-project recover`)
	legacyShared = strings.Fields(`snapshot identity outline read-batch plan-verification eligible task-context verification-status knowledge-context work-get work-context work-view work-list work-origins project-view cycle-view work-provider-get work-project-get work-transition-map-get`)
)

func sortedSet(values []string) []string {
	seen := map[string]bool{}
	out := []string{}
	for _, v := range values {
		if !seen[v] {
			seen[v] = true
			out = append(out, v)
		}
	}
	sort.Strings(out)
	return out
}

func TestOperationDescriptorsPreserveLegacySetsAndAdvertiseRepairApply(t *testing.T) {
	want := sortedSet(append(append([]string{}, legacyAdvertised...), "repair-apply"))
	if got := Names(); strings.Join(got, " ") != strings.Join(want, " ") {
		t.Fatalf("advertised operations changed beyond repair-apply:\n got %v\nwant %v", got, want)
	}
	journaledSet := []string{}
	sharedSet := []string{}
	for _, name := range Names() {
		if JournaledMutation(name) {
			journaledSet = append(journaledSet, name)
		}
		d, _ := Descriptor(name)
		if d.Lock == "shared" {
			sharedSet = append(sharedSet, name)
		}
		// Run's lock choice and the declared trait agree for every operation.
		if got := sharedObservation(name, object{}); got != (d.Lock == "shared") {
			t.Errorf("%s: Run lock shared=%v but descriptor says %q", name, got, d.Lock)
		}
	}
	if strings.Join(journaledSet, " ") != strings.Join(sortedSet(legacyJournaled), " ") {
		t.Fatalf("journaled replay set changed: %v", journaledSet)
	}
	if strings.Join(sharedSet, " ") != strings.Join(sortedSet(legacyShared), " ") {
		t.Fatalf("shared observation set changed: %v", sharedSet)
	}
	if d, _ := Descriptor("read"); d.Lock != "by-mode" || !sharedObservation("read", object{"mode": "exact"}) || sharedObservation("read", object{}) {
		t.Fatal("read lock no longer depends on its mode")
	}
}

func TestOperationDescriptorTraitsAreClosedAndHonest(t *testing.T) {
	vocab := map[string]map[string]bool{
		"effect": {"metadata": true, "store-initialization": true, "observation": true, "contextual-read": true,
			"derived-write": true, "immutable-capture": true, "journaled-mutation": true, "owner-journaled-mutation": true, "recovery": true},
		"lock":     {"none": true, "shared": true, "exclusive": true, "by-mode": true},
		"evidence": {"none": true, "ordinary": true, "explicit": true, "by-request": true},
	}
	for _, name := range Names() {
		d, ok := Descriptor(name)
		if !ok {
			t.Fatalf("%s has no descriptor", name)
		}
		if !vocab["effect"][d.Effect] || !vocab["lock"][d.Lock] || !vocab["evidence"][d.Evidence] {
			t.Errorf("%s uses an undeclared trait value: %+v", name, d)
		}
		if _, err := RequestSchema(name); err != nil {
			t.Errorf("%s is advertised without a closed request contract: %v", name, err)
		}
		// A write-free effect class declares no writes, and every writing class
		// declares what it writes: Journaled=false is never "writes nothing".
		writeFree := d.Effect == "metadata" || d.Effect == "observation"
		if writeFree != (len(d.Writes) == 0) {
			t.Errorf("%s effect %q disagrees with its writes %v", name, d.Effect, d.Writes)
		}
		if d.Journaled != (d.Effect == "journaled-mutation" || d.Effect == "recovery") {
			t.Errorf("%s journaled=%v contradicts effect %q", name, d.Journaled, d.Effect)
		}
	}
	for _, unknown := range []string{"repair", "task-delete", ""} {
		if _, err := RequestSchema(unknown); fault.Code(err) != "UNKNOWN_OPERATION" {
			t.Errorf("unknown operation %q was admitted: %v", unknown, err)
		}
	}
}

// operationLiterals collects every string literal compared with the variable
// `op` inside the named functions: `case "x"` under `switch op` and `op == "x"`.
// It enumerates handlers independently of Names, so an omitted operation fails.
func operationLiterals(t *testing.T, file string, functions ...string) map[string]bool {
	t.Helper()
	parsed, err := parser.ParseFile(token.NewFileSet(), file, nil, 0)
	if err != nil {
		t.Fatal(err)
	}
	wanted := map[string]bool{}
	for _, f := range functions {
		wanted[f] = true
	}
	out := map[string]bool{}
	isOp := func(e ast.Expr) bool { id, ok := e.(*ast.Ident); return ok && id.Name == "op" }
	add := func(e ast.Expr) {
		if lit, ok := e.(*ast.BasicLit); ok && lit.Kind == token.STRING {
			v, _ := strconv.Unquote(lit.Value)
			out[v] = true
		}
	}
	for _, decl := range parsed.Decls {
		fn, ok := decl.(*ast.FuncDecl)
		if !ok || !wanted[fn.Name.Name] {
			continue
		}
		ast.Inspect(fn.Body, func(n ast.Node) bool {
			switch node := n.(type) {
			case *ast.SwitchStmt:
				if isOp(node.Tag) {
					for _, stmt := range node.Body.List {
						for _, e := range stmt.(*ast.CaseClause).List {
							add(e)
						}
					}
				}
			case *ast.BinaryExpr:
				if node.Op == token.EQL || node.Op == token.NEQ {
					if isOp(node.X) {
						add(node.Y)
					} else if isOp(node.Y) {
						add(node.X)
					}
				}
			}
			return true
		})
	}
	return out
}

func TestOperationRegistryReverseClosure(t *testing.T) {
	names := map[string]bool{}
	for _, n := range Names() {
		names[n] = true
	}
	schemaCases := operationLiterals(t, "protocol.go", "RequestSchema", "JournaledMutation")
	dispatched := operationLiterals(t, "engine.go", "Run", "sharedObservation")
	for label, set := range map[string]map[string]bool{"request-schema": schemaCases, "dispatch": dispatched} {
		for op := range set {
			if !names[op] {
				t.Errorf("%s handles %q, which discovery does not advertise", label, op)
			}
		}
	}
	for op := range names {
		if !schemaCases[op] {
			t.Errorf("advertised %q has no request-schema case", op)
		}
		if !dispatched[op] {
			t.Errorf("advertised %q has no Run dispatch", op)
		}
	}
}

func TestCapabilitiesAdvertiseVersionedOperationContract(t *testing.T) {
	out, err := Run(".", "capabilities", object{"protocol": Protocol})
	if err != nil {
		t.Fatal(err)
	}
	caps := model.M(out)
	contract := model.M(caps["operation_contract"])
	if contract["format"] != OperationContractFormat {
		t.Fatalf("operation contract is not versioned: %v", contract)
	}
	rows := model.A(contract["operations"])
	names := caps["operations"].([]string)
	if len(rows) != len(names) {
		t.Fatalf("descriptor rows %d disagree with operations %d", len(rows), len(names))
	}
	for i, row := range rows {
		if model.M(row)["name"] != names[i] {
			t.Fatalf("descriptor order disagrees with operations at %d", i)
		}
		if names[i] == "repair-apply" && (model.M(row)["journaled"] != true || model.M(row)["effect"] != "journaled-mutation") {
			t.Fatalf("repair-apply traits are wrong: %v", row)
		}
	}
}

// Acceptance "Discover and execute repair": both operations are discoverable,
// apply is CAS-bound to the preview, and the exact retry replays the result.
func TestRepairIsDiscoverableAppliedAndReplayed(t *testing.T) {
	f := newAssistiveFixture(t)
	caps, err := Run(f.root, "capabilities", object{"protocol": Protocol})
	if err != nil {
		t.Fatal(err)
	}
	advertised := strings.Join(model.M(caps)["operations"].([]string), " ")
	for _, op := range []string{"repair-preview", "repair-apply"} {
		if !strings.Contains(" "+advertised+" ", " "+op+" ") {
			t.Fatalf("%s is not discoverable", op)
		}
	}
	p := filepath.Join(f.root, ".codearbiter", "specs", "example.html")
	b, err := os.ReadFile(p)
	if err != nil {
		t.Fatal(err)
	}
	drifted := bytes.Replace(b, []byte("Configuration precedence"), []byte("Misleading replacement"), 1)
	if bytes.Equal(drifted, b) {
		t.Fatal("fixture did not introduce view drift")
	}
	if err := os.WriteFile(p, drifted, 0644); err != nil {
		t.Fatal(err)
	}
	preview := f.call("repair-preview", object{"path": ".codearbiter/specs/example.html"})
	stale := object{"operation_id": "repair-stale-0001", "path": preview["path"],
		"expected_bytes_sha256": strings.Repeat("0", 64), "preview_sha256": preview["preview_sha256"]}
	if _, err := f.request("repair-apply", stale); fault.Code(err) != "REVISION_CONFLICT" {
		t.Fatalf("repair-apply ignored its preview binding: %v", err)
	}
	request := object{"operation_id": "repair-apply-0001", "path": preview["path"],
		"expected_bytes_sha256": preview["expected_bytes_sha256"], "preview_sha256": preview["preview_sha256"]}
	first := f.call("repair-apply", request)
	repaired, _ := os.ReadFile(p)
	if first["transaction"].(store.Outcome).Replay || bytes.Equal(repaired, drifted) {
		t.Fatal("repair did not apply")
	}
	again := f.call("repair-apply", object{"operation_id": "repair-apply-0001", "path": preview["path"],
		"expected_bytes_sha256": preview["expected_bytes_sha256"], "preview_sha256": preview["preview_sha256"]})
	if !again["transaction"].(store.Outcome).Replay {
		t.Fatal("exact repair retry was not a replay")
	}
	if now, _ := os.ReadFile(p); !bytes.Equal(now, repaired) {
		t.Fatal("replay rewrote repaired bytes")
	}
	f.doc("SPEC-EXAMPLE")
}

// Every implemented operation appears in the protocol document's family table.
func TestProtocolDocumentListsEveryOperation(t *testing.T) {
	b, err := os.ReadFile(filepath.Join("..", "..", "..", "..", "docs", "artifacts", "PROTOCOL.md"))
	if err != nil {
		t.Fatal(err)
	}
	text := string(b)
	start := strings.Index(text, "## Operation families")
	if start < 0 {
		t.Fatal("protocol document lost its operation family table")
	}
	section := text[start:]
	if end := strings.Index(section[3:], "\n## "); end >= 0 {
		section = section[:end+3]
	}
	for _, name := range Names() {
		if !strings.Contains(section, "`"+name+"`") {
			t.Errorf("protocol operation family table omits %s", name)
		}
	}
}

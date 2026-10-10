package operations

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/evidence"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/observation"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

// Completion fixtures exercise the real engine with explicitly synthetic
// producers. They do not claim a real host or verification command ran.
func TestCompletionPublicationClosureRetainsIntegrity(t *testing.T) {
	for _, mutation := range []string{"unchanged", "source", "unknown-output", "malformed-output", "tamper"} {
		t.Run(mutation, func(t *testing.T) {
			h, _ := completionHarness(t)
			writeFixture(t, h.root, ".gitignore", nil)
			startNativeV1FixtureTask(t, h, "T-001")
			verification := completionVerification(t, h, "T-001", h.root, mutation)
			switch mutation {
			case "source":
				writeFixture(t, h.root, "src/stage1.go", []byte("ordinary source changed\n"))
			case "unknown-output":
				writeFixture(t, h.root, ".codearbiter/.artifacts/unknown.txt", []byte("unknown bytes"))
			case "malformed-output":
				writeFixture(t, h.root, ".codearbiter/.artifacts/observations/"+mustHashFixture(t, "bad")+".json", []byte("malformed"))
			}
			_, err := h.request("evidence-context", object{"artifact_id": "PLAN-EXAMPLE", "activity": "spec_review", "record_id": "T-001", "completion_selection": object{"verification_receipts": []any{verification}, "supporting_files": []any{}}})
			if mutation == "unchanged" {
				if err != nil {
					t.Fatalf("native publication invalidated normalized closure: %v", err)
				}
			} else if err == nil {
				t.Fatalf("%s was accepted as fresh completion evidence", mutation)
			}
		})
	}
}

func TestCompletionReviewRejectsDefinitionOnlyReceipt(t *testing.T) {
	h := newFarmHarness(t)
	h.createPair()
	startNativeV1FixtureTask(t, h, "T-001")
	source, payload := nativeV1ReviewSource(t, h, "T-001", "spec_review")
	review := h.run("capture-observation", source)["receipt"]
	commands := []any{}
	for _, value := range model.A(h.doc("PLAN-EXAMPLE").Symbols.ByID["T-001"].Value["verification"]) {
		definition := model.M(value)
		tests := []any{}
		for _, name := range model.Strings(definition["required_tests"]) {
			tests = append(tests, object{"name": name, "status": "pass"})
		}
		commands = append(commands, object{"definition_sha256": mustHashFixture(t, definition), "exit": int64(0), "tests": tests, "stdout_sha256": mustHashFixture(t, "fixture stdout"), "stderr_sha256": mustHashFixture(t, "")})
	}
	delete(payload, "assessment")
	payload["commands"] = commands
	verification := captureObservedPromptFixture(t, h.root, "PLAN-EXAMPLE", "T-001", "verification", "verification_runner", "passed", "Synthetic completion regression verifier.", payload)
	d := h.doc("PLAN-EXAMPLE")
	_, err := h.request("task-review", object{"artifact_id": d.ID(), "operation_id": h.next(), "expected": object{"revision": d.Revision(), "model_sha256": d.Hash()}, "task": "T-001", "verification_receipt": verification, "review_receipt": review, "completion_sha256": mustHashFixture(t, "explicit completed evidence")})
	if fault.Code(err) != "COMPLETION_REQUIRED" {
		t.Fatalf("explicit completion review must reject definition-only receipt with COMPLETION_REQUIRED; got %v", err)
	}
}

func TestCompletionReviewNativeCapturePublicationAndScope(t *testing.T) {
	h, linked := completionHarness(t)
	material := filepath.Join(testutil.Root(t), "matrix.txt")
	if err := os.WriteFile(material, []byte("Task completion evidence matrix\n"), 0600); err != nil {
		t.Fatal(err)
	}
	receipts := []string{}
	for i, id := range []string{"T-001", "T-002"} {
		startNativeV1FixtureTask(t, h, id)
		root := h.root
		if i == 1 {
			root = linked
		}
		verification := completionVerification(t, h, id, root)
		receipts = append(receipts, verification)
		cr := completionContext(t, h, id, "spec_review", []string{verification}, []string{material})
		context := h.derived(model.S(cr["context_ref"]))
		packet := model.M(context["completion"])
		rows := model.A(packet["verifications"])
		materials := model.A(packet["materials"])
		if len(rows) != 1 || model.S(model.M(rows[0])["receipt_ref"]) != verification || len(materials) != 1 || model.S(model.M(materials[0])["source_path"]) != material || model.S(model.M(materials[0])["content_base64"]) == "" {
			t.Fatalf("selected evidence omitted: %v", packet)
		}
		if model.S(model.M(model.A(model.M(rows[0])["workspace_after"])[0])["root"]) != root {
			t.Fatal("mapped verifier workspace omitted")
		}
		source, _ := nativeV1ReviewSourceForContext(t, h, id, "spec_review", cr)
		review := h.run("capture-observation", source)["receipt"]
		h.mutate("task-review", "PLAN-EXAMPLE", object{"task": id, "verification_receipt": verification, "review_receipt": review, "completion_sha256": context["completion_sha256"]})
		f, err := store.Open(h.root)
		if err != nil {
			t.Fatal(err)
		}
		plan, spec := h.doc("PLAN-EXAMPLE"), h.doc("SPEC-EXAMPLE")
		err = evidence.TaskFresh(f, plan, spec, plan.Symbols.ByID[id].Value, model.S(context["input_sha256"]))
		f.Close()
		if err != nil {
			t.Fatalf("native task-review state update invalidated completed evidence: %v", err)
		}
		resume := h.run("evidence-context", object{"artifact_id": "PLAN-EXAMPLE", "activity": "spec_review", "record_id": id, "completion_context_ref": cr["context_ref"], "completion_context_sha256": cr["context_sha256"]})
		if resume["context_sha256"] != cr["context_sha256"] {
			t.Fatal("state-only update changed resumed completion context")
		}
	}
	quality := completionContext(t, h, "CP-01", "quality_review", receipts, []string{material})
	qcontext := h.derived(model.S(quality["context_ref"]))
	if len(model.A(model.M(qcontext["completion"])["verifications"])) != 2 {
		t.Fatal("quality omitted a selected task")
	}
	source, _ := nativeV1ReviewSourceForContext(t, h, "CP-01", "quality_review", quality)
	review := h.run("capture-observation", source)["receipt"]
	h.mutate("accept-scope", "PLAN-EXAMPLE", object{"scope": "CP-01", "receipt": review, "completion_sha256": qcontext["completion_sha256"]})
	f, err := store.Open(h.root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	plan, spec := h.doc("PLAN-EXAMPLE"), h.doc("SPEC-EXAMPLE")
	for _, id := range []string{"T-001", "T-002"} {
		if err = evidence.AcceptedFresh(f, plan, spec, id, model.S(qcontext["input_sha256"])); err != nil {
			t.Fatalf("accepted completion is stale after typed publication: %v", err)
		}
	}
}

func TestCompletionReviewRejectsSelectedEvidenceDrift(t *testing.T) {
	for _, mode := range []string{"mapped-before-capture", "material-before-capture", "mapped-before-consume", "material-before-consume", "mapped-after-publish", "material-after-publish"} {
		t.Run(mode, func(t *testing.T) {
			h, linked := completionHarness(t)
			startNativeV1FixtureTask(t, h, "T-001")
			material := filepath.Join(testutil.Root(t), "matrix.txt")
			if err := os.WriteFile(material, []byte("exact selected evidence"), 0600); err != nil {
				t.Fatal(err)
			}
			verification := completionVerification(t, h, "T-001", linked)
			cr := completionContext(t, h, "T-001", "spec_review", []string{verification}, []string{material})
			context := h.derived(model.S(cr["context_ref"]))
			source, _ := nativeV1ReviewSourceForContext(t, h, "T-001", "spec_review", cr)
			mutate := func() {
				path := material
				if mode[:6] == "mapped" {
					path = filepath.Join(linked, "src", "stage1.go")
				}
				if err := os.WriteFile(path, []byte("changed after selected evidence"), 0600); err != nil {
					t.Fatal(err)
				}
			}
			if mode == "mapped-before-capture" || mode == "material-before-capture" {
				mutate()
				if _, err := h.request("capture-observation", source); err == nil {
					t.Fatal("capture accepted drift in selected completed evidence")
				}
				return
			}
			review := h.run("capture-observation", source)["receipt"]
			if mode == "mapped-before-consume" || mode == "material-before-consume" {
				mutate()
				d := h.doc("PLAN-EXAMPLE")
				_, err := h.request("task-review", object{"artifact_id": d.ID(), "operation_id": h.next(), "expected": object{"revision": d.Revision(), "model_sha256": d.Hash()}, "task": "T-001", "verification_receipt": verification, "review_receipt": review, "completion_sha256": context["completion_sha256"]})
				if err == nil {
					t.Fatal("task-review consumed stale selected evidence")
				}
				return
			}
			h.mutate("task-review", "PLAN-EXAMPLE", object{"task": "T-001", "verification_receipt": verification, "review_receipt": review, "completion_sha256": context["completion_sha256"]})
			mutate()
			f, err := store.Open(h.root)
			if err != nil {
				t.Fatal(err)
			}
			defer f.Close()
			plan, spec := h.doc("PLAN-EXAMPLE"), h.doc("SPEC-EXAMPLE")
			if err = evidence.TaskFresh(f, plan, spec, plan.Symbols.ByID["T-001"].Value, model.S(context["input_sha256"])); err == nil {
				t.Fatal("task freshness accepted drift in completed evidence")
			}
		})
	}
}

func TestCompletionReviewSelectionAndDecisionAreExact(t *testing.T) {
	h, linked := completionHarness(t)
	startNativeV1FixtureTask(t, h, "T-001")
	verification := completionVerification(t, h, "T-001", linked)
	foreign := completionVerification(t, h, "T-002", linked)
	for _, refs := range [][]string{{verification, verification}, {foreign}, {verification, foreign}, {".codearbiter/.artifacts/receipts/" + mustHashFixture(t, "unpublished") + ".json"}} {
		if _, err := h.request("evidence-context", object{"artifact_id": "PLAN-EXAMPLE", "activity": "spec_review", "record_id": "T-001", "completion_selection": object{"verification_receipts": model.List(refs...), "supporting_files": []any{}}}); err == nil {
			t.Fatalf("ambiguous, foreign, or unpublished selection accepted: %v", refs)
		}
	}
	cr := completionContext(t, h, "T-001", "spec_review", []string{verification}, nil)
	source, _ := nativeV1ReviewSourceForContext(t, h, "T-001", "spec_review", cr)
	for _, mode := range []string{"missing-obligation", "duplicate-obligation", "missing-fact", "unselected-reference", "duplicate-reference", "whitespace-assessment", "definition-only"} {
		t.Run(mode, func(t *testing.T) {
			event := h.derived(model.S(source["source_ref"]))
			observed := h.derived(model.S(event["observation_ref"]))
			producer := model.M(observed["producer_result"])
			decision := model.M(producer["decision"])
			payload := model.M(event["payload"])
			rows := model.A(decision["completion_assessment"])
			switch mode {
			case "missing-obligation":
				rows = rows[1:]
			case "duplicate-obligation":
				rows = append(rows, rows[0])
			case "missing-fact":
				model.M(rows[0])["status"] = "missing"
			case "unselected-reference":
				model.M(rows[0])["evidence_refs"] = model.List("coordinator-summary:trust-me")
			case "duplicate-reference":
				refs := model.Strings(model.M(rows[0])["evidence_refs"])
				model.M(rows[0])["evidence_refs"] = model.List(refs[0], refs[0])
			case "whitespace-assessment":
				model.M(rows[0])["assessment"] = " \r\n\t"
			case "definition-only":
				delete(decision, "completion_sha256")
				delete(payload, "completion_sha256")
			}
			decision["completion_assessment"], payload["completion_assessment"] = rows, rows
			observed["producer_result_sha256"] = mustHashFixture(t, producer)
			observed["payload_sha256"] = mustHashFixture(t, payload)
			event["observation_ref"], event["observation_sha256"] = h.forge("observations", observed), mustHashFixture(t, observed)
			_, err := h.request("capture-observation", object{"source_ref": h.forge("authority-sources", event), "source_sha256": mustHashFixture(t, event)})
			if fault.Code(err) != "OBSERVATION_UNVERIFIED" {
				t.Fatalf("incomplete or unbound decision was not rejected at observation boundary: %v", err)
			}
		})
	}
	review := h.run("capture-observation", source)["receipt"]
	receipt := h.derived(verification)
	event := h.derived(model.S(receipt["authority_source_ref"]))
	event["source_text"] = "Second distinct synthetic run, same definitions and outcomes."
	other := h.run("capture-observation", object{"source_ref": h.forge("authority-sources", event), "source_sha256": mustHashFixture(t, event)})["receipt"]
	d := h.doc("PLAN-EXAMPLE")
	_, err := h.request("task-review", object{"artifact_id": d.ID(), "operation_id": h.next(), "expected": object{"revision": d.Revision(), "model_sha256": d.Hash()}, "task": "T-001", "verification_receipt": other, "review_receipt": review, "completion_sha256": cr["completion_sha256"]})
	if fault.Code(err) != "COMPLETION_REQUIRED" {
		t.Fatalf("task-review substituted an unselected verifier run: %v", err)
	}
}

func TestCompletionReviewCanSupersedeStaleCompletedRun(t *testing.T) {
	h, linked := completionHarness(t)
	startNativeV1FixtureTask(t, h, "T-001")
	first := completionVerification(t, h, "T-001", linked)
	cr := completionContext(t, h, "T-001", "spec_review", []string{first}, nil)
	source, _ := nativeV1ReviewSourceForContext(t, h, "T-001", "spec_review", cr)
	review := h.run("capture-observation", source)["receipt"]
	h.mutate("task-review", "PLAN-EXAMPLE", object{"task": "T-001", "verification_receipt": first, "review_receipt": review, "completion_sha256": cr["completion_sha256"]})
	writeFixture(t, linked, "src/stage1.go", []byte("package repaired\n"))
	second := completionVerification(t, h, "T-001", linked)
	if second == first {
		t.Fatal("fresh verifier observation did not identify the changed worktree")
	}
	cr = completionContext(t, h, "T-001", "spec_review", []string{second}, nil)
	source, _ = nativeV1ReviewSourceForContext(t, h, "T-001", "spec_review", cr)
	review = h.run("capture-observation", source)["receipt"]
	h.mutate("task-review", "PLAN-EXAMPLE", object{"task": "T-001", "verification_receipt": second, "review_receipt": review, "completion_sha256": cr["completion_sha256"]})
	f, err := store.Open(h.root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	plan, spec := h.doc("PLAN-EXAMPLE"), h.doc("SPEC-EXAMPLE")
	context := h.derived(model.S(cr["context_ref"]))
	if err = evidence.TaskFresh(f, plan, spec, plan.Symbols.ByID["T-001"].Value, model.S(context["input_sha256"])); err != nil {
		t.Fatalf("fresh selected completion did not supersede stale run: %v", err)
	}
}

func TestCompletionReviewReplayRetainsExplicitSelectedReceipt(t *testing.T) {
	h, linked := completionHarness(t)
	startNativeV1FixtureTask(t, h, "T-001")
	verification := completionVerification(t, h, "T-001", linked)
	first := completionContext(t, h, "T-001", "spec_review", []string{verification}, nil)
	source, _ := nativeV1ReviewSourceForContext(t, h, "T-001", "spec_review", first)
	firstReview := h.run("capture-observation", source)["receipt"]
	h.mutate("task-review", "PLAN-EXAMPLE", object{"task": "T-001", "verification_receipt": verification, "review_receipt": firstReview, "completion_sha256": first["completion_sha256"]})
	material := filepath.Join(testutil.Root(t), "matrix.txt")
	if err := os.WriteFile(material, []byte("second review evidence"), 0600); err != nil {
		t.Fatal(err)
	}
	second := completionContext(t, h, "T-001", "spec_review", []string{verification}, []string{material})
	source, _ = nativeV1ReviewSourceForContext(t, h, "T-001", "spec_review", second)
	secondReview := h.run("capture-observation", source)["receipt"]
	h.mutate("task-review", "PLAN-EXAMPLE", object{"task": "T-001", "verification_receipt": verification, "review_receipt": secondReview, "completion_sha256": second["completion_sha256"]})
	h.mutate("task-review", "PLAN-EXAMPLE", object{"task": "T-001", "verification_receipt": verification, "review_receipt": firstReview, "completion_sha256": first["completion_sha256"]})
	f, err := store.Open(h.root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	selected, err := evidence.LatestTaskCompletion(f, h.doc("PLAN-EXAMPLE"), "T-001")
	if err != nil || selected == nil || selected.Path != firstReview {
		t.Fatalf("explicit replay selected %v, %v; wanted retained first receipt %v", selected, err, firstReview)
	}
}

func TestCompletionReviewMaterialCannotBypassCanonicalArtifactAPI(t *testing.T) {
	h, linked := completionHarness(t)
	startNativeV1FixtureTask(t, h, "T-001")
	verification := completionVerification(t, h, "T-001", linked)
	_, err := h.request("evidence-context", object{"artifact_id": "PLAN-EXAMPLE", "activity": "spec_review", "record_id": "T-001", "completion_selection": object{"verification_receipts": model.List(verification), "supporting_files": model.List(filepath.Join(h.root, ".codearbiter", "plans", "example.html"))}})
	if fault.Code(err) != "UNSAFE_COMPLETION_MATERIAL" {
		t.Fatalf("canonical artifact was imported as ordinary supporting bytes: %v", err)
	}
}

func TestCompletionReviewRejectsWindowsMaterialAlias(t *testing.T) {
	if runtime.GOOS != "windows" {
		t.Skip("Windows case-insensitive locator contract")
	}
	h, linked := completionHarness(t)
	startNativeV1FixtureTask(t, h, "T-001")
	verification := completionVerification(t, h, "T-001", linked)
	dir := testutil.Root(t)
	material := filepath.Join(dir, "matrix.txt")
	if err := os.WriteFile(material, []byte("one physical selected file"), 0600); err != nil {
		t.Fatal(err)
	}
	_, err := h.request("evidence-context", object{"artifact_id": "PLAN-EXAMPLE", "activity": "spec_review", "record_id": "T-001", "completion_selection": object{"verification_receipts": model.List(verification), "supporting_files": model.List(material, filepath.Join(dir, "MATRIX.TXT"))}})
	if fault.Code(err) != "INVALID_COMPLETION_SELECTION" {
		t.Fatalf("same material locator was admitted twice through Windows case aliases: %v", err)
	}
}

func TestCompletionReviewQualityPreservesExactTaskEvidence(t *testing.T) {
	h, linked := completionHarness(t)
	material := filepath.Join(testutil.Root(t), "matrix.txt")
	if err := os.WriteFile(material, []byte("selected task evidence"), 0600); err != nil {
		t.Fatal(err)
	}
	receipts := []string{}
	for _, id := range []string{"T-001", "T-002"} {
		startNativeV1FixtureTask(t, h, id)
		verification := completionVerification(t, h, id, linked)
		receipts = append(receipts, verification)
		cr := completionContext(t, h, id, "spec_review", []string{verification}, []string{material})
		source, _ := nativeV1ReviewSourceForContext(t, h, id, "spec_review", cr)
		review := h.run("capture-observation", source)["receipt"]
		h.mutate("task-review", "PLAN-EXAMPLE", object{"task": id, "verification_receipt": verification, "review_receipt": review, "completion_sha256": cr["completion_sha256"]})
	}
	for _, selection := range []object{
		{"verification_receipts": model.List(receipts[0]), "supporting_files": model.List(material)},
		{"verification_receipts": model.List(receipts...), "supporting_files": []any{}},
	} {
		if _, err := h.request("evidence-context", object{"artifact_id": "PLAN-EXAMPLE", "activity": "quality_review", "record_id": "CP-01", "completion_selection": selection}); err == nil {
			t.Fatal("quality arm omitted selected task or supporting material")
		}
	}
	firstReceipt := h.derived(receipts[0])
	alternateEvent := h.derived(model.S(firstReceipt["authority_source_ref"]))
	alternateEvent["source_text"] = "A distinct synthetic verification run with equal results."
	alternate := model.S(h.run("capture-observation", object{"source_ref": h.forge("authority-sources", alternateEvent), "source_sha256": mustHashFixture(t, alternateEvent)})["receipt"])
	if _, err := h.request("evidence-context", object{"artifact_id": "PLAN-EXAMPLE", "activity": "quality_review", "record_id": "CP-01", "completion_selection": object{"verification_receipts": model.List(alternate, receipts[1]), "supporting_files": model.List(material)}}); fault.Code(err) != "COMPLETION_REQUIRED" {
		t.Fatalf("quality arm substituted a successful but unselected run: %v", err)
	}
	ordinarySource, _ := nativeV1ReviewSource(t, h, "CP-01", "quality_review")
	ordinary := h.run("capture-observation", ordinarySource)["receipt"]
	d := h.doc("PLAN-EXAMPLE")
	if _, err := h.request("accept-scope", object{"artifact_id": d.ID(), "operation_id": h.next(), "expected": object{"revision": d.Revision(), "model_sha256": d.Hash()}, "scope": "CP-01", "receipt": ordinary}); fault.Code(err) != "COMPLETION_REQUIRED" {
		t.Fatalf("ordinary quality receipt downgraded completed tasks: %v", err)
	}
	quality := completionContext(t, h, "CP-01", "quality_review", receipts, []string{material})
	context := h.derived(model.S(quality["context_ref"]))
	// Synthetic test-only substitution: valid closed bytes still must not omit
	// the supporting evidence of the completed tasks they purport to review.
	model.M(context["completion"])["materials"] = []any{}
	context["completion_sha256"] = mustHashFixture(t, context["completion"])
	forged := object{"context_ref": h.forge("evidence-contexts", context), "context_sha256": mustHashFixture(t, context)}
	source, _ := nativeV1ReviewSourceForContext(t, h, "CP-01", "quality_review", forged)
	if _, err := h.request("capture-observation", source); fault.Code(err) != "COMPLETION_REQUIRED" {
		t.Fatalf("quality capture accepted a closed context omitting task supporting evidence: %v", err)
	}
}

func TestCompletionReviewMaterialBoundsAndClosedSchema(t *testing.T) {
	h, linked := completionHarness(t)
	startNativeV1FixtureTask(t, h, "T-001")
	verification := completionVerification(t, h, "T-001", linked)
	dir := testutil.Root(t)
	files := []string{}
	for i := 0; i < 17; i++ {
		path := filepath.Join(dir, fmt.Sprintf("part-%02d.txt", i))
		if err := os.WriteFile(path, nil, 0600); err != nil {
			t.Fatal(err)
		}
		files = append(files, path)
	}
	accepted := completionContext(t, h, "T-001", "spec_review", []string{verification}, files[:16])
	if _, err := h.request("evidence-context", object{"artifact_id": "PLAN-EXAMPLE", "activity": "spec_review", "record_id": "T-001", "completion_selection": object{"verification_receipts": model.List(verification), "supporting_files": model.List(files...)}}); err == nil {
		t.Fatal("17 selected files bypassed the native packet limit")
	}
	for _, field := range []string{"packet", "verification", "material"} {
		context := h.derived(model.S(accepted["context_ref"]))
		packet := model.M(context["completion"])
		target := packet
		if field == "verification" {
			target = model.M(model.A(packet["verifications"])[0])
		}
		if field == "material" {
			target = model.M(model.A(packet["materials"])[0])
		}
		target["unvalidated_authority"] = true
		if len(schema.ValidateWith(observation.CompletionSchema(), packet)) == 0 {
			t.Fatalf("unknown %s descendant field became a generated-output exclusion", field)
		}
	}
	for _, path := range files[:5] {
		if err := os.WriteFile(path, bytes.Repeat([]byte("x"), 64<<10), 0600); err != nil {
			t.Fatal(err)
		}
	}
	completionContext(t, h, "T-001", "spec_review", []string{verification}, files[:4])
	if _, err := h.request("evidence-context", object{"artifact_id": "PLAN-EXAMPLE", "activity": "spec_review", "record_id": "T-001", "completion_selection": object{"verification_receipts": model.List(verification), "supporting_files": model.List(files[:5]...)}}); fault.Code(err) != "MAX_BYTES" {
		t.Fatalf("more than 256KiB material bytes bypassed aggregate limit: %v", err)
	}
}

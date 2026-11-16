//go:build linux || darwin || windows

package operations

import (
	"reflect"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

// Actual in-process mutation/readiness owners only. These fixtures create no
// approval receipt, run no declared verification command, and call no provider.
func n07ChangedPaths(before, after map[string]string) map[string][2]string {
	changed := map[string][2]string{}
	for path, prior := range before {
		current, present := after[path]
		if !present {
			changed[path] = [2]string{canonical.BytesHash([]byte(prior)), "<absent>"}
		} else if current != prior {
			changed[path] = [2]string{canonical.BytesHash([]byte(prior)), canonical.BytesHash([]byte(current))}
		}
	}
	for path, current := range after {
		if _, present := before[path]; !present {
			changed[path] = [2]string{"<absent>", canonical.BytesHash([]byte(current))}
		}
	}
	return changed
}

func n07ReadinessIsReadOnly(t *testing.T, h *harness, artifact string, valid bool, code, symbol, field string) {
	t.Helper()
	before := readModeTree(t, h.root)
	raw, err := h.request("validate", object{"artifact_id": artifact, "gate": "ready"})
	after := readModeTree(t, h.root)
	if err != nil || !reflect.DeepEqual(before, after) {
		t.Fatalf("readiness failed or wrote state: %v; changed=%v", err, n07ChangedPaths(before, after))
	}
	first := model.M(raw)
	diagnostics, ok := first["diagnostics"].([]fault.Error)
	if !ok || first["valid"] != valid {
		t.Fatalf("unexpected readiness result: %#v", raw)
	}
	if code != "" {
		found := false
		for _, diagnostic := range diagnostics {
			if diagnostic.Code == code && (symbol == "" || diagnostic.Symbol == symbol) && (field == "" || diagnostic.Field == field) {
				found = true
			}
		}
		if !found {
			t.Fatalf("missing exact readiness diagnostic %s/%s/%s: %+v", code, symbol, field, diagnostics)
		}
	} else if len(diagnostics) != 0 {
		t.Fatalf("healthy control had diagnostics: %+v", diagnostics)
	}
	for repeat := 0; repeat < 2; repeat++ {
		next, repeatErr := h.request("validate", object{"artifact_id": artifact, "gate": "ready"})
		after = readModeTree(t, h.root)
		if repeatErr != nil || !reflect.DeepEqual(before, after) {
			t.Fatalf("repeated readiness wrote state: %v; changed=%v", repeatErr, n07ChangedPaths(before, after))
		}
		result := model.M(next)
		if result["valid"] != first["valid"] || !reflect.DeepEqual(result["diagnostics"], first["diagnostics"]) {
			t.Fatalf("readiness diagnostics depend on iteration/history: first=%+v repeated=%+v", first["diagnostics"], result["diagnostics"])
		}
	}
	governance := model.M(h.doc(artifact).Data["governance"])
	if governance["state"] != "draft" || len(model.A(governance["approvals"])) != 0 {
		t.Fatal("readiness was treated as approval")
	}
}

func n07MutationRefusesWithoutWrites(t *testing.T, h *harness, artifact string, fields object, want string) {
	t.Helper()
	document := h.doc(artifact)
	request := object{"artifact_id": artifact, "operation_id": h.next(), "expected": object{"revision": document.Revision(), "model_sha256": document.Hash()}, "changes": fields["changes"]}
	before := readModeTree(t, h.root)
	_, err := h.request("apply", request)
	after := readModeTree(t, h.root)
	if fault.Code(err) != want || !reflect.DeepEqual(before, after) {
		t.Fatalf("mutation must refuse %s without writes: %v; changed=%v", want, err, n07ChangedPaths(before, after))
	}
}

func TestN07DecisionResolutionChangesReadinessWithoutApproving(t *testing.T) {
	for _, kind := range []string{"resolved", "blank-resolution", "dangling-reference"} {
		t.Run(kind, func(t *testing.T) {
			h := newHarness(t)
			h.createPair()
			h.mut("apply", "SPEC-EXAMPLE", object{"changes": []any{object{"op": "record.add", "collection": "open_decisions", "record": object{
				"id": "CONFIRM-01", "question": "Which supported precedence is intended?", "blocking": true,
				"affects": model.List("AC-001"), "source_ref": "Owned characterization requirement", "owner": "fixture user",
				"status": "open", "resolution": nil,
			}}}})
			n07ReadinessIsReadOnly(t, h, "SPEC-EXAMPLE", false, "OPEN_BLOCKER", "CONFIRM-01", "status")
			previous := h.doc("SPEC-EXAMPLE")
			fields := object{"status": "resolved", "resolution": "Use the declared environment-first behavior."}
			if kind == "blank-resolution" {
				fields["resolution"] = " \t "
			}
			if kind == "dangling-reference" {
				fields["affects"] = model.List("AC-MISSING")
			}
			change := object{"changes": []any{object{"op": "record.update", "symbol": "CONFIRM-01", "fields": fields}}}
			if kind != "resolved" {
				want := "INVALID_DECISION"
				if kind == "dangling-reference" {
					want = "DANGLING_REFERENCE"
				}
				n07MutationRefusesWithoutWrites(t, h, "SPEC-EXAMPLE", change, want)
				n07ReadinessIsReadOnly(t, h, "SPEC-EXAMPLE", false, "OPEN_BLOCKER", "CONFIRM-01", "status")
				return
			}
			h.mut("apply", "SPEC-EXAMPLE", change)
			updated := h.doc("SPEC-EXAMPLE")
			decision := updated.Symbols.ByID["CONFIRM-01"].Value
			if updated.Revision() != previous.Revision()+1 || decision["status"] != "resolved" || decision["resolution"] != fields["resolution"] || updated.NormHash() == previous.NormHash() {
				t.Fatal("actual resolution did not update the normative record exactly once")
			}
			n07ReadinessIsReadOnly(t, h, "SPEC-EXAMPLE", true, "", "", "")
		})
	}
}

func TestN07ReadyDiagnosticsAreCompleteDeterministicAndNonAuthorizing(t *testing.T) {
	for _, kind := range []string{"ready-positive", "missing-statement", "uncovered-scope", "uncovered-criterion", "uncovered-input", "invalid-partition"} {
		t.Run(kind, func(t *testing.T) {
			h := newHarness(t)
			h.createPair()
			artifact, code, symbol, field := "PLAN-EXAMPLE", "", "", ""
			if kind == "missing-statement" || kind == "uncovered-scope" {
				artifact = "SPEC-EXAMPLE"
			}
			n07ReadinessIsReadOnly(t, h, artifact, true, "", "", "")
			changes := []any{}
			switch kind {
			case "ready-positive":
				return
			case "missing-statement":
				changes = []any{object{"op": "record.update", "symbol": "AC-001", "fields": object{"statement": ""}}}
				code, symbol, field = "NOT_READY", "AC-001", "statement"
			case "uncovered-scope":
				changes = []any{object{"op": "record.add", "collection": "scope", "record": object{"id": "SCOPE-UNMAPPED", "statement": "A distinct unclaimed caller outcome."}}}
				code, symbol = "UNCOVERED_SCOPE", "SCOPE-UNMAPPED"
			case "uncovered-criterion":
				for _, task := range []string{"T-001", "T-002", "T-003"} {
					changes = append(changes, object{"op": "record.update", "symbol": task, "fields": object{"criterion_refs": []any{}}})
				}
				code, symbol = "UNCOVERED_CRITERION", "AC-001"
			case "uncovered-input":
				changes = []any{object{"op": "header.update", "fields": object{"verification_inputs": object{"roots": model.List("other-source"), "exclude_directories": []any{}}}}}
				code, symbol, field = "UNCOVERED_INPUT", "T-001", "verification_inputs"
			case "invalid-partition":
				// This candidate is rejected at the actual mutation's structural
				// gate. Never handwrite invalid canonical bytes just to make
				// validate read a state the writer cannot admit.
				changes = []any{object{"op": "record.update", "symbol": "CP-01", "fields": object{"tasks": model.List("T-001")}}}
				n07MutationRefusesWithoutWrites(t, h, artifact, object{"changes": changes}, "INVALID_PARTITION")
				n07ReadinessIsReadOnly(t, h, artifact, true, "", "", "")
				return
			}
			h.mut("apply", artifact, object{"changes": changes})
			n07ReadinessIsReadOnly(t, h, artifact, false, code, symbol, field)
		})
	}
}

func n07PairWithUnmappedCriterion(t *testing.T, obligation string) *harness {
	t.Helper()
	h := newHarness(t)
	spec := testutil.Spec()
	normative := model.M(spec["normative"])
	extra := testutil.Criterion("AC-002")
	extra["obligation"] = obligation
	normative["criteria"] = append(model.A(normative["criteria"]), extra)
	h.run("create", object{"operation_id": h.next(), "kind": "spec", "artifact_id": "SPEC-EXAMPLE", "slug": "example", "title": normative["title"], "summary": normative["summary"], "normative": normative})
	plan := testutil.Plan(h.doc("SPEC-EXAMPLE"))
	pn := model.M(plan["normative"])
	h.run("create", object{"operation_id": h.next(), "kind": "plan", "artifact_id": "PLAN-EXAMPLE", "slug": "example", "title": pn["title"], "summary": pn["summary"], "spec_id": "SPEC-EXAMPLE", "normative": pn})
	return h
}

func TestN07ActiveNotApplicableAndMandatoryDispositionRefuse(t *testing.T) {
	for _, kind := range []string{"active-not-applicable", "mandatory-disposition", "optional-disposition"} {
		t.Run(kind, func(t *testing.T) {
			if kind == "active-not-applicable" {
				h := newHarness(t)
				h.createPair()
				n07ReadinessIsReadOnly(t, h, "SPEC-EXAMPLE", true, "", "", "")
				h.mut("apply", "SPEC-EXAMPLE", object{"changes": []any{object{"op": "record.update", "symbol": "AC-001", "fields": object{"applicability": object{"mode": "not_applicable", "rationale": "A caller cannot quietly discard the active outcome."}}}}})
				n07ReadinessIsReadOnly(t, h, "SPEC-EXAMPLE", false, "NOT_READY", "AC-001", "applicability")
				if h.doc("SPEC-EXAMPLE").Symbols.ByID["AC-001"].Retired {
					t.Fatal("readiness silently retired the active criterion")
				}
				return
			}
			obligation := "must"
			if kind == "optional-disposition" {
				obligation = "should"
			}
			h := n07PairWithUnmappedCriterion(t, obligation)
			n07ReadinessIsReadOnly(t, h, "PLAN-EXAMPLE", false, "UNCOVERED_CRITERION", "AC-002", "")
			h.mut("apply", "PLAN-EXAMPLE", object{"changes": []any{object{"op": "record.add", "collection": "criterion_dispositions", "record": object{
				"criterion_ref": "SPEC-EXAMPLE#AC-002", "disposition": "not_applicable", "rationale": "Explicitly recorded scope disposition; not an approval.",
			}}}})
			// Draft storage permits the typed disposition; readiness is the
			// actual guard that refuses disposing a mandatory outcome.
			if obligation == "must" {
				n07ReadinessIsReadOnly(t, h, "PLAN-EXAMPLE", false, "UNCOVERED_CRITERION", "AC-002", "")
			} else {
				n07ReadinessIsReadOnly(t, h, "PLAN-EXAMPLE", true, "", "", "")
			}
			dispositions := model.A(h.doc("PLAN-EXAMPLE").Norm()["criterion_dispositions"])
			if len(dispositions) != 1 || model.M(dispositions[0])["criterion_ref"] != "SPEC-EXAMPLE#AC-002" {
				t.Fatal("explicit disposition was rewritten or lost")
			}
		})
	}
}

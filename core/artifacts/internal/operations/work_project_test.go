package operations

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

func TestWorkProjectEffectPreservesIssueAndScopesRetry(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, r object) object {
		t.Helper()
		r["protocol"] = Protocol
		v, err := Run(root, op, r)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return model.M(v)
	}
	expected := func(v object) object { return object{"revision": v["revision"], "model_sha256": v["model_sha256"]} }
	work := call("work-create", object{"operation_id": "project-work-create-001", "title": "One issue", "intent": "Keep binding", "work_type": "fix"})
	id := model.S(work["work_id"])
	issueConfig := call("work-provider-configure", object{"operation_id": "project-issue-config-001", "repository": "arbiterForge/disposable", "credential_ref": "GH_TOKEN", "effect_timing": "immediate"})
	projectConfig := call("work-project-configure", object{"operation_id": "project-config-001", "project_node_id": "PVT_fixture12345678"})
	work = call("work-effect-adopt", object{"operation_id": "project-issue-adopt-001", "work_id": id,
		"binding_generation": issueConfig["binding_generation"], "expected": expected(work),
		"remote_issue_number": int64(7), "remote_issue_url": "https://github.com/arbiterForge/disposable/issues/7", "remote_state": "open"})
	issue := model.M(work["provider_effect"])
	staged := call("work-project-stage", object{"operation_id": "project-stage-001", "work_id": id,
		"binding_generation": projectConfig["binding_generation"], "expected": expected(work)})
	claimed := call("work-project-claim", object{"operation_id": "project-claim-001", "work_id": id,
		"binding_generation": projectConfig["binding_generation"], "attempt_id": "project-attempt-001",
		"expected": expected(staged)})
	if model.S(model.M(claimed["project_effect"])["status"]) != "outcome_unknown" {
		t.Fatalf("project pre-send claim lost uncertainty: %v", claimed)
	}
	if model.S(model.M(claimed["provider_effect"])["remote_issue_url"]) != model.S(issue["remote_issue_url"]) {
		t.Fatalf("project claim changed issue binding: %v", claimed)
	}
	view := call("work-view", object{"work_id": id})
	if !strings.Contains(model.S(view["html"]), "Project outcome unknown") ||
		!strings.Contains(model.S(view["html"]), "https://github.com/arbiterForge/disposable/issues/7") {
		t.Fatal("work view concealed the partial Project outcome or issue binding")
	}
	fresh := testutil.Root(t)
	for _, rel := range []string{projectPath, workPath(id), workProviderPath, workProjectPath} {
		b, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(rel)))
		if err != nil {
			t.Fatal(err)
		}
		p := filepath.Join(fresh, filepath.FromSlash(rel))
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, b, 0o644); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := Run(fresh, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	portable, err := Run(fresh, "work-get", object{"protocol": Protocol, "work_id": id})
	if err != nil || model.S(model.M(model.M(portable)["project_effect"])["status"]) != "outcome_unknown" {
		t.Fatalf("Project uncertainty was lost without the local journal: %v, %v", portable, err)
	}
	_, err = Run(root, "work-project-claim", object{"protocol": Protocol, "operation_id": "project-claim-002",
		"work_id": id, "binding_generation": projectConfig["binding_generation"], "attempt_id": "project-attempt-002",
		"expected": expected(claimed)})
	if fault.Code(err) != "EFFECT_UNKNOWN" {
		t.Fatalf("uncertain project send retried: %v", err)
	}
	recorded := call("work-project-record", object{"operation_id": "project-record-001", "work_id": id,
		"binding_generation": projectConfig["binding_generation"], "attempt_id": "project-attempt-001",
		"remote_item_id": "PVTI_fixture12345678", "expected": expected(claimed)})
	if model.S(model.M(recorded["project_effect"])["status"]) != "synchronized" ||
		model.S(model.M(recorded["provider_effect"])["remote_issue_url"]) != model.S(issue["remote_issue_url"]) {
		t.Fatalf("project readback did not retain the issue: %v", recorded)
	}
	statusPending := call("work-effect-stage", object{"operation_id": "project-issue-status-stage-001",
		"work_id": id, "binding_generation": issueConfig["binding_generation"],
		"kind": "status_update", "desired_state": "closed", "expected": expected(recorded)})
	field := call("work-project-stage-field", object{"operation_id": "project-field-stage-001",
		"work_id": id, "binding_generation": projectConfig["binding_generation"],
		"field_id": "PVTSSF_fixture12345678", "desired_option_id": "f75ad846",
		"expected_remote_option_id": nil, "expected": expected(statusPending)})
	if model.S(model.M(field["project_effect"])["remote_item_id"]) != "PVTI_fixture12345678" {
		t.Fatalf("field staging erased the Project item binding: %v", field)
	}
	claimedField := call("work-project-claim", object{"operation_id": "project-field-claim-001",
		"work_id": id, "binding_generation": projectConfig["binding_generation"],
		"attempt_id": "project-field-attempt-001", "expected": expected(field)})
	completedField := call("work-project-record", object{"operation_id": "project-field-record-001",
		"work_id": id, "binding_generation": projectConfig["binding_generation"],
		"attempt_id": "project-field-attempt-001", "remote_item_id": "PVTI_fixture12345678",
		"observed_option_id": "f75ad846", "expected": expected(claimedField)})
	if model.S(model.M(completedField["project_effect"])["status"]) != "synchronized" ||
		model.S(model.M(completedField["project_effect"])["observed_option_id"]) != "f75ad846" ||
		model.S(model.M(completedField["provider_effect"])["status"]) != "pending" {
		t.Fatalf("field readback was not recorded: %v", completedField)
	}
	replay := call("work-project-record", object{"operation_id": "project-field-record-001",
		"work_id": id, "binding_generation": projectConfig["binding_generation"],
		"attempt_id": "project-field-attempt-001", "remote_item_id": "PVTI_fixture12345678",
		"observed_option_id": "f75ad846", "expected": expected(claimedField)})
	if replay["revision"] != completedField["revision"] {
		t.Fatal("field result retry did not replay")
	}
	issueUnknown := call("work-effect-claim", object{"operation_id": "project-issue-status-claim-001",
		"work_id": id, "binding_generation": issueConfig["binding_generation"],
		"attempt_id": "project-issue-status-attempt-001", "expected": expected(completedField)})
	if model.S(model.M(issueUnknown["provider_effect"])["status"]) != "outcome_unknown" {
		t.Fatalf("issue status claim was not retained: %v", issueUnknown)
	}
	fieldWhileUnknown := call("work-project-stage-field", object{"operation_id": "project-field-stage-unknown-001",
		"work_id": id, "binding_generation": projectConfig["binding_generation"],
		"field_id": "PVTSSF_fixture12345678", "desired_option_id": "b1234567",
		"expected_remote_option_id": "f75ad846", "expected": expected(issueUnknown)})
	if model.S(model.M(fieldWhileUnknown["project_effect"])["status"]) != "pending" ||
		model.S(model.M(fieldWhileUnknown["provider_effect"])["status"]) != "outcome_unknown" {
		t.Fatalf("field staging changed or blocked an independent issue status effect: %v", fieldWhileUnknown)
	}
}

func TestWorkProjectAcceptsBoundedLegacyGlobalNodeIDs(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, r object) object {
		t.Helper()
		r["protocol"] = Protocol
		v, err := Run(root, op, r)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return model.M(v)
	}
	call("work-create", object{"operation_id": "legacy-node-work-001", "title": "Legacy IDs", "intent": "Keep global node IDs opaque", "work_type": "fix"})
	call("work-provider-configure", object{"operation_id": "legacy-node-issue-001", "repository": "arbiterForge/disposable", "credential_ref": "GH_TOKEN", "effect_timing": "immediate"})
	config := call("work-project-configure", object{"operation_id": "legacy-node-project-001",
		"project_node_id": "UHJvamVjdFYyOjEyMzQ="})
	if model.S(config["project_node_id"]) != "UHJvamVjdFYyOjEyMzQ=" {
		t.Fatal("legacy base64 global project ID was reinterpreted")
	}
}

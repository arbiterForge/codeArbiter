package operations

import (
	"bytes"
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

func TestTrackerCoordinationT01FiniteOptInMap(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, fields object) object {
		t.Helper()
		fields["protocol"] = Protocol
		got, err := Run(root, op, fields)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return got.(map[string]any)
	}
	call("init-store", object{})
	item := call("work-create", object{"operation_id": "tracker-map-work-create-001", "title": "Map fixture", "intent": "Preserve local progress", "work_type": "fix"})
	if got := call("work-transition-map-get", object{}); got["configured"] != false {
		t.Fatalf("absent mapping was enabled: %+v", got)
	}
	provider := call("work-provider-configure", object{"operation_id": "tracker-map-provider-001", "repository": "example/repo", "credential_ref": "GH_TOKEN", "effect_timing": "after_merge"})
	request := object{
		"operation_id": "tracker-map-configure-001", "enabled": true,
		"issue_generation": provider["binding_generation"],
		"actions": object{
			"start":    object{"issue_state": nil, "project_option_id": nil},
			"complete": object{"issue_state": "closed", "project_option_id": nil},
			"reopen":   object{"issue_state": "open", "project_option_id": nil},
		},
	}
	configured := call("work-transition-map-configure", request)
	if configured["configured"] != true || configured["project_id"] != item["project_id"] || configured["binding_generation"] == "" {
		t.Fatalf("mapping identity missing: %+v", configured)
	}
	if got := call("work-transition-map-get", object{}); got["binding_generation"] != configured["binding_generation"] {
		t.Fatalf("saved map changed generation: %+v", got)
	}
	request["operation_id"] = "tracker-map-configure-002"
	if _, err := Run(root, "work-transition-map-configure", object{"protocol": Protocol, "operation_id": request["operation_id"], "enabled": request["enabled"], "issue_generation": request["issue_generation"], "actions": request["actions"]}); fault.Code(err) != "REVISION_CONFLICT" {
		t.Fatalf("stale map write was admitted: %v", err)
	}
	bad := object{"protocol": Protocol, "operation_id": "tracker-map-configure-003", "enabled": true, "issue_generation": provider["binding_generation"], "expected_config_sha256": configured["binding_generation"], "actions": request["actions"], "token": "secret"}
	if _, err := Run(root, "work-transition-map-configure", bad); err == nil {
		t.Fatal("unknown secret-shaped configuration field was admitted")
	}
}

func TestTrackerCoordinationT02OneTransitionStagesBoundIssue(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, fields object) object {
		t.Helper()
		fields["protocol"] = Protocol
		got, err := Run(root, op, fields)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return got.(map[string]any)
	}
	call("init-store", object{})
	work := call("work-create", object{"operation_id": "tracker-transition-work-001", "title": "Bound fixture", "intent": "Complete locally", "work_type": "fix"})
	id := work["work_id"]
	provider := call("work-provider-configure", object{"operation_id": "tracker-transition-provider-001", "repository": "example/repo", "credential_ref": "GH_TOKEN", "effect_timing": "after_merge"})
	bound := call("work-effect-adopt", object{"operation_id": "tracker-transition-adopt-001", "work_id": id,
		"binding_generation": provider["binding_generation"], "expected": object{"revision": work["revision"], "model_sha256": work["model_sha256"]},
		"remote_issue_number": int64(42), "remote_issue_url": "https://github.com/example/repo/issues/42", "remote_state": "open"})
	call("work-transition-map-configure", object{"operation_id": "tracker-transition-map-001", "enabled": true,
		"issue_generation": provider["binding_generation"], "actions": object{
			"start":    object{"issue_state": nil, "project_option_id": nil},
			"complete": object{"issue_state": "closed", "project_option_id": nil},
			"reopen":   object{"issue_state": "open", "project_option_id": nil},
		}})
	transition := object{"protocol": Protocol, "operation_id": "tracker-transition-complete-001", "work_id": id, "action": "complete",
		"expected": object{"revision": bound["revision"], "model_sha256": bound["model_sha256"]}}
	first := call("work-update", transition)
	if first["state"] != "complete" {
		t.Fatalf("local completion was lost: %+v", first)
	}
	effect := model.M(first["provider_effect"])
	coordination := model.M(first["coordination"])
	if model.S(effect["status"]) != "pending" || model.S(effect["desired_state"]) != "closed" ||
		model.S(coordination["action"]) != "complete" || model.S(coordination["transition_id"]) == "" {
		t.Fatalf("completion lacks atomic tracker intent: effect=%+v coordination=%+v", effect, coordination)
	}
	if replay := call("work-update", transition); replay["model_sha256"] != first["model_sha256"] {
		t.Fatalf("exact retry changed saved transition: %+v", replay)
	}
	view := call("work-view", object{"work_id": id})
	if html := model.S(view["html"]); !strings.Contains(html, "Mapped complete transition") ||
		!strings.Contains(html, "Check status is separate from local completion") ||
		!strings.Contains(html, "Remote updates require explicit synchronization") {
		t.Fatalf("derived work view concealed separate progress and tracker states: %s", html)
	}
	portable, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(workPath(model.S(id)))))
	if err != nil {
		t.Fatal(err)
	}
	parsed, err := render.Parse(portable)
	if err != nil {
		t.Fatal(err)
	}
	if parsed.Data["schema_version"] != model.WorkCoordinationVersion {
		t.Fatalf("mapped work did not advance its reader contract: %v", parsed.Data["schema_version"])
	}
	parsed.Data["schema_version"] = model.SchemaVersion
	if _, err := model.Check(parsed.Data); fault.Code(err) != "UNSUPPORTED_VERSION" {
		t.Fatalf("old-version envelope admitted new coordination fields: %v", err)
	}
	claimed := call("work-effect-claim", object{"operation_id": "tracker-transition-claim-001", "work_id": id,
		"binding_generation": provider["binding_generation"], "attempt_id": "tracker-attempt-001",
		"merge_pull_number": int64(12), "merge_commit_sha": "0000000000000000000000000000000000000000",
		"expected": object{"revision": first["revision"], "model_sha256": first["model_sha256"]}})
	reopened := call("work-update", object{"operation_id": "tracker-transition-reopen-001", "work_id": id, "action": "reopen",
		"expected": object{"revision": claimed["revision"], "model_sha256": claimed["model_sha256"]}})
	if reopened["state"] != "active" || model.S(model.M(reopened["provider_effect"])["status"]) != "outcome_unknown" ||
		model.S(model.M(reopened["coordination"])["issue_status"]) != "waiting_reconciliation" {
		t.Fatalf("reopen lost uncertain close or latest desire: %+v", reopened)
	}
	call("work-provider-configure", object{"operation_id": "tracker-transition-provider-changed-001", "repository": "example/repo",
		"credential_ref": "GH_TOKEN", "effect_timing": "immediate", "expected_config_sha256": provider["binding_generation"]})
	selected := call("work-get", object{"work_id": id})
	if model.S(model.M(selected["coordination"])["send_status"]) != "paused" {
		t.Fatalf("changed provider generation did not pause mapped send: %+v", selected)
	}
}

func TestTrackerCoordinationT03CoalescesUnclaimedMappedIssue(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, fields object) object {
		t.Helper()
		fields["protocol"] = Protocol
		got, err := Run(root, op, fields)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return got.(map[string]any)
	}
	call("init-store", object{})
	work := call("work-create", object{"operation_id": "tracker-coalesce-work-001", "title": "Coalesce fixture", "intent": "Return to closed", "work_type": "fix"})
	provider := call("work-provider-configure", object{"operation_id": "tracker-coalesce-provider-001", "repository": "example/repo", "credential_ref": "GH_TOKEN", "effect_timing": "after_merge"})
	bound := call("work-effect-adopt", object{"operation_id": "tracker-coalesce-adopt-001", "work_id": work["work_id"],
		"binding_generation": provider["binding_generation"], "expected": object{"revision": work["revision"], "model_sha256": work["model_sha256"]},
		"remote_issue_number": int64(42), "remote_issue_url": "https://github.com/example/repo/issues/42", "remote_state": "closed"})
	call("work-transition-map-configure", object{"operation_id": "tracker-coalesce-map-001", "enabled": true,
		"issue_generation": provider["binding_generation"], "actions": object{
			"start":    object{"issue_state": "open", "project_option_id": nil},
			"complete": object{"issue_state": "closed", "project_option_id": nil},
			"reopen":   object{"issue_state": "open", "project_option_id": nil},
		}})
	started := call("work-update", object{"operation_id": "tracker-coalesce-start-001", "work_id": work["work_id"], "action": "start",
		"expected": object{"revision": bound["revision"], "model_sha256": bound["model_sha256"]}})
	if model.S(model.M(started["provider_effect"])["status"]) != "pending" {
		t.Fatalf("start did not stage the mapped open: %+v", started)
	}
	completed := call("work-update", object{"operation_id": "tracker-coalesce-complete-001", "work_id": work["work_id"], "action": "complete",
		"expected": object{"revision": started["revision"], "model_sha256": started["model_sha256"]}})
	if model.S(model.M(completed["provider_effect"])["status"]) != "pending" ||
		model.S(model.M(completed["provider_effect"])["desired_state"]) != "closed" ||
		model.S(model.M(completed["coordination"])["issue_status"]) != "pending" {
		t.Fatalf("obsolete unsent open was not coalesced into a readback intent: %+v", completed)
	}
	mappedIntent := model.S(model.M(completed["provider_effect"])["intent_id"])
	manual := call("work-effect-stage", object{"operation_id": "tracker-coalesce-manual-001", "work_id": work["work_id"],
		"binding_generation": provider["binding_generation"], "kind": "status_update", "desired_state": "open",
		"expected": object{"revision": completed["revision"], "model_sha256": completed["model_sha256"]}})
	if model.S(model.M(manual["coordination"])["superseded_issue_intent_id"]) != mappedIntent ||
		model.M(manual["provider_effect"])["source_transition_id"] != nil {
		t.Fatalf("manual issue override lost replaced mapped intent lineage: %+v", manual)
	}
}

func TestTrackerCoordinationT03NullTargetRetiresOnlyUnsentIssue(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, fields object) object {
		t.Helper()
		fields["protocol"] = Protocol
		got, err := Run(root, op, fields)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return got.(map[string]any)
	}
	expected := func(v object) object { return object{"revision": v["revision"], "model_sha256": v["model_sha256"]} }
	call("init-store", object{})
	work := call("work-create", object{"operation_id": "tracker-null-work-001", "title": "Null target", "intent": "Cancel unsent only", "work_type": "fix"})
	provider := call("work-provider-configure", object{"operation_id": "tracker-null-provider-001", "repository": "example/repo", "credential_ref": "GH_TOKEN", "effect_timing": "immediate"})
	bound := call("work-effect-adopt", object{"operation_id": "tracker-null-adopt-001", "work_id": work["work_id"],
		"binding_generation": provider["binding_generation"], "expected": expected(work),
		"remote_issue_number": int64(42), "remote_issue_url": "https://github.com/example/repo/issues/42", "remote_state": "closed"})
	call("work-transition-map-configure", object{"operation_id": "tracker-null-map-001", "enabled": true,
		"issue_generation": provider["binding_generation"], "actions": object{
			"start":    object{"issue_state": "open", "project_option_id": nil},
			"complete": object{"issue_state": nil, "project_option_id": nil},
			"reopen":   object{"issue_state": "open", "project_option_id": nil},
		}})
	started := call("work-update", object{"operation_id": "tracker-null-start-001", "work_id": work["work_id"], "action": "start", "expected": expected(bound)})
	if model.S(model.M(started["provider_effect"])["status"]) != "pending" {
		t.Fatalf("start did not stage issue target: %+v", started)
	}
	completed := call("work-update", object{"operation_id": "tracker-null-complete-001", "work_id": work["work_id"], "action": "complete", "expected": expected(started)})
	effect := model.M(completed["provider_effect"])
	if model.S(effect["status"]) != "synchronized" || effect["source_transition_id"] != nil ||
		model.S(effect["remote_state"]) != "closed" || model.M(completed["coordination"])["desired_issue_state"] != nil {
		t.Fatalf("null target left obsolete unsent issue effect: %+v", completed)
	}
	reopened := call("work-update", object{"operation_id": "tracker-null-reopen-001", "work_id": work["work_id"], "action": "reopen", "expected": expected(completed)})
	if model.S(model.M(reopened["provider_effect"])["status"]) != "pending" ||
		model.S(model.M(reopened["provider_effect"])["desired_state"]) != "open" {
		t.Fatalf("later mapped target could not stage: %+v", reopened)
	}
}

func TestTrackerCoordinationT04ProjectObservationAndMergeFence(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, fields object) object {
		t.Helper()
		fields["protocol"] = Protocol
		got, err := Run(root, op, fields)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return got.(map[string]any)
	}
	expected := func(v object) object { return object{"revision": v["revision"], "model_sha256": v["model_sha256"]} }
	call("init-store", object{})
	work := call("work-create", object{"operation_id": "tracker-project-work-001", "title": "Project fixture", "intent": "Update one field", "work_type": "fix"})
	id := work["work_id"]
	issue := call("work-provider-configure", object{"operation_id": "tracker-project-provider-001", "repository": "example/repo", "credential_ref": "GH_TOKEN", "effect_timing": "after_merge"})
	project := call("work-project-configure", object{"operation_id": "tracker-project-config-001", "project_node_id": "PVT_fixture12345678"})
	work = call("work-effect-adopt", object{"operation_id": "tracker-project-adopt-001", "work_id": id,
		"binding_generation": issue["binding_generation"], "expected": expected(work),
		"remote_issue_number": int64(42), "remote_issue_url": "https://github.com/example/repo/issues/42", "remote_state": "open"})
	staged := call("work-project-stage", object{"operation_id": "tracker-project-stage-001", "work_id": id,
		"binding_generation": project["binding_generation"], "expected": expected(work)})
	claimed := call("work-project-claim", object{"operation_id": "tracker-project-claim-001", "work_id": id,
		"binding_generation": project["binding_generation"], "attempt_id": "tracker-project-attempt-001", "expected": expected(staged)})
	bound := call("work-project-record", object{"operation_id": "tracker-project-record-001", "work_id": id,
		"binding_generation": project["binding_generation"], "attempt_id": "tracker-project-attempt-001",
		"remote_item_id": "PVTI_fixture12345678", "expected": expected(claimed)})
	call("work-transition-map-configure", object{"operation_id": "tracker-project-map-001", "enabled": true,
		"issue_generation": issue["binding_generation"], "project_generation": project["binding_generation"],
		"project_field_id": "PVTSSF_fixture12345678", "actions": object{
			"start":    object{"issue_state": nil, "project_option_id": "optionA"},
			"complete": object{"issue_state": nil, "project_option_id": "optionB"},
			"reopen":   object{"issue_state": nil, "project_option_id": "optionA"},
		}})
	started := call("work-update", object{"operation_id": "tracker-project-start-001", "work_id": id, "action": "start", "expected": expected(bound)})
	if model.S(model.M(started["coordination"])["project_status"]) != "awaiting_observation" ||
		model.S(model.M(started["project_effect"])["kind"]) != "add_item" {
		t.Fatalf("first field observation was invented: %+v", started)
	}
	boardPath := filepath.Join(root, ".codearbiter", "open-tasks.md")
	if err := os.WriteFile(boardPath, []byte("- [ ] Legacy owner\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	resumeRequest := object{"protocol": Protocol, "operation_id": "tracker-project-resume-legacy-refuse-001", "work_id": id,
		"expected": expected(started), "observed_item_id": "PVTI_fixture12345678", "observed_option_id": nil}
	if _, err := Run(root, "work-coordinate-resume", resumeRequest); fault.Code(err) != "LEGACY_CONFLICT" {
		t.Fatalf("mapped resume bypassed restored legacy owner: %v", err)
	}
	if err := os.Remove(boardPath); err != nil {
		t.Fatal(err)
	}
	ready := call("work-coordinate-resume", object{"operation_id": "tracker-project-resume-001", "work_id": id,
		"expected": expected(started), "observed_item_id": "PVTI_fixture12345678", "observed_option_id": nil})
	effect := model.M(ready["project_effect"])
	if model.S(effect["status"]) != "pending" || effect["expected_remote_option_id"] != nil ||
		model.S(effect["source_transition_id"]) != model.S(model.M(ready["coordination"])["transition_id"]) {
		t.Fatalf("explicit null observation did not stage original transition: %+v", ready)
	}
	claim := object{"protocol": Protocol, "operation_id": "tracker-project-claim-mapped-001", "work_id": id,
		"binding_generation": project["binding_generation"], "attempt_id": "tracker-project-attempt-002", "expected": expected(ready)}
	if _, err := Run(root, "work-project-claim", claim); fault.Code(err) != "EFFECT_WAITING_FOR_MERGE" {
		t.Fatalf("mapped Project send bypassed merge timing: %v", err)
	}
	mappedIntent := model.S(effect["intent_id"])
	manual := call("work-project-stage-field", object{"operation_id": "tracker-project-manual-override-001", "work_id": id,
		"binding_generation": project["binding_generation"], "field_id": "PVTSSF_fixture12345678",
		"desired_option_id": "optionB", "expected_remote_option_id": nil, "expected": expected(ready)})
	if model.M(manual["project_effect"])["source_transition_id"] != nil ||
		model.S(model.M(manual["coordination"])["superseded_project_intent_id"]) != mappedIntent ||
		model.S(model.M(manual["coordination"])["project_status"]) != "waiting_manual" {
		t.Fatalf("explicit manual field intent did not supersede unclaimed mapped intent: %+v", manual)
	}
}

func TestTrackerCoordinationT02MalformedOptionalMapKeepsLocalProgress(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, fields object) object {
		t.Helper()
		fields["protocol"] = Protocol
		got, err := Run(root, op, fields)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return got.(map[string]any)
	}
	call("init-store", object{})
	work := call("work-create", object{"operation_id": "tracker-bad-map-work-001", "title": "Bad optional map", "intent": "Keep progress", "work_type": "fix"})
	path := filepath.Join(root, filepath.FromSlash(workTransitionMapPath))
	if err := os.WriteFile(path, []byte(`{"format":"bad","token":"do-not-copy"}`), 0o644); err != nil {
		t.Fatal(err)
	}
	complete := call("work-update", object{"operation_id": "tracker-bad-map-complete-001", "work_id": work["work_id"],
		"action": "complete", "expected": object{"revision": work["revision"], "model_sha256": work["model_sha256"]}})
	coordination := model.M(complete["coordination"])
	if complete["state"] != "complete" || coordination["issue_status"] != "unavailable" ||
		coordination["project_status"] != "unavailable" || complete["provider_effect"] != nil {
		t.Fatalf("optional map corrupted local progress or fabricated an effect: %+v", complete)
	}
	if strings.Contains(model.S(coordination["reason"]), "do-not-copy") {
		t.Fatal("optional map diagnostics leaked its content")
	}
	malformed, err := canonical.Marshal(object{"format": "codearbiter.work-transition-map", "version": int64(1),
		"enabled": true, "project_id": work["project_id"], "issue_generation": strings.Repeat("a", 64),
		"project_generation": int64(1), "project_field_id": nil, "actions": object{
			"start":    object{"issue_state": nil, "project_option_id": nil},
			"complete": object{"issue_state": "closed", "project_option_id": nil},
			"reopen":   object{"issue_state": nil, "project_option_id": nil},
		}})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, malformed, 0o644); err != nil {
		t.Fatal(err)
	}
	invalid := call("work-create", object{"operation_id": "tracker-wrong-type-map-work-001", "title": "Wrong type optional map", "intent": "Keep progress", "work_type": "fix"})
	complete = call("work-update", object{"operation_id": "tracker-wrong-type-map-complete-001", "work_id": invalid["work_id"],
		"action": "complete", "expected": object{"revision": invalid["revision"], "model_sha256": invalid["model_sha256"]}})
	if complete["state"] != "complete" || model.S(model.M(complete["coordination"])["issue_status"]) != "unavailable" {
		t.Fatalf("wrong-type optional map denied local progress: %+v", complete)
	}
	second := call("work-create", object{"operation_id": "tracker-oversized-map-work-001", "title": "Oversized optional map", "intent": "Keep progress", "work_type": "fix"})
	if err := os.WriteFile(path, bytes.Repeat([]byte("x"), workTransitionMapLimit+1), 0o644); err != nil {
		t.Fatal(err)
	}
	complete = call("work-update", object{"operation_id": "tracker-oversized-map-complete-001", "work_id": second["work_id"],
		"action": "complete", "expected": object{"revision": second["revision"], "model_sha256": second["model_sha256"]}})
	if complete["state"] != "complete" || model.S(model.M(complete["coordination"])["issue_status"]) != "unavailable" {
		t.Fatalf("oversized optional map denied local progress: %+v", complete)
	}
	third := call("work-create", object{"operation_id": "tracker-huge-map-work-001", "title": "Huge optional map", "intent": "Keep progress", "work_type": "fix"})
	if err := os.WriteFile(path, bytes.Repeat([]byte("x"), (1<<20)+1), 0o644); err != nil {
		t.Fatal(err)
	}
	complete = call("work-update", object{"operation_id": "tracker-huge-map-complete-001", "work_id": third["work_id"],
		"action": "complete", "expected": object{"revision": third["revision"], "model_sha256": third["model_sha256"]}})
	if complete["state"] != "complete" || model.S(model.M(complete["coordination"])["issue_status"]) != "unavailable" {
		t.Fatalf("large optional map read limit denied local progress: %+v", complete)
	}
}

func TestTrackerCoordinationLegacyPendingCreateWithoutIntentKeepsLocalProgress(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, fields object) object {
		t.Helper()
		fields["protocol"] = Protocol
		got, err := Run(root, op, fields)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return got.(map[string]any)
	}
	call("init-store", object{})
	work := call("work-create", object{"operation_id": "legacy-intent-work-001", "title": "Legacy pending issue",
		"intent": "Complete locally", "work_type": "fix"})
	provider := call("work-provider-configure", object{"operation_id": "legacy-intent-provider-001",
		"repository": "example/repo", "credential_ref": "GH_TOKEN", "effect_timing": "after_merge"})
	staged := call("work-effect-stage", object{"operation_id": "legacy-intent-stage-001", "work_id": work["work_id"],
		"binding_generation": provider["binding_generation"],
		"expected":           object{"revision": work["revision"], "model_sha256": work["model_sha256"]}})
	path := filepath.Join(root, filepath.FromSlash(workPath(model.S(work["work_id"]))))
	body, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	legacy, err := render.Parse(body)
	if err != nil {
		t.Fatal(err)
	}
	delete(model.M(model.M(legacy.Data["execution"])["provider_effect"]), "intent_id")
	legacy, err = render.Prepare(legacy.Data)
	if err != nil {
		t.Fatal(err)
	}
	body, err = render.Render(legacy)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, body, 0o600); err != nil {
		t.Fatal(err)
	}
	call("work-transition-map-configure", object{"operation_id": "legacy-intent-map-001", "enabled": true,
		"issue_generation": provider["binding_generation"], "actions": object{
			"start":    object{"issue_state": nil, "project_option_id": nil},
			"complete": object{"issue_state": "closed", "project_option_id": nil},
			"reopen":   object{"issue_state": "open", "project_option_id": nil},
		}})
	current := call("work-get", object{"work_id": work["work_id"]})
	if current["revision"] != staged["revision"] {
		t.Fatal("historical effect changed its revision")
	}
	completed := call("work-update", object{"operation_id": "legacy-intent-complete-001", "work_id": work["work_id"],
		"action": "complete", "expected": object{"revision": current["revision"], "model_sha256": current["model_sha256"]}})
	coordination := model.M(completed["coordination"])
	if completed["state"] != "complete" || coordination["issue_status"] != "waiting_binding" ||
		coordination["predecessor_issue_intent_id"] != nil {
		t.Fatalf("legacy pending issue blocked local completion or invented intent lineage: %+v", completed)
	}
}

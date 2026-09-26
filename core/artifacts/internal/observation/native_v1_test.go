package observation

import (
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
)

// These are isolated contract fixtures, not host observations or live authority.
func nativeV1ReviewFixture(t *testing.T, kind string) (map[string]any, map[string]any, map[string]any, string) {
	t.Helper()
	observed, event, context, _ := claudeReviewFixture(t)
	context["activity"], observed["kind"], event["kind"] = kind, kind, kind
	if kind == "quality_review" {
		context["tasks"] = []any{context["task"], map[string]any{"id": "T-002", "criterion_refs": []any{"AC-001", "AC-002"}}}
		context["base_input_sha256"] = testDigest("scope base")
		context["task_hashes"] = map[string]any{"T-001": context["task_sha256"], "T-002": testDigest("task two")}
		context["scope_baseline"] = map[string]any{"base_input_sha256": context["base_input_sha256"], "plan_sha256": context["plan_sha256"]}
		delete(context, "task")
		delete(context, "task_sha256")
		delete(context, "commands")
		model.M(model.M(observed["producer_result"])["decision"])["coverage"] = []any{"AC-002", "AC-001"}
	}
	contextHash := testValueHash(t, context)
	observed["context_ref"], observed["context_sha256"] = ContextRef(contextHash), contextHash
	observed["producer_profile"] = "codex-native-v1/0.145.0"
	observed["producer_run_id"] = "a0123456-789b-4cde-8123-456789abcdef"
	model.M(observed["producer_result"])["launch"] = map[string]any{
		"parent_session_id": "fixture-parent", "parent_turn_id": "b0123456-789b-4cde-8123-456789abcdef", "tool_use_id": "fixture-tool",
		"post_confirmed": true, "agent_id": observed["producer_run_id"], "agent_type": "default",
		"codex_review_profile": "codex-native-v1/0.145.0", "child_turn_id": "c0123456-789b-4cde-8123-456789abcdef",
		"fork_context": false, "first_stop": true,
	}
	observed["producer_result_sha256"] = testValueHash(t, observed["producer_result"])
	return observed, event, context, contextHash
}

func testValueHash(t *testing.T, value any) string {
	t.Helper()
	h, err := canonical.Hash(value)
	if err != nil {
		t.Fatal(err)
	}
	return h
}

func requireNativeV1Review(t *testing.T, observed, event, context map[string]any, contextHash string) {
	t.Helper()
	if errors := schema.ValidateWith(ContextSchema(), context); len(errors) != 0 {
		t.Fatalf("invalid review context fixture: %v", errors)
	}
	if errors := schema.ValidateWith(Schema(), observed); len(errors) != 0 {
		t.Fatalf("native-v1 review rejected by observation schema: %v", errors)
	}
	if err := ValidateLink(event, observed, context, ContextRef(contextHash), contextHash); err != nil {
		t.Fatalf("native-v1 review rejected by semantic binding: %v", err)
	}
}

func TestCodexNativeV1ReviewProfile(t *testing.T) {
	for _, kind := range []string{"spec_review", "quality_review"} {
		t.Run(kind, func(t *testing.T) {
			observed, event, context, contextHash := nativeV1ReviewFixture(t, kind)
			requireNativeV1Review(t, observed, event, context, contextHash)
		})
	}
}

func TestCodexNativeV1ReviewRejectsUnboundEvidence(t *testing.T) {
	base, event, context, contextHash := nativeV1ReviewFixture(t, "spec_review")
	// Every rejection below has this admitted validity witness; a blanket
	// rejection of the native profile cannot make the negative controls pass.
	requireNativeV1Review(t, base, event, context, contextHash)
	tests := []struct {
		name   string
		mutate func(map[string]any, map[string]any, map[string]any)
	}{
		{"changed producer run", func(o, e, c map[string]any) { o["producer_run_id"] = "d0123456-789b-4cde-8123-456789abcdef" }},
		{"wrong producer profile", func(o, e, c map[string]any) { o["producer_profile"] = "codex-native-v1/0.145.1" }},
		{"native under historical codex", func(o, e, c map[string]any) { o["producer_profile"] = CodexReviewProfile }},
		{"native under claude", func(o, e, c map[string]any) { o["producer_profile"] = ClaudeReviewProfile }},
		{"changed context", func(o, e, c map[string]any) { c["input_sha256"] = testDigest("other input") }},
		{"changed context locator", func(o, e, c map[string]any) { o["context_ref"] = ContextRef(testDigest("other context")) }},
		{"changed context digest", func(o, e, c map[string]any) { o["context_sha256"] = testDigest("other context") }},
		{"changed subject", func(o, e, c map[string]any) { model.M(o["subject"])["record_id"] = "T-002" }},
		{"changed event kind", func(o, e, c map[string]any) { e["kind"] = "quality_review" }},
		{"changed payload", func(o, e, c map[string]any) { model.M(e["payload"])["assessment"] = "Different assessment." }},
	}
	for name, value := range map[string]any{
		"agent_id": "not-a-uuid", "agent_type": "explorer", "codex_review_profile": "codex-review/0.1.0",
		"child_turn_id": "not-a-uuid", "fork_context": true, "first_stop": false, "post_confirmed": false,
	} {
		tests = append(tests, struct {
			name   string
			mutate func(map[string]any, map[string]any, map[string]any)
		}{"invalid launch " + name, func(o, e, c map[string]any) { model.M(model.M(o["producer_result"])["launch"])[name] = value }})
	}
	for _, name := range []string{"parent_session_id", "parent_turn_id", "tool_use_id", "post_confirmed", "agent_id", "agent_type", "codex_review_profile", "child_turn_id", "fork_context", "first_stop"} {
		tests = append(tests, struct {
			name   string
			mutate func(map[string]any, map[string]any, map[string]any)
		}{"missing launch " + name, func(o, e, c map[string]any) { delete(model.M(model.M(o["producer_result"])["launch"]), name) }})
	}
	for _, name := range []string{"task_name", "fork_turns", "requested_agent_type", "unexpected"} {
		tests = append(tests, struct {
			name   string
			mutate func(map[string]any, map[string]any, map[string]any)
		}{"forbidden launch " + name, func(o, e, c map[string]any) { model.M(model.M(o["producer_result"])["launch"])[name] = "none" }})
	}
	for _, name := range []string{"agent_id", "child_turn_id"} {
		tests = append(tests, struct {
			name   string
			mutate func(map[string]any, map[string]any, map[string]any)
		}{"noncanonical uuid " + name, func(o, e, c map[string]any) {
			model.M(model.M(o["producer_result"])["launch"])[name] = "A0123456-789B-4CDE-8123-456789ABCDEF"
		}})
	}
	tests = append(tests, struct {
		name   string
		mutate func(map[string]any, map[string]any, map[string]any)
	}{"parent child turn confusion", func(o, e, c map[string]any) {
		launch := model.M(model.M(o["producer_result"])["launch"])
		launch["child_turn_id"] = launch["parent_turn_id"]
	}})
	for name, value := range map[string]any{
		"format": "codearbiter.review-decision/0.2.0", "request_id": "invalid", "target_sha256": testDigest("other target"),
		"contract_sha256": testDigest("other contract"), "decision": "changes_requested", "assessment": "Other assessment.",
		"coverage": []any{"AC-002"}, "findings": []any{map[string]any{"severity": "BLOCK", "code": "NO", "message": "Blocked."}},
	} {
		tests = append(tests, struct {
			name   string
			mutate func(map[string]any, map[string]any, map[string]any)
		}{"changed decision " + name, func(o, e, c map[string]any) { model.M(model.M(o["producer_result"])["decision"])[name] = value }})
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			candidate, err := canonical.Clone(base)
			if err != nil {
				t.Fatal(err)
			}
			eventCopy, _ := canonical.Clone(event)
			contextCopy, _ := canonical.Clone(context)
			tc.mutate(candidate, eventCopy, contextCopy)
			// Rehash the changed producer to test its meaning, not merely stale bytes.
			candidate["producer_result_sha256"] = testValueHash(t, candidate["producer_result"])
			if len(schema.ValidateWith(Schema(), candidate)) == 0 && ValidateLink(eventCopy, candidate, contextCopy, ContextRef(contextHash), contextHash) == nil {
				t.Fatal("unbound native-v1 evidence accepted")
			}
		})
	}
}

func TestCodexNativeV1RejectsHistoricalRelabeling(t *testing.T) {
	for _, profile := range []string{CodexReviewProfile, ClaudeReviewProfile} {
		t.Run(profile, func(t *testing.T) {
			observed, event, context, contextHash := claudeReviewFixture(t)
			if profile == CodexReviewProfile {
				observed["producer_profile"] = profile
				model.M(observed["producer_result"])["launch"] = map[string]any{
					"parent_session_id": "historical-parent", "parent_turn_id": "historical-turn", "tool_use_id": "historical-tool",
					"post_confirmed": true, "agent_id": observed["producer_run_id"], "agent_type": "default", "task_name": "review", "fork_turns": "none",
				}
				observed["producer_result_sha256"] = testValueHash(t, observed["producer_result"])
			}
			if len(schema.ValidateWith(Schema(), observed)) != 0 || ValidateLink(event, observed, context, ContextRef(contextHash), contextHash) != nil {
				t.Fatal("historical profile validity witness rejected")
			}
			observed["producer_profile"] = "codex-native-v1/0.145.0"
			if len(schema.ValidateWith(Schema(), observed)) == 0 && ValidateLink(event, observed, context, ContextRef(contextHash), contextHash) == nil {
				t.Fatal("historical launch relabeled as native-v1")
			}
		})
	}
}

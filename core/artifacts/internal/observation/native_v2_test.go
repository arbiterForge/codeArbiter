package observation

import (
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
)

// Source-derived isolated fixtures. These are not native host receipts.
func nativeV2ReviewFixture(t *testing.T, kind string) (map[string]any, map[string]any, map[string]any, string) {
	t.Helper()
	o, e, c, h := nativeV1ReviewFixture(t, kind)
	o["producer_profile"] = "codex-native-v2/0.162.0-alpha.2"
	l := model.M(model.M(o["producer_result"])["launch"])
	l["codex_review_profile"] = o["producer_profile"]
	delete(l, "fork_context")
	l["fork_turns"] = "none"
	l["parent_thread_id"] = "d0123456-789b-4cde-8123-456789abcdef"
	l["task_name"] = "/root/authority_example"
	l["native_activity"] = map[string]any{
		"type": "item_completed", "thread_id": l["parent_thread_id"], "turn_id": l["parent_turn_id"],
		"item":          map[string]any{"type": "SubAgentActivity", "id": l["tool_use_id"], "kind": "started", "agent_thread_id": l["agent_id"], "agent_path": l["task_name"]},
		"started_at_ms": int64(1791601481147), "completed_at_ms": int64(1791601481147),
	}
	l["native_activity_sha256"] = testValueHash(t, l["native_activity"])
	l["native_child"] = map[string]any{"cli_version": "0.162.0-alpha.2", "thread_id": l["agent_id"], "parent_thread_id": l["parent_thread_id"], "session_id": l["parent_session_id"], "agent_path": l["task_name"], "metadata_sha256": testDigest("child metadata")}
	o["producer_result_sha256"] = testValueHash(t, o["producer_result"])
	return o, e, c, h
}

func requireNativeV2Review(t *testing.T, o, e, c map[string]any, h string) {
	t.Helper()
	if errors := schema.ValidateWith(Schema(), o); len(errors) != 0 {
		t.Fatalf("native-v2 exact activity/UUID review rejected by schema: %v", errors)
	}
	if err := ValidateLink(e, o, c, ContextRef(h), h); err != nil {
		t.Fatalf("native-v2 exact activity/UUID review rejected by semantic binding: %v", err)
	}
}

func TestCodexNativeV2ReviewProfile(t *testing.T) {
	for _, kind := range []string{"spec_review", "quality_review"} {
		t.Run(kind, func(t *testing.T) {
			o, e, c, h := nativeV2ReviewFixture(t, kind)
			requireNativeV2Review(t, o, e, c, h)
		})
	}
}

func TestCodexNativeV2RejectsUnboundActivityAndProfileRelabeling(t *testing.T) {
	base, event, context, hash := nativeV2ReviewFixture(t, "spec_review")
	requireNativeV2Review(t, base, event, context, hash)
	mutations := map[string]func(map[string]any){
		"run UUID":         func(o map[string]any) { o["producer_run_id"] = "e0123456-789b-4cde-8123-456789abcdef" },
		"V1 label":         func(o map[string]any) { o["producer_profile"] = "codex-native-v1/0.145.0" },
		"historical label": func(o map[string]any) { o["producer_profile"] = CodexReviewProfile },
		"launch profile": func(o map[string]any) {
			model.M(model.M(o["producer_result"])["launch"])["codex_review_profile"] = "codex-native-v1/0.145.0"
		},
		"activity digest": func(o map[string]any) {
			model.M(model.M(o["producer_result"])["launch"])["native_activity_sha256"] = testDigest("other activity")
		},
		"first Stop":   func(o map[string]any) { model.M(model.M(o["producer_result"])["launch"])["first_stop"] = false },
		"history fork": func(o map[string]any) { model.M(model.M(o["producer_result"])["launch"])["fork_turns"] = "all" },
		"parent child turn": func(o map[string]any) {
			l := model.M(model.M(o["producer_result"])["launch"])
			l["child_turn_id"] = l["parent_turn_id"]
		},
		"reversed activity time": func(o map[string]any) {
			l := model.M(model.M(o["producer_result"])["launch"])
			model.M(l["native_activity"])["completed_at_ms"] = int64(0)
			l["native_activity_sha256"] = testValueHash(t, l["native_activity"])
		},
	}
	for _, field := range []string{"thread_id", "parent_thread_id", "session_id", "agent_path", "cli_version"} {
		mutations["child "+field] = func(o map[string]any) {
			model.M(model.M(model.M(o["producer_result"])["launch"])["native_child"])[field] = "wrong"
		}
	}
	for _, field := range []string{"thread_id", "turn_id"} {
		mutations["activity "+field] = func(o map[string]any) {
			l := model.M(model.M(o["producer_result"])["launch"])
			model.M(l["native_activity"])[field] = "e0123456-789b-4cde-8123-456789abcdef"
			l["native_activity_sha256"] = testValueHash(t, l["native_activity"])
		}
	}
	for _, field := range []string{"id", "agent_thread_id", "agent_path", "kind", "type"} {
		mutations["activity item "+field] = func(o map[string]any) {
			l := model.M(model.M(o["producer_result"])["launch"])
			model.M(model.M(l["native_activity"])["item"])[field] = "wrong"
			l["native_activity_sha256"] = testValueHash(t, l["native_activity"])
		}
	}
	for _, field := range []string{"native_activity", "native_activity_sha256", "native_child", "parent_thread_id", "task_name", "first_stop", "child_turn_id"} {
		mutations["missing "+field] = func(o map[string]any) { delete(model.M(model.M(o["producer_result"])["launch"]), field) }
	}
	for name, mutate := range mutations {
		t.Run(name, func(t *testing.T) {
			o, _ := canonical.Clone(base)
			mutate(o)
			o["producer_result_sha256"] = testValueHash(t, o["producer_result"])
			if len(schema.ValidateWith(Schema(), o)) == 0 && ValidateLink(event, o, context, ContextRef(hash), hash) == nil {
				t.Fatal("unbound V2 evidence accepted")
			}
		})
	}
	old, e, c, h := nativeV1ReviewFixture(t, "spec_review")
	requireNativeV1Review(t, old, e, c, h)
	old["producer_profile"] = "codex-native-v2/0.162.0-alpha.2"
	if len(schema.ValidateWith(Schema(), old)) == 0 && ValidateLink(e, old, c, ContextRef(h), h) == nil {
		t.Fatal("V1 receipt relabeled as V2")
	}
}

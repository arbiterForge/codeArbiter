package operations

import (
	"os"
	"path"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

func TestProjectViewPresentsBoundedCanonicalWork(t *testing.T) {
	root := testutil.Root(t)
	call := func(op string, r object) object {
		t.Helper()
		r["protocol"] = Protocol
		v, err := Run(root, op, r)
		if err != nil {
			t.Fatalf("%s: %v", op, err)
		}
		return v.(object)
	}
	call("init-store", object{})
	first := call("work-create", object{"operation_id": "project-view-create-001", "title": "Fix <input>", "intent": "Local repair", "work_type": "fix"})
	second := call("work-create", object{"operation_id": "project-view-create-002", "title": "Plan delivery", "intent": "Local plan", "work_type": "feature"})
	call("work-update", object{"operation_id": "project-view-complete-001", "work_id": first["work_id"], "action": "complete", "expected": object{"revision": first["revision"], "model_sha256": first["model_sha256"]}})
	listing := call("work-list", object{"limit": int64(2)})
	call("work-provider-configure", object{"operation_id": "project-view-provider-001", "repository": "arbiterForge/disposable", "credential_ref": "GH_TOKEN", "effect_timing": "after_merge"})
	ids := []string{first["work_id"].(string), second["work_id"].(string)}
	seenEscaped, seenComplete, seenUnknown := false, false, false
	for offset := int64(0); offset < 2; offset++ {
		request := object{"offset": offset, "limit": int64(1)}
		if offset > 0 {
			request["membership_sha256"] = listing["membership_sha256"]
		}
		view := call("project-view", request)
		if view["canonical"] != false || view["content_snapshot"] != false || view["total"] != int64(2) {
			t.Fatalf("project view claimed canonical or complete snapshot: %v", view)
		}
		if view["project_id"] != first["project_id"] || view["membership_sha256"] != listing["membership_sha256"] {
			t.Fatalf("project identity or continuation changed: %v", view)
		}
		html := view["html"].(string)
		seenEscaped = seenEscaped || strings.Contains(html, "Fix &lt;input&gt;")
		seenComplete = seenComplete || strings.Contains(html, "<strong>Local progress:</strong> complete")
		seenUnknown = seenUnknown || strings.Contains(html, "<strong>Checks:</strong> unknown")
		if !strings.Contains(html, "Local progress") || !strings.Contains(html, "Checks") || !strings.Contains(html, "Delivery") || !strings.Contains(html, "Tracker sync") {
			t.Fatal("project view collapsed distinct status owners")
		}
		if strings.Contains(html, `<h2>Delivery</h2><p>Unobserved`) || !strings.Contains(html, "Open a work item for its delivery observation") {
			t.Fatal("project page misreported individual PR observations as a project-wide delivery state")
		}
		if strings.Contains(html, "Unconfigured in the local work model") || !strings.Contains(html, "Open a work item for its tracker state") {
			t.Fatal("project view invented an unconfigured tracker state after provider binding")
		}
		if strings.Contains(html, "Fix <input>") || strings.Contains(html, `id="ca-artifact-model"`) {
			t.Fatal("project view emitted unsafe or canonical content")
		}
		if _, err := render.Parse([]byte(html)); err == nil {
			t.Fatal("generated project view parsed as a canonical artifact")
		}
		viewPath := view["view_path"].(string)
		if _, err := os.Stat(filepath.Join(root, filepath.FromSlash(viewPath))); !os.IsNotExist(err) {
			t.Fatalf("read-only project view wrote a file: %v", err)
		}
		linked := 0
		for _, id := range ids {
			href := "../../work/" + id + ".html"
			if strings.Contains(html, href) {
				linked++
				resolved := path.Clean(path.Join(path.Dir(viewPath), href))
				if _, err := os.Stat(filepath.Join(root, filepath.FromSlash(resolved))); err != nil {
					t.Fatalf("project link does not reach canonical work: %v", err)
				}
			}
		}
		if linked != 1 {
			t.Fatalf("page %d linked %d work items, expected one", offset, linked)
		}
		if offset == 0 && (view["next_offset"] != int64(1) || !strings.Contains(html, "More work remains")) {
			t.Fatalf("first page hid continuation: %v", view)
		}
		if offset == 0 {
			command := "work.py project-view --offset 1 --membership-sha256 " + listing["membership_sha256"].(string)
			if !strings.Contains(html, command) {
				t.Fatalf("HTML-only caller cannot request the next page without response metadata: %v", view)
			}
		}
		if offset == 1 && view["next_offset"] != nil {
			t.Fatalf("last page claimed another page: %v", view)
		}
	}
	if !seenEscaped || !seenComplete || !seenUnknown {
		t.Fatal("project pages lost escaped title or independent progress/check facts")
	}
	call("work-create", object{"operation_id": "project-view-create-003", "title": "Later work", "intent": "New member", "work_type": "chore"})
	if _, err := Run(root, "project-view", object{"protocol": Protocol, "offset": int64(1), "limit": int64(1), "membership_sha256": listing["membership_sha256"]}); err == nil || !strings.Contains(err.Error(), "STALE_CURSOR") {
		t.Fatalf("project view accepted a stale membership cursor: %v", err)
	}
	if _, err := Run(root, "project-view", object{"protocol": Protocol, "budget": int64(4096)}); err == nil || !strings.Contains(err.Error(), "INVALID_MODEL") {
		t.Fatalf("HTML project view accepted a misleading JSON response budget: %v", err)
	}
}

func TestProjectViewShowsBoundedRecordedArchitecture(t *testing.T) {
	f := newAssistiveFixture(t)
	f.createKnowledge("knowledge", "CTX-CODE-MAP", "code-map")
	f.addKnowledge("CTX-CODE-MAP",
		knowledgeRecord("component", "API <gateway>", "Receives local requests.", "inferred", []string{"api/**"}),
		knowledgeRecord("interface", "Worker boundary", "Passes jobs to workers.", "inferred", []string{"worker/**"}),
		knowledgeRecord("fact", "Unrelated detail", "Not an architecture record.", "inferred", nil),
		knowledgeRecord("component", "Storage", "Persists records.", "proposed", []string{"store/**"}),
		knowledgeRecord("component", "UI", "Shows work.", "inferred", []string{"ui/**"}),
		knowledgeRecord("component", "CLI", "Routes commands.", "inferred", []string{"cli/**"}),
	)
	f.call("work-create", object{"operation_id": f.next(), "title": "Build interface", "intent": "Explain system boundaries", "work_type": "feature"})
	view := f.call("project-view", object{"limit": int64(1)})
	html := view["html"].(string)
	for _, required := range []string{"Recorded architecture", "API &lt;gateway&gt;", "Worker boundary", "Storage", "UI", "More architecture records", "../../context/code-map.html"} {
		if !strings.Contains(html, required) {
			t.Fatalf("architecture summary omitted %q: %s", required, html)
		}
	}
	if strings.Contains(html, "API <gateway>") || strings.Contains(html, "Unrelated detail") || strings.Contains(html, "CLI</h3>") {
		t.Fatal("architecture summary escaped incorrectly or exceeded its four-record bound")
	}
	if _, claimed := view["architecture_complete"]; claimed || view["architecture_omitted"] != int64(1) {
		t.Fatalf("architecture summary claimed completeness or lost omissions: %v", view)
	}
}

func TestCycleViewGroupsCanonicalWorkWithoutCopyingIt(t *testing.T) {
	f := newAssistiveFixture(t)
	first := f.call("work-create", object{"operation_id": f.next(), "title": "First delivery", "intent": "Ship first slice", "work_type": "feature"})
	second := f.call("work-create", object{"operation_id": f.next(), "title": "Second delivery", "intent": "Ship second slice", "work_type": "fix"})
	other := f.call("work-create", object{"operation_id": f.next(), "title": "Outside cycle", "intent": "Separate work", "work_type": "chore"})
	assign := func(item object, cycle string) object {
		t.Helper()
		return f.call("work-update", object{"operation_id": f.next(), "work_id": item["work_id"], "action": "set-cycle", "cycle_id": cycle,
			"expected": object{"revision": item["revision"], "model_sha256": item["model_sha256"]}})
	}
	first = assign(first, "october-sprint")
	second = assign(second, "october-sprint")
	other = assign(other, "later-sprint")
	second = f.call("work-update", object{"operation_id": f.next(), "work_id": second["work_id"], "action": "complete",
		"expected": object{"revision": second["revision"], "model_sha256": second["model_sha256"]}})
	view := f.call("cycle-view", object{"cycle_id": "october-sprint", "limit": int64(1)})
	if view["total"] != int64(2) || view["next_offset"] != int64(1) || view["canonical"] != false || view["content_snapshot"] != false {
		t.Fatalf("cycle page lost bounded derived membership: %v", view)
	}
	html := view["html"].(string)
	if !strings.Contains(html, "First delivery") && !strings.Contains(html, "Second delivery") {
		t.Fatal("cycle page omitted its selected member")
	}
	if strings.Contains(html, "Outside cycle") || strings.Contains(html, `id="ca-artifact-model"`) || !strings.Contains(html, "Checks") {
		t.Fatal("cycle page leaked another cycle, claimed authority or hid check state")
	}
	if _, err := render.Parse([]byte(html)); err == nil {
		t.Fatal("derived cycle page parsed as canonical work")
	}
	view2 := f.call("cycle-view", object{"cycle_id": "october-sprint", "offset": int64(1), "limit": int64(1), "membership_sha256": view["membership_sha256"]})
	if view2["total"] != int64(2) || view2["next_offset"] != nil {
		t.Fatalf("cycle continuation is wrong: %v", view2)
	}
	if _, err := Run(f.root, "cycle-view", object{"protocol": Protocol, "cycle_id": "october-sprint", "offset": int64(1), "limit": int64(1), "membership_sha256": strings.Repeat("0", 64)}); err == nil || !strings.Contains(err.Error(), "STALE_CURSOR") {
		t.Fatalf("cycle page accepted a stale cursor: %v", err)
	}
	if _, err := Run(f.root, "cycle-view", object{"protocol": Protocol, "cycle_id": "missing-sprint"}); err == nil || !strings.Contains(err.Error(), "NOT_FOUND") {
		t.Fatalf("missing cycle was presented as recorded: %v", err)
	}
	if got := f.call("work-get", object{"work_id": first["work_id"]}); got["cycle_id"] != "october-sprint" || got["work_id"] != first["work_id"] {
		t.Fatalf("cycle assignment changed work identity: %v", got)
	}
	if got := f.call("work-get", object{"work_id": other["work_id"]}); got["cycle_id"] != "later-sprint" {
		t.Fatalf("other cycle changed: %v", got)
	}
	cleared := f.call("work-update", object{"operation_id": f.next(), "work_id": first["work_id"], "action": "set-cycle", "cycle_id": nil,
		"expected": object{"revision": first["revision"], "model_sha256": first["model_sha256"]}})
	if cleared["cycle_id"] != nil || cleared["work_id"] != first["work_id"] {
		t.Fatalf("clearing cycle changed the work identity: %v", cleared)
	}
	if _, err := Run(f.root, "work-update", object{"protocol": Protocol, "operation_id": f.next(), "work_id": first["work_id"], "action": "set-cycle", "cycle_id": "later-sprint",
		"expected": object{"revision": first["revision"], "model_sha256": first["model_sha256"]}}); err == nil || !strings.Contains(err.Error(), "REVISION_CONFLICT") {
		t.Fatalf("stale cycle assignment overwrote a later edit: %v", err)
	}
}

func TestCycleViewRejectsOutOfRangeDirectLimit(t *testing.T) {
	f := newAssistiveFixture(t)
	f.call("work-create", object{"operation_id": f.next(), "title": "Bounded cycle", "intent": "One member", "work_type": "chore", "cycle_id": "bounded-cycle"})
	fs, err := store.Open(f.root)
	if err != nil {
		t.Fatal(err)
	}
	defer fs.Close()
	e := &Engine{FS: fs}
	if _, err := e.cycleView(object{"cycle_id": "bounded-cycle", "limit": int64(17)}); err == nil || !strings.Contains(err.Error(), "INVALID_LIMIT") {
		t.Fatalf("direct cycle view accepted an out-of-range limit: %v", err)
	}
}

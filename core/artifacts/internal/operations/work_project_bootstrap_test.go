package operations

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

func nativeKnowledgeFixture(t *testing.T) *assistiveFixture {
	t.Helper()
	f := newGreenfield(t)
	if err := os.Remove(filepath.Join(f.root, ".codearbiter", "open-tasks.md")); err != nil {
		t.Fatal(err)
	}
	for _, slug := range []string{"project", "tech-stack", "coding-standards", "security-controls", "code-map"} {
		f.createKnowledge("knowledge", "CTX-"+strings.ToUpper(slug), slug)
	}
	return f
}

func TestKnowledgeInitializeBootstrapsPortableProjectBeforeFirstWork(t *testing.T) {
	f := nativeKnowledgeFixture(t)
	if _, err := f.request("work-create", object{"operation_id": "work-before-knowledge-001", "title": "Early", "intent": "Must wait", "work_type": "feature"}); fault.Code(err) != "PROJECT_NOT_INITIALIZED" {
		t.Fatalf("first work before enrollment was accepted: %v", err)
	}
	before, err := os.ReadFile(filepath.Join(f.root, filepath.FromSlash(contextPath)))
	if err != nil {
		t.Fatal(err)
	}
	request := object{"operation_id": "native-knowledge-initialize-001", "expected": object{contextPath: canonical.BytesHash(before)}}
	initialized, err := f.request("knowledge-initialize", request)
	if err != nil {
		t.Fatal(err)
	}
	projectID := model.S(model.M(initialized)["project_id"])
	if !projectIDPattern.MatchString(projectID) {
		t.Fatalf("knowledge initialization did not return a project ID: %v", initialized)
	}
	replayed, err := f.request("knowledge-initialize", request)
	if err != nil || model.S(model.M(replayed)["project_id"]) != projectID || model.M(replayed)["transaction"] == nil {
		t.Fatalf("lost-response retry did not retain the project identity: %v, %v", replayed, err)
	}
	projectBytes, err := os.ReadFile(filepath.Join(f.root, filepath.FromSlash(projectPath)))
	if err != nil {
		t.Fatal(err)
	}
	clone := testutil.Root(t)
	cloneProject := filepath.Join(clone, filepath.FromSlash(projectPath))
	if err := os.MkdirAll(filepath.Dir(cloneProject), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(cloneProject, projectBytes, 0600); err != nil {
		t.Fatal(err)
	}
	ids := []string{}
	for i, root := range []string{f.root, clone} {
		created, err := Run(root, "work-create", object{"protocol": Protocol, "operation_id": "independent-work-00" + string(rune('1'+i)), "title": "Same title", "intent": "Distinct outcome", "work_type": "feature"})
		if err != nil {
			t.Fatal(err)
		}
		v := model.M(created)
		if model.S(v["project_id"]) != projectID {
			t.Fatalf("first work minted another project ID: %v", created)
		}
		ids = append(ids, model.S(v["work_id"]))
	}
	if ids[0] == ids[1] {
		t.Fatal("independent first work items share one work identity")
	}
}

func TestKnowledgeInitializeRejectsOrphanAndKeepsLegacyOwner(t *testing.T) {
	legacy := newGreenfield(t)
	for _, slug := range []string{"project", "tech-stack", "coding-standards", "security-controls", "code-map"} {
		legacy.createKnowledge("knowledge", "CTX-"+strings.ToUpper(slug), slug)
	}
	if _, err := legacy.initializeKnowledge(); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(legacy.root, filepath.FromSlash(projectPath))); !os.IsNotExist(err) {
		t.Fatalf("legacy initialization created native owner: %v", err)
	}

	native := nativeKnowledgeFixture(t)
	orphan := filepath.Join(native.root, ".codearbiter", "work", "WORK-"+strings.Repeat("A", 32)+".html")
	if err := os.MkdirAll(filepath.Dir(orphan), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(orphan, []byte("orphan"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := native.initializeKnowledge(); fault.Code(err) != "INVALID_PROJECT" {
		t.Fatalf("orphan work without project identity was accepted: %v", err)
	}
	if _, err := os.Stat(filepath.Join(native.root, filepath.FromSlash(projectPath))); !os.IsNotExist(err) {
		t.Fatalf("refused initialization wrote a project identity: %v", err)
	}
}

func TestWorkCreateOriginReuseRefusesMixedOwner(t *testing.T) {
	f := nativeKnowledgeFixture(t)
	if _, err := f.initializeKnowledge(); err != nil {
		t.Fatal(err)
	}
	request := object{"operation_id": "mixed-origin-first", "title": "Original", "intent": "Keep one owner", "work_type": "feature", "origin": "test#mixed-owner"}
	if _, err := f.request("work-create", request); err != nil {
		t.Fatal(err)
	}
	board := filepath.Join(f.root, ".codearbiter", "open-tasks.md")
	if err := os.WriteFile(board, []byte("# Open tasks\n"), 0600); err != nil {
		t.Fatal(err)
	}
	request["operation_id"] = "mixed-origin-second"
	if _, err := f.request("work-create", request); fault.Code(err) != "LEGACY_CONFLICT" {
		t.Fatalf("origin reuse bypassed the mixed owner refusal: %v", err)
	}
}

func TestKnowledgeInitializeKeepsExistingNativeProjectIdentity(t *testing.T) {
	f := nativeKnowledgeFixture(t)
	projectID := "PROJECT-" + strings.Repeat("A", 32)
	projectBytes, err := canonical.Marshal(object{"format": "codearbiter.project", "version": int64(1), "owner": "native", "project_id": projectID})
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(f.root, filepath.FromSlash(projectPath))
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, projectBytes, 0600); err != nil {
		t.Fatal(err)
	}
	result, err := f.initializeKnowledge()
	if err != nil || model.S(model.M(result)["project_id"]) != projectID {
		t.Fatalf("existing project identity was not retained: %v, %v", result, err)
	}
	after, err := os.ReadFile(path)
	if err != nil || string(after) != string(projectBytes) {
		t.Fatalf("knowledge initialization rewrote an existing identity: %v", err)
	}
}

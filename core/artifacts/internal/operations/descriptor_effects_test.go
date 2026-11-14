package operations

import (
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
)

func descriptorEffectSnapshot(t *testing.T, root string) map[string]string {
	t.Helper()
	files := map[string]string{}
	base := filepath.Join(root, ".codearbiter")
	err := filepath.WalkDir(base, func(path string, entry fs.DirEntry, err error) error {
		if err != nil || entry.IsDir() {
			return err
		}
		bytes, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(base, path)
		if err == nil {
			files[filepath.ToSlash(rel)] = canonical.BytesHash(bytes)
		}
		return err
	})
	if err != nil {
		t.Fatal(err)
	}
	return files
}

func assertDescriptorCoversEffects(t *testing.T, f *assistiveFixture, op string, before map[string]string, required ...string) {
	t.Helper()
	d, ok := Descriptor(op)
	if !ok {
		t.Fatal("missing operation descriptor")
	}
	declared, observed := map[string]bool{}, map[string]bool{}
	for _, class := range d.Writes {
		declared[class] = true
	}
	for path, digest := range descriptorEffectSnapshot(t, f.root) {
		if before[path] == digest {
			continue
		}
		class := "canonical-artifact"
		if strings.HasPrefix(path, ".artifacts/") {
			class = strings.Split(strings.TrimPrefix(path, ".artifacts/"), "/")[0]
		}
		observed[class] = true
		if !declared[class] {
			t.Errorf("%s wrote %s in undeclared class %q; descriptor writes=%v", op, path, class, d.Writes)
		}
	}
	for _, class := range required {
		if !observed[class] {
			t.Errorf("%s fixture did not produce required effect class %q", op, class)
		}
	}
	for class := range declared {
		if !observed[class] {
			t.Errorf("%s descriptor credits input-only or unobserved effect class %q", op, class)
		}
	}
}

// Portable synthetic approvals exercise the real producers and compare actual
// newly written bytes with capability metadata. Fixture sources predate each
// snapshot, so the check cannot credit an operation with host-supplied inputs.
func TestApprovalDescriptorsCoverActualEffects(t *testing.T) {
	f := newAssistiveFixture(t)
	request := prepareEpochApprovalFixture(t, f)
	before := descriptorEffectSnapshot(t, f.root)
	approval := f.mutate("sprint-approve", request)
	t.Run("sprint-approve", func(t *testing.T) {
		assertDescriptorCoversEffects(t, f, "sprint-approve", before, "canonical-artifact", "events", "receipts", "transactions", "history")
	})
	lenses := object{}
	for _, name := range []string{"Scalable", "Maintainable", "Available", "Reliable", "Testable", "Securable"} {
		lenses[name] = object{"verdict": "Adequate", "reason": "Preserves the existing bounded contract."}
	}
	decision := object{"task_id": "T-001", "options": []any{object{"label": "Explicit method", "steps": model.List("Retain the regression oracle.", "Make the bounded change."), "lenses": lenses}}, "selected": int64(0), "strength": "moderate", "rationale": "No scope or authority expansion."}
	before = descriptorEffectSnapshot(t, f.root)
	f.mutate("smarts-apply", object{"grant_receipt": approval["grant_receipt"], "decision": decision})
	t.Run("smarts-apply", func(t *testing.T) {
		assertDescriptorCoversEffects(t, f, "smarts-apply", before, "canonical-artifact", "evidence-contexts", "observations", "authority-sources", "events", "receipts", "transactions", "history")
	})
}

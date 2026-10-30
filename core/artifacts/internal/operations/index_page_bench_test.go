package operations

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

func indexPageFixture(tb testing.TB, count int) string {
	tb.Helper()
	root := testutil.Root(tb)
	dir := filepath.Join(root, ".codearbiter", "specs")
	if err := os.MkdirAll(dir, 0700); err != nil {
		tb.Fatal(err)
	}
	for i := 0; i < count; i++ {
		slug := fmt.Sprintf("index-%04d", i)
		v := testutil.Spec()
		v["artifact_id"] = fmt.Sprintf("SPEC-INDEX-%04d", i)
		v["slug"] = slug
		body, err := render.Render(testutil.Seal(tb, v))
		if err != nil {
			tb.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(dir, slug+".html"), body, 0600); err != nil {
			tb.Fatal(err)
		}
	}
	if _, err := Run(root, "init-store", object{"protocol": Protocol}); err != nil {
		tb.Fatal(err)
	}
	return root
}

func TestIndexPageBudgetAndContinuation(t *testing.T) {
	root := indexPageFixture(t, 20)
	seen := map[string]bool{}
	offset := int64(0)
	digest := ""
	for {
		r := object{"protocol": Protocol, "budget": int64(4096), "offset": offset}
		if offset > 0 {
			r["catalog_sha256"] = digest
		}
		value, err := Run(root, "index", r)
		if err != nil {
			t.Fatal(err)
		}
		page := value.(object)
		encoded, err := json.Marshal(page)
		if err != nil || len(encoded)+1024 > 4096 {
			t.Fatalf("page exceeds budget: bytes=%d error=%v", len(encoded), err)
		}
		if digest != "" && page["catalog_sha256"] != digest {
			t.Fatal("catalog digest changed during stable paging")
		}
		digest = page["catalog_sha256"].(string)
		for _, raw := range page["entries"].([]any) {
			id := raw.(object)["artifact_id"].(string)
			if seen[id] {
				t.Fatalf("duplicate page item %s", id)
			}
			seen[id] = true
		}
		if page["next_offset"] == nil {
			break
		}
		next := page["next_offset"].(int64)
		if next <= offset {
			t.Fatal("index paging did not advance")
		}
		offset = next
	}
	if len(seen) != 20 {
		t.Fatalf("got %d unique artifacts, want 20", len(seen))
	}
}

// BenchmarkIndexPageAssembly excludes catalog scanning but includes authority
// status and digest generation, so it captures the complete page operation.
func BenchmarkIndexPageAssembly(b *testing.B) {
	root := indexPageFixture(b, repository.MaxArtifacts)
	f, err := store.Open(root)
	if err != nil {
		b.Fatal(err)
	}
	defer f.Close()
	c, err := repository.Scan(f)
	if err != nil {
		b.Fatal(err)
	}
	e := &Engine{FS: f, Catalog: c}
	r := object{"offset": int64(0)}
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if _, err := e.index(r, 65536); err != nil {
			b.Fatal(err)
		}
	}
}

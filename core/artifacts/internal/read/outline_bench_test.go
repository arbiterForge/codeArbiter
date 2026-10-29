package read_test

import (
	"encoding/json"
	"fmt"
	"reflect"
	"sort"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	artifactread "github.com/arbiterForge/codeArbiter/core/artifacts/internal/read"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

func outlineFixture(t testing.TB, rows int) *model.Document {
	t.Helper()
	v := testutil.Spec()
	n := model.M(v["normative"])
	scope := model.A(n["scope"])
	for i := 0; i < rows; i++ {
		scope = append(scope, map[string]any{
			"id": fmt.Sprintf("SCOPE-P%04d", i), "statement": "A bounded synthetic scope record.",
		})
	}
	n["scope"] = scope
	return testutil.Seal(t, v)
}

func TestOutlineDirectPageParity(t *testing.T) {
	doc := outlineFixture(t, 500)
	want := append([]string{}, doc.Symbols.Order...)
	sort.Strings(want)
	got := []string{}
	for offset := 0; ; {
		page, err := artifactread.Outline(doc, offset, 4096)
		if err != nil {
			t.Fatal(err)
		}
		encoded, err := json.Marshal(page)
		if err != nil || len(encoded) > 4096 {
			t.Fatalf("outline page exceeds budget: %d bytes, %v", len(encoded), err)
		}
		rows := model.A(page["records"])
		if offset == 0 && len(rows) != 50 {
			t.Fatalf("first 4096-byte page changed its boundary: %d rows", len(rows))
		}
		if len(rows) == 0 {
			t.Fatal("outline returned a nonadvancing page")
		}
		for _, row := range rows {
			got = append(got, model.S(model.M(row)["id"]))
		}
		if page["next_offset"] == nil {
			break
		}
		next := int(model.I(page["next_offset"]))
		if next != len(got) || next <= offset {
			t.Fatalf("outline continuation did not advance: %d after %d", next, offset)
		}
		offset = next
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("outline lost or reordered records: got %d, want %d", len(got), len(want))
	}
	wide, err := artifactread.Outline(doc, 0, 65536)
	if err != nil {
		t.Fatal(err)
	}
	if rows := len(model.A(wide["records"])); rows != 507 || wide["next_offset"] != nil {
		t.Fatalf("wide page boundary changed: %d rows, next %v", rows, wide["next_offset"])
	}
	if _, err := artifactread.Outline(doc, 0, 64); fault.Code(err) != "RECORD_TOO_LARGE" {
		t.Fatalf("small budget should refuse a nonadvancing page: %v", err)
	}
}

func BenchmarkOutlinePage(b *testing.B) {
	doc := outlineFixture(b, 500)
	for _, budget := range []int{4096, 16384, 65536} {
		b.Run(fmt.Sprintf("budget-%d", budget), func(b *testing.B) {
			b.ReportAllocs()
			for i := 0; i < b.N; i++ {
				if _, err := artifactread.Outline(doc, 0, budget); err != nil {
					b.Fatal(err)
				}
			}
		})
	}
}

package render

import (
	"strings"
	"testing"
)

// NT-07 / N-F06: passed and failed are accepted stored values that no native
// operation sets. A historical value still renders, with honest provenance.
func TestWorkViewLabelsStoredCheckValuesWithoutClaimingAnEvent(t *testing.T) {
	for _, status := range []string{"passed", "failed"} {
		html, err := WorkView(WorkViewData{
			ID: "WORK-0123456789ABCDEF0123456789ABCDEF", ProjectID: "PROJECT-0123456789ABCDEF0123456789ABCDEF",
			Title: "Historical work", Intent: "Keep history readable", WorkType: "feature",
			State: "complete", CheckStatus: status, CompletedAt: "2026-10-31",
		})
		if err != nil {
			t.Fatal(err)
		}
		view := string(html)
		if !strings.Contains(view, strings.ToUpper(status[:1])+status[1:]) {
			t.Fatalf("stored %s value was hidden", status)
		}
		if !strings.Contains(view, "No native codeArbiter operation sets this value") {
			t.Fatalf("stored %s value was presented as a native verification event", status)
		}
	}
	html, err := WorkView(WorkViewData{
		ID: "WORK-0123456789ABCDEF0123456789ABCDEF", ProjectID: "PROJECT-0123456789ABCDEF0123456789ABCDEF",
		Title: "New work", Intent: "Plain", WorkType: "feature", State: "active", CheckStatus: "unknown",
	})
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(html), "No native codeArbiter operation sets this value") {
		t.Fatal("the produced unknown value was labeled schema-only")
	}
}

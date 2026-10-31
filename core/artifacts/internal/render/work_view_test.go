package render

import (
	stdhtml "html"
	"strings"
	"testing"
)

func TestWorkViewNamesUnknownChecksAsRemainingObstacle(t *testing.T) {
	html, err := WorkView(WorkViewData{
		ID: "WORK-0123456789ABCDEF0123456789ABCDEF", ProjectID: "PROJECT-0123456789ABCDEF0123456789ABCDEF",
		Title: "Deliver local work", Intent: "Make the journey useful", WorkType: "feature",
		State: "complete", CheckStatus: "unknown", CompletedAt: "2026-10-31",
		Plan: &WorkViewAttachment{ID: "PLAN-WORK", Title: "Plan", Href: "../../plans/work.html"},
	})
	if err != nil {
		t.Fatal(err)
	}
	view := stdhtml.UnescapeString(string(html))
	if !strings.Contains(view, "Check evidence is unknown") || !strings.Contains(view, "Review the attached plan's verification evidence") {
		t.Fatal("completed work hid its unknown check or offered the wrong next action")
	}
	if strings.Contains(view, "Remaining obstacle</dt><dd>Not recorded") {
		t.Fatal("unknown checks were presented as no recorded obstacle")
	}
}

func TestWorkViewNamesFailedChecksAfterLocalCompletion(t *testing.T) {
	html, err := WorkView(WorkViewData{
		ID: "WORK-0123456789ABCDEF0123456789ABCDEF", ProjectID: "PROJECT-0123456789ABCDEF0123456789ABCDEF",
		Title: "Deliver local work", Intent: "Make the journey useful", WorkType: "feature",
		State: "complete", CheckStatus: "failed", CompletedAt: "2026-10-31",
	})
	if err != nil {
		t.Fatal(err)
	}
	view := string(html)
	if !strings.Contains(view, "Checks failed") || !strings.Contains(view, "Investigate the failed check") {
		t.Fatal("completed work concealed failed checks or offered the wrong next action")
	}
}

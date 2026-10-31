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

func TestWorkViewExplainsBoundStatusConflictWithoutClaimingDelivery(t *testing.T) {
	html, err := WorkView(WorkViewData{
		ID: "WORK-0123456789ABCDEF0123456789ABCDEF", ProjectID: "PROJECT-0123456789ABCDEF0123456789ABCDEF",
		Title: "Reopen issue", Intent: "Keep local and remote progress distinct", WorkType: "fix",
		State: "complete", CheckStatus: "unknown", CompletedAt: "2026-10-31", ProviderEffectKind: "status_update",
		ProviderEffectStatus: "conflict", RemoteState: "open", DesiredState: "closed",
		RemoteIssueURL: "https://github.com/owner/repo/issues/7",
	})
	if err != nil {
		t.Fatal(err)
	}
	view := string(html)
	for _, required := range []string{"Remote issue is open", "Local intent was closed", "Inspect the remote issue", "Checks", "Unobserved"} {
		if !strings.Contains(view, required) {
			t.Fatalf("work view omitted %q", required)
		}
	}
	if strings.Contains(view, "Checks</h2><p class=\"state\">Passed") {
		t.Fatal("remote conflict falsely established passing checks")
	}
}

func TestWorkViewLinksOnlyExactGithubWorkURLs(t *testing.T) {
	base := WorkViewData{ID: "WORK-0123456789ABCDEF0123456789ABCDEF", ProjectID: "PROJECT-0123456789ABCDEF0123456789ABCDEF",
		Title: "Deliver work", Intent: "Show navigable observations", WorkType: "fix", State: "complete", CheckStatus: "unknown",
		ProviderEffectStatus: "synchronized", RemoteIssueURL: "https://github.com/owner/repo/issues/7",
		DeliveryState: "open", DeliveryURL: "https://github.com/owner/repo/pull/8", DeliveryObservedAt: "2026-10-31T12:00:00Z"}
	html, err := WorkView(base)
	if err != nil {
		t.Fatal(err)
	}
	for _, href := range []string{`href="https://github.com/owner/repo/issues/7"`, `href="https://github.com/owner/repo/pull/8"`} {
		if !strings.Contains(string(html), href) {
			t.Fatalf("verified work URL is not navigable: %s", href)
		}
	}
	base.RemoteIssueURL = "javascript:alert(1)"
	base.DeliveryURL = "https://github.com.evil.example/owner/repo/pull/8"
	html, err = WorkView(base)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(html), `href="javascript:`) || strings.Contains(string(html), `href="https://github.com.evil.example`) {
		t.Fatal("unverified provider text became a navigation target")
	}
}

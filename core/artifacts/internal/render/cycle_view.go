package render

import (
	"strconv"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

type CycleViewData struct {
	ProjectID, CycleID, MembershipSHA256      string
	Offset, Total                             int64
	NextOffset                                *int64
	Queued, Active, Complete, Archived        int64
	UnknownChecks, PassedChecks, FailedChecks int64
	Entries                                   []ProjectViewEntry
}

// CycleView renders an inert overview of canonical work references. Counts
// describe local records at read time; they are not check or delivery proof.
func CycleView(data CycleViewData) ([]byte, error) {
	var w strings.Builder
	w.WriteString(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'"><title>Cycle work · codeArbiter</title><style>`)
	w.Write(CSS())
	w.WriteString(workViewStyle)
	w.WriteString(`</style></head><body><a class="skip" href="#main-content">Skip to cycle work</a><div class="layout"><aside class="sidebar"><img src="`)
	w.WriteString(esc(DefaultLogo()) + `" alt="codeArbiter"><p class="identity">` + esc(data.ProjectID) + `</p><h2>In this cycle</h2><nav aria-label="Cycle sections"><a href="#summary">Summary</a><a href="#work">Work</a></nav><p>Derived from current local work references. Refresh after they change.</p></aside><main class="main" id="main-content"><header class="hero"><p class="eyebrow">codeArbiter / cycle</p><h1>`)
	w.WriteString(esc(data.CycleID) + `</h1><p class="deck">A cycle groups work references. Local progress and checks are separate; delivery and tracker results remain on each work item.</p></header>`)
	w.WriteString(`<section class="work-card" id="summary"><h2>Cycle summary</h2><p>` + strconv.FormatInt(data.Total, 10) + ` work items · ` + strconv.FormatInt(data.Queued, 10) + ` queued · ` + strconv.FormatInt(data.Active, 10) + ` active · ` + strconv.FormatInt(data.Complete, 10) + ` complete · ` + strconv.FormatInt(data.Archived, 10) + ` archived</p><p><strong>Checks:</strong> ` + strconv.FormatInt(data.UnknownChecks, 10) + ` unknown · ` + strconv.FormatInt(data.PassedChecks, 10) + ` passed · ` + strconv.FormatInt(data.FailedChecks, 10) + ` failed</p><p>These counts reflect local work records at read time, not a frozen or remotely verified result.</p></section>`)
	w.WriteString(`<section class="work-card" id="work"><h2>Work on this page</h2><p>Showing ` + strconv.Itoa(len(data.Entries)) + ` of ` + strconv.FormatInt(data.Total, 10) + ` cycle members.</p><div class="work-grid">`)
	for _, item := range data.Entries {
		w.WriteString(`<section class="work-card"><h3><a href="` + esc(item.Href) + `">` + esc(item.Title) + `</a></h3><p class="identity">` + esc(item.ID) + ` · ` + esc(item.WorkType) + `</p><p><strong>Local progress:</strong> ` + esc(item.State) + `</p><p><strong>Checks:</strong> ` + esc(item.CheckStatus) + `</p></section>`)
	}
	w.WriteString(`</div>`)
	if data.NextOffset != nil {
		w.WriteString(`<p>More work remains. Run <code>work.py cycle-view ` + esc(data.CycleID) + ` --offset ` + strconv.FormatInt(*data.NextOffset, 10) + ` --membership-sha256 ` + esc(data.MembershipSHA256) + `</code>.</p>`)
	}
	w.WriteString(`</section><footer class="footer"><p>Derived static view · no runtime network resources</p></footer></main></div></body></html>`)
	out := []byte(w.String())
	if len(out) > 64<<10 {
		return nil, fault.New("RESPONSE_TOO_LARGE", "cycle view page exceeds 64 KiB")
	}
	return out, nil
}

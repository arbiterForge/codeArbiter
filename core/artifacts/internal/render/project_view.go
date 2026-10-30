package render

import (
	"strconv"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

// ProjectViewData is a bounded page of validated native work, not a second
// project or work model. The caller owns membership and continuation checks.
type ProjectViewData struct {
	ID         string
	Offset     int64
	Total      int64
	NextOffset *int64
	Entries    []ProjectViewEntry
}

type ProjectViewEntry struct {
	ID, Title, WorkType, State, CheckStatus, Href string
}

// ProjectView renders an inert, read-only page. Canonical work remains at its
// existing path; the generated page contains no artifact model container.
func ProjectView(data ProjectViewData) ([]byte, error) {
	var w strings.Builder
	w.WriteString(`<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'"><title>Project work · codeArbiter</title><style>`)
	w.Write(CSS())
	w.WriteString(workViewStyle)
	w.WriteString(`</style></head><body><a class="skip" href="#main-content">Skip to project work</a><div class="layout"><aside class="sidebar"><img src="`)
	w.WriteString(esc(DefaultLogo()) + `" alt="codeArbiter"><p class="identity">` + esc(data.ID) + `</p><h2>In this project</h2><nav aria-label="Project sections"><a href="#work">Work</a><a href="#delivery">Delivery</a><a href="#sync">Tracker sync</a></nav><p>Derived from current local work records. Refresh this view after work changes.</p></aside><main class="main" id="main-content"><header class="hero"><p class="eyebrow">codeArbiter / project</p><h1>Project work</h1><p class="deck">Local progress and checks are reported separately. Delivery and tracker state require their own evidence.</p></header>`)
	w.WriteString(`<section class="work-card" id="work"><h2>Work</h2><p>Showing ` + strconv.Itoa(len(data.Entries)) + ` of ` + strconv.FormatInt(data.Total, 10) + ` work items on this page.</p>`)
	if len(data.Entries) == 0 {
		w.WriteString(`<p>No work items on this page.</p>`)
	} else {
		w.WriteString(`<div class="work-grid">`)
		for _, item := range data.Entries {
			check := item.CheckStatus
			if check == "" {
				check = "unknown"
			}
			w.WriteString(`<section class="work-card"><h3><a href="` + esc(item.Href) + `">` + esc(item.Title) + `</a></h3><p class="identity">` + esc(item.ID) + ` · ` + esc(item.WorkType) + `</p><p><strong>Local progress:</strong> ` + esc(item.State) + `</p><p><strong>Checks:</strong> ` + esc(check) + `</p></section>`)
		}
		w.WriteString(`</div>`)
	}
	if data.NextOffset != nil {
		w.WriteString(`<p>More work remains. Generate the next page to continue from item ` + strconv.FormatInt(*data.NextOffset+1, 10) + `.</p>`)
	}
	w.WriteString(`</section><div class="work-grid"><section class="work-card" id="delivery"><h2>Delivery</h2><p>Unobserved. Local completion does not establish merge, release or deployment.</p></section><section class="work-card" id="sync"><h2>Tracker sync</h2><p>Unconfigured in the local work model. No remote result is implied.</p></section></div><details class="work-details"><summary>Source identity</summary><p>Project ` + esc(data.ID) + `</p><p>Page offset ` + strconv.FormatInt(data.Offset, 10) + `</p></details><footer class="footer"><p>Derived static view · no runtime network resources</p></footer></main></div></body></html>`)
	out := []byte(w.String())
	if len(out) > 64<<10 {
		return nil, fault.New("RESPONSE_TOO_LARGE", "project view page exceeds 64 KiB")
	}
	return out, nil
}

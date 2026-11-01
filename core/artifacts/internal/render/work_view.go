package render

import (
	"regexp"
	"strconv"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

// WorkViewData is a selected, already validated projection. A work view is
// generated for human orientation and contains no canonical artifact model.
type WorkViewData struct {
	ID, ProjectID, CycleID, Title, Intent, WorkType string
	State, CheckStatus, StartedAt, CompletedAt      string
	Revision                                        int64
	ModelSHA256                                     string
	Spec, Plan                                      *WorkViewAttachment
	PlanTask                                        *WorkViewTask
	ProviderEffectKind, ProviderEffectStatus        string
	RemoteIssueURL, RemoteState, DesiredState       string
	ProjectEffectKind, ProjectEffectStatus          string
	CoordinationAction, CoordinationIssueStatus     string
	CoordinationProjectStatus, CoordinationReason   string
	CoordinationSendStatus                          string
	DeliveryState, DeliveryURL, DeliveryObservedAt  string
	LegacyDetail                                    string
	LegacyMore                                      bool
}

type WorkViewAttachment struct {
	ID, Title, Summary, Href string
}

type WorkViewTask struct {
	ID, Title, State, NextAction, ReportedOutcome, ReportedFreshness string
	BindingCurrent                                                   bool
}

var githubWorkURL = regexp.MustCompile(`^https://github\.com/[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/(?:issues|pull)/[1-9][0-9]*$`)

func workExternalLink(w *strings.Builder, raw string) {
	if githubWorkURL.MatchString(raw) {
		w.WriteString(`<p><a href="` + esc(raw) + `">` + esc(raw) + `</a></p>`)
	} else {
		w.WriteString(`<p>` + esc(raw) + `</p>`)
	}
}

const workViewStyle = `
.work-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}
.work-card{border:1px solid #d5dce3;border-radius:.8rem;padding:1.1rem;background:#fff}
.work-card h2{margin-top:0}
.work-card p{overflow-wrap:anywhere}
.work-card .state{font-size:1.3rem;font-weight:700}
.work-nav{display:flex;flex-wrap:wrap;gap:.7rem;margin:1.2rem 0}
.work-nav a{padding:.35rem .65rem;border:1px solid #d5dce3;border-radius:.5rem}
.work-details{margin-top:1.5rem}
.work-details pre{white-space:pre-wrap;overflow-wrap:anywhere}
.work-snapshot{margin:1rem 0}
.work-snapshot dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.8rem 1.4rem;margin:0}
.work-snapshot dt{font-weight:700}
.work-snapshot dd{margin:.2rem 0 0;overflow-wrap:anywhere}
@media(max-width:48rem){.work-grid{grid-template-columns:1fr}}
@media(max-width:48rem){.work-snapshot dl{grid-template-columns:1fr}}
`

func workViewAttachment(w *strings.Builder, label, section string, a *WorkViewAttachment) {
	w.WriteString(`<section class="work-card" id="` + section + `"><h2>` + label + `</h2>`)
	if a == nil {
		w.WriteString(`<p>Not attached.</p></section>`)
		return
	}
	w.WriteString(`<p><a href="` + esc(a.Href) + `">` + esc(a.Title) + `</a></p><p>` + esc(a.Summary) + `</p>`)
	w.WriteString(`<p class="identity">` + esc(a.ID) + `</p></section>`)
}

// WorkView renders an inert, self-contained overview from selected native
// records. Its missing model container deliberately makes Parse refuse it.
func WorkView(data WorkViewData) ([]byte, error) {
	var w strings.Builder
	checkStatus := data.CheckStatus
	if checkStatus == "" {
		checkStatus = "unknown"
	}
	change := "No local implementation change recorded."
	if data.CompletedAt != "" {
		change = "Marked complete locally on " + data.CompletedAt + "."
	} else if data.StartedAt != "" {
		change = "Started locally on " + data.StartedAt + "."
	}
	next := "Define a concrete next action for this work."
	if data.Plan != nil {
		next = "No executable plan task was identified; inspect the attached plan."
	}
	if data.PlanTask != nil {
		next = data.PlanTask.ID + " — " + data.PlanTask.Title + ": " + data.PlanTask.NextAction
	}
	obstacle := "Not recorded in this work item."
	if checkStatus == "failed" {
		obstacle = "Checks failed; local completion does not resolve them."
		next = "Investigate the failed check and repeat the affected verification."
	} else if data.ProviderEffectStatus == "outcome_unknown" {
		obstacle = "The remote issue outcome is unknown."
		next = "Reconcile the remote issue before any new send."
	} else if data.ProviderEffectStatus == "conflict" {
		obstacle = "The remote issue status differs from the last local observation."
		next = "Inspect the remote issue and select a new status intent if needed."
	} else if data.ProjectEffectStatus == "outcome_unknown" {
		obstacle = "The GitHub Project effect outcome is unknown."
		next = "Read back the selected Project item or field before another send."
	} else if data.ProjectEffectStatus == "conflict" {
		obstacle = "The GitHub Project field differs from the saved remote baseline."
		next = "Inspect the Project field before selecting a new update."
	} else if data.CoordinationIssueStatus == "waiting_binding" || data.CoordinationProjectStatus == "waiting_binding" {
		obstacle = "A mapped tracker target is waiting for its existing issue or Project binding."
		next = "Bind the selected target, then explicitly run work.py sync-mapped."
	} else if data.CoordinationProjectStatus == "awaiting_observation" {
		obstacle = "The mapped Project field has no verified remote baseline yet."
		next = "Explicitly run work.py sync-mapped to read the bound field before sending."
	} else if data.CoordinationIssueStatus == "waiting_reconciliation" || data.CoordinationProjectStatus == "waiting_reconciliation" {
		obstacle = "A mapped tracker send has an uncertain prior outcome."
		next = "Reconcile the uncertain target before syncing the latest desired state."
	} else if data.CoordinationIssueStatus == "waiting_manual" || data.CoordinationProjectStatus == "waiting_manual" {
		obstacle = "A selected manual effect or conflict owns the tracker target."
		next = "Resolve or synchronize that manual effect before resuming mapped coordination."
	} else if data.CoordinationIssueStatus == "binding_changed" || data.CoordinationProjectStatus == "binding_changed" ||
		data.CoordinationIssueStatus == "unavailable" || data.CoordinationProjectStatus == "unavailable" {
		obstacle = "The saved transition mapping needs repair or explicit rebinding."
		next = "Inspect the map and bound provider identities before another send."
	} else if data.CoordinationSendStatus == "paused" || data.CoordinationIssueStatus == "paused" || data.CoordinationProjectStatus == "paused" {
		obstacle = "Mapped tracker effects are paused because the transition map is disabled."
		next = "Inspect the pending mapped effects before explicitly resuming or cancelling them."
	} else if data.State == "complete" && checkStatus == "unknown" {
		obstacle = "Check evidence is unknown."
		next = "Record the result of the relevant checks."
		if data.Plan != nil {
			next = "Review the attached plan's verification evidence and record the result."
		}
	}
	w.WriteString(`<!doctype html>
<!-- codeArbiter derived work view; regenerate from canonical work with work.py view --save -->
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'"><title>`)
	w.WriteString(esc(data.Title) + ` · codeArbiter work</title><style>`)
	w.Write(CSS())
	w.WriteString(workViewStyle)
	w.WriteString(`</style></head><body><a class="skip" href="#main-content">Skip to work</a><div class="layout"><aside class="sidebar"><img src="`)
	w.WriteString(esc(DefaultLogo()) + `" alt="codeArbiter"><p class="identity">` + esc(data.ID) + `</p><h2>In this work</h2><nav aria-label="Work sections"><a href="#progress">Progress</a><a href="#checks">Checks</a><a href="#delivery">Delivery</a><a href="#sync">Tracker sync</a><a href="#spec">Specification</a><a href="#plan">Plan</a></nav><p>Derived from the selected local work record. Refresh this view after the work changes.</p></aside><main class="main" id="main-content"><header class="hero"><p class="eyebrow">codeArbiter / work</p><h1>`)
	w.WriteString(esc(data.Title) + `</h1><p class="deck">` + esc(data.Intent) + `</p><div class="meta"><span>` + esc(data.ID) + `</span><span>` + esc(data.WorkType) + `</span>`)
	if data.CycleID != "" {
		w.WriteString(`<span>Cycle ` + esc(data.CycleID) + `</span>`)
	}
	w.WriteString(`</div></header>`)
	w.WriteString(`<section class="work-card work-snapshot" aria-labelledby="snapshot-title"><h2 id="snapshot-title">At a glance</h2><dl><div><dt>Current situation</dt><dd>` + esc(strings.ToUpper(data.State)) + ` locally</dd></div><div><dt>Recorded change</dt><dd>` + esc(change) + `</dd></div><div><dt>Remaining obstacle</dt><dd>` + esc(obstacle) + `</dd></div><div><dt>Next action</dt><dd>` + esc(next) + `</dd></div></dl></section>`)
	w.WriteString(`<nav class="work-nav" aria-label="Jump to work status"><a href="#progress">Progress</a><a href="#checks">Checks</a><a href="#delivery">Delivery</a><a href="#sync">Tracker sync</a></nav><div class="work-grid">`)
	w.WriteString(`<section class="work-card" id="progress"><h2>Local progress</h2><p class="state">` + esc(strings.ToUpper(data.State)) + `</p>`)
	if data.StartedAt != "" {
		w.WriteString(`<p>Started ` + esc(data.StartedAt) + `</p>`)
	}
	if data.CompletedAt != "" {
		w.WriteString(`<p>Completed locally ` + esc(data.CompletedAt) + `</p>`)
	}
	w.WriteString(`</section><section class="work-card" id="checks"><h2>Checks</h2><p class="state">` + esc(strings.ToUpper(checkStatus[:1])+checkStatus[1:]) + `</p><p>Check status is separate from local completion. Read the attached plan for exact verification evidence.</p></section>`)
	w.WriteString(`<section class="work-card" id="delivery"><h2>Delivery</h2>`)
	if data.DeliveryState == "" {
		w.WriteString(`<p class="state">Unobserved</p><p>This local record does not establish a merge, release or deployment.</p>`)
	} else {
		w.WriteString(`<p class="state">Recorded PR ` + esc(data.DeliveryState) + `</p><p>Observed ` + esc(data.DeliveryObservedAt) + `. Review the PR diff and checks to verify this work. Refresh this observation for later changes. It does not establish a release or deployment.</p>`)
		workExternalLink(&w, data.DeliveryURL)
	}
	w.WriteString(`</section>`)
	w.WriteString(`<section class="work-card" id="sync"><h2>Tracker sync</h2>`)
	if data.CoordinationAction != "" {
		w.WriteString(`<p>Mapped ` + esc(data.CoordinationAction) + ` transition: issue ` + esc(data.CoordinationIssueStatus) + `; Project ` + esc(data.CoordinationProjectStatus) + `. Remote updates require explicit synchronization.</p>`)
		if data.CoordinationSendStatus == "paused" {
			w.WriteString(`<p>Mapped sends are paused until this intent is explicitly reconciled with the current mapping.</p>`)
		}
		if data.CoordinationReason != "" {
			w.WriteString(`<p>` + esc(data.CoordinationReason) + `</p>`)
		}
	}
	switch data.ProviderEffectStatus {
	case "pending":
		if data.ProviderEffectKind == "status_update" {
			w.WriteString(`<p class="state">Pending</p><p>The bound issue has a local status intent; no update is confirmed.</p>`)
		} else {
			w.WriteString(`<p class="state">Pending</p><p>Local intent is saved; no remote issue is confirmed.</p>`)
		}
	case "outcome_unknown":
		w.WriteString(`<p class="state">Outcome unknown</p><p>A send may have succeeded. Reconcile the remote issue before retrying.</p>`)
	case "synchronized":
		w.WriteString(`<p class="state">Synchronized</p><p>A remote issue identity is recorded.</p>`)
		if data.RemoteIssueURL != "" {
			workExternalLink(&w, data.RemoteIssueURL)
		}
	case "conflict":
		w.WriteString(`<p class="state">Conflict</p><p>Inspect the remote issue before selecting another status intent.</p>`)
	default:
		w.WriteString(`<p class="state">Unconfigured</p><p>No provider binding or remote result is recorded in this local work model.</p>`)
	}
	if data.RemoteState != "" {
		w.WriteString(`<p>Remote issue is ` + esc(data.RemoteState) + `.</p>`)
	}
	if data.DesiredState != "" {
		w.WriteString(`<p>Local intent was ` + esc(data.DesiredState) + `.</p>`)
	}
	if data.ProviderEffectStatus != "synchronized" && data.RemoteIssueURL != "" {
		workExternalLink(&w, data.RemoteIssueURL)
	}
	if data.ProjectEffectStatus != "" {
		w.WriteString(`<h3>GitHub Project</h3>`)
		switch data.ProjectEffectStatus {
		case "pending":
			w.WriteString(`<p>Project effect pending; no new remote result is confirmed.</p>`)
		case "outcome_unknown":
			w.WriteString(`<p>Project outcome unknown. Read back before another send.</p>`)
		case "conflict":
			w.WriteString(`<p>Project field conflict. Inspect the remote value before restaging.</p>`)
		case "synchronized":
			if data.ProjectEffectKind == "set_single_select" {
				w.WriteString(`<p>Selected Project option was read back.</p>`)
			} else {
				w.WriteString(`<p>Project item was read back.</p>`)
			}
		}
	}
	w.WriteString(`</section>`)
	workViewAttachment(&w, "Specification", "spec", data.Spec)
	workViewAttachment(&w, "Implementation plan", "plan", data.Plan)
	if data.Plan != nil {
		w.WriteString(`<section class="work-card" id="plan-task"><h2>Selected plan task</h2>`)
		if data.PlanTask == nil {
			w.WriteString(`<p>No executable task was identified from the current plan state.</p>`)
		} else {
			task := data.PlanTask
			w.WriteString(`<p><strong>` + esc(task.ID) + ` — ` + esc(task.Title) + `</strong> · ` + esc(task.State) + `</p>`)
			if task.BindingCurrent {
				w.WriteString(`<p>Source binding current.</p>`)
			} else {
				w.WriteString(`<p>Source binding changed; reconcile the plan before relying on its task requirements.</p>`)
			}
			w.WriteString(`<p>` + esc(task.NextAction) + `</p>`)
			if task.ReportedOutcome == "" {
				w.WriteString(`<p>No check report recorded for this task.</p>`)
			} else {
				w.WriteString(`<p>Last check reported ` + esc(task.ReportedOutcome) + `; freshness ` + esc(task.ReportedFreshness) + `. Reported outcomes are not verified evidence.</p>`)
			}
		}
		w.WriteString(`</section>`)
	}
	w.WriteString(`</div>`)
	if data.LegacyDetail != "" {
		w.WriteString(`<details class="work-details"><summary>Original task details</summary><pre>` + esc(data.LegacyDetail) + `</pre>`)
		if data.LegacyMore {
			w.WriteString(`<p>More historical text is available through the selected work context pages.</p>`)
		}
		w.WriteString(`</details>`)
	}
	w.WriteString(`<details class="work-details"><summary>Source identity</summary><p>Project ` + esc(data.ProjectID) + `</p><p>Revision ` + strconv.FormatInt(data.Revision, 10) + `</p><p>Model SHA-256 ` + esc(data.ModelSHA256) + `</p></details><footer class="footer"><p>Derived static view · no runtime network resources</p></footer></main></div></body></html>`)
	out := []byte(w.String())
	if len(out) > 32<<10 {
		return nil, fault.New("RESPONSE_TOO_LARGE", "selected work view exceeds 32 KiB")
	}
	return out, nil
}

// Package render owns the complete static artifact grammar. Parse accepts only
// a byte-exact rendering by the declared installed renderer. It is not an HTML
// scraper: arbitrary HTML is never interpreted as a specification.
package render

import (
	"bytes"
	"embed"
	"encoding/json"
	"fmt"
	"html"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/symbol"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
)

const Version = "codearbiter-html/0.1.0"
const modelStart = "<script id=\"ca-artifact-model\" type=\"application/json\">\n"
const modelEnd = "\n</script>"

//go:embed assets/*
var assets embed.FS

func CSS() []byte { b, _ := assets.ReadFile("assets/artifact.css"); return b }
func DefaultLogo() string {
	b, _ := assets.ReadFile("assets/logo.svg")
	s, e := Logo("image/svg+xml", b)
	if e != nil {
		panic(e)
	}
	return s
}
func Presentation(companion string) map[string]any {
	return map[string]any{"renderer": Version, "brand_name": "codeArbiter", "logo_data_uri": DefaultLogo(), "logo_origin": "embedded codeArbiter logo", "logo_git_blob": nil, "companion_path": companion, "stylesheet_sha256": canonical.BytesHash(CSS())}
}
func Prepare(v map[string]any) (*model.Document, error) {
	if model.S(model.M(v["presentation"])["renderer"]) != Version {
		return nil, fault.New("UNSUPPORTED_RENDERER", "explicitly select the installed renderer")
	}
	d, e := model.Seal(v)
	if e != nil {
		return nil, e
	}
	if e = validate.Error(validate.Structural(d)); e != nil {
		return nil, e
	}
	return d, nil
}
func esc(s string) string { return html.EscapeString(s) }
func label(s string) string {
	if s == "spec_ref" {
		return "Specification binding"
	}
	if s == "criterion_refs" {
		return "Acceptance criteria"
	}
	if s == "argv" {
		return "Command arguments (not executed by this tool)"
	}
	s = strings.ReplaceAll(s, "_", " ")
	if len(s) == 0 {
		return s
	}
	return strings.ToUpper(s[:1]) + s[1:]
}

type writer struct {
	b strings.Builder
	d *model.Document
}

func (w *writer) text(s string) { w.b.WriteString(esc(s)) }
func (w *writer) raw(s string)  { w.b.WriteString(s) }
func (w *writer) link(s string) {
	if r, ok := w.d.Symbols.ByID[s]; ok {
		w.raw(`<a href="#` + esc(r.ID) + `">`)
		w.text(s)
		w.raw(`</a>`)
		return
	}
	if a, b, e := symbol.Split(s); e == nil {
		base := ""
		if a != w.d.ID() {
			base = model.S(model.M(w.d.Data["presentation"])["companion_path"])
		}
		if a == w.d.ID() || base != "" {
			w.raw(`<a href="` + esc(base+"#"+b) + `">`)
			w.text(s)
			w.raw(`</a>`)
			return
		}
	}
	w.text(s)
}
func (w *writer) value(v any, k string) {
	switch x := v.(type) {
	case nil:
		w.raw(`<span class="missing">Not yet supplied</span>`)
	case string:
		if x == "" {
			w.raw(`<span class="missing">Not yet supplied</span>`)
		} else if strings.HasSuffix(k, "_ref") || k == "refs" || k == "depends_on" || k == "tasks" || strings.HasSuffix(k, "_refs") {
			w.link(x)
		} else {
			w.text(x)
		}
	case int64:
		w.text(fmt.Sprint(x))
	case bool:
		w.text(fmt.Sprint(x))
	case []any:
		if len(x) > 0 && k == "argv" {
			encoded, err := canonical.Marshal(x)
			if err != nil {
				panic(err)
			}
			w.raw(`<pre><code>`)
			w.text(string(encoded))
			w.raw(`</code></pre>`)
			return
		}
		if len(x) > 0 && k == "paths" {
			w.raw(`<div class="table-wrap"><table><thead><tr><th scope="col">Action</th><th scope="col">Repository path</th></tr></thead><tbody>`)
			for _, item := range x {
				m := model.M(item)
				w.raw(`<tr><td>`)
				w.text(model.S(m["action"]))
				w.raw(`</td><td><code>`)
				w.text(model.S(m["path"]))
				w.raw(`</code></td></tr>`)
			}
			w.raw(`</tbody></table></div>`)
			return
		}
		if len(x) == 0 {
			w.raw(`<span class="missing">None recorded</span>`)
			return
		}
		simple := true
		for _, v := range x {
			if _, ok := v.(map[string]any); ok {
				simple = false
			}
			if _, ok := v.([]any); ok {
				simple = false
			}
		}
		if simple {
			w.raw(`<ul class="items">`)
			for _, v := range x {
				w.raw(`<li>`)
				w.value(v, k)
				w.raw(`</li>`)
			}
			w.raw(`</ul>`)
		} else {
			for _, v := range x {
				w.value(v, k)
			}
		}
	case map[string]any:
		if _, ok := x["id"]; ok {
			w.record(x, k)
			return
		}
		if k == "blocks" {
			w.block(x)
			return
		}
		w.raw(`<div class="fields">`)
		w.fields(x, nil)
		w.raw(`</div>`)
	}
}
func (w *writer) fields(m map[string]any, skip map[string]bool) {
	for _, k := range canonical.Keys(m) {
		if skip[k] {
			continue
		}
		w.raw(`<div class="field"><span class="label">`)
		w.text(label(k))
		w.raw(`</span>`)
		w.value(m[k], k)
		w.raw(`</div>`)
	}
}
func (w *writer) record(m map[string]any, k string) {
	id := model.S(m["id"])
	r := w.d.Symbols.ByID[id]
	class := "record"
	if r.Retired {
		class += " retired"
	}
	// IDs have already passed the symbol grammar; marker text is trusted structure.
	w.raw("\n<!-- CA:BEGIN:" + id + " -->\n")
	w.raw(`<article class="` + class + `" id="` + id + `" data-ca-symbol="` + id + `" data-ca-kind="` + esc(r.Kind) + `"><div class="record-head"><a class="id" href="#` + id + `">` + id + `</a><h3>`)
	title := model.S(m["title"])
	if title == "" {
		title = model.S(m["topic"])
	}
	if title == "" {
		title = label(k)
	}
	w.text(title)
	w.raw(`</h3>`)
	if ob := model.S(m["obligation"]); ob != "" {
		w.raw(`<span class="badge">`)
		w.text(ob)
		w.raw(`</span>`)
	}
	if r.Kind == "tasks" {
		state := model.S(model.M(model.M(model.M(w.d.Data["execution"])["tasks"])[id])["state"])
		w.raw(`<span class="badge">`)
		w.text(state)
		w.raw(`</span>`)
	}
	if r.Retired {
		w.raw(`<span class="badge">Retired</span>`)
	}
	w.raw(`</div>`)
	w.fields(m, map[string]bool{"id": true, "title": true, "topic": true, "obligation": true})
	if r.Kind == "tasks" {
		w.raw(`<details><summary>Execution record</summary>`)
		w.value(model.M(model.M(w.d.Data["execution"])["tasks"])[id], "execution")
		w.raw(`</details>`)
	}
	w.raw(`</article>` + "\n<!-- CA:END:" + id + " -->\n")
}
func (w *writer) block(m map[string]any) {
	w.raw(`<div class="block">`)
	switch model.S(m["type"]) {
	case "paragraph":
		w.raw(`<p>`)
		w.text(model.S(m["text"]))
		w.raw(`</p>`)
	case "code":
		w.raw(`<pre><code>`)
		w.text(model.S(m["text"]))
		w.raw(`</code></pre>`)
	case "list":
		w.value(m["items"], "items")
	case "table":
		w.raw(`<div class="table-wrap"><table><thead><tr>`)
		for _, v := range model.A(m["columns"]) {
			w.raw(`<th scope="col">`)
			w.text(model.S(v))
			w.raw(`</th>`)
		}
		w.raw(`</tr></thead><tbody>`)
		for _, row := range model.A(m["rows"]) {
			w.raw(`<tr>`)
			for _, v := range model.A(row) {
				w.raw(`<td>`)
				w.text(model.S(v))
				w.raw(`</td>`)
			}
			w.raw(`</tr>`)
		}
		w.raw(`</tbody></table></div>`)
	default:
		w.fields(m, map[string]bool{"refs": true})
	}
	if len(model.A(m["refs"])) > 0 {
		w.raw(`<div class="refs">References: `)
		for _, r := range model.Strings(m["refs"]) {
			w.link(r)
			w.raw(" ")
		}
		w.raw(`</div>`)
	}
	w.raw(`</div>`)
}
func Render(d *model.Document) ([]byte, error) {
	if e := d.VerifyIntegrity(); e != nil {
		return nil, e
	}
	if e := validate.Error(validate.Structural(d)); e != nil {
		return nil, e
	}
	p := model.M(d.Data["presentation"])
	if model.S(p["renderer"]) != Version {
		return nil, fault.New("UNSUPPORTED_RENDERER", "renderer is not installed")
	}
	if model.S(p["stylesheet_sha256"]) != canonical.BytesHash(CSS()) {
		return nil, fault.New("STYLE_MISMATCH", "stylesheet digest differs from installed renderer")
	}
	if e := CheckLogo(model.S(p["logo_data_uri"])); e != nil {
		return nil, e
	}
	w := writer{d: d}
	w.raw("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><meta name=\"color-scheme\" content=\"light\"><meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'\"><meta name=\"ca-artifact-format\" content=\"codearbiter.artifact/0.1.0\"><title>")
	w.text(model.S(d.Norm()["title"]))
	w.raw(` · `)
	w.text(model.S(p["brand_name"]))
	w.raw("</title><style>\n")
	w.raw(string(CSS()))
	w.raw("</style></head><body><a class=\"skip\" href=\"#main-content\">Skip to document</a><div class=\"layout\"><aside class=\"sidebar\"><img src=\"")
	w.raw(esc(model.S(p["logo_data_uri"])))
	w.raw(`" alt="` + esc(model.S(p["brand_name"])) + `"><p class="identity">`)
	w.text(d.ID())
	w.raw(`</p><h2>In this document</h2><nav aria-label="Document sections">`)
	order := []string{"intent", "scope", "non_goals", "approach", "constraints", "decisions", "criteria", "spec_ref", "prerequisites", "tasks", "checkpoints", "open_decisions", "sections", "sources", "baseline", "retired_symbols"}
	for _, k := range order {
		if _, ok := d.Norm()[k]; ok {
			w.raw(`<a href="#group-` + k + `">`)
			w.text(label(k))
			w.raw(`</a>`)
		}
	}
	w.raw(`</nav>`)
	if s := model.S(p["companion_path"]); s != "" {
		w.raw(`<a class="companion" href="` + esc(s) + `">Open companion `)
		if d.Kind() == "spec" {
			w.text("implementation plan")
		} else {
			w.text("specification")
		}
		w.raw(`</a>`)
	}
	w.raw(`<p>Generated from the embedded model. Edit through the artifact engine, not the HTML view.</p></aside><main class="main" id="main-content"><header class="hero"><p class="eyebrow">`)
	w.text(model.S(p["brand_name"]) + " / " + d.Kind())
	w.raw(`</p><span class="status">`)
	w.text(strings.ToUpper(model.S(model.M(d.Data["governance"])["state"])))
	w.raw(` · authority must be verified at use</span><h1>`)
	w.text(model.S(d.Norm()["title"]))
	w.raw(`</h1><p class="deck">`)
	w.text(model.S(d.Norm()["summary"]))
	w.raw(`</p><div class="meta"><span>`)
	w.text(d.ID())
	w.raw(`</span><span>`)
	w.text(fmt.Sprintf("Revision %d · schema %s", d.Revision(), model.S(d.Data["schema_version"])))
	w.raw(`</span><span>`)
	w.text(fmt.Sprintf("%d addressable records", len(d.Symbols.ByID)))
	w.raw(`</span></div></header>`)
	seen := map[string]bool{"title": true, "summary": true}
	group := func(k string) {
		if v, ok := d.Norm()[k]; ok {
			seen[k] = true
			w.raw(`<section class="group" id="group-` + k + `"><a class="back" href="#main-content">Top</a><h2>`)
			w.text(label(k))
			w.raw(`</h2>`)
			w.value(v, k)
			w.raw(`</section>`)
		}
	}
	for _, k := range order {
		group(k)
	}
	for _, k := range canonical.Keys(d.Norm()) {
		if !seen[k] {
			group(k)
		}
	}
	w.raw(`<section class="group"><h2>Governance record</h2><p class="notice">Hash consistency establishes content identity, not who approved it. Execution must verify current receipt sources and binding.</p>`)
	w.value(d.Data["governance"], "governance")
	w.raw(`</section><footer class="footer"><p>`)
	w.text(Version + " · self-contained, static HTML · no runtime network resources")
	w.raw(`</p><p class="digest">Normative SHA-256: `)
	w.text(d.NormHash())
	w.raw(`<br>Model SHA-256: `)
	w.text(d.Hash())
	w.raw(`</p></footer></main></div>` + "\n" + modelStart)
	// encoding/json's default HTML escaping prevents a payload closing its data script.
	b, e := json.MarshalIndent(d.Data, "", "  ")
	if e != nil {
		return nil, e
	}
	w.raw(string(b))
	w.raw(modelEnd + "\n</body></html>\n")
	out := []byte(w.b.String())
	if len(out) > canonical.MaxBytes {
		return nil, fault.New("MAX_BYTES", "rendered HTML exceeds 8 MiB")
	}
	return out, nil
}
func DecodeModel(b []byte) (map[string]any, error) {
	if len(b) > canonical.MaxBytes {
		return nil, fault.New("MAX_BYTES", "HTML exceeds 8 MiB")
	}
	start := []byte(modelStart)
	if bytes.Count(b, start) != 1 {
		return nil, fault.New("INVALID_CONTAINER", "expected exactly one canonical model container")
	}
	i := bytes.Index(b, start) + len(start)
	j := bytes.Index(b[i:], []byte(modelEnd))
	if j < 0 {
		return nil, fault.New("INVALID_CONTAINER", "model container is not closed")
	}
	return canonical.Object(b[i : i+j])
}
func Parse(b []byte) (*model.Document, error) {
	v, e := DecodeModel(b)
	if e != nil {
		return nil, e
	}
	d, e := model.Check(v)
	if e != nil {
		return nil, e
	}
	expected, e := Render(d)
	if e != nil {
		return nil, e
	}
	if !bytes.Equal(expected, b) {
		return nil, fault.New("RENDER_DRIFT", "HTML view differs from its validated model; use explicit repair preview, never an implicit rewrite")
	}
	return d, nil
}

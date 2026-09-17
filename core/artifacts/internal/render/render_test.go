package render_test

import (
	"bytes"
	"encoding/base64"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
	"testing"
)

func TestRenderRoundTrip(t *testing.T) {
	s := testutil.Seal(t, testutil.Spec())
	p := testutil.Seal(t, testutil.Plan(s))
	for _, d := range []*model.Document{s, p} {
		b, e := render.Render(d)
		if e != nil {
			t.Fatal(e)
		}
		got, e := render.Parse(b)
		if e != nil {
			t.Fatal(e)
		}
		if got.Hash() != d.Hash() {
			t.Fatal("hash changed")
		}
		for id := range d.Symbols.ByID {
			if bytes.Count(b, []byte("<!-- CA:BEGIN:"+id+" -->")) != 1 || bytes.Count(b, []byte("id=\""+id+"\"")) != 1 {
				t.Errorf("marker/anchor %s", id)
			}
		}
	}
}
func TestRenderDriftNormalRead(t *testing.T) {
	d := testutil.Seal(t, testutil.Spec())
	b, e := render.Render(d)
	if e != nil {
		t.Fatal(e)
	}
	bad := bytes.Replace(b, []byte("Select the environment value"), []byte("Select file value"), 1)
	if _, e = render.Parse(bad); e == nil {
		t.Fatal("tampered view accepted")
	}
	bad = append(b, []byte("<script>alert(1)</script>")...)
	if _, e = render.Parse(bad); e == nil {
		t.Fatal("extra HTML accepted")
	}
}
func TestScriptAndMarkerPayload(t *testing.T) {
	v := testutil.Spec()
	model.M(v["normative"])["summary"] = `</script><script>alert(1)</script><!-- CA:BEGIN:FAKE -->`
	d := testutil.Seal(t, v)
	b, e := render.Render(d)
	if e != nil {
		t.Fatal(e)
	}
	if bytes.Contains(b, []byte("<script>alert")) {
		t.Fatal("unescaped payload")
	}
	if _, e = render.Parse(b); e != nil {
		t.Fatal(e)
	}
}
func TestSafeBrand(t *testing.T) {
	if e := render.CheckLogo(render.DefaultLogo()); e != nil {
		t.Fatal(e)
	}
	for _, s := range []string{`<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"></svg>`, `<svg><script/></svg>`, `<svg><image href="https://x"/></svg>`, `<!DOCTYPE svg><svg/>`, `<svg><path fill="url(https://x)"/></svg>`, `<svg><foreignObject/></svg>`, `<svg width="100000"/>`, `<svg><path fill="url(#absent)"/></svg>`} {
		if _, e := render.Logo("image/svg+xml", []byte(s)); e == nil {
			t.Errorf("unsafe logo: %s", s)
		}
	}
	if e := render.CheckLogo("data:image/png;base64," + base64.StdEncoding.EncodeToString([]byte("fake"))); e == nil {
		t.Fatal("fake PNG accepted")
	}
}

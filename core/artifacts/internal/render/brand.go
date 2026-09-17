package render

import (
	"bytes"
	"encoding/base64"
	"encoding/xml"
	"fmt"
	"image"
	_ "image/jpeg"
	_ "image/png"
	"io"
	"regexp"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

const MaxLogoBytes = 256 * 1024

var localPaint = regexp.MustCompile(`^url\(#[A-Za-z][A-Za-z0-9_-]*\)$`)
var allowedElements = wordSet("svg g path rect circle ellipse line polyline polygon text tspan title desc defs linearGradient radialGradient stop")
var allowedAttrs = wordSet("xmlns viewBox width height role aria-label aria-hidden id d x y x1 y1 x2 y2 cx cy r rx ry points fill fill-opacity fill-rule stroke stroke-width stroke-linecap stroke-linejoin stroke-opacity opacity transform font-family font-size font-weight letter-spacing text-anchor gradientUnits gradientTransform offset stop-color stop-opacity preserveAspectRatio data-brand-element")

func wordSet(s string) map[string]bool {
	m := map[string]bool{}
	for _, s := range strings.Fields(s) {
		m[s] = true
	}
	return m
}
func Logo(mime string, b []byte) (string, error) {
	if len(b) == 0 || len(b) > MaxLogoBytes {
		return "", fault.New("INVALID_BRAND", "logo must contain 1..262144 bytes")
	}
	switch mime {
	case "image/png", "image/jpeg":
		c, f, e := image.DecodeConfig(bytes.NewReader(b))
		expected := "png"
		if mime == "image/jpeg" {
			expected = "jpeg"
		}
		if e != nil || f != expected || c.Width < 1 || c.Height < 1 || c.Width > 4096 || c.Height > 4096 || c.Width*c.Height > 4000000 {
			return "", fault.New("INVALID_BRAND", "invalid or oversized raster logo")
		}
	case "image/svg+xml":
		if e := svg(b); e != nil {
			return "", e
		}
	default:
		return "", fault.New("INVALID_BRAND", "logo type must be SVG, PNG or JPEG")
	}
	return "data:" + mime + ";base64," + base64.StdEncoding.EncodeToString(b), nil
}
func CheckLogo(uri string) error {
	prefix, body, ok := strings.Cut(uri, ";base64,")
	if !ok || !strings.HasPrefix(prefix, "data:") {
		return fault.New("INVALID_BRAND", "expected a base64 data image")
	}
	b, e := base64.StdEncoding.Strict().DecodeString(body)
	if e != nil {
		return fault.New("INVALID_BRAND", "malformed logo encoding")
	}
	normalized, e := Logo(strings.TrimPrefix(prefix, "data:"), b)
	if e != nil {
		return e
	}
	if uri != normalized {
		return fault.New("INVALID_BRAND", "noncanonical logo encoding")
	}
	return nil
}
func svg(b []byte) error {
	dec := xml.NewDecoder(bytes.NewReader(b))
	dec.Strict = true
	depth, n, roots := 0, 0, 0
	ids := map[string]bool{}
	uses := []string{}
	bad := func() error {
		return fault.New("INVALID_BRAND", "SVG must be a bounded static image with no scripts, external resources, entities, styles or event handlers")
	}
	for {
		t, e := dec.Token()
		if e == io.EOF {
			break
		}
		if e != nil {
			return bad()
		}
		n++
		if n > 10000 {
			return bad()
		}
		switch v := t.(type) {
		case xml.StartElement:
			if depth == 0 {
				roots++
				if roots != 1 || v.Name.Local != "svg" {
					return bad()
				}
			}
			depth++
			if depth > 32 || !allowedElements[v.Name.Local] || (v.Name.Space != "" && v.Name.Space != "http://www.w3.org/2000/svg") {
				return bad()
			}
			seen := map[string]bool{}
			for _, a := range v.Attr {
				if seen[a.Name.Local] {
					return bad()
				}
				seen[a.Name.Local] = true
				if !allowedAttrs[a.Name.Local] || (a.Name.Space != "" && a.Name.Local != "xmlns") {
					return bad()
				}
				s := strings.TrimSpace(a.Value)
				lower := strings.ToLower(s)
				if strings.ContainsAny(s, "<>") || strings.Contains(lower, "javascript:") || strings.Contains(lower, "data:") || strings.Contains(lower, "http:") || strings.Contains(lower, "https:") {
					if a.Name.Local != "xmlns" || s != "http://www.w3.org/2000/svg" {
						return bad()
					}
				}
				if strings.Contains(lower, "url") {
					if !localPaint.MatchString(s) {
						return bad()
					}
					uses = append(uses, s[5:len(s)-1])
				}
				if a.Name.Local == "id" {
					if ids[s] || !regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_-]*$`).MatchString(s) {
						return bad()
					}
					ids[s] = true
				}
				if (a.Name.Local == "width" || a.Name.Local == "height") && depth == 1 {
					var x float64
					if _, e := fmt.Sscan(s, &x); e != nil || x <= 0 || x > 4096 {
						return bad()
					}
				}
			}
		case xml.EndElement:
			depth--
		case xml.Directive:
			return bad()
		case xml.ProcInst:
			return bad()
		case xml.CharData:
			if depth == 0 && strings.TrimSpace(string(v)) != "" {
				return bad()
			}
		}
	}
	if roots != 1 || depth != 0 {
		return bad()
	}
	for _, id := range uses {
		if !ids[id] {
			return bad()
		}
	}
	return nil
}

// Package canonical implements the declared RFC 8785-compatible safe-integer
// subset. Floating point, exponent notation, lone surrogates and duplicate keys
// are deliberately rejected; this is not a general-purpose JCS implementation.
package canonical

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"sort"
	"strconv"
	"strings"
	"unicode/utf16"
	"unicode/utf8"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
)

const MaxBytes = 8 * 1024 * 1024
const MaxDepth = 64
const SafeInteger int64 = 9007199254740991

type parser struct {
	b   []byte
	pos int
}

func Decode(b []byte) (any, error) {
	if len(b) > MaxBytes {
		return nil, fault.New("FILE_TOO_LARGE", "JSON exceeds 8 MiB")
	}
	if !utf8.Valid(b) {
		return nil, fault.New("INVALID_UNICODE", "invalid UTF-8")
	}
	p := parser{b: b}
	v, err := p.value(0)
	if err != nil {
		return nil, err
	}
	p.space()
	if p.pos != len(b) {
		return nil, p.fail("TRAILING_JSON")
	}
	return v, nil
}
func Read(r io.Reader) (any, error) {
	b, e := io.ReadAll(io.LimitReader(r, MaxBytes+1))
	if e != nil {
		return nil, e
	}
	return Decode(b)
}
func Object(b []byte) (map[string]any, error) {
	v, e := Decode(b)
	if e != nil {
		return nil, e
	}
	m, ok := v.(map[string]any)
	if !ok {
		return nil, fault.New("INVALID_JSON", "expected object")
	}
	return m, nil
}
func (p *parser) fail(code string) error {
	return fault.New(code, fmt.Sprintf("JSON rejected at byte %d", p.pos))
}
func (p *parser) space() {
	for p.pos < len(p.b) && strings.ContainsRune(" \t\r\n", rune(p.b[p.pos])) {
		p.pos++
	}
}
func (p *parser) value(depth int) (any, error) {
	if depth > MaxDepth {
		return nil, p.fail("MAX_DEPTH")
	}
	p.space()
	if p.pos >= len(p.b) {
		return nil, p.fail("INVALID_JSON")
	}
	switch p.b[p.pos] {
	case '{':
		p.pos++
		p.space()
		m := map[string]any{}
		if p.take('}') {
			return m, nil
		}
		for {
			p.space()
			if p.pos >= len(p.b) || p.b[p.pos] != '"' {
				return nil, p.fail("INVALID_JSON")
			}
			k, e := p.str()
			if e != nil {
				return nil, e
			}
			if _, ok := m[k]; ok {
				return nil, p.fail("DUPLICATE_KEY")
			}
			p.space()
			if !p.take(':') {
				return nil, p.fail("INVALID_JSON")
			}
			v, e := p.value(depth + 1)
			if e != nil {
				return nil, e
			}
			m[k] = v
			p.space()
			if p.take('}') {
				return m, nil
			}
			if !p.take(',') {
				return nil, p.fail("INVALID_JSON")
			}
		}
	case '[':
		p.pos++
		p.space()
		a := []any{}
		if p.take(']') {
			return a, nil
		}
		for {
			v, e := p.value(depth + 1)
			if e != nil {
				return nil, e
			}
			a = append(a, v)
			p.space()
			if p.take(']') {
				return a, nil
			}
			if !p.take(',') {
				return nil, p.fail("INVALID_JSON")
			}
		}
	case '"':
		return p.str()
	case 'n':
		if p.literal("null") {
			return nil, nil
		}
	case 't':
		if p.literal("true") {
			return true, nil
		}
	case 'f':
		if p.literal("false") {
			return false, nil
		}
	default:
		start := p.pos
		if p.take('-') && p.pos == len(p.b) {
			return nil, p.fail("INVALID_NUMBER")
		}
		if p.pos < len(p.b) && p.b[p.pos] >= '0' && p.b[p.pos] <= '9' {
			if p.b[p.pos] == '0' {
				p.pos++
			} else {
				for p.pos < len(p.b) && p.b[p.pos] >= '0' && p.b[p.pos] <= '9' {
					p.pos++
				}
			}
			if p.pos < len(p.b) && strings.ContainsRune(".eE0123456789", rune(p.b[p.pos])) {
				return nil, p.fail("INVALID_NUMBER")
			}
			n, e := strconv.ParseInt(string(p.b[start:p.pos]), 10, 64)
			if e != nil || n > SafeInteger || n < -SafeInteger {
				return nil, p.fail("INVALID_NUMBER")
			}
			return n, nil
		}
	}
	return nil, p.fail("INVALID_JSON")
}
func (p *parser) literal(s string) bool {
	if bytes.HasPrefix(p.b[p.pos:], []byte(s)) {
		p.pos += len(s)
		return true
	}
	return false
}
func (p *parser) take(b byte) bool {
	if p.pos < len(p.b) && p.b[p.pos] == b {
		p.pos++
		return true
	}
	return false
}
func (p *parser) hex4() (uint16, error) {
	if len(p.b)-p.pos < 4 {
		return 0, p.fail("INVALID_UNICODE")
	}
	s := string(p.b[p.pos : p.pos+4])
	n, e := strconv.ParseUint(s, 16, 16)
	if e != nil {
		return 0, p.fail("INVALID_UNICODE")
	}
	p.pos += 4
	return uint16(n), nil
}
func (p *parser) str() (string, error) {
	if !p.take('"') {
		return "", p.fail("INVALID_JSON")
	}
	var b strings.Builder
	for p.pos < len(p.b) {
		c := p.b[p.pos]
		p.pos++
		switch {
		case c == '"':
			return b.String(), nil
		case c < 0x20:
			return "", p.fail("INVALID_JSON")
		case c == '\\':
			if p.pos >= len(p.b) {
				return "", p.fail("INVALID_JSON")
			}
			e := p.b[p.pos]
			p.pos++
			switch e {
			case '"', '\\', '/':
				b.WriteByte(e)
			case 'b':
				b.WriteByte('\b')
			case 'f':
				b.WriteByte('\f')
			case 'n':
				b.WriteByte('\n')
			case 'r':
				b.WriteByte('\r')
			case 't':
				b.WriteByte('\t')
			case 'u':
				u, err := p.hex4()
				if err != nil {
					return "", err
				}
				r := rune(u)
				if u >= 0xD800 && u <= 0xDBFF {
					if !p.take('\\') || !p.take('u') {
						return "", p.fail("INVALID_UNICODE")
					}
					v, err := p.hex4()
					if err != nil || v < 0xDC00 || v > 0xDFFF {
						return "", p.fail("INVALID_UNICODE")
					}
					r = utf16.DecodeRune(rune(u), rune(v))
				} else if u >= 0xDC00 && u <= 0xDFFF {
					return "", p.fail("INVALID_UNICODE")
				}
				b.WriteRune(r)
			default:
				return "", p.fail("INVALID_JSON")
			}
		default:
			b.WriteByte(c)
		}
	}
	return "", p.fail("INVALID_JSON")
}
func appendString(b *bytes.Buffer, s string) error {
	if !utf8.ValidString(s) {
		return fault.New("INVALID_UNICODE", "invalid string")
	}
	b.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			b.WriteString(`\"`)
		case '\\':
			b.WriteString(`\\`)
		case '\b':
			b.WriteString(`\b`)
		case '\f':
			b.WriteString(`\f`)
		case '\n':
			b.WriteString(`\n`)
		case '\r':
			b.WriteString(`\r`)
		case '\t':
			b.WriteString(`\t`)
		default:
			if r < 0x20 {
				fmt.Fprintf(b, `\u%04x`, r)
			} else {
				b.WriteRune(r)
			}
		}
	}
	b.WriteByte('"')
	return nil
}
func lessUTF16(a, b string) bool {
	aa := utf16.Encode([]rune(a))
	bb := utf16.Encode([]rune(b))
	for i := 0; i < len(aa) && i < len(bb); i++ {
		if aa[i] != bb[i] {
			return aa[i] < bb[i]
		}
	}
	return len(aa) < len(bb)
}
func Keys(m map[string]any) []string {
	ks := make([]string, 0, len(m))
	for k := range m {
		ks = append(ks, k)
	}
	sort.Slice(ks, func(i, j int) bool { return lessUTF16(ks[i], ks[j]) })
	return ks
}
func Marshal(v any) ([]byte, error) {
	var b bytes.Buffer
	err := emit(&b, v, 0)
	if err != nil {
		return nil, err
	}
	if b.Len() > MaxBytes {
		return nil, fault.New("FILE_TOO_LARGE", "canonical JSON exceeds 8 MiB")
	}
	return b.Bytes(), nil
}
func emit(b *bytes.Buffer, v any, d int) error {
	if d > MaxDepth {
		return fault.New("MAX_DEPTH", "canonical nesting exceeds 64")
	}
	switch x := v.(type) {
	case nil:
		b.WriteString("null")
	case bool:
		if x {
			b.WriteString("true")
		} else {
			b.WriteString("false")
		}
	case string:
		return appendString(b, x)
	case int:
		return emit(b, int64(x), d)
	case int64:
		if x > SafeInteger || x < -SafeInteger {
			return fault.New("INVALID_NUMBER", "integer outside safe range")
		}
		b.WriteString(strconv.FormatInt(x, 10))
	case []string:
		a := make([]any, len(x))
		for i, s := range x {
			a[i] = s
		}
		return emit(b, a, d)
	case []any:
		b.WriteByte('[')
		for i, item := range x {
			if i > 0 {
				b.WriteByte(',')
			}
			if e := emit(b, item, d+1); e != nil {
				return e
			}
		}
		b.WriteByte(']')
	case map[string]any:
		b.WriteByte('{')
		for i, k := range Keys(x) {
			if i > 0 {
				b.WriteByte(',')
			}
			if e := appendString(b, k); e != nil {
				return e
			}
			b.WriteByte(':')
			if e := emit(b, x[k], d+1); e != nil {
				return e
			}
		}
		b.WriteByte('}')
	default:
		return fault.New("UNSUPPORTED_VALUE", fmt.Sprintf("canonical encoder rejects %T", v))
	}
	return nil
}
func Hash(v any) (string, error) {
	b, e := Marshal(v)
	if e != nil {
		return "", e
	}
	return BytesHash(b), nil
}
func BytesHash(b []byte) string { h := sha256.Sum256(b); return hex.EncodeToString(h[:]) }
func Clone(v map[string]any) (map[string]any, error) {
	b, e := Marshal(v)
	if e != nil {
		return nil, e
	}
	return Object(b)
}

// Package schema evaluates the closed JSON Schema vocabulary used by the
// packaged models. It is deliberately not a general JSON Schema implementation.
// Unknown keywords or remote references fail compilation, never silently pass.
package schema

import (
	"embed"
	"fmt"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/kind"
	"regexp"
	"strings"
	"sync"
	"unicode/utf8"
)

//go:embed *.schema.json
var source embed.FS
var once sync.Once
var registry map[string]any
var initialization error
var vocabulary = map[string]bool{}

func names() []string {
	out := []string{"common"}
	for _, contract := range kind.All() {
		out = append(out, contract.Schema)
	}
	return out
}

func initRegistry() {
	vocabulary = map[string]bool{}
	for _, k := range strings.Fields("$schema $id title description $defs $ref type const enum oneOf anyOf allOf properties required additionalProperties propertyNames items minItems maxItems uniqueItems minLength maxLength pattern minimum maximum") {
		vocabulary[k] = true
	}
	registry = map[string]any{}
	for _, name := range names() {
		b, e := source.ReadFile(name + ".schema.json")
		if e != nil {
			initialization = e
			return
		}
		v, e := canonical.Decode(b)
		if e != nil {
			initialization = e
			return
		}
		d, ok := v.(map[string]any)
		if !ok {
			initialization = fmt.Errorf("schema %s is not an object", name)
			return
		}
		registry[d["$id"].(string)] = v
		registry[name] = v
	}
	for _, name := range names() {
		if e := check(registry[name], 0); e != nil {
			initialization = e
			return
		}
	}
}
func check(v any, depth int) error {
	if depth > 128 {
		return fmt.Errorf("schema nesting too deep")
	}
	if _, ok := v.(bool); ok {
		return nil
	}
	m, ok := v.(map[string]any)
	if !ok {
		return fmt.Errorf("invalid packaged schema")
	}
	for k, v := range m {
		if !vocabulary[k] {
			return fmt.Errorf("unsupported schema keyword %s", k)
		}
		switch k {
		case "$ref":
			if _, e := resolve(v.(string)); e != nil {
				return e
			}
		case "pattern":
			if _, e := regexp.Compile(v.(string)); e != nil {
				return e
			}
		case "$defs", "properties":
			for _, s := range v.(map[string]any) {
				if e := check(s, depth+1); e != nil {
					return e
				}
			}
		case "items", "additionalProperties", "propertyNames":
			if e := check(v, depth+1); e != nil {
				return e
			}
		case "oneOf", "anyOf", "allOf":
			for _, s := range v.([]any) {
				if e := check(s, depth+1); e != nil {
					return e
				}
			}
		}
	}
	return nil
}
func resolve(ref string) (any, error) {
	parts := strings.SplitN(ref, "#", 2)
	v, ok := registry[parts[0]]
	if !ok {
		return nil, fmt.Errorf("schema reference is not packaged: %s", parts[0])
	}
	if len(parts) == 1 || parts[1] == "" {
		return v, nil
	}
	if !strings.HasPrefix(parts[1], "/") {
		return nil, fmt.Errorf("unsupported schema fragment")
	}
	for _, part := range strings.Split(parts[1][1:], "/") {
		m, ok := v.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("invalid schema fragment")
		}
		part = strings.ReplaceAll(strings.ReplaceAll(part, "~1", "/"), "~0", "~")
		v, ok = m[part]
		if !ok {
			return nil, fmt.Errorf("missing schema fragment")
		}
	}
	return v, nil
}
func Get(name, fragment string) (any, error) {
	once.Do(initRegistry)
	if initialization != nil {
		return nil, initialization
	}
	v, ok := registry[name]
	if !ok {
		return nil, fault.New("UNKNOWN_SCHEMA", "select a registered artifact schema or common")
	}
	if fragment != "" {
		return resolve(v.(map[string]any)["$id"].(string) + "#" + fragment)
	}
	return v, nil
}
func Validate(kindName string, v any) []fault.Error {
	once.Do(initRegistry)
	if initialization != nil {
		return []fault.Error{{Code: "SCHEMA_PACKAGE_INVALID", Message: initialization.Error()}}
	}
	contract, ok := kind.Lookup(kindName)
	if !ok {
		return []fault.Error{{Code: "UNSUPPORTED_VERSION", Message: "unsupported artifact kind"}}
	}
	s := registry[contract.Schema]
	var out []fault.Error
	validate(s, v, "", 0, &out)
	return out
}
func ValidateWith(s any, v any) []fault.Error {
	once.Do(initRegistry)
	if initialization != nil {
		return []fault.Error{{Code: "SCHEMA_PACKAGE_INVALID", Message: initialization.Error()}}
	}
	if e := check(s, 0); e != nil {
		return []fault.Error{{Code: "SCHEMA_PACKAGE_INVALID", Message: e.Error()}}
	}
	var out []fault.Error
	validate(s, v, "", 0, &out)
	return out
}
func add(out *[]fault.Error, path, msg string) {
	if len(*out) < 128 {
		*out = append(*out, fault.Error{Code: "INVALID_MODEL", Field: path, Message: msg})
	}
}
func typeOK(t string, v any) bool {
	switch t {
	case "null":
		return v == nil
	case "boolean":
		_, ok := v.(bool)
		return ok
	case "string":
		_, ok := v.(string)
		return ok
	case "integer":
		_, ok := v.(int64)
		return ok
	case "object":
		_, ok := v.(map[string]any)
		return ok
	case "array":
		_, ok := v.([]any)
		return ok
	}
	return false
}
func equal(a, b any) bool {
	x, e := canonical.Marshal(a)
	if e != nil {
		return false
	}
	y, e := canonical.Marshal(b)
	return e == nil && string(x) == string(y)
}
func esc(k string) string { return strings.ReplaceAll(strings.ReplaceAll(k, "~", "~0"), "/", "~1") }
func validate(s, v any, path string, depth int, out *[]fault.Error) {
	if len(*out) >= 128 {
		return
	}
	if depth > 128 {
		add(out, path, "schema recursion limit")
		return
	}
	if b, ok := s.(bool); ok {
		if !b {
			add(out, path, "additional value not permitted")
		}
		return
	}
	m := s.(map[string]any)
	if ref, ok := m["$ref"].(string); ok {
		r, e := resolve(ref)
		if e != nil {
			add(out, path, e.Error())
			return
		}
		validate(r, v, path, depth+1, out)
	}
	if t, ok := m["type"]; ok {
		valid := false
		if ts, ok := t.(string); ok {
			valid = typeOK(ts, v)
		} else {
			for _, ts := range t.([]any) {
				if typeOK(ts.(string), v) {
					valid = true
				}
			}
		}
		if !valid {
			add(out, path, "incorrect value type")
			return
		}
	}
	if c, ok := m["const"]; ok && !equal(c, v) {
		add(out, path, "value does not match constant")
	}
	if es, ok := m["enum"].([]any); ok {
		valid := false
		for _, e := range es {
			if equal(e, v) {
				valid = true
			}
		}
		if !valid {
			add(out, path, "value outside closed enumeration")
		}
	}
	for _, key := range []string{"oneOf", "anyOf", "allOf"} {
		if alternatives, ok := m[key].([]any); ok {
			count := 0
			for _, alt := range alternatives {
				var candidate []fault.Error
				validate(alt, v, path, depth+1, &candidate)
				if len(candidate) == 0 {
					count++
				}
			}
			if (key == "oneOf" && count != 1) || (key == "anyOf" && count == 0) || (key == "allOf" && count != len(alternatives)) {
				add(out, path, "value fails "+key+" alternatives")
			}
		}
	}
	switch x := v.(type) {
	case map[string]any:
		props, _ := m["properties"].(map[string]any)
		if required, ok := m["required"].([]any); ok {
			for _, r := range required {
				if _, found := x[r.(string)]; !found {
					add(out, path+"/"+esc(r.(string)), "required field absent")
				}
			}
		}
		for _, k := range canonical.Keys(x) {
			value := x[k]
			p := path + "/" + esc(k)
			if ps, ok := m["propertyNames"]; ok {
				validate(ps, k, p, depth+1, out)
			}
			if sub, ok := props[k]; ok {
				validate(sub, value, p, depth+1, out)
			} else if sub, ok := m["additionalProperties"]; ok {
				validate(sub, value, p, depth+1, out)
			}
		}
	case []any:
		if n, ok := m["minItems"].(int64); ok && int64(len(x)) < n {
			add(out, path, "too few items")
		}
		if n, ok := m["maxItems"].(int64); ok && int64(len(x)) > n {
			add(out, path, "too many items")
		}
		if m["uniqueItems"] == true {
			seen := map[string]bool{}
			for _, item := range x {
				h, e := canonical.Hash(item)
				if e != nil {
					add(out, path, e.Error())
					continue
				}
				if seen[h] {
					add(out, path, "duplicate array value")
					break
				}
				seen[h] = true
			}
		}
		if items, ok := m["items"]; ok {
			for i, item := range x {
				validate(items, item, fmt.Sprintf("%s/%d", path, i), depth+1, out)
			}
		}
	case string:
		n := int64(utf8.RuneCountInString(x))
		if min, ok := m["minLength"].(int64); ok && n < min {
			add(out, path, "string too short")
		}
		if max, ok := m["maxLength"].(int64); ok && n > max {
			add(out, path, "string too long")
		}
		if pattern, ok := m["pattern"].(string); ok {
			r, e := regexp.Compile(pattern)
			if e != nil || !r.MatchString(x) {
				add(out, path, "string fails pattern")
			}
		}
	case int64:
		if n, ok := m["minimum"].(int64); ok && x < n {
			add(out, path, "integer below minimum")
		}
		if n, ok := m["maximum"].(int64); ok && x > n {
			add(out, path, "integer above maximum")
		}
	}
}

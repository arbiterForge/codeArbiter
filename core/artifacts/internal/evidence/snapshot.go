// Package evidence builds explicit source-input identities. Presentation and
// progress are excluded only after their authoritative HTML has been validated.
package evidence

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/observation"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
	"os"
	"path"
	"runtime"
	"sort"
	"strings"
)

const MaxInputFile = 32 << 20
const MaxInputTotal = 256 << 20
const MaxInputEntries = 50000

func internalOutputs(f *store.FS) (map[string]bool, error) {
	out, e := f.Infrastructure()
	if e != nil {
		return nil, e
	}
	dirs, e := f.List(authority.Root)
	if os.IsNotExist(e) {
		return out, nil
	}
	if e != nil {
		return nil, e
	}
	for _, d := range dirs {
		if !d.IsDir() {
			if d.Name() == "store.lock" {
				// The engine already holds this file's native lock while it
				// snapshots inputs. Reopening it can fail with a sharing error on
				// Windows even though the lock is valid and empty. Stat through the
				// rooted store instead: contents are forbidden, and List above has
				// already rejected links/reparse points.
				info, e := f.Stat(authority.Root + "/store.lock")
				if e != nil || !info.Mode().IsRegular() || info.Size() != 0 {
					return nil, fault.New("INVALID_OUTPUT", "invalid native cooperative lock file")
				}
				out[authority.Root+"/store.lock"] = true
				continue
			}
			return nil, fault.New("UNRECOGNIZED_OUTPUT", "file in reserved artifact output root")
		}
		switch d.Name() {
		case "transactions", "history":
			continue
		case "authority-sources", "events", "receipts", "context-tokens", "evidence-contexts", "observations", "farm-bindings", "farm-seals", "farm-markers":
		default:
			return nil, fault.New("UNRECOGNIZED_OUTPUT", "unrecognized reserved output directory")
		}
		entries, e := f.List(authority.Root + "/" + d.Name())
		if e != nil {
			return nil, e
		}
		for _, entry := range entries {
			p := authority.Root + "/" + d.Name() + "/" + entry.Name()
			if entry.IsDir() {
				return nil, fault.New("UNRECOGNIZED_OUTPUT", "nested reserved output directory")
			}
			b, e := f.Read(p, canonical.MaxBytes)
			if e != nil {
				return nil, e
			}
			h := strings.TrimSuffix(entry.Name(), ".json")
			if !strings.HasSuffix(entry.Name(), ".json") || canonical.BytesHash(b) != h {
				return nil, fault.New("INVALID_OUTPUT", "generated output filename does not match its bytes")
			}
			if d.Name() == "receipts" {
				// Historical v0.1 receipts are valid inventory inputs but cannot
				// confer current authority. Authority-consuming paths use Load,
				// which continues to reject them until freshly attested.
				if _, e := authority.Inspect(f, p); e != nil {
					return nil, e
				}
			} else if d.Name() == "events" || d.Name() == "authority-sources" {
				v, e := canonical.Object(b)
				if e != nil {
					return nil, e
				}
				if es := schema.ValidateWith(authority.EventSchema(), v); len(es) > 0 {
					return nil, &es[0]
				}
			} else if d.Name() == "context-tokens" {
				v, e := canonical.Object(b)
				if e != nil || model.S(v["format"]) != "codearbiter.context-token/0.1.0" {
					return nil, fault.New("INVALID_OUTPUT", "invalid generated context receipt")
				}
			} else if d.Name() == "evidence-contexts" || d.Name() == "observations" {
				v, e := canonical.Object(b)
				if e != nil {
					return nil, fault.New("INVALID_OUTPUT", "invalid generated evidence object")
				}
				contract := observation.ContextSchema()
				if d.Name() == "observations" {
					contract = observation.InspectionSchema()
				}
				if es := schema.ValidateWith(contract, v); len(es) > 0 {
					return nil, &es[0]
				}
			} else {
				v, e := canonical.Object(b)
				expected := "codearbiter.farm-binding/0.1.0"
				if d.Name() == "farm-seals" {
					expected = "codearbiter.farm-seal/0.1.0"
				} else if d.Name() == "farm-markers" {
					expected = "codearbiter.farm-marker/0.1.0"
				}
				if e != nil || model.S(v["format"]) != expected {
					return nil, fault.New("INVALID_OUTPUT", "invalid generated farm receipt")
				}
				if d.Name() == "farm-markers" {
					projection := model.S(v["projection_path"])
					if len(v) != 2 || !validate.Path(projection, false) || !strings.HasPrefix(projection, ".codearbiter/plans/") || !strings.HasSuffix(projection, ".plan.json") || strings.Count(projection, "/") != 2 {
						return nil, fault.New("INVALID_OUTPUT", "farm marker names an unsafe projection")
					}
				}
				if d.Name() == "farm-bindings" {
					projection := model.S(v["projection_path"])
					if !validate.Path(projection, false) || !strings.HasPrefix(projection, ".codearbiter/plans/") || !strings.HasSuffix(projection, ".plan.json") {
						return nil, fault.New("INVALID_OUTPUT", "farm binding names an unsafe projection")
					}
					projectionBytes, readErr := f.Read(projection, canonical.MaxBytes)
					if readErr == nil {
						projectionValue, parseErr := canonical.Object(projectionBytes)
						if parseErr == nil {
							base, cloneErr := canonical.Clone(projectionValue)
							if cloneErr == nil {
								meta := model.M(base["meta"])
								delete(meta, "model")
								delete(meta, "apiBaseUrl")
								baseBytes, marshalErr := canonical.Marshal(base)
								if marshalErr == nil && canonical.BytesHash(baseBytes) == model.S(v["base_sha256"]) {
									out[projection] = true
								}
							}
						}
					}
				}
			}
			out[p] = true
		}
	}
	return out, nil
}
func snapshotOnce(f *store.FS, plan *model.Document) (map[string]any, error) {
	outputs, e := internalOutputs(f)
	if e != nil {
		return nil, e
	}
	roots := []string{"."}
	excludes := []string{}
	if plan != nil {
		if policy := model.M(plan.Norm()["verification_inputs"]); policy != nil {
			roots = model.Strings(policy["roots"])
			excludes = model.Strings(policy["exclude_directories"])
		}
	}
	for _, p := range roots {
		if !validate.Path(p, true) || p == ".git" || strings.HasPrefix(p, ".git/") {
			return nil, fault.New("INVALID_INPUT_POLICY", "unsafe input root")
		}
	}
	for _, p := range excludes {
		if !validate.Path(p, false) || p == ".codearbiter" || strings.HasPrefix(p, ".codearbiter/") {
			return nil, fault.New("INVALID_INPUT_POLICY", "exclude directories must be explicit non-governance repo paths")
		}
	}
	excluded := func(p string) bool {
		if p == ".git" {
			return true
		}
		for _, x := range excludes {
			if p == x {
				return true
			}
		}
		return false
	}
	items := map[string]any{}
	count, total := 0, 0
	var walk func(string) error
	walk = func(rel string) error {
		// Reserved output membership is validated above and omitted as a whole only
		// after EVERY contained file has a recognized output contract.
		if rel == authority.Root {
			return nil
		}
		entries, e := f.ListUnfollowed(rel)
		if e != nil {
			return e
		}
		names := []any{}
		for _, entry := range entries {
			p := path.Join(rel, entry.Name())
			if p == authority.Root {
				continue
			}
			if (entry.IsDir() || entry.Type()&os.ModeSymlink != 0) && excluded(p) {
				continue
			}
			if p == ".git" {
				continue
			}
			if !validate.Path(p, false) {
				return fault.New("INVALID_PATH", "input path is not portable")
			}
			count++
			if count > MaxInputEntries {
				return fault.New("MAX_INPUTS", "input manifest exceeds 50000 entries")
			}
			if outputs[p] {
				continue
			}
			names = append(names, entry.Name())
			if entry.IsDir() {
				if e = walk(p); e != nil {
					return e
				}
				continue
			}
			b, e := f.Read(p, MaxInputFile)
			if e != nil {
				return e
			}
			total += len(b)
			if total > MaxInputTotal {
				return fault.New("MAX_INPUTS", "input bytes exceed 256 MiB; approve an explicit input policy")
			}
			kind := "bytes"
			h := canonical.BytesHash(b)
			if strings.HasSuffix(p, ".html") && (strings.HasPrefix(p, ".codearbiter/specs/") || strings.HasPrefix(p, ".codearbiter/plans/")) {
				d, e := render.Parse(b)
				if e != nil {
					return e
				}
				kind = "artifact_normative"
				h = d.NormHash()
			}
			info, e := f.Stat(p)
			if e != nil {
				return e
			}
			items[p] = map[string]any{"kind": kind, "sha256": h, "executable": info.Mode()&0111 != 0}
		}
		items[rel+"/"] = map[string]any{"kind": "directory", "members": names}
		return nil
	}
	sort.Strings(roots)
	for _, root := range roots {
		if root != "." {
			b, e := f.Read(root, MaxInputFile)
			if e == nil {
				count++
				total += len(b)
				if count > MaxInputEntries || total > MaxInputTotal {
					return nil, fault.New("MAX_INPUTS", "explicit input roots exceed manifest limits")
				}
				info, err := f.Stat(root)
				if err != nil {
					return nil, err
				}
				items[root] = map[string]any{"kind": "bytes", "sha256": canonical.BytesHash(b), "executable": info.Mode()&0111 != 0}
				continue
			}
		}
		if e = walk(root); e != nil {
			return nil, e
		}
	}
	// Always include canonical normative artifacts even when scoped roots omit
	// their directory. This also makes source-definition changes stale evidence.
	for _, kind := range []string{"specs", "plans"} {
		dir := ".codearbiter/" + kind
		entries, e := f.List(dir)
		if os.IsNotExist(e) {
			continue
		}
		if e != nil {
			return nil, e
		}
		for _, entry := range entries {
			if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".html") {
				continue
			}
			p := dir + "/" + entry.Name()
			b, e := f.Read(p, canonical.MaxBytes)
			if e != nil {
				return nil, e
			}
			d, e := render.Parse(b)
			if e != nil {
				return nil, e
			}
			items[p] = map[string]any{"kind": "artifact_normative", "sha256": d.NormHash()}
		}
	}
	manifest := map[string]any{"format": "codearbiter.verification-inputs/0.1.0", "engine": render.Version, "platform": runtime.GOOS + "/" + runtime.GOARCH, "engine_toolchain": runtime.Version(), "roots": model.List(roots...), "exclude_directories": model.List(excludes...), "entries": items}
	h, e := canonical.Hash(manifest)
	if e != nil {
		return nil, e
	}
	return map[string]any{"sha256": h, "manifest": manifest}, nil
}

// Two complete, identical passes reject ordinary concurrent-editor changes.
// This does not claim protection against a same-user adversary performing ABA
// writes; source editors are outside the cooperative artifact-writer lock.
func Snapshot(f *store.FS, plan *model.Document) (map[string]any, error) {
	a, e := snapshotOnce(f, plan)
	if e != nil {
		return nil, e
	}
	b, e := snapshotOnce(f, plan)
	if e != nil {
		return nil, e
	}
	if a["sha256"] != b["sha256"] {
		return nil, fault.New("CONCURRENT_CHANGE", "verification inputs changed during snapshot collection")
	}
	return b, nil
}

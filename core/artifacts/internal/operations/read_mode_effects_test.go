//go:build linux || darwin || windows

package operations

import (
	"io/fs"
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"
	"time"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

// readModeTree observes logical names and bytes, not unspecified access times.
// Every fixture is an owned temporary root returned by freshCheckout.
func readModeTree(t *testing.T, root string) map[string]string {
	t.Helper()
	out := map[string]string{}
	err := filepath.WalkDir(root, func(name string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(root, name)
		if err != nil {
			return err
		}
		if rel == "." {
			return nil
		}
		rel = filepath.ToSlash(rel)
		if entry.IsDir() {
			out[rel] = "directory"
			return nil
		}
		info, err := entry.Info()
		if err != nil {
			return err
		}
		if !info.Mode().IsRegular() {
			t.Fatalf("fixture contains nonordinary entry %s", rel)
		}
		b, err := os.ReadFile(name)
		if err != nil {
			return err
		}
		out[rel] = "file:" + string(b)
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	return out
}

func readModeRequest(mode string) object {
	r := object{"protocol": Protocol, "artifact_id": "SPEC-EXAMPLE", "symbol": "AC-001", "budget": int64(65536)}
	if mode != "default" {
		r["mode"] = mode
	}
	return r
}

func readModeToken(t *testing.T, root string, out any) (string, string) {
	t.Helper()
	page := model.M(out)
	ticket := model.S(page["context_ticket"])
	if page["mode"] != "contextual" || page["context_complete"] != true || page["next_cursor"] != nil || !digestString(ticket) {
		t.Fatalf("contextual delivery did not complete with one receipt: %v", page)
	}
	name := ".codearbiter/.artifacts/context-tokens/" + ticket + ".json"
	b, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(name)))
	if err != nil {
		t.Fatal(err)
	}
	if canonical.BytesHash(b) != ticket {
		t.Fatal("delivery receipt name does not bind its actual bytes")
	}
	payload, err := canonical.Object(b)
	if err != nil || payload["purpose"] != "context" || payload["artifact_id"] != "SPEC-EXAMPLE" || payload["symbol"] != "AC-001" || model.I(payload["offset"]) <= 0 {
		t.Fatalf("delivery receipt has wrong subject or purpose: %v %v", payload, err)
	}
	return name, "file:" + string(b)
}

func readModeLock(t *testing.T, mode string) {
	t.Helper()
	root := freshCheckout(t)
	if _, err := Run(root, "init-store", object{"protocol": Protocol}); err != nil {
		t.Fatal(err)
	}
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	release, err := f.Lock(false, time.Second)
	if err != nil {
		t.Fatal(err)
	}
	held := true
	defer func() {
		if held {
			release()
		}
	}()
	before := readModeTree(t, root)
	out, err := Run(root, "read", readModeRequest(mode))
	if mode == "exact" {
		if err != nil || model.M(out)["mode"] != "exact" {
			t.Fatalf("exact read failed to share an existing reader lock: %v %v", out, err)
		}
	} else if fault.Code(err) != "LOCK_TIMEOUT" || out != nil {
		t.Fatalf("%s read bypassed exclusive-lock requirement: %v %v", mode, out, err)
	}
	if after := readModeTree(t, root); !reflect.DeepEqual(after, before) {
		t.Fatalf("%s locked probe changed logical names or bytes", mode)
	}
	release()
	held = false
	out, err = Run(root, "read", readModeRequest(mode))
	if err != nil {
		t.Fatalf("%s read failed after reader release: %v", mode, err)
	}
	if mode != "exact" {
		readModeToken(t, root, out)
	}
}

// One non-skipping parent executes every matrix cell and lock probe directly.
// Its parent PASS therefore cannot conceal optional skipped child cases.
func TestReadModeMetadataEffects(t *testing.T) {
	if runtime.GOOS != "linux" && runtime.GOOS != "darwin" && runtime.GOOS != "windows" {
		t.Fatalf("unsupported characterization platform %s", runtime.GOOS)
	}
	const metadata = ".codearbiter/.artifacts"
	cells := 0
	for _, present := range []bool{false, true} {
		for _, mode := range []string{"exact", "contextual", "default"} {
			root := freshCheckout(t)
			if present {
				// Linux needs no lock file; the explicit directory distinguishes
				// the present-metadata fixture without inventing a Linux mutex.
				if err := os.MkdirAll(filepath.Join(root, filepath.FromSlash(metadata)), 0700); err != nil {
					t.Fatal(err)
				}
				if _, err := Run(root, "init-store", object{"protocol": Protocol}); err != nil {
					t.Fatal(err)
				}
			}
			before := readModeTree(t, root)
			want := map[string]string{}
			for name, value := range before {
				want[name] = value
			}
			out, err := Run(root, "read", readModeRequest(mode))
			refused := runtime.GOOS == "windows" && !present && mode == "exact"
			if refused {
				if fault.Code(err) != "NO_LOCAL_STORE" || out != nil {
					t.Fatalf("%s absent/%s must refuse without initialization: %v %v", runtime.GOOS, mode, out, err)
				}
			} else {
				if err != nil {
					t.Fatalf("%s present=%v mode=%s: %v", runtime.GOOS, present, mode, err)
				}
				if runtime.GOOS != "linux" {
					want[metadata] = "directory"
					want[metadata+"/store.lock"] = "file:"
				}
				if mode == "exact" {
					page := model.M(out)
					if page["mode"] != "exact" || page["context_complete"] != false || page["context_ticket"] != nil || page["next_cursor"] != nil || model.M(page["record"])["id"] != "AC-001" {
						t.Fatalf("exact read became context delivery: %v", page)
					}
				} else {
					name, value := readModeToken(t, root, out)
					want[metadata] = "directory"
					want[metadata+"/context-tokens"] = "directory"
					want[name] = value
				}
			}
			if after := readModeTree(t, root); !reflect.DeepEqual(after, want) {
				t.Fatalf("%s present=%v mode=%s changed files beyond declared lock/token metadata: got %v want %v", runtime.GOOS, present, mode, after, want)
			}
			cells++
		}
	}
	if cells != 6 {
		t.Fatalf("incomplete mode/metadata matrix: %d", cells)
	}
	locks := 0
	for _, mode := range []string{"exact", "contextual", "default"} {
		readModeLock(t, mode)
		locks++
	}
	if locks != 3 {
		t.Fatalf("incomplete mode lock probes: %d", locks)
	}
	t.Logf("observed %s/%s: all 6 mode/metadata cells and 3 actual lock probes, no optional skips", runtime.GOOS, runtime.GOARCH)
}

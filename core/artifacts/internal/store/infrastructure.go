package store

import (
	"encoding/hex"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"os"
	"strings"
)

// Infrastructure proves each transaction/history file is known generated
// output. Unknown or orphaned files are not silently excluded from snapshots.
func (f *FS) Infrastructure() (map[string]bool, error) {
	out := map[string]bool{}
	hist := map[string]string{}
	names, e := f.List(meta + "/transactions")
	if os.IsNotExist(e) {
		names = nil
	} else if e != nil {
		return nil, e
	}
	for _, n := range names {
		p := meta + "/transactions/" + n.Name()
		if !strings.HasSuffix(p, ".json") || n.IsDir() {
			return nil, fault.New("RECOVERY_REQUIRED", "unexpected transaction staging file requires reconciliation")
		}
		id := strings.TrimSuffix(n.Name(), ".json")
		j, e := f.journal(id)
		if e != nil {
			return nil, e
		}
		if model.S(j["state"]) == "prepared" {
			return nil, fault.New("RECOVERY_REQUIRED", "pending transaction blocks input snapshots")
		}
		out[p] = true
		for _, v := range model.A(j["entries"]) {
			r := model.M(v)
			if r["before_sha256"] != nil {
				hist[model.S(r["backup"])] = model.S(r["before_sha256"])
			}
		}
	}
	names, e = f.List(meta + "/history")
	if os.IsNotExist(e) {
		names = nil
	} else if e != nil {
		return nil, e
	}
	for _, n := range names {
		p := meta + "/history/" + n.Name()
		h, ok := hist[p]
		if !ok || n.IsDir() {
			return nil, fault.New("ORPHAN_HISTORY", "unreferenced history file; preserve it and retry the original operation with identical input or inspect retained history")
		}
		b, e := f.Read(p, canonical.MaxBytes)
		if e != nil || canonical.BytesHash(b) != h {
			return nil, fault.New("CORRUPT_JOURNAL", "before-image bytes changed")
		}
		out[p] = true
		delete(hist, p)
	}
	if len(hist) > 0 {
		return nil, fault.New("CORRUPT_JOURNAL", "before-image is missing")
	}
	return out, nil
}

// PutEvent only stores immutable captured workflow data. Authority.Load still
// validates its schema and correspondence to a receipt before use.
func (f *FS) PutEvent(sha string, b []byte) error {
	if len(sha) != 64 || canonical.BytesHash(b) != sha || len(b) > 1<<20 {
		return fault.New("INVALID_EVENT", "invalid content-addressed event")
	}
	return f.createOrCompare(meta+"/events/"+sha+".json", b, 0600)
}

// PutContextToken records an engine-issued cooperative delivery receipt. The
// digest is an opaque capability only in the cooperative same-user model: it is
// not authentication and it grants no approval or filesystem authority.
func (f *FS) PutContextToken(sha string, b []byte) error {
	if !digest(sha) || canonical.BytesHash(b) != sha || len(b) > 4096 {
		return fault.New("INVALID_CURSOR", "invalid content-addressed context receipt")
	}
	return f.createOrCompare(meta+"/context-tokens/"+sha+".json", b, 0600)
}

// PutDerived records immutable, content-addressed execution metadata. Its
// allowlist is closed: farm receipts and engine-owned evidence contexts only;
// canonical planning authority remains in the HTML pair.
func (f *FS) PutDerived(kind, sha string, b []byte) error {
	if (kind != "farm-bindings" && kind != "farm-seals" && kind != "farm-markers" && kind != "evidence-contexts") || !digest(sha) || canonical.BytesHash(b) != sha || len(b) > canonical.MaxBytes {
		return fault.New("INVALID_OUTPUT", "invalid content-addressed derived receipt")
	}
	return f.createOrCompare(meta+"/"+kind+"/"+sha+".json", b, 0600)
}

func (f *FS) ContextToken(sha string) ([]byte, error) {
	if !digest(sha) {
		return nil, fault.New("INVALID_CURSOR", "context receipt must be a SHA-256 digest")
	}
	b, e := f.Read(meta+"/context-tokens/"+sha+".json", 4096)
	if os.IsNotExist(e) {
		return nil, fault.New("INVALID_CURSOR", "context receipt was not issued by the engine")
	}
	if e != nil {
		return nil, e
	}
	if canonical.BytesHash(b) != sha {
		return nil, fault.New("CORRUPT_CONTEXT_TOKEN", "context receipt filename does not match its bytes")
	}
	return b, nil
}

func digest(s string) bool {
	if len(s) != 64 {
		return false
	}
	_, e := hex.DecodeString(s)
	return e == nil
}

// PutObservation and PutAuthoritySource have closed content-addressed locations.
// Callers must validate the producer before these records confer authority.
func (f *FS) PutObservation(sha string, b []byte) error {
	if !digest(sha) || canonical.BytesHash(b) != sha || len(b) > canonical.MaxBytes {
		return fault.New("INVALID_OBSERVATION", "invalid immutable observation")
	}
	return f.createOrCompare(meta+"/observations/"+sha+".json", b, 0600)
}
func (f *FS) PutAuthoritySource(sha string, b []byte) error {
	if !digest(sha) || canonical.BytesHash(b) != sha || len(b) > 1<<20 {
		return fault.New("INVALID_EVENT", "invalid immutable source event")
	}
	return f.createOrCompare(meta+"/authority-sources/"+sha+".json", b, 0600)
}

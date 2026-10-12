package store

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"path"
	"strings"
	"sync"
	"sync/atomic"
)

// rawBudget bounds the evidence bytes one operation's memo retains. Past it
// recording stops silently: nothing is lost but a later re-read.
const rawBudget = 64 << 20

// rawKind is the memo kind of verified root-relative evidence reads.
const rawKind = "raw-reads"

// Memo is one engine operation's record of fully validated evidence objects,
// keyed by object kind and full content hash (DEC-07). The FS an operation opens
// owns it and nothing outside this package can reach the FS's memo except through
// the methods below, so it ends with that handle and no other handle shares it.
// It stores only objects that passed every check: an error or an absent object is
// never recorded, so a later valid read after a transient failure still succeeds.
// A nil *Memo, the value for a hand-built FS, reuses nothing.
//
// A Memo reuses bytes as well as validation. Scan returns a view for a caller that
// already holds the repository's bytes (the snapshot scan): it never skips the
// supplied reader, so presence still comes from the scan and a missing object
// fails closed, and it records validation without retaining bytes.
type Memo struct {
	objs *sync.Map
	base *Memo
	hook func(kind, hash string)
	scan bool
	raw  *rawState
}

// rawState is the byte account shared by a memo and its Scan views.
type rawState struct {
	used, limit atomic.Int64
}

func newMemo() *Memo {
	r := &rawState{}
	r.limit.Store(rawBudget)
	return &Memo{objs: &sync.Map{}, raw: r}
}

// Memo returns the reuse memo of the operation that owns f, or nil.
func (f *FS) Memo() *Memo {
	if f == nil {
		return nil
	}
	return f.memo
}

// SetValidateHook installs the test-only seam called once for every schema
// validation of an evidence object, with its kind and content hash. Production
// code never calls it, and it cannot add an object to the memo.
func (f *FS) SetValidateHook(hook func(kind, hash string)) {
	if f != nil && f.memo != nil {
		f.memo.hook = hook
	}
}

// SetReadHook installs the test-only seam called with the repository-relative
// path of every file Read (anchored false) or a scan's Dir.ReadEntry (anchored
// true) opens.
func (f *FS) SetReadHook(hook func(rel string, anchored bool)) {
	if f != nil {
		f.readHook = hook
	}
}

// SetRawBudget lowers the retained-byte budget of the operation that owns f. It
// is a test-only seam; production code never calls it.
func (f *FS) SetRawBudget(n int64) {
	if f != nil && f.memo != nil {
		f.memo.raw.limit.Store(n)
	}
}

// Scan is the view for callers that supply bytes from a completed scan.
func (m *Memo) Scan() *Memo {
	if m == nil {
		return nil
	}
	return &Memo{objs: m.objs, base: m.root(), scan: true, raw: m.raw}
}

func (m *Memo) root() *Memo {
	if m.base != nil {
		return m.base
	}
	return m
}

// Held reports the retained value for an object and whether it was validated.
// A nil value with ok set is a validation marker without retained bytes. In a
// Scan view nothing but the marker is exposed.
func (m *Memo) Held(kind, hash string) (value any, ok bool) {
	if m == nil {
		return nil, false
	}
	v, ok := m.objs.Load(kind + "/" + hash)
	if !ok {
		return nil, false
	}
	if m.scan {
		return nil, true
	}
	return v, true
}

// Mark records that an object passed its schema (and, for the caller's kind, its
// chain) checks. It retains no bytes: a marker only lets a later check skip
// re-validating bytes that are themselves hash-checked again. It never replaces
// a retained value.
func (m *Memo) Mark(kind, hash string) {
	if m == nil {
		return
	}
	m.objs.LoadOrStore(kind+"/"+hash, nil)
}

// KeepValue records a value derived by the owning operation itself (not from a
// reader). A Scan view records nothing.
func (m *Memo) KeepValue(kind, key string, value any) {
	if m == nil || m.scan {
		return
	}
	m.objs.Store(kind+"/"+key, value)
}

// KeepRaw records the bytes a root-relative evidence read returned, only when
// their content hash is the name of ref and the budget allows. It stores its own
// copy, so the caller keeps its slice. A Scan view records nothing.
func (m *Memo) KeepRaw(ref string, b []byte) {
	if m == nil || m.scan {
		return
	}
	sum := sha256.Sum256(b)
	if hex.EncodeToString(sum[:]) != strings.TrimSuffix(path.Base(ref), ".json") {
		return
	}
	key := rawKind + "/" + ref
	if _, held := m.objs.Load(key); held {
		return
	}
	n := int64(len(b))
	if m.raw.used.Add(n) > m.raw.limit.Load() {
		m.raw.used.Add(-n)
		return
	}
	if _, loaded := m.objs.LoadOrStore(key, bytes.Clone(b)); loaded {
		m.raw.used.Add(-n)
	}
}

// Raw returns a copy of the verified bytes recorded for ref, if they fit limit.
func (m *Memo) Raw(ref string, limit int64) ([]byte, bool) {
	if m == nil || m.scan {
		return nil, false
	}
	v, ok := m.objs.Load(rawKind + "/" + ref)
	b, isBytes := v.([]byte)
	if !ok || !isBytes || int64(len(b)) > limit {
		return nil, false
	}
	return bytes.Clone(b), true
}

// Count reports one schema validation of an object to the test-only hook.
func (m *Memo) Count(kind, hash string) {
	if m == nil {
		return
	}
	if r := m.root(); r.hook != nil {
		r.hook(kind, hash)
	}
}

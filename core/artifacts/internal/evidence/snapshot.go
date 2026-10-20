// Package evidence builds explicit source-input identities. Presentation and
// progress are excluded only after their authoritative HTML has been validated.
package evidence

import (
	"fmt"
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
	"path/filepath"
	"runtime"
	"sort"
	"strings"
)

// ManifestFormat is the verification-inputs manifest format this engine emits.
// It is a variable only so tests in other packages can simulate an older
// engine; production code never assigns it.
var ManifestFormat = "codearbiter.verification-inputs/0.2.0"

const MaxInputFile = 32 << 20
const MaxInputTotal = 256 << 20
const MaxInputEntries = 50000

// gateEventsLog is the single append-only audit log exempt from input identity
// (ADR-0042). It is an exact repository-relative path: not plan-configurable,
// no prefix or glob. The file stays git-tracked; it is only not an input.
const gateEventsLog = ".codearbiter/gate-events.log"

func inputReadError(rel string, err error) error {
	if fault.Code(err) == "MAX_BYTES" {
		return fault.At("MAX_BYTES", "", "verification_inputs", fmt.Sprintf("input %q exceeds the %d-byte (32 MiB) file limit; review roots and explicit repository-relative exclude_directories for generated dependencies or output", rel, MaxInputFile))
	}
	return err
}

// internalOutputs returns every engine-generated output path, including each
// farm projection whose current bytes match a binding's base hash.
func internalOutputs(f *store.FS) (map[string]bool, error) {
	out, projections, e := internalOutputsWith(f)
	if e != nil {
		return nil, e
	}
	for projection, bases := range projections {
		b, e := f.Read(projection, canonical.MaxBytes)
		if e == nil && bases[farmProjectionBase(b)] {
			out[projection] = true
		}
	}
	return out, nil
}

// farmProjectionBase hashes a plan projection with its host-specific meta fields
// removed, the base a farm binding records. It is empty when b is not a
// canonical object.
func farmProjectionBase(b []byte) string {
	v, e := canonical.Object(b)
	if e != nil {
		return ""
	}
	base, e := canonical.Clone(v)
	if e != nil {
		return ""
	}
	meta := model.M(base["meta"])
	delete(meta, "model")
	delete(meta, "apiBaseUrl")
	baseBytes, e := canonical.Marshal(base)
	if e != nil {
		return ""
	}
	return canonical.BytesHash(baseBytes)
}

// internalOutputsWith validates the reserved output root and returns its output
// paths. Farm projections are not read here: it returns each bound projection
// path with the base hashes its bindings accept, and the caller decides when it
// reads the projection. A snapshot decides while its walk reads the file anyway,
// so a projection is opened once and no directory is listed ahead of the walk.
func internalOutputsWith(f *store.FS) (map[string]bool, map[string]map[string]bool, error) {
	projections := map[string]map[string]bool{}
	out, e := f.Infrastructure()
	if e != nil {
		return nil, nil, e
	}
	dirs, e := f.List(authority.Root)
	if os.IsNotExist(e) {
		return out, projections, nil
	}
	if e != nil {
		return nil, nil, e
	}
	// Two phases (ADR-0042 AC-08): every reserved output directory is read once
	// into this reference-to-bytes index, then each receipt chain is validated from
	// the index. A receipt's event, observation, evidence context and authority
	// source were already read (and their names checked against their bytes) in
	// the first phase, so validation costs no further open or ancestor walk. An
	// object a chain names that the index does not hold fails the chain closed.
	//
	// The index is bounded (security review MEDIUM-2): it keeps every receipt and
	// only the objects a receipt chain reaches. Directories are therefore read in
	// dependency order (receipts, then events and authority sources, then
	// observations, then evidence contexts) so each directory knows which of its
	// objects were named. A named object keeps its bytes and its schema check is
	// left to chain validation, which performs it once; an unnamed object is
	// checked inline and its bytes are dropped. Retained bytes are also capped.
	index := map[string][]byte{}
	receipts := []string{}
	need := map[string]bool{}
	deferred := []string{}
	retained := 0
	memo := observation.MemoFor(f).Scan()
	ordered := make([]os.DirEntry, 0, len(dirs))
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
					return nil, nil, fault.New("INVALID_OUTPUT", "invalid native cooperative lock file")
				}
				out[authority.Root+"/store.lock"] = true
				continue
			}
			return nil, nil, fault.New("UNRECOGNIZED_OUTPUT", "file in reserved artifact output root")
		}
		switch d.Name() {
		case "transactions", "history":
			continue
		case "authority-sources", "events", "receipts", "context-tokens", "evidence-contexts", "observations", "farm-bindings", "farm-seals", "farm-markers":
		default:
			return nil, nil, fault.New("UNRECOGNIZED_OUTPUT", "unrecognized reserved output directory")
		}
		ordered = append(ordered, d)
	}
	sort.SliceStable(ordered, func(i, j int) bool { return outputRank(ordered[i].Name()) < outputRank(ordered[j].Name()) })
	for _, d := range ordered {
		// Anchor the output directory once and read each receipt relative to it
		// (one open per receipt, no per-file ancestor walk). Like List, any link
		// among the entries is an error.
		sub, e := f.OpenDir(authority.Root + "/" + d.Name())
		if e != nil {
			return nil, nil, e
		}
		defer sub.Close()
		entries, e := sub.Entries()
		if e != nil {
			return nil, nil, e
		}
		for _, entry := range entries {
			if entry.Type()&os.ModeSymlink != 0 {
				return nil, nil, fault.New("UNSAFE_PATH", "symlink or reparse point encountered in scanned directory")
			}
		}
		for _, entry := range entries {
			p := authority.Root + "/" + d.Name() + "/" + entry.Name()
			if entry.IsDir() {
				return nil, nil, fault.New("UNRECOGNIZED_OUTPUT", "nested reserved output directory")
			}
			b, _, e := sub.ReadEntry(entry, canonical.MaxBytes)
			if e != nil {
				return nil, nil, e
			}
			h := strings.TrimSuffix(entry.Name(), ".json")
			if !strings.HasSuffix(entry.Name(), ".json") || canonical.BytesHash(b) != h {
				return nil, nil, fault.New("INVALID_OUTPUT", "generated output filename does not match its bytes")
			}
			referenced := false
			switch d.Name() {
			case "receipts", "events", "authority-sources", "observations", "evidence-contexts":
				// Receipt chains are validated below from these bytes; no object a
				// chain names is read a second time. Only receipts and the objects
				// they reach are retained.
				referenced = d.Name() == "receipts" || need[p]
				if referenced {
					retained += len(b)
					if retained > MaxInputTotal {
						return nil, nil, fault.At("MAX_BYTES", "", "verification_inputs", "reserved receipt chain evidence exceeds the retained-byte limit")
					}
					index[p] = b
					if d.Name() != "receipts" {
						deferred = append(deferred, p)
					}
				}
			}
			if d.Name() == "receipts" {
				// Historical v0.1 receipts are valid inventory inputs but cannot
				// confer current authority. Authority-consuming paths use Load,
				// which continues to reject them until freshly attested. The chain
				// is validated in the second phase, once every reserved directory
				// has been read.
				receipts = append(receipts, p)
				if r, e := canonical.Object(b); e == nil {
					need[authority.EventRef(model.S(r["event_sha256"]))] = true
					need[model.S(r["authority_source_ref"])] = true
				}
			} else if d.Name() == "events" || d.Name() == "authority-sources" {
				v, e := canonical.Object(b)
				if e != nil {
					return nil, nil, e
				}
				if referenced {
					if d.Name() == "events" && model.S(v["format"]) == "codearbiter.workflow-event/0.2.0" {
						need[model.S(v["observation_ref"])] = true
					}
				} else if _, done := memo.Held(d.Name()+":schema", h); !done {
					// Schema only: the chain rules (kind, verdict, link) belong to a
					// receipt that names this object, so this is not the "validated"
					// marker a chain check honors.
					memo.Count(d.Name(), h)
					if es := schema.ValidateWith(authority.EventSchema(), v); len(es) > 0 {
						return nil, nil, &es[0]
					}
					memo.Mark(d.Name()+":schema", h)
				}
			} else if d.Name() == "context-tokens" {
				v, e := canonical.Object(b)
				if e != nil || model.S(v["format"]) != "codearbiter.context-token/0.1.0" {
					return nil, nil, fault.New("INVALID_OUTPUT", "invalid generated context receipt")
				}
			} else if d.Name() == "evidence-contexts" || d.Name() == "observations" {
				v, e := canonical.Object(b)
				if e != nil {
					return nil, nil, fault.New("INVALID_OUTPUT", "invalid generated evidence object")
				}
				contract := observation.ContextSchema()
				if d.Name() == "observations" {
					contract = observation.InspectionSchema()
				}
				if referenced {
					if d.Name() == "observations" {
						need[model.S(v["context_ref"])] = true
					}
				} else if _, done := memo.Held(d.Name(), h); !done {
					memo.Count(d.Name(), h)
					if es := schema.ValidateWith(contract, v); len(es) > 0 {
						return nil, nil, &es[0]
					}
					memo.Mark(d.Name(), h)
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
					return nil, nil, fault.New("INVALID_OUTPUT", "invalid generated farm receipt")
				}
				if d.Name() == "farm-markers" {
					projection := model.S(v["projection_path"])
					if len(v) != 2 || !validate.Path(projection, false) || !strings.HasPrefix(projection, ".codearbiter/plans/") || !strings.HasSuffix(projection, ".plan.json") || strings.Count(projection, "/") != 2 {
						return nil, nil, fault.New("INVALID_OUTPUT", "farm marker names an unsafe projection")
					}
				}
				if d.Name() == "farm-bindings" {
					projection := model.S(v["projection_path"])
					if !validate.Path(projection, false) || !strings.HasPrefix(projection, ".codearbiter/plans/") || !strings.HasSuffix(projection, ".plan.json") {
						return nil, nil, fault.New("INVALID_OUTPUT", "farm binding names an unsafe projection")
					}
					if projections[projection] == nil {
						projections[projection] = map[string]bool{}
					}
					projections[projection][model.S(v["base_sha256"])] = true
				}
			}
			out[p] = true
		}
	}
	lookup := func(ref string, limit int64) ([]byte, error) {
		b, ok := index[ref]
		if !ok || int64(len(b)) > limit {
			return nil, os.ErrNotExist
		}
		return b, nil
	}
	for _, p := range receipts {
		if _, e := authority.InspectMemo(memo, p, index[p], lookup); e != nil {
			return nil, nil, e
		}
	}
	// A retained object that no chain check reached (an observation behind a
	// legacy event, say) still owes the schema check the first phase would have
	// made, so deferring it cannot let an invalid object through.
	for _, p := range deferred {
		dir, h := path.Base(path.Dir(p)), strings.TrimSuffix(path.Base(p), ".json")
		marker := dir
		if dir == "events" || dir == "authority-sources" {
			marker = dir + ":schema"
		}
		if _, done := memo.Held(dir, h); done {
			continue
		}
		if _, done := memo.Held(marker, h); done {
			continue
		}
		v, e := canonical.Object(index[p])
		if e != nil {
			return nil, nil, fault.New("INVALID_OUTPUT", "invalid generated evidence object")
		}
		contract := observation.ContextSchema()
		switch dir {
		case "events", "authority-sources":
			contract = authority.EventSchema()
		case "observations":
			contract = observation.InspectionSchema()
		}
		memo.Count(dir, h)
		if es := schema.ValidateWith(contract, v); len(es) > 0 {
			return nil, nil, &es[0]
		}
		memo.Mark(marker, h)
	}
	return out, projections, nil
}

// outputRank orders reserved output directories so that each is read after the
// directories whose objects name its own: receipts name events and authority
// sources, events name observations, observations name evidence contexts.
func outputRank(name string) int {
	switch name {
	case "receipts":
		return 0
	case "events":
		return 1
	case "authority-sources":
		return 2
	case "observations":
		return 3
	case "evidence-contexts":
		return 4
	}
	return 5
}

// shipSet is the git-defined ship set of a git work tree (ADR-0042).
type shipSet struct {
	files, dirs map[string]bool
	// executable records tracked files whose INDEX mode is 100755; the on-disk
	// mode is never consulted for tracked files.
	executable map[string]bool
	tracked    map[string]bool
	// gitlinks maps a submodule path to the commit its worktree has checked out.
	// Such a path is recorded as a single {"kind":"gitlink","commit":...} entry
	// and is never descended into.
	gitlinks map[string]string
}

// lstatDotGit is the one filesystem probe that decides whether a root is a git
// work tree. It is a variable only so a test can make it fail; production code
// never assigns it.
var lstatDotGit = os.Lstat

// shipSetMembers returns the git-defined ship set for a git work tree: index
// entries present on disk plus untracked, non-ignored files. A root below the
// top level of an enclosing work tree (a monorepo package, say) uses that work
// tree's membership scoped to the root: Git run from a subdirectory lists only
// the paths beneath it, relative to it. It returns nil only for roots with no
// work tree at all, which keep the filesystem walk. All argv is fixed by
// completionGitText probes.
func shipSetMembers(f *store.FS) (*shipSet, error) {
	nested := false
	if _, statErr := lstatDotGit(filepath.Join(f.Root, ".git")); statErr != nil {
		if !os.IsNotExist(statErr) {
			// A .git that cannot be inspected is not proof there is no repository.
			return nil, fault.New("WORKSPACE_DRIFT", "root .git cannot be inspected")
		}
		enclosed, err := enclosingWorkTree(f.Root)
		if err != nil || !enclosed {
			return nil, err
		}
		nested = true
	}
	realRoot, err := filepath.EvalSymlinks(f.Root)
	if err != nil {
		return nil, fault.New("WORKSPACE_DRIFT", "input root cannot be resolved")
	}
	top, err := completionResolvedGitPath(f.Root, completionGitTop)
	if err != nil {
		return nil, err
	}
	if nested {
		if !completionStrictlyWithin(top, realRoot) {
			return nil, fault.New("WORKSPACE_DRIFT", "Git top-level does not contain the input root")
		}
		// An ignored root has no ship set at all, which would leave every
		// file uncounted; that is not a membership the evidence can rest on.
		ignored, err := completionGitText(f.Root, completionGitRootIgnored)
		if err != nil {
			return nil, err
		}
		if ignored != "" {
			return nil, fault.New("WORKSPACE_DRIFT", "the input root is ignored by its enclosing Git work tree; stop ignoring it there or run git init in the root")
		}
	} else if !completionSamePath(top, realRoot) {
		// A present but fake or empty .git makes git search upward and answer
		// for an enclosing repository; the resolved top-level must be this root.
		return nil, fault.New("WORKSPACE_DRIFT", "Git top-level is not the input root")
	}
	index, err := completionGitText(f.Root, completionGitIndex)
	if err != nil {
		return nil, err
	}
	untracked, err := completionGitText(f.Root, completionGitUntracked)
	if err != nil {
		return nil, err
	}
	var rootCommon string
	commonOfRoot := func() (string, error) {
		if rootCommon == "" {
			c, cerr := completionResolvedGitPath(f.Root, completionGitCommon)
			if cerr != nil {
				return "", cerr
			}
			rootCommon = c
		}
		return rootCommon, nil
	}
	set := &shipSet{files: map[string]bool{}, dirs: map[string]bool{}, executable: map[string]bool{}, tracked: map[string]bool{}, gitlinks: map[string]string{}}
	add := func(p string) {
		set.files[p] = true
		for d := path.Dir(p); d != "." && d != "/" && !set.dirs[d]; d = path.Dir(d) {
			set.dirs[d] = true
		}
	}
	seen := map[string]bool{}
	for _, record := range strings.Split(index, "\x00") {
		if record == "" {
			continue
		}
		meta, p, ok := strings.Cut(record, "\t")
		fields := strings.Split(meta, " ")
		if !ok || len(fields) != 3 || fields[2] != "0" || seen[p] || !validate.Path(p, false) {
			return nil, fault.New("WORKSPACE_DRIFT", "Git index entry cannot be read")
		}
		switch fields[0] {
		case "100644", "100755", "120000", "160000":
		default:
			return nil, fault.New("WORKSPACE_DRIFT", "Git index mode cannot be read")
		}
		seen[p] = true
		abs := filepath.Join(f.Root, filepath.FromSlash(p))
		if _, lerr := os.Lstat(abs); lerr != nil {
			if os.IsNotExist(lerr) {
				continue // deleted from the working tree
			}
			return nil, fault.New("WORKSPACE_DRIFT", "Git index entry cannot be inspected")
		}
		set.tracked[p] = true
		switch fields[0] {
		case "160000":
			commit, gerr := gitlinkCommit(abs, fields[1], commonOfRoot)
			if gerr != nil {
				return nil, gerr
			}
			set.gitlinks[p] = commit
		case "100755":
			set.executable[p] = true
		}
		add(p)
	}
	for _, p := range strings.Split(untracked, "\x00") {
		if p == "" {
			continue
		}
		if strings.HasSuffix(p, "/") {
			// Git reports an embedded repository as "dir/". Its HEAD is its identity.
			p = strings.TrimSuffix(p, "/")
			if seen[p] || !validate.Path(p, false) {
				return nil, fault.New("WORKSPACE_DRIFT", "embedded repository path cannot be read")
			}
			seen[p] = true
			commit, gerr := gitlinkCommit(filepath.Join(f.Root, filepath.FromSlash(p)), "", commonOfRoot)
			if gerr != nil {
				return nil, gerr
			}
			set.gitlinks[p] = commit
			add(p)
			continue
		}
		if seen[p] || !validate.Path(p, false) {
			return nil, fault.New("WORKSPACE_DRIFT", "untracked path cannot be read")
		}
		seen[p] = true
		add(p)
	}
	return set, nil
}

// enclosingWorkTree reports whether any ancestor of root holds a .git entry, so
// root lies inside a work tree it does not itself top. An ancestor that cannot be
// inspected fails closed rather than reading as no repository.
func enclosingWorkTree(root string) (bool, error) {
	real, err := filepath.EvalSymlinks(root)
	if err != nil {
		return false, fault.New("WORKSPACE_DRIFT", "input root cannot be resolved")
	}
	for dir := filepath.Dir(real); ; dir = filepath.Dir(dir) {
		if _, err := lstatDotGit(filepath.Join(dir, ".git")); err == nil {
			return true, nil
		} else if !os.IsNotExist(err) {
			return false, fault.New("WORKSPACE_DRIFT", "an enclosing .git cannot be inspected")
		}
		if filepath.Dir(dir) == dir {
			return false, nil
		}
	}
}

// completionStrictlyWithin reports whether inner lies strictly below outer.
func completionStrictlyWithin(outer, inner string) bool {
	if runtime.GOOS == "windows" {
		outer, inner = strings.ToLower(outer), strings.ToLower(inner)
	}
	rel, err := filepath.Rel(filepath.Clean(outer), filepath.Clean(inner))
	return err == nil && rel != "." && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator)) && !filepath.IsAbs(rel)
}

// gitlinkCommit returns the commit identifying a submodule or embedded repo at
// abs. The path must be a real directory. Without its own .git a tracked
// submodule is not checked out and keeps its index pointer (indexSha); an
// embedded repository (indexSha == "") always has one. When .git is present the
// repository's own top-level must be abs, otherwise git would answer for an
// enclosing repository. Its git common directory must also differ from the root
// repository's: a .git file pointing at the parent's own git directory would
// otherwise report the parent's HEAD as the submodule's identity.
func gitlinkCommit(abs, indexSha string, rootCommon func() (string, error)) (string, error) {
	info, err := os.Lstat(abs)
	if err != nil || info.Mode()&os.ModeSymlink != 0 || completionReparse(info) || !info.IsDir() {
		return "", fault.New("WORKSPACE_DRIFT", "gitlink path is not a real directory")
	}
	if _, gerr := os.Lstat(filepath.Join(abs, ".git")); gerr != nil {
		if os.IsNotExist(gerr) && indexSha != "" {
			return indexSha, nil
		}
		return "", fault.New("WORKSPACE_DRIFT", "repository at gitlink path cannot be inspected")
	}
	realAbs, err := filepath.EvalSymlinks(abs)
	if err != nil {
		return "", fault.New("WORKSPACE_DRIFT", "gitlink path cannot be resolved")
	}
	top, err := completionResolvedGitPath(abs, completionGitTop)
	if err != nil {
		return "", err
	}
	if !completionSamePath(top, realAbs) {
		return "", fault.New("WORKSPACE_DRIFT", "gitlink .git does not belong to the gitlink path")
	}
	common, err := completionResolvedGitPath(abs, completionGitCommon)
	if err != nil {
		return "", err
	}
	parentCommon, err := rootCommon()
	if err != nil {
		return "", err
	}
	if completionSamePath(common, parentCommon) {
		return "", fault.New("WORKSPACE_DRIFT", "gitlink .git shares the root repository's git directory")
	}
	return completionGitText(abs, completionGitHead)
}

func (s *shipSet) gitlinkCommit(p string) (string, bool) {
	if s == nil {
		return "", false
	}
	c, ok := s.gitlinks[p]
	return c, ok
}

// foldMatches reports whether any ship-set file, directory or gitlink equals
// root, or lies under it, when compared case-insensitively. Callers use it only
// after an exact-name lookup failed, so a true result means a case mismatch.
// It folds case only. Unicode normalization (NFC/NFD) and Windows 8.3 short-name
// spellings are not folded here (the stdlib has no normalizer and no dependency
// may be added); resolveRoot refuses any explicit root whose segments are not
// listed under exactly that name, which is what closes those spellings.
func (s *shipSet) foldMatches(root string) bool {
	if s == nil {
		return false
	}
	under := func(p string) bool {
		if strings.EqualFold(p, root) {
			return true
		}
		return len(p) > len(root) && p[len(root)] == '/' && strings.EqualFold(p[:len(root)], root)
	}
	for p := range s.files {
		if under(p) {
			return true
		}
	}
	for p := range s.dirs {
		if under(p) {
			return true
		}
	}
	for p := range s.gitlinks {
		if under(p) {
			return true
		}
	}
	return false
}

// anchor is one scan-anchored directory together with its single listing.
type anchor struct {
	dir     *store.Dir
	entries []os.DirEntry
	byName  map[string]os.DirEntry
}

// anchors memoizes, for the duration of ONE scan, the directories that more than
// one consumer of that scan reaches: the ancestors of explicit roots and the
// normative artifact directories. Each is anchored once and listed once; later consumers reuse the
// anchor and the listing. It is created per scan and closed with it, never shared
// across scans or operations.
//
// The cache is capped at maxAnchors handles: plan roots are unbounded in number,
// and an uncapped cache could exhaust file descriptors on a very wide policy.
// A reused anchor is re-checked against its parent's current entry, so the cache
// saves the open and the listing but never the identity check.
type anchors struct {
	f *store.FS
	m map[string]*anchor
}

const maxAnchors = 512

// keep caches a for rel, or closes it and fails closed when the cache is full.
func (s *anchors) keep(rel string, a *anchor) error {
	if len(s.m) >= maxAnchors {
		a.dir.Close()
		return fault.At("MAX_INPUTS", "", "verification_inputs.roots", fmt.Sprintf("input roots need more than %d anchored directories; consolidate verification_inputs.roots under fewer common parents", maxAnchors))
	}
	s.m[rel] = a
	return nil
}

func newAnchors(f *store.FS) *anchors { return &anchors{f: f, m: map[string]*anchor{}} }

func (s *anchors) Close() {
	for _, a := range s.m {
		a.dir.Close()
	}
	s.m = map[string]*anchor{}
}

func newAnchor(d *store.Dir) (*anchor, error) {
	entries, e := d.Entries()
	if e != nil {
		d.Close()
		return nil, e
	}
	byName := make(map[string]os.DirEntry, len(entries))
	for _, entry := range entries {
		byName[entry.Name()] = entry
	}
	return &anchor{dir: d, entries: entries, byName: byName}, nil
}

// top anchors and lists the repository root once per scan.
func (s *anchors) top() (*anchor, error) {
	if a, ok := s.m["."]; ok {
		return a, nil
	}
	d, e := s.f.OpenDir(".")
	if e != nil {
		return nil, e
	}
	a, e := newAnchor(d)
	if e != nil {
		return nil, e
	}
	if e := s.keep(".", a); e != nil {
		return nil, e
	}
	return a, nil
}

// child anchors the directory named seg inside parent (whose repository path is
// parentRel). kind is "missing" when no such name exists and "variant" when the
// platform resolves seg to an entry the listing spells differently.
func (s *anchors) child(parent *anchor, parentRel, seg string) (*anchor, string, error) {
	rel := path.Join(parentRel, seg)
	if a, ok := s.m[rel]; ok {
		if e := parent.dir.Current(seg, a.dir); e != nil {
			return nil, "", e
		}
		return a, "", nil
	}
	entry := parent.byName[seg]
	if entry == nil {
		exists, e := parent.dir.Has(seg)
		if e != nil {
			return nil, "", e
		}
		if exists {
			return nil, "variant", nil
		}
		return nil, "missing", nil
	}
	d, e := parent.dir.OpenSub(entry)
	if e != nil {
		return nil, "", e
	}
	a, e := newAnchor(d)
	if e != nil {
		return nil, "", e
	}
	if e := s.keep(rel, a); e != nil {
		return nil, "", e
	}
	return a, "", nil
}

// get anchors the real directory at rel, reusing every already-anchored prefix.
// A missing directory is os.ErrNotExist.
func (s *anchors) get(rel string) (*anchor, error) {
	cur, e := s.top()
	if e != nil || rel == "." {
		return cur, e
	}
	at := "."
	for _, seg := range strings.Split(rel, "/") {
		next, kind, e := s.child(cur, at, seg)
		if e != nil {
			return nil, e
		}
		if kind == "missing" {
			return nil, os.ErrNotExist
		}
		if kind == "variant" {
			return nil, fault.New("INPUT_MEMBERSHIP_UNAVAILABLE", fmt.Sprintf("path %q is not spelled exactly as it is stored on disk", rel))
		}
		cur, at = next, path.Join(at, seg)
	}
	return cur, nil
}

// resolveRoot canonicalizes an explicit plan root segment by segment and returns
// the anchored directory that contains its last segment together with that
// segment's listing entry. Every segment must appear in its parent's listing
// under exactly that name: a case variant, a Windows 8.3 short name or an
// NFC/NFD respelling that the host resolves anyway is refused, because the
// ship-set and gitlink lookups that follow compare exact index spellings. Shared
// prefixes of several roots are anchored and listed once per scan; the returned
// anchor is owned by anch.
func resolveRoot(anch *anchors, root string) (*anchor, os.DirEntry, error) {
	parts := strings.Split(root, "/")
	cur, err := anch.top()
	if err != nil {
		return nil, nil, err
	}
	at := "."
	for i, seg := range parts {
		if i == len(parts)-1 {
			if found := cur.byName[seg]; found != nil {
				return cur, found, nil
			}
		}
		var next *anchor
		var kind string
		if i == len(parts)-1 {
			exists, err := cur.dir.Has(seg)
			if err != nil {
				return nil, nil, err
			}
			kind = "missing"
			if exists {
				kind = "variant"
			}
		} else {
			next, kind, err = anch.child(cur, at, seg)
			if err != nil {
				return nil, nil, err
			}
		}
		switch kind {
		case "variant":
			return nil, nil, fault.New("INPUT_MEMBERSHIP_UNAVAILABLE", fmt.Sprintf("input root %q is not spelled exactly as it is stored on disk (case, short-name or Unicode-normalization variant at %q); spell the root as the directory listing does", root, seg))
		case "missing":
			return nil, nil, fault.At("MISSING_INPUT_ROOT", "", "verification_inputs.roots", fmt.Sprintf("input root %q does not exist; for proposed files select an existing containing directory so creation is tracked", root))
		}
		cur, at = next, path.Join(at, seg)
	}
	return nil, nil, fault.New("INVALID_INPUT_POLICY", "empty input root")
}

func snapshotOnce(f *store.FS, plan *model.Document) (map[string]any, error) {
	anch := newAnchors(f)
	defer anch.Close()
	outputs, projections, e := internalOutputsWith(f)
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
		if errors := validate.InputPolicyErrors(plan.Norm()); len(errors) > 0 {
			return nil, &errors[0]
		}
	}
	for _, p := range roots {
		if !validate.Path(p, true) || validate.IsGitPath(p) || validate.IsRuntimeMarkerPath(p) {
			return nil, fault.New("INVALID_INPUT_POLICY", "unsafe input root")
		}
	}
	for _, p := range excludes {
		if !validate.Path(p, false) || p == ".codearbiter" || strings.HasPrefix(p, ".codearbiter/") {
			return nil, fault.New("INVALID_INPUT_POLICY", "exclude directories must be explicit non-governance repo paths")
		}
	}
	excluded := func(p string) bool {
		if p == ".git" || p == validate.RuntimeMarkers {
			return true
		}
		for _, x := range excludes {
			if validate.InputWithin(x, p) {
				return true
			}
		}
		return false
	}
	// A git root whose membership cannot be determined is an error: it never
	// degrades to the filesystem walk (ADR-0042).
	set, e := shipSetMembers(f)
	if e != nil {
		return nil, fault.New("INPUT_MEMBERSHIP_UNAVAILABLE", "git ship-set membership cannot be determined: "+e.Error())
	}
	membership := "filesystem"
	if set != nil {
		membership = "git_ship_set"
	}
	isExecutable := func(p string, info os.FileInfo) bool {
		if set != nil && set.tracked[p] {
			return set.executable[p]
		}
		return info.Mode()&0111 != 0
	}
	items := map[string]any{}
	visited := map[string]bool{}
	count, total := 0, 0
	// walk visits one already-anchored directory. Each directory is opened once by
	// its parent and each input file is opened once relative to its directory, so
	// a scan costs one open per visited directory and per input file, never a
	// per-file ancestor walk (ADR-0042 AC-08). Symlink and reparse refusal comes
	// from the listing's own entry types. Reserved output membership is validated
	// above and omitted as a whole only after EVERY contained file has a
	// recognized output contract, so the reserved root is never entered.
	// normativeDone records the specs/plans directories already included while the
	// walk had them anchored and listed, so the always-include pass below does not
	// anchor or list them a second time.
	normativeDone := map[string]bool{}
	includeNormative := func(dir *store.Dir, entries []os.DirEntry, dirPath string) error {
		for _, entry := range entries {
			// Strict catalog scan: any link in these directories is an error.
			if entry.Type()&os.ModeSymlink != 0 {
				return fault.New("UNSAFE_PATH", "symlink or reparse point encountered in scanned directory")
			}
		}
		for _, entry := range entries {
			if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".html") {
				continue
			}
			p := dirPath + "/" + entry.Name()
			if prior, ok := items[p].(map[string]any); ok && prior["kind"] == "artifact_normative" {
				// The walk already opened, parsed and hashed this exact file in
				// this scan; reading it again would open it twice.
				items[p] = map[string]any{"kind": "artifact_normative", "sha256": prior["sha256"]}
				continue
			}
			b, _, e := dir.ReadEntry(entry, canonical.MaxBytes)
			if e != nil {
				return e
			}
			d, e := render.Parse(b)
			if e != nil {
				return e
			}
			items[p] = map[string]any{"kind": "artifact_normative", "sha256": d.NormHash()}
		}
		return nil
	}
	// descend walks a child directory, reusing its scan anchor and listing when
	// one exists and otherwise anchoring and listing it exactly once.
	var walk func(*store.Dir, []os.DirEntry, string) error
	descend := func(parent *store.Dir, entry os.DirEntry, p string) error {
		if a, ok := anch.m[p]; ok {
			if e := parent.Current(entry.Name(), a.dir); e != nil {
				return e
			}
			return walk(a.dir, a.entries, p)
		}
		sub, e := parent.OpenSub(entry)
		if e != nil {
			return e
		}
		if p == ".codearbiter" {
			// The always-include pass below reaches specs and plans through this
			// directory; retain its anchor and listing for the rest of the scan
			// instead of anchoring and listing it a second time.
			held, e := newAnchor(sub)
			if e != nil {
				return e
			}
			if e := anch.keep(p, held); e != nil {
				return e
			}
			return walk(held.dir, held.entries, p)
		}
		defer sub.Close()
		subEntries, e := sub.Entries()
		if e != nil {
			return e
		}
		return walk(sub, subEntries, p)
	}
	walk = func(dir *store.Dir, entries []os.DirEntry, rel string) error {
		names := []any{}
		for _, entry := range entries {
			p := path.Join(rel, entry.Name())
			if p == authority.Root {
				continue
			}
			if (entry.IsDir() || entry.Type()&os.ModeSymlink != 0) && excluded(p) {
				continue
			}
			if p == ".git" || p == gateEventsLog {
				continue
			}
			if set != nil && !set.files[p] && !set.dirs[p] {
				continue // outside the git ship set (ignored)
			}
			if !validate.Path(p, false) {
				return fault.New("INVALID_PATH", "input path is not portable")
			}
			count++
			if count > MaxInputEntries {
				return fault.New("MAX_INPUTS", "input manifest exceeds 50000 entries")
			}
			visited[p] = true
			if outputs[p] {
				continue
			}
			// A bound farm projection is an output only while its bytes match a
			// binding's base. Decide from the one read the walk makes anyway, and
			// hash those same bytes when no binding accepts them.
			var held []byte
			var heldInfo os.FileInfo
			holding := false
			if bases := projections[p]; bases != nil && !entry.IsDir() {
				b, info, e := dir.ReadEntry(entry, MaxInputFile)
				if e != nil {
					return inputReadError(p, e)
				}
				if len(b) <= canonical.MaxBytes && bases[farmProjectionBase(b)] {
					continue
				}
				held, heldInfo, holding = b, info, true
			}
			names = append(names, entry.Name())
			if commit, ok := set.gitlinkCommit(p); ok {
				// Submodule: the checked-out commit is the whole identity; its
				// worktree contents are never read.
				items[p] = map[string]any{"kind": "gitlink", "commit": commit}
				continue
			}
			if entry.IsDir() {
				if e := descend(dir, entry, p); e != nil {
					return e
				}
				continue
			}
			b, info := held, heldInfo
			if !holding {
				var e error
				if b, info, e = dir.ReadEntry(entry, MaxInputFile); e != nil {
					return inputReadError(p, e)
				}
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
			items[p] = map[string]any{"kind": kind, "sha256": h, "executable": isExecutable(p, info)}
		}
		items[rel+"/"] = map[string]any{"kind": "directory", "members": names}
		if rel == ".codearbiter/specs" || rel == ".codearbiter/plans" {
			normativeDone[rel] = true
			return includeNormative(dir, entries, rel)
		}
		return nil
	}
	sort.Strings(roots)
	walked := []string{}
	for _, root := range roots {
		if excluded(root) {
			continue
		}
		if set != nil {
			for g := range set.gitlinks {
				if strings.HasPrefix(root, g+"/") {
					return nil, fault.At("INVALID_INPUT_POLICY", "", "verification_inputs.roots", fmt.Sprintf("input root %q lies inside the submodule or embedded repository %q; name the submodule path itself", root, g))
				}
			}
		}
		covered := false
		for _, prior := range walked {
			if validate.InputWithin(prior, root) {
				covered = true
				break
			}
		}
		if covered {
			continue
		}
		if root == gateEventsLog {
			continue // append-only hook log: never an input, even as an explicit root
		}
		if root == "." {
			top, e := anch.top()
			if e != nil {
				return nil, e
			}
			if e = walk(top.dir, top.entries, "."); e != nil {
				return nil, e
			}
			walked = append(walked, root)
			continue
		}
		if set != nil && !set.files[root] && !set.dirs[root] && set.foldMatches(root) {
			return nil, fault.New("INPUT_MEMBERSHIP_UNAVAILABLE", fmt.Sprintf("input root %q matches a git ship-set path only case-insensitively; spell the root exactly as the index does", root))
		}
		parent, entry, err := resolveRoot(anch, root)
		if err != nil {
			return nil, err
		}
		if commit, ok := set.gitlinkCommit(root); ok {
			// A submodule root is its pointer, never its contents.
			count++
			visited[root] = true
			items[root] = map[string]any{"kind": "gitlink", "commit": commit}
			continue
		}
		if !entry.IsDir() {
			if entry.Type() != 0 {
				return nil, fault.New("UNSAFE_PATH", "input root is a symlink, reparse point or special file")
			}
			if set != nil && !set.files[root] {
				continue // outside the git ship set (ignored): same rule as the walk
			}
			visited[root] = true
			b, info, err := parent.dir.ReadEntry(entry, MaxInputFile)
			if err != nil {
				return nil, inputReadError(root, err)
			}
			count++
			total += len(b)
			if count > MaxInputEntries || total > MaxInputTotal {
				return nil, fault.New("MAX_INPUTS", "explicit input roots exceed manifest limits")
			}
			items[root] = map[string]any{"kind": "bytes", "sha256": canonical.BytesHash(b), "executable": isExecutable(root, info)}
			continue
		}
		if root == authority.Root {
			walked = append(walked, root)
			continue
		}
		if err := descend(parent.dir, entry, root); err != nil {
			return nil, err
		}
		walked = append(walked, root)
	}
	// Coverage: the walk matches ship-set paths by exact name, so a case or
	// Unicode-normalization mismatch between the index and the disk would hide a
	// member. Every ship-set file inside a walked root that nothing legitimately
	// removed must have been visited; otherwise membership is not faithful.
	if set != nil {
		members := make([]string, 0, len(set.files))
		for p := range set.files {
			members = append(members, p)
		}
		sort.Strings(members)
		for _, root := range walked {
			for _, p := range members {
				if !validate.InputWithin(root, p) || visited[p] || p == gateEventsLog || outputs[p] || validate.InputWithin(authority.Root, p) {
					continue
				}
				removed := false
				for d := p; d != "." && d != "/"; d = path.Dir(d) {
					if excluded(d) {
						removed = true
						break
					}
				}
				if !removed {
					return nil, fault.New("INPUT_MEMBERSHIP_UNAVAILABLE", fmt.Sprintf("ship-set member %q was not found on disk under that exact name (case or Unicode-normalization mismatch); rename it to match the index", p))
				}
			}
		}
	}
	// Always include canonical normative artifacts even when scoped roots omit
	// their directory. This also makes source-definition changes stale evidence.
	for _, kind := range []string{"specs", "plans"} {
		dirPath := ".codearbiter/" + kind
		if normativeDone[dirPath] {
			continue
		}
		a, e := anch.get(dirPath)
		if os.IsNotExist(e) {
			continue
		}
		if e != nil {
			return nil, e
		}
		if e := includeNormative(a.dir, a.entries, dirPath); e != nil {
			return nil, e
		}
	}
	manifest := map[string]any{"format": ManifestFormat, "engine": render.Version, "platform": runtime.GOOS + "/" + runtime.GOARCH, "engine_toolchain": runtime.Version(), "roots": model.List(roots...), "exclude_directories": model.List(excludes...), "entries": items}
	if ManifestFormat != "codearbiter.verification-inputs/0.1.0" {
		// The historical 0.1.0 manifest predates membership and is closed
		// without it, so an engine simulating it must not emit the field.
		manifest["membership"] = membership
	}
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

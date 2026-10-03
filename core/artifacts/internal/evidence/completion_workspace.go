package evidence

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/binary"
	"fmt"
	"hash"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"runtime"
	"sort"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

// CompletionWorkspaces freezes the command bindings from a qualified verifier.
// Raw mode reproduces the producer's Python fingerprint exactly. Consumer mode
// normalizes only validated canonical artifacts and validated derived outputs
// in the artifact root. Other worktrees retain the full producer byte closure.
// As with Snapshot, two passes detect ordinary concurrent edits, not hostile ABA.
func CompletionWorkspaces(f *store.FS, bindings []any, normalize bool) ([]any, error) {
	if f == nil || len(bindings) == 0 || len(bindings) > 256 {
		return nil, fault.New("WORKSPACE_DRIFT", "completion command bindings are missing or exceed bounds")
	}
	a, err := completionWorkspacesOnce(f, bindings, normalize)
	if err != nil {
		return nil, err
	}
	b, err := completionWorkspacesOnce(f, bindings, normalize)
	if err != nil {
		return nil, err
	}
	if !reflect.DeepEqual(a, b) {
		return nil, fault.New("CONCURRENT_CHANGE", "completion workspaces changed during collection")
	}
	return b, nil
}

func completionSamePath(a, b string) bool {
	if runtime.GOOS == "windows" {
		return strings.EqualFold(filepath.Clean(a), filepath.Clean(b))
	}
	return filepath.Clean(a) == filepath.Clean(b)
}

// CompletionPathIdentity retains Python's raw st_dev:st_ino representation.
// Each existing component must be real; alternate spellings cannot hide links.
func CompletionPathIdentity(path string) (string, error) {
	if !filepath.IsAbs(path) || strings.IndexByte(path, 0) >= 0 {
		return "", fault.New("WORKSPACE_DRIFT", "workspace path must be absolute")
	}
	path = filepath.Clean(path)
	for p := path; ; p = filepath.Dir(p) {
		info, err := os.Lstat(p)
		if err != nil {
			return "", err
		}
		if info.Mode()&os.ModeSymlink != 0 || completionReparse(info) {
			return "", fault.New("WORKSPACE_DRIFT", "workspace path traverses replaceable indirection")
		}
		if p != path && !info.IsDir() {
			return "", fault.New("WORKSPACE_DRIFT", "workspace ancestor is not a directory")
		}
		if filepath.Dir(p) == p {
			break
		}
	}
	return completionNativeIdentity(path)
}

// CompletionReadFile imports bounded regular data through the rooted native
// reader, checking locator identity before and after the read.
func CompletionReadFile(path string, max int) ([]byte, error) {
	if max < 0 {
		return nil, fault.New("MAX_BYTES", "invalid completion file bound")
	}
	before, err := CompletionPathIdentity(path)
	if err != nil {
		return nil, err
	}
	f, err := store.Open(filepath.Dir(path))
	if err != nil {
		return nil, err
	}
	defer f.Close()
	data, err := f.Read(filepath.Base(path), int64(max))
	if err != nil {
		return nil, err
	}
	after, err := CompletionPathIdentity(path)
	if err != nil || before != after {
		return nil, fault.New("WORKSPACE_DRIFT", "completion file identity changed while reading")
	}
	return data, nil
}

type completionOutput struct{ bytes.Buffer }

func (b *completionOutput) Write(p []byte) (int, error) {
	if b.Len()+len(p) > MaxInputFile {
		return 0, fault.New("MAX_BYTES", "Git workspace output exceeds its bound")
	}
	return b.Buffer.Write(p)
}

func completionGitText(root string, args ...string) (string, error) {
	executable := os.Getenv("CODEARBITER_GIT_EXECUTABLE")
	if executable == "" || !filepath.IsAbs(executable) {
		return "", fault.New("WORKSPACE_DRIFT", "completion requires the bridge-selected absolute Git executable")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	// Disable fsmonitor execution for these read-only probes. Preserve protected
	// Git configuration (including safe.directory), removing only root selectors.
	cmd := exec.CommandContext(ctx, executable, append([]string{"-C", root, "-c", "core.fsmonitor=false"}, args...)...)
	blocked := map[string]bool{}
	for _, name := range strings.Fields("GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_OBJECT_DIRECTORY GIT_DIR GIT_WORK_TREE GIT_IMPLICIT_WORK_TREE GIT_GRAFT_FILE GIT_INDEX_FILE GIT_NO_REPLACE_OBJECTS GIT_REPLACE_REF_BASE GIT_PREFIX GIT_SHALLOW_FILE GIT_COMMON_DIR GIT_CEILING_DIRECTORIES GIT_DISCOVERY_ACROSS_FILESYSTEM") {
		blocked[name] = true
	}
	for _, entry := range os.Environ() {
		name, _, _ := strings.Cut(entry, "=")
		if !blocked[strings.ToUpper(name)] {
			cmd.Env = append(cmd.Env, entry)
		}
	}
	var out, stderr completionOutput
	cmd.Stdout, cmd.Stderr = &out, &stderr
	if err := cmd.Run(); err != nil {
		return "", fault.New("WORKSPACE_DRIFT", "Git workspace identity or inventory is unavailable")
	}
	if !utf8.Valid(out.Bytes()) {
		return "", fault.New("WORKSPACE_DRIFT", "Git workspace paths are not UTF-8")
	}
	value := out.String()
	for _, arg := range args {
		if arg == "-z" {
			return value, nil
		}
	}
	return strings.TrimSpace(value), nil
}

func completionDirectory(path, identity string) error {
	if !completionIdentityMatches(path, identity) {
		return fault.New("WORKSPACE_DRIFT", "workspace filesystem identity changed")
	}
	info, err := os.Lstat(path)
	if err != nil || !info.IsDir() {
		return fault.New("WORKSPACE_DRIFT", "workspace directory is unavailable")
	}
	return nil
}

func completionIdentityMatches(path, expected string) bool {
	current, err := CompletionPathIdentity(path)
	if err != nil {
		return false
	}
	if current == expected {
		return true
	}
	legacy, err := completionLegacyIdentity(path)
	if err != nil || legacy != expected {
		return false
	}
	// The legacy spelling is an alternate native representation, never an
	// arbitrary caller-supplied fallback. Preserve all component checks and
	// require the full identity to remain unchanged across both native reads.
	after, err := CompletionPathIdentity(path)
	return err == nil && after == current
}

func completionResolvedGitPath(root string, args ...string) (string, error) {
	path, err := completionGitText(root, args...)
	if err != nil {
		return "", err
	}
	if !filepath.IsAbs(path) {
		return "", fault.New("WORKSPACE_DRIFT", "Git returned a relative identity path")
	}
	return filepath.EvalSymlinks(path)
}

func completionWorkspacesOnce(f *store.FS, bindings []any, normalize bool) ([]any, error) {
	artifactCommon, err := completionResolvedGitPath(f.Root, "rev-parse", "--path-format=absolute", "--git-common-dir")
	if err != nil {
		return nil, err
	}
	unique := map[string]any{}
	for _, value := range bindings {
		binding := model.M(value)
		root, cwd, common := model.S(binding["workspace_root"]), model.S(binding["cwd"]), model.S(binding["git_common_dir"])
		for _, pair := range [][2]string{{root, model.S(binding["workspace_filesystem_id"])}, {cwd, model.S(binding["cwd_filesystem_id"])}, {common, model.S(binding["git_common_filesystem_id"])}} {
			if err := completionDirectory(pair[0], pair[1]); err != nil {
				return nil, err
			}
		}
		top, err := completionResolvedGitPath(cwd, "rev-parse", "--show-toplevel")
		if err != nil || !completionSamePath(top, root) {
			return nil, fault.New("WORKSPACE_DRIFT", "command cwd no longer belongs to its mapped worktree")
		}
		actualCommon, err := completionResolvedGitPath(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
		if err != nil || !completionSamePath(actualCommon, common) || !completionSamePath(common, artifactCommon) {
			return nil, fault.New("WORKSPACE_DRIFT", "mapped workspace Git common directory changed")
		}
		argv := model.A(binding["argv"])
		if len(argv) == 0 {
			return nil, fault.New("WORKSPACE_DRIFT", "command executable binding is missing")
		}
		executable, err := CompletionReadFile(model.S(argv[0]), 512<<20)
		if err != nil || canonical.BytesHash(executable) != model.S(binding["executable_sha256"]) {
			return nil, fault.New("WORKSPACE_DRIFT", "command executable identity changed")
		}
		launchFiles, ok := binding["launch_files"].([]any)
		if !ok || len(launchFiles) == 0 || len(launchFiles) > 32 {
			return nil, fault.New("WORKSPACE_DRIFT", "command launch file bindings are unavailable")
		}
		for _, v := range launchFiles {
			item := model.M(v)
			path := model.S(item["path"])
			if !completionIdentityMatches(path, model.S(item["filesystem_id"])) {
				return nil, fault.New("WORKSPACE_DRIFT", "command launch file identity changed")
			}
			data, err := CompletionReadFile(path, 512<<20)
			if err != nil || canonical.BytesHash(data) != model.S(item["sha256"]) {
				return nil, fault.New("WORKSPACE_DRIFT", "command launch file bytes changed")
			}
		}
		key := filepath.Clean(root)
		if runtime.GOOS == "windows" {
			key = strings.ToLower(key)
		}
		if _, ok := unique[key]; ok {
			continue
		}
		snapshot, err := completionWorkspace(f, binding, normalize && completionSamePath(root, f.Root))
		if err != nil {
			return nil, err
		}
		unique[key] = snapshot
	}
	result := make([]any, 0, len(unique))
	for _, snapshot := range unique {
		result = append(result, snapshot)
	}
	// Python sorts the retained root spelling, including its case on Windows.
	sort.Slice(result, func(i, j int) bool {
		return model.S(model.M(result[i])["root"]) < model.S(model.M(result[j])["root"])
	})
	return result, nil
}

func completionWorkspace(f *store.FS, binding map[string]any, normalize bool) (map[string]any, error) {
	root := model.S(binding["workspace_root"])
	workspace, err := store.Open(root)
	if err != nil {
		return nil, err
	}
	defer workspace.Close()
	outputs, norms := map[string]bool{}, map[string]string{}
	if normalize {
		outputs, err = internalOutputs(f)
		if err != nil {
			return nil, err
		}
		catalog, err := repository.Scan(f)
		if err != nil {
			return nil, err
		}
		for _, entry := range catalog.Entries {
			norms[entry.Path] = entry.Doc.NormHash()
		}
	}
	status, err := completionGitText(root, "status", "--porcelain=v2", "-z", "--untracked-files=all")
	if err != nil {
		return nil, err
	}
	index, err := completionGitText(root, "ls-files", "--stage", "-z")
	if err != nil {
		return nil, err
	}
	untracked, err := completionGitText(root, "ls-files", "--others", "--exclude-standard", "-z")
	if err != nil {
		return nil, err
	}
	entries := map[string]string{}
	for _, record := range strings.Split(index, "\x00") {
		if record == "" {
			continue
		}
		metadata, path, ok := strings.Cut(record, "\t")
		fields := strings.Split(metadata, " ")
		if !ok || len(fields) != 3 || fields[2] != "0" || entries[path] != "" {
			return nil, fault.New("WORKSPACE_DRIFT", "Git index entry cannot be frozen")
		}
		switch fields[0] {
		case "100644", "100755", "120000", "160000":
		default:
			return nil, fault.New("WORKSPACE_DRIFT", "Git index mode cannot be frozen")
		}
		entries[path] = fields[0]
	}
	for _, path := range strings.Split(untracked, "\x00") {
		if path == "" {
			continue
		}
		if entries[path] != "" {
			return nil, fault.New("WORKSPACE_DRIFT", "duplicate Git workspace entry")
		}
		entries[path] = "untracked"
	}
	if len(entries) > MaxInputEntries {
		return nil, fault.New("MAX_INPUTS", "completion workspace exceeds 50000 entries")
	}
	paths := make([]string, 0, len(entries))
	for path := range entries {
		paths = append(paths, path)
	}
	sort.Strings(paths)
	content, total := sha256.New(), 0
	for _, path := range paths {
		if outputs[path] {
			continue
		}
		kind, data, err := completionMember(workspace, path, entries[path])
		if err != nil {
			return nil, err
		}
		total += len(data)
		if total > MaxInputTotal {
			return nil, fault.New("MAX_INPUTS", "completion workspace exceeds 256 MiB")
		}
		if norm, ok := norms[path]; ok {
			if kind != "file" {
				return nil, fault.New("WORKSPACE_DRIFT", "canonical artifact changed type")
			}
			kind, data = "artifact_normative", []byte(norm)
		}
		completionHashPart(content, []byte(path))
		completionHashPart(content, []byte(entries[path]+":"+kind))
		completionHashPart(content, data)
	}
	if normalize {
		status, err = completionNormalizedStatus(status, outputs, norms)
		if err != nil {
			return nil, err
		}
	}
	head, err := completionGitText(root, "rev-parse", "HEAD")
	if err != nil {
		return nil, err
	}
	return map[string]any{"root": root, "filesystem_id": binding["workspace_filesystem_id"], "git_common_dir": binding["git_common_dir"], "git_common_filesystem_id": binding["git_common_filesystem_id"], "head": head, "status_sha256": canonical.BytesHash([]byte(status)), "content_sha256": fmt.Sprintf("%x", content.Sum(nil))}, nil
}

func completionHashPart(h hash.Hash, data []byte) {
	var length [8]byte
	binary.BigEndian.PutUint64(length[:], uint64(len(data)))
	h.Write(length[:])
	h.Write(data)
}

func completionWithin(root, path string) bool {
	rel, err := filepath.Rel(root, path)
	return err == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator)) && !filepath.IsAbs(rel)
}

// filepath.EvalSymlinks requires the final file to exist; the producer also
// fingerprints dangling links, so resolve the existing components explicitly.
func completionResolveMissing(path string, depth int) (string, error) {
	if depth > 128 {
		return "", fault.New("WORKSPACE_DRIFT", "workspace symlink resolution exceeds bound")
	}
	parent := filepath.Dir(path)
	if parent == path {
		return path, nil
	}
	resolved, err := completionResolveMissing(parent, depth+1)
	if err != nil {
		return "", err
	}
	candidate := filepath.Join(resolved, filepath.Base(path))
	info, err := os.Lstat(candidate)
	if os.IsNotExist(err) {
		return candidate, nil
	}
	if err != nil {
		return "", err
	}
	if info.Mode()&os.ModeSymlink != 0 {
		target, err := os.Readlink(candidate)
		if err != nil {
			return "", err
		}
		if !filepath.IsAbs(target) {
			target = filepath.Join(resolved, target)
		}
		return completionResolveMissing(filepath.Clean(target), depth+1)
	}
	if completionReparse(info) {
		return "", fault.New("WORKSPACE_DRIFT", "workspace member traverses reparse indirection")
	}
	return candidate, nil
}

func completionMember(f *store.FS, relative, mode string) (string, []byte, error) {
	bad := func() (string, []byte, error) {
		return "", nil, fault.New("WORKSPACE_DRIFT", "workspace content cannot be frozen")
	}
	if relative == "" || strings.Contains(relative, "\\") || strings.HasPrefix(relative, "/") || filepath.IsAbs(relative) || filepath.ToSlash(filepath.Clean(relative)) != relative {
		return bad()
	}
	candidate := filepath.Join(f.Root, filepath.FromSlash(relative))
	parent, err := completionResolveMissing(filepath.Dir(candidate), 0)
	if err != nil || !completionWithin(f.Root, parent) {
		return bad()
	}
	info, err := os.Lstat(candidate)
	if os.IsNotExist(err) && mode != "untracked" {
		return "deleted", []byte{}, nil
	}
	if err != nil {
		return bad()
	}
	if info.Mode()&os.ModeSymlink != 0 {
		if mode != "120000" && mode != "untracked" {
			return bad()
		}
		resolved, err := completionResolveMissing(candidate, 0)
		if err != nil || !completionWithin(f.Root, resolved) {
			return bad()
		}
		target, err := os.Readlink(candidate)
		if err != nil {
			return bad()
		}
		resolvedRel, err := filepath.Rel(f.Root, resolved)
		if err != nil {
			return bad()
		}
		data := []byte(target + "\x00" + filepath.ToSlash(resolvedRel))
		targetInfo, err := os.Lstat(resolved)
		if os.IsNotExist(err) {
			return "dangling-symlink", data, nil
		}
		if err != nil || !targetInfo.Mode().IsRegular() || completionReparse(targetInfo) {
			return bad()
		}
		targetData, err := f.Read(filepath.ToSlash(resolvedRel), MaxInputFile)
		if err != nil {
			return "", nil, err
		}
		return "symlink", append(append(data, 0), targetData...), nil
	}
	if completionReparse(info) {
		return bad()
	}
	if info.Mode().IsRegular() && mode != "160000" {
		// Windows locks the first byte even for the engine's empty lock file.
		// Prove the exact rooted file is empty without opening a conflicting
		// read handle; it still contributes its path, mode, type and zero bytes
		// to the raw producer fingerprint (it is not an exclusion).
		if relative == ".codearbiter/.artifacts/store.lock" && info.Size() == 0 {
			pinned, err := f.Stat(relative)
			if err != nil || !pinned.Mode().IsRegular() || pinned.Size() != 0 {
				return bad()
			}
			return "file", []byte{}, nil
		}
		data, err := f.Read(relative, MaxInputFile)
		kind := "file"
		if mode == "120000" {
			kind = "materialized-symlink"
		}
		return kind, data, err
	}
	if info.IsDir() && mode == "160000" {
		top, err := completionResolvedGitPath(candidate, "rev-parse", "--show-toplevel")
		if err != nil {
			return bad()
		}
		if !completionSamePath(top, candidate) {
			files, err := os.ReadDir(candidate)
			if err != nil || len(files) != 0 {
				return bad()
			}
			return "uninitialized-gitlink", []byte{}, nil
		}
		status, err := completionGitText(candidate, "status", "--porcelain", "--untracked-files=all")
		if err != nil || status != "" {
			return bad()
		}
		head, err := completionGitText(candidate, "rev-parse", "HEAD")
		if err != nil {
			return bad()
		}
		return "gitlink", []byte(head), nil
	}
	return bad()
}

func completionNormalizedStatus(status string, outputs map[string]bool, norms map[string]string) (string, error) {
	records := strings.Split(status, "\x00")
	var out strings.Builder
	for i := 0; i < len(records); i++ {
		record := records[i]
		if record == "" {
			continue
		}
		fields, normSafe := []string{}, false
		switch record[0] {
		case '?':
			fields = strings.SplitN(record, " ", 2)
			normSafe = true
		case '1':
			fields = strings.SplitN(record, " ", 9)
			normSafe = len(fields) == 9 && fields[3] == fields[4] && fields[4] == fields[5]
			// A newly staged canonical artifact has no HEAD mode. Its typed
			// progress write changes A. to AM without changing the selected
			// normative content. Keep requiring equal regular index/worktree
			// modes; the content closure independently retains that index mode.
			if len(fields) == 9 && (fields[1] == "A." || fields[1] == "AM") && fields[3] == "000000" && fields[4] == fields[5] && (fields[4] == "100644" || fields[4] == "100755") {
				normSafe = true
			}
		case '2':
			fields = strings.SplitN(record, " ", 10)
		case 'u':
			fields = strings.SplitN(record, " ", 11)
		default:
			return "", fault.New("WORKSPACE_DRIFT", "unrecognized Git workspace status")
		}
		expected := map[byte]int{'?': 2, '1': 9, '2': 10, 'u': 11}[record[0]]
		if len(fields) != expected {
			return "", fault.New("WORKSPACE_DRIFT", "malformed Git workspace status")
		}
		path := fields[len(fields)-1]
		_, canonicalArtifact := norms[path]
		omit := outputs[path] || (canonicalArtifact && normSafe)
		if !omit {
			out.WriteString(record)
			out.WriteByte(0)
		}
		if record[0] == '2' {
			i++
			if i >= len(records) || records[i] == "" {
				return "", fault.New("WORKSPACE_DRIFT", "incomplete Git rename status")
			}
			if !omit {
				out.WriteString(records[i])
				out.WriteByte(0)
			}
		}
	}
	return out.String(), nil
}

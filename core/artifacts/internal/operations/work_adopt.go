package operations

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"regexp"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

const legacyBoardPath = ".codearbiter/open-tasks.md"
const legacyArchivePath = ".codearbiter/done-tasks.md"

var legacyAliasPattern = regexp.MustCompile(`^[a-z][a-z0-9]*\.[a-z][a-z0-9]*\.[0-9]{4,}$`)
var legacyStrayMarkerPattern = regexp.MustCompile(`^\s*[-*+]?\s*\[[ xX~]\]`)
var legacyCanonicalTaskPattern = regexp.MustCompile(`^- \[[ xX~]\] `)

func digestBytes(b []byte) string { return fmt.Sprintf("%x", sha256.Sum256(b)) }

// Each accepted row must name one exact top-level board block. The original
// board bytes are saved separately; this parser is only a coverage check.
func adoptionBlocks(raw []byte) (map[int64]string, error) {
	if !utf8.Valid(raw) || strings.Contains(strings.ReplaceAll(string(raw), "\r\n", ""), "\r") {
		return nil, fault.New("INVALID_LEGACY_BOARD", "legacy board is not canonical UTF-8 line text")
	}
	lines := strings.Split(strings.ReplaceAll(string(raw), "\r\n", "\n"), "\n")
	if len(lines) > 0 && lines[len(lines)-1] == "" {
		lines = lines[:len(lines)-1]
	}
	blocks := map[int64]string{}
	for i, line := range lines {
		if legacyStrayMarkerPattern.MatchString(line) && !legacyCanonicalTaskPattern.MatchString(line) {
			return nil, fault.New("INVALID_LEGACY_BOARD", "legacy board has a malformed task marker")
		}
		if !strings.HasPrefix(line, "- ") {
			continue
		}
		if strings.TrimSpace(line[2:]) == "" {
			return nil, fault.New("INVALID_LEGACY_BOARD", "legacy board has an empty task row")
		}
		end := i + 1
		for end < len(lines) {
			current := lines[end]
			if strings.HasPrefix(current, "- ") || (strings.TrimSpace(current) != "" && current[0] != ' ' && current[0] != '\t') {
				break
			}
			end++
		}
		for end > i+1 && strings.TrimSpace(lines[end-1]) == "" {
			end--
		}
		blocks[int64(i+1)] = digestBytes([]byte(strings.Join(lines[i:end], "\n")))
	}
	return blocks, nil
}

func (e *Engine) workAdopt(r object) (any, error) {
	unlock, err := lockLegacyBoard(e.FS.Root)
	if err != nil {
		return nil, err
	}
	defer unlock()
	if projectID, _, err := e.projectIdentity(); err != nil {
		return nil, err
	} else if projectID != "" {
		return nil, fault.At("NATIVE_OWNER_EXISTS", "", projectPath, "native work already owns this project")
	}
	entries, err := e.FS.List(".codearbiter/work")
	if err != nil && !os.IsNotExist(err) {
		return nil, err
	}
	if len(entries) != 0 {
		return nil, fault.At("NATIVE_OWNER_EXISTS", "", ".codearbiter/work", "native work files already exist")
	}
	board, err := e.FS.Read(legacyBoardPath, 1<<20)
	if os.IsNotExist(err) {
		return nil, fault.At("LEGACY_OWNER_MISSING", "", legacyBoardPath, "legacy board no longer owns this project")
	}
	if err != nil {
		return nil, err
	}
	archive, err := e.FS.Read(legacyArchivePath, canonical.MaxBytes)
	if os.IsNotExist(err) {
		archive = nil
	} else if err != nil {
		return nil, err
	}
	if digestBytes(board) != model.S(r["expected_board_sha256"]) ||
		(archive == nil && r["expected_archive_sha256"] != nil) ||
		(archive != nil && digestBytes(archive) != model.S(r["expected_archive_sha256"])) {
		return nil, fault.New("REVISION_CONFLICT", "legacy board changed after the adoption inventory")
	}
	openBlocks, err := adoptionBlocks(board)
	if err != nil {
		return nil, err
	}
	archiveBlocks := map[int64]string{}
	if archive != nil {
		archiveBlocks, err = adoptionBlocks(archive)
		if err != nil {
			return nil, err
		}
	}
	rows := model.A(r["rows"])
	if len(rows) != len(openBlocks)+len(archiveBlocks) {
		return nil, fault.New("INCOMPLETE_ADOPTION", "every legacy task row needs one native work item")
	}
	// A process may die while staging before the journal is published. Repeating
	// the same selected cutover must derive identical portable bytes.
	projectSeed := sha256.Sum256([]byte("codearbiter-work-adopt-v1\x00" + model.S(r["operation_id"]) + "\x00" + digestBytes(board) + "\x00" + model.S(r["expected_archive_sha256"])))
	projectID := "PROJECT-" + strings.ToUpper(hex.EncodeToString(projectSeed[:16]))
	projectAfter, err := canonical.Marshal(object{"format": "codearbiter.project", "version": int64(1), "owner": "native", "project_id": projectID})
	if err != nil {
		return nil, err
	}
	edits := []store.Edit{{Path: projectPath, Before: nil, After: projectAfter}}
	seenIDs, seenOrigins, seenAliases, seenLines := map[string]bool{}, map[string]bool{}, map[string]bool{}, map[string]bool{}
	type binding struct{ specPath, planPath string }
	bindings := map[string]binding{}
	for _, value := range rows {
		row := model.M(value)
		id, origin, location, alias := model.S(row["work_id"]), model.S(row["origin"]), model.S(row["location"]), model.S(row["alias"])
		line := model.I(row["line"])
		key := fmt.Sprintf("%s:%d", location, line)
		blocks := openBlocks
		if location == "archive" {
			blocks = archiveBlocks
		}
		if !workIDPattern.MatchString(id) || seenIDs[id] || seenOrigins[origin] || (alias != "" && (seenAliases[alias] || !legacyAliasPattern.MatchString(alias))) || seenLines[key] || blocks[line] == "" || blocks[line] != model.S(row["block_sha256"]) {
			return nil, fault.New("INVALID_ADOPTION", "legacy row identity, alias or block digest is invalid")
		}
		seenIDs[id], seenOrigins[origin], seenLines[key] = true, true, true
		if alias != "" {
			seenAliases[alias] = true
		}
		state := model.S(row["state"])
		if (location == "archive") != (state == "archived") {
			return nil, fault.New("INVALID_ADOPTION", "archive and work state disagree")
		}
		for _, date := range []string{model.S(row["started_at"]), model.S(row["completed_at"])} {
			if date != "" {
				if _, err := time.Parse("2006-01-02", date); err != nil {
					return nil, fault.New("INVALID_ADOPTION", "legacy work date is invalid")
				}
			}
		}
		specID, planID := model.S(row["spec_id"]), model.S(row["plan_id"])
		bindingKey := specID + "\x00" + planID
		resolved, ok := bindings[bindingKey]
		if !ok {
			specPath, planPath, err := e.checkWorkBinding(specID, planID)
			if err != nil {
				return nil, err
			}
			resolved = binding{specPath, planPath}
			bindings[bindingKey] = resolved
		}
		norm := object{"project_id": projectID, "title": row["title"], "summary": row["intent"], "work_type": row["work_type"], "spec_id": nil, "plan_id": nil, "spec_path": nil, "plan_path": nil, "origin": origin, "aliases": []any{}}
		if alias != "" {
			norm["aliases"] = []any{alias}
		}
		if specID != "" {
			norm["spec_id"], norm["spec_path"] = specID, resolved.specPath
		}
		if planID != "" {
			norm["plan_id"], norm["plan_path"] = planID, resolved.planPath
		}
		v := object{"format": model.Format, "format_version": model.FormatVersion, "kind": "work", "schema_version": model.SchemaVersion,
			"artifact_id": id, "slug": "work-" + strings.ToLower(strings.TrimPrefix(id, "WORK-")), "revision": int64(1), "presentation": render.Presentation(""),
			"normative": norm, "execution": object{"state": state, "check_status": "unknown", "started_at": row["started_at"], "completed_at": row["completed_at"]}}
		d, err := render.Prepare(v)
		if err != nil {
			return nil, err
		}
		b, err := render.Render(d)
		if err != nil {
			return nil, err
		}
		edits = append(edits, store.Edit{Path: workPath(id), Before: nil, After: b})
	}
	if err := e.FS.Mkdir(".codearbiter/work"); err != nil {
		return nil, err
	}
	if err := e.FS.Mkdir(".codearbiter/legacy"); err != nil {
		return nil, err
	}
	edits = append(edits, store.Edit{Path: ".codearbiter/legacy/open-tasks.md", Before: nil, After: board}, store.Edit{Path: legacyBoardPath, Before: board, After: nil})
	if archive != nil {
		edits = append(edits, store.Edit{Path: ".codearbiter/legacy/done-tasks.md", Before: nil, After: archive}, store.Edit{Path: legacyArchivePath, Before: archive, After: nil})
	}
	result := object{"project_id": projectID, "adopted_count": int64(len(rows)), "legacy_open_sha256": digestBytes(board), "legacy_archive_sha256": r["expected_archive_sha256"], "owner": "native"}
	outcome, err := e.FS.Commit(model.S(r["operation_id"]), e.RequestHash, edits, result)
	if err != nil {
		return nil, err
	}
	return mutationResult(outcome), nil
}

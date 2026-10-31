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
var legacyFencePattern = regexp.MustCompile("^ {0,3}(`{3,}|~{3,})(.*)$")
var legacyOriginRefPattern = regexp.MustCompile(`\(from ([^()\r\n]+)\)`)
var legacyTitleBackrefPattern = regexp.MustCompile(`\(from\s+[^)]*\)`)
var legacySourceOriginPattern = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9:._-]{0,127}#[A-Za-z0-9][A-Za-z0-9:._-]{0,127}$`)
var legacyIDishPattern = regexp.MustCompile(`^[^\s.]+(?:\.[^\s.]+){2,}$`)
var legacyDatePattern = regexp.MustCompile(`\((started|done)\s+([^)]*)\)`)
var legacyTrailingDatePattern = regexp.MustCompile(`\s*\((?:started|done)\s+[^)]*\)\s*$`)
var legacySubfieldPattern = regexp.MustCompile(`^\s+-\s*([^:]+):\s*(.*)$`)
var legacyMetadataPattern = regexp.MustCompile(`^  - (Work origin|Work type|Work ID|Work operation ID|Spec ID|Plan ID): (.*)$`)

const legacyScaffoldSchema = "Schema (one task = a lifecycle line + indented content sub-bullets):"

var legacyScaffoldNotes = map[string]bool{
	"- Marker: `[ ]` queued | `[~]` in-progress | `[x]` done. In-progress and done":   true,
	"- ID `<group>.<type>.<seq>`: `group` = build phase (poc/mvp1/v1...), `type` =":   true,
	"- `Desc` / `Done when` / `Boundaries` are filled when known (`TBD` until then).": true,
}

func digestBytes(b []byte) string { return fmt.Sprintf("%x", sha256.Sum256(b)) }

// One cutover reserves five edits for the project, board snapshots and board removal.
const maxAdoptionRows = 507

// Each accepted row must name one exact top-level board block. The original
// board bytes are saved separately; this parser is only a coverage check.
type legacyAdoptionBlock struct {
	digest string
	text   string
}

func adoptionBlocks(raw []byte) (map[int64]legacyAdoptionBlock, error) {
	if !utf8.Valid(raw) || strings.Contains(strings.ReplaceAll(string(raw), "\r\n", ""), "\r") {
		return nil, fault.New("INVALID_LEGACY_BOARD", "legacy board is not canonical UTF-8 line text")
	}
	lines := strings.Split(strings.ReplaceAll(string(raw), "\r\n", "\n"), "\n")
	if len(lines) > 0 && lines[len(lines)-1] == "" {
		lines = lines[:len(lines)-1]
	}
	skipped := make([]bool, len(lines))
	fenceChar, fenceWidth := byte(0), 0
	scaffold, beforeSection := false, true
	for i, line := range lines {
		marker := legacyFencePattern.FindStringSubmatch(line)
		if fenceChar != 0 {
			skipped[i] = true
			if marker != nil && marker[1][0] == fenceChar && len(marker[1]) >= fenceWidth && strings.TrimSpace(marker[2]) == "" {
				fenceChar, fenceWidth = 0, 0
			}
			continue
		}
		if marker != nil {
			fenceChar, fenceWidth = marker[1][0], len(marker[1])
			skipped[i] = true
			continue
		}
		if strings.HasPrefix(line, "## ") {
			beforeSection = false
		}
		if beforeSection && line == legacyScaffoldSchema {
			scaffold = true
		}
		if scaffold && beforeSection && strings.HasPrefix(line, "- ") {
			if legacyScaffoldNotes[line] {
				skipped[i] = true
			} else if !legacyCanonicalTaskPattern.MatchString(line) {
				return nil, fault.New("INVALID_LEGACY_BOARD", "unaccounted scaffold preamble bullet")
			}
		}
	}
	if fenceChar != 0 {
		return nil, fault.New("INVALID_LEGACY_BOARD", "unterminated Markdown fence in legacy board")
	}
	blocks := map[int64]legacyAdoptionBlock{}
	for i, line := range lines {
		if skipped[i] {
			continue
		}
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
		text := strings.Join(lines[i:end], "\n")
		blocks[int64(i+1)] = legacyAdoptionBlock{digest: digestBytes([]byte(text)), text: text}
	}
	return blocks, nil
}

// Read a selected historical block through its portable source pointer. The
// saved board is immutable source evidence, never another writable work owner.
func (e *Engine) legacyDetailPage(source object, offset, budget int64) (object, error) {
	location := model.S(source["location"])
	path := ".codearbiter/legacy/open-tasks.md"
	if location == "archive" {
		path = ".codearbiter/legacy/done-tasks.md"
	} else if location != "open" {
		return nil, fault.New("INVALID_LEGACY_SOURCE", "selected work has an invalid historical source")
	}
	raw, err := e.FS.Read(path, canonical.MaxBytes)
	if os.IsNotExist(err) {
		return nil, fault.At("STALE_LEGACY_SOURCE", "", path, "selected historical board is absent")
	}
	if err != nil {
		return nil, err
	}
	blocks, err := adoptionBlocks(raw)
	if err != nil {
		return nil, fault.At("STALE_LEGACY_SOURCE", "", path, "selected historical board is invalid")
	}
	block, ok := blocks[model.I(source["line"])]
	if !ok || block.digest != model.S(source["block_sha256"]) {
		return nil, fault.At("STALE_LEGACY_SOURCE", "", path, "selected historical task block changed")
	}
	content := []byte(block.text)
	if offset < 0 || offset > int64(len(content)) || offset < int64(len(content)) && !utf8.RuneStart(content[offset]) {
		return nil, fault.New("INVALID_LEGACY_OFFSET", "selected historical detail offset is outside a UTF-8 boundary")
	}
	limit := budget / 4
	if limit > 4096 {
		limit = 4096
	}
	end := offset + limit
	if end > int64(len(content)) {
		end = int64(len(content))
	}
	for end < int64(len(content)) && end > offset && !utf8.RuneStart(content[end]) {
		end--
	}
	if end == offset && end < int64(len(content)) {
		return nil, fault.New("INVALID_LEGACY_OFFSET", "selected historical detail cannot fit its page")
	}
	var next any
	if end < int64(len(content)) {
		next = end
	}
	return object{"source": source, "text": string(content[offset:end]), "offset": offset,
		"next_offset": next, "total_bytes": int64(len(content))}, nil
}

// Derive every portable field from the exact hashed block. The Python
// inventory is a preview, not authority for a destructive ownership cutover.
func canonicalAdoptionRow(block legacyAdoptionBlock, location string, line int64) (object, error) {
	lines := strings.Split(block.text, "\n")
	if len(lines) == 0 || !strings.HasPrefix(lines[0], "- ") {
		return nil, fault.New("INVALID_ADOPTION", "legacy task block is malformed")
	}
	raw := lines[0]
	body := strings.TrimSpace(raw[2:])
	state := "queued"
	if len(body) >= 4 && body[0] == '[' && body[2] == ']' && body[3] == ' ' {
		switch body[1] {
		case ' ':
			state = "queued"
		case '~':
			state = "active"
		case 'x', 'X':
			state = "complete"
		default:
			return nil, fault.New("INVALID_ADOPTION", "legacy task marker is invalid")
		}
		body = strings.TrimSpace(body[4:])
	}
	if body == "" {
		return nil, fault.New("INVALID_ADOPTION", "legacy task title is empty")
	}
	alias, titleBody := "", body
	parts := strings.Fields(body)
	if len(parts) > 0 && legacyIDishPattern.MatchString(parts[0]) {
		alias = parts[0]
		titleBody = strings.TrimSpace(strings.TrimPrefix(body, alias))
		titleBody = strings.TrimSpace(strings.TrimLeft(titleBody, "—–-"))
	}
	metadata := map[string]string{}
	desc := ""
	for _, subline := range lines[1:] {
		if strings.HasPrefix(subline, "  - Work ") || strings.HasPrefix(subline, "  - Spec ID:") || strings.HasPrefix(subline, "  - Plan ID:") {
			match := legacyMetadataPattern.FindStringSubmatch(subline)
			if match == nil {
				return nil, fault.New("INVALID_ADOPTION", "legacy work metadata is ambiguous")
			}
			if _, exists := metadata[match[1]]; exists {
				return nil, fault.New("INVALID_ADOPTION", "legacy work metadata is ambiguous")
			}
			metadata[match[1]] = match[2]
		}
		if match := legacySubfieldPattern.FindStringSubmatch(subline); match != nil && strings.EqualFold(strings.TrimSpace(match[1]), "desc") {
			desc = strings.TrimSpace(match[2])
		}
	}
	refs := legacyOriginRefPattern.FindAllStringSubmatch(raw, -1)
	legacyOrigin := ""
	if source, present := metadata["Work origin"]; present {
		if len(refs) == 0 || refs[len(refs)-1][1] != source {
			return nil, fault.New("INVALID_ADOPTION", "legacy origin metadata disagrees with its task row")
		}
		legacyOrigin = source
	} else if len(refs) > 1 {
		return nil, fault.New("INVALID_ADOPTION", "legacy task has ambiguous origin markers")
	} else if len(refs) == 1 {
		legacyOrigin = refs[0][1]
	}
	origin := legacyOrigin
	if origin != "" && !legacySourceOriginPattern.MatchString(origin) {
		origin = "legacy:origin#" + digestBytes([]byte(origin))[:32]
	}
	if origin == "" {
		seed := fmt.Sprintf("%s\x00%d\x00%s", location, line, block.text)
		origin = "legacy:" + location + "#" + digestBytes([]byte(seed))[:32]
	}
	id := metadata["Work ID"]
	if id == "" {
		source := origin
		if legacyOrigin != "" {
			source = legacyOrigin
		}
		id = "WORK-" + strings.ToUpper(digestBytes([]byte("codearbiter-legacy-work-v1\x00" + source))[:32])
	}
	title := titleBody
	if legacyOrigin != "" {
		// The legacy work reader removes its final origin marker before trimming
		// trailing whitespace. Preserve that order for imported titles.
		title = raw[2:]
		if len(title) >= 3 && title[0] == '[' && title[2] == ']' {
			title = strings.TrimLeft(title[3:], " \t")
		}
		if alias != "" {
			title = strings.TrimLeft(strings.TrimPrefix(title, alias), " \t")
			title = strings.TrimLeft(title, "—–-")
			title = strings.TrimLeft(title, " \t")
		}
		title = legacyTrailingDatePattern.ReplaceAllString(title, "")
		title = strings.TrimSpace(strings.TrimSuffix(title, "(from "+legacyOrigin+")"))
		title = strings.TrimSpace(legacyTrailingDatePattern.ReplaceAllString(title, ""))
	} else {
		title = strings.TrimSpace(legacyDatePattern.ReplaceAllString(title, ""))
		title = strings.TrimSpace(legacyTitleBackrefPattern.ReplaceAllString(title, ""))
	}
	if title == "" {
		return nil, fault.New("INVALID_ADOPTION", "legacy task title is empty")
	}
	intent := desc
	if intent == "" {
		intent = title
	}
	workType := metadata["Work type"]
	if workType == "" {
		workType = "unknown"
	}
	if location == "archive" {
		state = "archived"
	}
	var started, completed any
	for _, match := range legacyDatePattern.FindAllStringSubmatch(body, -1) {
		date := strings.TrimSpace(match[2])
		parsed, err := time.Parse("2006-1-2", date)
		if err != nil {
			continue
		}
		date = parsed.Format("2006-01-02")
		if match[1] == "started" && started == nil {
			started = date
		} else if match[1] == "done" && completed == nil {
			completed = date
		}
	}
	return object{"work_id": id, "origin": origin, "alias": alias, "title": title,
		"intent": intent, "work_type": workType, "state": state,
		"started_at": started, "completed_at": completed,
		"spec_id": metadata["Spec ID"], "plan_id": metadata["Plan ID"]}, nil
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
	archiveBlocks := map[int64]legacyAdoptionBlock{}
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
		block, found := blocks[line]
		if !workIDPattern.MatchString(id) || seenIDs[id] || seenOrigins[origin] || (alias != "" && (seenAliases[alias] || !legacyAliasPattern.MatchString(alias))) || seenLines[key] || !found || block.digest != model.S(row["block_sha256"]) {
			return nil, fault.New("INVALID_ADOPTION", "legacy row identity, alias or block digest is invalid")
		}
		canonical, err := canonicalAdoptionRow(block, location, line)
		if err != nil {
			return nil, err
		}
		for _, field := range []string{"work_id", "origin", "alias", "title", "intent", "work_type", "state", "started_at", "completed_at", "spec_id", "plan_id"} {
			if model.S(canonical[field]) != model.S(row[field]) {
				return nil, fault.New("INVALID_ADOPTION", "legacy row fields disagree with the selected source block")
			}
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
		norm := object{"project_id": projectID, "title": row["title"], "summary": row["intent"], "work_type": row["work_type"], "spec_id": nil, "plan_id": nil, "spec_path": nil, "plan_path": nil, "origin": origin, "aliases": []any{},
			"legacy_source": object{"location": location, "line": line, "block_sha256": block.digest}}
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

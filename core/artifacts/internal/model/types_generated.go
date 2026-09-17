// Code generated from the packaged, closed schemas. DO NOT EDIT.
package model

import "encoding/json"

type Block = json.RawMessage
type Section struct {
	ID     string  `json:"id"`
	Title  string  `json:"title"`
	Blocks []Block `json:"blocks"`
}
type Scope struct {
	ID        string `json:"id"`
	Statement string `json:"statement"`
}
type Decision struct {
	ID        string  `json:"id"`
	Topic     string  `json:"topic"`
	Choice    string  `json:"choice"`
	Rationale string  `json:"rationale"`
	Authority string  `json:"authority"`
	SourceRef *string `json:"source_ref,omitempty"`
}
type Source struct {
	ID      string  `json:"id"`
	Title   string  `json:"title"`
	Type    string  `json:"type"`
	URL     *string `json:"url"`
	Locator string  `json:"locator"`
	Note    string  `json:"note"`
}
type Baseline struct {
	Repository   *string `json:"repository"`
	Commit       *string `json:"commit"`
	ObservedDate string  `json:"observed_date"`
}
type Scenario struct {
	ID    string `json:"id"`
	Given string `json:"given,omitempty"`
	When  string `json:"when,omitempty"`
	Then  string `json:"then,omitempty"`
}
type Verification struct {
	ID              string `json:"id"`
	Method          string `json:"method,omitempty"`
	PlannedTarget   string `json:"planned_target,omitempty"`
	Oracle          string `json:"oracle,omitempty"`
	NegativeControl string `json:"negative_control,omitempty"`
	EvidenceState   string `json:"evidence_state,omitempty"`
}
type Criterion struct {
	ID             string        `json:"id"`
	Title          string        `json:"title"`
	Kind           string        `json:"kind,omitempty"`
	Obligation     string        `json:"obligation,omitempty"`
	IntentRefs     []string      `json:"intent_refs,omitempty"`
	Statement      string        `json:"statement,omitempty"`
	Preconditions  []string      `json:"preconditions,omitempty"`
	Trigger        string        `json:"trigger,omitempty"`
	Guarantees     []string      `json:"guarantees,omitempty"`
	Scenarios      []Scenario    `json:"scenarios,omitempty"`
	Verification   *Verification `json:"verification,omitempty"`
	SourceRefs     []string      `json:"source_refs,omitempty"`
	Applicability  Applicability `json:"applicability,omitempty"`
	ConstraintRefs []string      `json:"constraint_refs,omitempty"`
}
type OpenDecision struct {
	ID         string   `json:"id"`
	Question   string   `json:"question"`
	Blocking   bool     `json:"blocking"`
	Affects    []string `json:"affects"`
	SourceRef  string   `json:"source_ref"`
	Owner      string   `json:"owner"`
	Status     string   `json:"status"`
	Resolution *string  `json:"resolution"`
}
type Path struct {
	Path   string `json:"path"`
	Action string `json:"action"`
}
type Command struct {
	Availability  string   `json:"availability"`
	CWD           string   `json:"cwd"`
	Argv          []string `json:"argv"`
	ExpectedExit  int64    `json:"expected_exit"`
	Assertion     string   `json:"assertion"`
	RequiredTests []string `json:"required_tests"`
}
type Task struct {
	ID             string    `json:"id"`
	Title          string    `json:"title"`
	Checkpoint     string    `json:"checkpoint"`
	DependsOn      []string  `json:"depends_on,omitempty"`
	Paths          []Path    `json:"paths,omitempty"`
	CriterionRefs  []string  `json:"criterion_refs,omitempty"`
	Steps          []string  `json:"steps,omitempty"`
	Verification   []Command `json:"verification,omitempty"`
	DoneWhen       []string  `json:"done_when,omitempty"`
	Rollback       string    `json:"rollback,omitempty"`
	SourceRefs     []string  `json:"source_refs,omitempty"`
	ExecutionScope string    `json:"execution_scope"`
}
type Checkpoint struct {
	ID        string   `json:"id"`
	Title     string   `json:"title"`
	Tasks     []string `json:"tasks"`
	Exit      string   `json:"exit"`
	DependsOn []string `json:"depends_on"`
}
type Prerequisite struct {
	ID          string   `json:"id"`
	Title       string   `json:"title"`
	Requirement string   `json:"requirement"`
	SourceRefs  []string `json:"source_refs"`
}
type SpecRef struct {
	ArtifactID      string `json:"artifact_id"`
	NormativeSHA256 string `json:"normative_sha256"`
	BindingMode     string `json:"binding_mode"`
}
type Approval struct {
	AuthorityKind    string `json:"authority_kind"`
	SourceRef        string `json:"source_ref"`
	NormativeSHA256  string `json:"normative_sha256"`
	AttestationLevel string `json:"attestation_level"`
	SourceSHA256     string `json:"source_sha256"`
	ArtifactID       string `json:"artifact_id"`
}
type Governance struct {
	State       string     `json:"state"`
	Approvals   []Approval `json:"approvals"`
	ReviewNotes []string   `json:"review_notes"`
}
type Presentation struct {
	Renderer         string  `json:"renderer"`
	BrandName        string  `json:"brand_name"`
	LogoDataUri      string  `json:"logo_data_uri"`
	LogoOrigin       string  `json:"logo_origin"`
	LogoGitBlob      *string `json:"logo_git_blob"`
	CompanionPath    string  `json:"companion_path"`
	StylesheetSHA256 string  `json:"stylesheet_sha256"`
}
type Integrity struct {
	NormativeSHA256 string `json:"normative_sha256"`
	ModelSHA256     string `json:"model_sha256"`
	SymbolCount     int64  `json:"symbol_count"`
}
type TaskState struct {
	State        string   `json:"state"`
	EvidenceRefs []string `json:"evidence_refs"`
	Reason       *string  `json:"reason"`
}
type Retired struct {
	ID                string  `json:"id"`
	RetiredInRevision int64   `json:"retired_in_revision"`
	ReplacementRef    *string `json:"replacement_ref"`
	Reason            string  `json:"reason"`
}
type Intent struct {
	ID         string   `json:"id"`
	Problem    string   `json:"problem,omitempty"`
	Caller     string   `json:"caller,omitempty"`
	Outcome    string   `json:"outcome,omitempty"`
	SourceRefs []string `json:"source_refs,omitempty"`
}
type Approach struct {
	ID                  string   `json:"id"`
	Choice              string   `json:"choice,omitempty"`
	Tradeoff            string   `json:"tradeoff,omitempty"`
	BindingDecisionRefs []string `json:"binding_decision_refs,omitempty"`
}
type Constraint struct {
	ID         string   `json:"id"`
	Statement  string   `json:"statement"`
	AppliesTo  []string `json:"applies_to"`
	SourceRefs []string `json:"source_refs"`
}
type Applicability struct {
	Mode      string `json:"mode"`
	Rationale string `json:"rationale"`
}
type CriterionDisposition struct {
	CriterionRef string `json:"criterion_ref"`
	Disposition  string `json:"disposition"`
	Rationale    string `json:"rationale"`
}
type Spec struct {
	RetiredSymbols []Retired      `json:"retired_symbols"`
	Title          string         `json:"title"`
	Summary        string         `json:"summary"`
	Baseline       Baseline       `json:"baseline"`
	Sections       []Section      `json:"sections"`
	Sources        []Source       `json:"sources"`
	Scope          []Scope        `json:"scope"`
	NonGoals       []Scope        `json:"non_goals"`
	Decisions      []Decision     `json:"decisions"`
	Criteria       []Criterion    `json:"criteria"`
	Governs        []string       `json:"governs"`
	OpenDecisions  []OpenDecision `json:"open_decisions"`
	Intent         Intent         `json:"intent"`
	Approach       Approach       `json:"approach"`
	Constraints    []Constraint   `json:"constraints"`
}
type Plan struct {
	RetiredSymbols        []Retired                  `json:"retired_symbols"`
	Title                 string                     `json:"title"`
	Summary               string                     `json:"summary"`
	Baseline              Baseline                   `json:"baseline"`
	Sections              []Section                  `json:"sections"`
	Sources               []Source                   `json:"sources"`
	SpecRef               SpecRef                    `json:"spec_ref"`
	Tasks                 []Task                     `json:"tasks"`
	Checkpoints           []Checkpoint               `json:"checkpoints"`
	Prerequisites         []Prerequisite             `json:"prerequisites"`
	CriterionDispositions []CriterionDisposition     `json:"criterion_dispositions"`
	VerificationInputs    map[string]json.RawMessage `json:"verification_inputs"`
}

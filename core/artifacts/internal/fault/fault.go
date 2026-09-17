// Package fault defines stable, bounded protocol diagnostics.
package fault

import (
	"errors"
	"fmt"
)

type Error struct {
	Code        string `json:"code"`
	Message     string `json:"message"`
	Symbol      string `json:"symbol,omitempty"`
	Field       string `json:"field,omitempty"`
	OperationID string `json:"operation_id,omitempty"`
}

func (e *Error) Error() string       { return e.Code + ": " + e.Message }
func New(code, message string) error { return &Error{Code: code, Message: message} }
func At(code, symbol, field, message string) error {
	return &Error{Code: code, Symbol: symbol, Field: field, Message: message}
}
func Wrap(code string, err error) error {
	if err == nil {
		return nil
	}
	var f *Error
	if errors.As(err, &f) {
		return err
	}
	return New(code, err.Error())
}
func Code(err error) string {
	var f *Error
	if errors.As(err, &f) {
		return f.Code
	}
	return "INTERNAL_ERROR"
}
func Exit(err error) int {
	switch Code(err) {
	case "REVISION_CONFLICT", "ALREADY_EXISTS", "OPERATION_REPLAY_MISMATCH", "OPERATION_ID_REUSE", "LEGACY_CONFLICT", "CONCURRENT_CHANGE":
		return 3
	case "AUTHORITY_UNVERIFIED", "STALE_BINDING", "EVIDENCE_STALE", "NOT_ELIGIBLE", "PATH_UNSAFE", "AMBIGUOUS_ARTIFACT":
		return 4
	case "IO_ERROR", "LOCK_BUSY":
		return 5
	case "UNSUPPORTED_PLATFORM", "UNSUPPORTED_VERSION", "UNSUPPORTED_RENDERER", "CAPABILITY_MISSING":
		return 6
	case "RECOVERY_REQUIRED", "COMMIT_OUTCOME_UNKNOWN", "RECOVERY_CONFLICT", "OPERATION_ROLLED_BACK":
		return 7
	default:
		return 2
	}
}
func Public(err error) *Error {
	var f *Error
	if errors.As(err, &f) {
		copy := *f
		if len(copy.Message) > 512 {
			copy.Message = fmt.Sprintf("%.480s [truncated diagnostic]", copy.Message)
		}
		if len(copy.Field) > 256 {
			copy.Field = copy.Field[:256] + "…"
		}
		if len(copy.Symbol) > 80 {
			copy.Symbol = copy.Symbol[:80]
		}
		if len(copy.OperationID) > 80 {
			copy.OperationID = copy.OperationID[:80]
		}
		return &copy
	}
	return &Error{Code: "INTERNAL_ERROR", Message: "operation failed; inspect local diagnostics"}
}

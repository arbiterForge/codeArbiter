// ca-artifact is internal subprocess machinery, not a new public slash command.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/operations"
	"io"
	"os"
)

func main() { os.Exit(run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr)) }
func run(args []string, in io.Reader, out, errout io.Writer) (exit int) {
	op := "capabilities"
	if len(args) > 0 {
		op = args[0]
		args = args[1:]
	}
	if op == "--version" || op == "--help" || op == "help" {
		op = "capabilities"
	}
	write := func(v any) bool {
		b, e := json.Marshal(v)
		if e != nil {
			return false
		}
		if len(b) > 65536 {
			return false
		}
		b = append(b, '\n')
		_, e = out.Write(b)
		return e == nil
	}
	fail := func(e error) int {
		p := fault.Public(e)
		write(map[string]any{"protocol": operations.Protocol, "operation": op, "ok": false, "error": p})
		fmt.Fprintln(errout, p.Code+": "+p.Message)
		return fault.Exit(e)
	}
	defer func() {
		if r := recover(); r != nil {
			exit = fail(fault.New("INTERNAL_ERROR", "unexpected internal failure; no completion is claimed; inspect operation recovery status before retrying a write"))
		}
	}()
	fs := flag.NewFlagSet("ca-artifact", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	root := fs.String("root", ".", "repository root")
	request := fs.String("request", "", "bounded JSON request file, or - for stdin")
	if e := fs.Parse(args); e != nil || fs.NArg() != 0 {
		return fail(fault.New("INVALID_ARGUMENT", "usage: ca-artifact <operation> --root <repository> --request <file|->"))
	}
	req := map[string]any{"protocol": operations.Protocol}
	if *request != "" {
		r := in
		var f *os.File
		if *request != "-" {
			var e error
			f, e = os.Open(*request)
			if e != nil {
				return fail(fault.New("REQUEST_UNAVAILABLE", "cannot open request file"))
			}
			defer f.Close()
			r = f
		}
		v, e := canonical.Read(r)
		if e != nil {
			return fail(e)
		}
		var ok bool
		req, ok = v.(map[string]any)
		if !ok {
			return fail(fault.New("INVALID_REQUEST", "request must be a JSON object"))
		}
	}
	result, e := operations.Run(*root, op, req)
	if e != nil {
		return fail(e)
	}
	envelope := map[string]any{"protocol": operations.Protocol, "operation": op, "ok": true, "result": result}
	encoded, e := json.Marshal(envelope)
	if e != nil {
		return fail(fault.New("INTERNAL_ERROR", "response serialization failed"))
	}
	limit := int64(65536)
	if b := model.I(req["budget"]); b != 0 {
		limit = b
	}
	if int64(len(encoded))+1 > limit {
		return fail(fault.New("RESPONSE_TOO_LARGE", "response exceeds requested budget; select a schema fragment or a smaller operation"))
	}
	if _, e = out.Write(append(encoded, '\n')); e != nil {
		return 5
	}
	if op == "validate" {
		if data, ok := result.(map[string]any); ok && data["valid"] == false {
			return 2
		}
	}
	return 0
}

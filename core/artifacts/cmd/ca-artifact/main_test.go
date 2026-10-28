package main

import (
	"bytes"
	"encoding/json"
	"testing"
)

func TestCLIEmitsJSONFaultAndMatchingExitClass(t *testing.T) {
	var stdout, stderr bytes.Buffer
	exit := run([]string{"not-an-operation"}, bytes.NewReader(nil), &stdout, &stderr)
	var envelope struct {
		OK    bool `json:"ok"`
		Error struct {
			Code string `json:"code"`
		} `json:"error"`
	}
	if err := json.Unmarshal(stdout.Bytes(), &envelope); err != nil {
		t.Fatalf("decode CLI envelope: %v", err)
	}
	if exit != 2 || envelope.OK || envelope.Error.Code != "UNKNOWN_OPERATION" || !bytes.Contains(stderr.Bytes(), []byte("UNKNOWN_OPERATION")) {
		t.Fatalf("CLI fault mismatch: exit=%d envelope=%+v stderr=%q", exit, envelope, stderr.String())
	}
}

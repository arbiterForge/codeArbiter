package canonical

import (
	"bytes"
	"testing"
)

func TestStrictJSON(t *testing.T) {
	bad := []string{`{"a":1,"a":2}`, `{"a":1,"\u0061":2}`, `1.0`, `1e2`, `9007199254740992`, `-9007199254740992`, `"\ud800"`, `"\udfff"`, `"\ud800\u0000"`, `[] []`, `{"a":}`, `[1,]`, `01`, `-01`, `NaN`, `"` + string([]byte{0xff}) + `"`}
	for _, s := range bad {
		t.Run(s, func(t *testing.T) {
			if _, e := Decode([]byte(s)); e == nil {
				t.Fatal("accepted", s)
			}
		})
	}
	for _, s := range []string{`null`, `true`, `false`, `-0`, `9007199254740991`, `"\ud83d\ude00"`, `{"a":[1,null,"x"]}`} {
		if _, e := Decode([]byte(s)); e != nil {
			t.Fatal(s, e)
		}
	}
}
func TestDigestDomains(t *testing.T) {
	v, e := Decode([]byte(`{"\ue000":1,"😀":2,"\r":3,"n":-0,"s":"</script>&"}`))
	if e != nil {
		t.Fatal(e)
	}
	got, e := Marshal(v)
	if e != nil {
		t.Fatal(e)
	}
	want := "{\"\\r\":3,\"n\":0,\"s\":\"</script>&\",\"😀\":2,\"\ue000\":1}"
	if string(got) != want {
		t.Fatalf("%s != %s", got, want)
	}
}
func TestResourceLimits(t *testing.T) {
	for _, b := range [][]byte{bytes.Repeat([]byte(" "), MaxBytes+1), append(append(bytes.Repeat([]byte("["), MaxDepth+2), []byte("0")...), bytes.Repeat([]byte("]"), MaxDepth+2)...)} {
		if _, e := Decode(b); e == nil {
			t.Fatal("limit accepted")
		}
	}
}
func FuzzStrictJSON(f *testing.F) {
	for _, s := range []string{`{}`, `[0,"x"]`, `{"id":"AC-001"}`, `"\ud800"`} {
		f.Add([]byte(s))
	}
	f.Fuzz(func(t *testing.T, b []byte) {
		if len(b) > 65536 {
			return
		}
		v, e := Decode(b)
		if e != nil {
			return
		}
		out, e := Marshal(v)
		if e != nil {
			t.Fatal(e)
		}
		v2, e := Decode(out)
		if e != nil {
			t.Fatal(e)
		}
		out2, e := Marshal(v2)
		if e != nil || !bytes.Equal(out, out2) {
			t.Fatal("unstable canonicalization")
		}
	})
}

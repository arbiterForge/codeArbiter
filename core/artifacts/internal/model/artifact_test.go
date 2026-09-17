package model

import (
	"math"
	"testing"
)

func TestNativeIntRejectsOutOfRangeValues(t *testing.T) {
	max := int64(^uint(0) >> 1)
	min := -max - 1
	for _, value := range []int64{min, -1, 0, 1, max} {
		converted, ok := NativeInt(value)
		if !ok || int64(converted) != value {
			t.Fatalf("native integer boundary %d was not preserved", value)
		}
	}
	if _, ok := NativeInt("1"); ok {
		t.Fatal("non-integer input was accepted")
	}
	if max < math.MaxInt64 {
		if _, ok := NativeInt(max + 1); ok {
			t.Fatal("positive overflow was accepted")
		}
		if _, ok := NativeInt(min - 1); ok {
			t.Fatal("negative overflow was accepted")
		}
	}
}

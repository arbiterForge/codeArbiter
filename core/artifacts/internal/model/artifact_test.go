package model

import (
	"math"
	"testing"
)

func TestNativeIntUsesPortableBounds(t *testing.T) {
	for _, value := range []int64{math.MinInt32, -1, 0, 1, math.MaxInt32} {
		converted, ok := NativeInt(value)
		if !ok || int64(converted) != value {
			t.Fatalf("native integer boundary %d was not preserved", value)
		}
	}
	if _, ok := NativeInt("1"); ok {
		t.Fatal("non-integer input was accepted")
	}
	if _, ok := NativeInt(int64(math.MaxInt32) + 1); ok {
		t.Fatal("positive non-portable value was accepted")
	}
	if _, ok := NativeInt(int64(math.MinInt32) - 1); ok {
		t.Fatal("negative non-portable value was accepted")
	}
}

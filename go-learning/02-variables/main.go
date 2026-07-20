package main

import (
	"fmt"
	"reflect"
)

func main() {
	// ===== VARIABLE DECLARATION =====

	// 1. var with explicit type
	var a int = 10
	var b string = "hello"

	// 2. var with type inference (Go figures out the type)
	var c = 3.14 // float64
	var d = true // bool

	// 3. var without initial value (gets "zero value")
	var e int    // 0
	var f string // "" (empty string)
	var g bool   // false

	// 4. Short declaration (:=) — MOST COMMON! Only inside functions
	x := 42
	y := "Go is fun"
	z := 1.5

	// 5. Multiple variables at once
	var i, j, k int = 1, 2, 3
	p, q, r := "a", "b", "c"

	// ===== CONSTANTS =====
	const Pi = 3.14159
	const (
		StatusOK       = 200
		StatusNotFound = 404
		StatusError    = 500
	)

	// ===== BASIC TYPES =====
	var (
		iInt     int     = 100
		iFloat64 float64 = 2.5
		iBool    bool    = true
		iString  string  = "text"
		iByte    byte    = 'A' // alias for uint8
		iRune    rune    = '€' // alias for int32 (Unicode code point)
	)

	// ===== TYPE CONVERSION =====
	var myFloat float64 = 99.5
	var myInt int = int(myFloat) // explicit conversion required!

	// Go does NOT have implicit type conversion. You must be explicit.
	// var wrong int = myFloat  // ❌ compiler error

	// ===== ZERO VALUES =====
	// Every type has a "zero value" if not initialized:
	// int, float → 0
	// string → ""
	// bool → false
	// pointer, slice, map, function, interface → nil

	// ===== PRINTING EVERYTHING =====
	fmt.Println("=== Variables ===")
	fmt.Println("a =", a, "b =", b)
	fmt.Println("c =", c, "d =", d)
	fmt.Println("Zero values: e =", e, "f =", f, "g =", g)
	fmt.Println("Short decl: x =", x, "y =", y, "z =", z)
	fmt.Println("Multiple: ", i, j, k, p, q, r)
	fmt.Println("Constants: Pi =", Pi, "StatusOK =", StatusOK)
	fmt.Println("Types: iInt =", iInt, "iFloat64 =", iFloat64, "iBool =", iBool, "iString =", iString)
	fmt.Println("iByte =", iByte, "iRune =", iRune)
	fmt.Println("Converted: myInt =", myInt)
	fmt.Println("Type of x:", reflect.TypeOf(x))
}

/* KEY TAKEAWAYS:
1. Use := for short variable declarations (inside functions only)
2. Use var for package-level or when you need the zero value
3. Go has NO implicit type conversion — be explicit
4. Every type has a zero value (0, "", false, nil)
5. Constants use const, can be grouped in blocks
6. Common types: int, float64, string, bool, byte, rune
*/

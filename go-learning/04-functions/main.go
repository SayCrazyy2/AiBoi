package main

import (
	"fmt"
	"strings"
)

// ==========================================
// BASIC FUNCTION
// ==========================================
func add(a int, b int) int {
	return a + b
}

// Shorter syntax: if consecutive params have same type
func multiply(a, b int) int {
	return a * b
}

// ==========================================
// MULTIPLE RETURN VALUES (Go's superpower!)
// ==========================================
func divide(a, b float64) (float64, error) {
	if b == 0 {
		return 0, fmt.Errorf("cannot divide by zero")
	}
	return a / b, nil
}

// ==========================================
// NAMED RETURN VALUES
// ==========================================
func rectangle(dims float64) (width, height, area float64) {
	width = dims * 2
	height = dims * 3
	area = width * height
	return // "naked return" — returns named values automatically
}

// ==========================================
// VARIADIC FUNCTIONS (variable number of args)
// ==========================================
func sum(nums ...int) int {
	total := 0
	for _, n := range nums {
		total += n
	}
	return total
}

// ==========================================
// FUNCTIONS AS VALUES (first-class citizens)
// ==========================================
func apply(f func(int) int, x int) int {
	return f(x)
}

// ==========================================
// CLOSURES (functions that capture variables)
// ==========================================
func counter() func() int {
	count := 0
	return func() int {
		count++
		return count
	}
}

// ==========================================
// INIT FUNCTION (runs before main, per package)
// ==========================================
func init() {
	// Used for setup/initialization
	// Can have multiple init() functions per file
	fmt.Println("init() runs before main()")
}

func main() {
	fmt.Println("=== Functions ===")

	// Basic
	fmt.Println("add(3, 5) =", add(3, 5))
	fmt.Println("multiply(4, 6) =", multiply(4, 6))

	// Multiple returns
	result, err := divide(10, 3)
	if err != nil {
		fmt.Println("Error:", err)
	} else {
		fmt.Printf("divide(10, 3) = %.2f\n", result)
	}

	// Multiple returns with error
	_, err2 := divide(10, 0)
	if err2 != nil {
		fmt.Println("Error:", err2)
	}

	// Named returns
	w, h, a := rectangle(5)
	fmt.Printf("width=%.1f height=%.1f area=%.1f\n", w, h, a)

	// Variadic
	fmt.Println("sum(1, 2, 3) =", sum(1, 2, 3))
	fmt.Println("sum(1, 2, 3, 4, 5) =", sum(1, 2, 3, 4, 5))

	// Spread operator for variadic
	nums := []int{10, 20, 30, 40}
	fmt.Println("sum(nums...) =", sum(nums...))

	// Functions as values
	double := func(x int) int { return x * 2 }
	triple := func(x int) int { return x * 3 }

	fmt.Println("apply(double, 5) =", apply(double, 5))
	fmt.Println("apply(triple, 5) =", apply(triple, 5))

	// Closures
	nextCount := counter()
	fmt.Println("Counter:", nextCount()) // 1
	fmt.Println("Counter:", nextCount()) // 2
	fmt.Println("Counter:", nextCount()) // 3

	anotherCounter := counter()
	fmt.Println("New counter:", anotherCounter()) // 1 (independent)

	// Anonymous function (IIFE — immediately invoked)
	result2 := func(s string) string {
		return strings.ToUpper(s)
	}("hello")
	fmt.Println("Anonymous IIFE:", result2)
}

/* KEY TAKEAWAYS:
1. Functions can return MULTIPLE values (very common in Go)
2. Use named return values for readability (especially in longer functions)
3. Variadic functions use ...int syntax
4. Functions are first-class: can be passed as args, returned, assigned to vars
5. Closures capture and remember variables from their surrounding scope
6. init() runs automatically before main() — used for setup
7. Anonymous functions can be defined and called inline
*/

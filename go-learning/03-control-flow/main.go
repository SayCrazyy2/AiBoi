package main

import (
	"fmt"
	"time"
)

func main() {
	// ==========================================
	// IF / ELSE
	// ==========================================
	age := 20

	if age >= 18 {
		fmt.Println("Adult")
	} else if age >= 13 {
		fmt.Println("Teenager")
	} else {
		fmt.Println("Child")
	}

	// if with a short statement (initialization before condition)
	if num := 10; num%2 == 0 {
		fmt.Println(num, "is even")
	} else {
		fmt.Println(num, "is odd")
	}
	// Note: 'num' is only accessible within the if/else block

	// ==========================================
	// FOR LOOPS (Go only has 'for' — no while, no do-while)
	// ==========================================

	// 1. Classic for loop
	fmt.Println("\n--- Classic for ---")
	for i := 0; i < 5; i++ {
		fmt.Printf("i=%d ", i)
	}
	fmt.Println()

	// 2. For like a while loop
	fmt.Println("--- While-style for ---")
	n := 5
	for n > 0 {
		fmt.Printf("n=%d ", n)
		n--
	}
	fmt.Println()

	// 3. Infinite loop (with break)
	fmt.Println("--- Infinite with break ---")
	count := 0
	for {
		count++
		if count >= 3 {
			break
		}
		fmt.Printf("count=%d ", count)
	}
	fmt.Println()

	// 4. For-range (iterate over collections)
	fmt.Println("--- For-range over slice ---")
	nums := []int{10, 20, 30, 40, 50}
	for index, value := range nums {
		fmt.Printf("index=%d value=%d\n", index, value)
	}

	// Skip index with _
	fmt.Println("--- For-range (skip index) ---")
	for _, value := range nums {
		fmt.Printf("value=%d ", value)
	}
	fmt.Println()

	// For-range over string (gives runes!)
	fmt.Println("--- For-range over string ---")
	for i, r := range "Hello€" {
		fmt.Printf("i=%d r=%c (code=%d)\n", i, r, r)
	}

	// 5. continue
	fmt.Println("--- Continue ---")
	for i := 0; i < 10; i++ {
		if i%2 == 0 {
			continue // skip even numbers
		}
		fmt.Printf("%d ", i)
	}
	fmt.Println()

	// ==========================================
	// SWITCH
	// ==========================================
	fmt.Println("\n--- Switch ---")
	day := time.Now().Weekday()
	switch day {
	case time.Saturday, time.Sunday:
		fmt.Println("It's the weekend! 🎉")
	default:
		fmt.Println("It's a weekday 📅")
	}

	// Switch with no expression (cleaner if/else chain)
	hour := 14
	switch {
	case hour < 12:
		fmt.Println("Good morning!")
	case hour < 18:
		fmt.Println("Good afternoon!")
	default:
		fmt.Println("Good evening!")
	}

	// Switch with fallthrough (rarely used, but exists)
	switch 2 {
	case 1:
		fmt.Println("One")
	case 2:
		fmt.Println("Two")
		fallthrough // executes next case's body too!
	case 3:
		fmt.Println("Three")
	}

	// ==========================================
	// DEFER (executes when function returns, LIFO order)
	// ==========================================
	fmt.Println("\n--- Defer ---")
	defer fmt.Println("This runs LAST (deferred)")
	defer fmt.Println("This runs second-to-last")
	fmt.Println("This runs FIRST")
	fmt.Println("This runs second")
	// Output order: FIRST, second, second-to-last, LAST (deferred)

	// Defer is commonly used for cleanup (closing files, unlocking mutexes)
}

/* KEY TAKEAWAYS:
1. Go has ONLY 'for' for loops (no while, no do-while)
2. if and switch can have initialization statements
3. switch does NOT fall through by default (unlike C/Java)
4. Use _ to ignore values you don't need
5. defer schedules a function call for when the current function returns (LIFO order)
6. No parentheses around conditions in if/for (unlike C/Java)
*/

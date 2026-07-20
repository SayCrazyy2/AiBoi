package main

// Every Go program starts with a package declaration.
// "main" is special — it tells Go this is an executable program (not a library).

import (
	"fmt" // fmt = format package, used for I/O
)

// The main function is the entry point of the program.
// Go executes this function automatically when you run the program.
func main() {
	// fmt.Println prints a line to stdout
	fmt.Println("Hello, World! 🌍")

	// fmt.Printf allows formatted output (like printf in C)
	name := "Gopher"
	fmt.Printf("Welcome, %s!\n", name)

	// Print without newline
	fmt.Print("Same ")
	fmt.Print("line\n")

	// Sprint returns a formatted string (doesn't print)
	msg := fmt.Sprintf("You are %s, learning Go!", name)
	fmt.Println(msg)
}

/* KEY TAKEAWAYS:
1. Every program needs: package main + func main()
2. Imports are grouped in parentheses (import block)
3. No semicolons needed at end of lines
4. Braces { } are required (even for one-line bodies)
5. The opening brace { must be on the same line as the function declaration
*/

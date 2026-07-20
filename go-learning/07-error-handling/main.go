package main

import (
	"errors"
	"fmt"
)

// ==========================================
// GO ERROR HANDLING PHILOSOPHY
// ==========================================
// Go does NOT use try/catch. Errors are VALUES.
// You check them explicitly. This is verbose but explicit.

// ==========================================
// CUSTOM ERROR TYPES
// ==========================================

// Method 1: Using errors.New()
var ErrNotFound = errors.New("resource not found")
var ErrUnauthorized = errors.New("unauthorized access")

// Method 2: Custom error struct (implements error interface)
type ValidationError struct {
	Field   string
	Message string
}

// Implement the error interface (requires Error() string method)
func (e *ValidationError) Error() string {
	return fmt.Sprintf("validation error: field '%s' - %s", e.Field, e.Message)
}

// Method 3: Wrapping errors (Go 1.13+) with %w
var ErrDatabase = errors.New("database error")

func connectDB() error {
	return fmt.Errorf("failed to connect: %w", ErrDatabase)
}

// ==========================================
// FUNCTIONS THAT RETURN ERRORS
// ==========================================

func findUser(id int) (string, error) {
	if id <= 0 {
		return "", ErrNotFound
	}
	if id == 999 {
		return "", ErrUnauthorized
	}
	users := map[int]string{1: "Alice", 2: "Bob", 3: "Charlie"}
	name, exists := users[id]
	if !exists {
		return "", fmt.Errorf("user %d not found", id)
	}
	return name, nil
}

func validateEmail(email string) error {
	if email == "" {
		return &ValidationError{
			Field:   "email",
			Message: "cannot be empty",
		}
	}
	if !contains(email, "@") {
		return &ValidationError{
			Field:   "email",
			Message: "must contain @",
		}
	}
	return nil
}

func contains(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

// ==========================================
// PANIC AND RECOVER (for truly unexpected errors)
// ==========================================

func riskyFunction() {
	defer func() {
		if r := recover(); r != nil {
			fmt.Println("Recovered from panic:", r)
		}
	}()

	panic("something went terribly wrong!")
}

// ==========================================
// MAIN
// ==========================================

func main() {
	fmt.Println("=== Error Handling ===")

	// Basic error checking
	name, err := findUser(1)
	if err != nil {
		fmt.Println("Error:", err)
	} else {
		fmt.Println("Found user:", name)
	}

	// Sentinel error comparison with errors.Is
	_, err = findUser(0)
	if errors.Is(err, ErrNotFound) {
		fmt.Println("Sentinel error matched: Not Found")
	}

	// Wrapped error unwrapping
	err = connectDB()
	if errors.Is(err, ErrDatabase) {
		fmt.Println("Wrapped error matched: Database error")
	}

	// Type assertion for custom error types
	err = validateEmail("")
	var validationErr *ValidationError
	if errors.As(err, &validationErr) {
		fmt.Printf("Custom error - Field: %s, Message: %s\n",
			validationErr.Field, validationErr.Message)
	}

	// Multiple validation checks
	emails := []string{"", "noemail", "user@example.com"}
	for _, email := range emails {
		if err := validateEmail(email); err != nil {
			fmt.Printf("'%s' → Error: %v\n", email, err)
		} else {
			fmt.Printf("'%s' → Valid!\n", email)
		}
	}

	// Panic and Recover
	fmt.Println("\n=== Panic & Recover ===")
	fmt.Println("About to call risky function...")
	riskyFunction()
	fmt.Println("Survived the panic!")

	// Error wrapping chain
	fmt.Println("\n=== Error Wrapping ===")
	err = fmt.Errorf("outer: %w", fmt.Errorf("middle: %w", errors.New("inner")))
	fmt.Println("Full error:", err)
	fmt.Println("Unwrapped:", errors.Unwrap(err))
}

/* KEY TAKEAWAYS:
1. Errors are values — always check them explicitly
2. Functions return (result, error) pattern — this is idiomatic Go
3. errors.Is() checks if an error matches a sentinel error (even if wrapped)
4. errors.As() extracts a custom error type from the error chain
5. Use fmt.Errorf with %w to wrap errors with context
6. panic/recover is for UNEXPECTED failures (like nil pointer dereference)
7. Don't panic for normal errors — return them!
8. The error interface only requires: Error() string
9. Custom error types can carry extra context (fields, methods)
10. errors.Unwrap() peels back one layer of wrapping
*/

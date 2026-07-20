package main

import (
	"fmt"
	"math"
)

// ==========================================
// STRUCTS — Go's way of grouping data (like classes without classes)
// ==========================================

// Basic struct
type Person struct {
	Name string
	Age  int
}

// Struct with embedded struct (composition — Go's alternative to inheritance)
type Employee struct {
	Person      // embedded struct (anonymous field)
	Company string
	Salary  float64
}

// Struct with tags (used by encoding/json etc.)
type User struct {
	Username string `json:"username"`
	Email    string `json:"email"`
	Active   bool   `json:"active"`
}

// ==========================================
// METHODS — functions with a receiver
// ==========================================

// Value receiver (works on a copy)
func (p Person) Greet() string {
	return fmt.Sprintf("Hi, I'm %s, age %d", p.Name, p.Age)
}

// Pointer receiver (can modify the struct)
func (p *Person) HaveBirthday() {
	p.Age++
}

// Method on a custom type
type Circle struct {
	Radius float64
}

func (c Circle) Area() float64 {
	return math.Pi * c.Radius * c.Radius
}

func (c Circle) Perimeter() float64 {
	return 2 * math.Pi * c.Radius
}

// ==========================================
// INTERFACES — contracts that types implement
// ==========================================

// Define an interface
type Shape interface {
	Area() float64
	Perimeter() float64
}

// Rectangle implements Shape (implicitly!)
type Rectangle struct {
	Width  float64
	Height float64
}

func (r Rectangle) Area() float64 {
	return r.Width * r.Height
}

func (r Rectangle) Perimeter() float64 {
	return 2 * (r.Width + r.Height)
}

// Triangle also implements Shape
type Triangle struct {
	Base   float64
	Height float64
	SideA  float64
	SideB  float64
	SideC  float64
}

func (t Triangle) Area() float64 {
	return 0.5 * t.Base * t.Height
}

func (t Triangle) Perimeter() float64 {
	return t.SideA + t.SideB + t.SideC
}

// Stringer interface (like toString() in other languages)
func (p Person) String() string {
	return fmt.Sprintf("Person(Name=%s, Age=%d)", p.Name, p.Age)
}

// ==========================================
// EMPTY INTERFACE (interface{}) — any type
// ==========================================
func describe(i interface{}) {
	fmt.Printf("Value: %v, Type: %T\n", i, i)
}

// ==========================================
// TYPE ASSERTIONS
// ==========================================
func getString(i interface{}) string {
	// Type assertion
	if s, ok := i.(string); ok {
		return s
	}
	return "not a string"
}

// ==========================================
// TYPE SWITCH
// ==========================================
func typeOf(i interface{}) string {
	switch v := i.(type) {
	case int:
		return fmt.Sprintf("int: %d", v)
	case string:
		return fmt.Sprintf("string: %s", v)
	case bool:
		return fmt.Sprintf("bool: %t", v)
	default:
		return fmt.Sprintf("unknown type: %T", v)
	}
}

func main() {
	fmt.Println("=== Structs ===")

	// Create a struct
	p1 := Person{Name: "Alice", Age: 30}
	p2 := Person{"Bob", 25} // positional (not recommended)
	var p3 Person           // zero value: {Name:"", Age:0}

	fmt.Println(p1)
	fmt.Println(p2)
	fmt.Println(p3)

	// Pointer to struct
	p4 := &Person{Name: "Charlie", Age: 40}
	fmt.Println(p4.Name) // Go auto-dereferences for you

	// Methods
	fmt.Println(p1.Greet())
	p1.HaveBirthday() // modifies p1 because pointer receiver
	fmt.Println("After birthday:", p1)

	// Embedded structs (composition)
	emp := Employee{
		Person:  Person{Name: "Dave", Age: 35},
		Company: "Google",
		Salary:  150000,
	}
	// Can access embedded fields directly
	fmt.Println(emp.Name)    // from embedded Person
	fmt.Println(emp.Greet())  // promoted method from Person

	fmt.Println("\n=== Interfaces ===")

	// Interface in action — polymorphism!
	shapes := []Shape{
		Circle{Radius: 5},
		Rectangle{Width: 3, Height: 4},
		Triangle{Base: 4, Height: 3, SideA: 3, SideB: 4, SideC: 5},
	}

	for _, s := range shapes {
		fmt.Printf("Area: %.2f, Perimeter: %.2f\n", s.Area(), s.Perimeter())
	}

	// Interface satisfaction is IMPLICIT in Go
	// No "implements" keyword needed!
	// If a type has all the methods, it implements the interface.

	fmt.Println("\n=== Empty Interface & Type Assertions ===")

	// interface{} (or 'any' in Go 1.18+) holds any type
	describe(42)
	describe("hello")
	describe(true)
	describe(3.14)

	fmt.Println(getString("test"))
	fmt.Println(getString(123))

	fmt.Println("\n=== Type Switch ===")
	fmt.Println(typeOf(42))
	fmt.Println(typeOf("hello"))
	fmt.Println(typeOf(true))
	fmt.Println(typeOf([]int{1, 2, 3}))

	fmt.Println("\n=== Stringer ===")
	fmt.Println(p1) // uses String() method automatically
}

/* KEY TAKEAWAYS:
1. Structs group data — Go's replacement for classes
2. Methods are functions with a receiver (value or pointer)
3. Use pointer receivers when you need to modify the struct
4. Embed structs for composition (Go's alternative to inheritance)
5. Interfaces define behavior (method sets)
6. Interface implementation is IMPLICIT — no "implements" keyword
7. interface{} (or 'any') can hold any value
8. Type assertions: val.(Type) to extract concrete type
9. Type switch: switch v := i.(type) { case T: ... }
10. Implement String() method for custom string representation
*/

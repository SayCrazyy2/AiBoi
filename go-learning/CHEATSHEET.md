# 🐹 Go Quick Reference Cheat Sheet

## Basic Syntax
```go
package main

import "fmt"

func main() {
    fmt.Println("Hello, World!")
}
```

## Variable Declarations
```go
var x int = 10        // explicit type
var y = 20             // inferred
z := 30               // short (inside functions only)
var a, b, c = 1, 2, 3  // multiple
```

## Types
```go
int  int8  int16  int32  int64
uint uint8 uint16 uint32 uint64
float32  float64
string  bool  byte  rune
```

## Control Flow
```go
if x > 0 { ... } else { ... }
for i := 0; i < 10; i++ { ... }
for x > 0 { ... }              // while
for { ... }                    // infinite
for i, v := range slice { ... }
switch x { case 1: ... default: ... }
```

## Functions
```go
func add(a, b int) int { return a + b }
func div(a, b float64) (float64, error) { ... }
func sum(nums ...int) int { ... }
func(f func(int) int, x int) int { ... }
```

## Structs & Methods
```go
type User struct {
    Name string
    Age  int
}

func (u User) String() string { return u.Name }
func (u *User) Birthday() { u.Age++ }
```

## Interfaces
```go
type Reader interface { Read() string }
// Implicitly implemented — no "implements" keyword
```

## Error Handling
```go
result, err := doSomething()
if err != nil { return err }
if errors.Is(err, ErrNotFound) { ... }
```

## Concurrency
```go
go func() { ... }()           // goroutine
ch := make(chan int)          // unbuffered
ch := make(chan int, 5)       // buffered
ch <- 42                      // send
val := <-ch                   // receive
select { case <-ch1: ... }    // multiplex
var wg sync.WaitGroup          // sync
```

## Common Commands
```bash
go run main.go      # run
go build            # compile
go test ./...       # test
go fmt ./...        # format
go mod init <name>  # init module
go mod tidy         # clean deps
go vet ./...        # lint
```

## Visibility Rules
```go
var Public   = "exported"   // Uppercase = public
var private  = "internal"   // lowercase = package-private
```

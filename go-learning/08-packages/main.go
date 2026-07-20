package main

// ==========================================
// GO PACKAGES & MODULES
// ==========================================

// IMPORTS — grouped and sorted (gofmt does this automatically)
import (
	// Standard library first
	"fmt"
	"strings"

	// Then third-party (after go mod download)
	// "github.com/gin-gonic/gin"

	// Then local modules
	// "myproject/internal/database"
)

// ==========================================
// VISIBILITY — Go uses capitalization instead of public/private keywords
// ==========================================

// Exported (public) — starts with UPPERCASE letter
var PublicVar = "I'm accessible from other packages"

func PublicFunc() string {
	return "I'm a public function"
}

// Unexported (private) — starts with lowercase letter
var privateVar = "I'm only accessible within this package"

func privateFunc() string {
	return "I'm a private function"
}

// Exported type
type Server struct {
	Host string // exported field
	Port int    // exported field

	internalState string // unexported field (private)
}

// Exported method
func (s *Server) Start() {
	s.internalState = "running"
	fmt.Printf("Server %s:%d started\n", s.Host, s.Port)
}

// Unexported method (internal only)
func (s *Server) shutdown() {
	s.internalState = "stopped"
	fmt.Println("Server stopped")
}

// ==========================================
// INIT FUNCTIONS — run once per package, before main()
// ==========================================

// You can have MULTIPLE init() functions in a single file!
func init() {
	fmt.Println("First init - runs before main()")
}

func init() {
	fmt.Println("Second init - also runs before main()")
}

// ==========================================
// PACKAGE-LEVEL VARIABLES & CONSTANTS
// ==========================================

const (
	// Exported constants
	Version   = "1.0.0"
	MaxConns = 100

	// Unexported constants
	defaultPort = 8080
)

// ==========================================
// MAIN FUNCTION
// ==========================================

func main() {
	fmt.Println("=== Packages ===")
	fmt.Println("Version:", Version)

	// Using exported vs unexported
	fmt.Println("Public:", PublicVar)
	fmt.Println("Private:", privateVar) // only works within same package

	// Using standard library packages
	name := "golang"
	fmt.Println("Uppercase:", strings.ToUpper(name))
	fmt.Println("Contains 'lang':", strings.Contains(name, "lang"))

	// Using custom type
	server := &Server{
		Host: "localhost",
		Port: 8080,
	}
	server.Start()
	server.shutdown()
}

/* ==========================================
	GO MODULE & PACKAGE STRUCTURE
	==========================================

	Project layout:

	myproject/
	├── go.mod              ← Module definition
	├── go.sum              ← Dependency checksums
	├── main.go             ← Package main (entry point)
	├── internal/           ← Private packages (not importable externally)
	│   ├── config/
	│   │   └── config.go   ← package config
	│   └── database/
	│       └── db.go       ← package database
	├── pkg/                ← Public packages (importable by others)
	│   ├── auth/
	│   │   └── auth.go     ← package auth
	│   └── utils/
	│       └── utils.go    ← package utils
	└── cmd/                ← Multiple binaries
	    ├── server/
	    │   └── main.go     ← package main (server binary)
	    └── cli/
	        └── main.go     ← package main (CLI binary)

	--- go.mod file example ---

	module github.com/username/myproject

	go 1.21

	require (
		github.com/gin-gonic/gin v1.9.1
		github.com/lib/pq v1.10.9
	)

	--- Common commands ---

	go mod init <module-name>    ← Create go.mod
	go mod tidy                  ← Add/remove dependencies
	go mod download              ← Download dependencies
	go build                     ← Compile to binary
	go install                   ← Build & install to $GOPATH/bin
	go run main.go               ← Build & run (temporary)
	go fmt ./...                 ← Format all files
	go vet ./...                 ← Lint for suspicious code
	go test ./...                ← Run all tests
	go get <package>             ← Add a dependency
	go doc <package>             ← Read documentation

	KEY TAKEAWAYS:
	1. Uppercase = exported (public), lowercase = unexported (private)
	2. One package per directory
	3. go.mod defines the module (like package.json)
	4. internal/ packages can only be imported within the module
	5. init() runs once before main() — used for setup
	6. Multiple init() functions per file are allowed (run in order)
	7. Use go mod tidy to keep dependencies clean
*/

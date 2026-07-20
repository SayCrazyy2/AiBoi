package main

import (
	"fmt"
	"sync"
	"time"
)

// ==========================================
// GOROUTINES — lightweight threads managed by Go runtime
// ==========================================
// Go's concurrency model is based on CSP (Communicating Sequential Processes)
// "Don't communicate by sharing memory; share memory by communicating"

func sayHello(id int) {
	fmt.Printf("Hello from goroutine %d\n", id)
}

func slowTask(id int, seconds int) {
	fmt.Printf("Task %d starting...\n", id)
	time.Sleep(time.Duration(seconds) * time.Second)
	fmt.Printf("Task %d done! (took %ds)\n", id, seconds)
}

func main() {
	fmt.Println("=== Goroutines ===")

	// Launch a goroutine with 'go' keyword
	go sayHello(1)
	go sayHello(2)
	go sayHello(3)

	// Give goroutines time to execute
	// (In real code, use WaitGroup or channels instead of Sleep)
	time.Sleep(100 * time.Millisecond)

	// Launch multiple goroutines concurrently
	fmt.Println("\n--- Concurrent tasks ---")
	start := time.Now()

	go slowTask(1, 2)
	go slowTask(2, 1)
	go slowTask(3, 3)

	time.Sleep(4 * time.Second) // wait for all
	fmt.Printf("Total time: %v (concurrent, not sequential)\n", time.Since(start))

	// ==========================================
	// WAIT GROUPS — wait for goroutines to finish
	// ==========================================
	fmt.Println("\n=== WaitGroup ===")

	var wg sync.WaitGroup

	for i := 1; i <= 5; i++ {
		wg.Add(1) // increment counter
		go func(id int) {
			defer wg.Done() // decrement when done
			fmt.Printf("Worker %d working...\n", id)
			time.Sleep(100 * time.Millisecond)
		}(i) // pass i as argument to avoid closure capture bug!
	}
	wg.Wait() // block until counter reaches 0
	fmt.Println("All workers done!")

	// ==========================================
	// CHANNELS — typed, thread-safe communication between goroutines
	// ==========================================
	fmt.Println("\n=== Channels ===")

	// Unbuffered channel (synchronous — blocks until receiver ready)
	ch := make(chan string)

	go func() {
		ch <- "Hello from goroutine!" // send to channel
	}()

	msg := <-ch // receive from channel (blocks until data available)
	fmt.Println("Received:", msg)

	// Buffered channel (asynchronous — doesn't block until buffer full)
	buffered := make(chan int, 3)
	buffered <- 1 // doesn't block (buffer has space)
	buffered <- 2
	buffered <- 3
	// buffered <- 4 // would block! (buffer full, no receiver)

	fmt.Println("Buffered:", <-buffered)
	fmt.Println("Buffered:", <-buffered)
	fmt.Println("Buffered:", <-buffered)

	// ==========================================
	// CHANNEL DIRECTION
	// ==========================================
	fmt.Println("\n=== Channel Direction ===")

	// Producer: only sends
	// Consumer: only receives
	producer := func(out chan<- int) { // send-only
		for i := 1; i <= 3; i++ {
			out <- i * 10
		}
		close(out)
	}

	consumer := func(in <-chan int) { // receive-only
		for val := range in {
			fmt.Println("Consumed:", val)
		}
	}

	ch2 := make(chan int)
	go producer(ch2)
	consumer(ch2)

	// ==========================================
	// SELECT — multiplexing channel operations
	// ==========================================
	fmt.Println("\n=== Select ===")

	ch3 := make(chan string)
	ch4 := make(chan string)

	go func() {
		time.Sleep(100 * time.Millisecond)
		ch3 <- "fast"
	}()

	go func() {
		time.Sleep(200 * time.Millisecond)
		ch4 <- "slow"
	}()

	// Select waits on multiple channel operations
	// It picks whichever is ready first (random if both ready)
	for i := 0; i < 2; i++ {
		select {
		case msg1 := <-ch3:
			fmt.Println("From ch3:", msg1)
		case msg2 := <-ch4:
			fmt.Println("From ch4:", msg2)
		}
	}

	// Select with timeout
	fmt.Println("\n--- Select with timeout ---")
	ch5 := make(chan string)
	go func() {
		time.Sleep(2 * time.Second)
		ch5 <- "late message"
	}()

	select {
	case msg := <-ch5:
		fmt.Println("Got:", msg)
	case <-time.After(500 * time.Millisecond):
		fmt.Println("Timeout! (waited 500ms)")
	}

	// ==========================================
	// WORKER POOL PATTERN
	// ==========================================
	fmt.Println("\n=== Worker Pool ===")

	jobs := make(chan int, 10)
	results := make(chan int, 10)

	// Worker function
	worker := func(id int, jobs <-chan int, results chan<- int) {
		for j := range jobs {
			fmt.Printf("Worker %d processing job %d\n", id, j)
			results <- j * j
		}
	}

	// Start 3 workers
	for w := 1; w <= 3; w++ {
		go worker(w, jobs, results)
	}

	// Send 5 jobs
	for j := 1; j <= 5; j++ {
		jobs <- j
	}
	close(jobs)

	// Collect results
	for r := 1; r <= 5; r++ {
		fmt.Printf("Result: %d\n", <-results)
	}

	// ==========================================
	// CLOSING CHANNELS & CHECKING STATUS
	// ==========================================
	fmt.Println("\n=== Channel Close Detection ===")

	ch6 := make(chan int, 3)
	ch6 <- 1
	ch6 <- 2
	close(ch6)

	// Receive until closed
	for {
		val, ok := <-ch6 // ok is false when channel is closed & empty
		if !ok {
			fmt.Println("Channel closed!")
			break
		}
		fmt.Println("Got:", val)
	}
}

/* KEY TAKEAWAYS:
1. Goroutines are lightweight threads — start with 'go' keyword
2. Channels are the Go way to communicate between goroutines
3. Unbuffered channels block until both sender & receiver are ready
4. Buffered channels block only when buffer is full
5. Use sync.WaitGroup to wait for multiple goroutines
6. select lets you wait on multiple channel operations
7. close() marks a channel as done; receivers detect with ok pattern or for-range
8. Channel direction: chan<- (send-only), <-chan (receive-only)
9. time.After() creates a timeout channel
10. NEVER communicate by sharing memory; share memory by communicating
*/

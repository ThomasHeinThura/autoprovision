// app2.backend — TaskDesk workers (Go). See ../PLAN.md §5.2.
//
// Background/async plane (NOT a read plane): on a ticker it scans the core API (app1), computes an
// overview / SLA-risk snapshot, caches it in Valkey, and publishes an event. Exposes a small HTTP
// surface for health + inspecting the last run.
package main

import (
	"context"
	_ "embed"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
)

//go:embed docs.yaml
var openapiDoc []byte

type Overview struct {
	Projects   int    `json:"projects"`
	Open       int    `json:"open"`
	Resolved   int    `json:"resolved"`
	Unassigned int    `json:"unassigned"`
	UrgentOpen int    `json:"urgentOpen"` // stand-in for "SLA-risk" until app1 exposes SLA timers
	LastScan   string `json:"lastScan"`
}

var (
	apiBase   = env("API_BASE", "http://localhost:5199")
	redisAddr = env("REDIS_ADDR", "")
	port      = env("PORT", "8081")
	interval  = envDur("SCAN_INTERVAL", 30*time.Second)
)

var (
	mu     sync.RWMutex
	latest Overview
	scans  int
	rdb    *redis.Client
)

func main() {
	if redisAddr != "" {
		rdb = redis.NewClient(&redis.Options{Addr: redisAddr})
	}
	go worker()

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, 200, map[string]string{"status": "ok"})
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, r *http.Request) {
		if rdb != nil {
			ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
			defer cancel()
			if err := rdb.Ping(ctx).Err(); err != nil {
				writeJSON(w, 503, map[string]string{"status": "redis unavailable"})
				return
			}
		}
		writeJSON(w, 200, map[string]string{"status": "ready"})
	})
	mux.HandleFunc("/workers/status", func(w http.ResponseWriter, r *http.Request) {
		mu.RLock()
		defer mu.RUnlock()
		writeJSON(w, 200, map[string]any{
			"apiBase": apiBase, "redis": redisAddr != "", "scans": scans,
			"interval": interval.String(), "latest": latest,
		})
	})
	mux.HandleFunc("/reports/overview", func(w http.ResponseWriter, r *http.Request) {
		mu.RLock()
		o := latest
		mu.RUnlock()
		writeJSON(w, 200, o)
	})
	mux.HandleFunc("/api/docs.yaml", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/yaml")
		_, _ = w.Write(openapiDoc)
	})

	log.Printf("app2 workers on :%s (api=%s redis=%v interval=%s)", port, apiBase, redisAddr != "", interval)
	log.Fatal(http.ListenAndServe(":"+port, mux))
}

func worker() {
	time.Sleep(3 * time.Second) // let app1 come up
	scan()
	t := time.NewTicker(interval)
	defer t.Stop()
	for range t.C {
		scan()
	}
}

func scan() {
	o, err := computeOverview()
	if err != nil {
		log.Printf("scan error: %v", err)
		return
	}
	o.LastScan = time.Now().UTC().Format(time.RFC3339)

	mu.Lock()
	latest = o
	scans++
	n := scans
	mu.Unlock()

	if rdb != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		if b, err := json.Marshal(o); err == nil {
			rdb.Set(ctx, "taskdesk:report:overview", b, 0)
			rdb.Publish(ctx, "taskdesk:events", "sla_scan_complete")
		}
	}
	log.Printf("scan #%d: projects=%d open=%d resolved=%d unassigned=%d urgentOpen=%d",
		n, o.Projects, o.Open, o.Resolved, o.Unassigned, o.UrgentOpen)
}

func computeOverview() (Overview, error) {
	var o Overview
	var projects []struct {
		Key string `json:"key"`
	}
	if err := getJSON(apiBase+"/api/v1/projects", &projects); err != nil {
		return o, err
	}
	o.Projects = len(projects)
	for _, p := range projects {
		var items []struct {
			Status   string  `json:"status"`
			Priority string  `json:"priority"`
			Assignee *string `json:"assignee"`
		}
		if err := getJSON(apiBase+"/api/v1/projects/"+p.Key+"/workitems", &items); err != nil {
			return o, err
		}
		for _, it := range items {
			if it.Status == "done" {
				o.Resolved++
				continue
			}
			o.Open++
			if it.Assignee == nil {
				o.Unassigned++
			}
			if it.Priority == "urgent" {
				o.UrgentOpen++
			}
		}
	}
	return o, nil
}

func getJSON(url string, v any) error {
	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	return json.NewDecoder(resp.Body).Decode(v)
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func env(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}

func envDur(k string, d time.Duration) time.Duration {
	if v := os.Getenv(k); v != "" {
		if p, err := time.ParseDuration(v); err == nil {
			return p
		}
	}
	return d
}

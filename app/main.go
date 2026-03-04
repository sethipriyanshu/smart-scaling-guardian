package main

import (
	"encoding/json"
	"net/http"
	"os"
	"strconv"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

const version = "v1.0.0"

type Config struct {
	Port                 string
	CPUIntensity         int
	SimulatedLatencyMs   int
	MaxConcurrentRequest int
}

func loadConfig() Config {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	cpu := 50000
	if v := os.Getenv("CPU_INTENSITY"); v != "" {
		if i, err := strconv.Atoi(v); err == nil {
			cpu = i
		}
	}
	latency := 0
	if v := os.Getenv("SIMULATED_LATENCY_MS"); v != "" {
		if i, err := strconv.Atoi(v); err == nil {
			latency = i
		}
	}
	maxConcurrent := 100
	if v := os.Getenv("MAX_CONCURRENT_REQUESTS"); v != "" {
		if i, err := strconv.Atoi(v); err == nil {
			maxConcurrent = i
		}
	}
	return Config{
		Port:                 port,
		CPUIntensity:         cpu,
		SimulatedLatencyMs:   latency,
		MaxConcurrentRequest: maxConcurrent,
	}
}

type OrderItem struct {
	SKU      string  `json:"sku"`
	Quantity int     `json:"quantity"`
	Price    float64 `json:"price"`
}

type OrderRequest struct {
	CustomerID      string      `json:"customer_id"`
	Items           []OrderItem `json:"items"`
	DeliveryAddress string      `json:"delivery_address"`
	Priority        string      `json:"priority"`
}

type OrderResponse struct {
	OrderID           string `json:"order_id"`
	Status            string `json:"status"`
	EstimatedDelivery string `json:"estimated_delivery"`
	ProcessingTimeMs  int64  `json:"processing_time_ms"`
}

type HealthResponse struct {
	Status         string `json:"status"`
	UptimeSeconds  int64  `json:"uptime_seconds"`
	ActiveRequests int    `json:"active_requests"`
	Version        string `json:"version"`
}

type ErrorResponse struct {
	Error   string `json:"error"`
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type LogEntry struct {
	Timestamp string `json:"timestamp"`
	Method    string `json:"method"`
	Path      string `json:"path"`
	Status    int    `json:"status_code"`
	LatencyMs int64  `json:"latency_ms"`
	RequestID string `json:"request_id"`
}

var (
	startTime = time.Now()
	cfg       Config
	sem       chan struct{}
	activeReq int
	activeMu  sync.Mutex

	reqCount = prometheus.NewCounterVec(
		prometheus.CounterOpts{Name: "http_requests_total", Help: "Total HTTP requests"},
		[]string{"method", "path", "status"},
	)
	reqLatency = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{Name: "http_request_duration_seconds", Help: "Request latency in seconds"},
		[]string{"method", "path"},
	)
	activeGauge = prometheus.NewGauge(prometheus.GaugeOpts{Name: "http_requests_in_flight", Help: "In-flight requests"})
)

func init() {
	prometheus.MustRegister(reqCount, reqLatency, activeGauge)
}

func cpuLoad(n int) {
	for i := 0; i < n; i++ {
		_ = i * i
	}
}

func logJSON(entry LogEntry) {
	b, _ := json.Marshal(entry)
	os.Stdout.Write(append(b, '\n'))
}

func writeJSON(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func handleOrders(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, ErrorResponse{
			Error: "method_not_allowed", Code: 405, Message: "POST required",
		})
		return
	}
	start := time.Now()
	reqID := r.Header.Get("X-Request-ID")
	if reqID == "" {
		reqID = uuid.New().String()
	}

	var body OrderRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{
			Error: "invalid_json", Code: 400, Message: err.Error(),
		})
		reqCount.WithLabelValues(r.Method, r.URL.Path, "400").Inc()
		reqLatency.WithLabelValues(r.Method, r.URL.Path).Observe(time.Since(start).Seconds())
		logJSON(LogEntry{time.Now().UTC().Format(time.RFC3339Nano), r.Method, r.URL.Path, 400, time.Since(start).Milliseconds(), reqID})
		return
	}
	if body.CustomerID == "" || len(body.Items) == 0 || body.DeliveryAddress == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{
			Error: "validation_error", Code: 400, Message: "customer_id, items, and delivery_address required",
		})
		reqCount.WithLabelValues(r.Method, r.URL.Path, "400").Inc()
		reqLatency.WithLabelValues(r.Method, r.URL.Path).Observe(time.Since(start).Seconds())
		logJSON(LogEntry{time.Now().UTC().Format(time.RFC3339Nano), r.Method, r.URL.Path, 400, time.Since(start).Milliseconds(), reqID})
		return
	}

	cpuLoad(cfg.CPUIntensity)
	if cfg.SimulatedLatencyMs > 0 {
		time.Sleep(time.Duration(cfg.SimulatedLatencyMs) * time.Millisecond)
	}
	processingMs := time.Since(start).Milliseconds()
	estDelivery := time.Now().UTC().Add(2 * time.Hour).Format(time.RFC3339)
	orderID := uuid.New().String()

	writeJSON(w, http.StatusOK, OrderResponse{
		OrderID:           orderID,
		Status:            "ACCEPTED",
		EstimatedDelivery: estDelivery,
		ProcessingTimeMs:  processingMs,
	})
	reqCount.WithLabelValues(r.Method, r.URL.Path, "200").Inc()
	reqLatency.WithLabelValues(r.Method, r.URL.Path).Observe(time.Since(start).Seconds())
	logJSON(LogEntry{time.Now().UTC().Format(time.RFC3339Nano), r.Method, r.URL.Path, 200, time.Since(start).Milliseconds(), reqID})
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
	activeMu.Lock()
	n := activeReq
	activeMu.Unlock()
	status := "healthy"
	if n >= cfg.MaxConcurrentRequest {
		status = "degraded"
	}
	writeJSON(w, http.StatusOK, HealthResponse{
		Status:         status,
		UptimeSeconds:  int64(time.Since(startTime).Seconds()),
		ActiveRequests: n,
		Version:        version,
	})
}

func main() {
	cfg = loadConfig()
	sem = make(chan struct{}, cfg.MaxConcurrentRequest)

	http.HandleFunc("/orders", func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		reqID := r.Header.Get("X-Request-ID")
		if reqID == "" {
			reqID = uuid.New().String()
		}
		activeMu.Lock()
		activeReq++
		activeMu.Unlock()
		defer func() {
			activeMu.Lock()
			activeReq--
			activeMu.Unlock()
		}()

		select {
		case sem <- struct{}{}:
			defer func() { <-sem }()
			handleOrders(w, r)
		default:
			writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{
				Error: "overloaded", Code: 503, Message: "max concurrent requests exceeded",
			})
			reqCount.WithLabelValues(r.Method, r.URL.Path, "503").Inc()
			reqLatency.WithLabelValues(r.Method, r.URL.Path).Observe(time.Since(start).Seconds())
			logJSON(LogEntry{time.Now().UTC().Format(time.RFC3339Nano), r.Method, r.URL.Path, 503, time.Since(start).Milliseconds(), reqID})
		}
	})
	http.HandleFunc("/health", handleHealth)
	http.Handle("/metrics", promhttp.Handler())

	addr := ":" + cfg.Port
	if err := http.ListenAndServe(addr, nil); err != nil {
		panic(err)
	}
}

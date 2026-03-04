# Build stage
FROM golang:1.21-alpine AS builder
WORKDIR /app

COPY go.mod ./
RUN go mod download
COPY *.go ./
RUN CGO_ENABLED=0 GOOS=linux go build -o /order-service .

# Runtime stage
FROM alpine:3.19
RUN adduser -D -u 1000 appuser
WORKDIR /app

COPY --from=builder /order-service .
USER appuser

EXPOSE 8080
ENV PORT=8080
ENTRYPOINT ["/app/order-service"]

# Build stage. On Apple Silicon Mac, build with: docker build --platform linux/amd64 ...
FROM golang:1.21-alpine AS builder
WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download
COPY *.go ./
# Build for linux/amd64 so the image runs on EKS (x86) nodes.
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /order-service .

# Runtime stage
FROM alpine:3.19
RUN adduser -D -u 1000 appuser
WORKDIR /app

COPY --from=builder /order-service .
USER appuser

EXPOSE 8080
ENV PORT=8080
ENTRYPOINT ["/app/order-service"]

# Phase 5: Load Testing `order-service` with k6

This directory contains a simple k6 script to drive traffic against the `order-service` and observe HPA behaviour.

## Prerequisites

- `kubectl` configured for your EKS cluster.
- `order-service` and HPA deployed (see `k8s/README.md`).
- [k6](https://grafana.com/docs/k6/latest/get-started/installation/) installed on your local machine.

## 1. Get the LoadBalancer URL

```bash
kubectl get svc order-service -n order-processing
# Note the EXTERNAL-IP, e.g. a DNS name like a1234567890abcdef.elb.us-east-2.amazonaws.com
```

## 2. Run the k6 script

From the repo root:

```bash
k6 run -e BASE_URL=http://<EXTERNAL-IP> load-test/k6_script.js
```

The script:

- Always hits `/health`.
- On every other iteration sends a `POST /orders` with a small, random order payload.
- Uses a simple ramp-up / steady / ramp-down pattern (5 → 20 VUs).

## 3. Watch scaling behaviour

While the test runs, in another terminal:

```bash
kubectl get hpa -n order-processing
kubectl get deploy order-service -n order-processing
kubectl get pods -n order-processing -w
```

You should see:

- CPU utilization increase in the HPA.
- Desired replicas rising as load grows, and shrinking after load drops.

You can adjust load by editing the `stages` in `k6_script.js` or changing `CPU_INTENSITY` / `SIMULATED_LATENCY_MS` env vars on the `order-service` deployment.


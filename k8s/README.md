# Kubernetes Manifests (Phase 3)

Apply in order. Ensure `kubectl` is configured for your EKS cluster (`aws eks update-kubeconfig --region us-east-2 --name smart-scaling-guardian`).

## Prerequisites

1. **Order service image**: Build and push to ECR, then set the image in `deployment.yaml`:
   ```bash
   # From repo root. Use --platform linux/amd64 on Apple Silicon so EKS (x86) nodes can run the image.
   aws ecr get-login-password --region us-east-2 | docker login --username AWS --password-stdin <AWS_ACCOUNT_ID>.dkr.ecr.us-east-2.amazonaws.com
   docker build --platform linux/amd64 -t <AWS_ACCOUNT_ID>.dkr.ecr.us-east-2.amazonaws.com/order-service:v1.0.0 ./app
   docker push <AWS_ACCOUNT_ID>.dkr.ecr.us-east-2.amazonaws.com/order-service:v1.0.0
   ```
   Then in `deployment.yaml`, set `spec.template.spec.containers[0].image` to that URI.

2. **Secrets**: Copy `secret.yaml.example` to `secret.yaml`, set `GEMINI_API_KEY` and `SLACK_WEBHOOK_URL`, then apply (do not commit `secret.yaml`).

3. **Metrics Server** (required for HPA): If your EKS cluster does not have it, install with:
   ```bash
   kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
   ```
   Or use the EKS add-on: `aws eks create-addon --cluster-name smart-scaling-guardian --addon-name metrics-server --region us-east-2`

## Apply order

```bash
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
kubectl apply -f secret.yaml          # after creating from secret.yaml.example
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f hpa.yaml
kubectl apply -f rbac.yaml
# Phase 4 — Sentinel: build and push image (use --platform linux/amd64 on Apple Silicon), then:
# kubectl apply -f sentinel-deployment.yaml
```

## Verify

```bash
kubectl get ns order-processing
kubectl get deploy,svc,hpa -n order-processing
kubectl get pods -n order-processing -w
```

Get the LoadBalancer external hostname (may take 1–2 minutes):

```bash
kubectl get svc order-service -n order-processing
# Hit http://<EXTERNAL-IP>/health
```

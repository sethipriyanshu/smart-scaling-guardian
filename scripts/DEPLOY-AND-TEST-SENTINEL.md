# Deploy and test Sentinel (new card design)

Run from the **repo root** (`smart-scaling-guardian/`).

## 1. Build and push the new image

```bash
docker build --platform linux/amd64 -t 557260578041.dkr.ecr.us-east-2.amazonaws.com/sentinel:v1.0.4 ./sentinel
docker push 557260578041.dkr.ecr.us-east-2.amazonaws.com/sentinel:v1.0.4
```

(If needed, log in to ECR first: `aws ecr get-login-password --region us-east-2 | docker login --username AWS --password-stdin 557260578041.dkr.ecr.us-east-2.amazonaws.com`)

## 2. Roll out the new Sentinel (free slot, then restart)

```bash
./scripts/rollout-sentinel.sh
```

This scales order-service to 0, scales Sentinel to 0, applies the deployment (v1.0.4), scales Sentinel to 1, waits for rollout, then scales order-service back to 1.

## 3. Confirm the running pod is using the new image

```bash
kubectl get pods -n order-processing -l app=sentinel -o jsonpath='{.items[0].spec.containers[0].image}'
```

You should see: `.../sentinel:v1.0.4`

## 4. Trigger an event to test the card

Delete one order-service pod so Sentinel sends an alert:

```bash
kubectl get pods -n order-processing -l app=order-service -o name | head -1 | xargs kubectl delete -n order-processing
```

(Or scale to 0 then back to 1 to trigger a scaling event.)

## 5. Check Slack

- **Header** should include `· v2`.
- **In plain language** should be descriptive and technical (e.g. scaling down to zero: "The deployment was scaled down to zero replicas; no pods are running. This usually indicates HPA reduced replicas due to low load or an intentional scale-to-zero.").
- **Technical details** should show the three-section overview (What Happened, Why It Happened, Recommended Action) — not "AI analysis unavailable".

#!/bin/bash
# Force the cluster to run the NEW Sentinel image (new card UI).
# Run from repo root. Prereq: build & push sentinel with tag v1.0.1.
set -e
NS=order-processing

echo "1. Free a pod slot (scale order-service to 0)..."
kubectl scale deployment order-service -n $NS --replicas=0

echo "2. Stop all Sentinel pods so the next one will be fresh..."
kubectl scale deployment sentinel -n $NS --replicas=0
echo "   Waiting for sentinel pods to terminate..."
sleep 10

echo "3. Apply deployment and scale Sentinel to 1..."
kubectl apply -f k8s/sentinel-deployment.yaml
kubectl scale deployment sentinel -n $NS --replicas=1

echo "4. Waiting for Sentinel rollout to complete..."
kubectl rollout status deployment/sentinel -n $NS --timeout=120s

echo "5. Restore order-service..."
kubectl scale deployment order-service -n $NS --replicas=1

echo "Done. Verify the pod is using the new image:"
kubectl get pods -n $NS -l app=sentinel -o jsonpath='{.items[0].spec.containers[0].image}'
echo ""
echo "Trigger an event (e.g. delete a pod) and check Slack — the card should show '· v2' in the title and have no footer."

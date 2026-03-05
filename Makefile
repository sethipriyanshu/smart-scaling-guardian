# Smart-Scaling Guardian — common targets
# Run from repo root.

.PHONY: deploy-k8s deploy-k8s-order tear-k8s

# Deploy all order-processing resources (namespace, configmap, deployment, service, hpa, rbac).
# Prereqs: set image in k8s/deployment.yaml, create k8s/secret.yaml from k8s/secret.yaml.example.
deploy-k8s:
	kubectl apply -f k8s/namespace.yaml
	kubectl apply -f k8s/configmap.yaml
	-kubectl apply -f k8s/secret.yaml
	kubectl apply -f k8s/deployment.yaml
	kubectl apply -f k8s/service.yaml
	kubectl apply -f k8s/hpa.yaml
	kubectl apply -f k8s/rbac.yaml

# Deploy only the order-service app (assumes namespace and configmap exist).
deploy-k8s-order:
	kubectl apply -f k8s/deployment.yaml
	kubectl apply -f k8s/service.yaml
	kubectl apply -f k8s/hpa.yaml

# Deploy Sentinel after building/pushing image: docker build --platform linux/amd64 -t 557260578041.dkr.ecr.us-east-2.amazonaws.com/sentinel:v1.0.0 ./sentinel && docker push ...
deploy-sentinel:
	kubectl apply -f k8s/sentinel-deployment.yaml

tear-k8s:
	kubectl delete -f k8s/sentinel-deployment.yaml --ignore-not-found
	kubectl delete -f k8s/rbac.yaml --ignore-not-found
	kubectl delete -f k8s/hpa.yaml --ignore-not-found
	kubectl delete -f k8s/service.yaml --ignore-not-found
	kubectl delete -f k8s/deployment.yaml --ignore-not-found
	kubectl delete -f k8s/secret.yaml --ignore-not-found
	kubectl delete -f k8s/configmap.yaml --ignore-not-found
	kubectl delete -f k8s/namespace.yaml --ignore-not-found

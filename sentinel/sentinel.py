"""
Sentinel: watch Kubernetes events in order-processing namespace, run AI summary, send Slack.
"""
import json
import logging
import os
import time
from kubernetes import client, config
from kubernetes.watch import Watch

from dedup_cache import DedupCache
from event_handler import process_event

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format="%(message)s")
logger = logging.getLogger(__name__)


def log_json(msg: str, **kwargs) -> None:
    line = {"message": msg, **kwargs}
    print(json.dumps(line), flush=True)


def load_k8s_config() -> tuple[client.CoreV1Api, client.AppsV1Api, client.AutoscalingV2Api]:
    try:
        config.load_incluster_config()
        log_json("Loaded in-cluster Kubernetes config")
    except config.ConfigException:
        config.load_kube_config()
        log_json("Loaded kubeconfig")
    v1 = client.CoreV1Api()
    v1_apps = client.AppsV1Api()
    v2_autoscaling = client.AutoscalingV2Api()
    return v1, v1_apps, v2_autoscaling


def run() -> None:
    namespace = os.environ.get("K8S_NAMESPACE", "order-processing")
    cluster_name = os.environ.get("CLUSTER_NAME", "smart-scaling-guardian")
    dedup_ttl = int(os.environ.get("DEDUP_CACHE_TTL_SECONDS", "300"))
    dedup_cache = DedupCache(ttl_seconds=dedup_ttl)

    v1_core, v1_apps, v2_autoscaling = load_k8s_config()
    watch = Watch()

    backoff = 1.0
    max_backoff = 60.0
    while True:
        try:
            log_json("Starting event watch", namespace=namespace)
            for event in watch.stream(
                v1_core.list_namespaced_event,
                namespace,
                timeout_seconds=3600,
            ):
                obj = event.get("object")
                if not obj:
                    continue
                ev = obj.to_dict() if hasattr(obj, "to_dict") else obj
                try:
                    process_event(
                        ev,
                        namespace=namespace,
                        cluster_name=cluster_name,
                        dedup_cache=dedup_cache,
                        v1_core=v1_core,
                        v1_apps=v1_apps,
                        v2_autoscaling=v2_autoscaling,
                    )
                except Exception as e:
                    log_json("Event processing failed", error=str(e), event_uid=ev.get("metadata", {}).get("uid"))
                    logger.exception("process_event failed")
            backoff = 1.0
        except Exception as e:
            log_json("Watch stream error, reconnecting", error=str(e), backoff_seconds=backoff)
            logger.exception("Watch failed")
            time.sleep(backoff)
            backoff = min(backoff * 2 + (time.time() % 1), max_backoff)


if __name__ == "__main__":
    run()

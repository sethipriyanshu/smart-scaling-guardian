"""
Handle a single Kubernetes event: collect context, call Gemini, send Slack.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from kubernetes import client
from kubernetes.client.rest import ApiException

from dedup_cache import DedupCache
from gemini_client import get_ai_summary, FALLBACK_MESSAGE
from slack_notifier import build_blocks, send_slack

logger = logging.getLogger(__name__)


def _build_technical_fallback(
    reason: str,
    message: str,
    involved_kind: str,
    involved_name: str,
    namespace: str,
    replica_section: str,
    current_replicas: int | None,
    desired_replicas: int | None,
) -> str:
    """Build a technical overview when AI is unavailable so Technical details is never 'unavailable'."""
    lines = []
    # What Happened
    what = f"{reason}: {message}".strip() if message else reason
    if replica_section:
        what += f" {replica_section}"
    elif current_replicas is not None and desired_replicas is not None:
        what += f" Current replicas: {current_replicas}, Desired: {desired_replicas}."
    lines.append(f"What Happened: {what}")
    # Why It Happened
    why_map = {
        "ScalingReplicaSet": "The deployment replica count was changed by the HorizontalPodAutoscaler (HPA) or a manual scale. Desired replicas now match the HPA target or the applied manifest.",
        "Killing": "The pod was terminated, e.g. by a rollout, node drain, or manual delete (kubectl delete pod).",
        "OOMKilling": "The container exceeded its memory limit and was killed by the kernel (OOMKiller).",
        "BackOff": "The container is crashing on start; Kubernetes is backing off before restarting again.",
        "Failed": "The container failed to start (e.g. image pull error, entrypoint failure, or missing config).",
        "Unhealthy": "A liveness or readiness probe failed; the pod was marked unhealthy.",
    }
    why = why_map.get(reason, f"Kubernetes reported event reason '{reason}' for {involved_kind}/{involved_name} in namespace {namespace}.")
    lines.append(f"Why It Happened: {why}")
    # Recommended Action
    action_map = {
        "ScalingReplicaSet": "If scale-to-zero is expected, no action needed. To restore service: kubectl scale deployment <name> -n " + namespace + " --replicas=1 (or let HPA scale up under load).",
        "Killing": "Check if this was intentional (rollout/delete). If not, inspect pod logs and events (kubectl describe pod) and redeploy if needed.",
        "OOMKilling": "ACTION REQUIRED: Increase memory limit or fix memory leak; then redeploy the workload.",
        "BackOff": "ACTION REQUIRED: Check pod logs and events; fix the failing container (config, image, or startup command) and redeploy.",
        "Failed": "ACTION REQUIRED: Fix image, config, or startup issue and redeploy.",
        "Unhealthy": "ACTION REQUIRED: Fix health checks or application readiness; then redeploy or restart.",
    }
    action = action_map.get(reason, "Review the event and namespace resources; take action if the workload is critical.")
    lines.append(f"Recommended Action: {action}")
    return "\n".join(lines)


def _build_plain_language_fallback(
    reason: str,
    message: str,
    involved_name: str,
    current_replicas: int | None,
    desired_replicas: int | None,
) -> str:
    """Build a descriptive, technical one-liner when AI is unavailable."""
    if reason == "ScalingReplicaSet" and current_replicas is not None and desired_replicas is not None:
        if desired_replicas == 0:
            return "The deployment was scaled down to zero replicas; no pods are running. This usually indicates HPA reduced replicas due to low load or an intentional scale-to-zero."
        if desired_replicas > (current_replicas or 0):
            return f"The deployment is scaling up from {current_replicas or 0} to {desired_replicas} replicas. HPA or a manual scale triggered the change."
        return f"The deployment replica count changed to {desired_replicas} (current: {current_replicas}). HPA or a manual scale triggered the change."
    if reason == "Killing":
        return f"Pod '{involved_name}' was terminated (e.g. rollout, node drain, or manual delete)."
    if reason == "OOMKilling":
        return f"Pod '{involved_name}' was killed by the system for exceeding its memory limit (OOM)."
    if reason == "BackOff":
        return f"Pod '{involved_name}' is in a crash loop: it is failing to start and Kubernetes is backing off between restarts."
    if reason == "Failed":
        return f"Pod '{involved_name}' failed to start (e.g. image pull or startup error)."
    if reason == "Unhealthy":
        return f"Pod '{involved_name}' failed a health check and was marked unhealthy."
    return f"Kubernetes event: {reason} — {message or involved_name}."

# Killing included so that "kubectl delete pod" triggers a test alert; FRD marks it as informational-only.
DEFAULT_REASONS_OF_INTEREST = frozenset({"ScalingReplicaSet", "OOMKilling", "BackOff", "Failed", "Unhealthy", "Killing"})


def _reasons_of_interest() -> frozenset[str]:
    """
    Comma-separated allowlist of reasons to alert on.
    Example: ALERT_REASONS=OOMKilling,BackOff,Failed,Unhealthy,Killing
    If unset/empty, defaults to DEFAULT_REASONS_OF_INTEREST.
    """
    raw = (os.environ.get("ALERT_REASONS") or "").strip()
    if not raw:
        return DEFAULT_REASONS_OF_INTEREST
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return frozenset(parts) if parts else DEFAULT_REASONS_OF_INTEREST


def _get_deployment_status(v1_apps: client.AppsV1Api, namespace: str, name: str) -> dict[str, Any] | None:
    try:
        dep = v1_apps.read_namespaced_deployment(name, namespace)
        if not dep or not dep.status:
            return None
        s = dep.status
        return {
            "desired": s.replicas or 0,
            "current": s.ready_replicas or 0,
            "available": s.available_replicas or 0,
        }
    except ApiException:
        return None


def _get_hpa_status(v2_autoscaling: client.AutoscalingV2Api, namespace: str, name: str) -> dict[str, Any] | None:
    try:
        hpa = v2_autoscaling.read_namespaced_horizontal_pod_autoscaler(name, namespace)
        if not hpa or not hpa.status:
            return None
        s = hpa.status
        current_cpu = "N/A"
        try:
            for m in (s.current_metrics or []):
                if getattr(m, "type", None) == "Resource" and getattr(m, "resource", None):
                    res = m.resource
                    if getattr(res, "name", None) == "cpu" and getattr(res, "current", None):
                        current_cpu = f"{int(getattr(res.current, 'average_utilization', 0) or 0)}%"
                        break
        except (AttributeError, TypeError):
            pass
        return {
            "current_replicas": s.current_replicas or 0,
            "desired_replicas": s.desired_replicas or 0,
            "cpu": current_cpu,
            "last_scale_time": str(s.last_scale_time) if getattr(s, "last_scale_time", None) else None,
        }
    except ApiException:
        return None


def _get_pod_logs(v1_core: client.CoreV1Api, namespace: str, pod_name: str, tail_lines: int = 100) -> str:
    try:
        return v1_core.read_namespaced_pod_log(pod_name, namespace, tail_lines=tail_lines)
    except ApiException:
        return ""


def _get_pod_info(v1_core: client.CoreV1Api, namespace: str, pod_name: str) -> dict[str, Any]:
    try:
        pod = v1_core.read_namespaced_pod(pod_name, namespace)
        status = pod.status
        exit_code = ""
        restart_count = "0"
        oom_killed = "false"
        if status and status.container_statuses:
            for cs in status.container_statuses:
                if cs.state and cs.state.terminated:
                    exit_code = str(cs.state.terminated.exit_code or "")
                restart_count = str(cs.restart_count or 0)
                if cs.last_state and cs.last_state.terminated and cs.last_state.terminated.reason == "OOMKilled":
                    oom_killed = "true"
        return {"exit_code": exit_code, "restart_count": restart_count, "oom_killed": oom_killed}
    except ApiException:
        return {"exit_code": "N/A", "restart_count": "N/A", "oom_killed": "N/A"}


def process_event(
    event: dict[str, Any],
    namespace: str,
    cluster_name: str,
    dedup_cache: DedupCache,
    v1_core: client.CoreV1Api,
    v1_apps: client.AppsV1Api,
    v2_autoscaling: client.AutoscalingV2Api,
) -> None:
    """Process one event: dedup, collect context, Gemini, Slack."""
    metadata = event.get("metadata", {})
    uid = metadata.get("uid", "")
    resource_version = metadata.get("resourceVersion", "")
    if dedup_cache.seen(uid, resource_version):
        logger.info("Event deduplicated uid=%s", uid)
        return

    involved = event.get("involvedObject", {})
    involved_kind = involved.get("kind", "")
    involved_name = involved.get("name", "")
    reason = event.get("reason", "")
    if reason not in _reasons_of_interest():
        return

    # Avoid noisy self-alerts: ignore Sentinel's own scaling/pod events
    if involved_name.startswith("sentinel"):
        logger.info("Skipping Sentinel self-event: %s %s", involved_kind, involved_name)
        return

    message = event.get("message", "")
    count = event.get("count", 1)
    # Kubernetes updates the same Event object by incrementing count; alert only on the first occurrence.
    if isinstance(count, int) and count > 1:
        return
    detection_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    logger.info("Processing event reason=%s name=%s", reason, involved_name)

    replica_section = ""
    pod_logs_section = ""
    current_replicas = None
    desired_replicas = None
    cpu_pct = None
    last_scale_time = None
    pod_name = None
    exit_code = None
    restart_count = None
    oom_killed = None
    replica_delta = None

    if involved_kind in ("Deployment", "ReplicaSet") or reason == "ScalingReplicaSet":
        dep_name = "order-service" if reason == "ScalingReplicaSet" else involved_name
        dep_status = _get_deployment_status(v1_apps, namespace, dep_name)
        if dep_status:
            current_replicas = dep_status.get("current")
            desired_replicas = dep_status.get("desired")
            replica_section = f"Current replicas: {current_replicas}, Desired: {desired_replicas}."
        hpa_status = _get_hpa_status(v2_autoscaling, namespace, "order-service-hpa")
        if hpa_status:
            cpu_pct = hpa_status.get("cpu")
            last_scale_time = hpa_status.get("last_scale_time")
            if current_replicas is None:
                current_replicas = hpa_status.get("current_replicas")
            if desired_replicas is None:
                desired_replicas = hpa_status.get("desired_replicas")
            if current_replicas is not None and desired_replicas is not None:
                replica_delta = desired_replicas - current_replicas

    if involved_kind == "Pod":
        pod_name = involved_name
        pod_info = _get_pod_info(v1_core, namespace, pod_name)
        exit_code = pod_info.get("exit_code")
        restart_count = pod_info.get("restart_count")
        oom_killed = pod_info.get("oom_killed")
        logs = _get_pod_logs(v1_core, namespace, pod_name)
        pod_logs_section = f"Last 100 lines of pod logs:\n{logs}" if logs else "No logs available."

    raw_event_json = json.dumps(event, default=str)
    event_type = event.get("type", "Normal")

    try:
        ai_insight, plain_language = get_ai_summary(
            event_type=event_type,
            reason=reason,
            message=message,
            involved_name=involved_name,
            involved_kind=involved_kind,
            namespace=namespace,
            count=count,
            detection_time=detection_time,
            replica_section=replica_section,
            pod_logs_section=pod_logs_section,
        )
        # When Gemini is unavailable, replace with technical + plain-language fallbacks so the card is never vague
        if not ai_insight or ai_insight.strip() == FALLBACK_MESSAGE.strip():
            ai_insight = _build_technical_fallback(
                reason=reason,
                message=message,
                involved_kind=involved_kind,
                involved_name=involved_name,
                namespace=namespace,
                replica_section=replica_section,
                current_replicas=current_replicas,
                desired_replicas=desired_replicas,
            )
            plain_language = _build_plain_language_fallback(
                reason=reason,
                message=message,
                involved_name=involved_name,
                current_replicas=current_replicas,
                desired_replicas=desired_replicas,
            )
        blocks = build_blocks(
            reason=reason,
            namespace=namespace,
            cluster_name=cluster_name,
            detection_time=detection_time,
            ai_insight=ai_insight or "—",
            plain_language=plain_language or "",
            current_replicas=current_replicas,
            desired_replicas=desired_replicas,
            cpu_pct=cpu_pct,
            last_scale_time=last_scale_time,
            pod_name=pod_name,
            exit_code=exit_code,
            restart_count=restart_count,
            oom_killed=oom_killed,
            replica_delta=replica_delta,
        )
        ok = send_slack(blocks)
        logger.info("Slack sent ok=%s for event uid=%s", ok, uid)
    except Exception as e:
        logger.exception("Failed to process event uid=%s: %s", uid, e)
        tech_fallback = _build_technical_fallback(
            reason=reason,
            message=message,
            involved_kind=involved_kind,
            involved_name=involved_name,
            namespace=namespace,
            replica_section=replica_section,
            current_replicas=current_replicas,
            desired_replicas=desired_replicas,
        )
        plain_fallback = _build_plain_language_fallback(
            reason=reason,
            message=message,
            involved_name=involved_name,
            current_replicas=current_replicas,
            desired_replicas=desired_replicas,
        )
        fallback_blocks = build_blocks(
            reason=reason,
            namespace=namespace,
            cluster_name=cluster_name,
            detection_time=detection_time,
            ai_insight=f"{tech_fallback}\n\n(Processing error during AI call: {e})",
            plain_language=plain_fallback,
            current_replicas=current_replicas,
            desired_replicas=desired_replicas,
            cpu_pct=cpu_pct,
            last_scale_time=last_scale_time,
            pod_name=pod_name,
            exit_code=exit_code,
            restart_count=restart_count,
            oom_killed=oom_killed,
            replica_delta=replica_delta,
        )
        send_slack(fallback_blocks)

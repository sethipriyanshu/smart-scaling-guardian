"""
Build Slack Block Kit payload and POST to webhook with retry.
"""
import os
import time
import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Backup plain-language when neither AI nor event_handler fallback provided one (reason -> line)
REASON_FALLBACK = {
    "ScalingReplicaSet": "The deployment replica count was changed (by HPA or manual scale). Current and desired replicas may have been updated.",
    "Killing": "A pod was terminated (e.g. rollout, node drain, or manual delete).",
    "OOMKilling": "A container exceeded its memory limit and was killed by the kernel (OOMKiller).",
    "BackOff": "A pod is in a crash loop: failing to start with Kubernetes backing off between restarts.",
    "Failed": "A pod failed to start (e.g. image pull failure, entrypoint error, or missing config).",
    "Unhealthy": "A pod failed a liveness or readiness probe and was marked unhealthy.",
}

# Event type -> (color, icon, status_label) for distinct card headers
EVENT_STYLE = {
    "ScalingReplicaSet": ("#2ECC71", "📈", "Scaling Event"),
    "ScaleUp": ("#2ECC71", "📈", "Scaling Up"),
    "ScaleDown": ("#3498DB", "📉", "Scaling Down"),
    "OOMKilling": ("#E67E22", "⚠", "Memory limit exceeded"),
    "BackOff": ("#E74C3C", "🔴", "Critical — Pod crashing"),
    "Failed": ("#9B59B6", "🚫", "Image or start error"),
    "Unhealthy": ("#F39C12", "💛", "Health check failed"),
    "Killing": ("#95A5A6", "⏹", "Pod terminated"),
}


def _style(reason: str, replica_delta: int | None) -> tuple[str, str, str]:
    if reason == "ScalingReplicaSet" and replica_delta is not None:
        if replica_delta > 0:
            return ("#2ECC71", "📈", f"Scaling up (+{replica_delta} pods)")
        return ("#3498DB", "📉", f"Scaling down ({replica_delta} pods)")
    return EVENT_STYLE.get(reason, ("#95A5A6", "📌", reason))


def build_blocks(
    reason: str,
    namespace: str,
    cluster_name: str,
    detection_time: str,
    ai_insight: str,
    plain_language: str = "",
    current_replicas: int | None = None,
    desired_replicas: int | None = None,
    cpu_pct: str | None = None,
    last_scale_time: str | None = None,
    pod_name: str | None = None,
    exit_code: str | None = None,
    restart_count: str | None = None,
    oom_killed: str | None = None,
    replica_delta: int | None = None,
) -> list[dict[str, Any]]:
    color, icon, status_label = _style(reason, replica_delta)
    # Distinct title; "· v2" confirms new card UI is running
    title = f"{icon} {status_label} — {cluster_name} · v2"

    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": title, "emoji": True}},
    ]

    # Plain-language summary first; use reason-based fallback when AI didn't provide one
    summary = plain_language or REASON_FALLBACK.get(reason, "An infrastructure event occurred; see technical details.")
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"*In plain language:*\n{summary}"},
    })
    blocks.append({"type": "divider"})

    # Metadata in a compact row
    blocks.append({
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": f"*When:*\n{detection_time}"},
            {"type": "mrkdwn", "text": f"*Namespace:*\n{namespace}"},
        ],
    })

    # Technical insight (for DevOps)
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"*Technical details*\n{ai_insight}"},
    })

    if current_replicas is not None and desired_replicas is not None:
        blocks.append({
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Current replicas:*\n{current_replicas}"},
                {"type": "mrkdwn", "text": f"*Desired replicas:*\n{desired_replicas}"},
                {"type": "mrkdwn", "text": f"*CPU:*\n{cpu_pct or 'N/A'}"},
                {"type": "mrkdwn", "text": f"*Last scale:*\n{last_scale_time or 'N/A'}"},
            ],
        })

    if pod_name:
        blocks.append({
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Pod:*\n{pod_name}"},
                {"type": "mrkdwn", "text": f"*Exit code:*\n{exit_code or 'N/A'}"},
                {"type": "mrkdwn", "text": f"*Restarts:*\n{restart_count or 'N/A'}"},
                {"type": "mrkdwn", "text": f"*OOM killed:*\n{oom_killed or 'N/A'}"},
            ],
        })

    grafana_url = os.environ.get("GRAFANA_DASHBOARD_URL", "http://grafana/placeholder")
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "actions",
        "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "View Grafana"}, "url": grafana_url, "style": "primary"},
            {"type": "button", "text": {"type": "plain_text", "text": "View logs"}, "url": grafana_url},
            {"type": "button", "text": {"type": "plain_text", "text": "Acknowledge"}, "url": grafana_url},
        ],
    })
    return blocks


def send_slack(blocks: list[dict[str, Any]]) -> bool:
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        logger.error("SLACK_WEBHOOK_URL not set")
        return False
    timeout = int(os.environ.get("SLACK_TIMEOUT_SECONDS", "10"))
    payload = {"blocks": blocks}
    for attempt in range(3):
        try:
            r = requests.post(url, json=payload, timeout=timeout)
            if r.status_code == 200:
                return True
            logger.warning("Slack returned %s: %s", r.status_code, r.text)
        except Exception as e:
            logger.warning("Slack POST failed: %s", e)
        if attempt < 2:
            time.sleep(2)
    return False

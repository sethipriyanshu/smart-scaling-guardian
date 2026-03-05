"""
Gemini API client: load prompt template, call API with retry/timeout, validate and sanitize response.
"""
import os
import re
import time
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# Sections we require in the AI response (plain-language is optional for display)
REQUIRED_SECTIONS = ("What Happened", "Why It Happened", "Recommended Action")
FALLBACK_MESSAGE = "AI analysis unavailable — raw event data attached."
PLAIN_LANGUAGE_FALLBACK = "Something changed in the system; the team has been notified."


def _load_prompt_template(path: str | None) -> str:
    if path and Path(path).exists():
        return Path(path).read_text()
    default = Path(__file__).parent / "prompts" / "sentinel_prompt.txt"
    if default.exists():
        return default.read_text()
    return "Analyze this Kubernetes event. Respond with: (1) What Happened (2) Why It Happened (3) Recommended Action. Max 150 words."


def _retry_with_backoff(max_retries: int = 3, timeout_seconds: int = 15):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            last_err = None
            for attempt in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    last_err = e
                    if attempt < max_retries - 1:
                        delay = min(2 ** attempt + (attempt * 0.5), 10)
                        logger.warning("Gemini attempt %s failed: %s; retry in %ss", attempt + 1, e, delay)
                        time.sleep(delay)
            raise last_err
        return wrapper
    return decorator


def _validate_and_sanitize(text: str) -> str | None:
    if not text or not text.strip():
        return None
    for section in REQUIRED_SECTIONS:
        if section not in text:
            return None
    # Remove Markdown that breaks Slack mrkdwn
    sanitized = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    sanitized = re.sub(r"\*(.+?)\*", r"\1", sanitized)
    sanitized = re.sub(r"^#+\s*", "", sanitized, flags=re.MULTILINE)
    return sanitized.strip()


def _extract_plain_language(text: str) -> str:
    """Extract the sentence after 'In plain language' or similar."""
    import re as re_mod
    for pattern in [
        r"In plain language[^:]*:\s*(.+?)(?=\n\n|\n\(|\Z)",
        r"plain language[^:]*:\s*(.+?)(?=\n\n|\Z)",
    ]:
        m = re_mod.search(pattern, text, re_mod.DOTALL | re_mod.IGNORECASE)
        if m:
            return m.group(1).strip().split("\n")[0][:200]
    return ""


def get_ai_summary(
    event_type: str,
    reason: str,
    message: str,
    involved_name: str,
    involved_kind: str,
    namespace: str,
    count: int,
    detection_time: str,
    replica_section: str = "",
    pod_logs_section: str = "",
) -> tuple[str, str]:
    """
    Call Gemini and return (ai_insight_full, plain_language_sentence).
    On failure returns (FALLBACK_MESSAGE, PLAIN_LANGUAGE_FALLBACK).
    """
    try:
        import google.generativeai as genai
    except ImportError:
        logger.error("google-generativeai not installed")
        return (FALLBACK_MESSAGE, PLAIN_LANGUAGE_FALLBACK)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY not set")
        return (FALLBACK_MESSAGE, PLAIN_LANGUAGE_FALLBACK)

    model_name = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
    timeout = int(os.environ.get("GEMINI_TIMEOUT_SECONDS", "15"))
    prompt_path = os.environ.get("PROMPT_TEMPLATE_PATH", "prompts/sentinel_prompt.txt")

    template = _load_prompt_template(prompt_path)
    prompt = template.format(
        event_type=event_type,
        reason=reason,
        message=message,
        involved_name=involved_name,
        involved_kind=involved_kind,
        namespace=namespace,
        count=count,
        detection_time=detection_time,
        replica_section=replica_section or "",
        pod_logs_section=pod_logs_section or "",
    )

    def _generate():
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(max_output_tokens=256),
        )
        if response and response.text:
            return response.text
        raise ValueError("Empty response")

    max_retries = int(os.environ.get("GEMINI_MAX_RETRIES", "3"))
    result = None
    for attempt in range(max_retries):
        err = []

        def _run():
            try:
                nonlocal result
                result = _generate()
            except Exception as e:
                err.append(e)

        thread = threading.Thread(target=_run)
        thread.daemon = True
        thread.start()
        thread.join(timeout=timeout)
        if thread.is_alive():
            logger.warning("Gemini call timed out after %ss", timeout)
            return (FALLBACK_MESSAGE, PLAIN_LANGUAGE_FALLBACK)
        if not err and result:
            break
        if err and attempt < max_retries - 1:
            time.sleep(min(2 ** attempt + attempt * 0.5, 10))

    try:
        validated = _validate_and_sanitize(result or "")
        if validated:
            plain = _extract_plain_language(validated)
            if not plain:
                plain = PLAIN_LANGUAGE_FALLBACK
            return (validated, plain)
        return (FALLBACK_MESSAGE, PLAIN_LANGUAGE_FALLBACK)
    except Exception as e:
        logger.exception("Gemini call failed: %s", e)
        return (FALLBACK_MESSAGE, PLAIN_LANGUAGE_FALLBACK)

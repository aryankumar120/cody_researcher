import json
import re
import time
import threading
from groq import Groq, APIStatusError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from backend.config import settings

_client = Groq(api_key=settings.groq_api_key) if settings.groq_api_key else None

# Simple rate limiter to stay within Groq free-tier TPM limits
_call_lock = threading.Lock()
_last_call_time = 0.0
_MIN_CALL_INTERVAL = 2.0  # seconds between calls


def _rate_limit():
    """Sleep if needed so we don't fire calls faster than the TPM ceiling allows."""
    global _last_call_time
    with _call_lock:
        now = time.time()
        elapsed = now - _last_call_time
        if elapsed < _MIN_CALL_INTERVAL:
            time.sleep(_MIN_CALL_INTERVAL - elapsed)
        _last_call_time = time.time()


class LLMError(Exception):
    pass


def _is_retryable(exception):
    """Don't retry errors that will always fail (payload too large, bad request)."""
    if isinstance(exception, APIStatusError):
        return exception.status_code not in (400, 413, 422)
    return True


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception(_is_retryable),
)
def _call(system: str, user: str, max_tokens: int = 1500) -> str:
    if _client is None:
        raise LLMError("GROQ_API_KEY is not set")
    _rate_limit()
    resp = _client.chat.completions.create(
        model=settings.groq_model,
        max_completion_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""


def _extract_json(raw: str):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(json)?", "", raw).rstrip("`").strip()
    match = re.search(r"(\[.*\]|\{.*\})", raw, re.DOTALL)
    candidate = match.group(1) if match else raw
    return json.loads(candidate)


def ask_json(system: str, user: str, max_tokens: int = 1500):
    """Call the model and parse the reply as JSON. Raises LLMError if the
    model did not return anything we can parse, after one retry with a
    stricter reminder - malformed structured output from an LLM is
    expected, not exceptional, so callers must handle LLMError."""
    raw = _call(system, user, max_tokens=max_tokens)
    try:
        return _extract_json(raw)
    except (json.JSONDecodeError, AttributeError):
        raw2 = _call(
            system + "\n\nIMPORTANT: reply with ONLY valid JSON, no prose, no markdown fences.",
            user,
            max_tokens=max_tokens,
        )
        try:
            return _extract_json(raw2)
        except (json.JSONDecodeError, AttributeError) as e:
            raise LLMError(f"model did not return parseable JSON: {raw2[:300]}") from e


def ask_text(system: str, user: str, max_tokens: int = 1500) -> str:
    return _call(system, user, max_tokens=max_tokens)

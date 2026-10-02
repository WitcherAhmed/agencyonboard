"""Thin OpenAI-compatible chat client for whatever model is configured."""
import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List

import config

TIMEOUT = 120
MAX_RETRIES = 3


def chat(messages: List[Dict[str, Any]], tools=None, max_tokens: int = 1200) -> Dict[str, Any]:
    """One completion. Retries transient failures. Raises RuntimeError if it can't."""
    body = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"

    last_err = ""
    for attempt in range(1, MAX_RETRIES + 1):
        req = urllib.request.Request(
            config.LLM_BASE_URL.rstrip("/") + "/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + config.LLM_API_KEY,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            last_err = f"HTTP {exc.code}: {detail}"
            if exc.code in (400, 401, 403):  # no point retrying
                break
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {exc}"
        if attempt < MAX_RETRIES:
            time.sleep(2 * attempt)
    raise RuntimeError(f"LLM call failed after {MAX_RETRIES} attempts -> {last_err}")


def image_part(b64: str) -> Dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}
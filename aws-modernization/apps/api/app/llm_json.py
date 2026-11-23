"""Small helper: ask the LLM gateway for JSON and parse it defensively."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from .llm_gateway import TaskType, gateway

logger = logging.getLogger(__name__)


def extract_json(text: str | None) -> Any | None:
    """Parse the first JSON value in an LLM reply (handles ```json fences and chatter)."""
    if not text:
        return None
    clean = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", clean, re.DOTALL)
    if fence:
        clean = fence.group(1).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass
    # Fall back to the outermost {...} or [...] span.
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start, end = clean.find(open_c), clean.rfind(close_c)
        if start != -1 and end > start:
            try:
                return json.loads(clean[start:end + 1])
            except json.JSONDecodeError:
                continue
    return None


def ask_json(system: str, user: str, *, max_tokens: int = 3000,
             task_type: TaskType = "reasoning") -> tuple[Any | None, str | None]:
    """Returns (parsed_json_or_None, model_id_or_None). None means: unavailable or unparsable."""
    try:
        reply = gateway.invoke(system_prompt=system, user_prompt=user, task_type=task_type,
                               max_tokens=max_tokens, temperature=0.1)
    except Exception as exc:  # gateway must never take a request down
        logger.warning("LLM call failed: %s", exc)
        return None, None
    parsed = extract_json(reply)
    if reply and parsed is None:
        logger.warning("LLM reply was not valid JSON (first 200 chars): %s", reply[:200])
    return parsed, (gateway.get_model_for_task(task_type) if parsed is not None else None)

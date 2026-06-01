"""Helpers for subprocess-based benchmark adapters."""

from __future__ import annotations

import json
from typing import Any, Optional


def extract_prefixed_json(stdout: str, prefix: str) -> Optional[dict[str, Any]]:
    """Return the last JSON object printed as `<prefix><json>`."""

    for raw in reversed(stdout.splitlines()):
        line = raw.strip()
        if not line.startswith(prefix):
            continue
        payload = line[len(prefix) :].strip()
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def tail_text(text: str, limit: int = 8000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]

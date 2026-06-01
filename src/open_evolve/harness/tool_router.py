"""Tool allowlist checks."""

from __future__ import annotations

from open_evolve.harness.harness_spec import HarnessSpec


def tool_allowed(spec: HarnessSpec, tool_name: str) -> bool:
    allowed = spec.tool_policy.get("allow")
    denied = spec.tool_policy.get("deny", [])
    if tool_name in denied:
        return False
    if allowed is None:
        return True
    return tool_name in allowed

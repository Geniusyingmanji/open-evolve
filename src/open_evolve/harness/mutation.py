"""Safe configuration-level harness mutations."""

from __future__ import annotations

import copy
from typing import Any

from open_evolve.harness.harness_spec import HarnessSpec


SAFE_TOP_LEVEL_POLICIES = {
    "tool_policy",
    "context_policy",
    "memory_policy",
    "verification_policy",
    "feedback_policy",
    "search_policy",
    "budget_policy",
    "promotion_gates",
    "rollback_policy",
    "metadata",
}


def mutate_policy(spec: HarnessSpec, policy_name: str, key: str, value: Any, new_version: str) -> HarnessSpec:
    if policy_name not in SAFE_TOP_LEVEL_POLICIES:
        raise ValueError("unsafe harness policy mutation: %s" % policy_name)
    data = copy.deepcopy(spec.__dict__)
    policy = dict(data.get(policy_name, {}))
    policy[key] = value
    data[policy_name] = policy
    data["version"] = new_version
    mutated = HarnessSpec(**data)
    mutated.validate()
    return mutated

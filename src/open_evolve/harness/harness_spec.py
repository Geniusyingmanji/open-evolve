"""Declarative harness specification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from open_evolve.core.types import JsonDict


@dataclass
class HarnessSpec:
    name: str
    version: str
    task_family: str
    agent_roles: List[str] = field(default_factory=list)
    tool_policy: JsonDict = field(default_factory=dict)
    context_policy: JsonDict = field(default_factory=dict)
    memory_policy: JsonDict = field(default_factory=dict)
    verification_policy: JsonDict = field(default_factory=dict)
    feedback_policy: JsonDict = field(default_factory=dict)
    search_policy: JsonDict = field(default_factory=dict)
    budget_policy: JsonDict = field(default_factory=dict)
    promotion_gates: JsonDict = field(default_factory=dict)
    rollback_policy: JsonDict = field(default_factory=dict)
    metadata: JsonDict = field(default_factory=dict)

    def validate(self) -> None:
        if not self.name:
            raise ValueError("HarnessSpec.name is required")
        if not self.version:
            raise ValueError("HarnessSpec.version is required")
        if not self.task_family:
            raise ValueError("HarnessSpec.task_family is required")
        if "allow" in self.tool_policy and not isinstance(self.tool_policy["allow"], list):
            raise ValueError("tool_policy.allow must be a list when present")

    @classmethod
    def default(cls, task_family: str = "generic") -> "HarnessSpec":
        return cls(
            name="%s_default" % task_family,
            version="0.1.0",
            task_family=task_family,
            agent_roles=["strategist", "implementer", "debugger", "evaluator"],
            tool_policy={"allow": ["read", "write", "execute", "evaluate"]},
            context_policy={"mode": "task_notebook", "max_history_events": 200},
            memory_policy={"write_gate": "verified_replay"},
            verification_policy={"cascade": ["lint", "smoke", "proxy", "full"]},
            feedback_policy={"summarize": True, "efc_gate": False},
            search_policy={"kind": "hybrid_depth", "parent_pool_size": 1},
            budget_policy={"max_iterations": 20, "max_evaluations": 100},
            promotion_gates={"require_replay": True, "max_regression": 0.0},
            rollback_policy={"enabled": True, "health_probe": "replay_smoke"},
        )

    def copy_with(self, **updates: Any) -> "HarnessSpec":
        data = dict(self.__dict__)
        data.update(updates)
        return HarnessSpec(**data)

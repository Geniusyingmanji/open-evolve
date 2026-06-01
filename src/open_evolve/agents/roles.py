"""Minimal role abstraction.

The first framework version keeps roles declarative. Concrete LLM-backed agents
can later implement the same interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class RoleDecision:
    action: str
    rationale: str = ""
    metadata: Dict[str, object] = field(default_factory=dict)


class AgentRole:
    name = "agent"

    def decide(self, context: Dict[str, object]) -> RoleDecision:
        return RoleDecision(action="noop", rationale="Base role has no policy.", metadata={"context_keys": list(context.keys())})

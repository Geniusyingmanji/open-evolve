"""Simple policy-based model router."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class ModelRoute:
    model: str
    reason: str


class ModelRouter:
    def __init__(self, routes: Dict[str, str], default_model: str) -> None:
        self.routes = dict(routes)
        self.default_model = default_model

    def route(self, operation: str) -> ModelRoute:
        if operation in self.routes:
            return ModelRoute(model=self.routes[operation], reason="matched operation route")
        return ModelRoute(model=self.default_model, reason="default route")

"""Verifier registry for structured checks."""

from __future__ import annotations

from typing import Callable, Dict

from open_evolve.core.types import Candidate, Task

Verifier = Callable[[Task, Candidate], bool]


class VerifierRegistry:
    def __init__(self) -> None:
        self._verifiers: Dict[str, Verifier] = {}

    def register(self, name: str, verifier: Verifier) -> None:
        self._verifiers[name] = verifier

    def run(self, name: str, task: Task, candidate: Candidate) -> bool:
        if name not in self._verifiers:
            raise KeyError("unknown verifier: %s" % name)
        return bool(self._verifiers[name](task, candidate))

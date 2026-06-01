"""Benchmark adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, List

from open_evolve.core.types import Candidate, CandidateDraft, EvaluationResult, Task


class BenchmarkAdapter(ABC):
    """Uniform interface for open optimization benchmarks."""

    family = "base"

    @abstractmethod
    def load_task(self, task_id: str) -> Task:
        raise NotImplementedError

    def initial_candidates(self, task: Task) -> List[CandidateDraft]:
        return [
            CandidateDraft(
                artifact=dict(task.initial_artifact),
                parent_ids=[],
                operator_id="initial",
                plan="Seed candidate from task.initial_artifact.",
            )
        ]

    @abstractmethod
    def evaluate(self, task: Task, candidate: Candidate) -> EvaluationResult:
        raise NotImplementedError

    def iter_task_ids(self) -> Iterable[str]:
        return []

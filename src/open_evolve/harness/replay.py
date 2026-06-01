"""Replay helpers for stored candidates."""

from __future__ import annotations

from typing import Iterable, List

from open_evolve.benchmarks.base import BenchmarkAdapter
from open_evolve.core.evaluator import EvaluationService
from open_evolve.core.types import Candidate, EvaluationResult, Task


def replay_candidates(adapter: BenchmarkAdapter, task: Task, candidates: Iterable[Candidate]) -> List[EvaluationResult]:
    evaluator = EvaluationService(adapter, cache_enabled=False)
    return [evaluator.evaluate(task, candidate) for candidate in candidates]

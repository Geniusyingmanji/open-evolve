"""A tiny executable benchmark used to validate the framework loop."""

from __future__ import annotations

from typing import Iterable

from open_evolve.benchmarks.base import BenchmarkAdapter
from open_evolve.core.types import Candidate, EvaluationResult, ScoreVector, Task, utc_ts


class ToyNumericBenchmark(BenchmarkAdapter):
    """Optimize a single integer field toward a hidden target."""

    family = "toy_numeric"

    def __init__(self, target: int = 10, lower: int = -100, upper: int = 100) -> None:
        self.target = target
        self.lower = lower
        self.upper = upper

    def iter_task_ids(self) -> Iterable[str]:
        return ["toy_numeric"]

    def load_task(self, task_id: str = "toy_numeric") -> Task:
        return Task(
            id=task_id,
            family=self.family,
            objective="Maximize -abs(x - target) while keeping x within bounds.",
            initial_artifact={"x": 0},
            maximize=True,
            metadata={"target": self.target},
            feasibility={"lower": self.lower, "upper": self.upper},
        )

    def evaluate(self, task: Task, candidate: Candidate) -> EvaluationResult:
        started = utc_ts()
        error = None
        feasible = True
        try:
            x = candidate.artifact["x"]
            if not isinstance(x, int):
                raise TypeError("artifact.x must be an int")
            feasible = self.lower <= x <= self.upper
            objective = -abs(x - self.target)
            distance = abs(x - self.target)
            logs = "x=%s target=%s distance=%s feasible=%s" % (x, self.target, distance, feasible)
        except Exception as exc:  # pragma: no cover - defensive fallback
            x = None
            objective = float("-inf")
            distance = None
            feasible = False
            logs = "invalid artifact: %r" % (candidate.artifact,)
            error = str(exc)
        score = ScoreVector(
            objective=float(objective),
            feasible=feasible,
            metrics={"x": x, "target": self.target, "distance": distance},
            cost={"eval_calls": 1},
        )
        return EvaluationResult(
            candidate_id=candidate.id,
            task_id=task.id,
            score=score,
            logs=logs,
            error=error,
            evaluator_version="toy_numeric_v1",
            started_at=started,
            finished_at=utc_ts(),
        )

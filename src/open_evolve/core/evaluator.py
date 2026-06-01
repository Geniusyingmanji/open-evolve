"""Evaluation service wrapper."""

from __future__ import annotations

from typing import Dict, Optional

from open_evolve.benchmarks.base import BenchmarkAdapter
from open_evolve.core.artifact_store import FileArtifactStore
from open_evolve.core.types import Candidate, CandidateStatus, EvaluationResult, ScoreVector, Task, stable_hash, utc_ts
from open_evolve.core.trace_recorder import TraceRecorder


class EvaluationService:
    """Runs benchmark evaluations with caching and trace recording."""

    def __init__(
        self,
        adapter: BenchmarkAdapter,
        store: Optional[FileArtifactStore] = None,
        run_id: Optional[str] = None,
        trace: Optional[TraceRecorder] = None,
        cache_enabled: bool = True,
    ) -> None:
        self.adapter = adapter
        self.store = store
        self.run_id = run_id
        self.trace = trace
        self.cache_enabled = cache_enabled
        self._cache: Dict[str, EvaluationResult] = {}
        self.evaluations = 0

    def evaluate(self, task: Task, candidate: Candidate) -> EvaluationResult:
        cache_key = "%s:%s" % (task.id, candidate.artifact_hash or stable_hash(candidate.artifact))
        if self.cache_enabled and cache_key in self._cache:
            cached = self._cache[cache_key]
            candidate.status = CandidateStatus.EVALUATED if cached.score.feasible else CandidateStatus.FAILED
            candidate.score = cached.score
            self._record(candidate, cached, cached=True)
            return cached

        started = utc_ts()
        try:
            result = self.adapter.evaluate(task, candidate)
        except Exception as exc:  # pragma: no cover - adapter safety net
            result = EvaluationResult(
                candidate_id=candidate.id,
                task_id=task.id,
                score=ScoreVector(objective=float("-inf"), feasible=False, metrics={}, cost={"eval_calls": 1}),
                logs="adapter exception",
                error=str(exc),
                evaluator_version="%s_exception_wrapper" % self.adapter.family,
                started_at=started,
                finished_at=utc_ts(),
            )

        candidate.score = result.score
        candidate.status = CandidateStatus.EVALUATED if result.score.feasible else CandidateStatus.FAILED
        self.evaluations += 1
        if self.cache_enabled:
            self._cache[cache_key] = result
        if self.store is not None and self.run_id is not None:
            self.store.save_evaluation(self.run_id, result)
        self._record(candidate, result, cached=False)
        return result

    def _record(self, candidate: Candidate, result: EvaluationResult, cached: bool) -> None:
        if self.trace is None:
            return
        self.trace.record(
            kind="feedback",
            message=result.logs,
            candidate_id=candidate.id,
            score=result.score.objective,
            feasible=result.score.feasible,
            cost=result.score.cost,
            feedback_valid=result.error is None,
            feedback_informative=bool(result.logs),
            feedback_retained=not cached,
            metadata={"cached": cached, "error": result.error},
        )

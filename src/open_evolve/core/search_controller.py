"""Search controllers for candidate evolution."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from open_evolve.benchmarks.base import BenchmarkAdapter
from open_evolve.core.archive import CandidateArchive
from open_evolve.core.artifact_store import FileArtifactStore
from open_evolve.core.evaluator import EvaluationService
from open_evolve.core.operators import OperatorLibrary
from open_evolve.core.trace_recorder import TraceRecorder
from open_evolve.core.types import Candidate, RunSummary, Task, best_candidate, new_id


@dataclass
class SearchConfig:
    max_iterations: int = 20
    max_evaluations: int = 100
    parent_pool_size: int = 1
    seed: int = 0
    skip_duplicate_artifacts: bool = True
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class SearchResult:
    run_id: str
    task: Task
    candidates: List[Candidate]
    summary: RunSummary

    @property
    def best(self) -> Optional[Candidate]:
        return best_candidate(self.candidates, maximize=self.task.maximize)


class GreedySearchController:
    """Depth-biased search with optional parent pool breadth."""

    def __init__(
        self,
        adapter: BenchmarkAdapter,
        operators: OperatorLibrary,
        store: FileArtifactStore,
        config: Optional[SearchConfig] = None,
        trace: Optional[TraceRecorder] = None,
    ) -> None:
        self.adapter = adapter
        self.operators = operators
        self.store = store
        self.config = config or SearchConfig()
        self.trace = trace

    def run(self, task: Task, run_id: Optional[str] = None) -> SearchResult:
        run_id = run_id or new_id("run")
        self.store.run_dir(run_id)
        evaluator = EvaluationService(self.adapter, store=self.store, run_id=run_id, trace=self.trace)
        rng = random.Random(self.config.seed)

        candidates: List[Candidate] = []
        seen_hashes: Set[str] = set()

        for draft in self.adapter.initial_candidates(task):
            candidate = Candidate.from_draft(task, draft)
            candidates.append(candidate)
            seen_hashes.add(candidate.artifact_hash)
            self.store.save_candidate(run_id, candidate)
            evaluator.evaluate(task, candidate)
            self.store.save_candidate(run_id, candidate)

        iterations = 0
        while iterations < self.config.max_iterations and evaluator.evaluations < self.config.max_evaluations:
            iterations += 1
            parents = self._select_parents(candidates, task)
            if not parents:
                break
            made_progress = False
            for parent in parents:
                self._record_action(parent.id, "expand", "Expanding parent %s." % parent.id)
                for draft in self.operators.propose(task, parent, rng):
                    if evaluator.evaluations >= self.config.max_evaluations:
                        break
                    candidate = Candidate.from_draft(task, draft)
                    if self.config.skip_duplicate_artifacts and candidate.artifact_hash in seen_hashes:
                        continue
                    seen_hashes.add(candidate.artifact_hash)
                    candidates.append(candidate)
                    self.store.save_candidate(run_id, candidate)
                    evaluator.evaluate(task, candidate)
                    self.store.save_candidate(run_id, candidate)
                    made_progress = True
            if not made_progress:
                break

        best = best_candidate(candidates, maximize=task.maximize)
        summary = RunSummary(
            run_id=run_id,
            task_id=task.id,
            best_candidate_id=best.id if best else None,
            best_score=best.score if best else None,
            evaluations=evaluator.evaluations,
            iterations=iterations,
            archive_size=len(candidates),
            metadata=dict(self.config.metadata),
        )
        self.store.save_summary(summary)
        return SearchResult(run_id=run_id, task=task, candidates=candidates, summary=summary)

    def _select_parents(self, candidates: List[Candidate], task: Task) -> List[Candidate]:
        evaluated = [candidate for candidate in candidates if candidate.score is not None]
        if task.maximize:
            evaluated.sort(key=lambda candidate: (candidate.score.feasible, candidate.score.objective), reverse=True)
        else:
            evaluated.sort(key=lambda candidate: (candidate.score.feasible, -candidate.score.objective), reverse=True)
        return evaluated[: max(1, self.config.parent_pool_size)]

    def _record_action(self, candidate_id: str, tool: str, message: str) -> None:
        if self.trace is None:
            return
        self.trace.record(kind="action", message=message, candidate_id=candidate_id, tool=tool)


class ArchiveSearchController(GreedySearchController):
    """Archive-driven search with diverse parent selection.

    This is a small step toward island/MAP-Elites search. Candidates are placed
    into archive cells keyed by novelty metadata or operator id; each iteration
    expands the best candidate from several cells instead of only the global best.
    """

    def run(self, task: Task, run_id: Optional[str] = None) -> SearchResult:
        run_id = run_id or new_id("run")
        self.store.run_dir(run_id)
        evaluator = EvaluationService(self.adapter, store=self.store, run_id=run_id, trace=self.trace)
        rng = random.Random(self.config.seed)
        archive = CandidateArchive(maximize=task.maximize)

        for draft in self.adapter.initial_candidates(task):
            candidate = Candidate.from_draft(task, draft)
            self.store.save_candidate(run_id, candidate)
            evaluator.evaluate(task, candidate)
            archive.add(candidate)
            self.store.save_candidate(run_id, candidate)

        iterations = 0
        while iterations < self.config.max_iterations and evaluator.evaluations < self.config.max_evaluations:
            iterations += 1
            parents = archive.diverse_parents(max(1, self.config.parent_pool_size))
            if not parents:
                break
            made_progress = False
            for parent in parents:
                self._record_action(parent.id, "archive_expand", "Expanding archive parent %s." % parent.id)
                for draft in self.operators.propose(task, parent, rng):
                    if evaluator.evaluations >= self.config.max_evaluations:
                        break
                    candidate = Candidate.from_draft(task, draft)
                    if self.config.skip_duplicate_artifacts and candidate.artifact_hash in archive.artifact_hashes:
                        continue
                    self.store.save_candidate(run_id, candidate)
                    evaluator.evaluate(task, candidate)
                    archive.add(candidate)
                    self.store.save_candidate(run_id, candidate)
                    made_progress = True
            if not made_progress:
                break

        best = archive.best()
        candidates = list(archive)
        summary = RunSummary(
            run_id=run_id,
            task_id=task.id,
            best_candidate_id=best.id if best else None,
            best_score=best.score if best else None,
            evaluations=evaluator.evaluations,
            iterations=iterations,
            archive_size=len(candidates),
            metadata=dict(self.config.metadata),
        )
        self.store.save_summary(summary)
        return SearchResult(run_id=run_id, task=task, candidates=candidates, summary=summary)

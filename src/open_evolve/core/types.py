"""Shared types for benchmark optimization runs."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional


JsonDict = Dict[str, Any]


def utc_ts() -> float:
    return time.time()


def new_id(prefix: str) -> str:
    return "%s_%s" % (prefix, uuid.uuid4().hex[:12])


def json_dumps(data: Any) -> str:
    return json.dumps(to_jsonable(data), ensure_ascii=False, indent=2, sort_keys=True)


def to_jsonable(data: Any) -> Any:
    if is_dataclass(data):
        return {key: to_jsonable(value) for key, value in asdict(data).items()}
    if isinstance(data, Enum):
        return data.value
    if isinstance(data, dict):
        return {str(key): to_jsonable(value) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        return [to_jsonable(value) for value in data]
    return data


def stable_hash(data: Any) -> str:
    encoded = json.dumps(to_jsonable(data), ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class CandidateStatus(str, Enum):
    DRAFT = "draft"
    EVALUATED = "evaluated"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclass
class Budget:
    max_iterations: int = 20
    max_evaluations: int = 100
    timeout_seconds: Optional[float] = None
    token_budget: Optional[int] = None
    cost_budget: Optional[float] = None


@dataclass
class Task:
    id: str
    family: str
    objective: str
    initial_artifact: JsonDict
    maximize: bool = True
    metadata: JsonDict = field(default_factory=dict)
    feasibility: JsonDict = field(default_factory=dict)
    budget: Budget = field(default_factory=Budget)


@dataclass
class ScoreVector:
    objective: float
    feasible: bool = True
    metrics: JsonDict = field(default_factory=dict)
    cost: JsonDict = field(default_factory=dict)
    risk: JsonDict = field(default_factory=dict)

    def better_than(self, other: Optional["ScoreVector"], maximize: bool = True) -> bool:
        if other is None:
            return True
        if self.feasible != other.feasible:
            return self.feasible and not other.feasible
        if maximize:
            return self.objective > other.objective
        return self.objective < other.objective


@dataclass
class CandidateDraft:
    artifact: JsonDict
    parent_ids: List[str] = field(default_factory=list)
    operator_id: str = "manual"
    plan: str = ""
    metadata: JsonDict = field(default_factory=dict)


@dataclass
class Candidate:
    id: str
    task_id: str
    artifact: JsonDict
    parent_ids: List[str] = field(default_factory=list)
    operator_id: str = "manual"
    plan: str = ""
    metadata: JsonDict = field(default_factory=dict)
    artifact_hash: str = ""
    status: CandidateStatus = CandidateStatus.DRAFT
    score: Optional[ScoreVector] = None
    created_at: float = field(default_factory=utc_ts)

    @classmethod
    def from_draft(cls, task: Task, draft: CandidateDraft) -> "Candidate":
        artifact_hash = stable_hash(draft.artifact)
        return cls(
            id=new_id("cand"),
            task_id=task.id,
            artifact=draft.artifact,
            parent_ids=list(draft.parent_ids),
            operator_id=draft.operator_id,
            plan=draft.plan,
            metadata=dict(draft.metadata),
            artifact_hash=artifact_hash,
        )


@dataclass
class EvaluationResult:
    candidate_id: str
    task_id: str
    score: ScoreVector
    logs: str = ""
    error: Optional[str] = None
    evaluator_version: str = "local"
    started_at: float = field(default_factory=utc_ts)
    finished_at: float = field(default_factory=utc_ts)

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, self.finished_at - self.started_at)


@dataclass
class RunSummary:
    run_id: str
    task_id: str
    best_candidate_id: Optional[str]
    best_score: Optional[ScoreVector]
    evaluations: int
    iterations: int
    archive_size: int
    metadata: JsonDict = field(default_factory=dict)


def best_candidate(candidates: Iterable[Candidate], maximize: bool = True) -> Optional[Candidate]:
    best: Optional[Candidate] = None
    for candidate in candidates:
        if candidate.score is None:
            continue
        if best is None or candidate.score.better_than(best.score, maximize=maximize):
            best = candidate
    return best

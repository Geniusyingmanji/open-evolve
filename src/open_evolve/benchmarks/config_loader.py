"""Load benchmark tasks and candidates from JSON config files."""

from __future__ import annotations

import json
from pathlib import Path

from open_evolve.core.types import Budget, CandidateDraft, Task


def load_task_config(path: Path) -> Task:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    budget_payload = payload.get("budget", {})
    return Task(
        id=payload["id"],
        family=payload.get("family", "local_command"),
        objective=payload.get("objective", ""),
        initial_artifact=dict(payload.get("initial_artifact", {})),
        maximize=bool(payload.get("maximize", True)),
        metadata=dict(payload.get("metadata", {})),
        feasibility=dict(payload.get("feasibility", {})),
        budget=Budget(**budget_payload),
    )


def load_candidate_draft(path: Path) -> CandidateDraft:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return CandidateDraft(
        artifact=dict(payload.get("artifact", payload)),
        parent_ids=list(payload.get("parent_ids", [])),
        operator_id=payload.get("operator_id", "manual"),
        plan=payload.get("plan", ""),
        metadata=dict(payload.get("metadata", {})),
    )

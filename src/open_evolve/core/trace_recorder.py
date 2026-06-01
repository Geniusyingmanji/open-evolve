"""Trace recording for trajectory-level metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from open_evolve.core.types import json_dumps, to_jsonable, utc_ts


@dataclass
class TraceEvent:
    kind: str
    message: str
    timestamp: float = field(default_factory=utc_ts)
    candidate_id: Optional[str] = None
    tool: Optional[str] = None
    score: Optional[float] = None
    feasible: Optional[bool] = None
    cost: Dict[str, Any] = field(default_factory=dict)
    feedback_valid: Optional[bool] = None
    feedback_informative: Optional[bool] = None
    feedback_retained: Optional[bool] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class TraceRecorder:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events: List[TraceEvent] = []

    def record(self, kind: str, message: str, **kwargs: Any) -> TraceEvent:
        event = TraceEvent(kind=kind, message=message, **kwargs)
        self.events.append(event)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json_dumps(event).replace("\n", " ") + "\n")
        return event

    def as_jsonable(self) -> List[Dict[str, Any]]:
        return [to_jsonable(event) for event in self.events]

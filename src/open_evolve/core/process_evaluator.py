"""Lightweight process-quality scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable

from open_evolve.core.trace_recorder import TraceEvent


@dataclass
class ProcessQualityReport:
    score: float
    counts: Dict[str, int] = field(default_factory=dict)
    stage_counts: Dict[str, int] = field(default_factory=dict)
    missing_verification: bool = False
    action_after_feedback: bool = False
    repeated_action_ratio: float = 0.0


def label_stage(event: TraceEvent) -> str:
    explicit = event.metadata.get("stage") if event.metadata else None
    if explicit:
        return str(explicit)
    if event.kind == "feedback":
        return "verification"
    if event.kind == "action":
        tool = (event.tool or "").lower()
        if "expand" in tool or "route" in tool:
            return "orchestration"
        if "edit" in tool or "append" in tool or "replace" in tool or "write" in tool:
            return "implementation"
        if "search" in tool or "read" in tool or "inspect" in tool:
            return "exploration"
    return "unknown"


def evaluate_process_quality(events: Iterable[TraceEvent]) -> ProcessQualityReport:
    counts: Dict[str, int] = {}
    stage_counts: Dict[str, int] = {}
    action_tools = []
    saw_feedback = False
    action_after_feedback = False
    for event in events:
        counts[event.kind] = counts.get(event.kind, 0) + 1
        stage = label_stage(event)
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        if event.kind == "feedback":
            saw_feedback = True
        if event.kind == "action":
            action_tools.append(event.tool or "action")
            if saw_feedback:
                action_after_feedback = True

    repeated = 0
    for previous, current in zip(action_tools, action_tools[1:]):
        if previous == current:
            repeated += 1
    repeated_ratio = float(repeated) / float(max(1, len(action_tools) - 1))
    missing_verification = counts.get("feedback", 0) == 0
    score = 1.0
    if missing_verification:
        score -= 0.4
    if not action_after_feedback and counts.get("action", 0) > 1:
        score -= 0.2
    score -= min(0.3, repeated_ratio * 0.3)
    return ProcessQualityReport(
        score=max(0.0, score),
        counts=counts,
        stage_counts=stage_counts,
        missing_verification=missing_verification,
        action_after_feedback=action_after_feedback,
        repeated_action_ratio=repeated_ratio,
    )

"""Effective Feedback Compute metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from open_evolve.core.trace_recorder import TraceEvent


@dataclass
class FeedbackComputeReport:
    feedback_events: int
    effective_feedback_events: int
    invalid_feedback_events: int
    redundant_feedback_events: int

    @property
    def effective_feedback_ratio(self) -> float:
        if self.feedback_events == 0:
            return 0.0
        return float(self.effective_feedback_events) / float(self.feedback_events)


def estimate_effective_feedback_compute(events: Iterable[TraceEvent]) -> FeedbackComputeReport:
    feedback_events = 0
    effective = 0
    invalid = 0
    redundant = 0
    seen_messages = set()
    for event in events:
        if event.kind != "feedback":
            continue
        feedback_events += 1
        if event.feedback_valid is False:
            invalid += 1
            continue
        key = event.message.strip()
        if key in seen_messages:
            redundant += 1
            continue
        seen_messages.add(key)
        if event.feedback_informative and event.feedback_retained:
            effective += 1
    return FeedbackComputeReport(
        feedback_events=feedback_events,
        effective_feedback_events=effective,
        invalid_feedback_events=invalid,
        redundant_feedback_events=redundant,
    )

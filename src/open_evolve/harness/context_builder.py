"""Context construction utilities."""

from __future__ import annotations

from typing import Iterable, List

from open_evolve.core.trace_recorder import TraceEvent
from open_evolve.harness.harness_spec import HarnessSpec


def build_context(spec: HarnessSpec, events: Iterable[TraceEvent]) -> List[TraceEvent]:
    max_events = int(spec.context_policy.get("max_history_events", 200))
    items = list(events)
    if max_events <= 0:
        return []
    return items[-max_events:]

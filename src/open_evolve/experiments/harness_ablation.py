"""Harness ablation utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List

from open_evolve.core.types import RunSummary
from open_evolve.harness.harness_spec import HarnessSpec


@dataclass
class HarnessAblationResult:
    harness_name: str
    harness_version: str
    summary: RunSummary
    metadata: Dict[str, object] = field(default_factory=dict)


class HarnessAblationRunner:
    def __init__(self, specs: Iterable[HarnessSpec], run_fn: Callable[[HarnessSpec], RunSummary]) -> None:
        self.specs = list(specs)
        self.run_fn = run_fn

    def run(self) -> List[HarnessAblationResult]:
        results: List[HarnessAblationResult] = []
        for spec in self.specs:
            spec.validate()
            summary = self.run_fn(spec)
            results.append(
                HarnessAblationResult(
                    harness_name=spec.name,
                    harness_version=spec.version,
                    summary=summary,
                    metadata={"task_family": spec.task_family},
                )
            )
        return results

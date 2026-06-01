"""Experiment report writers."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from open_evolve.core.types import json_dumps
from open_evolve.experiments.harness_ablation import HarnessAblationResult


def write_ablation_json(results: Iterable[HarnessAblationResult], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps(list(results)) + "\n", encoding="utf-8")
    return path


def write_ablation_markdown(results: Iterable[HarnessAblationResult], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: List[str] = [
        "# Harness Ablation Report",
        "",
        "| Harness | Version | Task | Best score | Evaluations | Archive size |",
        "|---------|---------|------|------------|-------------|--------------|",
    ]
    for result in results:
        summary = result.summary
        best = summary.best_score.objective if summary.best_score else ""
        rows.append(
            "| %s | %s | %s | %s | %s | %s |"
            % (
                result.harness_name,
                result.harness_version,
                summary.task_id,
                best,
                summary.evaluations,
                summary.archive_size,
            )
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path

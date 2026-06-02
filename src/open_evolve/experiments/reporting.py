"""Experiment report writers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, List, Sequence

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


def collect_run_summary_rows(paths: Sequence[Path]) -> List[dict[str, Any]]:
    summary_paths: List[Path] = []
    for path in paths:
        path = Path(path)
        if path.is_dir():
            summary_paths.extend(sorted(path.rglob("summary.json")))
        elif path.is_file():
            summary_paths.append(path)

    rows: List[dict[str, Any]] = []
    seen: set[Path] = set()
    for path in summary_paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            rows.append({"path": str(path), "error": str(exc)})
            continue
        best_score = payload.get("best_score") or {}
        metrics = best_score.get("metrics") or {}
        rows.append(
            {
                "run_id": payload.get("run_id"),
                "task_id": payload.get("task_id"),
                "evaluations": payload.get("evaluations"),
                "iterations": payload.get("iterations"),
                "archive_size": payload.get("archive_size"),
                "best_objective": best_score.get("objective"),
                "feasible": best_score.get("feasible"),
                "combined_score": metrics.get("combined_score"),
                "valid": metrics.get("valid"),
                "runtime_s": metrics.get("runtime_s"),
                "path": str(path),
            }
        )
    rows.sort(key=lambda row: str(row.get("run_id") or row.get("path") or ""))
    return rows


def write_run_summary_json(rows: Sequence[dict[str, Any]], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps(list(rows)) + "\n", encoding="utf-8")
    return path


def write_run_summary_markdown(rows: Sequence[dict[str, Any]], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Run Summary",
        "",
        "| Run | Task | Evaluations | Best objective | Combined | Valid |",
        "|-----|------|-------------|----------------|----------|-------|",
    ]
    for row in rows:
        if row.get("error"):
            lines.append("| %s | ERROR |  |  | %s |  |" % (row.get("path", ""), row.get("error", "")))
            continue
        lines.append(
            "| %s | %s | %s | %s | %s | %s |"
            % (
                row.get("run_id", ""),
                row.get("task_id", ""),
                row.get("evaluations", ""),
                row.get("best_objective", ""),
                row.get("combined_score", ""),
                row.get("valid", ""),
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path

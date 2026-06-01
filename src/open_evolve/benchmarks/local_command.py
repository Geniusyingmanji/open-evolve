"""Local command benchmark adapter.

This adapter is the bridge from JSON candidates to executable benchmark tasks:
static task files and candidate files are written into a temporary workspace,
an evaluation command is executed, and a JSON score file is parsed.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Iterable

from open_evolve.benchmarks.base import BenchmarkAdapter
from open_evolve.core.types import Candidate, EvaluationResult, ScoreVector, Task, utc_ts


class LocalCommandBenchmarkAdapter(BenchmarkAdapter):
    family = "local_command"

    def __init__(self, tasks: Dict[str, Task]) -> None:
        self.tasks = dict(tasks)

    def iter_task_ids(self) -> Iterable[str]:
        return sorted(self.tasks.keys())

    def load_task(self, task_id: str) -> Task:
        return self.tasks[task_id]

    def evaluate(self, task: Task, candidate: Candidate) -> EvaluationResult:
        started = utc_ts()
        score_file = task.metadata.get("score_file", "score.json")
        timeout = task.metadata.get("timeout_seconds", 60)
        command = task.metadata.get("eval_command")
        if not isinstance(command, list) or not command:
            return self._failed(task, candidate, started, "task.metadata.eval_command must be a non-empty list")

        with tempfile.TemporaryDirectory(prefix="open_evolve_eval_") as tmp:
            workdir = Path(tmp)
            try:
                self._write_files(workdir, task.metadata.get("static_files", {}))
                self._write_files(workdir, candidate.artifact.get("files", {}))
                completed = subprocess.run(
                    command,
                    cwd=str(workdir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=float(timeout),
                    check=False,
                )
                logs = (completed.stdout or "") + (completed.stderr or "")
                if completed.returncode != 0:
                    return self._failed(task, candidate, started, "eval command failed", logs=logs)
                score_path = workdir / str(score_file)
                if not score_path.exists():
                    return self._failed(task, candidate, started, "score file not found: %s" % score_file, logs=logs)
                payload = json.loads(score_path.read_text(encoding="utf-8"))
                score = ScoreVector(
                    objective=float(payload["objective"]),
                    feasible=bool(payload.get("feasible", True)),
                    metrics=dict(payload.get("metrics", {})),
                    cost=dict(payload.get("cost", {})),
                    risk=dict(payload.get("risk", {})),
                )
                return EvaluationResult(
                    candidate_id=candidate.id,
                    task_id=task.id,
                    score=score,
                    logs=logs,
                    evaluator_version="local_command_v1",
                    started_at=started,
                    finished_at=utc_ts(),
                )
            except subprocess.TimeoutExpired as exc:
                return self._failed(task, candidate, started, "eval command timed out", logs=str(exc))
            except Exception as exc:
                return self._failed(task, candidate, started, str(exc))

    def _failed(self, task: Task, candidate: Candidate, started: float, error: str, logs: str = "") -> EvaluationResult:
        return EvaluationResult(
            candidate_id=candidate.id,
            task_id=task.id,
            score=ScoreVector(objective=float("-inf"), feasible=False, metrics={}, cost={"eval_calls": 1}),
            logs=logs,
            error=error,
            evaluator_version="local_command_v1",
            started_at=started,
            finished_at=utc_ts(),
        )

    def _write_files(self, root: Path, files: Dict[str, str]) -> None:
        if not isinstance(files, dict):
            raise TypeError("files must be a mapping of relative path to content")
        for rel_path, content in files.items():
            target = root / rel_path
            resolved = target.resolve()
            if root.resolve() not in resolved.parents and resolved != root.resolve():
                raise ValueError("unsafe file path: %s" % rel_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(content), encoding="utf-8")

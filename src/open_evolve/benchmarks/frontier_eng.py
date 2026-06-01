"""Adapter for EinsiaLab Frontier-Engineering unified tasks."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from open_evolve.benchmarks._subprocess_json import extract_prefixed_json, tail_text
from open_evolve.benchmarks.base import BenchmarkAdapter
from open_evolve.core.types import Candidate, CandidateDraft, EvaluationResult, ScoreVector, Task, utc_ts


RESULT_PREFIX = "OPEN_EVOLVE_FRONTIER_RESULT "


def default_frontier_repo_root() -> Path:
    return Path(os.environ.get("OPEN_EVOLVE_FRONTIER_ROOT", "/data/zyf/benchmarks/Frontier-Engineering")).expanduser()


class FrontierEngineeringAdapter(BenchmarkAdapter):
    """Evaluate Frontier-Engineering candidates through the official unified evaluator."""

    family = "frontier_engineering"

    def __init__(
        self,
        repo_root: Optional[Path] = None,
        benchmark_id: str = "WirelessChannelSimulation/HighReliableSimulation",
        timeout_seconds: float = 600.0,
        evaluator_timeout_seconds: float = 300.0,
        runtime_env_name: str = "frontier-eval-driver",
        runtime_python_path: Optional[str] = None,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root is not None else default_frontier_repo_root()
        self.benchmark_id = benchmark_id
        self.timeout_seconds = float(timeout_seconds)
        self.evaluator_timeout_seconds = float(evaluator_timeout_seconds)
        self.runtime_env_name = runtime_env_name
        self.runtime_python_path = runtime_python_path

    @property
    def python_executable(self) -> Path:
        venv_python = self.repo_root / ".venvs" / "frontier-eval-driver" / "bin" / "python"
        return venv_python if venv_python.exists() else Path("python3")

    def load_task(self, task_id: str) -> Task:
        benchmark_id = task_id or self.benchmark_id
        metadata = self._load_spec_metadata(benchmark_id)
        candidate_rel = str(metadata.get("candidate_destination_rel") or metadata.get("initial_program_rel") or "solution.py")
        initial_program_path = Path(str(metadata.get("initial_program_path") or ""))
        initial_code = initial_program_path.read_text(encoding="utf-8", errors="replace") if initial_program_path.is_file() else ""
        metadata["agent_context"] = self._build_agent_context(metadata)
        return Task(
            id=benchmark_id,
            family=self.family,
            objective="Maximize Frontier-Engineering `combined_score` while keeping `valid=1.0`.",
            initial_artifact={"files": {candidate_rel: initial_code}},
            maximize=True,
            metadata=metadata,
            feasibility={"valid_metric": "valid", "valid_threshold": 1.0},
        )

    def initial_candidates(self, task: Task) -> List[CandidateDraft]:
        return [
            CandidateDraft(
                artifact=dict(task.initial_artifact),
                parent_ids=[],
                operator_id="frontier_initial",
                plan="Seed Frontier-Engineering candidate from benchmark initial_program.",
                metadata={"benchmark_id": task.id},
            )
        ]

    def iter_task_ids(self) -> Iterable[str]:
        return [self.benchmark_id]

    def evaluate(self, task: Task, candidate: Candidate) -> EvaluationResult:
        started = utc_ts()
        candidate_rel, code = self._candidate_program(task, candidate)
        with tempfile.TemporaryDirectory(prefix="open_evolve_frontier_") as tmp:
            candidate_path = Path(tmp) / Path(candidate_rel).name
            candidate_path.write_text(code, encoding="utf-8")
            proc = subprocess.run(
                [
                    str(self.python_executable),
                    "-c",
                    self._eval_script(),
                    str(self.repo_root),
                    task.id,
                    str(candidate_path),
                    self.runtime_env_name,
                    self.runtime_python_path or "",
                ],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=self._env(),
            )

        parsed = extract_prefixed_json(proc.stdout, RESULT_PREFIX)
        if parsed is None:
            return EvaluationResult(
                candidate_id=candidate.id,
                task_id=task.id,
                score=ScoreVector(
                    objective=float("-inf"),
                    feasible=False,
                    metrics={"returncode": proc.returncode},
                    cost={"eval_calls": 1},
                ),
                logs=tail_text(proc.stdout + "\n" + proc.stderr),
                error="Frontier-Engineering subprocess did not emit result JSON.",
                evaluator_version="frontier_engineering_subprocess",
                started_at=started,
                finished_at=utc_ts(),
            )

        metrics = dict(parsed.get("metrics") or {})
        artifacts = dict(parsed.get("artifacts") or {})
        objective = float(metrics.get("combined_score", float("-inf")))
        valid = float(metrics.get("valid", 0.0) or 0.0)
        feasible = bool(valid > 0.0 and proc.returncode == 0 and objective > -1e17)
        error = None if feasible else str(artifacts.get("error_message") or artifacts.get("failure_summary") or "invalid")
        logs = json.dumps(
            {
                "benchmark_id": task.id,
                "combined_score": metrics.get("combined_score"),
                "valid": metrics.get("valid"),
                "runtime_s": metrics.get("runtime_s"),
                "benchmark_returncode": metrics.get("benchmark_returncode"),
                "error": error,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        score_metrics: Dict[str, Any] = dict(metrics)
        interesting_artifacts = {
            key: artifacts[key]
            for key in ("error_message", "failure_summary", "benchmark_stdout", "benchmark_stderr", "constraints")
            if key in artifacts
        }
        if interesting_artifacts:
            score_metrics["artifacts"] = interesting_artifacts
        return EvaluationResult(
            candidate_id=candidate.id,
            task_id=task.id,
            score=ScoreVector(
                objective=objective,
                feasible=feasible,
                metrics=score_metrics,
                cost={"eval_calls": 1, "runtime_s": metrics.get("runtime_s")},
            ),
            logs=logs,
            error=error,
            evaluator_version="frontier_engineering_unified",
            started_at=started,
            finished_at=utc_ts(),
        )

    def _candidate_program(self, task: Task, candidate: Candidate) -> tuple[str, str]:
        files = candidate.artifact.get("files")
        preferred = str(task.metadata.get("candidate_destination_rel") or task.metadata.get("initial_program_rel") or "")
        if isinstance(files, dict):
            if preferred and isinstance(files.get(preferred), str):
                return preferred, files[preferred]
            if len(files) == 1:
                rel, content = next(iter(files.items()))
                return str(rel), str(content)
        code = candidate.artifact.get("code")
        if isinstance(code, str):
            return preferred or "solution.py", code
        raise ValueError("Frontier candidate artifact must contain `files` or `code`.")

    def _load_spec_metadata(self, benchmark_id: str) -> Dict[str, Any]:
        proc = subprocess.run(
            [
                str(self.python_executable),
                "-c",
                self._spec_script(),
                str(self.repo_root),
                benchmark_id,
                self.runtime_env_name,
                self.runtime_python_path or "",
            ],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
            timeout=min(self.timeout_seconds, 180.0),
            env=self._env(),
        )
        parsed = extract_prefixed_json(proc.stdout, RESULT_PREFIX)
        if parsed is None:
            return {
                "repo_root": str(self.repo_root),
                "benchmark_id": benchmark_id,
                "metadata_error": tail_text(proc.stdout + "\n" + proc.stderr, limit=2000),
            }
        return dict(parsed)

    def _build_agent_context(self, metadata: Dict[str, Any]) -> str:
        benchmark_dir = Path(str(metadata.get("benchmark_dir") or ""))
        agent_files = metadata.get("agent_files") or []
        chunks: List[str] = []
        if metadata.get("constraints_text"):
            chunks.append("## constraints\n%s" % str(metadata["constraints_text"])[:20000])
        if isinstance(agent_files, list):
            for rel in agent_files:
                src = (benchmark_dir / str(rel)).resolve()
                try:
                    src.relative_to(benchmark_dir.resolve())
                except Exception:
                    continue
                if not src.is_file():
                    continue
                text = src.read_text(encoding="utf-8", errors="replace")
                chunks.append("## %s\n%s" % (rel, text[:40000]))
                if sum(len(chunk) for chunk in chunks) > 120000:
                    break
        return "\n\n".join(chunks)[:160000]

    def _env(self) -> Dict[str, str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.repo_root) + os.pathsep + env.get("PYTHONPATH", "")
        env.setdefault("FRONTIER_ENGINEERING_ROOT", str(self.repo_root))
        env["FRONTIER_EVAL_EVALUATOR_TIMEOUT_S"] = str(self.evaluator_timeout_seconds)
        return env

    @staticmethod
    def _task_cfg_literal() -> str:
        return """{
    "benchmark": benchmark_id,
    "runtime": {
        "env_name": runtime_env_name,
        "python_path": runtime_python_path or None,
    },
}"""

    @classmethod
    def _spec_script(cls) -> str:
        return r"""
import json
import sys
from pathlib import Path
from omegaconf import OmegaConf

repo_root = Path(sys.argv[1]).resolve()
benchmark_id = sys.argv[2]
runtime_env_name = sys.argv[3]
runtime_python_path = sys.argv[4]
sys.path.insert(0, str(repo_root))
from frontier_eval.tasks.unified.spec import load_unified_task_spec

cfg = OmegaConf.create(""" + cls._task_cfg_literal() + r""")
spec = load_unified_task_spec(task_cfg=cfg, repo_root=repo_root)
payload = {
    "repo_root": str(spec.repo_root),
    "benchmark_id": spec.benchmark_id,
    "benchmark_dir": str(spec.benchmark_dir),
    "initial_program_rel": spec.initial_program_rel,
    "candidate_destination_rel": spec.candidate_destination_rel,
    "initial_program_path": str(spec.initial_program_path),
    "eval_command": spec.eval_command,
    "eval_cwd_rel": spec.eval_cwd_rel,
    "agent_files": list(spec.agent_files),
    "copy_files": list(spec.copy_files),
    "readonly_files": list(spec.readonly_files),
    "artifact_files": list(spec.artifact_files),
    "constraints_text": spec.constraints_text,
    "metrics_json_rel": spec.metrics_json_rel,
    "artifacts_json_rel": spec.artifacts_json_rel,
    "runtime_env_name": spec.runtime_env_name,
    "runtime_python_path": spec.runtime_python_path,
}
print("OPEN_EVOLVE_FRONTIER_RESULT " + json.dumps(payload, ensure_ascii=False, default=str))
"""

    @classmethod
    def _eval_script(cls) -> str:
        return r"""
import json
import sys
from pathlib import Path
from omegaconf import OmegaConf

repo_root = Path(sys.argv[1]).resolve()
benchmark_id = sys.argv[2]
candidate_path = Path(sys.argv[3]).resolve()
runtime_env_name = sys.argv[4]
runtime_python_path = sys.argv[5]
sys.path.insert(0, str(repo_root))
from frontier_eval.tasks.unified.spec import load_unified_task_spec
from frontier_eval.tasks.unified.evaluator.python import evaluate

cfg = OmegaConf.create(""" + cls._task_cfg_literal() + r""")
spec = load_unified_task_spec(task_cfg=cfg, repo_root=repo_root)
result = evaluate(str(candidate_path), spec=spec)
if hasattr(result, "metrics") and hasattr(result, "artifacts"):
    payload = {"metrics": dict(result.metrics), "artifacts": dict(result.artifacts)}
else:
    payload = {"metrics": dict(result), "artifacts": {}}
print("OPEN_EVOLVE_FRONTIER_RESULT " + json.dumps(payload, ensure_ascii=False, default=str))
"""

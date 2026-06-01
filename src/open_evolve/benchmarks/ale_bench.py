"""Adapter for SakanaAI ALE-Bench."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from open_evolve.benchmarks._subprocess_json import extract_prefixed_json, tail_text
from open_evolve.benchmarks.base import BenchmarkAdapter
from open_evolve.core.types import Candidate, CandidateDraft, EvaluationResult, ScoreVector, Task, utc_ts


RESULT_PREFIX = "OPEN_EVOLVE_ALE_RESULT "
INFO_PREFIX = "OPEN_EVOLVE_ALE_INFO "


def default_ale_repo_root() -> Path:
    return Path(os.environ.get("OPEN_EVOLVE_ALE_ROOT", "/data/zyf/benchmarks/ALE-Bench")).expanduser()


def default_ahc039_cpp20() -> str:
    return textwrap.dedent(
        r"""
        #include <bits/stdc++.h>
        using namespace std;
        int main(){
            string discard;
            while (cin >> discard) {}
            cout << 6 << '\n';
            cout << "15000 25000\n";
            cout << "80000 25000\n";
            cout << "80000 60000\n";
            cout << "65000 60000\n";
            cout << "65000 35000\n";
            cout << "15000 35000\n";
        }
        """
    ).strip() + "\n"


class ALEBenchAdapter(BenchmarkAdapter):
    """Run ALE-Bench public or private evaluation through the official toolkit.

    Search should use ``eval_split="public"``. Use ``eval_split="private"`` for
    one final held-out estimate after candidate selection.
    """

    family = "ale_bench"

    def __init__(
        self,
        repo_root: Optional[Path] = None,
        problem_id: str = "ahc039",
        lite_version: bool = True,
        code_language: str = "cpp20",
        judge_version: str = "202301",
        eval_split: str = "public",
        num_workers: int = 1,
        timeout_seconds: float = 600.0,
    ) -> None:
        if eval_split not in {"public", "private"}:
            raise ValueError("eval_split must be 'public' or 'private'")
        self.repo_root = Path(repo_root) if repo_root is not None else default_ale_repo_root()
        self.problem_id = problem_id
        self.lite_version = bool(lite_version)
        self.code_language = code_language
        self.judge_version = judge_version
        self.eval_split = eval_split
        self.num_workers = int(num_workers)
        self.timeout_seconds = float(timeout_seconds)

    @property
    def python_executable(self) -> Path:
        venv_python = self.repo_root / ".venv" / "bin" / "python"
        return venv_python if venv_python.exists() else Path("python3")

    def load_task(self, task_id: str) -> Task:
        problem_id = task_id or self.problem_id
        metadata: Dict[str, Any] = {
            "repo_root": str(self.repo_root),
            "problem_id": problem_id,
            "lite_version": self.lite_version,
            "code_language": self.code_language,
            "judge_version": self.judge_version,
            "eval_split": self.eval_split,
        }
        metadata.update(self._load_problem_metadata(problem_id))
        initial_code = default_ahc039_cpp20() if problem_id == "ahc039" else ""
        return Task(
            id=problem_id,
            family=self.family,
            objective=(
                "Maximize ALE-Bench public score during search. Use private evaluation "
                "only once for final held-out reporting."
            ),
            initial_artifact={
                "code": initial_code,
                "code_language": self.code_language,
                "judge_version": self.judge_version,
            },
            maximize=True,
            metadata=metadata,
            feasibility={"required_overall_judge_result": "ACCEPTED"},
        )

    def initial_candidates(self, task: Task) -> List[CandidateDraft]:
        return [
            CandidateDraft(
                artifact=dict(task.initial_artifact),
                parent_ids=[],
                operator_id="ale_initial",
                plan="Seed ALE candidate from a known valid baseline.",
                metadata={"problem_id": task.id},
            )
        ]

    def iter_task_ids(self) -> Iterable[str]:
        return [self.problem_id]

    def evaluate(self, task: Task, candidate: Candidate) -> EvaluationResult:
        started = utc_ts()
        code = self._candidate_code(candidate)
        language = str(candidate.artifact.get("code_language") or self.code_language)
        judge = str(candidate.artifact.get("judge_version") or self.judge_version)
        eval_split = str(candidate.artifact.get("eval_split") or task.metadata.get("eval_split") or self.eval_split)
        if eval_split not in {"public", "private"}:
            eval_split = self.eval_split

        with tempfile.TemporaryDirectory(prefix="open_evolve_ale_") as tmp:
            code_path = Path(tmp) / "Main.txt"
            code_path.write_text(code, encoding="utf-8")
            proc = subprocess.run(
                [
                    str(self.python_executable),
                    "-c",
                    self._eval_script(),
                    str(code_path),
                    task.id,
                    "1" if bool(task.metadata.get("lite_version", self.lite_version)) else "0",
                    language,
                    judge,
                    eval_split,
                    str(self.num_workers),
                ],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                env=self._env(),
            )

        parsed = extract_prefixed_json(proc.stdout, RESULT_PREFIX)
        if parsed is None:
            finished = utc_ts()
            logs = tail_text(proc.stdout + "\n" + proc.stderr)
            return EvaluationResult(
                candidate_id=candidate.id,
                task_id=task.id,
                score=ScoreVector(
                    objective=float("-inf"),
                    feasible=False,
                    metrics={"returncode": proc.returncode},
                    cost={"eval_calls": 1},
                ),
                logs=logs,
                error="ALE-Bench subprocess did not emit result JSON.",
                evaluator_version="ale_bench_subprocess",
                started_at=started,
                finished_at=finished,
            )

        metrics = dict(parsed.get("metrics") or {})
        objective = float(metrics.get("objective", metrics.get("absolute_score", 0.0)))
        feasible = bool(metrics.get("accepted", False)) and proc.returncode == 0
        error = None if feasible else str(parsed.get("error") or metrics.get("overall_judge_result") or "not accepted")
        logs = json.dumps(
            {
                "split": eval_split,
                "problem_id": task.id,
                "overall_judge_result": metrics.get("overall_judge_result"),
                "absolute_score": metrics.get("absolute_score"),
                "rank": metrics.get("rank"),
                "performance": metrics.get("performance"),
                "case_count": metrics.get("case_count"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return EvaluationResult(
            candidate_id=candidate.id,
            task_id=task.id,
            score=ScoreVector(
                objective=objective,
                feasible=feasible,
                metrics=metrics,
                cost={"eval_calls": 1, "split": eval_split},
            ),
            logs=logs,
            error=error,
            evaluator_version="ale_bench_%s" % eval_split,
            started_at=started,
            finished_at=utc_ts(),
        )

    def _candidate_code(self, candidate: Candidate) -> str:
        code = candidate.artifact.get("code")
        if isinstance(code, str) and code.strip():
            return code
        files = candidate.artifact.get("files")
        if isinstance(files, dict):
            for key in ("Main.cpp", "main.cpp", "solution.cpp"):
                value = files.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            if len(files) == 1:
                value = next(iter(files.values()))
                if isinstance(value, str):
                    return value
        raise ValueError("ALE candidate artifact must contain `code` or one source file.")

    def _load_problem_metadata(self, problem_id: str) -> Dict[str, Any]:
        if not self.repo_root.exists():
            return {"metadata_error": "ALE-Bench repo not found: %s" % self.repo_root}
        try:
            proc = subprocess.run(
                [
                    str(self.python_executable),
                    "-c",
                    self._info_script(),
                    problem_id,
                    "1" if self.lite_version else "0",
                    str(self.num_workers),
                ],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=min(self.timeout_seconds, 180.0),
                env=self._env(),
            )
        except Exception as exc:
            return {"metadata_error": str(exc)}
        parsed = extract_prefixed_json(proc.stdout, INFO_PREFIX)
        if parsed is None:
            return {"metadata_error": tail_text(proc.stdout + "\n" + proc.stderr, limit=2000)}
        return parsed

    def _env(self) -> Dict[str, str]:
        env = os.environ.copy()
        src_path = str(self.repo_root / "src")
        env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
        return env

    @staticmethod
    def _info_script() -> str:
        return r"""
import json
import sys
import ale_bench

problem_id = sys.argv[1]
lite = sys.argv[2] == "1"
workers = int(sys.argv[3])
session = ale_bench.start(problem_id=problem_id, lite_version=lite, num_workers=workers)
try:
    problem = session.problem
    constraints = getattr(problem, "constraints", None)
    constraints_payload = constraints.model_dump() if hasattr(constraints, "model_dump") else str(constraints)
    metadata = getattr(problem, "metadata", None)
    metadata_payload = metadata.model_dump() if hasattr(metadata, "model_dump") else {}
    payload = {
        "statement": str(getattr(problem, "statement", ""))[:120000],
        "constraints": constraints_payload,
        "problem_metadata": metadata_payload,
    }
    print("OPEN_EVOLVE_ALE_INFO " + json.dumps(payload, ensure_ascii=False, default=str))
finally:
    session.close()
"""

    @staticmethod
    def _eval_script() -> str:
        return r"""
import json
import sys
import traceback
import ale_bench

code_path, problem_id, lite_raw, language, judge, split, workers_raw = sys.argv[1:8]
code = open(code_path, encoding="utf-8").read()
session = None
try:
    session = ale_bench.start(
        problem_id=problem_id,
        lite_version=(lite_raw == "1"),
        num_workers=int(workers_raw),
    )
    if split == "private":
        result, rank, performance = session.private_eval(code, code_language=language, judge_version=judge)
    else:
        result = session.public_eval(code, code_language=language, judge_version=judge)
        rank, performance = None, None
    judge_result = str(result.overall_judge_result.value if hasattr(result.overall_judge_result, "value") else result.overall_judge_result)
    case_counts = {}
    for case in result.case_results:
        jr = str(case.judge_result.value if hasattr(case.judge_result, "value") else case.judge_result)
        case_counts[jr] = case_counts.get(jr, 0) + 1
    metrics = {
        "objective": float(result.overall_absolute_score),
        "absolute_score": float(result.overall_absolute_score),
        "relative_score": result.overall_relative_score,
        "overall_judge_result": judge_result,
        "accepted": judge_result == "ACCEPTED",
        "case_count": len(result.case_results),
        "case_judge_counts": case_counts,
        "rank": rank,
        "performance": performance,
    }
    print("OPEN_EVOLVE_ALE_RESULT " + json.dumps({"metrics": metrics}, ensure_ascii=False, default=str))
except Exception as exc:
    print("OPEN_EVOLVE_ALE_RESULT " + json.dumps({
        "metrics": {
            "objective": float("-inf"),
            "absolute_score": 0.0,
            "accepted": False,
            "overall_judge_result": "ERROR",
        },
        "error": str(exc),
        "traceback": traceback.format_exc(),
    }, ensure_ascii=False, default=str))
finally:
    if session is not None:
        session.close()
"""

"""Command-line entry points."""

from __future__ import annotations

import argparse
import fnmatch
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from open_evolve.benchmarks.ale_bench import ALEBenchAdapter
from open_evolve.benchmarks.frontier_eng import FrontierEngineeringAdapter, discover_frontier_task_ids
from open_evolve.benchmarks.toy_numeric import ToyNumericBenchmark
from open_evolve.benchmarks.config_loader import load_candidate_draft, load_task_config
from open_evolve.benchmarks.local_command import LocalCommandBenchmarkAdapter
from open_evolve.core.artifact_store import FileArtifactStore
from open_evolve.core.evaluator import EvaluationService
from open_evolve.core.feedback_compute import estimate_effective_feedback_compute
from open_evolve.core.llm_operators import AzureCodeEditOperator
from open_evolve.core.operators import (
    JsonFieldStepOperator,
    OperatorLibrary,
    RandomJsonFieldOperator,
    RegexFloatJitterOperator,
    RegexNumberJitterOperator,
)
from open_evolve.core.process_evaluator import evaluate_process_quality
from open_evolve.core.search_controller import ArchiveSearchController, GreedySearchController, SearchConfig
from open_evolve.core.trace_recorder import TraceRecorder
from open_evolve.core.types import json_dumps
from open_evolve.core.types import Candidate, CandidateDraft
from open_evolve.experiments.reporting import (
    collect_run_summary_rows,
    write_run_summary_json,
    write_run_summary_markdown,
)
from open_evolve.harness.harness_spec import HarnessSpec
from open_evolve.harness.registry import HarnessRegistry
from open_evolve.models.azure_openai import AzureOpenAIResponsesClient


def run_toy(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace)
    store = FileArtifactStore(workspace / "runs")
    trace = TraceRecorder(workspace / "traces" / "toy_trace.jsonl")
    benchmark = ToyNumericBenchmark(target=args.target)
    task = benchmark.load_task("toy_numeric")
    harness = HarnessSpec.default(task.family)
    HarnessRegistry(workspace / "harness_registry").register(harness, status="candidate")

    operators = OperatorLibrary(
        [
            JsonFieldStepOperator("x", steps=[-5, -2, -1, 1, 2, 5]),
            RandomJsonFieldOperator("x", lower=-20, upper=20, samples=2),
        ]
    )
    controller_cls = ArchiveSearchController if args.search == "archive" else GreedySearchController
    controller = controller_cls(
        adapter=benchmark,
        operators=operators,
        store=store,
        config=SearchConfig(max_iterations=args.iterations, max_evaluations=args.max_evaluations, seed=args.seed),
        trace=trace,
    )
    result = controller.run(task, run_id=args.run_id)
    efc = estimate_effective_feedback_compute(trace.events)
    process = evaluate_process_quality(trace.events)
    payload = {
        "summary": result.summary,
        "best_artifact": result.best.artifact if result.best else None,
        "effective_feedback_ratio": efc.effective_feedback_ratio,
        "process_quality": process.score,
        "workspace": str(workspace),
    }
    print(json_dumps(payload))
    return 0


def eval_local(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace)
    store = FileArtifactStore(workspace / "runs")
    trace = TraceRecorder(workspace / "traces" / "eval_local_trace.jsonl")
    task = load_task_config(Path(args.task_config))
    draft = load_candidate_draft(Path(args.candidate_json)) if args.candidate_json else None
    if draft is None:
        from open_evolve.core.types import CandidateDraft

        draft = CandidateDraft(artifact=dict(task.initial_artifact), operator_id="initial")
    candidate = Candidate.from_draft(task, draft)
    adapter = LocalCommandBenchmarkAdapter({task.id: task})
    run_id = args.run_id or "eval_local"
    store.save_candidate(run_id, candidate)
    evaluator = EvaluationService(adapter, store=store, run_id=run_id, trace=trace, cache_enabled=False)
    result = evaluator.evaluate(task, candidate)
    store.save_candidate(run_id, candidate)
    payload = {
        "candidate_id": candidate.id,
        "score": result.score,
        "error": result.error,
        "logs": result.logs,
        "workspace": str(workspace),
    }
    print(json_dumps(payload))
    return 0 if result.error is None and result.score.feasible else 1


def test_azure(args: argparse.Namespace) -> int:
    client = AzureOpenAIResponsesClient.from_env()
    text = client.complete_text(
        prompt=args.prompt,
        system="Return only the requested answer. Do not include explanations.",
        max_output_tokens=args.max_output_tokens,
    )
    payload = {
        "ok": bool(text.strip()),
        "model": client.config.model,
        "base_url": client.config.base_url,
        "api_version": client.config.api_version,
        "text": text.strip(),
    }
    print(json_dumps(payload))
    return 0 if text.strip() else 1


def _azure_client_with_timeout(timeout_seconds: float) -> AzureOpenAIResponsesClient:
    client = AzureOpenAIResponsesClient.from_env()
    client.config.timeout_seconds = float(timeout_seconds)
    return client


def _safe_id(value: str, max_len: int = 96) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)
    safe = "_".join(part for part in safe.split("_") if part)
    return (safe or "run")[:max_len]


def _csv_values(values: Optional[Iterable[str]]) -> List[str]:
    result: List[str] = []
    for value in values or []:
        for item in str(value).split(","):
            item = item.strip()
            if item:
                result.append(item)
    return result


def _frontier_adapter_from_args(args: argparse.Namespace, benchmark: Optional[str] = None) -> FrontierEngineeringAdapter:
    return FrontierEngineeringAdapter(
        repo_root=Path(args.repo_root) if getattr(args, "repo_root", None) else None,
        benchmark_id=benchmark or getattr(args, "benchmark", "WirelessChannelSimulation/HighReliableSimulation"),
        timeout_seconds=getattr(args, "timeout_seconds", 900.0),
        evaluator_timeout_seconds=getattr(args, "evaluator_timeout_seconds", 300.0),
        runtime_env_name=getattr(args, "runtime_env_name", "frontier-eval-driver"),
        runtime_python_path=getattr(args, "runtime_python_path", None),
    )


def _frontier_task_selection(args: argparse.Namespace) -> List[str]:
    explicit = _csv_values(getattr(args, "benchmarks", None))
    benchmark_file = getattr(args, "benchmarks_file", None)
    if benchmark_file:
        explicit.extend(
            line.strip()
            for line in Path(benchmark_file).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    if explicit:
        task_ids = explicit
    else:
        root = Path(args.repo_root) if getattr(args, "repo_root", None) else None
        task_ids = discover_frontier_task_ids(root)

    include = _csv_values(getattr(args, "include", None))
    exclude = _csv_values(getattr(args, "exclude", None))
    if include:
        task_ids = [task_id for task_id in task_ids if any(fnmatch.fnmatch(task_id, pat) for pat in include)]
    if exclude:
        task_ids = [task_id for task_id in task_ids if not any(fnmatch.fnmatch(task_id, pat) for pat in exclude)]

    seen = set()
    deduped = []
    for task_id in task_ids:
        if task_id not in seen:
            seen.add(task_id)
            deduped.append(task_id)
    limit = int(getattr(args, "limit", 0) or 0)
    return deduped[:limit] if limit > 0 else deduped


def _frontier_candidate_rel(task) -> str:
    return str(
        task.metadata.get("candidate_destination_rel")
        or task.metadata.get("initial_program_rel")
        or "solution.py"
    )


def _seed_frontier_task_from_file(task, candidate_file: Optional[str]) -> None:
    if not candidate_file:
        return
    task.initial_artifact = {
        "files": {_frontier_candidate_rel(task): Path(candidate_file).read_text(encoding="utf-8")}
    }


def _frontier_operator_library(args: argparse.Namespace, task) -> OperatorLibrary:
    operator_items = []
    if args.operator in ("llm", "mixed"):
        operator_items.append(
            AzureCodeEditOperator(
                client=_azure_client_with_timeout(args.llm_timeout_seconds),
                path=_frontier_candidate_rel(task),
                samples=args.samples,
                max_output_tokens=args.max_output_tokens,
                request_retries=args.llm_retries,
            )
        )
    if args.operator in ("float-jitter", "mixed"):
        operator_items.append(
            RegexFloatJitterOperator(
                path=_frontier_candidate_rel(task),
                samples=args.jitter_samples,
                changes_per_sample=args.jitter_changes,
                relative_jitter=args.float_relative_jitter,
                absolute_jitter=args.float_absolute_jitter,
                min_abs_value=args.float_min_abs,
                region=args.jitter_region,
            )
        )
    return OperatorLibrary(operator_items)


def _run_frontier_search(
    args: argparse.Namespace, benchmark: str, run_id: Optional[str] = None
) -> Tuple[object, Dict[str, Any]]:
    workspace = Path(args.workspace)
    adapter = _frontier_adapter_from_args(args, benchmark=benchmark)
    task = adapter.load_task(benchmark)
    _seed_frontier_task_from_file(task, getattr(args, "candidate_file", None))
    trace_name = _safe_id(run_id or benchmark) + "_trace.jsonl"
    trace = TraceRecorder(workspace / "traces" / trace_name)
    controller_cls = ArchiveSearchController if args.search == "archive" else GreedySearchController
    controller = controller_cls(
        adapter=adapter,
        operators=_frontier_operator_library(args, task),
        store=FileArtifactStore(workspace / "runs"),
        config=SearchConfig(
            max_iterations=args.iterations,
            max_evaluations=args.max_evaluations,
            parent_pool_size=args.parent_pool_size,
            seed=args.seed,
            metadata={"benchmark": benchmark, "adapter": "frontier_engineering", "operator": args.operator},
        ),
        trace=trace,
    )
    result = controller.run(task, run_id=run_id)
    payload = {
        "summary": result.summary,
        "best_artifact": result.best.artifact if result.best else None,
        "workspace": str(workspace),
        "trace": str(trace.path),
    }
    return result, payload


def _score_metric(summary, key: str) -> object:
    if summary is None or summary.best_score is None:
        return ""
    return summary.best_score.metrics.get(key, "")


def _frontier_run_row(result, payload: Dict[str, Any], error: Optional[str] = None) -> Dict[str, Any]:
    summary = result.summary if result is not None else None
    best_score = summary.best_score if summary is not None else None
    return {
        "benchmark": summary.task_id if summary is not None else "",
        "run_id": summary.run_id if summary is not None else "",
        "ok": bool(best_score and best_score.feasible and not error),
        "evaluations": summary.evaluations if summary is not None else "",
        "best_objective": best_score.objective if best_score is not None else "",
        "combined_score": _score_metric(summary, "combined_score"),
        "valid": _score_metric(summary, "valid"),
        "workspace": payload.get("workspace", "") if payload else "",
        "trace": payload.get("trace", "") if payload else "",
        "error": error or "",
    }


def _frontier_rows_markdown(rows: List[Dict[str, Any]], columns: List[str], title: str) -> str:
    lines = [
        "# %s" % title,
        "",
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        values = [str(row.get(column, "")).replace("\n", " ") for column in columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def _write_frontier_rows(rows: List[Dict[str, Any]], output: Optional[str], fmt: str, title: str) -> Optional[Path]:
    if not output:
        return None
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        path.write_text(json_dumps(rows) + "\n", encoding="utf-8")
    else:
        columns = list(rows[0].keys()) if rows else ["benchmark", "ok", "error"]
        path.write_text(_frontier_rows_markdown(rows, columns, title), encoding="utf-8")
    return path


def eval_frontier(args: argparse.Namespace) -> int:
    adapter = _frontier_adapter_from_args(args)
    task = adapter.load_task(args.benchmark)
    artifact = dict(task.initial_artifact)
    if args.candidate_file:
        candidate_rel = _frontier_candidate_rel(task)
        artifact = {"files": {candidate_rel: Path(args.candidate_file).read_text(encoding="utf-8")}}
    candidate = Candidate.from_draft(task, CandidateDraft(artifact=artifact))
    result = adapter.evaluate(task, candidate)
    payload = {
        "candidate_id": candidate.id,
        "task_id": task.id,
        "score": result.score,
        "error": result.error,
        "logs": result.logs,
    }
    print(json_dumps(payload))
    return 0 if result.error is None and result.score.feasible else 1


def eval_ale(args: argparse.Namespace) -> int:
    adapter = ALEBenchAdapter(
        repo_root=Path(args.repo_root) if args.repo_root else None,
        problem_id=args.problem,
        lite_version=args.lite,
        code_language=args.code_language,
        judge_version=args.judge_version,
        eval_split=args.split,
        num_workers=args.num_workers,
        timeout_seconds=args.timeout_seconds,
    )
    task = adapter.load_task(args.problem)
    artifact = dict(task.initial_artifact)
    if args.candidate_file:
        artifact = {
            "code": Path(args.candidate_file).read_text(encoding="utf-8"),
            "code_language": args.code_language,
            "judge_version": args.judge_version,
            "eval_split": args.split,
        }
    candidate = Candidate.from_draft(task, CandidateDraft(artifact=artifact))
    result = adapter.evaluate(task, candidate)
    payload = {
        "candidate_id": candidate.id,
        "task_id": task.id,
        "score": result.score,
        "error": result.error,
        "logs": result.logs,
    }
    print(json_dumps(payload))
    return 0 if result.error is None and result.score.feasible else 1


def run_frontier(args: argparse.Namespace) -> int:
    result, payload = _run_frontier_search(args, args.benchmark, run_id=args.run_id)
    print(json_dumps(payload))
    return 0 if result.best and result.best.score and result.best.score.feasible else 1


def list_frontier(args: argparse.Namespace) -> int:
    task_ids = _frontier_task_selection(args)
    rows = [{"benchmark": task_id} for task_id in task_ids]
    _write_frontier_rows(rows, args.output, args.format, "Frontier Tasks")
    if args.format == "json":
        print(json_dumps(rows))
    else:
        print(_frontier_rows_markdown(rows, ["benchmark"], "Frontier Tasks"), end="")
    return 0


def frontier_smoke(args: argparse.Namespace) -> int:
    rows: List[Dict[str, Any]] = []
    task_ids = _frontier_task_selection(args)
    if not task_ids:
        rows.append(
            {
                "benchmark": "",
                "ok": False,
                "objective": "",
                "combined_score": "",
                "valid": "",
                "runtime_s": "",
                "error": "no Frontier tasks selected",
            }
        )
    for benchmark in task_ids:
        row: Dict[str, Any] = {
            "benchmark": benchmark,
            "ok": False,
            "objective": "",
            "combined_score": "",
            "valid": "",
            "runtime_s": "",
            "error": "",
        }
        try:
            adapter = _frontier_adapter_from_args(args, benchmark=benchmark)
            task = adapter.load_task(benchmark)
            candidate = Candidate.from_draft(task, CandidateDraft(artifact=dict(task.initial_artifact)))
            result = adapter.evaluate(task, candidate)
            row.update(
                {
                    "ok": result.error is None and result.score.feasible,
                    "objective": result.score.objective,
                    "combined_score": result.score.metrics.get("combined_score", ""),
                    "valid": result.score.metrics.get("valid", ""),
                    "runtime_s": result.score.metrics.get("runtime_s", ""),
                    "error": result.error or "",
                }
            )
        except Exception as exc:
            row["error"] = "%s: %s" % (type(exc).__name__, exc)
        rows.append(row)

    _write_frontier_rows(rows, args.output, args.format, "Frontier Baseline Smoke")
    if args.format == "json":
        print(json_dumps(rows))
    else:
        print(
            _frontier_rows_markdown(
                rows,
                ["benchmark", "ok", "objective", "combined_score", "valid", "error"],
                "Frontier Baseline Smoke",
            ),
            end="",
        )
    all_ok = all(bool(row.get("ok")) for row in rows)
    return 1 if args.fail_on_error and not all_ok else 0


def run_frontier_suite(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    prefix = args.run_id_prefix or ("frontier_suite_%s" % timestamp)
    rows: List[Dict[str, Any]] = []
    task_ids = _frontier_task_selection(args)
    if not task_ids:
        rows.append(
            {
                "benchmark": "",
                "run_id": "",
                "ok": False,
                "evaluations": "",
                "best_objective": "",
                "combined_score": "",
                "valid": "",
                "workspace": str(workspace),
                "trace": "",
                "error": "no Frontier tasks selected",
            }
        )
    for index, benchmark in enumerate(task_ids, start=1):
        run_id = "%s_%03d_%s" % (prefix, index, _safe_id(benchmark, max_len=72))
        try:
            result, payload = _run_frontier_search(args, benchmark, run_id=run_id)
            rows.append(_frontier_run_row(result, payload))
        except Exception as exc:
            rows.append(
                {
                    "benchmark": benchmark,
                    "run_id": run_id,
                    "ok": False,
                    "evaluations": "",
                    "best_objective": "",
                    "combined_score": "",
                    "valid": "",
                    "workspace": str(workspace),
                    "trace": "",
                    "error": "%s: %s" % (type(exc).__name__, exc),
                }
            )
        if args.stop_on_error and rows[-1].get("error"):
            break

    suite_dir = workspace / "suite"
    suite_dir.mkdir(parents=True, exist_ok=True)
    json_path = suite_dir / ("%s_summary.json" % prefix)
    md_path = suite_dir / ("%s_summary.md" % prefix)
    json_path.write_text(json_dumps(rows) + "\n", encoding="utf-8")
    md_path.write_text(
        _frontier_rows_markdown(
            rows,
            ["benchmark", "run_id", "ok", "evaluations", "best_objective", "combined_score", "valid", "error"],
            "Frontier Suite Summary",
        ),
        encoding="utf-8",
    )
    _write_frontier_rows(rows, args.output, args.format, "Frontier Suite Summary")
    payload = {"rows": rows, "summary_json": str(json_path), "summary_markdown": str(md_path)}
    if args.format == "json":
        print(json_dumps(payload))
    else:
        print(md_path.read_text(encoding="utf-8"), end="")
    all_ok = all(bool(row.get("ok")) for row in rows)
    return 1 if args.fail_on_error and not all_ok else 0


def run_ale(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace)
    public_adapter = ALEBenchAdapter(
        repo_root=Path(args.repo_root) if args.repo_root else None,
        problem_id=args.problem,
        lite_version=args.lite,
        code_language=args.code_language,
        judge_version=args.judge_version,
        eval_split="public",
        num_workers=args.num_workers,
        timeout_seconds=args.timeout_seconds,
    )
    task = public_adapter.load_task(args.problem)
    trace = TraceRecorder(workspace / "traces" / "ale_trace.jsonl")
    if args.operator == "numeric":
        operator_items = [
            RegexNumberJitterOperator(
                samples=args.samples,
                changes_per_sample=args.numeric_changes,
                jitter=args.numeric_jitter,
                min_abs_value=args.numeric_min_abs,
            )
        ]
    else:
        operator_items = [
            AzureCodeEditOperator(
                client=_azure_client_with_timeout(args.llm_timeout_seconds),
                samples=args.samples,
                max_output_tokens=args.max_output_tokens,
                request_retries=args.llm_retries,
            )
        ]
    operators = OperatorLibrary(operator_items)
    controller_cls = ArchiveSearchController if args.search == "archive" else GreedySearchController
    controller = controller_cls(
        adapter=public_adapter,
        operators=operators,
        store=FileArtifactStore(workspace / "runs"),
        config=SearchConfig(
            max_iterations=args.iterations,
            max_evaluations=args.max_evaluations,
            parent_pool_size=args.parent_pool_size,
            seed=args.seed,
            metadata={"problem": args.problem, "adapter": "ale_bench", "search_split": "public"},
        ),
        trace=trace,
    )
    result = controller.run(task, run_id=args.run_id)
    final_private = None
    if args.private_final and result.best is not None:
        private_adapter = ALEBenchAdapter(
            repo_root=Path(args.repo_root) if args.repo_root else None,
            problem_id=args.problem,
            lite_version=args.lite,
            code_language=args.code_language,
            judge_version=args.judge_version,
            eval_split="private",
            num_workers=args.num_workers,
            timeout_seconds=args.timeout_seconds,
        )
        final_private = private_adapter.evaluate(task, result.best)
    payload = {
        "summary": result.summary,
        "best_artifact": result.best.artifact if result.best else None,
        "final_private": final_private,
        "workspace": str(workspace),
        "trace": str(trace.path),
    }
    print(json_dumps(payload))
    ok = result.best is not None and result.best.score is not None and result.best.score.feasible
    return 0 if ok else 1


def summarize_runs(args: argparse.Namespace) -> int:
    paths = [Path(value) for value in (args.paths or [".open_evolve"])]
    rows = collect_run_summary_rows(paths)
    if args.output:
        if args.format == "json":
            write_run_summary_json(rows, Path(args.output))
        else:
            write_run_summary_markdown(rows, Path(args.output))
    if args.format == "json":
        print(json_dumps(rows))
    else:
        lines = [
            "| Run | Task | Evaluations | Best objective | Combined | Valid |",
            "|-----|------|-------------|----------------|----------|-------|",
        ]
        for row in rows:
            if row.get("error"):
                lines.append("| %s | ERROR |  |  | %s |  |" % (row.get("path", ""), row.get("error", "")))
            else:
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
        print("\n".join(lines))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Open Evolve framework CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    toy = subparsers.add_parser("run-toy", help="Run the toy numeric optimization benchmark")
    toy.add_argument("--workspace", default=".open_evolve")
    toy.add_argument("--iterations", type=int, default=8)
    toy.add_argument("--max-evaluations", type=int, default=80)
    toy.add_argument("--target", type=int, default=10)
    toy.add_argument("--seed", type=int, default=0)
    toy.add_argument("--run-id", default=None)
    toy.add_argument("--search", choices=["greedy", "archive"], default="greedy")
    toy.set_defaults(func=run_toy)

    local = subparsers.add_parser("eval-local", help="Evaluate a JSON candidate with LocalCommandBenchmarkAdapter")
    local.add_argument("--workspace", default=".open_evolve/local")
    local.add_argument("--task-config", required=True)
    local.add_argument("--candidate-json", default=None)
    local.add_argument("--run-id", default=None)
    local.set_defaults(func=eval_local)

    azure = subparsers.add_parser("test-azure", help="Smoke test Azure OpenAI managed-identity Responses call")
    azure.add_argument("--prompt", default="Return exactly: OPEN_EVOLVE_OK")
    azure.add_argument("--max-output-tokens", type=int, default=32)
    azure.set_defaults(func=test_azure)

    frontier_eval = subparsers.add_parser("eval-frontier", help="Evaluate one Frontier-Engineering candidate")
    frontier_eval.add_argument("--repo-root", default=None)
    frontier_eval.add_argument("--benchmark", default="WirelessChannelSimulation/HighReliableSimulation")
    frontier_eval.add_argument("--candidate-file", default=None)
    frontier_eval.add_argument("--timeout-seconds", type=float, default=900.0)
    frontier_eval.add_argument("--evaluator-timeout-seconds", type=float, default=300.0)
    frontier_eval.add_argument("--runtime-env-name", default="frontier-eval-driver")
    frontier_eval.add_argument("--runtime-python-path", default=None)
    frontier_eval.set_defaults(func=eval_frontier)

    frontier_list = subparsers.add_parser("list-frontier", help="List discovered Frontier-Engineering tasks")
    frontier_list.add_argument("--repo-root", default=None)
    frontier_list.add_argument("--benchmarks", action="append", default=[])
    frontier_list.add_argument("--benchmarks-file", default=None)
    frontier_list.add_argument("--include", action="append", default=[])
    frontier_list.add_argument("--exclude", action="append", default=[])
    frontier_list.add_argument("--limit", type=int, default=0)
    frontier_list.add_argument("--format", choices=["markdown", "json"], default="markdown")
    frontier_list.add_argument("--output", default=None)
    frontier_list.set_defaults(func=list_frontier)

    frontier_smoke_parser = subparsers.add_parser(
        "frontier-smoke", help="Evaluate initial candidates for multiple Frontier-Engineering tasks"
    )
    frontier_smoke_parser.add_argument("--repo-root", default=None)
    frontier_smoke_parser.add_argument("--benchmarks", action="append", default=[])
    frontier_smoke_parser.add_argument("--benchmarks-file", default=None)
    frontier_smoke_parser.add_argument("--include", action="append", default=[])
    frontier_smoke_parser.add_argument("--exclude", action="append", default=[])
    frontier_smoke_parser.add_argument("--limit", type=int, default=0)
    frontier_smoke_parser.add_argument("--timeout-seconds", type=float, default=900.0)
    frontier_smoke_parser.add_argument("--evaluator-timeout-seconds", type=float, default=300.0)
    frontier_smoke_parser.add_argument("--runtime-env-name", default="frontier-eval-driver")
    frontier_smoke_parser.add_argument("--runtime-python-path", default=None)
    frontier_smoke_parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    frontier_smoke_parser.add_argument("--output", default=None)
    frontier_smoke_parser.add_argument("--fail-on-error", action="store_true")
    frontier_smoke_parser.set_defaults(func=frontier_smoke)

    ale_eval = subparsers.add_parser("eval-ale", help="Evaluate one ALE-Bench candidate")
    ale_eval.add_argument("--repo-root", default=None)
    ale_eval.add_argument("--problem", default="ahc039")
    ale_eval.set_defaults(lite=True)
    ale_eval.add_argument("--lite", dest="lite", action="store_true")
    ale_eval.add_argument("--no-lite", dest="lite", action="store_false")
    ale_eval.add_argument("--candidate-file", default=None)
    ale_eval.add_argument("--code-language", default="cpp20")
    ale_eval.add_argument("--judge-version", default="202301")
    ale_eval.add_argument("--split", choices=["public", "private"], default="public")
    ale_eval.add_argument("--num-workers", type=int, default=1)
    ale_eval.add_argument("--timeout-seconds", type=float, default=900.0)
    ale_eval.set_defaults(func=eval_ale)

    frontier_run = subparsers.add_parser("run-frontier", help="Run LLM search on Frontier-Engineering")
    frontier_run.add_argument("--workspace", default=".open_evolve/frontier")
    frontier_run.add_argument("--repo-root", default=None)
    frontier_run.add_argument("--benchmark", default="WirelessChannelSimulation/HighReliableSimulation")
    frontier_run.add_argument("--candidate-file", default=None)
    frontier_run.add_argument("--iterations", type=int, default=3)
    frontier_run.add_argument("--max-evaluations", type=int, default=5)
    frontier_run.add_argument("--parent-pool-size", type=int, default=1)
    frontier_run.add_argument("--seed", type=int, default=0)
    frontier_run.add_argument("--run-id", default=None)
    frontier_run.add_argument("--search", choices=["greedy", "archive"], default="greedy")
    frontier_run.add_argument("--operator", choices=["llm", "float-jitter", "mixed"], default="llm")
    frontier_run.add_argument("--samples", type=int, default=1)
    frontier_run.add_argument("--max-output-tokens", type=int, default=4096)
    frontier_run.add_argument("--llm-timeout-seconds", type=float, default=180.0)
    frontier_run.add_argument("--llm-retries", type=int, default=2)
    frontier_run.add_argument("--jitter-samples", type=int, default=4)
    frontier_run.add_argument("--jitter-changes", type=int, default=2)
    frontier_run.add_argument("--float-relative-jitter", type=float, default=0.15)
    frontier_run.add_argument("--float-absolute-jitter", type=float, default=0.0)
    frontier_run.add_argument("--float-min-abs", type=float, default=1e-9)
    frontier_run.add_argument("--jitter-region", choices=["auto", "all", "evolve-block", "allowed-section"], default="auto")
    frontier_run.add_argument("--timeout-seconds", type=float, default=900.0)
    frontier_run.add_argument("--evaluator-timeout-seconds", type=float, default=300.0)
    frontier_run.add_argument("--runtime-env-name", default="frontier-eval-driver")
    frontier_run.add_argument("--runtime-python-path", default=None)
    frontier_run.set_defaults(func=run_frontier)

    frontier_suite = subparsers.add_parser("run-frontier-suite", help="Run search over multiple Frontier-Engineering tasks")
    frontier_suite.add_argument("--workspace", default=".open_evolve/frontier_suite")
    frontier_suite.add_argument("--repo-root", default=None)
    frontier_suite.add_argument("--benchmarks", action="append", default=[])
    frontier_suite.add_argument("--benchmarks-file", default=None)
    frontier_suite.add_argument("--include", action="append", default=[])
    frontier_suite.add_argument("--exclude", action="append", default=[])
    frontier_suite.add_argument("--limit", type=int, default=0)
    frontier_suite.add_argument("--iterations", type=int, default=3)
    frontier_suite.add_argument("--max-evaluations", type=int, default=5)
    frontier_suite.add_argument("--parent-pool-size", type=int, default=1)
    frontier_suite.add_argument("--seed", type=int, default=0)
    frontier_suite.add_argument("--run-id-prefix", default=None)
    frontier_suite.add_argument("--search", choices=["greedy", "archive"], default="greedy")
    frontier_suite.add_argument("--operator", choices=["llm", "float-jitter", "mixed"], default="float-jitter")
    frontier_suite.add_argument("--samples", type=int, default=1)
    frontier_suite.add_argument("--max-output-tokens", type=int, default=4096)
    frontier_suite.add_argument("--llm-timeout-seconds", type=float, default=180.0)
    frontier_suite.add_argument("--llm-retries", type=int, default=2)
    frontier_suite.add_argument("--jitter-samples", type=int, default=4)
    frontier_suite.add_argument("--jitter-changes", type=int, default=2)
    frontier_suite.add_argument("--float-relative-jitter", type=float, default=0.15)
    frontier_suite.add_argument("--float-absolute-jitter", type=float, default=0.0)
    frontier_suite.add_argument("--float-min-abs", type=float, default=1e-9)
    frontier_suite.add_argument("--jitter-region", choices=["auto", "all", "evolve-block", "allowed-section"], default="auto")
    frontier_suite.add_argument("--timeout-seconds", type=float, default=900.0)
    frontier_suite.add_argument("--evaluator-timeout-seconds", type=float, default=300.0)
    frontier_suite.add_argument("--runtime-env-name", default="frontier-eval-driver")
    frontier_suite.add_argument("--runtime-python-path", default=None)
    frontier_suite.add_argument("--format", choices=["markdown", "json"], default="markdown")
    frontier_suite.add_argument("--output", default=None)
    frontier_suite.add_argument("--stop-on-error", action="store_true")
    frontier_suite.add_argument("--fail-on-error", action="store_true")
    frontier_suite.set_defaults(func=run_frontier_suite)

    ale_run = subparsers.add_parser("run-ale", help="Run LLM search on ALE-Bench public split")
    ale_run.add_argument("--workspace", default=".open_evolve/ale")
    ale_run.add_argument("--repo-root", default=None)
    ale_run.add_argument("--problem", default="ahc039")
    ale_run.set_defaults(lite=True, private_final=False)
    ale_run.add_argument("--lite", dest="lite", action="store_true")
    ale_run.add_argument("--no-lite", dest="lite", action="store_false")
    ale_run.add_argument("--iterations", type=int, default=3)
    ale_run.add_argument("--max-evaluations", type=int, default=5)
    ale_run.add_argument("--parent-pool-size", type=int, default=1)
    ale_run.add_argument("--seed", type=int, default=0)
    ale_run.add_argument("--run-id", default=None)
    ale_run.add_argument("--search", choices=["greedy", "archive"], default="greedy")
    ale_run.add_argument("--samples", type=int, default=1)
    ale_run.add_argument("--operator", choices=["llm", "numeric"], default="llm")
    ale_run.add_argument("--max-output-tokens", type=int, default=4096)
    ale_run.add_argument("--llm-timeout-seconds", type=float, default=180.0)
    ale_run.add_argument("--llm-retries", type=int, default=2)
    ale_run.add_argument("--numeric-jitter", type=int, default=5000)
    ale_run.add_argument("--numeric-changes", type=int, default=2)
    ale_run.add_argument("--numeric-min-abs", type=int, default=1000)
    ale_run.add_argument("--code-language", default="cpp20")
    ale_run.add_argument("--judge-version", default="202301")
    ale_run.add_argument("--num-workers", type=int, default=1)
    ale_run.add_argument("--timeout-seconds", type=float, default=900.0)
    ale_run.add_argument("--private-final", dest="private_final", action="store_true")
    ale_run.add_argument("--no-private-final", dest="private_final", action="store_false")
    ale_run.set_defaults(func=run_ale)

    summary = subparsers.add_parser("summarize-runs", help="Summarize saved run summary.json files")
    summary.add_argument("paths", nargs="*", default=[".open_evolve"])
    summary.add_argument("--format", choices=["markdown", "json"], default="markdown")
    summary.add_argument("--output", default=None)
    summary.set_defaults(func=summarize_runs)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

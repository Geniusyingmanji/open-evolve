"""Command-line entry points."""

from __future__ import annotations

import argparse
from pathlib import Path

from open_evolve.benchmarks.ale_bench import ALEBenchAdapter
from open_evolve.benchmarks.frontier_eng import FrontierEngineeringAdapter
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


def eval_frontier(args: argparse.Namespace) -> int:
    adapter = FrontierEngineeringAdapter(
        repo_root=Path(args.repo_root) if args.repo_root else None,
        benchmark_id=args.benchmark,
        timeout_seconds=args.timeout_seconds,
        evaluator_timeout_seconds=args.evaluator_timeout_seconds,
        runtime_env_name=args.runtime_env_name,
        runtime_python_path=args.runtime_python_path,
    )
    task = adapter.load_task(args.benchmark)
    artifact = dict(task.initial_artifact)
    if args.candidate_file:
        candidate_rel = str(task.metadata.get("candidate_destination_rel") or task.metadata.get("initial_program_rel"))
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
    workspace = Path(args.workspace)
    adapter = FrontierEngineeringAdapter(
        repo_root=Path(args.repo_root) if args.repo_root else None,
        benchmark_id=args.benchmark,
        timeout_seconds=args.timeout_seconds,
        evaluator_timeout_seconds=args.evaluator_timeout_seconds,
        runtime_env_name=args.runtime_env_name,
        runtime_python_path=args.runtime_python_path,
    )
    task = adapter.load_task(args.benchmark)
    trace = TraceRecorder(workspace / "traces" / "frontier_trace.jsonl")
    operator_items = []
    if args.operator in ("llm", "mixed"):
        operator_items.append(
            AzureCodeEditOperator(
                client=_azure_client_with_timeout(args.llm_timeout_seconds),
                path=str(task.metadata.get("candidate_destination_rel") or task.metadata.get("initial_program_rel")),
                samples=args.samples,
                max_output_tokens=args.max_output_tokens,
                request_retries=args.llm_retries,
            )
        )
    if args.operator in ("float-jitter", "mixed"):
        operator_items.append(
            RegexFloatJitterOperator(
                path=str(task.metadata.get("candidate_destination_rel") or task.metadata.get("initial_program_rel")),
                samples=args.jitter_samples,
                changes_per_sample=args.jitter_changes,
                relative_jitter=args.float_relative_jitter,
                absolute_jitter=args.float_absolute_jitter,
                min_abs_value=args.float_min_abs,
                region=args.jitter_region,
            )
        )
    operators = OperatorLibrary(operator_items)
    controller_cls = ArchiveSearchController if args.search == "archive" else GreedySearchController
    controller = controller_cls(
        adapter=adapter,
        operators=operators,
        store=FileArtifactStore(workspace / "runs"),
        config=SearchConfig(
            max_iterations=args.iterations,
            max_evaluations=args.max_evaluations,
            parent_pool_size=args.parent_pool_size,
            seed=args.seed,
            metadata={"benchmark": args.benchmark, "adapter": "frontier_engineering"},
        ),
        trace=trace,
    )
    result = controller.run(task, run_id=args.run_id)
    payload = {
        "summary": result.summary,
        "best_artifact": result.best.artifact if result.best else None,
        "workspace": str(workspace),
        "trace": str(trace.path),
    }
    print(json_dumps(payload))
    return 0 if result.best and result.best.score and result.best.score.feasible else 1


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

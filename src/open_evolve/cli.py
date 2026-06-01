"""Command-line entry points."""

from __future__ import annotations

import argparse
from pathlib import Path

from open_evolve.benchmarks.toy_numeric import ToyNumericBenchmark
from open_evolve.benchmarks.config_loader import load_candidate_draft, load_task_config
from open_evolve.benchmarks.local_command import LocalCommandBenchmarkAdapter
from open_evolve.core.artifact_store import FileArtifactStore
from open_evolve.core.evaluator import EvaluationService
from open_evolve.core.feedback_compute import estimate_effective_feedback_compute
from open_evolve.core.operators import JsonFieldStepOperator, OperatorLibrary, RandomJsonFieldOperator
from open_evolve.core.process_evaluator import evaluate_process_quality
from open_evolve.core.search_controller import ArchiveSearchController, GreedySearchController, SearchConfig
from open_evolve.core.trace_recorder import TraceRecorder
from open_evolve.core.types import json_dumps
from open_evolve.core.types import Candidate
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
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

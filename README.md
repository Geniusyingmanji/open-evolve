# Open Evolve Framework

Harness-first framework for self-evolving agents on open optimization benchmarks such as Frontier-Eng, MLE-bench, ALE-Bench, and RE-Bench.

The first implementation is intentionally small and dependency-free. It provides a working optimization loop, file-backed artifact storage, harness configuration, trace recording, effective-feedback metrics, and a toy benchmark for smoke tests.

## Quick Start

```bash
PYTHONPATH=src python3 -m open_evolve.cli run-toy \
  --workspace .open_evolve/toy \
  --iterations 4 \
  --max-evaluations 40 \
  --target 10 \
  --search archive
```

Expected behavior:
- creates a run under `.open_evolve/toy/runs/`
- writes a harness spec under `.open_evolve/toy/harness_registry/`
- records a trajectory under `.open_evolve/toy/traces/toy_trace.jsonl`
- finds the toy optimum `{"x": 10}` within a few iterations

Run tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Evaluate a local command task from JSON:

```bash
PYTHONPATH=src python3 -m open_evolve.cli eval-local \
  --task-config examples/local_command/task.json \
  --candidate-json examples/local_command/candidate.json \
  --workspace .open_evolve/local
```

Run a local-command search example using a file mutation operator:

```bash
PYTHONPATH=src python3 examples/local_command/run_search.py
```

Smoke test the local Azure managed-identity GPT-5.5 path:

```bash
PYTHONPATH=src python3 -m open_evolve.cli test-azure \
  --prompt 'Return exactly: OPEN_EVOLVE_OK'
```

Run three benchmark-family smoke tests through the same task adapter:

```bash
PYTHONPATH=src python3 examples/benchmark_smoke/run_three_benchmarks.py \
  --workspace .open_evolve/benchmark_smoke
```

This uses GPT-5.5 to propose one candidate for each proxy task, validates the artifact schema, evaluates it with `LocalCommandBenchmarkAdapter`, and writes `report.json` / `report.md`.

Real upstream benchmark bootstrap status is tracked in `benchmark_runs.md`. Current completed real runs:

- ALE-Bench `ahc039` lite/debug public + private eval: all cases `ACCEPTED`.
- Frontier-Eng official smoke and `WirelessChannelSimulation/HighReliableSimulation` baseline: both passed.
- MLE-bench install passed, but official data prepare is blocked until Kaggle credentials are configured.

## Current Modules

```text
src/open_evolve/
  benchmarks/
    base.py              # BenchmarkAdapter interface
    config_loader.py     # JSON task/candidate loader
    local_command.py     # Write files, run eval command, parse score.json
    toy_numeric.py       # Tiny optimization benchmark for smoke tests
  core/
    types.py             # Task, Candidate, ScoreVector, EvaluationResult
    artifact_store.py    # File-backed candidate/evaluation store
    archive.py           # In-memory candidate archive for diversity/islands
    evaluator.py         # EvaluationService with cache + trace hooks
    operators.py         # Mutation operator interface, JSON and file operators
    search_controller.py # Greedy and archive-driven search loops
    trace_recorder.py    # JSONL trajectory recorder
    feedback_compute.py  # Effective Feedback Compute estimate
    process_evaluator.py # Lightweight process quality score
    memory.py            # VerifiedMemoryStore
    model_router.py      # Policy-based model routing stub
    budget.py            # Budget accounting helpers
  harness/
    harness_spec.py      # Declarative HarnessSpec
    registry.py          # File-backed harness registry
    mutation.py          # Safe config-level harness mutations
    governance.py        # Promotion gate checks
    context_builder.py
    tool_router.py
    verifier_registry.py
    replay.py
  agents/
    roles.py             # Declarative role interface
  experiments/
    harness_ablation.py  # Fixed-task harness ablation runner
    reporting.py         # JSON/Markdown ablation reports
  models/
    azure_openai.py      # Azure OpenAI Responses client using local bearer token env
```

## Adapter Contract

To add a real benchmark, implement `BenchmarkAdapter`:

```python
class MyBenchmark(BenchmarkAdapter):
    family = "my_benchmark"

    def load_task(self, task_id: str) -> Task:
        ...

    def initial_candidates(self, task: Task) -> List[CandidateDraft]:
        ...

    def evaluate(self, task: Task, candidate: Candidate) -> EvaluationResult:
        ...
```

The framework expects every candidate to be a JSON-serializable artifact. Real adapters can map that artifact to code files, notebook cells, config files, simulation parameters, or benchmark-specific submissions.

## Local Command Adapter

`LocalCommandBenchmarkAdapter` is the lowest-friction bridge to real tasks. A task provides static evaluator files and an `eval_command`; a candidate provides files to overlay into a temporary workspace. The command must write `score.json`.

Minimal score format:

```json
{
  "objective": 0.0,
  "feasible": true,
  "metrics": {"example": 1},
  "cost": {"eval_calls": 1}
}
```

This adapter is a practical starting point for:
- ALE-Bench tasks that compile/run a submitted heuristic.
- Frontier-Eng tasks that call a simulator/verifier wrapper.
- MLE-bench proxy tasks that run a local CV script and write a score.

In other words, a benchmark task is normalized as:

1. `Task`: objective, family, initial artifact, budget, feasibility metadata.
2. Candidate artifact: usually a `files` mapping from relative path to file content.
3. Evaluator command: runs in an isolated temporary workspace.
4. `score.json`: common `objective / feasible / metrics / cost / risk` output.

Example task config:

```json
{
  "id": "demo",
  "family": "local_command",
  "objective": "Run evaluate.py and maximize objective.",
  "initial_artifact": {
    "files": {
      "solution.json": "{\"x\": 0}"
    }
  },
  "metadata": {
    "eval_command": ["python3", "evaluate.py"],
    "score_file": "score.json",
    "timeout_seconds": 60,
    "static_files": {
      "evaluate.py": "import json\nx=json.load(open('solution.json'))['x']\njson.dump({'objective': -abs(x-5)}, open('score.json','w'))\n"
    }
  }
}
```

Example candidate:

```json
{
  "artifact": {
    "files": {
      "solution.json": "{\"x\": 5}"
    }
  },
  "operator_id": "manual"
}
```

## Harness-First Direction

The framework treats harness design as a first-class optimization target:

- `HarnessSpec` declares tools, context policy, memory policy, verification cascade, feedback policy, search policy, budget policy, promotion gates, and rollback policy.
- `HarnessRegistry` tracks harness variants and their status.
- `mutation.py` only permits safe config-level mutations first.
- `HarnessAblationRunner` runs fixed-task comparisons across multiple specs.
- `reporting.py` writes ablation results to JSON/Markdown.
- source-level harness mutation is intentionally not enabled in the MVP; it should require evidence batches, isolated replay workers, regression suites, diff audit, and rollback.

## Azure GPT-5.5 Local Path

The current local provider shape is:

- wire API: `responses`
- model: `gpt-5.5`
- auth: bearer token from managed identity environment, no API key required
- endpoint shape: `/openai/v1/responses?api-version=preview`

`AzureOpenAIResponsesClient` intentionally does not print or persist tokens. It reads `AZURE_OPENAI_AD_TOKEN` by default, with `AZURE_OPENAI_AUTHORIZATION` as a fallback.

## Real Benchmark Adapters

Current real adapters:

- `FrontierEngineeringAdapter`: wraps Frontier-Engineering unified metadata and evaluator, starting from `WirelessChannelSimulation/HighReliableSimulation`.
- `ALEBenchAdapter`: wraps `ale_bench.start()`, `public_eval()`, and `private_eval()` for `ahc039` lite/debug.

Useful commands:

```bash
PYTHONPATH=src python3 -m open_evolve.cli eval-frontier \
  --benchmark WirelessChannelSimulation/HighReliableSimulation

PYTHONPATH=src python3 -m open_evolve.cli run-frontier \
  --benchmark WirelessChannelSimulation/HighReliableSimulation \
  --workspace .open_evolve/frontier_smoke \
  --iterations 3 --max-evaluations 4 \
  --llm-timeout-seconds 120 --llm-retries 1

PYTHONPATH=src python3 -m open_evolve.cli run-ale \
  --problem ahc039 --lite \
  --operator numeric --iterations 3 --max-evaluations 7 --samples 2

PYTHONPATH=src python3 -m open_evolve.cli eval-ale \
  --problem ahc039 --lite --split private
```

MLE-bench remains blocked on Kaggle credentials for official data preparation.

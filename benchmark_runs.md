# Real Benchmark Bootstrap Runs

Date: 2026-06-01

This file records the first local runs against the real upstream benchmark repositories. Proxy smoke tasks are still useful for framework development, but the results below are from the benchmark repos' own runners.

## Repositories

| Benchmark | Repository | Local path | Status |
|-----------|------------|------------|--------|
| MLE-bench | `https://github.com/openai/mle-bench` | `/data/zyf/benchmarks/mle-bench` | cloned, installed, data prepare blocked by Kaggle credentials |
| ALE-Bench | `https://github.com/SakanaAI/ALE-Bench` | `/data/zyf/benchmarks/ALE-Bench` | cloned, installed, real task eval passed |
| Frontier-Eng | `https://github.com/EinsiaLab/Frontier-Engineering` | `/data/zyf/benchmarks/Frontier-Engineering` | cloned, driver initialized, smoke and single-task baseline passed |

`openai/frontier-evals` was also cloned while locating Frontier-Eng, but it is not the Frontier-Eng benchmark requested here.

## MLE-Bench

Setup:

```bash
cd /data/zyf/benchmarks/mle-bench
uv venv --python 3.11 .venv
uv pip install -e .
```

Attempted official data preparation on a small lite task:

```bash
mkdir -p /data/zyf/benchmarks/mle-data
.venv/bin/mlebench prepare \
  -c detecting-insults-in-social-commentary \
  --data-dir /data/zyf/benchmarks/mle-data \
  --skip-verification
```

Result: blocked at Kaggle authentication. The repo installed successfully, but official `prepare` requires Kaggle credentials (`kaggle.json` or Kaggle environment credentials). No MLE task score was produced.

## ALE-Bench

Setup:

```bash
cd /data/zyf/benchmarks/ALE-Bench
uv venv --python 3.12 .venv
uv sync --no-dev --extra eval
bash ./scripts/docker_build_202301.sh $(id -u) $(id -g)
```

The Docker build produced local judge images including:

```text
ale-bench:cpp17-202301
ale-bench:cpp20-202301
ale-bench:cpp23-202301
ale-bench:python-202301
ale-bench:rust-202301
```

Initial README example note: current ALE-Bench has `ahc001` in the full set, not the lite/debug set. A full `ahc001` start was too slow for a quick smoke, so the first completed run used a real lite/debug task: `ahc039`.

Completed run:

```bash
cd /data/zyf/benchmarks/ALE-Bench
.venv/bin/python - <<'PY'
import ale_bench

code = r'''
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
'''

session = ale_bench.start(problem_id="ahc039", lite_version=True, num_workers=1)
public_result = session.public_eval(code, code_language="cpp20", judge_version="202301")
private_result, rank, performance = session.private_eval(code, code_language="cpp20", judge_version="202301")
session.close()
PY
```

Result:

| Field | Value |
|-------|-------|
| Problem | `ahc039` |
| Set | `lite_version=True` |
| Public cases | 5 |
| Private cases | 150 |
| Public judge | all `ACCEPTED` |
| Public absolute score | `1739` |
| Private judge | all `ACCEPTED` |
| Private absolute score | `56814` |
| Estimated rank | `531` |
| Estimated performance | `973` |

## Frontier-Eng

Setup:

```bash
cd /data/zyf/benchmarks/Frontier-Engineering
bash init.sh
```

Host note: `Octave` is not installed, so Octave-backed tasks such as `Astrodynamics/MannedLunarLanding` are not ready. The smoke test and selected CPU task below do not require it.

Official smoke:

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=smoke \
  algorithm=openevolve \
  algorithm.iterations=0
```

Result:

| Metric | Value |
|--------|-------|
| `combined_score` | `1.0` |
| `valid` | `1.0` |
| `runtime_s` | `0.0179` |
| Output | `/data/zyf/benchmarks/Frontier-Engineering/runs/smoke/openevolve/gpt-4o-mini/20260601_063237/` |

Single real task baseline from the README:

```bash
.venvs/frontier-eval-driver/bin/python -m frontier_eval \
  task=unified \
  task.benchmark=WirelessChannelSimulation/HighReliableSimulation \
  algorithm=openevolve \
  algorithm.iterations=0
```

Result:

| Metric | Value |
|--------|-------|
| `combined_score` | `165.49228239490498` |
| `valid` | `1.0` |
| `timeout` | `0.0` |
| `runtime_s` | `14.3771` |
| `benchmark_returncode` | `0.0` |
| Output | `/data/zyf/benchmarks/Frontier-Engineering/runs/unified__WirelessChannelSimulation__HighReliableSimulation/openevolve/gpt-4o-mini/20260601_063301/` |

## Immediate Implications

## Open Evolve Adapter Runs

These runs use the framework adapters in `src/open_evolve/benchmarks`, not direct one-off scripts.

### Frontier-Engineering adapter

Baseline adapter eval:

```bash
PYTHONPATH=src python3 -m open_evolve.cli eval-frontier \
  --benchmark WirelessChannelSimulation/HighReliableSimulation
```

Result: `valid=1.0`, `combined_score=151.69891010244862`, `runtime_s=16.0193`.

GPT-5.5 1-iteration smoke:

```bash
PYTHONPATH=src python3 -m open_evolve.cli run-frontier \
  --benchmark WirelessChannelSimulation/HighReliableSimulation \
  --workspace .open_evolve/frontier_smoke \
  --run-id frontier_smoke_gpt55_1iter_sourceonly \
  --iterations 1 --max-evaluations 2 \
  --max-output-tokens 7000 --llm-timeout-seconds 120 --llm-retries 1
```

Result: 2 evaluations, best `valid=1.0`, best `combined_score=195.39841489926056`.

GPT-5.5 3-iteration smoke:

```bash
PYTHONPATH=src python3 -m open_evolve.cli run-frontier \
  --benchmark WirelessChannelSimulation/HighReliableSimulation \
  --workspace .open_evolve/frontier_smoke \
  --run-id frontier_smoke_gpt55_3iter_sourceonly \
  --iterations 3 --max-evaluations 4 \
  --max-output-tokens 7000 --llm-timeout-seconds 120 --llm-retries 1
```

Result: 4 evaluations, 3 iterations, best `valid=1.0`, best `combined_score=197.71118522053231`.

Implementation note: the first JSON-wrapped LLM operator shape timed out for full-file generation. The operator now asks for complete source directly, uses shorter context, and treats LLM timeouts as no-draft events instead of crashing the controller.

### ALE-Bench adapter

Adapter public eval:

```bash
PYTHONPATH=src python3 -m open_evolve.cli eval-ale \
  --problem ahc039 --lite --split public \
  --code-language cpp20 --judge-version 202301
```

Result: 5/5 public cases `ACCEPTED`, public absolute score `1739`.

Public-search numeric 3-iteration smoke:

```bash
PYTHONPATH=src python3 -m open_evolve.cli run-ale \
  --problem ahc039 --lite \
  --workspace .open_evolve/ale_smoke \
  --run-id ale_ahc039_numeric_3iter_public \
  --iterations 3 --max-evaluations 7 --samples 2 \
  --operator numeric --numeric-jitter 7000 --numeric-changes 2 \
  --code-language cpp20 --judge-version 202301
```

Result: 7 public evaluations, 3 iterations, best public score stayed at `1739`. The adapter/search loop is stable, but naive coordinate jitter did not improve the baseline.

Private final eval of the selected best:

```bash
PYTHONPATH=src python3 -m open_evolve.cli eval-ale \
  --problem ahc039 --lite --split private \
  --code-language cpp20 --judge-version 202301
```

Result: 150/150 private cases `ACCEPTED`, private absolute score `56814`, estimated rank `531`, estimated performance `973`.

## Immediate Implications

1. ALE-Bench and Frontier-Eng are now wrapped by real framework adapters and can run through the same search/evaluation/store path.
2. Frontier GPT-5.5 full-file evolution is viable on the selected CPU task; a larger 20-50 eval campaign is the next useful quality signal.
3. ALE-Bench needs a stronger task-specific generator/repair loop. The adapter is stable, but naive numeric jitter and the first LLM prompt do not yet improve `ahc039`.
4. MLE-bench needs Kaggle credentials before official prepare/grade can run.
5. For Frontier-Eng, start with CPU/self-contained tasks before full `v1` validation because some tasks need Octave, Docker, CUDA, or external assets.

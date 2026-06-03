# Codex Harness Summary

## Local Invocation

The local Codex path uses Azure managed identity, not an API key:

```bash
/home/azureuser/zicong/OpenAgentScaler/scripts/codex-azure-mi \
  -p azure_uami exec --json --ephemeral -C /tmp --skip-git-repo-check \
  'Return exactly OPEN_EVOLVE_CODEX_SMOKE and nothing else.'
```

The helper refreshes a managed-identity bearer token and runs Codex with the
`azure_uami` profile. The profile points at the local Azure proxy and uses
`gpt-5.5`.

## Framework Integration

`CodexCliEditOperator` writes a candidate source file, task context, and latest
evaluation feedback into a temporary workspace, runs Codex CLI, then reads the
edited source back as a candidate artifact.

Frontier examples:

```bash
PYTHONPATH=src python3 -m open_evolve.cli run-frontier \
  --benchmark Robotics/PIDTuning \
  --workspace .open_evolve/frontier_codex \
  --operator codex \
  --iterations 2 --max-evaluations 3 \
  --codex-timeout-seconds 300
```

```bash
PYTHONPATH=src python3 -m open_evolve.cli run-frontier-suite \
  --benchmarks-file tasks.txt \
  --workspace .open_evolve/frontier_codex_suite \
  --operator codex-mixed \
  --iterations 3 --max-evaluations 8
```

## Smoke Results

- Direct Codex smoke returned `OPEN_EVOLVE_CODEX_SMOKE`.
- Open-evolve operator smoke edited a temporary `solution.py` from `return 1`
  to `return 2`.
- Frontier `Robotics/PIDTuning` Codex smoke:
  - run: `frontier_pid_codex_smoke_20260603_075041`
  - evaluations: 2
  - baseline: `0.0366267666`
  - best: `0.0834244220`
  - valid: `1.0`

This is an improvement over baseline, not a SOTA claim. The earlier safe-jitter
longer run remains stronger on PID (`0.1209846244`), but Codex generated a
nontrivial valid code edit in a single expansion.

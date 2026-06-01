"""Run three benchmark-family smoke tests through the generic task adapter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from open_evolve.benchmarks.config_loader import load_task_config
from open_evolve.benchmarks.local_command import LocalCommandBenchmarkAdapter
from open_evolve.core.types import Candidate, CandidateDraft, json_dumps
from open_evolve.models.azure_openai import AzureOpenAIResponsesClient


ROOT = Path(__file__).resolve().parent

TASKS = {
    "mle_proxy": {
        "config": ROOT / "mle_proxy" / "task.json",
        "file": "pipeline.json",
        "fallback": {
            "model": "gbdt",
            "learning_rate": 0.035,
            "n_estimators": 360,
            "feature_policy": "interaction",
            "leakage_checks": True,
        },
        "prompt": (
            "Return only JSON for a high-scoring MLE-bench proxy pipeline. "
            "Schema: {\"model\": \"gbdt|xgboost|random_forest|linear\", "
            "\"learning_rate\": float, \"n_estimators\": int, "
            "\"feature_policy\": \"interaction|target_safe|basic\", "
            "\"leakage_checks\": true}. Hard constraints: 0.001 <= learning_rate <= 0.5, "
            "10 <= n_estimators <= 1000, leakage_checks must be true. Strong values are near "
            "model=gbdt, learning_rate=0.035, n_estimators=360, feature_policy=interaction."
        ),
    },
    "ale_proxy": {
        "config": ROOT / "ale_proxy" / "task.json",
        "file": "heuristic.json",
        "fallback": {
            "beam_width": 49,
            "lookahead": 3,
            "restart_budget": 160,
            "temperature": 0.7,
            "pruning": "dominance",
        },
        "prompt": (
            "Return only JSON for a high-scoring ALE-Bench proxy heuristic. "
            "Schema: {\"beam_width\": int, \"lookahead\": int, "
            "\"restart_budget\": int, \"temperature\": float, "
            "\"pruning\": \"dominance|bound|none\"}. Hard constraints: 1 <= beam_width <= 128, "
            "1 <= lookahead <= 5, beam_width * lookahead <= 220, 0 <= restart_budget <= 300, "
            "0.0 <= temperature <= 2.0. Strong values are near beam_width=49, lookahead=3, "
            "restart_budget=160, temperature=0.7, pruning=dominance."
        ),
    },
    "frontier_proxy": {
        "config": ROOT / "frontier_proxy" / "task.json",
        "file": "design.json",
        "fallback": {
            "material": "titanium",
            "wall_thickness_mm": 5.2,
            "cooling_channels": 5,
            "inlet_angle_deg": 42,
            "safety_factor": 1.35,
        },
        "prompt": (
            "Return only JSON for a high-scoring Frontier-Eng proxy design. "
            "Schema: {\"material\": \"titanium|steel|aluminum\", "
            "\"wall_thickness_mm\": float, \"cooling_channels\": int, "
            "\"inlet_angle_deg\": float, \"safety_factor\": float}. Hard constraints: "
            "1.2 <= safety_factor <= 2.5, 3.0 <= wall_thickness_mm <= 12.0, "
            "1 <= cooling_channels <= 8, 10 <= inlet_angle_deg <= 70, and if "
            "cooling_channels >= 5 then wall_thickness_mm >= 4.8. Strong values are near "
            "material=titanium, wall_thickness_mm=5.2, cooling_channels=5, inlet_angle_deg=42, "
            "safety_factor=1.35."
        ),
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run three local-command benchmark smoke tests.")
    parser.add_argument("--workspace", default=".open_evolve/benchmark_smoke")
    parser.add_argument("--skip-azure", action="store_true", help="Use deterministic fallback candidates only")
    parser.add_argument(
        "--require-azure",
        action="store_true",
        help="Fail if Azure candidate generation or schema validation fails",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    client = None if args.skip_azure else AzureOpenAIResponsesClient.from_env()

    rows = []
    for name, spec in TASKS.items():
        task = load_task_config(spec["config"])
        artifact, source = candidate_artifact(name, spec, client, require_azure=args.require_azure)
        candidate = Candidate.from_draft(task, CandidateDraft(artifact=artifact, operator_id=source["kind"]))
        adapter = LocalCommandBenchmarkAdapter({task.id: task})
        result = adapter.evaluate(task, candidate)

        task_dir = workspace / name
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "candidate.json").write_text(json_dumps(artifact), encoding="utf-8")
        (task_dir / "result.json").write_text(json_dumps(result), encoding="utf-8")

        rows.append(
            {
                "benchmark": name,
                "task_id": task.id,
                "candidate_source": source,
                "score": result.score,
                "error": result.error,
                "candidate_path": str(task_dir / "candidate.json"),
                "result_path": str(task_dir / "result.json"),
            }
        )

    report = {"workspace": str(workspace), "results": rows}
    (workspace / "report.json").write_text(json_dumps(report), encoding="utf-8")
    (workspace / "report.md").write_text(markdown_report(rows), encoding="utf-8")
    print(json_dumps(report))
    return 0 if all(row["error"] is None and row["score"].feasible for row in rows) else 1


def candidate_artifact(
    name: str,
    spec: Dict[str, Any],
    client: Optional[AzureOpenAIResponsesClient],
    require_azure: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    payload = None
    source = {"kind": "fallback", "reason": "azure skipped"}
    if client is not None:
        try:
            text = client.complete_text(
                prompt=spec["prompt"],
                system=(
                    "You emit one compact JSON object and nothing else. "
                    "Use the provided schema exactly. Choose strong but feasible values."
                ),
                max_output_tokens=220,
            )
            payload = extract_json_object(text)
            source = {"kind": "azure_gpt55", "model": client.config.model}
            valid, reason = validate_payload(name, payload)
            if not valid:
                if require_azure:
                    raise ValueError(reason)
                payload = None
                source = {
                    "kind": "fallback_after_azure_validation",
                    "model": client.config.model,
                    "reason": reason,
                }
        except Exception as exc:
            if require_azure:
                raise
            source = {"kind": "fallback", "reason": "%s: %s" % (type(exc).__name__, str(exc)[:160])}
    if payload is None:
        payload = dict(spec["fallback"])
    return {"files": {spec["file"]: json.dumps(payload, sort_keys=True)}}, source


def validate_payload(name: str, payload: Dict[str, Any]) -> Tuple[bool, str]:
    try:
        if name == "mle_proxy":
            lr = float(payload.get("learning_rate"))
            n_estimators = int(payload.get("n_estimators"))
            ok = (
                payload.get("model") in ["gbdt", "xgboost", "random_forest", "linear"]
                and payload.get("feature_policy") in ["interaction", "target_safe", "basic"]
                and bool(payload.get("leakage_checks")) is True
                and 0.001 <= lr <= 0.5
                and 10 <= n_estimators <= 1000
            )
            return ok, "mle schema or safe range violation"
        if name == "ale_proxy":
            beam = int(payload.get("beam_width"))
            lookahead = int(payload.get("lookahead"))
            restart = int(payload.get("restart_budget"))
            temperature = float(payload.get("temperature"))
            ok = (
                1 <= beam <= 128
                and 1 <= lookahead <= 5
                and beam * lookahead <= 220
                and 0 <= restart <= 300
                and 0.0 <= temperature <= 2.0
                and payload.get("pruning") in ["dominance", "bound", "none"]
            )
            return ok, "ale schema or runtime range violation"
        if name == "frontier_proxy":
            thickness = float(payload.get("wall_thickness_mm"))
            channels = int(payload.get("cooling_channels"))
            angle = float(payload.get("inlet_angle_deg"))
            safety = float(payload.get("safety_factor"))
            ok = (
                payload.get("material") in ["titanium", "steel", "aluminum"]
                and 1.2 <= safety <= 2.5
                and 3.0 <= thickness <= 12.0
                and 1 <= channels <= 8
                and 10 <= angle <= 70
                and not (channels >= 5 and thickness < 4.8)
            )
            return ok, "frontier schema or hard safety range violation"
    except Exception as exc:
        return False, "%s: %s" % (type(exc).__name__, str(exc)[:80])
    return False, "unknown benchmark"


def extract_json_object(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("expected a JSON object")
    return parsed


def markdown_report(rows) -> str:
    lines = [
        "# Benchmark Smoke Report",
        "",
        "| Benchmark | Source | Feasible | Objective | Error |",
        "|---|---:|---:|---:|---|",
    ]
    for row in rows:
        score = row["score"]
        lines.append(
            "| %s | %s | %s | %.4f | %s |"
            % (
                row["benchmark"],
                row["candidate_source"]["kind"],
                score.feasible,
                score.objective,
                row["error"] or "",
            )
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())

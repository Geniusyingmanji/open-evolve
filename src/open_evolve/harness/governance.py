"""Harness promotion and rollback checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from open_evolve.harness.harness_spec import HarnessSpec


@dataclass
class HarnessPromotionEvidence:
    improved_tasks: List[str] = field(default_factory=list)
    regressed_tasks: List[str] = field(default_factory=list)
    replay_passed: bool = False
    cost_delta: float = 0.0
    process_quality_delta: float = 0.0
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class HarnessPromotionDecision:
    promote: bool
    reasons: List[str] = field(default_factory=list)


def evaluate_promotion(spec: HarnessSpec, evidence: HarnessPromotionEvidence) -> HarnessPromotionDecision:
    reasons: List[str] = []
    gates = spec.promotion_gates
    if not evidence.improved_tasks:
        reasons.append("no improved tasks")
    max_regression = float(gates.get("max_regression", 0.0))
    if evidence.regressed_tasks and max_regression <= 0.0:
        reasons.append("regression tasks present: %s" % ", ".join(evidence.regressed_tasks))
    if gates.get("require_replay", True) and not evidence.replay_passed:
        reasons.append("replay did not pass")
    if evidence.process_quality_delta < 0:
        reasons.append("process quality regressed")
    return HarnessPromotionDecision(promote=not reasons, reasons=reasons)

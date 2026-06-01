"""Budget accounting."""

from __future__ import annotations

from dataclasses import dataclass

from open_evolve.core.types import Budget


@dataclass
class BudgetState:
    evaluations: int = 0
    iterations: int = 0
    tokens: int = 0
    cost: float = 0.0


def budget_allows(budget: Budget, state: BudgetState) -> bool:
    if state.evaluations >= budget.max_evaluations:
        return False
    if state.iterations >= budget.max_iterations:
        return False
    if budget.token_budget is not None and state.tokens >= budget.token_budget:
        return False
    if budget.cost_budget is not None and state.cost >= budget.cost_budget:
        return False
    return True

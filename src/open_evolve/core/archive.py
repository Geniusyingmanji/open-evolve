"""In-memory candidate archive for island and MAP-Elites style search."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from open_evolve.core.types import Candidate, best_candidate


ArchiveKey = Tuple[str, ...]


@dataclass
class ArchiveCell:
    key: ArchiveKey
    candidate_ids: List[str] = field(default_factory=list)
    best_candidate_id: Optional[str] = None


class CandidateArchive:
    def __init__(self, maximize: bool = True) -> None:
        self.maximize = maximize
        self.candidates: Dict[str, Candidate] = {}
        self.cells: Dict[ArchiveKey, ArchiveCell] = {}
        self.artifact_hashes: Dict[str, str] = {}

    def add(self, candidate: Candidate) -> bool:
        if candidate.artifact_hash in self.artifact_hashes:
            return False
        self.candidates[candidate.id] = candidate
        self.artifact_hashes[candidate.artifact_hash] = candidate.id
        key = self.key_for(candidate)
        cell = self.cells.setdefault(key, ArchiveCell(key=key))
        cell.candidate_ids.append(candidate.id)
        current_best = self.candidates.get(cell.best_candidate_id) if cell.best_candidate_id else None
        if candidate.score is not None and (current_best is None or candidate.score.better_than(current_best.score, self.maximize)):
            cell.best_candidate_id = candidate.id
        return True

    def key_for(self, candidate: Candidate) -> ArchiveKey:
        novelty = candidate.metadata.get("novelty_features")
        if isinstance(novelty, list) and novelty:
            return tuple(str(item) for item in novelty)
        return (candidate.operator_id,)

    def best(self) -> Optional[Candidate]:
        return best_candidate(self.candidates.values(), maximize=self.maximize)

    def top_k(self, k: int) -> List[Candidate]:
        evaluated = [candidate for candidate in self.candidates.values() if candidate.score is not None]
        if self.maximize:
            evaluated.sort(key=lambda candidate: (candidate.score.feasible, candidate.score.objective), reverse=True)
        else:
            evaluated.sort(key=lambda candidate: (candidate.score.feasible, -candidate.score.objective), reverse=True)
        return evaluated[:k]

    def diverse_parents(self, limit: int) -> List[Candidate]:
        parents: List[Candidate] = []
        for key in sorted(self.cells.keys()):
            cell = self.cells[key]
            if cell.best_candidate_id and cell.best_candidate_id in self.candidates:
                parents.append(self.candidates[cell.best_candidate_id])
        if self.maximize:
            parents.sort(
                key=lambda candidate: (candidate.score.feasible, candidate.score.objective) if candidate.score else (False, float("-inf")),
                reverse=True,
            )
        else:
            parents.sort(
                key=lambda candidate: (candidate.score.feasible, -candidate.score.objective) if candidate.score else (False, float("-inf")),
                reverse=True,
            )
        return parents[:limit]

    def __len__(self) -> int:
        return len(self.candidates)

    def __iter__(self) -> Iterable[Candidate]:
        return iter(self.candidates.values())

"""File-backed artifact and evaluation store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Optional

from open_evolve.core.types import Candidate, EvaluationResult, RunSummary, json_dumps, to_jsonable


class FileArtifactStore:
    """Persist candidate artifacts, metadata, and evaluation records.

    The store is intentionally simple: every run is a directory with candidate
    subdirectories. This makes early benchmark work easy to inspect and replay.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        path = self.root / run_id
        path.mkdir(parents=True, exist_ok=True)
        (path / "candidates").mkdir(exist_ok=True)
        (path / "evaluations").mkdir(exist_ok=True)
        return path

    def candidate_dir(self, run_id: str, candidate_id: str) -> Path:
        path = self.run_dir(run_id) / "candidates" / candidate_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_candidate(self, run_id: str, candidate: Candidate) -> Path:
        path = self.candidate_dir(run_id, candidate.id)
        (path / "artifact.json").write_text(json_dumps(candidate.artifact) + "\n", encoding="utf-8")
        (path / "metadata.json").write_text(json_dumps(candidate) + "\n", encoding="utf-8")
        return path

    def save_evaluation(self, run_id: str, result: EvaluationResult) -> Path:
        path = self.run_dir(run_id) / "evaluations" / ("%s.json" % result.candidate_id)
        path.write_text(json_dumps(result) + "\n", encoding="utf-8")
        return path

    def save_summary(self, summary: RunSummary) -> Path:
        path = self.run_dir(summary.run_id) / "summary.json"
        path.write_text(json_dumps(summary) + "\n", encoding="utf-8")
        return path

    def load_candidate_artifact(self, run_id: str, candidate_id: str) -> Dict[str, object]:
        path = self.candidate_dir(run_id, candidate_id) / "artifact.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def list_candidate_ids(self, run_id: str) -> Iterable[str]:
        path = self.run_dir(run_id) / "candidates"
        for child in sorted(path.iterdir()):
            if child.is_dir():
                yield child.name

    def load_summary(self, run_id: str) -> Optional[Dict[str, object]]:
        path = self.run_dir(run_id) / "summary.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

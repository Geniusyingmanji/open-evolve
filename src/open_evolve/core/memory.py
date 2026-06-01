"""Verified memory and skill records."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List

from open_evolve.core.types import json_dumps, new_id, utc_ts


@dataclass
class MemoryRecord:
    id: str
    task_family: str
    summary: str
    evidence: Dict[str, object] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    verified: bool = False
    created_at: float = field(default_factory=utc_ts)


class VerifiedMemoryStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def add(
        self,
        task_family: str,
        summary: str,
        evidence: Dict[str, object],
        tags: List[str],
        verified: bool = False,
    ) -> MemoryRecord:
        record = MemoryRecord(
            id=new_id("mem"),
            task_family=task_family,
            summary=summary,
            evidence=evidence,
            tags=tags,
            verified=verified,
        )
        path = self.root / ("%s.json" % record.id)
        path.write_text(json_dumps(record) + "\n", encoding="utf-8")
        return record

    def query(self, task_family: str, require_verified: bool = True) -> Iterable[MemoryRecord]:
        for path in sorted(self.root.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("task_family") != task_family:
                continue
            if require_verified and not payload.get("verified"):
                continue
            yield MemoryRecord(**payload)

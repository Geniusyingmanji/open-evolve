"""File-backed harness registry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Optional

from open_evolve.core.types import json_dumps
from open_evolve.harness.harness_spec import HarnessSpec


class HarnessRegistry:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str, version: str) -> Path:
        safe_name = name.replace("/", "_")
        safe_version = version.replace("/", "_")
        return self.root / ("%s__%s.json" % (safe_name, safe_version))

    def register(self, spec: HarnessSpec, status: str = "candidate") -> Path:
        spec.validate()
        payload = dict(spec.__dict__)
        payload["registry_status"] = status
        path = self._path(spec.name, spec.version)
        path.write_text(json_dumps(payload) + "\n", encoding="utf-8")
        return path

    def load(self, name: str, version: str) -> Optional[Dict[str, object]]:
        path = self._path(name, version)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_specs(self) -> Iterable[Dict[str, object]]:
        for path in sorted(self.root.glob("*.json")):
            yield json.loads(path.read_text(encoding="utf-8"))
